"""Tests for multi-user: registration, per-user isolation, scripts.

Strict TDD — tests define the contract before implementation.

Test scenarios:
  - GET /register renders form with all fields
  - POST /register creates user in users.db
  - POST /register creates per-user SQLite database
  - POST /register auto-login (sets session cookie, redirects to /)
  - POST /register duplicate username returns error
  - POST /register short password returns error
  - POST /register password mismatch returns error
  - Registration → dashboard shows empty state
  - Per-user DB isolation (user 1's exercises don't show for user 2)
  - cron-sync-all.py has valid Python syntax and parseable structure
"""

from __future__ import annotations

import os
import re
import sqlite3

import pytest
from werkzeug.security import generate_password_hash


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def client(tmp_path):
    """Return a TestClient with a fresh app using temp data dir."""
    from fastapi.testclient import TestClient

    from darth_gain.web.app import create_app

    app = create_app(
        data_dir=str(tmp_path),
        secret_key="test-secret",
        users_db_path=str(tmp_path / "users.db"),
    )
    with TestClient(app) as c:
        yield c


def _seed_user(users_db_path: str, user_id: int, username: str, password: str) -> None:
    """Insert a user into users.db (table must already exist)."""
    conn = sqlite3.connect(users_db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO users (id, username, password_hash) VALUES (?, ?, ?)",
            (user_id, username, generate_password_hash(password)),
        )
        conn.commit()
    finally:
        conn.close()


# ===========================================================================
# T4 — Registration page renders correctly
# ===========================================================================


