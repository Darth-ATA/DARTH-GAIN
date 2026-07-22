"""Tests for darth_gain.hevy.client — domain dataclasses and HevyClient adapter."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from darth_gain.hevy.client import EventsPage, HevyClient, WorkoutEvent


# ===========================================================================
# Domain dataclasses
# ===========================================================================


class TestWorkoutEvent:
    """WorkoutEvent holds an event index, type, and optional workout dict."""

    def test_updated_event_holds_workout_dict(self) -> None:
        """An updated event carries the full workout data."""
        event = WorkoutEvent(
            index=0,
            type="updated",
            workout={"id": "w001", "title": "Push Day"},
        )
        assert event.index == 0
        assert event.type == "updated"
        assert event.workout == {"id": "w001", "title": "Push Day"}

    def test_deleted_event_has_none_workout(self) -> None:
        """A deleted event has no workout data attached."""
        event = WorkoutEvent(index=1, type="deleted", workout=None)
        assert event.index == 1
        assert event.type == "deleted"
        assert event.workout is None


class TestEventsPage:
    """EventsPage holds pagination metadata and a list of events."""

    def test_holds_page_metadata(self) -> None:
        """EventsPage stores page, page_count, total_count."""
        page = EventsPage(page=1, page_count=5, total_count=42, events=[])
        assert page.page == 1
        assert page.page_count == 5
        assert page.total_count == 42

    def test_holds_events_list(self) -> None:
        """EventsPage stores the list of WorkoutEvent objects."""
        events = [
            WorkoutEvent(index=0, type="updated", workout={"id": "w001"}),
            WorkoutEvent(index=1, type="deleted", workout=None),
        ]
        page = EventsPage(page=1, page_count=1, total_count=2, events=events)
        assert len(page.events) == 2
        assert page.events[0].type == "updated"
        assert page.events[1].type == "deleted"


# ===========================================================================
# HevyClient adapter
# ===========================================================================


class TestHevyClientInit:
    """HevyClient wraps hevy_api_wrapper.Client."""

    def test_creates_sdk_client(self) -> None:
        """HevyClient instantiates the SDK Client with the given API key."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            client = HevyClient(api_key="test-key")
            mock_sdk.assert_called_once_with(api_key="test-key")
            assert client._client is mock_sdk.return_value


