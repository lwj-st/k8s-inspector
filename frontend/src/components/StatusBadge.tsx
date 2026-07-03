type StatusBadgeProps = {
  status: string;
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const normalized = status.toLowerCase();
  const tone =
    normalized.includes("healthy") || normalized.includes("ready")
      ? "status-badge status-good"
      : normalized.includes("warning") || normalized.includes("degraded")
        ? "status-badge status-warn"
        : "status-badge status-bad";

  return <span className={tone}>{status}</span>;
}
