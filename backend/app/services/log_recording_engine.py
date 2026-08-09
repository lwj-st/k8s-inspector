from __future__ import annotations

from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.models import LogRecording
from app.schemas.log_recording import (
    LogRecordingDurationSource,
    LogRecordingStatus,
    LogRecordingStopReason,
)
from app.security.lifespan import register_lifespan_hook
from app.services import log_recording_service


def schedule_auto_stop(app, recording_id: int) -> None:
    scheduler: BackgroundScheduler | None = getattr(app.state, "log_recording_scheduler", None)
    if scheduler is None or not scheduler.running:
        return
    with app.state.session_factory() as session:
        row = session.get(LogRecording, recording_id)
        if row is None or row.status != LogRecordingStatus.recording.value:
            return
        _add_auto_stop_job(scheduler, app, row)
        _add_collection_job(scheduler, app, row.id)


def remove_auto_stop(app, recording_id: int) -> None:
    scheduler: BackgroundScheduler | None = getattr(app.state, "log_recording_scheduler", None)
    if scheduler is None:
        return
    job = scheduler.get_job(_job_id(recording_id))
    if job is not None:
        scheduler.remove_job(job.id)
    collection_job = scheduler.get_job(_collection_job_id(recording_id))
    if collection_job is not None:
        scheduler.remove_job(collection_job.id)


def auto_stop_recording(app, recording_id: int) -> None:
    now = datetime.now(timezone.utc)
    with app.state.session_factory() as session:
        row = session.get(LogRecording, recording_id)
        if row is None or row.status != LogRecordingStatus.recording.value:
            return
        row.status = LogRecordingStatus.auto_completed.value
        row.ended_at = now
        row.stop_reason = _auto_stop_reason(row.duration_source)
        row.updated_at = now
        session.commit()
    remove_auto_stop(app, recording_id)


def auto_stop_due_recordings(app) -> int:
    now = datetime.now(timezone.utc)
    stopped = 0
    with app.state.session_factory() as session:
        rows = session.scalars(
            select(LogRecording).where(
                LogRecording.status == LogRecordingStatus.recording.value,
                LogRecording.planned_end_at <= now,
            )
        ).all()
        stopped_ids: list[int] = []
        for row in rows:
            row.status = LogRecordingStatus.auto_completed.value
            row.ended_at = now
            row.stop_reason = _auto_stop_reason(row.duration_source)
            row.updated_at = now
            stopped_ids.append(row.id)
            stopped += 1
        session.commit()
    for recording_id in stopped_ids:
        remove_auto_stop(app, recording_id)
    return stopped


def collect_recording_once(app, recording_id: int) -> None:
    with app.state.session_factory() as session:
        row = session.get(LogRecording, recording_id)
        if row is None or row.status != LogRecordingStatus.recording.value:
            remove_auto_stop(app, recording_id)
            return
        try:
            result = log_recording_service.collect_recording_once(
                session,
                app.state.provider,
                recording_id,
            )
        except Exception:
            remove_auto_stop(app, recording_id)
            return
        if result.status != LogRecordingStatus.recording:
            remove_auto_stop(app, recording_id)


def mark_interrupted_recordings(session, now: datetime | None = None) -> int:
    current = now or datetime.now(timezone.utc)
    rows = session.scalars(
        select(LogRecording).where(LogRecording.status == LogRecordingStatus.recording.value)
    ).all()
    for row in rows:
        row.status = LogRecordingStatus.failed.value
        row.ended_at = current
        row.stop_reason = LogRecordingStopReason.recovery_failed_after_restart.value
        row.updated_at = current
    session.commit()
    return len(rows)


def _start_engine(app) -> None:
    scheduler = BackgroundScheduler(timezone=timezone.utc)
    with app.state.session_factory() as session:
        mark_interrupted_recordings(session)
    scheduler.add_job(
        auto_stop_due_recordings,
        trigger=IntervalTrigger(seconds=10, timezone=timezone.utc),
        args=[app],
        id="v1.3:log-recordings:auto-stop-due",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    app.state.log_recording_scheduler = scheduler
    scheduler.start()
    auto_stop_due_recordings(app)


def _stop_engine(app) -> None:
    scheduler: BackgroundScheduler | None = getattr(app.state, "log_recording_scheduler", None)
    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=False)
    app.state.log_recording_scheduler = None


def _add_auto_stop_job(
    scheduler: BackgroundScheduler,
    app,
    row: LogRecording,
) -> None:
    run_at = _utc(row.planned_end_at)
    current = datetime.now(timezone.utc)
    if run_at is None or run_at <= current:
        run_at = current
    scheduler.add_job(
        auto_stop_recording,
        trigger=DateTrigger(run_date=run_at, timezone=timezone.utc),
        args=[app, row.id],
        id=_job_id(row.id),
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,
    )


def _add_collection_job(
    scheduler: BackgroundScheduler,
    app,
    recording_id: int,
) -> None:
    scheduler.add_job(
        collect_recording_once,
        trigger=IntervalTrigger(seconds=5, timezone=timezone.utc),
        args=[app, recording_id],
        id=_collection_job_id(recording_id),
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),
    )


def _auto_stop_reason(duration_source: str) -> str:
    if duration_source == LogRecordingDurationSource.system_default.value:
        return LogRecordingStopReason.system_default_timeout.value
    return LogRecordingStopReason.selected_duration_timeout.value


def _job_id(recording_id: int) -> str:
    return f"v1.3:log-recording:auto-stop:{recording_id}"


def _collection_job_id(recording_id: int) -> str:
    return f"v1.3:log-recording:collect:{recording_id}"


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


register_lifespan_hook(
    name="v1.3-log-recording-engine",
    start=_start_engine,
    stop=_stop_engine,
)
