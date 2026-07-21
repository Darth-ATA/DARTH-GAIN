#!/usr/bin/env python3
"""Iterate all users in users.db and run Hevy sync for each with an API key.

Usage:
    DARTH_GAIN_DATA_DIR=/data python scripts/cron-sync-all.py

Environment:
    DARTH_GAIN_DATA_DIR  Data root directory (default: /data)

This script is designed to replace the single-user ``darth-gain ingest``
cron entry.  Run it from cron instead::

    0 6 * * * /path/to/cron-sync-all.py >> /var/log/darth-gain-sync.log 2>&1
"""

from __future__ import annotations

import logging
import os
import sys

from darth_gain.config import Config
from darth_gain.db.engine import create_engine
from darth_gain.hevy.client import HevyClient
from darth_gain.hevy.sync import sync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("cron-sync-all")


def main() -> int:
    """Open users.db, iterate users with API keys, sync per user."""
    data_dir = os.environ.get("DARTH_GAIN_DATA_DIR", "/data")
    users_db_path = os.path.join(data_dir, "users.db")

    if not os.path.exists(users_db_path):
        logger.error("users.db not found at %s", users_db_path)
        return 1

    conn = create_engine(users_db_path)
    try:
        rows = conn.execute(
            "SELECT id, username, hevy_api_key FROM users "
            "WHERE hevy_api_key IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        logger.info("No users with API keys found — nothing to sync.")
        return 0

    success_count = 0
    failed_count = 0

    for row in rows:
        user_id = row["id"]
        username = row["username"]
        api_key = row["hevy_api_key"]

        user_db_path = os.path.join(data_dir, f"user_{user_id}", "workouts.db")

        logger.info("Syncing user '%s' (id=%d) ...", username, user_id)

        try:
            api = HevyClient(api_key=api_key)
            conn = create_engine(user_db_path)
            try:
                config = Config(
                    hevy_api_key=api_key,
                    db_path=user_db_path,
                )
                result = sync(api=api, conn=conn, config=config)
                logger.info(
                    "User '%s' sync complete: %d updated, %d deleted, %d errors",
                    username,
                    result.updated,
                    result.deleted,
                    result.errors,
                )
                if result.errors == 0:
                    success_count += 1
                else:
                    failed_count += 1
            finally:
                conn.close()
        except Exception as exc:
            logger.exception(
                "User '%s' sync failed: %s", username, exc
            )
            failed_count += 1

    logger.info(
        "Sync complete: %d succeeded, %d failed", success_count, failed_count
    )
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
