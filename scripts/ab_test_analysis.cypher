// =============================================================================
// A/B Test Analysis Queries for Kublai Prompt Optimization
// =============================================================================
// Version: 1.0
// Date: 2026-03-08
// Author: Jochi (Analyst)
//
// Usage: Copy individual queries to cypher-shell or Neo4j Browser
// =============================================================================

// -----------------------------------------------------------------------------
// QUERY 1: Basic A/B Test Summary
// Returns key metrics for control vs treatment groups
// -----------------------------------------------------------------------------
MATCH (t:Task)
WHERE t.ab_test_group IS NOT NULL
  AND t.created > datetime() - duration('P7D')
WITH t.ab_test_group AS group,
     count(t) AS n,
     avg(t.data_quality_score) AS avg_quality,
     stddev(t.data_quality_score) AS std_quality,
     min(t.data_quality_score) AS min_quality,
     max(t.data_quality_score) AS max_quality,
     sum(CASE WHEN upper(t.status) = 'COMPLETED' THEN 1 ELSE 0 END) AS successes,
     avg(t.duration_seconds) AS avg_duration,
     avg(COALESCE(t.retry_count, 0)) AS avg_retries
RETURN group,
       n AS sample_size,
       round(avg_quality * 100) / 100 AS avg_quality,
       round(std_quality * 100) / 100 AS std_quality,
       min_quality,
       max_quality,
       successes,
       round((successes * 100.0 / n), 1) AS success_rate_pct,
       round(avg_duration) AS avg_duration_seconds,
       round(avg_retries * 100) / 100 AS avg_retries
ORDER BY group;

// -----------------------------------------------------------------------------
// QUERY 2: Statistical Significance Calculation
// Returns t-statistic and effect size for quality difference
// -----------------------------------------------------------------------------
MATCH (t:Task)
WHERE t.ab_test_group IS NOT NULL
  AND t.data_quality_score IS NOT NULL
  AND t.created > datetime() - duration('P7D')
WITH t.ab_test_group AS group,
     t.data_quality_score AS quality
WITH group,
     count(quality) AS n,
     avg(quality) AS mean,
     stdev(quality) AS std
WITH collect({group: group, n: n, mean: mean, std: std}) AS stats
WITH stats[0] AS control,
     stats[1] AS treatment
WITH
  // Pooled standard error
  sqrt((pow(control.std, 2) / control.n) + (pow(treatment.std, 2) / treatment.n)) AS pooled_se,
  // Difference in means
  (treatment.mean - control.mean) AS mean_diff,
  control.n AS n_control,
  treatment.n AS n_treatment,
  control.mean AS mean_control,
  treatment.mean AS mean_treatment,
  control.std AS std_control,
  treatment.std AS std_treatment
WITH
  CASE WHEN pooled_se > 0 THEN mean_diff / pooled_se ELSE 0 END AS t_statistic,
  mean_diff,
  n_control,
  n_treatment,
  mean_control,
  mean_treatment
RETURN
  'Quality Difference Test' AS test_name,
  round(mean_control * 100) / 100 AS control_mean_quality,
  round(mean_treatment * 100) / 100 AS treatment_mean_quality,
  round(mean_diff * 100) / 100 AS absolute_diff,
  round((mean_diff / control.mean * 100), 1) AS relative_lift_pct,
  round(t_statistic, 3) AS t_statistic,
  // P-value approximation (two-tailed)
  CASE
    WHEN abs(t_statistic) < 1.96 THEN '> 0.05 (not significant)'
    WHEN abs(t_statistic) < 2.58 THEN '0.01 - 0.05 (significant)'
    WHEN abs(t_statistic) < 3.29 THEN '0.001 - 0.01 (highly significant)'
    ELSE '< 0.001 (very highly significant)'
  END AS significance_level,
  n_control,
  n_treatment;

// -----------------------------------------------------------------------------
// QUERY 3: Success Rate Chi-Square Test
// Tests if success rate difference is statistically significant
// -----------------------------------------------------------------------------
MATCH (t:Task)
WHERE t.ab_test_group IS NOT NULL
  AND t.created > datetime() - duration('P7D')
WITH t.ab_test_group AS group,
     count(t) AS total,
     sum(CASE WHEN upper(t.status) = 'COMPLETED' THEN 1 ELSE 0 END) AS successes,
     sum(CASE WHEN upper(t.status) = 'FAILED' THEN 1 ELSE 0 END) AS failures
