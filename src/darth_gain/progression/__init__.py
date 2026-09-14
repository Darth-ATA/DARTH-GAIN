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
from datetime import date, datetime

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

_SKIP_TYPES = frozenset({"reps_only", "distance"})


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

    def check(self, template_id: str, check_date: str | None = None) -> ProgressionStatus:
        """Run a progression check for the given exercise template.

        Args:
            template_id: The exercise template ID to check.
            check_date: Optional date string (YYYY-MM-DD) for historical checks.
                        Defaults to current date via SQLite datetime('now').

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
                deload_recommended=False,
                deload_weight_kg=None,
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
                deload_recommended=False,
                deload_weight_kg=None,
            )

        # 4. TIME-GATE: Check for detraining/deload before normal progression logic
        #    Only applies to weight exercises (not duration or skip types)
        exercise_type = template.get("type", "")
        if exercise_type not in _SKIP_TYPES and exercise_type != "duration":
            deload_result = self._check_deload(template_id, config, check_date)
            if deload_result is not None:
                return deload_result

        # 5. Route duration exercises to separate handler
        if exercise_type == "duration":
            return self._check_duration(template, config)

        # 6. Check if exercise type qualifies for weight progression
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
                deload_recommended=False,
                deload_weight_kg=None,
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
                deload_recommended=False,
                deload_weight_kg=None,
            )

        # 7. Get normal sets
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
                deload_recommended=False,
                deload_weight_kg=None,
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
                deload_recommended=False,
                deload_weight_kg=None,
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
                deload_recommended=False,
                deload_weight_kg=None,
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
                deload_recommended=False,
                deload_weight_kg=None,
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
            deload_recommended=False,
            deload_weight_kg=None,
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
            increment=config.weight_increment,
            deload_recommended=False,
            deload_weight_kg=None,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_duration(
        self,
        template: dict,
        config: ProgressionConfig,
    ) -> ProgressionStatus:
        """Duration-based progression: increase target time instead of weight.

        Uses the same double-progression logic but with ``duration_seconds``
        instead of reps and weight.

        Args:
            template: Exercise template dict (must be type=duration).
            config: Progression config where rep_min/rep_max define the
                    target time range in seconds, and weight_increment is
                    the time increment in seconds.

        Returns:
            A ``ProgressionStatus`` with time-based values.
        """
        template_id = template["id"]

        # 1. Get normal sets (includes duration_seconds)
        sets = get_normal_sets(self.conn, template_id)
        if not sets:
            self._persist_history(
                template_id,
                "insufficient_data",
                current_weight=None,
                recommended_weight=None,
                details={"reason": "no_normal_sets_found"},
                deload_recommended=False,
                deload_weight_kg=None,
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
                deload_recommended=False,
                deload_weight_kg=None,
            )

        # 2. Group by workout date
        groups: dict[str, list[dict]] = {}
        for s in sets:
            groups.setdefault(s["start_time"], []).append(s)
        ordered_dates = list(groups.keys())  # latest first
        total_workouts = len(ordered_dates)

        # 3. Evaluate last N sessions (same adaptive threshold as weight)
        n_sessions = min(3, len(ordered_dates))
        threshold = 2 if n_sessions >= 3 else n_sessions
        recent_dates = ordered_dates[:n_sessions]

        sessions_at_top = 0
        total_valid_sessions = 0
        most_recent_valid_sets: list[dict] = []
        most_recent_date = ""

        for date in recent_dates:
            session_sets = groups[date]
            valid = [s for s in session_sets if s["duration_seconds"] is not None]
            if not valid:
                continue
            if not most_recent_date:
                most_recent_date = date
                most_recent_valid_sets = valid
            total_valid_sessions += 1
            durations = [s["duration_seconds"] for s in valid]
            if all(d >= config.rep_max for d in durations):
                sessions_at_top += 1

        if not most_recent_valid_sets:
            self._persist_history(
                template_id,
                "insufficient_data",
                current_weight=None,
                recommended_weight=None,
                details={
                    "reason": "all_sets_have_null_duration",
                    "total_workouts_analyzed": total_workouts,
                },
                deload_recommended=False,
                deload_weight_kg=None,
            )
            return ProgressionStatus(
                exercise_template_id=template_id,
                exercise_name=template["title"],
                rep_range=(config.rep_min, config.rep_max),
                current_weight_kg=None,
                latest_reps=[],
                top_of_range_reached=False,
                recommendation="Insufficient data — all sets have null duration",
                error=None,
                deload_recommended=False,
                deload_weight_kg=None,
            )

        # 4. Determine working time from most recent session (mode, tie → longer)
        times = [s["duration_seconds"] for s in most_recent_valid_sets]
        working_time = self._resolve_working_weight(times)  # mode, tie → max

        # 5. Check threshold
        top_of_range = sessions_at_top >= threshold
        latest_times = [s["duration_seconds"] for s in most_recent_valid_sets]

        # 6. Build result
        if top_of_range:
            recommended_time = working_time + config.weight_increment
            status = "progress"
            recommendation = f"increase to {recommended_time}s"
        else:
            recommended_time = None
            status = "maintain"
            recommendation = f"keep at {working_time}s"

        details = {
            "total_workouts_analyzed": total_workouts,
            "sessions_evaluated": n_sessions,
            "sessions_at_top": sessions_at_top,
            "sessions_threshold": threshold,
            "most_recent_workout_date": most_recent_date,
            "sets_analyzed": len(most_recent_valid_sets),
            "working_time_seconds": working_time,
            "time_increment_seconds": config.weight_increment,
            "time_range": [config.rep_min, config.rep_max],
            "latest_times": latest_times,
            "exercise_type": "duration",
        }

        # 7. Persist history (store time as weight for backward compat)
        self._persist_history(
            template_id,
            status,
            current_weight=working_time,
            recommended_weight=recommended_time,
            details=details,
            deload_recommended=False,
            deload_weight_kg=None,
        )

        return ProgressionStatus(
            exercise_template_id=template_id,
            exercise_name=template["title"],
            rep_range=(config.rep_min, config.rep_max),
            current_weight_kg=working_time,
            latest_reps=latest_times,
            top_of_range_reached=top_of_range,
            recommendation=recommendation,
            error=None,
            increment=config.weight_increment,
            deload_recommended=False,
            deload_weight_kg=None,
        )

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

    def _check_deload(
        self,
        template_id: str,
        config: ProgressionConfig,
        check_date: str | None,
    ) -> ProgressionStatus | None:
        """Check if detraining/deload should be triggered for this exercise.

        Args:
            template_id: The exercise template ID.
            config: The progression config with deload settings.
            check_date: Optional date string (YYYY-MM-DD) for historical checks.
                       Defaults to current date via SQLite datetime('now').

        Returns:
            ProgressionStatus with "deload_recommended" if deload triggers,
            None if normal progression logic should continue.
        """
        # Get the most recent workout date from normal sets
        sets = get_normal_sets(self.conn, template_id)
        if not sets:
            # No history → insufficient_data (not deload)
            return None

        # Get last workout date (first set since ordered by start_time DESC)
        last_workout_date = sets[0]["start_time"]
        if not last_workout_date:
            return None

        # Parse dates and calculate weeks elapsed
        # Use date() to compare UTC date strings only (ignore time-of-day)
        if check_date is None:
            # Use SQLite's current date
            cursor = self.conn.execute("SELECT date('now')")
            check_date = cursor.fetchone()[0]

        try:
            last_date = date.fromisoformat(last_workout_date.split("T")[0].split(" ")[0])
            check_date_parsed = date.fromisoformat(check_date.split("T")[0].split(" ")[0])
        except (ValueError, AttributeError):
            # Invalid date format → skip deload check
            return None

        # Calculate days elapsed, handle future dates
        days_elapsed = (check_date_parsed - last_date).days
        if days_elapsed < 0:
            days_elapsed = 0

        weeks_elapsed = days_elapsed // 7

        # Calculate effective threshold with training level adjustment
        # novice: -1 (min 1), intermediate: 0, advanced: +1
        training_level_adjustment = {"novice": -1, "intermediate": 0, "advanced": 1}
        adjustment = training_level_adjustment.get(config.training_level, 0)
        effective_threshold = max(1, config.deload_after_weeks + adjustment)

        # Check if deload triggers
        if weeks_elapsed <= effective_threshold:
            return None

        # Deload triggered - compute working weight from most recent session
        # Group by workout date to find most recent session's sets
        groups: dict[str, list[dict]] = {}
        for s in sets:
            groups.setdefault(s["start_time"], []).append(s)
        most_recent_date = list(groups.keys())[0]
        most_recent_sets = groups[most_recent_date]

        # Get valid weights from most recent session
        valid_weights = [
            s["weight_kg"] for s in most_recent_sets
            if s["weight_kg"] is not None
        ]
        if not valid_weights:
            # No valid weights → insufficient_data
            return None

        working_weight = self._resolve_working_weight(valid_weights)

        # Calculate deload percent (cap at 40% for gaps > 12 weeks)
        deload_percent = config.deload_percent
        warning = None
        if weeks_elapsed > 12:
            deload_percent = 40
            warning = "gap_exceeds_12_weeks_capped_at_40_percent"

        # Calculate deload weight: round(working_weight * (1 - deload_percent/100), 1)
        deload_weight_kg = round(working_weight * (1 - deload_percent / 100), 1)

        # Build details
        details = {
            "gap_weeks": weeks_elapsed,
            "effective_threshold": effective_threshold,
            "deload_percent_used": deload_percent,
            "training_level": config.training_level,
            "last_workout_date": last_workout_date,
            "check_date": check_date,
        }
        if warning:
            details["warning"] = warning

        # Persist history
        self._persist_history(
            template_id,
            "deload_recommended",
            current_weight=working_weight,
            recommended_weight=deload_weight_kg,
            details=details,
            deload_recommended=True,
            deload_weight_kg=deload_weight_kg,
        )

        # Get template for exercise name
        template = get_template(self.conn, template_id)
        exercise_name = template["title"] if template else ""

        return ProgressionStatus(
            exercise_template_id=template_id,
            exercise_name=exercise_name,
            rep_range=(config.rep_min, config.rep_max),
            current_weight_kg=working_weight,
            latest_reps=[],
            top_of_range_reached=False,
            recommendation=f"deload to {deload_weight_kg} kg",
            error=None,
            increment=config.weight_increment,
            deload_recommended=True,
            deload_weight_kg=deload_weight_kg,
        )

    def _persist_history(
        self,
        template_id: str,
        status: str,
        current_weight: float | None,
        recommended_weight: float | None,
        details: dict | None,
        deload_recommended: bool = False,
        deload_weight_kg: float | None = None,
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
            deload_recommended=deload_recommended,
            deload_weight_kg=deload_weight_kg,
        )
        add_history_entry(self.conn, entry)