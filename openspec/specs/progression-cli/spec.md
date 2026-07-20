# Progression CLI Specification

## Purpose

Click-based `progression` command group providing user-facing access to progression checks and configuration. Follows existing CLI patterns: Click groups, `click.echo` output, `click.Abort` on errors, `--db-path` option.

## Requirements

### Requirement: Progression command group exists

The system SHALL register a `progression` group under the root `cli` group, with `check` and `config` subcommands.

#### Scenario: Progression group visible in help

- GIVEN the CLI is installed
- WHEN user runs `darth-gain --help`
- THEN output includes "progression" in the command list

#### Scenario: Config group visible under progression

- GIVEN the CLI is installed
- WHEN user runs `darth-gain progression --help`
- THEN output includes "check", "config"

### Requirement: Check command accepts exercise_template_id

`darth-gain progression check <exercise_template_id>` SHALL accept a positional argument for the exercise template ID, plus `--db-path` to specify a custom database.

#### Scenario: Check command parses exercise ID

- GIVEN a valid exercise template ID `t001`
- WHEN user runs `darth-gain progression check t001`
- THEN the engine runs progression check for `t001`

### Requirement: Check output is a human-readable table

The system SHALL output a formatted table (via `rich.table` or plain `click.echo`) containing: exercise title, current working weight, rep range, status, and recommended next weight.

#### Scenario: Progress status printed to terminal

- GIVEN `t001` (Bench Press) is at "progress" status with `current_weight_kg = 80.0` and `recommended_weight_kg = 82.5`
- WHEN user runs `darth-gain progression check t001`
- THEN output contains "Bench Press", "80.0kg", "82.5kg", "PROGRESS"

#### Scenario: Maintain status printed to terminal

- GIVEN `t002` is at "maintain" status with `current_weight_kg = 80.0`
- WHEN user runs `darth-gain progression check t002`
- THEN output contains "MAINTAIN" or "maintain" and no recommended weight (or "—")

### Requirement: Unknown exercise template ID returns error

The system MUST return a non-zero exit code and a clear error message when the exercise template ID does not exist.

#### Scenario: Check nonexistent exercise

- GIVEN no exercise template with id `bogus999`
- WHEN user runs `darth-gain progression check bogus999`
- THEN exit code is non-zero and output contains "not found" or "unknown"

### Requirement: No workout history returns clear status

The system SHALL print `"INSUFFICIENT_DATA"` (or `"insufficient_data"`) for exercises with no history, not a crash.

#### Scenario: Check exercise with no history

- GIVEN exercise template `t003` has zero sets in the database
- WHEN user runs `darth-gain progression check t003`
- THEN exit code is zero and output contains "insufficient data" or "INSUFFICIENT_DATA"

### Requirement: Unqualified exercise type returns skipped

The system SHALL print `"SKIPPED"` (or `"skipped"`) for exercises where `progression_config.enabled = 0` (e.g. `reps_only` type), with explanation.

#### Scenario: Check reps_only exercise returns skipped

- GIVEN exercise template `t010` has `type = "reps_only"` (auto-disabled)
- WHEN user runs `darth-gain progression check t010`
- THEN exit code is zero and output contains "skipped" and "reps_only"

### Requirement: Config subcommand for showing settings

`darth-gain progression config show <exercise_template_id>` SHALL display rep range, increment, and enabled status.

#### Scenario: Show config for configured exercise

- GIVEN `t001` has config row with `rep_min = 6, rep_max = 10, weight_increment = 5.0, enabled = 1`
- WHEN user runs `darth-gain progression config show t001`
- THEN output contains "6", "10", "5.0", "enabled"

### Requirement: Config subcommand for setting settings

`darth-gain progression config set <exercise_template_id>` SHALL accept `--rep-min`, `--rep-max`, `--increment`, `--enabled/--disabled` to upsert config.

#### Scenario: Set config via CLI

- GIVEN no config row exists for `t001`
- WHEN user runs `darth-gain progression config set t001 --rep-min 8 --rep-max 12 --increment 2.5`
- THEN a config row is upserted with those values and `enabled = 1` (auto-resolved)

### Requirement: Config and check share DB connection pattern

Both commands SHALL use the same `Config` → `create_engine` → `create_tables` pattern as the existing `ingest` command, respecting `--db-path`.

#### Scenario: Custom DB path for check

- GIVEN a database at `/tmp/custom.db` with progression data
- WHEN user runs `darth-gain progression check t001 --db-path /tmp/custom.db`
- THEN the engine connects to `/tmp/custom.db`

### Requirement: CLI access without HEVY_API_KEY

The `progression` commands SHALL NOT require `HEVY_API_KEY` — they work entirely against the local database.

#### Scenario: Progression check without API key

- GIVEN no `HEVY_API_KEY` environment variable
- WHEN user runs `darth-gain progression check t001`
- THEN the command proceeds without error (no API key validation)

## Edge Cases

- **Standard output only**: No Rich progress bars — progression commands are quick queries
- **Exit codes**: All non-error results exit 0; errors (unknown exercise, DB failures) exit non-zero
- **Config set idempotent**: Running `set` with the same values twice produces the same state
