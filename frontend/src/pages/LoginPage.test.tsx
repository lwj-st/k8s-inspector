import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { listIssues } from "../api/client";
import { RequireSession, SessionProvider, useSession } from "../features/auth/SessionContext";
import { LoginPage } from "./LoginPage";

const fetchMock = vi.fn();

function SessionActions() {
  const { logout } = useSession();
  return (
    <>
      <button type="button" onClick={() => void listIssues().catch(() => undefined)}>读取问题</button>
      <button type="button" onClick={() => void logout()}>退出登录</button>
    </>
  );
}

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={[{ pathname: "/login", state: { from: "/target" } }]}>
      <SessionProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/target" element={<h1>目标问题</h1>} />
        </Routes>
      </SessionProvider>
    </MemoryRouter>,
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    cleanup();
    fetchMock.mockReset();
    vi.unstubAllGlobals();
  });

  it("logs in and returns to the original problem page without exposing a token", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/auth/session")) {
        return new Response(JSON.stringify({ authenticated: false }), { status: 200 });
      }
      if (url.endsWith("/auth/login")) {
        expect(JSON.parse(String(init?.body))).toEqual({ username: "admin", password: "correct-password" });
        return new Response(JSON.stringify({
          authenticated: true,
          username: "admin",
          csrf_token: "csrf-token-at-least-16",
          idle_expires_at: "2026-07-26T22:00:00Z",
          absolute_expires_at: "2026-07-27T05:00:00Z",
        }), { status: 200 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    renderLogin();

    await user.type(await screen.findByLabelText("用户名"), "admin");
    await user.tab();
    await user.type(screen.getByLabelText("密码"), "correct-password");
    await user.keyboard("{Enter}");

    expect(await screen.findByRole("heading", { name: "目标问题" })).toBeInTheDocument();
    expect(screen.queryByText("csrf-token-at-least-16")).not.toBeInTheDocument();
  });

  it("shows readable 401 and rate-limit feedback while keeping the username", async () => {
    const user = userEvent.setup();
    let loginAttempts = 0;
    fetchMock.mockImplementation(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/auth/session")) {
        return new Response(JSON.stringify({ authenticated: false }), { status: 200 });
      }
      if (url.endsWith("/auth/login")) {
        loginAttempts += 1;
        return new Response(
          JSON.stringify({ detail: loginAttempts === 1 ? "用户名或密码错误" : "登录尝试过多" }),
          { status: loginAttempts === 1 ? 401 : 429 },
        );
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    renderLogin();
    const username = await screen.findByLabelText("用户名");
    await user.type(username, "admin");
    await user.type(screen.getByLabelText("密码"), "wrong");
    await user.click(screen.getByRole("button", { name: "登录" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("用户名或密码不正确");
    expect(username).toHaveValue("admin");

    await user.click(screen.getByRole("button", { name: "登录" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("尝试次数过多，请稍后再试");
  });

  it("redirects an unauthenticated protected route to login", async () => {
    fetchMock.mockImplementation(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/auth/session")) {
        return new Response(JSON.stringify({ authenticated: false }), { status: 200 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    render(
      <MemoryRouter initialEntries={["/protected"]}>
        <SessionProvider>
          <Routes>
            <Route element={<RequireSession />}>
              <Route path="/protected" element={<h1>受保护数据</h1>} />
            </Route>
            <Route path="/login" element={<LoginPage />} />
          </Routes>
        </SessionProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "登录巡检台" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "受保护数据" })).not.toBeInTheDocument();
  });

  it("returns to login when an active session expires with 401", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/auth/session")) {
        return new Response(JSON.stringify({
          authenticated: true,
          username: "admin",
          csrf_token: "csrf-token-at-least-16",
          idle_expires_at: "2026-07-26T22:00:00Z",
          absolute_expires_at: "2026-07-27T05:00:00Z",
        }), { status: 200 });
      }
      if (url.endsWith("/issues")) {
        return new Response(JSON.stringify({
          code: "AUTHENTICATION_REQUIRED",
          message: "登录已过期",
          request_id: "request-401",
          details: {},
        }), { status: 401 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    render(
      <MemoryRouter initialEntries={["/protected"]}>
        <SessionProvider>
          <Routes>
            <Route element={<RequireSession />}>
              <Route path="/protected" element={<SessionActions />} />
            </Route>
            <Route path="/login" element={<LoginPage />} />
          </Routes>
        </SessionProvider>
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole("button", { name: "读取问题" }));
    expect(await screen.findByRole("heading", { name: "登录巡检台" })).toBeInTheDocument();
  });

  it("logs out through the server and clears the protected screen", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/auth/session")) {
        return new Response(JSON.stringify({
          authenticated: true,
          username: "admin",
          csrf_token: "csrf-token-at-least-16",
          idle_expires_at: "2026-07-26T22:00:00Z",
          absolute_expires_at: "2026-07-27T05:00:00Z",
        }), { status: 200 });
      }
      if (url.endsWith("/auth/logout") && init?.method === "POST") {
        expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-token-at-least-16");
        return new Response(null, { status: 204 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    render(
      <MemoryRouter initialEntries={["/protected"]}>
        <SessionProvider>
          <Routes>
            <Route element={<RequireSession />}>
              <Route path="/protected" element={<SessionActions />} />
            </Route>
            <Route path="/login" element={<LoginPage />} />
          </Routes>
        </SessionProvider>
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole("button", { name: "退出登录" }));
    expect(await screen.findByRole("heading", { name: "登录巡检台" })).toBeInTheDocument();
  });
});
