# Mongke Queue Starvation Incident Post-Mortem

**Incident Date:** 2026-03-11  
**Detection Time:** 06:13 EDT  
**Resolution Time:** Pending  
**Severity:** Medium (Score 3/10)  
**Investigator:** Jochi  
**Report Author:** Chagatai  

---

## Executive Summary

On 2026-03-11 at 06:13 EDT, the anomaly detection system flagged Mongke (research agent) with a performance score of 3/10 and complete queue starvation. Initial investigation suggested a broken self-tasking mechanism.

**Root Cause:** A stuck selfwake task (`normal-selfwake-1773223804.md`) created a deadlock condition that prevented the self-tasking system from generating new research tasks. The queue-empty check incorrectly returned "not empty" due to the stuck task, causing the self-tasking logic to exit early without ever evaluating research opportunities.

**Key Finding:** The self-tasking mechanism itself was NOT broken. The routing system was working correctly. The incident was caused by a structural deadlock + missing organic research demand pipeline.

---

## Timeline

| Time | Event |
|------|-------|
| **2026-03-10 23:16** | Last successful self-tasking run (cooldown timestamp recorded) |
| **2026-03-11 06:10** | Stuck selfwake task created (`normal-selfwake-1773223804.md`) |
| **2026-03-11 06:13** | Anomaly scanner detects Mongke starvation (Score 3/10) |
| **2026-03-11 06:13+** | Jochi begins root cause analysis |
| **2026-03-11 08:08** | Post-mortem documentation initiated |

---

## Impact

### Direct Impact
- **Duration:** ~7 hours of degraded research capacity (from last self-tasking run to detection)
- **Tasks Affected:** 0 new research tasks generated during starvation period
- **Agent Performance:** Mongke operating at 30% effectiveness (Score 3/10)

### Systemic Impact
- **Routing System:** Unaffected (continued routing research-keyword tasks to Mongke correctly)
- **Organic Demand:** 50 Mongke tasks processed (3.4% of 1471 total routing decisions)
- **Missed Opportunities:** 0 missed research opportunities in last 100 routing decisions

### User Impact
- No direct user-facing impact detected
- Research backlog may have accumulated for high-priority topics

---

## Root Cause Analysis

### Primary Cause: Deadlock from Stuck Selfwake Task

**Mechanism:**
```python
# mongke_self_task.py lines 399-407
def generate_self_tasks(dry_run=True):
    if not _mongke_queue_empty():  # ← Returns False due to selfwake task
        print("mongke queue not empty — skipping self-task generation")
        return []  # ← EXITS HERE, never reaches _find_implicit_research_opportunities()
```

**The Deadlock:**
1. Selfwake task exists in queue → Queue check returns "not empty"
2. Self-tasking logic exits early → No new tasks generated
3. Selfwake task remains unprocessed → Cycle continues indefinitely

**Why the Selfwake Task Was Stuck:**
- Task contained non-actionable content (reference to cost analysis from 2026-03-09)
- No active Mongke session to process the task
- Selfwake tasks lack automatic triggering mechanism
- No TTL (time-to-live) to auto-expire stale tasks

### Secondary Cause: No Organic Research Demand Pipeline

**Structural Issue:**
- Self-tasking only finds **implicit** opportunities (missed routing decisions)
- No **explicit** proactive research triggers exist
- System depends on external demand signals that may be sparse

**Evidence:**
- Analysis of 1471 routing decisions showed only 23 tasks with research keywords
- Last 100 entries: 0 missed research opportunities
- Routing correctly assigned all 50 Mongke tasks (3.4% of total)

### Tertiary Cause: Anomaly Scanner Queue Detection Bug

**Issue:** The anomaly scanner reported "0 pending, 0 running tasks" when 1 task actually existed.

**Impact:** Delayed accurate diagnosis; suggested false leads during investigation.

---

## Resolution

### Immediate Actions Required

1. **Clear Stuck Selfwake Task**
   ```bash
   # Option A: Mark as completed if resolved
   mv /Users/kublai/.openclaw/agents/mongke/tasks/normal-selfwake-1773223804.md \
      /Users/kublai/.openclaw/agents/mongke/tasks/normal-selfwake-1773223804.completed.done.md
   
   # Option B: Execute task via Mongke session
   # (invoke mongke to process the task)
   ```

2. **Verify Self-Tasking Recovery**
   ```bash
   # Check queue-empty state
   python3 -c "from mongke_self_task import _mongke_queue_empty; print(_mongke_queue_empty())"
   
   # Run self-tasking dry-run
   python3 /Users/kublai/.openclaw/agents/main/scripts/mongke_self_task.py --dry-run
   
   # Confirm task generation
   ls -la /Users/kublai/.openclaw/agents/mongke/tasks/
   ```

