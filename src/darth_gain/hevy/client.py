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

        Args:
            since: ISO 8601 timestamp — only events after this time are
                returned.
            page: Page number (1-indexed, defaults to 1).
            page_size: Items per page (1-10, defaults to 10).

        Returns:
            An ``EventsPage`` with converted ``WorkoutEvent`` entries.
        """
        resp = self._client.workouts.get_events(
            since=since, page=page, page_size=page_size
        )

        events: list[WorkoutEvent] = []
        for i, event in enumerate(resp.events):
            if event.type == "updated":
                events.append(
                    WorkoutEvent(
                        index=i,
                        type="updated",
                        workout=_workout_to_dict(event.workout),
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
            page=resp.page,
            page_count=resp.page_count,
            total_count=len(events),
            events=events,
        )

    def get_exercise_templates(self) -> list[dict[str, Any]]:
        """Fetch all exercise templates across all pages.

        Uses the SDK's raw HTTP client directly instead of its pydantic-
        validated endpoint. This avoids crashes when the Hevy API adds new
        enum values (e.g. ``floors_duration``, ``steps_duration``) that the
        SDK hasn't caught up with yet.

        Paginates through every page (page_size=100) and returns the
        aggregated list of template dicts in repo-compatible format.

        Returns:
            List of template dicts with keys ``id``, ``title``, ``type``,
            ``primary_muscle_group``, ``other_muscle_groups`` (JSON string),
            ``equipment``, and ``is_custom``.
        """
        templates: list[dict[str, Any]] = []

        data = self._fetch_templates_page(page=1, page_size=100)
        for t in data["exercise_templates"]:
            templates.append(_raw_template_to_dict(t))

        page = 2
        while page <= data["page_count"]:
            data = self._fetch_templates_page(page=page, page_size=100)
            for t in data["exercise_templates"]:
                templates.append(_raw_template_to_dict(t))
            page += 1

        return templates

    def _fetch_templates_page(
        self, page: int, page_size: int = 100
    ) -> dict[str, Any]:
        """Fetch a single page of exercise templates as raw JSON dict.

        Bypasses the SDK's pydantic model to avoid validation errors on
        new API response fields.

        Raises:
            hevy_api_wrapper.exceptions.HevyAPIError: On non-2xx status.
        """
        from hevy_api_wrapper.endpoints.exercise_templates import raise_for_status

        resp = self._client._request(
            "GET",
            "/v1/exercise_templates",
            params={"page": page, "pageSize": page_size},
        )
        data: dict[str, Any] = resp.json()
        if resp.status_code >= 400:
            message = (
                data.get("message") if isinstance(data, dict) else None
            ) or resp.text
            code = data.get("code") if isinstance(data, dict) else None
            raise_for_status(
                status_code=resp.status_code,
                message=message,
                error_code=code,
                details=data,
                request_id=None,
            )
        return data


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
        "exercises": exercises,
    }


def _raw_template_to_dict(t: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw API template dict to repo-compatible format.

    Works directly from the JSON response (no pydantic models) so new
    API fields don't cause validation errors.
    """
    return {
        "id": t["id"],
        "title": t.get("title", ""),
        "type": t.get("type", ""),
        "primary_muscle_group": t.get("primary_muscle_group", ""),
        "other_muscle_groups": json.dumps(t.get("secondary_muscle_groups", [])),
        "equipment": "",
        "is_custom": int(t.get("is_custom", False)),
    }


def _template_to_dict(template: Any) -> dict[str, Any]:
    """Convert a SDK ExerciseTemplate model to a plain dict.

    Maps SDK field names to the format expected by
    ``db.repo.upsert_templates``:

    * ``secondary_muscle_groups`` (list) → ``other_muscle_groups`` (JSON string)
    * ``is_custom`` (bool) → ``is_custom`` (int)
    * ``type`` (enum) → string value
    * ``primary_muscle_group`` (enum) → string value

    Note:
        Prefer :func:`_raw_template_to_dict` for new code. This function
        is kept for backward compatibility with existing tests that mock
        the SDK model layer.
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
