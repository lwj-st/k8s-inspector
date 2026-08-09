from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from fnmatch import fnmatchcase
from threading import Lock, RLock

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from app.engine.matcher import match_template
from app.models import FaultTemplate, LogRecording, LogRecordingLine, LogRecordingPod, LogRecordingTemplateMatch
from app.providers.base import InspectionProvider, LogPodLimitExceededError, LogRecordingSnapshot
from app.schemas.log_recording import (
    LogRecordingCreate,
    LogRecordingDurationSource,
    LogRecordingLineRead,
    LogRecordingLogPage,
    LogRecordingPodRead,
    LogRecordingPreview,
    LogRecordingRead,
    LogRecordingStatus,
    LogRecordingStopReason,
    LogRecordingStorageUsage,
    LogRecordingTemplateMatchRead,
    LogRecordingUpdate,
    LogRecordingViewMode,
)
from app.schemas.v1_1 import Page, ReproductionLogPolicySettings
from app.services import discovery_service, keyword_service, settings_service


DEFAULT_REDACTION_RULES: tuple[tuple[str, str], ...] = (
    (r"(?i)(Authorization:\s*Bearer\s+)[^\s,;]+", r"\1***"),
    (r"(?i)(Authorization:\s*(?:Basic|Digest|Token)\s+)[^\s,;]+", r"\1***"),
    (r"(?i)(Cookie:\s*)[^\r\n]+", r"\1***"),
    (r"(?i)\b(token|password|secret|access_key|private_key)(\s*[:=]\s*)[^\s&;,\"]+", r"\1\2***"),
    (r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "***"),
    (r"(?<!\d)1[3-9]\d{9}(?!\d)", "***"),
    (r"(?<!\d)\d{17}[\dXx](?!\d)", "***"),
)

FINGERPRINT_NORMALIZERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b", re.IGNORECASE), "<time>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.IGNORECASE), "<id>"),
    (re.compile(r"\b(?:trace|request|req|span)[-_ ]?id[=:]\s*[A-Za-z0-9_.:\-]+\b", re.IGNORECASE), "<id>"),
    (re.compile(r"\b[0-9a-f]{16,}\b", re.IGNORECASE), "<hex>"),
    (re.compile(r"\b\d+\b"), "<num>"),
    (re.compile(r"\s+"), " "),
)


class LogRecordingNotFoundError(ValueError):
    pass


class LogRecordingAlreadyStoppedError(ValueError):
    pass


class LogRecordingStorageFullError(ValueError):
    pass


class LogRecordingScopeTooLargeError(ValueError):
    def __init__(self, pod_count: int, limit: int):
        self.pod_count = pod_count
        self.limit = limit
        super().__init__(f"名称空间 Pod 数 {pod_count} 超过复现日志上限 {limit}")


class LogRecordingCollectionFailedError(RuntimeError):
    pass


class LogRecordingDurationError(ValueError):
    pass


_LOCK_GUARD = RLock()
_COLLECTION_LOCKS: dict[int, Lock] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _policy(session: Session) -> ReproductionLogPolicySettings:
    settings = settings_service.get_settings(session)
    policy = settings_service.policy_with_builtin_required_components(settings.inspection_policy)
    return ReproductionLogPolicySettings.model_validate(policy.get("reproduction_logs") or {})


def storage_usage(session: Session) -> LogRecordingStorageUsage:
    policy = _policy(session)
    used_bytes = session.scalar(select(func.coalesce(func.sum(LogRecording.total_bytes), 0))) or 0
    used_percent = (used_bytes / policy.global_storage_bytes) * 100 if policy.global_storage_bytes else 0
    return LogRecordingStorageUsage(
        used_bytes=used_bytes,
        max_bytes=policy.global_storage_bytes,
        used_percent=round(used_percent, 2),
        warning_threshold_percent=policy.storage_warning_percent,
        warning=used_percent >= policy.storage_warning_percent,
        full=used_bytes >= policy.global_storage_bytes,
    )


