# Experiment System Runbook

Operational procedures for handling experiment system failures and alerts.

---

## Alert Response Matrix

| Alert | Severity | Response Time | Primary Action |
|-------|----------|---------------|----------------|
| 3+ Consecutive Crashes | HIGH | 15 minutes | Investigate agent health |
| Merge Rate < 10% | MEDIUM | 1 hour | Review hypothesis quality |
| Bad Merge to Production | CRITICAL | 5 minutes | Emergency rollback |
| High Cost Alert ($5+/hr) | MEDIUM | 30 minutes | Throttle experiments |
| Stale Experiments (>2h) | MEDIUM | 30 minutes | Check for deadlocks |

---

## Alert: 3+ Consecutive Crashes

**Symptom**: Experiments repeatedly crash without completing

### Investigation Steps

1. **Check agent logs**
   ```bash
   tail -100 ~/.openclaw/agents/<agent>/memory/session.log
   ```

2. **Check for OOM (Out of Memory)**
   ```bash
   dmesg | grep -i oom
   # Or on macOS
   log show --predicate 'eventMessage contains "memor"' --last 1h
   ```

3. **Verify dependencies**
   ```bash
   pip install -r requirements.txt --dry-run
   ```

4. **Check resource limits**
   ```bash
   # Current memory usage
   ps aux | grep -E "(python|claude)" | head -20

   # Available disk space
   df -h ~/.openclaw
   ```

### Resolution

| Root Cause | Action |
|------------|--------|
| Dependency issue | Fix requirements.txt, retry experiment |
| Resource issue | Reduce experiment batch size, add memory |
| Code bug in experiment | Fix manually, pause experiments for that agent |
| Agent health issue | Restart agent session |

### Pause/Resume Experiments

```bash
# Pause all experiments
touch ~/.openclaw/experiments/.pause

# Resume experiments
rm ~/.openclaw/experiments/.pause

# Pause specific agent
touch ~/.openclaw/agents/<agent>/.pause-experiments
```

---

## Alert: Merge Rate < 10%

**Symptom**: Most experiments are being discarded instead of merged

### Investigation Steps

1. **Review recent experiments**
   ```bash
   python3 scripts/experiment_dashboard.py --today | grep -A10 "FAILED\|DISCARDED"
   ```

2. **Check hypothesis quality**
   ```bash
   # Review hypothesis descriptions in ledger
   cat ~/.openclaw/experiments/ledger.tsv | grep discard | tail -10
   ```

3. **Verify baseline metrics**
   ```bash
   # Check current baseline in Neo4j
   python3 -c "
   from neo4j import GraphDatabase
   driver = GraphDatabase.driver('bolt://localhost:7687')
   with driver.session() as s:
       result = s.run('MATCH (b:BaselineMetric) RETURN b')
       for r in result:
           print(r)
   "
   ```

4. **Review successful experiments**
   ```bash
   # What's working?
   cat ~/.openclaw/experiments/ledger.tsv | grep merge | tail -10
   ```

### Resolution

| Issue | Action |
|-------|--------|
| Poor hypothesis quality | Improve hypothesis generation prompt |
| Incorrect baseline | Recalibrate baseline metrics |
| Too aggressive changes | Reduce change magnitude thresholds |
| Metric miscalculation | Debug metric collection code |

### Adjust Thresholds

Edit `~/.openclaw/config/experiment_thresholds.yaml`:

```yaml
improvement_threshold_pct: 5.0    # Lower to accept smaller improvements
regression_threshold_pct: 5.0     # Higher to tolerate more regression
min_experiment_duration_s: 300    # Longer experiments for more data
```

---

## Alert: Bad Merge to Production

**CRITICAL** — Immediate action required

### Immediate Action

```bash
# Emergency rollback to known-good commit
python3 scripts/rollback_manager.py --emergency --commit <bad-commit-hash>

# Or manual rollback
cd ~/.openclaw
git revert --no-commit <bad-commit-hash>
git commit -m "EMERGENCY ROLLBACK: Reverts <bad-commit-hash>"
git push origin main --force-with-lease
```

### Verification Steps

1. **Confirm rollback executed**
   ```bash
   git log -1 --oneline
   # Should show rollback commit
   ```

2. **Check error rate normalized**
   ```bash
   # Monitor task error rate
   python3 scripts/monitor_error_rate.py --watch
   ```

3. **Verify rollback logged to Neo4j**
   ```cypher
   MATCH (r:RollbackEvent)
   WHERE r.timestamp > datetime() - duration('PT1H')
   RETURN r
   ORDER BY r.timestamp DESC
   LIMIT 5
   ```

4. **Confirm Signal alert sent**
   - Check Signal message received at +15165643945
   - Alert should contain commit hash and reason

### Post-Incident

1. **Document incident** within 24 hours
   - Root cause
   - Time to detect (TTD)
   - Time to resolve (TTR)
   - Prevention measures

