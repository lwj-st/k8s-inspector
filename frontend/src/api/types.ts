export type InspectionTargetType = "namespace" | "pod" | "template";
export type KeywordHitSeverity = "info" | "warning" | "error" | "critical";
export type AbnormalCategory = "pod_status" | "container_status" | "event" | "log_keyword" | "related_object";
export type TemplateConditionType =
  | "pod_status"
  | "log_keyword"
  | "event_keyword"
  | "restart_count"
  | "related_object_status";
export type TemplateConditionOperator = "equals" | "in" | "contains" | "gte" | "lte";
export type TemplateConditionJoinOperator = "AND" | "OR";
export type DiagnosisDirection = "template_check";
export type IssueSeverity = "critical" | "warning" | "info";
export type IssueStatus = "open" | "recovered";
export type IssueSortMode = "priority" | "duration" | "last_changed";
export type IssueScope = "cluster" | "namespace" | "workload" | "pod" | "service" | "ingress" | "node" | "storage";
export type HealthStatus = "healthy" | "warning" | "critical" | "unknown";
export type CheckStatus = "passed" | "abnormal" | "skipped" | "failed";
export type InspectionTrigger = "manual" | "scheduled";
export type InspectionRunStatus = "queued" | "running" | "succeeded" | "partial" | "failed";
export type NotificationChannelType = "generic_webhook" | "feishu_custom_bot";
export type NotificationDeliveryStatus = "pending" | "delivering" | "succeeded" | "failed" | "suppressed";
export type ComponentState = "ok" | "degraded" | "failed" | "unavailable";
export type JsonPrimitive = string | number | boolean | null;

export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type ResourceRef = {
  api_version?: string | null;
  kind: string;
  namespace?: string | null;
  name: string;
  uid?: string | null;
};

export type Evidence = {
  code: string;
  source: "kubernetes_api" | "metrics_api" | "event" | "log_match" | "template" | "derived";
  summary: string;
  facts: Record<string, JsonPrimitive | JsonPrimitive[]>;
  related_resources: ResourceRef[];
  observed_at: string;
  truncated: boolean;
};

export type Issue = {
  id: number;
  cluster_id: string;
  issue_code: string;
  fingerprint: string;
  severity: IssueSeverity;
  status: IssueStatus;
  scope: IssueScope;
  resource: ResourceRef;
  summary: string;
  reason: string;
  suggestion: string;
  evidence: Evidence[];
  first_seen_at: string;
  last_seen_at: string;
  recovered_at?: string | null;
  occurrence_count: number;
  source_check: string;
  correlation_key?: string | null;
  acknowledged_at?: string | null;
  acknowledge_note?: string | null;
};

export type IssueEvent = {
  id: number;
  issue_id: number;
  run_id?: number | null;
  event_type: "opened" | "observed" | "severity_escalated" | "acknowledged" | "recovered" | "reopened";
  trigger: InspectionTrigger;
  previous_status?: IssueStatus | null;
  new_status?: IssueStatus | null;
  previous_severity?: IssueSeverity | null;
  new_severity?: IssueSeverity | null;
  occurred_at: string;
  summary: string;
  evidence_codes: string[];
};

export type IssueListParams = {
  status?: IssueStatus;
  severity?: IssueSeverity;
  namespace?: string;
  resource_kind?: string;
  source_check?: string;
  sort?: IssueSortMode;
  page?: number;
  page_size?: number;
};

export type IssueFilterOption = {
  value: string;
  label: string;
};

export type IssueFilterOptions = {
  namespaces: IssueFilterOption[];
  resource_kinds: IssueFilterOption[];
  source_checks: IssueFilterOption[];
};

export type Coverage = {
  check_code: string;
  name: string;
  status: CheckStatus;
  reason?: string | null;
  checked_objects: number;
  duration_ms: number;
  issue_count: number;
};

export type InspectionScope = {
  type: "cluster" | "namespace" | "pod";
  namespaces: string[];
  namespace?: string | null;
  label_selector?: string | null;
  pod_name?: string | null;
};

export type InspectionCheckResult = Coverage & {
  id: number;
  run_id: number;
  scope: InspectionScope;
  scope_key: string;
  completed_at: string;
};

export type InspectionRun = {
  id: number;
  plan_id?: number | null;
  inspection_record_id?: number | null;
  trigger: InspectionTrigger;
  status: InspectionRunStatus;
  scope: InspectionScope;
  started_at?: string | null;
  finished_at?: string | null;
  coverage: Coverage[];
  issue_ids: number[];
  opened_issue_count: number;
  recovered_issue_count: number;
  kubernetes_api_calls: number;
  log_pods_read: number;
  collected_log_bytes: number;
  duration_ms: number;
  error_code?: string | null;
  error_message?: string | null;
};

