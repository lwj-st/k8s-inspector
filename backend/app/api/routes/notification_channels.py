from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.v1_1 import (
    NotificationChannel,
    NotificationChannelCreate,
    NotificationChannelUpdate,
    NotificationTestResponse,
    Page,
    SecurityAuditAction,
    SecurityAuditOutcome,
)
from app.security.audit import write_security_audit
from app.services import notification_service


router = APIRouter(prefix="/notification-channels", tags=["notification-channels"])


@router.get("", response_model=Page[NotificationChannel])
def list_notification_channels(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db_session),
) -> Page[NotificationChannel]:
    return notification_service.list_channels(session, page=page, page_size=page_size)


@router.post("", response_model=NotificationChannel, status_code=status.HTTP_201_CREATED)
def create_notification_channel(
    payload: NotificationChannelCreate,
    request: Request,
    session: Session = Depends(get_db_session),
) -> NotificationChannel:
    try:
        result = notification_service.create_channel(session, payload, request.app.state.settings)
    except notification_service.NotificationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (notification_service.NotificationTargetError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    _audit_channel(session, request, result.id, "create", result.type.value)
    notification_service.refresh_notification_registry(
        session,
        request.app.state.component_status_registry,
    )
    return result


@router.put("/{channel_id}", response_model=NotificationChannel)
def update_notification_channel(
    channel_id: int,
    payload: NotificationChannelUpdate,
    request: Request,
    session: Session = Depends(get_db_session),
) -> NotificationChannel:
    row = notification_service.get_channel(session, channel_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知渠道不存在")
    channel_type = row.type
    try:
        result = notification_service.update_channel(
            session,
            row,
            payload,
            request.app.state.settings,
        )
    except notification_service.NotificationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (notification_service.NotificationTargetError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    _audit_channel(session, request, result.id, "update", channel_type)
    notification_service.refresh_notification_registry(
        session,
        request.app.state.component_status_registry,
    )
    return result


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification_channel(
    channel_id: int,
    request: Request,
    session: Session = Depends(get_db_session),
) -> Response:
    row = notification_service.get_channel(session, channel_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知渠道不存在")
    channel_type = row.type
    notification_service.delete_channel(session, row)
    _audit_channel(session, request, channel_id, "delete", channel_type)
    notification_service.refresh_notification_registry(
        session,
        request.app.state.component_status_registry,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{channel_id}/test", response_model=NotificationTestResponse)
def test_notification_channel(
    channel_id: int,
    request: Request,
    session: Session = Depends(get_db_session),
) -> NotificationTestResponse:
    row = notification_service.get_channel(session, channel_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知渠道不存在")
    result = notification_service.test_channel(
        session,
        row=row,
        settings=request.app.state.settings,
    )
    authenticated = getattr(request.state, "authenticated_session", None)
    write_security_audit(
        session,
        action=SecurityAuditAction.notification_tested,
        outcome=(
            SecurityAuditOutcome.success
            if result.delivery.status.value == "succeeded"
            else SecurityAuditOutcome.failed
        ),
        actor=authenticated.username if authenticated else "development",
        source_ip=request.client.host if request.client else None,
        request_id=request.state.request_id,
        details={"resource_type": "notification_channel", "resource_id": channel_id},
    )
    notification_service.refresh_notification_registry(
        session,
        request.app.state.component_status_registry,
    )
    return result


def _audit_channel(
    session: Session,
    request: Request,
    channel_id: int,
    operation: str,
    channel_type: str,
) -> None:
    authenticated = getattr(request.state, "authenticated_session", None)
    write_security_audit(
        session,
        action=SecurityAuditAction.configuration_changed,
        outcome=SecurityAuditOutcome.success,
        actor=authenticated.username if authenticated else "development",
        source_ip=request.client.host if request.client else None,
        request_id=request.state.request_id,
        details={
            "resource_type": "notification_channel",
            "resource_id": channel_id,
            "changed_fields": operation,
            "channel_type": channel_type,
        },
    )
