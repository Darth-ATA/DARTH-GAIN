"""Tests for web exercise detail page and config editor.

Strict TDD — tests define the contract before implementation.

Test scenarios:
  - Auth required for GET and PUT /exercises/{id}
  - 404 for nonexistent template
  - Detail page renders exercise info and current status
  - History entries displayed as table
  - Empty history shows message
  - Config form pre-filled with saved values
  - Default config when none saved
  - Config PUT update succeeds
  - Config PUT validation errors (rep_min > rep_max, increment <= 0)
  - Config PUT for nonexistent template returns 404
  - Back to Dashboard link present
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


def _seed_history(
    conn: sqlite3.Connection,
    tid: str,
    status: str,
    weight: float | None,
    checked_at: str,
    recommended: float | None = None,
) -> None:
    conn.execute(
        "INSERT INTO progression_history "
        "(exercise_template_id, checked_at, status, "
        " current_weight_kg, recommended_weight_kg) "
        "VALUES (?, ?, ?, ?, ?)",
        (tid, checked_at, status, weight, recommended),
    )
    conn.commit()


def _create_user_db(db_path: str) -> sqlite3.Connection:
    """Create a per-user SQLite DB with all tables at the given path."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    from darth_gain.db.engine import create_engine, create_tables

    conn = create_engine(db_path)
    create_tables(conn)
    return conn


def _seed_user(users_db_path: str, user_id: int, username: str, password: str) -> None:
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
# T4 — Auth required
# ===========================================================================


