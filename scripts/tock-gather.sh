#!/bin/bash
# tock-gather.sh — 30-minute agent effectiveness data collection
# Collects agent-level and system-level metrics for hourly kurultai-reflection.
# Bash does 90% of work. LLM makes a brief workload assessment via direct API call.
#
# Outputs:
#   - tock/<date>/<time>.json  (full snapshot)
#   - tock/latest.json         (symlink to most recent)
#   - tock.log                 (one-liner per tock)

set -o pipefail

# Single-instance lock — prevents concurrent tocks (e.g., after sleep/wake catch-up)
LOCK_DIR="/tmp/tock-gather.lock"
_cleanup_lock() { rmdir "$LOCK_DIR" 2>/dev/null; }
trap _cleanup_lock EXIT

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    if [ -f "$LOCK_DIR/pid" ]; then
        OLD_PID=$(cat "$LOCK_DIR/pid" 2>/dev/null)
        if [ -n "$OLD_PID" ] && ! kill -0 "$OLD_PID" 2>/dev/null; then
            rmdir "$LOCK_DIR" 2>/dev/null || rm -rf "$LOCK_DIR"
            mkdir "$LOCK_DIR" 2>/dev/null || { echo "[$(date '+%Y-%m-%d %H:%M:%S')] TOCK | SKIP: lock contention" >> "/Users/kublai/.openclaw/agents/main/logs/tock.log"; exit 0; }
        else
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] TOCK | SKIP: already running (pid=$OLD_PID)" >> "/Users/kublai/.openclaw/agents/main/logs/tock.log"
            exit 0
        fi
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] TOCK | SKIP: already running" >> "/Users/kublai/.openclaw/agents/main/logs/tock.log"
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

BASE="/Users/kublai/.openclaw/agents/main"
TOCK_DIR="$BASE/logs/tock"
TOCK_LOG="$BASE/logs/tock.log"

DATE=$(date +%Y-%m-%d)
TIME=$(date +%H-%M)
TS=$(date '+%Y-%m-%d %H:%M:%S')
TS_ISO=$(date '+%Y-%m-%dT%H:%M:%S%z')

OUTDIR="$TOCK_DIR/$DATE"
OUTFILE="$OUTDIR/$TIME.json"
LATEST="$TOCK_DIR/latest.json"

mkdir -p "$OUTDIR"

# ============================================================
# 1. Neo4j: Per-agent task metrics + delegations + errors
# ============================================================
NEO4J_DATA=$(python3 2>/dev/null << 'PYEOF'
import json, signal, sys
signal.alarm(30)  # kill after 30 seconds

results = {"_failed_queries": []}  # Track which queries failed for diagnostics

def run_query(session, query, name):
    """Task 6.2: Run a Neo4j query with graceful degradation - returns [] on failure."""
    try:
        r = session.run(query)
        return [dict(rec) for rec in r]
    except Exception as e:
        results["_failed_queries"].append(f"{name}: {str(e)[:100]}")
        print(f"Neo4j query failed ({name}): {e}", file=sys.stderr)
        return []

try:
    from neo4j import GraphDatabase
    import os as _os
    driver = GraphDatabase.driver(
        _os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(_os.getenv("NEO4J_USER", "neo4j"), _os.getenv("NEO4J_PASSWORD", "myStrongPassword123")),
        connection_timeout=5, max_transaction_retry_time=5
    )
    with driver.session() as session:
        # Per-agent tasks (30m)
        results["agent_tasks"] = run_query(session, """
            MATCH (t:Task)
            WHERE t.created > datetime() - duration('PT30M')
            WITH t.agent AS agent,
                 count(t) AS total,
                 sum(CASE WHEN toUpper(t.status) = 'COMPLETED' THEN 1 ELSE 0 END) AS completed,
                 sum(CASE WHEN toUpper(t.status) = 'FAILED' THEN 1 ELSE 0 END) AS failed,
                 sum(CASE WHEN toUpper(t.status) IN ['READY','QUEUED','PENDING'] THEN 1 ELSE 0 END) AS pending,
                 sum(CASE WHEN toUpper(t.status) IN ['RUNNING','EXECUTING','IN_PROGRESS'] THEN 1 ELSE 0 END) AS running,
                 coalesce(sum(t.retry_count),0) AS retries
            RETURN agent, total, completed, failed, pending, running, retries
        """, "agent_tasks")

        # Model usage stats (30m)
        results["model_stats"] = run_query(session, """
            MATCH (t:Task)
            WHERE t.created > datetime() - duration('PT30M')
              AND t.model_id IS NOT NULL
            WITH
                t.model_id AS model,
                t.model_provider AS provider,
                count(t) AS total,
                sum(CASE WHEN t.model_success = true THEN 1 ELSE 0 END) AS success,
                coalesce(avg(t.model_duration_seconds), 0) AS avg_duration
            RETURN
                model,
                provider,
                total,
                success,
                CASE WHEN total > 0 THEN round(100.0 * success / total, 1) ELSE 0.0 END AS success_rate,
                round(avg_duration, 1) AS avg_duration
        """, "model_stats")

        # Per-agent model breakdown (30m)
        results["agent_model_stats"] = run_query(session, """
            MATCH (t:Task)
            WHERE t.created > datetime() - duration('PT30M')
              AND t.model_id IS NOT NULL
            WITH
                t.agent AS agent,
                t.model_id AS model,
                count(t) AS total,
                sum(CASE WHEN t.model_success = true THEN 1 ELSE 0 END) AS success
            RETURN
                agent,
                model,
                total,
                success,
                CASE WHEN total > 0 THEN round(100.0 * success / total, 1) ELSE 0.0 END AS success_rate
            ORDER BY agent, total DESC
        """, "agent_model_stats")

        # Delegations (30m)
        results["delegations"] = run_query(session, """
            MATCH (t:Task)
            WHERE t.created > datetime() - duration('PT30M')
              AND t.source IS NOT NULL AND t.source <> t.agent
            RETURN t.source AS from_agent, t.agent AS to_agent,
                   t.label AS task_label
            LIMIT 20
        """, "delegations")

        # Error clusters (30m)
        results["error_clusters"] = run_query(session, """
            MATCH (t:Task)
            WHERE t.created > datetime() - duration('PT30M')
              AND toUpper(t.status) = 'FAILED' AND t.error IS NOT NULL
            RETURN t.error AS error, count(t) AS count,
                   collect(DISTINCT t.agent) AS agents
            ORDER BY count DESC LIMIT 10
        """, "error_clusters")

    driver.close()
    print(json.dumps(results, default=str))
except Exception as e:
    # Graceful degradation: return partial data with error info
    results["_error"] = str(e)[:200]
    results["_partial"] = True
    print(json.dumps(results, default=str))
PYEOF
)
NEO4J_DATA=${NEO4J_DATA:-'{"error":"neo4j_unavailable"}'}

