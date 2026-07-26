import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { configureApiSession } from "../api/client";
import type { SettingsResponse, SystemStatus } from "../api/types";
import { SettingsPage } from "./SettingsPage";

const fetchMock = vi.fn();

const settings: SettingsResponse = {
  base_path: "",
  provider_mode: "kubernetes",
  kubeconfig_path: null,
  kube_context: null,
  llm_enabled: false,
  llm_provider: "openai",
  model_endpoint: null,
  api_key: null,
  default_inspection_strategy: {},
  inspection_policy: {
    required_components: [],
    namespace_concurrency: 3,
    max_log_pods: 200,
    retention: {
      inspection_run_days: 30,
      recovered_issue_days: 90,
      notification_delivery_days: 30,
      security_audit_days: 90,
    },
    thresholds: {
      tls_warning_days: 30,
      tls_critical_days: 7,
      pvc_pending_warning_minutes: 5,
      pvc_pending_critical_minutes: 30,
      pv_released_stale_hours: 24,
      job_incomplete_info_minutes: 60,
      resource_usage_warning_percent: 90,
      resource_usage_consecutive_cycles: 3,
      pod_terminating_warning_minutes: 10,
      pod_restart_window_minutes: 10,
      pod_restart_delta: 3,
      warning_event_window_minutes: 30,
      node_not_ready_grace_seconds: 0,
    },
  },
};

function component(state: "ok" | "degraded" | "failed" | "unavailable", message: string) {
  return { state, message, checked_at: "2026-07-26T10:00:00Z", details: {} };
}

const systemStatus: SystemStatus = {
  status: "degraded",
  version: "1.1.0",
  cluster_id: "prod-cluster",
  database: component("ok", "Schema 已是最新版本"),
  kubernetes_api: component("ok", "连接正常"),
  provider: component("ok", "Kubernetes Provider"),
  scheduler: component("ok", "最近心跳正常"),
  metrics_api: component("unavailable", "资源指标未覆盖"),
  notifications: component("degraded", "一个渠道发送失败"),
  last_inspection: component("degraded", "最近巡检部分完成"),
  configuration: component("ok", "配置有效"),
  kubernetes_server_version: "1.36.1",
  kubernetes_version_supported: true,
};

