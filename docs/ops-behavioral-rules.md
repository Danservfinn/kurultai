# Ops Behavioral Rules Appendix

This document tracks ops-related behavioral rules across the Kurultai system. It provides cross-agent visibility for monitoring, health checks, and failover patterns.

## Purpose
- **Cross-agent visibility**: All agents can see what ops rules are active
- **Centralized reference**: Single source of truth for ops behaviors
- **Rule lifecycle**: Track when rules are added, deprecated, or modified

## Active Ops Rules

### Ogedei-Specific Rules (meta_reflection.py)

| ID | WHEN | THEN | Priority | Status |
|----|------|------|----------|--------|
| O001 | task-handler spawns ogedei session AND session model does not match resolved config model | log MODEL_MISMATCH anomaly AND request config audit from jochi | 1 | active |
| O002 | task fails with execution_time < 120s | read full error output, verify config resolution in settings.json, and check auth credentials before retrying | 2 | active |
| O003 | kurultai-monitor log shows >10min gap between "Check Started" entries AND system was supposedly active | investigate cron/launchd reliability (5min interval = 12 checks/hour) | 3 | active |
| O004 | tick detects orphaned task condition OR queue depth mismatch >5 between Neo4j and filesystem | execute `python3 scripts/reconcile_neo4j_tasks.py --fix` AND log reconciliation results | 4 | active |
| O005 | ogedei receives task involving feature development, documentation writing, or security research | route to appropriate agent (temujin/chagatai/mongke) instead | 5 | active |
| O006 | kurultai-monitor log shows >10min gap AND last tick was "degraded" status | immediately run auth_health_preflight.py AND create ogedei task if auth failures detected | 1 | active |

### System-Wide Ops Rules (when_then_rules.md)

| ID | WHEN | THEN | Scope | Status |
|----|------|------|-------|--------|
| R001 | errors/hour > 100 AND trend rising | auto-escalate to kublai (routes to ogedei) | system | active |
| R010 | tick (5min watchdog) executes | run subprocess_health_check.py to detect orphaned agent subprocesses | system | active |
| R011 | tick detects GAP_DETECTED=1 AND gap_minutes > 10 | auto-escalate to kublai (bypasses LLM triage) | system | active |

## Rule Implementation Locations

| Rule | Code Location | Config Location |
|------|---------------|-----------------|
| O001-O006 | `~/.openclaw/agents/ogedei/rules.json` (active behavioral rules) | `~/.openclaw/agents/ogedei/CLAUDE.md` (reflection context) |
| R001 | `scripts/task_intake.py` | `memory/when_then_rules.md` |
| R010 | `scripts/watchdog-gather.sh` | `memory/when_then_rules.md` |
| R011 | `scripts/watchdog-gather.sh` | `memory/when_then_rules.md` |

## Ops Scripts (Rule Enforcement)

| Script | Rule(s) | Frequency |
|--------|---------|-----------|
| `subprocess_health_check.py` | R010 | Every tick (5min) |
| `reconcile_neo4j_tasks.py` | O004 | On-demand + escalation |
| `watchdog-gather.sh` | R010, R011 | Every tick (5min) |
| `task-watcher.py` | Stale execution recovery | Every cycle (30s) |
| `scan_doc_gaps.py` | C002 (Documentation Self-Tasking) | On-demand + idle check |

## Chagatai Documentation Support

**Script:** `scan_doc_gaps.py` — Created 2026-03-11

Enables C002 (Documentation Self-Tasking) by automatically identifying:
- Stale docs (>7 days since last update)
- Missing expected documentation files
- Incomplete docs (<300 chars)

**Usage:**
```bash
python3 scripts/scan_doc_gaps.py
```

**Output:** JSON with prioritized gap list for task creation.

**Rule Connection:** When chagatai is idle >2h with no pending tasks, C002 triggers this scanner to identify documentation gaps and create proactive tasks.

## Implemented Rules

### Gap Detection Enhancement (2026-03-11)

**Problem**: 14-hour auth blackout went undetected because kurultai-monitor gaps weren't escalated.

**Rule O006**:
- **WHEN**: kurultai-monitor log shows >10min gap AND last tick was "degraded" status
- **THEN**: Immediately run auth_health_preflight.py AND create ogedei task if auth failures detected
- **Priority**: 1 (critical)
- **Status**: active (implemented in rules.json)

## Rule Change Log

| Date | Rule | Action | Notes |
|------|------|--------|-------|
| 2026-03-11 | O006 | implement | Auth health gap response rule moved from proposed to active |
| 2026-03-11 | O001-O006 | operationalize | Created ~/.openclaw/agents/ogedei/rules.json to active behavioral rules |
| 2026-03-11 | O001-O005 | document | Added ogedei-specific behavioral rules to appendix |
| 2026-03-11 | R010 | document | Subprocess health check rule from when_then_rules.md |
| 2026-03-11 | R011 | document | Gap escalation rule from when_then_rules.md |
| 2026-03-11 | - | create | Created ops-behavioral-rules.md for cross-agent visibility |
| 2026-03-11 | escalation | routing | Moved ogedei to first position in escalation domain (task_intake.py line 98) — escalation tasks now route to ops instead of falling through to jochi |

## Usage

Agents can reference this document to understand:
- What ops behaviors are active across the system
- Where specific rules are implemented in code
- How to escalate ops issues appropriately
- What new ops rules have been proposed

To add a new rule:
1. Add to appropriate section (ogedei-specific or system-wide)
2. Implement in code (script or config)
3. Update rule implementation locations table
4. Add entry to change log
