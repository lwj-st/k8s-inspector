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
