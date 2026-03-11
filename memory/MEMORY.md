# Kublai Agent Memory - Main Project

## Recent Critical Issues (2026-03-08)

### Model Configuration Crisis
- **Issue:** GLM-5 model drift causing reflection failures
- **Impact:** Hourly reflections completely broken, 50% success rate
- **Root Cause:** settings.json ANTHROPIC_MODEL overriding config.json
- **Fix Applied:** Option 1 proposal for proactive configuration validation

### Fake Completion Bug
- **Issue:** Systemic fake completions in task execution pipeline
- **Impact:** Queue inflation, ledger reconciliation failures
- **Frequency:** Recurring every 2-3 hours
- **Fix Applied:** Option 3 proposal for root cause fix

### Queue Imbalance Crisis
- **Issue:** Ogedei accumulating 2125s old tasks
- **Impact:** System throughput degradation, poor load balancing
- **Root Cause:** Static thresholds not adapting to workload patterns
- **Fix Applied:** Option 2 proposal for predictive routing

## Routing System Improvements (2026-03-08)

### Current Load-Balancing Thresholds
- HIGH=3 (was 20), CRITICAL=8 (was 30), LOW=2 (was 5)
- Working correctly but overwhelmed by configuration drift

### Proposed Solutions
1. **Proactive Configuration Validation** - Priority 1
   - Real-time model validation with auto-correction
   - Prevents reflection failures before they happen
   - Self-healing system architecture

2. **Enhanced Queue Management** - Priority 2
   - Predictive routing using historical patterns
   - Dynamic thresholds adjusting for peak hours
   - Task type classification for accurate routing

3. **Fake Completion Root Cause Fix** - Priority 3
   - Atomic operations for task state changes
   - Race condition prevention in completion markers
   - Post-execution verification system

## Key Learnings

### Agent Communication
- Gateway-router shows sticky routing to Temujin regardless of queue depth
- Secondary agents (Ogedei, Chagatai) being starved
- Need audit of auto_dispatch.py queue_depth fallback logic

### System Stability
- 7 missed ticks in reporting window indicates systemic instability
- Queue audit system effectively identifying fake completions
- Ledger reconciliation shows -15 delta (Neo4j vs actual ledger)

## WHEN/THEN Rules

**Canonical registry:** `memory/when_then_rules.md` (7 active rules, R001-R007)
**Rule lifecycle docs:** `memory/rules_lifecycle.md`

> Do NOT define rules here. All rules live in the canonical registry above.

## Memory Maintenance

- **Pruning:** `scripts/memory_pruner.py` — consolidates daily files >3 days old into weekly summaries
- Run: `python3 scripts/memory_pruner.py [--dry-run]`
- Targets ~90% line reduction while preserving key learnings and rules

## Code Reference

### Key Files
- `scripts/task_intake.py` - Main routing logic
- `scripts/agent-task-handler.py` - Task execution
- `logs/routing-decisions.jsonl` - Routing decisions log
- `logs/completion-audit.jsonl` - Task completion audit

### Configuration
- Queue thresholds: HIGH=3, CRITICAL=8, LOW=2
- Failure bypass: 80% failure rate threshold
- Model validation: Real-time checking against canonical config

### Mongke Research Self-Tasking (2026-03-11)
**Improvement:** Added proactive implicit research opportunity detection
**File:** `scripts/mongke_self_task.py` - `_find_implicit_research_opportunities()`
**Purpose:** Detects research demand not explicitly flagged:
- Routing decisions with research keywords that went to other agents
- Recent proposals needing competitive/market analysis
- Aggregates missed opportunities into actionable research tasks
**Impact:** Shifts mongke from reactive to proactive research, increasing throughput without waiting for explicit requests