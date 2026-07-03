import { useState } from "react";

import { KeyValueList } from "../components/KeyValueList";
import { StatusBadge } from "../components/StatusBadge";
import { useRunNamespaceInspection } from "../features/inspections/useRunNamespaceInspection";

export function NamespaceInspectionPage() {
  const [namespace, setNamespace] = useState("demo");
  const [labelSelector, setLabelSelector] = useState("app=demo");
  const [selectedPodName, setSelectedPodName] = useState<string | null>(null);
  const { data, loading, error, submit } = useRunNamespaceInspection();
  const selectedPod =
    data?.pods.find((pod) => pod.name === selectedPodName) ??
    data?.pods[0] ??
    null;

  return (
    <section className="page-section">
      <h2>命名空间巡检</h2>
      <form
        className="panel"
        onSubmit={(event) => {
          event.preventDefault();
          void submit(namespace, labelSelector).then(() => setSelectedPodName(null));
        }}
      >
        <label>
          Namespace
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
              { label: "Pod 数量", value: String(data.pods.length) },
              { label: "巡检状态", value: data.health_status },
            ]}
          />
          <div className="inspection-layout">
            <div className="panel">
              <div className="section-header">
                <h3>Pod 列表</h3>
              </div>
              <div className="pod-list">
                {data.pods.map((pod) => {
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
                    <pre className="log-block">{selectedPod.log_summary ?? "无日志摘要"}</pre>
                  </article>
                </div>
              ) : (
                <p>暂无 Pod 证据</p>
              )}
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}
