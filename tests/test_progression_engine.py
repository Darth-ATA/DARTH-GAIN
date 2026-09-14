"""Tests for darth_gain.progression.ProgressionEngine — algorithm unit tests."""

from __future__ import annotations

import json
import sqlite3

import pytest

from darth_gain.db.engine import create_engine, create_tables
from darth_gain.progression import ProgressionEngine
from darth_gain.progression.models import ProgressionConfig
from darth_gain.progression.repo import set_config, get_config

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn() -> sqlite3.Connection:
    """Return an in-memory SQLite with all tables created."""
    c = create_engine(":memory:")
    create_tables(c)
    return c


def _seed_template(conn: sqlite3.Connection, tid: str = "t001", name: str = "Bench Press", exercise_type: str = "strength") -> None:
    conn.execute(
        "INSERT OR IGNORE INTO exercise_templates (id, title, type, primary_muscle_group) "
        "VALUES (?, ?, ?, 'Chest')",
        (tid, name, exercise_type),
    )
    conn.commit()


def _seed_workout(
    conn: sqlite3.Connection,
    wid: str,
    start_time: str,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO workouts (id, title, start_time) VALUES (?, ?, ?)",
        (wid, "Workout", start_time),
    )
    conn.commit()


def _seed_exercise(
    conn: sqlite3.Connection,
    eid: int,
    wid: str,
    tid: str = "t001",
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO exercises (id, workout_id, exercise_template_id, title) "
        "VALUES (?, ?, ?, 'Bench Press')",
        (eid, wid, tid),
    )
    conn.commit()


def _seed_set(
    conn: sqlite3.Connection,
    sid: int,
    eid: int,
    set_index: int = 0,
    weight_kg: float | None = 80.0,
    reps: int | None = 10,
    type_: str = "normal",
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO sets (id, exercise_id, set_index, type, weight_kg, reps) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (sid, eid, set_index, type_, weight_kg, reps),
    )
    conn.commit()


def _seed_single_workout(
    conn: sqlite3.Connection,
    template_id: str = "t001",
    exercise_name: str = "Bench Press",
    workout_id: str = "w001",
    start_time: str = "2024-06-01T08:00:00Z",
    exercise_id: int = 1,
    sets: list[tuple[float | None, int | None]] | None = None,
) -> None:
    """Seed one workout with one exercise and normal sets.

    Args:
        sets: List of (weight_kg, reps) tuples for normal sets.
    """
    if sets is None:
        sets = [(80.0, 10)]
    _seed_template(conn, template_id, exercise_name)
    _seed_workout(conn, workout_id, start_time)
    _seed_exercise(conn, exercise_id, workout_id, template_id)
    for idx, (w, r) in enumerate(sets):
        _seed_set(conn, idx + 1, exercise_id, idx, w, r)


# ---------------------------------------------------------------------------
# All sets at rep_max → progress
# ---------------------------------------------------------------------------


class TestAllSetsHitRepMax:
    def test_all_sets_at_max_returns_progress(self, conn: sqlite3.Connection) -> None:
        """3 normal sets at 12 reps with rep_max=12 → progress, recommended 82.5."""
        _seed_single_workout(
            conn,
            sets=[(80.0, 12), (80.0, 12), (80.0, 12)],
        )
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-06-02")
        assert result.recommendation == "increase to 82.5 kg"
        assert result.current_weight_kg == 80.0
        assert result.latest_reps == [12, 12, 12]
        assert result.top_of_range_reached is True
        assert result.error is None

    def test_sets_exceed_max_still_progress(self, conn: sqlite3.Connection) -> None:
        """Sets above rep_max still count as meeting criteria."""
        _seed_single_workout(
            conn,
            sets=[(80.0, 12), (80.0, 11), (80.0, 10)],
        )
        cfg = ProgressionConfig(exercise_template_id="t001", rep_min=8, rep_max=10)
        set_config(conn, cfg)
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-06-02")
        assert result.recommendation == "increase to 82.5 kg"
        assert result.top_of_range_reached is True

    def test_single_normal_set_at_max(self, conn: sqlite3.Connection) -> None:
        """Single normal set at rep_max still triggers progress."""
        _seed_single_workout(
            conn,
            sets=[(80.0, 12)],
        )
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-06-02")
        assert result.recommendation == "increase to 82.5 kg"
        assert result.top_of_range_reached is True


