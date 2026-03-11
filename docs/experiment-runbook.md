# Experiment System Runbook

Operational procedures for handling experiment system failures and alerts.

**Last updated:** 2026-03-08
**Implementation status:** FULLY OPERATIONAL

---

## Quick Reference

| Tool | Path | Purpose |
|------|------|---------|
| Health Monitor | `scripts/experiment_health_monitor.py` | System health checks |
| Experiment Manager | `scripts/experiment_manager.py` | Create/list/cleanup experiments |
| Experiment Pool | `scripts/experiment-pool.py` | Concurrent experiment daemon |
| Pool Status | `scripts/experiment-pool-status.py` | Query pool metrics |
| Lock Manager | `scripts/experiment_lock.py` | File-level locking |
| Ledger | `experiments/experiment-ledger.tsv` | Experiment records |
| Lock Dir | `/tmp/kurultai-experiment-locks/` | Active lock files |

---

## Alert Response Matrix

| Alert | Severity | Response Time | Primary Action |
|-------|----------|---------------|----------------|
| 3+ Consecutive Crashes | HIGH | 15 minutes | Investigate agent health |
| Merge Rate < 10% | MEDIUM | 1 hour | Review hypothesis quality |
| Bad Merge to Production | CRITICAL | 5 minutes | Emergency rollback |
| High Cost Alert ($5+/hr) | MEDIUM | 30 minutes | Throttle experiments |
| Stale Experiments (>2h) | MEDIUM | 30 minutes | Check for deadlocks |
| High Active Count (>5) | MEDIUM | 30 minutes | Review pool capacity |

---

## Alert: 3+ Consecutive Crashes

**Symptom**: Experiments repeatedly crash without completing

### Investigation Steps

1. **Check health monitor for crash sequence**
   ```bash
   cd ~/.openclaw/agents/main
   python3 scripts/experiment_health_monitor.py
   ```

2. **Check agent logs**
   ```bash
   tail -100 ~/.openclaw/agents/<agent>/memory/session.log
   tail -100 ~/.openclaw/agents/main/logs/experiment-pool.log
   ```

3. **Check for OOM (Out of Memory)**
   ```bash
   # On macOS
   log show --predicate 'eventMessage contains "memor"' --last 1h

   # Check memory usage
   ps aux | grep -E "(python|claude)" | head -20
   ```

4. **Check lock files**
   ```bash
   python3 scripts/experiment_lock.py list
   ```

### Resolution

| Root Cause | Action |
|------------|--------|
| Stale lock | `python3 scripts/experiment_lock.py clear` |
| Resource issue | Reduce pool size, see "Throttle Experiments" |
| Code bug in experiment | Fix manually, pause experiments for that agent |
| Agent health issue | Restart agent session |

### Pause/Resume Experiments

```bash
# Pause experiment pool (stops accepting new experiments)
touch ~/.openclaw/agents/main/.experiment-pool/.pause

# Resume experiments
rm ~/.openclaw/agents/main/.experiment-pool/.pause

# Kill stuck pool daemon
pkill -f experiment-pool.py
```

---

## Alert: Merge Rate < 10%

**Symptom**: Most experiments are being discarded instead of merged

### Investigation Steps

1. **Check health monitor output**
   ```bash
   cd ~/.openclaw/agents/main
   python3 scripts/experiment_health_monitor.py
   ```

2. **Review recent experiments in ledger**
   ```bash
   # Show discarded experiments
   cat ~/.openclaw/experiments/experiment-ledger.tsv | grep -E "discarded|crashed" | tail -10

   # Show merged experiments
   cat ~/.openclaw/experiments/experiment-ledger.tsv | grep merged | tail -10
   ```

3. **Check experiment details**
   ```bash
   python3 scripts/experiment_manager.py status --experiment-id exp-20260308-001
   ```

### Resolution

| Issue | Action |
|-------|--------|
| Poor hypothesis quality | Review hypothesis generation prompts |
| Incorrect baseline | Recalibrate baseline metrics |
| Too aggressive changes | Reduce improvement threshold |

### Adjust Thresholds

Edit the evaluation logic in your experiment executor:

```python
# Current thresholds (default)
IMPROVEMENT_THRESHOLD_PCT = 5.0     # Merge if improvement > 5%
REGRESSION_THRESHOLD_PCT = 5.0      # Discard if regression > 5%
MIN_EXPERIMENT_DURATION_S = 300     # Minimum 5 minutes
```

---

## Alert: Bad Merge to Production

**CRITICAL** — Immediate action required

### Immediate Action

```bash
# View recent experiments to identify problematic merge
cd ~/.openclaw/agents/main
python3 scripts/experiment_manager.py list

# Rollback specific commit (manual procedure)
cd ~/.openclaw
git revert --no-commit <bad-commit-hash>
git commit -m "EMERGENCY ROLLBACK: Reverts <bad-commit-hash>"

# Delete experiment branch
git branch -D experiment/<agent>/<exp-id>/<slug>
```

