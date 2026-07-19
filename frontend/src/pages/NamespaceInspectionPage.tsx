import { useMemo, useState } from "react";

import { ignoreWhitelistLogHit } from "../api/client";
import type { InspectedPod, KeywordHit, SavedInspectionTarget } from "../api/types";
import { KeyValueList } from "../components/KeyValueList";
import { StatusBadge } from "../components/StatusBadge";
import { DiagnosisResultPanel } from "../features/diagnosis/DiagnosisResultPanel";
import { useRunDiagnosis } from "../features/diagnosis/useRunDiagnosis";
import { useDiscoverNamespaces } from "../features/inspections/useDiscoverNamespaces";
import { isHealthyPod } from "../features/inspections/podHealth";
import { useRunNamespaceInspection } from "../features/inspections/useRunNamespaceInspection";
import { useSavedInspectionTargets } from "../features/inspections/useSavedInspectionTargets";

type NamespaceModalType = "save" | "import" | "export" | null;

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

export function NamespaceInspectionPage() {
  const [namespaceSearch, setNamespaceSearch] = useState("");
  const [namespace, setNamespace] = useState("");
  const [manualNamespaceEnabled, setManualNamespaceEnabled] = useState(false);
  const [manualNamespace, setManualNamespace] = useState("");
  const [labelSelector, setLabelSelector] = useState("");
  const [targetName, setTargetName] = useState("");
  const [editingTargetId, setEditingTargetId] = useState<number | null>(null);
  const [exportContent, setExportContent] = useState("");
  const [importContent, setImportContent] = useState("");
  const [modalType, setModalType] = useState<NamespaceModalType>(null);
  const [savedTargetsOpen, setSavedTargetsOpen] = useState(false);
  const [selectedPodName, setSelectedPodName] = useState<string | null>(null);
  const [ignoredLogKeys, setIgnoredLogKeys] = useState<string[]>([]);
  const [ignoringLogKeys, setIgnoringLogKeys] = useState<string[]>([]);
  const [ignoreMessage, setIgnoreMessage] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const [diagnosisVisible, setDiagnosisVisible] = useState(false);
  const { data: namespaceDiscovery, loading: namespaceLoading, error: namespaceError } = useDiscoverNamespaces();
  const { data, loading, error, submit } = useRunNamespaceInspection();
  const diagnosis = useRunDiagnosis();
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
  } = useSavedInspectionTargets("namespace");

  const filteredNamespaces = useMemo(() => {
    const keyword = namespaceSearch.trim().toLowerCase();
    const items = namespaceDiscovery?.namespaces ?? [];
    if (!keyword) {
      return items;
    }
    return items.filter((item) => item.name.toLowerCase().includes(keyword));
  }, [namespaceDiscovery, namespaceSearch]);

  const sortedPods = data ? sortPods(data.pods) : [];
  const selectedPod =
    sortedPods.find((pod) => pod.name === selectedPodName) ??
    sortedPods[0] ??
    null;
  const abnormalPods = sortedPods.filter((pod) => !isHealthyPod(pod));
  const healthyPods = sortedPods.filter(isHealthyPod);
  const logHits = selectedPod?.log_hits ?? [];
  const selectedNamespace = manualNamespaceEnabled ? manualNamespace.trim() : namespace.trim();
  const currentSaveLabelSelector = labelSelector.trim() || data?.inspection_target.label_selector?.trim() || "";
  const currentSaveScopeText = selectedNamespace
    ? `${selectedNamespace}${currentSaveLabelSelector ? ` / ${currentSaveLabelSelector}` : " / 全名称空间"}`
    : "未选择名称空间";

  function resetAfterInspection() {
    setSelectedPodName(null);
    setIgnoredLogKeys([]);
    setIgnoringLogKeys([]);
    setIgnoreMessage(null);
    setDiagnosisVisible(false);
  }

  function applyQuickTarget(target: SavedInspectionTarget) {
    setManualNamespaceEnabled(false);
    setManualNamespace("");
    setNamespace(target.namespace);
    setNamespaceSearch(target.namespace);
    setLabelSelector(target.label_selector ?? "");
    setSavedTargetsOpen(false);
    void submit(target.namespace, target.label_selector ?? "").then(resetAfterInspection);
  }

  async function handleIgnoreLogHit(hit: KeywordHit) {
    if (!selectedPod) {
      return;
    }

    const hitKey = `${selectedPod.name}:${hit.keyword}:${hit.matched_text}`;
    setIgnoringLogKeys((current) => [...current, hitKey]);
    setIgnoreMessage(null);

    try {
      await ignoreWhitelistLogHit({
        namespace: data?.namespace ?? selectedNamespace,
        label_selector: data?.inspection_target.label_selector ?? (labelSelector || null),
        pod_name_pattern: selectedPod.name,
        container_name: hit.container_name ?? null,
        keyword: hit.keyword,
        note: "从巡检结果忽略",
      });
      setIgnoredLogKeys((current) => [...current, hitKey]);
      setIgnoreMessage("已加入白名单，后续巡检会自动忽略该命中");
    } catch (reason) {
      setIgnoreMessage(reason instanceof Error ? `加入白名单失败：${reason.message}` : "加入白名单失败");
    } finally {
      setIgnoringLogKeys((current) => current.filter((item) => item !== hitKey));
    }
  }

  async function handleRunInspection() {
    if (!selectedNamespace) {
      setSaveMessage("请先选择名称空间");
      return;
    }
    setSaveMessage(null);
    await submit(selectedNamespace, labelSelector.trim() || "");
    resetAfterInspection();
  }

  function openCreateSaveModal() {
    setEditingTargetId(null);
    setTargetName("");
    setModalType("save");
  }

  function startEditingTarget(target: SavedInspectionTarget) {
    setEditingTargetId(target.id);
    setTargetName(target.name);
    setManualNamespaceEnabled(false);
    setManualNamespace("");
    setNamespace(target.namespace);
    setNamespaceSearch(target.namespace);
    setLabelSelector(target.label_selector ?? "");
    setModalType("save");
    setSavedTargetsOpen(true);
    setSaveMessage(`正在编辑 ${target.name}`);
  }

  async function handleSaveCurrentTarget() {
    const normalizedName = targetName.trim();
    if (!normalizedName) {
      setSaveMessage("请先填写常用范围名称");
      return;
    }
    if (!selectedNamespace) {
      setSaveMessage("请先选择名称空间，或先完成一次名称空间巡检后再保存");
      return;
    }

    try {
      const payload = {
        name: normalizedName,
        namespace: selectedNamespace,
        label_selector: currentSaveLabelSelector || null,
        resource_scope: ["pods", "services", "ingresses", "daemonsets", "secrets"],
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
        setSaveMessage("导入内容不包含当前页面可导入的名称空间对象");
        return;
      }
      setSaveMessage(`已导入 ${created.length} 个名称空间巡检对象`);
      setImportContent("");
      setSavedTargetsOpen(true);
      setModalType(null);
    } catch {
      setSaveMessage("导入失败，请检查 JSON 格式");
    }
  }

  async function handleRunDiagnosis() {
    if (!data) {
      return;
    }

    setDiagnosisVisible(true);
    await diagnosis.submit({
      namespace: data.namespace,
      scope: data.inspection_target.label_selector ?? null,
    });
  }

  return (
    <section className="page-section">
      <header className="section-header">
        <div>
          <p className="eyebrow">巡检入口</p>
          <h2>名称空间巡检</h2>
        </div>
        {data ? <StatusBadge status={data.health_status} /> : <StatusBadge status="info" />}
      </header>

      <section className="panel workbench-hero">
        <div className="workbench-copy">
          <div className="section-header">
            <div>
              <h3>选择范围</h3>
              <p className="inline-note">先选名称空间，再决定是否加 Label Selector，最后直接巡检名称空间。</p>
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
                onChange={(event) => {
                  setNamespace(event.target.value);
                  setManualNamespaceEnabled(false);
                  setManualNamespace("");
                }}
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
              Label Selector（可选）
              <input
                aria-label="Label Selector（可选）"
                value={labelSelector}
                onChange={(event) => setLabelSelector(event.target.value)}
                placeholder="例如：app=api"
              />
            </label>
          </div>
          <div className="button-row">
            <button type="button" onClick={() => void handleRunInspection()} disabled={loading || !selectedNamespace}>
              {loading ? "巡检中..." : "巡检名称空间"}
            </button>
            <button
              type="button"
              className="text-button"
              onClick={() => setManualNamespaceEnabled((current) => !current)}
            >
              {manualNamespaceEnabled ? "收起高级输入" : "找不到名称空间？使用高级输入"}
            </button>
          </div>
          {manualNamespaceEnabled ? (
            <label>
              手动名称空间
              <input
                aria-label="手动名称空间"
                value={manualNamespace}
                onChange={(event) => setManualNamespace(event.target.value)}
                placeholder="仅在下拉中找不到时使用"
              />
            </label>
          ) : null}
          <p className="inline-note">当前范围：{currentSaveScopeText}</p>
          {namespaceLoading ? <p className="inline-note">名称空间发现中...</p> : null}
          {namespaceError ? <p>名称空间读取失败：{namespaceError}</p> : null}
        </div>
        <div className="hero-metric-stack">
          <div className="hero-metric hero-metric-compact">
            <span>可选名称空间</span>
            <strong>{namespaceDiscovery?.namespaces.length ?? 0}</strong>
          </div>
          <div className="hero-metric hero-metric-compact">
            <span>当前模式</span>
            <strong>{labelSelector.trim() ? "标签范围" : "全名称空间"}</strong>
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
              <span className="section-tip">编辑和删除只放在这里</span>
            </div>
            {targetsLoading ? <p>加载已保存对象中...</p> : null}
            {!targetsLoading && targets.length === 0 ? <p>暂无保存对象，保存当前巡检范围后可复用。</p> : null}
            <div className="quick-target-grid">
              {targets.map((target) => (
                <div key={target.id} className="quick-target-card">
                  <strong>{target.name}</strong>
                  <span>{target.namespace}{target.label_selector ? ` / ${target.label_selector}` : " / 全名称空间"}</span>
                  <small>名称空间巡检对象</small>
                  <div className="log-hit-actions">
                    <button type="button" onClick={() => applyQuickTarget(target)} disabled={loading}>
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

      {error ? <p>巡检失败：{error}</p> : null}
      {data ? (
        <>
          <section className="panel">
            <div className="section-header">
              <div>
                <h3>本次结果摘要</h3>
                <p className="inline-note">先看异常数量和异常分类，再进入 Pod 证据和模板匹配。</p>
              </div>
              <StatusBadge status={data.health_status} />
            </div>
            <KeyValueList
              items={[
                { label: "巡检命名空间", value: data.namespace },
                { label: "异常 Pod", value: String(abnormalPods.length) },
                { label: "正常 / 已完成 Pod", value: String(healthyPods.length) },
                { label: "异常分类", value: abnormalPods.length > 0 ? "需要处理" : "无异常 Pod" },
              ]}
            />
            <div className="card-grid card-grid-wide">
              <article className="card">
                <div className="card-title">
                  <strong>当前范围</strong>
                  <StatusBadge status={labelSelector.trim() ? "warning" : "info"} />
                </div>
                <p>{data.namespace}{data.inspection_target.label_selector ? ` / ${data.inspection_target.label_selector}` : " / 全名称空间"}</p>
              </article>
              <article className="card">
                <div className="card-title">
                  <strong>关联对象</strong>
                  <StatusBadge status="info" />
                </div>
                <p>
                  Service {data.services.length} / Ingress {data.ingresses.length} / Secret {data.tls_secrets.length} /
                  DaemonSet {data.daemonsets.length}
                </p>
              </article>
            </div>
          </section>

          <section className="panel panel-muted">
            <div className="section-header">
              <div>
                <h3>模板匹配</h3>
                <p className="inline-note">基于当前名称空间巡检范围运行故障模板，不展示完整日志和完整 describe。</p>
              </div>
              {diagnosis.data ? <StatusBadge status={diagnosis.data.status} /> : null}
            </div>
            <div className="button-row">
              <button type="button" onClick={() => void handleRunDiagnosis()} disabled={diagnosis.loading}>
                {diagnosis.loading ? "模板匹配中..." : "模板匹配"}
              </button>
            </div>
            {diagnosisVisible ? (
              <DiagnosisResultPanel
                data={diagnosis.data}
                loading={diagnosis.loading}
                error={diagnosis.error}
                title="当前范围模板匹配结果"
                idleMessage="点击模板匹配后，系统会按当前名称空间和标签范围检查已录入模板。"
              />
            ) : null}
          </section>

          <div className="inspection-layout">
            <div className="panel">
              <div className="section-header">
                <h3>Pod 证据入口</h3>
                <span className="section-tip">异常排前面，点左侧 Pod 再看右侧详情</span>
              </div>
              <div className="pod-list">
                {sortedPods.map((pod) => {
                  const active = selectedPod?.name === pod.name;
                  return (
                    <button
                      key={pod.name}
                      type="button"
                      className={`pod-list-item${active ? " pod-list-item-active" : ""}`}
                      onClick={() => setSelectedPodName(pod.name)}
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
                {selectedPod ? <StatusBadge status={selectedPod.status} /> : null}
              </div>
              {selectedPod ? (
                <div className="page-section">
                  <KeyValueList
                    items={[
                      { label: "Pod", value: selectedPod.name },
                      { label: "状态", value: selectedPod.status },
                      { label: "重启次数", value: String(selectedPod.restarts) },
                      {
                        label: "资源使用",
                        value: `CPU ${selectedPod.resource_usage.cpu ?? "n/a"} / MEM ${selectedPod.resource_usage.memory ?? "n/a"}`,
                      },
                    ]}
                  />
                  <article className="card">
                    <strong>Describe 摘要</strong>
                    <p>{selectedPod.describe_summary}</p>
                  </article>
                  <article className="card">
                    <strong>事件</strong>
                    {selectedPod.events.length > 0 ? (
                      <ul className="plain-list">
                        {selectedPod.events.map((event) => (
                          <li key={event}>{event}</li>
                        ))}
                      </ul>
                    ) : (
                      <p>无事件</p>
                    )}
                  </article>
                  <article className="card">
                    <strong>{logHits.length > 0 ? "关键字命中" : "原始日志摘要"}</strong>
                    {ignoreMessage ? <p className="inline-note">{ignoreMessage}</p> : null}
                    {logHits.length > 0 ? (
                      <div className="log-hit-list">
                        {logHits.map((hit) => {
                          const hitKey = `${selectedPod.name}:${hit.keyword}:${hit.matched_text}`;
                          const ignored = hit.whitelisted || ignoredLogKeys.includes(hitKey);
                          const ignoring = ignoringLogKeys.includes(hitKey);
                          return (
                            <article key={hitKey} className={`log-hit-card${ignored ? " log-hit-card-muted" : ""}`}>
                              <div className="card-title">
                                <strong>{hit.keyword}</strong>
                                <StatusBadge status={ignored ? "disabled" : hit.severity} />
                              </div>
                              <p>{hit.category} / {hit.container_name ? `容器 ${hit.container_name}` : "未标记容器"}</p>
                              <pre className="log-block">{hit.matched_text}</pre>
                              <div className="log-hit-actions">
                                <button
                                  type="button"
                                  onClick={() => void handleIgnoreLogHit(hit)}
                                  disabled={ignored || ignoring}
                                >
                                  {hit.whitelisted ? "白名单已生效" : ignored ? "已忽略" : ignoring ? "处理中..." : "忽略此报错"}
                                </button>
                              </div>
                              {hit.whitelisted ? <p className="inline-note">该命中已被白名单忽略</p> : null}
                              {!hit.whitelisted && ignored ? <p className="inline-note">已加入白名单，后续巡检会自动忽略该命中</p> : null}
                            </article>
                          );
                        })}
                      </div>
                    ) : (
                      <pre className="log-block">{selectedPod.log_summary ?? "无日志摘要"}</pre>
                    )}
                  </article>
                </div>
              ) : (
                <p>暂无 Pod 证据</p>
              )}
            </div>
          </div>

          <section className="page-section">
            <div className="section-header">
              <h3>关联对象状态</h3>
              <span className="section-tip">不抢 Pod 焦点，只做补充判断</span>
            </div>
            <div className="card-grid">
              {[
                { title: "Service", items: data.services },
                { title: "Ingress", items: data.ingresses },
                { title: "Secret", items: data.tls_secrets },
                { title: "DaemonSet", items: data.daemonsets },
              ].map((group) => (
                <article key={group.title} className="card">
                  <div className="card-title">
                    <strong>{group.title}</strong>
                    <span>{group.items.length}</span>
                  </div>
                  {group.items.length > 0 ? (
                    <ul className="plain-list">
                      {group.items.map((item) => (
                        <li key={`${group.title}-${item.name}`}>
                          {item.name} / {item.status}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>本次未发现相关对象</p>
                  )}
                </article>
              ))}
            </div>
          </section>
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
                    ? "把当前名称空间巡检范围保存为可复用入口。"
                    : modalType === "import"
                      ? "只导入名称空间巡检对象，其他类型会自动过滤。"
                      : "导出后可复制到其他环境导入。"}
                </p>
              </div>
              <button type="button" onClick={() => setModalType(null)}>关闭</button>
            </div>

            {modalType === "save" ? (
              <>
                <p className="inline-note">当前将保存：{currentSaveScopeText}</p>
                <label>
                  常用范围名称
                  <input
                    aria-label="常用范围名称"
                    value={targetName}
                    onChange={(event) => setTargetName(event.target.value)}
                    placeholder="例如：demo API 名称空间巡检"
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
