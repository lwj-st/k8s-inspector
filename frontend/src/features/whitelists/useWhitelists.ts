import { useEffect, useState } from "react";

import { listWhitelists } from "../../api/client";
import type { Whitelist } from "../../api/types";

export function useWhitelists() {
  const [data, setData] = useState<Whitelist[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listWhitelists()
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  return { data, loading };
}
