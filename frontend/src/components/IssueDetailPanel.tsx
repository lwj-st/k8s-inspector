import { useMemo, useState } from "react";

import type { Issue, IssueEvent, ResourceRef } from "../api/types";
import { StatusBadge } from "./StatusBadge";

const sourceLabels: Record<string, string> = {
  kubernetes_api: "Kubernetes API",
  metrics_api: "Metrics API",
  event: "Warning Event",
  log_match: "日志命中上下文",
  template: "故障模板",
  derived: "规则计算",
};

const evidenceFilterOptions = [
  { value: "all", label: "全部证据" },
  { value: "kubernetes_api", label: "Kubernetes API" },
  { value: "event", label: "Event" },
  { value: "log_match", label: "Log" },
  { value: "metrics_api", label: "Metrics" },
  { value: "config", label: "Config" },
] as const;

type EvidenceFilter = typeof evidenceFilterOptions[number]["value"];

const eventLabels: Record<IssueEvent["event_type"], string> = {
  opened: "问题首次发现",
  observed: "问题仍在持续",
  severity_escalated: "严重程度升级",
  acknowledged: "问题已确认",
  note_added: "处理记录",
  ignored: "问题已忽略",
  unignored: "已取消忽略",
  notification_silenced: "通知已静默",
  recovered: "问题已恢复",
  reopened: "问题重新出现",
};

const chainOrder: Record<string, number> = {
  ingress: 0,
  service: 1,
  endpointslice: 2,
  pod: 3,
};

const resourceAliases: Record<string, string> = {
  configmap: "configmap",
  cronjob: "cronjob",
  daemonset: "daemonset",
  deployment: "deployment",
  endpoint: "endpoints",
  endpoints: "endpoints",
  endpointslice: "endpointslices.discovery.k8s.io",
  ingress: "ingress",
  ingressclass: "ingressclass",
  job: "job",
  namespace: "namespace",
  node: "node",
  persistentvolume: "pv",
  persistentvolumeclaim: "pvc",
  pod: "pod",
  replicaset: "replicaset",
  secret: "secret",
  service: "service",
  statefulset: "statefulset",
  storageclass: "storageclass",
};

