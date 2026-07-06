from sqlalchemy.orm import Session

from app.models import Whitelist
from app.schemas.whitelist import WhitelistCreate, WhitelistIgnoreCreate, WhitelistUpdate


def list_whitelists(session: Session) -> list[Whitelist]:
    return session.query(Whitelist).order_by(Whitelist.id.desc()).all()


def create_whitelist(session: Session, payload: WhitelistCreate) -> Whitelist:
    whitelist = Whitelist(**payload.model_dump())
    session.add(whitelist)
    session.commit()
    session.refresh(whitelist)
    return whitelist


def ignore_log_hit(session: Session, payload: WhitelistIgnoreCreate) -> Whitelist:
    whitelist = Whitelist(
        namespace=payload.namespace,
        label_selector=payload.label_selector,
        pod_name_pattern=payload.pod_name_pattern,
        container_name=payload.container_name,
        keyword=payload.keyword,
        enabled=True,
        note=payload.note,
    )
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


def import_whitelists(session: Session, payloads: list[WhitelistCreate]) -> list[Whitelist]:
    created: list[Whitelist] = []
    for payload in payloads:
        created.append(create_whitelist(session, payload))
    return created


def export_whitelists(session: Session) -> list[Whitelist]:
    return list_whitelists(session)


def find_matching_whitelist(
    session: Session,
    namespace: str,
    label_selector: str | None,
    pod_name: str,
    container_name: str | None,
    keyword: str,
) -> Whitelist | None:
    rules = (
        session.query(Whitelist)
        .filter(
            Whitelist.namespace == namespace,
            Whitelist.keyword == keyword,
            Whitelist.enabled.is_(True),
        )
        .order_by(Whitelist.id.desc())
        .all()
    )
    for rule in rules:
        if rule.label_selector and rule.label_selector != label_selector:
            continue
        if rule.pod_name_pattern and rule.pod_name_pattern not in pod_name:
            continue
        if rule.container_name and rule.container_name != container_name:
            continue
        return rule
    return None
