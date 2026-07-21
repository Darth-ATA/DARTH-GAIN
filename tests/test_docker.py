"""Smoke tests for Docker deployment configuration.

Tests cover:
  - Dockerfile exists with expected multi-stage structure
  - docker-compose.yml exists with valid service definition
  - Environment variable resolution (DARTH_GAIN_SECRET / dev-secret fallback)
  - Docker build (integration, requires Docker daemon)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _docker_available() -> bool:
    """Check if Docker daemon is accessible."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ===========================================================================
# T1 — Dockerfile structure
# ===========================================================================


class TestDockerfile:
    """Dockerfile exists and has expected multi-stage build structure."""

    def test_dockerfile_exists(self) -> None:
        """Dockerfile should exist at project root."""
        assert (PROJECT_ROOT / "Dockerfile").is_file()

    def test_dockerfile_content(self) -> None:
        """Dockerfile should have expected multi-stage content."""
        content = (PROJECT_ROOT / "Dockerfile").read_text()

        # Multi-stage build
        assert (
            "python:3.13-slim" in content
        ), "Should use python:3.13-slim base image"

        # Build stage installs web deps
        assert (
            "pip install" in content and ".[web]" in content
        ), "Should install package with web dependencies"

        # Runtime config
        assert "EXPOSE 8000" in content, "Should expose port 8000"
        assert "WORKDIR /app" in content, "Should set workdir to /app"
        assert "uvicorn" in content, "Should use uvicorn as server"
        assert (
            "darth_gain.web.app:app" in content
        ), "Should reference the FastAPI app"


# ===========================================================================
# T2 — docker-compose.yml structure
# ===========================================================================


class TestComposeFile:
    """docker-compose.yml exists with valid service definition."""

    def test_compose_exists(self) -> None:
        """docker-compose.yml should exist at project root."""
        assert (PROJECT_ROOT / "docker-compose.yml").is_file()

    def test_compose_content(self) -> None:
        """docker-compose.yml should have expected service structure."""
        content = (PROJECT_ROOT / "docker-compose.yml").read_text()

        assert "web:" in content, "Should define a web service"
        assert "8000:8000" in content, "Should map port 8000"
        assert "./data:/data" in content, "Should mount ./data:/data volume"
        assert "unless-stopped" in content, "Should set restart policy"
        assert (
            "DARTH_GAIN_SECRET" in content
        ), "Should configure DARTH_GAIN_SECRET env var"
        assert (
            "healthcheck" in content.lower()
        ), "Should define a healthcheck"

    def test_compose_valid_yaml(self) -> None:
        """docker-compose.yml should parse as valid YAML."""
        yaml = pytest.importorskip("yaml", reason="PyYAML not installed")

        content = (PROJECT_ROOT / "docker-compose.yml").read_text()
        data = yaml.safe_load(content)

        assert isinstance(data, dict)
        assert "services" in data
        assert "web" in data["services"]

        svc = data["services"]["web"]
        assert "build" in svc, "Service should have build config"
        assert "ports" in svc, "Service should have ports"
        assert "volumes" in svc, "Service should have volumes"
        assert "restart" in svc, "Service should have restart policy"
        assert svc["restart"] == "unless-stopped"
        assert "environment" in svc, "Service should have environment"
        assert "healthcheck" in svc, "Service should have healthcheck"


# ===========================================================================
# T3 — Environment variable handling
# ===========================================================================


class TestSecretKeyResolution:
    """DARTH_GAIN_SECRET env var resolution for Docker deployment."""

    def test_create_app_uses_env_var(
        self,
        tmp_path: pytest.TempPathFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When DARTH_GAIN_SECRET is set, create_app should pick it up."""
        from darth_gain.web.app import create_app

        monkeypatch.setenv("DARTH_GAIN_SECRET", "docker-secret-123")
        app = create_app(
            data_dir=str(tmp_path),
            users_db_path=":memory:",
        )
        with TestClient(app) as _:
            assert app.state.secret_key == "docker-secret-123"

    def test_create_app_fallback_to_dev(
        self,
        tmp_path: pytest.TempPathFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When DARTH_GAIN_SECRET is unset, fallback to 'dev-secret'."""
        from darth_gain.web.app import create_app

        monkeypatch.delenv("DARTH_GAIN_SECRET", raising=False)
        app = create_app(
            data_dir=str(tmp_path),
            users_db_path=":memory:",
        )
        with TestClient(app) as _:
            assert app.state.secret_key == "dev-secret"


# ===========================================================================
# T4 — Docker build (integration / smoke)
# ===========================================================================


class TestDockerBuild:
    """Docker build integration tests — requires Docker daemon."""

    @pytest.mark.skipif(
        not _docker_available(),
        reason="Docker daemon not available",
    )
    def test_docker_build_succeeds(self) -> None:
        """Dockerfile should build without errors."""
        result = subprocess.run(
            ["docker", "build", "-t", "darth-gain-web:test", "."],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            timeout=120,
        )
        assert result.returncode == 0, f"docker build failed:\n{result.stderr}"

    @pytest.mark.skipif(
        not _docker_available(),
        reason="Docker daemon not available",
    )
    def test_compose_config_validates(self) -> None:
        """docker compose config should validate without errors."""
        result = subprocess.run(
            ["docker", "compose", "config", "--quiet"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            timeout=30,
        )
        assert (
            result.returncode == 0
        ), f"docker compose config failed:\n{result.stderr}"
