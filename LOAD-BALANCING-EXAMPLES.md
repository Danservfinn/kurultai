# Queue-Depth Load Balancing: Examples & Flowcharts

## Example Scenarios

### Scenario 1: Simple Overflow (Infrastructure Task)

**Initial State:**
```
temujin: 8 pending (max: 5) ← OVERLOADED
ogedei:  2 pending (max: 6) ← HAS CAPACITY
jochi:   3 pending (max: 8) ← BACKUP
```

**Task:** "Build a deployment pipeline infrastructure"

**Pipeline:**
```
1. Classify
   LLM: "temujin" ✓

2. Check Queue Depth
   temujin depth = 8
   temujin max = 5
   8 >= 5? YES → OVERLOADED

3. Check Overflow Routes
   Task contains "infrastructure"
   OVERFLOW_ROUTING[("temujin", "infrastructure")] = ("ogedei", "jochi")

4. Check Overflow Agent Capacity
   ogedei depth = 2
   ogedei max = 6
   2 < 6? YES → HAS CAPACITY

5. Route Decision
   original: temujin
   overflow_to: ogedei
   reason: "overflow: temujin (8/5) → ogedei (2/6)"

6. Route to ogedei (not temujin)

7. Log to routing-rebalanced.jsonl
   ts: 2026-03-04T18:30:45
   primary_agent: temujin
   overflow_to: ogedei
   reason: "overflow: temujin (8/5) → ogedei (2/6)"
```

**Result:**
```
temujin: 8 pending (would have been 9)
ogedei:  3 pending (was 2)  ← REBALANCED
```

---

### Scenario 2: Cascade (Both Overflow & Fallback Full)

**Initial State:**
```
temujin: 8 pending (max: 5) ← OVERLOADED
ogedei:  6 pending (max: 6) ← AT LIMIT
jochi:   5 pending (max: 8) ← HAS CAPACITY
```

**Task:** "Build deployment infrastructure"

**Pipeline:**
```
1-3. [Same as Scenario 1]

4. Check Overflow Agent Capacity
   ogedei depth = 6
   ogedei max = 6
   6 < 6? NO → NO CAPACITY

5. Check Fallback Agent
   OVERFLOW_ROUTING[("temujin", "infrastructure")] = ("ogedei", "jochi")
   fallback = jochi

   jochi depth = 5
   jochi max = 8
   5 < 8? YES → HAS CAPACITY

6. Route Decision
   original: temujin
   overflow_to: jochi (cascade from ogedei)
   reason: "cascade: ogedei full (6/6) → jochi (5/8)"

7. Route to jochi (not temujin or ogedei)

8. Log to routing-rebalanced.jsonl
   primary_agent: temujin
   overflow_to: jochi
   reason: "cascade: ogedei full (6/6) → jochi (5/8)"
```

**Result:**
```
temujin: 8 pending (would have been 9)
ogedei:  6 pending (unchanged)
jochi:   6 pending (was 5)  ← REBALANCED
```

---

### Scenario 3: No Rebalancing (Primary Has Capacity)

**Initial State:**
```
temujin: 3 pending (max: 5) ← HAS CAPACITY
```

**Task:** "Fix login bug"

**Pipeline:**
```
1. Classify
   LLM: "temujin" ✓

2. Check Queue Depth
   temujin depth = 3
   temujin max = 5
   3 >= 5? NO → HAS CAPACITY

3. Should Rebalance?
   return False, None, "primary has capacity"

4. Route to temujin (primary)

5. No rebalance decision logged
```

**Result:**
```
temujin: 4 pending (was 3)
[No entry in routing-rebalanced.jsonl]
```

---

### Scenario 4: No Overflow Route (Can't Rebalance)

**Initial State:**
```
temujin: 8 pending (max: 5) ← OVERLOADED
```

**Task:** "Document the API"

**Pipeline:**
```
1. Classify
   LLM: "chagatai" (writing task)

2. Check Queue Depth
   chagatai depth = 5
   chagatai max = 8
   5 >= 8? NO → HAS CAPACITY

3. Should Rebalance?
   return False, None, "primary has capacity"

4. Route to chagatai

5. No rebalance (chagatai not overloaded)
```