# ---------------------------------------------------------------------------
# One set below rep_max → maintain
# ---------------------------------------------------------------------------


class TestBelowRepMax:
    def test_one_set_below_returns_maintain(self, conn: sqlite3.Connection) -> None:
        """One set at 11 reps with rep_max=12 → maintain."""
        _seed_single_workout(
            conn,
            sets=[(80.0, 12), (80.0, 11), (80.0, 12)],
        )
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-06-02")
        assert result.recommendation == "keep at 80.0 kg"
        assert result.top_of_range_reached is False
        assert result.error is None

    def test_all_sets_below_returns_maintain(self, conn: sqlite3.Connection) -> None:
        """All sets below rep_max → maintain."""
        _seed_single_workout(
            conn,
            sets=[(80.0, 8), (80.0, 7), (80.0, 8)],
        )
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-06-02")
        assert result.recommendation == "keep at 80.0 kg"
        assert result.top_of_range_reached is False


# ---------------------------------------------------------------------------
# Multiple workouts — only most recent matters
# ---------------------------------------------------------------------------


class TestMultipleWorkouts:
    def test_only_most_recent_workout_matters(self, conn: sqlite3.Connection) -> None:
        """Older workout had all at 12, but recent workout has 10,10,10 → maintain."""
        _seed_template(conn, "t001", "Bench Press")
        # Old workout with all 12s
        _seed_workout(conn, "w001", "2024-05-01T08:00:00Z")
        _seed_exercise(conn, 1, "w001", "t001")
        _seed_set(conn, 1, 1, 0, 80.0, 12)
        _seed_set(conn, 2, 1, 1, 80.0, 12)
        _seed_set(conn, 3, 1, 2, 80.0, 12)
        # Recent workout with all 10s
        _seed_workout(conn, "w002", "2024-06-01T08:00:00Z")
        _seed_exercise(conn, 2, "w002", "t001")
        _seed_set(conn, 4, 2, 0, 80.0, 10)
        _seed_set(conn, 5, 2, 1, 80.0, 10)
        _seed_set(conn, 6, 2, 2, 80.0, 10)

        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-06-02")
        assert result.recommendation == "keep at 80.0 kg"
        assert result.top_of_range_reached is False


# ---------------------------------------------------------------------------
# Working weight resolution
# ---------------------------------------------------------------------------


class TestWorkingWeight:
    def test_mode_weight_is_used(self, conn: sqlite3.Connection) -> None:
        """Most common weight among normal sets is used as working weight."""
        _seed_single_workout(
            conn,
            sets=[(80.0, 10), (80.0, 10), (85.0, 8)],
        )
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-06-02")
        assert result.current_weight_kg == 80.0

    def test_tie_breaks_to_heavier(self, conn: sqlite3.Connection) -> None:
        """When weights are tied for frequency, heavier weight wins."""
        _seed_single_workout(
            conn,
            sets=[(80.0, 10), (85.0, 10), (80.0, 10), (85.0, 10)],
        )
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-06-02")
        assert result.current_weight_kg == 85.0

    def test_same_weight_all_sets(self, conn: sqlite3.Connection) -> None:
        """All sets at same weight → that weight is used."""
        _seed_single_workout(
            conn,
            sets=[(80.0, 10), (80.0, 10), (80.0, 10)],
        )
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-06-02")
        assert result.current_weight_kg == 80.0


