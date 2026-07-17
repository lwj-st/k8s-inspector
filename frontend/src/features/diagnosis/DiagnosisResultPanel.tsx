import type { DiagnosisResponse, TemplateCondition, TemplateConditionOperator, TemplateConditionType } from "../../api/types";
import { StatusBadge } from "../../components/StatusBadge";

type RawCondition =
  | TemplateCondition
  | {
      target_ref?: string | null;
      type: TemplateConditionType;
      operator: TemplateConditionOperator;
      value: unknown;
    };

type NormalizedCondition = {
  target_ref?: string | null;
  type: string;
  operator: string;
  value: unknown;
};

type NormalizedMatchResult = {
  template_id: number;
  template_name: string;
  matched: boolean;
  matched_conditions: NormalizedCondition[];
  unmatched_conditions: NormalizedCondition[];
  summary?: string | null;
  reason: string;
  suggestion: string;
  risk_note?: string | null;
  evidence_refs: Array<Record<string, unknown>>;
};

function normalizeCondition(condition: RawCondition): NormalizedCondition {
  if ("condition_type" in condition) {
    return {
      target_ref: condition.target_ref,
      type: condition.condition_type,
      operator: condition.operator,
      value: condition.expected_value,
    };
  }

  return {
    target_ref: condition.target_ref,
    type: condition.type,
    operator: condition.operator,
    value: condition.value,
  };
}

function describeCondition(input: RawCondition | NormalizedCondition) {
  const condition: NormalizedCondition = "condition_type" in input ? normalizeCondition(input) : input;
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

function summarizeEvidence(item: Record<string, unknown>) {
  const type = String(item.type ?? "证据");
  const pod = item.pod ? String(item.pod) : null;
  const pods = Array.isArray(item.pods) ? item.pods.join(", ") : null;
  const matchedText = item.matched_text ? String(item.matched_text) : null;
  const value = Array.isArray(item.value) ? item.value.join(", ") : item.value ? String(item.value) : null;

  return [type, pod ?? pods, matchedText ?? value].filter(Boolean).join(" / ");
}

function MatchResultCard({ item }: { item: NormalizedMatchResult }) {
  return (
    <article className="card">
      <div className="section-header">
        <div>
          <strong>{item.template_name}</strong>
          <p>{item.reason}</p>
        </div>
        <StatusBadge status={item.matched ? "matched" : "info"} />
      </div>
      <p>{item.suggestion}</p>
      {item.summary ? <p className="inline-note">{item.summary}</p> : null}
      <p className="inline-note">命中条件 {item.matched_conditions.length}</p>
      <div className="condition-list">
        {item.matched_conditions.map((condition, index: number) => (
          <div key={`${item.template_id}-matched-${index}`} className="condition-item">
            {describeCondition(condition)}
          </div>
        ))}
      </div>
      <p className="inline-note">未命中条件 {item.unmatched_conditions.length}</p>
      <div className="condition-list">
        {item.unmatched_conditions.map((condition, index: number) => (
          <div key={`${item.template_id}-unmatched-${index}`} className="condition-item condition-item-muted">
            {describeCondition(condition)}
          </div>
        ))}
      </div>
      {item.evidence_refs.length > 0 ? (
        <>
          <p className="inline-note">证据摘要</p>
          <ul className="plain-list">
            {item.evidence_refs.map((evidence, index) => (
              <li key={`${item.template_id}-evidence-${index}`}>{summarizeEvidence(evidence)}</li>
            ))}
          </ul>
        </>
      ) : null}
      {item.risk_note ? <p className="inline-note">风险说明：{item.risk_note}</p> : null}
    </article>
  );
}

function normalizeResults(data: DiagnosisResponse): NormalizedMatchResult[] {
  if (data.template_match_results.length > 0) {
    return data.template_match_results.map((item) => ({
      ...item,
      matched_conditions: item.matched_conditions.map(normalizeCondition),
      unmatched_conditions: item.unmatched_conditions.map(normalizeCondition),
    }));
  }

  return data.matches.map((match) => ({
    template_id: match.template_id,
    template_name: match.template_name,
    matched: true,
    matched_conditions: match.matched_conditions.map(normalizeCondition),
    unmatched_conditions: match.unmatched_conditions.map(normalizeCondition),
    summary: null,
    reason: match.reason,
    suggestion: match.suggestion,
    risk_note: match.risk_note ?? null,
    evidence_refs: match.evidence,
  }));
}

type DiagnosisResultPanelProps = {
  data: DiagnosisResponse | null;
  loading: boolean;
  error: string | null;
  idleMessage?: string;
  title?: string;
};

export function DiagnosisResultPanel({
  data,
  loading,
  error,
  idleMessage = "点击运行后显示模板匹配结果。",
  title = "模板匹配结果",
}: DiagnosisResultPanelProps) {
  if (loading) {
    return (
      <section className="panel panel-muted" aria-label={title}>
        <h3>{title}</h3>
        <p>模板匹配中...</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="panel panel-muted" aria-label={title}>
        <h3>{title}</h3>
        <p>模板匹配失败：{error}</p>
      </section>
    );
  }

  if (!data) {
    return (
      <section className="panel panel-muted" aria-label={title}>
        <h3>{title}</h3>
        <p>{idleMessage}</p>
      </section>
    );
  }

  const results = normalizeResults(data);
  const matchedResults = results.filter((item) => item.matched);
  const unmatchedResults = results.filter((item) => !item.matched);

  return (
    <section className="page-section" aria-label={title}>
      <section className="panel">
        <div className="card-title">
          <strong>{title}</strong>
          <StatusBadge status={data.status} />
        </div>
        <p className="inline-note">
          本次执行方式：{data.direction}
          {data.executed_at ? ` / ${data.executed_at}` : ""}
        </p>
        <p className="inline-note">
          命中模板 {matchedResults.length} / 未命中模板 {unmatchedResults.length}
        </p>
        {data.evidence_summary.length > 0 ? (
          <>
            <p className="inline-note">全局证据摘要</p>
            <ul className="plain-list">
              {data.evidence_summary.map((item, index) => (
                <li key={`summary-${index}`}>{summarizeEvidence(item)}</li>
              ))}
            </ul>
          </>
        ) : null}
      </section>
      {results.length === 0 ? (
        <section className="panel">
          <p>本次未命中任何故障模板。</p>
        </section>
      ) : null}
      {matchedResults.length > 0 ? (
        <section className="page-section">
          <div className="section-header">
            <h3>已命中模板</h3>
            <span className="section-tip">至少有一个对象满足模板条件</span>
          </div>
          {matchedResults.map((item) => (
            <MatchResultCard key={`matched-${item.template_id}`} item={item} />
          ))}
        </section>
      ) : null}
      {unmatchedResults.length > 0 ? (
        <section className="page-section">
          <div className="section-header">
            <h3>未命中模板</h3>
            <span className="section-tip">用于解释为什么这次不属于该故障</span>
          </div>
          {unmatchedResults.map((item) => (
            <MatchResultCard key={`unmatched-${item.template_id}`} item={item} />
          ))}
        </section>
      ) : null}
    </section>
  );
}
