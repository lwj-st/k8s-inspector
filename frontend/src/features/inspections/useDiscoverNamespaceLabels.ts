import { useEffect, useState } from "react";

import { discoverNamespaceLabels } from "../../api/client";
import type { NamespaceLabelDiscoveryResponse } from "../../api/types";

export function useDiscoverNamespaceLabels(namespace: string) {
  const [data, setData] = useState<NamespaceLabelDiscoveryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!namespace) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }

    let active = true;
    setLoading(true);
    setError(null);
    void discoverNamespaceLabels(namespace)
      .then((result) => {
        if (active) {
          setData(result);
        }
      })
      .catch((reason) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "未知错误");
          setData(null);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [namespace]);

  return { data, loading, error };
}
