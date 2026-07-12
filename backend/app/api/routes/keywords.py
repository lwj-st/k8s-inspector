from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.keyword import KeywordRuleCreate, KeywordRuleRead, KeywordRuleUpdate
from app.services import keyword_service

router = APIRouter(tags=["keywords"])


@router.get("/keywords", response_model=list[KeywordRuleRead])
def list_keywords(session: Session = Depends(get_db_session)) -> list[KeywordRuleRead]:
    return [KeywordRuleRead.model_validate(item) for item in keyword_service.list_keywords(session)]


@router.post("/keywords", status_code=status.HTTP_201_CREATED, response_model=KeywordRuleRead)
def create_keyword(payload: KeywordRuleCreate, session: Session = Depends(get_db_session)) -> KeywordRuleRead:
    return KeywordRuleRead.model_validate(keyword_service.create_keyword(session, payload))


@router.put("/keywords/{keyword_id}", response_model=KeywordRuleRead)
def update_keyword(keyword_id: int, payload: KeywordRuleUpdate, session: Session = Depends(get_db_session)) -> KeywordRuleRead:
    try:
        return KeywordRuleRead.model_validate(keyword_service.update_keyword(session, keyword_id, payload))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/keywords/{keyword_id}/enable", response_model=KeywordRuleRead)
def enable_keyword(keyword_id: int, session: Session = Depends(get_db_session)) -> KeywordRuleRead:
    try:
        return KeywordRuleRead.model_validate(keyword_service.set_keyword_enabled(session, keyword_id, True))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/keywords/{keyword_id}/disable", response_model=KeywordRuleRead)
def disable_keyword(keyword_id: int, session: Session = Depends(get_db_session)) -> KeywordRuleRead:
    try:
        return KeywordRuleRead.model_validate(keyword_service.set_keyword_enabled(session, keyword_id, False))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/keywords/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_keyword(keyword_id: int, session: Session = Depends(get_db_session)) -> None:
    try:
        keyword_service.delete_keyword(session, keyword_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/keywords/export", response_model=list[KeywordRuleRead])
def export_keywords(session: Session = Depends(get_db_session)) -> list[KeywordRuleRead]:
    return [KeywordRuleRead.model_validate(item) for item in keyword_service.export_keywords(session)]


@router.post("/keywords/import", response_model=list[KeywordRuleRead])
def import_keywords(payload: list[KeywordRuleCreate], session: Session = Depends(get_db_session)) -> list[KeywordRuleRead]:
    created = keyword_service.import_keywords(session, payload)
    return [KeywordRuleRead.model_validate(item) for item in created]
