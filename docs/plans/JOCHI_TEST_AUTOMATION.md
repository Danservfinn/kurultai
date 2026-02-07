# Jochi Automated Testing - Deployment Guide

> **Created:** 2026-02-07
> **Purpose:** Configure Jochi to periodically run tests and action results

---

## Overview

Jochi (the analyst agent) now has automated testing capabilities that:

1. **Periodically execute** the Kurultai testing framework
2. **Analyze results** and categorize findings by severity
3. **Auto-remediate** simple issues (threshold constants, configuration)
4. **Create tickets** for issues requiring human intervention
5. **Send alerts** via Signal for critical failures

---

## Quick Start

### 1. Test the Orchestrator Manually

```bash
# Dry run (no files saved, no actions taken)
python tools/kurultai/test_runner_orchestrator.py --dry-run

# Run all phases
python tools/kurultai/test_runner_orchestrator.py

# Run specific phase
python tools/kurultai/test_runner_orchestrator.py --phase integration

# Run with custom output directory
python tools/kurultai/test_runner_orchestrator.py --output-dir /tmp/test_results
```

### 2. Railway Cron Configuration

Add to `railway.yml` under the moltbot service:

```yaml
services:
  - name: moltbot
    # ... existing config ...
    schedules:
      - name: jochi-smoke-tests
        cron: "*/15 * * * *"  # Every 15 minutes
        command: "python tools/kurultai/test_runner_orchestrator.py --phase fixtures --phase integration"
      - name: jochi-hourly-tests
        cron: "0 * * * *"  # Every hour
        command: "python tools/kurultai/test_runner_orchestrator.py"
      - name: jochi-nightly-tests
        cron: "0 2 * * *"  # 2 AM daily
        command: "python tools/kurultai/test_runner_orchestrator.py --phase all && python tools/kurultai/test_runner_orchestrator.py --phase performance"
```

### 3. Systemd Timer (Alternative)

Create `/etc/systemd/system/jochi-test.service`:

```ini
[Unit]
Description=Jochi Automated Test Runner
After=network.target neo4j.service openclaw.service

[Service]
Type=oneshot
User=kurultai
WorkingDirectory=/Users/kurultai/molt
Environment="PYTHONPATH=/Users/kurultai/molt"
ExecStart=/usr/bin/python3 tools/kurultai/test_runner_orchestrator.py
```

Create `/etc/systemd/system/jochi-test.timer`:

```ini
[Unit]
Description=Jochi Automated Test Timer
Requires=jochi-test.service

[Timer]
# Run every 15 minutes
OnBootSec=5min
OnUnitActiveSec=15min
# Accuracy within 1 minute to allow batching
AccuracySec=1min

[Install]
WantedBy=timers.target
```

Enable the timer:

```bash
sudo systemctl daemon-reload
sudo systemctl enable jochi-test.timer
sudo systemctl start jochi-test.timer

# Check status
sudo systemctl list-timers
sudo systemctl status jochi-test.timer
sudo journalctl -u jochi-test.service -f
```

### 4. Cron (Simple Alternative)

```bash
# Edit crontab
crontab -e

# Add these lines:
# Jochi automated tests - smoke every 15 minutes
*/15 * * * * cd /Users/kurultai/molt && /usr/bin/python3 tools/kurultai/test_runner_orchestrator.py --phase fixtures --phase integration >> /var/log/jochi-tests.log 2>&1

# Jochi automated tests - full hourly
0 * * * * cd /Users/kurultai/molt && /usr/bin/python3 tools/kurultai/test_runner_orchestrator.py >> /var/log/jochi-tests.log 2>&1

# Jochi automated tests - nightly comprehensive
0 2 * * * cd /Users/kurultai/molt && /usr/bin/python3 tools/kurultai/test_runner_orchestrator.py --phase all --phase performance >> /var/log/jochi-nightly.log 2>&1
```

---

## Jochi's Analysis Workflow

When tests run, Jochi follows this workflow:

```
┌─────────────────────────────────────────────────────────────────────┐
│  1. EXECUTE TESTS                                                  │
│     - Run pytest across configured phases                           │
│     - Capture pass/fail/status                                      │
│     - Record durations                                             │
├─────────────────────────────────────────────────────────────────────┤
│  2. ANALYZE RESULTS                                                │
│     - Calculate pass rates per phase                               │
│     - Identify failure patterns                                    │
│     - Categorize by severity (CRITICAL/HIGH/MEDIUM/LOW)            │
├─────────────────────────────────────────────────────────────────────┤
│  3. GENERATE FINDINGS                                               │
│     - Security failures → CRITICAL                                 │
│     - Concurrency issues (duplicates) → CRITICAL                   │
│     - Performance regression → HIGH                                 │
│     - Infrastructure failures → HIGH                                │
├─────────────────────────────────────────────────────────────────────┤
│  4. AUTO-REMEDIATE                                                  │
│     - Fix threshold constant mismatches                            │
│     - Create tickets for complex issues                            │
│     - Send Signal alerts for critical findings                     │
├─────────────────────────────────────────────────────────────────────┤
│  5. SAVE REPORT                                                     │
│     - JSON report for machine processing                           │
│     - TXT summary for human review                                 │
│     - Update trends for dashboard visualization                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Severity Levels & Actions

| Severity | Description | Example | Auto Action |
|----------|-------------|---------|-------------|
| **CRITICAL** | System down, data loss, security breach | Duplicate task claims, auth bypass | Create ticket + Signal alert |
| **HIGH** | Major functionality broken, >50% perf degradation | Agent unreachable, Neo4j down | Create ticket + alert |
| **MEDIUM** | Minor functionality broken, 10-50% perf degradation | Test timeout, config drift | Create ticket |
| **LOW** | Cosmetic issues, <10% perf degradation | Formatting inconsistency | Log only |
| **INFO** | Informational findings | Optimization opportunity | Log only |

---

## Report Locations

Test reports are saved to:

```
data/test_results/
├── test_report_20260207_020000.json    # Machine-readable
├── test_summary_20260207_020000.txt    # Human-readable
├── test_report_20260207_030000.json
├── test_summary_20260207_030000.txt
└── ...
```

Tickets are created at:

```
data/workspace/tickets/
├── TICKET-20260207143025.json        # Critical: race condition
├── TICKET-20260207143026.json        # High: performance degradation
└── ...
```

---

## Environment Variables

Configure these for full functionality:

```bash
# Project root (auto-detected if not set)
export PROJECT_ROOT=/Users/kurultai/molt

