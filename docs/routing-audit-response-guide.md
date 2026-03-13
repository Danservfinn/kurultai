# Routing Audit Response Guide

**Version:** 1.0
**Date:** 2026-03-12
**Author:** Chagatai (Kurultai Writer)
**Domain:** routing_pipeline

---

## Overview

The routing audit system generates structured analysis every hour via `queue-audit.py` and stores results in `logs/routing-audit-latest.json` and `logs/routing-audit-trend.json`. This guide explains how to interpret each field and what action to take for each issue type.

**Who should use this:** Any agent or operator responding to routing degradation, persistent queue backlogs, or high failure rates. Jochi typically owns routing health; kublai escalates when issues persist.

**Quick links:**
- [Reading the Audit Report](#reading-the-audit-report)
- [Issue Response Matrix](#issue-response-matrix)
- [Trend Escalation Rules](#trend-escalation-rules)
- [Fix Recipes](#fix-recipes)
- [Escalation Thresholds](#escalation-thresholds)

---

## Reading the Audit Report

### Key Fields in `routing-audit-latest.json`

```json
{
  "period_hours": 1,
  "generated_at": "2026-03-12T17:07:07Z",
  "total_routed": 26,
  "routing_methods": { ... },
  "destinations": { ... },
  "by_agent": { ... },
  "queue_state": { ... },
  "issues": [ ... ],
  "suggestions": [ ... ],
  "kw_misroute_count": 1,
  "kw_misroute_rate": "1/26",
  "kw_misroute_examples": [ ... ],
  "skill_hint_coverage": "17/26",
  "routing_drift": { ... },
  "recurring_issues": [ ... ],
  "missed_opportunities": { ... }
}
```

| Field | What it Means | Healthy Range |
|-------|---------------|---------------|
| `total_routed` | Tasks entering the pipeline this period | Any |
| `routing_methods.explicit` | Tasks routed via `@mention` or direct `agent=` parameter | < 60% of total |
| `kw_misroute_rate` | Keyword router disagreed with actual routing | < 10% |
| `skill_hint_coverage` | Tasks with a skill hint attached | > 50% |
| `routing_drift.drift_pct` | Routing changed after initial assignment | < 10% |
| `recurring_issues` | Issues appearing in 3+ consecutive audits | Empty |
| `missed_opportunities.count` | Tasks sent to agents when idler alternatives existed | 0 |

### The `by_agent` Block

```json
"by_agent": {
  "jochi": {
    "routed": 9,
    "executed": 5,
    "succeeded": 0,
    "failed": 5
  }
}
```

**Interpretation:**
- `routed > executed`: Tasks sitting in queue, not being dispatched (dispatch stall or agent overloaded)
- `executed > succeeded + failed`: Tasks currently executing
- `failed / executed ≥ 80%`: Agent is unhealthy — likely auth, OOM, or model error
- `routed >> other agents`: Workload skew — may cause backlog regardless of agent health

---

## Issue Response Matrix

The `issues` array is the primary action driver. Each string maps to a response category:

### Issue: "High explicit routing: N/N (X%) — keyword table may be underused"

**Meaning:** Most tasks bypassed keyword scoring and were sent directly to specific agents via `@mention` or `agent=` parameter. The keyword router had limited opportunity to balance load.

**Threshold:** Flag when explicit > 60% of total.

**Response (severity by consecutive count):**

| Consecutive | Response |
|-------------|----------|
| 1–2 | Informational. Note pattern but no action unless other issues co-occur. |
| 3–5 | Investigate call sites. Which script is sending explicit agent assignments? Check `kublai-actions.py`, watchdog, tock scripts. |
| 6+ | File a temujin task to audit hardcoded `agent=` parameters across dispatch scripts. |

**Root causes:**
1. System scripts (tick, tock, watchdog) hardcode agents by design — this inflates the explicit rate
2. Skill-locked routing counts as explicit after S4 in the pipeline
3. `@mention` tasks from human operators

**Not a problem if:** `issues` shows no backlog AND `missed_opportunities.count == 0`. Explicit routing is fine when load is balanced.

---

### Issue: "AGENT: N/N tasks failed (X%) — check if agent is healthy before routing more tasks"

**Meaning:** Agent executed tasks but all (or most) failed. System will continue routing to this agent unless the circuit breaker opens.

**Immediate action:**

```bash
# 1. Check failure category distribution
python3 ~/.openclaw/agents/main/scripts/failed-task-review.py --patterns

# 2. Check agent's recent failure log entries
tail -20 ~/.openclaw/agents/main/logs/failure-patterns.jsonl | \
  python3 -c "import sys,json; [print(json.loads(l)['agent'], json.loads(l).get('category','?'), json.loads(l).get('duration','?')) for l in sys.stdin]"

# 3. Check circuit breaker state
python3 -c "import json; s=json.load(open('$HOME/.openclaw/agents/main/logs/circuit-breaker-state.json')); [print(k, v.get('state')) for k,v in s.items()]"
```

**Decision tree:**

```
Duration < 10s AND category = "auth_error"?
  → See [Auth Failure Fix](#fix-auth-failures)

Duration 10–90s AND category = "claude_code_crash"?
  → See [OOM/Process Fix](#fix-oom-process-kills)

Duration > 90s AND category = "timeout"?
  → Tasks too complex. Break into subtasks.

Category = "unknown" > 50%?
  → Likely OOM kill (exit -9). Check memory pressure.
```

**Circuit breaker note:** After 3 consecutive failures, the circuit breaker opens for the agent. Routing will auto-exclude the agent. However, the circuit breaker requires `check_agent()` to be called to transition to HALF_OPEN — this is done by `circuit_breaker_health.py` on a 5-minute cron. Do NOT manually force-close a circuit breaker without fixing the root cause.

---

### Issue: "AGENT: N tasks pending in queue (backlog)"

**Meaning:** Agent has accumulated tasks faster than it processes them. This is the most dangerous pattern — tasks silently pile up.

**Severity by queue depth:**

| Pending | Action |
|---------|--------|
| 3–7 | Monitor. Normal for burst periods. |
| 8–14 | Investigate. Check if agent is executing. |
| 15+ | Escalate. Likely execution stall or dispatch failure. |

**Backlog diagnosis:**

```bash
# Is the agent actually executing anything?
cat ~/.openclaw/agents/AGENT_NAME/tasks/*.executing.md 2>/dev/null | head -5

# Is task-watcher running?
pgrep -f "task-watcher" | wc -l

# What are the queued tasks? (sample)
ls ~/.openclaw/agents/AGENT_NAME/tasks/*.md 2>/dev/null | head -5 | xargs -I{} head -3 {}
```

**Response if agent not executing anything:**
1. Check `logs/task-watcher-state.json` — is the agent's slot in use by a stale PID?
2. If stale PID: Kill the process, rename `.executing.md` → `.md` to restore to pending
3. If task-watcher itself is stopped: Check `launchd-registry.md` for the cron entry

**Response if backlog is structural (recurring 6+ audits):**
Create a redistribution task for kublai to spread pending tasks to idle agents:

```bash
python3 ~/.openclaw/agents/main/scripts/task_intake.py \
  --title "@kublai Redistribute jochi backlog — 12 consecutive audits, 13 pending" \
  --priority high \
  --body "See logs/routing-audit-trend.json for details"
```

---

### Issue: "AGENT: N task(s) routed but 0 executed — dispatch may be stalled"

**Meaning:** Tasks were created and assigned to this agent, but task-watcher never picked them up. Usually transient (within 5–10min cycle), but persistent across audits indicates a dispatch stall.

**Diagnosis:**

```bash
# Check task-watcher dispatch log
tail -20 ~/.openclaw/agents/main/logs/task-watcher-dispatch.json | python3 -m json.tool

# Was the agent dispatched in the last 15 minutes?
tail -5 ~/.openclaw/agents/main/logs/task-watcher.log.$(date +%Y%m%d%H%M | head -c 10)00 2>/dev/null
```

**Fix:** Usually resolves within next task-watcher cycle (5 min). If persistent after 3 audits, create an ogedei task to investigate the dispatch pipeline.

---

### Issue: "Missed opportunities: N task(s) could have been routed to idle agents"

**Meaning:** Tasks were sent to agents with non-zero queues when other domain-compatible agents had shorter (or zero) queues. This represents wasted capacity.

**Cause:** Almost always explicit routing (`agent=` hardcoded) which bypasses S8 load balancing.

**Response:**

```bash
# See which tasks missed opportunities
python3 -c "
import json
data = json.load(open('logs/routing-audit-latest.json'))
for ex in data.get('missed_opportunities',{}).get('examples',[]):
    print(f\"Task: {ex['task'][:60]}\")
    print(f\"  -> routed_to={ex['routed_to']} (queue={ex['dest_queue']})\")
    print(f\"  -> idle_alternatives={ex['idle_alternatives']}\")
    print(f\"  -> method={ex['method']}\")
"
```

If the routing method is `explicit` and the source is a system script (not a human @mention), it's worth investigating whether the hardcoded routing is still appropriate.

---

### Issue: "RECURRING: N issue(s) unresolved for 3+ consecutive audits — escalation recommended"

**Meaning:** One or more issues have appeared in the `recurring_issues` array for 3+ consecutive audit cycles (approximately every 1 hour). This is the primary escalation trigger.

**Escalation action:**

```bash
# See which issues are recurring and for how long
python3 -c "
import json
trend = json.load(open('logs/routing-audit-trend.json'))
for issue, data in trend['issue_streaks'].items():
    print(f\"{data['consecutive']:2d} consecutive: {issue}\")
" | sort -rn
```

**Escalation thresholds:**

| Consecutive Audits | Duration | Required Action |
|-------------------|----------|-----------------|
| 3 | ~3 hours | File a task for the responsible agent |
| 6 | ~6 hours | File a HIGH priority task with `/horde-debug` skill |
| 12 | ~12 hours | Escalate to kublai for manual intervention |
| 24+ | ~24 hours | CRITICAL — human operator notification via ESCALATION_PROTOCOL.md |

---

## Trend Escalation Rules

`logs/routing-audit-trend.json` tracks consecutive appearances of each issue. The `consecutive` field is the key signal.

### Reading the trend file

```json
{
  "issue_streaks": {
    "jochi: # tasks pending in queue (backlog)": {
      "consecutive": 12,
      "first_seen": "2026-03-12T12:09:34Z",
      "last_seen": "2026-03-12T17:07:14Z"
    }
  }
}
```

**Template syntax:** `#` in issue keys is a placeholder for any number. The trend system normalizes numeric values so "13 tasks pending" and "9 tasks pending" count as the same recurring issue.

### Response escalation ladder

```
consecutive = 1–2: Monitor
consecutive = 3–5: File investigation task (normal priority)
consecutive = 6–11: File HIGH task with /horde-debug skill
consecutive = 12+: Escalate to kublai (manual intervention)
consecutive = 24+: Create human alert in ACTIVE_ALERTS.txt
```

---

## Fix Recipes

### Fix: Auth Failures

```bash
# Identify which agents have bad credentials
for agent in kublai temujin mongke chagatai jochi ogedei tolui; do
    python3 -c "
import json, sys
settings = json.load(open('$HOME/.openclaw/agents/$agent/.claude/settings.json'))
token = settings.get('env',{}).get('ANTHROPIC_AUTH_TOKEN','MISSING')
prefix = token[:15] if token != 'MISSING' else 'MISSING'
print(f'$agent: {prefix}...')
"
done

# Check the auth heartbeat
cat ~/.openclaw/agents/main/logs/auth-heartbeat.json | python3 -m json.tool | head -30
```

Fix procedure: `docs/credential-troubleshooting.md`

---

### Fix: OOM / Process Kills

```bash
# Count active Claude processes (target: < 8)
pgrep -f "claude" | wc -l

# Kill orphaned processes
bash ~/.openclaw/agents/main/scripts/cleanup-orphan-claude.sh

# Check memory pressure
memory_pressure
sysctl vm.swapusage
```

If process count is consistently high: Reduce `MAX_CONCURRENT` in task-watcher.py.

---

### Fix: jochi Backlog (Structural)

The jochi backlog is the most commonly recurring issue because jochi is the default recipient for many system-generated tasks (security, analysis, routing checks). When jochi is slow or unhealthy, these pile up.

**Short-term:** Redistribute pending tasks

```bash
python3 ~/.openclaw/agents/main/scripts/task_intake.py \
  --title "@kublai Emergency redistribute jochi queue — N pending, 12h backlog" \
  --priority high \
  --skill /kurultai-health
```

**Long-term:** Add `/horde-review` and `/horde-debug` to jochi's alternates map so overflow fires sooner when jochi is overloaded. File a temujin task to update `_SKILL_CAPABLE_ALTERNATES` in `task_intake.py`.

---

### Fix: High Explicit Routing Rate

Explicit routing bypasses load balancing (S8). If the rate exceeds 60% and co-occurs with backlogs:

1. Identify which dispatch scripts are hardcoding `agent=` — check `kublai-actions.py`, watchdog scripts, tock handler
2. For system-generated tasks where the agent is appropriate, this is expected behavior
3. For tasks where skill-based routing would be better, remove the hardcoded `agent=` and let the pipeline route via keywords + skill

```bash
# Find hardcoded agent= calls in dispatch scripts
grep -r 'agent="jochi"\|agent="ogedei"\|agent="temujin"' \
  ~/.openclaw/agents/main/scripts/ | grep -v ".pyc"
```

---

## Escalation Thresholds

| Signal | Threshold | Owner | Action |
|--------|-----------|-------|--------|
| Any agent: 100% failure rate | 3 consecutive audits | jochi | Investigate credentials + circuit breaker |
| Queue backlog | 12 consecutive audits | kublai | Manual redistribution + root cause task |
| High explicit routing | 6 consecutive audits + backlog | temujin | Audit `agent=` hardcoding in dispatch scripts |
| Missed opportunities | > 5 per audit | kublai | Review load-balancing configuration |
| All agents failing | Any occurrence | kublai → human | See ESCALATION_PROTOCOL.md |
| Keyword misroute rate | > 15% | jochi | Update `AGENT_KEYWORDS` in `kurultai_paths.py` |

---

## Audit File Locations

| File | Purpose | Update Frequency |
|------|---------|-----------------|
| `logs/routing-audit-latest.json` | Current period analysis | Hourly |
| `logs/routing-audit-trend.json` | Issue streak tracking | Hourly |
| `logs/routing-audit-cooldown.json` | Prevents duplicate audit alerts | Hourly |
| `logs/routing-decisions.jsonl` | Per-task routing log (source of truth) | Per task |
| `logs/routing-metrics-YYYY-MM-DD-HH.json` | Historical hourly snapshots | Hourly |

---

## Related Documentation

- `docs/routing-pipeline-reference.md` — Full 8-stage pipeline with code locations
- `docs/routing-cli-guide.md` — How to test routing manually with `test_routing.py`
- `docs/fleet-failure-triage.md` — Failure category diagnosis and fix procedures
- `docs/credential-troubleshooting.md` — Fix invalid API credentials
- `docs/ESCALATION_PROTOCOL.md` — When and how to escalate to human operator
- `scripts/queue-audit.py` — Generates `routing-audit-latest.json`
- `scripts/circuit_breaker_health.py` — Auto-recovery for OPEN circuit breakers

---

**Document Metadata:**
- Author: Chagatai (Writer)
- Domain: routing_pipeline
- Created: 2026-03-12
- Trigger: Routing audit data exists but no interpretation/response guide existed; jochi backlog at 12 consecutive audits with no documented response path
