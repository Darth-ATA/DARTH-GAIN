"""Exercise detail and config editor routes for the web dashboard.

Provides:
  - ``GET /exercises/{template_id}`` — detail page with history and config
  - ``PUT /exercises/{template_id}/config`` — update progression config
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request

from darth_gain.progression import ProgressionEngine
from darth_gain.progression.models import ProgressionConfig
from darth_gain.progression.repo import get_config, get_history, get_template, set_config
from darth_gain.web.deps import get_db, require_user

from ..templates import render_template

router = APIRouter()


@router.get("/exercises/{template_id}")
async def exercise_detail(
    request: Request,
    template_id: str,
    db: sqlite3.Connection = Depends(get_db),
    current_user: dict = Depends(require_user),
) -> Any:
    """Render the exercise detail page with history and config editor.

    Args:
        request: The incoming HTTP request.
        template_id: The exercise template ID.
        db: Open per-user SQLite connection.
        current_user: The authenticated user dict.

    Returns:
        HTML page with exercise info, current status, history table, and config form.
    """
    # 1. Validate template exists
    template = get_template(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Exercise not found")

    # 2. Run progression check for current status
    engine = ProgressionEngine(db)
    status = engine.check(template_id)

    # 3. Load config (or defaults)
    config = get_config(db, template_id)

    # 4. Load history — newest first
    history = get_history(db, template_id)
    history.reverse()  # repo returns oldest-first, reverse for newest-first

    # 5. Read canonical status from the latest history entry
    #    (engine.check() just persisted it with the correct status string)
    latest = db.execute(
        "SELECT status FROM progression_history "
        "WHERE exercise_template_id = ? "
        "ORDER BY id DESC LIMIT 1",
        (template_id,),
    ).fetchone()
    status_str = latest["status"] if latest else "unknown"

    # 6. Parse details JSON for display
    history_rows = []
    for entry in history:
        details_dict = None
        if entry.details:
            try:
                details_dict = json.loads(entry.details)
            except (json.JSONDecodeError, TypeError):
                details_dict = None
        history_rows.append({
            "checked_at": entry.checked_at,
            "status": entry.status,
            "current_weight_kg": entry.current_weight_kg,
            "recommended_weight_kg": entry.recommended_weight_kg,
            "details": details_dict,
        })

    return render_template(
        "exercise_detail.html",
        {
            "request": request,
            "template": template,
            "status": status,
            "status_str": status_str,
            "config": config,
            "history": history_rows,
        },
    )


@router.put("/exercises/{template_id}/config")
async def update_config(
    request: Request,
    template_id: str,
    db: sqlite3.Connection = Depends(get_db),
    current_user: dict = Depends(require_user),
    rep_min: int | None = Form(None),
    rep_max: int | None = Form(None),
    weight_increment: float | None = Form(None),
    enabled: bool | None = Form(None),
) -> Any:
    """Update progression config for an exercise template.

    Accepts partial updates — missing fields are taken from the current config.
    On success, returns the config form HTML snippet for HTMX in-place swap.

    Args:
        request: The incoming HTTP request.
        template_id: The exercise template ID.
        db: Open per-user SQLite connection.
        current_user: The authenticated user dict.
        rep_min: Minimum reps (optional — partial update).
        rep_max: Maximum reps (optional — partial update).
        weight_increment: Weight increment in kg (optional — partial update).
        enabled: Whether progression checking is enabled (optional — partial update).

    Returns:
        HTML snippet with the updated config form.

    Raises:
        HTTPException 404: Template not found.
        HTTPException 422: Validation error (rep_min > rep_max, increment <= 0).
    """
    # 1. Validate template exists
    template = get_template(db, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Exercise not found")

    # 2. Load current config for partial update support
    current = get_config(db, template_id)

    # 3. Apply partial updates — use current values as defaults
    new_rep_min = rep_min if rep_min is not None else current.rep_min
    new_rep_max = rep_max if rep_max is not None else current.rep_max
    new_increment = weight_increment if weight_increment is not None else current.weight_increment
    new_enabled = enabled if enabled is not None else current.enabled

    # 4. Validate
    if new_rep_min > new_rep_max:
        raise HTTPException(
            status_code=422,
            detail="rep_min must be less than or equal to rep_max",
        )
    if new_increment <= 0:
        raise HTTPException(
            status_code=422,
            detail="weight_increment must be greater than 0",
        )

    # 5. Persist
    config = ProgressionConfig(
        exercise_template_id=template_id,
        rep_min=new_rep_min,
        rep_max=new_rep_max,
        weight_increment=new_increment,
        enabled=new_enabled,
    )
    set_config(db, config)

    # Return config form snippet for HTMX in-place swap
    return render_template(
        "partials/config_form.html",
        {
            "config": config,
            "request": request,
        },
    )
