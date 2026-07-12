import { useState } from "react";

import { runPodInspection } from "../../api/client";
import type { PodInspectionResponse } from "../../api/types";

export function useRunPodInspection() {
  const [data, setData] = useState<PodInspectionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(namespace: string, podName: string) {
    setLoading(true);
    setError(null);
    try {
      const result = await runPodInspection(namespace, podName);
      setData(result);
      return result;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "未知错误");
      return null;
    } finally {
      setLoading(false);
    }
  }

  return { data, loading, error, submit };
}
