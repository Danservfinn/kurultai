# kurultai-reflect: mongke — 2026-03-07 06:45

## My Red Flags (2h)
| Flag | Evidence | Action Taken |
|------|----------|--------------|
| RULE_BREAKER | 0/5 triggered rules followed (06:03 reflection confirms). All active rules violated — zero output during extended idle/gateway degradation. | Rule written: load ACTIVE RULES at session start within 30s |
| STALE_SKILL_HINT | kanban-pause-button-001 assigned with skill_hint=/horde-implement (dev skill) to research agent. 3rd occurrence in 24h. | Rule exists (Rule 1). Root cause: Rule 1 not loaded — covered by new RULE_BREAKER fix |
| HOLLOW_SUCCESS | 2 COMPLETED events, 0 SCORED, 0 SKILL_OUTCOME, no artifact files. Completions produced no measurable output. | Rule written: require artifact file before marking done |

## Rules Written to My Memory
| Rule (abbreviated) | Confidence | Evidence |
|-------------------|------------|---------|
| WHEN session starts THEN load ACTIVE RULES within 30s | HIGH | 0/5 rules followed, 81.1% fail rate 7d |
| WHEN task completes exit 0 AND no artifact THEN write findings summary | MEDIUM | 2 completions, 0 scored, 0 artifacts |

## Skill Improvement Proposals I Created
| Skill | Problem | File |
|-------|---------|------|
| (none) | Insufficient SKILL_OUTCOME telemetry (0 events) | — |

## Architecture Drift Check
- Invariants reviewed: 3 (research-only role, ACP execution, knowledge graph storage)
- Violations detected: 1 — dev task (kanban-pause-button-001, skill=/horde-implement) assigned to research-only agent. Architecture §3 explicitly defines mongke as Research Specialist.
- My role as documented: Deep research, fact-checking, truth-seeking via web_search/web_fetch
- My actual behavior this cycle: 1 failed dev task (domain mismatch), 2 hollow completions (no artifacts), 0 research output

## My Status
**NEEDS_ATTENTION** — Rules written to address rule-loading gap and hollow success pattern. Architectural drift detected (dev tasks still routed to research agent despite 3 prior occurrences). Root cause is upstream (auto_dispatch.py domain guard missing) + local (rules not loaded at session start).

### Key Metrics (2h window)
- Failed: 1 (kanban-pause-button-001 — domain mismatch)
- Completed: 2 (hollow — no artifacts)
- 7d fail rate: 81.1% (14 tasks)
- 7d quality: 4.87/10 overall, 7.0/10 in-domain research, 8.0/10 security
- Rule adherence: 0/5 (0%)
- Session context: 8% (severely underutilized)

### Upstream Fix Required
auto_dispatch.py MUST add domain-compatibility guard before reassigning tasks. Current behavior: when temujin queue > threshold, system assigns ANY available agent regardless of domain. This is the root cause of mongke's 81.1% fail rate — most failures are misrouted dev tasks.
