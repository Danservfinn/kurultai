# Profiles

The live system uses a chair/caretaker profile plus specialist profiles. This public repo includes role contracts, not private identity/memory text.

Canonical Kurultai roster:

- `kublai` — chair/caretaker, synthesis, approvals, receipts, operator interface.
- `batu` — retrieval, research intake, return-path compilation, high-signal source capture.
- `chagatai` — research, writing, synthesis, content.
- `jochi` — analysis, audit, scouting, alternatives, red-team style second opinions.
- `temujin` — implementation, tests, code repair.
- `coder` — optional implementation worker lane for hosts that preserve a dedicated coding profile.
- `mongke` — review, risk, quality gates, release gates.
- `ogedei` — operations, integration, runbooks, gateway/cron/dashboard surfaces.
- `subc` — Subconscious/Dreamer signal layer for pattern noticing, retrospectives, and proposal candidates.
- `tolui` — local lightweight triage, summarization, classification, receipt prefiltering.
- `codex` — non-routable compatibility/pseudo-profile for explicit Codex CLI workflows only.

Generic role classes:

- `chair` — synthesis, approvals, receipts, operator interface.
- `researcher` — web/literature/reconnaissance.
- `builder` — implementation and tests.
- `reviewer` — PR review, security scans, release gates.
- `ops` — cron, dashboards, health checks, recovery.
- `memory` — Brain/wiki ingestion and synthesis.
- `signal` — background pattern detection and proposal candidates.
- `local-triage` — cheap local classification/summarization only until tool calls are verified.

Copy a template from `templates/SOUL.profile.md` into each profile home and customize locally.
