# Proposal: Detraining Detection

## Intent

Add automatic deload recommendation after training gaps based on scientific evidence. The ProgressionEngine currently has no detraining handling — users returning from breaks get incorrect "progress" or "maintain" recommendations instead of appropriate deloads. This change adds a time-gate that detects training gaps and recommends deloads based on established detraining timelines (1-2 weeks: 5% neural loss, 2-4 weeks: 5-10%, 1-2 months: 10-20%, 3+ months: 25-40%), with training level adjustment (novice detrains faster, advanced retains longer via myonuclei retention).

## Scope

### In Scope
- Time-gate logic in `ProgressionEngine.check()` comparing last workout date to current check date
- New config fields in `ProgressionConfig` and `progression_config` table: `deload_after_weeks`, `deload_percent`, `training_level`
- New status `"deload_recommended"` in `progression_history.status` CHECK constraint
- Per-exercise deload configuration with muscle-group defaults
- Updated `ProgressionStatus` dataclass with `deload_recommended` boolean and `deload_weight_kg` fields

### Out of Scope
- Automatic weight application (remains manual via CLI)
- Multi-exercise deload overview dashboard
- Deload period tracking (how long to stay at reduced weight)
- RPE-based deload depth adjustment
- Web UI for deload configuration

## Capabilities

### New Capabilities
- `detraining-detection`: Training gap detection, deload recommendation calculation, per-exercise deload config management, integration with progression check flow

### Modified Capabilities
- `progression-engine`: Added deload status to check result; config schema extended; history status constraint expanded; CLI output includes deload recommendation

## Approach

Integrated time-gate in `ProgressionEngine.check()` method (Approach 1 from exploration). Before evaluating set performance, the engine:
1. Finds the most recent workout date for the exercise
2. Calculates weeks since that workout
3. If weeks exceed `deload_after_weeks` (configurable, default 2), computes deload weight = `working_weight * (1 - deload_percent/100)`
4. Returns status `"deload_recommended"` with `deload_weight_kg` instead of normal progression logic
5. Persists result with new status in `progression_history`

Config fields added to `ProgressionConfig`:
- `deload_after_weeks: int = 2` — threshold to trigger deload
- `deload_percent: int = 10` — percentage reduction (5-40% based on gap)
- `training_level: str = "intermediate"` — "novice" | "intermediate" | "advanced" (adjusts threshold)

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/darth_gain/progression/__init__.py` | Modified | Time-gate logic in `check()`, new status handling, deload weight calculation |
| `src/darth_gain/progression/models.py` | Modified | `ProgressionConfig` new fields; `ProgressionStatus` add `deload_recommended`, `deload_weight_kg` |
| `src/darth_gain/progression/repo.py` | Modified | `get_config`/`set_config` for new fields; `_MUSCLE_DEFAULT_RANGES` may need deload defaults |
| `src/darth_gain/db/engine.py` | Modified | `progression_config` ADD COLUMNs; `progression_history.status` CHECK constraint add `'deload_recommended'` |
| `tests/test_progression_engine.py` | Modified | New tests for deload scenarios (gap thresholds, percent calc, training level) |
| `tests/test_progression_repo.py` | Modified | Tests for new config fields persistence |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Schema migration on existing DBs | High | Idempotent `ALTER TABLE ADD COLUMN IF NOT EXISTS` with defaults; update CHECK constraint via recreate or new table |
| First-workout edge case (no history) | Medium | Treat as `insufficient_data` — no deload without baseline |
| Timezone handling for `start_time` | Medium | Use UTC ISO strings consistently; compare dates not datetimes |
| Incorrect deload for very long gaps | Low | Cap `deload_percent` at 40%; log warning for gaps > 12 weeks |
| User confusion: deload vs progress | Low | Clear recommendation string: "Deload recommended: reduce to X kg (Y% due to Z weeks off)" |

## Rollback Plan

1. Revert code changes in `progression/` module
2. `ALTER TABLE progression_config DROP COLUMN deload_after_weeks, DROP COLUMN deload_percent, DROP COLUMN training_level`
3. Revert `progression_history` status CHECK constraint: recreate table with original `('progress','maintain','insufficient_data','skipped')` or use `UPDATE progression_history SET status='maintain' WHERE status='deload_recommended'` + new table swap
4. No data loss — history rows preserved with mapped status

## Dependencies

- Existing `progression_config` and `progression_history` tables (from original progression-engine change)
- `workouts.start_time` index (already exists)
- SQLite `datetime()` for date comparison (built-in)

## Success Criteria

- [ ] Engine returns `deload_recommended` status when weeks since last workout > `deload_after_weeks`
- [ ] Deload weight calculated correctly: `working_weight * (1 - deload_percent/100)`
- [ ] Config persists via `set_config`/`get_config` with new fields
- [ ] `progression_history` accepts and stores `deload_recommended` status
- [ ] Training level adjusts threshold: novice=1 week, intermediate=2 weeks, advanced=3 weeks
- [ ] All existing tests pass + new deload tests pass
- [ ] CLI output shows clear deload recommendation with percentage and reason