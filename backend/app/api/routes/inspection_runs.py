from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.v1_1 import (
    InspectionRun,
    InspectionRunDetail,
    InspectionRunListFilter,
    InspectionRunStatus,
    InspectionTrigger,
    Page,
)
from app.services import inspection_run_service


router = APIRouter(prefix="/inspection-runs", tags=["inspection-runs"])


@router.get("", response_model=Page[InspectionRun])
def list_inspection_runs(
    status_filter: InspectionRunStatus | None = Query(default=None, alias="status"),
    trigger: InspectionTrigger | None = None,
    plan_id: int | None = Query(default=None, gt=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db_session),
) -> Page[InspectionRun]:
    return inspection_run_service.list_runs(
        session,
        InspectionRunListFilter(
            status=status_filter,
            trigger=trigger,
            plan_id=plan_id,
            page=page,
            page_size=page_size,
        ),
    )


@router.get("/{run_id}", response_model=InspectionRunDetail)
def get_inspection_run(
    run_id: int,
    session: Session = Depends(get_db_session),
) -> InspectionRunDetail:
    result = inspection_run_service.get_run(session, run_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="巡检执行记录不存在")
    return result