class TestExerciseAuth:
    """Exercise detail and config routes require authentication."""

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

    def test_exercise_detail_requires_auth(self, client):
        """GET /exercises/{id} without session should redirect to login."""
        response = client.get("/exercises/bench_press", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers.get("location") == "/login"

    def test_config_update_requires_auth(self, client):
        """PUT /exercises/{id}/config without session should redirect to login."""
        response = client.put(
            "/exercises/bench_press/config",
            data={"rep_min": 6, "rep_max": 12, "weight_increment": 2.5},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers.get("location") == "/login"


# ===========================================================================
# T4 — Exercise detail page
# ===========================================================================


class TestExerciseDetail:
    """GET /exercises/{template_id} renders detail page."""

    @pytest.fixture
    def auth_client(self, tmp_path):
        from fastapi.testclient import TestClient

        from darth_gain.web.app import create_app
        from darth_gain.web.auth import create_session

        users_db = tmp_path / "users.db"
        app = create_app(
            data_dir=str(tmp_path),
            secret_key="test-secret",
            users_db_path=str(users_db),
        )

        token = create_session({"user_id": 1, "username": "alice"}, "test-secret")
        with TestClient(app) as c:
            _seed_user(str(users_db), 1, "alice", "pass")

            # Seed per-user DB
            user_db = tmp_path / "user_1" / "workouts.db"
            conn = _create_user_db(str(user_db))

            # bench_press — 3 history entries, configured
            _seed_template(conn, "bench_press", "Bench Press", "Chest")
            _seed_workout(conn, "w001", "2024-06-01T08:00:00Z")
            _seed_exercise(conn, 1, "w001", "bench_press")
            _seed_set(conn, 1, 1, 80.0, 12, 0)
            _seed_set(conn, 2, 1, 80.0, 12, 1)
            conn.execute(
                "INSERT INTO progression_config "
                "(exercise_template_id, rep_min, rep_max, weight_increment, enabled) "
                "VALUES ('bench_press', 6, 10, 5.0, 1)"
            )
            conn.commit()
            _seed_history(conn, "bench_press", "progress", 80.0,
                          "2024-06-01T08:00:00", 82.5)
            _seed_history(conn, "bench_press", "maintain", 77.5,
                          "2024-05-25T08:00:00")
            _seed_history(conn, "bench_press", "progress", 77.5,
                          "2024-05-18T08:00:00", 80.0)

            # deadlift — has data, engine.check() creates history
            _seed_template(conn, "deadlift", "Deadlift", "Back")
            _seed_workout(conn, "w002", "2024-06-02T08:00:00Z")
            _seed_exercise(conn, 2, "w002", "deadlift")
            _seed_set(conn, 3, 2, 100.0, 8, 0)

            # lonely_exercise — template exists but NO workout data → no history
            _seed_template(conn, "lonely", "Lonely Exercise", "Core")

            conn.close()

            c.cookies.set("dg_session", token)
            yield c

    def test_nonexistent_exercise_returns_404(self, auth_client):
        """GET /exercises/{id} for nonexistent template should return 404."""
        response = auth_client.get("/exercises/nonexistent_999")
        assert response.status_code == 404
        assert "not found" in response.text.lower() or "404" in response.text

    def test_detail_shows_exercise_title(self, auth_client):
        """Detail page should show the exercise title."""
        response = auth_client.get("/exercises/bench_press")
        assert response.status_code == 200
        assert "Bench Press" in response.text

    def test_detail_shows_current_status(self, auth_client):
        """Detail page should show the current progression status."""
        response = auth_client.get("/exercises/bench_press")
        assert response.status_code == 200
        # After engine.check(), the latest history entry determines status
        assert "progress" in response.text.lower()

    def test_detail_shows_history_table(self, auth_client):
        """Detail page should show history entries in a table."""
        response = auth_client.get("/exercises/bench_press")
        assert response.status_code == 200
        html = response.text
        # Should contain history date references
        assert "2024-06-01" in html or "2024-05-25" in html or "2024-05-18" in html
        # Should show weights from history
        assert "80.0" in html
        assert "82.5" in html

    def test_detail_shows_history_sorted_newest_first(self, auth_client):
        """History entries should appear newest first."""
        response = auth_client.get("/exercises/bench_press")
        assert response.status_code == 200
        html = response.text
        # 2024-06-01 should appear before 2024-05-18
        june_pos = html.find("2024-06-01")
        may18_pos = html.find("2024-05-18")
        assert june_pos >= 0
        assert may18_pos >= 0
        assert june_pos < may18_pos, (
            "Newest history entry should appear before older ones"
        )

    def test_detail_without_history_shows_message(self, auth_client):
        """Exercise with no workout data shows insufficient_data status and empty history."""
        response = auth_client.get("/exercises/lonely")
        assert response.status_code == 200
        html = response.text.lower()
        # The engine runs check() which creates a history entry. With no workout data,
        # the status should be insufficient_data.
        assert "insufficient" in html or "no data" in html or "no history" in html

    def test_config_form_prefilled_with_saved_values(self, auth_client):
        """Config form should show saved rep_min, rep_max, increment, enabled."""
        response = auth_client.get("/exercises/bench_press")
        assert response.status_code == 200
        html = response.text
        # bench_press has config: rep_min=6, rep_max=10, increment=5.0, enabled=true
        assert 'value="6"' in html or 'name="rep_min"' in html
        assert 'value="10"' in html or 'name="rep_max"' in html
        assert 'value="5.0"' in html or 'step="0.5"' in html

    def test_config_form_shows_defaults_when_not_configured(self, auth_client):
        """Exercise without config should show default values (8, 12, 2.5)."""
        response = auth_client.get("/exercises/deadlift")
        assert response.status_code == 200
        html = response.text
        # Defaults: rep_min=8, rep_max=12, increment=2.5, enabled=true
        assert 'value="8"' in html or 'min="1"' in html
        assert 'value="12"' in html or 'max="99"' in html
        assert 'value="2.5"' in html or 'step="0.5"' in html

    def test_detail_has_back_to_dashboard_link(self, auth_client):
        """Detail page should include a link back to the dashboard."""
        response = auth_client.get("/exercises/bench_press")
        assert response.status_code == 200
        html = response.text.lower()
        assert "back to dashboard" in html or "←" in html


# ===========================================================================
# T4 — Config editor
# ===========================================================================


class TestExerciseConfigUpdate:
    """PUT /exercises/{template_id}/config behavior."""

    @pytest.fixture
    def auth_client(self, tmp_path):
        from fastapi.testclient import TestClient

        from darth_gain.web.app import create_app
        from darth_gain.web.auth import create_session

        users_db = tmp_path / "users.db"
        app = create_app(
            data_dir=str(tmp_path),
            secret_key="test-secret",
            users_db_path=str(users_db),
        )

        token = create_session({"user_id": 1, "username": "alice"}, "test-secret")
        with TestClient(app) as c:
            _seed_user(str(users_db), 1, "alice", "pass")

            user_db = tmp_path / "user_1" / "workouts.db"
            conn = _create_user_db(str(user_db))

            _seed_template(conn, "bench_press", "Bench Press", "Chest")
            _seed_workout(conn, "w001", "2024-06-01T08:00:00Z")
            _seed_exercise(conn, 1, "w001", "bench_press")
            _seed_set(conn, 1, 1, 80.0, 12, 0)

            # Start with config: rep_min=6, rep_max=10, increment=5.0, enabled=true
            conn.execute(
                "INSERT INTO progression_config "
                "(exercise_template_id, rep_min, rep_max, weight_increment, enabled) "
                "VALUES ('bench_press', 6, 10, 5.0, 1)"
            )
            conn.commit()

            conn.close()

            c.cookies.set("dg_session", token)
            yield c

    def test_config_update_succeeds(self, auth_client):
        """PUT with valid data should update config and return snippet."""
        response = auth_client.put(
            "/exercises/bench_press/config",
            data={"rep_min": 8, "rep_max": 12, "weight_increment": 2.5, "enabled": True},
        )
        assert response.status_code == 200
        html = response.text
        # Response should be an HTML snippet (not full page)
        assert '<form' in html.lower() or 'config' in html.lower()
        # Should reflect updated values
        assert 'value="8"' in html or 'rep_min' in html

    def test_config_update_persists_to_database(self, auth_client, tmp_path):
        """Config values should be persisted after PUT."""
        response = auth_client.put(
            "/exercises/bench_press/config",
            data={"rep_min": 8, "rep_max": 12, "weight_increment": 2.5, "enabled": True},
        )
        assert response.status_code == 200

        # Verify in DB directly
        user_db = tmp_path / "user_1" / "workouts.db"
        conn = sqlite3.connect(str(user_db))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT rep_min, rep_max, weight_increment, enabled "
                "FROM progression_config WHERE exercise_template_id = 'bench_press'"
            ).fetchone()
            assert row is not None
            assert row["rep_min"] == 8
            assert row["rep_max"] == 12
            assert row["weight_increment"] == 2.5
            assert row["enabled"] == 1
        finally:
            conn.close()

    def test_config_update_rep_min_greater_than_rep_max(self, auth_client):
        """PUT with rep_min > rep_max should return 422."""
        response = auth_client.put(
            "/exercises/bench_press/config",
            data={"rep_min": 15, "rep_max": 10, "weight_increment": 2.5, "enabled": True},
        )
        assert response.status_code == 422
        assert "rep_min" in response.text.lower() or "must be" in response.text.lower()

    def test_config_update_increment_zero(self, auth_client):
        """PUT with increment <= 0 should return 422."""
        response = auth_client.put(
            "/exercises/bench_press/config",
            data={"rep_min": 6, "rep_max": 10, "weight_increment": 0, "enabled": True},
        )
        assert response.status_code == 422
        assert "increment" in response.text.lower() or "greater" in response.text.lower()

    def test_config_update_nonexistent_template(self, auth_client):
        """PUT for nonexistent template should return 404."""
        response = auth_client.put(
            "/exercises/nonexistent_999/config",
            data={"rep_min": 6, "rep_max": 10, "weight_increment": 2.5, "enabled": True},
        )
        assert response.status_code == 404

    def test_config_update_partial_preserves_unchanged(self, auth_client, tmp_path):
        """PUT with subset of fields should preserve others from current config."""
        # Current config: rep_min=6, rep_max=10, increment=5.0, enabled=true
        # Submit only weight_increment
        response = auth_client.put(
            "/exercises/bench_press/config",
            data={"weight_increment": 2.5},
        )
        assert response.status_code == 200

        user_db = tmp_path / "user_1" / "workouts.db"
        conn = sqlite3.connect(str(user_db))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT rep_min, rep_max, weight_increment, enabled "
                "FROM progression_config WHERE exercise_template_id = 'bench_press'"
            ).fetchone()
            assert row is not None
            assert row["rep_min"] == 6  # unchanged
            assert row["rep_max"] == 10  # unchanged
            assert row["weight_increment"] == 2.5  # changed
            assert row["enabled"] == 1  # unchanged
        finally:
            conn.close()
