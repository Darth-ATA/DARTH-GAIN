"""Tests for darth_gain.hevy.client — domain dataclasses and HevyClient adapter."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch


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
    """HevyClient.get_events wraps SDK get_workout_events."""

    def test_calls_sdk_with_correct_params(self) -> None:
        """get_events passes since and page to the SDK method."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_sdk.return_value.workouts.get_events.return_value = (
                _sdk_page_with_events([])
            )
            client = HevyClient(api_key="test-key")

            client.get_events(since="2024-01-01T00:00:00Z", page=2)

            mock_sdk.return_value.workouts.get_events.assert_called_once_with(
                since="2024-01-01T00:00:00Z", page=2, page_size=10
            )

    def test_defaults_to_page_1(self) -> None:
        """get_events defaults to page 1 when not specified."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_sdk.return_value.workouts.get_events.return_value = (
                _sdk_page_with_events([])
            )
            client = HevyClient(api_key="test-key")

            client.get_events(since="2024-01-01T00:00:00Z")

            mock_sdk.return_value.workouts.get_events.assert_called_once_with(
                since="2024-01-01T00:00:00Z", page=1, page_size=10
            )

    def test_returns_events_page_with_metadata(self) -> None:
        """get_events returns EventsPage with page/page_count/total_count."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_sdk.return_value.workouts.get_events.return_value = (
                _sdk_page_with_events([_sdk_updated_event("w001")])
            )
            client = HevyClient(api_key="test-key")

            result = client.get_events(since="2024-01-01T00:00:00Z")

            assert result.page == 1
            assert result.page_count == 3
            assert result.total_count == 1

    def test_converts_updated_event(self) -> None:
        """An updated SDK event becomes WorkoutEvent with type='updated'."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_sdk.return_value.workouts.get_events.return_value = (
                _sdk_page_with_events([_sdk_updated_event("w001")])
            )
            client = HevyClient(api_key="test-key")

            result = client.get_events(since="2024-01-01T00:00:00Z")

            assert len(result.events) == 1
            event = result.events[0]
            assert event.type == "updated"
            assert event.workout is not None
            assert event.workout["id"] == "w001"

    def test_converts_deleted_event(self) -> None:
        """A deleted SDK event becomes WorkoutEvent with type='deleted'."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_sdk.return_value.workouts.get_events.return_value = (
                _sdk_page_with_events([_sdk_deleted_event("w099")])
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
            mock_sdk.return_value.workouts.get_events.return_value = (
                _sdk_page_with_events(
                    [_sdk_updated_event("w001"), _sdk_deleted_event("w099")]
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
        """The converted workout dict has fields expected by repo.upsert_workout."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            sdk_workout = MagicMock()
            sdk_workout.id = "w001"
            sdk_workout.title = "Push Day"
            sdk_workout.description = "Chest"
            sdk_workout.start_time = "2024-06-01T08:00:00Z"
            sdk_workout.end_time = "2024-06-01T09:00:00Z"
            sdk_workout.updated_at = "2024-06-01T10:00:00Z"
            sdk_workout.created_at = "2024-05-01T08:00:00Z"

            sdk_exercise = MagicMock()
            sdk_exercise.index = 0
            sdk_exercise.title = "Bench Press"
            sdk_exercise.notes = "Go heavy"
            sdk_exercise.exercise_template_id = "t001"
            sdk_exercise.supersets_id = None

            sdk_set = MagicMock()
            sdk_set.index = 0
            sdk_set.type = "normal"
            sdk_set.weight_kg = 80.0
            sdk_set.reps = 10
            sdk_set.distance_meters = None
            sdk_set.duration_seconds = None
            sdk_set.rpe = None
            sdk_set.custom_metric = None

            sdk_exercise.sets = [sdk_set]
            sdk_workout.exercises = [sdk_exercise]

            mock_sdk.return_value.workouts.get_events.return_value = (
                _sdk_page_with_events([_sdk_updated_event_raw(sdk_workout)])
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
        """Exercises are converted with index mapped to sort_order."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            sdk_workout = MagicMock()
            sdk_workout.id = "w001"
            sdk_workout.title = "Push Day"
            sdk_workout.description = ""
            sdk_workout.start_time = "2024-06-01T08:00:00Z"
            sdk_workout.end_time = "2024-06-01T09:00:00Z"
            sdk_workout.updated_at = "2024-06-01T10:00:00Z"
            sdk_workout.created_at = "2024-05-01T08:00:00Z"

            ex1 = MagicMock()
            ex1.index = 0
            ex1.title = "Bench Press"
            ex1.notes = ""
            ex1.exercise_template_id = "t001"
            ex1.supersets_id = None
            ex1.sets = []

            ex2 = MagicMock()
            ex2.index = 1
            ex2.title = "Overhead Press"
            ex2.notes = "Slow negatives"
            ex2.exercise_template_id = "t002"
            ex2.supersets_id = None
            ex2.sets = []

            sdk_workout.exercises = [ex1, ex2]

            mock_sdk.return_value.workouts.get_events.return_value = (
                _sdk_page_with_events([_sdk_updated_event_raw(sdk_workout)])
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
        """Sets are converted with index mapped to set_index."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            sdk_workout = MagicMock()
            sdk_workout.id = "w001"
            sdk_workout.title = "Push Day"
            sdk_workout.description = ""
            sdk_workout.start_time = "2024-06-01T08:00:00Z"
            sdk_workout.end_time = "2024-06-01T09:00:00Z"
            sdk_workout.updated_at = "2024-06-01T10:00:00Z"
            sdk_workout.created_at = "2024-05-01T08:00:00Z"

            sdk_set = MagicMock()
            sdk_set.index = 0
            sdk_set.type = "normal"
            sdk_set.weight_kg = 80.0
            sdk_set.reps = 10
            sdk_set.distance_meters = None
            sdk_set.duration_seconds = None
            sdk_set.rpe = None
            sdk_set.custom_metric = None

            sdk_exercise = MagicMock()
            sdk_exercise.index = 0
            sdk_exercise.title = "Bench Press"
            sdk_exercise.notes = ""
            sdk_exercise.exercise_template_id = "t001"
            sdk_exercise.supersets_id = None
            sdk_exercise.sets = [sdk_set]

            sdk_workout.exercises = [sdk_exercise]

            mock_sdk.return_value.workouts.get_events.return_value = (
                _sdk_page_with_events([_sdk_updated_event_raw(sdk_workout)])
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
        """Events preserve their index from the SDK response."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_sdk.return_value.workouts.get_events.return_value = (
                _sdk_page_with_events(
                    [
                        _sdk_updated_event("w001"),
                        _sdk_updated_event("w002"),
                        _sdk_deleted_event("w099"),
                    ]
                )
            )
            client = HevyClient(api_key="test-key")

            result = client.get_events(since="2024-01-01T00:00:00Z")

            assert result.events[0].index == 0
            assert result.events[1].index == 1
            assert result.events[2].index == 2

    def test_empty_events_page(self) -> None:
        """An SDK response with no events returns empty events list."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_sdk.return_value.workouts.get_events.return_value = (
                _sdk_page_with_events([])
            )
            client = HevyClient(api_key="test-key")

            result = client.get_events(since="2024-01-01T00:00:00Z")

            assert len(result.events) == 0
            assert result.page == 1
            assert result.page_count == 3


class TestGetExerciseTemplates:
    """HevyClient.get_exercise_templates fetches all templates with pagination."""

    def _mock_response(
        self, templates: list[dict], page: int = 1, page_count: int = 1
    ) -> MagicMock:
        """Create a mock httpx.Response that returns the given templates JSON."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "exercise_templates": templates,
            "page": page,
            "page_count": page_count,
        }
        return resp

    def test_fetches_templates(self) -> None:
        """get_exercise_templates calls SDK and returns list of dicts."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_sdk.return_value._request.return_value = self._mock_response(
                [_raw_template("t001", "Bench Press")]
            )
            client = HevyClient(api_key="test-key")

            result = client.get_exercise_templates()

            assert len(result) == 1
            assert result[0]["id"] == "t001"

    def test_converts_template_fields(self) -> None:
        """Template dict has fields expected by repo.upsert_templates."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_sdk.return_value._request.return_value = self._mock_response(
                [_raw_template("t001", "Bench Press")]
            )
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
            page1 = self._mock_response(
                [_raw_template("t001", "Bench Press")],
                page=1,
                page_count=2,
            )
            page2 = self._mock_response(
                [_raw_template("t002", "Overhead Press")],
                page=2,
                page_count=2,
            )
            mock_sdk.return_value._request.side_effect = [page1, page2]
            client = HevyClient(api_key="test-key")

            result = client.get_exercise_templates()

            assert len(result) == 2
            assert result[0]["id"] == "t001"
            assert result[1]["id"] == "t002"
            assert mock_sdk.return_value._request.call_count == 2

    def test_empty_templates_list(self) -> None:
        """An empty templates response returns an empty list."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_sdk.return_value._request.return_value = self._mock_response(
                [], page=1, page_count=1
            )
            client = HevyClient(api_key="test-key")

            result = client.get_exercise_templates()

            assert result == []

    def test_single_page_no_extra_call(self) -> None:
        """When page_count is 1, only one API call is made."""
        with patch("darth_gain.hevy.client.SdkClient") as mock_sdk:
            mock_sdk.return_value._request.return_value = self._mock_response(
                [_raw_template("t001", "Bench Press")],
                page=1,
                page_count=1,
            )
            client = HevyClient(api_key="test-key")

            result = client.get_exercise_templates()

            assert len(result) == 1
            mock_sdk.return_value._request.assert_called_once()


# ===========================================================================
# Helper factories — create SDK mock responses
# ===========================================================================


def _sdk_page_with_events(events: list) -> MagicMock:
    """Create a mock PaginatedWorkoutEvents SDK response."""
    page = MagicMock()
    page.page = 1
    page.page_count = 3
    page.events = events
    return page


def _sdk_updated_event(workout_id: str) -> MagicMock:
    """Create a mock UpdatedWorkout SDK event."""
    workout = MagicMock()
    workout.id = workout_id
    workout.title = f"Workout {workout_id}"
    workout.description = ""
    workout.start_time = "2024-06-01T08:00:00Z"
    workout.end_time = "2024-06-01T09:00:00Z"
    workout.updated_at = "2024-06-01T10:00:00Z"
    workout.created_at = "2024-05-01T08:00:00Z"
    workout.exercises = []

    event = MagicMock()
    event.type = "updated"
    event.workout = workout
    return event


def _sdk_updated_event_raw(workout: Any) -> MagicMock:
    """Create a mock UpdatedWorkout with a pre-built workout mock."""
    event = MagicMock()
    event.type = "updated"
    event.workout = workout
    return event


def _sdk_deleted_event(workout_id: str) -> MagicMock:
    """Create a mock DeletedWorkout SDK event."""
    event = MagicMock()
    event.type = "deleted"
    event.id = workout_id
    event.deleted_at = "2024-06-01T10:00:00Z"
    return event


def _raw_template(template_id: str, title: str) -> dict[str, Any]:
    """Create a raw API template dict (matching JSON response shape)."""
    return {
        "id": template_id,
        "title": title,
        "type": "strength",
        "primary_muscle_group": "Chest",
        "secondary_muscle_groups": ["Triceps", "Front Delts"],
        "is_custom": False,
    }
