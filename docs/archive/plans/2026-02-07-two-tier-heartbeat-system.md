---
plan_manifest:
  version: "1.0"
  created_by: "horde-plan"
  plan_name: "Two-Tier Heartbeat System"
  total_phases: 4
  total_tasks: 10
  phases:
    - id: "1"
      name: "Infra Heartbeat Sidecar"
      task_count: 2
      parallelizable: false
      gate_depth: "STANDARD"
    - id: "2"
      name: "Functional Heartbeat Hooks"
      task_count: 3
      parallelizable: true
      gate_depth: "STANDARD"
    - id: "3"
      name: "Consolidate & Standardize"
      task_count: 3
      parallelizable: true
      gate_depth: "LIGHT"
    - id: "4"
      name: "Verification"
      task_count: 2
      parallelizable: false
      gate_depth: "NONE"
  task_transfer:
    mode: "transfer"
    task_ids: []
---

# Two-Tier Heartbeat System (Option A) Implementation Plan

> **Plan Status:** Draft
> **Created:** 2026-02-07
> **Estimated Tasks:** 10
> **Estimated Phases:** 4

## Context

Kurultai's 6-agent system has a broken heartbeat chain: the **read side** exists (Ogedei checks `Agent.last_heartbeat` in Neo4j, triggers failover if stale >90s) but the **write side has no caller** — nothing invokes `update_agent_heartbeat()`. The entire failover system reads a timestamp that is never written.

Additionally, there are two competing heartbeat node patterns (`Agent.last_heartbeat` vs `AgentHeartbeat.last_seen`) and three inconsistent failover thresholds (60s, 90s, 300s) across the codebase.

**Option A (Two-Tier Heartbeat)** solves this with:
- **Infra heartbeat** — Python sidecar writes `Agent.infra_heartbeat` every 30s (proves gateway process alive)
- **Functional heartbeat** — Agent activity writes `Agent.last_heartbeat` (proves agent is actually working)

Cost: ~$0/month. No new services, no new dependencies, no LLM tokens.

## Overview

**Goal:** Implement a working heartbeat system that enables Ogedei's failover detection.

**Architecture:** Background Python sidecar (infra) + piggyback on `claim_task()`/`complete_task()` (functional). Consolidate duplicate node patterns and standardize thresholds.

## Phase 1: Infra Heartbeat Sidecar
**Duration**: 30-45 minutes
**Dependencies**: None
**Parallelizable**: No (sequential: script then entrypoint)

### Task 1.1: Create heartbeat_writer.py sidecar script
**Dependencies**: None

Create a standalone Python script that writes infra heartbeats for all 6 agents to Neo4j every 30 seconds. Uses existing `neo4j` pip package (already installed in Dockerfile line 23-26). Includes its own circuit breaker (3 consecutive failures -> pause 60s).

```python
# moltbot-railway-template/scripts/heartbeat_writer.py
# Standalone sidecar — writes infra_heartbeat for all 6 agents every 30s
```

Agent list derived from `openclaw.json` agent IDs: `["main", "researcher", "writer", "developer", "analyst", "ops"]`

Key design points:
- Single batched `UNWIND` query per cycle (1 transaction for all 6 agents)
- Circuit breaker: 3 failures -> 60s cooldown, then retry
- Graceful shutdown on SIGTERM/SIGINT
- Writes `Agent.infra_heartbeat` (new property, distinct from `last_heartbeat`)
- Log to stdout (Railway captures container stdout)
- Uses env vars: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`

**Files:**
- Create: `moltbot-railway-template/scripts/heartbeat_writer.py`

**Acceptance Criteria:**
- [ ] Script connects to Neo4j using env vars
- [ ] Writes `infra_heartbeat` timestamp on all 6 Agent nodes every 30s
- [ ] Circuit breaker pauses after 3 consecutive failures
- [ ] Clean shutdown on SIGTERM

### Task 1.2: Launch sidecar from entrypoint.sh
**Dependencies**: Task 1.1

Add background sidecar launch before the `exec` of OpenClaw gateway. The sidecar runs as the same user (moltbot) in the background.

```bash
# In entrypoint.sh, before the OPENCLAW GATEWAY section:
# Start heartbeat writer sidecar (background, as moltbot user)
if [ -n "$NEO4J_PASSWORD" ]; then
    echo "Starting heartbeat writer sidecar..."
    su -s /bin/sh moltbot -c "python /app/scripts/heartbeat_writer.py &"
