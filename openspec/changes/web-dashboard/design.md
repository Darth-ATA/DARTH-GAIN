# Design: Web Dashboard for DARTH-GAIN

## Technical Approach

FastAPI app in `src/darth_gain/web/` reuses existing `ProgressionEngine` and `db/` CRUD directly — no duplication. Per-user SQLite files at `/data/user_{id}/workouts.db` with zero schema changes. Shared `users.db` for auth (bcrypt). Sessions via signed `itsdangerous` cookies. Server-rendered Jinja2 templates with HTMX for inline edits. 4 stacked PRs (A–D) for reviewability.

## Architecture Decisions

### Decision: Connection Strategy

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Connection pool | sqlite3 doesn't benefit; concurrent writes still serialize | ❌ |
| Per-request connection | Opens/closes per request; WAL mitigates read contention | ✅ |
| Singleton connection | Stateful across requests — unsafe with async | ❌ |

Per-request via `Depends`: `get_db()` reads session `user_id`, resolves `/data/user_{id}/workouts.db`, opens connection, sets WAL + foreign_keys, yields, closes in cleanup.

### Decision: Auth Model

| Option | Tradeoff | Decision |
|--------|----------|----------|
| JWT | Stateless but overkill for homelab, needs refresh logic | ❌ |
| Signed cookie (itsdangerous) | Simple, no DB round-trip per request, can't tamper | ✅ |
| Session DB table | Requires lookup per request, no benefit over signed cookie | ❌ |

Session payload: `{"user_id": int, "username": str}`. Signed with `URLSafeTimedSerializer`, max_age=7 days. HttpOnly + Secure + SameSite=Lax.

### Decision: Password Hashing

| Option | Tradeoff | Decision |
|--------|----------|----------|
| bcrypt directly | Works, but more boilerplate | ❌ |
| werkzeug.security | Same bcrypt under the hood, simpler API (`generate_password_hash`/`check_password_hash`) | ✅ |
| passlib | Deprecated/unmaintained | ❌ |

### Decision: Static Assets

Single `app.css` served via `StaticFiles` at `/static/`. No build step, no framework. HTMX loaded from CDN (or vendored).

### Decision: WAL Mode

Set `PRAGMA journal_mode=WAL` on every new connection. Mitigates read-vs-write contention when cron ingest runs concurrently with web reads. OS-level advisory lock via `PRAGMA locking_mode=NORMAL`.

## Module Layout

```
src/darth_gain/web/
├── __init__.py
├── app.py               # FastAPI app factory, lifespan, middleware stack
├── auth.py              # Session encode/decode, login/logout helpers
├── deps.py              # FastAPI Depends: get_current_user, get_db
├── routers/
│   ├── __init__.py
│   ├── auth.py          # POST /login, /logout, /register, GET /health
│   ├── dashboard.py     # GET /
│   └── exercises.py     # GET /exercises/{id}, PUT /exercises/{id}/config
├── templates/
│   ├── base.html        # Base skeleton, nav, CSS/HTMX includes
│   ├── login.html       # Login + register form
│   ├── dashboard.html   # Grouped exercise list with status badges
│   ├── exercise_detail.html  # History table + config editor
│   └── partials/
│       ├── exercise_card.html   # Single exercise row/card fragment
│       ├── status_badge.html    # Colored status pill
│       └── config_form.html     # Inline config editor snippet
└── static/
    └── app.css           # Minimal styling (responsive, dark-friendly)
```

## Data Flow

```
Browser ──HTMX──→ FastAPI ──middleware──→ Router ──Depends──→ Handler
                    │                        │                  │
                    │                   get_current_user    get_db(user_id)
                    │                        │                  │
                    │                   session cookie     /data/user_7/
                    │                        │             workouts.db
                    │                        ↓                  ↓
                    │                   ProgressionEngine.check()
                    │                        │
                    └── Jinja2 template ←─── status + history
```

### Dashboard Flow (GET /)

```
get_db() → query exercise_templates → for each id:
    ProgressionEngine.check(template_id) → ProgressionStatus
group by status (progress/maintain/skipped/insufficient_data)
→ render dashboard.html
```

### Config Edit Flow (PUT /exercises/{id}/config)

```
HTMX hx-put → validate (rep_min ≤ rep_max, increment > 0) →
update progression_config table → return config_form.html snippet
→ HTMX swaps in-place
```

## File Changes

### PR A — Foundation + Auth + Docker

