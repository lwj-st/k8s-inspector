import { useMemo, useState } from "react";

import type { Issue, IssueEvent, ResourceRef } from "../api/types";
import { StatusBadge } from "./StatusBadge";

const sourceLabels: Record<string, string> = {
  kubernetes_api: "Kubernetes API",
  metrics_api: "Metrics API",
  event: "Warning Event",
  log_match: "日志命中上下文",
  template: "故障模板",
  derived: "规则计算",
};

const eventLabels: Record<IssueEvent["event_type"], string> = {
  opened: "问题首次发现",
  observed: "问题仍在持续",
  severity_escalated: "严重程度升级",
  acknowledged: "问题已确认",
  recovered: "问题已恢复",
  reopened: "问题重新出现",
};

const chainOrder: Record<string, number> = {
  ingress: 0,
  service: 1,
  endpointslice: 2,
  pod: 3,
};

function formatDateTime(value?: string | null) {
  if (!value) {
    return "--";
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function resourceKey(resource: ResourceRef) {
  return `${resource.kind}:${resource.namespace ?? ""}:${resource.name}`;
}

function resourceLabel(resource: ResourceRef) {
  return `${resource.kind}/${resource.namespace ? `${resource.namespace}/` : ""}${resource.name}`;
}

function factValue(value: unknown) {
  if (Array.isArray(value)) {
    return value.map(String).join("、");
  }
  if (value === null || value === undefined || value === "") {
    return "--";
  }
  return String(value);
}

export function IssueDetailPanel({
  issue,
  events,
  eventsTotal,
  eventsLoading,
  eventsError,
  onLoadMore,
  onAcknowledge,
}: {
  issue: Issue;
  events: IssueEvent[];
  eventsTotal: number;
  eventsLoading: boolean;
  eventsError: string | null;
  onLoadMore: () => void;
  onAcknowledge: (note: string) => Promise<void>;
}) {
  const [note, setNote] = useState("");
  const [acknowledging, setAcknowledging] = useState(false);
  const [acknowledgeError, setAcknowledgeError] = useState<string | null>(null);

  const chainResources = useMemo(() => {
    const resources = [issue.resource, ...issue.evidence.flatMap((item) => item.related_resources)];
    const unique = new Map(resources.map((resource) => [resourceKey(resource), resource]));
    return Array.from(unique.values())
      .filter((resource) => resource.kind.toLowerCase() in chainOrder)
      .sort((left, right) => chainOrder[left.kind.toLowerCase()] - chainOrder[right.kind.toLowerCase()]);
  }, [issue]);

  async function handleAcknowledge(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!note.trim()) {
      setAcknowledgeError("请填写确认备注");
      return;
    }
    setAcknowledging(true);
    setAcknowledgeError(null);
    try {
      await onAcknowledge(note.trim());
      setNote("");
    } catch (reason) {
      setAcknowledgeError(reason instanceof Error ? reason.message : "确认失败，请重试");
    } finally {
      setAcknowledging(false);
    }
  }

  return (
    <article className="issue-detail" aria-labelledby="issue-detail-title">
      <header className="issue-detail-header">
        <div>
          <p className="eyebrow">{issue.resource.kind} · {issue.resource.namespace ?? "集群级"}</p>
          <h1 id="issue-detail-title">{issue.summary}</h1>
          <p>{resourceLabel(issue.resource)}</p>
        </div>
        <div className="status-pair">
          <StatusBadge status={issue.severity} />
          <StatusBadge status={issue.status} />
        </div>
      </header>

      <section className="detail-section" aria-labelledby="impact-title">
        <h2 id="impact-title">结论与影响范围</h2>
        <p>{issue.reason}</p>
        <dl className="detail-grid">
          <div><dt>集群</dt><dd>{issue.cluster_id}</dd></div>
          <div><dt>范围</dt><dd>{issue.scope}</dd></div>
          <div><dt>首次发现</dt><dd>{formatDateTime(issue.first_seen_at)}</dd></div>
          <div><dt>最后发现</dt><dd>{formatDateTime(issue.last_seen_at)}</dd></div>
          <div><dt>出现次数</dt><dd>{issue.occurrence_count}</dd></div>
          <div><dt>确认状态</dt><dd>{issue.acknowledged_at ? "已确认" : "未确认"}</dd></div>
        </dl>
      </section>

      {chainResources.length > 1 ? (
        <section className="detail-section" aria-labelledby="chain-title">
          <div className="section-header">
            <div>
              <h2 id="chain-title">访问配置链路</h2>
              <p className="inline-note">只展示后端提供的关联证据；本次未验证集群外真实访问。</p>
            </div>
          </div>
          <ol className="config-chain" aria-label="访问配置链路">
            {chainResources.map((resource) => (
              <li key={resourceKey(resource)}>
                <span className="chain-kind">{resource.kind}</span>
                <strong>{resource.name}</strong>
                <small>{resource.namespace ?? "集群级"} · 关联证据</small>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <section className="detail-section" aria-labelledby="evidence-title">
        <h2 id="evidence-title">证据</h2>
        {issue.evidence.length === 0 ? (
          <p className="empty-copy">本问题没有可展示的持久化证据。</p>
        ) : (
          <div className="evidence-card-list">
            {issue.evidence.map((item) => (
              <article className="evidence-card" key={`${item.code}-${item.observed_at}`}>
                <div className="section-header">
                  <strong>{item.summary}</strong>
                  <span>{sourceLabels[item.source] ?? item.source}</span>
                </div>
                <p className="inline-note">观测时间：{formatDateTime(item.observed_at)}</p>
                {Object.keys(item.facts).length > 0 ? (
                  <dl className="facts-grid">
                    {Object.entries(item.facts).map(([key, value]) => (
                      <div key={key}><dt>{key}</dt><dd>{factValue(value)}</dd></div>
                    ))}
                  </dl>
                ) : null}
                {item.related_resources.length > 0 ? (
                  <p className="related-resources">
                    关联对象：{item.related_resources.map(resourceLabel).join("；")}
                  </p>
                ) : null}
                {item.truncated ? (
                  <p className="feedback-banner feedback-warning">证据已按安全和长度限制截断。</p>
                ) : null}
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="detail-section suggestion-section" aria-labelledby="suggestion-title">
        <h2 id="suggestion-title">处理建议</h2>
        <p>{issue.suggestion}</p>
      </section>

      <section className="detail-section" aria-labelledby="timeline-title">
        <div className="section-header">
          <h2 id="timeline-title">问题时间线</h2>
          <span className="section-tip">最新动态在前</span>
        </div>
        {eventsError ? (
          <div className="feedback-banner feedback-error" role="alert">
            时间线读取失败：{eventsError}
          </div>
        ) : null}
        {events.length === 0 && !eventsLoading && !eventsError ? (
          <p className="empty-copy">暂无生命周期记录。</p>
        ) : (
          <ol className="issue-timeline">
            {events.map((item) => (
              <li key={item.id}>
                <div className="timeline-dot" aria-hidden="true" />
                <div>
                  <div className="section-header">
                    <strong>{eventLabels[item.event_type]}</strong>
                    <time dateTime={item.occurred_at}>{formatDateTime(item.occurred_at)}</time>
                  </div>
                  <p>{item.summary}</p>
                  <small>{item.trigger === "scheduled" ? "定时巡检" : "手动巡检"}</small>
                </div>
              </li>
            ))}
          </ol>
        )}
        {events.length < eventsTotal ? (
          <button type="button" onClick={onLoadMore} disabled={eventsLoading}>
            {eventsLoading ? "加载中…" : "加载更早记录"}
          </button>
        ) : null}
      </section>

      <section className="detail-section acknowledgement-section" aria-labelledby="ack-title">
        <h2 id="ack-title">确认问题</h2>
        <div className="feedback-banner feedback-warning">
          确认只表示你已知晓此问题，不会恢复问题，也不会修改 Kubernetes 资源。
        </div>
        {issue.acknowledged_at ? (
          <div className="acknowledged-note">
            <strong>已于 {formatDateTime(issue.acknowledged_at)} 确认</strong>
            <p>{issue.acknowledge_note}</p>
          </div>
        ) : (
          <form className="acknowledge-form" onSubmit={handleAcknowledge}>
            <label>
              确认备注
              <textarea
                value={note}
                maxLength={1000}
                rows={4}
                onChange={(event) => setNote(event.target.value)}
                aria-describedby="ack-help"
              />
            </label>
            <div id="ack-help" className="field-help">请说明负责人、处理计划或已知影响。还可输入 {1000 - note.length} 字。</div>
            {acknowledgeError ? <p className="field-error" role="alert">{acknowledgeError}</p> : null}
            <button type="submit" className="primary-action" disabled={acknowledging}>
              {acknowledging ? "确认中…" : "确认已知晓"}
            </button>
          </form>
        )}
      </section>

      <details className="technical-details">
        <summary>技术详情</summary>
        <dl className="detail-grid">
          <div><dt>Issue Code</dt><dd>{issue.issue_code}</dd></div>
          <div><dt>检查来源</dt><dd>{issue.source_check}</dd></div>
          <div><dt>Fingerprint</dt><dd className="break-all">{issue.fingerprint}</dd></div>
          <div><dt>Correlation Key</dt><dd>{issue.correlation_key ?? "--"}</dd></div>
        </dl>
      </details>
    </article>
  );
}
