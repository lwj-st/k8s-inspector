from sqlalchemy.orm import Session

from app.models import Whitelist
from app.schemas.whitelist import WhitelistCreate, WhitelistUpdate


def list_whitelists(session: Session) -> list[Whitelist]:
    return session.query(Whitelist).order_by(Whitelist.id.desc()).all()


def create_whitelist(session: Session, payload: WhitelistCreate) -> Whitelist:
    whitelist = Whitelist(**payload.model_dump())
    session.add(whitelist)
    session.commit()
    session.refresh(whitelist)
    return whitelist


def update_whitelist(session: Session, whitelist_id: int, payload: WhitelistUpdate) -> Whitelist:
    whitelist = session.get(Whitelist, whitelist_id)
    if whitelist is None:
        raise ValueError("whitelist not found")

    for key, value in payload.model_dump().items():
        setattr(whitelist, key, value)

    session.commit()
    session.refresh(whitelist)
    return whitelist


def delete_whitelist(session: Session, whitelist_id: int) -> None:
    whitelist = session.get(Whitelist, whitelist_id)
    if whitelist is None:
        raise ValueError("whitelist not found")
    session.delete(whitelist)
    session.commit()
