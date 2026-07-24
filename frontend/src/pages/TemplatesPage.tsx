import { useMemo, useState } from "react";

import type {
  FaultTemplate,
  TemplateCondition,
  TemplateConditionOperator,
  TemplateConditionType,
  TemplateTarget,
} from "../api/types";
import { StatusBadge } from "../components/StatusBadge";
import { useDiscoverNamespaceLabels } from "../features/inspections/useDiscoverNamespaceLabels";
import { useDiscoverNamespaces } from "../features/inspections/useDiscoverNamespaces";
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
  related_match_any: boolean;
  related_object_name: string;
  enabled: boolean;
};

type StepKey = "basic" | "targets" | "conditions" | "advice" | "preview";
type ModalType = "import" | "export" | "editor" | null;

type StepDefinition = {
  key: StepKey;
  title: string;
  description: string;
};

const stepDefinitions: StepDefinition[] = [
  { key: "basic", title: "基本信息", description: "说明这是哪类故障经验。" },
  { key: "targets", title: "目标范围", description: "选择名称空间和 Label Selector，确定检查对象组。" },
  { key: "conditions", title: "匹配条件", description: "按对象组补齐日志、状态、重启次数等可量化条件。" },
  { key: "advice", title: "原因与建议", description: "录入诊断原因、处理建议、命令和风险说明。" },
  { key: "preview", title: "预览与保存", description: "最后检查摘要，再决定新增或更新模板。" },
];

const conditionTypeLabels: Record<TemplateConditionType, string> = {
  log_keyword: "日志包含关键字",
  pod_status: "Pod 状态匹配",
  restart_count: "重启次数达到阈值",
  event_keyword: "事件包含关键字",
  related_object_status: "关联对象状态异常",
};

const operatorLabels: Record<TemplateConditionOperator, string> = {
  contains: "包含",
  equals: "等于",
  in: "属于任一值",
  gte: "大于等于",
  lte: "小于等于",
};

const relatedResourceOptions = [
  { value: "services", label: "Service" },
  { value: "ingresses", label: "Ingress" },
  { value: "daemonsets", label: "DaemonSet" },
  { value: "tls_secrets", label: "TLS Secret" },
] as const;

const relatedObjectStatusOptions: Record<string, string[]> = {
  services: ["healthy", "degraded", "unknown"],
  ingresses: ["healthy", "degraded", "unknown"],
  daemonsets: ["healthy", "degraded", "unknown"],
  tls_secrets: ["healthy", "expiring", "expired", "missing", "unknown"],
};

const podStatusOptions = ["Running", "Succeeded", "Pending", "Failed", "Unknown", "CrashLoopBackOff", "ImagePullBackOff"];

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
    related_match_any: true,
    related_object_name: "",
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
  const type = String(condition.condition_type ?? "unknown") as TemplateConditionType;
  const operator = String(condition.operator ?? "equals") as TemplateConditionOperator;
  const expectedValue = Array.isArray(condition.expected_value)
    ? condition.expected_value.join(", ")
    : String(condition.expected_value ?? "");

  if (type === "log_keyword") {
    return `对象组 ${targetRef} 的日志包含 ${expectedValue}`;
  }

  if (type === "pod_status") {
    return `对象组 ${targetRef} 的 Pod 状态${operatorLabels[operator]} ${expectedValue}`;
  }

  if (type === "restart_count") {
    return `对象组 ${targetRef} 的重启次数${operatorLabels[operator]} ${expectedValue}`;
  }

  if (type === "event_keyword") {
    return `对象组 ${targetRef} 的事件包含 ${expectedValue}`;
  }

  if (type === "related_object_status") {
    const related = condition.expected_value as { resource?: string; object_name?: string | null; object_name_pattern?: string | null; match_any?: boolean; statuses?: string[] } | undefined;
    const objectName = related?.match_any === false && (related.object_name || related.object_name_pattern)
      ? ` ${related.object_name || related.object_name_pattern}`
      : " 任意对象";
    const statuses = related?.statuses?.join(", ") ?? "";
    return `对象组 ${targetRef} 的 ${related?.resource ?? "关联对象"}${objectName} 状态${operatorLabels[operator]} ${statuses}`;
  }

  return `对象组 ${targetRef} 满足 ${type} ${operator} ${expectedValue}`;
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
  if (template.targets.length === 0) {
    if (template.target_groups?.length) {
      return template.target_groups.map((target) => ({
        target_ref: target.ref,
        namespace: target.namespace,
        label_selector: target.label_selector ?? "",
        pod_name_pattern: target.name ?? "",
        resource_scope: target.object_scope ? [target.object_scope] : ["pods"],
      }));
    }

    return [createDefaultTarget()];
  }

  return template.targets.map((target) => ({
    target_ref: target.target_ref,
    namespace: target.namespace,
    label_selector: target.label_selector ?? "",
    pod_name_pattern: target.pod_name_pattern ?? "",
    resource_scope: target.resource_scope,
  }));
}

