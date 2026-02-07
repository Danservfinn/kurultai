# Complexity Scoring System: Monitoring and Alerting Design

## Production Monitoring Architecture for Team Spawn Decisions

> **Status**: Design Document
> **Date**: 2026-02-05
> **Author**: Kurultai MLOps Architecture
> **Related**: [`agent_team_orchestration.md`](../plans/agent_team_orchestration.md), [`monitoring.py`](../../tools/monitoring.py)

---

## Executive Summary

This document designs a comprehensive metrics and monitoring system for the complexity scoring system that drives team spawn decisions in the Kurultai capability acquisition pipeline. The monitoring system tracks classification accuracy, cost efficiency, success rates by team size, and provides real-time alerting for anomalous behavior.

### Key Objectives

1. **Classification Quality**: Monitor accuracy of complexity assessments vs actual outcomes
2. **Cost Optimization**: Track token efficiency by complexity bucket
3. **Operational Health**: Detect misclassifications and system degradation
4. **Feedback Loop**: Enable continuous improvement of complexity thresholds

---

## 1. Key Metrics Definitions

### 1.1 Classification Accuracy Metrics

```python
@dataclass
class ClassificationMetrics:
    """Metrics for complexity classification quality."""

    # Core accuracy metrics
    classification_confidence: float  # 0.0 - 1.0
    predicted_complexity: float       # 0.0 - 1.0
    actual_complexity: float          # Derived from post-hoc analysis

    # Calibration metrics
    confidence_calibration_error: float  # |confidence - accuracy|
    complexity_bucket_accuracy: Dict[str, float]  # Per-bucket accuracy

    # Ground truth tracking
    user_override: bool               # Did user manually override?
    override_direction: str           # "up" | "down"
    final_team_size: int              # Actual team size used
    recommended_team_size: int        # Complexity-based recommendation
```

#### Metric: Classification Accuracy Score

**Definition**: Percentage of classifications where predicted complexity bucket matches post-hoc analysis.

**Neo4j Query**:
```cypher
// Classification accuracy by bucket
MATCH (c:ComplexityClassification)-[:RESULTED_IN]->(t:TeamTask)
MATCH (t)-[:HAS_OUTCOME]->(o:TaskOutcome)
WITH c.predicted_bucket as predicted,
     o.actual_complexity_bucket as actual,
     count(*) as total
RETURN predicted,
       actual,
       total,
       CASE WHEN predicted = actual THEN 1.0 ELSE 0.0 END as accuracy,
       count(CASE WHEN predicted = actual THEN 1 END) / toFloat(count(*)) as accuracy_rate
ORDER BY predicted, actual
```

**Target**: >85% accuracy for high-complexity classifications (>0.7)

---

### 1.2 Cost Efficiency Metrics

```python
@dataclass
class CostEfficiencyMetrics:
    """Metrics for token cost efficiency."""

    # Expected vs actual
    expected_tokens: int              # Based on complexity model
    actual_tokens: int                # Measured from execution
    token_efficiency_ratio: float     # expected / actual (1.0 = perfect)

    # Cost by complexity bucket
    cost_per_complexity_bucket: Dict[str, float]
    cost_per_team_size: Dict[int, float]

    # ROI metrics
    tokens_per_capability_learned: float
    cost_per_successful_completion: float
```

#### Metric: Token Cost Efficiency

**Definition**: Ratio of expected tokens (based on complexity classification) to actual tokens consumed.

**Neo4j Query**:
```cypher
// Token efficiency by complexity bucket
MATCH (c:ComplexityClassification)-[:RESULTED_IN]->(t:TeamTask)
MATCH (t)-[:HAS_COST]->(tc:TaskCost)
WITH c.complexity_bucket as bucket,
     avg(c.estimated_tokens) as expected,
     avg(tc.actual_tokens) as actual,
     count(*) as task_count
RETURN bucket,
       expected,
       actual,
       expected / actual as efficiency_ratio,
       task_count,
       CASE
         WHEN expected / actual >= 0.9 THEN "efficient"
         WHEN expected / actual >= 0.7 THEN "acceptable"
         ELSE "inefficient"
       END as efficiency_grade
ORDER BY bucket
```

**Target**: Efficiency ratio >0.9 (within 10% of estimate)

---

### 1.3 Success Rate by Team Size

```python
@dataclass
class TeamSizeSuccessMetrics:
    """Metrics for success rates by team configuration."""

    team_size: int
    task_count: int
    success_count: int
    failure_count: int
    success_rate: float

    # Breakdown by complexity
    success_by_complexity: Dict[str, float]

    # Quality metrics
    avg_mastery_score: float
    min_mastery_score: float
    mastery_variance: float
```

#### Metric: Success Rate by Team Size

**Definition**: Percentage of successful task completions by team size, segmented by complexity.

**Neo4j Query**:
```cypher
// Success rate by team size and complexity
MATCH (c:ComplexityClassification)-[:RESULTED_IN]->(t:TeamTask)
MATCH (t)-[:HAS_OUTCOME]->(o:TaskOutcome)
WITH t.team_size as team_size,
     c.complexity_bucket as complexity,
     count(*) as total,
     count(CASE WHEN o.status = "completed" THEN 1 END) as successes,
     avg(o.mastery_score) as avg_mastery
RETURN team_size,
       complexity,
       total,
       successes,
       successes / toFloat(total) as success_rate,
       avg_mastery
ORDER BY team_size, complexity
```

**Targets**:
- Individual (size=1): >90% success for low complexity
- Small team (size=3): >85% success for medium complexity
- Full team (size=5): >80% success for high complexity

