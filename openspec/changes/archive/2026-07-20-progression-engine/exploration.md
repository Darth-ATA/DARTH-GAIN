# Exploration: Progression Engine for DARTH-GAIN

## Current State

DARTH-GAIN v0.1.0 is a CLI tool that syncs workout data from the Hevy API to a local SQLite database. The architecture has four layers:

1. **Config** (`src/darth_gain/config.py`) — Resolves `HEVY_API_KEY`, `db_path`, and CLI flags. Uses `platformdirs` for XDG-compliant defaults.
2. **Hevy Client** (`src/darth_gain/hevy/client.py`) — Adapter wrapping `hevy-api-wrapper` SDK. Converts Pydantic models to plain dicts. Provides `get_events()` for delta sync and `get_exercise_templates()` for template caching.
3. **Sync** (`src/darth_gain/hevy/sync.py`) — Orchestrator that paginates events, upserts workouts, soft-deletes deleted ones, caches templates, and persists `last_sync_at`.
4. **DB** (`src/darth_gain/db/engine.py` + `repo.py`) — SQLite with 5 tables: `workouts`, `exercises`, `sets`, `exercise_templates`, `sync_metadata`. Functions: `upsert_workout()`, `soft_delete_workout()`, `upsert_templates()`, `get_templates()`, `set_sync_meta()`, `get_sync_meta()`.

The CLI has a single `ingest` command. **There is no progression engine yet.**

---

## 1. Current DB Schema Analysis

### Tables

**`workouts`**
| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | Hevy UUID |
| title | TEXT | e.g. "Push Day" |
| description | TEXT | |
| start_time | TEXT | ISO 8601 |
| end_time | TEXT | ISO 8601, nullable |
| is_deleted | INTEGER | Soft delete flag |
| created_at | TEXT | Our creation timestamp |
| updated_at | TEXT | Our update timestamp |

Indexes: `idx_workouts_start_time`, `idx_workouts_updated_at`.

**`exercises`**
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | AUTOINCREMENT |
| workout_id | TEXT FK | → workouts.id |
| exercise_template_id | TEXT | **Key cross-workout identifier** |
| title | TEXT | |
| notes | TEXT | |
| sort_order | INTEGER | Position in workout |
| is_deleted | INTEGER | Soft delete |

Index: `idx_exercises_workout_id`. **No index on `exercise_template_id`** — this matters for progression queries.

**`sets`**
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | AUTOINCREMENT |
| exercise_id | INTEGER FK | → exercises.id |
| set_index | INTEGER | Position within exercise |
| type | TEXT | `normal` \| `warmup` \| `dropset` \| `failure` |
| weight_kg | REAL | Nullable |
| reps | INTEGER | Nullable |
| distance_meters | REAL | Nullable |
| duration_seconds | REAL | Nullable |
| rpe | REAL | Nullable (6, 7, 7.5, 8, 8.5, 9, 9.5, 10) |
| is_deleted | INTEGER | |

**`exercise_templates`**
| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | Hevy UUID |
| title | TEXT | e.g. "Barbell Bench Press" |
| type | TEXT | `weight_reps`, `reps_only`, `duration` |
| primary_muscle_group | TEXT | |
| other_muscle_groups | TEXT | JSON array string |
| equipment | TEXT | |
| is_custom | INTEGER | |
| cached_at | TEXT | When we cached it |

**`sync_metadata`**
| Column | Type |
|--------|------|
| key | TEXT PK |
| value | TEXT |

Holds `last_sync_at`.

### Critical Gaps for Progression

- **No rep range data** — nowhere to store target rep ranges (e.g., 8-12). The Hevy API's `RoutineSet` has a `rep_range` field (`RepRange(start, end)`), but routines are not currently synced.
- **No progression state table** — no way to track current weight per exercise, last increase date, or configured rep ranges.
- **No per-exercise config** — no flag to mark an exercise as "use double progression" vs. not.
- **No index on `exercise_template_id`** — progression queries will scan the exercises table.
- **`routine_id` not stored** — workouts have a `routine_id` in the Hevy API but it's not synced.

---

## 2. Data Availability for Progression Calculations

### What We HAVE

