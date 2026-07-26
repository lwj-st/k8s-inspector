from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from app.models import Issue as IssueModel
from app.models import IssueEvent as IssueEventModel
from app.schemas.v1_1 import (
    Evidence,
    InspectionTrigger,
    Issue,
    IssueEvent,
    IssueEventType,
    IssueListFilter,
    IssueScope,
    IssueSeverity,
    IssueSortMode,
    IssueStatus,
    Page,
    ResourceRef,
)
from app.services.payload_sanitizer import sanitize_public_payload


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def issue_from_model(row: IssueModel) -> Issue:
    payload = {
        "id": row.id,
        "cluster_id": row.cluster_id,
        "issue_code": row.issue_code,
        "fingerprint": row.fingerprint,
        "severity": row.severity,
        "status": row.status,
        "scope": row.scope,
        "resource": {
            "api_version": row.resource_api_version,
            "kind": row.resource_kind,
            "namespace": row.resource_namespace,
            "name": row.resource_name,
            "uid": row.resource_uid,
        },
        "summary": row.summary,
        "reason": row.reason,
        "suggestion": row.suggestion,
        "evidence": list(row.evidence or []),
        "first_seen_at": _utc(row.first_seen_at),
        "last_seen_at": _utc(row.last_seen_at),
        "recovered_at": _utc(row.recovered_at),
        "occurrence_count": row.occurrence_count,
        "source_check": row.source_check,
        "correlation_key": row.correlation_key,
        "acknowledged_at": _utc(row.acknowledged_at),
        "acknowledge_note": row.acknowledge_note,
    }
    return Issue.model_validate(sanitize_public_payload(payload))


def issue_event_from_model(row: IssueEventModel) -> IssueEvent:
    payload = {
        "id": row.id,
        "issue_id": row.issue_id,
        "run_id": row.run_id,
        "event_type": row.event_type,
        "trigger": row.trigger,
        "previous_status": row.previous_status,
        "new_status": row.new_status,
        "previous_severity": row.previous_severity,
        "new_severity": row.new_severity,
        "occurred_at": _utc(row.occurred_at),
        "summary": row.summary,
        "evidence_codes": list(row.evidence_codes or []),
    }
    return IssueEvent.model_validate(sanitize_public_payload(payload))


def get_issue(session: Session, issue_id: int) -> IssueModel | None:
    return session.get(IssueModel, issue_id)


def list_issues(session: Session, filters: IssueListFilter) -> Page[Issue]:
    query = select(IssueModel)
    if filters.status is not None:
        query = query.where(IssueModel.status == filters.status.value)
    if filters.severity is not None:
        query = query.where(IssueModel.severity == filters.severity.value)
    if filters.namespace is not None:
        query = query.where(IssueModel.resource_namespace == filters.namespace)
    if filters.resource_kind is not None:
        query = query.where(func.lower(IssueModel.resource_kind) == filters.resource_kind.casefold())
    if filters.source_check is not None:
        query = query.where(IssueModel.source_check == filters.source_check)

    total = int(session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    query_time = datetime.now(timezone.utc)
    status_rank = case((IssueModel.status == IssueStatus.open.value, 0), else_=1)
    severity_rank = case(
        (IssueModel.severity == IssueSeverity.critical.value, 0),
        (IssueModel.severity == IssueSeverity.warning.value, 1),
        else_=2,
    )
    duration = case(
        (
            IssueModel.status == IssueStatus.open.value,
            func.julianday(query_time) - func.julianday(IssueModel.first_seen_at),
        ),
        else_=func.julianday(IssueModel.recovered_at) - func.julianday(IssueModel.first_seen_at),
    )
    if filters.sort == IssueSortMode.last_changed:
        latest_event = (
            select(func.max(IssueEventModel.occurred_at))
            .where(IssueEventModel.issue_id == IssueModel.id)
            .correlate(IssueModel)
            .scalar_subquery()
        )
        query = query.order_by(desc(func.coalesce(latest_event, IssueModel.first_seen_at)), desc(IssueModel.id))
    elif filters.sort == IssueSortMode.duration:
        query = query.order_by(status_rank, desc(duration), severity_rank, desc(IssueModel.id))
    else:
        query = query.order_by(status_rank, severity_rank, desc(duration), desc(IssueModel.id))

    rows = session.scalars(
        query.offset((filters.page - 1) * filters.page_size).limit(filters.page_size)
    ).all()
    return Page[Issue](
        items=[issue_from_model(row) for row in rows],
        total=total,
        page=filters.page,
        page_size=filters.page_size,
    )


def list_issue_events(
    session: Session,
    *,
    issue_id: int,
    page: int,
    page_size: int,
) -> Page[IssueEvent] | None:
    if session.get(IssueModel, issue_id) is None:
        return None
    base = select(IssueEventModel).where(IssueEventModel.issue_id == issue_id)
    total = int(session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = session.scalars(
        base.order_by(desc(IssueEventModel.occurred_at), desc(IssueEventModel.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page[IssueEvent](
        items=[issue_event_from_model(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