class TestRegistrationPage:
    """GET /register renders the registration form."""

    def test_register_page_renders(self, client) -> None:
        """GET /register should render the registration form."""
        response = client.get("/register")
        assert response.status_code == 200
        content = response.text.lower()
        assert "register" in content
        assert "password" in content
        assert "username" in content

    def test_register_page_has_confirm_password_field(self, client) -> None:
        """GET /register should include a confirm password field."""
        response = client.get("/register")
        assert response.status_code == 200
        content = response.text.lower()
        assert "confirm" in content or "confirm_password" in content

    def test_register_page_has_link_to_login(self, client) -> None:
        """GET /register should have a link to the login page."""
        response = client.get("/register")
        assert response.status_code == 200
        content = response.text.lower()
        assert "/login" in content or "login" in content

    def test_register_redirects_when_logged_in(self, client, tmp_path) -> None:
        """GET /register should redirect to / if user is already authenticated."""
        from darth_gain.web.auth import create_session

        _seed_user(str(tmp_path / "users.db"), 1, "alice", "pass")
        token = create_session({"user_id": 1, "username": "alice"}, "test-secret")
        client.cookies.set("dg_session", token)

        response = client.get("/register", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers.get("location") == "/"


# ===========================================================================
# T4 — Registration creates user
# ===========================================================================


class TestRegistrationCreatesUser:
    """POST /register creates a user in users.db."""

    def test_register_creates_user_row(self, client, tmp_path) -> None:
        """POST /register should insert a new user row into users.db."""
        client.post(
            "/register",
            data={"username": "bob", "password": "secure123", "confirm_password": "secure123"},
        )
        conn = sqlite3.connect(str(tmp_path / "users.db"))
        try:
            row = conn.execute(
                "SELECT id, username, password_hash FROM users WHERE username = ?",
                ("bob",),
            ).fetchone()
            # sqlite3 without Row factory — use tuple access
            assert row is not None, "User 'bob' should exist in users.db"
            assert row[1] == "bob"
            # password_hash should be bcrypt hash (not plain text)
            assert row[2].startswith("scrypt") or row[2].startswith("$2"), (
                "Password must be hashed, not stored in plain text"
            )
        finally:
            conn.close()

    def test_register_creates_per_user_db(self, client, tmp_path) -> None:
        """POST /register should create per-user SQLite file with all tables."""
        client.post(
            "/register",
            data={"username": "bob", "password": "secure123", "confirm_password": "secure123"},
        )

        # Find the user's id
        conn = sqlite3.connect(str(tmp_path / "users.db"))
        try:
            user_id = conn.execute(
                "SELECT id FROM users WHERE username = ?", ("bob",)
            ).fetchone()[0]
        finally:
            conn.close()

        user_db = tmp_path / f"user_{user_id}" / "workouts.db"
        assert user_db.exists(), f"Per-user DB should exist at {user_db}"

        # Verify tables exist
        uconn = sqlite3.connect(str(user_db))
        try:
            tables = {
                r[0]
                for r in uconn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "workouts" in tables
            assert "exercise_templates" in tables
            assert "progression_config" in tables
            assert "progression_history" in tables
        finally:
            uconn.close()

    def test_register_auto_login(self, client) -> None:
        """POST /register should set session cookie and redirect to /."""
        response = client.post(
            "/register",
            data={"username": "bob", "password": "secure123", "confirm_password": "secure123"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers.get("location") == "/"
        set_cookie = response.headers.get("set-cookie", "")
        assert "dg_session=" in set_cookie


# ===========================================================================
# T4 — Registration validation
# ===========================================================================


class TestRegistrationValidation:
    """POST /register input validation."""

    def test_duplicate_username_returns_error(self, client, tmp_path) -> None:
        """POST /register with existing username should return error."""
        # First registration
        client.post(
            "/register",
            data={"username": "bob", "password": "secure123", "confirm_password": "secure123"},
        )
        # Second with same username
        response = client.post(
            "/register",
            data={"username": "bob", "password": "secure456", "confirm_password": "secure456"},
        )
        assert response.status_code in (409, 422)
        content = response.text.lower()
        assert "already taken" in content or "already exists" in content or "duplicate" in content

    def test_short_password_returns_error(self, client) -> None:
        """POST /register with password < 6 chars should return error."""
        response = client.post(
            "/register",
            data={"username": "bob", "password": "12345", "confirm_password": "12345"},
        )
        assert response.status_code == 422
        content = response.text.lower()
        assert "6" in content or "at least" in content or "short" in content

    def test_password_mismatch_returns_error(self, client) -> None:
        """POST /register with mismatched passwords should return error."""
        response = client.post(
            "/register",
            data={
                "username": "bob",
                "password": "secure123",
                "confirm_password": "different456",
            },
        )
        assert response.status_code == 422
        content = response.text.lower()
        assert "match" in content or "mismatch" in content or "not the same" in content

    def test_empty_username_returns_error(self, client) -> None:
        """POST /register with empty username should return error."""
        response = client.post(
            "/register",
            data={"username": "", "password": "secure123", "confirm_password": "secure123"},
        )
        assert response.status_code == 422
        content = response.text.lower()
        assert "required" in content or "empty" in content

    def test_empty_password_returns_error(self, client) -> None:
        """POST /register with empty password should return error."""
        response = client.post(
            "/register",
            data={"username": "bob", "password": "", "confirm_password": ""},
        )
        assert response.status_code == 422


# ===========================================================================
# T4 — Auto-login after registration
# ===========================================================================


class TestRegistrationAutoLogin:
    """After registration, user can access dashboard without separate login."""

    def test_register_then_dashboard_shows_empty(self, client, tmp_path) -> None:
        """After registration, GET / should show dashboard (not redirect to login)."""
        response = client.post(
            "/register",
            data={"username": "alice", "password": "secure123", "confirm_password": "secure123"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        # Extract session cookie from response
        set_cookie = response.headers.get("set-cookie", "")
        match = re.search(r"dg_session=([^;]+)", set_cookie)
        assert match, "Should set dg_session cookie"
        token = match.group(1)

        # Access dashboard with the session cookie
        dash = client.get(
            "/",
            cookies={"dg_session": token},
            follow_redirects=False,
        )
        # Should render dashboard (200), not redirect to login
        assert dash.status_code == 200, (
            "Auto-login should allow dashboard access without separate login"
        )
        content = dash.text.lower()
        assert "no exercises" in content or "no data" in content or "sync" in content


# ===========================================================================
# T4 — Per-user DB isolation
# ===========================================================================


class TestPerUserIsolation:
    """Each user's data is isolated in their own database."""

    def _register_user(
        self, client, tmp_path, username: str, password: str
    ) -> tuple[int, str]:
        """Register a user and return (user_id, session_token)."""
        from darth_gain.web.auth import create_session

        # We'll seed users directly for reliability
        _seed_user(str(tmp_path / "users.db"), None, username, password)
        # Get the actual user id
        conn = sqlite3.connect(str(tmp_path / "users.db"))
        try:
            row = conn.execute(
                "SELECT id FROM users WHERE username = ?", (username,)
            ).fetchone()
            user_id = row[0]
        finally:
            conn.close()

        token = create_session(
            {"user_id": user_id, "username": username}, "test-secret"
        )
        return user_id, token

    def _seed_exercise_data(self, db_path: str, template_id: str, name: str) -> None:
        """Seed exercise data into a per-user database."""
        from darth_gain.db.engine import create_engine, create_tables

        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = create_engine(db_path)
        try:
            create_tables(conn)
            conn.execute(
                "INSERT OR IGNORE INTO exercise_templates "
                "(id, title, type, primary_muscle_group) VALUES (?, ?, 'strength', 'Chest')",
                (template_id, name),
            )
            conn.commit()
        finally:
            conn.close()

    def test_users_see_only_their_exercises(self, client, tmp_path) -> None:
        """User 1's exercises should not appear on User 2's dashboard."""
        # Register user 1 with exercise data
        uid1, token1 = self._register_user(client, tmp_path, "alice", "pass1")
        db1 = str(tmp_path / f"user_{uid1}" / "workouts.db")
        self._seed_exercise_data(db1, "t001", "Bench Press")

        # Register user 2 with NO exercise data
        uid2, token2 = self._register_user(client, tmp_path, "bob", "pass2")
        db2 = str(tmp_path / f"user_{uid2}" / "workouts.db")
        self._seed_exercise_data(db2, "t002", "Deadlift")

        # User 1 should see their exercises
        dash1 = client.get("/", cookies={"dg_session": token1})
        assert dash1.status_code == 200
        assert "Bench Press" in dash1.text
        # User 1 should NOT see user 2's exercises
        assert "Deadlift" not in dash1.text

        # User 2 should see their exercises
        dash2 = client.get("/", cookies={"dg_session": token2})
        assert dash2.status_code == 200
        assert "Deadlift" in dash2.text
        # User 2 should NOT see user 1's exercises
        assert "Bench Press" not in dash2.text


# ===========================================================================
# T4 — Script validation
# ===========================================================================


class TestCronSyncAllScript:
    """cron-sync-all.py parses and has valid structure."""

    SCRIPT_PATH = "scripts/cron-sync-all.py"

    def test_script_exists(self) -> None:
        """cron-sync-all.py should exist."""
        assert os.path.exists(self.SCRIPT_PATH), (
            f"{self.SCRIPT_PATH} should exist"
        )

    def test_script_has_valid_syntax(self) -> None:
        """cron-sync-all.py should have valid Python syntax."""
        import ast

        with open(self.SCRIPT_PATH) as f:
            source = f.read()
        tree = ast.parse(source)
        # Verify it's a valid module (no SyntaxError)
        assert isinstance(tree, ast.Module)


class TestMigrateScript:
    """migrate-to-multi-user.py parses and has valid structure."""

    SCRIPT_PATH = "scripts/migrate-to-multi-user.py"

    def test_script_exists(self) -> None:
        """migrate-to-multi-user.py should exist."""
        assert os.path.exists(self.SCRIPT_PATH), (
            f"{self.SCRIPT_PATH} should exist"
        )

    def test_script_has_valid_syntax(self) -> None:
        """migrate-to-multi-user.py should have valid Python syntax."""
        import ast

        with open(self.SCRIPT_PATH) as f:
            source = f.read()
        tree = ast.parse(source)
        assert isinstance(tree, ast.Module)
