import { useEffect, useState } from "react";

import { runClusterInspection } from "../../api/client";
import type { ClusterInspectionResponse } from "../../api/types";

export function useRunClusterInspection() {
  const [data, setData] = useState<ClusterInspectionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function execute() {
    setLoading(true);
    setError(null);
    try {
      const result = await runClusterInspection();
      setData(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "未知错误");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void execute();
  }, []);

  return { data, loading, error, execute };
}
