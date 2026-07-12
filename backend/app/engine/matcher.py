from __future__ import annotations

from typing import Any


def _operator(condition: dict[str, Any]) -> str:
    return str(condition.get("operator") or "equals")


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


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _matches_scalar(operator: str, actual: Any, expected: Any) -> bool:
    if operator == "equals":
        return actual == expected
    if operator == "in":
        return actual in set(_as_list(expected))
    if operator == "contains":
        if actual is None:
            return False
        expected_values = [str(item) for item in _as_list(expected) if item is not None]
        actual_text = str(actual)
        return any(item in actual_text for item in expected_values)
    if operator == "gte":
        try:
            return float(actual) >= float(expected)
        except (TypeError, ValueError):
            return False
    if operator == "lte":
        try:
            return float(actual) <= float(expected)
        except (TypeError, ValueError):
            return False
    return False


def _match_pod_status(condition: dict[str, Any], target: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    operator = _operator(condition)
    expected = _expected_value(condition)
    matched = [
        pod["name"]
        for pod in target.get("pods", [])
        if _matches_scalar(operator, pod.get("status"), expected)
    ]
    if not matched:
        return False, []
    return True, [{"type": "pod_status", "pods": matched, "value": expected}]


def _match_log_keyword(condition: dict[str, Any], target: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    operator = _operator(condition)
    expected = _expected_value(condition)
    evidence = []
    for pod in target.get("pods", []):
        for hit in pod.get("log_hits", []):
            if hit.get("whitelisted"):
                continue
            keyword_matched = _matches_scalar(operator, hit.get("keyword"), expected)
            text_matched = operator == "contains" and _matches_scalar(operator, hit.get("matched_text"), expected)
            if keyword_matched or text_matched:
                evidence.append(
                    {
                        "type": "log_keyword",
                        "pod": pod["name"],
                        "value": expected,
                        "matched_text": hit.get("matched_text") or "",
                        "container_name": hit.get("container_name"),
                    }
                )
                break
    return (len(evidence) > 0, evidence)


def _match_event_keyword(condition: dict[str, Any], target: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    operator = _operator(condition)
    expected = _expected_value(condition)
    evidence = []
    for pod in target.get("pods", []):
        for event in pod.get("events", []):
            if _matches_scalar(operator, str(event), expected):
                evidence.append({"type": "event_keyword", "pod": pod["name"], "value": expected, "matched_text": str(event)})
                break
    return (len(evidence) > 0, evidence)


def _match_restart_count(condition: dict[str, Any], target: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    operator = _operator(condition)
    expected = _expected_value(condition)
    matched = [
        pod["name"]
        for pod in target.get("pods", [])
        if _matches_scalar(operator, int(pod.get("restarts", 0)), expected)
    ]
    if not matched:
        return False, []
    return True, [{"type": "restart_count", "pods": matched, "value": expected}]


def _match_related_object_status(condition: dict[str, Any], target: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    expected = _expected_value(condition) or {}
    resource = expected.get("resource")
    operator = _operator(condition)
    statuses = expected.get("statuses", [])
    objects = target.get("related_objects", {}).get(resource, [])
    matched = [
        item["name"]
        for item in objects
        if _matches_scalar(operator, item.get("status"), statuses if operator == "in" else (statuses[0] if statuses else None))
    ]
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