| Need | Available? | Source |
|------|-----------|--------|
| Historical set data (reps, weight, date) | ✅ | `sets` + `exercises` + `workouts` JOIN |
| Exercise identity across workouts | ✅ | `exercise_template_id` in `exercises` |
| Set type filtering (normal vs warmup) | ✅ | `sets.type` |
| RPE data | ✅ | `sets.rpe` (nullable) |
| Chronological ordering | ✅ | `workouts.start_time` |
| Soft-delete awareness | ✅ | `workouts.is_deleted`, `exercises.is_deleted` |
| Exercise metadata (muscle group, equipment) | ✅ | `exercise_templates` table |

### What We DON'T Have

| Need | Status | Why |
|------|--------|-----|
| Target rep range per exercise | ❌ | Not stored anywhere |
| Per-exercise weight increment config | ❌ | Not stored |
| Progression tracking state | ❌ | When was weight last increased? |
| Routine data with default set info | ❌ | Routines not synced yet |
| "Use double progression" flag | ❌ | Configuration needed |

### Key Query Pattern for Progression

```sql
-- All normal sets for an exercise across workouts (chronological)
SELECT w.start_time, s.set_index, s.weight_kg, s.reps, s.rpe
FROM sets s
JOIN exercises e ON s.exercise_id = e.id
JOIN workouts w ON e.workout_id = w.id
WHERE e.exercise_template_id = ?
  AND w.is_deleted = 0
  AND e.is_deleted = 0
  AND s.type = 'normal'
ORDER BY w.start_time ASC, s.set_index ASC;
```

This gives the algorithm exactly what it needs: every "normal" set for a given exercise across time.

---

## 3. Key Design Decisions

### D1: Where do rep ranges come from?
- **A**: Sync routines + routine_sets from Hevy API (they have `rep_range` per set)
- **B**: New `progression_config` table — user configures rep ranges per exercise
- **C**: Hard-code by exercise type or muscle group
- **Recommendation**: A+B — sync routines as defaults, allow user overrides. First PR implements B only.

### D2: Progression state tracking?
- Track `current_weight`, `rep_min`, `rep_max`, `last_increased_date` per exercise
- Enables `darth-gain progression status` to show state without re-querying all history
- Also: `progression_history` table to audit every weight increase

### D3: Weight increment?
- Global default: 2.5kg (barbell) — most common smallest increment (1.25kg plates per side)
- Per-exercise override in config
- Auto-detect from historical data as future enhancement

### D4: Which exercises qualify?
- Auto-detect by `exercise_template.type`: `weight_reps` qualifies, `reps_only`/`duration` don't
- User override via `progression_config.enabled` flag
- Default: enabled for all `weight_reps` type exercises

### D5: RPE integration?
- RPE is nullable — algorithm must work without it
- Future: if all sets at max reps with RPE < 8, weight may be too light
- Future: if at max reps with RPE > 9.5, definitely progress

### D6: Deload and irregular schedules?
- Initial version: simplest deterministic check (all sets hit top of range)
- Future: require N consecutive workouts at target before progressing
- Deload detection is Phase 2

---

## 4. Recommended Approach

### Module Structure

```
src/darth_gain/progression/
├── __init__.py        # Public API: check(), status(), apply()
├── engine.py          # Core double progression algorithm
├── models.py          # Dataclasses: RepRangeConfig, ProgressionStatus, Recommendation
├── repo.py            # DB queries for progression data + config CRUD
└── config.py          # Per-exercise rep range and increment configuration
```

### CLI Integration

```python
# Under the existing cli group in cli.py
@cli.group()
def progression():
    """Check and manage exercise progression."""

@progression.command()
@click.argument("exercise_template_id")
def check(exercise_template_id):
    """Check progression status for an exercise."""

@progression.command()
def status():
    """Overview of all exercises needing progression."""

@progression.command()
@click.argument("exercise_template_id")
def config(exercise_template_id):
    """View/set progression configuration."""

@progression.command()
@click.argument("exercise_template_id")
def apply(exercise_template_id):
    """Mark progression as applied."""
```

### DB Schema Additions

