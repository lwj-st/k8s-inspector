import { useEffect, useState } from "react";

import { ignoreWhitelistLogHit, runNamespaceBatchInspection } from "../api/client";
import type {
  InspectedObject,
  InspectedPod,
  KeywordHit,
  NamespaceBatchInspectionResponse,
  NamespaceBatchInspectionResult,
  NamespaceInspectionResponse,
  NamespaceSummary,
} from "../api/types";
import { KeyValueList } from "../components/KeyValueList";
import { StatusBadge } from "../components/StatusBadge";
import { DiagnosisResultPanel } from "../features/diagnosis/DiagnosisResultPanel";
import { useRunDiagnosis } from "../features/diagnosis/useRunDiagnosis";
import { useDiscoverNamespaces } from "../features/inspections/useDiscoverNamespaces";
import { isHealthyPod } from "../features/inspections/podHealth";
import { labelSelectorOptionsForPod } from "../features/inspections/podLabels";
import { useRunNamespaceInspection } from "../features/inspections/useRunNamespaceInspection";
import { normalizeTerminalLogText } from "../features/logs/logText";

const ABNORMAL_CATEGORY_LABELS = {
  pod_status: "Pod 状态",
  container_status: "容器状态",
  event: "事件",
  log_keyword: "日志关键字",
  related_object: "关联对象",
} as const;

function namespaceStatus(summary: NamespaceSummary) {
  if (summary.status) {
    return summary.status;
  }
  if (summary.abnormal_pod_count > 0) {
    return "warning";
  }
  return "unknown";
}

function abnormalCategoryLabel(category: string) {
  return ABNORMAL_CATEGORY_LABELS[category as keyof typeof ABNORMAL_CATEGORY_LABELS] ?? category;
}

function batchRowType(status: NamespaceBatchInspectionResult["health_status"]) {
  if (status === "error") {
    return "需要处理";
  }
  if (status === "warning") {
    return "需要处理";
  }
  return "巡检正常";
}

function isHealthyObject(item: InspectedObject) {
  return item.status === "healthy";
}

function buildLogHitKey(podName: string, hit: KeywordHit) {
  return `${podName}:${hit.container_name ?? "-"}:${hit.keyword}:${hit.matched_text}`;
}

function logHitContext(hit: KeywordHit) {
  return normalizeTerminalLogText(hit.context_text?.trim() || hit.matched_text);
}

type IgnoreDraft = {
  pod: InspectedPod;
  hit: KeywordHit;
  namespace: string;
  labelSelector: string;
  keyword: string;
  note: string;
};

function NamespaceObjectSection({
  title,
  kindLabel,
  items,
}: {
  title: string;
  kindLabel: string;
  items: InspectedObject[];
}) {
  if (items.length === 0) {
    return null;
  }

  const abnormalItems = items.filter((item) => !isHealthyObject(item));
  const healthyItems = items.filter(isHealthyObject);

  return (
    <section className="namespace-object-section">
      <div className="section-header">
        <h4>{title}</h4>
        {abnormalItems.length > 0 ? <span className="section-tip">异常优先</span> : null}
      </div>
      {abnormalItems.length > 0 ? (
        <div className="namespace-object-list">
          {abnormalItems.map((item) => (
            <article key={`${kindLabel}-${item.name}`} className="namespace-object-card namespace-object-card-abnormal">
              <strong>{kindLabel}/{item.name}：{item.status}</strong>
              <p>{item.summary}</p>
            </article>
          ))}
        </div>
      ) : null}
      {healthyItems.length > 0 ? (
        <details className="healthy-pods-details">
          <summary>{abnormalItems.length > 0 ? `正常${title}（${healthyItems.length}）` : `${title}（全部正常 ${healthyItems.length}）`}</summary>
          <div className="namespace-object-list">
            {healthyItems.map((item) => (
              <article key={`${kindLabel}-${item.name}`} className="namespace-object-card namespace-object-card-healthy">
                <strong>{kindLabel}/{item.name}：{item.status}</strong>
                <p>{item.summary}</p>
              </article>
            ))}
          </div>
        </details>
      ) : null}
    </section>
  );
}

