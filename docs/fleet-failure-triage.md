# Fleet Failure Triage Runbook

**Last Updated:** 2026-03-12
**Trigger:** Watchdog reports `HIGH_FAILURE_RATE` (>50% fleet-wide) for 2+ consecutive ticks
**Owner:** Any agent or operator responding to throughput anomalies

---

## Quick Triage (Under 2 Minutes)

Run this first to identify the failure category:

```bash
# 1. What's failing? Category breakdown (last 2h)
python3 ~/.openclaw/agents/main/scripts/failed-task-review.py --patterns

# 2. Which agents are affected?
tail -50 ~/.openclaw/agents/main/logs/failure-patterns.jsonl | \
  python3 -c "import sys,json,collections; c=collections.Counter(); [c.update({json.loads(l).get('agent','?'):1}) for l in sys.stdin]; print(dict(c))"

# 3. What's the median failure duration?
tail -50 ~/.openclaw/agents/main/logs/failure-patterns.jsonl | \
  python3 -c "import sys,json; ds=[float(json.loads(l).get('duration','0s').replace('s','')) for l in sys.stdin]; print(f'Median: {sorted(ds)[len(ds)//2]:.0f}s, Range: {min(ds):.0f}-{max(ds):.0f}s')"
```

**Decision tree based on median failure duration:**