function toConditionDrafts(template: FaultTemplate): ConditionDraft[] {
  if (template.match_conditions.length === 0) {
    return [createDefaultCondition(template.targets[0]?.target_ref ?? "group-1")];
  }

  return template.match_conditions.map((condition) => {
    if (condition.condition_type === "related_object_status") {
      const value = (condition.expected_value ?? {}) as {
        resource?: string;
        object_name?: string | null;
        object_name_pattern?: string | null;
        match_any?: boolean;
        statuses?: string[];
      };
      return {
        target_ref: condition.target_ref,
        condition_type: condition.condition_type,
        operator: condition.operator,
        value_text: (value.statuses ?? []).join(", "),
        related_resource: value.resource ?? "services",
        related_match_any: value.match_any !== false,
        related_object_name: String(value.object_name ?? value.object_name_pattern ?? ""),
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
      related_match_any: true,
      related_object_name: "",
      enabled: condition.enabled,
    };
  });
}

function getTemplateValidation(args: {
  name: string;
  scenario: string;
  targets: TargetDraft[];
  conditions: ConditionDraft[];
  reason: string;
  suggestion: string;
}) {
  const issues: Record<StepKey, string[]> = {
    basic: [],
    targets: [],
    conditions: [],
    advice: [],
    preview: [],
  };

  if (args.name.trim().length === 0) {
    issues.basic.push("请填写模板名称");
  }
  if (args.scenario.trim().length === 0) {
    issues.basic.push("请填写场景标识");
  }

  args.targets.forEach((target, index) => {
    if (target.target_ref.trim().length === 0) {
      issues.targets.push(`对象组 ${index + 1} 缺少对象组标识`);
    }
    if (target.namespace.trim().length === 0) {
      issues.targets.push(`对象组 ${index + 1} 缺少名称空间`);
    }
  });

  args.conditions.forEach((condition, index) => {
    if (condition.target_ref.trim().length === 0) {
      issues.conditions.push(`条件 ${index + 1} 缺少绑定对象组`);
    }
    if (condition.condition_type === "related_object_status" && !condition.related_match_any && condition.related_object_name.trim().length === 0) {
      issues.conditions.push(`条件 ${index + 1} 缺少关联对象名称`);
    }
    if (condition.value_text.trim().length === 0) {
      issues.conditions.push(`条件 ${index + 1} 缺少目标值`);
    }
  });

  if (args.reason.trim().length === 0) {
    issues.advice.push("请填写诊断原因");
  }
  if (args.suggestion.trim().length === 0) {
    issues.advice.push("请填写处理建议");
  }

  return issues;
}

type TargetScopeEditorProps = {
  target: TargetDraft;
  index: number;
  totalTargets: number;
  namespaceOptions: string[];
  onUpdate: (index: number, patch: Partial<TargetDraft>) => void;
  onRemove: (index: number) => void;
};

function TargetScopeEditor({ target, index, totalTargets, namespaceOptions, onUpdate, onRemove }: TargetScopeEditorProps) {
  const { data: labelDiscovery, loading: labelLoading, error: labelError } = useDiscoverNamespaceLabels(target.namespace);
  const labelOptions = labelDiscovery?.labels ?? [];
  const namespaceValues = target.namespace && !namespaceOptions.includes(target.namespace)
    ? [target.namespace, ...namespaceOptions]
    : namespaceOptions;

  return (
    <details className="template-details-card template-target-card" open>
      <summary>
        <span>对象组 {index + 1}：{target.target_ref || "未命名对象组"}</span>
        <span className="section-tip">{target.namespace || "待选名称空间"}</span>
      </summary>
      <div className="template-details-body">
        <div className="section-header">
          <strong>目标范围</strong>
          <button type="button" className="mini-button button-danger" disabled={totalTargets === 1} onClick={() => onRemove(index)}>
            删除对象组
          </button>
        </div>
        <div className="template-form-grid">
          <label className="template-field">
            对象组标识
            <input
              className="template-input"
              aria-label={`对象组标识 ${index + 1}`}
              value={target.target_ref}
              onChange={(event) => onUpdate(index, { target_ref: event.target.value })}
              placeholder="例如：api"
            />
          </label>
          <label className="template-field">
            名称空间
            <select
              className="template-input"
              aria-label={index === 0 ? "名称空间" : `名称空间 ${index + 1}`}
              value={target.namespace}
              onChange={(event) => onUpdate(index, { namespace: event.target.value, label_selector: "" })}
            >
              <option value="">请选择名称空间</option>
              {namespaceValues.map((namespace) => (
                <option key={namespace} value={namespace}>{namespace}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="template-label-row">
          <label className="template-field">
            Label Selector
            <select
              className="template-input"
              aria-label={`Label Selector ${index + 1}`}
              value={target.label_selector}
              onChange={(event) => onUpdate(index, { label_selector: event.target.value })}
              disabled={!target.namespace}
            >
              <option value="">{labelLoading ? "正在发现标签..." : "请选择 Label Selector"}</option>
              {target.label_selector && !labelOptions.some((item) => item.selector === target.label_selector) ? (
                <option value={target.label_selector}>{target.label_selector}</option>
              ) : null}
              {labelOptions.map((item) => (
                <option key={item.selector} value={item.selector}>
                  {item.selector}（{item.pod_count} 个 Pod）
                </option>
              ))}
            </select>
          </label>
          <label className="template-field">
            手动 Label Selector
            <input
              className="template-input"
              aria-label={`手动 Label Selector ${index + 1}`}
              value={target.label_selector}
              onChange={(event) => onUpdate(index, { label_selector: event.target.value })}
              placeholder="例如：app=gateway"
            />
          </label>
        </div>
        {labelError ? <p className="inline-note">Label 发现失败：{labelError}</p> : null}
      </div>
    </details>
  );
}

function TemplateDetailDrawer({ template, onClose }: { template: FaultTemplate; onClose: () => void }) {
  const targetGroups = getTargetGroups(template);

  return (
    <div className="evidence-drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside className="evidence-drawer" aria-label={`${template.name} 模板详情`} onMouseDown={(event) => event.stopPropagation()}>
        <div className="section-header">
          <div>
            <h3>{template.name}</h3>
            <p className="inline-note">{template.scenario} / {String(template.joint_rule?.operator ?? "AND")}</p>
          </div>
          <button type="button" onClick={onClose}>关闭</button>
        </div>
        <section className="panel panel-muted">
          <div className="section-header">
            <h4>对象组</h4>
            <StatusBadge status={template.enabled ? "enabled" : "disabled"} />
          </div>
          <div className="template-detail-list">
            {targetGroups.map((group, index) => (
              <div key={`${template.id}-detail-group-${index}`} className="template-detail-row">
                <span className="ellipsis-cell" title={group.ref}>{group.ref}</span>
                <span className="ellipsis-cell" title={group.namespace}>{group.namespace}</span>
                <span className="ellipsis-cell" title={group.label_selector ?? ""}>{group.label_selector || "无 Label"}</span>
              </div>
            ))}
          </div>
        </section>
        <section className="panel panel-muted">
          <h4>匹配条件</h4>
          <div className="condition-list">
            {template.match_conditions.map((condition, index) => (
              <div key={`${template.id}-detail-condition-${index}`} className="condition-item">
                {describeCondition(condition as { target_ref?: string; condition_type?: string; operator?: string; expected_value?: unknown })}
              </div>
            ))}
          </div>
        </section>
        <section className="panel panel-muted">
          <h4>原因与建议</h4>
          <p><strong>判断原因：</strong>{template.reason}</p>
          <p><strong>处理意见：</strong>{template.suggestion}</p>
          {template.command ? <pre className="log-block code-block-scroll">{template.command}</pre> : null}
          {template.risk_note ? <p><strong>风险说明：</strong>{template.risk_note}</p> : null}
        </section>
      </aside>
    </div>
  );
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
  const { data: namespaceDiscovery } = useDiscoverNamespaces();

  const [editingId, setEditingId] = useState<number | null>(null);
  const [activeStep, setActiveStep] = useState<StepKey>("basic");
  const [modalType, setModalType] = useState<ModalType>(null);
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
  const [selectedDetail, setSelectedDetail] = useState<FaultTemplate | null>(null);

  const validation = useMemo(
    () => getTemplateValidation({ name, scenario, targets, conditions, reason, suggestion }),
    [name, scenario, targets, conditions, reason, suggestion],
  );
  const validationEntries = stepDefinitions
    .map((step) => validation[step.key].map((issue) => ({ step, issue })))
    .flat();
  const currentStepIndex = stepDefinitions.findIndex((step) => step.key === activeStep);
  const activeStepDefinition = stepDefinitions[currentStepIndex];
  const namespaceOptions = useMemo(
    () => (namespaceDiscovery?.namespaces ?? []).map((item) => item.name),
    [namespaceDiscovery],
  );

  function resetForm() {
    setEditingId(null);
    setActiveStep("basic");
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
    setModalType(null);
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
          match_any: condition.related_match_any,
          object_name: condition.related_match_any ? null : condition.related_object_name.trim() || null,
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
    if (validationEntries.length > 0) {
      setActiveStep(validationEntries[0].step.key);
      setMessage(`还缺这些内容：${validationEntries.map((item) => `${item.step.title} - ${item.issue}`).join("；")}`);
      return;
    }

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

  function startCreate() {
    setEditingId(null);
    setActiveStep("basic");
    setModalType("editor");
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
    setMessage(null);
  }

  function startEdit(template: FaultTemplate) {
    setEditingId(template.id);
    setActiveStep("basic");
    setModalType("editor");
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
            next.related_match_any = true;
            next.related_object_name = "";
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

  async function handleOpenExport() {
    const exported = await exportAll();
    setExportText(formatJson(exported));
    setModalType("export");
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
    setModalType(null);
  }

  function moveStep(direction: "prev" | "next") {
    const nextIndex = direction === "prev" ? currentStepIndex - 1 : currentStepIndex + 1;
    if (nextIndex < 0 || nextIndex >= stepDefinitions.length) {
      return;
    }
    setActiveStep(stepDefinitions[nextIndex].key);
  }

  if (loading) {
    return <p>加载中...</p>;
  }

  return (
    <section className="page-section">
      {error ? <p>操作失败：{error}</p> : null}
      {message ? <p className="inline-note">{message}</p> : null}

      <section className="panel">
        <div className="section-header">
          <div>
            <h3>模板列表</h3>
            <p className="inline-note">共 {data.length} 个模板</p>
          </div>
          <div className="button-row">
            <button type="button" onClick={startCreate}>新增模板</button>
            <button type="button" className="mini-button button-success" onClick={() => setModalType("import")}>
              导入模板
            </button>
            <button type="button" className="mini-button button-success" onClick={() => void handleOpenExport()}>
              导出模板
            </button>
          </div>
        </div>
        <div className="table-scroll-shell">
          <table className="compact-table">
            <thead>
              <tr>
                <th>模板</th>
                <th>状态</th>
                <th>摘要</th>
                <th>对象组 / 条件</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {data.map((item) => {
                const targetGroups = getTargetGroups(item);
                return (
                  <tr key={item.id}>
                    <td>
                      <div className="stack-list">
                        <strong>{item.name}</strong>
                        <span className="inline-note">{String(item.joint_rule?.operator ?? "AND")}</span>
                      </div>
                    </td>
                    <td>
                      <StatusBadge status={item.enabled ? "enabled" : "disabled"} />
                    </td>
                    <td>
                      <span className="ellipsis-cell" title={item.reason}>{item.reason}</span>
                    </td>
                    <td>{targetGroups.length} / {item.match_conditions.length}</td>
                    <td>
                      <div className="button-row">
                        <button type="button" className="mini-button" disabled={saving} onClick={() => setSelectedDetail(item)}>详情</button>
                        <button type="button" className="mini-button" disabled={saving} onClick={() => startEdit(item)}>编辑</button>
                        <button type="button" className={`mini-button${item.enabled ? " button-danger" : ""}`} disabled={saving} onClick={() => void setEnabled(item.id, !item.enabled)}>{item.enabled ? "停用" : "启用"}</button>
                        <button type="button" className="mini-button button-danger" disabled={saving} onClick={() => void remove(item.id)}>删除</button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {selectedDetail ? <TemplateDetailDrawer template={selectedDetail} onClose={() => setSelectedDetail(null)} /> : null}

      {modalType === "editor" ? (
        <div className="modal-backdrop" role="presentation">
          <section className="modal-card modal-card-polished modal-card-wide" role="dialog" aria-modal="true" aria-label="模板录入器">
            <div className="section-header">
              <div>
                <p className="eyebrow">当前步骤</p>
                <h3>{activeStepDefinition.title}</h3>
                <p className="inline-note">{activeStepDefinition.description}</p>
              </div>
              <div className="secondary-action-row">
                <StatusBadge status={saving ? "warning" : editingId !== null ? "enabled" : "info"} />
                <button type="button" className="mini-button" onClick={resetForm}>关闭</button>
              </div>
            </div>
            <div className="template-stepper" aria-label="模板录入步骤">
              {stepDefinitions.map((step, index) => (
                <button
                  key={step.key}
                  type="button"
                  className={`template-step-chip ${step.key === activeStep ? "template-step-chip-active" : ""}`}
                  onClick={() => setActiveStep(step.key)}
                >
                  <span>{index + 1}</span>
                  {step.title}
                </button>
              ))}
            </div>
            {validationEntries.length > 0 && activeStep === "preview" ? (
              <section className="panel template-warning-panel">
                <h4>保存前还缺内容</h4>
                <ul className="plain-list">
                  {validationEntries.map((item) => (
                    <li key={`${item.step.key}-${item.issue}`}>{item.step.title}：{item.issue}</li>
                  ))}
                </ul>
              </section>
            ) : null}

            {activeStep === "basic" ? (
            <div className="page-section template-editor-form">
              <div className="template-form-grid">
              <label className="template-field">
                模板名称
                <input className="template-input" aria-label="模板名称" value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：网关 502 故障" />
              </label>
              <label className="template-field">
                场景标识
                <input className="template-input" aria-label="场景标识" value={scenario} onChange={(event) => setScenario(event.target.value)} placeholder="例如：gateway_502" />
              </label>
              </div>
              <label className="template-toggle-field">
                <input type="checkbox" checked={enabled} onChange={(event) => setTemplateEnabled(event.target.checked)} />
                模板启用
              </label>
            </div>
          ) : null}

          {activeStep === "targets" ? (
            <div className="page-section">
              <div className="section-header">
                <h3>对象组</h3>
                <button type="button" onClick={addTarget}>新增对象组</button>
              </div>
              <div className="stack-list">
                {targets.map((target, index) => (
                  <TargetScopeEditor
                    key={`target-${index}`}
                    target={target}
                    index={index}
                    totalTargets={targets.length}
                    namespaceOptions={namespaceOptions}
                    onUpdate={updateTarget}
                    onRemove={removeTarget}
                  />
                ))}
              </div>
            </div>
          ) : null}

          {activeStep === "conditions" ? (
            <div className="page-section">
              <section className="panel template-hint-panel">
                <h4>条件关系说明</h4>
                <p>AND：所有启用条件都满足才命中故障。</p>
                <p>OR：任一启用条件满足就命中故障。</p>
                <label className="template-field">
                  条件关系
                  <select className="template-input" aria-label="条件关系" value={jointOperator} onChange={(event) => setJointOperator(event.target.value as "AND" | "OR")}>
                    <option value="AND">AND：所有条件都满足才命中</option>
                    <option value="OR">OR：任一条件满足就命中</option>
                  </select>
                </label>
              </section>
              <div className="section-header">
                <h3>条件块</h3>
                <button type="button" onClick={addCondition}>新增条件</button>
              </div>
              <div className="stack-list">
                {conditions.map((condition, index) => (
                  <details key={`condition-${index}`} className="template-details-card" open>
                    <summary>
                      <span>条件 {index + 1}：{conditionTypeLabels[condition.condition_type]}</span>
                      <span className="section-tip">{condition.target_ref}</span>
                    </summary>
                    <div className="template-details-body">
                      <div className="section-header">
                        <strong>条件配置</strong>
                        <button type="button" className="button-danger" disabled={conditions.length === 1} onClick={() => removeCondition(index)}>
                          删除条件
                        </button>
                      </div>
                      <label className="template-field">
                        绑定对象组
                        <select className="template-input" aria-label={index === 0 ? "绑定对象组" : `绑定对象组 ${index + 1}`} value={condition.target_ref} onChange={(event) => updateCondition(index, { target_ref: event.target.value })}>
                          {targets.map((target) => (
                            <option key={target.target_ref} value={target.target_ref}>{target.target_ref}</option>
                          ))}
                        </select>
                      </label>
                      <label className="template-field">
                        条件类型
                        <select
                          className="template-input"
                          aria-label={index === 0 ? "条件类型" : `条件类型 ${index + 1}`}
                          value={condition.condition_type}
                          onChange={(event) => updateCondition(index, { condition_type: event.target.value as TemplateConditionType })}
                        >
                          {Object.entries(conditionTypeLabels).map(([value, label]) => (
                            <option key={value} value={value}>{label}</option>
                          ))}
                        </select>
                      </label>
                      <label className="template-field">
                        匹配方式
                        <select
                          className="template-input"
                          aria-label={index === 0 ? "匹配方式" : `匹配方式 ${index + 1}`}
                          value={condition.operator}
                          onChange={(event) => updateCondition(index, { operator: event.target.value as TemplateConditionOperator })}
                        >
                          {getOperators(condition.condition_type).map((operator) => (
                            <option key={`${condition.condition_type}-${operator}`} value={operator}>{operatorLabels[operator]}</option>
                          ))}
                        </select>
                      </label>
                      {condition.condition_type === "related_object_status" ? (
                        <>
                          <label className="template-field">
                            关联资源类型
                            <select
                              className="template-input"
                              aria-label={index === 0 ? "关联资源类型" : `关联资源类型 ${index + 1}`}
                              value={condition.related_resource}
                              onChange={(event) => updateCondition(index, { related_resource: event.target.value, value_text: "" })}
                            >
                              {relatedResourceOptions.map((item) => (
                                <option key={item.value} value={item.value}>{item.label}</option>
                              ))}
                            </select>
                          </label>
                          <label className="template-toggle-field template-toggle-field-plain">
                            <input
                              type="checkbox"
                              checked={condition.related_match_any}
                              onChange={(event) => updateCondition(index, { related_match_any: event.target.checked })}
                            />
                            任意对象
                          </label>
                          {!condition.related_match_any ? (
                            <label className="template-field">
                              对象名称
                              <input
                                className="template-input"
                                aria-label={index === 0 ? "对象名称" : `对象名称 ${index + 1}`}
                                value={condition.related_object_name}
                                onChange={(event) => updateCondition(index, { related_object_name: event.target.value })}
                                placeholder="例如：gateway-svc"
                              />
                            </label>
                          ) : null}
                          <label className="template-field">
                            状态值
                            <select
                              className="template-input"
                              aria-label={index === 0 ? "状态值" : `状态值 ${index + 1}`}
                              value={condition.value_text}
                              onChange={(event) => updateCondition(index, { value_text: event.target.value })}
                            >
                              <option value="">请选择状态</option>
                              {(relatedObjectStatusOptions[condition.related_resource] ?? relatedObjectStatusOptions.services).map((status) => (
                                <option key={status} value={status}>{status}</option>
                              ))}
                            </select>
                          </label>
                        </>
                      ) : condition.condition_type === "pod_status" ? (
                        <label className="template-field">
                          目标值
                          <select
                            className="template-input"
                            aria-label={index === 0 ? "目标值" : `目标值 ${index + 1}`}
                            value={condition.value_text}
                            onChange={(event) => updateCondition(index, { value_text: event.target.value })}
                          >
                            <option value="">请选择 Pod 状态</option>
                            {podStatusOptions.map((status) => (
                              <option key={status} value={status}>{status}</option>
                            ))}
                          </select>
                        </label>
                      ) : (
                        <label className="template-field">
                          目标值
                          <input
                            className="template-input"
                            aria-label={index === 0 ? "目标值" : `目标值 ${index + 1}`}
                            value={condition.value_text}
                            onChange={(event) => updateCondition(index, { value_text: event.target.value })}
                            placeholder={condition.operator === "in" ? "多个值请用逗号分隔" : condition.condition_type === "restart_count" ? "例如：3" : "请输入目标值"}
                          />
                        </label>
                      )}
                      <label>
                        <input type="checkbox" checked={condition.enabled} onChange={(event) => updateCondition(index, { enabled: event.target.checked })} />
                        条件启用
                      </label>
                      <div className="condition-item">{describeDraftCondition(condition)}</div>
                    </div>
                  </details>
                ))}
              </div>
            </div>
          ) : null}

          {activeStep === "advice" ? (
            <div className="page-section template-editor-form">
              <label className="template-field">
                诊断原因
                <textarea className="template-input template-textarea-large" aria-label="诊断原因" value={reason} onChange={(event) => setReason(event.target.value)} rows={5} placeholder="例如：网关进程无法连接上游服务" />
              </label>
              <label className="template-field">
                处理建议
                <textarea className="template-input template-textarea-large" aria-label="处理建议" value={suggestion} onChange={(event) => setSuggestion(event.target.value)} rows={5} placeholder="例如：检查上游 Service 和配置" />
              </label>
              <label className="template-field">
                建议命令
                <textarea className="template-input template-code-textarea" aria-label="建议命令" value={command} onChange={(event) => setCommand(event.target.value)} rows={4} placeholder="例如：kubectl logs -n xxx deploy/xxx" />
              </label>
              <label className="template-field">
                风险说明
                <textarea className="template-input template-textarea-large" aria-label="风险说明" value={riskNote} onChange={(event) => setRiskNote(event.target.value)} rows={4} placeholder="例如：只读命令，可直接执行" />
              </label>
            </div>
          ) : null}

          {activeStep === "preview" ? (
            <div className="page-section">
              <section className="panel">
                <div className="section-header">
                  <h3>模板摘要</h3>
                  <StatusBadge status={enabled ? "enabled" : "disabled"} />
                </div>
                <p><strong>{name || "未填写模板名称"}</strong></p>
                <p className="inline-note">场景：{scenario || "未填写场景标识"}</p>
                <p className="inline-note">条件关系：{jointOperator}</p>
              </section>
              <section className="panel">
                <h3>对象组摘要</h3>
                <div className="stack-list">
                  {targets.map((target, index) => (
                    <div key={`preview-target-${index}`} className="stack-item">
                      <strong>{target.target_ref || `对象组 ${index + 1}`}</strong>
                      <p>{target.namespace || "待填写名称空间"}{target.label_selector ? ` / ${target.label_selector}` : ""}</p>
                    </div>
                  ))}
                </div>
              </section>
              <section className="panel">
                <h3>条件摘要</h3>
                <div className="condition-list">
                  {conditions.map((condition, index) => (
                    <div key={`preview-condition-${index}`} className="condition-item">
                      {describeDraftCondition(condition)}
                    </div>
                  ))}
                </div>
              </section>
              <section className="panel">
                <h3>原因与建议摘要</h3>
                <p><strong>诊断原因：</strong>{reason || "未填写"}</p>
                <p><strong>处理建议：</strong>{suggestion || "未填写"}</p>
                {command ? <p><strong>建议命令：</strong>{command}</p> : null}
                {riskNote ? <p><strong>风险说明：</strong>{riskNote}</p> : null}
              </section>
            </div>
          ) : null}

          <div className="button-row template-action-row">
            <button className="template-secondary-button" type="button" onClick={() => moveStep("prev")} disabled={currentStepIndex === 0 || saving}>上一步</button>
            {activeStep !== "preview" ? (
              <button className="template-primary-button" type="button" onClick={() => moveStep("next")} disabled={currentStepIndex === stepDefinitions.length - 1 || saving}>下一步</button>
            ) : null}
            <button className="template-primary-button" type="button" disabled={saving} onClick={() => void handleSubmit()}>
              {saving ? "处理中..." : editingId !== null ? "保存模板" : "新增模板"}
            </button>
          </div>
          </section>
        </div>
      ) : null}

      {modalType === "import" ? (
        <div className="modal-backdrop" role="presentation">
          <section className="modal-card modal-card-polished" role="dialog" aria-modal="true" aria-label="导入模板">
            <div className="section-header">
              <div>
                <h3>导入模板</h3>
                <p className="inline-note">只在迁移配置时使用，关闭后不会影响当前录入步骤。</p>
              </div>
              <button type="button" onClick={() => setModalType(null)}>关闭</button>
            </div>
            <label>
              导入模板 JSON
              <textarea className="modal-code-input code-block-scroll" aria-label="导入模板 JSON" value={importText} onChange={(event) => setImportText(event.target.value)} rows={12} placeholder='[{"name":"..."}]' />
            </label>
            <div className="button-row">
              <button type="button" disabled={saving || importText.trim().length === 0} onClick={() => void handleImport()}>导入模板</button>
              <button type="button" onClick={() => setModalType(null)}>取消</button>
            </div>
          </section>
        </div>
      ) : null}

      {modalType === "export" ? (
        <div className="modal-backdrop" role="presentation">
          <section className="modal-card modal-card-polished" role="dialog" aria-modal="true" aria-label="导出模板">
            <div className="section-header">
              <div>
                <h3>导出模板</h3>
                <p className="inline-note">导出结果只用于跨环境迁移，不会改变当前录入状态。</p>
              </div>
              <button type="button" onClick={() => setModalType(null)}>关闭</button>
            </div>
            <label>
              已导出 JSON
              <textarea className="modal-code-input code-block-scroll" aria-label="已导出 JSON" value={exportText} readOnly rows={14} />
            </label>
            <div className="button-row">
              <button type="button" onClick={() => setModalType(null)}>关闭</button>
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}
