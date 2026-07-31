from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock, RLock

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.models import InspectionPlan as InspectionPlanModel
from app.models import InspectionRecord, InspectionRun as InspectionRunModel
from app.schemas.v1_1 import (
    ComponentState,
    InspectionPlanScope,
    InspectionPlanScopeType,
    InspectionRun,
    InspectionRunStatus,
    InspectionScope,
    InspectionScopeType,
    InspectionTrigger,
    PlanInterval,
    PlanSchedule,
    SystemComponentStatus,
)
from app.security.lifespan import register_lifespan_hook
from app.services import inspection_plan_service, notification_service, retention_service, settings_service
from app.services.inspection_service import sanitize_persistence_payload
from app.services.inspection_run_service import execute_inspection, run_from_model


class PlanAlreadyRunningError(RuntimeError):
    pass


_LOCK_GUARD = RLock()
_PLAN_LOCKS: dict[int, Lock] = {}


def enqueue_plan(app, plan_id: int) -> InspectionRun:
    lock = _plan_lock(plan_id)
    if not lock.acquire(blocking=False):
        raise PlanAlreadyRunningError("该巡检计划正在执行")
    try:
        with app.state.session_factory() as session:
            plan = session.get(InspectionPlanModel, plan_id)
            if plan is None:
                raise LookupError("巡检计划不存在")
            in_flight = session.scalar(
                select(InspectionRunModel.id).where(
                    InspectionRunModel.plan_id == plan_id,
                    InspectionRunModel.status.in_(
                        [
                            InspectionRunStatus.queued.value,
                            InspectionRunStatus.running.value,
                        ]
                    ),
                )
            )
            if in_flight is not None:
                raise PlanAlreadyRunningError("该巡检计划正在执行")
            record = InspectionRecord(
                inspection_type="scheduled",
                request_payload={"plan_id": plan.id, "scope": plan.scope},
                result_payload={"status": "queued"},
                summary_status="queued",
            )
            session.add(record)
            scope = _inspection_scope(InspectionPlanScope.model_validate(plan.scope))
            queued = InspectionRunModel(
                plan_id=plan.id,
                inspection_record_id=None,
                trigger=InspectionTrigger.scheduled,
                status=InspectionRunStatus.queued.value,
                scope=scope.model_dump(mode="json"),
                coverage=[],
            )
            session.add(queued)
            session.flush()
            queued.inspection_record_id = record.id
            session.commit()
            session.refresh(queued)
            result = run_from_model(session, queued)
    finally:
        lock.release()
    _schedule_queued_run(app, result.id)
    return result


def execute_queued_run(app, run_id: int) -> InspectionRun:
    with app.state.session_factory() as lookup:
        queued = lookup.get(InspectionRunModel, run_id)
        if queued is None:
            raise LookupError("待执行的巡检记录不存在")
        if queued.status != InspectionRunStatus.queued.value:
            return run_from_model(lookup, queued)
        plan_id = queued.plan_id
    if plan_id is None:
        raise LookupError("queued 巡检缺少计划")
    lock = _plan_lock(plan_id)
    if not lock.acquire(blocking=False):
        raise PlanAlreadyRunningError("该巡检计划正在执行")
    try:
        with app.state.session_factory() as session:
            queued = session.get(InspectionRunModel, run_id)
            if queued is None:
                raise LookupError("待执行的巡检记录不存在")
            if queued.status != InspectionRunStatus.queued.value:
                return run_from_model(session, queued)
            other_running = session.scalar(
                select(InspectionRunModel.id).where(
                    InspectionRunModel.plan_id == plan_id,
                    InspectionRunModel.status == InspectionRunStatus.running.value,
                    InspectionRunModel.id != run_id,
                )
            )
            if other_running is not None:
                raise PlanAlreadyRunningError("该巡检计划正在执行")
            plan = session.get(InspectionPlanModel, plan_id)
            if plan is None:
                raise LookupError("巡检计划不存在")
            scope = InspectionScope.model_validate(queued.scope)
            cluster_id = settings_service.get_effective_cluster_id(session, app.state.settings)
            run, lifecycle = execute_inspection(
                session,
                provider=app.state.provider,
                cluster_id=cluster_id,
                scope=scope,
                trigger=InspectionTrigger.scheduled,
                plan_id=plan_id,
                inspection_record_id=queued.inspection_record_id,
                registry=app.state.component_status_registry,
                existing_run_id=run_id,
                include_template_matching=plan.include_template_matching,
                provider_mode=app.state.settings.provider_mode,
            )
            record = session.get(InspectionRecord, queued.inspection_record_id)
            if record is not None:
                record.result_payload = sanitize_persistence_payload(
                    run.model_dump(mode="json")
                )
                record.summary_status = run.status.value
                session.commit()
            plan = session.get(InspectionPlanModel, plan_id)
            if plan is not None:
                inspection_plan_service.mark_plan_after_run(
                    session,
                    plan,
                    status=run.status.value,
                    finished_at=run.finished_at or datetime.now(timezone.utc),
                )
            notification_service.dispatch_lifecycle_changes(
                session,
                plan_id=plan_id,
                changes=lifecycle.changes,
                settings=app.state.settings,
                registry=app.state.component_status_registry,
            )
            if run.status == InspectionRunStatus.failed:
                row = session.get(InspectionRunModel, run.id)
                if row is not None:
                    notification_service.dispatch_inspection_failure(
                        session,
                        plan_id=plan_id,
                        run=row,
                        settings=app.state.settings,
                        registry=app.state.component_status_registry,
                    )
            return run
    finally:
        lock.release()


