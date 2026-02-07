# Complexity Scoring Validation Framework

## Overview

This document provides a comprehensive validation framework for the `TeamSizeClassifier` used in Kurultai's agent teams integration. The classifier determines team size based on capability complexity:

- **< 0.6**: Individual agent (simple)
- **0.6 - 0.8**: Small team (3 agents)
- **> 0.8**: Full team (5 agents)

---

## 1. Test Case Design

### 1.1 Test Case Categories

We define 30 test cases across 5 capability domains, complexity ranges, and edge cases.

#### COMMUNICATION Domain (6 cases)

| ID | Capability Request | Expected Complexity | Expected Team | Rationale |
|----|-------------------|---------------------|---------------|-----------|
| C1 | "Send a simple Slack message" | 0.25 | Individual | Single API call, no auth complexity |
| C2 | "Post to Twitter with rate limiting" | 0.45 | Individual | Simple API with basic error handling |
| C3 | "Send email with attachments" | 0.55 | Individual | File handling adds slight complexity |
| C4 | **EDGE**: "Integrate Discord bot with slash commands" | 0.60 | Small Team | Borderline: WebSocket + command parsing |
| C5 | "Build real-time chat with WebSocket" | 0.72 | Small Team | Stateful connection, message queuing |
| C6 | **EDGE**: "Multi-channel notification system with fallbacks" | 0.80 | Small Team | Borderline: Multiple providers, retry logic |

#### DATA Domain (6 cases)

| ID | Capability Request | Expected Complexity | Expected Team | Rationale |
|----|-------------------|---------------------|---------------|-----------|
| D1 | "Parse CSV file" | 0.20 | Individual | Standard library, no external deps |
| D2 | "Query PostgreSQL database" | 0.40 | Individual | Single connection, simple queries |
| D3 | "Sync data between two APIs" | 0.58 | Individual | Bidirectional sync, conflict detection |
| D4 | **EDGE**: "ETL pipeline with data validation" | 0.60 | Small Team | Borderline: Multi-stage, schema validation |
| D5 | "Real-time data streaming with Kafka" | 0.75 | Small Team | Distributed system, consumer groups |
| D6 | **EDGE**: "Data warehouse with incremental loads" | 0.80 | Small Team | Borderline: Complex orchestration, CDC |

#### INFRASTRUCTURE Domain (6 cases)

| ID | Capability Request | Expected Complexity | Expected Team | Rationale |
|----|-------------------|---------------------|---------------|-----------|
| I1 | "Check disk space" | 0.15 | Individual | System call, no network |
| I2 | "Deploy Docker container" | 0.35 | Individual | Single container, basic config |
| I3 | "Set up nginx reverse proxy" | 0.55 | Individual | Config file generation, SSL |
| I4 | **EDGE**: "Kubernetes deployment with health checks" | 0.60 | Small Team | Borderline: Multi-resource, probes |
| I5 | "Auto-scaling group with custom metrics" | 0.78 | Small Team | Cloud APIs, metric aggregation |
| I6 | **EDGE**: "Multi-region deployment with failover" | 0.80 | Small Team | Borderline: DNS, health checks, sync |

#### AUTOMATION Domain (6 cases)

| ID | Capability Request | Expected Complexity | Expected Team | Rationale |
|----|-------------------|---------------------|---------------|-----------|
| A1 | "Schedule a cron job" | 0.20 | Individual | Time-based trigger, local execution |
| A2 | "Automate file backups" | 0.38 | Individual | File operations, compression |
| A3 | "GitHub Actions workflow" | 0.52 | Individual | YAML generation, basic triggers |
| A4 | **EDGE**: "CI/CD pipeline with approval gates" | 0.60 | Small Team | Borderline: Multi-stage, human-in-loop |
| A5 | "End-to-end test automation with reporting" | 0.73 | Small Team | Test orchestration, result aggregation |
| A6 | **EDGE**: "Self-healing infrastructure automation" | 0.80 | Small Team | Borderline: Monitoring, remediation loops |

#### INTELLIGENCE Domain (6 cases)

| ID | Capability Request | Expected Complexity | Expected Team | Rationale |
|----|-------------------|---------------------|---------------|-----------|
| N1 | "Simple text classification" | 0.30 | Individual | Pre-trained model, single inference |
| N2 | "Sentiment analysis API" | 0.42 | Individual | External API integration |
| N3 | "Document OCR with preprocessing" | 0.56 | Individual | Image processing, text extraction |
| N4 | **EDGE**: "Named entity recognition with custom training" | 0.60 | Small Team | Borderline: Model fine-tuning, data prep |
| N5 | "Multi-modal RAG system" | 0.76 | Small Team | Vector DB, embeddings, retrieval |
| N6 | **EDGE**: "Autonomous agent with tool use" | 0.80 | Small Team | Borderline: Planning, execution loops |

### 1.2 Edge Case Specifications

#### Borderline 0.6 Cases (Team Threshold)

```python
BORDERLINE_06_CASES = [
    {
        "id": "B06-1",
        "request": "Integrate Discord bot with slash commands",
        "factors": {
            "domain_risk": 0.4,      # Medium: Real-time WebSocket
            "api_count": 0.5,        # Medium: Discord API + Gateway
            "integration_points": 0.7,  # High: Event handlers, commands
            "security_sensitivity": 0.4   # Medium: Bot token management
        },
        "expected_complexity": 0.60,
        "classification": "small_team"
    },
    {
        "id": "B06-2",
        "request": "ETL pipeline with data validation",
        "factors": {
            "domain_risk": 0.5,      # Medium: Data integrity critical
            "api_count": 0.6,        # Medium: Source + target APIs
            "integration_points": 0.6,  # Medium: Transform stages
            "security_sensitivity": 0.3   # Low-Medium: PII handling
        },
        "expected_complexity": 0.60,
        "classification": "small_team"
    },
    {
        "id": "B06-3",
        "request": "Kubernetes deployment with health checks",
        "factors": {
            "domain_risk": 0.6,      # Medium-High: Production critical
            "api_count": 0.5,        # Medium: K8s API
            "integration_points": 0.6,  # Medium: Multiple resources
            "security_sensitivity": 0.4   # Medium: RBAC, secrets
        },
        "expected_complexity": 0.60,
        "classification": "small_team"
    }
]
```

