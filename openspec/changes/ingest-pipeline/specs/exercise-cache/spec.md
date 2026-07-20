# Exercise Cache Specification

## Purpose

Maintain a local SQLite cache of Hevy exercise templates to avoid redundant API calls. Exercise templates are fetched eagerly on the first sync and persisted for offline use.

## Requirements

### Requirement: Eager Fetch on First Sync

On the first sync (when the `exercise_templates` table is empty), the system MUST fetch ALL exercise templates from the Hevy API before processing workouts. The fetch SHALL use `get_exercise_templates()` with page size 100 and paginate through all pages. Each template SHALL be stored with its `id`, `title`, `type`, `primary_muscle_group`, `secondary_muscle_groups`, `is_custom`, and `synced_at` timestamp.

#### Scenario: Full template cache on initial sync

- GIVEN the `exercise_templates` table is empty
- WHEN `darth-gain ingest` runs
- THEN all exercise templates are fetched from the API (paginating as needed)
- AND each template is inserted into `exercise_templates`
- AND templates are available for any exercise lookups during the same sync run

#### Scenario: Empty template list from API

- GIVEN the user has no exercise templates (brand new Hevy account)
- WHEN the template fetch completes successfully with zero results
- THEN no rows are inserted into `exercise_templates`
- AND the sync continues normally without error

### Requirement: Cache Reuse on Subsequent Syncs

On subsequent syncs (when `exercise_templates` is non-empty), the system MUST skip the API fetch entirely. Exercise templates SHALL be read from the local cache for any lookups needed during workout ingestion.

#### Scenario: Templates cached, no re-fetch

- GIVEN the `exercise_templates` table has 50 rows from a previous sync
- WHEN `darth-gain ingest` runs again
- THEN no API call is made to `get_exercise_templates`
- AND all exercise lookups resolve from SQLite

#### Scenario: Stale cache (templates changed on Hevy)

- GIVEN the local cache was populated 30 days ago and templates have since been edited on Hevy
- WHEN a subsequent delta sync encounters an exercise with a `template_id` not in the cache
- THEN the system SHALL log a warning with the missing template ID
- AND continue processing without fetching the template
- (Note: template changes don't affect historical workout data — the cached title and type are for display/reference only)

### Requirement: Forced Re-Fetch

The system SHOULD support a `--refresh-templates` flag on the `ingest` command that forces a full re-fetch of exercise templates regardless of cache state. When set, the system SHALL truncate the `exercise_templates` table and re-fetch all templates from the API.

#### Scenario: Explicit template refresh

- GIVEN the user runs `darth-gain ingest --refresh-templates`
- WHEN the sync starts
- THEN the `exercise_templates` table is cleared and all templates are re-fetched
- AND workout ingestion proceeds normally

### Requirement: Cache for Offline Display

The system MAY display exercise template titles alongside workout data in dry-run output. Titles SHALL be resolved from the local cache when available. If a template ID is not found in the cache, the raw ID SHALL be displayed instead.

#### Scenario: Template ID not in cache during dry run

- GIVEN the user runs `darth-gain ingest --dry-run` on a fresh database (before first sync)
- WHEN an exercise's `exercise_template_id` is not in the cache
- THEN the output displays the raw template ID as a fallback
- AND no error is raised
