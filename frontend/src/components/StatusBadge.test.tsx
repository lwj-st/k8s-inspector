import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("maps common statuses to chinese copy while keeping raw kubernetes statuses", () => {
    render(
      <div>
        <StatusBadge status="enabled" />
        <StatusBadge status="disabled" />
        <StatusBadge status="loading" />
        <StatusBadge status="info" />
        <StatusBadge status="unknown" />
        <StatusBadge status="healthy" />
        <StatusBadge status="running" />
        <StatusBadge status="ready" />
        <StatusBadge status="succeeded" />
        <StatusBadge status="completed" />
        <StatusBadge status="warning" />
        <StatusBadge status="error" />
        <StatusBadge status="failed" />
        <StatusBadge status="degraded" />
        <StatusBadge status="critical" />
        <StatusBadge status="CrashLoopBackOff" />
      </div>,
    );

    expect(screen.getByText("启用")).toBeInTheDocument();
    expect(screen.getByText("停用")).toBeInTheDocument();
    expect(screen.getByText("加载中")).toBeInTheDocument();
    expect(screen.getByText("信息")).toBeInTheDocument();
    expect(screen.getByText("未知")).toBeInTheDocument();
    expect(screen.getByText("健康")).toBeInTheDocument();
    expect(screen.getByText("运行中")).toBeInTheDocument();
    expect(screen.getByText("就绪")).toBeInTheDocument();
    expect(screen.getAllByText("已完成")).toHaveLength(2);
    expect(screen.getByText("告警")).toBeInTheDocument();
    expect(screen.getByText("异常")).toBeInTheDocument();
    expect(screen.getByText("失败")).toBeInTheDocument();
    expect(screen.getByText("降级")).toBeInTheDocument();
    expect(screen.getByText("严重")).toBeInTheDocument();
    expect(screen.getByText("CrashLoopBackOff")).toBeInTheDocument();
  });

  it("keeps tone classes unchanged", () => {
    const { container } = render(
      <div>
        <StatusBadge status="enabled" />
        <StatusBadge status="healthy" />
        <StatusBadge status="warning" />
        <StatusBadge status="info" />
        <StatusBadge status="error" />
        <StatusBadge status="CrashLoopBackOff" />
      </div>,
    );

    const badges = container.querySelectorAll(".status-badge");
    expect(badges[0]).toHaveClass("status-good");
    expect(badges[1]).toHaveClass("status-good");
    expect(badges[2]).toHaveClass("status-warn");
    expect(badges[3]).toHaveClass("status-neutral");
    expect(badges[4]).toHaveClass("status-bad");
    expect(badges[5]).toHaveClass("status-bad");
  });
});
