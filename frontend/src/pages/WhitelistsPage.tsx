import { useMemo, useState } from "react";

import type { KeywordHitSeverity, KeywordRule, Whitelist } from "../api/types";
import { StatusBadge } from "../components/StatusBadge";
import { useKeywords } from "../features/whitelists/useKeywords";
import { useWhitelists } from "../features/whitelists/useWhitelists";

type KeywordModalType = "create" | "edit" | "import" | "export" | null;
type WhitelistModalType = "create" | "edit" | "import" | "export" | null;

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

function describeWhitelistScope(item: Whitelist) {
  const parts = [item.namespace];
  if (item.label_selector) {
    parts.push(item.label_selector);
  }
  if (item.pod_name_pattern) {
    parts.push(`Pod ${item.pod_name_pattern}`);
  }
  if (item.container_name) {
    parts.push(`容器 ${item.container_name}`);
  }
  return parts.join(" / ");
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

  const enabledKeywords = useMemo(() => keywords.filter((item) => item.enabled).length, [keywords]);
  const builtinKeywords = useMemo(() => keywords.filter((item) => item.builtin).length, [keywords]);
  const enabledWhitelists = useMemo(() => whitelists.filter((item) => item.enabled).length, [whitelists]);

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
    setPodNamePattern(item.pod_name_pattern ?? "");
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
      <header className="section-header">
        <div>
          <p className="eyebrow">规则中心</p>
          <h2>关键字库与白名单</h2>
        </div>
        <span className="section-tip">让运维能看清楚哪些规则会判异常，哪些报错会被忽略。</span>
      </header>

      <section className="workbench-hero">
        <div className="workbench-copy">
          <div>
            <p className="eyebrow">配置说明</p>
            <p className="hero-summary">关键字库负责定义哪些日志算异常，白名单负责记录哪些命中应忽略。导入导出只用于跨环境迁移，默认不占主页面。</p>
          </div>
          <div className="secondary-action-row">
            <button type="button" className="text-button" onClick={openKeywordCreate}>新增关键字</button>
            <button type="button" className="text-button" onClick={openWhitelistCreate}>新增白名单</button>
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

      <div className="card-grid card-grid-wide">
        <section className="panel">
          <div className="section-header">
            <div>
              <h3>关键字库</h3>
              <p className="inline-note">突出启用状态、严重程度、匹配关键字和用途说明。</p>
            </div>
            <StatusBadge status={keywordsLoading ? "loading" : "enabled"} />
          </div>
          {keywordError ? <p>操作失败：{keywordError}</p> : null}
          {keywordMessage ? <p className="inline-note">{keywordMessage}</p> : null}
          <div className="secondary-action-row">
            <button type="button" className="text-button" disabled={keywordSaving} onClick={openKeywordCreate}>新增关键字</button>
            <button type="button" className="text-button" disabled={keywordSaving} onClick={() => setKeywordModalType("import")}>导入关键字</button>
            <button type="button" className="text-button" disabled={keywordSaving} onClick={() => void handleExportKeywords()}>导出 JSON</button>
          </div>
          <div className="stack-list">
            {keywords.map((item) => (
              <article key={item.id} className="card">
                <div className="card-title">
                  <strong>{item.keyword}</strong>
                  <StatusBadge status={item.enabled ? item.severity : "disabled"} />
                </div>
                <p>{item.category} / {item.description ?? "未填写说明"}</p>
                <p className="inline-note">严重程度：{severityLabel(item.severity)}{item.builtin ? " / 系统内置" : " / 自定义规则"}</p>
                <div className="button-row">
                  <button type="button" disabled={keywordSaving} onClick={() => startEditKeyword(item)}>编辑</button>
                  <button type="button" disabled={keywordSaving || item.builtin} onClick={() => void removeKeyword(item.id)}>删除</button>
                  <button type="button" disabled={keywordSaving} onClick={() => void setKeywordEnabled(item.id, !item.enabled)}>
                    {item.enabled ? "停用" : "启用"}
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="section-header">
            <div>
              <h3>白名单规则</h3>
              <p className="inline-note">突出忽略范围、忽略关键字和来源说明，方便核对巡检结果为何被忽略。</p>
            </div>
            <StatusBadge status={whitelistsLoading ? "loading" : "enabled"} />
          </div>
          {whitelistError ? <p>操作失败：{whitelistError}</p> : null}
          {whitelistMessage ? <p className="inline-note">{whitelistMessage}</p> : null}
          <div className="secondary-action-row">
            <button type="button" className="text-button" disabled={whitelistSaving} onClick={openWhitelistCreate}>新增白名单</button>
            <button type="button" className="text-button" disabled={whitelistSaving} onClick={() => setWhitelistModalType("import")}>导入白名单</button>
            <button type="button" className="text-button" disabled={whitelistSaving} onClick={() => void handleExportWhitelists()}>导出 JSON</button>
          </div>
          <div className="stack-list">
            {whitelists.map((item) => (
              <article key={item.id} className="card">
                <div className="card-title">
                  <strong>{item.keyword}</strong>
                  <StatusBadge status={item.enabled ? "enabled" : "disabled"} />
                </div>
                <p>{describeWhitelistScope(item)}</p>
                <p className="inline-note">来源说明：{item.note ?? "未填写来源说明"}</p>
                <div className="button-row">
                  <button type="button" disabled={whitelistSaving} onClick={() => startEditWhitelist(item)}>编辑</button>
                  <button type="button" disabled={whitelistSaving} onClick={() => void removeWhitelist(item.id)}>删除</button>
                  <button type="button" disabled={whitelistSaving} onClick={() => void setWhitelistEnabled(item.id, !item.enabled)}>
                    {item.enabled ? "停用" : "启用"}
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>
      </div>

      {keywordModalType === "create" || keywordModalType === "edit" ? (
        <div className="modal-backdrop" role="presentation">
          <section className="modal-card" role="dialog" aria-modal="true" aria-label={keywordModalType === "edit" ? "编辑关键字" : "新增关键字"}>
            <div className="section-header">
              <div>
                <h3>{keywordModalType === "edit" ? "编辑关键字" : "新增关键字"}</h3>
                <p className="inline-note">关键字会直接影响日志命中结果，请明确类别、严重程度和用途说明。</p>
              </div>
              <button type="button" onClick={closeKeywordModal}>关闭</button>
            </div>
            <label>
              关键字
              <input aria-label="关键字" value={keyword} onChange={(event) => setKeyword(event.target.value)} />
            </label>
            <label>
              类别
              <input aria-label="类别" value={category} onChange={(event) => setCategory(event.target.value)} />
            </label>
            <label>
              严重级别
              <select aria-label="严重级别" value={severity} onChange={(event) => setSeverity(event.target.value as KeywordHitSeverity)}>
                <option value="info">info</option>
                <option value="warning">warning</option>
                <option value="error">error</option>
                <option value="critical">critical</option>
              </select>
            </label>
            <label>
              说明
              <input aria-label="说明" value={description} onChange={(event) => setDescription(event.target.value)} />
            </label>
            <div className="button-row">
              <button type="button" disabled={keywordSaving || keyword.trim().length === 0} onClick={() => void handleSubmitKeyword()}>
                {keywordSaving ? "处理中..." : keywordEditingId !== null ? "保存关键字" : "新增关键字"}
              </button>
              <button type="button" onClick={closeKeywordModal}>取消</button>
            </div>
          </section>
        </div>
      ) : null}

      {keywordModalType === "import" ? (
        <div className="modal-backdrop" role="presentation">
          <section className="modal-card" role="dialog" aria-modal="true" aria-label="导入关键字">
            <div className="section-header">
              <div>
                <h3>导入关键字</h3>
                <p className="inline-note">只在迁移配置时使用，默认不在主页面展示 JSON。</p>
              </div>
              <button type="button" onClick={() => setKeywordModalType(null)}>关闭</button>
            </div>
            <label>
              导入关键字 JSON
              <textarea aria-label="导入关键字 JSON" value={keywordImportText} onChange={(event) => setKeywordImportText(event.target.value)} rows={10} />
            </label>
            <div className="button-row">
              <button type="button" disabled={keywordSaving || keywordImportText.trim().length === 0} onClick={() => void handleImportKeywords()}>导入关键字</button>
              <button type="button" onClick={() => setKeywordModalType(null)}>取消</button>
            </div>
          </section>
        </div>
      ) : null}

      {keywordModalType === "export" ? (
        <div className="modal-backdrop" role="presentation">
          <section className="modal-card" role="dialog" aria-modal="true" aria-label="导出关键字">
            <div className="section-header">
              <div>
                <h3>导出关键字</h3>
                <p className="inline-note">导出结果只用于跨环境迁移。</p>
              </div>
              <button type="button" onClick={() => setKeywordModalType(null)}>关闭</button>
            </div>
            <label>
              已导出 JSON
              <textarea aria-label="已导出 JSON" value={keywordExportText} readOnly rows={12} />
            </label>
            <div className="button-row">
              <button type="button" onClick={() => setKeywordModalType(null)}>关闭</button>
            </div>
          </section>
        </div>
      ) : null}

      {whitelistModalType === "create" || whitelistModalType === "edit" ? (
        <div className="modal-backdrop" role="presentation">
          <section className="modal-card" role="dialog" aria-modal="true" aria-label={whitelistModalType === "edit" ? "编辑白名单" : "新增白名单"}>
            <div className="section-header">
              <div>
                <h3>{whitelistModalType === "edit" ? "编辑白名单" : "新增白名单"}</h3>
                <p className="inline-note">请明确忽略会作用在哪个名称空间、标签、Pod、容器和关键字上。</p>
              </div>
              <button type="button" onClick={closeWhitelistModal}>关闭</button>
            </div>
            <label>
              名称空间
              <input aria-label="名称空间" value={namespace} onChange={(event) => setNamespace(event.target.value)} />
            </label>
            <label>
              Label Selector
              <input aria-label="Label Selector" value={labelSelector} onChange={(event) => setLabelSelector(event.target.value)} />
            </label>
            <label>
              Pod 名称匹配
              <input aria-label="Pod 名称匹配" value={podNamePattern} onChange={(event) => setPodNamePattern(event.target.value)} />
            </label>
            <label>
              容器名称
              <input aria-label="容器名称" value={containerName} onChange={(event) => setContainerName(event.target.value)} />
            </label>
            <label>
              白名单关键字
              <input aria-label="白名单关键字" value={whitelistKeyword} onChange={(event) => setWhitelistKeyword(event.target.value)} />
            </label>
            <label>
              备注
              <input aria-label="备注" value={note} onChange={(event) => setNote(event.target.value)} placeholder="例如：来自巡检误报，启动预热阶段忽略" />
            </label>
            <div className="button-row">
              <button type="button" disabled={whitelistSaving || namespace.trim().length === 0 || whitelistKeyword.trim().length === 0} onClick={() => void handleSubmitWhitelist()}>
                {whitelistSaving ? "处理中..." : whitelistEditingId !== null ? "保存白名单" : "新增白名单"}
              </button>
              <button type="button" onClick={closeWhitelistModal}>取消</button>
            </div>
          </section>
        </div>
      ) : null}

      {whitelistModalType === "import" ? (
        <div className="modal-backdrop" role="presentation">
          <section className="modal-card" role="dialog" aria-modal="true" aria-label="导入白名单">
            <div className="section-header">
              <div>
                <h3>导入白名单</h3>
                <p className="inline-note">只在迁移配置时使用，默认不在主页面展示 JSON。</p>
              </div>
              <button type="button" onClick={() => setWhitelistModalType(null)}>关闭</button>
            </div>
            <label>
              导入白名单 JSON
              <textarea aria-label="导入白名单 JSON" value={whitelistImportText} onChange={(event) => setWhitelistImportText(event.target.value)} rows={10} />
            </label>
            <div className="button-row">
              <button type="button" disabled={whitelistSaving || whitelistImportText.trim().length === 0} onClick={() => void handleImportWhitelists()}>导入白名单</button>
              <button type="button" onClick={() => setWhitelistModalType(null)}>取消</button>
            </div>
          </section>
        </div>
      ) : null}

      {whitelistModalType === "export" ? (
        <div className="modal-backdrop" role="presentation">
          <section className="modal-card" role="dialog" aria-modal="true" aria-label="导出白名单">
            <div className="section-header">
              <div>
                <h3>导出白名单</h3>
                <p className="inline-note">导出结果只用于跨环境迁移。</p>
              </div>
              <button type="button" onClick={() => setWhitelistModalType(null)}>关闭</button>
            </div>
            <label>
              已导出 JSON
              <textarea aria-label="已导出 JSON" value={whitelistExportText} readOnly rows={12} />
            </label>
            <div className="button-row">
              <button type="button" onClick={() => setWhitelistModalType(null)}>关闭</button>
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}
