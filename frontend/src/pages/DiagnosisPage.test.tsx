import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DiagnosisPage } from "./DiagnosisPage";

const fetchMock = vi.fn();

describe("DiagnosisPage", () => {
  afterEach(() => {
    cleanup();
    fetchMock.mockReset();
    vi.unstubAllGlobals();
  });

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
  });

  it("runs template diagnosis without manual scope inputs and prioritizes matched, undetermined and collapsed unmatched templates", async () => {
    const user = userEvent.setup();
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
                {
                  type: "log_keyword",
                  pod: "demo-api-0",
                  value: "connection refused",
                  matched_text: "database connection refused",
                  context_text: "booting app\ndial tcp db:5432\ndatabase connection refused\nretry in 3s",
                },
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
          template_match_results: [
            {
              template_id: 1,
              template_name: "CrashLoop 模板",
              matched: true,
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
              summary: "启动异常与日志关键字同时命中",
              reason: "依赖启动失败",
              suggestion: "检查下游服务",
              risk_note: "只读命令",
              evidence_refs: [
                { type: "pod_status", pods: ["demo-api-0"], value: ["CrashLoopBackOff"] },
                {
                  type: "log_keyword",
                  pod: "demo-api-0",
                  value: "connection refused",
                  matched_text: "database connection refused",
                  context_text: "booting app\ndial tcp db:5432\ndatabase connection refused\nretry in 3s",
                },
              ],
            },
            {
              template_id: 2,
              template_name: "Redis 连接失败模板",
              matched: false,
              matched_conditions: [],
              unmatched_conditions: [
                {
                  target_ref: "redis",
                  type: "log_keyword",
                  operator: "contains",
                  value: "redis timeout",
                  matched: false,
                  evidence: [],
                },
              ],
              summary: "当前没有发现 redis timeout 日志",
              reason: "Redis 不可达",
              suggestion: "检查 redis 服务",
              risk_note: null,
              evidence_refs: [],
            },
            {
              template_id: 3,
              template_name: "API 采集失败模板",
              matched: false,
              matched_conditions: [],
              unmatched_conditions: [],
              summary: "无法判断：采集 demo/app=api 失败，错误：Forbidden。",
              reason: "采集 demo/app=api 失败，错误：Forbidden。",
              suggestion: "检查账号权限后重试",
              risk_note: "当前结论不完整",
              evidence_refs: [],
            },
          ],
          evidence_summary: [{ type: "namespace", value: "demo" }],
          llm_supplement: null,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

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
    const panel = await screen.findByLabelText("模板匹配结果");
    expect(within(panel).getAllByText("CrashLoop 模板").length).toBeGreaterThan(0);
    expect(within(panel).getByText("优先关注命中模板")).toBeInTheDocument();
    expect(await screen.findByText("已命中模板")).toBeInTheDocument();
    expect(within(panel).getByRole("heading", { name: "无法判断" })).toBeInTheDocument();
    expect(within(panel).getByText("未命中模板（1）")).toBeInTheDocument();
    expect(within(panel).getByText("命中条件 2")).toBeInTheDocument();
    expect(within(panel).getByText(/对象组 api 的 Pod 状态/)).toBeInTheDocument();
    expect(within(panel).getByText(/对象组 api 在日志中包含 connection refused/)).toBeInTheDocument();
    expect(within(panel).getByText("API 采集失败模板")).toBeInTheDocument();
    expect(within(panel).getByText("无法判断：采集 demo/app=api 失败，错误：Forbidden。")).toBeInTheDocument();

    const unmatchedDetails = within(panel).getByText("未命中模板（1）").closest("details");
    expect(unmatchedDetails).not.toHaveAttribute("open");
    expect(within(unmatchedDetails as HTMLDetailsElement).getAllByText("Redis 连接失败模板").length).toBeGreaterThan(0);

    await user.click(within(unmatchedDetails as HTMLDetailsElement).getByText("未命中模板（1）"));
    expect(unmatchedDetails).toHaveAttribute("open");
    expect(within(unmatchedDetails as HTMLDetailsElement).getByText(/对象组 redis 在日志中包含 redis timeout/)).toBeInTheDocument();
    expect(within(unmatchedDetails as HTMLDetailsElement).getByText("当前没有发现 redis timeout 日志")).toBeInTheDocument();

    await user.click(within(panel).getByText("查看证据（2）"));
    expect(within(panel).getByText("命中上下文（不是完整日志）")).toBeInTheDocument();
    expect(
      within(panel).getByText((_, element) => element?.textContent === "booting app\ndial tcp db:5432\ndatabase connection refused\nretry in 3s"),
    ).toBeInTheDocument();
  });

  it("shows loading state while diagnosis is running", async () => {
    const user = userEvent.setup();
    const pending = { resolve: null as ((value: Response) => void) | null };
    fetchMock.mockImplementation(
      () =>
        new Promise<Response>((resolve) => {
          pending.resolve = resolve;
        }),
    );

    render(<DiagnosisPage />);

    await user.click(await screen.findByRole("button", { name: "运行模板检查" }));

    expect(await screen.findByText("模板匹配中...")).toBeInTheDocument();

    pending.resolve?.(
      new Response(
        JSON.stringify({
          status: "unmatched",
          namespace: null,
          direction: "template_check",
          scope: null,
          executed_at: "2026-07-11T11:00:00Z",
          inspection_target: {
            type: "template",
            namespace: null,
            pod_name: null,
            label_selector: null,
            saved_target_id: null,
            template_id: null,
            resource_scope: ["pods"],
          },
          matches: [],
          template_match_results: [],
          evidence_summary: [],
          llm_supplement: null,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await waitFor(() => {
      expect(screen.queryByText("模板匹配中...")).not.toBeInTheDocument();
    });
  });

  it("shows failure state when diagnosis request fails", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "boom" }), { status: 500 }));

    render(<DiagnosisPage />);

    await user.click(await screen.findByRole("button", { name: "运行模板检查" }));

    expect(await screen.findByText("模板匹配失败：Request failed: 500")).toBeInTheDocument();
  });

  it("shows empty result state when no template matches are returned", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          status: "unmatched",
          namespace: null,
          direction: "template_check",
          scope: null,
          executed_at: "2026-07-11T12:00:00Z",
          inspection_target: {
            type: "template",
            namespace: null,
            pod_name: null,
            label_selector: null,
            saved_target_id: null,
            template_id: null,
            resource_scope: ["pods"],
          },
          matches: [],
          template_match_results: [],
          evidence_summary: [],
          llm_supplement: null,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    render(<DiagnosisPage />);

    await user.click(await screen.findByRole("button", { name: "运行模板检查" }));

    expect(await screen.findByText("本次未命中任何故障模板。")).toBeInTheDocument();
  });
});
