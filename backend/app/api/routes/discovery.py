from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_provider
from app.providers.base import InspectionProvider
from app.schemas.inspection import NamespaceDiscoveryResponse, NamespaceLabelDiscoveryResponse
from app.services import discovery_service

router = APIRouter(tags=["discovery"])


@router.get("/discovery/namespaces", response_model=NamespaceDiscoveryResponse)
def discover_namespaces(
    provider: InspectionProvider = Depends(get_provider),
) -> NamespaceDiscoveryResponse:
    return NamespaceDiscoveryResponse.model_validate(discovery_service.discover_namespaces(provider))


@router.get("/discovery/namespaces/{namespace}/labels", response_model=NamespaceLabelDiscoveryResponse)
def discover_namespace_labels(
    namespace: str,
    provider: InspectionProvider = Depends(get_provider),
) -> NamespaceLabelDiscoveryResponse:
    try:
        result = discovery_service.discover_namespace_labels(provider, namespace)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return NamespaceLabelDiscoveryResponse.model_validate(result)
