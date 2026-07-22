import re

from sqlalchemy.orm import Session

from app.models import KeywordRule, Whitelist
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
    {
        "keyword": "ERROR",
        "category": "generic",
        "severity": "error",
        "description": "通用错误日志级别，支持匹配 [error]、[ERROR] 等常见日志格式。",
        "enabled": True,
        "builtin": True,
    },
    {
        "keyword": "Traceback (most recent call last)",
        "category": "python",
        "severity": "error",
        "description": "Python 未捕获异常堆栈起始行，需要结合后续异常类型定位代码问题。",
        "enabled": True,
        "builtin": True,
    },
    {
        "keyword": "ModuleNotFoundError",
        "category": "python",
        "severity": "error",
        "description": "Python 模块缺失，常见于镜像依赖未安装或启动路径错误。",
        "enabled": True,
        "builtin": True,
    },
    {
        "keyword": "ImportError",
        "category": "python",
        "severity": "error",
        "description": "Python 导入失败，可能是依赖版本、模块路径或循环导入问题。",
        "enabled": True,
        "builtin": True,
    },
    {
        "keyword": "SyntaxError",
        "category": "python",
        "severity": "error",
        "description": "Python 语法错误，通常会导致进程启动失败。",
        "enabled": True,
        "builtin": True,
    },
    {
        "keyword": "IndentationError",
        "category": "python",
        "severity": "error",
        "description": "Python 缩进错误，通常会导致进程启动失败。",
        "enabled": True,
        "builtin": True,
    },
    {
        "keyword": "KeyError",
        "category": "python",
        "severity": "warning",
        "description": "Python 字典键不存在，可能是配置、响应结构或数据字段缺失。",
        "enabled": True,
        "builtin": True,
    },
    {
        "keyword": "TypeError",
        "category": "python",
        "severity": "warning",
        "description": "Python 类型错误，通常表示参数类型或返回值结构不符合预期。",
        "enabled": True,
        "builtin": True,
    },
    {
        "keyword": "ValueError",
        "category": "python",
        "severity": "warning",
        "description": "Python 值错误，常见于配置值、入参或解析结果不合法。",
        "enabled": True,
        "builtin": True,
    },
    {
        "keyword": "OperationalError",
        "category": "database",
        "severity": "error",
        "description": "数据库操作异常，常见于连接失败、SQL 执行失败或数据库不可用。",
        "enabled": True,
        "builtin": True,
    },
    {
        "keyword": "UnhandledPromiseRejection",
        "category": "frontend",
        "severity": "error",
        "description": "前端或 Node.js Promise 未处理异常，可能导致页面功能或服务请求失败。",
        "enabled": True,
        "builtin": True,
    },
    {
        "keyword": "TypeError:",
        "category": "frontend",
        "severity": "warning",
        "description": "前端或 Node.js 类型错误，常见于空对象访问、参数类型错误或 API 返回结构变化。",
        "enabled": True,
        "builtin": True,
    },
    {
        "keyword": "ReferenceError",
        "category": "frontend",
        "severity": "error",
        "description": "前端或 Node.js 引用未定义变量，通常表示代码或构建产物异常。",
        "enabled": True,
        "builtin": True,
    },
    {
        "keyword": "ChunkLoadError",
        "category": "frontend",
        "severity": "error",
        "description": "前端资源分片加载失败，常见于发布后缓存、CDN 或静态资源路径问题。",
        "enabled": True,
        "builtin": True,
    },
    {
        "keyword": "Loading chunk",
        "category": "frontend",
        "severity": "error",
        "description": "前端分片资源加载失败，可能导致页面白屏或功能不可用。",
        "enabled": True,
        "builtin": True,
    },
    {
        "keyword": "Failed to fetch",
        "category": "frontend",
        "severity": "warning",
        "description": "浏览器请求失败，常见于网络、跨域、后端不可达或网关异常。",
        "enabled": True,
        "builtin": True,
    },
    {
        "keyword": "NetworkError",
        "category": "frontend",
        "severity": "warning",
        "description": "前端网络请求异常，需要结合目标接口、网关和浏览器控制台确认。",
        "enabled": True,
        "builtin": True,
    },
    {
        "keyword": "Cannot read properties of undefined",
        "category": "frontend",
        "severity": "warning",
        "description": "前端访问 undefined 对象属性，常见于接口字段缺失或状态初始化问题。",
        "enabled": True,
        "builtin": True,
    },
    {
        "keyword": "Cannot read property",
        "category": "frontend",
        "severity": "warning",
        "description": "前端访问空对象属性的兼容报错写法，常见于旧浏览器或旧构建产物。",
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
    for rule in active_keywords:
        if not _keyword_matches_text(log_text, rule.keyword):
            continue

        matched_text, context_before, context_after, context_text, whitelist_rule = _select_keyword_hit_context(
            session=session,
            namespace=namespace,
            label_selector=label_selector,
            container_name=container_name,
            log_text=log_text,
            keyword=rule.keyword,
        )
        hits.append(
            KeywordHit(
                keyword=rule.keyword,
                category=rule.category,
                severity=rule.severity,
                source="log_summary",
                matched_text=matched_text,
                context_before=context_before,
                context_after=context_after,
                context_text=context_text,
                container_name=container_name,
                whitelisted=whitelist_rule is not None,
                whitelist_rule_id=whitelist_rule.id if whitelist_rule else None,
            )
        )
    return hits


def match_explicit_log_keywords(
    session: Session,
    namespace: str,
    label_selector: str | None,
    pod_name: str,
    container_name: str | None,
    log_text: str | None,
    keywords: list[str],
) -> list[KeywordHit]:
    if not log_text:
        return []

    hits: list[KeywordHit] = []
    seen_keywords: set[str] = set()
    for keyword in keywords:
        normalized_keyword = str(keyword or "").strip()
        lowered_keyword = normalized_keyword.lower()
        if not lowered_keyword or lowered_keyword in seen_keywords:
            continue
        seen_keywords.add(lowered_keyword)
        if not _keyword_matches_text(log_text, normalized_keyword):
            continue

        matched_text, context_before, context_after, context_text, whitelist_rule = _select_keyword_hit_context(
            session=session,
            namespace=namespace,
            label_selector=label_selector,
            container_name=container_name,
            log_text=log_text,
            keyword=normalized_keyword,
        )
        hits.append(
            KeywordHit(
                keyword=normalized_keyword,
                category="fault_template",
                severity="error",
                source="template_log_condition",
                matched_text=matched_text,
                context_before=context_before,
                context_after=context_after,
                context_text=context_text,
                container_name=container_name,
                whitelisted=whitelist_rule is not None,
                whitelist_rule_id=whitelist_rule.id if whitelist_rule else None,
            )
        )
    return hits


def _extract_matched_text(log_text: str, keyword: str) -> str:
    for line in log_text.splitlines():
        if _keyword_matches_text(line, keyword):
            return line
    return log_text


def _extract_log_context(log_text: str, keyword: str, radius: int = 5) -> tuple[str, list[str], list[str], str | None]:
    contexts = _extract_log_contexts(log_text, keyword, radius)
    if contexts:
        return contexts[0]
    return log_text, [], [], None


def _extract_log_contexts(log_text: str, keyword: str, radius: int = 5) -> list[tuple[str, list[str], list[str], str | None]]:
    contexts: list[tuple[str, list[str], list[str], str | None]] = []
    lines = log_text.splitlines()
    for index, line in enumerate(lines):
        if not _keyword_matches_text(line, keyword):
            continue
        before = lines[max(0, index - radius):index]
        after = lines[index + 1:index + radius + 1]
        contexts.append((line, before, after, "\n".join([*before, line, *after])))
    return contexts


def _select_keyword_hit_context(
    session: Session,
    namespace: str,
    label_selector: str | None,
    container_name: str | None,
    log_text: str,
    keyword: str,
) -> tuple[str, list[str], list[str], str | None, Whitelist | None]:
    first_whitelisted: tuple[str, list[str], list[str], str | None, Whitelist] | None = None
    for matched_text, context_before, context_after, context_text in _extract_log_contexts(log_text, keyword):
        whitelist_rule = find_matching_whitelist(
            session=session,
            namespace=namespace,
            label_selector=label_selector,
            container_name=container_name,
            keyword=keyword,
            matched_text=matched_text,
        )
        if whitelist_rule is None:
            return matched_text, context_before, context_after, context_text, None
        if first_whitelisted is None:
            first_whitelisted = (matched_text, context_before, context_after, context_text, whitelist_rule)

    if first_whitelisted is not None:
        return first_whitelisted
    return log_text, [], [], None, None


def _keyword_matches_text(text: str, keyword: str) -> bool:
    normalized_keyword = keyword.strip()
    if not normalized_keyword:
        return False
    if _requires_token_boundary(normalized_keyword):
        return re.search(rf"(?<![A-Za-z0-9_]){re.escape(normalized_keyword)}(?![A-Za-z0-9_])", text, re.IGNORECASE) is not None
    return normalized_keyword.lower() in text.lower()


def _requires_token_boundary(keyword: str) -> bool:
    return re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", keyword) is not None
