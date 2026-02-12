# Heartbeat Monitor System

## Overview
Self-healing heartbeat monitoring system that ensures the Kurultai heartbeat is always running.

## Components

### 1. heartbeat_monitor.py
**Purpose:** Checks if heartbeat is running and restarts if needed
**Location:** `tools/kurultai/heartbeat_monitor.py`
**Features:**
- Checks if heartbeat_master.py process exists
- Verifies heartbeat log is being updated (not stuck)
- Automatically restarts heartbeat if dead or stale
- Logs all actions to `/tmp/heartbeat_monitor.log`

**Usage:**
```bash
python3 tools/kurultai/heartbeat_monitor.py
```

### 2. heartbeat_monitor_daemon.py
**Purpose:** Runs heartbeat_monitor.py every hour (cron alternative)
**Location:** `tools/kurultai/heartbeat_monitor_daemon.py`
**Features:**
- Runs check every hour (3600 seconds)
- Runs immediately on startup
- Handles graceful shutdown
- No cron required

**Usage:**
```bash
# Start daemon
nohup python3 tools/kurultai/heartbeat_monitor_daemon.py > /tmp/heartbeat_monitor.log 2>&1 &

# Check status
cat /tmp/heartbeat_monitor_daemon.pid

# Stop daemon
kill $(cat /tmp/heartbeat_monitor_daemon.pid)
```

## Current Status

| Component | Status | PID |
|-----------|--------|-----|
| heartbeat_master.py | ✅ Running | Check /tmp/heartbeat.pid |
| heartbeat_monitor_daemon.py | ✅ Running | Check /tmp/heartbeat_monitor_daemon.pid |

## Log Files

| File | Purpose |
|------|---------|
| `/tmp/heartbeat.log` | Heartbeat master output |
| `/tmp/heartbeat_monitor.log` | Monitor check results |
| `/tmp/heartbeat_monitor_daemon.log` | Monitor daemon output |

## Auto-Recovery Behavior

```
Every hour:
    Check if heartbeat is running
    ↓
    If NOT running → Restart heartbeat
    ↓
    If log stale (>10 min) → Restart heartbeat
    ↓
    If running normally → Do nothing
```

## Files Created

1. `tools/kurultai/heartbeat_monitor.py` - Monitor script
2. `tools/kurultai/heartbeat_monitor_daemon.py` - Hourly scheduler
3. `/tmp/heartbeat_monitor.log` - Monitor log
4. `/tmp/heartbeat_monitor_daemon.pid` - Daemon PID