def preview_recording(
    session: Session,
    provider: InspectionProvider,
    namespace: str,
) -> LogRecordingPreview:
    policy = _policy(session)
    discovery = discovery_service.discover_namespace_pods(provider, namespace)
    pods = discovery.get("pods", [])
    pod_count = len(pods)
    container_count = sum(len(item.get("containers") or []) for item in pods)
    if pod_count > policy.max_namespace_pods:
        return LogRecordingPreview(
            namespace=namespace,
            pod_count=pod_count,
            container_count=container_count,
            allowed=False,
            reason=f"Pod 数 {pod_count} 超过上限 {policy.max_namespace_pods}",
        )
    usage = storage_usage(session)
    if usage.full:
        return LogRecordingPreview(
            namespace=namespace,
            pod_count=pod_count,
            container_count=container_count,
            allowed=False,
            reason="复现日志存储已达到上限",
        )
    return LogRecordingPreview(
        namespace=namespace,
        pod_count=pod_count,
        container_count=container_count,
        allowed=True,
    )


def create_recording(
    session: Session,
    provider: InspectionProvider,
    payload: LogRecordingCreate,
    *,
    created_by: str | None,
) -> LogRecording:
    policy = _policy(session)
    usage = storage_usage(session)
    if usage.full:
        raise LogRecordingStorageFullError("复现日志存储已达到上限")
    discovery = discovery_service.discover_namespace_pods(provider, payload.namespace)
    pods = discovery.get("pods", [])
    pod_count = len(pods)
    if pod_count > policy.max_namespace_pods:
        raise LogRecordingScopeTooLargeError(pod_count, policy.max_namespace_pods)
    duration_minutes = _resolve_duration_minutes(payload, policy)
    now = _utcnow()
    row = LogRecording(
        name=payload.name,
        namespace=payload.namespace,
        status=LogRecordingStatus.recording.value,
        started_at=now,
        planned_end_at=now + timedelta(minutes=duration_minutes),
        duration_source=payload.duration_source.value,
        duration_minutes=duration_minutes,
        stop_reason=None,
        pod_count=pod_count,
        container_count=sum(len(item.get("containers") or []) for item in pods),
        raw_line_count=0,
        folded_line_count=0,
        total_bytes=0,
        truncated=False,
        note=payload.note,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_recordings(
    session: Session,
    *,
    page: int,
    page_size: int,
    namespace: str | None = None,
) -> Page[LogRecordingRead]:
    statement: Select[tuple[LogRecording]] = select(LogRecording)
    count_statement = select(func.count()).select_from(LogRecording)
    if namespace:
        statement = statement.where(LogRecording.namespace == namespace)
        count_statement = count_statement.where(LogRecording.namespace == namespace)
    total = session.scalar(count_statement) or 0
    rows = session.scalars(
        statement.order_by(LogRecording.started_at.desc(), LogRecording.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(
        items=[LogRecordingRead.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_recording(session: Session, recording_id: int) -> LogRecording:
    row = session.get(LogRecording, recording_id)
    if row is None:
        raise LogRecordingNotFoundError("日志记录不存在")
    return row


def update_recording(session: Session, recording_id: int, payload: LogRecordingUpdate) -> LogRecording:
    row = get_recording(session, recording_id)
    values = payload.model_dump(exclude_unset=True)
    for key, value in values.items():
        setattr(row, key, value)
    row.updated_at = _utcnow()
    session.commit()
    session.refresh(row)
    return row


def stop_recording(session: Session, recording_id: int) -> LogRecording:
    row = get_recording(session, recording_id)
    if row.status != LogRecordingStatus.recording.value:
        raise LogRecordingAlreadyStoppedError("日志记录已结束")
    row.status = LogRecordingStatus.completed.value
    row.stop_reason = LogRecordingStopReason.user_stopped.value
    row.ended_at = _utcnow()
    row.updated_at = row.ended_at
    session.commit()
    session.refresh(row)
    return row


def delete_recording(session: Session, recording_id: int) -> None:
    row = get_recording(session, recording_id)
    session.delete(row)
    session.commit()


def collect_recording_once(
    session: Session,
    provider: InspectionProvider,
    recording_id: int,
) -> LogRecordingRead:
    lock = _collection_lock(recording_id)
    with lock:
        return _collect_recording_once_locked(session, provider, recording_id)


def _collect_recording_once_locked(
    session: Session,
    provider: InspectionProvider,
    recording_id: int,
) -> LogRecordingRead:
    row = get_recording(session, recording_id)
    if row.status != LogRecordingStatus.recording.value:
        return LogRecordingRead.model_validate(row)
    policy = _policy(session)
    since_time = _last_collection_time(session, row) or row.started_at
    remaining_total = max(0, policy.max_recording_bytes - row.total_bytes)
    if remaining_total <= 0:
        row.truncated = True
        row.status = LogRecordingStatus.auto_completed.value
        row.stop_reason = LogRecordingStopReason.max_recording_bytes_reached.value
        row.ended_at = _utcnow()
        row.updated_at = row.ended_at
        session.commit()
        session.refresh(row)
        return LogRecordingRead.model_validate(row)
    try:
        snapshot = provider.collect_log_recording_snapshot(
            row.namespace,
            since_time=_ensure_utc(since_time),
            max_pods=policy.max_namespace_pods,
            max_total_bytes=remaining_total,
            max_pod_bytes=policy.max_pod_bytes,
        )
    except LogPodLimitExceededError as exc:
        _fail_recording(session, row, f"Pod 数 {exc.requested_pods} 超过上限 {exc.limit}")
        raise LogRecordingScopeTooLargeError(exc.requested_pods, exc.limit) from exc
    except Exception as exc:
        _fail_recording(session, row, "采集失败")
        raise LogRecordingCollectionFailedError("日志采集失败") from exc
    _ingest_snapshot(session, row, snapshot)
    if row.total_bytes >= policy.max_recording_bytes:
        row.truncated = True
        row.status = LogRecordingStatus.auto_completed.value
        row.stop_reason = LogRecordingStopReason.max_recording_bytes_reached.value
        row.ended_at = _utcnow()
        row.updated_at = row.ended_at
    session.commit()
    session.refresh(row)
    return LogRecordingRead.model_validate(row)


def list_pods(session: Session, recording_id: int) -> list[LogRecordingPodRead]:
    get_recording(session, recording_id)
    rows = session.scalars(
        select(LogRecordingPod)
        .where(LogRecordingPod.recording_id == recording_id)
        .order_by(LogRecordingPod.keyword_hit_count.desc(), LogRecordingPod.pod_name.asc())
    ).all()
    return [
        LogRecordingPodRead.model_validate(row).model_copy(
            update={"container_names": _pod_container_names(session, recording_id, row.pod_name)}
        )
        for row in rows
    ]


def list_logs(
    session: Session,
    recording_id: int,
    *,
    pod_name: str,
    container_name: str,
    page: int,
    page_size: int,
    view: LogRecordingViewMode,
) -> LogRecordingLogPage:
    get_recording(session, recording_id)
    filters = [
        LogRecordingLine.recording_id == recording_id,
        LogRecordingLine.pod_name == pod_name,
        LogRecordingLine.container_name == container_name,
    ]
    if view == LogRecordingViewMode.folded:
        filters.append(LogRecordingLine.folded.is_(True))
    else:
        filters.append(LogRecordingLine.folded.is_(False))
    total = session.scalar(select(func.count()).select_from(LogRecordingLine).where(*filters)) or 0
    rows = session.scalars(
        select(LogRecordingLine)
        .where(*filters)
        .order_by(LogRecordingLine.first_seen_at.asc(), LogRecordingLine.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return LogRecordingLogPage(
        items=[LogRecordingLineRead.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        view=view,
        redacted=True,
    )


def list_template_matches(session: Session, recording_id: int) -> list[LogRecordingTemplateMatchRead]:
    get_recording(session, recording_id)
    rows = session.scalars(
        select(LogRecordingTemplateMatch)
        .where(LogRecordingTemplateMatch.recording_id == recording_id)
        .order_by(LogRecordingTemplateMatch.created_at.desc(), LogRecordingTemplateMatch.id.desc())
    ).all()
    return [LogRecordingTemplateMatchRead.model_validate(row) for row in rows]


def match_recording_templates(session: Session, recording_id: int) -> list[LogRecordingTemplateMatchRead]:
    recording = get_recording(session, recording_id)
    session.execute(
        delete(LogRecordingTemplateMatch).where(LogRecordingTemplateMatch.recording_id == recording_id)
    )
    templates = _log_templates(session)
    created: list[LogRecordingTemplateMatch] = []
    for template in templates:
        context = _build_recording_template_context(session, recording, template)
        matched = match_template(
            {
                "target_groups": template.target_groups,
                "match_conditions": _enabled_log_conditions(template),
                "joint_rule": template.joint_rule,
                "reason": template.reason,
            },
            context,
        )
        if not matched["matched"]:
            continue
        for evidence in matched["evidence"]:
            if evidence.get("type") != "log_keyword":
                continue
            match_row = LogRecordingTemplateMatch(
                recording_id=recording_id,
                template_id=template.id,
                template_name=template.name,
                severity=_template_severity(template),
                pod_name=str(evidence.get("pod") or ""),
                container_name=str(evidence.get("container_name") or ""),
                keyword=_evidence_keyword(evidence),
                matched_context=str(evidence.get("context_text") or evidence.get("matched_text") or ""),
                suggestion=template.suggestion,
                created_at=_utcnow(),
            )
            session.add(match_row)
            created.append(match_row)
    session.commit()
    for item in created:
        session.refresh(item)
    return [LogRecordingTemplateMatchRead.model_validate(item) for item in created]


def _ingest_snapshot(session: Session, row: LogRecording, snapshot: LogRecordingSnapshot) -> None:
    policy = _policy(session)
    existing_pods = {
        pod.pod_uid: pod
        for pod in session.scalars(
            select(LogRecordingPod).where(LogRecordingPod.recording_id == row.id)
        ).all()
    }
    seen_uids: set[str] = set()
    inserted_lines = 0
    inserted_bytes = 0
    for pod_snapshot in snapshot.pods:
        seen_uids.add(pod_snapshot.pod_uid)
        pod_row = existing_pods.get(pod_snapshot.pod_uid)
        if pod_row is None:
            pod_row = LogRecordingPod(
                recording_id=row.id,
                namespace=pod_snapshot.namespace,
                pod_uid=pod_snapshot.pod_uid,
                pod_name=pod_snapshot.pod_name,
                node_name=pod_snapshot.node_name,
                owner_kind=pod_snapshot.owner_kind,
                owner_name=pod_snapshot.owner_name,
                container_count=len(pod_snapshot.container_names),
                raw_line_count=0,
                folded_line_count=0,
                keyword_hit_count=0,
                deleted_during_recording=False,
                truncated=False,
                collection_error=None,
            )
            session.add(pod_row)
            existing_pods[pod_snapshot.pod_uid] = pod_row
        else:
            pod_row.pod_name = pod_snapshot.pod_name
            pod_row.node_name = pod_snapshot.node_name
            pod_row.owner_kind = pod_snapshot.owner_kind
            pod_row.owner_name = pod_snapshot.owner_name
            pod_row.container_count = len(pod_snapshot.container_names)
            pod_row.deleted_during_recording = False
        pod_row.truncated = pod_row.truncated or pod_snapshot.truncated
        pod_row.collection_error = "; ".join(pod_snapshot.failures)[:1000] if pod_snapshot.failures else None

        raw_line_count = 0
        folded_line_count = 0
        pod_bytes = 0
        pod_keyword_hits = 0
        fold_candidates: dict[str, LogRecordingLine | None] = {}
        for entry in sorted(
            pod_snapshot.entries,
            key=lambda item: (item.log_time or item.collected_at, item.container_name),
        ):
            redacted_text, redacted = _redact_log_text(entry.text, policy=policy)
            fingerprint = _fingerprint(redacted_text)
            byte_size = len(redacted_text.encode("utf-8"))
            raw_line = LogRecordingLine(
                recording_id=row.id,
                pod_uid=entry.pod_uid,
                pod_name=entry.pod_name,
                container_name=entry.container_name,
                log_time=entry.log_time,
                collected_at=entry.collected_at,
                line_text=redacted_text,
                normalized_fingerprint=fingerprint,
                repeat_count=1,
                first_seen_at=entry.log_time or entry.collected_at,
                last_seen_at=entry.log_time or entry.collected_at,
                redacted=redacted,
                folded=False,
                byte_size=byte_size,
            )
            session.add(raw_line)
            raw_line_count += 1
            pod_bytes += byte_size
            pod_keyword_hits += len(
                [
                    hit
                    for hit in keyword_service.match_log_text(
                        session,
                        namespace=row.namespace,
                        label_selector=None,
                        pod_name=entry.pod_name,
                        log_text=redacted_text,
                        container_name=entry.container_name,
                    )
                    if not hit.whitelisted
                ]
            )

            fold_candidate = fold_candidates.get(entry.container_name)
            if entry.container_name not in fold_candidates and policy.duplicate_folding_enabled:
                fold_candidate = _latest_folded_line(session, row.id, entry.pod_name, entry.container_name)
                fold_candidates[entry.container_name] = fold_candidate
            if (
                policy.duplicate_folding_enabled
                and fold_candidate is not None
                and fold_candidate.normalized_fingerprint == fingerprint
            ):
                fold_candidate.repeat_count += 1
                fold_candidate.last_seen_at = entry.log_time or entry.collected_at
                fold_candidate.byte_size += byte_size
                continue

            folded_line = LogRecordingLine(
                recording_id=row.id,
                pod_uid=entry.pod_uid,
                pod_name=entry.pod_name,
                container_name=entry.container_name,
                log_time=entry.log_time,
                collected_at=entry.collected_at,
                line_text=redacted_text,
                normalized_fingerprint=fingerprint,
                repeat_count=1,
                first_seen_at=entry.log_time or entry.collected_at,
                last_seen_at=entry.log_time or entry.collected_at,
                redacted=redacted,
                folded=True,
                byte_size=byte_size,
            )
            session.add(folded_line)
            fold_candidates[entry.container_name] = folded_line
            folded_line_count += 1
        if not policy.duplicate_folding_enabled:
            folded_line_count = raw_line_count
        pod_row.raw_line_count += raw_line_count
        pod_row.folded_line_count += folded_line_count
        pod_row.keyword_hit_count += pod_keyword_hits
        inserted_lines += raw_line_count
        inserted_bytes += pod_bytes

    for pod_uid, pod_row in existing_pods.items():
        if pod_uid not in seen_uids and row.status == LogRecordingStatus.recording.value:
            pod_row.deleted_during_recording = True

    row.pod_count = len(existing_pods)
    row.container_count = sum(pod.container_count for pod in existing_pods.values())
    row.raw_line_count += inserted_lines
    row.folded_line_count = sum(pod.folded_line_count for pod in existing_pods.values())
    row.total_bytes += inserted_bytes
    row.truncated = row.truncated or snapshot.truncated
    row.updated_at = snapshot.collected_at


def _log_templates(session: Session) -> list[FaultTemplate]:
    templates = session.scalars(
        select(FaultTemplate)
        .where(FaultTemplate.enabled.is_(True))
        .order_by(FaultTemplate.id.asc())
    ).all()
    return [template for template in templates if _enabled_log_conditions(template)]


def _enabled_log_conditions(template: FaultTemplate) -> list[dict]:
    return [
        condition
        for condition in template.match_conditions
        if condition.get("enabled", True)
        and (condition.get("condition_type") or condition.get("type")) == "log_keyword"
    ]


def _build_recording_template_context(
    session: Session,
    recording: LogRecording,
    template: FaultTemplate,
) -> dict:
    targets: dict[str, dict] = {}
    pods = session.scalars(
        select(LogRecordingPod).where(LogRecordingPod.recording_id == recording.id)
    ).all()
    for target in template.target_groups or [{"target_ref": "default"}]:
        target_ref = str(target.get("target_ref") or target.get("ref") or "default")
        target_namespace = target.get("namespace")
        if target_namespace and target_namespace != recording.namespace:
            targets[target_ref] = {"namespace": target_namespace, "pods": [], "related_objects": {}}
            continue
        pod_pattern = target.get("pod_name_pattern") or target.get("name")
        target_pods = [
            _pod_context(session, recording, pod, template)
            for pod in pods
            if not pod_pattern or fnmatchcase(pod.pod_name, str(pod_pattern))
        ]
        targets[target_ref] = {
            "namespace": recording.namespace,
            "label_selector": target.get("label_selector"),
            "pods": target_pods,
            "related_objects": {},
        }
    return {"targets": targets}


def _pod_context(session: Session, recording: LogRecording, pod: LogRecordingPod, template: FaultTemplate) -> dict:
    lines = session.scalars(
        select(LogRecordingLine)
        .where(
            LogRecordingLine.recording_id == recording.id,
            LogRecordingLine.pod_name == pod.pod_name,
            LogRecordingLine.folded.is_(False),
        )
        .order_by(LogRecordingLine.first_seen_at.asc(), LogRecordingLine.id.asc())
    ).all()
    logs_by_container: dict[str, list[str]] = {}
    for line in lines:
        logs_by_container.setdefault(line.container_name, []).append(line.line_text)
    log_hits = []
    explicit_keywords = _template_keywords(template)
    for container_name, entries in logs_by_container.items():
        log_text = "\n".join(entries)
        log_hits.extend(
            hit.model_dump()
            for hit in keyword_service.match_log_text(
                session=session,
                namespace=recording.namespace,
                label_selector=None,
                pod_name=pod.pod_name,
                container_name=container_name,
                log_text=log_text,
            )
            if not hit.whitelisted
        )
        log_hits.extend(
            hit.model_dump()
            for hit in keyword_service.match_explicit_log_keywords(
                session=session,
                namespace=recording.namespace,
                label_selector=None,
                pod_name=pod.pod_name,
                container_name=container_name,
                log_text=log_text,
                keywords=explicit_keywords,
            )
            if not hit.whitelisted
        )
    return {
        "name": pod.pod_name,
        "containers": [{"name": name} for name in logs_by_container],
        "log_hits": log_hits,
    }


def _template_severity(template: FaultTemplate) -> str:
    for condition in _enabled_log_conditions(template):
        severity = condition.get("severity")
        if severity:
            return str(severity)
    return "warning"


def _template_keywords(template: FaultTemplate) -> list[str]:
    keywords: list[str] = []
    for condition in _enabled_log_conditions(template):
        value = condition.get("expected_value", condition.get("value"))
        if isinstance(value, list):
            keywords.extend(str(item) for item in value if item)
        elif value:
            keywords.append(str(value))
    return keywords


def _evidence_keyword(evidence: dict) -> str:
    value = evidence.get("value")
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value or "")


def _last_collection_time(session: Session, row: LogRecording) -> datetime | None:
    return session.scalar(
        select(func.max(LogRecordingLine.collected_at)).where(LogRecordingLine.recording_id == row.id)
    )


def _pod_container_names(session: Session, recording_id: int, pod_name: str) -> list[str]:
    return sorted(
        session.scalars(
            select(LogRecordingLine.container_name)
            .where(
                LogRecordingLine.recording_id == recording_id,
                LogRecordingLine.pod_name == pod_name,
            )
            .distinct()
        ).all()
    )


def _latest_folded_line(
    session: Session,
    recording_id: int,
    pod_name: str,
    container_name: str,
) -> LogRecordingLine | None:
    return session.scalar(
        select(LogRecordingLine)
        .where(
            LogRecordingLine.recording_id == recording_id,
            LogRecordingLine.pod_name == pod_name,
            LogRecordingLine.container_name == container_name,
            LogRecordingLine.folded.is_(True),
        )
        .order_by(LogRecordingLine.id.desc())
        .limit(1)
    )


def _fail_recording(session: Session, row: LogRecording, message: str) -> None:
    now = _utcnow()
    row.status = LogRecordingStatus.failed.value
    row.ended_at = now
    row.stop_reason = LogRecordingStopReason.collection_failed.value
    row.updated_at = now
    row.note = f"{row.note}\n{message}" if row.note else message
    session.commit()


def _fingerprint(text: str) -> str:
    normalized = text.strip().lower()
    for pattern, replacement in FINGERPRINT_NORMALIZERS:
        normalized = pattern.sub(replacement, normalized)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _redact_log_text(text: str, *, policy: ReproductionLogPolicySettings) -> tuple[str, bool]:
    redacted = text
    changed = False
    for pattern, replacement in _redaction_rules(policy):
        updated = pattern.sub(replacement, redacted)
        if updated != redacted:
            changed = True
            redacted = updated
    return redacted, changed


def _redaction_rules(policy: ReproductionLogPolicySettings) -> list[tuple[re.Pattern[str], str]]:
    rules = [(re.compile(pattern), replacement) for pattern, replacement in DEFAULT_REDACTION_RULES]
    for rule in policy.custom_redaction_rules:
        if not rule.enabled:
            continue
        rules.append((re.compile(rule.pattern), rule.replacement))
    return rules


def _ensure_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _collection_lock(recording_id: int) -> Lock:
    with _LOCK_GUARD:
        return _COLLECTION_LOCKS.setdefault(recording_id, Lock())


def _resolve_duration_minutes(payload: LogRecordingCreate, policy: ReproductionLogPolicySettings) -> int:
    if payload.duration_source == LogRecordingDurationSource.system_default:
        return policy.default_duration_minutes
    duration = payload.duration_minutes or policy.default_duration_minutes
    if duration > policy.max_duration_minutes:
        raise LogRecordingDurationError(f"记录时长 {duration} 分钟超过上限 {policy.max_duration_minutes} 分钟")
    return duration
