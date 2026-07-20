# Tasks: Progression Engine

## Delivery Strategy

| Attribute | Value |
|-----------|-------|
| Strategy | `ask-on-risk` |
| Forecast total | ~1,032 lines (authored) |
| Risk level | **High** |
| Recommendation | **3 chained PRs** |

---

## Review Workload Forecast

### Estimated Lines (authored additions + deletions)

| Component | New | Modified | Total |
|-----------|-----|----------|-------|
| `db/engine.py` DDL | — | ~17 | 17 |
| `progression/models.py` | ~35 | — | 35 |
| `progression/repo.py` | ~85 | — | 85 |
| `progression/__init__.py` | ~95 | — | 95 |
| `cli.py` commands | — | ~115 | 115 |
| `tests/conftest.py` fixtures | — | ~65 | 65 |
| `tests/test_db_engine.py` (DDL assertions) | — | ~25 | 25 |
| `tests/test_progression_repo.py` | ~160 | — | 160 |
| `tests/test_progression_engine.py` | ~280 | — | 280 |
| `tests/test_progression_cli.py` | ~140 | — | 140 |
| **Total** | **~795** | **~222** | **~1,017** |

> **Exceeding 400-line threshold — chained PRs strongly recommended.**

### Recommended Chained PR Slice Boundaries

```
PR A ── Foundation (T1 + T2 + T3)   ≈ 337 lines
  └─ T1: DB Schema DDL
  └─ T2: Progression domain models
  └─ T3: Progression repository CRUD

PR B ── Algorithm (T4)                ≈ 440 lines
  └─ T4: ProgressionEngine + engine tests + conftest fixtures

PR C ── CLI (T5)                     ≈ 255 lines
  └─ T5: Progression CLI commands + CLI tests
```

**Rationale**: Each PR delivers a coherent slice of the change that can be reviewed, merged, and rolled back independently:
- **PR A**: Foundation — DB schema, models, data access. No behaviour exposed yet. Zero user impact. Can be merged without changing any UX.
- **PR B**: Algorithm — the core domain logic. Largest slice (~440 lines) but the most cohesive: engine class + its comprehensive test suite + required fixtures. Borderline over 400; the algorithm code + its tests form an atomic deliverable that cannot be split further without breaking the "keep tests with code" rule.
- **PR C**: CLI — user-facing commands wired to the engine. Depends on PR B. Smallest slice, fastest review.

---

## Task Dependency Graph

```
T1 (DDL)
 │
 ├──→ T3 (Repo) ──→ T4 (Engine) ──→ T5 (CLI)
 │
T2 (Models) ──┘
```

- **T1** and **T2** are independent (can be parallelised).
- **T3** depends on both T1 (tables exist) and T2 (models exist).
- **T4** depends on T2 (models) and T3 (repo functions).
- **T5** depends on T4 (engine class).

---

## ✅ Task T1: Add progression_config and progression_history DDL

| Attribute | Value |
|-----------|-------|
| **ID** | T1 |
| **Name** | Add DDL for progression tables |
| **Complexity** | S |
| **PR Slice** | PR A (Foundation) |

### Files

| File | Action |
|------|--------|
| `src/darth_gain/db/engine.py` | Modify — append DDL to `SCHEMA_SQL` |
| `tests/test_db_engine.py` | Modify — add table existence and schema tests |

### DDL Contract

```sql
CREATE TABLE IF NOT EXISTS progression_config (
    exercise_template_id TEXT PRIMARY KEY REFERENCES exercise_templates(id),
    rep_min              INTEGER NOT NULL DEFAULT 8,
    rep_max              INTEGER NOT NULL DEFAULT 12,
    weight_increment     REAL NOT NULL DEFAULT 2.5,
    enabled              INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS progression_history (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_template_id TEXT NOT NULL REFERENCES exercise_templates(id),
    checked_at           TEXT NOT NULL DEFAULT (datetime('now')),
    status               TEXT NOT NULL CHECK(status IN ('progress','maintain','insufficient_data','skipped')),
    current_weight_kg    REAL,
    recommended_weight_kg REAL,
    details              TEXT
);

CREATE INDEX IF NOT EXISTS idx_progression_history_template
    ON progression_history(exercise_template_id);
```

### Acceptance Criteria

- [x] `progression_config` table exists with all columns and default values per spec
- [x] `progression_history` table exists with all columns per spec
- [x] `progression_history.status` CHECK constraint accepts `progress`, `maintain`, `insufficient_data`, `skipped`
- [x] Index `idx_progression_history_template` exists on `exercise_template_id`
- [x] `create_tables()` is idempotent — running twice does not error
- [x] FK references to `exercise_templates(id)` are enforced

