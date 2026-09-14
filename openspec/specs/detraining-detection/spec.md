# Detraining Detection Specification

## Purpose

Automatic detection of training gaps and deload recommendation based on scientific detraining timelines. The engine compares the most recent workout date for an exercise against the current check date, and when the gap exceeds a configurable threshold (adjusted by training level), it recommends a deload with calculated reduced weight.

## Data Contract

### `progression_config` table — ADDED columns

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `deload_after_weeks` | INTEGER | 2 | Weeks since last workout before deload triggers |
| `deload_percent` | INTEGER | 10 | Percentage reduction for deload weight (5-40) |
| `training_level` | TEXT | 'intermediate' | `'novice'` \| `'intermediate'` \| `'advanced'` — adjusts threshold |

### `progression_history` table — MODIFIED CHECK constraint

| Column | Type | Description |
|--------|------|-------------|
| `status` | TEXT | Extended: `"progress"` \| `"maintain"` \| `"insufficient_data"` \| `"skipped"` \| **`"deload_recommended"`** |

### `ProgressionConfig` — ADDED fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `deload_after_weeks` | int | 2 | Base threshold weeks |
| `deload_percent` | int | 10 | Deload reduction percentage |
| `training_level` | str | "intermediate" | "novice" \| "intermediate" \| "advanced" |

### `ProgressionStatus` — ADDED fields

| Field | Type | Description |
|-------|------|-------------|
| `deload_recommended` | bool | True when status is `"deload_recommended"` |
| `deload_weight_kg` | float \| None | Calculated deload weight when recommended, else None |

### Training Level Threshold Adjustment

| Training Level | Effective `deload_after_weeks` |
|----------------|-------------------------------|
| novice | base - 1 (minimum 1) |
| intermediate | base (default 2) |
| advanced | base + 1 |

## Requirements

### Requirement: Time-gate triggers deload when gap exceeds threshold

The engine MUST find the most recent workout date for the exercise template, calculate weeks elapsed since that workout, and compare against the effective threshold (base `deload_after_weeks` adjusted by `training_level`). If weeks elapsed > effective threshold, status is `"deload_recommended"`.

#### Scenario: Gap exceeds intermediate threshold → deload recommended

- GIVEN an exercise with last workout 3 weeks ago, `deload_after_weeks = 2`, `training_level = "intermediate"`
- WHEN the engine runs the check
- THEN status is `"deload_recommended"` with `deload_weight_kg` calculated

#### Scenario: Gap equals threshold → no deload (normal progression logic applies)

- GIVEN an exercise with last workout exactly 2 weeks ago, `deload_after_weeks = 2`, `training_level = "intermediate"`
- WHEN the engine runs the check
- THEN status follows normal progression logic (`"progress"`/`"maintain"`/`"insufficient_data"`)

#### Scenario: Novice threshold is 1 week lower

- GIVEN an exercise with last workout 2 weeks ago, `deload_after_weeks = 2`, `training_level = "novice"`
- WHEN the engine runs the check
- THEN status is `"deload_recommended"` (effective threshold = 1 week)

#### Scenario: Advanced threshold is 1 week higher

- GIVEN an exercise with last workout 3 weeks ago, `deload_after_weeks = 2`, `training_level = "advanced"`
- WHEN the engine runs the check
- THEN status follows normal progression logic (effective threshold = 3 weeks)

### Requirement: Deload weight calculated from working weight and deload_percent

When deload is triggered, the engine MUST compute `deload_weight_kg = working_weight_kg * (1 - deload_percent / 100)`, rounded to 1 decimal place.

#### Scenario: Standard 10% deload

- GIVEN working weight 100kg, `deload_percent = 10`
- WHEN deload is triggered
- THEN `deload_weight_kg` is 90.0

#### Scenario: Custom 20% deload

- GIVEN working weight 80kg, `deload_percent = 20`
- WHEN deload is triggered
- THEN `deload_weight_kg` is 64.0

#### Scenario: Deload weight rounded to 1 decimal

