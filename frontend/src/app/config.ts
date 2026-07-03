export function normalizeBasePath(value: string): string {
  if (!value || value === "/") {
    return "";
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return "";
  }

  const prefixed = trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
  return prefixed.replace(/\/+$/, "");
}

export function getRouterBasename(value: string): string {
  return normalizeBasePath(value) || "/";
}

export function buildApiBaseUrl(value: string): string {
  return `${normalizeBasePath(value)}/api/v1`;
}

const envBasePath = typeof import.meta !== "undefined" ? import.meta.env.VITE_BASE_PATH ?? "" : "";

export const appConfig = {
  basePath: normalizeBasePath(envBasePath),
  routerBasename: getRouterBasename(envBasePath),
  apiBaseUrl: buildApiBaseUrl(envBasePath),
};
