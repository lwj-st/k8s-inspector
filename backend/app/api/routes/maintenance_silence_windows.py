from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.v1_1 import (
    MaintenanceSilenceWindow,
    MaintenanceSilenceWindowCreate,
    MaintenanceSilenceWindowUpdate,
    Page,
    SecurityAuditAction,
    SecurityAuditOutcome,
)
from app.security.audit import write_security_audit
from app.services import maintenance_silence_service


router = APIRouter(prefix="/maintenance-silence-windows", tags=["maintenance-silence-windows"])


@router.get("", response_model=Page[MaintenanceSilenceWindow])
def list_maintenance_silence_windows(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db_session),
) -> Page[MaintenanceSilenceWindow]:
    return maintenance_silence_service.list_windows(session, page=page, page_size=page_size)


@router.post("", response_model=MaintenanceSilenceWindow, status_code=status.HTTP_201_CREATED)
def create_maintenance_silence_window(
    payload: MaintenanceSilenceWindowCreate,
    request: Request,
    session: Session = Depends(get_db_session),
) -> MaintenanceSilenceWindow:
    result = maintenance_silence_service.create_window(session, payload)
    _audit_window(session, request, result.id, "create")
    return result


@router.put("/{window_id}", response_model=MaintenanceSilenceWindow)
def update_maintenance_silence_window(
    window_id: int,
    payload: MaintenanceSilenceWindowUpdate,
    request: Request,
    session: Session = Depends(get_db_session),
) -> MaintenanceSilenceWindow:
    row = maintenance_silence_service.get_window(session, window_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="静默窗口不存在")
    result = maintenance_silence_service.update_window(session, row, payload)
    _audit_window(session, request, result.id, "update")
    return result


@router.delete("/{window_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_maintenance_silence_window(
    window_id: int,
    request: Request,
    session: Session = Depends(get_db_session),
) -> Response:
    row = maintenance_silence_service.get_window(session, window_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="静默窗口不存在")
    maintenance_silence_service.delete_window(session, row)
    _audit_window(session, request, window_id, "delete")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _audit_window(
    session: Session,
    request: Request,
    window_id: int,
    operation: str,
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
            "resource_type": "maintenance_silence_window",
            "resource_id": window_id,
            "changed_fields": operation,
        },
    )
