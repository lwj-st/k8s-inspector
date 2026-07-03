import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { NamespaceInspectionPage } from "./NamespaceInspectionPage";

const fetchMock = vi.fn();

describe("NamespaceInspectionPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          namespace: "demo",
          health_status: "warning",
          executed_at: "2026-07-03T10:00:00Z",
          pods: [
            {
              name: "demo-api-1",
              status: "CrashLoopBackOff",
              restarts: 6,
              events: ["BackOff: restart container"],
              describe_summary: "startup failed",
              log_summary: "database connection refused",
              resource_usage: { cpu: "220m", memory: "180Mi" },
            },
            {
              name: "demo-worker-1",
              status: "Running",
              restarts: 0,
              events: [],
              describe_summary: "running",
              log_summary: null,
              resource_usage: { cpu: "40m", memory: "60Mi" },
            },
          ],
          services: [],
          ingresses: [],
          tls_secrets: [],
          daemonsets: [],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
  });

  it("shows pod evidence details after inspection", async () => {
    render(<NamespaceInspectionPage />);

    fireEvent.click(screen.getByRole("button", { name: "运行巡检" }));

    expect(await screen.findByText("证据详情")).toBeInTheDocument();
    expect(await screen.findByText("BackOff: restart container")).toBeInTheDocument();
    expect(await screen.findByText("database connection refused")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /demo-worker-1/ }));

    expect(await screen.findByText("无事件")).toBeInTheDocument();
    expect(await screen.findByText("无日志摘要")).toBeInTheDocument();
  });
});
