import { useEffect, useMemo, useState, type ReactNode } from "react";

import { ignoreWhitelistLogHit, runNamespaceInspection } from "../api/client";
import type { InspectedPod, KeywordHit, SavedInspectionTarget } from "../api/types";
import { KeyValueList } from "../components/KeyValueList";
import { StatusBadge } from "../components/StatusBadge";
import { useDiscoverNamespaceLabels } from "../features/inspections/useDiscoverNamespaceLabels";
import { useDiscoverNamespaces } from "../features/inspections/useDiscoverNamespaces";
import { isHealthyPod } from "../features/inspections/podHealth";
import { useRunNamespaceInspection } from "../features/inspections/useRunNamespaceInspection";
import { useRunPodInspection } from "../features/inspections/useRunPodInspection";
import { useSavedInspectionTargets } from "../features/inspections/useSavedInspectionTargets";
import { findLogKeywordMatchRanges, normalizeTerminalLogText } from "../features/logs/logText";

type PodScopeMode = "all" | "label" | "single";
type PodModalType = "save" | "import" | "export" | null;

function sortPods(pods: InspectedPod[]) {
  return [...pods].sort((left, right) => {
    const leftRank = isHealthyPod(left) ? 1 : 0;
    const rightRank = isHealthyPod(right) ? 1 : 0;

    if (leftRank !== rightRank) {
      return leftRank - rightRank;
    }

    return right.restarts - left.restarts;
  });
}

function logHitContext(hit: KeywordHit) {
  return hit.context_text?.trim() || hit.matched_text;
}

