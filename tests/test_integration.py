"""Integration tests: config → sync → DB with mocked API responses.

Tests the full end-to-end flow of the DARTH-GAIN ingest pipeline,
covering all spec scenarios for ingestion, caching, and error handling.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from darth_gain.config import Config
from darth_gain.db.engine import create_engine, create_tables
from darth_gain.db.repo import (
    get_sync_meta,
    get_template_count,
    get_templates,
    upsert_workout,
)
from darth_gain.hevy.sync import sync
from tests.conftest import EventsPage, MockHevyClient, WorkoutEvent


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def conn() -> object:  # noqa: F811
    """In-memory SQLite connection with schema for integration tests."""
    c = create_engine(":memory:")
    create_tables(c)
    return c


@pytest.fixture
def sample_config() -> Config:
    """A base Config with dry_run=False and a dummy API key."""
    return Config(
        hevy_api_key="test-integration-key",
        dry_run=False,
    )


# ===========================================================================
# Integration: First Sync (Full Fetch)
# ===========================================================================


class TestFirstSync:
    """First sync with an empty database — full fetch from scratch."""

    def test_full_sync_multiple_pages(self, conn: object, sample_config: Config) -> None:
        """A first sync with multiple pages inserts all workouts into the DB."""
        api = MockHevyClient()
        api.templates = [
            {
                "id": "t001", "title": "Bench Press", "type": "strength",
                "primary_muscle_group": "Chest", "other_muscle_groups": "[]",
                "equipment": "", "is_custom": 0,
            },
        ]
        api.events_pages = [
            EventsPage(page=1, page_count=2, total_count=3, events=[
                WorkoutEvent(index=0, type="updated", workout={
                    "id": "w001", "title": "Push Day", "description": "Chest",
                    "start_time": "2024-06-01T08:00:00Z",
                    "end_time": "2024-06-01T09:00:00Z",
                    "updated_at": "2024-06-01T10:00:00Z",
                    "created_at": "2024-05-01T08:00:00Z",
                    "exercises": [
                        {
                            "exercise_template_id": "t001",
                            "title": "Bench Press",
                            "notes": "",
                            "sort_order": 0,
                            "sets": [
                                {"set_index": 0, "type": "normal", "weight_kg": 80.0,
                                 "reps": 10, "distance_meters": None,
                                 "duration_seconds": None, "rpe": None},
                            ],
                        },
                    ],
                }),
                WorkoutEvent(index=1, type="updated", workout={
                    "id": "w002", "title": "Arm Day", "description": "Biceps",
                    "start_time": "2024-06-01T06:00:00Z",
                    "end_time": "2024-06-01T07:00:00Z",
                    "updated_at": "2024-06-01T07:00:00Z",
                    "created_at": "2024-05-01T06:00:00Z",
                    "exercises": [],
                }),
            ]),
            EventsPage(page=2, page_count=2, total_count=3, events=[
                WorkoutEvent(index=0, type="deleted", workout={
                    "id": "w002", "title": "Arm Day", "description": "Biceps",
                    "start_time": "2024-06-01T06:00:00Z", "end_time": None,
                    "updated_at": "2024-06-01T07:00:00Z",
                    "created_at": "2024-05-01T06:00:00Z", "exercises": [],
                }),
                WorkoutEvent(index=1, type="updated", workout={
                    "id": "w003", "title": "Pull Day", "description": "Back",
                    "start_time": "2024-06-02T08:00:00Z",
                    "end_time": "2024-06-02T09:00:00Z",
                    "updated_at": "2024-06-02T10:00:00Z",
                    "created_at": "2024-05-02T08:00:00Z",
                    "exercises": [],
                }),
            ]),
        ]

        result = sync(api, conn, sample_config)

        # Database should have workouts from both pages
        rows = conn.execute("SELECT id, title FROM workouts ORDER BY id").fetchall()
        assert len(rows) == 3
        assert rows[0]["id"] == "w001"
        assert rows[1]["id"] == "w002"
        assert rows[2]["id"] == "w003"

        # w002 should be soft-deleted (was created on page 1, then deleted on page 2)
        deleted = conn.execute(
            "SELECT is_deleted FROM workouts WHERE id = ?", ("w002",)
        ).fetchone()
        assert deleted["is_deleted"] == 1

        # w001 should have its exercise
        exercises = conn.execute(
            "SELECT exercise_template_id, title FROM exercises WHERE workout_id = ?",
            ("w001",),
        ).fetchall()
        assert len(exercises) == 1
        assert exercises[0]["exercise_template_id"] == "t001"

        # w003 should have zero exercises
        ex3 = conn.execute(
            "SELECT COUNT(*) as cnt FROM exercises WHERE workout_id = ?",
            ("w003",),
        ).fetchone()
        assert ex3["cnt"] == 0

        # Templates should have been cached
        assert get_template_count(conn) == 1

        # Sync result should reflect the counts
        # w001, w002, w003 all upserted → 3 updated
        # w002 later deleted → 1 deleted
        assert result.updated == 3
        assert result.deleted == 1
        assert result.errors == 0
        assert result.dry_run is False

    def test_first_sync_with_templates(self, conn: object, sample_config: Config) -> None:
        """Templates are eagerly fetched on first sync and cached in DB."""
        api = MockHevyClient()
        api.templates = [
            {"id": "t001", "title": "Bench Press", "type": "strength",
             "primary_muscle_group": "Chest", "other_muscle_groups": "[]",
             "equipment": "", "is_custom": 0},
            {"id": "t002", "title": "Pull Up", "type": "strength",
             "primary_muscle_group": "Back", "other_muscle_groups": '["Biceps"]',
             "equipment": "", "is_custom": 0},
        ]
        api.events_pages = [
            EventsPage(page=1, page_count=1, total_count=0, events=[]),
        ]

        sync(api, conn, sample_config)

        templates = get_templates(conn)
        assert len(templates) == 2
        assert templates[0]["title"] == "Bench Press"
        assert templates[1]["title"] == "Pull Up"

    def test_no_events_first_sync(self, conn: object, sample_config: Config) -> None:
        """An empty first sync still updates last_sync_at."""
        api = MockHevyClient()
        api.templates = []
        api.events_pages = [
            EventsPage(page=1, page_count=1, total_count=0, events=[]),
        ]

        result = sync(api, conn, sample_config)

        assert result.updated == 0
        assert result.deleted == 0
        assert get_sync_meta(conn, "last_sync_at") is not None


# ===========================================================================
# Integration: Delta Sync
# ===========================================================================


class TestDeltaSync:
    """Subsequent syncs use stored last_sync_at and cached templates."""

    def test_delta_sync_no_new_events(self, conn: object, sample_config: Config) -> None:
        """A delta sync with no new events updates last_sync_at with no changes."""
        # Pre-populate: simulate a previous sync
        from darth_gain.db.repo import set_sync_meta, upsert_templates
        set_sync_meta(conn, "last_sync_at", "2024-06-15T12:00:00Z")
        upsert_templates(conn, [
            {"id": "t001", "title": "Bench Press", "type": "strength",
             "primary_muscle_group": "Chest", "other_muscle_groups": "[]",
             "equipment": "", "is_custom": 0},
        ])

        api = MockHevyClient()
        api.events_pages = [
            EventsPage(page=1, page_count=1, total_count=0, events=[]),
        ]

        before = datetime.now(timezone.utc)
        result = sync(api, conn, sample_config)
        after = datetime.now(timezone.utc)

        assert result.updated == 0
        assert result.deleted == 0

        # last_sync_at should be updated
        meta = get_sync_meta(conn, "last_sync_at")
        assert meta is not None
        ts = datetime.fromisoformat(meta.replace("Z", "+00:00"))
        assert before.replace(microsecond=0) <= ts <= after.replace(microsecond=0)

        # No template API calls should have been made
        assert len(api.get_templates_calls) == 0

    def test_delta_sync_mixed_events(self, conn: object, sample_config: Config) -> None:
        """Delta sync with mixed updated/deleted events processes both."""
        from darth_gain.db.repo import set_sync_meta, upsert_templates

        # Seed DB with a workout that will be soft-deleted
        upsert_workout(
            conn,
            {"id": "w099", "title": "To Delete", "description": "",
             "start_time": "2024-06-01T08:00:00Z", "end_time": None},
            [],
        )
        set_sync_meta(conn, "last_sync_at", "2024-06-15T12:00:00Z")
        upsert_templates(conn, [
            {"id": "t001", "title": "Bench Press", "type": "strength",
             "primary_muscle_group": "Chest", "other_muscle_groups": "[]",
             "equipment": "", "is_custom": 0},
        ])

        api = MockHevyClient()
        api.events_pages = [
            EventsPage(page=1, page_count=1, total_count=3, events=[
                WorkoutEvent(index=0, type="updated", workout={
                    "id": "w100", "title": "New Push", "description": "",
                    "start_time": "2024-06-16T08:00:00Z", "end_time": None,
                    "updated_at": "2024-06-16T10:00:00Z",
                    "created_at": "2024-06-16T08:00:00Z", "exercises": [],
                }),
                WorkoutEvent(index=1, type="deleted", workout={
                    "id": "w099", "title": "To Delete", "description": "",
                    "start_time": "2024-06-01T08:00:00Z", "end_time": None,
                    "updated_at": "2024-06-01T10:00:00Z",
                    "created_at": "2024-06-01T08:00:00Z", "exercises": [],
                }),
                WorkoutEvent(index=2, type="updated", workout={
                    "id": "w101", "title": "New Pull", "description": "",
                    "start_time": "2024-06-16T12:00:00Z", "end_time": None,
                    "updated_at": "2024-06-16T14:00:00Z",
                    "created_at": "2024-06-16T12:00:00Z", "exercises": [],
                }),
            ]),
        ]

        result = sync(api, conn, sample_config)

        assert result.updated == 2
        assert result.deleted == 1
        assert result.errors == 0

        # Verify DB state
        rows = conn.execute(
            "SELECT id, is_deleted FROM workouts ORDER BY id"
        ).fetchall()
        assert rows[0]["id"] == "w099"
        assert rows[0]["is_deleted"] == 1
        assert rows[1]["id"] == "w100"
        assert rows[1]["is_deleted"] == 0
        assert rows[2]["id"] == "w101"
        assert rows[2]["is_deleted"] == 0


# ===========================================================================
# Integration: Error Handling
# ===========================================================================


class TestErrorHandling:
    """Error isolation and skip-and-continue behavior."""

    def test_skip_and_continue_on_workout_error(
        self, conn: object, sample_config: Config
    ) -> None:
        """A single failing workout doesn't stop the sync."""
        from darth_gain.db.repo import upsert_templates
        upsert_templates(conn, [
            {"id": "t001", "title": "Bench Press", "type": "strength",
             "primary_muscle_group": "Chest", "other_muscle_groups": "[]",
             "equipment": "", "is_custom": 0},
        ])

        api = MockHevyClient()
        api.events_pages = [
            EventsPage(page=1, page_count=1, total_count=3, events=[
                WorkoutEvent(index=0, type="updated", workout={
                    "id": "w001", "title": "Good One", "description": "",
                    "start_time": "2024-06-01T08:00:00Z", "end_time": None,
                    "updated_at": "2024-06-01T10:00:00Z",
                    "created_at": "2024-06-01T08:00:00Z", "exercises": [],
                }),
                WorkoutEvent(index=1, type="updated", workout={
                    "id": "w002", "title": "Bad One", "description": "",
                    "start_time": "2024-06-01T08:00:00Z", "end_time": None,
                    "updated_at": "2024-06-01T10:00:00Z",
                    "created_at": "2024-06-01T08:00:00Z", "exercises": [],
                }),
                WorkoutEvent(index=2, type="updated", workout={
                    "id": "w003", "title": "Also Good", "description": "",
                    "start_time": "2024-06-01T08:00:00Z", "end_time": None,
                    "updated_at": "2024-06-01T10:00:00Z",
                    "created_at": "2024-06-01T08:00:00Z", "exercises": [],
                }),
            ]),
        ]

        # Make w002 fail
        from unittest.mock import patch

        def failing_upsert(w_conn, workout, exercises):
            if workout.get("id") == "w002":
                raise RuntimeError("Simulated DB failure")
            return upsert_workout(w_conn, workout, exercises)

        with patch("darth_gain.hevy.sync.upsert_workout", side_effect=failing_upsert):
            result = sync(api, conn, sample_config)

        assert result.updated == 2  # Only w001 and w003 succeeded
        assert result.errors == 1  # w002 failed

        # w001 and w003 should be in DB
        assert conn.execute(
            "SELECT id FROM workouts WHERE id = ?", ("w001",)
        ).fetchone() is not None
        assert conn.execute(
            "SELECT id FROM workouts WHERE id = ?", ("w003",)
        ).fetchone() is not None

    def test_all_workouts_fail_no_last_sync_update(
        self, conn: object, sample_config: Config
    ) -> None:
        """When ALL events fail, last_sync_at is NOT updated."""
        from darth_gain.db.repo import set_sync_meta, upsert_templates
        set_sync_meta(conn, "last_sync_at", "2024-06-15T12:00:00Z")
        upsert_templates(conn, [
            {"id": "t001", "title": "Bench Press", "type": "strength",
             "primary_muscle_group": "Chest", "other_muscle_groups": "[]",
             "equipment": "", "is_custom": 0},
        ])

        api = MockHevyClient()
        api.events_pages = [
            EventsPage(page=1, page_count=1, total_count=2, events=[
                WorkoutEvent(index=0, type="updated", workout={
                    "id": "w001", "title": "Fail", "description": "",
                    "start_time": "2024-06-01T08:00:00Z", "end_time": None,
                    "updated_at": "2024-06-01T10:00:00Z",
                    "created_at": "2024-06-01T08:00:00Z", "exercises": [],
                }),
                WorkoutEvent(index=1, type="updated", workout={
                    "id": "w002", "title": "Also Fail", "description": "",
                    "start_time": "2024-06-01T08:00:00Z", "end_time": None,
                    "updated_at": "2024-06-01T10:00:00Z",
                    "created_at": "2024-06-01T08:00:00Z", "exercises": [],
                }),
            ]),
        ]

        from unittest.mock import patch
        with patch(
            "darth_gain.hevy.sync.upsert_workout",
            side_effect=RuntimeError("DB failure"),
        ):
            result = sync(api, conn, sample_config)

        assert result.errors == 2
        # last_sync_at should remain unchanged
        assert get_sync_meta(conn, "last_sync_at") == "2024-06-15T12:00:00Z"


