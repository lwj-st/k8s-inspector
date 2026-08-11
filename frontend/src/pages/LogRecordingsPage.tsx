import { useEffect, useMemo, useRef, useState } from "react";

import {
  ApiClientError,
  deleteLogRecording,
  discoverNamespaces,
  getLogRecording,
  getLogRecordingStorage,
  listLogRecordingLogs,
  listLogRecordingPods,
  listLogRecordings,
  listTemplates,
  matchLogRecordingTemplates,
  stopLogRecording,
  updateLogRecording,
} from "../api/client";
import type {
  LogRecording,
  LogRecordingLine,
  LogRecordingPod,
  LogRecordingTemplateMatch,
  LogRecordingViewMode,
  FaultTemplate,
  NamespaceSummary,
  Page,
} from "../api/types";
import { ConfirmPopoverButton, ConfirmPopoverPrompt } from "../components/ConfirmPopoverButton";

const pageSize = 20;
const logPageSize = 100;

function formatTime(value?: string | null) {
  if (!value) {
    return "--";
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function formatBytes(value: number) {
  if (value >= 1024 * 1024 * 1024) {
    return `${(value / 1024 / 1024 / 1024).toFixed(1)} GiB`;
  }
  if (value >= 1024 * 1024) {
    return `${(value / 1024 / 1024).toFixed(1)} MiB`;
  }
  if (value >= 1024) {
    return `${(value / 1024).toFixed(1)} KiB`;
  }
  return `${value} B`;
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "--";
  }
  if (typeof value === "string") {
    return value;
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function statusText(status: LogRecording["status"]) {
  return {
    recording: "记录中",
    completed: "已结束",
    auto_completed: "已自动结束",
    failed: "失败",
  }[status];
}

function truncatedText(value: boolean) {
  return value ? "已截断" : "未截断";
}

function stopReasonText(reason?: LogRecording["stop_reason"] | null) {
  if (!reason) {
    return "--";
  }
  return {
    user_stopped: "用户手动结束",
    system_default_timeout: "到达系统默认时长",
    selected_duration_timeout: "到达本次指定时长",
    max_recording_bytes_reached: "达到单记录日志上限",
    collection_failed: "采集失败",
    recovery_failed_after_restart: "系统重启后恢复失败",
  }[reason];
}

function recordingNamespacesText(recording: LogRecording) {
  const namespaces = (recording as LogRecording & { namespaces?: string[] }).namespaces ?? [];
  return namespaces.length > 0 ? namespaces.join("、") : recording.namespace;
}

function countdown(recording: LogRecording | null, nowMs = Date.now()) {
  if (!recording || recording.status !== "recording") {
    return "--";
  }
  const diff = new Date(recording.planned_end_at).getTime() - nowMs;
  if (diff <= 0) {
    return "即将结束";
  }
  const minutes = Math.floor(diff / 60000);
  const seconds = Math.floor((diff % 60000) / 1000);
  return `${minutes}分${seconds.toString().padStart(2, "0")}秒`;
}

function errorMessage(error: unknown) {
  if (error instanceof ApiClientError) {
    const reason = typeof error.details.reason === "string" ? error.details.reason : null;
    return reason ?? error.message;
  }
  return error instanceof Error ? error.message : "请求失败";
}

function highlightText(text: string, keyword: string) {
  const trimmed = keyword.trim();
  if (!trimmed) {
    return text;
  }
  const escaped = trimmed.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const parts = text.split(new RegExp(`(${escaped})`, "ig"));
  return parts.map((part, index) =>
    part.toLowerCase() === trimmed.toLowerCase()
      ? <mark key={`${part}-${index}`}>{part}</mark>
      : <span key={`${part}-${index}`}>{part}</span>,
  );
}

function uniqueContainers(lines: LogRecordingLine[]) {
  return Array.from(new Set(lines.map((line) => line.container_name))).sort();
}

export function LogRecordingsPage() {
  const [namespaces, setNamespaces] = useState<NamespaceSummary[]>([]);
  const [filterNamespace, setFilterNamespace] = useState("");
  const [records, setRecords] = useState<Page<LogRecording> | null>(null);
  const [recordPage, setRecordPage] = useState(1);
  const [storageText, setStorageText] = useState("");
  const [storageWarning, setStorageWarning] = useState(false);
  const [storageFull, setStorageFull] = useState(false);
  const [selected, setSelected] = useState<LogRecording | null>(null);
  const [pods, setPods] = useState<LogRecordingPod[]>([]);
  const [selectedPod, setSelectedPod] = useState<string>("");
  const [selectedContainer, setSelectedContainer] = useState<string>("");
  const [view, setView] = useState<LogRecordingViewMode>("folded");
  const [logs, setLogs] = useState<Page<LogRecordingLine> | null>(null);
  const [logPage, setLogPage] = useState(1);
  const [search, setSearch] = useState("");
  const [matches, setMatches] = useState<LogRecordingTemplateMatch[]>([]);
  const [selectedMatch, setSelectedMatch] = useState<LogRecordingTemplateMatch | null>(null);
  const [matchTemplate, setMatchTemplate] = useState<FaultTemplate | null>(null);
  const [templates, setTemplates] = useState<FaultTemplate[] | null>(null);
  const [pendingTemplateMatchCount, setPendingTemplateMatchCount] = useState<number | null>(null);
  const [activeSearchIndex, setActiveSearchIndex] = useState(0);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tick, setTick] = useState(0);
  const logLineRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const matchesRef = useRef<HTMLDivElement | null>(null);

  const hasRunningRecords = useMemo(() => (records?.items ?? []).some((item) => item.status === "recording"), [records]);
  const searchLineIds = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    if (!keyword || !logs) {
      return [];
    }
    return logs.items.filter((line) => line.line_text.toLowerCase().includes(keyword)).map((line) => line.id);
  }, [logs, search]);
  const searchCount = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    if (!keyword || !logs) {
      return 0;
    }
    return logs.items.reduce((count, line) => count + (line.line_text.toLowerCase().includes(keyword) ? 1 : 0), 0);
  }, [logs, search]);
  const activeSearchLineId = searchLineIds[activeSearchIndex] ?? null;
  const nowMs = useMemo(() => Date.now(), [tick]);
  const historyTotalPages = Math.max(1, Math.ceil((records?.total ?? 0) / (records?.page_size ?? pageSize)));

  useEffect(() => {
    void loadInitial();
  }, []);

  useEffect(() => {
    const recordingId = Number(new URLSearchParams(window.location.search).get("recordingId"));
    if (!Number.isInteger(recordingId) || recordingId < 1) {
      return;
    }
    void getLogRecording(recordingId)
      .then((recording) => {
        setSelected(recording);
        setFilterNamespace(recording.namespace);
      })
      .catch((err) => setError(errorMessage(err)));
  }, []);

  useEffect(() => {
    setRecordPage(1);
    void loadRecords(1);
  }, [filterNamespace]);

  useEffect(() => {
    const timer = window.setInterval(() => setTick((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!hasRunningRecords) {
      return;
    }
    const timer = window.setInterval(() => void loadRecords(recordPage), 5000);
    return () => window.clearInterval(timer);
  }, [hasRunningRecords, filterNamespace, recordPage]);

  useEffect(() => {
    if (selected) {
      void loadPods(selected.id);
    }
  }, [selected?.id]);

  useEffect(() => {
    if (selected && selectedPod && selectedContainer) {
      void loadLogs(selected.id, selectedPod, selectedContainer, logPage, view);
    }
  }, [selected?.id, selectedPod, selectedContainer, logPage, view]);

  useEffect(() => {
    setActiveSearchIndex(0);
  }, [search, logs?.page, selectedPod, selectedContainer]);

  useEffect(() => {
    if (activeSearchLineId) {
      logLineRefs.current[activeSearchLineId]?.scrollIntoView({ block: "center" });
    }
  }, [activeSearchLineId]);

  async function loadInitial() {
    try {
      const [namespaceData, storage] = await Promise.all([
        discoverNamespaces(),
        getLogRecordingStorage(),
        loadRecords(1),
      ]);
      setNamespaces(namespaceData.namespaces);
      applyStorage(storage);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  function applyStorage(storage: Awaited<ReturnType<typeof getLogRecordingStorage>>) {
    setStorageText(`${formatBytes(storage.used_bytes)} / ${formatBytes(storage.max_bytes)} (${storage.used_percent}%)`);
    setStorageWarning(storage.warning);
    setStorageFull(storage.full);
  }

  async function refreshStorage() {
    applyStorage(await getLogRecordingStorage());
  }

  async function loadRecords(page = recordPage) {
    const result = await listLogRecordings({ page, page_size: pageSize, namespace: filterNamespace || null });
    setRecords(result);
    if (selected) {
      const refreshed = result.items.find((item) => item.id === selected.id);
      if (refreshed) {
        setSelected(refreshed);
      }
    }
    return result;
  }

  async function changeRecordPage(nextPage: number) {
    setRecordPage(nextPage);
    await loadRecords(nextPage);
  }

  async function loadPods(recordingId: number) {
    try {
      const result = await listLogRecordingPods(recordingId);
      setPods(result);
      const nextPod = result[0]?.pod_name ?? "";
      setSelectedPod((current) => current || nextPod);
      setSelectedContainer((current) => current || result[0]?.container_names[0] || "");
      if (!nextPod) {
        setSelectedContainer("");
        setLogs(null);
      }
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function loadLogs(recordingId: number, podName: string, containerName: string, page: number, mode: LogRecordingViewMode) {
    try {
      const result = await listLogRecordingLogs(recordingId, podName, containerName, {
        page,
        page_size: logPageSize,
        view: mode,
      });
      setLogs(result);
      const nextContainers = uniqueContainers(result.items);
      if (!containerName && nextContainers[0]) {
        setSelectedContainer(nextContainers[0]);
      }
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function stop(recordingId: number) {
    setBusy(true);
    setError(null);
    try {
      const updated = await stopLogRecording(recordingId);
      setSelected(updated);
      setMessage("记录已结束");
      await loadRecords(recordPage);
      await refreshStorage();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function renameSelected() {
    if (!selected) {
      return;
    }
    const nextName = window.prompt("日志名称", selected.name);
    if (nextName === null || !nextName.trim()) {
      return;
    }
    try {
      const updated = await updateLogRecording(selected.id, { name: nextName.trim() });
      setSelected(updated);
      await loadRecords(recordPage);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function updateNote() {
    if (!selected) {
      return;
    }
    const nextNote = window.prompt("备注", selected.note ?? "");
    if (nextNote === null) {
      return;
    }
    try {
      const updated = await updateLogRecording(selected.id, { note: nextNote.trim() || null });
      setSelected(updated);
      await loadRecords(recordPage);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function remove(recording: LogRecording) {
    try {
      await deleteLogRecording(recording.id);
      if (selected?.id === recording.id) {
        setSelected(null);
        setPods([]);
        setLogs(null);
      }
      await loadRecords(recordPage);
      await refreshStorage();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function runTemplateMatch() {
    if (!selected) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await matchLogRecordingTemplates(selected.id);
      setMatches(result);
      setSelectedMatch(null);
      setMatchTemplate(null);
      setPendingTemplateMatchCount(result.length > 0 ? result.length : null);
      setMessage(result.length > 0 ? `命中 ${result.length} 条模板结果` : "未命中日志类模板");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function selectRecord(recording: LogRecording) {
    setSelected(recording);
    setSelectedPod("");
    setSelectedContainer("");
    setLogs(null);
    setMatches([]);
  }

  function selectPodContainer(pod: LogRecordingPod, containerName = pod.container_names[0] ?? "") {
    setSelectedPod(pod.pod_name);
    setSelectedContainer(containerName);
    setLogs(null);
    setLogPage(1);
  }

  async function openMatchDetails(match: LogRecordingTemplateMatch) {
    setSelectedMatch(match);
    setMatchTemplate(null);
    try {
      const loadedTemplates = templates ?? await listTemplates();
      if (!templates) {
        setTemplates(loadedTemplates);
      }
      setMatchTemplate(loadedTemplates.find((template) => template.id === match.template_id) ?? null);
    } catch {
      setMatchTemplate(null);
    }
  }

  function moveSearch(delta: number) {
    if (searchLineIds.length === 0) {
      return;
    }
    setActiveSearchIndex((current) => (current + delta + searchLineIds.length) % searchLineIds.length);
  }

  const displaySelected = selected ? { ...selected } : null;

  return (
    <section className="page-section log-recordings-page">
      <div className="section-header">
        <div>
          <h2>日志记录</h2>
          <p className="inline-note">查看正在记录和已经完成的日志记录任务。</p>
        </div>
        <button type="button" onClick={() => void loadRecords()}>刷新</button>
      </div>

      {error ? <p className="form-error">{error}</p> : null}
      {message ? <p className="form-success">{message}</p> : null}
      <p className={storageWarning ? "form-error" : "inline-note"}>
        日志存储：{storageText || "--"}{storageFull ? "，已达到上限，请删除旧记录或调整配置" : ""}
      </p>

      <div className="section-header log-recording-history-header">
        <h3>记录列表</h3>
        <label>
          名称空间
          <select value={filterNamespace} onChange={(event) => setFilterNamespace(event.target.value)}>
            <option value="">全部</option>
            {namespaces.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}
          </select>
        </label>
      </div>
      <div className="table-scroll-shell">
        <table className="compact-table">
          <thead>
            <tr>
              <th>名称</th>
              <th>名称空间</th>
              <th>状态</th>
              <th>开始时间</th>
              <th>结束原因</th>
              <th>日志行</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {(records?.items ?? []).map((item) => (
              <tr key={item.id}>
                <td>{item.name}</td>
                <td>{recordingNamespacesText(item)}</td>
                <td>{statusText(item.status)}</td>
                <td>{formatTime(item.started_at)}</td>
                <td>{item.error_message ?? stopReasonText(item.stop_reason)}</td>
                <td>{item.folded_line_count}/{item.raw_line_count}</td>
                <td>
                  <button type="button" onClick={() => selectRecord(item)}>查看</button>
                  {item.status === "recording" ? <button type="button" onClick={() => void stop(item.id)}>结束</button> : null}
                  <ConfirmPopoverButton
                    className="button-danger"
                    disabled={busy}
                    title="确认删除"
                    message={`确定要删除日志记录“${item.name}”吗？删除后无法恢复。`}
                    confirmText="确认删除"
                    confirmingText="删除中..."
                    onConfirm={() => remove(item)}
                  >
                    删除
                  </ConfirmPopoverButton>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pagination-row">
        <button type="button" disabled={recordPage <= 1} onClick={() => void changeRecordPage(Math.max(1, recordPage - 1))}>上一页</button>
        <span>{records?.page ?? recordPage} / {historyTotalPages}</span>
        <button type="button" disabled={recordPage >= historyTotalPages} onClick={() => void changeRecordPage(recordPage + 1)}>下一页</button>
      </div>

      {displaySelected ? (
        <section className="log-recording-detail">
          <div className="section-header">
            <div>
              <h3>{displaySelected.name}</h3>
              <p className="inline-note">
                {recordingNamespacesText(displaySelected)} · {statusText(displaySelected.status)} · {formatBytes(displaySelected.total_bytes)} · 已脱敏
              </p>
              {displaySelected.error_message ? <p className="inline-note">失败原因：{displaySelected.error_message}</p> : null}
            </div>
            <div className="log-recording-actions">
              <button type="button" onClick={renameSelected}>改名</button>
              <button type="button" onClick={updateNote}>备注</button>
              {displaySelected.status === "recording" ? <button type="button" className="button-danger" onClick={() => void stop(displaySelected.id)}>结束记录</button> : null}
              <span className="log-recording-template-action">
                <button type="button" onClick={() => void runTemplateMatch()} disabled={busy}>模板匹配</button>
                {pendingTemplateMatchCount ? (
                  <ConfirmPopoverPrompt
                    title="发现命中模板"
                    message={`已命中 ${pendingTemplateMatchCount} 条模板结果，是否查看？`}
                    confirmText="查看"
                    onCancel={() => setPendingTemplateMatchCount(null)}
                    onConfirm={() => {
                      setPendingTemplateMatchCount(null);
                      window.setTimeout(() => matchesRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
                    }}
                  />
                ) : null}
              </span>
            </div>
          </div>
          <dl className="log-recording-meta">
            <div><dt>计划结束</dt><dd>{formatTime(displaySelected.planned_end_at)}</dd></div>
            <div><dt>实际结束</dt><dd>{formatTime(displaySelected.ended_at)}</dd></div>
            <div><dt>倒计时</dt><dd>{countdown(displaySelected, nowMs)}</dd></div>
            <div><dt>Pod/容器</dt><dd>{displaySelected.pod_count}/{displaySelected.container_count}</dd></div>
            <div><dt>截断状态</dt><dd>{truncatedText(displaySelected.truncated)}</dd></div>
          </dl>
          {displaySelected.note ? <p className="inline-note">备注：{displaySelected.note}</p> : null}

          <div className="log-recording-workbench">
            <aside className="log-recording-pods">
              {pods.length === 0 ? <p className="empty-copy">暂无已采集日志的 Pod。</p> : pods.map((pod) => (
                <article
                  key={pod.pod_uid}
                  className={selectedPod === pod.pod_name ? "log-recording-pod-card log-recording-pod-active" : "log-recording-pod-card"}
                >
                  <div className="log-recording-pod-heading">
                    <strong className="log-recording-pod-name" title={pod.pod_name}>{pod.pod_name}</strong>
                    <button
                      type="button"
                      className="log-recording-pod-summary"
                      title={pod.pod_name}
                      onClick={() => selectPodContainer(pod)}
                    >
                      <span>名称空间：{pod.namespace} · 异常关键字 {pod.keyword_hit_count} · 日志 {pod.folded_line_count}/{pod.raw_line_count} 行{pod.truncated ? " · 已截断" : ""}</span>
                    </button>
                  </div>
                  {pod.container_names.length > 0 ? (
                    <div className="log-recording-container-list">
                      {pod.container_names.map((container) => (
                        <button
                          type="button"
                          key={container}
                          className={selectedPod === pod.pod_name && selectedContainer === container ? "log-recording-container-active" : ""}
                          title={`${pod.pod_name} / ${container}`}
                          onClick={() => selectPodContainer(pod, container)}
                        >
                          {container}
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p className="log-recording-pod-note">未采集到容器日志</p>
                  )}
                </article>
              ))}
            </aside>

            <div className="log-recording-logs">
              <div className="log-recording-toolbar">
                <select value={view} onChange={(event) => setView(event.target.value as LogRecordingViewMode)}>
                  <option value="folded">折叠视图</option>
                  <option value="raw">原始逐行</option>
                </select>
                <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索当前日志" />
                <span>{search ? `${searchCount} 行命中` : ""}</span>
                <button type="button" disabled={searchLineIds.length === 0} onClick={() => moveSearch(-1)}>上一个</button>
                <button type="button" disabled={searchLineIds.length === 0} onClick={() => moveSearch(1)}>下一个</button>
                <button type="button" disabled={!search} onClick={() => setSearch("")}>清空</button>
              </div>
              {!selectedPod ? <p className="empty-copy">请选择 Pod。</p> : null}
              {selectedPod && !selectedContainer ? <p className="empty-copy">该 Pod 暂无可查看的容器日志。</p> : null}
              {logs ? (
                <>
                  <div className="log-block log-recording-log-block">
                    {logs.items.length === 0 ? <p>暂无日志。</p> : logs.items.map((line) => (
                      <div
                        key={line.id}
                        ref={(node) => {
                          logLineRefs.current[line.id] = node;
                        }}
                        className={`log-recording-line${line.id === activeSearchLineId ? " log-recording-line-active" : ""}`}
                      >
                        <span className="log-recording-time">{formatTime(line.log_time ?? line.collected_at)}</span>
                        <span className="log-recording-repeat" aria-hidden={line.repeat_count <= 1}>
                          {line.repeat_count > 1 ? `x${line.repeat_count}` : ""}
                        </span>
                        <code>{highlightText(line.line_text, search)}</code>
                      </div>
                    ))}
                  </div>
                  <div className="pagination-row">
                    <button type="button" disabled={logPage <= 1} onClick={() => setLogPage((value) => Math.max(1, value - 1))}>上一页</button>
                    <span>{logs.page} / {Math.max(1, Math.ceil(logs.total / logs.page_size))}</span>
                    <button type="button" disabled={logs.page * logs.page_size >= logs.total} onClick={() => setLogPage((value) => value + 1)}>下一页</button>
                  </div>
                </>
              ) : null}
            </div>
          </div>

          {matches.length > 0 ? (
            <div className="table-scroll-shell" ref={matchesRef}>
              <table className="compact-table">
                <thead>
                  <tr><th className="log-recording-match-heading">命中模板</th><th>名称空间</th><th>Pod</th><th>容器</th><th>关键字</th><th>建议</th><th>操作</th></tr>
                </thead>
                <tbody>
                  {matches.map((item) => (
                    <tr key={item.id}>
                      <td>{item.template_name}</td>
                      <td>{item.namespace ?? "--"}</td>
                      <td>{item.pod_name}</td>
                      <td>{item.container_name}</td>
                      <td>{item.keyword}</td>
                      <td>{item.suggestion ?? "--"}</td>
                      <td>
                        <button type="button" onClick={() => void openMatchDetails(item)}>详情</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          {selectedMatch ? (
            <div className="modal-backdrop" role="presentation" onMouseDown={() => setSelectedMatch(null)}>
              <section
                className="modal-card modal-card-polished log-recording-template-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="log-recording-template-detail-title"
                onMouseDown={(event) => event.stopPropagation()}
              >
                <div className="section-header">
                  <div>
                    <h3 id="log-recording-template-detail-title">命中模板详情</h3>
                    <p className="inline-note">{selectedMatch.template_name} · {selectedMatch.namespace ?? "--"} · {selectedMatch.pod_name}</p>
                  </div>
                  <button type="button" onClick={() => setSelectedMatch(null)}>关闭</button>
                </div>
                <dl className="log-recording-template-detail-grid">
                  <div><dt>模板 ID</dt><dd>{selectedMatch.template_id ?? "--"}</dd></div>
                  <div><dt>模板名称</dt><dd>{selectedMatch.template_name}</dd></div>
                  <div><dt>严重级别</dt><dd>{selectedMatch.severity}</dd></div>
                  <div><dt>启用状态</dt><dd>{matchTemplate ? (matchTemplate.enabled ? "启用" : "停用") : "--"}</dd></div>
                  <div><dt>场景</dt><dd>{matchTemplate?.scenario ?? "--"}</dd></div>
                  <div><dt>命中时间</dt><dd>{formatTime(selectedMatch.created_at)}</dd></div>
                  <div><dt>名称空间</dt><dd>{selectedMatch.namespace ?? "--"}</dd></div>
                  <div><dt>Pod</dt><dd>{selectedMatch.pod_name}</dd></div>
                  <div><dt>容器</dt><dd>{selectedMatch.container_name}</dd></div>
                  <div><dt>关键字</dt><dd>{selectedMatch.keyword}</dd></div>
                </dl>
                {matchTemplate ? (
                  <>
                    <div className="log-recording-template-section">
                      <strong>对象组</strong>
                      {(matchTemplate.targets?.length ? matchTemplate.targets : matchTemplate.target_groups ?? []).map((target, index) => (
                        <code key={index}>{formatValue(target)}</code>
                      ))}
                    </div>
                    <div className="log-recording-template-section">
                      <strong>匹配条件</strong>
                      {matchTemplate.match_conditions.map((condition, index) => (
                        <code key={index}>{formatValue(condition)}</code>
                      ))}
                    </div>
                    <dl className="log-recording-template-detail-grid">
                      <div><dt>原因</dt><dd>{matchTemplate.reason || "--"}</dd></div>
                      <div><dt>建议</dt><dd>{matchTemplate.suggestion || selectedMatch.suggestion || "--"}</dd></div>
                      <div><dt>处理命令</dt><dd>{matchTemplate.command || "--"}</dd></div>
                      <div><dt>风险说明</dt><dd>{matchTemplate.risk_note || "--"}</dd></div>
                    </dl>
                  </>
                ) : (
                  <p className="inline-note">未能加载完整模板信息，仅展示本次命中记录。</p>
                )}
                <div className="log-recording-template-section">
                  <strong>匹配上下文</strong>
                  <code>{selectedMatch.matched_context || "--"}</code>
                </div>
              </section>
            </div>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}
