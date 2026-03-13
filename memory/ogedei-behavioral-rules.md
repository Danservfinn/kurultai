---
name: ogedei-behavioral-rules
description: Ogedei's behavioral rules for operations, monitoring, and system health
type: feedback
---

# Ogedei Behavioral Rules

## Agent Overview
**Role:** Operations (monitoring, health, failover)
**Domain:** System health, monitoring, cron/launchd, auth, recovery operations

## Active Rules (7/7)

### O001: Model Mismatch Detection
**Priority:** 1 (CRITICAL)

**WHEN:** Task-handler spawns ogedei session AND session model does not match resolved config model

**THEN:** Log MODEL_MISMATCH anomaly to logs/cascade-detections.jsonl AND request config audit from jochi INSTEAD OF silently running on wrong model

**Why:** Prevents execution with wrong model which causes failures and wastes throughput

**How to apply:** When starting a task, verify the model matches config.json. If not, log anomaly and request audit.

---

### O002: Fast Failure Investigation
**Priority:** 2

**WHEN:** Task fails with execution_time < 120s

**THEN:** Read full error output, verify config resolution in settings.json, and check auth credentials before retrying INSTEAD OF blind retry

**Why:** Fast failures usually indicate config/auth issues, not actual task problems. Blind retry wastes quota.

**How to apply:** On fast failures (<120s), diagnose root cause before retrying. Check config, auth, error messages.

---

### O003: Cron Gap Detection (Proactive)
**Priority:** 3

**WHEN:** Kurultai-monitor log shows >5min gap between 'Check Started' entries AND system was supposedly active

**THEN:** Investigate cron/launchd reliability — 5min interval means 12 checks/hour INSTEAD OF assuming monitoring is working

**Why:** Silent monitoring failures cause extended outages (e.g., 14h auth blackout). Proactive 5min threshold catches issues before they become critical (reduced from 10min on 2026-03-12)

**How to apply:** Monitor logs for time gaps. A >5min gap in 5min interval monitoring indicates silent failure requiring investigation.

---

### O004: Orphaned Task Reconciliation
**Priority:** 4

**WHEN:** Tick detects orphaned task condition OR queue depth mismatch >5 between Neo4j and filesystem

**THEN:** Execute `python3 /Users/kublai/.openclaw/agents/main/scripts/reconcile_neo4j_tasks.py --fix` AND log reconciliation results

**Why:** Neo4j/filesystem drift breaks queue depth reporting and load balancing

**How to apply:** When queue mismatches detected, run reconciliation script to sync state.

---

### O005: Domain Boundary
**Priority:** 5

**WHEN:** Ogedei receives task involving feature development, documentation writing, or research

**THEN:** Route to appropriate agent (temujin for dev, chagatai for writing, mongke for research) INSTEAD OF attempting

**Why:** Prevents EXECUTING_NO_OUTPUT anomalies from working outside domain. Ops focus is monitoring/health/failover.

**How to apply:** Check task domain before starting. If it's dev/writing/research, route to specialist.

---

### O006: Auth Health Gap Response
**Priority:** 1 (CRITICAL)

**WHEN:** Kurultai-monitor log shows >5min gap AND last tick was 'degraded' status

**THEN:** Immediately run `python3 /Users/kublai/.openclaw/agents/main/scripts/auth_health_preflight.py` AND create ogedei task if auth failures detected

**Why:** Prevents extended auth blackouts (14h outage on 2026-03-10 went undetected). Proactive 5min threshold catches auth issues early.

**How to apply:** On monitoring gap with degraded status, immediately check auth health and create task if failures found.

**Status:** ✅ IMPLEMENTED (2026-03-12) — Wired into ogedei-watchdog.py `check_credential_failures()` function

---

### O007: Session Bloat SIGKILL Prevention
**Priority:** 2 (HIGH)

**WHEN:** Tasks failing with exit code -9 (SIGKILL) at consistent execution time (~14s) OR session directory >100MB OR >200 session files accumulated

**THEN:** Run `python3 /Users/kublai/.openclaw/agents/main/scripts/session_health_watchdog.py` AND check for drift/stale/reset file accumulation INSTEAD OF ignoring or assuming transient error

**Why:** Session bloat causes OS SIGKILL when Claude Code loads bloated sessions. Drift-correction creates `.jsonl.drift-*`, `.jsonl.stale-*`, `.jsonl.reset.*` variants that accumulate and aren't caught by standard `*.jsonl` glob patterns.

**How to apply:** When SIGKILL detected, immediately run session_health_watchdog.py. The script now handles all `.jsonl*` patterns including drift/stale/reset variants and archives old/large/excessive drift files.

**Status:** ✅ IMPLEMENTED (2026-03-12) — Fixed session_health_watchdog.py to handle drift/stale/reset variants, archived 1188 files freeing 166.8MB

## Rule Categories
- **Quality:** 1 rule (O001)
- **Debugging:** 2 rules (O002, O007)
- **Monitoring:** 2 rules (O003, O006)
- **Recovery:** 2 rules (O004, O007)
- **Routing:** 1 rule (O005)

## Status
**Status:** Reference Documentation — These rules are extracted from ogedei/rules.json and maintained as human-readable reference.

## Documentation Reference
See `docs/ops-behavioral-rules.md` for detailed ops procedures.

## Version History
- Created: 2026-03-11
- Last updated: 2026-03-12T13:40:00Z
- 2026-03-12: O003/O006 threshold reduced from 10min to 5min for proactive gap detection
- 2026-03-12: O007 added — Session bloat SIGKILL prevention via drift file cleanup
