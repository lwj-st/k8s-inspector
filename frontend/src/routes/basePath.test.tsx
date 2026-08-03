import { cleanup, render, screen } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { buildApiBaseUrl, getRouterBasename, normalizeBasePath } from "../app/config";
import { appRoutes } from ".";

const fetchMock = vi.fn();

describe("base path helpers", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation(async (input: string | URL | Request) => {
      const url = String(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);

      if (url.endsWith("/api/v1/auth/session")) {
        return new Response(
          JSON.stringify({
            authenticated: true,
            username: "admin",
            csrf_token: "csrf-token-at-least-16",
            idle_expires_at: "2026-07-26T22:00:00Z",
            absolute_expires_at: "2026-07-27T05:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (url.endsWith("/api/v1/settings")) {
        return new Response(
          JSON.stringify({
            cluster_id: "test",
            base_path: "/inspector",
            provider_mode: "kubernetes",
            kubeconfig_path: "/path/to/.kube/config",
            kube_context: "kubernetes-admin@kubernetes",
            llm_provider: "qwen",
            api_key: "",
            model_endpoint: "",
            default_inspection_strategy: {},
            llm_enabled: false,
            inspection_policy: {
              required_components: [],
              thresholds: {
                tls_warning_days: 30,
                tls_critical_days: 7,
                pvc_pending_warning_minutes: 5,
                pvc_pending_critical_minutes: 30,
                pv_released_stale_hours: 24,
                job_incomplete_info_minutes: 60,
                resource_usage_warning_percent: 90,
                resource_usage_consecutive_cycles: 3,
                pod_terminating_warning_minutes: 10,
                pod_restart_window_minutes: 10,
                pod_restart_delta: 3,
                warning_event_window_minutes: 30,
                node_not_ready_grace_seconds: 0,
              },
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (url.endsWith("/api/v1/system/status")) {
        return new Response(
          JSON.stringify({
            status: "healthy",
            version: "1.1.0",
            cluster_id: "test",
            database: { state: "ok", message: "ok", checked_at: "2026-07-26T10:00:00Z", details: {} },
            kubernetes_api: { state: "ok", message: "ok", checked_at: "2026-07-26T10:00:00Z", details: {} },
            provider: { state: "ok", message: "ok", checked_at: "2026-07-26T10:00:00Z", details: {} },
            scheduler: { state: "ok", message: "ok", checked_at: "2026-07-26T10:00:00Z", details: {} },
            metrics_api: { state: "ok", message: "ok", checked_at: "2026-07-26T10:00:00Z", details: {} },
            notifications: { state: "ok", message: "ok", checked_at: "2026-07-26T10:00:00Z", details: {} },
            last_inspection: { state: "ok", message: "ok", checked_at: "2026-07-26T10:00:00Z", details: {} },
            configuration: { state: "ok", message: "ok", checked_at: "2026-07-26T10:00:00Z", details: {} },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (url.includes("/api/v1/inspection-plans?")) {
        return new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 100 }), { status: 200 });
      }

      if (url.includes("/api/v1/notification-channels?")) {
        return new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 100 }), { status: 200 });
      }

      throw new Error(`Unexpected request: ${url}`);
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  it("normalizes root and sub-path values", () => {
    expect(normalizeBasePath("")).toBe("");
    expect(normalizeBasePath("/")).toBe("");
    expect(normalizeBasePath("inspector")).toBe("/inspector");
    expect(normalizeBasePath("/inspector/")).toBe("/inspector");
  });

  it("builds router basename and api base url", () => {
    expect(getRouterBasename("")).toBe("/");
    expect(getRouterBasename("/inspector")).toBe("/inspector");
    expect(buildApiBaseUrl("")).toBe("/api/v1");
    expect(buildApiBaseUrl("/inspector/")).toBe("/inspector/api/v1");
  });

  it("renders routes correctly under /inspector basename", async () => {
    const router = createMemoryRouter(appRoutes, {
      initialEntries: ["/inspector/settings?tab=basic"],
      basename: getRouterBasename("/inspector")
    });

    render(<RouterProvider router={router} />);

    expect(await screen.findByRole("heading", { name: "系统设置" })).toBeInTheDocument();
    expect(await screen.findByText("kubernetes")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "系统设置" })).toHaveAttribute("href", "/inspector/settings");
  });

  it("renders routes correctly at root basename", async () => {
    const router = createMemoryRouter(appRoutes, {
      initialEntries: ["/settings?tab=basic"],
      basename: getRouterBasename("")
    });

    render(<RouterProvider router={router} />);

    expect(await screen.findByRole("heading", { name: "系统设置" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "系统设置" })).toHaveAttribute("href", "/settings");
  });
});
