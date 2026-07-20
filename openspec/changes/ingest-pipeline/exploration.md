# Exploration: Hevy API / Ingest Pipeline

## Executive Summary

The `hevy-api-wrapper` SDK (v1.0.0) provides excellent coverage of the Hevy API with sync/async clients, Pydantic v2 models, built-in retry with exponential backoff, and typed error handling. The Hevy API has a purpose-built **events endpoint** (`GET /v1/workouts/events?since=`) specifically designed for delta/incremental sync — this is the cornerstone of the ingest pipeline.

**Key findings:**
- SDK has everything needed — no custom HTTP client needed
- Events endpoint handles delta sync natively (updated + deleted workouts)
- Page size max 10 for workouts/events, max 100 for exercise templates
- No documented rate limits, but SDK retries 429/5xx automatically
- Webhook subscriptions exist for real-time notifications (bonus, not needed for MVP)
- API key requires Hevy Pro, available at `hevy.com/settings?developer`

---

## 1. hevy-api-wrapper SDK

### Location
`hevy_api_wrapper` v1.0.0 — installed via pip, lives in site-packages.

### Available Endpoints & Methods

#### Workouts (`client.workouts`)
| Method | HTTP | Description | Page Size Limit |
|--------|------|-------------|-----------------|
| `get_workouts(page, page_size)` | GET /v1/workouts | List workouts | 1-10 |
| `get_workout(workout_id)` | GET /v1/workouts/{id} | Single workout | — |
| `create_workout(body)` | POST /v1/workouts | Create workout | — |
| `update_workout(workout_id, body)` | PUT /v1/workouts/{id} | Update workout | — |
| `get_events(since, page, page_size)` | GET /v1/workouts/events | Delta sync events | 1-10 |
| `get_count()` | GET /v1/workouts/count | Total workout count | — |

#### Routines (`client.routines`)
| Method | HTTP | Description |
|--------|------|-------------|
| `get_routines(page, page_size)` | GET /v1/routines | List routines |
| `get_routine(routine_id)` | GET /v1/routines/{id} | Single routine |
| `create_routine(body)` | POST /v1/routines | Create routine |
| `update_routine(routine_id, body)` | PUT /v1/routines/{id} | Update routine |

#### Exercise Templates (`client.exercise_templates`)
| Method | HTTP | Description | Page Size Limit |
|--------|------|-------------|-----------------|
| `get_exercise_templates(page, page_size)` | GET /v1/exercise_templates | List templates | 1-100 |
| `get_exercise_template(template_id)` | GET /v1/exercise_templates/{id} | Single template | — |
| `create_custom_exercise(body)` | POST /v1/exercise_templates | Create custom exercise | — |

#### Exercise History (`client.exercise_history`)
| Method | HTTP | Description |
|--------|------|-------------|
| `get_exercise_history(exercise_template_id, start_date, end_date)` | GET /v1/exercise_history/{id} | Per-exercise history |

#### Routine Folders (`client.routine_folders`)
| Method | HTTP | Description |
|--------|------|-------------|
| `get_routine_folders(page, page_size)` | GET /v1/routine_folders | List folders |
| `get_routine_folder(folder_id)` | GET /v1/routine_folders/{id} | Single folder |
| `create_routine_folder(body)` | POST /v1/routine_folders | Create folder |

### Auth
- Header: `api-key` (configurable, but default).
- `Client.from_env(env_var="HEVY_API_TOKEN")` reads from env var.
- Errors: `AuthError` (401/403), `NotFoundError` (404), `RateLimitError` (429), `ServerError` (5xx), `ValidationError` (400).

### Retry Logic
Built into `_request()`: retries on 429, 500, 502, 503, 504 with exponential backoff (`backoff_factor * 2^(retries-1)`). Default: max 3 retries, 0.5s factor. **This is good — we don't need to add our own retry.**

### Pagination
- All list endpoints use `page` (1-indexed) + `pageSize`.
- Responses include `page` + `page_count` for iterating.
- Max `pageSize` varies: 10 for workouts, routines, events, folders; **100 for exercise templates**.

### Sync vs Async
Both `Client` (sync) and `AsyncClient` (async) exist. For a CLI tool, **sync is simpler and appropriate**. No benefit to async for a one-shot `ingest` command.

---

## 2. Hevy API Data Model

