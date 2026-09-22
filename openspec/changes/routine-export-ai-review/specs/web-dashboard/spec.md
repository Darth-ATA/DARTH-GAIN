# Delta for Web Dashboard

## ADDED Requirements

### Requirement: REQ-WD-001 — Register export router in FastAPI app

The system MUST register the new `export` router under the `/api/v1` prefix in the FastAPI application factory.
(Previously: only auth, dashboard, exercises, and routines routers were registered)

#### Scenario: Export router accessible at /api/v1/routines/{id}/export

- GIVEN the FastAPI app is created via `create_app()`
- WHEN the app starts
- THEN the `export.router` is included with prefix `/api/v1`
- AND `GET /api/v1/routines/R1/export?weeks=8` routes to the export handler
- AND the router is registered after the existing routers (order doesn't matter for non-overlapping paths)

### Requirement: REQ-WD-002 — Export router module exists

The system MUST provide a `web/routers/export.py` module containing the export endpoint handler with proper dependencies, Pydantic response models, and error handling.

#### Scenario: Export router module structure

- GIVEN the `web/routers/export.py` file exists
- WHEN the module is imported
- THEN it defines an `APIRouter` instance named `router`
- AND it defines Pydantic response models (`RoutineExportResponse`, `RoutineMeta`, `ExportWindow`, `WorkoutExport`, `ExerciseExport`, `SetExport`, `ExportSummary`, `ExerciseSummary`)
- AND it defines a `GET /routines/{routine_id}/export` handler
- AND the handler uses `Depends(get_db)` for per-user database connection
- AND the handler uses `Depends(require_user)` for authentication
- AND the handler validates `weeks` query parameter (4-24, default 8)
- AND the handler returns `RoutineExportResponse` on success
- AND the handler raises `HTTPException(404)` for routine not found
- AND the handler raises `HTTPException(422)` for invalid weeks (handled by Pydantic)

## MODIFIED Requirements

### Requirement: FastAPI app with lifecycle management

The system SHALL provide a FastAPI application that initializes on startup (creates connection pool, sets WAL mode) and cleans up on shutdown. The app SHALL serve under a configurable host/port with uvicorn. **The app SHALL include the export router under `/api/v1` prefix.**
(Previously: did not include export router)

#### Scenario: Export router registered in create_app

- GIVEN `create_app()` is called
- WHEN the app instance is created
- THEN `app.include_router(export.router, prefix="/api/v1")` is called
- AND the export endpoints are available at `/api/v1/routines/{routine_id}/export`

## REMOVED Requirements

None.

## RENAMED Requirements

None.

## Acceptance Criteria Mapping

| Proposal AC | Requirement(s) |
|-------------|----------------|
| Register new router in `web/app.py` | REQ-WD-001, REQ-WD-002 |

## Open Questions

1. **Router import path**: The proposal says "New `export.py` router module in `web/routers/`". The current `web/app.py` imports routers from `darth_gain.web.routers import auth, dashboard, exercises, routines`. Should the export router be imported the same way (`from darth_gain.web.routers import export`) or from a separate import?

2. **Prefix consistency**: The proposal specifies `/api/v1/routines/{id}/export`. The existing routers don't use a prefix (they're mounted at root: `/login`, `/`, `/exercises`, `/routines`). Is `/api/v1` a new convention for JSON APIs, and should future JSON endpoints follow this pattern?

3. **OpenAPI documentation**: Should the export endpoint appear in the auto-generated OpenAPI docs (`/docs`, `/redoc`)? Currently the HTML routes don't need OpenAPI docs since they return HTML. The JSON API would benefit from it.

4. **CORS**: If the export API is consumed by external AI tools or browser extensions, should CORS headers be configured? Currently the app doesn't appear to have CORS middleware.