"""Session management for the web dashboard.

Uses ``itsdangerous.URLSafeTimedSerializer`` to create signed cookies
that cannot be tampered with. Sessions expire after 7 days by default.
"""

from __future__ import annotations

from itsdangerous import URLSafeTimedSerializer


def create_session(data: dict, secret_key: str) -> str:
    """Create a signed session cookie string.

    Args:
        data: Session payload (e.g. ``{"user_id": 1, "username": "alice"}``).
        secret_key: Secret key for signing.

    Returns:
        A URL-safe signed token string.
    """
    s = URLSafeTimedSerializer(secret_key)
    return s.dumps(data)


def read_session(
    token: str,
    secret_key: str,
    max_age: int = 604800,
) -> dict | None:
    """Verify and decode a signed session cookie.

    Args:
        token: The signed token from the cookie.
        secret_key: Secret key used for signing.
        max_age: Maximum age in seconds (default 7 days).

    Returns:
        The original session data dict, or ``None`` if the token is
        invalid, expired, or tampered with.
    """
    s = URLSafeTimedSerializer(secret_key)
    try:
        return s.loads(token, max_age=max_age)
    except Exception:
        return None
