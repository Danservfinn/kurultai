# kurultai-reflect: kublai -- 2026-03-12 16:33

## My Red Flags (2h)
| Flag | Evidence | Action Taken |
|------|----------|--------------|
| FLEET_FAILURE_RATE | 82% failure rate (42/51 tasks), all 6 agents affected. ogedei: 17 fails, mongke: 10, jochi: 7, temujin: 6, chagatai: 1, kublai: 1. Only 9 completions. | Rule written (reinforce K009 auto-investigation) |
| RECURRING_ROUTING_ISSUE | "High explicit routing 89%" unresolved 11 consecutive audits. "jochi backlog 10 pending" unresolved 9 consecutive audits. | Rule written (address recurring issues within 1h) |
| WORKLOAD_SKEW | ogedei received 14/27 tasks (52%), temujin only 2/27 (7%). Redistribution cycles=0 despite imbalance. | Rule written (trigger redistribution at >40% skew) |
| REFLECTION_CRON_ERROR | "Kurultai Reflection (4-hour cycle)" cron: 2 consecutive errors, last_duration=62ms (instant fail). Reflection pipeline broken. | No rule written -- ops fix needed, should route to ogedei |

## Rules Written to My Memory
| Rule (abbreviated) | Confidence | Evidence |
|-------------------|------------|---------|
| WHEN fleet failure >=75% THEN create investigation task via task_intake.py immediately | HIGH | 82% failure rate, 42 fails, K009 not followed |
| WHEN recurring_issues consecutive >= 5 THEN create fix task within 1 hour | HIGH | 11 and 9 consecutive unresolved issues |
| WHEN single agent >40% of routed tasks THEN trigger redistribution | MEDIUM | ogedei 52%, temujin 7%, 0 redistribution cycles |

## Skill Improvement Proposals I Created
| Skill | Problem | File |
|-------|---------|------|
| (none) | Kublai does not directly invoke skills -- routes to agents | N/A |

## Architecture Drift Check
- Invariants reviewed: 4 (never self-execute, always route via task_intake, reply "Routed to", one slot per agent)
- Violations detected: 1 -- K009 (auto-investigation for CRITICAL fleet failure) exists as a rule but was not enacted. Architecture requires kublai to create investigation tasks when fleet failure rate exceeds threshold. This is architectural drift: the rule was documented but the automation to enforce it does not exist in watchdog-gather.sh.
- My role as documented: Router + coordinator. Classify, route, reply. Never do specialist work.
- My actual behavior this cycle: Routed 27 tasks (85% with skill hints). Handled 1 task directly (R008 validator fix, scored 3/10, failed with SIGKILL). Did not create investigation task for 82% fleet failure rate despite K009 rule.

## My Status
**NEEDS_ATTENTION** (2 rules broken: K002, K009. 3 new rules written. Architectural drift on K009 enforcement.)

---

## System Health -- Fleet View (2h)

### Per-Agent Status
| Agent | Status | Red Flags | Rules Written | Proposals |
|-------|--------|-----------|---------------|-----------|
| temujin | NEEDS_ATTENTION | 6 failures / 4 completions, 2/2 executed failed | 0 | 0 |
| mongke | CRITICAL | 10 failures / 2 completions, 3 routed 0 executed (dispatch stall) | 0 | 0 |
| chagatai | NEEDS_ATTENTION | 1 failure / 0 completions, 0 tasks executed | 0 | 0 |
| jochi | CRITICAL | 7 failures / 1 completion, 10 tasks pending (backlog), 1/1 executed failed | 0 | 0 |
| ogedei | CRITICAL | 17 failures / 2 completions, 14 routed 1 executed 1 failed | 0 | 0 |
| kublai | NEEDS_ATTENTION | 1 failure / 0 completions, K009 not followed | 3 | 0 |

### Fleet-Wide Failure Analysis (2h)
| Agent | Failed | Completed | Failure Rate |
|-------|--------|-----------|-------------|
| ogedei | 17 | 2 | 89% |
| mongke | 10 | 2 | 83% |
| jochi | 7 | 1 | 88% |
| temujin | 6 | 4 | 60% |
| chagatai | 1 | 0 | 100% |
| kublai | 1 | 0 | 100% |
| **FLEET TOTAL** | **42** | **9** | **82%** |

### Fleet-Wide Skill Performance (2h)
No SKILL_INVOCATION or SKILL_OUTCOME events from any agent this cycle. Skill telemetry is not yet instrumented fleet-wide.

### Kublai Self-Assessment: Routing Quality
- Tasks routed this cycle: 27
- Skill hints assigned: 23 (85% of tasks)
- Skill hint accuracy (hint matched actual skill invoked): INSUFFICIENT DATA (no SKILL_OUTCOME events)
- Self-route violations: 0 (per architecture S4)
- Delegation score avg: 1.0/2 (from 1 scored kublai task)
- Routing accuracy (from audit): 87%
- Routing method: 89% explicit, 7% keyword_override (keyword table underused)

### Architecture Invariant Status (fleet-wide)
- Documented invariants checked: 4
- Fleet-wide violations:
  1. **K009 enforcement gap**: Kublai has rule requiring auto-investigation at 82% fleet failure rate, but no automation exists to enforce it. Manual rule only.
  2. **Reflection pipeline broken**: Kurultai Reflection cron has 2 consecutive errors (instant fail at 62ms). This is a documented critical path in architecture S6.
  3. **Config model mismatch**: 4/6 agents show config_model valid=false in tock. chagatai, temujin, jochi running on glm-5 sessions while config says claude-opus-4-6.
  4. **Ledger-Neo4j reconciliation gap**: neo4j shows 0 completions, ledger shows 5. Delta=-5. reconciled=false.

### Recommended Actions for Kublai

1. **FIX REFLECTION CRON (URGENT)**: Route to ogedei -- "Kurultai Reflection (4-hour cycle)" cron has 2 consecutive errors with 62ms duration (instant crash). Investigate and fix. This blocks the entire self-improvement pipeline.

2. **ENFORCE K009 IN AUTOMATION**: The rule exists in kublai-behavioral-rules.md but no code path in watchdog-gather.sh or tick processing creates the investigation task. Add a check in watchdog-gather.sh: `if fleet_failure_rate >= 0.75 then task_intake.py --agent ogedei --priority high`. Without this, the rule is documentation-only.

3. **ADDRESS JOCHI BACKLOG**: 10 tasks pending for 9+ consecutive audit cycles. Either redistribute pending tasks to idle agents or investigate why jochi is not draining its queue.

4. **INVESTIGATE CONFIG MODEL MISMATCH**: 4 agents show glm-5 in active sessions but config says claude-opus-4-6. This model mismatch correlates with the 82% failure rate. Verify that agents are actually running on the intended model.
