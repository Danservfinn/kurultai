# EXECUTING_NO_OUTPUT — Diagnostic & Recovery Guide

**Version:** 1.0
**Date:** 2026-03-10
**Author:** Chagatai (Kurultai Content Specialist)
**Severity:** CRITICAL when consecutive ≥6

---

## What Is EXECUTING_NO_OUTPUT?

**Definition:** Agents have tasks marked `.executing` but zero completions in the past 2 hours.

**What it means:**
- Tasks are being dispatched (picked up by agents)
- Agents are not producing completions
- Fleet is stuck in a "spinning" state

**Detection script:** `scripts/throughput_anomaly.py` (runs every tick)

---

## Symptom Checklist

| Symptom | Indicates |
|---------|-----------|
| `.executing` files exist in agent task dirs | Tasks dispatched |
| Zero entries in `logs/task-events.jsonl` with `event: COMPLETED` (2h window) | No completions |
| `logs/throughput-anomaly-state.json` shows `consecutive ≥ 6` | CRITICAL state |
| Gateway process running (`pgrep openclaw-gateway`) | Not gateway crash |
| Redis UP, Neo4j status variable | Check infrastructure |

---

## Root Cause Analysis

### Cause 1: Agent Model Stall (Most Common)

**Symptoms:**
- Same agents stuck with `.executing` tasks
- Their log shows "model timeout" or "API rate limit"
- Tasks are complex (e.g., "implement full feature" vs "fix bug")

**Diagnosis:**
```bash
# Check which agents are stuck
for agent in temujin mongke chagatai jochi ogedei tolui; do
    count=$(ls ~/.openclaw/agents/$agent/tasks/*.executing* 2>/dev/null | wc -l)
    if [ $count -gt 0 ]; then
        echo "$agent: $count stuck"
    fi
done

# Check their recent logs for model errors
tail -100 ~/.openclaw/agents/$agent/logs/session*.jsonl | grep -i "error\|timeout\|rate"
```

**Recovery:**
1. Escalate stuck tasks to kublai for redistribution
2. Check agent model config (`~/.openclaw/agents/$agent/.claude/settings.json`)
3. If model is failing, switch to fallback provider
4. Consider reducing task complexity (mega-task decomposition)

### Cause 2: Task-Watcher Stall

**Symptoms:**
- Tasks pending but not being dispatched to `.executing`
- `launchctl list | grep task-watcher` shows not running
- Recent `.executing` tasks are old (>30 min)

**Diagnosis:**
```bash
# Check task-watcher status
launchctl list | grep task-watcher

# Check last .executing file timestamp
ls -lt ~/.openclaw/agents/*/tasks/*.executing* 2>/dev/null | head -1
```

**Recovery:**
```bash
# Restart task-watcher
launchctl kickstart -k gui/$(id -u)/ai.openclaw.task-watcher

# Or manually trigger dispatch
~/.openclaw/agents/main/scripts/task-watcher.py
```

### Cause 3: Mega-Task Deadlock

**Symptoms:**
- 1-2 agents have single `.executing` task for >60 minutes
- Task title contains "and", "plus", "also" (multiple deliverables)
- Agent CPU near 0% (not processing, just waiting)

**Diagnosis:**
```bash
# Find long-running .executing tasks
find ~/.openclaw/agents/*/tasks -name "*.executing*.md" -mtime +1h -exec basename {} \;
```

**Recovery:**
1. Kill the stuck task (move to `.stale`)
2. Decompose into 2-3 smaller subtasks
3. Requeue with concrete deliverables

### Cause 4: Completion Gate Loop

**Symptoms:**
- `.executing` tasks sit forever
- `logs/completion-audit.jsonl` shows repeated verification failures
- Tasks have `.verified` or `.revision-N` suffixes

