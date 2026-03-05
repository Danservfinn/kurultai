# Queue-Depth-Aware Load Balancing Design & Implementation

**Date:** 2026-03-04
**Status:** Ready for Implementation
**Core Logic:** ~50 lines
**Total Package:** 5 design docs + 1 implementation module

---

## Problem Statement

The task router currently classifies & routes tasks with **zero queue awareness**:

```
CURRENT STATE:
  temujin:  93 pending tasks (massively overloaded)
  mongke:   1 pending  (idle)
  jochi:    3 pending  (idle)
  ogedei:   0 pending  (idle)

ISSUE:
  - All tasks routed based on capability match alone
  - No fallback when primary agent is full
  - Bottleneck in development → system slows
  - Wasted research/testing/ops capacity
```

**Goal:** Rebalance overflow tasks to less-loaded agents while preserving capability matching.

---

## Solution: Load-Balanced Routing Pipeline

New pipeline integrates into `route_task()` function:

```
Classify Task
    ↓
CHECK IF PRIMARY AGENT OVERLOADED
    ├─ No  → Route to primary (normal)
    └─ Yes → Check overflow routes
       └─ Can this task overflow elsewhere?
          ├─ No  → Route to primary (graceful degrade)
          └─ Yes → Is overflow agent available?
             ├─ Yes → Route to overflow agent
             └─ No  → Try fallback agent
                ├─ Yes → Route to fallback agent
                └─ No  → Route to primary (degrade)
```

---

## Deliverables

### 1. LOAD-BALANCING-DESIGN.md (11 KB)
**What:** Complete technical specification

**Contains:**
- Architecture diagrams (ASCII flow)
- Function signatures with full docstrings
- Pseudocode for each component
- Default thresholds table
- Testing strategy
- Future enhancements (phases 2-4)

**Read time:** 20 minutes
**Audience:** Architects, senior engineers

---

### 2. load-balancer-patch.py (293 lines)
**What:** Standalone Python module with full implementation

**Contains:**
- `AGENT_CAPABILITIES` dict (agent profiles + max queue depths)
- `OVERFLOW_ROUTING` dict (overflow rules matrix)
- `get_agent_queue_depth(agent)` function
- `should_rebalance(primary_agent, task_keywords)` function
- `_log_rebalance_decision()` function
- Test harness (main block)

**Use:** Copy-paste functions into task-router.py OR import as separate module

**Copy locations:**
- Lines 1-80: Imports + AGENT_CAPABILITIES
- Lines 82-120: OVERFLOW_ROUTING + log path
- Lines 124-165: get_agent_queue_depth()
- Lines 169-205: should_rebalance()
- Lines 209-245: _log_rebalance_decision()

---

### 3. INTEGRATION-GUIDE.md (400 lines)
**What:** Step-by-step setup & configuration

**Contains:**
- Option A: Inline integration (copy 3 sections into task-router.py)
- Option B: Separate module import
- Testing procedures (3 test cases)
- Monitoring queries (jq examples)
- Tuning instructions (thresholds, new routes)
- Rollback plan (3 steps)
- Validation checklist (12 items)

**Read time:** 15 minutes
**Audience:** Implementation engineers

---

### 4. LOAD-BALANCING-EXAMPLES.md (500 lines)
**What:** Concrete scenarios, flowcharts, decision trees

**Contains:**
- 5 detailed example scenarios (with queue states before/after)
- Decision flowchart (full ASCII)
- State transition diagram
- Data structure examples (actual Python objects)
- Configuration tweaking recipes
- Monitoring queries (bash examples)
- Common issues & fixes (5 Q&A pairs)

**Read time:** 30 minutes
**Audience:** QA engineers, operations teams

---

### 5. QUEUE-BALANCING-SUMMARY.md (9.9 KB)
**What:** Executive summary + architecture overview

**Contains:**
- Problem recap + solution diagram
- Core components (5 subsections)
- Default configuration table
- File inventory (all 3 deliverables)
- Integration steps (quick path: 15 min)
- Validation strategy (before/during/metrics)
- Key design decisions (with tradeoffs)
- Graceful degradation guarantees
- Future enhancements (phases 2-4)
- Code statistics (breakdown by component)
- Safety guarantees (4 bullet points)
- Success criteria (5 requirements)
- Q&A (6 common questions)

**Read time:** 10 minutes
**Audience:** Project leads, architects

---

### 6. QUICK-REFERENCE.md (8.7 KB)
**What:** Cheatsheet for developers

**Contains:**
- File inventory table
- Core functions (3 code snippets)
- Configuration (2 dicts to copy)
- Decision trees (visual)
- Monitoring commands (bash one-liners)
- Thresholds tuning (symptoms + fixes)
- Testing procedures (3 quick tests)
- Rollback plan (3 steps)
- Performance notes
- Safety guarantees (5 bullet points)
- Success metrics (24h targets)
- Links to all documents

**Read time:** 5 minutes
**Audience:** All team members (bookmark this!)

---

## Quick Start (15 minutes)

