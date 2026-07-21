# Web Dashboard Specification

## Purpose

Main dashboard view for the DARTH-GAIN web UI. Displays all exercises with their latest progression status, grouped by muscle group. Provides sort/filter controls and a refresh action to re-check progression.

## Requirements

### Requirement: Dashboard lists all exercises with progression status

The system MUST render `GET /` as an HTML page (Jinja2 template) showing every exercise template that has workout history, each with its latest progression status from `progression_history`.

#### Scenario: Dashboard shows exercises with status badges

- GIVEN user has 5 exercises with progression history entries
- WHEN the user navigates to `/`
- THEN the page displays 5 exercise entries, each with title, current weight (or "—"), and a status badge (PROGRESS / MAINTAIN / SKIPPED / INSUFFICIENT_DATA)

#### Scenario: Dashboard renders without error when no history exists

- GIVEN the user has registered but has zero workout data
- WHEN the user navigates to `/`
- THEN the page renders an empty state message ("No exercise data yet — sync your Hevy account") without errors

### Requirement: Status badges use distinct visual styling

Each progression status SHALL have a distinct visual badge: PROGRESS (green), MAINTAIN (yellow/amber), SKIPPED (gray), INSUFFICIENT_DATA (blue/neutral). Badges SHALL be rendered server-side in the template.

#### Scenario: Each status renders correct badge

- GIVEN exercises with statuses "progress", "maintain", "skipped", "insufficient_data"
- WHEN the dashboard renders
- THEN each exercise shows the correct colored badge matching its status

### Requirement: Exercises grouped by muscle group

The system MUST group exercises by `primary_muscle_group` from `exercise_templates`, displaying group headers between sections.

#### Scenario: Muscle group headers visible

- GIVEN exercises in "Chest", "Back", and "Legs" muscle groups
- WHEN the dashboard renders
- THEN the page shows section headers "Chest", "Back", "Legs" with exercises listed under each

#### Scenario: Single exercise per group still shows header

- GIVEN only one exercise in "Chest" and none in others
- WHEN the dashboard renders
- THEN the "Chest" header is displayed above the single exercise

### Requirement: Empty state for no exercises

The system SHALL render a user-friendly empty state when the user's database has no exercise data — a centered message with a link to the Hevy sync instructions.

#### Scenario: Empty state displays guidance

- GIVEN the user has zero sets across all workouts
- WHEN the dashboard renders
- THEN the page shows "No exercises found" with guidance on syncing their Hevy account

### Requirement: Error state for database failures

The system SHALL handle database errors gracefully, rendering an error banner on the dashboard page rather than crashing.

#### Scenario: Corrupt database shows error message

- GIVEN the user's DB file is corrupted or unreadable
- WHEN the dashboard handler is invoked
- THEN the page renders an error banner saying "Unable to load exercise data" with a retry suggestion, and the server logs the error

### Requirement: Refresh button re-checks progression

The system MUST provide a "Refresh" button on the dashboard that triggers a progression check for all exercises. The refresh SHALL use HTMX to replace the exercise list content without a full page reload.

#### Scenario: Refresh triggers re-check for all exercises

- GIVEN the dashboard is displayed with status data from 2 hours ago
- WHEN the user clicks "Refresh"
- THEN an HTMX request triggers `ProgressionEngine.check()` for each exercise, and the list updates with fresh statuses

#### Scenario: Refresh shows loading indicator

- GIVEN the user clicks "Refresh"
- WHEN the HTMX request is in flight
- THEN the dashboard shows a loading spinner or "Checking progression..." indicator in the exercise list container

### Requirement: Sort/filter controls

The system SHALL provide sort options for the exercise list: by name (A-Z), by status (progressing first), or by last checked date (newest first). An optional text filter SHALL allow searching by exercise name.

#### Scenario: Sort by name reorders exercises

- GIVEN exercises "Z Press", "Bench Press", "Curl"
- WHEN the user selects "Sort by name"
- THEN the order becomes "Bench Press", "Curl", "Z Press"

#### Scenario: Filter by name shows matching subset

- GIVEN exercises "Bench Press", "Incline Press", "Barbell Row"
- WHEN the user types "Press" in the filter input
- THEN only "Bench Press" and "Incline Press" are shown

#### Scenario: Filter with no matches shows empty state

- GIVEN exercises "Bench Press" and "Curl"
- WHEN the user types "zzz" in the filter input
- THEN the list shows "No exercises match your filter"

### Requirement: Refresh computes all exercises at once

The system SHOULD run progression checks for all exercise templates in a single pass, iterating over all templates and persisting results to `progression_history`. This differs from the single-exercise CLI command.

#### Scenario: Bulk refresh processes every template

- GIVEN 10 exercise templates exist
- WHEN the bulk refresh runs
- THEN `ProgressionEngine.check()` is called for each of the 10 templates and results are persisted

## Edge Cases

- **Large datasets**: Dashboard SHOULD paginate or virtual-scroll if exercise list exceeds 50 entries
- **Concurrent refresh**: If a refresh is already in progress, a second click SHOULD be debounced or ignored
- **HTMX fallback**: If JavaScript is disabled, the refresh button SHOULD fall back to a full page reload via a standard form POST with redirect
- **Muscle group order**: Groups SHOULD be ordered alphabetically or by most recent activity, not arbitrarily
- **Filter + sort combination**: Filter and sort SHOULD compose — filtered results are sorted by the selected criterion
