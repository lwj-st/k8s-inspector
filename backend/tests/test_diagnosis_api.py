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


def test_run_diagnosis_passes_template_target_namespace_and_label_selector(client) -> None:
    recorded_calls: list[tuple[str, str | None]] = []

    def run_namespace(namespace: str, label_selector: str | None) -> dict:
        recorded_calls.append((namespace, label_selector))
        return {
            "inspection_target": {
                "type": "namespace",
                "namespace": namespace,
                "label_selector": label_selector,
                "resource_scope": ["pods", "services", "ingresses", "daemonsets", "secrets"],
            },
            "namespace": namespace,
            "label_selector": label_selector,
            "health_status": "warning",
            "executed_at": "2026-07-17T08:00:00Z",
            "pods": [
                {
                    "name": "demo-api-1",
                    "status": "CrashLoopBackOff",
                    "node_name": "node-a",
                    "restarts": 3,
                    "containers": [{"name": "demo-api", "restart_count": 3, "state": "waiting", "reason": "CrashLoopBackOff"}],
                    "events": [],
                    "describe_summary": "demo failed",
                    "log_summary": "connection refused",
                    "previous_log_summary": None,
                    "resource_usage": {},
                    "related_resources": [],
                }
            ],
            "services": [],
            "ingresses": [],
            "tls_secrets": [],
            "daemonsets": [],
        }

    client.app.state.provider.run_namespace_inspection = run_namespace

    create_response = client.post(
        "/api/v1/templates",
        json={
            "name": "Targeted template",
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
            ],
            "joint_rule": {"operator": "AND"},
            "reason": "Dependency startup failure",
            "suggestion": "Check downstream service",
            "enabled": True,
        },
    )

    assert create_response.status_code == 201

    response = client.post("/api/v1/diagnoses/run", json={})

    assert response.status_code == 200
    assert recorded_calls == [("demo", "app=demo")]
    body = response.json()
    assert body["matches"][0]["template_name"] == "Targeted template"
    assert body["evidence_summary"]


