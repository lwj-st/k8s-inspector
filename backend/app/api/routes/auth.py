from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.v1_1 import (
    AdminSession,
    AuthPasswordChangeRequest,
    AuthLoginRequest,
    SecurityAuditAction,
    SecurityAuditOutcome,
)
from app.security.audit import recent_failed_logins, write_security_audit
from app.security.auth import (
    create_admin_session,
    hash_admin_password,
    resolve_admin_session,
    revoke_admin_session,
    revoke_other_admin_sessions,
    to_session_response,
    verify_admin_password,
)
from app.services import settings_service


router = APIRouter(prefix="/auth", tags=["auth"])


def _source_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=AdminSession)
def login(
    payload: AuthLoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db_session),
) -> AdminSession:
    settings = request.app.state.settings
    source_ip = _source_ip(request)
    failed_count = recent_failed_logins(
        session,
        source_ip=source_ip,
        window_minutes=settings.login_failure_window_minutes,
    )
    if failed_count >= settings.login_failure_limit:
        write_security_audit(
            session,
            action=SecurityAuditAction.login_failed,
            outcome=SecurityAuditOutcome.denied,
            actor=payload.username,
            source_ip=source_ip,
            request_id=request.state.request_id,
            details={"reason": "rate_limited"},
        )
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="登录尝试过多，请稍后再试")

    password_hash = settings_service.get_effective_admin_password_hash(session, settings)
    if not verify_admin_password(
        settings,
        payload.username,
        payload.password.get_secret_value(),
        password_hash=password_hash,
    ):
        write_security_audit(
            session,
            action=SecurityAuditAction.login_failed,
            outcome=SecurityAuditOutcome.denied,
            actor=payload.username,
            source_ip=source_ip,
            request_id=request.state.request_id,
            details={"reason": "invalid_credentials"},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    token, authenticated = create_admin_session(
        session,
        settings,
        source_ip=source_ip,
        user_agent=request.headers.get("user-agent"),
    )
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_absolute_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path=settings.base_path.rstrip("/") or "/",
    )
    write_security_audit(
        session,
        action=SecurityAuditAction.login_succeeded,
        outcome=SecurityAuditOutcome.success,
        actor=authenticated.username,
        source_ip=source_ip,
        request_id=request.state.request_id,
    )
    return to_session_response(authenticated)


@router.post("/password", response_model=AdminSession)
def change_password(
    payload: AuthPasswordChangeRequest,
    request: Request,
    session: Session = Depends(get_db_session),
) -> AdminSession:
    settings = request.app.state.settings
    authenticated = resolve_admin_session(
        session,
        settings,
        request.cookies.get(settings.session_cookie_name),
        touch=False,
    )
    if authenticated is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期")
    password_hash = settings_service.get_effective_admin_password_hash(session, settings)
    if not verify_admin_password(
        settings,
        authenticated.username,
        payload.current_password.get_secret_value(),
        password_hash=password_hash,
    ):
        write_security_audit(
            session,
            action=SecurityAuditAction.password_changed,
            outcome=SecurityAuditOutcome.denied,
            actor=authenticated.username,
            source_ip=_source_ip(request),
            request_id=request.state.request_id,
            details={"reason": "invalid_current_password"},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="当前密码错误")

    system_settings = settings_service.get_settings(session)
    system_settings.admin_password_hash = hash_admin_password(payload.new_password.get_secret_value())
    session.commit()
    revoked_count = revoke_other_admin_sessions(
        session,
        username=authenticated.username,
        keep_database_id=authenticated.database_id,
    )
    write_security_audit(
        session,
        action=SecurityAuditAction.password_changed,
        outcome=SecurityAuditOutcome.success,
        actor=authenticated.username,
        source_ip=_source_ip(request),
        request_id=request.state.request_id,
        details={"revoked_other_sessions": revoked_count},
    )
    return to_session_response(authenticated)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_db_session),
) -> None:
    settings = request.app.state.settings
    token = request.cookies.get(settings.session_cookie_name)
    authenticated = resolve_admin_session(session, settings, token, touch=False)
    revoke_admin_session(session, settings, token)
    response.delete_cookie(
        key=settings.session_cookie_name,
        path=settings.base_path.rstrip("/") or "/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    write_security_audit(
        session,
        action=SecurityAuditAction.logout,
        outcome=SecurityAuditOutcome.success,
        actor=authenticated.username if authenticated else None,
        source_ip=_source_ip(request),
        request_id=request.state.request_id,
    )


@router.get("/session", response_model=AdminSession)
def get_session(
    request: Request,
    session: Session = Depends(get_db_session),
) -> AdminSession:
    settings = request.app.state.settings
    authenticated = resolve_admin_session(
        session,
        settings,
        request.cookies.get(settings.session_cookie_name),
    )
    return to_session_response(authenticated)
