"""DARTH-GAIN CLI — entry point for the Click application."""

from __future__ import annotations

import logging
import sys

import click

from darth_gain.config import Config
from darth_gain.db.engine import create_engine, create_tables

logger = logging.getLogger(__name__)

# Module-level sentinel for testability — allows tests to patch is_tty
is_tty: bool = sys.stdout.isatty()


@click.group()
def cli() -> None:
    """DARTH-GAIN: Automate your Hevy workout progression."""


@cli.command()
@click.option("--since", "-s", default=None, help="ISO 8601 timestamp to sync from")
@click.option("--dry-run", "-n", is_flag=True, help="Fetch and display without storing")
@click.option("--verbose", "-v", is_flag=True, help="Enable detailed logging")
@click.option("--db-path", default=None, help="Path to SQLite database")
@click.option("--refresh-templates", is_flag=True, help="Force re-fetch exercise templates")
def ingest(
    since: str | None,
    dry_run: bool,
    verbose: bool,
    db_path: str | None,
    refresh_templates: bool,
) -> None:
    """Sync Hevy workouts to the local database."""
    # 1. Build config
    cfg = Config(
        hevy_api_key=None,
        since=since,
        dry_run=dry_run,
        verbose=verbose,
        db_path=db_path,
        refresh_templates=refresh_templates,
    )

    # 2. Setup logging
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)

    # 3. Create DB connection
    conn = create_engine(cfg.db_path)
    create_tables(conn)

    # 4. Create API client
    from darth_gain.hevy.client import HevyClient

    api = HevyClient(api_key=cfg.hevy_api_key)

    # 5. Non-TTY detection — suppress progress bar for cron
    use_tty = is_tty

    # 6. Run sync (with Rich progress if TTY and multi-page)
    from darth_gain.hevy.sync import sync

    if use_tty:
        from rich.progress import Progress

        with Progress(transient=True) as progress_bar:
            result = sync(api, conn, cfg, progress=progress_bar)
    else:
        result = sync(api, conn, cfg)

    # 7. Print summary
    summary = f"Sync complete: {result.updated} updated, {result.deleted} deleted"
    if result.errors:
        summary += f", {result.errors} errors"
    click.echo(summary)
    if result.errors:
        raise click.Abort()
