from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.v1_1 import (
    InspectionPlan,
    InspectionPlanCreate,
    InspectionPlanUpdate,
    InspectionRun,
    Page,
    SecurityAuditAction,
    SecurityAuditOutcome,
)
from app.security.audit import write_security_audit
from app.services import inspection_plan_service
from app.services.inspection_scheduler import (
    PlanAlreadyRunningError,
    enqueue_plan,
    remove_plan_job,
    sync_plan_job,
)


router = APIRouter(prefix="/inspection-plans", tags=["inspection-plans"])


@router.get("", response_model=Page[InspectionPlan])
def list_inspection_plans(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db_session),
) -> Page[InspectionPlan]:
    return inspection_plan_service.list_plans(session, page=page, page_size=page_size)


@router.post("", response_model=InspectionPlan, status_code=status.HTTP_201_CREATED)
def create_inspection_plan(
    payload: InspectionPlanCreate,
    request: Request,
    session: Session = Depends(get_db_session),
) -> InspectionPlan:
    try:
        result = inspection_plan_service.create_plan(session, payload)
    except inspection_plan_service.PlanConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except inspection_plan_service.PlanReferenceError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    sync_plan_job(request.app, result.id)
    _audit_plan(session, request, result.id, "create")
    return result


@router.put("/{plan_id}", response_model=InspectionPlan)
def update_inspection_plan(
    plan_id: int,
    payload: InspectionPlanUpdate,
    request: Request,
    session: Session = Depends(get_db_session),
) -> InspectionPlan:
    row = inspection_plan_service.get_plan(session, plan_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="巡检计划不存在")
    try:
        result = inspection_plan_service.update_plan(session, row, payload)
    except inspection_plan_service.PlanConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except inspection_plan_service.PlanReferenceError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    sync_plan_job(request.app, result.id)
    _audit_plan(session, request, result.id, "update")
    return result


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inspection_plan(
    plan_id: int,
    request: Request,
    session: Session = Depends(get_db_session),
) -> Response:
    row = inspection_plan_service.get_plan(session, plan_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="巡检计划不存在")
    remove_plan_job(request.app, plan_id)
    inspection_plan_service.delete_plan(session, row)
    _audit_plan(session, request, plan_id, "delete")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{plan_id}/run", response_model=InspectionRun, status_code=status.HTTP_202_ACCEPTED)
def run_inspection_plan(
    plan_id: int,
    request: Request,
) -> InspectionRun:
    try:
        return enqueue_plan(request.app, plan_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="巡检计划不存在") from exc
    except PlanAlreadyRunningError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


def _audit_plan(session: Session, request: Request, plan_id: int, operation: str) -> None:
    authenticated = getattr(request.state, "authenticated_session", None)
    write_security_audit(
        session,
        action=SecurityAuditAction.plan_changed,
        outcome=SecurityAuditOutcome.success,
        actor=authenticated.username if authenticated else "development",
        source_ip=request.client.host if request.client else None,
        request_id=request.state.request_id,
        details={
            "resource_type": "inspection_plan",
            "resource_id": plan_id,
            "changed_fields": operation,
        },
    )