function normalizeLogText(value: string) {
  return normalizeTerminalLogText(value);
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
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
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

  const filteredNamespaces = useMemo(() => {
    const keyword = namespaceSearch.trim().toLowerCase();
    const items = namespaceDiscovery?.namespaces ?? [];
    if (!keyword) {
      return items;
    }
    return items.filter((item) => item.name.toLowerCase().includes(keyword));
  }, [namespaceDiscovery, namespaceSearch]);

  const sortedRangePods = namespaceInspection.data ? sortPods(namespaceInspection.data.pods) : [];
  const selectedRangePod =
    sortedRangePods.find((pod) => pod.name === selectedRangePodName) ??
    sortedRangePods[0] ??
    null;
  const getActiveLogHits = (pod: InspectedPod) =>
    pod.log_hits.filter((hit) => !hit.whitelisted && !ignoredLogKeys.includes(`${pod.name}:${hit.keyword}:${hit.matched_text}`));
  const currentPod = scopeMode === "single" ? podInspection.data?.pod ?? null : selectedRangePod;
  const currentLogHits = currentPod ? getActiveLogHits(currentPod) : [];
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
  const getPodResultStatus = (pod: InspectedPod) => (!isHealthyPod(pod) || getActiveLogHits(pod).length > 0 ? "error" : "healthy");
  const getPodResultSummary = (pod: InspectedPod) => {
    const activeHits = getActiveLogHits(pod);
    if (activeHits.length > 0) {
      const keywords = Array.from(new Set(activeHits.map((hit) => hit.keyword))).slice(0, 3);
      return `命中关键字：${keywords.join("、")}`;
    }
    return isHealthyPod(pod) ? "正常" : "异常";
  };

  useEffect(() => {
    if (scopeMode !== "single" || !namespace.trim() || podOptionsNamespace === namespace.trim()) {
      return;
    }

    let alive = true;
    setPodOptionsLoading(true);
    setPodOptionsError(null);
    void runNamespaceInspection(namespace.trim(), null)
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

  useEffect(() => {
    if (!namespaceInspection.data) {
      return;
    }
    setPodOptions(namespaceInspection.data.pods.map((pod) => pod.name));
    setPodOptionsNamespace(namespaceInspection.data.namespace);
  }, [namespaceInspection.data]);

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

    await namespaceInspection.submit(normalizedNamespace, scopeMode === "label" ? labelSelector.trim() || "" : "");
    resetAfterInspection();
  }

  async function handleIgnoreLogHit(hit: KeywordHit) {
    if (!currentPod) {
      return;
    }

    const hitKey = `${currentPod.name}:${hit.keyword}:${hit.matched_text}`;
    setIgnoringLogKeys((current) => [...current, hitKey]);
    setIgnoreMessage(null);

    try {
      await ignoreWhitelistLogHit({
        namespace: scopeMode === "single" ? podInspection.data?.namespace ?? namespace : namespaceInspection.data?.namespace ?? namespace,
        label_selector:
          scopeMode === "label"
            ? namespaceInspection.data?.inspection_target.label_selector ?? (labelSelector || null)
            : null,
        pod_name_pattern: null,
        container_name: hit.container_name ?? null,
        keyword: normalizeLogText(hit.matched_text),
        note: scopeMode === "single" ? "从 Pod 巡检结果忽略" : "从 Pod 范围巡检结果忽略",
      });
      setIgnoredLogKeys((current) => [...current, hitKey]);
      setIgnoreMessage(scopeMode === "single" ? "已加入白名单，后续 Pod 巡检会自动忽略该命中" : "已加入白名单，后续范围巡检会自动忽略该命中");
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
      void namespaceInspection.submit(target.namespace, target.label_selector).then(() => resetAfterInspection());
      return;
    }

    setScopeMode("all");
    void namespaceInspection.submit(target.namespace, "").then(() => resetAfterInspection());
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

  const currentModeLabel = scopeMode === "all" ? "全部 Pod" : scopeMode === "label" ? "Label Selector" : "单个 Pod";
  const currentRunLabel = scopeMode === "single" ? "巡检单个 Pod" : "巡检日志范围";
  const listTitle = scopeMode === "single" ? "最近使用范围" : "范围内 Pod 列表";

  return (
    <section className="page-section">
      <section className="panel workbench-hero">
        <div className="workbench-copy">
          <div className="section-header">
            <div>
              <h3>选择范围</h3>
            </div>
          </div>
          <div className="entry-form-grid entry-form-grid-compact">
            <label className="inline-search">
              筛选名称空间
              <input
                aria-label="筛选名称空间"
                value={namespaceSearch}
                onChange={(event) => setNamespaceSearch(event.target.value)}
                placeholder="例如：demo、prod、kube-system"
              />
            </label>
            <label>
              名称空间
              <select
                aria-label="名称空间"
                value={namespace}
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
            <label>
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

          <div className="button-row">
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
          </div>
          {namespaceLoading ? <p className="inline-note">名称空间发现中...</p> : null}
          {namespaceError ? <p>名称空间读取失败：{namespaceError}</p> : null}
          {scopeMode === "single" && podOptionsError ? <p>Pod 下拉加载失败：{podOptionsError}</p> : null}
        </div>
        <div className="hero-metric-stack">
          <div className="hero-metric hero-metric-compact">
            <span>当前模式</span>
            <strong>{currentModeLabel}</strong>
          </div>
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
          <button type="button" className="text-button mini-button" onClick={() => setModalType("import")}>
            导入
          </button>
          <button type="button" className="text-button mini-button" onClick={() => void handleOpenExportModal()}>
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
                            <button type="button" className="mini-button" onClick={() => void handleDeleteTarget(target)} disabled={targetSaving}>
                              删除
                            </button>
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

      {scopeMode === "single" && podInspection.data ? (
        <>
          {currentPod ? (
            <div className="inspection-layout">
              <div className="panel">
                <div className="section-header">
                  <h3>单 Pod 结果</h3>
                  <StatusBadge status={getPodResultStatus(currentPod)} />
                </div>
                <KeyValueList
                  items={[
                    { label: "Pod", value: currentPod.name },
                    { label: "状态", value: currentPod.status },
                    {
                      label: "资源使用",
                      value: `CPU ${currentPod.resource_usage.cpu ?? "n/a"} / MEM ${currentPod.resource_usage.memory ?? "n/a"}`,
                    },
                  ]}
                />
                <article className="card">
                  <strong>Describe 摘要</strong>
                  <pre className="log-block code-block-scroll">{currentPod.describe_summary}</pre>
                </article>
              </div>
              <div className="panel">
                <div className="section-header">
                  <h3>证据详情</h3>
                </div>
                <article className="card">
                  <strong>事件</strong>
                  {currentPod.events.length > 0 ? (
                    <pre className="log-block code-block-scroll">{currentPod.events.join("\n")}</pre>
                  ) : (
                    <p>无事件</p>
                  )}
                </article>
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
                            <span className="inline-note">原始日志</span>
                            <pre className="log-block code-block-scroll terminal-log-block">{renderHighlightedLog(logHitContext(hit), hit.keyword)}</pre>
                            <div className="log-hit-actions">
                              <button type="button" onClick={() => void handleIgnoreLogHit(hit)} disabled={ignoring}>
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
                <span className="section-tip">范围巡检结果不会伪装成单 Pod</span>
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
                      <p>重启次数：{pod.restarts}</p>
                      <small title={getPodResultSummary(pod)}>{getPodResultSummary(pod)}</small>
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="panel">
              <div className="section-header">
                <h3>证据详情</h3>
                {currentPod ? <StatusBadge status={getPodResultStatus(currentPod)} /> : null}
              </div>
              {currentPod ? (
                <div className="page-section">
                  <KeyValueList
                    items={[
                      { label: "Pod", value: currentPod.name },
                      { label: "状态", value: currentPod.status },
                      { label: "重启次数", value: String(currentPod.restarts) },
                      {
                        label: "资源使用",
                        value: `CPU ${currentPod.resource_usage.cpu ?? "n/a"} / MEM ${currentPod.resource_usage.memory ?? "n/a"}`,
                      },
                    ]}
                  />
                  <article className="card">
                    <strong>Describe 摘要</strong>
                    <pre className="log-block code-block-scroll">{currentPod.describe_summary}</pre>
                  </article>
                  <article className="card">
                    <strong>事件</strong>
                    {currentPod.events.length > 0 ? (
                      <pre className="log-block code-block-scroll">{currentPod.events.join("\n")}</pre>
                    ) : (
                      <p>无事件</p>
                    )}
                  </article>
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
                              <span className="inline-note">原始日志</span>
                              <pre className="log-block code-block-scroll terminal-log-block">{renderHighlightedLog(logHitContext(hit), hit.keyword)}</pre>
                              <div className="log-hit-actions">
                                <button type="button" onClick={() => void handleIgnoreLogHit(hit)} disabled={ignoring}>
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
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setModalType(null)}>
          <section
            className="modal-card modal-card-polished"
            role="dialog"
            aria-modal="true"
            aria-label={modalType === "save" ? "保存巡检点" : modalType === "import" ? "导入巡检点" : "导出巡检点"}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="section-header">
              <div>
                <h3>{modalType === "save" ? (editingTargetId !== null ? "编辑巡检点" : "保存巡检点") : modalType === "import" ? "导入巡检点" : "导出巡检点"}</h3>
                <p className="inline-note">
                  {modalType === "save"
                    ? "把当前 Label Selector 筛选范围保存为巡检点。"
                    : modalType === "import"
                      ? "只导入 Label Selector 巡检点，其他类型会自动过滤。"
                      : "导出后可复制到其他环境导入。"}
                </p>
              </div>
              <button type="button" onClick={() => setModalType(null)}>关闭</button>
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
                <div className="button-row">
                  <button type="button" onClick={() => void handleCopyExport()} disabled={!exportContent || exportContent === "导出失败"}>
                    复制
                  </button>
                  <button type="button" onClick={() => setModalType(null)}>关闭</button>
                </div>
              </>
            ) : null}
          </section>
        </div>
      ) : null}
    </section>
  );
}