WITH group, total, successes, failures,
     (successes * 1.0 / total) AS success_rate
WITH collect({group: group, total: total, successes: successes, failures: failures, success_rate: success_rate}) AS results
WITH results[0] AS r1, results[1] AS r2
WITH
  r1.total + r2.total AS grand_total,
  (r1.successes + r2.successes) AS total_successes,
  (r1.failures + r2.failures) AS total_failures,
  r1, r2
WITH
  // Expected values under null hypothesis
  (r1.total * total_successes * 1.0 / grand_total) AS expected_r1_success,
  (r1.total * total_failures * 1.0 / grand_total) AS expected_r1_failure,
  (r2.total * total_successes * 1.0 / grand_total) AS expected_r2_success,
  (r2.total * total_failures * 1.0 / grand_total) AS expected_r2_failure,
  // Observed values
  r1.successes * 1.0 AS obs_r1_success,
  r1.failures * 1.0 AS obs_r1_failure,
  r2.successes * 1.0 AS obs_r2_success,
  r2.failures * 1.0 AS obs_r2_failure
WITH
  // Chi-square statistic
  pow(obs_r1_success - expected_r1_success, 2) / expected_r1_success +
  pow(obs_r1_failure - expected_r1_failure, 2) / expected_r1_failure +
  pow(obs_r2_success - expected_r2_success, 2) / expected_r2_success +
  pow(obs_r2_failure - expected_r2_failure, 2) / expected_r2_failure AS chi_square
RETURN
  'Success Rate Difference Test' AS test_name,
  round(r1.success_rate * 1000) / 10 AS control_success_rate_pct,
  round(r2.success_rate * 1000) / 10 AS treatment_success_rate_pct,
  round((r2.success_rate - r1.success_rate) * 1000) / 10 AS rate_diff_pct,
  round(chi_square, 3) AS chi_square_statistic,
  CASE
    WHEN chi_square < 3.84 THEN '> 0.05 (not significant)'
    WHEN chi_square < 6.63 THEN '0.05 - 0.01 (significant)'
    WHEN chi_square < 10.83 THEN '0.01 - 0.001 (highly significant)'
    ELSE '< 0.001 (very highly significant)'
  END AS significance_level;

// -----------------------------------------------------------------------------
// QUERY 4: Agent-Specific A/B Results
// Breaks down results by agent to detect agent-specific effects
// -----------------------------------------------------------------------------
MATCH (t:Task)
WHERE t.ab_test_group IS NOT NULL
  AND t.created > datetime() - duration('P7D')
WITH t.agent AS agent,
     t.ab_test_group AS group,
     count(t) AS n,
     avg(t.data_quality_score) AS avg_quality,
     sum(CASE WHEN upper(t.status) = 'COMPLETED' THEN 1 ELSE 0 END) AS successes
RETURN agent, group, n,
       round(avg_quality * 100) / 100 AS avg_quality,
       successes,
       round((successes * 100.0 / n), 1) AS success_rate_pct
ORDER BY agent, group;

// -----------------------------------------------------------------------------
// QUERY 5: Priority-Level A/B Results
// Tests if optimization affects different task priorities differently
// -----------------------------------------------------------------------------
MATCH (t:Task)
WHERE t.ab_test_group IS NOT NULL
  AND t.created > datetime() - duration('P7D')
WITH t.priority AS priority,
     t.ab_test_group AS group,
     count(t) AS n,
     avg(t.data_quality_score) AS avg_quality,
     sum(CASE WHEN upper(t.status) = 'COMPLETED' THEN 1 ELSE 0 END) AS successes
RETURN priority, group, n,
       round(avg_quality * 100) / 100 AS avg_quality,
       successes,
       round((successes * 100.0 / n), 1) AS success_rate_pct
ORDER BY priority, group;

// -----------------------------------------------------------------------------
// QUERY 6: Skill Hint Effectiveness by A/B Group
// Tests if optimization affects skill hint performance
// -----------------------------------------------------------------------------
MATCH (t:Task)
WHERE t.ab_test_group IS NOT NULL
  AND t.skill_hint IS NOT NULL
  AND t.created > datetime() - duration('P7D')
WITH t.skill_hint AS skill_hint,
     t.ab_test_group AS group,
     count(t) AS n,
     avg(t.data_quality_score) AS avg_quality,
     sum(CASE WHEN upper(t.status) = 'COMPLETED' THEN 1 ELSE 0 END) AS successes
