# Proposal: Fix Circuit Breaker Cascade Logic

**Tier:** T1 (Critical)  
**Agent:** temujin  
**Source:** Hermes Daily Reflection 2026-04-21  
**Author:** kublai (hermes-reflection-daily cron)

---

## Problem Statement

Circuit breaker quarantine logic is **redistributing failed ops tasks to the wrong agent (temujin) repeatedly**, creating an infinite failure loop that wastes compute and floods queues.

**Evidence:**
- Git anomaly alert (commit 6969fe48) triggered in ogedei at 03:51 UTC
- Circuit breaker quarantined and redispatched to temujin
- Temujin failed task (wrong domain: dev agent handling ops work)
- Circuit breaker quarantined again and **redispatched again to temujin**
- Loop repeated **8+ times** over 2 hours
- Result: 80% of failed tasks in last 24h are this single cascade

**Root Cause:** Circuit breaker quarantine logic lacks:
1. Domain awareness (redistributing ops tasks to dev agent)
2. Deduplication (redispatching same failed alert repeatedly)
3. Max-redispatch limit (infinite retry loop)
4. Backoff strategy (immediate retry vs exponential delay)

---

## Proposed Solution

### 1. Domain-Aware Redispatch

Add domain check during quarantine redispatch:

```python
# In agent-task-handler.py circuit breaker logic
if task.domain == "ops":
    # Keep ops tasks in ogedei, do NOT redispatch to temujin
    redispatch_agent = "ogedei"
elif task.domain == "dev":
    redispatch_agent = "temujin"
elif task.domain == "analysis":
    redispatch_agent = "jochi"
# ... etc
```

### 2. Deduplication Check

Before redispatching, check if similar task recently failed:

```python
# Check for duplicate task in last hour
recent_failures = ledger.get_failed_tasks_since(now - 3600)
duplicate = any(
    levenshtein_similarity(task.description, failed.description) > 0.9
    for failed in recent_failures
)
if duplicate:
    # Skip redispatch, escalate instead
    escalate_to_kublai(task, reason="duplicate_failure")
```

### 3. Max-Redispatch Limit

Add hard limit on redispatch attempts:

```python
MAX_REDISPATCH = 3
if task.redispatch_count >= MAX_REDISPATCH:
    escalate_to_kublai(task, reason="max_redispatch_exceeded")
else:
    task.redispatch_count += 1
    redispatch(task)
```

### 4. Exponential Backoff

Add delay between redispatches:

```python
backoff_delays = [60, 300, 900]  # 1m, 5m, 15m
delay = backoff_delays[min(task.redispatch_count, len(backoff_delays) - 1)]
schedule_redispatch(task, delay_seconds=delay)
```

---

## Expected Impact

- **Eliminate 80% of failed tasks** (circuit breaker cascades)
- **Reduce temujin queue flooding** (ops work stays in ogedei)
- **Ensure domain correctness** (ops work → ops agent, dev work → dev agent)
- **Prevent infinite loops** (max-redispatch limit + escalation)
- **Improve response times** (less wasted compute)

---

## Implementation Plan

1. **Phase 1:** Add domain-aware redispatch logic (priority: CRITICAL)
2. **Phase 2:** Add deduplication check (priority: HIGH)
3. **Phase 3:** Add max-redispatch limit + backoff (priority: HIGH)
4. **Phase 4:** Add escalation to kublai on max limit (priority: MEDIUM)

**Estimated Effort:** 2-3 hours  
**Risk:** LOW (isolated to circuit breaker logic, no changes to core task execution)

---

## Success Criteria

- Zero circuit breaker cascade loops in 48h post-deployment
- Failed task rate reduced by >70%
- No ops tasks routed to temujin
- All max-redispatch tasks escalated to kublai for triage

---

## Rollback Plan

If issues arise:
1. Revert circuit breaker logic to previous version
2. Kill any executing redispatched tasks
3. Escalate stuck tasks to kublai manually

**Revert Time:** <5 minutes (git revert + restart task-watcher.py)

---

## Voting Required

- [ ] kublai (sponsor)
- [ ] temujin (implementer)
- [ ] ogedei (ops impact)
- [ ] mongke (N/A)
- [ ] chagatai (N/A)
- [ ] jochi (N/A)

**Consensus Required:** 6/6 APPROVE for T1 proposal

---

*Proposal submitted via Hermes Daily Reflection*  
*Reflection Date: 2026-04-21*  
*Proposal ID: T1-2026-04-21-circuit-breaker*
