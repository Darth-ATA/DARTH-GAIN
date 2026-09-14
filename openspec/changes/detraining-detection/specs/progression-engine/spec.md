# Progression Engine — Delta Spec: Detraining Detection

## Summary

This delta adds detraining detection (time-gate) to `ProgressionEngine.check()`. When weeks since last workout exceed a configurable threshold (adjusted by training level), the engine returns `"deload_recommended"` with a calculated deload weight instead of evaluating normal progression logic.

---

## ADDED: Data Contract Changes

### `ProgressionConfig` — NEW fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `deload_after_weeks` | int | 2 | Base weeks threshold before deload triggers |
| `deload_percent` | int | 10 | Percentage reduction for deload (5-40) |
| `training_level` | str | "intermediate" | `"novice"` \| `"intermediate"` \| `"advanced"` |

### `ProgressionStatus` — NEW fields

| Field | Type | Description |
|-------|------|-------------|
| `deload_recommended` | bool | True iff status == `"deload_recommended"` |
| `deload_weight_kg` | float \| None | Calculated deload weight when recommended |

### `progression_config` table — ADDED columns

```sql
ALTER TABLE progression_config ADD COLUMN deload_after_weeks INTEGER NOT NULL DEFAULT 2;
ALTER TABLE progression_config ADD COLUMN deload_percent INTEGER NOT NULL DEFAULT 10;
ALTER TABLE progression_config ADD COLUMN training_level TEXT NOT NULL DEFAULT 'intermediate'
  CHECK (training_level IN ('novice','intermediate','advanced'));
```

### `progression_history` table — MODIFIED CHECK constraint

**BEFORE:**
```sql
status TEXT NOT NULL CHECK (status IN ('progress','maintain','insufficient_data','skipped'))
```

**AFTER:**
```sql
status TEXT NOT NULL CHECK (status IN ('progress','maintain','insufficient_data','skipped','deload_recommended'))
```

---

## ADDED: Training Level Threshold Logic

Effective threshold = `deload_after_weeks` adjusted by `training_level`:

| training_level | Adjustment | Effective Threshold (base=2) |
|----------------|------------|------------------------------|
| novice | -1 (min 1) | 1 week |
| intermediate | 0 | 2 weeks |
| advanced | +1 | 3 weeks |

---

## ADDED: Deload Weight Calculation

```
deload_weight_kg = round(working_weight_kg * (1 - deload_percent / 100), 1)
```

- `deload_percent` clamped to [5, 40] at config set time
- For gaps > 12 weeks: effective percent = 40 (capped), warning in details

---

## MODIFIED: `ProgressionEngine.check()` — Time-Gate Logic

**New algorithm flow (inserted at start of check):**

1. If `config.enabled == 0` → return `"skipped"` (unchanged)
2. Query most recent non-deleted workout date for exercise template
3. If no workout history → return `"insufficient_data"` (unchanged)
4. Calculate `weeks_elapsed = floor((check_date - last_workout_date).days / 7)`
5. Determine `effective_threshold` from `config.deload_after_weeks` + training_level adjustment
6. If `weeks_elapsed > effective_threshold`:
   - Compute `working_weight_kg` (most common normal-set weight from last workout)
   - Compute `deload_weight_kg = round(working_weight_kg * (1 - min(config.deload_percent, 40) / 100), 1)`
   - Build details JSON with `gap_weeks`, `effective_threshold`, `deload_percent_used`, `training_level`
   - If `weeks_elapsed > 12` → add `"warning": "gap_exceeds_12_weeks_capped_at_40_percent"` to details
   - Return `ProgressionStatus(status="deload_recommended", deload_recommended=True, deload_weight_kg=..., ...)`
7. Else → proceed with existing progression logic (progress/maintain/insufficient_data)

---

## ADDED: Scenarios

### Scenario: Time-gate triggers deload for intermediate at 3 weeks

