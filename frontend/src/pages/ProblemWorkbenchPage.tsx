import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";

import { ApiClientError, getIssueFilterOptions, listInspectionRuns, listIssues } from "../api/client";
import type {
  InspectionRun,
  Issue,
  IssueFilterOption,
  IssueFilterOptions,
  IssueListParams,
  IssueSeverity,
  IssueSortMode,
  IssueStatus,
  Page,
} from "../api/types";
import { CoveragePanel } from "../components/CoveragePanel";
import { StatusBadge } from "../components/StatusBadge";

const allowedSeverities = new Set<IssueSeverity>(["critical", "warning", "info"]);
const allowedStatuses = new Set<IssueStatus>(["open", "recovered", "ignored"]);
const allowedSorts = new Set<IssueSortMode>(["priority", "duration", "last_changed"]);
const problemWorkbenchRefreshKey = "k8s-inspector:problem-workbench-refresh";

function getProblemWorkbenchRefreshMarker() {
  try {
    return window.localStorage?.getItem?.(problemWorkbenchRefreshKey) ?? null;
  } catch {
    return null;
  }
}

function displayError(reason: unknown) {
  if (reason instanceof ApiClientError) {
    return `${reason.message}${reason.requestId ? `（请求 ID：${reason.requestId}）` : ""}`;
  }
  return reason instanceof Error ? reason.message : "请求失败";
}

function displayTime(value?: string | null) {
  if (!value) {
    return "--";
  }
  const time = new Date(value);
  return Number.isNaN(time.getTime()) ? value : time.toLocaleString();
}

