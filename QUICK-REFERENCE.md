# Load Balancing: Quick Reference Card

## Files Created

| File | Purpose | Lines |
|------|---------|-------|
| LOAD-BALANCING-DESIGN.md | Full technical design + thresholds | 300 |
| load-balancer-patch.py | Standalone module (import or copy) | 200 |
| INTEGRATION-GUIDE.md | Step-by-step setup instructions | 400 |
| LOAD-BALANCING-EXAMPLES.md | Scenarios + flowcharts + queries | 500 |
| QUICK-REFERENCE.md | This cheatsheet | 100 |

## Core Functions

### 1. Queue Depth Checker

```python
depth = get_agent_queue_depth("temujin", check_neo4j=False)
# Returns: {"agent": "temujin", "filesystem": 8, "neo4j": 9, "total": 9}

# Check if overloaded
max_allowed = AGENT_CAPABILITIES["temujin"]["max_queue_depth"]  # 5
if depth["total"] >= max_allowed:
    print("OVERLOADED")
```

### 2. Rebalancing Logic

```python
should_rebalance, overflow_agent, reason = should_rebalance("temujin", task_text)

if should_rebalance:
    print(f"Route to {overflow_agent}")
    print(f"Reason: {reason}")
else:
    print(f"Route to temujin (primary)")
```

### 3. Integration

```python
def route_task(message, priority="normal"):
    classification = classify_task(message)
    destination = classification['destination']

    # ADD THIS BLOCK:
    if destination != 'subagent':
        should, target, reason = should_rebalance(destination, message)
        if should:
            destination = target
            _log_rebalance_decision(...)

    return route_to_agent(destination, message, priority)
```

## Configuration

### Max Queue Depths

```python
AGENT_CAPABILITIES = {
    "temujin": {"max_queue_depth": 5},    # Small = early rebalancing
    "mongke": {"max_queue_depth": 10},
    "jochi": {"max_queue_depth": 8},
    "ogedei": {"max_queue_depth": 6},
    "chagatai": {"max_queue_depth": 8},
    "kublai": {"max_queue_depth": 3},     # Lead keeps light
}
```

### Overflow Routes

```python
OVERFLOW_ROUTING = {
    ("temujin", "infrastructure"): ("ogedei", "jochi"),      # cascade
    ("temujin", "code review"): ("jochi", None),             # single
    ("temujin", "api discover"): ("mongke", None),
    ("temujin", "testing"): ("jochi", None),
    ("temujin", "deploy"): ("ogedei", None),
}
```

## Decision Trees

### When does rebalancing happen?

```
classification_result == "temujin"?
└─ YES
   └─ queue_depth >= max?
      └─ YES
         └─ task matches overflow_route?
            └─ YES
               └─ overflow_agent has capacity?
                  ├─ YES → REBALANCE to overflow_agent
                  └─ NO → fallback_agent has capacity?
                     ├─ YES → REBALANCE to fallback_agent
                     └─ NO → route to primary (temujin)
            └─ NO → route to primary (temujin)
      └─ NO → route to primary (temujin)
└─ NO → route to primary (result)
```

### Example Path

```
Task: "Build API infrastructure"
│
├─ Classify: "temujin"
├─ Depth: 8 pending (max: 5) ✗ OVERLOADED
├─ Keyword match: "infrastructure" ✓
├─ Overflow to: ogedei
├─ Ogedei depth: 2 (max: 6) ✓ HAS CAPACITY
└─ ROUTE TO: ogedei
```

## Monitoring Commands

### Queue Status

```bash
python3 -c "
from task_router import get_agent_queue_depth, AGENT_CAPABILITIES
for a in ['temujin','mongke','jochi','ogedei','chagatai','kublai']:
    d = get_agent_queue_depth(a)
    m = AGENT_CAPABILITIES[a]['max_queue_depth']
    print(f'{a}: {d[\"total\"]}/{m}')
"
```

### Last 10 Rebalances

```bash
tail -10 logs/routing-rebalanced.jsonl | jq .
```

### Rebalance Rate

```bash
wc -l logs/routing-rebalanced.jsonl logs/routing-decisions.jsonl
# Rebalance % = routing-rebalanced / routing-decisions * 100
```

### Agent-Specific Overflow

```bash
jq 'select(.primary_agent == "temujin")' logs/routing-rebalanced.jsonl
```

## Thresholds Tuning

### Too Many Rebalances? (>30% of tasks)

**Symptom:** Overflow log growing too fast

**Fix:** Increase max_queue_depth thresholds
```python
AGENT_CAPABILITIES["temujin"]["max_queue_depth"] = 10  # Was 5
```

### Not Enough Rebalancing? (<5% of tasks)

**Symptom:** temujin still has 50+ pending, others idle

**Fix:** Lower max_queue_depth thresholds
```python
AGENT_CAPABILITIES["temujin"]["max_queue_depth"] = 3   # Was 5
```

### Overflow Agent Gets Overloaded Too

