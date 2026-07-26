import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { runClusterInspection } from "../api/client";
import { PodInspectionPage } from "./PodInspectionPage";

const fetchMock = vi.fn();
let discoveredPodCount: number | null = 3;
let configuredMaxLogPods = 120;

describe("PodInspectionPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    discoveredPodCount = 3;
    configuredMaxLogPods = 120;
    const savedTargets = [
      {
        id: 1,
        name: "demo-api 固定排查",
        target_type: "pod",
        namespace: "demo",
        pod_name: "demo-api-1",
        label_selector: null,
        resource_scope: ["pods"],
        created_at: "2026-07-19T10:00:00Z",
        updated_at: "2026-07-19T10:00:00Z",
      },
      {
        id: 2,
        name: "demo API 标签范围",
        target_type: "pod",
        namespace: "demo",
        pod_name: "",
        label_selector: "app=demo-api",
        resource_scope: ["pods"],
        created_at: "2026-07-19T10:00:00Z",
        updated_at: "2026-07-19T10:00:00Z",
      },
    ];

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/settings")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({ inspection_policy: { max_log_pods: configuredMaxLogPods } }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/discovery/namespaces")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              executed_at: "2026-07-19T10:00:00Z",
              namespaces: [
                {
                  name: "demo",
                  status: "warning",
                  pod_count: discoveredPodCount,
                  abnormal_pod_count: 1,
                  last_inspected_at: null,
                  labels: {},
                  abnormal_categories: ["pod_status"],
                },
                {
                  name: "prod",
                  status: "healthy",
                  pod_count: 4,
                  abnormal_pod_count: 0,
                  last_inspected_at: null,
                  labels: {},
                  abnormal_categories: [],
                },
              ],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/inspection-targets") && (!init || init.method === undefined)) {
        return Promise.resolve(
          new Response(JSON.stringify(savedTargets), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/discovery/namespaces/demo/labels")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              namespace: "demo",
              executed_at: "2026-07-19T10:00:00Z",
              labels: [{ key: "app", values: ["demo-api"], selector: "app=demo-api", pod_count: 1 }],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/discovery/namespaces/demo/pods")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              namespace: "demo",
              label_selector: null,
              executed_at: "2026-07-19T10:00:00Z",
              pod_count: 2,
              pods: [
                { name: "demo-api-1", labels: { app: "demo-api" } },
                { name: "demo-worker-1", labels: { app: "demo-worker" } },
              ],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/discovery/namespaces/prod/pods")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              namespace: "prod",
              label_selector: null,
              executed_at: "2026-07-19T10:00:00Z",
              pod_count: 1,
              pods: [{ name: "prod-api-1", labels: { app: "prod-api" } }],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/inspection-targets") && init?.method === "POST") {
        const payload = JSON.parse(String(init.body));
        const created = {
          id: savedTargets.length + 1,
          created_at: "2026-07-19T11:00:00Z",
          updated_at: "2026-07-19T11:00:00Z",
          ...payload,
        };
        savedTargets.unshift(created);
        return Promise.resolve(
          new Response(JSON.stringify(created), { status: 201, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.match(/\/inspection-targets\/\d+$/) && init?.method === "PUT") {
        const payload = JSON.parse(String(init.body));
        const targetId = Number(url.split("/").pop());
        const index = savedTargets.findIndex((item) => item.id === targetId);
        savedTargets[index] = { ...savedTargets[index], ...payload, updated_at: "2026-07-19T12:00:00Z" };
        return Promise.resolve(
          new Response(JSON.stringify(savedTargets[index]), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.match(/\/inspection-targets\/\d+$/) && init?.method === "DELETE") {
        const targetId = Number(url.split("/").pop());
        const index = savedTargets.findIndex((item) => item.id === targetId);
        savedTargets.splice(index, 1);
        return Promise.resolve(new Response(null, { status: 204 }));
      }

      if (url.endsWith("/inspection-targets/export") && (!init || init.method === undefined)) {
        return Promise.resolve(
          new Response(JSON.stringify(savedTargets), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/inspection-targets/import") && init?.method === "POST") {
        const payload = JSON.parse(String(init.body));
        const created = payload.map((item: Record<string, unknown>, index: number) => ({
          id: savedTargets.length + index + 1,
          created_at: "2026-07-19T13:00:00Z",
          updated_at: "2026-07-19T13:00:00Z",
          ...item,
        }));
        savedTargets.unshift(...created.reverse());
        return Promise.resolve(
          new Response(JSON.stringify(created), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/inspections/namespace/run") && init?.method === "POST") {
        const payload = JSON.parse(String(init.body));
        return Promise.resolve(
          new Response(
            JSON.stringify({
              inspection_target: {
                type: "namespace",
                namespace: payload.namespace,
                label_selector: payload.label_selector,
                saved_target_id: null,
                resource_scope: ["pods"],
              },
              namespace: payload.namespace,
              health_status: "warning",
              executed_at: "2026-07-19T10:30:00Z",
              evidence_bundles: [],
              pods: [
                {
                  name: "demo-api-1",
                  status: "CrashLoopBackOff",
                  restarts: 6,
                  node_name: "node-a",
                  containers: [],
                  events: ["BackOff: restart container"],
                  describe_summary: "startup failed",
                  log_summary: "database connection refused",
                  previous_log_summary: null,
                  log_hits: [
                    {
                      keyword: "connection refused",
                      category: "database",
                      severity: "error",
                      source: "log_summary",
                      matched_text: "database connection refused",
                      container_name: "demo-api",
                      whitelisted: false,
                      whitelist_rule_id: null,
                    },
                    {
                      keyword: "ERROR",
                      category: "generic",
                      severity: "error",
                      source: "current_log",
                      matched_text: "{\"error\":\"invalid_client\",\"error_description\":\"Client authentication failed\"}",
                      context_text: "{\"error\":\"invalid_client\",\"error_description\":\"Client authentication failed\"}",
                      container_name: "demo-api",
                      whitelisted: true,
                      whitelist_rule_id: 9,
                    },
                  ],
                  resource_usage: { cpu: "220m", memory: "180Mi" },
                  related_resources: [],
                },
                {
                  name: "demo-worker-1",
                  status: "Succeeded",
                  restarts: 0,
                  node_name: "node-b",
                  containers: [{ name: "worker", restart_count: 0, state: "terminated", reason: "Completed" }],
                  events: [],
                  describe_summary: "running",
                  log_summary: "plain worker output without keyword hit",
                  previous_log_summary: null,
                  log_hits: [],
                  resource_usage: { cpu: "40m", memory: "60Mi" },
                  related_resources: [],
                },
              ],
              services: [],
              ingresses: [],
              tls_secrets: [],
              daemonsets: [],
              issues: [],
              coverage: [{
                check_code: "pod_runtime",
                name: "Pod 运行状态",
                status: "failed",
                reason: "部分 Pod 读取超时",
                checked_objects: 1,
                duration_ms: 200,
                issue_count: 0,
              }],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/inspections/pod/run") && init?.method === "POST") {
        const payload = JSON.parse(String(init.body));
        return Promise.resolve(
          new Response(
            JSON.stringify({
              inspection_target: { type: "pod", namespace: payload.namespace, pod_name: payload.pod_name, resource_scope: ["pods"] },
              namespace: payload.namespace,
              health_status: "warning",
              executed_at: "2026-07-19T10:00:00Z",
              pod: {
                name: payload.pod_name,
                labels: { app: "demo-api" },
                status: "CrashLoopBackOff",
                restarts: 6,
                containers: [
                  {
                    name: "demo-api",
                    restart_count: 6,
                    state: "waiting",
                    reason: "CrashLoopBackOff",
                  },
                ],
                events: ["BackOff: restart container"],
                describe_summary: "startup failed",
                log_summary: "database connection refused",
                previous_log_summary: "previous database connection refused",
                log_hits: [
                  {
                    keyword: "ERROR",
                    category: "database",
                    severity: "error",
                    source: "log_summary",
                    matched_text: "level=error msg=database connection refused",
                    container_name: "demo-api",
                    whitelisted: false,
                    whitelist_rule_id: null,
                  },
                ],
                resource_usage: { cpu: "220m", memory: "180Mi" },
                related_resources: [],
              },
              evidence_bundle: null,
              issues: [],
              coverage: [{
                check_code: "metrics",
                name: "资源指标",
                status: "skipped",
                reason: "Metrics API 不可用",
                checked_objects: 0,
                duration_ms: 5,
                issue_count: 0,
              }],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/whitelists/ignore") && init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toMatchObject({
          namespace: "demo",
          label_selector: "app=demo-api",
          pod_name_pattern: null,
          container_name: null,
          keyword: "level=error msg=database connection refused",
          note: "从 Pod 巡检结果忽略",
        });
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 1,
              namespace: "demo",
              label_selector: null,
              pod_name_pattern: null,
              container_name: "demo-api",
              keyword: "level=error msg=database connection refused",
              enabled: true,
              note: "从 Pod 巡检结果忽略",
            }),
            { status: 201, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      throw new Error(`Unexpected request: ${url}`);
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  it("keeps import and export textarea hidden until modal opens", async () => {
    render(<PodInspectionPage />);

    await screen.findByRole("option", { name: "demo" });
    expect(screen.queryByLabelText("导出内容")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("导入内容")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "导出" }));
    const exportDialog = await screen.findByRole("dialog", { name: "导出巡检点" });
    expect(exportDialog).toBeInTheDocument();
    expect(screen.getByLabelText("导出内容")).toBeInTheDocument();
  });

  it("runs the cluster status inspection with logs explicitly disabled", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          health_status: "unknown",
          executed_at: "2026-07-26T10:00:00Z",
          results: [],
          issues: [],
          coverage: [],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await runClusterInspection();

    expect(String(fetchMock.mock.calls[0]?.[0])).toMatch(
      /\/inspections\/cluster\/run\?include_logs=false$/,
    );
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
  });

  it("runs all pod mode without requiring pod name", async () => {
    render(<PodInspectionPage />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("范围类型"), { target: { value: "all" } });
    fireEvent.click(screen.getByRole("button", { name: "日志巡检" }));

    expect(await screen.findByText("Pod 列表")).toBeInTheDocument();
    expect(screen.getByText("Pod 运行状态").closest(".coverage-row")).toHaveClass("coverage-failed");
    expect(screen.getByText("本次有检查跳过或失败，不能据此确认全部正常。")).toBeInTheDocument();
    expect(screen.queryByText("最近一次巡检摘要")).not.toBeInTheDocument();
    expect(screen.getByText("命中关键字：connection refused")).toBeInTheDocument();

    const request = fetchMock.mock.calls.find(
      ([input, init]) => String(input).endsWith("/inspections/namespace/run") && init?.method === "POST",
    );
    expect(request).toBeDefined();
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({
      namespace: "demo",
      label_selector: null,
      include_logs: true,
    });
  });

  it("blocks a discovered range over the configured pod limit without sending an inspection request", async () => {
    configuredMaxLogPods = 120;
    discoveredPodCount = 121;
    render(<PodInspectionPage initialScopeMode="all" />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.click(screen.getByRole("button", { name: "日志巡检" }));

    const dialog = await screen.findByRole("dialog", { name: "无法执行大范围日志巡检" });
    expect(within(dialog).getByText("当前范围发现 121 个 Pod，超过当前日志采集上限 120 个，本次巡检已阻断。")).toBeInTheDocument();
    expect(within(dialog).getByText("请使用 Label Selector 缩小到 120 个及以下 Pod 后重试。")).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "仍要继续" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(
      ([input, init]) => String(input).endsWith("/inspections/namespace/run") && init?.method === "POST",
    )).toHaveLength(0);

    fireEvent.click(within(dialog).getByRole("button", { name: "返回缩小范围" }));
    expect(screen.queryByRole("dialog", { name: "无法执行大范围日志巡检" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(
      ([input, init]) => String(input).endsWith("/inspections/namespace/run") && init?.method === "POST",
    )).toHaveLength(0);
  });

  it("blocks a range with unknown pod count without sending an inspection request", async () => {
    discoveredPodCount = null;
    render(<PodInspectionPage initialScopeMode="all" />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.click(screen.getByRole("button", { name: "日志巡检" }));

    const dialog = await screen.findByRole("dialog", { name: "无法执行大范围日志巡检" });
    expect(within(dialog).getByText("当前无法确认该范围的 Pod 数量，为避免读取过多日志，本次巡检已阻断。")).toBeInTheDocument();
    expect(within(dialog).getByText("请先刷新发现数据、选择可确认 Pod 数量的范围，或使用 Label Selector 缩小范围后重试。")).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "仍要继续" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(
      ([input, init]) => String(input).endsWith("/inspections/namespace/run") && init?.method === "POST",
    )).toHaveLength(0);

    fireEvent.click(within(dialog).getByRole("button", { name: "返回缩小范围" }));
    expect(fetchMock.mock.calls.filter(
      ([input, init]) => String(input).endsWith("/inspections/namespace/run") && init?.method === "POST",
    )).toHaveLength(0);
  });

  it("runs label selector mode through namespace inspection", async () => {
    render(<PodInspectionPage />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("范围类型"), { target: { value: "label" } });
    await screen.findByRole("option", { name: "app=demo-api（1 个 Pod）" });
    fireEvent.change(screen.getByLabelText("Label Selector"), { target: { value: "app=demo-api" } });
    expect(screen.getByLabelText("手动 Label Selector")).toHaveValue("app=demo-api");
    fireEvent.click(screen.getByRole("button", { name: "日志巡检" }));

    expect(await screen.findByText("Pod 列表")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /demo-api-1/ })).toBeInTheDocument();

    const request = fetchMock.mock.calls
      .filter(([input, init]) => String(input).endsWith("/inspections/namespace/run") && init?.method === "POST")
      .at(-1);
    expect(request).toBeDefined();
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({
      namespace: "demo",
      label_selector: "app=demo-api",
      include_logs: true,
    });
  });

  it("loads a single Pod dropdown through lightweight discovery without running namespace inspection", async () => {
    render(<PodInspectionPage />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("范围类型"), { target: { value: "single" } });

    expect(await screen.findByRole("option", { name: "demo-api-1" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(
      ([input, init]) => String(input).endsWith("/discovery/namespaces/demo/pods") && !init?.method,
    )).toBe(true);
    expect(fetchMock.mock.calls.filter(
      ([input, init]) => String(input).endsWith("/inspections/namespace/run") && init?.method === "POST",
    )).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Pod 名称"), { target: { value: "demo-api-1" } });
    fireEvent.click(screen.getByRole("button", { name: "巡检单个 Pod" }));

    expect(await screen.findByText("单 Pod 结果")).toBeInTheDocument();
    expect(screen.getByText("资源指标").closest(".coverage-row")).toHaveClass("coverage-skipped");
    expect(screen.getByText("本次有检查跳过或失败，不能据此确认全部正常。")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "确认大范围日志巡检" })).not.toBeInTheDocument();
    expect(screen.getByText((_, element) => element?.textContent === "level=error msg=database connection refused")).toBeInTheDocument();

    const request = fetchMock.mock.calls.find(
      ([input, init]) => String(input).endsWith("/inspections/pod/run") && init?.method === "POST",
    );
    expect(request).toBeDefined();
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({
      namespace: "demo",
      pod_name: "demo-api-1",
    });
  });

  it("clears the Pod dropdown when switching namespaces and only shows the new discovery result", async () => {
    render(<PodInspectionPage />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    expect(await screen.findByRole("option", { name: "demo-api-1" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "prod" } });
    expect(screen.queryByRole("option", { name: "demo-api-1" })).not.toBeInTheDocument();
    expect(await screen.findByRole("option", { name: "prod-api-1" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(
      ([input, init]) => String(input).includes("/inspections/") && init?.method === "POST",
    )).toHaveLength(0);
  });

  it("prefers context_text when rendering log hit details", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/settings")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({ inspection_policy: { max_log_pods: 120 } }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/discovery/namespaces")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              executed_at: "2026-07-21T10:00:00Z",
              namespaces: [
                {
                  name: "demo",
                  status: "warning",
                  pod_count: 1,
                  abnormal_pod_count: 1,
                  last_inspected_at: null,
                  labels: {},
                  abnormal_categories: ["log_keyword"],
                },
              ],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/inspection-targets") && (!init || init.method === undefined)) {
        return Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } }));
      }

      if (url.endsWith("/discovery/namespaces/demo/labels")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({ namespace: "demo", executed_at: "2026-07-21T10:00:00Z", labels: [] }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/discovery/namespaces/demo/pods")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              namespace: "demo",
              label_selector: null,
              executed_at: "2026-07-21T10:00:00Z",
              pod_count: 1,
              pods: [{ name: "demo-api-1", labels: { app: "demo-api" } }],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/inspections/namespace/run") && init?.method === "POST") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              inspection_target: { type: "namespace", namespace: "demo", label_selector: null, saved_target_id: null, resource_scope: ["pods"] },
              namespace: "demo",
              health_status: "warning",
              executed_at: "2026-07-21T10:10:00Z",
              evidence_bundles: [],
              pods: [
                {
                  name: "demo-api-1",
                  status: "CrashLoopBackOff",
                  restarts: 6,
                  node_name: "node-a",
                  containers: [],
                  events: [],
                  describe_summary: "startup failed",
                  log_summary: "database connection refused",
                  previous_log_summary: null,
                  log_hits: [
                    {
                      keyword: "connection refused",
                      category: "database",
                      severity: "error",
                      source: "current_log",
                      matched_text: "database connection refused",
                      context_before: ["booting app", "dial tcp db:5432"],
                      context_after: ["retry in 3s", "panic: dependency unavailable"],
                      context_text: "booting app\ndial tcp db:5432\ndatabase connection refused\nretry in 3s\npanic: dependency unavailable",
                      container_name: "demo-api",
                      whitelisted: false,
                      whitelist_rule_id: null,
                    },
                  ],
                  resource_usage: { cpu: "220m", memory: "180Mi" },
                  related_resources: [],
                },
              ],
              services: [],
              ingresses: [],
              tls_secrets: [],
              daemonsets: [],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    render(<PodInspectionPage initialScopeMode="all" />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.click(screen.getByRole("button", { name: "日志巡检" }));

    expect(await screen.findByText("原始日志")).toBeInTheDocument();
    expect(screen.getByText((_, element) => element?.textContent === "booting app\ndial tcp db:5432\ndatabase connection refused\nretry in 3s\npanic: dependency unavailable")).toBeInTheDocument();
    expect(screen.getAllByText("connection refused").some((element) => element.tagName.toLowerCase() === "mark")).toBe(true);
    expect(screen.queryByText((_, element) => element?.textContent === "{\"error\":\"invalid_client\",\"error_description\":\"Client authentication failed\"}")).not.toBeInTheDocument();
  });

  it("saves current label selector as inspection point through modal", async () => {
    render(<PodInspectionPage />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("范围类型"), { target: { value: "label" } });
    await screen.findByRole("option", { name: "app=demo-api（1 个 Pod）" });
    fireEvent.change(screen.getByLabelText("Label Selector"), { target: { value: "app=demo-api" } });
    fireEvent.click(screen.getAllByRole("button", { name: "保存巡检点" })[0]);
    const saveDialog = await screen.findByRole("dialog", { name: "保存巡检点" });
    expect(screen.getByLabelText("巡检点名称")).toHaveValue("demo / app=demo-api");
    fireEvent.change(screen.getByLabelText("巡检点名称"), { target: { value: "demo API 标签巡检" } });
    fireEvent.click(saveDialog.querySelectorAll("button")[1] as HTMLButtonElement);

    expect(await screen.findByText("demo API 标签巡检")).toBeInTheDocument();
  });

  it("preserves whitelist ignore entry in pod inspection", async () => {
    render(<PodInspectionPage />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("范围类型"), { target: { value: "single" } });
    fireEvent.change(await screen.findByLabelText("Pod 名称"), { target: { value: "demo-api-1" } });
    fireEvent.click(screen.getByRole("button", { name: "巡检单个 Pod" }));
    fireEvent.click(await screen.findByRole("button", { name: "忽略此报错" }));
    const ignoreDialog = await screen.findByRole("dialog", { name: "忽略此报错" });
    expect(within(ignoreDialog).getByLabelText("白名单名称空间")).toHaveValue("demo");
    expect(within(ignoreDialog).getByLabelText("白名单 Label Selector 候选")).toHaveValue("app=demo-api");
    expect(within(ignoreDialog).getByLabelText("白名单来源 Pod")).toHaveValue("demo-api-1");
    expect(within(ignoreDialog).getByLabelText("白名单字段")).toHaveValue("");
    fireEvent.change(within(ignoreDialog).getByLabelText("白名单字段"), { target: { value: "level=error msg=database connection refused" } });
    fireEvent.click(within(ignoreDialog).getByRole("button", { name: "加入白名单" }));

    await waitFor(() => {
      expect(screen.getByText("已加入白名单，后续 Pod 巡检会自动忽略该命中")).toBeInTheDocument();
    });
  });

  it("supports import filtering in modal flow", async () => {
    render(<PodInspectionPage />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.click(screen.getByRole("button", { name: "导入" }));
    fireEvent.change(await screen.findByLabelText("导入内容"), {
      target: {
        value: JSON.stringify([
          {
            name: "imported pod target",
            target_type: "pod",
            namespace: "prod",
            pod_name: "",
            label_selector: "app=api",
            resource_scope: ["pods"],
          },
          {
            name: "ignored namespace target",
            target_type: "namespace",
            namespace: "prod",
            label_selector: "app=api",
            resource_scope: ["pods", "services"],
          },
        ]),
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "导入巡检点" }));

    expect(await screen.findByText("imported pod target")).toBeInTheDocument();
    expect(await screen.findByText("已导入 1 个巡检点")).toBeInTheDocument();
    expect(screen.queryByText("ignored namespace target")).not.toBeInTheDocument();
  });
});
