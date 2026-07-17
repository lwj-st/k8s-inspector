import { useEffect, useState } from "react";

import { discoverNamespaces } from "../../api/client";
import type { NamespaceDiscoveryResponse } from "../../api/types";

export function useDiscoverNamespaces() {
  const [data, setData] = useState<NamespaceDiscoveryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const result = await discoverNamespaces();
      setData(result);
      return result;
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "未知错误";
      setError(message);
      throw reason;
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh().catch(() => undefined);
  }, []);

  return { data, loading, error, refresh };
}
