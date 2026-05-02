# Launchd Services Registry

Registry of all launchd services for the Kurultai multi-agent system.

## Active Services (18 total)

### Persistent Services (KeepAlive daemons)

| Label | Script/Command | Purpose |
|-------|---------------|---------|
| `ai.openclaw.gateway` | `openclaw gateway --port 18789` | OpenClaw gateway (Node.js) |
| `com.kurultai.api` | `uvicorn tools.kurultai.api.main:app --port 8082` | Kurultai REST API (Python/FastAPI) |
| `com.kurultai.the-kurultai` | `server.js` | Dashboard web app (Node.js) |
| `com.kurultai.signal-jsonrpc` | `signal_jsonrpc_server.py --port 8080` | Signal messaging JSONRPC server |
| `com.kurultai.task-executor` | `task_executor.py` | Task execution daemon (claims + executes tasks) |
| `com.kurultai.ogedei-watchdog` | `ogedei-watchdog.py --daemon` | Quality assurance daemon (18 checks at 30s cadence, detect-only for stalled tasks) |
| `com.kurultai.heartbeat-writer` | `heartbeat_writer.py` | Writes infra heartbeats via brain-service (telemetry.heartbeat -> agent_state in telemetry.db) every 30s. Migrated 2026-05-02 (Phase 5 Neo4j decommission). |
| `com.kurultai.experiment-pool` | `experiment-pool.py` | Bounded experiment subprocess pool (max 3) |
| `com.kurultai.fs-indexer` | `fs_indexer.py --interval 30` | QUARANTINED 2026-05-02 (Phase 5 Neo4j decommission). Plist disabled. See `docs/fs-indexer-retired-20260502.md`. Re-implementation deferred to the Phase 3 task-lifecycle carveout. |
| `com.cloudflared.kublai` | `cloudflared tunnel run` | Cloudflare tunnel |

### Scheduled/Interval Jobs

| Label | Script | Schedule | Purpose |
|-------|--------|----------|---------|
| `com.kurultai.heartbeat-watchdog` | `watchdog-gather.sh` | Every 5 min | Infrastructure health metrics ("tick") |
| `com.kurultai.task-reaper` | `task-reaper.py` | Every 5 min | Sole owner of orphan recovery + executor restart |
| `com.kurultai.failed-task-review` | `failed-task-review.py` | Every 1 hour | Categorizes and reports failed tasks |
| `com.kurultai.calendar-reminders` | `run_calendar_worker.sh` | Every 120s | Calendar reminder processing |
| `com.kurultai.daily-task-review` | `daily-task-review.py` | Daily 7 AM | Reviews completed tasks (30% sampling for normal/low priority) |
| `ai.kurultai.rotate-ledger` | `rotate_ledger.py` | Daily 1:50 AM | Archives ledger entries older than 14 days |
| `com.kurultai.backup` | `backup_neo4j.sh` | Daily 2:00 AM | Neo4j database backup |
| `ai.kurultai.twitter-maintenance` | `twitter_maintenance.py` | 9am/12pm/2pm/7pm + Sun 10am | Twitter posting and engagement |

### Infrastructure Services (Homebrew-managed)

| Label | Service |
|-------|---------|
| `homebrew.mxcl.neo4j` | Neo4j graph database |
| `homebrew.mxcl.redis` | Redis cache |
| `homebrew.mxcl.ollama` | Ollama LLM server |

## Plist Locations

All plists are located in `~/Library/LaunchAgents/`:

```
~/Library/LaunchAgents/ai.openclaw.gateway.plist
~/Library/LaunchAgents/com.kurultai.api.plist
~/Library/LaunchAgents/com.kurultai.the-kurultai.plist
~/Library/LaunchAgents/com.kurultai.signal-jsonrpc.plist
~/Library/LaunchAgents/com.kurultai.task-executor.plist
~/Library/LaunchAgents/com.kurultai.ogedei-watchdog.plist
~/Library/LaunchAgents/com.kurultai.heartbeat-writer.plist
~/Library/LaunchAgents/com.kurultai.experiment-pool.plist
~/Library/LaunchAgents/com.kurultai.fs-indexer.plist.disabled-2026-05-02  # quarantined; see docs/fs-indexer-retired-20260502.md
~/Library/LaunchAgents/com.cloudflared.kublai.plist
~/Library/LaunchAgents/com.kurultai.heartbeat-watchdog.plist
~/Library/LaunchAgents/com.kurultai.task-reaper.plist
~/Library/LaunchAgents/com.kurultai.failed-task-review.plist
~/Library/LaunchAgents/com.kurultai.calendar-reminders.plist
~/Library/LaunchAgents/com.kurultai.daily-task-review.plist
~/Library/LaunchAgents/ai.kurultai.rotate-ledger.plist
~/Library/LaunchAgents/com.kurultai.backup.plist
~/Library/LaunchAgents/ai.kurultai.twitter-maintenance.plist
```

