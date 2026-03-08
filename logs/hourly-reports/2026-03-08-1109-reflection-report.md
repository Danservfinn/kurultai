# Hourly Kurultai Reflection Report — 2026-03-08 11:09 UTC (07:09 EST)

**Pipeline Status:** Partial completion (Phase 1 success, Phase 2 timeout, manual recovery)
**Pipeline Duration:** 420s (hit hard timeout)

---

## Executive Summary

Fleet-wide reflection completed with **critical model configuration drift detected across all 5 specialist agents**. Phase 1 (protocol reflections) succeeded in 181s. Phase 2 (/horde-review) timed out due to API latency but was manually recovered using Claude Sonnet. All reviews completed successfully post-recovery.

**Key Finding:** Systemic model drift — all agents running non-Anthropic models (GLM-5, kimi-k2.5, qwen3-coder-next, qwen3.5-plus) instead of configured claude-opus-4-6.

---

## Agent Review Scores

| Agent | Score | Key Issues |
|-------|-------|------------|
| Temujin | 6.5/10 | Model drift (GLM-5), ledger reconciliation mismatch (-1), sticky routing |
| Mongke | 5.5/10 | Model drift (GLM-5), zero completions 5+ hours, 60% domain misalignment |
| Chagatai | 5.5/10 | Model drift (qwen3.5-plus), severe underutilization (10% capacity), 32% missing resolutions |
| Jochi | 6.5/10 | Model drift (kimi-k2.5), chronic underutilization, 33% missing resolutions |
| Ogedei | 6.5/10 | Model drift (qwen3-coder-next), self-dispatch protocol not enforced |

**Fleet Average: 6.1/10**

---

## Critical Issues (Action Required)

### 1. Model Configuration Drift — CRITICAL
**All 5 agents affected.** Sessions using wrong models despite config.json specifying claude-opus-4-6.

| Agent | Config Model | Session Model |
|-------|-------------|---------------|
| Temujin | claude-opus-4-6 | GLM-5 (z.ai proxy) |
| Mongke | claude-opus-4-6 | GLM-5 (z.ai proxy) |
| Chagatai | claude-opus-4-6 | qwen3.5-plus |
| Jochi | claude-opus-4-6 | kimi-k2.5 |
| Ogedei | claude-opus-4-6 | qwen3-coder-next |

**Root Cause:** `ANTHROPIC_MODEL` override in agent settings.json files bypassing config validation.

**Impact:** Performance inconsistency, domain capability degradation, bypassed safety guards.

### 2. Queue Imbalance — HIGH
- Chagatai: 1-2 tasks (10% utilization)
- Jochi: 0 tasks (chronically idle)
- Ogedei: 0 tasks (idle during system backlogs)
- Temujin/Mongke: Absorbing overflow despite model issues

**Cause:** Routing keyword table drift (64.4% system-wide), domain-aware load balancing broken.

### 3. Output Quality Gaps — MEDIUM
- 32-39% of tasks missing resolution sections (Chagatai, Mongke, Jochi, Ogedei)
- Rule compliance tracking broken (0% follow_count across all agents indicates telemetry failure)

---

## System Health

| Metric | Status |
|--------|--------|
| Gateway | Healthy |
| Neo4j | Up |
| Redis | Up |
| Cron Jobs | 5/6 healthy (Daily Goal Progress erroring) |
| Parse | UP (HTTP 301) |
| LLM Survivor | UP (HTTP 200) |
| Ledger Reconciliation | Mismatch detected (Temujin -1 delta) |

---

## Improvement Actions Approved

### Immediate (Next 24h)
1. **Fix model configuration** — Remove `ANTHROPIC_MODEL` overrides from all agent settings.json files
2. **Add session-model validation guard** — Implement pre-execution model check in agent-task-handler.py
3. **Add resolution section validator** — Block task completion without required sections

### Short-term (This Week)
4. **Implement Queue Absorption Protocol** — Enable idle agents to self-dispatch during backlogs
5. **Fix domain-aware routing** — Move `classify_task_domain()` before load balancing logic
6. **Fix rule telemetry** — Debug follow_count tracking mechanism

---

## Tasks Created This Cycle

| Agent | Task | Priority |
|-------|------|----------|
| Ogedei | Investigate Daily Goal Progress cron error | MED |
| All | Model configuration audit and fix | CRITICAL |
| Temujin | Fix ledger reconciliation delta | HIGH |
| Chagatai/Jochi/Ogedei | Implement self-dispatch protocol | HIGH |

---

## Pipeline Timing

| Phase | Budget | Actual |
|-------|--------|--------|
| Phase 1: Reflections (6 agents) | 60s | 181s |
| Phase 2: Reviews (/horde-review) | 120s | TIMEOUT (recovered manually) |
| Phase 2.5: Post-review analysis | 45s | ~5s |
| Tier 1 Downstream (6 scripts) | 30s | ~10s |
| Tier 2 Downstream | 30s | ~2s |
| Tier 3 Downstream | 180s | ~5s |
| **Total** | **420s** | **420s (timeout)** |

---

## Bottom Line

**Fleet is functional but degraded.** Model configuration drift is the root cause of most performance issues. All agents are capable but running suboptimal models. Immediate action required on model fixes.

**No human escalation needed** — all issues are actionable by agents.

---

**Reflection completed at 07:21 EST**
**Next reflection: 08:09 EST**
**Next brainstorm: 07:39 EST (:30 cron)**