---

### 1.4 Latency by Complexity

```python
@dataclass
class LatencyMetrics:
    """Metrics for task execution latency."""

    # Timing breakdown
    classification_latency_ms: int    # Time to classify
    team_formation_latency_ms: int    # Time to spawn team
    execution_latency_ms: int         # Time to execute
    total_latency_ms: int

    # Percentiles
    p50_latency: float
    p95_latency: float
    p99_latency: float

    # By complexity
    latency_by_bucket: Dict[str, Dict[str, float]]  # bucket -> percentiles
```

#### Metric: End-to-End Latency Distribution

**Definition**: Time from request submission to completion, segmented by complexity bucket.

**Neo4j Query**:
```cypher
// Latency percentiles by complexity bucket
MATCH (c:ComplexityClassification)-[:RESULTED_IN]->(t:TeamTask)
MATCH (t)-[:HAS_OUTCOME]->(o:TaskOutcome)
WHERE o.completed_at IS NOT NULL
WITH c.complexity_bucket as bucket,
     duration.inMillis(t.created_at, o.completed_at).milliseconds as latency_ms
WITH bucket,
     collect(latency_ms) as latencies
RETURN bucket,
       apoc.coll.percentile(latencies, 0.5) as p50_ms,
       apoc.coll.percentile(latencies, 0.95) as p95_ms,
       apoc.coll.percentile(latencies, 0.99) as p99_ms,
       avg(latency_ms) as avg_ms,
       count(*) as sample_size
ORDER BY bucket
```

**Targets**:
- Low complexity: p95 < 5 minutes
- Medium complexity: p95 < 15 minutes
- High complexity: p95 < 45 minutes

---

## 2. Dashboard Design

### 2.1 Real-Time Complexity Distribution

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COMPLEXITY SCORING DASHBOARD                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ REAL-TIME COMPLEXITY DISTRIBUTION (Last 24h)                       │   │
│  │                                                                      │   │
│  │  Low (0.0-0.6)      ████████████████████  45% (128 tasks)          │   │
│  │  Medium (0.6-0.8)   ██████████████        32% (91 tasks)           │   │
│  │  High (0.8-1.0)     ████████              23% (65 tasks)           │   │
│  │                                                                      │   │
│  │  [========= Classification Confidence: 87% =========]               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────┐  ┌─────────────────────────────────────┐   │
│  │ TEAM UTILIZATION BY AGENT   │  │ COST PER CAPABILITY LEARNED         │   │
│  │                             │  │                                     │   │
│  │  Möngke (Research)   ████   │  │  Today:     $12.45 / capability    │   │
│  │  Temüjin (Dev)       █████  │  │  Yesterday: $13.20 / capability    │   │
│  │  Jochi (Validate)    ███    │  │  Trend:     ↓ 5.7%                 │   │
│  │  Ögedei (Ops)        ██     │  │                                     │   │
│  │                             │  │  By Complexity:                     │   │
│  │  [Team Size Distribution]   │  │  Low:    $4.20  |  Med: $11.50    │   │
│  │  Individual: 45%            │  │  High:   $28.75                    │   │
│  │  Small Team: 32%            │  │                                     │   │
│  │  Full Team:  23%            │  │  Target: $15.00                    │   │
│  └─────────────────────────────┘  └─────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ERROR RATES AND MISCLASSIFICATIONS (Last Hour)                     │   │
│  │                                                                      │   │
│  │  Classification Errors: 3 (2.1%)  [Alert if >5%]                   │   │
│  │  ├── Under-classification: 2 (high complexity marked as medium)    │   │
│  │  └── Over-classification: 1 (medium marked as high)                │   │
│  │                                                                      │   │
│  │  Team Spawn Rate: 12/hour  [Normal: 10-15/hour]                    │   │
│  │  Cost Threshold Breaches: 0                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Detailed Metrics Panels

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DETAILED PERFORMANCE METRICS                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ SUCCESS RATE BY TEAM SIZE & COMPLEXITY                             │   │
│  │                                                                      │   │
│  │              Low Complex.    Med Complex.    High Complex.          │   │
│  │  Individual     94% ✓          78% ⚠           45% ✗               │   │
│  │  Small Team     92% ✓          88% ✓           72% ⚠               │   │
│  │  Full Team      89% ✓          85% ✓           81% ✓               │   │
│  │                                                                      │   │
│  │  ✓ = On target  ⚠ = Warning  ✗ = Critical                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ TOKEN COST ANALYSIS (Actual vs Expected)                           │   │
│  │                                                                      │   │
│  │  Bucket    Expected    Actual    Variance    Efficiency             │   │
│  │  ─────────────────────────────────────────────────────────          │   │
│  │  Low       5.2K        5.8K      +11.5%      0.90  Acceptable       │   │
│  │  Medium    18.5K       22.1K     +19.5%      0.84  Warning          │   │
│  │  High      52.0K       48.5K     -6.7%       1.07  Efficient        │   │
│  │                                                                      │   │
│  │  [View Detailed Breakdown]  [Adjust Models]                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ LATENCY HEATMAP (Minutes to Completion)                            │   │
│  │                                                                      │   │
│  │  Time     | Low | Med | High |                                     │   │
│  │  ─────────────────────────────                                     │   │
│  │  p50      | 2.1 | 8.5 | 28.3 |                                     │   │
│  │  p95      | 4.8 | 14.2| 42.1 |  ← High p95 exceeding target        │   │
│  │  p99      | 7.2 | 22.1| 58.9 |                                     │   │
│  │                                                                      │   │
│  │  Target p95: Low=5, Med=15, High=45                                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Feedback Loop Panel

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FEEDBACK LOOP & MODEL HEALTH                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ CONCEPT DRIFT DETECTION                                            │   │
│  │                                                                      │   │
│  │  Feature Drift Score: 0.12  [Healthy: <0.2]                        │   │
│  │  Prediction Drift:    0.08  [Healthy: <0.15]                       │   │
│  │                                                                      │   │
│  │  Drift by Input Feature:                                           │   │
│  │  ├── Domain Novelty:     0.05 ✓                                    │   │
│  │  ├── API Complexity:     0.18 ⚠  (trending up)                     │   │
│  │  ├── Integration Surface: 0.09 ✓                                   │   │
│  │  └── Code Volume:        0.11 ✓                                    │   │
│  │                                                                      │   │
│  │  [Retraining Recommended]  [View Feature Analysis]                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ GROUND TRUTH CAPTURE STATUS                                        │   │
│  │                                                                      │   │
│  │  Tasks with Feedback:     45/284 (15.8%)                           │   │
│  │  User Overrides:          12 (4.2%)                                │   │
│  │  Post-hoc Analysis:       33 (11.6%)                               │   │
│  │                                                                      │   │
│  │  Feedback Quality Score:  8.2/10                                   │   │
│  │  (Based on completeness and consistency)                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Alerting Rules

