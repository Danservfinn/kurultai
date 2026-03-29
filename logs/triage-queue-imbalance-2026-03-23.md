# Queue Imbalance Investigation — 2026-03-23 13:26

## Summary
**FALSE POSITIVE** — The QUEUE_IMBALANCE anomaly triggered because mongke and tolui are idle, but this is intentional.

## Root Cause
The DOMAIN_AGENT_COMPATIBILITY matrix in `scripts/task_domain.py` excludes mongke and tolui from most task domains:

| Agent | Can Handle |
|-------|------------|
| mongke | research, documentation, analysis, autoresearch |
| tolui | **Nothing** (uses ollama executor, not dispatch-capable) |
| chagatai | documentation, strategy, autoresearch |
| temujin | implementation, ops, strategy, completion, escalation |
| jochi | implementation, ops, analysis, completion, escalation, research, autoresearch |
| ogedei | implementation, ops, strategy, completion, escalation, analysis |

## Current Queue State
- temujin: 3 tasks (implementation/ops domain)
- jochi: 3 tasks (analysis/completion domain)
- ogedei: 3 tasks (ops/escalation domain)
- chagatai: 1 task
- mongke: 0 tasks (waiting for research/documentation tasks)
- tolui: 0 tasks (not dispatch-capable)

## Why Redistribution Won't Work
- `task-redistribute.py --dry-run` shows **0 tasks would be moved**
- Tasks in overloaded queues don't have explicit `domain:` frontmatter
- Fallback to keyword matching still restricts to domain-compatible agents
- mongke/tolui cannot handle implementation, ops, completion, or escalation tasks

## Resolution
1. ✅ Cleared `logs/throughput-anomaly-state.json` (false positive)
2. Recommendation: Add domain frontmatter to tasks at intake for better redistribution
3. Recommendation: Update anomaly detector to consider domain compatibility before escalating

## Action Taken
- Cleared anomaly state at 2026-03-23 13:30
- No task redistribution needed (system working as designed)
