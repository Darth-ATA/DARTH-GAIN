# Tasks: Hevy Ingest Pipeline

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1,100-1,300 (11 src + 8 test/fixture + doc + script) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (foundation) → PR 2 (hevy) → PR 3 (CLI + scheduling) |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Foundation: config, DB engine, DB repo | PR 1 | Includes tests, no Hevy dependency |
| 2 | Hevy client adapter + sync orchestrator | PR 2 | Depends on PR 1, tested with mocks + fixtures |
| 3 | CLI command + scheduling + docs | PR 3 | Depends on PR 2, integration-verified |

## Phase 1: Foundation

- [x] 1.1 Add `platformdirs>=4.0` to `pyproject.toml`
- [x] 1.2 Create `src/darth_gain/config.py` — `Config` dataclass, env/override resolution (TDD)
- [x] 1.3 Create `src/darth_gain/db/engine.py` — connection mgmt, DDL for 5 tables + sync_metadata (TDD)
- [x] 1.4 Create `src/darth_gain/db/repo.py` — upsert_workout, soft_delete, template CRUD, sync_meta (TDD)

## Phase 2: Hevy Client & Sync

- [x] 2.1 Create `tests/fixtures/events_page.json` + `templates.json` matching SDK response shapes (minimal inline variant)
- [x] 2.2 Create `src/darth_gain/hevy/client.py` — domain dataclasses + `HevyClient` adapter (TDD)
- [x] 2.3 Create `src/darth_gain/hevy/sync.py` — orchestrator: paginate, 0.5s pace, error isolation, Rich progress, dry-run (TDD)
- [x] 2.4 Create `tests/conftest.py` — shared fixtures: in-memory DB, mock HevyClient, domain objects

## Phase 3: CLI & Wiring

- [ ] 3.1 Create `src/darth_gain/cli.py` — Click `ingest` command with all flags (TDD, spec scenarios)
- [ ] 3.2 Create `src/darth_gain/__init__.py`, `db/__init__.py`, `hevy/__init__.py` packages
- [ ] 3.3 Create `scripts/install-cron.sh` — idempotent crontab helper with `--remove`, `--status`

## Phase 4: Integration & Verification

- [ ] 4.1 Verify all 14 spec scenarios pass (ingestion 10, cache 3, scheduling 1)
- [ ] 4.2 Run end-to-end test: config→sync→db with mocked API responses
- [ ] 4.3 Verify non-TTY progress bar suppression and summary output for cron

## Phase 5: Documentation

- [ ] 5.1 Create `SCHEDULING.md` — cron setup, env vars, verification, removal instructions
