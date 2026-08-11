import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { configureApiSession } from "../api/client";
import { LogRecordingsPage } from "./LogRecordingsPage";

const fetchMock = vi.fn();
const scrollIntoViewMock = vi.fn();

const baseRecording = {
  id: 1,
  name: "支付 500 复现",
  namespace: "demo",
  note: "checkout",
  status: "recording",
  started_at: "2026-08-09T10:00:00Z",
  ended_at: null,
  planned_end_at: "2026-08-09T10:20:00Z",
  duration_source: "system_default",
  duration_minutes: 20,
  stop_reason: null,
  pod_count: 1,
  container_count: 1,
  raw_line_count: 3,
  folded_line_count: 2,
  total_bytes: 256,
  truncated: false,
  created_by: "admin",
  created_at: "2026-08-09T10:00:00Z",
  updated_at: "2026-08-09T10:00:00Z",
};

function json(data: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } }));
}

describe("LogRecordingsPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    Element.prototype.scrollIntoView = scrollIntoViewMock;
    configureApiSession("csrf-token-at-least-16");
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    fetchMock.mockReset();
    scrollIntoViewMock.mockReset();
    configureApiSession(null);
  });

  it("shows storage usage and stops a running recording from the list", async () => {
    const records: Record<string, unknown>[] = [baseRecording];
    fetchMock.mockImplementation((input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/discovery/namespaces")) {
        return json({
          executed_at: "2026-08-09T10:00:00Z",
          namespaces: [{ name: "demo", status: "healthy", pod_count: 1, abnormal_pod_count: 0, last_inspected_at: null, labels: {}, abnormal_categories: [] }],
        });
      }
      if (url.endsWith("/log-recordings/storage")) {
        return json({ used_bytes: 256, max_bytes: 10737418240, used_percent: 1, warning_threshold_percent: 80, warning: false, full: false });
      }
      if (url.includes("/log-recordings?")) {
        return json({ items: records, total: records.length, page: 1, page_size: 20 });
      }
      if (url.endsWith("/log-recordings/1/stop") && init?.method === "POST") {
        records[0] = { ...baseRecording, status: "completed", ended_at: "2026-08-09T10:03:00Z", stop_reason: "user_stopped" };
        return json(records[0]);
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    render(<LogRecordingsPage />);

    expect(await screen.findByText("日志存储：256 B / 10.0 GiB (1%)")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "开始记录" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "结束" }));

    await waitFor(() => expect(screen.getByText("记录已结束")).toBeInTheDocument());
    expect(screen.getByText("用户手动结束")).toBeInTheDocument();
  });

  it("opens details, switches logs, searches with highlight, and runs template matching", async () => {
    fetchMock.mockImplementation((input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/discovery/namespaces")) {
        return json({
          executed_at: "2026-08-09T10:00:00Z",
          namespaces: [{ name: "demo", status: "warning", pod_count: 1, abnormal_pod_count: 1, last_inspected_at: null, labels: {}, abnormal_categories: ["log_keyword"] }],
        });
      }
      if (url.endsWith("/log-recordings/storage")) {
        return json({ used_bytes: 512, max_bytes: 10737418240, used_percent: 1, warning_threshold_percent: 80, warning: false, full: false });
      }
      if (url.includes("/log-recordings?")) {
        return json({ items: [{ ...baseRecording, status: "completed", ended_at: "2026-08-09T10:03:00Z", stop_reason: "user_stopped" }], total: 1, page: 1, page_size: 20 });
      }
      if (url.endsWith("/log-recordings/1/pods")) {
        return json([{
          id: 1,
          recording_id: 1,
          namespace: "demo",
          pod_uid: "pod-uid",
          pod_name: "api-0",
          node_name: "node-1",
          owner_kind: "Deployment",
          owner_name: "api",
          container_count: 1,
          raw_line_count: 2,
          folded_line_count: 2,
          keyword_hit_count: 1,
          deleted_during_recording: false,
          truncated: false,
          collection_error: null,
          container_names: ["api"],
        }]);
      }
      if (url.includes("/log-recordings/1/pods/api-0/containers/api/logs")) {
        expect(url).toContain("view=folded");
        return json({
          items: [
            { id: 11, recording_id: 1, pod_uid: "pod-uid", pod_name: "api-0", container_name: "api", log_time: "2026-08-09T10:01:00Z", collected_at: "2026-08-09T10:01:01Z", line_text: "Authorization: Bearer [REDACTED]", normalized_fingerprint: "auth", repeat_count: 1, first_seen_at: "2026-08-09T10:01:01Z", last_seen_at: "2026-08-09T10:01:01Z", redacted: true, folded: true, byte_size: 32 },
            { id: 12, recording_id: 1, pod_uid: "pod-uid", pod_name: "api-0", container_name: "api", log_time: "2026-08-09T10:02:00Z", collected_at: "2026-08-09T10:02:01Z", line_text: "database timeout while checkout", normalized_fingerprint: "timeout", repeat_count: 2, first_seen_at: "2026-08-09T10:02:01Z", last_seen_at: "2026-08-09T10:02:03Z", redacted: true, folded: true, byte_size: 64 },
          ],
          total: 2,
          page: 1,
          page_size: 100,
          view: "folded",
          redacted: true,
        });
      }
      if (url.endsWith("/log-recordings/1/template-match") && init?.method === "POST") {
        return json([{
          id: 1,
          recording_id: 1,
          template_id: 7,
          template_name: "数据库超时",
          severity: "warning",
          namespace: "demo",
          pod_name: "api-0",
          container_name: "api",
          keyword: "timeout",
          matched_context: "database timeout while checkout",
          suggestion: "检查数据库连接",
          created_at: "2026-08-09T10:04:00Z",
        }]);
      }
      if (url.endsWith("/templates")) {
        return json([{
          id: 7,
          name: "数据库超时",
          scenario: "targeted_diagnosis",
          targets: [{ target_ref: "api", namespace: "demo", resource_scope: ["pods"] }],
          match_conditions: [{
            target_ref: "api",
            condition_type: "log_keyword",
            operator: "contains",
            expected_value: "timeout",
            enabled: true,
          }],
          joint_rule: { operator: "AND" },
          reason: "数据库响应超时",
          suggestion: "检查数据库连接",
          command: "kubectl logs deploy/api",
          risk_note: "只读命令",
          enabled: true,
          created_at: "2026-08-09T09:00:00Z",
          updated_at: "2026-08-09T09:00:00Z",
        }]);
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    render(<LogRecordingsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "查看" }));
    expect(await screen.findByText("api-0")).toBeInTheDocument();
    expect(screen.getByText(/名称空间：demo/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "复制" })).not.toBeInTheDocument();
    expect(await screen.findByText(/database timeout while checkout/)).toBeInTheDocument();
    expect(screen.getByText(/Bearer \[REDACTED]/)).toBeInTheDocument();
    expect(screen.getByText(/Bearer \[REDACTED]/).closest(".log-recording-line")?.querySelector(".log-recording-repeat")).not.toBeNull();

    fireEvent.change(screen.getByPlaceholderText("搜索当前日志"), { target: { value: "timeout" } });
    expect(screen.getByText("1 行命中")).toBeInTheDocument();
    expect(screen.getByText("timeout")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "下一个" }));
    expect(scrollIntoViewMock).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "清空" }));
    expect(screen.getByPlaceholderText("搜索当前日志")).toHaveValue("");

    fireEvent.click(screen.getByRole("button", { name: "模板匹配" }));
    const row = await screen.findByText("数据库超时");
    expect(screen.getByText("已命中 1 条模板结果，是否查看？")).toBeInTheDocument();
    fireEvent.click(within(screen.getByRole("alertdialog", { name: "发现命中模板" })).getByRole("button", { name: "查看" }));
    await waitFor(() => expect(scrollIntoViewMock).toHaveBeenCalled());
    expect(screen.getByRole("columnheader", { name: "命中模板" })).toHaveClass("log-recording-match-heading");
    const matchRow = row.closest("tr") as HTMLElement;
    expect(within(matchRow).getByText("demo")).toBeInTheDocument();
    expect(within(matchRow).getByText("检查数据库连接")).toBeInTheDocument();
    fireEvent.click(within(matchRow).getByRole("button", { name: "详情" }));
    const dialog = await screen.findByRole("dialog", { name: "命中模板详情" });
    expect(within(dialog).getByText("数据库响应超时")).toBeInTheDocument();
    expect(within(dialog).getByText("kubectl logs deploy/api")).toBeInTheDocument();
    expect(within(dialog).getByText("database timeout while checkout")).toBeInTheDocument();
  });
});
