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

BASE="$HOME/.openclaw/agents/main"
LOGDIR="$BASE/logs"
TICKS="$LOGDIR/ticks.jsonl"
SUMMARY="$LOGDIR/tick-summary.txt"
WATCHDOG_LOG="$LOGDIR/watchdog.log"
OPENCLAW_LOG="$HOME/.openclaw/logs/openclaw.log"
AGENT_BASE="$BASE/agent"
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
# SECTION 3: Error Counts
# ============================================================
if [ -f "$OPENCLAW_LOG" ]; then
    ERRORS_5M=$(tail -500 "$OPENCLAW_LOG" 2>/dev/null | grep -c "ERROR\|FATAL\|CRASH" 2>/dev/null; true)
    ERRORS_1H=$(tail -5000 "$OPENCLAW_LOG" 2>/dev/null | grep -c "ERROR\|FATAL\|CRASH" 2>/dev/null; true)
    FATAL_5M=$(tail -500 "$OPENCLAW_LOG" 2>/dev/null | grep -c "FATAL\|CRASH" 2>/dev/null; true)
    ERRORS_5M=${ERRORS_5M:-0}; ERRORS_1H=${ERRORS_1H:-0}; FATAL_5M=${FATAL_5M:-0}
else
    ERRORS_5M=0; ERRORS_1H=0; FATAL_5M=0
fi

# ============================================================
# SECTION 4: Dependent Services
# ============================================================
NEO4J_STATUS=$(python3 -c "
from neo4j import GraphDatabase
try:
    d=GraphDatabase.driver('bolt://localhost:7687',auth=('neo4j','myStrongPassword123'))
    d.verify_connectivity(); print('up'); d.close()
except: print('down')
" 2>/dev/null || echo "unknown")

REDIS_STATUS=$(redis-cli ping 2>/dev/null | grep -q "PONG" && echo "up" || echo "down")

# ============================================================
# SECTION 5: Task Queue Status + Push Forward
# ============================================================
AGENTS=("temujin" "mongke" "chagatai" "jochi" "ogedei" "kublai")
TASKS_DISPATCHED=0
TASKS_PENDING_TOTAL=0
TASK_QUEUE_STATUS=""
SPAWN_COUNT=0

for agent in "${AGENTS[@]}"; do
    TASK_DIR="$AGENT_BASE/$agent/tasks"
    if [ ! -d "$TASK_DIR" ]; then
        continue
    fi

    # Count pending tasks (not .executing, not .done)
    PENDING=0
    shopt -s nullglob
    for f in "$TASK_DIR"/high-*.md "$TASK_DIR"/normal-*.md "$TASK_DIR"/low-*.md; do
        case "$f" in
            *.executing*|*.done*) continue ;;
            *) PENDING=$((PENDING + 1)) ;;
        esac
    done
    shopt -u nullglob

    TASKS_PENDING_TOTAL=$((TASKS_PENDING_TOTAL + PENDING))

    if [ "$PENDING" -gt 0 ]; then
        TASK_QUEUE_STATUS="${TASK_QUEUE_STATUS}${agent}=${PENDING},"
    fi
done