#### Borderline 0.8 Cases (Full Team Threshold)

```python
BORDERLINE_08_CASES = [
    {
        "id": "B08-1",
        "request": "Multi-channel notification system with fallbacks",
        "factors": {
            "domain_risk": 0.7,      # High: Critical alerts
            "api_count": 0.8,        # High: 3+ provider APIs
            "integration_points": 0.9,  # High: Circuit breakers, retries
            "security_sensitivity": 0.6   # Medium-High: API keys
        },
        "expected_complexity": 0.80,
        "classification": "full_team"
    },
    {
        "id": "B08-2",
        "request": "Data warehouse with incremental loads",
        "factors": {
            "domain_risk": 0.8,      # High: Business critical data
            "api_count": 0.7,        # Medium-High: Multiple sources
            "integration_points": 0.9,  # High: CDC, transformations
            "security_sensitivity": 0.7   # High: Sensitive data
        },
        "expected_complexity": 0.80,
        "classification": "full_team"
    },
    {
        "id": "B08-3",
        "request": "Autonomous agent with tool use",
        "factors": {
            "domain_risk": 0.7,      # High: Unpredictable behavior
            "api_count": 0.6,        # Medium: Multiple tool APIs
            "integration_points": 0.95, # Very High: Planning, execution
            "security_sensitivity": 0.8   # High: Sandboxing required
        },
        "expected_complexity": 0.80,
        "classification": "full_team"
    }
]
```

### 1.3 Known Simple vs Complex Reference Cases

```python
REFERENCE_CASES = {
    "simple_benchmarks": [
        {"request": "Hello world HTTP endpoint", "complexity": 0.10},
        {"request": "Read environment variable", "complexity": 0.05},
        {"request": "Log message to console", "complexity": 0.05},
        {"request": "Parse JSON string", "complexity": 0.15},
        {"request": "Make GET request", "complexity": 0.20},
    ],
    "complex_benchmarks": [
        {"request": "Distributed transaction coordinator", "complexity": 0.95},
        {"request": "Byzantine fault-tolerant consensus", "complexity": 0.98},
        {"request": "Real-time ML inference pipeline", "complexity": 0.92},
        {"request": "Multi-tenant SaaS platform", "complexity": 0.90},
        {"request": "Zero-knowledge proof system", "complexity": 0.97},
    ]
}
```

---

## 2. Validation Metrics

### 2.1 Core Metrics

```python
from dataclasses import dataclass
from typing import List, Dict
from enum import Enum

class TeamSize(Enum):
    INDIVIDUAL = "individual"      # < 0.6
    SMALL_TEAM = "small"           # 0.6 - 0.8
    FULL_TEAM = "full"             # > 0.8

@dataclass
class ClassificationResult:
    test_id: str
    request: str
    predicted_complexity: float
    predicted_team: TeamSize
    actual_complexity: float      # From human expert or outcome
    actual_team: TeamSize         # Optimal team size from results

    @property
    def correct(self) -> bool:
        return self.predicted_team == self.actual_team

    @property
    def complexity_error(self) -> float:
        return abs(self.predicted_complexity - self.actual_complexity)

@dataclass
class ValidationMetrics:
    """Comprehensive validation metrics for complexity classifier."""

    # Accuracy
    total_cases: int
    correct_classifications: int
    accuracy: float

    # Precision by team size
    individual_precision: float   # TP / (TP + FP) for individual
    small_team_precision: float   # TP / (TP + FP) for small team
    full_team_precision: float    # TP / (TP + FP) for full team

    # Recall by team size
    individual_recall: float      # TP / (TP + FN) for individual
    small_team_recall: float      # TP / (TP + FN) for small team
    full_team_recall: float       # TP / (TP + FN) for full team

    # F1 Scores
    individual_f1: float
    small_team_f1: float
    full_team_f1: float
    macro_f1: float

    # Complexity calibration
    mean_absolute_error: float
    root_mean_squared_error: float

    # Cost efficiency
    avg_tokens_per_task: float
    cost_vs_complexity_correlation: float

    # Edge case performance
    borderline_accuracy: float    # Accuracy on 0.55-0.65 and 0.75-0.85 cases

    def to_dict(self) -> Dict:
        return {
            "accuracy": self.accuracy,
            "precision": {
                "individual": self.individual_precision,
                "small_team": self.small_team_precision,
                "full_team": self.full_team_precision,
            },
            "recall": {
                "individual": self.individual_recall,
                "small_team": self.small_team_recall,
                "full_team": self.full_team_recall,
            },
            "f1": {
                "individual": self.individual_f1,
                "small_team": self.small_team_f1,
                "full_team": self.full_team_f1,
                "macro": self.macro_f1,
            },
            "complexity_error": {
                "mae": self.mean_absolute_error,
                "rmse": self.root_mean_squared_error,
            },
            "cost_efficiency": {
                "avg_tokens": self.avg_tokens_per_task,
                "cost_correlation": self.cost_vs_complexity_correlation,
            },
            "edge_cases": {
                "borderline_accuracy": self.borderline_accuracy,
            }
        }
```

### 2.2 Metric Thresholds

```python
VALIDATION_THRESHOLDS = {
    "production_ready": {
        "accuracy": 0.85,           # Overall accuracy must be > 85%
        "individual_precision": 0.90,  # Don't waste teams on simple tasks
        "full_team_recall": 0.95,      # Don't miss complex tasks
        "borderline_accuracy": 0.70,   # Edge cases can be harder
        "mae": 0.10,                   # Complexity prediction within 0.1
    },
    "acceptable": {
        "accuracy": 0.75,
        "individual_precision": 0.80,
        "full_team_recall": 0.90,
        "borderline_accuracy": 0.60,
        "mae": 0.15,
    },
    "minimum_viable": {
        "accuracy": 0.65,
        "individual_precision": 0.70,
        "full_team_recall": 0.85,
        "borderline_accuracy": 0.50,
        "mae": 0.20,
    }
}
```

