# Proposal: Web Dashboard for DARTH-GAIN

## Intent

Add a web UI and multi-user support so users can view workout progression via browser instead of CLI, and share the instance with family/housemates. Without this, the progression engine is only accessible via terminal — a barrier for casual use.

## Scope

### In Scope

- FastAPI app + HTMX/Jinja2 templates for dashboard views
- Session-based auth with login page, per-user SQLite isolation
- Progressive delivery as 4 stacked PRs (A: foundation + auth + Docker, B: dashboard, C: detail + config, D: multi-user cron + migration)
- WAL mode on all SQLite connections for concurrent read/write safety

### Out of Scope

- SPA framework (React/Svelte/Vue), push notifications, admin panel, Hevy write-back, webhooks, OAuth providers

## Capabilities

### New Capabilities

- `web-auth`: Login, logout, session management, registration
- `web-dashboard`: Exercise list grouped by muscle group with progression badges
- `web-exercise-detail`: Per-exercise history table + config editor

### Modified Capabilities

None — existing CLI specs unchanged.

## Approach

FastAPI app in `src/darth_gain/web/` reuses existing DB engine and ProgressionEngine directly. Per-user SQLite files at `/data/user_{id}/workouts.db` (zero schema changes). Shared `users.db` for auth with bcrypt-hashed passwords. Sessions via signed cookies (`itsdangerous`). Templates rendered server-side; HTMX for inline edits. Optional deps in `pyproject.toml` under `[project.optional-dependencies] web`. Dockerfile based on python:3.11-slim with volume at `/data/`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/darth_gain/web/` | New | ~6 modules, 4 templates, minimal static |
| `pyproject.toml` | Modified | Optional `[web]` deps group |
| `src/darth_gain/db/engine.py` | Modified | Add `PRAGMA journal_mode=WAL` |
| `src/darth_gain/progression/repo.py` | Modified | Add `get_all_history()` aggregate query |
| `tests/` | New | ~5 test files for web routes |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| WAL + cron concurrency | Low | WAL on every connection; stagger per user |
| API keys on disk (no encryption) | Low (homelab) | Document; acceptable behind NPM |
| Existing single-user DB migration | Medium | One-time copy script; CLI unaffected |
| PRs exceed 400 lines | High | Enforce 4 stacked PRs with review gate |

## Rollback Plan

1. **Code**: revert commits (isolated to `src/darth_gain/web/`)
2. **Docker**: `docker compose down --rmi all --volumes`
3. **Data**: delete `/data/` directory — existing `~/.local/share/darth-gain/workouts.db` untouched
4. **Deps**: undo `pyproject.toml` additions, no CLI impact

## Dependencies

- FastAPI, uvicorn, Jinja2, itsdangerous, python-multipart, bcrypt
- Docker + compose for deployment (LXC 101 via Terraform)

## Success Criteria

- [ ] `docker compose up` boots a working web UI on a known port
- [ ] Registration + login creates session and routes to per-user DB
- [ ] Dashboard displays exercise list with correct progression status badges
- [ ] Exercise detail page shows history and allows config edits
- [ ] CLI unchanged — all existing commands pass tests
- [ ] 4 chained PRs each under 400 lines, independently reviewable
