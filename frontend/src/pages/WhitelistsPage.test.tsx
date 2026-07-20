import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WhitelistsPage } from "./WhitelistsPage";

const fetchMock = vi.fn();

describe("WhitelistsPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/keywords") && (!init || init.method === undefined)) {
        return Promise.resolve(
          new Response(JSON.stringify([
            {
              id: 1,
              keyword: "connection refused",
              category: "database",
              severity: "error",
              description: "downstream not ready",
              enabled: true,
              builtin: true,
            },
          ]), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/keywords") && init?.method === "POST") {
        return Promise.resolve(
          new Response(JSON.stringify({
            id: 2,
            keyword: "timeout",
            category: "network",
            severity: "warning",
            description: "request timeout",
            enabled: true,
            builtin: false,
          }), { status: 201, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/keywords/2") && init?.method === "PUT") {
        return Promise.resolve(
          new Response(JSON.stringify({
            id: 2,
            keyword: "timeout",
            category: "network",
            severity: "critical",
            description: "request timeout updated",
            enabled: true,
            builtin: false,
          }), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/keywords/2") && init?.method === "DELETE") {
        return Promise.resolve(new Response(null, { status: 204 }));
      }

      if (url.endsWith("/keywords/export")) {
        return Promise.resolve(
          new Response(JSON.stringify([
            {
              id: 1,
              keyword: "connection refused",
              category: "database",
              severity: "error",
              description: "downstream not ready",
              enabled: true,
              builtin: true,
            },
          ]), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/keywords/import")) {
        return Promise.resolve(
          new Response(JSON.stringify([
            {
              id: 3,
              keyword: "oom",
              category: "runtime",
              severity: "critical",
              description: "memory spike",
              enabled: true,
              builtin: false,
            },
          ]), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/keywords/1/disable")) {
        return Promise.resolve(
          new Response(JSON.stringify({
            id: 1,
            keyword: "connection refused",
            category: "database",
            severity: "error",
            description: "downstream not ready",
            enabled: false,
            builtin: true,
          }), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/keywords/3/disable")) {
        return Promise.resolve(
          new Response(JSON.stringify({
            id: 3,
            keyword: "oom",
            category: "runtime",
            severity: "critical",
            description: "memory spike",
            enabled: false,
            builtin: false,
          }), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/whitelists") && (!init || init.method === undefined)) {
        return Promise.resolve(
          new Response(JSON.stringify([
            {
              id: 1,
              namespace: "demo",
              label_selector: "app=demo",
              pod_name_pattern: "demo-api-*",
              container_name: "demo-api",
              keyword: "connection refused",
              enabled: true,
              note: "warmup noise",
            },
          ]), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/whitelists") && init?.method === "POST") {
        return Promise.resolve(
          new Response(JSON.stringify({
            id: 2,
            namespace: "prod",
            label_selector: "app=worker",
            pod_name_pattern: "worker-*",
            container_name: "worker",
            keyword: "timeout",
            enabled: true,
            note: "known worker retry",
          }), { status: 201, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/whitelists/2") && init?.method === "PUT") {
        return Promise.resolve(
          new Response(JSON.stringify({
            id: 2,
            namespace: "prod",
            label_selector: "app=worker",
            pod_name_pattern: "worker-*",
            container_name: "worker",
            keyword: "timeout",
            enabled: true,
            note: "known worker retry updated",
          }), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/whitelists/3") && init?.method === "DELETE") {
        return Promise.resolve(new Response(null, { status: 204 }));
      }

      if (url.endsWith("/whitelists/export")) {
        return Promise.resolve(
          new Response(JSON.stringify([
            {
              id: 1,
              namespace: "demo",
              label_selector: "app=demo",
              pod_name_pattern: "demo-api-*",
              container_name: "demo-api",
              keyword: "connection refused",
              enabled: true,
              note: "warmup noise",
            },
          ]), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/whitelists/import")) {
        return Promise.resolve(
          new Response(JSON.stringify([
            {
              id: 3,
              namespace: "qa",
              label_selector: "app=batch",
              pod_name_pattern: "batch-*",
              container_name: "batch",
              keyword: "oom",
              enabled: true,
              note: "batch retry",
            },
          ]), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/whitelists/1/disable")) {
        return Promise.resolve(
          new Response(JSON.stringify({
            id: 1,
            namespace: "demo",
            label_selector: "app=demo",
            pod_name_pattern: "demo-api-*",
            container_name: "demo-api",
            keyword: "connection refused",
            enabled: false,
            note: "warmup noise",
          }), { status: 200, headers: { "Content-Type": "application/json" } }),
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

  it("renders summarized keyword and whitelist sections without default json textareas", async () => {
    render(<WhitelistsPage />);

    expect(await screen.findByRole("heading", { name: "关键字库与白名单" })).toBeInTheDocument();
    expect(screen.getByText("database / downstream not ready")).toBeInTheDocument();
    expect(screen.getByText("严重程度：高 / 系统内置")).toBeInTheDocument();
    expect(screen.getByText("demo / app=demo / Pod demo-api-* / 容器 demo-api")).toBeInTheDocument();
    expect(screen.getByText("来源说明：warmup noise")).toBeInTheDocument();
    expect(screen.queryByLabelText("导入关键字 JSON")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("导入白名单 JSON")).not.toBeInTheDocument();
  });

  it("allows creating and editing keyword and whitelist in modals", async () => {
    render(<WhitelistsPage />);

    fireEvent.click((await screen.findAllByRole("button", { name: "新增关键字" }))[0]);
    const keywordDialog = await screen.findByRole("dialog", { name: "新增关键字" });
    fireEvent.change(within(keywordDialog).getByLabelText("关键字"), { target: { value: "timeout" } });
    fireEvent.change(within(keywordDialog).getByLabelText("类别"), { target: { value: "network" } });
    fireEvent.change(within(keywordDialog).getByLabelText("严重级别"), { target: { value: "warning" } });
    fireEvent.change(within(keywordDialog).getByLabelText("说明"), { target: { value: "request timeout" } });
    fireEvent.click(within(keywordDialog).getByRole("button", { name: "新增关键字" }));

    await waitFor(() => {
      expect(screen.getByText("关键字已新增")).toBeInTheDocument();
      expect(screen.getByText("timeout")).toBeInTheDocument();
    });

    const timeoutCard = screen.getByText("timeout").closest(".card");
    expect(timeoutCard).not.toBeNull();
    fireEvent.click(within(timeoutCard as HTMLElement).getByRole("button", { name: "编辑" }));
    const editKeywordDialog = await screen.findByRole("dialog", { name: "编辑关键字" });
    fireEvent.change(within(editKeywordDialog).getByLabelText("严重级别"), { target: { value: "critical" } });
    fireEvent.change(within(editKeywordDialog).getByLabelText("说明"), { target: { value: "request timeout updated" } });
    fireEvent.click(within(editKeywordDialog).getByRole("button", { name: "保存关键字" }));

    await waitFor(() => {
      expect(screen.getByText("network / request timeout updated")).toBeInTheDocument();
    });

    fireEvent.click((screen.getAllByRole("button", { name: "新增白名单" }))[0]);
    const whitelistDialog = await screen.findByRole("dialog", { name: "新增白名单" });
    fireEvent.change(within(whitelistDialog).getByLabelText("名称空间"), { target: { value: "prod" } });
    fireEvent.change(within(whitelistDialog).getByLabelText("Label Selector"), { target: { value: "app=worker" } });
    fireEvent.change(within(whitelistDialog).getByLabelText("Pod 名称匹配"), { target: { value: "worker-*" } });
    fireEvent.change(within(whitelistDialog).getByLabelText("容器名称"), { target: { value: "worker" } });
    fireEvent.change(within(whitelistDialog).getByLabelText("白名单关键字"), { target: { value: "timeout" } });
    fireEvent.change(within(whitelistDialog).getByLabelText("备注"), { target: { value: "known worker retry" } });
    fireEvent.click(within(whitelistDialog).getByRole("button", { name: "新增白名单" }));

    await waitFor(() => {
      expect(screen.getByText("来源说明：known worker retry")).toBeInTheDocument();
    });

    const whitelistCard = screen.getByText("来源说明：known worker retry").closest(".card");
    expect(whitelistCard).not.toBeNull();
    fireEvent.click(within(whitelistCard as HTMLElement).getByRole("button", { name: "编辑" }));
    const editWhitelistDialog = await screen.findByRole("dialog", { name: "编辑白名单" });
    fireEvent.change(within(editWhitelistDialog).getByLabelText("备注"), { target: { value: "known worker retry updated" } });
    fireEvent.click(within(editWhitelistDialog).getByRole("button", { name: "保存白名单" }));

    await waitFor(() => {
      expect(screen.getByText("来源说明：known worker retry updated")).toBeInTheDocument();
    });
  });

  it("opens import export modals and keeps toggle plus delete actions working", async () => {
    render(<WhitelistsPage />);

    fireEvent.click((await screen.findAllByRole("button", { name: "导出 JSON" }))[0]);
    const keywordExportDialog = await screen.findByRole("dialog", { name: "导出关键字" });
    expect((within(keywordExportDialog).getByLabelText("已导出 JSON") as HTMLTextAreaElement).value).toContain("connection refused");
    fireEvent.click(within(keywordExportDialog).getAllByRole("button", { name: "关闭" })[0]);

    fireEvent.click(screen.getByRole("button", { name: "导入关键字" }));
    const keywordImportDialog = await screen.findByRole("dialog", { name: "导入关键字" });
    fireEvent.change(within(keywordImportDialog).getByLabelText("导入关键字 JSON"), {
      target: { value: '[{"keyword":"oom","category":"runtime","severity":"critical","enabled":true,"description":"memory spike","builtin":false}]' },
    });
    fireEvent.click(within(keywordImportDialog).getByRole("button", { name: "导入关键字" }));

    await waitFor(() => {
      expect(screen.getByText("oom")).toBeInTheDocument();
    });

    const importedKeywordCard = screen.getByText("oom").closest(".card");
    expect(importedKeywordCard).not.toBeNull();
    fireEvent.click(within(importedKeywordCard as HTMLElement).getByRole("button", { name: "停用" }));

    await waitFor(() => {
      expect(within(importedKeywordCard as HTMLElement).getAllByText("停用")[0]).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByRole("button", { name: "导出 JSON" })[1]);
    const whitelistExportDialog = await screen.findByRole("dialog", { name: "导出白名单" });
    expect((within(whitelistExportDialog).getByLabelText("已导出 JSON") as HTMLTextAreaElement).value).toContain("warmup noise");
    fireEvent.click(within(whitelistExportDialog).getAllByRole("button", { name: "关闭" })[0]);

    fireEvent.click(screen.getByRole("button", { name: "导入白名单" }));
    const whitelistImportDialog = await screen.findByRole("dialog", { name: "导入白名单" });
    fireEvent.change(within(whitelistImportDialog).getByLabelText("导入白名单 JSON"), {
      target: { value: '[{"namespace":"qa","label_selector":"app=batch","pod_name_pattern":"batch-*","container_name":"batch","keyword":"oom","enabled":true,"note":"batch retry"}]' },
    });
    fireEvent.click(within(whitelistImportDialog).getByRole("button", { name: "导入白名单" }));

    await waitFor(() => {
      expect(screen.getByText("来源说明：batch retry")).toBeInTheDocument();
    });

    const importedWhitelistCard = screen.getByText("来源说明：batch retry").closest(".card");
    expect(importedWhitelistCard).not.toBeNull();
    fireEvent.click(within(importedWhitelistCard as HTMLElement).getByRole("button", { name: "删除" }));

    await waitFor(() => {
      expect(screen.queryByText("来源说明：batch retry")).not.toBeInTheDocument();
    });
  });
});
