# Progression Engine Specification

## Purpose

Deterministic double progression algorithm: analyzes historical set data for an exercise, checks if all normal sets in the most recent workout reach the top of the configured rep range, and recommends a weight increase when criteria are met.

## Data Contract

### `progression_history` table

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `exercise_template_id` | TEXT NOT NULL | FK to `exercise_templates.id` |
| `checked_at` | TEXT NOT NULL | ISO 8601 timestamp of check |
| `status` | TEXT NOT NULL | `"progress"` \| `"maintain"` \| `"insufficient_data"` |
| `current_weight_kg` | REAL | Most common normal-set weight at check time |
| `recommended_weight_kg` | REAL | New weight if status = "progress", else NULL |
| `details` | TEXT | JSON blob with per-workout breakdown |

## Requirements

### Requirement: Algorithm processes only normal sets chronologically

The engine MUST query all non-deleted sets for an exercise template where `type = 'normal'`, joined to workouts, ordered by `workouts.start_time ASC`. Warmup, dropset, and failure sets SHALL be excluded.

#### Scenario: Only normal sets considered

- GIVEN an exercise has 3 normal sets (10 reps at 80kg) and 2 warmup sets with lighter weight
- WHEN the engine runs progression check
- THEN only the 3 normal sets are included in the analysis

### Requirement: One full workout at rep max triggers progress recommendation

When ALL normal sets in the most recent workout have `reps >= rep_max`, the engine MUST return status `"progress"` with `recommended_weight_kg = current_weight_kg + weight_increment`.

#### Scenario: All sets hit rep_max → progress

- GIVEN an exercise with `rep_max = 12` and last workout has 3 normal sets of 12, 12, 12 reps at 80kg
- WHEN the engine runs the check
- THEN status is `"progress"` and `recommended_weight_kg` is `82.5`

#### Scenario: One set below rep_max → maintain

- GIVEN an exercise with `rep_max = 12` and last workout has 3 normal sets of 12, 11, 12 reps at 80kg
- WHEN the engine runs the check
- THEN status is `"maintain"` and `recommended_weight_kg` is NULL

#### Scenario: Multiple workouts — only most recent matters

- GIVEN a workout 7 days ago with 12, 12, 12 reps and a workout yesterday with 10, 10, 10 reps
- WHEN the engine runs the check
- THEN status is `"maintain"` (latest workout below rep_max)

### Requirement: Sets beyond rep_max also count as meeting criteria

Sets with `reps > rep_max` satisfy the "at or above rep_max" condition.

#### Scenario: Sets exceed rep_max

- GIVEN `rep_max = 10` and last workout has 12, 11, 10 reps
- WHEN the engine runs the check
- THEN status is `"progress"`

### Requirement: Working weight resolves to most common normal-set weight

If normal sets within the most recent workout have varying weights, the engine MUST use the most frequently occurring weight as `current_weight_kg`. On a tie, the heavier weight SHALL be used.

#### Scenario: Inconsistent weights use most common

- GIVEN a workout with sets: 80kg×10, 80kg×10, 85kg×8
- WHEN the engine determines working weight
- THEN `current_weight_kg` is `80.0`

#### Scenario: Tie breaks to heavier weight

- GIVEN a workout with sets: 80kg×10, 85kg×10, 80kg×10, 85kg×10
- WHEN the engine determines working weight
- THEN `current_weight_kg` is `85.0`

### Requirement: NULL weight_kg or reps are skipped

Sets where `weight_kg IS NULL` or `reps IS NULL` SHALL be excluded from the analysis for that workout. If all sets in the most recent workout are NULL, status is `"insufficient_data"`.

#### Scenario: Partial NULLs filtered

- GIVEN a workout with sets: (80kg, 10 reps), (80kg, NULL), (NULL, 12 reps)
- WHEN the engine runs the check
- THEN only the first set is analyzed; remaining valid sets are checked

#### Scenario: All sets NULL → insufficient data

- GIVEN a workout where all normal sets have NULL weight_kg or reps
- WHEN the engine runs the check
- THEN status is `"insufficient_data"`

### Requirement: No workout history returns insufficient_data

The engine MUST return `"insufficient_data"` when no normal sets exist for the exercise template.

#### Scenario: New exercise with no history

- GIVEN an exercise template with zero sets across all workouts
- WHEN the engine runs the check
- THEN status is `"insufficient_data"` and `recommended_weight_kg` is NULL

#### Scenario: All sets deleted

- GIVEN an exercise template where every set has `is_deleted = 1`
- WHEN the engine runs the check
- THEN status is `"insufficient_data"`

### Requirement: Disabled config returns skipped

The engine MUST return `"skipped"` when the exercise template's config has `enabled = 0`.

#### Scenario: Disabled exercise returns skipped

- GIVEN `progression_config.enabled = 0` for an exercise template
- WHEN the engine runs the check
- THEN status is `"skipped"` and `recommended_weight_kg` is NULL

### Requirement: Each check result is persisted to progression_history

The engine MUST insert a row into `progression_history` for every run, recording the status, working weight, recommended weight, and details JSON.

#### Scenario: Progress result persisted

- GIVEN a check returns status `"progress"` with `recommended_weight_kg = 82.5`
- WHEN the engine completes
- THEN a `progression_history` row exists with those values and a non-NULL `checked_at`

## Edge Cases

- **Sets at multiple rep counts**: All sets must reach rep_max individually; averages are not used
- **Zero-weight bodyweight exercises**: `weight_kg = 0` is valid — not treated as NULL
- **Tied most-common weight**: Breaks to heavier, not lighter
- **Partial workout data**: Only non-NULL, normal-type, non-deleted sets are analyzed; remaining sets still trigger progress if all valid ones meet criteria
