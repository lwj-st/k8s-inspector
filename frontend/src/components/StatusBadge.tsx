type StatusBadgeProps = {
  status: string;
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const normalized = status.toLowerCase();
  const isBad =
    normalized.includes("notready") ||
    normalized.includes("fail") ||
    normalized.includes("error") ||
    normalized.includes("crash") ||
    normalized.includes("backoff");
  const tone = isBad
    ? "status-badge status-bad"
    : normalized.includes("healthy") || normalized.includes("ready") || normalized.includes("running")
      ? "status-badge status-good"
      : normalized.includes("warning") || normalized.includes("degraded") || normalized.includes("enabled")
        ? "status-badge status-warn"
        : normalized.includes("info") || normalized.includes("unknown")
          ? "status-badge status-neutral"
          : "status-badge status-bad";

  return <span className={tone}>{status}</span>;
}
