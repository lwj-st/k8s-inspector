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
  PodDiscoveryResponse,
  NamespaceInspectionResponse,
  OverviewResponse,
  PodInspectionResponse,
  SavedInspectionTarget,
  SettingsResponse,
  Whitelist,
  WhitelistCreate,
  WhitelistIgnoreCreate,
  KeywordHitSeverity,
  AdminSession,
  ApiError,
  Issue,
  IssueEvent,
  IssueListParams,
  Page,
  InspectionRun,
  InspectionRunDetail,
  InspectionPlan,
  InspectionPlanCreate,
  InspectionPlanUpdate,
  NotificationChannel,
  NotificationChannelCreate,
  NotificationChannelUpdate,
  NotificationTestResponse,
  SettingsUpdate,
  SystemStatus,
} from "./types";

let currentCsrfToken: string | null = null;
let unauthorizedHandler: (() => void) | null = null;

export class ApiClientError extends Error {
  status: number;
  code: string;
  requestId: string | null;
  details: ApiError["details"];

  constructor(status: number, payload: Partial<ApiError>) {
    super(payload.message ?? `Request failed: ${status}`);
    this.name = "ApiClientError";
    this.status = status;
    this.code = payload.code ?? `HTTP_${status}`;
    this.requestId = payload.request_id ?? null;
    this.details = payload.details ?? {};
  }
}

export function configureApiSession(
  csrfToken: string | null,
  onUnauthorized: (() => void) | null = null,
) {
  currentCsrfToken = csrfToken;
  unauthorizedHandler = onUnauthorized;
}

type InternalRequestInit = RequestInit & {
  skipUnauthorizedHandler?: boolean;
};

async function responseError(response: Response): Promise<ApiClientError> {
  let payload: Partial<ApiError> = {};
  try {
    const raw = await response.json() as Partial<ApiError>;
    payload = {
      code: raw.code,
      message: raw.message ?? `Request failed: ${response.status}`,
      request_id: raw.request_id ?? response.headers.get("x-request-id"),
      details: raw.details ?? {},
    };
  } catch {
    payload = {
      message: `请求失败（${response.status}）`,
      request_id: response.headers.get("x-request-id"),
    };
  }
  return new ApiClientError(response.status, payload);
}

async function request<T>(path: string, init?: InternalRequestInit): Promise<T> {
  const { skipUnauthorizedHandler = false, ...fetchInit } = init ?? {};
  const headers = new Headers(fetchInit.headers);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const method = (fetchInit.method ?? "GET").toUpperCase();
  if (currentCsrfToken && ["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    headers.set("X-CSRF-Token", currentCsrfToken);
  }
  const response = await fetch(`${appConfig.apiBaseUrl}${path}`, {
    credentials: "same-origin",
    ...fetchInit,
    headers,
  });

  if (!response.ok) {
    if (response.status === 401 && !skipUnauthorizedHandler) {
      unauthorizedHandler?.();
    }
    throw await responseError(response);
  }

  return (await response.json()) as T;
}

async function requestVoid(path: string, init?: InternalRequestInit): Promise<void> {
  const { skipUnauthorizedHandler = false, ...fetchInit } = init ?? {};
  const headers = new Headers(fetchInit.headers);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const method = (fetchInit.method ?? "GET").toUpperCase();
  if (currentCsrfToken && ["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    headers.set("X-CSRF-Token", currentCsrfToken);
  }
  const response = await fetch(`${appConfig.apiBaseUrl}${path}`, {
    credentials: "same-origin",
    ...fetchInit,
    headers,
  });

  if (!response.ok) {
    if (response.status === 401 && !skipUnauthorizedHandler) {
      unauthorizedHandler?.();
    }
    throw await responseError(response);
  }
}

function queryString(params: Record<string, string | number | boolean | null | undefined>) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, String(value));
    }
  }
  const serialized = query.toString();
  return serialized ? `?${serialized}` : "";
}

export function getOverview(): Promise<OverviewResponse> {
  return request("/overview");
}

export function getSession(): Promise<AdminSession> {
  return request("/auth/session", { skipUnauthorizedHandler: true });
}

