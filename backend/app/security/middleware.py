from __future__ import annotations

import re
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.pathing import build_api_prefix
from app.security.auth import resolve_admin_session
from app.security.csrf import csrf_token_matches


_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class AuthenticationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, settings) -> None:
        super().__init__(app)
        self.settings = settings
        self.api_prefix = build_api_prefix(settings.base_path).rstrip("/")
        self.anonymous_api_paths = {
            f"{self.api_prefix}/auth/login",
            f"{self.api_prefix}/auth/session",
        }
        base_path = settings.base_path.rstrip("/")
        self.anonymous_health_paths = {
            f"{base_path}/health/live" if base_path else "/health/live",
            f"{base_path}/health/ready" if base_path else "/health/ready",
        }

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = safe_request_id(request.headers.get("x-request-id"))
        request.state.request_id = request_id
        path = request.url.path.rstrip("/") or "/"
        if (
            request.method == "OPTIONS"
            or (
                self.settings.auth_mode == "disabled"
                and self.settings.app_env in {"development", "test", "ci", "mock"}
            )
            or path in self.anonymous_api_paths
            or path in self.anonymous_health_paths
            or not path.startswith(f"{self.api_prefix}/")
        ):
            response = await call_next(request)
            response.headers.setdefault("x-request-id", request_id)
            return response

        session_factory = request.app.state.session_factory
        with session_factory() as database:
            authenticated = resolve_admin_session(
                database,
                self.settings,
                request.cookies.get(self.settings.session_cookie_name),
            )
        if authenticated is None:
            return _error_response(
                401,
                "AUTHENTICATION_REQUIRED",
                "请先登录后再访问",
                request_id,
            )
        request.state.authenticated_session = authenticated
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if not csrf_token_matches(authenticated, request.headers.get("x-csrf-token")):
                return _error_response(
                    403,
                    "CSRF_VALIDATION_FAILED",
                    "请求安全校验失败，请刷新页面后重试",
                    request_id,
                )
        response = await call_next(request)
        response.headers.setdefault("x-request-id", request_id)
        return response


def safe_request_id(candidate: str | None) -> str:
    if candidate and _SAFE_REQUEST_ID.fullmatch(candidate):
        return candidate
    return str(uuid4())


def _error_response(status_code: int, code: str, message: str, request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "request_id": request_id,
            "details": {},
        },
        headers={"x-request-id": request_id},
    )
