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
