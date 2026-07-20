"""Tests for darth_gain.db.engine — connection management and schema DDL."""

from __future__ import annotations

import sqlite3

import pytest

from darth_gain.db.engine import create_engine, create_tables


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def in_memory_conn() -> sqlite3.Connection:
    """Return an in-memory SQLite connection with tables created."""
    conn = create_engine(":memory:")
    create_tables(conn)
    return conn


# ---------------------------------------------------------------------------
# create_engine
# ---------------------------------------------------------------------------


class TestCreateEngine:
    def test_returns_connection(self) -> None:
        """create_engine returns a sqlite3.Connection."""
        conn = create_engine(":memory:")
        assert isinstance(conn, sqlite3.Connection)
        conn.close()

    def test_in_memory_works(self) -> None:
        """In-memory database opens without error."""
        conn = create_engine(":memory:")
        cursor = conn.execute("SELECT 1")
        assert cursor.fetchone()[0] == 1
        conn.close()


# ---------------------------------------------------------------------------
# create_tables — table existence
# ---------------------------------------------------------------------------


class TestCreateTables:
    def test_workouts_table_exists(self, in_memory_conn: sqlite3.Connection) -> None:
        """workouts table is created with correct columns."""
        cursor = in_memory_conn.execute("PRAGMA table_info(workouts)")
        cols = {row[1]: row[2] for row in cursor.fetchall()}
        assert cols["id"] == "TEXT"
        assert cols["title"] == "TEXT"
        assert cols["description"] == "TEXT"
        assert cols["start_time"] == "TEXT"
        assert cols["end_time"] == "TEXT"
        assert "is_deleted" in cols
        assert "created_at" in cols
        assert "updated_at" in cols

    def test_workouts_pk_is_id(self, in_memory_conn: sqlite3.Connection) -> None:
        """workouts.id is the primary key."""
        cursor = in_memory_conn.execute("PRAGMA table_info(workouts)")
        pk_cols = [row[1] for row in cursor.fetchall() if row[5] == 1]
        assert pk_cols == ["id"]

    def test_exercises_table_exists(self, in_memory_conn: sqlite3.Connection) -> None:
        """exercises table is created with correct columns."""
        cursor = in_memory_conn.execute("PRAGMA table_info(exercises)")
        cols = {row[1]: row[2] for row in cursor.fetchall()}
        assert cols["id"] == "INTEGER"
        assert cols["workout_id"] == "TEXT"
        assert cols["exercise_template_id"] == "TEXT"
        assert cols["title"] == "TEXT"
        assert cols["notes"] == "TEXT"
        assert cols["sort_order"] == "INTEGER"
        assert "is_deleted" in cols

    def test_sets_table_exists(self, in_memory_conn: sqlite3.Connection) -> None:
        """sets table is created with correct columns."""
        cursor = in_memory_conn.execute("PRAGMA table_info(sets)")
        cols = {row[1]: row[2] for row in cursor.fetchall()}
        assert cols["id"] == "INTEGER"
        assert cols["exercise_id"] == "INTEGER"
        assert cols["set_index"] == "INTEGER"
        assert cols["type"] == "TEXT"
        assert cols["weight_kg"] == "REAL"
        assert cols["reps"] == "INTEGER"
        assert cols["distance_meters"] == "REAL"
        assert cols["duration_seconds"] == "REAL"
        assert cols["rpe"] == "REAL"
        assert "is_deleted" in cols

    def test_exercise_templates_table_exists(
        self, in_memory_conn: sqlite3.Connection
    ) -> None:
        """exercise_templates table is created with correct columns."""
        cursor = in_memory_conn.execute("PRAGMA table_info(exercise_templates)")
        cols = {row[1]: row[2] for row in cursor.fetchall()}
        assert cols["id"] == "TEXT"
        assert cols["title"] == "TEXT"
        assert cols["type"] == "TEXT"
        assert cols["primary_muscle_group"] == "TEXT"
        assert cols["other_muscle_groups"] == "TEXT"
        assert cols["equipment"] == "TEXT"
        assert cols["is_custom"] == "INTEGER"
        assert cols["cached_at"] == "TEXT"

    def test_sync_metadata_table_exists(
        self, in_memory_conn: sqlite3.Connection
    ) -> None:
        """sync_metadata table is created as key/value store."""
        cursor = in_memory_conn.execute("PRAGMA table_info(sync_metadata)")
        cols = {row[1]: row[2] for row in cursor.fetchall()}
        assert cols["key"] == "TEXT"
        assert cols["value"] == "TEXT"

    def test_sync_metadata_pk_is_key(
        self, in_memory_conn: sqlite3.Connection
    ) -> None:
        """sync_metadata.key is the primary key."""
        cursor = in_memory_conn.execute("PRAGMA table_info(sync_metadata)")
        pk_cols = [row[1] for row in cursor.fetchall() if row[5] == 1]
        assert pk_cols == ["key"]

    def test_create_tables_is_idempotent(
        self, in_memory_conn: sqlite3.Connection
    ) -> None:
        """Calling create_tables twice does not raise an error."""
        create_tables(in_memory_conn)  # second call
        # verify all tables still exist
        cursor = in_memory_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        assert "workouts" in tables
        assert "exercises" in tables
        assert "sets" in tables
        assert "exercise_templates" in tables
        assert "sync_metadata" in tables

    def test_index_on_workouts_start_time(
        self, in_memory_conn: sqlite3.Connection
    ) -> None:
        """Index exists on workouts.start_time."""
        cursor = in_memory_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='workouts'"
        )
        indexes = {row[0] for row in cursor.fetchall()}
        matching = [i for i in indexes if "start_time" in i]
        assert matching, "No index on workouts.start_time found"

    def test_index_on_workouts_updated_at(
        self, in_memory_conn: sqlite3.Connection
    ) -> None:
        """Index exists on workouts.updated_at."""
        cursor = in_memory_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='workouts'"
        )
        indexes = {row[0] for row in cursor.fetchall()}
        matching = [i for i in indexes if "updated_at" in i]
        assert matching, "No index on workouts.updated_at found"

    def test_index_on_exercises_workout_id(
        self, in_memory_conn: sqlite3.Connection
    ) -> None:
        """Index exists on exercises.workout_id."""
        cursor = in_memory_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='exercises'"
        )
        indexes = {row[0] for row in cursor.fetchall()}
        matching = [i for i in indexes if "workout_id" in i]
        assert matching, "No index on exercises.workout_id found"

    # ------------------------------------------------------------------
    # progression_config
    # ------------------------------------------------------------------

    def test_progression_config_table_exists(
        self, in_memory_conn: sqlite3.Connection
    ) -> None:
        """progression_config table is created with correct columns."""
        cursor = in_memory_conn.execute("PRAGMA table_info(progression_config)")
        cols = {row[1]: row[2] for row in cursor.fetchall()}
        assert cols["exercise_template_id"] == "TEXT"
        assert cols["rep_min"] == "INTEGER"
        assert cols["rep_max"] == "INTEGER"
        assert cols["weight_increment"] == "REAL"
        assert cols["enabled"] == "INTEGER"

    def test_progression_config_pk_is_exercise_template_id(
        self, in_memory_conn: sqlite3.Connection
    ) -> None:
        """progression_config.exercise_template_id is the primary key."""
        cursor = in_memory_conn.execute("PRAGMA table_info(progression_config)")
        pk_cols = [row[1] for row in cursor.fetchall() if row[5] == 1]
        assert pk_cols == ["exercise_template_id"]

    def test_progression_config_defaults(
        self, in_memory_conn: sqlite3.Connection
    ) -> None:
        """progression_config columns have correct default values."""
        cursor = in_memory_conn.execute("PRAGMA table_info(progression_config)")
        defaults = {row[1]: row[4] for row in cursor.fetchall()}
        assert defaults["rep_min"] == "8"
        assert defaults["rep_max"] == "12"
        assert defaults["weight_increment"] == "2.5"
        assert defaults["enabled"] == "1"

    # ------------------------------------------------------------------
    # progression_history
    # ------------------------------------------------------------------

    def test_progression_history_table_exists(
        self, in_memory_conn: sqlite3.Connection
    ) -> None:
        """progression_history table is created with correct columns."""
        cursor = in_memory_conn.execute("PRAGMA table_info(progression_history)")
        cols = {row[1]: row[2] for row in cursor.fetchall()}
        assert cols["id"] == "INTEGER"
        assert cols["exercise_template_id"] == "TEXT"
        assert cols["checked_at"] == "TEXT"
        assert cols["status"] == "TEXT"
        assert cols["current_weight_kg"] == "REAL"
        assert cols["recommended_weight_kg"] == "REAL"
        assert cols["details"] == "TEXT"

    def test_progression_history_pk_is_id(
        self, in_memory_conn: sqlite3.Connection
    ) -> None:
        """progression_history.id is the primary key."""
        cursor = in_memory_conn.execute("PRAGMA table_info(progression_history)")
        pk_cols = [row[1] for row in cursor.fetchall() if row[5] == 1]
        assert pk_cols == ["id"]

    def test_progression_history_auto_increment(
        self, in_memory_conn: sqlite3.Connection
    ) -> None:
        """progression_history.id is autoincrement."""
        cursor = in_memory_conn.execute("PRAGMA table_info(progression_history)")
        id_row = [row for row in cursor.fetchall() if row[1] == "id"][0]
        # Column 6 (index 6) is `pk` — actually sqlite_master table_info
        # returns: cid, name, type, notnull, dflt_value, pk
        # Auto-increment is implied by INTEGER PRIMARY KEY, not directly
        # exposed via PRAGMA. We verify by checking PK=True and type=INTEGER.
        assert id_row[2] == "INTEGER"  # type
        assert id_row[5] == 1  # pk

    def test_progression_history_index_on_template_id(
        self, in_memory_conn: sqlite3.Connection
    ) -> None:
        """Index exists on progression_history.exercise_template_id."""
        cursor = in_memory_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='progression_history'"
        )
        indexes = {row[0] for row in cursor.fetchall()}
        matching = [i for i in indexes if "template" in i.lower()]
        assert matching, "No index on progression_history.exercise_template_id found"

    # ------------------------------------------------------------------
    # Idempotency with new tables
    # ------------------------------------------------------------------

    def test_create_tables_idempotent_includes_progression(
        self, in_memory_conn: sqlite3.Connection
    ) -> None:
        """Idempotent create_tables includes progression tables."""
        create_tables(in_memory_conn)  # second call
        cursor = in_memory_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        assert "progression_config" in tables
        assert "progression_history" in tables
