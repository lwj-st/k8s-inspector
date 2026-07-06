from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_provider
from app.providers.base import InspectionProvider
from app.schemas.inspection import (
    ClusterInspectionResponse,
    InspectionRunRequest,
    InspectionRunResponse,
    NamespaceInspectionRequest,
    NamespaceInspectionResponse,
    PodInspectionRequest,
    PodInspectionResponse,
)
from app.services import inspection_service

router = APIRouter(tags=["inspections"])


@router.post("/inspections/cluster/run", response_model=ClusterInspectionResponse)
def run_cluster_inspection(
    session: Session = Depends(get_db_session),
    provider: InspectionProvider = Depends(get_provider),
) -> ClusterInspectionResponse:
    return ClusterInspectionResponse.model_validate(inspection_service.run_cluster_inspection(session, provider))


@router.get("/inspections/cluster/history")
def list_cluster_history(session: Session = Depends(get_db_session)) -> list[dict]:
    records = inspection_service.list_history(session, "cluster")
    return [record.result_payload for record in records]


@router.post("/inspections/namespace/run", response_model=NamespaceInspectionResponse)
def run_namespace_inspection(
    payload: NamespaceInspectionRequest,
    session: Session = Depends(get_db_session),
    provider: InspectionProvider = Depends(get_provider),
) -> NamespaceInspectionResponse:
    return NamespaceInspectionResponse.model_validate(inspection_service.run_namespace_inspection(session, provider, payload))


@router.get("/inspections/namespace/history")
def list_namespace_history(session: Session = Depends(get_db_session)) -> list[dict]:
    records = inspection_service.list_history(session, "namespace")
    return [record.result_payload for record in records]


@router.post("/inspections/pod/run", response_model=PodInspectionResponse)
def run_pod_inspection(
    payload: PodInspectionRequest,
    session: Session = Depends(get_db_session),
    provider: InspectionProvider = Depends(get_provider),
) -> PodInspectionResponse:
    try:
        result = inspection_service.run_pod_inspection(session, provider, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PodInspectionResponse.model_validate(result)


@router.get("/inspections/pod/history")
def list_pod_history(session: Session = Depends(get_db_session)) -> list[dict]:
    records = inspection_service.list_history(session, "pod")
    return [record.result_payload for record in records]


@router.post("/inspections/run", response_model=InspectionRunResponse)
def run_inspection(
    payload: InspectionRunRequest,
    session: Session = Depends(get_db_session),
    provider: InspectionProvider = Depends(get_provider),
) -> InspectionRunResponse:
    try:
        result = inspection_service.run_inspection(session, provider, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return InspectionRunResponse.model_validate(result)
