"""Tests for routine view data infrastructure — schema, adapter, client, repo, sync.

Strict TDD — tests define the contract before implementation.
"""

from __future__ import annotations

import sqlite3
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from darth_gain.db.engine import create_engine, create_tables
from darth_gain.db.repo import (
    get_routine,
    get_routines,
    upsert_routine,
    upsert_routines,
    upsert_workout,
)
from darth_gain.hevy.client import HevyClient
from darth_gain.hevy.sync import sync
from tests.conftest import MockHevyClient, EventsPage, WorkoutEvent

# ===========================================================================
# Schema — routines table + routine_id column on workouts
# ===========================================================================


class TestRoutinesSchema:
    """Schema migration for routines table and routine_id column."""

    def test_routines_table_exists(self, conn: sqlite3.Connection) -> None:
        """The routines table exists with the defined columns."""
        cursor = conn.execute("PRAGMA table_info(routines)")
        cols = {row[1]: row[2] for row in cursor.fetchall()}
        assert cols["id"] == "TEXT"
        assert cols["title"] == "TEXT"
        assert cols["folder_id"] == "INTEGER"
        assert cols["created_at"] == "TEXT"
        assert cols["updated_at"] == "TEXT"

    def test_routines_pk_is_id(self, conn: sqlite3.Connection) -> None:
        """routines.id is the primary key."""
        cursor = conn.execute("PRAGMA table_info(routines)")
        pk_cols = [row[1] for row in cursor.fetchall() if row[5] == 1]
        assert pk_cols == ["id"]

    def test_workouts_has_routine_id_column(self, conn: sqlite3.Connection) -> None:
        """workouts table has a nullable routine_id column."""
        cursor = conn.execute("PRAGMA table_info(workouts)")
        cols = {row[1]: row[2] for row in cursor.fetchall()}
        assert "routine_id" in cols
        assert cols["routine_id"] == "TEXT"

    def test_routine_id_nullable(self, conn: sqlite3.Connection) -> None:
        """routine_id column allows NULL values."""
        cursor = conn.execute("PRAGMA table_info(workouts)")
        for row in cursor.fetchall():
            if row[1] == "routine_id":
                # Column 3 (index 3) is `notnull` — 0 means nullable
                assert row[3] == 0, "routine_id should be nullable"
                return
        pytest.fail("routine_id column not found")

    def test_create_tables_is_idempotent_with_routines(
        self, conn: sqlite3.Connection
    ) -> None:
        """Calling create_tables twice does not raise an error and tables exist."""
        create_tables(conn)  # second call
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        assert "routines" in tables

    def test_no_fk_on_routine_id(self, conn: sqlite3.Connection) -> None:
        """No FK constraint on workouts.routine_id — orphaned IDs are allowed."""
        # Insert a workout with a routine_id that doesn't exist in routines
        upsert_workout(
            conn,
            {
                "id": "orphan_w",
                "title": "Orphan Workout",
                "description": "",
                "start_time": "2024-01-01T00:00:00Z",
                "end_time": None,
                "routine_id": "nonexistent_routine",
            },
            [],
        )
        row = conn.execute(
            "SELECT routine_id FROM workouts WHERE id = ?", ("orphan_w",)
        ).fetchone()
        assert row["routine_id"] == "nonexistent_routine"


# ===========================================================================
# Adapter — routine_id passthrough in _raw_workout_to_dict
# ===========================================================================


