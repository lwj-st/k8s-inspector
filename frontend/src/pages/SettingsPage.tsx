import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  ApiClientError,
  createInspectionPlan,
  createNotificationChannel,
  deleteInspectionPlan,
  deleteNotificationChannel,
  getInspectionRun,
  getSettings,
  getSystemStatus,
  listRequiredComponentCandidates,
  listInspectionPlans,
  listNotificationChannels,
  runInspectionPlan,
  testNotificationChannel,
  updateInspectionPlan,
  updateNotificationChannel,
  updateSettings,
} from "../api/client";
import type {
  DataRetentionSettings,
  InspectionPlan,
  InspectionPlanCreate,
  InspectionRun,
  InspectionRunDetail,
  InspectionThresholds,
  NotificationChannel,
  NotificationChannelCreate,
  NotificationChannelType,
  RequiredComponentCandidate,
  RequiredComponentPolicy,
  SettingsResponse,
  SystemComponentStatus,
  SystemStatus,
} from "../api/types";
import { CoveragePanel } from "../components/CoveragePanel";
import { StatusBadge } from "../components/StatusBadge";

type SettingsTab = "plans" | "notifications" | "policy" | "status" | "basic";
type VisibleInspectionRun = InspectionRun & {
  check_results?: InspectionRunDetail["check_results"];
};

const tabs: Array<{ id: SettingsTab; label: string }> = [
  { id: "plans", label: "巡检计划" },
  { id: "notifications", label: "通知渠道" },
  { id: "policy", label: "巡检策略" },
  { id: "status", label: "系统状态" },
  { id: "basic", label: "基础配置" },
];

const intervalLabels: Record<InspectionPlanCreate["schedule"]["interval"], string> = {
  "5m": "每 5 分钟",
  "10m": "每 10 分钟",
  "30m": "每 30 分钟",
  "60m": "每 60 分钟",
  daily: "每日",
};

function requiredComponentKey(component: RequiredComponentPolicy) {
  return `${component.namespace}|${component.kind.toLowerCase()}|${component.label_selector}`;
}

function requiredComponentLabel(component: RequiredComponentPolicy) {
  return `${component.name}（${component.namespace} · ${component.kind} · ${component.label_selector}）`;
}

const thresholdFields: Array<{
  key: keyof InspectionThresholds;
  label: string;
  unit: string;
  group: string;
}> = [
  { key: "tls_warning_days", label: "TLS 到期警告", unit: "天", group: "TLS" },
  { key: "tls_critical_days", label: "TLS 到期严重", unit: "天", group: "TLS" },
  { key: "pvc_pending_warning_minutes", label: "PVC Pending 警告", unit: "分钟", group: "存储" },
  { key: "pvc_pending_critical_minutes", label: "PVC Pending 严重", unit: "分钟", group: "存储" },
  { key: "pv_released_stale_hours", label: "PV Released 清理提示", unit: "小时", group: "存储" },
  { key: "job_incomplete_info_minutes", label: "Job 长时间未完成提示", unit: "分钟", group: "Job" },
  { key: "resource_usage_warning_percent", label: "资源使用警告", unit: "% limit", group: "资源使用" },
  { key: "resource_usage_consecutive_cycles", label: "连续超阈值周期", unit: "次", group: "资源使用" },
  { key: "pod_terminating_warning_minutes", label: "Pod Terminating 警告", unit: "分钟", group: "Pod" },
  { key: "pod_restart_window_minutes", label: "Pod 重启统计窗口", unit: "分钟", group: "Pod" },
  { key: "pod_restart_delta", label: "Pod 重启增量", unit: "次", group: "Pod" },
  { key: "warning_event_window_minutes", label: "Warning Event 窗口", unit: "分钟", group: "Event" },
  { key: "node_not_ready_grace_seconds", label: "Node NotReady 宽限", unit: "秒", group: "Node" },
];

const retentionFields: Array<{
  key: keyof DataRetentionSettings;
  label: string;
  help: string;
}> = [
  { key: "inspection_run_days", label: "巡检运行记录保留", help: "包括可以安全清理的关联数据" },
  { key: "recovered_issue_days", label: "已恢复问题保留", help: "开放或仍活跃的问题不会清理" },
  { key: "notification_delivery_days", label: "通知投递记录保留", help: "用于排查历史投递结果" },
  { key: "security_audit_days", label: "安全审计记录保留", help: "用于追溯登录和敏感操作" },
];

function readableError(reason: unknown) {
  if (reason instanceof ApiClientError) {
    return `${reason.message}${reason.requestId ? `（请求 ID：${reason.requestId}）` : ""}`;
  }
  return reason instanceof Error ? reason.message : "操作失败";
}

