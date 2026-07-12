import { useEffect, useState } from "react";

import {
  createTemplate,
  deleteTemplate,
  disableTemplate,
  enableTemplate,
  exportTemplates,
  importTemplates,
  listTemplates,
  updateTemplate,
} from "../../api/client";
import type { FaultTemplate, TemplateCondition, TemplateTarget } from "../../api/types";

type TemplatePayload = {
  name: string;
  scenario: string;
  targets: TemplateTarget[];
  match_conditions: TemplateCondition[];
  joint_rule?: { operator: "AND" | "OR" } | null;
  reason: string;
  suggestion: string;
  command?: string | null;
  risk_note?: string | null;
  enabled: boolean;
};

export function useTemplates() {
  const [data, setData] = useState<FaultTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const result = await listTemplates();
    setData(result);
    return result;
  }

  useEffect(() => {
    refresh()
      .catch((reason) => {
        setError(reason instanceof Error ? reason.message : "未知错误");
      })
      .finally(() => setLoading(false));
  }, []);

  async function create(payload: TemplatePayload) {
    setSaving(true);
    setError(null);
    try {
      const created = await createTemplate(payload);
      setData((current) => [created, ...current]);
      return created;
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "未知错误";
      setError(message);
      throw reason;
    } finally {
      setSaving(false);
    }
  }

  async function update(templateId: number, payload: TemplatePayload) {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateTemplate(templateId, payload);
      setData((current) => current.map((item) => (item.id === templateId ? updated : item)));
      return updated;
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "未知错误";
      setError(message);
      throw reason;
    } finally {
      setSaving(false);
    }
  }

  async function remove(templateId: number) {
    setSaving(true);
    setError(null);
    try {
      await deleteTemplate(templateId);
      setData((current) => current.filter((item) => item.id !== templateId));
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "未知错误";
      setError(message);
      throw reason;
    } finally {
      setSaving(false);
    }
  }

  async function setEnabled(templateId: number, enabled: boolean) {
    setSaving(true);
    setError(null);
    try {
      const updated = enabled ? await enableTemplate(templateId) : await disableTemplate(templateId);
      setData((current) => current.map((item) => (item.id === templateId ? updated : item)));
      return updated;
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "未知错误";
      setError(message);
      throw reason;
    } finally {
      setSaving(false);
    }
  }

  async function exportAll() {
    setSaving(true);
    setError(null);
    try {
      return await exportTemplates();
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "未知错误";
      setError(message);
      throw reason;
    } finally {
      setSaving(false);
    }
  }

  async function importAll(payload: TemplatePayload[]) {
    setSaving(true);
    setError(null);
    try {
      const imported = await importTemplates(payload);
      setData((current) => [...imported, ...current]);
      return imported;
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "未知错误";
      setError(message);
      throw reason;
    } finally {
      setSaving(false);
    }
  }

  return { data, loading, saving, error, refresh, create, update, remove, setEnabled, exportAll, importAll };
}
