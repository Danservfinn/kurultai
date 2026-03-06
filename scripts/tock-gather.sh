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
import json, signal
signal.alarm(30)  # kill after 30 seconds
try:
    from neo4j import GraphDatabase
    import os as _os
    driver = GraphDatabase.driver(
        _os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(_os.getenv("NEO4J_USER", "neo4j"), _os.getenv("NEO4J_PASSWORD", "myStrongPassword123")),
        connection_timeout=5, max_transaction_retry_time=5
    )
    results = {}
    with driver.session() as session:
        # Per-agent tasks (30m)
        r = session.run("""
            MATCH (t:Task)
            WHERE t.created > datetime() - duration('PT30M')
            WITH t.agent AS agent,
                 count(t) AS total,
                 sum(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) AS completed,
                 sum(CASE WHEN t.status = 'failed' THEN 1 ELSE 0 END) AS failed,
                 sum(CASE WHEN t.status IN ['ready','queued'] THEN 1 ELSE 0 END) AS pending,
                 sum(CASE WHEN t.status = 'running' THEN 1 ELSE 0 END) AS running,
                 coalesce(sum(t.retry_count),0) AS retries
            RETURN agent, total, completed, failed, pending, running, retries
        """)
        results["agent_tasks"] = [dict(rec) for rec in r]

        # Delegations (30m)
        r = session.run("""
            MATCH (t:Task)
            WHERE t.created > datetime() - duration('PT30M')
              AND t.source IS NOT NULL AND t.source <> t.agent
            RETURN t.source AS from_agent, t.agent AS to_agent,
                   t.label AS task_label
            LIMIT 20
        """)
        results["delegations"] = [dict(rec) for rec in r]

        # Error clusters (30m)
        r = session.run("""
            MATCH (t:Task)
            WHERE t.created > datetime() - duration('PT30M')
              AND t.status = 'failed' AND t.error IS NOT NULL
            RETURN t.error AS error, count(t) AS count,
                   collect(DISTINCT t.agent) AS agents
            ORDER BY count DESC LIMIT 10
        """)
        results["error_clusters"] = [dict(rec) for rec in r]

    driver.close()
    print(json.dumps(results, default=str))
except Exception as e:
    print(json.dumps({"error": str(e)}))
PYEOF
)
NEO4J_DATA=${NEO4J_DATA:-'{"error":"neo4j_unavailable"}'}

# ============================================================
# 2. Session usage from gateway
# ============================================================
SESSION_DATA=$(timeout 15 openclaw gateway call status --json 2>/dev/null || echo '{}')

# ============================================================
# 3. Cron job health
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
    print(json.dumps({"error": str(e)}))
PYEOF
)
CRON_DATA=${CRON_DATA:-'{"total_jobs":0,"healthy":0,"erroring":0,"jobs":[]}'}

# ============================================================
# 4. Task queue depths (file-based)
# ============================================================
QUEUE_DATA=$(python3 2>/dev/null << 'PYEOF'
import json, os, glob
base = "/Users/kublai/.openclaw/agents"
queues = {}
for agent in ["kublai","mongke","chagatai","temujin","jochi","ogedei"]:
    task_dir = f"{base}/{agent}/tasks"
    if not os.path.isdir(task_dir):
        queues[agent] = 0
        continue
    pending = 0
    for pattern in ["high-*.md", "normal-*.md", "low-*.md"]:
        for f in glob.glob(f"{task_dir}/{pattern}"):
            if ".executing" not in f and ".done" not in f:
                pending += 1
    queues[agent] = pending
print(json.dumps(queues))
PYEOF
)
QUEUE_DATA=${QUEUE_DATA:-'{}'}

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
# 5. Last tick status
# ============================================================
TICK_STATUS=$(tail -1 "$BASE/logs/watchdog.log" 2>/dev/null | grep -o "status=[a-z]*" | cut -d= -f2; true)
TICK_STATUS=${TICK_STATUS:-unknown}

# ============================================================
# 6. Assemble full JSON
# ============================================================
ASSEMBLED=$(python3 << PYEOF
import json

neo4j = json.loads('''$NEO4J_DATA''')
session_raw = '''$SESSION_DATA'''
cron = json.loads('''$CRON_DATA''')
queues = json.loads('''$QUEUE_DATA''')
try:
    queue_audit = json.loads('''$QUEUE_AUDIT''')
except:
    queue_audit = {"audited":0,"fake_found":0,"requeued":0,"skipped":0}

# Parse session data
try:
    session = json.loads(session_raw) if session_raw.strip() else {}
except:
    session = {}

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
    agents[name] = {
        "tasks": {
            "completed": completed, "failed": t.get("failed",0),
            "pending": t.get("pending",0), "running": t.get("running",0),
            "total": total, "queue_depth": queues.get(name,0)
        },
        "success_rate": round(100.0*completed/total,1) if total > 0 else None,
        "retries": t.get("retries",0),
        "session": s if s else {"count":0,"pct_used":0,"model":"none"}
    }

queue_total = sum(queues.get(a,0) for a in agent_names)

output = {
    "timestamp": "$TS_ISO",
    "agents": agents,
    "cron": cron if "error" not in cron else {"total_jobs":0,"healthy":0,"erroring":0,"jobs":[]},
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
        "tick_status": "$TICK_STATUS"
    },
    "queue_audit": queue_audit
}

