#!/bin/bash
# watchdog-gather.sh — Unified TICK: health monitor + task driver
# Runs every 5 minutes via OpenClaw cron (local LLM)
#
# Two jobs:
#   1. Gather infrastructure health metrics
#   2. Push forward all agent task queues
#
# Outputs:
#   - ticks.jsonl    (append, machine-readable history)
#   - tick-summary.txt (overwrite, compact summary for LLM)
#   - watchdog.log   (append, one-liner per tick)
#
# Exit codes: 0=healthy 1=degraded 2=down(restarted) 3=down(restart failed)
#
# STALE TASK DETECTION PRE-FILTER (ogedei-watchdog.py)
# =====================================================
# The watchdog stale detection in ogedei-watchdog.py includes a pre-filter
# to prevent false-positive escalations of completed tasks:
#
#   - Tasks with .verified.done.md suffix (already verified)
#   - Tasks with grade: [A-F] in frontmatter (graded completion)
#   - Tasks with resolved: true in frontmatter (escalations resolved)
#
# This pre-filter eliminates $0.03-0.12 per false positive incident.
# See: mongke/workspace/stale-task-escalation-cost-analysis-2026-03-09.md
#
# Implementation: is_task_already_completed() in ogedei-watchdog.py
#   - Checks file suffixes (.verified.done.md, .resolved.md, etc.)
#   - Checks frontmatter content (grade: A-F, resolved: true)
#   - Called before Tier 3 escalation (check_stalled_tasks function)

set -o pipefail

# === Cron Consolidation 2026-03-23 ===
# Removed duplicate sub-script calls now handled by ogedei-watchdog.py (30s cadence):
# - credential-health-monitor.py -> reads credential-alerts.json
# - completion-audit.py -> reads completion state from ogedei
# - subprocess-audit.py -> reads subprocess state from ogedei

# Single-instance lock — prevents concurrent ticks (e.g., after sleep/wake catch-up)
LOCK_DIR="/tmp/watchdog-gather.lock"
# FIX 2026-03-24: Use rm -rf instead of rmdir to handle PID file inside lock directory
# rmdir fails on non-empty directories, causing stale locks and 9-12min tick gaps
_cleanup_lock() { rm -rf "$LOCK_DIR" 2>/dev/null; }
trap _cleanup_lock EXIT

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    # Check for stale lock (PID file inside lock dir)
    if [ -f "$LOCK_DIR/pid" ]; then
        OLD_PID=$(cat "$LOCK_DIR/pid" 2>/dev/null)
        if [ -n "$OLD_PID" ] && ! kill -0 "$OLD_PID" 2>/dev/null; then
            # Stale lock — previous process died without cleanup
            rmdir "$LOCK_DIR" 2>/dev/null || rm -rf "$LOCK_DIR"
            mkdir "$LOCK_DIR" 2>/dev/null || { echo "[$(date '+%Y-%m-%d %H:%M:%S')] TICK | SKIP: lock contention" >> "$HOME/.openclaw/agents/main/logs/watchdog.log"; exit 0; }
        else
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] TICK | SKIP: already running (pid=$OLD_PID)" >> "$HOME/.openclaw/agents/main/logs/watchdog.log"
            exit 0
        fi
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] TICK | SKIP: already running" >> "$HOME/.openclaw/agents/main/logs/watchdog.log"
        exit 0
    fi
fi
echo $$ > "$LOCK_DIR/pid"

# Source Neo4j credentials
if [ -f "$HOME/.openclaw/credentials/neo4j.env" ]; then
    set -a
    source "$HOME/.openclaw/credentials/neo4j.env"
    set +a
fi

BASE="$HOME/.openclaw/agents/main"
LOGDIR="$BASE/logs"
TICKS="$LOGDIR/ticks.jsonl"
SUMMARY="$LOGDIR/tick-summary.txt"
WATCHDOG_LOG="$LOGDIR/watchdog.log"
OPENCLAW_LOG="$HOME/.openclaw/logs/openclaw.log"
AGENT_BASE="$HOME/.openclaw/agents"
SCRIPTS="$BASE/scripts"
LAST_TICK_FILE="$LOGDIR/.last_tick_epoch"

TS=$(date '+%Y-%m-%d %H:%M:%S')
TS_ISO=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
EPOCH=$(date '+%s')

mkdir -p "$LOGDIR"

# ============================================================
# MODEL DETECTION: Get the model used for LLM triage
# ============================================================
# Read from main agent's .claude/settings.json (watchdog/main uses main agent config)
MODEL=$(python3 "$SCRIPTS/get_model.py" --agent main 2>/dev/null || echo "unknown")

# ============================================================
# SECTION 0a: Execution Gap Detection
# ============================================================
# Detect if we missed scheduled runs (should run every 10min)
# Alert if gap exceeds 12 minutes (allows for some jitter + sleep/wake)
GAP_ALERT_THRESHOLD=720  # 12 minutes in seconds (10min interval + 2min buffer)
LAST_EPOCH=0
GAP_DETECTED=0
GAP_MINUTES=0

if [ -f "$LAST_TICK_FILE" ]; then
    LAST_EPOCH=$(cat "$LAST_TICK_FILE" 2>/dev/null || echo "0")
    if [ "$LAST_EPOCH" -gt 0 ]; then
        GAP_SECONDS=$((EPOCH - LAST_EPOCH))
        if [ "$GAP_SECONDS" -gt "$GAP_ALERT_THRESHOLD" ]; then
            GAP_MINUTES=$((GAP_SECONDS / 60))
            GAP_DETECTED=1
            echo "[$TS] GAP_DETECTED | missed=$((GAP_SECONDS / 600)) ticks | gap=${GAP_MINUTES}m | last_run_ts=$(date -r "$LAST_EPOCH" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo 'unknown')" >> "$WATCHDOG_LOG"
        fi
    fi
fi
# Record current epoch for next run
echo "$EPOCH" > "$LAST_TICK_FILE"

# ============================================================
# SECTION 0: Gateway Instance Deduplication + Health Check
# ============================================================
# Count gateway processes and kill extras (keep only 1)
# Use -x for exact match on command name, exclude our own pgrep
GW_PIDS=$(pgrep -x "openclaw-gateway" 2>/dev/null | sort -n)
if [ -z "$GW_PIDS" ]; then
    GW_COUNT=0
else
    GW_COUNT=$(echo "$GW_PIDS" | wc -l | tr -d ' ')
fi

# Track if we found duplicates BEFORE killing (for health reporting)
GW_DUPLICATES_FOUND=0
if [ "$GW_COUNT" -gt 1 ]; then
    GW_DUPLICATES_FOUND=$GW_COUNT
fi

if [ "$GW_COUNT" -gt 1 ]; then
    # Keep the oldest (first) gateway, kill the rest
    KEEP_PID=$(echo "$GW_PIDS" | head -1)
    KILL_PIDS=$(echo "$GW_PIDS" | tail -n +2)
    
    for pid in $KILL_PIDS; do
        if [ -n "$pid" ] && [ "$pid" != "$KEEP_PID" ]; then
            kill "$pid" 2>/dev/null
            sleep 0.5
            # Force kill if still running
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null
            fi
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] TICK | KILLED duplicate gateway pid=$pid (kept pid=$KEEP_PID)" >> "$WATCHDOG_LOG"
        fi
    done
    
    GW_COUNT=1
    GW_PIDS="$KEEP_PID"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] TICK | GATEWAY HEALTH: Found $GW_DUPLICATES_FOUND instances, reduced to 1" >> "$WATCHDOG_LOG"
fi

# ============================================================
# SECTION 1: Gateway Process
# ============================================================
PIDS=$(pgrep -f "openclaw" 2>/dev/null | head -5 | tr '\n' ',' | sed 's/,$//')
FIRST_PID=$(echo "$PIDS" | cut -d',' -f1)

if [ -n "$FIRST_PID" ] && [ "$FIRST_PID" -gt 0 ] 2>/dev/null; then
    CPU=$(ps -p "$FIRST_PID" -o %cpu= 2>/dev/null | tr -d ' ')
    MEM=$(ps -p "$FIRST_PID" -o %mem= 2>/dev/null | tr -d ' ')
    RSS=$(ps -p "$FIRST_PID" -o rss= 2>/dev/null | tr -d ' ')
    THREADS=$(ps -M -p "$FIRST_PID" 2>/dev/null | wc -l | tr -d ' ')
    ETIME_RAW=$(ps -p "$FIRST_PID" -o etime= 2>/dev/null | tr -d ' ')
    UPTIME_S=$(echo "$ETIME_RAW" | awk -F'[-:]' '{
        n=NF;
        if(n==4) print $1*86400+$2*3600+$3*60+$4;
        else if(n==3) print $1*3600+$2*60+$3;
        else if(n==2) print $1*60+$2;
        else print 0
    }')
else
    CPU=0; MEM=0; RSS=0; THREADS=0; UPTIME_S=0
fi

