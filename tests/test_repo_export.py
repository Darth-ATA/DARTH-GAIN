"""Tests for repo export query."""

from __future__ import annotations

import sqlite3
import pytest

from darth_gain.db.engine import create_engine, create_tables
from darth_gain.db.repo import (
    upsert_workout,
    upsert_templates,
    upsert_routine,
    get_routine_export,
)


@pytest.fixture
def db() -> sqlite3.Connection:
    """Create in-memory test database with schema."""
    conn = create_engine(":memory:")
    create_tables(conn)
    yield conn
    conn.close()


def setup_test_data(db: sqlite3.Connection) -> dict[str, str]:
    """Insert test routine, templates, workouts, exercises, sets.

    Returns dict with routine_id, template_ids, workout_ids.
    """
    # Routine
    routine_id = "routine-push-day"
    upsert_routine(db, {
        "id": routine_id,
        "title": "Push Day",
        "folder_id": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    })

    # Templates
    template_ids = {
        "bench": "tmpl-bench-press",
        "squat": "tmpl-squat",
        "ohp": "tmpl-ohp",
    }
    upsert_templates(db, [
        {"id": template_ids["bench"], "title": "Bench Press", "type": "weight_reps",
         "primary_muscle_group": "chest", "other_muscle_groups": "[]",
         "equipment": "barbell", "is_custom": 0},
        {"id": template_ids["squat"], "title": "Squat", "type": "weight_reps",
         "primary_muscle_group": "quads", "other_muscle_groups": "[]",
         "equipment": "barbell", "is_custom": 0},
        {"id": template_ids["ohp"], "title": "Overhead Press", "type": "weight_reps",
         "primary_muscle_group": "shoulders", "other_muscle_groups": "[]",
         "equipment": "barbell", "is_custom": 0},
    ])

    # Workouts across 3 weeks
    workout_ids = {}
    base_date = "2026-07-01"
    for week, (wk_start, wk_title) in enumerate([
        ("2026-07-01", "Week 1"),
        ("2026-07-08", "Week 2"),
        ("2026-07-15", "Week 3"),
    ]):
        wo_id = f"wo-{week}"
        workout_ids[f"week{week+1}"] = wo_id
        upsert_workout(db,
            {"id": wo_id, "title": wk_title, "description": "",
             "start_time": f"{wk_start}T10:00:00Z", "end_time": f"{wk_start}T11:00:00Z",
             "routine_id": routine_id},
            [
                {
                    "exercise_template_id": template_ids["bench"],
                    "title": "Bench Press", "notes": "", "sort_order": 0,
                    "sets": [
                        {"set_index": 0, "type": "normal", "weight_kg": 100, "reps": 8, "rpe": 8.0},
                        {"set_index": 1, "type": "normal", "weight_kg": 100, "reps": 8, "rpe": 8.5},
                        {"set_index": 2, "type": "normal", "weight_kg": 100, "reps": 7, "rpe": 9.0},
                    ],
                },
                {
                    "exercise_template_id": template_ids["squat"],
                    "title": "Squat", "notes": "", "sort_order": 1,
                    "sets": [
                        {"set_index": 0, "type": "normal", "weight_kg": 140, "reps": 8, "rpe": 8.0},
                        {"set_index": 1, "type": "normal", "weight_kg": 140, "reps": 8, "rpe": 8.5},
                    ],
                },
            ])

    # Add a workout in a different routine (should be excluded)
    other_routine_id = "routine-pull-day"
    upsert_routine(db, {
        "id": other_routine_id, "title": "Pull Day", "folder_id": None,
        "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
    })
    upsert_workout(db,
        {"id": "wo-other", "title": "Pull Day", "description": "",
         "start_time": "2026-07-10T10:00:00Z", "end_time": "2026-07-10T11:00:00Z",
         "routine_id": other_routine_id},
        [
            {
                "exercise_template_id": template_ids["ohp"],
                "title": "Overhead Press", "notes": "", "sort_order": 0,
                "sets": [
                    {"set_index": 0, "type": "normal", "weight_kg": 60, "reps": 10, "rpe": 7.0},
                ],
            },
        ])

    # Add a soft-deleted workout in the target routine (should be excluded)
    upsert_workout(db,
        {"id": "wo-deleted", "title": "Deleted", "description": "",
         "start_time": "2026-07-12T10:00:00Z", "end_time": "2026-07-12T11:00:00Z",
         "routine_id": routine_id},
        [
            {
                "exercise_template_id": template_ids["bench"],
                "title": "Bench Press", "notes": "", "sort_order": 0,
                "sets": [
                    {"set_index": 0, "type": "normal", "weight_kg": 50, "reps": 5, "rpe": 6.0},
                ],
            },
        ])
    # Soft delete it
    from darth_gain.db.repo import soft_delete_workout
    soft_delete_workout(db, "wo-deleted")

    return {"routine_id": routine_id, "template_ids": template_ids, "workout_ids": workout_ids}


