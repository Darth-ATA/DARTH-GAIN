"""Authentication routes for the web dashboard.

Provides:
  - ``GET /login`` — render login form
  - ``POST /login`` — authenticate user, set session cookie
  - ``GET /register`` — render registration form
  - ``POST /register`` — create user, per-user DB, auto-login
  - ``GET /logout`` — clear session cookie, redirect to login
  - ``GET /health`` — healthcheck (no auth required)
"""

from __future__ import annotations

import os
import sqlite3

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from werkzeug.security import check_password_hash, generate_password_hash

from darth_gain.db.engine import create_engine, create_tables
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


@router.get("/register", response_class=HTMLResponse, response_model=None)
async def register_page(
    request: Request,
    current_user: dict | None = Depends(get_current_user),
):
    """Render the registration page.

    If the user is already authenticated, redirect to the dashboard.
    """
    if current_user is not None:
        return RedirectResponse(url="/", status_code=302)
    return render_template("register.html", {"request": request, "error": None})


@router.post("/register", response_model=None)
async def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(""),
) -> Response:
    """Register a new user, create per-user DB, and auto-login.

    Validates input (non-empty, min length, uniqueness), hashes the
    password with werkzeug, creates the user in ``users.db``, creates
    a per-user database at ``/data/user_{id}/workouts.db``, sets a
    session cookie, and redirects to the dashboard.
    """
    username = username.strip()

    # --- Input validation -------------------------------------------------
    if not username:
        return render_template(
            "register.html",
            {"request": request, "error": "Username is required"},
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if not password:
        return render_template(
            "register.html",
            {"request": request, "error": "Password is required"},
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if len(password) < 6:
        return render_template(
            "register.html",
            {"request": request, "error": "Password must be at least 6 characters"},
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if password != confirm_password:
        return render_template(
            "register.html",
            {"request": request, "error": "Passwords do not match"},
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    # --- Check duplicate username & create user --------------------------
    conn = _get_users_db(request)
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing is not None:
            return render_template(
                "register.html",
                {"request": request, "error": "Username already taken"},
                status_code=status.HTTP_409_CONFLICT,
            )

        password_hash = generate_password_hash(password)
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )
        user_id: int = cursor.lastrowid  # type: ignore[assignment]
        conn.commit()
    finally:
        conn.close()

    # --- Create per-user database ----------------------------------------
    data_dir: str = request.app.state.data_dir  # type: ignore[union-attr]
    user_db_dir = os.path.join(data_dir, f"user_{user_id}")
    os.makedirs(user_db_dir, exist_ok=True)
    user_db_path = os.path.join(user_db_dir, "workouts.db")
    user_conn = create_engine(user_db_path)
    try:
        create_tables(user_conn)
    finally:
        user_conn.close()

    # --- Auto-login (set session cookie) ---------------------------------
    secret_key: str = request.app.state.secret_key  # type: ignore[union-attr]
    token = create_session(
        {"user_id": user_id, "username": username}, secret_key,
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


@router.get("/health")
async def health() -> dict[str, str]:
    """Healthcheck endpoint — no auth required."""
    return {"status": "ok"}