export type InspectionRunDetail = InspectionRun & {
  check_results: InspectionCheckResult[];
};

export type PlanInterval = "5m" | "10m" | "30m" | "60m" | "daily";

export type InspectionPlanScope = {
  type: "global" | "namespaces";
  namespaces: string[];
};

export type PlanSchedule = {
  interval: PlanInterval;
  daily_at?: string | null;
  timezone: string;
};

export type InspectionPlanCreate = {
  name: string;
  enabled: boolean;
  scope: InspectionPlanScope;
  schedule: PlanSchedule;
  include_template_matching: boolean;
  notification_channel_ids: number[];
};

export type InspectionPlanUpdate = Partial<InspectionPlanCreate>;

export type InspectionPlan = InspectionPlanCreate & {
  id: number;
  last_run_at?: string | null;
  next_run_at?: string | null;
  last_run_status?: InspectionRunStatus | null;
  created_at: string;
  updated_at: string;
};

export type NotificationChannelCreate = {
  name: string;
  type: NotificationChannelType;
  enabled: boolean;
  webhook_url: string;
  signing_secret?: string | null;
  mention_all_on_critical: boolean;
  timeout_seconds: number;
};

export type NotificationChannelUpdate = {
  name?: string;
  enabled?: boolean;
  webhook_url?: string;
  signing_secret?: string;
  clear_signing_secret?: boolean;
  mention_all_on_critical?: boolean;
  timeout_seconds?: number;
};

export type NotificationChannel = {
  id: number;
  name: string;
  type: NotificationChannelType;
  enabled: boolean;
  endpoint_masked: string;
  signing_secret_configured: boolean;
  mention_all_on_critical: boolean;
  timeout_seconds: number;
  created_at: string;
  updated_at: string;
};

