from unittest.mock import patch

from app.schemas.common import KeywordHit


def _namespace_batch_discovery_summary() -> dict:
    return {
        "executed_at": "2026-07-13T00:00:00Z",
        "namespaces": [
            {
                "name": "demo",
                "status": "healthy",
                "pod_count": 99,
                "abnormal_pod_count": 0,
                "last_inspected_at": "2026-07-12T00:00:00Z",
                "labels": {"team": "platform"},
                "abnormal_categories": [],
            }
        ],
    }


def _namespace_batch_inspection_payload(
    *,
    health_status: str = "healthy",
    executed_at: str = "2026-07-13T08:00:00Z",
    pods: list[dict] | None = None,
    services: list[dict] | None = None,
    ingresses: list[dict] | None = None,
    tls_secrets: list[dict] | None = None,
    daemonsets: list[dict] | None = None,
) -> dict:
    return {
        "inspection_target": {
            "type": "namespace",
            "namespace": "demo",
            "label_selector": None,
            "saved_target_id": None,
            "template_id": None,
            "resource_scope": ["pods", "services", "ingresses", "daemonsets", "secrets"],
        },
        "namespace": "demo",
        "label_selector": None,
        "health_status": health_status,
        "executed_at": executed_at,
        "evidence_bundles": [],
        "pods": pods or [],
        "services": services or [],
        "ingresses": ingresses or [],
        "tls_secrets": tls_secrets or [],
        "daemonsets": daemonsets or [],
    }


def _inspected_pod(
    *,
    status: str = "Running",
    containers: list[dict] | None = None,
    events: list[str] | None = None,
    log_summary: str | None = None,
    log_hits: list[dict] | None = None,
    related_resources: list[dict] | None = None,
) -> dict:
    return {
        "name": "demo-api-1",
        "status": status,
        "node_name": "node-a",
        "restarts": 0,
        "containers": containers or [{"name": "demo-api", "restart_count": 0, "state": "running", "reason": None}],
        "events": events or [],
        "describe_summary": "demo summary",
        "log_summary": log_summary,
        "previous_log_summary": None,
        "log_hits": log_hits or [],
        "resource_usage": {},
        "related_resources": related_resources or [],
    }


def test_run_namespace_inspection_returns_pod_evidence(client) -> None:
    response = client.post(
        "/api/v1/inspections/namespace/run",
        json={"namespace": "demo", "label_selector": "app=demo"},
    )

    payload = response.json()

    assert response.status_code == 200
    assert payload["namespace"] == "demo"
    assert payload["pods"][0]["describe_summary"]
    assert "log_summary" in payload["pods"][0]


def test_run_namespace_inspection_returns_structured_pod_evidence(client) -> None:
    response = client.post(
        "/api/v1/inspections/namespace/run",
        json={"namespace": "demo", "label_selector": "app=demo"},
    )

    payload = response.json()
    pod = payload["pods"][0]

    assert response.status_code == 200
    assert pod["node_name"] == "node-a"
    assert pod["containers"] == [
        {
            "name": "demo-api",
            "restart_count": 6,
            "state": "waiting",
            "reason": "CrashLoopBackOff",
        }
    ]
    assert pod["previous_log_summary"] == "previous crash: database connection refused"
    assert pod["related_resources"] == [{"kind": "Service", "name": "demo-api", "status": "healthy"}]


def test_run_pod_inspection_returns_selected_pod_evidence(client) -> None:
    response = client.post(
        "/api/v1/inspections/pod/run",
        json={"namespace": "demo", "pod_name": "demo-api-7c8f6f7c6b-fh2ns"},
    )

    payload = response.json()

    assert response.status_code == 200
    assert payload["namespace"] == "demo"
    assert payload["pod"]["name"] == "demo-api-7c8f6f7c6b-fh2ns"
    assert payload["pod"]["describe_summary"]
    assert "log_summary" in payload["pod"]
    assert payload["inspection_target"]["resource_scope"] == ["pods"]


def test_run_inspection_dispatches_pod_target(client) -> None:
    response = client.post(
        "/api/v1/inspections/run",
        json={"target_type": "pod", "namespace": "demo", "pod_name": "demo-api-7c8f6f7c6b-fh2ns"},
    )

    payload = response.json()

    assert response.status_code == 200
    assert payload["target_type"] == "pod"
    assert payload["pod_result"]["pod"]["name"] == "demo-api-7c8f6f7c6b-fh2ns"
    assert payload["pod_result"]["inspection_target"]["resource_scope"] == ["pods"]
    assert payload["namespace_result"] is None
    assert payload["cluster_result"] is None