def test_get_routine_export_happy_path(db: sqlite3.Connection) -> None:
    """Export returns structured data for routine with workouts in window."""
    data = setup_test_data(db)
    routine_id = data["routine_id"]

    result = get_routine_export(db, routine_id, "2026-07-01T00:00:00Z", "2026-07-21T23:59:59Z")

    assert result is not None
    assert result["routine"]["id"] == routine_id
    assert result["routine"]["title"] == "Push Day"
    assert len(result["workouts"]) == 3
    assert len(result["exercises"]) == 6  # 2 exercises × 3 workouts
    assert len(result["sets"]) == 15  # (3+2) sets × 3 workouts
    assert "chest" in {t.get("primary_muscle_group") for t in result["templates"].values()}
    assert "quads" in {t.get("primary_muscle_group") for t in result["templates"].values()}


def test_get_routine_export_empty_window(db: sqlite3.Connection) -> None:
    """Export returns empty arrays when routine exists but no workouts in window."""
    data = setup_test_data(db)
    routine_id = data["routine_id"]

    # Window before any workouts
    result = get_routine_export(db, routine_id, "2026-01-01T00:00:00Z", "2026-06-30T23:59:59Z")

    assert result is not None
    assert result["routine"]["id"] == routine_id
    assert result["workouts"] == []
    assert result["exercises"] == []
    assert result["sets"] == []
    assert result["templates"] == {}


def test_get_routine_export_routine_not_found(db: sqlite3.Connection) -> None:
    """Export returns None for non-existent routine."""
    setup_test_data(db)

    result = get_routine_export(db, "non-existent-routine",
                                "2026-07-01T00:00:00Z", "2026-07-21T23:59:59Z")

    assert result is None


def test_get_routine_export_cross_routine_isolation(db: sqlite3.Connection) -> None:
    """Workouts from other routines are not included."""
    data = setup_test_data(db)
    routine_id = data["routine_id"]

    result = get_routine_export(db, routine_id, "2026-07-01T00:00:00Z", "2026-07-21T23:59:59Z")

    # Only 3 workouts from Push Day, not the 1 from Pull Day
    assert len(result["workouts"]) == 3
    workout_ids = {w["id"] for w in result["workouts"]}
    assert "wo-other" not in workout_ids


def test_get_routine_export_excludes_soft_deleted(db: sqlite3.Connection) -> None:
    """Soft-deleted workouts are excluded."""
    data = setup_test_data(db)
    routine_id = data["routine_id"]

    result = get_routine_export(db, routine_id, "2026-07-01T00:00:00Z", "2026-07-21T23:59:59Z")

    workout_ids = {w["id"] for w in result["workouts"]}
    assert "wo-deleted" not in workout_ids


def test_get_routine_export_null_rpe_handled(db: sqlite3.Connection) -> None:
    """Null RPE values in sets are preserved."""
    data = setup_test_data(db)
    routine_id = data["routine_id"]
    template_ids = data["template_ids"]

    # Add workout with null RPE
    upsert_workout(db,
        {"id": "wo-null-rpe", "title": "Null RPE", "description": "",
         "start_time": "2026-07-20T10:00:00Z", "end_time": "2026-07-20T11:00:00Z",
         "routine_id": routine_id},
        [
            {
                "exercise_template_id": template_ids["bench"],
                "title": "Bench Press", "notes": "", "sort_order": 0,
                "sets": [
                    {"set_index": 0, "type": "normal", "weight_kg": 100, "reps": 8, "rpe": None},
                ],
            },
        ])

    result = get_routine_export(db, routine_id, "2026-07-01T00:00:00Z", "2026-07-21T23:59:59Z")

    # Find the null RPE set
    null_rpe_sets = [s for s in result["sets"] if s["rpe"] is None]
    assert len(null_rpe_sets) >= 1


def test_get_routine_export_date_boundaries_inclusive(db: sqlite3.Connection) -> None:
    """Date boundaries are inclusive (start_time >= start AND start_time <= end)."""
    data = setup_test_data(db)
    routine_id = data["routine_id"]

    # Exact boundary on first workout date
    result = get_routine_export(db, routine_id,
                                "2026-07-01T10:00:00Z", "2026-07-01T10:00:00Z")
    assert len(result["workouts"]) == 1
    assert result["workouts"][0]["id"] == "wo-0"

    # Exact boundary on last workout date
    result = get_routine_export(db, routine_id,
                                "2026-07-15T10:00:00Z", "2026-07-15T10:00:00Z")
    assert len(result["workouts"]) == 1
    assert result["workouts"][0]["id"] == "wo-2"


def test_get_routine_export_excludes_workouts_outside_window(db: sqlite3.Connection) -> None:
    """Workouts outside the date window are excluded."""
    data = setup_test_data(db)
    routine_id = data["routine_id"]

    # Window covering only week 2
    result = get_routine_export(db, routine_id,
                                "2026-07-08T00:00:00Z", "2026-07-08T23:59:59Z")

    assert len(result["workouts"]) == 1
    assert result["workouts"][0]["id"] == "wo-1"