def sync_plan_job(app, plan_id: int) -> None:
    scheduler: BackgroundScheduler | None = getattr(app.state, "inspection_scheduler", None)
    if scheduler is None or not scheduler.running:
        return
    with app.state.session_factory() as session:
        plan = session.get(InspectionPlanModel, plan_id)
        if plan is None or not plan.enabled:
            remove_plan_job(app, plan_id)
            return
        _add_or_replace_job(scheduler, app, plan)


def remove_plan_job(app, plan_id: int) -> None:
    scheduler: BackgroundScheduler | None = getattr(app.state, "inspection_scheduler", None)
    if scheduler is None:
        return
    job = scheduler.get_job(_job_id(plan_id))
    if job is not None:
        scheduler.remove_job(job.id)


def _scheduled_execute(app, plan_id: int) -> None:
    try:
        enqueue_plan(app, plan_id)
    except (LookupError, PlanAlreadyRunningError):
        return
    except Exception:
        registry = app.state.component_status_registry
        registry.update(
            "scheduler",
            SystemComponentStatus(
                state=ComponentState.degraded,
                message="调度任务执行发生受控失败",
                checked_at=datetime.now(timezone.utc),
                details={"plan_id": plan_id},
            ),
        )


def _start_scheduler(app) -> None:
    scheduler = BackgroundScheduler(timezone=timezone.utc)
    now = datetime.now(timezone.utc)
    with app.state.session_factory() as session:
        _mark_interrupted_runs(session, now)
        _restore_last_inspection_registry(
            session,
            app.state.component_status_registry,
        )
        plans = session.scalars(
            select(InspectionPlanModel).where(InspectionPlanModel.enabled.is_(True))
        ).all()
        for plan in plans:
            _add_or_replace_job(scheduler, app, plan, now=now)
        queued_runs = session.scalars(
            select(InspectionRunModel).where(
                InspectionRunModel.status == InspectionRunStatus.queued.value
            )
        ).all()
        for queued in queued_runs:
            _add_queued_job(
                scheduler,
                app,
                queued.id,
                run_at=now + timedelta(milliseconds=100),
            )
        if (
            app.state.component_status_registry.get("notifications").state
            == ComponentState.unavailable
        ):
            notification_service.refresh_notification_registry(
                session,
                app.state.component_status_registry,
            )
    scheduler.add_job(
        _heartbeat,
        trigger=IntervalTrigger(seconds=30),
        args=[app],
        id="v1.1:scheduler-heartbeat",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _run_retention,
        trigger=CronTrigger(hour=3, minute=0, timezone=timezone.utc),
        args=[app],
        id="v1.1:retention",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    app.state.inspection_scheduler = scheduler
    scheduler.start()
    _heartbeat(app)


def _stop_scheduler(app) -> None:
    scheduler: BackgroundScheduler | None = getattr(app.state, "inspection_scheduler", None)
    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=False)
    app.state.inspection_scheduler = None


def _add_or_replace_job(
    scheduler: BackgroundScheduler,
    app,
    plan: InspectionPlanModel,
    *,
    now: datetime | None = None,
) -> None:
    schedule = PlanSchedule.model_validate(plan.schedule)
    trigger = _trigger(schedule)
    next_run_time = _utc(plan.next_run_at)
    current = now or datetime.now(timezone.utc)
    if next_run_time is not None and next_run_time <= current:
        next_run_time = current
    scheduler.add_job(
        _scheduled_execute,
        trigger=trigger,
        args=[app, plan.id],
        id=_job_id(plan.id),
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
        next_run_time=next_run_time,
    )


def _schedule_queued_run(app, run_id: int) -> None:
    scheduler: BackgroundScheduler | None = getattr(app.state, "inspection_scheduler", None)
    if scheduler is None or not scheduler.running:
        return
    _add_queued_job(
        scheduler,
        app,
        run_id,
        run_at=datetime.now(timezone.utc),
    )


def _add_queued_job(
    scheduler: BackgroundScheduler,
    app,
    run_id: int,
    *,
    run_at: datetime,
) -> None:
    scheduler.add_job(
        _execute_queued_job,
        trigger=DateTrigger(run_date=run_at, timezone=timezone.utc),
        args=[app, run_id],
        id=f"v1.1:queued-run:{run_id}",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,
    )