### 3.1 Alert Definitions

```python
@dataclass
class ComplexityAlertRule:
    """Definition of an alerting rule."""

    name: str
    severity: str  # critical | warning | info
    condition: str
    threshold: float
    evaluation_window: str  # e.g., "5m", "1h", "24h"
    cooldown: str
    notification_channels: List[str]
    auto_resolve: bool
```

### 3.2 Alert: Sudden Spike in Team Spawns

**Rule Definition**:
```yaml
alert: HighTeamSpawnRate
severity: warning
condition: |
  rate(complexity_team_spawns_total[5m]) > 3 * avg_over_time(
    rate(complexity_team_spawns_total[1h])[24h:1h]
  )
threshold: 3.0  # 3x normal rate
evaluation_window: 5m
cooldown: 15m
notification_channels:
  - slack:#alerts-ml
  - pagerduty:low
auto_resolve: true
```

**Neo4j Query**:
```cypher
// Detect spike in team spawn rate
MATCH (t:TeamTask)
WHERE t.created_at > datetime() - duration('PT1H')
WITH datetime() - duration('PT5M') as recent_cutoff,
     datetime() - duration('PT1H') as hour_ago,
     count(CASE WHEN t.created_at > datetime() - duration('PT5M') THEN 1 END) as recent_spawns,
     count(CASE WHEN t.created_at <= datetime() - duration('PT5M') THEN 1 END) as previous_spawns
WITH recent_spawns,
     previous_spawns,
     CASE WHEN previous_spawns > 0
          THEN toFloat(recent_spawns) / previous_spawns
          ELSE 999
     END as spawn_rate_ratio
WHERE spawn_rate_ratio > 3.0
RETURN recent_spawns,
       previous_spawns,
       spawn_rate_ratio,
       "ALERT: Team spawn rate spike detected" as alert
```

**Response Actions**:
1. Check for batch job or unusual traffic pattern
2. Verify complexity classifier is not stuck in high-complexity mode
3. Scale agent pool if sustained increase

---

### 3.3 Alert: High Failure Rate for Specific Complexity Range

**Rule Definition**:
```yaml
alert: HighFailureRateByComplexity
severity: critical
condition: |
  (
    complexity_task_failures_total / complexity_task_total
  ) by (complexity_bucket) > 0.25
threshold: 0.25  # 25% failure rate
evaluation_window: 30m
cooldown: 1h
notification_channels:
  - slack:#alerts-ml-critical
  - pagerduty:high
auto_resolve: true
```

**Neo4j Query**:
```cypher
// High failure rate by complexity bucket
MATCH (c:ComplexityClassification)-[:RESULTED_IN]->(t:TeamTask)
MATCH (t)-[:HAS_OUTCOME]->(o:TaskOutcome)
WHERE t.created_at > datetime() - duration('PT30M')
WITH c.complexity_bucket as bucket,
     count(*) as total,
     count(CASE WHEN o.status = "failed" THEN 1 END) as failures
WITH bucket,
       total,
       failures,
       failures / toFloat(total) as failure_rate
WHERE failure_rate > 0.25 AND total >= 5  // Minimum sample size
RETURN bucket,
       total,
       failures,
       failure_rate,
       "CRITICAL: High failure rate for " + bucket + " complexity" as alert
ORDER BY failure_rate DESC
```

**Response Actions**:
1. Immediately review failed tasks for common patterns
2. Check if complexity thresholds need adjustment
3. Consider temporarily increasing team sizes for affected bucket
4. Escalate to on-call if failure rate >50%

---

### 3.4 Alert: Cost Threshold Exceeded

**Rule Definition**:
```yaml
alert: CostThresholdExceeded
severity: warning
condition: |
  complexity_actual_cost / complexity_expected_cost > 1.5
threshold: 1.5  # 50% over budget
evaluation_window: 1h
cooldown: 30m
notification_channels:
  - slack:#alerts-cost
  - email:finance@kurult.ai
auto_resolve: true
```

