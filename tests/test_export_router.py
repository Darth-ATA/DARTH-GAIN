"""Contract tests for export router."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import freezegun
from fastapi.testclient import TestClient

from darth_gain.db.engine import create_engine, create_tables
from darth_gain.db.repo import (
    upsert_workout,
    upsert_templates,
    upsert_routine,
    soft_delete_workout,
)
from darth_gain.web.app import create_app
from darth_gain.web.deps import require_user


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def temp_data_dir() -> str:
    """Create temporary data directory (session-scoped so all tests share same DB)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def frozen_time():
    """Freeze time to 2026-08-15 so July workouts are within 8-week window."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        yield


@pytest.fixture
def test_db(temp_data_dir: str) -> sqlite3.Connection:
    """Create test database with schema and sample data (July 2026)."""
    db_path = os.path.join(temp_data_dir, "user_test-user", "workouts.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = create_engine(db_path)
    create_tables(conn)

    # Create routine
    routine_id = "routine-push"
    upsert_routine(conn, {
        "id": routine_id, "title": "Push Day", "folder_id": None,
        "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
    })

    # Templates
    template_ids = {
        "bench": "tmpl-bench",
        "squat": "tmpl-squat",
    }
    upsert_templates(conn, [
        {"id": template_ids["bench"], "title": "Bench Press", "type": "weight_reps",
         "primary_muscle_group": "chest", "other_muscle_groups": "[]",
         "equipment": "barbell", "is_custom": 0},
        {"id": template_ids["squat"], "title": "Squat", "type": "weight_reps",
         "primary_muscle_group": "quads", "other_muscle_groups": "[]",
         "equipment": "barbell", "is_custom": 0},
    ])

    # Workouts across 3 weeks in July 2026 (within 8 weeks of frozen 2026-08-15)
    for week, (date_str, title) in enumerate([
        ("2026-07-01", "Week 1"),
        ("2026-07-08", "Week 2"),
        ("2026-07-15", "Week 3"),
    ]):
        wo_id = f"wo-{week}"
        upsert_workout(conn,
            {"id": wo_id, "title": title, "description": "",
             "start_time": f"{date_str}T10:00:00Z", "end_time": f"{date_str}T11:00:00Z",
             "routine_id": routine_id},
            [
                {"exercise_template_id": template_ids["bench"], "title": "Bench Press",
                 "notes": "", "sort_order": 0,
                 "sets": [
                     {"set_index": 0, "type": "normal", "weight_kg": 100, "reps": 8, "rpe": 8.0},
                     {"set_index": 1, "type": "normal", "weight_kg": 100, "reps": 8, "rpe": 8.5},
                 ]},
                {"exercise_template_id": template_ids["squat"], "title": "Squat",
                 "notes": "", "sort_order": 1,
                 "sets": [
                     {"set_index": 0, "type": "normal", "weight_kg": 140, "reps": 8, "rpe": 8.0},
                 ]},
            ])

    # Other routine (should not appear in export)
    other_routine = "routine-pull"
    upsert_routine(conn, {
        "id": other_routine, "title": "Pull Day", "folder_id": None,
        "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
    })
    upsert_workout(conn,
        {"id": "wo-other", "title": "Pull", "description": "",
         "start_time": "2026-07-10T10:00:00Z", "end_time": "2026-07-10T11:00:00Z",
         "routine_id": other_routine},
        [{"exercise_template_id": template_ids["bench"], "title": "Bench",
          "notes": "", "sort_order": 0,
          "sets": [{"set_index": 0, "type": "normal", "weight_kg": 80, "reps": 10, "rpe": 7.0}]}])

    # Soft deleted workout
    upsert_workout(conn,
        {"id": "wo-deleted", "title": "Deleted", "description": "",
         "start_time": "2026-07-12T10:00:00Z", "end_time": "2026-07-12T11:00:00Z",
         "routine_id": routine_id},
        [{"exercise_template_id": template_ids["bench"], "title": "Bench",
          "notes": "", "sort_order": 0,
          "sets": [{"set_index": 0, "type": "normal", "weight_kg": 50, "reps": 5, "rpe": 6.0}]}])
    soft_delete_workout(conn, "wo-deleted")

    conn.close()
    return conn


@pytest.fixture
def app(temp_data_dir: str, test_db: sqlite3.Connection):
    """Create FastAPI app with test data directory."""
    app = create_app(data_dir=temp_data_dir)

    # Override auth dependency
    async def mock_require_user():
        return {"user_id": "test-user", "email": "test@example.com"}

    app.dependency_overrides[require_user] = mock_require_user
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def client(app) -> TestClient:
    """Test client for sync tests."""
    with TestClient(app) as client:
        yield client


# ---------------------------------------------------------------------------
# Happy Path Tests
# ---------------------------------------------------------------------------


def test_export_routine_success(client: TestClient) -> None:
    """GET /api/v1/routines/{id}/export returns 200 with valid JSON."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        resp = client.get("/api/v1/routines/routine-push/export?weeks=8")
    assert resp.status_code == 200

    data = resp.json()
    assert data["meta"]["routine_id"] == "routine-push"
    assert data["meta"]["routine_title"] == "Push Day"
    assert data["window"]["weeks_analyzed"] == 8
    assert len(data["workouts"]) == 3
    assert data["summary"]["total_workouts"] == 3