def _execute_queued_job(app, run_id: int) -> None:
    try:
        execute_queued_run(app, run_id)
    except PlanAlreadyRunningError:
        scheduler: BackgroundScheduler | None = getattr(app.state, "inspection_scheduler", None)
        if scheduler is not None and scheduler.running:
            _add_queued_job(
                scheduler,
                app,
                run_id,
                run_at=datetime.now(timezone.utc) + timedelta(seconds=1),
            )
    except Exception:
        _fail_queued_run(app, run_id)


def _fail_queued_run(app, run_id: int) -> None:
    now = datetime.now(timezone.utc)
    with app.state.session_factory() as session:
        row = session.get(InspectionRunModel, run_id)
        if row is None:
            return
        if row.status in {
            InspectionRunStatus.queued.value,
            InspectionRunStatus.running.value,
        }:
            row.status = InspectionRunStatus.failed.value
            row.started_at = row.started_at or now
            row.finished_at = now
            row.error_code = "QUEUED_INSPECTION_FAILED"
            row.error_message = "后台执行器无法接管 queued 巡检"
        record = (
            session.get(InspectionRecord, row.inspection_record_id)
            if row.inspection_record_id
            else None
        )
        if record is not None and record.summary_status in {"queued", "running"}:
            record.summary_status = row.status
            record.result_payload = {
                "run_id": row.id,
                "status": row.status,
                "error_code": row.error_code,
                "error_message": row.error_message,
            }
        session.commit()


def _trigger(schedule: PlanSchedule):
    minutes = {
        PlanInterval.minutes_5: 5,
        PlanInterval.minutes_10: 10,
        PlanInterval.minutes_30: 30,
        PlanInterval.minutes_60: 60,
    }
    if schedule.interval in minutes:
        return IntervalTrigger(minutes=minutes[schedule.interval], timezone=timezone.utc)
    hour, minute = (int(item) for item in (schedule.daily_at or "00:00").split(":"))
    return CronTrigger(hour=hour, minute=minute, timezone=schedule.timezone)


def _mark_interrupted_runs(session, now: datetime) -> None:
    rows = session.scalars(
        select(InspectionRunModel).where(
            InspectionRunModel.status == InspectionRunStatus.running.value
        )
    ).all()
    for row in rows:
        row.status = InspectionRunStatus.failed.value
        row.finished_at = now
        row.error_code = "INSPECTION_INTERRUPTED"
        row.error_message = "应用重启时发现未完成的巡检，已标记为中断"
        started = _utc(row.started_at) or now
        row.duration_ms = max(0, int((now - started).total_seconds() * 1000))
    session.commit()


def _restore_last_inspection_registry(session, registry) -> None:
    row = session.scalar(
        select(InspectionRunModel)
        .order_by(
            InspectionRunModel.finished_at.desc().nulls_last(),
            InspectionRunModel.created_at.desc(),
            InspectionRunModel.id.desc(),
        )
        .limit(1)
    )
    if row is None:
        return
    states = {
        InspectionRunStatus.succeeded.value: ComponentState.ok,
        InspectionRunStatus.partial.value: ComponentState.degraded,
        InspectionRunStatus.failed.value: ComponentState.failed,
        InspectionRunStatus.queued.value: ComponentState.degraded,
        InspectionRunStatus.running.value: ComponentState.degraded,
    }
    registry.update(
        "last_inspection",
        SystemComponentStatus(
            state=states.get(row.status, ComponentState.degraded),
            message=f"最近巡检状态：{row.status}",
            checked_at=_utc(row.finished_at or row.created_at)
            or datetime.now(timezone.utc),
            details={
                "run_id": row.id,
                "status": row.status,
                "restored_from_database": True,
            },
        ),
    )


def _run_retention(app) -> None:
    with app.state.session_factory() as session:
        retention_service.cleanup_expired_data(session)


def _heartbeat(app) -> None:
    app.state.component_status_registry.update(
        "scheduler",
        SystemComponentStatus(
            state=ComponentState.ok,
            message="单实例巡检调度器运行中",
            checked_at=datetime.now(timezone.utc),
            details={},
        ),
    )


def _inspection_scope(plan_scope: InspectionPlanScope) -> InspectionScope:
    if plan_scope.type == InspectionPlanScopeType.global_:
        return InspectionScope(type=InspectionScopeType.cluster)
    return InspectionScope(
        type=InspectionScopeType.namespace,
        namespaces=plan_scope.namespaces,
    )


def _plan_lock(plan_id: int) -> Lock:
    with _LOCK_GUARD:
        return _PLAN_LOCKS.setdefault(plan_id, Lock())


def _job_id(plan_id: int) -> str:
    return f"v1.1:inspection-plan:{plan_id}"


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


register_lifespan_hook(
    name="v1.1-inspection-scheduler",
    start=_start_scheduler,
    stop=_stop_scheduler,
)
