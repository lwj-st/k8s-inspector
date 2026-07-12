import { useEffect, useState } from "react";

import { createKeyword, deleteKeyword, disableKeyword, enableKeyword, exportKeywords, importKeywords, listKeywords, updateKeyword } from "../../api/client";
import type { KeywordHitSeverity, KeywordRule } from "../../api/types";

type CreateKeywordPayload = {
  keyword: string;
  category: string;
  severity: KeywordHitSeverity;
  description?: string | null;
  enabled: boolean;
  builtin?: boolean;
};

type UpdateKeywordPayload = CreateKeywordPayload;

export function useKeywords() {
  const [data, setData] = useState<KeywordRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const result = await listKeywords();
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

  async function create(payload: CreateKeywordPayload) {
    setSaving(true);
    setError(null);
    try {
      const created = await createKeyword(payload);
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

  async function setEnabled(keywordId: number, enabled: boolean) {
    setSaving(true);
    setError(null);
    try {
      const updated = enabled ? await enableKeyword(keywordId) : await disableKeyword(keywordId);
      setData((current) => current.map((item) => (item.id === keywordId ? updated : item)));
      return updated;
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "未知错误";
      setError(message);
      throw reason;
    } finally {
      setSaving(false);
    }
  }

  async function update(keywordId: number, payload: UpdateKeywordPayload) {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateKeyword(keywordId, payload);
      setData((current) => current.map((item) => (item.id === keywordId ? updated : item)));
      return updated;
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "未知错误";
      setError(message);
      throw reason;
    } finally {
      setSaving(false);
    }
  }

  async function remove(keywordId: number) {
    setSaving(true);
    setError(null);
    try {
      await deleteKeyword(keywordId);
      setData((current) => current.filter((item) => item.id !== keywordId));
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
      return await exportKeywords();
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "未知错误";
      setError(message);
      throw reason;
    } finally {
      setSaving(false);
    }
  }

  async function importAll(payload: CreateKeywordPayload[]) {
    setSaving(true);
    setError(null);
    try {
      const imported = await importKeywords(payload);
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