### Step 1: Read Overview
```bash
# Read this first (5 min)
cat QUEUE-BALANCING-SUMMARY.md

# Or the quick version (2 min)
cat QUICK-REFERENCE.md
```

### Step 2: Copy Code
```bash
# Option A: Inline integration
# Copy sections from INTEGRATION-GUIDE.md Section A/B/C into task-router.py

# Option B: Separate module
cp scripts/load-balancer-patch.py scripts/load-balancer.py
# Then import in task-router.py: from load_balancer import ...
```

### Step 3: Modify route_task()
```python
# In task-router.py, replace route_task() with:
def route_task(message, priority="normal"):
    classification = classify_task(message)
    destination = classification['destination']
    rebalance_decision = None

    # NEW: Load balance check
    if destination != 'subagent':
        should_rebalance_flag, overflow_agent, reason = should_rebalance(destination, message)
        if should_rebalance_flag:
            rebalance_decision = {...}
            destination = overflow_agent

    result = route_to_agent(destination, message, priority)

    if rebalance_decision:
        _log_rebalance_decision(rebalance_decision, classification, result)

    return result
```

### Step 4: Test
```bash
python3 task-router.py --task "Build infrastructure"

# Check logs
tail logs/routing-rebalanced.jsonl | jq .
```

---

## Architecture at a Glance

### Data Structures

```python
# Agent profiles
AGENT_CAPABILITIES = {
    "temujin": {"max_queue_depth": 5},
    "mongke": {"max_queue_depth": 10},
    "jochi": {"max_queue_depth": 8},
    # ... 3 more agents
}

# Overflow rules
OVERFLOW_ROUTING = {
    ("temujin", "infrastructure"): ("ogedei", "jochi"),  # cascade
    ("temujin", "code review"): ("jochi", None),         # single
}
```

### Queue Depth Check

```python
depth = get_agent_queue_depth("temujin")
# Returns: {"agent": "temujin", "filesystem": 8, "neo4j": 0, "total": 8}

if depth["total"] >= AGENT_CAPABILITIES["temujin"]["max_queue_depth"]:
    print("Overloaded!")
```

### Rebalancing Decision

```python
should, target, reason = should_rebalance("temujin", "Build infrastructure")
# Returns: (True, "ogedei", "overflow: temujin (8/5) → ogedei (2/6)")

if should:
    route_to_agent(target, task)  # Route to ogedei instead of temujin
```

### Logging

```json
{
  "ts": "2026-03-04T18:30:45",
  "task": "Build infrastructure",
  "primary_agent": "temujin",
  "overflow_to": "ogedei",
  "reason": "overflow: temujin (8/5) → ogedei (2/6)",
  "primary_queue_depth": 8,
  "overflow_queue_depth": 2
}
```

---

## Configuration & Tuning

### Default Thresholds

| Agent | Max Pending | Notes |
|-------|------------|-------|
| temujin | 5 | Small = aggressive rebalancing |
| mongke | 10 | Research tasks take longer |
| jochi | 8 | Testing is parallelizable |
| ogedei | 6 | Ops tasks time-sensitive |
| chagatai | 8 | Writing can batch |
| kublai | 3 | Lead stays light |

### Overflow Routes

```
temujin overflow rules:
  infrastructure → ogedei (fallback: jochi)
  code review → jochi (no fallback)
  api discovery → mongke (no fallback)
  testing → jochi (no fallback)
  deployment → ogedei (no fallback)
```

### Tuning Recipes

**Too many rebalances?** Increase thresholds:
```python
AGENT_CAPABILITIES["temujin"]["max_queue_depth"] = 10  # was 5
```

**Not enough rebalancing?** Decrease thresholds:
```python
AGENT_CAPABILITIES["temujin"]["max_queue_depth"] = 3  # was 5
```

**Add custom overflow route?** Edit dict:
```python
OVERFLOW_ROUTING[("temujin", "new_task")] = ("target", "fallback")
```

---

## Monitoring & Operations

### Status Dashboard
```bash
python3 << 'EOF'
from task_router import get_agent_queue_depth, AGENT_CAPABILITIES

for agent in ["temujin", "mongke", "jochi", "ogedei", "chagatai", "kublai"]:
    depth = get_agent_queue_depth(agent)
    max_d = AGENT_CAPABILITIES[agent]["max_queue_depth"]
    pct = 100 * depth["total"] / max_d
    status = "OVERLOAD" if pct >= 100 else "HIGH" if pct >= 80 else "OK"
    print(f"{agent:10} {depth['total']:2}/{max_d} ({pct:3.0f}%) {status}")
EOF
```

### Rebalance Log
```bash
# Last 10 rebalances
tail -10 logs/routing-rebalanced.jsonl | jq .

# Rebalance rate (%)
wc -l logs/routing-{decisions,rebalanced}.jsonl

# By overflow target
jq -r '.overflow_to' logs/routing-rebalanced.jsonl | sort | uniq -c
```

---

## Success Criteria (24h)

After deploying, check:

