from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.pathing import normalize_base_path
from app.models import (
    InspectionRun as InspectionRunModel,
    Issue as IssueModel,
    IssueEvent as IssueEventModel,
    MaintenanceSilenceWindow as MaintenanceSilenceWindowModel,
    NotificationChannel as NotificationChannelModel,
    NotificationDelivery as NotificationDeliveryModel,
)
from app.models.v1_1 import inspection_plan_channels
from app.schemas.v1_1 import (
    ComponentState,
    IssueEventType,
    IssueSeverity,
    IssueStatus,
    NotificationChannel,
    NotificationChannelCreate,
    NotificationChannelType,
    NotificationChannelUpdate,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationEventType,
    NotificationMessage,
    NotificationTestResponse,
    Page,
    ResourceRef,
    SystemComponentStatus,
    WebhookTargetPolicy,
)
from app.security.component_status import ComponentStatusRegistry
from app.security.crypto import SensitiveValueCipher
from app.security.outbound import validate_outbound_target
from app.services import maintenance_silence_service, notification_delivery
from app.services.notification_delivery import WebhookSender
from app.services.settings_service import get_effective_cluster_id
from app.services.notification_transport import (
    NotificationTransportError as NotificationTargetError,
    SendResult,
)


class NotificationConflictError(ValueError):
    pass


