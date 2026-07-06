import { useState } from "react";

import { KeyValueList } from "../components/KeyValueList";
import { StatusBadge } from "../components/StatusBadge";
import { useRunNamespaceInspection } from "../features/inspections/useRunNamespaceInspection";

const quickTargets = [
  { name: "demo-api", namespace: "demo", labelSelector: "app=demo-api", description: "常看 API Pod 和启动异常" },
  { name: "demo-worker", namespace: "demo", labelSelector: "app=demo-worker", description: "适合排查异步任务堆积和重启" },
  { name: "entire-namespace", namespace: "demo", labelSelector: "", description: "直接巡检整个名称空间" },
] as const;

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
  const [namespace, setNamespace] = useState("demo");
  const [labelSelector, setLabelSelector] = useState("app=demo");
  const [selectedPodName, setSelectedPodName] = useState<string | null>(null);
  const [ignoredLogKeys, setIgnoredLogKeys] = useState<string[]>([]);
  const { data, loading, error, submit } = useRunNamespaceInspection();
  const sortedPods = data ? sortPods(data.pods) : [];
  const selectedPod =
    sortedPods.find((pod) => pod.name === selectedPodName) ??
    sortedPods[0] ??
    null;
  const abnormalPods = sortedPods.filter((pod) => !isHealthyStatus(pod.status));
  const healthyPods = sortedPods.filter((pod) => isHealthyStatus(pod.status));
  const logHits = (selectedPod?.log_summary ?? "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  function applyQuickTarget(target: (typeof quickTargets)[number]) {
    setNamespace(target.namespace);
    setLabelSelector(target.labelSelector);
    void submit(target.namespace, target.labelSelector).then(() => {
      setSelectedPodName(null);
      setIgnoredLogKeys([]);
    });
  }

  return (
    <section className="page-section">
      <header className="section-header">
        <div>
          <p className="eyebrow">Namespace Inspection</p>
          <h2>命名空间巡检</h2>
        </div>
        {data ? <StatusBadge status={data.health_status} /> : null}
      </header>
      <section className="panel panel-muted">
        <div className="section-header">
          <h3>常用巡检对象</h3>
          <span className="section-tip">先用常用对象，减少重复输入</span>
        </div>
        <div className="quick-target-grid">
          {quickTargets.map((target) => (
            <button
              key={target.name}
              type="button"
              className="quick-target-card"
              onClick={() => applyQuickTarget(target)}
              disabled={loading}
            >
              <strong>使用 {target.name}</strong>
              <span>{target.namespace}{target.labelSelector ? ` / ${target.labelSelector}` : " / 全名称空间"}</span>
              <small>{target.description}</small>
            </button>
          ))}
        </div>
      </section>
      <form
        className="panel"
        onSubmit={(event) => {
          event.preventDefault();
          void submit(namespace, labelSelector).then(() => {
            setSelectedPodName(null);
            setIgnoredLogKeys([]);
          });
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
                    <strong>日志摘要</strong>
                    {logHits.length > 0 ? (
                      <div className="log-hit-list">
                        {logHits.map((hit) => {
                          const ignored = ignoredLogKeys.includes(`${selectedPod.name}:${hit}`);
                          return (
                            <article key={`${selectedPod.name}:${hit}`} className={`log-hit-card${ignored ? " log-hit-card-muted" : ""}`}>
                              <pre className="log-block">{hit}</pre>
                              <div className="log-hit-actions">
                                <button
                                  type="button"
                                  onClick={() =>
                                    setIgnoredLogKeys((current) => [...current, `${selectedPod.name}:${hit}`])
                                  }
                                  disabled={ignored}
                                >
                                  {ignored ? "已忽略" : "忽略此报错"}
                                </button>
                              </div>
                              {ignored ? <p className="inline-note">已在本次会话中忽略该日志命中</p> : null}
                            </article>
                          );
                        })}
                      </div>
                    ) : (
                      <pre className="log-block">无日志摘要</pre>
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
