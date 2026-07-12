from sqlalchemy.orm import Session

from app.models import SavedInspectionTarget
from app.schemas.saved_target import SavedInspectionTargetCreate, SavedInspectionTargetUpdate


def list_saved_targets(session: Session) -> list[SavedInspectionTarget]:
    return session.query(SavedInspectionTarget).order_by(SavedInspectionTarget.id.desc()).all()


def create_saved_target(session: Session, payload: SavedInspectionTargetCreate) -> SavedInspectionTarget:
    target = SavedInspectionTarget(**payload.model_dump())
    session.add(target)
    session.commit()
    session.refresh(target)
    return target


def update_saved_target(session: Session, target_id: int, payload: SavedInspectionTargetUpdate) -> SavedInspectionTarget:
    target = session.get(SavedInspectionTarget, target_id)
    if target is None:
        raise ValueError("saved target not found")

    for key, value in payload.model_dump().items():
        setattr(target, key, value)

    session.commit()
    session.refresh(target)
    return target


def delete_saved_target(session: Session, target_id: int) -> None:
    target = session.get(SavedInspectionTarget, target_id)
    if target is None:
        raise ValueError("saved target not found")
    session.delete(target)
    session.commit()


def export_saved_targets(session: Session) -> list[SavedInspectionTarget]:
    return list_saved_targets(session)


def import_saved_targets(session: Session, payloads: list[SavedInspectionTargetCreate]) -> list[SavedInspectionTarget]:
    created: list[SavedInspectionTarget] = []
    for payload in payloads:
        created.append(create_saved_target(session, payload))
    return created
