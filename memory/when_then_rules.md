# WHEN/THEN Rule Registry

## Rule Lifecycle States
- `proposed` - New rule, not yet implemented
- `active` - Currently enforced in code/config
- `deprecated` - Obsolete but kept for reference
- `pruned` - Removed from active tracking (archived)

## Rule Categories
- `routing` - Task classification and agent assignment
- `ops` - System operations and health checks
- `quality` - Verification and standards enforcement
- `coordination` - Cross-agent communication patterns
- `escalation` - Alert and notification triggers

## Active Rules (13/10 capacity - OVER limit, prune low-impact rules)

| ID | WHEN condition | THEN action | Category | Created | Status |
|----|----------------|-------------|----------|---------|--------|
| R001 | errors/hour > 100 AND trend rising | auto-escalate to kublai (routes to ogedei) | escalation | 2026-03-09 | active |
| R002 | queue imbalance (idle agent, others >5 tasks for 3+ ticks) AND capacity for 2+ | accept overflow | routing | 2026-03-09 | active |
| R003 | human sends message to kublai | classify via AGENTS.md + create task via task_intake.py + reply "Routed to [agent]. Task created." | routing | 2026-03-09 | active |
| R004 | claiming a fix is complete | verify by checking file size/content or running test command | quality | 2026-03-09 | active |
| R005 | routing research | suggest /horde-learn in ACP prompt | routing | 2026-03-09 | active |
| R006 | routing pure research (competitor/market/pricing/trend/landscape) | route to mongke (research protection) | routing | 2026-03-09 | active |
| R007 | invoked for reflection AND tasks_completed == 0 AND completed task files exist not authored | produce missing deliverable inline before answering | quality | 2026-03-09 | active |
| R008 | task assigned with skill_hint present (e.g., /horde-implement, /horde-brainstorming, /horde-learn) | invoke Skill tool explicitly before any other work; complete all skill phases before marking done | quality | 2026-03-10 | active |
| R009 | marking task complete (any agent) | run `python3 scripts/pre_submit_check.py <task_file>` to verify quality thresholds BEFORE marking done; fix any failures first | quality | 2026-03-10 | active |
| R010 | tick (5min watchdog) executes | run subprocess_health_check.py to detect and clear orphaned agent subprocesses (.executing.md with dead/stopped PIDs) | ops | 2026-03-11 | active |
| R011 | tick detects GAP_DETECTED=1 AND gap_minutes > 10 | auto-escalate to kublai (routes to ogedei) via GAP_ESCALATION section in watchdog-gather.sh; bypasses LLM triage for deterministic monitoring gap response | ops | 2026-03-11 | active |
| R012 | security/vulnerability/audit/compliance/injection/unauthorized task routing | route to jochi (analyst) NOT away to temujin/ogedei; jochi RECEIVES security overflow from temujin | routing | 2026-03-11 | active |
| R013 | watchdog detects CRITICAL severity (HIGH_FAILURE_RATE >=75% across 10+ tasks, OR AUTH_HEARTBEAT failed_checks >=1, OR circuit-breaker stuck_open >=1) | self-initiate investigation task in kublai queue with priority=high, assigned to ogedei; title format: "CRITICAL: Investigate fleet-wide [ANOMALY_TYPE] - [timestamp]" | escalation | 2026-03-12 | active |

## Deprecated Rules

| ID | Rule | Deprecated | Reason |
|----|------|------------|--------|
| _ | _ | _ | _ |

## Proposed Rules (pending implementation)

| ID | WHEN condition | THEN action | Category | Proposed |
|----|----------------|-------------|----------|----------|
| _ | _ | _ | _ | _ |

## Change Log

| Date | Rule ID | Action | Notes |
|------|---------|--------|-------|
| 2026-03-09 | - | init | Created rule registry with 7 existing rules backfilled |
| 2026-03-10 | R008 | add | Enforce explicit skill invocation when skill_hint present (fixes EXECUTING_NO_OUTPUT throughput issue) |
| 2026-03-10 | R009 | add | Pre-submit verification: run pre_submit_check.py before marking done (fixes hollow success pattern) |
| 2026-03-11 | R010 | add | Subprocess health check: tick runs subprocess_health_check.py to clear orphaned .executing tasks (fixes PENDING_NO_DISPATCH throughput anomaly) |
| 2026-03-11 | R011 | add | Gap escalation: tick detects >10min monitoring gap and auto-escalates to kublai (fixes "14h blackout went undetected" issue) |
| 2026-03-11 | R012 | add | Security routing fix: jochi RECEIVES security overflow (was incorrectly sending security AWAY); fixed OVERFLOW_MAP and AGENT_CAPABILITY_MATRIX in task_intake.py |
| 2026-03-12 | R013 | add | CRITICAL fleet auto-investigation: Fixes "92% failure rate persisted 10+ ticks without investigation" incident. Auto-creates investigation task when watchdog detects HIGH_FAILURE_RATE >=75% or AUTH_HEARTBEAT failures |
| 2026-03-12 | R002/K004 | fix | Queue overflow acceptance (K004) was silently failing: kublai-actions.py imports `task_redistribute` but file was named `task-redistribute.py` (hyphen = unimportable). Created task_redistribute.py shim. |