**Diagnosis:**
```bash
# Check for revision loops
ls ~/.openclaw/agents/*/tasks/*.revision-*.md 2>/dev/null | wc -l

# Check completion audit
tail -20 ~/.openclaw/agents/main/logs/completion-audit.jsonl
```

**Recovery:**
```bash
# Force-complete stuck revision tasks
# (Manual intervention: review task, mark .done if actually complete)
```

---

## Escalation Thresholds

| Consecutive Ticks | Duration | Severity | Action |
|------------------|----------|----------|--------|
| 1-2 | 5-10 min | MEDIUM | Log only |
| 3-5 | 15-25 min | HIGH | Create task for Ogedei |
| 6+ | 30+ min | CRITICAL | Escalate to Kublai, consider model switchover |

**Current state tracking:**
```bash
cat ~/.openclaw/agents/main/logs/throughput-anomaly-state.json
```

---

## Quick Recovery Script

```bash
#!/bin/bash
# quick-executing-recovery.sh — First-response for EXECUTING_NO_OUTPUT

echo "=== EXECUTING_NO_OUTPUT Quick Recovery ==="
echo

# 1. Check which agents have stuck tasks
echo "1. Stuck agents:"
for agent in temujin mongke chagatai jochi ogedei tolui; do
    count=$(ls ~/.openclaw/agents/$agent/tasks/*.executing* 2>/dev/null | wc -l)
    if [ $count -gt 0 ]; then
        echo "   $agent: $count stuck"
    fi
done
echo

# 2. Check task-watcher
echo "2. Task-watcher status:"
if pgrep -f "task-watcher" > /dev/null; then
    echo "   RUNNING"
else
    echo "   NOT RUNNING - restarting..."
    launchctl kickstart -k gui/$(id -u)/ai.openclaw.task-watcher
fi
echo

# 3. Check infrastructure
echo "3. Infrastructure:"
redis-cli ping 2>/dev/null && echo "   Redis: UP" || echo "   Redis: DOWN"
# Neo4j check requires credentials
echo

# 4. Recent completions check
echo "4. Recent completions (last 2h):"
COMPLETED=$(tail -1000 ~/.openclaw/agents/main/logs/task-events.jsonl 2>/dev/null | \
    grep '"event":"COMPLETED"' | tail -10 | wc -l)
echo "   Found: $COMPLETED in sample"
echo

# 5. Suggest next action
echo "=== RECOMMENDATION ==="
if [ $COMPLETED -eq 0 ]; then
    echo "No recent completions detected."
    echo "Next: Check agent models for rate limiting / timeouts"
    echo "      Consider: /kurultai-model-switcher skill"
else
    echo "Completions detected — anomaly may be clearing."
    echo "Monitor for 2-3 more ticks."
fi
```

---

## Related Files

| File | Purpose |
|------|---------|
| `scripts/throughput_anomaly.py` | Detection script |
| `logs/throughput-anomaly-state.json` | Persistent tracking |
| `logs/task-events.jsonl` | Completion ledger |
| `agents/*/tasks/*.executing*.md` | Stuck tasks |
| `docs/heartbeat-troubleshooting.md` | Tick-level diagnostics |

## Related Documentation

- `docs/reflection-pipeline-reference.md` — Full pipeline overview
- `docs/heartbeat-troubleshooting.md` — Tick gap diagnosis
- `memory/model-fixes.md` — Model configuration history

---

## Prevention

1. **Mega-task decomposition**: Break "bring to production" into 2-3 subtasks
2. **Model diversity**: Use different providers per agent to avoid single-point failure
3. **Timeout awareness**: Set realistic task deadlines based on complexity
4. **Monitor anomaly state**: Check `throughput-anomaly-state.json` before it hits CRITICAL

---

## Notes

- EXECUTING_NO_OUTPUT is measured over a 2-hour completion window
- A single complex task can trigger this if it blocks an agent
- The anomaly auto-clears once any completion occurs
- 167+ consecutive occurrences indicate systemic model failure (check credentials)
