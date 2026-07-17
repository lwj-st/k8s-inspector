import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AutoInspectionPage } from "./AutoInspectionPage";

const fetchMock = vi.fn();

describe("AutoInspectionPage", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
  });

  it("loads namespaces and supports search plus multi select", async () => {
    fetchMock.mockImplementation(async (input: string | URL | Request) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return new Response(
          JSON.stringify({
            executed_at: "2026-07-12T10:00:00Z",
            namespaces: [
              {
                name: "default",
                status: "healthy",
                pod_count: 12,
                abnormal_pod_count: 0,
                last_inspected_at: null,
                labels: {},
                abnormal_categories: [],
              },
              {
                name: "prod-core",
                status: "warning",
                pod_count: 18,
                abnormal_pod_count: 2,
                last_inspected_at: "2026-07-12T09:30:00Z",
                labels: { env: "prod" },
                abnormal_categories: ["pod_status"],
              },
              {
                name: "kube-system",
                status: "healthy",
                pod_count: 9,
                abnormal_pod_count: 0,
                last_inspected_at: "2026-07-12T09:20:00Z",
                labels: {},
                abnormal_categories: [],
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    render(<AutoInspectionPage />);

    expect(await screen.findByText("名称空间列表")).toBeInTheDocument();
    expect(screen.getByText("default")).toBeInTheDocument();
    expect(screen.getByText("prod-core")).toBeInTheDocument();
    expect(screen.getByText("kube-system")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("搜索名称空间"), { target: { value: "prod" } });
    expect(screen.getByText("prod-core")).toBeInTheDocument();
    expect(screen.queryByText("default")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "全选当前结果" }));
    expect(screen.getByRole("checkbox", { name: "选择 prod-core" })).toBeChecked();

    fireEvent.change(screen.getByLabelText("搜索名称空间"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "选择 default" }));
    expect(screen.getByRole("checkbox", { name: "选择 prod-core" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "选择 default" })).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: "取消当前结果" }));
    await waitFor(() => {
      expect(screen.getByRole("checkbox", { name: "选择 prod-core" })).not.toBeChecked();
      expect(screen.getByRole("checkbox", { name: "选择 default" })).not.toBeChecked();
    });
  });

  it("shows empty state when no namespaces are returned", async () => {
    fetchMock.mockImplementation(async (input: string | URL | Request) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return new Response(
          JSON.stringify({
            executed_at: "2026-07-12T10:00:00Z",
            namespaces: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    render(<AutoInspectionPage />);

    expect(await screen.findByText("当前集群没有可用名称空间。")).toBeInTheDocument();
  });

  it("shows retry on failure and can reload", async () => {
    let attempt = 0;
    fetchMock.mockImplementation(async (input: string | URL | Request) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
      if (url.endsWith("/api/v1/discovery/namespaces")) {
        attempt += 1;
        if (attempt === 1) {
          throw new Error("Request failed: 500");
        }
        return new Response(
          JSON.stringify({
            executed_at: "2026-07-12T10:01:00Z",
            namespaces: [
              {
                name: "prod-core",
                status: "warning",
                pod_count: 18,
                abnormal_pod_count: 2,
                last_inspected_at: "2026-07-12T09:30:00Z",
                labels: {},
                abnormal_categories: ["pod_status"],
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    render(<AutoInspectionPage />);

    expect(await screen.findByText("名称空间读取失败：Request failed: 500")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "重试" }));

    expect(await screen.findByText("prod-core")).toBeInTheDocument();
  });

  it("keeps failure state when retry still fails", async () => {
    let attempt = 0;
    fetchMock.mockImplementation(async (input: string | URL | Request) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
      if (url.endsWith("/api/v1/discovery/namespaces")) {
        attempt += 1;
        throw new Error(attempt === 1 ? "Request failed: 500" : "Request failed: 503");
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    render(<AutoInspectionPage />);

    expect(await screen.findByText("名称空间读取失败：Request failed: 500")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "重试" }));

    expect(await screen.findByText("名称空间读取失败：Request failed: 503")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
  });

  it("runs selected namespaces and shows batch summary", async () => {
    fetchMock.mockImplementation(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);

      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return new Response(
          JSON.stringify({
            executed_at: "2026-07-13T10:00:00Z",
            namespaces: [
              {
                name: "default",
                status: "healthy",
                pod_count: 12,
                abnormal_pod_count: 0,
                last_inspected_at: null,
                labels: {},
                abnormal_categories: [],
              },
              {
                name: "prod-core",
                status: "warning",
                pod_count: 18,
                abnormal_pod_count: 2,
                last_inspected_at: "2026-07-13T09:30:00Z",
                labels: {},
                abnormal_categories: ["pod_status"],
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (url.endsWith("/api/v1/inspections/namespaces/run") && init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toEqual({
          namespaces: ["prod-core"],
          all_namespaces: false,
        });
        return new Response(
          JSON.stringify({
            executed_at: "2026-07-13T10:02:00Z",
            all_namespaces: false,
            requested_namespaces: ["prod-core"],
            results: [
              {
                summary: {
                  name: "prod-core",
                  status: "warning",
                  pod_count: 18,
                  abnormal_pod_count: 2,
                  last_inspected_at: "2026-07-13T10:02:00Z",
                  labels: {},
                  abnormal_categories: ["pod_status", "event"],
                },
                health_status: "warning",
                detail_target: { type: "namespace", namespace: "prod-core", resource_scope: ["pods"] },
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    render(<AutoInspectionPage />);

    fireEvent.click(await screen.findByRole("checkbox", { name: "选择 prod-core" }));
    fireEvent.click(screen.getByRole("button", { name: "巡检选中" }));

    expect(await screen.findByText("批量巡检摘要")).toBeInTheDocument();
    expect(await screen.findByText("本次执行：巡检选中 1 个名称空间")).toBeInTheDocument();
    expect(await screen.findByText("Pod 状态")).toBeInTheDocument();
    expect(await screen.findByText("事件")).toBeInTheDocument();
  });

  it("runs all namespaces and disables buttons while running", async () => {
    const batchResolver: { current: ((value: Response) => void) | null } = { current: null };
    fetchMock.mockImplementation((input: string | URL | Request, init?: RequestInit) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);

      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              executed_at: "2026-07-13T10:00:00Z",
              namespaces: [
                {
                  name: "default",
                  status: "healthy",
                  pod_count: 12,
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

      if (url.endsWith("/api/v1/inspections/namespaces/run") && init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toEqual({
          namespaces: [],
          all_namespaces: true,
        });
        return new Promise<Response>((resolve) => {
          batchResolver.current = resolve;
        });
      }

      return Promise.reject(new Error(`Unexpected request: ${url}`));
    });

    render(<AutoInspectionPage />);

    const runAllButton = await screen.findByRole("button", { name: "巡检全部" });
    fireEvent.click(runAllButton);

    const loadingButtons = screen.getAllByRole("button", { name: "巡检中..." });
    expect(loadingButtons).toHaveLength(2);
    expect(loadingButtons[0]).toBeDisabled();
    expect(loadingButtons[1]).toBeDisabled();

    if (batchResolver.current) {
      batchResolver.current(
        new Response(
          JSON.stringify({
            executed_at: "2026-07-13T10:05:00Z",
            all_namespaces: true,
            requested_namespaces: [],
            results: [
              {
                summary: {
                  name: "default",
                  status: "healthy",
                  pod_count: 12,
                  abnormal_pod_count: 0,
                  last_inspected_at: "2026-07-13T10:05:00Z",
                  labels: {},
                  abnormal_categories: [],
                },
                health_status: "healthy",
                detail_target: { type: "namespace", namespace: "default", resource_scope: ["pods"] },
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    }

    expect(await screen.findByText("本次执行：巡检全部名称空间")).toBeInTheDocument();
  });

  it("shows namespace level error without turning it into global failure", async () => {
    fetchMock.mockImplementation(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);

      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return new Response(
          JSON.stringify({
            executed_at: "2026-07-13T10:00:00Z",
            namespaces: [
              {
                name: "broken-ns",
                status: "unknown",
                pod_count: 0,
                abnormal_pod_count: 0,
                last_inspected_at: null,
                labels: {},
                abnormal_categories: [],
              },
              {
                name: "prod-core",
                status: "warning",
                pod_count: 18,
                abnormal_pod_count: 2,
                last_inspected_at: null,
                labels: {},
                abnormal_categories: ["pod_status"],
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (url.endsWith("/api/v1/inspections/namespaces/run") && init?.method === "POST") {
        return new Response(
          JSON.stringify({
            executed_at: "2026-07-13T10:06:00Z",
            all_namespaces: true,
            requested_namespaces: [],
            results: [
              {
                summary: {
                  name: "broken-ns",
                  status: "error",
                  pod_count: 0,
                  abnormal_pod_count: 0,
                  last_inspected_at: null,
                  labels: {},
                  abnormal_categories: [],
                },
                health_status: "error",
                detail_target: { type: "namespace", namespace: "broken-ns", resource_scope: ["pods"] },
              },
              {
                summary: {
                  name: "prod-core",
                  status: "warning",
                  pod_count: 18,
                  abnormal_pod_count: 2,
                  last_inspected_at: "2026-07-13T10:06:00Z",
                  labels: {},
                  abnormal_categories: ["pod_status"],
                },
                health_status: "warning",
                detail_target: { type: "namespace", namespace: "prod-core", resource_scope: ["pods"] },
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    render(<AutoInspectionPage />);

    fireEvent.click(await screen.findByRole("button", { name: "巡检全部" }));

    expect(await screen.findByText("该名称空间巡检失败")).toBeInTheDocument();
    expect(screen.queryByText(/批量巡检请求失败/)).not.toBeInTheDocument();
    expect((await screen.findAllByText("prod-core")).length).toBeGreaterThan(0);
  });

  it("shows summary metrics and localized abnormal categories in sorted order", async () => {
    fetchMock.mockImplementation(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);

      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return new Response(
          JSON.stringify({
            executed_at: "2026-07-13T10:00:00Z",
            namespaces: [
              {
                name: "healthy-ns",
                status: "healthy",
                pod_count: 6,
                abnormal_pod_count: 0,
                last_inspected_at: null,
                labels: {},
                abnormal_categories: [],
              },
              {
                name: "warning-ns",
                status: "warning",
                pod_count: 12,
                abnormal_pod_count: 2,
                last_inspected_at: null,
                labels: {},
                abnormal_categories: ["pod_status", "event"],
              },
              {
                name: "error-ns",
                status: "error",
                pod_count: 0,
                abnormal_pod_count: 0,
                last_inspected_at: null,
                labels: {},
                abnormal_categories: [],
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (url.endsWith("/api/v1/inspections/namespaces/run") && init?.method === "POST") {
        return new Response(
          JSON.stringify({
            executed_at: "2026-07-13T10:12:00Z",
            all_namespaces: true,
            requested_namespaces: [],
            results: [
              {
                summary: {
                  name: "healthy-ns",
                  status: "healthy",
                  pod_count: 6,
                  abnormal_pod_count: 0,
                  last_inspected_at: "2026-07-13T10:12:00Z",
                  labels: {},
                  abnormal_categories: [],
                },
                health_status: "healthy",
                detail_target: { type: "namespace", namespace: "healthy-ns", resource_scope: ["pods"] },
              },
              {
                summary: {
                  name: "warning-ns",
                  status: "warning",
                  pod_count: 12,
                  abnormal_pod_count: 2,
                  last_inspected_at: "2026-07-13T10:12:00Z",
                  labels: {},
                  abnormal_categories: ["pod_status", "event", "log_keyword", "related_object", "container_status"],
                },
                health_status: "warning",
                detail_target: { type: "namespace", namespace: "warning-ns", resource_scope: ["pods"] },
              },
              {
                summary: {
                  name: "error-ns",
                  status: "error",
                  pod_count: 0,
                  abnormal_pod_count: 0,
                  last_inspected_at: null,
                  labels: {},
                  abnormal_categories: [],
                },
                health_status: "error",
                detail_target: { type: "namespace", namespace: "error-ns", resource_scope: ["pods"] },
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    const { container } = render(<AutoInspectionPage />);

    fireEvent.click(await screen.findByRole("button", { name: "巡检全部" }));
    expect(await screen.findByText("批量巡检摘要")).toBeInTheDocument();

    const inspectedMetric = screen.getByText("巡检名称空间").closest("article");
    const warningMetric = screen.getByText("告警名称空间").closest("article");
    const errorMetric = screen.getByText("失败名称空间").closest("article");

    expect(inspectedMetric).not.toBeNull();
    expect(warningMetric).not.toBeNull();
    expect(errorMetric).not.toBeNull();
    expect(within(inspectedMetric as HTMLElement).getByText("3")).toBeInTheDocument();
    expect(within(warningMetric as HTMLElement).getByText("1")).toBeInTheDocument();
    expect(within(errorMetric as HTMLElement).getByText("1")).toBeInTheDocument();

    expect(screen.getByText("Pod 状态")).toBeInTheDocument();
    expect(screen.getByText("容器状态")).toBeInTheDocument();
    expect(screen.getByText("事件")).toBeInTheDocument();
    expect(screen.getByText("日志关键字")).toBeInTheDocument();
    expect(screen.getByText("关联对象")).toBeInTheDocument();
    expect(screen.getAllByText("无异常分类")).toHaveLength(2);

    const cards = Array.from(container.querySelectorAll(".batch-summary-card"));
    expect(cards).toHaveLength(3);
    expect(cards[0]).toHaveAttribute("aria-label", "批量结果 error-ns");
    expect(cards[1]).toHaveAttribute("aria-label", "批量结果 warning-ns");
    expect(cards[2]).toHaveAttribute("aria-label", "批量结果 healthy-ns");
  });

  it("shows global error when batch request fails", async () => {
    fetchMock.mockImplementation(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);

      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return new Response(
          JSON.stringify({
            executed_at: "2026-07-13T10:00:00Z",
            namespaces: [
              {
                name: "default",
                status: "healthy",
                pod_count: 12,
                abnormal_pod_count: 0,
                last_inspected_at: null,
                labels: {},
                abnormal_categories: [],
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (url.endsWith("/api/v1/inspections/namespaces/run") && init?.method === "POST") {
        throw new Error("Request failed: 500");
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    render(<AutoInspectionPage />);

    fireEvent.click(await screen.findByRole("button", { name: "巡检全部" }));

    expect(await screen.findByText("批量巡检请求失败：Request failed: 500")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试批量巡检" })).toBeInTheDocument();
  });

  it("retries failed run-all with the original all_namespaces payload", async () => {
    let batchAttempt = 0;
    const batchPayloads: Array<{ namespaces: string[]; all_namespaces: boolean }> = [];

    fetchMock.mockImplementation(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);

      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return new Response(
          JSON.stringify({
            executed_at: "2026-07-13T10:00:00Z",
            namespaces: [
              {
                name: "default",
                status: "healthy",
                pod_count: 12,
                abnormal_pod_count: 0,
                last_inspected_at: null,
                labels: {},
                abnormal_categories: [],
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (url.endsWith("/api/v1/inspections/namespaces/run") && init?.method === "POST") {
        batchAttempt += 1;
        batchPayloads.push(JSON.parse(String(init.body)));
        if (batchAttempt === 1) {
          throw new Error("Request failed: 500");
        }
        return new Response(
          JSON.stringify({
            executed_at: "2026-07-13T10:10:00Z",
            all_namespaces: true,
            requested_namespaces: [],
            results: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    render(<AutoInspectionPage />);

    fireEvent.click(await screen.findByRole("button", { name: "巡检全部" }));
    expect(await screen.findByText("批量巡检请求失败：Request failed: 500")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "重试批量巡检" }));
    await screen.findByText("本次执行：巡检全部名称空间");

    expect(batchPayloads).toEqual([
      { namespaces: [], all_namespaces: true },
      { namespaces: [], all_namespaces: true },
    ]);
  });

  it("retries failed run-selected with the original selected namespaces payload", async () => {
    let batchAttempt = 0;
    const batchPayloads: Array<{ namespaces: string[]; all_namespaces: boolean }> = [];

    fetchMock.mockImplementation(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);

      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return new Response(
          JSON.stringify({
            executed_at: "2026-07-13T10:00:00Z",
            namespaces: [
              {
                name: "prod-core",
                status: "warning",
                pod_count: 18,
                abnormal_pod_count: 2,
                last_inspected_at: null,
                labels: {},
                abnormal_categories: ["pod_status"],
              },
              {
                name: "kube-system",
                status: "healthy",
                pod_count: 9,
                abnormal_pod_count: 0,
                last_inspected_at: null,
                labels: {},
                abnormal_categories: [],
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (url.endsWith("/api/v1/inspections/namespaces/run") && init?.method === "POST") {
        batchAttempt += 1;
        batchPayloads.push(JSON.parse(String(init.body)));
        if (batchAttempt === 1) {
          throw new Error("Request failed: 500");
        }
        return new Response(
          JSON.stringify({
            executed_at: "2026-07-13T10:11:00Z",
            all_namespaces: false,
            requested_namespaces: ["prod-core", "kube-system"],
            results: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    render(<AutoInspectionPage />);

    fireEvent.click(await screen.findByRole("checkbox", { name: "选择 prod-core" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "选择 kube-system" }));
    fireEvent.click(screen.getByRole("button", { name: "巡检选中" }));
    expect(await screen.findByText("批量巡检请求失败：Request failed: 500")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "重试批量巡检" }));
    await screen.findByText("本次执行：巡检选中 2 个名称空间");

    expect(batchPayloads).toEqual([
      { namespaces: ["prod-core", "kube-system"], all_namespaces: false },
      { namespaces: ["prod-core", "kube-system"], all_namespaces: false },
    ]);
  });

  it("triggers manual template diagnosis and renders matched plus unmatched conditions", async () => {
    fetchMock.mockImplementation(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);

      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return new Response(JSON.stringify({
          executed_at: "2026-07-17T17:00:00Z",
          namespaces: [{ name: "prod-core", status: "warning", pod_count: 2, abnormal_pod_count: 1, last_inspected_at: null, labels: {}, abnormal_categories: ["pod_status"] }],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }

      if (url.endsWith("/api/v1/inspections/namespaces/run") && init?.method === "POST") {
        return new Response(JSON.stringify({
          executed_at: "2026-07-17T17:01:00Z",
          all_namespaces: false,
          requested_namespaces: ["prod-core"],
          results: [{
            summary: { name: "prod-core", status: "warning", pod_count: 2, abnormal_pod_count: 1, last_inspected_at: null, labels: {}, abnormal_categories: ["pod_status"] },
            health_status: "warning",
            detail_target: { type: "namespace", namespace: "prod-core", resource_scope: ["pods"] },
          }],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }

      if (url.endsWith("/api/v1/diagnoses/run") && init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toEqual({});
        return new Response(JSON.stringify({
          status: "matched",
          namespace: null,
          direction: "template_check",
          scope: null,
          executed_at: "2026-07-17T17:02:00Z",
          inspection_target: { type: "template", namespace: null, pod_name: null, label_selector: null, saved_target_id: null, template_id: null, resource_scope: ["pods"] },
          matches: [],
          template_match_results: [
            {
              template_id: 1,
              template_name: "CrashLoop 模板",
              matched: true,
              matched_conditions: [
                { target_ref: "api", condition_type: "pod_status", operator: "in", expected_value: ["CrashLoopBackOff"], enabled: true },
              ],
              unmatched_conditions: [],
              summary: "启动异常命中",
              reason: "依赖启动失败",
              suggestion: "检查下游服务",
              risk_note: null,
              evidence_refs: [{ type: "pod_status", pods: ["demo-api-0"], value: ["CrashLoopBackOff"] }],
            },
            {
              template_id: 2,
              template_name: "Redis 连接失败模板",
              matched: false,
              matched_conditions: [],
              unmatched_conditions: [
                { target_ref: "redis", condition_type: "log_keyword", operator: "contains", expected_value: "redis timeout", enabled: true },
              ],
              summary: "当前没有发现 redis timeout 日志",
              reason: "Redis 不可达",
              suggestion: "检查 redis 服务",
              risk_note: null,
              evidence_refs: [],
            },
          ],
          evidence_summary: [{ type: "namespace", value: "prod-core" }],
          llm_supplement: null,
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    render(<AutoInspectionPage />);

    fireEvent.click(await screen.findByRole("checkbox", { name: "选择 prod-core" }));
    fireEvent.click(screen.getByRole("button", { name: "巡检选中" }));
    await screen.findByText("批量巡检摘要");

    fireEvent.click(screen.getByRole("button", { name: "运行模板匹配" }));

    const drawer = await screen.findByRole("complementary", { name: "模板匹配结果" });
    expect(within(drawer).getByText("故障模板手动匹配")).toBeInTheDocument();
    expect(within(drawer).getByText("已命中模板")).toBeInTheDocument();
    expect(within(drawer).getByText("未命中模板")).toBeInTheDocument();
    expect(within(drawer).getByText("CrashLoop 模板")).toBeInTheDocument();
    expect(within(drawer).getByText("Redis 连接失败模板")).toBeInTheDocument();
    expect(within(drawer).getByText(/对象组 api 的 Pod 状态/)).toBeInTheDocument();
    expect(within(drawer).getByText(/对象组 redis 在日志中包含 redis timeout/)).toBeInTheDocument();
  });

  it("shows diagnosis loading state in auto inspection page", async () => {
    const diagnosisResolver: { current: ((value: Response) => void) | null } = { current: null };

    fetchMock.mockImplementation((input: string | URL | Request, init?: RequestInit) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);

      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return Promise.resolve(new Response(JSON.stringify({
          executed_at: "2026-07-17T17:10:00Z",
          namespaces: [{ name: "prod-core", status: "warning", pod_count: 1, abnormal_pod_count: 1, last_inspected_at: null, labels: {}, abnormal_categories: ["pod_status"] }],
        }), { status: 200, headers: { "Content-Type": "application/json" } }));
      }

      if (url.endsWith("/api/v1/inspections/namespaces/run")) {
        return Promise.resolve(new Response(JSON.stringify({
          executed_at: "2026-07-17T17:11:00Z",
          all_namespaces: false,
          requested_namespaces: ["prod-core"],
          results: [{
            summary: { name: "prod-core", status: "warning", pod_count: 1, abnormal_pod_count: 1, last_inspected_at: null, labels: {}, abnormal_categories: ["pod_status"] },
            health_status: "warning",
            detail_target: { type: "namespace", namespace: "prod-core", resource_scope: ["pods"] },
          }],
        }), { status: 200, headers: { "Content-Type": "application/json" } }));
      }

      if (url.endsWith("/api/v1/diagnoses/run")) {
        return new Promise<Response>((resolve) => {
          diagnosisResolver.current = resolve;
        });
      }

      return Promise.reject(new Error(`Unexpected request: ${url}`));
    });

    render(<AutoInspectionPage />);

    fireEvent.click(await screen.findByRole("checkbox", { name: "选择 prod-core" }));
    fireEvent.click(screen.getByRole("button", { name: "巡检选中" }));
    await screen.findByText("批量巡检摘要");
    fireEvent.click(screen.getByRole("button", { name: "运行模板匹配" }));

    const drawer = await screen.findByRole("complementary", { name: "模板匹配结果" });
    expect(within(drawer).getByText("模板匹配中...")).toBeInTheDocument();

    diagnosisResolver.current?.(new Response(JSON.stringify({
      status: "unmatched",
      namespace: null,
      direction: "template_check",
      scope: null,
      executed_at: "2026-07-17T17:12:00Z",
      inspection_target: { type: "template", namespace: null, pod_name: null, label_selector: null, saved_target_id: null, template_id: null, resource_scope: ["pods"] },
      matches: [],
      template_match_results: [],
      evidence_summary: [],
      llm_supplement: null,
    }), { status: 200, headers: { "Content-Type": "application/json" } }));

    await waitFor(() => {
      expect(within(drawer).queryByText("模板匹配中...")).not.toBeInTheDocument();
    });
  });

  it("shows diagnosis failure state in auto inspection page", async () => {
    fetchMock.mockImplementation(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);

      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return new Response(JSON.stringify({
          executed_at: "2026-07-17T17:20:00Z",
          namespaces: [{ name: "prod-core", status: "warning", pod_count: 1, abnormal_pod_count: 1, last_inspected_at: null, labels: {}, abnormal_categories: ["pod_status"] }],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }

      if (url.endsWith("/api/v1/inspections/namespaces/run")) {
        return new Response(JSON.stringify({
          executed_at: "2026-07-17T17:21:00Z",
          all_namespaces: false,
          requested_namespaces: ["prod-core"],
          results: [{
            summary: { name: "prod-core", status: "warning", pod_count: 1, abnormal_pod_count: 1, last_inspected_at: null, labels: {}, abnormal_categories: ["pod_status"] },
            health_status: "warning",
            detail_target: { type: "namespace", namespace: "prod-core", resource_scope: ["pods"] },
          }],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }

      if (url.endsWith("/api/v1/diagnoses/run")) {
        throw new Error("Request failed: 500");
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    render(<AutoInspectionPage />);

    fireEvent.click(await screen.findByRole("checkbox", { name: "选择 prod-core" }));
    fireEvent.click(screen.getByRole("button", { name: "巡检选中" }));
    await screen.findByText("批量巡检摘要");
    fireEvent.click(screen.getByRole("button", { name: "运行模板匹配" }));

    const drawer = await screen.findByRole("complementary", { name: "模板匹配结果" });
    expect(await within(drawer).findByText("模板匹配失败：Request failed: 500")).toBeInTheDocument();
  });

  it("shows empty diagnosis state in auto inspection page when no template matches are returned", async () => {
    fetchMock.mockImplementation(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);

      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return new Response(JSON.stringify({
          executed_at: "2026-07-17T17:30:00Z",
          namespaces: [{ name: "prod-core", status: "warning", pod_count: 1, abnormal_pod_count: 1, last_inspected_at: null, labels: {}, abnormal_categories: ["pod_status"] }],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }

      if (url.endsWith("/api/v1/inspections/namespaces/run")) {
        return new Response(JSON.stringify({
          executed_at: "2026-07-17T17:31:00Z",
          all_namespaces: false,
          requested_namespaces: ["prod-core"],
          results: [{
            summary: { name: "prod-core", status: "warning", pod_count: 1, abnormal_pod_count: 1, last_inspected_at: null, labels: {}, abnormal_categories: ["pod_status"] },
            health_status: "warning",
            detail_target: { type: "namespace", namespace: "prod-core", resource_scope: ["pods"] },
          }],
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }

      if (url.endsWith("/api/v1/diagnoses/run")) {
        return new Response(JSON.stringify({
          status: "unmatched",
          namespace: null,
          direction: "template_check",
          scope: null,
          executed_at: "2026-07-17T17:32:00Z",
          inspection_target: { type: "template", namespace: null, pod_name: null, label_selector: null, saved_target_id: null, template_id: null, resource_scope: ["pods"] },
          matches: [],
          template_match_results: [],
          evidence_summary: [],
          llm_supplement: null,
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    render(<AutoInspectionPage />);

    fireEvent.click(await screen.findByRole("checkbox", { name: "选择 prod-core" }));
    fireEvent.click(screen.getByRole("button", { name: "巡检选中" }));
    await screen.findByText("批量巡检摘要");
    fireEvent.click(screen.getByRole("button", { name: "运行模板匹配" }));

    const drawer = await screen.findByRole("complementary", { name: "模板匹配结果" });
    expect(await within(drawer).findByText("本次未命中任何故障模板。")).toBeInTheDocument();
  });

  it("opens namespace evidence with detail_target namespace and label selector, then prioritizes abnormal pods", async () => {
    fetchMock.mockImplementation(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);

      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return new Response(JSON.stringify({ executed_at: "2026-07-14T10:00:00Z", namespaces: [{
          name: "prod-core", status: "warning", pod_count: 2, abnormal_pod_count: 1,
          last_inspected_at: null, labels: {}, abnormal_categories: ["pod_status", "event"],
        }] }), { status: 200 });
      }
      if (url.endsWith("/api/v1/inspections/namespaces/run")) {
        return new Response(JSON.stringify({
          executed_at: "2026-07-14T10:01:00Z", all_namespaces: false, requested_namespaces: ["prod-core"],
          results: [{
            summary: { name: "summary-name", status: "warning", pod_count: 2, abnormal_pod_count: 1,
              last_inspected_at: null, labels: {}, abnormal_categories: ["pod_status", "event"] },
            health_status: "warning",
            detail_target: { type: "namespace", namespace: "detail-name", label_selector: "app=api", resource_scope: ["pods"] },
          }],
        }), { status: 200 });
      }
      if (url.endsWith("/api/v1/inspections/namespace/run")) {
        expect(JSON.parse(String(init?.body))).toEqual({ namespace: "detail-name", label_selector: "app=api" });
        return new Response(JSON.stringify({
          inspection_target: { type: "namespace", namespace: "detail-name", label_selector: "app=api", resource_scope: ["pods"] },
          namespace: "detail-name", label_selector: "app=api", health_status: "warning", executed_at: "2026-07-14T10:01:30Z",
          evidence_bundles: [],
          services: [{ name: "api", status: "healthy", summary: "服务正常" }],
          ingresses: [{ name: "public", status: "healthy", summary: "入口正常" }],
          tls_secrets: [],
          daemonsets: [],
          pods: [
            {
              name: "broken-api", status: "CrashLoopBackOff", node_name: "node-a", restarts: 4,
              containers: [{ name: "api", restart_count: 4, state: "waiting", reason: "CrashLoopBackOff" }],
              events: ["Back-off restarting failed container"], describe_summary: "健康检查失败",
              log_summary: null, previous_log_summary: null,
              log_hits: [{ keyword: "connection refused", category: "dependency", severity: "warning", source: "current_log", matched_text: "database connection refused", container_name: "api", whitelisted: false }],
              resource_usage: {}, related_resources: [{ kind: "Service", name: "api", status: "healthy" }],
            },
            {
              name: "healthy-api", status: "Running", node_name: "node-b", restarts: 0,
              containers: [{ name: "api", restart_count: 0, state: "running", reason: null }],
              events: [], describe_summary: "运行正常", log_summary: null, previous_log_summary: null,
              log_hits: [], resource_usage: {}, related_resources: [],
            },
          ],
        }), { status: 200 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    render(<AutoInspectionPage />);
    fireEvent.click(await screen.findByRole("checkbox", { name: "选择 prod-core" }));
    fireEvent.click(screen.getByRole("button", { name: "巡检选中" }));
    expect(await screen.findByText("批量巡检摘要")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "查看证据" }));

    const drawer = await screen.findByRole("complementary", { name: "detail-name 巡检证据" });
    expect(within(drawer).getByText("Pod 状态")).toBeInTheDocument();
    expect(within(drawer).getByText("事件")).toBeInTheDocument();
    expect(within(drawer).getByText("broken-api")).toBeInTheDocument();
    expect(within(drawer).getByText("Back-off restarting failed container")).toBeInTheDocument();
    expect(within(drawer).getByText("connection refused：database connection refused")).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "忽略此命中" })).toBeInTheDocument();
    expect(within(drawer).getByText("healthy-api").closest("details")).not.toHaveAttribute("open");
    expect(within(drawer).getByText("Service（全部正常 1）")).toBeInTheDocument();
  });

  it("confirms ignore log hit with full context and sends whitelist payload", async () => {
    fetchMock.mockImplementation(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);

      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return new Response(JSON.stringify({ executed_at: "2026-07-17T11:00:00Z", namespaces: [{
          name: "prod-core", status: "warning", pod_count: 1, abnormal_pod_count: 1,
          last_inspected_at: null, labels: {}, abnormal_categories: ["log_keyword"],
        }] }), { status: 200 });
      }
      if (url.endsWith("/api/v1/inspections/namespaces/run")) {
        return new Response(JSON.stringify({
          executed_at: "2026-07-17T11:01:00Z", all_namespaces: false, requested_namespaces: ["prod-core"],
          results: [{
            summary: { name: "prod-core", status: "warning", pod_count: 1, abnormal_pod_count: 1, last_inspected_at: null, labels: {}, abnormal_categories: ["log_keyword"] },
            health_status: "warning",
            detail_target: { type: "namespace", namespace: "detail-name", label_selector: "app=api", resource_scope: ["pods"] },
          }],
        }), { status: 200 });
      }
      if (url.endsWith("/api/v1/inspections/namespace/run")) {
        return new Response(JSON.stringify({
          inspection_target: { type: "namespace", namespace: "detail-name", label_selector: "app=api", resource_scope: ["pods"] },
          namespace: "detail-name", label_selector: "app=api", health_status: "warning", executed_at: "2026-07-17T11:01:30Z",
          evidence_bundles: [],
          services: [],
          ingresses: [],
          tls_secrets: [],
          daemonsets: [],
          pods: [
            {
              name: "broken-api", status: "CrashLoopBackOff", node_name: "node-a", restarts: 4,
              containers: [{ name: "api", restart_count: 4, state: "waiting", reason: "CrashLoopBackOff" }],
              events: [], describe_summary: "健康检查失败", log_summary: null, previous_log_summary: null,
              log_hits: [{ keyword: "connection refused", category: "dependency", severity: "warning", source: "current_log", matched_text: "database connection refused", container_name: "api", whitelisted: false }],
              resource_usage: {}, related_resources: [],
            },
          ],
        }), { status: 200 });
      }
      if (url.endsWith("/api/v1/whitelists/ignore")) {
        expect(JSON.parse(String(init?.body))).toEqual({
          namespace: "detail-name",
          label_selector: "app=api",
          pod_name_pattern: "broken-api",
          container_name: "api",
          keyword: "connection refused",
          note: "自动巡检证据抽屉忽略",
        });
        return new Response(JSON.stringify({
          id: 1,
          namespace: "detail-name",
          label_selector: "app=api",
          pod_name_pattern: "broken-api",
          container_name: "api",
          keyword: "connection refused",
          enabled: true,
        }), { status: 200 });
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    render(<AutoInspectionPage />);
    fireEvent.click(await screen.findByRole("checkbox", { name: "选择 prod-core" }));
    fireEvent.click(screen.getByRole("button", { name: "巡检选中" }));
    await screen.findByText("批量巡检摘要");
    fireEvent.click(screen.getByRole("button", { name: "查看证据" }));

    const drawer = await screen.findByRole("complementary", { name: "detail-name 巡检证据" });
    fireEvent.click(within(drawer).getByRole("button", { name: "忽略此命中" }));

    const confirmPanel = within(drawer).getByLabelText("忽略关键字命中确认");
    expect(within(confirmPanel).getByText("detail-name")).toBeInTheDocument();
    expect(within(confirmPanel).getByText("app=api")).toBeInTheDocument();
    expect(within(confirmPanel).getByText("broken-api")).toBeInTheDocument();
    expect(within(confirmPanel).getByText("api")).toBeInTheDocument();
    expect(within(confirmPanel).getByText("connection refused")).toBeInTheDocument();

    fireEvent.click(within(confirmPanel).getByRole("button", { name: "确认忽略" }));

    expect(await within(drawer).findByText("已加入白名单，后续相同范围的该命中会自动忽略")).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "已忽略" })).toBeDisabled();
  });

  it("shows ignored state for whitelisted log hit", async () => {
    fetchMock.mockImplementation(async (input: string | URL | Request) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return new Response(JSON.stringify({ executed_at: "2026-07-17T12:00:00Z", namespaces: [{
          name: "prod-core", status: "warning", pod_count: 1, abnormal_pod_count: 1,
          last_inspected_at: null, labels: {}, abnormal_categories: ["log_keyword"],
        }] }), { status: 200 });
      }
      if (url.endsWith("/api/v1/inspections/namespaces/run")) {
        return new Response(JSON.stringify({
          executed_at: "2026-07-17T12:01:00Z", all_namespaces: false, requested_namespaces: ["prod-core"],
          results: [{
            summary: { name: "prod-core", status: "warning", pod_count: 1, abnormal_pod_count: 1, last_inspected_at: null, labels: {}, abnormal_categories: ["log_keyword"] },
            health_status: "warning",
            detail_target: { type: "namespace", namespace: "prod-core", resource_scope: ["pods"] },
          }],
        }), { status: 200 });
      }
      if (url.endsWith("/api/v1/inspections/namespace/run")) {
        return new Response(JSON.stringify({
          inspection_target: { type: "namespace", namespace: "prod-core", resource_scope: ["pods"] },
          namespace: "prod-core", label_selector: null, health_status: "warning", executed_at: "2026-07-17T12:01:30Z",
          evidence_bundles: [],
          services: [],
          ingresses: [],
          tls_secrets: [],
          daemonsets: [],
          pods: [
            {
              name: "broken-api", status: "CrashLoopBackOff", node_name: "node-a", restarts: 4,
              containers: [{ name: "api", restart_count: 4, state: "waiting", reason: "CrashLoopBackOff" }],
              events: [], describe_summary: "健康检查失败", log_summary: null, previous_log_summary: null,
              log_hits: [{ keyword: "connection refused", category: "dependency", severity: "warning", source: "current_log", matched_text: "database connection refused", whitelisted: true }],
              resource_usage: {}, related_resources: [],
            },
          ],
        }), { status: 200 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    render(<AutoInspectionPage />);
    fireEvent.click(await screen.findByRole("checkbox", { name: "选择 prod-core" }));
    fireEvent.click(screen.getByRole("button", { name: "巡检选中" }));
    await screen.findByText("批量巡检摘要");
    fireEvent.click(screen.getByRole("button", { name: "查看证据" }));

    const drawer = await screen.findByRole("complementary", { name: "prod-core 巡检证据" });
    expect(within(drawer).getByRole("button", { name: "已忽略" })).toBeDisabled();
  });

  it("keeps drawer open and shows readable error when ignore request fails", async () => {
    fetchMock.mockImplementation(async (input: string | URL | Request) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return new Response(JSON.stringify({ executed_at: "2026-07-17T13:00:00Z", namespaces: [{
          name: "prod-core", status: "warning", pod_count: 1, abnormal_pod_count: 1,
          last_inspected_at: null, labels: {}, abnormal_categories: ["log_keyword"],
        }] }), { status: 200 });
      }
      if (url.endsWith("/api/v1/inspections/namespaces/run")) {
        return new Response(JSON.stringify({
          executed_at: "2026-07-17T13:01:00Z", all_namespaces: false, requested_namespaces: ["prod-core"],
          results: [{
            summary: { name: "prod-core", status: "warning", pod_count: 1, abnormal_pod_count: 1, last_inspected_at: null, labels: {}, abnormal_categories: ["log_keyword"] },
            health_status: "warning",
            detail_target: { type: "namespace", namespace: "prod-core", resource_scope: ["pods"] },
          }],
        }), { status: 200 });
      }
      if (url.endsWith("/api/v1/inspections/namespace/run")) {
        return new Response(JSON.stringify({
          inspection_target: { type: "namespace", namespace: "prod-core", resource_scope: ["pods"] },
          namespace: "prod-core", label_selector: null, health_status: "warning", executed_at: "2026-07-17T13:01:30Z",
          evidence_bundles: [],
          services: [],
          ingresses: [],
          tls_secrets: [],
          daemonsets: [],
          pods: [
            {
              name: "broken-api", status: "CrashLoopBackOff", node_name: "node-a", restarts: 4,
              containers: [{ name: "api", restart_count: 4, state: "waiting", reason: "CrashLoopBackOff" }],
              events: [], describe_summary: "健康检查失败", log_summary: null, previous_log_summary: null,
              log_hits: [{ keyword: "connection refused", category: "dependency", severity: "warning", source: "current_log", matched_text: "database connection refused", whitelisted: false }],
              resource_usage: {}, related_resources: [],
            },
          ],
        }), { status: 200 });
      }
      if (url.endsWith("/api/v1/whitelists/ignore")) {
        throw new Error("Request failed: 500");
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    render(<AutoInspectionPage />);
    fireEvent.click(await screen.findByRole("checkbox", { name: "选择 prod-core" }));
    fireEvent.click(screen.getByRole("button", { name: "巡检选中" }));
    await screen.findByText("批量巡检摘要");
    fireEvent.click(screen.getByRole("button", { name: "查看证据" }));

    const drawer = await screen.findByRole("complementary", { name: "prod-core 巡检证据" });
    fireEvent.click(within(drawer).getByRole("button", { name: "忽略此命中" }));
    fireEvent.click(within(drawer).getByRole("button", { name: "确认忽略" }));

    expect(await within(drawer).findByText("加入白名单失败：Request failed: 500")).toBeInTheDocument();
    const confirmPanel = within(drawer).getByLabelText("忽略关键字命中确认");
    expect(confirmPanel).toBeInTheDocument();
    expect(within(confirmPanel).getByText("broken-api")).toBeInTheDocument();
  });

  it("shows a readable error when namespace evidence fails", async () => {
    fetchMock.mockImplementation(async (input: string | URL | Request) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return new Response(JSON.stringify({ executed_at: "2026-07-14T10:00:00Z", namespaces: [{
          name: "prod-core", status: "warning", pod_count: 1, abnormal_pod_count: 1,
          last_inspected_at: null, labels: {}, abnormal_categories: ["pod_status"],
        }] }), { status: 200 });
      }
      if (url.endsWith("/api/v1/inspections/namespaces/run")) {
        return new Response(JSON.stringify({ executed_at: "2026-07-14T10:01:00Z", all_namespaces: false, requested_namespaces: ["prod-core"], results: [{
          summary: { name: "prod-core", status: "warning", pod_count: 1, abnormal_pod_count: 1, last_inspected_at: null, labels: {}, abnormal_categories: ["pod_status"] },
          health_status: "warning", detail_target: { type: "namespace", namespace: "prod-core", resource_scope: ["pods"] },
        }] }), { status: 200 });
      }
      if (url.endsWith("/api/v1/inspections/namespace/run")) {
        throw new Error("Request failed: 503");
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    render(<AutoInspectionPage />);
    fireEvent.click(await screen.findByRole("checkbox", { name: "选择 prod-core" }));
    fireEvent.click(screen.getByRole("button", { name: "巡检选中" }));
    await screen.findByText("批量巡检摘要");
    fireEvent.click(screen.getByRole("button", { name: "查看证据" }));
    expect(await screen.findByText("Request failed: 503")).toBeInTheDocument();
  });

  it("shows namespace level object abnormalities even when all pods are healthy", async () => {
    fetchMock.mockImplementation(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return new Response(JSON.stringify({ executed_at: "2026-07-17T10:00:00Z", namespaces: [{
          name: "edge-core", status: "warning", pod_count: 1, abnormal_pod_count: 0,
          last_inspected_at: null, labels: {}, abnormal_categories: ["related_object"],
        }] }), { status: 200 });
      }
      if (url.endsWith("/api/v1/inspections/namespaces/run")) {
        return new Response(JSON.stringify({
          executed_at: "2026-07-17T10:01:00Z", all_namespaces: false, requested_namespaces: ["edge-core"],
          results: [{
            summary: { name: "edge-core", status: "warning", pod_count: 1, abnormal_pod_count: 0,
              last_inspected_at: null, labels: {}, abnormal_categories: ["related_object"] },
            health_status: "warning",
            detail_target: { type: "namespace", namespace: "edge-core", resource_scope: ["pods"] },
          }],
        }), { status: 200 });
      }
      if (url.endsWith("/api/v1/inspections/namespace/run")) {
        expect(JSON.parse(String(init?.body))).toEqual({ namespace: "edge-core", label_selector: null });
        return new Response(JSON.stringify({
          inspection_target: { type: "namespace", namespace: "edge-core", resource_scope: ["pods"] },
          namespace: "edge-core", label_selector: null, health_status: "warning", executed_at: "2026-07-17T10:01:30Z",
          evidence_bundles: [],
          services: [{ name: "api", status: "healthy", summary: "服务正常" }],
          ingresses: [{ name: "demo", status: "unknown", summary: "入口地址未就绪" }],
          tls_secrets: [],
          daemonsets: [{ name: "agent", status: "degraded", summary: "部分节点未就绪" }],
          pods: [
            {
              name: "healthy-api", status: "Running", node_name: "node-b", restarts: 0,
              containers: [{ name: "api", restart_count: 0, state: "running", reason: null }],
              events: [], describe_summary: "运行正常", log_summary: null, previous_log_summary: null,
              log_hits: [], resource_usage: {}, related_resources: [],
            },
          ],
        }), { status: 200 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    render(<AutoInspectionPage />);
    fireEvent.click(await screen.findByRole("checkbox", { name: "选择 edge-core" }));
    fireEvent.click(screen.getByRole("button", { name: "巡检选中" }));
    await screen.findByText("批量巡检摘要");
    fireEvent.click(screen.getByRole("button", { name: "查看证据" }));

    const drawer = await screen.findByRole("complementary", { name: "edge-core 巡检证据" });
    expect(within(drawer).getAllByText("关联对象").length).toBeGreaterThan(0);
    expect(within(drawer).getByText("Ingress/demo：unknown")).toBeInTheDocument();
    expect(within(drawer).getByText("DaemonSet/agent：degraded")).toBeInTheDocument();
    expect(within(drawer).getByText("Pod（全部正常 1）")).toBeInTheDocument();
    expect(within(drawer).getByText("Service（全部正常 1）")).toBeInTheDocument();
  });
});
