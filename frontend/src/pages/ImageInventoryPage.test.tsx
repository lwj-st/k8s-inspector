import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ImageInventoryPage } from "./ImageInventoryPage";

const fetchMock = vi.fn();
const writeTextMock = vi.fn();
const anchorClickMock = vi.fn();

function namespacesResponse() {
  return {
    executed_at: "2026-08-19T10:00:00Z",
    namespaces: [
      { name: "demo", status: "warning", pod_count: 2, abnormal_pod_count: 1, last_inspected_at: null, labels: {}, abnormal_categories: ["pod_status"] },
      { name: "prod-core", status: "healthy", pod_count: 1, abnormal_pod_count: 0, last_inspected_at: null, labels: {}, abnormal_categories: [] },
    ],
  };
}

function inventoryResponse() {
  return {
    executed_at: "2026-08-19T10:01:00Z",
    namespaces: ["demo", "prod-core"],
    search: null,
    provider_mode: "mock",
    simulated: true,
    summary: {
      image_count: 1,
      namespace_count: 2,
      pod_count: 2,
      container_count: 2,
    },
    items: [
      {
        image: "registry.local/apps/demo-api:1.4.0-with-a-very-long-digest-sha256-abcdef",
        namespace_count: 2,
        pod_count: 2,
        container_count: 2,
        latest_pod_created_at: "2026-08-19T08:00:00Z",
        latest_pod_phase: "Running",
        references: [
          {
            namespace: "demo",
            pod_name: "demo-api-1",
            pod_phase: "Running",
            container_name: "api",
            container_type: "container",
            source: "spec",
            image: "registry.local/apps/demo-api:1.4.0-with-a-very-long-digest-sha256-abcdef",
            image_id: null,
            pod_created_at: "2026-08-19T08:00:00Z",
          },
          {
            namespace: "prod-core",
            pod_name: "payments-api-1",
            pod_phase: "Running",
            container_name: "api",
            container_type: "container",
            source: "imageID",
            image: "registry.local/apps/demo-api:1.4.0-with-a-very-long-digest-sha256-abcdef",
            image_id: "docker-pullable://registry.local/apps/demo-api@sha256:abc",
            pod_created_at: "2026-08-19T07:00:00Z",
          },
        ],
      },
    ],
  };
}

describe("ImageInventoryPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: writeTextMock.mockResolvedValue(undefined) },
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(anchorClickMock);
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:inventory"),
      revokeObjectURL: vi.fn(),
    });
    fetchMock.mockImplementation(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/api/v1/discovery/namespaces")) {
        return new Response(JSON.stringify(namespacesResponse()), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.includes("/api/v1/images?")) {
        return new Response(JSON.stringify(inventoryResponse()), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.includes("/api/v1/images/export?")) {
        return new Response("images txt", {
          status: 200,
          headers: {
            "Content-Type": "text/plain",
            "Content-Disposition": "attachment; filename=\"k8s-inspector-images-test.txt\"",
          },
        });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
  });

  afterEach(() => {
    cleanup();
    fetchMock.mockReset();
    writeTextMock.mockReset();
    anchorClickMock.mockReset();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("does not query images before namespace is selected", async () => {
    render(<ImageInventoryPage />);

    expect((await screen.findAllByText("请选择名称空间后查看镜像清单")).length).toBeGreaterThan(0);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/v1/discovery/namespaces");
  });

  it("queries multiple namespaces with repeated query params and shows details", async () => {
    const user = userEvent.setup();
    render(<ImageInventoryPage />);

    await user.click(await screen.findByRole("checkbox", { name: "demo" }));
    await user.click(screen.getByRole("checkbox", { name: "prod-core" }));
    fireEvent.change(screen.getByLabelText("搜索镜像关键字"), { target: { value: "demo-api" } });
    await user.click(screen.getByRole("button", { name: "查询" }));

    await screen.findByText("registry.local/apps/demo-api:1.4.0-with-a-very-long-digest-sha256-abcdef");
    const imageRequest = fetchMock.mock.calls.find(([input]) => String(input).includes("/api/v1/images?"));
    expect(String(imageRequest?.[0])).toContain("namespace=demo");
    expect(String(imageRequest?.[0])).toContain("namespace=prod-core");
    expect(String(imageRequest?.[0])).toContain("search=demo-api");

    await user.click(screen.getByRole("button", { name: "详情" }));
    const dialog = await screen.findByRole("dialog", { name: "镜像引用详情" });
    expect(within(dialog).getByText("demo-api-1")).toBeInTheDocument();
    expect(within(dialog).getByText("payments-api-1")).toBeInTheDocument();
    expect(within(dialog).getAllByText("imageID").length).toBeGreaterThan(0);
    expect(within(dialog).getByText("docker-pullable://registry.local/apps/demo-api@sha256:abc")).toBeInTheDocument();
  });

  it("copies full image and blocks export without namespace", async () => {
    const user = userEvent.setup();
    render(<ImageInventoryPage />);

    await screen.findByRole("group", { name: "选择名称空间" });
    await user.click(screen.getByRole("button", { name: "导出 TXT" }));
    expect(await screen.findByText("未选择名称空间时不能导出镜像清单")).toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: "demo" }));
    await user.click(screen.getByRole("button", { name: "查询" }));
    await user.click(await screen.findByRole("button", { name: "复制" }));

    expect(await screen.findByText("镜像地址已复制。")).toBeInTheDocument();
  });

  it("exports current filter as txt", async () => {
    const user = userEvent.setup();
    render(<ImageInventoryPage />);

    await user.click(await screen.findByRole("checkbox", { name: "demo" }));
    fireEvent.change(screen.getByLabelText("搜索镜像关键字"), { target: { value: "api" } });
    await user.click(screen.getByRole("button", { name: "导出 TXT" }));

    await waitFor(() => {
      const exportRequest = fetchMock.mock.calls.find(([input]) => String(input).includes("/api/v1/images/export?"));
      expect(String(exportRequest?.[0])).toContain("namespace=demo");
      expect(String(exportRequest?.[0])).toContain("search=api");
    });
    expect(await screen.findByText("镜像清单已导出。")).toBeInTheDocument();
  });
});
