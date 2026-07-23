"""Domain dataclasses for the progression engine.

Provides:
  - ProgressionConfig: per-exercise configuration for rep ranges and increments
  - ProgressionStatus: result of a progression check
  - ProgressionHistoryEntry: persisted history of progression checks
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProgressionConfig:
    """Per-exercise configuration for double progression.

    Attributes:
        exercise_template_id: FK to exercise_templates.id.
        rep_min: Minimum reps in the target rep range (default 8).
        rep_max: Maximum reps in the target rep range (default 12).
        weight_increment: Weight to add when progressing (kg, default 2.5).
        enabled: Whether automatic progression checking is enabled (default True).
    """

    exercise_template_id: str
    rep_min: int = 8
    rep_max: int = 12
    weight_increment: float = 2.5
    enabled: bool = True


@dataclass
class ProgressionStatus:
    """Result of a progression check for an exercise.

    Attributes:
        exercise_template_id: The exercise template that was checked.
        exercise_name: Human-readable name of the exercise.
        rep_range: The (rep_min, rep_max) configured for this exercise.
        current_weight_kg: Working weight at check time, or None.
        latest_reps: Reps performed in the most recent workout's normal sets.
        top_of_range_reached: Whether ALL normal set reps >= rep_max.
        recommendation: Human-readable recommendation string.
        error: Error message if check failed, None otherwise.
        increment: Configured weight/time increment for this exercise.
    """

    exercise_template_id: str
    exercise_name: str
    rep_range: tuple[int, int]
    current_weight_kg: float | None
    latest_reps: list[int]
    top_of_range_reached: bool
    recommendation: str
    error: str | None
    increment: float = 2.5


@dataclass
class ProgressionHistoryEntry:
    """A single progression check result persisted to the database.

    Attributes:
        id: Auto-incremented primary key.
        exercise_template_id: FK to exercise_templates.id.
        checked_at: ISO 8601 timestamp of when the check was performed.
        status: One of ``progress``, ``maintain``, ``insufficient_data``, ``skipped``.
        current_weight_kg: Working weight at check time, or None.
        recommended_weight_kg: Recommended new weight if progressing, or None.
        details: Optional JSON string with per-workout breakdown.
    """

    id: int
    exercise_template_id: str
    checked_at: str
    status: str
    current_weight_kg: float | None
    recommended_weight_kg: float | None
    details: str | None
