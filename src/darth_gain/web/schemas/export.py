"""Pydantic schemas for routine export API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class ExportRequest(BaseModel):
    """Query parameters for routine export endpoint."""

    weeks: int = Field(default=8, ge=4, le=24, description="Number of weeks to export")
    tz: str = Field(
        default="UTC",
        pattern=r"^[A-Za-z_+/.-]+$",
        description="IANA timezone for window calculation",
    )


# ---------------------------------------------------------------------------
# Response — Core Data
# ---------------------------------------------------------------------------


class SetExport(BaseModel):
    """Single set within an exercise."""

    set_index: int
    type: Literal["normal", "warmup", "drop", "failure"]
    weight_kg: float | None = None
    reps: int | None = None
    distance_meters: float | None = None
    duration_seconds: int | None = None
    rpe: float | None = None


class ExerciseExport(BaseModel):
    """Exercise with its sets."""

    template_id: str
    title: str
    muscle_group: str
    sets: list[SetExport]


class WorkoutExport(BaseModel):
    """Single workout with exercises."""

    workout_id: str
    date: datetime
    exercises: list[ExerciseExport]


# ---------------------------------------------------------------------------
# Response — Summary Analytics
# ---------------------------------------------------------------------------


class ExerciseSummary(BaseModel):
    """Aggregated stats for one exercise across the export window."""

    template_id: str
    title: str
    muscle_group: str
    total_sets: int
    total_volume_kg: float
    avg_weight_kg: float
    max_weight_kg: float
    progression_slope_kg_per_week: float | None = None
    r2: float | None = None
    avg_rpe: float | None = None
    max_rpe: float | None = None
    sets_with_rpe: int


class ExportSummary(BaseModel):
    """Computed summary analytics for the export window."""

    total_workouts: int
    frequency_per_week: float
    volume_by_muscle_group: dict[str, float]
    progression_trends: dict[str, dict[str, float]]  # exercise -> {slope, r2}
    deload_weeks_detected: list[str]  # ISO week start dates (YYYY-Www)
    exercise_summaries: list[ExerciseSummary]


# ---------------------------------------------------------------------------
# Response — Meta
# ---------------------------------------------------------------------------


class RoutineMeta(BaseModel):
    """Routine identifying information."""

    routine_id: str
    routine_title: str
    routine_created_at: datetime


class ExportWindow(BaseModel):
    """Window metadata."""

    start: datetime
    end: datetime
    weeks_analyzed: int
    timezone: str


class RoutineExportResponse(BaseModel):
    """Complete routine export response."""

    meta: RoutineMeta
    window: ExportWindow
    workouts: list[WorkoutExport]
    summary: ExportSummary


# ---------------------------------------------------------------------------
# Helpers for computing summary (used by router, not exposed in API)
# ---------------------------------------------------------------------------


def compute_deload_weeks(
    workouts: list[dict[str, Any] | Any],
    templates: dict[str, dict[str, Any]],
) -> list[str]:
    """Detect deload weeks: volume drop >= 20% WoW for >= 2 major muscle groups.

    Returns list of ISO week start dates (YYYY-Www) where deload detected.
    Accepts both dict and Pydantic model instances.
    """
    from collections import defaultdict
    from datetime import datetime

    def get_attr(obj, key, default=None):
        """Get attribute from dict or Pydantic model."""
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    # Volume per muscle_group per ISO week
    vol_by_week: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for wo in workouts:
        # ISO week: year-week
        dt = get_attr(wo, "date")
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        week_key = dt.strftime("%G-W%V")
        exercises = get_attr(wo, "exercises", [])
        for ex in exercises:
            muscle = get_attr(ex, "muscle_group", "unknown")
            sets = get_attr(ex, "sets", [])
            for s in sets:
                s_type = get_attr(s, "type")
                weight = get_attr(s, "weight_kg")
                reps = get_attr(s, "reps")
                if s_type == "normal" and weight is not None and reps is not None:
                    vol_by_week[week_key][muscle] += weight * reps

    if len(vol_by_week) < 2:
        return []

    sorted_weeks = sorted(vol_by_week.keys())
    deload_weeks: list[str] = []

    for i in range(1, len(sorted_weeks)):
        prev = vol_by_week[sorted_weeks[i - 1]]
        curr = vol_by_week[sorted_weeks[i]]

        major_drops = 0
        for muscle, prev_vol in prev.items():
            if prev_vol == 0:
                continue
            curr_vol = curr.get(muscle, 0)
            if curr_vol < 0.8 * prev_vol:
                major_drops += 1

        if major_drops >= 2:
            deload_weeks.append(sorted_weeks[i])

    return deload_weeks


def compute_progression_trends(
    workouts: list[dict[str, Any] | Any],
) -> dict[str, dict[str, float]]:
    """Linear regression slope (kg/week) per exercise with >= 4 data points.

    Returns dict: template_id -> {slope, r2}
    Accepts both dict and Pydantic model instances.
    """
    from collections import defaultdict
    import statistics
    from datetime import datetime

    def get_attr(obj, key, default=None):
        """Get attribute from dict or Pydantic model."""
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    # Collect avg weight per exercise per week
    points_by_ex: dict[str, list[tuple[float, float]]] = defaultdict(list)

    for wo in workouts:
        dt = get_attr(wo, "date")
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        week_num = float(dt.strftime("%V"))  # week of year
        exercises = get_attr(wo, "exercises", [])
        for ex in exercises:
            template_id = get_attr(ex, "template_id")
            sets = get_attr(ex, "sets", [])
            normal_weights = [
                get_attr(s, "weight_kg") for s in sets
                if get_attr(s, "type") == "normal" and get_attr(s, "weight_kg") is not None
            ]
            if normal_weights:
                points_by_ex[template_id].append((week_num, statistics.mean(normal_weights)))

    trends: dict[str, dict[str, float]] = {}
    for tid, points in points_by_ex.items():
        if len(points) < 4:
            continue
        x_vals = [p[0] for p in points]
        y_vals = [p[1] for p in points]
        # Simple linear regression
        n = len(points)
        x_mean = statistics.mean(x_vals)
        y_mean = statistics.mean(y_vals)
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in points)
        denominator = sum((x - x_mean) ** 2 for x in x_vals)
        if denominator == 0:
            continue
        slope = numerator / denominator
        # R^2
        y_pred = [slope * (x - x_mean) + y_mean for x in x_vals]
        ss_res = sum((y - yp) ** 2 for y, yp in zip(y_vals, y_pred))
        ss_tot = sum((y - y_mean) ** 2 for y in y_vals)
        r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        trends[tid] = {"slope": slope, "r2": r2}

    return trends