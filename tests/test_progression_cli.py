"""Tests for darth_gain.cli — progression command group.

Follows patterns from ``test_cli.py``: CliRunner, class-based grouping,
source-level patching via ``unittest.mock.patch``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from darth_gain.cli import cli
from darth_gain.progression.models import ProgressionConfig, ProgressionStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_status(**overrides: Any) -> ProgressionStatus:
    """Factory for ProgressionStatus with sensible progress defaults."""
    defaults: dict[str, Any] = dict(
        exercise_template_id="t001",
        exercise_name="Bench Press",
        rep_range=(8, 12),
        current_weight_kg=80.0,
        latest_reps=[12, 12, 12],
        top_of_range_reached=True,
        recommendation="increase to 82.5 kg",
        error=None,
    )
    defaults.update(overrides)
    return ProgressionStatus(**defaults)


# ---------------------------------------------------------------------------
# Help output
# ---------------------------------------------------------------------------


class TestProgressionCheckHelp:
    """Progression group and its commands should appear in help."""

    def test_progression_in_root_help(self) -> None:
        """``--help`` includes ``progression`` in the command list."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "progression" in result.output

    def test_progression_help_shows_commands(self) -> None:
        """``progression --help`` lists ``check`` and ``config``."""
        runner = CliRunner()
        result = runner.invoke(cli, ["progression", "--help"])
        assert result.exit_code == 0
        assert "check" in result.output
        assert "config" in result.output


# ---------------------------------------------------------------------------
# Check output formatting
# ---------------------------------------------------------------------------


