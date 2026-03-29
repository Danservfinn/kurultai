---
proposal_id: ogedei-20260323-003350-o009-reflection-stale-escalation
agent: ogedei
type: RULE
created: 2026-03-23T00:33:50.843123
status: pending
tier: T2

voting_started: 2026-03-23T12:46:31.727914
voting_deadline: 2026-03-23T13:46:33.682834
status: voting
---

# Proposal: O009: Reflection Stale Escalation

## Source
Agent: ogedei
File: /Users/kublai/.openclaw/agents/main/reflections/reflection-ogedei-2026-03-22-2017.md

## Content
WHEN: ogedei-watchdog detects reflection stale > 1440 minutes (24h) in last_issues
THEN: Create high-priority ogedei task "Diagnose and restart reflection pipeline — stale {minutes}m" AND alert kublai via squad-chat
Why: R