# ============================================================
# 2. Session usage from gateway
# ============================================================
SESSION_DATA=$(timeout 15 openclaw gateway call status --json 2>/dev/null || echo '{}')

# ============================================================
# 3. Cron job health (generic from jobs.json)
# ============================================================
CRON_DATA=$(python3 2>/dev/null << 'PYEOF'
import json
try:
    with open("/Users/kublai/.openclaw/cron/jobs.json") as f:
        data = json.load(f)
    jobs = data.get("jobs", [])
    healthy = erroring = 0
    job_list = []
    for job in jobs:
        state = job.get("state", {})
        consec = state.get("consecutiveErrors", 0)
        last_run = state.get("lastRunAtMs")
        running = state.get("runningAtMs")
        # Skip disabled jobs from counts
        if not job.get("enabled", False):
            continue
        # Jobs that have never run (scheduled for future) are not errors
        if last_run is None and running is None:
            continue
        if state.get("lastRunStatus") == "ok" and consec == 0:
            healthy += 1
        else:
            erroring += 1
        job_list.append({
            "name": job.get("name", "?"),
            "status": state.get("lastRunStatus", "unknown"),
            "consecutive_errors": consec,
            "last_duration_ms": state.get("lastDurationMs", 0),
            "enabled": job.get("enabled", False)
        })
    print(json.dumps({"total_jobs": len(jobs), "healthy": healthy, "erroring": erroring, "jobs": job_list}))
except Exception as e:
    # Graceful degradation: return partial data with error info
    results["_error"] = str(e)[:200]
    results["_partial"] = True
    print(json.dumps(results, default=str))
PYEOF
)
CRON_DATA=${CRON_DATA:-'{"total_jobs":0,"healthy":0,"erroring":0,"jobs":[]}'}

# ============================================================
# 3b. Specific cron job monitoring - calendar_reminder and backup
# ============================================================
CRON_JOBS=$(python3 2>/dev/null << 'PYEOF'
import json
import os
from datetime import datetime, timedelta

now = datetime.now()
result = {
    "calendar_reminder": {
        "status": "unknown",
        "last_run": None,
        "ran_last_5min": False,
        "error_log_exists": False,
        "error_log_lines_24h": 0
    },
    "backup": {
        "status": "unknown",
        "last_backup": None,
        "ran_last_24h": False,
        "backup_file_exists": False,
        "latest_backup_size": None
    }
}

# --- Calendar Reminder Worker ---
# Check log file: ~/.openclaw/logs/calendar_reminders.log
log_file = os.path.expanduser("~/.openclaw/logs/calendar_reminders.log")
if os.path.exists(log_file):
    result["calendar_reminder"]["error_log_exists"] = True
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
        # Find most recent entry
        recent_lines = []
        cutoff_5min = now - timedelta(minutes=5)
        cutoff_24h = now - timedelta(hours=24)

        for line in lines:
            # Parse timestamp from format: [2026-03-07T09:05:12.123456] message
            if line.startswith('['):
                try:
                    ts_end = line.index(']')
                    ts_str = line[1:ts_end]
                    ts = datetime.fromisoformat(ts_str)
                    if ts > cutoff_5min:
                        recent_lines.append(line)
                    if ts > cutoff_24h:
                        result["calendar_reminder"]["error_log_lines_24h"] += 1
                        # Track most recent
                        if result["calendar_reminder"]["last_run"] is None:
                            result["calendar_reminder"]["last_run"] = ts.isoformat()
                except (ValueError, IndexError):
                    pass

        result["calendar_reminder"]["ran_last_5min"] = len(recent_lines) > 0
        if result["calendar_reminder"]["last_run"] is None and lines:
            # Fallback: use last line timestamp
            try:
                last_line = lines[-1]
                if last_line.startswith('['):
                    ts_end = last_line.index(']')
                    ts_str = last_line[1:ts_end]
                    result["calendar_reminder"]["last_run"] = datetime.fromisoformat(ts_str).isoformat()
            except (ValueError, IndexError):
                pass
    except Exception:
        pass

# Determine calendar_reminder status
if result["calendar_reminder"]["ran_last_5min"]:
    result["calendar_reminder"]["status"] = "ok"
elif result["calendar_reminder"]["error_log_exists"]:
    result["calendar_reminder"]["status"] = "stale"
else:
    result["calendar_reminder"]["status"] = "no_log"

# --- Backup Job ---
# Check backup directory: /tmp/openclaw-backups/
backup_dir = "/tmp/openclaw-backups"
if os.path.isdir(backup_dir):
    try:
        backups = [f for f in os.listdir(backup_dir) if f.startswith("openclaw-backup_") and f.endswith(".tar.gz")]
        if backups:
            # Sort by modification time
            backups_with_time = []
            for b in backups:
                full_path = os.path.join(backup_dir, b)
                mtime = os.path.getmtime(full_path)
                backups_with_time.append((b, mtime, os.path.getsize(full_path)))
            backups_with_time.sort(key=lambda x: x[1], reverse=True)

            latest = backups_with_time[0]
            latest_time = datetime.fromtimestamp(latest[1])
            result["backup"]["last_backup"] = latest_time.isoformat()
            result["backup"]["latest_backup_size"] = latest[2]
            result["backup"]["backup_file_exists"] = True
            result["backup"]["ran_last_24h"] = (now - latest_time) < timedelta(hours=24)
    except Exception:
        pass

# Determine backup status
if result["backup"]["ran_last_24h"]:
    result["backup"]["status"] = "ok"
elif result["backup"]["backup_file_exists"]:
    result["backup"]["status"] = "stale"
else:
    result["backup"]["status"] = "no_backup"

print(json.dumps(result))
PYEOF
)
CRON_JOBS=${CRON_JOBS:-'{"calendar_reminder":{"status":"unknown","error_log_exists":false},"backup":{"status":"unknown","backup_file_exists":false}}'}

