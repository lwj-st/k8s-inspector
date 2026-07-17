import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NamespaceInspectionPage } from "./NamespaceInspectionPage";

const fetchMock = vi.fn();

describe("NamespaceInspectionPage", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

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
        created_at: "2026-07-11T10:00:00Z",
        updated_at: "2026-07-11T10:00:00Z",
      },
      {
        id: 2,
        name: "demo-api Pod 对象",
        target_type: "pod",
        namespace: "demo",
        pod_name: "demo-api-1",
        label_selector: null,
        resource_scope: ["pods"],
        created_at: "2026-07-11T10:00:00Z",
        updated_at: "2026-07-11T10:00:00Z",
      },
    ];
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/inspection-targets") && (!init || init.method === undefined)) {
        return Promise.resolve(
          new Response(JSON.stringify(savedTargets), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/inspection-targets") && init?.method === "POST") {
        const payload = JSON.parse(String(init.body));
        const created = {
          id: savedTargets.length + 1,
          created_at: "2026-07-11T11:00:00Z",
          updated_at: "2026-07-11T11:00:00Z",
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
        savedTargets[index] = { ...savedTargets[index], ...payload, updated_at: "2026-07-11T12:00:00Z" };
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
          created_at: "2026-07-11T13:00:00Z",
          updated_at: "2026-07-11T13:00:00Z",
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
              executed_at: "2026-07-17T09:00:00Z",
              inspection_target: {
                type: "template",
                namespace: "demo",
                pod_name: null,
                label_selector: "app=demo-api",
                saved_target_id: null,
                template_id: null,
                resource_scope: ["pods"],
              },
              matches: [
                {
                  template_id: 1,
                  template_name: "API 启动失败模板",
                  reason: "启动依赖不可达",
                  suggestion: "检查数据库与网络",
                  command: null,
                  risk_note: null,
                  evidence: [{ type: "log_keyword", pod: "demo-api-1", matched_text: "database connection refused" }],
                  matched_conditions: [
                    {
                      target_ref: "api",
                      type: "log_keyword",
                      operator: "contains",
                      value: "connection refused",
                      matched: true,
                      evidence: [{ type: "log_keyword", pod: "demo-api-1", matched_text: "database connection refused" }],
                    },
                  ],
                  unmatched_conditions: [],
                },
              ],
              template_match_results: [
                {
                  template_id: 1,
                  template_name: "API 启动失败模板",
                  matched: true,
                  matched_conditions: [
                    {
                      target_ref: "api",
                      type: "log_keyword",
                      operator: "contains",
                      value: "connection refused",
                      matched: true,
                      evidence: [{ type: "log_keyword", pod: "demo-api-1", matched_text: "database connection refused" }],
                    },
                  ],
                  unmatched_conditions: [],
                  summary: "日志关键字已命中",
                  reason: "启动依赖不可达",
                  suggestion: "检查数据库与网络",
                  risk_note: null,
                  evidence_refs: [{ type: "log_keyword", pod: "demo-api-1", matched_text: "database connection refused" }],
                },
                {
                  template_id: 2,
                  template_name: "Worker 堵塞模板",
                  matched: false,
                  matched_conditions: [],
                  unmatched_conditions: [
                    {
                      target_ref: "worker",
                      type: "pod_status",
                      operator: "equals",
                      value: "Failed",
                      matched: false,
                      evidence: [],
                    },
                  ],
                  summary: "worker 当前没有 Failed 状态",
                  reason: "后台任务执行失败",
                  suggestion: "检查 worker 依赖",
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

      return Promise.resolve(
        new Response(
          JSON.stringify({
            inspection_target: {
              type: "namespace",
              namespace: "demo",
              label_selector: "app=demo-api",
              saved_target_id: null,
              resource_scope: ["pods", "services", "ingresses", "daemonsets", "secrets"],
            },
            namespace: "demo",
            health_status: "warning",
            executed_at: "2026-07-03T10:00:00Z",
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
                    keyword: "warmup timeout",
                    category: "startup",
                    severity: "warning",
                    source: "previous_log_summary",
                    matched_text: "warmup timeout",
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
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    });
  });

  it("shows pod evidence details after inspection", async () => {
    render(<NamespaceInspectionPage />);

    fireEvent.click(await screen.findByRole("button", { name: /使用 demo 全名称空间/ }));

    expect(await screen.findByText("异常 Pod")).toBeInTheDocument();
    expect(await screen.findByText("正常 / 已完成 Pod")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /demo-api-1/ })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /demo-worker-1/ })).toBeInTheDocument();
    expect(await screen.findByText("状态正常 / 已完成")).toBeInTheDocument();
    expect(await screen.findByText("证据详情")).toBeInTheDocument();
    expect(await screen.findByText("BackOff: restart container")).toBeInTheDocument();
    expect(await screen.findByText("database connection refused")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "忽略此报错" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "白名单已生效" })).toBeDisabled();
    expect(await screen.findByText("该命中已被白名单忽略")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "忽略此报错" }));

    expect((await screen.findAllByText("已加入白名单，后续巡检会自动忽略该命中")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /demo-worker-1/ }));

    expect(await screen.findByText("无事件")).toBeInTheDocument();
    expect(await screen.findByText("原始日志摘要")).toBeInTheDocument();
    expect(await screen.findByText("plain worker output without keyword hit")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "忽略此报错" })).not.toBeInTheDocument();
  });

  it("keeps log evidence visible for succeeded pods with non-whitelisted hits", async () => {
    fetchMock.mockReset();
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/inspection-targets") && (!init || init.method === undefined)) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              {
                id: 1,
                name: "demo 全名称空间",
                target_type: "namespace",
                namespace: "demo",
                label_selector: null,
                resource_scope: ["pods", "services", "ingresses", "daemonsets", "secrets"],
                created_at: "2026-07-11T10:00:00Z",
                updated_at: "2026-07-11T10:00:00Z",
              },
            ]),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/api/v1/inspections/namespace/run")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              inspection_target: {
                type: "namespace",
                namespace: "demo",
                label_selector: null,
                saved_target_id: null,
                resource_scope: ["pods", "services", "ingresses", "daemonsets", "secrets"],
              },
              namespace: "demo",
              health_status: "warning",
              executed_at: "2026-07-17T10:00:00Z",
              evidence_bundles: [],
              pods: [
                {
                  name: "job-cleanup-1",
                  status: "Succeeded",
                  restarts: 0,
                  node_name: "node-b",
                  containers: [{ name: "cleanup", restart_count: 0, state: "terminated", reason: "Completed" }],
                  events: [],
                  describe_summary: "任务执行完成",
                  log_summary: "cleanup checksum mismatch",
                  previous_log_summary: null,
                  log_hits: [
                    {
                      keyword: "checksum mismatch",
                      category: "data",
                      severity: "warning",
                      source: "log_summary",
                      matched_text: "cleanup checksum mismatch",
                      container_name: "cleanup",
                      whitelisted: false,
                      whitelist_rule_id: null,
                    },
                  ],
                  resource_usage: { cpu: "10m", memory: "20Mi" },
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

    render(<NamespaceInspectionPage />);

    fireEvent.click(await screen.findByRole("button", { name: /使用 demo 全名称空间/ }));

    expect(await screen.findByText("正常 / 已完成 Pod")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /job-cleanup-1/ }));

    expect(await screen.findByText("关键字命中")).toBeInTheDocument();
    expect(await screen.findByText("cleanup checksum mismatch")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "忽略此报错" })).toBeInTheDocument();
  });

  it("runs template matching inside namespace inspection and renders matched and unmatched templates", async () => {
    render(<NamespaceInspectionPage />);

    fireEvent.click(await screen.findByRole("button", { name: /使用 demo 全名称空间/ }));
    fireEvent.click(await screen.findByRole("button", { name: "模板匹配" }));

    const diagnosisRequest = await waitFor(() =>
      fetchMock.mock.calls.find(
        ([input, init]) => String(input).endsWith("/diagnoses/run") && init?.method === "POST",
      ),
    );

    expect(diagnosisRequest).toBeDefined();
    expect(JSON.parse(String(diagnosisRequest?.[1]?.body))).toEqual({
      namespace: "demo",
      scope: "app=demo-api",
    });

    expect(await screen.findByText("当前范围模板匹配结果")).toBeInTheDocument();
    expect(await screen.findByText("API 启动失败模板")).toBeInTheDocument();
    expect(await screen.findByText("Worker 堵塞模板")).toBeInTheDocument();
    expect(await screen.findByText(/对象组 api 在日志中包含 connection refused/)).toBeInTheDocument();
    expect(await screen.findByText(/对象组 worker 的 Pod 状态等于 Failed/)).toBeInTheDocument();
    expect(await screen.findByText("worker 当前没有 Failed 状态")).toBeInTheDocument();
  });

  it("allows saving the current namespace target", async () => {
    render(<NamespaceInspectionPage />);

    fireEvent.change(await screen.findByLabelText("保存为"), {
      target: { value: "demo-api 启动排查" },
    });
    fireEvent.change(screen.getByLabelText("名称空间"), {
      target: { value: "demo" },
    });
    fireEvent.change(screen.getByLabelText(/Label Selector/), {
      target: { value: "app=demo-api" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存当前范围" }));

    expect(await screen.findByRole("button", { name: /使用 demo-api 启动排查/ })).toBeInTheDocument();
  });

  it("blocks saving namespace target without namespace context", async () => {
    render(<NamespaceInspectionPage />);

    fireEvent.change(await screen.findByLabelText("保存为"), {
      target: { value: "缺少名称空间" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存当前范围" }));

    expect(await screen.findByText("请先填写名称空间，或先完成一次名称空间巡检后再保存")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([input, init]) => String(input).endsWith("/inspection-targets") && init?.method === "POST"),
    ).toBe(false);
  });

  it("shows empty state when there are no saved targets", async () => {
    fetchMock.mockReset();
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/inspection-targets")) {
        return Promise.resolve(
          new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    render(<NamespaceInspectionPage />);

    expect(await screen.findByText("暂无保存对象，保存当前巡检范围后可复用。")).toBeInTheDocument();
    expect(screen.queryByText("内置常用范围")).not.toBeInTheDocument();
  });

  it("does not show pod saved targets in namespace page", async () => {
    render(<NamespaceInspectionPage />);

    expect(await screen.findByRole("button", { name: /使用 demo 全名称空间/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /使用 demo-api Pod 对象/ })).not.toBeInTheDocument();
  });

  it("allows updating, importing and deleting saved namespace targets", async () => {
    render(<NamespaceInspectionPage />);

    fireEvent.click(await screen.findByRole("button", { name: /编辑 demo 全名称空间/ }));
    fireEvent.change(screen.getByLabelText("保存为"), {
      target: { value: "demo 全名称空间-更新" },
    });
    fireEvent.click(screen.getByRole("button", { name: "更新当前对象" }));

    expect(await screen.findByRole("button", { name: /使用 demo 全名称空间-更新/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "刷新导出内容" }));
    expect((await screen.findByLabelText("导出内容") as HTMLTextAreaElement).value).toContain("demo 全名称空间-更新");

    fireEvent.change(screen.getByLabelText("导入内容"), {
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

    const importRequest = fetchMock.mock.calls.find(
      ([input, init]) => String(input).endsWith("/inspection-targets/import") && init?.method === "POST",
    );
    expect(importRequest).toBeDefined();
    expect(JSON.parse(String(importRequest?.[1]?.body))).toEqual([
      {
        name: "imported target",
        target_type: "namespace",
        namespace: "prod",
        label_selector: "app=api",
        resource_scope: ["pods", "services"],
      },
    ]);

    fireEvent.click(screen.getByRole("button", { name: /删除 imported target/ }));
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /使用 imported target/ })).not.toBeInTheDocument();
    });
  });

  it("does not call backend import when payload has no namespace objects", async () => {
    render(<NamespaceInspectionPage />);

    const importCallCountBefore = fetchMock.mock.calls.filter(
      ([input, init]) => String(input).endsWith("/inspection-targets/import") && init?.method === "POST",
    ).length;

    fireEvent.change(await screen.findByLabelText("导入内容"), {
      target: {
        value: JSON.stringify([
          {
            name: "pod only target",
            target_type: "pod",
            namespace: "prod",
            pod_name: "api-0",
            resource_scope: ["pods"],
          },
        ]),
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "导入巡检对象" }));

    expect(await screen.findByText("导入内容不包含当前页面可导入的名称空间对象")).toBeInTheDocument();

    const importCallCountAfter = fetchMock.mock.calls.filter(
      ([input, init]) => String(input).endsWith("/inspection-targets/import") && init?.method === "POST",
    ).length;
    expect(importCallCountAfter).toBe(importCallCountBefore);
  });
});