WHERE n >= 5  // Minimum sample size per skill hint
RETURN skill_hint, group, n,
       round(avg_quality * 100) / 100 AS avg_quality,
       round((successes * 100.0 / n), 1) AS success_rate_pct
ORDER BY skill_hint, group;

// -----------------------------------------------------------------------------
// QUERY 7: Time-Series A/B Analysis
// Daily breakdown to detect trends or temporal effects
// -----------------------------------------------------------------------------
MATCH (t:Task)
WHERE t.ab_test_group IS NOT NULL
  AND t.created > datetime() - duration('P7D')
WITH date(t.created) AS day,
     t.ab_test_group AS group,
     count(t) AS n,
     avg(t.data_quality_score) AS avg_quality,
     sum(CASE WHEN upper(t.status) = 'COMPLETED' THEN 1 ELSE 0 END) AS successes
RETURN day.toString() AS date, group, n,
       round(avg_quality * 100) / 100 AS avg_quality,
       round((successes * 100.0 / n), 1) AS success_rate_pct
ORDER BY day, group;

// -----------------------------------------------------------------------------
// QUERY 8: Quality Distribution by Group
// Percentiles for understanding distribution shifts
// -----------------------------------------------------------------------------
MATCH (t:Task)
WHERE t.ab_test_group IS NOT NULL
  AND t.data_quality_score IS NOT NULL
  AND t.created > datetime() - duration('P7D')
WITH t.ab_test_group AS group,
     t.data_quality_score AS quality
WITH group,
     count(quality) AS n,
     avg(quality) AS mean,
     percentileCont(quality, 0.25) AS p25,
     percentileCont(quality, 0.50) AS median,
     percentileCont(quality, 0.75) AS p75,
     percentileCont(quality, 0.90) AS p90,
     percentileCont(quality, 0.95) AS p95
RETURN group, n,
       round(mean * 100) / 100 AS mean,
       round(p25 * 100) / 100 AS p25,
       round(median * 100) / 100 AS median,
       round(p75 * 100) / 100 AS p75,
       round(p90 * 100) / 100 AS p90,
       round(p95 * 100) / 100 AS p95
ORDER BY group;

// -----------------------------------------------------------------------------
// QUERY 9: Duration Analysis (Mann-Whitney U proxy)
// Tests if optimization affects task duration
// -----------------------------------------------------------------------------
MATCH (t:Task)
WHERE t.ab_test_group IS NOT NULL
  AND t.duration_seconds IS NOT NULL
  AND t.created > datetime() - duration('P7D')
WITH t.ab_test_group AS group,
     count(t) AS n,
     avg(t.duration_seconds) AS avg_duration,
     percentileCont(t.duration_seconds, 0.50) AS median_duration,
     percentileCont(t.duration_seconds, 0.90) AS p90_duration
RETURN group, n,
       round(avg_duration) AS avg_duration_seconds,
       round(median_duration) AS median_duration_seconds,
       round(p90_duration) AS p90_duration_seconds
ORDER BY group;

// -----------------------------------------------------------------------------
// QUERY 10: Guardrail Check - Critical Tasks
// Verifies no regression in critical/high-priority tasks
// -----------------------------------------------------------------------------
MATCH (t:Task)
WHERE t.ab_test_group IS NOT NULL
  AND t.priority IN ['critical', 'high']
  AND t.created > datetime() - duration('P7D')
WITH t.priority AS priority,
     t.ab_test_group AS group,
     count(t) AS n,
     avg(t.data_quality_score) AS avg_quality,
     sum(CASE WHEN upper(t.status) = 'COMPLETED' THEN 1 ELSE 0 END) AS successes
RETURN priority, group, n,
       round(avg_quality * 100) / 100 AS avg_quality,
       round((successes * 100.0 / n), 1) AS success_rate_pct
ORDER BY priority, group;

// -----------------------------------------------------------------------------
// QUERY 11: A/B Test Status Dashboard
// Single query showing overall test health
// -----------------------------------------------------------------------------
MATCH (t:Task)
WHERE t.ab_test_group IS NOT NULL
  AND t.created > datetime() - duration('P7D')
WITH t.ab_test_group AS group,
     count(t) AS n,
     sum(CASE WHEN upper(t.status) = 'COMPLETED' THEN 1 ELSE 0 END) AS completed,
     sum(CASE WHEN upper(t.status) = 'FAILED' THEN 1 ELSE 0 END) AS failed,
     sum(CASE WHEN upper(t.status) = 'PENDING' THEN 1 ELSE 0 END) AS pending
