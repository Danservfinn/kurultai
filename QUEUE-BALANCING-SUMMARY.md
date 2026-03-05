# Queue-Depth-Aware Load Balancing: Design Summary

**Status:** Ready for Implementation
**Total LOC (logic only):** ~50 lines
**Total LOC (with config):** ~120 lines
**Files Created:** 3
**Complexity:** Low (straightforward FSM + queue checks)

---

## Problem

- **temujin** accumulates massive backlogs (93+ pending tasks)
- **mongke, jochi, ogedei** sit idle (1-3 tasks each)
- Current router has **zero queue awareness**
- No fallback when primary agent is overloaded

## Solution Architecture

```
Classify Task
    ↓
CHECK QUEUE DEPTH
    ↓
Should Rebalance?
    ├─ YES: Find overflow agent
    │  └─ Overflow agent has capacity?
    │     ├─ YES → Route to overflow agent
    │     └─ NO → Try fallback agent
    └─ NO: Route to primary agent
       ↓
Log Routing Decision
       ↓
Route to Agent
```

---

## Core Components

### 1. Queue Depth Checker
**Function:** `get_agent_queue_depth(agent, check_neo4j=True)`

Counts:
- Filesystem: `.md` files without `.executing`, `.completed`, `.done`
- Neo4j (optional): `Task` nodes with `status='PENDING'`

**Return:** `{"agent": str, "filesystem": int, "neo4j": int, "total": int}`

### 2. Capability Overlap Matrix
**Config:** `AGENT_CAPABILITIES` dict + `OVERFLOW_ROUTING` dict

Maps:
- Primary responsibilities per agent
- Secondary capabilities (for overflow)
- Max queue depth before triggering rebalance
- Fallback agents if primary overflow also full

### 3. Rebalancing Logic
**Function:** `should_rebalance(primary_agent, task_keywords)`

Decision tree:
1. Is primary agent overloaded? If no, return False
2. Can this task type overflow? Check `OVERFLOW_ROUTING`
3. Does overflow agent have capacity? If yes, return True + target
4. Does fallback agent have capacity? If yes, return True + fallback
5. Otherwise, return False

**Return:** `(should_rebalance: bool, target_agent: str, reason: str)`

### 4. Integration Point
**Location:** `route_task()` function in task-router.py

**Insertion point:** After `classify_task()`, before `route_to_agent()`

**Code change:** 10 lines

```python
def route_task(message, priority="normal"):
    classification = classify_task(message)
    destination = classification['destination']
    rebalance_decision = None

    # NEW: Load balance check
    if destination != 'subagent':
        should_rebalance_flag, overflow_agent, reason = should_rebalance(destination, message)
        if should_rebalance_flag:
            rebalance_decision = {"original": destination, "overflow_to": overflow_agent, "reason": reason}
            destination = overflow_agent

    # Existing routing logic...
    result = route_to_agent(destination, message, priority)

    # Log rebalance decision if happened
    if rebalance_decision:
        _log_rebalance_decision(rebalance_decision, classification, result)

    return result
```

### 5. Logging
**File:** `/logs/routing-rebalanced.jsonl` (separate from routing-decisions.jsonl)

**Entry:**
```json
{
  "ts": "2026-03-04T18:30:45.123456",
  "task": "Build API infrastructure",
  "primary_agent": "temujin",
  "overflow_to": "ogedei",
  "reason": "overflow: temujin (8/5) → ogedei (2/6)",
  "primary_queue_depth": 8,
  "overflow_queue_depth": 2,
  "classification_method": "llm"
}
```

---

## Default Configuration

### Agent Thresholds

| Agent | Max Queue | Rationale |
|-------|-----------|-----------|
| temujin | 5 | Small to force early rebalancing |
| mongke | 10 | Research tasks take longer |
| jochi | 8 | Testing is parallelizable |
| ogedei | 6 | Ops tasks time-sensitive |
| chagatai | 8 | Writing can queue up |
| kublai | 3 | Lead keeps light |

### Overflow Routes

| If temujin overloaded with... | Goes to... | Then fallback to... |
|------|-----------|-----------|
| infrastructure | ogedei | jochi |
| code review | jochi | (none) |
| api discovery | mongke | (none) |
| testing | jochi | (none) |
| deployment | ogedei | (none) |

---

## File Inventory

### 1. `/LOAD-BALANCING-DESIGN.md` (this repo)
Complete technical design with:
- Architecture diagrams
- Function signatures
- Pseudocode
- Thresholds table
- Testing strategy
- Future enhancements

### 2. `/scripts/load-balancer-patch.py` (standalone module)
Importable Python module containing:
- All functions + logic
- Can be dropped into task-router.py or imported separately
- Includes test harness

### 3. `/INTEGRATION-GUIDE.md` (setup instructions)
Step-by-step guide:
- Option A: Inline integration (copy-paste sections into task-router.py)
- Option B: Separate module import
- Testing procedures
- Monitoring queries
- Configuration tuning
- Rollback instructions

---

## Integration Steps (Quick Path)

1. Open `/scripts/task-router.py`
2. After imports, add `AGENT_CAPABILITIES` + `OVERFLOW_ROUTING` dicts (from LOAD-BALANCING-DESIGN.md Section 1)
3. After `_log_routing_decision()`, add three functions:
   - `get_agent_queue_depth()`
   - `should_rebalance()`
   - `_log_rebalance_decision()`
