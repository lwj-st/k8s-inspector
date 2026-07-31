from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import AdminSession as AdminSessionModel
from app.schemas.v1_1 import AdminSession as AdminSessionResponse


_PASSWORD_HASHER = PasswordHasher()


@dataclass(frozen=True)
class AuthenticatedSession:
    username: str
    csrf_token: str
    idle_expires_at: datetime
    absolute_expires_at: datetime
    database_id: int | None


def verify_admin_password(
    settings: Settings,
    username: str,
    password: str,
    *,
    password_hash: str | None = None,
) -> bool:
    effective_password_hash = password_hash or settings.admin_password_hash
    if settings.auth_mode != "local" or not settings.admin_username or not effective_password_hash:
        return False
    username_matches = hmac.compare_digest(username.encode("utf-8"), settings.admin_username.encode("utf-8"))
    try:
        password_matches = _PASSWORD_HASHER.verify(effective_password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        password_matches = False
    return bool(username_matches and password_matches)


def hash_admin_password(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def hash_session_token(token: str, settings: Settings) -> str:
    if not settings.session_secret:
        raise RuntimeError("Session Secret 未配置")
    return hmac.new(
        settings.session_secret.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def create_admin_session(
    session: Session,
    settings: Settings,
    *,
    source_ip: str | None,
    user_agent: str | None,
) -> tuple[str, AuthenticatedSession]:
    now = datetime.now(timezone.utc)
    absolute_expires_at = now + timedelta(hours=settings.session_absolute_hours)
    idle_expires_at = min(
        now + timedelta(minutes=settings.session_idle_minutes),
        absolute_expires_at,
    )
    token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    model = AdminSessionModel(
        token_hash=hash_session_token(token, settings),
        username=settings.admin_username or "",
        csrf_token=csrf_token,
        created_at=now,
        last_seen_at=now,
        idle_expires_at=idle_expires_at,
        absolute_expires_at=absolute_expires_at,
        source_ip=source_ip,
        user_agent_hash=(
            hashlib.sha256(user_agent.encode("utf-8")).hexdigest() if user_agent else None
        ),
    )
    session.add(model)
    session.commit()
    session.refresh(model)
    return token, AuthenticatedSession(
        username=model.username,
        csrf_token=model.csrf_token,
        idle_expires_at=_as_utc(model.idle_expires_at),
        absolute_expires_at=_as_utc(model.absolute_expires_at),
        database_id=model.id,
    )


def resolve_admin_session(
    session: Session,
    settings: Settings,
    token: str | None,
    *,
    touch: bool = True,
) -> AuthenticatedSession | None:
    if settings.auth_mode == "disabled":
        if settings.app_env not in {"development", "test", "ci", "mock"}:
            return None
        now = datetime.now(timezone.utc)
        return AuthenticatedSession(
            username="development",
            csrf_token="development-csrf-token",
            idle_expires_at=now + timedelta(days=1),
            absolute_expires_at=now + timedelta(days=1),
            database_id=None,
        )
    if not token:
        return None
    token_hash = hash_session_token(token, settings)
    model = session.scalar(
        select(AdminSessionModel).where(AdminSessionModel.token_hash == token_hash)
    )
    if model is None or model.revoked_at is not None:
        return None
    now = datetime.now(timezone.utc)
    idle_expires_at = _as_utc(model.idle_expires_at)
    absolute_expires_at = _as_utc(model.absolute_expires_at)
    if now >= idle_expires_at or now >= absolute_expires_at:
        if model.revoked_at is None:
            model.revoked_at = now
            session.commit()
        return None
    if touch:
        model.last_seen_at = now
        model.idle_expires_at = min(
            now + timedelta(minutes=settings.session_idle_minutes),
            absolute_expires_at,
        )
        session.commit()
        idle_expires_at = _as_utc(model.idle_expires_at)
    return AuthenticatedSession(
        username=model.username,
        csrf_token=model.csrf_token,
        idle_expires_at=idle_expires_at,
        absolute_expires_at=absolute_expires_at,
        database_id=model.id,
    )


def revoke_admin_session(
    session: Session,
    settings: Settings,
    token: str | None,
) -> bool:
    if settings.auth_mode == "disabled" or not token:
        return False
    model = session.scalar(
        select(AdminSessionModel).where(
            AdminSessionModel.token_hash == hash_session_token(token, settings)
        )
    )
    if model is None or model.revoked_at is not None:
        return False
    model.revoked_at = datetime.now(timezone.utc)
    session.commit()
    return True


def revoke_other_admin_sessions(
    session: Session,
    *,
    username: str,
    keep_database_id: int | None,
) -> int:
    if keep_database_id is None:
        return 0
    now = datetime.now(timezone.utc)
    rows = list(
        session.scalars(
            select(AdminSessionModel).where(
                AdminSessionModel.username == username,
                AdminSessionModel.id != keep_database_id,
                AdminSessionModel.revoked_at.is_(None),
            )
        )
    )
    for row in rows:
        row.revoked_at = now
    if rows:
        session.commit()
    return len(rows)


def to_session_response(value: AuthenticatedSession | None) -> AdminSessionResponse:
    if value is None:
        return AdminSessionResponse(authenticated=False)
    return AdminSessionResponse(
        authenticated=True,
        username=value.username,
        csrf_token=value.csrf_token,
        idle_expires_at=value.idle_expires_at,
        absolute_expires_at=value.absolute_expires_at,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
