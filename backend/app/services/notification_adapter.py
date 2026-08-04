from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from copy import deepcopy
from typing import Any

from app.schemas.v1_1 import (
    IssueSeverity,
    NotificationEventType,
    NotificationMessage,
)


FEISHU_MAX_BODY_BYTES = 30 * 1024
_SENSITIVE_PATTERNS = (
    re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\b(password|passwd|token|secret|api[_-]?key)\s*[:=]\s*\S+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"https://(?:open\.feishu\.cn/)?open-apis/bot/v2/hook/[^\s\"']+", re.I),
)


def sanitize_notification_message(message: NotificationMessage) -> NotificationMessage:
    updates = {
        "summary": _sanitize(message.summary, 500),
        "suggestion": _sanitize(message.suggestion, 2000) if message.suggestion else None,
        "evidence_summaries": [
            _sanitize(item, 500) for item in message.evidence_summaries[:20]
        ],
    }
    return message.model_copy(update=updates)


def build_generic_payload(message: NotificationMessage) -> dict[str, Any]:
    safe = sanitize_notification_message(message)
    return {
        "event_type": safe.event_type.value,
        "cluster_id": safe.cluster_id,
        "issue_id": safe.issue_id,
        "run_id": safe.run_id,
        "fingerprint": safe.fingerprint,
        "status": safe.issue_status.value if safe.issue_status else None,
        "severity": safe.severity.value if safe.severity else None,
        "summary": safe.summary,
        "resource": safe.resource.model_dump(mode="json") if safe.resource else None,
        "first_seen_at": safe.first_seen_at.isoformat() if safe.first_seen_at else None,
        "last_seen_at": safe.last_seen_at.isoformat(),
        "evidence": safe.evidence_summaries,
        "suggestion": safe.suggestion,
        "detail_url": str(safe.detail_url),
        "is_test": safe.is_test,
        "truncated": safe.truncated,
    }


def build_feishu_payload(
    message: NotificationMessage,
    *,
    signing_secret: str | None = None,
    text_fallback: bool = False,
    timestamp: int | None = None,
) -> tuple[dict[str, Any], bool]:
    safe = sanitize_notification_message(message)
    payload = _feishu_text(safe) if text_fallback else _feishu_card(safe)
    if signing_secret:
        current_timestamp = timestamp or int(time.time())
        payload["timestamp"] = str(current_timestamp)
        payload["sign"] = _feishu_signature(current_timestamp, signing_secret)
    payload, truncated = _fit_feishu_payload(payload)
    return payload, truncated


def serialized_body(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _feishu_card(message: NotificationMessage) -> dict[str, Any]:
    title = "测试通知" if message.is_test else _event_title(message.event_type)
    resource = _resource_label(message)
    evidence = "\n".join(f"• {item}" for item in message.evidence_summaries) or "• 无额外证据摘要"
    mention = "\n<at id=all></at>" if message.mention_all and message.severity == IssueSeverity.critical else ""
    content = (
        f"**集群**：{message.cluster_id}\n"
        f"**状态/级别**：{message.issue_status.value if message.issue_status else '-'} / "
        f"{message.severity.value if message.severity else '-'}\n"
        f"**结论**：{message.summary}\n"
        f"**资源**：{resource}\n"
        f"**首次发现**：{message.first_seen_at.isoformat() if message.first_seen_at else '-'}\n"
        f"**最后变化**：{message.last_seen_at.isoformat()}\n"
        f"**证据摘要**：\n{evidence}\n"
        f"**建议**：{message.suggestion or '请进入系统查看详情。'}\n"
        f"**详情**：{message.detail_url}{mention}"
    )
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": _feishu_color(message),
                "title": {"tag": "plain_text", "content": title},
            },
            "elements": [{"tag": "markdown", "content": content}],
        },
    }


def _feishu_text(message: NotificationMessage) -> dict[str, Any]:
    mention = "\n<at user_id=\"all\">所有人</at>" if message.mention_all and message.severity == IssueSeverity.critical else ""
    content = (
        f"[{'测试通知' if message.is_test else _event_title(message.event_type)}]\n"
        f"集群：{message.cluster_id}\n"
        f"状态/级别：{message.issue_status.value if message.issue_status else '-'} / "
        f"{message.severity.value if message.severity else '-'}\n"
        f"结论：{message.summary}\n"
        f"资源：{_resource_label(message)}\n"
        f"时间：{message.last_seen_at.isoformat()}\n"
        f"建议：{message.suggestion or '请进入系统查看详情。'}\n"
        f"详情：{message.detail_url}{mention}"
    )
    return {"msg_type": "text", "content": {"text": content}}


def _fit_feishu_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    if len(serialized_body(payload)) <= FEISHU_MAX_BODY_BYTES:
        return payload, False
    fitted = deepcopy(payload)
    if fitted.get("msg_type") == "interactive":
        content = fitted["card"]["elements"][0]["content"]
        content = re.sub(
            r"\*\*证据摘要\*\*：\n.*?\n\*\*建议\*\*：",
            "**证据摘要**：\n• 已因消息长度限制裁剪\n**建议**：",
            content,
            flags=re.S,
        )
        fitted["card"]["elements"][0]["content"] = content[:24000] + "\n\n（消息已安全裁剪）"
    else:
        text = fitted["content"]["text"]
        fitted["content"]["text"] = text[:24000] + "\n（消息已安全裁剪）"
    if len(serialized_body(fitted)) > FEISHU_MAX_BODY_BYTES:
        fitted = {
            "msg_type": "text",
            "content": {"text": "告警消息过长，已安全裁剪。请进入 K8s Inspector 查看详情。"},
        }
        for key in ("timestamp", "sign"):
            if key in payload:
                fitted[key] = payload[key]
    return fitted, True


def _feishu_signature(timestamp: int, signing_secret: str) -> str:
    string_to_sign = f"{timestamp}\n{signing_secret}".encode("utf-8")
    digest = hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def _event_title(event_type: NotificationEventType) -> str:
    return {
        NotificationEventType.issue_opened: "发现新问题",
        NotificationEventType.severity_escalated: "问题严重程度升级",
        NotificationEventType.issue_recovered: "问题已恢复",
        NotificationEventType.inspection_failed: "巡检任务失败",
        NotificationEventType.flapping: "问题频繁抖动",
        NotificationEventType.maintenance_summary: "维护静默结束摘要",
        NotificationEventType.notification_test: "测试通知",
    }[event_type]


def _feishu_color(message: NotificationMessage) -> str:
    if message.event_type == NotificationEventType.issue_recovered:
        return "green"
    if message.event_type == NotificationEventType.inspection_failed:
        return "red"
    if message.severity == IssueSeverity.critical:
        return "red"
    if message.severity == IssueSeverity.warning:
        return "orange"
    return "blue"


def _resource_label(message: NotificationMessage) -> str:
    if message.resource is None:
        return "-"
    namespace = f"{message.resource.namespace}/" if message.resource.namespace else ""
    return f"{message.resource.kind} {namespace}{message.resource.name}"


def _sanitize(value: str | None, limit: int) -> str:
    text = value or ""
    for pattern in _SENSITIVE_PATTERNS:
        text = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]" if match.lastindex else "[REDACTED]", text)
    return text[:limit]