# ============================================================
# 4. Task queue depths (file-based)
# Task 6.1: oldest_age_s returns 0 for empty queues (not null)
# ============================================================
QUEUE_DATA=$(python3 2>/dev/null << 'PYEOF'
import json, os, glob, time
base = "/Users/kublai/.openclaw/agents"
queues = {}
oldest_ages = {}
now = time.time()
for agent in ["kublai","mongke","chagatai","temujin","jochi","ogedei"]:
    task_dir = f"{base}/{agent}/tasks"
    if not os.path.isdir(task_dir):
        queues[agent] = 0
        # Task 6.1: Return 0 (no tasks) not None (measurement failure) for missing task dir
        oldest_ages[agent] = 0  # Missing task dir = no tasks, not measurement error
        continue
    pending = 0
    oldest_age_s = 0  # Default: 0 means no pending tasks (distinguishes from measurement failure)
    for pattern in ["high-*.md", "normal-*.md", "low-*.md"]:
        for f in glob.glob(f"{task_dir}/{pattern}"):
            if ".executing" not in f and ".done" not in f:
                pending += 1
                try:
                    age = now - os.path.getmtime(f)
                    if age > oldest_age_s:  # oldest_age_s starts at 0 for empty queue
                        oldest_age_s = age
                except:
                    pass
    queues[agent] = pending
    oldest_ages[agent] = round(oldest_age_s)  # Returns 0 when queue empty (not null)
print(json.dumps({"queues": queues, "oldest_age_s": oldest_ages}))
PYEOF
)
QUEUE_DATA=${QUEUE_DATA:-'{}'}

# ============================================================
# 4a. Config model resolution (ground truth vs stale sessions)
# ============================================================
CONFIG_MODELS=$(python3 2>/dev/null << 'PYEOF'
import json, os
base = "/Users/kublai/.openclaw/agents"
VALID_MODELS = {'claude-opus-4-6', 'claude-sonnet-4-6', 'claude-haiku-4-5-20251001', 'kimi-k2.5', 'glm-5'}
DEFAULT_MODEL = 'claude-opus-4-6'
result = {}
for agent in ["kublai","mongke","chagatai","temujin","jochi","ogedei"]:
    model = None
    source = "default"
    # Layer 1: config.json model key
    try:
        with open(f"{base}/{agent}/config.json") as f:
            cfg = json.load(f)
            m = cfg.get("model")
            if m:
                model = m
                source = "config.json"
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    # Layer 2: .claude/settings.json ANTHROPIC_MODEL
    if not model:
        try:
            with open(f"{base}/{agent}/.claude/settings.json") as f:
                settings = json.load(f)
                m = settings.get("env", {}).get("ANTHROPIC_MODEL")
                if m:
                    model = m
                    source = "settings.json"
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    resolved = model if model and model in VALID_MODELS else DEFAULT_MODEL
    valid = model is None or model in VALID_MODELS
    result[agent] = {"configured": model, "resolved": resolved, "source": source, "valid": valid}
print(json.dumps(result))
PYEOF
)
CONFIG_MODELS=${CONFIG_MODELS:-'{}'}