export type NotificationDelivery = {
  id: number;
  channel_id: number;
  deduplication_key: string;
  issue_event_id?: number | null;
  run_id?: number | null;
  event_type: string;
  status: NotificationDeliveryStatus;
  attempt_count: number;
  http_status?: number | null;
  provider_code?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  next_retry_at?: string | null;
  delivered_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type NotificationTestResponse = {
  delivery: NotificationDelivery;
  message: string;
};

export type AdminSession = {
  authenticated: boolean;
  username?: string | null;
  csrf_token?: string | null;
  idle_expires_at?: string | null;
  absolute_expires_at?: string | null;
};

export type ApiError = {
  code: string;
  message: string;
  request_id?: string | null;
  details: Record<string, JsonPrimitive>;
};

export type RequiredComponentPolicy = {
  name: string;
  namespace: string;
  kind: string;
  label_selector: string;
  enabled: boolean;
};

export type InspectionThresholds = {
  tls_warning_days: number;
  tls_critical_days: number;
  pvc_pending_warning_minutes: number;
  pvc_pending_critical_minutes: number;
  pv_released_stale_hours: number;
  job_incomplete_info_minutes: number;
  resource_usage_warning_percent: number;
  resource_usage_consecutive_cycles: number;
  pod_terminating_warning_minutes: number;
  pod_restart_window_minutes: number;
  pod_restart_delta: number;
  warning_event_window_minutes: number;
  node_not_ready_grace_seconds: number;
};

export type InspectionPolicySettings = {
  required_components: RequiredComponentPolicy[];
  thresholds: InspectionThresholds;
  namespace_concurrency: number;
  max_log_pods: number;
  retention: DataRetentionSettings;
};

export type DataRetentionSettings = {
  inspection_run_days: number;
  recovered_issue_days: number;
  notification_delivery_days: number;
  security_audit_days: number;
};

export type SystemComponentStatus = {
  state: ComponentState;
  message: string;
  checked_at: string;
  details: Record<string, JsonPrimitive>;
};

export type SystemStatus = {
  status: "healthy" | "degraded" | "not_ready";
  version: string;
  cluster_id: string;
  database: SystemComponentStatus;
  kubernetes_api: SystemComponentStatus;
  provider: SystemComponentStatus;
  scheduler: SystemComponentStatus;
  metrics_api: SystemComponentStatus;
  notifications: SystemComponentStatus;
  last_inspection: SystemComponentStatus;
  configuration: SystemComponentStatus;
  kubernetes_server_version?: string | null;
  kubernetes_version_supported?: boolean | null;
};

// Transitional alias for the v1.0 settings hook. New code uses SystemStatus.
export type SystemStatusResponse = SystemStatus;

export type InspectionTarget = {
  type: InspectionTargetType;
  namespace?: string | null;
  pod_name?: string | null;
  label_selector?: string | null;
  saved_target_id?: number | null;
  template_id?: number | null;
  resource_scope: string[];
};

export type SavedInspectionTarget = {
  id: number;
  name: string;
  target_type: "namespace" | "pod";
  namespace: string;
  label_selector?: string | null;
  pod_name?: string | null;
  resource_scope: string[];
  created_at?: string | null;
  updated_at?: string | null;
};

export type KeywordHit = {
  keyword: string;
  category: string;
  severity: KeywordHitSeverity;
  source: string;
  matched_text: string;
  context_before?: string[];
  context_after?: string[];
  context_text?: string | null;
  container_name?: string | null;
  whitelisted: boolean;
  whitelist_rule_id?: number | null;
};

export type KeywordRule = {
  id: number;
  keyword: string;
  category: string;
  severity: KeywordHitSeverity;
  description?: string | null;
  enabled: boolean;
  builtin: boolean;
};

export type EvidenceBundle = {
  object_type: string;
  namespace: string;
  name: string;
  status: string;
  node_name?: string | null;
  restarts?: number | null;
  describe_summary?: string | null;
  events: string[];
  resource_usage: Record<string, string>;
  log_hits: KeywordHit[];
  related_resources: Array<Record<string, unknown>>;
};

export type TemplateTarget = {
  target_ref: string;
  namespace: string;
  label_selector?: string | null;
  pod_name_pattern?: string | null;
  resource_scope: string[];
};

export type TemplateCondition = {
  target_ref: string;
  condition_type: TemplateConditionType;
  operator: TemplateConditionOperator;
  expected_value: unknown;
  join_operator?: TemplateConditionJoinOperator | null;
  enabled: boolean;
};

export type TemplateMatchResult = {
  template_id: number;
  template_name: string;
  matched: boolean;
  matched_conditions: TemplateCondition[];
  unmatched_conditions: TemplateCondition[];
  summary?: string | null;
  reason: string;
  suggestion: string;
  risk_note?: string | null;
  evidence_refs: Array<Record<string, unknown>>;
};

export type OverviewIssue = {
  name: string;
  component?: string | null;
  namespace?: string | null;
  node?: string | null;
  status: string;
  summary: string;
};

export type OverviewResponse = {
  health_status: string;
  health_score?: number;
  cluster_status?: string;
  last_checked_at: string;
  issues: OverviewIssue[];
  recent_summary: string;
};

export type ClusterInspectionResult = {
  component: string;
  namespace?: string | null;
  node?: string | null;
  status: string;
  describe_summary?: string | null;
  log_summary?: string | null;
};

export type ClusterInspectionResponse = {
  health_status: string;
  executed_at: string;
  results: ClusterInspectionResult[];
  issues: Issue[];
  coverage: Coverage[];
};

export type NamespaceSummary = {
  name: string;
  status: string;
  pod_count: number;
  abnormal_pod_count: number;
  last_inspected_at?: string | null;
  labels?: Record<string, string>;
  abnormal_categories: AbnormalCategory[];
  resource_usage?: Record<string, string>;
};

export type NamespaceDiscoveryResponse = {
  executed_at: string;
  namespaces: NamespaceSummary[];
};

export type NamespaceLabelSummary = {
  key: string;
  values: string[];
  selector: string;
  pod_count: number;
};

export type NamespaceLabelDiscoveryResponse = {
  namespace: string;
  executed_at: string;
  labels: NamespaceLabelSummary[];
};

export type PodDiscoverySummary = {
  name: string;
  labels: Record<string, string>;
};

export type PodDiscoveryResponse = {
  namespace: string;
  label_selector?: string | null;
  executed_at: string;
  pod_count: number;
  pods: PodDiscoverySummary[];
};

export type InspectedPod = {
  name: string;
  labels: Record<string, string>;
  status: string;
  node_name?: string | null;
  restarts: number;
  containers: Array<{
    name: string;
    restart_count: number;
    state: string;
    reason?: string | null;
  }>;
  events: string[];
  describe_summary: string;
  log_summary?: string | null;
  previous_log_summary?: string | null;
  log_hits: KeywordHit[];
  resource_usage: Record<string, string>;
  related_resources: Array<{
    kind: string;
    name: string;
    status: string;
  }>;
};

export type InspectedObject = {
  name: string;
  status: string;
  summary: string;
};

export type NamespaceInspectionResponse = {
  inspection_target: InspectionTarget;
  namespace: string;
  label_selector?: string | null;
  health_status: string;
  executed_at: string;
  evidence_bundles: EvidenceBundle[];
  pods: InspectedPod[];
  services: InspectedObject[];
  ingresses: InspectedObject[];
  tls_secrets: InspectedObject[];
  daemonsets: InspectedObject[];
  issues: Issue[];
  coverage: Coverage[];
};

export type NamespaceBatchInspectionRequest = {
  namespaces: string[];
  all_namespaces?: boolean;
};

export type NamespaceBatchInspectionResult = {
  summary: NamespaceSummary;
  health_status: string;
  detail_target: InspectionTarget;
};

export type NamespaceBatchInspectionResponse = {
  executed_at: string;
  all_namespaces: boolean;
  requested_namespaces: string[];
  results: NamespaceBatchInspectionResult[];
  issues: Issue[];
  coverage: Coverage[];
};

export type PodInspectionResponse = {
  inspection_target: InspectionTarget;
  namespace: string;
  health_status: string;
  executed_at: string;
  pod: InspectedPod;
  evidence_bundle?: EvidenceBundle | null;
  issues: Issue[];
  coverage: Coverage[];
};

export type DiagnosisMatch = {
  template_id: number;
  template_name: string;
  reason: string;
  suggestion: string;
  command?: string | null;
  risk_note?: string | null;
  evidence: Array<Record<string, unknown>>;
  matched_conditions: Array<{
    target_ref?: string | null;
    type: TemplateConditionType;
    operator: TemplateConditionOperator;
    value: unknown;
    matched: boolean;
    evidence: Array<Record<string, unknown>>;
  }>;
  unmatched_conditions: Array<{
    target_ref?: string | null;
    type: TemplateConditionType;
    operator: TemplateConditionOperator;
    value: unknown;
    matched: boolean;
    evidence: Array<Record<string, unknown>>;
  }>;
};

export type DiagnosisRequest = {
  namespace?: string | null;
  direction?: DiagnosisDirection;
  scope?: string | null;
  template_id?: number | null;
  template_ids?: number[];
};

export type DiagnosisResponse = {
  status: "matched" | "unmatched" | "llm_supplemented";
  inspection_target: InspectionTarget;
  namespace?: string | null;
  direction: DiagnosisDirection;
  scope?: string | null;
  executed_at: string;
  matches: DiagnosisMatch[];
  template_match_results: TemplateMatchResult[];
  evidence_summary: Array<Record<string, unknown>>;
  llm_supplement?: Record<string, unknown> | null;
};

export type FaultTemplate = {
  id: number;
  name: string;
  scenario: string;
  targets: TemplateTarget[];
  target_groups?: Array<{
    ref: string;
    namespace: string;
    label_selector?: string | null;
    name?: string | null;
    object_scope?: string | null;
  }>;
  object_scope?: string | null;
  namespace_scope?: string | null;
  label_selector?: string | null;
  match_conditions: TemplateCondition[];
  joint_rule?: Record<string, unknown> | null;
  reason: string;
  suggestion: string;
  command?: string | null;
  risk_note?: string | null;
  enabled: boolean;
  created_at?: string | null;
  updated_at?: string | null;
};

export type Whitelist = {
  id: number;
  namespace: string;
  label_selector?: string | null;
  pod_name_pattern?: string | null;
  container_name?: string | null;
  keyword: string;
  enabled: boolean;
  note?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type WhitelistCreate = {
  namespace: string;
  label_selector?: string | null;
  pod_name_pattern?: string | null;
  container_name?: string | null;
  keyword: string;
  enabled: boolean;
  note?: string | null;
};

export type WhitelistIgnoreCreate = {
  namespace: string;
  label_selector?: string | null;
  pod_name_pattern?: string | null;
  container_name?: string | null;
  keyword: string;
  note?: string | null;
};

export type SettingsResponse = {
  base_path: string;
  provider_mode: string;
  kubeconfig_path?: string | null;
  kube_context?: string | null;
  llm_enabled: boolean;
  llm_provider: string;
  model_endpoint?: string | null;
  api_key?: string | null;
  default_inspection_strategy: Record<string, unknown>;
  inspection_policy: InspectionPolicySettings;
};

export type SettingsUpdate = SettingsResponse;
