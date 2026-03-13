#!/bin/bash
# Cleanup orphaned cron run files — removes .jsonl files in cron/runs/ that
# don't match any active job ID in jobs.json.
# Added 2026-03-12

JOBS_FILE="/Users/kublai/.openclaw/cron/jobs.json"
RUNS_DIR="/Users/kublai/.openclaw/cron/runs"

if [ ! -f "$JOBS_FILE" ]; then
    echo "[orphan-cron-runs] jobs.json not found at $JOBS_FILE"
    exit 1
fi

if [ ! -d "$RUNS_DIR" ]; then
    echo "[orphan-cron-runs] runs directory not found at $RUNS_DIR"
    exit 0
fi

# Extract active job IDs from jobs.json
ACTIVE_IDS=$(python3 -c "
import json, sys
with open('$JOBS_FILE') as f:
    data = json.load(f)
for job in data.get('jobs', []):
    jid = job.get('id', '')
    if jid:
        print(jid)
")

if [ $? -ne 0 ]; then
    echo "[orphan-cron-runs] Failed to parse jobs.json"
    exit 1
fi

DELETED=0
FREED=0

for runfile in "$RUNS_DIR"/*.jsonl; do
    [ -f "$runfile" ] || continue

    basename=$(basename "$runfile" .jsonl)

    # Check if this file ID matches any active job
    if echo "$ACTIVE_IDS" | grep -qxF "$basename"; then
        continue
    fi

    # Orphan found — delete it
    filesize=$(stat -f%z "$runfile" 2>/dev/null || echo 0)
    rm -f "$runfile"
    DELETED=$((DELETED + 1))
    FREED=$((FREED + filesize))
    echo "  [orphan-cron-runs] Deleted orphan: $basename.jsonl ($filesize bytes)"
done

if [ "$DELETED" -eq 0 ]; then
    echo "[orphan-cron-runs] No orphaned run files found"
else
    echo "[orphan-cron-runs] Deleted $DELETED orphan file(s), freed $FREED bytes"
fi
