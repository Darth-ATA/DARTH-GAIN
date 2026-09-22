# Delta for Routine View

## ADDED Requirements

### Requirement: REQ-RV-001 — Export button in routine group header

The system MUST render an "Export for AI Review" button in each routine group header on the `/routines` page, which triggers a download of the routine's workout history as JSON via the export API.

#### Scenario: Button visible for each routine group

- GIVEN the `/routines` page renders with 2 routine groups ("Push", "Pull")
- WHEN the page loads
- THEN each group header contains an "Export for AI Review" button
- AND the button has `data-routine-id` attribute set to the routine's ID
- AND the button has `data-routine-title` attribute set to the routine's title

#### Scenario: Button not shown for Uncategorized section

- GIVEN the `/routines` page renders with an "Uncategorized" section
- WHEN the page loads
- THEN the "Uncategorized" section header does NOT contain an export button
- AND only routine groups with a valid `routine_id` show the button

### Requirement: REQ-RV-002 — Export button triggers JSON download

The system MUST wire the export button to call `GET /api/v1/routines/{routine_id}/export?weeks=8` via HTMX and trigger a file download with the response.

#### Scenario: Click button downloads JSON file

- GIVEN user is on `/routines` page with routine "R1" ("Push Day")
- WHEN the user clicks the "Export for AI Review" button for "Push Day"
- THEN an HTMX GET request is sent to `/api/v1/routines/R1/export?weeks=8`
- AND the response is received as JSON
- AND the browser triggers a file download
- AND the downloaded file is named `routine-Push Day-8w-2026-08-20.json` (title sanitized, weeks, current date)

#### Scenario: Download filename sanitizes special characters

- GIVEN routine title is "Push/Pull: Legs & Core"
- WHEN the export button is clicked
- THEN the downloaded filename is `routine-Push_Pull__Legs___Core-8w-2026-08-20.json`
- AND invalid filesystem characters are replaced with underscores

#### Scenario: Button shows loading state during request

- GIVEN the user clicks the export button
- WHEN the HTMX request is in flight
- THEN the button shows a loading spinner or "Exporting..." text
- AND the button is disabled to prevent double-clicks

#### Scenario: Error state shows user-friendly message

- GIVEN the export API returns 404 (routine not found) or 500 (server error)
- WHEN the HTMX request completes with error
- THEN a toast notification or inline error message appears: "Failed to export routine data. Please try again."
- AND the button returns to enabled state

### Requirement: REQ-RV-003 — Default weeks parameter (8) used for UI export

The system MUST use the default 8-week window when the export button is clicked from the UI (no weeks selector in MVP).

#### Scenario: UI export uses default 8 weeks

- GIVEN the user clicks "Export for AI Review" for routine "R1"
- WHEN the HTMX request is made
- THEN the request URL includes `?weeks=8` (default)
- AND no weeks parameter picker is shown in the UI

## MODIFIED Requirements

### Requirement: Router — GET /routines

The system MUST provide a `GET /routines` route that runs `ProgressionEngine.check()` per unique exercise template, groups results by routine name, assigns exercises with `routine_id IS NULL` to an `"Uncategorized"` bucket, **and includes export button data in each routine group context**.
(Previously: did not include export button data in template context)

#### Scenario: Template context includes routine_id for export button

- GIVEN 2 routines ("Push", "Pull") each with exercise templates
- WHEN `GET /routines` is called
- THEN the template context `routine_groups` includes each group with `routine_id` field
- AND the `routine_id` is passed through to the template for button wiring

#### Scenario: Uncategorized bucket has no routine_id

- GIVEN an exercise done outside any routine (`routine_id IS NULL`)
- WHEN `GET /routines` is called
- THEN the `uncategorized` context object does NOT include a `routine_id` field
- AND no export button is rendered for the Uncategorized section

### Requirement: Template — routine_view.html

The template MUST display routine groups as headers with exercise cards inside each group, reusing `partials/exercise_card.html`. The `"Uncategorized"` section MUST appear last. **Each routine group header MUST include an "Export for AI Review" button wired to the export API.**
(Previously: no export button in group headers)

#### Scenario: Export button rendered in group header

- GIVEN a routine group with `routine_id="R1"` and `routine_title="Push Day"`
- WHEN `routine_view.html` renders
- THEN the group header contains a button with:
  - Text: "Export for AI Review"
  - `hx-get="/api/v1/routines/R1/export?weeks=8"`
  - `hx-trigger="click"`
  - `hx-target="this"`
  - `hx-swap="none"`
  - `hx-on::after-request="downloadExport(event.detail.xhr.response, 'routine-Push Day-8w-{date}.json')"`
  - `data-routine-id="R1"`
  - `data-routine-title="Push Day"`

#### Scenario: JavaScript download helper available

- GIVEN the `routine_view.html` template renders
- WHEN the page loads
- THEN a JavaScript function `downloadExport(jsonResponse, filename)` is available
- AND it creates a Blob from the JSON, generates a temporary object URL, triggers download via anchor click, and revokes the URL

## REMOVED Requirements

None.

## RENAMED Requirements

None.

## Acceptance Criteria Mapping

| Proposal AC | Requirement(s) |
|-------------|----------------|
| Export button in `routines.html` triggers download of JSON file with filename `routine-{title}-{weeks}w-{date}.json` | REQ-RV-001, REQ-RV-002, REQ-RV-003 |

## Open Questions

1. **HTMX response handling for file download**: HTMX doesn't natively support file downloads from AJAX responses. The current approach uses `hx-on::after-request` with a custom JavaScript handler. Is this the intended pattern, or should we use a standard `<a href="...">` link with `download` attribute (which would require a separate endpoint or query param to trigger download vs inline JSON)?

2. **Weeks selector in UI**: MVP uses default 8 weeks. Should a future iteration add a dropdown/input next to the button to let users choose 4–24 weeks before exporting?

3. **Toast notification system**: The error handling scenario assumes a toast notification system exists. Does the current codebase have one, or should we use a simpler inline error message?

4. **Multiple routine export**: Proposal says "Multi-routine comparison in single export" is out of scope. Should the UI allow selecting multiple routines and exporting a combined file in the future?