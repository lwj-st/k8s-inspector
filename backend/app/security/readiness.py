from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from app.models import SystemSetting
from app.db.migrate import HEAD_REVISION, current_revision
from app.schemas.v1_1 import ComponentState, ReadyHealthResponse, SystemComponentStatus, SystemStatus


def readiness_reasons(app) -> list[str]:
    reasons = list(_security_configuration_errors(app))
    if app.state.platform_initialization_error:
        reasons.append(app.state.platform_initialization_error)
    if app.state.provider_initialization_error:
        reasons.append(app.state.provider_initialization_error)
    if getattr(app.state, "lifespan_hook_error", None):
        reasons.append(app.state.lifespan_hook_error)
    try:
        revision = current_revision(settings)
        if revision != HEAD_REVISION:
            reasons.append(f"数据库 schema 版本不匹配：当前 {revision}，要求 {HEAD_REVISION}")
    except Exception:
        reasons.append("数据库 schema 版本检查失败")
    return reasons


def build_ready_response(app) -> ReadyHealthResponse:
    reasons = readiness_reasons(app)
    return ReadyHealthResponse(
        status="not_ready" if reasons else "ready",
        ready=not reasons,
        reasons=reasons,
    )


def build_system_status(app, *, cluster_id: str | None = None) -> SystemStatus:
    settings = app.state.settings
    now = datetime.now(timezone.utc)
    reasons = readiness_reasons(app)
    database = _database_status(app, now)
    configuration_errors = _security_configuration_errors(app)
    configuration = SystemComponentStatus(
        state=ComponentState.failed if configuration_errors else ComponentState.ok,
        message="配置校验失败" if configuration_errors else "配置校验通过",
        checked_at=now,
        details={"error_count": len(configuration_errors)},
    )
    provider_state = ComponentState.ok if app.state.provider is not None else ComponentState.failed
    provider = SystemComponentStatus(
        state=provider_state,
        message=f"{settings.provider_mode} Provider 已初始化"
        if app.state.provider is not None
        else "Provider 初始化失败",
        checked_at=now,
        details={"mode": settings.provider_mode},
    )
    registry = app.state.component_status_registry
    scheduler = registry.get("scheduler")
    hook_error = getattr(app.state, "lifespan_hook_error", None)
    if hook_error:
        scheduler = SystemComponentStatus(
            state=ComponentState.failed,
            message=hook_error,
            checked_at=now,
            details={},
        )
    kubernetes_version, kubernetes_supported = registry.kubernetes_version()
    kubernetes_api = registry.get("kubernetes_api")
    metrics_api = registry.get("metrics_api")
    notifications = registry.get("notifications")
    last_inspection = registry.get("last_inspection")
    components = (
        database,
        kubernetes_api,
        provider,
        scheduler,
        metrics_api,
        notifications,
        last_inspection,
        configuration,
    )
    if reasons:
        status_value = "not_ready"
    elif all(component.state == ComponentState.ok for component in components):
        status_value = "healthy"
    else:
        status_value = "degraded"
    return SystemStatus(
        status=status_value,
        version=settings.app_version,
        cluster_id=cluster_id or settings.cluster_id,
        database=database,
        kubernetes_api=kubernetes_api,
        provider=provider,
        scheduler=scheduler,
        metrics_api=metrics_api,
        notifications=notifications,
        last_inspection=last_inspection,
        configuration=configuration,
        kubernetes_server_version=kubernetes_version,
        kubernetes_version_supported=kubernetes_supported,
    )


def _security_configuration_errors(app) -> list[str]:
    settings = app.state.settings
    errors = list(settings.security_configuration_errors())
    missing_password_message = "缺少管理员密码哈希"
    if missing_password_message in errors and _stored_admin_password_hash_configured(app):
        errors.remove(missing_password_message)
    return errors


def _stored_admin_password_hash_configured(app) -> bool:
    try:
        with app.state.session_factory() as session:
            row = session.get(SystemSetting, 1)
            return bool(row and row.admin_password_hash)
    except Exception:
        return False


def _database_status(app, now: datetime) -> SystemComponentStatus:
    try:
        revision = current_revision(app.state.settings)
        with app.state.session_factory() as session:
            session.execute(text("SELECT 1"))
        state = ComponentState.ok if revision == HEAD_REVISION else ComponentState.failed
        message = "数据库连接与 schema 正常" if state == ComponentState.ok else "数据库 schema 版本不匹配"
        return SystemComponentStatus(
            state=state,
            message=message,
            checked_at=now,
            details={"schema_version": revision},
        )
    except Exception:
        return SystemComponentStatus(
            state=ComponentState.failed,
            message="数据库连接或 schema 检查失败",
            checked_at=now,
            details={},
        )
