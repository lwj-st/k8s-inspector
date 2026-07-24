import { useMemo, useState } from "react";
import type { ReactNode } from "react";

import type { KeywordHitSeverity, KeywordRule, Whitelist } from "../api/types";
import { StatusBadge } from "../components/StatusBadge";
import { useDiscoverNamespaceLabels } from "../features/inspections/useDiscoverNamespaceLabels";
import { useDiscoverNamespaces } from "../features/inspections/useDiscoverNamespaces";
import { useKeywords } from "../features/whitelists/useKeywords";
import { useWhitelists } from "../features/whitelists/useWhitelists";

type KeywordModalType = "create" | "edit" | "import" | "export" | null;
type WhitelistModalType = "create" | "edit" | "import" | "export" | null;
type ActiveTab = "keywords" | "whitelists";

function formatJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function severityLabel(severity: KeywordHitSeverity) {
  if (severity === "critical") {
    return "严重";
  }
  if (severity === "error") {
    return "高";
  }
  if (severity === "warning") {
    return "中";
  }
  return "提示";
}

function builtinLabel(item: KeywordRule) {
  return item.builtin ? "内置" : "自定义";
}

function describeWhitelistScope(item: Whitelist) {
  const parts = [item.namespace];
  if (item.label_selector) {
    parts.push(item.label_selector);
  }
  if (item.container_name) {
    parts.push(`容器 ${item.container_name}`);
  }
  return parts.join(" / ");
}

function ToggleBadge({ enabled }: { enabled: boolean }) {
  return <span className={`status-badge ${enabled ? "status-toggle-enabled" : "status-neutral"}`}>{enabled ? "启用" : "停用"}</span>;
}

function ModalShell({
  title,
  note,
  children,
  onClose,
}: {
  title: string;
  note: string;
  children: ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal-card modal-card-polished" role="dialog" aria-modal="true" aria-label={title}>
        <div className="section-header">
          <div>
            <h3>{title}</h3>
            <p className="inline-note">{note}</p>
          </div>
          <button type="button" className="mini-button" onClick={onClose}>关闭</button>
        </div>
        {children}
      </section>
    </div>
  );
}

