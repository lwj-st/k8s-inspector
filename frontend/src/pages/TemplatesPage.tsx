import { useState } from "react";

import type {
  FaultTemplate,
  TemplateCondition,
  TemplateConditionOperator,
  TemplateConditionType,
  TemplateTarget,
} from "../api/types";
import { StatusBadge } from "../components/StatusBadge";
import { useTemplates } from "../features/templates/useTemplates";

type TargetDraft = {
  target_ref: string;
  namespace: string;
  label_selector: string;
  pod_name_pattern: string;
  resource_scope: string[];
};

type ConditionDraft = {
  target_ref: string;
  condition_type: TemplateConditionType;
  operator: TemplateConditionOperator;
  value_text: string;
  related_resource: string;
  enabled: boolean;
};

const resourceScopeOptions = ["pods", "deployment", "services", "ingresses", "daemonsets", "tls_secrets"] as const;

function formatJson(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function createDefaultTarget(): TargetDraft {
  return {
    target_ref: "group-1",
    namespace: "",
    label_selector: "",
    pod_name_pattern: "",
    resource_scope: ["pods"],
  };
}

function createDefaultCondition(targetRef = "group-1"): ConditionDraft {
  return {
    target_ref: targetRef,
    condition_type: "log_keyword",
    operator: "contains",
    value_text: "",
    related_resource: "services",
    enabled: true,
  };
}

function getOperators(conditionType: TemplateConditionType): TemplateConditionOperator[] {
  if (conditionType === "pod_status") {
    return ["equals", "in"];
  }
  if (conditionType === "restart_count") {
    return ["equals", "gte", "lte"];
  }
  if (conditionType === "related_object_status") {
    return ["equals", "in"];
  }
  return ["contains"];
}

function normalizeOperator(conditionType: TemplateConditionType, operator: TemplateConditionOperator): TemplateConditionOperator {
  const allowed = getOperators(conditionType);
  return allowed.includes(operator) ? operator : allowed[0];
}

function describeCondition(condition: {
  target_ref?: string | null;
  condition_type?: string;
  operator?: string;
  expected_value?: unknown;
}) {
  const targetRef = String(condition.target_ref ?? "对象组");
  const type = String(condition.condition_type ?? "unknown");
  const operator = String(condition.operator ?? "equals");
  const expectedValue = Array.isArray(condition.expected_value)
    ? condition.expected_value.join(", ")
    : String(condition.expected_value ?? "");

  if (type === "log_keyword") {
    return `对象组 ${targetRef} 在日志中包含 ${expectedValue}`;
  }

  if (type === "pod_status") {
    return operator === "equals"
      ? `对象组 ${targetRef} 的 Pod 状态等于 ${expectedValue}`
      : `对象组 ${targetRef} 的 Pod 状态属于 ${expectedValue}`;
  }

  if (type === "restart_count") {
    return `对象组 ${targetRef} 的重启次数 ${operator} ${expectedValue}`;
  }

  if (type === "event_keyword") {
    return `对象组 ${targetRef} 的事件中包含 ${expectedValue}`;
  }

  if (type === "related_object_status") {
    const related = condition.expected_value as { resource?: string; statuses?: string[] } | undefined;
    const statuses = related?.statuses?.join(", ") ?? "";
    return `对象组 ${targetRef} 的关联对象 ${related?.resource ?? ""} 状态 ${operator} ${statuses}`;
  }

  return `对象组 ${targetRef} 需要满足 ${type} ${operator} ${expectedValue}`;
}

function describeDraftCondition(condition: ConditionDraft) {
  if (condition.condition_type === "related_object_status") {
    return describeCondition({
      target_ref: condition.target_ref,
      condition_type: condition.condition_type,
      operator: condition.operator,
      expected_value: {
        resource: condition.related_resource,
        statuses: condition.value_text.split(",").map((item) => item.trim()).filter(Boolean),
      },
    });
  }

  return describeCondition({
    target_ref: condition.target_ref,
    condition_type: condition.condition_type,
    operator: condition.operator,
    expected_value: condition.operator === "in"
      ? condition.value_text.split(",").map((item) => item.trim()).filter(Boolean)
      : condition.value_text,
  });
}

function getTargetGroups(item: FaultTemplate) {
  if (item.targets.length > 0) {
    return item.targets.map((target) => ({
      ref: target.target_ref,
      namespace: target.namespace,
      label_selector: target.label_selector,
      name: target.pod_name_pattern,
      resource_scope: target.resource_scope,
    }));
  }

  return (item.target_groups ?? []).map((target) => ({
    ref: target.ref,
    namespace: target.namespace,
    label_selector: target.label_selector,
    name: target.name,
    resource_scope: target.object_scope ? [target.object_scope] : [],
  }));
}

function toTargetDrafts(template: FaultTemplate): TargetDraft[] {
  return template.targets.map((target) => ({
    target_ref: target.target_ref,
    namespace: target.namespace,
    label_selector: target.label_selector ?? "",
    pod_name_pattern: target.pod_name_pattern ?? "",
    resource_scope: target.resource_scope,
  }));
}

function toConditionDrafts(template: FaultTemplate): ConditionDraft[] {
  return template.match_conditions.map((condition) => {
    if (condition.condition_type === "related_object_status") {
      const value = (condition.expected_value ?? {}) as { resource?: string; statuses?: string[] };
      return {
        target_ref: condition.target_ref,
        condition_type: condition.condition_type,
        operator: condition.operator,
        value_text: (value.statuses ?? []).join(", "),
        related_resource: value.resource ?? "services",
        enabled: condition.enabled,
      };
    }

    return {
      target_ref: condition.target_ref,
      condition_type: condition.condition_type,
      operator: condition.operator,
      value_text: Array.isArray(condition.expected_value)
        ? condition.expected_value.join(", ")
        : String(condition.expected_value ?? ""),
      related_resource: "services",
      enabled: condition.enabled,
    };
  });
}

export function TemplatesPage() {
  const {
    data,
    loading,
    saving,
    error,
    create,
    update,
    remove,
    setEnabled,
    exportAll,
    importAll,
  } = useTemplates();

  const [editingId, setEditingId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [scenario, setScenario] = useState("targeted_diagnosis");
  const [jointOperator, setJointOperator] = useState<"AND" | "OR">("AND");
  const [targets, setTargets] = useState<TargetDraft[]>([createDefaultTarget()]);
  const [conditions, setConditions] = useState<ConditionDraft[]>([createDefaultCondition()]);
  const [reason, setReason] = useState("");
  const [suggestion, setSuggestion] = useState("");
  const [command, setCommand] = useState("");
  const [riskNote, setRiskNote] = useState("");
  const [enabled, setTemplateEnabled] = useState(true);
  const [importText, setImportText] = useState("");
  const [exportText, setExportText] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  function resetForm() {
    setEditingId(null);
    setName("");
    setScenario("targeted_diagnosis");
    setJointOperator("AND");
    setTargets([createDefaultTarget()]);
    setConditions([createDefaultCondition()]);
    setReason("");
    setSuggestion("");
    setCommand("");
    setRiskNote("");
    setTemplateEnabled(true);
  }

  function buildPayload() {
    const normalizedTargets: TemplateTarget[] = targets.map((target) => ({
      target_ref: target.target_ref.trim(),
      namespace: target.namespace.trim(),
      label_selector: target.label_selector.trim() || null,
      pod_name_pattern: target.pod_name_pattern.trim() || null,
      resource_scope: target.resource_scope,
    }));

    const normalizedConditions: TemplateCondition[] = conditions.map((condition) => {
      let expectedValue: unknown = condition.value_text.trim();
      if (condition.condition_type === "pod_status" && condition.operator === "in") {
        expectedValue = condition.value_text.split(",").map((item) => item.trim()).filter(Boolean);
      } else if (condition.condition_type === "restart_count") {
        expectedValue = Number(condition.value_text || "0");
      } else if (condition.condition_type === "related_object_status") {
        expectedValue = {
          resource: condition.related_resource,
          statuses: condition.value_text.split(",").map((item) => item.trim()).filter(Boolean),
        };
      }

      return {
        target_ref: condition.target_ref,
        condition_type: condition.condition_type,
        operator: condition.operator,
        expected_value: expectedValue,
        join_operator: jointOperator,
        enabled: condition.enabled,
      };
    });

    return {
      name: name.trim(),
      scenario: scenario.trim(),
      targets: normalizedTargets,
      match_conditions: normalizedConditions,
      joint_rule: { operator: jointOperator },
      reason: reason.trim(),
      suggestion: suggestion.trim(),
      command: command.trim() || null,
      risk_note: riskNote.trim() || null,
      enabled,
    };
  }

  async function handleSubmit() {
    setMessage(null);
    const payload = buildPayload();

    if (editingId !== null) {
      await update(editingId, payload);
      setMessage("模板已更新");
    } else {
      await create(payload);
      setMessage("模板已新增");
    }
    resetForm();
  }

  function startEdit(template: FaultTemplate) {
    setEditingId(template.id);
    setName(template.name);
    setScenario(template.scenario);
    setJointOperator((template.joint_rule?.operator as "AND" | "OR" | undefined) ?? "AND");
    setTargets(toTargetDrafts(template));
    setConditions(toConditionDrafts(template));
    setReason(template.reason);
    setSuggestion(template.suggestion);
    setCommand(template.command ?? "");
    setRiskNote(template.risk_note ?? "");
    setTemplateEnabled(template.enabled);
    setMessage(`正在编辑模板：${template.name}`);
  }

  function addTarget() {
    const nextRef = `group-${targets.length + 1}`;
    setTargets((current) => [...current, { ...createDefaultTarget(), target_ref: nextRef }]);
  }

  function updateTarget(index: number, patch: Partial<TargetDraft>) {
    const previousTargetRef = targets[index]?.target_ref;
    setTargets((current) => current.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
    if (patch.target_ref && previousTargetRef && patch.target_ref !== previousTargetRef) {
      setConditions((current) =>
        current.map((item) => (item.target_ref === previousTargetRef ? { ...item, target_ref: patch.target_ref ?? item.target_ref } : item)),
      );
    }
  }

  function removeTarget(index: number) {
    if (targets.length === 1) {
      return;
    }
    const targetRef = targets[index].target_ref;
    const remainingTargets = targets.filter((_, itemIndex) => itemIndex !== index);
    const fallbackTargetRef = remainingTargets[0]?.target_ref ?? "group-1";
    setTargets(remainingTargets);
    setConditions((current) =>
      current.map((item) => ({
        ...item,
        target_ref: item.target_ref === targetRef ? fallbackTargetRef : item.target_ref,
      })),
    );
  }

  function toggleTargetScope(index: number, scope: string) {
    setTargets((current) =>
      current.map((item, itemIndex) => {
        if (itemIndex !== index) {
          return item;
        }
        return item.resource_scope.includes(scope)
          ? { ...item, resource_scope: item.resource_scope.filter((value) => value !== scope) }
          : { ...item, resource_scope: [...item.resource_scope, scope] };
      }),
    );
  }

  function addCondition() {
    setConditions((current) => [...current, createDefaultCondition(targets[0]?.target_ref ?? "group-1")]);
  }

  function updateCondition(index: number, patch: Partial<ConditionDraft>) {
    setConditions((current) =>
      current.map((item, itemIndex) => {
        if (itemIndex !== index) {
          return item;
        }
        const next = { ...item, ...patch };
        if (patch.condition_type) {
          next.operator = normalizeOperator(patch.condition_type, next.operator);
          if (patch.condition_type !== "related_object_status") {
            next.related_resource = "services";
          }
        }
        return next;
      }),
    );
  }

  function removeCondition(index: number) {
    if (conditions.length === 1) {
      return;
    }
    setConditions((current) => current.filter((_, itemIndex) => itemIndex !== index));
  }

  async function handleExport() {
    const exported = await exportAll();
    setExportText(formatJson(exported));
    setMessage(`已导出 ${exported.length} 个模板`);
  }

  async function handleImport() {
    const imported = await importAll(JSON.parse(importText) as Array<{
      name: string;
      scenario: string;
      targets: TemplateTarget[];
      match_conditions: TemplateCondition[];
      joint_rule?: { operator: "AND" | "OR" } | null;
      reason: string;
      suggestion: string;
      command?: string | null;
      risk_note?: string | null;
      enabled: boolean;
    }>);
    setMessage(`已导入 ${imported.length} 个模板`);
    setImportText("");
  }

  if (loading) {
    return <p>加载中...</p>;
  }

  return (
    <section className="page-section">
      <header className="section-header">
        <div>
          <p className="eyebrow">Template Studio</p>
          <h2>故障模板</h2>
        </div>
        <span className="section-tip">先定义对象组，再组合条件，最后补齐原因和处理建议。</span>
      </header>

      <div className="card-grid card-grid-wide">
        <section className="panel panel-muted">
          <div className="section-header">
            <div>
              <h3>模板录入器</h3>
              <p className="inline-note">支持多个对象组；多个 Pod 命中时只要有一个满足条件即可视为该对象组命中。</p>
            </div>
            <StatusBadge status={saving ? "warning" : editingId !== null ? "enabled" : "info"} />
          </div>
          {error ? <p>操作失败：{error}</p> : null}
          {message ? <p className="inline-note">{message}</p> : null}
          <label>
            模板名称
            <input value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：网关 502 故障" />
          </label>
          <label>
            场景标识
            <input value={scenario} onChange={(event) => setScenario(event.target.value)} placeholder="例如：gateway_502" />
          </label>
          <label>
            条件关系
            <select value={jointOperator} onChange={(event) => setJointOperator(event.target.value as "AND" | "OR")}>
              <option value="AND">AND：所有条件都满足才命中</option>
              <option value="OR">OR：任一条件满足就命中</option>
            </select>
          </label>

          <div className="section-header">
            <h3>对象组</h3>
            <button type="button" onClick={addTarget}>
              新增对象组
            </button>
          </div>
          <div className="stack-list">
            {targets.map((target, index) => (
              <div key={`target-${index}`} className="stack-item">
                <div className="section-header">
                  <strong>对象组 {index + 1}</strong>
                  <button type="button" disabled={targets.length === 1} onClick={() => removeTarget(index)}>
                    删除对象组
                  </button>
                </div>
                <label>
                  对象组标识
                  <input value={target.target_ref} onChange={(event) => updateTarget(index, { target_ref: event.target.value })} />
                </label>
                <label>
                  名称空间
                  <input value={target.namespace} onChange={(event) => updateTarget(index, { namespace: event.target.value })} placeholder="例如：gateway-system" />
                </label>
                <label>
                  Label Selector
                  <input value={target.label_selector} onChange={(event) => updateTarget(index, { label_selector: event.target.value })} placeholder="例如：app=gateway" />
                </label>
                <label>
                  Pod 名称模式
                  <input value={target.pod_name_pattern} onChange={(event) => updateTarget(index, { pod_name_pattern: event.target.value })} placeholder="例如：gateway-*" />
                </label>
                <div className="stack-list">
                  <strong>资源范围</strong>
                  {resourceScopeOptions.map((scope) => (
                    <label key={`${target.target_ref}-${scope}`}>
                      <input
                        type="checkbox"
                        checked={target.resource_scope.includes(scope)}
                        onChange={() => toggleTargetScope(index, scope)}
                      />
                      {scope}
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <div className="section-header">
            <h3>条件块</h3>
            <button type="button" onClick={addCondition}>
              新增条件
            </button>
          </div>
          <div className="stack-list">
            {conditions.map((condition, index) => (
              <div key={`condition-${index}`} className="stack-item">
                <div className="section-header">
                  <strong>条件 {index + 1}</strong>
                  <button type="button" disabled={conditions.length === 1} onClick={() => removeCondition(index)}>
                    删除条件
                  </button>
                </div>
                <label>
                  绑定对象组
                  <select value={condition.target_ref} onChange={(event) => updateCondition(index, { target_ref: event.target.value })}>
                    {targets.map((target) => (
                      <option key={target.target_ref} value={target.target_ref}>
                        {target.target_ref}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  条件类型
                  <select
                    value={condition.condition_type}
                    onChange={(event) => updateCondition(index, { condition_type: event.target.value as TemplateConditionType })}
                  >
                    <option value="log_keyword">log_keyword</option>
                    <option value="pod_status">pod_status</option>
                    <option value="restart_count">restart_count</option>
                    <option value="event_keyword">event_keyword</option>
                    <option value="related_object_status">related_object_status</option>
                  </select>
                </label>
                <label>
                  运算符
                  <select
                    value={condition.operator}
                    onChange={(event) => updateCondition(index, { operator: event.target.value as TemplateConditionOperator })}
                  >
                    {getOperators(condition.condition_type).map((operator) => (
                      <option key={`${condition.condition_type}-${operator}`} value={operator}>
                        {operator}
                      </option>
                    ))}
                  </select>
                </label>
                {condition.condition_type === "related_object_status" ? (
                  <>
                    <label>
                      关联资源类型
                      <select
                        value={condition.related_resource}
                        onChange={(event) => updateCondition(index, { related_resource: event.target.value })}
                      >
                        <option value="services">services</option>
                        <option value="ingresses">ingresses</option>
                        <option value="daemonsets">daemonsets</option>
                        <option value="tls_secrets">tls_secrets</option>
                      </select>
                    </label>
                    <label>
                      状态值
                      <input
                        value={condition.value_text}
                        onChange={(event) => updateCondition(index, { value_text: event.target.value })}
                        placeholder={condition.operator === "in" ? "例如：degraded, failed" : "例如：degraded"}
                      />
                    </label>
                  </>
                ) : (
                  <label>
                    目标值
                    <input
                      value={condition.value_text}
                      onChange={(event) => updateCondition(index, { value_text: event.target.value })}
                      placeholder={
                        condition.operator === "in"
                          ? "多个值请用逗号分隔"
                          : condition.condition_type === "restart_count"
                            ? "例如：3"
                            : "请输入目标值"
                      }
                    />
                  </label>
                )}
                <label>
                  <input
                    type="checkbox"
                    checked={condition.enabled}
                    onChange={(event) => updateCondition(index, { enabled: event.target.checked })}
                  />
                  条件启用
                </label>
                <div className="condition-item">
                  {describeDraftCondition(condition)}
                </div>
              </div>
            ))}
          </div>

          <label>
            诊断原因
            <textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={3} placeholder="例如：网关进程无法连接上游服务" />
          </label>
          <label>
            处理建议
            <textarea value={suggestion} onChange={(event) => setSuggestion(event.target.value)} rows={3} placeholder="例如：检查上游 Service 和配置" />
          </label>
          <label>
            建议命令
            <input value={command} onChange={(event) => setCommand(event.target.value)} placeholder="例如：kubectl logs -n xxx deploy/xxx" />
          </label>
          <label>
            风险说明
            <input value={riskNote} onChange={(event) => setRiskNote(event.target.value)} placeholder="例如：只读命令，可直接执行" />
          </label>
          <label>
            <input type="checkbox" checked={enabled} onChange={(event) => setTemplateEnabled(event.target.checked)} />
            模板启用
          </label>
          <div className="log-hit-actions">
            <button
              type="button"
              disabled={
                saving ||
                name.trim().length === 0 ||
                reason.trim().length === 0 ||
                suggestion.trim().length === 0 ||
                targets.some((target) => target.target_ref.trim().length === 0 || target.namespace.trim().length === 0) ||
                conditions.some((condition) => condition.value_text.trim().length === 0)
              }
              onClick={() => void handleSubmit()}
            >
              {saving ? "处理中..." : editingId !== null ? "保存模板" : "新增模板"}
            </button>
            {editingId !== null ? (
              <button type="button" disabled={saving} onClick={resetForm}>
                取消编辑
              </button>
            ) : null}
          </div>
        </section>

        <section className="panel">
          <div className="section-header">
            <h3>导入导出</h3>
            <StatusBadge status={saving ? "warning" : "info"} />
          </div>
          <p className="inline-note">JSON 仅作为迁移能力，日常录入请优先使用左侧录入器。</p>
          <div className="log-hit-actions">
            <button type="button" disabled={saving} onClick={() => void handleExport()}>
              导出模板 JSON
            </button>
          </div>
          <label>
            导入模板 JSON
            <textarea value={importText} onChange={(event) => setImportText(event.target.value)} rows={10} placeholder='[{"name":"..."}]' />
          </label>
          <button type="button" disabled={saving || importText.trim().length === 0} onClick={() => void handleImport()}>
            导入模板
          </button>
          {exportText ? (
            <label>
              已导出 JSON
              <textarea value={exportText} readOnly rows={12} />
            </label>
          ) : null}
        </section>
      </div>

      <section className="page-section">
        <div className="section-header">
          <h3>模板列表</h3>
          <span className="section-tip">展示启用状态、对象组摘要、条件摘要和处理建议。</span>
        </div>
        <div className="card-grid">
          {data.map((item) => {
            const targetGroups = getTargetGroups(item);
            return (
              <article key={item.id} className="card">
                <div className="card-title">
                  <strong>{item.name}</strong>
                  <StatusBadge status={item.enabled ? "enabled" : "disabled"} />
                </div>
                <p>{item.reason}</p>
                <p className="inline-note">建议：{item.suggestion}</p>
                <div className="stack-list">
                  {targetGroups.map((group, index) => (
                    <div key={`${item.id}-group-${index}`} className="stack-item">
                      <strong>对象组：{group.ref}</strong>
                      <p>
                        {group.namespace}
                        {group.label_selector ? ` / ${group.label_selector}` : ""}
                      </p>
                      {group.name ? <p className="inline-note">Pod 名称模式：{group.name}</p> : null}
                      {group.resource_scope?.length ? (
                        <p className="inline-note">资源范围：{group.resource_scope.join(", ")}</p>
                      ) : null}
                    </div>
                  ))}
                </div>
                <div className="condition-list">
                  {item.match_conditions.map((condition, index) => (
                    <div key={`${item.id}-condition-${index}`} className="condition-item">
                      {describeCondition(condition as { target_ref?: string; condition_type?: string; operator?: string; expected_value?: unknown })}
                    </div>
                  ))}
                </div>
                <p className="inline-note">条件关系：{String(item.joint_rule?.operator ?? "AND")}</p>
                {item.command ? <p className="inline-note">建议命令：{item.command}</p> : null}
                {item.risk_note ? <p className="inline-note">风险说明：{item.risk_note}</p> : null}
                <div className="log-hit-actions">
                  <button type="button" disabled={saving} onClick={() => startEdit(item)}>
                    编辑
                  </button>
                  <button type="button" disabled={saving} onClick={() => void setEnabled(item.id, !item.enabled)}>
                    {item.enabled ? "停用" : "启用"}
                  </button>
                  <button type="button" disabled={saving} onClick={() => void remove(item.id)}>
                    删除
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      </section>
    </section>
  );
}
