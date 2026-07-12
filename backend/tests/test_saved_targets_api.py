def test_create_and_list_saved_namespace_target(client) -> None:
    create_response = client.post(
        "/api/v1/inspection-targets",
        json={
            "name": "demo 全名称空间",
            "target_type": "namespace",
            "namespace": "demo",
            "label_selector": None,
            "resource_scope": ["pods", "services", "ingresses", "daemonsets", "secrets"],
        },
    )

    list_response = client.get("/api/v1/inspection-targets")

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["name"] == "demo 全名称空间"
    assert created["namespace"] == "demo"
    assert created["target_type"] == "namespace"

    assert list_response.status_code == 200
    items = list_response.json()
    assert items[0]["name"] == "demo 全名称空间"
    assert items[0]["resource_scope"] == ["pods", "services", "ingresses", "daemonsets", "secrets"]


def test_delete_saved_target_removes_it(client) -> None:
    create_response = client.post(
        "/api/v1/inspection-targets",
        json={
            "name": "demo api",
            "target_type": "namespace",
            "namespace": "demo",
            "label_selector": "app=demo-api",
            "resource_scope": ["pods"],
        },
    )
    target_id = create_response.json()["id"]

    delete_response = client.delete(f"/api/v1/inspection-targets/{target_id}")
    list_response = client.get("/api/v1/inspection-targets")

    assert delete_response.status_code == 204
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_update_saved_target_changes_name_and_selector(client) -> None:
    create_response = client.post(
        "/api/v1/inspection-targets",
        json={
            "name": "demo api",
            "target_type": "namespace",
            "namespace": "demo",
            "label_selector": "app=demo-api",
            "resource_scope": ["pods"],
        },
    )
    target_id = create_response.json()["id"]

    update_response = client.put(
        f"/api/v1/inspection-targets/{target_id}",
        json={
            "name": "demo api updated",
            "target_type": "namespace",
            "namespace": "demo",
            "label_selector": "app=demo-api-v2",
            "resource_scope": ["pods", "services"],
        },
    )

    assert update_response.status_code == 200
    payload = update_response.json()
    assert payload["name"] == "demo api updated"
    assert payload["label_selector"] == "app=demo-api-v2"
    assert payload["resource_scope"] == ["pods", "services"]


def test_export_and_import_saved_targets(client) -> None:
    client.post(
        "/api/v1/inspection-targets",
        json={
            "name": "demo 全名称空间",
            "target_type": "namespace",
            "namespace": "demo",
            "label_selector": None,
            "resource_scope": ["pods", "services"],
        },
    )

    export_response = client.get("/api/v1/inspection-targets/export")
    delete_response = client.delete(f"/api/v1/inspection-targets/{export_response.json()[0]['id']}")
    import_response = client.post("/api/v1/inspection-targets/import", json=[export_response.json()[0]])
    list_response = client.get("/api/v1/inspection-targets")

    assert export_response.status_code == 200
    assert delete_response.status_code == 204
    assert import_response.status_code == 200
    imported = import_response.json()[0]
    assert imported["name"] == "demo 全名称空间"
    assert imported["namespace"] == "demo"
    assert list_response.json()[0]["name"] == "demo 全名称空间"
