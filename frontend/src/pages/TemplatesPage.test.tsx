import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TemplatesPage } from "./TemplatesPage";

const fetchMock = vi.fn();

describe("TemplatesPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);

    const templates = [
      {
        id: 1,
        name: "网关 502 模板",
        scenario: "gateway",
        target_groups: [
          {
            ref: "gateway",
            namespace: "gateway-system",
            label_selector: "app=gateway",
            name: "gateway-*",
            resource_scope: ["deployment"],
          },
        ],
        targets: [
          {
            target_ref: "gateway",
            namespace: "gateway-system",
            label_selector: "app=gateway",
            pod_name_pattern: "gateway-*",
            resource_scope: ["deployment"],
          },
        ],
        match_conditions: [
          {
            target_ref: "gateway",
            condition_type: "log_keyword",
            operator: "contains",
            expected_value: "connect() failed",
            join_operator: "AND",
            enabled: true,
          },
        ],
        joint_rule: { operator: "AND" },
        reason: "网关进程反复失败",
        suggestion: "检查上游连通性和配置",
        command: null,
        risk_note: null,
        enabled: true,
      },
      {
        id: 3,
        name: "兼容旧模板",
        scenario: "legacy",
        target_groups: [
          {
            ref: "legacy",
            namespace: "legacy-system",
            label_selector: "app=legacy",
            name: "legacy-*",
            object_scope: "deployment",
          },
        ],
        targets: [],
        match_conditions: [
          {
            target_ref: "legacy",
            condition_type: "log_keyword",
            operator: "contains",
            expected_value: "legacy timeout",
            join_operator: "AND",
            enabled: true,
          },
        ],
        joint_rule: { operator: "AND" },
        reason: "旧结构导入",
        suggestion: "检查旧服务",
        command: null,
        risk_note: null,
        enabled: true,
      },
    ];

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/templates") && (!init || init.method === undefined)) {
        return Promise.resolve(
          new Response(JSON.stringify(templates), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/templates") && init?.method === "POST") {
        const payload = JSON.parse(String(init.body));
        const created = { id: 2, ...payload };
        templates.unshift(created);
        return Promise.resolve(
          new Response(JSON.stringify(created), { status: 201, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/templates/1") && init?.method === "PUT") {
        const payload = JSON.parse(String(init.body));
        templates[0] = { ...templates[0], ...payload };
        return Promise.resolve(
          new Response(JSON.stringify(templates[0]), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/templates/1/disable")) {
        templates[0] = { ...templates[0], enabled: false };
        return Promise.resolve(
          new Response(JSON.stringify(templates[0]), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/templates/1/enable")) {
        templates[0] = { ...templates[0], enabled: true };
        return Promise.resolve(
          new Response(JSON.stringify(templates[0]), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/templates/export")) {
        return Promise.resolve(
          new Response(JSON.stringify(templates), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/templates/import") && init?.method === "POST") {
        const payload = JSON.parse(String(init.body));
        const imported = payload.map((item: Record<string, unknown>, index: number) => ({ id: index + 10, ...item }));
        templates.unshift(...imported.reverse());
        return Promise.resolve(
          new Response(JSON.stringify(imported), { status: 200, headers: { "Content-Type": "application/json" } }),
        );
      }

      if (url.endsWith("/templates/1") && init?.method === "DELETE") {
        return Promise.resolve(new Response(null, { status: 204 }));
      }

      if (url.endsWith("/discovery/namespaces")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              executed_at: "2026-07-21T10:00:00Z",
              namespaces: [
                { name: "demo", status: "healthy", pod_count: 2, abnormal_pod_count: 0, last_inspected_at: null, labels: {}, abnormal_categories: [] },
                { name: "gateway-system", status: "warning", pod_count: 1, abnormal_pod_count: 1, last_inspected_at: null, labels: {}, abnormal_categories: ["log_keyword"] },
                { name: "legacy-system", status: "healthy", pod_count: 1, abnormal_pod_count: 0, last_inspected_at: null, labels: {}, abnormal_categories: [] },
              ],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/discovery/namespaces/demo/labels")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({ namespace: "demo", executed_at: "2026-07-21T10:00:00Z", labels: [{ key: "app", values: ["api"], selector: "app=api", pod_count: 2 }] }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/discovery/namespaces/gateway-system/labels")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({ namespace: "gateway-system", executed_at: "2026-07-21T10:00:00Z", labels: [{ key: "app", values: ["gateway"], selector: "app=gateway", pod_count: 1 }] }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/discovery/namespaces/legacy-system/labels")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({ namespace: "legacy-system", executed_at: "2026-07-21T10:00:00Z", labels: [{ key: "app", values: ["legacy"], selector: "app=legacy", pod_count: 1 }] }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      throw new Error(`Unexpected request: ${url}`);
    });
  });

  afterEach(() => {
    cleanup();
    fetchMock.mockReset();
    vi.unstubAllGlobals();
  });

  it("shows step-based authoring flow and keeps import/export hidden by default", async () => {
    render(<TemplatesPage />);

    expect(await screen.findByRole("button", { name: "新增模板" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "模板录入器" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("导入模板 JSON")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("已导出 JSON")).not.toBeInTheDocument();
    expect(await screen.findByText("网关 502 模板")).toBeInTheDocument();
  });

  it("moves to target step and supports editing target scope", async () => {
    const user = userEvent.setup();
    render(<TemplatesPage />);

    await user.click(await screen.findByRole("button", { name: "新增模板" }));
    const editor = await screen.findByRole("dialog", { name: "模板录入器" });
    await user.click(within(editor).getByRole("button", { name: "下一步" }));
    expect(within(editor).getByRole("heading", { name: "对象组" })).toBeInTheDocument();

    await user.click(within(editor).getByRole("button", { name: "新增对象组" }));
    await user.selectOptions(within(editor).getByLabelText("名称空间 2"), "demo");
    await screen.findByRole("option", { name: "app=api（2 个 Pod）" });
    await user.selectOptions(within(editor).getByLabelText("Label Selector 2"), "app=api");

    expect(within(editor).getByLabelText("名称空间 2")).toHaveValue("demo");
    expect(within(editor).getByLabelText("Label Selector 2")).toHaveValue("app=api");
  });

  it("uses chinese labels in condition step but keeps payload enums unchanged on create", async () => {
    const user = userEvent.setup();
    render(<TemplatesPage />);

    await user.click(await screen.findByRole("button", { name: "新增模板" }));
    const editor = await screen.findByRole("dialog", { name: "模板录入器" });

    await user.type(within(editor).getByLabelText("模板名称"), "新模板");
    await user.clear(within(editor).getByLabelText("场景标识"));
    await user.type(within(editor).getByLabelText("场景标识"), "targeted_diagnosis");
    await user.click(within(editor).getByRole("button", { name: "下一步" }));
    await user.selectOptions(within(editor).getByLabelText("名称空间"), "demo");
    await user.click(within(editor).getByRole("button", { name: "下一步" }));

    expect(within(editor).getByRole("option", { name: "日志包含关键字" })).toBeInTheDocument();
    expect(within(editor).getByRole("option", { name: "包含" })).toBeInTheDocument();

    await user.selectOptions(within(editor).getByLabelText("条件类型"), "pod_status");
    await user.selectOptions(within(editor).getByLabelText("匹配方式"), "in");
    await user.clear(within(editor).getByLabelText("目标值"));
    await user.type(within(editor).getByLabelText("目标值"), "CrashLoopBackOff, ImagePullBackOff");
    await user.click(within(editor).getByRole("button", { name: "下一步" }));
    await user.type(within(editor).getByLabelText("诊断原因"), "Pod 状态异常");
    await user.type(within(editor).getByLabelText("处理建议"), "检查镜像和依赖");
    await user.click(within(editor).getByRole("button", { name: "下一步" }));
    await user.click(within(editor).getByRole("button", { name: "新增模板" }));

    await waitFor(() => {
      const request = fetchMock.mock.calls.find(
        ([input, init]) => String(input).endsWith("/templates") && init?.method === "POST",
      );
      expect(request).toBeDefined();
      expect(JSON.parse(String(request?.[1]?.body))).toEqual({
        name: "新模板",
        scenario: "targeted_diagnosis",
        targets: [
          {
            target_ref: "group-1",
            namespace: "demo",
            label_selector: null,
            pod_name_pattern: null,
            resource_scope: ["pods"],
          },
        ],
        match_conditions: [
          {
            target_ref: "group-1",
            condition_type: "pod_status",
            operator: "in",
            expected_value: ["CrashLoopBackOff", "ImagePullBackOff"],
            join_operator: "AND",
            enabled: true,
          },
        ],
        joint_rule: { operator: "AND" },
        reason: "Pod 状态异常",
        suggestion: "检查镜像和依赖",
        command: null,
        risk_note: null,
        enabled: true,
      });
    });
  });

  it("shows preview summary and explicit validation message before save", async () => {
    const user = userEvent.setup();
    render(<TemplatesPage />);

    await user.click(await screen.findByRole("button", { name: "新增模板" }));
    const editor = await screen.findByRole("dialog", { name: "模板录入器" });
    await user.click(within(editor).getByRole("button", { name: "5 预览与保存" }));
    await user.click(within(editor).getByRole("button", { name: "新增模板" }));

    expect(await screen.findByText(/还缺这些内容：/)).toBeInTheDocument();
    expect(screen.getByText(/基本信息 - 请填写模板名称/)).toBeInTheDocument();
  });

  it("opens import and export in modals", async () => {
    const user = userEvent.setup();
    render(<TemplatesPage />);

    await user.click(await screen.findByRole("button", { name: "导出模板" }));
    const exportDialog = await screen.findByRole("dialog", { name: "导出模板" });
    expect(within(exportDialog).getByLabelText("已导出 JSON")).toBeInTheDocument();
    await user.click(within(exportDialog).getAllByRole("button", { name: "关闭" })[0]);
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "导出模板" })).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "导入模板" }));
    const importDialog = await screen.findByRole("dialog", { name: "导入模板" });
    fireEvent.change(within(importDialog).getByLabelText("导入模板 JSON"), {
      target: {
        value: JSON.stringify([
          {
            name: "导入模板",
            scenario: "demo_case",
            targets: [{ target_ref: "group-1", namespace: "demo", label_selector: null, pod_name_pattern: null, resource_scope: ["pods"] }],
            match_conditions: [{ target_ref: "group-1", condition_type: "log_keyword", operator: "contains", expected_value: "timeout", join_operator: "AND", enabled: true }],
            joint_rule: { operator: "AND" },
            reason: "依赖超时",
            suggestion: "检查网络",
            command: null,
            risk_note: null,
            enabled: true,
          },
        ]),
      },
    });
    await user.click(within(importDialog).getByRole("button", { name: "导入模板" }));

    expect(await screen.findByText("已导入 1 个模板")).toBeInTheDocument();
    expect(await screen.findByText("依赖超时")).toBeInTheDocument();
  });

  it("fills step form when editing existing template and supports list actions", async () => {
    const user = userEvent.setup();
    render(<TemplatesPage />);

    const gatewayRow = (await screen.findByText("网关 502 模板")).closest("tr");
    expect(gatewayRow).not.toBeNull();

    await user.click(within(gatewayRow as HTMLElement).getByRole("button", { name: "编辑" }));
    const editor = await screen.findByRole("dialog", { name: "模板录入器" });
    expect(await screen.findByText("正在编辑模板：网关 502 模板")).toBeInTheDocument();
    expect(within(editor).getByLabelText("模板名称")).toHaveValue("网关 502 模板");

    await user.click(within(editor).getByRole("button", { name: "2 目标范围" }));
    expect(within(editor).getByLabelText("名称空间")).toHaveValue("gateway-system");
    await user.click(within(editor).getByRole("button", { name: "3 匹配条件" }));
    expect(within(editor).getByLabelText("条件类型")).toHaveValue("log_keyword");
    await user.click(within(editor).getByRole("button", { name: "4 原因与建议" }));
    expect(within(editor).getByLabelText("诊断原因")).toHaveValue("网关进程反复失败");

    await user.click(within(editor).getByRole("button", { name: "关闭" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "模板录入器" })).not.toBeInTheDocument();
    });
    const updatedGatewayRow = screen.getByText("网关 502 模板").closest("tr");
    expect(updatedGatewayRow).not.toBeNull();
    await user.click(within(updatedGatewayRow as HTMLElement).getByRole("button", { name: "停用" }));
    await waitFor(() => {
      expect(within(updatedGatewayRow as HTMLElement).getAllByText("停用")[0]).toBeInTheDocument();
      expect(within(updatedGatewayRow as HTMLElement).getByRole("button", { name: "启用" })).toBeInTheDocument();
    });
  });

  it("uses compatible target_groups when editing templates without targets", async () => {
    const user = userEvent.setup();
    render(<TemplatesPage />);

    const legacyRow = (await screen.findByText("兼容旧模板")).closest("tr");
    expect(legacyRow).not.toBeNull();

    await user.click(within(legacyRow as HTMLElement).getByRole("button", { name: "编辑" }));
    const editor = await screen.findByRole("dialog", { name: "模板录入器" });
    await user.click(within(editor).getByRole("button", { name: "2 目标范围" }));

    expect(within(editor).getByLabelText("对象组标识 1")).toHaveValue("legacy");
    expect(within(editor).getByLabelText("名称空间")).toHaveValue("legacy-system");
    expect(within(editor).getByLabelText("Label Selector 1")).toHaveValue("app=legacy");
    expect(within(editor).queryByLabelText("Pod 名称模式 1")).not.toBeInTheDocument();
    expect(within(editor).queryByLabelText("Deployment")).not.toBeInTheDocument();
  });
});
