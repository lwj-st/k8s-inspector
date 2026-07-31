from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.v1_1 import SystemStatus
from app.security.readiness import build_system_status
from app.services.settings_service import get_effective_cluster_id


router = APIRouter(tags=["system"])


@router.get("/system/status", response_model=SystemStatus)
def get_system_status(
    request: Request,
    session: Session = Depends(get_db_session),
) -> SystemStatus:
    return build_system_status(
        request.app,
        cluster_id=get_effective_cluster_id(session, request.app.state.settings),
    )