### Workout (the core entity)
```python
class Workout(BaseModel):
    id: str                        # UUID
    title: str                     # e.g. "Push Day"
    routine_id: Optional[str]      # If started from a routine
    description: Optional[str]
    start_time: str                # ISO 8601
    end_time: str                  # ISO 8601
    updated_at: str                # ISO 8601 — key for delta sync
    created_at: str                # ISO 8601
    exercises: List[WorkoutExercise]

class WorkoutExercise(BaseModel):
    index: int
    title: str                     # e.g. "Bench Press"
    notes: Optional[str]
    exercise_template_id: str      # Links to ExerciseTemplate
    supersets_id: Optional[int]
    sets: List[WorkoutSet]

class WorkoutSet(BaseModel):
    index: int
    type: str                      # "normal" | "warmup" | "dropset" | "failure"
    weight_kg: Optional[float]
    reps: Optional[int]
    distance_meters: Optional[float]
    duration_seconds: Optional[float]
    rpe: Optional[float]           # 6, 7, 7.5, 8, 8.5, 9, 9.5, 10
    custom_metric: Optional[float]
```

### Routine
```python
class Routine(BaseModel):
    id: str
    title: str
    folder_id: Optional[int]
    updated_at: str
    created_at: str
    exercises: List[RoutineExercise]

class RoutineExercise(BaseModel):
    index: int
    title: str
    rest_seconds: Optional[int]
    notes: Optional[str]
    exercise_template_id: str
    supersets_id: Optional[int]
    sets: List[RoutineSet]         # RoutineSet has same fields as WorkoutSet + rep_range

class RoutineSet(BaseModel):
    index: int
    type: str
    weight_kg: Optional[float]
    reps: Optional[int]
    rep_range: Optional[RepRange]  # RepRange(start: float, end: float) — target range
    distance_meters: Optional[float]
    duration_seconds: Optional[float]
    rpe: Optional[float]
    custom_metric: Optional[float]
```

### ExerciseTemplate
```python
class ExerciseTemplate(BaseModel):
    id: str
    title: str                     # "Barbell Bench Press"
    type: CustomExerciseType       # Enum: weight_reps, reps_only, duration, etc.
    primary_muscle_group: MuscleGroup
    secondary_muscle_groups: List[str]
    is_custom: bool
```

### Exercise History (simplified per-set view)
```python
class ExerciseHistoryEntry(BaseModel):
    workout_id: str
    workout_title: str
    workout_start_time: str
    workout_end_time: str
    exercise_template_id: str
    weight_kg: Optional[float]
    reps: Optional[int]
    set_type: str                  # "warmup" | "normal" | "failure" | "dropset"
    rpe: Optional[float]
```

### Events (delta sync)
```python
# Discriminated union:
Event = UpdatedWorkout | DeletedWorkout

class UpdatedWorkout(BaseModel):
    type: Literal["updated"]
    workout: Workout               # Full workout object

class DeletedWorkout(BaseModel):
    type: Literal["deleted"]
    id: str
    deleted_at: str                # ISO 8601
```

### Key Observations
- **No RIR field** — Hevy uses RPE, not RIR. Our progression logic will work with RPE.
- **Routine sets have `rep_range`** (target rep range like "8-12"), while **workout sets have actual `reps`** performed.
- **Exercise type variants** matter: `weight_reps` has weight_kg + reps; `reps_only` has reps only; `duration` has duration_seconds only.
- **No webhook for updates** — webhooks fire on creation only. This means the events endpoint is necessary for catching edits.

---

## 3. Incremental Sync Strategy

### The Events Endpoint (Primary Mechanism)
`GET /v1/workouts/events?since=<ISO8601_timestamp>`

This is **purpose-built for delta sync** as stated in the API docs:
> *"Retrieve a paged list of workout events (updates or deletes) since a given date. Events are ordered from newest to oldest. The intention is to allow clients to keep their local cache of workouts up to date without having to fetch the entire list of workouts."*

**Recommended strategy:**
1. Store `last_sync_at` timestamp in SQLite (ISO 8601, UTC).
2. On ingest, call `get_events(since=last_sync_at)`.
3. For each `UpdatedWorkout` event: upsert the workout + its exercises + sets.
4. For each `DeletedWorkout` event: mark the workout as deleted (soft delete).
5. Update `last_sync_at` to the current time after successful processing.
6. If `page_count > 1`, paginate through all pages.
7. **Edge case — first sync:** `since` defaults to epoch, fetches ALL workouts. Consider a separate full-sync path that uses `get_workouts()` instead (or accept the pagination).

