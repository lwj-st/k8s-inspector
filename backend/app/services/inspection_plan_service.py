from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import InspectionPlan as InspectionPlanModel
from app.models import InspectionRun as InspectionRunModel
from app.models import NotificationChannel as NotificationChannelModel
from app.models.v1_1 import inspection_plan_channels
from app.schemas.v1_1 import (
    InspectionPlan,
    InspectionPlanCreate,
    InspectionPlanUpdate,
    Page,
    PlanInterval,
    PlanSchedule,
)


class PlanConflictError(ValueError):
    pass


class PlanReferenceError(ValueError):
    pass


def plan_from_model(session: Session, row: InspectionPlanModel) -> InspectionPlan:
    channel_ids = list(
        session.scalars(
            select(inspection_plan_channels.c.channel_id)
            .where(inspection_plan_channels.c.plan_id == row.id)
            .order_by(inspection_plan_channels.c.channel_id)
        ).all()
    )
    return InspectionPlan(
        id=row.id,
        name=row.name,
        enabled=row.enabled,
        scope=row.scope,
        schedule=row.schedule,
        include_template_matching=row.include_template_matching,
        notification_channel_ids=channel_ids,
        last_run_at=_utc(row.last_run_at),
        next_run_at=_utc(row.next_run_at),
        last_run_status=row.last_run_status,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


def list_plans(session: Session, *, page: int, page_size: int) -> Page[InspectionPlan]:
    total = int(session.scalar(select(func.count(InspectionPlanModel.id))) or 0)
    rows = session.scalars(
        select(InspectionPlanModel)
        .order_by(desc(InspectionPlanModel.created_at), desc(InspectionPlanModel.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page[InspectionPlan](
        items=[plan_from_model(session, row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_plan(session: Session, plan_id: int) -> InspectionPlanModel | None:
    return session.get(InspectionPlanModel, plan_id)


def create_plan(
    session: Session,
    payload: InspectionPlanCreate,
    *,
    now: datetime | None = None,
) -> InspectionPlan:
    _validate_channels(session, payload.notification_channel_ids)
    current = now or datetime.now(timezone.utc)
    row = InspectionPlanModel(
        name=payload.name.strip(),
        normalized_name=_normalize_name(payload.name),
        enabled=payload.enabled,
        scope=payload.scope.model_dump(mode="json"),
        schedule=payload.schedule.model_dump(mode="json"),
        include_template_matching=payload.include_template_matching,
        next_run_at=next_run_at(payload.schedule, after=current) if payload.enabled else None,
        created_at=current,
        updated_at=current,
    )
    session.add(row)
    try:
        session.flush()
        _replace_channels(session, row.id, payload.notification_channel_ids)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise PlanConflictError("巡检计划名称已存在") from exc
    session.refresh(row)
    return plan_from_model(session, row)


def update_plan(
    session: Session,
    row: InspectionPlanModel,
    payload: InspectionPlanUpdate,
    *,
    now: datetime | None = None,
) -> InspectionPlan:
    current = now or datetime.now(timezone.utc)
    if payload.notification_channel_ids is not None:
        _validate_channels(session, payload.notification_channel_ids)
    if payload.name is not None:
        row.name = payload.name.strip()
        row.normalized_name = _normalize_name(payload.name)
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.scope is not None:
        row.scope = payload.scope.model_dump(mode="json")
    if payload.schedule is not None:
        row.schedule = payload.schedule.model_dump(mode="json")
    if payload.include_template_matching is not None:
        row.include_template_matching = payload.include_template_matching
    row.updated_at = current
    if row.enabled:
        row.next_run_at = next_run_at(
            PlanSchedule.model_validate(row.schedule),
            after=current,
        )
    else:
        row.next_run_at = None
    try:
        session.flush()
        if payload.notification_channel_ids is not None:
            _replace_channels(session, row.id, payload.notification_channel_ids)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise PlanConflictError("巡检计划名称已存在") from exc
    session.refresh(row)
    return plan_from_model(session, row)


def delete_plan(session: Session, row: InspectionPlanModel) -> None:
    session.execute(
        update(InspectionRunModel)
        .where(InspectionRunModel.plan_id == row.id)
        .values(plan_id=None)
    )
    session.execute(
        delete(inspection_plan_channels).where(inspection_plan_channels.c.plan_id == row.id)
    )
    session.delete(row)
    session.commit()


def next_run_at(schedule: PlanSchedule, *, after: datetime) -> datetime:
    current = _utc(after) or after
    interval_minutes = {
        PlanInterval.minutes_5: 5,
        PlanInterval.minutes_10: 10,
        PlanInterval.minutes_30: 30,
        PlanInterval.minutes_60: 60,
    }
    if schedule.interval in interval_minutes:
        return current + timedelta(minutes=interval_minutes[schedule.interval])

    local_zone = ZoneInfo(schedule.timezone)
    local_now = current.astimezone(local_zone)
    hour, minute = (int(item) for item in (schedule.daily_at or "00:00").split(":"))
    candidate = datetime.combine(local_now.date(), time(hour, minute), tzinfo=local_zone)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def mark_plan_after_run(
    session: Session,
    row: InspectionPlanModel,
    *,
    status: str,
    finished_at: datetime,
) -> None:
    row.last_run_at = finished_at
    row.last_run_status = status
    row.next_run_at = (
        next_run_at(PlanSchedule.model_validate(row.schedule), after=finished_at)
        if row.enabled
        else None
    )
    row.updated_at = finished_at
    session.commit()


def _validate_channels(session: Session, channel_ids: list[int]) -> None:
    if not channel_ids:
        return
    rows = session.scalars(
        select(NotificationChannelModel).where(
            NotificationChannelModel.id.in_(channel_ids),
            NotificationChannelModel.deleted_at.is_(None),
        )
    ).all()
    found = {row.id for row in rows}
    missing = sorted(set(channel_ids) - found)
    if missing:
        raise PlanReferenceError("通知渠道不存在或已删除")


def _replace_channels(session: Session, plan_id: int, channel_ids: list[int]) -> None:
    session.execute(
        delete(inspection_plan_channels).where(inspection_plan_channels.c.plan_id == plan_id)
    )
    for channel_id in channel_ids:
        session.execute(
            inspection_plan_channels.insert().values(plan_id=plan_id, channel_id=channel_id)
        )


def _normalize_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
