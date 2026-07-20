"""Tests for darth_gain.progression.models — domain dataclasses."""

from __future__ import annotations

from darth_gain.progression.models import (
    ProgressionConfig,
    ProgressionHistoryEntry,
    ProgressionStatus,
)


class TestProgressionConfig:
    """ProgressionConfig dataclass construction and defaults."""

    def test_default_construction(self) -> None:
        """ProgressionConfig constructs with defaults: 8, 12, 2.5, True."""
        cfg = ProgressionConfig(exercise_template_id="t001")
        assert cfg.exercise_template_id == "t001"
        assert cfg.rep_min == 8
        assert cfg.rep_max == 12
        assert cfg.weight_increment == 2.5
        assert cfg.enabled is True

    def test_all_fields_override(self) -> None:
        """ProgressionConfig accepts overrides for every field."""
        cfg = ProgressionConfig(
            exercise_template_id="t002",
            rep_min=5,
            rep_max=10,
            weight_increment=5.0,
            enabled=False,
        )
        assert cfg.exercise_template_id == "t002"
        assert cfg.rep_min == 5
        assert cfg.rep_max == 10
        assert cfg.weight_increment == 5.0
        assert cfg.enabled is False

    def test_partial_override(self) -> None:
        """ProgressionConfig partial override keeps defaults for unspecified fields."""
        cfg = ProgressionConfig(exercise_template_id="t003", rep_min=6)
        assert cfg.rep_min == 6
        assert cfg.rep_max == 12  # default
        assert cfg.weight_increment == 2.5  # default
        assert cfg.enabled is True  # default


class TestProgressionStatus:
    """ProgressionStatus dataclass construction."""

    def test_success_construction(self) -> None:
        """ProgressionStatus with no error."""
        status = ProgressionStatus(
            exercise_template_id="t001",
            exercise_name="Bench Press",
            rep_range=(8, 12),
            current_weight_kg=80.0,
            latest_reps=[12, 12, 12],
            top_of_range_reached=True,
            recommendation="increase to 82.5 kg",
            error=None,
        )
        assert status.exercise_template_id == "t001"
        assert status.exercise_name == "Bench Press"
        assert status.rep_range == (8, 12)
        assert status.current_weight_kg == 80.0
        assert status.latest_reps == [12, 12, 12]
        assert status.top_of_range_reached is True
        assert status.recommendation == "increase to 82.5 kg"
        assert status.error is None

    def test_error_construction(self) -> None:
        """ProgressionStatus with an error message."""
        status = ProgressionStatus(
            exercise_template_id="t999",
            exercise_name="Unknown",
            rep_range=(8, 12),
            current_weight_kg=None,
            latest_reps=[],
            top_of_range_reached=False,
            recommendation="no data",
            error="Exercise template not found: t999",
        )
        assert status.error == "Exercise template not found: t999"
        assert status.current_weight_kg is None
        assert status.latest_reps == []

    def test_rep_range_is_tuple(self) -> None:
        """ProgressionStatus.rep_range is a tuple of two ints."""
        status = ProgressionStatus(
            exercise_template_id="t001",
            exercise_name="Squat",
            rep_range=(6, 10),
            current_weight_kg=100.0,
            latest_reps=[10, 9, 10],
            top_of_range_reached=False,
            recommendation="keep at 100.0 kg",
            error=None,
        )
        assert isinstance(status.rep_range, tuple)
        rmin, rmax = status.rep_range
        assert rmin == 6
        assert rmax == 10


class TestProgressionHistoryEntry:
    """ProgressionHistoryEntry dataclass construction."""

    def test_full_construction(self) -> None:
        """ProgressionHistoryEntry constructs with all fields."""
        entry = ProgressionHistoryEntry(
            id=1,
            exercise_template_id="t001",
            checked_at="2024-06-15T08:00:00Z",
            status="progress",
            current_weight_kg=80.0,
            recommended_weight_kg=82.5,
            details='{"sets_analyzed": 3}',
        )
        assert entry.id == 1
        assert entry.exercise_template_id == "t001"
        assert entry.checked_at == "2024-06-15T08:00:00Z"
        assert entry.status == "progress"
        assert entry.current_weight_kg == 80.0
        assert entry.recommended_weight_kg == 82.5
        assert entry.details == '{"sets_analyzed": 3}'

    def test_nullable_fields(self) -> None:
        """ProgressionHistoryEntry nullable fields default to None."""
        entry = ProgressionHistoryEntry(
            id=2,
            exercise_template_id="t002",
            checked_at="2024-06-15T09:00:00Z",
            status="maintain",
            current_weight_kg=None,
            recommended_weight_kg=None,
            details=None,
        )
        assert entry.current_weight_kg is None
        assert entry.recommended_weight_kg is None
        assert entry.details is None
