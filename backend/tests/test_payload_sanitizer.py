import pytest

from app.services.payload_sanitizer import (
    sanitize_persistence_payload,
    sanitize_public_payload,
)


@pytest.mark.parametrize(
    "text",
    [
        "password=hunter2",
        "PASSWD: 'hunter2'",
        'event={"token":"eyJhbGciOiJIUzI1NiJ9.value"}',
        "access_token = access-value",
        "refresh-token: refresh-value",
        "Session Token=session-value",
        'payload={"client_secret":"client-value"}',
        "signing_secret: signing-value",
        "api-key=api-value",
        "X-Api-Key: x-api-value",
        "Authorization: Basic dXNlcjpwYXNz",
        "Bearer eyJhbGciOiJIUzI1NiJ9.value",
        "Cookie: session=plain-session",
        "https://open.feishu.cn/open-apis/bot/v2/hook/plain-hook-token",
        (
            "-----BEGIN PRIVATE KEY-----\n"
            "plain-private-key\n"
            "-----END PRIVATE KEY-----"
        ),
    ],
)
def test_public_sanitizer_redacts_sensitive_text_variants(text: str) -> None:
    result = sanitize_public_payload(
        {
            "events": [
                {
                    "message": f"non-sensitive ERROR; {text}",
                }
            ]
        }
    )

    message = result["events"][0]["message"]
    assert "non-sensitive ERROR" in message
    assert (
        "hunter2" not in message
        and "plain-" not in message
        and "eyJhbGciOiJIUzI1NiJ9" not in message
        and "dXNlcjpwYXNz" not in message
        and "access-value" not in message
        and "refresh-value" not in message
        and "session-value" not in message
        and "client-value" not in message
        and "signing-value" not in message
        and "api-value" not in message
        and "x-api-value" not in message
    )
    assert "[REDACTED]" in message


def test_public_sanitizer_preserves_nested_shape_and_redacts_sensitive_keys() -> None:
    payload = {
        "facts": {
            "password": "plain-password",
            "nested": [
                {"access-token": "plain-access"},
                {"summary": ["ERROR", "token=plain-token"]},
            ],
        },
        "tls_secrets": [{"name": "demo-tls"}],
    }

    result = sanitize_public_payload(payload)

    assert result == {
        "facts": {
            "password": "[REDACTED]",
            "nested": [
                {"access-token": "[REDACTED]"},
                {"summary": ["ERROR", "token=[REDACTED]"]},
            ],
        },
        "tls_secrets": [{"name": "demo-tls"}],
    }
    assert payload["facts"]["password"] == "plain-password"


@pytest.mark.parametrize(
    "text",
    [
        "token bucket is saturated",
        "secret-controller pod restarted",
        "service account token projection is enabled",
        "webhook controller is healthy",
    ],
)
def test_public_sanitizer_does_not_over_redact_non_sensitive_phrases(
    text: str,
) -> None:
    assert sanitize_public_payload(text) == text


def test_persistence_sanitizer_removes_raw_logs_and_records_metadata() -> None:
    payload = {
        "matches": [
            {
                "matched_text": "password=plain-password " + ("x" * 3000),
                "container_log_summaries": {"api": "raw log"},
                "facts": {"client_secret": "plain-client-secret"},
            }
        ]
    }

    result = sanitize_persistence_payload(payload)

    match = result["matches"][0]
    assert "container_log_summaries" not in match
    assert "plain-password" not in match["matched_text"]
    assert match["matched_text"].endswith("…（已截断）")
    assert match["facts"]["client_secret"] == "[REDACTED]"
    assert result["_persistence_sanitization"] == {
        "raw_logs_removed": True,
        "sensitive_values_redacted": True,
        "truncated": True,
    }


def test_public_sanitizer_bounds_arbitrary_nested_string_arrays() -> None:
    result = sanitize_public_payload(
        {"coverage": {"reasons": [["ERROR " + ("x" * 5000)]]}}
    )

    reason = result["coverage"]["reasons"][0][0]
    assert reason.startswith("ERROR ")
    assert reason.endswith("…（已截断）")
    assert len(reason) < 5000
