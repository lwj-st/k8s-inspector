import { render, screen } from "@testing-library/react";
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

      if (url.endsWith("/api/v1/settings")) {
        return new Response(
          JSON.stringify({
            base_path: "/inspector",
            provider_mode: "kubernetes",
            kubeconfig_path: "/path/to/.kube/config",
            kube_context: "kubernetes-admin@kubernetes",
            llm_provider: "qwen",
            api_key: "",
            model_endpoint: "",
            default_inspection_strategy: {},
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (url.endsWith("/api/v1/system/status")) {
        return new Response(
          JSON.stringify({
            status: "ready",
            version: "0.1.0",
            message: "ok",
            provider_mode: "kubernetes",
            kube_context: "kubernetes-admin@kubernetes",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected request: ${url}`);
    });
  });

  afterEach(() => {
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
      initialEntries: ["/inspector/settings"],
      basename: getRouterBasename("/inspector")
    });

    render(<RouterProvider router={router} />);

    expect(await screen.findByRole("heading", { name: "系统配置" })).toBeInTheDocument();
    expect(await screen.findByDisplayValue("kubernetes")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute("href", "/inspector/settings");
  });
});
