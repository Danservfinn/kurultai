# Known Bugs & Fixes

## 2026-03-10: False-positive pending count in pipeline_health.py

**Symptom:** Ogedei showed "3 pending" with infinite hours-to-clear despite having no actual pending tasks.

**Root Cause:** `bottleneck_index()` in `pipeline_health.py` (line 227) only checked `fname.endswith(".done.md")` to exclude completed tasks. This missed patterns like `.done-{uuid}.md`, `.false-positive.md`, `.resolved.md` which are also terminal states.

**Fix:** Added `skip_patterns` list matching `task-watcher.py` logic:
```python
skip_patterns = ['.done', '.failed', '.resolved', '.completed', '.cancelled', '.false-positive']
if any(pattern in fname for pattern in skip_patterns):
    continue
```

**Files Modified:** `scripts/pipeline_health.py`

**Verification:** After fix, ogedei shows 0 pending (correct).

## TICK_LLM Data Verification Filter (2026-03-11)

**Problem:** Local LLM (Qwen3.5-9B) used in TICK_LLM triage was hallucinating technical issues not present in tick data. Example: claiming "Neo4j disconnected" when tick summary showed `neo4j=up`.

**Solution:** Added DATA-VERIFICATION FILTER in watchdog-gather.sh (lines 911-953) that:
1. Extracts actual system states (neo4j, redis, gateway) from tick summary
2. Cross-checks LLM assertions against actual data
3. Filters out alerts where LLM claims X is down but data shows X=up
4. Logs filtered assertions with full context for audit

**Agent:** mongke (Researcher)
**File:** scripts/watchdog-gather.sh
**Impact:** Eliminates false-positive TICK_LLM alerts for infrastructure issues