def test_export_routine_default_weeks(client: TestClient) -> None:
    """Default weeks=8 when not specified."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        resp = client.get("/api/v1/routines/routine-push/export")
    assert resp.status_code == 200
    assert resp.json()["window"]["weeks_analyzed"] == 8


def test_export_routine_custom_tz(client: TestClient) -> None:
    """Custom timezone parameter works."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        resp = client.get("/api/v1/routines/routine-push/export?weeks=8&tz=America/New_York")
    assert resp.status_code == 200
    assert resp.json()["window"]["timezone"] == "America/New_York"


def test_export_routine_response_structure(client: TestClient) -> None:
    """Response has all required fields per schema."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        resp = client.get("/api/v1/routines/routine-push/export?weeks=8")
    data = resp.json()

    # Meta
    assert "meta" in data
    assert "routine_id" in data["meta"]
    assert "routine_title" in data["meta"]
    assert "routine_created_at" in data["meta"]

    # Window
    assert "window" in data
    assert "start" in data["window"]
    assert "end" in data["window"]
    assert "weeks_analyzed" in data["window"]
    assert "timezone" in data["window"]

    # Workouts
    assert "workouts" in data
    assert isinstance(data["workouts"], list)
    for wo in data["workouts"]:
        assert "workout_id" in wo
        assert "date" in wo
        assert "exercises" in wo
        for ex in wo["exercises"]:
            assert "template_id" in ex
            assert "title" in ex
            assert "muscle_group" in ex
            assert "sets" in ex
            for s in ex["sets"]:
                assert "set_index" in s
                assert "type" in s

    # Summary
    assert "summary" in data
    summary = data["summary"]
    assert "total_workouts" in summary
    assert "frequency_per_week" in summary
    assert "volume_by_muscle_group" in summary
    assert "progression_trends" in summary
    assert "deload_weeks_detected" in summary
    assert "exercise_summaries" in summary


def test_export_routine_content_disposition_header(client: TestClient) -> None:
    """Response includes Content-Disposition header for download."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        resp = client.get("/api/v1/routines/routine-push/export?weeks=8")
    assert resp.status_code == 200
    cd = resp.headers.get("content-disposition")
    assert cd is not None
    assert 'attachment; filename="routine-push-day-' in cd
    assert cd.endswith('.json"')


def test_export_routine_etag_header(client: TestClient) -> None:
    """Response includes ETag header."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        resp = client.get("/api/v1/routines/routine-push/export?weeks=8")
    assert resp.status_code == 200
    etag = resp.headers.get("etag")
    assert etag is not None
    assert len(etag) == 16  # SHA256 truncated to 16 chars


def test_export_routine_cache_control_header(client: TestClient) -> None:
    """Response includes Cache-Control header."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        resp = client.get("/api/v1/routines/routine-push/export?weeks=8")
    assert resp.status_code == 200
    cc = resp.headers.get("cache-control")
    assert cc == "private, max-age=300"


