"""SQLite connection management and schema initialization.

Provides:
  - create_engine(db_path) -> sqlite3.Connection
  - create_tables(conn) -> None (idempotent DDL execution)
"""

from __future__ import annotations

import sqlite3

# ---------------------------------------------------------------------------
# DDL Statements
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS workouts (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT DEFAULT '',
    start_time  TEXT NOT NULL,
    end_time    TEXT,
    is_deleted  INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_workouts_start_time ON workouts(start_time);
CREATE INDEX IF NOT EXISTS idx_workouts_updated_at ON workouts(updated_at);

CREATE TABLE IF NOT EXISTS exercises (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id            TEXT NOT NULL REFERENCES workouts(id),
    exercise_template_id  TEXT,
    title                 TEXT,
    notes                 TEXT DEFAULT '',
    sort_order            INTEGER NOT NULL DEFAULT 0,
    is_deleted            INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_exercises_workout_id ON exercises(workout_id);

CREATE TABLE IF NOT EXISTS sets (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_id      INTEGER NOT NULL REFERENCES exercises(id),
    set_index        INTEGER NOT NULL DEFAULT 0,
    type             TEXT DEFAULT 'normal',
    weight_kg        REAL,
    reps             INTEGER,
    distance_meters  REAL,
    duration_seconds REAL,
    rpe              REAL,
    is_deleted       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS exercise_templates (
    id                   TEXT PRIMARY KEY,
    title                TEXT,
    type                 TEXT,
    primary_muscle_group TEXT,
    other_muscle_groups  TEXT,
    equipment            TEXT,
    is_custom            INTEGER DEFAULT 0,
    cached_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sync_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS progression_config (
    exercise_template_id TEXT PRIMARY KEY REFERENCES exercise_templates(id),
    rep_min              INTEGER NOT NULL DEFAULT 8,
    rep_max              INTEGER NOT NULL DEFAULT 12,
    weight_increment     REAL NOT NULL DEFAULT 2.5,
    enabled              INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS progression_history (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_template_id TEXT NOT NULL REFERENCES exercise_templates(id),
    checked_at           TEXT NOT NULL DEFAULT (datetime('now')),
    status               TEXT NOT NULL CHECK(status IN ('progress','maintain','insufficient_data','skipped')),
    current_weight_kg    REAL,
    recommended_weight_kg REAL,
    details              TEXT
);

CREATE INDEX IF NOT EXISTS idx_progression_history_template
    ON progression_history(exercise_template_id);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    hevy_api_key  TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_engine(db_path: str) -> sqlite3.Connection:
    """Create and return a SQLite connection.

    Args:
        db_path: Path to the SQLite database file. Use ``:memory:`` for
            an in-memory database (used by dry-run and tests).

    Returns:
        A ``sqlite3.Connection`` with foreign keys enabled.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    """Execute DDL to create all tables and indexes (idempotent).

    Safe to call multiple times — uses ``CREATE TABLE IF NOT EXISTS``
    and ``CREATE INDEX IF NOT EXISTS``.

    Args:
        conn: An open SQLite connection.
    """
    conn.executescript(SCHEMA_SQL)
    conn.commit()