### Timestamp Fields
| Field | Entity | Use for Sync? |
|-------|--------|---------------|
| `created_at` | Workout | When it was first created |
| `updated_at` | Workout | **Best for event `since` filtering** |
| `start_time` | Workout | When the session started |
| `end_time` | Workout | When the session ended |
| `deleted_at` | Event | When it was deleted |

### Pagination Constraints
- Max 10 workouts/events per page.
- Response has `page` + `page_count` (total pages).
- If a user has 500 workouts, initial sync = 50 API calls.
- **At 1 call per 0.5s ~ 25s for initial sync** — acceptable for CLI.

### Rate Limits
- **No official rate limits documented.** The API beta disclaimer warns: *"we make no guarantees that we won't completely change the structure or abandon the project entirely."*
- Common REST API patterns suggest rate limiting is informal — the SDK handles 429s with backoff.
- **Recommendation:** Be conservative — add a 0.5s delay between pages during initial sync to avoid triggering heuristics.

### Webhooks (Optional Enhancement)
Webhook subscriptions exist:
- `POST /v1/webhooks` — create subscription, receives POST on workout creation
- Endpoint must respond within 5 seconds
- Only fires on **creation**, not updates

**Not needed for MVP** but could be a future enhancement for near-real-time sync.

### Full Sync vs Delta Sync Decision

| Aspect | Full Sync (get_workouts) | Delta Sync (get_events) |
|--------|------------------------|------------------------|
| First run | Paginate all pages | Same (since=epoch) |
| Subsequent runs | Unnecessary overhead | Only changed workouts |
| Detects updates | Would need to re-fetch all | ✅ Yes, via events |
| Detects deletes | Would need to diff | ✅ Yes, via events |
| API calls | O(n/10) always | O(changes/10) |

**Winner: Events endpoint for all runs.**

**But:** The events endpoint returns full workout objects for updates. This means an event that changes a single field sends the entire workout. That's fine — the SDK handles deserialization.

---

## 4. SQLite Schema Design

### Design Principles
1. **Faithful representation** — store exactly what the API returns, no premature aggregation.
2. **Idempotent upserts** — same data ingested twice = same state (no duplicates).
3. **Sync metadata** — track what was synced and when.
4. **Query-friendly** — indexes for the queries the progression engine will need.

### Proposed Schema

