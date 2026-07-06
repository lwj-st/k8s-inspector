import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TemplatesPage } from "./TemplatesPage";

const fetchMock = vi.fn();

describe("TemplatesPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify([
          {
            id: 1,
            name: "网关 502 模板",
            scenario: "gateway",
            object_scope: "deployment",
            namespace_scope: "gateway-system",
            label_selector: "app=gateway",
            match_conditions: [
              {
                target_ref: "gateway",
                condition_type: "log_keyword",
                operator: "contains",
                expected_value: "connect() failed",
              },
              {
                target_ref: "gateway",
                condition_type: "pod_status",
                operator: "equals",
                expected_value: "CrashLoopBackOff",
              },
            ],
            joint_rule: { operator: "AND" },
            reason: "网关进程反复失败",
            suggestion: "检查上游连通性和配置",
            enabled: true,
          },
        ]),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
  });

  it("renders template conditions as natural language blocks", async () => {
    render(<TemplatesPage />);

    expect(await screen.findByText("模板录入建议")).toBeInTheDocument();
    expect(await screen.findByText("网关 502 模板")).toBeInTheDocument();
    expect(await screen.findByText(/对象组 gateway 在日志中包含 connect\(\) failed/)).toBeInTheDocument();
    expect(await screen.findByText(/对象组 gateway 的 Pod 状态等于 CrashLoopBackOff/)).toBeInTheDocument();
    expect(await screen.findByText("条件关系：AND")).toBeInTheDocument();
  });
});
