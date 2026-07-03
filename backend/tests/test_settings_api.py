def test_get_settings_returns_base_path_field(client) -> None:
    response = client.get("/api/v1/settings")

    assert response.status_code == 200
    assert response.json()["base_path"] == ""
    assert response.json()["provider_mode"] == "mock"


def test_update_settings_persists_values(client) -> None:
    response = client.put(
        "/api/v1/settings",
        json={
            "base_path": "/inspector",
            "llm_enabled": True,
            "llm_provider": "qwen",
            "model_endpoint": "https://example.com",
            "api_key": "demo-key",
            "default_inspection_strategy": {"mode": "fast"},
        },
    )

    assert response.status_code == 200
    assert response.json()["base_path"] == "/inspector"
    assert response.json()["llm_enabled"] is True
