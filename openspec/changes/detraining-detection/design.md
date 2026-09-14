# Design: Detraining Detection

## Technical Approach

Add a time-gate at the start of `ProgressionEngine.check()` that queries the most recent non-deleted workout date, calculates weeks elapsed, and compares against an effective threshold (base `deload_after_weeks` adjusted by `training_level`). If exceeded, return `"deload_recommended"` with calculated deload weight; otherwise, proceed with existing logic. Follows delta spec's "time-gate first" flow.

## Architecture Decisions

### Decision: Time-Gate Placement in `check()`

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Early return at start | Clean separation; avoids redundant set fetching | **Chosen** |
| After existing logic | Fetches sets unnecessarily for deload cases | Rejected |
| Separate `_check_deload()` helper | Reuses `_check_duration` pattern; keeps `check()` readable | Used internally |

**Rationale**: Matches delta spec flow; early return avoids loading set data when deload triggers.

### Decision: Most Recent Workout Query

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Reuse `get_normal_sets()` | Returns `start_time` DESC; no new query | **Chosen** |
| New workout→exercise→set query | Duplicates existing logic | Rejected |

**Rationale**: `get_normal_sets()` returns sets with `start_time` DESC. Most recent = `sets[0]["start_time"]`.

### Decision: Training Level Adjustment

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Inline logic in `check()` | Simple arithmetic mapping | **Chosen** |
| Lookup table in `models.py` | Over-engineered for 3 values | Rejected |

**Rationale**: Mapping: novice -1, intermediate 0, advanced +1 (floor 1 week).

### Decision: Deload Weight Calculation

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Reuse `_resolve_working_weight()` + formula | Consistent with existing resolution | **Chosen** |
| Use last set's weight | Less robust for multi-set | Rejected |

**Rationale**: `_resolve_working_weight()` implements mode-with-tie-break-to-heavier.

## Data Flow

```
ProgressionEngine.check(template_id)
         │
         ▼
   [1] Get config (with deload fields)
         │
         ▼
   [2] If !enabled → "skipped"
         │
         ▼
   [3] Get normal sets → if empty → "insufficient_data"
         │
         ▼
   [4] last_workout_date = sets[0]["start_time"]
         │
         ▼
   [5] weeks_elapsed = floor((check_date - last_workout_date).days / 7)
         │
         ▼
   [6] effective_threshold = deload_after_weeks + training_level_adjustment
         │
         ├── weeks_elapsed > threshold → [7a] Compute deload → "deload_recommended"
         │
         └── weeks_elapsed <= threshold → [7b] Existing progression logic
```

Dates compared as UTC `YYYY-MM-DD` via SQLite `date()`.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/darth_gain/progression/models.py` | Modify | Add `deload_after_weeks`, `deload_percent`, `training_level` to `ProgressionConfig`; add `deload_recommended`, `deload_weight_kg` to `ProgressionStatus` |
| `src/darth_gain/progression/repo.py` | Modify | Update `get_config`/`set_config` for new fields; add muscle-group deload defaults; clamp `deload_percent` to [5,40]; validate `training_level` |
| `src/darth_gain/progression/__init__.py` | Modify | Add time-gate at start of `check()`; add `_check_deload()` helper; update `_persist_history()` for deload |
| `src/darth_gain/db/engine.py` | Modify | `ALTER TABLE` for new columns; extend `CHECK` constraint to include `'deload_recommended'` |

## Interfaces / Contracts

### ProgressionConfig (updated)

```python
@dataclass
class ProgressionConfig:
    exercise_template_id: str
    rep_min: int = 8
    rep_max: int = 12
    weight_increment: float = 2.5
    enabled: bool = True
    deload_after_weeks: int = 2
    deload_percent: int = 10
    training_level: str = "intermediate"  # "novice" | "intermediate" | "advanced"
```

### ProgressionStatus (updated)

```python
@dataclass
class ProgressionStatus:
    exercise_template_id: str
    exercise_name: str
    rep_range: tuple[int, int]
    current_weight_kg: float | None
    latest_reps: list[int]
    top_of_range_reached: bool
    recommendation: str
    error: str | None
    increment: float = 2.5
    deload_recommended: bool = False
    deload_weight_kg: float | None = None
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Training level adjustment | Parametrized: novice/intermediate/advanced with base thresholds |
| Unit | Deload weight calc & rounding | 10% (90.0), 20% (64.0), rounding (87.5→78.8), 40% cap |
| Unit | Weeks elapsed calculation | floor(days/7): 13d=1w, 14d=2w, future date=0w |
| Unit | Config validation | `set_config` clamps deload_percent to [5,40], rejects invalid training_level |
| Integration | Full `check()` flow with time-gate | In-memory DB; seed workouts; assert status/deload_weight_kg |
| Integration | History persistence | Verify row has correct status, weights, details JSON |
| Edge Case | No history → insufficient_data | Empty sets returns insufficient_data |
| Edge Case | Disabled config → skipped | enabled=0 returns skipped |
| Edge Case | Gap > 12 weeks → 40% cap + warning | 112 days with deload_percent=10 uses 40% |

## Migration / Rollout

**Schema**: Idempotent `ALTER TABLE` in `create_tables()`. Defaults apply; no backfill.

**Config defaults**: Muscle-group deload defaults (compounds: 3w/15%, isolation: 2w/10%) in `repo.py` alongside `_MUSCLE_DEFAULT_RANGES`.

**Rollout**: Passive until config set; defaults conservative (2w/10%/intermediate). No feature flag.

## Open Questions

- [ ] Muscle-group defaults: compounds 3w/15% vs isolation 2w/10%? Spec mentions "compound movements may use longer thresholds" — need concrete mapping.
- [ ] Inject `check_date` for testing/historical checks? Delta spec uses `check_date=today`; optional param enables time-travel tests.
- [ ] Duration exercises need deload? Spec focuses on weight exercises; defer if needed.