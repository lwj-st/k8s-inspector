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
    assert response.json()["detail"] == "无法读取名称空间 demo 的 Pod 标签：Forbidden"
