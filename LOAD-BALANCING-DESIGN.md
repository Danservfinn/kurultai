# Queue-Depth-Aware Load Balancing Design

**Version:** 1.0
**Date:** 2026-03-04
**Purpose:** Prevent agent queue buildup (esp. temujin) by redistributing overflow to capable agents.

---

## Problem Statement

Current system has **zero queue awareness**:
- temujin routinely accumulates 93+ pending tasks while mongke/jochi sit at 1-3
- Router classifies + routes without checking if target agent is overloaded
- No fallback when primary agent hits capacity
- Result: bottlenecks for dev work, idle research/testing capacity

---

## Solution: Load-Balanced Routing Pipeline

### 1. Queue Depth Checker

**Function:** `get_agent_queue_depth(agent, check_neo4j=True)`

Counts pending tasks from filesystem + optionally Neo4j:
- **Filesystem check**: Count `.md` files without `.executing`, `.completed`, `.done` suffixes
- **Neo4j check** (optional): Query `Task` nodes with `status='PENDING'` for that agent
- **Return value**: `{"agent": str, "filesystem": int, "neo4j": int, "total": int}`

```python
def get_agent_queue_depth(agent, check_neo4j=True):
    """
    Count pending tasks for an agent (filesystem + optionally Neo4j).

    Args:
        agent: Agent name (temujin, mongke, etc.)
        check_neo4j: If True, include Neo4j PENDING count

    Returns:
        {"agent": agent, "filesystem": int, "neo4j": int, "total": int}
    """
    base = "/Users/kublai/.openclaw/agents/main/agent"
    task_dir = f"{base}/{agent}/tasks"
    fs_count = 0

    if os.path.isdir(task_dir):
        # Count only true pending files (no .executing, .completed, .done)
        for fname in os.listdir(task_dir):
            if not any(suffix in fname for suffix in [".executing", ".completed", ".done"]):
                fs_count += 1

    neo4j_count = 0
    if check_neo4j:
        try:
            from neo4j_task_tracker import get_tracker
            tracker = get_tracker()
            # Count pending tasks in Neo4j for this agent
            with tracker.driver.session() as session:
                result = session.run(
                    "MATCH (t:Task {agent: $agent, status: 'PENDING'}) RETURN count(t) AS cnt",
                    agent=agent
                )
                record = result.single()
                neo4j_count = record["cnt"] if record else 0
        except Exception:
            neo4j_count = 0  # Graceful degradation if Neo4j unavailable

    return {
        "agent": agent,
        "filesystem": fs_count,
        "neo4j": neo4j_count,
        "total": max(fs_count, neo4j_count)  # Use max to avoid double-counting
    }
```

---

### 2. Capability Overlap Matrix

**What:** Map of which agents can handle what overflow tasks.

```python
# Capability profiles (primary vs. secondary)
AGENT_CAPABILITIES = {
    "temujin": {
        "primary": ["code", "build", "fix", "deploy", "apis"],
        "secondary": ["infrastructure", "automation"],
        "can_accept_from": [],  # No overflow TO temujin
        "max_queue_depth": 5,  # Trigger rebalancing at 5+ pending
    },

    "mongke": {
        "primary": ["research", "analysis", "discovery"],
        "secondary": [],
        "can_accept_from": ["temujin"],  # Can help with discovery tasks
        "max_queue_depth": 10,
    },

    "chagatai": {
        "primary": ["writing", "documentation", "content"],
        "secondary": [],
        "can_accept_from": [],
        "max_queue_depth": 8,
    },

    "jochi": {
        "primary": ["testing", "security", "validation", "review"],
        "secondary": ["code review"],  # Can review code that temujin wrote
        "can_accept_from": ["temujin"],
        "max_queue_depth": 8,
    },

    "ogedei": {
        "primary": ["ops", "monitoring", "infrastructure"],
        "secondary": ["automation"],
        "can_accept_from": ["temujin"],  # Can handle infrastructure/deployment
        "max_queue_depth": 6,
    },

    "kublai": {
        "primary": ["coordination", "triage", "system-wide"],
        "secondary": [],
        "can_accept_from": [],  # Lead — doesn't take overflow
        "max_queue_depth": 3,
    },
}

# Overflow routing rules: (primary_agent, task_keywords) -> (overflow_agent, fallback_agent)
OVERFLOW_ROUTING = {
    ("temujin", "infrastructure"): ("ogedei", "jochi"),  # Build infrastructure → ogedei, fallback jochi
    ("temujin", "code review"): ("jochi", None),         # Code review → jochi, no fallback
    ("temujin", "api discovery"): ("mongke", None),      # API discovery → mongke
}
```

---

### 3. Rebalancing Logic

**Where it goes:** After `classify_task()` but before `route_to_agent()`, in the `route_task()` function.

```python
def should_rebalance(primary_agent, task_keywords):
    """
    Check if primary agent is overloaded + task can be handled elsewhere.

    Args:
        primary_agent: Result from LLM classification
        task_keywords: Task text (to match against OVERFLOW_ROUTING)

    Returns:
        (should_rebalance: bool, target_agent: str or None, reason: str)
    """
    # Check if primary agent is overloaded
    depth = get_agent_queue_depth(primary_agent, check_neo4j=True)
    max_allowed = AGENT_CAPABILITIES[primary_agent]["max_queue_depth"]

    if depth["total"] < max_allowed:
        return False, None, "primary agent has capacity"

    # Primary is overloaded — check if this task can overflow
    task_lower = task_keywords.lower()

    for (primary, keywords_pattern), (overflow_agent, fallback_agent) in OVERFLOW_ROUTING.items():
        if primary == primary_agent and keywords_pattern in task_lower:
            # Found overflow rule
            overflow_depth = get_agent_queue_depth(overflow_agent, check_neo4j=True)
            overflow_max = AGENT_CAPABILITIES[overflow_agent]["max_queue_depth"]

            if overflow_depth["total"] < overflow_max:
                return True, overflow_agent, f"overflow: {primary} full → {overflow_agent}"

            # Overflow agent also full, try fallback
            if fallback_agent:
                fallback_depth = get_agent_queue_depth(fallback_agent, check_neo4j=True)
                fallback_max = AGENT_CAPABILITIES[fallback_agent]["max_queue_depth"]
                if fallback_depth["total"] < fallback_max:
                    return True, fallback_agent, f"overflow cascade: {overflow_agent} full → {fallback_agent}"

    return False, None, "no overflow route available"
```