---

## 3. Validation Pipeline Design

### 3.1 Pipeline Architecture

```python
"""
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COMPLEXITY VALIDATION PIPELINE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐                │
│  │ Test Case    │────▶│ Classifier   │────▶│ Team         │                │
│  │ Loader       │     │ Execution    │     │ Simulation   │                │
│  └──────────────┘     └──────────────┘     └──────┬───────┘                │
│         │                                         │                         │
│         │                                         ▼                         │
│         │                                ┌──────────────┐                  │
│         │                                │ Outcome      │                  │
│         │                                │ Measurement  │                  │
│         │                                └──────┬───────┘                  │
│         │                                       │                           │
│         ▼                                       ▼                           │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐                │
│  │ Ground Truth │◄────│ Metrics      │◄────│ Results      │                │
│  │ Comparison   │     │ Calculation  │     │ Aggregation  │                │
│  └──────┬───────┘     └──────────────┘     └──────────────┘                │
│         │                                                                   │
│         ▼                                                                   │
│  ┌──────────────┐     ┌──────────────┐                                     │
│  │ Threshold    │────▶│ Report       │                                     │
│  │ Evaluation   │     │ Generation   │                                     │
│  └──────────────┘     └──────────────┘                                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
"""
```

### 3.2 Pipeline Implementation

```python
import asyncio
from typing import List, Dict, Optional
from dataclasses import dataclass
import json
from datetime import datetime

class ComplexityValidationPipeline:
    """
    End-to-end validation pipeline for TeamSizeClassifier.
    """

    def __init__(
        self,
        classifier: "TeamSizeClassifier",
        test_cases: List[Dict],
        team_simulator: "TeamSimulator",
        metrics_calculator: "MetricsCalculator"
    ):
        self.classifier = classifier
        self.test_cases = test_cases
        self.team_simulator = team_simulator
        self.metrics_calculator = metrics_calculator
        self.results: List[ClassificationResult] = []

    async def run_validation(
        self,
        environment: str = "staging",
        parallel_executions: int = 5
    ) -> ValidationReport:
        """
        Run full validation pipeline.

        Args:
            environment: 'local', 'staging', or 'production'
            parallel_executions: Number of parallel test executions
        """
        print(f"Starting validation in {environment} environment...")
        print(f"Test cases: {len(self.test_cases)}")

        # Phase 1: Execute classifications
        classification_tasks = [
            self._classify_and_simulate(test_case)
            for test_case in self.test_cases
        ]

        # Run with semaphore for rate limiting
        semaphore = asyncio.Semaphore(parallel_executions)

        async def execute_with_limit(task):
            async with semaphore:
                return await task

        self.results = await asyncio.gather(*[
            execute_with_limit(task) for task in classification_tasks
        ])

        # Phase 2: Calculate metrics
        metrics = self.metrics_calculator.calculate(self.results)

        # Phase 3: Evaluate against thresholds
        threshold_evaluation = self._evaluate_thresholds(metrics)

        # Phase 4: Generate report
        report = ValidationReport(
            timestamp=datetime.utcnow(),
            environment=environment,
            metrics=metrics,
            threshold_evaluation=threshold_evaluation,
            results=self.results,
            recommendations=self._generate_recommendations(metrics, threshold_evaluation)
        )

        return report

    async def _classify_and_simulate(
        self,
        test_case: Dict
    ) -> ClassificationResult:
        """Classify a test case and simulate team execution."""

        # Step 1: Get classifier prediction
        prediction = self.classifier.classify(test_case["request"])
        predicted_complexity = prediction.complexity
        predicted_team = self._complexity_to_team(predicted_complexity)

        # Step 2: Simulate team execution
        simulation_result = await self.team_simulator.simulate(
            request=test_case["request"],
            team_size=predicted_team,
            expected_complexity=test_case.get("expected_complexity", 0.5)
        )

        # Step 3: Determine actual optimal team from simulation
        actual_team = simulation_result.optimal_team_size
        actual_complexity = simulation_result.measured_complexity

        return ClassificationResult(
            test_id=test_case.get("id", "unknown"),
            request=test_case["request"],
            predicted_complexity=predicted_complexity,
            predicted_team=predicted_team,
            actual_complexity=actual_complexity,
            actual_team=actual_team
        )

    def _complexity_to_team(self, complexity: float) -> TeamSize:
        """Convert complexity score to team size."""
        if complexity < 0.6:
            return TeamSize.INDIVIDUAL
        elif complexity < 0.8:
            return TeamSize.SMALL_TEAM
        else:
            return TeamSize.FULL_TEAM

    def _evaluate_thresholds(self, metrics: ValidationMetrics) -> Dict:
        """Evaluate metrics against production thresholds."""
        thresholds = VALIDATION_THRESHOLDS["production_ready"]

        return {
            "passed": all([
                metrics.accuracy >= thresholds["accuracy"],
                metrics.individual_precision >= thresholds["individual_precision"],
                metrics.full_team_recall >= thresholds["full_team_recall"],
                metrics.borderline_accuracy >= thresholds["borderline_accuracy"],
                metrics.mean_absolute_error <= thresholds["mae"],
            ]),
            "checks": {
                "accuracy": {
                    "value": metrics.accuracy,
                    "threshold": thresholds["accuracy"],
                    "passed": metrics.accuracy >= thresholds["accuracy"]
                },
                "individual_precision": {
                    "value": metrics.individual_precision,
                    "threshold": thresholds["individual_precision"],
                    "passed": metrics.individual_precision >= thresholds["individual_precision"]
                },
                "full_team_recall": {
                    "value": metrics.full_team_recall,
                    "threshold": thresholds["full_team_recall"],
                    "passed": metrics.full_team_recall >= thresholds["full_team_recall"]
                },
                "borderline_accuracy": {
                    "value": metrics.borderline_accuracy,
                    "threshold": thresholds["borderline_accuracy"],
                    "passed": metrics.borderline_accuracy >= thresholds["borderline_accuracy"]
                },
                "mae": {
                    "value": metrics.mean_absolute_error,
                    "threshold": thresholds["mae"],
                    "passed": metrics.mean_absolute_error <= thresholds["mae"]
                },
            }
        }

    def _generate_recommendations(
        self,
        metrics: ValidationMetrics,
        threshold_eval: Dict
    ) -> List[str]:
        """Generate calibration recommendations."""
        recommendations = []

        # Check for threshold drift
        if not threshold_eval["checks"]["accuracy"]["passed"]:
            recommendations.append(
                "ACCURACY BELOW THRESHOLD: Consider retraining classifier with "
                "expanded training set or adjusting factor weights."
            )

        if not threshold_eval["checks"]["individual_precision"]["passed"]:
            recommendations.append(
                "LOW INDIVIDUAL PRECISION: Too many simple tasks getting teams. "
                "Consider raising threshold from 0.6 to 0.62-0.65."
            )

        if not threshold_eval["checks"]["full_team_recall"]["passed"]:
            recommendations.append(
                "LOW FULL TEAM RECALL: Complex tasks underperforming. "
                "Consider lowering threshold from 0.8 to 0.75-0.78."
            )

        if metrics.mean_absolute_error > 0.15:
            recommendations.append(
                "HIGH COMPLEXITY ERROR: Classifier predictions diverging from "
                "actual outcomes. Review factor calculation logic."
            )

        # Check for bias
        if metrics.small_team_precision < 0.7:
            recommendations.append(
                "SMALL TEAM CLASSIFICATION UNSTABLE: Consider adding more "
                "granularity to 0.6-0.8 range or merging with adjacent categories."
            )

        return recommendations


@dataclass
class ValidationReport:
    """Complete validation report."""
    timestamp: datetime
    environment: str
    metrics: ValidationMetrics
    threshold_evaluation: Dict
    results: List[ClassificationResult]
    recommendations: List[str]

    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps({
            "timestamp": self.timestamp.isoformat(),
            "environment": self.environment,
            "metrics": self.metrics.to_dict(),
            "threshold_evaluation": self.threshold_evaluation,
            "summary": {
                "total_cases": len(self.results),
                "correct": sum(1 for r in self.results if r.correct),
                "accuracy": self.metrics.accuracy,
                "passed": self.threshold_evaluation["passed"]
            },
            "recommendations": self.recommendations
        }, indent=2)
```

