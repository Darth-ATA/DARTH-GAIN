"""FastAPI application factory for the DARTH-GAIN web dashboard.

Provides:
  - ``create_app()`` — build and configure a FastAPI instance
  - Lifespan management (startup: ensure data dir, create tables)
  - Static file serving, Jinja2 templates, router registration
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from darth_gain.db.engine import create_engine, create_tables
from darth_gain.web.routers import auth, dashboard


def _resolve_static_dir() -> str:
    """Return the path to the package's static directory."""
    return str(Path(__file__).resolve().parent / "static")


def create_app(
    data_dir: str = "/data/",
    secret_key: str | None = None,
    users_db_path: str | None = None,
    static_dir: str | None = None,
    **kwargs: Any,
) -> FastAPI:
    """Create and configure the DARTH-GAIN web FastAPI application.

    Args:
        data_dir: Directory for per-user data (default: ``/data/``).
        secret_key: Secret for session signing. Falls back to
            ``DARTH_GAIN_SECRET`` env var, then ``"dev-secret"``.
        users_db_path: Path to the shared users database. Defaults to
            ``<data_dir>/users.db``.
        static_dir: Path to static assets. Defaults to the package's
            ``static/`` directory.
        **kwargs: Additional arguments passed to the FastAPI constructor.

    Returns:
        A configured FastAPI application instance.
    """
    if secret_key is None:
        secret_key = os.environ.get("DARTH_GAIN_SECRET", "dev-secret")
    if users_db_path is None:
        users_db_path = os.path.join(data_dir, "users.db")
    if static_dir is None:
        static_dir = _resolve_static_dir()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        """Handle application startup and shutdown."""
        # Ensure data directory exists
        os.makedirs(data_dir, exist_ok=True)
        # Ensure users.db directory exists
        users_dir = os.path.dirname(users_db_path)
        if users_dir:
            os.makedirs(users_dir, exist_ok=True)
        # Create users table
        conn = create_engine(users_db_path)
        try:
            create_tables(conn)
        finally:
            conn.close()

        # Store config in app state
        _app.state.secret_key = secret_key
        _app.state.users_db_path = users_db_path
        _app.state.data_dir = data_dir
        yield

    app = FastAPI(
        title="DARTH-GAIN Web Dashboard",
        lifespan=lifespan,
        **kwargs,
    )

    # Mount static files
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Register routers
    app.include_router(auth.router)
    app.include_router(dashboard.router)

    # Auth exception handler — redirect 401 to login page
    @app.exception_handler(HTTPException)
    async def _auth_exception_handler(request: Request, exc: HTTPException):
        if exc.status_code == 401:
            return RedirectResponse(url="/login", status_code=302)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    return app
