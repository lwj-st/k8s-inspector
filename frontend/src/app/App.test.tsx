import { render, screen } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { appRoutes } from "../routes";
import { getRouterBasename } from "./config";

const fetchMock = vi.fn();

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation(async (input: string | URL | Request) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);

      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return new Response(
          JSON.stringify({
            executed_at: "2026-07-12T12:00:00Z",
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
                last_inspected_at: "2026-07-12T11:30:00Z",
                labels: { env: "prod" },
                abnormal_categories: ["pod_status"],
              },
            ],
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" }
          }
        );
      }

      if (url.endsWith("/api/v1/inspections/cluster/run")) {
        return new Response(
          JSON.stringify({
            health_status: "warning",
            executed_at: "2026-07-02T12:01:00Z",
            results: [
              {
                component: "ingress-nginx",
                namespace: "ingress-nginx",
                node: "node-a",
                status: "degraded",
                describe_summary: "controller restarted 3 times",
                log_summary: "failed to load backend",
              },
              {
                component: "Calico CNI",
                namespace: "calico-system",
                node: "node-b",
                status: "NotReady",
                describe_summary: "felix pod not ready",
                log_summary: null,
              }
            ],
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" }
          }
        );
      }

      if (url.endsWith("/api/v1/templates")) {
        return new Response(
          JSON.stringify([
            {
              id: 1,
              name: "ingress 控制器故障",
              scenario: "ingress",
              object_scope: "deployment",
              namespace_scope: "ingress-nginx",
              label_selector: "app.kubernetes.io/component=controller",
              match_conditions: [
                {
                  target_ref: "controller",
                  condition_type: "log_keyword",
                  operator: "contains",
                  expected_value: "failed to load backend"
                }
              ],
              joint_rule: { operator: "AND" },
              reason: "控制器无法加载后端",
              suggestion: "检查 upstream 配置与 service",
              enabled: true
            }
          ]),
          {
            status: 200,
            headers: { "Content-Type": "application/json" }
          },
        );
      }

      if (url.endsWith("/api/v1/whitelists")) {
        return new Response(
          JSON.stringify([
            {
              id: 1,
              namespace: "demo",
              label_selector: "app=demo-api",
              keyword: "readiness probe failed",
              enabled: true,
              note: "已确认是预发布环境的已知噪音"
            }
          ]),
          {
            status: 200,
            headers: { "Content-Type": "application/json" }
          },
        );
      }

      if (url.endsWith("/api/v1/settings")) {
        return new Response(
          JSON.stringify({
            base_path: "/inspector",
            provider_mode: "kubernetes",
            kubeconfig_path: "/path/to/.kube/config",
            kube_context: "kubernetes-admin@kubernetes",
            llm_provider: "openai",
            model: "gpt-5",
            api_key: "",
            default_namespace: "default",
            system_status: "ready"
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" }
          }
        );
      }

      if (url.endsWith("/api/v1/system/status")) {
        return new Response(
          JSON.stringify({
            status: "ready",
            version: "0.1.0",
            message: "kubernetes provider active",
            provider_mode: "kubernetes",
            kube_context: "kubernetes-admin@kubernetes"
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" }
          }
        );
      }

      throw new Error(`Unexpected request: ${url}`);
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  it("renders auto inspection home with namespace list", async () => {
    const router = createMemoryRouter(appRoutes, {
      initialEntries: ["/"],
      basename: getRouterBasename("")
    });

    render(<RouterProvider router={router} />);

    expect(await screen.findByRole("heading", { name: "K8s 巡检台" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "自动巡检" })).toBeInTheDocument();
    expect(await screen.findByText("名称空间列表")).toBeInTheDocument();
    expect(await screen.findByText("default")).toBeInTheDocument();
    expect(await screen.findByText("prod-core")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "自动巡检" })).toBeInTheDocument();
  });
});
