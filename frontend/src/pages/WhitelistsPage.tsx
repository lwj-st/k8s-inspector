import { useState } from "react";

import type { KeywordHitSeverity, KeywordRule, Whitelist } from "../api/types";
import { StatusBadge } from "../components/StatusBadge";
import { useKeywords } from "../features/whitelists/useKeywords";
import { useWhitelists } from "../features/whitelists/useWhitelists";

function formatJson(value: unknown) {
  return JSON.stringify(value, null, 2);
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
  const [keyword, setKeyword] = useState("");
  const [category, setCategory] = useState("application");
  const [severity, setSeverity] = useState<KeywordHitSeverity>("warning");
  const [description, setDescription] = useState("");
  const [keywordImportText, setKeywordImportText] = useState("");
  const [keywordExportText, setKeywordExportText] = useState("");
  const [keywordMessage, setKeywordMessage] = useState<string | null>(null);

  const [whitelistEditingId, setWhitelistEditingId] = useState<number | null>(null);
  const [namespace, setNamespace] = useState("");
  const [labelSelector, setLabelSelector] = useState("");
  const [podNamePattern, setPodNamePattern] = useState("");
  const [containerName, setContainerName] = useState("");
  const [whitelistKeyword, setWhitelistKeyword] = useState("");
  const [note, setNote] = useState("");
  const [whitelistImportText, setWhitelistImportText] = useState("");
  const [whitelistExportText, setWhitelistExportText] = useState("");
  const [whitelistMessage, setWhitelistMessage] = useState<string | null>(null);

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

  function startEditKeyword(item: KeywordRule) {
    setKeywordEditingId(item.id);
    setKeyword(item.keyword);
    setCategory(item.category);
    setSeverity(item.severity);
    setDescription(item.description ?? "");
    setKeywordMessage(`正在编辑关键字：${item.keyword}`);
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
  }

  async function handleExportKeywords() {
    const exported = await exportKeywords();
    setKeywordExportText(formatJson(exported));
    setKeywordMessage(`已导出 ${exported.length} 条关键字`);
  }

  async function handleExportWhitelists() {
    const exported = await exportWhitelists();
    setWhitelistExportText(formatJson(exported));
    setWhitelistMessage(`已导出 ${exported.length} 条白名单`);
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
  }

  return (
    <section className="page-section">
      <header className="section-header">
        <div>
          <p className="eyebrow">Whitelist Center</p>
          <h2>关键字库与白名单</h2>
        </div>
        <span className="section-tip">先定义系统判异常的关键字，再把已知噪音就地忽略成白名单</span>
      </header>

      <div className="card-grid card-grid-wide">
        <section className="panel">
          <div className="section-header">
            <h3>关键字库</h3>
            <StatusBadge status={keywordsLoading ? "loading" : "enabled"} />
          </div>
          {keywordError ? <p>操作失败：{keywordError}</p> : null}
          {keywordMessage ? <p className="inline-note">{keywordMessage}</p> : null}
          <label>
            关键字
            <input value={keyword} onChange={(event) => setKeyword(event.target.value)} />
          </label>
          <label>
            类别
            <input value={category} onChange={(event) => setCategory(event.target.value)} />
          </label>
          <label>
            严重级别
            <select value={severity} onChange={(event) => setSeverity(event.target.value as KeywordHitSeverity)}>
              <option value="info">info</option>
              <option value="warning">warning</option>
              <option value="error">error</option>
              <option value="critical">critical</option>
            </select>
          </label>
          <label>
            说明
            <input value={description} onChange={(event) => setDescription(event.target.value)} />
          </label>
          <div className="log-hit-actions">
            <button type="button" disabled={keywordSaving || keyword.trim().length === 0} onClick={() => void handleSubmitKeyword()}>
              {keywordSaving ? "处理中..." : keywordEditingId !== null ? "保存关键字" : "新增关键字"}
            </button>
            {keywordEditingId !== null ? (
              <button type="button" disabled={keywordSaving} onClick={resetKeywordForm}>
                取消编辑
              </button>
            ) : null}
            <button type="button" disabled={keywordSaving} onClick={() => void handleExportKeywords()}>
              导出 JSON
            </button>
          </div>
          <label>
            导入关键字 JSON
            <textarea value={keywordImportText} onChange={(event) => setKeywordImportText(event.target.value)} rows={6} />
          </label>
          <button type="button" disabled={keywordSaving || keywordImportText.trim().length === 0} onClick={() => void handleImportKeywords()}>
            导入关键字
          </button>
          {keywordExportText ? (
            <label>
              已导出 JSON
              <textarea value={keywordExportText} readOnly rows={6} />
            </label>
          ) : null}
          <div className="stack-list">
            {keywords.map((item) => (
              <div key={item.id} className="stack-item">
                <div className="card-title">
                  <strong>{item.keyword}</strong>
                  <StatusBadge status={item.enabled ? item.severity : "disabled"} />
                </div>
                <p>{[item.category, item.description].filter(Boolean).join(" / ")}</p>
                {item.builtin ? <p className="inline-note">系统内置</p> : null}
                <div className="log-hit-actions">
                  <button type="button" disabled={keywordSaving} onClick={() => startEditKeyword(item)}>
                    编辑
                  </button>
                  <button type="button" disabled={keywordSaving || item.builtin} onClick={() => void removeKeyword(item.id)}>
                    删除
                  </button>
                  <button type="button" disabled={keywordSaving} onClick={() => void setKeywordEnabled(item.id, !item.enabled)}>
                    {item.enabled ? "停用" : "启用"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="section-header">
            <h3>白名单规则</h3>
            <StatusBadge status={whitelistsLoading ? "loading" : "enabled"} />
          </div>
          {whitelistError ? <p>操作失败：{whitelistError}</p> : null}
          {whitelistMessage ? <p className="inline-note">{whitelistMessage}</p> : null}
          <label>
            名称空间
            <input value={namespace} onChange={(event) => setNamespace(event.target.value)} />
          </label>
          <label>
            Label Selector
            <input value={labelSelector} onChange={(event) => setLabelSelector(event.target.value)} />
          </label>
          <label>
            Pod 名称匹配
            <input value={podNamePattern} onChange={(event) => setPodNamePattern(event.target.value)} />
          </label>
          <label>
            容器名称
            <input value={containerName} onChange={(event) => setContainerName(event.target.value)} />
          </label>
          <label>
            白名单关键字
            <input value={whitelistKeyword} onChange={(event) => setWhitelistKeyword(event.target.value)} />
          </label>
          <label>
            备注
            <input value={note} onChange={(event) => setNote(event.target.value)} />
          </label>
          <div className="log-hit-actions">
            <button
              type="button"
              disabled={whitelistSaving || namespace.trim().length === 0 || whitelistKeyword.trim().length === 0}
              onClick={() => void handleSubmitWhitelist()}
            >
              {whitelistSaving ? "处理中..." : whitelistEditingId !== null ? "保存白名单" : "新增白名单"}
            </button>
            {whitelistEditingId !== null ? (
              <button type="button" disabled={whitelistSaving} onClick={resetWhitelistForm}>
                取消编辑
              </button>
            ) : null}
            <button type="button" disabled={whitelistSaving} onClick={() => void handleExportWhitelists()}>
              导出 JSON
            </button>
          </div>
          <label>
            导入白名单 JSON
            <textarea value={whitelistImportText} onChange={(event) => setWhitelistImportText(event.target.value)} rows={6} />
          </label>
          <button type="button" disabled={whitelistSaving || whitelistImportText.trim().length === 0} onClick={() => void handleImportWhitelists()}>
            导入白名单
          </button>
          {whitelistExportText ? (
            <label>
              已导出 JSON
              <textarea value={whitelistExportText} readOnly rows={6} />
            </label>
          ) : null}
          <div className="stack-list">
            {whitelists.map((item) => (
              <div key={item.id} className="stack-item">
                <div className="card-title">
                  <strong>{item.keyword}</strong>
                  <StatusBadge status={item.enabled ? "enabled" : "disabled"} />
                </div>
                <p>{item.namespace}{item.label_selector ? ` / ${item.label_selector}` : ""}</p>
                {item.note ? <p className="inline-note">{item.note}</p> : null}
                <div className="log-hit-actions">
                  <button type="button" disabled={whitelistSaving} onClick={() => startEditWhitelist(item)}>
                    编辑
                  </button>
                  <button type="button" disabled={whitelistSaving} onClick={() => void removeWhitelist(item.id)}>
                    删除
                  </button>
                  <button type="button" disabled={whitelistSaving} onClick={() => void setWhitelistEnabled(item.id, !item.enabled)}>
                    {item.enabled ? "停用" : "启用"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}
