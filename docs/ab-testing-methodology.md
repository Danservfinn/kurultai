# A/B Testing Methodology for Kublai Prompt Optimization

**Version:** 1.0
**Date:** 2026-03-08
**Author:** Jochi (Analyst)
**Status:** Ready for Implementation

---

## Executive Summary

This methodology defines the statistical framework for validating prompt optimization changes before full rollout. The framework ensures that optimization improvements are real, measurable, and do not introduce regressions.

**Testing Strategy:**
- Split tasks 50/50 between control (no optimization) and treatment (with optimization)
- Measure quality lift, success rate, duration changes
- Require statistical significance before rollout
- Automated rollback if regressions detected

---

## Experimental Design

### Hypothesis

**H₀ (Null Hypothesis):** Prompt optimization has no effect on task outcomes.
- Quality scores: μ_control = μ_treatment
- Success rates: p_control = p_treatment

**H₁ (Alternative Hypothesis):** Prompt optimization improves task outcomes.
- Quality scores: μ_treatment > μ_control
- Success rates: p_treatment > p_control

### Experimental Variables

| Variable | Type | Description |
|----------|------|-------------|
| `ab_test_group` | Independent | "control" or "treatment" assignment |
| `data_quality_score` | Dependent | Primary outcome measure (0-10 scale) |
| `status` | Dependent | Success/failure (completed/failed) |
| `duration_seconds` | Dependent | Task completion time |
| `retry_count` | Dependent | Number of retries required |

### Assignment Mechanism

**Deterministic 50/50 Split:**
```python
def get_ab_group(task_id: str) -> str:
    """
    Assign task to A/B test group based on hash of task_id.
    Ensures consistent assignment for same task_id across retries.
    """
    import hashlib
    hash_value = int(hashlib.sha256(task_id.encode()).hexdigest(), 16)
    return 'treatment' if hash_value % 2 == 0 else 'control'
```

**Properties:**
- Deterministic: Same task_id always maps to same group
- Even distribution: 50/50 split with expected 49-51% variance
- Persistent: Survives task retries and system restarts
- Audit-able: Group assignment is reproducible

---

## Success Metrics

### Primary Metric

**data_quality_score** (0-10 scale)
- Measured by task-report-hook.py
- Composite measure of output quality
- Target lift: +0.5 points minimum
- Statistical test: Two-sample t-test (unequal variance)

### Secondary Metrics

| Metric | Target | Test | Threshold |
|--------|--------|------|-----------|
| Success Rate | +5% | Chi-square test | p < 0.05 |
| Duration | -10% | Mann-Whitney U | p < 0.05 |
| Retry Count | -20% | Poisson test | p < 0.05 |
| Token Efficiency | +5% | t-test | p < 0.05 |

### Guardrail Metrics

**These must NOT regress:**
- Critical task success rate: 0% regression allowed
- High-priority task quality: 0% regression allowed
- Any agent-specific quality: <0.3 point regression threshold

---

## Statistical Power Analysis

### Sample Size Calculation

Using two-sample t-test formula:
```
n = (Z_α + Z_β)² × 2 × σ² / Δ²
```

Where:
- Z_α = 1.96 (95% confidence, two-tailed)
- Z_β = 0.84 (80% power)
- σ = 1.5 (estimated standard deviation of quality scores)
- Δ = 0.5 (minimum detectable effect)

```
n = (1.96 + 0.84)² × 2 × 1.5² / 0.5²
n = 7.84 × 2 × 2.25 / 0.25
n ≈ 141 per group
```

**Minimum sample: 50 tasks per variant** (practical minimum for early signals)
**Recommended sample: 150 tasks per variant** (for 80% power)

### Duration Estimation

At current task volume (~50 tasks/day across all agents):
- 50 tasks per variant: ~2 days
- 150 tasks per variant: ~6 days
- **Minimum test duration: 7 days** (captures weekly patterns)

---

## Analysis Queries

### Basic A/B Test Summary

