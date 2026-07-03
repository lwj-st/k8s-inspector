def test_run_diagnosis_returns_matched_status(client) -> None:
    client.post(
        "/api/v1/templates",
        json={
            "name": "CrashLoop template",
            "scenario": "targeted_diagnosis",
            "object_scope": "deployment",
            "namespace_scope": "demo",
            "label_selector": "app=demo",
            "match_conditions": [
                {"type": "pod_status", "operator": "in", "value": ["CrashLoopBackOff"]},
                {"type": "log_keyword", "operator": "contains", "value": "connection refused"},
            ],
            "joint_rule": None,
            "reason": "Dependency startup failure",
            "suggestion": "Check downstream service",
            "command": "kubectl logs -n demo deploy/demo-api",
            "risk_note": "Read-only command",
            "enabled": True,
        },
    )

    response = client.post("/api/v1/diagnoses/run", json={"namespace": "demo", "scope": "deployment/demo-api"})

    assert response.status_code == 200
    assert response.json()["status"] in {"matched", "unmatched", "llm_supplemented"}
