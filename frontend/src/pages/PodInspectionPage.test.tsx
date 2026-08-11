import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { runClusterInspection } from "../api/client";
import { PodInspectionPage } from "./PodInspectionPage";

const fetchMock = vi.fn();
let discoveredPodCount: number | null = 3;
let configuredMaxLogPods = 120;
let failDemoPodDiscovery = false;
let stopRecordingConflict = false;
let listRunningRecording = false;
let listEndedRecording = false;

describe("PodInspectionPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    discoveredPodCount = 3;
    configuredMaxLogPods = 120;
    failDemoPodDiscovery = false;
    stopRecordingConflict = false;
    listRunningRecording = false;
    listEndedRecording = false;
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

      if (url.includes("/log-recordings?") && (!init || init.method === undefined)) {
        const items = [
          ...(listRunningRecording
            ? [{
              id: 7,
              name: "接口恢复的记录",
              namespace: "demo",
              note: null,
              status: "recording",
              started_at: "2026-07-19T10:00:00Z",
              ended_at: null,
              planned_end_at: "2026-07-19T10:20:00Z",
              duration_source: "system_default",
              duration_minutes: 20,
              stop_reason: null,
              pod_count: 2,
              container_count: 3,
              raw_line_count: 0,
              folded_line_count: 0,
              total_bytes: 0,
              truncated: false,
              created_by: "admin",
              created_at: "2026-07-19T10:00:00Z",
              updated_at: "2026-07-19T10:00:00Z",
            }]
            : []),
          ...(listEndedRecording
            ? [{
              id: 8,
              name: "已结束的复现记录",
              namespace: "demo",
              note: null,
              status: "completed",
              started_at: "2026-07-19T09:00:00Z",
              ended_at: "2026-07-19T09:10:00Z",
              planned_end_at: "2026-07-19T09:20:00Z",
              duration_source: "system_default",
              duration_minutes: 20,
              stop_reason: "user_stopped",
              pod_count: 2,
              container_count: 3,
              raw_line_count: 12,
              folded_line_count: 6,
              total_bytes: 200,
              truncated: false,
              created_by: "admin",
              created_at: "2026-07-19T09:00:00Z",
              updated_at: "2026-07-19T09:10:00Z",
            }]
            : []),
        ];
        return Promise.resolve(
          new Response(
            JSON.stringify({ items, total: items.length, page: 1, page_size: 20 }),
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

      if (url.includes("/discovery/namespaces/demo/pods?")) {
        expect(url).toContain("label_selector=app%3Ddemo-api");
        return Promise.resolve(
          new Response(
            JSON.stringify({
              namespace: "demo",
              label_selector: "app=demo-api",
              executed_at: "2026-07-19T10:00:00Z",
              pod_count: 1,
              pods: [{ name: "demo-api-1", labels: { app: "demo-api" } }],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/discovery/namespaces/demo/pods")) {
        if (failDemoPodDiscovery) {
          return Promise.resolve(
            new Response(JSON.stringify({ detail: "discovery failed" }), {
              status: 503,
              headers: { "Content-Type": "application/json" },
            }),
          );
        }
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

      if (url.endsWith("/inspections/logs/namespace/run") && init?.method === "POST") {
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
              coverage: [],
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

      if (url.endsWith("/log-recordings/preview") && init?.method === "POST") {
        return Promise.resolve(
          new Response(
            JSON.stringify({ namespace: "demo", pod_count: 2, container_count: 3, allowed: true, reason: null }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/log-recordings") && init?.method === "POST") {
        const payload = JSON.parse(String(init.body));
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: payload.namespace === "prod" ? 2 : 1,
              status: "recording",
              started_at: "2026-07-19T10:00:00Z",
              ended_at: null,
              planned_end_at: "2026-07-19T10:20:00Z",
              stop_reason: null,
              pod_count: 2,
              container_count: 3,
              raw_line_count: 0,
              folded_line_count: 0,
              total_bytes: 0,
              truncated: false,
              created_by: "admin",
              created_at: "2026-07-19T10:00:00Z",
              updated_at: "2026-07-19T10:00:00Z",
              ...payload,
              duration_minutes: payload.duration_minutes ?? 20,
            }),
            { status: 201, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/log-recordings/1/stop") && init?.method === "POST") {
        if (stopRecordingConflict) {
          return Promise.resolve(
            new Response(JSON.stringify({ detail: "日志记录已结束" }), {
              status: 409,
              headers: { "Content-Type": "application/json" },
            }),
          );
        }
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 1,
              name: "支付 500 复现",
              namespace: "demo",
              note: "点击支付后复现",
              status: "completed",
              started_at: "2026-07-19T10:00:00Z",
              ended_at: "2026-07-19T10:05:00Z",
              planned_end_at: "2026-07-19T10:20:00Z",
              duration_source: "preset",
              duration_minutes: 20,
              stop_reason: "user_stopped",
              pod_count: 2,
              container_count: 3,
              raw_line_count: 1,
              folded_line_count: 1,
              total_bytes: 20,
              truncated: false,
              created_by: "admin",
              created_at: "2026-07-19T10:00:00Z",
              updated_at: "2026-07-19T10:05:00Z",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/log-recordings/1") && (!init || init.method === undefined)) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 1,
              name: "支付 500 复现",
              namespace: "demo",
              note: "点击支付后复现",
              status: "auto_completed",
              started_at: "2026-07-19T10:00:00Z",
              ended_at: "2026-07-19T10:20:00Z",
              planned_end_at: "2026-07-19T10:20:00Z",
              duration_source: "system_default",
              duration_minutes: 20,
              stop_reason: "system_default_timeout",
              pod_count: 2,
              container_count: 3,
              raw_line_count: 1,
              folded_line_count: 1,
              total_bytes: 20,
              truncated: false,
              created_by: "admin",
              created_at: "2026-07-19T10:00:00Z",
              updated_at: "2026-07-19T10:20:00Z",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
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
    expect(screen.getByText("日志巡检结果")).toBeInTheDocument();
    expect(screen.getByText(/已检查 2 个 Pod，发现 1 个日志命中/)).toBeInTheDocument();
    expect(screen.queryByText("本次巡检结论")).not.toBeInTheDocument();
    expect(screen.queryByText("本次巡检覆盖")).not.toBeInTheDocument();
    expect(screen.queryByText("Pod 运行状态")).not.toBeInTheDocument();
    expect(screen.queryByText("本次有检查跳过或失败，不能据此确认全部正常。")).not.toBeInTheDocument();
    expect(screen.queryByText("最近一次巡检摘要")).not.toBeInTheDocument();
    expect(screen.getByText("命中关键字：connection refused")).toBeInTheDocument();

    const request = fetchMock.mock.calls.find(
      ([input, init]) => String(input).endsWith("/inspections/logs/namespace/run") && init?.method === "POST",
    );
    expect(request).toBeDefined();
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({
      namespace: "demo",
      label_selector: null,
      log_time_range: { mode: "recent", recent_minutes: 15 },
    });
  });

  it("starts and stops reproduction log recording inside the log inspection page", async () => {
    render(<PodInspectionPage initialScopeMode="all" />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.click(screen.getByRole("button", { name: "开始记录日志" }));

    expect(await screen.findByRole("heading", { name: "开始记录日志" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("日志名称"), { target: { value: "支付 500 复现" } });
    fireEvent.change(screen.getByLabelText("记录备注"), { target: { value: "点击支付后复现" } });
    fireEvent.click(screen.getByRole("button", { name: "确认开始" }));

    expect(await screen.findByText("已开始 1 条日志记录")).toBeInTheDocument();
    expect(screen.getByText("进行中的日志记录")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始记录日志" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "结束记录" })).toBeInTheDocument();

    const createRequest = fetchMock.mock.calls.find(
      ([input, init]) => String(input).endsWith("/log-recordings") && init?.method === "POST",
    );
    expect(createRequest).toBeDefined();
    expect(JSON.parse(String(createRequest?.[1]?.body))).toMatchObject({
      name: "支付 500 复现",
      namespace: "demo",
      note: "点击支付后复现",
      duration_source: "system_default",
      duration_minutes: null,
    });

    fireEvent.click(screen.getByRole("button", { name: "结束记录" }));
    expect(await screen.findByText("已停止记录：支付 500 复现")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始记录日志" })).toBeInTheDocument();
  });

  it("starts recordings after selecting namespaces in the recording tree", async () => {
    render(<PodInspectionPage initialScopeMode="all" />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.click(screen.getByRole("button", { name: "开始记录日志" }));

    expect(await screen.findByRole("heading", { name: "开始记录日志" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "日志记录" })).toHaveAttribute("href", "/log-recordings");
    fireEvent.change(screen.getByLabelText("日志名称"), { target: { value: "批量复现" } });
    fireEvent.click(screen.getByLabelText("记录名称空间 demo"));
    fireEvent.click(screen.getByLabelText("记录名称空间 prod"));
    fireEvent.click(screen.getByRole("button", { name: "确认开始" }));

    expect(await screen.findByText("已开始 2 条日志记录")).toBeInTheDocument();
    const createRequests = fetchMock.mock.calls.filter(
      ([input, init]) => String(input).endsWith("/log-recordings") && init?.method === "POST",
    );
    expect(createRequests).toHaveLength(2);
    expect(createRequests.map((request) => JSON.parse(String(request[1]?.body)).namespace)).toEqual(["demo", "prod"]);
  });

  it("loads running recordings as a list after returning to the log inspection page", async () => {
    listRunningRecording = true;
    render(<PodInspectionPage initialScopeMode="all" />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });

    expect(await screen.findByText("进行中的日志记录")).toBeInTheDocument();
    expect(screen.getByText("接口恢复的记录")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始记录日志" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "结束记录" })).toBeInTheDocument();
  });

  it("shows ended recordings history inside the log inspection page", async () => {
    listEndedRecording = true;
    render(<PodInspectionPage initialScopeMode="all" />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });

    expect(await screen.findByText("最近结束的日志记录")).toBeInTheDocument();
    expect(screen.getByText("已结束的复现记录")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看日志" })).toHaveAttribute(
      "href",
      "/log-recordings?recordingId=8",
    );
  });

  it("recovers when stopping a recording that already ended in the backend", async () => {
    stopRecordingConflict = true;
    render(<PodInspectionPage initialScopeMode="all" />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.click(screen.getByRole("button", { name: "开始记录日志" }));

    await screen.findByRole("heading", { name: "开始记录日志" });
    fireEvent.change(screen.getByLabelText("日志名称"), { target: { value: "支付 500 复现" } });
    fireEvent.click(screen.getByRole("button", { name: "确认开始" }));
    expect(await screen.findByRole("button", { name: "结束记录" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "结束记录" }));

    expect(await screen.findByText("记录已结束：支付 500 复现")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始记录日志" })).toBeInTheDocument();
    expect(screen.queryByText(/记录日志失败/)).not.toBeInTheDocument();
  });

  it("runs saved label inspection point on the first click after resolving pod count", async () => {
    render(<PodInspectionPage />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.click(screen.getByRole("button", { name: "巡检点" }));
    const targetRow = screen.getByText("demo API 标签范围").closest("tr");
    expect(targetRow).not.toBeNull();

    fireEvent.click(within(targetRow as HTMLTableRowElement).getByRole("button", { name: "巡检" }));

    expect(await screen.findByText("Pod 列表")).toBeInTheDocument();
    expect(screen.queryByText("日志读取保护")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input, init]) =>
      String(input).endsWith("/inspections/logs/namespace/run")
      && init?.method === "POST"
      && JSON.parse(String(init.body)).label_selector === "app=demo-api",
    )).toBe(true);
  });

  it("presents log inspection as healthy when no log keyword is hit", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/settings")) {
        return Promise.resolve(
          new Response(JSON.stringify({ inspection_policy: { max_log_pods: 120 } }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }

      if (url.endsWith("/discovery/namespaces")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              executed_at: "2026-07-19T10:00:00Z",
              namespaces: [{ name: "demo", status: "healthy", pod_count: 1, abnormal_pod_count: 0, last_inspected_at: null, labels: {}, abnormal_categories: [] }],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/inspection-targets") && (!init || init.method === undefined)) {
        return Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } }));
      }

      if (url.includes("/log-recordings?") && (!init || init.method === undefined)) {
        return Promise.resolve(
          new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }

      if (url.endsWith("/discovery/namespaces/demo/labels")) {
        return Promise.resolve(
          new Response(JSON.stringify({ namespace: "demo", executed_at: "2026-07-19T10:00:00Z", labels: [] }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }

      if (url.endsWith("/discovery/namespaces/demo/pods")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              namespace: "demo",
              label_selector: null,
              executed_at: "2026-07-19T10:00:00Z",
              pod_count: 1,
              pods: [{ name: "demo-worker-1", labels: { app: "demo-worker" } }],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/inspections/logs/namespace/run") && init?.method === "POST") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              inspection_target: { type: "namespace", namespace: "demo", label_selector: null, saved_target_id: null, resource_scope: ["pod_logs"] },
              namespace: "demo",
              label_selector: null,
              health_status: "healthy",
              executed_at: "2026-07-19T10:30:00Z",
              evidence_bundles: [],
              pods: [{
                name: "demo-worker-1",
                status: "unknown",
                restarts: 0,
                node_name: null,
                containers: [],
                events: [],
                describe_summary: "日志巡检未采集 Pod 运行状态、事件、Service 或 Ingress。",
                log_summary: "worker started",
                previous_log_summary: null,
                log_hits: [],
                resource_usage: {},
                related_resources: [],
              }],
              services: [],
              ingresses: [],
              tls_secrets: [],
              daemonsets: [],
              issues: [],
              coverage: [],
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

    expect(await screen.findByText(/已检查 1 个 Pod，发现 0 个日志命中/)).toBeInTheDocument();
    const resultPanel = screen.getByText("日志巡检结果").closest(".panel");
    expect(resultPanel).not.toBeNull();
    expect(within(resultPanel as HTMLElement).getByText("正常")).toBeInTheDocument();
    const podRow = screen.getByRole("button", { name: /demo-worker-1/ });
    expect(within(podRow).getByText("正常")).toBeInTheDocument();
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
      ([input, init]) => String(input).endsWith("/inspections/logs/namespace/run") && init?.method === "POST",
    )).toHaveLength(0);

    fireEvent.click(within(dialog).getByRole("button", { name: "返回缩小范围" }));
    expect(screen.queryByRole("dialog", { name: "无法执行大范围日志巡检" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(
      ([input, init]) => String(input).endsWith("/inspections/logs/namespace/run") && init?.method === "POST",
    )).toHaveLength(0);
  });

  it("blocks a range with unknown pod count without sending an inspection request", async () => {
    discoveredPodCount = null;
    failDemoPodDiscovery = true;
    render(<PodInspectionPage initialScopeMode="all" />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.click(screen.getByRole("button", { name: "日志巡检" }));

    const dialog = await screen.findByRole("dialog", { name: "无法执行大范围日志巡检" });
    expect(within(dialog).getByText("当前无法确认该范围的 Pod 数量，为避免读取过多日志，本次巡检已阻断。")).toBeInTheDocument();
    expect(within(dialog).getByText("请先刷新发现数据、选择可确认 Pod 数量的范围，或使用 Label Selector 缩小范围后重试。")).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "仍要继续" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(
      ([input, init]) => String(input).endsWith("/inspections/logs/namespace/run") && init?.method === "POST",
    )).toHaveLength(0);

    fireEvent.click(within(dialog).getByRole("button", { name: "返回缩小范围" }));
    expect(fetchMock.mock.calls.filter(
      ([input, init]) => String(input).endsWith("/inspections/logs/namespace/run") && init?.method === "POST",
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
      .filter(([input, init]) => String(input).endsWith("/inspections/logs/namespace/run") && init?.method === "POST")
      .at(-1);
    expect(request).toBeDefined();
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({
      namespace: "demo",
      label_selector: "app=demo-api",
      log_time_range: { mode: "recent", recent_minutes: 15 },
    });
  });

  it("sends a custom log time range for namespace log inspection", async () => {
    render(<PodInspectionPage />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("范围类型"), { target: { value: "label" } });
    await screen.findByRole("option", { name: "app=demo-api（1 个 Pod）" });
    fireEvent.change(screen.getByLabelText("Label Selector"), { target: { value: "app=demo-api" } });
    fireEvent.change(screen.getByLabelText("日志时间范围"), { target: { value: "custom" } });
    fireEvent.change(screen.getByLabelText("日志开始时间"), { target: { value: "2020-01-02T10:00" } });
    fireEvent.change(screen.getByLabelText("日志结束时间"), { target: { value: "2020-01-02T10:30" } });
    fireEvent.click(screen.getByRole("button", { name: "日志巡检" }));

    expect(await screen.findByText("Pod 列表")).toBeInTheDocument();
    const request = fetchMock.mock.calls
      .filter(([input, init]) => String(input).endsWith("/inspections/logs/namespace/run") && init?.method === "POST")
      .at(-1);
    const body = JSON.parse(String(request?.[1]?.body));
    expect(body.namespace).toBe("demo");
    expect(body.label_selector).toBe("app=demo-api");
    expect(body.log_time_range.mode).toBe("custom");
    expect(body.log_time_range.start_time).toBe(new Date("2020-01-02T10:00").toISOString());
    expect(body.log_time_range.end_time).toBe(new Date("2020-01-02T10:30").toISOString());
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
      ([input, init]) => String(input).endsWith("/inspections/logs/namespace/run") && init?.method === "POST",
    )).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Pod 名称"), { target: { value: "demo-api-1" } });
    fireEvent.click(screen.getByRole("button", { name: "巡检单个 Pod" }));

    expect(await screen.findByText("单 Pod 日志")).toBeInTheDocument();
    expect(screen.getByText("日志巡检结果")).toBeInTheDocument();
    expect(screen.getByText(/已检查 1 个 Pod，发现 1 个日志命中/)).toBeInTheDocument();
    expect(screen.queryByText("本次巡检结论")).not.toBeInTheDocument();
    expect(screen.queryByText("本次巡检覆盖")).not.toBeInTheDocument();
    expect(screen.queryByText("资源指标")).not.toBeInTheDocument();
    expect(screen.queryByText("本次有检查跳过或失败，不能据此确认全部正常。")).not.toBeInTheDocument();
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

      if (url.endsWith("/inspections/logs/namespace/run") && init?.method === "POST") {
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

    expect(await screen.findByText("命中上下文（不是完整日志）")).toBeInTheDocument();
    expect(screen.getByText("Pod：demo-api-1")).toBeInTheDocument();
    expect(screen.getByText("容器：demo-api")).toBeInTheDocument();
    expect(screen.getByText("关键字：connection refused")).toBeInTheDocument();
    expect(screen.getByText("时间：服务端未返回")).toBeInTheDocument();
    expect(screen.getByText((_, element) => element?.textContent === "booting app\ndial tcp db:5432\ndatabase connection refused\nretry in 3s\npanic: dependency unavailable")).toBeInTheDocument();
    expect(screen.getAllByText("connection refused").some((element) => element.tagName.toLowerCase() === "mark")).toBe(true);
    expect(screen.queryByText((_, element) => element?.textContent === "{\"error\":\"invalid_client\",\"error_description\":\"Client authentication failed\"}")).not.toBeInTheDocument();
  });

  it("always shows matched log line when context text was truncated before the hit", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/settings")) {
        return Promise.resolve(new Response(JSON.stringify({ inspection_policy: { max_log_pods: 120 } }), { status: 200, headers: { "Content-Type": "application/json" } }));
      }
      if (url.endsWith("/discovery/namespaces")) {
        return Promise.resolve(new Response(JSON.stringify({
          executed_at: "2026-07-21T10:00:00Z",
          namespaces: [{ name: "demo", status: "warning", pod_count: 1, abnormal_pod_count: 1, last_inspected_at: null, labels: {}, abnormal_categories: ["log_keyword"] }],
        }), { status: 200, headers: { "Content-Type": "application/json" } }));
      }
      if (url.endsWith("/inspection-targets") && (!init || init.method === undefined)) {
        return Promise.resolve(new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } }));
      }
      if (url.endsWith("/discovery/namespaces/demo/labels")) {
        return Promise.resolve(new Response(JSON.stringify({ namespace: "demo", executed_at: "2026-07-21T10:00:00Z", labels: [] }), { status: 200, headers: { "Content-Type": "application/json" } }));
      }
      if (url.endsWith("/discovery/namespaces/demo/pods")) {
        return Promise.resolve(new Response(JSON.stringify({
          namespace: "demo",
          label_selector: null,
          executed_at: "2026-07-21T10:00:00Z",
          pod_count: 1,
          pods: [{ name: "demo-api-1", labels: { app: "demo-api" } }],
        }), { status: 200, headers: { "Content-Type": "application/json" } }));
      }
      if (url.endsWith("/inspections/logs/namespace/run") && init?.method === "POST") {
        return Promise.resolve(new Response(JSON.stringify({
          inspection_target: { type: "namespace", namespace: "demo", label_selector: null, saved_target_id: null, resource_scope: ["pods"] },
          namespace: "demo",
          health_status: "warning",
          executed_at: "2026-07-21T10:10:00Z",
          evidence_bundles: [],
          pods: [{
            name: "demo-api-1",
            status: "Running",
            restarts: 0,
            node_name: "node-a",
            containers: [],
            events: [],
            describe_summary: "running",
            log_summary: null,
            previous_log_summary: null,
            log_hits: [{
              keyword: "ERROR",
              category: "runtime",
              severity: "error",
              source: "current_log",
              matched_text: "level=error msg=database failed",
              context_text: "[DEBUG] long stream output without the matched keyword…（已截断）",
              container_name: "api",
              whitelisted: false,
              whitelist_rule_id: null,
            }],
            resource_usage: {},
            related_resources: [],
          }],
          services: [],
          ingresses: [],
          tls_secrets: [],
          daemonsets: [],
        }), { status: 200, headers: { "Content-Type": "application/json" } }));
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    render(<PodInspectionPage initialScopeMode="all" />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.click(screen.getByRole("button", { name: "日志巡检" }));

    expect(await screen.findByText("命中上下文（不是完整日志）")).toBeInTheDocument();
    expect(screen.getByText("原始日志已截断")).toBeInTheDocument();
    expect(screen.getByText("容器：api")).toBeInTheDocument();
    expect(screen.getAllByText((_, element) =>
      element?.tagName.toLowerCase() === "pre"
      && Boolean(element.textContent?.includes("命中行：level=error msg=database failed")),
    )).toHaveLength(1);
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
