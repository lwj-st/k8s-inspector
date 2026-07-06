from __future__ import annotations

from typing import Any


def _condition_type(condition: dict[str, Any]) -> str:
    return str(condition.get("condition_type") or condition.get("type") or "")


def _expected_value(condition: dict[str, Any]) -> Any:
    return condition.get("expected_value", condition.get("value"))


def _normalize_targets(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    targets = context.get("targets")
    if isinstance(targets, dict) and targets:
        return targets
    return {
        "default": {
            "namespace": context.get("namespace"),
            "label_selector": context.get("label_selector"),
            "pods": context.get("pods", []),
            "related_objects": context.get("related_objects", {}),
        }
    }


def _condition_result(condition: dict[str, Any], matched: bool, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "target_ref": condition.get("target_ref"),
        "type": _condition_type(condition),
        "operator": condition.get("operator"),
        "value": _expected_value(condition),
        "matched": matched,
        "evidence": evidence,
    }


def _match_pod_status(condition: dict[str, Any], target: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    statuses = set(_expected_value(condition) or [])
    matched = [pod["name"] for pod in target.get("pods", []) if pod.get("status") in statuses]
    if not matched:
        return False, []
    return True, [{"type": "pod_status", "pods": matched, "value": list(statuses)}]


def _match_log_keyword(condition: dict[str, Any], target: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    keyword = str(_expected_value(condition) or "")
    evidence = []
    for pod in target.get("pods", []):
        log_summary = str(pod.get("log_summary") or "")
        if keyword and keyword in log_summary:
            evidence.append({"type": "log_keyword", "pod": pod["name"], "value": keyword, "matched_text": log_summary})
    return (len(evidence) > 0, evidence)


def _match_event_keyword(condition: dict[str, Any], target: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    keyword = str(_expected_value(condition) or "")
    evidence = []
    for pod in target.get("pods", []):
        for event in pod.get("events", []):
            if keyword and keyword in str(event):
                evidence.append({"type": "event_keyword", "pod": pod["name"], "value": keyword, "matched_text": str(event)})
                break
    return (len(evidence) > 0, evidence)


def _match_restart_count(condition: dict[str, Any], target: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    threshold = int(_expected_value(condition) or 0)
    matched = [pod["name"] for pod in target.get("pods", []) if int(pod.get("restarts", 0)) >= threshold]
    if not matched:
        return False, []
    return True, [{"type": "restart_count", "pods": matched, "value": threshold}]


def _match_related_object_status(condition: dict[str, Any], target: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    expected = _expected_value(condition) or {}
    resource = expected.get("resource")
    statuses = set(expected.get("statuses", []))
    objects = target.get("related_objects", {}).get(resource, [])
    matched = [item["name"] for item in objects if item.get("status") in statuses]
    if not matched:
        return False, []
    return True, [{"type": "related_object_status", "resource": resource, "objects": matched, "value": expected}]


def _evaluate_condition(condition: dict[str, Any], target: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    kind = _condition_type(condition)
    if kind == "pod_status":
        return _match_pod_status(condition, target)
    if kind == "log_keyword":
        return _match_log_keyword(condition, target)
    if kind == "event_keyword":
        return _match_event_keyword(condition, target)
    if kind == "restart_count":
        return _match_restart_count(condition, target)
    if kind == "related_object_status":
        return _match_related_object_status(condition, target)
    return False, []


def match_template(template: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    matched_conditions: list[dict[str, Any]] = []
    unmatched_conditions: list[dict[str, Any]] = []
    targets = _normalize_targets(context)
    conditions = [condition for condition in template.get("match_conditions", []) if condition.get("enabled", True)]

    for condition in conditions:
        target_ref = condition.get("target_ref", "default")
        target = targets.get(target_ref, {})
        matched, condition_evidence = _evaluate_condition(condition, target)
        if matched:
            matched_conditions.append(_condition_result(condition, True, condition_evidence))
            evidence.extend(condition_evidence)
        else:
            unmatched_conditions.append(_condition_result(condition, False, []))

    joint_rule = template.get("joint_rule") or {}
    operator = str(joint_rule.get("operator") or "AND").upper()
    if not conditions:
        matched = False
    elif operator == "OR":
        matched = len(matched_conditions) > 0
    else:
        matched = len(unmatched_conditions) == 0

    return {
        "matched": matched,
        "evidence": evidence,
        "matched_conditions": matched_conditions,
        "unmatched_conditions": unmatched_conditions,
    }
