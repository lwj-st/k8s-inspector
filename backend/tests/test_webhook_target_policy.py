import pytest

from app.schemas.v1_1 import WebhookTargetPolicy
from app.security.outbound import (
    OutboundTargetError,
    validate_outbound_target,
    validate_trusted_detail_base_url,
)


def test_outbound_target_allows_only_allowlisted_public_dns_results() -> None:
    policy = WebhookTargetPolicy(allowed_hosts=["hooks.example.com"])
    result = validate_outbound_target(
        "https://hooks.example.com/v1/events",
        policy,
        production=True,
        resolver=lambda host, port: ["93.184.216.34"],
    )
    assert result.hostname == "hooks.example.com"
    assert result.port == 443
    assert result.resolved_addresses == ("93.184.216.34",)
    result.require_allowed_peer("93.184.216.34")
    with pytest.raises(OutboundTargetError):
        result.require_allowed_peer("93.184.216.35")


@pytest.mark.parametrize(
    ("url", "addresses"),
    [
        ("https://hooks.example.com/path", ["127.0.0.1"]),
        ("https://hooks.example.com/path", ["169.254.169.254"]),
        ("https://hooks.example.com/path", ["10.0.0.1"]),
        ("https://hooks.example.com/path", ["93.184.216.34", "127.0.0.1"]),
        ("https://user@hooks.example.com/path", ["93.184.216.34"]),
        ("https://hooks.example.com/path\r\nHost:internal", ["93.184.216.34"]),
    ],
)
def test_outbound_target_blocks_ssrf_rebinding_and_host_injection(
    url: str,
    addresses: list[str],
) -> None:
    policy = WebhookTargetPolicy(allowed_hosts=["hooks.example.com"])
    with pytest.raises(OutboundTargetError):
        validate_outbound_target(
            url,
            policy,
            production=True,
            resolver=lambda host, port: addresses,
        )


def test_outbound_target_requires_https_in_production_and_allowlist_match() -> None:
    policy = WebhookTargetPolicy(allowed_hosts=["hooks.example.com"])
    with pytest.raises(OutboundTargetError):
        validate_outbound_target(
            "http://hooks.example.com/path",
            policy,
            production=True,
            resolver=lambda host, port: ["93.184.216.34"],
        )
    with pytest.raises(OutboundTargetError):
        validate_outbound_target(
            "https://other.example.com/path",
            policy,
            production=True,
            resolver=lambda host, port: ["93.184.216.35"],
        )


def test_trusted_detail_url_ignores_request_host_by_requiring_static_base() -> None:
    assert (
        validate_trusted_detail_base_url(
            "https://inspector.example.com/ops/",
            production=True,
        )
        == "https://inspector.example.com/ops"
    )
    with pytest.raises(OutboundTargetError):
        validate_trusted_detail_base_url("http://inspector.example.com", production=True)
