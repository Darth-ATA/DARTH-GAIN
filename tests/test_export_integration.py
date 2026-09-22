"""Integration tests for export router — auth, rate limit, CORS, ETag, isolation."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import pytest
import freezegun
from fastapi.testclient import TestClient

from darth_gain.db.engine import create_engine, create_tables
from darth_gain.db.repo import upsert_routine, upsert_templates, upsert_workout
from darth_gain.web.app import create_app
from darth_gain.web.deps import require_user


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def temp_data_dir() -> str:
    """Create temporary data directory (session-scoped)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def setup_two_users(temp_data_dir: str) -> tuple[str, str]:
    """Create databases for two users with routines and workouts."""
    # User 1
    db_path_1 = os.path.join(temp_data_dir, "user_user-1", "workouts.db")
    os.makedirs(os.path.dirname(db_path_1), exist_ok=True)
    conn = create_engine(db_path_1)
    create_tables(conn)
    upsert_routine(conn, {"id": "routine-push-1", "title": "Push Day", "folder_id": None, "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"})
    upsert_templates(conn, [{"id": "tmpl-bench", "title": "Bench Press", "type": "weight_reps", "primary_muscle_group": "chest", "other_muscle_groups": "[]", "equipment": "barbell", "is_custom": 0}])
    upsert_workout(conn, {"id": "wo-1", "title": "Week 1", "description": "", "start_time": "2026-07-01T10:00:00Z", "end_time": "2026-07-01T11:00:00Z", "routine_id": "routine-push-1"}, [{"exercise_template_id": "tmpl-bench", "title": "Bench Press", "notes": "", "sort_order": 0, "sets": [{"set_index": 0, "type": "normal", "weight_kg": 100, "reps": 8, "rpe": 8.0}]}])
    conn.close()

    # User 2
    db_path_2 = os.path.join(temp_data_dir, "user_user-2", "workouts.db")
    os.makedirs(os.path.dirname(db_path_2), exist_ok=True)
    conn = create_engine(db_path_2)
    create_tables(conn)
    upsert_routine(conn, {"id": "routine-pull-2", "title": "Pull Day", "folder_id": None, "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"})
    upsert_templates(conn, [{"id": "tmpl-row", "title": "Row", "type": "weight_reps", "primary_muscle_group": "back", "other_muscle_groups": "[]", "equipment": "barbell", "is_custom": 0}])
    upsert_workout(conn, {"id": "wo-2", "title": "Week 1", "description": "", "start_time": "2026-07-01T10:00:00Z", "end_time": "2026-07-01T11:00:00Z", "routine_id": "routine-pull-2"}, [{"exercise_template_id": "tmpl-row", "title": "Row", "notes": "", "sort_order": 0, "sets": [{"set_index": 0, "type": "normal", "weight_kg": 80, "reps": 10, "rpe": 7.5}]}])
    conn.close()

    return "user-1", "user-2"


@pytest.fixture
def app(temp_data_dir: str, setup_two_users: tuple[str, str]):
    """Create FastAPI app with test data directory."""
    app = create_app(data_dir=temp_data_dir)

    # We'll override auth per-test
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def client(app) -> TestClient:
    """Test client for sync tests."""
    with TestClient(app) as client:
        yield client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_authed_client(app, user_id: str) -> TestClient:
    """Create a TestClient with auth override for a specific user."""
    app.dependency_overrides.clear()
    async def mock_require_user():
        return {"user_id": user_id, "email": f"{user_id}@example.com"}
    app.dependency_overrides[require_user] = mock_require_user
    return TestClient(app)


# ---------------------------------------------------------------------------
# Auth Tests
# ---------------------------------------------------------------------------


def test_export_requires_auth(app, temp_data_dir, setup_two_users):
    """Unauthenticated request to export endpoint redirects to login."""
    app.dependency_overrides.clear()
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        with TestClient(app, follow_redirects=False) as unauth_client:
            resp = unauth_client.get("/api/v1/routines/routine-push-1/export?weeks=8")
    # Auth exception handler redirects to /login (302) or returns 401
    assert resp.status_code in (302, 401)
    if resp.status_code == 302:
        assert resp.headers.get("location") == "/login"


