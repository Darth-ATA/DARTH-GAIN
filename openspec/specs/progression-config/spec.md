# Progression Configuration Specification

## Purpose

Per-exercise configuration for the double progression engine: rep ranges, weight increments, and eligibility flags. Persisted in the `progression_config` SQLite table. Applies defaults when no row exists for an exercise template.

## Requirements

### Requirement: Rep range defaults to 8–12 with per-exercise override

The system MUST default to `rep_min = 8` and `rep_max = 12` when no `progression_config` row exists for an exercise template. Users SHALL override rep range per exercise template via CLI.

#### Scenario: Default rep range when no config exists

- GIVEN an exercise template `t001` with no row in `progression_config`
- WHEN the engine queries its rep range
- THEN the system returns `(rep_min = 8, rep_max = 12)`

#### Scenario: Custom rep range saved and retrieved

- GIVEN a `progression_config` row for `t001` with `rep_min = 6, rep_max = 10`
- WHEN the engine queries its rep range
- THEN the system returns `(rep_min = 6, rep_max = 10)`

### Requirement: Weight increment defaults to 2.5kg with per-exercise override

The system MUST default to `weight_increment = 2.5` when no config row exists. Users SHALL override increment per exercise template via CLI.

#### Scenario: Custom increment saved and retrieved

- GIVEN a `progression_config` row for `t001` with `weight_increment = 5.0`
- WHEN the engine queries its increment
- THEN the system returns `5.0`

### Requirement: Auto-eligibility based on exercise template type

The system MUST auto-set `enabled = 1` for exercises with `type = "weight_reps"` and `enabled = 0` for `reps_only` or `duration` type exercises. Users MAY override `enabled` per exercise template via CLI.

#### Scenario: weight_reps exercise auto-enabled

- GIVEN an exercise template `t001` with `type = "weight_reps"` and no `progression_config` row
- WHEN the system first resolves eligibility
- THEN `enabled` defaults to `1`

#### Scenario: reps_only exercise auto-disabled

- GIVEN an exercise template `t002` with `type = "reps_only"` and no config row
- WHEN the system first resolves eligibility
- THEN `enabled` defaults to `0`

#### Scenario: User overrides disabled for an eligible exercise

- GIVEN an exercise template `t001` with `type = "weight_reps"`
- WHEN a user sets `enabled = 0` via CLI
- THEN the engine skips `t001` in progression checks

### Requirement: CLI command to view progression config

The system SHALL provide `darth-gain progression config show <exercise_template_id>` that prints rep range, increment, and enabled status for the given exercise.

#### Scenario: Show config for configured exercise

- GIVEN `t001` has a `progression_config` row with `rep_min = 6, rep_max = 10, weight_increment = 5.0, enabled = 1`
- WHEN the user runs `darth-gain progression config show t001`
- THEN output contains "6", "10", "5.0", "enabled"

#### Scenario: Show config for unconfigured exercise

- GIVEN `t001` has no `progression_config` row
- WHEN the user runs `darth-gain progression config show t001`
- THEN output shows defaults: "8", "12", "2.5", "enabled" (auto-resolved from template type)

### Requirement: CLI command to set progression config

The system SHALL provide `darth-gain progression config set <exercise_template_id>` with options `--rep-min`, `--rep-max`, `--increment`, `--enabled/--disabled` to upsert a config row.

#### Scenario: Set full config for an exercise

- GIVEN no `progression_config` row exists for `t001`
- WHEN user runs `darth-gain progression config set t001 --rep-min 6 --rep-max 10 --increment 5.0 --enabled`
- THEN a row with those values is inserted into `progression_config`

#### Scenario: Set partial config preserves existing values

- GIVEN `t001` has `rep_min = 6, rep_max = 10, weight_increment = 5.0, enabled = 1`
- WHEN user runs `darth-gain progression config set t001 --increment 2.5`
- THEN only `weight_increment` changes to `2.5`; other fields remain

### Requirement: Unknown exercise template ID returns error

The system MUST return a clear error when the exercise template ID does not exist in `exercise_templates`.

#### Scenario: Config show for nonexistent template

- GIVEN no exercise template with id `unknown999`
- WHEN user runs `darth-gain progression config show unknown999`
- THEN the command exits with a non-zero code and a message containing "not found"

## Edge Cases

- **New exercise template**: Auto-resolves defaults based on type; no explicit config row needed
- **Corner values**: Rep min > rep max should be accepted but the engine treats range as invalid — engine scenarios handle this
- **Zero increment**: `weight_increment = 0` means "never increase" — treated as valid
