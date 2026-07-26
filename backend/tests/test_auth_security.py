from pathlib import Path
from datetime import datetime, timedelta, timezone
import json

from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.main import create_app
from app.models import AdminSession as AdminSessionModel
from app.models import SecurityAuditLog


TEST_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


def _local_auth_settings(path: Path, **changes) -> Settings:
    values = {
        "app_env": "test",
        "database_url": f"sqlite:///{path}",
        "auth_mode": "local",
        "admin_username": "admin",
        "admin_password_hash": PasswordHasher().hash("correct-password"),
        "session_secret": "s" * 32,
        "encryption_key": TEST_KEY,
        "session_cookie_secure": False,
    }
    values.update(changes)
    return Settings(**values)


def test_login_session_csrf_logout_and_server_side_revocation(tmp_path: Path) -> None:
    settings = _local_auth_settings(tmp_path / "auth.db")
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/v1/settings").status_code == 401
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "correct-password"},
        )
        assert login.status_code == 200
        csrf_token = login.json()["csrf_token"]
        raw_cookie = login.cookies.get(settings.session_cookie_name)
        assert raw_cookie
        assert "HttpOnly" in login.headers["set-cookie"]
        assert "SameSite=strict" in login.headers["set-cookie"]

        with app.state.session_factory() as database:
            stored = database.scalar(select(AdminSessionModel))
            assert stored is not None
            assert stored.token_hash != raw_cookie
            assert raw_cookie not in stored.token_hash

        assert client.get("/api/v1/settings").status_code == 200
        assert client.put("/api/v1/settings", json={}).status_code == 403
        logout = client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf_token},
        )
        assert logout.status_code == 204
        assert client.get("/api/v1/auth/session").json() == {
            "authenticated": False,
            "username": None,
            "csrf_token": None,
            "idle_expires_at": None,
            "absolute_expires_at": None,
        }
        assert client.get("/api/v1/settings").status_code == 401


def test_login_failure_limit_returns_429_and_never_echoes_password(tmp_path: Path) -> None:
    settings = _local_auth_settings(
        tmp_path / "rate.db",
        login_failure_limit=2,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        malicious_request_id = "x" * 129
        for _ in range(2):
            denied = client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "wrong-password"},
                headers={"X-Request-ID": malicious_request_id},
            )
            assert denied.status_code == 401
            assert "wrong-password" not in denied.text
            assert denied.json()["code"] == "AUTHENTICATION_REQUIRED"
            assert denied.json()["request_id"]
            assert denied.json()["request_id"] != malicious_request_id
            assert denied.headers["x-request-id"] == denied.json()["request_id"]
            assert denied.json()["details"] == {}
        limited = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "wrong-password"},
            headers={"X-Request-ID": malicious_request_id},
        )
        assert limited.status_code == 429
        assert limited.json()["code"] == "LOGIN_RATE_LIMITED"
        assert "wrong-password" not in limited.text
        with app.state.session_factory() as database:
            audits = database.scalars(select(SecurityAuditLog)).all()
            serialized = json.dumps(
                [{"actor": item.actor, "details": item.details} for item in audits]
            )
            assert "wrong-password" not in serialized
            assert malicious_request_id not in serialized
            assert all(item.request_id and len(item.request_id) <= 128 for item in audits)


def test_idle_expired_session_is_rejected_and_revoked(tmp_path: Path) -> None:
    settings = _local_auth_settings(tmp_path / "expired.db")
    app = create_app(settings)
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "correct-password"},
        )
        assert login.status_code == 200
        with app.state.session_factory() as database:
            stored = database.scalar(select(AdminSessionModel))
            stored.idle_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            database.commit()

        assert client.get("/api/v1/auth/session").json()["authenticated"] is False
        with app.state.session_factory() as database:
            stored = database.scalar(select(AdminSessionModel))
            assert stored.revoked_at is not None
