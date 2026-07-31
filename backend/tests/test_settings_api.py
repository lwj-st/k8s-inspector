from app.models import SystemSetting
from app.schemas.v1_1 import InspectionPolicySettings
from app.security.crypto import SensitiveValueCipher


def _settings_payload(**changes) -> dict:
    payload = {
        "base_path": "",
        "provider_mode": "mock",
        "kubeconfig_path": None,
        "kube_context": None,
        "llm_enabled": False,
        "llm_provider": "qwen",
        "model_endpoint": None,
        "api_key": None,
        "default_inspection_strategy": {},
    }
    payload.update(changes)
    return payload


def test_get_settings_returns_base_path_field(client) -> None:
    response = client.get("/api/v1/settings")

    assert response.status_code == 200
    assert response.json()["cluster_id"] == client.app.state.settings.cluster_id
    assert response.json()["base_path"] == ""
    assert response.json()["provider_mode"] == "mock"
    assert response.json()["inspection_policy"]["max_log_pods"] == 200
    required_components = response.json()["inspection_policy"]["required_components"]
    assert any(
        item["namespace"] == "kube-system"
        and item["kind"] == "Deployment"
        and item["label_selector"] == "k8s-app=kube-dns"
        for item in required_components
    )
    assert any(
        item["namespace"] == "ingress-nginx"
        and item["kind"] == "DaemonSet"
        and item["label_selector"] == "app.kubernetes.io/name=ingress-nginx,app.kubernetes.io/component=controller"
        for item in required_components
    )


def test_required_component_candidates_include_builtin_and_discovered(client) -> None:
    response = client.get("/api/v1/settings/required-component-candidates")

    assert response.status_code == 200
    items = response.json()["items"]
    assert any(
        item["source"] == "builtin"
        and item["name"] == "CoreDNS"
        and item["label_selector"] == "k8s-app=kube-dns"
        for item in items
    )
    assert any(
        item["source"] == "discovered"
        and item["name"] == "demo-api"
        and item["namespace"] == "demo"
        and item["kind"] == "Deployment"
        and item["label_selector"] == "app=demo-api"
        for item in items
    )


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
    assert response.json()["api_key"] == "********"

    with client.app.state.session_factory() as session:
        stored = session.get(SystemSetting, 1)
        assert stored.api_key is None
        assert "demo-key" not in stored.api_key_encrypted
        assert (
            SensitiveValueCipher.from_key(client.app.state.settings.encryption_key).decrypt(
                stored.api_key_encrypted,
                purpose="llm_api_key",
            )
            == "demo-key"
        )


def test_update_settings_persists_cluster_id_and_system_status_uses_it(client) -> None:
    response = client.put(
        "/api/v1/settings",
        json=_settings_payload(cluster_id="dev-cluster"),
    )

    assert response.status_code == 200
    assert response.json()["cluster_id"] == "dev-cluster"

    with client.app.state.session_factory() as session:
        stored = session.get(SystemSetting, 1)
        assert stored.cluster_id == "dev-cluster"

    status_response = client.get("/api/v1/system/status")
    assert status_response.status_code == 200
    assert status_response.json()["cluster_id"] == "dev-cluster"


def test_old_settings_put_without_inspection_policy_preserves_current_policy(client) -> None:
    policy = {
        "required_components": [
            {
                "name": "Ingress Controller",
                "namespace": "ingress-nginx",
                "kind": "Deployment",
                "label_selector": "app.kubernetes.io/name=ingress-nginx",
                "enabled": True,
            }
        ],
        "thresholds": {
            "tls_warning_days": 45,
            "tls_critical_days": 7,
            "pvc_pending_warning_minutes": 5,
            "pvc_pending_critical_minutes": 30,
            "pv_released_stale_hours": 24,
            "job_incomplete_info_minutes": 60,
            "resource_usage_warning_percent": 90,
            "resource_usage_consecutive_cycles": 3,
            "pod_terminating_warning_minutes": 10,
            "pod_restart_window_minutes": 10,
            "pod_restart_delta": 3,
            "warning_event_window_minutes": 30,
            "node_not_ready_grace_seconds": 0,
        },
        "max_log_pods": 321,
    }
    first = client.put(
        "/api/v1/settings",
        json=_settings_payload(inspection_policy=policy),
    )
    assert first.status_code == 200

    old_client = client.put(
        "/api/v1/settings",
        json=_settings_payload(base_path="/legacy-client"),
    )
    assert old_client.status_code == 200
    normalized_policy = InspectionPolicySettings.model_validate(policy).model_dump(mode="json")
    assert old_client.json()["inspection_policy"] == normalized_policy
    assert old_client.json()["inspection_policy"]["thresholds"]["tls_warning_days"] == 45
    assert old_client.json()["inspection_policy"]["required_components"] == policy["required_components"]
    assert old_client.json()["inspection_policy"]["max_log_pods"] == 321


def test_settings_put_persists_configurable_log_pod_limit(client) -> None:
    policy = InspectionPolicySettings(max_log_pods=450).model_dump(mode="json")

    response = client.put(
        "/api/v1/settings",
        json=_settings_payload(inspection_policy=policy),
    )

    assert response.status_code == 200
    assert response.json()["inspection_policy"]["max_log_pods"] == 450
    with client.app.state.session_factory() as session:
        stored = session.get(SystemSetting, 1)
        assert stored.inspection_policy["max_log_pods"] == 450


def test_settings_put_rejects_explicit_null_inspection_policy(client) -> None:
    response = client.put(
        "/api/v1/settings",
        json=_settings_payload(inspection_policy=None),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"
    assert response.json()["details"] == {}
