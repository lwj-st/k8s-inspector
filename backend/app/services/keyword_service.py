from sqlalchemy.orm import Session

from app.models import KeywordRule
from app.schemas.common import KeywordHit
from app.schemas.keyword import KeywordRuleCreate, KeywordRuleUpdate
from app.services.whitelist_service import find_matching_whitelist


DEFAULT_KEYWORDS = [
    {
        "keyword": "connection refused",
        "category": "database",
        "severity": "error",
        "description": "下游连接被拒绝，通常表示依赖服务未就绪或地址配置错误。",
        "enabled": True,
        "builtin": True,
    },
    {
        "keyword": "timeout",
        "category": "network",
        "severity": "warning",
        "description": "请求超时，通常表示网络、依赖服务或探针异常。",
        "enabled": True,
        "builtin": True,
    },
]


def ensure_default_keywords(session: Session) -> None:
    existing_keywords = {
        item[0]
        for item in session.query(KeywordRule.keyword).filter(KeywordRule.builtin.is_(True)).all()
    }
    created = False
    for payload in DEFAULT_KEYWORDS:
        if payload["keyword"] in existing_keywords:
            continue
        session.add(KeywordRule(**payload))
        created = True
    if created:
        session.commit()


def list_keywords(session: Session) -> list[KeywordRule]:
    ensure_default_keywords(session)
    return session.query(KeywordRule).order_by(KeywordRule.builtin.desc(), KeywordRule.id.desc()).all()


def create_keyword(session: Session, payload: KeywordRuleCreate) -> KeywordRule:
    keyword = KeywordRule(**payload.model_dump())
    session.add(keyword)
    session.commit()
    session.refresh(keyword)
    return keyword


def update_keyword(session: Session, keyword_id: int, payload: KeywordRuleUpdate) -> KeywordRule:
    keyword = session.get(KeywordRule, keyword_id)
    if keyword is None:
        raise ValueError("keyword not found")

    for key, value in payload.model_dump().items():
        setattr(keyword, key, value)

    session.commit()
    session.refresh(keyword)
    return keyword


def set_keyword_enabled(session: Session, keyword_id: int, enabled: bool) -> KeywordRule:
    keyword = session.get(KeywordRule, keyword_id)
    if keyword is None:
        raise ValueError("keyword not found")
    keyword.enabled = enabled
    session.commit()
    session.refresh(keyword)
    return keyword


def delete_keyword(session: Session, keyword_id: int) -> None:
    keyword = session.get(KeywordRule, keyword_id)
    if keyword is None:
        raise ValueError("keyword not found")
    session.delete(keyword)
    session.commit()


def import_keywords(session: Session, payloads: list[KeywordRuleCreate]) -> list[KeywordRule]:
    created: list[KeywordRule] = []
    for payload in payloads:
        created.append(create_keyword(session, payload))
    return created


def export_keywords(session: Session) -> list[KeywordRule]:
    return list_keywords(session)


def match_log_text(
    session: Session,
    namespace: str,
    label_selector: str | None,
    pod_name: str,
    container_name: str | None,
    log_text: str | None,
) -> list[KeywordHit]:
    if not log_text:
        return []

    ensure_default_keywords(session)
    active_keywords = (
        session.query(KeywordRule)
        .filter(KeywordRule.enabled.is_(True))
        .order_by(KeywordRule.builtin.desc(), KeywordRule.id.asc())
        .all()
    )

    hits: list[KeywordHit] = []
    lowered_text = log_text.lower()
    for rule in active_keywords:
        lowered_keyword = rule.keyword.lower()
        if lowered_keyword not in lowered_text:
            continue

        whitelist_rule = find_matching_whitelist(
            session=session,
            namespace=namespace,
            label_selector=label_selector,
            pod_name=pod_name,
            container_name=container_name,
            keyword=rule.keyword,
        )
        hits.append(
            KeywordHit(
                keyword=rule.keyword,
                category=rule.category,
                severity=rule.severity,
                source="log_summary",
                matched_text=_extract_matched_text(log_text, rule.keyword),
                container_name=container_name,
                whitelisted=whitelist_rule is not None,
                whitelist_rule_id=whitelist_rule.id if whitelist_rule else None,
            )
        )
    return hits


def _extract_matched_text(log_text: str, keyword: str) -> str:
    lowered_keyword = keyword.lower()
    for line in log_text.splitlines():
        if lowered_keyword in line.lower():
            return line
    return log_text