---

### 4. Integration Point: Modified `route_task()`

```python
def route_task(message, priority="normal"):
    """
    Classify, check load-balance, and route in one call.

    Pipeline:
    1. Classify task
    2. Check if primary agent is overloaded
    3. If overloaded + overflow route exists, use overflow agent
    4. Log load-balance decision separately
    5. Route to final agent
    """
    classification = classify_task(message)
    destination = classification['destination']
    rebalance_decision = None

    # LOAD BALANCE CHECK (new)
    if destination != 'subagent':
        should_rebalance, overflow_agent, reason = should_rebalance(destination, message)
        if should_rebalance:
            rebalance_decision = {
                "original": destination,
                "overflow_to": overflow_agent,
                "reason": reason,
            }
            destination = overflow_agent  # Update routing target
            classification['rebalanced'] = True  # Mark in classification

    # Route
    if destination == 'subagent':
        result = route_to_subagent(message, priority)
    else:
        result = route_to_agent(destination, message, priority)

    # Log load-balance decision (if happened)
    if rebalance_decision:
        _log_rebalance_decision(rebalance_decision, classification, result)

    return result
```

---

### 5. Logging: Load-Balance Decisions

**Where:** Separate JSONL file (or add flag to routing-decisions.jsonl)

```python
REBALANCE_LOG = "/Users/kublai/.openclaw/agents/main/logs/routing-rebalanced.jsonl"

def _log_rebalance_decision(rebalance_decision, classification, result):
    """
    Log load-balanced routing decision.

    Entry format:
    {
        "ts": "2026-03-04T18:30:00.123456",
        "task": "Build API endpoint",
        "primary_agent": "temujin",
        "overflow_to": "jochi",
        "reason": "overflow: temujin full (8/5) → jochi",
        "primary_queue_depth": 8,
        "overflow_queue_depth": 2,
        "task_file": "path/to/task.md",
        "classification_method": "llm"
    }
    """
    try:
        primary = rebalance_decision["original"]
        overflow = rebalance_decision["overflow_to"]

        primary_depth = get_agent_queue_depth(primary, check_neo4j=False)
        overflow_depth = get_agent_queue_depth(overflow, check_neo4j=False)

        entry = {
            "ts": datetime.now().isoformat(),
            "task": classification["task"],
            "primary_agent": primary,
            "overflow_to": overflow,
            "reason": rebalance_decision["reason"],
            "primary_queue_depth": primary_depth["total"],
            "overflow_queue_depth": overflow_depth["total"],
            "task_file": result.get("task_file", ""),
            "classification_method": classification["method"],
        }

        os.makedirs(os.path.dirname(REBALANCE_LOG), exist_ok=True)
        with open(REBALANCE_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Never let logging break routing
```

---

## Thresholds & Configuration

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| temujin max depth | 5 | Small queue to enforce rebalancing early |
| mongke max depth | 10 | Research tasks take longer |
| jochi max depth | 8 | Testing parallelizable |
| ogedei max depth | 6 | Ops tasks time-sensitive |
| chagatai max depth | 8 | Writing can queue up |
| kublai max depth | 3 | Lead keeps light (high-priority only) |

---

## Code Size Estimate

- **Queue depth checker**: ~35 lines
- **Rebalancing logic**: ~25 lines
- **Integration in route_task**: ~10 lines
- **Logging function**: ~20 lines
- **Capability matrix** (config): ~30 lines
- **Total**: ~120 lines (but most is config/comments)
- **Pure logic**: ~50 lines

---

## Testing Strategy

1. **Unit test**: Verify `get_agent_queue_depth()` counts correctly
2. **Mock test**: Simulate overloaded agents, verify `should_rebalance()` picks overflow correctly
3. **Integration test**: Route 100 tasks, check distribution is balanced
4. **Log audit**: Verify routing-rebalanced.jsonl captures decisions correctly

---

## Deployment

1. Add `AGENT_CAPABILITIES` and `OVERFLOW_ROUTING` dicts to task-router.py
2. Add `get_agent_queue_depth()` and `should_rebalance()` functions
3. Modify `route_task()` to call `should_rebalance()` before routing
4. Add `_log_rebalance_decision()` for audit trail
5. Start logging to routing-rebalanced.jsonl
6. Monitor for 24h, adjust thresholds based on actual queue patterns

---

## Future Enhancements

1. **Dynamic thresholds**: Learn optimal depths from success rates (via Neo4j)
2. **Cost-aware routing**: Weight by agent utilization + task complexity
3. **Skill-based overflow**: Use Neo4j to find agents with highest success rate for task type
4. **Cascade routing**: If overflow agent also full, try tertiary agent
5. **ML-based prediction**: Predict queue depth 1h ahead, pre-rebalance

---

## Notes

- **Graceful degradation**: If Neo4j down, fall back to filesystem count only
- **No blocking**: Load-balance check is O(N) filesystem scan — add caching if needed
- **Audit trail**: Every rebalance decision logged separately for analysis
- **Easy to disable**: Set all max_queue_depth to 999 to disable rebalancing
