#!/usr/bin/env python3
"""Migrate a legacy single-user DB to multi-user format.

Copies the existing single-user ``workouts.db`` (from the default
platformdirs path or a custom ``--source``) into the first user's
per-user directory at ``/data/user_{id}/workouts.db``.

Usage::

    # Default: source = ~/.local/share/darth-gain/workouts.db
    python scripts/migrate-to-multi-user.py

    # Custom source, custom username
    python scripts/migrate-to-multi-user.py --source /tmp/old.db --username admin

    # Custom data root
    python scripts/migrate-to-multi-user.py --data-dir /custom/data/path
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from pathlib import Path

from werkzeug.security import generate_password_hash

from darth_gain.db.engine import create_engine, create_tables


def main() -> int:
    """Run the migration: create user, copy DB, verify integrity."""
    default_source = str(
        Path.home() / ".local" / "share" / "darth-gain" / "workouts.db"
    )
    parser = argparse.ArgumentParser(
        description="Migrate legacy single-user DB to multi-user format."
    )
    parser.add_argument(
        "--source",
        default=default_source,
        help="Path to existing workouts.db (default: %(default)s)",
    )
    parser.add_argument(
        "--username",
        default="admin",
        help="Username for the migrated user (default: %(default)s)",
    )
    parser.add_argument(
        "--password",
        default="admin",
        help="Password for the migrated user (default: %(default)s)",
    )
    parser.add_argument(
        "--data-dir",
        default="/data",
        help="Data directory for multi-user databases (default: %(default)s)",
    )
    args = parser.parse_args()

    source = os.path.expanduser(args.source)

    # --- Validate source -------------------------------------------------
    if not os.path.exists(source):
        print(f"ERROR: Source DB not found at {source}")
        return 1

    print(f"Source DB: {source}")
    print(f"Data dir:  {args.data_dir}")

    # --- Create or find user in users.db ---------------------------------
    users_db_path = os.path.join(args.data_dir, "users.db")
    os.makedirs(args.data_dir, exist_ok=True)

    conn = create_engine(users_db_path)
    try:
        create_tables(conn)
        cursor = conn.execute(
            "INSERT OR IGNORE INTO users (username, password_hash) VALUES (?, ?)",
            (args.username, generate_password_hash(args.password)),
        )
        conn.commit()

        if cursor.rowcount == 0:
            row = conn.execute(
                "SELECT id FROM users WHERE username = ?", (args.username,)
            ).fetchone()
            user_id = row["id"]
            print(f"User '{args.username}' already exists with id={user_id}")
        else:
            user_id = cursor.lastrowid
            print(f"Created user '{args.username}' with id={user_id}")
    finally:
        conn.close()

    # --- Copy DB to per-user directory -----------------------------------
    user_db_dir = os.path.join(args.data_dir, f"user_{user_id}")
    os.makedirs(user_db_dir, exist_ok=True)
    dest = os.path.join(user_db_dir, "workouts.db")

    shutil.copy2(source, dest)
    print(f"Copied {source} -> {dest}")

    # --- Verify integrity ------------------------------------------------
    verifier = sqlite3.connect(dest)
    try:
        cursor = verifier.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        if result is not None and result[0] == "ok":
            print("Integrity check PASSED")
        else:
            print(f"WARNING: Integrity check result: {result}")
            return 1
    finally:
        verifier.close()

    print("Migration complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
