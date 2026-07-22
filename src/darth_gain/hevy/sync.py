"""Sync orchestrator — paginate events, persist workouts, track progress.

The main entry point is :func:`sync`, which drives the full delta-sync
loop: fetch changes from the Hevy API via the :class:`HevyClient`
adapter and persist them through :mod:`darth_gain.db.repo`.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from darth_gain.config import Config
from darth_gain.db.repo import (
    get_routines,
    get_sync_meta,
    get_template_count,
    set_sync_meta,
    soft_delete_workout,
    upsert_routines,
    upsert_templates,
    upsert_workout,
)
from darth_gain.hevy.client import HevyClient

logger = logging.getLogger(__name__)

EPOCH = "1970-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class SyncResult:
    """Holds the outcome of a sync run.

    Attributes:
        updated: Number of workouts upserted.
        deleted: Number of workouts soft-deleted.
        errors: Number of events that failed to process.
        dry_run: Whether this was a dry-run (no persistence of metadata).
    """

    updated: int = 0
    deleted: int = 0
    errors: int = 0
    dry_run: bool = False


# ---------------------------------------------------------------------------
# Main sync entry point
# ---------------------------------------------------------------------------


def sync(
    api: HevyClient,
    conn: Any,
    config: Config,
    progress: Any = None,
    progress_task_id: int | None = None,
) -> SyncResult:
    """Execute a full delta-sync from Hevy to the local SQLite database.

    Args:
        api: Configured :class:`HevyClient` adapter.
        conn: Open SQLite connection (use ``:memory:`` for dry-run).
        config: Application configuration (resolves ``since``,
            ``dry_run``, ``refresh_templates``).
        progress: Optional Rich ``Progress`` instance for page-level
            progress tracking.  When provided, ``advance(progress_task_id)``
            is called after each page is processed.  Ignored for single-page
            syncs.
        progress_task_id: Optional Rich ``Progress`` task ID for the
            progress bar.  Required when ``progress`` is given.

    Returns:
        A :class:`SyncResult` with aggregated counts.

    The sync flow:

    1. Resolve ``since`` — from ``config.since``, stored metadata, or epoch.
    2. Fetch and cache exercise templates if the cache is empty or
       ``refresh_templates`` is set.
    3. Fetch and persist all routines via ``api.get_routines()``.
    4. Paginate events via ``api.get_events()``.
    5. For each ``updated`` event: upsert the workout (with error isolation).
    6. For each ``deleted`` event: soft-delete the workout.
    7. On success (and not dry-run): persist ``last_sync_at``.
    """
    result = SyncResult(dry_run=config.dry_run)

    # 1. Resolve since timestamp
    since = _resolve_since(conn, config)

    # 2. Fetch / refresh exercise templates
    _ensure_templates(api, conn, config.refresh_templates)

    # 3. Fetch / persist routines
    _ensure_routines(api, conn)

    # 5. Paginate events
    page = 1
    page_count = 1

    while page <= page_count:
        events_page = api.get_events(since=since, page=page)

        # On first call, capture page_count for the loop
        if page_count == 1 and page == 1:
            page_count = events_page.page_count

        # 6-7. Process each event with error isolation
        for event in events_page.events:
            try:
                if event.type == "updated" and event.workout:
                    _process_updated(conn, event.workout)
                    result.updated += 1
                elif event.type == "deleted":
                    _process_deleted(conn, event.workout)
                    result.deleted += 1
            except Exception:
                logger.exception(
                    "Failed to process event index %d (type=%s)",
                    event.index,
                    event.type,
                )
                result.errors += 1

        # Progress tracking
        if progress is not None and progress_task_id is not None and page_count > 1:
            progress.advance(progress_task_id)

        # Advance to next page
        page += 1

        # Inter-page delay (skip after the last page)
        if page <= page_count:
            time.sleep(0.5)

    # 8. Persist last_sync_at on success
    if not config.dry_run and result.errors == 0:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        set_sync_meta(conn, "last_sync_at", now)

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_since(conn: Any, config: Config) -> str:
    """Determine the ``since`` timestamp for the events API call.

    Priority:
    1. Explicit ``config.since`` (CLI override).
    2. Stored ``last_sync_at`` from sync metadata.
    3. Unix epoch (first-ever sync).
    """
    if config.since is not None:
        return config.since

    stored = get_sync_meta(conn, "last_sync_at")
    if stored is not None:
        return stored

    return EPOCH


def _ensure_templates(
    api: HevyClient,
    conn: Any,
    refresh: bool = False,
) -> None:
    """Fetch and cache exercise templates if needed.

    Templates are fetched when:
    * The template table is empty (first sync), OR
    * ``refresh`` is ``True`` (``--refresh-templates`` flag).
    """
    count = get_template_count(conn)

    if count == 0 or refresh:
        templates = api.get_exercise_templates()
        if templates:
            upsert_templates(conn, templates)


def _process_updated(conn: Any, workout: dict[str, Any]) -> None:
    """Upsert an updated workout from its event dict.

    Separates the workout header from the exercises list before calling
    ``upsert_workout``.
    """
    exercises = workout.pop("exercises", [])
    upsert_workout(conn, workout, exercises)


def _ensure_routines(api: HevyClient, conn: Any) -> None:
    """Fetch all routines from the Hevy API and persist them.

    Routines are fetched on every sync run because they are small
    and rarely change. Caching in the DB avoids redundant API calls
    in the web view.
    """
    routines = api.get_routines()
    if routines:
        upsert_routines(conn, routines)


def _process_deleted(conn: Any, workout: dict[str, Any] | None) -> None:
    """Soft-delete a workout.

    Extracts the ``id`` from the workout dict if present.  If the dict
    is ``None`` or has no ``id``, the event is logged and skipped.
    """
    if workout is None:
        logger.warning("Deleted event has no workout data — cannot soft-delete.")
        return

    workout_id = workout.get("id")
    if workout_id is None:
        logger.warning("Deleted event workout has no 'id' field.")
        return

    soft_delete_workout(conn, workout_id)
