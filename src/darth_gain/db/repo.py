"""Repository functions for DARTH-GAIN SQLite database.

Provides atomic CRUD operations for workouts, exercise templates,
and sync metadata.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Workouts
# ---------------------------------------------------------------------------


def upsert_workout(
    conn: sqlite3.Connection,
    workout: Mapping[str, Any],
    exercises: Sequence[Mapping[str, Any]],
) -> None:
    """Atomically upsert a workout with its exercises and sets.

    Uses replace-on-update: existing exercises and sets for this workout
    are deleted and re-inserted within a single transaction.

    Args:
        conn: Open SQLite connection.
        workout: Dict with keys ``id``, ``title``, ``description``,
            ``start_time``, ``end_time`` (optional).
        exercises: Sequence of exercise dicts. Each may contain a ``sets``
            key with a sequence of set dicts.
    """
    workout_id = workout["id"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with conn:
        # Remove old exercises and sets for this workout
        conn.execute(
            "DELETE FROM sets WHERE exercise_id IN ("
            "  SELECT id FROM exercises WHERE workout_id = ?"
            ")",
            (workout_id,),
        )
        conn.execute("DELETE FROM exercises WHERE workout_id = ?", (workout_id,))

        # Upsert the workout row (preserve original created_at)
        conn.execute(
            """INSERT INTO workouts (id, title, description, start_time, end_time,
                                     updated_at, routine_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   title       = excluded.title,
                   description = excluded.description,
                   start_time   = excluded.start_time,
                   end_time     = excluded.end_time,
                   updated_at   = excluded.updated_at,
                   routine_id   = excluded.routine_id""",
            (
                workout_id,
                workout.get("title", ""),
                workout.get("description", ""),
                workout.get("start_time", ""),
                workout.get("end_time"),
                now,
                workout.get("routine_id"),
            ),
        )

        # Insert exercises
        for ex in exercises:
            cursor = conn.execute(
                """INSERT INTO exercises (workout_id, exercise_template_id, title, notes, sort_order)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    workout_id,
                    ex.get("exercise_template_id"),
                    ex.get("title", ""),
                    ex.get("notes", ""),
                    ex.get("sort_order", 0),
                ),
            )
            exercise_id = cursor.lastrowid

            # Insert sets for this exercise
            for s in ex.get("sets", []):
                conn.execute(
                    """INSERT INTO sets
                       (exercise_id, set_index, type, weight_kg, reps,
                        distance_meters, duration_seconds, rpe)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        exercise_id,
                        s.get("set_index", 0),
                        s.get("type", "normal"),
                        s.get("weight_kg"),
                        s.get("reps"),
                        s.get("distance_meters"),
                        s.get("duration_seconds"),
                        s.get("rpe"),
                    ),
                )


def soft_delete_workout(conn: sqlite3.Connection, workout_id: str) -> None:
    """Mark a workout as deleted (soft delete).

    Sets ``is_deleted = 1`` on the workout row. Does nothing if the
    workout ID does not exist.

    Args:
        conn: Open SQLite connection.
        workout_id: The Hevy workout UUID to mark as deleted.
    """
    conn.execute(
        "UPDATE workouts SET is_deleted = 1 WHERE id = ?", (workout_id,)
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Exercise Templates
# ---------------------------------------------------------------------------


def upsert_templates(
    conn: sqlite3.Connection,
    templates: Sequence[Mapping[str, Any]],
) -> None:
    """Insert or replace exercise templates.

    Uses ``INSERT OR REPLACE`` — if a template with the same ``id``
    already exists it is replaced.

    Args:
        conn: Open SQLite connection.
        templates: Sequence of template dicts with keys ``id``, ``title``,
            ``type``, ``primary_muscle_group``, ``other_muscle_groups``,
            ``equipment``, ``is_custom``.
    """
    for t in templates:
        conn.execute(
            """INSERT OR REPLACE INTO exercise_templates
               (id, title, type, primary_muscle_group, other_muscle_groups,
                equipment, is_custom)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                t["id"],
                t.get("title", ""),
                t.get("type", ""),
                t.get("primary_muscle_group", ""),
                t.get("other_muscle_groups", "[]"),
                t.get("equipment", ""),
                t.get("is_custom", 0),
            ),
        )
    conn.commit()


