import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

function normalizeBasePath(value?: string): string {
  if (!value || value === "/") {
    return "/";
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return "/";
  }

  const prefixed = trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
  return `${prefixed.replace(/\/+$/, "")}/`;
}

export default defineConfig({
  base: normalizeBasePath(process.env.VITE_BASE_PATH),
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts"
  }
});