```sql
CREATE TABLE IF NOT EXISTS progression_config (
    exercise_template_id TEXT PRIMARY KEY REFERENCES exercise_templates(id),
    rep_min              INTEGER NOT NULL DEFAULT 8,
    rep_max              INTEGER NOT NULL DEFAULT 12,
    weight_increment_kg  REAL NOT NULL DEFAULT 2.5,
    enabled              INTEGER NOT NULL DEFAULT 1,
    updated_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS progression_history (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_template_id TEXT NOT NULL REFERENCES exercise_templates(id),
    previous_weight_kg   REAL,
    new_weight_kg        REAL NOT NULL,
    prev_rep_min         INTEGER,
    prev_rep_max         INTEGER,
    reason               TEXT,
    applied_at           TEXT NOT NULL,
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### Progression Algorithm

```
function check(exercise_template_id):
    1. Load config (rep_min, rep_max, increment, enabled)
    2. If not enabled → skip/report "not tracked"
    3. Query all normal sets for this exercise, chronological by workout
    4. Group sets by workout (grouped by workout start_time)
    5. For each workout (oldest → newest):
       a. Get all "normal" sets
       b. In each workout, get the working weight (most common weight across all normal sets, or highest)
       c. Check: ALL sets have reps >= rep_max?
    6. Find the MOST RECENT consecutive streak where ALL sets hit rep_max
       - Need at least 1 full workout at target (or configurable)
    7. If criteria met → recommend: increase weight by increment
    8. If not → report: stay at current weight, target reps is rep_max
    9. Return: { exercise_template_id, current_weight, rep_range, status, recommendation, history }
```

### Error Handling per Existing Patterns

Following the codebase pattern:
- **Error isolation** — each progression check is independent (like event processing in sync)
- **Graceful fallback** — if exercise has no config, report "not configured"
- **NULL handling** — sets with NULL weight_kg or reps are skipped (but exercise_template.type can hint why)

---

## 5. Risks and Unknowns

1. **Rep range source is unknown without routines** — The Hevy API provides `rep_range` on `RoutineSet`, but routines aren't synced. Without routine data or user config, there's no source of truth. The first PR must provide a configuration mechanism.

2. **Exercise type variance** — `ExerciseTemplate.type` can be `weight_reps`, `reps_only`, `duration`. Double progression only works for `weight_reps`. The engine must auto-skip others.

3. **Inconsistent weight across sets** — Users sometimes change weight mid-exercise. Algorithm must decide "working weight" vs. individual set weights.

4. **NULL weight_kg / reps** — Some Hevy exercises don't log weight (bodyweight, mobility). Algorithm must handle gracefully.

5. **API is beta** — Hevy's API could change data models. The adapter pattern in `client.py` already protects against this.

6. **No real-time progression** — CLI is pull-based (cron or manual). Progression evaluation happens on demand, not after every workout log. Document as UX trade-off.

7. **Testing with real data shapes** — Current tests use synthetic data. Progression engine should be verified against actual Hevy workout patterns. Consider a fixture with realistic multi-workout data.

---

## 6. Suggested Scope for First Implementation PR

### Single Deliverable
`darth-gain progression check <exercise_template_id>` — check progression status for one exercise.

### Files to Create
| File | Purpose |
|------|---------|
| `src/darth_gain/progression/__init__.py` | Package init, public API exports |
| `src/darth_gain/progression/engine.py` | Core double progression algorithm |
| `src/darth_gain/progression/models.py` | Dataclasses (RepRangeConfig, ProgressionStatus, Recommendation) |
| `src/darth_gain/progression/repo.py` | DB queries for progression data + CRUD |
| `tests/test_progression_engine.py` | Unit tests for the algorithm |
| `tests/test_progression_repo.py` | Tests for DB queries |

### Files to Modify
| File | Change |
|------|--------|
| `src/darth_gain/db/engine.py` | Add `progression_config` and `progression_history` to DDL |
| `src/darth_gain/cli.py` | Add `progression` group with `check` subcommand |

### What It Does
- Adds DB schema for progression configuration and history
- Implements deterministic double progression check algorithm
- Exposes `darth-gain progression check <id>` — outputs current weight, rep range, status, recommendation
- Fully tested (unit + integration with known synthetic scenarios)

### What It Explicitly Does NOT Do
- ❌ Multi-exercise overview (`progression status` — Phase 2)
- ❌ Progression application tracking (`progression apply` — Phase 2)
- ❌ Automatic rep range discovery from routines (Phase 2)
- ❌ Deload detection (Phase 2)
- ❌ RPE-aware adjustments (Phase 2)

---

## Ready for Proposal

**Yes.** All required information has been gathered. The orchestrator can proceed to the Proposal phase with confidence.
