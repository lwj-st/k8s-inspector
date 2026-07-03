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
