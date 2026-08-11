import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";

import {
  ApiClientError,
  batchAcknowledgeIssues,
  batchIgnoreIssues,
  batchUnignoreIssues,
  getIssueFilterOptions,
  listInspectionRuns,
  listIssues,
} from "../api/client";
import type {
  InspectionRun,
  Issue,
  IssueBatchResponse,
  IssueFilterOption,
  IssueFilterOptions,
  IssueListParams,
  IssueSeverity,
  IssueSortMode,
  IssueStatus,
  Page,
} from "../api/types";
import { CoveragePanel } from "../components/CoveragePanel";
import { ConfirmPopoverButton } from "../components/ConfirmPopoverButton";
import { StatusBadge } from "../components/StatusBadge";

const allowedSeverities = new Set<IssueSeverity>(["critical", "warning", "info"]);
const allowedStatuses = new Set<IssueStatus>(["open", "recovered", "ignored"]);
const allowedSorts = new Set<IssueSortMode>(["priority", "duration", "last_changed"]);
const problemWorkbenchRefreshKey = "k8s-inspector:problem-workbench-refresh";
const autoRefreshEnabledKey = "k8s-inspector:problem-workbench-auto-refresh";
const autoRefreshIntervalKey = "k8s-inspector:problem-workbench-auto-refresh-interval";
const defaultAutoRefreshIntervalSeconds = 30;

function getProblemWorkbenchRefreshMarker() {
  try {
    return window.localStorage?.getItem?.(problemWorkbenchRefreshKey) ?? null;
  } catch {
    return null;
  }
}

function readStoredBoolean(key: string, fallback: boolean) {
  try {
    const value = window.localStorage?.getItem?.(key);
    if (value === "true") {
      return true;
    }
    if (value === "false") {
      return false;
    }
  } catch {
    // localStorage 不可用时使用默认值。
  }
  return fallback;
}

function readStoredIntervalSeconds() {
  try {
    const value = Number(window.localStorage?.getItem?.(autoRefreshIntervalKey));
    if (Number.isInteger(value) && value >= 5 && value <= 600) {
      return value;
    }
  } catch {
    // localStorage 不可用时使用默认值。
  }
  return defaultAutoRefreshIntervalSeconds;
}

