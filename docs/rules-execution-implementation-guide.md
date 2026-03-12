# Rules Execution Implementation Guide

## Problem Statement

**Gap identified:** 2026-03-11 during chagatai reflection

Rules are defined in two places but neither has an execution mechanism:

| Location | Type | Rules | Executed? |
|----------|------|-------|-----------|
| `main/memory/when_then_rules.md` | System-wide (R001-R012) | 12 active | ❌ No — documentation only |
| `chagatai/rules.json` | Agent-specific (C001-C005) | 5 active | ❌ No — metadata only |

**Impact**: C002 "Documentation Self-Tasking" rule exists but doesn't fire, causing chagatai to sit idle with zero throughput when documentation gaps exist.

## Architecture: Two-Layer Rule System

### Layer 1: System-Wide WHEN/THEN Rules (memory/when_then_rules.md)

- **Scope**: Cross-agent behaviors, routing policies, escalation triggers
- **Examples**: R001 (error escalation), R003 (kublai routing), R009 (pre-submit gate)
- **Status**: Manually enforced via code (e.g., R009 in `pre_submit_check.py`)
- **Execution**: Hard-coded in scripts, not dynamic evaluation

### Layer 2: Agent-Specific Behavioral Rules ({agent}/rules.json)

- **Scope**: Single-agent behaviors, quality standards, productivity patterns
- **Examples**: C001 (pre-submit check), C002 (self-tasking), C005 (content structure)
- **Status**: Currently metadata only — no eval loop
- **Execution**: **NOT IMPLEMENTED** — this is the gap

## Implementation Options

### Option A: Script-Based Rule Evaluator (Recommended)

Create `scripts/evaluate_agent_rules.py`:

```python
#!/usr/bin/env python3
"""
Evaluates agent-specific rules from {agent}/rules.json
Invoked by: hourly_reflection.sh, task_intake.py, or agent idle-watchdog
"""
import json
from pathlib import Path
from datetime import datetime, timedelta

def load_rules(agent_dir: str) -> dict:
    rules_path = Path(agent_dir) / "rules.json"
    if not rules_path.exists():
        return {"rules": []}
    return json.loads(rules_path.read_text())

def evaluate_c002_self_tasking(agent: str) -> bool:
    """C002: WHEN idle >2h AND no pending tasks AND docs gaps exist"""
    # Check idle time
    # Check pending tasks
    # Check docs for stale content
    # If all true -> create self-tasked writing task
    pass

def evaluate_rule(rule: dict, agent: str) -> bool:
    """Dispatch to specific evaluator based on rule ID"""
    if rule["id"] == "C002":
        return evaluate_c002_self_tasking(agent)
    # Add other rule evaluators...
    return False

def main(agent: str = "chagatai"):
    agent_dir = f"/Users/kublai/.openclaw/agents/{agent}"
    rules_data = load_rules(agent_dir)

    for rule in rules_data.get("rules", []):
        if rule.get("enabled", False):
            evaluate_rule(rule, agent)

if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else "chagatai")
```

**Integration points:**
- Add to `hourly_reflection.sh` → "C002 evaluation phase"
- Add to `task_intake.py` → after task dispatch, check if agent needs self-tasking
- Add to agent wrapper `.claude/settings.json` → `post-response` hook (if supported)

### Option B: Inline Rule Enforcement (Current Pattern)

Each rule is hard-coded in relevant scripts:

- R009 → `scripts/pre_submit_check.py` (implemented)
- C001 → Same as R009 (redundant)
- C002 → Needs new script or integration

**Pros:** Simple, deterministic, already working for some rules
**Cons:** Duplication, rules must be implemented twice (doc + code), hard to maintain

### Option C: LLM-Based Rule Evaluation (Experimental)

Invoke the agent with a special "evaluate your rules" prompt:

```bash
echo "Evaluate your behavioral rules from rules.json. Take action on any triggered rules." | \
  /Users/kublai/.local/bin/claude-agent --agent chagatai
```

**Pros:** Flexible, can handle complex WHEN conditions
**Cons:** Non-deterministic, LLM might not recognize rule state, token overhead

## Recommendation

**Implement Option A** for these rules first:

| Priority | Rule | Implementation Effort | Impact |
|----------|------|----------------------|--------|
| 1 | C002 (self-tasking) | M script + hourly cron | Fixes chagatai starvation |
| 2 | C003 (domain boundary) | S check in task_intake.py | Prevents misrouting |
| 3 | C001/C004/C005 | Already covered by R009 | No action needed |

## Migration Path

1. **Phase 1**: Create `evaluate_agent_rules.py` with C002 evaluator
2. **Phase 2**: Add cron job or integrate into `hourly_reflection.sh`
3. **Phase 3**: Verify C002 fires when conditions met (check for self-tasked tasks)
4. **Phase 4**: Add evaluators for other agents' rules as they're defined

## Cross-Agent Visibility

Current state: Only chagatai has rules.json. Other agents need:

1. Create rules.json for each agent with their behavioral patterns
2. Add entries to `when_then_rules.md` for tracking
3. Implement evaluation loop for each agent

## Related Files

- `main/memory/when_then_rules.md` — System-wide rule registry
- `main/memory/rules_lifecycle.md` — Rule lifecycle (proposed→active→deprecated→pruned)
- `chagatai/rules.json` — Agent-specific rules template
- `main/docs/behavioral-rules-execution.md` — Execution patterns doc
- `scripts/pre_submit_check.py` — Example of rule enforcement (R009)

## Resolution

**Status**: Documentation created ✅
**Next step**: temujin to implement `evaluate_agent_rules.py` with C002 evaluator
**Estimated effort**: M (2-3 hours for MVP)
