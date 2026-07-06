from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.whitelist import WhitelistCreate, WhitelistIgnoreCreate, WhitelistRead, WhitelistUpdate
from app.services import whitelist_service

router = APIRouter(tags=["whitelists"])


@router.get("/whitelists", response_model=list[WhitelistRead])
def list_whitelists(session: Session = Depends(get_db_session)) -> list[WhitelistRead]:
    return [WhitelistRead.model_validate(item) for item in whitelist_service.list_whitelists(session)]


@router.post("/whitelists", status_code=status.HTTP_201_CREATED, response_model=WhitelistRead)
def create_whitelist(payload: WhitelistCreate, session: Session = Depends(get_db_session)) -> WhitelistRead:
    return WhitelistRead.model_validate(whitelist_service.create_whitelist(session, payload))


@router.post("/whitelists/ignore", status_code=status.HTTP_201_CREATED, response_model=WhitelistRead)
def ignore_log_hit(payload: WhitelistIgnoreCreate, session: Session = Depends(get_db_session)) -> WhitelistRead:
    return WhitelistRead.model_validate(whitelist_service.ignore_log_hit(session, payload))


@router.put("/whitelists/{whitelist_id}", response_model=WhitelistRead)
def update_whitelist(whitelist_id: int, payload: WhitelistUpdate, session: Session = Depends(get_db_session)) -> WhitelistRead:
    try:
        return WhitelistRead.model_validate(whitelist_service.update_whitelist(session, whitelist_id, payload))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/whitelists/{whitelist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_whitelist(whitelist_id: int, session: Session = Depends(get_db_session)) -> Response:
    try:
        whitelist_service.delete_whitelist(session, whitelist_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/whitelists/export", response_model=list[WhitelistRead])
def export_whitelists(session: Session = Depends(get_db_session)) -> list[WhitelistRead]:
    return [WhitelistRead.model_validate(item) for item in whitelist_service.export_whitelists(session)]


@router.post("/whitelists/import", response_model=list[WhitelistRead])
def import_whitelists(payload: list[WhitelistCreate], session: Session = Depends(get_db_session)) -> list[WhitelistRead]:
    created = whitelist_service.import_whitelists(session, payload)
    return [WhitelistRead.model_validate(item) for item in created]