def get_templates(
    conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    """Return all cached exercise templates as dicts.

    Args:
        conn: Open SQLite connection.

    Returns:
        List of template dicts ordered by ``id``.
    """
    cursor = conn.execute(
        "SELECT id, title, type, primary_muscle_group, "
        "other_muscle_groups, equipment, is_custom, cached_at "
        "FROM exercise_templates ORDER BY id"
    )
    return [dict(row) for row in cursor.fetchall()]


def get_template_count(conn: sqlite3.Connection) -> int:
    """Return the number of cached exercise templates.

    Args:
        conn: Open SQLite connection.

    Returns:
        Count of rows in ``exercise_templates``.
    """
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM exercise_templates"
    ).fetchone()
    return row["cnt"]


# ---------------------------------------------------------------------------
# Routines
# ---------------------------------------------------------------------------


def upsert_routine(
    conn: sqlite3.Connection,
    routine: Mapping[str, Any],
) -> None:
    """Insert or replace a single routine.

    Uses ``INSERT OR REPLACE`` — if a routine with the same ``id``
    already exists it is replaced.

    Args:
        conn: Open SQLite connection.
        routine: Dict with keys ``id``, ``title``, ``folder_id``,
            ``created_at``, ``updated_at``.
    """
    conn.execute(
        """INSERT OR REPLACE INTO routines
           (id, title, folder_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            routine["id"],
            routine.get("title", ""),
            routine.get("folder_id"),
            routine.get("created_at"),
            routine.get("updated_at"),
        ),
    )
    conn.commit()


def upsert_routines(
    conn: sqlite3.Connection,
    routines: Sequence[Mapping[str, Any]],
) -> None:
    """Insert or replace multiple routines.

    Args:
        conn: Open SQLite connection.
        routines: Sequence of routine dicts.
    """
    for r in routines:
        upsert_routine(conn, r)


def get_routines(
    conn: sqlite3.Connection,
) -> list[dict[str, Any]]:
    """Return all stored routines ordered by title.

    Args:
        conn: Open SQLite connection.

    Returns:
        List of routine dicts ordered by ``title``.
    """
    cursor = conn.execute(
        "SELECT id, title, folder_id, created_at, updated_at "
        "FROM routines ORDER BY title"
    )
    return [dict(row) for row in cursor.fetchall()]


def get_routine(
    conn: sqlite3.Connection,
    routine_id: str,
) -> dict[str, Any] | None:
    """Return a single routine by id.

    Args:
        conn: Open SQLite connection.
        routine_id: The routine UUID.

    Returns:
        Routine dict or ``None`` if not found.
    """
    cursor = conn.execute(
        "SELECT id, title, folder_id, created_at, updated_at "
        "FROM routines WHERE id = ?",
        (routine_id,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Sync Metadata (key/value store)
# ---------------------------------------------------------------------------


def set_sync_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Set a sync metadata key/value pair.

    Uses ``INSERT OR REPLACE`` — if the key already exists its value
    is replaced.

    Args:
        conn: Open SQLite connection.
        key: Metadata key (e.g. ``last_sync_at``).
        value: String value to store.
    """
    conn.execute(
        "INSERT OR REPLACE INTO sync_metadata (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()


def get_sync_meta(conn: sqlite3.Connection, key: str) -> str | None:
    """Retrieve a sync metadata value by key.

    Args:
        conn: Open SQLite connection.
        key: Metadata key to look up.

    Returns:
        The stored value string, or ``None`` if the key does not exist.
    """
    cursor = conn.execute(
        "SELECT value FROM sync_metadata WHERE key = ?", (key,)
    )
    row = cursor.fetchone()
    return row["value"] if row else None