4. Replace `route_task()` function with load-balance aware version
5. Test: `python3 task-router.py --task "Build API infrastructure"`
6. Check `/logs/routing-rebalanced.jsonl` for decisions

**Total time:** ~15 minutes

---

## Validation Strategy

### Before Deployment
- Unit test `get_agent_queue_depth()` with mock filesystem
- Mock test `should_rebalance()` with overloaded agents
- Integration test with 100 mock tasks

### During Rollout (24h window)
- Monitor queue distribution (should be more balanced)
- Check routing-rebalanced.jsonl for patterns
- Verify no duplicate task routing
- Watch for Neo4j state consistency

### Metrics to Track
- Rebalance rate (% of tasks that overflow)
- Queue depth per agent (trend toward equilibrium)
- Task completion time by agent (should improve for temujin)
- Log file size (should be <1KB/hour per 100 tasks)

---

## Key Design Decisions

### 1. Filesystem-first counting (not Neo4j)
**Why:** Faster, no DB dependency, PENDING state is canonical on disk

**Tradeoff:** May miss tasks that exist in Neo4j but not filesystem (rare edge case)

### 2. Max not Sum for total
**Why:** Avoids double-counting if task exists in both systems

**Tradeoff:** If systems are out of sync, will undercount

### 3. Separate log file (routing-rebalanced.jsonl)
**Why:** Easier to audit, separate concerns, easier to query

**Tradeoff:** Two log files instead of one

### 4. No blocking I/O or locks
**Why:** Simple, fast, no deadlock risk

**Tradeoff:** In rare concurrent scenarios, might see stale queue counts (acceptable)

### 5. Keyword pattern matching (not sophisticated NLP)
**Why:** Lightweight, doesn't require LLM

**Tradeoff:** Will miss some valid overflow opportunities (but simpler to debug/tune)

---

## Graceful Degradation

If Neo4j is down:
- Queue depth check falls back to filesystem only
- Rebalancing still works (just less accurate)
- System continues to route tasks

If filesystem is corrupted:
- Neo4j check (if enabled) provides backup count
- Worst case: all queue depths become 0, rebalancing activates conservatively

---

## Future Enhancements

### Phase 2: Learning
- Track success rates per agent + task type (via Neo4j)
- Adjust thresholds dynamically based on actual performance
- Learn overflow preferences from history

### Phase 3: Predictive
- Predict queue depth 1h ahead (via time-series model)
- Pre-rebalance before overflow happens
- Smooth load distribution

### Phase 4: Skill-based
- Query Neo4j for agent success rates on task type
- Route to best agent, not just least-loaded
- Combine load + expertise

---

## Code Statistics

```
Load Balancer Components:
  AGENT_CAPABILITIES dict    : ~30 lines (config)
  OVERFLOW_ROUTING dict      : ~10 lines (config)
  get_agent_queue_depth()    : ~20 lines
  should_rebalance()         : ~22 lines
  _log_rebalance_decision()  : ~20 lines
  route_task() modification  : ~10 lines
  ─────────────────────────────────────
  TOTAL                      : ~112 lines

Core Logic (no comments):
  get_agent_queue_depth()    : ~10 lines
  should_rebalance()         : ~15 lines
  route_task() hook          : ~8 lines
  ─────────────────────────────────────
  TOTAL                      : ~33 lines
```

---

## Safety Guarantees

- **No infinite loops:** Cascade only goes 1 level deep (overflow → fallback)
- **No task loss:** Tasks are only routed, never deleted
- **No routing deadlock:** If all agents overloaded, routes to primary (degrades gracefully)
- **Idempotent:** Rebalancing decision is deterministic + logged

---

## Success Criteria

System is working if:
1. temujin queue stays <5 pending (vs. 93 before)
2. mongke/jochi/ogedei queues increase (more tasks)
3. Overall completion time stays same or improves
4. routing-rebalanced.jsonl shows 10-20% of tasks are rebalanced
5. No errors in logs related to rebalancing

---

## Questions & Answers

**Q: What if overflow agent also gets overloaded?**
A: Falls back to tertiary agent (if defined). Otherwise routes to primary (degrades gracefully).

**Q: Does this increase latency?**
A: ~50ms added per classification (one filesystem scan + dict lookups). Negligible.

**Q: Can I disable rebalancing?**
A: Yes. Set all `max_queue_depth` to 999 or comment out the `should_rebalance()` call.

**Q: What about tasks already in neo4j_task_tracker?**
A: They're not double-counted (we use `max(filesystem, neo4j)` for total). Existing Neo4j state is preserved.

**Q: Can agents reject tasks?**
A: No. Each agent's task-watcher just executes them. Rebalancing prevents overload preemptively.

---

## References

- **Design Doc:** `/LOAD-BALANCING-DESIGN.md`
- **Implementation:** `/scripts/load-balancer-patch.py`
- **Integration Steps:** `/INTEGRATION-GUIDE.md`
- **Task Router Source:** `/scripts/task-router.py`
- **Neo4j Tracker:** `/scripts/neo4j_task_tracker.py`
- **Agent Queues:** `/agent/{agent}/tasks/`
- **Routing Decisions Log:** `/logs/routing-decisions.jsonl`
- **Rebalance Log (new):** `/logs/routing-rebalanced.jsonl`