```cypher
// A/B test summary - key metrics by group
MATCH (t:Task)
WHERE t.ab_test_group IS NOT NULL
  AND t.created > datetime() - duration('P7D')
WITH t.ab_test_group AS group,
     count(t) AS n,
     avg(t.data_quality_score) AS avg_quality,
     stddev(t.data_quality_score) AS std_quality,
     sum(CASE WHEN t.status = 'COMPLETED' THEN 1 ELSE 0 END) AS successes
RETURN group,
       n,
       avg_quality,
       std_quality,
       successes,
       (successes * 1.0 / n) AS success_rate
```

### Statistical Significance Test

```cypher
// Two-sample t-test for quality difference
// Returns p-value for treatment vs control
MATCH (t:Task)
WHERE t.ab_test_group IS NOT NULL
  AND t.data_quality_score IS NOT NULL
  AND t.created > datetime() - duration('P7D')
WITH t.ab_test_group AS group,
     t.data_quality_score AS quality
WITH group,
     count(quality) AS n,
     avg(quality) AS mean,
     stddev(quality) AS std
WITH collect({group: group, n: n, mean: mean, std: std}) AS stats
RETURN stats[0].group AS group1,
       stats[0].n AS n1,
       stats[0].mean AS mean1,
       stats[0].std AS std1,
       stats[1].group AS group2,
       stats[1].n AS n2,
       stats[1].mean AS mean2,
       stats[1].std AS std2,
       // Pooled standard error
       sqrt((pow(stats[0].std, 2) / stats[0].n) + (pow(stats[1].std, 2) / stats[1].n)) AS pooled_se,
       // T-statistic
       (stats[1].mean - stats[0].mean) / sqrt((pow(stats[0].std, 2) / stats[0].n) + (pow(stats[1].std, 2) / stats[1].n)) AS t_stat
```

### Agent-Specific Breakdown

```cypher
// A/B test results by agent
MATCH (t:Task)
WHERE t.ab_test_group IS NOT NULL
  AND t.created > datetime() - duration('P7D')
WITH t.agent AS agent,
     t.ab_test_group AS group,
     count(t) AS n,
     avg(t.data_quality_score) AS avg_quality,
     sum(CASE WHEN t.status = 'COMPLETED' THEN 1 ELSE 0 END) AS successes
RETURN agent, group, n, avg_quality, successes,
       (successes * 1.0 / n) AS success_rate
ORDER BY agent, group
```

### Task Type Segmentation

```cypher
// A/B test by priority (proxy for task type)
MATCH (t:Task)
WHERE t.ab_test_group IS NOT NULL
  AND t.created > datetime() - duration('P7D')
WITH t.priority AS priority,
     t.ab_test_group AS group,
     count(t) AS n,
     avg(t.data_quality_score) AS avg_quality,
     sum(CASE WHEN t.status = 'COMPLETED' THEN 1 ELSE 0 END) AS successes
RETURN priority, group, n, avg_quality, successes,
       (successes * 1.0 / n) AS success_rate
ORDER BY priority, group
```

---

## Rollout Decision Framework

### Decision Criteria

| Outcome | Action | Condition |
|---------|--------|-----------|
| **ROLL OUT** | Enable 100% | p < 0.05 AND quality lift ≥ +0.5 AND no guardrail regressions |
| **EXTEND** | Continue test | 50 ≤ n < 150 OR 0.05 ≤ p < 0.10 (trending positive) |
| **SEGMENT** | Partial rollout | Significant for some agents/types but not all |
| **ROLLBACK** | Disable optimization | Quality regression ≥ -0.3 OR success rate drop ≥ 5% |
| **ITERATE** | Redesign optimization | No significant difference AND n ≥ 150 |

### Rollback Triggers

**Immediate rollback (feature flag off):**
- Quality drop: ≥ 0.3 points (control > treatment)
- Success rate drop: ≥ 5 percentage points
- Critical task failures: Any increase in critical task failure rate

**Investigation required:**
- Duration increase: ≥ 30% (without quality improvement)
- Retry rate increase: ≥ 20%
- Any agent-specific regression ≥ -0.5 quality points

---

## Implementation Checklist

### Phase 1: Setup (Pre-Test)

