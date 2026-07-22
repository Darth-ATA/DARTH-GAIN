# Design: Routine View

## Technical Approach

Additive change layering routine awareness on the existing dashboard stack. Reuses `ProgressionEngine`, `exercise_card` partial, flat repo functions, and per-user DB pattern. No new dependencies, no existing route modification.

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|----------|--------|-------------|-----------|
| Schema migration | `PRAGMA table_info` check before `ALTER TABLE` in `create_tables()` | Catch exception on duplicate column | Cleaner than exception flow; `create_tables()` is already idempotent |
| `folder_id` type | `INTEGER` | `TEXT` | SDK `Routine.folder_id` is `Optional[int]` — matches Hevy API |
| `get_routines()` | Paginate SDK with `page_size=10` | Call SDK without params | Template pagination pattern; handles edge case of >10 routines |
| Routine-per-template resolution | Latest-workout join in router query | Store on exercises table | One template may appear across routines over time; most recent workout reflects user's current assignment |
| `workouts.routine_id` FK | None (no constraint) | `REFERENCES routines(id)` | Avoids sync failures when Hevy deletes routines (per proposal) |

## Data Flow

```
Hevy API ──→ HevyClient.get_routines()
                  │
            _routine_to_dict(r) → {id, title, folder_id, ...}
                  │
                  ▼
              Sync pipeline:
                _ensure_templates(api, conn)
                _ensure_routines(api, conn)   ← new
                paginate events...
                  │
            upsert_routines(conn, routines)
            upsert_workout(conn, workout, exercises)
              └─ now includes routine_id from workout dict
                  │
                  ▼
              routines table     +     workouts.routine_id (TEXT NULL)

GET /routines ──→ Router:
  1. Open per-user DB, ensure tables
  2. Query templates (same as dashboard)
  3. Load routines: `SELECT id, title FROM routines`
  4. For each template:
     a. engine.check(tid) → progression status + card dict
     b. Find most recent routine:
        SELECT w.routine_id FROM exercises e
        JOIN workouts w ON e.workout_id = w.id
        WHERE e.exercise_template_id = ?
        ORDER BY w.start_time DESC LIMIT 1
     c. Map routine_id → routine_name (or "Uncategorized")
  5. Group: {routine_name: [cards]} sorted by name + "Uncategorized" last
  6. Render routine_view.html
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/darth_gain/db/engine.py` | Modify | Add `routines` table DDL + `_add_routine_id_column(conn)` helper called from `create_tables()` |
| `src/darth_gain/db/repo.py` | Modify | `upsert_workout`: add `routine_id` TO the SQL columns; new `upsert_routines(conn, routines)`; new `get_routines(conn)` |
| `src/darth_gain/hevy/client.py` | Modify | `_raw_workout_to_dict`: extract `routine_id` passthrough; `_workout_to_dict`: add `routine_id` from SDK model; new `_routine_to_dict(r)`; new `get_routines()` method paginating via `self._client.routines.get_routines()` |
| `src/darth_gain/hevy/sync.py` | Modify | Add `_ensure_routines(api, conn)` alongside `_ensure_templates()` in the sync flow |
| `src/darth_gain/web/routers/routines.py` | Create | `GET /routines` with per-template progression + routine grouping |
| `src/darth_gain/web/templates/routine_view.html` | Create | Jinja2 template extending `base.html`, group sections per routine name, "Uncategorized" section, reuses `exercise_card.html` |
| `src/darth_gain/web/templates/base.html` | Modify | Add `<a href="/routines" class="nav-link">Routines</a>` in the `nav-links` div |
| `src/darth_gain/web/app.py` | Modify | Import and register `routines` router alongside existing routers |
| `tests/test_db_repo.py` | Modify | Tests for `upsert_routines`, `get_routines`, `routine_id` field in `upsert_workout` |
| `tests/test_hevy_client.py` | Modify | Tests for `get_routines()` pagination + `_routine_to_dict` field mapping |
| `tests/test_hevy_sync.py` | Modify | Test `_ensure_routines` is called and populates routines table |
| `tests/test_web_routines.py` | Create | Full suite: auth, empty state, routine grouping, uncategorized, error isolation |

## Interfaces

### DDL additions (engine.py)
```sql
CREATE TABLE IF NOT EXISTS routines (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    folder_id  INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### Column migration helper (engine.py)
```python
def _add_routine_id_column(conn: sqlite3.Connection) -> None:
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(workouts)")]
    if "routine_id" not in columns:
        conn.execute("ALTER TABLE workouts ADD COLUMN routine_id TEXT")
```

### Routine dict shape (HevyClient → repo)
```python
{
    "id": str,            # Hevy routine UUID
    "title": str,          # e.g. "Push / Pull / Legs"
    "folder_id": int|None,
    "created_at": str,
    "updated_at": str,
}
```

### Repo: upsert_routines(conn, routines)
```python
def upsert_routines(conn, routines):
    for r in routines:
        conn.execute(
            "INSERT OR REPLACE INTO routines (id, title, folder_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (r["id"], r["title"], r.get("folder_id"), r.get("created_at"), r.get("updated_at")),
        )
    conn.commit()
```

### Router context structure (routines.py)
```python
{
    "request": request,
    "groups": OrderedDict[str, list[dict]],  # routine_name → [card_dict, ...]
    "ordered_names": list[str],              # sorted routine names, "Uncategorized" last
    "empty": bool,
    "error": str|None,
}
```

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | `_raw_workout_to_dict` passes `routine_id` | Mock raw workout dict with/without routine_id; verify output |
| Unit | `_routine_to_dict` field mapping | Mock SDK Routine model; verify id, title, folder_id, timestamps |
| Unit | `get_routines()` pagination | Mock SDK `PaginatedRoutines` with page_count>1; verify full aggregation |
| Unit | `upsert_routines` CRUD | In-memory DB: insert, replace, query, count |
| Unit | `get_routines(conn)` returns dicts | Verify `folder_id` maps correctly (int/NULL) |
| Unit | `upsert_workout` with routine_id | Verify column populated on insert; replaced on re-upsert |
| Unit | `_ensure_routines` sync flow | MockHevyClient with routines; verify `upsert_routines` called and DB populated |
| Web | GET /routines auth | Follows existing pattern: 302 to login without session |
| Web | GET /routines empty state | No DB → empty message; DB with templates but no workouts → empty |
| Web | GET /routines grouping | Exercises map to routines via workout joins; group headers render correct routine names |
| Web | GET /routines uncategorized | Workouts with NULL/missing routine_id appear under "Uncategorized" |
| Web | GET /routines progression | Each exercise card shows same status fields as dashboard (reuses engine.check) |
| Web | GET /routines error isolation | One template error does not crash the page (catch per-template) |

## Migration / Rollout

**No data migration.** `routine_id` is nullable and additive. Existing workouts render as "Uncategorized" until re-synced. The `ALTER TABLE` runs idempotently via `create_tables()`.

Rollback sequence:
1. Revert `engine.py`: remove `routines` table DDL and `ALTER TABLE` helper
2. Revert `repo.py` changes
3. Remove `routines.py` router and `routine_view.html`
4. Revert `base.html` nav link
5. Unregister router from `app.py`
6. Drop `routines` table manually (no data loss — additive column only)

## Open Questions

None. All interfaces confirmed by reading the SDK source (`hevy_api_wrapper` v1.0.0).