# ---------------------------------------------------------------------------
# NULL filtering
# ---------------------------------------------------------------------------


class TestNullFiltering:
    def test_null_weight_skipped(self, conn: sqlite3.Connection) -> None:
        """Sets with NULL weight_kg are excluded from analysis."""
        _seed_single_workout(
            conn,
            sets=[(80.0, 12), (None, 12), (80.0, 12)],
        )
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-06-02")
        assert result.recommendation == "increase to 82.5 kg"
        assert result.current_weight_kg == 80.0

    def test_null_reps_skipped(self, conn: sqlite3.Connection) -> None:
        """Sets with NULL reps are excluded from analysis."""
        _seed_single_workout(
            conn,
            sets=[(80.0, 12), (80.0, None), (80.0, 12)],
        )
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-06-02")
        assert result.recommendation == "increase to 82.5 kg"

    def test_zero_weight_is_valid(self, conn: sqlite3.Connection) -> None:
        """weight_kg=0 is valid (bodyweight), not treated as NULL."""
        _seed_single_workout(
            conn,
            sets=[(0.0, 12), (0.0, 12), (0.0, 12)],
        )
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-06-02")
        assert result.recommendation == "increase to 2.5 kg"
        assert result.current_weight_kg == 0.0


# ---------------------------------------------------------------------------
# Insufficient data
# ---------------------------------------------------------------------------


class TestInsufficientData:
    def test_no_sets_at_all(self, conn: sqlite3.Connection) -> None:
        """No normal sets → insufficient_data."""
        _seed_template(conn, "t001", "Bench Press")
        engine = ProgressionEngine(conn)
        result = engine.check("t001")
        assert "Insufficient data" in result.recommendation
        assert result.error is None
        assert result.current_weight_kg is None

    def test_all_nulls_in_most_recent_workout(self, conn: sqlite3.Connection) -> None:
        """All sets in most recent workout have NULL weight or reps."""
        _seed_single_workout(
            conn,
            sets=[(None, None), (None, None)],
        )
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-06-02")
        assert "Insufficient data" in result.recommendation

    def test_deleted_sets(self, conn: sqlite3.Connection) -> None:
        """All sets are deleted → insufficient_data."""
        _seed_template(conn, "t001", "Bench Press")
        _seed_workout(conn, "w001", "2024-06-01T08:00:00Z")
        _seed_exercise(conn, 1, "w001", "t001")
        conn.execute(
            "INSERT INTO sets (id, exercise_id, set_index, type, weight_kg, reps, is_deleted) "
            "VALUES (1, 1, 0, 'normal', 80.0, 10, 1)"
        )
        conn.commit()
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-06-02")
        assert "Insufficient data" in result.recommendation


# ---------------------------------------------------------------------------
# Disabled config → skipped
# ---------------------------------------------------------------------------


class TestDisabledConfig:
    def test_disabled_returns_skipped(self, conn: sqlite3.Connection) -> None:
        """Config with enabled=0 → status skipped."""
        _seed_single_workout(conn)
        cfg = ProgressionConfig(exercise_template_id="t001", enabled=False)
        set_config(conn, cfg)
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-06-02")
        assert result.recommendation == "Progression checking is disabled for this exercise"
        assert result.error is None


# ---------------------------------------------------------------------------
# Unknown template
# ---------------------------------------------------------------------------


class TestUnknownTemplate:
    def test_unknown_template_has_error(self, conn: sqlite3.Connection) -> None:
        """Unknown template ID returns status with error populated."""
        engine = ProgressionEngine(conn)
        result = engine.check("nonexistent")
        assert result.error is not None
        assert "not found" in result.recommendation.lower()


# ---------------------------------------------------------------------------
# History persistence
# ---------------------------------------------------------------------------


