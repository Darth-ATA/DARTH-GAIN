# Scheduling Automated Hevy Syncs

DARTH-GAIN can run automatically via cron to keep your local workout database
current without manual intervention.

## Prerequisites

Before setting up scheduling, ensure:

- `darth-gain` is installed and works from the command line
- You have a valid `HEVY_API_KEY` (from your [Hevy Settings](https://hevy.com/settings))
- Cron is available on your system (macOS/Linux)

## Finding the `darth-gain` Binary Path

### pipx installation

```bash
command -v darth-gain
# Typical output: ~/.local/bin/darth-gain
```

### pip / venv installation

```bash
# Activate your virtual environment first, then:
command -v darth-gain
# Typical output: /path/to/venv/bin/darth-gain
```

Use the full path from `command -v` in your crontab entry.

## Setting up the API Key

The `HEVY_API_KEY` environment variable must be available when `darth-gain`
runs. Cron provides a minimal environment — your shell profile (`.bashrc`,
`.zshrc`) is **not sourced** automatically.

**Option 1 — Shell profile** (if your cron shell reads it):

Add to `~/.profile`, `~/.bash_profile`, or `~/.zshrc`:

```bash
export HEVY_API_KEY="your-api-key-here"
```

**Option 2 — Inline in crontab** (simplest for single-user setups):

```cron
HEVY_API_KEY="your-api-key-here"
0 6 * * * /path/to/darth-gain ingest
```

**Option 3 — Dedicated env file** (keeps secrets out of crontab):

Create `~/.darth-gain/env`:

```
HEVY_API_KEY=your-api-key-here
```

Then reference it in crontab:

```cron
0 6 * * * . $HOME/.darth-gain/env && /path/to/darth-gain ingest
```

## Installing the Cron Job

### Using the helper script (recommended)

```bash
# The helper script detects paths and checks the API key:
scripts/install-cron.sh

# For a fully automated install (specifying the key):
HEVY_API_KEY="your-key" scripts/install-cron.sh

# If darth-gain is not on PATH:
scripts/install-cron.sh --cmd=$(command -v darth-gain)
```

This adds the following entry to your crontab:

```
0 6 * * * /path/to/darth-gain ingest
```

### Manual crontab entry

```bash
crontab -e
```

Add one of the following lines:

**With API key inline:**

```cron
HEVY_API_KEY="your-api-key"
0 6 * * * /path/to/darth-gain ingest
```

**Using an env file:**

```cron
0 6 * * * . $HOME/.darth-gain/env && /path/to/darth-gain ingest
```

**With logging to a file:**

```cron
0 6 * * * /path/to/darth-gain ingest >> $HOME/.darth-gain/cron.log 2>&1
```

## Verifying the Cron Job

### Check if the entry is installed

```bash
scripts/install-cron.sh --status
# Output: "DARTH-GAIN cron entry IS installed."
```

Or manually:

```bash
crontab -l | grep "darth-gain ingest"
```

### Check run logs

If you added logging to a file:

```bash
tail -f ~/.darth-gain/cron.log
```

**On Linux** (with mail):

```bash
# Check cron's mail for any error output
mail
```

**On macOS** (check system logs):

```bash
# Check cron execution logs
grep -i cron /var/log/system.log
log show --predicate 'process == "cron"' --last 1d
```

The expected output from a successful run is:

```
Sync complete: 5 updated, 0 deleted
```

Or on a quiet day with no new workouts:

```
Sync complete: 0 updated, 0 deleted
```

If there are errors, they are reported:

```
Sync complete: 3 updated, 0 deleted, 2 errors
```

## Removing the Cron Job

### Using the helper script

```bash
scripts/install-cron.sh --remove
```

### Manually

```bash
crontab -e
# Remove or comment out the line containing "darth-gain ingest"
```

## How It Works

When `darth-gain ingest` runs from cron (no TTY attached):

1. The CLI detects it is not running in a terminal
2. Rich progress bars are **suppressed** (no ANSI output in logs)
3. The sync runs silently, fetching events since the last successful sync
4. On completion, a single summary line is written to stdout
5. Errors are written to stderr (captured by cron's mail mechanism)

This design ensures clean log files without progress bar garbage.
