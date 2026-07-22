# Routine View Specification

## Purpose

Group exercises by Hevy routine on the web dashboard so users can see which movements need weight progression within each training plan, including exercises done without a routine.

## Requirements

### Requirement: Schema — routines table

The system MUST store a `routines` table with columns `id TEXT PRIMARY KEY`, `title TEXT NOT NULL`, `folder_id TEXT`, `created_at TEXT`, and `updated_at TEXT`. The `workouts` table MUST have a nullable `routine_id TEXT` column with no foreign key constraint.

#### Scenario: Table creation is idempotent

- GIVEN an empty database
- WHEN `create_tables` is called
- THEN the `routines` table exists with the defined columns
- AND `workouts` has a nullable `routine_id` column

#### Scenario: No FK constraint allows orphaned IDs

- GIVEN a workout with `routine_id` referencing a non-existent routine
- WHEN the workout is upserted
- THEN the operation succeeds without integrity error

### Requirement: Adapter — routine_id extraction

The adapter functions `_raw_workout_to_dict` and `_workout_to_dict` MUST extract the optional `routine_id` field from Hevy API/SDK responses.

#### Scenario: Routine ID present in workout

- GIVEN a Hevy workout dict with `routine_id: "ABC123"`
- WHEN `_raw_workout_to_dict` converts it
- THEN the output dict includes `routine_id: "ABC123"`

#### Scenario: Routine ID absent

- GIVEN a Hevy workout dict without `routine_id`
- WHEN `_raw_workout_to_dict` converts it
- THEN the output dict includes `routine_id` as null

### Requirement: HevyClient — get_routines method

`HevyClient` MUST expose a `get_routines()` method that paginates the `routines.get_routines()` SDK endpoint and returns domain dicts with keys `id`, `title`, `folder_id`, `created_at`, `updated_at`.

#### Scenario: Fetch all routines across pages

- GIVEN a Hevy account with 3 routines across 2 pages
- WHEN `client.get_routines()` is called
- THEN all 3 routines are returned as domain dicts

#### Scenario: No routines

- GIVEN a Hevy account with zero routines
- WHEN `client.get_routines()` is called
- THEN an empty list is returned

### Requirement: RoutineRepo — upsert and query

The repo layer MUST provide `upsert_routines(conn, routines)` using `INSERT OR REPLACE`, and `get_routines(conn)` returning all routines ordered by title.

#### Scenario: Upsert replaces existing

- GIVEN a routine with id "R1" title "Push" already stored
- WHEN `upsert_routines` is called with same id and title "Push v2"
- THEN the title is updated to "Push v2"

#### Scenario: Query returns all

- GIVEN 2 stored routines
- WHEN `get_routines` is called
- THEN both routines are returned sorted by title

### Requirement: Sync — fetch routines on every run

The sync pipeline MUST call `api.get_routines()` at the start of each sync run and persist them via `upsert_routines`. The `upsert_workout` call MUST pass `routine_id` through to the workouts table.

#### Scenario: Routines stored before event processing

- GIVEN a sync run starting
- WHEN `sync()` is called
- THEN routines are fetched and persisted before any workout events are processed

#### Scenario: Routine ID persisted on workout upsert

- GIVEN an updated event with `routine_id: "R1"` in the workout dict
- WHEN `sync()` processes the event
- THEN `workouts.routine_id` is "R1" after upsert

### Requirement: Router — GET /routines

The system MUST provide a `GET /routines` route that runs `ProgressionEngine.check()` per unique exercise template, groups results by routine name, and assigns exercises with `routine_id IS NULL` to an `"Uncategorized"` bucket.

#### Scenario: Exercises grouped by routine

- GIVEN 2 routines ("Push", "Pull") each with 2 distinct exercise templates
- WHEN `GET /routines` is called
- THEN the response contains groups "Push" and "Pull", each with their 2 exercises with progression status

#### Scenario: Uncategorized bucket for null routine_id

- GIVEN an exercise done outside any routine (`routine_id IS NULL`)
- WHEN `GET /routines` is called
- THEN that exercise appears under an "Uncategorized" group

#### Scenario: Empty database

- GIVEN no workouts in the database
- WHEN `GET /routines` is called
- THEN the page renders with empty state (no groups)

### Requirement: Template — routine_view.html

The template MUST display routine groups as headers with exercise cards inside each group, reusing `partials/exercise_card.html`. The `"Uncategorized"` section MUST appear last.

#### Scenario: Groups rendered with headers

- GIVEN a response with groups "Push" and "Pull"
- WHEN `routine_view.html` renders
- THEN each group has a header with the routine name and exercise count
- AND exercise cards are rendered inside each group

### Requirement: Nav link

The `base.html` template MUST show a "Routines" nav link when the user is authenticated.

#### Scenario: Nav link visible when logged in

- GIVEN an authenticated user on any page
- THEN the navbar includes an "Routines" link pointing to `/routines`

### Requirement: Tests

The test suite MUST cover: adapter `routine_id` extraction (present/absent), `get_routines` success and empty response, routine upsert and query, sync integration (routines fetched first, routine_id persisted), `GET /routines` with grouped and uncategorized results, and the nav link presence.

#### Scenario: Adapter tests

- GIVEN workout dicts with and without `routine_id`
- WHEN the adapter converts them
- THEN `routine_id` is correctly extracted or null

#### Scenario: Router response structure

- GIVEN seeded data with 2 routines and 1 uncategorized exercise
- WHEN `GET /routines` is called in tests
- THEN the response contains 3 groups total, including "Uncategorized"
