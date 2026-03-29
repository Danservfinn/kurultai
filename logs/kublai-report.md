# Kurultai Status — 2026-03-23 16:50

## Activity (last 2h)
- (all agents: idle — last ledger entry was 08:54 UTC, ~8h ago)
- *Last 8h:* ogedei: 1 completed

## Pending Queue (9 total)
| Agent    | Pending | Next task |
|----------|---------|-----------|
| temujin  | 2       | Fix parsethis.ai 404 error |
| jochi    | 3       | Diagnose and restart reflection pipeline (15,736 misses, 164h stale) |
| ogedei   | 3       | Get https://www.parsethis.ai/ online |
| chagatai | 1       | C002 Auto: Documentation scan |

## Kublai's Next Steps
**Initiative:** Review and process pending task queue backlog
**Assigned to:** ogedei
**Rationale:** Tasks are queued but not being processed
⚠️ *Heuristic fallback* — local LLM (localhost:1234) is unreachable

## System Health
Neo4j: **up** | Redis: **up** | Tick: **degraded** | Total queued: 9

**⚠️ STALLED AGENTS — tasks not being processed:**
- jochi: oldest task ~12.3h old (44,220s)
- chagatai: oldest task ~10.9h old (39,120s)
- ogedei: oldest task ~10.4h old (37,284s)

**⚠️ Other issues:**
- Cron error: "Kurultai Reflection (4-hour cycle)" — 1 consecutive error (ran 45min)
- Zombie process: kublai PID 91671 (~11.3h old, no .executing.md file)
- Local LLM offline: initiative engine using heuristic fallback

✅ Ledger reconciliation: clean (no mismatches)
