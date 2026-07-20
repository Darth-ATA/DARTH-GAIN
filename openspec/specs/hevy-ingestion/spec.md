# Hevy Ingestion Specification

## Purpose

Ingest Hevy workout data into local SQLite storage via events-based delta sync. Establishes the foundation for all downstream analysis features.

## Requirements

### Requirement: CLI Command Structure

The system MUST expose a `darth-gain ingest` CLI command via Click with the following options:

- `--since` / `-s` (optional): ISO 8601 timestamp to sync from. Defaults to the last successful sync timestamp stored in SQLite.
- `--dry-run` / `-n` (flag): Fetch and display workout summaries without writing to the database.
- `--verbose` / `-v` (flag): Enable detailed logging output.
- `--db-path` (optional): Path to SQLite database. Defaults to `~/.darth-gain/workouts.db`.

#### Scenario: Command invocation with defaults

- GIVEN no CLI flags are provided
- WHEN the user runs `darth-gain ingest`
- THEN the system reads `HEVY_API_TOKEN` from the environment
- AND defaults `--since` to the stored `last_sync_at` value (or epoch if absent)
- AND defaults `--db-path` to `~/.darth-gain/workouts.db`

#### Scenario: API key not configured

- GIVEN `HEVY_API_TOKEN` is not set in the environment
- WHEN the user runs `darth-gain ingest`
- THEN the system SHALL exit with a non-zero code and a clear error message

#### Scenario: Unknown option passed

- GIVEN the user passes a non-existent flag
- WHEN the CLI parses arguments
- THEN Click SHALL display the error and usage help before exiting

### Requirement: Events-Based Delta Sync

The system MUST use the Hevy events endpoint (`GET /v1/workouts/events?since=`) as its sole sync mechanism. On each run:

1. Read `last_sync_at` from SQLite `_sync_metadata` table.
2. Call `get_events(since=last_sync_at)` starting from page 1.
3. Paginate through all pages (iterate while `page <= page_count`).
4. For each `UpdatedWorkout` event: upsert the full workout (workout + exercises + sets).
5. For each `DeletedWorkout` event: soft-delete the workout (`is_deleted = 1`).
6. On successful completion of all pages, update `last_sync_at` to the current UTC timestamp.

#### Scenario: Delta sync with no new events

- GIVEN the last sync was 1 hour ago and no workouts changed since
- WHEN `get_events` returns zero events across all pages
- THEN no workouts are upserted or deleted
- AND `last_sync_at` is updated to the current time

#### Scenario: Delta sync with mixed events

- GIVEN the last sync was yesterday and 3 workouts were updated and 1 was deleted since
- WHEN the sync processes all events
- THEN the 3 updated workouts are upserted in the database
- AND the deleted workout has `is_deleted = 1`
- AND `last_sync_at` is updated

#### Scenario: Event ordering (newest-first)

- GIVEN events are returned newest-first by the API
- WHEN the same workout appears in multiple event pages
- THEN the system MUST process all events to ensure the latest version is stored (proposal recommendation: process oldest-first or apply latest-wins)

### Requirement: First Sync (Full Fetch)

On first run (no `last_sync_at` in the database), the system MUST default `since` to the Unix epoch (`1970-01-01T00:00:00Z`), which triggers a full fetch of all workouts via the events endpoint.

#### Scenario: First sync with 500 workouts

- GIVEN the database is empty and the user has 500 workouts on Hevy
- WHEN the user runs `darth-gain ingest`
- THEN the system paginates through all pages (page size 10, ~50 API calls)
- AND shows a progress bar tracking page completion
- AND inserts all 500 workouts into SQLite
- AND sets `last_sync_at` to the current timestamp

#### Scenario: Interrupted first sync

- GIVEN the first sync is in progress and is interrupted mid-way (e.g., network loss)
- WHEN the user runs `darth-gain ingest` again
- THEN the system resumes by defaulting to epoch (re-fetches from the beginning)
- AND upsert idempotency ensures no duplicate rows