# ============================================================
# SECTION 2: Health Endpoint (with latency)
# ============================================================
HEALTH_RESULT=$(curl -s -o /dev/null -w "%{http_code} %{time_total}" \
    --max-time 5 http://127.0.0.1:18789/health 2>/dev/null || echo "0 0")
HTTP=$(echo "$HEALTH_RESULT" | awk '{print $1}')
# Sanitize: curl returns "000" on connection failure (invalid JSON) - force to integer
HTTP=$((10#$HTTP))  # Strip leading zeros (base 10), e.g., 000 -> 0
LATENCY_S=$(echo "$HEALTH_RESULT" | awk '{print $2}')
LATENCY_MS=$(echo "$LATENCY_S" | awk '{printf "%.0f", $1 * 1000}')

# ============================================================
# SECTION 3: Error Counts (timestamp-accurate)
# ============================================================
if [ -f "$OPENCLAW_LOG" ]; then
    # Use timestamp-based counting (reads JSON "time" field from log entries)
    # Falls back to line-count heuristic if the python script fails
    ERROR_COUNTS=$(python3 "$SCRIPTS/count_errors.py" "$OPENCLAW_LOG" 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$ERROR_COUNTS" ]; then
        ERRORS_5M=$(echo "$ERROR_COUNTS" | awk '{print $1}')
        ERRORS_1H=$(echo "$ERROR_COUNTS" | awk '{print $2}')
        FATAL_5M=$(echo "$ERROR_COUNTS" | awk '{print $3}')
    else
        # Fallback: line-count heuristic (original approach)
        NOISE_FILTER="gateway-like services\|Cleanup hint\|Recommendation: run\|isolate ports\|com.kurultai.task-watcher\|signal daemon exited\|Service unit not found\|Service not installed\|File logs:\|message failed: Unknown target\|ENOENT.*skills\|command not found: timeout\|(user, plist:\|RPC probe:\|RPC target:\|is already in use\|Gateway target:\|Source: cli\|Multiple listeners\|gateway closed\|Embedded agent failed\|Gateway agent failed\|Unknown agent id\|Config: /Users/\|Gateway already running\|Gateway failed to start\|Gateway service appears\|Tip: openclaw\|Or: launchctl\|- pid \|subsystem.*diagnostic\|subsystem.*gateway"
        ERRORS_5M=$(tail -500 "$OPENCLAW_LOG" 2>/dev/null | grep "ERROR\|FATAL\|CRASH" | grep -cv "$NOISE_FILTER" 2>/dev/null; true)
        ERRORS_1H=$(tail -5000 "$OPENCLAW_LOG" 2>/dev/null | grep "ERROR\|FATAL\|CRASH" | grep -cv "$NOISE_FILTER" 2>/dev/null; true)
        FATAL_5M=$(tail -500 "$OPENCLAW_LOG" 2>/dev/null | grep -c "FATAL\|CRASH" 2>/dev/null; true)
    fi
    # Sanitize: strip non-numeric chars to prevent silent bash -gt failures
    ERRORS_5M=$(echo "$ERRORS_5M" | tr -cd '0-9')
    ERRORS_1H=$(echo "$ERRORS_1H" | tr -cd '0-9')
    FATAL_5M=$(echo "$FATAL_5M" | tr -cd '0-9')
    ERRORS_5M=${ERRORS_5M:-0}; ERRORS_1H=${ERRORS_1H:-0}; FATAL_5M=${FATAL_5M:-0}
else
    ERRORS_5M=0; ERRORS_1H=0; FATAL_5M=0
fi

# ============================================================
# SECTION 3b: PROACTIVE HEALTH CHECKS (New - 2026-03-23)
# ============================================================
# Trend prediction and anomaly detection for earlier warnings
# Implements consensus-approved proposal: ogedei-20260323-124630

TICKS_JSONL="$LOGDIR/ticks.jsonl"
PROACTIVE_ALERTS_TRIGGERED=0

# Run trend prediction to forecast when thresholds will be hit
TREND_PREDICTION=$(python3 "$SCRIPTS_DIR/trend-predictor.py" "$TICKS_JSONL" 2>/dev/null || echo '{"error":"prediction_failed"}')

# Extract trend info
if echo "$TREND_PREDICTION" | grep -q "error"; then
    ERR_DIRECTION="unknown"
else
    ERR_DIRECTION=$(echo "$TREND_PREDICTION" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('trend_direction','unknown'))" 2>/dev/null || echo "unknown")

    # Check if we'll hit a threshold within 30 minutes (proactive alert!)
    APPROACHING_THRESHOLD=$(echo "$TREND_PREDICTION" | python3 -c "
import sys, json
d = json.load(sys.stdin)
hits = d.get('predicted_threshold_hits', {})
for level, info in hits.items():
    if info.get('minutes_until', 999) < 30:
        print(f'{level}:{info[\"minutes_until\"]}:{info[\"threshold\"]}')
        break
" 2>/dev/null || echo "")

    if [ -n "$APPROACHING_THRESHOLD" ]; then
        IFS=':' read -r LEVEL MINS THRESH <<< "$APPROACHING_THRESHOLD"
        echo "[$TS] PROACTIVE_ALERT | trend_prediction | will_hit_${LEVEL}_in_${MINS}min (current=${ERRORS_1H}, threshold=${THRESH})" >> "$WATCHDOG_LOG"
        PROACTIVE_ALERTS_TRIGGERED=$((PROACTIVE_ALERTS_TRIGGERED + 1))

        # Send urgent notification
        "$SCRIPTS_DIR/urgent-notify.sh" "HIGH" "Proactive Alert: Error Rate Rising" \
            "Trend prediction shows error rate will hit ${LEVEL} threshold in ~${MINS} minutes.

Current: ${ERRORS_1H} errors/hour
Threshold: ${THRESH} errors/hour
Trend: ${ERR_DIRECTION}

Action recommended: Investigate error sources before threshold is breached." \
            >> "$LOGDIR/proactive-alert-$EPOCH.log" 2>&1
    fi
fi

# Run anomaly detection against baseline
ANOMALY_DETECTION=$(python3 "$SCRIPTS_DIR/anomaly-detector.py" "$TICKS_JSONL" "${ERRORS_1H:-0}" 2>/dev/null || echo '{"error":"detection_failed"}')

# Extract anomaly info
if echo "$ANOMALY_DETECTION" | grep -q "error"; then
    ANOMALY_SEVERITY="unknown"
else
    ANOMALY_SEVERITY=$(echo "$ANOMALY_DETECTION" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('severity','NORMAL'))" 2>/dev/null || echo "NORMAL")

    # Trigger alert if anomaly detected (HIGH or CRITICAL)
    if [ "$ANOMALY_SEVERITY" = "HIGH" ] || [ "$ANOMALY_SEVERITY" = "CRITICAL" ]; then
        ANOMALY_ZSCORE=$(echo "$ANOMALY_DETECTION" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('z_score',0))" 2>/dev/null || echo "0")
        ANOMALY_DEV=$(echo "$ANOMALY_DETECTION" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('deviation_from_mean',0))" 2>/dev/null || echo "0")

        echo "[$TS] PROACTIVE_ALERT | anomaly_detection | severity=${ANOMALY_SEVERITY} zscore=${ANOMALY_ZSCORE} deviation=${ANOMALY_DEV}" >> "$WATCHDOG_LOG"
        PROACTIVE_ALERTS_TRIGGERED=$((PROACTIVE_ALERTS_TRIGGERED + 1))

        # Send urgent notification
        "$SCRIPTS_DIR/urgent-notify.sh" "${ANOMALY_SEVERITY}" "Anomaly Detected: Error Rate Deviation" \
            "Error rate is ${ANOMALY_SEVERITY}: ${ANOMALY_DEV:+${ANOMALY_DEV} }from baseline for this time of day (z-score: ${ANOMALY_ZSCORE}).

Current: ${ERRORS_1H} errors/hour
Baseline varies by time of day.

Action recommended: Investigate unusual error activity." \
            >> "$LOGDIR/anomaly-alert-$EPOCH.log" 2>&1
    fi
fi

# ============================================================
# SECTION 4: Dependent Services
# ============================================================
SCRIPTS_DIR="$(dirname "$0")"
NEO4J_STATUS=$(python3 -c "
import signal, sys
signal.alarm(15)  # kill after 15 seconds (was 8s — too short during GC pauses with large heap)
sys.path.insert(0, '$SCRIPTS_DIR')
from neo4j_task_tracker import get_driver, close_driver
try:
    d = get_driver()
    d.verify_connectivity(); print('up'); close_driver()
except Exception: print('down')
" 2>/dev/null || echo "down")

REDIS_STATUS=$(redis-cli ping 2>/dev/null | grep -q "PONG" && echo "up" || echo "down")

# ============================================================
# SECTION 4aa: Cloudflare Tunnel (cloudflared) Health + Auto-Recovery
# ============================================================
# Critical infrastructure: the.kurult.ai depends on cloudflared tunnel
# If cloudflared stops, the site returns HTTP 530 (origin unreachable)
CLOUDFLARED_STATUS=$(pgrep -f "cloudflared tunnel run" >/dev/null 2>&1 && echo "up" || echo "down")
# Sanitize PIDs: replace newlines with commas for JSON safety
CLOUDFLARED_PID=$(pgrep -f "cloudflared tunnel run" 2>/dev/null | tr '\n' ',' | sed 's/,$//' || echo "none")
CLOUDFLARED_RECOVERY_ATTEMPTED=0
CLOUDFLARED_RECOVERY_RESULT=""

# Auto-restart cloudflared if down (prevents extended downtime)
if [ "$CLOUDFLARED_STATUS" = "down" ]; then
    # Check for recent recovery attempt (5 min cooldown to avoid thrashing)
    CLOUDFLARED_COOLDOWN_FILE="$LOGDIR/.cloudflared_recovery_last"
    MAY_RECOVER=1
    if [ -f "$CLOUDFLARED_COOLDOWN_FILE" ]; then
        LAST_RECOVERY=$(cat "$CLOUDFLARED_COOLDOWN_FILE" 2>/dev/null || echo "0")
        RECOVERY_AGE_S=$((EPOCH - LAST_RECOVERY))
        if [ "$RECOVERY_AGE_S" -lt 300 ]; then
            MAY_RECOVER=0
        fi
    fi

    if [ "$MAY_RECOVER" = "1" ]; then
        CLOUDFLARED_RECOVERY_ATTEMPTED=1
        echo "[$TS] CLOUDFLARED_RECOVERY | attempting restart (tunnel detected down)" >> "$WATCHDOG_LOG"

        # Try launchd first (preferred persistent method)
        if launchctl list | grep -q "com.cloudflare.cloudflared"; then
            # Unload and reload to force restart
            launchctl bootout gui/$(id -u)/com.cloudflare.cloudflared 2>/dev/null || true
            sleep 2
            launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist 2>/dev/null
        else
            # Fallback: direct cloudflared start
            ~/bin/cloudflared tunnel run kublai-macmini >/dev/null 2>&1 &
        fi

        # Wait and verify tunnel started
        sleep 3
        CLOUDFLARED_STATUS_AFTER=$(pgrep -f "cloudflared tunnel run" >/dev/null 2>&1 && echo "up" || echo "down")

        if [ "$CLOUDFLARED_STATUS_AFTER" = "up" ]; then
            CLOUDFLARED_RECOVERY_RESULT="success"
            CLOUDFLARED_STATUS="up"
            CLOUDFLARED_PID=$(pgrep -f "cloudflared tunnel run" 2>/dev/null | tr '\n' ',' | sed 's/,$//' || echo "unknown")
            echo "[$TS] CLOUDFLARED_RECOVERY | success | tunnel PID: $CLOUDFLARED_PID" >> "$WATCHDOG_LOG"
        else
            CLOUDFLARED_RECOVERY_RESULT="failed"
            echo "[$TS] CLOUDFLARED_RECOVERY | failed | escalation required - the.kurult.ai may be down" >> "$WATCHDOG_LOG"
        fi

        # Record recovery attempt time
        echo "$EPOCH" > "$CLOUDFLARED_COOLDOWN_FILE"
    else
        echo "[$TS] CLOUDFLARED_RECOVERY | skipped | cooldown active (${RECOVERY_AGE_S}s since last)" >> "$WATCHDOG_LOG"
    fi
fi

# ============================================================
# SECTION 4a: Neo4j Auto-Recovery
# ============================================================
# Attempt to restart Neo4j if down (prevents EXECUTING_NO_OUTPUT cascade)
# Auto-recovery reduces mean time to recovery from minutes to seconds
NEO4J_RECOVERY_ATTEMPTED=0
NEO4J_RECOVERY_RESULT=""
if [ "$NEO4J_STATUS" = "down" ]; then
    # Check if we have a recent recovery attempt (avoid thrashing - wait 5 min between attempts)
    RECOVERY_COOLDOWN_FILE="$LOGDIR/.neo4j_recovery_last"
    MAY_RECOVER=1
    if [ -f "$RECOVERY_COOLDOWN_FILE" ]; then
        LAST_RECOVERY=$(cat "$RECOVERY_COOLDOWN_FILE" 2>/dev/null || echo "0")
        RECOVERY_AGE_S=$((EPOCH - LAST_RECOVERY))
        if [ "$RECOVERY_AGE_S" -lt 300 ]; then  # 5 min cooldown
            MAY_RECOVER=0
        fi
    fi

    if [ "$MAY_RECOVER" = "1" ]; then
        NEO4J_RECOVERY_ATTEMPTED=1
        echo "[$TS] NEO4J_RECOVERY | attempting restart (neo4j detected down)" >> "$WATCHDOG_LOG"

        # Use 'start' not 'restart' — restart sends SIGTERM first, which kills Neo4j
        # if it was just slow to respond (GC pause). Start is a no-op if already running.
        if command -v brew >/dev/null 2>&1; then
            brew services start neo4j >/dev/null 2>&1
        else
            # Fallback: direct neo4j command
            neo4j start >/dev/null 2>&1
        fi

        # Wait for Neo4j to start with retries (can take 5-30 seconds for cold start)
        NEO4J_STATUS_AFTER="down"
        for retry in {1..15}; do
            sleep 2
            NEO4J_STATUS_AFTER=$(python3 -c "
import signal, sys
signal.alarm(5)
sys.path.insert(0, '$SCRIPTS_DIR')
from neo4j_task_tracker import get_driver, close_driver
try:
    d = get_driver()
    d.verify_connectivity(); print('up'); close_driver()
except Exception: print('down')
" 2>/dev/null || echo "down")

            if [ "$NEO4J_STATUS_AFTER" = "up" ]; then
                break
            fi
        done

        if [ "$NEO4J_STATUS_AFTER" = "up" ]; then
            NEO4J_RECOVERY_RESULT="success"
            NEO4J_STATUS="up"  # Update for rest of script
            echo "[$TS] NEO4J_RECOVERY | success | neo4j back online" >> "$WATCHDOG_LOG"
        else
            NEO4J_RECOVERY_RESULT="failed"
            echo "[$TS] NEO4J_RECOVERY | failed | escalation required" >> "$WATCHDOG_LOG"
        fi

        # Record recovery attempt time
        echo "$EPOCH" > "$RECOVERY_COOLDOWN_FILE"
    else
        echo "[$TS] NEO4J_RECOVERY | skipped | cooldown active (${RECOVERY_AGE_S}s since last)" >> "$WATCHDOG_LOG"
    fi
fi

# ============================================================
# SECTION 4b: Credential Health Check (fleet API tokens)
# ============================================================
# Validates ANTHROPIC_AUTH_TOKEN for all agents (must start with sk-ant-)
# Fleet-wide credential crisis detection (DashScope tokens = invalid)
# FIX: Capture output even when exit code 2 (crisis) is returned
# Exit codes: 0=healthy, 1=degraded, 2=crisis — all are valid outputs
# Use { ...; } to run in subshell and capture output before exit code propagates
# [COMMENTED 2026-03-23] Duplicates ogedei-watchdog.py check_credential_failures() + check_agent_credentials()
# ogedei runs at 30s cadence and writes credential-alerts.json + agent-health-flags.json
# CRED_HEALTH_OUTPUT=$({ python3 "$SCRIPTS/credential-health-monitor.py" 2>&1 || true; } | tail -1)
# CRED_HEALTH_FLEET=$(echo "$CRED_HEALTH_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('fleet_health','unknown'))" 2>/dev/null || echo "unknown")
# CRED_HEALTH_VALID=$(echo "$CRED_HEALTH_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('summary',{}).get('valid',0))" 2>/dev/null || echo "0")
# CRED_HEALTH_INVALID=$(echo "$CRED_HEALTH_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('summary',{}).get('invalid',0))" 2>/dev/null || echo "0")
# CRED_HEALTH_MISSING=$(echo "$CRED_HEALTH_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('summary',{}).get('missing',0))" 2>/dev/null || echo "0")

# Credential health (was: python3 credential-health-monitor.py)
# Now reads ogedei-watchdog's state files instead (runs at 30s cadence)
CRED_STATE_FILE="$LOGDIR/credential-alerts.json"
CRED_FLAGS_FILE="$LOGDIR/agent-health-flags.json"
if [ -f "$CRED_STATE_FILE" ]; then
    # credential-alerts.json has: {"ts": "...", "alerts": [...]}
    CRED_ALERT_COUNT=$(python3 -c "import json; d=json.load(open('$CRED_STATE_FILE')); print(len(d.get('alerts',[])))" 2>/dev/null || echo "0")
else
    CRED_ALERT_COUNT="0"
fi
if [ -f "$CRED_FLAGS_FILE" ]; then
    # agent-health-flags.json has per-agent failure rates and flagged status
    CRED_HEALTH_FLEET=$(python3 -c "
import json
d=json.load(open('$CRED_FLAGS_FILE'))
flags=d.get('agents',{})
total=len(flags)
flagged=sum(1 for f in flags.values() if f.get('flagged'))
if flagged == 0: print('healthy')
elif flagged == total and total > 0: print('crisis')
else: print('degraded')
" 2>/dev/null || echo "unknown")
    CRED_HEALTH_VALID=$(python3 -c "import json; d=json.load(open('$CRED_FLAGS_FILE')); print(sum(1 for f in d.get('agents',{}).values() if not f.get('flagged')))" 2>/dev/null || echo "0")
    CRED_HEALTH_INVALID=$(python3 -c "import json; d=json.load(open('$CRED_FLAGS_FILE')); print(sum(1 for f in d.get('agents',{}).values() if f.get('flagged')))" 2>/dev/null || echo "0")
    CRED_HEALTH_MISSING="0"
else
    CRED_HEALTH_FLEET="unknown"
    CRED_HEALTH_VALID="0"
    CRED_HEALTH_INVALID="0"
    CRED_HEALTH_MISSING="0"
fi

# ============================================================
# SECTION 4c: Auth Heartbeat (actual authentication test)
# ============================================================
# Tests if claude-agent can actually authenticate (not just format check)
# Creates logs/auth-heartbeat.json with last-success timestamps
# Task-watcher checks this BEFORE dispatching to prevent auth failures
# FIX 2026-03-11: Added to prevent jochi/ogedei auth failures during task execution
AUTH_HEARTBEAT_OUTPUT=$(python3 "$SCRIPTS/auth_heartbeat.py" 2>&1 || true)
AUTH_HEARTBEAT_FAILED=$(echo "$AUTH_HEARTBEAT_OUTPUT" | grep -c "✗" || true)
# If any agent failed auth, mark degraded but continue (tasks will skip unhealthy agents)

# ============================================================
# SECTION 4d: Circuit Breaker Auto-Recovery
# ============================================================
# Recover OPEN circuits that have been quarantined longer than RECOVERY_TIMEOUT (30min)
# Prevents agents from being stuck in OPEN state indefinitely
# Transitions OPEN -> HALF_OPEN automatically after timeout
CIRCUIT_RECOVER_OUTPUT=$(python3 "$SCRIPTS/circuit_breaker.py" --recover 2>/dev/null || echo '{"recovered":[],"still_open":[]}')
CIRCUIT_RECOVERED=$(echo "$CIRCUIT_RECOVER_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('recovered',[])))" 2>/dev/null || echo "0")
CIRCUIT_STILL_OPEN=$(echo "$CIRCUIT_RECOVER_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('still_open',[])))" 2>/dev/null || echo "0")

# ============================================================
# SECTION 5: Task Queue Status + Push Forward
# ============================================================
AGENTS=("kublai" "temujin" "mongke" "chagatai" "jochi" "ogedei" "tolui")
TASKS_DISPATCHED=0
TASKS_PENDING_TOTAL=0
TASK_QUEUE_STATUS=""
SPAWN_COUNT=0

# ============================================================
# SECTION 5b: Completion Audit (continuous verification)
# ============================================================
# Run lightweight audit of recently completed tasks to catch fake completions
# Integrated into heartbeat cycle (every 5 minutes) for continuous monitoring
# LLM review provides intelligent escalation decisions
# [COMMENTED 2026-03-23] Duplicates ogedei-watchdog.py verify_recent_completions()
# ogedei runs at 30s cadence and tracks completion verification in its state file
# COMPLETION_AUDIT_OUTPUT=$(python3 "$SCRIPTS/completion-audit.py" --json 2>/dev/null || echo "{}")
# COMPLETION_AUDIT_FAKE=$(echo "$COMPLETION_AUDIT_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('fake_found',0))" 2>/dev/null || echo "0")
# COMPLETION_AUDIT_REQUEUED=$(echo "$COMPLETION_AUDIT_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('requeued',0))" 2>/dev/null || echo "0")
# COMPLETION_AUDIT_VERIFIED=$(echo "$COMPLETION_AUDIT_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('verified',0))" 2>/dev/null || echo "0")
# COMPLETION_AUDIT_LLM_DECISION=$(echo "$COMPLETION_AUDIT_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('llm_decision','IGNORE'))" 2>/dev/null || echo "IGNORE")
# COMPLETION_AUDIT_LLM_CONFIDENCE=$(echo "$COMPLETION_AUDIT_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('llm_confidence',0))" 2>/dev/null || echo "0")

# Completion audit (was: python3 completion-audit.py --json)
# Now reads ogedei-watchdog's state file instead (runs at 30s cadence)
OGEDEI_STATE_FILE="$LOGDIR/ogedei-watchdog-state.json"
if [ -f "$OGEDEI_STATE_FILE" ]; then
    COMPLETION_AUDIT_FAKE=$(python3 -c "import json; d=json.load(open('$OGEDEI_STATE_FILE')); print(d.get('fake_completions_found',0))" 2>/dev/null || echo "0")
    COMPLETION_AUDIT_VERIFIED=$(python3 -c "import json; d=json.load(open('$OGEDEI_STATE_FILE')); print(d.get('completions_verified',0))" 2>/dev/null || echo "0")
    COMPLETION_AUDIT_REQUEUED=$(python3 -c "import json; d=json.load(open('$OGEDEI_STATE_FILE')); print(d.get('completions_requeued',0))" 2>/dev/null || echo "0")
else
    COMPLETION_AUDIT_FAKE="0"
    COMPLETION_AUDIT_VERIFIED="0"
    COMPLETION_AUDIT_REQUEUED="0"
fi
# LLM decision fields not available from ogedei state — default to safe values
COMPLETION_AUDIT_LLM_DECISION="IGNORE"
COMPLETION_AUDIT_LLM_CONFIDENCE="0"

# ============================================================
# SECTION 5c: Vote Sync (DISABLED - migrated to voting_manager.py)
# ============================================================
# NOTE: vote_manager.py was archived 2026-03-08. Voting now uses
# voting_manager.py with proposals/voting/ directory. Vote sync
# is handled by kurultai_voting.py during reflection, not tick.
# VOTE_SYNC_COUNT=0
# VOTE_SYNC_ERRORS=0
# for agent in kublai temujin mongke chagatai jochi ogedei tolui; do
#     SYNC_RESULT=$(python3 "$SCRIPTS/vote_manager.py" sync --agent "$agent" 2>&1 || echo "error")
#     if echo "$SYNC_RESULT" | grep -q "Synced [1-9]"; then
#         SYNCED=$(echo "$SYNC_RESULT" | grep -o 'Synced [0-9]*' | grep -o '[0-9]*' || echo "0")
#         VOTE_SYNC_COUNT=$((VOTE_SYNC_COUNT + SYNCED))
#     fi
#     if echo "$SYNC_RESULT" | grep -q "error"; then
#         VOTE_SYNC_ERRORS=$((VOTE_SYNC_ERRORS + 1))
#     fi
# done
# Set defaults for tick summary output
VOTE_SYNC_COUNT=0
VOTE_SYNC_ERRORS=0

# ============================================================
# SECTION 5d: Subprocess Audit (claude-agent process correlation)
# ============================================================
# Audit active claude-agent processes and correlate with executing tasks
# Detects orphaned files, missing PID sentinels, zombie processes, stale executions
# [COMMENTED 2026-03-23] Duplicates ogedei-watchdog.py process monitoring (check_stalled_tasks, check_agent_failure_rates)
# ogedei runs at 30s cadence with tiered stall detection and PID verification
# SUBPROCESS_AUDIT_OUTPUT=$(python3 "$SCRIPTS/subprocess-audit.py" --json 2>/dev/null || echo "{}")
# SUBPROCESS_EXECUTING=$(echo "$SUBPROCESS_AUDIT_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); s=d.get('summary',{}); print(s.get('total_executing',0))" 2>/dev/null || echo "0")
# SUBPROCESS_ALIVE=$(echo "$SUBPROCESS_AUDIT_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); s=d.get('summary',{}); print(s.get('alive',0))" 2>/dev/null || echo "0")
# SUBPROCESS_DEAD=$(echo "$SUBPROCESS_AUDIT_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); s=d.get('summary',{}); print(s.get('dead',0))" 2>/dev/null || echo "0")
# SUBPROCESS_STALE=$(echo "$SUBPROCESS_AUDIT_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); s=d.get('summary',{}); print(s.get('stale',0))" 2>/dev/null || echo "0")
# SUBPROCESS_ZOMBIES=$(echo "$SUBPROCESS_AUDIT_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); a=d.get('anomalies',[]); print(sum(1 for x in a if x.get('type')=='zombie_process'))" 2>/dev/null || echo "0")
# SUBPROCESS_ORPHANED=$(echo "$SUBPROCESS_AUDIT_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); a=d.get('anomalies',[]); print(sum(1 for x in a if x.get('type')=='orphaned_executing'))" 2>/dev/null || echo "0")
# SUBPROCESS_ANOMALIES=$(echo "$SUBPROCESS_AUDIT_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); s=d.get('summary',{}); print(s.get('anomaly_count',0))" 2>/dev/null || echo "0")

# Subprocess audit (was: python3 subprocess-audit.py --json)
# Now reads ogedei-watchdog's state file instead (runs at 30s cadence)
# Reuse OGEDEI_STATE_FILE from completion audit section above
if [ -f "$OGEDEI_STATE_FILE" ]; then
    SUBPROCESS_EXECUTING=$(python3 -c "import json; d=json.load(open('$OGEDEI_STATE_FILE')); print(d.get('executing_tasks',0))" 2>/dev/null || echo "0")
    SUBPROCESS_STALE=$(python3 -c "import json; d=json.load(open('$OGEDEI_STATE_FILE')); print(d.get('stale_tasks',0))" 2>/dev/null || echo "0")
    SUBPROCESS_ANOMALIES=$(python3 -c "import json; d=json.load(open('$OGEDEI_STATE_FILE')); print(d.get('anomaly_count',0))" 2>/dev/null || echo "0")
else
    SUBPROCESS_EXECUTING="0"
    SUBPROCESS_STALE="0"
    SUBPROCESS_ANOMALIES="0"
fi
# Detailed breakdown not tracked in ogedei state — default to safe values
# Zombie cleanup (Section 5e) still works: it reads the flag file, not SUBPROCESS_AUDIT_OUTPUT
SUBPROCESS_ALIVE="0"
SUBPROCESS_DEAD="0"
SUBPROCESS_ZOMBIES="0"
SUBPROCESS_ORPHANED="0"

# ============================================================
# SECTION 5e: Resolution Compliance Audit (task completion quality)
# ============================================================
# Audit task reports for missing ## Resolution sections (horde-review PRIORITY_FIX)
# Tracks whether agents are properly documenting their fix outcomes
# < 90% compliance triggers escalation to jochi (quality assurance)
RESOLUTION_AUDIT_OUTPUT=$(python3 "$SCRIPTS/audit_missing_resolutions.py" --recent 24 --json 2>/dev/null || echo '{"completion_rate_percent":0}')
RESOLUTION_COMPLIANCE=$(echo "$RESOLUTION_AUDIT_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('completion_rate_percent',0))" 2>/dev/null || echo "0")
RESOLUTION_WITH=$(echo "$RESOLUTION_AUDIT_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('with_resolution',0))" 2>/dev/null || echo "0")
RESOLUTION_WITHOUT=$(echo "$RESOLUTION_AUDIT_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('without_resolution',0))" 2>/dev/null || echo "0")

# Query Neo4j for pending task counts (unified task executor is the source of truth)
# File-based task tracking was deprecated in favor of Neo4j database
TASKS_PENDING_TOTAL=0
TASK_QUEUE_STATUS=""
NEO4J_PENDING_QUERY=$(python3 -c "
from neo4j import GraphDatabase
import json
import sys
try:
    driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'password'))
    with driver.session() as session:
        result = session.run('''
            MATCH (t:Task {status: \"PENDING\"})
            RETURN t.agent_id as agent, count(t) as count
            ORDER BY count DESC
        ''')
        counts = {row['agent'] or 'unassigned': row['count'] for row in result}
        print(json.dumps(counts))
    driver.close()
except Exception as e:
    print(json.dumps({}), file=sys.stderr)
    sys.exit(1)
" 2>/dev/null || echo "{}")

if [ -n "$NEO4J_PENDING_QUERY" ]; then
    for agent in "${AGENTS[@]}"; do
        PENDING=$(echo "$NEO4J_PENDING_QUERY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('$agent', 0))" 2>/dev/null || echo "0")
        TASKS_PENDING_TOTAL=$((TASKS_PENDING_TOTAL + PENDING))
        if [ "$PENDING" -gt 0 ]; then
            TASK_QUEUE_STATUS="${TASK_QUEUE_STATUS}${agent}=${PENDING},"
        fi
    done
fi

# task-executor (launchd daemon) is the sole dispatcher for all tasks
# Read dispatch count from task-executor heartbeat/pid (fixes visibility gap)
TASKS_DISPATCHED=0
if [ -f "$BASE/logs/task-executor.pid" ]; then
    TASKS_DISPATCHED=$(python3 -c "
import json, sys
try:
    d=json.load(open('$BASE/logs/task-executor-heartbeat.json'))
    print(d.get('last_dispatch_count', 0))
except Exception: print(0)
" 2>/dev/null || echo "0")
fi
# Fallback: spawn queue count
if [ -f "$BASE/logs/spawn-pending.json" ]; then
    SPAWN_COUNT=$(python3 -c "
import json
try:
    d=json.load(open('$BASE/logs/spawn-pending.json'))
    ready=[s for s in d.get('spawns',[]) if s.get('status')=='ready']
    print(len(ready))
except Exception: print(0)
" 2>/dev/null || echo "0")
else
    SPAWN_COUNT=0
fi

TASK_QUEUE_STATUS="${TASK_QUEUE_STATUS%,}"

# ============================================================
# SECTION 6: Compute 1-Hour Trends (from last 12 ticks)
# ============================================================
if [ -f "$TICKS" ]; then
    TRENDS=$(tail -12 "$TICKS" | python3 -c "
import sys, json
ticks = []
for line in sys.stdin:
    line = line.strip()
    if line:
        try: ticks.append(json.loads(line))
        except Exception: pass
if not ticks:
    print('100.0 0.0 0 0 stable 0')
    sys.exit(0)
n = len(ticks)
gw = [t.get('gateway',{}) for t in ticks]
up = sum(1 for g in gw if g.get('http',0) == 200)
uptime_pct = round(100.0 * up / n, 1)
avg_cpu = round(sum(t.get('process',{}).get('cpu_pct',0) for t in ticks) / n, 1)
avg_lat = round(sum(g.get('latency_ms',0) for g in gw) / n)
errs = [t.get('errors',{}).get('last_5m',0) for t in ticks]
err_avg = round(sum(errs) / n, 1)
# Direction: compare first-half avg vs second-half avg
mid = n // 2 or 1
first_avg = sum(errs[:mid]) / mid
second_avg = sum(errs[mid:]) / max(len(errs[mid:]), 1)
if second_avg > first_avg * 1.25:
    err_dir = 'rising'
elif second_avg < first_avg * 0.75:
    err_dir = 'falling'
else:
    err_dir = 'stable'
restarts = sum(1 for t in ticks if 'restart' in str(t.get('action','')))
print(f'{uptime_pct} {avg_cpu} {avg_lat} {err_avg} {err_dir} {restarts}')
" 2>/dev/null || echo "100.0 0.0 0 0 stable 0")
else
    TRENDS="100.0 0.0 0 0 stable 0"
fi
UPTIME_1H=$(echo "$TRENDS" | awk '{print $1}')
AVG_CPU_1H=$(echo "$TRENDS" | awk '{print $2}')
AVG_LAT_1H=$(echo "$TRENDS" | awk '{print $3}')
ERR_AVG_5M=$(echo "$TRENDS" | awk '{print $4}')
ERR_DIRECTION=$(echo "$TRENDS" | awk '{print $5}')
RESTARTS_1H=$(echo "$TRENDS" | awk '{print $6}')

# ============================================================
# SECTION 6b: Routing Metrics (from routing-metrics.sh or latest hourly file)
# ============================================================
# Read or compute routing metrics for queue balance index
ROUTING_BALANCE_IDX=0
ROUTING_MISSED=0
ROUTING_ACCURACY=0.87
ROUTING_P95=420
ROUTING_TOTAL=0

# Try to get from latest hourly file
LATEST_ROUTING_JSON=$(ls -t "$LOGDIR"/routing-metrics-*.json 2>/dev/null | head -1)
if [ -n "$LATEST_ROUTING_JSON" ]; then
    FILE_AGE_S=$(( $(date +%s) - $(stat -f%m "$LATEST_ROUTING_JSON" 2>/dev/null || stat -c%Y "$LATEST_ROUTING_JSON" 2>/dev/null) ))
    if [ "$FILE_AGE_S" -lt 7200 ]; then  # File is fresh (< 2 hours)
        ROUTING_BALANCE_IDX=$(python3 -c "import json; print(json.load(open('$LATEST_ROUTING_JSON')).get('queue_balance',{}).get('index',0))" 2>/dev/null || echo "0")
        ROUTING_MISSED=$(python3 -c "import json; print(json.load(open('$LATEST_ROUTING_JSON')).get('routing',{}).get('missed_opportunities',0))" 2>/dev/null || echo "0")
        ROUTING_ACCURACY=$(python3 -c "import json; print(json.load(open('$LATEST_ROUTING_JSON')).get('routing',{}).get('routing_accuracy',0.87))" 2>/dev/null || echo "0.87")
        ROUTING_P95=$(python3 -c "import json; print(json.load(open('$LATEST_ROUTING_JSON')).get('routing',{}).get('time_to_start_p95_seconds',420))" 2>/dev/null || echo "420")
        ROUTING_TOTAL=$(python3 -c "import json; print(json.load(open('$LATEST_ROUTING_JSON')).get('routing',{}).get('total_routed',0))" 2>/dev/null || echo "0")
    fi
fi

# Fallback: compute queue balance index from current queue state
if [ "$ROUTING_BALANCE_IDX" = "0" ]; then
    ROUTING_BALANCE_IDX=$(python3 -c "
import statistics, os, glob
agents = ['kublai', 'temujin', 'mongke', 'chagatai', 'jochi', 'ogedei', 'tolui']
base = '$AGENT_BASE'
depths = []
for agent in agents:
    task_dir = f'{base}/{agent}/tasks'
    if os.path.isdir(task_dir):
        pending = 0
        for f in glob.glob(f'{task_dir}/*.md'):
            if any(x in f for x in ['.done', '.executing', '.completed', '.stale', '.failed', '.obsolete', '.cancelled', '.resolved', '.revision', '.no_output', '.loop']):
                continue
            pending += 1
        depths.append(pending)
    else:
        depths.append(0)
mean_depth = statistics.mean(depths) if depths else 0
std_depth = statistics.stdev(depths) if len(depths) > 1 else 0
balance_idx = round(std_depth / mean_depth, 3) if mean_depth > 0 else 0
print(balance_idx)
" 2>/dev/null || echo "0")
fi

# ============================================================
# SECTION 6c: Pre-decision throughput anomaly check
# ============================================================
THROUGHPUT_ANOMALY_TYPE=""
THROUGHPUT_SEVERITY=""
THROUGHPUT_CONSECUTIVE=0
THROUGHPUT_OUTPUT=$(python3 "$SCRIPTS/throughput_anomaly.py" 2>/dev/null)
if [ -n "$THROUGHPUT_OUTPUT" ]; then
    # Extract anomaly type for decision logic
    # Order matters: check highest priority first (matches throughput_anomaly.py priority)
    if echo "$THROUGHPUT_OUTPUT" | grep -q "HIGH_FAILURE_RATE"; then
        THROUGHPUT_ANOMALY_TYPE="HIGH_FAILURE_RATE"
    elif echo "$THROUGHPUT_OUTPUT" | grep -q "PENDING_NO_DISPATCH"; then
        THROUGHPUT_ANOMALY_TYPE="PENDING_NO_DISPATCH"
    elif echo "$THROUGHPUT_OUTPUT" | grep -q "EXECUTING_NO_OUTPUT"; then
        THROUGHPUT_ANOMALY_TYPE="EXECUTING_NO_OUTPUT"
    elif echo "$THROUGHPUT_OUTPUT" | grep -q "LOW_YIELD"; then
        THROUGHPUT_ANOMALY_TYPE="LOW_YIELD"
    elif echo "$THROUGHPUT_OUTPUT" | grep -q "QUEUE_IMBALANCE"; then
        THROUGHPUT_ANOMALY_TYPE="QUEUE_IMBALANCE"
    elif echo "$THROUGHPUT_OUTPUT" | grep -q "FLEET_IDLE"; then
        THROUGHPUT_ANOMALY_TYPE="FLEET_IDLE"
    fi
    # Extract persistent severity from THROUGHPUT_SEVERITY line
    SEVERITY_LINE=$(echo "$THROUGHPUT_OUTPUT" | grep "^THROUGHPUT_SEVERITY:" | head -1)
    if [ -n "$SEVERITY_LINE" ]; then
        THROUGHPUT_SEVERITY=$(echo "$SEVERITY_LINE" | sed 's/^THROUGHPUT_SEVERITY: *//' | awk '{print $1}')
        THROUGHPUT_CONSECUTIVE=$(echo "$SEVERITY_LINE" | grep -o 'consecutive=[0-9]*' | cut -d= -f2)
        THROUGHPUT_CONSECUTIVE=${THROUGHPUT_CONSECUTIVE:-0}
    fi
fi

# ============================================================
# SECTION 7: Decision Logic
# ============================================================
STATUS="healthy"
ACTION="none"
REASON="all checks passed"
EXIT_CODE=0

GW_STATUS="up"
[ "$HTTP" != "200" ] && GW_STATUS="degraded"
[ -z "$PIDS" ] && GW_STATUS="down"

# DOWN: no process and no endpoint
if [ -z "$PIDS" ] && [ "$HTTP" = "000" ]; then
    STATUS="down"; ACTION="restart"; REASON="no PID and endpoint unreachable"; EXIT_CODE=2
    launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway 2>/dev/null
    sleep 5
    NEW_PID=$(pgrep -f "openclaw" | head -1)
    if [ -n "$NEW_PID" ]; then
        ACTION="restart_ok"; REASON="restarted (new PID: $NEW_PID)"
    else
        ACTION="restart_fail"; REASON="restart failed"; EXIT_CODE=3
    fi
# DEGRADED conditions
elif [ "$HTTP" != "200" ] && [ "$HTTP" != "000" ]; then
    STATUS="degraded"; ACTION="warn"; REASON="endpoint HTTP $HTTP"; EXIT_CODE=1
elif [ -n "$CPU" ] && [ "$(echo "$CPU > 80" | bc -l 2>/dev/null)" = "1" ]; then
    STATUS="degraded"; ACTION="warn"; REASON="high CPU ${CPU}%"; EXIT_CODE=1
elif [ -n "$RSS" ] && [ "$RSS" -gt 1048576 ] 2>/dev/null; then
    STATUS="degraded"; ACTION="warn"; REASON="high RSS $(( RSS / 1024 ))MB"; EXIT_CODE=1
elif [ "$ERRORS_5M" -gt 100 ]; then
    STATUS="degraded"; ACTION="warn"; REASON="$ERRORS_5M errors in 5m"; EXIT_CODE=1
elif [ "$ERRORS_1H" -gt 400 ]; then
    STATUS="degraded"; ACTION="warn"; REASON="sustained errors: $ERRORS_1H in 1h"; EXIT_CODE=1
elif [ "$ERRORS_1H" -gt 150 ] && [ "$ERR_DIRECTION" = "rising" ]; then
    STATUS="degraded"; ACTION="warn"; REASON="rising errors: $ERRORS_1H in 1h (trend: rising)"; EXIT_CODE=1
# Earlier warning levels (2026-03-23: proactive alerting)
elif [ "$ERRORS_1H" -gt 75 ] && [ "$ERR_DIRECTION" = "rising" ]; then
    STATUS="degraded"; ACTION="warn"; REASON="rising errors early warning: $ERRORS_1H in 1h (trend: rising)"; EXIT_CODE=1
elif [ "$ERRORS_1H" -gt 50 ]; then
    STATUS="degraded"; ACTION="warn"; REASON="elevated errors: $ERRORS_1H in 1h (monitoring)"; EXIT_CODE=1
# Spike detection: current 5m errors far above rolling average
elif [ "$ERRORS_5M" -gt 20 ] && [ -n "$ERR_AVG_5M" ] && [ "$(echo "$ERRORS_5M > $ERR_AVG_5M * 3 + 5" | bc -l 2>/dev/null)" = "1" ]; then
    STATUS="degraded"; ACTION="warn"; REASON="error spike: $ERRORS_5M in 5m (rolling avg: $ERR_AVG_5M)"; EXIT_CODE=1
elif [ "$LATENCY_MS" -gt 2000 ] && [ "$HTTP" = "200" ]; then
    STATUS="degraded"; ACTION="warn"; REASON="latency ${LATENCY_MS}ms"; EXIT_CODE=1
elif [ "$NEO4J_STATUS" = "down" ] || [ "$REDIS_STATUS" = "down" ] || [ "$CLOUDFLARED_STATUS" = "down" ]; then
    STATUS="degraded"; ACTION="warn"
    REASON="services down: $([ "$NEO4J_STATUS" = "down" ] && echo neo4j)$([ "$REDIS_STATUS" = "down" ] && echo ${NEO4J_STATUS:+,}redis)$([ "$CLOUDFLARED_STATUS" = "down" ] && echo ${NEO4J_STATUS:+${REDIS_STATUS:+,}}cloudflared)"
    EXIT_CODE=1
# Resolution compliance: task completion quality tracking (horde-review PRIORITY_FIX)
elif [ "$RESOLUTION_COMPLIANCE" -lt 90 ] 2>/dev/null; then
    STATUS="degraded"; ACTION="warn"
    REASON="resolution compliance ${RESOLUTION_COMPLIANCE}% < 90% threshold: ${RESOLUTION_WITHOUT} reports missing ## Resolution section"
    EXIT_CODE=1
fi

# Safety-net: cross-validate decision vs error thresholds
# Catches cases where the elif chain silently missed a threshold
# Logs diagnostic info when triggered (indicates logic bypass in main chain)
if [ "$STATUS" = "healthy" ]; then
    _SAFETY_HIT=""
    if [ "${ERRORS_1H:-0}" -gt 400 ] 2>/dev/null; then
        _SAFETY_HIT="errors_1h=${ERRORS_1H}>400"
        STATUS="degraded"; ACTION="warn"; REASON="sustained errors: $ERRORS_1H in 1h (safety-net)"; EXIT_CODE=1
    elif [ "${ERRORS_5M:-0}" -gt 100 ] 2>/dev/null; then
        _SAFETY_HIT="errors_5m=${ERRORS_5M}>100"
        STATUS="degraded"; ACTION="warn"; REASON="$ERRORS_5M errors in 5m (safety-net)"; EXIT_CODE=1
    elif [ "${ERRORS_1H:-0}" -gt 150 ] && [ "$ERR_DIRECTION" = "rising" ] 2>/dev/null; then
        _SAFETY_HIT="errors_1h=${ERRORS_1H}>150+rising"
        STATUS="degraded"; ACTION="warn"; REASON="rising errors: $ERRORS_1H in 1h (safety-net)"; EXIT_CODE=1
    elif [ "${ERRORS_1H:-0}" -gt 75 ] && [ "$ERR_DIRECTION" = "rising" ] 2>/dev/null; then
        _SAFETY_HIT="errors_1h=${ERRORS_1H}>75+rising"
        STATUS="degraded"; ACTION="warn"; REASON="rising errors early warning: $ERRORS_1H in 1h (safety-net)"; EXIT_CODE=1
    elif [ "${ERRORS_1H:-0}" -gt 50 ] 2>/dev/null; then
        _SAFETY_HIT="errors_1h=${ERRORS_1H}>50"
        STATUS="degraded"; ACTION="warn"; REASON="elevated errors: $ERRORS_1H in 1h (safety-net)"; EXIT_CODE=1
    fi
    # Gateway instance count check (after dedup)
    if [ "${GW_DUPLICATES_FOUND:-0}" -gt 1 ] 2>/dev/null; then
        _SAFETY_HIT="gateway_instances=${GW_DUPLICATES_FOUND}>1"
        STATUS="degraded"; ACTION="warn"; REASON="gateway running $GW_DUPLICATES_FOUND instances (auto-reduced to 1) - investigate root cause"; EXIT_CODE=1
    fi
    if [ -n "$_SAFETY_HIT" ]; then
        echo "[$TS] SAFETY_NET_HIT | trigger=$_SAFETY_HIT | errors_5m=$ERRORS_5M errors_1h=$ERRORS_1H err_avg=$ERR_AVG_5M err_dir=$ERR_DIRECTION" >> "$WATCHDOG_LOG"
    fi
fi

# Throughput anomaly escalation: promote to degraded if dispatch is stalled
if [ -n "$THROUGHPUT_ANOMALY_TYPE" ]; then
    if [ "$STATUS" = "healthy" ]; then
        STATUS="degraded"; ACTION="warn"
        REASON="throughput anomaly: $THROUGHPUT_ANOMALY_TYPE (pending=$TASKS_PENDING_TOTAL, consecutive=${THROUGHPUT_CONSECUTIVE})"
        EXIT_CODE=1
    fi
    # Force-escalate on sustained anomalies (HIGH/CRITICAL bypass LLM triage)
    if [ "$THROUGHPUT_SEVERITY" = "HIGH" ] || [ "$THROUGHPUT_SEVERITY" = "CRITICAL" ]; then
        STATUS="degraded"; ACTION="escalate"
        REASON="sustained throughput anomaly: $THROUGHPUT_ANOMALY_TYPE x${THROUGHPUT_CONSECUTIVE} ticks ($THROUGHPUT_SEVERITY)"
        EXIT_CODE=1
    fi
fi

# Subprocess anomaly escalation: orphaned or stale executions require recovery
if [ "${SUBPROCESS_ORPHANED:-0}" -gt 0 ] || [ "${SUBPROCESS_STALE:-0}" -gt 0 ]; then
    if [ "$STATUS" = "healthy" ]; then
        STATUS="degraded"; ACTION="warn"
        REASON="subprocess anomaly: orphaned=$SUBPROCESS_ORPHANED stale=$SUBPROCESS_STALE (recovery needed)"
        EXIT_CODE=1
    fi
    # Log anomaly details for investigation
    echo "[$TS] SUBPROCESS_ANOMALY | orphaned=$SUBPROCESS_ORPHANED stale=$SUBPROCESS_STALE zombies=$SUBPROCESS_ZOMBIES dead=$SUBPROCESS_DEAD" >> "$WATCHDOG_LOG"
    # Trigger task-watcher recovery by touching a flag file
    touch "$BASE/logs/subprocess-recovery-needed.flag"
fi

# ============================================================
# SECTION 5e: Automatic Zombie Process Cleanup
# ============================================================
# Kill zombie handler processes immediately instead of waiting for task-executor
# Prevents resource waste and false-positive "executing" status in telemetry
#
# FALSE-POSITIVE PREVENTION (2026-03-09):
# The subprocess-audit.py now filters out handlers with recent .done.md files
# (within 60 seconds) to avoid killing legitimate handlers during normal shutdown.
# See: docs/zombie-handler-research-2026-03-09.md for full analysis.
#
# NOTE 2026-03-23: SUBPROCESS_ZOMBIES defaults to 0 since subprocess-audit.py was replaced
# by ogedei-watchdog.py state file reads. Zombie detection is now handled by ogedei's
# check_stalled_tasks() with tiered recovery (Tier 2 clears locks, Tier 3 escalates).
# This block is retained but effectively dormant — it will only fire if SUBPROCESS_ZOMBIES
# is manually set or re-populated from a future state file field.
if [ "${SUBPROCESS_ZOMBIES:-0}" -gt 0 ]; then
    # Extract zombie PIDs from audit output (legacy — needs SUBPROCESS_AUDIT_OUTPUT)
    ZOMBIE_PIDS=$(echo "${SUBPROCESS_AUDIT_OUTPUT:-}" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for a in data.get('anomalies', []):
        if a.get('type') == 'zombie_process' and a.get('pid'):
            print(a.get('pid'))
except Exception: pass
" 2>/dev/null || echo "")

    if [ -n "$ZOMBIE_PIDS" ]; then
        ZOMBIES_KILLED=0
        for zombie_pid in $ZOMBIE_PIDS; do
            # Double-check this is actually a handler process (safety)
            if [ -n "$zombie_pid" ] && ps -p "$zombie_pid" -o command= 2>/dev/null | grep -q "task_executor"; then
                # Graceful kill first
                kill "$zombie_pid" 2>/dev/null
                sleep 0.5
                # Force kill if still running
                if kill -0 "$zombie_pid" 2>/dev/null; then
                    kill -9 "$zombie_pid" 2>/dev/null
                fi
                # Verify termination
                if ! kill -0 "$zombie_pid" 2>/dev/null; then
                    ZOMBIES_KILLED=$((ZOMBIES_KILLED + 1))
                    echo "[$TS] ZOMBIE_CLEANUP | killed zombie handler pid=$zombie_pid" >> "$WATCHDOG_LOG"
                fi
            fi
        done

        if [ "$ZOMBIES_KILLED" -gt 0 ]; then
            echo "[$TS] ZOMBIE_CLEANUP | killed $ZOMBIES_KILLED zombie process(es)" >> "$WATCHDOG_LOG"
        fi
    fi
fi

# ============================================================
# SECTION 5f: Stale Task Claim Cleanup
# ============================================================
# Clear stale session_keys from PENDING tasks that failed to execute
# This fixes PENDING_NO_DISPATCH where tasks have old session_keys but
# no handler is running (from crashed/timed-out handlers)
#
# BUG: When a handler crashes or times out, the session_key remains in
# Neo4j. The claim_task_atomic() function rejects PENDING tasks with
# non-null session_keys as "already_claimed", preventing re-dispatch.
#
# FIX: Clear session_keys for PENDING tasks with stale claims (>10 min old)
# allowing task-watcher to re-dispatch them.
#
# NOTE: Run on EVERY tick, not just when subprocess anomalies detected.
# Stale claims occur from handler timeouts, manual kills, network issues, etc.
# The 10-minute age threshold prevents clearing active legitimate claims.
#
STALE_CLAIMS_OUTPUT=$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPTS_DIR')
from neo4j_v2_core import TaskStore
s = TaskStore()
orphans = s.recover_orphans(grace_minutes=10)
for o in orphans: print(f\"Recovered: {o['task_id']} ({o.get('assigned_to','?')})\")
if not orphans: print('No stale claims')
s.close()
" 2>>"$LOGDIR/watchdog-neo4j-errors.log" || echo "Neo4j unavailable")
STALE_CLAIMS_CLEARED=$(echo "$STALE_CLAIMS_OUTPUT" | grep -c "Recovered:" 2>/dev/null || echo 0)
STALE_CLAIMS_CLEARED=$(echo "$STALE_CLAIMS_CLEARED" | tr -d '[:space:]' | grep -o '[0-9]*' | tail -1)
STALE_CLAIMS_CLEARED=${STALE_CLAIMS_CLEARED:-0}
if [ "$STALE_CLAIMS_CLEARED" -gt 0 ] 2>/dev/null; then
    echo "[$TS] STALE_CLAIM_CLEANUP | cleared $STALE_CLAIMS_CLEARED stale claim(s)" >> "$WATCHDOG_LOG"
fi

# Disk space check
AVAIL_KB=$(df -k "$LOGDIR" 2>/dev/null | awk 'NR==2{print $4}')
if [ "${AVAIL_KB:-0}" -lt 524288 ] 2>/dev/null; then  # < 512MB
    STATUS="degraded"; ACTION="warn"
    REASON="low disk: $((AVAIL_KB / 1024))MB available"
    EXIT_CODE=1
fi

# Disk usage growth monitoring
OPENCLAW_SIZE_FILE="$LOGDIR/.openclaw_size_prev"
OPENCLAW_SIZE_CURRENT=$(du -sk "$HOME/.openclaw" 2>/dev/null | awk '{print $1}')
if [ -f "$OPENCLAW_SIZE_FILE" ] && [ -n "$OPENCLAW_SIZE_CURRENT" ]; then
    OPENCLAW_SIZE_PREV=$(cat "$OPENCLAW_SIZE_FILE" 2>/dev/null || echo 0)
    # Growth in KB (over ~5 minutes between ticks)
    OPENCLAW_GROWTH=$((OPENCLAW_SIZE_CURRENT - OPENCLAW_SIZE_PREV))
    # Alert on >500MB growth per tick (rapid accumulation)
    if [ "$OPENCLAW_GROWTH" -gt 512000 ] 2>/dev/null; then
        GROWTH_MB=$((OPENCLAW_GROWTH / 1024))
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] TICK | WARN: rapid disk growth ${GROWTH_MB}MB/5min" >> "$WATCHDOG_LOG"
        # Don't degrade status but log warning
    fi
fi
echo "$OPENCLAW_SIZE_CURRENT" > "$OPENCLAW_SIZE_FILE"

# Human-readable uptime
if [ "$UPTIME_S" -gt 86400 ]; then
    UPTIME_H="$(( UPTIME_S / 86400 ))d$(( (UPTIME_S % 86400) / 3600 ))h"
elif [ "$UPTIME_S" -gt 3600 ]; then
    UPTIME_H="$(( UPTIME_S / 3600 ))h$(( (UPTIME_S % 3600) / 60 ))m"
else
    UPTIME_H="$(( UPTIME_S / 60 ))m"
fi
RSS_MB=$(( ${RSS:-0} / 1024 ))

# ============================================================
# WRITE 1: Append to ticks.jsonl
# ============================================================
printf '{"ts":"%s","epoch":%s,"model":"%s","heartbeat":{"gap_detected":%s,"gap_minutes":%s,"last_epoch":%s},"gateway":{"status":"%s","pid":"%s","http":%s,"latency_ms":%s,"uptime_s":%s,"instance_count":%s},"process":{"cpu_pct":%s,"mem_pct":%s,"rss_kb":%s,"threads":%s},"errors":{"last_5m":%s,"last_1h":%s,"fatal_5m":%s},"services":{"neo4j":"%s","redis":"%s","cloudflared":"%s","cloudflared_pid":"%s","recovery":{"neo4j":{"attempted":%s,"result":"%s"},"cloudflared":{"attempted":%s,"result":"%s"}}},"credentials":{"fleet_health":"%s","valid":%s,"invalid":%s,"missing":%s},"auth_heartbeat":{"failed_checks":%s},"circuit_breaker":{"recovered":%s,"still_open":%s},"tasks":{"pending":%s,"dispatched":%s,"spawn_ready":%s,"queues":"%s","audit":{"verified":%s,"fake_found":%s,"requeued":%s,"llm_decision":"%s","llm_confidence":%s},"vote_sync_count":%s},"subprocess":{"executing":%s,"alive":%s,"dead":%s,"stale":%s,"zombies":%s,"orphaned":%s,"anomalies":%s},"resolution":{"compliance_pct":%s,"with":%s,"without":%s},"routing":{"queue_balance_index":%s,"missed_opportunities":%s,"routing_accuracy":%s,"time_to_start_p95":%s,"total_routed":%s},"trends":{"uptime_pct_1h":%s,"avg_cpu_1h":%s,"avg_latency_1h":%s,"err_avg_5m":%s,"err_direction":"%s","restarts_1h":%s},"throughput":{"anomaly_type":"%s","severity":"%s","consecutive":%s},"decision":"%s","action":"%s","reason":"%s"}\n' \
    "$TS_ISO" "$EPOCH" "$MODEL" "$GAP_DETECTED" "${GAP_MINUTES:-0}" "$LAST_EPOCH" \
    "$GW_STATUS" "$PIDS" "$HTTP" "$LATENCY_MS" "${UPTIME_S:-0}" "${GW_COUNT:-1}" \
    "${CPU:-0}" "${MEM:-0}" "${RSS:-0}" "${THREADS:-0}" \
    "$ERRORS_5M" "$ERRORS_1H" "$FATAL_5M" \
    "$NEO4J_STATUS" "$REDIS_STATUS" "$CLOUDFLARED_STATUS" "${CLOUDFLARED_PID:-none}" "${NEO4J_RECOVERY_ATTEMPTED:-0}" "${NEO4J_RECOVERY_RESULT:-}" "${CLOUDFLARED_RECOVERY_ATTEMPTED:-0}" "${CLOUDFLARED_RECOVERY_RESULT:-}" \
    "$CRED_HEALTH_FLEET" "$CRED_HEALTH_VALID" "$CRED_HEALTH_INVALID" "$CRED_HEALTH_MISSING" \
    "${AUTH_HEARTBEAT_FAILED:-0}" \
    "${CIRCUIT_RECOVERED:-0}" "${CIRCUIT_STILL_OPEN:-0}" \
    "$TASKS_PENDING_TOTAL" "$TASKS_DISPATCHED" "${SPAWN_COUNT:-0}" "$TASK_QUEUE_STATUS" \
    "$COMPLETION_AUDIT_VERIFIED" "$COMPLETION_AUDIT_FAKE" "$COMPLETION_AUDIT_REQUEUED" "$COMPLETION_AUDIT_LLM_DECISION" "$COMPLETION_AUDIT_LLM_CONFIDENCE" "$VOTE_SYNC_COUNT" \
    "$SUBPROCESS_EXECUTING" "$SUBPROCESS_ALIVE" "$SUBPROCESS_DEAD" "$SUBPROCESS_STALE" "$SUBPROCESS_ZOMBIES" "$SUBPROCESS_ORPHANED" "$SUBPROCESS_ANOMALIES" \
    "$RESOLUTION_COMPLIANCE" "$RESOLUTION_WITH" "$RESOLUTION_WITHOUT" \
    "$ROUTING_BALANCE_IDX" "$ROUTING_MISSED" "$ROUTING_ACCURACY" "$ROUTING_P95" "$ROUTING_TOTAL" \
    "$UPTIME_1H" "$AVG_CPU_1H" "$AVG_LAT_1H" "$ERR_AVG_5M" "$ERR_DIRECTION" "$RESTARTS_1H" \
    "${THROUGHPUT_ANOMALY_TYPE:-}" "${THROUGHPUT_SEVERITY:-}" "${THROUGHPUT_CONSECUTIVE:-0}" \
    "$STATUS" "$ACTION" "$REASON" >> "$TICKS"

# ============================================================
# WRITE 2: Overwrite tick-summary.txt (for LLM)
# ============================================================
printf 'TICK %s\nMODEL: %s (LLM triage)\nHEARTBEAT: gap_detected=%s gap_minutes=%s\nGATEWAY: %s pid=%s http=%s latency=%sms uptime=%s instances=%s\nPROCESS: cpu=%s%% mem=%s%% rss=%sMB threads=%s\nERRORS:  last5m=%s last1h=%s fatal=%s\nSERVICES: neo4j=%s redis=%s cloudflared=%s pid=%s\nRECOVERY: neo4j_attempted=%s neo4j_result=%s cloudflared_attempted=%s cloudflared_result=%s\nCREDENTIALS: fleet_health=%s valid=%s invalid=%s missing=%s\nAUTH_HEARTBEAT: failed_checks=%s\nCIRCUIT_BREAKER: recovered=%s still_open=%s\nTASKS:   pending=%s dispatched=%s spawn=%s queues=[%s]\nAUDIT:   verified=%s fake=%s requeued=%s llm_decision=%s llm_confidence=%s%%\nVOTES:   synced=%s errors=%s\nSUBPROC: executing=%s alive=%s dead=%s stale=%s zombies=%s orphaned=%s anomalies=%s\nRESOLUTION: compliance=%s%% (with=%s without=%s)\nROUTING: balance_idx=%s missed=%s accuracy=%s%% p95=%ss routed=%s\nTRENDS:  uptime_1h=%s%% avg_cpu=%s%% err_avg_5m=%s err_direction=%s restarts_1h=%s\nDECISION: %s\nACTION:   %s\nREASON:   %s\n' \
    "$TS" "$MODEL" "$GAP_DETECTED" "${GAP_MINUTES:-0}" \
    "$GW_STATUS" "$PIDS" "$HTTP" "$LATENCY_MS" "$UPTIME_H" "${GW_COUNT:-1}" \
    "${CPU:-0}" "${MEM:-0}" "$RSS_MB" "${THREADS:-0}" \
    "$ERRORS_5M" "$ERRORS_1H" "$FATAL_5M" \
    "$NEO4J_STATUS" "$REDIS_STATUS" "$CLOUDFLARED_STATUS" "${CLOUDFLARED_PID:-none}" \
    "${NEO4J_RECOVERY_ATTEMPTED:-0}" "${NEO4J_RECOVERY_RESULT:--}" "${CLOUDFLARED_RECOVERY_ATTEMPTED:-0}" "${CLOUDFLARED_RECOVERY_RESULT:--}" \
    "$CRED_HEALTH_FLEET" "$CRED_HEALTH_VALID" "$CRED_HEALTH_INVALID" "$CRED_HEALTH_MISSING" \
    "${AUTH_HEARTBEAT_FAILED:-0}" \
    "${CIRCUIT_RECOVERED:-0}" "${CIRCUIT_STILL_OPEN:-0}" \
    "$TASKS_PENDING_TOTAL" "$TASKS_DISPATCHED" "$SPAWN_COUNT" "$TASK_QUEUE_STATUS" \
    "$COMPLETION_AUDIT_VERIFIED" "$COMPLETION_AUDIT_FAKE" "$COMPLETION_AUDIT_REQUEUED" "$COMPLETION_AUDIT_LLM_DECISION" "$COMPLETION_AUDIT_LLM_CONFIDENCE" \
    "$VOTE_SYNC_COUNT" "$VOTE_SYNC_ERRORS" \
    "$SUBPROCESS_EXECUTING" "$SUBPROCESS_ALIVE" "$SUBPROCESS_DEAD" "$SUBPROCESS_STALE" "$SUBPROCESS_ZOMBIES" "$SUBPROCESS_ORPHANED" "$SUBPROCESS_ANOMALIES" \
    "$RESOLUTION_COMPLIANCE" "$RESOLUTION_WITH" "$RESOLUTION_WITHOUT" \
    "$ROUTING_BALANCE_IDX" "$ROUTING_MISSED" "$(python3 -c "print(int($ROUTING_ACCURACY*100))" 2>/dev/null || echo "87")" "$ROUTING_P95" "$ROUTING_TOTAL" \
    "$UPTIME_1H" "$AVG_CPU_1H" "$ERR_AVG_5M" "$ERR_DIRECTION" "$RESTARTS_1H" \
    "$STATUS" "$ACTION" "$REASON" > "$SUMMARY"

# Append STALL_WARNINGs for tasks idle > 60 minutes
STALL_OUTPUT=$(python3 -c "
import sys
sys.path.insert(0, '$SCRIPTS_DIR')
from neo4j_v2_core import TaskStore
s = TaskStore()
try:
    with s.driver.session() as session:
        result = session.run('''
            MATCH (t:Task {status: \"WORKING\"})
            WHERE t.lease_expires_at IS NOT NULL
              AND t.lease_expires_at < datetime()
            RETURN t.task_id AS tid, t.assigned_to AS agent
        ''')
        found = False
        for r in result:
            print(f\"STALL: {r['tid']} on {r['agent'] or '?'}\")
            found = True
        if not found:
            print('No stalled tasks')
finally:
    s.close()
" 2>>"$LOGDIR/watchdog-neo4j-errors.log" || echo "Neo4j unavailable")
if [ -n "$STALL_OUTPUT" ]; then
    echo "$STALL_OUTPUT" >> "$SUMMARY"
fi

# Check and clear orphaned agent subprocesses
SUBPROCESS_OUTPUT=$(python3 "$SCRIPTS/subprocess_health_check.py" 2>/dev/null)
if [ -n "$SUBPROCESS_OUTPUT" ]; then
    echo "$SUBPROCESS_OUTPUT" >> "$SUMMARY"
    # Also log to watchdog for tracking
    echo "[$TS] $SUBPROCESS_OUTPUT" >> "$WATCHDOG_LOG"
fi

# Append THROUGHPUT_ANOMALYs for fleet-wide throughput issues (reuse Section 6b result)
if [ -n "$THROUGHPUT_OUTPUT" ]; then
    # Write anomaly lines to summary (exclude THROUGHPUT_SEVERITY which is machine-only)
    echo "$THROUGHPUT_OUTPUT" | grep -v "^THROUGHPUT_SEVERITY:" >> "$SUMMARY"
    # Write only anomaly lines (not severity) to watchdog log
    ANOMALY_LINES=$(echo "$THROUGHPUT_OUTPUT" | grep "^THROUGHPUT_ANOMALY:")
    if [ -n "$ANOMALY_LINES" ]; then
        echo "[$TS] $ANOMALY_LINES" >> "$WATCHDOG_LOG"
    fi
    # Log severity escalation separately if present
    if [ -n "$THROUGHPUT_SEVERITY" ] && [ "$THROUGHPUT_SEVERITY" != "MEDIUM" ]; then
        echo "[$TS] THROUGHPUT_PERSIST | severity=$THROUGHPUT_SEVERITY | type=$THROUGHPUT_ANOMALY_TYPE | consecutive=$THROUGHPUT_CONSECUTIVE" >> "$WATCHDOG_LOG"
    fi
fi

# ============================================================
# WRITE 3: Append to watchdog.log (one-liner)
# ============================================================
echo "[$TS] TICK | gap_detected=$GAP_DETECTED | gap_minutes=${GAP_MINUTES:-0} | status=$STATUS | pid=$PIDS | cpu=${CPU:-0}% | mem=${MEM:-0}% | rss=${RSS_MB}MB | http=$HTTP | latency=${LATENCY_MS}ms | errors=$ERRORS_5M | neo4j=$NEO4J_STATUS | redis=$REDIS_STATUS | cloudflared=$CLOUDFLARED_STATUS cloudflared_pid=${CLOUDFLARED_PID:-none} | credentials=$CRED_HEALTH_FLEET valid=$CRED_HEALTH_VALID invalid=$CRED_HEALTH_INVALID | auth_heartbeat_failed=${AUTH_HEARTBEAT_FAILED:-0} | tasks_pending=$TASKS_PENDING_TOTAL | tasks_dispatched=$TASKS_DISPATCHED | audit_verified=$COMPLETION_AUDIT_VERIFIED | audit_fake=$COMPLETION_AUDIT_FAKE | audit_requeued=$COMPLETION_AUDIT_REQUEUED | audit_llm=$COMPLETION_AUDIT_LLM_DECISION | vote_sync_count=$VOTE_SYNC_COUNT | vote_sync_errors=$VOTE_SYNC_ERRORS | subprocess_exec=$SUBPROCESS_EXECUTING | subprocess_alive=$SUBPROCESS_ALIVE | subprocess_dead=$SUBPROCESS_DEAD | subprocess_stale=$SUBPROCESS_STALE | subprocess_anomalies=$SUBPROCESS_ANOMALIES | routing_balance=$ROUTING_BALANCE_IDX | routing_missed=$ROUTING_MISSED | routing_accuracy=$ROUTING_ACCURACY | routing_p95=$ROUTING_P95 | action=$ACTION | reason=$REASON" >> "$WATCHDOG_LOG"

# ============================================================
# SECTION 8: LLM Triage (local ollama — decide if Kublai should act)
# ============================================================
export _WD_SCRIPTS="$SCRIPTS"
LLM_TRIAGE=$(python3 << 'PYEOF'
import json, os, re, sys
sys.path.insert(0, os.environ.get("_WD_SCRIPTS", ""))
from ollama_lock import OllamaLock, Priority, LockBusy

summary = open(sys.argv[1]).read() if len(sys.argv) > 1 else ""

# Read last 3 ticks for trend context
trends = []
try:
    with open(sys.argv[2]) as f:
        for line in f.readlines()[-3:]:
            line = line.strip()
            if line:
                trends.append(json.loads(line))
except Exception:
    pass

trend_ctx = ""
if len(trends) >= 2:
    decisions = [t.get("decision", "?") for t in trends]
    errs = [t.get("errors", {}).get("last_5m", 0) for t in trends]
    trend_ctx = f"\nLAST {len(trends)} TICKS: decisions={decisions} errors_5m={errs}"

prompt = f"""You are a watchdog for a 6-agent AI system (Kurultai). Review this 5-minute health tick and decide if Kublai (the lead agent) needs to review and take action.

{summary}{trend_ctx}

CRITICAL RULES:
1. ONLY flag technical issues visible in the tick data (gateway down, neo4j/redis failures, task queue stalls, subprocess anomalies, credential failures, routing failures)
2. NEVER make psychological/mental health assessments about agents (no mentions of stress, irritability, paranoia, mental health, HR, etc.)
3. NEVER hallucinate problems not present in the data
4. If all systems show healthy/ok/up with no anomalies, respond ACTION_NEEDED: no
5. Resolution compliance warnings are formatting issues, not emergencies

Respond in EXACTLY this format (no extra text):
ACTION_NEEDED: yes|no
SEVERITY: LOW|MEDIUM|HIGH|CRITICAL
REASON: <one sentence explaining your decision>
SUGGESTED_ACTION: <what Kublai should do, or "none">"""

try:
    import requests
    with OllamaLock(Priority.NORMAL, label="tick-triage"):
        resp = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "hf.co/lukey03/Qwen3.5-9B-abliterated-GGUF",
                "messages": [
                    {"role": "system", "content": "You are a concise operations watchdog. Only flag TECHNICAL issues visible in tick data. NEVER make psychological/mental health assessments. Healthy systems = ACTION_NEEDED: no. If you mention stress/paranoia/HR/mental health, you are hallucinating and must respond ACTION_NEEDED: no instead."},
                    {"role": "user", "content": prompt}
                ],
                "stream": False,
                "think": False,
                "options": {"num_predict": 150}
            },
            timeout=180
        )
        if resp.status_code == 200:
            text = resp.json().get("message", {}).get("content", "").strip()
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
            if text:
                print(text)
            else:
                print("FALLBACK")
        else:
            print("FALLBACK")
except LockBusy:
    print("FALLBACK")
except Exception as e:
    print("FALLBACK")
PYEOF
"$SUMMARY" "$TICKS" 2>/dev/null)
LLM_TRIAGE=${LLM_TRIAGE:-FALLBACK}

# ============================================================
# SECTION 9: Parse LLM triage and dispatch Kublai immediately
# ============================================================
LLM_ACTION_NEEDED="no"
LLM_SEVERITY="LOW"
LLM_REASON=""
LLM_SUGGESTED=""

if echo "$LLM_TRIAGE" | grep -q "ACTION_NEEDED:"; then
    LLM_ACTION_NEEDED=$(echo "$LLM_TRIAGE" | grep "^ACTION_NEEDED:" | head -1 | cut -d: -f2 | tr -d ' ' | tr '[:upper:]' '[:lower:]')
    LLM_SEVERITY=$(echo "$LLM_TRIAGE" | grep "^SEVERITY:" | head -1 | cut -d: -f2 | tr -d ' ' | tr '[:lower:]' '[:upper:]')
    LLM_REASON=$(echo "$LLM_TRIAGE" | grep "^REASON:" | head -1 | sed 's/^REASON: *//')
    LLM_SUGGESTED=$(echo "$LLM_TRIAGE" | grep "^SUGGESTED_ACTION:" | head -1 | sed 's/^SUGGESTED_ACTION: *//')
fi

# HALLUCINATION FILTER: Reject psychological/mental health assessments (LLM hallucination)
if echo "$LLM_REASON $LLM_SUGGESTED" | grep -qiE "psychological|mental.health|stress|irritability|paranoia|HR|human.resources|therapy|counseling|burnout"; then
    echo "[$TS] LLM_HALLUCINATION_FILTERED | original_reason=$LLM_REASON | forced_action=no" >> "$WATCHDOG_LOG"
    LLM_ACTION_NEEDED="no"
    LLM_SEVERITY="LOW"
    LLM_REASON="LLM hallucination filtered (psychological assessment not permitted)"
    LLM_SUGGESTED="none"
fi

# DATA-VERIFICATION FILTER: Cross-check LLM assertions against actual tick data
# Prevents false alerts when LLM claims system X is down but tick summary shows X=up
# 2026-03-11: mongke research showed LLM hallucinating "Neo4j disconnected" when neo4j=up
if [ "$LLM_ACTION_NEEDED" = "yes" ]; then
    # Extract actual states from tick summary
    TICK_DATA=$(cat "$SUMMARY" 2>/dev/null)
    NEO4J_STATE=$(echo "$TICK_DATA" | grep -oE "neo4j=\S+" | cut -d= -f2)
    REDIS_STATE=$(echo "$TICK_DATA" | grep -oE "redis=\S+" | cut -d= -f2)
    GATEWAY_STATE=$(echo "$TICK_DATA" | grep -oE "gateway=\S+" | cut -d= -f2)

    # Check if LLM asserts Neo4j issue but data shows neo4j=up
    if echo "$LLM_REASON" | grep -qiE "neo4j|graph.*database|graph.*db"; then
        if [ "$NEO4J_STATE" = "up" ]; then
            echo "[$TS] LLM_DATA_VERIFICATION_FILTERED | assertion=Neo4j_down | actual_state=neo4j=up | original_reason=$LLM_REASON | forced_action=no" >> "$WATCHDOG_LOG"
            LLM_ACTION_NEEDED="no"
            LLM_SEVERITY="LOW"
            LLM_REASON="Filtered: LLM claimed Neo4j issue but tick data shows neo4j=up"
            LLM_SUGGESTED="none"
        fi
    fi

    # Check if LLM asserts Redis issue but data shows redis=up
    if echo "$LLM_REASON" | grep -qiE "redis"; then
        if [ "$REDIS_STATE" = "up" ]; then
            echo "[$TS] LLM_DATA_VERIFICATION_FILTERED | assertion=Redis_down | actual_state=redis=up | original_reason=$LLM_REASON | forced_action=no" >> "$WATCHDOG_LOG"
            LLM_ACTION_NEEDED="no"
            LLM_SEVERITY="LOW"
            LLM_REASON="Filtered: LLM claimed Redis issue but tick data shows redis=up"
            LLM_SUGGESTED="none"
        fi
    fi

    # Check if LLM asserts gateway issue but data shows gateway=up
    if echo "$LLM_REASON" | grep -qiE "gateway|down.*system|system.*down"; then
        if [ "$GATEWAY_STATE" = "up" ]; then
            echo "[$TS] LLM_DATA_VERIFICATION_FILTERED | assertion=gateway_down | actual_state=gateway=up | original_reason=$LLM_REASON | forced_action=no" >> "$WATCHDOG_LOG"
            LLM_ACTION_NEEDED="no"
            LLM_SEVERITY="LOW"
            LLM_REASON="Filtered: LLM claimed gateway issue but tick data shows gateway=up"
            LLM_SUGGESTED="none"
        fi
    fi
fi

# Log LLM triage result
echo "[$TS] TICK_LLM | action_needed=$LLM_ACTION_NEEDED | severity=$LLM_SEVERITY | reason=$LLM_REASON" >> "$WATCHDOG_LOG"

# Dispatch Kublai immediately if LLM says action needed (backgrounded)
if [ "$LLM_ACTION_NEEDED" = "yes" ]; then
    TICK_SUMMARY=$(cat "$SUMMARY")
    KUBLAI_MSG="## Tick Watchdog Alert (LLM Triage)

**Severity:** $LLM_SEVERITY
**Reason:** $LLM_REASON
**Suggested Action:** $LLM_SUGGESTED

## Current Tick Summary
\`\`\`
$TICK_SUMMARY
\`\`\`

## You Decide
Review the tick data above and take whatever action you deem appropriate.
You may:
- Investigate further (check logs, run diagnostics)
- Delegate to another agent (temujin for code fixes, ogedei for infra, jochi for debugging)
- Dismiss if the LLM overreacted (log your reasoning to ~/.openclaw/agents/main/logs/watchdog.log)
- Escalate if the situation is worse than described"

    echo "[$TS] TICK_LLM | dispatching main immediately" >> "$WATCHDOG_LOG"
    /Users/kublai/.local/bin/claude-agent \
        --message "$KUBLAI_MSG" \
        --thinking high \
        >> "$LOGDIR/tick-kublai-dispatch.log" 2>&1 &
    echo "TICK_LLM: Dispatched main (pid=$!) — severity=$LLM_SEVERITY reason=$LLM_REASON"
fi

# ============================================================
# SUSTAINED ANOMALY ESCALATION: Force-dispatch Kublai on HIGH/CRITICAL
# Bypasses LLM triage — persistent throughput stalls require deterministic response
# ============================================================
if [ "$LLM_ACTION_NEEDED" != "yes" ] && { [ "$THROUGHPUT_SEVERITY" = "HIGH" ] || [ "$THROUGHPUT_SEVERITY" = "CRITICAL" ]; }; then
    TICK_SUMMARY=$(cat "$SUMMARY")
    KUBLAI_MSG="## Sustained Throughput Anomaly — $THROUGHPUT_SEVERITY

**Anomaly:** $THROUGHPUT_ANOMALY_TYPE persisting for ${THROUGHPUT_CONSECUTIVE} consecutive ticks ($((THROUGHPUT_CONSECUTIVE * 5)) minutes)
**Severity:** $THROUGHPUT_SEVERITY (auto-escalated, LLM triage bypassed)
**Action:** $ACTION — $REASON

## Current Tick Summary
\`\`\`
$TICK_SUMMARY
\`\`\`

## Required Action
This anomaly has persisted too long for LLM triage to handle. Investigate root cause:
- If HIGH_FAILURE_RATE: Check for model misconfiguration, API outage, or credential issues
- If EXECUTING_NO_OUTPUT: Check if executing tasks are zombie processes (stale PIDs)
- If PENDING_NO_DISPATCH: Check task-executor is running and dispatching
- If QUEUE_IMBALANCE: Redistribute overloaded agent queues to idle agents
- If LOW_YIELD: Check for model execution failures or timeout patterns"

    echo "[$TS] THROUGHPUT_ESCALATION | severity=$THROUGHPUT_SEVERITY | type=$THROUGHPUT_ANOMALY_TYPE | consecutive=$THROUGHPUT_CONSECUTIVE | dispatching main" >> "$WATCHDOG_LOG"
    /Users/kublai/.local/bin/claude-agent \
        --message "$KUBLAI_MSG" \
        --thinking high \
        >> "$LOGDIR/tick-kublai-dispatch.log" 2>&1 &
    echo "THROUGHPUT_ESCALATION: Dispatched main (pid=$!) — severity=$THROUGHPUT_SEVERITY type=$THROUGHPUT_ANOMALY_TYPE consecutive=$THROUGHPUT_CONSECUTIVE"
fi

# ============================================================
# CREDENTIAL_CRISIS: Immediate escalation when ALL agents have invalid tokens
# Implements fleet-wide credential guard (2026-03-09) — escalates BEFORE error spikes
# Bypasses LLM triage — ALL agents broken is a deterministic crisis requiring human action
# ============================================================
CREDENTIAL_CRISIS_LAST_ESCALATION="$LOGDIR/.credential-crisis-last-escalation"
CREDENTIAL_CRISIS_SHOULD_ESCALATE=0

# Only escalate if ALL agents have invalid credentials AND cooldown has elapsed
if [ "$CRED_HEALTH_FLEET" = "crisis" ] && [ "$CRED_HEALTH_INVALID" -ge 7 ]; then
    # Check cooldown: only escalate if last escalation was > 60 minutes ago
    if [ -f "$CREDENTIAL_CRISIS_LAST_ESCALATION" ]; then
        LAST_ESCALATION_EPOCH=$(cat "$CREDENTIAL_CRISIS_LAST_ESCALATION" 2>/dev/null || echo "0")
        CURRENT_EPOCH=$(date '+%s')
        ESCALATION_AGE_SECONDS=$((CURRENT_EPOCH - LAST_ESCALATION_EPOCH))
        if [ "$ESCALATION_AGE_SECONDS" -gt 3600 ]; then  # 60 minutes = 3600 seconds
            CREDENTIAL_CRISIS_SHOULD_ESCALATE=1
        fi
    else
        # No previous escalation recorded
        CREDENTIAL_CRISIS_SHOULD_ESCALATE=1
    fi
fi

if [ "$CREDENTIAL_CRISIS_SHOULD_ESCALATE" -eq 1 ]; then
    # Record escalation time
    date '+%s' > "$CREDENTIAL_CRISIS_LAST_ESCALATION"

    TICK_SUMMARY=$(cat "$SUMMARY")
    CREDENTIAL_CRISIS_MSG="## CRITICAL: Fleet-Wide Credential Crisis

**Status:** ALL 7 agents have invalid API credentials
**Valid:** ${CRED_HEALTH_VALID} | **Invalid:** ${CRED_HEALTH_INVALID} | **Missing:** ${CRED_HEALTH_MISSING}

## Required Action (HUMAN INTERVENTION REQUIRED)

The fleet is DEADLOCKED — no agent can execute tasks until credentials are fixed.

1. **Obtain valid Anthropic API keys** (sk-ant- prefix) from https://console.anthropic.com/
2. **Update each agent's settings.json:**
   \`for agent in kublai temujin mongke chagatai jochi ogedei tolui; do
     vim ~/.openclaw/agents/\$agent/.claude/settings.json
   done\`
3. **Set ANTHROPIC_AUTH_TOKEN to valid sk-ant- key** (NOT DashScope sk-sp-*)
4. **Reset sessions:** \`echo '{}' > ~/.openclaw/agents/main/sessions/sessions.json\`
5. **Verify:** \`python3 scripts/credential-health-monitor.py\`

## Current Tick Summary
\`\`\`
$TICK_SUMMARY
\`\`\`

Route to: ogedei (for coordination, but requires human to fix credentials)"

    echo "[$TS] CREDENTIAL_CRISIS | fleet=$CRED_HEALTH_FLEET valid=$CRED_HEALTH_VALID invalid=$CRED_HEALTH_INVALID | dispatching main" >> "$WATCHDOG_LOG"
    /Users/kublai/.local/bin/claude-agent \
        --message "$CREDENTIAL_CRISIS_MSG" \
        --thinking high \
        >> "$LOGDIR/tick-credential-crisis-escalate.log" 2>&1 &
    echo "CREDENTIAL_CRISIS: Dispatched main (pid=$!) — ALL agents invalid, human intervention required"
fi

# ============================================================
# ERROR_RATE_ESCALATION: Auto-escalate when errors exceed threshold with rising trend
# Implements WHEN/THEN rule #2: auto-trigger when errors/hour > 75 with rising trend
# Updated 2026-03-23: Lowered threshold from 100 to 75 for earlier proactive escalation
# Bypasses LLM triage — persistent error spikes require deterministic escalation to ogedei
# ============================================================
ERROR_RATE_SHOULD_ESCALATE=0
ERROR_RATE_LAST_ESCALATION="$LOGDIR/.error-rate-last-escalation"

# Only escalate if errors_1h > 75 AND trend is rising (earlier threshold for proactive response)
if [ "$ERRORS_1H" -gt 75 ] && [ "$ERR_DIRECTION" = "rising" ]; then
    # Check cooldown: only escalate if last escalation was > 30 minutes ago
    if [ -f "$ERROR_RATE_LAST_ESCALATION" ]; then
        LAST_ESCALATION_EPOCH=$(cat "$ERROR_RATE_LAST_ESCALATION" 2>/dev/null || echo "0")
        CURRENT_EPOCH=$(date '+%s')
        ESCALATION_AGE_SECONDS=$((CURRENT_EPOCH - LAST_ESCALATION_EPOCH))
        if [ "$ESCALATION_AGE_SECONDS" -gt 1800 ]; then  # 30 minutes = 1800 seconds
            ERROR_RATE_SHOULD_ESCALATE=1
        fi
    else
        # No previous escalation recorded
        ERROR_RATE_SHOULD_ESCALATE=1
    fi
fi

if [ "$ERROR_RATE_SHOULD_ESCALATE" -eq 1 ]; then
    # Record escalation time
    date '+%s' > "$ERROR_RATE_LAST_ESCALATION"

    TICK_SUMMARY=$(cat "$SUMMARY")
    ERROR_RATE_MSG="## Critical Error Rate Escalation — ERRORS_1H=${ERRORS_1H} Rising Trend

**Error Count:** ${ERRORS_1H} errors in last hour
**Trend:** Rising (getting worse)
**5-Minute Rate:** ${ERRORS_5M} errors (current spike)
**Rolling Average:** ${ERR_AVG_5M} errors/5min

## Current Tick Summary
\`\`\`
$TICK_SUMMARY
\`\`\`

## Required Action
This error rate spike is worsening and requires immediate intervention:

1. **Check credentials** — High error rates often indicate invalid/expired API tokens
2. **Review logs** — Check ${OPENCLAW_LOG} for error patterns (auth, timeout, etc.)
3. **Fleet health** — Verify all agents have valid credentials via credential-health-monitor.py
4. **Scale back** — If load-related, consider pausing non-critical tasks

Route to: ogedei (for credential/system health investigation)"

    echo "[$TS] ERROR_RATE_ESCALATION | errors_1h=$ERRORS_1H err_dir=$ERR_DIRECTION | dispatching main" >> "$WATCHDOG_LOG"
    /Users/kublai/.local/bin/claude-agent \
        --message "$ERROR_RATE_MSG" \
        --thinking high \
        >> "$LOGDIR/tick-error-rate-escalate.log" 2>&1 &
    echo "ERROR_RATE_ESCALATION: Dispatched main (pid=$!) — errors_1h=$ERRORS_1H trend=$ERR_DIRECTION"
fi

# ============================================================
# GAP_ESCALATION: Auto-escalate when monitoring gaps detected
# Implements Rule O003: WHEN kurultai-monitor log shows >5min gap, investigate cron/launchd reliability
# Proactive escalation (reduced from 10min to 5min threshold for faster response)
# Bypasses LLM triage — monitoring blackouts are deterministic failures requiring escalation
# ============================================================
GAP_ESCALATION_SHOULD_DISPATCH=0
GAP_ESCALATION_LAST_ESCALATION="$LOGDIR/.gap-escalation-last-escalation"
GAP_ESCALATION_THRESHOLD_MINUTES=5  # Rule O003 threshold - proactive escalation (reduced from 10 for faster detection)

# Check if gap detected and exceeds threshold
if [ "$GAP_DETECTED" -eq 1 ] && [ "${GAP_MINUTES:-0}" -gt "$GAP_ESCALATION_THRESHOLD_MINUTES" ]; then
    # Determine severity based on gap size
    if [ "$GAP_MINUTES" -gt 60 ]; then
        GAP_SEVERITY="CRITICAL"
    elif [ "$GAP_MINUTES" -gt 30 ]; then
        GAP_SEVERITY="HIGH"
    elif [ "$GAP_MINUTES" -gt 15 ]; then
        GAP_SEVERITY="MEDIUM"
    else
        GAP_SEVERITY="LOW"
    fi

    # Check cooldown: only escalate if last escalation was > 15 minutes ago
    # (shorter than other escalations because gaps indicate infrastructure failure)
    if [ -f "$GAP_ESCALATION_LAST_ESCALATION" ]; then
        LAST_ESCALATION_EPOCH=$(cat "$GAP_ESCALATION_LAST_ESCALATION" 2>/dev/null || echo "0")
        CURRENT_EPOCH=$(date '+%s')
        ESCALATION_AGE_SECONDS=$((CURRENT_EPOCH - LAST_ESCALATION_EPOCH))
        if [ "$ESCALATION_AGE_SECONDS" -gt 900 ]; then  # 15 minutes = 900 seconds
            GAP_ESCALATION_SHOULD_DISPATCH=1
        fi
    else
        # No previous escalation recorded
        GAP_ESCALATION_SHOULD_DISPATCH=1
    fi
fi

if [ "$GAP_ESCALATION_SHOULD_DISPATCH" -eq 1 ]; then
    # Record escalation time
    date '+%s' > "$GAP_ESCALATION_LAST_ESCALATION"

    TICK_SUMMARY=$(cat "$SUMMARY")
    GAP_MSG="## Monitoring Gap Detected — $GAP_SEVERITY

**Gap Duration:** ${GAP_MINUTES} minutes (${GAP_MINUTES}m gap = ~$((GAP_MINUTES / 5)) missed ticks)
**Last Tick Epoch:** ${LAST_EPOCH} ($(date -r "$LAST_EPOCH" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo 'unknown'))
**Threshold:** >${GAP_ESCALATION_THRESHOLD_MINUTES} minutes triggers investigation

## Required Action

A ${GAP_MINUTES}-minute gap in watchdog execution indicates infrastructure failure:

1. **Check cron/launchd** — Verify watchdog-gather.sh is scheduled every 5 minutes
   - \`launchctl list | grep watchdog\`
   - \`crontab -l | grep watchdog\`
2. **Check for crashes** — Review system logs for watchdog crashes
   - \`log show --predicate 'process == "watchdog"' --last 1h\`
3. **Check lock file** — Verify /tmp/watchdog-gather.lock isn't stale
   - \`ls -la /tmp/watchdog-gather.lock\`
4. **Check system sleep/wake** — Mac Mini may have slept, delaying cron execution
5. **Verify OpenClaw cron** — Check if OpenClaw's local LLM scheduler is running

## Current Tick Summary
\`\`\`
$TICK_SUMMARY
\`\`\`

Route to: ogedei (for infrastructure investigation)"

    echo "[$TS] GAP_ESCALATION | gap_minutes=${GAP_MINUTES} severity=$GAP_SEVERITY last_epoch=$LAST_EPOCH | dispatching main" >> "$WATCHDOG_LOG"
    /Users/kublai/.local/bin/claude-agent \
        --message "$GAP_MSG" \
        --thinking high \
        >> "$LOGDIR/tick-gap-escalate.log" 2>&1 &
    echo "GAP_ESCALATION: Dispatched main (pid=$!) — gap=${GAP_MINUTES}m severity=$GAP_SEVERITY"
fi

# ============================================================
# AUTO-REDISTRIBUTE: Execute task redistribution on QUEUE_IMBALANCE
# Bypasses manual kublai intervention — direct action for fleet balance
# ============================================================
if [ "$THROUGHPUT_ANOMALY_TYPE" = "QUEUE_IMBALANCE" ]; then
    echo "[$TS] AUTO_REDISTRIBUTE | Triggering task-redistribute.py for QUEUE_IMBALANCE" >> "$WATCHDOG_LOG"
    REDISTRIBUTE_OUTPUT=$(python3 "$SCRIPTS/task-redistribute.py" --auto --max-move 5 2>&1)
    REDISTRIBUTE_RC=$?

    # Extract tasks moved count (rc 0 or 1 both mean script ran - 1 just means no tasks moved)
    TASKS_MOVED=$(echo "$REDISTRIBUTE_OUTPUT" | sed -nE 's/Total tasks (that would be )?moved: ([0-9]+).*/\2/p' | head -1)
    TASKS_MOVED=${TASKS_MOVED:-0}

    if [ $REDISTRIBUTE_RC -le 1 ]; then
        if [ "$TASKS_MOVED" -gt 0 ]; then
            echo "[$TS] AUTO_REDISTRIBUTE | Success — moved $TASKS_MOVED tasks from overloaded to idle agents" >> "$WATCHDOG_LOG"
            echo "AUTO_REDISTRIBUTE: Moved $TASKS_MOVED tasks (QUEUE_IMBALANCE resolved)"
        else
            echo "[$TS] AUTO_REDISTRIBUTE | No-op — no movable tasks found or no underutilized agents available" >> "$WATCHDOG_LOG"
        fi
    else
        echo "[$TS] AUTO_REDISTRIBUTE | Failed — rc=$REDISTRIBUTE_RC — $REDISTRIBUTE_OUTPUT" >> "$WATCHDOG_LOG"
        echo "AUTO_REDISTRIBUTE: Failed (rc=$REDISTRIBUTE_RC)"
    fi
fi

# ============================================================
# STALE LOCK CLEANUP: Remove orphaned session lock files
# Runs every 5 minutes to prevent "session file locked" errors
# ============================================================
# TODO(2026-03-12): system-health-check.py (cron id: 26e111ed) also calls
# stale-lock-cleanup.py every 5 min (systemEvent, no LLM cost). It adds
# git-operation-monitor.py which watchdog lacks, plus gateway/neo4j/redis/
# website HTTP checks. Overlap is CPU-only (both are systemEvent), so
# leaving both active. If consolidating later, merge git ops monitoring
# here and disable the separate cron entry.
python3 "$BASE/scripts/stale-lock-cleanup.py" --json >> "$BASE/logs/stale-lock-cleanup.log" 2>&1

# KUBLAI ACTIONS: Rule-based actions (safety net, runs alongside LLM triage)
# ============================================================
python3 "$SCRIPTS/kublai-actions.py" --trigger tick >> "$LOGDIR/kublai-actions.log" 2>&1 &

# ============================================================
# SELF-WAKE: Rule T7 — wake idle agents with blocked items (backgrounded)
# ============================================================
python3 "$SCRIPTS/agent-self-wake.py" >> "$LOGDIR/self-wake.log" 2>&1 &

# ============================================================
# MONGKE SELF-TASK: Generate research tasks when mongke queue is empty
# Runs every tick (5min) with internal 2h cooldown to prevent flooding
# Finds stale knowledge in Neo4j and generates refresh research tasks
# ============================================================
python3 "$SCRIPTS/mongke_self_task.py" --exec >> "$LOGDIR/mongke-self-task.log" 2>&1 &

# ============================================================
# GATE TIMEOUT CHECK: Monitor for stuck completion gates
# Runs every tick (5min) to check for gates stuck > 24h
# ============================================================
GATE_TIMEOUT_OUTPUT=$(python3 "$SCRIPTS/gate-timeout-watchdog.py" --json 2>/dev/null || echo '{"stuck_count":0}')
GATE_TIMEOUT_COUNT=$(echo "$GATE_TIMEOUT_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('stuck_count',0))" 2>/dev/null || echo "0")
GATE_TIMEOUT_ESCALATED=$(echo "$GATE_TIMEOUT_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('escalated_count',0))" 2>/dev/null || echo "0")

# Log timeout events
if [ "$GATE_TIMEOUT_COUNT" -gt 0 ]; then
    echo "[$TS] GATE_TIMEOUT | stuck=$GATE_TIMEOUT_COUNT | escalated=$GATE_TIMEOUT_ESCALATED" >> "$WATCHDOG_LOG"
fi

# Auto-escalate if gates are critically stuck (no escalation in last hour)
# This prevents indefinite gating while avoiding spam escalation
if [ "$GATE_TIMEOUT_COUNT" -gt 0 ]; then
    GATE_TIMEOUT_LAST_ESCALATION="$LOGDIR/.gate-timeout-last-escalation"
    SHOULD_ESCALATE=0

    if [ -f "$GATE_TIMEOUT_LAST_ESCALATION" ]; then
        LAST_ESCALATION_EPOCH=$(cat "$GATE_TIMEOUT_LAST_ESCALATION" 2>/dev/null || echo "0")
        CURRENT_EPOCH=$(date '+%s')
        ESCALATION_AGE_SECONDS=$((CURRENT_EPOCH - LAST_ESCALATION_EPOCH))
        # Only escalate if last escalation was > 1 hour ago
        if [ "$ESCALATION_AGE_SECONDS" -gt 3600 ]; then
            SHOULD_ESCALATE=1
        fi
    else
        # No previous escalation recorded
        SHOULD_ESCALATE=1
    fi

    if [ "$SHOULD_ESCALATE" -eq 1 ]; then
        # Record escalation time
        date '+%s' > "$GATE_TIMEOUT_LAST_ESCALATION"

        # Run escalation
        python3 "$SCRIPTS/gate-timeout-watchdog.py" --escalate >> "$LOGDIR/gate-timeout-escalate.log" 2>&1 &

        echo "[$TS] GATE_TIMEOUT_ESCALATE | triggered | stuck_count=$GATE_TIMEOUT_COUNT" >> "$WATCHDOG_LOG"
    fi
fi

# ============================================================
# WRITE 4: Consolidated WATCHDOG_LLM line (replaces LLM manual logging)
# ============================================================
WATCHDOG_LLM_LOG="$LOGDIR/watchdog-llm.log"
if [ "$STATUS" = "healthy" ]; then
    WATCHDOG_NOTE="nominal"
else
    WATCHDOG_NOTE="$REASON"
fi
echo "[$TS] WATCHDOG_LLM | status=$STATUS | action_needed=$LLM_ACTION_NEEDED | severity=$LLM_SEVERITY | note=$WATCHDOG_NOTE" >> "$WATCHDOG_LLM_LOG"

# ============================================================
# Output for the LLM
# ============================================================
cat "$SUMMARY"
if [ "$LLM_ACTION_NEEDED" = "yes" ]; then
    echo "LLM_TRIAGE: action_needed=yes severity=$LLM_SEVERITY reason=$LLM_REASON"
fi

exit $EXIT_CODE
