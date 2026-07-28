import { cleanup, render, screen } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { appRoutes } from "../routes";
import { getRouterBasename } from "./config";

const fetchMock = vi.fn();

function authenticatedSession() {
  return {
    authenticated: true,
    username: "admin",
    csrf_token: "csrf-token-at-least-16",
    idle_expires_at: "2026-07-26T22:00:00Z",
    absolute_expires_at: "2026-07-27T05:00:00Z",
  };
}

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/session")) {
        return new Response(JSON.stringify(authenticatedSession()), { status: 200 });
      }
      if (url.includes("/api/v1/issues?")) {
        return new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: url.includes("page_size=1") ? 1 : 20 }), { status: 200 });
      }
      if (url.endsWith("/api/v1/issues/filter-options")) {
        return new Response(JSON.stringify({
          namespaces: [],
          resource_kinds: [],
          source_checks: [],
        }), { status: 200 });
      }
      if (url.includes("/api/v1/inspection-runs?")) {
        return new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 1 }), { status: 200 });
      }
      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return new Response(JSON.stringify({
          executed_at: "2026-07-26T12:00:00Z",
          namespaces: [{
            name: "default",
            status: "healthy",
            pod_count: 12,
            abnormal_pod_count: 0,
            last_inspected_at: null,
            labels: {},
            abnormal_categories: [],
          }],
        }), { status: 200 });
      }
      if (url.endsWith("/api/v1/inspection-targets")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  it("renders the problem workbench and preserves all v1.0 entries", async () => {
    const router = createMemoryRouter(appRoutes, {
      initialEntries: ["/"],
      basename: getRouterBasename(""),
    });

    render(<RouterProvider router={router} />);

    expect(await screen.findByRole("heading", { name: "K8s 巡检台" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "问题工作台" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "状态巡检" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "日志巡检" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "模板检查" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "故障模板" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "关键字与白名单" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "系统设置" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "打开菜单" })).toHaveAttribute("aria-expanded", "false");
  });

  it("keeps the old pod route on the merged log inspection page in single-pod mode", async () => {
    const router = createMemoryRouter(appRoutes, {
      initialEntries: ["/inspections/pod"],
      basename: getRouterBasename(""),
    });

    render(<RouterProvider router={router} />);

    expect(await screen.findByRole("heading", { name: "选择范围" })).toBeInTheDocument();
    expect(screen.getByLabelText("范围类型")).toBeInTheDocument();
    expect(screen.getByDisplayValue("单个 Pod")).toBeInTheDocument();
  });

});
