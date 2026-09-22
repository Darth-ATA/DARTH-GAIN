"""Tests for export schemas."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from darth_gain.web.schemas.export import (
    ExportRequest,
    SetExport,
    ExerciseExport,
    WorkoutExport,
    ExerciseSummary,
    ExportSummary,
    RoutineMeta,
    ExportWindow,
    RoutineExportResponse,
    compute_deload_weeks,
    compute_progression_trends,
)


# ---------------------------------------------------------------------------
# ExportRequest
# ---------------------------------------------------------------------------


def test_export_request_defaults() -> None:
    """Default weeks=8, tz=UTC."""
    req = ExportRequest()
    assert req.weeks == 8
    assert req.tz == "UTC"


def test_export_request_valid_weeks() -> None:
    """Valid weeks in range 4-24."""
    for w in (4, 8, 12, 16, 20, 24):
        req = ExportRequest(weeks=w)
        assert req.weeks == w


def test_export_request_invalid_weeks_low() -> None:
    """Weeks < 4 raises validation error."""
    with pytest.raises(ValueError):
        ExportRequest(weeks=3)


def test_export_request_invalid_weeks_high() -> None:
    """Weeks > 24 raises validation error."""
    with pytest.raises(ValueError):
        ExportRequest(weeks=25)


def test_export_request_invalid_tz() -> None:
    """Invalid timezone pattern raises validation error."""
    with pytest.raises(ValueError):
        ExportRequest(tz="invalid/timezone!")


def test_export_request_valid_tz() -> None:
    """Valid IANA timezone accepted."""
    req = ExportRequest(tz="America/Argentina/Buenos_Aires")
    assert req.tz == "America/Argentina/Buenos_Aires"


# ---------------------------------------------------------------------------
# SetExport
# ---------------------------------------------------------------------------


def test_set_export_all_fields() -> None:
    """SetExport accepts all fields including nulls."""
    s = SetExport(
        set_index=0,
        type="normal",
        weight_kg=100.0,
        reps=8,
        distance_meters=None,
        duration_seconds=None,
        rpe=8.5,
    )
    assert s.weight_kg == 100.0
    assert s.rpe == 8.5


def test_set_export_null_rpe() -> None:
    """SetExport allows null RPE."""
    s = SetExport(set_index=0, type="normal", weight_kg=100.0, reps=8, rpe=None)
    assert s.rpe is None


def test_set_export_types() -> None:
    """SetExport accepts all set types."""
    for t in ("normal", "warmup", "drop", "failure"):
        s = SetExport(set_index=0, type=t)
        assert s.type == t


# ---------------------------------------------------------------------------
# ExerciseExport
# ---------------------------------------------------------------------------


def test_exercise_export() -> None:
    """ExerciseExport with sets."""
    ex = ExerciseExport(
        template_id="ex-1",
        title="Bench Press",
        muscle_group="chest",
        sets=[
            SetExport(set_index=0, type="normal", weight_kg=100, reps=8, rpe=8.0),
            SetExport(set_index=1, type="normal", weight_kg=100, reps=8, rpe=8.5),
        ],
    )
    assert len(ex.sets) == 2
    assert ex.muscle_group == "chest"


# ---------------------------------------------------------------------------
# WorkoutExport
# ---------------------------------------------------------------------------


def test_workout_export() -> None:
    """WorkoutExport with exercises."""
    dt = datetime(2026, 8, 25, 10, 0, 0, tzinfo=timezone.utc)
    wo = WorkoutExport(
        workout_id="wo-1",
        date=dt,
        exercises=[
            ExerciseExport(
                template_id="ex-1",
                title="Bench Press",
                muscle_group="chest",
                sets=[SetExport(set_index=0, type="normal", weight_kg=100, reps=8)],
            )
        ],
    )
    assert wo.workout_id == "wo-1"
    assert wo.date == dt


# ---------------------------------------------------------------------------
# ExerciseSummary
# ---------------------------------------------------------------------------


def test_exercise_summary_null_rpe() -> None:
    """ExerciseSummary handles null RPE fields."""
    es = ExerciseSummary(
        template_id="ex-1",
        title="Bench Press",
        muscle_group="chest",
        total_sets=4,
        total_volume_kg=3200.0,
        avg_weight_kg=100.0,
        max_weight_kg=105.0,
        progression_slope_kg_per_week=None,
        r2=None,
        avg_rpe=None,
        max_rpe=None,
        sets_with_rpe=0,
    )
    assert es.avg_rpe is None
    assert es.sets_with_rpe == 0


def test_exercise_summary_with_rpe() -> None:
    """ExerciseSummary with RPE data."""
    es = ExerciseSummary(
        template_id="ex-1",
        title="Bench Press",
        muscle_group="chest",
        total_sets=4,
        total_volume_kg=3200.0,
        avg_weight_kg=100.0,
        max_weight_kg=105.0,
        progression_slope_kg_per_week=0.5,
        r2=0.85,
        avg_rpe=8.2,
        max_rpe=9.0,
        sets_with_rpe=3,
    )
    assert es.avg_rpe == 8.2
    assert es.sets_with_rpe == 3


# ---------------------------------------------------------------------------
# ExportSummary
# ---------------------------------------------------------------------------


def test_export_summary() -> None:
    """ExportSummary with all fields."""
    es = ExerciseSummary(
        template_id="ex-1",
        title="Bench Press",
        muscle_group="chest",
        total_sets=4,
        total_volume_kg=3200.0,
        avg_weight_kg=100.0,
        max_weight_kg=105.0,
        progression_slope_kg_per_week=0.5,
        r2=0.85,
        avg_rpe=8.2,
        max_rpe=9.0,
        sets_with_rpe=3,
    )
    summary = ExportSummary(
        total_workouts=8,
        frequency_per_week=2.0,
        volume_by_muscle_group={"chest": 3200.0, "triceps": 1800.0},
        progression_trends={"ex-1": {"slope": 0.5, "r2": 0.85}},
        deload_weeks_detected=["2026-W30", "2026-W34"],
        exercise_summaries=[es],
    )
    assert summary.total_workouts == 8
    assert summary.frequency_per_week == 2.0
    assert "chest" in summary.volume_by_muscle_group


# ---------------------------------------------------------------------------
# RoutineMeta, ExportWindow, RoutineExportResponse
# ---------------------------------------------------------------------------


def test_routine_meta() -> None:
    """RoutineMeta serialization."""
    dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    meta = RoutineMeta(routine_id="r-1", routine_title="Push Day", routine_created_at=dt)
    assert meta.routine_id == "r-1"


def test_export_window() -> None:
    """ExportWindow serialization."""
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    end = datetime(2026, 8, 26, tzinfo=timezone.utc)
    win = ExportWindow(start=start, end=end, weeks_analyzed=8, timezone="UTC")
    assert win.weeks_analyzed == 8


def test_routine_export_response_serialization() -> None:
    """Full response serializes to JSON correctly."""
    dt = datetime(2026, 8, 25, 10, 0, 0, tzinfo=timezone.utc)
    response = RoutineExportResponse(
        meta=RoutineMeta(
            routine_id="r-1",
            routine_title="Push Day",
            routine_created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        window=ExportWindow(
            start=datetime(2026, 7, 1, tzinfo=timezone.utc),
            end=datetime(2026, 8, 26, tzinfo=timezone.utc),
            weeks_analyzed=8,
            timezone="UTC",
        ),
        workouts=[
            WorkoutExport(
                workout_id="wo-1",
                date=dt,
                exercises=[
                    ExerciseExport(
                        template_id="ex-1",
                        title="Bench Press",
                        muscle_group="chest",
                        sets=[SetExport(set_index=0, type="normal", weight_kg=100, reps=8)],
                    )
                ],
            )
        ],
        summary=ExportSummary(
            total_workouts=1,
            frequency_per_week=0.25,
            volume_by_muscle_group={"chest": 800.0},
            progression_trends={},
            deload_weeks_detected=[],
            exercise_summaries=[
                ExerciseSummary(
                    template_id="ex-1",
                    title="Bench Press",
                    muscle_group="chest",
                    total_sets=1,
                    total_volume_kg=800.0,
                    avg_weight_kg=100.0,
                    max_weight_kg=100.0,
                    sets_with_rpe=0,
                )
            ],
        ),
    )
    # Test serialization
    json_str = response.model_dump_json()
    assert "Push Day" in json_str
    assert "Bench Press" in json_str
    assert "800.0" in json_str


# ---------------------------------------------------------------------------
# Helpers: compute_deload_weeks, compute_progression_trends
# ---------------------------------------------------------------------------


def test_compute_deload_weeks_detects_drop() -> None:
    """Deload detected when >=2 muscle groups drop >=20%."""
    from darth_gain.web.schemas.export import WorkoutExport, ExerciseExport, SetExport

    # Week 1: high volume
    wo1 = WorkoutExport(
        workout_id="wo1",
        date=datetime(2026, 7, 1, tzinfo=timezone.utc),
        exercises=[
            ExerciseExport(
                template_id="ex1",
                title="Bench",
                muscle_group="chest",
                sets=[SetExport(set_index=0, type="normal", weight_kg=100, reps=10)],
            ),
            ExerciseExport(
                template_id="ex2",
                title="Squat",
                muscle_group="quads",
                sets=[SetExport(set_index=0, type="normal", weight_kg=140, reps=10)],
            ),
        ],
    )
    # Week 2: deload (both drop >20%)
    wo2 = WorkoutExport(
        workout_id="wo2",
        date=datetime(2026, 7, 8, tzinfo=timezone.utc),
        exercises=[
            ExerciseExport(
                template_id="ex1",
                title="Bench",
                muscle_group="chest",
                sets=[SetExport(set_index=0, type="normal", weight_kg=70, reps=10)],
            ),
            ExerciseExport(
                template_id="ex2",
                title="Squat",
                muscle_group="quads",
                sets=[SetExport(set_index=0, type="normal", weight_kg=100, reps=10)],
            ),
        ],
    )
    templates = {"ex1": {"primary_muscle_group": "chest"}, "ex2": {"primary_muscle_group": "quads"}}

    deloads = compute_deload_weeks([wo1, wo2], templates)
    # Week 2 (2026-W28) should be detected as deload
    assert "2026-W28" in deloads


def test_compute_deload_weeks_no_deload() -> None:
    """No deload when only one muscle group drops."""
    from darth_gain.web.schemas.export import WorkoutExport, ExerciseExport, SetExport

    wo1 = WorkoutExport(
        workout_id="wo1",
        date=datetime(2026, 7, 1, tzinfo=timezone.utc),
        exercises=[
            ExerciseExport(
                template_id="ex1",
                title="Bench",
                muscle_group="chest",
                sets=[SetExport(set_index=0, type="normal", weight_kg=100, reps=10)],
            ),
        ],
    )
    wo2 = WorkoutExport(
        workout_id="wo2",
        date=datetime(2026, 7, 8, tzinfo=timezone.utc),
        exercises=[
            ExerciseExport(
                template_id="ex1",
                title="Bench",
                muscle_group="chest",
                sets=[SetExport(set_index=0, type="normal", weight_kg=70, reps=10)],
            ),
        ],
    )
    templates = {"ex1": {"primary_muscle_group": "chest"}}

    deloads = compute_deload_weeks([wo1, wo2], templates)
    assert deloads == []


def test_compute_progression_trends() -> None:
    """Progression trend computed for exercise with >=4 weeks."""
    from darth_gain.web.schemas.export import WorkoutExport, ExerciseExport, SetExport

    # 4 weeks of increasing bench press
    workouts = []
    for i, w in enumerate([100, 102.5, 105, 107.5]):
        workouts.append(
            WorkoutExport(
                workout_id=f"wo{i}",
                date=datetime(2026, 7, 1 + i * 7, tzinfo=timezone.utc),
                exercises=[
                    ExerciseExport(
                        template_id="bench",
                        title="Bench Press",
                        muscle_group="chest",
                        sets=[SetExport(set_index=0, type="normal", weight_kg=w, reps=8)],
                    )
                ],
            )
        )

    trends = compute_progression_trends(workouts)
    assert "bench" in trends
    assert trends["bench"]["slope"] > 0  # positive progression
    assert 0 <= trends["bench"]["r2"] <= 1


def test_compute_progression_trends_insufficient_data() -> None:
    """No trend when < 4 data points."""
    from darth_gain.web.schemas.export import WorkoutExport, ExerciseExport, SetExport

    workouts = [
        WorkoutExport(
            workout_id="wo1",
            date=datetime(2026, 7, 1, tzinfo=timezone.utc),
            exercises=[
                ExerciseExport(
                    template_id="bench",
                    title="Bench Press",
                    muscle_group="chest",
                    sets=[SetExport(set_index=0, type="normal", weight_kg=100, reps=8)],
                )
            ],
        )
    ]
    trends = compute_progression_trends(workouts)
    assert trends == {}