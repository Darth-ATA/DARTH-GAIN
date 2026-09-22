# Routine Export Specification

## Purpose

JSON API endpoint for exporting routine workout history with a configurable time window (4–24 weeks, default 8). Returns structured data optimized for AI consumption — including routine metadata, full workout sessions with set-level detail (weight, reps, RPE, order), and aggregated summary statistics (volume by muscle, frequency, progression trends, deload detection).

## Data Contracts

### Request

```python
class ExportRequest(BaseModel):
    weeks: int = Field(default=8, ge=4, le=24, description="Number of weeks of history to include (4-24)")
```

**Endpoint**: `GET /api/v1/routines/{routine_id}/export`
**Query Parameter**: `weeks` (integer, 4–24, default 8)

### Response — RoutineExportResponse

```python
class RoutineExportResponse(BaseModel):
    routine: RoutineMeta
    window: ExportWindow
    workouts: list[WorkoutExport]
    summary: ExportSummary
```

### Response — RoutineMeta

```python
class RoutineMeta(BaseModel):
    id: str
    title: str
    folder_id: str | None
```

### Response — ExportWindow

```python
class ExportWindow(BaseModel):
    weeks: int
    from_: datetime = Field(alias="from")
    to: datetime
```

### Response — WorkoutExport

```python
class WorkoutExport(BaseModel):
    id: str
    start_time: datetime
    end_time: datetime | None
    exercises: list[ExerciseExport]
```

### Response — ExerciseExport

```python
class ExerciseExport(BaseModel):
    template_id: str
    name: str
    sets: list[SetExport]
```

### Response — SetExport

```python
class SetExport(BaseModel):
    weight_kg: float
    reps: int
    rpe: float | None
    order: int
```

### Response — ExportSummary

```python
class ExportSummary(BaseModel):
    total_workouts: int
    total_sets: int
    exercises: list[ExerciseSummary]
```

### Response — ExerciseSummary

```python
class ExerciseSummary(BaseModel):
    template_id: str
    name: str
    total_sets: int
    avg_weight_kg: float
    max_weight_kg: float
```

## Requirements

### Requirement: REQ-001 — Export endpoint exists at correct path

The system MUST expose a `GET /api/v1/routines/{routine_id}/export` endpoint that returns JSON matching the `RoutineExportResponse` schema.

#### Scenario: Happy path — routine with workouts in window

- GIVEN an authenticated user with routine "R1" ("Push Day") and 3 workouts in the last 8 weeks
- WHEN the user requests `GET /api/v1/routines/R1/export?weeks=8`
- THEN the response is 200 OK
- AND the response body matches `RoutineExportResponse` schema
- AND `routine.id` equals "R1"
- AND `routine.title` equals "Push Day"
- AND `window.weeks` equals 8
- AND `window.from` is 8 weeks before `window.to`
- AND `workouts` contains exactly 3 workout entries
- AND each workout includes `exercises` with `sets` containing `weight_kg`, `reps`, `rpe`, `order`
- AND `summary.total_workouts` equals 3
- AND `summary.total_sets` equals sum of all sets across the 3 workouts

#### Scenario: Routine exists but has no workouts in window

- GIVEN an authenticated user with routine "R2" ("Pull Day") but zero workouts in the last 8 weeks
- WHEN the user requests `GET /api/v1/routines/R2/export?weeks=8`
- THEN the response is 200 OK
- AND `workouts` is an empty list
- AND `summary.total_workouts` equals 0
- AND `summary.total_sets` equals 0
- AND `summary.exercises` is an empty list

#### Scenario: Routine has workouts with partial data (missing RPE)