- GIVEN exercise with last workout 21 days ago, `deload_after_weeks=2`, `training_level="intermediate"`, `deload_percent=10`, working weight 100kg
- WHEN `engine.check(exercise_id, check_date=today)` is called
- THEN status is `"deload_recommended"`, `deload_recommended=True`, `deload_weight_kg=90.0`, `current_weight_kg=100.0`

### Scenario: Novice triggers at 1 week (base=2, adjusted=1)

- GIVEN exercise with last workout 10 days ago, `deload_after_weeks=2`, `training_level="novice"`, working weight 80kg
- WHEN check runs
- THEN status is `"deload_recommended"`, `deload_weight_kg=72.0` (10% default)

### Scenario: Advanced does NOT trigger at 3 weeks (base=2, adjusted=3)

- GIVEN exercise with last workout 21 days ago, `deload_after_weeks=2`, `training_level="advanced"`, working weight 120kg
- WHEN check runs
- THEN status follows normal progression logic (not deload)

### Scenario: Gap exactly at threshold → normal progression

- GIVEN exercise with last workout 14 days ago, `deload_after_weeks=2`, `training_level="intermediate"`, last workout all sets at rep_max
- WHEN check runs
- THEN status is `"progress"` (normal logic applies)

### Scenario: Deload weight rounded to 1 decimal

- GIVEN working weight 87.5kg, `deload_percent=10`
- WHEN deload triggers
- THEN `deload_weight_kg = 78.8`

### Scenario: 16-week gap capped at 40% with warning

- GIVEN last workout 112 days ago, `deload_percent=10` (config), `training_level="intermediate"`, working weight 100kg
- WHEN check runs
- THEN `deload_weight_kg = 60.0` (40% cap), details includes `"warning": "gap_exceeds_12_weeks_capped_at_40_percent"`

### Scenario: No history → insufficient_data (not deload)

- GIVEN exercise template with zero workouts
- WHEN check runs
- THEN status is `"insufficient_data"`, `deload_recommended=False`, `deload_weight_kg=None`

### Scenario: Disabled config → skipped (bypasses time-gate)

- GIVEN `progression_config.enabled = 0`
- WHEN check runs
- THEN status is `"skipped"`, `deload_recommended=False`, `deload_weight_kg=None`

### Scenario: History row stores deload_recommended with correct fields

- GIVEN check returns deload_recommended with `current_weight_kg=100.0`, `deload_weight_kg=90.0`
- WHEN check completes
- THEN `progression_history` row: `status="deload_recommended"`, `current_weight_kg=100.0`, `recommended_weight_kg=90.0`, `details` JSON contains `gap_weeks`, `deload_percent_used`, `training_level`

---

## MODIFIED: Existing Scenarios (behavior unchanged, but now run after time-gate)

All existing scenarios from base spec remain valid **when time-gate does not trigger**. The time-gate is evaluated first; only if `weeks_elapsed <= effective_threshold` does the original logic run.

### Scenario: All sets hit rep_max → progress (unchanged, runs after time-gate pass)

- GIVEN exercise with `rep_max = 12` and last workout has 3 normal sets of 12, 12, 12 reps at 80kg, last workout 1 week ago
- WHEN the engine runs the check
- THEN status is `"progress"` and `recommended_weight_kg` is `82.5`

### Scenario: Disabled exercise returns skipped (unchanged, runs before time-gate)

- GIVEN `progression_config.enabled = 0` for an exercise template
- WHEN the engine runs the check
- THEN status is `"skipped"` and `recommended_weight_kg` is NULL

---

## Edge Cases (ADDED to base spec)

- **Timezone**: Compare UTC date strings (`YYYY-MM-DD`) only; `datetime()` with `date()` in SQLite
- **Future workout date**: If `last_workout_date > check_date` → `weeks_elapsed = 0`
- **Partial weeks**: `floor(days/7)` — 13 days = 1 week, 14 days = 2 weeks
- **Bodyweight (weight_kg=0)**: `deload_weight_kg = 0`
- **Deleted workouts**: Excluded from "most recent workout" query
- **Config validation**: `set_config` clamps `deload_percent` to [5, 40]; rejects invalid `training_level`