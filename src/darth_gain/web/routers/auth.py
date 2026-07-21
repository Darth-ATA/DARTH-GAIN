"""Authentication routes for the web dashboard.

Provides:
  - ``GET /login`` — render login form
  - ``POST /login`` — authenticate user, set session cookie
  - ``GET /logout`` — clear session cookie, redirect to login
  - ``GET /health`` — healthcheck (no auth required)
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from werkzeug.security import check_password_hash

from darth_gain.db.engine import create_engine
from darth_gain.web.auth import create_session
from darth_gain.web.deps import COOKIE_NAME, get_current_user

from ..templates import render_template

router = APIRouter()


def _get_users_db(request: Request) -> sqlite3.Connection:
    """Open a connection to the shared users.db."""
    users_db_path: str = request.app.state.users_db_path  # type: ignore[union-attr]
    return create_engine(users_db_path)


@router.get("/login", response_class=HTMLResponse, response_model=None)
async def login_page(
    request: Request,
    current_user: dict | None = Depends(get_current_user),
):
    """Render the login page.

    If the user is already authenticated, redirect to the dashboard.
    """
    if current_user is not None:
        return RedirectResponse(url="/", status_code=302)
    return render_template("login.html", {"request": request, "error": None})


@router.post("/login", response_model=None)
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
) -> Response:
    """Authenticate a user and set a session cookie.

    Validates credentials against ``users.db``. On success, sets a
    signed ``dg_session`` cookie and redirects to ``/``. On failure,
    returns 401 with an error message.
    """
    conn = _get_users_db(request)
    try:
        row = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    finally:
        conn.close()

    if row is None or not check_password_hash(row["password_hash"], password):
        return render_template(
            "login.html",
            {"request": request, "error": "Invalid username or password"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    secret_key: str = request.app.state.secret_key  # type: ignore[union-attr]
    token = create_session(
        {"user_id": row["id"], "username": row["username"]},
        secret_key,
    )
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=604800,  # 7 days
    )
    return response


@router.get("/logout")
async def logout() -> RedirectResponse:
    """Clear the session cookie and redirect to login."""
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(key=COOKIE_NAME)
    return response


@router.get("/health")
async def health() -> dict[str, str]:
    """Healthcheck endpoint — no auth required."""
    return {"status": "ok"}