- GIVEN working weight 87.5kg, `deload_percent = 10`
- WHEN deload is triggered
- THEN `deload_weight_kg` is 78.8 (87.5 * 0.9 = 78.75 → 78.8)

### Requirement: Config persists via get_config/set_config

The repository MUST persist and retrieve `deload_after_weeks`, `deload_percent`, and `training_level` through the existing config API.

#### Scenario: Set and get new config fields

- GIVEN a clean config for exercise template "bench_press"
- WHEN `set_config("bench_press", deload_after_weeks=3, deload_percent=15, training_level="advanced")` is called
- THEN `get_config("bench_press")` returns an object with those values

#### Scenario: Default values used when not set

- GIVEN a new exercise template with no config
- WHEN `get_config("new_exercise")` is called
- THEN `deload_after_weeks = 2`, `deload_percent = 10`, `training_level = "intermediate"`

### Requirement: History stores deload_recommended status

The engine MUST insert a row into `progression_history` with `status = "deload_recommended"`, `current_weight_kg` = working weight, `recommended_weight_kg` = deload weight, and details JSON containing gap weeks and deload percent.

#### Scenario: Deload result persisted

- GIVEN a check returns status `"deload_recommended"` with `deload_weight_kg = 90.0`
- WHEN the engine completes
- THEN a `progression_history` row exists with `status = "deload_recommended"`, `current_weight_kg = 100.0`, `recommended_weight_kg = 90.0`

### Requirement: First workout (no history) returns insufficient_data — no deload

The engine MUST NOT trigger deload when no workout history exists for the exercise.

#### Scenario: New exercise returns insufficient_data

- GIVEN an exercise template with zero sets across all workouts
- WHEN the engine runs the check
- THEN status is `"insufficient_data"` (not `"deload_recommended"`)

### Requirement: Disabled config returns skipped — bypasses deload check

When `enabled = 0` for an exercise, the engine MUST return `"skipped"` without evaluating the time-gate.

#### Scenario: Disabled exercise returns skipped

- GIVEN `progression_config.enabled = 0` for an exercise template
- WHEN the engine runs the check
- THEN status is `"skipped"` and `deload_recommended` is False

### Requirement: Per-exercise config with muscle-group defaults

The repository MUST support per-exercise deload configuration, with muscle-group-specific defaults for `deload_after_weeks` and `deload_percent` (e.g., compound movements may use longer thresholds).

#### Scenario: Muscle-group default applied

- GIVEN exercise template "squat" with muscle_group "legs" and no explicit config
- WHEN `get_config("squat")` is called
- THEN `deload_after_weeks` and `deload_percent` reflect legs defaults

#### Scenario: Explicit config overrides muscle-group default

- GIVEN exercise template "bench_press" with muscle_group "chest" and explicit `set_config(deload_after_weeks=4)`
- WHEN `get_config("bench_press")` is called
- THEN `deload_after_weeks = 4` (not the chest default)

### Requirement: Long gaps capped at 40% deload with warning

When weeks elapsed > 12, the engine MUST cap `deload_percent` at 40% for calculation and include a warning in details JSON.

#### Scenario: 16-week gap capped at 40%

- GIVEN last workout 16 weeks ago, `deload_percent = 10` (config), `training_level = "intermediate"`
- WHEN deload is triggered
- THEN `deload_weight_kg` uses 40% reduction, details includes `"warning": "gap_exceeds_12_weeks_capped_at_40_percent"`

## Edge Cases

- **Timezone handling**: All dates compared as UTC date strings (YYYY-MM-DD), ignoring time-of-day
- **Future workout dates**: If `start_time` is in the future (data error), treat as 0 weeks elapsed
- **Partial week calculation**: Weeks = floor(days_elapsed / 7); 13 days = 1 week, 14 days = 2 weeks
- **Zero working weight**: Bodyweight exercises (weight_kg = 0) → deload_weight_kg = 0
- **Config validation**: `deload_percent` clamped to [5, 40]; `training_level` validated against enum
- **Deleted workouts**: Only non-deleted workouts considered for "last workout" lookup