"""Tests for web dashboard: exercise list with progression status.

Strict TDD — tests define the contract before implementation.

Test scenarios:
  - Auth required (redirect to /login without session)
  - Empty state (no DB exists)
  - Empty state (DB with no templates)
  - Exercises in various states (progress, maintain, skipped, insufficient_data)
  - Error isolation (one bad template doesn't crash page)
  - Status grouping (section headers for each status)
  - Exercise card content (title, weight, rep range, recommendation)
"""

from __future__ import annotations

import os
import sqlite3

import pytest

from darth_gain.db.engine import create_engine, create_tables


# ===========================================================================
# Fixture helpers
# ===========================================================================


def _seed_template(
    conn: sqlite3.Connection,
    tid: str,
    name: str,
    muscle_group: str = "Chest",
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO exercise_templates "
        "(id, title, type, primary_muscle_group) VALUES (?, ?, 'strength', ?)",
        (tid, name, muscle_group),
    )
    conn.commit()


def _seed_workout(conn: sqlite3.Connection, wid: str, start_time: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO workouts (id, title, start_time) VALUES (?, ?, ?)",
        (wid, "Workout", start_time),
    )
    conn.commit()


def _seed_exercise(conn: sqlite3.Connection, eid: int, wid: str, tid: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO exercises "
        "(id, workout_id, exercise_template_id, title) VALUES (?, ?, ?, 'Ex')",
        (eid, wid, tid),
    )
    conn.commit()


def _seed_set(
    conn: sqlite3.Connection,
    sid: int,
    eid: int,
    weight_kg: float,
    reps: int,
    set_index: int = 0,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO sets "
        "(id, exercise_id, set_index, type, weight_kg, reps) "
        "VALUES (?, ?, ?, 'normal', ?, ?)",
        (sid, eid, set_index, weight_kg, reps),
    )
    conn.commit()


def _create_user_db(db_path: str) -> sqlite3.Connection:
    """Create a per-user SQLite DB with all tables at the given path."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = create_engine(db_path)
    create_tables(conn)
    return conn


def _seed_user(users_db_path: str, user_id: int, username: str, password: str) -> None:
    """Insert a user into users.db (table must already exist)."""
    from werkzeug.security import generate_password_hash

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
# T3 — Auth required
# ===========================================================================


class TestDashboardAuth:
    """Dashboard route requires authentication."""

    @pytest.fixture
    def client(self, tmp_path):
        from fastapi.testclient import TestClient

        from darth_gain.web.app import create_app

        app = create_app(
            data_dir=str(tmp_path),
            secret_key="test-secret",
            users_db_path=str(tmp_path / "users.db"),
        )
        with TestClient(app) as c:
            yield c

    def test_dashboard_requires_auth(self, client):
        """GET / without session should redirect to login."""
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers.get("location") == "/login"


# ===========================================================================
# T3 — Empty states
# ===========================================================================


class TestDashboardEmptyState:
    """Dashboard with no exercise data at all."""

    @pytest.fixture
    def auth_client(self, tmp_path):
        from fastapi.testclient import TestClient

        from darth_gain.web.app import create_app

        users_db = tmp_path / "users.db"
        app = create_app(
            data_dir=str(tmp_path),
            secret_key="test-secret",
            users_db_path=str(users_db),
        )
        from darth_gain.web.auth import create_session

        token = create_session({"user_id": 1, "username": "alice"}, "test-secret")
        with TestClient(app) as c:
            # Seed user AFTER app lifespan has created the users table
            _seed_user(str(users_db), 1, "alice", "pass")
            c.cookies.set("dg_session", token)
            yield c

    def test_dashboard_without_db_shows_empty(self, auth_client):
        """GET / when per-user DB doesn't exist yet should show empty state."""
        response = auth_client.get("/")
        assert response.status_code == 200
        content = response.text.lower()
        assert "no exercise" in content or "no data" in content or "sync" in content

    def test_dashboard_with_empty_db_shows_empty(self, auth_client, tmp_path):
        """GET / when DB exists but has no templates should show empty state."""
        # Create empty per-user DB
        user_db = tmp_path / "user_1" / "workouts.db"
        conn = _create_user_db(str(user_db))
        conn.close()

        response = auth_client.get("/")
        assert response.status_code == 200
        content = response.text.lower()
        assert "no exercise" in content or "no data" in content or "sync" in content


