from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import Settings
from app.main import create_app
from app.schemas.v1_1 import ComponentState, SystemComponentStatus
from app.security import lifespan as lifespan_module
from app.security.middleware import safe_request_id


TEST_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


def test_liveness_does_not_depend_on_database_or_kubernetes_readiness(tmp_path: Path) -> None:
    database_path = tmp_path / "invalid.db"
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)"))
    engine.dispose()

    app = create_app(
        Settings(
            app_env="test",
            database_url=f"sqlite:///{database_path}",
            encryption_key=TEST_KEY,
        )
    )
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        ready = client.get("/health/ready")
        assert ready.status_code == 503
        assert ready.json()["ready"] is False
        assert ready.json()["reasons"]


def test_production_missing_security_configuration_is_not_ready(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            app_env="production",
            database_url=f"sqlite:///{tmp_path / 'prod.db'}",
            auth_mode="disabled",
            auto_migrate=True,
        )
    )
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        result = client.get("/health/ready")
        assert result.status_code == 503
        assert any("鉴权" in reason for reason in result.json()["reasons"])


def test_ready_succeeds_after_platform_initialization(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            app_env="test",
            database_url=f"sqlite:///{tmp_path / 'ready.db'}",
            encryption_key=TEST_KEY,
        )
    )
    with TestClient(app) as client:
        result = client.get("/health/ready")
        assert result.status_code == 200
        assert result.json()["ready"] is True
        assert result.json()["reasons"] == []


def test_lifespan_hook_failure_cleans_started_hooks_and_blocks_readiness(
    tmp_path: Path,
) -> None:
    original_hooks = list(lifespan_module._HOOKS)
    lifespan_module._HOOKS.clear()
    events: list[str] = []

    async def first_start(app) -> None:
        events.append("first_start")

    async def first_stop(app) -> None:
        events.append("first_stop")

    async def failing_start(app) -> None:
        events.append("failing_start")
        raise RuntimeError("sensitive internal reason")

    async def failing_stop(app) -> None:
        events.append("failing_stop")

    try:
        lifespan_module.register_lifespan_hook(
            name="first",
            start=first_start,
            stop=first_stop,
        )
        lifespan_module.register_lifespan_hook(
            name="failing",
            start=failing_start,
            stop=failing_stop,
        )
        app = create_app(
            Settings(
                app_env="test",
                database_url=f"sqlite:///{tmp_path / 'hooks.db'}",
                encryption_key=TEST_KEY,
            )
        )
        with TestClient(app) as client:
            ready = client.get("/health/ready")
            assert ready.status_code == 503
            assert "sensitive internal reason" not in ready.text
        assert events == ["first_start", "failing_start", "first_stop"]
    finally:
        lifespan_module._HOOKS[:] = original_hooks


def test_later_modules_can_update_frozen_system_component_status(
    tmp_path: Path,
) -> None:
    app = create_app(
        Settings(
            app_env="test",
            database_url=f"sqlite:///{tmp_path / 'registry.db'}",
            encryption_key=TEST_KEY,
        )
    )
    now = datetime.now(timezone.utc)
    app.state.component_status_registry.update(
        "scheduler",
        SystemComponentStatus(
            state=ComponentState.ok,
            message="调度器运行中",
            checked_at=now,
            details={"registered_plans": 2},
        ),
    )
    app.state.component_status_registry.update(
        "notifications",
        SystemComponentStatus(
            state=ComponentState.degraded,
            message="一个渠道暂不可用",
            checked_at=now,
            details={"failed_channels": 1},
        ),
    )
    app.state.component_status_registry.update_kubernetes_version("v1.36.1", True)
    with TestClient(app) as client:
        result = client.get("/api/v1/system/status")
        assert result.status_code == 200
        payload = result.json()
        assert payload["status"] == "degraded"
        assert payload["scheduler"]["state"] == "ok"
        assert payload["notifications"]["state"] == "degraded"
        assert payload["kubernetes_server_version"] == "v1.36.1"
        assert payload["kubernetes_version_supported"] is True


def test_provider_initialization_failure_keeps_live_and_returns_controlled_503(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fail_provider(settings):
        raise RuntimeError("kubeconfig secret content")

    monkeypatch.setattr("app.main.build_provider", fail_provider)
    app = create_app(
        Settings(
            app_env="test",
            database_url=f"sqlite:///{tmp_path / 'provider.db'}",
            encryption_key=TEST_KEY,
        )
    )
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        ready = client.get("/health/ready")
        assert ready.status_code == 503
        assert "kubeconfig secret content" not in ready.text
        system = client.get("/api/v1/system/status")
        assert system.json()["status"] == "not_ready"
        assert system.json()["provider"]["state"] == "failed"
        dependency = client.get("/api/v1/discovery/namespaces")
        assert dependency.status_code == 503
        assert dependency.json()["code"] == "SERVICE_NOT_READY"


def test_system_status_is_healthy_only_when_every_component_is_ok(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            app_env="test",
            database_url=f"sqlite:///{tmp_path / 'healthy.db'}",
            encryption_key=TEST_KEY,
        )
    )
    now = datetime.now(timezone.utc)
    for component in (
        "kubernetes_api",
        "scheduler",
        "metrics_api",
        "notifications",
        "last_inspection",
    ):
        app.state.component_status_registry.update(
            component,
            SystemComponentStatus(
                state=ComponentState.ok,
                message=f"{component} 正常",
                checked_at=now,
                details={},
            ),
        )
    with TestClient(app) as client:
        result = client.get("/api/v1/system/status")
        assert result.status_code == 200
        assert result.json()["status"] == "healthy"


@pytest.mark.parametrize("candidate", ["x" * 129, "bad request id", "bad/id", "\r\ninjected"])
def test_unsafe_request_id_is_replaced_and_never_echoed(candidate: str) -> None:
    generated = safe_request_id(candidate)
    assert generated != candidate
    assert str(UUID(generated)) == generated


def test_request_id_header_accepts_only_bounded_safe_characters(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            app_env="test",
            database_url=f"sqlite:///{tmp_path / 'request-id.db'}",
            encryption_key=TEST_KEY,
        )
    )
    with TestClient(app) as client:
        valid = client.get("/health/live", headers={"X-Request-ID": "ops.req-1:trace"})
        assert valid.headers["x-request-id"] == "ops.req-1:trace"

        malicious = "x" * 129
        replaced = client.get("/health/live", headers={"X-Request-ID": malicious})
        assert replaced.headers["x-request-id"] != malicious
        assert malicious not in replaced.text
        assert str(UUID(replaced.headers["x-request-id"])) == replaced.headers["x-request-id"]