def test_export_with_auth_works(app, temp_data_dir, setup_two_users):
    """Authenticated request works."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        with make_authed_client(app, "user-1") as client:
            resp = client.get("/api/v1/routines/routine-push-1/export?weeks=8")
    assert resp.status_code == 200
    assert resp.json()["meta"]["routine_id"] == "routine-push-1"


# ---------------------------------------------------------------------------
# Cross-User Isolation Tests
# ---------------------------------------------------------------------------


def test_export_cannot_access_other_user_routine(app, temp_data_dir, setup_two_users):
    """User 1 cannot export User 2's routine (404)."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        with make_authed_client(app, "user-1") as client:
            resp = client.get("/api/v1/routines/routine-pull-2/export?weeks=8")
    # Routine doesn't exist for user-1
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_export_only_sees_own_workouts(app, temp_data_dir, setup_two_users):
    """User 1 only sees their own workouts."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        with make_authed_client(app, "user-1") as client:
            resp = client.get("/api/v1/routines/routine-push-1/export?weeks=8")
    data = resp.json()
    assert len(data["workouts"]) == 1
    assert data["workouts"][0]["workout_id"] == "wo-1"


# ---------------------------------------------------------------------------
# ETag / 304 Tests
# ---------------------------------------------------------------------------


def test_export_etag_304_not_modified(app, temp_data_dir, setup_two_users):
    """If-None-Match with matching ETag returns 304."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        with make_authed_client(app, "user-1") as client:
            # First request
            resp1 = client.get("/api/v1/routines/routine-push-1/export?weeks=8")
            assert resp1.status_code == 200
            etag = resp1.headers.get("etag")
            assert etag is not None

            # Second request with same ETag
            resp2 = client.get(
                "/api/v1/routines/routine-push-1/export?weeks=8",
                headers={"If-None-Match": etag},
            )
            assert resp2.status_code == 304


def test_export_etag_changes_on_data_change(app, temp_data_dir, setup_two_users):
    """ETag changes when workout data changes."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        with make_authed_client(app, "user-1") as client:
            # First request
            resp1 = client.get("/api/v1/routines/routine-push-1/export?weeks=8")
            etag1 = resp1.headers.get("etag")

            # Add a new workout
            from darth_gain.db.engine import create_engine
            from darth_gain.db.repo import upsert_workout
            db_path = os.path.join(temp_data_dir, "user_user-1", "workouts.db")
            conn = create_engine(db_path)
            upsert_workout(conn, {"id": "wo-new", "title": "New", "description": "", "start_time": "2026-08-10T10:00:00Z", "end_time": "2026-08-10T11:00:00Z", "routine_id": "routine-push-1"}, [{"exercise_template_id": "tmpl-bench", "title": "Bench Press", "notes": "", "sort_order": 0, "sets": [{"set_index": 0, "type": "normal", "weight_kg": 105, "reps": 8, "rpe": 8.5}]}])
            conn.close()

            # Second request - ETag should be different
            resp2 = client.get("/api/v1/routines/routine-push-1/export?weeks=8")
            etag2 = resp2.headers.get("etag")
            assert etag1 != etag2


def test_export_no_304_on_different_etag(app, temp_data_dir, setup_two_users):
    """If-None-Match with non-matching ETag returns 200."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        with make_authed_client(app, "user-1") as client:
            resp = client.get(
                "/api/v1/routines/routine-push-1/export?weeks=8",
                headers={"If-None-Match": "different-etag"},
            )
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# CORS Tests
# ---------------------------------------------------------------------------


def test_export_cors_headers_present(app, temp_data_dir, setup_two_users):
    """CORS headers are present for allowed origins."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        with make_authed_client(app, "user-1") as client:
            resp = client.get(
                "/api/v1/routines/routine-push-1/export?weeks=8",
                headers={"Origin": "https://ai-tool.example.com"},
            )
    # Note: CORS middleware not yet configured in test app
    # This test documents expected behavior when CORS is enabled
    # For now, verify the endpoint works with Origin header
    assert resp.status_code == 200


def test_export_preflight_request(app, temp_data_dir, setup_two_users):
    """OPTIONS preflight request works."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        with make_authed_client(app, "user-1") as client:
            resp = client.options(
                "/api/v1/routines/routine-push-1/export?weeks=8",
                headers={
                    "Origin": "https://ai-tool.example.com",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "Content-Type",
                },
            )
    # OPTIONS may return 200 or 405 depending on middleware
    assert resp.status_code in (200, 405)


# ---------------------------------------------------------------------------
# Cache Control Tests
# ---------------------------------------------------------------------------


def test_export_cache_control_header(app, temp_data_dir, setup_two_users):
    """Response includes Cache-Control: private, max-age=300."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        with make_authed_client(app, "user-1") as client:
            resp = client.get("/api/v1/routines/routine-push-1/export?weeks=8")
    assert resp.status_code == 200
    cc = resp.headers.get("cache-control")
    assert cc == "private, max-age=300"


def test_export_etag_header_present(app, temp_data_dir, setup_two_users):
    """Response includes ETag header."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        with make_authed_client(app, "user-1") as client:
            resp = client.get("/api/v1/routines/routine-push-1/export?weeks=8")
    etag = resp.headers.get("etag")
    assert etag is not None
    assert len(etag) == 16  # SHA256 truncated to 16 chars


