"""Adapter wrapping the hevy-api-wrapper SDK into domain-friendly types.

The HevyClient class wraps ``hevy_api_wrapper.Client`` and converts its
Pydantic models into plain Python dicts and simple dataclasses.  This
isolates the rest of the codebase from SDK API changes — only this file
needs to change when the SDK version changes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from hevy_api_wrapper import Client as SdkClient


# ---------------------------------------------------------------------------
# Domain dataclasses
# ---------------------------------------------------------------------------


@dataclass
class WorkoutEvent:
    """A single workout change event from the Hevy events endpoint.

    Attributes:
        index: Position of this event within the page (0-based).
        type: ``"updated"`` or ``"deleted"``.
        workout: The full workout dict for updated events, or ``None``
            for deleted events.
    """

    index: int
    type: Literal["updated", "deleted"]
    workout: dict[str, Any] | None


@dataclass
class EventsPage:
    """A page of workout events returned by the Hevy API.

    Attributes:
        page: Current page number (1-indexed).
        page_count: Total number of pages available.
        total_count: Total number of events on this page.
        events: List of ``WorkoutEvent`` objects.
    """

    page: int
    page_count: int
    total_count: int
    events: list[WorkoutEvent]


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class HevyClient:
    """Thin adapter over ``hevy_api_wrapper.Client``.

    Usage::

        client = HevyClient(api_key="my-api-key")
        page = client.get_events(since="2024-01-01T00:00:00Z")
        templates = client.get_exercise_templates()
    """

    def __init__(self, api_key: str) -> None:
        self._client = SdkClient(api_key=api_key)

    def get_events(
        self, since: str, page: int = 1, page_size: int = 10
    ) -> EventsPage:
        """Fetch a page of workout change events.

        Bypasses the SDK's pydantic model because the API returns
        a ``workouts`` key while the SDK expects ``events``.

        Args:
            since: ISO 8601 timestamp — only events after this time are
                returned.
            page: Page number (1-indexed, defaults to 1).
            page_size: Items per page (1-10, defaults to 10).

        Returns:
            An ``EventsPage`` with converted ``WorkoutEvent`` entries.
        """
        params: dict[str, Any] = {"since": since}
        if page:
            params["page"] = page
            params["pageSize"] = page_size

        resp = self._client._request(
            "GET", "/v1/workouts/events", params=params
        )
        data = resp.json()

        raw_events: list[dict[str, Any]] = data.get("workouts", [])

        events: list[WorkoutEvent] = []
        for i, raw in enumerate(raw_events):
            if raw.get("type") == "updated" and "workout" in raw:
                events.append(
                    WorkoutEvent(
                        index=i,
                        type="updated",
                        workout=_raw_workout_to_dict(raw["workout"]),
                    )
                )
            else:  # deleted
                events.append(
                    WorkoutEvent(
                        index=i,
                        type="deleted",
                        workout=None,
                    )
                )

        return EventsPage(
            page=data.get("page", page),
            page_count=data.get("page_count", 1),
            total_count=len(events),
            events=events,
        )

    def get_exercise_templates(self) -> list[dict[str, Any]]:
        """Fetch all exercise templates across all pages.

        Paginates through every page (page_size=100) and returns the
        aggregated list of template dicts in repo-compatible format.

        Bypasses SDK pydantic models to avoid ValidationError on new
        exercise types (``floors_duration``, ``steps_duration``, etc.)
        that the SDK enum doesn't include.

        Returns:
            List of template dicts with keys ``id``, ``title``, ``type``,
            ``primary_muscle_group``, ``other_muscle_groups`` (JSON string),
            ``equipment``, and ``is_custom``.
        """
        templates: list[dict[str, Any]] = []
        base_url = f"{self._client.config.base_url}v1/exercise_templates"
        headers = self._client._build_headers()

        page = 1
        page_count = 1

        while page <= page_count:
            raw = self._client._client.get(
                base_url,
                headers=headers,
                params={"page": page, "pageSize": 100},
            )
            raw.raise_for_status()
            data = raw.json()

            if page_count == 1 and page == 1:
                page_count = data.get("page_count", 1)

            for t in data.get("exercise_templates", []):
                templates.append(_raw_template_to_dict(t))

            page += 1

        return templates

    def get_routines(self) -> list[dict[str, Any]]:
        """Fetch all routines across all pages.

        Paginates through every page (page_size=10) and returns the
        aggregated list of routine dicts in repo-compatible format.

        Returns:
            List of routine dicts with keys ``id``, ``title``,
            ``folder_id``, ``created_at``, and ``updated_at``.
        """
        routines: list[dict[str, Any]] = []

        resp = self._client.routines.get_routines(page=1, page_size=10)
        for r in resp.routines:
            routines.append(_routine_to_dict(r))

        page = 2
        while page <= resp.page_count:
            resp = self._client.routines.get_routines(page=page, page_size=10)
            for r in resp.routines:
                routines.append(_routine_to_dict(r))
            page += 1

        return routines


# ---------------------------------------------------------------------------
# Internal helpers — SDK model → dict conversion
# ---------------------------------------------------------------------------


def _workout_to_dict(workout: Any) -> dict[str, Any]:
    """Convert a SDK Workout model to a plain dict for repo functions.

    Maps the SDK field names to the format expected by
    ``db.repo.upsert_workout``:

    * ``exercise.index`` → ``exercise["sort_order"]``
    * ``set.index`` → ``set["set_index"]``
    """
    exercises = []
    for ex in workout.exercises:
        sets = []
        for s in ex.sets:
            sets.append(
                {
                    "set_index": s.index,
                    "type": s.type,
                    "weight_kg": s.weight_kg,
                    "reps": s.reps,
                    "distance_meters": s.distance_meters,
                    "duration_seconds": s.duration_seconds,
                    "rpe": s.rpe,
                }
            )
        exercises.append(
            {
                "exercise_template_id": ex.exercise_template_id,
                "title": ex.title,
                "notes": ex.notes or "",
                "sort_order": ex.index,
                "sets": sets,
            }
        )

    return {
        "id": workout.id,
        "title": workout.title,
        "description": workout.description or "",
        "start_time": workout.start_time,
        "end_time": workout.end_time,
        "updated_at": workout.updated_at,
        "created_at": workout.created_at,
        "routine_id": getattr(workout, "routine_id", None),
        "exercises": exercises,
    }


def _raw_workout_to_dict(workout: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw API workout dict to the repo-compatible format.

    Mirrors ``_workout_to_dict`` but works on raw JSON dicts instead of
    SDK pydantic models — field names ``index`` → ``sort_order`` /
    ``set_index``.
    """
    exercises = []
    for ex in workout.get("exercises", []):
        sets = []
        for s in ex.get("sets", []):
            sets.append(
                {
                    "set_index": s.get("index"),
                    "type": s.get("type"),
                    "weight_kg": s.get("weight_kg"),
                    "reps": s.get("reps"),
                    "distance_meters": s.get("distance_meters"),
                    "duration_seconds": s.get("duration_seconds"),
                    "rpe": s.get("rpe"),
                }
            )
        exercises.append(
            {
                "exercise_template_id": ex.get("exercise_template_id"),
                "title": ex.get("title"),
                "notes": ex.get("notes") or "",
                "sort_order": ex.get("index"),
                "sets": sets,
            }
        )

    return {
        "id": workout.get("id"),
        "title": workout.get("title"),
        "description": workout.get("description") or "",
        "start_time": workout.get("start_time"),
        "end_time": workout.get("end_time"),
        "updated_at": workout.get("updated_at"),
        "created_at": workout.get("created_at"),
        "routine_id": workout.get("routine_id"),
        "exercises": exercises,
    }


