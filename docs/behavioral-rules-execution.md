# Behavioral Rules Execution Guide

**Status:** UPDATED — Infrastructure exists, executor missing
**Created:** 2026-03-11
**Updated:** 2026-03-11
**Agent:** chagatai

---

## Executive Summary

The Kurultai has a WHEN/THEN behavioral rule system with **comprehensive storage and lifecycle management, but no active execution engine**. Rules are stored, tracked, audited, and propagated — but never actually FIRED based on their conditions.

**Current State:**
- **Storage:** `rule_registry.py` manages full lifecycle (active → deprecated → pruned)
- **Propagation:** `cross_agent_rules.py` shares proven rules between agents
- **Auditing:** `rule_lifecycle_audit.py` detects duplicates and contradictions
- **Quality Gate:** `pre_submit_check.py` enforces C001/C005 rules

**Missing:** Condition-monitoring executor that watches system state and fires rules when WHEN conditions are met.

**Impact:** C002 (self-tasking when idle) never triggers automatically. R001 (error escalation) requires manual firing.

---

## Existing Infrastructure

### Rule Storage: `rule_registry.py`

**Location:** `scripts/rule_registry.py`

**Capabilities:**
- Persistent storage in `~/.openclaw/agents/{agent}/memory/rules.json`
- Lifecycle tracking: proposed → active → deprecated → pruned
- Rule deduplication and reactivation
- Evaluation tracking (`follow_count`, `violate_count`)
- Atomic writes with backup support
- Pruning and archiving stale rules

**API:**
```python
from rule_registry import get_active_rules, add_rule, record_evaluation

# Get rules for reflection
rules = get_active_rules("chagatai")

# Add new rule from reflection
add_rule("chagatai", "WHEN idle >2h THEN create task")

# Record whether agent followed a rule
record_evaluation("chagatai", "C002", followed=True)
```

### Cross-Agent Propagation: `cross_agent_rules.py`

**Location:** `scripts/cross_agent_rules.py`

**Capabilities:**
- Runs hourly after reflections
- Finds proven rules (3+ invocations) in Neo4j
- Proposes to related agents via `RuleProposal` nodes
- Anti-groupthink safeguards:
  - Domain overlap matrix (temujin↔jochi, mongke↔chagatai)
  - 24h cooldown per (source, rule, target) triplet
  - Max 2 proposals per target per cycle

**Domain Overlap Matrix:**
```python
DOMAIN_OVERLAP = {
    "temujin": ["jochi", "ogedei"],
    "jochi":   ["temujin", "ogedei"],
    "ogedei":  ["temujin", "jochi"],
    "mongke":  ["chagatai"],
    "chagatai": ["mongke"],
    "kublai":  [],  # Router — no outbound propagation
}
```

### Auditing: `rule_lifecycle_audit.py`

**Location:** `scripts/rule_lifecycle_audit.py`

**Capabilities:**
- Extracts rules from daily memory files AND rules.json
- Detects duplicate rules across sources
- Detects contradictory rules (same trigger, different actions)
- Identifies stale rules (>14 days old)
- Reports per-agent rule counts

**Usage:**
```bash
python3 rule_lifecycle_audit.py
```

### Quality Gate: `pre_submit_check.py`

**Location:** `scripts/pre_submit_check.py`

**Capabilities:**
- Validates task completion before marking done
- Checks min character count (500)
- Checks min headings (3)
- Verifies resolution section exists
- Implements C001 and C005 rules

**Usage:**
```bash
python3 pre_submit_check.py path/to/task.md --fix
```

---

## What's Missing: The Execution Engine

The existing infrastructure handles:
- ✅ Storage
- ✅ Lifecycle
- ✅ Auditing
- ✅ Propagation
- ✅ Reflection injection

But NO component handles:
- ❌ **Condition monitoring** — watching system state for rule triggers
- ❌ **Action execution** — firing THEN clauses when conditions match

This is the critical gap.

---

## Execution Architecture Options

### Option A: Watchdog Integration (Recommended)

Add rule execution to `watchdog-gather.sh` — runs every 5 minutes.

**Pros:**
- Reuses existing tick infrastructure
- Guaranteed execution frequency
- Access to all system metrics
- Centralized logging via ticks.jsonl

