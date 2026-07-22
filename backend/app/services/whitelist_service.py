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
        pod_name_pattern=None,
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


def set_whitelist_enabled(session: Session, whitelist_id: int, enabled: bool) -> Whitelist:
    whitelist = session.get(Whitelist, whitelist_id)
    if whitelist is None:
        raise ValueError("whitelist not found")
    whitelist.enabled = enabled
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
    container_name: str | None,
    keyword: str,
    matched_text: str,
) -> Whitelist | None:
    rules = (
        session.query(Whitelist)
        .filter(
            Whitelist.namespace == namespace,
            Whitelist.enabled.is_(True),
        )
        .order_by(Whitelist.id.desc())
        .all()
    )
    for rule in rules:
        if rule.label_selector and rule.label_selector != label_selector:
            continue
        if rule.container_name and rule.container_name != container_name:
            continue
        if not _whitelist_phrase_covers_hit(rule.keyword, keyword, matched_text):
            continue
        return rule
    return None


def _whitelist_phrase_covers_hit(whitelist_keyword: str, hit_keyword: str, matched_text: str) -> bool:
    normalized_whitelist = whitelist_keyword.strip().lower()
    normalized_keyword = hit_keyword.strip().lower()
    normalized_text = matched_text.strip().lower()
    if not normalized_whitelist or not normalized_keyword:
        return False
    return (
        normalized_whitelist == normalized_keyword
        or normalized_whitelist in normalized_text
    )
