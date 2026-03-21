# Agent Manager

## Overview

The Agent Manager is the consolidated tool for monitoring agent health, tracking subagent completion, and activating agents in the Kurultai fleet. It replaces three legacy scripts (`agent-health-monitor.py`, `subagent_completion_tracker.py`, `launch-agent.py`) with a single interface.

**Script:** `~/.openclaw/agents/main/scripts/agent-manager.py`

## Managed Agents

The manager tracks six core agents: **kublai**, **temujin**, **mongke**, **chagatai**, **jochi**, **ogedei**.

## Usage

```bash
# One-time health check (prints summary and exits)
python3 agent-manager.py

# Show JSON health summary
python3 agent-manager.py --status

# Run as a continuous daemon (default: every 30s)
python3 agent-manager.py --daemon

# Custom check interval (every 60 seconds)
python3 agent-manager.py --daemon --interval 60

# Activate all agents in Neo4j
python3 agent-manager.py --activate
```

## How Health Checks Work

For each agent, the manager queries Neo4j for its `AgentState` node and checks:

1. **Existence** — Does the agent have an `AgentState` node? If not, it's marked unhealthy.
2. **Heartbeat freshness** — Is the `last_heartbeat` timestamp within the last 10 minutes? Stale heartbeats indicate a stuck or crashed agent.
3. **Status field** — Reports the current status (`running`, `idle`, etc.) and current task.

### Health output

```
=== Agent Health Summary ===
Timestamp: 2026-03-18T08:00:00
Healthy: 5/6
Unhealthy: 1/6

 kublai: running (task: fleet-coordination)
 temujin: running (task: api-fix-1234)
 mongke: running (task: research-queue)
 chagatai: running (task: docs-gap)
 jochi: running (task: security-scan)
 ogedei: Heartbeat stale (15 min ago)
```

## Auto-Recovery

In daemon mode, the manager automatically reactivates agents when:
- The heartbeat is stale (>10 minutes old)
- The `AgentState` node is missing from Neo4j

Reactivation sets the agent's status to `running`, updates `last_heartbeat` to now, and records an `activated` timestamp.

## Dependencies

- **Neo4j** — All state is stored in Neo4j `AgentState` nodes. Requires `neo4j_task_tracker.py` for driver access.
- **kurultai_paths.py** — Provides standard path constants (`AGENTS_DIR`, `SPAWN_QUEUE`, `LOGS_DIR`).

## Logs

All operations are logged to `~/.openclaw/logs/agent-manager.log` with timestamps.

## Related Tools

- **`backup-kurultai.sh`** — Backs up agent state files that the manager monitors. See [backup-restore.md](backup-restore.md).
- **`apply-agent-backup-config.py`** — Resets agent settings to known-good configuration (model, plugins, hooks). Use after fleet-wide configuration drift.
