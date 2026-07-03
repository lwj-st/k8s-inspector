import { useEffect, useState } from "react";

import { getSettings, getSystemStatus } from "../../api/client";
import type { SettingsResponse, SystemStatusResponse } from "../../api/types";

export function useSettings() {
  const [data, setData] = useState<SettingsResponse | null>(null);
  const [systemStatus, setSystemStatus] = useState<SystemStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getSettings(), getSystemStatus()])
      .then(([settings, status]) => {
        setData(settings);
        setSystemStatus(status);
      })
      .finally(() => setLoading(false));
  }, []);

  return { data, systemStatus, loading };
}
