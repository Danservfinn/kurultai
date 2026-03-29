---
proposal_id: ogedei-20260323-003350-o008-drift-triggered-remediation-task
agent: ogedei
created: 2026-03-23T00:33:50.842874
status: approved
tier: T1
result: Auto-approved (self-scoped rule)
finalized: 2026-03-23T00:33:50.842874
---

# Proposal: O008: Drift-Triggered Remediation Task

## Source
Agent: ogedei
File: /Users/kublai/.openclaw/agents/main/reflections/reflection-ogedei-2026-03-22-2017.md

## Content
WHEN: ogedei-watchdog detects model_drift_drifted.length > 0 AND no open model-audit task in ogedei queue
THEN: Create high-priority ogedei task "Restore correct model config: {agents}" via task_intake.py within 10 minutes
Why: O