# ---------------------------------------------------------------------------
# Conditional Request (304) Tests
# ---------------------------------------------------------------------------


def test_export_routine_304_not_modified(client: TestClient) -> None:
    """If-None-Match with matching ETag returns 304."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        # First request to get ETag
        resp1 = client.get("/api/v1/routines/routine-push/export?weeks=8")
        assert resp1.status_code == 200
        etag = resp1.headers.get("etag")
        assert etag is not None

        # Second request with matching ETag (same freeze_time context)
        resp2 = client.get(
            "/api/v1/routines/routine-push/export?weeks=8",
            headers={"If-None-Match": etag},
        )
        assert resp2.status_code == 304, f"Expected 304, got {resp2.status_code}. ETag: {etag}"


def test_export_routine_no_304_on_different_etag(client: TestClient) -> None:
    """If-None-Match with non-matching ETag returns 200."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        resp = client.get(
            "/api/v1/routines/routine-push/export?weeks=8",
            headers={"If-None-Match": "different-etag"},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Error Cases
# ---------------------------------------------------------------------------


def test_export_routine_not_found(client: TestClient) -> None:
    """Non-existent routine returns 404."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        resp = client.get("/api/v1/routines/non-existent/export?weeks=8")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_export_routine_no_workouts_in_window(client: TestClient) -> None:
    """Routine exists but no workouts in window returns 404."""
    # weeks=4 from 2026-08-15 would be ~2026-07-18 to 2026-08-15
    # Test data is from July 1-15, so outside 4-week window
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        resp = client.get("/api/v1/routines/routine-push/export?weeks=4")
    assert resp.status_code == 404
    assert "no workouts" in resp.json()["detail"].lower()


def test_export_routine_weeks_too_low(client: TestClient) -> None:
    """weeks < 4 returns 422."""
    resp = client.get("/api/v1/routines/routine-push/export?weeks=3")
    assert resp.status_code == 422


def test_export_routine_weeks_too_high(client: TestClient) -> None:
    """weeks > 24 returns 422."""
    resp = client.get("/api/v1/routines/routine-push/export?weeks=25")
    assert resp.status_code == 422


def test_export_routine_invalid_tz(client: TestClient) -> None:
    """Invalid timezone pattern returns 422."""
    resp = client.get("/api/v1/routines/routine-push/export?weeks=8&tz=invalid!")
    assert resp.status_code == 422


def test_export_routine_unauthorized(client: TestClient, app) -> None:
    """Unauthenticated request returns 401 (redirects to login)."""
    # Remove auth override
    app.dependency_overrides.clear()
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        with TestClient(app, follow_redirects=False) as unauth_client:
            resp = unauth_client.get("/api/v1/routines/routine-push/export?weeks=8")
    # Auth exception handler redirects to /login (302) or returns 401
    assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# Data Isolation Tests
# ---------------------------------------------------------------------------


def test_export_routine_excludes_other_routines(client: TestClient) -> None:
    """Export only includes workouts from the specified routine."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        resp = client.get("/api/v1/routines/routine-push/export?weeks=8")
    data = resp.json()

    workout_ids = {w["workout_id"] for w in data["workouts"]}
    assert "wo-other" not in workout_ids
    assert len(data["workouts"]) == 3


def test_export_routine_excludes_soft_deleted(client: TestClient) -> None:
    """Export excludes soft-deleted workouts."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        resp = client.get("/api/v1/routines/routine-push/export?weeks=8")
    data = resp.json()

    workout_ids = {w["workout_id"] for w in data["workouts"]}
    assert "wo-deleted" not in workout_ids


# ---------------------------------------------------------------------------
# Summary Analytics Tests
# ---------------------------------------------------------------------------


def test_export_summary_volume_by_muscle(client: TestClient) -> None:
    """Summary includes volume_by_muscle_group."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        resp = client.get("/api/v1/routines/routine-push/export?weeks=8")
    data = resp.json()
    vol = data["summary"]["volume_by_muscle_group"]
    assert "chest" in vol
    assert "quads" in vol
    assert vol["chest"] > 0
    assert vol["quads"] > 0


