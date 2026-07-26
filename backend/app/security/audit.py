from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import SecurityAuditLog
from app.schemas.v1_1 import SecurityAuditAction, SecurityAuditOutcome


_ALLOWED_DETAIL_KEYS = {
    "reason",
    "resource_id",
    "resource_type",
    "changed_fields",
    "channel_type",
}


def write_security_audit(
    session: Session,
    *,
    action: SecurityAuditAction | str,
    outcome: SecurityAuditOutcome | str,
    actor: str | None,
    source_ip: str | None,
    request_id: str | None,
    details: dict[str, str | int | float | bool | None] | None = None,
) -> SecurityAuditLog:
    safe_details = details or {}
    unexpected = set(safe_details) - _ALLOWED_DETAIL_KEYS
    if unexpected:
        raise ValueError(f"安全审计包含未批准字段：{', '.join(sorted(unexpected))}")
    record = SecurityAuditLog(
        action=action.value if isinstance(action, SecurityAuditAction) else action,
        outcome=outcome.value if isinstance(outcome, SecurityAuditOutcome) else outcome,
        actor=actor,
        source_ip=source_ip,
        request_id=request_id,
        details=safe_details,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def recent_failed_logins(
    session: Session,
    *,
    source_ip: str,
    window_minutes: int,
) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    return int(
        session.scalar(
            select(func.count(SecurityAuditLog.id)).where(
                SecurityAuditLog.action == SecurityAuditAction.login_failed.value,
                SecurityAuditLog.source_ip == source_ip,
                SecurityAuditLog.occurred_at >= cutoff,
            )
        )
        or 0
    )
