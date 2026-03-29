---
proposal_id: kublai-20260323-041200-improve-reflection-telemetry-accuracy
agent: kublai
type: SYSTEM
created: 2026-03-23T04:12:00
status: pending
tier: T1
impact: high
effort: medium

voting_started: 2026-03-23T12:46:31.858347
voting_deadline: 2026-03-23T13:46:33.806709
status: voting
---

# Proposal: Improve Reflection Telemetry Accuracy

## Domain
Routing / System Coordination

## Problem Statement
Current reflection telemetry shows HOLLOW_SUCCESS and TELEMETRY_GAP red flags across multiple agents (jochi, chagatai, ogedei). The task-ledger.jsonl shows SKILL_INVOCATION events but corresponding SKILL_OUTCOME events with success metrics are not being captured accurately. This leads to false positives in red flag detection and reduces trust in the reflection system.

## Proposed Solution
1. Audit task-watcher.py to ensure it logs SKILL_OUTCOME events with success boolean
2. Update agent-task-handler.py to capture tool call counts and durations
3. Add validation in score_tasks.py to cross-reference task files with telemetry
4. Create a telemetry health check that runs hourly to detect gaps

## Expected Impact
- Reduce false positive HOLLOW_SUCCESS flags by 80%
- Improve accuracy of agent effectiveness scoring
- Enable data-driven skill improvements

## Implementation Steps
1. Review task-watcher.py event logging
2. Update agent-task-handler.py to emit SKILL_OUTCOME
3. Add tool call counting to execution wrapper
4. Create telemetry validation script
5. Test with 24h window

## Resource Requirements
- 2-3 hours development time
- Testing across all 5 agents

## Risk Assessment
Low risk - changes are additive, existing functionality preserved

## Success Metrics
- Zero TELEMETRY_GAP red flags in next 4 cycles
- 100% of completed tasks have SKILL_OUTCOME events