### Test Requirements

- Follow `test_db_engine.py::TestCreateTables` pattern
- One test per new table asserting column names and types via `PRAGMA table_info`
- Idempotency test verifies `create_tables()` can be called twice
- Verify `progression_config` PK is `exercise_template_id`
- Verify `progression_history` has AUTOINCREMENT on `id`

### Dependencies

None.

---

## ✅ Task T2: Add progression domain models

| Attribute | Value |
|-----------|-------|
| **ID** | T2 |
| **Name** | Progression domain dataclasses |
| **Complexity** | S |
| **PR Slice** | PR A (Foundation) |

### Files

| File | Action |
|------|--------|
| `src/darth_gain/progression/models.py` | Create |
| `tests/test_progression_models.py` | Create (or inline in test_progression_repo.py) |

### Interfaces

```python
@dataclass
class ProgressionConfig:
    exercise_template_id: str
    rep_min: int = 8
    rep_max: int = 12
    weight_increment: float = 2.5
    enabled: bool = True

@dataclass
class ProgressionStatus:
    exercise_template_id: str
    exercise_name: str
    rep_range: tuple[int, int]           # (rep_min, rep_max)
    current_weight_kg: float | None
    latest_reps: list[int]               # reps from most recent workout
    top_of_range_reached: bool           # ALL normal set reps >= rep_max?
    recommendation: str                  # "increase to X kg" or "keep at X kg"
    error: str | None                    # None if OK
```

### Acceptance Criteria

- [x] `ProgressionConfig` constructs with defaults: 8, 12, 2.5, True
- [x] `ProgressionConfig` accepts all keyword overrides
- [x] `ProgressionStatus` constructs with all required fields
- [x] `ProgressionStatus.rep_range` is `tuple[int, int]` type
- [x] `ProgressionStatus.error` is `None` for success, `str` for errors

### Test Requirements

- Test default construction of both dataclasses
- Test field override for every mutable field
- Test `ProgressionStatus` with error vs no-error states

### Dependencies

None.

---

## ✅ Task T3: Add progression repository CRUD

| Attribute | Value |
|-----------|-------|
| **ID** | T3 |
| **Name** | Progression repo functions |
| **Complexity** | M |
| **PR Slice** | PR A (Foundation) |

### Files

| File | Action |
|------|--------|
| `src/darth_gain/progression/repo.py` | Create |
| `tests/test_progression_repo.py` | Create |

### Functions

```python
def get_template(conn, template_id: str) -> dict | None
def get_config(conn, template_id: str) -> ProgressionConfig      # defaults if no row
def upsert_config(conn, template_id: str, **kwargs) -> None       # partial update
def get_normal_sets(conn, template_id: str) -> list[dict]         # chronological by workout
def insert_history(conn, template_id: str, status: str,
                   current_weight: float | None,
                   recommended_weight: float | None,
                   details: dict | None) -> None
```

### Key Behaviours

- `get_config` returns a `ProgressionConfig` with default values (8-12, 2.5kg, enabled) when no row exists — **never returns None**
- `upsert_config` performs partial update: reads current row, merges provided kwargs, writes back
- `get_normal_sets` filters `s.type = 'normal'`, `w.is_deleted = 0`, `e.is_deleted = 0`, orders by `w.start_time ASC, s.set_index ASC`
- `get_normal_sets` includes `weight_kg`, `reps`, `start_time`, `exercise_id`, `set_index`
- `insert_history` persists a row with `current_weight_kg`, `recommended_weight_kg`, `details` (JSON-serialised dict), `checked_at` auto-set by SQLite
- Module-level functions (not a class), matching `db/repo.py` pattern

### Acceptance Criteria

- [x] `get_config` returns default `ProgressionConfig` when no row exists
- [x] `get_config` returns stored config when row exists
- [x] `set_config` creates a new row when none exists
- [x] `set_config` upserts an existing config
- [x] `get_all_configs` returns all stored configs
- [x] `add_history_entry` creates a row and returns its id
- [x] `add_history_entry` stores `maintain`, `progress`, `insufficient_data` statuses
- [x] `get_history` returns entries for a template, excluding others
- [x] `get_latest_history` returns most recent entry or None

### Test Requirements