**Neo4j Query**:
```cypher
// Cost threshold exceeded detection
MATCH (c:ComplexityClassification)-[:RESULTED_IN]->(t:TeamTask)
MATCH (t)-[:HAS_COST]->(tc:TaskCost)
WHERE t.created_at > datetime() - duration('PT1H')
WITH c.id as classification_id,
       c.estimated_cost as expected,
       tc.actual_cost as actual,
       actual / expected as cost_ratio
WHERE cost_ratio > 1.5
RETURN classification_id,
       expected,
       actual,
       cost_ratio,
       (actual - expected) as overage,
       "WARNING: Cost exceeded by " + round((cost_ratio - 1) * 100) + "%" as alert
ORDER BY cost_ratio DESC
LIMIT 10
```

**Response Actions**:
1. Identify specific tasks causing overruns
2. Review complexity model for systematic underestimation
3. Implement emergency budget controls if widespread
4. Schedule model retraining

---

### 3.5 Alert: Classification Confidence Below Threshold

**Rule Definition**:
```yaml
alert: LowClassificationConfidence
severity: warning
condition: |
  avg(complexity_classification_confidence) by (complexity_bucket) < 0.7
threshold: 0.7
evaluation_window: 15m
cooldown: 1h
notification_channels:
  - slack:#alerts-ml
auto_resolve: true
```

**Neo4j Query**:
```cypher
// Low classification confidence detection
MATCH (c:ComplexityClassification)
WHERE c.created_at > datetime() - duration('PT15M')
WITH c.complexity_bucket as bucket,
     avg(c.confidence_score) as avg_confidence,
     count(*) as sample_count,
     collect(c.confidence_score) as confidences
WHERE avg_confidence < 0.7 AND sample_count >= 3
RETURN bucket,
       avg_confidence,
       sample_count,
       apoc.coll.min(confidences) as min_confidence,
       "WARNING: Low classification confidence in " + bucket + " bucket" as alert
```

**Response Actions**:
1. Review edge-case inputs causing uncertainty
2. Consider adding human-in-the-loop for low-confidence cases
3. Expand training data for ambiguous regions
4. Adjust confidence threshold if model is well-calibrated

---

### 3.6 Alert: Misclassification Pattern Detected

**Rule Definition**:
```yaml
alert: MisclassificationPattern
severity: critical
condition: |
  rate(complexity_underclassification_total[10m]) > 0.05 OR
  rate(complexity_overclassification_total[10m]) > 0.05
threshold: 0.05  # 5% misclassification rate
evaluation_window: 10m
cooldown: 30m
notification_channels:
  - slack:#alerts-ml-critical
  - pagerduty:medium
auto_resolve: true
```

**Neo4j Query**:
```cypher
// Misclassification pattern detection
MATCH (c:ComplexityClassification)-[:RESULTED_IN]->(t:TeamTask)
MATCH (t)-[:HAS_OUTCOME]->(o:TaskOutcome)
WHERE t.created_at > datetime() - duration('PT10M')
WITH c.predicted_bucket as predicted,
       o.actual_bucket as actual,
       count(*) as count
WHERE predicted != actual
WITH collect({predicted: predicted, actual: actual, count: count}) as mismatches,
     sum(count) as total_mismatches
MATCH (c2:ComplexityClassification)
WHERE c2.created_at > datetime() - duration('PT10M')
WITH mismatches,
     total_mismatches,
     count(c2) as total_classifications,
     total_mismatches / toFloat(count(c2)) as mismatch_rate
WHERE mismatch_rate > 0.05
RETURN mismatches,
       total_mismatches,
       total_classifications,
       mismatch_rate,
       "CRITICAL: Misclassification rate at " + round(mismatch_rate * 100) + "%" as alert
```

**Response Actions**:
1. Halt automatic team spawning for affected complexity range
2. Enable manual review for all classifications
3. Emergency model rollback if recent deployment
4. Root cause analysis within 1 hour

---

## 4. Feedback Loop Architecture

### 4.1 Ground Truth Capture

