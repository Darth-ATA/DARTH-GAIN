# Tasks: Detraining Detection

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~500-600 |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR 1: schema + models → PR 2: repo + engine time-gate → PR 3: tests |
| Delivery strategy | single-pr |
| Chain strategy | feature-branch-chain |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Schema + dataclasses | PR 1 | Base branch; creates new columns and fields |
| 2 | Config CRUD + time-gate | PR 2 | Depends on PR 1; core logic |
| 3 | Tests | PR 3 | Depends on PR 2; references spec scenarios |

## Phase 1: Foundation (Schema + Models)

- [x] 1.1 Add `deload_after_weeks INTEGER NOT NULL DEFAULT 2`, `deload_percent INTEGER NOT NULL DEFAULT 10`, `training_level TEXT NOT NULL DEFAULT 'intermediate'` with CHECK constraint to `progression_config` table in `src/darth_gain/db/engine.py` using `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` idempotent pattern
- [x] 1.2 Extend `progression_history.status` CHECK constraint to include `'deload_recommended'` in `src/darth_gain/db/engine.py` (recreate table or use CREATE TABLE IF NOT EXISTS with updated constraint)
- [x] 1.3 Add `deload_after_weeks: int = 2`, `deload_percent: int = 10`, `training_level: str = "intermediate"` fields to `ProgressionConfig` dataclass in `src/darth_gain/progression/models.py`
- [x] 1.4 Add `deload_recommended: bool = False`, `deload_weight_kg: float | None = None` fields to `ProgressionStatus` dataclass in `src/darth_gain/progression/models.py`

## Phase 2: Core Implementation (Config + Time-Gate)

- [x] 2.1 Add `_MUSCLE_DELOAD_DEFAULTS` dict to `src/darth_gain/progression/repo.py` mapping compound muscles (chest, shoulders, back, glutes, hamstrings, quadriceps) to `(3, 15)` and isolation muscles to `(2, 10)` for `deload_after_weeks, deload_percent` defaults
- [x] 2.2 Update `get_config()` in `src/darth_gain/progression/repo.py` to query new columns and return `ProgressionConfig` with `deload_after_weeks`, `deload_percent`, `training_level`; fall back to muscle-group deload defaults when no row exists
- [x] 2.3 Update `set_config()` in `src/darth_gain/progression/repo.py` to include new fields in INSERT/REPLACE; clamp `deload_percent` to [5, 40] and validate `training_level` against `('novice','intermediate','advanced')`, raising `ValueError` on invalid
- [x] 2.4 Update `get_all_configs()` and `_row_to_history_entry()` in `src/darth_gain/progression/repo.py` for new columns; add `deload_recommended` and `deload_weight_kg` to `ProgressionHistoryEntry` dataclass in `models.py`
- [x] 2.5 Add `_check_deload()` helper method to `ProgressionEngine` in `src/darth_gain/progression/__init__.py` that takes `config` and `last_workout_date`, computes `weeks_elapsed = floor((check_date - last_workout_date).days / 7)`, `effective_threshold`, and returns deload result or None
- [x] 2.6 Insert time-gate at start of `check()` in `src/darth_gain/progression/__init__.py`: after disabled check but before set fetching; call `_check_deload()`; if deload triggers, compute `deload_weight_kg`, build details with `gap_weeks`, `effective_threshold`, `deload_percent_used`, `training_level`, cap at 40% for gaps > 12 weeks with warning, persist and return `"deload_recommended"`
- [x] 2.7 Add optional `check_date: str | None = None` parameter to `ProgressionEngine.check()` for test/historical time-travel; default to `datetime('now')` via SQLite
- [x] 2.8 Update `_persist_history()` to include `deload_recommended` and `deload_weight_kg` from `ProgressionStatus` in the history row; ensure `details` JSON contains `gap_weeks`, `deload_percent_used`, `training_level`, and warning when applicable

## Phase 3: Integration (Wiring + Edge Cases)

- [x] 3.1 Wire `get_normal_sets()` call in `_check_deload()` to find most recent non-deleted workout date for the exercise template (reuse existing query pattern)
- [x] 3.2 Handle edge cases in time-gate: no workout history → `insufficient_data` (not deload), future workout date → `weeks_elapsed = 0`, bodyweight (`weight_kg=0`) → `deload_weight_kg = 0`, `get_config` muscle-group defaults applied when no explicit config
- [x] 3.3 Ensure duration exercises skip deload check (deferred per design open question — time-gate only applies to weight exercises; duration exercises continue using `_check_duration`)

## Phase 4: Testing (Reference Spec Scenarios)

- [x] 4.1 Write test for intermediate threshold (3 weeks → deload): spec scenario "Gap exceeds intermediate threshold → deload recommended" — assert status `"deload_recommended"`, `deload_weight_kg=90.0`
- [x] 4.2 Write test for novice threshold (base-1=1 week): spec scenario "Novice triggers at 1 week" — 10 days ago, assert deload triggered with `deload_weight_kg=72.0`
- [x] 4.3 Write test for advanced threshold (base+1=3 weeks): spec scenario "Advanced does NOT trigger at 3 weeks" — 21 days ago, assert normal progression logic
- [x] 4.4 Write test for gap at threshold: spec scenario "Gap exactly at threshold → normal progression" — 14 days ago, assert status `"progress"`
- [x] 4.5 Write test for deload weight calculation: spec scenario "Deload weight rounded to 1 decimal" — 87.5kg, 10%, assert `deload_weight_kg=78.8`
- [x] 4.6 Write test for 40% cap + warning: spec scenario "16-week gap capped at 40% with warning" — 112 days ago, assert `deload_weight_kg=60.0` and warning in details
- [x] 4.7 Write test for no history → `insufficient_data`: spec scenario "No history → insufficient_data (not deload)" — assert `deload_recommended=False`, `deload_weight_kg=None`
- [x] 4.8 Write test for disabled → `skipped`: spec scenario "Disabled config → skipped (bypasses time-gate)" — assert `deload_recommended=False`
- [x] 4.9 Write test for history persistence: spec scenario "History row stores deload_recommended with correct fields" — assert `progression_history` row has `status="deload_recommended"`, correct weights, details JSON with `gap_weeks`, `deload_percent_used`, `training_level`
- [x] 4.10 Write tests for config validation: `set_config` clamps `deload_percent` to [5,40], rejects invalid `training_level`; test muscle-group defaults applied (squat with muscle_group "legs" → compounds 3w/15%)
- [x] 4.11 Write test for `check_date` injection: verify historical check works with explicit `check_date` parameter
- [x] 4.12 Run full existing test suite to confirm no regressions

## Phase 5: Cleanup (Open Questions Resolution)

- [x] 5.1 Document resolved open questions: muscle-group defaults confirmed as compounds 3w/15%, isolation 2w/10%; `check_date` injection implemented as optional param; duration exercises deferred from deload
- [x] 5.2 Verify `get_config` returns `deload_after_weeks`, `deload_percent`, `training_level` for duration exercise types with appropriate defaults
