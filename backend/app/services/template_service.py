from sqlalchemy.orm import Session

from app.models import FaultTemplate
from app.schemas.template import FaultTemplateCreate, FaultTemplateUpdate


def _serialize_template_payload(payload: FaultTemplateCreate | FaultTemplateUpdate) -> dict:
    targets = payload.targets
    primary_target = targets[0] if targets else None
    return {
        "name": payload.name,
        "scenario": payload.scenario,
        "target_groups": [item.model_dump() for item in targets],
        "object_scope": (primary_target.resource_scope[0] if primary_target and primary_target.resource_scope else None),
        "namespace_scope": primary_target.namespace if primary_target else None,
        "label_selector": primary_target.label_selector if primary_target else None,
        "match_conditions": [item.model_dump() for item in payload.match_conditions],
        "joint_rule": payload.joint_rule,
        "reason": payload.reason,
        "suggestion": payload.suggestion,
        "command": payload.command,
        "risk_note": payload.risk_note,
        "enabled": payload.enabled,
    }


def list_templates(session: Session) -> list[FaultTemplate]:
    return session.query(FaultTemplate).order_by(FaultTemplate.id.desc()).all()


def create_template(session: Session, payload: FaultTemplateCreate) -> FaultTemplate:
    template = FaultTemplate(**_serialize_template_payload(payload))
    session.add(template)
    session.commit()
    session.refresh(template)
    return template


def import_templates(session: Session, payloads: list[FaultTemplateCreate]) -> list[FaultTemplate]:
    created: list[FaultTemplate] = []
    for payload in payloads:
        created.append(create_template(session, payload))
    return created


def export_templates(session: Session) -> list[FaultTemplate]:
    return list_templates(session)


def update_template(session: Session, template_id: int, payload: FaultTemplateUpdate) -> FaultTemplate:
    template = session.get(FaultTemplate, template_id)
    if template is None:
        raise ValueError("template not found")

    for key, value in _serialize_template_payload(payload).items():
        setattr(template, key, value)

    session.commit()
    session.refresh(template)
    return template


def set_template_enabled(session: Session, template_id: int, enabled: bool) -> FaultTemplate:
    template = session.get(FaultTemplate, template_id)
    if template is None:
        raise ValueError("template not found")
    template.enabled = enabled
    session.commit()
    session.refresh(template)
    return template


def delete_template(session: Session, template_id: int) -> None:
    template = session.get(FaultTemplate, template_id)
    if template is None:
        raise ValueError("template not found")
    session.delete(template)
    session.commit()