| File | Action | Description |
|------|--------|-------------|
| `src/darth_gain/web/__init__.py` | Create | Package |
| `src/darth_gain/web/app.py` | Create | FastAPI factory, lifespan (init users.db, shutdown), middleware, static mount |
| `src/darth_gain/web/auth.py` | Create | Session sign/verify with `itsdangerous`, login/logout helpers |
| `src/darth_gain/web/deps.py` | Create | `get_current_user`, `get_db` (per-user path resolution, WAL) |
| `src/darth_gain/web/routers/__init__.py` | Create | Package |
| `src/darth_gain/web/routers/auth.py` | Create | `GET /login`, `POST /login`, `POST /logout`, `POST /register`, `GET /health` |
| `src/darth_gain/web/templates/base.html` | Create | Base Jinja2 layout |
| `src/darth_gain/web/templates/login.html` | Create | Login/register form |
| `src/darth_gain/web/static/app.css` | Create | Minimal responsive CSS |
| `pyproject.toml` | Modify | Add `[project.optional-dependencies] web` (FastAPI, uvicorn, Jinja2, itsdangerous, python-multipart, werkzeug) |
| `Dockerfile` | Create | Multi-stage: deps install, runtime with `uvicorn` |
| `docker-compose.yml` | Create | Web service, `/data/` volume, env vars |
| `tests/test_web_auth.py` | Create | Auth route tests |

### PR B — Dashboard

| File | Action | Description |
|------|--------|-------------|
| `src/darth_gain/web/routers/dashboard.py` | Create | `GET /` — query templates, run ProgressionEngine.check() each, group, render |
| `src/darth_gain/web/templates/dashboard.html` | Create | Grouped exercise list with status badges |
| `src/darth_gain/web/templates/partials/status_badge.html` | Create | Color-coded status pill |
| `src/darth_gain/web/templates/partials/exercise_card.html` | Create | Single exercise row (HTMX refresh target) |
| `tests/test_web_dashboard.py` | Create | Dashboard route tests |

### PR C — Exercise Detail

| File | Action | Description |
|------|--------|-------------|
| `src/darth_gain/web/routers/exercises.py` | Create | `GET /exercises/{id}`, `PUT /exercises/{id}/config` |
| `src/darth_gain/web/templates/exercise_detail.html` | Create | History table + config form |
| `src/darth_gain/web/templates/partials/config_form.html` | Create | Inline editor snippet |
| `tests/test_web_exercises.py` | Create | Exercise route tests |

### PR D — Multi-User + Cron + Migration

| File | Action | Description |
|------|--------|-------------|
| `src/darth_gain/db/engine.py` | Modify | Add `PRAGMA journal_mode=WAL` to `create_engine()` |
| `scripts/cron-sync-all.py` | Create | Iterate `users.db` → run `ingest` per user |
| `scripts/migrate-to-multi-user.py` | Create | Copy `~/.local/share/darth-gain/workouts.db` → `/data/user_1/` |
| `tests/test_multi_user.py` | Create | Registration + DB isolation tests |

## Interfaces / Contracts

### users.db Schema (new)

```sql
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    hevy_api_key  TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### Session Cookie

```
Cookie: dg_session=<URLSafeTimedSerializer.sign({"user_id": 1, "username": "alice"})>
```

### get_db Dependency

```python
async def get_db(
    current_user: dict = Depends(get_current_user),
) -> Generator[sqlite3.Connection, None, None]:
    db_path = f"/data/user_{current_user['user_id']}/workouts.db"
    conn = create_engine(db_path)  # sets WAL + foreign_keys
    try:
        yield conn
    finally:
        conn.close()
```

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit — auth | Login/logout/register flows, session sign/verify, password hashing | `TestClient` + in-memory `:memory:` for users.db |
| Unit — dashboard | Template rendering, exercise grouping, empty/error states | `TestClient` + in-memory DB with seeded exercise_templates |
| Unit — exercises | Detail page, config PUT validation, HTMX response | `TestClient` + in-memory DB |
| Integration | Registration → login → dashboard → exercise detail → config edit | Full flow through `TestClient` with seeded data |
| Integration | WAL + concurrent reads | Two simultaneous `TestClient` requests during cron ingest |

**Strict TDD per `openspec/config.yaml`**: write test before handler for every route.

## Threat Matrix

N/A — no routing (network-level), shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundaries. FastAPI HTTP routing is application-level, not infrastructure routing.

## Migration / Rollout

1. PR A deployed first: Docker + auth work in isolation.
2. PR B + C shipped with feature parity to CLI — no user data affected.
3. PR D migration: one-time `scripts/migrate-to-multi-user.py` copies existing DB to `/data/user_1/`. CLI still works unchanged (its Config → `platformdirs` path untouched).
4. Cron: install `scripts/cron-sync-all.py` in existing crontab, replacing `darth-gain ingest`.

## Open Questions

- [ ] Should `hevy_api_key` be per-user or global env var? Spec says per-user in `users.db` — confirms the column exists but cron's env var approach needs a bridge (key in `users.db`, cron reads it to call ingest per user).
- [ ] Static files: vendor HTMX or CDN? CDN is simpler for homelab with internet; vendor for air-gapped. Decision: **CDN with SRI hash** (simpler, matches homelab assumption).
- [ ] CSS framework? Proposal says "minimal" — single `app.css` with utility classes. No Tailwind/Bootstrap to keep deps minimal. Confirm during implementation.
