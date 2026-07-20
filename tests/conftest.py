"""Shared fixtures for DARTH-GAIN tests.

Provides:
  - In-memory SQLite connection with schema
  - Mock HevyClient for testing sync orchestration
  - Sample domain dataclasses and dicts matching SDK shapes
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

import pytest

from darth_gain.db.engine import create_engine, create_tables


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn() -> sqlite3.Connection:
    """Return an in-memory SQLite connection with all tables created."""
    c = create_engine(":memory:")
    create_tables(c)
    return c


# ---------------------------------------------------------------------------
# Mock HevyClient for testing sync orchestration
# ---------------------------------------------------------------------------


@dataclass
class WorkoutEvent:
    """Minimal WorkoutEvent for test fixtures."""

    index: int
    type: str  # "updated" | "deleted"
    workout: dict[str, Any] | None


@dataclass
class EventsPage:
    """Minimal EventsPage for test fixtures."""

    page: int
    page_count: int
    total_count: int
    events: list[WorkoutEvent]


class MockHevyClient:
    """Fake HevyClient that returns pre-configured data.

    Set ``events_pages`` (list of EventsPage) and ``templates``
    (list of dict) before calling sync. The mock tracks calls for
    assertion.
    """

    def __init__(self) -> None:
        self.events_pages: list[EventsPage] = []
        self.templates: list[dict[str, Any]] = []
        self.get_events_calls: list[tuple[str, int]] = []
        self.get_templates_calls: list[tuple[int, int]] = []

    def get_events(self, since: str, page: int = 1) -> EventsPage:
        self.get_events_calls.append((since, page))
        if self.events_pages:
            return self.events_pages.pop(0)
        return EventsPage(page=1, page_count=1, total_count=0, events=[])

    def get_exercise_templates(self) -> list[dict[str, Any]]:
        self.get_templates_calls.append((1, 100))
        return self.templates


# ---------------------------------------------------------------------------
# Sample response data matching SDK shapes
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_workout_dict() -> dict[str, Any]:
    """A single workout dict as returned by the HevyClient adapter."""
    return {
        "id": "w001",
        "title": "Push Day",
        "description": "Chest and triceps",
        "start_time": "2024-06-01T08:00:00Z",
        "end_time": "2024-06-01T09:00:00Z",
        "updated_at": "2024-06-01T10:00:00Z",
        "created_at": "2024-05-01T08:00:00Z",
        "exercises": [
            {
                "exercise_template_id": "t001",
                "title": "Bench Press",
                "notes": "Warm up properly",
                "sort_order": 0,
                "sets": [
                    {
                        "set_index": 0,
                        "type": "normal",
                        "weight_kg": 80.0,
                        "reps": 10,
                        "distance_meters": None,
                        "duration_seconds": None,
                        "rpe": None,
                    },
                    {
                        "set_index": 1,
                        "type": "normal",
                        "weight_kg": 90.0,
                        "reps": 8,
                        "distance_meters": None,
                        "duration_seconds": None,
                        "rpe": None,
                    },
                ],
            },
            {
                "exercise_template_id": "t002",
                "title": "Overhead Press",
                "notes": "",
                "sort_order": 1,
                "sets": [
                    {
                        "set_index": 0,
                        "type": "normal",
                        "weight_kg": 50.0,
                        "reps": 10,
                        "distance_meters": None,
                        "duration_seconds": None,
                        "rpe": None,
                    }
                ],
            },
        ],
    }


@pytest.fixture
def sample_template_dict() -> dict[str, Any]:
    """A single exercise template dict as returned by the HevyClient adapter."""
    return {
        "id": "t001",
        "title": "Bench Press",
        "type": "strength",
        "primary_muscle_group": "Chest",
        "other_muscle_groups": '["Triceps", "Front Delts"]',
        "equipment": "",
        "is_custom": 0,
    }


@pytest.fixture
def sample_templates_list() -> list[dict[str, Any]]:
    """A list of exercise template dicts for seeding the DB."""
    return [
        {
            "id": "t001",
            "title": "Bench Press",
            "type": "strength",
            "primary_muscle_group": "Chest",
            "other_muscle_groups": '["Triceps", "Front Delts"]',
            "equipment": "",
            "is_custom": 0,
        },
        {
            "id": "t002",
            "title": "Overhead Press",
            "type": "strength",
            "primary_muscle_group": "Shoulders",
            "other_muscle_groups": "[]",
            "equipment": "",
            "is_custom": 0,
        },
    ]


@pytest.fixture
def sample_single_events_page(sample_workout_dict: dict[str, Any]) -> EventsPage:
    """A single-page events response with one updated and one deleted workout."""
    return EventsPage(
        page=1,
        page_count=1,
        total_count=2,
        events=[
            WorkoutEvent(index=0, type="updated", workout=sample_workout_dict),
            WorkoutEvent(index=1, type="deleted", workout=None),
        ],
    )


@pytest.fixture
def sample_multi_events_page(sample_workout_dict: dict[str, Any]) -> list[EventsPage]:
    """Two pages of events for testing pagination."""
    w2 = {**sample_workout_dict, "id": "w002", "title": "Pull Day"}
    return [
        EventsPage(
            page=1,
            page_count=2,
            total_count=3,
            events=[
                WorkoutEvent(index=0, type="updated", workout=w2),
                WorkoutEvent(index=1, type="updated", workout=sample_workout_dict),
            ],
        ),
        EventsPage(
            page=2,
            page_count=2,
            total_count=3,
            events=[
                WorkoutEvent(index=0, type="deleted", workout=None),
            ],
        ),
    ]
