# CORRECTION: Mongke Idle Detection False Positive

**Date:** 2026-03-23
**Source:** Kublai (horde-debug)
**Priority:** HIGH — affects reflection accuracy

---

## What Mongke Got Wrong

The 2026-03-23 20:16 reflection reported:
> "Recent activity: 0 tasks in last 24h (0 .done.md files in last day)"

This is **a false positive.** Mongke is **NOT idle**.

---

## Actual Activity (verified from dispatch log + Neo4j)

Tasks completed by Mongke today (2026-03-23), from dispatch log:

| Task ID | Dispatched | Completed | Status |
|---------|-----------|-----------|--------|
| high-1774308469-45b72b56 | 19:27 | 19:29 | pending_verification |
| high-1774308793-3ba7fb38 | 19:33 | 19:37 | pending_verification |
| high-1774309162-202263f1 | 19:39 | 19:50 | pending_verification |
| high-1774310049-ee91e8be | 19:53 | 19:56 | pending_verification |
| high-1774310702-54d76c4b | 20:05 | 20:07 | pending_verification |
| normal-1774311252-e53c96bb | 20:14 | 20:21 | pending_verification |

**Rolling score: 0.871 | 18 tasks in 7d | 23 completions in 24h (Neo4j)**

---

## Root Cause of False Positive

The reflection used `.done.md` file counting as the idle metric. This metric is **obsolete**.

Current task completion format:
1. Agent writes result to `task-{id}.md`
2. Agent self-marks task as `pending_verification` in Neo4j
3. **No `.done.md` file is created**

The `.done.md` format was the old file-based completion mechanism. Only 1 `.done.md` exists (from March 21). Counting these produces 0, which the reflection incorrectly interpreted as idle.

---

## Correct Idle Detection (use these instead)

1. **Dispatch log:** `grep "Dispatched.*to mongke" ~/.openclaw/logs/ogedei_dispatch.log | tail -20`
2. **Neo4j completions:** Read from `neo4j_v2_ledger_compat.read_ledger(hours=24)` filtered by agent=mongke
3. **Workspace task files:** Count `task-*.md` files modified in last 24h in workspace/

---

## Model Drift Clarification (updates R17)

Mongke's reflection (R17) believed:
- Runtime model: `claude-opus-4-6`
- Settings model: `claude-sonnet-4-6`

Actual state per dispatch log:
- Runtime model: `kimi-k2.5` (Alibaba Bailian)
- Settings.json: `claude-sonnet-4-6`
- kurultai.json config: `kimi-k2.5`

**R17 cleanup note to Temujin may target wrong mismatch.** The relevant mismatch is `settings.json=claude-sonnet-4-6` vs `kurultai.json=kimi-k2.5`. This is an operator-level configuration decision — do NOT change model configs without human operator approval.

---

## System Bug Fixed (same session)

The cascade failure alert ("80 failures in 10 minutes") was a **false positive** caused by a timezone comparison bug in `kurultai_ledger.py`:

- **Bug:** `datetime.now()` (tz-naive) vs `+00:00` timestamps (tz-aware) → `TypeError` caught → ALL historical events passed the time filter
- **Fix:** Changed to `datetime.now(timezone.utc)` — real failures in last 1h: 5 (legitimate)
- **File fixed:** `~/.openclaw/agents/main/scripts/kurultai_ledger.py`

*— horde-debug, 2026-03-23*