class TestGetEvents:
    """HevyClient.get_events bypasses the SDK pydantic model via _request()."""

    # -------------------------------------------------------------------
    # Helpers — raw API response fragments
    # -------------------------------------------------------------------

    @staticmethod
    def _workout_dict(
        workout_id: str,
        title: str | None = None,
        exercises: list[dict] | None = None,
    ) -> dict:
        """Return a minimal raw workout dict as the API would return it."""
        return {
            "id": workout_id,
            "title": title or f"Workout {workout_id}",
            "description": "",
            "start_time": "2024-06-01T08:00:00Z",
            "end_time": "2024-06-01T09:00:00Z",
            "updated_at": "2024-06-01T10:00:00Z",
            "created_at": "2024-05-01T08:00:00Z",
            "exercises": exercises or [],
        }

    @staticmethod
    def _raw_api_response(
        raw_events: list[dict],
        page: int = 1,
        page_count: int = 3,
    ) -> dict:
        """Return a dict that simulates the raw ``/v1/workouts/events`` JSON.

        The API returns ``workouts`` (not ``events``) as the key for the
        array of change items.
        """
        return {"page": page, "page_count": page_count, "workouts": raw_events}

    @staticmethod
    def _mock_response(json_data: dict) -> MagicMock:
        """Build a mock ``_request`` return value with a ``.json()`` method."""
        resp = MagicMock()
        resp.json.return_value = json_data
        return resp

    # -------------------------------------------------------------------
    # Tests
    # -------------------------------------------------------------------

    def test_calls_sdk_with_correct_params(self) -> None:
        """get_events calls _request with the right HTTP method and path."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_sdk.return_value._request.return_value = self._mock_response(
                self._raw_api_response([])
            )
            client = HevyClient(api_key="test-key")

            client.get_events(since="2024-01-01T00:00:00Z", page=2)

            mock_sdk.return_value._request.assert_called_once_with(
                "GET",
                "/v1/workouts/events",
                params={"since": "2024-01-01T00:00:00Z", "page": 2, "pageSize": 10},
            )

    def test_defaults_to_page_1(self) -> None:
        """get_events defaults to page 1 with page_size=10."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_sdk.return_value._request.return_value = self._mock_response(
                self._raw_api_response([])
            )
            client = HevyClient(api_key="test-key")

            client.get_events(since="2024-01-01T00:00:00Z")

            mock_sdk.return_value._request.assert_called_once_with(
                "GET",
                "/v1/workouts/events",
                params={"since": "2024-01-01T00:00:00Z", "page": 1, "pageSize": 10},
            )

    def test_returns_events_page_with_metadata(self) -> None:
        """get_events returns EventsPage with page/page_count/total_count."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_sdk.return_value._request.return_value = self._mock_response(
                self._raw_api_response(
                    [{"type": "updated", "workout": self._workout_dict("w001")}],
                    page=1,
                    page_count=3,
                )
            )
            client = HevyClient(api_key="test-key")

            result = client.get_events(since="2024-01-01T00:00:00Z")

            assert result.page == 1
            assert result.page_count == 3
            assert result.total_count == 1

    def test_converts_updated_event(self) -> None:
        """An updated workout becomes WorkoutEvent with type='updated'."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_sdk.return_value._request.return_value = self._mock_response(
                self._raw_api_response(
                    [{"type": "updated", "workout": self._workout_dict("w001")}]
                )
            )
            client = HevyClient(api_key="test-key")

            result = client.get_events(since="2024-01-01T00:00:00Z")

            assert len(result.events) == 1
            event = result.events[0]
            assert event.type == "updated"
            assert event.workout is not None
            assert event.workout["id"] == "w001"

    def test_converts_deleted_event(self) -> None:
        """A deleted event becomes WorkoutEvent with type='deleted'."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_sdk.return_value._request.return_value = self._mock_response(
                self._raw_api_response(
                    [{"type": "deleted"}]
                )
            )
            client = HevyClient(api_key="test-key")

            result = client.get_events(since="2024-01-01T00:00:00Z")

            assert len(result.events) == 1
            event = result.events[0]
            assert event.type == "deleted"
            assert event.workout is None

    def test_converts_mixed_events(self) -> None:
        """Both updated and deleted events are converted correctly."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_sdk.return_value._request.return_value = self._mock_response(
                self._raw_api_response(
                    [
                        {"type": "updated", "workout": self._workout_dict("w001")},
                        {"type": "deleted"},
                    ]
                )
            )
            client = HevyClient(api_key="test-key")

            result = client.get_events(since="2024-01-01T00:00:00Z")

            assert len(result.events) == 2
            assert result.events[0].type == "updated"
            assert result.events[0].workout is not None
            assert result.events[1].type == "deleted"
            assert result.events[1].workout is None

    def test_workout_dict_includes_repo_fields(self) -> None:
        """The workout dict has the fields expected by repo.upsert_workout."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            raw_workout = {
                "id": "w001",
                "title": "Push Day",
                "description": "Chest",
                "start_time": "2024-06-01T08:00:00Z",
                "end_time": "2024-06-01T09:00:00Z",
                "updated_at": "2024-06-01T10:00:00Z",
                "created_at": "2024-05-01T08:00:00Z",
                "exercises": [
                    {
                        "exercise_template_id": "t001",
                        "title": "Bench Press",
                        "notes": "Go heavy",
                        "index": 0,
                        "sets": [
                            {
                                "index": 0,
                                "type": "normal",
                                "weight_kg": 80.0,
                                "reps": 10,
                                "distance_meters": None,
                                "duration_seconds": None,
                                "rpe": None,
                            }
                        ],
                    }
                ],
            }
            mock_sdk.return_value._request.return_value = self._mock_response(
                self._raw_api_response(
                    [{"type": "updated", "workout": raw_workout}]
                )
            )
            client = HevyClient(api_key="test-key")

            result = client.get_events(since="2024-01-01T00:00:00Z")
            workout = result.events[0].workout

            assert workout is not None
            assert workout["id"] == "w001"
            assert workout["title"] == "Push Day"
            assert workout["description"] == "Chest"
            assert workout["start_time"] == "2024-06-01T08:00:00Z"
            assert workout["end_time"] == "2024-06-01T09:00:00Z"
            assert workout["updated_at"] == "2024-06-01T10:00:00Z"
            assert workout["created_at"] == "2024-05-01T08:00:00Z"

    def test_workout_includes_exercises_with_sort_order(self) -> None:
        """Exercises have index mapped to sort_order."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            raw_workout = {
                "id": "w001",
                "title": "Push Day",
                "description": "",
                "start_time": "2024-06-01T08:00:00Z",
                "end_time": "2024-06-01T09:00:00Z",
                "updated_at": "2024-06-01T10:00:00Z",
                "created_at": "2024-05-01T08:00:00Z",
                "exercises": [
                    {
                        "exercise_template_id": "t001",
                        "title": "Bench Press",
                        "notes": "",
                        "index": 0,
                        "sets": [],
                    },
                    {
                        "exercise_template_id": "t002",
                        "title": "Overhead Press",
                        "notes": "Slow negatives",
                        "index": 1,
                        "sets": [],
                    },
                ],
            }
            mock_sdk.return_value._request.return_value = self._mock_response(
                self._raw_api_response(
                    [{"type": "updated", "workout": raw_workout}]
                )
            )
            client = HevyClient(api_key="test-key")

            result = client.get_events(since="2024-01-01T00:00:00Z")
            exercises = result.events[0].workout["exercises"]

            assert len(exercises) == 2
            assert exercises[0]["sort_order"] == 0
            assert exercises[0]["title"] == "Bench Press"
            assert exercises[0]["exercise_template_id"] == "t001"
            assert exercises[0]["notes"] == ""
            assert exercises[1]["sort_order"] == 1
            assert exercises[1]["title"] == "Overhead Press"

    def test_exercise_includes_sets_with_set_index(self) -> None:
        """Sets have index mapped to set_index."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            raw_workout = {
                "id": "w001",
                "title": "Push Day",
                "description": "",
                "start_time": "2024-06-01T08:00:00Z",
                "end_time": "2024-06-01T09:00:00Z",
                "updated_at": "2024-06-01T10:00:00Z",
                "created_at": "2024-05-01T08:00:00Z",
                "exercises": [
                    {
                        "exercise_template_id": "t001",
                        "title": "Bench Press",
                        "notes": "",
                        "index": 0,
                        "sets": [
                            {
                                "index": 0,
                                "type": "normal",
                                "weight_kg": 80.0,
                                "reps": 10,
                                "distance_meters": None,
                                "duration_seconds": None,
                                "rpe": None,
                            }
                        ],
                    }
                ],
            }
            mock_sdk.return_value._request.return_value = self._mock_response(
                self._raw_api_response(
                    [{"type": "updated", "workout": raw_workout}]
                )
            )
            client = HevyClient(api_key="test-key")

            result = client.get_events(since="2024-01-01T00:00:00Z")
            sets = result.events[0].workout["exercises"][0]["sets"]

            assert len(sets) == 1
            assert sets[0]["set_index"] == 0
            assert sets[0]["type"] == "normal"
            assert sets[0]["weight_kg"] == 80.0
            assert sets[0]["reps"] == 10
            assert sets[0]["distance_meters"] is None
            assert sets[0]["duration_seconds"] is None
            assert sets[0]["rpe"] is None

    def test_events_maintain_index_order(self) -> None:
        """Events preserve their position from the API response."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_sdk.return_value._request.return_value = self._mock_response(
                self._raw_api_response(
                    [
                        {"type": "updated", "workout": self._workout_dict("w001")},
                        {"type": "updated", "workout": self._workout_dict("w002")},
                        {"type": "deleted"},
                    ]
                )
            )
            client = HevyClient(api_key="test-key")

            result = client.get_events(since="2024-01-01T00:00:00Z")

            assert result.events[0].index == 0
            assert result.events[1].index == 1
            assert result.events[2].index == 2

    def test_empty_events_page(self) -> None:
        """An empty events response returns empty events list."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_sdk.return_value._request.return_value = self._mock_response(
                self._raw_api_response([], page=1, page_count=3)
            )
            client = HevyClient(api_key="test-key")

            result = client.get_events(since="2024-01-01T00:00:00Z")

            assert len(result.events) == 0
            assert result.page == 1
            assert result.page_count == 3


class TestGetExerciseTemplates:
    """HevyClient.get_exercise_templates fetches all templates with pagination."""

    @staticmethod
    def _mock_httpx_response(json_data: dict) -> MagicMock:
        """Build a mock httpx response with .json() method."""
        resp = MagicMock()
        resp.json.return_value = json_data
        resp.raise_for_status.return_value = None
        return resp

    @staticmethod
    def _raw_templates_page(
        templates: list[dict],
        page: int = 1,
        page_count: int = 1,
    ) -> dict:
        """Return a dict that simulates the raw /v1/exercise_templates JSON."""
        return {
            "page": page,
            "page_count": page_count,
            "exercise_templates": templates,
        }

    @staticmethod
    def _raw_template(
        template_id: str,
        title: str,
    ) -> dict:
        """Return a raw exercise template dict (as returned by Hevy API)."""
        return {
            "id": template_id,
            "title": title,
            "type": "strength",
            "primary_muscle_group": "Chest",
            "secondary_muscle_groups": ["Triceps", "Front Delts"],
            "is_custom": False,
        }

    def _setup_mock(
        self, mock_sdk: MagicMock, mock_httpx: MagicMock
    ) -> None:
        """Configure mock SDK client for template tests."""
        mock_sdk.return_value._client = mock_httpx
        mock_sdk.return_value.config.base_url = "https://api.hevyapp.com"
        mock_sdk.return_value._build_headers.return_value = {"api-key": "test"}

    def test_fetches_templates(self) -> None:
        """get_exercise_templates returns list of template dicts."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_httpx = MagicMock()
            mock_httpx.get.return_value = self._mock_httpx_response(
                self._raw_templates_page(
                    [self._raw_template("t001", "Bench Press")]
                )
            )
            self._setup_mock(mock_sdk, mock_httpx)
            client = HevyClient(api_key="test-key")

            result = client.get_exercise_templates()

            assert len(result) == 1
            assert result[0]["id"] == "t001"

    def test_converts_template_fields(self) -> None:
        """Template dict has fields expected by repo.upsert_templates."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_httpx = MagicMock()
            mock_httpx.get.return_value = self._mock_httpx_response(
                self._raw_templates_page(
                    [self._raw_template("t001", "Bench Press")]
                )
            )
            self._setup_mock(mock_sdk, mock_httpx)
            client = HevyClient(api_key="test-key")

            result = client.get_exercise_templates()

            assert len(result) == 1
            t = result[0]
            assert t["id"] == "t001"
            assert t["title"] == "Bench Press"
            assert t["type"] == "strength"
            assert t["primary_muscle_group"] == "Chest"
            assert "Triceps" in t["other_muscle_groups"]
            assert t["is_custom"] == 0

    def test_paginates_multiple_pages(self) -> None:
        """get_exercise_templates fetches all pages and returns merged list."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_httpx = MagicMock()
            mock_httpx.get.side_effect = [
                self._mock_httpx_response(
                    self._raw_templates_page(
                        [self._raw_template("t001", "Bench Press")],
                        page=1,
                        page_count=2,
                    )
                ),
                self._mock_httpx_response(
                    self._raw_templates_page(
                        [self._raw_template("t002", "Overhead Press")],
                        page=2,
                        page_count=2,
                    )
                ),
            ]
            self._setup_mock(mock_sdk, mock_httpx)
            client = HevyClient(api_key="test-key")

            result = client.get_exercise_templates()

            assert len(result) == 2
            assert result[0]["id"] == "t001"
            assert result[1]["id"] == "t002"

    def test_empty_templates_list(self) -> None:
        """An empty templates response returns an empty list."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_httpx = MagicMock()
            mock_httpx.get.return_value = self._mock_httpx_response(
                self._raw_templates_page([], page=1, page_count=1)
            )
            self._setup_mock(mock_sdk, mock_httpx)
            client = HevyClient(api_key="test-key")

            result = client.get_exercise_templates()

            assert result == []

    def test_single_page_no_extra_call(self) -> None:
        """When page_count is 1, only one API call is made."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_httpx = MagicMock()
            mock_httpx.get.return_value = self._mock_httpx_response(
                self._raw_templates_page(
                    [self._raw_template("t001", "Bench Press")],
                    page=1,
                    page_count=1,
                )
            )
            self._setup_mock(mock_sdk, mock_httpx)
            client = HevyClient(api_key="test-key")

            result = client.get_exercise_templates()

            assert len(result) == 1
            mock_httpx.get.assert_called_once()
