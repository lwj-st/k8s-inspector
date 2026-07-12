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


def test_enable_disable_export_and_import_template(client) -> None:
    payload = {
        "name": "Dependency timeout",
        "scenario": "targeted_diagnosis",
        "targets": [
            {
                "target_ref": "api",
                "namespace": "demo",
                "label_selector": "app=demo",
                "resource_scope": ["pods"],
            }
        ],
        "match_conditions": [
            {"target_ref": "api", "condition_type": "log_keyword", "operator": "contains", "expected_value": "timeout"}
        ],
        "joint_rule": {"operator": "AND"},
        "reason": "Downstream timeout",
        "suggestion": "Check dependency health",
        "enabled": True,
    }

    create_response = client.post("/api/v1/templates", json=payload)
    template_id = create_response.json()["id"]

    disable_response = client.post(f"/api/v1/templates/{template_id}/disable")
    enable_response = client.post(f"/api/v1/templates/{template_id}/enable")
    export_response = client.get("/api/v1/templates/export")
    import_response = client.post(
        "/api/v1/templates/import",
        json=[
            {
                "name": "Imported template",
                "scenario": "targeted_diagnosis",
                "targets": [
                    {
                        "target_ref": "worker",
                        "namespace": "demo",
                        "label_selector": "app=worker",
                        "resource_scope": ["pods"],
                    }
                ],
                "match_conditions": [
                    {
                        "target_ref": "worker",
                        "condition_type": "restart_count",
                        "operator": "gte",
                        "expected_value": 3,
                    }
                ],
                "joint_rule": {"operator": "AND"},
                "reason": "Worker restart storm",
                "suggestion": "Check worker dependencies",
                "enabled": True,
            }
        ],
    )

    assert disable_response.status_code == 200
    assert disable_response.json()["enabled"] is False
    assert enable_response.status_code == 200
    assert enable_response.json()["enabled"] is True
    assert export_response.status_code == 200
    assert export_response.json()[0]["name"] in {"Dependency timeout", "Pod CrashLoop"}
    assert import_response.status_code == 200
    assert import_response.json()[0]["name"] == "Imported template"
