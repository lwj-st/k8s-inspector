import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Issue } from "../api/types";
import { IssueDetailPage } from "./IssueDetailPage";
import { ProblemWorkbenchPage } from "./ProblemWorkbenchPage";

const fetchMock = vi.fn();

function issue(overrides: Partial<Issue> = {}): Issue {
  return {
    id: 1,
    cluster_id: "prod-cluster",
    issue_code: "SERVICE_NO_READY_ENDPOINT",
    fingerprint: "a".repeat(64),
    severity: "critical",
    status: "open",
    scope: "service",
    resource: { kind: "Ingress", namespace: "prod", name: "checkout" },
    summary: "结算入口没有可用后端",
    reason: "Ingress 引用的 Service 当前没有 Ready Endpoint",
    suggestion: "检查 Service selector 和后端 Pod Ready 状态",
    evidence: [{
      code: "INGRESS_SERVICE_CHAIN",
      source: "kubernetes_api",
      summary: "配置链路在 Service 后端处中断",
      facts: { ready_endpoints: 0 },
      related_resources: [
        { kind: "Service", namespace: "prod", name: "checkout" },
        { kind: "EndpointSlice", namespace: "prod", name: "checkout-x1" },
        { kind: "Pod", namespace: "prod", name: "checkout-0" },
      ],
      observed_at: "2026-07-26T10:00:00Z",
      truncated: false,
    }],
    first_seen_at: "2026-07-26T08:00:00Z",
    last_seen_at: "2026-07-26T10:00:00Z",
    recovered_at: null,
    occurrence_count: 3,
    source_check: "ingress_chain",
    correlation_key: "prod/checkout",
    acknowledged_at: null,
    acknowledge_note: null,
    ...overrides,
  };
}

function page(items: Issue[], total = items.length) {
  return { items, total, page: 1, page_size: 20 };
}