**Result:**
```
chagatai: 6 pending (was 5)
[No entry in routing-rebalanced.jsonl]

Note: temujin NOT involved in this task.
      Only the primary agent's capacity matters.
```

---

### Scenario 5: No Fallback Available (All Full)

**Initial State:**
```
temujin: 8 pending (max: 5) ← OVERLOADED
ogedei:  6 pending (max: 6) ← AT LIMIT
jochi:   8 pending (max: 8) ← AT LIMIT
```

**Task:** "Build infrastructure"

**Pipeline:**
```
1-2. [Classify + Check temujin is overloaded]

3. Check Overflow Routes
   Task contains "infrastructure"
   overflow_agent = ogedei, fallback = jochi

4. Check Overflow Agent Capacity
   ogedei depth = 6, max = 6
   NO CAPACITY

5. Check Fallback Agent Capacity
   jochi depth = 8, max = 8
   NO CAPACITY

6. Route Decision
   should_rebalance = False
   reason: "no overflow route available"

7. Route to temujin (primary, graceful degradation)

8. No rebalance logged
```

**Result:**
```
temujin: 9 pending (was 8)
[No entry in routing-rebalanced.jsonl]

WARNING: System is saturated. Consider:
  - Increasing max_queue_depth thresholds
  - Adding more agents
  - Spawning subagents
```

---

## Decision Flowchart

```
START: route_task(message, priority)
  │
  ├─→ classification = classify_task(message)
  │   destination = classification['destination']
  │
  ├─→ destination == 'subagent'?
  │   │
  │   YES──→ route_to_subagent() → RETURN
  │   │
  │   NO
  │   │
  ├─→ depth = get_agent_queue_depth(destination)
  │   max = AGENT_CAPABILITIES[destination]['max_queue_depth']
  │   │
  ├─→ depth['total'] >= max?
  │   │
  │   NO──→ route_to_agent(destination) → RETURN
  │   │
  │   YES (OVERLOADED)
  │   │
  ├─→ Check OVERFLOW_ROUTING
  │   for (primary, keyword), (overflow, fallback) in table:
  │     if primary == destination and keyword in message:
  │       │
  │       ├─→ overflow_depth = get_agent_queue_depth(overflow)
  │       │   overflow_max = AGENT_CAPABILITIES[overflow]['max_queue_depth']
  │       │   │
  │       ├─→ overflow_depth['total'] < overflow_max?
  │       │   │
  │       │   YES──→ REBALANCE to overflow
  │       │   │      Log decision
  │       │   │      route_to_agent(overflow) → RETURN
  │       │   │
  │       │   NO (FALLBACK)
  │       │   │
  │       ├─→ fallback != None?
  │       │   │
  │       │   YES
  │       │   │
  │       │   ├─→ fallback_depth = get_agent_queue_depth(fallback)
  │       │   │    fallback_max = AGENT_CAPABILITIES[fallback]['max_queue_depth']
  │       │   │    │
  │       │   │    ├─→ fallback_depth['total'] < fallback_max?
  │       │   │    │   │
  │       │   │    │   YES──→ REBALANCE to fallback
  │       │   │    │   │      Log decision
  │       │   │    │   │      route_to_agent(fallback) → RETURN
  │       │   │    │   │
  │       │   │    │   NO (CONTINUE)
  │       │   │    │
  │       │   NO (CONTINUE)
  │       │
  ├─→ No overflow route found
  │   │
  ├─→ route_to_agent(destination)  [Degrade gracefully]
  │   │
  └─→ RETURN
```

---

## State Transition Diagram

