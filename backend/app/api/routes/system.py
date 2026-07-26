from fastapi import APIRouter, Request

from app.schemas.v1_1 import SystemStatus
from app.security.readiness import build_system_status


router = APIRouter(tags=["system"])


@router.get("/system/status", response_model=SystemStatus)
def get_system_status(request: Request) -> SystemStatus:
    return build_system_status(request.app)
