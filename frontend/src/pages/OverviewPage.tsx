import { Link } from "react-router-dom";

import { KeyValueList } from "../components/KeyValueList";
import { StatusBadge } from "../components/StatusBadge";
import { useOverview } from "../features/overview/useOverview";
import { useRunClusterInspection } from "../features/overview/useRunClusterInspection";
import { useTemplates } from "../features/templates/useTemplates";
import { useWhitelists } from "../features/whitelists/useWhitelists";

function groupIssuesByComponent(
  issues: Array<{ component?: string | null; name: string; status: string; summary: string }>,
) {
  const groups = new Map<string, typeof issues>();
  for (const issue of issues) {
    const key = issue.component ?? "unknown";
    const current = groups.get(key) ?? [];
    current.push(issue);
    groups.set(key, current);
  }
  return Array.from(groups.entries());
}

export function OverviewPage() {
  const { data, loading, error } = useOverview();
  const clusterInspection = useRunClusterInspection();
  const templates = useTemplates();
  const whitelists = useWhitelists();

  if (loading) {
    return <p>加载中...</p>;
  }

  if (error) {
    return <p>加载失败：{error}</p>;
  }

  if (!data) {
    return <p>暂无数据</p>;
  }

  const groupedIssues = groupIssuesByComponent(data.issues);
  const groupedInspectionResults = groupIssuesByComponent(
    (clusterInspection.data?.results ?? []).map((item) => ({
      component: item.component,
      name: item.component,
      status: item.status,
      summary: item.describe_summary ?? item.log_summary ?? "无摘要",
    })),
  );
  const recentTemplates = templates.data.slice(0, 3);
  const whitelistReminders = whitelists.data.slice(0, 3);

  return (
    <section className="page-section">
      <section className="workbench-hero">
        <div className="workbench-copy">
          <header className="section-header">
            <div>
              <p className="eyebrow">Workbench</p>
              <h2>排障工作台</h2>
            </div>
            <StatusBadge status={data.health_status ?? data.cluster_status ?? "unknown"} />
          </header>
          <p className="hero-summary">{data.recent_summary}</p>
          <div className="quick-action-grid">
            <Link to="/inspections/namespace" className="quick-action-card">
              <strong>巡检名称空间</strong>
              <span>从整个名称空间快速筛出异常 Pod 和关联对象。</span>
            </Link>
            <Link to="/inspections/namespace#pod-focus" className="quick-action-card">
              <strong>巡检单个 Pod</strong>
              <span>聚焦某个 Pod 的状态、事件、describe 和日志命中。</span>
            </Link>
            <Link to="/diagnosis" className="quick-action-card">
              <strong>故障模板检查</strong>
              <span>按预录入模板核对常见故障，不再重复输入检查范围。</span>
            </Link>
          </div>
        </div>
        <div className="hero-metric-stack">
          <div className="hero-metric">
            <span>健康分</span>
            <strong>{data.health_score ?? "--"}</strong>
          </div>
          <div className="hero-metric hero-metric-compact">
            <span>异常组件组</span>
            <strong>{groupedIssues.length}</strong>
          </div>
        </div>
      </section>
      <KeyValueList
        items={[
          { label: "最近检查时间", value: data.last_checked_at },
          { label: "问题数量", value: String(data.issues.length) },
          { label: "自检异常项", value: String(clusterInspection.data?.results.length ?? 0) },
        ]}
      />
      <section className="card-grid card-grid-wide">
        <article className="card">
          <div className="section-header">
            <h3>最近异常</h3>
            <span className="section-tip">按组件聚合，先看高风险项</span>
          </div>
          <div className="alert-list">
            {groupedIssues.map(([component, issues]) => (
              <article key={component} className="alert-row">
                <div className="card-title">
                  <strong>{component}</strong>
                  <StatusBadge status={issues[0]?.status ?? "unknown"} />
                </div>
                <p>{issues[0]?.summary}</p>
                <small>异常对象数：{issues.length}</small>
              </article>
            ))}
          </div>
        </article>
        <article className="card">
          <div className="section-header">
            <h3>最近使用的模板</h3>
            <Link to="/templates" className="text-link">查看全部</Link>
          </div>
          {recentTemplates.length > 0 ? (
            <div className="stack-list">
              {recentTemplates.map((item) => (
                <div key={item.id} className="stack-item">
                  <strong>{item.name}</strong>
                  <p>{item.reason}</p>
                </div>
              ))}
            </div>
          ) : (
            <p>暂无模板</p>
          )}
        </article>
        <article className="card">
          <div className="section-header">
            <h3>白名单提醒</h3>
            <Link to="/whitelists" className="text-link">管理规则</Link>
          </div>
          {whitelistReminders.length > 0 ? (
            <div className="stack-list">
              {whitelistReminders.map((item) => (
                <div key={item.id} className="stack-item">
                  <strong>{item.keyword}</strong>
                  <p>{item.namespace}{item.label_selector ? ` / ${item.label_selector}` : ""}</p>
                </div>
              ))}
            </div>
          ) : (
            <p>暂无白名单规则</p>
          )}
        </article>
      </section>
      <section className="page-section">
        <div className="section-header">
          <h3>异常组件分组</h3>
          <span className="section-tip">保留完整条目，便于追溯</span>
        </div>
        <div className="card-grid">
          {groupedIssues.map(([component, issues]) => (
            <article key={component} className="card">
              <div className="card-title">
                <strong>{component}</strong>
                <StatusBadge status={issues[0]?.status ?? "unknown"} />
              </div>
              <p>异常对象数：{issues.length}</p>
              <ul className="plain-list">
                {issues.map((issue) => (
                  <li key={`${component}-${issue.name}`}>{issue.name}: {issue.summary}</li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </section>
      <section className="page-section">
        <div className="section-header">
          <h3>集群自检结果</h3>
          <button type="button" onClick={() => void clusterInspection.execute()} disabled={clusterInspection.loading}>
            {clusterInspection.loading ? "自检中..." : "重新自检"}
          </button>
        </div>
        {clusterInspection.error ? <p>自检失败：{clusterInspection.error}</p> : null}
        {clusterInspection.data ? (
          <>
            <KeyValueList
              items={[
                { label: "自检状态", value: clusterInspection.data.health_status },
                { label: "执行时间", value: clusterInspection.data.executed_at },
                { label: "异常结果数", value: String(clusterInspection.data.results.length) },
              ]}
            />
            <div className="card-grid">
              {groupedInspectionResults.map(([component, results]) => (
                <article key={`inspection-${component}`} className="card">
                  <div className="card-title">
                    <strong>{component}</strong>
                    <StatusBadge status={results[0]?.status ?? "unknown"} />
                  </div>
                  <p>异常条目：{results.length}</p>
                  <ul className="plain-list">
                    {results.map((result) => (
                      <li key={`${component}-${result.name}-${result.summary}`}>{result.summary}</li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          </>
        ) : null}
      </section>
    </section>
  );
}