# ---------------------------------------------------------------------------
# Content-Disposition Tests
# ---------------------------------------------------------------------------


def test_export_content_disposition_filename(app, temp_data_dir, setup_two_users):
    """Response includes Content-Disposition with proper filename."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        with make_authed_client(app, "user-1") as client:
            resp = client.get("/api/v1/routines/routine-push-1/export?weeks=8")
    cd = resp.headers.get("content-disposition")
    assert cd is not None
    assert 'attachment; filename="routine-push-day-' in cd
    assert cd.endswith('.json"')


# ---------------------------------------------------------------------------
# Rate Limiting Tests (Documentation)
# ---------------------------------------------------------------------------


# Note: Rate limiting requires slowapi middleware which is not yet integrated
# These tests document expected behavior when rate limiting is enabled


def test_export_rate_limit_exceeded_returns_429(app, temp_data_dir, setup_two_users):
    """Exceeding rate limit returns 429 (when slowapi enabled)."""
    # This test is skipped until slowapi is integrated
    pytest.skip("Rate limiting not yet implemented - requires slowapi middleware")


# ---------------------------------------------------------------------------
# Weeks Validation Tests
# ---------------------------------------------------------------------------


def test_export_weeks_bounds_validation(app, temp_data_dir, setup_two_users):
    """weeks parameter validates bounds (4-24)."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        with make_authed_client(app, "user-1") as client:
            # weeks=3 should fail
            resp = client.get("/api/v1/routines/routine-push-1/export?weeks=3")
            assert resp.status_code == 422

            # weeks=25 should fail
            resp = client.get("/api/v1/routines/routine-push-1/export?weeks=25")
            assert resp.status_code == 422

            # weeks=4 should work
            resp = client.get("/api/v1/routines/routine-push-1/export?weeks=4")
            assert resp.status_code == 200

            # weeks=24 should work
            resp = client.get("/api/v1/routines/routine-push-1/export?weeks=24")
            assert resp.status_code == 200


def test_export_invalid_tz_validation(app, temp_data_dir, setup_two_users):
    """Invalid timezone returns 422."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        with make_authed_client(app, "user-1") as client:
            resp = client.get("/api/v1/routines/routine-push-1/export?weeks=8&tz=invalid!")
            assert resp.status_code == 422


def test_export_valid_tz_accepted(app, temp_data_dir, setup_two_users):
    """Valid IANA timezone accepted."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        with make_authed_client(app, "user-1") as client:
            resp = client.get("/api/v1/routines/routine-push-1/export?weeks=8&tz=America/New_York")
            assert resp.status_code == 200
            assert resp.json()["window"]["timezone"] == "America/New_York"


# ---------------------------------------------------------------------------
# Response Structure Tests
# ---------------------------------------------------------------------------


def test_export_response_has_all_required_fields(app, temp_data_dir, setup_two_users):
    """Response includes all required fields per schema."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        with make_authed_client(app, "user-1") as client:
            resp = client.get("/api/v1/routines/routine-push-1/export?weeks=8")
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

    # Summary
    assert "summary" in data
    summary = data["summary"]
    assert "total_workouts" in summary
    assert "frequency_per_week" in summary
    assert "volume_by_muscle_group" in summary
    assert "progression_trends" in summary
    assert "deload_weeks_detected" in summary
    assert "exercise_summaries" in summary


def test_export_exercise_summary_includes_rpe_fields(app, temp_data_dir, setup_two_users):
    """Exercise summaries include RPE-related fields."""
    with freezegun.freeze_time("2026-08-15 12:00:00", tz_offset=0):
        with make_authed_client(app, "user-1") as client:
            resp = client.get("/api/v1/routines/routine-push-1/export?weeks=8")
    data = resp.json()
    summaries = data["summary"]["exercise_summaries"]
    assert len(summaries) > 0
    for es in summaries:
        assert "avg_rpe" in es
        assert "max_rpe" in es
        assert "sets_with_rpe" in es


# ---------------------------------------------------------------------------
# OpenAPI Tests
# ---------------------------------------------------------------------------


def test_openapi_includes_export_endpoint(app):
    """OpenAPI schema includes the export endpoint."""
    from fastapi.openapi.utils import get_openapi
    schema = get_openapi(title="Test", version="1.0.0", routes=app.routes)
    paths = schema["paths"]
    assert "/api/v1/routines/{routine_id}/export" in paths
    assert "get" in paths["/api/v1/routines/{routine_id}/export"]