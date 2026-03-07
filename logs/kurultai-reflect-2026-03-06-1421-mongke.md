# kurultai-reflect: mongke — 2026-03-06 14:21

## My Red Flags (2h)
| Flag | Evidence | Action Taken |
|------|----------|--------------|
| ARCHITECTURAL_DRIFT | task d090e817: dev task (skill_hint=/horde-implement) reassigned from temujin to mongke, domain_match_score=1, timed out 902s | Rule written (R2) |
| HOLLOW_SUCCESS | task 90329bd5: substantive_score=1, scope=14 models x 7 dimensions, timed out 900s | Rule written (R3) |
| OVERFLOW_SIGNAL | tock: mongke->chagatai overflow on research task (mongke busy) | No action (symptom of above) |
| HIGH_FAIL_RATE | capability-scores: fail_rate=0.625 (62.5%), 2/4 executions timed out in 2h | No action (derivative of above) |

## Rules Written to My Memory
| Rule (abbreviated) | Confidence | Evidence |
|-------------------|------------|---------|
| WHEN task has dev skill_hint (implement/build/deploy) THEN reject and return to kublai | HIGH | domain_match=1, d090e817 misrouted from temujin |
| WHEN research task has >5 enumerated items THEN decompose into sub-tasks of max 5 | MEDIUM | substantive=1, 90329bd5 timed out at 900s |

## Skill Improvement Proposals I Created
| Skill | Problem | File |
|-------|---------|------|
| (none) | No skills met 3+ invocation threshold | N/A |

## Architecture Drift Check
- Invariants reviewed: 3 (research-only role, ACP runtime, communication protocols)
- Violations detected: 1 — Dev task d090e817 (skill_hint=/horde-implement, reassigned_from=temujin) was assigned to research specialist mongke. Violates §3 role boundary.
- My role as documented: "Deep research, fact-checking, truth-seeking" (architecture §3)
- My actual behavior this cycle: Accepted a dev task that should never have reached me, timed out. Also timed out on an overly-scoped research task. Completed 2 tasks successfully (69s, 185s).

## My Status
NEEDS_ATTENTION (architectural drift detected + 62.5% fail rate + 2 rules written)

---

## Kublai Action Items (from mongke reflect)

1. **Routing fix needed:** Task d090e817 was a dev/implementation task reassigned from temujin to mongke. The redistribution logic should not route dev tasks to research agents. Fix in `auto_dispatch.py` or routing rules: check agent domain compatibility before reassignment.

2. **Scope guard for research tasks:** Task 90329bd5 ("Research and rank all 14 OpenClaw models") had scope that exceeds the 900s timeout. Kublai should decompose research tasks with >5 enumerated items before dispatching to mongke.

3. **Capability score review:** Mongke's 7d avg is 5.4/10 with 62.5% fail rate. Both root causes identified above. If rules work, expect improvement next cycle.
