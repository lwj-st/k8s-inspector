import { useMemo, useState } from "react";

import { exportImages, listImages } from "../api/client";
import type { ImageInventoryItem, ImageInventoryResponse } from "../api/types";
import { useDiscoverNamespaces } from "../features/inspections/useDiscoverNamespaces";

function formatDateTime(value?: string | null) {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function containerTypeLabel(value: string) {
  return value === "init" ? "初始化容器" : "运行容器";
}

function sourceLabel(value: string) {
  if (value === "imageID") {
    return "imageID";
  }
  return value === "status" ? "status" : "spec";
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function ImageInventoryPage() {
  const { data: namespaceDiscovery, loading: namespacesLoading, error: namespacesError, refresh } = useDiscoverNamespaces();
  const [namespaceInput, setNamespaceInput] = useState("");
  const [selectedNamespaces, setSelectedNamespaces] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [inventory, setInventory] = useState<ImageInventoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [selectedImage, setSelectedImage] = useState<ImageInventoryItem | null>(null);

  const namespaceOptions = useMemo(
    () => (namespaceDiscovery?.namespaces ?? []).map((item) => item.name),
    [namespaceDiscovery],
  );
  const availableNamespaceOptions = namespaceOptions.filter((item) => !selectedNamespaces.includes(item));
  const canQuery = selectedNamespaces.length > 0;

  function addNamespace() {
    if (!namespaceInput || selectedNamespaces.includes(namespaceInput)) {
      return;
    }
    setSelectedNamespaces((current) => [...current, namespaceInput]);
    setNamespaceInput("");
    setMessage(null);
  }

  function removeNamespace(namespace: string) {
    setSelectedNamespaces((current) => current.filter((item) => item !== namespace));
    setInventory(null);
    if (selectedImage?.references.some((ref) => ref.namespace === namespace)) {
      setSelectedImage(null);
    }
  }

  async function handleQuery() {
    if (!canQuery) {
      setError("请选择名称空间后查看镜像清单");
      return;
    }
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const result = await listImages({ namespaces: selectedNamespaces, search });
      setInventory(result);
      setSelectedImage(null);
      if (result.items.length === 0) {
        setMessage("所选名称空间下没有匹配的可见 Pod 镜像。");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "镜像清单查询失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleExport() {
    if (!canQuery) {
      setError("未选择名称空间时不能导出镜像清单");
      return;
    }
    setExporting(true);
    setError(null);
    setMessage(null);
    try {
      const result = await exportImages({ namespaces: selectedNamespaces, search });
      downloadBlob(result.blob, result.filename ?? "k8s-inspector-images.txt");
      setMessage("镜像清单已导出。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "镜像清单导出失败，请稍后重试或查看后端日志");
    } finally {
      setExporting(false);
    }
  }

  async function copyImage(image: string) {
    setMessage(null);
    setError(null);
    try {
      await navigator.clipboard.writeText(image);
      setMessage("镜像地址已复制。");
    } catch {
      setError("复制失败，请手动选择镜像地址。");
    }
  }

  return (
    <section className="page-stack image-inventory-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">资源查看</p>
          <h2>镜像清单</h2>
          <p className="page-description">按名称空间查看 Kubernetes API 可见 Pod 引用的镜像。</p>
        </div>
      </div>

      <section className="panel-card">
        <div className="section-header">
          <div>
            <h3>筛选条件</h3>
            <p className="inline-note">至少选择一个名称空间后再查询，不会自动读取全集群。</p>
          </div>
          {namespacesError ? (
            <button type="button" className="modal-secondary-button" onClick={() => void refresh().catch(() => undefined)}>
              重试
            </button>
          ) : null}
        </div>
        <div className="image-filter-grid">
          <label>
            <span>名称空间</span>
            <select
              aria-label="选择名称空间"
              value={namespaceInput}
              disabled={namespacesLoading || availableNamespaceOptions.length === 0}
              onChange={(event) => setNamespaceInput(event.target.value)}
            >
              <option value="">{namespacesLoading ? "正在加载名称空间" : "选择名称空间"}</option>
              {availableNamespaceOptions.map((namespace) => (
                <option key={namespace} value={namespace}>{namespace}</option>
              ))}
            </select>
          </label>
          <button type="button" className="primary-button" disabled={!namespaceInput} onClick={addNamespace}>
            添加
          </button>
          <label>
            <span>镜像关键字</span>
            <input
              aria-label="搜索镜像关键字"
              value={search}
              placeholder="registry / repository / tag / digest"
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <button type="button" className="primary-button" disabled={!canQuery || loading} onClick={() => void handleQuery()}>
            {loading ? "查询中" : "查询"}
          </button>
          <button type="button" className="modal-secondary-button" disabled={exporting} onClick={() => void handleExport()}>
            {exporting ? "导出中" : "导出 TXT"}
          </button>
        </div>
        <div className="selected-chip-row" aria-label="已选择名称空间">
          {selectedNamespaces.length > 0 ? selectedNamespaces.map((namespace) => (
            <span className="selected-chip" key={namespace}>
              {namespace}
              <button type="button" aria-label={`移除 ${namespace}`} onClick={() => removeNamespace(namespace)}>x</button>
            </span>
          )) : <span className="empty-copy">请选择名称空间后查看镜像清单</span>}
        </div>
        {namespacesError ? <p className="form-error">名称空间读取失败：{namespacesError}</p> : null}
        {error ? <p className="form-error">{error}</p> : null}
        {message ? <p className="form-success">{message}</p> : null}
      </section>

      {inventory ? (
        <>
          <div className="summary-card-grid">
            <div className="summary-card"><span>镜像数</span><strong>{inventory.summary.image_count}</strong></div>
            <div className="summary-card"><span>名称空间数</span><strong>{inventory.summary.namespace_count}</strong></div>
            <div className="summary-card"><span>Pod 数</span><strong>{inventory.summary.pod_count}</strong></div>
            <div className="summary-card"><span>容器数</span><strong>{inventory.summary.container_count}</strong></div>
          </div>
          {inventory.simulated ? <p className="inline-note">当前为 Mock Provider 模拟数据。</p> : null}
          <section className="panel-card">
            <div className="section-header">
              <div>
                <h3>镜像列表</h3>
                <p className="inline-note">共 {inventory.items.length} 个镜像。</p>
              </div>
            </div>
            {inventory.items.length === 0 ? (
              <div className="empty-state"><strong>所选名称空间下没有可见 Pod 镜像。</strong></div>
            ) : (
              <div className="table-scroll-shell">
                <table className="data-table image-inventory-table">
                  <thead>
                    <tr>
                      <th>镜像</th>
                      <th>名称空间</th>
                      <th>Pod</th>
                      <th>容器</th>
                      <th>最近创建</th>
                      <th>最近状态</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {inventory.items.map((item) => (
                      <tr key={item.image}>
                        <td>
                          <div className="copyable-cell">
                            <code title={item.image}>{item.image}</code>
                            <button type="button" className="copy-button" onClick={() => void copyImage(item.image)}>复制</button>
                          </div>
                        </td>
                        <td>{item.namespace_count}</td>
                        <td>{item.pod_count}</td>
                        <td>{item.container_count}</td>
                        <td>{formatDateTime(item.latest_pod_created_at)}</td>
                        <td>{item.latest_pod_phase ?? "-"}</td>
                        <td>
                          <button type="button" className="modal-secondary-button" onClick={() => setSelectedImage(item)}>
                            详情
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      ) : (
        <div className="empty-state"><strong>请选择名称空间后查看镜像清单</strong></div>
      )}

      {selectedImage ? (
        <div className="modal-backdrop" role="presentation">
          <section className="modal-card modal-card-polished image-detail-modal" role="dialog" aria-modal="true" aria-label="镜像引用详情">
            <div className="section-header">
              <div>
                <h3>镜像引用详情</h3>
                <p className="inline-note">{selectedImage.image}</p>
              </div>
              <button type="button" className="modal-secondary-button" onClick={() => setSelectedImage(null)}>关闭</button>
            </div>
            <div className="table-scroll-shell">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>名称空间</th>
                    <th>Pod</th>
                    <th>Pod 阶段</th>
                    <th>容器</th>
                    <th>容器类型</th>
                    <th>来源</th>
                    <th>imageID</th>
                    <th>Pod 创建时间</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedImage.references.map((ref, index) => (
                    <tr key={`${ref.namespace}-${ref.pod_name}-${ref.container_name}-${ref.source}-${index}`}>
                      <td>{ref.namespace}</td>
                      <td>{ref.pod_name}</td>
                      <td>{ref.pod_phase}</td>
                      <td>{ref.container_name}</td>
                      <td>{containerTypeLabel(ref.container_type)}</td>
                      <td>{sourceLabel(ref.source)}</td>
                      <td><code title={ref.image_id ?? ""}>{ref.image_id ?? "-"}</code></td>
                      <td>{formatDateTime(ref.pod_created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}