def test_export_summary_frequency(client: TestClient) -> None:
    """Summary includes frequency_per_week."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        resp = client.get("/api/v1/routines/routine-push/export?weeks=8")
    data = resp.json()
    freq = data["summary"]["frequency_per_week"]
    assert freq == pytest.approx(0.375, rel=0.2)  # 3 workouts / 8 weeks = 0.375/week


def test_export_summary_progression_trends(client: TestClient) -> None:
    """Summary includes progression_trends for exercises with data."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        resp = client.get("/api/v1/routines/routine-push/export?weeks=8")
    data = resp.json()
    trends = data["summary"]["progression_trends"]
    # 3 weeks of data but need >=4 data points for trend
    assert trends == {}


def test_export_summary_deload_weeks(client: TestClient) -> None:
    """Summary includes deload_weeks_detected."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        resp = client.get("/api/v1/routines/routine-push/export?weeks=8")
    data = resp.json()
    deloads = data["summary"]["deload_weeks_detected"]
    # No deload in test data (consistent volume)
    assert deloads == []


def test_export_summary_exercise_summaries(client: TestClient) -> None:
    """Summary includes exercise_summaries with all fields."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        resp = client.get("/api/v1/routines/routine-push/export?weeks=8")
    data = resp.json()
    summaries = data["summary"]["exercise_summaries"]
    assert len(summaries) == 2  # bench + squat

    for es in summaries:
        assert "template_id" in es
        assert "title" in es
        assert "muscle_group" in es
        assert "total_sets" in es
        assert "total_volume_kg" in es
        assert "avg_weight_kg" in es
        assert "max_weight_kg" in es
        assert "sets_with_rpe" in es
        # Optional fields
        assert "progression_slope_kg_per_week" in es
        assert "r2" in es
        assert "avg_rpe" in es
        assert "max_rpe" in es


def test_export_summary_null_rpe_handling(client: TestClient, temp_data_dir: str) -> None:
    """Summary handles null RPE correctly."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        # Add workout with null RPE (in July, within window)
        db_path = os.path.join(temp_data_dir, "user_test-user", "workouts.db")
        conn = create_engine(db_path)
        upsert_workout(conn,
            {"id": "wo-null-rpe", "title": "Null RPE", "description": "",
             "start_time": "2026-07-20T10:00:00Z", "end_time": "2026-07-20T11:00:00Z",
             "routine_id": "routine-push"},
            [{"exercise_template_id": "tmpl-bench", "title": "Bench",
              "notes": "", "sort_order": 0,
              "sets": [{"set_index": 0, "type": "normal", "weight_kg": 100, "reps": 8, "rpe": None}]}])
        conn.close()

        resp = client.get("/api/v1/routines/routine-push/export?weeks=8")
        data = resp.json()
        summaries = data["summary"]["exercise_summaries"]
        bench = next(s for s in summaries if "Bench" in s["title"])
        # 2 sets × 3 original workouts = 6 sets with RPE, plus 1 null = 6 with RPE
        assert bench["sets_with_rpe"] == 6
        assert bench["avg_rpe"] is not None  # Should average the non-null ones


# ---------------------------------------------------------------------------
# OpenAPI Schema Tests
# ---------------------------------------------------------------------------

def test_openapi_includes_export_endpoint(app) -> None:
    """OpenAPI schema includes the export endpoint."""
    from fastapi.openapi.utils import get_openapi
    schema = get_openapi(title="Test", version="1.0.0", routes=app.routes)
    paths = schema["paths"]
    assert "/api/v1/routines/{routine_id}/export" in paths
    assert "get" in paths["/api/v1/routines/{routine_id}/export"]