fi
```

**Files:**
- Modify: `moltbot-railway-template/entrypoint.sh` (add ~5 lines before gateway start)

**Acceptance Criteria:**
- [ ] Sidecar starts before OpenClaw gateway
- [ ] Only starts if `NEO4J_PASSWORD` is set (same guard as migrations)
- [ ] Runs as moltbot user (not root)
- [ ] Does not block gateway startup (backgrounded with `&`)

### Exit Criteria Phase 1
- [ ] `heartbeat_writer.py` exists and is syntactically valid (`python -c "import ast; ast.parse(open('...').read())"`)
- [ ] `entrypoint.sh` contains sidecar launch block
- [ ] Sidecar would write `infra_heartbeat` on Agent nodes (verified by reading the Cypher)

## Phase 2: Functional Heartbeat Hooks
**Duration**: 30-45 minutes
**Dependencies**: None (can run parallel to Phase 1 — different files)
**Parallelizable**: Yes (Tasks 2.1-2.3 independent)

### Task 2.1: Add functional heartbeat to claim_task()
**Dependencies**: None

After a successful task claim, update the claiming agent's `last_heartbeat`. This piggybacks on existing work — no extra Neo4j round-trip needed (add SET clause to existing Cypher).

```python
# openclaw_memory.py line ~429: Add to the existing SET clause
# SET t.status = 'in_progress',
#     t.claimed_by = $agent,
#     t.claimed_at = $claimed_at
# ADD:
# WITH t
# MATCH (a:Agent {name: $agent})
# SET a.last_heartbeat = $claimed_at
```

**Files:**
- Modify: `openclaw_memory.py` (`claim_task()` method, ~line 416-460)

**Acceptance Criteria:**
- [ ] `claim_task()` updates `Agent.last_heartbeat` as side effect
- [ ] No additional Neo4j transaction (same query)
- [ ] Existing tests still pass

### Task 2.2: Add functional heartbeat to complete_task()
**Dependencies**: None

After a successful task completion, update the completing agent's `last_heartbeat`.

```python
# openclaw_memory.py line ~481: Add agent heartbeat update
# After SET t.status = 'completed', ...
# WITH t
# MATCH (a:Agent {name: t.claimed_by})
# SET a.last_heartbeat = $completed_at
```

**Files:**
- Modify: `openclaw_memory.py` (`complete_task()` method, ~line 462-498)

**Acceptance Criteria:**
- [ ] `complete_task()` updates `Agent.last_heartbeat` as side effect
- [ ] No additional Neo4j transaction (same query)
- [ ] Existing tests still pass

### Task 2.3: Fix fallback_mode bug in update_agent_heartbeat()
**Dependencies**: None

Currently `update_agent_heartbeat()` returns `True` when Neo4j is unavailable (fallback mode). This silently masks failures. Should return `False`.

```python
# openclaw_memory.py line ~1057
# BEFORE: return True
# AFTER:  return False
```

**Files:**
- Modify: `openclaw_memory.py` (`update_agent_heartbeat()` method, line ~1057)

**Acceptance Criteria:**
- [ ] `update_agent_heartbeat()` returns `False` in fallback mode
- [ ] Logged as warning (already is)

### Exit Criteria Phase 2
- [ ] `claim_task()` Cypher includes `Agent.last_heartbeat` update
- [ ] `complete_task()` Cypher includes `Agent.last_heartbeat` update
- [ ] `update_agent_heartbeat()` returns `False` in fallback mode
- [ ] `python -m pytest tests/test_openclaw_memory.py` passes (if tests exist)

## Phase 3: Consolidate & Standardize
**Duration**: 30-45 minutes
**Dependencies**: Phase 1, Phase 2
**Parallelizable**: Yes (Tasks 3.1-3.3 independent)

### Task 3.1: Update failover.py to use two-tier model
**Dependencies**: None (after Phase deps)

Update `FailoverProtocol.check_kublai_health()` to check **both** heartbeats:
- `infra_heartbeat` stale >120s = gateway process dead (hard failure)
- `last_heartbeat` stale >90s = agent stuck/zombie (functional failure)

Standardize threshold to 120s for infra (4 missed beats at 30s) and keep 90s for functional.

```python
# src/protocols/failover.py
# Update constants:
HEARTBEAT_INTERVAL_SECONDS = 30
MAX_MISSED_INFRA_HEARTBEATS = 4   # 120s for infra
MAX_MISSED_FUNC_HEARTBEATS = 3    # 90s for functional
```

Update the Cypher in `check_kublai_health()` to read both `a.infra_heartbeat` and `a.last_heartbeat`.

**Files:**
- Modify: `src/protocols/failover.py` (constants + `check_kublai_health()`)

**Acceptance Criteria:**
- [ ] `check_kublai_health()` reads both `infra_heartbeat` and `last_heartbeat`
- [ ] Returns status based on worst-case of the two signals
- [ ] Threshold constants are documented with rationale

### Task 3.2: Migrate failover_monitor.py from AgentHeartbeat to Agent node
**Dependencies**: None (after Phase deps)

`FailoverMonitor` uses a separate `AgentHeartbeat` node type. Migrate it to read from `Agent.infra_heartbeat` and `Agent.last_heartbeat` instead. This eliminates the duplicate node pattern.

Changes:
- `update_heartbeat()` → write `Agent.infra_heartbeat` (or delegate to sidecar)
- `is_agent_available()` → check `Agent.last_heartbeat` (functional) or `Agent.infra_heartbeat` (infra)
- Standardize `FAILOVER_THRESHOLD_SECONDS` from 60 → 90 (match failover.py)

**Files:**
- Modify: `tools/failover_monitor.py` (Cypher queries + constants)

**Acceptance Criteria:**
- [ ] No more references to `AgentHeartbeat` node type
- [ ] Uses `Agent.last_heartbeat` and `Agent.infra_heartbeat`
- [ ] `FAILOVER_THRESHOLD_SECONDS = 90` (standardized)

### Task 3.3: Standardize delegation.py heartbeat threshold
**Dependencies**: None (after Phase deps)

`DelegationProtocol.check_agent_availability()` uses a 5-minute (300s) threshold — too generous. Standardize to 120s to match the infra heartbeat cycle.

```python
# src/protocols/delegation.py line ~582
# BEFORE: five_minutes_ago = (datetime.utcnow() - timedelta(minutes=5)).isoformat() + "Z"
# AFTER:  two_minutes_ago = (datetime.utcnow() - timedelta(seconds=120)).isoformat() + "Z"
```

**Files:**
- Modify: `src/protocols/delegation.py` (`check_agent_availability()`, ~line 573-597)

**Acceptance Criteria:**
- [ ] Threshold changed from 300s to 120s
- [ ] Variable name updated to match new threshold
- [ ] Comment explains: "Agent must have infra heartbeat within 120s"

### Exit Criteria Phase 3
- [ ] `grep -r "AgentHeartbeat" tools/failover_monitor.py` returns 0 matches
- [ ] All three files use consistent thresholds (90s functional, 120s infra)
- [ ] `failover.py` reads both heartbeat properties

## Phase 4: Verification
**Duration**: 15-30 minutes
**Dependencies**: Phase 1, Phase 2, Phase 3
**Parallelizable**: No

### Task 4.1: Run existing test suite
**Dependencies**: None (after Phase deps)

```bash
python -m pytest tests/test_openclaw_memory.py tests/integration/test_failover_workflow.py -v
# Expected: All tests pass
```

**Files:**
- None (read-only verification)

**Acceptance Criteria:**
- [ ] All existing tests pass
- [ ] No import errors from modified modules

### Task 4.2: Manual verification of Cypher correctness
**Dependencies**: Task 4.1

Verify all modified Cypher queries are syntactically valid by dry-running them:

```bash
python -c "
from openclaw_memory import OperationalMemory
# Verify claim_task Cypher parses
# Verify complete_task Cypher parses
# Verify heartbeat_writer batched query parses
print('All Cypher queries parse successfully')
"
```

Also verify:
- `heartbeat_writer.py` imports and runs without syntax errors
- `entrypoint.sh` has valid shell syntax: `bash -n moltbot-railway-template/entrypoint.sh`

**Files:**
- None (read-only verification)

**Acceptance Criteria:**
- [ ] All Cypher queries parse
- [ ] `heartbeat_writer.py` has no syntax errors
- [ ] `entrypoint.sh` passes `bash -n` check

### Exit Criteria Phase 4
- [ ] All tests pass
- [ ] All modified files parse correctly
- [ ] No regressions introduced

## Dependency Graph

```
Phase 1 (Infra Sidecar)     Phase 2 (Functional Hooks)
     \                             /
      \                           /
       Phase 3 (Consolidate & Standardize) — gate: LIGHT
              |
       Phase 4 (Verification) — gate: NONE
