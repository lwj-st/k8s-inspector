import { KeyValueList } from "../components/KeyValueList";
import { StatusBadge } from "../components/StatusBadge";
import { useOverview } from "../features/overview/useOverview";
import { useRunClusterInspection } from "../features/overview/useRunClusterInspection";

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

  return (
    <section className="page-section">
      <header className="section-header">
        <h2>集群总览</h2>
        <StatusBadge status={data.health_status ?? data.cluster_status ?? "unknown"} />
      </header>
      <div className="hero-metric">
        <span>健康分</span>
        <strong>{data.health_score ?? "--"}</strong>
      </div>
      <p>{data.recent_summary}</p>
      <KeyValueList
        items={[
          { label: "最近检查时间", value: data.last_checked_at },
          { label: "问题数量", value: String(data.issues.length) },
          { label: "异常组件组数", value: String(groupedIssues.length) },
        ]}
      />
      <section className="page-section">
        <div className="section-header">
          <h3>异常组件分组</h3>
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
