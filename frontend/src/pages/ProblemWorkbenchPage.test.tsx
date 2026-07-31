import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
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
    });
    const recoveredIssue = issue({
      id: 3,
      fingerprint: "c".repeat(64),
      status: "recovered",
      severity: "info",
      summary: "结算入口已恢复",
      recovered_at: "2026-07-26T10:05:00Z",
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
    const rows = within(table).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("结算入口没有可用后端");
    expect(rows[2]).toHaveTextContent("Worker 重启次数突增");
    expect(screen.getByText("最近巡检未完全覆盖")).toBeInTheDocument();
    expect(screen.getByText("资源指标").closest(".coverage-row")).toHaveClass("coverage-skipped");
    expect(screen.getByText("存储检查").closest(".coverage-row")).toHaveClass("coverage-failed");
    expect(screen.getAllByText("部分完成").length).toBeGreaterThan(0);
    expect(screen.getByTestId("issue-mobile-list")).toBeInTheDocument();
    expect(screen.getByText("汇总手动巡检和定时巡检发现的当前问题；同一问题会自动去重和更新状态。")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "最近一次定时巡检覆盖（全集群）" })).toBeInTheDocument();
    const requestCountBeforeRefresh = requestedUrls.length;
    await userEvent.click(screen.getByRole("button", { name: "刷新" }));
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

  it("renders the evidence chain and paged timeline, and keeps the note after a 403", async () => {
    const user = userEvent.setup();
    const targetIssue = issue();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    fetchMock.mockImplementation(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/issues/1")) {
        return new Response(JSON.stringify(targetIssue), { status: 200 });
      }
      if (url.includes("/issues/1/events")) {
        const currentPage = new URL(url, "http://localhost").searchParams.get("page");
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
      if (url.endsWith("/issues/1/acknowledge") && init?.method === "POST") {
        return new Response(JSON.stringify({
          code: "CSRF_VALIDATION_FAILED",
          message: "请求安全校验失败，请刷新页面后重试",
          request_id: "request-403",
          details: {},
        }), { status: 403 });
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
    expect(screen.getAllByText("问题仍在持续")).toHaveLength(2);
    expect(screen.getByRole("heading", { name: "查看命令" })).toBeInTheDocument();
    expect(screen.getByText("kubectl get ingress -n 'prod' 'checkout' -o yaml")).toBeInTheDocument();
    expect(screen.getByText("kubectl get endpointslices.discovery.k8s.io -n 'prod' 'checkout-x1' -o yaml")).toBeInTheDocument();
    expect(screen.getByText("kubectl get endpointslices.discovery.k8s.io -n 'prod' -l kubernetes.io/service-name='checkout' -o wide")).toBeInTheDocument();
    expect(screen.getByText("kubectl logs -n 'prod' 'checkout-0' --all-containers --tail=200")).toBeInTheDocument();

    const copyButtons = screen.getAllByRole("button", { name: "复制命令" });
    await user.click(copyButtons[0]);
    expect(writeText).toHaveBeenCalledWith("kubectl get ingress -n 'prod' 'checkout' -o yaml");
    expect(await screen.findByRole("button", { name: "已复制" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "加载更早记录" }));
    expect(await screen.findByText("首次发现问题")).toBeInTheDocument();

    const note = screen.getByLabelText("确认备注");
    await user.type(note, "值班同学处理中");
    await user.click(screen.getByRole("button", { name: "确认已知晓" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("请求安全校验失败");
    expect(note).toHaveValue("值班同学处理中");
    expect(screen.getByText(/确认只表示你已知晓/)).toBeInTheDocument();
  });
});
