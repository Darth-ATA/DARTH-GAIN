"""FastAPI dependencies for the web dashboard.

Provides:
  - ``get_current_user``: extracts user from session cookie
  - ``require_user``: redirects to login if no session
  - ``get_user_db``: resolves per-user DB path
  - ``get_db``: yields an open per-user SQLite connection (FastAPI Depends)
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Generator
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from darth_gain.db.engine import create_engine
from darth_gain.web.auth import read_session

COOKIE_NAME = "dg_session"


def get_current_user(request: Request) -> dict | None:
    """Extract user info from the session cookie.

    Reads the ``dg_session`` cookie and verifies the signature.
    Returns the user dict or ``None`` if missing/invalid/expired.
    """
    secret_key = getattr(request.app.state, "secret_key", "dev-secret")
    token = request.cookies.get(COOKIE_NAME)
    if token is None:
        return None
    return read_session(token, secret_key)


async def require_user(
    current_user: dict | None = Depends(get_current_user),
) -> dict:
    """Require an authenticated user.

    Raises 401 (or redirects to login) if no valid session exists.
    """
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return current_user


def get_user_db(user_id: int) -> str:
    """Return the per-user SQLite database path.

    Args:
        user_id: The user's numeric ID.

    Returns:
        Path like ``/data/user_{id}/workouts.db``.
    """
    return f"/data/user_{user_id}/workouts.db"


async def get_db(
    request: Request,
    current_user: dict = Depends(require_user),
) -> Generator[sqlite3.Connection, Any, None]:
    """FastAPI dependency that yields an open per-user SQLite connection.

    Resolves the per-user DB path using ``data_dir`` from app state,
    opens the connection with WAL + foreign_keys, and closes on teardown.

    Args:
        request: The incoming HTTP request.
        current_user: The authenticated user dict.

    Yields:
        An open ``sqlite3.Connection`` to the per-user database.
    """
    data_dir: str = getattr(request.app.state, "data_dir", "/data/")
    user_id = current_user["user_id"]
    db_path = os.path.join(data_dir, f"user_{user_id}", "workouts.db")
    conn = create_engine(db_path)
    try:
        yield conn
    finally:
        conn.close()
