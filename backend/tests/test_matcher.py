from app.engine.matcher import match_template


def test_match_template_hits_target_group_conditions() -> None:
    template = {
        "target_groups": [
            {
                "ref": "api",
                "namespace": "demo",
                "label_selector": "app=demo-api",
                "object_scope": "deployment",
            }
        ],
        "match_conditions": [
            {"target_ref": "api", "type": "pod_status", "operator": "in", "value": ["CrashLoopBackOff"]},
            {"target_ref": "api", "type": "log_keyword", "operator": "contains", "value": "connection refused"},
            {"target_ref": "api", "type": "event_keyword", "operator": "contains", "value": "Back-off restarting"},
        ],
        "joint_rule": {"operator": "AND"},
        "reason": "Startup dependency failure",
    }
    context = {
        "targets": {
            "api": {
                "namespace": "demo",
                "label_selector": "app=demo-api",
                "pods": [
                    {
                        "name": "demo-api",
                        "status": "CrashLoopBackOff",
                        "log_summary": "database connection refused",
                        "events": ["Back-off restarting failed container"],
                        "restarts": 5,
                    }
                ],
                "related_objects": {"services": [], "ingresses": [], "daemonsets": [], "tls_secrets": []},
            }
        }
    }

    result = match_template(template, context)

    assert result["matched"] is True
    assert len(result["matched_conditions"]) == 3
    assert result["unmatched_conditions"] == []
    assert result["evidence"]


def test_match_template_reports_unmatched_related_object_condition() -> None:
    template = {
        "target_groups": [
            {
                "ref": "api",
                "namespace": "demo",
                "label_selector": "app=demo-api",
            }
        ],
        "match_conditions": [
            {"target_ref": "api", "type": "pod_status", "operator": "in", "value": ["CrashLoopBackOff"]},
            {
                "target_ref": "api",
                "type": "related_object_status",
                "operator": "equals",
                "value": {"resource": "services", "statuses": ["degraded"]},
            },
        ],
        "joint_rule": {"operator": "AND"},
    }
    context = {
        "targets": {
            "api": {
                "namespace": "demo",
                "label_selector": "app=demo-api",
                "pods": [{"name": "demo-api", "status": "CrashLoopBackOff", "log_summary": "", "events": []}],
                "related_objects": {
                    "services": [{"name": "demo-api", "status": "healthy"}],
                    "ingresses": [],
                    "daemonsets": [],
                    "tls_secrets": [],
                },
            }
        }
    }

    result = match_template(template, context)

    assert result["matched"] is False
    assert len(result["matched_conditions"]) == 1
    assert len(result["unmatched_conditions"]) == 1
    assert result["unmatched_conditions"][0]["type"] == "related_object_status"
