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
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      if (url.endsWith("/api/v1/whitelists")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
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

  it("renders overview page with navigation and api data", async () => {
    const router = createMemoryRouter(appRoutes, {
      initialEntries: ["/"],
      basename: getRouterBasename("")
    });

    render(<RouterProvider router={router} />);

    expect(await screen.findByRole("heading", { name: "K8s Inspector" })).toBeInTheDocument();
    expect(await screen.findByText("Cluster is healthy")).toBeInTheDocument();
    expect(await screen.findByText(/异常对象数：/)).toBeInTheDocument();
    expect(await screen.findByText("ingress-nginx-controller: controller restarted")).toBeInTheDocument();
    expect(await screen.findByText("异常组件分组")).toBeInTheDocument();
    expect(await screen.findByText("集群自检结果")).toBeInTheDocument();
    expect(await screen.findByText("controller restarted 3 times")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Overview" })).toBeInTheDocument();
  });
});
