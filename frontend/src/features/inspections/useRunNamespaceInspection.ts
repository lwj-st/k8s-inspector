import { useState } from "react";

import { runNamespaceInspection } from "../../api/client";
import type { NamespaceInspectionResponse } from "../../api/types";

export function useRunNamespaceInspection() {
  const [data, setData] = useState<NamespaceInspectionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(namespace: string, labelSelector: string | null) {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const result = await runNamespaceInspection(namespace, labelSelector);
      setData(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "未知错误");
    } finally {
      setLoading(false);
    }
  }

  return { data, loading, error, submit };
}
