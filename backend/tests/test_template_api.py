def test_create_and_list_template(client) -> None:
    payload = {
        "name": "Pod CrashLoop",
        "scenario": "targeted_diagnosis",
        "object_scope": "deployment",
        "namespace_scope": "demo",
        "label_selector": "app=demo",
        "match_conditions": [{"type": "pod_status", "operator": "in", "value": ["CrashLoopBackOff"]}],
        "joint_rule": None,
        "reason": "Application startup failure",
        "suggestion": "Check startup configuration",
        "command": "kubectl logs -n demo deploy/demo",
        "risk_note": "Read-only command",
        "enabled": True,
    }

    create_response = client.post("/api/v1/templates", json=payload)
    list_response = client.get("/api/v1/templates")

    assert create_response.status_code == 201
    assert list_response.status_code == 200
    assert list_response.json()[0]["name"] == "Pod CrashLoop"
