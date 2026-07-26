import { useId } from "react";

import type { Coverage } from "../api/types";
import { StatusBadge } from "./StatusBadge";

const coverageRank: Record<Coverage["status"], number> = {
  abnormal: 0,
  failed: 1,
  skipped: 2,
  passed: 3,
};

function CoverageRow({ item }: { item: Coverage }) {
  return (
    <article className={`coverage-row coverage-${item.status}`}>
      <div className="coverage-row-main">
        <div>
          <strong>{item.name}</strong>
          <span className="technical-code">{item.check_code}</span>
        </div>
        <StatusBadge status={item.status} />
      </div>
      {item.reason ? <p>{item.reason}</p> : null}
      <div className="coverage-meta">
        <span>检查对象 {item.checked_objects}</span>
        <span>问题 {item.issue_count}</span>
        <span>耗时 {item.duration_ms} ms</span>
      </div>
    </article>
  );
}

export function CoveragePanel({
  coverage,
  title = "检查覆盖",
}: {
  coverage: Coverage[];
  title?: string;
}) {
  const titleId = useId();
  if (coverage.length === 0) {
    return (
      <section className="panel coverage-panel" aria-labelledby={titleId}>
        <h3 id={titleId}>{title}</h3>
        <p className="empty-copy">服务端未提供覆盖信息，当前不能确认全部正常。</p>
      </section>
    );
  }

  const ordered = [...coverage].sort((left, right) => coverageRank[left.status] - coverageRank[right.status]);
  const attention = ordered.filter((item) => item.status !== "passed");
  const passed = ordered.filter((item) => item.status === "passed");
  const completed = coverage.filter((item) => item.status === "passed" || item.status === "abnormal").length;

  return (
    <section className="panel coverage-panel" aria-labelledby={titleId}>
      <div className="section-header">
        <div>
          <h3 id={titleId}>{title}</h3>
          <p className="inline-note">检查完成 {completed}/{coverage.length}；完成率不代表集群健康分。</p>
        </div>
      </div>
      {attention.length > 0 ? (
        <div className="coverage-list">
          {attention.map((item) => <CoverageRow key={item.check_code} item={item} />)}
        </div>
      ) : (
        <p className="success-copy">所有已返回检查项均已完成，未发现未执行或检查失败项。</p>
      )}
      {passed.length > 0 ? (
        <details className="normal-details">
          <summary>已检查且无异常（{passed.length}）</summary>
          <div className="coverage-list">
            {passed.map((item) => <CoverageRow key={item.check_code} item={item} />)}
          </div>
        </details>
      ) : null}
    </section>
  );
}