# Test results directory
export TEST_RESULTS_DIR=${PROJECT_ROOT}/data/test_results

# Alert settings
export SIGNAL_ALERT_NUMBER="+15551234567"  # For critical alerts
export SLACK_WEBHOOK_URL="https://hooks.slack.com/..."  # Optional

# Jochi agent settings
export JOCHI_AUTO_FIXES=true         # Enable auto-remediation
export JOCHI_MAX_FIXES=3             # Max auto-fixes per run
export JOCHI_DRY_RUN=false            # Set to true for testing
```

---

## Monitoring Jochi's Execution

### Check Recent Runs

```bash
# List recent test reports
ls -lt data/test_results/*.json | head -10

# View latest summary
cat data/test_results/test_summary_$(ls -t data/test_results/*.txt | head -1 | xargs basename -a)

# Check for tickets created today
find data/workspace/tickets/ -name "*.json" -mtime -1
```

### Signal Alert Format

When critical findings occur, Jochi sends a Signal message:

```
🚨 JOCHI TEST ALERT

Execution: 20260207-143025
Status: FAILED (3 critical findings)

[C] Race condition: duplicate task claims detected
   Phase: concurrent
   Test: test_ten_agents_hundred_tasks_no_duplicate_claims

[C] Security test failed: sql_injection_prevention
   Phase: integration
   Test: test_sql_injection_sanitization

[H] Agent heartbeat stale - possible failure
   Phase: integration
   Test: test_infra_heartbeat_sidecar_writes_every_30s

Actions: 3 tickets created
Report: data/test_results/test_report_20260207_143025.json
```

---

## Integration with Existing Agents

Jochi's test automation integrates with the 6-agent system:

### Kublai (Orchestrator)
- Receives test failure notifications
- Can pause delegation if system is unhealthy
- Routes critical issues to appropriate specialists

### Möngke (Researcher)
- Investigates failure patterns
- Researches root causes of complex issues
- Provides context for remediation decisions

### Temüjin (Developer)
- Receives security-related tickets
- Implements fixes for critical bugs
- Reviews code changes before hotfix deployment

### Chagatai (Writer)
- Documents test findings
- Creates runbooks for common issues
- Updates test documentation based on discoveries

### Jochi (Analyst) - Self
- Orchestrates test execution
- Analyzes results and generates findings
- Coordinates remediation efforts

### Ögedei (Operations)
- Receives infrastructure-related tickets
- Restarts failed services
- Implements configuration fixes

---

## Troubleshooting

### Tests Hang/Timeout

```bash
# Check if services are running
curl -f http://localhost:18789/health  # OpenClaw gateway
echo "MATCH (n) RETURN count(n)" | cypher-shell  # Neo4j

# Check for orphaned processes
ps aux | grep pytest
ps aux | grep test_runner
```

### High False Positive Rate

Adjust severity thresholds in `test_schedule_config.json5`:

```json
{
  "thresholds": {
    "pass_rate": {
      "critical": 40,  // Lowered from 50
      "high": 70,      // Lowered from 80
      "warning": 90    // Lowered from 95
    }
  }
}
```

### Missing Alerts

Verify Signal integration:

```bash
# Check Signal number is configured
echo $SIGNAL_ALERT_NUMBER

# Test Signal sending (via OpenClaw)
curl -X POST http://localhost:18789/api/signal \
  -H "Content-Type: application/json" \
  -d '{"message":"Test alert from Jochi","number":"<YOUR_NUMBER>"}'
```

---

## Advanced Configuration

### Custom Test Phases

Create custom phase combinations in `tools/kurultai/test_runner_orchestrator.py`:

```python
# Add to Phase enum
Phase.SECURITY_ONLY = "phase_security"

# Configure in phase_configs
Phase.SECURITY_ONLY = {
    "name": "Security Tests Only",
    "path": "tests/security/",
    "type": "pytest"
}
```

### Custom Remediation Actions

Extend `RemediationOrchestrator` class:

```python
def _fix_custom_issue(self, finding: Finding) -> Optional[Dict]:
    """Custom remediation for specific issue types."""
    if "template" in finding.title.lower():
        # Fix template configuration
        return self._update_template_config(finding)
    return None
```

---

## Summary

Jochi's automated testing provides:

- ✅ **Continuous monitoring** - Tests run every 15 minutes (smoke) / hour (full)
- ✅ **Intelligent analysis** - Findings categorized by severity and type
- ✅ **Auto-remediation** - Simple fixes applied automatically
- ✅ **Ticket creation** - Complex issues tracked for human resolution
- ✅ **Alerting** - Critical findings sent via Signal
- ✅ **Historical tracking** - Reports retained for 30 days with trend analysis

The system is designed to be:
- **Low maintenance** - Runs automatically with minimal oversight
- **Fast** - Smoke tests complete in < 5 minutes
- **Actionable** - Every finding includes remediation guidance
- **Integrated** - Works with all 6 agents in the Kurultai system
