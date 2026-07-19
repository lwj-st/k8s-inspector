import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NamespaceInspectionPage } from "./NamespaceInspectionPage";

const fetchMock = vi.fn();

describe("NamespaceInspectionPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    const savedTargets = [
      {
        id: 1,
        name: "demo 全名称空间",
        target_type: "namespace",
        namespace: "demo",
        label_selector: null,
        resource_scope: ["pods", "services", "ingresses", "daemonsets", "secrets"],
        created_at: "2026-07-19T10:00:00Z",
        updated_at: "2026-07-19T10:00:00Z",
      },
      {
        id: 2,
        name: "demo-api Pod 对象",
        target_type: "pod",
        namespace: "demo",
        pod_name: "demo-api-1",
        label_selector: null,
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
                  pod_count: 2,
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

      if (url.endsWith("/whitelists/ignore") && init?.method === "POST") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 3,
              namespace: "demo",
              label_selector: "app=demo-api",
              pod_name_pattern: "demo-api-1",
              container_name: "demo-api",
              keyword: "connection refused",
              enabled: true,
              note: "从巡检结果忽略",
            }),
            { status: 201, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/diagnoses/run") && init?.method === "POST") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              status: "matched",
              namespace: "demo",
              direction: "template_check",
              scope: "app=demo-api",
              executed_at: "2026-07-19T09:00:00Z",
              inspection_target: {
                type: "template",
                namespace: "demo",
                pod_name: null,
                label_selector: "app=demo-api",
                saved_target_id: null,
                template_id: null,
                resource_scope: ["pods"],
              },
              matches: [],
              template_match_results: [
                {
                  template_id: 1,
                  template_name: "API 启动失败模板",
                  matched: true,
                  matched_conditions: [],
                  unmatched_conditions: [],
                  summary: "日志关键字已命中",
                  reason: "启动依赖不可达",
                  suggestion: "检查数据库与网络",
                  risk_note: null,
                  evidence_refs: [],
                },
              ],
              evidence_summary: [{ type: "namespace", value: "demo" }],
              llm_supplement: null,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
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
                resource_scope: ["pods", "services", "ingresses", "daemonsets", "secrets"],
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

      throw new Error(`Unexpected request: ${url}`);
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  it("shows discovered namespaces in dropdown and runs namespace inspection", async () => {
    render(<NamespaceInspectionPage />);

    expect(await screen.findByRole("option", { name: "demo" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("Label Selector（可选）"), { target: { value: "app=demo-api" } });
    fireEvent.click(screen.getByRole("button", { name: "巡检名称空间" }));

    expect(await screen.findByText("本次结果摘要")).toBeInTheDocument();
    expect(await screen.findByText("异常 Pod")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /demo-api-1/ })).toBeInTheDocument();

    const request = fetchMock.mock.calls.find(
      ([input, init]) => String(input).endsWith("/inspections/namespace/run") && init?.method === "POST",
    );
    expect(request).toBeDefined();
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({
      namespace: "demo",
      label_selector: "app=demo-api",
    });
  });

  it("keeps import and export textarea hidden until modal opens", async () => {
    render(<NamespaceInspectionPage />);

    await screen.findByRole("option", { name: "demo" });
    expect(screen.queryByLabelText("导出内容")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("导入内容")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "导出" }));
    const exportDialog = await screen.findByRole("dialog", { name: "导出巡检对象" });
    expect(exportDialog).toBeInTheDocument();
    expect(screen.getByLabelText("导出内容")).toBeInTheDocument();

    fireEvent.click(within(exportDialog).getAllByRole("button", { name: "关闭" })[0]);
    await waitFor(() => {
      expect(screen.queryByLabelText("导出内容")).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "导入" }));
    expect(await screen.findByRole("dialog", { name: "导入巡检对象" })).toBeInTheDocument();
    expect(screen.getByLabelText("导入内容")).toBeInTheDocument();
  });

  it("saves current namespace range through modal", async () => {
    render(<NamespaceInspectionPage />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("Label Selector（可选）"), { target: { value: "app=demo-api" } });
    fireEvent.click(screen.getAllByRole("button", { name: "保存当前范围" })[0]);
    const saveDialog = await screen.findByRole("dialog", { name: "保存当前范围" });
    fireEvent.change(screen.getByLabelText("常用范围名称"), { target: { value: "demo-api 启动排查" } });
    fireEvent.click(within(saveDialog).getByRole("button", { name: "保存当前范围" }));

    expect(await screen.findByRole("button", { name: /使用 demo-api 启动排查/ })).toBeInTheDocument();
  });

  it("supports import and export in modal flow", async () => {
    render(<NamespaceInspectionPage />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.click(screen.getByRole("button", { name: "导出" }));
    expect((await screen.findByLabelText("导出内容") as HTMLTextAreaElement).value).toContain("demo 全名称空间");
    const exportDialog = await screen.findByRole("dialog", { name: "导出巡检对象" });
    fireEvent.click(within(exportDialog).getAllByRole("button", { name: "关闭" })[0]);

    fireEvent.click(screen.getByRole("button", { name: "导入" }));
    fireEvent.change(await screen.findByLabelText("导入内容"), {
      target: {
        value: JSON.stringify([
          {
            name: "imported target",
            target_type: "namespace",
            namespace: "prod",
            label_selector: "app=api",
            resource_scope: ["pods", "services"],
          },
          {
            name: "ignored pod target",
            target_type: "pod",
            namespace: "prod",
            pod_name: "api-0",
            resource_scope: ["pods"],
          },
        ]),
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "导入巡检对象" }));

    expect(await screen.findByRole("button", { name: /使用 imported target/ })).toBeInTheDocument();
    expect(await screen.findByText("已导入 1 个名称空间巡检对象")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /使用 ignored pod target/ })).not.toBeInTheDocument();
  });

  it("preserves whitelist ignore entry in evidence details", async () => {
    render(<NamespaceInspectionPage />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.click(screen.getByRole("button", { name: "巡检名称空间" }));

    expect(await screen.findByRole("button", { name: "忽略此报错" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "忽略此报错" }));

    expect(await screen.findByRole("button", { name: "已忽略" })).toBeInTheDocument();
  });

  it("keeps template matching entry after ia rework", async () => {
    render(<NamespaceInspectionPage />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("Label Selector（可选）"), { target: { value: "app=demo-api" } });
    fireEvent.click(screen.getByRole("button", { name: "巡检名称空间" }));
    fireEvent.click(await screen.findByRole("button", { name: "模板匹配" }));

    expect(await screen.findByLabelText("当前范围模板匹配结果")).toBeInTheDocument();
    expect(await screen.findByText("API 启动失败模板")).toBeInTheDocument();
  });
});