class TestRawWorkoutToDictRoutineId:
    """_raw_workout_to_dict extracts routine_id from raw event data."""

    def test_routine_id_present(self) -> None:
        """When routine_id is in the raw dict, it is passed through."""
        raw = {
            "id": "w001",
            "title": "Push Day",
            "routine_id": "ABC123",
            "description": "",
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": None,
            "updated_at": "2024-01-01T01:00:00Z",
            "created_at": "2024-01-01T00:00:00Z",
            "exercises": [],
        }
        # Use HevyClient.get_events which internally calls _raw_workout_to_dict
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_sdk.return_value._request.return_value = _mock_json_response(
                _raw_api_response([{"type": "updated", "workout": raw}])
            )
            client = HevyClient(api_key="test-key")
            result = client.get_events(since="2024-01-01T00:00:00Z")
            workout = result.events[0].workout
            assert workout is not None
            assert workout["routine_id"] == "ABC123"

    def test_routine_id_absent_is_none(self) -> None:
        """When routine_id is missing, the output has routine_id as None."""
        raw = {
            "id": "w002",
            "title": "Pull Day",
            "description": "",
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": None,
            "updated_at": "2024-01-01T01:00:00Z",
            "created_at": "2024-01-01T00:00:00Z",
            "exercises": [],
        }
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_sdk.return_value._request.return_value = _mock_json_response(
                _raw_api_response([{"type": "updated", "workout": raw}])
            )
            client = HevyClient(api_key="test-key")
            result = client.get_events(since="2024-01-01T00:00:00Z")
            workout = result.events[0].workout
            assert workout is not None
            assert workout["routine_id"] is None

    def test_routine_id_none_in_raw(self) -> None:
        """When routine_id is explicitly None, output is None."""
        raw = {
            "id": "w003",
            "title": "Leg Day",
            "routine_id": None,
            "description": "",
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": None,
            "updated_at": "2024-01-01T01:00:00Z",
            "created_at": "2024-01-01T00:00:00Z",
            "exercises": [],
        }
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_sdk.return_value._request.return_value = _mock_json_response(
                _raw_api_response([{"type": "updated", "workout": raw}])
            )
            client = HevyClient(api_key="test-key")
            result = client.get_events(since="2024-01-01T00:00:00Z")
            workout = result.events[0].workout
            assert workout is not None
            assert workout["routine_id"] is None


# ===========================================================================
# HevyClient — _routine_to_dict and get_routines
# ===========================================================================


class TestRoutineToDict:
    """_routine_to_dict converts SDK Routine model to domain dict."""

    def test_converts_all_fields(self) -> None:
        """Routine dict has id, title, folder_id, created_at, updated_at."""
        from darth_gain.hevy.client import _routine_to_dict

        mock_routine = MagicMock()
        mock_routine.id = "r001"
        mock_routine.title = "Push / Pull / Legs"
        mock_routine.folder_id = 1
        mock_routine.created_at = "2024-01-01T00:00:00Z"
        mock_routine.updated_at = "2024-01-02T00:00:00Z"

        result = _routine_to_dict(mock_routine)
        assert result["id"] == "r001"
        assert result["title"] == "Push / Pull / Legs"
        assert result["folder_id"] == 1
        assert result["created_at"] == "2024-01-01T00:00:00Z"
        assert result["updated_at"] == "2024-01-02T00:00:00Z"

    def test_folder_id_none(self) -> None:
        """When folder_id is None, it maps to None."""
        from darth_gain.hevy.client import _routine_to_dict

        mock_routine = MagicMock()
        mock_routine.id = "r002"
        mock_routine.title = "My Routine"
        mock_routine.folder_id = None
        mock_routine.created_at = "2024-01-01T00:00:00Z"
        mock_routine.updated_at = "2024-01-02T00:00:00Z"

        result = _routine_to_dict(mock_routine)
        assert result["folder_id"] is None