## Management Commands

```bash
# Load a service
launchctl load ~/Library/LaunchAgents/<label>.plist

# Unload a service
launchctl unload ~/Library/LaunchAgents/<label>.plist

# Check service status
launchctl list | grep -E 'kurultai|openclaw|cloudflared'

# View service logs
tail -f ~/.openclaw/agents/main/logs/<service>.log
```

## Disabled Services

Located in `~/Library/LaunchAgents/_disabled/`:

| Label | Reason |
|-------|--------|
| `com.kurultai.squad-chat` | Exit code 2 crash loop (missing websockets/aiohttp). Fix or delete. |
| `com.kurultai.fs-indexer` | Quarantined 2026-05-02 for Phase 5 Neo4j decommission. Plist renamed to `.disabled-2026-05-02` (still in `~/Library/LaunchAgents/`, not `_disabled/`). Re-implementation deferred to Phase 3 task-lifecycle carveout. See `docs/fs-indexer-retired-20260502.md`. |

## Deleted/Archived (2026-03-23 cron consolidation)

| Label | Superseded By |
|-------|---------------|
| `com.kurultai.ogedei-dispatcher` | task-executor |
| `com.kurultai.ogedei-heartbeat` | ogedei-watchdog (all checks duplicated) |
| `ai.kurultai.brainstorm` | Ad-hoc, never reloaded |
| `ai.kurultai.hourly-reflection` | daily-task-review |
| `ai.kurultai.kurultai-reflect` | daily-task-review |
| `com.kurultai.kanban` | Deprecated |
| `com.kurultai.kurultai-monitor` | heartbeat-watchdog |
| `com.kurultai.system-health` | heartbeat-watchdog |
| `com.openclaw.kurultai` | ogedei-watchdog |
| `com.openclaw.tock` | heartbeat-watchdog |
| `com.openclaw.watchdog` | heartbeat-watchdog + ogedei-watchdog |
| `com.kurultai.auto-dispatch` | task-executor |
| `com.kurultai.worker` | task-executor |

## Key Design Decisions

1. **Single-writer orphan recovery**: `task-reaper.py` is the sole owner of orphan recovery and executor restart. `ogedei-watchdog.py` detects and alerts but does NOT recover.
2. **watchdog-gather.sh simplified**: Removed 3 duplicate sub-scripts (credential-health-monitor, completion-audit, subprocess-audit). Now reads ogedei-watchdog state files instead.
3. **Schedule stagger**: rotate-ledger at 1:50 AM, backup at 2:00 AM (no collision).
4. **heartbeat-writer stays separate**: ogedei-watchdog is file-based, so heartbeat-writer remains its own daemon. As of 2026-05-02 it writes via brain-service (`telemetry.heartbeat` RPC -> `agent_state` row in `~/.kublai/telemetry.db`) instead of Neo4j (Phase 5 migration). Backups: `~/backups/neo4j-pre-migration/2026-05-02/heartbeat_writer.py.pre-phase-5`.

## Service Dependencies

```
task-executor (continuous)
    └── Requires: Neo4j, Redis, LLM API

ogedei-watchdog (continuous, 30s cadence)
    └── Requires: filesystem only (no Neo4j)

heartbeat-writer (continuous, 30s cadence)
    └── Requires: brain-service (Unix socket /Users/kublai/.kublai/brain-service.sock)
        # Migrated off Neo4j 2026-05-02 (Phase 5)

task-reaper (5 min)
    └── Requires: Neo4j, Redis

heartbeat-watchdog / watchdog-gather (5 min)
    └── Requires: Neo4j, Redis

daily-task-review (daily)
    └── Requires: Neo4j, LLM API

signal-jsonrpc (continuous)
    └── Requires: signal-cli, port 8080

api (continuous)
    └── Requires: Neo4j, port 8082

gateway (continuous)
    └── Requires: port 18789
```

---

Last Updated: 2026-05-02