### Pending Fixes

1. **Fix Anomaly Scanner Queue Detection**
   - File: `reflection_anomaly_scanner.py`
   - Issue: Incorrect queue state reporting

2. **Exclude Selfwake Tasks from Queue-Empty Check**
   - Modify `_mongke_queue_empty()` to ignore selfwake tasks
   - OR create dedicated processing path for selfwake tasks

3. **Add TTL to Selfwake Tasks**
   - Auto-expire if not processed within N hours
   - Prevent future deadlock scenarios

---

## Prevention

### Short-Term (1-2 weeks)

| Action | Owner | Priority |
|--------|-------|----------|
| Fix queue detection in anomaly scanner | Engineering | High |
| Add TTL to selfwake tasks | Engineering | High |
| Exclude selfwake from queue-empty check | Engineering | Medium |
| Add monitoring for selfwake task age | Engineering | Medium |

### Medium-Term (1 month)

| Action | Owner | Priority |
|--------|-------|----------|
| Implement proactive research triggers | Engineering | High |
| Add weekly cron for research task generation | Engineering | Medium |
| Enhance selfwake task validation | Engineering | Medium |

### Long-Term (Quarter)

| Action | Owner | Priority |
|--------|-------|----------|
| Build ecosystem monitoring (GitHub, HN, competitor changelogs) | Engineering | Medium |
| Implement demand forecasting for research pipeline | Engineering | Low |
| Add circuit-breaker for deadlock detection | Engineering | Medium |

---

## Lessons Learned

### What Went Well
✅ Routing system correctly assigned all research-keyword tasks to Mongke  
✅ Anomaly detection successfully identified the starvation condition  
✅ Systematic debugging approach quickly isolated root cause  
✅ Self-tasking logic itself was sound (not fundamentally broken)

### What Went Wrong
❌ Selfwake tasks can block queue-empty checks (deadlock risk)  
❌ No TTL mechanism for selfwake tasks  
❌ Anomaly scanner reported incorrect queue state  
❌ No proactive research pipeline (depends entirely on implicit demand)  
❌ Selfwake tasks lack automatic triggering

### Key Insights

1. **Deadlocks Hide in Plain Sight:** A single stuck task can cascade into system-wide starvation when queue checks are too broad.

2. **Self-Tasking ≠ Self-Healing:** The self-tasking mechanism only fills gaps in existing demand. Without organic demand, it has nothing to optimize.

3. **Monitoring Blind Spots:** Queue detection bugs can mislead investigations. Multiple independent verification methods are essential.

4. **Structural Gaps:** Mongke has no "push" research pipeline. The system is reactive, not proactive.

### Actionable Rules

**NEW RULE:** WHEN selfwake task blocks self-tasking THEN exclude selfwake from queue-empty check OR add selfwake TTL.

**NEW RULE:** WHEN agent queue shows starvation THEN verify queue state via multiple methods before concluding root cause.

**NEW RULE:** WHEN designing self-tasking systems THEN include both implicit (gap-filling) AND explicit (proactive) task generation.

---

## Appendix: Investigation Evidence

### Queue State Analysis
```bash
# Anomaly report claimed: "0 pending, 0 running tasks"
# Actual state:
$ find /Users/kublai/.openclaw/agents/mongke/tasks -name "*.md" \
    ! -name "*.done*" ! -name "*.failed*" ! -name "*.completed*" \
    ! -name "*.verified*" ! -name "*.rerouted*" ! -name "*.absorbed*" | wc -l
1

# The pending task:
$ ls -l /Users/kublai/.openclaw/agents/mongke/tasks/normal-selfwake-1773223804.md
-rw-r--r--  1 kublai  staff  744 Mar 11 06:10
```

### Cooldown Status
```json
// /Users/kublai/.openclaw/agents/main/logs/mongke-self-task-cooldown.json
{"last_run": "2026-03-10T23:16:25.834296"}
```
- Last run: ~7 hours ago
- Cooldown period: 30 minutes
- **Conclusion:** Cooldown was NOT the blocker

### Routing Decisions Analysis
```
Total entries analyzed: 1471
Tasks with research keywords: 23
Mongke tasks: 50 (3.4% of total)
Last 100 entries: 0 missed research opportunities
```

---

## Document Metadata

- **Created:** 2026-03-11 08:08 EDT
- **Source:** Jochi's root cause analysis at `/Users/kublai/.openclaw/agents/jochi/workspace/mongke_starvation_root_cause_20260311.md`
- **Status:** Draft (pending resolution verification)
- **Review Required:** Engineering team, Kublai

---

*This post-mortem follows the Kurultai incident documentation standard. All findings are based on systematic analysis with verifiable evidence.*
