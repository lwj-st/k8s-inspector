def test_create_and_list_template(client) -> None:
    payload = {
        "name": "Pod CrashLoop",
        "scenario": "targeted_diagnosis",
        "target_groups": [
            {
                "ref": "api",
                "name": "demo-api",
                "namespace": "demo",
                "label_selector": "app=demo",
                "object_scope": "deployment",
            }
        ],
        "match_conditions": [
            {"target_ref": "api", "type": "pod_status", "operator": "in", "value": ["CrashLoopBackOff"]}
        ],
        "joint_rule": {"operator": "AND"},
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
    assert list_response.json()[0]["target_groups"][0]["ref"] == "api"
