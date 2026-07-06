def test_run_diagnosis_uses_template_targets_and_returns_condition_breakdown(client) -> None:
    client.post(
        "/api/v1/templates",
        json={
            "name": "CrashLoop template",
            "scenario": "targeted_diagnosis",
            "target_groups": [
                {
                    "ref": "api",
                    "namespace": "demo",
                    "label_selector": "app=demo",
                    "object_scope": "deployment",
                }
            ],
            "match_conditions": [
                {"target_ref": "api", "type": "pod_status", "operator": "in", "value": ["CrashLoopBackOff"]},
                {"target_ref": "api", "type": "log_keyword", "operator": "contains", "value": "connection refused"},
            ],
            "joint_rule": {"operator": "AND"},
            "reason": "Dependency startup failure",
            "suggestion": "Check downstream service",
            "command": "kubectl logs -n demo deploy/demo-api",
            "risk_note": "Read-only command",
            "enabled": True,
        },
    )

    response = client.post("/api/v1/diagnoses/run", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "matched"
    assert body["matches"][0]["template_name"] == "CrashLoop template"
    assert len(body["matches"][0]["matched_conditions"]) == 2
    assert body["matches"][0]["unmatched_conditions"] == []
    assert body["matches"][0]["matched_conditions"][0]["type"] == "pod_status"
    assert body["template_match_results"][0]["matched_conditions"][0]["condition_type"] == "pod_status"