# ===========================================================================
# Integration: Template Cache
# ===========================================================================


class TestTemplateCache:
    """Exercise template caching behavior across sync runs."""

    def test_templates_cached_no_refetch(self, conn: object, sample_config: Config) -> None:
        """Templates cached from a previous sync are not re-fetched."""
        from darth_gain.db.repo import set_sync_meta, upsert_templates

        upsert_templates(conn, [
            {"id": "t001", "title": "Bench Press", "type": "strength",
             "primary_muscle_group": "Chest", "other_muscle_groups": "[]",
             "equipment": "", "is_custom": 0},
        ])
        set_sync_meta(conn, "last_sync_at", "2024-06-15T12:00:00Z")

        api = MockHevyClient()
        api.events_pages = [
            EventsPage(page=1, page_count=1, total_count=0, events=[]),
        ]

        sync(api, conn, sample_config)

        # No template fetch calls
        assert len(api.get_templates_calls) == 0
        # Cache still has the template
        assert get_template_count(conn) == 1

    def test_refresh_templates_flag(self, conn: object, sample_config: Config) -> None:
        """--refresh-templates forces a template re-fetch even when cached."""
        from darth_gain.db.repo import upsert_templates

        upsert_templates(conn, [
            {"id": "t001", "title": "Old Bench", "type": "strength",
             "primary_muscle_group": "Chest", "other_muscle_groups": "[]",
             "equipment": "", "is_custom": 0},
        ])

        api = MockHevyClient()
        api.events_pages = [
            EventsPage(page=1, page_count=1, total_count=0, events=[]),
        ]
        api.templates = [
            {"id": "t001", "title": "New Bench", "type": "strength",
             "primary_muscle_group": "Chest", "other_muscle_groups": "[]",
             "equipment": "", "is_custom": 0},
        ]

        refresh_config = Config(
            hevy_api_key="test-key",
            refresh_templates=True,
            dry_run=False,
        )
        sync(api, conn, refresh_config)

        # Should have fetched
        assert len(api.get_templates_calls) >= 1
        # Cache should have new title
        cached = get_templates(conn)
        assert cached[0]["title"] == "New Bench"


