import type { DiagnosisResponse, TemplateCondition, TemplateConditionOperator, TemplateConditionType } from "../../api/types";
import { StatusBadge } from "../../components/StatusBadge";
import { normalizeTerminalLogText } from "../logs/logText";

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

type MatchResultKind = "matched" | "undetermined" | "unmatched";

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

function formatConditionValue(value: unknown) {
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  if (value && typeof value === "object") {
    const related = value as {
      resource?: string;
      object_name?: string | null;
      object_name_pattern?: string | null;
      match_any?: boolean;
      statuses?: string[];
    };
    if (related.resource) {
      const objectText = related.match_any === false && (related.object_name || related.object_name_pattern)
        ? related.object_name || related.object_name_pattern
        : "任意对象";
      return `${related.resource} ${objectText} 状态 ${(related.statuses ?? []).join(", ")}`;
    }
  }
  return String(value ?? "");
}

function formatOperator(operator: string) {
  return {
    equals: "等于",
    in: "属于",
    contains: "包含",
    gte: "大于等于",
    lte: "小于等于",
  }[operator] ?? operator;
}

function describeCondition(input: RawCondition | NormalizedCondition) {
  const condition: NormalizedCondition = "condition_type" in input ? normalizeCondition(input) : input;
  const targetRef = condition.target_ref ?? "对象组";
  const expectedValue = formatConditionValue(condition.value);

  if (condition.type === "related_object_status") {
    const related = condition.value as {
      resource?: string;
      object_name?: string | null;
      object_name_pattern?: string | null;
      match_any?: boolean;
      statuses?: string[];
    } | null;
    const objectText = related?.match_any === false && (related.object_name || related.object_name_pattern)
      ? related.object_name || related.object_name_pattern
      : "任意对象";
    return `对象组 ${targetRef} 的 ${related?.resource ?? "关联对象"} ${objectText} 状态${formatOperator(condition.operator)} ${(related?.statuses ?? []).join(", ")}`;
  }

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

function evidenceObjectName(item: Record<string, unknown>) {
  if (item.pod) {
    return String(item.pod);
  }
  if (Array.isArray(item.pods) && item.pods.length > 0) {
    return item.pods.map((value) => String(value)).join(", ");
  }
  if (item.object_name) {
    return String(item.object_name);
  }
  if (item.name) {
    return String(item.name);
  }
  return "匹配对象";
}

function evidenceStatusText(item: Record<string, unknown>) {
  if (item.status) {
    return String(item.status);
  }
  if (item.value) {
    return Array.isArray(item.value) ? item.value.map((value) => String(value)).join(", ") : String(item.value);
  }
  if (item.matched_text) {
    return String(item.matched_text);
  }
  return "已匹配";
}

function evidenceTypeLabel(item: Record<string, unknown>) {
  const type = String(item.type ?? "");
  if (type === "pod_status") {
    return "Pod 状态";
  }
  if (type === "restart_count") {
    return "重启次数";
  }
  if (type === "event_keyword") {
    return "事件";
  }
  if (type === "related_object_status") {
    return "关联对象";
  }
  if (type === "log_keyword") {
    return "日志";
  }
  return type || "证据";
}

function summarizePods(item: Record<string, unknown>) {
  const pod = item.pod ? [String(item.pod)] : [];
  const pods = Array.isArray(item.pods) ? item.pods.map((value) => String(value)) : [];
  const values = [...pod, ...pods];
  return values.length > 0 ? values.join(", ") : "未标记 Pod";
}

function summarizeContainer(item: Record<string, unknown>) {
  return item.container_name ? String(item.container_name) : "未标记容器";
}

function evidenceContext(item: Record<string, unknown>) {
  if (item.type !== "log_keyword") {
    return null;
  }
  const contextText = item.context_text ? String(item.context_text).trim() : "";
  const matchedText = item.matched_text ? String(item.matched_text) : "";
  return contextText || matchedText || null;
}

function normalizeLogText(value: string) {
  return normalizeTerminalLogText(value);
}

function getResultKind(item: NormalizedMatchResult): MatchResultKind {
  if (item.matched) {
    return "matched";
  }

  const summary = item.summary?.trim() ?? "";
  const reason = item.reason?.trim() ?? "";
  const combined = `${summary} ${reason}`.toLowerCase();
  const indicatesCollectionFailure =
    combined.includes("无法判断") ||
    combined.includes("采集失败") ||
    combined.includes("forbidden") ||
    combined.includes("permission denied") ||
    combined.includes("error:");

  if (indicatesCollectionFailure || reason.includes("采集") || summary.includes("采集")) {
    return "undetermined";
  }

  return "unmatched";
}

function MatchResultDetails({ item, kind, compact = false }: { item: NormalizedMatchResult; kind: MatchResultKind; compact?: boolean }) {
  const evidencePods = Array.from(new Set(item.evidence_refs.map((evidence) => summarizePods(evidence))));
  const evidenceContainers = Array.from(
    new Set(item.evidence_refs.map((evidence) => summarizeContainer(evidence)).filter((value) => value !== "未标记容器")),
  );

  return (
    <div className={compact ? "diagnosis-card-body diagnosis-card-body-compact" : "diagnosis-card-body"}>
        {item.summary ? <p className="diagnosis-summary">{item.summary}</p> : null}
        <div className="diagnosis-meta">
          <p><strong>判断原因：</strong>{item.reason}</p>
          <p><strong>建议动作：</strong>{item.suggestion}</p>
          {item.risk_note ? <p><strong>风险说明：</strong>{item.risk_note}</p> : null}
        </div>
        {kind === "matched" ? (
          <div className="diagnosis-inline-metrics">
            <span>命中 Pod：{evidencePods.join(" / ") || "未标记"}</span>
            <span>命中容器：{evidenceContainers.join(" / ") || "未标记"}</span>
          </div>
        ) : null}
        {item.matched_conditions.length > 0 ? (
          <>
            <p className="inline-note">命中条件 {item.matched_conditions.length}</p>
            <div className="condition-list">
              {item.matched_conditions.map((condition, index: number) => (
                <div key={`${item.template_id}-matched-${index}`} className="condition-item">
                  {describeCondition(condition)}
                </div>
              ))}
            </div>
          </>
        ) : null}
        {item.unmatched_conditions.length > 0 ? (
          <>
            <p className="inline-note">未命中条件 {item.unmatched_conditions.length}</p>
            <div className="condition-list">
              {item.unmatched_conditions.map((condition, index: number) => (
                <div key={`${item.template_id}-unmatched-${index}`} className="condition-item condition-item-muted">
                  {describeCondition(condition)}
                </div>
              ))}
            </div>
          </>
        ) : null}
        {item.evidence_refs.length > 0 ? (
          <details className="diagnosis-evidence-details">
            <summary>查看证据（{item.evidence_refs.length}）</summary>
            <div className="page-section diagnosis-evidence-body">
              {item.evidence_refs.map((evidence, index) => {
                const logContext = evidenceContext(evidence);

                return (
                  <section key={`${item.template_id}-evidence-${index}`} className="compact-subpanel">
                    {logContext ? (
                      <>
                        <span className="inline-note">
                          {evidenceObjectName(evidence)}
                          {evidence.container_name ? ` / ${String(evidence.container_name)}` : ""}
                          {evidence.matched_text ? ` / 命中：${String(evidence.matched_text)}` : ""}
                        </span>
                        <pre className="log-block code-block-scroll terminal-log-block">{normalizeLogText(logContext)}</pre>
                      </>
                    ) : (
                      <div className="diagnosis-evidence-row">
                        <span>{evidenceTypeLabel(evidence)}</span>
                        <strong className="ellipsis-cell" title={evidenceObjectName(evidence)}>{evidenceObjectName(evidence)}</strong>
                        <StatusBadge status={evidenceStatusText(evidence)} />
                      </div>
                    )}
                  </section>
                );
              })}
            </div>
          </details>
        ) : null}
    </div>
  );
}

function MatchResultList({
  title,
  items,
  kind,
  showHeader = true,
}: {
  title: string;
  items: NormalizedMatchResult[];
  kind: MatchResultKind;
  showHeader?: boolean;
}) {
  const badgeStatus = kind === "matched" ? "matched" : kind === "undetermined" ? "warning" : "info";
  return (
    <section className="panel panel-muted diagnosis-highlight-panel">
      {showHeader ? (
        <div className="section-header">
          <div>
            <h3>{title}（{items.length}）</h3>
          </div>
          <StatusBadge status={badgeStatus} />
        </div>
      ) : null}
      <div className="diagnosis-result-list">
        {items.map((item) => (
          <details key={`${kind}-row-${item.template_id}`} className={`diagnosis-result-row diagnosis-result-row-${kind}`}>
            <summary>
              <span className="diagnosis-row-title">{item.template_name}</span>
              <span className="diagnosis-row-meta">命中 {item.matched_conditions.length} 个条件</span>
              <span className="diagnosis-row-meta ellipsis-cell" title={item.reason}>{item.reason}</span>
              <span className="diagnosis-row-action">详情</span>
            </summary>
            <MatchResultDetails item={item} kind={kind} compact />
          </details>
        ))}
      </div>
    </section>
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
  const matchedResults = results.filter((item) => getResultKind(item) === "matched");
  const undeterminedResults = results.filter((item) => getResultKind(item) === "undetermined");
  const unmatchedResults = results.filter((item) => getResultKind(item) === "unmatched");

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
          命中模板 {matchedResults.length} / 未命中模板 {unmatchedResults.length} / 无法判断 {undeterminedResults.length}
        </p>
      </section>
      {matchedResults.length > 0 ? <MatchResultList title="已命中模板" items={matchedResults} kind="matched" /> : null}
      {results.length === 0 ? (
        <section className="panel">
          <p>本次未命中任何故障模板。</p>
        </section>
      ) : null}
      {undeterminedResults.length > 0 ? <MatchResultList title="无法判断" items={undeterminedResults} kind="undetermined" /> : null}
      {unmatchedResults.length > 0 ? (
        <details className="diagnosis-collapsible">
          <summary>未命中模板（{unmatchedResults.length}）</summary>
          <div className="page-section diagnosis-collapsible-body">
            <MatchResultList title="未命中模板" items={unmatchedResults} kind="unmatched" showHeader={false} />
          </div>
        </details>
      ) : null}
    </section>
  );
}
