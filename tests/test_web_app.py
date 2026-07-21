"""Tests for web app factory, healthcheck, middleware, and engine changes.

Tests cover:
  - WAL mode enabled on connections
  - users table DDL in SCHEMA_SQL
  - App factory create_app()
  - Healthcheck endpoint
  - Static file serving
"""

from __future__ import annotations

import sqlite3

import pytest


# ===========================================================================
# T1 — WAL mode
# ===========================================================================


class TestWalMode:
    """PRAGMA journal_mode=WAL is set on every connection."""

    def test_wal_mode_on_file_db(self, tmp_path: pytest.TempPathFactory) -> None:
        """Given a file-based DB, journal_mode should be 'wal'."""
        from darth_gain.db.engine import create_engine

        db_path = str(tmp_path / "test_wal.db")
        conn = create_engine(db_path)
        try:
            row = conn.execute("PRAGMA journal_mode").fetchone()
            assert row is not None
            assert row[0] == "wal"
        finally:
            conn.close()

    def test_wal_mode_on_memory_db(self) -> None:
        """Given an in-memory DB, pragma should not raise."""
        from darth_gain.db.engine import create_engine

        conn = create_engine(":memory:")
        try:
            # In-memory SQLite may silently fall back to 'memory' journal mode
            # but the pragma call itself should not error
            row = conn.execute("PRAGMA journal_mode").fetchone()
            assert row is not None
        finally:
            conn.close()


# ===========================================================================
# T2 — users table DDL
# ===========================================================================


class TestUsersDDL:
    """Users table is created as part of SCHEMA_SQL."""

    @pytest.fixture
    def conn_with_users(self) -> sqlite3.Connection:
        from darth_gain.db.engine import create_engine, create_tables

        c = create_engine(":memory:")
        create_tables(c)
        return c

    def test_users_table_exists(self, conn_with_users: sqlite3.Connection) -> None:
        """users table should exist after create_tables."""
        row = conn_with_users.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        assert row is not None

    def test_users_table_columns(self, conn_with_users: sqlite3.Connection) -> None:
        """users table should have all required columns."""
        cursor = conn_with_users.execute("PRAGMA table_info(users)")
        cols = {r["name"]: r for r in cursor.fetchall()}

        assert "id" in cols
        assert cols["id"]["type"].upper() == "INTEGER"
        assert cols["id"]["pk"] == 1

        assert "username" in cols
        assert cols["username"]["type"].upper() == "TEXT"
        assert cols["username"]["notnull"] == 1

        assert "password_hash" in cols
        assert cols["password_hash"]["type"].upper() == "TEXT"
        assert cols["password_hash"]["notnull"] == 1

        assert "hevy_api_key" in cols
        assert cols["hevy_api_key"]["type"].upper() == "TEXT"

        assert "created_at" in cols
        assert cols["created_at"]["type"].upper() == "TEXT"
        assert cols["created_at"]["notnull"] == 1

    def test_username_unique_constraint(self, conn_with_users: sqlite3.Connection) -> None:
        """Duplicate usernames should be rejected."""
        conn_with_users.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            ("alice", "hash1"),
        )
        conn_with_users.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn_with_users.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                ("alice", "hash2"),
            )
            conn_with_users.commit()


# ===========================================================================
# T3 — App factory, healthcheck, middleware
# ===========================================================================


class TestAppFactory:
    """App factory create_app() behaves correctly."""

    def test_create_app_returns_fastapi_instance(self, tmp_path: pytest.TempPathFactory) -> None:
        """create_app should return a FastAPI instance."""
        from darth_gain.web.app import create_app

        app = create_app(
            data_dir=str(tmp_path),
            secret_key="test-secret",
            users_db_path=":memory:",
        )
        assert app is not None
        assert app.title is not None


class TestHealthcheck:
    """GET /health endpoint."""

    @pytest.fixture
    def client(self, tmp_path: pytest.TempPathFactory):
        from fastapi.testclient import TestClient

        from darth_gain.web.app import create_app

        app = create_app(
            data_dir=str(tmp_path),
            secret_key="test-secret",
            users_db_path=":memory:",
        )
        with TestClient(app) as c:
            yield c

    def test_health_returns_ok(self, client) -> None:
        """GET /health returns 200 with {"status": "ok"}."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_bypasses_auth(self, client) -> None:
        """Healthcheck should work without any session cookie."""
        response = client.get("/health", cookies={})
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestStaticFiles:
    """Static file serving."""

    @pytest.fixture
    def client(self, tmp_path: pytest.TempPathFactory):
        from fastapi.testclient import TestClient

        from darth_gain.web.app import create_app

        # Create the static dir with a test file
        static_dir = tmp_path / "static"
        static_dir.mkdir(parents=True, exist_ok=True)
        (static_dir / "test.txt").write_text("hello world")

        app = create_app(
            data_dir=str(tmp_path),
            secret_key="test-secret",
            users_db_path=":memory:",
            static_dir=str(static_dir),
        )
        with TestClient(app) as c:
            yield c

    def test_static_file_served(self, client) -> None:
        """GET /static/test.txt returns file contents."""
        response = client.get("/static/test.txt")
        assert response.status_code == 200
        assert response.text == "hello world"

    def test_static_file_not_found(self, client) -> None:
        """GET /static/nonexistent.txt returns 404."""
        response = client.get("/static/nonexistent.txt")
        assert response.status_code == 404


class TestAppStartup:
    """App startup creates users.db and users table."""

    def test_startup_creates_users_table(self, tmp_path: pytest.TempPathFactory) -> None:
        """On app startup, the users table should be created."""
        users_db = tmp_path / "users.db"

        from darth_gain.web.app import create_app

        app = create_app(
            data_dir=str(tmp_path),
            secret_key="test-secret",
            users_db_path=str(users_db),
        )

        from fastapi.testclient import TestClient

        with TestClient(app) as _client:
            # Lifespan startup ran — users.db should exist
            assert users_db.exists()
            conn = sqlite3.connect(str(users_db))
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
            ).fetchone()
            assert row is not None
            conn.close()