### 3.3 Team Simulator for Validation

```python
class TeamSimulator:
    """
    Simulates team execution to measure actual vs predicted complexity.

    This uses historical data and heuristics to estimate:
    1. What team size would have been optimal
    2. What the actual complexity was (based on outcomes)
    """

    def __init__(
        self,
        historical_data: Optional[List[Dict]] = None,
        llm_evaluator: Optional["LLMComplexityEvaluator"] = None
    ):
        self.historical_data = historical_data or []
        self.llm_evaluator = llm_evaluator

    async def simulate(
        self,
        request: str,
        team_size: TeamSize,
        expected_complexity: float
    ) -> "SimulationResult":
        """
        Simulate execution and determine optimal team size.

        Returns measured complexity and optimal team configuration.
        """

        # Method 1: Historical pattern matching
        historical_match = self._find_historical_match(request)
        if historical_match:
            return SimulationResult(
                measured_complexity=historical_match["actual_complexity"],
                optimal_team_size=historical_match["optimal_team"],
                confidence=0.8,
                method="historical_match"
            )

        # Method 2: LLM-based complexity evaluation
        if self.llm_evaluator:
            llm_result = await self.llm_evaluator.evaluate(request)
            return SimulationResult(
                measured_complexity=llm_result.complexity,
                optimal_team_size=self._complexity_to_team(llm_result.complexity),
                confidence=llm_result.confidence,
                method="llm_evaluation"
            )

        # Method 3: Factor-based estimation
        factor_complexity = self._estimate_from_factors(request)
        return SimulationResult(
            measured_complexity=factor_complexity,
            optimal_team_size=self._complexity_to_team(factor_complexity),
            confidence=0.6,
            method="factor_estimation"
        )

    def _find_historical_match(self, request: str) -> Optional[Dict]:
        """Find similar requests in historical data."""
        # Simple keyword matching - could use embeddings
        request_words = set(request.lower().split())

        best_match = None
        best_score = 0.0

        for record in self.historical_data:
            record_words = set(record["request"].lower().split())
            overlap = len(request_words & record_words)
            score = overlap / max(len(request_words), len(record_words))

            if score > 0.7 and score > best_score:  # 70% similarity threshold
                best_score = score
                best_match = record

        return best_match

    def _estimate_from_factors(self, request: str) -> float:
        """Estimate complexity from request characteristics."""
        # Heuristic factors
        factors = {
            "length": min(len(request) / 200, 1.0),  # Longer requests tend to be complex
            "technical_terms": self._count_technical_terms(request) / 10,
            "integration_indicators": self._count_integration_words(request) / 5,
            "security_keywords": self._count_security_words(request) / 3,
        }

        # Weighted average
        weights = {"length": 0.2, "technical_terms": 0.3,
                   "integration_indicators": 0.3, "security_keywords": 0.2}

        complexity = sum(factors[k] * weights[k] for k in factors)
        return min(max(complexity, 0.0), 1.0)  # Clamp to [0, 1]

    def _count_technical_terms(self, request: str) -> int:
        """Count technical complexity indicators."""
        terms = [
            "api", "database", "websocket", "microservice", "kubernetes",
            "distributed", "async", "queue", "cache", "authentication",
            "authorization", "encryption", "pipeline", "orchestration"
        ]
        return sum(1 for term in terms if term in request.lower())

    def _count_integration_words(self, request: str) -> int:
        """Count integration complexity indicators."""
        words = [
            "integrate", "connect", "sync", "bridge", "middleware",
            "adapter", "webhook", "callback", "event", "stream"
        ]
        return sum(1 for word in words if word in request.lower())

    def _count_security_words(self, request: str) -> int:
        """Count security sensitivity indicators."""
        words = [
            "auth", "oauth", "sso", "mfa", "encrypt", "hash",
            "token", "credential", "secret", "permission", "rbac"
        ]
        return sum(1 for word in words if word in request.lower())

    def _complexity_to_team(self, complexity: float) -> TeamSize:
        if complexity < 0.6:
            return TeamSize.INDIVIDUAL
        elif complexity < 0.8:
            return TeamSize.SMALL_TEAM
        else:
            return TeamSize.FULL_TEAM


@dataclass
class SimulationResult:
    measured_complexity: float
    optimal_team_size: TeamSize
    confidence: float
    method: str
```

