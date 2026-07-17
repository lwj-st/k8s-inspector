import type { InspectedPod } from "../../api/types";

const NORMAL_POD_STATUSES = new Set(["running", "healthy", "succeeded", "completed"]);

export function isHealthyPod(pod: InspectedPod) {
  if (!NORMAL_POD_STATUSES.has(pod.status.toLowerCase())) {
    return false;
  }

  return pod.containers.every((container) => {
    const state = container.state.toLowerCase();
    const reason = container.reason?.toLowerCase() ?? "";
    return (state === "running" && reason.length === 0) || (state === "terminated" && reason === "completed");
  });
}
