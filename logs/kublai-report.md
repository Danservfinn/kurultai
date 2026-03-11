# Kurultai Status — 2026-03-11 06:11

## Activity (last 2h)
All agents: idle (0 completed in last 2h)

## Pending Queue (7 total)
| Agent    | Pending | Next task |
|----------|---------|-----------|
| kublai   | 1       | Review routing decisions and optimize agent load balancing |
| temujin  | 2       | Self-Wake -- Execute Blocked Items |
| mongke   | 1       | Self-Wake -- Execute Blocked Items |
| chagatai | 1       | (self-task queued) |
| jochi    | 2       | Investigate stalled task: ogedei idle task; Investigate mongke low performance |
| ogedei   | 0       | — |

## Kublai's Next Steps
**Initiative:** Review routing decisions and optimize agent load balancing
**Assigned to:** kublai
**Rationale:** Rotating proactive initiative (System efficiency - improve task distribution across fleet)
**Mode:** Heuristic fallback (LLM unavailable: localhost:1234 connection refused)

## System Health
Neo4j: up | Redis: up | Tick: degraded | Total queued: 7

**Issues:**
- 5 cron jobs erroring (Daily Goal Progress Summary, 4 skipped)
- Backup stale (last: 2026-03-09)
- Zombie process detected: kublai handler (pid 26332, investigate)
- Oldest pending: jochi task (17,787s / ~5h)

**Load:** 0.095 (stable, threshold 0.8) | Routing accuracy: 87% | Overflow: 2
