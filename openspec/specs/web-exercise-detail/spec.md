# Web Exercise Detail Specification

## Purpose

Per-exercise detail view showing progression history and configuration editor. Allows users to view historical progression check results as a timeline and edit rep range, increment, and enabled settings inline.

## Requirements

### Requirement: Exercise detail page shows history

The system MUST render `GET /exercises/{exercise_template_id}` as an HTML page showing the exercise title, current status, working weight, rep range, and a chronological list of all progression history entries.

#### Scenario: Detail page renders with history table

- GIVEN exercise "Bench Press" has 8 progression history entries
- WHEN the user navigates to `/exercises/bench_press_template_id`
- THEN the page shows exercise title "Bench Press", current status, working weight, and a table of all 8 history entries with columns: date, status, weight, recommended weight

#### Scenario: Detail page for exercise with no history

- GIVEN exercise "Deadlift" exists but has zero progression history entries
- WHEN the user navigates to `/exercises/deadlift_template_id`
- THEN the page shows the exercise title with "No progression history yet" and no history table

#### Scenario: Nonexistent exercise returns 404

- GIVEN no exercise template with id "nonexistent_999"
- WHEN the user navigates to `/exercises/nonexistent_999`
- THEN the response is 404 with a "Exercise not found" message

### Requirement: History entries displayed as sortable table

The system SHALL display progression history entries in a table with columns: date (`checked_at`), status (with badge), current weight, recommended weight, and details. The table SHALL be sorted by date descending (newest first) by default.

#### Scenario: History table sorted newest first

- GIVEN history entries from March 1, Feb 15, and Jan 10 (all same exercise)
- WHEN the detail page renders
- THEN the table shows March 1 first, then Feb 15, then Jan 10

#### Scenario: History entry details expandable

- GIVEN a history entry with a non-null `details` JSON column
- WHEN the detail page renders
- THEN the table shows an expandable row or tooltip revealing the details JSON (e.g., sets analyzed, rep breakdown)

### Requirement: Inline config editor

The system MUST provide an editable config form on the exercise detail page showing rep_min, rep_max, weight_increment, and enabled fields. The form SHALL be pre-filled with current values and submit via HTMX to `PUT /exercises/{exercise_template_id}/config`.

#### Scenario: Config form pre-filled with current values

- GIVEN exercise "Bench Press" has config: rep_min=6, rep_max=10, increment=5.0, enabled=true
- WHEN the detail page renders
- THEN the config form shows rep_min=6, rep_max=10, increment=5.0, and enabled checked

#### Scenario: Default config shown when not configured

- GIVEN exercise "Deadlift" has no config row (defaults: 8-12, 2.5kg, enabled)
- WHEN the detail page renders
- THEN the config form shows rep_min=8, rep_max=12, increment=2.5, and enabled checked

### Requirement: Config update via PUT endpoint

The system MUST accept `PUT /exercises/{exercise_template_id}/config` with form fields `rep_min`, `rep_max`, `weight_increment`, and `enabled`. On success, it SHALL update the config row and return the updated config as an HTML snippet via HTMX for in-place replacement.

#### Scenario: Successful config update returns updated snippet

- GIVEN exercise "Bench Press" with config rep_min=6, rep_max=10
- WHEN the user submits the form with rep_min=8, rep_max=12
- THEN the config is updated in the database, and the response is an HTML snippet showing the new values (8, 12) in the config form

#### Scenario: Partial update preserves unchanged fields

- GIVEN exercise "Bench Press" config is: rep_min=6, rep_max=10, increment=5.0, enabled=true
- WHEN the user submits only `weight_increment=2.5` (other fields absent)
- THEN increment changes to 2.5; rep_min, rep_max, and enabled remain unchanged

#### Scenario: Invalid values return validation error

- GIVEN exercise "Bench Press"
- WHEN the user submits `rep_min=15, rep_max=10` (min > max)
- THEN the response is 422 with a "rep_min must be less than or equal to rep_max" error, and existing config is unchanged

### Requirement: Loading state for detail page

The system SHALL show a loading indicator while the exercise detail page data is being fetched. For HTMX-driven config updates, a local spinner SHALL appear on the config form during submission.

#### Scenario: Config save shows loading indicator

- GIVEN the user submits a config change
- WHEN the HTMX request is in flight
- THEN the submit button shows a "Saving..." state (disabled + spinner)

### Requirement: Responsive layout for mobile

The detail page SHALL be responsive: the history table SHALL collapse to a card-based layout on screens narrower than 768px, with each history entry showing key fields stacked vertically.

#### Scenario: History table collapses to cards on mobile

- GIVEN a viewport width of 375px
- WHEN the detail page renders
- THEN history entries are displayed as stacked cards (date on top, status badge, weight details below) instead of a horizontal table

#### Scenario: Config form stacked on mobile

- GIVEN a viewport width of 375px
- WHEN the detail page renders
- THEN config fields (rep_min, rep_max, increment, enabled) are stacked vertically, not in a row

### Requirement: Navigation back to dashboard

The detail page SHALL include a breadcrumb or "Back to Dashboard" link at the top for easy navigation.

#### Scenario: Back link navigates to dashboard

- GIVEN the user is on an exercise detail page
- WHEN the user clicks "← Back to Dashboard"
- THEN the browser navigates to `/`

## Edge Cases

- **Special characters in exercise names**: Must be HTML-escaped to prevent XSS
- **Rapid config saves**: Consecutive PUT requests within 500ms SHOULD be debounced or queued
- **Long history**: If an exercise has 100+ history entries, the table SHOULD paginate (e.g., 25 per page) or show a "Load more" button
- **Concurrent config update**: If two tabs save different configs, the last write wins (accepted — no pessimistic locking for this scope)
- **HTMX overflow handling**: Config form errors returned as HTML snippets SHALL be inserted above the form, not replacing it
