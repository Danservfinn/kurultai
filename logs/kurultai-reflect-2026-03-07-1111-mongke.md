# kurultai-reflect: mongke — 2026-03-07 11:11

## My Red Flags (2h)
| Flag | Evidence | Action Taken |
|------|----------|--------------|
| STALE_SKILL_HINT | task 10fd2bac-f8c had skill_hint=/horde-implement (dev skill) assigned to researcher agent, stalled 930s | Rule written (#1) |
| MODEL_MISMATCH | Infrastructure pulse shows model=glm-5, architecture mandates claude-opus-4-6; selfwake failed instantly 2x (14.9s) | Rule written (#2) |
| DEBUGGING_LOOP | selfwake-mongke-1772894676 failed twice in 22s, immediate identical retry | Rule written (#3) |

## Rules Written to My Memory
| Rule (abbreviated) | Confidence | Evidence |
|-------------------|------------|---------|
| WHEN dev-domain skill_hint THEN reject + signal Kublai for re-route | HIGH | task 10fd2bac-f8c, 930s stall, primary+fallback failure |
| WHEN config.json model != claude-opus-4-6/sonnet THEN refuse + log MODEL_VIOLATION | HIGH | model=glm-5 in session, 2x instant selfwake failure |
| WHEN selfwake fails <30s THEN check model config before retry | MEDIUM | selfwake-1772894676, 2 failures in 22s |

## Skill Improvement Proposals I Created
| Skill | Problem | File |
|-------|---------|------|
| (none) | Insufficient invocation data (0 SKILL_OUTCOME events) | N/A |

## Architecture Drift Check
- Invariants reviewed: 2 (model=claude-opus-4-6, research-domain specialization)
- Violations detected: 2 — model=glm-5 (violates §3 model mandate), dev skill assigned to researcher (violates role specialization)
- My role as documented: Deep research, fact-checking, truth-seeking, web research, source verification
- My actual behavior this cycle: 75% failure rate (3/4 tasks failed). 1 task was a dev-domain task misrouted to me. 2 selfwake failures from model misconfiguration. 1 selfwake completed (211.7s).

## My Status
**CRITICAL** — Architectural drift detected: model misconfiguration (glm-5 instead of claude-opus-4-6) causing systemic task failures. Additionally receiving misrouted dev-domain tasks.

### Root Causes Requiring Kublai/Ogedei Intervention
1. **mongke config.json** must be audited and corrected to claude-opus-4-6 (or model key removed so wrapper defaults apply)
2. **task_intake.py routing** assigned a /horde-implement task to mongke — skill_hint domain should constrain agent selection
3. **selfwake retry logic** should not immediately retry tasks that fail in <30s without checking infrastructure health
