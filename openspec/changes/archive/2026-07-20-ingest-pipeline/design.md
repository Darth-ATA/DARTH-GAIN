# Design: Hevy Ingest Pipeline

## Technical Approach

Greenfield sync client wrapping `hevy-api-wrapper` SDK with typed domain models, events-based delta sync into local SQLite, and a Click CLI with Rich progress. Every API call flows through a thin adapter layer that translates SDK Pydantic models → our dataclasses, isolating the rest of the codebase from SDK changes.

## Architecture Decisions

### Decision: Module Layout

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Single flat module | Simple but all concerns mixed | ❌ |
| `db/` + `hevy/` subpackages | Clear boundaries, easy to test in isolation | ✅ |
| One file per concern | More files but each has one job: cli, config, hevy/client, hevy/sync, db/repo, db/engine | ✅ |

Structure:

```
src/darth_gain/
├── __init__.py
├── cli.py              # Click "ingest" command
├── config.py           # Config dataclass, env/override resolution
├── db/
│   ├── __init__.py
│   ├── engine.py       # Connection mgmt, schema init, create_tables()
│   └── repo.py         # upsert_workout, soft_delete_workout, get_templates, set_sync_meta
└── hevy/
    ├── __init__.py
    ├── client.py       # Adapter wrapping SDK Client into our domain types
    └── sync.py         # Orchestrator: paginate, progress bar, error isolation
```

### Decision: DB Schema

5 tables, soft-delete via `is_deleted` flag, replace-on-update for exercises/sets.

```
workouts
├── id TEXT PK            ← Hevy's UUID string
├── title TEXT
├── description TEXT
├── start_time TEXT       ← ISO 8601
├── end_time TEXT         ← ISO 8601
├── is_deleted INT DEFAULT 0
├── created_at TEXT       ← local insert
└── updated_at TEXT       ← local update

exercises
├── id INT PK AUTO
├── workout_id TEXT FK → workouts(id)
├── exercise_template_id TEXT
├── title TEXT
├── notes TEXT
├── sort_order INT
└── is_deleted INT DEFAULT 0

sets
├── id INT PK AUTO
├── exercise_id INT FK → exercises(id)
├── set_index INT
├── type TEXT             ← normal|warmup|dropset|failure
├── weight_kg REAL
├── reps INT
├── distance_meters REAL
├── duration_seconds REAL
├── rpe REAL
└── is_deleted INT DEFAULT 0

exercise_templates
├── id TEXT PK            ← Hevy template ID
├── title TEXT
├── type TEXT
├── primary_muscle_group TEXT
├── other_muscle_groups TEXT  ← JSON array
├── equipment TEXT
├── is_custom INT
└── cached_at TEXT

sync_metadata              ← key/value store
├── key TEXT PK
└── value TEXT
```

**Why replace-on-update**: Workouts have mutable exercise/set structures. Tracking individual row diffs adds complexity with zero benefit — our reads are offline analysis, not real-time. On `workout_updated` event: DELETE FROM exercises WHERE workout_id = ? + INSERT. Per-workout atomic transaction.

### Decision: Sync Orchestration Strategy

- **Pacing**: `time.sleep(0.5)` between page calls. The SDK sets page_size=10 max via its validation.
- **Error isolation**: Each workout event wrapped in try/except. On failure → log error, increment `errors` counter, continue to next event. The failed event's `since` timestamp is still consumed (we don't retry mid-sync).
- **Dry-run**: Writes to an in-memory SQLite (`:memory:`), prints summary, discards.
- **Progress measurement**: Two-pass — first count total pages (send one request), then iterate with Rich `Progress`. For first sync with unknown total, use indeterminate mode.

```
sync():
  meta = get_sync_meta()          # last_sync_at from db
  since = meta or epoch           # epoch = full sync
  templates = load_exercise_templates(db)

  if not templates:               # first sync or cache empty
      templates = api.fetch_templates()
      upsert_templates(db, templates)

  page = 1
  while True:
      events = api.get_events(page=page, page_size=10, since=since)
      for event in events.updated:
          with db.transaction():
              upsert_workout(db, event)
      for event in events.deleted:
          soft_delete_workout(db, event.id)
      page += 1
      if page > events.page_count:
          break
      time.sleep(0.5)

  set_sync_meta(db, latest_event_time)
```

### Decision: Config Resolution

