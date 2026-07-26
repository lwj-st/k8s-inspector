import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Coverage } from "../api/types";
import { InspectionOutcomePanel } from "./InspectionOutcomePanel";

afterEach(cleanup);

function coverage(status: Coverage["status"]): Coverage[] {
  return [{
    check_code: `check-${status}`,
    name: `检查 ${status}`,
    status,
    reason: status === "passed" ? null : "证据未完整获取",
    checked_objects: 0,
    duration_ms: 10,
    issue_count: 0,
  }];
}

describe("InspectionOutcomePanel", () => {
  it.each(["failed", "skipped"] as const)(
    "does not present healthy when coverage is %s",
    (coverageStatus) => {
      render(
        <InspectionOutcomePanel
          healthStatus="healthy"
          coverage={coverage(coverageStatus)}
        />,
      );

      expect(screen.queryByText("正常")).not.toBeInTheDocument();
      expect(screen.getByText("未知")).toBeInTheDocument();
      expect(screen.getByText("当前证据不足，无法判断整体健康状态（存在未完成的检查）。")).toBeInTheDocument();
    },
  );

  it.each(["unknown", "future_health_state"])(
    "does not present %s as healthy",
    (healthStatus) => {
      render(
        <InspectionOutcomePanel
          healthStatus={healthStatus}
          coverage={coverage("passed")}
        />,
      );

      expect(screen.queryByText("正常")).not.toBeInTheDocument();
      expect(screen.getByText("未知")).toBeInTheDocument();
    },
  );
});