```python
class GroundTruthCapture:
    """
    Captures ground truth for complexity classification improvement.

    Three sources of ground truth:
    1. User overrides (explicit feedback)
    2. Post-hoc complexity analysis (actual vs predicted)
    3. Outcome correlation (success/failure by classification)
    """

    def __init__(self, neo4j_client: OperationalMemory):
        self.neo4j = neo4j_client

    async def capture_user_override(
        self,
        classification_id: str,
        original_bucket: str,
        override_bucket: str,
        reason: Optional[str] = None
    ) -> None:
        """
        Capture when user manually overrides complexity classification.
        """
        query = """
        MATCH (c:ComplexityClassification {id: $classification_id})
        CREATE (o:ComplexityOverride {
            id: $override_id,
            original_bucket: $original_bucket,
            override_bucket: $override_bucket,
            reason: $reason,
            created_at: datetime()
        })
        CREATE (c)-[:HAS_OVERRIDE]->(o)
        SET c.has_override = true,
            c.final_bucket = $override_bucket
        """

        await self.neo4j.run(query, {
            "classification_id": classification_id,
            "override_id": str(uuid.uuid4()),
            "original_bucket": original_bucket,
            "override_bucket": override_bucket,
            "reason": reason
        })

    async def compute_post_hoc_complexity(
        self,
        team_task_id: str
    ) -> Dict[str, Any]:
        """
        Compute actual complexity after task completion.

        Factors:
        - Actual tokens consumed vs estimated
        - Actual time to completion
        - Number of retries needed
        - Final mastery score achieved
        """
        query = """
        MATCH (t:TeamTask {id: $task_id})-[:HAS_OUTCOME]->(o:TaskOutcome)
        MATCH (t)-[:HAS_COST]->(c:TaskCost)
        MATCH (t)<-[:RESULTED_FROM]-(cl:ComplexityClassification)
        RETURN {
            estimated_complexity: cl.overall_score,
            actual_tokens: c.actual_tokens,
            estimated_tokens: cl.estimated_tokens,
            actual_duration_minutes: duration.inMinutes(t.created_at, o.completed_at).minutes,
            estimated_duration_minutes: cl.estimated_duration_minutes,
            retry_count: o.retry_count,
            mastery_score: o.mastery_score,
            team_size: t.team_size
        } as metrics
        """

        result = await self.neo4j.run(query, {"task_id": team_task_id})
        metrics = result[0]["metrics"] if result else {}

        # Compute actual complexity score
        actual_complexity = self._calculate_actual_complexity(metrics)

        # Store post-hoc analysis
        await self._store_post_hoc_analysis(team_task_id, actual_complexity, metrics)

        return {
            "actual_complexity": actual_complexity,
            "metrics": metrics
        }

    def _calculate_actual_complexity(self, metrics: Dict) -> float:
        """
        Calculate actual complexity score from outcome metrics.
        """
        if not metrics:
            return 0.5

        # Token ratio (actual / estimated)
        token_ratio = metrics.get("actual_tokens", 0) / max(metrics.get("estimated_tokens", 1), 1)

        # Duration ratio
        duration_ratio = metrics.get("actual_duration_minutes", 0) / max(metrics.get("estimated_duration_minutes", 1), 1)

        # Retry penalty
        retry_factor = 1 + (metrics.get("retry_count", 0) * 0.2)

        # Mastery difficulty (inverse of score)
        mastery_difficulty = 1 - metrics.get("mastery_score", 0.5)

        # Weighted combination
        complexity = (
            0.3 * min(token_ratio, 3.0) / 3.0 +  # Cap at 3x
            0.3 * min(duration_ratio, 3.0) / 3.0 +
            0.2 * (retry_factor - 1) +
            0.2 * mastery_difficulty
        )

        return min(max(complexity, 0.0), 1.0)
```

### 4.2 Threshold Adjustment Engine

```python
class ThresholdAdjustmentEngine:
    """
    Automatically adjusts complexity thresholds based on feedback.

    Uses Bayesian optimization to find optimal thresholds that
    maximize success rate while minimizing cost.
    """

    def __init__(self, neo4j_client: OperationalMemory):
        self.neo4j = neo4j_client
        self.current_thresholds = {
            "complexity_low": 0.0,
            "complexity_medium": 0.6,
            "complexity_high": 0.8,
        }

    async def analyze_threshold_performance(
        self,
        lookback_days: int = 7
    ) -> Dict[str, Any]:
        """
        Analyze performance of current thresholds.
        """
        query = """
        MATCH (c:ComplexityClassification)-[:RESULTED_IN]->(t:TeamTask)
        MATCH (t)-[:HAS_OUTCOME]->(o:TaskOutcome)
        WHERE c.created_at > datetime() - duration({days: $days})
        WITH c.complexity_bucket as bucket,
             count(*) as total,
             count(CASE WHEN o.status = "completed" THEN 1 END) as successes,
             avg(o.mastery_score) as avg_mastery,
             sum(o.cost) as total_cost
        RETURN bucket,
               total,
               successes,
               successes / toFloat(total) as success_rate,
               avg_mastery,
               total_cost / total as avg_cost
        ORDER BY bucket
        """

        results = await self.neo4j.run(query, {"days": lookback_days})

        return {
            row["bucket"]: {
                "success_rate": row["success_rate"],
                "avg_mastery": row["avg_mastery"],
                "avg_cost": row["avg_cost"],
                "sample_size": row["total"]
            }
            for row in results
        }

    async def recommend_threshold_adjustments(
        self,
        min_samples_per_bucket: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Recommend threshold adjustments based on performance data.
        """
        performance = await self.analyze_threshold_performance()

        recommendations = []

        # Check if medium bucket is underperforming
        if "medium" in performance:
            medium_perf = performance["medium"]
            if medium_perf["success_rate"] < 0.8 and medium_perf["sample_size"] >= min_samples_per_bucket:
                recommendations.append({
                    "threshold": "complexity_medium",
                    "current_value": self.current_thresholds["complexity_medium"],
                    "recommended_value": self.current_thresholds["complexity_medium"] + 0.05,
                    "reason": f"Medium bucket success rate {medium_perf['success_rate']:.1%} below target",
                    "expected_impact": "Move more tasks to full teams, increasing success rate"
                })

        # Check if high bucket is overperforming (could be more aggressive)
        if "high" in performance:
            high_perf = performance["high"]
            if high_perf["success_rate"] > 0.9 and high_perf["sample_size"] >= min_samples_per_bucket:
                recommendations.append({
                    "threshold": "complexity_high",
                    "current_value": self.current_thresholds["complexity_high"],
                    "recommended_value": self.current_thresholds["complexity_high"] - 0.05,
                    "reason": f"High bucket overperforming at {high_perf['success_rate']:.1%}",
                    "expected_impact": "Reduce team size for some tasks, saving costs"
                })

        return recommendations

    async def apply_threshold_adjustment(
        self,
        threshold_name: str,
        new_value: float,
        approved_by: Optional[str] = None
    ) -> bool:
        """
        Apply a threshold adjustment with audit logging.
        """
        old_value = self.current_thresholds.get(threshold_name)

        # Validate new value
        if not 0.0 <= new_value <= 1.0:
            raise ValueError(f"Threshold must be between 0 and 1, got {new_value}")

        # Apply change
        self.current_thresholds[threshold_name] = new_value

        # Log to Neo4j
        query = """
        CREATE (a:ThresholdAdjustment {
            id: $adjustment_id,
            threshold_name: $threshold_name,
            old_value: $old_value,
            new_value: $new_value,
            approved_by: $approved_by,
            applied_at: datetime()
        })
        RETURN a.id
        """

        await self.neo4j.run(query, {
            "adjustment_id": str(uuid.uuid4()),
            "threshold_name": threshold_name,
            "old_value": old_value,
            "new_value": new_value,
            "approved_by": approved_by
        })

        return True
```

