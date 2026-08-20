from unittest.mock import Mock


def test_image_inventory_requires_namespace(client) -> None:
    response = client.get("/api/v1/images")

    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


def test_image_inventory_merges_namespaces_and_keeps_references(client) -> None:
    response = client.get(
        "/api/v1/images",
        params=[("namespace", "demo"), ("namespace", "prod-core")],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["simulated"] is True
    assert payload["namespaces"] == ["demo", "prod-core"]
    shared = next(item for item in payload["items"] if item["image"] == "registry.local/apps/demo-api:1.4.0")
    assert shared["namespace_count"] == 2
    assert shared["pod_count"] == 2
    assert shared["container_count"] == 2
    assert not any("@sha256:" in item["image"] for item in payload["items"])
    assert any(ref.get("image_id") and "@sha256:" in ref["image_id"] for item in payload["items"] for ref in item["references"])
    assert any(ref["container_type"] == "init" for item in payload["items"] for ref in item["references"])
    assert any(ref["pod_phase"] == "Succeeded" for item in payload["items"] for ref in item["references"])


def test_image_inventory_search_filters_images(client) -> None:
    response = client.get(
        "/api/v1/images",
        params=[("namespace", "demo"), ("search", "migrate")],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["search"] == "migrate"
    assert [item["image"] for item in payload["items"]] == ["registry.local/jobs/demo-migrate:20260816"]


def test_image_inventory_empty_namespace_returns_empty_result(client) -> None:
    response = client.get("/api/v1/images", params={"namespace": "empty"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "image_count": 0,
        "namespace_count": 0,
        "pod_count": 0,
        "container_count": 0,
    }
    assert payload["items"] == []


def test_image_inventory_export_matches_filter(client) -> None:
    response = client.get(
        "/api/v1/images/export",
        params=[("namespace", "demo"), ("search", "wait-for-db")],
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "attachment;" in response.headers["content-disposition"]
    assert response.text == "registry.local/platform/wait-for-db:1.2.0"
    assert "sha256" not in response.text


def test_image_inventory_provider_error_returns_upstream_error(client) -> None:
    client.app.state.provider.list_namespace_pod_images = Mock(
        side_effect=RuntimeError("当前账号缺少读取名称空间 demo Pod 的权限，无法生成镜像清单")
    )

    response = client.get("/api/v1/images", params={"namespace": "demo"})

    assert response.status_code == 502
    assert response.json()["code"] == "UPSTREAM_UNAVAILABLE"
