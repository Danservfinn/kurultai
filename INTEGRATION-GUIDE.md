# Load Balancer Integration Guide

## Quick Start

### Option 1: Inline Integration (Recommended)

Add these 3 sections to `task-router.py`:

#### Section A: Capability Matrix (after imports, before LLM_SYSTEM_PROMPT)

```python
# ============================================================
# LOAD BALANCER — Queue-depth aware routing
# ============================================================

AGENT_CAPABILITIES = {
    "temujin": {
        "primary": ["code", "build", "fix", "deploy", "apis"],
        "secondary": ["infrastructure", "automation"],
        "max_queue_depth": 5,
    },
    "mongke": {
        "primary": ["research", "analysis", "discovery"],
        "secondary": [],
        "max_queue_depth": 10,
    },
    "chagatai": {
        "primary": ["writing", "documentation", "content"],
        "secondary": [],
        "max_queue_depth": 8,
    },
    "jochi": {
        "primary": ["testing", "security", "validation", "review"],
        "secondary": ["code review"],
        "max_queue_depth": 8,
    },
    "ogedei": {
        "primary": ["ops", "monitoring", "infrastructure"],
        "secondary": ["automation"],
        "max_queue_depth": 6,
    },
    "kublai": {
        "primary": ["coordination", "triage", "system-wide"],
        "secondary": [],
        "max_queue_depth": 3,
    },
}

OVERFLOW_ROUTING = {
    ("temujin", "infrastructure"): ("ogedei", "jochi"),
    ("temujin", "code review"): ("jochi", None),
    ("temujin", "api discover"): ("mongke", None),
    ("temujin", "testing"): ("jochi", None),
    ("temujin", "deploy"): ("ogedei", None),
}

REBALANCE_LOG = "/Users/kublai/.openclaw/agents/main/logs/routing-rebalanced.jsonl"
```

#### Section B: Queue Depth Functions (after _log_routing_decision)

```python
def get_agent_queue_depth(agent, check_neo4j=False):
    """Count pending tasks for an agent (filesystem + optionally Neo4j)."""
    base = "/Users/kublai/.openclaw/agents/main/agent"
    task_dir = f"{base}/{agent}/tasks"
    fs_count = 0

    if os.path.isdir(task_dir):
        for fname in os.listdir(task_dir):
            if not any(suffix in fname for suffix in [".executing", ".completed", ".done"]):
                fs_count += 1

    neo4j_count = 0
    if check_neo4j:
        try:
            from neo4j_task_tracker import get_tracker
            tracker = get_tracker()
            with tracker.driver.session() as session:
                result = session.run(
                    "MATCH (t:Task {agent: $agent, status: 'PENDING'}) RETURN count(t) AS cnt",
                    agent=agent
                )
                record = result.single()
                neo4j_count = record["cnt"] if record else 0
        except Exception:
            pass

    return {
        "agent": agent,
        "filesystem": fs_count,
        "neo4j": neo4j_count,
        "total": max(fs_count, neo4j_count)
    }


def should_rebalance(primary_agent, task_keywords):
    """Check if primary agent is overloaded + task can overflow elsewhere."""
    if primary_agent not in AGENT_CAPABILITIES:
        return False, None, "unknown agent"

    depth = get_agent_queue_depth(primary_agent, check_neo4j=False)
    max_allowed = AGENT_CAPABILITIES[primary_agent]["max_queue_depth"]

    if depth["total"] < max_allowed:
        return False, None, "primary has capacity"

    task_lower = task_keywords.lower()

    for (primary, keywords_pattern), (overflow_agent, fallback_agent) in OVERFLOW_ROUTING.items():
        if primary == primary_agent and keywords_pattern in task_lower:
            overflow_depth = get_agent_queue_depth(overflow_agent, check_neo4j=False)
            overflow_max = AGENT_CAPABILITIES[overflow_agent]["max_queue_depth"]

            if overflow_depth["total"] < overflow_max:
                return True, overflow_agent, f"overflow: {primary} ({depth['total']}/{max_allowed}) → {overflow_agent}"

            if fallback_agent:
                fallback_depth = get_agent_queue_depth(fallback_agent, check_neo4j=False)
                fallback_max = AGENT_CAPABILITIES[fallback_agent]["max_queue_depth"]
                if fallback_depth["total"] < fallback_max:
                    return True, fallback_agent, f"cascade: {overflow_agent} full → {fallback_agent}"

    return False, None, "no overflow route"


def _log_rebalance_decision(rebalance_decision, classification, result):
    """Log load-balanced routing decision."""
    try:
        primary = rebalance_decision["original"]
        overflow = rebalance_decision["overflow_to"]
        primary_depth = get_agent_queue_depth(primary, check_neo4j=False)
        overflow_depth = get_agent_queue_depth(overflow, check_neo4j=False)

        entry = {
            "ts": datetime.now().isoformat(),
            "task": classification.get("task", "")[:100],
            "primary_agent": primary,
            "overflow_to": overflow,
            "reason": rebalance_decision["reason"],
            "primary_queue_depth": primary_depth["total"],
            "overflow_queue_depth": overflow_depth["total"],
            "task_file": result.get("task_file", ""),
            "classification_method": classification.get("method", "unknown"),
        }

        os.makedirs(os.path.dirname(REBALANCE_LOG), exist_ok=True)
        with open(REBALANCE_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass
```

#### Section C: Modify route_task() function

Replace the current `route_task()` function with:

