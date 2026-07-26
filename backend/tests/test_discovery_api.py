from unittest.mock import Mock

from app.models import InspectionRecord, InspectionRun


def test_discover_namespaces_returns_namespace_summaries(client) -> None:
    response = client.get("/api/v1/discovery/namespaces")

    assert response.status_code == 200
    payload = response.json()
    assert "executed_at" in payload
    assert payload["namespaces"][0]["name"] == "demo"
    assert payload["namespaces"][0]["status"] == "warning"
    assert payload["namespaces"][0]["pod_count"] == 1
    assert payload["namespaces"][0]["abnormal_pod_count"] == 1


def test_discover_namespaces_returns_empty_list(client) -> None:
    client.app.state.provider.list_namespaces = lambda: {
        "executed_at": "2026-07-12T00:00:00Z",
        "namespaces": [],
    }

    response = client.get("/api/v1/discovery/namespaces")

    assert response.status_code == 200
    payload = response.json()
    assert payload["executed_at"] == "2026-07-12T00:00:00Z"
    assert payload["namespaces"] == []


def test_discover_namespaces_sorts_by_name(client) -> None:
    client.app.state.provider.list_namespaces = lambda: {
        "executed_at": "2026-07-12T00:00:00Z",
        "namespaces": [
            {
                "name": "prod",
                "status": "healthy",
                "pod_count": 2,
                "abnormal_pod_count": 0,
                "last_inspected_at": "2026-07-12T00:00:00Z",
                "labels": {},
                "abnormal_categories": [],
            },
            {
                "name": "demo",
                "status": "warning",
                "pod_count": 3,
                "abnormal_pod_count": 1,
                "last_inspected_at": "2026-07-12T00:00:00Z",
                "labels": {},
                "abnormal_categories": ["pod_status"],
            },
        ],
    }

    response = client.get("/api/v1/discovery/namespaces")

    assert response.status_code == 200
    payload = response.json()
    assert [item["name"] for item in payload["namespaces"]] == ["demo", "prod"]


def test_discover_namespace_labels_returns_selector_candidates(client) -> None:
    client.app.state.provider.list_namespace_labels = lambda namespace: {
        "executed_at": "2026-07-21T00:00:00Z",
        "labels": [
            {
                "key": "app.kubernetes.io/instance",
                "values": ["worker"],
                "selector": "app.kubernetes.io/instance=worker",
                "pod_count": 3,
            }
        ],
    }

    response = client.get("/api/v1/discovery/namespaces/platform/labels")

    assert response.status_code == 200
    payload = response.json()
    assert payload["namespace"] == "platform"
    assert payload["labels"][0]["key"] == "app.kubernetes.io/instance"
    assert payload["labels"][0]["selector"] == "app.kubernetes.io/instance=worker"
    assert payload["labels"][0]["pod_count"] == 3


def test_discover_namespace_labels_returns_empty_list(client) -> None:
    client.app.state.provider.list_namespace_labels = lambda namespace: {
        "executed_at": "2026-07-21T00:00:00Z",
        "labels": [],
    }

    response = client.get("/api/v1/discovery/namespaces/demo/labels")

    assert response.status_code == 200
    payload = response.json()
    assert payload["namespace"] == "demo"
    assert payload["labels"] == []


def test_discover_namespace_labels_returns_provider_error(client) -> None:
    client.app.state.provider.list_namespace_labels = lambda namespace: (_ for _ in ()).throw(
        RuntimeError(f"无法读取名称空间 {namespace} 的 Pod 标签：Forbidden")
    )

    response = client.get("/api/v1/discovery/namespaces/demo/labels")

    assert response.status_code == 502
    assert response.json()["code"] == "UPSTREAM_UNAVAILABLE"
    assert response.json()["message"] == "上游服务暂时不可用"
    assert response.json()["details"] == {}


def test_discover_namespace_pods_is_lightweight_and_has_no_run_side_effects(
    client,
) -> None:
    provider = client.app.state.provider
    provider.list_namespace_pods = Mock(
        return_value={
            "namespace": "demo",
            "label_selector": "app=api",
            "executed_at": "2026-07-26T00:00:00Z",
            "pod_count": 2,
            "pods": [
                {"name": "demo-api-2", "labels": {"app": "api"}},
                {"name": "demo-api-1", "labels": {"app": "api"}},
            ],
        }
    )
    provider.run_namespace_inspection = Mock(
        side_effect=AssertionError("lightweight discovery must not inspect")
    )
    provider.collect_pod_log_samples = Mock(
        side_effect=AssertionError("lightweight discovery must not read logs")
    )
    with client.app.state.session_factory() as session:
        before = (
            session.query(InspectionRecord).count(),
            session.query(InspectionRun).count(),
        )

    response = client.get(
        "/api/v1/discovery/namespaces/demo/pods",
        params={"label_selector": "app=api"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "namespace": "demo",
        "label_selector": "app=api",
        "executed_at": "2026-07-26T00:00:00Z",
        "pod_count": 2,
        "pods": [
            {"name": "demo-api-1", "labels": {"app": "api"}},
            {"name": "demo-api-2", "labels": {"app": "api"}},
        ],
    }
    provider.list_namespace_pods.assert_called_once_with("demo", "app=api")
    provider.run_namespace_inspection.assert_not_called()
    provider.collect_pod_log_samples.assert_not_called()
    with client.app.state.session_factory() as session:
        after = (
            session.query(InspectionRecord).count(),
            session.query(InspectionRun).count(),
        )
    assert after == before


def test_discover_namespace_pods_returns_provider_error(client) -> None:
    client.app.state.provider.list_namespace_pods = Mock(
        side_effect=RuntimeError(
            "无法读取名称空间 demo 的 Pod 名单：Forbidden"
        )
    )

    response = client.get("/api/v1/discovery/namespaces/demo/pods")

    assert response.status_code == 502
    assert response.json()["code"] == "UPSTREAM_UNAVAILABLE"