WITH collect({group: group, n: n, completed: completed, failed: failed, pending: pending}) AS stats
WITH stats[0] AS r1, stats[1] AS r2
RETURN
  'A/B Test Status' AS dashboard,
  datetime() AS checked_at,
  r1.group AS group1,
  r1.n AS group1_total,
  r1.completed AS group1_completed,
  r1.failed AS group1_failed,
  r1.pending AS group1_pending,
  r2.group AS group2,
  r2.n AS group2_total,
  r2.completed AS group2_completed,
  r2.failed AS group2_failed,
  r2.pending AS group2_pending,
  r1.n + r2.n AS total_sample,
  // Balance check
  round(abs(r1.n - r2.n) * 100.0 / (r1.n + r2.n), 1) AS imbalance_pct,
  CASE
    WHEN abs(r1.n - r2.n) * 100.0 / (r1.n + r2.n) > 10 THEN 'WARNING: Imbalanced > 10%'
    ELSE 'OK: Balanced within 10%'
  END AS balance_status,
  // Sample size check
  CASE
    WHEN r1.n < 50 OR r2.n < 50 THEN 'WARNING: Below minimum sample (50)'
    WHEN r1.n < 150 OR r2.n < 150 THEN 'INFO: Below recommended sample (150)'
    ELSE 'OK: Sufficient sample size'
  END AS sample_status;

// -----------------------------------------------------------------------------
// QUERY 12: Rollout Decision Summary
// Computes all decision criteria in one query
// -----------------------------------------------------------------------------
MATCH (t:Task)
WHERE t.ab_test_group IS NOT NULL
  AND t.created > datetime() - duration('P7D')
WITH t.ab_test_group AS group,
     count(t) AS n,
     avg(t.data_quality_score) AS avg_quality,
     sum(CASE WHEN upper(t.status) = 'COMPLETED' THEN 1 ELSE 0 END) AS successes,
     t.priority AS priority
WITH group, n, avg_quality, successes, priority
WITH group,
     sum(n) AS total_n,
     avg(avg_quality) AS overall_quality,
     sum(successes) AS total_successes
WITH collect({group: group, n: total_n, quality: overall_quality, successes: total_successes}) AS results
WITH results[0] AS r1, results[1] AS r2
WITH
  r2.quality - r1.quality AS quality_diff,
  (r2.successes * 100.0 / r2.n) - (r1.successes * 100.0 / r1.n) AS success_rate_diff
RETURN
  'Rollout Decision' AS analysis_type,
  round(r1.quality * 100) / 100 AS control_quality,
  round(r2.quality * 100) / 100 AS treatment_quality,
  round(quality_diff * 100) / 100 AS quality_lift,
  CASE
    WHEN quality_diff >= 0.5 THEN 'PASS: Meets +0.5 threshold'
    WHEN quality_diff > 0 THEN 'INFO: Positive but below threshold'
    WHEN quality_diff <= -0.3 THEN 'FAIL: Regression >= -0.3 (ROLLBACK)'
    ELSE 'WARNING: No lift detected'
  END AS quality_criteria,
  round(r1.successes * 100.0 / r1.n, 1) AS control_success_pct,
  round(r2.successes * 100.0 / r2.n, 1) AS treatment_success_pct,
  round(success_rate_diff, 1) AS success_rate_lift,
  CASE
    WHEN success_rate_diff >= 5 THEN 'PASS: Meets +5% threshold'
    WHEN success_rate_diff > 0 THEN 'INFO: Positive but below threshold'
    WHEN success_rate_diff <= -5 THEN 'FAIL: Regression >= -5% (ROLLBACK)'
    ELSE 'WARNING: No lift detected'
  END AS success_rate_criteria,
  CASE
    WHEN r1.n < 50 OR r2.n < 50 THEN 'INSUFFICIENT DATA'
    WHEN quality_diff >= 0.5 AND success_rate_diff >= 5 THEN 'RECOMMEND: ROLL OUT TO 100%'
    WHEN quality_diff > 0 OR success_rate_diff > 0 THEN 'RECOMMEND: EXTEND TEST'
    WHEN quality_diff <= -0.3 OR success_rate_diff <= -5 THEN 'RECOMMEND: ROLLBACK IMMEDIATELY'
    ELSE 'RECOMMEND: ITERATE DESIGN'
  END AS overall_recommendation;
