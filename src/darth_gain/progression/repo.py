"""Repository functions for progression engine CRUD operations.

Provides module-level functions for reading and writing progression
configuration and history, following the same pattern as ``db/repo.py``.
"""

from __future__ import annotations

import sqlite3

from darth_gain.progression.models import ProgressionConfig, ProgressionHistoryEntry

# ---------------------------------------------------------------------------
# Progression Config
# ---------------------------------------------------------------------------


def get_config(conn: sqlite3.Connection, template_id: str) -> ProgressionConfig:
    """Return the progression config for a template, or defaults if no row.

    Args:
        conn: Open SQLite connection.
        template_id: The exercise template ID to look up.

    Returns:
        A ``ProgressionConfig`` with stored values or defaults.
        Never returns ``None``.
    """
    cursor = conn.execute(
        """SELECT exercise_template_id, rep_min, rep_max, weight_increment, enabled
           FROM progression_config
           WHERE exercise_template_id = ?""",
        (template_id,),
    )
    row = cursor.fetchone()
    if row:
        return ProgressionConfig(
            exercise_template_id=row["exercise_template_id"],
            rep_min=row["rep_min"],
            rep_max=row["rep_max"],
            weight_increment=row["weight_increment"],
            enabled=bool(row["enabled"]),
        )
    return ProgressionConfig(exercise_template_id=template_id)


def set_config(conn: sqlite3.Connection, config: ProgressionConfig) -> None:
    """Upsert a progression config for the given exercise template.

    Inserts a new row or replaces an existing one with the same
    ``exercise_template_id``.

    Args:
        conn: Open SQLite connection.
        config: The ``ProgressionConfig`` to persist.
    """
    conn.execute(
        """INSERT OR REPLACE INTO progression_config
           (exercise_template_id, rep_min, rep_max, weight_increment, enabled)
           VALUES (?, ?, ?, ?, ?)""",
        (
            config.exercise_template_id,
            config.rep_min,
            config.rep_max,
            config.weight_increment,
            int(config.enabled),
        ),
    )
    conn.commit()


def get_all_configs(conn: sqlite3.Connection) -> list[ProgressionConfig]:
    """Return all stored progression configs.

    Args:
        conn: Open SQLite connection.

    Returns:
        List of ``ProgressionConfig`` objects, one per stored row.
        Empty list if no configs exist.
    """
    cursor = conn.execute(
        """SELECT exercise_template_id, rep_min, rep_max, weight_increment, enabled
           FROM progression_config
           ORDER BY exercise_template_id"""
    )
    return [
        ProgressionConfig(
            exercise_template_id=row["exercise_template_id"],
            rep_min=row["rep_min"],
            rep_max=row["rep_max"],
            weight_increment=row["weight_increment"],
            enabled=bool(row["enabled"]),
        )
        for row in cursor.fetchall()
    ]


# ---------------------------------------------------------------------------
# Progression History
# ---------------------------------------------------------------------------


def add_history_entry(
    conn: sqlite3.Connection, entry: ProgressionHistoryEntry
) -> int:
    """Insert a progression history entry and return its auto-incremented id.

    Args:
        conn: Open SQLite connection.
        entry: The ``ProgressionHistoryEntry`` to persist. The ``id`` field
            is ignored and replaced by auto-increment.

    Returns:
        The newly inserted row id.
    """
    cursor = conn.execute(
        """INSERT INTO progression_history
           (exercise_template_id, checked_at, status,
            current_weight_kg, recommended_weight_kg, details)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            entry.exercise_template_id,
            entry.checked_at,
            entry.status,
            entry.current_weight_kg,
            entry.recommended_weight_kg,
            entry.details,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_history(
    conn: sqlite3.Connection, template_id: str
) -> list[ProgressionHistoryEntry]:
    """Return all progression history entries for a template, ordered by id.

    Args:
        conn: Open SQLite connection.
        template_id: The exercise template ID to look up.

    Returns:
        List of ``ProgressionHistoryEntry`` objects, oldest first.
        Empty list if no history exists.
    """
    cursor = conn.execute(
        """SELECT id, exercise_template_id, checked_at, status,
                  current_weight_kg, recommended_weight_kg, details
           FROM progression_history
           WHERE exercise_template_id = ?
           ORDER BY id ASC""",
        (template_id,),
    )
    return [_row_to_history_entry(row) for row in cursor.fetchall()]


def get_latest_history(
    conn: sqlite3.Connection, template_id: str
) -> ProgressionHistoryEntry | None:
    """Return the most recent progression history entry for a template.

    Args:
        conn: Open SQLite connection.
        template_id: The exercise template ID to look up.

    Returns:
        The most recent ``ProgressionHistoryEntry``, or ``None`` if no history
        exists.
    """
    cursor = conn.execute(
        """SELECT id, exercise_template_id, checked_at, status,
                  current_weight_kg, recommended_weight_kg, details
           FROM progression_history
           WHERE exercise_template_id = ?
           ORDER BY id DESC
           LIMIT 1""",
        (template_id,),
    )
    row = cursor.fetchone()
    return _row_to_history_entry(row) if row else None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _row_to_history_entry(row: sqlite3.Row) -> ProgressionHistoryEntry:
    """Convert a SQLite row to a ProgressionHistoryEntry."""
    return ProgressionHistoryEntry(
        id=row["id"],
        exercise_template_id=row["exercise_template_id"],
        checked_at=row["checked_at"],
        status=row["status"],
        current_weight_kg=row["current_weight_kg"],
        recommended_weight_kg=row["recommended_weight_kg"],
        details=row["details"],
    )