class TestProgressionCheckOutput:
    """Verify formatted output for every ProgressionStatus variant."""

    def _check(self, status: ProgressionStatus, args: list[str] | None = None) -> Any:
        """Invoke check with patched engine and DB, return result."""
        if args is None:
            args = ["t001"]
        runner = CliRunner()
        with patch("darth_gain.progression.ProgressionEngine") as mock_cls, \
             patch("darth_gain.cli.create_engine"), \
             patch("darth_gain.cli.create_tables"):
            mock_engine = MagicMock()
            mock_engine.check.return_value = status
            mock_cls.return_value = mock_engine
            return runner.invoke(cli, ["progression", "check", *args])

    def test_progress_output_format(self) -> None:
        """Progress status: exercise name, weight, PROGRESS label."""
        result = self._check(_make_status())
        assert result.exit_code == 0
        assert "Bench Press" in result.output
        assert "80.0 kg" in result.output
        assert "82.5 kg" in result.output
        assert "PROGRESS" in result.output

    def test_maintain_output_format(self) -> None:
        """Maintain status: MAINTAIN label, current weight, rep_max hint."""
        result = self._check(_make_status(
            current_weight_kg=80.0,
            latest_reps=[10, 9, 11, 8],
            top_of_range_reached=False,
            recommendation="keep at 80.0 kg",
        ))
        assert result.exit_code == 0
        assert "MAINTAIN" in result.output
        assert "80.0 kg" in result.output
        assert "12" in result.output  # rep_max in the hint

    def test_insufficient_data_output(self) -> None:
        """Insufficient data: INSUFFICIENT DATA label, not an error."""
        result = self._check(_make_status(
            current_weight_kg=None,
            latest_reps=[],
            top_of_range_reached=False,
            recommendation="Insufficient data — no workout history found",
        ))
        assert result.exit_code == 0
        assert "INSUFFICIENT DATA" in result.output or "insufficient" in result.output.lower()

    def test_skipped_output(self) -> None:
        """Skipped: SKIPPED label with explanation."""
        result = self._check(_make_status(
            current_weight_kg=None,
            latest_reps=[],
            top_of_range_reached=False,
            recommendation="Progression checking is disabled for this exercise",
        ))
        assert result.exit_code == 0
        assert "SKIPPED" in result.output or "skipped" in result.output.lower()

    def test_unknown_template_exits_nonzero(self) -> None:
        """Unknown template ID → non-zero exit, error message."""
        result = self._check(
            _make_status(
                exercise_name="",
                current_weight_kg=None,
                latest_reps=[],
                top_of_range_reached=False,
                recommendation="Exercise template not found",
                error="Unknown exercise template",
            ),
            args=["unknown123"],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# No API key required
# ---------------------------------------------------------------------------


class TestProgressionCheckNoApiKey:
    """Progression commands don't need HEVY_API_KEY."""

    def test_works_without_hevy_api_key(self) -> None:
        """No HEVY_API_KEY in env → command proceeds without error."""
        runner = CliRunner()
        with patch("darth_gain.progression.ProgressionEngine") as mock_cls, \
             patch("darth_gain.cli.create_engine"), \
             patch("darth_gain.cli.create_tables"), \
             patch.dict("os.environ", {}, clear=True):
            mock_engine = MagicMock()
            mock_engine.check.return_value = _make_status()
            mock_cls.return_value = mock_engine
            result = runner.invoke(cli, ["progression", "check", "t001"])

        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Custom --db-path
# ---------------------------------------------------------------------------


class TestProgressionCheckDbPath:
    """--db-path option is respected."""

    def test_custom_db_path_used(self) -> None:
        """``--db-path`` is passed through to create_engine."""
        runner = CliRunner()
        with patch("darth_gain.progression.ProgressionEngine") as mock_cls, \
             patch("darth_gain.cli.create_engine") as mock_engine_factory, \
             patch("darth_gain.cli.create_tables"):
            mock_engine = MagicMock()
            mock_engine.check.return_value = _make_status()
            mock_cls.return_value = mock_engine
            result = runner.invoke(cli, ["progression", "check", "t001", "--db-path", "/tmp/custom.db"])

        assert result.exit_code == 0
        # Verify create_engine was called with the custom path
        call_args, _ = mock_engine_factory.call_args
        assert "/tmp/custom.db" in call_args[0]


# ---------------------------------------------------------------------------
# Config show
# ---------------------------------------------------------------------------


class TestProgressionConfigShow:
    """``config show <id>`` displays progression settings."""

    def test_config_show_configured(self) -> None:
        """Shows stored config values."""
        runner = CliRunner()
        with patch("darth_gain.progression.repo.get_config") as mock_get_config, \
             patch("darth_gain.cli.create_engine"), \
             patch("darth_gain.cli.create_tables"):
            mock_get_config.return_value = ProgressionConfig(
                exercise_template_id="t001",
                rep_min=6,
                rep_max=10,
                weight_increment=5.0,
                enabled=True,
            )
            result = runner.invoke(cli, ["progression", "config", "show", "t001"])

        assert result.exit_code == 0
        assert "6" in result.output
        assert "10" in result.output
        assert "5.0" in result.output
        assert "yes" in result.output.lower() or "enabled" in result.output.lower()

    def test_config_show_unconfigured_defaults(self) -> None:
        """No config row → shows defaults."""
        runner = CliRunner()
        with patch("darth_gain.progression.repo.get_config") as mock_get_config, \
             patch("darth_gain.cli.create_engine"), \
             patch("darth_gain.cli.create_tables"):
            mock_get_config.return_value = ProgressionConfig(
                exercise_template_id="t050",
            )
            result = runner.invoke(cli, ["progression", "config", "show", "t050"])

        assert result.exit_code == 0
        assert "8" in result.output  # default rep_min
        assert "12" in result.output  # default rep_max
        assert "2.5" in result.output  # default increment


# ---------------------------------------------------------------------------
# Config set
# ---------------------------------------------------------------------------


class TestProgressionConfigSet:
    """``config set <id> --options`` updates progression settings."""

    def test_config_set_increment(self) -> None:
        """``--increment 5.0`` calls set_config with updated increment."""
        runner = CliRunner()
        with patch("darth_gain.progression.repo.get_config") as mock_get_config, \
             patch("darth_gain.progression.repo.set_config") as mock_set_config, \
             patch("darth_gain.cli.create_engine"), \
             patch("darth_gain.cli.create_tables"):
            mock_get_config.return_value = ProgressionConfig(
                exercise_template_id="t001",
            )
            result = runner.invoke(cli, ["progression", "config", "set", "t001", "--increment", "5.0"])

        assert result.exit_code == 0
        # Verify set_config was called with increment=5.0
        args, _ = mock_set_config.call_args
        saved_config: ProgressionConfig = args[1]
        assert saved_config.weight_increment == 5.0
        assert saved_config.rep_min == 8  # unchanged default
        assert saved_config.rep_max == 12  # unchanged default

    def test_config_set_enabled(self) -> None:
        """``--enabled`` sets enabled=True."""
        runner = CliRunner()
        with patch("darth_gain.progression.repo.get_config") as mock_get_config, \
             patch("darth_gain.progression.repo.set_config") as mock_set_config, \
             patch("darth_gain.cli.create_engine"), \
             patch("darth_gain.cli.create_tables"):
            mock_get_config.return_value = ProgressionConfig(
                exercise_template_id="t001",
                enabled=False,
            )
            result = runner.invoke(cli, ["progression", "config", "set", "t001", "--enabled"])

        assert result.exit_code == 0
        args, _ = mock_set_config.call_args
        saved_config: ProgressionConfig = args[1]
        assert saved_config.enabled is True

    def test_config_set_disabled(self) -> None:
        """``--disabled`` sets enabled=False."""
        runner = CliRunner()
        with patch("darth_gain.progression.repo.get_config") as mock_get_config, \
             patch("darth_gain.progression.repo.set_config") as mock_set_config, \
             patch("darth_gain.cli.create_engine"), \
             patch("darth_gain.cli.create_tables"):
            mock_get_config.return_value = ProgressionConfig(
                exercise_template_id="t001",
                enabled=True,
            )
            result = runner.invoke(cli, ["progression", "config", "set", "t001", "--disabled"])

        assert result.exit_code == 0
        args, _ = mock_set_config.call_args
        saved_config: ProgressionConfig = args[1]
        assert saved_config.enabled is False

    def test_config_set_confirmation_output(self) -> None:
        """Set command prints a confirmation message."""
        runner = CliRunner()
        with patch("darth_gain.progression.repo.get_config") as mock_get_config, \
             patch("darth_gain.progression.repo.set_config"), \
             patch("darth_gain.cli.create_engine"), \
             patch("darth_gain.cli.create_tables"):
            mock_get_config.return_value = ProgressionConfig(
                exercise_template_id="t001",
            )
            result = runner.invoke(cli, ["progression", "config", "set", "t001", "--rep-min", "6"])

        assert result.exit_code == 0
        assert "updated" in result.output.lower() or "t001" in result.output