def test_run_diagnosis_isolates_single_template_collection_failure(client) -> None:
    client.app.state.provider.run_namespace_inspection = lambda namespace, label_selector: (
        (_ for _ in ()).throw(RuntimeError("provider failed"))
        if namespace == "broken"
        else {
            "inspection_target": {
                "type": "namespace",
                "namespace": namespace,
                "label_selector": label_selector,
                "resource_scope": ["pods", "services", "ingresses", "daemonsets", "secrets"],
            },
            "namespace": namespace,
            "label_selector": label_selector,
            "health_status": "warning",
            "executed_at": "2026-07-17T08:00:00Z",
            "pods": [
                {
                    "name": f"{namespace}-api-1",
                    "status": "CrashLoopBackOff",
                    "node_name": "node-a",
                    "restarts": 3,
                    "containers": [{"name": "demo-api", "restart_count": 3, "state": "waiting", "reason": "CrashLoopBackOff"}],
                    "events": [],
                    "describe_summary": "demo failed",
                    "log_summary": "connection refused",
                    "previous_log_summary": None,
                    "resource_usage": {},
                    "related_resources": [],
                }
            ],
            "services": [],
            "ingresses": [],
            "tls_secrets": [],
            "daemonsets": [],
        }
    )

    first_template = client.post(
        "/api/v1/templates",
        json={
            "name": "Healthy collection template",
            "scenario": "targeted_diagnosis",
            "target_groups": [{"ref": "api", "namespace": "demo", "label_selector": "app=demo"}],
            "match_conditions": [
                {"target_ref": "api", "type": "pod_status", "operator": "in", "value": ["CrashLoopBackOff"]},
            ],
            "joint_rule": {"operator": "AND"},
            "reason": "Dependency startup failure",
            "suggestion": "Check downstream service",
            "enabled": True,
        },
    )
    second_template = client.post(
        "/api/v1/templates",
        json={
            "name": "Broken collection template",
            "scenario": "targeted_diagnosis",
            "target_groups": [{"ref": "api", "namespace": "broken", "label_selector": "app=broken"}],
            "match_conditions": [
                {"target_ref": "api", "type": "pod_status", "operator": "in", "value": ["CrashLoopBackOff"]},
            ],
            "joint_rule": {"operator": "AND"},
            "reason": "Broken namespace",
            "suggestion": "Check provider",
            "enabled": True,
        },
    )

    assert first_template.status_code == 201
    assert second_template.status_code == 201

    response = client.post("/api/v1/diagnoses/run", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "matched"
    assert [item["template_name"] for item in body["matches"]] == ["Healthy collection template"]
    result_by_name = {item["template_name"]: item for item in body["template_match_results"]}
    assert result_by_name["Healthy collection template"]["matched"] is True
    assert result_by_name["Broken collection template"]["matched"] is False
    assert result_by_name["Broken collection template"]["summary"] == "Broken collection template 采集失败"
    assert result_by_name["Broken collection template"]["reason"] == "provider failed"


def test_run_diagnosis_ignore_whitelist_prevents_log_keyword_template_match(client) -> None:
    template_response = client.post(
        "/api/v1/templates",
        json={
            "name": "Ignored log template",
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
                {"target_ref": "api", "type": "log_keyword", "operator": "contains", "value": "connection refused"},
            ],
            "joint_rule": {"operator": "AND"},
            "reason": "Dependency startup failure",
            "suggestion": "Check downstream service",
            "enabled": True,
        },
    )
    assert template_response.status_code == 201

    ignore_response = client.post(
        "/api/v1/whitelists/ignore",
        json={
            "namespace": "demo",
            "label_selector": "app=demo",
            "pod_name_pattern": "demo-api-*",
            "container_name": "demo-api",
            "keyword": "connection refused",
            "note": "ignored from diagnosis regression",
        },
    )
    assert ignore_response.status_code == 201

    response = client.post("/api/v1/diagnoses/run", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unmatched"
    assert body["matches"] == []
    assert body["evidence_summary"] == []
    assert body["template_match_results"][0]["template_name"] == "Ignored log template"
    assert body["template_match_results"][0]["matched"] is False
    assert body["template_match_results"][0]["matched_conditions"] == []
    assert len(body["template_match_results"][0]["unmatched_conditions"]) == 1
    assert body["template_match_results"][0]["unmatched_conditions"][0]["condition_type"] == "log_keyword"


def test_run_diagnosis_filters_pods_by_template_name_pattern(client) -> None:
    template_response = client.post(
        "/api/v1/templates",
        json={
            "name": "Pattern scoped template",
            "scenario": "targeted_diagnosis",
            "target_groups": [
                {
                    "ref": "api",
                    "namespace": "demo",
                    "label_selector": "app=demo",
                    "pod_name_pattern": "demo-api-*",
                }
            ],
            "match_conditions": [
                {"target_ref": "api", "type": "pod_status", "operator": "equals", "value": "CrashLoopBackOff"},
            ],
            "joint_rule": {"operator": "AND"},
            "reason": "API startup failure",
            "suggestion": "Check API dependencies",
            "enabled": True,
        },
    )
    assert template_response.status_code == 201

    client.app.state.provider.run_namespace_inspection = lambda namespace, label_selector: {
        "namespace": namespace,
        "label_selector": label_selector,
        "health_status": "warning",
        "executed_at": "2026-07-17T00:00:00Z",
        "pods": [
            {
                "name": "demo-api-1",
                "status": "CrashLoopBackOff",
                "containers": [],
                "events": [],
                "restarts": 4,
                "log_summary": None,
            },
            {
                "name": "demo-worker-1",
                "status": "CrashLoopBackOff",
                "containers": [],
                "events": [],
                "restarts": 4,
                "log_summary": None,
            },
        ],
        "services": [],
        "ingresses": [],
        "daemonsets": [],
        "tls_secrets": [],
    }

    response = client.post("/api/v1/diagnoses/run", json={})

    assert response.status_code == 200
    result = response.json()["template_match_results"][0]
    assert result["matched"] is True
    assert result["evidence_refs"][0]["pods"] == ["demo-api-1"]