```python
def route_task(message, priority="normal"):
    """Classify, check load-balance, and route in one call"""
    classification = classify_task(message)
    destination = classification['destination']
    rebalance_decision = None

    # LOAD BALANCE CHECK (new)
    if destination != 'subagent':
        should_rebalance_flag, overflow_agent, reason = should_rebalance(destination, message)
        if should_rebalance_flag:
            rebalance_decision = {
                "original": destination,
                "overflow_to": overflow_agent,
                "reason": reason,
            }
            destination = overflow_agent
            classification['rebalanced'] = True

    # Route
    if destination == 'subagent':
        result = route_to_subagent(message, priority)
    else:
        result = route_to_agent(destination, message, priority)

    # Log rebalance decision (if happened)
    if rebalance_decision:
        _log_rebalance_decision(rebalance_decision, classification, result)

    return result
```

---

### Option 2: Separate Module

Alternatively, keep load balancing in a separate file:

```python
# In task-router.py, add after other imports:
from load_balancer_patch import get_agent_queue_depth, should_rebalance, _log_rebalance_decision

# Then modify route_task() the same way (Section C above)
```

---

## Testing the Integration

### Test 1: Queue Depth Check

```bash
python3 -c "
from task_router import get_agent_queue_depth
for agent in ['temujin', 'mongke', 'jochi']:
    depth = get_agent_queue_depth(agent)
    print(f'{agent}: {depth[\"total\"]} pending')
"
```

### Test 2: Rebalancing Logic

```bash
python3 -c "
from task_router import should_rebalance

tests = [
    ('temujin', 'Build REST API'),
    ('temujin', 'Build infrastructure'),
    ('mongke', 'Research competitors'),
]

for agent, task in tests:
    should, target, reason = should_rebalance(agent, task)
    print(f'{agent}: {should} → {target}')
"
```

### Test 3: Full Routing with Load Balancing

```bash
python3 task-router.py --task "Build API infrastructure" --priority normal

# Should route to ogedei instead of temujin if temujin is overloaded
# Check logs/routing-rebalanced.jsonl for the decision
```

---

## Monitoring Load Balance

### Check Rebalance Log

```bash
tail -f logs/routing-rebalanced.jsonl | jq .

# Example output:
# {
#   "ts": "2026-03-04T18:30:45.123456",
#   "task": "Build API infrastructure",
#   "primary_agent": "temujin",
#   "overflow_to": "ogedei",
#   "reason": "overflow: temujin (8/5) → ogedei",
#   "primary_queue_depth": 8,
#   "overflow_queue_depth": 2,
#   "classification_method": "llm"
# }
```

### Analyze Queue Distribution

```bash
python3 -c "
from task_router import get_agent_queue_depth, AGENT_CAPABILITIES

print('QUEUE STATUS')
print('=' * 50)
for agent in ['temujin', 'mongke', 'jochi', 'ogedei', 'chagatai', 'kublai']:
    depth = get_agent_queue_depth(agent)
    max_d = AGENT_CAPABILITIES[agent]['max_queue_depth']
    pct = 100 * depth['total'] / max_d
    status = '🔴 OVERLOADED' if pct >= 100 else '🟡 HIGH' if pct >= 80 else '🟢 OK'
    print(f'{agent:10} {depth[\"total\"]:2}/{max_d} ({pct:3.0f}%) {status}')
"
```

---

## Configuration & Tuning

### Adjust Max Queue Depths

Edit `AGENT_CAPABILITIES` dict. Start conservative (lower thresholds), then relax:

```python
AGENT_CAPABILITIES = {
    "temujin": {"max_queue_depth": 5},   # ← Lower = more aggressive rebalancing
    "mongke": {"max_queue_depth": 10},
    "jochi": {"max_queue_depth": 8},
    "ogedei": {"max_queue_depth": 6},
    "chagatai": {"max_queue_depth": 8},
    "kublai": {"max_queue_depth": 3},
}
```

### Disable Rebalancing Temporarily

Set all `max_queue_depth` to 999:

```python
for agent in AGENT_CAPABILITIES:
    AGENT_CAPABILITIES[agent]["max_queue_depth"] = 999
```

### Add New Overflow Routes

Edit `OVERFLOW_ROUTING`:

```python
OVERFLOW_ROUTING = {
    # (primary_agent, task_keyword) -> (overflow_agent, fallback_agent)
    ("temujin", "new_task_type"): ("agent_x", "agent_y"),
}
```

---

## Performance Notes

- **Queue depth check**: O(N) filesystem scan per classification. If slow, add caching:
  ```python
  from functools import lru_cache

  @lru_cache(maxsize=10)
  def get_agent_queue_depth_cached(agent):
      ...
  ```

- **Neo4j check**: Optional (check_neo4j=False by default). Only enable if needed.

- **Logging**: Async-safe (uses `open()` with append). No locks needed.

---

## Validation Checklist

- [ ] Added `AGENT_CAPABILITIES` dict
- [ ] Added `OVERFLOW_ROUTING` dict
- [ ] Added `get_agent_queue_depth()` function
- [ ] Added `should_rebalance()` function
- [ ] Added `_log_rebalance_decision()` function
- [ ] Modified `route_task()` to call `should_rebalance()`
- [ ] Verified `routing-rebalanced.jsonl` is created on first rebalance
- [ ] Tested with manual routing: `python3 task-router.py --task "..."`
- [ ] Queue distribution is balanced after 24h
- [ ] No duplicate tasks created
- [ ] Logs are clean (no errors in routing)

---

## Rollback

If issues arise, immediately rollback:

```bash
# Disable rebalancing
python3 -c "
import task_router as t
for agent in t.AGENT_CAPABILITIES:
    t.AGENT_CAPABILITIES[agent]['max_queue_depth'] = 999
"

# Or revert task-router.py to previous version
git checkout HEAD -- scripts/task-router.py
```