---

## 4. Calibration Strategy

### 4.1 Threshold Calibration

```python
class ThresholdCalibrator:
    """
    Calibrate complexity thresholds based on validation results.
    """

    def __init__(
        self,
        lower_threshold: float = 0.6,
        upper_threshold: float = 0.8,
        step_size: float = 0.02
    ):
        self.lower = lower_threshold
        self.upper = upper_threshold
        self.step_size = step_size

    def calibrate(
        self,
        results: List[ClassificationResult],
        target_precision: float = 0.90,
        target_recall: float = 0.95
    ) -> "CalibrationResult":
        """
        Find optimal thresholds based on validation results.

        Strategy:
        - If too many simple tasks get teams → raise lower threshold
        - If complex tasks underperform → lower upper threshold
        """

        best_config = None
        best_score = -1

        # Grid search over threshold combinations
        for lower in self._generate_threshold_range(0.5, 0.7):
            for upper in self._generate_threshold_range(0.7, 0.9):
                if upper <= lower:
                    continue

                score = self._evaluate_thresholds(results, lower, upper)

                if score > best_score:
                    best_score = score
                    best_config = (lower, upper)

        return CalibrationResult(
            optimal_lower=best_config[0],
            optimal_upper=best_config[1],
            score=best_score,
            recommendations=self._generate_recommendations(best_config, results)
        )

    def _generate_threshold_range(self, start: float, end: float) -> List[float]:
        """Generate threshold values to test."""
        values = []
        current = start
        while current <= end:
            values.append(round(current, 2))
            current += self.step_size
        return values

    def _evaluate_thresholds(
        self,
        results: List[ClassificationResult],
        lower: float,
        upper: float
    ) -> float:
        """Evaluate a threshold configuration."""

        # Re-classify results with new thresholds
        reclassified = []
        for r in results:
            predicted = self._classify_with_thresholds(
                r.predicted_complexity, lower, upper
            )
            reclassified.append({
                "predicted": predicted,
                "actual": r.actual_team
            })

        # Calculate metrics
        correct = sum(1 for r in reclassified if r["predicted"] == r["actual"])
        accuracy = correct / len(reclassified)

        # Penalize misclassification of complex tasks (high cost)
        false_negatives = sum(
            1 for r in reclassified
            if r["actual"] == TeamSize.FULL_TEAM
            and r["predicted"] != TeamSize.FULL_TEAM
        )
        fn_penalty = false_negatives * 0.5  # Heavy penalty

        # Penalize over-allocation to simple tasks (inefficiency)
        false_positives = sum(
            1 for r in reclassified
            if r["actual"] == TeamSize.INDIVIDUAL
            and r["predicted"] != TeamSize.INDIVIDUAL
        )
        fp_penalty = false_positives * 0.2  # Moderate penalty

        return accuracy - fn_penalty - fp_penalty

    def _classify_with_thresholds(
        self,
        complexity: float,
        lower: float,
        upper: float
    ) -> TeamSize:
        """Classify using custom thresholds."""
        if complexity < lower:
            return TeamSize.INDIVIDUAL
        elif complexity < upper:
            return TeamSize.SMALL_TEAM
        else:
            return TeamSize.FULL_TEAM

    def _generate_recommendations(
        self,
        config: Tuple[float, float],
        results: List[ClassificationResult]
    ) -> List[str]:
        """Generate calibration recommendations."""
        lower, upper = config
        recommendations = []

        if lower > 0.6:
            recommendations.append(
                f"RAISE lower threshold from 0.6 to {lower:.2f} to improve "
                "individual precision and reduce team over-allocation."
            )
        elif lower < 0.6:
            recommendations.append(
                f"LOWER lower threshold from 0.6 to {lower:.2f} to improve "
                "recall for moderate-complexity tasks."
            )

        if upper < 0.8:
            recommendations.append(
                f"LOWER upper threshold from 0.8 to {upper:.2f} to ensure "
                "complex tasks get full team resources."
            )
        elif upper > 0.8:
            recommendations.append(
                f"RAISE upper threshold from 0.8 to {upper:.2f} to reduce "
                "unnecessary full team allocation."
            )

        return recommendations


@dataclass
class CalibrationResult:
    optimal_lower: float
    optimal_upper: float
    score: float
    recommendations: List[str]
```

### 4.2 A/B Testing Framework

