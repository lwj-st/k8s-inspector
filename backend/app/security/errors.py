from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from kubernetes.client.exceptions import ApiException


def register_api_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _response(request, 422, "REQUEST_VALIDATION_FAILED", "请求参数校验失败")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code, message = _safe_http_error(exc.status_code)
        return _response(request, exc.status_code, code, message, headers=exc.headers)

    @app.exception_handler(ApiException)
    async def kubernetes_api_error(request: Request, exc: ApiException) -> JSONResponse:
        if exc.status == 403:
            return _response(
                request,
                503,
                "KUBERNETES_RBAC_FORBIDDEN",
                "Kubernetes 巡检权限不足，请检查 ServiceAccount 的只读 RBAC 权限",
                details={"upstream_status": 403, "reason": "Forbidden"},
            )
        return _response(
            request,
            503,
            "KUBERNETES_API_UNAVAILABLE",
            "Kubernetes API 暂时不可用，请稍后重试",
            details={
                "upstream_status": int(exc.status) if exc.status else None,
                "reason": str(exc.reason or "Kubernetes API request failed")[:200],
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return _response(request, 500, "INTERNAL_SERVER_ERROR", "服务暂时无法处理请求")


def _safe_http_error(status_code: int) -> tuple[str, str]:
    mapping = {
        400: ("BAD_REQUEST", "请求无法处理"),
        401: ("AUTHENTICATION_REQUIRED", "用户名或密码错误"),
        403: ("ACCESS_DENIED", "没有权限执行此操作"),
        404: ("RESOURCE_NOT_FOUND", "请求的资源不存在"),
        409: ("STATE_CONFLICT", "请求与当前状态冲突"),
        422: ("REQUEST_VALIDATION_FAILED", "请求参数校验失败"),
        429: ("LOGIN_RATE_LIMITED", "登录尝试过多，请稍后再试"),
        502: ("UPSTREAM_UNAVAILABLE", "上游服务暂时不可用"),
        503: ("SERVICE_NOT_READY", "服务尚未就绪"),
    }
    return mapping.get(status_code, ("REQUEST_FAILED", "请求处理失败"))


def _response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    *,
    headers: dict[str, str] | None = None,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    response_headers = dict(headers or {})
    if request_id:
        response_headers["x-request-id"] = request_id
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "request_id": request_id,
            "details": details or {},
        },
        headers=response_headers,
    )