- [ ] Add `ab_test_group` field to Task node schema
- [ ] Implement `get_ab_group()` in task creation
- [ ] Create feature flag for enabling optimization
- [ ] Set baseline measurement (1 week without optimization)
- [ ] Document integration point in `neo4j_task_tracker.py:create_task_full()`

### Phase 2: Test Execution

- [ ] Enable A/B test (feature flag at 50%)
- [ ] Monitor daily: group balance, sample sizes
- [ ] Weekly analysis: run A/B test queries
- [ ] Check guardrail metrics every 3 days
- [ ] Document any anomalies or outliers

### Phase 3: Analysis

- [ ] After 7 days or 150 tasks per variant: run full analysis
- [ ] Calculate p-values for all metrics
- [ ] Check segment-level results (agent, priority, skill_hint)
- [ ] Visualize results: quality distribution, success rate trends
- [ ] Generate decision report with recommendation

### Phase 4: Decision

- [ ] Review decision framework criteria
- [ ] If ROLL OUT: enable 100% and monitor for 7 days
- [ ] If EXTEND: continue test with updated timeline
- [ ] If SEGMENT: partial rollout with clear segment definition
- [ ] If ROLLBACK: disable and document failure mode
- [ ] If ITERATE: feed learnings back to design phase

---

## Integration Points

### Task Creation Hook

**File:** `~/.openclaw/agents/main/scripts/neo4j_task_tracker.py:create_task_full()`

```python
# After task_id generation, add A/B group assignment
task_id = str(uuid.uuid4())[:12]
ab_group = get_ab_group(task_id)  # 'control' or 'treatment'

# In Neo4j CREATE statement, add:
ab_test_group: $ab_group,

# For feature flag, only apply optimization to treatment group:
use_optimization = (ab_group == 'treatment') and FEATURE_FLAG_OPTIMIZATION_ENABLED
```

### Feature Flag

**File:** `~/.openclaw/agents/main/config/feature_flags.json`

```json
{
  "prompt_optimization_ab_test": {
    "enabled": true,
    "treatment_percent": 50,
    "enabled_at": "2026-03-08T00:00:00Z",
    "description": "A/B test for prompt optimization framework"
  }
}
```

### Reporting Hook

**File:** `~/.openclaw/agents/main/hooks/task-report-hook.py`

```python
# Ensure ab_test_group is recorded in task completion
# Already tracked in Task node, verify it's included in report
```

---

## Monitoring and Alerts

### Daily Checks

- Group balance (target: 45-55% split)
- Sample size accumulation
- No critical errors in treatment group

### Weekly Checks

- Statistical significance calculation
- Guardrail metric regression check
- Duration and token efficiency

### Alerts

**WARNING level:**
- Group imbalance > 60/40
- Sample size < 25 per variant after 3 days
- Success rate drop > 3% (not meeting rollback threshold)

**CRITICAL level:**
- Quality regression ≥ 0.3 points (rollback immediately)
- Success rate drop ≥ 5% (rollback immediately)
- Critical task failure in treatment group

---

## Appendix: Statistical Reference

### T-Test Interpretation

| t-statistic | p-value (approx) | Interpretation |
|-------------|------------------|----------------|
| < 1.96 | > 0.05 | Not significant |
| 1.96 - 2.58 | 0.05 - 0.01 | Significant |
| 2.58 - 3.29 | 0.01 - 0.001 | Highly significant |
| > 3.29 | < 0.001 | Very highly significant |

### Confidence Interval Calculation

```
95% CI = mean ± (1.96 × SE)
where SE = std / sqrt(n)
```

### Effect Size (Cohen's d)

```
d = (mean_treatment - mean_control) / pooled_std
where pooled_std = sqrt((std1² + std2²) / 2)
```

Interpretation:
- d = 0.2: Small effect
- d = 0.5: Medium effect (our target)
- d = 0.8: Large effect

---

**Status:** Ready for Implementation
**Next Step:** Sprint 5 (T5.1) - Enable A/B test for 50% of tasks
**Owner:** Jochi (analysis) + Ogedei (deployment)

---

*Generated by Jochi (Analyst) - 2026-03-08*
*Task ID: kublai-ab-test-framework-1772992005*
