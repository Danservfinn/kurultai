# MyClaw Backup Skill — Installed ✅

**Date:** 2026-03-04  
**Source:** https://github.com/LeoYeAI/openclaw-backup  
**Powered by:** MyClaw.ai

---

## Installation Status

| Component | Status | Location |
|-----------|--------|----------|
| **Skill** | ✅ Installed | `skills/myclaw-backup/` |
| **Scripts** | ✅ Copied | `skills/myclaw-backup/scripts/` |
| **First Backup** | ✅ Complete | `/tmp/openclaw-backups/` |
| **Backup Size** | 3.0 GB | Compressed archive |

---

## What Was Backed Up

| Component | Status | Size |
|-----------|--------|------|
| Workspace | ✅ | 248K |
| Gateway config (openclaw.json) | ✅ | 9.9 KB |
| System skills | ⚠️ None found | - |
| Credentials & channel state | ✅ | signal, neo4j, gemini |
| Agent config & sessions | ✅ | 526 sessions |
| Devices | ✅ | paired.json, pending.json |
| Identity | ✅ | device-auth.json, device.json |
| Scripts | ✅ | - |
| Cron state | ✅ | 3 files |

**Archive:** `openclaw-backup_kublai.local_20260304_165222.tar.gz`

---

## Scripts Available

| Script | Purpose | Command |
|--------|---------|---------|
| `backup.sh` | Create backup | `bash skills/myclaw-backup/scripts/backup.sh [output-dir]` |
| `restore.sh` | Restore backup | `bash skills/myclaw-backup/scripts/restore.sh <archive> --dry-run` |
| `serve.sh` | HTTP server | `bash skills/myclaw-backup/scripts/serve.sh start --token TOKEN --port 7373` |
| `schedule.sh` | Cron scheduling | `bash skills/myclaw-backup/scripts/schedule.sh --interval daily` |

---

## Security Notes

⚠️ **This skill handles highly sensitive data:**
- Bot tokens
- API keys
- Channel credentials
- Session history

**Security measures:**
- Backup archives are `chmod 600` (owner read/write only)
- HTTP server requires `--token` (refuses to start without)
- Shell-execution endpoints are localhost-only
- Always run `--dry-run` before restore

---

## Common Workflows

### Create Backup
```bash
bash skills/myclaw-backup/scripts/backup.sh /tmp/openclaw-backups
```

### Restore (Always Dry-Run First)
```bash
# Preview changes
bash skills/myclaw-backup/scripts/restore.sh /tmp/openclaw-backups/openclaw-backup_TIMESTAMP.tar.gz --dry-run

# Apply restore
bash skills/myclaw-backup/scripts/restore.sh /tmp/openclaw-backups/openclaw-backup_TIMESTAMP.tar.gz
```

### Start HTTP Server (Browser UI)
```bash
# Generate secure token
TOKEN=$(openssl rand -hex 16)

# Start server
bash skills/myclaw-backup/scripts/serve.sh start --token $TOKEN --port 7373

# Open in browser: http://localhost:7373/?token=$TOKEN
```

### Schedule Daily Auto-Backup
```bash
bash skills/myclaw-backup/scripts/schedule.sh --interval daily
```

---

## Migration to New Server

**Old machine:**
```bash
bash skills/myclaw-backup/scripts/serve.sh start --token MYTOKEN --port 7373
```

**New machine:**
```bash
# Download backup
curl -O "http://OLD_IP:7373/download/openclaw-backup_TIMESTAMP.tar.gz?token=MYTOKEN"

# Dry-run first
bash skills/myclaw-backup/scripts/restore.sh openclaw-backup_TIMESTAMP.tar.gz --dry-run

# Apply
bash skills/myclaw-backup/scripts/restore.sh openclaw-backup_TIMESTAMP.tar.gz
```

---

## Cron Job Integration

To add automated daily backup via OpenClaw cron:

```json
{
  "name": "daily-openclaw-backup",
  "schedule": { 
    "kind": "cron", 
    "expr": "0 3 * * *", 
    "tz": "UTC" 
  },
  "payload": {
    "kind": "agentTurn",
    "message": "Run backup: bash skills/myclaw-backup/scripts/backup.sh /tmp/openclaw-backups",
    "timeoutSeconds": 300
  },
  "sessionTarget": "main"
}
```

---

## Files Installed

```
skills/myclaw-backup/
├── SKILL.md
└── scripts/
    ├── backup.sh      (8.9 KB)
    ├── restore.sh     (15.7 KB)
    ├── schedule.sh    (2.0 KB)
    ├── serve.sh       (3.3 KB)
    ├── server.js      (11.0 KB)
    └── ui.html        (6.9 KB)
```

---

*Installation complete. First backup created successfully.*
