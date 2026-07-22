# Tasks: Routine View

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 550–650 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (data infra) → PR 2 (web UI) |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Base |
|------|------|-----------|------|
| 1 | Schema, repo, client, sync + data-layer tests | PR 1 | main |
| 2 | Router, template, nav, web tests | PR 2 | main |

## Phase 1: Data Infrastructure (PR 1)

- [x] 1.1 Add `routines` table DDL + `_add_routine_id_column(conn)` in `engine.py`, call from `create_tables()`
- [x] 1.2 Add `_routine_to_dict(r)` and `get_routines()` with pagination in `client.py`; pass `routine_id` through `_raw_workout_to_dict` and `_workout_to_dict`
- [x] 1.3 Add `upsert_routines(conn, routines)` + `get_routines(conn)` in `repo.py`; add `routine_id` column to `upsert_workout` SQL
- [x] 1.4 Add `_ensure_routines(api, conn)` call before event pagination in `sync.py`; add `get_routines` to `MockHevyClient` in `conftest.py`
- [x] 1.5 Tests: `get_routines()` pagination + `_routine_to_dict` + `routine_id` passthrough — consolidated in `tests/test_routines.py`
- [x] 1.6 Tests: `upsert_routines` CRUD + `get_routines` order + `routine_id` in `upsert_workout` — consolidated in `tests/test_routines.py`
- [x] 1.7 Tests: `_ensure_routines` called before events + `routine_id` persisted — consolidated in `tests/test_routines.py`

## Phase 2: Web UI (PR 2)

- [ ] 2.1 Create `routines.py` router with `GET /routines` — per-template progression check, routine grouping via latest-workout join, "Uncategorized" bucket
- [ ] 2.2 Create `routine_view.html` — extends `base.html`, group sections with headers + exercise count, reuses `exercise_card.html`, "Uncategorized" last
- [ ] 2.3 Add "Routines" nav link in `base.html`; import and register `routines.router` in `app.py`
- [ ] 2.4 Create `test_web_routines.py` — auth redirect, empty state, grouping by 2 routines, uncategorized bucket, progression cards, error isolation

## Implementation Order

Data infra first (PR 1) — schema + client + repo + sync must be complete before web UI (PR 2) can exercise the data path. Each PR is independently testable and merges to main.

## Next Step

Forecast exceeds 400 lines. **Decision needed**: proceed with 2 stacked PRs to main, or accept as single PR with `size:exception`?
