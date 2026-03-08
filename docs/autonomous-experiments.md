# Kurultai Autonomous Experiments

## Overview

Kurultai can run 100+ experiments overnight with automatic merge/rollback. This system enables continuous improvement of the multi-agent platform through:

- **Autonomous hypothesis generation** — Agents propose experiments based on observed metrics
- **Automatic branching** — Each experiment runs in isolation on its own git branch
- **Metric-driven decisions** — Merge on improvement, discard on regression
- **Instant rollback** — Production safety with sub-5-second rollback capability
- **Concurrent execution** — Multiple experiments on different files run in parallel

---

## Quick Start

### 1. Generate a Hypothesis

Express your hypothesis in natural language:

```
"I think increasing the router scorer learning rate will improve task routing quality"
```

Or let an agent generate hypotheses automatically based on observed performance metrics.

### 2. Create an Experiment

Programmatically create an experiment:

```python
from experiment_manager import ExperimentManager

em = ExperimentManager()

experiment = em.create_experiment(
    agent="temujin",
    hypothesis="Increase router scorer learning rate from 0.001 to 0.01",
    target_files=["scripts/router_scorer.py"],
    timeout=600  # 10 minute budget
)

print(f"Created: {experiment['experiment_id']}")
print(f"Branch: {experiment['branch']}")
```

### 3. Experiment Runs Automatically

The experiment system:
1. Creates an isolated branch
2. Applies the proposed changes
3. Runs for the specified duration
4. Collects quality, duration, and cost metrics
5. Compares against baseline

### 4. Check Results

View today's experiments:

```bash
python3 scripts/experiment_dashboard.py --today
```

Output:

```
================================================================================
                    KURLTAI EXPERIMENT DASHBOARD - 2026-03-08
================================================================================

SUMMARY
-------
Total Experiments:    47
Merged:              12 (25.5%)
Discarded:           33 (70.2%)
Crashed:              2 (4.3%)
Avg Improvement:    +3.2% (merged experiments)
Total Cost:         $18.47

RECENT MERGES
-------------
exp-20260308-047  temujin  +8.3% quality via LR tuning           5m 12s
exp-20260308-045  ogedei   -9% duration via batch size           4m 45s

ACTIVE EXPERIMENTS
------------------
exp-20260308-048  temujin  Testing attention layer               Running 3m 22s
```

---

## How It Works

### Branch Strategy

Each experiment creates a branch with the naming convention:

```
experiment/<agent>/<experiment-id>/<hypothesis-slug>

Examples:
  experiment/temujin/exp-20260308-001/ab-test-opt-params
  experiment/ogedei/exp-20260308-002/cron-backoff-tuning
  experiment/kublai/exp-20260308-003/router-scorer-v2
```

### Decision Criteria

Experiments are automatically:

| Outcome | Criteria | Action |
|---------|----------|--------|
| **MERGE** | Quality improvement > 5% OR Duration reduction > 10% | Branch merged to main |
| **DISCARD** | Quality regression > 5% OR Error rate > 2x baseline | Branch deleted |
| **CRASH** | Experiment fails or times out | Logged for analysis |

### Rollback Triggers

After merge, the system monitors for:

- Quality drop > 5% from baseline → **Immediate rollback**
- Error rate > 2x baseline → **Immediate rollback**
- Duration spike > 50% → **Immediate rollback**

Rollback completes in < 5 seconds with automatic Signal alert.

---

## Safety

### Canary Deployments

Code changes follow a canary deployment pattern:

1. Merge to staging
2. Route 5% of traffic to new code
3. Monitor for 10 minutes
4. If stable, scale to 100%
5. If errors > 2x baseline, auto-rollback

### Human Approval Gates

Some changes require human approval before merge:

| Change Type | Auto-Merge | Human Approval |
|-------------|------------|----------------|
| Config tuning (hyperparams) | Yes | - |
| New utility function | Yes | - |
| API signature change | - | Required |
| Database schema change | - | Required |
| Security-sensitive code | - | Required + 2 approvers |
| Cron job changes | - | Required |

### Protected Branches

The following branches are **never** auto-merged to:
- `main` (production)
- `prod/*`
- `release/*`

---

## Monitoring

### Dashboard

View experiment status:

```bash
# Today's experiments
python3 scripts/experiment_dashboard.py --today

# Specific date
python3 scripts/experiment_dashboard.py --date 2026-03-07

# Last 7 days summary
python3 scripts/experiment_dashboard.py --week
```

### Health Monitoring

Check system health:

```bash
python3 scripts/experiment_health_monitor.py
```

This reports:
- Merge rate (alert if < 10%)
- Stale experiments (stuck > 2 hours)
- Post-merge error rates

### Experiment Ledger

All experiments are logged to:

```bash
cat ~/.openclaw/experiments/ledger.tsv
```

Format:

```
experiment_id	agent	commit	val_quality	duration_s	cost_usd	status	description
exp-20260308-001	temujin	a1b2c3d	0.7800	312	0.47	merge	+8.3% quality via LR tuning
exp-20260308-002	ogedei	b2c3d4e	0.7500	285	0.41	merge	-9% duration via batch size
exp-20260308-003	kublai	c3d4e5f	0.7100	301	0.39	discard	-1.4% quality, discarded
```

