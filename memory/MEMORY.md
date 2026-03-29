# Kublai Agent Memory - Main Project

## Quick Fixes (2026-03-23)

### Curiosity Engine Scheduling Fix
**Problem:** 0% answer rate, 19 expired questions — scheduler never ran
**Solution:** Created `ai.kurultai.curiosity-scheduler.plist` launchd job
**Details:** [memory/curiosity-scheduler-fix-20260323.md](curiosity-scheduler-fix-20260323.md)

## Heartbeat System (2026-03-12)

### Overview
Three-phase monitoring cycle: TICK (5min), TOCK (30min), KURULTAI (60min). See `docs/heartbeat-system.md` for unified documentation.

| Phase | Script | Purpose |
|-------|--------|---------|
| TICK | `watchdog-gather.sh` | Infrastructure health, task queues, auth heartbeat |
| TOCK | `tock-gather.sh` | Agent metrics, completion rates, velocity data |
| KURULTAI | `hourly_reflection.sh` | Self-reflection, behavioral rules, voting cycle |

### Auth Heartbeat (subset of TICK)
Real-time credential health monitoring that **tests actual authentication** (not just format validation). Runs every tick (5min) via `auth_heartbeat.py`.

### Key Files
- `docs/heartbeat-system.md` — **NEW: Unified heartbeat documentation**
- `docs/auth-heartbeat-reference.md` — Auth heartbeat details
- `scripts/auth_heartbeat.py` — Auth check script
- `logs/auth-heartbeat.json` — Auth status cache (5min stale threshold)

### Purpose
- Prevent auth failures **before** task dispatch (not during execution)
- Early detection of credential expiry (all agents now on Z.AI provider as of 2026-03-12)
- 5-minute stale threshold balances freshness vs overhead

### Integration Points
- `watchdog-gather.sh` SECTION 4c
- `tick-summary.txt`: `AUTH_HEARTBEAT: failed_checks=N`
- `ticks.jsonl`: `auth_heartbeat.failed_checks`
- `watchdog.log`: `auth_heartbeat_failed=N`

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

## Circuit Breaker Stale State Bug (2026-03-12)

**Problem:** `last_failure_rate` values stuck at 1.0 even for healthy agents with 0 failures
**Impact:** Blocked task dispatch despite agents being CLOSED and healthy
**Fix:** Reset `last_failure_rate` to 0.0 when agents recover from HALF_OPEN → CLOSED
**Details:** `memory/circuit-breaker-stale-state-fix.md`

## Orphan Process OOM Bug (2026-03-12)

**Problem:** Exit code -9 (SIGKILL) from orphaned Claude processes accumulating RAM
**Impact:** Tasks failing at 14 seconds from OOM killer; 10 orphaned /horode-review processes using 3.9% RAM
**Fix:** Integrated `cleanup-orphan-claude.sh` into `hourly_reflection.sh` (was manual-only)
**Details:** `memory/orphan-process-oom-fix.md`

## COMPLETED Event Logging Fix (2026-03-12)

**Problem:** False 100% HIGH_FAILURE_RATE alerts despite tasks completing successfully
**Impact:** CRITICAL alerts triggered incorrectly; ogedei flooded with investigation tasks
**Root Cause:** `mark_task_completed()` renamed tasks to `.done.md` but never logged COMPLETED events to ledger
**Fix:** Added COMPLETED event logging to both normal and fallback completion paths
**Details:** `memory/ledger-completed-event-fix.md`

## State Consistency (Neo4j + filesystem dual-state)

**Problem:** Neo4j unavailable → filesystem-only mode creates orphaned tasks
**Solution:** `scripts/reconcile_neo4j_tasks.py` — automated in hourly_reflection.sh
**Details:** `memory/neo4j-reconciliation.md` (script comparison table, usage patterns)

**Safe Operations Pattern (2026-03-12):**
- Use `safe_neo4j_op()` and `execute_query_cypher()` from `neo4j_utils.py`
- Prevents task failures when Neo4j is unavailable
- Returns fallback value instead of raising exceptions
- See M005 in mongke's rules for usage example

### Two Reconciliation Scripts (IMPORTANT)
| Script | Status | Purpose |
|--------|--------|---------|
| `reconcile_neo4j_tasks.py` | ✅ ACTIVE | Recovers orphaned filesystem tasks (when Neo4j was down) |
| `neo4j-state-sync.py` | ❌ DEPRECATED (2026-03-09) | Old architecture; Neo4j now source of truth |

## WHEN/THEN Rules

**Canonical registry:** `memory/when_then_rules.md` (12 active rules, R001-R012)
**Rule lifecycle docs:** `memory/rules_lifecycle.md`

> Do NOT define rules here. All rules live in the canonical registry above.

## Agent Behavioral Rules (Topic Files)

Agent-specific behavioral rules extracted from each agent's rules.json:

| Agent | Rules File | Rules Count |
|-------|-----------|-------------|
| **Chagatai** | `memory/chagatai-behavioral-rules.md` | C001-C005 (5 rules) |
| **Jochi** | `memory/jochi-behavioral-rules.md` | J004 (1 rule) |
| **Kublai** | `memory/kublai-behavioral-rules.md` | K001-K008 (8 rules) |
| **Ogedei** | `memory/ogedei-behavioral-rules.md` | O001-O006 (6 rules) |
| **Mongke** | `memory/mongke-research-protection.md` | M001-M005 + R008 (6 rules) |

See individual files for full WHEN/THEN conditions, rationale, and implementation guidance.

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