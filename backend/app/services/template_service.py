from sqlalchemy.orm import Session

from app.models import FaultTemplate
from app.schemas.template import FaultTemplateCreate, FaultTemplateUpdate


def list_templates(session: Session) -> list[FaultTemplate]:
    return session.query(FaultTemplate).order_by(FaultTemplate.id.desc()).all()


def create_template(session: Session, payload: FaultTemplateCreate) -> FaultTemplate:
    template = FaultTemplate(**payload.model_dump())
    session.add(template)
    session.commit()
    session.refresh(template)
    return template


def update_template(session: Session, template_id: int, payload: FaultTemplateUpdate) -> FaultTemplate:
    template = session.get(FaultTemplate, template_id)
    if template is None:
        raise ValueError("template not found")

    for key, value in payload.model_dump().items():
        setattr(template, key, value)

    session.commit()
    session.refresh(template)
    return template


def delete_template(session: Session, template_id: int) -> None:
    template = session.get(FaultTemplate, template_id)
    if template is None:
        raise ValueError("template not found")
    session.delete(template)
    session.commit()
