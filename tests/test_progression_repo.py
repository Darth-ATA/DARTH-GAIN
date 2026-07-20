"""Tests for darth_gain.progression.repo — progression CRUD operations."""

from __future__ import annotations

import sqlite3

import pytest

from darth_gain.db.engine import create_engine, create_tables
from darth_gain.progression.models import ProgressionConfig, ProgressionHistoryEntry
from darth_gain.progression.repo import (
    add_history_entry,
    get_all_configs,
    get_config,
    get_history,
    get_latest_history,
    get_normal_sets,
    get_template,
    set_config,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn() -> sqlite3.Connection:
    """Return an in-memory SQLite with all tables created."""
    c = create_engine(":memory:")
    create_tables(c)
    return c


@pytest.fixture
def conn_with_template(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Seed a base exercise template for FK-dependent tests."""
    conn.execute(
        """INSERT INTO exercise_templates (id, title, type, primary_muscle_group)
           VALUES ('t001', 'Bench Press', 'strength', 'Chest')"""
    )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# get_config
# ---------------------------------------------------------------------------


class TestGetConfig:
    def test_returns_defaults_when_no_row(self, conn: sqlite3.Connection) -> None:
        """get_config returns ProgressionConfig with defaults when no row exists."""
        cfg = get_config(conn, "t001")
        assert cfg.exercise_template_id == "t001"
        assert cfg.rep_min == 8
        assert cfg.rep_max == 12
        assert cfg.weight_increment == 2.5
        assert cfg.enabled is True

    def test_returns_stored_row(self, conn_with_template: sqlite3.Connection) -> None:
        """get_config returns stored config when a row exists."""
        conn_with_template.execute(
            """INSERT INTO progression_config
               (exercise_template_id, rep_min, rep_max, weight_increment, enabled)
               VALUES ('t001', 6, 10, 5.0, 0)"""
        )
        conn_with_template.commit()
        cfg = get_config(conn_with_template, "t001")
        assert cfg.rep_min == 6
        assert cfg.rep_max == 10
        assert cfg.weight_increment == 5.0
        assert cfg.enabled is False

    def test_different_templates_return_independent_configs(
        self, conn: sqlite3.Connection
    ) -> None:
        """Configs for different template IDs are independent."""
        cfg_a = get_config(conn, "t001")
        cfg_b = get_config(conn, "t002")
        assert cfg_a.exercise_template_id == "t001"
        assert cfg_b.exercise_template_id == "t002"
        assert cfg_a.rep_min == 8  # defaults
        assert cfg_b.rep_min == 8


# ---------------------------------------------------------------------------
# set_config (upsert)
# ---------------------------------------------------------------------------


class TestSetConfig:
    def test_insert_new_config(self, conn_with_template: sqlite3.Connection) -> None:
        """set_config inserts a new config row."""
        cfg = ProgressionConfig(
            exercise_template_id="t001",
            rep_min=6,
            rep_max=10,
            weight_increment=5.0,
            enabled=False,
        )
        set_config(conn_with_template, cfg)

        row = conn_with_template.execute(
            "SELECT * FROM progression_config WHERE exercise_template_id = 't001'"
        ).fetchone()
        assert row["rep_min"] == 6
        assert row["rep_max"] == 10
        assert row["weight_increment"] == 5.0
        assert row["enabled"] == 0

    def test_update_existing_config(self, conn_with_template: sqlite3.Connection) -> None:
        """set_config updates an existing config row."""
        # Insert original
        conn_with_template.execute(
            """INSERT INTO progression_config
               (exercise_template_id, rep_min, rep_max, weight_increment, enabled)
               VALUES ('t001', 8, 12, 2.5, 1)"""
        )
        conn_with_template.commit()

        # Update with new values
        cfg = ProgressionConfig(
            exercise_template_id="t001",
            rep_min=5,
            rep_max=8,
            weight_increment=5.0,
            enabled=False,
        )
        set_config(conn_with_template, cfg)

        rows = conn_with_template.execute(
            "SELECT * FROM progression_config"
        ).fetchall()
        assert len(rows) == 1  # still only one row
        assert rows[0]["rep_min"] == 5
        assert rows[0]["weight_increment"] == 5.0
        assert rows[0]["enabled"] == 0

    def test_insert_with_defaults(self, conn_with_template: sqlite3.Connection) -> None:
        """set_config with defaults uses DDL default values."""
        cfg = ProgressionConfig(exercise_template_id="t001")
        set_config(conn_with_template, cfg)

        row = conn_with_template.execute(
            "SELECT * FROM progression_config WHERE exercise_template_id = 't001'"
        ).fetchone()
        assert row["rep_min"] == 8
        assert row["rep_max"] == 12
        assert row["weight_increment"] == 2.5
        assert row["enabled"] == 1


# ---------------------------------------------------------------------------
# get_all_configs
# ---------------------------------------------------------------------------


class TestGetAllConfigs:
    def test_empty_when_no_configs(self, conn: sqlite3.Connection) -> None:
        """get_all_configs returns empty list when no config rows exist."""
        configs = get_all_configs(conn)
        assert configs == []

    def test_returns_all_configs(self, conn_with_template: sqlite3.Connection) -> None:
        """get_all_configs returns all stored configs."""
        # Seed a second template
        conn_with_template.execute(
            """INSERT INTO exercise_templates (id, title, type, primary_muscle_group)
               VALUES ('t002', 'Squat', 'strength', 'Legs')"""
        )
        conn_with_template.commit()

        # Insert configs
        cfg1 = ProgressionConfig(exercise_template_id="t001", rep_min=8, rep_max=12)
        cfg2 = ProgressionConfig(exercise_template_id="t002", rep_min=5, rep_max=8)
        set_config(conn_with_template, cfg1)
        set_config(conn_with_template, cfg2)

        configs = get_all_configs(conn_with_template)
        assert len(configs) == 2
        ids = {c.exercise_template_id for c in configs}
        assert ids == {"t001", "t002"}

    def test_includes_defaults_not_stored(self, conn: sqlite3.Connection) -> None:
        """get_all_configs only returns stored rows (empty list if none)."""
        # No configs stored, no exercise templates seeded
        configs = get_all_configs(conn)
        assert configs == []


# ---------------------------------------------------------------------------
# add_history_entry
# ---------------------------------------------------------------------------


def _seed_template(c: sqlite3.Connection, tid: str, name: str) -> None:
    """Seed an exercise template for FK-dependent tests."""
    c.execute(
        """INSERT OR IGNORE INTO exercise_templates
           (id, title, type, primary_muscle_group)
           VALUES (?, ?, 'strength', 'General')""",
        (tid, name),
    )
    c.commit()


class TestAddHistoryEntry:
    def test_inserts_history_row(self, conn: sqlite3.Connection) -> None:
        """add_history_entry inserts a row and returns its id."""
        _seed_template(conn, "t001", "Bench Press")
        entry = ProgressionHistoryEntry(
            id=-1,  # will be replaced
            exercise_template_id="t001",
            checked_at="2024-06-15T08:00:00Z",
            status="progress",
            current_weight_kg=80.0,
            recommended_weight_kg=82.5,
            details='{"sets_analyzed": 3}',
        )
        row_id = add_history_entry(conn, entry)
        assert isinstance(row_id, int)
        assert row_id > 0

        row = conn.execute(
            "SELECT * FROM progression_history WHERE id = ?", (row_id,)
        ).fetchone()
        assert row["exercise_template_id"] == "t001"
        assert row["status"] == "progress"
        assert row["current_weight_kg"] == 80.0
        assert row["recommended_weight_kg"] == 82.5
        assert row["details"] == '{"sets_analyzed": 3}'

    def test_inserts_maintain_status(self, conn: sqlite3.Connection) -> None:
        """add_history_entry stores maintain status with null recommended."""
        _seed_template(conn, "t001", "Bench Press")
        entry = ProgressionHistoryEntry(
            id=-1,
            exercise_template_id="t001",
            checked_at="2024-06-15T08:00:00Z",
            status="maintain",
            current_weight_kg=80.0,
            recommended_weight_kg=None,
            details=None,
        )
        row_id = add_history_entry(conn, entry)

        row = conn.execute(
            "SELECT * FROM progression_history WHERE id = ?", (row_id,)
        ).fetchone()
        assert row["status"] == "maintain"
        assert row["recommended_weight_kg"] is None
        assert row["details"] is None

    def test_inserts_insufficient_data_status(self, conn: sqlite3.Connection) -> None:
        """add_history_entry stores insufficient_data status."""
        _seed_template(conn, "t001", "Bench Press")
        entry = ProgressionHistoryEntry(
            id=-1,
            exercise_template_id="t001",
            checked_at="2024-06-15T08:00:00Z",
            status="insufficient_data",
            current_weight_kg=None,
            recommended_weight_kg=None,
            details=None,
        )
        row_id = add_history_entry(conn, entry)
        row = conn.execute(
            "SELECT * FROM progression_history WHERE id = ?", (row_id,)
        ).fetchone()
        assert row["status"] == "insufficient_data"
        assert row["current_weight_kg"] is None

    def test_increments_id_on_multiple_inserts(self, conn: sqlite3.Connection) -> None:
        """Multiple history entries get different auto-incremented ids."""
        _seed_template(conn, "t001", "Bench Press")
        e1 = ProgressionHistoryEntry(
            id=-1, exercise_template_id="t001",
            checked_at="2024-06-15T08:00:00Z", status="maintain",
            current_weight_kg=None, recommended_weight_kg=None, details=None,
        )
        e2 = ProgressionHistoryEntry(
            id=-1, exercise_template_id="t001",
            checked_at="2024-06-16T08:00:00Z", status="progress",
            current_weight_kg=80.0, recommended_weight_kg=82.5, details=None,
        )
        id1 = add_history_entry(conn, e1)
        id2 = add_history_entry(conn, e2)
        assert id2 > id1


# ---------------------------------------------------------------------------
# get_history
# ---------------------------------------------------------------------------


class TestGetHistory:
    def test_returns_empty_when_no_history(self, conn: sqlite3.Connection) -> None:
        """get_history returns empty list when no history exists."""
        entries = get_history(conn, "t001")
        assert entries == []

    def test_returns_all_entries_for_template(
        self, conn: sqlite3.Connection
    ) -> None:
        """get_history returns all entries for a given template."""
        _seed_template(conn, "t001", "Bench Press")
        e1 = ProgressionHistoryEntry(
            id=-1, exercise_template_id="t001",
            checked_at="2024-06-15T08:00:00Z", status="maintain",
            current_weight_kg=80.0, recommended_weight_kg=None, details=None,
        )
        e2 = ProgressionHistoryEntry(
            id=-1, exercise_template_id="t001",
            checked_at="2024-06-16T08:00:00Z", status="progress",
            current_weight_kg=80.0, recommended_weight_kg=82.5, details=None,
        )
        add_history_entry(conn, e1)
        add_history_entry(conn, e2)

        entries = get_history(conn, "t001")
        assert len(entries) == 2
        assert all(e.exercise_template_id == "t001" for e in entries)

    def test_does_not_return_other_templates(
        self, conn: sqlite3.Connection
    ) -> None:
        """get_history only returns entries for the requested template."""
        _seed_template(conn, "t001", "Bench Press")
        _seed_template(conn, "t002", "Squat")
        e1 = ProgressionHistoryEntry(
            id=-1, exercise_template_id="t001",
            checked_at="2024-06-15T08:00:00Z", status="maintain",
            current_weight_kg=None, recommended_weight_kg=None, details=None,
        )
        e2 = ProgressionHistoryEntry(
            id=-1, exercise_template_id="t002",
            checked_at="2024-06-15T08:00:00Z", status="progress",
            current_weight_kg=100.0, recommended_weight_kg=102.5, details=None,
        )
        add_history_entry(conn, e1)
        add_history_entry(conn, e2)

        entries = get_history(conn, "t001")
        assert len(entries) == 1
        assert entries[0].exercise_template_id == "t001"


# ---------------------------------------------------------------------------
# get_latest_history
# ---------------------------------------------------------------------------


class TestGetLatestHistory:
    def test_returns_none_when_no_history(self, conn: sqlite3.Connection) -> None:
        """get_latest_history returns None when no history exists."""
        latest = get_latest_history(conn, "t001")
        assert latest is None

    def test_returns_most_recent_entry(
        self, conn: sqlite3.Connection
    ) -> None:
        """get_latest_history returns the most recent entry by id."""
        _seed_template(conn, "t001", "Bench Press")
        e1 = ProgressionHistoryEntry(
            id=-1, exercise_template_id="t001",
            checked_at="2024-06-15T08:00:00Z", status="maintain",
            current_weight_kg=80.0, recommended_weight_kg=None, details=None,
        )
        e2 = ProgressionHistoryEntry(
            id=-1, exercise_template_id="t001",
            checked_at="2024-06-16T08:00:00Z", status="progress",
            current_weight_kg=80.0, recommended_weight_kg=82.5, details=None,
        )
        id1 = add_history_entry(conn, e1)
        id2 = add_history_entry(conn, e2)

        latest = get_latest_history(conn, "t001")
        assert latest is not None
        assert latest.id == id2
        assert latest.status == "progress"


# ---------------------------------------------------------------------------
# get_template
# ---------------------------------------------------------------------------


class TestGetTemplate:
    def test_returns_template_when_exists(self, conn: sqlite3.Connection) -> None:
        """get_template returns the template dict when the row exists."""
        conn.execute(
            """INSERT INTO exercise_templates (id, title, type, primary_muscle_group)
               VALUES ('t001', 'Bench Press', 'strength', 'Chest')"""
        )
        conn.commit()
        tpl = get_template(conn, "t001")
        assert tpl is not None
        assert tpl["id"] == "t001"
        assert tpl["title"] == "Bench Press"
        assert tpl["type"] == "strength"

    def test_returns_none_when_not_found(self, conn: sqlite3.Connection) -> None:
        """get_template returns None when no row matches."""
        tpl = get_template(conn, "nonexistent")
        assert tpl is None


# ---------------------------------------------------------------------------
# get_normal_sets
# ---------------------------------------------------------------------------


class TestGetNormalSets:
    def test_returns_empty_when_no_sets(self, conn: sqlite3.Connection) -> None:
        """get_normal_sets returns empty list when no sets exist."""
        result = get_normal_sets(conn, "t001")
        assert result == []

    def test_returns_only_normal_sets_for_template(
        self, conn: sqlite3.Connection
    ) -> None:
        """get_normal_sets returns only normal, non-deleted sets for the template."""
        conn.execute(
            """INSERT INTO exercise_templates (id, title, type, primary_muscle_group)
               VALUES ('t001', 'Bench Press', 'strength', 'Chest')"""
        )
        conn.execute(
            """INSERT INTO workouts (id, title, start_time)
               VALUES ('w001', 'Push Day', '2024-06-01T08:00:00Z')"""
        )
        conn.execute(
            """INSERT INTO exercises (id, workout_id, exercise_template_id, title)
               VALUES (1, 'w001', 't001', 'Bench Press')"""
        )
        conn.execute(
            """INSERT INTO sets (id, exercise_id, set_index, type, weight_kg, reps)
               VALUES (1, 1, 0, 'normal', 80.0, 10),
                      (2, 1, 1, 'normal', 80.0, 10),
                      (3, 1, 2, 'warmup', 40.0, 8),
                      (4, 1, 3, 'dropset', 60.0, 6)"""
        )
        conn.commit()
        result = get_normal_sets(conn, "t001")
        assert len(result) == 2
        assert all(s["type"] == "normal" for s in result)
        assert all(s["set_index"] in (0, 1) for s in result)

    def test_orders_by_start_time_desc(self, conn: sqlite3.Connection) -> None:
        """get_normal_sets orders by workout start_time DESC, set_index ASC."""
        conn.execute(
            """INSERT INTO exercise_templates (id, title, type, primary_muscle_group)
               VALUES ('t001', 'Bench Press', 'strength', 'Chest')"""
        )
        conn.execute(
            """INSERT INTO workouts (id, title, start_time)
               VALUES ('w001', 'Old Workout', '2024-05-01T08:00:00Z'),
                      ('w002', 'New Workout', '2024-06-01T08:00:00Z')"""
        )
        conn.execute(
            """INSERT INTO exercises (id, workout_id, exercise_template_id, title)
               VALUES (1, 'w001', 't001', 'Bench Press'),
                      (2, 'w002', 't001', 'Bench Press')"""
        )
        conn.execute(
            """INSERT INTO sets (id, exercise_id, set_index, type, weight_kg, reps)
               VALUES (1, 1, 0, 'normal', 80.0, 10),
                      (2, 2, 0, 'normal', 85.0, 8)"""
        )
        conn.commit()
        result = get_normal_sets(conn, "t001")
        assert len(result) == 2
        # Most recent workout first
        assert result[0]["start_time"] == "2024-06-01T08:00:00Z"
        assert result[1]["start_time"] == "2024-05-01T08:00:00Z"

    def test_includes_required_fields(self, conn: sqlite3.Connection) -> None:
        """get_normal_sets result includes weight_kg, reps, start_time, exercise_id."""
        conn.execute(
            """INSERT INTO exercise_templates (id, title, type, primary_muscle_group)
               VALUES ('t001', 'Bench Press', 'strength', 'Chest')"""
        )
        conn.execute(
            """INSERT INTO workouts (id, title, start_time)
               VALUES ('w001', 'Push Day', '2024-06-01T08:00:00Z')"""
        )
        conn.execute(
            """INSERT INTO exercises (id, workout_id, exercise_template_id, title)
               VALUES (1, 'w001', 't001', 'Bench Press')"""
        )
        conn.execute(
            """INSERT INTO sets (id, exercise_id, set_index, type, weight_kg, reps)
               VALUES (1, 1, 0, 'normal', 80.0, 10)"""
        )
        conn.commit()
        result = get_normal_sets(conn, "t001")
        assert len(result) == 1
        assert "weight_kg" in result[0]
        assert "reps" in result[0]
        assert "start_time" in result[0]
        assert "exercise_id" in result[0]
        assert "set_index" in result[0]
