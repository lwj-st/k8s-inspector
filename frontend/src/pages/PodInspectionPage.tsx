import { useEffect, useMemo, useState } from "react";

import { ignoreWhitelistLogHit, runNamespaceInspection } from "../api/client";
import type { InspectedPod, KeywordHit, SavedInspectionTarget } from "../api/types";
import { KeyValueList } from "../components/KeyValueList";
import { StatusBadge } from "../components/StatusBadge";
import { useDiscoverNamespaces } from "../features/inspections/useDiscoverNamespaces";
import { isHealthyPod } from "../features/inspections/podHealth";
import { useRunNamespaceInspection } from "../features/inspections/useRunNamespaceInspection";
import { useRunPodInspection } from "../features/inspections/useRunPodInspection";
import { useSavedInspectionTargets } from "../features/inspections/useSavedInspectionTargets";

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

export function PodInspectionPage() {
  const [namespaceSearch, setNamespaceSearch] = useState("");
  const [namespace, setNamespace] = useState("");
  const [scopeMode, setScopeMode] = useState<PodScopeMode>("single");
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
  const rangeAbnormalPods = sortedRangePods.filter((pod) => !isHealthyPod(pod));
  const rangeHealthyPods = sortedRangePods.filter(isHealthyPod);
  const currentPod = scopeMode === "single" ? podInspection.data?.pod ?? null : selectedRangePod;
  const currentLogHits = currentPod?.log_hits ?? [];
  const currentScopeText =
    !namespace.trim()
      ? "未选择名称空间"
      : scopeMode === "all"
        ? `${namespace.trim()} / 全部 Pod`
        : scopeMode === "label"
          ? `${namespace.trim()} / ${labelSelector.trim() || "未填写 Label Selector"}`
          : `${namespace.trim()} / ${podName.trim() || "未选择 Pod"}`;

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
        pod_name_pattern: currentPod.name,
        container_name: hit.container_name ?? null,
        keyword: hit.keyword,
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
    setEditingTargetId(null);
    setTargetName("");
    setModalType("save");
  }

  function startEditingTarget(target: SavedInspectionTarget) {
    setEditingTargetId(target.id);
    setTargetName(target.name);
    setNamespaceSearch(target.namespace);
    resetNamespaceContext(target.namespace);
    setLabelSelector(target.label_selector ?? "");
    if (target.pod_name && target.pod_name.trim()) {
      setScopeMode("single");
      setPodName(target.pod_name);
    } else if (target.label_selector) {
      setScopeMode("label");
      setPodName("");
    } else {
      setScopeMode("all");
      setPodName("");
    }
    setSavedTargetsOpen(true);
    setModalType("save");
  }

  async function handleSaveCurrentTarget() {
    const normalizedName = targetName.trim();
    const normalizedNamespace = namespace.trim();
    if (!normalizedName) {
      setSaveMessage("请先填写常用范围名称");
      return;
    }
    if (!normalizedNamespace) {
      setSaveMessage("请先选择名称空间");
      return;
    }
    if (scopeMode === "single" && !podName.trim()) {
      setSaveMessage("单个 Pod 巡检前，请先选择 Pod，再保存常用范围");
      return;
    }

    try {
      const payload = {
        name: normalizedName,
        namespace: normalizedNamespace,
        label_selector: scopeMode === "label" ? labelSelector.trim() || null : null,
        pod_name: scopeMode === "single" ? podName.trim() : "",
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
      setExportContent(JSON.stringify(items, null, 2));
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
      const created = await importTargets(parsed);
      if (created.length === 0) {
        setSaveMessage("导入内容不包含当前页面可导入的 Pod 巡检对象");
        return;
      }
      setSaveMessage(`已导入 ${created.length} 个 Pod 巡检对象`);
      setImportContent("");
      setSavedTargetsOpen(true);
      setModalType(null);
    } catch {
      setSaveMessage("导入失败，请检查 JSON 格式");
    }
  }

  const currentModeLabel = scopeMode === "all" ? "全部 Pod" : scopeMode === "label" ? "Label Selector" : "单个 Pod";

  return (
    <section className="page-section">
      <header className="section-header">
        <div>
          <p className="eyebrow">定点巡检</p>
          <h2>Pod 巡检</h2>
        </div>
        {currentPod ? <StatusBadge status={currentPod.status} /> : <StatusBadge status="info" />}
      </header>

      <section className="panel workbench-hero">
        <div className="workbench-copy">
          <div className="section-header">
            <div>
              <h3>选择范围</h3>
              <p className="inline-note">先选名称空间，再决定巡检全部 Pod、标签范围，还是单个 Pod。</p>
            </div>
          </div>
          <div className="entry-form-grid">
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
              巡检范围
              <select
                aria-label="巡检范围"
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
            <label>
              Label Selector
              <input
                aria-label="Label Selector"
                value={labelSelector}
                onChange={(event) => setLabelSelector(event.target.value)}
                placeholder="例如：app=demo-api"
              />
            </label>
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
              {podInspection.loading || namespaceInspection.loading ? "巡检中..." : scopeMode === "single" ? "巡检单个 Pod" : "巡检 Pod 范围"}
            </button>
          </div>
          <p className="inline-note">当前范围：{currentScopeText}</p>
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
            <p className="inline-note">保存、导入、导出和编辑常用范围都收在这里，不占主流程位置。</p>
          </div>
        </div>
        <div className="secondary-action-row">
          <button type="button" className="text-button" onClick={openCreateSaveModal}>
            保存当前范围
          </button>
          <button type="button" className="text-button" onClick={() => setSavedTargetsOpen((current) => !current)}>
            {savedTargetsOpen ? "收起常用范围" : "常用范围"}
          </button>
          <button type="button" className="text-button" onClick={() => setModalType("import")}>
            导入
          </button>
          <button type="button" className="text-button" onClick={() => void handleOpenExportModal()}>
            导出
          </button>
        </div>
        {saveMessage ? <p className="inline-note">{saveMessage}</p> : null}
        {targetsError ? <p>保存对象失败：{targetsError}</p> : null}
        {savedTargetsOpen ? (
          <section className="saved-target-panel">
            <div className="section-header">
              <h4>常用范围</h4>
              <span className="section-tip">Pod 巡检对象、标签范围和全部 Pod 范围都在这里复用</span>
            </div>
            {targetsLoading ? <p>加载已保存对象中...</p> : null}
            {!targetsLoading && targets.length === 0 ? <p>暂无保存对象，保存当前 Pod 巡检范围后可复用。</p> : null}
            <div className="quick-target-grid">
              {targets.map((target) => (
                <div key={target.id} className="quick-target-card">
                  <strong>{target.name}</strong>
                  <span>
                    {target.namespace}
                    {target.pod_name && target.pod_name.trim()
                      ? ` / ${target.pod_name}`
                      : target.label_selector
                        ? ` / ${target.label_selector}`
                        : " / 全部 Pod"}
                  </span>
                  <small>
                    {target.pod_name && target.pod_name.trim()
                      ? "单个 Pod"
                      : target.label_selector
                        ? "Label Selector"
                        : "全部 Pod"}
                  </small>
                  <div className="log-hit-actions">
                    <button type="button" onClick={() => applySavedTarget(target)} disabled={podInspection.loading || namespaceInspection.loading}>
                      使用 {target.name}
                    </button>
                    <button type="button" onClick={() => startEditingTarget(target)} disabled={targetSaving}>
                      编辑 {target.name}
                    </button>
                    <button type="button" onClick={() => void handleDeleteTarget(target)} disabled={targetSaving}>
                      删除 {target.name}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        ) : null}
      </section>

      {podInspection.error ? <p>巡检失败：{podInspection.error}</p> : null}
      {namespaceInspection.error ? <p>巡检失败：{namespaceInspection.error}</p> : null}
      {ignoreMessage ? <p className="inline-note">{ignoreMessage}</p> : null}

      {scopeMode === "single" && podInspection.data ? (
        <>
          <section className="panel">
            <div className="section-header">
              <div>
                <h3>最近一次巡检摘要</h3>
                <p className="inline-note">当前为单个 Pod 精确巡检，只展示这一条 Pod 的证据链。</p>
              </div>
              <StatusBadge status={podInspection.data.health_status} />
            </div>
            <KeyValueList
              items={[
                { label: "名称空间", value: podInspection.data.namespace },
                { label: "Pod", value: currentPod?.name ?? "--" },
                { label: "状态", value: currentPod?.status ?? "--" },
                { label: "重启次数", value: currentPod ? String(currentPod.restarts) : "--" },
              ]}
            />
          </section>
          {currentPod ? (
            <div className="inspection-layout">
              <div className="panel">
                <div className="section-header">
                  <h3>单 Pod 结果</h3>
                  <StatusBadge status={currentPod.status} />
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
                  <p>{currentPod.describe_summary}</p>
                </article>
              </div>
              <div className="panel">
                <div className="section-header">
                  <h3>证据详情</h3>
                  <span className="section-tip">白名单忽略入口保留在日志命中卡片中</span>
                </div>
                <article className="card">
                  <strong>事件</strong>
                  {currentPod.events.length > 0 ? (
                    <ul className="plain-list">
                      {currentPod.events.map((event) => (
                        <li key={event}>{event}</li>
                      ))}
                    </ul>
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
                        const ignored = hit.whitelisted || ignoredLogKeys.includes(hitKey);
                        const ignoring = ignoringLogKeys.includes(hitKey);
                        return (
                          <article key={hitKey} className={`log-hit-card${ignored ? " log-hit-card-muted" : ""}`}>
                            <div className="card-title">
                              <strong>{hit.keyword}</strong>
                              <StatusBadge status={ignored ? "disabled" : hit.severity} />
                            </div>
                            <pre className="log-block">{hit.matched_text}</pre>
                            <div className="log-hit-actions">
                              <button type="button" onClick={() => void handleIgnoreLogHit(hit)} disabled={ignored || ignoring}>
                                {hit.whitelisted ? "白名单已生效" : ignored ? "已忽略" : ignoring ? "处理中..." : "忽略此报错"}
                              </button>
                            </div>
                          </article>
                        );
                      })}
                    </div>
                  ) : (
                    <pre className="log-block">{currentPod.log_summary ?? "无日志摘要"}</pre>
                  )}
                </article>
              </div>
            </div>
          ) : null}
        </>
      ) : null}

      {scopeMode !== "single" && namespaceInspection.data ? (
        <>
          <section className="panel">
            <div className="section-header">
              <div>
                <h3>最近一次巡检摘要</h3>
                <p className="inline-note">当前是 Pod 范围巡检，Label Selector 命中多个 Pod 时会展示多个 Pod 结果。</p>
              </div>
              <StatusBadge status={namespaceInspection.data.health_status} />
            </div>
            <KeyValueList
              items={[
                { label: "名称空间", value: namespaceInspection.data.namespace },
                { label: "巡检范围", value: scopeMode === "label" ? namespaceInspection.data.inspection_target.label_selector ?? "Label Selector" : "全部 Pod" },
                { label: "异常 Pod", value: String(rangeAbnormalPods.length) },
                { label: "正常 / 已完成 Pod", value: String(rangeHealthyPods.length) },
              ]}
            />
          </section>
          <div className="inspection-layout">
            <div className="panel">
              <div className="section-header">
                <h3>Pod 列表</h3>
                <span className="section-tip">范围巡检结果不会伪装成单 Pod</span>
              </div>
              <div className="pod-list">
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
                        <strong>{pod.name}</strong>
                        <StatusBadge status={pod.status} />
                      </div>
                      <p>重启次数：{pod.restarts}</p>
                      <small>{isHealthyPod(pod) ? "状态正常 / 已完成" : "优先处理"}</small>
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="panel">
              <div className="section-header">
                <h3>证据详情</h3>
                {currentPod ? <StatusBadge status={currentPod.status} /> : null}
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
                    <p>{currentPod.describe_summary}</p>
                  </article>
                  <article className="card">
                    <strong>事件</strong>
                    {currentPod.events.length > 0 ? (
                      <ul className="plain-list">
                        {currentPod.events.map((event) => (
                          <li key={event}>{event}</li>
                        ))}
                      </ul>
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
                          const ignored = hit.whitelisted || ignoredLogKeys.includes(hitKey);
                          const ignoring = ignoringLogKeys.includes(hitKey);
                          return (
                            <article key={hitKey} className={`log-hit-card${ignored ? " log-hit-card-muted" : ""}`}>
                              <div className="card-title">
                                <strong>{hit.keyword}</strong>
                                <StatusBadge status={ignored ? "disabled" : hit.severity} />
                              </div>
                              <pre className="log-block">{hit.matched_text}</pre>
                              <div className="log-hit-actions">
                                <button type="button" onClick={() => void handleIgnoreLogHit(hit)} disabled={ignored || ignoring}>
                                  {hit.whitelisted ? "白名单已生效" : ignored ? "已忽略" : ignoring ? "处理中..." : "忽略此报错"}
                                </button>
                              </div>
                            </article>
                          );
                        })}
                      </div>
                    ) : (
                      <pre className="log-block">{currentPod.log_summary ?? "无日志摘要"}</pre>
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
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-label={modalType === "save" ? "保存当前范围" : modalType === "import" ? "导入巡检对象" : "导出巡检对象"}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="section-header">
              <div>
                <h3>{modalType === "save" ? (editingTargetId !== null ? "编辑常用范围" : "保存当前范围") : modalType === "import" ? "导入巡检对象" : "导出巡检对象"}</h3>
                <p className="inline-note">
                  {modalType === "save"
                    ? "把当前 Pod 巡检范围保存为可复用入口。"
                    : modalType === "import"
                      ? "只导入 Pod 巡检对象，其他类型会自动过滤。"
                      : "导出后可复制到其他环境导入。"}
                </p>
              </div>
              <button type="button" onClick={() => setModalType(null)}>关闭</button>
            </div>

            {modalType === "save" ? (
              <>
                <p className="inline-note">当前将保存：{currentScopeText}</p>
                <label>
                  常用范围名称
                  <input
                    aria-label="常用范围名称"
                    value={targetName}
                    onChange={(event) => setTargetName(event.target.value)}
                    placeholder="例如：demo API 单 Pod 排查"
                  />
                </label>
                <div className="button-row">
                  <button type="button" onClick={() => void handleSaveCurrentTarget()} disabled={targetSaving || targetName.trim().length === 0}>
                    {targetSaving ? (editingTargetId !== null ? "更新中..." : "保存中...") : editingTargetId !== null ? "更新当前对象" : "保存当前范围"}
                  </button>
                  <button type="button" onClick={() => setModalType(null)}>取消</button>
                </div>
              </>
            ) : null}

            {modalType === "import" ? (
              <>
                <label>
                  导入内容
                  <textarea
                    aria-label="导入内容"
                    value={importContent}
                    onChange={(event) => setImportContent(event.target.value)}
                    rows={10}
                  />
                </label>
                <div className="button-row">
                  <button type="button" onClick={() => void handleImportTargets()} disabled={targetSaving || importContent.trim().length === 0}>
                    导入巡检对象
                  </button>
                  <button type="button" onClick={() => setModalType(null)}>取消</button>
                </div>
              </>
            ) : null}

            {modalType === "export" ? (
              <>
                <label>
                  导出内容
                  <textarea aria-label="导出内容" value={exportContent} readOnly rows={10} />
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
