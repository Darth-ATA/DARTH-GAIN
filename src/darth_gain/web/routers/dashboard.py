"""Dashboard route for the web dashboard.

Provides:
  - ``GET /`` — exercise list with progression status, grouped by status
"""

from __future__ import annotations

import os
import sqlite3
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, Request

from darth_gain.db.engine import create_engine, create_tables
from darth_gain.progression import ProgressionEngine
from darth_gain.web.deps import require_user

from ..templates import render_template

router = APIRouter()

# Ordered status groups for display (others follow in arbitrary order)
STATUS_ORDER = [
    "progress",
    "maintain",
    "skipped",
    "insufficient_data",
]


def _build_exercise_card(
    template: dict[str, Any],
    status_obj: Any,
    status_str: str | None,
) -> dict[str, Any]:
    """Build a flat dict for template rendering from a template row and check result."""
    return {
        "template_id": template["id"],
        "title": template["title"],
        "muscle_group": template.get("primary_muscle_group", ""),
        "exercise_type": template.get("type", ""),
        "current_weight": status_obj.current_weight_kg,
        "rep_min": status_obj.rep_range[0],
        "rep_max": status_obj.rep_range[1],
        "increment": status_obj.increment,
        "recommended_weight": None,
        "recommendation": status_obj.recommendation,
        "status": status_str or "unknown",
        "error": status_obj.error,
    }


def _error_card(template: dict[str, Any], exc: Exception) -> dict[str, Any]:
    """Build an error card when progression check fails for a template."""
    return {
        "template_id": template["id"],
        "title": template["title"],
        "muscle_group": template.get("primary_muscle_group", ""),
        "status": "error",
        "current_weight": None,
        "rep_min": 8,
        "rep_max": 12,
        "recommended_weight": None,
        "recommendation": str(exc),
        "error": str(exc),
    }


@router.get("/")
async def dashboard(
    request: Request,
    current_user: dict = Depends(require_user),
) -> Any:
    """Render the dashboard with exercise list grouped by progression status.

    For each exercise template:
      1. Calls ``ProgressionEngine.check()`` to compute status
      2. Queries the latest progression_history entry for the canonical status
      3. Groups results into sections (progress, maintain, skipped, etc.)

    Isolates per-template failures so one bad template doesn't crash the page.
    """
    user_id = current_user["user_id"]
    data_dir: str = getattr(request.app.state, "data_dir", "/data/")
    db_path = os.path.join(data_dir, f"user_{user_id}", "workouts.db")

    # --- Handle missing per-user DB -------------------------------------------------
    if not os.path.exists(db_path):
        return render_template(
            "dashboard.html",
            {
                "request": request,
                "groups": {},
                "empty": True,
                "error": None,
            },
        )

    # --- Open connection ------------------------------------------------------------
    conn: sqlite3.Connection | None = None
    try:
        conn = create_engine(db_path)
        # Ensure tables exist in case this is a fresh per-user DB
        create_tables(conn)

        # --- Query templates (convert Row → dict for .get() support) ----------------
        raw_templates = conn.execute(
            "SELECT id, title, type, primary_muscle_group "
            "FROM exercise_templates "
            "ORDER BY title"
        ).fetchall()
        templates = [dict(row) for row in raw_templates]

        if not templates:
            return render_template(
                "dashboard.html",
                {
                    "request": request,
                    "groups": {},
                    "empty": True,
                    "error": None,
                },
            )

        # --- Run progression checks -------------------------------------------------
        engine = ProgressionEngine(conn)
        results: list[dict[str, Any]] = []

        for template in templates:
            tid = template["id"]
            try:
                # Run progression check (also persists to progression_history)
                status = engine.check(tid)
                # Get canonical status from the latest history entry
                latest = conn.execute(
                    "SELECT status FROM progression_history "
                    "WHERE exercise_template_id = ? "
                    "ORDER BY id DESC LIMIT 1",
                    (tid,),
                ).fetchone()
                status_str = latest["status"] if latest else "unknown"

                results.append(_build_exercise_card(template, status, status_str))

            except Exception as exc:
                # Isolate failures — one bad template should not crash the page
                results.append(_error_card(template, exc))

        # --- Group by status --------------------------------------------------------
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in results:
            groups[r["status"]].append(r)

        # Build ordered groups (known statuses first, then any extras)
        ordered_groups: dict[str, list[dict[str, Any]]] = {}
        for s in STATUS_ORDER:
            if s in groups:
                ordered_groups[s] = groups[s]
        # Add any remaining groups not in STATUS_ORDER (e.g. "error", "unknown")
        for s in sorted(groups.keys()):
            if s not in ordered_groups:
                ordered_groups[s] = groups[s]

        return render_template(
            "dashboard.html",
            {
                "request": request,
                "groups": ordered_groups,
                "empty": False,
                "error": None,
            },
        )

    except Exception as exc:
        # Catch-all: if DB itself is corrupt or unreadable
        return render_template(
            "dashboard.html",
            {
                "request": request,
                "groups": {},
                "empty": True,
                "error": str(exc),
            },
        )

    finally:
        if conn is not None:
            conn.close()
