"""In-memory TLS Secret parsing without retaining certificate or key bytes."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import serialization


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def dns_name_matches(host: str, pattern: str) -> bool:
    normalized_host = host.casefold().rstrip(".")
    normalized_pattern = pattern.casefold().rstrip(".")
    if normalized_host == normalized_pattern:
        return True
    if not normalized_pattern.startswith("*."):
        return False
    suffix = normalized_pattern[2:]
    return (
        normalized_host.endswith(f".{suffix}")
        and normalized_host.count(".") == suffix.count(".") + 1
    )


def parse_tls_secret(
    secret: Any,
    hosts: set[str],
    *,
    now: datetime,
) -> dict[str, Any]:
    """Return sanitized certificate facts and never expose private-key content."""

    data = getattr(secret, "data", None) or {}
    certificate_value = data.get("tls.crt")
    key_value = data.get("tls.key")
    secret_type = str(getattr(secret, "type", "") or "")
    base: dict[str, Any] = {
        "exists": True,
        "parse_ok": False,
        "hosts": sorted(hosts)[:50],
        "secret_type": secret_type,
    }
    if (
        secret_type != "kubernetes.io/tls"
        or not certificate_value
        or not key_value
    ):
        return base
    try:
        certificate_bytes = base64.b64decode(certificate_value, validate=True)
        key_bytes = base64.b64decode(key_value, validate=True)
        certificate = x509.load_pem_x509_certificate(certificate_bytes)
        private_key = serialization.load_pem_private_key(key_bytes, password=None)
        public_cert = certificate.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        public_key = private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        try:
            sans = certificate.extensions.get_extension_for_class(
                x509.SubjectAlternativeName
            ).value.get_values_for_type(x509.DNSName)
        except x509.ExtensionNotFound:
            sans = []
        not_after = getattr(certificate, "not_valid_after_utc", None) or _aware(
            certificate.not_valid_after
        )
        not_before = getattr(certificate, "not_valid_before_utc", None) or _aware(
            certificate.not_valid_before
        )
        return {
            **base,
            "parse_ok": True,
            "key_match": public_cert == public_key,
            "host_match": all(
                any(dns_name_matches(host, san) for san in sans)
                for host in hosts
            ),
            "sans": sans[:50],
            "not_before": not_before.isoformat() if not_before else "",
            "not_after": not_after.isoformat() if not_after else "",
            "days_until_expiry": (
                (not_after - now).total_seconds() / 86400
                if not_after
                else 0.0
            ),
            "not_yet_valid": bool(not_before and not_before > now),
        }
    except Exception:
        return base
    finally:
        # Best effort: drop decoded input references at function exit.
        certificate_value = key_value = None
