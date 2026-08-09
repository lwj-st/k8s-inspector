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

function settingsResponse() {
  return {
    inspection_policy: {
      reproduction_logs: {
        default_duration_minutes: 20,
        max_duration_minutes: 20,
        max_namespace_pods: 200,
        max_recording_bytes: 209715200,
        max_pod_bytes: 20971520,
        global_storage_bytes: 10737418240,
        storage_warning_percent: 80,
        duplicate_folding_enabled: true,
        auto_cleanup_enabled: false,
        max_log_inspection_range_minutes: 120,
        custom_redaction_rules: [],
      },
    },
  };
}

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

  it("starts a recording, shows running state, and stops it", async () => {
    const records: Record<string, unknown>[] = [baseRecording];
    fetchMock.mockImplementation((input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/discovery/namespaces")) {
        return json({
          executed_at: "2026-08-09T10:00:00Z",
          namespaces: [{ name: "demo", status: "healthy", pod_count: 1, abnormal_pod_count: 0, last_inspected_at: null, labels: {}, abnormal_categories: [] }],
        });
      }
      if (url.endsWith("/settings")) {
        return json(settingsResponse());
      }
      if (url.endsWith("/log-recordings/storage")) {
        return json({ used_bytes: 256, max_bytes: 10737418240, used_percent: 1, warning_threshold_percent: 80, warning: false, full: false });
      }
      if (url.includes("/log-recordings?")) {
        return json({ items: records, total: records.length, page: 1, page_size: 20 });
      }
      if (url.endsWith("/log-recordings/preview") && init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toEqual({ namespace: "demo" });
        return json({ namespace: "demo", pod_count: 1, container_count: 1, allowed: true, reason: null });
      }
      if (url.endsWith("/log-recordings") && init?.method === "POST") {
        expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-token-at-least-16");
        expect(JSON.parse(String(init.body))).toMatchObject({
          name: "支付 500 复现",
          namespace: "demo",
          duration_source: "system_default",
        });
        return json(baseRecording, 201);
      }
      if (url.endsWith("/log-recordings/1/stop") && init?.method === "POST") {
        records[0] = { ...baseRecording, status: "completed", ended_at: "2026-08-09T10:03:00Z", stop_reason: "user_stopped" };
        return json(records[0]);
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    render(<LogRecordingsPage />);

    expect(await screen.findByText("使用系统默认（20 分钟）")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("日志名称"), { target: { value: "支付 500 复现" } });
    fireEvent.change(screen.getAllByLabelText("名称空间")[0], { target: { value: "demo" } });
    fireEvent.click(screen.getByRole("button", { name: "开始记录" }));

    expect(await screen.findByText("已开始记录")).toBeInTheDocument();
    expect(screen.getByText(/自动结束倒计时/)).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "结束记录" })[0]);

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
      if (url.endsWith("/settings")) {
        return json(settingsResponse());
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
          pod_name: "api-0",
          container_name: "api",
          keyword: "timeout",
          matched_context: "database timeout while checkout",
          suggestion: "检查数据库连接",
          created_at: "2026-08-09T10:04:00Z",
        }]);
      }

      throw new Error(`Unexpected request: ${url}`);
    });

    render(<LogRecordingsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "查看" }));
    expect(await screen.findByText("api-0")).toBeInTheDocument();
    expect(await screen.findByText(/database timeout while checkout/)).toBeInTheDocument();
    expect(screen.getByText(/Bearer \[REDACTED]/)).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("搜索当前日志"), { target: { value: "timeout" } });
    expect(screen.getByText("1 行命中")).toBeInTheDocument();
    expect(screen.getByText("timeout")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "下一个" }));
    expect(scrollIntoViewMock).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "清空" }));
    expect(screen.getByPlaceholderText("搜索当前日志")).toHaveValue("");

    fireEvent.click(screen.getByRole("button", { name: "模板匹配" }));
    const row = await screen.findByText("数据库超时");
    expect(within(row.closest("tr") as HTMLElement).getByText("检查数据库连接")).toBeInTheDocument();
  });
});
