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
import { useRunNamespaceInspection } from "../features/inspections/useRunNamespaceInspection";

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

function batchSectionTitle(status: "error" | "warning" | "healthy") {
  if (status === "error") {
    return "巡检失败";
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
  return hit.context_text?.trim() || hit.matched_text;
}

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
          {pod.log_hits.length > 0 ? (
            <ul className="plain-list">
              {pod.log_hits.map((hit) => {
                const hitKey = buildLogHitKey(pod.name, hit);
                const isIgnored = hit.whitelisted || ignoredLogKeys.includes(hitKey);
                const isIgnoring = ignoringLogKeys.includes(hitKey);

                return (
                  <li key={hitKey}>
                    <div>{hit.keyword}</div>
                    <span className="inline-note">命中上下文（不是完整日志）</span>
                    <pre className="log-block code-block-scroll">{logHitContext(hit)}</pre>
                    <div className="button-row">
                      <button
                        type="button"
                        disabled={isIgnored || isIgnoring}
                        onClick={() => onRequestIgnore(pod, hit)}
                      >
                        {isIgnored ? "已忽略" : isIgnoring ? "处理中..." : "忽略此命中"}
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
  ignoreTarget,
  onRequestIgnore,
  onCancelIgnore,
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
  ignoreTarget: { pod: InspectedPod; hit: KeywordHit } | null;
  onRequestIgnore: (pod: InspectedPod, hit: KeywordHit) => void;
  onCancelIgnore: () => void;
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
            <div>
              <h4>结论</h4>
              <p className="inline-note">先看名称空间结论，再决定是否下钻到 Pod 和日志证据。</p>
            </div>
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
                <div>
                  <h4>证据</h4>
                  <p className="inline-note">异常 Pod、关键字命中和名称空间级对象异常都会在这里展开。</p>
                </div>
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
              {ignoreTarget ? (
                <section className="panel panel-muted evidence-nested-panel" aria-label="忽略关键字命中确认">
                  <div className="section-header">
                    <h4>确认忽略此命中</h4>
                    <span className="section-tip">忽略后，当前范围的相同命中会加入白名单</span>
                  </div>
                  <KeyValueList
                    items={[
                      { label: "名称空间", value: namespace },
                      { label: "Label Selector", value: data?.inspection_target.label_selector ?? item.detail_target.label_selector ?? "未设置" },
                      { label: "Pod", value: ignoreTarget.pod.name },
                      { label: "容器", value: ignoreTarget.hit.container_name ?? "未区分容器" },
                      { label: "关键字", value: ignoreTarget.hit.keyword },
                    ]}
                  />
                  <div className="button-row">
                    <button type="button" onClick={onConfirmIgnore}>
                      确认忽略
                    </button>
                    <button type="button" onClick={onCancelIgnore}>
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
  const [ignoreTarget, setIgnoreTarget] = useState<{ pod: InspectedPod; hit: KeywordHit } | null>(null);
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
    setIgnoreTarget(null);
    setEvidenceTarget(item);
    void evidenceInspection.submit(item.detail_target.namespace ?? item.summary.name, item.detail_target.label_selector ?? null);
  }

  function handleCloseEvidence() {
    setEvidenceTarget(null);
    setIgnoreTarget(null);
    setIgnoreMessage(null);
    setIgnoredLogKeys([]);
    setIgnoringLogKeys([]);
  }

  function handleRequestIgnore(pod: InspectedPod, hit: KeywordHit) {
    setIgnoreMessage(null);
    setIgnoreTarget({ pod, hit });
  }

  function handleCancelIgnore() {
    setIgnoreTarget(null);
  }

  async function handleConfirmIgnore() {
    if (!evidenceTarget || !ignoreTarget) {
      return;
    }

    const hitKey = buildLogHitKey(ignoreTarget.pod.name, ignoreTarget.hit);
    setIgnoringLogKeys((current) => [...current, hitKey]);
    setIgnoreMessage(null);

    try {
      await ignoreWhitelistLogHit({
        namespace: evidenceInspection.data?.namespace ?? evidenceTarget.detail_target.namespace ?? evidenceTarget.summary.name,
        label_selector: evidenceInspection.data?.inspection_target.label_selector ?? evidenceTarget.detail_target.label_selector ?? null,
        pod_name_pattern: ignoreTarget.pod.name,
        container_name: ignoreTarget.hit.container_name ?? null,
        keyword: ignoreTarget.hit.keyword,
        note: "自动巡检证据抽屉忽略",
      });
      setIgnoredLogKeys((current) => [...current, hitKey]);
      setIgnoreMessage("已加入白名单，后续相同范围的该命中会自动忽略");
      setIgnoreTarget(null);
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
  const groupedBatchResultsSource: Array<{
    status: "error" | "warning" | "healthy";
    items: NamespaceBatchInspectionResult[];
  }> = [
    { status: "error", items: sortedBatchResults.filter((item) => item.health_status === "error") },
    { status: "warning", items: sortedBatchResults.filter((item) => item.health_status === "warning") },
    { status: "healthy", items: sortedBatchResults.filter((item) => item.health_status === "healthy") },
  ];
  const groupedBatchResults = groupedBatchResultsSource.filter((group) => group.items.length > 0);
  const batchGuidance =
    errorBatchCount > 0
      ? "先处理巡检失败的名称空间，再进入告警名称空间查看证据。"
      : warningBatchCount > 0
        ? "先打开告警名称空间证据，确认是 Pod、事件还是日志关键字导致告警。"
          : batchResults.length > 0
            ? "本轮没有发现异常名称空间；如需判断是否属于已知故障，可继续运行模板匹配。"
          : "可直接巡检全部名称空间，或先搜索并选择一个名称空间后再执行。";

  return (
    <section className="page-section">
      <header className="section-header">
        <div>
            <p className="eyebrow">状态工作台</p>
            <h2>状态巡检</h2>
        </div>
        <StatusBadge status="info" />
      </header>

      <section className="workbench-hero">
        <div className="workbench-copy">
          <div className="section-header">
            <div>
              <h3>名称空间</h3>
            </div>
          </div>
          <div className="workbench-command-panel status-command-panel">
            <label className="inline-search">
              搜索名称空间
              <input
                aria-label="搜索名称空间"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="例如：prod、kube-system"
              />
            </label>
            <label className="inline-search">
              选择名称空间
              <select
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
          <section className="panel panel-muted batch-summary-overview">
            <div className="batch-summary-metrics">
              <article className="hero-metric hero-metric-compact batch-summary-metric">
                <span>巡检名称空间</span>
                <strong>{batchResults.length}</strong>
              </article>
              <article className="hero-metric hero-metric-compact batch-summary-metric batch-summary-metric-warning">
                <span>告警名称空间</span>
                <strong>{warningBatchCount}</strong>
              </article>
              <article className="hero-metric hero-metric-compact batch-summary-metric batch-summary-metric-error">
                <span>失败名称空间</span>
                <strong>{errorBatchCount}</strong>
              </article>
              <article className="hero-metric hero-metric-compact batch-summary-metric batch-summary-metric-healthy">
                <span>正常名称空间</span>
                <strong>{healthyBatchCount}</strong>
              </article>
            </div>
            <article className="quick-action-card batch-guidance-card">
              <strong>下一步建议</strong>
              <span>{batchGuidance}</span>
            </article>
          </section>
          <div className="batch-group-stack">
            {groupedBatchResults.map((group) => (
              <section key={group.status} className="batch-group-section">
                <div className="section-header">
                  <div>
                    <h4>{batchSectionTitle(group.status)}</h4>
                    <p className="inline-note">共 {group.items.length} 个名称空间</p>
                  </div>
                  <StatusBadge status={group.status} />
                </div>
                <div className="card-grid batch-group-scroll">
                  {group.items.map((item) => (
                    <article
                      key={item.summary.name}
                      aria-label={`批量结果 ${item.summary.name}`}
                      className={`card batch-summary-card${item.health_status === "error" ? " batch-card-error" : item.health_status === "healthy" ? " batch-card-quiet" : item.health_status === "warning" ? " batch-card-warning" : ""}`}
                    >
                      <div className="card-title">
                        <div>
                          <strong>{item.summary.name}</strong>
                          <p className="inline-note">
                            Pod {item.summary.pod_count} / 异常 Pod {item.summary.abnormal_pod_count}
                          </p>
                        </div>
                        <StatusBadge status={item.health_status} />
                      </div>
                      {item.health_status === "error" ? <p>该名称空间巡检失败</p> : null}
                      <div className="batch-summary-stats">
                        <p>Pod 总数：{item.summary.pod_count}</p>
                        <p>异常 Pod：{item.summary.abnormal_pod_count}</p>
                      </div>
                      <div className="batch-category-block">
                        <span className="inline-note">异常分类</span>
                        <div className="batch-category-list">
                          {item.summary.abnormal_categories.length > 0 ? (
                            item.summary.abnormal_categories.map((category) => (
                              <span key={`${item.summary.name}-${category}`} className="batch-category-chip">
                                {abnormalCategoryLabel(category)}
                              </span>
                            ))
                          ) : (
                            <span className="batch-category-chip batch-category-chip-muted">无异常分类</span>
                          )}
                        </div>
                      </div>
                      <button type="button" onClick={() => handleViewEvidence(item)} disabled={item.health_status === "error"}>
                        查看证据
                      </button>
                    </article>
                  ))}
                </div>
              </section>
            ))}
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
          ignoreTarget={ignoreTarget}
          onRequestIgnore={handleRequestIgnore}
          onCancelIgnore={handleCancelIgnore}
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
