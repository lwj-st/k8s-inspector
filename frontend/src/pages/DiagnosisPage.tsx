import type { DiagnosisMatch } from "../api/types";
import { StatusBadge } from "../components/StatusBadge";
import { useRunDiagnosis } from "../features/diagnosis/useRunDiagnosis";

function describeCondition(condition: {
  target_ref?: string | null;
  type: string;
  operator: string;
  value: unknown;
}) {
  const targetRef = condition.target_ref ?? "对象组";
  const expectedValue = Array.isArray(condition.value)
    ? condition.value.join(", ")
    : String(condition.value ?? "");

  if (condition.type === "log_keyword") {
    return `对象组 ${targetRef} 在日志中包含 ${expectedValue}`;
  }

  if (condition.type === "pod_status") {
    return condition.operator === "equals"
      ? `对象组 ${targetRef} 的 Pod 状态等于 ${expectedValue}`
      : `对象组 ${targetRef} 的 Pod 状态 ${condition.operator} ${expectedValue}`;
  }

  if (condition.type === "restart_count") {
    return `对象组 ${targetRef} 的重启次数 ${condition.operator} ${expectedValue}`;
  }

  if (condition.type === "event_keyword") {
    return `对象组 ${targetRef} 的事件中包含 ${expectedValue}`;
  }

  return `对象组 ${targetRef} 满足 ${condition.type} ${condition.operator} ${expectedValue}`;
}

function MatchCard({ match }: { match: DiagnosisMatch }) {
  return (
    <article className="card">
      <div className="section-header">
        <div>
          <strong>{match.template_name}</strong>
          <p>{match.reason}</p>
        </div>
        <StatusBadge status="matched" />
      </div>
      <p>{match.suggestion}</p>
      <p className="inline-note">命中条件 {match.matched_conditions.length}</p>
      <div className="condition-list">
        {match.matched_conditions.map((condition, index) => (
          <div key={`${match.template_id}-matched-${index}`} className="condition-item">
            {describeCondition(condition)}
          </div>
        ))}
      </div>
      {match.unmatched_conditions.length > 0 ? (
        <>
          <p className="inline-note">未命中条件 {match.unmatched_conditions.length}</p>
          <div className="condition-list">
            {match.unmatched_conditions.map((condition, index) => (
              <div key={`${match.template_id}-unmatched-${index}`} className="condition-item condition-item-muted">
                {describeCondition(condition)}
              </div>
            ))}
          </div>
        </>
      ) : null}
    </article>
  );
}

export function DiagnosisPage() {
  const { data, loading, error, submit } = useRunDiagnosis();

  return (
    <section className="page-section">
      <header className="section-header">
        <div>
          <p className="eyebrow">模板匹配</p>
          <h2>故障模板检查</h2>
        </div>
        {data ? <StatusBadge status={data.status} /> : null}
      </header>

      <section className="panel panel-muted">
        <div className="section-header">
          <div>
            <h3>按已录入模板直接检查</h3>
            <p className="inline-note">模板里已经绑定名称空间和对象组，这里不再手填范围。</p>
          </div>
        </div>
        <button type="button" onClick={() => void submit()} disabled={loading}>
          {loading ? "检查中..." : "运行模板检查"}
        </button>
      </section>

      {error ? <p>排查失败：{error}</p> : null}

      {data ? (
        <div className="page-section">
          <section className="panel">
            <div className="card-title">
              <strong>结果状态</strong>
              <StatusBadge status={data.status} />
            </div>
            <p className="inline-note">
              本次执行方式：{data.direction}
              {data.executed_at ? ` / ${data.executed_at}` : ""}
            </p>
          </section>
          {data.matches.length > 0 ? (
            data.matches.map((match) => <MatchCard key={match.template_id} match={match} />)
          ) : (
            <section className="panel">
              <p>本次未命中任何故障模板。</p>
            </section>
          )}
        </div>
      ) : null}
    </section>
  );
}
