from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.saved_target import SavedInspectionTargetCreate, SavedInspectionTargetRead, SavedInspectionTargetUpdate
from app.services import saved_target_service

router = APIRouter(tags=["inspection-targets"])


@router.get("/inspection-targets", response_model=list[SavedInspectionTargetRead])
def list_saved_targets(session: Session = Depends(get_db_session)) -> list[SavedInspectionTargetRead]:
    return [SavedInspectionTargetRead.model_validate(item) for item in saved_target_service.list_saved_targets(session)]


@router.post("/inspection-targets", status_code=status.HTTP_201_CREATED, response_model=SavedInspectionTargetRead)
def create_saved_target(
    payload: SavedInspectionTargetCreate,
    session: Session = Depends(get_db_session),
) -> SavedInspectionTargetRead:
    return SavedInspectionTargetRead.model_validate(saved_target_service.create_saved_target(session, payload))


@router.put("/inspection-targets/{target_id}", response_model=SavedInspectionTargetRead)
def update_saved_target(
    target_id: int,
    payload: SavedInspectionTargetUpdate,
    session: Session = Depends(get_db_session),
) -> SavedInspectionTargetRead:
    try:
        return SavedInspectionTargetRead.model_validate(saved_target_service.update_saved_target(session, target_id, payload))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/inspection-targets/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_target(target_id: int, session: Session = Depends(get_db_session)) -> Response:
    try:
        saved_target_service.delete_saved_target(session, target_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/inspection-targets/export", response_model=list[SavedInspectionTargetRead])
def export_saved_targets(session: Session = Depends(get_db_session)) -> list[SavedInspectionTargetRead]:
    return [SavedInspectionTargetRead.model_validate(item) for item in saved_target_service.export_saved_targets(session)]


@router.post("/inspection-targets/import", response_model=list[SavedInspectionTargetRead])
def import_saved_targets(
    payload: list[SavedInspectionTargetCreate],
    session: Session = Depends(get_db_session),
) -> list[SavedInspectionTargetRead]:
    created = saved_target_service.import_saved_targets(session, payload)
    return [SavedInspectionTargetRead.model_validate(item) for item in created]