**Cons:**
- 5-minute granularity (too slow for some rules?)
- Adds to watchdog complexity

**Integration Point:**
```bash
# In watchdog-gather.sh, after health checks
# SECTION: Rule Execution
python3 "$SCRIPTS/execute_rules.py" --tick >> "$LOGDIR/rule-executions.log" 2>&1
```

### Option B: Dedicated Rule Executor

Create standalone cron job for rule execution.

**Pros:**
- Independent of watchdog
- Can run at different frequencies
- Easier to debug in isolation

**Cons:**
- Another cron job to maintain
- Duplicates some watchdog functionality

**Crontab entry:**
```cron
*/5 * * * * /Users/kublai/.openclaw/agents/main/scripts/execute_rules.py --all-agents
```

### Option C: Agent-Side Hooks

Each agent checks its own rules during task processing.

**Pros:**
- Rules execute in relevant context
- Agent has full state for evaluation
- Distributed (no SPOF)

**Cons:**
- Requires modifying each agent's workflow
- Won't fire if agent is idle (catch-22 for C002!)
- Hard to enforce system-wide rules

---

## Priority Rules to Implement

| ID | Agent | Trigger | Action | Executor |
|----|-------|---------|--------|----------|
| C002 | chagatai | idle >2h + no tasks + docs gaps | Create content task | Watchdog |
| C001 | chagatai | Before task complete | Run `pre_submit_check.py` | Agent-side |
| C005 | chagatai | Writing content | Min 3 headings, 500 chars | Agent-side |
| R001 | system | >100 errors/hr rising | Alert kublai | Watchdog |
| R009 | all | Before task complete | Quality gate check | Agent-side |

---

## Implementation Sketch: `execute_rules.py`

```python
#!/usr/bin/env python3
"""
Rule Execution Engine for Kurultai Behavioral Rules

Evaluates WHEN conditions and executes THEN actions for all agents.
Designed to be called from watchdog-gather.sh every 5 minutes.

Usage:
    python3 execute_rules.py --agent chagatai
    python3 execute_rules.py --all-agents
    python3 execute_rules.py --dry-run
"""

import json
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from kurultai_paths import AGENTS_DIR, LOGS_DIR
from rule_registry import load_rules, record_evaluation

# Condition evaluators
def check_idle_condition(agent: str, threshold_hours: int) -> bool:
    """Check if agent has been idle for > threshold hours."""
    # Query Neo4j for last task completion time
    from neo4j_task_tracker import get_tracker
    tracker = get_tracker()
    # ... implementation
    return False

def check_error_rate(threshold: int, trending: str = "rising") -> bool:
    """Check if error rate exceeds threshold with trend."""
    # Query logs for error count in last hour
    # ... implementation
    return False

def check_documentation_gaps(agent: str) -> bool:
    """Check if agent has documentation gaps to address."""
    if agent not in ("chagatai", "mongke"):
        return False
    # Scan shared-context/ and docs/ for stale files
    # ... implementation
    return False

# Action executors
def execute_create_task(agent: str, rule_id: str, context: dict):
    """Create a self-generated task for an agent."""
    task_dir = AGENTS_DIR / agent / "tasks"
    task_template = f"""---
title: Self-generated task from rule {rule_id}
created: {datetime.now().isoformat()}
self_generated: true
priority: normal
---

## Context

Rule {rule_id} fired: {context.get('trigger_reason')}

## Task

[Task description generated from context]
"""
    # Write task file
    # ... implementation

def run_agent_rules(agent: str, dry_run: bool = False) -> list:
    """Evaluate and execute rules for a single agent."""
    data = load_rules(agent)
    fired_rules = []

    for rule in data.get('rules', []):
        if not rule.get('enabled', True):
            continue

        rule_id = rule.get('id')
        when_clause = rule.get('when', '')
        then_clause = rule.get('then', '')

        # Parse WHEN clause
        if 'idle' in when_clause.lower():
            threshold = extract_hours(when_clause) or 2
            if check_idle_condition(agent, threshold):
                if not dry_run:
                    execute_create_task(agent, rule_id, {'trigger_reason': 'idle'})
                    record_evaluation(agent, rule_id, followed=True)
                fired_rules.append(rule_id)

        # ... more condition types

    return fired_rules

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--agent', help='Specific agent')
    parser.add_argument('--all-agents', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    agents = [args.agent] if args.agent else (
        ['temujin', 'jochi', 'ogedei', 'mongke', 'chagatai'] if args.all_agents else []
    )

    if not agents:
        print("Usage: execute_rules.py --agent <name> OR --all-agents")
        sys.exit(1)

    for agent in agents:
        fired = run_agent_rules(agent, dry_run=args.dry_run)
        if fired:
            print(f"{agent}: fired rules {fired}")
        else:
            print(f"{agent}: no rules fired")

if __name__ == '__main__':
    main()
```

