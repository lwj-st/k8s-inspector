import { appConfig } from "../app/config";
import type {
  ClusterInspectionResponse,
  DiagnosisResponse,
  FaultTemplate,
  NamespaceInspectionResponse,
  OverviewResponse,
  SettingsResponse,
  SystemStatusResponse,
  Whitelist,
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

export function getOverview(): Promise<OverviewResponse> {
  return request("/overview");
}

export function runClusterInspection(): Promise<ClusterInspectionResponse> {
  return request("/inspections/cluster/run", {
    method: "POST",
  });
}

export function runNamespaceInspection(namespace: string, labelSelector: string): Promise<NamespaceInspectionResponse> {
  return request("/inspections/namespace/run", {
    method: "POST",
    body: JSON.stringify({ namespace, label_selector: labelSelector || null }),
  });
}

export function runDiagnosis(namespace: string, scope: string): Promise<DiagnosisResponse> {
  return request("/diagnoses/run", {
    method: "POST",
    body: JSON.stringify({ namespace, scope }),
  });
}

export function listTemplates(): Promise<FaultTemplate[]> {
  return request("/templates");
}

export function listWhitelists(): Promise<Whitelist[]> {
  return request("/whitelists");
}

export function getSettings(): Promise<SettingsResponse> {
  return request("/settings");
}

export function getSystemStatus(): Promise<SystemStatusResponse> {
  return request("/system/status");
}
