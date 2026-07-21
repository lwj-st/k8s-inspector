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
};

export type NamespaceSummary = {
  name: string;
  status: string;
  pod_count: number;
  abnormal_pod_count: number;
  last_inspected_at?: string | null;
  labels: Record<string, string>;
  abnormal_categories: AbnormalCategory[];
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

export type InspectedPod = {
  name: string;
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
};

export type PodInspectionResponse = {
  inspection_target: InspectionTarget;
  namespace: string;
  health_status: string;
  executed_at: string;
  pod: InspectedPod;
  evidence_bundle?: EvidenceBundle | null;
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
  provider_mode?: string;
  kubeconfig_path?: string | null;
  kube_context?: string | null;
  llm_enabled?: boolean;
  llm_provider?: string;
  model_endpoint?: string | null;
  api_key?: string | null;
  default_inspection_strategy?: Record<string, unknown>;
  model?: string;
  default_namespace?: string;
  system_status?: string;
};

export type SystemStatusResponse = {
  status: string;
  version: string;
  message: string;
  provider_mode?: string;
  kube_context?: string | null;
};