export function WhitelistsPage() {
  const {
    data: keywords,
    loading: keywordsLoading,
    saving: keywordSaving,
    error: keywordError,
    create: createKeyword,
    update: updateKeyword,
    remove: removeKeyword,
    setEnabled: setKeywordEnabled,
    exportAll: exportKeywords,
    importAll: importKeywords,
  } = useKeywords();
  const {
    data: whitelists,
    loading: whitelistsLoading,
    saving: whitelistSaving,
    error: whitelistError,
    create: createWhitelist,
    update: updateWhitelist,
    remove: removeWhitelist,
    setEnabled: setWhitelistEnabled,
    exportAll: exportWhitelists,
    importAll: importWhitelists,
  } = useWhitelists();
  const { data: namespaceDiscovery } = useDiscoverNamespaces();

  const [activeTab, setActiveTab] = useState<ActiveTab>("keywords");
  const [keywordEditingId, setKeywordEditingId] = useState<number | null>(null);
  const [keywordModalType, setKeywordModalType] = useState<KeywordModalType>(null);
  const [keyword, setKeyword] = useState("");
  const [category, setCategory] = useState("application");
  const [severity, setSeverity] = useState<KeywordHitSeverity>("warning");
  const [description, setDescription] = useState("");
  const [keywordImportText, setKeywordImportText] = useState("");
  const [keywordExportText, setKeywordExportText] = useState("");
  const [keywordMessage, setKeywordMessage] = useState<string | null>(null);

  const [whitelistEditingId, setWhitelistEditingId] = useState<number | null>(null);
  const [whitelistModalType, setWhitelistModalType] = useState<WhitelistModalType>(null);
  const [namespace, setNamespace] = useState("");
  const [labelSelector, setLabelSelector] = useState("");
  const [podNamePattern, setPodNamePattern] = useState("");
  const [containerName, setContainerName] = useState("");
  const [whitelistKeyword, setWhitelistKeyword] = useState("");
  const [note, setNote] = useState("");
  const [whitelistImportText, setWhitelistImportText] = useState("");
  const [whitelistExportText, setWhitelistExportText] = useState("");
  const [whitelistMessage, setWhitelistMessage] = useState<string | null>(null);
  const { data: labelDiscovery, loading: labelsLoading } = useDiscoverNamespaceLabels(namespace);

  const enabledKeywords = useMemo(() => keywords.filter((item) => item.enabled).length, [keywords]);
  const builtinKeywords = useMemo(() => keywords.filter((item) => item.builtin).length, [keywords]);
  const enabledWhitelists = useMemo(() => whitelists.filter((item) => item.enabled).length, [whitelists]);
  const namespaceOptions = useMemo(() => (namespaceDiscovery?.namespaces ?? []).map((item) => item.name), [namespaceDiscovery]);
  const labelOptions = labelDiscovery?.labels ?? [];
  const keywordOptions = useMemo(() => keywords.map((item) => item.keyword), [keywords]);

  function resetKeywordForm() {
    setKeywordEditingId(null);
    setKeyword("");
    setCategory("application");
    setSeverity("warning");
    setDescription("");
  }

  function resetWhitelistForm() {
    setWhitelistEditingId(null);
    setNamespace("");
    setLabelSelector("");
    setPodNamePattern("");
    setContainerName("");
    setWhitelistKeyword("");
    setNote("");
  }

  function openKeywordCreate() {
    resetKeywordForm();
    setKeywordModalType("create");
  }

  function openWhitelistCreate() {
    resetWhitelistForm();
    setWhitelistModalType("create");
  }

  function startEditKeyword(item: KeywordRule) {
    setKeywordEditingId(item.id);
    setKeyword(item.keyword);
    setCategory(item.category);
    setSeverity(item.severity);
    setDescription(item.description ?? "");
    setKeywordMessage(`正在编辑关键字：${item.keyword}`);
    setKeywordModalType("edit");
  }

  function startEditWhitelist(item: Whitelist) {
    setWhitelistEditingId(item.id);
    setNamespace(item.namespace);
    setLabelSelector(item.label_selector ?? "");
    setPodNamePattern("");
    setContainerName(item.container_name ?? "");
    setWhitelistKeyword(item.keyword);
    setNote(item.note ?? "");
    setWhitelistMessage(`正在编辑白名单：${item.keyword}`);
    setWhitelistModalType("edit");
  }

  function closeKeywordModal() {
    setKeywordModalType(null);
    if (keywordEditingId === null) {
      resetKeywordForm();
    }
  }

  function closeWhitelistModal() {
    setWhitelistModalType(null);
    if (whitelistEditingId === null) {
      resetWhitelistForm();
    }
  }

  async function handleSubmitKeyword() {
    setKeywordMessage(null);
    const payload = {
      keyword,
      category,
      severity,
      description: description || null,
      enabled: true,
      builtin: false,
    };

    if (keywordEditingId !== null) {
      await updateKeyword(keywordEditingId, payload);
      setKeywordMessage("关键字已更新");
    } else {
      await createKeyword(payload);
      setKeywordMessage("关键字已新增");
    }
    resetKeywordForm();
    setKeywordModalType(null);
  }

  async function handleSubmitWhitelist() {
    setWhitelistMessage(null);
    const payload = {
      namespace,
      label_selector: labelSelector || null,
      pod_name_pattern: podNamePattern || null,
      container_name: containerName || null,
      keyword: whitelistKeyword,
      enabled: true,
      note: note || null,
    };

    if (whitelistEditingId !== null) {
      await updateWhitelist(whitelistEditingId, payload);
      setWhitelistMessage("白名单已更新");
    } else {
      await createWhitelist(payload);
      setWhitelistMessage("白名单已新增");
    }
    resetWhitelistForm();
    setWhitelistModalType(null);
  }

  async function handleExportKeywords() {
    const exported = await exportKeywords();
    setKeywordExportText(formatJson(exported));
    setKeywordMessage(`已导出 ${exported.length} 条关键字`);
    setKeywordModalType("export");
  }

  async function handleExportWhitelists() {
    const exported = await exportWhitelists();
    setWhitelistExportText(formatJson(exported));
    setWhitelistMessage(`已导出 ${exported.length} 条白名单`);
    setWhitelistModalType("export");
  }

  async function handleImportKeywords() {
    const imported = await importKeywords(JSON.parse(keywordImportText) as Array<{
      keyword: string;
      category: string;
      severity: KeywordHitSeverity;
      description?: string | null;
      enabled: boolean;
      builtin?: boolean;
    }>);
    setKeywordMessage(`已导入 ${imported.length} 条关键字`);
    setKeywordImportText("");
    setKeywordModalType(null);
  }

  async function handleImportWhitelists() {
    const imported = await importWhitelists(JSON.parse(whitelistImportText) as Array<{
      namespace: string;
      label_selector?: string | null;
      pod_name_pattern?: string | null;
      container_name?: string | null;
      keyword: string;
      enabled: boolean;
      note?: string | null;
    }>);
    setWhitelistMessage(`已导入 ${imported.length} 条白名单`);
    setWhitelistImportText("");
    setWhitelistModalType(null);
  }

  return (
    <section className="page-section">
      <section className="workbench-hero keyword-library-hero">
        <div className="workbench-copy">
          <div>
            <p className="eyebrow">配置说明</p>
            <p className="hero-summary">关键字决定哪些日志算异常，白名单决定哪些命中应忽略。</p>
          </div>
          <div className="template-stepper" role="tablist" aria-label="关键字库标签">
            <button type="button" role="tab" aria-selected={activeTab === "keywords"} className={`template-step-chip${activeTab === "keywords" ? " template-step-chip-active" : ""}`} onClick={() => setActiveTab("keywords")}>
              <span>1</span>关键字
            </button>
            <button type="button" role="tab" aria-selected={activeTab === "whitelists"} className={`template-step-chip${activeTab === "whitelists" ? " template-step-chip-active" : ""}`} onClick={() => setActiveTab("whitelists")}>
              <span>2</span>白名单
            </button>
          </div>
        </div>
        <div className="hero-metric-stack">
          <article className="hero-metric hero-metric-compact">
            <span>启用关键字</span>
            <strong>{enabledKeywords}</strong>
          </article>
          <article className="hero-metric hero-metric-compact">
            <span>内置关键字</span>
            <strong>{builtinKeywords}</strong>
          </article>
          <article className="hero-metric hero-metric-compact">
            <span>启用白名单</span>
            <strong>{enabledWhitelists}</strong>
          </article>
        </div>
      </section>

      {activeTab === "keywords" ? (
        <section className="panel">
          <div className="section-header">
            <div>
              <h3>关键字规则</h3>
              <p className="inline-note">只展示巡检判断必需字段，描述默认省略。</p>
            </div>
            <StatusBadge status={keywordsLoading ? "loading" : "enabled"} />
          </div>
          {keywordError ? <p>操作失败：{keywordError}</p> : null}
          {keywordMessage ? <p className="inline-note">{keywordMessage}</p> : null}
          <div className="secondary-action-row">
            <button type="button" className="mini-button" disabled={keywordSaving} onClick={openKeywordCreate}>新增关键字</button>
            <button type="button" className="mini-button button-success" disabled={keywordSaving} onClick={() => setKeywordModalType("import")}>导入关键字</button>
            <button type="button" className="mini-button button-success" disabled={keywordSaving} onClick={() => void handleExportKeywords()}>导出 JSON</button>
          </div>
          <div className="table-scroll-shell">
            <table className="compact-table" aria-label="关键字规则表">
              <thead>
                <tr>
                  <th>关键字</th>
                  <th>类别</th>
                  <th>严重级别</th>
                  <th>启用状态</th>
                  <th>是否内置</th>
                  <th>说明</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {keywords.map((item) => (
                  <tr key={item.id}>
                    <td>{item.keyword}</td>
                    <td>{item.category}</td>
                    <td>{severityLabel(item.severity)}</td>
                    <td><ToggleBadge enabled={item.enabled} /></td>
                    <td>{builtinLabel(item)}</td>
                    <td className="ellipsis-cell" title={item.description ?? "未填写说明"}>{item.description ?? "未填写说明"}</td>
                    <td>
                      <div className="button-row">
                        <button type="button" className="mini-button" disabled={keywordSaving} onClick={() => startEditKeyword(item)}>编辑</button>
                        <button type="button" className={`mini-button${item.enabled ? " button-danger" : ""}`} disabled={keywordSaving} onClick={() => void setKeywordEnabled(item.id, !item.enabled)}>
                          {item.enabled ? "停用" : "启用"}
                        </button>
                        <button type="button" className="mini-button button-danger" disabled={keywordSaving || item.builtin} onClick={() => void removeKeyword(item.id)}>删除</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : (
        <section className="panel">
          <div className="section-header">
            <div>
              <h3>白名单规则</h3>
              <p className="inline-note">范围与来源说明默认省略，悬停可看全量内容。</p>
            </div>
            <StatusBadge status={whitelistsLoading ? "loading" : "enabled"} />
          </div>
          {whitelistError ? <p>操作失败：{whitelistError}</p> : null}
          {whitelistMessage ? <p className="inline-note">{whitelistMessage}</p> : null}
          <div className="secondary-action-row">
            <button type="button" className="mini-button" disabled={whitelistSaving} onClick={openWhitelistCreate}>新增白名单</button>
            <button type="button" className="mini-button button-success" disabled={whitelistSaving} onClick={() => setWhitelistModalType("import")}>导入白名单</button>
            <button type="button" className="mini-button button-success" disabled={whitelistSaving} onClick={() => void handleExportWhitelists()}>导出 JSON</button>
          </div>
          <div className="table-scroll-shell">
            <table className="compact-table" aria-label="白名单规则表">
              <thead>
                <tr>
                  <th className="whitelist-keyword-column">关键字</th>
                  <th>范围</th>
                  <th>启用状态</th>
                  <th>备注</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {whitelists.map((item) => (
                  <tr key={item.id}>
                    <td className="whitelist-keyword-column" title={item.keyword}>{item.keyword}</td>
                    <td className="ellipsis-cell" title={describeWhitelistScope(item)}>{describeWhitelistScope(item)}</td>
                    <td><ToggleBadge enabled={item.enabled} /></td>
                    <td className="ellipsis-cell" title={item.note ?? "未填写来源说明"}>{item.note ?? "未填写来源说明"}</td>
                    <td>
                      <div className="button-row">
                        <button type="button" className="mini-button" disabled={whitelistSaving} onClick={() => startEditWhitelist(item)}>编辑</button>
                        <button type="button" className={`mini-button${item.enabled ? " button-danger" : ""}`} disabled={whitelistSaving} onClick={() => void setWhitelistEnabled(item.id, !item.enabled)}>
                          {item.enabled ? "停用" : "启用"}
                        </button>
                        <button type="button" className="mini-button button-danger" disabled={whitelistSaving} onClick={() => void removeWhitelist(item.id)}>删除</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {keywordModalType === "create" || keywordModalType === "edit" ? (
        <ModalShell title={keywordModalType === "edit" ? "编辑关键字" : "新增关键字"} note="关键字会直接影响日志命中结果，请明确类别、严重程度和用途说明。" onClose={closeKeywordModal}>
          <div className="entry-form-grid">
            <label className="modal-form-field">
              关键字
              <input className="template-input" aria-label="关键字" value={keyword} onChange={(event) => setKeyword(event.target.value)} />
            </label>
            <label className="modal-form-field">
              类别
              <select className="template-input" aria-label="类别" value={category} onChange={(event) => setCategory(event.target.value)}>
                <option value="application">应用</option>
                <option value="runtime">运行时</option>
                <option value="database">数据库</option>
                <option value="network">网络</option>
                <option value="frontend">前端</option>
                <option value="python">Python</option>
              </select>
            </label>
            <label className="modal-form-field">
              严重级别
              <select className="template-input" aria-label="严重级别" value={severity} onChange={(event) => setSeverity(event.target.value as KeywordHitSeverity)}>
                <option value="info">提示</option>
                <option value="warning">中</option>
                <option value="error">高</option>
                <option value="critical">严重</option>
              </select>
            </label>
            <label className="modal-form-field" style={{ gridColumn: "1 / -1" }}>
              说明
              <input className="template-input" aria-label="说明" value={description} onChange={(event) => setDescription(event.target.value)} />
            </label>
          </div>
          <div className="button-row modal-action-row">
            <button type="button" className="modal-primary-button" disabled={keywordSaving || keyword.trim().length === 0} onClick={() => void handleSubmitKeyword()}>
              {keywordSaving ? "处理中..." : keywordEditingId !== null ? "保存关键字" : "新增关键字"}
            </button>
            <button type="button" className="modal-secondary-button" onClick={closeKeywordModal}>取消</button>
          </div>
        </ModalShell>
      ) : null}

      {keywordModalType === "import" ? (
        <ModalShell title="导入关键字" note="只在迁移配置时使用，JSON 不在主页面长期占位。" onClose={() => setKeywordModalType(null)}>
          <label>
            导入关键字 JSON
            <textarea aria-label="导入关键字 JSON" className="log-block code-block-scroll modal-code-input" value={keywordImportText} onChange={(event) => setKeywordImportText(event.target.value)} rows={10} />
          </label>
          <div className="button-row">
            <button type="button" className="mini-button" disabled={keywordSaving || keywordImportText.trim().length === 0} onClick={() => void handleImportKeywords()}>导入关键字</button>
            <button type="button" className="mini-button" onClick={() => setKeywordModalType(null)}>取消</button>
          </div>
        </ModalShell>
      ) : null}

      {keywordModalType === "export" ? (
        <ModalShell title="导出关键字" note="导出结果只用于跨环境迁移。" onClose={() => setKeywordModalType(null)}>
          <label>
            已导出 JSON
            <textarea aria-label="已导出 JSON" className="log-block code-block-scroll modal-code-input" value={keywordExportText} readOnly rows={12} />
          </label>
          <div className="button-row">
            <button type="button" className="mini-button" onClick={() => setKeywordModalType(null)}>关闭</button>
          </div>
        </ModalShell>
      ) : null}

      {whitelistModalType === "create" || whitelistModalType === "edit" ? (
        <ModalShell title={whitelistModalType === "edit" ? "编辑白名单" : "新增白名单"} note="白名单按名称空间和 Label Selector 生效，不绑定 Pod 名称；Pod 重启换名后仍可复用。" onClose={closeWhitelistModal}>
          <div className="entry-form-grid">
            <label className="modal-form-field">
              名称空间
              <select className="template-input" aria-label="名称空间" value={namespace} onChange={(event) => setNamespace(event.target.value)}>
                <option value="">请选择名称空间</option>
                {namespace && !namespaceOptions.includes(namespace) ? <option value={namespace}>{namespace}</option> : null}
                {namespaceOptions.map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
            </label>
            <label className="modal-form-field">
              Label Selector
              <select className="template-input" aria-label="Label Selector" value={labelSelector} onChange={(event) => setLabelSelector(event.target.value)} disabled={!namespace}>
                <option value="">{labelsLoading ? "正在发现标签..." : "不限 Label"}</option>
                {labelSelector && !labelOptions.some((item) => item.selector === labelSelector) ? <option value={labelSelector}>{labelSelector}</option> : null}
                {labelOptions.map((item) => (
                  <option key={item.selector} value={item.selector}>{item.selector}（{item.pod_count} 个 Pod）</option>
                ))}
              </select>
            </label>
            <label className="modal-form-field">
              容器名称
              <input className="template-input" aria-label="容器名称" value={containerName} onChange={(event) => setContainerName(event.target.value)} placeholder="可选，例如 worker" />
            </label>
            <label className="modal-form-field">
              白名单关键字
              <input
                className="template-input"
                aria-label="白名单关键字"
                list="whitelist-keyword-options"
                value={whitelistKeyword}
                onChange={(event) => setWhitelistKeyword(event.target.value)}
                placeholder="可选择关键字，也可粘贴完整误报日志片段"
              />
              <datalist id="whitelist-keyword-options">
                {keywordOptions.map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </datalist>
            </label>
            <label className="modal-form-field" style={{ gridColumn: "1 / -1" }}>
              备注
              <input className="template-input" aria-label="备注" value={note} onChange={(event) => setNote(event.target.value)} placeholder="例如：来自巡检误报，启动预热阶段忽略" />
            </label>
          </div>
          <div className="button-row modal-action-row">
            <button type="button" className="modal-primary-button" disabled={whitelistSaving || namespace.trim().length === 0 || whitelistKeyword.trim().length === 0} onClick={() => void handleSubmitWhitelist()}>
              {whitelistSaving ? "处理中..." : whitelistEditingId !== null ? "保存白名单" : "新增白名单"}
            </button>
            <button type="button" className="modal-secondary-button" onClick={closeWhitelistModal}>取消</button>
          </div>
        </ModalShell>
      ) : null}

      {whitelistModalType === "import" ? (
        <ModalShell title="导入白名单" note="只在迁移配置时使用，JSON 不在主页面长期占位。" onClose={() => setWhitelistModalType(null)}>
          <label>
            导入白名单 JSON
            <textarea aria-label="导入白名单 JSON" className="log-block code-block-scroll modal-code-input" value={whitelistImportText} onChange={(event) => setWhitelistImportText(event.target.value)} rows={10} />
          </label>
          <div className="button-row">
            <button type="button" className="mini-button" disabled={whitelistSaving || whitelistImportText.trim().length === 0} onClick={() => void handleImportWhitelists()}>导入白名单</button>
            <button type="button" className="mini-button" onClick={() => setWhitelistModalType(null)}>取消</button>
          </div>
        </ModalShell>
      ) : null}

      {whitelistModalType === "export" ? (
        <ModalShell title="导出白名单" note="导出结果只用于跨环境迁移。" onClose={() => setWhitelistModalType(null)}>
          <label>
            已导出 JSON
            <textarea aria-label="已导出 JSON" className="log-block code-block-scroll modal-code-input" value={whitelistExportText} readOnly rows={12} />
          </label>
          <div className="button-row">
            <button type="button" className="mini-button" onClick={() => setWhitelistModalType(null)}>关闭</button>
          </div>
        </ModalShell>
      ) : null}
    </section>
  );
}