### Requirement: Database Write

The system MUST write workout data to SQLite with the following guarantees:

- Each workout is upserted atomically in a single transaction (workout + exercises + sets).
- Existing rows are replaced on `workout_id` conflict (UPSERT semantics).
- The `workouts` table has a `is_deleted` column (default 0) for soft deletes.
- The schema MUST match the exploration's proposed DDL with indexes on `start_time`, `updated_at`, and `workout_id`.

#### Scenario: Upsert replaces existing workout

- GIVEN a workout with ID `abc-123` already exists in the database
- WHEN an `UpdatedWorkout` event with a newer `updated_at` is processed
- THEN all rows for that workout (exercises, sets) are replaced atomically
- AND no orphaned exercise or set rows remain

#### Scenario: Database file does not exist

- GIVEN `--db-path` points to a non-existent path
- WHEN the sync starts
- THEN the system SHALL create the database file and run all DDL statements
- AND then proceed with the full sync

### Requirement: Dry Run Mode

When `--dry-run` is set, the system MUST fetch workout data from the API, display a summary for each workout (title, date, exercise count), and SHALL NOT write anything to the database.

#### Scenario: Dry run on first sync

- GIVEN the user runs `darth-gain ingest --dry-run` on an empty database
- WHEN the sync processes all API pages
- THEN each workout title and date is printed to stdout
- AND no rows are written to SQLite
- AND `last_sync_at` is NOT updated
- AND the final output shows "Dry run complete — X workouts would be synced"

#### Scenario: Dry run with verbose logging

- GIVEN the user runs `darth-gain ingest --dry-run --verbose`
- WHEN the sync processes API responses
- THEN each page fetch is logged with count and timing
- AND per-workout summaries include exercise names and set counts

### Requirement: Skip-and-Continue Error Handling

If a single workout fails to process (API error, parse error, database error), the system MUST log the error, increment an error counter, and continue with the next workout. After all pages are processed, the system SHALL print a summary line: `"Sync complete: X updated, Y deleted, Z errors"`.

#### Scenario: Single workout API failure

- GIVEN 10 workouts are returned across 2 pages
- WHEN the 3rd workout's API call fails with a server error (5xx)
- THEN the error is logged with the workout ID and error details
- AND processing continues with the 4th workout
- AND the final summary reports `1 error`

#### Scenario: All workouts fail

- GIVEN the Hevy API returns 500 errors for all pages
- WHEN every workout fails to process
- THEN each error is logged individually
- AND the summary reports `Z errors` matching the total workout count
- AND `last_sync_at` is NOT updated
- AND the system exits with a non-zero code

### Requirement: Progress UX

The system MUST display a Rich progress bar during sync operations. The progress bar SHALL track pages completed out of total pages. For the initial full sync, an estimated time remaining MAY be shown based on page count and inter-page delay.

#### Scenario: Progress display during multi-page sync

- GIVEN the sync spans 10 API pages
- WHEN processing begins
- THEN a progress bar is rendered showing `1/10`, `2/10`, etc.
- AND the bar is updated after each page completes
- AND the bar is removed on completion, replaced by the summary line

#### Scenario: Single-page sync (no progress needed)

- GIVEN the sync completes in a single API page
- WHEN processing finishes
- THEN no progress bar is displayed
- AND only the summary line is printed

### Requirement: Inter-Page Delay

The system SHOULD wait 500ms between paginated API calls during the initial (full) sync to avoid triggering rate-limit heuristics. Subsequent delta syncs MAY skip the delay.

#### Scenario: Delay applied during initial sync

- GIVEN a first sync with 50 pages
- WHEN each page fetch completes
- THEN a 500ms pause occurs before the next page request
- AND the total sync time is at least 25 seconds

#### Scenario: No delay during empty delta sync

- GIVEN a delta sync with zero events returns a single page
- WHEN the page fetch completes
- THEN no inter-page delay is applied
