from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Event, Lock, Thread
from time import sleep

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.models import LogRecording
from app.providers.base import LogRecordingPodSnapshot, LogRecordingSnapshot
from app.schemas.log_recording import (
    LogRecordingDurationSource,
    LogRecordingStatus,
    LogRecordingStopReason,
)
from app.security.lifespan import register_lifespan_hook
from app.services import log_recording_service


@dataclass
class RecordingStreamHandle:
    stop_event: Event
    manager_thread: Thread
    worker_threads: dict[tuple[str, str, str], Thread] = field(default_factory=dict)


_STREAM_LOCK = Lock()
_STREAMS: dict[int, RecordingStreamHandle] = {}


def schedule_auto_stop(app, recording_id: int) -> None:
    scheduler: BackgroundScheduler | None = getattr(app.state, "log_recording_scheduler", None)
    if scheduler is None or not scheduler.running:
        return
    with app.state.session_factory() as session:
        row = session.get(LogRecording, recording_id)
        if row is None or row.status != LogRecordingStatus.recording.value:
            return
        _add_auto_stop_job(scheduler, app, row)
        _start_streaming(app, row.id)


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
    _stop_streaming(recording_id)


def auto_stop_recording(app, recording_id: int) -> None:
    now = datetime.now(timezone.utc)
    with app.state.session_factory() as session:
        _collect_before_completion(session, app, recording_id)
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
        recording_ids = session.scalars(
            select(LogRecording.id).where(
                LogRecording.status == LogRecordingStatus.recording.value,
                LogRecording.planned_end_at <= now,
            )
        ).all()
        stopped_ids: list[int] = []
        for recording_id in recording_ids:
            _collect_before_completion(session, app, recording_id)
            row = session.get(LogRecording, recording_id)
            if row is None or row.status != LogRecordingStatus.recording.value:
                continue
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


def _collect_before_completion(session, app, recording_id: int) -> None:
    try:
        log_recording_service.collect_recording_once(
            session,
            app.state.provider,
            recording_id,
        )
    except Exception:
        pass


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
    _stop_all_streams()


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


def _start_streaming(app, recording_id: int) -> None:
    with _STREAM_LOCK:
        existing = _STREAMS.get(recording_id)
        if existing is not None and existing.manager_thread.is_alive():
            return
        stop_event = Event()
        handle = RecordingStreamHandle(
            stop_event=stop_event,
            manager_thread=Thread(
                target=_stream_recording_manager,
                args=(app, recording_id, stop_event),
                name=f"log-recording-stream-manager-{recording_id}",
                daemon=True,
            ),
        )
        _STREAMS[recording_id] = handle
        handle.manager_thread.start()


def _stop_streaming(recording_id: int) -> None:
    with _STREAM_LOCK:
        handle = _STREAMS.pop(recording_id, None)
    if handle is not None:
        handle.stop_event.set()


def _stop_all_streams() -> None:
    with _STREAM_LOCK:
        handles = list(_STREAMS.values())
        _STREAMS.clear()
    for handle in handles:
        handle.stop_event.set()


def _stream_recording_manager(app, recording_id: int, stop_event: Event) -> None:
    while not stop_event.is_set():
        with app.state.session_factory() as session:
            row = session.get(LogRecording, recording_id)
            if row is None or row.status != LogRecordingStatus.recording.value:
                stop_event.set()
                break
            policy = log_recording_service._policy(session)
            namespaces = log_recording_service._recording_namespaces(row)
            since_time = log_recording_service._ensure_utc(
                log_recording_service._last_collection_time(session, row) or row.started_at
            )
        for namespace in namespaces:
            if stop_event.is_set():
                break
            try:
                snapshot = app.state.provider.discover_log_recording_pods(
                    namespace,
                    max_pods=policy.max_namespace_pods,
                )
            except Exception:
                continue
            with app.state.session_factory() as session:
                result = log_recording_service.ingest_recording_snapshot(session, recording_id, snapshot)
                if result.status != LogRecordingStatus.recording:
                    stop_event.set()
                    break
            _ensure_container_streams(app, recording_id, snapshot, since_time, stop_event)
        for _ in range(15):
            if stop_event.is_set():
                break
            sleep(1)
    _stop_streaming(recording_id)


def _ensure_container_streams(
    app,
    recording_id: int,
    snapshot: LogRecordingSnapshot,
    since_time: datetime,
    stop_event: Event,
) -> None:
    with _STREAM_LOCK:
        handle = _STREAMS.get(recording_id)
        if handle is None:
            return
        for pod in snapshot.pods:
            for container_name in pod.container_names:
                key = (snapshot.namespace, pod.pod_name, container_name)
                current = handle.worker_threads.get(key)
                if current is not None and current.is_alive():
                    continue
                worker = Thread(
                    target=_stream_container_worker,
                    args=(app, recording_id, snapshot.namespace, pod, container_name, since_time, stop_event),
                    name=f"log-recording-stream-{recording_id}-{pod.pod_name}-{container_name}",
                    daemon=True,
                )
                handle.worker_threads[key] = worker
                worker.start()


def _stream_container_worker(
    app,
    recording_id: int,
    namespace: str,
    pod: LogRecordingPodSnapshot,
    container_name: str,
    since_time: datetime,
    stop_event: Event,
) -> None:
    try:
        for entry in app.state.provider.stream_log_recording_entries(
            namespace,
            pod_uid=pod.pod_uid,
            pod_name=pod.pod_name,
            container_name=container_name,
            since_time=since_time,
        ):
            if stop_event.is_set():
                break
            snapshot = LogRecordingSnapshot(
                namespace=namespace,
                collected_at=entry.collected_at,
                pods=[
                    LogRecordingPodSnapshot(
                        namespace=namespace,
                        pod_uid=pod.pod_uid,
                        pod_name=pod.pod_name,
                        node_name=pod.node_name,
                        owner_kind=pod.owner_kind,
                        owner_name=pod.owner_name,
                        container_names=pod.container_names,
                        entries=[entry],
                    )
                ],
                total_bytes=len(entry.text.encode("utf-8")),
            )
            with app.state.session_factory() as session:
                result = log_recording_service.ingest_recording_snapshot(session, recording_id, snapshot)
                if result.status != LogRecordingStatus.recording:
                    stop_event.set()
                    break
    except Exception:
        return


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