- Follow `test_db_repo.py` patterns: class-based grouping, `conn` fixture from conftest, seed data inline
- In-memory SQLite with `create_tables()` for every test
- Seed `exercise_templates`, `workouts`, `exercises`, `sets` tables as needed
- Test both `weight_reps` and `reps_only` template types for `get_normal_sets`

### Dependencies

- T1 (DDL tables must exist)
- T2 (models must be importable)

---

## Task T4: Implement progression engine algorithm

| Attribute | Value |
|-----------|-------|
| **ID** | T4 |
| **Name** | ProgressionEngine class |
| **Complexity** | L |
| **PR Slice** | PR B (Algorithm) |

### Files

| File | Action |
|------|--------|
| `src/darth_gain/progression/__init__.py` | Create |
| `tests/conftest.py` | Modify — add multi-workout progression fixtures |
| `tests/test_progression_engine.py` | Create |

### Public API

```python
class ProgressionEngine:
    def __init__(self, conn: sqlite3.Connection) -> None: ...
    def check(self, template_id: str) -> ProgressionStatus: ...
```

### Algorithm (Data Flow)

```
1. repo.get_template() → validate exists (error if None)
2. repo.get_config() → ProgressionConfig (or defaults)
3. If config.enabled == False → return skipped
4. repo.get_normal_sets() → list[dict]
5. If no sets → return insufficient_data
6. Group by workout (exercise_id, start_time)
7. Isolate most recent workout
8. Filter NULL weight_kg or reps from that workout
9. If all sets filtered → return insufficient_data
10. Determine working weight (mode of weights; tie → heavier)
11. Check: ALL valid reps >= rep_max?
     Yes → status="progress", recommended = weight + increment
     No  → status="maintain", recommended = None
12. repo.insert_history(...)
13. Build and return ProgressionStatus
```

### Acceptance Criteria

- [ ] All sets at rep_max → status `"progress"`, recommended = current + increment
- [ ] One set below rep_max → status `"maintain"`, recommended `None`
- [ ] Multiple workouts → only most recent workout matters
- [ ] Sets above rep_max also satisfy the condition (12 reps at rep_max=10 → progress)
- [ ] Working weight = mode; tie → heavier
- [ ] NULL weight_kg sets skipped; NULL reps sets skipped
- [ ] All NULLs in most recent workout → `insufficient_data`
- [ ] No normal sets at all → `insufficient_data`
- [ ] All sets deleted → `insufficient_data`
- [ ] Disabled config (enabled=0) → status `"skipped"`
- [ ] Unknown template ID → status with `error` populated, `recommendation` explains
- [ ] Each check result persisted to `progression_history`
- [ ] History row contains correct `current_weight_kg`, `recommended_weight_kg`, `details`

### Test Requirements

- **Fixtures in conftest.py**: Add multi-workout seed fixtures with exercise templates, multiple workouts with varying dates, and normal + warmup sets across exercises. Follow existing `sample_workout_dict` pattern but with progression-specific data.
- **Engine tests**: One test class per major requirement (TestAllSetsHitRepMax, TestBelowRepMax, TestWorkingWeight, TestNullFiltering, TestInsufficientData, TestDisabledConfig, TestHistoryPersistence)
- **Each scenario**: build in-memory DB with seed data → construct `ProgressionEngine(conn)` → call `check(id)` → assert `ProgressionStatus` fields
- Use `repo.insert_history` spy/assertion to verify persistence
- Cover edge case: `weight_kg = 0` is valid and not treated as NULL
- Cover edge case: sets across different exercises don't pollute each other

### Dependencies

- T2 (models)
- T3 (repo functions)

---

## Task T5: Add progression CLI commands

| Attribute | Value |
|-----------|-------|
| **ID** | T5 |
| **Name** | CLI progression group |
| **Complexity** | M |
| **PR Slice** | PR C (CLI) |

### Files

| File | Action |
|------|--------|
| `src/darth_gain/cli.py` | Modify — add `progression` group, `check`, `config show`, `config set` commands |
| `tests/test_progression_cli.py` | Create |

### Command Structure

```
darth-gain progression check <exercise_template_id>
darth-gain progression config show <exercise_template_id>
darth-gain progression config set <exercise_template_id> [options]
```

- `check` accepts `--db-path` (same as `ingest`)
- `config set` accepts `--rep-min`, `--rep-max`, `--increment`, `--enabled/--disabled`
- Both commands use the existing `Config` → `create_engine` → `create_tables` pattern
- **No HEVY_API_KEY required** — progression commands work entirely against the local database

### Output Format

