# Kurultai Status — 2026-03-07 15:08

## Activity (last 2h)
- jochi: 4 completed, 0 failed (neo4j; not in ledger — reconciliation delta=4)
- temujin, mongke, chagatai, ogedei, kublai: idle (0 completions in ledger)

> Note: task-ledger.jsonl has no recent entries — neo4j is authoritative source above.

## Pending Queue (3 total)
| Agent   | Pending | Next task |
|---------|---------|-----------|
| temujin | 3       | Review: Ogedei agent stalled — model config + queue failure analysis |
| temujin | —       | Build visual frontend calendar for Danny (monthly events) |
| temujin | —       | 3-hour review: the.kurult.ai |
| others  | 0       | — |

Note: temujin also has 1 executing (`high-1772910533`).

## Kublai's Next Steps
**Initiative:** Review and process pending task queue backlog (heuristic fallback — local LLM at port 1234 unreachable)
**Assigned to:** kublai
**Rationale:** Tasks queued but not being processed
**Status:** In cooldown since 15:03; kublai-actions found no pending feedback to act on

## System Health
Neo4j: up | Redis: up | Tick: degraded | Total queued: 3 (tock reports 2)
Idle agents: kublai, mongke, chagatai, jochi, ogedei
Cron: 14/18 healthy, 0 erroring

⚠️  Session model mismatch on 5/6 agents (mongke=glm-5, chagatai=qwen3.5-plus, temujin=lukey03/qwen3.5-9b, jochi=kimi-k2.5, ogedei=qwen3-coder-next) — model guards active, config resolves to claude-opus-4-6
⚠️  Ledger/neo4j reconciliation gap: jochi 4 neo4j completions not in ledger
⚠️  Local LLM (port 1234) down — kublai-initiative using heuristic fallback
