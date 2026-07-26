"""Thread-safe, bounded Pod restart samples shared across collection runs."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta


class RestartSampleStore:
    """Keep only the samples needed to calculate a recent restart delta."""

    def __init__(self) -> None:
        self._samples: dict[str, tuple[int, datetime]] = {}
        self._lock = threading.Lock()

    def observe(
        self,
        *,
        key: str,
        restart_total: int,
        observed_at: datetime,
        window_minutes: int,
    ) -> int:
        with self._lock:
            previous = self._samples.get(key)
            self._samples[key] = (restart_total, observed_at)
            cutoff = observed_at - timedelta(
                minutes=max(window_minutes * 2, 60)
            )
            stale_keys = [
                sample_key
                for sample_key, value in self._samples.items()
                if value[1] < cutoff
            ]
            for sample_key in stale_keys:
                del self._samples[sample_key]
        if not previous:
            return 0
        previous_total, previous_at = previous
        if (observed_at - previous_at).total_seconds() > window_minutes * 60:
            return 0
        return max(0, restart_total - previous_total)
