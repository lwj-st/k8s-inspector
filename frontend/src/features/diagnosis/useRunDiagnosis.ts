import { useState } from "react";

import { runDiagnosis } from "../../api/client";
import type { DiagnosisResponse } from "../../api/types";

export function useRunDiagnosis() {
  const [data, setData] = useState<DiagnosisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(payload: { namespace?: string | null; scope?: string | null; template_ids?: number[] } = {}) {
    setLoading(true);
    setError(null);
    try {
      const result = await runDiagnosis(payload);
      setData(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "未知错误");
    } finally {
      setLoading(false);
    }
  }

  return { data, loading, error, submit };
}
