import { useState } from "react";

import { ignoreWhitelistLogHit } from "../api/client";
import type { KeywordHit, SavedInspectionTarget } from "../api/types";
import { KeyValueList } from "../components/KeyValueList";
import { StatusBadge } from "../components/StatusBadge";
import { useRunPodInspection } from "../features/inspections/useRunPodInspection";
import { useSavedInspectionTargets } from "../features/inspections/useSavedInspectionTargets";

export function PodInspectionPage() {
  const [namespace, setNamespace] = useState("");
  const [podName, setPodName] = useState("");
  const [targetName, setTargetName] = useState("");
  const [editingTargetId, setEditingTargetId] = useState<number | null>(null);
  const [exportContent, setExportContent] = useState("");
  const [importContent, setImportContent] = useState("");
  const [ignoredLogKeys, setIgnoredLogKeys] = useState<string[]>([]);
  const [ignoringLogKeys, setIgnoringLogKeys] = useState<string[]>([]);
  const [ignoreMessage, setIgnoreMessage] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const { data, loading, error, submit } = useRunPodInspection();
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

  const selectedPod = data?.pod ?? null;
  const logHits = selectedPod?.log_hits ?? [];

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
        label_selector: null,
        pod_name_pattern: selectedPod.name,
        container_name: hit.container_name ?? null,
        keyword: hit.keyword,
        note: "从 Pod 巡检结果忽略",
      });
      setIgnoredLogKeys((current) => [...current, hitKey]);
      setIgnoreMessage("已加入白名单，后续 Pod 巡检会自动忽略该命中");
    } catch (reason) {
      setIgnoreMessage(reason instanceof Error ? `加入白名单失败：${reason.message}` : "加入白名单失败");
    } finally {
      setIgnoringLogKeys((current) => current.filter((item) => item !== hitKey));
    }
  }

  function resetAfterInspection() {
    setIgnoredLogKeys([]);
    setIgnoringLogKeys([]);
    setIgnoreMessage(null);
  }

  function applySavedTarget(target: SavedInspectionTarget) {
    setNamespace(target.namespace);
    setPodName(target.pod_name ?? "");
    void submit(target.namespace, target.pod_name ?? "").then(resetAfterInspection);
  }

  function startEditingTarget(target: SavedInspectionTarget) {
    setEditingTargetId(target.id);
    setTargetName(target.name);
    setNamespace(target.namespace);
    setPodName(target.pod_name ?? "");
    setSaveMessage(`正在编辑 ${target.name}`);
  }

  async function handleSaveCurrentTarget() {
    const normalizedName = targetName.trim();
    const normalizedNamespace = namespace.trim() || data?.namespace?.trim() || "";
    const normalizedPodName = podName.trim();
    if (!normalizedName) {
      setSaveMessage("请先填写保存名称");
      return;
    }
    if (!normalizedNamespace || !normalizedPodName) {
      setSaveMessage("请先填写名称空间和 Pod 名称");
      return;
    }

    try {
      const payload = {
        name: normalizedName,
        namespace: normalizedNamespace,
        pod_name: normalizedPodName,
        resource_scope: ["pods"],
      };

      if (editingTargetId !== null) {
        await updateTarget(editingTargetId, payload);
        setSaveMessage(`已更新 ${normalizedName}`);
      } else {
        await saveTarget(payload);
        setSaveMessage(`已保存 ${normalizedName}`);
      }

      setNamespace(normalizedNamespace);
      setPodName(normalizedPodName);
      setTargetName("");
      setEditingTargetId(null);
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
        setSaveMessage("导入内容不包含当前页面可导入的 Pod 巡检对象");
        return;
      }
      setSaveMessage(`已导入 ${created.length} 个 Pod 巡检对象`);
      setImportContent("");
    } catch {
      setSaveMessage("导入失败，请检查 JSON 格式");
    }
  }

  return (
    <section className="page-section">
      <header className="section-header">
        <div>
          <p className="eyebrow">定点巡检</p>
          <h2>单 Pod 巡检</h2>
        </div>
        {selectedPod ? <StatusBadge status={selectedPod.status} /> : null}
      </header>
      <section className="panel panel-muted">
        <div className="section-header">
          <h3>已保存 Pod 巡检对象</h3>
          <span className="section-tip">保存常用 Pod 后，可直接复用巡检入口</span>
        </div>
        <label>
          保存名称
          <input value={targetName} onChange={(event) => setTargetName(event.target.value)} placeholder="例如：demo-api 启动排查" />
        </label>
        <div className="button-row">
          <button type="button" onClick={() => void handleSaveCurrentTarget()} disabled={targetSaving || targetName.trim().length === 0}>
            {targetSaving ? (editingTargetId !== null ? "更新中..." : "保存中...") : editingTargetId !== null ? "更新当前对象" : "保存当前 Pod"}
          </button>
          <button type="button" onClick={() => void handleExportTargets()} disabled={targetsLoading}>
            刷新导出内容
          </button>
        </div>
        {saveMessage ? <p className="inline-note">{saveMessage}</p> : null}
        {targetsError ? <p>保存对象失败：{targetsError}</p> : null}
        {targetsLoading ? <p>加载已保存对象中...</p> : null}
        {!targetsLoading && targets.length === 0 ? <p>暂无保存对象，保存当前 Pod 巡检范围后可复用。</p> : null}
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
              <span>{target.namespace}{target.pod_name ? ` / ${target.pod_name}` : ""}</span>
              <small>Pod 巡检对象</small>
              <div className="log-hit-actions">
                <button type="button" onClick={() => applySavedTarget(target)} disabled={loading}>
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
          void submit(namespace, podName).then(resetAfterInspection);
        }}
      >
        <div className="section-header">
          <h3>检查入口</h3>
          <span className="section-tip">直接调用 Pod 专用巡检接口，只返回这一条 Pod 的证据链</span>
        </div>
        <label>
          名称空间
          <input value={namespace} onChange={(event) => setNamespace(event.target.value)} />
        </label>
        <label>
          Pod 名称
          <input value={podName} onChange={(event) => setPodName(event.target.value)} />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "巡检中..." : "运行 Pod 巡检"}
        </button>
      </form>
      {error ? <p>巡检失败：{error}</p> : null}
      {ignoreMessage ? <p className="inline-note">{ignoreMessage}</p> : null}
      {selectedPod ? (
        <>
          <KeyValueList
            items={[
              { label: "名称空间", value: data?.namespace ?? namespace },
              { label: "Pod", value: selectedPod.name },
              { label: "状态", value: selectedPod.status },
              { label: "重启次数", value: String(selectedPod.restarts) },
            ]}
          />
          <div className="card-grid">
            <article className="card">
              <div className="card-title">
                <strong>资源使用</strong>
                <StatusBadge status="info" />
              </div>
              <p>CPU {selectedPod.resource_usage.cpu ?? "n/a"} / MEM {selectedPod.resource_usage.memory ?? "n/a"}</p>
            </article>
            <article className="card">
              <div className="card-title">
                <strong>命中事件</strong>
                <StatusBadge status={selectedPod.events.length > 0 ? "warning" : "healthy"} />
              </div>
              <p>{selectedPod.events.length > 0 ? `${selectedPod.events.length} 条事件` : "无关键事件"}</p>
            </article>
          </div>
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
            <strong>日志命中</strong>
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
              <pre className="log-block">{selectedPod.log_summary ?? "无日志摘要"}</pre>
            )}
          </article>
        </>
      ) : null}
    </section>
  );
}
