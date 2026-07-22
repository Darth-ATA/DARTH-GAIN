"""Tests for web routine view: exercises grouped by Hevy routine.

Strict TDD — tests define the contract before implementation.

Test scenarios:
  - Auth required (redirect to /login without session)
  - Empty state (no DB exists)
  - Empty state (DB with no routines/exercises)
  - Routines render with their exercises
  - Exercise cards show progression status in routine groups
  - Uncategorized bucket for null routine_id exercises
  - Exercise count shown per routine
  - All exercises appear even across multiple routines
"""

from __future__ import annotations

import os
import sqlite3

import pytest


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


def _seed_workout(
    conn: sqlite3.Connection,
    wid: str,
    start_time: str,
    routine_id: str | None = None,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO workouts "
        "(id, title, start_time, routine_id) VALUES (?, ?, ?, ?)",
        (wid, "Workout", start_time, routine_id),
    )
    conn.commit()


def _seed_exercise(conn: sqlite3.Connection, eid: int, wid: str, tid: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO exercises "
        "(id, workout_id, exercise_template_id, title) VALUES (?, ?, ?, ?)",
        (eid, wid, tid, "Ex"),
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


def _seed_routine(conn: sqlite3.Connection, rid: str, title: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO routines "
        "(id, title, folder_id, created_at, updated_at) "
        "VALUES (?, ?, NULL, '2024-01-01T00:00:00Z', '2024-01-02T00:00:00Z')",
        (rid, title),
    )
    conn.commit()


def _seed_progression_config(
    conn: sqlite3.Connection,
    tid: str,
    enabled: int = 1,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO progression_config "
        "(exercise_template_id, rep_min, rep_max, weight_increment, enabled) "
        "VALUES (?, 8, 12, 2.5, ?)",
        (tid, enabled),
    )
    conn.commit()


def _create_user_db(db_path: str) -> sqlite3.Connection:
    """Create a per-user SQLite DB with all tables at the given path."""
    from darth_gain.db.engine import create_engine, create_tables

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = create_engine(db_path)
    create_tables(conn)
    return conn


def _seed_user(
    users_db_path: str, user_id: int, username: str, password: str
) -> None:
    """Insert a user into users.db (table must already exist)."""
    from werkzeug.security import generate_password_hash

    conn = sqlite3.connect(users_db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO users (id, username, password_hash) "
            "VALUES (?, ?, ?)",
            (user_id, username, generate_password_hash(password)),
        )
        conn.commit()
    finally:
        conn.close()


# ===========================================================================
# T1 — Auth required
# ===========================================================================


class TestRoutinesAuth:
    """Routines route requires authentication."""

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

    def test_routines_requires_auth(self, client):
        """GET /routines without session should redirect to login."""
        response = client.get("/routines", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers.get("location") == "/login"


# ===========================================================================
# T2 — Empty states
# ===========================================================================


class TestRoutinesEmptyState:
    """Routines page with no data at all."""

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

        token = create_session(
            {"user_id": 1, "username": "alice"}, "test-secret"
        )
        with TestClient(app) as c:
            _seed_user(str(users_db), 1, "alice", "pass")
            c.cookies.set("dg_session", token)
            yield c

    def test_routines_without_db_shows_empty(self, auth_client):
        """GET /routines when per-user DB doesn't exist yet should show empty."""
        response = auth_client.get("/routines")
        assert response.status_code == 200
        content = response.text.lower()
        assert "no routine" in content or "no exercise" in content or "sync" in content

    def test_routines_with_empty_db_shows_empty(self, auth_client, tmp_path):
        """GET /routines when DB exists but has no content should show empty."""
        user_db = tmp_path / "user_1" / "workouts.db"
        conn = _create_user_db(str(user_db))
        conn.close()

        response = auth_client.get("/routines")
        assert response.status_code == 200
        content = response.text.lower()
        assert "no routine" in content or "no exercise" in content or "sync" in content


# ===========================================================================
# T3 — Routines with exercises
# ===========================================================================


class TestRoutinesWithExercises:
    """Routines page with seeded routines, exercises, and progression data."""

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

        token = create_session(
            {"user_id": 1, "username": "alice"}, "test-secret"
        )
        with TestClient(app) as c:
            _seed_user(str(users_db), 1, "alice", "pass")

            user_db = tmp_path / "user_1" / "workouts.db"
            conn = _create_user_db(str(user_db))

            # --- Routine A: Push Day (2 exercises) ---
            _seed_routine(conn, "r001", "Push Day")
            _seed_template(conn, "t001", "Bench Press", "Chest")
            _seed_template(conn, "t002", "Overhead Press", "Shoulders")
            _seed_workout(conn, "w001", "2024-06-01T08:00:00Z", "r001")
            _seed_exercise(conn, 1, "w001", "t001")
            _seed_set(conn, 1, 1, 80.0, 12, 0)  # all reps >= 12 → PROGRESS
            _seed_set(conn, 2, 1, 80.0, 12, 1)
            _seed_progression_config(conn, "t001")
            _seed_exercise(conn, 2, "w001", "t002")
            _seed_set(conn, 3, 2, 50.0, 8, 0)  # reps < 12 → MAINTAIN
            _seed_progression_config(conn, "t002")

            # --- Routine B: Pull Day (1 exercise) ---
            _seed_routine(conn, "r002", "Pull Day")
            _seed_template(conn, "t003", "Barbell Row", "Back")
            _seed_workout(conn, "w002", "2024-06-03T08:00:00Z", "r002")
            _seed_exercise(conn, 3, "w002", "t003")
            _seed_set(conn, 4, 3, 60.0, 10, 0)  # reps < 12 → MAINTAIN
            _seed_progression_config(conn, "t003")

            # --- Uncategorized: null routine_id (1 exercise) ---
            _seed_template(conn, "t004", "Deadlift", "Back")
            _seed_workout(conn, "w003", "2024-06-04T08:00:00Z", None)
            _seed_exercise(conn, 4, "w003", "t004")
            # no sets → INSUFFICIENT_DATA
            _seed_progression_config(conn, "t004")

            conn.close()

            c.cookies.set("dg_session", token)
            yield c

    def test_routines_page_renders_successfully(self, auth_client):
        """GET /routines returns 200."""
        response = auth_client.get("/routines")
        assert response.status_code == 200

    def test_routines_shows_routine_names(self, auth_client):
        """Routine group headers should appear in the page."""
        response = auth_client.get("/routines")
        html = response.text
        assert "Push Day" in html
        assert "Pull Day" in html

    def test_routines_shows_exercises_by_group(self, auth_client):
        """Exercises should appear under their routine group."""
        response = auth_client.get("/routines")
        html = response.text
        assert "Bench Press" in html
        assert "Overhead Press" in html
        assert "Barbell Row" in html
        assert "Deadlift" in html

    def test_routines_shows_uncategorized_section(self, auth_client):
        """Exercises with null routine_id should appear under Uncategorized."""
        response = auth_client.get("/routines")
        html = response.text.lower()
        assert "uncategorized" in html or "uncategorized" in html

    def test_routines_shows_exercise_count(self, auth_client):
        """Routine groups should show exercise count."""
        response = auth_client.get("/routines")
        html = response.text
        # Push Day has 2 exercises
        assert "(2)" in html
        # Pull Day has 1 exercise
        assert "(1)" in html

    def test_routines_shows_progression_status(self, auth_client):
        """Exercise cards should include progression status."""
        response = auth_client.get("/routines")
        html = response.text

        # Bench Press: all 12 reps → PROGRESS (82.5 kg recommended)
        assert "82.5" in html or "PROGRESS" in html

        # Overhead Press: 8 reps → MAINTAIN
        assert "MAINTAIN" in html or "Maintain" in html

    def test_routines_shows_exercise_details(self, auth_client):
        """Exercise cards should show weight and rep range."""
        response = auth_client.get("/routines")
        html = response.text

        # Rep range visible (8–12 default)
        assert "8" in html and "12" in html
        # Weights visible
        assert "80.0" in html or "80" in html
        assert "50.0" in html or "50" in html



# ===========================================================================
# T4 — Routines with only routines (zero exercises)
# ===========================================================================


class TestRoutinesEmptyExercises:
    """Routines exist but have no exercises — should not crash."""

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

        token = create_session(
            {"user_id": 1, "username": "alice"}, "test-secret"
        )
        with TestClient(app) as c:
            _seed_user(str(users_db), 1, "alice", "pass")

            user_db = tmp_path / "user_1" / "workouts.db"
            conn = _create_user_db(str(user_db))

            # A routine with NO exercises and NO workouts
            _seed_routine(conn, "r001", "Empty Routine")
            conn.close()

            c.cookies.set("dg_session", token)
            yield c

    def test_routine_without_exercises_does_not_crash(self, auth_client):
        """A routine with no exercises should not crash the page."""
        response = auth_client.get("/routines")
        assert response.status_code == 200


# ===========================================================================
# T5 — Routines with only uncategorized exercises
# ===========================================================================


class TestRoutinesOnlyUncategorized:
    """Only uncategorized exercises exist (no routines)."""

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

        token = create_session(
            {"user_id": 1, "username": "alice"}, "test-secret"
        )
        with TestClient(app) as c:
            _seed_user(str(users_db), 1, "alice", "pass")

            user_db = tmp_path / "user_1" / "workouts.db"
            conn = _create_user_db(str(user_db))

            _seed_template(conn, "t001", "Squat", "Legs")
            _seed_workout(conn, "w001", "2024-06-01T08:00:00Z", None)
            _seed_exercise(conn, 1, "w001", "t001")
            _seed_set(conn, 1, 1, 100.0, 10, 0)
            _seed_progression_config(conn, "t001")
            conn.close()

            c.cookies.set("dg_session", token)
            yield c

    def test_uncategorized_shows_with_no_routines(self, auth_client):
        """When no routines exist, uncategorized exercises still render."""
        response = auth_client.get("/routines")
        assert response.status_code == 200
        html = response.text.lower()
        assert "squat" in html
        assert "uncategorized" in html or "uncategorized" in html