| Source | Key | Resolution |
|--------|-----|------------|
| Env var | `HEVY_API_KEY` | Required at runtime. Click validates before calling sync. |
| Env var / default | DB path | `$XDG_DATA_HOME/darth-gain/workouts.db` via `platformdirs`, override with `--db-path` |
| CLI flag | `--since` | Overrides stored `last_sync_at`. ISO 8601 or "epoch" keyword. |
| CLI flag | `--dry-run` | Use `:memory:` SQLite, print summary, no persist. |
| CLI flag | `--verbose` | Enables debug logging per event. |

Add `platformdirs>=4.0` to `pyproject.toml`.

### Decision: Hevy Client Adapter

We DO NOT pass the SDK `Client` through the codebase. Instead:

```python
# src/darth_gain/hevy/client.py
@dataclass
class WorkoutEvent:
    type: Literal["created", "updated", "deleted"]
    workout: Workout | None  # None for deleted events

@dataclass  
class EventsPage:
    page: int
    page_count: int
    events: list[WorkoutEvent]

class HevyClient:
    def __init__(self, api_key: str): ...
    def get_events(self, since: str, page: int = 1) -> EventsPage: ...
    def get_exercise_templates(self) -> list[ExerciseTemplate]: ...
```

This translates `hevy_api_wrapper.models` → our `dataclasses`. If the SDK changes, only this file changes.

## Data Flow

```
CLI (click) ──→ config.py ──→ hevy/sync.py ──→ hevy/client.py ──→ hevy-api-wrapper SDK ──→ Hevy API
                   │               │
                   │               └──→ db/repo.py ──→ SQLite
                   │
              platformdirs
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/darth_gain/cli.py` | Create | `ingest` command group with all flags |
| `src/darth_gain/config.py` | Create | `Config` dataclass, env/override resolution |
| `src/darth_gain/db/__init__.py` | Create | Package |
| `src/darth_gain/db/engine.py` | Create | `create_engine()`, `create_tables()`, `get_connection()` |
| `src/darth_gain/db/repo.py` | Create | All CRUD operations for the 5 tables |
| `src/darth_gain/hevy/__init__.py` | Create | Package |
| `src/darth_gain/hevy/client.py` | Create | SDK adapter, domain types, pagination |
| `src/darth_gain/hevy/sync.py` | Create | Orchestrator — progress, pacing, error isolation |
| `scripts/install-cron.sh` | Create | Crontab helper `*/30 * * * * darth-gain ingest` |
| `pyproject.toml` | Modify | Add `platformdirs>=4.0` to dependencies |

## Testing Strategy

Strict TDD (config: `strict_tdd: true`). Write test before implementation.

| Layer | What | How |
|-------|------|-----|
| Unit — `hevy/client.py` | Adapter translates SDK models → domain dataclasses; pagination iteration logic | Mock `hevy_api_wrapper.Client` with `pytest.MonkeyPatch`. Fixtures: `sample_events_page.json`, `sample_templates.json`. |
| Unit — `db/repo.py` | upsert/soft-delete/query on each table | In-memory SQLite (`:memory:`), raw SQL assertions. Verify transactions roll back on failure. |
| Unit — `hevy/sync.py` | Orchestration: pacing, error isolation, progress, dry-run dispatch | Mock both `HevyClient` and `db/repo.py`. Verify correct call sequence and per-event error handling. |
| Unit — `cli.py` | Flag parsing, `--dry-run` vs real, `--since` override | Click `CliRunner` with isolated filesystem. Assert correct flags reach sync. |
| Integration | End-to-end with a real (sandbox) API call | Manual — requires Hevy Pro API key. Smoke test against `page_size=1` and verify DB state. |

**Fixtures**: Store JSON samples (`tests/fixtures/events_page.json`, `templates.json`) that mirror `hevy-api-wrapper` response shapes.

**Test isolation**: Every test file opens its own `:memory:` SQLite. No shared state.

## Migration / Rollout

No migration — first component of a greenfield project. The database is self-contained and auto-created on first run. Dropping and re-syncing is always an option (it's just remote data).

## Open Questions

- [ ] `hevy-api-wrapper.get_events()` returns events newest-first. For delta sync, should we process reverse-chronological (so latest sync time is first event's timestamp)? Or process all and take max timestamp? **Decision: take max `created_at` across all returned events as the new `last_sync_at`** — simplest, correct.
- [ ] Exercise templates: does the SDK have a dedicated endpoint, or should we use `client.exercise_templates.get_all()`? **Assumption: yes, based on SDK docs**. Verify during implementation.
