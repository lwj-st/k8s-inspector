import { useEffect, useState } from "react";

import {
  createSavedInspectionTarget,
  deleteSavedInspectionTarget,
  exportSavedInspectionTargets,
  importSavedInspectionTargets,
  listSavedInspectionTargets,
  updateSavedInspectionTarget,
} from "../../api/client";
import type { SavedInspectionTarget } from "../../api/types";

type TargetType = SavedInspectionTarget["target_type"];

type SaveNamespaceTargetPayload = {
  name: string;
  namespace: string;
  label_selector?: string | null;
  resource_scope: string[];
};

type SavePodTargetPayload = {
  name: string;
  namespace: string;
  pod_name: string;
  resource_scope: string[];
};

export function useSavedInspectionTargets(targetType: TargetType) {
  const [targets, setTargets] = useState<SavedInspectionTarget[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    void listSavedInspectionTargets()
      .then((items) => {
        if (alive) {
          setTargets(items.filter((item) => item.target_type === targetType));
        }
      })
      .catch((reason) => {
        if (alive) {
          setError(reason instanceof Error ? reason.message : "未知错误");
        }
      })
      .finally(() => {
        if (alive) {
          setLoading(false);
        }
      });

    return () => {
      alive = false;
    };
  }, []);

  async function saveTarget(payload: SaveNamespaceTargetPayload | SavePodTargetPayload) {
    setSaving(true);
    setError(null);
    try {
      const created = await createSavedInspectionTarget({
        ...payload,
        target_type: targetType,
      });
      setTargets((current) => [created, ...current]);
      return created;
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "未知错误";
      setError(message);
      throw reason;
    } finally {
      setSaving(false);
    }
  }

  async function updateTarget(
    targetId: number,
    payload: SaveNamespaceTargetPayload | SavePodTargetPayload,
  ) {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateSavedInspectionTarget(targetId, {
        ...payload,
        target_type: targetType,
      });
      setTargets((current) => current.map((item) => (item.id === targetId ? updated : item)));
      return updated;
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "未知错误";
      setError(message);
      throw reason;
    } finally {
      setSaving(false);
    }
  }

  async function exportTargets() {
    setError(null);
    const items = await exportSavedInspectionTargets();
    return items.filter((item) => item.target_type === targetType);
  }

  async function deleteTarget(targetId: number) {
    setSaving(true);
    setError(null);
    try {
      await deleteSavedInspectionTarget(targetId);
      setTargets((current) => current.filter((item) => item.id !== targetId));
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "未知错误";
      setError(message);
      throw reason;
    } finally {
      setSaving(false);
    }
  }

  async function importTargets(payload: Array<{
    name: string;
    target_type: "namespace" | "pod";
    namespace: string;
    label_selector?: string | null;
    pod_name?: string | null;
    resource_scope: string[];
  }>) {
    const filteredPayload = payload.filter((item) => item.target_type === targetType);
    if (filteredPayload.length === 0) {
      setError(null);
      return [];
    }

    setSaving(true);
    setError(null);
    try {
      const created = await importSavedInspectionTargets(filteredPayload);
      const filtered = created.filter((item) => item.target_type === targetType);
      setTargets((current) => [...filtered.reverse(), ...current]);
      return filtered;
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "未知错误";
      setError(message);
      throw reason;
    } finally {
      setSaving(false);
    }
  }

  return { targets, loading, saving, error, saveTarget, updateTarget, deleteTarget, exportTargets, importTargets };
}