---

## Troubleshooting

### Experiment Stuck?

Check for stale locks:

```bash
# List all experiment locks
ls /tmp/kurultai-exp-*.lock

# Release a specific lock (emergency only)
rm /tmp/kurultai-exp-temujin.lock
```

### Too Many Crashes?

Pause all experiments:

```bash
# Create pause flag
touch ~/.openclaw/experiments/.pause

# Resume when ready
rm ~/.openclaw/experiments/.pause
```

### Low Merge Rate?

If merge rate drops below 10%:
1. Check hypothesis quality — are agents proposing reasonable experiments?
2. Check metric calculation — is baseline correct?
3. Review recent merged experiments — what patterns work?

### View Detailed Logs

```bash
# Agent-specific logs
tail -100 ~/.openclaw/agents/<agent>/memory/session.log

# Experiment orchestrator logs
tail -100 ~/.openclaw/logs/experiment_orchestrator.log
```

---

## API Reference

### ExperimentManager

```python
from experiment_manager import ExperimentManager

em = ExperimentManager()

# Create experiment
exp = em.create_experiment(
    agent="temujin",
    hypothesis="Description of hypothesis",
    target_files=["path/to/file.py"],
    timeout=600  # seconds
)

# Start experiment
em.start_experiment(exp["experiment_id"])

# Complete with metrics
em.complete_experiment(
    exp["experiment_id"],
    metrics={
        "quality_score_result": 0.78,
        "error_rate_result": 0.04
    },
    decision="merged"  # or "discarded", "crashed"
)

# Cleanup
em.cleanup_experiment(exp["experiment_id"])
```

### RollbackManager

```python
from rollback_manager import RollbackManager

rm = RollbackManager(baseline_metrics={
    "quality": 0.72,
    "error_rate": 0.05,
    "duration": 300
})

# Check if rollback needed
needs_rollback, reason = rm.check_rollback_needed({
    "quality": 0.65,
    "error_rate": 0.08
})

if needs_rollback:
    rm.execute_rollback(
        commit_hash="abc123",
        reason=reason
    )
```

### ExperimentLock

```python
from experiment_lock import ExperimentLock

# Acquire lock
lock = ExperimentLock(
    agent="temujin",
    target_paths=["scripts/router.py"],
    timeout=3600  # 1 hour max
)

if lock.acquire():
    # Run experiment
    # ...
    lock.release()
else:
    print("File is locked by another experiment")

# Or use context manager
with ExperimentLock("temujin", ["scripts/router.py"]) as lock:
    if lock.acquired_at:
        # Run experiment
        pass
```

---

## Best Practices

### Writing Good Hypotheses

A good hypothesis:
- Is specific and measurable
- Targets a single variable
- Has a clear success criterion

Examples:

```
✓ "Increasing batch_size from 10 to 20 will reduce average duration by 15%"
✓ "Adding caching to router_scorer will improve quality by 5%"
✗ "Make things faster"  (too vague)
✗ "Improve everything"  (no single variable)
```

### Choosing Target Files

- Prefer single-file experiments for faster iteration
- Multi-file experiments are allowed but increase conflict risk
- Avoid experiments on shared configuration files

### Setting Timeouts

| Experiment Type | Recommended Timeout |
|-----------------|---------------------|
| Config tuning | 5-10 minutes |
| Algorithm changes | 15-30 minutes |
| Infrastructure changes | 30-60 minutes |

### Interpreting Results

- **High discard rate**: Hypotheses may be too aggressive
- **Low improvement**: Baseline may already be optimal
- **Crashes**: Check for resource limits or syntax errors

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                    EXPERIMENT EXECUTION PIPELINE                         │
├────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. HYPOTHESIS GENERATION                                                │
│     └─> Agent analyzes metrics, identifies improvement area              │
│     └─> Creates experiment task file                                     │
│                                                                          │
│  2. BRANCH CREATION                                                      │
│     └─> experiment_manager.create_experiment_branch()                    │
│     └─> Validates no conflicts, acquires lock                           │
│                                                                          │
│  3. IMPLEMENTATION                                                       │
│     └─> Agent modifies target files                                      │
│     └─> Pre-commit hooks run validation                                  │
│                                                                          │
│  4. METRIC COLLECTION                                                    │
│     └─> Run experiment for time budget                                   │
│     └─> Collect quality, duration, cost, error_rate                     │
│                                                                          │
│  5. DECISION ENGINE                                                      │
│     └─> Compare metrics to baseline                                      │
│     └─> Determine merge/discard/crash                                    │
│                                                                          │
│  6. MERGE/ROLLBACK                                                       │
│     └─> MERGE: git merge to main, trigger canary                        │
│     └─> ROLLBACK: git revert, send alert                                 │
│                                                                          │
│  7. CLEANUP                                                              │
│     └─> Release lock, delete branch, archive logs                       │
│                                                                          │
└────────────────────────────────────────────────────────────────────────┘
```

---

## See Also

- [Experiment Runbook](experiment-runbook.md) — Operational procedures for failures
- [Architecture Guide](../ARCHITECTURE.md) — System architecture overview
- [Experiment Health Monitoring](../scripts/experiment_health_monitor.py) — Automated health checks