def test_run_namespace_inspection_uses_plural_resource_scope_names(client) -> None:
    response = client.post(
        "/api/v1/inspections/namespace/run",
        json={"namespace": "demo", "label_selector": "app=demo"},
    )

    payload = response.json()

    assert response.status_code == 200
    assert payload["inspection_target"]["resource_scope"] == [
        "pods",
        "services",
        "ingresses",
        "daemonsets",
        "secrets",
    ]


def test_list_pod_inspection_history_returns_latest_runs(client) -> None:
    client.post(
        "/api/v1/inspections/pod/run",
        json={"namespace": "demo", "pod_name": "demo-api-7c8f6f7c6b-fh2ns"},
    )

    response = client.get("/api/v1/inspections/pod/history")
    payload = response.json()

    assert response.status_code == 200
    assert payload[0]["namespace"] == "demo"
    assert payload[0]["pod"]["name"] == "demo-api-7c8f6f7c6b-fh2ns"


def test_run_namespace_batch_inspection_for_requested_namespaces(client) -> None:
    response = client.post(
        "/api/v1/inspections/namespaces/run",
        json={"namespaces": ["demo"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["all_namespaces"] is False
    assert payload["requested_namespaces"] == ["demo"]
    assert payload["results"][0]["summary"]["name"] == "demo"
    assert payload["results"][0]["health_status"] == "warning"
    assert payload["results"][0]["detail_target"]["type"] == "namespace"
    assert payload["results"][0]["detail_target"]["namespace"] == "demo"


def test_namespace_batch_detail_target_can_reload_namespace_evidence(client) -> None:
    batch_response = client.post(
        "/api/v1/inspections/namespaces/run",
        json={"namespaces": ["demo"]},
    )

    assert batch_response.status_code == 200
    detail_target = batch_response.json()["results"][0]["detail_target"]

    detail_response = client.post(
        "/api/v1/inspections/namespace/run",
        json={"namespace": detail_target["namespace"], "label_selector": detail_target.get("label_selector")},
    )

    assert detail_response.status_code == 200
    payload = detail_response.json()
    assert payload["namespace"] == "demo"
    assert payload["pods"]
    assert payload["evidence_bundles"]
    assert "log_hits" in payload["pods"][0]
    assert "events" in payload["pods"][0]
    assert "related_resources" in payload["pods"][0]


def test_run_namespace_batch_inspection_for_all_namespaces(client) -> None:
    client.app.state.provider.list_namespaces = lambda: {
        "executed_at": "2026-07-13T00:00:00Z",
        "namespaces": [
            {
                "name": "prod",
                "status": "warning",
                "pod_count": 9,
                "abnormal_pod_count": 7,
                "last_inspected_at": "2026-07-12T00:00:00Z",
                "labels": {"team": "prod"},
                "abnormal_categories": ["pod_status"],
            },
            {
                "name": "demo",
                "status": "healthy",
                "pod_count": 8,
                "abnormal_pod_count": 0,
                "last_inspected_at": "2026-07-12T00:00:00Z",
                "labels": {"team": "demo"},
                "abnormal_categories": [],
            },
        ],
    }

    def run_namespace(namespace: str, label_selector: str | None) -> dict:
        if namespace == "prod":
            pods = []
            health_status = "healthy"
        else:
            pods = [
                {
                    "name": "demo-api-1",
                    "status": "CrashLoopBackOff",
                    "node_name": "node-a",
                    "restarts": 4,
                    "containers": [{"name": "demo-api", "restart_count": 4, "state": "waiting", "reason": "CrashLoopBackOff"}],
                    "events": [],
                    "describe_summary": "demo failed",
                    "log_summary": "connection refused",
                    "previous_log_summary": None,
                    "resource_usage": {},
                    "related_resources": [],
                }
            ]
            health_status = "warning"
        return {
            "inspection_target": {
                "type": "namespace",
                "namespace": namespace,
                "label_selector": label_selector,
                "saved_target_id": None,
                "template_id": None,
                "resource_scope": ["pods", "services", "ingresses", "daemonsets", "secrets"],
            },
            "namespace": namespace,
            "label_selector": label_selector,
            "health_status": health_status,
            "executed_at": "2026-07-13T00:00:00Z",
            "evidence_bundles": [],
            "pods": pods,
            "services": [],
            "ingresses": [],
            "tls_secrets": [],
            "daemonsets": [],
        }

    client.app.state.provider.run_namespace_inspection = run_namespace

    response = client.post(
        "/api/v1/inspections/namespaces/run",
        json={"all_namespaces": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["all_namespaces"] is True
    assert payload["requested_namespaces"] == ["demo", "prod"]
    assert [item["summary"]["name"] for item in payload["results"]] == ["demo", "prod"]
    result_by_name = {item["summary"]["name"]: item for item in payload["results"]}
    assert result_by_name["demo"]["summary"]["status"] == "warning"
    assert result_by_name["demo"]["summary"]["pod_count"] == 1
    assert result_by_name["demo"]["summary"]["abnormal_pod_count"] == 1
    assert result_by_name["demo"]["summary"]["last_inspected_at"] == "2026-07-13T00:00:00Z"
    assert result_by_name["demo"]["summary"]["labels"] == {"team": "demo"}
    assert result_by_name["demo"]["summary"]["abnormal_categories"] == ["pod_status", "container_status", "log_keyword"]
    assert result_by_name["prod"]["summary"]["status"] == "healthy"
    assert result_by_name["prod"]["summary"]["pod_count"] == 0
    assert result_by_name["prod"]["summary"]["abnormal_pod_count"] == 0


def test_run_namespace_batch_inspection_uses_current_inspection_for_summary(client) -> None:
    client.app.state.provider.list_namespaces = _namespace_batch_discovery_summary
    client.app.state.provider.run_namespace_inspection = lambda namespace, label_selector: _namespace_batch_inspection_payload(
        health_status="warning",
        pods=[
            _inspected_pod(
                status="CrashLoopBackOff",
                containers=[{"name": "demo-api", "restart_count": 2, "state": "waiting", "reason": "CrashLoopBackOff"}],
                log_summary="connection refused",
            )
        ],
    )

    response = client.post(
        "/api/v1/inspections/namespaces/run",
        json={"namespaces": ["demo"]},
    )

    assert response.status_code == 200
    payload = response.json()
    summary = payload["results"][0]["summary"]
    assert summary["status"] == "warning"
    assert summary["pod_count"] == 1
    assert summary["abnormal_pod_count"] == 1
    assert summary["last_inspected_at"] == "2026-07-13T08:00:00Z"
    assert summary["labels"] == {"team": "platform"}
    assert summary["abnormal_categories"] == ["pod_status", "container_status", "log_keyword"]


def test_run_namespace_batch_inspection_returns_empty_categories_for_healthy_namespace(client) -> None:
    client.app.state.provider.list_namespaces = _namespace_batch_discovery_summary
    client.app.state.provider.run_namespace_inspection = lambda namespace, label_selector: _namespace_batch_inspection_payload(
        health_status="healthy",
        pods=[_inspected_pod()],
    )

    response = client.post(
        "/api/v1/inspections/namespaces/run",
        json={"namespaces": ["demo"]},
    )

    assert response.status_code == 200
    summary = response.json()["results"][0]["summary"]
    assert summary["status"] == "healthy"
    assert summary["abnormal_pod_count"] == 0
    assert summary["abnormal_categories"] == []


def test_run_namespace_batch_inspection_derives_all_abnormal_categories_in_stable_order(client) -> None:
    client.app.state.provider.list_namespaces = _namespace_batch_discovery_summary
    client.app.state.provider.run_namespace_inspection = lambda namespace, label_selector: _namespace_batch_inspection_payload(
        health_status="warning",
        pods=[
            _inspected_pod(
                status="CrashLoopBackOff",
                containers=[{"name": "demo-api", "restart_count": 3, "state": "waiting", "reason": "ImagePullBackOff"}],
                events=["Back-off pulling image"],
                log_summary="connection refused",
                related_resources=[{"kind": "Service", "name": "demo-api", "status": "degraded"}],
            )
        ],
    )

    response = client.post(
        "/api/v1/inspections/namespaces/run",
        json={"namespaces": ["demo"]},
    )

    assert response.status_code == 200
    summary = response.json()["results"][0]["summary"]
    assert summary["abnormal_categories"] == [
        "pod_status",
        "container_status",
        "event",
        "log_keyword",
        "related_object",
    ]


def test_run_namespace_batch_inspection_derives_related_object_from_namespace_objects(client) -> None:
    client.app.state.provider.list_namespaces = _namespace_batch_discovery_summary
    client.app.state.provider.run_namespace_inspection = lambda namespace, label_selector: _namespace_batch_inspection_payload(
        health_status="warning",
        pods=[_inspected_pod()],
        services=[{"name": "demo-api", "status": "degraded", "summary": "selector mismatch"}],
    )

    response = client.post(
        "/api/v1/inspections/namespaces/run",
        json={"namespaces": ["demo"]},
    )

    assert response.status_code == 200
    summary = response.json()["results"][0]["summary"]
    result = response.json()["results"][0]
    assert summary["status"] == "warning"
    assert result["health_status"] == "warning"
    assert summary["abnormal_categories"] == ["related_object"]


def test_run_namespace_batch_inspection_ignores_whitelisted_log_hits_in_summary(client) -> None:
    client.app.state.provider.list_namespaces = _namespace_batch_discovery_summary
    client.app.state.provider.run_namespace_inspection = lambda namespace, label_selector: _namespace_batch_inspection_payload(
        health_status="healthy",
        pods=[
            _inspected_pod(
                log_hits=[
                    {
                        "keyword": "connection refused",
                        "category": "runtime",
                        "severity": "warning",
                        "source": "current_log",
                        "matched_text": "connection refused",
                        "container_name": "demo-api",
                        "whitelisted": True,
                        "whitelist_rule_id": 1,
                    }
                ]
            )
        ],
    )

    response = client.post(
        "/api/v1/inspections/namespaces/run",
        json={"namespaces": ["demo"]},
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["summary"]["abnormal_categories"] == []
    assert result["health_status"] == "healthy"


def test_run_namespace_batch_inspection_keeps_log_keyword_when_non_whitelisted_hit_exists(client) -> None:
    client.app.state.provider.list_namespaces = _namespace_batch_discovery_summary
    client.app.state.provider.run_namespace_inspection = lambda namespace, label_selector: _namespace_batch_inspection_payload(
        health_status="warning",
        pods=[
            _inspected_pod(log_summary="mixed log hits")
        ],
    )

    with patch(
        "app.services.inspection_service.match_log_text",
        return_value=[
            KeywordHit(
                keyword="known issue",
                category="runtime",
                severity="warning",
                source="current_log",
                matched_text="known issue",
                container_name="demo-api",
                whitelisted=True,
                whitelist_rule_id=1,
            ),
            KeywordHit(
                keyword="new error",
                category="runtime",
                severity="warning",
                source="current_log",
                matched_text="new error",
                container_name="demo-api",
                whitelisted=False,
                whitelist_rule_id=None,
            ),
        ],
    ):
        response = client.post(
            "/api/v1/inspections/namespaces/run",
            json={"namespaces": ["demo"]},
        )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["summary"]["abnormal_categories"] == ["log_keyword"]
    assert result["health_status"] == "warning"


def test_run_namespace_inspection_keeps_whitelisted_log_hits_in_detail_response(client) -> None:
    client.app.state.provider.run_namespace_inspection = lambda namespace, label_selector: _namespace_batch_inspection_payload(
        health_status="healthy",
        pods=[
            _inspected_pod(log_summary="connection refused")
        ],
    )

    with patch(
        "app.services.inspection_service.match_log_text",
        return_value=[
            KeywordHit(
                keyword="connection refused",
                category="runtime",
                severity="warning",
                source="current_log",
                matched_text="connection refused",
                container_name="demo-api",
                whitelisted=True,
                whitelist_rule_id=1,
            )
        ],
    ):
        response = client.post(
            "/api/v1/inspections/namespace/run",
            json={"namespace": "demo", "label_selector": None},
        )

    assert response.status_code == 200
    log_hits = response.json()["pods"][0]["log_hits"]
    assert len(log_hits) == 1
    assert log_hits[0]["whitelisted"] is True
    assert log_hits[0]["keyword"] == "connection refused"


def test_run_namespace_batch_inspection_isolates_single_namespace_failure(client) -> None:
    client.app.state.provider.list_namespaces = lambda: {
        "executed_at": "2026-07-13T00:00:00Z",
        "namespaces": [
            {
                "name": "demo",
                "status": "warning",
                "pod_count": 1,
                "abnormal_pod_count": 1,
                "last_inspected_at": "2026-07-13T00:00:00Z",
                "labels": {},
                "abnormal_categories": ["pod_status"],
            },
            {
                "name": "broken",
                "status": "error",
                "pod_count": 0,
                "abnormal_pod_count": 0,
                "last_inspected_at": "2026-07-13T00:00:00Z",
                "labels": {},
                "abnormal_categories": [],
            },
            {
                "name": "prod",
                "status": "healthy",
                "pod_count": 1,
                "abnormal_pod_count": 0,
                "last_inspected_at": "2026-07-13T00:00:00Z",
                "labels": {},
                "abnormal_categories": [],
            },
        ],
    }

    def run_namespace(namespace: str, label_selector: str | None) -> dict:
        if namespace == "broken":
            raise RuntimeError("provider failed")
        return {
            "inspection_target": {
                "type": "namespace",
                "namespace": namespace,
                "label_selector": label_selector,
                "saved_target_id": None,
                "template_id": None,
                "resource_scope": ["pods", "services", "ingresses", "daemonsets", "secrets"],
            },
            "namespace": namespace,
            "label_selector": label_selector,
            "health_status": "healthy" if namespace == "prod" else "warning",
            "executed_at": "2026-07-13T00:00:00Z",
            "evidence_bundles": [],
            "pods": [],
            "services": [],
            "ingresses": [],
            "tls_secrets": [],
            "daemonsets": [],
        }

    client.app.state.provider.run_namespace_inspection = run_namespace

    response = client.post(
        "/api/v1/inspections/namespaces/run",
        json={"namespaces": ["demo", "broken", "prod"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["summary"]["name"] for item in payload["results"]] == ["broken", "demo", "prod"]
    result_by_name = {item["summary"]["name"]: item for item in payload["results"]}
    assert result_by_name["demo"]["health_status"] == "warning"
    assert result_by_name["prod"]["health_status"] == "healthy"
    assert result_by_name["broken"]["health_status"] == "error"
    assert result_by_name["broken"]["summary"]["status"] == "error"


def test_run_namespace_batch_inspection_sorts_explicit_namespaces_by_name(client) -> None:
    client.app.state.provider.list_namespaces = lambda: {
        "executed_at": "2026-07-13T00:00:00Z",
        "namespaces": [
            {
                "name": "prod",
                "status": "healthy",
                "pod_count": 1,
                "abnormal_pod_count": 0,
                "last_inspected_at": "2026-07-13T00:00:00Z",
                "labels": {},
                "abnormal_categories": [],
            },
            {
                "name": "demo",
                "status": "warning",
                "pod_count": 1,
                "abnormal_pod_count": 1,
                "last_inspected_at": "2026-07-13T00:00:00Z",
                "labels": {},
                "abnormal_categories": ["pod_status"],
            },
            {
                "name": "alpha",
                "status": "healthy",
                "pod_count": 1,
                "abnormal_pod_count": 0,
                "last_inspected_at": "2026-07-13T00:00:00Z",
                "labels": {},
                "abnormal_categories": [],
            },
        ],
    }
    client.app.state.provider.run_namespace_inspection = lambda namespace, label_selector: {
        "inspection_target": {
            "type": "namespace",
            "namespace": namespace,
            "label_selector": label_selector,
            "saved_target_id": None,
            "template_id": None,
            "resource_scope": ["pods", "services", "ingresses", "daemonsets", "secrets"],
        },
        "namespace": namespace,
        "label_selector": label_selector,
        "health_status": "healthy",
        "executed_at": "2026-07-13T00:00:00Z",
        "evidence_bundles": [],
        "pods": [],
        "services": [],
        "ingresses": [],
        "tls_secrets": [],
        "daemonsets": [],
    }

    response = client.post(
        "/api/v1/inspections/namespaces/run",
        json={"namespaces": ["prod", "alpha", "demo"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requested_namespaces"] == ["prod", "alpha", "demo"]
    assert [item["summary"]["name"] for item in payload["results"]] == ["alpha", "demo", "prod"]


def test_mock_provider_pod_inspection_does_not_depend_on_namespace_inspection() -> None:
    from app.providers.mock_provider import MockInspectionProvider

    provider = MockInspectionProvider()
    provider.run_namespace_inspection = lambda namespace, label_selector: (_ for _ in ()).throw(
        AssertionError("run_namespace_inspection should not be used for single pod inspection")
    )

    result = provider.run_pod_inspection("demo", "demo-api-7c8f6f7c6b-fh2ns")

    assert result["pod"]["name"] == "demo-api-7c8f6f7c6b-fh2ns"
