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
        created_at: "2026-07-11T10:00:00Z",
        updated_at: "2026-07-11T10:00:00Z",
      },
      {
        id: 2,
        name: "demo 名称空间对象",
        target_type: "namespace",
        namespace: "demo",
        pod_name: null,
        label_selector: "app=demo",
        resource_scope: ["pods", "services"],
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

      if (url.endsWith("/inspections/pod/run") && init?.method === "POST") {
        const payload = JSON.parse(String(init.body));
        return Promise.resolve(
          new Response(
            JSON.stringify({
              inspection_target: { type: "pod", namespace: payload.namespace, pod_name: payload.pod_name, resource_scope: ["pods"] },
              namespace: payload.namespace,
              health_status: "warning",
              executed_at: "2026-07-11T10:00:00Z",
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

  it("focuses on a single pod evidence chain", async () => {
    render(<PodInspectionPage />);

    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("Pod 名称"), { target: { value: "demo-api-1" } });
    fireEvent.click(screen.getByRole("button", { name: "运行 Pod 巡检" }));

    expect(await screen.findByText("单 Pod 巡检")).toBeInTheDocument();
    expect(await screen.findByText("demo-api-1")).toBeInTheDocument();
    expect(await screen.findByText("database connection refused")).toBeInTheDocument();
    expect(await screen.findByText("BackOff: restart container")).toBeInTheDocument();
  });

  it("can ignore a log hit through whitelist api", async () => {
    render(<PodInspectionPage />);

    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("Pod 名称"), { target: { value: "demo-api-1" } });
    fireEvent.click(screen.getByRole("button", { name: "运行 Pod 巡检" }));
    fireEvent.click(await screen.findByRole("button", { name: "忽略此报错" }));

    await waitFor(() => {
      expect(screen.getByText("已加入白名单，后续 Pod 巡检会自动忽略该命中")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "已忽略" })).toBeDisabled();
    });
  });

  it("only shows pod saved targets and supports pod target management", async () => {
    render(<PodInspectionPage />);

    expect(await screen.findByRole("button", { name: /使用 demo-api 固定排查/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /使用 demo 名称空间对象/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /使用 demo-api 固定排查/ }));
    expect(await screen.findByText("单 Pod 巡检")).toBeInTheDocument();
    expect(await screen.findByText("demo-api-1")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /编辑 demo-api 固定排查/ }));
    fireEvent.change(screen.getByLabelText("保存名称"), { target: { value: "demo-api 固定排查-更新" } });
    fireEvent.click(screen.getByRole("button", { name: "更新当前对象" }));
    expect(await screen.findByRole("button", { name: /使用 demo-api 固定排查-更新/ })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("保存名称"), { target: { value: "worker 巡检对象" } });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "prod" } });
    fireEvent.change(screen.getByLabelText("Pod 名称"), { target: { value: "worker-0" } });
    fireEvent.click(screen.getByRole("button", { name: "保存当前 Pod" }));
    expect(await screen.findByRole("button", { name: /使用 worker 巡检对象/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "刷新导出内容" }));
    expect((await screen.findByLabelText("导出内容") as HTMLTextAreaElement).value).toContain("\"target_type\": \"pod\"");

    fireEvent.change(screen.getByLabelText("导入内容"), {
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

    const importRequest = fetchMock.mock.calls.find(
      ([input, init]) => String(input).endsWith("/inspection-targets/import") && init?.method === "POST",
    );
    expect(importRequest).toBeDefined();
    expect(JSON.parse(String(importRequest?.[1]?.body))).toEqual([
      {
        name: "imported pod target",
        target_type: "pod",
        namespace: "prod",
        pod_name: "api-0",
        resource_scope: ["pods"],
      },
    ]);

    fireEvent.click(screen.getByRole("button", { name: /删除 imported pod target/ }));
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /使用 imported pod target/ })).not.toBeInTheDocument();
    });
  });

  it("does not call backend import when payload has no pod objects", async () => {
    render(<PodInspectionPage />);

    const importCallCountBefore = fetchMock.mock.calls.filter(
      ([input, init]) => String(input).endsWith("/inspection-targets/import") && init?.method === "POST",
    ).length;

    fireEvent.change(await screen.findByLabelText("导入内容"), {
      target: {
        value: JSON.stringify([
          {
            name: "namespace only target",
            target_type: "namespace",
            namespace: "prod",
            label_selector: "app=api",
            resource_scope: ["pods", "services"],
          },
        ]),
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "导入巡检对象" }));

    expect(await screen.findByText("导入内容不包含当前页面可导入的 Pod 巡检对象")).toBeInTheDocument();

    const importCallCountAfter = fetchMock.mock.calls.filter(
      ([input, init]) => String(input).endsWith("/inspection-targets/import") && init?.method === "POST",
    ).length;
    expect(importCallCountAfter).toBe(importCallCountBefore);
  });
});
