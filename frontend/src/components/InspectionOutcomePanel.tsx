import { useId } from "react";

import type { Coverage, Issue } from "../api/types";
import { CoveragePanel } from "./CoveragePanel";
import { StatusBadge } from "./StatusBadge";

const knownHealthStatuses = new Set(["healthy", "warning", "critical", "unknown", "error"]);

function displayHealthStatus(status: string) {
  return knownHealthStatuses.has(status.toLowerCase()) ? status.toLowerCase() : "unknown";
}

export function InspectionOutcomePanel({
  healthStatus,
  issues = [],
  coverage = [],
  title = "本次巡检结论",
}: {
  healthStatus: string;
  issues?: Issue[];
  coverage?: Coverage[];
  title?: string;
}) {
  const titleId = useId();
  const normalizedHealthStatus = displayHealthStatus(healthStatus);
  const hasIncompleteCoverage = coverage.some(
    (item) => item.status === "skipped" || item.status === "failed",
  );
  const effectiveHealthStatus = normalizedHealthStatus === "healthy" && hasIncompleteCoverage
    ? "unknown"
    : normalizedHealthStatus;

  return (
    <div className="page-section inspection-outcome">
      <section className="panel" aria-labelledby={titleId}>
        <div className="section-header">
          <h3 id={titleId}>{title}</h3>
          <StatusBadge status={effectiveHealthStatus} />
        </div>
        {effectiveHealthStatus === "unknown" ? (
          <p className="feedback-banner feedback-warning">
            当前证据不足，无法判断整体健康状态
            {normalizedHealthStatus === "healthy" && hasIncompleteCoverage
              ? "（存在未完成的检查）。"
              : healthStatus.toLowerCase() === "unknown"
                ? "。"
                : `（服务端状态：${healthStatus}）。`}
          </p>
        ) : null}
        {hasIncompleteCoverage ? (
          <p className="feedback-banner feedback-warning">
            本次有检查跳过或失败，不能据此确认全部正常。
          </p>
        ) : null}
        {issues.length > 0 ? (
          <div className="management-list" aria-label="本次发现的问题">
            {issues.map((issue) => (
              <article className="management-card" key={issue.id}>
                <div className="section-header">
                  <strong>{issue.summary}</strong>
                  <StatusBadge status={issue.severity} />
                </div>
                <p>{issue.resource.kind}/{issue.resource.name} · {issue.resource.namespace ?? "集群级"}</p>
                <small>{issue.reason}</small>
              </article>
            ))}
          </div>
        ) : (
          <p className="inline-note">
            本次未返回问题；是否可以判定正常仍以检查覆盖结果为准。
          </p>
        )}
      </section>
      <CoveragePanel coverage={coverage} title="本次巡检覆盖" />
    </div>
  );
}
