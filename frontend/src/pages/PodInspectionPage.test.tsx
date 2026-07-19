import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PodInspectionPage } from "./PodInspectionPage";

const fetchMock = vi.fn();

describe("PodInspectionPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
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

      if (url.endsWith("/discovery/namespaces")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              executed_at: "2026-07-19T10:00:00Z",
              namespaces: [
                {
                  name: "demo",
                  status: "warning",
                  pod_count: 3,
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
                    keyword: "connection refused",
                    category: "database",
                    severity: "error",
                    source: "log_summary",
                    matched_text: "database connection refused",
                    container_name: "demo-api",
                    whitelisted: false,
                    whitelist_rule_id: null,
                  },
                ],
                resource_usage: { cpu: "220m", memory: "180Mi" },
                related_resources: [],
              },
              evidence_bundle: null,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/whitelists/ignore") && init?.method === "POST") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 1,
              namespace: "demo",
              label_selector: null,
              pod_name_pattern: "demo-api-1",
              container_name: "demo-api",
              keyword: "connection refused",
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
    const exportDialog = await screen.findByRole("dialog", { name: "导出巡检对象" });
    expect(exportDialog).toBeInTheDocument();
    expect(screen.getByLabelText("导出内容")).toBeInTheDocument();
  });

  it("runs all pod mode without requiring pod name", async () => {
    render(<PodInspectionPage />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("巡检范围"), { target: { value: "all" } });
    fireEvent.click(screen.getByRole("button", { name: "巡检 Pod 范围" }));

    expect(await screen.findByText("最近一次巡检摘要")).toBeInTheDocument();

    const request = fetchMock.mock.calls.find(
      ([input, init]) => String(input).endsWith("/inspections/namespace/run") && init?.method === "POST",
    );
    expect(request).toBeDefined();
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({
      namespace: "demo",
      label_selector: null,
    });
  });

  it("runs label selector mode through namespace inspection", async () => {
    render(<PodInspectionPage />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("巡检范围"), { target: { value: "label" } });
    fireEvent.change(screen.getByLabelText("Label Selector"), { target: { value: "app=demo-api" } });
    fireEvent.click(screen.getByRole("button", { name: "巡检 Pod 范围" }));

    expect(await screen.findByText("范围巡检结果不会伪装成单 Pod")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /demo-api-1/ })).toBeInTheDocument();

    const request = fetchMock.mock.calls
      .filter(([input, init]) => String(input).endsWith("/inspections/namespace/run") && init?.method === "POST")
      .at(-1);
    expect(request).toBeDefined();
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({
      namespace: "demo",
      label_selector: "app=demo-api",
    });
  });

  it("runs single pod mode through pod inspection with dropdown pod selection", async () => {
    render(<PodInspectionPage />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("巡检范围"), { target: { value: "single" } });

    expect(await screen.findByRole("option", { name: "demo-api-1" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Pod 名称"), { target: { value: "demo-api-1" } });
    fireEvent.click(screen.getByRole("button", { name: "巡检单个 Pod" }));

    expect(await screen.findByText("单 Pod 结果")).toBeInTheDocument();
    expect(await screen.findByText("database connection refused")).toBeInTheDocument();

    const request = fetchMock.mock.calls.find(
      ([input, init]) => String(input).endsWith("/inspections/pod/run") && init?.method === "POST",
    );
    expect(request).toBeDefined();
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({
      namespace: "demo",
      pod_name: "demo-api-1",
    });
  });

  it("saves current pod range through modal", async () => {
    render(<PodInspectionPage />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("巡检范围"), { target: { value: "label" } });
    fireEvent.change(screen.getByLabelText("Label Selector"), { target: { value: "app=demo-api" } });
    fireEvent.click(screen.getAllByRole("button", { name: "保存当前范围" })[0]);
    const saveDialog = await screen.findByRole("dialog", { name: "保存当前范围" });
    fireEvent.change(screen.getByLabelText("常用范围名称"), { target: { value: "demo API 标签巡检" } });
    fireEvent.click(saveDialog.querySelectorAll("button")[1] as HTMLButtonElement);

    expect(await screen.findByRole("button", { name: /使用 demo API 标签巡检/ })).toBeInTheDocument();
  });

  it("preserves whitelist ignore entry in pod inspection", async () => {
    render(<PodInspectionPage />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("巡检范围"), { target: { value: "single" } });
    fireEvent.change(await screen.findByLabelText("Pod 名称"), { target: { value: "demo-api-1" } });
    fireEvent.click(screen.getByRole("button", { name: "巡检单个 Pod" }));
    fireEvent.click(await screen.findByRole("button", { name: "忽略此报错" }));

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
            pod_name: "api-0",
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
    fireEvent.click(screen.getByRole("button", { name: "导入巡检对象" }));

    expect(await screen.findByRole("button", { name: /使用 imported pod target/ })).toBeInTheDocument();
    expect(await screen.findByText("已导入 1 个 Pod 巡检对象")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /使用 ignored namespace target/ })).not.toBeInTheDocument();
  });
});
