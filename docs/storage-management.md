# Storage Management — OpenClaw Kurultai

Disk space monitoring and alerting for the Mac Mini hosting OpenClaw.

## Overview

The storage monitoring system tracks disk usage, OpenClaw growth, and provides alerts when storage thresholds are reached. This prevents service disruption from full disks.

**Current Status (2026-03-08):**
- Total Storage: 228 GB
- Used: 14.8 GB (34%)
- Free: 28.5 GB
- OpenClaw Usage: 5.6 GB
  - Agents: 3.7 GB
  - Logs: 555 MB
  - Backups: 614 MB

## Components

### 1. Storage Monitor Script

**Location:** `~/.openclaw/agents/main/scripts/storage_monitor.py`

**Features:**
- Disk usage checking via `df` command (APFS-aware)
- OpenClaw directory size tracking
- Growth rate calculation (GB/week)
- Threshold-based alerting
- Cleanup suggestions
- Historical state persistence

**Usage:**
```bash
# Full check with alerts
python3 ~/.openclaw/agents/main/scripts/storage_monitor.py

# Quiet mode (no output unless alert)
python3 ~/.openclaw/agents/main/scripts/storage_monitor.py --quiet

# JSON output for dashboards
python3 ~/.openclaw/agents/main/scripts/storage_monitor.py --json

# Show cleanup suggestions only
python3 ~/.openclaw/agents/main/scripts/storage_monitor.py --suggest

# Run without sending alerts
python3 ~/.openclaw/agents/main/scripts/storage_monitor.py --no-alert
```

**Exit Codes:**
- 0: Healthy (below 70%)
- 1: Warning (70%+)
- 2: Critical (85%+)
- 3: Emergency (95%+)

### 2. Thresholds

| Level | Percent | Action |
|-------|---------|--------|
| Healthy | < 70% | No action |
| Warning | 70% | Plan to buy external storage |
| Critical | 85% | Buy external storage within 2-3 weeks |
| Emergency | 95% | Immediate action required |

### 3. Alert Messages

**Warning (70%):**
```
💾 Storage Alert — 70% Full

Current usage: 159GB used of 228GB (70%)
Free space: 69GB
OpenClaw usage: 8.2GB

Growth rate: ~0.5GB/week
Projected critical (85%): ~18 weeks

Recommendation: Consider purchasing 1-2TB external SSD
Estimated cost: $100-150

No immediate action needed, but plan ahead!
```

**Critical (85%):**
```
🚨 Storage Alert — 85% Full

Current usage: 194GB used of 228GB (85%)
Free space: 34GB
OpenClaw usage: 12.5GB

Growth rate: ~0.5GB/week

ACTION NEEDED: Purchase external storage within 2-3 weeks
Recommended: 2TB external SSD (~$150)

Should I suggest specific cleanup actions?
```

**Emergency (95%):**
```
⚠️ URGENT: Storage 95% Full

Current usage: 217GB used of 228GB (95%)
Free space: 11GB

IMMEDIATE ACTION REQUIRED:
1. Purchase external storage TODAY
2. Free up space with emergency cleanup

Cleanup options:
- Old logs (90+ days): ~5GB
- Old backups: ~3GB
- Archive old conversations: ~2GB

Should I proceed with emergency cleanup?
```

## State Persistence

**Location:** `~/.openclaw/storage-state.json`

Stores:
- Last check timestamp
- Historical size data (last 90 days)
- Growth rate calculations
- Baseline measurements

Example:
```json
{
  "last_check": "2026-03-08T11:43:00",
  "baseline_size": 5.5,
  "baseline_date": "2026-03-01T00:00:00",
  "history": [
    {
      "date": "2026-03-01T00:00:00",
      "disk_used_gb": 14.2,
      "disk_percent": 0.33,
      "openclaw_size_gb": 5.4,
      "openclaw_breakdown": {
        "agents": "3.6GB",
        "logs": "550MB",
        "backups": "600MB"
      }
    }
  ]
}
```

## Cleanup Suggestions

The monitor automatically suggests cleanup actions:

| Category | Age Threshold | Action |
|----------|---------------|--------|
| Old Logs | 90 days | Compress |
| Old Backups | 30 days | Archive |
| Old Conversations | 365 days | Archive |
| Task Ledger | 1000+ entries | Review |

## Scheduling

### Weekly Storage Check

**Cron Job:** `storage-monitor-weekly`

```json
{
  "name": "Storage Monitoring - Weekly Check",
  "schedule": { "kind": "cron", "expr": "0 9 * * 1" },
  "payload": {
    "kind": "systemEvent",
    "text": "/usr/bin/python3 ~/.openclaw/agents/main/scripts/storage_monitor.py"
  }
}
```

Runs every Monday at 9 AM.

## External Storage Recommendations

When purchasing external storage:

1. **Capacity:**
   - 1TB SSD (~$100) - sufficient for next 2-3 years
   - 2TB SSD (~$150) - recommended for longer-term

2. **Format:** APFS (macOS native)

3. **Setup:**
   ```bash
   # After connecting, format as APFS
   diskutil list  # Find disk identifier (e.g., /dev/disk2)
   diskutil eraseDisk APFS "ExternalStorage" /dev/disk2

   # Create backup directory
   mkdir /Volumes/ExternalStorage/openclaw-backup

   # Configure automated backups (via rsync or Time Machine)
   ```

4. **Automated Backup Configuration:**
   ```bash
   # Add to crontab for daily backup at 3 AM
   0 3 * * * rsync -av --delete ~/.openclaw /Volumes/ExternalStorage/openclaw-backup/
   ```

## Troubleshooting

### Incorrect Disk Usage

If the monitor shows incorrect disk usage:

```bash
# Verify df output matches monitor
df -h /
python3 ~/.openclaw/agents/main/scripts/storage_monitor.py --no-alert

# Check for APFS snapshot bloat
tmutil listlocalsnapshots /
```

### Alerts Not Received

If alerts aren't sent via Signal:

1. Check Signal CLI availability:
   ```bash
   /opt/signal-cli-0.13.24/bin/signal-cli --version
   ```

2. Check gateway API:
   ```bash
   curl http://localhost:18789/signal/status
   ```

3. Run manually to see errors:
   ```bash
   python3 ~/.openclaw/agents/main/scripts/storage_monitor.py --no-alert
   ```

### Growth Rate Calculation Issues

If growth rate is 0 or inaccurate:

```bash
# Check state file history
cat ~/.openclaw/storage-state.json | jq '.history'

# Manually trigger several checks over time
python3 ~/.openclaw/agents/main/scripts/storage_monitor.py --no-alert
```

## Integration with Other Systems

### Dashboard Integration

The JSON output can be consumed by the.kurult.ai dashboard:

```bash
curl http://localhost:18789/storage/status
```

### Neo4j Telemetry

Storage metrics can be stored in Neo4j for trend analysis:

```cypher
CREATE (s:StorageMetrics {
  date: datetime(),
  disk_percent: 34,
  openclaw_gb: 5.6,
  growth_rate_per_week: 0.002
})
```

## Maintenance

- **Weekly:** Automatic check via cron
- **Monthly:** Review cleanup suggestions
- **Quarterly:** Verify external backup integrity
- **Annually:** Archive old conversations and logs

## Contact

For issues or questions about storage monitoring, create a task for Ögedei (operations agent).

---

**Last Updated:** 2026-03-08
**Maintainer:** Ögedei (Operations Guardian)