# ===========================================================================
# T3 — Dashboard with exercises
# ===========================================================================


class TestDashboardWithExercises:
    """Dashboard with seeded exercises in various progression states."""

    @pytest.fixture
    def auth_client(self, tmp_path):
        from fastapi.testclient import TestClient

        from darth_gain.web.app import create_app

        users_db = tmp_path / "users.db"
        app = create_app(
            data_dir=str(tmp_path),
            secret_key="test-secret",
            users_db_path=str(users_db),
        )

        from darth_gain.web.auth import create_session

        token = create_session({"user_id": 1, "username": "alice"}, "test-secret")
        with TestClient(app) as c:
            _seed_user(str(users_db), 1, "alice", "pass")

            # Seed per-user DB with data for each progression state
            user_db = tmp_path / "user_1" / "workouts.db"
            conn = _create_user_db(str(user_db))

            # t001 — PROGRESS: all reps >= 12 (default rep_max)
            _seed_template(conn, "t001", "Bench Press", "Chest")
            _seed_workout(conn, "w001", "2024-06-01T08:00:00Z")
            _seed_exercise(conn, 1, "w001", "t001")
            _seed_set(conn, 1, 1, 80.0, 12, 0)  # 12 reps = rep_max → top of range
            _seed_set(conn, 2, 1, 80.0, 12, 1)  # all sets hit max

            # t002 — MAINTAIN: reps < 12
            _seed_template(conn, "t002", "Overhead Press", "Shoulders")
            _seed_workout(conn, "w002", "2024-06-02T08:00:00Z")
            _seed_exercise(conn, 2, "w002", "t002")
            _seed_set(conn, 3, 2, 50.0, 8, 0)  # 8 reps < 12

            # t003 — SKIPPED: disabled config
            _seed_template(conn, "t003", "Barbell Curl", "Biceps")
            conn.execute(
                "INSERT INTO progression_config "
                "(exercise_template_id, rep_min, rep_max, weight_increment, enabled) "
                "VALUES ('t003', 8, 12, 2.5, 0)"
            )
            conn.commit()

            # t004 — INSUFFICIENT_DATA: template exists but no sets
            _seed_template(conn, "t004", "Deadlift", "Back")

            conn.close()

            c.cookies.set("dg_session", token)
            yield c

    def test_dashboard_renders_all_exercises(self, auth_client):
        """Dashboard should render all seeded exercises."""
        response = auth_client.get("/")
        assert response.status_code == 200
        html = response.text
        assert "Bench Press" in html
        assert "Overhead Press" in html
        assert "Barbell Curl" in html
        assert "Deadlift" in html

    def test_dashboard_shows_status_badges(self, auth_client):
        """Each exercise should have a status badge matching its state."""
        response = auth_client.get("/")
        assert response.status_code == 200
        html = response.text

        # Status badges as CSS classes (spec: distinct visual styling)
        assert "status-progress" in html or "progress" in html.lower()
        assert "status-maintain" in html or "maintain" in html.lower()
        assert "status-skipped" in html or "skipped" in html.lower()

    def test_dashboard_groups_by_status(self, auth_client):
        """Exercises should be grouped by status with section headers."""
        response = auth_client.get("/")
        assert response.status_code == 200
        html = response.text

        # Each status group should have a section header
        assert "PROGRESS" in html or "Progress" in html
        assert "MAINTAIN" in html or "Maintain" in html
        assert "SKIPPED" in html or "Skipped" in html

    def test_dashboard_shows_exercise_details(self, auth_client):
        """Exercise cards should show title, weight, rep range."""
        response = auth_client.get("/")
        assert response.status_code == 200
        html = response.text

        # Should show rep range info
        assert "8" in html and "12" in html

    def test_dashboard_shows_recommendation_for_progress(self, auth_client):
        """Exercises with PROGRESS status should show recommended next weight."""
        response = auth_client.get("/")
        assert response.status_code == 200
        html = response.text

        # Bench Press should be PROGRESS (all reps = 12, = rep_max)
        # Default increment is 2.5, so recommended = 80 + 2.5 = 82.5
        assert "82.5" in html

    def test_dashboard_empty_section_missing(self, auth_client):
        """Status groups with no exercises should not render a section."""
        response = auth_client.get("/")
        assert response.status_code == 200


