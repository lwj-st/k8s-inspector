def match_template(template: dict, context: dict) -> dict:
    evidence: list[dict] = []
    pods = context.get("pods", [])
    conditions = template.get("match_conditions", [])

    for condition in conditions:
        condition_type = condition.get("type")
        if condition_type == "pod_status":
            matched = [pod for pod in pods if pod.get("status") in condition.get("value", [])]
            if matched:
                evidence.append({"type": "pod_status", "pods": [pod["name"] for pod in matched], "value": condition.get("value", [])})
        elif condition_type == "log_keyword":
            keyword = str(condition.get("value", ""))
            matched = [pod for pod in pods if keyword in str(pod.get("log_summary") or "")]
            if matched:
                evidence.append({"type": "log_keyword", "pods": [pod["name"] for pod in matched], "value": keyword})
        elif condition_type == "restart_count":
            threshold = int(condition.get("value", 0))
            matched = [pod for pod in pods if int(pod.get("restarts", 0)) >= threshold]
            if matched:
                evidence.append({"type": "restart_count", "pods": [pod["name"] for pod in matched], "value": threshold})

    return {
        "matched": len(evidence) == len(conditions) and len(conditions) > 0,
        "evidence": evidence,
    }
