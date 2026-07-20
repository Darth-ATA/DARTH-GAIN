#!/bin/bash
# ─────────────────────────────────────────────────────────────
# install-cron.sh — Idempotent crontab helper for DARTH-GAIN
#
# Usage:
#   scripts/install-cron.sh                    # Install cron entry
#   scripts/install-cron.sh --remove           # Remove cron entry
#   scripts/install-cron.sh --status           # Check if installed
#   scripts/install-cron.sh --cmd=PATH         # Specify darth-gain path
#   scripts/install-cron.sh --api-key=KEY      # Provide API key explicitly
#   scripts/install-cron.sh --help             # Show this message
# ─────────────────────────────────────────────────────────────
set -Eeuo pipefail

# ── Paths ─────────────────────────────────────────────────────
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SCRIPT_NAME="$(basename -- "${BASH_SOURCE[0]}")"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"

# ── Defaults ──────────────────────────────────────────────────
CRON_SCHEDULE="0 6 * * *"
MODE="install"
DARTH_GAIN_CMD=""
HEVY_API_KEY=""

# ── Help ──────────────────────────────────────────────────────
usage() {
    cat <<EOF
Usage: $SCRIPT_NAME [OPTIONS]

Install, remove, or check a DARTH-GAIN cron job that runs
\`darth-gain ingest\` daily at 6:00 AM.

Options:
    --remove         Remove the DARTH-GAIN cron entry
    --status         Check whether the cron entry is installed
    --cmd=PATH       Full path to the darth-gain binary
    --api-key=KEY    Hevy API key (reads HEVY_API_KEY env by default)
    -h, --help       Show this help message

Examples:
    $SCRIPT_NAME                          # Install (detects paths)
    $SCRIPT_NAME --cmd=\$(command -v darth-gain)  # Install with explicit path
    $SCRIPT_NAME --remove                 # Remove cron entry
    $SCRIPT_NAME --status                 # Check installation status
EOF
    exit "${1:-0}"
}

# ── Logging ───────────────────────────────────────────────────
log_info()  { echo "[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $*" >&2; }
log_warn()  { echo "[$(date +'%Y-%m-%d %H:%M:%S')] WARN: $*" >&2; }
log_error() { echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2; }

# ── Error trap ────────────────────────────────────────────────
trap 'log_error "Unexpected error on line $LINENO"' ERR

# ── Argument parsing ──────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --remove)
            MODE="remove"
            shift
            ;;
        --status)
            MODE="status"
            shift
            ;;
        --cmd=*)
            DARTH_GAIN_CMD="${1#*=}"
            shift
            ;;
        --api-key=*)
            HEVY_API_KEY="${1#*=}"
            shift
            ;;
        -h|--help)
            usage 0
            ;;
        --)
            shift
            break
            ;;
        *)
            log_error "Unknown option: $1"
            usage 1
            ;;
    esac
done

# ── Detect / validate darth-gain path ─────────────────────────
if [[ "$MODE" == "install" ]]; then
    if [[ -z "$DARTH_GAIN_CMD" ]]; then
        DARTH_GAIN_CMD="$(command -v darth-gain)" || {
            log_error "darth-gain not found on PATH. Use --cmd=PATH to specify."
            exit 1
        }
    fi

    # Validate the binary exists and is executable
    if [[ ! -x "$DARTH_GAIN_CMD" ]]; then
        log_error "Not executable: $DARTH_GAIN_CMD"
        exit 1
    fi

    # Validate darth-gain responds (this also makes sure it's the right binary)
    if ! "$DARTH_GAIN_CMD" --help &>/dev/null; then
        log_error "darth-gain at '$DARTH_GAIN_CMD' does not respond to --help."
        exit 1
    fi

    # ── Detect API key ────────────────────────────────────────
    if [[ -z "$HEVY_API_KEY" ]]; then
        HEVY_API_KEY="${HEVY_API_KEY:-}"
    fi

    if [[ -z "$HEVY_API_KEY" ]]; then
        log_warn "HEVY_API_KEY is not set and no --api-key was provided."
        log_warn "The cron job will fail unless the key is available in cron's environment."
        log_warn "Set HEVY_API_KEY in your shell profile or pass --api-key=KEY."
    fi
fi

# ── Status ────────────────────────────────────────────────────
if [[ "$MODE" == "status" ]]; then
    if crontab -l 2>/dev/null | grep -qF "darth-gain ingest"; then
        echo "DARTH-GAIN cron entry IS installed."
        crontab -l 2>/dev/null | grep --color=never "darth-gain ingest"
    else
        echo "No DARTH-GAIN cron entry found."
    fi
    exit 0
fi

# ── Remove ────────────────────────────────────────────────────
if [[ "$MODE" == "remove" ]]; then
    if ! crontab -l 2>/dev/null | grep -qF "darth-gain ingest"; then
        log_info "No DARTH-GAIN cron entry found — nothing to remove."
        exit 0
    fi

    log_info "Removing DARTH-GAIN cron entry..."
    crontab -l 2>/dev/null \
        | grep -vF "darth-gain ingest" \
        | crontab -

    log_info "DARTH-GAIN cron entry removed."
    exit 0
fi

# ── Install ───────────────────────────────────────────────────
CRON_LINE="$CRON_SCHEDULE $DARTH_GAIN_CMD ingest"

if crontab -l 2>/dev/null | grep -qF "darth-gain ingest"; then
    log_info "Cron entry already installed:"
    crontab -l 2>/dev/null | grep --color=never "darth-gain ingest"
    exit 0
fi

log_info "Installing cron entry: $CRON_LINE"

# Check if HEVY_API_KEY is available for the warning
if [[ -z "$HEVY_API_KEY" ]]; then
    log_warn "HEVY_API_KEY is not set. Make sure it's available in cron's environment."
fi

# Append to crontab (idempotent: we already checked it doesn't exist)
(
    crontab -l 2>/dev/null || true
    echo "$CRON_LINE"
) | crontab -

log_info "Cron entry installed successfully."
log_info "Run '$SCRIPT_NAME --status' to verify."
