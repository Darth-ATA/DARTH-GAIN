"""Tests for darth_gain.cli — Click CLI command."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from darth_gain.cli import cli


def _patch_ingest_deps() -> list[Any]:
    """Patch all dependencies called by the ingest command.

    Returns a list of the patcher ``start`` return values for assertions.
    """
    patchers = [
        patch("darth_gain.db.engine.create_engine"),
        patch("darth_gain.db.engine.create_tables"),
        patch("darth_gain.hevy.client.HevyClient"),
        patch("darth_gain.hevy.sync.sync"),
    ]
    mocks = [p.start() for p in patchers]
    return mocks


class TestCliIngestHelp:
    """The CLI should show usage information with --help."""

    def test_help_shows_usage(self) -> None:
        """Running ``ingest --help`` displays usage information."""
        runner = CliRunner()
        result = runner.invoke(cli, ["ingest", "--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "ingest" in result.output


class TestCliIngestFlags:
    """Each CLI flag should be parsed and passed through to Config."""

    def _invoke(self, args: list[str]) -> MagicMock:
        """Invoke the CLI with args and return the mock_sync from patchers.

        Ensures HEVY_API_KEY is set and is_tty is True.
        """
        runner = CliRunner()
        mocks = self._enter_patches()
        mock_sync = mocks[3]  # sync is the 4th patcher
        with patch.dict(os.environ, {"HEVY_API_KEY": "test-key"}):
            runner.invoke(cli, ["ingest", *args])
        self._exit_patches()
        return mock_sync

    def _enter_patches(self) -> list[MagicMock]:
        """Start all patchers and return their mock objects."""
        patchers = [
            patch("darth_gain.db.engine.create_engine"),
            patch("darth_gain.db.engine.create_tables"),
            patch("darth_gain.hevy.client.HevyClient"),
            patch("darth_gain.hevy.sync.sync"),
            patch("darth_gain.cli.is_tty", True),
        ]
        for p in patchers:
            p.start()
        return [p.start() if i < 4 else p.start() for i, p in enumerate(patchers)]

    def _exit_patches(self) -> None:
        """Stop all patchers."""
        for p in [
            patch("darth_gain.db.engine.create_engine"),
            patch("darth_gain.db.engine.create_tables"),
            patch("darth_gain.hevy.client.HevyClient"),
            patch("darth_gain.hevy.sync.sync"),
            patch("darth_gain.cli.is_tty", True),
        ]:
            p.stop()

    def test_dry_run_flag(self) -> None:
        """--dry-run sets dry_run=True in Config."""
        runner = CliRunner()
        with patch("darth_gain.hevy.sync.sync") as mock_sync, \
             patch("darth_gain.db.engine.create_engine"), \
             patch("darth_gain.db.engine.create_tables"), \
             patch("darth_gain.hevy.client.HevyClient"), \
             patch("darth_gain.cli.is_tty", True), \
             patch.dict(os.environ, {"HEVY_API_KEY": "test-key"}):
            runner.invoke(cli, ["ingest", "--dry-run"])

        cfg = mock_sync.call_args[0][2]
        assert cfg.dry_run is True

    def test_dry_run_short_flag(self) -> None:
        """-n is a shortcut for --dry-run."""
        runner = CliRunner()
        with patch("darth_gain.hevy.sync.sync") as mock_sync, \
             patch("darth_gain.db.engine.create_engine"), \
             patch("darth_gain.db.engine.create_tables"), \
             patch("darth_gain.hevy.client.HevyClient"), \
             patch("darth_gain.cli.is_tty", True), \
             patch.dict(os.environ, {"HEVY_API_KEY": "test-key"}):
            runner.invoke(cli, ["ingest", "-n"])

        cfg = mock_sync.call_args[0][2]
        assert cfg.dry_run is True

    def test_since_option(self) -> None:
        """--since passes the timestamp through to Config."""
        runner = CliRunner()
        with patch("darth_gain.hevy.sync.sync") as mock_sync, \
             patch("darth_gain.db.engine.create_engine"), \
             patch("darth_gain.db.engine.create_tables"), \
             patch("darth_gain.hevy.client.HevyClient"), \
             patch("darth_gain.cli.is_tty", True), \
             patch.dict(os.environ, {"HEVY_API_KEY": "test-key"}):
            runner.invoke(cli, ["ingest", "--since", "2024-01-01T00:00:00Z"])

        cfg = mock_sync.call_args[0][2]
        assert cfg.since == "2024-01-01T00:00:00Z"

    def test_since_short_option(self) -> None:
        """-s is a shortcut for --since."""
        runner = CliRunner()
        with patch("darth_gain.hevy.sync.sync") as mock_sync, \
             patch("darth_gain.db.engine.create_engine"), \
             patch("darth_gain.db.engine.create_tables"), \
             patch("darth_gain.hevy.client.HevyClient"), \
             patch("darth_gain.cli.is_tty", True), \
             patch.dict(os.environ, {"HEVY_API_KEY": "test-key"}):
            runner.invoke(cli, ["ingest", "-s", "2024-06-01T00:00:00Z"])

        cfg = mock_sync.call_args[0][2]
        assert cfg.since == "2024-06-01T00:00:00Z"

    def test_verbose_flag(self) -> None:
        """--verbose sets verbose=True in Config."""
        runner = CliRunner()
        with patch("darth_gain.hevy.sync.sync") as mock_sync, \
             patch("darth_gain.db.engine.create_engine"), \
             patch("darth_gain.db.engine.create_tables"), \
             patch("darth_gain.hevy.client.HevyClient"), \
             patch("darth_gain.cli.is_tty", True), \
             patch.dict(os.environ, {"HEVY_API_KEY": "test-key"}):
            runner.invoke(cli, ["ingest", "--verbose"])

        cfg = mock_sync.call_args[0][2]
        assert cfg.verbose is True

    def test_verbose_short_flag(self) -> None:
        """-v is a shortcut for --verbose."""
        runner = CliRunner()
        with patch("darth_gain.hevy.sync.sync") as mock_sync, \
             patch("darth_gain.db.engine.create_engine"), \
             patch("darth_gain.db.engine.create_tables"), \
             patch("darth_gain.hevy.client.HevyClient"), \
             patch("darth_gain.cli.is_tty", True), \
             patch.dict(os.environ, {"HEVY_API_KEY": "test-key"}):
            runner.invoke(cli, ["ingest", "-v"])

        cfg = mock_sync.call_args[0][2]
        assert cfg.verbose is True

    def test_refresh_templates_flag(self) -> None:
        """--refresh-templates sets refresh_templates=True in Config."""
        runner = CliRunner()
        with patch("darth_gain.hevy.sync.sync") as mock_sync, \
             patch("darth_gain.db.engine.create_engine"), \
             patch("darth_gain.db.engine.create_tables"), \
             patch("darth_gain.hevy.client.HevyClient"), \
             patch("darth_gain.cli.is_tty", True), \
             patch.dict(os.environ, {"HEVY_API_KEY": "test-key"}):
            runner.invoke(cli, ["ingest", "--refresh-templates"])

        cfg = mock_sync.call_args[0][2]
        assert cfg.refresh_templates is True

    def test_db_path_option(self) -> None:
        """--db-path passes the path through to Config."""
        runner = CliRunner()
        with patch("darth_gain.hevy.sync.sync") as mock_sync, \
             patch("darth_gain.db.engine.create_engine"), \
             patch("darth_gain.db.engine.create_tables"), \
             patch("darth_gain.hevy.client.HevyClient"), \
             patch("darth_gain.cli.is_tty", True), \
             patch.dict(os.environ, {"HEVY_API_KEY": "test-key"}):
            runner.invoke(cli, ["ingest", "--db-path", "/tmp/custom.db"])

        cfg = mock_sync.call_args[0][2]
        assert cfg.db_path == "/tmp/custom.db"


class TestCliApiKeyValidation:
    """The CLI should validate HEVY_API_KEY before running sync."""

    def test_missing_api_key_exits_with_error(self) -> None:
        """Without HEVY_API_KEY, the command exits with a non-zero code."""
        runner = CliRunner()
        with patch("darth_gain.db.engine.create_engine"), \
             patch("darth_gain.db.engine.create_tables"):
            with patch.dict(os.environ, {}, clear=True):
                result = runner.invoke(cli, ["ingest"])

        assert result.exit_code != 0
        # The ValueError from Config is propagated through Click
        assert result.exception is not None
        assert "HEVY_API_KEY" in str(result.exception)


class TestCliNonTtyProgress:
    """Non-TTY output should suppress the Rich progress bar."""

    def test_non_tty_suppresses_progress(self) -> None:
        """When not a TTY, sync is called without a progress argument."""
        runner = CliRunner()
        with patch("darth_gain.hevy.sync.sync") as mock_sync, \
             patch("darth_gain.db.engine.create_engine"), \
             patch("darth_gain.db.engine.create_tables"), \
             patch("darth_gain.hevy.client.HevyClient"), \
             patch("darth_gain.cli.is_tty", False), \
             patch.dict(os.environ, {"HEVY_API_KEY": "test-key"}):
            runner.invoke(cli, ["ingest"])

        # When is_tty=False, sync should be called WITHOUT progress keyword
        _, kwargs = mock_sync.call_args
        assert "progress" not in kwargs

    def test_tty_uses_progress(self) -> None:
        """When on a TTY, sync receives a Progress instance."""
        runner = CliRunner()
        with patch("darth_gain.hevy.sync.sync") as mock_sync, \
             patch("darth_gain.db.engine.create_engine"), \
             patch("darth_gain.db.engine.create_tables"), \
             patch("darth_gain.hevy.client.HevyClient"), \
             patch("darth_gain.cli.is_tty", True), \
             patch.dict(os.environ, {"HEVY_API_KEY": "test-key"}):
            runner.invoke(cli, ["ingest"])

        _, kwargs = mock_sync.call_args
        assert "progress" in kwargs


class TestCliSummaryOutput:
    """The CLI should print a summary after sync completes."""

    def test_summary_printed_on_success(self) -> None:
        """A summary line is printed with updated/deleted/errors counts."""
        runner = CliRunner()
        with patch("darth_gain.hevy.sync.sync") as mock_sync, \
             patch("darth_gain.db.engine.create_engine"), \
             patch("darth_gain.db.engine.create_tables"), \
             patch("darth_gain.hevy.client.HevyClient"), \
             patch("darth_gain.cli.is_tty", True), \
             patch.dict(os.environ, {"HEVY_API_KEY": "test-key"}):
            mock_result = MagicMock()
            mock_result.updated = 5
            mock_result.deleted = 1
            mock_result.errors = 0
            mock_sync.return_value = mock_result
            result = runner.invoke(cli, ["ingest"])

        assert result.exit_code == 0
        assert "Sync complete" in result.output
        assert "5 updated" in result.output

    def test_errors_printed_in_summary(self) -> None:
        """When there are errors, they appear in the summary."""
        runner = CliRunner()
        with patch("darth_gain.hevy.sync.sync") as mock_sync, \
             patch("darth_gain.db.engine.create_engine"), \
             patch("darth_gain.db.engine.create_tables"), \
             patch("darth_gain.hevy.client.HevyClient"), \
             patch("darth_gain.cli.is_tty", True), \
             patch.dict(os.environ, {"HEVY_API_KEY": "test-key"}):
            mock_result = MagicMock()
            mock_result.updated = 3
            mock_result.deleted = 0
            mock_result.errors = 2
            mock_sync.return_value = mock_result
            result = runner.invoke(cli, ["ingest"])

        assert "3 updated" in result.output
        assert "2 errors" in result.output

    def test_exits_nonzero_on_errors(self) -> None:
        """When sync has errors, the CLI exits with non-zero code."""
        runner = CliRunner()
        with patch("darth_gain.hevy.sync.sync") as mock_sync, \
             patch("darth_gain.db.engine.create_engine"), \
             patch("darth_gain.db.engine.create_tables"), \
             patch("darth_gain.hevy.client.HevyClient"), \
             patch("darth_gain.cli.is_tty", True), \
             patch.dict(os.environ, {"HEVY_API_KEY": "test-key"}):
            mock_result = MagicMock()
            mock_result.updated = 0
            mock_result.deleted = 0
            mock_result.errors = 5
            mock_sync.return_value = mock_result
            result = runner.invoke(cli, ["ingest"])

        assert result.exit_code != 0
