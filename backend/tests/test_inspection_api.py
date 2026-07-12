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


def test_mock_provider_pod_inspection_does_not_depend_on_namespace_inspection() -> None:
    from app.providers.mock_provider import MockInspectionProvider

    provider = MockInspectionProvider()
    provider.run_namespace_inspection = lambda namespace, label_selector: (_ for _ in ()).throw(
        AssertionError("run_namespace_inspection should not be used for single pod inspection")
    )

    result = provider.run_pod_inspection("demo", "demo-api-7c8f6f7c6b-fh2ns")

    assert result["pod"]["name"] == "demo-api-7c8f6f7c6b-fh2ns"