# ===========================================================================
# Integration: Dry Run Mode
# ===========================================================================


class TestDryRun:
    """Dry-run mode fetches data but does not persist metadata."""

    def test_dry_run_does_not_persist_metadata(
        self, conn: object, sample_config: Config
    ) -> None:
        """Dry-run mode does not write last_sync_at or templates."""
        api = MockHevyClient()
        api.events_pages = [
            EventsPage(page=1, page_count=1, total_count=1, events=[
                WorkoutEvent(index=0, type="updated", workout={
                    "id": "w001", "title": "Dry Run Workout", "description": "",
                    "start_time": "2024-06-01T08:00:00Z", "end_time": None,
                    "updated_at": "2024-06-01T10:00:00Z",
                    "created_at": "2024-06-01T08:00:00Z", "exercises": [],
                }),
            ]),
        ]
        dry_config = Config(
            hevy_api_key="test-key",
            dry_run=True,
        )

        result = sync(api, conn, dry_config)

        assert result.updated == 1
        assert result.dry_run is True

        # Workouts ARE upserted (the connection is in-memory, discarded after)
        row = conn.execute(
            "SELECT id FROM workouts WHERE id = ?", ("w001",)
        ).fetchone()
        assert row is not None
        assert row["id"] == "w001"

        # But metadata should NOT be written
        assert get_sync_meta(conn, "last_sync_at") is None


# ===========================================================================
# Integration: Sync Metadata
# ===========================================================================


class TestSyncMetadata:
    """last_sync_at is updated on successful sync."""

    def test_metadata_updated_on_success(
        self, conn: object, sample_config: Config
    ) -> None:
        """After a successful sync, last_sync_at is set to current time."""
        from darth_gain.db.repo import upsert_templates
        upsert_templates(conn, [
            {"id": "t001", "title": "Bench Press", "type": "strength",
             "primary_muscle_group": "Chest", "other_muscle_groups": "[]",
             "equipment": "", "is_custom": 0},
        ])

        api = MockHevyClient()
        api.events_pages = [
            EventsPage(page=1, page_count=1, total_count=0, events=[]),
        ]

        before = datetime.now(timezone.utc)
        sync(api, conn, sample_config)
        after = datetime.now(timezone.utc)

        meta = get_sync_meta(conn, "last_sync_at")
        assert meta is not None
        ts = datetime.fromisoformat(meta.replace("Z", "+00:00"))
        assert before.replace(microsecond=0) <= ts <= after.replace(microsecond=0)