- `check`: Human-readable output (via `click.echo` or simple formatting). Contains exercise name, current weight, rep range, status, and recommendation. Use clear labels (e.g., `PROGRESS`, `MAINTAIN`, `INSUFFICIENT DATA`, `SKIPPED`).
- `config show`: Displays rep_min, rep_max, weight_increment, enabled status (or defaults if no row)
- `config set`: Outputs confirmation of what was set
- All non-error results exit 0
- Unknown exercise template exits non-zero with clear "not found" message

### Acceptance Criteria

- [ ] `darth-gain --help` shows `progression` in the command list
- [ ] `darth-gain progression --help` shows `check` and `config`
- [ ] `darth-gain progression check <id>` returns correct status for a configured exercise
- [ ] `darth-gain progression check <id>` works without HEVY_API_KEY set
- [ ] `darth-gain progression check <id>` with unknown ID exits non-zero with "not found"
- [ ] `darth-gain progression config show <id>` shows defaults for unconfigured exercise
- [ ] `darth-gain progression config set <id> --increment 5.0` updates only increment
- [ ] `darth-gain progression config set <id> --enabled` sets enabled=1
- [ ] Custom `--db-path` is respected by both `check` and `config` commands

### Test Requirements

- Follow `test_cli.py` patterns: `CliRunner`, `@patch` engine dependencies, **no real DB in CLI tests**
- Mock `ProgressionEngine.check` to return known `ProgressionStatus` values for output tests
- Test output strings contain expected labels and values
- Test exit codes for success (0) and error (non-zero)
- Test that `HEVY_API_KEY` absence does not block progression commands
- Test `config show` with patched `get_config` for both configured and unconfigured cases
- Test `config set` with patched `upsert_config` verifying correct kwargs passed

### Dependencies

- T4 (ProgressionEngine class must exist)

---

## Test Execution Patterns

All tests follow existing codebase conventions:

```bash
# Run all tests for a PR slice
pytest tests/test_db_engine.py -v -k "progression"  # PR A: DDL tests
pytest tests/test_progression_repo.py -v             # PR A: repo tests
pytest tests/test_progression_engine.py -v           # PR B: engine tests
pytest tests/test_progression_cli.py -v              # PR C: CLI tests

# Full regression
pytest
```

### Existing Patterns to Replicate

| Pattern | Source |
|---------|--------|
| Class-based test grouping (`Test*` classes) | All existing test files |
| In-memory SQLite `conn` fixture | `conftest.py::conn`, `test_db_repo.py::conn` |
| `CliRunner` with `@patch` for dependencies | `test_cli.py` |
| `PRAGMA table_info` for schema validation | `test_db_engine.py::TestCreateTables` |
| Seed data inline in test methods or as module-level constants | `test_db_repo.py::SAMPLE_WORKOUT` |
| `sqlite3.Row` assertions via dict key access | All DB tests |

### `details` JSON Schema for History

When engine persists a check result, the `details` column (stored as JSON via `json.dumps`) should contain:

```json
{
  "total_workouts_analyzed": 3,
  "most_recent_workout_date": "2024-06-15T08:00:00Z",
  "sets_analyzed": 3,
  "sets_filtered_null": 0,
  "working_weight_kg": 80.0,
  "weight_increment_kg": 2.5,
  "rep_range": [8, 12],
  "latest_reps": [12, 12, 11]
}
```

---

## Rollback Boundaries

| Slice | Rollback |
|-------|----------|
| **PR A** | `git revert` the PR. If DB exists: `DROP TABLE IF EXISTS progression_config, progression_history` (both new, no data migration needed) |
| **PR B** | `git revert` the PR. No DB schema changes — only new Python module. Zero blast radius on ingest. |
| **PR C** | `git revert` the PR. CLI commands gone. No runtime depends on them. |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Working weight mode algorithm doesn't match user expectation | Low | Medium | Document in algorithm: mode, tie → heavier. Edge-case tests cover all weight combinations. |
| Engine tests miss edge case in NULL filtering | Low | Medium | Cover all combinations: weight NULL, reps NULL, both NULL, valid with mixed NULLs. |
| CLI test mocks diverge from real engine behaviour | Low | Medium | One integration-style test per PR slice uses real in-memory DB + real engine. CLI tests mock only for output format coverage. |
| PR B at ~440 lines exceeds 400 threshold | Medium | Low | Core algorithm + its comprehensive test suite is the most natural atomic slice. Reviewer should treat the tests as the verification they'd request anyway. |