def _routine_to_dict(routine: Any) -> dict[str, Any]:
    """Convert a SDK Routine model to a plain dict for repo functions.

    Maps SDK field names to the format expected by
    ``db.repo.upsert_routines``:

    * ``folder_id`` (Optional[int]) → ``folder_id`` (int or None)
    """
    return {
        "id": routine.id,
        "title": routine.title,
        "folder_id": routine.folder_id,
        "created_at": routine.created_at,
        "updated_at": routine.updated_at,
    }


def _template_to_dict(template: Any) -> dict[str, Any]:
    """Convert a SDK ExerciseTemplate model to a plain dict.

    Maps SDK field names to the format expected by
    ``db.repo.upsert_templates``:

    * ``secondary_muscle_groups`` (list) → ``other_muscle_groups`` (JSON string)
    * ``is_custom`` (bool) → ``is_custom`` (int)
    * ``type`` (enum) → string value
    * ``primary_muscle_group`` (enum) → string value
    """
    return {
        "id": template.id,
        "title": template.title,
        "type": template.type if isinstance(template.type, str) else template.type.value,
        "primary_muscle_group": (
            template.primary_muscle_group
            if isinstance(template.primary_muscle_group, str)
            else template.primary_muscle_group.value
        ),
        "other_muscle_groups": json.dumps(template.secondary_muscle_groups),
        "equipment": "",
        "is_custom": int(template.is_custom),
    }


def _raw_template_to_dict(template: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw API exercise template dict to repo-compatible format.

    Mirrors ``_template_to_dict`` but works on raw JSON dicts instead of
    SDK pydantic models — avoids ValidationError on new exercise types
    that the SDK enum doesn't include.
    """
    return {
        "id": template.get("id", ""),
        "title": template.get("title", ""),
        "type": template.get("type", ""),
        "primary_muscle_group": template.get("primary_muscle_group", ""),
        "other_muscle_groups": json.dumps(
            template.get("secondary_muscle_groups", [])
        ),
        "equipment": "",
        "is_custom": int(template.get("is_custom", False)),
    }
