import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";

import {
  ApiClientError,
  createLogRecording,
  discoverNamespacePods,
  getLogRecording,
  getSettings,
  ignoreWhitelistLogHit,
  listLogRecordings,
  previewLogRecording,
  runNamespaceLogInspection,
  stopLogRecording,
} from "../api/client";
import type {
  InspectedPod,
  KeywordHit,
  LogRecording,
  LogRecordingDurationSource,
  LogTimeRangeRequest,
  SavedInspectionTarget,
} from "../api/types";
import { ConfirmDeleteButton } from "../components/ConfirmDeleteButton";
import { KeyValueList } from "../components/KeyValueList";
import { StatusBadge } from "../components/StatusBadge";
import { useDiscoverNamespaceLabels } from "../features/inspections/useDiscoverNamespaceLabels";
import { useDiscoverNamespaces } from "../features/inspections/useDiscoverNamespaces";
import { labelSelectorOptionsForPod } from "../features/inspections/podLabels";
import { useRunNamespaceInspection } from "../features/inspections/useRunNamespaceInspection";
import { useRunPodInspection } from "../features/inspections/useRunPodInspection";
import { useSavedInspectionTargets } from "../features/inspections/useSavedInspectionTargets";
import { findLogKeywordMatchRanges, normalizeTerminalLogText } from "../features/logs/logText";

type PodScopeMode = "all" | "label" | "single";
type PodModalType = "save" | "import" | "export" | "ignore" | null;
type RangeInspectionConfirmation = {
  namespace: string;
  scopeMode: Exclude<PodScopeMode, "single">;
  labelSelector: string;
  podCount: number | null;
  logTimeRange: LogTimeRangeRequest;
};
type IgnoreDraft = {
  pod: InspectedPod;
  hit: KeywordHit;
  namespace: string;
  labelSelector: string;
  keyword: string;
  note: string;
};
type RecordingDurationMode = LogRecordingDurationSource;
type RecordingLists = {
  running: LogRecording[];
  ended: LogRecording[];
};

function logHitContext(hit: KeywordHit) {
  const context = hit.context_text?.trim();
  if (!context) {
    return hit.matched_text;
  }
  return context.toLowerCase().includes(hit.matched_text.toLowerCase())
    ? context
    : `命中行：${hit.matched_text}\n\n上下文：\n${context}`;
}

function logHitTime(hit: KeywordHit) {
  const timedHit = hit as KeywordHit & {
    matched_at?: string | null;
    log_time?: string | null;
    timestamp?: string | null;
    observed_at?: string | null;
  };
  return timedHit.matched_at ?? timedHit.log_time ?? timedHit.timestamp ?? timedHit.observed_at ?? "服务端未返回";
}

function isLogContextTruncated(hit: KeywordHit) {
  return /已截断|已省略|省略/.test(hit.context_text ?? "");
}

function normalizeLogText(value: string) {
  return normalizeTerminalLogText(value);
}

function toLocalInputValue(value: Date) {
  const offsetMs = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offsetMs).toISOString().slice(0, 16);
}

function defaultCustomLogStart() {
  return toLocalInputValue(new Date(Date.now() - 15 * 60_000));
}

function defaultCustomLogEnd() {
  return toLocalInputValue(new Date());
}

function renderHighlightedLog(value: string, keyword: string) {
  const text = normalizeLogText(value);
  const ranges = findLogKeywordMatchRanges(text, keyword);
  if (ranges.length === 0) {
    return text;
  }

  const parts: ReactNode[] = [];
  let cursor = 0;

  ranges.forEach(({ start, end }) => {
    if (start > cursor) {
      parts.push(text.slice(cursor, start));
    }
    const match = text.slice(start, end);
    parts.push(
      <mark key={`${start}-${match}`} className="log-keyword-highlight">
        {match}
      </mark>,
    );
    cursor = end;
  });

  if (cursor < text.length) {
    parts.push(text.slice(cursor));
  }

  return parts;
}

function resourceUsageItems(resourceUsage: Record<string, string> | undefined) {
  if (!resourceUsage || Object.keys(resourceUsage).length === 0) {
    return [];
  }
  return [
    { label: "CPU", value: resourceUsage.cpu },
    { label: "内存", value: resourceUsage.memory },
    { label: "CPU / limit", value: resourceUsage.cpu_limit_percent },
    { label: "内存 / limit", value: resourceUsage.memory_limit_percent },
    { label: "CPU / request", value: resourceUsage.cpu_request_percent },
    { label: "内存 / request", value: resourceUsage.memory_request_percent },
    { label: "采样时间", value: resourceUsage.sample_time },
  ].filter((item): item is { label: string; value: string } => Boolean(item.value));
}

type PodInspectionPageProps = {
  initialScopeMode?: PodScopeMode;
};

function formatSavedTargetScope(target: SavedInspectionTarget) {
  if (target.pod_name && target.pod_name.trim()) {
    return `单个 Pod / ${target.pod_name}`;
  }
  if (target.label_selector && target.label_selector.trim()) {
    return `Label Selector / ${target.label_selector}`;
  }
  return "全部 Pod";
}

function formatLogCollectionTimeRange(data: ReturnType<typeof useRunNamespaceInspection>["data"]) {
  const range = data?.log_collection?.time_range;
  if (!range) {
    return null;
  }
  if (range.mode === "recent" && range.recent_minutes) {
    return `最近 ${range.recent_minutes === 60 ? "1 小时" : `${range.recent_minutes} 分钟`}`;
  }
  const start = new Date(range.start_time);
  const end = range.end_time ? new Date(range.end_time) : null;
  const startText = Number.isNaN(start.getTime()) ? range.start_time : start.toLocaleString();
  const endText = end && !Number.isNaN(end.getTime()) ? end.toLocaleString() : "当前时间";
  return `${startText} 至 ${endText}`;
}

