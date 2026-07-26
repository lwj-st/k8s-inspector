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
        <StatusBadge status="matched" />
        <StatusBadge status="error" />
        <StatusBadge status="failed" />
        <StatusBadge status="degraded" />
        <StatusBadge status="critical" />
        <StatusBadge status="recovered" />
        <StatusBadge status="passed" />
        <StatusBadge status="abnormal" />
        <StatusBadge status="skipped" />
        <StatusBadge status="partial" />
        <StatusBadge status="not_ready" />
        <StatusBadge status="CrashLoopBackOff" />
      </div>,
    );

    expect(screen.getByText("启用")).toBeInTheDocument();
    expect(screen.getByText("停用")).toBeInTheDocument();
    expect(screen.getByText("加载中")).toBeInTheDocument();
    expect(screen.getByText("信息")).toBeInTheDocument();
    expect(screen.getByText("未知")).toBeInTheDocument();
    expect(screen.getByText("正常")).toBeInTheDocument();
    expect(screen.getByText("运行中")).toBeInTheDocument();
    expect(screen.getByText("就绪")).toBeInTheDocument();
    expect(screen.getAllByText("已完成")).toHaveLength(2);
    expect(screen.getByText("告警")).toBeInTheDocument();
    expect(screen.getByText("已命中")).toBeInTheDocument();
    expect(screen.getByText("异常")).toBeInTheDocument();
    expect(screen.getByText("失败")).toBeInTheDocument();
    expect(screen.getByText("降级")).toBeInTheDocument();
    expect(screen.getByText("严重")).toBeInTheDocument();
    expect(screen.getByText("已恢复")).toBeInTheDocument();
    expect(screen.getByText("已检查，无异常")).toBeInTheDocument();
    expect(screen.getByText("已检查，发现异常")).toBeInTheDocument();
    expect(screen.getByText("未检查/不适用")).toBeInTheDocument();
    expect(screen.getByText("部分完成")).toBeInTheDocument();
    expect(screen.getByText("未就绪")).toBeInTheDocument();
    expect(screen.getByText("CrashLoopBackOff")).toBeInTheDocument();
  });

  it("keeps tone classes unchanged", () => {
    const { container } = render(
      <div>
        <StatusBadge status="enabled" />
        <StatusBadge status="healthy" />
        <StatusBadge status="running" />
        <StatusBadge status="warning" />
        <StatusBadge status="matched" />
        <StatusBadge status="info" />
        <StatusBadge status="error" />
        <StatusBadge status="skipped" />
        <StatusBadge status="partial" />
        <StatusBadge status="not_ready" />
        <StatusBadge status="CrashLoopBackOff" />
      </div>,
    );

    const badges = container.querySelectorAll(".status-badge");
    expect(badges[0]).toHaveClass("status-good");
    expect(badges[1]).toHaveClass("status-good");
    expect(badges[2]).toHaveClass("status-neutral");
    expect(badges[3]).toHaveClass("status-warn");
    expect(badges[4]).toHaveClass("status-warn");
    expect(badges[5]).toHaveClass("status-neutral");
    expect(badges[6]).toHaveClass("status-bad");
    expect(badges[7]).toHaveClass("status-neutral");
    expect(badges[8]).toHaveClass("status-warn");
    expect(badges[9]).toHaveClass("status-bad");
    expect(badges[10]).toHaveClass("status-bad");
  });
});
