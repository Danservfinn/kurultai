# Kurultai Status — 2026-03-12 22:48

## Activity (last 2h)
- (all agents: idle — no ledger events recorded in last 2h)

## Pending Queue (7 total)
| Agent    | Pending | Next task |
|----------|---------|-----------|
| kublai   | 4       | Escalation: Stale Task Recovery (×2, critical) |
| temujin  | 1       | Self-Wake — Execute Blocked Items |
| ogedei   | 2       | Fallback Chain Validation Failed; Fix /horde-learn 63s Timeout |
| mongke   | 0       | — |
| chagatai | 0       | — |
| jochi    | 0       | — |

## Kublai's Next Steps
**Initiative:** Review and process pending task queue backlog
**Assigned to:** kublai
**Rationale:** Tasks are queued but not being processed
**Expected outcome:** Queue backlog reduced to zero
⚠️ **LLM unavailable** — heuristic fallback active (localhost:1234 refused)
**Redistribution flagged:** temujin & kublai can offload to mongke, chagatai, jochi (all idle)

## System Health
Neo4j: unknown (not reporting in tock) | Idle agents: mongke, chagatai, jochi | Tock queue: 4
⚠️ **Model mismatch:** mongke and chagatai running on `glm-5`, configured for `claude-opus-4-6`
✅ Ledger reconciliation: no mismatches