```

Phases 1 and 2 can run in parallel (different files, no conflicts).

## Summary of Changes

| File | Change |
|------|--------|
| `moltbot-railway-template/scripts/heartbeat_writer.py` | **NEW** ~80 lines — infra heartbeat sidecar |
| `moltbot-railway-template/entrypoint.sh` | +5 lines — launch sidecar before gateway |
| `openclaw_memory.py` | ~15 lines changed — functional heartbeat in claim/complete + fallback fix |
| `src/protocols/failover.py` | ~20 lines changed — two-tier health check |
| `tools/failover_monitor.py` | ~30 lines changed — migrate from AgentHeartbeat to Agent node |
| `src/protocols/delegation.py` | ~3 lines changed — threshold 300s → 120s |

**Total new code:** ~80 lines (sidecar)
**Total modified:** ~70 lines across 5 existing files

## Threshold Reference (After Implementation)

| Component | Property | Threshold | Meaning |
|-----------|----------|-----------|---------|
| Sidecar | `Agent.infra_heartbeat` | writes every 30s | Gateway process alive |
| Agents | `Agent.last_heartbeat` | on claim/complete | Agent functionally working |
| failover.py | infra check | 120s (4 missed) | Hard failure: process dead |
| failover.py | functional check | 90s (3 missed) | Soft failure: agent stuck |
| failover_monitor.py | availability | 90s | Same as failover.py |
| delegation.py | routing | 120s | Agent eligible for task routing |