function formatDateTime(value?: string | null) {
  if (!value) {
    return "--";
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function resourceKey(resource: ResourceRef) {
  return `${resource.kind}:${resource.namespace ?? ""}:${resource.name}`;
}

function resourceLabel(resource: ResourceRef) {
  return `${resource.kind}/${resource.namespace ? `${resource.namespace}/` : ""}${resource.name}`;
}

function factValue(value: unknown) {
  if (Array.isArray(value)) {
    return sanitizeMarkdown(value.map(String).join("、"));
  }
  if (value === null || value === undefined || value === "") {
    return "--";
  }
  return sanitizeMarkdown(String(value));
}

function sanitizeMarkdown(value: string) {
  return value
    .replace(/(authorization\s*[:=]\s*)([^\s,;]+)/gi, "$1***")
    .replace(/(cookie\s*[:=]\s*)([^\n]+)/gi, "$1***")
    .replace(/((?:password|token|secret|webhook|api[_-]?key)\s*[:=]\s*)([^\s,;]+)/gi, "$1***")
    .replace(/(https?:\/\/[^/\s]+\/(?:open-apis\/bot\/v2\/hook|webhook|hooks?)\/)[^\s)]+/gi, "$1***");
}

function evidenceMatchesFilter(source: string, filter: EvidenceFilter) {
  if (filter === "all") {
    return true;
  }
  if (filter === "config") {
    return source === "template" || source === "derived";
  }
  return source === filter;
}

function shellQuote(value: string) {
  return `'${value.replace(/'/g, "'\"'\"'")}'`;
}

function kubectlKind(kind: string) {
  return resourceAliases[kind.toLowerCase()] ?? kind.toLowerCase();
}

function namespaceFlag(resource: ResourceRef) {
  return resource.namespace ? ` -n ${shellQuote(resource.namespace)}` : "";
}

function commandKey(command: IssueCommand) {
  return `${command.title}:${command.command}`;
}

type IssueCommand = {
  title: string;
  command: string;
};

function getResourceCommand(resource: ResourceRef): IssueCommand {
  const kind = kubectlKind(resource.kind);
  const namespace = namespaceFlag(resource);
  const name = shellQuote(resource.name);
  const label = resourceLabel(resource);
  return {
    title: `查看 ${label}`,
    command: `kubectl get ${kind}${namespace} ${name} -o yaml`,
  };
}

function describeResourceCommand(resource: ResourceRef): IssueCommand {
  const kind = kubectlKind(resource.kind);
  const namespace = namespaceFlag(resource);
  const name = shellQuote(resource.name);
  const label = resourceLabel(resource);
  return {
    title: `Describe ${label}`,
    command: `kubectl describe ${kind}${namespace} ${name}`,
  };
}

function relatedResource(issue: Issue, kind: string) {
  return issue.evidence
    .flatMap((item) => item.related_resources)
    .find((resource) => resource.kind.toLowerCase() === kind.toLowerCase());
}

function evidenceFacts(issue: Issue) {
  return issue.evidence.map((item) => item.facts);
}

function firstFactString(issue: Issue, key: string) {
  for (const facts of evidenceFacts(issue)) {
    const value = facts[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return "";
}

function serviceEndpointCommands(resource: ResourceRef, facts: Record<string, unknown> = {}): IssueCommand[] {
  if (resource.kind.toLowerCase() !== "service" || !resource.namespace) {
    return [];
  }
  const namespace = shellQuote(resource.namespace);
  const selector = Array.isArray(facts.selector) ? facts.selector.map(String).filter(Boolean).join(",") : "";
  return [
    {
      title: `查看 ${resource.name} 的 EndpointSlice`,
      command: `kubectl get endpointslices.discovery.k8s.io -n ${namespace} -l kubernetes.io/service-name=${shellQuote(resource.name)} -o wide`,
    },
    {
      title: `查看 ${resource.name} 的 Endpoints`,
      command: `kubectl get endpoints -n ${namespace} ${shellQuote(resource.name)} -o wide`,
    },
    ...(selector
      ? [{
          title: `按 Service selector 查 Pod`,
          command: `kubectl get pods -n ${namespace} -l ${shellQuote(selector)} -o wide`,
        }]
      : []),
  ];
}

function podDiagnosisCommands(resource: ResourceRef): IssueCommand[] {
  if (resource.kind.toLowerCase() !== "pod" || !resource.namespace) {
    return [];
  }
  const namespace = shellQuote(resource.namespace);
  const name = shellQuote(resource.name);
  return [
    {
      title: `查看 ${resource.name} 事件`,
      command: `kubectl get events -n ${namespace} --field-selector involvedObject.kind=Pod,involvedObject.name=${shellQuote(resource.name)} --sort-by=.lastTimestamp`,
    },
    {
      title: `查看 ${resource.name} 最近日志`,
      command: `kubectl logs -n ${namespace} ${name} --all-containers --tail=200`,
    },
    {
      title: `查看 ${resource.name} 上次崩溃日志`,
      command: `kubectl logs -n ${namespace} ${name} --all-containers --previous --tail=200`,
    },
  ];
}

function ingressDiagnosisCommands(issue: Issue): IssueCommand[] {
  const resource = issue.resource.kind.toLowerCase() === "ingress" ? issue.resource : relatedResource(issue, "Ingress");
  if (!resource || resource.kind.toLowerCase() !== "ingress" || !resource.namespace) {
    return [];
  }
  const namespace = shellQuote(resource.namespace);
  const commands: IssueCommand[] = [
    {
      title: `查看 ${resource.name} 引用的后端 Service`,
      command: `kubectl describe ingress -n ${namespace} ${shellQuote(resource.name)}`,
    },
  ];
  const backend = firstFactString(issue, "backend");
  const backendService = backend.split(":", 1)[0]?.trim();
  if (backendService) {
    commands.push({
      title: `查看后端 Service ${backendService}`,
      command: `kubectl get service -n ${namespace} ${shellQuote(backendService)} -o yaml`,
    });
  }
  return commands;
}

function tlsSecretDiagnosisCommands(resource: ResourceRef): IssueCommand[] {
  if (resource.kind.toLowerCase() !== "secret" || !resource.namespace) {
    return [];
  }
  const namespace = shellQuote(resource.namespace);
  const name = shellQuote(resource.name);
  return [
    {
      title: `查看 TLS Secret 证书主体`,
      command: `kubectl get secret -n ${namespace} ${name} -o jsonpath='{.data.tls\\.crt}' | base64 -d | openssl x509 -noout -subject -issuer -dates`,
    },
    {
      title: `查看 TLS Secret SAN`,
      command: `kubectl get secret -n ${namespace} ${name} -o jsonpath='{.data.tls\\.crt}' | base64 -d | openssl x509 -noout -ext subjectAltName`,
    },
  ];
}

function issueCommands(issue: Issue): IssueCommand[] {
  const commands: IssueCommand[] = [];
  const service = issue.resource.kind.toLowerCase() === "service" ? issue.resource : relatedResource(issue, "Service");
  const pod = issue.resource.kind.toLowerCase() === "pod" ? issue.resource : relatedResource(issue, "Pod");

  if (issue.issue_code.startsWith("INGRESS_")) {
    commands.push(...ingressDiagnosisCommands(issue));
  } else if (issue.issue_code.startsWith("TLS_")) {
    commands.push(getResourceCommand(issue.resource), ...tlsSecretDiagnosisCommands(issue.resource));
    const ingress = relatedResource(issue, "Ingress");
    if (ingress) {
      commands.push(describeResourceCommand(ingress));
    }
  } else if (issue.issue_code.startsWith("SERVICE_") && service) {
    commands.push(describeResourceCommand(service));
    for (const facts of evidenceFacts(issue)) {
      commands.push(...serviceEndpointCommands(service, facts));
    }
  } else if (issue.issue_code.startsWith("POD_") && pod) {
    commands.push(describeResourceCommand(pod), ...podDiagnosisCommands(pod));
  } else if (issue.issue_code.startsWith("PVC_") || issue.issue_code === "VOLUME_MOUNT_FAILED") {
    commands.push(describeResourceCommand(issue.resource));
  } else if (issue.issue_code.startsWith("PV_")) {
    commands.push(describeResourceCommand(issue.resource));
  } else if (issue.issue_code.startsWith("NODE_")) {
    commands.push(describeResourceCommand(issue.resource));
    commands.push({
      title: "查看节点资源使用",
      command: `kubectl top node ${shellQuote(issue.resource.name)}`,
    });
  } else if (
    issue.issue_code.startsWith("WORKLOAD_")
    || issue.issue_code === "JOB_FAILED"
    || issue.issue_code === "CRONJOB_NOT_SCHEDULED"
    || issue.issue_code === "REQUIRED_COMPONENT_MISSING"
  ) {
    commands.push(describeResourceCommand(issue.resource));
  }
  return Array.from(
    new Map(commands.map((command) => [commandKey(command), command])).values(),
  );
}

function buildIssueMarkdown(issue: Issue, events: IssueEvent[], commands: IssueCommand[]) {
  const lines = [
    `# ${issue.summary}`,
    "",
    "## 问题概览",
    "",
    `- 资源：${resourceLabel(issue.resource)}`,
    `- 名称空间：${issue.resource.namespace ?? "集群级"}`,
    `- 严重程度：${issue.severity}`,
    `- 当前状态：${issue.status}`,
    `- 判断原因：${issue.reason}`,
    `- 建议动作：${issue.suggestion}`,
    "",
    "## 关键证据",
    "",
    ...(issue.evidence.length > 0
      ? issue.evidence.flatMap((item) => [
          `### ${item.summary}`,
          "",
          `- 类型：${sourceLabels[item.source] ?? item.source}`,
          `- 观测时间：${formatDateTime(item.observed_at)}`,
          `- 截断：${item.truncated ? "是" : "否"}`,
          ...Object.entries(item.facts).map(([key, value]) => `- ${key}：${factValue(value)}`),
          "",
        ])
      : ["暂无持久化证据。", ""]),
    "## 查看命令",
    "",
    ...(commands.length > 0
      ? commands.flatMap((command) => [
          `### ${command.title}`,
          "",
          "```bash",
          command.command,
          "```",
          "",
        ])
      : ["无确定命令。", ""]),
    "## 处理记录",
    "",
    ...(events.length > 0
      ? events.flatMap((event) => [
          `- ${formatDateTime(event.occurred_at)} ${event.actor ?? "系统"} ${eventLabels[event.event_type] ?? event.event_type}：${event.summary}`,
        ])
      : ["暂无处理记录。"]),
    "",
  ];
  return sanitizeMarkdown(lines.join("\n"));
}

export function IssueDetailPanel({
  issue,
  events,
  eventsTotal,
  eventsLoading,
  eventsError,
  onLoadMore,
  onAddNote,
  onAcknowledge,
  onIgnore,
  onUnignore,
}: {
  issue: Issue;
  events: IssueEvent[];
  eventsTotal: number;
  eventsLoading: boolean;
  eventsError: string | null;
  onLoadMore: () => void;
  onAddNote: (content: string) => Promise<void>;
  onAcknowledge: (note: string) => Promise<void>;
  onIgnore: () => Promise<void>;
  onUnignore: () => Promise<void>;
}) {
  const [note, setNote] = useState("");
  const [acknowledging, setAcknowledging] = useState(false);
  const [acknowledgeError, setAcknowledgeError] = useState<string | null>(null);
  const [handlingNote, setHandlingNote] = useState("");
  const [savingHandlingNote, setSavingHandlingNote] = useState(false);
  const [handlingNoteMessage, setHandlingNoteMessage] = useState<string | null>(null);
  const [handlingNoteError, setHandlingNoteError] = useState<string | null>(null);
  const [ignoring, setIgnoring] = useState(false);
  const [ignoreError, setIgnoreError] = useState<string | null>(null);
  const [unignoring, setUnignoring] = useState(false);
  const [unignoreError, setUnignoreError] = useState<string | null>(null);
  const [copiedCommandKey, setCopiedCommandKey] = useState<string | null>(null);
  const [evidenceFilter, setEvidenceFilter] = useState<EvidenceFilter>("all");
  const [exportMessage, setExportMessage] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  const chainResources = useMemo(() => {
    const resources = [issue.resource, ...issue.evidence.flatMap((item) => item.related_resources)];
    const unique = new Map(resources.map((resource) => [resourceKey(resource), resource]));
    return Array.from(unique.values())
      .filter((resource) => resource.kind.toLowerCase() in chainOrder)
      .sort((left, right) => chainOrder[left.kind.toLowerCase()] - chainOrder[right.kind.toLowerCase()]);
  }, [issue]);

  const commands = useMemo(() => issueCommands(issue), [issue]);
  const filteredEvidence = useMemo(
    () => issue.evidence.filter((item) => evidenceMatchesFilter(item.source, evidenceFilter)),
    [issue.evidence, evidenceFilter],
  );
  const markdown = useMemo(() => buildIssueMarkdown(issue, events, commands), [issue, events, commands]);

  async function handleAcknowledge(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!note.trim()) {
      setAcknowledgeError("请填写确认备注");
      return;
    }
    setAcknowledging(true);
    setAcknowledgeError(null);
    try {
      await onAcknowledge(note.trim());
      setNote("");
    } catch (reason) {
      setAcknowledgeError(reason instanceof Error ? reason.message : "确认失败，请重试");
    } finally {
      setAcknowledging(false);
    }
  }

  async function handleAddNote(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!handlingNote.trim()) {
      setHandlingNoteError("请填写处理记录");
      return;
    }
    setSavingHandlingNote(true);
    setHandlingNoteError(null);
    setHandlingNoteMessage(null);
    try {
      await onAddNote(handlingNote.trim());
      setHandlingNote("");
      setHandlingNoteMessage("处理记录已添加。");
    } catch (reason) {
      setHandlingNoteError(reason instanceof Error ? reason.message : "处理记录保存失败，请重试");
    } finally {
      setSavingHandlingNote(false);
    }
  }

  async function copyCommand(command: IssueCommand) {
    await navigator.clipboard?.writeText(command.command);
    setCopiedCommandKey(commandKey(command));
  }

  async function copyMarkdown() {
    setExportError(null);
    setExportMessage(null);
    try {
      if (!navigator.clipboard?.writeText) {
        setExportError("当前浏览器不支持复制，请下载 Markdown 文件。");
        return;
      }
      await navigator.clipboard.writeText(markdown);
      setExportMessage("Markdown 已复制。");
    } catch {
      setExportError("复制 Markdown 失败，请下载文件。");
    }
  }

  function downloadMarkdown() {
    setExportError(null);
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `issue-${issue.id}.md`;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    setExportMessage("Markdown 文件已生成。");
  }

  async function handleIgnore() {
    const confirmed = window.confirm("忽略后，此问题默认不再出现在开放问题列表，可通过“已忽略”筛选查看。确认忽略吗？");
    if (!confirmed) {
      return;
    }
    setIgnoring(true);
    setIgnoreError(null);
    try {
      await onIgnore();
    } catch (reason) {
      setIgnoreError(reason instanceof Error ? reason.message : "忽略失败，请重试");
    } finally {
      setIgnoring(false);
    }
  }

  async function handleUnignore() {
    const confirmed = window.confirm("取消忽略后，此问题会重新出现在开放问题列表。确认取消忽略吗？");
    if (!confirmed) {
      return;
    }
    setUnignoring(true);
    setUnignoreError(null);
    try {
      await onUnignore();
    } catch (reason) {
      setUnignoreError(reason instanceof Error ? reason.message : "取消忽略失败，请重试");
    } finally {
      setUnignoring(false);
    }
  }

  return (
    <article className="issue-detail" aria-labelledby="issue-detail-title">
      <header className="issue-detail-header">
        <div>
          <p className="eyebrow">{issue.resource.kind} · {issue.resource.namespace ?? "集群级"}</p>
          <h1 id="issue-detail-title">{issue.summary}</h1>
          <p>{resourceLabel(issue.resource)}</p>
        </div>
        <div className="status-pair">
          <StatusBadge status={issue.severity} />
          <StatusBadge status={issue.status} />
        </div>
      </header>

      <section className="detail-section" aria-labelledby="impact-title">
        <h2 id="impact-title">结论与影响范围</h2>
        <p className="issue-primary-reason">{issue.reason}</p>
        <div className="issue-primary-summary" aria-label="问题重点">
          <div>
            <span>资源</span>
            <strong>{resourceLabel(issue.resource)}</strong>
          </div>
          <div>
            <span>最后发现</span>
            <strong>{formatDateTime(issue.last_seen_at)}</strong>
          </div>
          <div>
            <span>出现次数</span>
            <strong>{issue.occurrence_count}</strong>
          </div>
          <div>
            <span>确认状态</span>
            <strong>{issue.acknowledged_at ? "已确认" : "未确认"}</strong>
          </div>
        </div>
        <div className="issue-next-action">
          <strong>建议动作</strong>
          <p>{issue.suggestion}</p>
        </div>
        <details className="evidence-drawer-details">
          <summary>查看技术字段</summary>
          <dl className="detail-grid">
            <div><dt>集群</dt><dd>{issue.cluster_id}</dd></div>
            <div><dt>范围</dt><dd>{issue.scope}</dd></div>
            <div><dt>首次发现</dt><dd>{formatDateTime(issue.first_seen_at)}</dd></div>
            <div><dt>最后发现</dt><dd>{formatDateTime(issue.last_seen_at)}</dd></div>
            <div><dt>出现次数</dt><dd>{issue.occurrence_count}</dd></div>
            <div><dt>确认状态</dt><dd>{issue.acknowledged_at ? "已确认" : "未确认"}</dd></div>
          </dl>
        </details>
      </section>

      {chainResources.length > 1 ? (
        <section className="detail-section" aria-labelledby="chain-title">
          <div className="section-header">
            <div>
              <h2 id="chain-title">访问配置链路</h2>
              <p className="inline-note">只展示后端提供的关联证据；本次未验证集群外真实访问。</p>
            </div>
          </div>
          <ol className="config-chain" aria-label="访问配置链路">
            {chainResources.map((resource) => (
              <li key={resourceKey(resource)}>
                <span className="chain-kind">{resource.kind}</span>
                <strong>{resource.name}</strong>
                <small>{resource.namespace ?? "集群级"} · 关联证据</small>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <section className="detail-section" aria-labelledby="evidence-title">
        <div className="section-header">
          <h2 id="evidence-title">证据</h2>
          <span className="section-tip">{filteredEvidence.length}/{issue.evidence.length} 条</span>
        </div>
        <div className="evidence-toolbar">
          <label>
            证据类型
            <select value={evidenceFilter} onChange={(event) => setEvidenceFilter(event.target.value as EvidenceFilter)}>
              {evidenceFilterOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
        </div>
        {issue.evidence.length === 0 ? (
          <p className="empty-copy">本问题没有可展示的持久化证据。</p>
        ) : filteredEvidence.length === 0 ? (
          <p className="empty-copy">当前证据类型没有结果。</p>
        ) : (
          <div className="evidence-card-list">
            {filteredEvidence.map((item) => (
              <article className="evidence-card" key={`${item.code}-${item.observed_at}`}>
                <div className="section-header">
                  <strong>{item.summary}</strong>
                  <span>{sourceLabels[item.source] ?? item.source}</span>
                </div>
                <p className="inline-note">观测时间：{formatDateTime(item.observed_at)}</p>
                {Object.keys(item.facts).length > 0 ? (
                  <dl className="facts-grid">
                    {Object.entries(item.facts).map(([key, value]) => (
                      <div key={key}><dt>{key}</dt><dd>{factValue(value)}</dd></div>
                    ))}
                  </dl>
                ) : null}
                {item.related_resources.length > 0 ? (
                  <p className="related-resources">
                    关联对象：{item.related_resources.map(resourceLabel).join("；")}
                  </p>
                ) : null}
                {item.truncated ? (
                  <p className="feedback-banner feedback-warning">证据已按安全和长度限制截断。</p>
                ) : null}
              </article>
            ))}
          </div>
        )}
      </section>

      {commands.length > 0 ? (
        <section className="detail-section" aria-labelledby="commands-title">
          <div className="section-header">
            <div>
              <h2 id="commands-title">查看命令</h2>
              <p className="inline-note">命令只用于到集群上核对当前状态，不会修改资源。</p>
            </div>
          </div>
          <div className="command-card-list">
            {commands.map((command) => {
              const key = commandKey(command);
              return (
                <article className="command-card" key={key}>
                  <div className="section-header">
                    <strong>{command.title}</strong>
                    <button type="button" className="mini-button" onClick={() => void copyCommand(command)}>
                      {copiedCommandKey === key ? "已复制" : "复制命令"}
                    </button>
                  </div>
                  <pre className="log-block code-block-scroll">{command.command}</pre>
                </article>
              );
            })}
          </div>
        </section>
      ) : null}

      <section className="detail-section" aria-labelledby="export-title">
        <div className="section-header">
          <div>
            <h2 id="export-title">导出 Markdown</h2>
            <p className="inline-note">导出内容会脱敏，包含问题结论、证据、命令和处理记录。</p>
          </div>
        </div>
        <div className="button-row">
          <button type="button" className="primary-action" onClick={() => void copyMarkdown()}>
            复制 Markdown
          </button>
          <button type="button" className="modal-secondary-button" onClick={downloadMarkdown}>
            下载 Markdown
          </button>
        </div>
        {exportMessage ? <p className="feedback-banner feedback-success" role="status">{exportMessage}</p> : null}
        {exportError ? <p className="feedback-banner feedback-error" role="alert">{exportError}</p> : null}
      </section>

      <section className="detail-section" aria-labelledby="timeline-title">
        <div className="section-header">
          <div>
            <h2 id="timeline-title">处理记录</h2>
            <p className="inline-note">记录交接、排查进展或临时处置，不会改变问题状态。</p>
          </div>
          <span className="section-tip">最新在前</span>
        </div>
        <form className="acknowledge-form handling-note-form" onSubmit={handleAddNote}>
          <label>
            新增记录
            <textarea
              value={handlingNote}
              maxLength={1000}
              rows={4}
              onChange={(event) => {
                setHandlingNote(event.target.value);
                setHandlingNoteMessage(null);
                setHandlingNoteError(null);
              }}
              aria-describedby="handling-note-help"
            />
          </label>
          <div id="handling-note-help" className="field-help">支持普通文本，还可输入 {1000 - handlingNote.length} 字。</div>
          <div className="button-row">
            <button type="submit" className="primary-action" disabled={savingHandlingNote}>
              {savingHandlingNote ? "保存中…" : "添加记录"}
            </button>
          </div>
          {handlingNoteMessage ? <p className="feedback-banner feedback-success" role="status">{handlingNoteMessage}</p> : null}
          {handlingNoteError ? <p className="field-error" role="alert">{handlingNoteError}</p> : null}
        </form>
        {eventsError ? (
          <div className="feedback-banner feedback-error" role="alert">
            处理记录读取失败：{eventsError}
          </div>
        ) : null}
        {events.length === 0 && !eventsLoading && !eventsError ? (
          <p className="empty-copy">暂无处理记录。</p>
        ) : (
          <ol className="issue-timeline">
            {events.map((item) => (
              <li key={item.id}>
                <div className="timeline-dot" aria-hidden="true" />
                <div>
                  <div className="section-header">
                    <strong>{eventLabels[item.event_type]}</strong>
                    <time dateTime={item.occurred_at}>{formatDateTime(item.occurred_at)}</time>
                  </div>
                  <p>{item.summary}</p>
                  <small>{item.actor ?? (item.trigger === "scheduled" ? "定时巡检" : "系统")}</small>
                </div>
              </li>
            ))}
          </ol>
        )}
        {events.length < eventsTotal ? (
          <button type="button" onClick={onLoadMore} disabled={eventsLoading}>
            {eventsLoading ? "加载中…" : "加载更早记录"}
          </button>
        ) : null}
      </section>

      <section className="detail-section acknowledgement-section" aria-labelledby="ack-title">
        <h2 id="ack-title">确认问题</h2>
        <div className="feedback-banner feedback-warning">
          确认只表示你已知晓此问题，不会恢复问题，也不会修改 Kubernetes 资源。
        </div>
        {issue.acknowledged_at ? (
          <div className="acknowledged-note">
            <strong>已于 {formatDateTime(issue.acknowledged_at)} 确认</strong>
            <p>{issue.acknowledge_note}</p>
          </div>
        ) : (
          <form className="acknowledge-form" onSubmit={handleAcknowledge}>
            <label>
              确认备注
              <textarea
                value={note}
                maxLength={1000}
                rows={4}
                onChange={(event) => setNote(event.target.value)}
                aria-describedby="ack-help"
              />
            </label>
            <div id="ack-help" className="field-help">请说明负责人、处理计划或已知影响。还可输入 {1000 - note.length} 字。</div>
            {acknowledgeError ? <p className="field-error" role="alert">{acknowledgeError}</p> : null}
            <button type="submit" className="primary-action" disabled={acknowledging}>
              {acknowledging ? "确认中…" : "确认已知晓"}
            </button>
          </form>
        )}
      </section>

      <section className="detail-section ignore-section" aria-labelledby="ignore-title">
        <h2 id="ignore-title">忽略问题</h2>
        <div className="feedback-banner feedback-warning">
          忽略后，此问题默认不再出现在开放问题列表；不会恢复问题，也不会修改 Kubernetes 资源。
        </div>
        {issue.status === "ignored" ? (
          <>
            <p className="acknowledged-note"><strong>此问题已忽略</strong></p>
            {unignoreError ? <p className="field-error" role="alert">{unignoreError}</p> : null}
            <button
              type="button"
              className="issue-ignore-action issue-ignore-action-restore"
              disabled={unignoring}
              onClick={() => void handleUnignore()}
            >
              {unignoring ? "恢复中…" : "恢复显示"}
            </button>
          </>
        ) : (
          <>
            {ignoreError ? <p className="field-error" role="alert">{ignoreError}</p> : null}
            <button
              type="button"
              className="issue-ignore-action issue-ignore-action-muted"
              disabled={ignoring}
              onClick={() => void handleIgnore()}
            >
              {ignoring ? "忽略中…" : "忽略此问题"}
            </button>
          </>
        )}
      </section>

      <details className="technical-details">
        <summary>技术详情</summary>
        <dl className="detail-grid">
          <div><dt>Issue Code</dt><dd>{issue.issue_code}</dd></div>
          <div><dt>检查来源</dt><dd>{issue.source_check}</dd></div>
          <div><dt>Fingerprint</dt><dd className="break-all">{issue.fingerprint}</dd></div>
          <div><dt>Correlation Key</dt><dd>{issue.correlation_key ?? "--"}</dd></div>
        </dl>
      </details>
    </article>
  );
}