```python
class ABTestFramework:
    """
    A/B testing for threshold configurations in production.
    """

    def __init__(
        self,
        neo4j_client: "Neo4jClient",
        traffic_split: float = 0.1  # 10% to variant
    ):
        self.neo4j = neo4j_client
        self.traffic_split = traffic_split

    def assign_variant(self, request_id: str) -> str:
        """
        Assign request to control or variant group.

        Uses deterministic hashing for consistent assignment.
        """
        import hashlib

        hash_val = int(hashlib.md5(request_id.encode()).hexdigest(), 16)
        if hash_val % 100 < (self.traffic_split * 100):
            return "variant"
        return "control"

    async def log_classification(
        self,
        request_id: str,
        variant: str,
        request: str,
        predicted_complexity: float,
        predicted_team: TeamSize,
        thresholds: Tuple[float, float]
    ):
        """Log classification for A/B test analysis."""

        query = """
        CREATE (c:ClassificationEvent {
            id: $request_id,
            variant: $variant,
            request: $request,
            predicted_complexity: $complexity,
            predicted_team: $team,
            lower_threshold: $lower,
            upper_threshold: $upper,
            timestamp: datetime()
        })
        """

        await self.neo4j.run(query,
            request_id=request_id,
            variant=variant,
            request=request,
            complexity=predicted_complexity,
            team=predicted_team.value,
            lower=thresholds[0],
            upper=thresholds[1]
        )

    async def log_outcome(
        self,
        request_id: str,
        success: bool,
        duration_seconds: float,
        token_usage: int,
        team_satisfaction: Optional[float] = None
    ):
        """Log outcome for A/B test analysis."""

        query = """
        MATCH (c:ClassificationEvent {id: $request_id})
        CREATE (o:Outcome {
            success: $success,
            duration_seconds: $duration,
            token_usage: $tokens,
            team_satisfaction: $satisfaction,
            timestamp: datetime()
        })
        CREATE (c)-[:RESULTED_IN]->(o)
        """

        await self.neo4j.run(query,
            request_id=request_id,
            success=success,
            duration=duration_seconds,
            tokens=token_usage,
            satisfaction=team_satisfaction
        )

    async def analyze_ab_test(
        self,
        control_thresholds: Tuple[float, float] = (0.6, 0.8),
        variant_thresholds: Tuple[float, float] = (0.62, 0.78),
        min_samples: int = 100
    ) -> "ABTestResult":
        """
        Analyze A/B test results.

        Compares control (current) vs variant (proposed) thresholds.
        """

        query = """
        MATCH (c:ClassificationEvent)-[:RESULTED_IN]->(o:Outcome)
        WHERE c.lower_threshold IN [$control_lower, $variant_lower]
        RETURN
            c.variant as variant,
            count(*) as n,
            avg(o.success) as success_rate,
            avg(o.duration_seconds) as avg_duration,
            avg(o.token_usage) as avg_tokens,
            percentileCont(o.duration_seconds, 0.95) as p95_duration
        """

        results = await self.neo4j.run(query,
            control_lower=control_thresholds[0],
            variant_lower=variant_thresholds[0]
        )

        control_stats = None
        variant_stats = None

        for record in results:
            if record["n"] < min_samples:
                continue

            stats = {
                "n": record["n"],
                "success_rate": record["success_rate"],
                "avg_duration": record["avg_duration"],
                "avg_tokens": record["avg_tokens"],
                "p95_duration": record["p95_duration"]
            }

            if record["variant"] == "control":
                control_stats = stats
            else:
                variant_stats = stats

        if not control_stats or not variant_stats:
            return ABTestResult(
                status="insufficient_data",
                recommendation="Continue test to gather more samples"
            )

        # Calculate improvements
        success_improvement = (
            variant_stats["success_rate"] - control_stats["success_rate"]
        ) / control_stats["success_rate"]

        duration_improvement = (
            control_stats["avg_duration"] - variant_stats["avg_duration"]
        ) / control_stats["avg_duration"]

        token_improvement = (
            control_stats["avg_tokens"] - variant_stats["avg_tokens"]
        ) / control_stats["avg_tokens"]

        # Determine winner
        if success_improvement > 0.05 and token_improvement > -0.1:
            winner = "variant"
            recommendation = (
                f"Adopt variant thresholds {variant_thresholds}. "
                f"Success rate improved by {success_improvement:.1%}, "
                f"tokens changed by {token_improvement:+.1%}"
            )
        elif success_improvement < -0.05:
            winner = "control"
            recommendation = (
                "Keep current thresholds. Variant shows significant "
                f"success rate degradation ({success_improvement:.1%})"
            )
        else:
            winner = "tie"
            recommendation = (
                "No significant difference. Consider extending test or "
                "testing more aggressive threshold changes."
            )

        return ABTestResult(
            status="complete",
            winner=winner,
            control_stats=control_stats,
            variant_stats=variant_stats,
            improvements={
                "success_rate": success_improvement,
                "duration": duration_improvement,
                "token_usage": token_improvement
            },
            recommendation=recommendation
        )


@dataclass
class ABTestResult:
    status: str
    winner: Optional[str] = None
    control_stats: Optional[Dict] = None
    variant_stats: Optional[Dict] = None
    improvements: Optional[Dict] = None
    recommendation: str = ""
```

---

## 5. Production Monitoring

### 5.1 Metrics to Track