print(json.dumps(output, indent=2, default=str))
PYEOF
)

if [ -z "$ASSEMBLED" ]; then
    echo "[$TS] TOCK | ERROR: assembly failed" >> "$TOCK_LOG"
    echo "TOCK FAILED: data assembly error"
    exit 1
fi

# ============================================================
# 7. Generate LLM summary (under 500 tokens)
# ============================================================
LLM_SUMMARY=$(python3 << PYEOF
import json
data = json.loads('''$ASSEMBLED''')
lines = ["TOCK SUMMARY $TS", ""]
lines.append("AGENT TASKS (30m):")
for name, a in data["agents"].items():
    t = a["tasks"]
    s = a.get("session",{})
    lines.append(f"  {name}: done={t['completed']} fail={t['failed']} pending={t['pending']} queue={t['queue_depth']} ctx={s.get('pct_used',0)}%")
q = data["queues"]
lines.append(f"\nQUEUES: file_pending={q['total_pending']} spawn={q['spawn_pending']}")
c = data["cron"]
lines.append(f"CRON: {c.get('healthy',0)}/{c.get('total_jobs',0)} healthy")
for j in c.get("jobs",[]):
    if j.get("consecutive_errors",0) > 0:
        lines.append(f"  ERR: {j['name']} consec={j['consecutive_errors']}")
e = data["errors"]
for cl in e.get("clusters",[]):
    lines.append(f"  error: '{str(cl.get('error',''))[:60]}' x{cl.get('count',0)}")
d = data["delegation"]
lines.append(f"DELEGATIONS: {d['count_30m']} in 30m")
lines.append(f"SYSTEM: neo4j={'ok' if data['system']['neo4j_reachable'] else 'DOWN'} tick={data['system']['tick_status']}")
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
                "model": "qwen3.5:9b",
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
data = json.loads('''$ASSEMBLED''')

assessment = {"model":"ollama/qwen3.5:9b","workload_balance":"","bottleneck":"","coordination_gap":"","recommended_action":"","severity":"LOW"}

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

    if total_pending > 20:
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
data = json.loads('''$ASSEMBLED''')
assessment = json.loads('''$LLM_JSON''')
data["llm_assessment"] = assessment
with open("$OUTFILE", "w") as f:
    json.dump(data, f, indent=2, default=str)
latest = "$LATEST"
if os.path.islink(latest) or os.path.exists(latest):
    os.remove(latest)
os.symlink("$OUTFILE", latest)
PYEOF

# One-liner to tock.log
SEVERITY=$(python3 -c "import json; print(json.loads('''$LLM_JSON''').get('severity','?'))" 2>/dev/null || echo "?")
BOTTLENECK=$(python3 -c "import json; print(json.loads('''$LLM_JSON''').get('bottleneck','?')[:80])" 2>/dev/null || echo "?")
TASKS_DONE=$(python3 -c "import json; d=json.loads('''$ASSEMBLED'''); print(sum(a['tasks']['completed'] for a in d['agents'].values()))" 2>/dev/null || echo 0)
TASKS_FAIL=$(python3 -c "import json; d=json.loads('''$ASSEMBLED'''); print(sum(a['tasks']['failed'] for a in d['agents'].values()))" 2>/dev/null || echo 0)
Q_TOTAL=$(python3 -c "import json; print(json.loads('''$ASSEMBLED''').get('queues',{}).get('total_pending',0))" 2>/dev/null || echo 0)
CRON_ERR=$(python3 -c "import json; print(json.loads('''$CRON_DATA''').get('erroring',0))" 2>/dev/null || echo 0)

echo "[$TS] TOCK | tasks_done=$TASKS_DONE | tasks_fail=$TASKS_FAIL | queue=$Q_TOTAL | cron_err=$CRON_ERR | severity=$SEVERITY | note=\"$BOTTLENECK\"" >> "$TOCK_LOG"

# ============================================================
# KUBLAI ACTIONS: Create tasks based on tock findings
# ============================================================
python3 "$BASE/scripts/kublai-actions.py" --trigger tock >> "$BASE/logs/kublai-actions.log" 2>&1 &

# Output for LLM
echo "TOCK COMPLETE. Severity: $SEVERITY. Bottleneck: $BOTTLENECK"
