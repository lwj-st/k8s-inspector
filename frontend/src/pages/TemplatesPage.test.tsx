import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TemplatesPage } from "./TemplatesPage";

const fetchMock = vi.fn();

describe("TemplatesPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/templates") && (!init || init.method === undefined)) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
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
            ]),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/templates") && init?.method === "POST") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 2,
              name: "新模板",
              scenario: "targeted_diagnosis",
              target_groups: [
                {
                  ref: "group-1",
                  namespace: "demo",
                  label_selector: null,
                  name: null,
                  resource_scope: ["pods"],
                },
              ],
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
                  condition_type: "log_keyword",
                  operator: "contains",
                  expected_value: "timeout",
                  join_operator: "AND",
                  enabled: true,
                },
              ],
              joint_rule: { operator: "AND" },
              reason: "依赖超时",
              suggestion: "检查网络和依赖服务",
              command: null,
              risk_note: null,
              enabled: true,
            }),
            { status: 201, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/templates/export")) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              {
                id: 1,
                name: "网关 502 模板",
                scenario: "gateway",
                targets: [],
                match_conditions: [],
                reason: "网关进程反复失败",
                suggestion: "检查上游连通性和配置",
                enabled: true,
              },
            ]),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/templates/1/disable")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 1,
              name: "网关 502 模板",
              scenario: "gateway",
              targets: [
                {
                  target_ref: "gateway",
                  namespace: "gateway-system",
                  label_selector: "app=gateway",
                  pod_name_pattern: "gateway-*",
                  resource_scope: ["deployment"],
                },
              ],
              target_groups: [
                {
                  ref: "gateway",
                  namespace: "gateway-system",
                  label_selector: "app=gateway",
                  name: "gateway-*",
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
              enabled: false,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      if (url.endsWith("/templates/2/disable")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 2,
              name: "新模板",
              scenario: "targeted_diagnosis",
              target_groups: [
                {
                  ref: "group-1",
                  namespace: "demo",
                  label_selector: null,
                  name: null,
                  resource_scope: ["pods"],
                },
              ],
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
                  condition_type: "log_keyword",
                  operator: "contains",
                  expected_value: "timeout",
                  join_operator: "AND",
                  enabled: true,
                },
              ],
              joint_rule: { operator: "AND" },
              reason: "依赖超时",
              suggestion: "检查网络和依赖服务",
              command: null,
              risk_note: null,
              enabled: false,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }

      throw new Error(`Unexpected request: ${url}`);
    });
  });

  it("supports visual template creation and list actions", async () => {
    const user = userEvent.setup();

    render(<TemplatesPage />);

    expect(await screen.findByText("模板录入器")).toBeInTheDocument();
    expect(await screen.findByText("网关 502 模板")).toBeInTheDocument();
    expect(await screen.findByText(/对象组 gateway 在日志中包含 connect\(\) failed/)).toBeInTheDocument();

    await user.type(screen.getByLabelText("模板名称"), "新模板");
    await user.clear(screen.getByLabelText("场景标识"));
    await user.type(screen.getByLabelText("场景标识"), "targeted_diagnosis");
    await user.clear(screen.getByLabelText("名称空间"));
    await user.type(screen.getByLabelText("名称空间"), "demo");
    await user.clear(screen.getByLabelText("目标值"));
    await user.type(screen.getByLabelText("目标值"), "timeout");
    await user.type(screen.getByLabelText("诊断原因"), "依赖超时");
    await user.type(screen.getByLabelText("处理建议"), "检查网络和依赖服务");

    await user.click(screen.getByRole("button", { name: "新增模板" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/templates"),
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"name":"新模板"'),
        }),
      );
    });
    expect(await screen.findByText("模板已新增")).toBeInTheDocument();
    expect(await screen.findByText("新模板")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "导出模板 JSON" }));
    expect(await screen.findByDisplayValue(/网关 502 模板/)).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "停用" })[0]);
    expect(await screen.findByText("disabled")).toBeInTheDocument();
  });
});