class TestHistoryPersistence:
    def test_progress_persists_history(self, conn: sqlite3.Connection) -> None:
        """A progress check persists a history row with correct values."""
        _seed_single_workout(
            conn,
            sets=[(80.0, 12), (80.0, 12), (80.0, 12)],
        )
        engine = ProgressionEngine(conn)
        engine.check("t001", check_date="2024-06-02")

        row = conn.execute(
            "SELECT * FROM progression_history WHERE exercise_template_id = 't001'"
        ).fetchone()
        assert row is not None
        assert row["status"] == "progress"
        assert row["current_weight_kg"] == 80.0
        assert row["recommended_weight_kg"] == 82.5
        details = json.loads(row["details"])
        assert details["working_weight_kg"] == 80.0
        assert details["sets_analyzed"] == 3

    def test_maintain_persists_history(self, conn: sqlite3.Connection) -> None:
        """A maintain check persists a history row with null recommended."""
        _seed_single_workout(
            conn,
            sets=[(80.0, 11), (80.0, 10)],
        )
        engine = ProgressionEngine(conn)
        engine.check("t001", check_date="2024-06-02")

        row = conn.execute(
            "SELECT status, recommended_weight_kg FROM progression_history WHERE exercise_template_id = 't001'"
        ).fetchone()
        assert row["status"] == "maintain"
        assert row["recommended_weight_kg"] is None

    def test_insufficient_data_persists_history(self, conn: sqlite3.Connection) -> None:
        """An insufficient_data check persists a history row."""
        _seed_template(conn, "t001", "Bench Press")
        engine = ProgressionEngine(conn)
        engine.check("t001")

        row = conn.execute(
            "SELECT status FROM progression_history WHERE exercise_template_id = 't001'"
        ).fetchone()
        assert row["status"] == "insufficient_data"

    def test_skipped_persists_history(self, conn: sqlite3.Connection) -> None:
        """A skipped check persists a history row."""
        _seed_single_workout(conn)
        cfg = ProgressionConfig(exercise_template_id="t001", enabled=False)
        set_config(conn, cfg)
        engine = ProgressionEngine(conn)
        engine.check("t001", check_date="2024-06-02")

        row = conn.execute(
            "SELECT status FROM progression_history WHERE exercise_template_id = 't001'"
        ).fetchone()
        assert row["status"] == "skipped"


# ---------------------------------------------------------------------------
# Cross-exercise isolation
# ---------------------------------------------------------------------------


class TestCrossExerciseIsolation:
    def test_sets_from_other_exercises_ignored(self, conn: sqlite3.Connection) -> None:
        """Sets from different exercises don't affect each other's check."""
        _seed_template(conn, "t001", "Bench Press")
        _seed_template(conn, "t002", "Overhead Press")
        _seed_workout(conn, "w001", "2024-06-01T08:00:00Z")
        _seed_exercise(conn, 1, "w001", "t001")
        _seed_set(conn, 1, 1, 0, 80.0, 12)
        _seed_set(conn, 2, 1, 1, 80.0, 12)
        _seed_exercise(conn, 2, "w001", "t002")
        _seed_set(conn, 3, 2, 0, 50.0, 10)

        engine = ProgressionEngine(conn)
        result_t001 = engine.check("t001", check_date="2024-06-02")
        result_t002 = engine.check("t002", check_date="2024-06-02")

        assert result_t001.recommendation == "increase to 82.5 kg"
        assert result_t002.recommendation == "keep at 50.0 kg"

    def test_different_configs_per_exercise(self, conn: sqlite3.Connection) -> None:
        """Each exercise uses its own config."""
        _seed_template(conn, "t001", "Bench Press")
        _seed_template(conn, "t002", "Squat")
        _seed_workout(conn, "w001", "2024-06-01T08:00:00Z")
        _seed_exercise(conn, 1, "w001", "t001")
        _seed_set(conn, 1, 1, 0, 80.0, 12)
        _seed_exercise(conn, 2, "w001", "t002")
        _seed_set(conn, 2, 2, 0, 100.0, 7)

        cfg_squat = ProgressionConfig(
            exercise_template_id="t002", rep_min=5, rep_max=8, weight_increment=5.0
        )
        set_config(conn, cfg_squat)

        engine = ProgressionEngine(conn)
        r1 = engine.check("t001", check_date="2024-06-02")
        r2 = engine.check("t002", check_date="2024-06-02")

        assert r1.recommendation == "increase to 82.5 kg"  # default config, 12 max
        assert r2.recommendation == "keep at 100.0 kg"  # custom config, 8 max, 7 reps
        assert r2.rep_range == (5, 8)
        assert r1.rep_range == (8, 12)


