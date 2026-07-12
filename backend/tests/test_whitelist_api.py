def test_create_and_list_whitelist(client) -> None:
    payload = {
        "namespace": "demo",
        "label_selector": "app=demo",
        "keyword": "connection refused",
        "enabled": True,
        "note": "known harmless in warmup",
    }

    create_response = client.post("/api/v1/whitelists", json=payload)
    list_response = client.get("/api/v1/whitelists")

    assert create_response.status_code == 201
    assert list_response.status_code == 200
    assert list_response.json()[0]["keyword"] == "connection refused"


def test_create_and_list_keywords(client) -> None:
    payload = {
        "keyword": "timeout",
        "category": "network",
        "severity": "warning",
        "description": "downstream request timeout",
        "enabled": True,
    }

    create_response = client.post("/api/v1/keywords", json=payload)
    list_response = client.get("/api/v1/keywords")

    assert create_response.status_code == 201
    assert list_response.status_code == 200
    created = create_response.json()
    assert created["keyword"] == "timeout"
    assert any(item["keyword"] == "timeout" for item in list_response.json())


def test_create_keyword_rejects_invalid_severity(client) -> None:
    response = client.post(
        "/api/v1/keywords",
        json={
            "keyword": "oom",
            "category": "runtime",
            "severity": "fatal",
            "description": "invalid severity",
            "enabled": True,
        },
    )

    assert response.status_code == 422


def test_keyword_enable_disable(client) -> None:
    create_response = client.post(
        "/api/v1/keywords",
        json={
            "keyword": "timeout",
            "category": "network",
            "severity": "warning",
            "description": "downstream request timeout",
            "enabled": True,
        },
    )
    keyword_id = create_response.json()["id"]

    disable_response = client.post(f"/api/v1/keywords/{keyword_id}/disable")
    enable_response = client.post(f"/api/v1/keywords/{keyword_id}/enable")

    assert disable_response.status_code == 200
    assert disable_response.json()["enabled"] is False
    assert enable_response.status_code == 200
    assert enable_response.json()["enabled"] is True


def test_ignore_log_hit_creates_whitelist_rule(client) -> None:
    response = client.post(
        "/api/v1/whitelists/ignore",
        json={
            "namespace": "demo",
            "label_selector": "app=demo",
            "keyword": "connection refused",
            "pod_name_pattern": "demo-api",
            "container_name": "demo-api",
            "note": "ignored from inspection result",
        },
    )

    payload = response.json()
    list_response = client.get("/api/v1/whitelists")

    assert response.status_code == 201
    assert payload["keyword"] == "connection refused"
    assert payload["pod_name_pattern"] == "demo-api"
    assert payload["container_name"] == "demo-api"
    assert list_response.json()[0]["keyword"] == "connection refused"


def test_whitelist_enable_disable(client) -> None:
    create_response = client.post(
        "/api/v1/whitelists",
        json={
            "namespace": "demo",
            "label_selector": "app=demo",
            "keyword": "connection refused",
            "pod_name_pattern": "demo-api-*",
            "container_name": "demo-api",
            "enabled": True,
            "note": "known harmless in warmup",
        },
    )
    whitelist_id = create_response.json()["id"]

    disable_response = client.post(f"/api/v1/whitelists/{whitelist_id}/disable")
    enable_response = client.post(f"/api/v1/whitelists/{whitelist_id}/enable")

    assert disable_response.status_code == 200
    assert disable_response.json()["enabled"] is False
    assert enable_response.status_code == 200
    assert enable_response.json()["enabled"] is True


def test_namespace_inspection_returns_keyword_hits(client) -> None:
    response = client.post(
        "/api/v1/inspections/namespace/run",
        json={"namespace": "demo", "label_selector": "app=demo"},
    )

    payload = response.json()
    pod = payload["pods"][0]
    hit = pod["log_hits"][0]

    assert response.status_code == 200
    assert hit["keyword"] == "connection refused"
    assert hit["category"] == "database"
    assert hit["severity"] == "error"
    assert hit["whitelisted"] is False


def test_namespace_inspection_marks_whitelisted_keyword_hits(client) -> None:
    client.post(
        "/api/v1/whitelists",
        json={
            "namespace": "demo",
            "label_selector": "app=demo",
            "keyword": "connection refused",
            "pod_name_pattern": "demo-api-*",
            "container_name": "demo-api",
            "enabled": True,
            "note": "known harmless in warmup",
        },
    )

    response = client.post(
        "/api/v1/inspections/namespace/run",
        json={"namespace": "demo", "label_selector": "app=demo"},
    )

    payload = response.json()
    pod = payload["pods"][0]
    hit = pod["log_hits"][0]

    assert response.status_code == 200
    assert hit["keyword"] == "connection refused"
    assert hit["whitelisted"] is True
    assert hit["whitelist_rule_id"] is not None


def test_namespace_inspection_supports_shell_style_pod_name_pattern(client) -> None:
    client.post(
        "/api/v1/whitelists",
        json={
            "namespace": "demo",
            "label_selector": "app=demo",
            "keyword": "connection refused",
            "pod_name_pattern": "demo-api-*",
            "container_name": "demo-api",
            "enabled": True,
            "note": "known harmless in warmup",
        },
    )

    response = client.post(
        "/api/v1/inspections/namespace/run",
        json={"namespace": "demo", "label_selector": "app=demo"},
    )

    hit = response.json()["pods"][0]["log_hits"][0]

    assert response.status_code == 200
    assert hit["whitelisted"] is True
