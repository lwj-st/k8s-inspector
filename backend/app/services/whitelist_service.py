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
    pod_labels: dict[str, str] | None = None,
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
        selector_matched_by_request = rule.label_selector == label_selector
        selector_matched_by_pod_labels = _labels_match_selector(pod_labels, rule.label_selector) if rule.label_selector else True
        if rule.label_selector and not selector_matched_by_request and not selector_matched_by_pod_labels:
            continue
        if rule.container_name and rule.container_name != container_name:
            continue
        if not _whitelist_phrase_covers_hit(rule.keyword, keyword, matched_text):
            continue
        return rule
    return None


def _whitelist_phrase_covers_hit(whitelist_keyword: str, hit_keyword: str, matched_text: str) -> bool:
    normalized_whitelist = _normalize_log_fragment(whitelist_keyword)
    normalized_keyword = _normalize_log_fragment(hit_keyword)
    normalized_text = _normalize_log_fragment(matched_text)
    if not normalized_whitelist or not normalized_keyword:
        return False
    return (
        normalized_whitelist == normalized_keyword
        or normalized_whitelist in normalized_text
        or _compact_log_fragment(normalized_whitelist) in _compact_log_fragment(normalized_text)
    )


def _normalize_log_fragment(value: str) -> str:
    return (
        value.strip()
        .replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\\'", "'")
        .lower()
    )


def _compact_log_fragment(value: str) -> str:
    return "".join(value.split())


def _labels_match_selector(labels: dict[str, str] | None, selector: str) -> bool:
    if not labels:
        return False

    requirements = [item.strip() for item in selector.split(",") if item.strip()]
    if not requirements:
        return False

    for requirement in requirements:
        if "=" not in requirement:
            return False
        key, value = [part.strip() for part in requirement.split("=", 1)]
        if not key or labels.get(key) != value:
            return False
    return True
