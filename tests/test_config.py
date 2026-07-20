"""Tests for darth_gain.config — Config dataclass and resolution logic."""

from __future__ import annotations


import pytest

from darth_gain.config import Config


class TestConfigDefaults:
    """Config should resolve defaults from environment variables and platformdirs."""

    def test_hevy_api_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config reads HEVY_API_KEY from environment."""
        monkeypatch.setenv("HEVY_API_KEY", "test-key-123")
        monkeypatch.setenv("XDG_DATA_HOME", "/tmp/xdg-test")
        cfg = Config()
        assert cfg.hevy_api_key == "test-key-123"

    def test_db_path_default_from_platformdirs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config resolves db_path from platformdirs when not overridden."""
        monkeypatch.setenv("XDG_DATA_HOME", "/tmp/xdg-test")
        monkeypatch.setenv("HEVY_API_KEY", "key")
        cfg = Config()
        assert cfg.db_path == "/tmp/xdg-test/darth-gain/workouts.db"

    def test_db_path_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Explicit db_path override takes precedence over defaults."""
        monkeypatch.setenv("HEVY_API_KEY", "key")
        cfg = Config(db_path="/custom/path/db.sqlite")
        assert cfg.db_path == "/custom/path/db.sqlite"

    def test_since_default_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """since defaults to None when not provided."""
        monkeypatch.setenv("HEVY_API_KEY", "key")
        cfg = Config()
        assert cfg.since is None

    def test_since_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Explicit since override is stored."""
        monkeypatch.setenv("HEVY_API_KEY", "key")
        cfg = Config(since="2024-01-01T00:00:00Z")
        assert cfg.since == "2024-01-01T00:00:00Z"

    def test_dry_run_default_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """dry_run defaults to False."""
        monkeypatch.setenv("HEVY_API_KEY", "key")
        cfg = Config()
        assert cfg.dry_run is False

    def test_dry_run_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """dry_run can be set to True."""
        monkeypatch.setenv("HEVY_API_KEY", "key")
        cfg = Config(dry_run=True)
        assert cfg.dry_run is True

    def test_verbose_default_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """verbose defaults to False."""
        monkeypatch.setenv("HEVY_API_KEY", "key")
        cfg = Config()
        assert cfg.verbose is False

    def test_verbose_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """verbose can be set to True."""
        monkeypatch.setenv("HEVY_API_KEY", "key")
        cfg = Config(verbose=True)
        assert cfg.verbose is True

    def test_refresh_templates_default_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """refresh_templates defaults to False."""
        monkeypatch.setenv("HEVY_API_KEY", "key")
        cfg = Config()
        assert cfg.refresh_templates is False

    def test_refresh_templates_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """refresh_templates can be set to True."""
        monkeypatch.setenv("HEVY_API_KEY", "key")
        cfg = Config(refresh_templates=True)
        assert cfg.refresh_templates is True

    def test_api_key_missing_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config raises ValueError when HEVY_API_KEY is not set and not provided."""
        monkeypatch.delenv("HEVY_API_KEY", raising=False)
        with pytest.raises(ValueError, match="HEVY_API_KEY"):
            Config()

    def test_api_key_explicit_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Explicit hevy_api_key kwarg takes precedence over env var."""
        monkeypatch.setenv("HEVY_API_KEY", "env-key")
        cfg = Config(hevy_api_key="explicit-key")
        assert cfg.hevy_api_key == "explicit-key"

    def test_platformdirs_import_works(self) -> None:
        """platformdirs is importable (dependency added to pyproject.toml)."""
        import platformdirs  # noqa: F401
        assert True

    def test_dry_run_sets_memory_db(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """dry_run=True without explicit db_path sets db_path to ':memory:'."""
        monkeypatch.setenv("HEVY_API_KEY", "key")
        cfg = Config(dry_run=True)
        assert cfg.db_path == ":memory:"

    def test_dry_run_with_explicit_db_path_uses_explicit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """dry_run=True with explicit db_path uses the explicit path, not :memory:."""
        monkeypatch.setenv("HEVY_API_KEY", "key")
        cfg = Config(dry_run=True, db_path="/tmp/real.db")
        assert cfg.db_path == "/tmp/real.db"