describe("ProblemWorkbenchPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    cleanup();
    fetchMock.mockReset();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("keeps server priority order and shows abnormal, skipped, failed and partial states", async () => {
    const requestedUrls: string[] = [];
    const criticalIssue = issue();
    const warningIssue = issue({
      id: 2,
      fingerprint: "b".repeat(64),
      issue_code: "POD_RESTART_SPIKE",
      severity: "warning",
      resource: { kind: "Pod", namespace: "prod", name: "worker-0" },
      summary: "Worker 重启次数突增",
      acknowledged_at: "2026-07-26T10:10:00Z",
    });
    const recoveredIssue = issue({
      id: 3,
      fingerprint: "c".repeat(64),
      status: "recovered",
      severity: "info",
      summary: "结算入口已恢复",
      recovered_at: "2026-07-26T10:05:00Z",
    });
    const ignoredIssue = issue({
      id: 4,
      fingerprint: "d".repeat(64),
      status: "ignored",
      severity: "warning",
      summary: "临时忽略的证书问题",
    });

    fetchMock.mockImplementation(async (input: string | URL | Request) => {
      const url = String(input);
      requestedUrls.push(url);
      if (url.endsWith("/issues/filter-options")) {
        return new Response(JSON.stringify({
          namespaces: [{ value: "prod", label: "prod" }],
          resource_kinds: [
            { value: "Ingress", label: "访问入口（Ingress）" },
            { value: "Pod", label: "容器实例（Pod）" },
          ],
          source_checks: [{ value: "ingress_chain", label: "Ingress 配置链路" }],
        }), { status: 200 });
      }
      if (url.includes("/issues?")) {
        const query = new URL(url, "http://localhost").searchParams;
        if (query.get("page_size") === "1") {
          if (query.get("severity") === "critical") return new Response(JSON.stringify(page([], 1)), { status: 200 });
          if (query.get("severity") === "warning") return new Response(JSON.stringify(page([], 1)), { status: 200 });
          return new Response(JSON.stringify(page([], 2)), { status: 200 });
        }
        if (query.get("status") === "recovered") {
          return new Response(JSON.stringify(page([recoveredIssue], 1)), { status: 200 });
        }
        if (query.get("status") === "ignored") {
          return new Response(JSON.stringify(page([ignoredIssue], 1)), { status: 200 });
        }
        return new Response(JSON.stringify(page([criticalIssue, warningIssue], 2)), { status: 200 });
      }
      if (url.includes("/inspection-runs?")) {
        return new Response(JSON.stringify({
          items: [{
            id: 8,
            plan_id: 1,
            inspection_record_id: 8,
            trigger: "scheduled",
            status: "partial",
            scope: { type: "cluster", namespaces: [] },
            started_at: "2026-07-26T10:00:00Z",
            finished_at: "2026-07-26T10:01:00Z",
            coverage: [
              { check_code: "pod_health", name: "Pod 健康", status: "abnormal", reason: "发现异常", checked_objects: 20, duration_ms: 80, issue_count: 2 },
              { check_code: "metrics", name: "资源指标", status: "skipped", reason: "Metrics API 未安装", checked_objects: 0, duration_ms: 2, issue_count: 0 },
              { check_code: "storage", name: "存储检查", status: "failed", reason: "RBAC Forbidden", checked_objects: 0, duration_ms: 5, issue_count: 0 },
              { check_code: "tls", name: "TLS 检查", status: "passed", reason: null, checked_objects: 3, duration_ms: 12, issue_count: 0 },
            ],
            issue_ids: [1, 2],
            opened_issue_count: 2,
            recovered_issue_count: 1,
            kubernetes_api_calls: 14,
            log_pods_read: 0,
            collected_log_bytes: 0,
            duration_ms: 60_000,
            error_code: null,
            error_message: null,
          }],
          total: 1,
          page: 1,
          page_size: 1,
        }), { status: 200 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    render(<MemoryRouter><ProblemWorkbenchPage /></MemoryRouter>);

    const table = await screen.findByRole("table");
    expect(requestedUrls.some((url) => {
      const query = new URL(url, "http://localhost").searchParams;
      return url.includes("/issues?") && query.get("page_size") === "20" && query.get("status") === "open";
    })).toBe(true);
    const rows = within(table).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("结算入口没有可用后端");
    expect(rows[2]).toHaveTextContent("Worker 重启次数突增");
    expect(within(table).queryByText("结算入口已恢复")).not.toBeInTheDocument();
    expect(within(table).queryByText("临时忽略的证书问题")).not.toBeInTheDocument();
    const summaryCell = within(table).getByText("结算入口没有可用后端").closest(".issue-table-text-cell");
    expect(summaryCell).toHaveClass("issue-table-text-cell-wrap");
    expect(summaryCell).toHaveAttribute("title", "结算入口没有可用后端");
    const resourceCell = within(table).getByText("Ingress/checkout").closest(".issue-table-text-cell");
    expect(resourceCell).not.toHaveClass("issue-table-text-cell-wrap");
    expect(resourceCell).toHaveAttribute("title", "Ingress/checkout");
    expect(within(table).queryByRole("button", { name: /复制/ })).not.toBeInTheDocument();
    expect(within(table).getByText("未确认")).toHaveClass("issue-ack-badge-pending");
    expect(within(table).getByText("已确认")).toHaveClass("issue-ack-badge-confirmed");
    expect(screen.queryByText("最近巡检未完全覆盖")).not.toBeInTheDocument();
    expect(screen.getByText("资源指标").closest(".coverage-row")).toHaveClass("coverage-skipped");
    expect(screen.getByText("存储检查").closest(".coverage-row")).toHaveClass("coverage-failed");
    expect(screen.getAllByText("部分完成").length).toBeGreaterThan(0);
    expect(screen.getByTestId("issue-mobile-list")).toBeInTheDocument();
    expect(screen.queryByText("可信巡检与主动发现")).not.toBeInTheDocument();
    expect(screen.queryByText("汇总手动巡检和定时巡检发现的当前问题；同一问题会自动去重和更新状态。")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "最近一次定时巡检覆盖（全集群）" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "刷新问题工作台" })).toHaveClass("page-refresh-button");
    const requestCountBeforeRefresh = requestedUrls.length;
    await userEvent.click(screen.getByRole("button", { name: "刷新问题工作台" }));
    await waitFor(() => {
      expect(requestedUrls.length).toBeGreaterThan(requestCountBeforeRefresh);
    });

    await userEvent.selectOptions(screen.getByLabelText("名称空间"), "prod");
    expect(requestedUrls.some((url) => url.includes("namespace=prod"))).toBe(true);
    await userEvent.selectOptions(screen.getByLabelText("资源类型"), "Pod");
    expect(requestedUrls.some((url) => url.includes("resource_kind=Pod"))).toBe(true);
    await userEvent.selectOptions(screen.getByLabelText("巡检项"), "ingress_chain");
    expect(requestedUrls.some((url) => url.includes("source_check=ingress_chain"))).toBe(true);

    await userEvent.selectOptions(screen.getByLabelText("排序"), "duration");
    expect(await screen.findByDisplayValue("持续最久")).toBeInTheDocument();
    expect(requestedUrls.some((url) => url.includes("sort=duration"))).toBe(true);

    await userEvent.selectOptions(screen.getByLabelText("状态"), "recovered");
    expect(await screen.findAllByText("结算入口已恢复")).toHaveLength(2);
    expect(screen.getAllByText("已恢复").length).toBeGreaterThan(0);

    await userEvent.selectOptions(screen.getByLabelText("状态"), "ignored");
    expect(await screen.findByRole("heading", { name: "已忽略问题" })).toBeInTheDocument();
    expect(await screen.findAllByText("临时忽略的证书问题")).toHaveLength(2);
    expect(requestedUrls.some((url) => url.includes("status=ignored"))).toBe(true);
  });

  it("reloads workbench data when a completed status inspection marks it stale", async () => {
    const requestedUrls: string[] = [];
    let refreshMarker: string | null = null;
    vi.stubGlobal("localStorage", {
      getItem: vi.fn(() => refreshMarker),
      setItem: vi.fn((_: string, value: string) => {
        refreshMarker = value;
      }),
    });

    fetchMock.mockImplementation(async (input: string | URL | Request) => {
      const url = String(input);
      requestedUrls.push(url);
      if (url.endsWith("/issues/filter-options")) {
        return new Response(JSON.stringify({
          namespaces: [],
          resource_kinds: [],
          source_checks: [],
        }), { status: 200 });
      }
      if (url.includes("/issues?")) {
        return new Response(JSON.stringify(page([], 0)), { status: 200 });
      }
      if (url.includes("/inspection-runs?")) {
        return new Response(JSON.stringify({
          items: [],
          total: 0,
          page: 1,
          page_size: 1,
        }), { status: 200 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    render(<MemoryRouter><ProblemWorkbenchPage /></MemoryRouter>);

    expect(await screen.findByText("当前没有开放问题")).toBeInTheDocument();
    const requestCountBeforeStatusInspection = requestedUrls.length;

    refreshMarker = "status-inspection-finished";
    window.dispatchEvent(new Event("focus"));

    await waitFor(() => {
      expect(requestedUrls.length).toBeGreaterThan(requestCountBeforeStatusInspection);
    });
  });

  it("auto refreshes at the configured interval without clearing batch input", async () => {
    const requestedUrls: string[] = [];
    const localStorageData = new Map<string, string>();
    let intervalHandler: TimerHandler | undefined;
    vi.spyOn(window, "setInterval").mockImplementation((handler: TimerHandler) => {
      intervalHandler = handler;
      return 1;
    });
    vi.spyOn(window, "clearInterval").mockImplementation(() => undefined);
    vi.stubGlobal("localStorage", {
      getItem: vi.fn((key: string) => localStorageData.get(key) ?? null),
      setItem: vi.fn((key: string, value: string) => {
        localStorageData.set(key, value);
      }),
    });

    fetchMock.mockImplementation(async (input: string | URL | Request) => {
      const url = String(input);
      requestedUrls.push(url);
      if (url.endsWith("/issues/filter-options")) {
        return new Response(JSON.stringify({ namespaces: [], resource_kinds: [], source_checks: [] }), { status: 200 });
      }
      if (url.includes("/issues?")) {
        return new Response(JSON.stringify(page([issue()], 1)), { status: 200 });
      }
      if (url.includes("/inspection-runs?")) {
        return new Response(JSON.stringify({
          items: [],
          total: 0,
          page: 1,
          page_size: 1,
        }), { status: 200 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    render(<MemoryRouter><ProblemWorkbenchPage /></MemoryRouter>);

    expect((await screen.findAllByText("结算入口没有可用后端")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("checkbox", { name: "自动刷新" }));
    fireEvent.change(screen.getByLabelText("自动刷新间隔秒数"), { target: { value: "5" } });
    fireEvent.click(screen.getByLabelText("选择问题 1"));
    fireEvent.change(screen.getByPlaceholderText("填写批量确认备注"), { target: { value: "值班同学处理中" } });
    const requestCountBeforeTimer = requestedUrls.length;

    if (typeof intervalHandler === "function") {
      intervalHandler();
    }

    await waitFor(() => {
      expect(requestedUrls.length).toBeGreaterThan(requestCountBeforeTimer);
    });
    expect(screen.getByPlaceholderText("填写批量确认备注")).toHaveValue("值班同学处理中");
    expect(localStorageData.get("k8s-inspector:problem-workbench-auto-refresh")).toBe("true");
    expect(localStorageData.get("k8s-inspector:problem-workbench-auto-refresh-interval")).toBe("5");
  });

  it("runs batch acknowledge, ignore and unignore actions for selected issues", async () => {
    const user = userEvent.setup();
    const requestedBodies: Array<{ url: string; body: unknown }> = [];
    const first = issue({ id: 1, fingerprint: "a".repeat(64), summary: "结算入口没有可用后端" });
    const second = issue({
      id: 2,
      fingerprint: "b".repeat(64),
      issue_code: "POD_RESTART_SPIKE",
      resource: { kind: "Pod", namespace: "prod", name: "worker-0" },
      summary: "Worker 重启次数突增",
    });
    const ignoredFirst = issue({ ...first, status: "ignored" });
    const ignoredSecond = issue({ ...second, status: "ignored" });

    fetchMock.mockImplementation(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (init?.body) {
        requestedBodies.push({ url, body: JSON.parse(String(init.body)) });
      }
      if (url.endsWith("/issues/filter-options")) {
        return new Response(JSON.stringify({ namespaces: [], resource_kinds: [], source_checks: [] }), { status: 200 });
      }
      if (url.includes("/inspection-runs?")) {
        return new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 1 }), { status: 200 });
      }
      if (url.includes("/issues/batch/acknowledge")) {
        return new Response(JSON.stringify({
          succeeded_count: 2,
          failed_count: 0,
          results: [
            { issue_id: 1, succeeded: true, issue: { ...first, acknowledged_at: "2026-07-26T10:00:00Z", acknowledge_note: "统一处理" } },
            { issue_id: 2, succeeded: true, issue: { ...second, acknowledged_at: "2026-07-26T10:00:00Z", acknowledge_note: "统一处理" } },
          ],
        }), { status: 200 });
      }
      if (url.includes("/issues/batch/ignore")) {
        return new Response(JSON.stringify({
          succeeded_count: 2,
          failed_count: 0,
          results: [
            { issue_id: 1, succeeded: true, issue: ignoredFirst },
            { issue_id: 2, succeeded: true, issue: ignoredSecond },
          ],
        }), { status: 200 });
      }
      if (url.includes("/issues/batch/unignore")) {
        return new Response(JSON.stringify({
          succeeded_count: 2,
          failed_count: 0,
          results: [
            { issue_id: 1, succeeded: true, issue: first },
            { issue_id: 2, succeeded: true, issue: second },
          ],
        }), { status: 200 });
      }
      if (url.includes("/issues?")) {
        const query = new URL(url, "http://localhost").searchParams;
        if (query.get("page_size") === "1") {
          return new Response(JSON.stringify(page([], query.get("severity") ? 1 : 2)), { status: 200 });
        }
        if (query.get("status") === "ignored") {
          return new Response(JSON.stringify(page([ignoredFirst, ignoredSecond], 2)), { status: 200 });
        }
        return new Response(JSON.stringify(page([first, second], 2)), { status: 200 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    render(<MemoryRouter><ProblemWorkbenchPage /></MemoryRouter>);

    expect(await screen.findByRole("table")).toBeInTheDocument();
    await user.click(screen.getByLabelText("选择问题 1"));
    await user.click(screen.getByLabelText("选择问题 2"));
    await user.type(screen.getByLabelText("统一确认备注"), "统一处理");
    await user.click(screen.getByRole("button", { name: "批量确认" }));

    expect(await screen.findByText("批量操作完成：成功 2 项。")).toBeInTheDocument();
    expect(requestedBodies.some((item) => (
      item.url.includes("/issues/batch/acknowledge")
      && JSON.stringify(item.body) === JSON.stringify({ issue_ids: [1, 2], note: "统一处理" })
    ))).toBe(true);

    await user.click(screen.getByLabelText("选择问题 1"));
    await user.click(screen.getByLabelText("选择问题 2"));
    await user.click(screen.getByRole("button", { name: "批量忽略" }));
    expect(screen.getByText("确认忽略选中的 2 个问题？忽略后默认不再出现在开放问题列表。")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认忽略" }));
    expect(requestedBodies.some((item) => (
      item.url.includes("/issues/batch/ignore")
      && JSON.stringify(item.body) === JSON.stringify({ issue_ids: [1, 2] })
    ))).toBe(true);

    await user.selectOptions(screen.getByLabelText("状态"), "ignored");
    expect(await screen.findByRole("heading", { name: "已忽略问题" })).toBeInTheDocument();
    await user.click(screen.getByLabelText("选择当前页全部问题"));
    await user.click(screen.getByRole("button", { name: "批量恢复显示" }));
    expect(screen.getByText("确认恢复显示选中的 2 个问题？恢复后会重新出现在开放问题列表。")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认恢复" }));
    expect(requestedBodies.some((item) => (
      item.url.includes("/issues/batch/unignore")
      && JSON.stringify(item.body) === JSON.stringify({ issue_ids: [1, 2] })
    ))).toBe(true);
  });

  it("renders the evidence chain and paged timeline, and keeps the note after a 403", async () => {
    const user = userEvent.setup();
    const targetIssue = issue({
      evidence: [
        ...issue().evidence,
        {
          code: "LOG_MATCH",
          source: "log_match",
          summary: "日志命中 error",
          facts: { context: "error token=abc123 password=secret-value" },
          related_resources: [{ kind: "Pod", namespace: "prod", name: "checkout-0" }],
          observed_at: "2026-07-26T10:01:00Z",
          truncated: false,
        },
      ],
    });
    const writeText = vi.fn().mockResolvedValue(undefined);
    const createObjectUrl = vi.fn(() => "blob:issue-md");
    const revokeObjectUrl = vi.fn();
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    let noteCreated = false;
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectUrl });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectUrl });
    fetchMock.mockImplementation(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/issues/1")) {
        return new Response(JSON.stringify(targetIssue), { status: 200 });
      }
      if (url.includes("/issues/1/events")) {
        const currentPage = new URL(url, "http://localhost").searchParams.get("page");
        if (noteCreated && currentPage === "1") {
          return new Response(JSON.stringify({
            items: [{
              id: 3,
              issue_id: 1,
              run_id: null,
              event_type: "note_added",
              trigger: "manual",
              previous_status: "open",
              new_status: "open",
              previous_severity: "critical",
              new_severity: "critical",
              occurred_at: "2026-07-26T10:05:00Z",
              summary: "已联系二线处理",
              actor: "admin",
              evidence_codes: [],
            }],
            total: 22,
            page: 1,
            page_size: 20,
          }), { status: 200 });
        }
        return new Response(JSON.stringify({
          items: [{
            id: currentPage === "2" ? 1 : 2,
            issue_id: 1,
            run_id: 8,
            event_type: currentPage === "2" ? "opened" : "observed",
            trigger: "scheduled",
            previous_status: null,
            new_status: "open",
            previous_severity: null,
            new_severity: "critical",
            occurred_at: currentPage === "2" ? "2026-07-26T08:00:00Z" : "2026-07-26T10:00:00Z",
            summary: currentPage === "2" ? "首次发现问题" : "问题仍在持续",
            evidence_codes: ["INGRESS_SERVICE_CHAIN"],
          }],
          total: 21,
          page: Number(currentPage),
          page_size: 20,
        }), { status: 200 });
      }
      if (url.endsWith("/issues/1/notes") && init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toEqual({ content: "已联系二线处理" });
        noteCreated = true;
        return new Response(JSON.stringify({
          id: 3,
          issue_id: 1,
          run_id: null,
          event_type: "note_added",
          trigger: "manual",
          previous_status: "open",
          new_status: "open",
          previous_severity: "critical",
          new_severity: "critical",
          occurred_at: "2026-07-26T10:05:00Z",
          summary: "已联系二线处理",
          actor: "admin",
          evidence_codes: [],
        }), { status: 201 });
      }
      if (url.endsWith("/issues/1/acknowledge") && init?.method === "POST") {
        return new Response(JSON.stringify({
          code: "CSRF_VALIDATION_FAILED",
          message: "请求安全校验失败，请刷新页面后重试",
          request_id: "request-403",
          details: {},
        }), { status: 403 });
      }
      if (url.endsWith("/issues/1/ignore") && init?.method === "POST") {
        return new Response(JSON.stringify({
          ...targetIssue,
          status: "ignored",
        }), { status: 200 });
      }
      if (url.endsWith("/issues/1/unignore") && init?.method === "POST") {
        return new Response(JSON.stringify(targetIssue), { status: 200 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    render(
      <MemoryRouter initialEntries={["/issues/1"]}>
        <Routes>
          <Route path="/issues/:id" element={<IssueDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "结算入口没有可用后端" })).toBeInTheDocument();
    const chain = screen.getByRole("list", { name: "访问配置链路" });
    expect(within(chain).getByText("Ingress")).toBeInTheDocument();
    expect(screen.getByText("配置链路在 Service 后端处中断")).toBeInTheDocument();
    expect(screen.getByText("日志命中 error")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("证据类型"), "log_match");
    expect(screen.queryByText("配置链路在 Service 后端处中断")).not.toBeInTheDocument();
    expect(screen.getByText("日志命中 error")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("证据类型"), "kubernetes_api");
    expect(screen.getByText("配置链路在 Service 后端处中断")).toBeInTheDocument();
    expect(screen.queryByText("日志命中 error")).not.toBeInTheDocument();
    expect(screen.getAllByText("问题仍在持续")).toHaveLength(2);
    expect(screen.getByRole("heading", { name: "查看命令" })).toBeInTheDocument();
    expect(screen.getByText("kubectl describe service -n 'prod' 'checkout'")).toBeInTheDocument();
    expect(screen.getByText("kubectl get endpoints -n 'prod' 'checkout' -o wide")).toBeInTheDocument();
    expect(screen.getByText("kubectl get endpointslices.discovery.k8s.io -n 'prod' -l kubernetes.io/service-name='checkout' -o wide")).toBeInTheDocument();
    expect(screen.queryByText("kubectl get endpointslices.discovery.k8s.io -n 'prod' 'checkout-x1' -o yaml")).not.toBeInTheDocument();
    expect(screen.queryByText("kubectl logs -n 'prod' 'checkout-0' --all-containers --tail=200")).not.toBeInTheDocument();

    await user.type(screen.getByLabelText("新增记录"), "已联系二线处理");
    await user.click(screen.getByRole("button", { name: "添加记录" }));
    expect(await screen.findByText("处理记录已添加。")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "处理记录" })).toBeInTheDocument();
    expect(screen.getByText("已联系二线处理")).toBeInTheDocument();
    expect(screen.getByText("admin")).toBeInTheDocument();

    const copyButtons = screen.getAllByRole("button", { name: "复制命令" });
    await user.click(copyButtons[0]);
    expect(writeText).toHaveBeenCalledWith("kubectl describe service -n 'prod' 'checkout'");
    expect(await screen.findByRole("button", { name: "已复制" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "复制 Markdown" }));
    const markdown = String(writeText.mock.calls.at(-1)?.[0] ?? "");
    expect(markdown).toContain("# 结算入口没有可用后端");
    expect(markdown).toContain("日志命中 error");
    expect(markdown).toContain("token=***");
    expect(markdown).toContain("password=***");
    expect(markdown).not.toContain("abc123");
    expect(markdown).not.toContain("secret-value");
    expect(await screen.findByText("Markdown 已复制。")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "下载 Markdown" }));
    expect(createObjectUrl).toHaveBeenCalled();
    expect(anchorClick).toHaveBeenCalled();
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:issue-md");

    await user.click(screen.getByRole("button", { name: "加载更早记录" }));
    expect(await screen.findByText("首次发现问题")).toBeInTheDocument();

    const note = screen.getByLabelText("确认备注");
    await user.type(note, "值班同学处理中");
    await user.click(screen.getByRole("button", { name: "确认已知晓" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("请求安全校验失败");
    expect(note).toHaveValue("值班同学处理中");
    expect(screen.getByText(/确认只表示你已知晓/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "忽略此问题" }));
    expect(screen.getByText("忽略后，此问题默认不再出现在开放问题列表，可通过“已忽略”筛选查看。确认忽略吗？")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认忽略" }));
    expect(await screen.findByText("此问题已忽略")).toBeInTheDocument();
    expect(screen.getByText("已忽略")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "恢复显示" }));
    expect(screen.getByText("取消忽略后，此问题会重新出现在开放问题列表。确认恢复显示吗？")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认恢复" }));
    expect(await screen.findByRole("button", { name: "忽略此问题" })).toBeInTheDocument();
  });

  it("hides command section when issue code has no deterministic resource command", async () => {
    const unknownIssue = issue({
      issue_code: "CUSTOM_PATTERN_MATCHED",
      resource: { kind: "CustomThing", namespace: "prod", name: "checkout-rule" },
      evidence: [],
    });

    fetchMock.mockImplementation(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/issues/1")) {
        return new Response(JSON.stringify(unknownIssue), { status: 200 });
      }
      if (url.includes("/issues/1/events")) {
        return new Response(JSON.stringify({
          items: [],
          total: 0,
          page: 1,
          page_size: 20,
        }), { status: 200 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    render(
      <MemoryRouter initialEntries={["/issues/1"]}>
        <Routes>
          <Route path="/issues/:id" element={<IssueDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "结算入口没有可用后端" })).toBeInTheDocument();
    expect(screen.getByText("0/0 条")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "查看命令" })).not.toBeInTheDocument();
    expect(screen.queryByText(/kubectl describe customthing/)).not.toBeInTheDocument();
  });
});
