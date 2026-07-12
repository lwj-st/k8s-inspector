import { useState } from "react";

import { ignoreWhitelistLogHit } from "../api/client";
import type { KeywordHit, SavedInspectionTarget } from "../api/types";
import { KeyValueList } from "../components/KeyValueList";
import { StatusBadge } from "../components/StatusBadge";
import { useRunNamespaceInspection } from "../features/inspections/useRunNamespaceInspection";
import { useSavedInspectionTargets } from "../features/inspections/useSavedInspectionTargets";

function isHealthyStatus(status: string) {
  const normalized = status.toLowerCase();
  return normalized.includes("running") || normalized.includes("ready") || normalized.includes("healthy");
}

function sortPods<T extends { status: string; restarts: number }>(pods: T[]) {
  return [...pods].sort((left, right) => {
    const leftRank = isHealthyStatus(left.status) ? 1 : 0;
    const rightRank = isHealthyStatus(right.status) ? 1 : 0;

    if (leftRank !== rightRank) {
      return leftRank - rightRank;
    }

    return right.restarts - left.restarts;
  });
}

export function NamespaceInspectionPage() {
  const [namespace, setNamespace] = useState("");
  const [labelSelector, setLabelSelector] = useState("");
  const [targetName, setTargetName] = useState("");
  const [editingTargetId, setEditingTargetId] = useState<number | null>(null);
  const [exportContent, setExportContent] = useState("");
  const [importContent, setImportContent] = useState("");
  const [selectedPodName, setSelectedPodName] = useState<string | null>(null);
  const [ignoredLogKeys, setIgnoredLogKeys] = useState<string[]>([]);
  const [ignoringLogKeys, setIgnoringLogKeys] = useState<string[]>([]);
  const [ignoreMessage, setIgnoreMessage] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const { data, loading, error, submit } = useRunNamespaceInspection();
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
  const sortedPods = data ? sortPods(data.pods) : [];
  const selectedPod =
    sortedPods.find((pod) => pod.name === selectedPodName) ??
    sortedPods[0] ??
    null;
  const abnormalPods = sortedPods.filter((pod) => !isHealthyStatus(pod.status));
  const healthyPods = sortedPods.filter((pod) => isHealthyStatus(pod.status));
  const logHits = selectedPod?.log_hits ?? [];
  const currentSaveNamespace = namespace.trim() || data?.namespace?.trim() || "";
  const currentSaveLabelSelector = labelSelector.trim() || data?.inspection_target.label_selector?.trim() || "";
  const canSaveCurrentTarget = targetName.trim().length > 0 && currentSaveNamespace.length > 0;

  function resetAfterInspection() {
    setSelectedPodName(null);
    setIgnoredLogKeys([]);
    setIgnoringLogKeys([]);
    setIgnoreMessage(null);
  }

  function applyQuickTarget(target: SavedInspectionTarget) {
    setNamespace(target.namespace);
    setLabelSelector(target.label_selector ?? "");
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
        namespace: data?.namespace ?? namespace,
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

  async function handleSaveCurrentTarget() {
    const normalizedName = targetName.trim();
    if (!normalizedName) {
      setSaveMessage("请先填写保存名称");
      return;
    }
    if (!currentSaveNamespace) {
      setSaveMessage("请先填写名称空间，或先完成一次名称空间巡检后再保存");
      return;
    }

    try {
      const payload = {
        name: normalizedName,
        namespace: currentSaveNamespace,
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
      setNamespace(currentSaveNamespace);
      setLabelSelector(currentSaveLabelSelector);
      setTargetName("");
      setEditingTargetId(null);
    } catch (reason) {
      const detail = reason instanceof Error ? `：${reason.message}` : "";
      setSaveMessage(editingTargetId !== null ? `更新失败${detail}` : `保存失败${detail}`);
    }
  }

  function startEditingTarget(target: SavedInspectionTarget) {
    setEditingTargetId(target.id);
    setTargetName(target.name);
    setNamespace(target.namespace);
    setLabelSelector(target.label_selector ?? "");
    setSaveMessage(`正在编辑 ${target.name}`);
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

  async function handleExportTargets() {
    try {
      const items = await exportTargets();
      setExportContent(JSON.stringify(items, null, 2));
    } catch {
      setExportContent("导出失败");
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
    } catch {
      setSaveMessage("导入失败，请检查 JSON 格式");
    }
  }

  return (
    <section className="page-section">
      <header className="section-header">
        <div>
          <p className="eyebrow">巡检入口</p>
          <h2>命名空间巡检</h2>
        </div>
        {data ? <StatusBadge status={data.health_status} /> : null}
      </header>
      <section className="panel panel-muted">
        <div className="section-header">
          <h3>已保存巡检对象</h3>
          <span className="section-tip">保存常用名称空间范围后，可直接复用</span>
        </div>
        <label>
          保存名称
          <input value={targetName} onChange={(event) => setTargetName(event.target.value)} placeholder="例如：demo 全名称空间" />
        </label>
        <div className="button-row">
          <button type="button" onClick={() => void handleSaveCurrentTarget()} disabled={targetSaving || !canSaveCurrentTarget}>
            {targetSaving ? (editingTargetId !== null ? "更新中..." : "保存中...") : editingTargetId !== null ? "更新当前对象" : "保存当前范围"}
          </button>
          <button type="button" onClick={() => void handleExportTargets()} disabled={targetsLoading}>
            刷新导出内容
          </button>
        </div>
        {targetName.trim().length > 0 && !currentSaveNamespace ? (
          <p className="inline-note">先填写名称空间，或运行一次巡检后再保存。</p>
        ) : null}
        {saveMessage ? <p className="inline-note">{saveMessage}</p> : null}
        {targetsError ? <p>保存对象失败：{targetsError}</p> : null}
        {targetsLoading ? <p>加载已保存对象中...</p> : null}
        {!targetsLoading && targets.length === 0 ? <p>暂无保存对象，保存当前巡检范围后可复用。</p> : null}
        <label>
          导出内容
          <textarea aria-label="导出内容" value={exportContent} readOnly rows={6} />
        </label>
        <label>
          导入内容
          <textarea aria-label="导入内容" value={importContent} onChange={(event) => setImportContent(event.target.value)} rows={6} />
        </label>
        <button type="button" onClick={() => void handleImportTargets()} disabled={targetSaving || importContent.trim().length === 0}>
          导入巡检对象
        </button>
        <div className="quick-target-grid">
          {targets.map((target) => (
            <div key={target.id} className="quick-target-card">
              <strong>使用 {target.name}</strong>
              <span>{target.namespace}{target.label_selector ? ` / ${target.label_selector}` : " / 全名称空间"}</span>
              <small>{target.target_type === "namespace" ? "名称空间巡检对象" : "Pod 巡检对象"}</small>
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
      <form
        className="panel"
        onSubmit={(event) => {
          event.preventDefault();
          void submit(namespace, labelSelector).then(resetAfterInspection);
        }}
      >
        <div className="section-header">
          <h3>检查范围</h3>
          <span className="section-tip">支持直接巡检整个名称空间或附加 label</span>
        </div>
        <label>
          名称空间
          <input value={namespace} onChange={(event) => setNamespace(event.target.value)} />
        </label>
        <label>
          Label Selector
          <input value={labelSelector} onChange={(event) => setLabelSelector(event.target.value)} />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "巡检中..." : "运行巡检"}
        </button>
      </form>
      {error ? <p>巡检失败：{error}</p> : null}
      {data ? (
        <>
          <KeyValueList
            items={[
              { label: "巡检命名空间", value: data.namespace },
              { label: "异常 Pod", value: String(abnormalPods.length) },
              { label: "正常 Pod", value: String(healthyPods.length) },
              { label: "巡检状态", value: data.health_status },
            ]}
          />
          <div className="card-grid">
            <article className="card">
              <div className="card-title">
                <strong>Pod 视角</strong>
                <StatusBadge status={abnormalPods.length > 0 ? "warning" : "healthy"} />
              </div>
              <p>异常优先排序，先看不健康的 Pod 和重启较多的实例。</p>
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
          <div className="inspection-layout">
            <div className="panel">
              <div className="section-header">
                <h3>Pod 列表</h3>
                <span className="section-tip">异常排前面</span>
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
                      <small>{isHealthyStatus(pod.status) ? "状态正常" : "优先处理"}</small>
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
    </section>
  );
}