```python
PRODUCTION_METRICS = {
    # Classification Quality
    "classification": {
        "accuracy_rolling_24h": {
            "description": "Rolling 24h accuracy vs human labels",
            "threshold": {"warning": 0.80, "critical": 0.70},
            "query": """
                MATCH (c:ClassificationEvent)-[:RESULTED_IN]->(o:Outcome)
                WHERE c.timestamp > datetime() - duration('P1D')
                RETURN avg(CASE WHEN c.predicted_team = o.actual_team THEN 1 ELSE 0 END) as accuracy
            """
        },
        "complexity_drift": {
            "description": "Distribution shift in complexity scores",
            "threshold": {"warning": 0.15, "critical": 0.25},  # KS statistic
            "query": """
                MATCH (c:ClassificationEvent)
                WHERE c.timestamp > datetime() - duration('P1D')
                RETURN c.predicted_complexity as complexity
            """
        },
        "borderline_rate": {
            "description": "Percentage of classifications near thresholds",
            "threshold": {"warning": 0.30, "critical": 0.40},
            "query": """
                MATCH (c:ClassificationEvent)
                WHERE c.timestamp > datetime() - duration('P1D')
                WITH c,
                     abs(c.predicted_complexity - 0.6) < 0.05 as near_lower,
                     abs(c.predicted_complexity - 0.8) < 0.05 as near_upper
                RETURN avg(CASE WHEN near_lower OR near_upper THEN 1.0 ELSE 0.0 END) as borderline_rate
            """
        }
    },

    # Team Performance
    "team_performance": {
        "individual_success_rate": {
            "description": "Success rate for individual agent tasks",
            "threshold": {"warning": 0.85, "critical": 0.75},
            "query": """
                MATCH (c:ClassificationEvent {predicted_team: 'individual'})-[:RESULTED_IN]->(o:Outcome)
                WHERE c.timestamp > datetime() - duration('P1D')
                RETURN avg(CASE WHEN o.success THEN 1.0 ELSE 0.0 END) as success_rate
            """
        },
        "small_team_success_rate": {
            "description": "Success rate for small team tasks",
            "threshold": {"warning": 0.88, "critical": 0.80},
            "query": """
                MATCH (c:ClassificationEvent {predicted_team: 'small'})-[:RESULTED_IN]->(o:Outcome)
                WHERE c.timestamp > datetime() - duration('P1D')
                RETURN avg(CASE WHEN o.success THEN 1.0 ELSE 0.0 END) as success_rate
            """
        },
        "full_team_success_rate": {
            "description": "Success rate for full team tasks",
            "threshold": {"warning": 0.90, "critical": 0.85},
            "query": """
                MATCH (c:ClassificationEvent {predicted_team: 'full'})-[:RESULTED_IN]->(o:Outcome)
                WHERE c.timestamp > datetime() - duration('P1D')
                RETURN avg(CASE WHEN o.success THEN 1.0 ELSE 0.0 END) as success_rate
            """
        }
    },

    # Cost Efficiency
    "cost_efficiency": {
        "avg_tokens_by_team_size": {
            "description": "Average token usage per team size",
            "threshold": None,  # Informational
            "query": """
                MATCH (c:ClassificationEvent)-[:RESULTED_IN]->(o:Outcome)
                WHERE c.timestamp > datetime() - duration('P1D')
                RETURN c.predicted_team as team_size, avg(o.token_usage) as avg_tokens
            """
        },
        "cost_per_successful_task": {
            "description": "Token cost normalized by success",
            "threshold": {"warning": 50000, "critical": 100000},
            "query": """
                MATCH (c:ClassificationEvent)-[:RESULTED_IN]->(o:Outcome)
                WHERE c.timestamp > datetime() - duration('P1D') AND o.success
                RETURN avg(o.token_usage) as cost_per_success
            """
        }
    },

    # Misclassification Patterns
    "misclassification": {
        "false_positive_rate": {
            "description": "Simple tasks getting teams (inefficiency)",
            "threshold": {"warning": 0.20, "critical": 0.30},
            "query": """
                MATCH (c:ClassificationEvent)-[:RESULTED_IN]->(o:Outcome)
                WHERE c.timestamp > datetime() - duration('P1D')
                  AND c.predicted_team != 'individual'
                  AND o.actual_team = 'individual'
                RETURN count(*) as false_positives
            """
        },
        "false_negative_rate": {
            "description": "Complex tasks not getting teams (risk)",
            "threshold": {"warning": 0.05, "critical": 0.10},
            "query": """
                MATCH (c:ClassificationEvent)-[:RESULTED_IN]->(o:Outcome)
                WHERE c.timestamp > datetime() - duration('P1D')
                  AND c.predicted_team = 'individual'
                  AND o.actual_team = 'full'
                RETURN count(*) as false_negatives
            """
        }
    }
}
```

### 5.2 Alerting Rules

```python
ALERTING_RULES = [
    {
        "name": "classification_accuracy_drop",
        "condition": "accuracy_rolling_24h < 0.75",
        "severity": "critical",
        "message": "Classification accuracy dropped below 75%. Immediate review required.",
        "actions": ["page_oncall", "create_incident"]
    },
    {
        "name": "high_false_negative_rate",
        "condition": "false_negative_rate > 0.08",
        "severity": "critical",
        "message": "Complex tasks being under-resourced. Risk of failures.",
        "actions": ["page_oncall", "trigger_threshold_review"]
    },
    {
        "name": "complexity_distribution_drift",
        "condition": "complexity_drift > 0.20",
        "severity": "warning",
        "message": "Significant distribution shift in task complexity. Model may need retraining.",
        "actions": ["notify_ml_team", "schedule_review"]
    },
    {
        "name": "high_borderline_rate",
        "condition": "borderline_rate > 0.35",
        "severity": "warning",
        "message": "Many classifications near thresholds. Consider threshold adjustment.",
        "actions": ["notify_product", "suggest_ab_test"]
    },
    {
        "name": "full_team_underperforming",
        "condition": "full_team_success_rate < 0.85",
        "severity": "warning",
        "message": "Full teams not achieving expected success rate. Review team composition.",
        "actions": ["notify_team_leads", "analyze_failures"]
    }
]
```

### 5.3 Feedback Loop Implementation

