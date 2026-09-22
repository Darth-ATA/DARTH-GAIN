# Proposal: Routine Export for AI Performance Review

## Intent

Users want to export their recent routine workout data in a structured format that can be fed to an AI agent for performance analysis and routine improvement suggestions. Currently, the web UI shows routine-grouped progression status (via `/routines`), but there's no way to extract the underlying workout history (sets, reps, weights, RPE) for a given routine over a configurable time window. This proposal adds a JSON API endpoint that returns the last X weeks of workout data for a specific routine, optimized for AI consumption.

**Scientific basis**: Research shows mesocycles average 4±2 weeks, periodization analysis requires ≥8 weeks, and AI coaching platforms typically use 6–12 weeks of history. Default is set to 8 weeks (2 mesocycles) with configurable range 4–24 weeks.

## Scope

### In Scope
- New JSON API router: `GET /api/v1/routines/{routine_id}/export?weeks=8`
- Configurable `weeks` query parameter (4–24, default 8)
- Response includes: routine metadata, workout sessions with full set-level data (weight, reps, RPE, timestamp), exercise aggregation stats
- Per-user database isolation (respects existing auth context)
- New `export.py` router module in `web/routers/`
- Extended `db/repo.py` with `get_routine_workouts_for_export(conn, routine_id, since_date)` 
- Button in `routines.html` template to trigger export (downloads JSON file)
- Register new router in `web/app.py`

### Out of Scope
- Authentication/authorization changes (uses existing session auth)
- PDF/CSV export formats (JSON only for AI consumption)
- Historical data backfill or migration
- AI agent integration or prompt engineering
- Real-time streaming or WebSocket updates
- Multi-routine comparison in single export
- Workout editing or modification via API

## Capabilities

### New Capabilities
- `routine-export`: JSON API endpoint for exporting routine workout history with configurable time window, returning structured data optimized for AI analysis

### Modified Capabilities
- `routine-view`: Adds export button to the routine view template (UI affordance only, no requirement changes)
- `web-dashboard`: Registers new API router in app factory (infrastructure wiring only)

## Approach

**Recommended approach (from exploration)**: Create a new dedicated JSON API router under `/api/v1/` namespace, separate from existing HTML routes. This avoids coupling with Jinja2 templates and HTMX patterns used by the dashboard.

**Implementation steps**:
1. Add `get_routine_workouts_for_export()` to `db/repo.py` — queries workouts joined with sets, filtered by `routine_id` and date window
2. Create `web/routers/export.py` with `GET /api/v1/routines/{routine_id}/export` handler
3. Register router in `web/app.py` with `/api/v1` prefix
4. Add "Export for AI Review" button in `routines.html` that calls the endpoint and triggers JSON download
5. Input validation: `weeks` query param clamped to [4, 24], default 8

**Alternatives considered**:
- Extend existing `/routines` HTML route with `?format=json` — rejected (mixes concerns, breaks HTMX expectations)
- Add export to `web-dashboard` router — rejected (dashboard is muscle-group oriented, not routine-oriented)
- GraphQL endpoint — rejected (overkill for single-purpose export, adds dependencies)

**JSON response structure**:
```json
{
  "routine": { "id": "string", "title": "string", "folder_id": "string|null" },
  "window": { "weeks": 8, "from": "ISO8601", "to": "ISO8601" },
  "workouts": [
    {
      "id": "string",
      "start_time": "ISO8601",
      "end_time": "ISO8601|null",
      "exercises": [
        {
          "template_id": "string",
          "name": "string",
          "sets": [
            { "weight_kg": 100.0, "reps": 8, "rpe": 8.5, "order": 1 }
          ]
        }
      ]
    }
  ],
  "summary": {
    "total_workouts": 16,
    "total_sets": 128,
    "exercises": [
      { "template_id": "string", "name": "string", "total_sets": 32, "avg_weight_kg": 95.2, "max_weight_kg": 105.0 }
    ]
  }
}
```

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `web/routers/export.py` | New | New router module with export endpoint |
| `db/repo.py` | Modified | Add `get_routine_workouts_for_export()` function |
| `web/app.py` | Modified | Register new router with `/api/v1` prefix |
| `templates/routines.html` | Modified | Add export button with HTMX-triggered download |
| `templates/base.html` | None | No changes needed (existing auth covers API) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| No existing JSON API in codebase — new patterns needed | Medium | Follow FastAPI best practices; add Pydantic response models; write contract tests first |
| Large payloads for users with high volume (50+ workouts × 20+ sets) | Medium | Add `weeks` cap at 24; consider pagination in future if needed; stream response if >1MB |
| Optional RPE field may be null for many sets | Low | Include `rpe: null` in JSON; AI agents handle missing data gracefully |
| Routine adherence variance (skipped workouts, partial weeks) | Low | Export raw data; let AI interpret adherence; include `window` metadata for context |
| Per-user DB isolation not respected in new query | Low | Use existing `get_db_connection(request)` pattern; all repo functions take `conn` from request context |
| Breaking changes to `db/repo.py` affecting sync/ingest | Low | New function only; no modifications to existing upsert/query functions |

## Rollback Plan

1. Remove `web/routers/export.py` file
2. Remove router registration from `web/app.py`
3. Remove `get_routine_workouts_for_export()` from `db/repo.py`
4. Remove export button from `templates/routines.html`
5. No database migrations needed (read-only query)

Rollback is a simple file deletion + router deregistration — no data loss possible.

## Dependencies

- Existing `routine-view` capability (provides `routine_id` context and template)
- Existing `web-auth` capability (provides per-user DB isolation via session)
- Existing `db/repo.py` workout/set query patterns
- FastAPI + Pydantic (already in project dependencies)

## Success Criteria

- [ ] `GET /api/v1/routines/{id}/export?weeks=8` returns 200 with valid JSON matching specified schema
- [ ] Response includes all workouts for that routine within the 8-week window
- [ ] Each workout includes full set-level data (weight, reps, RPE, order)
- [ ] Summary section aggregates total workouts, sets, and per-exercise stats
- [ ] `weeks` parameter accepts 4–24, defaults to 8, rejects out-of-range with 422
- [ ] Export button in `routines.html` triggers download of JSON file with filename `routine-{title}-{weeks}w-{date}.json`
- [ ] Per-user isolation verified: User A cannot export User B's routine data
- [ ] Response time < 500ms for typical dataset (≤20 workouts, ≤500 sets)
- [ ] Contract tests cover: happy path, empty routine, invalid routine_id, invalid weeks, auth required