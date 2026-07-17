from fastapi import APIRouter, Depends

from app.api.deps import get_provider
from app.providers.base import InspectionProvider
from app.schemas.inspection import NamespaceDiscoveryResponse
from app.services import discovery_service

router = APIRouter(tags=["discovery"])


@router.get("/discovery/namespaces", response_model=NamespaceDiscoveryResponse)
def discover_namespaces(
    provider: InspectionProvider = Depends(get_provider),
) -> NamespaceDiscoveryResponse:
    return NamespaceDiscoveryResponse.model_validate(discovery_service.discover_namespaces(provider))