function baseFetch(
  extra: (url: string, init?: RequestInit) => Promise<Response> | Response | null,
) {
  return async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    const handled = await extra(url, init);
    if (handled) return handled;
    if (url.includes("/settings") && (!init?.method || init.method === "GET")) {
      return new Response(JSON.stringify(settings), { status: 200 });
    }
    if (url.includes("/system/status")) {
      return new Response(JSON.stringify(systemStatus), { status: 200 });
    }
    if (url.includes("/inspection-plans") && (!init?.method || init.method === "GET")) {
      return new Response(JSON.stringify({
        items: [{
          id: 1,
          name: "生产集群巡检",
          enabled: false,
          scope: { type: "global", namespaces: [] },
          schedule: { interval: "10m", daily_at: null, timezone: "Asia/Shanghai" },
          include_template_matching: true,
          notification_channel_ids: [1],
          last_run_at: null,
          next_run_at: null,
          last_run_status: null,
          created_at: "2026-07-26T09:00:00Z",
          updated_at: "2026-07-26T09:00:00Z",
        }],
        total: 1,
        page: 1,
        page_size: 100,
      }), { status: 200 });
    }
    if (url.includes("/notification-channels") && (!init?.method || init.method === "GET")) {
      return new Response(JSON.stringify({
        items: [{
          id: 1,
          name: "运维飞书群",
          type: "feishu_custom_bot",
          enabled: true,
          endpoint_masked: "https://open.feishu.cn/***/hook/****",
          signing_secret_configured: true,
          mention_all_on_critical: false,
          timeout_seconds: 5,
          created_at: "2026-07-26T09:00:00Z",
          updated_at: "2026-07-26T09:00:00Z",
        }],
        total: 1,
        page: 1,
        page_size: 100,
      }), { status: 200 });
    }
    throw new Error(`Unexpected request: ${url}`);
  };
}

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("confirm", vi.fn(() => true));
    configureApiSession("csrf-token-at-least-16");
  });

  afterEach(() => {
    cleanup();
    fetchMock.mockReset();
    configureApiSession(null);
    vi.unstubAllGlobals();
  });

  it("creates and enables plans with CSRF while keeping management outside the workbench", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(baseFetch((url, init) => {
      if (url.endsWith("/inspection-plans/1") && init?.method === "PUT") {
        expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-token-at-least-16");
        return new Response(JSON.stringify({
          id: 1,
          name: "生产集群巡检",
          enabled: true,
          scope: { type: "global", namespaces: [] },
          schedule: { interval: "10m", daily_at: null, timezone: "Asia/Shanghai" },
          include_template_matching: true,
          notification_channel_ids: [1],
          last_run_at: null,
          next_run_at: "2026-07-26T10:10:00Z",
          last_run_status: null,
          created_at: "2026-07-26T09:00:00Z",
          updated_at: "2026-07-26T10:00:00Z",
        }), { status: 200 });
      }
      if (url.endsWith("/inspection-plans") && init?.method === "POST") {
        const payload = JSON.parse(String(init.body));
        expect(payload.name).toBe("核心名称空间");
        expect(payload.scope).toEqual({ type: "namespaces", namespaces: ["prod", "payments"] });
        return new Response(JSON.stringify({
          ...payload,
          id: 2,
          last_run_at: null,
          next_run_at: "2026-07-26T10:10:00Z",
          last_run_status: null,
          created_at: "2026-07-26T10:00:00Z",
          updated_at: "2026-07-26T10:00:00Z",
        }), { status: 201 });
      }
      return null;
    }));

    render(<MemoryRouter initialEntries={["/settings?tab=plans"]}><SettingsPage /></MemoryRouter>);

    const existing = await screen.findByText("生产集群巡检");
    const card = existing.closest(".management-card") as HTMLElement;
    await user.click(within(card).getByRole("button", { name: "启用" }));
    expect(await screen.findByText("计划已启用")).toBeInTheDocument();

    await user.type(screen.getByLabelText("计划名称"), "核心名称空间");
    await user.selectOptions(screen.getByLabelText("巡检范围"), "namespaces");
    await user.type(screen.getByLabelText("名称空间（逗号分隔）"), "prod, payments");
    await user.click(screen.getByRole("button", { name: "保存计划" }));
    expect(await screen.findByText("巡检计划已创建")).toBeInTheDocument();
  });

  it("keeps Webhook secrets masked and limits Feishu to one-way group alerts", async () => {
    const user = userEvent.setup();
    let createdPayload: Record<string, unknown> | null = null;
    fetchMock.mockImplementation(baseFetch((url, init) => {
      if (url.endsWith("/notification-channels") && init?.method === "POST") {
        createdPayload = JSON.parse(String(init.body));
        return new Response(JSON.stringify({
          id: 2,
          name: "值班群",
          type: "feishu_custom_bot",
          enabled: true,
          endpoint_masked: "https://open.feishu.cn/***/****",
          signing_secret_configured: true,
          mention_all_on_critical: true,
          timeout_seconds: 5,
          created_at: "2026-07-26T10:00:00Z",
          updated_at: "2026-07-26T10:00:00Z",
        }), { status: 201 });
      }
      if (url.endsWith("/notification-channels/1/test") && init?.method === "POST") {
        return new Response(JSON.stringify({
          message: "测试通知已送达",
          delivery: {
            id: 9,
            channel_id: 1,
            deduplication_key: "test-9",
            event_type: "notification_test",
            status: "succeeded",
            attempt_count: 1,
            delivered_at: "2026-07-26T10:00:00Z",
            created_at: "2026-07-26T10:00:00Z",
            updated_at: "2026-07-26T10:00:00Z",
          },
        }), { status: 200 });
      }
      return null;
    }));

    render(<MemoryRouter initialEntries={["/settings?tab=notifications"]}><SettingsPage /></MemoryRouter>);

    expect(await screen.findByText("https://open.feishu.cn/***/hook/****")).toBeInTheDocument();
    expect(screen.queryByText(/真实-webhook-token/)).not.toBeInTheDocument();
    expect(screen.getByText("仅发送群告警，不接收消息。")).toBeInTheDocument();
    expect(screen.queryByLabelText(/App ID/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/App Secret/i)).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("渠道类型"), "feishu_custom_bot");
    const mentionAll = screen.getByLabelText("仅 critical 时提醒所有人（默认关闭）");
    expect(mentionAll).not.toBeChecked();
    await user.type(screen.getByLabelText("渠道名称"), "值班群");
    await user.type(screen.getByLabelText("Webhook 地址"), "https://open.feishu.cn/open-apis/bot/v2/hook/example");
    await user.type(screen.getByLabelText("签名密钥（可选）"), "secret-value");
    await user.click(mentionAll);
    await user.click(screen.getByRole("button", { name: "保存渠道" }));
    expect(await screen.findByText("通知渠道已创建")).toBeInTheDocument();
    expect(createdPayload).toMatchObject({
      type: "feishu_custom_bot",
      mention_all_on_critical: true,
    });
    expect(createdPayload).not.toHaveProperty("app_id");
    expect(createdPayload).not.toHaveProperty("app_secret");

    const existingCard = screen.getByText("运维飞书群").closest(".management-card") as HTMLElement;
    await user.click(within(existingCard).getByRole("button", { name: "发送测试" }));
    expect(await screen.findByText("测试通知已送达（已送达）")).toBeInTheDocument();
  });

  it("keeps queued runs single-flight, polls to a terminal result, and exposes the run", async () => {
    const user = userEvent.setup();
    let detailResolver: (response: Response) => void = () => {
      throw new Error("巡检执行详情请求尚未开始");
    };
    fetchMock.mockImplementation(baseFetch((url, init) => {
      if (url.endsWith("/inspection-plans/1/run") && init?.method === "POST") {
        return new Response(JSON.stringify({
          id: 44,
          plan_id: 1,
          inspection_record_id: null,
          trigger: "manual",
          status: "queued",
          scope: { type: "cluster", namespaces: [] },
          started_at: null,
          finished_at: null,
          coverage: [],
          issue_ids: [],
          opened_issue_count: 0,
          recovered_issue_count: 0,
          kubernetes_api_calls: 0,
          log_pods_read: 0,
          collected_log_bytes: 0,
          duration_ms: 0,
          error_code: null,
          error_message: null,
        }), { status: 202 });
      }
      if (url.endsWith("/inspection-runs/44")) {
        return new Promise<Response>((resolve) => {
          detailResolver = resolve;
        });
      }
      return null;
    }));

    render(<MemoryRouter initialEntries={["/settings?tab=plans"]}><SettingsPage /></MemoryRouter>);

    const card = (await screen.findByText("生产集群巡检")).closest(".management-card") as HTMLElement;
    await user.click(within(card).getByRole("button", { name: "立即运行" }));
    expect(await within(card).findByRole("button", { name: "等待执行" })).toBeDisabled();
    expect(within(card).getByText("查看本次执行 #44")).toBeInTheDocument();

    detailResolver(new Response(JSON.stringify({
      id: 44,
      plan_id: 1,
      inspection_record_id: 44,
      trigger: "manual",
      status: "succeeded",
      scope: { type: "cluster", namespaces: [] },
      started_at: "2026-07-26T10:00:00Z",
      finished_at: "2026-07-26T10:01:00Z",
      coverage: [{
        check_code: "pod_health",
        name: "Pod 健康",
        status: "passed",
        reason: null,
        checked_objects: 8,
        duration_ms: 50,
        issue_count: 0,
      }],
      issue_ids: [],
      opened_issue_count: 0,
      recovered_issue_count: 0,
      kubernetes_api_calls: 6,
      log_pods_read: 0,
      collected_log_bytes: 0,
      duration_ms: 60_000,
      error_code: null,
      error_message: null,
      check_results: [],
    }), { status: 200 }));

    await waitFor(() => {
      expect(within(card).getByRole("button", { name: "立即运行" })).toBeEnabled();
    });
    expect(within(card).getAllByText("已完成")).toHaveLength(2);
  });

  it("labels an active plan run as running instead of healthy", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(baseFetch((url, init) => {
      if (url.endsWith("/inspection-plans/1/run") && init?.method === "POST") {
        return new Response(JSON.stringify({
          id: 45,
          plan_id: 1,
          inspection_record_id: null,
          trigger: "manual",
          status: "running",
          scope: { type: "cluster", namespaces: [] },
          started_at: "2026-07-26T10:00:00Z",
          finished_at: null,
          coverage: [],
          issue_ids: [],
          opened_issue_count: 0,
          recovered_issue_count: 0,
          kubernetes_api_calls: 1,
          log_pods_read: 0,
          collected_log_bytes: 0,
          duration_ms: 0,
          error_code: null,
          error_message: null,
        }), { status: 202 });
      }
      if (url.endsWith("/inspection-runs/45")) {
        return new Promise<Response>(() => {});
      }
      return null;
    }));

    render(<MemoryRouter initialEntries={["/settings?tab=plans"]}><SettingsPage /></MemoryRouter>);

    const card = (await screen.findByText("生产集群巡检")).closest(".management-card") as HTMLElement;
    await user.click(within(card).getByRole("button", { name: "立即运行" }));

    expect(await within(card).findByRole("button", { name: "执行中…" })).toBeDisabled();
    expect(within(card).getAllByText("运行中")).toHaveLength(2);
    expect(within(card).queryByText("正常")).not.toBeInTheDocument();
  });

  it("does not report pending or failed notification tests as succeeded", async () => {
    const user = userEvent.setup();
    let attempt = 0;
    fetchMock.mockImplementation(baseFetch((url, init) => {
      if (url.endsWith("/notification-channels/1/test") && init?.method === "POST") {
        attempt += 1;
        const status = attempt === 1 ? "pending" : "failed";
        return new Response(JSON.stringify({
          message: attempt === 1 ? "测试通知进入队列" : "目标返回失败",
          delivery: {
            id: 10 + attempt,
            channel_id: 1,
            deduplication_key: `test-${attempt}`,
            event_type: "notification_test",
            status,
            attempt_count: attempt,
            error_code: status === "failed" ? "PROVIDER_REJECTED" : null,
            created_at: "2026-07-26T10:00:00Z",
            updated_at: "2026-07-26T10:00:00Z",
          },
        }), { status: 200 });
      }
      return null;
    }));

    render(<MemoryRouter initialEntries={["/settings?tab=notifications"]}><SettingsPage /></MemoryRouter>);
    const card = (await screen.findByText("运维飞书群")).closest(".management-card") as HTMLElement;

    await user.click(within(card).getByRole("button", { name: "发送测试" }));
    expect(await screen.findByText("测试通知进入队列（已受理，仍在投递或重试）")).toBeInTheDocument();
    expect(screen.queryByText("测试通知已发送")).not.toBeInTheDocument();

    await user.click(within(card).getByRole("button", { name: "发送测试" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("目标返回失败（投递失败）");
    expect(screen.queryByText("测试通知已发送")).not.toBeInTheDocument();
  });

  it("saves required components and thresholds, and shows degraded system components honestly", async () => {
    const user = userEvent.setup();
    let updatedSettings: SettingsResponse | null = null;
    fetchMock.mockImplementation(baseFetch((url, init) => {
      if (url.endsWith("/settings") && init?.method === "PUT") {
        updatedSettings = JSON.parse(String(init.body));
        return new Response(JSON.stringify(updatedSettings), { status: 200 });
      }
      return null;
    }));

    render(<MemoryRouter initialEntries={["/settings?tab=policy"]}><SettingsPage /></MemoryRouter>);

    await user.type(await screen.findByLabelText("显示名称"), "入口控制器");
    await user.type(screen.getByLabelText("名称空间"), "ingress-nginx");
    await user.clear(screen.getByLabelText("Kind"));
    await user.type(screen.getByLabelText("Kind"), "Deployment");
    await user.type(screen.getByLabelText("Label Selector"), "app.kubernetes.io/component=controller");
    await user.click(screen.getByRole("button", { name: "加入策略" }));
    expect(screen.getByText("入口控制器")).toBeInTheDocument();

    const concurrency = screen.getByLabelText("名称空间并发数");
    await user.clear(concurrency);
    await user.type(concurrency, "11");
    await user.click(screen.getByRole("button", { name: "保存巡检策略" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("名称空间并发数必须是 1–10 的整数");

    await user.clear(concurrency);
    await user.type(concurrency, "4");
    const maxLogPods = screen.getByLabelText("单次日志采集 Pod 上限");
    await user.clear(maxLogPods);
    await user.type(maxLogPods, "1001");
    await user.click(screen.getByRole("button", { name: "保存巡检策略" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("单次日志采集 Pod 上限必须是 1–1000 的整数");

    await user.clear(maxLogPods);
    await user.type(maxLogPods, "350");
    const runRetention = screen.getByLabelText("巡检运行记录保留");
    await user.clear(runRetention);
    await user.type(runRetention, "45");
    await user.click(screen.getByRole("button", { name: "保存巡检策略" }));
    expect(await screen.findByText("巡检策略已保存")).toBeInTheDocument();
    expect((updatedSettings as SettingsResponse | null)?.inspection_policy.required_components).toHaveLength(1);
    expect((updatedSettings as SettingsResponse | null)?.inspection_policy.namespace_concurrency).toBe(4);
    expect((updatedSettings as SettingsResponse | null)?.inspection_policy.max_log_pods).toBe(350);
    expect((updatedSettings as SettingsResponse | null)?.inspection_policy.retention.inspection_run_days).toBe(45);

    await user.click(screen.getByRole("button", { name: "系统状态" }));
    expect(await screen.findByText("资源指标未覆盖")).toBeInTheDocument();
    expect(screen.getByText("资源指标未覆盖").closest(".system-component-card")).toHaveTextContent("不可用");
    expect(screen.getByText("一个渠道发送失败").closest(".system-component-card")).toHaveTextContent("降级");
  });
});
