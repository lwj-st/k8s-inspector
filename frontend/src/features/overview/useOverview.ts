import { useEffect, useState } from "react";

import { getOverview } from "../../api/client";
import type { OverviewResponse } from "../../api/types";

export function useOverview() {
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;

    getOverview()
      .then((result) => {
        if (!alive) {
          return;
        }
        setData(result);
      })
      .catch((reason: Error) => {
        if (!alive) {
          return;
        }
        setError(reason.message);
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

  return { data, loading, error };
}
