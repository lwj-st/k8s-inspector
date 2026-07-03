from fastapi import APIRouter, Depends

from app.api.deps import get_provider
from app.schemas.overview import OverviewResponse
from app.services import overview_service
from app.providers.mock_provider import MockInspectionProvider

router = APIRouter(tags=["overview"])


@router.get("/overview", response_model=OverviewResponse)
def get_overview(provider: MockInspectionProvider = Depends(get_provider)) -> OverviewResponse:
    return OverviewResponse.model_validate(overview_service.get_overview(provider))
