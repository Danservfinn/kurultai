# kurultai-reflect: ogedei — 2026-03-07 05:30

## My Red Flags (2h)
| Flag | Evidence | Action Taken |
|------|----------|--------------|
| MODEL_MISMATCH | 3/7 FAILED events show "kimi-k2.5" model (tasks e1501e02, 343654a2, 7bfa30c7) | Rule 6 written — reject non-opus model execution |
| DOMAIN_MISMATCH | task 7bfa30c7 "Parse MVP" with skill=/horde-implement assigned to ogedei (ops agent) | Rule 7 written — reject dev tasks, escalate to kublai |
| ZOMBIE_ACCUMULATION | 3 duplicate executing file recoveries (ages 263s, 4509s, 7122s) | Rule 8 written — kill tasks in .executing >1800s |
| STALL_TIMEOUT | signal-calendar-retry stalled 916.6s, fallback to sonnet also failed | No rule (1 data point, LOW confidence) |

## Rules Written to My Memory
| Rule (abbreviated) | Confidence | Evidence |
|-------------------|------------|---------|
| WHEN non-opus model fails THEN verify config, reject execution | HIGH | 3 kimi-k2.5 failures |
| WHEN task has skill_hint=/horde-implement THEN reject, escalate to kublai | HIGH | 1 dev task in ops queue (architectural drift) |
| WHEN .executing >1800s THEN kill + revert for clean retry | MEDIUM | 3 zombie recoveries |

## Skill Improvement Proposals I Created
| Skill | Problem | File |
|-------|---------|------|
| (none) | No SKILL_OUTCOME telemetry instrumented for ogedei | N/A |

## Architecture Drift Check
- Invariants reviewed: 4 (ops-only domain, self-healing infra, incident response ownership, auto-restart)
- Violations detected: 2 — MODEL_MISMATCH (kimi-k2.5 instead of opus), DOMAIN_MISMATCH (dev task routed to ops agent)
- My role as documented: Infrastructure, deployment, monitoring, incident response, security hardening, backup/recovery
- My actual behavior this cycle: Attempted dev work (Parse MVP) outside domain; executed with wrong model; accumulated zombie tasks

## Performance Summary (2h)
- **Completed:** 5 tasks (avg 244.8s)
- **Failed:** 7 events (58.3% failure rate)
- **Distinct failure causes:** model mismatch (3), zombie recovery (3), stall timeout (1)
- **Overall quality rating:** 6.0/10 (7d rolling)
- **Ops-specific rating:** 8.0/10 (ops tasks only)

## My Status
**NEEDS_ATTENTION** — 2 architectural drift violations detected (model config + domain routing). Rules written to prevent recurrence. Root causes are upstream (auto_dispatch.py routing + model config propagation) and require kublai/temujin fixes.