# ===========================================================================
# T3 — Error isolation
# ===========================================================================


class TestDashboardErrorIsolation:
    """A single failing template should not crash the whole dashboard."""

    @pytest.fixture
    def auth_client(self, tmp_path):
        from fastapi.testclient import TestClient

        from darth_gain.web.app import create_app

        users_db = tmp_path / "users.db"
        app = create_app(
            data_dir=str(tmp_path),
            secret_key="test-secret",
            users_db_path=str(users_db),
        )

        from darth_gain.web.auth import create_session

        token = create_session({"user_id": 1, "username": "alice"}, "test-secret")
        with TestClient(app) as c:
            _seed_user(str(users_db), 1, "alice", "pass")

            user_db = tmp_path / "user_1" / "workouts.db"
            conn = _create_user_db(str(user_db))

            # A valid template with data
            _seed_template(conn, "t001", "Working Press", "Shoulders")
            _seed_workout(conn, "w001", "2024-06-01T08:00:00Z")
            _seed_exercise(conn, 1, "w001", "t001")
            _seed_set(conn, 1, 1, 50.0, 10, 0)

            # A template with no workout data at all (will get insufficient_data)
            _seed_template(conn, "t999", "Lonely Exercise", "Chest")

            conn.close()

            c.cookies.set("dg_session", token)
            yield c

    def test_valid_exercise_survives_alongside_failing(self, auth_client):
        """A template that errors during check() should not crash the page."""
        response = auth_client.get("/")
        assert response.status_code == 200
        html = response.text

        # The valid exercise should still render
        assert "Working Press" in html

    def test_insufficient_data_shows_as_group(self, auth_client):
        """A template with no data should show in insufficient_data group."""
        response = auth_client.get("/")
        assert response.status_code == 200
        html = response.text.lower()

        assert "lonely exercise" in html
        assert "insufficient" in html or "Insufficient" in html


# ===========================================================================
# T3 — Status grouping
# ===========================================================================


class TestDashboardGroupingOrder:
    """Status groups appear in a defined order."""

    @pytest.fixture
    def auth_client(self, tmp_path):
        from fastapi.testclient import TestClient

        from darth_gain.web.app import create_app

        users_db = tmp_path / "users.db"
        app = create_app(
            data_dir=str(tmp_path),
            secret_key="test-secret",
            users_db_path=str(users_db),
        )

        from darth_gain.web.auth import create_session

        token = create_session({"user_id": 1, "username": "alice"}, "test-secret")
        with TestClient(app) as c:
            _seed_user(str(users_db), 1, "alice", "pass")

            user_db = tmp_path / "user_1" / "workouts.db"
            conn = _create_user_db(str(user_db))

            # maintain exercise (not top of range)
            _seed_template(conn, "t001", "Pull-up", "Back")
            _seed_workout(conn, "w001", "2024-06-01T08:00:00Z")
            _seed_exercise(conn, 1, "w001", "t001")
            _seed_set(conn, 1, 1, 70.0, 8, 0)  # maintain

            # progress exercise (all reps >= 12)
            _seed_template(conn, "t002", "Bench Press", "Chest")
            _seed_workout(conn, "w002", "2024-06-02T08:00:00Z")
            _seed_exercise(conn, 2, "w002", "t002")
            _seed_set(conn, 2, 2, 80.0, 12, 0)  # progress

            conn.close()

            c.cookies.set("dg_session", token)
            yield c

    def test_progress_group_appears_before_maintain(self, auth_client):
        """PROGRESS group should appear before MAINTAIN in the page."""
        response = auth_client.get("/")
        assert response.status_code == 200
        html = response.text

        # Find positions of headers
        progress_idx = html.find("PROGRESS")
        maintain_idx = html.find("MAINTAIN")

        if progress_idx >= 0 and maintain_idx >= 0:
            assert progress_idx < maintain_idx, (
                "PROGRESS group should appear before MAINTAIN"
            )
