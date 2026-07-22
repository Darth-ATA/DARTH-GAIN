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
            task_id = progress_bar.add_task("Syncing...", total=None)
            result = sync(api, conn, cfg, progress=progress_bar, progress_task_id=task_id)
    else:
        result = sync(api, conn, cfg)

    # 7. Print summary
    summary = f"Sync complete: {result.updated} updated, {result.deleted} deleted"
    if result.errors:
        summary += f", {result.errors} errors"
    click.echo(summary)
    if result.errors:
        raise click.Abort()


# ---------------------------------------------------------------------------
# Progression commands
# ---------------------------------------------------------------------------


def _resolve_db_path(db_path: str | None) -> str:
    """Resolve the database path for progression commands.

    Progression commands work without HEVY_API_KEY and resolve the
    database path directly (matching ``Config._resolve_db_path``).
    """
    if db_path is not None:
        return db_path
    from pathlib import Path

    import platformdirs

    data_dir = platformdirs.user_data_dir("darth-gain", ensure_exists=True)
    return str(Path(data_dir) / "workouts.db")


@cli.group()
def progression() -> None:
    """Check and configure exercise progression."""


@progression.command()
@click.argument("exercise_template_id")
@click.option("--db-path", default=None, help="Path to SQLite database")
def check(exercise_template_id: str, db_path: str | None) -> None:
    """Check progression status for an exercise."""
    from darth_gain.progression import ProgressionEngine

    conn = create_engine(_resolve_db_path(db_path))
    create_tables(conn)

    engine = ProgressionEngine(conn)
    result = engine.check(exercise_template_id)

    if result.error:
        click.echo(f"Error: Exercise template '{exercise_template_id}' not found")
        raise click.Abort()

    click.echo(f"Exercise:         {result.exercise_name}")
    click.echo(f"Rep Range:        {result.rep_range[0]}-{result.rep_range[1]}")

    if result.current_weight_kg is not None:
        click.echo(f"Current Weight:   {result.current_weight_kg} kg")
    else:
        click.echo("Current Weight:   —")

    if result.latest_reps:
        reps_str = ", ".join(str(r) for r in result.latest_reps)
        click.echo(f"Latest Reps:      {reps_str}")
    else:
        click.echo("Latest Reps:      —")

    if result.top_of_range_reached:
        click.echo(f"Status:           PROGRESS → {result.recommendation}")
    elif result.current_weight_kg is not None:
        click.echo(
            f"Status:           MAINTAIN at {result.current_weight_kg} kg"
            f" — need all sets ≥ {result.rep_range[1]} reps"
        )
    elif "insufficient data" in result.recommendation.lower():
        click.echo(f"Status:           INSUFFICIENT DATA — {result.recommendation}")
    else:
        click.echo(f"Status:           SKIPPED — {result.recommendation}")


@progression.group()
def config() -> None:
    """Manage progression configuration."""


@config.command("show")
@click.argument("exercise_template_id")
@click.option("--db-path", default=None, help="Path to SQLite database")
def config_show(exercise_template_id: str, db_path: str | None) -> None:
    """Show progression config for an exercise."""
    from darth_gain.progression.repo import get_config

    conn = create_engine(_resolve_db_path(db_path))
    create_tables(conn)

    cfg = get_config(conn, exercise_template_id)
    click.echo(f"Exercise Template: {cfg.exercise_template_id}")
    click.echo(f"Rep Range:         {cfg.rep_min}-{cfg.rep_max}")
    click.echo(f"Weight Increment:  {cfg.weight_increment} kg")
    click.echo(f"Enabled:           {'yes' if cfg.enabled else 'no'}")


@config.command("set")
@click.argument("exercise_template_id")
@click.option("--rep-min", type=int, default=None, help="Minimum reps in the rep range")
@click.option("--rep-max", type=int, default=None, help="Maximum reps in the rep range")
@click.option("--increment", type=float, default=None, help="Weight increment in kg")
@click.option("--enabled/--disabled", default=None, help="Enable or disable progression checking")
@click.option("--db-path", default=None, help="Path to SQLite database")
def config_set(
    exercise_template_id: str,
    rep_min: int | None,
    rep_max: int | None,
    increment: float | None,
    enabled: bool | None,
    db_path: str | None,
) -> None:
    """Set progression config for an exercise."""
    from darth_gain.progression.models import ProgressionConfig
    from darth_gain.progression.repo import get_config, set_config

    conn = create_engine(_resolve_db_path(db_path))
    create_tables(conn)

    current = get_config(conn, exercise_template_id)

    new_config = ProgressionConfig(
        exercise_template_id=exercise_template_id,
        rep_min=rep_min if rep_min is not None else current.rep_min,
        rep_max=rep_max if rep_max is not None else current.rep_max,
        weight_increment=increment if increment is not None else current.weight_increment,
        enabled=enabled if enabled is not None else current.enabled,
    )
    set_config(conn, new_config)
    click.echo(f"Config updated for '{exercise_template_id}'")
