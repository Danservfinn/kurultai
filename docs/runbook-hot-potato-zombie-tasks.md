# Runbook: Hot-Potato / Zombie Task Incidents

**Created:** 2026-03-23
**Origin:** Review of task normal-1774002689-188154db (temujin stalled agent triage)
**Severity trigger:** Task redistributed > 5 times with no completion

---

## What Is a Hot-Potato Loop?

A task bounces endlessly between agents because:
1. The task is in a terminal/stale state (`.stale-resolved`, `.revision`, etc.) but the redistribution system treats it as pending
2. All candidate agents are down — the task is redistributed to a dead agent, which routes it back
3. A revision task from a failed quality gate is never picked up because no suitable agent is running

**Signature:** Redistribution comments piling up in the task file (`<!-- Task redistributed from ... -->`), or `redispatch_count` in frontmatter incrementing without any agent claiming the work.

---

## Detection

### Automated (post-2026-03-23)
- `stale-task-archiver.py` runs hourly (at :15) and auto-archives tasks matching `.stale-resolved`, `.quarantine`, `.revision` that are older than 4 hours
- `circuit_breaker.py` now filters the full TERMINAL_MARKERS set (same as `task-redistribute.py`) — stale tasks will no longer be redistributed at all

### Manual Detection
```bash
# Find tasks that have been redistributed many times
grep -r "Task redistributed" ~/.openclaw/agents/*/tasks/*.md | \
  awk -F: '{print $1}' | sort | uniq -c | sort -rn | head -20

# Find tasks with high redispatch_count
grep -r "^redispatch_count:" ~/.openclaw/agents/*/tasks/*.md | \
  sort -t: -k3 -rn | head -10

# Find very old .stale-resolved tasks
find ~/.openclaw/agents/*/tasks -name "*.stale-resolved*.md" -mmin +120 2>/dev/null

# Check redistribution activity in logs
grep "redistribute\|hot.potato\|redispatch" ~/.openclaw/agents/main/logs/circuit-breaker*.log 2>/dev/null | tail -30
```

---

## Diagnosis Steps

### Step 1: Identify the zombie task
```bash
# List all task files with redistribution markers
find ~/.openclaw/agents/*/tasks -name "*.md" | xargs grep -l "Task redistributed" 2>/dev/null

# Check its state
cat <path-to-task>
```

**Key fields to check:**
- `redispatch_count:` — how many times it's been moved
- File extension — `.stale-resolved`, `.revision-N`, `.quarantine` = terminal state, should not be here
- Age: `ls -la <path>` — if >4h old with no completion, it's a zombie

### Step 2: Check Neo4j for this task
```bash
python3 ~/.openclaw/agents/main/scripts/neo4j-state-sync.py --verbose 2>/dev/null | grep <task_id>
# OR direct Cypher:
# MATCH (t:Task {task_id: '<id>'}) RETURN t.status, t.dispatch_phase, t.claimed_by, t.retry_count
```

If Neo4j shows `PENDING` or `WORKING` but the file is `.stale-resolved`, there is state divergence.

### Step 3: Check agent liveness
```bash
# Is the target agent actually running?
ps aux | grep "claude-agent.*<agent_name>"

# Check agent heartbeat file
ls -la ~/.openclaw/agents/<agent_name>/

# Check last completed task
cat ~/.openclaw/agents/<agent_name>/last-completed-task.json 2>/dev/null
```

### Step 4: Check circuit breaker state
```bash
python3 ~/.openclaw/agents/main/scripts/circuit_breaker.py --status
python3 ~/.openclaw/agents/main/scripts/circuit_breaker.py --check <agent_name>
```

If the circuit is OPEN for the target agent, the dispatcher correctly won't route there — but the task may still be stuck in the queue.

---

## Resolution

### Option A: Let the archiver handle it (preferred)
If the stale-task-archiver cron is running (hourly at :15), it will auto-archive within ~1 hour.
- Verify: `tail -f ~/.openclaw/agents/main/logs/stale-archiver.jsonl`
- Force run now: `python3 ~/.openclaw/agents/main/scripts/stale-task-archiver.py --dry-run` (preview), then without `--dry-run`

### Option B: Manual archive (immediate)
```bash
# Move to agent's archive directory
TASK_PATH="<full path to zombie task file>"
AGENT_DIR=$(dirname $(dirname $TASK_PATH))
ARCHIVE_DIR="$AGENT_DIR/tasks/_archive-$(date +%Y%m%d)"
mkdir -p "$ARCHIVE_DIR"
mv "$TASK_PATH" "$ARCHIVE_DIR/$(basename $TASK_PATH).archived-hotpotato.md"
echo "Archived to $ARCHIVE_DIR"
```

Then sync Neo4j state:
```bash
python3 ~/.openclaw/agents/main/scripts/neo4j-state-sync.py --apply
```

### Option C: Fail the task via TaskStore (if Neo4j is authoritative)
```python
# In python3 -c or a script:
import sys; sys.path.insert(0, '/Users/kublai/.openclaw/agents/main/scripts')
from neo4j_task_tracker import TaskStore
store = TaskStore()
store.fail_task('<task_id>', error='Zombie hot-potato: archived by operator', is_transient=False)
store.close()
```

---

## Prevention (post-2026-03-23 fixes)

1. **`circuit_breaker.py`** now uses the full TERMINAL_MARKERS list — stale/resolved/revision tasks are never redistributed
2. **`stale-task-archiver.py`** runs hourly — catches any stragglers within 4 hours
3. **Quality gate revisions** — revision tasks should not be created infinitely (add `max_depth: 1` to task frontmatter)

---

## Escalation

If the loop persists after manual archive + Neo4j sync:
1. Check if a NEW zombie task was spawned (health alert cron creating duplicates)
2. If parsethe.media (or another monitored service) is genuinely down, the health-check cron will recreate the alert task every hour — dedup is needed at the source
3. Escalate to kublai for coordination via `/horde-debug` on the underlying monitoring cron

---

## Related Files
- `scripts/circuit_breaker.py` — redistribution and liveness logic
- `scripts/stale-task-archiver.py` — automated cleanup
- `scripts/task-redistribute.py` — TERMINAL_MARKERS reference
- `scripts/neo4j-state-sync.py` — state reconciliation
- `logs/stale-archiver.jsonl` — archiver run history
- `docs/state-management-reference.md` — canonical task state lifecycle