### 4.3 Concept Drift Detection

```python
class ConceptDriftDetector:
    """
    Detects when the underlying data distribution changes,
    indicating model retraining may be needed.
    """

    def __init__(self, neo4j_client: OperationalMemory):
        self.neo4j = neo4j_client
        self.drift_threshold = 0.2

    async def detect_feature_drift(
        self,
        feature_name: str,
        window_size_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Detect drift in a specific input feature.

        Uses Population Stability Index (PSI) to measure drift.
        """
        # Get reference distribution (last 30 days)
        reference_query = """
        MATCH (c:ComplexityClassification)
        WHERE c.created_at BETWEEN datetime() - duration({days: 30})
                              AND datetime() - duration({hours: $window})
        RETURN c.$feature_name as value
        """

        # Get current distribution
        current_query = """
        MATCH (c:ComplexityClassification)
        WHERE c.created_at > datetime() - duration({hours: $window})
        RETURN c.$feature_name as value
        """

        reference = await self.neo4j.run(reference_query, {
            "feature": feature_name,
            "window": window_size_hours
        })
        current = await self.neo4j.run(current_query, {
            "feature": feature_name,
            "window": window_size_hours
        })

        # Calculate PSI
        psi = self._calculate_psi(
            [r["value"] for r in reference],
            [r["value"] for r in current]
        )

        return {
            "feature": feature_name,
            "psi": psi,
            "is_drift": psi > self.drift_threshold,
            "severity": "high" if psi > 0.3 else "medium" if psi > 0.2 else "low",
            "reference_samples": len(reference),
            "current_samples": len(current)
        }

    def _calculate_psi(
        self,
        reference: List[float],
        current: List[float],
        bins: int = 10
    ) -> float:
        """
        Calculate Population Stability Index.
        """
        import numpy as np

        # Create bins based on reference distribution
        ref_array = np.array(reference)
        bin_edges = np.percentile(ref_array, np.linspace(0, 100, bins + 1))
        bin_edges[0] = -np.inf
        bin_edges[-1] = np.inf

        # Calculate distributions
        ref_hist, _ = np.histogram(reference, bins=bin_edges)
        curr_hist, _ = np.histogram(current, bins=bin_edges)

        # Normalize to probabilities
        ref_dist = ref_hist / len(reference)
        curr_dist = curr_hist / len(current)

        # Calculate PSI
        psi = 0.0
        for r, c in zip(ref_dist, curr_dist):
            if r > 0 and c > 0:
                psi += (c - r) * np.log(c / r)

        return float(psi)

    async def detect_prediction_drift(
        self,
        window_size_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Detect drift in model predictions (model decay).
        """
        query = """
        MATCH (c:ComplexityClassification)
        WHERE c.created_at > datetime() - duration({hours: $window})
        RETURN c.complexity_bucket as bucket,
               count(*) as count,
               avg(c.overall_score) as avg_score
        ORDER BY bucket
        """

        results = await self.neo4j.run(query, {"window": window_size_hours})

        # Compare to historical baseline
        baseline = await self._get_baseline_distribution()

        current_dist = {r["bucket"]: r["count"] for r in results}
        total = sum(current_dist.values())

        if total == 0:
            return {"is_drift": False, "reason": "No data in window"}

        # Normalize current distribution
        current_norm = {k: v / total for k, v in current_dist.items()}

        # Calculate drift from baseline
        drift_score = sum(
            abs(current_norm.get(k, 0) - baseline.get(k, 0))
            for k in set(current_norm) | set(baseline)
        ) / 2

        return {
            "drift_score": drift_score,
            "is_drift": drift_score > 0.15,
            "current_distribution": current_norm,
            "baseline_distribution": baseline,
            "window_hours": window_size_hours
        }

    async def generate_drift_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive drift report.
        """
        features = [
            "domain_novelty",
            "api_complexity",
            "integration_surface",
            "code_volume"
        ]

        feature_drifts = []
        for feature in features:
            drift = await self.detect_feature_drift(feature)
            feature_drifts.append(drift)

        prediction_drift = await self.detect_prediction_drift()

        # Overall assessment
        high_drift_features = [d for d in feature_drifts if d.get("severity") == "high"]
        needs_retraining = len(high_drift_features) > 0 or prediction_drift.get("is_drift", False)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "feature_drifts": feature_drifts,
            "prediction_drift": prediction_drift,
            "needs_retraining": needs_retraining,
            "retraining_urgency": "high" if len(high_drift_features) > 1 else "medium" if needs_retraining else "low",
            "recommended_action": "immediate_retraining" if len(high_drift_features) > 1 else "schedule_retraining" if needs_retraining else "monitor"
        }
```

---

## 5. Neo4j Schema for Monitoring

### 5.1 Node Types