# Spawn queue
SPAWN_COUNT=$(python3 -c "
import json,os
f='/Users/kublai/.openclaw/agents/main/logs/spawn-pending.json'
if os.path.exists(f):
    d=json.load(open(f))
    print(len([s for s in d.get('spawns',[]) if s.get('status')=='ready']))
else: print(0)
" 2>/dev/null || echo "0")

# ============================================================
# 4b. Queue audit — read from ogedei-watchdog state (fallback: run inline)
# ============================================================
WATCHDOG_STATE="$BASE/logs/ogedei-watchdog-state.json"
QUEUE_AUDIT=$(python3 2>/dev/null << 'PYEOF'
import json, os, time
state_file = os.environ.get("_WD_STATE", "/Users/kublai/.openclaw/agents/main/logs/ogedei-watchdog-state.json")
try:
    with open(state_file) as f:
        state = json.load(f)
    last_audit = state.get("last_audit", 0)
    if (time.time() - last_audit) < 2100:  # 35 min — watchdog is fresh
        print(json.dumps(state.get("audit_result", {"audited":0,"fake_found":0,"requeued":0,"skipped":0})))
    else:
        raise ValueError("stale")
except:
    # Fallback: run queue-audit.py inline
    import sys, importlib.util
    spec = importlib.util.spec_from_file_location("queue_audit", "/Users/kublai/.openclaw/agents/main/scripts/queue-audit.py")
    qa = importlib.util.module_from_spec(spec)
    sys.argv = ["queue-audit.py", "--json"]
    spec.loader.exec_module(qa)
    totals, _ = qa.audit()
    print(json.dumps(totals))
PYEOF
)
QUEUE_AUDIT=${QUEUE_AUDIT:-'{"audited":0,"fake_found":0,"requeued":0,"skipped":0}'}

# ============================================================
# 4b. Stale lock detection — scan all agent task directories for .pid files
# ============================================================
STALE_LOCKS=$(python3 2>/dev/null << 'PYEOF'
import json, os, glob, time, subprocess
base = "/Users/kublai/.openclaw/agents"
agents = ["kublai","mongke","chagatai","temujin","jochi","ogedei","tolui"]
now = time.time()
stale_locks = []
by_agent = {}

for agent in agents:
    task_dir = f"{base}/{agent}/tasks"
    if not os.path.isdir(task_dir):
        continue
    by_agent[agent] = 0
    # Find all .executing.pid files
    for pid_file in glob.glob(f"{task_dir}/*.executing.pid"):
        try:
            with open(pid_file, 'r') as f:
                lines = f.readlines()
                if not lines:
                    continue
                pid = lines[0].strip()
                if not pid.isdigit():
                    continue
                pid = int(pid)
            # Check if process is alive
            result = subprocess.run(['ps', '-p', str(pid)], capture_output=True, text=True)
            is_alive = str(pid) in result.stdout
            # Calculate age
            age_seconds = int(now - os.path.getmtime(pid_file))
            if not is_alive:
                task_file = os.path.basename(pid_file).replace('.executing.pid', '')
                stale_locks.append({
                    "agent": agent,
                    "task_file": task_file,
                    "pid": pid,
                    "age_seconds": age_seconds
                })
                by_agent[agent] += 1
        except (OSError, ValueError, subprocess.SubprocessError):
            pass

output = {
    "total": len(stale_locks),
    "by_agent": by_agent,
    "details": stale_locks
}
print(json.dumps(output))
PYEOF
)
STALE_LOCKS=${STALE_LOCKS:-'{"total":0,"by_agent":{},"details":[]}'}

# ============================================================
# 4c. Ledger completions (30m) — for reconciliation against Neo4j
# ============================================================
LEDGER_DATA=$(python3 2>/dev/null << 'PYEOF'
import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ledger_path = Path.home() / ".openclaw" / "tasks" / "task-ledger.jsonl"
cutoff = datetime.now() - timedelta(minutes=30)
agents = ["kublai","mongke","chagatai","temujin","jochi","ogedei"]
completed = {a: 0 for a in agents}
failed = {a: 0 for a in agents}

if ledger_path.exists():
    try:
        with open(ledger_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    ts_str = ev.get("ts", "")
                    if not ts_str:
                        continue
                    try:
                        ev_time = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if ev_time.tzinfo is not None:
                            ev_time = ev_time.replace(tzinfo=None)
                        if ev_time < cutoff:
                            continue
                    except (ValueError, TypeError):
                        continue
                    agent = ev.get("agent", "")
                    event = ev.get("event", "")
                    if agent in completed and event == "COMPLETED":
                        completed[agent] += 1
                    elif agent in failed and event == "FAILED":
                        failed[agent] += 1
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

print(json.dumps({"completed": completed, "failed": failed}))
PYEOF
)
LEDGER_DATA=${LEDGER_DATA:-'{"completed":{},"failed":{}}'}

# ============================================================
# 4d. Routing Metrics (from routing-metrics.sh or latest hourly file)
# ============================================================
ROUTING_METRICS=$(python3 2>/dev/null << 'PYEOF'
import json, os, glob
from datetime import datetime, timedelta

logs_dir = "/Users/kublai/.openclaw/agents/main/logs"

# Try to read the most recent hourly routing metrics file
try:
    pattern = os.path.join(logs_dir, "routing-metrics-*.json")
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    if files:
        # Use the most recent file (within last 2 hours to be relevant)
        latest_file = files[0]
        file_age = datetime.now().timestamp() - os.path.getmtime(latest_file)
        if file_age < 7200:  # 2 hours
            with open(latest_file) as f:
                data = json.load(f)
            # Extract key metrics
            routing = data.get("routing", {})
            queue_balance = data.get("queue_balance", {})
            print(json.dumps({
                "queue_balance_index": queue_balance.get("index", 0),
                "queue_depths": queue_balance.get("depths", {}),
                "missed_opportunities": routing.get("missed_opportunities", 0),
                "routing_accuracy": routing.get("routing_accuracy", 0),
                "time_to_start_p95": routing.get("time_to_start_p95_seconds", 0),
                "total_routed": routing.get("total_routed", 0),
                "overflow_count": routing.get("overflow_count", 0),
                "source": "file",
                "file_age_minutes": int(file_age / 60)
            }))
        else:
            # File too old, compute fresh metrics
            raise ValueError("stale_file")
    else:
        raise ValueError("no_file")
except Exception:
    # Fallback: compute queue balance index from current queue state
    import statistics
    base = "/Users/kublai/.openclaw/agents"
    agents = ["temujin", "mongke", "chagatai", "jochi", "ogedei"]
    depths = []
    depth_map = {}
    for agent in agents:
        task_dir = f"{base}/{agent}/tasks"
        if os.path.isdir(task_dir):
            import glob
            pending = 0
            for f in glob.glob(f"{task_dir}/*.md"):
                if any(x in f for x in ['.done', '.executing', '.completed', '.stale', '.failed']):
                    continue
                pending += 1
            depth_map[agent] = pending
            depths.append(pending)
        else:
            depth_map[agent] = 0
            depths.append(0)

    mean_depth = statistics.mean(depths) if depths else 0
    std_depth = statistics.stdev(depths) if len(depths) > 1 else 0
    balance_index = round(std_depth / mean_depth, 3) if mean_depth > 0 else 0

    print(json.dumps({
        "queue_balance_index": balance_index,
        "queue_depths": depth_map,
        "missed_opportunities": 0,
        "routing_accuracy": 0.87,  # Default
        "time_to_start_p95": 420,  # Default
        "total_routed": 0,
        "overflow_count": 0,
        "source": "computed",
        "file_age_minutes": None
    }))
PYEOF
)
ROUTING_METRICS=${ROUTING_METRICS:-'{"queue_balance_index":0,"missed_opportunities":0,"routing_accuracy":0.87,"time_to_start_p95":420}'}

# ============================================================
# 4e. Subprocess Audit (claude-agent process correlation)
# ============================================================
# Audit active claude-agent processes and correlate with executing tasks
SUBPROCESS_AUDIT=$(python3 "$BASE/scripts/subprocess-audit.py" --json 2>/dev/null || echo '{}')

# ============================================================
# 5. Last tick status + service health (from TICK lines, not TICK_LLM)
# ============================================================
LAST_TICK_LINE=$(tail -20 "$BASE/logs/watchdog.log" 2>/dev/null | grep "] TICK |" | grep -v "TICK_LLM" | tail -1; true)
TICK_STATUS=$(echo "$LAST_TICK_LINE" | grep -o "status=[a-z]*" | cut -d= -f2; true)
TICK_STATUS=${TICK_STATUS:-unknown}
TICK_NEO4J=$(echo "$LAST_TICK_LINE" | grep -o "neo4j=[a-z]*" | cut -d= -f2; true)
TICK_NEO4J=${TICK_NEO4J:-unknown}
TICK_REDIS=$(echo "$LAST_TICK_LINE" | grep -o "redis=[a-z]*" | cut -d= -f2; true)
TICK_REDIS=${TICK_REDIS:-unknown}

# ============================================================
# 6. Assemble full JSON (via temp files to avoid heredoc escaping issues)
# ============================================================
TOCK_TMP=$(mktemp -d)
echo "$NEO4J_DATA" > "$TOCK_TMP/neo4j.json"
echo "$SESSION_DATA" > "$TOCK_TMP/session.json"
echo "$CRON_DATA" > "$TOCK_TMP/cron.json"
echo "$CRON_JOBS" > "$TOCK_TMP/cron_jobs.json"
echo "$QUEUE_DATA" > "$TOCK_TMP/queues.json"
echo "$QUEUE_AUDIT" > "$TOCK_TMP/queue_audit.json"
echo "$LEDGER_DATA" > "$TOCK_TMP/ledger.json"
echo "$CONFIG_MODELS" > "$TOCK_TMP/config_models.json"
echo "$STALE_LOCKS" > "$TOCK_TMP/stale_locks.json"
echo "$ROUTING_METRICS" > "$TOCK_TMP/routing.json"
echo "$SUBPROCESS_AUDIT" > "$TOCK_TMP/subprocess.json"

ASSEMBLED=$(python3 << PYEOF
import json, os, sys

tmp = "$TOCK_TMP"

def safe_load(path, default):
    try:
        with open(path) as f:
            return json.loads(f.read().strip())
    except:
        return default

neo4j = safe_load(f"{tmp}/neo4j.json", {"error":"parse_failed"})
cron = safe_load(f"{tmp}/cron.json", {"total_jobs":0,"healthy":0,"erroring":0,"jobs":[]})
cron_jobs = safe_load(f"{tmp}/cron_jobs.json", {})
queues = safe_load(f"{tmp}/queues.json", {})
config_models = safe_load(f"{tmp}/config_models.json", {})
queue_audit = safe_load(f"{tmp}/queue_audit.json", {"audited":0,"fake_found":0,"requeued":0,"skipped":0})
ledger = safe_load(f"{tmp}/ledger.json", {"completed":{},"failed":{}})
stale_locks = safe_load(f"{tmp}/stale_locks.json", {"total":0,"by_agent":{},"details":[]})
routing = safe_load(f"{tmp}/routing.json", {
    "queue_balance_index": 0,
    "missed_opportunities": 0,
    "routing_accuracy": 0.87,
    "time_to_start_p95": 420,
    "queue_depths": {}
})
subprocess_audit = safe_load(f"{tmp}/subprocess.json", {
    "summary": {"total_executing": 0, "alive": 0, "dead": 0, "stale": 0, "anomaly_count": 0},
    "anomalies": [],
    "executing_tasks": []
})

# Parse session data
session = safe_load(f"{tmp}/session.json", {})

agent_names = ["kublai","mongke","chagatai","temujin","jochi","ogedei"]

# Build per-agent data
task_by_agent = {}
if "agent_tasks" in neo4j:
    for row in neo4j["agent_tasks"]:
        task_by_agent[row.get("agent","")] = row

session_by_agent = {}
if "sessions" in session:
    for a in session.get("sessions",{}).get("byAgent",[]):
        aid = a.get("agentId","")
        recent = a.get("recent",[{}])[0] if a.get("recent") else {}
        session_by_agent[aid] = {
            "count": a.get("count",0),
            "pct_used": recent.get("percentUsed",0),
            "model": recent.get("model","unknown")
        }

agents = {}
for name in agent_names:
    t = task_by_agent.get(name, {})
    s = session_by_agent.get(name, {})
    total = t.get("total", 0)
    completed = t.get("completed", 0)
    cm = config_models.get(name, {})
    session_model = s.get("model", "none") if s else "none"
    config_resolved = cm.get("resolved", "claude-opus-4-6")
    model_match = session_model == "none" or session_model == config_resolved
    agents[name] = {
        "tasks": {
            "completed": completed, "failed": t.get("failed",0),
            "pending": t.get("pending",0), "running": t.get("running",0),
            "total": total, "queue_depth": queues.get(name,0)
        },
        "success_rate": round(100.0*completed/total,1) if total > 0 else None,
        "retries": t.get("retries",0),
        "session": s if s else {"count":0,"pct_used":0,"model":"none"},
        "config_model": {
            "resolved": config_resolved,
            "source": cm.get("source", "default"),
            "valid": cm.get("valid", True),
            "session_match": model_match
        }
    }

queue_total = sum(queues.get(a,0) for a in agent_names)

def _gather_gate_metrics():
    """Gather completion gate metrics for system observability."""
    import os
    import json
    from pathlib import Path

    gate_metrics = {
        "pending_gates": 0,
        "blocked_gates": 0,
        "pass_rate_24h": 0.0,
        "avg_completion_24h": 0.0,
        "avg_followups": 0.0,
        "recent_audits": 0
    }

    try:
        # Method 1: Use gate resolver if available
        sys.path.insert(0, "/Users/kublai/.openclaw/agents/main/scripts")
        try:
            from completion_gate_resolver import GateResolver
            resolver = GateResolver(dry_run=True)
            metrics = resolver.get_gate_metrics()
            return {
                "pending_gates": metrics.get("pending_gates", 0),
                "blocked_gates": metrics.get("blocked_gates", 0),
                "pass_rate_24h": metrics.get("pass_rate_24h", 0.0),
                "avg_completion_24h": metrics.get("avg_completion_24h", 0.0),
                "avg_followups": metrics.get("total_followups", 0) / max(metrics.get("recent_audits", 1), 1),
                "recent_audits": metrics.get("recent_audits_24h", 0)
            }
        except ImportError:
            pass

        # Method 2: Scan filesystem for pending gates
        pending_count = 0
        blocked_count = 0

        agents_dir = Path("/Users/kublai/.openclaw/agents")
        for agent_dir in agents_dir.iterdir():
            if not agent_dir.is_dir() or agent_dir.name.startswith('.'):
                continue
            tasks_dir = agent_dir / "tasks"
            if not tasks_dir.exists():
                continue
            pending_count += len(list(tasks_dir.glob("*.pending-gate.md")))
            blocked_count += len(list(tasks_dir.glob("*.gate-blocked.md")))

        gate_metrics["pending_gates"] = pending_count
        gate_metrics["blocked_gates"] = blocked_count

        # Method 3: Read audit JSON files for metrics
        audit_dir = Path("/Users/kublai/.openclaw/agents/main/logs/gate-audits")
        if audit_dir.exists():
            import time
            cutoff = time.time() - (24 * 3600)  # 24 hours ago
            recent_audits = []
            total_completion = 0
            passed_count = 0

            for audit_file in audit_dir.glob("*.json"):
                try:
                    mtime = audit_file.stat().st_mtime
                    if mtime > cutoff:
                        with open(audit_file) as f:
                            data = json.load(f)
                        recent_audits.append(data)
                        total_completion += data.get("completion_percentage", 100)
                        if data.get("can_complete"):
                            passed_count += 1
                except Exception:
                    continue

            if recent_audits:
                gate_metrics["recent_audits"] = len(recent_audits)
                gate_metrics["avg_completion_24h"] = round(total_completion / len(recent_audits), 1)
                gate_metrics["pass_rate_24h"] = round(100.0 * passed_count / len(recent_audits), 1)

    except Exception as e:
        gate_metrics["error"] = str(e)

    return gate_metrics

def _build_ledger_recon(neo4j_data, ledger_data):
    """Compare Neo4j completion counts vs ledger counts. Flag mismatches."""
    neo4j_completed = {}
    neo4j_failed = {}
    if "agent_tasks" in neo4j_data:
        for row in neo4j_data["agent_tasks"]:
            a = row.get("agent", "")
            neo4j_completed[a] = row.get("completed", 0)
            neo4j_failed[a] = row.get("failed", 0)

    ledger_completed = ledger_data.get("completed", {})
    ledger_failed = ledger_data.get("failed", {})

    mismatches = []
    for agent in agent_names:
        nc = neo4j_completed.get(agent, 0)
        lc = ledger_completed.get(agent, 0)
        nf = neo4j_failed.get(agent, 0)
        lf = ledger_failed.get(agent, 0)
        if nc != lc or nf != lf:
            mismatches.append({
                "agent": agent,
                "neo4j_completed": nc, "ledger_completed": lc,
                "neo4j_failed": nf, "ledger_failed": lf,
            })

    total_neo4j = sum(neo4j_completed.values())
    total_ledger = sum(ledger_completed.values())
    return {
        "neo4j_total_completed": total_neo4j,
        "ledger_total_completed": total_ledger,
        "delta": total_neo4j - total_ledger,
        "mismatches": mismatches,
        "reconciled": len(mismatches) == 0
    }

output = {
    "timestamp": "$TS_ISO",
    "agents": agents,
    "cron": cron if "error" not in cron else {"total_jobs":0,"healthy":0,"erroring":0,"jobs":[]},
    "cron_jobs": cron_jobs,
    "completion_gate": _gather_gate_metrics(),
    "queues": {
        "total_pending": queue_total,
        "by_agent": queues,
        "spawn_pending": int("$SPAWN_COUNT")
    },
    "delegation": {
        "recent": neo4j.get("delegations",[]),
        "count_30m": len(neo4j.get("delegations",[]))
    },
    "errors": {
        "clusters": neo4j.get("error_clusters",[])
    },
    "system": {
        "neo4j_reachable": "error" not in neo4j,
        "tick_status": "$TICK_STATUS",
        "neo4j_status": "$TICK_NEO4J",
        "redis_status": "$TICK_REDIS"
    },
    "queue_audit": queue_audit,
    "ledger_reconciliation": _build_ledger_recon(neo4j, ledger),
    "stale_locks": stale_locks,
    "routing": {
        "queue_balance_index": routing.get("queue_balance_index", 0),
        "missed_opportunities": routing.get("missed_opportunities", 0),
        "routing_accuracy": routing.get("routing_accuracy", 0.87),
        "time_to_start_p95": routing.get("time_to_start_p95", 420),
        "total_routed": routing.get("total_routed", 0),
        "overflow_count": routing.get("overflow_count", 0),
        "queue_depths": routing.get("queue_depths", {}),
        "source": routing.get("source", "unknown")
    },
    "subprocess": {
        "executing": subprocess_audit.get("summary", {}).get("total_executing", 0),
        "alive": subprocess_audit.get("summary", {}).get("alive", 0),
        "dead": subprocess_audit.get("summary", {}).get("dead", 0),
        "stale": subprocess_audit.get("summary", {}).get("stale", 0),
        "zombies": subprocess_audit.get("summary", {}).get("zombies", 0),
        "orphaned": subprocess_audit.get("summary", {}).get("orphaned", 0),
        "anomaly_count": subprocess_audit.get("summary", {}).get("anomaly_count", 0),
        "anomalies": subprocess_audit.get("anomalies", [])
    }
}

print(json.dumps(output, indent=2, default=str))
PYEOF
)
rm -rf "$TOCK_TMP"

if [ -z "$ASSEMBLED" ]; then
    echo "[$TS] TOCK | ERROR: assembly failed" >> "$TOCK_LOG"
    echo "TOCK FAILED: data assembly error"
    exit 1
fi

# ============================================================
# 7. Generate LLM summary (under 500 tokens)
# ============================================================
# Write assembled JSON to temp file for safe Python access
TOCK_ASSEMBLED_TMP=$(mktemp)
echo "$ASSEMBLED" > "$TOCK_ASSEMBLED_TMP"

LLM_SUMMARY=$(python3 << PYEOF
import json
with open("$TOCK_ASSEMBLED_TMP") as f:
    data = json.loads(f.read().strip())
lines = ["TOCK SUMMARY $TS", ""]
lines.append("AGENT TASKS (30m):")
for name, a in data["agents"].items():
    t = a["tasks"]
    s = a.get("session",{})
    lines.append(f"  {name}: done={t['completed']} fail={t['failed']} pending={t['pending']} queue={t['queue_depth']} ctx={s.get('pct_used',0)}%")
# Model config vs session check
model_issues = []
for name, a in data["agents"].items():
    cm = a.get("config_model", {})
    if not cm.get("valid", True):
        model_issues.append(f"  {name}: INVALID config model (resolved={cm.get('resolved','?')})")
    elif not cm.get("session_match", True) and a.get("session",{}).get("model","none") != "none":
        model_issues.append(f"  {name}: session={a['session']['model']} != config={cm.get('resolved','?')} (stale session, config OK)")
if model_issues:
    lines.append("\nMODEL STATUS:")
    lines.extend(model_issues)
else:
    lines.append("\nMODEL STATUS: all configs valid, no mismatches")

q = data["queues"]
lines.append(f"\nQUEUES: file_pending={q['total_pending']} spawn={q['spawn_pending']}")
# Stale locks reporting
sl = data.get("stale_locks", {})
stale_total = sl.get("total", 0)
if stale_total > 0:
    lines.append(f"STALE LOCKS: {stale_total} detected")
    for lock in sl.get("details", [])[:5]:  # Show up to 5 stale locks
        lines.append(f"  {lock['agent']}: {lock['task_file'][:50]} pid={lock['pid']} age={lock['age_seconds']}s")
else:
    lines.append("STALE LOCKS: none")
c = data["cron"]
lines.append(f"CRON: {c.get('healthy',0)}/{c.get('total_jobs',0)} healthy")
for j in c.get("jobs",[]):
    if j.get("consecutive_errors",0) > 0:
        lines.append(f"  ERR: {j['name']} consec={j['consecutive_errors']}")
# Cron jobs monitoring (calendar_reminder, backup)
cj = data.get("cron_jobs", {})
if cj:
    cal = cj.get("calendar_reminder", {})
    backup = cj.get("backup", {})
    lines.append(f"CRON_JOBS: calendar_reminder={cal.get('status','?')} (5min={cal.get('ran_last_5min',False)}) | backup={backup.get('status','?')} (24h={backup.get('ran_last_24h',False)})")
e = data["errors"]
for cl in e.get("clusters",[]):
    lines.append(f"  error: '{str(cl.get('error',''))[:60]}' x{cl.get('count',0)}")
d = data["delegation"]
lines.append(f"DELEGATIONS: {d['count_30m']} in 30m")
lines.append(f"SYSTEM: neo4j={'ok' if data['system']['neo4j_reachable'] else 'DOWN'} tick={data['system']['tick_status']}")
lr = data.get("ledger_reconciliation", {})
if not lr.get("reconciled", True):
    lines.append(f"LEDGER MISMATCH: neo4j={lr.get('neo4j_total_completed',0)} vs ledger={lr.get('ledger_total_completed',0)} (delta={lr.get('delta',0)})")
    for m in lr.get("mismatches", []):
        lines.append(f"  {m['agent']}: neo4j_done={m['neo4j_completed']} ledger_done={m['ledger_completed']} neo4j_fail={m['neo4j_failed']} ledger_fail={m['ledger_failed']}")
# Routing metrics (from routing-metrics.sh)
r = data.get("routing", {})
lines.append(f"ROUTING: balance_idx={r.get('queue_balance_index',0):.2f} missed={r.get('missed_opportunities',0)} accuracy={r.get('routing_accuracy',0):.0%} p95={r.get('time_to_start_p95',0)}s routed={r.get('total_routed',0)}")
# Subprocess audit (claude-agent process correlation)
sp = data.get("subprocess", {})
sp_anomalies = sp.get("anomaly_count", 0)
if sp_anomalies > 0:
    lines.append(f"SUBPROCESS: {sp.get('executing',0)} executing (alive={sp.get('alive',0)} dead={sp.get('dead',0)} stale={sp.get('stale',0)}) ANOMALIES={sp_anomalies}")
    for a in sp.get("anomalies", [])[:3]:  # Show up to 3 anomalies
        lines.append(f"  {a.get('type','?')}: agent={a.get('agent','?')} task={a.get('task_id','?')[:30]} action={a.get('action','?')}")
else:
    lines.append(f"SUBPROCESS: {sp.get('executing',0)} executing (alive={sp.get('alive',0)} dead={sp.get('dead',0)} stale={sp.get('stale',0)}) all healthy")
print("\n".join(lines))
PYEOF
)

# ============================================================
# 8. LLM Assessment (direct API call to Ollama)
# ============================================================
LLM_ASSESSMENT=$(python3 << PYEOF
import json, re, sys, requests
sys.path.insert(0, "$BASE/scripts")
from ollama_lock import OllamaLock, Priority, LockBusy

summary = """$LLM_SUMMARY"""

prompt = f"""You are an operations analyst for a 6-agent AI system. Given this 30-minute snapshot, provide a brief assessment.

{summary}

Respond in EXACTLY this format (no extra text):
WORKLOAD: <one sentence on agent workload balance>
BOTTLENECK: <biggest bottleneck or "none">
COORDINATION: <inter-agent gaps or "none">
ACTION: <one recommended action or "none needed">
SEVERITY: LOW|MEDIUM|HIGH|CRITICAL"""

try:
    with OllamaLock(Priority.NORMAL, label="tock-assessment"):
        resp = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "hf.co/lukey03/Qwen3.5-9B-abliterated-GGUF",
                "messages": [
                    {"role": "system", "content": "You are a concise operations analyst. Respond only in the exact format requested."},
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
except:
    print("FALLBACK")
PYEOF
)
LLM_ASSESSMENT=${LLM_ASSESSMENT:-FALLBACK}

# ============================================================
# 9. Parse LLM response or heuristic fallback
# ============================================================
LLM_JSON=$(python3 << PYEOF
import json

raw = """$LLM_ASSESSMENT"""
with open("$TOCK_ASSEMBLED_TMP") as f:
    data = json.loads(f.read().strip())

assessment = {"model":"ollama/hf.co/lukey03/Qwen3.5-9B-abliterated-GGUF","workload_balance":"","bottleneck":"","coordination_gap":"","recommended_action":"","severity":"LOW"}

if raw.strip() != "FALLBACK" and "WORKLOAD:" in raw:
    for line in raw.strip().split("\n"):
        line = line.strip()
        if line.startswith("WORKLOAD:"): assessment["workload_balance"] = line[9:].strip()
        elif line.startswith("BOTTLENECK:"): assessment["bottleneck"] = line[11:].strip()
        elif line.startswith("COORDINATION:"): assessment["coordination_gap"] = line[13:].strip()
        elif line.startswith("ACTION:"): assessment["recommended_action"] = line[7:].strip()
        elif line.startswith("SEVERITY:"):
            sev = line[9:].strip().upper()
            if sev in ["LOW","MEDIUM","HIGH","CRITICAL"]: assessment["severity"] = sev
else:
    # Heuristic fallback
    assessment["model"] = "heuristic-fallback"
    q = data.get("queues",{})
    total_pending = q.get("total_pending",0)
    cron_errors = data.get("cron",{}).get("erroring",0)
    stale_total = data.get("stale_locks",{}).get("total",0)

    if stale_total > 0:
        assessment["bottleneck"] = f"{stale_total} stale task locks blocking system"
        assessment["severity"] = "HIGH"
        assessment["recommended_action"] = "Run stale-lock-cleanup cron job or manually remove .executing.pid files"
    elif total_pending > 20:
        assessment["workload_balance"] = f"IMBALANCED: {total_pending} tasks queued"
        assessment["bottleneck"] = f"Queue backlog: {total_pending} pending"
        assessment["severity"] = "MEDIUM"
    elif cron_errors > 0:
        assessment["bottleneck"] = f"{cron_errors} cron jobs erroring"
        assessment["severity"] = "MEDIUM"
    else:
        assessment["workload_balance"] = "Balanced"
        assessment["bottleneck"] = "none"
        assessment["severity"] = "LOW"
    assessment["recommended_action"] = "Review queue backlog" if total_pending > 0 else "none needed"

print(json.dumps(assessment))
PYEOF
)

# ============================================================
# 10. Write outputs
# ============================================================
python3 << PYEOF
import json, os
with open("$TOCK_ASSEMBLED_TMP") as f:
    data = json.loads(f.read().strip())
assessment = json.loads('''$LLM_JSON''')
data["llm_assessment"] = assessment
with open("$OUTFILE", "w") as f:
    json.dump(data, f, indent=2, default=str)
latest = "$LATEST"
if os.path.islink(latest) or os.path.exists(latest):
    os.remove(latest)
os.symlink("$OUTFILE", latest)
PYEOF
# ============================================================
# 10.5 Model Mismatch Remediation (Finding 2)
# ============================================================
python3 << 'PYEND'
import json, os, hashlib
from datetime import datetime

TOCK_FILE = os.environ.get("OUTFILE", "/Users/kublai/.openclaw/agents/main/logs/tock/latest.json")
AGENTS_DIR = os.path.expanduser("~/.openclaw/agents")

# Neo4j connection for idempotency check
def check_existing_remediation_task(agent_name, mismatch_type):
    """Check Neo4j for existing pending remediation task to prevent duplicates."""
    try:
        from neo4j import GraphDatabase
        import os as _os
        driver = GraphDatabase.driver(
            _os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            auth=(_os.getenv("NEO4J_USER", "neo4j"), _os.getenv("NEO4J_PASSWORD", "myStrongPassword123")),
            connection_timeout=5, max_transaction_retry_time=5
        )
        with driver.session() as session:
            # Check for existing Task nodes with same idempotency key
            result = session.run("""
                MATCH (t:Task)
                WHERE t.idempotency_key = $idempotency_key
                  AND NOT t.status = 'completed'
                  AND t.created > datetime() - duration({hours: 24})
                RETURN t.task_id AS task_id, t.status AS status
                LIMIT 1
            """, idempotency_key=f"model-mismatch-{agent_name}-{mismatch_type}")
            record = result.single()
            if record:
                return {"exists": True, "task_id": record["task_id"], "status": record["status"]}
        driver.close()
    except Exception as e:
        # If Neo4j fails, fall back to file check only
        pass
    return {"exists": False}

try:
    with open(TOCK_FILE) as f:
        data = json.load(f)
except Exception as e:
    exit(0)

for agent_name, agent_data in data.get("agents", {}).items():
    config_model = agent_data.get("config_model", "")
    session_model = agent_data.get("session_model", "")
    
    if not session_model or session_model == "none":
        continue
    
    if config_model and session_model and config_model != session_model:
        # Create mismatch type hash for idempotency key
        mismatch_type = hashlib.md5(f"{config_model}:{session_model}".encode()).hexdigest()[:8]
        idempotency_key = f"model-mismatch-{agent_name}-{mismatch_type}"
        
        # Check Neo4j for existing remediation task (idempotency check)
        existing = check_existing_remediation_task(agent_name, mismatch_type)
        if existing["exists"]:
            print(f"  {agent_name}: Skipping - remediation already exists ({existing['task_id']}, status={existing['status']})")
            continue
        
        agent_tasks_dir = os.path.join(AGENTS_DIR, agent_name, "tasks")
        if not os.path.exists(agent_tasks_dir):
            continue
        
        # Fallback: check filesystem for recent task files
        existing_task = None
        for task_file in os.listdir(agent_tasks_dir):
            if task_file.endswith(".md"):
                task_path = os.path.join(agent_tasks_dir, task_file)
                try:
                    with open(task_path) as tf:
                        content = tf.read().lower()
                        if "model mismatch" in content and agent_name in content:
                            # Check if task is recent (within 24 hours by filename timestamp)
                            existing_task = task_file
                            break
                except:
                    pass
        
        if not existing_task:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            task_file = f"normal-{timestamp}-model-mismatch.md"
            task_path = os.path.join(agent_tasks_dir, task_file)
            
            task_content = f"""---
task_id: auto-model-mismatch-{timestamp}
agent: {agent_name}
priority: high
created_at: {datetime.now().isoformat()}
source: tock-gather-remediation
idempotency_key: {idempotency_key}
remediation_triggered_by: tock-gather
tags: [model-mismatch, configuration, idempotent]
---

# Model Mismatch Detected

**Config model:** {config_model}
**Session model:** {session_model}
**Idempotency key:** {idempotency_key}

## Actions
1. Verify settings.json model config
2. Check session spawn parameters
3. Restart agent if needed

## Notes
- Triggered by: tock-gather.sh
- This task is idempotent - duplicates prevented by idempotency_key
- Do not create multiple remediation tasks for same agent+mismatch
"""
            with open(task_path, "w") as f:
                f.write(task_content)
            print(f"  {agent_name}: Created {task_file} (idempotency_key={idempotency_key})")
PYEND


# One-liner to tock.log
SEVERITY=$(python3 -c "import json; print(json.loads('''$LLM_JSON''').get('severity','?'))" 2>/dev/null || echo "?")
BOTTLENECK=$(python3 -c "import json; print(json.loads('''$LLM_JSON''').get('bottleneck','?')[:80])" 2>/dev/null || echo "?")
TASKS_DONE=$(python3 -c "import json; d=json.load(open('$TOCK_ASSEMBLED_TMP')); print(sum(a['tasks']['completed'] for a in d['agents'].values()))" 2>/dev/null || echo 0)
TASKS_FAIL=$(python3 -c "import json; d=json.load(open('$TOCK_ASSEMBLED_TMP')); print(sum(a['tasks']['failed'] for a in d['agents'].values()))" 2>/dev/null || echo 0)
Q_TOTAL=$(python3 -c "import json; print(json.load(open('$TOCK_ASSEMBLED_TMP')).get('queues',{}).get('total_pending',0))" 2>/dev/null || echo 0)
CRON_ERR=$(python3 -c "import json; print(json.loads('''$CRON_DATA''').get('erroring',0))" 2>/dev/null || echo 0)
LEDGER_DELTA=$(python3 -c "import json; d=json.load(open('$TOCK_ASSEMBLED_TMP')); print(d.get('ledger_reconciliation',{}).get('delta',0))" 2>/dev/null || echo 0)
# Cron jobs status
CAL_STATUS=$(python3 -c "import json; d=json.load(open('$TOCK_ASSEMBLED_TMP')); print(d.get('cron_jobs',{}).get('calendar_reminder',{}).get('status','?'))" 2>/dev/null || echo "?")
BACKUP_STATUS=$(python3 -c "import json; d=json.load(open('$TOCK_ASSEMBLED_TMP')); print(d.get('cron_jobs',{}).get('backup',{}).get('status','?'))" 2>/dev/null || echo "?")

LEDGER_NOTE=""
if [ "$LEDGER_DELTA" != "0" ]; then
    LEDGER_NOTE=" | ledger_delta=$LEDGER_DELTA"
fi

echo "[$TS] TOCK | tasks_done=$TASKS_DONE | tasks_fail=$TASKS_FAIL | queue=$Q_TOTAL | cron_err=$CRON_ERR | calendar_reminder=$CAL_STATUS | backup=$BACKUP_STATUS | severity=$SEVERITY${LEDGER_NOTE} | note=\"$BOTTLENECK\"" >> "$TOCK_LOG"

# ============================================================
# NEO4J STATE SYNC: Reconcile filesystem task state with Neo4j (safety net)
# ============================================================
python3 "$BASE/scripts/neo4j-state-sync.py" --apply >> "$BASE/logs/neo4j-state-sync.log" 2>&1 &

# ============================================================
# KUBLAI ACTIONS: Create tasks based on tock findings
# ============================================================
python3 "$BASE/scripts/kublai-actions.py" --trigger tock >> "$BASE/logs/kublai-actions.log" 2>&1 &

# Cleanup temp file
rm -f "$TOCK_ASSEMBLED_TMP"

# ============================================================
# QMD INDEX REFRESH: Update semantic search index (every 60 min at :01)
# ============================================================
CURRENT_MIN=$(date +%M)
if [ "$CURRENT_MIN" = "01" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] QMD: Refreshing semantic search index" >> "$TOCK_LOG"
    QMD_LOG="$BASE/logs/qmd-index.log"
    mkdir -p "$(dirname "$QMD_LOG")"

    # Run QMD update and embed
    if qmd update >> "$QMD_LOG" 2>&1 && qmd embed >> "$QMD_LOG" 2>&1; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] QMD: Index refresh complete" >> "$TOCK_LOG"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] QMD: Index refresh FAILED (see $QMD_LOG)" >> "$TOCK_LOG"
    fi
fi

# Output for LLM
echo "TOCK COMPLETE. Severity: $SEVERITY. Bottleneck: $BOTTLENECK"