2. **Review experiment that caused issue**
   ```bash
   cat ~/.openclaw/experiments/ledger.tsv | grep <exp-id>
   ```

3. **Consider adding human approval gate** for similar changes

---

## Alert: High Cost Alert ($5+/hr)

**Symptom**: Experiment costs exceeding budget threshold

### Investigation Steps

1. **Check active experiments**
   ```bash
   python3 scripts/experiment_dashboard.py --today | grep -A5 "ACTIVE"
   ```

2. **Identify expensive experiments**
   ```bash
   # Sort ledger by cost
   cat ~/.openclaw/experiments/ledger.tsv | sort -t$'\t' -k6 -rn | head -10
   ```

3. **Check for runaway experiments**
   ```bash
   # Experiments running > 1 hour
   python3 -c "
   import time
   from pathlib import Path
   for lock in Path('/tmp').glob('kurultai-exp-*.lock'):
       import json
       with open(lock) as f:
           data = json.load(f)
       age_hours = (time.time() - data['acquired_at']) / 3600
       if age_hours > 1:
           print(f'{lock}: {age_hours:.1f} hours old')
   "
   ```

### Resolution

| Issue | Action |
|-------|--------|
| Runaway experiment | Kill and release lock |
| Too many concurrent experiments | Reduce max_concurrent in config |
| Expensive model calls | Add cost limits to experiment config |

### Throttle Experiments

```bash
# Reduce concurrent experiments
echo '{"max_concurrent": 2}' > ~/.openclaw/config/experiment_throttle.json

# Or pause non-critical experiments
touch ~/.openclaw/experiments/.pause-low-priority
```

---

## Alert: Stale Experiments (>2h)

**Symptom**: Experiments stuck in "running" state for extended time

### Investigation Steps

1. **List stale experiments**
   ```bash
   python3 scripts/experiment_health_monitor.py | grep -A10 "stale"
   ```

2. **Check lock files**
   ```bash
   ls -la /tmp/kurultai-exp-*.lock
   ```

3. **Check agent process status**
   ```bash
   ps aux | grep claude
   ```

### Resolution

| Issue | Action |
|-------|--------|
| Dead lock | Release lock manually |
| Agent crashed | Restart agent |
| Network timeout | Check connectivity, retry |

### Force Release Locks

```bash
# Release specific lock
rm /tmp/kurultai-exp-<experiment-id>.lock

# Release all locks (nuclear option)
rm /tmp/kurultai-exp-*.lock

# Kill stuck experiment process
pkill -f "experiment.*<experiment-id>"
```

---

## Manual Procedures

### Manually Trigger Rollback

```bash
# Rollback specific commit
python3 scripts/rollback_manager.py --commit <commit-hash> --reason "Manual rollback: <reason>"

# Rollback last N commits
python3 scripts/rollback_manager.py --last-n 2 --reason "Manual rollback: batch revert"
```

### Manually Approve/Discard Experiment

```bash
# Force merge (override decision engine)
python3 scripts/experiment_manager.py --approve <experiment-id> --force

# Force discard
python3 scripts/experiment_manager.py --discard <experiment-id> --reason "Manual override"
```

### Reset Experiment System

```bash
# Full reset (CAUTION: clears all state)
python3 scripts/reset_experiment_system.py --confirm

# Soft reset (keeps ledger, clears active experiments)
python3 scripts/reset_experiment_system.py --soft
```

---

## Health Check Commands

### Quick Health Check

```bash
# All-in-one health check
python3 scripts/experiment_health_monitor.py --quick
```

Expected output:
```
✓ Merge rate (24h): 28.5%
✓ No stale experiments
✓ No consecutive crashes
✓ Cost within budget
✓ All locks valid
```

### Detailed Status

```bash
# Full system status
python3 scripts/experiment_health_monitor.py --verbose
```

### Component Checks

```bash
# Check Neo4j connectivity
python3 -c "from neo4j import GraphDatabase; d=GraphDatabase.driver('bolt://localhost:7687'); print('OK')"

# Check git repository status
cd ~/.openclaw && git status

# Check lock directory
ls -la /tmp/kurultai-exp-*.lock 2>/dev/null || echo "No active locks"

# Check experiment ledger
tail -5 ~/.openclaw/experiments/ledger.tsv
```

---

## Escalation Path

| Severity | First Response | Escalate To |
|----------|---------------|-------------|
| CRITICAL | On-call operator | Kublai (human) immediately |
| HIGH | Automated response | On-call if not resolved in 15 min |
| MEDIUM | Queue for review | Next business day |

### Contact Information

- **Signal**: +15165643945 (automated alerts + manual contact)
- **GitHub Issues**: github.com/kurultai/kurultai/issues

---

## Runbook Maintenance

This runbook should be updated:
- After each incident (add learnings)
- When new alert types are added
- Quarterly review for accuracy

Last updated: 2026-03-08