```cypher
// Complexity classification record
(:ComplexityClassification {
    id: uuid,
    overall_score: float,           // 0.0 - 1.0
    complexity_bucket: string,      // "low" | "medium" | "high"
    confidence_score: float,        // Model confidence
    domain_novelty: float,
    api_complexity: float,
    integration_surface: float,
    code_volume: float,
    estimated_tokens: int,
    estimated_duration_minutes: int,
    recommended_team_size: int,
    created_at: datetime,
    has_override: boolean
})

// Classification override (ground truth)
(:ComplexityOverride {
    id: uuid,
    original_bucket: string,
    override_bucket: string,
    reason: string,
    created_at: datetime
})

// Task outcome for feedback
(:TaskOutcome {
    id: uuid,
    status: string,                 // "completed" | "failed" | "cancelled"
    actual_complexity: float,       // Post-hoc computed
    actual_bucket: string,
    mastery_score: float,
    retry_count: int,
    completed_at: datetime,
    failure_reason: string
})

// Cost tracking
(:TaskCost {
    id: uuid,
    estimated_tokens: int,
    actual_tokens: int,
    estimated_cost: float,
    actual_cost: float,
    cost_variance_percent: float
})

// Threshold adjustment audit
(:ThresholdAdjustment {
    id: uuid,
    threshold_name: string,
    old_value: float,
    new_value: float,
    approved_by: string,
    applied_at: datetime
})

// Drift detection record
(:DriftDetection {
    id: uuid,
    detection_type: string,         // "feature" | "prediction"
    feature_name: string,           // If feature drift
    drift_score: float,
    severity: string,
    detected_at: datetime,
    recommended_action: string
})
```

### 5.2 Relationships

```cypher
(:ComplexityClassification)-[:RESULTED_IN]->(:TeamTask)
(:ComplexityClassification)-[:HAS_OVERRIDE]->(:ComplexityOverride)
(:TeamTask)-[:HAS_OUTCOME]->(:TaskOutcome)
(:TeamTask)-[:HAS_COST]->(:TaskCost)
(:ThresholdAdjustment)-[:AFFECTED]->(:ComplexityClassification)
```

### 5.3 Indexes

```cypher
// Classification lookups
CREATE INDEX complexity_classification_time IF NOT EXISTS
FOR (c:ComplexityClassification) ON (c.created_at, c.complexity_bucket);

CREATE INDEX complexity_classification_confidence IF NOT EXISTS
FOR (c:ComplexityClassification) ON (c.confidence_score);

// Outcome lookups
CREATE INDEX task_outcome_status IF NOT EXISTS
FOR (o:TaskOutcome) ON (o.status, o.completed_at);

CREATE INDEX task_outcome_complexity IF NOT EXISTS
FOR (o:TaskOutcome) ON (o.actual_bucket);

// Cost lookups
CREATE INDEX task_cost_variance IF NOT EXISTS
FOR (tc:TaskCost) ON (tc.cost_variance_percent);

// Override lookups
CREATE INDEX complexity_override_time IF NOT EXISTS
FOR (co:ComplexityOverride) ON (co.created_at);
```

---

## 6. Integration with Existing Monitoring

### 6.1 Prometheus Metrics Extension

```python
class ComplexityScoringMetrics:
    """
    Prometheus metrics for complexity scoring system.
    Extends the existing monitoring.py infrastructure.
    """

    def __init__(self, registry: Optional[MetricsRegistry] = None):
        self.registry = registry or get_registry()
        self._init_complexity_metrics()

    def _init_complexity_metrics(self) -> None:
        """Initialize complexity-specific metrics."""

        # Classification metrics
        self.classifications_total = Counter(
            "complexity_classifications_total",
            "Total number of complexity classifications",
            ["bucket", "confidence_level"]
        )

        self.classification_confidence = Histogram(
            "complexity_classification_confidence",
            "Classification confidence distribution",
            ["bucket"],
            buckets=[0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0]
        )

        # Accuracy metrics
        self.classification_accuracy = Gauge(
            "complexity_classification_accuracy",
            "Classification accuracy by bucket",
            ["bucket"]
        )

        self.misclassifications_total = Counter(
            "complexity_misclassifications_total",
            "Total misclassifications",
            ["predicted_bucket", "actual_bucket"]
        )

        # Cost efficiency metrics
        self.token_efficiency_ratio = Gauge(
            "complexity_token_efficiency_ratio",
            "Token efficiency ratio (expected/actual)",
            ["bucket"]
        )

        self.cost_variance_percent = Histogram(
            "complexity_cost_variance_percent",
            "Cost variance from estimate",
            ["bucket"],
            buckets=[-50, -25, -10, 0, 10, 25, 50, 100]
        )

        # Team spawn metrics
        self.team_spawns_total = Counter(
            "complexity_team_spawns_total",
            "Total team spawns by size",
            ["team_size", "trigger_reason"]
        )

        self.team_spawn_rate = Gauge(
            "complexity_team_spawn_rate",
            "Team spawn rate per minute",
            []
        )

        # Success rate metrics
        self.success_rate_by_team_size = Gauge(
            "complexity_success_rate_by_team_size",
            "Task success rate by team size",
            ["team_size", "complexity_bucket"]
        )

        # Latency metrics
        self.classification_latency_ms = Histogram(
            "complexity_classification_latency_ms",
            "Time to classify complexity",
            [],
            buckets=[10, 50, 100, 250, 500, 1000, 2500]
        )

        self.task_latency_by_bucket = Histogram(
            "complexity_task_latency_minutes",
            "Task completion time by complexity",
            ["bucket"],
            buckets=[1, 5, 15, 30, 60, 120, 240]
        )

        # Drift metrics
        self.feature_drift_score = Gauge(
            "complexity_feature_drift_score",
            "Feature drift detection score",
            ["feature_name"]
        )

        self.prediction_drift_score = Gauge(
            "complexity_prediction_drift_score",
            "Prediction drift score",
            []
        )

        # Register all metrics
        for metric in [
            self.classifications_total,
            self.classification_confidence,
            self.classification_accuracy,
            self.misclassifications_total,
            self.token_efficiency_ratio,
            self.cost_variance_percent,
            self.team_spawns_total,
            self.team_spawn_rate,
            self.success_rate_by_team_size,
            self.classification_latency_ms,
            self.task_latency_by_bucket,
            self.feature_drift_score,
            self.prediction_drift_score,
        ]:
            self.registry.register(metric)
```

