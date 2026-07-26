from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.settings import SettingsResponse, SettingsUpdate
from app.schemas.v1_1 import SecurityAuditAction, SecurityAuditOutcome
from app.security.audit import write_security_audit
from app.services import settings_service

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=SettingsResponse)
def get_settings(session: Session = Depends(get_db_session)) -> SettingsResponse:
    return settings_service.serialize_settings(settings_service.get_settings(session))


@router.put("/settings", response_model=SettingsResponse)
def update_settings(
    payload: SettingsUpdate,
    request: Request,
    session: Session = Depends(get_db_session),
) -> SettingsResponse:
    updated = settings_service.update_settings(session, payload, request.app.state.settings)
    authenticated = getattr(request.state, "authenticated_session", None)
    write_security_audit(
        session,
        action=SecurityAuditAction.configuration_changed,
        outcome=SecurityAuditOutcome.success,
        actor=authenticated.username if authenticated else "development",
        source_ip=request.client.host if request.client else None,
        request_id=request.state.request_id,
        details={
            "changed_fields": ",".join(
                sorted(field for field in payload.model_fields_set if field != "api_key")
            )
        },
    )
    return settings_service.serialize_settings(updated)
