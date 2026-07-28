from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from kubernetes.client.exceptions import ApiException

from app.models import InspectionRecord, SystemSetting
from app.models import InspectionRun as InspectionRunModel
from app.providers.base import LogPodLimitExceededError
from app.providers.kubernetes_provider import KubernetesInspectionProvider
from app.schemas.common import KeywordHit
from app.schemas.inspection import NamespaceInspectionRequest
from app.services import inspection_service


def _v11_issue_payload() -> dict:
    return {
        "id": 1,
        "cluster_id": "default",
        "issue_code": "NODE_NOT_READY",
        "fingerprint": "a" * 64,
        "severity": "critical",
        "status": "open",
        "scope": "node",
        "resource": {"kind": "Node", "name": "node-a"},
        "summary": "Node 未就绪",
        "reason": "Ready=False",
        "suggestion": "检查节点状态",
        "evidence": [],
        "first_seen_at": "2026-07-26T08:00:00Z",
        "last_seen_at": "2026-07-26T08:00:00Z",
        "occurrence_count": 1,
        "source_check": "node.readiness",
    }


def _v11_coverage_payload() -> dict:
    return {
        "check_code": "node.readiness",
        "name": "Node 就绪状态",
        "status": "abnormal",
        "reason": "存在未就绪 Node",
        "checked_objects": 1,
        "duration_ms": 5,
        "issue_count": 1,
    }


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


