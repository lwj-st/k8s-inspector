from typing import Any


NORMAL_POD_STATUSES = {"running", "healthy", "succeeded", "completed"}


def is_normal_pod_status(status: Any) -> bool:
    return str(status or "").lower() in NORMAL_POD_STATUSES


def is_abnormal_container(state: Any, reason: Any = None, exit_code: Any = None) -> bool:
    normalized_state = str(state or "").lower()
    normalized_reason = str(reason or "").strip().lower()

    if normalized_state == "running":
        return bool(normalized_reason)
    if normalized_state == "terminated":
        return normalized_reason != "completed" or exit_code not in (None, 0)
    return True


def is_abnormal_pod(pod: dict[str, Any]) -> bool:
    if not is_normal_pod_status(pod.get("status")):
        return True
    return any(
        is_abnormal_container(
            container.get("state"),
            container.get("reason"),
            container.get("exit_code"),
        )
        for container in pod.get("containers", [])
    )
