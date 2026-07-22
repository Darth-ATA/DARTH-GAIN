"""Routine view route for the web dashboard.

Provides:
  - ``GET /routines`` — exercises grouped by Hevy routine with progression status
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Request

from darth_gain.db.engine import create_engine, create_tables
from darth_gain.db.repo import get_routines
from darth_gain.progression import ProgressionEngine
from darth_gain.web.deps import require_user

from ..templates import render_template
from .dashboard import _build_exercise_card, _error_card

router = APIRouter()


@router.get("/routines")
async def routines_view(
    request: Request,
    current_user: dict = Depends(require_user),
) -> Any:
    """Render the routines page with exercises grouped by routine.

    For each routine:
      1. Queries all unique exercise template IDs via workouts.routine_id join
      2. Calls ``ProgressionEngine.check()`` for each template
      3. Groups results into routine sections

    Exercises with ``routine_id IS NULL`` are placed in an "Uncategorized" section.
    """
    user_id = current_user["user_id"]
    data_dir: str = getattr(request.app.state, "data_dir", "/data/")
    db_path = os.path.join(data_dir, f"user_{user_id}", "workouts.db")

    # --- Handle missing per-user DB -------------------------------------------------
    if not os.path.exists(db_path):
        return render_template(
            "routines.html",
            {
                "request": request,
                "routine_groups": [],
                "uncategorized": None,
                "empty": True,
                "error": None,
            },
        )

    # --- Open connection ------------------------------------------------------------
    conn: sqlite3.Connection | None = None
    try:
        conn = create_engine(db_path)
        create_tables(conn)

        # --- Build template lookup --------------------------------------------------
        raw_templates = conn.execute(
            "SELECT id, title, type, primary_muscle_group "
            "FROM exercise_templates"
        ).fetchall()
        templates = {row["id"]: dict(row) for row in raw_templates}

        if not templates:
            return render_template(
                "routines.html",
                {
                    "request": request,
                    "routine_groups": [],
                    "uncategorized": None,
                    "empty": True,
                    "error": None,
                },
            )

        # --- Get all routines -------------------------------------------------------
        routines = get_routines(conn)

        # --- Process routines -------------------------------------------------------
        engine = ProgressionEngine(conn)
        routine_groups: list[dict[str, Any]] = []
        seen_template_ids: set[str] = set()

        for routine in routines:
            tids = [
                row["exercise_template_id"]
                for row in conn.execute(
                    "SELECT DISTINCT e.exercise_template_id "
                    "FROM exercises e "
                    "JOIN workouts w ON w.id = e.workout_id "
                    "WHERE w.routine_id = ?",
                    (routine["id"],),
                ).fetchall()
            ]
            if not tids:
                continue

            cards: list[dict[str, Any]] = []
            for tid in tids:
                if tid not in templates:
                    continue
                seen_template_ids.add(tid)
                template = templates[tid]
                try:
                    status = engine.check(tid)
                    latest = conn.execute(
                        "SELECT status FROM progression_history "
                        "WHERE exercise_template_id = ? "
                        "ORDER BY id DESC LIMIT 1",
                        (tid,),
                    ).fetchone()
                    status_str = latest["status"] if latest else "unknown"
                    cards.append(_build_exercise_card(template, status, status_str))
                except Exception as exc:
                    cards.append(_error_card(template, exc))

            if cards:
                routine_groups.append({
                    "routine_id": routine["id"],
                    "routine_title": routine["title"],
                    "exercise_count": len(cards),
                    "exercises": cards,
                })

        # --- Uncategorized (null routine_id) ----------------------------------------
        uncategorized: dict[str, Any] | None = None
        null_tids = [
            row["exercise_template_id"]
            for row in conn.execute(
                "SELECT DISTINCT e.exercise_template_id "
                "FROM exercises e "
                "JOIN workouts w ON w.id = e.workout_id "
                "WHERE w.routine_id IS NULL"
            ).fetchall()
        ]
        # Exclude template_ids already shown in a routine group
        new_tids = [t for t in null_tids if t not in seen_template_ids]
        if new_tids:
            uc_cards: list[dict[str, Any]] = []
            for tid in new_tids:
                if tid not in templates:
                    continue
                template = templates[tid]
                try:
                    status = engine.check(tid)
                    latest = conn.execute(
                        "SELECT status FROM progression_history "
                        "WHERE exercise_template_id = ? "
                        "ORDER BY id DESC LIMIT 1",
                        (tid,),
                    ).fetchone()
                    status_str = latest["status"] if latest else "unknown"
                    uc_cards.append(_build_exercise_card(template, status, status_str))
                except Exception as exc:
                    uc_cards.append(_error_card(template, exc))

            if uc_cards:
                uncategorized = {
                    "exercise_count": len(uc_cards),
                    "exercises": uc_cards,
                }

        is_empty = not routine_groups and uncategorized is None

        return render_template(
            "routines.html",
            {
                "request": request,
                "routine_groups": routine_groups,
                "uncategorized": uncategorized,
                "empty": is_empty,
                "error": None,
            },
        )

    except Exception as exc:
        return render_template(
            "routines.html",
            {
                "request": request,
                "routine_groups": [],
                "uncategorized": None,
                "empty": True,
                "error": str(exc),
            },
        )

    finally:
        if conn is not None:
            conn.close()
