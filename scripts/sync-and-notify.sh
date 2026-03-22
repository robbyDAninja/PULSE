#!/bin/bash
set -euo pipefail

# ── Configuration ──────────────────────────────────────────────
REPO_DIR="/Users/robbyhiggins/Documents/Bridge.ninja/openclaw-ecosystem-pulse"
REPORTS_DIR="$REPO_DIR/reports"
LOG_DIR="$REPO_DIR/scripts/logs"
LOG_FILE="$LOG_DIR/pulse-sync.log"
GIT="/usr/bin/git"
GWS="/opt/homebrew/bin/gws"
RECIPIENT="admin@bridge.ninja"

export GOOGLE_WORKSPACE_CLI_CONFIG_DIR="/Users/robbyhiggins/Documents/Bridge.ninja/.gws"

# ── Logging helper ─────────────────────────────────────────────
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"; }

# ── Ensure log directory exists ────────────────────────────────
mkdir -p "$LOG_DIR"

log "=== Pulse sync started ==="

# ── Step 1: Capture current HEAD ───────────────────────────────
cd "$REPO_DIR"
BEFORE=$($GIT rev-parse HEAD)
log "HEAD before pull: $BEFORE"

# ── Step 2: Pull latest ───────────────────────────────────────
if ! $GIT pull --ff-only origin main >> "$LOG_FILE" 2>&1; then
    log "ERROR: git pull failed. Aborting."
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
    log "New commits but no new pulse report. Skipping email."
    exit 0
fi

log "New report detected: $NEW_REPORT"
REPORT_PATH="$REPO_DIR/$NEW_REPORT"

# ── Step 4: Extract report date for subject line ──────────────
REPORT_DATE=$(basename "$NEW_REPORT" | grep -oE '^[0-9]{4}-[0-9]{2}-[0-9]{2}')
SUBJECT="OpenClaw Ecosystem Pulse — $REPORT_DATE"

# ── Step 5: Convert markdown to simple HTML ───────────────────
REPORT_CONTENT=$(cat "$REPORT_PATH")
HTML_BODY=$(echo "$REPORT_CONTENT" | sed \
    -e 's/^# \(.*\)/<h1>\1<\/h1>/' \
    -e 's/^## \(.*\)/<h2>\1<\/h2>/' \
    -e 's/\*\*\([^*]*\)\*\*/<strong>\1<\/strong>/g' \
    -e 's/^- \(.*\)/<li>\1<\/li>/' \
    -e 's|\[\([^]]*\)\](\([^)]*\))|<a href="\2">\1</a>|g' \
    -e '/^$/s/.*/<br>/' \
)

# Wrap in minimal styling
HTML_BODY="<div style=\"font-family: -apple-system, sans-serif; max-width: 680px; line-height: 1.6;\">
${HTML_BODY}
<br><hr><p style=\"color: #888; font-size: 12px;\">Auto-synced from <a href=\"https://github.com/robbyDAninja/openclaw-ecosystem-pulse\">openclaw-ecosystem-pulse</a></p>
</div>"

# ── Step 6: Send email via GWS ────────────────────────────────
log "Sending email to $RECIPIENT..."
if $GWS gmail +send \
    --to "$RECIPIENT" \
    --subject "$SUBJECT" \
    --body "$HTML_BODY" \
    --html >> "$LOG_FILE" 2>&1; then
    log "Email sent successfully."
else
    log "ERROR: Failed to send email. Check gws auth."
fi

log "=== Pulse sync complete ==="
exit 0