### Verification Steps

1. **Confirm rollback executed**
   ```bash
   git log -1 --oneline
   ```

2. **Check experiment status**
   ```bash
   python3 scripts/experiment_health_monitor.py
   ```

3. **Verify experiment marked in ledger**
   ```bash
   grep <exp-id> ~/.openclaw/experiments/experiment-ledger.tsv
   ```

### Post-Incident

1. **Document incident** in `logs/experiment-incidents.log`
2. **Review experiment that caused issue**
   ```bash
   cat ~/.openclaw/experiments/experiment-ledger.tsv | grep <exp-id>
   ```

---

## Alert: High Cost Alert ($5+/hr)

**Symptom**: Experiment costs exceeding budget threshold

### Investigation Steps

1. **Check active experiments**
   ```bash
   cd ~/.openclaw/agents/main
   python3 scripts/experiment_health_monitor.py
   ```

2. **Check pool status**
   ```bash
   python3 scripts/experiment-pool-status.py --json
   ```

3. **Identify expensive experiments**
   ```bash
   # Sort ledger by cost (column 5)
   sort -t$'\t' -k5 -rn ~/.openclaw/experiments/experiment-ledger.tsv | head -10
   ```

### Resolution

| Issue | Action |
|-------|--------|
| Runaway experiment | Kill experiment, release lock |
| Too many concurrent experiments | Reduce MAX_CONCURRENT in pool config |
| Expensive model calls | Add cost limits to experiment config |

### Throttle Experiments

```bash
# Kill pool daemon (stops all new experiments)
pkill -f experiment-pool.py

# Restart with reduced capacity
cd ~/.openclaw/agents/main
# Edit MAX_CONCURRENT in scripts/experiment-pool.py before restarting
python3 scripts/experiment-pool.py &
```

---

## Alert: Stale Experiments (>2h)

**Symptom**: Experiments stuck in "running" state for extended time

### Investigation Steps

1. **Check health monitor for stale experiments**
   ```bash
   cd ~/.openclaw/agents/main
   python3 scripts/experiment_health_monitor.py
   ```

2. **Check lock files**
   ```bash
   python3 scripts/experiment_lock.py list
   ls -la /tmp/kurultai-experiment-locks/
   ```

3. **Check pool state**
   ```bash
   cat ~/.openclaw/agents/main/.experiment-pool/state.json
   ```

### Resolution

| Issue | Action |
|-------|--------|
| Dead lock | `python3 scripts/experiment_lock.py clear` |
| Agent crashed | Restart agent |
| Pool daemon crashed | Restart `experiment-pool.py` |

### Force Release Locks

```bash
# Clear all stale locks
cd ~/.openclaw/agents/main
python3 scripts/experiment_lock.py clear

# Release specific lock manually
rm /tmp/kurultai-experiment-locks/<agent>.lock

# Kill stuck experiment process
pkill -f "experiment.*<experiment-id>"
```

---

## Manual Procedures

### Create Experiment

```bash
cd ~/.openclaw/agents/main
python3 scripts/experiment_manager.py create \
  --agent temujin \
  --hypothesis "Test router scorer learning rate adjustment" \
  --files scripts/router_scorer.py \
  --timeout 600
```

### List Active Experiments

```bash
# All active experiments
python3 scripts/experiment_manager.py list

# Agent-specific
python3 scripts/experiment_manager.py list --agent temujin

# Via pool status
python3 scripts/experiment-pool-status.py --json
```

### Get Experiment Status

```bash
python3 scripts/experiment_manager.py status \
  --experiment-id exp-20260308-001
```

### Cleanup Experiment

```bash
python3 scripts/experiment_manager.py cleanup \
  --experiment-id exp-20260308-001
```

### Check Lock Status

```bash
# List all active locks
python3 scripts/experiment_lock.py list

# Check if specific path is locked
python3 scripts/experiment_lock.py check --path scripts/router_scorer.py

# Clear stale locks
python3 scripts/experiment_lock.py clear
```

### Git Branch Operations

```bash
# List all experiment branches
cd ~/.openclaw
git branch --list "experiment/*"

# Checkout specific experiment branch
git checkout experiment/temujin/exp-20260308-001/router-scorer-lr-tuning

# Delete experiment branch (cleanup)
git branch -D experiment/temujin/exp-20260308-001/router-scorer-lr-tuning
```

---

## Health Check Commands

### Quick Health Check

```bash
cd ~/.openclaw/agents/main
python3 scripts/experiment_health_monitor.py
```

**Expected output:**
```
EXPERIMENT HEALTH CHECK - 2026-03-08 14:30

SUMMARY
-------
Active experiments:   2
Merge rate (24h):     28.5%
Consecutive crashes:  0
Cost per hour:        $0.00

STATUS
------
✓ No stale experiments
✓ Merge rate healthy
✓ No crash sequences
✓ Cost within budget
```

