# Design: Progression Engine

## Technical Approach

New `src/darth_gain/progression/` module with a deterministic double progression algorithm. The `ProgressionEngine` class (in `__init__.py`) queries normal set history for an exercise, checks if the most recent workout's sets all meet the top of the configured rep range, and recommends a weight increase when criteria are met. Config and history are stored in new SQLite tables appended to the existing DDL. The CLI gets a `progression` group with `check` and `config` subcommands, following the existing Click and DB init patterns.

## Architecture Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Module layout | Engine class in `__init__.py`, `models.py` + `repo.py` as submodules | Matches task spec — single public class as package entry point |
| Repo style | Module-level functions | Follows existing `db/repo.py` pattern; simple CRUD doesn't need OOP |
| History schema | Status-based per spec (`status`, `current_weight_kg`, `recommended_weight_kg`, `details`) | Spec is authoritative over task description's suggested columns; rich status enables detailed CLI output |
| Working weight | Mode of weights in most recent workout; tie → heavier | Per spec — deterministic, intuitive for gym context |
| Config defaults | Hard-coded as constants in engine | Config row may not exist; defaults (8-12, 2.5kg, enabled) must work without a DB row |
| DB init per command | `create_engine` + `create_tables` per CLI invocation | Matches `ingest` pattern; commands are independent and tables are created idempotently |
| Config command pattern | `config show` + `config set` sub-subcommands | Per CLI spec; `show` reads + prints, `set` upserts with partial update via current read |

## Data Flow

```
CLI (progression check <id>)
 │
 ├── Config(db_path) → create_engine() → create_tables()
 │
 └── ProgressionEngine.check(template_id)
       │
       ├── 1. repo.get_template(template_id) → validate exists
       ├── 2. repo.get_config(template_id) → ProgressionConfig (or defaults)
       │       └── progression_config table (or 8-12, 2.5kg, enabled)
       ├── 3. repo.get_normal_sets(template_id)
       │       └── sets JOIN exercises JOIN workouts
       │           WHERE type='normal' AND is_deleted=0 ORDER BY start_time
       ├── 4. Group by workout → isolate most recent workout
       ├── 5. Filter NULL weight_kg/reps from that workout
       │       └── If no valid sets remain → insufficient_data
       ├── 6. Determine working weight (mode; tie → heavier)
       ├── 7. Check: ALL valid reps >= rep_max?
       │       ├── Yes → status="progress", recommended = weight + increment
       │       └── No  → status="maintain", recommended = None
       ├── 8. Build ProgressionStatus (rich result for CLI)
       └── 9. repo.insert_history(...) → progression_history table
```

## File Changes

| File | Action | Description |
|---|---|---|
| `src/darth_gain/progression/__init__.py` | Create | `ProgressionEngine` class with `check(template_id)` |
| `src/darth_gain/progression/models.py` | Create | `ProgressionConfig`, `ProgressionStatus` dataclasses |
| `src/darth_gain/progression/repo.py` | Create | `get_template()`, `get_config()`, `upsert_config()`, `get_normal_sets()`, `insert_history()` |
| `src/darth_gain/db/engine.py` | Modify | Add `progression_config` + `progression_history` DDL to `SCHEMA_SQL` |
| `src/darth_gain/cli.py` | Modify | Add `progression` group + `check`/`config show`/`config set` commands |
| `tests/conftest.py` | Modify | Add multi-workout progression test fixtures |
| `tests/test_progression_engine.py` | Create | Unit tests for algorithm scenarios |
| `tests/test_progression_repo.py` | Create | Tests for repo CRUD + default resolution |

## Interfaces / Contracts

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

**Repo functions** — module-level, same style as `db/repo.py`:

```python
def get_template(conn, template_id: str) -> dict | None
def get_config(conn, template_id: str) -> ProgressionConfig  # uses defaults if no row
def upsert_config(conn, template_id: str, **kwargs) -> None   # partial update
def get_normal_sets(conn, template_id: str) -> list[dict]     # chronological by workout
def insert_history(conn, template_id: str, status: str,       # persists check result
                   current_weight: float | None,
                   recommended_weight: float | None,
                   details: dict | None) -> None
```

**DDL additions** appended to `SCHEMA_SQL` in `engine.py`:

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

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | Algorithm: all sets hit max → progress, one below → maintain, all below → maintain | In-memory `conn` fixture; seed sets across multiple workouts; call `engine.check()` |
| Unit | Edge cases: NULL weights/reps filtered, all NULL → insufficient, no history → insufficient | Synthetic sets with NULL fields |
| Unit | Working weight: mode resolution, tie → heavier | Repeat weight across sets; assert `current_weight_kg` |
| Unit | Disabled config: `enabled=0` → skipped | Seed config row; assert status "skipped" |
| Unit | Repo defaults: no config row returns 8-12/2.5/enabled | Call `get_config()` with no row; assert defaults |
| Unit | Repo CRUD: upsert, overwrite, history insert | Assert row counts and values |
| CLI | `check <id>` output format, exit codes, no API key | `CliRunner` with patched engine |
| CLI | `config show` / `config set` subcommands | `CliRunner` with patched repo functions |

## Migration / Rollout

No migration needed. `create_tables()` is idempotent (`CREATE TABLE IF NOT EXISTS`). Existing databases gain the new tables on the first `progression` command execution. Backward compatible — zero impact on existing `ingest` functionality.

## Open Questions

None. All design decisions are resolved against specs and codebase conventions.
