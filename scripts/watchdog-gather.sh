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

set -o pipefail

# Single-instance lock — prevents concurrent ticks (e.g., after sleep/wake catch-up)
LOCK_DIR="/tmp/watchdog-gather.lock"
_cleanup_lock() { rmdir "$LOCK_DIR" 2>/dev/null; }
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

TS=$(date '+%Y-%m-%d %H:%M:%S')
TS_ISO=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
EPOCH=$(date '+%s')

mkdir -p "$LOGDIR"

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
    --max-time 5 http://127.0.0.1:18789/health 2>/dev/null || echo "000 0")
HTTP=$(echo "$HEALTH_RESULT" | awk '{print $1}')
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
# SECTION 4: Dependent Services
# ============================================================
NEO4J_STATUS=$(python3 -c "
import signal, sys
signal.alarm(8)  # kill after 8 seconds
from neo4j import GraphDatabase
try:
    import os as _os; d=GraphDatabase.driver(_os.getenv('NEO4J_URI','bolt://localhost:7687'),auth=(_os.getenv('NEO4J_USER','neo4j'),_os.getenv('NEO4J_PASSWORD','myStrongPassword123')),connection_timeout=3,max_transaction_retry_time=3)
    d.verify_connectivity(); print('up'); d.close()
except: print('down')
" 2>/dev/null || echo "down")

REDIS_STATUS=$(redis-cli ping 2>/dev/null | grep -q "PONG" && echo "up" || echo "down")

# ============================================================
# SECTION 5: Task Queue Status + Push Forward
# ============================================================
AGENTS=("temujin" "mongke" "chagatai" "jochi" "ogedei" "main")
TASKS_DISPATCHED=0
TASKS_PENDING_TOTAL=0
TASK_QUEUE_STATUS=""
SPAWN_COUNT=0

for agent in "${AGENTS[@]}"; do
    TASK_DIR="$AGENT_BASE/$agent/tasks"
    if [ ! -d "$TASK_DIR" ]; then
        continue
    fi

    # Count pending tasks — match ALL .md files, exclude done/executing/completed/stale
    PENDING=0
    shopt -s nullglob
    for f in "$TASK_DIR"/*.md; do
        case "$f" in
            *.done*|*.executing*|*.completed*|*.stale*|*.failed*|*.obsolete*|*.cancelled*) continue ;;
            *) PENDING=$((PENDING + 1)) ;;
        esac
    done
    shopt -u nullglob

    TASKS_PENDING_TOTAL=$((TASKS_PENDING_TOTAL + PENDING))

    if [ "$PENDING" -gt 0 ]; then
        TASK_QUEUE_STATUS="${TASK_QUEUE_STATUS}${agent}=${PENDING},"
    fi
done

# task-watcher.py (launchd daemon) is the sole dispatcher for all tasks and spawns
TASKS_DISPATCHED=0
if [ -f "$BASE/logs/spawn-pending.json" ]; then
    SPAWN_COUNT=$(python3 -c "
import json
try:
    d=json.load(open('$BASE/logs/spawn-pending.json'))
    ready=[s for s in d.get('spawns',[]) if s.get('status')=='ready']
    print(len(ready))
except: print(0)
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
        except: pass
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
# SECTION 6b: Pre-decision throughput anomaly check
# ============================================================
THROUGHPUT_ANOMALY_TYPE=""
THROUGHPUT_SEVERITY=""
THROUGHPUT_CONSECUTIVE=0
THROUGHPUT_OUTPUT=$(python3 "$SCRIPTS/throughput_anomaly.py" 2>/dev/null)
if [ -n "$THROUGHPUT_OUTPUT" ]; then
    # Extract anomaly type for decision logic
    if echo "$THROUGHPUT_OUTPUT" | grep -q "PENDING_NO_DISPATCH"; then
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
elif [ "$ERRORS_1H" -gt 500 ]; then
    STATUS="degraded"; ACTION="warn"; REASON="sustained errors: $ERRORS_1H in 1h"; EXIT_CODE=1
elif [ "$ERRORS_1H" -gt 300 ] && [ "$ERR_DIRECTION" = "rising" ]; then
    STATUS="degraded"; ACTION="warn"; REASON="rising errors: $ERRORS_1H in 1h (trend: rising)"; EXIT_CODE=1
# Early warning: moderate errors with rising trend (catch before they hit 300)
elif [ "$ERRORS_1H" -gt 100 ] && [ "$ERR_DIRECTION" = "rising" ]; then
    STATUS="degraded"; ACTION="warn"; REASON="rising errors early warning: $ERRORS_1H in 1h (trend: rising)"; EXIT_CODE=1
# Spike detection: current 5m errors far above rolling average
elif [ "$ERRORS_5M" -gt 20 ] && [ -n "$ERR_AVG_5M" ] && [ "$(echo "$ERRORS_5M > $ERR_AVG_5M * 3 + 5" | bc -l 2>/dev/null)" = "1" ]; then
    STATUS="degraded"; ACTION="warn"; REASON="error spike: $ERRORS_5M in 5m (rolling avg: $ERR_AVG_5M)"; EXIT_CODE=1
elif [ "$LATENCY_MS" -gt 2000 ] && [ "$HTTP" = "200" ]; then
    STATUS="degraded"; ACTION="warn"; REASON="latency ${LATENCY_MS}ms"; EXIT_CODE=1
elif [ "$NEO4J_STATUS" = "down" ] || [ "$REDIS_STATUS" = "down" ]; then
    STATUS="degraded"; ACTION="warn"
    REASON="services down: $([ "$NEO4J_STATUS" = "down" ] && echo neo4j)$([ "$REDIS_STATUS" = "down" ] && echo ${NEO4J_STATUS:+,}redis)"
    EXIT_CODE=1
fi

# Safety-net: cross-validate decision vs error thresholds
# Catches cases where the elif chain silently missed a threshold
# Logs diagnostic info when triggered (indicates logic bypass in main chain)
if [ "$STATUS" = "healthy" ]; then
    _SAFETY_HIT=""
    if [ "${ERRORS_1H:-0}" -gt 500 ] 2>/dev/null; then
        _SAFETY_HIT="errors_1h=${ERRORS_1H}>500"
        STATUS="degraded"; ACTION="warn"; REASON="sustained errors: $ERRORS_1H in 1h (safety-net)"; EXIT_CODE=1
    elif [ "${ERRORS_5M:-0}" -gt 100 ] 2>/dev/null; then
        _SAFETY_HIT="errors_5m=${ERRORS_5M}>100"
        STATUS="degraded"; ACTION="warn"; REASON="$ERRORS_5M errors in 5m (safety-net)"; EXIT_CODE=1
    elif [ "${ERRORS_1H:-0}" -gt 300 ] && [ "$ERR_DIRECTION" = "rising" ] 2>/dev/null; then
        _SAFETY_HIT="errors_1h=${ERRORS_1H}>300+rising"
        STATUS="degraded"; ACTION="warn"; REASON="rising errors: $ERRORS_1H in 1h (safety-net)"; EXIT_CODE=1
    elif [ "${ERRORS_1H:-0}" -gt 100 ] && [ "$ERR_DIRECTION" = "rising" ] 2>/dev/null; then
        _SAFETY_HIT="errors_1h=${ERRORS_1H}>100+rising"
        STATUS="degraded"; ACTION="warn"; REASON="rising errors early warning: $ERRORS_1H in 1h (safety-net)"; EXIT_CODE=1
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

# Disk space check
AVAIL_KB=$(df -k "$LOGDIR" 2>/dev/null | awk 'NR==2{print $4}')
if [ "${AVAIL_KB:-0}" -lt 524288 ] 2>/dev/null; then  # < 512MB
    STATUS="degraded"; ACTION="warn"
    REASON="low disk: $((AVAIL_KB / 1024))MB available"
    EXIT_CODE=1
fi

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
printf '{"ts":"%s","epoch":%s,"gateway":{"status":"%s","pid":"%s","http":%s,"latency_ms":%s,"uptime_s":%s},"process":{"cpu_pct":%s,"mem_pct":%s,"rss_kb":%s,"threads":%s},"errors":{"last_5m":%s,"last_1h":%s,"fatal_5m":%s},"services":{"neo4j":"%s","redis":"%s"},"tasks":{"pending":%s,"dispatched":%s,"spawn_ready":%s,"queues":"%s"},"trends":{"uptime_pct_1h":%s,"avg_cpu_1h":%s,"avg_latency_1h":%s,"err_avg_5m":%s,"err_direction":"%s","restarts_1h":%s},"decision":"%s","action":"%s","reason":"%s"}\n' \
    "$TS_ISO" "$EPOCH" "$GW_STATUS" "$PIDS" "$HTTP" "$LATENCY_MS" "${UPTIME_S:-0}" \
    "${CPU:-0}" "${MEM:-0}" "${RSS:-0}" "${THREADS:-0}" \
    "$ERRORS_5M" "$ERRORS_1H" "$FATAL_5M" \
    "$NEO4J_STATUS" "$REDIS_STATUS" \
    "$TASKS_PENDING_TOTAL" "$TASKS_DISPATCHED" "${SPAWN_COUNT:-0}" "$TASK_QUEUE_STATUS" \
    "$UPTIME_1H" "$AVG_CPU_1H" "$AVG_LAT_1H" "$ERR_AVG_5M" "$ERR_DIRECTION" "$RESTARTS_1H" \
    "$STATUS" "$ACTION" "$REASON" >> "$TICKS"

# ============================================================
# WRITE 2: Overwrite tick-summary.txt (for LLM)
# ============================================================
printf 'TICK %s\nGATEWAY: %s pid=%s http=%s latency=%sms uptime=%s\nPROCESS: cpu=%s%% mem=%s%% rss=%sMB threads=%s\nERRORS:  last5m=%s last1h=%s fatal=%s\nSERVICES: neo4j=%s redis=%s\nTASKS:   pending=%s dispatched=%s spawn=%s queues=[%s]\nTRENDS:  uptime_1h=%s%% avg_cpu=%s%% err_avg_5m=%s err_direction=%s restarts_1h=%s\nDECISION: %s\nACTION:   %s\nREASON:   %s\n' \
    "$TS" "$GW_STATUS" "$PIDS" "$HTTP" "$LATENCY_MS" "$UPTIME_H" \
    "${CPU:-0}" "${MEM:-0}" "$RSS_MB" "${THREADS:-0}" \
    "$ERRORS_5M" "$ERRORS_1H" "$FATAL_5M" \
    "$NEO4J_STATUS" "$REDIS_STATUS" \
    "$TASKS_PENDING_TOTAL" "$TASKS_DISPATCHED" "$SPAWN_COUNT" "$TASK_QUEUE_STATUS" \
    "$UPTIME_1H" "$AVG_CPU_1H" "$ERR_AVG_5M" "$ERR_DIRECTION" "$RESTARTS_1H" \
    "$STATUS" "$ACTION" "$REASON" > "$SUMMARY"

# Append STALL_WARNINGs for tasks idle > 60 minutes
STALL_OUTPUT=$(python3 "$SCRIPTS/stall_detector.py" 2>/dev/null)
if [ -n "$STALL_OUTPUT" ]; then
    echo "$STALL_OUTPUT" >> "$SUMMARY"
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
echo "[$TS] TICK | status=$STATUS | pid=$PIDS | cpu=${CPU:-0}% | mem=${MEM:-0}% | rss=${RSS_MB}MB | http=$HTTP | latency=${LATENCY_MS}ms | errors=$ERRORS_5M | neo4j=$NEO4J_STATUS | redis=$REDIS_STATUS | tasks_pending=$TASKS_PENDING_TOTAL | tasks_dispatched=$TASKS_DISPATCHED | action=$ACTION | reason=$REASON" >> "$WATCHDOG_LOG"

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
                    {"role": "system", "content": "You are a concise operations watchdog. Only flag things that genuinely need human/lead-agent attention. Healthy systems with no anomalies should get ACTION_NEEDED: no."},
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
    /opt/homebrew/bin/openclaw agent --agent main \
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
- If EXECUTING_NO_OUTPUT: Check if executing tasks are zombie processes (stale PIDs)
- If PENDING_NO_DISPATCH: Check task-watcher is running and dispatching
- If QUEUE_IMBALANCE: Redistribute overloaded agent queues to idle agents
- If LOW_YIELD: Check for model execution failures or timeout patterns"

    echo "[$TS] THROUGHPUT_ESCALATION | severity=$THROUGHPUT_SEVERITY | type=$THROUGHPUT_ANOMALY_TYPE | consecutive=$THROUGHPUT_CONSECUTIVE | dispatching main" >> "$WATCHDOG_LOG"
    /opt/homebrew/bin/openclaw agent --agent main \
        --message "$KUBLAI_MSG" \
        --thinking high \
        >> "$LOGDIR/tick-kublai-dispatch.log" 2>&1 &
    echo "THROUGHPUT_ESCALATION: Dispatched main (pid=$!) — severity=$THROUGHPUT_SEVERITY type=$THROUGHPUT_ANOMALY_TYPE consecutive=$THROUGHPUT_CONSECUTIVE"
fi

# ============================================================
# KUBLAI ACTIONS: Rule-based actions (safety net, runs alongside LLM triage)
# ============================================================
python3 "$SCRIPTS/kublai-actions.py" --trigger tick >> "$LOGDIR/kublai-actions.log" 2>&1 &

# ============================================================
# SELF-WAKE: Rule T7 — wake idle agents with blocked items (backgrounded)
# ============================================================
python3 "$SCRIPTS/agent-self-wake.py" >> "$LOGDIR/self-wake.log" 2>&1 &

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
