from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.schemas.template import FaultTemplateCreate, FaultTemplateRead, FaultTemplateUpdate
from app.services import template_service

router = APIRouter(tags=["templates"])


@router.get("/templates", response_model=list[FaultTemplateRead])
def list_templates(session: Session = Depends(get_db_session)) -> list[FaultTemplateRead]:
    return [FaultTemplateRead.model_validate(item) for item in template_service.list_templates(session)]


@router.post("/templates", status_code=status.HTTP_201_CREATED, response_model=FaultTemplateRead)
def create_template(payload: FaultTemplateCreate, session: Session = Depends(get_db_session)) -> FaultTemplateRead:
    return FaultTemplateRead.model_validate(template_service.create_template(session, payload))


@router.put("/templates/{template_id}", response_model=FaultTemplateRead)
def update_template(template_id: int, payload: FaultTemplateUpdate, session: Session = Depends(get_db_session)) -> FaultTemplateRead:
    try:
        return FaultTemplateRead.model_validate(template_service.update_template(session, template_id, payload))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: int, session: Session = Depends(get_db_session)) -> Response:
    try:
        template_service.delete_template(session, template_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
