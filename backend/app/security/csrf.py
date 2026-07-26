from __future__ import annotations

import hmac

from app.security.auth import AuthenticatedSession


def csrf_token_matches(authenticated: AuthenticatedSession, supplied: str | None) -> bool:
    if not supplied:
        return False
    return hmac.compare_digest(
        authenticated.csrf_token.encode("utf-8"),
        supplied.encode("utf-8"),
    )
