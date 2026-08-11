import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { appRoutes } from "../routes";
import { getRouterBasename } from "./config";

const fetchMock = vi.fn();
let localStorageData: Record<string, string> = {};

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
    localStorageData = {};
    vi.stubGlobal("fetch", fetchMock);
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem: vi.fn((key: string) => localStorageData[key] ?? null),
        setItem: vi.fn((key: string, value: string) => {
          localStorageData[key] = value;
        }),
        removeItem: vi.fn((key: string) => {
          delete localStorageData[key];
        }),
        clear: vi.fn(() => {
          localStorageData = {};
        }),
      },
    });
    fetchMock.mockImplementation(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/session")) {
        return new Response(JSON.stringify(authenticatedSession()), { status: 200 });
      }
      if (url.endsWith("/api/v1/auth/logout")) {
        return new Promise<Response>(() => {});
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
    localStorageData = {};
    delete document.documentElement.dataset.theme;
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

  it("changes password from the sidebar with csrf protection", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/session")) {
        return new Response(JSON.stringify(authenticatedSession()), { status: 200 });
      }
      if (url.endsWith("/api/v1/auth/password") && init?.method === "POST") {
        expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-token-at-least-16");
        expect(JSON.parse(String(init.body))).toEqual({
          current_password: "old-password",
          new_password: "123456",
        });
        return new Response(JSON.stringify(authenticatedSession()), { status: 200 });
      }
      if (url.includes("/api/v1/issues?")) {
        return new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: url.includes("page_size=1") ? 1 : 20 }), { status: 200 });
      }
      if (url.endsWith("/api/v1/issues/filter-options")) {
        return new Response(JSON.stringify({ namespaces: [], resource_kinds: [], source_checks: [] }), { status: 200 });
      }
      if (url.includes("/api/v1/inspection-runs?")) {
        return new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 1 }), { status: 200 });
      }
      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return new Response(JSON.stringify({ executed_at: "2026-07-26T12:00:00Z", namespaces: [] }), { status: 200 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    const router = createMemoryRouter(appRoutes, {
      initialEntries: ["/"],
      basename: getRouterBasename(""),
    });

    render(<RouterProvider router={router} />);

    await user.click(await screen.findByRole("button", { name: /admin/ }));
    await user.click(screen.getByRole("menuitem", { name: "更改密码" }));
    await user.type(screen.getByLabelText("当前密码"), "old-password");
    await user.type(screen.getByLabelText("新密码"), "123456");
    await user.type(screen.getByLabelText("确认新密码"), "123456");
    await user.click(screen.getByRole("button", { name: "保存新密码" }));

    expect(await screen.findByText("密码已更新，其他已登录会话会失效。")).toBeInTheDocument();
  });

  it("uses a light sidebar theme with restrained nav typography", async () => {
    const router = createMemoryRouter(appRoutes, {
      initialEntries: ["/"],
      basename: getRouterBasename(""),
    });

    render(<RouterProvider router={router} />);

    await screen.findByRole("heading", { name: "K8s 巡检台" });
    const sidebar = document.querySelector(".app-sidebar") as HTMLElement;
    const activeLink = screen.getByRole("link", { name: "问题工作台" });

    expect(sidebar).toHaveClass("app-sidebar");
    expect(activeLink).toHaveClass("nav-link-active");
    expect(document.body.scrollWidth).toBeLessThanOrEqual(window.innerWidth);
  });

  it("opens the user menu and closes it from outside click or Escape", async () => {
    const user = userEvent.setup();
    const router = createMemoryRouter(appRoutes, {
      initialEntries: ["/"],
      basename: getRouterBasename(""),
    });

    render(<RouterProvider router={router} />);

    const userCard = await screen.findByRole("button", { name: /admin/ });
    await user.click(userCard);
    expect(screen.getByText("主题切换")).toBeInTheDocument();
    expect(screen.getByRole("menuitemradio", { name: "亮色" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("menuitemradio", { name: "暗色" })).toHaveAttribute("aria-checked", "false");
    expect(screen.getByRole("menuitem", { name: "更改密码" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "注销" })).toBeInTheDocument();

    await user.click(document.body);
    expect(screen.queryByRole("menuitem", { name: "注销" })).not.toBeInTheDocument();

    userCard.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("menuitem", { name: "注销" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menuitem", { name: "注销" })).not.toBeInTheDocument();
  });

  it("switches to dark theme from the user menu and keeps it after remount", async () => {
    const user = userEvent.setup();
    const router = createMemoryRouter(appRoutes, {
      initialEntries: ["/"],
      basename: getRouterBasename(""),
    });

    render(<RouterProvider router={router} />);

    expect(await screen.findByRole("heading", { name: "K8s 巡检台" })).toBeInTheDocument();
    expect(document.documentElement.dataset.theme).toBe("light");

    await user.click(screen.getByRole("button", { name: /admin/ }));
    await user.click(screen.getByRole("menuitemradio", { name: "暗色" }));

    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorageData["k8s-inspector:theme"]).toBe("dark");
    expect(screen.getByRole("menuitemradio", { name: "暗色" })).toHaveAttribute("aria-checked", "true");

    cleanup();

    const remountedRouter = createMemoryRouter(appRoutes, {
      initialEntries: ["/"],
      basename: getRouterBasename(""),
    });
    render(<RouterProvider router={remountedRouter} />);

    expect(await screen.findByRole("heading", { name: "K8s 巡检台" })).toBeInTheDocument();
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("logs out from the user menu", async () => {
    const user = userEvent.setup();
    const router = createMemoryRouter(appRoutes, {
      initialEntries: ["/"],
      basename: getRouterBasename(""),
    });

    render(<RouterProvider router={router} />);

    await user.click(await screen.findByRole("button", { name: /admin/ }));
    await user.click(screen.getByRole("menuitem", { name: "注销" }));

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/auth/logout"),
      expect.objectContaining({ method: "POST" }),
    );
  });
});