| Duration | Likely Cause | Jump To |
|----------|-------------|---------|
| < 10s | Auth/credential failure | [Auth Failures](#auth-failures) |
| 10-90s | Process crash or OOM kill | [Claude Code Crashes](#claude-code-crashes) |
| 90-300s | Task timeout (too complex) | [Timeouts](#timeouts) |
| > 300s | Stale lock or hung process | [Stale Processes](#stale-processes) |

**Decision tree based on dominant failure category:**

| Category | % of Failures | Jump To |
|----------|--------------|---------|
| `unknown` | >30% | [Unknown Failures](#unknown-failures) |
| `timeout` | >30% | [Timeouts](#timeouts) |
| `claude_code_crash` | >30% | [Claude Code Crashes](#claude-code-crashes) |
| `auth_error` | Any | [Auth Failures](#auth-failures) |
| `rate_limit` | >10% | [Rate Limits](#rate-limits) |
| `model_error` | >10% | [Model Errors](#model-errors) |

---

## Category Diagnostics

### Unknown Failures

**What it means:** The failure classifier in `failed-task-review.py` couldn't match the error text to any known pattern. This is the #1 failure category (38% of all failures as of 2026-03-12).

**Common root causes:**
1. **Exit code -9 (SIGKILL):** Process was killed by OS (usually OOM or system resource pressure)
2. **Empty output:** Agent spawned but produced no output before dying
3. **New error patterns:** A failure mode not yet in `FAILURE_CATEGORIES`

**Diagnostic steps:**

```bash
# Check for OOM kills in system log (last 1h)
log show --predicate 'eventMessage contains "killed"' --last 1h --style compact 2>/dev/null | head -20

# Check memory pressure
memory_pressure

# Check swap usage
sysctl vm.swapusage

# Look at actual error text in recent unknown failures
tail -20 ~/.openclaw/agents/main/logs/failure-patterns.jsonl | \
  python3 -c "import sys,json; [print(json.loads(l).get('title',''),'-',json.loads(l).get('duration','')) for l in sys.stdin if json.loads(l).get('category')=='unknown']"
```

**Fix actions:**
- If OOM: Run `cleanup-orphan-claude.sh` to kill orphaned Claude processes
- If empty output: Check auth credentials (see [Auth Failures](#auth-failures))
- If new pattern: Add regex to `FAILURE_CATEGORIES` in `scripts/failed-task-review.py` (~line 40)

---

### Claude Code Crashes

**What it means:** The Claude Code subprocess exited with a non-zero code (often -9 or -11). Accounts for 27% of failures.

**Common root causes:**
1. **Memory exhaustion:** Too many concurrent Claude processes
2. **Context overflow:** Task prompt too large for model context
3. **Node.js crash:** Underlying Node runtime issue

**Diagnostic steps:**

```bash
# Count active Claude processes (should be < 8)
pgrep -f "claude" | wc -l

# Check per-process memory (top consumers)
ps aux | grep claude | sort -k6 -rn | head -5

# Check for core dumps
ls /cores/ 2>/dev/null
```

**Fix actions:**
- Kill orphaned processes: `bash ~/.openclaw/agents/main/scripts/cleanup-orphan-claude.sh`
- If persistent: Reduce concurrent agent dispatch (lower `MAX_CONCURRENT` in task-watcher.py)
- If context overflow: Break large tasks into smaller subtasks

---

### Timeouts

**What it means:** Task exceeded the execution timeout (DEFAULT=1800s). Accounts for 28% of failures.

**Common root causes:**
1. **Task too broad:** "Bring to production" or "investigate everything" style tasks
2. **Blocked on external resource:** Neo4j/Redis down, API unreachable
3. **Infinite loop in skill:** Agent stuck in brainstorming/planning cycle

**Diagnostic steps:**

```bash
# Check Neo4j availability
python3 -c "from neo4j import GraphDatabase; d=GraphDatabase.driver('bolt://localhost:7687'); d.verify_connectivity(); print('OK')" 2>&1

# Check Redis availability
redis-cli ping

# Check for stuck executing tasks
find ~/.openclaw/agents/*/tasks -name "*.executing.md" -mmin +30 2>/dev/null
```

**Fix actions:**
- If external resource down: Fix resource first, tasks will succeed on retry
- If task too broad: Apply mega-task decomposition (break into 2-3 subtasks)
- If stuck agent: Kill the specific process and clear `.executing.md` marker

---

### Auth Failures

**What it means:** API credential rejected. Usually the fastest failures (< 10s).

**Diagnostic steps:**

```bash
# Run auth health preflight
python3 ~/.openclaw/agents/main/scripts/auth_health_preflight.py

# Check each agent's token prefix
for agent in kublai temujin mongke chagatai jochi ogedei tolui; do
    token=$(python3 -c "import json; print(json.load(open('$HOME/.openclaw/agents/$agent/.claude/settings.json')).get('env',{}).get('ANTHROPIC_AUTH_TOKEN','MISSING')[:12])" 2>/dev/null)
    echo "$agent: $token..."
done
```

**Fix actions:**
- See [credential-troubleshooting.md](credential-troubleshooting.md) for full fix procedure
- Key points: Replace `sk-sp-*` tokens with valid `sk-ant-*` or Z.AI tokens

---

### Rate Limits

**What it means:** API provider throttling requests. Usually intermittent.

**Diagnostic steps:**

```bash
# Check recent rate limit entries
grep "rate_limit" ~/.openclaw/agents/main/logs/failure-patterns.jsonl | tail -10

# Check if concentrated on one agent (shared key issue)
grep "rate_limit" ~/.openclaw/agents/main/logs/failure-patterns.jsonl | \
  python3 -c "import sys,json,collections; c=collections.Counter(); [c.update({json.loads(l).get('agent','?'):1}) for l in sys.stdin]; print(dict(c))"
```

**Fix actions:**
- If one agent: That agent's key may be shared with another service — isolate keys
- If fleet-wide: Reduce concurrent dispatches or switch to provider with higher limits
- Retry is usually sufficient — rate limits are transient

---

### Model Errors

**What it means:** The LLM model returned an error (invalid model name, overloaded, etc).

**Diagnostic steps:**

```bash
# Check model configuration consistency
python3 ~/.openclaw/agents/main/scripts/agents_config.py 2>/dev/null

# Verify model in claude-agent wrapper
grep -A2 "model" ~/.local/bin/claude-agent | head -10
```

**Fix actions:**
- Verify model name is valid (e.g., `claude-opus-4-6`, not a deprecated name)
- Check the 3-layer model config (see MEMORY.md → Model Configuration)

---

### Stale Processes

**What it means:** Agent process is alive but not producing output. Usually shows as timeout.

**Diagnostic steps:**

```bash
# Find executing tasks older than 30 minutes
find ~/.openclaw/agents/*/tasks -name "*.executing.md" -mmin +30 2>/dev/null

# Check if the PID is actually running
# (PIDs are logged in task-watcher-state.json)
cat ~/.openclaw/agents/main/logs/task-watcher-state.json | python3 -m json.tool | head -20
```

**Fix actions:**
- Run subprocess health check: `python3 ~/.openclaw/agents/main/scripts/subprocess_health_check.py` (if exists)
- Kill specific stale PIDs and clear `.executing.md` files
- Circuit breaker should auto-recover via `circuit_breaker_health.py`

---

## Escalation Thresholds

| Condition | Action | Reference |
|-----------|--------|-----------|
| >50% failure rate for 15min (3 ticks) | Auto-escalate to kublai | ESCALATION_PROTOCOL.md |
| Single agent at 0% for 2h | Investigate credentials + reassign tasks | credential-troubleshooting.md |
| All agents failing simultaneously | CRITICAL — likely infrastructure issue | Check Neo4j, Redis, API provider |
| "unknown" >50% of failures | Improve failure classifier first | Add patterns to `failed-task-review.py` |

---

## Historical Patterns (Reference)

| Date | Pattern | Root Cause | Resolution |
|------|---------|------------|------------|
| 2026-03-08 | 15h agent blackout | DashScope credentials in settings.json | Replaced with valid Z.AI tokens |
| 2026-03-11 | Auth preflight missing | No credential check before subagent spawn | Added auth_health_preflight.py |
| 2026-03-12 | 74% fleet-wide failure | Unknown (60-70s duration cluster) | Under investigation |

---

## Related Documentation

- [ESCALATION_PROTOCOL.md](ESCALATION_PROTOCOL.md) — When and how to escalate
- [credential-troubleshooting.md](credential-troubleshooting.md) — Fix invalid API credentials
- [auth-health-preflight.md](auth-health-preflight.md) — Credential validation before dispatch
- [heartbeat-troubleshooting.md](heartbeat-troubleshooting.md) — Tick gap diagnosis
- `scripts/failed-task-review.py` — Failure classification engine
- `scripts/circuit_breaker_health.py` — Circuit breaker deadlock recovery
- `scripts/cleanup-orphan-claude.sh` — Orphaned process cleanup
