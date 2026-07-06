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

      if (url.endsWith("/api/v1/overview")) {
        return new Response(
          JSON.stringify({
            cluster_status: "healthy",
            health_score: 93,
            last_checked_at: "2026-07-02T12:00:00Z",
            issues: [
              {
                name: "ingress-nginx-controller",
                component: "ingress-nginx",
                status: "degraded",
                summary: "controller restarted",
              }
            ],
            recent_summary: "Cluster is healthy"
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

  it("renders workbench style overview with navigation and quick actions", async () => {
    const router = createMemoryRouter(appRoutes, {
      initialEntries: ["/"],
      basename: getRouterBasename("")
    });

    render(<RouterProvider router={router} />);

    expect(await screen.findByRole("heading", { name: "K8s Inspector" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "排障工作台" })).toBeInTheDocument();
    expect(await screen.findByText("最近异常")).toBeInTheDocument();
    expect(await screen.findByText("最近使用的模板")).toBeInTheDocument();
    expect(await screen.findByText("白名单提醒")).toBeInTheDocument();
    expect(await screen.findByText("ingress-nginx-controller: controller restarted")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /巡检名称空间/ })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /巡检单个 Pod/ })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /故障模板检查/ })).toBeInTheDocument();
    expect(await screen.findByText("ingress 控制器故障")).toBeInTheDocument();
    expect(await screen.findByText("readiness probe failed")).toBeInTheDocument();
    expect(await screen.findByText("controller restarted 3 times")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "工作台" })).toBeInTheDocument();
  });
});