function EvidencePodCard({
  pod,
  ignoredLogKeys,
  ignoringLogKeys,
  onRequestIgnore,
}: {
  pod: InspectedPod;
  ignoredLogKeys: string[];
  ignoringLogKeys: string[];
  onRequestIgnore: (pod: InspectedPod, hit: KeywordHit) => void;
}) {
  const activeLogHits = pod.log_hits.filter((hit) => !hit.whitelisted && !ignoredLogKeys.includes(buildLogHitKey(pod.name, hit)));

  return (
    <article className={`evidence-pod-card${isHealthyPod(pod) ? " evidence-pod-card-healthy" : " evidence-pod-card-abnormal"}`}>
      <div className="card-title">
        <div>
          <strong>{pod.name}</strong>
          <p className="inline-note">节点：{pod.node_name ?? "未知"} · 重启：{pod.restarts}</p>
        </div>
        <StatusBadge status={pod.status} />
      </div>
      <div className="evidence-grid">
        <div>
          <span className="evidence-label">容器状态</span>
          {pod.containers.length > 0 ? (
            <ul className="plain-list">
              {pod.containers.map((container) => (
                <li key={container.name}>
                  {container.name}：{container.state}{container.reason ? ` / ${container.reason}` : ""}
                </li>
              ))}
            </ul>
          ) : <p className="inline-note">暂无容器状态</p>}
        </div>
        <div>
          <span className="evidence-label">事件摘要</span>
          {pod.events.length > 0 ? <pre className="log-block code-block-scroll">{pod.events.join("\n")}</pre> : <p className="inline-note">暂无事件</p>}
        </div>
        <div>
          <span className="evidence-label">Describe 摘要</span>
          <pre className="log-block code-block-scroll">{pod.describe_summary || "暂无 Describe 摘要"}</pre>
        </div>
        <div>
          <span className="evidence-label">日志关键字命中</span>
          {activeLogHits.length > 0 ? (
            <ul className="plain-list">
              {activeLogHits.map((hit) => {
                const hitKey = buildLogHitKey(pod.name, hit);
                const isIgnoring = ignoringLogKeys.includes(hitKey);

                return (
                  <li key={hitKey}>
                    <div>{hit.keyword}</div>
                    <span className="inline-note">命中上下文（不是完整日志）</span>
                    <pre className="log-block code-block-scroll">{logHitContext(hit)}</pre>
                    <div className="button-row">
                      <button
                        type="button"
                        disabled={isIgnoring}
                        onClick={() => onRequestIgnore(pod, hit)}
                      >
                        {isIgnoring ? "处理中..." : "忽略此命中"}
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : <p className="inline-note">暂无命中</p>}
        </div>
        <div>
          <span className="evidence-label">关联对象</span>
          {pod.related_resources.length > 0 ? (
            <ul className="plain-list">
              {pod.related_resources.map((resource) => <li key={`${resource.kind}-${resource.name}`}>{resource.kind}/{resource.name}：{resource.status}</li>)}
            </ul>
          ) : <p className="inline-note">暂无关联对象</p>}
        </div>
      </div>
    </article>
  );
}

function NamespaceEvidenceDrawer({
  item,
  data,
  loading,
  error,
  onClose,
  ignoredLogKeys,
  ignoringLogKeys,
  ignoreMessage,
  ignoreDraft,
  onRequestIgnore,
  onCancelIgnore,
  onChangeIgnoreDraft,
  onConfirmIgnore,
}: {
  item: NamespaceBatchInspectionResult;
  data: NamespaceInspectionResponse | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  ignoredLogKeys: string[];
  ignoringLogKeys: string[];
  ignoreMessage: string | null;
  ignoreDraft: IgnoreDraft | null;
  onRequestIgnore: (pod: InspectedPod, hit: KeywordHit) => void;
  onCancelIgnore: () => void;
  onChangeIgnoreDraft: (draft: IgnoreDraft) => void;
  onConfirmIgnore: () => void;
}) {
  const namespace = item.detail_target.namespace ?? item.summary.name;
  const summary = item.summary;
  const pods = data?.pods ?? [];
  const abnormalPods = pods.filter((pod) => !isHealthyPod(pod));
  const healthyPods = pods.filter(isHealthyPod);
  const abnormalCategoryLabels = summary.abnormal_categories.map(abnormalCategoryLabel);
  const services = data?.services ?? [];
  const ingresses = data?.ingresses ?? [];
  const daemonsets = data?.daemonsets ?? [];
  const tlsSecrets = data?.tls_secrets ?? [];
  const hasNamespaceObjects = services.length > 0 || ingresses.length > 0 || daemonsets.length > 0 || tlsSecrets.length > 0;

  return (
    <div className="evidence-drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside className="evidence-drawer" aria-label={`${namespace} 巡检证据`} onMouseDown={(event) => event.stopPropagation()}>
        <div className="section-header">
          <div>
            <p className="eyebrow">名称空间证据</p>
            <h3>{namespace}</h3>
          </div>
          <button type="button" onClick={onClose}>关闭</button>
        </div>
        <section className="panel panel-muted">
          <div className="section-header">
            <h4>结论</h4>
            <StatusBadge status={data?.health_status ?? summary.status} />
          </div>
          <div className="evidence-drawer-summary">
            <span>Pod {data?.pods.length ?? summary.pod_count}</span>
            <span>异常 Pod {data ? abnormalPods.length : summary.abnormal_pod_count}</span>
          </div>
          <KeyValueList
            items={[
              { label: "名称空间", value: namespace },
              { label: "Label Selector", value: data?.inspection_target.label_selector ?? item.detail_target.label_selector ?? "未设置" },
              { label: "健康状态", value: data?.health_status ?? summary.status },
              { label: "异常分类数", value: String(abnormalCategoryLabels.length) },
            ]}
          />
          <div className="batch-category-block">
            <span className="inline-note">异常分类</span>
            <div className="batch-category-list">
              {abnormalCategoryLabels.length > 0 ? (
                abnormalCategoryLabels.map((label) => (
                  <span key={`${namespace}-${label}`} className="batch-category-chip">
                    {label}
                  </span>
                ))
              ) : (
                <span className="batch-category-chip batch-category-chip-muted">无异常分类</span>
              )}
            </div>
          </div>
        </section>
        {loading ? <p>正在读取名称空间证据...</p> : null}
        {error ? <section className="panel panel-muted"><h4>证据读取失败</h4><p>{error}</p></section> : null}
        {!loading && !error && data && pods.length === 0 && !hasNamespaceObjects ? <p>本次没有返回可展示的证据。</p> : null}
        {!loading && !error && data ? (
          <>
            <section className="panel panel-muted">
              <div className="section-header">
                <h4>证据</h4>
              </div>
              {pods.length > 0 ? (
                <div className="evidence-pod-list">
                  {abnormalPods.length > 0 ? (
                    <>
                      <div className="section-header"><h4>异常 Pod</h4><span className="section-tip">优先处理</span></div>
                      {abnormalPods.map((pod) => (
                        <EvidencePodCard
                          key={pod.name}
                          pod={pod}
                          ignoredLogKeys={ignoredLogKeys}
                          ignoringLogKeys={ignoringLogKeys}
                          onRequestIgnore={onRequestIgnore}
                        />
                      ))}
                    </>
                  ) : null}
                  {healthyPods.length > 0 ? (
                    <details className="healthy-pods-details">
                      <summary>{abnormalPods.length > 0 ? `正常 / 已完成 Pod（${healthyPods.length}）` : `Pod（全部正常 / 已完成 ${healthyPods.length}）`}</summary>
                      <div className="evidence-pod-list">
                        {healthyPods.map((pod) => (
                          <EvidencePodCard
                            key={pod.name}
                            pod={pod}
                            ignoredLogKeys={ignoredLogKeys}
                            ignoringLogKeys={ignoringLogKeys}
                            onRequestIgnore={onRequestIgnore}
                          />
                        ))}
                      </div>
                    </details>
                  ) : null}
                </div>
              ) : null}
              {hasNamespaceObjects ? (
                <section className="panel panel-muted evidence-nested-panel">
                  <div className="section-header">
                    <h4>名称空间级关联对象</h4>
                    <span className="section-tip">用于定位 Ingress、DaemonSet、Service、TLS Secret 异常</span>
                  </div>
                  <div className="evidence-pod-list">
                    <NamespaceObjectSection title="Service" kindLabel="Service" items={services} />
                    <NamespaceObjectSection title="Ingress" kindLabel="Ingress" items={ingresses} />
                    <NamespaceObjectSection title="DaemonSet" kindLabel="DaemonSet" items={daemonsets} />
                    <NamespaceObjectSection title="TLS Secret" kindLabel="TLS Secret" items={tlsSecrets} />
                  </div>
                </section>
              ) : null}
            </section>
            <section className="panel panel-muted">
              <div className="section-header">
                <div>
                  <h4>后续操作</h4>
                  <p className="inline-note">白名单忽略只影响相同范围下的同类命中；模板匹配入口保留在批量巡检摘要区。</p>
                </div>
              </div>
              {ignoreMessage ? (
                <section className="panel panel-muted evidence-nested-panel">
                  <p>{ignoreMessage}</p>
                </section>
              ) : null}
              {ignoreDraft ? (
                <section className="panel panel-muted evidence-nested-panel" aria-label="忽略关键字命中确认">
                  <div className="section-header">
                    <h4>确认忽略此命中</h4>
                    <span className="section-tip">确认白名单字段和生效 Label</span>
                  </div>
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
                        onChange={(event) => onChangeIgnoreDraft({ ...ignoreDraft, labelSelector: event.target.value })}
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
                        onChange={(event) => onChangeIgnoreDraft({ ...ignoreDraft, labelSelector: event.target.value })}
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
                        onChange={(event) => onChangeIgnoreDraft({ ...ignoreDraft, keyword: event.target.value })}
                        rows={4}
                      />
                    </label>
                    <label className="modal-form-field" style={{ gridColumn: "1 / -1" }}>
                      备注
                      <input
                        className="template-input"
                        aria-label="白名单备注"
                        value={ignoreDraft.note}
                        onChange={(event) => onChangeIgnoreDraft({ ...ignoreDraft, note: event.target.value })}
                        placeholder="例如：已确认是启动预热噪音"
                      />
                    </label>
                  </div>
                  <div className="button-row">
                    <button
                      className="modal-primary-button"
                      type="button"
                      onClick={onConfirmIgnore}
                      disabled={ignoringLogKeys.includes(buildLogHitKey(ignoreDraft.pod.name, ignoreDraft.hit)) || !ignoreDraft.namespace.trim() || !ignoreDraft.labelSelector.trim() || !ignoreDraft.keyword.trim()}
                    >
                      {ignoringLogKeys.includes(buildLogHitKey(ignoreDraft.pod.name, ignoreDraft.hit)) ? "保存中..." : "加入白名单"}
                    </button>
                    <button className="modal-secondary-button" type="button" onClick={onCancelIgnore}>
                      取消
                    </button>
                  </div>
                </section>
              ) : (
                <article className="quick-action-card evidence-action-card">
                  <strong>下一步</strong>
                  <span>先看异常 Pod 和日志关键字；如果需要判断是否属于已知故障，请关闭抽屉后点击“运行模板匹配”。</span>
                </article>
              )}
            </section>
          </>
        ) : null}
      </aside>
    </div>
  );
}

export function AutoInspectionPage() {
  const [search, setSearch] = useState("");
  const [selectedNamespace, setSelectedNamespace] = useState("");
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchError, setBatchError] = useState<string | null>(null);
  const [batchResult, setBatchResult] = useState<NamespaceBatchInspectionResponse | null>(null);
  const [lastBatchPayload, setLastBatchPayload] = useState<{ namespaces: string[]; all_namespaces: boolean } | null>(null);
  const [evidenceTarget, setEvidenceTarget] = useState<NamespaceBatchInspectionResult | null>(null);
  const [ignoredLogKeys, setIgnoredLogKeys] = useState<string[]>([]);
  const [ignoringLogKeys, setIgnoringLogKeys] = useState<string[]>([]);
  const [ignoreMessage, setIgnoreMessage] = useState<string | null>(null);
  const [ignoreDraft, setIgnoreDraft] = useState<IgnoreDraft | null>(null);
  const [diagnosisOpen, setDiagnosisOpen] = useState(false);
  const { data, loading, error, refresh } = useDiscoverNamespaces();
  const evidenceInspection = useRunNamespaceInspection();
  const diagnosis = useRunDiagnosis();

  const namespaces = data?.namespaces ?? [];
  const filteredNamespaces = namespaces.filter((item) => item.name.toLowerCase().includes(search.trim().toLowerCase()));
  const hasSelectedNamespace = selectedNamespace.length > 0;
  const hasNamespaces = namespaces.length > 0;

  useEffect(() => {
    if (selectedNamespace && !namespaces.some((item) => item.name === selectedNamespace)) {
      setSelectedNamespace("");
    }
  }, [namespaces, selectedNamespace]);

  function handleRetry() {
    void refresh().catch(() => undefined);
  }

  async function executeBatchInspection(payload: { namespaces: string[]; all_namespaces: boolean }) {
    setLastBatchPayload(payload);
    setBatchLoading(true);
    setBatchError(null);
    try {
      const result = await runNamespaceBatchInspection(payload);
      setBatchResult(result);
      return result;
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "未知错误";
      setBatchError(message);
      throw reason;
    } finally {
      setBatchLoading(false);
    }
  }

  function handleRunSelected() {
    if (!selectedNamespace) {
      return;
    }
    void executeBatchInspection({
      namespaces: [selectedNamespace],
      all_namespaces: false,
    }).catch(() => undefined);
  }

  function handleRunAll() {
    void executeBatchInspection({
      namespaces: [],
      all_namespaces: true,
    }).catch(() => undefined);
  }

  function handleRetryBatchInspection() {
    if (!lastBatchPayload) {
      return;
    }
    void executeBatchInspection(lastBatchPayload).catch(() => undefined);
  }

  function handleViewEvidence(item: NamespaceBatchInspectionResult) {
    setIgnoredLogKeys([]);
    setIgnoringLogKeys([]);
    setIgnoreMessage(null);
    setIgnoreDraft(null);
    setEvidenceTarget(item);
    void evidenceInspection.submit(item.detail_target.namespace ?? item.summary.name, item.detail_target.label_selector ?? null);
  }

  function handleCloseEvidence() {
    setEvidenceTarget(null);
    setIgnoreDraft(null);
    setIgnoreMessage(null);
    setIgnoredLogKeys([]);
    setIgnoringLogKeys([]);
  }

  function handleRequestIgnore(pod: InspectedPod, hit: KeywordHit) {
    if (!evidenceTarget) {
      return;
    }
    const namespace = evidenceInspection.data?.namespace ?? evidenceTarget.detail_target.namespace ?? evidenceTarget.summary.name;
    const currentSelector = evidenceInspection.data?.inspection_target.label_selector ?? evidenceTarget.detail_target.label_selector ?? null;
    const labelOptions = labelSelectorOptionsForPod(pod, currentSelector);
    setIgnoreMessage(null);
    setIgnoreDraft({
      pod,
      hit,
      namespace,
      labelSelector: labelOptions[0] ?? "",
      keyword: "",
      note: "自动巡检证据抽屉忽略",
    });
  }

  function handleCancelIgnore() {
    setIgnoreDraft(null);
  }

  async function handleConfirmIgnore() {
    if (!evidenceTarget || !ignoreDraft) {
      return;
    }

    const hitKey = buildLogHitKey(ignoreDraft.pod.name, ignoreDraft.hit);
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
      setIgnoreMessage("已加入白名单，后续相同范围的该命中会自动忽略");
      setIgnoreDraft(null);
    } catch (reason) {
      setIgnoreMessage(reason instanceof Error ? `加入白名单失败：${reason.message}` : "加入白名单失败");
    } finally {
      setIgnoringLogKeys((current) => current.filter((item) => item !== hitKey));
    }
  }

  function handleOpenDiagnosis() {
    setDiagnosisOpen(true);
    void diagnosis.submit({});
  }

  function handleCloseDiagnosis() {
    setDiagnosisOpen(false);
  }

  const batchResults = batchResult?.results ?? [];
  const sortedBatchResults = [...batchResults].sort((left, right) => {
    const leftRank = left.health_status === "error" ? 0 : left.health_status === "warning" ? 1 : 2;
    const rightRank = right.health_status === "error" ? 0 : right.health_status === "warning" ? 1 : 2;
    if (leftRank !== rightRank) {
      return leftRank - rightRank;
    }
    return left.summary.name.localeCompare(right.summary.name);
  });
  const errorBatchCount = batchResults.filter((item) => item.health_status === "error").length;
  const warningBatchCount = batchResults.filter((item) => item.health_status === "warning").length;
  const healthyBatchCount = batchResults.filter((item) => item.health_status === "healthy").length;
  const batchSummaryStatus = errorBatchCount > 0 ? "error" : warningBatchCount > 0 ? "warning" : "healthy";
  return (
    <section className="page-section">
      <section className="workbench-hero">
        <div className="workbench-copy">
          <div className="section-header">
            <div>
              <h3>名称空间</h3>
            </div>
          </div>
          <div className="workbench-command-panel status-command-panel">
            <div className="namespace-control-grid">
              <label className="inline-search namespace-field">
                <span className="namespace-field-label">搜索名称空间</span>
                <input
                  className="namespace-control namespace-search-control"
                  aria-label="搜索名称空间"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="例如：prod、kube-system"
                />
              </label>
              <label className="inline-search namespace-field">
                <span className="namespace-field-label">选择名称空间</span>
                <select
                  className="namespace-control namespace-select-control"
                  aria-label="选择名称空间"
                  value={selectedNamespace}
                  onChange={(event) => setSelectedNamespace(event.target.value)}
                  disabled={filteredNamespaces.length === 0}
                >
                  <option value="">{filteredNamespaces.length === 0 ? "没有可选名称空间" : "请选择一个名称空间"}</option>
                  {filteredNamespaces.map((item) => (
                    <option key={item.name} value={item.name}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="status-action-row">
              <button type="button" className="status-action-button status-action-button-primary" onClick={handleRunSelected} disabled={!hasSelectedNamespace || batchLoading}>
                {batchLoading ? "巡检中..." : "巡检"}
              </button>
              <button type="button" className="status-action-button" onClick={handleRunAll} disabled={!hasNamespaces || batchLoading}>
                {batchLoading ? "巡检中..." : "巡检全部名称空间"}
              </button>
            </div>
          </div>
        </div>
        <div className="hero-metric-stack">
          <div className="hero-metric hero-metric-compact">
            <span>名称空间总数</span>
            <strong>{namespaces.length}</strong>
          </div>
        </div>
      </section>

      {loading ? <p>名称空间加载中...</p> : null}
      {error ? (
        <section className="panel">
          <div className="section-header">
            <h3>加载失败</h3>
            <button type="button" onClick={handleRetry}>
              重试
            </button>
          </div>
          <p>名称空间读取失败：{error}</p>
        </section>
      ) : null}

      {!loading && !error ? (
        <>
          {namespaces.length === 0 ? (
            <section className="panel">
              <p>当前集群没有可用名称空间。</p>
            </section>
          ) : filteredNamespaces.length === 0 ? (
            <section className="panel">
              <p>没有匹配的名称空间，请调整搜索条件。</p>
            </section>
          ) : null}
        </>
      ) : null}

      {batchError ? (
        <section className="panel">
          <div className="section-header">
            <h3>批量巡检失败</h3>
            <button
              type="button"
              onClick={handleRetryBatchInspection}
              disabled={batchLoading || !lastBatchPayload}
            >
              重试批量巡检
            </button>
          </div>
          <p>批量巡检请求失败：{batchError}</p>
        </section>
      ) : null}

      {batchResult ? (
        <section className="panel">
          <div className="section-header">
            <div>
              <h3>批量巡检摘要</h3>
              <p className="inline-note">
                {batchResult.all_namespaces
                  ? "本次执行：巡检全部名称空间"
                  : `本次执行：巡检名称空间 ${batchResult.requested_namespaces.join("、") || "--"}`}
              </p>
            </div>
            <div className="button-row">
              <StatusBadge status={batchSummaryStatus} />
              <button type="button" onClick={handleOpenDiagnosis} disabled={diagnosis.loading}>
                {diagnosis.loading ? "模板匹配中..." : "运行模板匹配"}
              </button>
            </div>
          </div>
          <div className="batch-compact-summary">
            <span>总数 {batchResults.length}</span>
            <span>失败 {errorBatchCount}</span>
            <span>告警 {warningBatchCount}</span>
            <span>正常 {healthyBatchCount}</span>
          </div>
          <div className="table-scroll-shell batch-result-table-shell">
            <table className="compact-table batch-result-table">
              <thead>
                <tr>
                  <th>分类</th>
                  <th>名称空间</th>
                  <th>状态</th>
                  <th>Pod</th>
                  <th>异常 Pod</th>
                  <th>异常分类</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {sortedBatchResults.map((item) => (
                  <tr key={item.summary.name} aria-label={`批量结果 ${item.summary.name}`}>
                    <td>{batchRowType(item.health_status)}</td>
                    <td>
                      <div className="copyable-cell">
                        <span className="ellipsis-cell" title={item.summary.name}>{item.summary.name}</span>
                        <button type="button" className="copy-button" onClick={() => void navigator.clipboard?.writeText(item.summary.name)}>
                          复制
                        </button>
                      </div>
                    </td>
                    <td><StatusBadge status={item.health_status} /></td>
                    <td>{item.summary.pod_count}</td>
                    <td>{item.summary.abnormal_pod_count}</td>
                    <td>
                      <div className="batch-category-list batch-category-list-inline">
                        {item.summary.abnormal_categories.length > 0 ? (
                          item.summary.abnormal_categories.map((category) => (
                            <span key={`${item.summary.name}-${category}`} className="batch-category-chip">
                              {abnormalCategoryLabel(category)}
                            </span>
                          ))
                        ) : (
                          <span className="batch-category-chip batch-category-chip-muted">无</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <button type="button" className="mini-button" onClick={() => handleViewEvidence(item)} disabled={item.health_status === "error"}>
                        查看证据
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
      {evidenceTarget ? (
        <NamespaceEvidenceDrawer
          item={evidenceTarget}
          data={evidenceInspection.data}
          loading={evidenceInspection.loading}
          error={evidenceInspection.error}
          onClose={handleCloseEvidence}
          ignoredLogKeys={ignoredLogKeys}
          ignoringLogKeys={ignoringLogKeys}
          ignoreMessage={ignoreMessage}
          ignoreDraft={ignoreDraft}
          onRequestIgnore={handleRequestIgnore}
          onCancelIgnore={handleCancelIgnore}
          onChangeIgnoreDraft={(draft) => setIgnoreDraft(draft)}
          onConfirmIgnore={handleConfirmIgnore}
        />
      ) : null}
      {diagnosisOpen ? (
        <div className="evidence-drawer-backdrop" role="presentation" onMouseDown={handleCloseDiagnosis}>
          <aside className="evidence-drawer" aria-label="模板匹配结果" onMouseDown={(event) => event.stopPropagation()}>
            <div className="section-header">
              <div>
                <p className="eyebrow">模板匹配</p>
                <h3>故障模板手动匹配</h3>
                <p className="inline-note">按模板自身绑定的名称空间与对象组执行检查，帮助判断当前异常是否属于已知故障。</p>
              </div>
              <button type="button" onClick={handleCloseDiagnosis}>关闭</button>
            </div>
            <DiagnosisResultPanel
              data={diagnosis.data}
              loading={diagnosis.loading}
              error={diagnosis.error}
              idleMessage="点击运行后显示模板匹配结果。"
              title="模板匹配结果"
            />
          </aside>
        </div>
      ) : null}
    </section>
  );
}
