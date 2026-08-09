from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_provider
from app.providers.base import InspectionProvider
from app.schemas.inspection import (
    ClusterInspectionResponse,
    InspectionRunRequest,
    InspectionRunResponse,
    NamespaceBatchInspectionRequest,
    NamespaceBatchInspectionResponse,
    NamespaceInspectionRequest,
    NamespaceInspectionResponse,
    PodInspectionRequest,
    PodInspectionResponse,
)
from app.services import inspection_service

router = APIRouter(tags=["inspections"])


@router.post("/inspections/cluster/run", response_model=ClusterInspectionResponse)
def run_cluster_inspection(
    request: Request,
    include_logs: bool = True,
    session: Session = Depends(get_db_session),
    provider: InspectionProvider = Depends(get_provider),
) -> ClusterInspectionResponse:
    try:
        return ClusterInspectionResponse.model_validate(
            inspection_service.run_cluster_inspection(
                session,
                provider,
                request.app.state.component_status_registry,
                include_logs=include_logs,
            )
        )
    except inspection_service.LogInspectionScopeTooLargeError as exc:
        return _log_limit_response(request, exc)


@router.get("/inspections/cluster/history")
def list_cluster_history(session: Session = Depends(get_db_session)) -> list[dict]:
    records = inspection_service.list_history(session, "cluster")
    return [record.result_payload for record in records]


@router.post("/inspections/namespace/run", response_model=NamespaceInspectionResponse)
def run_namespace_inspection(
    payload: NamespaceInspectionRequest,
    request: Request,
    session: Session = Depends(get_db_session),
    provider: InspectionProvider = Depends(get_provider),
) -> NamespaceInspectionResponse:
    try:
        return NamespaceInspectionResponse.model_validate(
            inspection_service.run_namespace_inspection(
                session,
                provider,
                payload,
                request.app.state.component_status_registry,
            )
        )
    except inspection_service.LogInspectionScopeTooLargeError as exc:
        return _log_limit_response(request, exc)
    except inspection_service.LogInspectionTimeRangeError as exc:
        return _log_time_range_response(request, exc)


@router.get("/inspections/namespace/history")
def list_namespace_history(session: Session = Depends(get_db_session)) -> list[dict]:
    records = inspection_service.list_history(session, "namespace")
    return [record.result_payload for record in records]


@router.post("/inspections/logs/namespace/run", response_model=NamespaceInspectionResponse)
def run_namespace_log_inspection(
    payload: NamespaceInspectionRequest,
    request: Request,
    session: Session = Depends(get_db_session),
    provider: InspectionProvider = Depends(get_provider),
) -> NamespaceInspectionResponse:
    try:
        return NamespaceInspectionResponse.model_validate(
            inspection_service.run_namespace_log_inspection(
                session,
                provider,
                payload,
            )
        )
    except inspection_service.LogInspectionScopeTooLargeError as exc:
        return _log_limit_response(request, exc)
    except inspection_service.LogInspectionTimeRangeError as exc:
        return _log_time_range_response(request, exc)


@router.post("/inspections/namespaces/run", response_model=NamespaceBatchInspectionResponse)
def run_namespace_batch_inspection(
    payload: NamespaceBatchInspectionRequest,
    request: Request,
    session: Session = Depends(get_db_session),
    provider: InspectionProvider = Depends(get_provider),
) -> NamespaceBatchInspectionResponse:
    try:
        return NamespaceBatchInspectionResponse.model_validate(
            inspection_service.run_namespace_batch_inspection(
                session,
                provider,
                payload,
                request.app.state.component_status_registry,
            )
        )
    except inspection_service.LogInspectionScopeTooLargeError as exc:
        return _log_limit_response(request, exc)


@router.post("/inspections/pod/run", response_model=PodInspectionResponse)
def run_pod_inspection(
    payload: PodInspectionRequest,
    request: Request,
    session: Session = Depends(get_db_session),
    provider: InspectionProvider = Depends(get_provider),
) -> PodInspectionResponse:
    try:
        result = inspection_service.run_pod_inspection(
            session,
            provider,
            payload,
            request.app.state.component_status_registry,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except inspection_service.LogInspectionScopeTooLargeError as exc:
        return _log_limit_response(request, exc)
    return PodInspectionResponse.model_validate(result)


@router.get("/inspections/pod/history")
def list_pod_history(session: Session = Depends(get_db_session)) -> list[dict]:
    records = inspection_service.list_history(session, "pod")
    return [record.result_payload for record in records]


@router.post("/inspections/run", response_model=InspectionRunResponse)
def run_inspection(
    payload: InspectionRunRequest,
    request: Request,
    session: Session = Depends(get_db_session),
    provider: InspectionProvider = Depends(get_provider),
) -> InspectionRunResponse:
    try:
        result = inspection_service.run_inspection(
            session,
            provider,
            payload,
            request.app.state.component_status_registry,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except inspection_service.LogInspectionScopeTooLargeError as exc:
        return _log_limit_response(request, exc)
    return InspectionRunResponse.model_validate(result)


def _log_limit_response(
    request: Request,
    exc: inspection_service.LogInspectionScopeTooLargeError,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    headers = {"x-request-id": request_id} if request_id else {}
    return JSONResponse(
        status_code=422,
        content={
            "code": "INSPECTION_LOG_SCOPE_TOO_LARGE",
            "message": str(exc),
            "request_id": request_id,
            "details": {
                "estimated_pods": exc.estimated_pods,
                "limit": exc.limit,
            },
        },
        headers=headers,
    )


def _log_time_range_response(
    request: Request,
    exc: inspection_service.LogInspectionTimeRangeError,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    headers = {"x-request-id": request_id} if request_id else {}
    return JSONResponse(
        status_code=422,
        content={
            "code": "INSPECTION_LOG_TIME_RANGE_INVALID",
            "message": str(exc),
            "request_id": request_id,
            "details": {"reason": str(exc)},
        },
        headers=headers,
    )