function formatRecordingTime(value?: string | null) {
  if (!value) {
    return "服务端未返回";
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function displayRecordingNamespaces(recording: LogRecording) {
  const namespaces = (recording as LogRecording & { namespaces?: string[] }).namespaces ?? [];
  return namespaces.length > 0 ? namespaces : [recording.namespace];
}

export function PodInspectionPage({ initialScopeMode = "single" }: PodInspectionPageProps) {
  const [namespaceSearch, setNamespaceSearch] = useState("");
  const [namespace, setNamespace] = useState("");
  const [scopeMode, setScopeMode] = useState<PodScopeMode>(initialScopeMode);
  const [labelSelector, setLabelSelector] = useState("");
  const [podName, setPodName] = useState("");
  const [podOptions, setPodOptions] = useState<string[]>([]);
  const [podOptionsLoading, setPodOptionsLoading] = useState(false);
  const [podOptionsError, setPodOptionsError] = useState<string | null>(null);
  const [podOptionsNamespace, setPodOptionsNamespace] = useState<string | null>(null);
  const [maxLogPods, setMaxLogPods] = useState<number | null>(null);
  const [maxLogTimeRangeMinutes, setMaxLogTimeRangeMinutes] = useState(120);
  const [logLimitError, setLogLimitError] = useState<string | null>(null);
  const [logTimeRangeMode, setLogTimeRangeMode] = useState<"recent" | "custom">("recent");
  const [recentLogMinutes, setRecentLogMinutes] = useState(15);
  const [customLogStart, setCustomLogStart] = useState(defaultCustomLogStart);
  const [customLogEnd, setCustomLogEnd] = useState(defaultCustomLogEnd);
  const [recordPanelOpen, setRecordPanelOpen] = useState(false);
  const [recordName, setRecordName] = useState("");
  const [recordNote, setRecordNote] = useState("");
  const [selectedRecordingNamespaces, setSelectedRecordingNamespaces] = useState<string[]>([]);
  const [recordDurationMode, setRecordDurationMode] = useState<RecordingDurationMode>("system_default");
  const [recordDurationMinutes, setRecordDurationMinutes] = useState(20);
  const [runningRecordings, setRunningRecordings] = useState<LogRecording[]>([]);
  const [endedRecordings, setEndedRecordings] = useState<LogRecording[]>([]);
  const [recordingBusy, setRecordingBusy] = useState(false);
  const [stoppingRecordingIds, setStoppingRecordingIds] = useState<number[]>([]);
  const [recordingMessage, setRecordingMessage] = useState<string | null>(null);
  const [recordingError, setRecordingError] = useState<string | null>(null);
  const [selectedRangePodName, setSelectedRangePodName] = useState<string | null>(null);
  const [targetName, setTargetName] = useState("");
  const [editingTargetId, setEditingTargetId] = useState<number | null>(null);
  const [exportContent, setExportContent] = useState("");
  const [importContent, setImportContent] = useState("");
  const [modalType, setModalType] = useState<PodModalType>(null);
  const [savedTargetsOpen, setSavedTargetsOpen] = useState(false);
  const [ignoredLogKeys, setIgnoredLogKeys] = useState<string[]>([]);
  const [ignoringLogKeys, setIgnoringLogKeys] = useState<string[]>([]);
  const [ignoreMessage, setIgnoreMessage] = useState<string | null>(null);
  const [ignoreDraft, setIgnoreDraft] = useState<IgnoreDraft | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const [rangeConfirmation, setRangeConfirmation] = useState<RangeInspectionConfirmation | null>(null);
  const { data: namespaceDiscovery, loading: namespaceLoading, error: namespaceError } = useDiscoverNamespaces();
  const { data: labelDiscovery, loading: labelLoading, error: labelError } = useDiscoverNamespaceLabels(namespace);
  const namespaceInspection = useRunNamespaceInspection();
  const podInspection = useRunPodInspection();
  const {
    targets,
    loading: targetsLoading,
    saving: targetSaving,
    error: targetsError,
    saveTarget,
    updateTarget,
    deleteTarget,
    exportTargets,
    importTargets,
  } = useSavedInspectionTargets("pod");

  useEffect(() => {
    let alive = true;
    void getSettings()
      .then((result) => {
        if (!alive) {
          return;
        }
        setMaxLogPods(result.inspection_policy.max_log_pods);
        setMaxLogTimeRangeMinutes(result.inspection_policy.reproduction_logs?.max_log_inspection_range_minutes ?? 120);
        setLogLimitError(null);
      })
      .catch((reason) => {
        if (!alive) {
          return;
        }
        setMaxLogPods(null);
        setLogLimitError(reason instanceof Error ? reason.message : "未知错误");
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    const normalizedNamespace = namespace.trim();
    if (!normalizedNamespace) {
      setRunningRecordings([]);
      setEndedRecordings([]);
      return;
    }

    let alive = true;
    void loadRecordingLists(normalizedNamespace)
      .then((recordings) => {
        if (!alive) {
          return;
        }
        setRunningRecordings(recordings.running);
        setEndedRecordings(recordings.ended);
      })
      .catch(() => {
        if (alive) {
          setRunningRecordings([]);
          setEndedRecordings([]);
        }
      });

    return () => {
      alive = false;
    };
  }, [namespace]);

  async function loadRecordingLists(targetNamespace: string): Promise<RecordingLists> {
    const result = await listLogRecordings({ namespace: targetNamespace, page: 1, page_size: 20 });
    return {
      running: result.items.filter((item) => item.status === "recording"),
      ended: result.items.filter((item) => item.status !== "recording").slice(0, 10),
    };
  }

  const filteredNamespaces = useMemo(() => {
    const keyword = namespaceSearch.trim().toLowerCase();
    const items = namespaceDiscovery?.namespaces ?? [];
    if (!keyword) {
      return items;
    }
    return items.filter((item) => item.name.toLowerCase().includes(keyword));
  }, [namespaceDiscovery, namespaceSearch]);
  const recordingNamespaceNames = useMemo(
    () => (namespaceDiscovery?.namespaces ?? []).map((item) => item.name).sort((left, right) => left.localeCompare(right)),
    [namespaceDiscovery],
  );

  const rangePods = namespaceInspection.data?.pods ?? [];
  const getActiveLogHits = (pod: InspectedPod) =>
    pod.log_hits.filter((hit) => !hit.whitelisted && !ignoredLogKeys.includes(`${pod.name}:${hit.keyword}:${hit.matched_text}`));
  const sortedRangePods = useMemo(
    () => [...rangePods].sort((left, right) => getActiveLogHits(right).length - getActiveLogHits(left).length),
    [rangePods, ignoredLogKeys],
  );
  const selectedRangePod =
    sortedRangePods.find((pod) => pod.name === selectedRangePodName) ??
    sortedRangePods[0] ??
    null;
  const currentPod = scopeMode === "single" ? podInspection.data?.pod ?? null : selectedRangePod;
  const currentLogHits = currentPod ? getActiveLogHits(currentPod) : [];
  const inspectedLogPods = scopeMode === "single"
    ? (podInspection.data?.pod ? [podInspection.data.pod] : [])
    : rangePods;
  const activeLogHitCount = inspectedLogPods.reduce((total, pod) => total + getActiveLogHits(pod).length, 0);
  const currentScopeText =
    !namespace.trim()
      ? "未选择名称空间"
      : scopeMode === "all"
        ? `${namespace.trim()} / 全部 Pod`
        : scopeMode === "label"
          ? `${namespace.trim()} / ${labelSelector.trim() || "未填写 Label Selector"}`
          : `${namespace.trim()} / ${podName.trim() || "未选择 Pod"}`;
  const inspectionPoints = useMemo(
    () => targets.filter((target) => Boolean(target.label_selector?.trim()) && !target.pod_name?.trim()),
    [targets],
  );
  const defaultInspectionPointName = namespace.trim() && labelSelector.trim() ? `${namespace.trim()} / ${labelSelector.trim()}` : "";
  const getPodResultStatus = (pod: InspectedPod) => (getActiveLogHits(pod).length > 0 ? "error" : "healthy");
  const getPodResultSummary = (pod: InspectedPod) => {
    const activeHits = getActiveLogHits(pod);
    if (activeHits.length > 0) {
      const keywords = Array.from(new Set(activeHits.map((hit) => hit.keyword))).slice(0, 3);
      return `命中关键字：${keywords.join("、")}`;
    }
    return "未命中日志关键字";
  };

  useEffect(() => {
    if (scopeMode !== "single" || !namespace.trim() || podOptionsNamespace === namespace.trim()) {
      return;
    }

    let alive = true;
    setPodOptionsLoading(true);
    setPodOptionsError(null);
    void discoverNamespacePods(namespace.trim())
      .then((result) => {
        if (!alive) {
          return;
        }
        setPodOptions(result.pods.map((pod) => pod.name));
        setPodOptionsNamespace(namespace.trim());
      })
      .catch((reason) => {
        if (!alive) {
          return;
        }
        setPodOptionsError(reason instanceof Error ? reason.message : "未知错误");
      })
      .finally(() => {
        if (alive) {
          setPodOptionsLoading(false);
        }
      });

    return () => {
      alive = false;
    };
  }, [namespace, podOptionsNamespace, scopeMode]);

  function resetAfterInspection() {
    setIgnoredLogKeys([]);
    setIgnoringLogKeys([]);
    setIgnoreMessage(null);
    setSelectedRangePodName(null);
  }

  function resetNamespaceContext(nextNamespace: string) {
    setNamespace(nextNamespace);
    setPodName("");
    setLabelSelector("");
    setPodOptions([]);
    setPodOptionsNamespace(null);
    setPodOptionsError(null);
    setSelectedRangePodName(null);
    setRangeConfirmation(null);
  }

  function discoveredRangePodCount(
    targetNamespace: string,
    targetScopeMode: Exclude<PodScopeMode, "single">,
    targetLabelSelector: string,
  ) {
    if (targetScopeMode === "all") {
      return namespaceDiscovery?.namespaces.find((item) => item.name === targetNamespace)?.pod_count ?? null;
    }
    if (labelDiscovery?.namespace !== targetNamespace) {
      return null;
    }
    return labelDiscovery.labels.find((item) => item.selector === targetLabelSelector)?.pod_count ?? null;
  }

  async function resolveRangePodCount(
    targetNamespace: string,
    targetScopeMode: Exclude<PodScopeMode, "single">,
    targetLabelSelector: string,
  ) {
    const cachedPodCount = discoveredRangePodCount(targetNamespace, targetScopeMode, targetLabelSelector);
    if (cachedPodCount !== null) {
      return cachedPodCount;
    }

    try {
      const discovery = await discoverNamespacePods(
        targetNamespace,
        targetScopeMode === "label" ? targetLabelSelector : null,
      );
      return discovery.pod_count;
    } catch {
      return null;
    }
  }

  async function runRangeInspection(request: RangeInspectionConfirmation) {
    await namespaceInspection.submitWith(
      () => runNamespaceLogInspection(
        request.namespace,
        request.scopeMode === "label" ? request.labelSelector : null,
        request.logTimeRange,
      ),
    );
    resetAfterInspection();
  }

  function buildLogTimeRange(): LogTimeRangeRequest | null {
    if (logTimeRangeMode === "recent") {
      if (!Number.isInteger(recentLogMinutes) || recentLogMinutes < 1) {
        setSaveMessage("日志时间范围必须是正整数分钟");
        return null;
      }
      if (recentLogMinutes > maxLogTimeRangeMinutes) {
        setSaveMessage(`日志时间范围不能超过 ${maxLogTimeRangeMinutes} 分钟`);
        return null;
      }
      return { mode: "recent", recent_minutes: recentLogMinutes };
    }

    const start = new Date(customLogStart);
    const end = new Date(customLogEnd);
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
      setSaveMessage("自定义日志时间范围需要填写开始时间和结束时间");
      return null;
    }
    if (start >= end) {
      setSaveMessage("日志开始时间必须早于结束时间");
      return null;
    }
    if (end > new Date()) {
      setSaveMessage("日志结束时间不能晚于当前时间");
      return null;
    }
    if ((end.getTime() - start.getTime()) / 60_000 > maxLogTimeRangeMinutes) {
      setSaveMessage(`日志时间范围不能超过 ${maxLogTimeRangeMinutes} 分钟`);
      return null;
    }
    return { mode: "custom", start_time: start.toISOString(), end_time: end.toISOString() };
  }

  async function requestRangeInspection(
    targetNamespace: string,
    targetScopeMode: Exclude<PodScopeMode, "single">,
    targetLabelSelector: string,
  ) {
    const logTimeRange = buildLogTimeRange();
    if (!logTimeRange) {
      return;
    }
    const podCount = await resolveRangePodCount(targetNamespace, targetScopeMode, targetLabelSelector);
    const request = {
      namespace: targetNamespace,
      scopeMode: targetScopeMode,
      labelSelector: targetLabelSelector,
      podCount,
      logTimeRange,
    };
    if (podCount === null || maxLogPods === null || podCount > maxLogPods) {
      setRangeConfirmation(request);
      return;
    }
    await runRangeInspection(request);
  }

  async function handleRunInspection() {
    const normalizedNamespace = namespace.trim();
    if (!normalizedNamespace) {
      setSaveMessage("请先选择名称空间");
      return;
    }

    setSaveMessage(null);

    if (scopeMode === "single") {
      if (!podName.trim()) {
        setSaveMessage("单个 Pod 巡检前，请先从下拉框选择 Pod");
        return;
      }
      await podInspection.submit(normalizedNamespace, podName.trim());
      resetAfterInspection();
      return;
    }

    await requestRangeInspection(
      normalizedNamespace,
      scopeMode,
      scopeMode === "label" ? labelSelector.trim() : "",
    );
  }

  async function handleToggleRecording() {
    setRecordingError(null);
    setRecordingMessage(null);
    setRecordPanelOpen(true);
    if (namespace.trim() && selectedRecordingNamespaces.length === 0) {
      setSelectedRecordingNamespaces([namespace.trim()]);
    }
    if (!recordName.trim()) {
      setRecordName(namespace.trim() ? `${namespace.trim()} 复现记录` : "复现日志记录");
    }
  }

  function toggleRecordingNamespace(targetNamespace: string) {
    setSelectedRecordingNamespaces((current) =>
      current.includes(targetNamespace)
        ? current.filter((item) => item !== targetNamespace)
        : [...current, targetNamespace].sort((left, right) => left.localeCompare(right)),
    );
  }

  async function handleStopRecording(recording: LogRecording) {
    setStoppingRecordingIds((current) => [...current, recording.id]);
    setRecordingError(null);
    setRecordingMessage(null);
    try {
      const stopped = await stopLogRecording(recording.id);
      setRunningRecordings((current) => current.filter((item) => item.id !== recording.id));
      setEndedRecordings((current) => [stopped, ...current.filter((item) => item.id !== stopped.id)].slice(0, 10));
      setRecordingMessage(`已停止记录：${stopped.name}`);
    } catch (reason) {
      if (reason instanceof ApiClientError && reason.status === 409) {
        try {
          const latest = await getLogRecording(recording.id);
          if (latest.status === "recording") {
            setRunningRecordings((current) => current.map((item) => item.id === latest.id ? latest : item));
            setRecordingError("记录仍在运行，请稍后重试结束");
          } else {
            setRunningRecordings((current) => current.filter((item) => item.id !== recording.id));
            setEndedRecordings((current) => [latest, ...current.filter((item) => item.id !== latest.id)].slice(0, 10));
            setRecordingMessage(`记录已结束：${latest.name}`);
          }
        } catch {
          const latestLists = await loadRecordingLists(recording.namespace);
          setRunningRecordings(latestLists.running);
          setEndedRecordings(latestLists.ended);
          if (latestLists.running.some((item) => item.id === recording.id)) {
            setRecordingError("记录状态已变化，请稍后重试结束");
          } else {
            setRecordingMessage("记录已结束");
          }
        }
        return;
      }
      setRecordingError(reason instanceof Error ? reason.message : "停止记录失败");
    } finally {
      setStoppingRecordingIds((current) => current.filter((item) => item !== recording.id));
    }
  }

  async function handleStartRecording(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedName = recordName.trim();
    const targetNamespaces = selectedRecordingNamespaces.filter((item) => recordingNamespaceNames.includes(item));
    if (targetNamespaces.length === 0) {
      setRecordingError("请选择至少一个名称空间");
      return;
    }
    if (!normalizedName) {
      setRecordingError("请填写日志名称");
      return;
    }
    if (recordDurationMode !== "system_default" && (!Number.isInteger(recordDurationMinutes) || recordDurationMinutes < 1)) {
      setRecordingError("记录时长必须是正整数分钟");
      return;
    }

    setRecordingBusy(true);
    setRecordingError(null);
    setRecordingMessage(null);
    try {
      for (const targetNamespace of targetNamespaces) {
        const preview = await previewLogRecording(targetNamespace);
        if (!preview.allowed) {
          setRecordingError(`${targetNamespace}：${preview.reason ?? "当前名称空间不允许开始记录"}`);
          return;
        }
      }
      const created = await createLogRecording({
        name: normalizedName,
        namespace: targetNamespaces[0],
        namespaces: targetNamespaces,
        note: recordNote.trim() || null,
        duration_source: recordDurationMode,
        duration_minutes: recordDurationMode === "system_default" ? null : recordDurationMinutes,
      });
      setRunningRecordings((current) => [
        created,
        ...current.filter((item) => item.id !== created.id),
      ]);
      setRecordPanelOpen(false);
      setRecordingMessage(`已开始日志记录：${created.name}`);
    } catch (reason) {
      setRecordingError(reason instanceof Error ? reason.message : "开始记录失败");
    } finally {
      setRecordingBusy(false);
    }
  }

  function openIgnoreLogHit(hit: KeywordHit) {
    if (!currentPod) {
      return;
    }

    const currentNamespace = scopeMode === "single" ? podInspection.data?.namespace ?? namespace : namespaceInspection.data?.namespace ?? namespace;
    const currentLabelSelector =
      scopeMode === "label"
        ? namespaceInspection.data?.inspection_target.label_selector ?? (labelSelector || null)
        : scopeMode === "single"
          ? podInspection.data?.inspection_target.label_selector ?? null
          : namespaceInspection.data?.inspection_target.label_selector ?? null;
    const options = labelSelectorOptionsForPod(currentPod, currentLabelSelector);
    setIgnoreDraft({
      pod: currentPod,
      hit,
      namespace: currentNamespace,
      labelSelector: options[0] ?? "",
      keyword: "",
      note: scopeMode === "single" ? "从 Pod 巡检结果忽略" : "从 Pod 范围巡检结果忽略",
    });
    setIgnoreMessage(null);
    setModalType("ignore");
  }

  function closeIgnoreModal() {
    setIgnoreDraft(null);
    setModalType(null);
  }

  async function handleConfirmIgnoreLogHit() {
    if (!ignoreDraft) {
      return;
    }

    const { pod, hit } = ignoreDraft;
    const hitKey = `${pod.name}:${hit.keyword}:${hit.matched_text}`;
    setIgnoringLogKeys((current) => [...current, hitKey]);
    setIgnoreMessage(null);

    try {
      await ignoreWhitelistLogHit({
        namespace: ignoreDraft.namespace.trim(),
        label_selector: ignoreDraft.labelSelector.trim() || null,
        pod_name_pattern: null,
        container_name: null,
        keyword: ignoreDraft.keyword.trim(),
        note: ignoreDraft.note.trim() || null,
      });
      setIgnoredLogKeys((current) => [...current, hitKey]);
      setIgnoreMessage(scopeMode === "single" ? "已加入白名单，后续 Pod 巡检会自动忽略该命中" : "已加入白名单，后续范围巡检会自动忽略该命中");
      closeIgnoreModal();
    } catch (reason) {
      setIgnoreMessage(reason instanceof Error ? `加入白名单失败：${reason.message}` : "加入白名单失败");
    } finally {
      setIgnoringLogKeys((current) => current.filter((item) => item !== hitKey));
    }
  }

  function applySavedTarget(target: SavedInspectionTarget) {
    setNamespaceSearch(target.namespace);
    resetNamespaceContext(target.namespace);
    setLabelSelector(target.label_selector ?? "");

    if (target.pod_name && target.pod_name.trim()) {
      setScopeMode("single");
      setPodName(target.pod_name);
      void podInspection.submit(target.namespace, target.pod_name).then(() => resetAfterInspection());
      return;
    }

    if (target.label_selector) {
      setScopeMode("label");
      void requestRangeInspection(target.namespace, "label", target.label_selector);
      return;
    }

    setScopeMode("all");
    void requestRangeInspection(target.namespace, "all", "");
  }

  function openCreateSaveModal() {
    if (scopeMode !== "label" || !namespace.trim() || !labelSelector.trim()) {
      setSaveMessage("只有 Label Selector 范围可以保存为巡检点");
      return;
    }
    setEditingTargetId(null);
    setTargetName(defaultInspectionPointName);
    setModalType("save");
  }

  function startEditingTarget(target: SavedInspectionTarget) {
    setEditingTargetId(target.id);
    setTargetName(target.name);
    setNamespaceSearch(target.namespace);
    resetNamespaceContext(target.namespace);
    setLabelSelector(target.label_selector ?? "");
    setScopeMode("label");
    setPodName("");
    setSavedTargetsOpen(true);
    setModalType("save");
  }

  async function handleSaveCurrentTarget() {
    const normalizedName = targetName.trim() || defaultInspectionPointName;
    const normalizedNamespace = namespace.trim();
    if (!normalizedNamespace) {
      setSaveMessage("请先选择名称空间");
      return;
    }
    if (scopeMode !== "label" || !labelSelector.trim()) {
      setSaveMessage("只有 Label Selector 范围可以保存为巡检点");
      return;
    }

    try {
      const payload = {
        name: normalizedName,
        namespace: normalizedNamespace,
        label_selector: labelSelector.trim(),
        pod_name: "",
        resource_scope: ["pods"],
      };

      if (editingTargetId !== null) {
        await updateTarget(editingTargetId, payload);
        setSaveMessage(`已更新 ${normalizedName}`);
      } else {
        await saveTarget(payload);
        setSaveMessage(`已保存 ${normalizedName}`);
      }

      setTargetName("");
      setEditingTargetId(null);
      setSavedTargetsOpen(true);
      setModalType(null);
    } catch (reason) {
      const detail = reason instanceof Error ? `：${reason.message}` : "";
      setSaveMessage(editingTargetId !== null ? `更新失败${detail}` : `保存失败${detail}`);
    }
  }

  async function handleDeleteTarget(target: SavedInspectionTarget) {
    try {
      await deleteTarget(target.id);
      setSaveMessage(`已删除 ${target.name}`);
      if (editingTargetId === target.id) {
        setEditingTargetId(null);
        setTargetName("");
      }
    } catch {
      setSaveMessage(`删除 ${target.name} 失败，请稍后重试`);
    }
  }

  async function handleOpenExportModal() {
    setCopyMessage(null);
    try {
      const items = await exportTargets();
      const labelTargets = items.filter((item) => Boolean(item.label_selector?.trim()) && !item.pod_name?.trim());
      setExportContent(JSON.stringify(labelTargets, null, 2));
      setModalType("export");
    } catch {
      setExportContent("导出失败");
      setModalType("export");
    }
  }

  async function handleCopyExport() {
    if (!exportContent) {
      return;
    }
    try {
      await navigator.clipboard.writeText(exportContent);
      setCopyMessage("导出内容已复制");
    } catch {
      setCopyMessage("当前环境不支持自动复制，请手动复制");
    }
  }

  async function handleImportTargets() {
    try {
      const parsed = JSON.parse(importContent) as Array<{
        name: string;
        target_type: "namespace" | "pod";
        namespace: string;
        label_selector?: string | null;
        pod_name?: string | null;
        resource_scope: string[];
      }>;
      const labelTargets = parsed.filter((item) => item.target_type === "pod" && Boolean(item.label_selector?.trim()) && !item.pod_name?.trim());
      const created = await importTargets(labelTargets);
      if (created.length === 0) {
        setSaveMessage("导入内容不包含 Label Selector 巡检点");
        return;
      }
      setSaveMessage(`已导入 ${created.length} 个巡检点`);
      setImportContent("");
      setSavedTargetsOpen(true);
      setModalType(null);
    } catch {
      setSaveMessage("导入失败，请检查 JSON 格式");
    }
  }

  const currentRunLabel = scopeMode === "single" ? "巡检单个 Pod" : "日志巡检";
  const listTitle = scopeMode === "single" ? "最近使用范围" : "Pod 列表";
  const activeLogTimeRangeText = formatLogCollectionTimeRange(namespaceInspection.data);

  return (
    <section className="page-section">
      <section className="panel workbench-hero log-inspection-hero">
        <div className="workbench-copy">
          <div className="section-header">
            <div>
              <h3>选择范围</h3>
            </div>
          </div>
          <div className="entry-form-grid entry-form-grid-compact">
            <label className="inline-search log-filter-search-field">
              筛选名称空间
              <input
                aria-label="筛选名称空间"
                value={namespaceSearch}
                onChange={(event) => setNamespaceSearch(event.target.value)}
                placeholder="例如：demo、prod、kube-system"
              />
            </label>
            <label className="log-filter-namespace-field">
              名称空间
              <select
                aria-label="名称空间"
                value={namespace}
                title={namespace || "请选择名称空间"}
                onChange={(event) => resetNamespaceContext(event.target.value)}
              >
                <option value="">请选择名称空间</option>
                {filteredNamespaces.map((item) => (
                  <option key={item.name} value={item.name}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="log-filter-scope-field">
              范围类型
              <select
                aria-label="范围类型"
                value={scopeMode}
                onChange={(event) => {
                  setScopeMode(event.target.value as PodScopeMode);
                  setIgnoreMessage(null);
                }}
              >
                <option value="all">全部 Pod</option>
                <option value="label">Label Selector</option>
                <option value="single">单个 Pod</option>
              </select>
            </label>
            {scopeMode !== "single" ? (
              <label className="label-selector-field log-filter-time-field">
                日志时间范围
                <select
                  aria-label="日志时间范围"
                  value={logTimeRangeMode === "recent" ? `recent:${recentLogMinutes}` : "custom"}
                  onChange={(event) => {
                    const value = event.target.value;
                    if (value === "custom") {
                      setLogTimeRangeMode("custom");
                      return;
                    }
                    setLogTimeRangeMode("recent");
                    setRecentLogMinutes(Number(value.split(":")[1]));
                  }}
                >
                  {[5, 15, 30, 60].map((minutes) => (
                    <option key={minutes} value={`recent:${minutes}`} disabled={minutes > maxLogTimeRangeMinutes}>
                      最近 {minutes === 60 ? "1 小时" : `${minutes} 分钟`}{minutes > maxLogTimeRangeMinutes ? "（超过上限）" : ""}
                    </option>
                  ))}
                  <option value="custom">自定义起止时间</option>
                </select>
              </label>
            ) : null}
            {scopeMode !== "single" && logTimeRangeMode === "custom" ? (
              <>
                <label className="label-selector-field">
                  日志开始时间
                  <input
                    aria-label="日志开始时间"
                    type="datetime-local"
                    value={customLogStart}
                    onChange={(event) => setCustomLogStart(event.target.value)}
                  />
                </label>
                <label className="label-selector-field">
                  日志结束时间
                  <input
                    aria-label="日志结束时间"
                    type="datetime-local"
                    value={customLogEnd}
                    onChange={(event) => setCustomLogEnd(event.target.value)}
                  />
                </label>
              </>
            ) : null}
          </div>

          {scopeMode === "label" ? (
            <div className="compact-subpanel label-selector-panel">
              <label className="label-selector-field">
                Label Selector
                <select
                  aria-label="Label Selector"
                  value={labelSelector}
                  onChange={(event) => setLabelSelector(event.target.value)}
                  disabled={!namespace.trim()}
                >
                  <option value="">{labelLoading ? "正在发现标签..." : "请选择自动发现候选"}</option>
                  {labelDiscovery?.labels.map((item) => (
                    <option key={item.selector} value={item.selector}>
                      {item.selector}（{item.pod_count} 个 Pod）
                    </option>
                  ))}
                </select>
              </label>
              <label className="label-selector-field">
                手动 Label Selector
                <input
                  aria-label="手动 Label Selector"
                  value={labelSelector}
                  onChange={(event) => setLabelSelector(event.target.value)}
                  placeholder="例如：app=demo-api"
                />
              </label>
              {labelError ? <p className="inline-note">标签发现失败：{labelError}</p> : null}
            </div>
          ) : null}

          {scopeMode === "single" ? (
            <label>
              Pod 名称
              <select
                aria-label="Pod 名称"
                value={podName}
                onChange={(event) => setPodName(event.target.value)}
                disabled={!namespace.trim() || podOptionsLoading}
              >
                <option value="">{podOptionsLoading ? "读取 Pod 中..." : "请选择 Pod"}</option>
                {podOptions.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
          ) : null}

          <div className="button-row log-inspection-action-row">
            <button
              type="button"
              onClick={() => void handleRunInspection()}
              disabled={
                scopeMode === "single"
                  ? podInspection.loading || !namespace.trim() || !podName.trim()
                  : namespaceInspection.loading || !namespace.trim() || (scopeMode === "label" && !labelSelector.trim())
              }
            >
              {podInspection.loading || namespaceInspection.loading ? "巡检中..." : currentRunLabel}
            </button>
            <button
              type="button"
              className="button-success"
              onClick={() => void handleToggleRecording()}
            >
              记录日志
            </button>
            <a className="mini-button text-button" href="/log-recordings">
              日志记录
            </a>
          </div>
          {recordPanelOpen ? (
            <form className="recording-inline-panel" onSubmit={(event) => void handleStartRecording(event)}>
              <div className="section-header">
                <div>
                  <h4>记录日志</h4>
                  <span className="section-tip">记录开始后，系统只保存该名称空间后续新增日志。</span>
                </div>
              </div>
              <div className="recording-form-grid">
                <label>
                  日志名称
                  <input
                    aria-label="日志名称"
                    value={recordName}
                    onChange={(event) => setRecordName(event.target.value)}
                    placeholder="例如：支付 500 复现"
                  />
                </label>
                <label>
                  记录时长
                  <select
                    aria-label="记录时长"
                    value={recordDurationMode === "system_default" ? "system_default" : String(recordDurationMinutes)}
                    onChange={(event) => {
                      const value = event.target.value;
                      if (value === "system_default") {
                        setRecordDurationMode("system_default");
                        return;
                      }
                      setRecordDurationMode(value === "custom" ? "custom" : "preset");
                      if (value !== "custom") {
                        setRecordDurationMinutes(Number(value));
                      }
                    }}
                  >
                    <option value="system_default">使用系统默认</option>
                    {[5, 10, 20, 30, 60].map((minutes) => (
                      <option key={minutes} value={minutes}>
                        {minutes} 分钟
                      </option>
                    ))}
                    <option value="custom">自定义</option>
                  </select>
                </label>
                {recordDurationMode === "custom" ? (
                  <label>
                    自定义分钟数
                    <input
                      aria-label="自定义记录分钟数"
                      type="number"
                      min={1}
                      value={recordDurationMinutes}
                      onChange={(event) => setRecordDurationMinutes(Number(event.target.value))}
                    />
                  </label>
                ) : null}
                <div className="recording-namespace-tree">
                  <div className="recording-tree-header">
                    <strong>选择名称空间</strong>
                    <span>{selectedRecordingNamespaces.length} / {recordingNamespaceNames.length}</span>
                  </div>
                  <div className="recording-tree-list">
                    <details open>
                      <summary>名称空间</summary>
                      <div className="recording-tree-children">
                        {recordingNamespaceNames.map((item) => (
                          <label key={item}>
                            <input
                              aria-label={`记录名称空间 ${item}`}
                              type="checkbox"
                              checked={selectedRecordingNamespaces.includes(item)}
                              onChange={() => toggleRecordingNamespace(item)}
                            />
                            {item}
                          </label>
                        ))}
                      </div>
                    </details>
                  </div>
                  {namespaceLoading ? <span className="inline-note">名称空间发现中...</span> : null}
                </div>
                <label className="recording-note-field">
                  备注
                  <textarea
                    aria-label="记录备注"
                    value={recordNote}
                    onChange={(event) => setRecordNote(event.target.value)}
                    placeholder="可填写复现步骤、业务场景或工单号"
                  />
                </label>
              </div>
              <div className="button-row">
                <button type="submit" className="button-success" disabled={recordingBusy}>
                  {recordingBusy ? "开始中..." : "确认开始"}
                </button>
                <button type="button" className="text-button mini-button" onClick={() => setRecordPanelOpen(false)} disabled={recordingBusy}>
                  取消
                </button>
              </div>
            </form>
          ) : null}
          {runningRecordings.length > 0 ? (
            <div className="running-recording-panel">
              <div className="section-header">
                <div>
                  <h4>进行中的日志记录</h4>
                  <span className="section-tip">离开页面后再次回来，会按当前名称空间重新加载。</span>
                </div>
              </div>
              <div className="running-recording-list">
                {runningRecordings.map((recording) => {
                  const stopping = stoppingRecordingIds.includes(recording.id);
                  return (
                    <article key={recording.id} className="running-recording-item">
                      <div>
                        <strong>{recording.name}</strong>
                        <div className="diagnosis-inline-metrics">
                          <span>名称空间：{recording.namespace}</span>
                          {displayRecordingNamespaces(recording).length > 1 ? <span>包含：{displayRecordingNamespaces(recording).join("、")}</span> : null}
                          <span>开始：{formatRecordingTime(recording.started_at)}</span>
                          <span>计划结束：{formatRecordingTime(recording.planned_end_at)}</span>
                        </div>
                      </div>
                      <button
                        type="button"
                        className="mini-button button-danger"
                        onClick={() => void handleStopRecording(recording)}
                        disabled={stopping}
                      >
                        {stopping ? "结束中..." : "结束记录"}
                      </button>
                    </article>
                  );
                })}
              </div>
            </div>
          ) : null}
          {endedRecordings.length > 0 ? (
            <div className="recording-history-panel">
              <div className="section-header">
                <div>
                  <h4>最近结束的日志记录</h4>
                  <span className="section-tip">点击查看日志可进入记录详情和搜索。</span>
                </div>
              </div>
              <div className="running-recording-list">
                {endedRecordings.map((recording) => (
                  <article key={recording.id} className="running-recording-item">
                    <div>
                      <strong>{recording.name}</strong>
                      <div className="diagnosis-inline-metrics">
                        <span>状态：{recording.status === "failed" ? "失败" : "已结束"}</span>
                        {recording.error_message ? <span>原因：{recording.error_message}</span> : null}
                        {displayRecordingNamespaces(recording).length > 1 ? <span>包含：{displayRecordingNamespaces(recording).join("、")}</span> : <span>名称空间：{recording.namespace}</span>}
                        <span>开始：{formatRecordingTime(recording.started_at)}</span>
                        <span>结束：{formatRecordingTime(recording.ended_at)}</span>
                        <span>日志行：{recording.folded_line_count} / {recording.raw_line_count}</span>
                      </div>
                    </div>
                    <a className="mini-button text-button" href={`/log-recordings?recordingId=${recording.id}`}>
                      查看日志
                    </a>
                  </article>
                ))}
              </div>
            </div>
          ) : null}
          {recordingMessage ? <p className="inline-note">{recordingMessage}</p> : null}
          {recordingError ? <p className="inline-note">记录日志失败：{recordingError}</p> : null}
          {namespaceLoading ? <p className="inline-note">名称空间发现中...</p> : null}
          {logLimitError ? <p className="inline-note">日志采集上限读取失败：{logLimitError}。范围日志巡检已安全阻断。</p> : null}
          {namespaceError ? <p>名称空间读取失败：{namespaceError}</p> : null}
          {scopeMode === "single" && podOptionsError ? <p>Pod 下拉加载失败：{podOptionsError}</p> : null}
        </div>
        <div className="hero-metric-stack">
          <div className="hero-metric hero-metric-compact">
            <span>已发现名称空间</span>
            <strong>{namespaceDiscovery?.namespaces.length ?? 0}</strong>
          </div>
        </div>
      </section>

      <section className="panel panel-muted">
        <div className="section-header">
          <div>
            <h3>次级操作</h3>
          </div>
        </div>
        <div className="secondary-action-row">
          <button type="button" className="text-button mini-button" onClick={openCreateSaveModal}>
            保存巡检点
          </button>
          <button type="button" className="text-button mini-button" onClick={() => setSavedTargetsOpen((current) => !current)}>
            {savedTargetsOpen ? "收起巡检点" : "巡检点"}
          </button>
          <button type="button" className="mini-button button-success" onClick={() => setModalType("import")}>
            导入
          </button>
          <button type="button" className="mini-button button-success" onClick={() => void handleOpenExportModal()}>
            导出
          </button>
        </div>
        {saveMessage ? <p className="inline-note">{saveMessage}</p> : null}
        {targetsError ? <p>保存对象失败：{targetsError}</p> : null}
        {savedTargetsOpen ? (
          <section className="saved-target-panel">
            <div className="section-header">
              <h4>巡检点</h4>
              <span className="section-tip">只保存 Label Selector 筛选范围</span>
            </div>
            {targetsLoading ? <p>加载已保存对象中...</p> : null}
            {!targetsLoading && inspectionPoints.length === 0 ? <p>暂无巡检点，选择 Label Selector 后可保存。</p> : null}
            {inspectionPoints.length > 0 ? (
              <div className="table-scroll-shell">
                <table className="compact-table">
                  <thead>
                    <tr>
                      <th>名称</th>
                      <th>名称空间</th>
                      <th>范围</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {inspectionPoints.map((target) => (
                      <tr key={target.id}>
                        <td>{target.name}</td>
                        <td>{target.namespace}</td>
                        <td className="ellipsis-cell" title={formatSavedTargetScope(target)}>
                          {formatSavedTargetScope(target)}
                        </td>
                        <td>
                          <div className="toolbar-row">
                            <button type="button" className="mini-button" onClick={() => applySavedTarget(target)} disabled={podInspection.loading || namespaceInspection.loading}>
                              巡检
                            </button>
                            <button type="button" className="mini-button" onClick={() => startEditingTarget(target)} disabled={targetSaving}>
                              编辑
                            </button>
                            <ConfirmDeleteButton itemName={`巡检点 ${target.name}`} onConfirm={() => handleDeleteTarget(target)} disabled={targetSaving}>删除</ConfirmDeleteButton>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </section>
        ) : null}
      </section>

      {podInspection.error ? <p>巡检失败：{podInspection.error}</p> : null}
      {namespaceInspection.error ? <p>巡检失败：{namespaceInspection.error}</p> : null}
      {ignoreMessage ? <p className="inline-note">{ignoreMessage}</p> : null}

      {inspectedLogPods.length > 0 ? (
        <section className="panel">
          <div className="section-header">
            <h3>日志巡检结果</h3>
            <StatusBadge status={activeLogHitCount > 0 ? "warning" : "healthy"} />
          </div>
          <p>
            已检查 {inspectedLogPods.length} 个 Pod，发现 {activeLogHitCount} 个日志命中。
            {activeLogHitCount === 0 ? " 未命中日志关键字；这不代表 Pod 或服务状态正常。" : ""}
          </p>
          {scopeMode !== "single" && namespaceInspection.data?.log_collection ? (
            <p className="inline-note">
              日志时间范围：{activeLogTimeRangeText ?? "服务端未返回"}；
              已读取 {namespaceInspection.data.log_collection.pods_read} / {namespaceInspection.data.log_collection.pod_count} 个 Pod；
              {namespaceInspection.data.log_collection.truncated ? "日志已截断。" : "未发生截断。"}
              {namespaceInspection.data.log_collection.time_range?.approximate ? " 时间范围为近似过滤。" : ""}
              {namespaceInspection.data.log_collection.time_range?.end_time_filter_precise === false ? " 结束时间无法精确过滤。" : ""}
            </p>
          ) : null}
        </section>
      ) : null}

      {scopeMode === "single" && podInspection.data ? (
        <>
          {currentPod ? (
            <div className="inspection-layout">
              <div className="panel">
                <div className="section-header">
                  <h3>单 Pod 日志</h3>
                  <StatusBadge status={getPodResultStatus(currentPod)} />
                </div>
                <KeyValueList
                  items={[
                    { label: "Pod", value: currentPod.name },
                    { label: "日志命中", value: String(currentLogHits.length) },
                    ...resourceUsageItems(currentPod.resource_usage),
                  ]}
                />
              </div>
              <div className="panel">
                <div className="section-header">
                  <h3>日志详情</h3>
                </div>
                <article className="card">
                  <strong>{currentLogHits.length > 0 ? "日志命中" : "原始日志摘要"}</strong>
                  {currentLogHits.length > 0 ? (
                    <div className="log-hit-list">
                      {currentLogHits.map((hit) => {
                        const hitKey = `${currentPod.name}:${hit.keyword}:${hit.matched_text}`;
                        const ignoring = ignoringLogKeys.includes(hitKey);
                        return (
                          <article key={hitKey} className="log-hit-card">
                            <div className="card-title">
                              <strong>{hit.keyword}</strong>
                              <StatusBadge status={hit.severity} />
                            </div>
                            <div className="diagnosis-inline-metrics">
                              <span>Pod：{currentPod.name}</span>
                              <span>容器：{hit.container_name ?? "服务端未返回"}</span>
                              <span>关键字：{hit.keyword}</span>
                              <span>时间：{logHitTime(hit)}</span>
                            </div>
                            <span className="inline-note">命中上下文（不是完整日志）</span>
                            {isLogContextTruncated(hit) ? <span className="inline-note">原始日志已截断</span> : null}
                            <pre className="log-block code-block-scroll terminal-log-block">{renderHighlightedLog(logHitContext(hit), hit.keyword)}</pre>
                            <div className="log-hit-actions">
                              <button type="button" onClick={() => openIgnoreLogHit(hit)} disabled={ignoring}>
                                {ignoring ? "处理中..." : "忽略此报错"}
                              </button>
                            </div>
                          </article>
                        );
                      })}
                    </div>
                  ) : (
                    <pre className="log-block code-block-scroll">{currentPod.log_summary ?? "无日志摘要"}</pre>
                  )}
                </article>
              </div>
            </div>
          ) : null}
        </>
      ) : null}

      {scopeMode !== "single" && namespaceInspection.data ? (
        <>
          <div className="inspection-layout">
            <div className="panel">
              <div className="section-header">
                <h3>{listTitle}</h3>
              </div>
              <div className="pod-list pod-list-scroll">
                {sortedRangePods.map((pod) => {
                  const active = selectedRangePod?.name === pod.name;
                  return (
                    <button
                      key={pod.name}
                      type="button"
                      className={`pod-list-item${active ? " pod-list-item-active" : ""}`}
                      onClick={() => setSelectedRangePodName(pod.name)}
                    >
                      <div className="card-title">
                        <strong title={pod.name}>{pod.name}</strong>
                        <StatusBadge status={getPodResultStatus(pod)} />
                      </div>
                      <small title={getPodResultSummary(pod)}>{getPodResultSummary(pod)}</small>
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="panel">
              <div className="section-header">
                <h3>日志详情</h3>
                {currentPod ? <StatusBadge status={getPodResultStatus(currentPod)} /> : null}
              </div>
              {currentPod ? (
                <div className="page-section">
                  <KeyValueList
                    items={[
                      { label: "Pod", value: currentPod.name },
                      { label: "日志命中", value: String(currentLogHits.length) },
                      ...resourceUsageItems(currentPod.resource_usage),
                    ]}
                  />
                  <article className="card">
                    <strong>{currentLogHits.length > 0 ? "日志命中" : "原始日志摘要"}</strong>
                    {currentLogHits.length > 0 ? (
                      <div className="log-hit-list">
                        {currentLogHits.map((hit) => {
                          const hitKey = `${currentPod.name}:${hit.keyword}:${hit.matched_text}`;
                          const ignoring = ignoringLogKeys.includes(hitKey);
                          return (
                            <article key={hitKey} className="log-hit-card">
                              <div className="card-title">
                                <strong>{hit.keyword}</strong>
                                <StatusBadge status={hit.severity} />
                              </div>
                              <div className="diagnosis-inline-metrics">
                                <span>Pod：{currentPod.name}</span>
                                <span>容器：{hit.container_name ?? "服务端未返回"}</span>
                                <span>关键字：{hit.keyword}</span>
                                <span>时间：{logHitTime(hit)}</span>
                              </div>
                              <span className="inline-note">命中上下文（不是完整日志）</span>
                              {isLogContextTruncated(hit) ? <span className="inline-note">原始日志已截断</span> : null}
                              <pre className="log-block code-block-scroll terminal-log-block">{renderHighlightedLog(logHitContext(hit), hit.keyword)}</pre>
                              <div className="log-hit-actions">
                                <button type="button" onClick={() => openIgnoreLogHit(hit)} disabled={ignoring}>
                                  {ignoring ? "处理中..." : "忽略此报错"}
                                </button>
                              </div>
                            </article>
                          );
                        })}
                      </div>
                    ) : (
                      <pre className="log-block code-block-scroll">{currentPod.log_summary ?? "无日志摘要"}</pre>
                    )}
                  </article>
                </div>
              ) : (
                <p>暂无 Pod 证据</p>
              )}
            </div>
          </div>
        </>
      ) : null}

      {modalType ? (
        <div className="modal-backdrop" role="presentation" onMouseDown={modalType === "ignore" ? closeIgnoreModal : () => setModalType(null)}>
          <section
            className="modal-card modal-card-polished"
            role="dialog"
            aria-modal="true"
            aria-label={modalType === "save" ? "保存巡检点" : modalType === "import" ? "导入巡检点" : modalType === "export" ? "导出巡检点" : "忽略此报错"}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="section-header">
              <div>
                <h3>{modalType === "save" ? (editingTargetId !== null ? "编辑巡检点" : "保存巡检点") : modalType === "import" ? "导入巡检点" : modalType === "export" ? "导出巡检点" : "忽略此报错"}</h3>
                <p className="inline-note">
                  {modalType === "save"
                    ? "把当前 Label Selector 筛选范围保存为巡检点。"
                    : modalType === "import"
                      ? "只导入 Label Selector 巡检点，其他类型会自动过滤。"
                      : modalType === "export"
                        ? "导出后可复制到其他环境导入。"
                        : "确认白名单字段和生效 Label，后续相同范围的命中会自动忽略。"}
                </p>
              </div>
              <button type="button" className="modal-secondary-button" onClick={modalType === "ignore" ? closeIgnoreModal : () => setModalType(null)}>关闭</button>
            </div>

            {modalType === "save" ? (
              <>
                <p className="inline-note">当前将保存：{currentScopeText}</p>
                <label className="modal-save-field">
                  巡检点名称
                  <input
                    className="modal-save-input"
                    aria-label="巡检点名称"
                    value={targetName}
                    onChange={(event) => setTargetName(event.target.value)}
                    placeholder={defaultInspectionPointName || "例如：platform / app=kong-service-kong"}
                  />
                </label>
                <div className="button-row modal-action-row">
                  <button className="modal-primary-button" type="button" onClick={() => void handleSaveCurrentTarget()} disabled={targetSaving || !labelSelector.trim()}>
                    {targetSaving ? (editingTargetId !== null ? "更新中..." : "保存中...") : editingTargetId !== null ? "更新巡检点" : "保存巡检点"}
                  </button>
                  <button className="modal-secondary-button" type="button" onClick={() => setModalType(null)}>取消</button>
                </div>
              </>
            ) : null}

            {modalType === "import" ? (
              <>
                <label>
                  导入内容
                  <textarea
                    aria-label="导入内容"
                    className="log-block code-block-scroll modal-code-input"
                    value={importContent}
                    onChange={(event) => setImportContent(event.target.value)}
                    rows={10}
                  />
                </label>
                <div className="button-row modal-action-row">
                  <button className="modal-primary-button" type="button" onClick={() => void handleImportTargets()} disabled={targetSaving || importContent.trim().length === 0}>
                    导入巡检点
                  </button>
                  <button className="modal-secondary-button" type="button" onClick={() => setModalType(null)}>取消</button>
                </div>
              </>
            ) : null}

            {modalType === "export" ? (
              <>
                <label>
                  导出内容
                  <textarea aria-label="导出内容" className="log-block code-block-scroll modal-code-input" value={exportContent} readOnly rows={10} />
                </label>
                {copyMessage ? <p className="inline-note">{copyMessage}</p> : null}
                <div className="button-row modal-action-row-left">
                  <button className="modal-primary-button" type="button" onClick={() => void handleCopyExport()} disabled={!exportContent || exportContent === "导出失败"}>
                    复制
                  </button>
                </div>
              </>
            ) : null}

            {modalType === "ignore" && ignoreDraft ? (
              <>
                <div className="entry-form-grid">
                  <label className="modal-form-field">
                    名称空间
                    <input className="template-input" aria-label="白名单名称空间" value={ignoreDraft.namespace} readOnly />
                  </label>
                  <label className="modal-form-field">
                    Label Selector
                    <select
                      className="template-input"
                      aria-label="白名单 Label Selector 候选"
                      value={ignoreDraft.labelSelector}
                      onChange={(event) => setIgnoreDraft((current) => current ? { ...current, labelSelector: event.target.value } : current)}
                    >
                      {labelSelectorOptionsForPod(ignoreDraft.pod, ignoreDraft.labelSelector).length === 0 ? <option value="">未发现可用 Label</option> : null}
                      {labelSelectorOptionsForPod(ignoreDraft.pod, ignoreDraft.labelSelector).map((option) => (
                        <option key={option} value={option}>{option}</option>
                      ))}
                    </select>
                  </label>
                  <label className="modal-form-field">
                    手动 Label Selector
                    <input
                      className="template-input"
                      aria-label="手动白名单 Label Selector"
                      value={ignoreDraft.labelSelector}
                      onChange={(event) => setIgnoreDraft((current) => current ? { ...current, labelSelector: event.target.value } : current)}
                      placeholder="例如：app=worker"
                    />
                  </label>
                  <label className="modal-form-field">
                    Pod
                    <input className="template-input" aria-label="白名单来源 Pod" value={ignoreDraft.pod.name} readOnly />
                  </label>
                  <label className="modal-form-field" style={{ gridColumn: "1 / -1" }}>
                    白名单字段
                    <textarea
                      className="template-input template-code-textarea"
                      aria-label="白名单字段"
                      value={ignoreDraft.keyword}
                      onChange={(event) => setIgnoreDraft((current) => current ? { ...current, keyword: event.target.value } : current)}
                      rows={4}
                    />
                  </label>
                  <label className="modal-form-field" style={{ gridColumn: "1 / -1" }}>
                    备注
                    <input
                      className="template-input"
                      aria-label="白名单备注"
                      value={ignoreDraft.note}
                      onChange={(event) => setIgnoreDraft((current) => current ? { ...current, note: event.target.value } : current)}
                      placeholder="例如：已确认是启动预热噪音"
                    />
                  </label>
                </div>
                <div className="button-row modal-action-row">
                  <button
                    className="modal-primary-button"
                    type="button"
                    onClick={() => void handleConfirmIgnoreLogHit()}
                    disabled={ignoringLogKeys.includes(`${ignoreDraft.pod.name}:${ignoreDraft.hit.keyword}:${ignoreDraft.hit.matched_text}`) || !ignoreDraft.namespace.trim() || !ignoreDraft.labelSelector.trim() || !ignoreDraft.keyword.trim()}
                  >
                    {ignoringLogKeys.includes(`${ignoreDraft.pod.name}:${ignoreDraft.hit.keyword}:${ignoreDraft.hit.matched_text}`) ? "保存中..." : "加入白名单"}
                  </button>
                  <button className="modal-secondary-button" type="button" onClick={closeIgnoreModal}>取消</button>
                </div>
              </>
            ) : null}
          </section>
        </div>
      ) : null}

      {rangeConfirmation ? (
        <div className="modal-backdrop" role="presentation">
          <section
            className="modal-card modal-card-polished"
            role="dialog"
            aria-modal="true"
            aria-labelledby="large-range-title"
          >
            <div className="section-header">
              <div>
                <p className="eyebrow">日志读取保护</p>
                <h3 id="large-range-title">无法执行大范围日志巡检</h3>
              </div>
            </div>
            {rangeConfirmation.podCount === null ? (
              <p>当前无法确认该范围的 Pod 数量，为避免读取过多日志，本次巡检已阻断。</p>
            ) : maxLogPods === null ? (
              <p>当前无法读取日志采集上限，为避免读取过多日志，本次巡检已阻断。</p>
            ) : (
              <p>当前范围发现 {rangeConfirmation.podCount} 个 Pod，超过当前日志采集上限 {maxLogPods} 个，本次巡检已阻断。</p>
            )}
            <p className="inline-note">
              {rangeConfirmation.podCount === null
                ? "请先刷新发现数据、选择可确认 Pod 数量的范围，或使用 Label Selector 缩小范围后重试。"
                : maxLogPods === null
                  ? "请确认系统设置可用并重新打开页面后重试。"
                  : `请使用 Label Selector 缩小到 ${maxLogPods} 个及以下 Pod 后重试。`}
            </p>
            <div className="button-row modal-action-row">
              <button type="button" className="modal-primary-button" onClick={() => setRangeConfirmation(null)}>
                返回缩小范围
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}