# ---------------------------------------------------------------------------
# Detraining / Deload Detection
# ---------------------------------------------------------------------------


class TestDeloadDetection:
    """Tests for the time-gate deload detection feature."""

    def _seed_workout_with_date(
        self,
        conn: sqlite3.Connection,
        workout_id: str,
        start_time: str,
        template_id: str = "t001",
        exercise_id: int = 1,
        sets: list[tuple[float | None, int | None]] | None = None,
    ) -> None:
        """Seed a workout with exercise and sets for a specific date."""
        if sets is None:
            sets = [(80.0, 10)]
        _seed_template(conn, template_id, "Bench Press")
        _seed_workout(conn, workout_id, start_time)
        _seed_exercise(conn, exercise_id, workout_id, template_id)
        for idx, (w, r) in enumerate(sets):
            _seed_set(conn, idx + 1, exercise_id, idx, w, r)

    def test_intermediate_threshold_exceeded_triggers_deload(self, conn: sqlite3.Connection) -> None:
        """Gap exceeds intermediate threshold (2 weeks) → deload recommended."""
        # Last workout 21 days ago (3 weeks)
        self._seed_workout_with_date(
            conn, "w001", "2024-05-10T08:00:00Z", sets=[(100.0, 12), (100.0, 12), (100.0, 12)]
        )
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-05-31")  # 21 days = 3 weeks
        assert result.deload_recommended is True
        assert result.deload_weight_kg == 90.0  # 100 * 0.9
        assert result.current_weight_kg == 100.0
        assert "deload" in result.recommendation.lower()

    def test_novice_threshold_triggers_at_one_week(self, conn: sqlite3.Connection) -> None:
        """Novice triggers at 1 week (base-1) → deload at 8+ days (2 weeks elapsed)."""
        # Last workout 15 days ago (2 weeks = weeks_elapsed > 1)
        self._seed_workout_with_date(
            conn, "w001", "2024-05-16T08:00:00Z", sets=[(80.0, 12), (80.0, 12), (80.0, 12)]
        )
        cfg = ProgressionConfig(exercise_template_id="t001", deload_after_weeks=2, training_level="novice")
        set_config(conn, cfg)
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-05-31")  # 15 days = 2 weeks
        assert result.deload_recommended is True
        assert result.deload_weight_kg == 72.0  # 80 * 0.9

    def test_advanced_threshold_does_not_trigger_at_three_weeks(self, conn: sqlite3.Connection) -> None:
        """Advanced does NOT trigger at 3 weeks (base+1=3) → normal progression."""
        # Last workout 21 days ago (3 weeks)
        self._seed_workout_with_date(
            conn, "w001", "2024-05-10T08:00:00Z", sets=[(120.0, 12), (120.0, 12), (120.0, 12)]
        )
        cfg = ProgressionConfig(exercise_template_id="t001", deload_after_weeks=2, training_level="advanced")
        set_config(conn, cfg)
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-05-31")  # 21 days = 3 weeks
        assert result.deload_recommended is False
        assert "increase" in result.recommendation.lower()  # Normal progression

    def test_gap_at_threshold_uses_normal_progression(self, conn: sqlite3.Connection) -> None:
        """Gap exactly at threshold (2 weeks) → normal progression logic applies."""
        # Last workout 14 days ago (exactly 2 weeks)
        self._seed_workout_with_date(
            conn, "w001", "2024-05-17T08:00:00Z", sets=[(80.0, 12), (80.0, 12), (80.0, 12)]
        )
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-05-31")  # 14 days = 2 weeks
        assert result.deload_recommended is False
        assert "increase" in result.recommendation.lower()  # Normal progression

    def test_deload_weight_rounded_to_one_decimal(self, conn: sqlite3.Connection) -> None:
        """Deload weight rounded to 1 decimal place."""
        # 87.5kg with 10% deload = 78.75 → 78.8
        self._seed_workout_with_date(
            conn, "w001", "2024-05-10T08:00:00Z", sets=[(87.5, 12), (87.5, 12), (87.5, 12)]
        )
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-05-31")  # 21 days = 3 weeks
        assert result.deload_weight_kg == 78.8

    def test_sixteen_week_gap_capped_at_forty_percent_with_warning(self, conn: sqlite3.Connection) -> None:
        """16-week gap capped at 40% with warning in details."""
        # Last workout 112 days ago (16 weeks)
        self._seed_workout_with_date(
            conn, "w001", "2024-02-08T08:00:00Z", sets=[(100.0, 12), (100.0, 12), (100.0, 12)]
        )
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-05-31")  # 112 days = 16 weeks
        assert result.deload_recommended is True
        assert result.deload_weight_kg == 60.0  # 40% cap: 100 * 0.6
        # Check history has warning
        row = conn.execute(
            "SELECT details FROM progression_history WHERE exercise_template_id = 't001'"
        ).fetchone()
        import json
        details = json.loads(row["details"])
        assert "warning" in details
        assert details["warning"] == "gap_exceeds_12_weeks_capped_at_40_percent"
        assert details["deload_percent_used"] == 40

    def test_no_history_returns_insufficient_data_not_deload(self, conn: sqlite3.Connection) -> None:
        """No workout history → insufficient_data (not deload)."""
        _seed_template(conn, "t001", "Bench Press")
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-05-31")
        assert result.deload_recommended is False
        assert result.deload_weight_kg is None
        assert "insufficient" in result.recommendation.lower()

    def test_disabled_config_returns_skipped_bypasses_time_gate(self, conn: sqlite3.Connection) -> None:
        """Disabled config → skipped (bypasses time-gate)."""
        self._seed_workout_with_date(
            conn, "w001", "2024-05-10T08:00:00Z", sets=[(80.0, 12), (80.0, 12), (80.0, 12)]
        )
        cfg = ProgressionConfig(exercise_template_id="t001", enabled=False)
        set_config(conn, cfg)
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-05-31")  # Would trigger deload if enabled
        assert result.deload_recommended is False
        assert result.deload_weight_kg is None
        assert "disabled" in result.recommendation.lower()

    def test_history_persists_deload_recommended_with_correct_fields(self, conn: sqlite3.Connection) -> None:
        """History row stores deload_recommended with correct fields."""
        self._seed_workout_with_date(
            conn, "w001", "2024-05-10T08:00:00Z", sets=[(100.0, 12), (100.0, 12), (100.0, 12)]
        )
        engine = ProgressionEngine(conn)
        engine.check("t001", check_date="2024-05-31")

        row = conn.execute(
            "SELECT * FROM progression_history WHERE exercise_template_id = 't001'"
        ).fetchone()
        assert row["status"] == "deload_recommended"
        assert row["current_weight_kg"] == 100.0
        assert row["recommended_weight_kg"] == 90.0
        import json
        details = json.loads(row["details"])
        assert details["gap_weeks"] == 3
        assert details["effective_threshold"] == 2
        assert details["deload_percent_used"] == 10
        assert details["training_level"] == "intermediate"

    def test_config_validation_clamps_deload_percent_and_validates_training_level(self, conn: sqlite3.Connection) -> None:
        """set_config clamps deload_percent to [5,40] and validates training_level."""
        _seed_template(conn, "t001", "Bench Press")
        # Test clamping: <5 → 5, >40 → 40
        cfg_low = ProgressionConfig(exercise_template_id="t001", deload_percent=3)
        set_config(conn, cfg_low)
        got = get_config(conn, "t001")
        assert got.deload_percent == 5

        cfg_high = ProgressionConfig(exercise_template_id="t001", deload_percent=50)
        set_config(conn, cfg_high)
        got = get_config(conn, "t001")
        assert got.deload_percent == 40

        # Test invalid training_level raises ValueError
        cfg_bad_level = ProgressionConfig(exercise_template_id="t001", training_level="expert")
        try:
            set_config(conn, cfg_bad_level)
            assert False, "Expected ValueError"
        except ValueError:
            pass

    def test_muscle_group_defaults_compounds_three_weeks_fifteen_percent(self, conn: sqlite3.Connection) -> None:
        """Muscle-group defaults: compounds (legs) get 3w/15%."""
        _seed_template(conn, "t001", "Squat", exercise_type="strength")
        # Update muscle group to quadriceps (compound)
        conn.execute(
            "UPDATE exercise_templates SET primary_muscle_group = 'quadriceps' WHERE id = 't001'"
        )
        conn.commit()

        cfg = get_config(conn, "t001")
        assert cfg.deload_after_weeks == 3
        assert cfg.deload_percent == 15

    def test_check_date_injection_for_historical_checks(self, conn: sqlite3.Connection) -> None:
        """Historical check works with explicit check_date parameter."""
        # Workout 21 days before check_date
        self._seed_workout_with_date(
            conn, "w001", "2024-05-10T08:00:00Z", sets=[(100.0, 12), (100.0, 12), (100.0, 12)]
        )
        engine = ProgressionEngine(conn)
        # Check as if today is 2024-05-31 (21 days later = 3 weeks)
        result = engine.check("t001", check_date="2024-05-31")
        assert result.deload_recommended is True
        assert result.deload_weight_kg == 90.0

        # Same workout, check as if today is 2024-05-24 (14 days later = 2 weeks) - at threshold
        result2 = engine.check("t001", check_date="2024-05-24")
        assert result2.deload_recommended is False
        assert "increase" in result2.recommendation.lower()  # Normal progression (at threshold, not over)

    def test_bodyweight_exercise_zero_weight_deload(self, conn: sqlite3.Connection) -> None:
        """Bodyweight exercise (weight_kg=0) → deload_weight_kg = 0."""
        self._seed_workout_with_date(
            conn, "w001", "2024-05-10T08:00:00Z", sets=[(0.0, 12), (0.0, 12), (0.0, 12)]
        )
        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-05-31")  # 21 days = 3 weeks
        assert result.deload_recommended is True
        assert result.deload_weight_kg == 0.0
        assert result.current_weight_kg == 0.0

    def test_duration_exercise_skips_deload(self, conn: sqlite3.Connection) -> None:
        """Duration exercises skip deload check and use _check_duration."""
        _seed_template(conn, "t001", "Plank", exercise_type="duration")
        _seed_workout(conn, "w001", "2024-05-10T08:00:00Z")
        _seed_exercise(conn, 1, "w001", "t001")
        # Duration sets use duration_seconds
        conn.execute(
            "INSERT INTO sets (id, exercise_id, set_index, type, duration_seconds) VALUES (1, 1, 0, 'normal', 60)"
        )
        conn.commit()

        cfg = ProgressionConfig(exercise_template_id="t001", deload_after_weeks=2, training_level="intermediate")
        set_config(conn, cfg)

        engine = ProgressionEngine(conn)
        result = engine.check("t001", check_date="2024-05-31")  # 21 days = 3 weeks
        # Duration exercises don't get deload, they use _check_duration logic
        assert result.deload_recommended is False
