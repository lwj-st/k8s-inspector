from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.settings import SettingsResponse, SettingsUpdate, SystemStatusResponse
from app.services import settings_service

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=SettingsResponse)
def get_settings(session: Session = Depends(get_db_session)) -> SettingsResponse:
    return SettingsResponse.model_validate(settings_service.get_settings(session))


@router.put("/settings", response_model=SettingsResponse)
def update_settings(payload: SettingsUpdate, session: Session = Depends(get_db_session)) -> SettingsResponse:
    return SettingsResponse.model_validate(settings_service.update_settings(session, payload))


@router.get("/system/status", response_model=SystemStatusResponse)
def get_system_status(request: Request) -> SystemStatusResponse:
    settings = request.app.state.settings
    return SystemStatusResponse(
        status="ready",
        version="0.1.0",
        message=f"{settings.provider_mode} provider active",
        provider_mode=settings.provider_mode,
        kube_context=settings.kube_context,
    )