```
Queue State Machine (per agent)

                    ┌─────────────┐
                    │   OK        │
                    │ (< max)     │
                    └──────┬──────┘
                           │
              [New task arrives]
              depth == max?
                           │
                    NO────┘
                           │
                           ▼
                    ┌─────────────┐
                    │ OVERLOADED  │
                    │ (>= max)    │
                    └──────┬──────┘
                           │
              [Check overflow route]
                           │
           ┌───────────────┼───────────────┐
           │               │               │
        Found         Not found         Found but
        & overflow                      overflow
        has capacity                    full too
           │               │               │
           ▼               ▼               ▼
      Rebalance      Degrade        Check
      to overflow    gracefully      fallback
         │               │               │
         │               │        ┌──────┘
         │               │        │
         ▼               ▼        ▼
     Route to         Route to  Fallback
     overflow         primary   has cap?
     agent            agent         │
                                    ├─ YES → Rebalance to fallback
                                    │
                                    └─ NO → Degrade (route to primary)


Legend:
  [  ] = Decision/check
  →    = Transition
  ◆    = Action
```

---

## Data Structure Examples

### AGENT_CAPABILITIES

```python
AGENT_CAPABILITIES = {
    "temujin": {
        "primary": ["code", "build", "fix", "deploy", "apis"],
        "secondary": ["infrastructure", "automation"],
        "max_queue_depth": 5,
    },
    ...
}

# Accessing:
max_depth = AGENT_CAPABILITIES["temujin"]["max_queue_depth"]  # 5
primary = AGENT_CAPABILITIES["jochi"]["primary"]  # ["testing", "security", ...]
```

### OVERFLOW_ROUTING

```python
OVERFLOW_ROUTING = {
    ("temujin", "infrastructure"): ("ogedei", "jochi"),
    ("temujin", "code review"): ("jochi", None),
    ...
}

# Accessing:
for (primary, keyword), (overflow, fallback) in OVERFLOW_ROUTING.items():
    if primary == "temujin" and keyword in task_text:
        # Found matching route
        print(f"Overflow to {overflow}, fallback to {fallback}")
```

### Queue Depth Return Value

```python
depth = get_agent_queue_depth("temujin", check_neo4j=False)

# Result:
{
    "agent": "temujin",
    "filesystem": 8,      # 8 .md files without .executing/.completed/.done
    "neo4j": 9,           # 9 Task nodes with status='PENDING'
    "total": 9            # max(filesystem, neo4j)
}

# Accessing:
if depth["total"] >= AGENT_CAPABILITIES["temujin"]["max_queue_depth"]:
    print("Overloaded!")
```

### Rebalance Decision Object

```python
rebalance_decision = {
    "original": "temujin",
    "overflow_to": "ogedei",
    "reason": "overflow: temujin (8/5) → ogedei (2/6)"
}

# Used for logging
_log_rebalance_decision(rebalance_decision, classification, result)
```

### Log Entry (routing-rebalanced.jsonl)

```json
{
  "ts": "2026-03-04T18:30:45.123456",
  "task": "Build deployment infrastructure",
  "primary_agent": "temujin",
  "overflow_to": "ogedei",
  "reason": "overflow: temujin (8/5) → ogedei (2/6)",
  "primary_queue_depth": 8,
  "overflow_queue_depth": 2,
  "task_file": "/Users/kublai/.openclaw/agents/main/agent/ogedei/tasks/normal-1772665880.md",
  "classification_method": "llm"
}
```

---

## Configuration Tweaking Examples

### Increase temujin Threshold (Less Aggressive Rebalancing)

```python
AGENT_CAPABILITIES["temujin"]["max_queue_depth"] = 10  # Was 5
# Now temujin can queue up to 10 before rebalancing kicks in
```

### Add New Overflow Route

```python
OVERFLOW_ROUTING[("temujin", "testing")] = ("jochi", None)
# Now "testing" tasks overflow from temujin to jochi
```

### Add Cascade for Code Review

```python
OVERFLOW_ROUTING[("temujin", "code review")] = ("jochi", "chagatai")
# Code review: temujin → jochi → chagatai
```

### Disable Rebalancing Temporarily

```python
for agent in AGENT_CAPABILITIES:
    AGENT_CAPABILITIES[agent]["max_queue_depth"] = 999
# All agents have 999 capacity = no rebalancing
```

---

## Monitoring Queries

### Queue Status Dashboard

