"""Progression engine for DARTH-GAIN double progression algorithm.

Provides the ``ProgressionEngine`` class that implements deterministic
double progression: checks whether recent workouts reached the top of
the rep range across the last N sessions, and recommends a weight
increase when a configurable threshold of sessions hit the top.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter

from darth_gain.progression.models import ProgressionConfig, ProgressionHistoryEntry, ProgressionStatus
from darth_gain.progression.repo import (
    add_history_entry,
    get_config,
    get_normal_sets,
    get_template,
    set_config,
)

# ---------------------------------------------------------------------------
# Exercise types that don't qualify for weight-based progression
# ---------------------------------------------------------------------------

_SKIP_TYPES = frozenset({"reps_only", "duration", "distance"})


class ProgressionEngine:
    """Deterministic double progression engine.

    Analyzes historical set data for an exercise, checks if all normal
    sets in the most recent workout reach the configured rep range
    maximum, and recommends a weight increase when criteria are met.

    Args:
        conn: An open SQLite connection with all tables created.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def check(self, template_id: str) -> ProgressionStatus:
        """Run a progression check for the given exercise template.

        Args:
            template_id: The exercise template ID to check.

        Returns:
            A ``ProgressionStatus`` with the check result.
        """
        # 1. Validate template exists
        template = get_template(self.conn, template_id)
        if template is None:
            return ProgressionStatus(
                exercise_template_id=template_id,
                exercise_name="",
                rep_range=(8, 12),
                current_weight_kg=None,
                latest_reps=[],
                top_of_range_reached=False,
                recommendation="Exercise template not found",
                error="Unknown exercise template",
            )

        # 2. Get config (defaults if not configured)
        config = get_config(self.conn, template_id)

        # 3. Check if disabled
        if not config.enabled:
            self._persist_history(
                template_id,
                "skipped",
                current_weight=None,
                recommended_weight=None,
                details={
                    "reason": "progression_disabled",
                },
            )
            return ProgressionStatus(
                exercise_template_id=template_id,
                exercise_name=template["title"],
                rep_range=(config.rep_min, config.rep_max),
                current_weight_kg=None,
                latest_reps=[],
                top_of_range_reached=False,
                recommendation="Progression checking is disabled for this exercise",
                error=None,
            )

        # 4. Check if exercise type qualifies for progression
        exercise_type = template.get("type", "")
        if exercise_type in _SKIP_TYPES:
            self._persist_history(
                template_id,
                "skipped",
                current_weight=None,
                recommended_weight=None,
                details={
                    "reason": "unqualified_exercise_type",
                    "exercise_type": exercise_type,
                },
            )
            return ProgressionStatus(
                exercise_template_id=template_id,
                exercise_name=template["title"],
                rep_range=(config.rep_min, config.rep_max),
                current_weight_kg=None,
                latest_reps=[],
                top_of_range_reached=False,
                recommendation="Exercise type does not support weight progression",
                error=None,
            )

        # 5. Get normal sets
        sets = get_normal_sets(self.conn, template_id)
        if not sets:
            self._persist_history(
                template_id,
                "insufficient_data",
                current_weight=None,
                recommended_weight=None,
                details={
                    "reason": "no_normal_sets_found",
                },
            )
            return ProgressionStatus(
                exercise_template_id=template_id,
                exercise_name=template["title"],
                rep_range=(config.rep_min, config.rep_max),
                current_weight_kg=None,
                latest_reps=[],
                top_of_range_reached=False,
                recommendation="Insufficient data — no workout history found",
                error=None,
            )

        # 6. Group by workout date (start_time), preserving DESC order
        groups: dict[str, list[dict]] = {}
        for s in sets:
            groups.setdefault(s["start_time"], []).append(s)
        ordered_dates = list(groups.keys())  # latest first

        total_workouts = len(ordered_dates)

        # 7. Evaluate the last N sessions (adaptive threshold)
        #     - 3+ sessions available: need 2 at top of range to progress
        #     - 1-2 sessions: need ALL at top (same as classic double progression)
        n_sessions = min(3, len(ordered_dates))
        threshold = 2 if n_sessions >= 3 else n_sessions
        recent_dates = ordered_dates[:n_sessions]

        sessions_at_top = 0
        total_valid_sessions = 0
        most_recent_valid_sets: list[dict] = []
        most_recent_date = ""

        for date in recent_dates:
            session_sets = groups[date]
            valid = [
                s for s in session_sets
                if s["weight_kg"] is not None and s["reps"] is not None
            ]
            if not valid:
                continue
            if not most_recent_date:
                most_recent_date = date
                most_recent_valid_sets = valid
            total_valid_sessions += 1
            reps = [s["reps"] for s in valid]
            if all(r >= config.rep_max for r in reps):
                sessions_at_top += 1

        sets_filtered_null = sum(
            1 for s in sets[:sum(len(groups[d]) for d in recent_dates)]
            if s["weight_kg"] is None or s["reps"] is None
        )

        if not most_recent_valid_sets:
            self._persist_history(
                template_id,
                "insufficient_data",
                current_weight=None,
                recommended_weight=None,
                details={
                    "reason": "all_sets_have_null_values",
                    "total_workouts_analyzed": total_workouts,
                    "most_recent_workout_date": most_recent_date,
                    "sets_analyzed": 0,
                    "sets_filtered_null": sets_filtered_null,
                },
            )
            return ProgressionStatus(
                exercise_template_id=template_id,
                exercise_name=template["title"],
                rep_range=(config.rep_min, config.rep_max),
                current_weight_kg=None,
                latest_reps=[],
                top_of_range_reached=False,
                recommendation="Insufficient data — all sets have null weight or reps",
                error=None,
            )

        # 8. Determine working weight from most recent session (mode, tie → heavier)
        weights = [s["weight_kg"] for s in most_recent_valid_sets]
        working_weight = self._resolve_working_weight(weights)

        # 9. Check if threshold of recent sessions hit top of range
        top_of_range = sessions_at_top >= threshold
        latest_reps = [s["reps"] for s in most_recent_valid_sets]

        # 10. Build result
        if top_of_range:
            recommended_weight = working_weight + config.weight_increment
            status = "progress"
            recommendation = f"increase to {recommended_weight} kg"
        else:
            recommended_weight = None
            status = "maintain"
            recommendation = f"keep at {working_weight} kg"

        # 11. Persist history
        self._persist_history(
            template_id,
            status,
            current_weight=working_weight,
            recommended_weight=recommended_weight,
            details={
                "total_workouts_analyzed": total_workouts,
                "sessions_evaluated": n_sessions,
                "sessions_at_top": sessions_at_top,
                "sessions_threshold": threshold,
                "most_recent_workout_date": most_recent_date,
                "sets_analyzed": len(most_recent_valid_sets),
                "sets_filtered_null": sets_filtered_null,
                "working_weight_kg": working_weight,
                "weight_increment_kg": config.weight_increment,
                "rep_range": [config.rep_min, config.rep_max],
                "latest_reps": latest_reps,
            },
        )

        return ProgressionStatus(
            exercise_template_id=template_id,
            exercise_name=template["title"],
            rep_range=(config.rep_min, config.rep_max),
            current_weight_kg=working_weight,
            latest_reps=latest_reps,
            top_of_range_reached=top_of_range,
            recommendation=recommendation,
            error=None,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_working_weight(weights: list[float]) -> float:
        """Resolve working weight using mode; tie → heavier.

        Args:
            weights: List of weight values (non-NULL, non-empty).

        Returns:
            The most common weight. On a tie, the heavier weight.
        """
        counts = Counter(weights)
        max_count = max(counts.values())
        candidates = [w for w, c in counts.items() if c == max_count]
        return max(candidates)

    def _persist_history(
        self,
        template_id: str,
        status: str,
        current_weight: float | None,
        recommended_weight: float | None,
        details: dict | None,
    ) -> None:
        """Insert a progression history entry for this check."""
        entry = ProgressionHistoryEntry(
            id=-1,
            exercise_template_id=template_id,
            checked_at="",  # SQLite auto-fills via DEFAULT
            status=status,
            current_weight_kg=current_weight,
            recommended_weight_kg=recommended_weight,
            details=json.dumps(details) if details else None,
        )
        add_history_entry(self.conn, entry)