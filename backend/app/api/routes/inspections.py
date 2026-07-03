from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_provider
from app.providers.mock_provider import MockInspectionProvider
from app.schemas.inspection import ClusterInspectionResponse, NamespaceInspectionRequest, NamespaceInspectionResponse
from app.services import inspection_service

router = APIRouter(tags=["inspections"])


@router.post("/inspections/cluster/run", response_model=ClusterInspectionResponse)
def run_cluster_inspection(
    session: Session = Depends(get_db_session),
    provider: MockInspectionProvider = Depends(get_provider),
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
    provider: MockInspectionProvider = Depends(get_provider),
) -> NamespaceInspectionResponse:
    return NamespaceInspectionResponse.model_validate(inspection_service.run_namespace_inspection(session, provider, payload))


@router.get("/inspections/namespace/history")
def list_namespace_history(session: Session = Depends(get_db_session)) -> list[dict]:
    records = inspection_service.list_history(session, "namespace")
    return [record.result_payload for record in records]
