import type { InspectedPod } from "../../api/types";

const STABLE_LABEL_PRIORITY = ["app.kubernetes.io/instance", "app", "app.kubernetes.io/name", "k8s-app", "component", "app.kubernetes.io/component"];
const UNSTABLE_LABEL_KEYS = new Set(["pod-template-hash", "controller-revision-hash", "statefulset.kubernetes.io/pod-name"]);

export function labelSelectorOptionsForPod(pod: InspectedPod, currentSelector?: string | null) {
  const options = new Set<string>();
  if (currentSelector?.trim()) {
    options.add(currentSelector.trim());
  }

  Object.entries(pod.labels ?? {})
    .filter(([key, value]) => key.trim() && value.trim() && !UNSTABLE_LABEL_KEYS.has(key))
    .sort(([leftKey], [rightKey]) => {
      const leftRank = STABLE_LABEL_PRIORITY.includes(leftKey) ? STABLE_LABEL_PRIORITY.indexOf(leftKey) : STABLE_LABEL_PRIORITY.length;
      const rightRank = STABLE_LABEL_PRIORITY.includes(rightKey) ? STABLE_LABEL_PRIORITY.indexOf(rightKey) : STABLE_LABEL_PRIORITY.length;
      if (leftRank !== rightRank) {
        return leftRank - rightRank;
      }
      return leftKey.localeCompare(rightKey);
    })
    .forEach(([key, value]) => options.add(`${key}=${value}`));

  return Array.from(options);
}
