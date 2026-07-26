from fastapi import APIRouter, Request, Response, status

from app.schemas.v1_1 import LiveHealthResponse, ReadyHealthResponse
from app.security.readiness import build_ready_response


router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=LiveHealthResponse)
def live(request: Request) -> LiveHealthResponse:
    return LiveHealthResponse(version=request.app.state.settings.app_version)


@router.get("/health/ready", response_model=ReadyHealthResponse)
def ready(request: Request, response: Response) -> ReadyHealthResponse:
    result = build_ready_response(request.app)
    if not result.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
