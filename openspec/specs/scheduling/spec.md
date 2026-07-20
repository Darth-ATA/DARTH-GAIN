# Scheduling Specification

## Purpose

Enable recurring automated Hevy ingests via cron or systemd timer so that the local SQLite database stays current without manual intervention.

## Requirements

### Requirement: Cron Scheduling Documentation

The project SHALL provide clear cron scheduling instructions in a `SCHEDULING.md` document at the repository root. The instructions MUST cover:

1. Determining the `darth-gain` binary path (for pipx-installed and venv-installed setups).
2. Determining the `HEVY_API_TOKEN` environment variable location.
3. A recommended crontab entry that runs `darth-gain ingest` daily at 6:00 AM.
4. How to verify the cron job ran successfully (checking journald logs or mail).
5. How to remove the cron entry.

#### Scenario: User follows cron setup instructions

- GIVEN the user reads `SCHEDULING.md`
- WHEN the user sets up the recommended crontab entry
- THEN the cron job runs `darth-gain ingest` daily at 6:00 AM
- AND errors are captured via cron's mail mechanism or system logger

#### Scenario: Missing HEVY_API_TOKEN in cron environment

- GIVEN the user sets up the cron job but does not provide `HEVY_API_TOKEN` in the cron environment
- WHEN the cron job runs
- THEN the job SHALL fail with a clear error (no API key configured)
- AND cron SHALL mail the error output to the user

### Requirement: Helper Script

The system SHALL provide a helper script at `scripts/install-cron.sh` that automates cron job installation. The script MUST:

1. Detect or prompt for the `darth-gain` command path.
2. Detect or prompt for the `HEVY_API_TOKEN` value.
3. Install a crontab entry that runs `darth-gain ingest` daily at 6:00 AM.
4. Support a `--remove` flag to uninstall the cron entry.
5. Support a `--status` flag to show whether the cron entry is installed.
6. Print what it will do before modifying the crontab (`--dry-run` mode implied).

#### Scenario: Install cron job via helper script

- GIVEN the user runs `scripts/install-cron.sh`
- WHEN the script detects the `darth-gain` path and API key
- THEN it adds `0 6 * * * /path/to/darth-gain ingest` to the user's crontab
- AND prints a confirmation message

#### Scenario: Remove cron job via helper script

- GIVEN a previously installed cron entry exists
- WHEN the user runs `scripts/install-cron.sh --remove`
- THEN the script removes the matching cron line
- AND prints a removal confirmation

#### Scenario: Check cron status

- GIVEN no cron entry is installed
- WHEN the user runs `scripts/install-cron.sh --status`
- THEN the script prints "No DARTH-GAIN cron entry found"
- AND exits with code 0

#### Scenario: Script is idempotent (double install)

- GIVEN the cron entry is already installed
- WHEN the user runs `scripts/install-cron.sh` again
- THEN the script detects the duplicate
- AND does NOT add a second entry
- AND prints "Cron entry already installed"

### Requirement: Error Logging for Scheduled Runs

When `darth-gain ingest` runs from cron (non-interactive, no TTY), the system MUST disable the Rich progress bar and write log output to stdout/stderr only. The cron job's natural output capture (mail or journald) serves as the logging mechanism.

#### Scenario: Non-TTY detected

- GIVEN `darth-gain ingest` is invoked from cron (no TTY)
- WHEN the sync runs
- THEN no progress bar is rendered
- AND the summary line is printed to stdout
- AND errors are printed to stderr
