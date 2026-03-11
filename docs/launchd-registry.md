# Launchd Services Registry

Registry of all launchd services for the Kurultai multi-agent system.

## Active Services

| Service | Plist | Owner | Schedule | Purpose |
|---------|-------|-------|----------|---------|
| task-watcher | `com.kurultai.task-watcher` | Kublai | Continuous | Task execution daemon - picks up pending tasks and executes them |
| ogedei-watchdog | `com.kurultai.ogedei-watchdog` | Ogedei | 5 minutes | Quality assurance daemon - monitors system health and quality metrics |
| hourly-reflection | `com.kurultai.hourly-reflection` | All | Hourly | Agent reflection cycle - each agent reflects on recent work |
| watchdog-gather | `com.kurultai.watchdog-gather` | Ogedei | 5 minutes | Health telemetry collection - gathers Neo4j, Redis, cron, and agent health |
| kurultai-monitor | `com.kurultai.kurultai-monitor` | Mongke | 1 minute | System monitoring - deep browser checks and service health |
| system-health-check | `com.kurultai.system-health-check` | Kublai | 5 minutes | Unified health monitoring - gateway, Neo4j, Redis, website checks |

## Plist Locations

All plists are located in `~/Library/LaunchAgents/`:

```
~/Library/LaunchAgents/com.kurultai.task-watcher.plist
~/Library/LaunchAgents/com.kurultai.ogedei-watchdog.plist
~/Library/LaunchAgents/com.kurultai.hourly-reflection.plist
~/Library/LaunchAgents/com.kurultai.watchdog-gather.plist
~/Library/LaunchAgents/com.kurultai.kurultai-monitor.plist
~/Library/LaunchAgents/com.kurultai.system-health-check.plist
```

## Management Commands

```bash
# Load a service
launchctl load ~/Library/LaunchAgents/com.kurultai.<service>.plist

# Unload a service
launchctl unload ~/Library/LaunchAgents/com.kurultai.<service>.plist

# Check service status
launchctl list | grep kurultai

# View service logs
tail -f ~/.openclaw/agents/main/logs/<service>.log
```

## Deprecation Candidates

| Service | Status | Replacement | Notes |
|---------|--------|-------------|-------|
| heartbeat-watchdog | Deprecated | watchdog-gather.sh | Superseded by unified telemetry collection |

## Cron Jobs (to migrate to launchd)

| Job | Schedule | Purpose | Migration Priority |
|-----|----------|---------|-------------------|
| `rotate_logs.sh` | Daily 2AM | Log rotation | Low |
| `backup.sh` | Daily 3AM | System backup | Medium |

## Health Check Hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│ system-health-check.py                                          │
│   - Unified 5-minute health monitoring                          │
│   - Calls: stale-lock-cleanup.py                                │
├─────────────────────────────────────────────────────────────────┤
│ Related health scripts:                                         │
│   - gateway-health-check.py (specialized for gateway incidents) │
│   - health_dashboard.py (dashboard interface)                   │
│   - ogedei-watchdog.py (quality assurance daemon, 5-min)        │
│   - task-watcher.py (task execution daemon, continuous)         │
│   - kurultai-monitor.py (deep browser checks, 1-min)            │
├─────────────────────────────────────────────────────────────────┤
│ Deprecated:                                                     │
│   - heartbeat-watchdog (superseded by watchdog-gather.sh)       │
└─────────────────────────────────────────────────────────────────┘
```

## Service Dependencies

```
task-watcher (continuous)
    └── Requires: Neo4j, Redis

ogedei-watchdog (5 min)
    └── Requires: Neo4j

hourly-reflection (hourly)
    └── Requires: Neo4j, LLM API

kurultai-monitor (1 min)
    └── Requires: Internet connectivity

system-health-check (5 min)
    └── Requires: Neo4j, Redis, Internet connectivity
```

---

Last Updated: 2026-03-09
