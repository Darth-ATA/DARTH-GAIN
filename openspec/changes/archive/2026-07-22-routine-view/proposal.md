# Proposal: Routine View

## Intent

Group exercises by Hevy routine on the web dashboard so users can see which movements need weight progression within each training plan, including exercises done without a routine.

## Scope

### In Scope
- Schema: `routine_id` column on `workouts`, new `routines` table (id, title, folder_id, timestamps)
- Adapter: extract `routine_id` in `_raw_workout_to_dict` and `_workout_to_dict`
- HevyClient: add `get_routines()` method wrapping SDK `routines.get_routines()`
- Repo: persist `routine_id` in `upsert_workout`, add `upsert_routines`
- Sync: fetch all routines during sync and store; link workouts to routines
- New route `GET /routines` — runs `ProgressionEngine.check()` per exercise template, groups by routine name
- New template `routine_view.html` + reuse `partials/exercise_card.html`
- Nav link in `base.html`
- Null `routine_id` → "Uncategorized" bucket

### Out of Scope
- Backfill of `routine_id` for already-synced workouts (deferred — needs full re-sync)
- Routine management (CRUD); routine folder grouping
- Sort/filter controls in routine view (defer to v2)
- Routine detail page (just the grouped list)

## Capabilities

### New Capabilities
- `routine-view`: Groups exercises by Hevy routine with per-exercise progression status; handles uncategorized exercises

### Modified Capabilities
- None — additive change; existing dashboard route stays unmodified

## Approach

1. **Schema migration** — alter `workouts` to add nullable `routine_id TEXT`, create `routines` table. Use `ALTER TABLE ... ADD COLUMN` (idempotent via IF NOT EXISTS check).
2. **Adapter + Repo** — extract `routine_id` from SDK/raw dicts; pass through upsert; add routine-upsert functions.
3. **HevyClient.get_routines()** — paginate all routines from SDK; return as domain dicts.
4. **Sync integration** — call `get_routines()` at start of sync, persist, then inject routine context during workout processing.
5. **Web router** — `GET /routines` reuses same ProgressionEngine and exercise_card partial. Query: exercises joined through workouts → routines, grouping by routine_id/name. Null routine_id coalesces to "Uncategorized".
6. **Template** — `routine_view.html` mirrors dashboard structure with group headers per routine. Add nav link in `base.html`.

### Design decisions
- **No foreign key constraint** on `workouts.routine_id` for now — routine may be deleted on Hevy side, we don't want sync failures
- **Progression check per exercise template** (same as dashboard) — avoids coupling progression logic to routine grouping
- **Routines fetched on every sync** — they're small and rarely change; cache in DB for the view query

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/darth_gain/db/engine.py` | Modified | Add `routines` table DDL + `ALTER TABLE` for `routine_id` |
| `src/darth_gain/db/repo.py` | Modified | `upsert_workout` gets `routine_id` param; new `upsert_routines` |
| `src/darth_gain/hevy/client.py` | Modified | `_raw_workout_to_dict` + `_workout_to_dict` extract `routine_id`; new `get_routines()` |
| `src/darth_gain/web/routers/` | New file | `routines.py` with `GET /routines` |
| `src/darth_gain/web/templates/routine_view.html` | New file | Routine-grouped template |
| `src/darth_gain/web/templates/base.html` | Modified | Add "Routines" nav link |
| `src/darth_gain/web/app.py` | Modified | Register new router |
| `tests/` | Modified | Adapter + repo + web tests for routine flow |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Routine deleted on Hevy side → DB orphan | Low | No FK constraint; render routine_id as "Unknown" if not in routines table |
| Large number of routines | Low | Paginate in SDK; small dataset (typical: <20 routines per user) |
| Re-sync needed for backfill | High | Accepted as deferred. Past workouts show as "Uncategorized"; new syncs populate routine_id going forward |

## Rollback Plan

1. Revert `engine.py` schema changes (remove ALTER TABLE, drop routines table)
2. Revert adapter + repo changes
3. Remove router and template files
4. Unregister router from `app.py`, remove nav link
5. No data loss — `routine_id` column is additive and nullable

## Dependencies

None.

## Success Criteria

- [ ] `GET /routines` renders exercises grouped by routine name, each with progression status
- [ ] Exercises with `routine_id IS NULL` appear under "Uncategorized"
- [ ] Progression check runs per exercise template (reuses existing `ProgressionEngine`)
- [ ] Sync captures and stores `routine_id` from Hevy API without breaking existing sync
- [ ] New nav link navigates to `/routines`
- [ ] All existing tests pass, new tests cover the routine router and adapter
