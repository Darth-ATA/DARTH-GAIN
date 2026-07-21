"""Tests for web auth: session management, login/logout routes.

Tests cover:
  - create_session / read_session with itsdangerous
  - Session expiry, tampering, key mismatch
  - GET /login renders form
  - POST /login validates credentials
  - GET /logout clears session
"""

from __future__ import annotations

import sqlite3

import pytest
from werkzeug.security import generate_password_hash


# ===========================================================================
# T3 — Auth module (pure functions)
# ===========================================================================


class TestSessionManagement:
    """create_session and read_session with itsdangerous."""

    def test_create_session_returns_string(self) -> None:
        """create_session should return a non-empty string token."""
        from darth_gain.web.auth import create_session

        token = create_session({"user_id": 1, "username": "alice"}, "secret")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_read_session_returns_data(self) -> None:
        """read_session should recover original data from valid token."""
        from darth_gain.web.auth import create_session, read_session

        data = {"user_id": 1, "username": "alice"}
        token = create_session(data, "secret")
        result = read_session(token, "secret")
        assert result == data

    def test_expired_session_returns_none(self) -> None:
        """read_session with negative max_age should treat token as expired."""
        from darth_gain.web.auth import create_session, read_session

        data = {"user_id": 1, "username": "alice"}
        token = create_session(data, "secret")
        result = read_session(token, "secret", max_age=-1)
        assert result is None

    def test_tampered_session_returns_none(self) -> None:
        """A modified token should fail signature verification."""
        from darth_gain.web.auth import create_session, read_session

        data = {"user_id": 1, "username": "alice"}
        token = create_session(data, "secret")
        # Append junk to tamper
        result = read_session(token + "x", "secret")
        assert result is None

    def test_different_key_fails(self) -> None:
        """Token signed with one key should not verify with another."""
        from darth_gain.web.auth import create_session, read_session

        data = {"user_id": 1, "username": "alice"}
        token = create_session(data, "key_a")
        result = read_session(token, "key_b")
        assert result is None


# ===========================================================================
# T3 — Login / Logout routes
# ===========================================================================


def _seed_user(db_path: str, username: str, password: str) -> None:
    """Insert a user into the users.db for testing."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, generate_password_hash(password)),
        )
        conn.commit()
    finally:
        conn.close()


class TestLoginRoutes:
    """GET /login and POST /login behavior."""

    @pytest.fixture
    def client(self, tmp_path):
        from fastapi.testclient import TestClient

        from darth_gain.web.app import create_app

        users_db = tmp_path / "users.db"
        app = create_app(
            data_dir=str(tmp_path),
            secret_key="test-secret",
            users_db_path=str(users_db),
        )
        with TestClient(app) as c:
            yield c

    def test_login_page_renders(self, client) -> None:
        """GET /login should render the login form."""
        response = client.get("/login")
        assert response.status_code == 200
        content = response.text.lower()
        assert "login" in content
        assert "password" in content or "Password" in content
        assert "username" in content

    def test_successful_login_redirects_with_cookie(self, client, tmp_path) -> None:
        """POST /login with valid creds should 302 to / and set session cookie."""
        users_db = tmp_path / "users.db"
        _seed_user(str(users_db), "alice", "correct")

        response = client.post(
            "/login",
            data={"username": "alice", "password": "correct"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers.get("location") == "/"
        # Should have a session cookie set
        set_cookie = response.headers.get("set-cookie", "")
        assert "session=" in set_cookie or "dg_session=" in set_cookie

    def test_wrong_password_returns_401(self, client, tmp_path) -> None:
        """POST /login with wrong password should return 401."""
        users_db = tmp_path / "users.db"
        _seed_user(str(users_db), "alice", "correct")

        response = client.post(
            "/login",
            data={"username": "alice", "password": "wrong"},
            follow_redirects=False,
        )
        assert response.status_code == 401

    def test_nonexistent_user_returns_401(self, client) -> None:
        """POST /login with unknown user should return 401 (not reveal existence)."""
        response = client.post(
            "/login",
            data={"username": "nobody", "password": "x"},
            follow_redirects=False,
        )
        assert response.status_code == 401


class TestLogoutRoutes:
    """GET /logout behavior."""

    @pytest.fixture
    def auth_client(self, tmp_path):
        """Return a TestClient with a logged-in session."""
        from fastapi.testclient import TestClient

        from darth_gain.web.auth import create_session
        from darth_gain.web.app import create_app

        users_db = tmp_path / "users.db"

        app = create_app(
            data_dir=str(tmp_path),
            secret_key="test-secret",
            users_db_path=str(users_db),
        )
        with TestClient(app) as c:
            # Seed user AFTER lifespan creates the table
            _seed_user(str(users_db), "alice", "correct")
            # Login
            resp = c.post(
                "/login",
                data={"username": "alice", "password": "correct"},
                follow_redirects=False,
            )
            assert resp.status_code == 302  # sanity
            yield c

    def test_logout_clears_session(self, auth_client) -> None:
        """GET /logout should clear the session cookie and redirect to login."""
        response = auth_client.get("/logout", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers.get("location") == "/login"
        # Cookie should be cleared (max-age=0 or expires in past)
        set_cookie = response.headers.get("set-cookie", "").lower()
        assert "max-age=0" in set_cookie or "expires=thu, 01 jan 1970" in set_cookie


class TestAuthDeps:
    """get_current_user and require_user dependencies."""

    @pytest.fixture
    def app_and_client(self, tmp_path):
        """App with a protected test route to exercise deps."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from darth_gain.web.app import create_app
        from darth_gain.web.deps import get_current_user, require_user

        users_db = tmp_path / "users.db"
        app = create_app(
            data_dir=str(tmp_path),
            secret_key="test-secret",
            users_db_path=str(users_db),
        )

        # Add a protected test route
        from fastapi import Depends

        @app.get("/protected")
        def _protected(current_user: dict = Depends(require_user)):
            return {"user_id": current_user["user_id"]}

        with TestClient(app) as c:
            yield c

    def test_unauthenticated_redirects_to_login(self, app_and_client) -> None:
        """Without session cookie, protected route should redirect to /login."""
        response = app_and_client.get("/protected", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers.get("location") == "/login"

    def test_authenticated_user_passes(self, app_and_client, tmp_path) -> None:
        """With valid session cookie, protected route should return user data."""
        from darth_gain.web.auth import create_session

        # Create a valid session cookie
        token = create_session({"user_id": 1, "username": "alice"}, "test-secret")

        response = app_and_client.get(
            "/protected",
            cookies={"dg_session": token},
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert response.json() == {"user_id": 1}

    def test_tampered_cookie_redirects(self, app_and_client) -> None:
        """Tampered session cookie should redirect to login."""
        response = app_and_client.get(
            "/protected",
            cookies={"dg_session": "tampered.token.here"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers.get("location") == "/login"


class TestUserDbPath:
    """get_user_db resolves correct per-user path."""

    def test_get_user_db_returns_correct_path(self) -> None:
        """get_user_db should return /data/user_{id}/workouts.db."""
        from darth_gain.web.deps import get_user_db

        path = get_user_db(7)
        assert path.endswith("/user_7/workouts.db")