```bash
python3 << 'EOF'
from task_router import get_agent_queue_depth, AGENT_CAPABILITIES

agents = ["temujin", "mongke", "jochi", "ogedei", "chagatai", "kublai"]
print("\nQUEUE STATUS DASHBOARD")
print("=" * 70)
print(f"{'Agent':<12} {'Pending':<10} {'Max':<10} {'%':<10} {'Status':<20}")
print("-" * 70)

for agent in agents:
    depth = get_agent_queue_depth(agent)
    max_d = AGENT_CAPABILITIES[agent]["max_queue_depth"]
    pct = 100 * depth["total"] / max_d

    if pct >= 100:
        status = "OVERLOADED"
    elif pct >= 80:
        status = "HIGH"
    else:
        status = "OK"

    print(f"{agent:<12} {depth['total']:<10} {max_d:<10} {pct:<10.1f} {status:<20}")

print("=" * 70)
EOF
```

### Rebalance Activity Log

```bash
# Last 10 rebalances
tail -10 /Users/kublai/.openclaw/agents/main/logs/routing-rebalanced.jsonl | jq .

# Rebalances in last 1 hour
grep -i '"primary_agent": "temujin"' \
  /Users/kublai/.openclaw/agents/main/logs/routing-rebalanced.jsonl | \
  jq -s 'length'

# Breakdown by overflow target
jq -r '.overflow_to' \
  /Users/kublai/.openclaw/agents/main/logs/routing-rebalanced.jsonl | \
  sort | uniq -c | sort -rn
```

---

## Common Issues & Fixes

### Issue: No Rebalancing Despite Overloaded Agent

**Cause:** Task doesn't match any overflow route patterns

**Fix:** Add entry to OVERFLOW_ROUTING:
```python
OVERFLOW_ROUTING[("temujin", "your_keyword")] = ("target_agent", "fallback")
```

### Issue: Rebalancing to Wrong Agent

**Cause:** Keyword pattern is too generic and matches unintended tasks

**Fix:** Make keyword pattern more specific:
```python
# Bad: ("temujin", "infrastructure") matches "build infrastructure" AND "infra setup"
# Good: ("temujin", "deployment infrastructure") is more specific
```

### Issue: Cascade is Too Deep

**Cause:** Fallback agent also overloaded

**Current behavior:** Routes to primary agent (graceful degradation)

**Fix:** Add more agents or increase max_queue_depth thresholds

### Issue: Performance is Slow After Adding Load Balancer

**Cause:** get_agent_queue_depth() scans filesystem on every classification

**Fix:** Add caching:
```python
from functools import lru_cache
import time

cache_timestamp = time.time()

@lru_cache(maxsize=10)
def get_agent_queue_depth_cached(agent):
    if time.time() - cache_timestamp > 5:  # 5s TTL
        get_agent_queue_depth_cached.cache_clear()
    return get_agent_queue_depth(agent, check_neo4j=False)
```

---

## Success Indicators (After 24h)

Check these metrics to verify system is working:

```bash
# 1. temujin queue has stabilized at ~5
jq '.primary_queue_depth' routing-rebalanced.jsonl | tail -20 | sort | uniq -c

# 2. Overall rebalance rate is 10-20%
lines_total=$(wc -l < routing-decisions.jsonl)
lines_rebalanced=$(wc -l < routing-rebalanced.jsonl)
echo "Rebalance rate: $(( lines_rebalanced * 100 / lines_total ))%"

# 3. Overflow agents (ogedei, jochi) queues have grown
# Compare initial vs. current via dashboard query

# 4. No errors in logs
grep -i 'error\|exception' routing-rebalanced.jsonl | wc -l
# Should be 0
```

---

## Implementation Checklist

- [ ] Read LOAD-BALANCING-DESIGN.md
- [ ] Copy functions from load-balancer-patch.py or INTEGRATION-GUIDE.md Section B
- [ ] Add AGENT_CAPABILITIES dict (Section A)
- [ ] Add OVERFLOW_ROUTING dict (Section A)
- [ ] Modify route_task() function (Section C)
- [ ] Create `/logs/routing-rebalanced.jsonl` (auto-created on first write)
- [ ] Test with 5 manual tasks via CLI
- [ ] Monitor for 24 hours
- [ ] Adjust thresholds if needed
- [ ] Document any custom changes