# Push forward: run task-consumer and spawn-consumer (non-blocking, backgrounded)
if [ "$TASKS_PENDING_TOTAL" -gt 0 ] || [ -f "$BASE/logs/spawn-pending.json" ]; then
    # Run task consumer for pending file-based tasks
    if [ "$TASKS_PENDING_TOTAL" -gt 0 ] && [ -x "$SCRIPTS/task-consumer.sh" ]; then
        bash "$SCRIPTS/task-consumer.sh" >> "$LOGDIR/task-consumer.log" 2>&1 &
        TASKS_DISPATCHED=$TASKS_PENDING_TOTAL
    fi

    # Run spawn consumer for spawn queue
    if [ -f "$BASE/logs/spawn-pending.json" ]; then
        SPAWN_COUNT=$(python3 -c "
import json
try:
    d=json.load(open('$BASE/logs/spawn-pending.json'))
    ready=[s for s in d.get('spawns',[]) if s.get('status')=='ready']
    print(len(ready))
except: print(0)
" 2>/dev/null || echo "0")

        if [ "$SPAWN_COUNT" -gt 0 ] && [ -x "$SCRIPTS/spawn-consumer.sh" ]; then
            bash "$SCRIPTS/spawn-consumer.sh" >> "$LOGDIR/spawn-consumer.log" 2>&1 &
            TASKS_DISPATCHED=$((TASKS_DISPATCHED + SPAWN_COUNT))
        fi
    else
        SPAWN_COUNT=0
    fi
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
    print('100.0 0.0 0 0 0')
    sys.exit(0)
n = len(ticks)
gw = [t.get('gateway',{}) for t in ticks]
up = sum(1 for g in gw if g.get('http',0) == 200)
uptime_pct = round(100.0 * up / n, 1)
avg_cpu = round(sum(t.get('process',{}).get('cpu_pct',0) for t in ticks) / n, 1)
avg_lat = round(sum(g.get('latency_ms',0) for g in gw) / n)
total_err = sum(t.get('errors',{}).get('last_5m',0) for t in ticks)
restarts = sum(1 for t in ticks if 'restart' in str(t.get('action','')))
print(f'{uptime_pct} {avg_cpu} {avg_lat} {total_err} {restarts}')
" 2>/dev/null || echo "100.0 0.0 0 0 0")
else
    TRENDS="100.0 0.0 0 0 0"
fi
UPTIME_1H=$(echo "$TRENDS" | awk '{print $1}')
AVG_CPU_1H=$(echo "$TRENDS" | awk '{print $2}')
AVG_LAT_1H=$(echo "$TRENDS" | awk '{print $3}')
ERRORS_TREND_1H=$(echo "$TRENDS" | awk '{print $4}')
RESTARTS_1H=$(echo "$TRENDS" | awk '{print $5}')

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
elif [ "$ERRORS_5M" -gt 5 ]; then
    STATUS="degraded"; ACTION="warn"; REASON="$ERRORS_5M errors in 5m"; EXIT_CODE=1
elif [ "$LATENCY_MS" -gt 2000 ] && [ "$HTTP" = "200" ]; then
    STATUS="degraded"; ACTION="warn"; REASON="latency ${LATENCY_MS}ms"; EXIT_CODE=1
elif [ "$NEO4J_STATUS" = "down" ] || [ "$REDIS_STATUS" = "down" ]; then
    STATUS="degraded"; ACTION="warn"
    REASON="services down: $([ "$NEO4J_STATUS" = "down" ] && echo neo4j)$([ "$REDIS_STATUS" = "down" ] && echo ${NEO4J_STATUS:+,}redis)"
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
printf '{"ts":"%s","epoch":%s,"gateway":{"status":"%s","pid":"%s","http":%s,"latency_ms":%s,"uptime_s":%s},"process":{"cpu_pct":%s,"mem_pct":%s,"rss_kb":%s,"threads":%s},"errors":{"last_5m":%s,"last_1h":%s,"fatal_5m":%s},"services":{"neo4j":"%s","redis":"%s"},"tasks":{"pending":%s,"dispatched":%s,"spawn_ready":%s,"queues":"%s"},"trends":{"uptime_pct_1h":%s,"avg_cpu_1h":%s,"avg_latency_1h":%s,"errors_1h":%s,"restarts_1h":%s},"decision":"%s","action":"%s","reason":"%s"}\n' \
    "$TS_ISO" "$EPOCH" "$GW_STATUS" "$PIDS" "$HTTP" "$LATENCY_MS" "${UPTIME_S:-0}" \
    "${CPU:-0}" "${MEM:-0}" "${RSS:-0}" "${THREADS:-0}" \
    "$ERRORS_5M" "$ERRORS_1H" "$FATAL_5M" \
    "$NEO4J_STATUS" "$REDIS_STATUS" \
    "$TASKS_PENDING_TOTAL" "$TASKS_DISPATCHED" "${SPAWN_COUNT:-0}" "$TASK_QUEUE_STATUS" \
    "$UPTIME_1H" "$AVG_CPU_1H" "$AVG_LAT_1H" "$ERRORS_TREND_1H" "$RESTARTS_1H" \
    "$STATUS" "$ACTION" "$REASON" >> "$TICKS"

# ============================================================
# WRITE 2: Overwrite tick-summary.txt (for LLM)
# ============================================================
cat > "$SUMMARY" << SUMEOF
TICK $TS
GATEWAY: $GW_STATUS pid=$PIDS http=$HTTP latency=${LATENCY_MS}ms uptime=$UPTIME_H
PROCESS: cpu=${CPU:-0}% mem=${MEM:-0}% rss=${RSS_MB}MB threads=${THREADS:-0}
ERRORS:  last5m=$ERRORS_5M last1h=$ERRORS_1H fatal=$FATAL_5M
SERVICES: neo4j=$NEO4J_STATUS redis=$REDIS_STATUS
TASKS:   pending=$TASKS_PENDING_TOTAL dispatched=$TASKS_DISPATCHED spawn=$SPAWN_COUNT queues=[$TASK_QUEUE_STATUS]
TRENDS:  uptime_1h=${UPTIME_1H}% avg_cpu=${AVG_CPU_1H}% errors_1h=$ERRORS_TREND_1H restarts_1h=$RESTARTS_1H
DECISION: $STATUS
ACTION:   $ACTION
REASON:   $REASON
SUMEOF

# ============================================================
# WRITE 3: Append to watchdog.log (one-liner)
# ============================================================
echo "[$TS] TICK | status=$STATUS | pid=$PIDS | cpu=${CPU:-0}% | mem=${MEM:-0}% | rss=${RSS_MB}MB | http=$HTTP | latency=${LATENCY_MS}ms | errors=$ERRORS_5M | neo4j=$NEO4J_STATUS | redis=$REDIS_STATUS | tasks_pending=$TASKS_PENDING_TOTAL | tasks_dispatched=$TASKS_DISPATCHED | action=$ACTION | reason=$REASON" >> "$WATCHDOG_LOG"

# ============================================================
# Output for the LLM
# ============================================================
cat "$SUMMARY"

exit $EXIT_CODE