export function login(username: string, password: string): Promise<AdminSession> {
  return request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
    skipUnauthorizedHandler: true,
  });
}

export function logout(): Promise<void> {
  return requestVoid("/auth/logout", { method: "POST" });
}

export function listIssues(params: IssueListParams = {}): Promise<Page<Issue>> {
  return request(`/issues${queryString(params)}`);
}

export function getIssue(issueId: number): Promise<Issue> {
  return request(`/issues/${issueId}`);
}

export function listIssueEvents(issueId: number, page = 1, pageSize = 20): Promise<Page<IssueEvent>> {
  return request(`/issues/${issueId}/events${queryString({ page, page_size: pageSize })}`);
}

export function acknowledgeIssue(issueId: number, note: string): Promise<Issue> {
  return request(`/issues/${issueId}/acknowledge`, {
    method: "POST",
    body: JSON.stringify({ note }),
  });
}

export function listInspectionRuns(params: {
  status?: string;
  trigger?: string;
  plan_id?: number;
  page?: number;
  page_size?: number;
} = {}): Promise<Page<InspectionRun>> {
  return request(`/inspection-runs${queryString(params)}`);
}

export function getInspectionRun(runId: number): Promise<InspectionRunDetail> {
  return request(`/inspection-runs/${runId}`);
}

export function listInspectionPlans(page = 1, pageSize = 100): Promise<Page<InspectionPlan>> {
  return request(`/inspection-plans${queryString({ page, page_size: pageSize })}`);
}

export function createInspectionPlan(payload: InspectionPlanCreate): Promise<InspectionPlan> {
  return request("/inspection-plans", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateInspectionPlan(planId: number, payload: InspectionPlanUpdate): Promise<InspectionPlan> {
  return request(`/inspection-plans/${planId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteInspectionPlan(planId: number): Promise<void> {
  return requestVoid(`/inspection-plans/${planId}`, { method: "DELETE" });
}

export function runInspectionPlan(planId: number): Promise<InspectionRun> {
  return request(`/inspection-plans/${planId}/run`, { method: "POST" });
}

export function listNotificationChannels(page = 1, pageSize = 100): Promise<Page<NotificationChannel>> {
  return request(`/notification-channels${queryString({ page, page_size: pageSize })}`);
}

export function createNotificationChannel(payload: NotificationChannelCreate): Promise<NotificationChannel> {
  return request("/notification-channels", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateNotificationChannel(
  channelId: number,
  payload: NotificationChannelUpdate,
): Promise<NotificationChannel> {
  return request(`/notification-channels/${channelId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function deleteNotificationChannel(channelId: number): Promise<void> {
  return requestVoid(`/notification-channels/${channelId}`, { method: "DELETE" });
}

export function testNotificationChannel(channelId: number): Promise<NotificationTestResponse> {
  return request(`/notification-channels/${channelId}/test`, { method: "POST" });
}

export function runClusterInspection(): Promise<ClusterInspectionResponse> {
  return request("/inspections/cluster/run?include_logs=false", {
    method: "POST",
  });
}

export function discoverNamespaces(): Promise<NamespaceDiscoveryResponse> {
  return request("/discovery/namespaces");
}

export function discoverNamespaceLabels(namespace: string): Promise<NamespaceLabelDiscoveryResponse> {
  return request(`/discovery/namespaces/${encodeURIComponent(namespace)}/labels`);
}

export function discoverNamespacePods(
  namespace: string,
  labelSelector: string | null = null,
): Promise<PodDiscoveryResponse> {
  return request(
    `/discovery/namespaces/${encodeURIComponent(namespace)}/pods${queryString({
      label_selector: labelSelector,
    })}`,
  );
}

export function runNamespaceInspection(
  namespace: string,
  labelSelector: string | null,
  includeLogs: boolean,
): Promise<NamespaceInspectionResponse> {
  return request("/inspections/namespace/run", {
    method: "POST",
    body: JSON.stringify({
      namespace,
      label_selector: labelSelector || null,
      include_logs: includeLogs,
    }),
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

export function updateSettings(payload: SettingsUpdate): Promise<SettingsResponse> {
  return request("/settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getSystemStatus(): Promise<SystemStatus> {
  return request("/system/status");
}
