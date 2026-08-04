from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models import Issue as IssueModel
from app.models import MaintenanceSilenceWindow as MaintenanceSilenceWindowModel
from app.schemas.v1_1 import (
    MaintenanceSilenceScope,
    MaintenanceSilenceScopeType,
    MaintenanceSilenceWindow,
    MaintenanceSilenceWindowCreate,
    MaintenanceSilenceWindowUpdate,
    Page,
)
from app.services.payload_sanitizer import sanitize_public_payload


def window_from_model(row: MaintenanceSilenceWindowModel) -> MaintenanceSilenceWindow:
    return MaintenanceSilenceWindow(
        id=row.id,
        name=row.name,
        enabled=row.enabled,
        start_at=_utc(row.start_at),
        end_at=_utc(row.end_at),
        scope=MaintenanceSilenceScope(
            type=MaintenanceSilenceScopeType(row.scope_type),
            namespace=row.namespace,
            resource_kind=row.resource_kind,
            label_selector=row.label_selector,
        ),
        note=row.note,
        pending_summary_recorded_at=_utc(row.pending_summary_recorded_at),
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


def list_windows(
    session: Session,
    *,
    page: int,
    page_size: int,
) -> Page[MaintenanceSilenceWindow]:
    base = select(MaintenanceSilenceWindowModel)
    total = int(session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = session.scalars(
        base.order_by(desc(MaintenanceSilenceWindowModel.start_at), desc(MaintenanceSilenceWindowModel.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page[MaintenanceSilenceWindow](
        items=[window_from_model(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_window(session: Session, window_id: int) -> MaintenanceSilenceWindowModel | None:
    return session.get(MaintenanceSilenceWindowModel, window_id)


def create_window(
    session: Session,
    payload: MaintenanceSilenceWindowCreate,
) -> MaintenanceSilenceWindow:
    scope = payload.scope
    row = MaintenanceSilenceWindowModel(
        name=sanitize_public_payload(payload.name.strip()),
        enabled=payload.enabled,
        start_at=payload.start_at,
        end_at=payload.end_at,
        scope_type=scope.type.value,
        namespace=scope.namespace,
        resource_kind=scope.resource_kind,
        label_selector=scope.label_selector,
        note=sanitize_public_payload(payload.note) if payload.note else None,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return window_from_model(row)


def update_window(
    session: Session,
    row: MaintenanceSilenceWindowModel,
    payload: MaintenanceSilenceWindowUpdate,
) -> MaintenanceSilenceWindow:
    if payload.name is not None:
        row.name = sanitize_public_payload(payload.name.strip())
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.start_at is not None and payload.end_at is not None:
        row.start_at = payload.start_at
        row.end_at = payload.end_at
    if payload.scope is not None:
        row.scope_type = payload.scope.type.value
        row.namespace = payload.scope.namespace
        row.resource_kind = payload.scope.resource_kind
        row.label_selector = payload.scope.label_selector
    if "note" in payload.model_fields_set:
        row.note = sanitize_public_payload(payload.note) if payload.note else None
    row.updated_at = utcnow()
    session.commit()
    session.refresh(row)
    return window_from_model(row)


def delete_window(session: Session, row: MaintenanceSilenceWindowModel) -> None:
    session.delete(row)
    session.commit()


def find_matching_window(
    session: Session,
    *,
    issue: IssueModel,
    now: datetime | None = None,
) -> MaintenanceSilenceWindowModel | None:
    current = now or utcnow()
    candidates = session.scalars(
        select(MaintenanceSilenceWindowModel)
        .where(
            MaintenanceSilenceWindowModel.enabled.is_(True),
            MaintenanceSilenceWindowModel.start_at <= current,
            MaintenanceSilenceWindowModel.end_at > current,
        )
        .order_by(MaintenanceSilenceWindowModel.end_at, MaintenanceSilenceWindowModel.id)
    ).all()
    for window in candidates:
        if window_matches_issue(window, issue):
            return window
    return None


def list_expired_pending_summary_windows(
    session: Session,
    *,
    now: datetime | None = None,
) -> list[MaintenanceSilenceWindowModel]:
    current = now or utcnow()
    return list(
        session.scalars(
            select(MaintenanceSilenceWindowModel)
            .where(
                MaintenanceSilenceWindowModel.pending_summary_recorded_at.is_not(None),
                MaintenanceSilenceWindowModel.end_at <= current,
            )
            .order_by(MaintenanceSilenceWindowModel.end_at, MaintenanceSilenceWindowModel.id)
        ).all()
    )


def list_open_issues_for_window(
    session: Session,
    window: MaintenanceSilenceWindowModel,
    *,
    limit: int = 20,
) -> list[IssueModel]:
    candidates = session.scalars(
        select(IssueModel)
        .where(IssueModel.status == "open")
        .order_by(desc(IssueModel.last_seen_at), desc(IssueModel.id))
        .limit(500)
    ).all()
    return [issue for issue in candidates if window_matches_issue(window, issue)][:limit]


def clear_pending_summary_recorded(
    session: Session,
    row: MaintenanceSilenceWindowModel,
) -> None:
    row.pending_summary_recorded_at = None
    row.updated_at = utcnow()
    session.commit()


def mark_pending_summary_recorded(
    session: Session,
    row: MaintenanceSilenceWindowModel,
    *,
    occurred_at: datetime | None = None,
) -> None:
    if row.pending_summary_recorded_at is None:
        row.pending_summary_recorded_at = occurred_at or utcnow()
        row.updated_at = utcnow()
        session.commit()


def window_matches_issue(window: MaintenanceSilenceWindowModel, issue: IssueModel) -> bool:
    scope_type = window.scope_type
    if scope_type == MaintenanceSilenceScopeType.global_scope.value:
        return True
    if scope_type == MaintenanceSilenceScopeType.namespace.value:
        return bool(window.namespace) and issue.resource_namespace == window.namespace
    if scope_type == MaintenanceSilenceScopeType.resource_kind.value:
        return bool(window.resource_kind) and issue.resource_kind.casefold() == window.resource_kind.casefold()
    if scope_type == MaintenanceSilenceScopeType.label_selector.value:
        return _label_selector_matches_issue(window.label_selector or "", issue)
    return False


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _label_selector_matches_issue(selector: str, issue: IssueModel) -> bool:
    requirements = _parse_label_selector(selector)
    if not requirements:
        return False
    labels = _issue_labels(issue)
    return all(labels.get(key) == value for key, value in requirements.items())


def _parse_label_selector(selector: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_item in selector.split(","):
        item = raw_item.strip()
        if not item or "=" not in item:
            return {}
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            return {}
        result[key] = value
    return result


def _issue_labels(issue: IssueModel) -> dict[str, str]:
    labels: dict[str, str] = {}
    for item in issue.evidence or []:
        if not isinstance(item, dict):
            continue
        facts = item.get("facts")
        if isinstance(facts, dict):
            _merge_labels(labels, facts.get("labels"))
            _merge_labels(labels, facts.get("resource_labels"))
    return labels


def _merge_labels(target: dict[str, str], value: Any) -> None:
    if not isinstance(value, dict):
        return
    for key, item in value.items():
        if isinstance(key, str) and isinstance(item, (str, int, float, bool)):
            target[key] = str(item)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