function persistSetting(key: string, value: string) {
  try {
    window.localStorage?.setItem?.(key, value);
  } catch {
    // 设置持久化失败不影响当前页面操作。
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
  const [selectedIssueIds, setSelectedIssueIds] = useState<Set<number>>(() => new Set());
  const [batchNote, setBatchNote] = useState("");
  const [batchSaving, setBatchSaving] = useState(false);
  const [batchMessage, setBatchMessage] = useState<string | null>(null);
  const [batchError, setBatchError] = useState<string | null>(null);
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(() => readStoredBoolean(autoRefreshEnabledKey, false));
  const [autoRefreshIntervalSeconds, setAutoRefreshIntervalSeconds] = useState(readStoredIntervalSeconds);
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
    setSelectedIssueIds(new Set());
    setBatchMessage(null);
    setBatchError(null);
  }, [query]);

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
    persistSetting(autoRefreshEnabledKey, String(autoRefreshEnabled));
  }, [autoRefreshEnabled]);

  useEffect(() => {
    persistSetting(autoRefreshIntervalKey, String(autoRefreshIntervalSeconds));
  }, [autoRefreshIntervalSeconds]);

  useEffect(() => {
    if (!autoRefreshEnabled) {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      if (document.visibilityState !== "hidden") {
        refreshWorkbench();
      }
    }, autoRefreshIntervalSeconds * 1000);
    return () => window.clearInterval(intervalId);
  }, [autoRefreshEnabled, autoRefreshIntervalSeconds, refreshWorkbench]);

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
  const visibleIssueIds = issues?.items.map((issue) => issue.id) ?? [];
  const selectedCount = selectedIssueIds.size;
  const allVisibleSelected = visibleIssueIds.length > 0 && visibleIssueIds.every((id) => selectedIssueIds.has(id));
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

  function toggleIssue(issueId: number, checked: boolean) {
    setSelectedIssueIds((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(issueId);
      } else {
        next.delete(issueId);
      }
      return next;
    });
  }

  function toggleVisibleIssues(checked: boolean) {
    setSelectedIssueIds((current) => {
      const next = new Set(current);
      for (const issueId of visibleIssueIds) {
        if (checked) {
          next.add(issueId);
        } else {
          next.delete(issueId);
        }
      }
      return next;
    });
  }

  function batchSummary(result: IssueBatchResponse) {
    if (result.failed_count > 0) {
      return `批量操作完成：成功 ${result.succeeded_count} 项，失败 ${result.failed_count} 项。`;
    }
    return `批量操作完成：成功 ${result.succeeded_count} 项。`;
  }

  async function runBatchAction(action: "acknowledge" | "ignore" | "unignore") {
    const issueIds = Array.from(selectedIssueIds);
    if (issueIds.length === 0) {
      return;
    }
    setBatchError(null);
    setBatchMessage(null);
    if (action === "acknowledge" && !batchNote.trim()) {
      setBatchError("请填写批量确认备注");
      return;
    }
    setBatchSaving(true);
    try {
      const result = action === "acknowledge"
        ? await batchAcknowledgeIssues(issueIds, batchNote.trim())
        : action === "ignore"
          ? await batchIgnoreIssues(issueIds)
          : await batchUnignoreIssues(issueIds);
      setBatchMessage(batchSummary(result));
      setSelectedIssueIds(new Set());
      setBatchNote("");
      refreshWorkbench();
      if (result.failed_count > 0) {
        const failed = result.results.filter((item) => !item.succeeded);
        setBatchError(failed.map((item) => `#${item.issue_id}：${item.error ?? "操作失败"}`).join("；"));
      }
    } catch (reason) {
      setBatchError(displayError(reason));
    } finally {
      setBatchSaving(false);
    }
  }

  return (
    <section className="page-section problem-workbench">
      <header className="workbench-heading">
        <div>
          <h1>问题工作台</h1>
        </div>
        <div className="status-pair">
          {summary.latestRun ? <StatusBadge status={summary.latestRun.status} /> : null}
          <button
            type="button"
            className="page-refresh-button"
            onClick={refreshWorkbench}
            disabled={issuesLoading || summary.loading}
            aria-label="刷新问题工作台"
          >
            <span
              aria-hidden="true"
              className={issuesLoading || summary.loading ? "page-refresh-icon page-refresh-icon-spinning" : "page-refresh-icon"}
            >
              ↻
            </span>
            {issuesLoading || summary.loading ? "刷新中…" : "刷新"}
          </button>
          <div className="auto-refresh-controls" aria-label="自动刷新">
            <label className="toggle-label">
              <input
                type="checkbox"
                checked={autoRefreshEnabled}
                onChange={(event) => setAutoRefreshEnabled(event.target.checked)}
              />
              自动刷新
            </label>
            <label>
              间隔
              <input
                type="number"
                min={5}
                max={600}
                step={5}
                value={autoRefreshIntervalSeconds}
                onChange={(event) => {
                  const value = Number(event.target.value);
                  if (Number.isInteger(value) && value >= 5 && value <= 600) {
                    setAutoRefreshIntervalSeconds(value);
                  }
                }}
                aria-label="自动刷新间隔秒数"
              />
              秒
            </label>
          </div>
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

        <div className="batch-action-bar" aria-label="批量操作">
          <strong>已选择 {selectedCount} 项</strong>
          <label>
            统一确认备注
            <input
              value={batchNote}
              onChange={(event) => setBatchNote(event.target.value)}
              placeholder="填写批量确认备注"
              disabled={batchSaving || selectedCount === 0}
            />
          </label>
          <div className="button-row">
            <button
              type="button"
              className="primary-action"
              disabled={batchSaving || selectedCount === 0}
              onClick={() => void runBatchAction("acknowledge")}
            >
              批量确认
            </button>
            {status !== "ignored" ? (
              <ConfirmPopoverButton
                className="danger-action"
                disabled={batchSaving || selectedCount === 0}
                title="确认忽略"
                message={`确认忽略选中的 ${selectedCount} 个问题？忽略后默认不再出现在开放问题列表。`}
                confirmText="确认忽略"
                confirmingText="忽略中..."
                onConfirm={() => runBatchAction("ignore")}
              >
                批量忽略
              </ConfirmPopoverButton>
            ) : (
              <ConfirmPopoverButton
                className="primary-action"
                disabled={batchSaving || selectedCount === 0}
                title="确认恢复"
                message={`确认恢复显示选中的 ${selectedCount} 个问题？恢复后会重新出现在开放问题列表。`}
                confirmText="确认恢复"
                confirmingText="恢复中..."
                onConfirm={() => runBatchAction("unignore")}
              >
                批量恢复显示
              </ConfirmPopoverButton>
            )}
          </div>
        </div>
        {batchMessage ? <div className="feedback-banner feedback-success" role="status">{batchMessage}</div> : null}
        {batchError ? <div className="feedback-banner feedback-error" role="alert">{batchError}</div> : null}

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
                  <col className="issue-col-select" />
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
                    <th>
                      <input
                        type="checkbox"
                        aria-label="选择当前页全部问题"
                        checked={allVisibleSelected}
                        onChange={(event) => toggleVisibleIssues(event.target.checked)}
                      />
                    </th>
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
                      <td>
                        <input
                          type="checkbox"
                          aria-label={`选择问题 ${issue.id}`}
                          checked={selectedIssueIds.has(issue.id)}
                          onChange={(event) => toggleIssue(issue.id, event.target.checked)}
                        />
                      </td>
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
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={selectedIssueIds.has(issue.id)}
                        onChange={(event) => toggleIssue(issue.id, event.target.checked)}
                      />
                      选择
                    </label>
                    <div className="status-pair">
                      <StatusBadge status={issue.severity} />
                      <StatusBadge status={issue.status} />
                    </div>
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