def channel_from_model(row: NotificationChannelModel) -> NotificationChannel:
    return NotificationChannel(
        id=row.id,
        name=row.name,
        type=row.type,
        enabled=row.enabled,
        endpoint_masked=row.endpoint_masked,
        signing_secret_configured=bool(row.encrypted_signing_secret),
        mention_all_on_critical=row.mention_all_on_critical,
        timeout_seconds=row.timeout_seconds,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


def list_channels(
    session: Session,
    *,
    page: int,
    page_size: int,
) -> Page[NotificationChannel]:
    base = select(NotificationChannelModel).where(NotificationChannelModel.deleted_at.is_(None))
    total = int(session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = session.scalars(
        base.order_by(desc(NotificationChannelModel.created_at), desc(NotificationChannelModel.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page[NotificationChannel](
        items=[channel_from_model(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_channel(session: Session, channel_id: int) -> NotificationChannelModel | None:
    return session.scalar(
        select(NotificationChannelModel).where(
            NotificationChannelModel.id == channel_id,
            NotificationChannelModel.deleted_at.is_(None),
        )
    )


def create_channel(
    session: Session,
    payload: NotificationChannelCreate,
    settings: Settings,
) -> NotificationChannel:
    webhook = payload.webhook_url.get_secret_value()
    _validate_channel_target(webhook, payload.type, settings)
    cipher = SensitiveValueCipher.from_key(settings.encryption_key)
    row = NotificationChannelModel(
        name=payload.name.strip(),
        normalized_name=_normalize_name(payload.name),
        type=payload.type.value,
        enabled=payload.enabled,
        encrypted_webhook_url=cipher.encrypt(webhook, purpose="notification_webhook_url"),
        encrypted_signing_secret=(
            cipher.encrypt(
                payload.signing_secret.get_secret_value(),
                purpose="notification_signing_secret",
            )
            if payload.signing_secret
            else None
        ),
        endpoint_masked=_mask_endpoint(webhook),
        mention_all_on_critical=payload.mention_all_on_critical,
        timeout_seconds=payload.timeout_seconds,
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise NotificationConflictError("通知渠道名称已存在") from exc
    session.refresh(row)
    return channel_from_model(row)


def update_channel(
    session: Session,
    row: NotificationChannelModel,
    payload: NotificationChannelUpdate,
    settings: Settings,
) -> NotificationChannel:
    cipher = SensitiveValueCipher.from_key(settings.encryption_key)
    channel_type = NotificationChannelType(row.type)
    if payload.name is not None:
        row.name = payload.name.strip()
        row.normalized_name = _normalize_name(payload.name)
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.webhook_url is not None:
        webhook = payload.webhook_url.get_secret_value()
        _validate_channel_target(webhook, channel_type, settings)
        row.encrypted_webhook_url = cipher.encrypt(
            webhook,
            purpose="notification_webhook_url",
        )
        row.endpoint_masked = _mask_endpoint(webhook)
    if payload.signing_secret is not None:
        row.encrypted_signing_secret = cipher.encrypt(
            payload.signing_secret.get_secret_value(),
            purpose="notification_signing_secret",
        )
    if payload.clear_signing_secret:
        row.encrypted_signing_secret = None
    if payload.mention_all_on_critical is not None:
        if channel_type != NotificationChannelType.feishu_custom_bot and payload.mention_all_on_critical:
            raise NotificationTargetError("只有飞书群机器人支持 critical 提醒所有人")
        row.mention_all_on_critical = payload.mention_all_on_critical
    if payload.timeout_seconds is not None:
        row.timeout_seconds = payload.timeout_seconds
    row.updated_at = utcnow()
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise NotificationConflictError("通知渠道名称已存在") from exc
    session.refresh(row)
    return channel_from_model(row)


def delete_channel(session: Session, row: NotificationChannelModel) -> None:
    row.enabled = False
    row.deleted_at = utcnow()
    session.execute(
        inspection_plan_channels.delete().where(inspection_plan_channels.c.channel_id == row.id)
    )
    session.commit()


def test_channel(
    session: Session,
    *,
    row: NotificationChannelModel,
    settings: Settings,
    sender: WebhookSender | None = None,
) -> NotificationTestResponse:
    now = utcnow()
    cluster_id = get_effective_cluster_id(session, settings)
    message = NotificationMessage(
        event_type=NotificationEventType.notification_test,
        cluster_id=cluster_id,
        summary="这是一条 K8s Inspector 测试通知",
        last_seen_at=now,
        evidence_summaries=[],
        suggestion="收到此消息表示通知渠道连接正常。",
        detail_url=_detail_url(settings, "/"),
        is_test=True,
    )
    delivery = notification_delivery.create_delivery(
        session,
        channel_id=row.id,
        deduplication_key=f"test:{row.id}:{now.isoformat()}",
        event_type=NotificationEventType.notification_test,
    )
    notification_delivery.deliver(
        session,
        row=row,
        delivery=delivery,
        message=message,
        settings=settings,
        target_policy=_target_policy(settings),
        sender=sender,
        max_attempts=1,
    )
    return NotificationTestResponse(
        delivery=notification_delivery.delivery_from_model(delivery),
        message="测试通知已送达" if delivery.status == NotificationDeliveryStatus.succeeded.value else "测试通知发送失败",
    )


def dispatch_lifecycle_changes(
    session: Session,
    *,
    plan_id: int | None,
    changes: list[Any],
    settings: Settings,
    registry: ComponentStatusRegistry | None = None,
    sender: WebhookSender | None = None,
) -> None:
    dispatch_due_maintenance_silence_summaries(
        session,
        settings=settings,
        registry=registry,
        sender=sender,
    )
    if not plan_id or not changes:
        return
    channels = _plan_channels(session, plan_id)
    for change in changes:
        event_type = _notification_event_for_issue_event(change.event.event_type)
        if event_type is None:
            continue
        issue = change.issue
        if (
            issue.severity == IssueSeverity.info.value
            and event_type
            in {
                NotificationEventType.issue_opened,
                NotificationEventType.issue_recovered,
            }
        ):
            continue
        now = utcnow()
        threshold_reached = _flapping_threshold_met(
            session,
            issue.id,
            change.event.event_type,
            now,
        )
        cooldown = _flapping_in_cooldown(session, issue.id, now)
        if threshold_reached:
            effective_event = NotificationEventType.flapping
        elif cooldown and event_type in {
            NotificationEventType.issue_opened,
            NotificationEventType.issue_recovered,
        }:
            for channel in channels:
                notification_delivery.suppress_delivery(
                    session,
                    channel_id=channel.id,
                    deduplication_key=f"issue-event:{change.event.id}:channel:{channel.id}",
                    issue_event_id=change.event.id,
                    run_id=change.event.run_id,
                    event_type=event_type,
                )
            continue
        else:
            effective_event = event_type
        silence_window = maintenance_silence_service.find_matching_window(
            session,
            issue=issue,
            now=now,
        )
        silence_breakthrough = (
            settings.notification_escalation_breaks_silence
            and effective_event == NotificationEventType.severity_escalated
        )
        if silence_window is not None and not silence_breakthrough:
            _record_silenced_issue_event(
                session,
                issue=issue,
                source_event=change.event,
                window=silence_window,
            )
            maintenance_silence_service.mark_pending_summary_recorded(
                session,
                silence_window,
                occurred_at=now,
            )
            for channel in channels:
                notification_delivery.suppress_delivery(
                    session,
                    channel_id=channel.id,
                    deduplication_key=f"issue-event:{change.event.id}:channel:{channel.id}",
                    issue_event_id=change.event.id,
                    run_id=change.event.run_id,
                    event_type=effective_event,
                    error_code="MAINTENANCE_SILENCE",
                    error_message=f"命中维护静默窗口：{silence_window.name}",
                )
            continue
        for channel in channels:
            delivery = notification_delivery.create_delivery(
                session,
                channel_id=channel.id,
                deduplication_key=(
                    f"flapping:{issue.id}:{change.event.id}:channel:{channel.id}"
                    if effective_event == NotificationEventType.flapping
                    else f"issue-event:{change.event.id}:channel:{channel.id}"
                ),
                issue_event_id=change.event.id,
                run_id=change.event.run_id,
                event_type=effective_event,
            )
            notification_delivery.deliver(
                session,
                row=channel,
                delivery=delivery,
                message=_issue_message(settings, issue, effective_event),
                settings=settings,
                target_policy=_target_policy(settings),
                sender=sender,
            )
    refresh_notification_registry(session, registry)


def _record_silenced_issue_event(
    session: Session,
    *,
    issue: IssueModel,
    source_event: IssueEventModel,
    window: MaintenanceSilenceWindowModel,
) -> None:
    existing = session.scalar(
        select(IssueEventModel.id).where(
            IssueEventModel.issue_id == issue.id,
            IssueEventModel.event_type == IssueEventType.notification_silenced.value,
            IssueEventModel.evidence_codes == [str(source_event.id), str(window.id)],
        )
    )
    if existing is not None:
        return
    event = IssueEventModel(
        issue_id=issue.id,
        run_id=source_event.run_id,
        event_type=IssueEventType.notification_silenced.value,
        trigger=source_event.trigger,
        previous_status=issue.status,
        new_status=issue.status,
        previous_severity=issue.severity,
        new_severity=issue.severity,
        occurred_at=utcnow(),
        summary=f"通知已静默：命中维护窗口“{window.name}”；静默结束后保留摘要待处理记录",
        evidence_codes=[str(source_event.id), str(window.id)],
    )
    session.add(event)
    session.commit()


def dispatch_inspection_failure(
    session: Session,
    *,
    plan_id: int | None,
    run: InspectionRunModel,
    settings: Settings,
    registry: ComponentStatusRegistry | None = None,
    sender: WebhookSender | None = None,
) -> None:
    dispatch_due_maintenance_silence_summaries(
        session,
        settings=settings,
        registry=registry,
        sender=sender,
    )
    if not plan_id:
        return
    channels = _plan_channels(session, plan_id)
    cluster_id = get_effective_cluster_id(session, settings)
    for channel in channels:
        delivery = notification_delivery.create_delivery(
            session,
            channel_id=channel.id,
            deduplication_key=f"inspection-failed:{run.id}:channel:{channel.id}",
            run_id=run.id,
            event_type=NotificationEventType.inspection_failed,
        )
        message = NotificationMessage(
            event_type=NotificationEventType.inspection_failed,
            cluster_id=cluster_id,
            run_id=run.id,
            summary="定时巡检任务整体失败",
            last_seen_at=_utc(run.finished_at) or utcnow(),
            suggestion="请检查系统状态、Kubernetes API 权限和执行记录。",
            detail_url=_detail_url(settings, f"/inspection-runs/{run.id}"),
        )
        notification_delivery.deliver(
            session,
            row=channel,
            delivery=delivery,
            message=message,
            settings=settings,
            target_policy=_target_policy(settings),
            sender=sender,
        )
    refresh_notification_registry(session, registry)


def dispatch_due_maintenance_silence_summaries(
    session: Session,
    *,
    settings: Settings,
    registry: ComponentStatusRegistry | None = None,
    sender: WebhookSender | None = None,
) -> None:
    windows = maintenance_silence_service.list_expired_pending_summary_windows(session)
    if not windows:
        return
    channels = _enabled_channels(session)
    cluster_id = get_effective_cluster_id(session, settings)
    for window in windows:
        issues = maintenance_silence_service.list_open_issues_for_window(session, window)
        if issues and channels:
            message = NotificationMessage(
                event_type=NotificationEventType.maintenance_summary,
                cluster_id=cluster_id,
                summary=f"维护静默窗口“{window.name}”已结束，仍有 {len(issues)} 个开放问题",
                last_seen_at=utcnow(),
                evidence_summaries=[
                    f"#{issue.id} {issue.severity} {issue.resource_kind}/{issue.resource_namespace or '集群级'}/{issue.resource_name}：{issue.summary}"
                    for issue in issues
                ],
                suggestion="请进入问题工作台查看当前仍开放的问题。",
                detail_url=_detail_url(settings, "/?status=open"),
                truncated=len(issues) >= 20,
            )
            for channel in channels:
                delivery = notification_delivery.create_delivery(
                    session,
                    channel_id=channel.id,
                    deduplication_key=(
                        f"maintenance-summary:{window.id}:"
                        f"{window.pending_summary_recorded_at.isoformat()}:channel:{channel.id}"
                    ),
                    event_type=NotificationEventType.maintenance_summary,
                )
                notification_delivery.deliver(
                    session,
                    row=channel,
                    delivery=delivery,
                    message=message,
                    settings=settings,
                    target_policy=_target_policy(settings),
                    sender=sender,
                )
        maintenance_silence_service.clear_pending_summary_recorded(session, window)
    refresh_notification_registry(session, registry)


def _plan_channels(session: Session, plan_id: int) -> list[NotificationChannelModel]:
    return list(
        session.scalars(
            select(NotificationChannelModel)
            .join(
                inspection_plan_channels,
                inspection_plan_channels.c.channel_id == NotificationChannelModel.id,
            )
            .where(
                inspection_plan_channels.c.plan_id == plan_id,
                NotificationChannelModel.enabled.is_(True),
                NotificationChannelModel.deleted_at.is_(None),
            )
            .order_by(NotificationChannelModel.id)
        ).all()
    )


def _enabled_channels(session: Session) -> list[NotificationChannelModel]:
    return list(
        session.scalars(
            select(NotificationChannelModel)
            .where(
                NotificationChannelModel.enabled.is_(True),
                NotificationChannelModel.deleted_at.is_(None),
            )
            .order_by(NotificationChannelModel.id)
        ).all()
    )


def _issue_message(
    settings: Settings,
    issue: IssueModel,
    event_type: NotificationEventType,
) -> NotificationMessage:
    evidence = [
        str(item.get("summary") or "")
        for item in (issue.evidence or [])
        if isinstance(item, dict) and item.get("summary")
    ][:20]
    return NotificationMessage(
        event_type=event_type,
        cluster_id=issue.cluster_id,
        issue_id=issue.id,
        fingerprint=issue.fingerprint,
        issue_status=IssueStatus(issue.status),
        severity=IssueSeverity(issue.severity),
        summary=issue.summary,
        resource=ResourceRef(
            api_version=issue.resource_api_version,
            kind=issue.resource_kind,
            namespace=issue.resource_namespace,
            name=issue.resource_name,
            uid=issue.resource_uid,
        ),
        first_seen_at=_utc(issue.first_seen_at),
        last_seen_at=(
            _utc(issue.recovered_at)
            if event_type == NotificationEventType.issue_recovered
            else _utc(issue.last_seen_at)
        ),
        evidence_summaries=evidence,
        suggestion=issue.suggestion,
        detail_url=_detail_url(settings, f"/issues/{issue.id}"),
    )


def _notification_event_for_issue_event(value: str) -> NotificationEventType | None:
    return {
        IssueEventType.opened.value: NotificationEventType.issue_opened,
        IssueEventType.reopened.value: NotificationEventType.issue_opened,
        IssueEventType.severity_escalated.value: NotificationEventType.severity_escalated,
        IssueEventType.recovered.value: NotificationEventType.issue_recovered,
    }.get(value)


def _flapping_threshold_met(
    session: Session,
    issue_id: int,
    current_event_type: str,
    now: datetime,
) -> bool:
    if current_event_type not in {
        IssueEventType.reopened.value,
        IssueEventType.recovered.value,
    }:
        return False
    cutoff = now - timedelta(minutes=30)
    event_types = list(
        session.scalars(
            select(IssueEventModel.event_type).where(
                IssueEventModel.issue_id == issue_id,
                IssueEventModel.occurred_at >= cutoff,
                IssueEventModel.event_type.in_(
                    [IssueEventType.opened.value, IssueEventType.reopened.value, IssueEventType.recovered.value]
                ),
            )
        ).all()
    )
    opened = sum(
        item in {IssueEventType.opened.value, IssueEventType.reopened.value}
        for item in event_types
    )
    recovered = sum(item == IssueEventType.recovered.value for item in event_types)
    if opened < 3 or recovered < 3:
        return False
    return not _flapping_in_cooldown(session, issue_id, now)


def _flapping_in_cooldown(
    session: Session,
    issue_id: int,
    now: datetime,
) -> bool:
    cutoff = now - timedelta(minutes=30)
    recent = session.scalar(
        select(NotificationDeliveryModel.id)
        .join(
            IssueEventModel,
            IssueEventModel.id == NotificationDeliveryModel.issue_event_id,
        )
        .where(
            IssueEventModel.issue_id == issue_id,
            NotificationDeliveryModel.event_type == NotificationEventType.flapping.value,
            NotificationDeliveryModel.created_at >= cutoff,
        )
        .limit(1)
    )
    return recent is not None


def _validate_channel_target(
    webhook: str,
    channel_type: NotificationChannelType,
    settings: Settings,
) -> None:
    if channel_type == NotificationChannelType.feishu_custom_bot:
        parsed = urlsplit(webhook)
        if parsed.hostname != "open.feishu.cn":
            raise NotificationTargetError("飞书群机器人地址必须使用官方域名")
    validate_outbound_target(
        webhook,
        _target_policy(settings),
        production=settings.is_production,
    )


def _target_policy(settings: Settings) -> WebhookTargetPolicy:
    allowed_hosts = list(settings.webhook_allowed_hosts)
    if not settings.is_production and not allowed_hosts and not settings.webhook_allowed_cidrs:
        allowed_hosts = ["open.feishu.cn"]
    return WebhookTargetPolicy(
        allowed_hosts=allowed_hosts,
        allowed_cidrs=settings.webhook_allowed_cidrs,
    )


def _mask_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    return f"{parsed.scheme}://{parsed.hostname or '***'}/***"


def _detail_url(settings: Settings, path: str) -> str:
    base = (settings.trusted_detail_base_url or "http://localhost").rstrip("/")
    detail_path = path if path.startswith("/") else f"/{path}"
    return f"{base}{normalize_base_path(settings.base_path)}{detail_path}"


def _normalize_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def refresh_notification_registry(
    session: Session,
    registry: ComponentStatusRegistry | None,
) -> None:
    if registry is None:
        return
    enabled_count = int(
        session.scalar(
            select(func.count(NotificationChannelModel.id)).where(
                NotificationChannelModel.enabled.is_(True),
                NotificationChannelModel.deleted_at.is_(None),
            )
        )
        or 0
    )
    registry.update(
        "notifications",
        SystemComponentStatus(
            state=ComponentState.ok if enabled_count else ComponentState.unavailable,
            message=f"已加载 {enabled_count} 个启用通知渠道" if enabled_count else "未配置启用的通知渠道",
            checked_at=utcnow(),
            details={"enabled_channels": enabled_count},
        ),
    )


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
