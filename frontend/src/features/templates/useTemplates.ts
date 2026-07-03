import { useEffect, useState } from "react";

import { listTemplates } from "../../api/client";
import type { FaultTemplate } from "../../api/types";

export function useTemplates() {
  const [data, setData] = useState<FaultTemplate[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listTemplates()
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  return { data, loading };
}
