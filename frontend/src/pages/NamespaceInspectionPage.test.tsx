import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NamespaceInspectionPage } from "./NamespaceInspectionPage";

const fetchMock = vi.fn();

describe("NamespaceInspectionPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/discovery/namespaces")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              executed_at: "2026-07-21T09:00:00Z",
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
              ],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/discovery/namespaces/demo/labels")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              namespace: "demo",
              executed_at: "2026-07-21T09:00:00Z",
              labels: [{ key: "app", values: ["demo-api"], selector: "app=demo-api", pod_count: 1 }],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/inspection-targets") && (!init || init.method === undefined)) {
        return Promise.resolve(
          new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } }),
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
              executed_at: "2026-07-21T09:30:00Z",
              evidence_bundles: [],
              pods: [
                {
                  name: "demo-api-1",
                  status: "CrashLoopBackOff",
                  restarts: 3,
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

  it("uses merged log inspection page with all pod mode by default", async () => {
    render(<NamespaceInspectionPage />);

    await screen.findByRole("option", { name: "demo" });
    expect(screen.getByRole("heading", { name: "日志巡检" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("全部 Pod")).toBeInTheDocument();
  });

  it("runs namespace route through merged range inspection flow", async () => {
    render(<NamespaceInspectionPage />);

    await screen.findByRole("option", { name: "demo" });
    fireEvent.change(screen.getByLabelText("名称空间"), { target: { value: "demo" } });
    fireEvent.click(screen.getByRole("button", { name: "巡检日志范围" }));

    expect(await screen.findByText("范围内 Pod 列表")).toBeInTheDocument();
    expect(screen.queryByText("最近一次巡检摘要")).not.toBeInTheDocument();
  });
});