**Symptom:** ogedei queue also growing

**Fix:** Check if task type is correct
```python
# Maybe "infrastructure" keyword too generic?
# Make it more specific: "deployment infrastructure"
OVERFLOW_ROUTING[("temujin", "deployment infrastructure")] = ("ogedei", "jochi")
```

## Testing

### Test 1: Verify Counting

```bash
python3 -c "from task_router import get_agent_queue_depth; print(get_agent_queue_depth('temujin'))"
```

### Test 2: Verify Rebalancing

```bash
python3 -c "
from task_router import should_rebalance
result = should_rebalance('temujin', 'Build infrastructure')
print('Should rebalance:', result[0])
print('Target:', result[1])
"
```

### Test 3: Full Route

```bash
python3 task-router.py --task "Build API infrastructure" --priority normal
# Check: which agent was routed to?
# Check: was it logged to routing-rebalanced.jsonl?
```

## Rollback Plan

### Step 1: Disable Rebalancing

```python
# In task-router.py, replace route_task with original:
def route_task(message, priority="normal"):
    classification = classify_task(message)
    destination = classification['destination']
    # SKIP the should_rebalance() call
    return route_to_agent(destination, message, priority)
```

### Step 2: Verify

```bash
python3 task-router.py --task "Build infrastructure"
# Should always route to "temujin", not rebalance
```

### Step 3: Full Revert

```bash
git checkout HEAD -- scripts/task-router.py
# Removes all load balancer code
```

## Performance Notes

- **Queue check time:** ~50ms per classification (one filesystem scan)
- **Log write time:** <1ms (async-safe append)
- **Memory overhead:** Negligible (dict lookups only)
- **Recommended caching:** Enable if >100 classifications/minute

## Safety Guarantees

✓ No task loss (routing only, never deletes)
✓ No infinite loops (cascade limited to 1 level)
✓ No deadlocks (no locks used)
✓ Graceful degradation (if all agents full, routes to primary)
✓ Idempotent decisions (same input = same output)

## What Gets Logged

### routing-decisions.jsonl (existing)
Every task classification is logged with:
- method: "llm" or "keyword_fallback"
- destination: "temujin", "mongke", etc.
- complexity: "simple" or "complex"

### routing-rebalanced.jsonl (new)
Only rebalanced tasks are logged with:
- primary_agent: original destination
- overflow_to: final destination (different from primary)
- reason: explanation (overflow/cascade)
- queue depths: before rebalance

## Audit Trail Example

```json
routing-decisions.jsonl:
{
  "ts": "2026-03-04T18:30:45.123456",
  "task": "Build API infrastructure",
  "dest": "temujin",
  "method": "llm"
}

routing-rebalanced.jsonl:
{
  "ts": "2026-03-04T18:30:45.124000",
  "task": "Build API infrastructure",
  "primary_agent": "temujin",
  "overflow_to": "ogedei",
  "reason": "overflow: temujin (8/5) → ogedei (2/6)",
  "primary_queue_depth": 8,
  "overflow_queue_depth": 2
}

Result: Task routed to ogedei, not temujin
```

## Key Decisions

| Decision | Rationale | Tradeoff |
|----------|-----------|----------|
| Filesystem-first count | Fast, no DB dependency | May miss Neo4j-only tasks |
| Separate log file | Easy audit | Two files instead of one |
| Keyword matching | Simple, debuggable | Won't catch all overflow opportunities |
| Single-level cascade | Simple, prevents loops | Limited fallback depth |
| No locks | Fast, no deadlock | Rare stale count edge case |

## Success Metrics (24h target)

- temujin queue: <5 pending (was 93)
- mongke/jochi queues: +3-5 tasks (more work)
- Rebalance rate: 10-20% of all tasks
- Completion time: Same or faster
- Error rate: 0 (no routing errors)

## Contacts & References

- **Design Doc:** LOAD-BALANCING-DESIGN.md
- **Code Module:** load-balancer-patch.py
- **Integration Steps:** INTEGRATION-GUIDE.md
- **Examples:** LOAD-BALANCING-EXAMPLES.md
- **Original Router:** task-router.py (lines 337-345)
- **Neo4j Tracker:** neo4j_task_tracker.py

## Links in Codebase

```
/agent/temujin/tasks/      ← Task queue (counted by get_agent_queue_depth)
/agent/mongke/tasks/
/agent/jochi/tasks/
/agent/ogedei/tasks/
/agent/chagatai/tasks/
/agent/kublai/tasks/

/logs/routing-decisions.jsonl   ← All classifications (existing)
/logs/routing-rebalanced.jsonl  ← Rebalances only (new)

/scripts/task-router.py         ← Main router (integration here)
/scripts/neo4j_task_tracker.py  ← Optional Neo4j check
```

---

**TL;DR:** Copy functions from load-balancer-patch.py → add to task-router.py → modify route_task() → done. Monitor routing-rebalanced.jsonl for decisions.
