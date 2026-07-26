from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.schemas.v1_1 import WebhookTargetPolicy


class OutboundTargetError(ValueError):
    pass


Resolver = Callable[[str, int], Iterable[str]]


_CLOUD_METADATA_ADDRESSES = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("fd00:ec2::254"),
}


@dataclass(frozen=True)
class ValidatedOutboundTarget:
    """A per-attempt DNS result that must be pinned by the network transport.

    Callers must connect to one of ``resolved_addresses`` while retaining
    ``hostname`` for HTTP Host and TLS SNI, then call ``require_allowed_peer``
    with the actual socket peer. Passing ``original_url`` to a default client
    that performs a second DNS lookup is explicitly unsafe.
    """

    original_url: str
    hostname: str
    port: int
    resolved_addresses: tuple[str, ...]

    def require_allowed_peer(self, peer_address: str) -> None:
        try:
            normalized = str(ipaddress.ip_address(peer_address))
        except ValueError as exc:
            raise OutboundTargetError("连接对端返回了无效 IP 地址") from exc
        if normalized not in self.resolved_addresses:
            raise OutboundTargetError("连接对端与本次已验证 DNS 结果不一致")


def validate_outbound_target(
    url: str,
    policy: WebhookTargetPolicy,
    *,
    production: bool,
    resolver: Resolver | None = None,
) -> ValidatedOutboundTarget:
    """Validate one connection attempt and return a transport-pinning result."""
    if any(character in url for character in ("\r", "\n", "\x00")):
        raise OutboundTargetError("Webhook 地址包含非法字符")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise OutboundTargetError("Webhook 只支持 HTTP 或 HTTPS")
    if production and policy.production_https_only and parsed.scheme != "https":
        raise OutboundTargetError("生产环境 Webhook 必须使用 HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise OutboundTargetError("Webhook 地址不允许包含用户信息")
    if not parsed.hostname:
        raise OutboundTargetError("Webhook 地址缺少主机名")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise OutboundTargetError("Webhook 端口无效") from exc
    host = parsed.hostname.casefold().rstrip(".")
    if port < 1 or port > 65535:
        raise OutboundTargetError("Webhook 端口无效")

    resolve = resolver or _resolve_all
    try:
        addresses = tuple(dict.fromkeys(resolve(host, port)))
    except (OSError, ValueError) as exc:
        raise OutboundTargetError("Webhook 主机 DNS 解析失败") from exc
    if not addresses:
        raise OutboundTargetError("Webhook 主机没有可用 IP 地址")

    host_allowed = any(_host_matches(host, pattern) for pattern in policy.allowed_hosts)
    allowed_networks = [ipaddress.ip_network(value, strict=True) for value in policy.allowed_cidrs]
    normalized: list[str] = []
    for address_text in addresses:
        try:
            address = ipaddress.ip_address(address_text)
        except ValueError as exc:
            raise OutboundTargetError("DNS 返回了无效 IP 地址") from exc
        _reject_blocked_address(address, policy)
        if not host_allowed and not any(address in network for network in allowed_networks):
            raise OutboundTargetError("Webhook 目标不在允许列表中")
        normalized.append(str(address))
    return ValidatedOutboundTarget(
        original_url=url,
        hostname=host,
        port=port,
        resolved_addresses=tuple(normalized),
    )


def validate_trusted_detail_base_url(url: str | None, *, production: bool) -> str | None:
    if url is None:
        return None
    if any(character in url for character in ("\r", "\n", "\x00")):
        raise OutboundTargetError("详情页基础地址包含非法字符")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise OutboundTargetError("详情页基础地址必须是完整 HTTP(S) 地址")
    if production and parsed.scheme != "https":
        raise OutboundTargetError("生产环境详情页基础地址必须使用 HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise OutboundTargetError("详情页基础地址不允许包含用户信息")
    if parsed.query or parsed.fragment:
        raise OutboundTargetError("详情页基础地址不允许包含 query 或 fragment")
    return url.rstrip("/")


def _resolve_all(host: str, port: int) -> tuple[str, ...]:
    return tuple(item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))


def _host_matches(host: str, pattern: str) -> bool:
    normalized = pattern.casefold().rstrip(".")
    if normalized.startswith("*."):
        suffix = normalized[1:]
        return host.endswith(suffix) and host != normalized[2:]
    return host == normalized


def _reject_blocked_address(address, policy: WebhookTargetPolicy) -> None:
    if policy.block_cloud_metadata and address in _CLOUD_METADATA_ADDRESSES:
        raise OutboundTargetError("禁止访问云元数据地址")
    if policy.block_loopback and address.is_loopback:
        raise OutboundTargetError("禁止访问回环地址")
    if policy.block_link_local and address.is_link_local:
        raise OutboundTargetError("禁止访问链路本地地址")
    if policy.block_private_networks and address.is_private:
        raise OutboundTargetError("禁止访问私有网络地址")
    if address.is_multicast or address.is_unspecified or address.is_reserved:
        raise OutboundTargetError("禁止访问非公网目标地址")
