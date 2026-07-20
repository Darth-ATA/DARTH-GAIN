# Proposal: Hevy Ingest Pipeline

## Intent

Ingest Hevy workout data into local SQLite storage so DARTH-GAIN can analyze progression offline. First component of the project — establishes the data foundation that all downstream features (progression engine, analysis, reporting) depend on.

## Scope

### In Scope
- Hevy API wrapper (read-only via `hevy-api-wrapper` SDK) for workouts + exercise templates
- SQLite database with events-based delta sync (`GET /v1/workouts/events?since=`)
- CLI `darth-gain ingest` command with `--dry-run`, `--since`, `--db-path`, `--verbose` flags
- Rich progress bar for sync operations
- Skip-and-continue error handling with summary report at end
- Eager exercise template cache (full fetch on first sync)
- Scheduling setup (`cron` / `systemd timer` — documentation + helper script)

### Out of Scope
- Routine syncing (deferred to `progression-engine` change)
- Write-back to Hevy (no `create_workout`, `update_workout`, etc.)
- Progression logic, analysis, or reporting
- Webhook subscriptions for real-time sync

## Capabilities

### New Capabilities
- `hevy-ingestion`: Hevy API integration, events-based delta sync, SQLite persistence, progress UX
- `exercise-cache`: Local cache of exercise templates fetched eagerly on first sync
- `scheduling`: Cron / systemd timer setup for recurring automated ingests

### Modified Capabilities
None — first change, no existing specs.

## Approach

Sync `Client` (no async needed for CLI). Delta sync via events endpoint — paginate all pages, upsert updated workouts, soft-delete deleted ones. Atomic transaction per workout. On first sync, `since` defaults to epoch (full fetch). Exercise templates fetched eagerly once. Error handling: catch per-workout, log, continue, report summary at end. Scheduling via `crontab -e` instructions + optional helper script at `scripts/install-cron.sh`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/darth_gain/cli.py` | New | Click `ingest` command group |
| `src/darth_gain/config.py` | New | Config loading (db path, api key) |
| `src/darth_gain/db/` | New | SQLite connection, schema DDL, repository CRUD |
| `src/darth_gain/hevy/` | New | Hevy client wrapper + sync orchestrator |
| `pyproject.toml` | Modified | Add `platformdirs` dependency if needed |
| `scripts/install-cron.sh` | New | Helper for scheduling setup |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Hevy API is beta — may change structure | Low | Wrap SDK calls, validate shapes, single ingestion boundary |
| Large initial sync (1000+ workouts = 100+ API calls) | Medium | Progress bar + 0.5s inter-page delay, user sees progress |
| `@` char causes silent API failures | Low | Warn or strip in notes/description before sending |

## Rollback Plan

1. Stop cron timer if installed (`crontab -e`, remove line)
2. Delete or rename `~/.darth-gain/workouts.db`
3. If code is unpalatable, revert the commit. This change touches no existing functionality — zero blast radius.

## Dependencies

- `hevy-api-wrapper>=1.0.0` (already in `pyproject.toml`)
- Hevy Pro account + API key (`HEVY_API_TOKEN` env var)

## Success Criteria

- [ ] `darth-gain ingest` fetches all workouts from Hevy and stores them in SQLite
- [ ] Second run syncs only changed workouts (delta, verified via `last_sync_at`)
- [ ] `--dry-run` prints workout summaries without writing to database
- [ ] Deleted workouts on Hevy are soft-deleted locally on next sync
- [ ] Exercise templates cached locally after first sync, no redundant API calls
- [ ] Workout with API failure is skipped, error logged, summary report shows count
- [ ] Scheduling instructions or helper script installs a working cron timer