```sql
-- Sync state tracking
CREATE TABLE IF NOT EXISTS _sync_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Last successful sync timestamp
INSERT INTO _sync_metadata (key, value) VALUES ('last_sync_at', '1970-01-01T00:00:00Z');

-- Exercise templates cache
CREATE TABLE IF NOT EXISTS exercise_templates (
    id                       TEXT PRIMARY KEY,          -- Hevy UUID
    title                    TEXT NOT NULL,
    type                     TEXT NOT NULL,              -- weight_reps, reps_only, etc.
    primary_muscle_group     TEXT NOT NULL,
    secondary_muscle_groups  TEXT NOT NULL DEFAULT '',   -- JSON array or comma-separated
    is_custom                INTEGER NOT NULL DEFAULT 0,
    synced_at                TEXT NOT NULL               -- ISO 8601
);

-- Workouts
CREATE TABLE IF NOT EXISTS workouts (
    id           TEXT PRIMARY KEY,              -- Hevy UUID
    title        TEXT NOT NULL,
    routine_id   TEXT,                           -- nullable if ad-hoc
    description  TEXT,
    start_time   TEXT NOT NULL,                  -- ISO 8601
    end_time     TEXT NOT NULL,                  -- ISO 8601
    created_at   TEXT NOT NULL,                  -- ISO 8601
    updated_at   TEXT NOT NULL,                  -- ISO 8601
    is_deleted   INTEGER NOT NULL DEFAULT 0,     -- soft delete from events
    synced_at    TEXT NOT NULL                   -- ISO 8601 — when WE synced it
);

CREATE INDEX idx_workouts_start_time ON workouts(start_time);
CREATE INDEX idx_workouts_updated_at ON workouts(updated_at);
CREATE INDEX idx_workouts_routine_id ON workouts(routine_id);

-- Exercises within a workout
CREATE TABLE IF NOT EXISTS workout_exercises (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id           TEXT NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
    exercise_index       INTEGER NOT NULL,
    title                TEXT NOT NULL,
    notes                TEXT,
    exercise_template_id TEXT NOT NULL,
    supersets_id         INTEGER,
    UNIQUE(workout_id, exercise_index)
);

CREATE INDEX idx_we_workout_id ON workout_exercises(workout_id);
CREATE INDEX idx_we_template_id ON workout_exercises(exercise_template_id);

-- Individual sets
CREATE TABLE IF NOT EXISTS workout_sets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id      TEXT NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
    exercise_index  INTEGER NOT NULL,
    set_index       INTEGER NOT NULL,
    set_type        TEXT NOT NULL,                   -- 'normal' | 'warmup' | 'dropset' | 'failure'
    weight_kg       REAL,
    reps            INTEGER,
    distance_meters REAL,
    duration_seconds REAL,
    rpe             REAL,
    custom_metric   REAL,
    FOREIGN KEY (workout_id, exercise_index)
        REFERENCES workout_exercises(workout_id, exercise_index),
    UNIQUE(workout_id, exercise_index, set_index)
);

CREATE INDEX idx_ws_workout_id ON workout_sets(workout_id);

-- Routines (for future use in analysis/prescription)
CREATE TABLE IF NOT EXISTS routines (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    folder_id   INTEGER,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    synced_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS routine_exercises (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    routine_id           TEXT NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
    exercise_index       INTEGER NOT NULL,
    title                TEXT NOT NULL,
    rest_seconds         INTEGER,
    notes                TEXT,
    exercise_template_id TEXT NOT NULL,
    supersets_id         INTEGER,
    UNIQUE(routine_id, exercise_index)
);

CREATE TABLE IF NOT EXISTS routine_sets (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    routine_id       TEXT NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
    exercise_index   INTEGER NOT NULL,
    set_index        INTEGER NOT NULL,
    set_type         TEXT NOT NULL,
    weight_kg        REAL,
    reps             INTEGER,
    rep_range_start  REAL,
    rep_range_end    REAL,
    distance_meters  REAL,
    duration_seconds REAL,
    rpe              REAL,
    custom_metric    REAL,
    UNIQUE(routine_id, exercise_index, set_index)
);
```

### Why this schema

1. **`workout_exercises` uses composite `(workout_id, exercise_index)` as natural key** — matches the API model where `index` is the ordering field.
2. **CASCADE deletes** — when a workout is replaced (update event), old data cleans up automatically.
3. **`is_deleted` flag** on workouts — we keep the row to avoid re-fetching if the event endpoint drops old deletions.
4. **`synced_at` on every row** — audit trail for debugging sync issues.
5. **Exercise templates cached locally** — avoids repeated API calls for template lookups.

### Query Patterns the Progression Engine Will Need

```sql
-- All sets for an exercise across recent workouts (for progression analysis)
SELECT ws.*
FROM workout_sets ws
JOIN workouts w ON ws.workout_id = w.id
WHERE ws.exercise_index = ?
  AND w.start_time >= date('now', '-90 days')
  AND w.is_deleted = 0
ORDER BY w.start_time DESC, ws.set_index;

-- Latest workout for a routine (to compare against template)
SELECT * FROM workouts
WHERE routine_id = ?
  AND is_deleted = 0
ORDER BY start_time DESC
LIMIT 1;

-- Summary: best set per exercise per workout
SELECT
    w.id AS workout_id,
    w.start_time,
    we.exercise_template_id,
    we.title,
    MAX(ws.weight_kg) AS max_weight,
    MAX(ws.reps) AS max_reps,
    ws.set_type
FROM workouts w
JOIN workout_exercises we ON w.id = we.workout_id
JOIN workout_sets ws ON w.id = ws.workout_id AND we.exercise_index = ws.exercise_index
WHERE ws.set_type = 'normal'
  AND w.is_deleted = 0
GROUP BY w.id, we.exercise_index
ORDER BY w.start_time DESC;
```

---

## 5. Click CLI Integration

### Proposed Command Structure