### 6.2 Alert Manager Integration

```python
class ComplexityAlertManager:
    """
    Alert manager for complexity scoring system.
    Integrates with existing AlertManager in monitoring.py.
    """

    def __init__(
        self,
        base_alert_manager: AlertManager,
        neo4j_client: OperationalMemory
    ):
        self.base_alerts = base_alert_manager
        self.neo4j = neo4j_client

    async def check_complexity_alerts(self) -> List[Alert]:
        """
        Run all complexity-specific alert checks.
        """
        alerts = []

        alerts.extend(await self._check_classification_accuracy())
        alerts.extend(await self._check_cost_efficiency())
        alerts.extend(await self._check_team_spawn_rate())
        alerts.extend(await self._check_misclassification_rate())
        alerts.extend(await self._check_concept_drift())

        return alerts

    async def _check_classification_accuracy(self) -> List[Alert]:
        """Check if classification accuracy is below threshold."""
        query = """
        MATCH (c:ComplexityClassification)-[:RESULTED_IN]->(t:TeamTask)
        MATCH (t)-[:HAS_OUTCOME]->(o:TaskOutcome)
        WHERE c.created_at > datetime() - duration('PT1H')
        WITH c.complexity_bucket as bucket,
             count(*) as total,
             count(CASE WHEN c.complexity_bucket = o.actual_bucket THEN 1 END) as correct
        WITH bucket,
             total,
             correct,
             correct / toFloat(total) as accuracy
        WHERE total >= 10 AND accuracy < 0.85
        RETURN bucket, accuracy, total
        """

        results = await self.neo4j.run(query)
        alerts = []

        for row in results:
            alert = Alert(
                alert_name=f"LowClassificationAccuracy_{row['bucket']}",
                severity="warning",
                summary=f"Low classification accuracy for {row['bucket']} bucket",
                description=f"Accuracy is {row['accuracy']:.1%} (target: 85%)",
                labels={"bucket": row["bucket"], "accuracy": f"{row['accuracy']:.2f}"}
            )
            alerts.append(alert)

        return alerts

    async def _check_cost_efficiency(self) -> List[Alert]:
        """Check if costs are exceeding estimates."""
        query = """
        MATCH (c:ComplexityClassification)-[:RESULTED_IN]->(t:TeamTask)
        MATCH (t)-[:HAS_COST]->(tc:TaskCost)
        WHERE t.created_at > datetime() - duration('PT1H')
        WITH c.complexity_bucket as bucket,
             avg(tc.actual_cost / tc.estimated_cost) as efficiency
        WHERE efficiency > 1.5
        RETURN bucket, efficiency
        """

        results = await self.neo4j.run(query)
        alerts = []

        for row in results:
            alert = Alert(
                alert_name=f"CostThresholdExceeded_{row['bucket']}",
                severity="warning",
                summary=f"Cost overruns in {row['bucket']} complexity bucket",
                description=f"Actual costs are {row['efficiency']:.1f}x estimates",
                labels={"bucket": row["bucket"], "efficiency": f"{row['efficiency']:.2f}"}
            )
            alerts.append(alert)

        return alerts
```

---

## 7. Implementation Roadmap

### Phase 1: Basic Metrics (Week 1)
- [ ] Implement core Neo4j schema for classification tracking
- [ ] Add Prometheus metrics to complexity classifier
- [ ] Create basic dashboard with real-time distribution
- [ ] Implement classification accuracy queries

### Phase 2: Alerting (Week 2)
- [ ] Implement all 5 alert rules
- [ ] Integrate with existing AlertManager
- [ ] Set up notification channels (Slack, PagerDuty)
- [ ] Create alert runbook documentation

### Phase 3: Feedback Loop (Week 3)
- [ ] Implement ground truth capture system
- [ ] Build post-hoc complexity analysis
- [ ] Create threshold adjustment engine
- [ ] Add user override UI/API

### Phase 4: Advanced Analytics (Week 4)
- [ ] Implement concept drift detection
- [ ] Build automated retraining pipeline
- [ ] Create cost optimization recommendations
- [ ] Add predictive capacity planning

---

## 8. Summary

| Component | Status | File Location |
|-----------|--------|---------------|
| Metric Definitions | Designed | This document |
| Neo4j Schema | Designed | This document, Section 5 |
| Dashboard Wireframes | Designed | This document, Section 2 |
| Alerting Rules | Designed | This document, Section 3 |
| Feedback Loop | Designed | This document, Section 4 |
| Prometheus Integration | Specified | This document, Section 6 |
| Implementation | Pending | `tools/kurultai/complexity_monitoring.py` |

---

*End of Document*