class TestGetRoutines:
    """HevyClient.get_routines paginates routines and returns domain dicts."""

    def test_fetches_all_routines_single_page(self) -> None:
        """get_routines returns all routines from a single page."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            _setup_routines_mock(mock_sdk, ["r001", "r002", "r003"], page=1, page_count=1)
            client = HevyClient(api_key="test-key")

            result = client.get_routines()

            assert len(result) == 3
            assert result[0]["id"] == "r001"
            assert result[1]["id"] == "r002"
            assert result[2]["id"] == "r003"

    def test_paginates_multiple_pages(self) -> None:
        """get_routines fetches all pages and merges results."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            page1 = _sdk_routines_page(
                [_sdk_routine("r001", "Push"), _sdk_routine("r002", "Pull")],
                page=1, page_count=2,
            )
            page2 = _sdk_routines_page(
                [_sdk_routine("r003", "Legs")],
                page=2, page_count=2,
            )
            mock_sdk.return_value.routines.get_routines.side_effect = [page1, page2]

            client = HevyClient(api_key="test-key")
            result = client.get_routines()

            assert len(result) == 3
            assert result[0]["id"] == "r001"
            assert result[1]["id"] == "r002"
            assert result[2]["id"] == "r003"
            assert mock_sdk.return_value.routines.get_routines.call_count == 2

    def test_empty_routines_returns_empty_list(self) -> None:
        """When no routines exist, returns empty list."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            _setup_routines_mock(mock_sdk, [], page=1, page_count=1)
            client = HevyClient(api_key="test-key")

            result = client.get_routines()

            assert result == []

    def test_single_page_no_extra_call(self) -> None:
        """When page_count is 1, only one API call is made."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            _setup_routines_mock(mock_sdk, ["r001"], page=1, page_count=1)
            client = HevyClient(api_key="test-key")

            result = client.get_routines()

            assert len(result) == 1
            mock_sdk.return_value.routines.get_routines.assert_called_once()

    def test_uses_default_page_size(self) -> None:
        """get_routines calls with page_size=10 by default."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            _setup_routines_mock(mock_sdk, ["r001"], page=1, page_count=1)
            client = HevyClient(api_key="test-key")

            client.get_routines()

            mock_sdk.return_value.routines.get_routines.assert_called_once_with(
                page=1, page_size=10
            )


# ===========================================================================
# RoutineRepo — upsert and query operations
# ===========================================================================


class TestRoutineRepo:
    """Routine repository CRUD operations."""

    SAMPLE_ROUTINES = [
        {"id": "r001", "title": "Push", "folder_id": 1, "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-02T00:00:00Z"},
        {"id": "r002", "title": "Pull", "folder_id": 1, "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-02T00:00:00Z"},
        {"id": "r003", "title": "Legs", "folder_id": None, "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-02T00:00:00Z"},
    ]

    def test_upsert_routine_inserts_new(self, conn: sqlite3.Connection) -> None:
        """A single routine is inserted into the routines table."""
        upsert_routine(conn, self.SAMPLE_ROUTINES[0])

        row = conn.execute(
            "SELECT id, title, folder_id FROM routines WHERE id = ?", ("r001",)
        ).fetchone()
        assert row["title"] == "Push"
        assert row["folder_id"] == 1

    def test_upsert_routine_replaces_existing(self, conn: sqlite3.Connection) -> None:
        """Upserting with the same id replaces the existing row."""
        upsert_routine(conn, self.SAMPLE_ROUTINES[0])
        upsert_routine(conn, {"id": "r001", "title": "Push v2", "folder_id": 2,
                              "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-03T00:00:00Z"})

        row = conn.execute(
            "SELECT title, folder_id FROM routines WHERE id = ?", ("r001",)
        ).fetchone()
        assert row["title"] == "Push v2"
        assert row["folder_id"] == 2

    def test_upsert_routines_bulk_inserts(self, conn: sqlite3.Connection) -> None:
        """Bulk upsert inserts all routines."""
        upsert_routines(conn, self.SAMPLE_ROUTINES)

        rows = conn.execute(
            "SELECT id, title FROM routines ORDER BY title"
        ).fetchall()
        assert len(rows) == 3

    def test_get_routines_returns_all_sorted_by_title(
        self, conn: sqlite3.Connection
    ) -> None:
        """get_routines returns all routines ordered by title."""
        upsert_routines(conn, self.SAMPLE_ROUTINES)

        result = get_routines(conn)

        assert len(result) == 3
        # Ordered by title: Legs, Pull, Push
        assert result[0]["title"] == "Legs"
        assert result[1]["title"] == "Pull"
        assert result[2]["title"] == "Push"

    def test_get_routines_returns_dicts_with_all_fields(
        self, conn: sqlite3.Connection
    ) -> None:
        """get_routines returns complete routine dicts."""
        upsert_routines(conn, self.SAMPLE_ROUTINES)

        result = get_routines(conn)

        r = result[0]  # first by title
        assert "id" in r
        assert "title" in r
        assert "folder_id" in r
        assert "created_at" in r
        assert "updated_at" in r

    def test_get_routines_empty(self, conn: sqlite3.Connection) -> None:
        """get_routines returns empty list when no routines exist."""
        result = get_routines(conn)
        assert result == []

    def test_get_routine_returns_single(self, conn: sqlite3.Connection) -> None:
        """get_routine returns a single routine by id."""
        upsert_routines(conn, self.SAMPLE_ROUTINES)

        result = get_routine(conn, "r001")
        assert result is not None
        assert result["title"] == "Push"

    def test_get_routine_nonexistent(self, conn: sqlite3.Connection) -> None:
        """get_routine returns None for non-existent id."""
        result = get_routine(conn, "nonexistent")
        assert result is None

    def test_upsert_routines_replaces_updated(
        self, conn: sqlite3.Connection
    ) -> None:
        """Upserting with same ids replaces titles (INSERT OR REPLACE)."""
        upsert_routines(conn, self.SAMPLE_ROUTINES)
        updated = [
            {"id": "r001", "title": "Push (Updated)", "folder_id": 1,
             "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-03T00:00:00Z"},
        ]
        upsert_routines(conn, updated)

        row = conn.execute(
            "SELECT title FROM routines WHERE id = ?", ("r001",)
        ).fetchone()
        assert row["title"] == "Push (Updated)"
        # Other routines still exist
        cnt = conn.execute("SELECT COUNT(*) AS cnt FROM routines").fetchone()["cnt"]
        assert cnt == 3


# ===========================================================================
# upsert_workout — routine_id column integration
# ===========================================================================


class TestUpsertWorkoutRoutineId:
    """upsert_workout persists routine_id in the workouts table."""

    def test_upsert_workout_with_routine_id(self, conn: sqlite3.Connection) -> None:
        """A workout upserted with routine_id persists the value."""
        upsert_workout(
            conn,
            {"id": "w_routine", "title": "Routine Workout", "description": "",
             "start_time": "2024-01-01T00:00:00Z", "end_time": None,
             "routine_id": "r001"},
            [],
        )
        row = conn.execute(
            "SELECT routine_id FROM workouts WHERE id = ?", ("w_routine",)
        ).fetchone()
        assert row["routine_id"] == "r001"

    def test_upsert_workout_without_routine_id(self, conn: sqlite3.Connection) -> None:
        """A workout upserted without routine_id stores NULL."""
        upsert_workout(
            conn,
            {"id": "w_no_routine", "title": "No Routine", "description": "",
             "start_time": "2024-01-01T00:00:00Z", "end_time": None},
            [],
        )
        row = conn.execute(
            "SELECT routine_id FROM workouts WHERE id = ?", ("w_no_routine",)
        ).fetchone()
        assert row["routine_id"] is None

    def test_upsert_workout_replaces_routine_id(self, conn: sqlite3.Connection) -> None:
        """Re-upserting a workout updates routine_id."""
        upsert_workout(
            conn,
            {"id": "w001", "title": "Workout", "description": "",
             "start_time": "2024-01-01T00:00:00Z", "end_time": None,
             "routine_id": "r001"},
            [],
        )
        upsert_workout(
            conn,
            {"id": "w001", "title": "Workout", "description": "",
             "start_time": "2024-01-01T00:00:00Z", "end_time": None,
             "routine_id": "r002"},
            [],
        )
        row = conn.execute(
            "SELECT routine_id FROM workouts WHERE id = ?", ("w001",)
        ).fetchone()
        assert row["routine_id"] == "r002"


# ===========================================================================
# Sync — routine integration
# ===========================================================================


class TestSyncRoutines:
    """Sync fetches and persists routines alongside events."""

    def test_routines_fetched_before_events(self, conn: sqlite3.Connection) -> None:
        """get_routines is called and routines are stored during sync."""
        api = MockHevyClient()
        api.events_pages = [
            EventsPage(page=1, page_count=1, total_count=0, events=[]),
        ]
        api.routines = [
            {"id": "r001", "title": "Push", "folder_id": None,
             "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-02T00:00:00Z"},
        ]
        cfg = _cfg(dry_run=True)

        sync(api, conn, cfg)

        # Routines should be stored in the DB
        stored = get_routines(conn)
        assert len(stored) == 1
        assert stored[0]["id"] == "r001"
        assert stored[0]["title"] == "Push"

    def test_routine_id_persisted_during_sync(self, conn: sqlite3.Connection) -> None:
        """A workout with routine_id persists routine_id during sync."""
        api = MockHevyClient()
        api.events_pages = [
            EventsPage(
                page=1,
                page_count=1,
                total_count=1,
                events=[
                    WorkoutEvent(
                        index=0,
                        type="updated",
                        workout={
                            "id": "w001",
                            "title": "Push Day",
                            "description": "",
                            "start_time": "2024-01-01T00:00:00Z",
                            "end_time": None,
                            "updated_at": "2024-01-01T01:00:00Z",
                            "created_at": "2024-01-01T00:00:00Z",
                            "routine_id": "r001",
                            "exercises": [],
                        },
                    ),
                ],
            )
        ]
        api.routines = [
            {"id": "r001", "title": "Push", "folder_id": None,
             "created_at": "2024-01-01T00:00:00Z", "updated_at": "2024-01-02T00:00:00Z"},
        ]
        cfg = _cfg(dry_run=True)

        sync(api, conn, cfg)

        row = conn.execute(
            "SELECT routine_id FROM workouts WHERE id = ?", ("w001",)
        ).fetchone()
        assert row["routine_id"] == "r001"

    def test_routines_empty_does_not_crash(self, conn: sqlite3.Connection) -> None:
        """Sync handles the case when user has no routines."""
        api = MockHevyClient()
        api.events_pages = [
            EventsPage(page=1, page_count=1, total_count=0, events=[]),
        ]
        api.routines = []
        cfg = _cfg(dry_run=True)

        sync(api, conn, cfg)

        stored = get_routines(conn)
        assert stored == []

    def test_workout_without_routine_id_syncs_normally(
        self, conn: sqlite3.Connection
    ) -> None:
        """A workout without routine_id is processed normally."""
        api = MockHevyClient()
        api.events_pages = [
            EventsPage(
                page=1,
                page_count=1,
                total_count=1,
                events=[
                    WorkoutEvent(
                        index=0,
                        type="updated",
                        workout={
                            "id": "w001",
                            "title": "Leg Day",
                            "description": "",
                            "start_time": "2024-01-01T00:00:00Z",
                            "end_time": None,
                            "updated_at": "2024-01-01T01:00:00Z",
                            "created_at": "2024-01-01T00:00:00Z",
                            "exercises": [],
                        },
                    ),
                ],
            )
        ]
        api.routines = []
        cfg = _cfg(dry_run=True)

        sync(api, conn, cfg)

        row = conn.execute(
            "SELECT id, routine_id FROM workouts WHERE id = ?", ("w001",)
        ).fetchone()
        assert row["routine_id"] is None


# ===========================================================================
# MockHevyClient — get_routines tracking
# ===========================================================================


class TestMockHevyClientRoutines:
    """MockHevyClient supports get_routines with call tracking."""

    def test_get_routines_returns_set_data(self) -> None:
        """MockHevyClient.get_routines returns pre-configured routines."""
        api = MockHevyClient()
        api.routines = [
            {"id": "r001", "title": "Push", "folder_id": None,
             "created_at": "", "updated_at": ""},
        ]

        result = api.get_routines()

        assert len(result) == 1
        assert result[0]["id"] == "r001"

    def test_get_routines_empty_by_default(self) -> None:
        """MockHevyClient.get_routines returns empty list by default."""
        api = MockHevyClient()
        result = api.get_routines()
        assert result == []

    def test_get_routines_tracks_calls(self) -> None:
        """MockHevyClient tracks calls to get_routines."""
        api = MockHevyClient()
        api.routines = [
            {"id": "r001", "title": "Push", "folder_id": None,
             "created_at": "", "updated_at": ""},
        ]
        api.get_routines()
        api.get_routines()

        assert len(api.get_routines_calls) == 2


# ===========================================================================
# Helper factories for SDK mocks
# ===========================================================================


def _mock_json_response(data: dict) -> MagicMock:
    """Build a mock _request return value with .json() method."""
    resp = MagicMock()
    resp.json.return_value = data
    return resp


def _raw_api_response(workouts: list, page: int = 1, page_count: int = 1) -> dict:
    """Simulate the raw /v1/workouts/events JSON response."""
    return {"page": page, "page_count": page_count, "workouts": workouts}


def _sdk_routine(r_id: str, title: str) -> MagicMock:
    """Create a mock SDK Routine model."""
    r = MagicMock()
    r.id = r_id
    r.title = title
    r.folder_id = None
    r.created_at = "2024-01-01T00:00:00Z"
    r.updated_at = "2024-01-02T00:00:00Z"
    return r


def _sdk_routines_page(
    routines: list, page: int = 1, page_count: int = 1,
) -> MagicMock:
    """Create a mock PaginatedRoutines SDK response."""
    resp = MagicMock()
    resp.page = page
    resp.page_count = page_count
    resp.routines = routines
    return resp


def _setup_routines_mock(
    mock_sdk: MagicMock, routine_ids: list[str], page: int, page_count: int,
) -> None:
    """Configure mock SDK to return routines with given IDs."""
    routines = [_sdk_routine(rid, f"Routine {rid}") for rid in routine_ids]
    mock_sdk.return_value.routines.get_routines.return_value = _sdk_routines_page(
        routines, page=page, page_count=page_count,
    )


def _cfg(dry_run: bool = False) -> Any:
    """Create a minimal Config for sync tests."""
    from darth_gain.config import Config
    return Config(hevy_api_key="test", dry_run=dry_run, refresh_templates=False)