function durationLabel(issue: Issue) {
  const start = new Date(issue.first_seen_at).getTime();
  const endValue = issue.status === "recovered" ? issue.recovered_at : new Date().toISOString();
  const end = new Date(endValue ?? issue.last_seen_at).getTime();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) {
    return "--";
  }
  const minutes = Math.floor((end - start) / 60_000);
  if (minutes < 60) {
    return `${minutes} 分钟`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours} 小时`;
  }
  return `${Math.floor(hours / 24)} 天`;
}

function resourceLabel(issue: Issue) {
  return `${issue.resource.kind}/${issue.resource.name}`;
}

function inspectionScopeLabel(run: InspectionRun) {
  if (run.scope.type === "pod") {
    return `${run.scope.namespace ?? "--"}/${run.scope.pod_name ?? "--"}`;
  }
  if (run.scope.type === "namespace") {
    return run.scope.namespaces.join("、") || run.scope.namespace || "名称空间";
  }
  return "全集群";
}

function selectableOptions(options: IssueFilterOption[], selected: string) {
  if (!selected || options.some((option) => option.value === selected)) {
    return options;
  }
  return [{ value: selected, label: selected }, ...options];
}

type IssueTableTextCellProps = {
  value: string;
  wrap?: boolean;
};

function IssueTableTextCell({ value, wrap = false }: IssueTableTextCellProps) {
  return (
    <div
      className={`issue-table-text-cell${wrap ? " issue-table-text-cell-wrap" : ""}`}
      title={value}
    >
      <span className={wrap ? "issue-table-wrap-text" : "issue-table-ellipsis-text"}>
        {value}
      </span>
    </div>
  );
}

type SummaryState = {
  open: number | null;
  critical: number | null;
  warning: number | null;
  latestRun: InspectionRun | null;
  error: string | null;
  loading: boolean;
};

export function ProblemWorkbenchPage() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [issues, setIssues] = useState<Page<Issue> | null>(null);
  const [issuesLoading, setIssuesLoading] = useState(true);
  const [issuesError, setIssuesError] = useState<string | null>(null);
  const [filterOptions, setFilterOptions] = useState<IssueFilterOptions>({
    namespaces: [],
    resource_kinds: [],
    source_checks: [],
  });
  const [summary, setSummary] = useState<SummaryState>({
    open: null,
    critical: null,
    warning: null,
    latestRun: null,
    error: null,
    loading: true,
  });

  const status = allowedStatuses.has(searchParams.get("status") as IssueStatus)
    ? searchParams.get("status") as IssueStatus
    : "open";
  const severity = allowedSeverities.has(searchParams.get("severity") as IssueSeverity)
    ? searchParams.get("severity") as IssueSeverity
    : undefined;
  const sort = allowedSorts.has(searchParams.get("sort") as IssueSortMode)
    ? searchParams.get("sort") as IssueSortMode
    : "priority";
  const namespace = searchParams.get("namespace") ?? "";
  const resourceKind = searchParams.get("resource_kind") ?? "";
  const sourceCheck = searchParams.get("source_check") ?? "";
  const parsedPage = Number(searchParams.get("page") ?? 1);
  const page = Number.isInteger(parsedPage) && parsedPage > 0 ? parsedPage : 1;

  const query = useMemo<IssueListParams>(() => ({
    status,
    severity,
    namespace: namespace || undefined,
    resource_kind: resourceKind || undefined,
    source_check: sourceCheck || undefined,
    sort,
    page,
    page_size: 20,
  }), [status, severity, namespace, resourceKind, sourceCheck, sort, page]);

  const updateFilter = useCallback((key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set(key, value);
    } else {
      next.delete(key);
    }
    if (key !== "page") {
      next.delete("page");
    }
    setSearchParams(next);
  }, [searchParams, setSearchParams]);

  const loadIssues = useCallback(async () => {
    setIssuesLoading(true);
    setIssuesError(null);
    try {
      setIssues(await listIssues(query));
    } catch (reason) {
      setIssuesError(displayError(reason));
    } finally {
      setIssuesLoading(false);
    }
  }, [query]);

  useEffect(() => {
    void loadIssues();
  }, [loadIssues]);

  useEffect(() => {
    void getIssueFilterOptions()
      .then(setFilterOptions)
      .catch(() => {
        // 问题列表仍可使用；保留 URL 中的已有筛选值。
      });
  }, []);

  const loadSummary = useCallback(async () => {
    setSummary((current) => ({ ...current, loading: true, error: null }));
    const [openResult, criticalResult, warningResult, runResult] = await Promise.allSettled([
      listIssues({ status: "open", page: 1, page_size: 1 }),
      listIssues({ status: "open", severity: "critical", page: 1, page_size: 1 }),
      listIssues({ status: "open", severity: "warning", page: 1, page_size: 1 }),
      listInspectionRuns({ page: 1, page_size: 1 }),
    ]);
    const failures = [openResult, criticalResult, warningResult, runResult]
      .filter((result) => result.status === "rejected") as PromiseRejectedResult[];
    setSummary({
      open: openResult.status === "fulfilled" ? openResult.value.total : null,
      critical: criticalResult.status === "fulfilled" ? criticalResult.value.total : null,
      warning: warningResult.status === "fulfilled" ? warningResult.value.total : null,
      latestRun: runResult.status === "fulfilled" ? runResult.value.items[0] ?? null : null,
      error: failures.length > 0 ? displayError(failures[0].reason) : null,
      loading: false,
    });
  }, []);

  useEffect(() => {
    void loadSummary();
  }, [loadSummary]);

  const refreshWorkbench = useCallback(() => {
    void loadIssues();
    void loadSummary();
    void getIssueFilterOptions()
      .then(setFilterOptions)
      .catch(() => undefined);
  }, [loadIssues, loadSummary]);

  useEffect(() => {
    let lastRefreshMarker = getProblemWorkbenchRefreshMarker();
    function refreshIfMarkerChanged() {
      const marker = getProblemWorkbenchRefreshMarker();
      if (marker && marker !== lastRefreshMarker) {
        lastRefreshMarker = marker;
        refreshWorkbench();
      }
    }
    function handleVisibilityChange() {
      if (document.visibilityState === "visible") {
        refreshIfMarkerChanged();
      }
    }
    window.addEventListener("focus", refreshIfMarkerChanged);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      window.removeEventListener("focus", refreshIfMarkerChanged);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [refreshWorkbench]);

  const completedCoverage = summary.latestRun?.coverage.filter(
    (item) => item.status === "passed" || item.status === "abnormal",
  ).length ?? 0;
  const coverageTotal = summary.latestRun?.coverage.length ?? 0;
  const coveragePercent = coverageTotal > 0 ? Math.round((completedCoverage / coverageTotal) * 100) : null;
  const hasIncompleteCoverage = summary.latestRun?.coverage.some(
    (item) => item.status === "skipped" || item.status === "failed",
  ) ?? false;
  const totalPages = issues ? Math.max(1, Math.ceil(issues.total / issues.page_size)) : 1;
  const namespaceOptions = selectableOptions(filterOptions.namespaces, namespace);
  const resourceKindOptions = selectableOptions(filterOptions.resource_kinds, resourceKind);
  const sourceCheckOptions = selectableOptions(filterOptions.source_checks, sourceCheck);
  const sourceCheckLabels = new Map(
    filterOptions.source_checks.map((option) => [option.value, option.label]),
  );

  const summaryCards = [
    { label: "开放问题", value: summary.open, filterKey: "status", filterValue: "open" },
    { label: "严重", value: summary.critical, filterKey: "severity", filterValue: "critical" },
    { label: "警告", value: summary.warning, filterKey: "severity", filterValue: "warning" },
    { label: "最近一次恢复", value: summary.latestRun?.recovered_issue_count ?? null },
    { label: "最近巡检", value: summary.latestRun ? displayTime(summary.latestRun.finished_at ?? summary.latestRun.started_at) : null },
    { label: "检查完成率", value: coveragePercent === null ? null : `${coveragePercent}%` },
  ];

  return (
    <section className="page-section problem-workbench">
      <header className="workbench-heading">
        <div>
          <p className="eyebrow">可信巡检与主动发现</p>
          <h1>问题工作台</h1>
          <p>汇总手动巡检和定时巡检发现的当前问题；同一问题会自动去重和更新状态。</p>
        </div>
        <div className="status-pair">
          {summary.latestRun ? <StatusBadge status={summary.latestRun.status} /> : null}
          <button
            type="button"
            className="workbench-refresh-button"
            onClick={refreshWorkbench}
            disabled={issuesLoading || summary.loading}
          >
            刷新
          </button>
        </div>
      </header>

      {summary.error ? (
        <div className="feedback-banner feedback-warning" role="status">
          部分概览暂时不可用：{summary.error}
          <button type="button" className="inline-action" onClick={() => void loadSummary()}>重试概览</button>
        </div>
      ) : null}

      <section className="summary-card-grid" aria-label="问题概览">
        {summaryCards.map((card) => (
          <button
            type="button"
            className="summary-card"
            key={card.label}
            onClick={() => card.filterKey && card.filterValue && updateFilter(card.filterKey, card.filterValue)}
            disabled={!card.filterKey}
          >
            <span>{card.label}</span>
            <strong>{summary.loading ? "…" : card.value ?? "--"}</strong>
          </button>
        ))}
      </section>

      <section className="panel issue-list-panel" aria-labelledby="issue-list-title">
        <div className="section-header">
          <div>
            <h2 id="issue-list-title">{status === "open" ? "开放问题" : status === "ignored" ? "已忽略问题" : "已恢复问题"}</h2>
            <p className="inline-note">结果来自所有已完成的巡检，排序由服务端在完整结果上完成。</p>
          </div>
          <span className="section-tip">共 {issues?.total ?? "--"} 项</span>
        </div>

        <div className="issue-filter-grid">
          <label>
            状态
            <select value={status} onChange={(event) => updateFilter("status", event.target.value)}>
              <option value="open">开放</option>
              <option value="recovered">已恢复</option>
              <option value="ignored">已忽略</option>
            </select>
          </label>
          <label>
            严重程度
            <select value={severity ?? ""} onChange={(event) => updateFilter("severity", event.target.value)}>
              <option value="">全部</option>
              <option value="critical">严重</option>
              <option value="warning">警告</option>
              <option value="info">提示</option>
            </select>
          </label>
          <label>
            名称空间
            <select value={namespace} onChange={(event) => updateFilter("namespace", event.target.value)}>
              <option value="">全部名称空间</option>
              {namespaceOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <label>
            资源类型
            <select value={resourceKind} onChange={(event) => updateFilter("resource_kind", event.target.value)}>
              <option value="">全部资源类型</option>
              {resourceKindOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <label>
            巡检项
            <select value={sourceCheck} onChange={(event) => updateFilter("source_check", event.target.value)}>
              <option value="">全部巡检项</option>
              {sourceCheckOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <label>
            排序
            <select value={sort} onChange={(event) => updateFilter("sort", event.target.value)}>
              <option value="priority">处置优先</option>
              <option value="duration">持续最久</option>
              <option value="last_changed">最近变化</option>
            </select>
          </label>
        </div>
        <button type="button" className="text-button" onClick={() => setSearchParams({ status: "open" })}>
          清除筛选
        </button>

        {issuesLoading ? <p aria-live="polite">正在加载问题…</p> : null}
        {issuesError ? (
          <div className="feedback-banner feedback-error" role="alert">
            问题列表读取失败：{issuesError}
            <button type="button" className="inline-action" onClick={() => void loadIssues()}>重试</button>
          </div>
        ) : null}
        {!issuesLoading && !issuesError && issues?.items.length === 0 ? (
          <div className="empty-state">
            <strong>{searchParams.toString() === "status=open" || searchParams.toString() === "" ? "当前没有开放问题" : "当前筛选没有结果"}</strong>
            <p>{hasIncompleteCoverage ? "但最近巡检有检查未完成，当前不能确认全部正常。" : "可以查看检查覆盖或发起一次手动巡检。"}</p>
          </div>
        ) : null}

        {issues && issues.items.length > 0 ? (
          <>
            <div className="responsive-table-shell issue-desktop-table">
              <table className="compact-table issue-workbench-table">
                <colgroup>
                  <col className="issue-col-severity" />
                  <col className="issue-col-summary" />
                  <col className="issue-col-resource" />
                  <col className="issue-col-namespace" />
                  <col className="issue-col-source" />
                  <col className="issue-col-status" />
                  <col className="issue-col-duration" />
                  <col className="issue-col-last-seen" />
                  <col className="issue-col-ack" />
                  <col className="issue-col-action" />
                </colgroup>
                <thead>
                  <tr>
                    <th>严重程度</th>
                    <th>结论</th>
                    <th>资源</th>
                    <th>名称空间</th>
                    <th>巡检项</th>
                    <th>状态</th>
                    <th>持续时间</th>
                    <th>最后发现</th>
                    <th>确认</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {issues.items.map((issue) => (
                    <tr key={issue.id}>
                      <td className="issue-cell-badge"><StatusBadge status={issue.severity} /></td>
                      <td className="issue-cell-summary"><IssueTableTextCell value={issue.summary} wrap /></td>
                      <td><IssueTableTextCell value={resourceLabel(issue)} /></td>
                      <td><IssueTableTextCell value={issue.resource.namespace ?? "集群级"} /></td>
                      <td><IssueTableTextCell value={sourceCheckLabels.get(issue.source_check) ?? issue.source_check} /></td>
                      <td className="issue-cell-badge"><StatusBadge status={issue.status} /></td>
                      <td><IssueTableTextCell value={durationLabel(issue)} /></td>
                      <td><IssueTableTextCell value={displayTime(issue.last_seen_at)} /></td>
                      <td className="issue-cell-ack">
                        <span className={`issue-ack-badge ${issue.acknowledged_at ? "issue-ack-badge-confirmed" : "issue-ack-badge-pending"}`}>
                          {issue.acknowledged_at ? "已确认" : "未确认"}
                        </span>
                      </td>
                      <td className="issue-cell-actions">
                        <Link
                          to={`/issues/${issue.id}`}
                          state={{ from: `${location.pathname}${location.search}` }}
                          className="text-link"
                        >
                          查看详情
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="issue-mobile-list" data-testid="issue-mobile-list">
              {issues.items.map((issue) => (
                <article className="issue-mobile-card" key={issue.id}>
                  <div className="section-header">
                    <StatusBadge status={issue.severity} />
                    <StatusBadge status={issue.status} />
                  </div>
                  <strong>{issue.summary}</strong>
                  <p>{resourceLabel(issue)} · {issue.resource.namespace ?? "集群级"}</p>
                  <small>巡检项：{sourceCheckLabels.get(issue.source_check) ?? issue.source_check}</small>
                  <small>持续 {durationLabel(issue)} · {issue.acknowledged_at ? "已确认" : "未确认"}</small>
                  <Link
                    to={`/issues/${issue.id}`}
                    state={{ from: `${location.pathname}${location.search}` }}
                    className="text-link"
                  >
                    查看详情
                  </Link>
                </article>
              ))}
            </div>
            <nav className="pagination" aria-label="问题分页">
              <button type="button" disabled={page <= 1} onClick={() => updateFilter("page", String(page - 1))}>上一页</button>
              <span>第 {page}/{totalPages} 页</span>
              <button type="button" disabled={page >= totalPages} onClick={() => updateFilter("page", String(page + 1))}>下一页</button>
            </nav>
          </>
        ) : null}
      </section>

      <div id="latest-coverage">
        <CoveragePanel
          coverage={summary.latestRun?.coverage ?? []}
          title={summary.latestRun
            ? `最近一次${summary.latestRun.trigger === "scheduled" ? "定时" : "手动"}巡检覆盖（${inspectionScopeLabel(summary.latestRun)}）`
            : "最近一次巡检覆盖"}
        />
      </div>
    </section>
  );
}
