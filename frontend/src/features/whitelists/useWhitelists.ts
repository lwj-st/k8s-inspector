import { useEffect, useState } from "react";

import { createWhitelist, deleteWhitelist, disableWhitelist, enableWhitelist, exportWhitelists, importWhitelists, listWhitelists, updateWhitelist } from "../../api/client";
import type { Whitelist } from "../../api/types";

type CreateWhitelistPayload = {
  namespace: string;
  label_selector?: string | null;
  pod_name_pattern?: string | null;
  container_name?: string | null;
  keyword: string;
  enabled: boolean;
  note?: string | null;
};

type UpdateWhitelistPayload = CreateWhitelistPayload;

export function useWhitelists() {
  const [data, setData] = useState<Whitelist[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const result = await listWhitelists();
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

  async function create(payload: CreateWhitelistPayload) {
    setSaving(true);
    setError(null);
    try {
      const created = await createWhitelist(payload);
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

  async function setEnabled(whitelistId: number, enabled: boolean) {
    setSaving(true);
    setError(null);
    try {
      const updated = enabled ? await enableWhitelist(whitelistId) : await disableWhitelist(whitelistId);
      setData((current) => current.map((item) => (item.id === whitelistId ? updated : item)));
      return updated;
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "未知错误";
      setError(message);
      throw reason;
    } finally {
      setSaving(false);
    }
  }

  async function update(whitelistId: number, payload: UpdateWhitelistPayload) {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateWhitelist(whitelistId, payload);
      setData((current) => current.map((item) => (item.id === whitelistId ? updated : item)));
      return updated;
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "未知错误";
      setError(message);
      throw reason;
    } finally {
      setSaving(false);
    }
  }

  async function remove(whitelistId: number) {
    setSaving(true);
    setError(null);
    try {
      await deleteWhitelist(whitelistId);
      setData((current) => current.filter((item) => item.id !== whitelistId));
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
      return await exportWhitelists();
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "未知错误";
      setError(message);
      throw reason;
    } finally {
      setSaving(false);
    }
  }

  async function importAll(payload: CreateWhitelistPayload[]) {
    setSaving(true);
    setError(null);
    try {
      const imported = await importWhitelists(payload);
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
