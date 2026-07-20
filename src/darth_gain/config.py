"""Configuration resolution for DARTH-GAIN.

Provides the Config dataclass which resolves settings from:
1. Explicit constructor arguments (CLI overrides — highest priority)
2. Environment variables
3. platformdirs defaults (XDG-compliant paths)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import platformdirs


@dataclass
class Config:
    """Application configuration resolved from env, defaults, and explicit overrides.

    Resolution order (highest priority first):
    1. Constructor argument (set by CLI)
    2. Environment variable
    3. platformdirs default (db_path only)
    """

    hevy_api_key: str | None = None
    db_path: str | None = None
    since: str | None = None
    dry_run: bool = False
    verbose: bool = False
    refresh_templates: bool = False

    def __post_init__(self) -> None:
        """Resolve defaults after dataclass init."""
        self._resolve_api_key()
        self._resolve_db_path()

    def _resolve_api_key(self) -> None:
        """Resolve HEVY_API_KEY from explicit arg or environment."""
        if self.hevy_api_key is None:
            self.hevy_api_key = os.environ.get("HEVY_API_KEY")
        if not self.hevy_api_key:
            raise ValueError(
                "HEVY_API_KEY is required. Set the HEVY_API_KEY environment "
                "variable or pass it explicitly."
            )

    def _resolve_db_path(self) -> None:
        """Resolve database path, defaulting to platformdirs."""
        if self.db_path is not None:
            return

        if self.dry_run:
            self.db_path = ":memory:"
            return

        data_dir = platformdirs.user_data_dir("darth-gain", ensure_exists=True)
        self.db_path = str(Path(data_dir) / "workouts.db")