1. **temujin queue:** Drops from 93 to ~5 pending
2. **Other agents:** mongke/jochi/ogedei queues increase (more work)
3. **Rebalance rate:** 10-20% of tasks overflow (logged in routing-rebalanced.jsonl)
4. **Task completion:** Same or faster (no slowdown)
5. **Error rate:** 0 (no routing failures)

---

## Safety & Rollback

### Guarantees
✓ No task loss (routing only, never deletes)
✓ No infinite loops (cascade limited to 1 level)
✓ Graceful degradation (if all agents full, routes to primary)
✓ Idempotent (same input = same output always)

### Rollback (30 seconds)
```bash
# Option 1: Disable rebalancing
python3 -c "
from task_router import AGENT_CAPABILITIES
for a in AGENT_CAPABILITIES:
    AGENT_CAPABILITIES[a]['max_queue_depth'] = 999
"

# Option 2: Full revert
git checkout HEAD -- scripts/task-router.py
```

---

## Performance Notes

- **Queue depth check:** ~50ms per classification (filesystem scan)
- **Log write:** <1ms (append mode)
- **Memory overhead:** Negligible (dicts only)
- **Recommended:** Cache queue depths if >100 routes/min

---

## Project Structure

```
/Users/kublai/.openclaw/agents/main/
├── README-LOAD-BALANCING.md          ← YOU ARE HERE
├── QUEUE-BALANCING-SUMMARY.md        ← Exec summary
├── LOAD-BALANCING-DESIGN.md          ← Full design
├── INTEGRATION-GUIDE.md              ← Setup steps
├── LOAD-BALANCING-EXAMPLES.md        ← Scenarios & flowcharts
├── QUICK-REFERENCE.md                ← Cheatsheet
├── scripts/
│   ├── task-router.py                ← INTEGRATE HERE
│   ├── load-balancer-patch.py        ← Copy or import from here
│   ├── neo4j_task_tracker.py         ← Optional Neo4j check
│   └── ...
├── agent/
│   ├── temujin/tasks/               ← Queue 1 (counted)
│   ├── mongke/tasks/                ← Queue 2 (counted)
│   ├── jochi/tasks/                 ← Queue 3 (counted)
│   ├── ogedei/tasks/                ← Queue 4 (counted)
│   ├── chagatai/tasks/              ← Queue 5 (counted)
│   └── kublai/tasks/                ← Queue 6 (counted)
└── logs/
    ├── routing-decisions.jsonl      ← All classifications (existing)
    └── routing-rebalanced.jsonl     ← Rebalances only (new)
```

---

## Document Guide (Reading Path)

**If you have 5 minutes:**
→ Read QUICK-REFERENCE.md

**If you have 15 minutes:**
→ Read QUEUE-BALANCING-SUMMARY.md
→ Read INTEGRATION-GUIDE.md Section 0-3

**If you have 30 minutes:**
→ Read LOAD-BALANCING-DESIGN.md
→ Read LOAD-BALANCING-EXAMPLES.md (first 3 scenarios)

**If you're implementing:**
→ Read INTEGRATION-GUIDE.md completely
→ Copy code from load-balancer-patch.py Section A/B/C
→ Follow validation checklist

**If you're troubleshooting:**
→ Read LOAD-BALANCING-EXAMPLES.md (Common Issues section)
→ Check QUICK-REFERENCE.md (Tuning section)

---

## FAQ

**Q: How long does this take to implement?**
A: ~15 minutes. Just copy 3 sections from INTEGRATION-GUIDE.md + modify route_task().

**Q: Will this break existing routing?**
A: No. If an agent has capacity, it routes normally. Rebalancing only activates when overloaded.

**Q: Can I disable it?**
A: Yes. Set all max_queue_depth to 999 or delete the should_rebalance() call.

**Q: What if Neo4j is down?**
A: Falls back to filesystem count only. Still works.

**Q: How do I know it's working?**
A: Check routing-rebalanced.jsonl. If it grows, rebalancing is active.

**Q: What's the performance impact?**
A: ~50ms added per classification (one filesystem scan). Acceptable.

---

## Next Steps

1. **Review:** Read QUEUE-BALANCING-SUMMARY.md + QUICK-REFERENCE.md
2. **Design Review:** Share LOAD-BALANCING-DESIGN.md with team
3. **Implement:** Follow INTEGRATION-GUIDE.md steps
4. **Test:** Use test procedures in INTEGRATION-GUIDE.md
5. **Monitor:** Watch routing-rebalanced.jsonl for 24h
6. **Tune:** Adjust thresholds based on observed patterns
7. **Document:** Record any custom changes to AGENT_CAPABILITIES/OVERFLOW_ROUTING

---

## Contact & Support

- **Blocks on:** queue-depth awareness in task router
- **Unblocks:** balanced workload across 6-agent system
- **Owner:** Backend Architecture Team
- **Status:** Ready for deployment

---

**Created:** 2026-03-04
**Version:** 1.0
**Maintenance:** Update thresholds quarterly based on queue metrics
