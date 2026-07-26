from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, exists, select, update
from sqlalchemy.orm import Session

from app.models import (
    InspectionCheckResult,
    InspectionRun,
    Issue,
    IssueEvent,
    IssueScopeMembership,
    NotificationDelivery,
    SecurityAuditLog,
    SystemSetting,
)
from app.models.v1_1 import inspection_run_issues
from app.schemas.v1_1 import InspectionPolicySettings


def cleanup_expired_data(
    session: Session,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    current = now or datetime.now(timezone.utc)
    policy = _policy(session)
    retention = policy.retention
    run_days = retention.inspection_run_days
    recovered_days = retention.recovered_issue_days
    delivery_days = retention.notification_delivery_days
    audit_days = retention.security_audit_days

    run_ids = list(
        session.scalars(
            select(InspectionRun.id).where(
                InspectionRun.created_at < current - timedelta(days=run_days),
                InspectionRun.status.not_in(["queued", "running"]),
            )
        ).all()
    )
    if run_ids:
        session.execute(
            update(NotificationDelivery)
            .where(NotificationDelivery.run_id.in_(run_ids))
            .values(run_id=None)
        )
        session.execute(
            update(IssueEvent).where(IssueEvent.run_id.in_(run_ids)).values(run_id=None)
        )
        session.execute(
            delete(InspectionCheckResult).where(InspectionCheckResult.run_id.in_(run_ids))
        )
        session.execute(
            delete(inspection_run_issues).where(inspection_run_issues.c.run_id.in_(run_ids))
        )
        session.execute(delete(InspectionRun).where(InspectionRun.id.in_(run_ids)))

    recovered_issue_ids = list(
        session.scalars(
            select(Issue.id).where(
                Issue.status == "recovered",
                Issue.recovered_at.is_not(None),
                Issue.recovered_at < current - timedelta(days=recovered_days),
                ~exists(
                    select(IssueScopeMembership.issue_id).where(
                        IssueScopeMembership.issue_id == Issue.id,
                        IssueScopeMembership.active.is_(True),
                    )
                ),
            )
        ).all()
    )
    if recovered_issue_ids:
        event_ids = list(
            session.scalars(
                select(IssueEvent.id).where(IssueEvent.issue_id.in_(recovered_issue_ids))
            ).all()
        )
        if event_ids:
            session.execute(
                update(NotificationDelivery)
                .where(NotificationDelivery.issue_event_id.in_(event_ids))
                .values(issue_event_id=None)
            )
        session.execute(
            delete(inspection_run_issues).where(
                inspection_run_issues.c.issue_id.in_(recovered_issue_ids)
            )
        )
        session.execute(
            delete(IssueScopeMembership).where(
                IssueScopeMembership.issue_id.in_(recovered_issue_ids)
            )
        )
        session.execute(delete(IssueEvent).where(IssueEvent.issue_id.in_(recovered_issue_ids)))
        session.execute(delete(Issue).where(Issue.id.in_(recovered_issue_ids)))

    delivery_result = session.execute(
        delete(NotificationDelivery).where(
            NotificationDelivery.created_at < current - timedelta(days=delivery_days)
        )
    )
    audit_result = session.execute(
        delete(SecurityAuditLog).where(
            SecurityAuditLog.occurred_at < current - timedelta(days=audit_days)
        )
    )
    session.commit()
    return {
        "inspection_runs": len(run_ids),
        "recovered_issues": len(recovered_issue_ids),
        "notification_deliveries": int(delivery_result.rowcount or 0),
        "security_audit_logs": int(audit_result.rowcount or 0),
    }


def _policy(session: Session) -> InspectionPolicySettings:
    settings = session.get(SystemSetting, 1)
    if settings is None or not settings.inspection_policy:
        return InspectionPolicySettings()
    return InspectionPolicySettings.model_validate(settings.inspection_policy)
