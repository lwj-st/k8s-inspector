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

export type InspectedPod = {
  name: string;
  status: string;
  restarts: number;
  events: string[];
  describe_summary: string;
  log_summary?: string | null;
  resource_usage: Record<string, string>;
};

export type InspectedObject = {
  name: string;
  status: string;
  summary: string;
};

export type NamespaceInspectionResponse = {
  namespace: string;
  label_selector?: string | null;
  health_status: string;
  executed_at: string;
  pods: InspectedPod[];
  services: InspectedObject[];
  ingresses: InspectedObject[];
  tls_secrets: InspectedObject[];
  daemonsets: InspectedObject[];
};

export type DiagnosisMatch = {
  template_id: number;
  template_name: string;
  reason: string;
  suggestion: string;
  command?: string | null;
  risk_note?: string | null;
  evidence: Array<Record<string, unknown>>;
};

export type DiagnosisResponse = {
  status: "matched" | "unmatched" | "llm_supplemented";
  namespace: string;
  direction: string;
  scope?: string | null;
  executed_at: string;
  matches: DiagnosisMatch[];
  evidence_summary: Array<Record<string, unknown>>;
  llm_supplement?: Record<string, unknown> | null;
};

export type FaultTemplate = {
  id: number;
  name: string;
  scenario: string;
  object_scope?: string | null;
  namespace_scope?: string | null;
  label_selector?: string | null;
  match_conditions: Array<Record<string, unknown>>;
  joint_rule?: Record<string, unknown> | null;
  reason: string;
  suggestion: string;
  command?: string | null;
  risk_note?: string | null;
  enabled: boolean;
};

export type Whitelist = {
  id: number;
  namespace: string;
  label_selector?: string | null;
  keyword: string;
  enabled: boolean;
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
