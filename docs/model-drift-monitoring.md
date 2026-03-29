# Model Drift Monitoring - Alert Mechanism

## Overview
This document describes the model drift monitoring system added to prevent silent degradation of agent capabilities.

## Components

### 1. Watchdog Integration (`ogedei-watchdog.py`)
- **Function**: `check_model_drift(state)`
- **Location**: Line 1811
- **Check Interval**: Every 5 minutes (300 seconds)
- **Integration**: Added to main health check loop (line 1997)

**What it checks:**
- Current model in `~/.openclaw/claude/settings.json`
- Expected model: `claude-sonnet-4-6`
- Current mode (auto/backup) from `~/.openclaw/claude/mode.json`

**Metrics stored in watchdog state:**
```python
state["model_drift"] = {
    "current_model": str,
    "expected_model": str,
    "mode": str,
    "drift_detected": bool,
    "last_check": ISO timestamp
}
```

**Alert behavior:**
- **Warning severity** when drift detected
- Logs to watchdog log file
- Included in cycle issue summary
- Metrics available for dashboard display

### 2. Settings Validation Script (`validate_settings.sh`)
- **Location**: `~/.openclaw/agents/ogedei/scripts/validate_settings.sh`
- **Cron Schedule**: Hourly at minute 13 (13 * * * *)
- **Log Output**: Appends to `/Users/kublai/.openclaw/logs/cron-health-monitor.log`

**What it checks:**
1. `settings.json` - Must have model `claude-sonnet-4-6`
2. `settings.backup.json` - Warns if model differs
3. `mode.json` - Warns if in backup mode

**Exit codes:**
- `0` - All settings valid
- `1` - Errors detected (wrong model, file corruption)

**Output format:**
```
❌ ERRORS:
   settings.json has wrong model: glm-5 (expected: claude-sonnet-4-6)
```

Or:
```
⚠️  WARNINGS:
   System in backup mode (fallback active)
```

Or:
```
✅ All settings valid
```

### 3. Hourly Health Check (Cron Job)
- **Job ID**: `4de563d2-6382-4e2c-866f-223336523b3d`
- **Job Name**: "Settings Validation - Hourly"
- **Schedule**: `13 * * * *` (13th minute of every hour)
- **Delivery**: None (logs only, no Signal alerts)

**Why no delivery?**
- Settings validation is informational
- Watchdog already alerts on drift detection
- Hourly runs provide historical log trail
- Prevents alert fatigue

## Alert Escalation Path

### Level 1: Watchdog Detection (Real-time)
- **Interval**: Every 5 minutes
- **Action**: Logs warning, stores metrics
- **Visibility**: Watchdog logs, dashboard

### Level 2: Hourly Validation (Persistent)
- **Interval**: Every hour at minute 13
- **Action**: Full settings validation, writes to log
- **Visibility**: Cron health monitor log

### Level 3: Manual Intervention
- **Trigger**: Persistent drift detected
- **Action**: Investigate root cause, remediate
- **Tools**: Dashboard settings panel, manual config reset

## Testing

### Test Watchdog Integration
```bash
# Watchdog will automatically check on next cycle
# Or manually test the function:
python3 << 'EOF'
import sys
sys.path.insert(0, '/Users/kublai/.openclaw/agents/ogedei/scripts')
from ogedei_watchdog import check_model_drift
state = {}
issues = check_model_drift(state)
print(f"Issues: {issues}")
print(f"State: {state.get('model_drift', {})}")
EOF
```

### Test Settings Validation Script
```bash
/Users/kublai/.openclaw/agents/ogedei/scripts/validate_settings.sh
echo $?  # Exit code: 0 = valid, 1 = errors
```

### View Cron Job Output
```bash
tail -f /Users/kublai/.openclaw/logs/cron-health-monitor.log
```

## Remediation Actions

When model drift is detected:

1. **Identify the drift source:**
   - Check watchdog logs: `tail -50 ~/.openclaw/agents/ogedei/logs/watchdog.log`
   - Check settings: `cat ~/.openclaw/claude/settings.json | grep ANTHROPIC_MODEL`
   - Check mode: `cat ~/.openclai/claude/mode.json`

2. **Remediate via dashboard:**
   - Open Kurultai dashboard
   - Navigate to Model Configuration
   - Reset to source of truth
   - Apply to fleet

3. **Verify fix:**
   - Run validation script: `~/.openclaw/agents/ogedei/scripts/validate_settings.sh`
   - Check watchdog clears alert on next cycle

## Prevention

To prevent future drift:
- Always use dashboard for model changes (never manual edits)
- Monitor backup mode activation (may indicate config guard issues)
- Review drift metrics in dashboard regularly
- Keep settings.backup.json in sync with expected config

## Related Files
- `/Users/kublai/.openclaw/agents/ogedei/scripts/ogedei-watchdog.py` - Main watchdog
- `/Users/kublai/.openclaw/agents/ogedei/scripts/validate_settings.sh` - Validation script
- `/Users/kublai/.openclaw/cron/jobs.json` - Cron job definitions
- `/Users/kublai/.openclaw/claude/settings.json` - Current settings
- `/Users/kublai/.openclaw/claude/settings.backup.json` - Backup settings
- `/Users/kublai/.openclaw/claude/mode.json` - Auto/backup mode

## Future Enhancements
- Add Signal alert for critical drift (backup mode + wrong model)
- Dashboard widget showing drift history
- Auto-remediation option (reset to backup if validated)
- Integration with config guard to prevent manual edits
