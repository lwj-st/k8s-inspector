import { appConfig } from "../app/config";
import type {
  NamespaceBatchInspectionRequest,
  NamespaceBatchInspectionResponse,
  ClusterInspectionResponse,
  DiagnosisRequest,
  DiagnosisResponse,
  FaultTemplate,
  KeywordRule,
  NamespaceLabelDiscoveryResponse,
  NamespaceDiscoveryResponse,
  NamespaceInspectionResponse,
  OverviewResponse,
  PodInspectionResponse,
  SavedInspectionTarget,
  SettingsResponse,
  SystemStatusResponse,
  Whitelist,
  WhitelistCreate,
  WhitelistIgnoreCreate,
  KeywordHitSeverity,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${appConfig.apiBaseUrl}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

async function requestVoid(path: string, init?: RequestInit): Promise<void> {
  const response = await fetch(`${appConfig.apiBaseUrl}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
}

export function getOverview(): Promise<OverviewResponse> {
  return request("/overview");
}

export function runClusterInspection(): Promise<ClusterInspectionResponse> {
  return request("/inspections/cluster/run", {
    method: "POST",
  });
}

export function discoverNamespaces(): Promise<NamespaceDiscoveryResponse> {
  return request("/discovery/namespaces");
}

export function discoverNamespaceLabels(namespace: string): Promise<NamespaceLabelDiscoveryResponse> {
  return request(`/discovery/namespaces/${encodeURIComponent(namespace)}/labels`);
}

export function runNamespaceInspection(namespace: string, labelSelector: string | null): Promise<NamespaceInspectionResponse> {
  return request("/inspections/namespace/run", {
    method: "POST",
    body: JSON.stringify({ namespace, label_selector: labelSelector || null }),
  });
}

export function runNamespaceBatchInspection(
  payload: NamespaceBatchInspectionRequest,
): Promise<NamespaceBatchInspectionResponse> {
  return request("/inspections/namespaces/run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function runPodInspection(namespace: string, podName: string): Promise<PodInspectionResponse> {
  return request("/inspections/pod/run", {
    method: "POST",
    body: JSON.stringify({ namespace, pod_name: podName }),
  });
}

export function runDiagnosis(payload: DiagnosisRequest = {}): Promise<DiagnosisResponse> {
  return request("/diagnoses/run", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listTemplates(): Promise<FaultTemplate[]> {
  return request("/templates");
}

export function createTemplate(payload: {
  name: string;
  scenario: string;
  targets: Array<{
    target_ref: string;
    namespace: string;
    label_selector?: string | null;
    pod_name_pattern?: string | null;
    resource_scope: string[];
  }>;
  match_conditions: Array<{
    target_ref: string;
    condition_type: "pod_status" | "log_keyword" | "event_keyword" | "restart_count" | "related_object_status";
    operator: "equals" | "in" | "contains" | "gte" | "lte";
    expected_value: unknown;
    join_operator?: "AND" | "OR" | null;
    enabled: boolean;
  }>;
  joint_rule?: { operator: "AND" | "OR" } | null;
  reason: string;
  suggestion: string;
  command?: string | null;
  risk_note?: string | null;
  enabled: boolean;
}): Promise<FaultTemplate> {
  return request("/templates", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateTemplate(
  templateId: number,
  payload: {
    name: string;
    scenario: string;
    targets: Array<{
      target_ref: string;
      namespace: string;
      label_selector?: string | null;
      pod_name_pattern?: string | null;
      resource_scope: string[];
    }>;
    match_conditions: Array<{
      target_ref: string;
      condition_type: "pod_status" | "log_keyword" | "event_keyword" | "restart_count" | "related_object_status";
      operator: "equals" | "in" | "contains" | "gte" | "lte";
      expected_value: unknown;
      join_operator?: "AND" | "OR" | null;
      enabled: boolean;
    }>;
    joint_rule?: { operator: "AND" | "OR" } | null;
    reason: string;
    suggestion: string;
    command?: string | null;
    risk_note?: string | null;
    enabled: boolean;
  },
): Promise<FaultTemplate> {
  return request(`/templates/${templateId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function enableTemplate(templateId: number): Promise<FaultTemplate> {
  return request(`/templates/${templateId}/enable`, {
    method: "POST",
  });
}

export function disableTemplate(templateId: number): Promise<FaultTemplate> {
  return request(`/templates/${templateId}/disable`, {
    method: "POST",
  });
}

export function deleteTemplate(templateId: number): Promise<void> {
  return requestVoid(`/templates/${templateId}`, {
    method: "DELETE",
  });
}

export function exportTemplates(): Promise<FaultTemplate[]> {
  return request("/templates/export");
}

export function importTemplates(payload: Array<{
  name: string;
  scenario: string;
  targets: Array<{
    target_ref: string;
    namespace: string;
    label_selector?: string | null;
    pod_name_pattern?: string | null;
    resource_scope: string[];
  }>;
  match_conditions: Array<{
    target_ref: string;
    condition_type: "pod_status" | "log_keyword" | "event_keyword" | "restart_count" | "related_object_status";
    operator: "equals" | "in" | "contains" | "gte" | "lte";
    expected_value: unknown;
    join_operator?: "AND" | "OR" | null;
    enabled: boolean;
  }>;
  joint_rule?: { operator: "AND" | "OR" } | null;
  reason: string;
  suggestion: string;
  command?: string | null;
  risk_note?: string | null;
  enabled: boolean;
}>): Promise<FaultTemplate[]> {
  return request("/templates/import", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listSavedInspectionTargets(): Promise<SavedInspectionTarget[]> {
  return request("/inspection-targets");
}

export function createSavedInspectionTarget(payload: {
  name: string;
  target_type: "namespace" | "pod";
  namespace: string;
  label_selector?: string | null;
  pod_name?: string | null;
  resource_scope: string[];
}): Promise<SavedInspectionTarget> {
  return request("/inspection-targets", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateSavedInspectionTarget(
  targetId: number,
  payload: {
    name: string;
    target_type: "namespace" | "pod";
    namespace: string;
    label_selector?: string | null;
    pod_name?: string | null;
    resource_scope: string[];
  },
): Promise<SavedInspectionTarget> {
  return request(`/inspection-targets/${targetId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteSavedInspectionTarget(targetId: number): Promise<void> {
  return requestVoid(`/inspection-targets/${targetId}`, {
    method: "DELETE",
  });
}

export function exportSavedInspectionTargets(): Promise<SavedInspectionTarget[]> {
  return request("/inspection-targets/export");
}

export function importSavedInspectionTargets(
  payload: Array<{
    name: string;
    target_type: "namespace" | "pod";
    namespace: string;
    label_selector?: string | null;
    pod_name?: string | null;
    resource_scope: string[];
  }>,
): Promise<SavedInspectionTarget[]> {
  return request("/inspection-targets/import", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function ignoreWhitelistLogHit(payload: WhitelistIgnoreCreate): Promise<Whitelist> {
  return request("/whitelists/ignore", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listKeywords(): Promise<KeywordRule[]> {
  return request("/keywords");
}

export function createKeyword(payload: {
  keyword: string;
  category: string;
  severity: KeywordHitSeverity;
  description?: string | null;
  enabled: boolean;
  builtin?: boolean;
}): Promise<KeywordRule> {
  return request("/keywords", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateKeyword(
  keywordId: number,
  payload: {
    keyword: string;
    category: string;
    severity: KeywordHitSeverity;
    description?: string | null;
    enabled: boolean;
    builtin?: boolean;
  },
): Promise<KeywordRule> {
  return request(`/keywords/${keywordId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteKeyword(keywordId: number): Promise<void> {
  return requestVoid(`/keywords/${keywordId}`, {
    method: "DELETE",
  });
}

export function exportKeywords(): Promise<KeywordRule[]> {
  return request("/keywords/export");
}

export function importKeywords(
  payload: Array<{
    keyword: string;
    category: string;
    severity: KeywordHitSeverity;
    description?: string | null;
    enabled: boolean;
    builtin?: boolean;
  }>,
): Promise<KeywordRule[]> {
  return request("/keywords/import", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function enableKeyword(keywordId: number): Promise<KeywordRule> {
  return request(`/keywords/${keywordId}/enable`, {
    method: "POST",
  });
}

export function disableKeyword(keywordId: number): Promise<KeywordRule> {
  return request(`/keywords/${keywordId}/disable`, {
    method: "POST",
  });
}

export function listWhitelists(): Promise<Whitelist[]> {
  return request("/whitelists");
}

export function createWhitelist(payload: WhitelistCreate): Promise<Whitelist> {
  return request("/whitelists", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateWhitelist(
  whitelistId: number,
  payload: WhitelistCreate,
): Promise<Whitelist> {
  return request(`/whitelists/${whitelistId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteWhitelist(whitelistId: number): Promise<void> {
  return requestVoid(`/whitelists/${whitelistId}`, {
    method: "DELETE",
  });
}

export function exportWhitelists(): Promise<Whitelist[]> {
  return request("/whitelists/export");
}

export function importWhitelists(
  payload: WhitelistCreate[],
): Promise<Whitelist[]> {
  return request("/whitelists/import", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function enableWhitelist(whitelistId: number): Promise<Whitelist> {
  return request(`/whitelists/${whitelistId}/enable`, {
    method: "POST",
  });
}

export function disableWhitelist(whitelistId: number): Promise<Whitelist> {
  return request(`/whitelists/${whitelistId}/disable`, {
    method: "POST",
  });
}

export function getSettings(): Promise<SettingsResponse> {
  return request("/settings");
}

export function getSystemStatus(): Promise<SystemStatusResponse> {
  return request("/system/status");
}