```python
# src/darth_gain/cli.py
import click

@click.group()
def cli():
    """DARTH-GAIN: The dark side of progressive overload."""

@cli.command()
@click.option("--since", "-s", default=None,
              help="ISO 8601 timestamp to sync from (default: last sync timestamp)")
@click.option("--dry-run", "-n", is_flag=True,
              help="Fetch and display workouts without storing")
@click.option("--verbose", "-v", is_flag=True,
              help="Detailed logging output")
@click.option("--db-path", default=None,
              help="Path to SQLite database (default: ~/.darth-gain/workouts.db)")
def ingest(since, dry_run, verbose, db_path):
    """Ingest workout data from Hevy into local SQLite storage."""
    ...
```

### Rich Library for Output
The project already has `rich` as a dependency. Use it for:
- Progress bars during long initial syncs
- Pretty tables for `--dry-run` preview
- Colored status messages

### Module Structure (Proposed)

```
src/darth_gain/
├── __init__.py
├── cli.py                 # Click commands
├── config.py              # Config loading (db path, api key)
├── db/
│   ├── __init__.py
│   ├── connection.py      # SQLite connection management
│   ├── schema.py          # DDL statements + migrations
│   └── repository.py      # CRUD operations
├── hevy/
│   ├── __init__.py
│   ├── client.py          # Hevy client wrapper
│   └── sync.py            # Sync logic (fetch + store)
└── models.py              # Optional: domain models
```

---

## 6. API Key Setup Instructions

### Prerequisites
1. **Hevy Pro subscription** (required for API access).
2. Navigate to [hevy.com/settings?developer](https://hevy.com/settings?developer).
3. Generate an API key.

### Configuration (for development)
```bash
# Set environment variable (SDK default env var name)
export HEVY_API_TOKEN="your-api-key-here"

# Or use .env file (already in .gitignore)
echo "HEVY_API_TOKEN=your-api-key-here" > .env
```

The SDK's `Client.from_env()` reads `HEVY_API_TOKEN` by default.

### Verification
```python
from hevy_api_wrapper import Client

client = Client.from_env()
count = client.workouts.get_count()
print(f"You have {count} workouts!")
```

---

## Recommended Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Sync client** | `Client` (sync) | CLI is one-shot, no benefit from async |
| **Delta sync** | Events endpoint | Purpose-built, captures updates AND deletes |
| **SQLite** | Local file, auto-created | Zero config, matches project scope |
| **First sync** | Paginate events with `since=epoch` | Works with existing endpoint |
| **Retry** | Rely on SDK built-in | Already handles 429/5xx with backoff |
| **Exercise cache** | Full sync on first ingest | Templates don't change often; store locally |
| **DB location** | `~/.darth-gain/workouts.db` | XDG-friendly (via `click.Path` or `platformdirs`) |
| **Transaction** | Atomic upsert per workout | One workout = one transaction, avoid partial state |

---

## Gotchas & Risks

1. **API is beta** — Hevy explicitly says "we make no guarantees that we won't completely change the structure or abandon the project." Build defensively, validate responses.
2. **No DELETE endpoint on templates** — once you create a custom exercise via API, you can only delete it manually in the app.
3. **`@` character in text fields** — Hevy API silently fails on `@` in title/description/notes. Need to strip or warn.
4. **Events ordering** — newest to oldest. Important: process events in reverse (oldest-first) when applying to local state, OR process all events for the same workout in chronological order.
5. **Events granularity** — an event might be "workout updated" but you don't know *what* changed. You get the full workout object. Minimal concern but worth testing.
6. **Deleted workout event doesn't include the workout data** — only `id` and `deleted_at`. Fine for cleanup but means you can't recover.
7. **No timezone in timestamps** — the API returns ISO 8601 strings. Assume UTC, but verify with real data.
8. **Page size is small** — max 10 per page. Initial sync for a user with 1000+ workouts = 100+ API calls. Add a progress bar and conservative pacing.

---

## Ready for Proposal

**Yes.** All required information has been gathered. The orchestrator can proceed to the Proposal phase with confidence in the architecture decisions.

The key proposal items to address:
1. Precisely how to handle the initial (full) sync vs subsequent (delta) syncs
2. Whether to cache exercise templates on first sync or fetch on demand
3. The exact error-handling policy (fail-fast vs. skip-and-continue)
4. Testing strategy (mock the SDK responses, use golden files for API shapes)