- GIVEN a workout with sets where some have `rpe: null` (user didn't log RPE)
- WHEN the export is requested
- THEN the response includes those sets with `rpe: null`
- AND the AI consumer can handle missing RPE gracefully

### Requirement: REQ-002 — Weeks parameter validation

The system MUST accept a `weeks` query parameter constrained to integer range [4, 24] with default 8, and reject out-of-range values with 422 Unprocessable Entity.

#### Scenario: Default weeks (8) when parameter omitted

- GIVEN an authenticated user with routine "R1" and workouts
- WHEN the user requests `GET /api/v1/routines/R1/export` (no weeks param)
- THEN the response uses `weeks=8` in the window
- AND `window.weeks` equals 8

#### Scenario: Valid weeks=4 (minimum)

- GIVEN an authenticated user with routine "R1"
- WHEN the user requests `GET /api/v1/routines/R1/export?weeks=4`
- THEN the response is 200 OK
- AND `window.weeks` equals 4

#### Scenario: Valid weeks=24 (maximum)

- GIVEN an authenticated user with routine "R1"
- WHEN the user requests `GET /api/v1/routines/R1/export?weeks=24`
- THEN the response is 200 OK
- AND `window.weeks` equals 24

#### Scenario: weeks=3 rejected (below minimum)

- GIVEN an authenticated user with routine "R1"
- WHEN the user requests `GET /api/v1/routines/R1/export?weeks=3`
- THEN the response is 422 Unprocessable Entity
- AND the error response indicates `weeks` must be >= 4

#### Scenario: weeks=25 rejected (above maximum)

- GIVEN an authenticated user with routine "R1"
- WHEN the user requests `GET /api/v1/routines/R1/export?weeks=25`
- THEN the response is 422 Unprocessable Entity
- AND the error response indicates `weeks` must be <= 24

#### Scenario: weeks=abc rejected (non-integer)

- GIVEN an authenticated user with routine "R1"
- WHEN the user requests `GET /api/v1/routines/R1/export?weeks=abc`
- THEN the response is 422 Unprocessable Entity
- AND the error response indicates `weeks` must be an integer

### Requirement: REQ-003 — Routine not found returns 404

The system MUST return 404 Not Found when the requested `routine_id` does not exist in the user's database.

#### Scenario: Non-existent routine_id

- GIVEN an authenticated user with routines "R1" and "R2"
- WHEN the user requests `GET /api/v1/routines/NOTEXIST/export?weeks=8`
- THEN the response is 404 Not Found
- AND the error response indicates routine not found

#### Scenario: Routine exists but belongs to another user

- GIVEN user A has routine "R1" and user B has routine "R2"
- WHEN user A requests `GET /api/v1/routines/R2/export?weeks=8`
- THEN the response is 404 Not Found (not 403 — routine appears non-existent to user A)

### Requirement: REQ-004 — Authentication required

The system MUST require valid authentication; unauthenticated requests return 401 Unauthorized (or redirect to login per existing auth middleware).

#### Scenario: No session cookie

- GIVEN no session cookie is present
- WHEN a client sends `GET /api/v1/routines/R1/export?weeks=8`
- THEN the response is 401 Unauthorized (or 302 redirect to /login per auth middleware)

#### Scenario: Expired session cookie

- GIVEN a session cookie past its expiry
- WHEN a client sends `GET /api/v1/routines/R1/export?weeks=8` with the expired cookie
- THEN the response is 401 Unauthorized (or 302 redirect to /login)

### Requirement: REQ-005 — Per-user database isolation

The system MUST scope all queries to the authenticated user's per-user database (`/data/user_{id}/workouts.db`), preventing cross-user data access.

#### Scenario: User A cannot see User B's routine data

- GIVEN user A (id=1) has routine "R1" with 5 workouts
- AND user B (id=2) has routine "R2" with 10 workouts
- WHEN user A requests `GET /api/v1/routines/R1/export?weeks=8`
- THEN the response contains only user A's data (5 workouts)
- WHEN user B requests `GET /api/v1/routines/R2/export?weeks=8`
- THEN the response contains only user B's data (10 workouts)
- AND user A never receives user B's workout data

### Requirement: REQ-006 — Response includes complete set-level data

The system MUST include every set for every exercise in every workout within the time window, with all available fields: `weight_kg`, `reps`, `rpe` (nullable), `order`.

#### Scenario: All set fields present

- GIVEN a workout with exercise "Bench Press" and 3 sets: (100kg, 8, RPE 8.5), (100kg, 6, RPE 9), (102.5kg, 5, RPE 9.5)
- WHEN the export is requested
- THEN the response includes 3 `SetExport` entries for that exercise
- AND each has `weight_kg`, `reps`, `rpe`, `order` populated correctly

#### Scenario: Sets with missing optional fields

- GIVEN a set with only `weight_kg` and `reps` (no RPE, no distance/duration)
- WHEN the export is requested
- THEN the set entry includes `weight_kg`, `reps`, `rpe: null`, `order`
- AND no fields are omitted from the response

### Requirement: REQ-007 — Summary aggregates correctly

The system MUST compute `summary` section correctly: `total_workouts`, `total_sets`, and per-exercise `total_sets`, `avg_weight_kg`, `max_weight_kg`.

#### Scenario: Summary matches workout data

- GIVEN 2 workouts for routine "R1":
  - Workout 1: "Bench Press" 3 sets (100, 102.5, 100), "Row" 3 sets (80, 80, 82.5)
  - Workout 2: "Bench Press" 3 sets (105, 105, 107.5), "Row" 3 sets (82.5, 85, 85)
- WHEN the export is requested with weeks covering both workouts
- THEN `summary.total_workouts` equals 2
- AND `summary.total_sets` equals 12
- AND `summary.exercises` contains 2 entries:
  - "Bench Press": `total_sets=6`, `avg_weight_kg≈103.33`, `max_weight_kg=107.5`
  - "Row": `total_sets=6`, `avg_weight_kg≈82.5`, `max_weight_kg=85`

### Requirement: REQ-008 — Window metadata accuracy

The system MUST include accurate `window.from` and `window.to` timestamps in ISO 8601 format, where `to` is the latest workout start_time in the window (or now if no workouts), and `from` is `to - weeks * 7 days`.

#### Scenario: Window bounds match requested weeks

- GIVEN workouts on 2026-08-01 and 2026-08-15 for routine "R1"
- WHEN requesting `GET /api/v1/routines/R1/export?weeks=4` on 2026-08-20
- THEN `window.to` is 2026-08-15T... (latest workout)
- AND `window.from` is 2026-07-18T... (4 weeks before latest workout)
- AND `window.weeks` equals 4

#### Scenario: No workouts — window.to is request time

- GIVEN routine "R1" has zero workouts
- WHEN requesting export on 2026-08-20T14:30:00Z
- THEN `window.to` is approximately 2026-08-20T14:30:00Z
- AND `window.from` is 4/8/24 weeks before that

### Requirement: REQ-009 — Performance target

The system SHOULD respond within 500ms for typical datasets (≤20 workouts, ≤500 sets) and SHOULD handle larger payloads (≤1000 sets) within 2 seconds.

#### Scenario: Typical dataset performance

- GIVEN a routine with 15 workouts and 400 total sets in the window
- WHEN the export endpoint is called
- THEN the response completes within 500ms

#### Scenario: Large dataset performance

- GIVEN a routine with 30 workouts and 900 total sets in the window
- WHEN the export endpoint is called
- THEN the response completes within 2 seconds

### Requirement: REQ-010 — Error handling for server failures

The system MUST return 500 Internal Server Error with a generic error message for unexpected database or server errors, without exposing internal details.

#### Scenario: Database corruption

- GIVEN the user's per-user database is corrupted
- WHEN the export endpoint is called
- THEN the response is 500 Internal Server Error
- AND the error response contains a generic message (not SQL stack trace)

## Acceptance Criteria Mapping

| Proposal AC | Requirement(s) |
|-------------|----------------|
| GET /api/v1/routines/{id}/export?weeks=8 returns 200 with valid JSON matching schema | REQ-001, REQ-006, REQ-007 |
| Response includes all workouts for that routine within the 8-week window | REQ-001, REQ-008 |
| Each workout includes full set-level data (weight, reps, RPE, order) | REQ-006 |
| Summary section aggregates total workouts, sets, and per-exercise stats | REQ-007 |
| `weeks` parameter accepts 4–24, defaults to 8, rejects out-of-range with 422 | REQ-002 |
| Export button in routines.html triggers download of JSON file with filename `routine-{title}-{weeks}w-{date}.json` | (Covered in routine-view delta spec) |
| Per-user isolation verified: User A cannot export User B's routine data | REQ-005 |
| Response time < 500ms for typical dataset (≤20 workouts, ≤500 sets) | REQ-009 |
| Contract tests cover: happy path, empty routine, invalid routine_id, invalid weeks, auth required | REQ-001, REQ-002, REQ-003, REQ-004 |

## Open Questions

1. **Pagination/streaming for >24 weeks or >1000 sets**: The proposal mentions considering pagination for large payloads. Should the spec define a `page`/`cursor` parameter now, or leave for future iteration? Current cap at 24 weeks should limit size, but high-frequency users could exceed 1000 sets.

2. **RPE null handling in summary**: `avg_weight_kg` and `max_weight_kg` currently ignore RPE. Should the summary include RPE statistics (avg/max RPE per exercise) for AI analysis?

3. **Deload detection in summary**: The proposal mentions "deload detection" in summary. Should `ExportSummary` include a `deload_weeks: list[int]` or similar field identifying weeks where volume dropped >20%?

4. **Progression trends in summary**: Should `ExerciseSummary` include trend indicators (e.g., `weight_trend: "increasing" | "stable" | "decreasing"` over the window) for AI coaching?

5. **Timezone handling**: `window.from`/`window.to` are ISO 8601 with timezone. Should the spec mandate UTC (Z suffix) or allow local time with offset?

6. **Filename format**: The proposal specifies `routine-{title}-{weeks}w-{date}.json`. Should `{date}` be the request date, the window `to` date, or the latest workout date? What format (YYYY-MM-DD)?

7. **Rate limiting**: Should the export endpoint have rate limiting (e.g., max 10 exports/hour per user) to prevent abuse?

8. **Caching**: Should the response be cacheable (ETag/Last-Modified) for repeated requests with same parameters?