import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DiagnosisPage } from "./DiagnosisPage";

const fetchMock = vi.fn();

describe("DiagnosisPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          status: "matched",
          namespace: null,
          direction: "template_check",
          scope: null,
          executed_at: "2026-07-11T10:00:00Z",
          inspection_target: {
            type: "template",
            namespace: null,
            pod_name: null,
            label_selector: null,
            saved_target_id: null,
            template_id: null,
            resource_scope: ["pods"],
          },
          matches: [
            {
              template_id: 1,
              template_name: "CrashLoop 模板",
              reason: "依赖启动失败",
              suggestion: "检查下游服务",
              command: "kubectl logs -n demo deploy/demo-api",
              risk_note: "只读命令",
              evidence: [
                { type: "pod_status", pods: ["demo-api-0"], value: ["CrashLoopBackOff"] },
                { type: "log_keyword", pod: "demo-api-0", value: "connection refused", matched_text: "database connection refused" },
              ],
              matched_conditions: [
                {
                  target_ref: "api",
                  type: "pod_status",
                  operator: "in",
                  value: ["CrashLoopBackOff"],
                  matched: true,
                  evidence: [{ type: "pod_status", pods: ["demo-api-0"], value: ["CrashLoopBackOff"] }],
                },
                {
                  target_ref: "api",
                  type: "log_keyword",
                  operator: "contains",
                  value: "connection refused",
                  matched: true,
                  evidence: [{ type: "log_keyword", pod: "demo-api-0", value: "connection refused" }],
                },
              ],
              unmatched_conditions: [],
            },
          ],
          template_match_results: [],
          evidence_summary: [],
          llm_supplement: null,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
  });

  it("runs template diagnosis without manual scope inputs and renders condition breakdown", async () => {
    const user = userEvent.setup();

    render(<DiagnosisPage />);

    expect(screen.queryByLabelText("名称空间")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Scope")).not.toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: "运行模板检查" }));

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/diagnoses/run"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({}),
      }),
    );
    expect(await screen.findByText("CrashLoop 模板")).toBeInTheDocument();
    expect(await screen.findByText("命中条件 2")).toBeInTheDocument();
    expect(await screen.findByText(/对象组 api 的 Pod 状态/)).toBeInTheDocument();
    expect(await screen.findByText(/对象组 api 在日志中包含 connection refused/)).toBeInTheDocument();
  });
});
