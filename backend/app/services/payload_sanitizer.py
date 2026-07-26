from __future__ import annotations

import copy
import re
from typing import Any


_RAW_LOG_KEYS = {
    "containerlogsummaries",
    "fulllog",
    "logtext",
    "podlogs",
    "rawlog",
    "rawlogs",
}
_SENSITIVE_KEYS = {
    "accesstoken",
    "apikey",
    "authorization",
    "clientsecret",
    "cookie",
    "password",
    "passwd",
    "privatekey",
    "refreshtoken",
    "sessionsecret",
    "sessiontoken",
    "setcookie",
    "signingsecret",
    "secret",
    "token",
    "webhookurl",
}
_SENSITIVE_TEXT_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(
        r"(?i)\b(?:Set-Cookie|Cookie|Authorization)\s*:\s*[^\r\n]+"
    ),
    re.compile(
        r"(?i)\b(password|passwd|token|secret|api[\s_-]*key|"
        r"x[\s_-]*api[\s_-]*key|access[\s_-]*token|"
        r"refresh[\s_-]*token|session[\s_-]*token|"
        r"client[\s_-]*secret|signing[\s_-]*secret|"
        r"authorization|cookie|webhook(?:[\s_-]*url)?)\b"
        r"\s*[\"']?\s*[:=]\s*[\"']?[^\s,;}\]]+"
    ),
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?"
        r"-----END [A-Z ]*PRIVATE KEY-----",
        re.S,
    ),
    re.compile(
        r"https://(?:open\.feishu\.cn/)?open-apis/bot/v2/hook/"
        r"[^\s\"']+",
        re.I,
    ),
)
_TRUNCATED_SUFFIX = "…（已截断）"


def _normalize_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _is_sensitive_key(value: object) -> bool:
    return _normalize_key(value) in _SENSITIVE_KEYS


def _is_raw_log_key(value: object) -> bool:
    return _normalize_key(value) in _RAW_LOG_KEYS


def _redact_text(value: str) -> tuple[str, bool]:
    sanitized = value
    for pattern in _SENSITIVE_TEXT_PATTERNS:
        sanitized = pattern.sub(
            lambda match: (
                f"{match.group(1)}=[REDACTED]"
                if match.lastindex and match.group(1)
                else "[REDACTED]"
            ),
            sanitized,
        )
    return sanitized, sanitized != value


def _string_limit(path: tuple[str, ...]) -> int:
    bounded_markers = ("context", "evidence", "log", "matchedtext", "reason", "summary")
    return (
        2000
        if any(
            any(marker in path_part for marker in bounded_markers)
            for path_part in path
        )
        else 4096
    )


def _bounded_text(value: str, path: tuple[str, ...]) -> tuple[str, bool, bool]:
    sanitized, redacted = _redact_text(value)
    limit = _string_limit(path)
    truncated = len(sanitized) > limit
    if truncated:
        sanitized = sanitized[:limit] + _TRUNCATED_SUFFIX
    return sanitized, redacted, truncated


def sanitize_public_payload(payload: Any) -> Any:
    """Return a detached, shape-preserving, redacted and bounded value."""

    return _sanitize_public_value(copy.deepcopy(payload), path=())


def _sanitize_public_value(value: Any, *, path: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        return {
            str(key): (
                None
                if item is None
                else "[REDACTED]"
                if _is_sensitive_key(key)
                else _sanitize_public_value(
                    item,
                    path=(*path, _normalize_key(key)),
                )
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _sanitize_public_value(item, path=path)
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            _sanitize_public_value(item, path=path)
            for item in value
        )
    if isinstance(value, str):
        sanitized, _, _ = _bounded_text(value, path)
        return sanitized
    return value


def sanitize_persistence_payload(payload: Any) -> Any:
    """Return a detached DTO safe for persistence with top-level metadata."""

    sanitized, metadata = _sanitize_persistence_value(
        copy.deepcopy(payload),
        path=(),
    )
    if isinstance(sanitized, dict) and any(metadata.values()):
        sanitized["_persistence_sanitization"] = metadata
    return sanitized


def _empty_metadata() -> dict[str, bool]:
    return {
        "raw_logs_removed": False,
        "sensitive_values_redacted": False,
        "truncated": False,
    }


def _merge_metadata(
    target: dict[str, bool],
    source: dict[str, bool],
) -> None:
    for key in target:
        target[key] = target[key] or source[key]


def _sanitize_persistence_value(
    value: Any,
    *,
    path: tuple[str, ...],
) -> tuple[Any, dict[str, bool]]:
    metadata = _empty_metadata()
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            if _is_raw_log_key(key):
                metadata["raw_logs_removed"] = True
                continue
            if _is_sensitive_key(key):
                result[key] = None if item is None else "[REDACTED]"
                metadata["sensitive_values_redacted"] |= item is not None
                continue
            sanitized, child = _sanitize_persistence_value(
                item,
                path=(*path, _normalize_key(key)),
            )
            result[key] = sanitized
            _merge_metadata(metadata, child)
        return result, metadata
    if isinstance(value, (list, tuple)):
        result = []
        for item in value:
            sanitized, child = _sanitize_persistence_value(item, path=path)
            result.append(sanitized)
            _merge_metadata(metadata, child)
        return result, metadata
    if isinstance(value, str):
        sanitized, redacted, truncated = _bounded_text(value, path)
        metadata["sensitive_values_redacted"] = redacted
        metadata["truncated"] = truncated
        return sanitized, metadata
    return value, metadata
