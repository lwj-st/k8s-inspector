from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.security.outbound import ValidatedOutboundTarget


class NotificationTransportError(ValueError):
    pass


@dataclass(frozen=True)
class SendResult:
    http_status: int
    provider_code: str | None = None
    provider_message: str | None = None

    @property
    def succeeded(self) -> bool:
        return 200 <= self.http_status < 300 and self.provider_code in {None, "0"}


def http_send(
    target: ValidatedOutboundTarget,
    body: bytes,
    headers: dict[str, str],
    timeout_seconds: int,
) -> SendResult:
    parsed = urlsplit(target.original_url)
    host_header = target.hostname
    default_port = 443 if parsed.scheme == "https" else 80
    if target.port != default_port:
        host_header = f"{host_header}:{target.port}"
    deadline = time.monotonic() + timeout_seconds
    response = None
    last_error: Exception | None = None
    for address in target.resolved_addresses:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        address_host = f"[{address}]" if ":" in address else address
        netloc = f"{address_host}:{target.port}"
        connect_url = urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, ""))
        try:
            with httpx.Client(follow_redirects=False, timeout=remaining, trust_env=False) as client:
                candidate = client.post(
                    connect_url,
                    content=body,
                    headers={**headers, "host": host_header},
                    extensions={"sni_hostname": target.hostname},
                )
                network_stream = candidate.extensions.get("network_stream")
                server_address = network_stream.get_extra_info("server_addr") if network_stream else None
                if not server_address:
                    raise NotificationTransportError("无法校验 Webhook 实际连接对端")
                peer = server_address[0] if isinstance(server_address, tuple) else str(server_address)
                target.require_allowed_peer(peer)
                response = candidate
                break
        except (httpx.TransportError, NotificationTransportError) as exc:
            last_error = exc
    if response is None:
        raise NotificationTransportError(
            f"Webhook 已验证地址均连接失败：{type(last_error).__name__ if last_error else 'Timeout'}"
        )
    provider_code = provider_message = None
    if parsed.hostname == "open.feishu.cn":
        try:
            payload = response.json()
            provider_code = str(payload.get("code")) if isinstance(payload, dict) and "code" in payload else None
            provider_message = "飞书返回失败" if provider_code not in {None, "0"} else None
        except (ValueError, json.JSONDecodeError):
            provider_code = "INVALID_RESPONSE"
            provider_message = "飞书响应格式无效"
    return SendResult(response.status_code, provider_code, provider_message)