function displayTime(value?: string | null) {
  if (!value) {
    return "--";
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function emptyPlanDraft(): InspectionPlanCreate {
  return {
    name: "",
    enabled: true,
    scope: { type: "global", namespaces: [] },
    schedule: { interval: "10m", daily_at: null, timezone: "Asia/Shanghai" },
    include_template_matching: true,
    notification_channel_ids: [],
  };
}

function emptyChannelDraft(): NotificationChannelCreate {
  return {
    name: "",
    type: "generic_webhook",
    enabled: true,
    webhook_url: "",
    signing_secret: null,
    mention_all_on_critical: false,
    timeout_seconds: 5,
  };
}

function SystemComponentCard({
  label,
  component,
}: {
  label: string;
  component: SystemComponentStatus;
}) {
  return (
    <article className="system-component-card">
      <div className="section-header">
        <strong>{label}</strong>
        <StatusBadge status={component.state} />
      </div>
      <p>{component.message}</p>
      <small>检查时间：{displayTime(component.checked_at)}</small>
      {Object.keys(component.details).length > 0 ? (
        <details>
          <summary>查看详情</summary>
          <dl className="facts-grid">
            {Object.entries(component.details).map(([key, value]) => (
              <div key={key}><dt>{key}</dt><dd>{String(value ?? "--")}</dd></div>
            ))}
          </dl>
        </details>
      ) : null}
    </article>
  );
}

export function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab") as SettingsTab | null;
  const activeTab = tabs.some((tab) => tab.id === requestedTab) ? requestedTab as SettingsTab : "plans";
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [plans, setPlans] = useState<InspectionPlan[]>([]);
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadErrors, setLoadErrors] = useState<string[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [planEditingId, setPlanEditingId] = useState<number | null>(null);
  const [planDraft, setPlanDraft] = useState<InspectionPlanCreate>(emptyPlanDraft);
  const [planNamespaces, setPlanNamespaces] = useState("");
  const [visiblePlanRuns, setVisiblePlanRuns] = useState<Record<number, VisibleInspectionRun>>({});
  const [channelEditingId, setChannelEditingId] = useState<number | null>(null);
  const [channelDraft, setChannelDraft] = useState<NotificationChannelCreate>(emptyChannelDraft);
  const [clearSigningSecret, setClearSigningSecret] = useState(false);
  const [componentCandidates, setComponentCandidates] = useState<RequiredComponentCandidate[]>([]);
  const [componentCandidateLoading, setComponentCandidateLoading] = useState(false);
  const [componentCandidateError, setComponentCandidateError] = useState<string | null>(null);
  const [selectedComponentKey, setSelectedComponentKey] = useState("");
  const [componentDraft, setComponentDraft] = useState<RequiredComponentPolicy>({
    name: "",
    namespace: "",
    kind: "Deployment",
    label_selector: "",
    enabled: true,
  });

  const reload = useCallback(async () => {
    setLoading(true);
    setLoadErrors([]);
    const results = await Promise.allSettled([
      getSettings(),
      getSystemStatus(),
      listInspectionPlans(),
      listNotificationChannels(),
    ]);
    const errors: string[] = [];
    if (results[0].status === "fulfilled") {
      setSettings(results[0].value);
    } else {
      errors.push(`基础设置：${readableError(results[0].reason)}`);
    }
    if (results[1].status === "fulfilled") {
      setSystemStatus(results[1].value);
    } else {
      errors.push(`系统状态：${readableError(results[1].reason)}`);
    }
    if (results[2].status === "fulfilled") {
      setPlans(results[2].value.items);
    } else {
      errors.push(`巡检计划：${readableError(results[2].reason)}`);
    }
    if (results[3].status === "fulfilled") {
      setChannels(results[3].value.items);
    } else {
      errors.push(`通知渠道：${readableError(results[3].reason)}`);
    }
    setLoadErrors(errors);
    setLoading(false);
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (activeTab !== "policy") {
      return;
    }
    let cancelled = false;
    setComponentCandidateLoading(true);
    setComponentCandidateError(null);
    void listRequiredComponentCandidates()
      .then((result) => {
        if (!cancelled) {
          setComponentCandidates(result.items);
        }
      })
      .catch((reason) => {
        if (!cancelled) {
          setComponentCandidateError(readableError(reason));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setComponentCandidateLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeTab]);

  const activePlanRuns = Object.entries(visiblePlanRuns).filter(([, run]) =>
    run.status === "queued" || run.status === "running");
  const activePlanRunKey = activePlanRuns
    .map(([planId, run]) => `${planId}:${run.id}`)
    .sort()
    .join(",");

  useEffect(() => {
    if (!activePlanRunKey) {
      return;
    }
    let cancelled = false;
    const trackedRuns = activePlanRuns.map(([planId, run]) => ({
      planId: Number(planId),
      runId: run.id,
    }));

    async function refreshActiveRuns() {
      await Promise.all(trackedRuns.map(async ({ planId, runId }) => {
        try {
          const run = await getInspectionRun(runId);
          if (cancelled) {
            return;
          }
          setVisiblePlanRuns((current) => ({ ...current, [planId]: run }));
          setPlans((current) => current.map((plan) => plan.id === planId
            ? {
              ...plan,
              last_run_status: run.status,
              last_run_at: run.started_at ?? plan.last_run_at,
            }
            : plan));
        } catch (reason) {
          if (!cancelled) {
            setActionError(`执行 #${runId} 状态刷新失败：${readableError(reason)}`);
          }
        }
      }));
    }

    void refreshActiveRuns();
    const timer = window.setInterval(() => void refreshActiveRuns(), 2_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activePlanRunKey]);

  function selectTab(tab: SettingsTab) {
    setSearchParams({ tab });
    setMessage(null);
    setActionError(null);
  }

  async function perform(action: () => Promise<void>, successMessage: string) {
    setSaving(true);
    setMessage(null);
    setActionError(null);
    try {
      await action();
      setMessage(successMessage);
    } catch (reason) {
      setActionError(readableError(reason));
      throw reason;
    } finally {
      setSaving(false);
    }
  }

  async function savePlan(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const namespaces = planNamespaces.split(",").map((item) => item.trim()).filter(Boolean);
    const payload: InspectionPlanCreate = {
      ...planDraft,
      name: planDraft.name.trim(),
      scope: planDraft.scope.type === "global"
        ? { type: "global", namespaces: [] }
        : { type: "namespaces", namespaces },
      schedule: {
        ...planDraft.schedule,
        daily_at: planDraft.schedule.interval === "daily" ? planDraft.schedule.daily_at : null,
      },
    };
    if (!payload.name) {
      setActionError("请填写计划名称");
      return;
    }
    if (payload.scope.type === "namespaces" && payload.scope.namespaces.length === 0) {
      setActionError("指定名称空间范围至少填写一个名称空间");
      return;
    }
    try {
      await perform(async () => {
        if (planEditingId) {
          const updated = await updateInspectionPlan(planEditingId, payload);
          setPlans((current) => current.map((item) => item.id === updated.id ? updated : item));
        } else {
          const created = await createInspectionPlan(payload);
          setPlans((current) => [created, ...current]);
        }
        setPlanEditingId(null);
        setPlanDraft(emptyPlanDraft());
        setPlanNamespaces("");
      }, planEditingId ? "巡检计划已更新" : "巡检计划已创建");
    } catch {
      // perform 已保留表单并展示错误。
    }
  }

  function editPlan(plan: InspectionPlan) {
    setPlanEditingId(plan.id);
    setPlanDraft({
      name: plan.name,
      enabled: plan.enabled,
      scope: plan.scope,
      schedule: plan.schedule,
      include_template_matching: plan.include_template_matching,
      notification_channel_ids: plan.notification_channel_ids,
    });
    setPlanNamespaces(plan.scope.namespaces.join(", "));
    setActionError(null);
  }

  async function togglePlan(plan: InspectionPlan) {
    try {
      await perform(async () => {
        const updated = await updateInspectionPlan(plan.id, { enabled: !plan.enabled });
        setPlans((current) => current.map((item) => item.id === plan.id ? updated : item));
      }, plan.enabled ? "计划已停用" : "计划已启用");
    } catch {
      // 错误已展示。
    }
  }

  async function removePlan(plan: InspectionPlan) {
    if (!window.confirm(`删除计划“${plan.name}”？历史执行记录会保留。`)) {
      return;
    }
    try {
      await perform(async () => {
        await deleteInspectionPlan(plan.id);
        setPlans((current) => current.filter((item) => item.id !== plan.id));
      }, "计划已删除");
    } catch {
      // 错误已展示。
    }
  }

  async function runPlan(plan: InspectionPlan) {
    const currentRun = visiblePlanRuns[plan.id];
    if (
      plan.last_run_status === "queued"
      || plan.last_run_status === "running"
      || currentRun?.status === "queued"
      || currentRun?.status === "running"
    ) {
      setActionError("该计划已有等待执行或正在执行的任务，无需重复启动");
      return;
    }
    try {
      await perform(async () => {
        const run = await runInspectionPlan(plan.id);
        setVisiblePlanRuns((current) => ({ ...current, [plan.id]: run }));
        setPlans((current) => current.map((item) => item.id === plan.id
          ? {
            ...item,
            last_run_status: run.status,
            last_run_at: run.started_at ?? item.last_run_at,
          }
          : item));
      }, "巡检任务已受理");
    } catch {
      // 409 等错误已用中文展示。
    }
  }

  async function saveChannel(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!channelDraft.name.trim()) {
      setActionError("请填写渠道名称");
      return;
    }
    if (!channelEditingId && !channelDraft.webhook_url.trim()) {
      setActionError("请填写 Webhook 地址");
      return;
    }
    try {
      await perform(async () => {
        if (channelEditingId) {
          const updated = await updateNotificationChannel(channelEditingId, {
            name: channelDraft.name.trim(),
            enabled: channelDraft.enabled,
            ...(channelDraft.webhook_url.trim() ? { webhook_url: channelDraft.webhook_url.trim() } : {}),
            ...(channelDraft.signing_secret?.trim() ? { signing_secret: channelDraft.signing_secret.trim() } : {}),
            clear_signing_secret: clearSigningSecret,
            mention_all_on_critical: channelDraft.mention_all_on_critical,
            timeout_seconds: channelDraft.timeout_seconds,
          });
          setChannels((current) => current.map((item) => item.id === updated.id ? updated : item));
        } else {
          const created = await createNotificationChannel({
            ...channelDraft,
            name: channelDraft.name.trim(),
            webhook_url: channelDraft.webhook_url.trim(),
            signing_secret: channelDraft.signing_secret?.trim() || null,
          });
          setChannels((current) => [created, ...current]);
        }
        setChannelEditingId(null);
        setChannelDraft(emptyChannelDraft());
        setClearSigningSecret(false);
      }, channelEditingId ? "通知渠道已更新" : "通知渠道已创建");
    } catch {
      // 错误已展示。
    }
  }

  function editChannel(channel: NotificationChannel) {
    setChannelEditingId(channel.id);
    setChannelDraft({
      name: channel.name,
      type: channel.type,
      enabled: channel.enabled,
      webhook_url: "",
      signing_secret: null,
      mention_all_on_critical: channel.mention_all_on_critical,
      timeout_seconds: channel.timeout_seconds,
    });
    setClearSigningSecret(false);
    setActionError(null);
  }

  function changeMentionAll(enabled: boolean) {
    if (enabled && !window.confirm("开启后仅 critical 告警会提醒群内所有人，可能造成较强打扰。确认开启吗？")) {
      return;
    }
    setChannelDraft((current) => ({ ...current, mention_all_on_critical: enabled }));
  }

  function selectRequiredComponent(value: string) {
    setSelectedComponentKey(value);
    const selected = componentCandidates.find((item) => requiredComponentKey(item) === value);
    if (!selected) {
      setComponentDraft({ name: "", namespace: "", kind: "Deployment", label_selector: "", enabled: true });
      return;
    }
    setComponentDraft({
      name: selected.name,
      namespace: selected.namespace,
      kind: selected.kind,
      label_selector: selected.label_selector,
      enabled: true,
    });
    setActionError(null);
  }

  async function toggleChannel(channel: NotificationChannel) {
    try {
      await perform(async () => {
        const updated = await updateNotificationChannel(channel.id, { enabled: !channel.enabled });
        setChannels((current) => current.map((item) => item.id === channel.id ? updated : item));
      }, channel.enabled ? "通知渠道已停用" : "通知渠道已启用");
    } catch {
      // 错误已展示。
    }
  }

  async function removeChannel(channel: NotificationChannel) {
    if (!window.confirm(`删除通知渠道“${channel.name}”？`)) {
      return;
    }
    try {
      await perform(async () => {
        await deleteNotificationChannel(channel.id);
        setChannels((current) => current.filter((item) => item.id !== channel.id));
      }, "通知渠道已删除");
    } catch {
      // 错误已展示。
    }
  }

  async function testChannel(channel: NotificationChannel) {
    if (!window.confirm(`将向“${channel.name}”发送一条明确标识的测试通知，不会创建问题。继续吗？`)) {
      return;
    }
    setSaving(true);
    setMessage(null);
    setActionError(null);
    try {
      const result = await testNotificationChannel(channel.id);
      if (result.delivery.status === "succeeded") {
        setMessage(`${result.message}（已送达）`);
      } else if (result.delivery.status === "pending" || result.delivery.status === "delivering") {
        setMessage(`${result.message}（已受理，仍在投递或重试）`);
      } else {
        setActionError(`${result.message}（${result.delivery.status === "failed" ? "投递失败" : "未发送"}）`);
      }
    } catch (reason) {
      setActionError(readableError(reason));
    } finally {
      setSaving(false);
    }
  }

  function addRequiredComponent(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!settings) {
      return;
    }
    if (!componentDraft.name.trim() || !componentDraft.namespace.trim() || !componentDraft.kind.trim() || !componentDraft.label_selector.trim()) {
      setActionError("必需组件的名称、名称空间、Kind 和 Label Selector 均不能为空");
      return;
    }
    const duplicate = settings.inspection_policy.required_components.some((item) =>
      item.namespace === componentDraft.namespace.trim()
      && item.kind.toLowerCase() === componentDraft.kind.trim().toLowerCase()
      && item.label_selector === componentDraft.label_selector.trim());
    if (duplicate) {
      setActionError("相同定位规则已经存在");
      return;
    }
    setSettings({
      ...settings,
      inspection_policy: {
        ...settings.inspection_policy,
        required_components: [
          ...settings.inspection_policy.required_components,
          {
            ...componentDraft,
            name: componentDraft.name.trim(),
            namespace: componentDraft.namespace.trim(),
            kind: componentDraft.kind.trim(),
            label_selector: componentDraft.label_selector.trim(),
          },
        ],
      },
    });
    setComponentDraft({ name: "", namespace: "", kind: "Deployment", label_selector: "", enabled: true });
    setSelectedComponentKey("");
    setActionError(null);
  }

  function removeRequiredComponent(index: number) {
    if (!settings) {
      return;
    }
    setSettings({
      ...settings,
      inspection_policy: {
        ...settings.inspection_policy,
        required_components: settings.inspection_policy.required_components.filter((_, itemIndex) => itemIndex !== index),
      },
    });
  }

  function updateThreshold(key: keyof InspectionThresholds, value: number) {
    if (!settings) {
      return;
    }
    setSettings({
      ...settings,
      inspection_policy: {
        ...settings.inspection_policy,
        thresholds: { ...settings.inspection_policy.thresholds, [key]: value },
      },
    });
  }

  function updateRetention(key: keyof DataRetentionSettings, value: number) {
    if (!settings) {
      return;
    }
    setSettings({
      ...settings,
      inspection_policy: {
        ...settings.inspection_policy,
        retention: { ...settings.inspection_policy.retention, [key]: value },
      },
    });
  }

  async function savePolicy() {
    if (!settings) {
      return;
    }
    const thresholds = settings.inspection_policy.thresholds;
    if (thresholds.tls_critical_days > thresholds.tls_warning_days) {
      setActionError("TLS 严重阈值不能大于警告阈值");
      return;
    }
    if (thresholds.pvc_pending_warning_minutes > thresholds.pvc_pending_critical_minutes) {
      setActionError("PVC 警告阈值不能大于严重阈值");
      return;
    }
    const namespaceConcurrency = settings.inspection_policy.namespace_concurrency;
    if (!Number.isInteger(namespaceConcurrency) || namespaceConcurrency < 1 || namespaceConcurrency > 10) {
      setActionError("名称空间并发数必须是 1–10 的整数");
      return;
    }
    const maxLogPods = settings.inspection_policy.max_log_pods;
    if (!Number.isInteger(maxLogPods) || maxLogPods < 1 || maxLogPods > 1000) {
      setActionError("单次日志采集 Pod 上限必须是 1–1000 的整数");
      return;
    }
    const invalidRetention = retentionFields.find(({ key }) => {
      const value = settings.inspection_policy.retention[key];
      return !Number.isInteger(value) || value < 7 || value > 180;
    });
    if (invalidRetention) {
      setActionError(`${invalidRetention.label}必须是 7–180 天的整数`);
      return;
    }
    try {
      await perform(async () => {
        setSettings(await updateSettings(settings));
      }, "巡检策略已保存");
    } catch {
      // 错误已展示。
    }
  }

  async function saveBasicSettings(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!settings) {
      return;
    }
    const clusterId = settings.cluster_id.trim();
    if (!clusterId) {
      setActionError("集群标识不能为空");
      return;
    }
    if (clusterId.length > 128) {
      setActionError("集群标识不能超过 128 个字符");
      return;
    }
    try {
      await perform(async () => {
        const updated = await updateSettings({ ...settings, cluster_id: clusterId });
        setSettings(updated);
        setSystemStatus((current) => current ? { ...current, cluster_id: updated.cluster_id } : current);
      }, "基础配置已保存");
    } catch {
      // 错误已展示。
    }
  }

  const groupedThresholds = useMemo(() => {
    const groups = new Map<string, typeof thresholdFields>();
    for (const field of thresholdFields) {
      groups.set(field.group, [...(groups.get(field.group) ?? []), field]);
    }
    return Array.from(groups.entries());
  }, []);

  return (
    <section className="page-section settings-page">
      <header className="workbench-heading">
        <div>
          <p className="eyebrow">管理区</p>
          <h1>系统设置</h1>
          <p>计划、通知和巡检策略不会占用日常排障工作台。</p>
        </div>
        <button type="button" onClick={() => void reload()} disabled={loading}>刷新</button>
      </header>

      <nav className="settings-tabs" aria-label="系统设置分类">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={activeTab === tab.id ? "settings-tab settings-tab-active" : "settings-tab"}
            aria-current={activeTab === tab.id ? "page" : undefined}
            onClick={() => selectTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {loading ? <p aria-live="polite">正在加载系统设置…</p> : null}
      {loadErrors.length > 0 ? (
        <div className="feedback-banner feedback-warning" role="status">
          <strong>部分设置暂时不可用</strong>
          <ul>{loadErrors.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
      ) : null}
      {message ? <div className="feedback-banner feedback-success" role="status">{message}</div> : null}
      {actionError ? <div className="feedback-banner feedback-error" role="alert">{actionError}</div> : null}

      {activeTab === "plans" ? (
        <div className="settings-two-column">
          <section className="panel" aria-labelledby="plan-list-title">
            <div className="section-header">
              <h2 id="plan-list-title">巡检计划</h2>
              <span>{plans.length} 个</span>
            </div>
            {plans.length === 0 ? <p className="empty-copy">还没有巡检计划，可以从右侧创建。</p> : (
              <div className="management-list">
                {plans.map((plan) => (
                  <article className="management-card" key={plan.id}>
                    <div className="section-header">
                      <strong>{plan.name}</strong>
                      <div className="status-pair">
                        <StatusBadge status={plan.enabled ? "enabled" : "disabled"} />
                        {plan.last_run_status ? <StatusBadge status={plan.last_run_status} /> : null}
                      </div>
                    </div>
                    <p>{plan.scope.type === "global" ? "全部集群" : plan.scope.namespaces.join("、")} · {intervalLabels[plan.schedule.interval]}</p>
                    <small>下次执行：{displayTime(plan.next_run_at)} · 上次执行：{displayTime(plan.last_run_at)}</small>
                    {visiblePlanRuns[plan.id] ? (
                      <details className="technical-details">
                        <summary>查看本次执行 #{visiblePlanRuns[plan.id].id}</summary>
                        <div className="page-section">
                          <div className="section-header">
                            <strong>执行状态</strong>
                            <StatusBadge status={visiblePlanRuns[plan.id].status} />
                          </div>
                          {visiblePlanRuns[plan.id].status === "queued" ? (
                            <p className="inline-note">任务已受理，正在等待执行；页面会自动刷新状态。</p>
                          ) : null}
                          {visiblePlanRuns[plan.id].status === "running" ? (
                            <p className="inline-note">巡检正在执行；页面会自动刷新到最终结果。</p>
                          ) : null}
                          {visiblePlanRuns[plan.id].error_message ? (
                            <p className="feedback-banner feedback-error">
                              {visiblePlanRuns[plan.id].error_message}
                            </p>
                          ) : null}
                          {visiblePlanRuns[plan.id].coverage.length > 0 ? (
                            <CoveragePanel
                              coverage={visiblePlanRuns[plan.id].coverage}
                              title={`执行 #${visiblePlanRuns[plan.id].id} 检查覆盖`}
                            />
                          ) : null}
                        </div>
                      </details>
                    ) : null}
                    <div className="button-row">
                      <button
                        type="button"
                        onClick={() => void runPlan(plan)}
                        disabled={
                          saving
                          || plan.last_run_status === "queued"
                          || plan.last_run_status === "running"
                          || visiblePlanRuns[plan.id]?.status === "queued"
                          || visiblePlanRuns[plan.id]?.status === "running"
                        }
                      >
                        {visiblePlanRuns[plan.id]?.status === "queued"
                          ? "等待执行"
                          : visiblePlanRuns[plan.id]?.status === "running"
                            ? "执行中…"
                            : "立即运行"}
                      </button>
                      <button type="button" onClick={() => editPlan(plan)} disabled={saving}>编辑</button>
                      <button type="button" onClick={() => void togglePlan(plan)} disabled={saving}>{plan.enabled ? "停用" : "启用"}</button>
                      <button type="button" className="danger-button" onClick={() => void removePlan(plan)} disabled={saving}>删除</button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
          <section className="panel" aria-labelledby="plan-form-title">
            <h2 id="plan-form-title">{planEditingId ? "编辑巡检计划" : "创建巡检计划"}</h2>
            <form className="management-form" onSubmit={savePlan}>
              <label>计划名称<input value={planDraft.name} onChange={(event) => setPlanDraft({ ...planDraft, name: event.target.value })} /></label>
              <label>
                巡检范围
                <select value={planDraft.scope.type} onChange={(event) => setPlanDraft({ ...planDraft, scope: { type: event.target.value as "global" | "namespaces", namespaces: [] } })}>
                  <option value="global">全部集群</option>
                  <option value="namespaces">指定名称空间</option>
                </select>
              </label>
              {planDraft.scope.type === "namespaces" ? (
                <label>名称空间（逗号分隔）<input value={planNamespaces} onChange={(event) => setPlanNamespaces(event.target.value)} placeholder="prod, kube-system" /></label>
              ) : null}
              <label>
                执行周期
                <select value={planDraft.schedule.interval} onChange={(event) => setPlanDraft({ ...planDraft, schedule: { ...planDraft.schedule, interval: event.target.value as InspectionPlanCreate["schedule"]["interval"] } })}>
                  {Object.entries(intervalLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </label>
              {planDraft.schedule.interval === "daily" ? (
                <label>每日时间<input type="time" value={planDraft.schedule.daily_at ?? ""} onChange={(event) => setPlanDraft({ ...planDraft, schedule: { ...planDraft.schedule, daily_at: event.target.value } })} /></label>
              ) : null}
              <label>时区<input value={planDraft.schedule.timezone} onChange={(event) => setPlanDraft({ ...planDraft, schedule: { ...planDraft.schedule, timezone: event.target.value } })} /></label>
              <fieldset>
                <legend>通知渠道</legend>
                {channels.length === 0 ? <p className="inline-note">尚未创建通知渠道。</p> : channels.map((channel) => (
                  <label className="checkbox-label" key={channel.id}>
                    <input
                      type="checkbox"
                      checked={planDraft.notification_channel_ids.includes(channel.id)}
                      onChange={(event) => setPlanDraft({
                        ...planDraft,
                        notification_channel_ids: event.target.checked
                          ? [...planDraft.notification_channel_ids, channel.id]
                          : planDraft.notification_channel_ids.filter((id) => id !== channel.id),
                      })}
                    />
                    {channel.name}
                  </label>
                ))}
              </fieldset>
              <label className="checkbox-label"><input type="checkbox" checked={planDraft.include_template_matching} onChange={(event) => setPlanDraft({ ...planDraft, include_template_matching: event.target.checked })} />执行模板匹配</label>
              <label className="checkbox-label"><input type="checkbox" checked={planDraft.enabled} onChange={(event) => setPlanDraft({ ...planDraft, enabled: event.target.checked })} />创建后启用</label>
              <div className="button-row">
                <button className="primary-action" type="submit" disabled={saving}>{saving ? "保存中…" : "保存计划"}</button>
                {planEditingId ? <button type="button" onClick={() => { setPlanEditingId(null); setPlanDraft(emptyPlanDraft()); setPlanNamespaces(""); }}>取消编辑</button> : null}
              </div>
            </form>
          </section>
        </div>
      ) : null}

      {activeTab === "notifications" ? (
        <div className="settings-two-column">
          <section className="panel" aria-labelledby="channel-list-title">
            <div className="section-header">
              <h2 id="channel-list-title">通知渠道</h2>
              <span>{channels.length} 个</span>
            </div>
            {channels.length === 0 ? <p className="empty-copy">还没有通知渠道。</p> : (
              <div className="management-list">
                {channels.map((channel) => (
                  <article className="management-card" key={channel.id}>
                    <div className="section-header">
                      <strong>{channel.name}</strong>
                      <StatusBadge status={channel.enabled ? "enabled" : "disabled"} />
                    </div>
                    <p>{channel.type === "feishu_custom_bot" ? "飞书群机器人" : "通用 Webhook"}</p>
                    <code className="masked-endpoint">{channel.endpoint_masked}</code>
                    <small>签名：{channel.signing_secret_configured ? "已配置（内容始终隐藏）" : "未配置"} · 超时 {channel.timeout_seconds} 秒</small>
                    {channel.type === "feishu_custom_bot" ? <small>仅发送群告警，不接收消息。</small> : null}
                    <div className="button-row">
                      <button type="button" onClick={() => void testChannel(channel)} disabled={saving}>发送测试</button>
                      <button type="button" onClick={() => editChannel(channel)} disabled={saving}>编辑</button>
                      <button type="button" onClick={() => void toggleChannel(channel)} disabled={saving}>{channel.enabled ? "停用" : "启用"}</button>
                      <button type="button" className="danger-button" onClick={() => void removeChannel(channel)} disabled={saving}>删除</button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
          <section className="panel" aria-labelledby="channel-form-title">
            <h2 id="channel-form-title">{channelEditingId ? "编辑通知渠道" : "创建通知渠道"}</h2>
            <form className="management-form" onSubmit={saveChannel}>
              <label>渠道名称<input value={channelDraft.name} onChange={(event) => setChannelDraft({ ...channelDraft, name: event.target.value })} /></label>
              <label>
                渠道类型
                <select
                  value={channelDraft.type}
                  disabled={Boolean(channelEditingId)}
                  onChange={(event) => {
                    const type = event.target.value as NotificationChannelType;
                    setChannelDraft({ ...channelDraft, type, mention_all_on_critical: false });
                  }}
                >
                  <option value="generic_webhook">通用 Webhook</option>
                  <option value="feishu_custom_bot">飞书群机器人</option>
                </select>
              </label>
              <label>
                {channelEditingId ? "新 Webhook 地址（留空保持不变）" : "Webhook 地址"}
                <input type="url" value={channelDraft.webhook_url} onChange={(event) => setChannelDraft({ ...channelDraft, webhook_url: event.target.value })} autoComplete="off" />
              </label>
              <label>
                {channelEditingId ? "新签名密钥（留空保持不变）" : "签名密钥（可选）"}
                <input type="password" value={channelDraft.signing_secret ?? ""} onChange={(event) => setChannelDraft({ ...channelDraft, signing_secret: event.target.value })} autoComplete="new-password" />
              </label>
              {channelEditingId ? <label className="checkbox-label"><input type="checkbox" checked={clearSigningSecret} onChange={(event) => setClearSigningSecret(event.target.checked)} />清除已配置签名</label> : null}
              <label>请求超时（秒）<input type="number" min={1} max={30} value={channelDraft.timeout_seconds} onChange={(event) => setChannelDraft({ ...channelDraft, timeout_seconds: Number(event.target.value) })} /></label>
              {channelDraft.type === "feishu_custom_bot" ? (
                <>
                  <div className="feedback-banner feedback-info">仅向机器人所在飞书群发送告警；不接收消息，不支持单聊、卡片回调或飞书内操作。无需填写消息 JSON。</div>
                  <label className="checkbox-label">
                    <input type="checkbox" checked={channelDraft.mention_all_on_critical} onChange={(event) => changeMentionAll(event.target.checked)} />
                    仅 critical 时提醒所有人（默认关闭）
                  </label>
                </>
              ) : (
                <p className="field-help">生产环境仅允许 HTTPS，目标必须在服务端允许范围内，系统不会跟随重定向。</p>
              )}
              <label className="checkbox-label"><input type="checkbox" checked={channelDraft.enabled} onChange={(event) => setChannelDraft({ ...channelDraft, enabled: event.target.checked })} />启用渠道</label>
              <div className="button-row">
                <button className="primary-action" type="submit" disabled={saving}>{saving ? "保存中…" : "保存渠道"}</button>
                {channelEditingId ? <button type="button" onClick={() => { setChannelEditingId(null); setChannelDraft(emptyChannelDraft()); setClearSigningSecret(false); }}>取消编辑</button> : null}
              </div>
            </form>
          </section>
        </div>
      ) : null}

      {activeTab === "policy" && settings ? (
        <div className="policy-layout">
          <section className="panel">
            <div className="section-header">
              <div>
                <h2>必需组件</h2>
                <p className="inline-note">自动发现的可选组件未安装不会告警；只有以下必需组件缺失时才告警。</p>
              </div>
            </div>
            {settings.inspection_policy.required_components.length === 0 ? <p className="empty-copy">尚未配置必需组件。</p> : (
              <div className="management-list required-component-list">
                {settings.inspection_policy.required_components.map((component, index) => (
                  <article className="management-card required-component-card" key={`${component.namespace}-${component.kind}-${component.label_selector}`}>
                    <div className="required-component-main">
                      <strong>{component.name}</strong>
                      <span>{component.namespace} · {component.kind}</span>
                      <code>{component.label_selector}</code>
                    </div>
                    <div className="required-component-actions">
                      <StatusBadge status={component.enabled ? "enabled" : "disabled"} />
                      <button type="button" className="danger-button mini-button" onClick={() => removeRequiredComponent(index)}>移除</button>
                    </div>
                  </article>
                ))}
              </div>
            )}
            <form className="management-form compact-add-form" onSubmit={addRequiredComponent}>
              <h3>添加必需组件</h3>
              <label>
                选择组件
                <select
                  value={selectedComponentKey}
                  onChange={(event) => selectRequiredComponent(event.target.value)}
                  disabled={componentCandidateLoading || componentCandidates.length === 0}
                >
                  <option value="">{componentCandidateLoading ? "正在发现组件…" : "请选择组件"}</option>
                  {componentCandidates.map((candidate) => {
                    const key = requiredComponentKey(candidate);
                    const exists = settings.inspection_policy.required_components.some((component) =>
                      requiredComponentKey(component) === key);
                    return (
                      <option key={`${candidate.source}-${key}`} value={key} disabled={exists}>
                        {candidate.source === "builtin" ? "内置：" : "发现："}{requiredComponentLabel(candidate)}{exists ? "（已加入）" : ""}
                      </option>
                    );
                  })}
                </select>
              </label>
              {componentCandidateError ? <p className="field-error">组件候选读取失败：{componentCandidateError}</p> : null}
              {componentDraft.name ? (
                <div className="candidate-preview" aria-label="已选择组件定位">
                  <span>显示名称：{componentDraft.name}</span>
                  <span>名称空间：{componentDraft.namespace}</span>
                  <span>Kind：{componentDraft.kind}</span>
                  <code>{componentDraft.label_selector}</code>
                </div>
              ) : null}
              <button type="submit" disabled={!selectedComponentKey}>加入策略</button>
            </form>
          </section>
          <section className="panel">
            <h2>运行与数据保留</h2>
            <p className="inline-note">并发数越高，对 Kubernetes API 的瞬时压力越大；保留设置只影响之后执行的每日清理任务。</p>
            <div className="threshold-groups">
              <fieldset>
                <legend>运行限制</legend>
                <label>
                  名称空间并发数
                  <span className="input-with-unit">
                    <input
                      aria-label="名称空间并发数"
                      type="number"
                      min={1}
                      max={10}
                      step={1}
                      value={settings.inspection_policy.namespace_concurrency}
                      onChange={(event) => setSettings({
                        ...settings,
                        inspection_policy: {
                          ...settings.inspection_policy,
                          namespace_concurrency: Number(event.target.value),
                        },
                      })}
                    />
                    <span>个</span>
                  </span>
                  <small>范围 1–10，默认 3；新值只影响之后启动的巡检。</small>
                </label>
                <label>
                  单次日志采集 Pod 上限
                  <span className="input-with-unit">
                    <input
                      aria-label="单次日志采集 Pod 上限"
                      type="number"
                      min={1}
                      max={1000}
                      step={1}
                      value={settings.inspection_policy.max_log_pods}
                      onChange={(event) => setSettings({
                        ...settings,
                        inspection_policy: {
                          ...settings.inspection_policy,
                          max_log_pods: Number(event.target.value),
                        },
                      })}
                    />
                    <span>个</span>
                  </span>
                  <small>范围 1–1000，默认 200；仅限制用户主动发起的范围日志采集，单 Pod 巡检不受影响。</small>
                </label>
              </fieldset>
              <fieldset>
                <legend>数据保留</legend>
                {retentionFields.map((field) => (
                  <label key={field.key}>
                    {field.label}
                    <span className="input-with-unit">
                      <input
                        aria-label={field.label}
                        type="number"
                        min={7}
                        max={180}
                        step={1}
                        value={settings.inspection_policy.retention[field.key]}
                        onChange={(event) => updateRetention(field.key, Number(event.target.value))}
                      />
                      <span>天</span>
                    </span>
                    <small>{field.help}，范围 7–180 天。</small>
                  </label>
                ))}
              </fieldset>
            </div>
            <hr className="section-divider" />
            <h2>巡检阈值</h2>
            <p className="inline-note">阈值整体保存，校验失败不会部分生效。</p>
            <div className="threshold-groups">
              {groupedThresholds.map(([group, fields]) => (
                <fieldset key={group}>
                  <legend>{group}</legend>
                  {fields.map((field) => (
                    <label key={field.key}>
                      {field.label}
                      <span className="input-with-unit">
                        <input type="number" min={0} value={settings.inspection_policy.thresholds[field.key]} onChange={(event) => updateThreshold(field.key, Number(event.target.value))} />
                        <span>{field.unit}</span>
                      </span>
                    </label>
                  ))}
                </fieldset>
              ))}
            </div>
            <button type="button" className="primary-action" onClick={() => void savePolicy()} disabled={saving}>{saving ? "保存中…" : "保存巡检策略"}</button>
          </section>
        </div>
      ) : null}

      {activeTab === "status" ? (
        <section className="panel">
          <div className="section-header">
            <div>
              <h2>系统状态</h2>
              <p className="inline-note">Metrics API 或通知降级不会被伪装成正常，也不会单独表示应用宕机。</p>
            </div>
            {systemStatus ? <StatusBadge status={systemStatus.status} /> : null}
          </div>
          {!systemStatus ? <p className="empty-copy">系统状态暂时不可用，不能推断系统健康。</p> : (
            <>
              <dl className="detail-grid">
                <div><dt>应用版本</dt><dd>{systemStatus.version}</dd></div>
                <div><dt>集群标识</dt><dd>{systemStatus.cluster_id}</dd></div>
                <div><dt>Kubernetes 版本</dt><dd>{systemStatus.kubernetes_server_version ?? "--"}</dd></div>
                <div><dt>支持范围</dt><dd>{systemStatus.kubernetes_version_supported === false ? "不在 1.34–1.36 商用支持范围" : systemStatus.kubernetes_version_supported === true ? "在支持范围" : "无法判断"}</dd></div>
              </dl>
              <div className="system-component-grid">
                <SystemComponentCard label="数据库与 Schema" component={systemStatus.database} />
                <SystemComponentCard label="Kubernetes API" component={systemStatus.kubernetes_api} />
                <SystemComponentCard label="Provider" component={systemStatus.provider} />
                <SystemComponentCard label="调度器" component={systemStatus.scheduler} />
                <SystemComponentCard label="Metrics API" component={systemStatus.metrics_api} />
                <SystemComponentCard label="通知" component={systemStatus.notifications} />
                <SystemComponentCard label="最近巡检" component={systemStatus.last_inspection} />
                <SystemComponentCard label="配置校验" component={systemStatus.configuration} />
              </div>
            </>
          )}
        </section>
      ) : null}

      {activeTab === "basic" ? (
        <section className="panel">
          <h2>基础配置</h2>
          {!settings ? <p className="empty-copy">基础配置暂时不可用。</p> : (
            <form className="settings-form" onSubmit={saveBasicSettings}>
              <label>
                集群标识
                <input
                  aria-label="集群标识"
                  value={settings.cluster_id}
                  maxLength={128}
                  onChange={(event) => setSettings({ ...settings, cluster_id: event.target.value })}
                  placeholder="例如：dev-cluster、prod-shanghai"
                />
                <small>用于问题去重、问题工作台过滤和通知来源。修改后，新巡检结果归属新标识，旧问题仍保留在原标识下。</small>
              </label>
              <dl className="detail-grid">
                <div><dt>访问前缀</dt><dd>{settings.base_path || "/"}</dd></div>
                <div><dt>Provider 模式</dt><dd>{settings.provider_mode}</dd></div>
                <div><dt>Kubeconfig</dt><dd>{settings.kubeconfig_path ?? "集群内配置"}</dd></div>
                <div><dt>Kube Context</dt><dd>{settings.kube_context ?? "--"}</dd></div>
                <div><dt>模型提供方</dt><dd>{settings.llm_provider}</dd></div>
                <div><dt>API Key</dt><dd>{settings.api_key ? "已配置（内容始终隐藏）" : "未配置"}</dd></div>
              </dl>
              <button type="submit" disabled={saving}>保存基础配置</button>
            </form>
          )}
        </section>
      ) : null}
    </section>
  );
}