```python
class FeedbackLoop:
    """
    Continuous improvement through outcome feedback.
    """

    def __init__(
        self,
        neo4j_client: "Neo4jClient",
        classifier: "TeamSizeClassifier",
        calibrator: ThresholdCalibrator
    ):
        self.neo4j = neo4j_client
        self.classifier = classifier
        self.calibrator = calibrator

    async def collect_feedback(
        self,
        request_id: str,
        actual_outcome: Dict
    ):
        """Collect outcome feedback for a classification."""

        query = """
        MATCH (c:ClassificationEvent {id: $request_id})
        CREATE (f:Feedback {
            actual_complexity: $actual_complexity,
            actual_team_size: $actual_team,
            success: $success,
            user_satisfaction: $satisfaction,
            notes: $notes,
            timestamp: datetime()
        })
        CREATE (c)-[:RECEIVED_FEEDBACK]->(f)
        """

        await self.neo4j.run(query,
            request_id=request_id,
            actual_complexity=actual_outcome.get("complexity"),
            actual_team=actual_outcome.get("team_size"),
            success=actual_outcome.get("success"),
            satisfaction=actual_outcome.get("satisfaction"),
            notes=actual_outcome.get("notes", "")
        )

    async def analyze_feedback_batch(
        self,
        since: datetime,
        min_samples: int = 50
    ) -> "FeedbackAnalysis":
        """
        Analyze recent feedback for improvement opportunities.
        """

        query = """
        MATCH (c:ClassificationEvent)-[:RECEIVED_FEEDBACK]->(f)
        WHERE f.timestamp > $since
        RETURN
            c.predicted_complexity as predicted,
            f.actual_complexity as actual,
            c.predicted_team as predicted_team,
            f.actual_team_size as actual_team,
            f.success as success
        """

        results = await self.neo4j.run(query, since=since)

        if len(results) < min_samples:
            return FeedbackAnalysis(
                status="insufficient_data",
                message=f"Only {len(results)} feedback samples available"
            )

        # Calculate bias by complexity range
        bias_analysis = self._analyze_bias(results)

        # Identify systematic errors
        systematic_errors = self._identify_systematic_errors(results)

        # Recommend actions
        recommendations = self._generate_feedback_recommendations(
            bias_analysis, systematic_errors
        )

        return FeedbackAnalysis(
            status="complete",
            sample_size=len(results),
            bias_analysis=bias_analysis,
            systematic_errors=systematic_errors,
            recommendations=recommendations
        )

    def _analyze_bias(self, results: List[Dict]) -> Dict:
        """Analyze prediction bias by complexity range."""

        ranges = {
            "low": (0.0, 0.4),
            "medium": (0.4, 0.7),
            "high": (0.7, 1.0)
        }

        bias_by_range = {}
        for name, (low, high) in ranges.items():
            range_results = [
                r for r in results
                if low <= r["predicted"] < high
            ]

            if range_results:
                errors = [r["predicted"] - r["actual"] for r in range_results]
                bias_by_range[name] = {
                    "mean_error": sum(errors) / len(errors),
                    "samples": len(range_results)
                }

        return bias_by_range

    def _identify_systematic_errors(self, results: List[Dict]) -> List[Dict]:
        """Identify patterns of systematic misclassification."""

        errors = []

        # Find common misclassification patterns
        for predicted in ["individual", "small", "full"]:
            for actual in ["individual", "small", "full"]:
                if predicted == actual:
                    continue

                mismatches = [
                    r for r in results
                    if r["predicted_team"] == predicted
                    and r["actual_team"] == actual
                ]

                if len(mismatches) > 5:  # At least 5 cases
                    errors.append({
                        "predicted": predicted,
                        "actual": actual,
                        "count": len(mismatches),
                        "avg_predicted_complexity": sum(
                            r["predicted"] for r in mismatches
                        ) / len(mismatches)
                    })

        return sorted(errors, key=lambda x: x["count"], reverse=True)

    def _generate_feedback_recommendations(
        self,
        bias_analysis: Dict,
        systematic_errors: List[Dict]
    ) -> List[str]:
        """Generate recommendations from feedback analysis."""

        recommendations = []

        # Check for systematic over/under estimation
        for range_name, stats in bias_analysis.items():
            if stats["mean_error"] > 0.1:
                recommendations.append(
                    f"Systematic OVER-estimation in {range_name} complexity range "
                    f"(bias: +{stats['mean_error']:.2f}). Consider calibrating factors."
                )
            elif stats["mean_error"] < -0.1:
                recommendations.append(
                    f"Systematic UNDER-estimation in {range_name} complexity range "
                    f"(bias: {stats['mean_error']:.2f}). Consider calibrating factors."
                )

        # Check for systematic misclassifications
        for error in systematic_errors[:3]:  # Top 3
            recommendations.append(
                f"Frequent {error['predicted']}→{error['actual']} misclassification "
                f"({error['count']} cases, avg complexity: {error['avg_predicted_complexity']:.2f}). "
                f"Review threshold at {error['avg_predicted_complexity']:.2f}"
            )

        return recommendations

    async def trigger_retraining(
        self,
        min_new_samples: int = 100
    ) -> bool:
        """
        Trigger classifier retraining if enough new feedback.

        Returns True if retraining was triggered.
        """

        query = """
        MATCH (c:ClassificationEvent)-[:RECEIVED_FEEDBACK]->(f)
        WHERE f.timestamp > datetime() - duration('P30D')
        RETURN count(*) as new_samples
        """

        result = await self.neo4j.run(query)
        new_samples = result[0]["new_samples"] if result else 0

        if new_samples >= min_new_samples:
            # Trigger retraining pipeline
            await self._start_retraining_pipeline()
            return True

        return False

    async def _start_retraining_pipeline(self):
        """Start the model retraining pipeline."""
        # Integration with ML pipeline
        pass


@dataclass
class FeedbackAnalysis:
    status: str
    sample_size: Optional[int] = None
    bias_analysis: Optional[Dict] = None
    systematic_errors: Optional[List[Dict]] = None
    recommendations: Optional[List[str]] = None
    message: str = ""
```

---

## 6. Implementation Checklist

### Pre-Production Validation

- [ ] Run full test suite (30 cases) in staging
- [ ] Verify accuracy >= 85%
- [ ] Verify individual precision >= 90%
- [ ] Verify full team recall >= 95%
- [ ] Validate borderline cases manually
- [ ] Run A/B test for 1 week minimum
- [ ] Document known limitations
- [ ] Set up monitoring dashboards
- [ ] Configure alerting rules
- [ ] Train team on override procedures

### Production Deployment

- [ ] Deploy with 10% traffic shadow mode
- [ ] Monitor for 48 hours
- [ ] Gradually increase to 50%
- [ ] Compare metrics against baseline
- [ ] Full rollout after 1 week stable
- [ ] Enable feedback collection
- [ ] Schedule weekly calibration reviews

### Ongoing Maintenance

- [ ] Weekly metric review
- [ ] Monthly threshold calibration
- [ ] Quarterly model retraining
- [ ] Annual architecture review

---

## 7. Summary

This validation framework provides:

1. **30 Test Cases** spanning all capability domains with defined expected outcomes
2. **Edge Case Specifications** for 0.6 and 0.8 threshold boundaries
3. **Comprehensive Metrics** including accuracy, precision, recall, and cost efficiency
4. **Validation Pipeline** for automated testing in staging
5. **Calibration Strategy** with grid search and A/B testing
6. **Production Monitoring** with alerting and feedback loops

The framework ensures the complexity classifier makes cost-effective team sizing decisions while minimizing risk of under-resourcing complex tasks.
