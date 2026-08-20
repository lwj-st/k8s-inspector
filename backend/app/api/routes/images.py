from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from app.api.deps import get_provider
from app.providers.base import InspectionProvider
from app.schemas.image_inventory import ImageInventoryResponse
from app.services import image_inventory_service

router = APIRouter(prefix="/images", tags=["images"])


@router.get("", response_model=ImageInventoryResponse)
def list_images(
    namespace: list[str] = Query(default=[]),
    search: str | None = Query(default=None, max_length=300),
    provider: InspectionProvider = Depends(get_provider),
) -> ImageInventoryResponse:
    try:
        result = image_inventory_service.build_inventory(
            provider,
            namespaces=namespace,
            search=search,
        )
    except image_inventory_service.ImageInventoryScopeError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return ImageInventoryResponse.model_validate(result)


@router.get("/export")
def export_images(
    namespace: list[str] = Query(default=[]),
    search: str | None = Query(default=None, max_length=300),
    provider: InspectionProvider = Depends(get_provider),
) -> Response:
    try:
        inventory = image_inventory_service.build_inventory(
            provider,
            namespaces=namespace,
            search=search,
        )
    except image_inventory_service.ImageInventoryScopeError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    content = image_inventory_service.export_inventory_text(inventory)
    filename = f"k8s-inspector-images-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
    disposition = f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": disposition},
    )