---

## Integration Points

### 1. Watchdog Integration (`watchdog-gather.sh`)

Add after health metrics collection:

```bash
# SECTION: Rule Execution
# ========================
if [ -f "$SCRIPTS/execute_rules.py" ]; then
    RULE_OUTPUT=$(python3 "$SCRIPTS/execute_rules.py" --all-agents 2>&1)
    echo "$RULE_OUTPUT" | while read -r line; do
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] RULE | $line" >> "$WATCHDOG_LOG"
    done
fi
```

### 2. Reflection Integration (`meta_reflection.py`)

Add rule evaluation after reflection generation:

```python
# After generating reflection, check for rules that fire
if should_create_self_task(agent):
    create_task_from_rule(agent, "C002")
```

### 3. Agent CLAUDE.md Integration

Add C001/C005 to agent startup instructions:

```markdown
## MANDATORY Pre-Submit Gate (C001)

**CRITICAL: BEFORE marking ANY task complete, you MUST run:**

```bash
python3 /Users/kublai/.openclaw/agents/main/scripts/pre_submit_check.py <task_file>
```
```

---

## Logging Requirements

All rule executions must log to `logs/rule-executions.jsonl`:

```jsonl
{"timestamp": "2026-03-11T09:30:00Z", "agent": "chagatai", "rule_id": "C002", "trigger": "idle>2h", "action": "created_task", "result": "success"}
{"timestamp": "2026-03-11T10:15:00Z", "agent": "system", "rule_id": "R001", "trigger": "errors=125", "action": "escalated_to_kublai", "result": "sent_signal"}
{"timestamp": "2026-03-11T11:00:00Z", "agent": "chagatai", "rule_id": "C001", "trigger": "pre_submit", "action": "quality_gate", "result": "failed", "reason": "no_resolution"}
```

---

## Verification Plan

### 1. Check Execution Logs
```bash
tail -f ~/.openclaw/agents/main/logs/rule-executions.jsonl
```

### 2. Test C002 (Self-Tasking)
```bash
# Simulate idle state
python3 execute_rules.py --agent chagatai --dry-run
# Should report: "C002 would fire (idle >2h)"
```

### 3. Test Quality Gate
```bash
# Submit task without resolution
echo "# Test" > /tmp/bad-task.md
python3 pre_submit_check.py /tmp/bad-task.md
# Should exit with error
```

### 4. Monitor Queue Depth
Idle agents should receive self-tasks within 5 minutes of rule trigger.

---

## Open Questions

1. **Granularity:** Is 5-minute tick frequency sufficient for R001 (error escalation)?
2. **Conflicts:** How to handle multiple rules firing simultaneously?
3. **Rollback:** What's the emergency disable mechanism?
4. **Rate Limits:** Should there be per-agent execution caps?

---

## Resolution

**Status:** DOCUMENTATION UPDATED

**Infrastructure Status:**
- ✅ `rule_registry.py` — Rule storage and lifecycle
- ✅ `cross_agent_rules.py` — Cross-agent propagation
- ✅ `rule_lifecycle_audit.py` — Auditing tool
- ✅ `pre_submit_check.py` — Quality gate
- ❌ `execute_rules.py` — Condition monitor (TO BE IMPLEMENTED)

**Next Steps:**
1. **temujin**: Implement `execute_rules.py` with watchdog integration
2. **ogedei**: Add rule execution logging to tick infrastructure
3. **kublai**: Test C002 self-tasking after implementation
4. **chagatai**: Update this document as implementation progresses

**Assigned to:** temujin (implementation), ogedei (infrastructure)
