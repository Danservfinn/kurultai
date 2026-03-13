---
name: circuit-breaker-stale-state
description: Circuit breaker stale last_failure_rate bug fix
type: feedback
---

# Circuit Breaker Stale State Bug

## Rule
When agents recover from HALF_OPEN to CLOSED state, **always reset `last_failure_rate` to 0.0**.

## Why
Discovered 2026-03-12 during throughput stall investigation. Agents mongke and jochi showed:
- `last_failure_rate: 1.0` but `failure_count: 0`, `success_count: 18/19`

The stale 1.0 values persisted after agents recovered, blocking task dispatch even though agents were healthy.

## How to Apply
The circuit_breaker.py recovery path (HALF_OPEN → CLOSED on success) must reset:
1. `agent_state["failure_count"] = 0`
2. `agent_state["last_failure_rate"] = 0.0`

Fixed in `/Users/kublai/.openclaw/agents/main/scripts/circuit_breaker.py` lines 295-299.

## Files Modified
- `scripts/circuit_breaker.py` - Added reset of failure_count and last_failure_rate on recovery
- `logs/circuit-breaker-state.json` - Manually cleared stale values for mongke, jochi
- `logs/ogedei-watchdog-state.json` - Cleared stale agent_failure_flags
