# Tasks: Web Dashboard for DARTH-GAIN

## Review Workload Forecast

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

| Metric | Value |
|--------|-------|
| Total estimated lines | ~1600 (4 stacked PRs) |
| 400-line budget risk | **High** (PR A ~600) |
| Chained PRs | Yes |
| Strategy | stacked-to-main |
| Delivery | auto-chain |

⚠️ PR A ~600 lines — consider splitting A1 (skeleton + Docker) + A2 (auth routes).

### Work Units

| Unit | Goal | PR | Test cmd | Rollback |
|------|------|----|----------|----------|
| 1 | Auth + app + Docker | A | `pytest tests/test_web_auth.py` | revert `web/` + Docker + deps |
| 2 | Dashboard | B | `pytest tests/test_web_dashboard.py` | revert dashboard router + template |
| 3 | Detail + Config | C | `pytest tests/test_web_exercises.py` | revert exercises router + template |
| 4 | Multi-user + Cron | D | `pytest tests/test_multi_user.py` | revert engine + scripts/ |

## Phase 1: Foundation & Auth (PR A)

- [x] 1.1 Add WAL pragma + users.db DDL to `db/engine.py`
- [x] 1.2 Add `[project.optional-dependencies] web` to `pyproject.toml`
- [x] 1.3 RED: `tests/test_web_auth.py` — DDL, health, login, logout, middleware
- [x] 1.4 Create `web/__init__.py` + `app.py` — FastAPI factory + lifespan
- [x] 1.5 Create `web/auth.py` — itsdangerous session sign/verify
- [x] 1.6 Create `web/deps.py` — `get_current_user`, `get_db` (per-user + WAL)
- [x] 1.7 Create `routers/__init__.py` + `routers/auth.py` — health, login, logout
- [x] 1.8 Create `templates/base.html` + `login.html`
- [x] 1.9 Create `static/css/app.css` — dark-friendly responsive base
- [x] 1.10 GREEN: Pass RED tests

## Phase 2: Docker (PR A cont.)

- [x] 2.1 Create `Dockerfile` — 3.13-slim, `pip install .[web]`, uvicorn
- [x] 2.2 Create `docker-compose.yml` — web service, `/data/` volume, env
- [x] 2.3 Verify `docker compose up` + health endpoint 200

## Phase 3: Dashboard (PR B)

- [x] 3.1 RED: `tests/test_web_dashboard.py` — list, empty/error states, grouping
- [x] 3.2 Create `routers/dashboard.py` — `GET /` with engine check + group
- [x] 3.3 Create `templates/dashboard.html` — grouped list, sort/filter, HTMX
- [x] 3.4 Create `partials/status_badge.html` + `exercise_card.html`
- [x] 3.5 GREEN: Pass RED tests

## Phase 4: Detail & Config (PR C)

- [x] 4.1 RED: `tests/test_web_exercises.py` — detail, 404, config PUT (valid/invalid)
- [x] 4.2 Create `routers/exercises.py` — `GET/PUT /exercises/{id}` + validation
- [x] 4.3 Create `templates/exercise_detail.html` — history + config + back link
- [x] 4.4 Create `partials/config_form.html` — HTMX inline editor
- [x] 4.5 GREEN: Pass RED tests
- [x] 4.6 Update `app.py` — register exercises router
- [x] 4.7 Update `app.css` — detail page styles, form styles, history table

## Phase 5: Multi-User (PR D)

- [x] 5.1 RED: `tests/test_multi_user.py` — registration isolation, data separation
- [x] 5.2 Add `POST /register` in `routers/auth.py` + `register.html`
- [x] 5.3 Create `scripts/cron-sync-all.py` — iterate users, ingest per user
- [x] 5.4 Create `scripts/migrate-to-multi-user.py` — legacy DB → `/data/user_1/`
- [x] 5.5 GREEN: Pass RED tests (18/18)
- [x] 5.6 Update `SCHEDULING.md` — multi-user cron setup docs
