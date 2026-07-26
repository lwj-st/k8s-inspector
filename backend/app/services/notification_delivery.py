from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import NotificationChannel as NotificationChannelModel
from app.models import NotificationDelivery as NotificationDeliveryModel
from app.schemas.v1_1 import (
    IssueSeverity,
    NotificationChannelType,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationEventType,
    NotificationMessage,
    WebhookTargetPolicy,
)
from app.security.crypto import SensitiveValueCipher
from app.security.outbound import ValidatedOutboundTarget, validate_outbound_target
from app.services.notification_adapter import (
    build_feishu_payload,
    build_generic_payload,
    serialized_body,
)
from app.services.notification_transport import SendResult, http_send


WebhookSender = Callable[[ValidatedOutboundTarget, bytes, dict[str, str], int], SendResult]


def delivery_from_model(row: NotificationDeliveryModel) -> NotificationDelivery:
    return NotificationDelivery(
        id=row.id,
        channel_id=row.channel_id,
        deduplication_key=row.deduplication_key,
        issue_event_id=row.issue_event_id,
        run_id=row.run_id,
        event_type=row.event_type,
        status=row.status,
        attempt_count=row.attempt_count,
        http_status=row.http_status,
        provider_code=row.provider_code,
        error_code=row.error_code,
        error_message=row.error_message,
        next_retry_at=_utc(row.next_retry_at),
        delivered_at=_utc(row.delivered_at),
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


def create_delivery(
    session: Session,
    *,
    channel_id: int,
    deduplication_key: str,
    event_type: NotificationEventType,
    issue_event_id: int | None = None,
    run_id: int | None = None,
) -> NotificationDeliveryModel:
    existing = session.scalar(
        select(NotificationDeliveryModel).where(
            NotificationDeliveryModel.deduplication_key == deduplication_key
        )
    )
    if existing is not None:
        return existing
    row = NotificationDeliveryModel(
        channel_id=channel_id,
        deduplication_key=deduplication_key,
        issue_event_id=issue_event_id,
        run_id=run_id,
        event_type=event_type.value,
        status=NotificationDeliveryStatus.pending.value,
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return session.scalar(
            select(NotificationDeliveryModel).where(
                NotificationDeliveryModel.deduplication_key == deduplication_key
            )
        )
    session.refresh(row)
    return row


def suppress_delivery(
    session: Session,
    *,
    channel_id: int,
    deduplication_key: str,
    event_type: NotificationEventType,
    issue_event_id: int | None = None,
    run_id: int | None = None,
) -> NotificationDeliveryModel:
    row = create_delivery(
        session,
        channel_id=channel_id,
        deduplication_key=deduplication_key,
        event_type=event_type,
        issue_event_id=issue_event_id,
        run_id=run_id,
    )
    if row.status == NotificationDeliveryStatus.pending.value:
        row.status = NotificationDeliveryStatus.suppressed.value
        row.updated_at = utcnow()
        session.commit()
    return row


def deliver(
    session: Session,
    *,
    row: NotificationChannelModel,
    delivery: NotificationDeliveryModel,
    message: NotificationMessage,
    settings: Settings,
    target_policy: WebhookTargetPolicy,
    sender: WebhookSender | None = None,
    max_attempts: int = 3,
) -> None:
    if not 1 <= max_attempts <= 3:
        raise ValueError("通知尝试次数必须在 1 至 3 之间")
    if delivery.status in {
        NotificationDeliveryStatus.succeeded.value,
        NotificationDeliveryStatus.failed.value,
        NotificationDeliveryStatus.suppressed.value,
    }:
        return
    send = sender or http_send
    cipher = SensitiveValueCipher.from_key(settings.encryption_key)
    try:
        webhook = cipher.decrypt(row.encrypted_webhook_url, purpose="notification_webhook_url")
        signing_secret = (
            cipher.decrypt(row.encrypted_signing_secret, purpose="notification_signing_secret")
            if row.encrypted_signing_secret
            else None
        )
    except Exception as exc:
        _finish_failure(delivery, code="CREDENTIAL_DECRYPT_FAILED", message=f"通知凭证不可用：{type(exc).__name__}")
        session.commit()
        return

    last_result: SendResult | None = None
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        delivery.status = NotificationDeliveryStatus.delivering.value
        delivery.attempt_count = attempt
        delivery.updated_at = utcnow()
        session.commit()
        try:
            target = validate_outbound_target(
                webhook,
                target_policy,
                production=settings.is_production,
            )
            if row.type == NotificationChannelType.feishu_custom_bot.value:
                payload, _ = build_feishu_payload(
                    message.model_copy(
                        update={
                            "mention_all": bool(
                                row.mention_all_on_critical
                                and message.severity == IssueSeverity.critical
                            )
                        }
                    ),
                    signing_secret=signing_secret,
                    text_fallback=attempt > 1,
                )
            else:
                payload = build_generic_payload(message)
            last_result = send(
                target,
                serialized_body(payload),
                {"content-type": "application/json"},
                row.timeout_seconds,
            )
            if last_result.succeeded:
                delivery.status = NotificationDeliveryStatus.succeeded.value
                delivery.http_status = last_result.http_status
                delivery.provider_code = last_result.provider_code
                delivery.error_code = None
                delivery.error_message = None
                delivery.next_retry_at = None
                delivery.delivered_at = utcnow()
                delivery.updated_at = utcnow()
                session.commit()
                return
            last_error = RuntimeError("下游返回失败状态")
        except Exception as exc:
            last_error = exc

    delivery.http_status = last_result.http_status if last_result else None
    delivery.provider_code = last_result.provider_code if last_result else None
    _finish_failure(
        delivery,
        code="NOTIFICATION_DELIVERY_FAILED",
        message=f"通知投递失败：{type(last_error).__name__ if last_error else 'UnknownError'}",
    )
    session.commit()


def _finish_failure(
    delivery: NotificationDeliveryModel,
    *,
    code: str,
    message: str,
) -> None:
    delivery.status = NotificationDeliveryStatus.failed.value
    delivery.error_code = code
    delivery.error_message = message[:1000]
    delivery.next_retry_at = None
    delivery.delivered_at = None
    delivery.updated_at = utcnow()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
