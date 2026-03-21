# Backup and Restore System

## Overview

The Kurultai backup system provides automated daily snapshots of all critical data stores, with manual restore capabilities for disaster recovery. Backups are stored locally with a 7-day rolling retention window.

**Script:** `~/.openclaw/agents/main/scripts/backup-kurultai.sh`

## What Gets Backed Up

| Component | Source | Description |
|-----------|--------|-------------|
| Neo4j database | `bolt://localhost:7687` | Agent state graph, task relationships, knowledge graph |
| SQLite databases | `~/.openclaw/data/*.db` | Local data stores (metrics, caches) |
| Task ledger | `~/.openclaw/tasks/task-ledger.jsonl` | Complete task history (all agents) |
| Agent state files | `~/.openclaw/agents/<agent>/state.json` | Per-agent runtime state (7 agents: kublai, temujin, mongke, chagatai, jochi, ogedei, tolui) |

**Backup destination:** `~/.openclaw/backups/daily/backup_YYYYMMDD_HHMMSS/`

Each backup includes a `manifest.json` recording which components were successfully captured.

## Running a Manual Backup

```bash
# Create a full backup
bash ~/.openclaw/agents/main/scripts/backup-kurultai.sh

# List existing backups with timestamps
bash ~/.openclaw/agents/main/scripts/backup-kurultai.sh --list
```

**Prerequisites:**
- Neo4j credentials must exist at `~/.openclaw/credentials/neo4j.env` (exports `NEO4J_USER`, `NEO4J_PASSWORD`, optionally `NEO4J_URI`)
- `sqlite3` CLI available for consistent database copies
- `neo4j-admin` preferred for Neo4j dumps; falls back to `cypher-shell` export if unavailable

## Restoring from Backup

```bash
# 1. List available backups to find the one you need
bash ~/.openclaw/agents/main/scripts/backup-kurultai.sh --list

# 2. Restore a specific backup (3-second safety delay before overwrite)
bash ~/.openclaw/agents/main/scripts/backup-kurultai.sh --restore backup_20260318_080000
```

**What gets restored automatically:**
- SQLite databases are copied back to `~/.openclaw/data/`
- Task ledger is restored to `~/.openclaw/tasks/task-ledger.jsonl`

**What requires manual steps:**
- **Neo4j:** The script prints the restore command but does NOT execute it (requires stopping the database first):
  ```bash
  neo4j stop
  neo4j-admin database load neo4j --from-path=~/.openclaw/backups/daily/<backup_id>/
  neo4j start
  ```

**Warning:** Restore overwrites current data. The script gives a 3-second window to Ctrl+C before proceeding.

## Backup Schedule and Retention

- **Retention:** 7 days (configured via `RETENTION_DAYS` in the script)
- **Cleanup:** Old backups are automatically purged after each new backup
- **Automation:** Can be scheduled via cron. Example crontab entry:
  ```bash
  # Daily backup at 2 AM
  0 2 * * * bash ~/.openclaw/agents/main/scripts/backup-kurultai.sh >> ~/.openclaw/logs/backup.log 2>&1
  ```

## Recovery Procedures

### Scenario: Neo4j database corruption

1. Stop Neo4j: `neo4j stop`
2. List backups: `bash backup-kurultai.sh --list`
3. Restore the most recent backup with a valid Neo4j dump:
   ```bash
   neo4j-admin database load neo4j --from-path=~/.openclaw/backups/daily/<backup_id>/
   ```
4. Start Neo4j: `neo4j start`
5. Verify agents reconnect: `python3 agent-manager.py --status`

### Scenario: Corrupted task ledger

```bash
bash ~/.openclaw/agents/main/scripts/backup-kurultai.sh --restore <backup_id>
```
This restores the task-ledger.jsonl. Active tasks in agent queues (individual `.md` files) are not affected.

### Scenario: Agent state lost or inconsistent

Agent state files (`state.json`) are backed up per-agent. To restore a single agent's state:
```bash
cp ~/.openclaw/backups/daily/<backup_id>/agent_state/chagatai_state.json \
   ~/.openclaw/agents/chagatai/state.json
```
Then re-activate the agent: `python3 agent-manager.py --activate`

### Scenario: Full system recovery

1. Restore SQLite + task ledger: `bash backup-kurultai.sh --restore <backup_id>`
2. Restore Neo4j manually (see above)
3. Copy agent state files from backup
4. Activate all agents: `python3 agent-manager.py --activate`
5. Verify health: `python3 agent-manager.py --status`

## Related Tools

- **`apply-agent-backup-config.py`** — Restores standardized agent settings (model, plugins, hooks) across the fleet. Not a data backup; it resets `.claude/settings.json` files to a known-good configuration. Use `--dry-run` to preview.
- **`agent-manager.py`** — Health monitoring and agent activation. Use `--status` after restore to verify agents are running.
- **`myclaw-backup` skill** — Higher-level backup/restore skill for OpenClaw configuration, agent memory, and skills.
