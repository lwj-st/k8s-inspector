type StatusBadgeProps = {
  status: string;
};

const statusLabels: Record<string, string> = {
  enabled: "启用",
  disabled: "停用",
  loading: "加载中",
  info: "信息",
  unknown: "未知",
  healthy: "正常",
  running: "正常",
  ready: "就绪",
  succeeded: "已完成",
  completed: "已完成",
  warning: "告警",
  error: "异常",
  failed: "失败",
  degraded: "降级",
  critical: "严重",
  matched: "已命中",
  unmatched: "未命中",
};

function formatStatusLabel(status: string) {
  const normalized = status.toLowerCase();
  return statusLabels[normalized] ?? status;
}

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
    : normalized.includes("healthy") || normalized.includes("ready") || normalized.includes("running") || normalized.includes("succeeded") || normalized.includes("completed") || normalized === "enabled"
      ? "status-badge status-good"
        : normalized.includes("warning") || normalized.includes("degraded") || normalized === "matched"
        ? "status-badge status-warn"
        : normalized.includes("info") || normalized.includes("unknown") || normalized === "unmatched"
          ? "status-badge status-neutral"
          : "status-badge status-bad";

  return <span className={tone}>{formatStatusLabel(status)}</span>;
}