### Detailed Status

```bash
# Verbose output
python3 scripts/experiment_health_monitor.py

# JSON output (for logging)
python3 scripts/experiment_health_monitor.py --json

# Pool status
python3 scripts/experiment-pool-status.py --json
```

### Component Checks

```bash
# Check ledger file
tail -5 ~/.openclaw/experiments/experiment-ledger.tsv

# Check lock directory
ls -la /tmp/kurultai-experiment-locks/

# Check pool state
cat ~/.openclaw/agents/main/.experiment-pool/state.json

# Check pool logs
tail -50 ~/.openclaw/agents/main/logs/experiment-pool.log
```

### Cron Job Status

```bash
# Check if health monitor is in cron
cat ~/.openclaw/cron/jobs.json | grep experiment_health_monitor

# View cron logs
tail -50 ~/.openclaw/logs/cron.log
```

---

## Real Troubleshooting Scenarios

### Scenario 1: "Pending experiment never starts"

**Symptoms:**
- Experiment shows status "pending" for > 10 minutes
- No errors in logs

**Diagnosis:**
```bash
# Check if pool is running
ps aux | grep experiment-pool

# Check queue
cat ~/.openclaw/agents/main/.experiment-pool/queue.json

# Check for file conflicts
python3 scripts/experiment_lock.py list
```

**Resolution:**
- If pool not running: `python3 scripts/experiment-pool.py &`
- If file conflict: Wait for conflicting experiment to complete
- If queue full: Check MAX_CONCURRENT limit

### Scenario 2: "Experiment marked 'crashed' but code looks fine"

**Symptoms:**
- Experiment status: "crashed"
- No obvious code issues

**Diagnosis:**
```bash
# Check experiment details
python3 scripts/experiment_manager.py status --experiment-id <exp-id>

# Check pool logs
tail -100 ~/.openclaw/agents/main/logs/experiment-pool.log
```

**Resolution:**
- Common cause: Timeout exceeded (default 300s)
- Check EXPERIMENT_TIMEOUT in `experiment-pool.py`
- Increase timeout if needed

### Scenario 3: "Stale lock blocking new experiments"

**Symptoms:**
- New experiments can't start
- Lock file exists but process is dead

**Diagnosis:**
```bash
# List locks with PIDs
python3 scripts/experiment_lock.py list

# Check if PID is alive
ps -p <pid>
```

**Resolution:**
```bash
# Clear all stale locks
python3 scripts/experiment_lock.py clear

# Or manually remove specific lock
rm /tmp/kurultai-experiment-locks/<agent>.lock
```

### Scenario 4: "Merge rate suddenly dropped to 0%"

**Symptoms:**
- Recent experiments all discarded
- No successful merges

**Diagnosis:**
```bash
# Review recent discards
grep discarded ~/.openclaw/experiments/experiment-ledger.tsv | tail -10

# Check baseline metrics
python3 scripts/experiment_manager.py status --experiment-id <exp-id>
```

**Resolution:**
- Common cause: Baseline metric shifted significantly
- Common cause: Threshold too aggressive
- Review and adjust thresholds in evaluation code

---

## Escalation Path

| Severity | First Response | Escalate To |
|----------|---------------|-------------|
| CRITICAL | On-call operator | Kublai (human) immediately |
| HIGH | Automated response | On-call if not resolved in 15 min |
| MEDIUM | Queue for review | Next business day |

### Contact Information

- **Signal**: +15165643945 (automated alerts + manual contact)
- **Logs**: `~/.openclaw/agents/main/logs/`
- **Experiment ledger**: `~/.openclaw/experiments/experiment-ledger.tsv`

---

## Runbook Maintenance

This runbook should be updated:
- After each incident (add learnings)
- When new alert types are added
- After any architecture changes
- Quarterly review for accuracy

### Changelog

| Date | Changes |
|------|---------|
| 2026-03-08 | Updated with actual implementation details, verified commands, real troubleshooting scenarios |

---

## Appendix: File Locations

```
~/.openclaw/
├── agents/main/
│   ├── scripts/
│   │   ├── experiment_health_monitor.py    # Health checks
│   │   ├── experiment_manager.py           # CRUD operations
│   │   ├── experiment-pool.py              # Pool daemon
│   │   ├── experiment-pool-status.py       # Status queries
│   │   └── experiment_lock.py              # Lock management
│   ├── .experiment-pool/                   # Pool state
│   │   ├── queue.json
│   │   ├── state.json
│   │   └── .pause                          # Stop flag
│   └── logs/
│       └── experiment-pool.log
├── experiments/
│   ├── experiment-ledger.tsv               # Master ledger
│   └── *.yaml                              # Queued experiments
└── /tmp/kurultai-experiment-locks/         # Lock files
    ├── temujin.lock
    ├── mongke.lock
    └── ...
```