def _oversized_discovery_summary() -> dict:
    return {
        "executed_at": "2026-07-26T08:00:00Z",
        "namespaces": [
            {
                "name": "demo",
                "status": "warning",
                "pod_count": 201,
                "abnormal_pod_count": 201,
                "last_inspected_at": "2026-07-26T08:00:00Z",
                "labels": {},
                "abnormal_categories": ["pod_status"],
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
    container_log_summaries: dict[str, str] | None = None,
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
        "container_log_summaries": container_log_summaries or {},
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


@pytest.mark.parametrize(
    ("request_body", "expected_include_logs"),
    [
        ({"namespace": "demo"}, True),
        ({"namespace": "demo", "include_logs": True}, True),
        ({"namespace": "demo", "include_logs": False}, False),
    ],
)
def test_namespace_api_forwards_explicit_log_collection_mode(
    client,
    request_body,
    expected_include_logs,
) -> None:
    provider = client.app.state.provider
    provider.list_namespace_pods = Mock(
        return_value={
            "namespace": "demo",
            "label_selector": None,
            "executed_at": "2026-07-26T00:00:00Z",
            "pod_count": 1,
            "pods": [{"name": "demo-api-0", "labels": {}}],
        }
    )
    provider.run_namespace_inspection = Mock(
        return_value=_namespace_batch_inspection_payload()
    )

    response = client.post(
        "/api/v1/inspections/namespace/run",
        json=request_body,
    )

    assert response.status_code == 200
    _, _, kwargs = provider.run_namespace_inspection.mock_calls[0]
    assert kwargs["include_logs"] is expected_include_logs
    assert kwargs["limits"].max_log_pods == 200
    if expected_include_logs:
        provider.list_namespace_pods.assert_called_once_with("demo", None)
    else:
        provider.list_namespace_pods.assert_not_called()


def test_cluster_api_explicit_status_mode_skips_log_preflight(client) -> None:
    provider = client.app.state.provider
    provider.list_namespaces = Mock(
        side_effect=AssertionError("status mode must not estimate log targets")
    )
    provider.run_cluster_inspection = Mock(
        return_value={
            "health_status": "healthy",
            "executed_at": "2026-07-26T00:00:00Z",
            "results": [],
        }
    )

    response = client.post(
        "/api/v1/inspections/cluster/run",
        params={"include_logs": "false"},
    )

    assert response.status_code == 200
    provider.list_namespaces.assert_not_called()
    provider.run_cluster_inspection.assert_called_once_with(
        include_logs=False
    )


def test_all_inspection_endpoints_return_v11_array_fields(client) -> None:
    responses = [
        client.post("/api/v1/inspections/cluster/run"),
        client.post("/api/v1/inspections/namespace/run", json={"namespace": "demo"}),
        client.post("/api/v1/inspections/namespaces/run", json={"namespaces": ["demo"]}),
        client.post(
            "/api/v1/inspections/pod/run",
            json={"namespace": "demo", "pod_name": "demo-api-7c8f6f7c6b-fh2ns"},
        ),
    ]

    for response in responses:
        assert response.status_code == 200
        payload = response.json()
        assert isinstance(payload["issues"], list)
        assert isinstance(payload["coverage"], list)

    nested_response = client.post(
        "/api/v1/inspections/run",
        json={"target_type": "cluster"},
    )
    assert nested_response.status_code == 200
    nested = nested_response.json()
    assert isinstance(nested["cluster_result"]["issues"], list)
    assert isinstance(nested["cluster_result"]["coverage"], list)
    assert "issues" not in nested
    assert "coverage" not in nested


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v1/inspections/cluster/run", None),
        ("/api/v1/inspections/namespace/run", {"namespace": "demo"}),
        ("/api/v1/inspections/run", {"target_type": "cluster"}),
    ],
)
def test_log_inspection_scope_over_200_is_rejected_before_execution(
    client,
    path,
    payload,
):
    provider = client.app.state.provider
    provider.list_namespaces = Mock(return_value=_oversized_discovery_summary())
    provider.list_namespace_pods = Mock(
        return_value={
            "namespace": "demo",
            "label_selector": None,
            "executed_at": "2026-07-26T08:00:00Z",
            "pod_count": 201,
            "pods": [
                {"name": f"demo-{index}", "labels": {}}
                for index in range(201)
            ],
        }
    )
    provider.run_cluster_inspection = Mock(
        side_effect=AssertionError("超限后不应执行集群巡检")
    )
    provider.run_namespace_inspection = Mock(
        side_effect=AssertionError("超限后不应执行名称空间巡检")
    )

    response = client.post(path, json=payload) if payload is not None else client.post(path)

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "INSPECTION_LOG_SCOPE_TOO_LARGE"
    assert "请缩小范围" in body["message"]
    assert body["details"] == {"estimated_pods": 201, "limit": 200}
    provider.run_cluster_inspection.assert_not_called()
    provider.run_namespace_inspection.assert_not_called()
    with client.app.state.session_factory() as session:
        assert session.query(InspectionRecord).count() == 0
        assert session.query(InspectionRunModel).count() == 0


def test_namespace_batch_over_200_uses_status_collection_without_log_gate(
    client,
) -> None:
    provider = client.app.state.provider
    provider.list_namespaces = Mock(
        return_value=_oversized_discovery_summary()
    )
    provider.run_namespace_inspection = Mock(
        return_value=_namespace_batch_inspection_payload()
    )

    response = client.post(
        "/api/v1/inspections/namespaces/run",
        json={"namespaces": ["demo"], "all_namespaces": False},
    )

    assert response.status_code == 200
    provider.run_namespace_inspection.assert_called_once_with(
        "demo",
        None,
        include_logs=False,
    )


def test_configured_log_limit_is_used_by_namespace_preflight(client) -> None:
    with client.app.state.session_factory() as session:
        settings = session.get(SystemSetting, 1)
        settings.inspection_policy = {"max_log_pods": 1}
        session.commit()
    provider = client.app.state.provider
    provider.list_namespace_pods = Mock(
        return_value={
            "namespace": "demo",
            "label_selector": "app=api",
            "executed_at": "2026-07-26T00:00:00Z",
            "pod_count": 2,
            "pods": [
                {"name": "api-0", "labels": {"app": "api"}},
                {"name": "api-1", "labels": {"app": "api"}},
            ],
        }
    )
    provider.run_namespace_inspection = Mock(
        side_effect=AssertionError("over limit must not inspect")
    )

    response = client.post(
        "/api/v1/inspections/namespace/run",
        json={
            "namespace": "demo",
            "label_selector": "app=api",
            "include_logs": True,
        },
    )

    assert response.status_code == 422
    assert response.json()["details"] == {
        "estimated_pods": 2,
        "limit": 1,
    }
    provider.run_namespace_inspection.assert_not_called()


def test_provider_log_limit_race_is_normalized_to_422(client) -> None:
    provider = client.app.state.provider
    provider.list_namespace_pods = Mock(
        return_value={
            "namespace": "demo",
            "label_selector": None,
            "executed_at": "2026-07-26T00:00:00Z",
            "pod_count": 1,
            "pods": [{"name": "api-0", "labels": {}}],
        }
    )
    provider.run_namespace_inspection = Mock(
        side_effect=LogPodLimitExceededError(2, 1)
    )

    response = client.post(
        "/api/v1/inspections/namespace/run",
        json={"namespace": "demo", "include_logs": True},
    )

    assert response.status_code == 422
    assert response.json()["details"] == {
        "estimated_pods": 2,
        "limit": 1,
    }


def test_cluster_dynamic_log_limit_stops_before_any_pod_log_read(
    client,
) -> None:
    with client.app.state.session_factory() as session:
        settings = session.get(SystemSetting, 1)
        settings.inspection_policy = {"max_log_pods": 1}
        session.commit()
    provider = KubernetesInspectionProvider.__new__(
        KubernetesInspectionProvider
    )
    provider.list_namespaces = Mock(
        return_value={
            "executed_at": "2026-07-26T00:00:00Z",
            "namespaces": [
                {
                    "name": "demo",
                    "status": "warning",
                    "pod_count": 2,
                    "abnormal_pod_count": 2,
                    "last_inspected_at": "2026-07-26T00:00:00Z",
                    "labels": {},
                    "abnormal_categories": ["pod_status"],
                }
            ],
        }
    )
    provider.core = SimpleNamespace(
        read_namespaced_pod_log=Mock()
    )
    client.app.state.provider = provider

    response = client.post(
        "/api/v1/inspections/cluster/run",
        params={"include_logs": "true"},
    )

    assert response.status_code == 422
    assert response.json()["details"] == {
        "estimated_pods": 2,
        "limit": 1,
    }
    provider.core.read_namespaced_pod_log.assert_not_called()


def test_namespace_label_scope_over_200_is_rejected_before_execution(client):
    provider = client.app.state.provider
    provider.list_namespace_pods = Mock(
        return_value={
            "namespace": "demo",
            "label_selector": "app=large",
            "executed_at": "2026-07-26T08:00:00Z",
            "pod_count": 201,
            "pods": [
                {"name": f"demo-{index}", "labels": {"app": "large"}}
                for index in range(201)
            ],
        }
    )
    provider.run_namespace_inspection = Mock(
        side_effect=AssertionError("超限后不应执行名称空间巡检")
    )

    response = client.post(
        "/api/v1/inspections/namespace/run",
        json={"namespace": "demo", "label_selector": "app=large"},
    )

    assert response.status_code == 422
    assert "请缩小范围" in response.json()["message"]
    provider.run_namespace_inspection.assert_not_called()


def test_direct_service_call_rejects_oversized_scope_before_execution(client):
    provider = client.app.state.provider
    provider.list_namespace_pods = Mock(
        return_value={
            "namespace": "demo",
            "label_selector": None,
            "executed_at": "2026-07-26T08:00:00Z",
            "pod_count": 201,
            "pods": [
                {"name": f"demo-{index}", "labels": {}}
                for index in range(201)
            ],
        }
    )
    provider.run_namespace_inspection = Mock(
        side_effect=AssertionError("超限后不应执行名称空间巡检")
    )
    with client.app.state.session_factory() as session:
        with pytest.raises(
            inspection_service.LogInspectionScopeTooLargeError,
            match="请缩小范围",
        ):
            inspection_service.run_namespace_inspection(
                session,
                provider,
                NamespaceInspectionRequest(namespace="demo"),
            )
        assert session.query(InspectionRecord).count() == 0
        assert session.query(InspectionRunModel).count() == 0
    provider.run_namespace_inspection.assert_not_called()


def test_public_inspection_results_redact_nested_secrets_and_keep_safe_summary(client):
    sensitive_text = "\n".join(
        [
            "password=plain-password",
            "passwd=passwd-value",
            "token=token-value",
            "secret=secret-value",
            "api-key=api-key-value",
            "Bearer bearer-value",
            "https://open.feishu.cn/open-apis/bot/v2/hook/webhook-value",
            "-----BEGIN PRIVATE KEY-----private-material-----END PRIVATE KEY-----",
            "ERROR upstream unavailable",
        ]
    )

    def sensitive_result(namespace: str, pod_name: str) -> dict:
        pod = _inspected_pod(
            status="CrashLoopBackOff",
            events=[sensitive_text],
            log_summary=sensitive_text,
            container_log_summaries={"demo-api": sensitive_text},
        )
        pod["name"] = pod_name
        pod["describe_summary"] = sensitive_text
        pod["previous_log_summary"] = sensitive_text
        return {
            "inspection_target": {
                "type": "pod",
                "namespace": namespace,
                "pod_name": pod_name,
                "resource_scope": ["pods"],
            },
            "namespace": namespace,
            "health_status": "warning",
            "executed_at": "2026-07-26T08:00:00Z",
            "pod": pod,
            "evidence_bundle": None,
        }

    def sensitive_namespace_result(
        namespace: str,
        label_selector: str | None,
        *,
        include_logs: bool = True,
        limits=None,
    ) -> dict:
        pod_result = sensitive_result(namespace, "sensitive-pod")
        pod = pod_result["pod"]
        return {
            "inspection_target": {
                "type": "namespace",
                "namespace": namespace,
                "label_selector": label_selector,
                "resource_scope": ["pods", "services", "ingresses", "daemonsets", "secrets"],
            },
            "namespace": namespace,
            "label_selector": label_selector,
            "health_status": sensitive_text,
            "executed_at": "2026-07-26T08:00:00Z",
            "evidence_bundles": [],
            "pods": [pod],
            "services": [],
            "ingresses": [],
            "tls_secrets": [],
            "daemonsets": [],
        }

    client.app.state.provider.run_cluster_inspection = lambda *, include_logs=True: {
        "health_status": "warning",
        "executed_at": "2026-07-26T08:00:00Z",
        "results": [
            {
                "component": "api",
                "namespace": "demo",
                "node": "node-a",
                "status": "degraded",
                "describe_summary": sensitive_text,
                "log_summary": sensitive_text,
            }
        ],
    }
    client.app.state.provider.run_namespace_inspection = sensitive_namespace_result
    client.app.state.provider.run_pod_inspection = sensitive_result
    responses = [
        client.post("/api/v1/inspections/cluster/run"),
        client.post(
            "/api/v1/inspections/namespace/run",
            json={"namespace": "demo"},
        ),
        client.post(
            "/api/v1/inspections/namespaces/run",
            json={"namespaces": ["demo"], "all_namespaces": False},
        ),
        client.post(
            "/api/v1/inspections/pod/run",
            json={"namespace": "demo", "pod_name": "sensitive-pod"},
        ),
        client.post(
            "/api/v1/inspections/run",
            json={
                "target_type": "pod",
                "namespace": "demo",
                "pod_name": "sensitive-pod",
            },
        ),
    ]

    forbidden = {
        "plain-password",
        "passwd-value",
        "token-value",
        "secret-value",
        "api-key-value",
        "bearer-value",
        "webhook-value",
        "private-material",
    }
    for response in responses:
        assert response.status_code == 200
        serialized = str(response.json())
        assert all(secret not in serialized for secret in forbidden)
        assert "ERROR upstream unavailable" in serialized

    public = inspection_service.sanitize_inspection_response(
        {"container_log_summaries": {"demo-api": sensitive_text}}
    )
    assert "container_log_summaries" in public
    assert "ERROR upstream unavailable" in public["container_log_summaries"]["demo-api"]
    assert all(
        secret not in str(public)
        for secret in forbidden
    )


def test_cluster_response_model_does_not_filter_non_empty_v11_fields(client) -> None:
    result = {
        "health_status": "critical",
        "executed_at": "2026-07-26T08:00:00Z",
        "results": [],
        "issues": [_v11_issue_payload()],
        "coverage": [_v11_coverage_payload()],
    }

    with patch(
        "app.api.routes.inspections.inspection_service.run_cluster_inspection",
        return_value=result,
    ):
        response = client.post("/api/v1/inspections/cluster/run")

    assert response.status_code == 200
    payload = response.json()
    assert payload["issues"][0]["issue_code"] == "NODE_NOT_READY"
    assert payload["coverage"][0]["check_code"] == "node.readiness"


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


def test_mock_pod_inspection_uses_shared_health_semantics(client) -> None:
    client.app.state.provider.run_pod_inspection = lambda namespace, pod_name: {
        "inspection_target": {"type": "pod", "namespace": namespace, "pod_name": pod_name, "resource_scope": ["pods"]},
        "namespace": namespace,
        "health_status": "healthy",
        "executed_at": "2026-07-17T00:00:00Z",
        "pod": {
            "name": pod_name,
            "status": "Succeeded",
            "node_name": "node-a",
            "restarts": 0,
            "containers": [{"name": "worker", "restart_count": 0, "state": "terminated", "reason": "Completed"}],
            "events": [],
            "describe_summary": "completed",
            "log_summary": None,
            "previous_log_summary": None,
            "resource_usage": {},
            "related_resources": [],
        },
    }

    response = client.post("/api/v1/inspections/pod/run", json={"namespace": "demo", "pod_name": "safeapi-migrate"})

    assert response.status_code == 200
    assert response.json()["health_status"] == "healthy"


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

    def run_namespace(
        namespace: str,
        label_selector: str | None,
        *,
        include_logs: bool = True,
        limits=None,
    ) -> dict:
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
    client.app.state.provider.run_namespace_inspection = lambda namespace, label_selector, *, include_logs=True, limits=None: _namespace_batch_inspection_payload(
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
    client.app.state.provider.run_namespace_inspection = lambda namespace, label_selector, *, include_logs=True, limits=None: _namespace_batch_inspection_payload(
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


def test_run_namespace_batch_inspection_treats_succeeded_completed_pod_as_healthy(client) -> None:
    client.app.state.provider.list_namespaces = _namespace_batch_discovery_summary
    client.app.state.provider.run_namespace_inspection = lambda namespace, label_selector, *, include_logs=True, limits=None: _namespace_batch_inspection_payload(
        health_status="healthy",
        pods=[
            _inspected_pod(
                status="Succeeded",
                containers=[{"name": "safeapi-migrate", "restart_count": 0, "state": "terminated", "reason": "Completed"}],
            )
        ],
    )

    response = client.post("/api/v1/inspections/namespaces/run", json={"namespaces": ["demo"]})

    assert response.status_code == 200
    summary = response.json()["results"][0]["summary"]
    assert summary["abnormal_pod_count"] == 0
    assert summary["abnormal_categories"] == []


def test_namespace_inspection_keeps_completed_pod_evidence(client) -> None:
    client.app.state.provider.run_namespace_inspection = lambda namespace, label_selector, *, include_logs=True, limits=None: _namespace_batch_inspection_payload(
        health_status="healthy",
        pods=[
            _inspected_pod(
                status="Succeeded",
                containers=[{"name": "safeapi-migrate", "restart_count": 0, "state": "terminated", "reason": "Completed"}],
                events=["Completed migration"],
            )
        ],
    )

    response = client.post("/api/v1/inspections/namespace/run", json={"namespace": "demo"})

    assert response.status_code == 200
    pod = response.json()["pods"][0]
    assert pod["status"] == "Succeeded"
    assert pod["describe_summary"] == "demo summary"
    assert pod["events"] == ["Completed migration"]
    assert "log_hits" in pod


def test_run_namespace_batch_inspection_derives_all_abnormal_categories_in_stable_order(client) -> None:
    client.app.state.provider.list_namespaces = _namespace_batch_discovery_summary
    client.app.state.provider.run_namespace_inspection = lambda namespace, label_selector, *, include_logs=True, limits=None: _namespace_batch_inspection_payload(
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
    client.app.state.provider.run_namespace_inspection = lambda namespace, label_selector, *, include_logs=True, limits=None: _namespace_batch_inspection_payload(
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
    client.app.state.provider.run_namespace_inspection = lambda namespace, label_selector, *, include_logs=True, limits=None: _namespace_batch_inspection_payload(
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
    client.app.state.provider.run_namespace_inspection = lambda namespace, label_selector, *, include_logs=True, limits=None: _namespace_batch_inspection_payload(
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


def test_run_namespace_inspection_hides_whitelisted_log_hits_in_detail_response(client) -> None:
    client.app.state.provider.run_namespace_inspection = lambda namespace, label_selector, *, include_logs=True, limits=None: _namespace_batch_inspection_payload(
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
    assert log_hits == []


def test_run_namespace_inspection_matches_keywords_for_every_container(client) -> None:
    client.app.state.provider.run_namespace_inspection = lambda namespace, label_selector, *, include_logs=True, limits=None: _namespace_batch_inspection_payload(
        health_status="healthy",
        pods=[
            _inspected_pod(
                containers=[
                    {"name": "demo-api", "restart_count": 0, "state": "running", "reason": None},
                    {"name": "sidecar", "restart_count": 0, "state": "running", "reason": None},
                ],
                log_summary="[demo-api]\nconnection refused\n[sidecar]\ntimeout",
                container_log_summaries={
                    "demo-api": "connection refused",
                    "sidecar": "timeout",
                },
            )
        ],
    )

    def match_by_container(**kwargs):
        return [
            KeywordHit(
                keyword=kwargs["log_text"],
                category="runtime",
                severity="warning",
                source="log_summary",
                matched_text=kwargs["log_text"],
                container_name=kwargs["container_name"],
                whitelisted=False,
                whitelist_rule_id=None,
            )
        ]

    with patch("app.services.inspection_service.match_log_text", side_effect=match_by_container) as matcher:
        response = client.post(
            "/api/v1/inspections/namespace/run",
            json={"namespace": "demo", "label_selector": None},
        )

    assert response.status_code == 200
    assert [call.kwargs["container_name"] for call in matcher.mock_calls] == ["demo-api", "sidecar"]
    log_hits = response.json()["pods"][0]["log_hits"]
    assert [hit["container_name"] for hit in log_hits] == ["demo-api", "sidecar"]
    assert [hit["matched_text"] for hit in log_hits] == ["connection refused", "timeout"]


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

    def run_namespace(
        namespace: str,
        label_selector: str | None,
        *,
        include_logs: bool = True,
        limits=None,
    ) -> dict:
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
    client.app.state.provider.run_namespace_inspection = lambda namespace, label_selector, *, include_logs=True, limits=None: {
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
    provider.run_namespace_inspection = lambda namespace, label_selector, *, include_logs=True, limits=None: (_ for _ in ()).throw(
        AssertionError("run_namespace_inspection should not be used for single pod inspection")
    )

    result = provider.run_pod_inspection("demo", "demo-api-7c8f6f7c6b-fh2ns")

    assert result["pod"]["name"] == "demo-api-7c8f6f7c6b-fh2ns"


def test_kubernetes_rbac_failure_returns_actionable_api_error(client) -> None:
    client.app.state.provider.run_namespace_inspection = (
        lambda namespace, label_selector, *, include_logs=True, limits=None: (
            _ for _ in ()
        ).throw(ApiException(status=403, reason="Forbidden"))
    )

    response = client.post(
        "/api/v1/inspections/namespace/run",
        json={"namespace": "demo", "include_logs": False},
    )

    assert response.status_code == 503
    assert response.json()["code"] == "KUBERNETES_RBAC_FORBIDDEN"
    assert "ServiceAccount" in response.json()["message"]
    assert "HTTP response headers" not in response.text
