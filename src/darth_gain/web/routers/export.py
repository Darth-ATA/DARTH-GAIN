"""JSON API router for routine export.

Provides:
  - GET /api/v1/routines/{routine_id}/export — Export routine data for AI review
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from darth_gain.db.engine import create_engine, create_tables
from darth_gain.db.repo import get_routine_export
from darth_gain.web.deps import require_user
from darth_gain.web.schemas.export import (
    ExportRequest,
    RoutineExportResponse,
    compute_deload_weeks,
    compute_progression_trends,
)

router = APIRouter()


def _get_user_db_path(request: Request, user_id: str) -> str:
    """Get per-user database path."""
    data_dir: str = getattr(request.app.state, "data_dir", "/data/")
    return f"{data_dir}/user_{user_id}/workouts.db"


def _compute_etag(routine_id: str, weeks: int, max_updated_at: str | None) -> str:
    """Compute ETag for cache validation."""
    content = f"{routine_id}:{weeks}:{max_updated_at or ''}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _parse_tz(tz: str) -> timezone:
    """Parse timezone string to timezone object. Falls back to UTC."""
    try:
        import zoneinfo
        return zoneinfo.ZoneInfo(tz)
    except Exception:
        return timezone.utc


def _calculate_window(weeks: int, tz: timezone) -> tuple[str, str]:
    """Calculate start/end dates for export window in UTC."""
    now = datetime.now(tz)
    end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    start = (now - timedelta(weeks=weeks)).replace(hour=0, minute=0, second=0, microsecond=0)
    # Convert to UTC for DB query
    start_utc = start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_utc = end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return start_utc, end_utc


def _build_response(
    export_data: dict[str, Any],
    weeks: int,
    tz: str,
    start_utc: str,
    end_utc: str,
) -> RoutineExportResponse:
    """Build Pydantic response from raw export data."""
    routine = export_data["routine"]
    workouts_raw = export_data["workouts"]
    exercises_raw = export_data["exercises"]
    sets_raw = export_data["sets"]
    templates = export_data["templates"]

    # Build lookup maps
    exercises_by_workout: dict[str, list[dict]] = {}
    for ex in exercises_raw:
        exercises_by_workout.setdefault(ex["workout_id"], []).append(ex)

    sets_by_exercise: dict[int, list[dict]] = {}
    for s in sets_raw:
        sets_by_exercise.setdefault(s["exercise_id"], []).append(s)

    # Build workouts with exercises and sets
    workouts: list[dict] = []
    for wo in workouts_raw:
        wo_exercises = []
        for ex in exercises_by_workout.get(wo["id"], []):
            ex_sets = []
            for s in sets_by_exercise.get(ex["id"], []):
                ex_sets.append({
                    "set_index": s["set_index"],
                    "type": s["type"],
                    "weight_kg": s["weight_kg"],
                    "reps": s["reps"],
                    "distance_meters": s["distance_meters"],
                    "duration_seconds": s["duration_seconds"],
                    "rpe": s["rpe"],
                })
            tmpl = templates.get(ex["exercise_template_id"], {})
            wo_exercises.append({
                "template_id": ex["exercise_template_id"],
                "title": ex["title"],
                "muscle_group": tmpl.get("primary_muscle_group", "unknown"),
                "sets": ex_sets,
            })
        workouts.append({
            "workout_id": wo["id"],
            "date": datetime.fromisoformat(wo["start_time"].replace("Z", "+00:00")),
            "exercises": wo_exercises,
        })

    # Build templates dict for helpers
    templates_for_helpers = {
        tid: {"primary_muscle_group": t.get("primary_muscle_group", "unknown")}
        for tid, t in templates.items()
    }

    # Compute summary analytics
    deload_weeks = compute_deload_weeks(workouts, templates_for_helpers)
    progression_trends = compute_progression_trends(workouts)

    # Volume by muscle group
    volume_by_muscle: dict[str, float] = {}
    exercise_stats: dict[str, dict] = {}
    total_sets = 0
    total_volume = 0.0

    for wo in workouts:
        for ex in wo["exercises"]:
            muscle = ex["muscle_group"]
            tid = ex["template_id"]
            title = ex["title"]
            if tid not in exercise_stats:
                exercise_stats[tid] = {
                    "title": title,
                    "muscle_group": muscle,
                    "sets": [],
                    "weights": [],
                    "rpes": [],
                }
            for s in ex["sets"]:
                if s["type"] == "normal":
                    exercise_stats[tid]["sets"].append(s)
                    if s["weight_kg"] is not None and s["reps"] is not None:
                        vol = s["weight_kg"] * s["reps"]
                        volume_by_muscle[muscle] = volume_by_muscle.get(muscle, 0.0) + vol
                        total_volume += vol
                        exercise_stats[tid]["weights"].append(s["weight_kg"])
                    if s["rpe"] is not None:
                        exercise_stats[tid]["rpes"].append(s["rpe"])
                    total_sets += 1

    # Build exercise summaries
    exercise_summaries = []
    for tid, stats in exercise_stats.items():
        weights = stats["weights"]
        rpes = stats["rpes"]
        progression = progression_trends.get(tid, {})
        exercise_summaries.append({
            "template_id": tid,
            "title": stats["title"],
            "muscle_group": stats["muscle_group"],
            "total_sets": len(stats["sets"]),
            "total_volume_kg": sum(w * s["reps"] for s in stats["sets"]
                                   if s["weight_kg"] is not None and s["reps"] is not None
                                   for w in [s["weight_kg"]]),
            "avg_weight_kg": sum(weights) / len(weights) if weights else 0.0,
            "max_weight_kg": max(weights) if weights else 0.0,
            "progression_slope_kg_per_week": progression.get("slope"),
            "r2": progression.get("r2"),
            "avg_rpe": sum(rpes) / len(rpes) if rpes else None,
            "max_rpe": max(rpes) if rpes else None,
            "sets_with_rpe": len(rpes),
        })

    total_workouts = len(workouts)
    frequency = total_workouts / weeks if weeks > 0 else 0.0

    return RoutineExportResponse(
        meta={
            "routine_id": routine["id"],
            "routine_title": routine["title"],
            "routine_created_at": datetime.fromisoformat(routine["created_at"].replace("Z", "+00:00")),
        },
        window={
            "start": datetime.fromisoformat(start_utc.replace("Z", "+00:00")),
            "end": datetime.fromisoformat(end_utc.replace("Z", "+00:00")),
            "weeks_analyzed": weeks,
            "timezone": tz,
        },
        workouts=workouts,
        summary={
            "total_workouts": total_workouts,
            "frequency_per_week": round(frequency, 2),
            "volume_by_muscle_group": volume_by_muscle,
            "progression_trends": progression_trends,
            "deload_weeks_detected": deload_weeks,
            "exercise_summaries": exercise_summaries,
        },
    )


@router.get(
    "/routines/{routine_id}/export",
    response_model=RoutineExportResponse,
    summary="Export routine workout data for AI review",
    description="Returns last N weeks of workout data for a routine in JSON format suitable for AI analysis.",
)
async def export_routine(
    routine_id: str,
    request: Request,
    response: Response,
    weeks: int = Query(default=8, ge=4, le=24, description="Weeks of history to export"),
    tz: str = Query(default="UTC", pattern=r"^[A-Za-z_+/.-]+$", description="IANA timezone"),
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
    current_user: dict = Depends(require_user),
) -> RoutineExportResponse:
    """Export routine data for AI performance review.

    - **routine_id**: The routine UUID to export
    - **weeks**: Number of weeks (4-24, default 8)
    - **tz**: IANA timezone for window calculation (default UTC)
    - **If-None-Match**: ETag for conditional requests (304 Not Modified)
    """
    user_id = current_user["user_id"]
    db_path = _get_user_db_path(request, user_id)

    # Verify database exists
    import os
    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="User database not found")

    # Calculate window
    tz_obj = _parse_tz(tz)
    start_utc, end_utc = _calculate_window(weeks, tz_obj)

    # Open DB and fetch data
    conn = create_engine(db_path)
    try:
        create_tables(conn)
        export_data = get_routine_export(conn, routine_id, start_utc, end_utc)
    finally:
        conn.close()

    if export_data is None:
        raise HTTPException(status_code=404, detail="Routine not found")

    if not export_data["workouts"]:
        raise HTTPException(
            status_code=404,
            detail=f"No workouts found for this routine in the last {weeks} weeks",
        )

    # Compute ETag for caching
    max_updated = max(
        (w.get("updated_at") or w["start_time"] for w in export_data["workouts"]),
        default=None,
    )
    etag = _compute_etag(routine_id, weeks, max_updated)

    # Check conditional request
    if if_none_match and if_none_match == etag:
        return Response(status_code=304)

    # Build response
    result = _build_response(export_data, weeks, tz, start_utc, end_utc)

    # Set headers
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=300"

    # Content-Disposition for download
    safe_title = "".join(c if c.isalnum() else "-" for c in export_data["routine"]["title"].lower())
    start_date = start_utc[:10]
    end_date = end_utc[:10]
    filename = f"routine-{safe_title}-{start_date}-to-{end_date}.json"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'

    return result