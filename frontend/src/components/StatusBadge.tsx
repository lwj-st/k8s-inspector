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
  running: "运行中",
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
  open: "开放",
  recovered: "已恢复",
  passed: "已检查，无异常",
  abnormal: "已检查，发现异常",
  skipped: "未检查/不适用",
  partial: "部分完成",
  queued: "等待执行",
  delivering: "发送中",
  suppressed: "已抑制",
  unavailable: "不可用",
  ok: "正常",
  not_ready: "未就绪",
};

function formatStatusLabel(status: string) {
  const normalized = status.toLowerCase();
  return statusLabels[normalized] ?? status;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const normalized = status.toLowerCase();
  const goodStatuses = new Set(["healthy", "ready", "succeeded", "completed", "enabled", "recovered", "passed", "ok"]);
  const warningStatuses = new Set(["warning", "degraded", "matched", "open", "abnormal", "partial"]);
  const neutralStatuses = new Set(["info", "unknown", "unmatched", "skipped", "queued", "running", "loading", "disabled", "delivering", "suppressed"]);
  const isBad =
    normalized === "not_ready" ||
    normalized === "unavailable" ||
    normalized.includes("notready") ||
    normalized.includes("fail") ||
    normalized.includes("error") ||
    normalized.includes("crash") ||
    normalized.includes("backoff");
  const toneName = isBad
    ? "bad"
    : goodStatuses.has(normalized)
      ? "good"
      : warningStatuses.has(normalized)
        ? "warn"
        : neutralStatuses.has(normalized)
          ? "neutral"
          : "bad";
  const symbol = toneName === "good" ? "✓" : toneName === "warn" ? "!" : toneName === "bad" ? "×" : "•";

  return (
    <span className={`status-badge status-${toneName}`}>
      <span className="status-symbol" aria-hidden="true">{symbol}</span>
      {formatStatusLabel(status)}
    </span>
  );
}
