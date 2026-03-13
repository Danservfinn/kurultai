# kurultai-reflect: jochi — 2026-03-12 16:45

## My Red Flags (2h)
| Flag | Evidence | Action Taken |
|------|----------|--------------|
| HOLLOW_SUCCESS | 8/8 tasks scored substantive=1/3; 7/8 failed outright; 1 completed with success=false | Rule 1 written (memory check before retry) |
| DEBUGGING_LOOP | Tasks high-1773345764 failed 2x (182s + 278s); high-1773344100 killed at 42s; high-1773346104 killed at 12s | Addressed by Rule 1 (same root cause: resource contention) |
| STALE_SKILL_HINT | high-1773342502 had skill_hint=/systematic-debugging, failed R008_SKILL_NOT_FOUND; high-1773345764 emitted invalid ledger event R008_SKILL_NOT_FOUND | Rule 2 written (prepend skill invocation to retry prompt) |
| RULE_BREAKER | rules.json: R008 follow=25, violate=0; actual ledger: 2+ R008 failures; measurement divergence | Rule 3 written (verify compliance via ledger not self-report) |

## Rules Written to My Memory
| Rule (abbreviated) | Confidence | Evidence |
|-------------------|------------|---------|
| WHEN exit -9/-15 AND exec_time<120s THEN check memory + kill orphans before retry | HIGH | 7/8 FAILED, 2x SIGKILL, 1x SIGTERM |
| WHEN skill_hint task retried after R008 fail THEN prepend explicit skill invocation | HIGH | 2 tasks with R008_SKILL_NOT_FOUND |
| WHEN evaluating R008 compliance THEN verify via ledger SKILL_INVOCATION events | MEDIUM | rules.json/ledger count divergence |

## Skill Improvement Proposals I Created
| Skill | Problem | File |
|-------|---------|------|
| (none) | Skills not invoked at all — pre-execution failure, not skill quality issue | N/A |

## Architecture Drift Check
- Invariants reviewed: 4 (from §3, §8, §13)
- Violations detected: 1 — **Jochi's documented role is "pattern recognition, analytics, optimization"** but 6/8 tasks this window were escalation/diagnostic tasks (e.g., "Investigate ogedei task failures", "Investigate ogedei low performance"). These are ops-investigation tasks more suited to ogedei or temujin per architecture §3. Jochi is being used as a general troubleshooter rather than an analyst.
- My role as documented: Data Analyst — pattern recognition, analytics, optimization, performance monitoring, security testing
- My actual behavior this cycle: Received diagnostic/escalation tasks, failed to execute any of them successfully (0% completion rate)

## Architecture Drift Detail
The routing system is assigning ogedei-investigation tasks to jochi with skill_hint=/systematic-debugging. Architecture §3 defines jochi as an analyst, not an incident responder. These escalation tasks require reading ogedei's logs, checking infrastructure state, and running debugging workflows — this is closer to ogedei's own ops domain or temujin's debugging capability. The mismatch between task type and agent role contributes to the low domain_match_score (1/3) across all tasks.

## Capability Scores (7d rolling)
- Overall: 3.62/10 (44 tasks) — LOW
- Security domain: 7.2/10 (6 tasks) — strong when correctly routed
- Ops domain: 3.0/10 (1 task) — poor fit

## Key Insight from jochi-latest.md Review
The horde-review correctly identified: "Jochi improves the system's infrastructure [via proposals] but can't reliably execute its assigned diagnostic tasks." The R008 60-second preflight timeout is designed for simple tasks but applied to complex multi-file diagnostic work. The review recommended either (a) auto-prepending skill invocation or (b) raising R008 timeout to 180s for high-priority escalation tasks.

## My Status
**CRITICAL** — 0% task completion rate in 2h window. 7/8 tasks failed. Architectural drift detected (analyst receiving ops-investigation tasks). R008 compliance tracking is inaccurate (self-reported 100% vs actual ~0% on triggered tasks).

## Recommended Kublai Actions
1. **Routing fix:** Stop routing "Investigate {agent} failures" tasks to jochi. Per architecture §3, these are ops-investigation tasks — route to ogedei or temujin with /systematic-debugging.
2. **R008 timeout:** Extend R008 preflight timeout from 60s to 180s for `priority: high` tasks with skill_hint=/systematic-debugging. Complex diagnostic tasks need context-loading time before skill invocation.
3. **Rules evaluator fix:** Update evaluate_agent_rules.py to cross-reference R008 compliance against actual SKILL_INVOCATION events in the ledger, not agent self-reports.
