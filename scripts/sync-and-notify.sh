#!/bin/bash
set -euo pipefail

# ── Configuration ──────────────────────────────────────────────
REPO_DIR="/Users/robbyhiggins/Documents/Bridge.ninja/openclaw-ecosystem-pulse"
LOG_DIR="$REPO_DIR/scripts/logs"
LOG_FILE="$LOG_DIR/pulse-sync.log"
GIT="/usr/bin/git"

# ── Helpers ────────────────────────────────────────────────────
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"; }

notify() {
    local title="$1"
    local message="$2"
    osascript -e "display notification \"$message\" with title \"$title\"" 2>/dev/null || true
}

# ── Ensure log directory exists ────────────────────────────────
mkdir -p "$LOG_DIR"

log "=== Pulse sync started ==="

cd "$REPO_DIR"

# ── Pre-flight: test git connectivity ──────────────────────────
if ! $GIT ls-remote --exit-code origin main > /dev/null 2>&1; then
    log "ERROR: git ls-remote failed. Git auth may be expired."
    notify "OpenClaw Pulse" "Sync failed: git auth expired. Run git pull manually to re-authenticate."
    exit 0
fi

# ── Step 1: Capture current HEAD ───────────────────────────────
BEFORE=$($GIT rev-parse HEAD)
log "HEAD before pull: $BEFORE"

# ── Step 2: Pull latest ───────────────────────────────────────
if ! $GIT pull --ff-only origin main >> "$LOG_FILE" 2>&1; then
    log "ERROR: git pull failed. Aborting."
    notify "OpenClaw Pulse" "Sync failed: git pull error. Check logs."
    exit 0
fi

AFTER=$($GIT rev-parse HEAD)
log "HEAD after pull: $AFTER"

# ── Step 3: Check for new reports ─────────────────────────────
if [ "$BEFORE" = "$AFTER" ]; then
    log "No new commits. Nothing to do."
    exit 0
fi

# Find new report files added between BEFORE and AFTER
NEW_REPORT=$($GIT diff --name-only "$BEFORE" "$AFTER" -- reports/ \
    | grep -E '^reports/[0-9]{4}-[0-9]{2}-[0-9]{2}-openclaw-ecosystem-pulse\.md$' \
    | sort | tail -1) || true

if [ -z "$NEW_REPORT" ]; then
    log "New commits but no new pulse report. Skipping."
    exit 0
fi

# ── Step 4: Notify locally ────────────────────────────────────
REPORT_DATE=$(basename "$NEW_REPORT" | grep -oE '^[0-9]{4}-[0-9]{2}-[0-9]{2}')
log "New report detected: $NEW_REPORT"
notify "OpenClaw Pulse" "New report available: $REPORT_DATE"

log "=== Pulse sync complete ==="
exit 0
