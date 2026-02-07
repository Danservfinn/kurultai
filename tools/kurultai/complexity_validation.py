"""
Complexity Scoring Validation Framework for Kurultai Agent Teams.

This module provides comprehensive validation for the TeamSizeClassifier
to ensure accurate team sizing decisions before production deployment.

Usage:
    validator = ComplexityValidator(classifier, test_cases)
    report = await validator.run_validation(environment="staging")
    print(report.to_json())
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

import numpy as np

from tools.kurultai.complexity_config import (
    ComplexityConfig,
    DEFAULT_CONFIG,
    INPUT_MAX_LENGTH,
    complexity_to_team_size,
)
from tools.kurultai.complexity_validation_framework import (
    CapabilityDomain,
    TeamSize,
)

logger = logging.getLogger(__name__)


@dataclass
class TestCase:
    """Single test case for validation."""
    id: str
    request: str
    domain: CapabilityDomain
    expected_complexity: float
    expected_team: TeamSize
    factors: Dict[str, float] = field(default_factory=dict)
    is_borderline: bool = False
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "request": self.request,
            "domain": self.domain.value,
            "expected_complexity": self.expected_complexity,
            "expected_team": self.expected_team.value,
            "factors": self.factors,
            "is_borderline": self.is_borderline,
            "description": self.description,
        }


@dataclass
class ClassificationResult:
    """Result of a single classification."""
    test_id: str
    request: str
    predicted_complexity: float
    predicted_team: TeamSize
    actual_complexity: float
    actual_team: TeamSize

    @property
    def correct(self) -> bool:
        return self.predicted_team == self.actual_team

    @property
    def complexity_error(self) -> float:
        return abs(self.predicted_complexity - self.actual_complexity)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "request": self.request,
            "predicted_complexity": self.predicted_complexity,
            "predicted_team": self.predicted_team.value,
            "actual_complexity": self.actual_complexity,
            "actual_team": self.actual_team.value,
            "correct": self.correct,
            "complexity_error": self.complexity_error,
        }


@dataclass
class ValidationMetrics:
    """Comprehensive validation metrics."""

    # Accuracy
    total_cases: int
    correct_classifications: int
    accuracy: float

    # Precision by team size
    individual_precision: float
    small_team_precision: float
    full_team_precision: float

    # Recall by team size
    individual_recall: float
    small_team_recall: float
    full_team_recall: float

    # F1 Scores
    individual_f1: float
    small_team_f1: float
    full_team_f1: float
    macro_f1: float

    # Complexity calibration
    mean_absolute_error: float
    root_mean_squared_error: float

    # Cost efficiency
    avg_tokens_per_task: float = 0.0
    cost_vs_complexity_correlation: float = 0.0

    # Edge case performance
    borderline_accuracy: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accuracy": {
                "total_cases": self.total_cases,
                "correct": self.correct_classifications,
                "accuracy": round(self.accuracy, 4),
            },
            "precision": {
                "individual": round(self.individual_precision, 4),
                "small_team": round(self.small_team_precision, 4),
                "full_team": round(self.full_team_precision, 4),
            },
            "recall": {
                "individual": round(self.individual_recall, 4),
                "small_team": round(self.small_team_recall, 4),
                "full_team": round(self.full_team_recall, 4),
            },
            "f1": {
                "individual": round(self.individual_f1, 4),
                "small_team": round(self.small_team_f1, 4),
                "full_team": round(self.full_team_f1, 4),
                "macro": round(self.macro_f1, 4),
            },
            "complexity_error": {
                "mae": round(self.mean_absolute_error, 4),
                "rmse": round(self.root_mean_squared_error, 4),
            },
            "cost_efficiency": {
                "avg_tokens": round(self.avg_tokens_per_task, 2),
                "cost_correlation": round(self.cost_vs_complexity_correlation, 4),
            },
            "edge_cases": {
                "borderline_accuracy": round(self.borderline_accuracy, 4),
            },
        }


@dataclass
class ThresholdEvaluation:
    """Evaluation against production thresholds."""
    passed: bool
    checks: Dict[str, Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": self.checks,
        }


@dataclass
class ValidationReport:
    """Complete validation report."""
    timestamp: datetime
    environment: str
    metrics: ValidationMetrics
    threshold_evaluation: ThresholdEvaluation
    results: List[ClassificationResult]
    recommendations: List[str]

    def to_json(self) -> str:
        return json.dumps({
            "timestamp": self.timestamp.isoformat(),
            "environment": self.environment,
            "metrics": self.metrics.to_dict(),
            "threshold_evaluation": self.threshold_evaluation.to_dict(),
            "summary": {
                "total_cases": len(self.results),
                "correct": sum(1 for r in self.results if r.correct),
                "accuracy": round(self.metrics.accuracy, 4),
                "passed": self.threshold_evaluation.passed,
            },
            "recommendations": self.recommendations,
        }, indent=2)


class TeamSizeClassifier(Protocol):
    """Protocol for team size classifiers."""

    def classify(self, capability_request: str) -> "ClassificationPrediction":
        """Classify a capability request."""
        ...


@dataclass
class ClassificationPrediction:
    """Prediction result from classifier."""
    complexity: float
    confidence: float = 1.0
    factors: Dict[str, float] = field(default_factory=dict)


class ComplexityValidator:
    """
    Main validation orchestrator for complexity classification.
    """

    # Production readiness thresholds
    THRESHOLDS = {
        "accuracy": 0.85,
        "individual_precision": 0.90,
        "full_team_recall": 0.95,
        "borderline_accuracy": 0.70,
        "mae": 0.10,
    }

    def __init__(
        self,
        classifier: TeamSizeClassifier,
        test_cases: List[TestCase],
        team_simulator: Optional["TeamSimulator"] = None,
    ):
        self.classifier = classifier
        self.test_cases = test_cases
        self.team_simulator = team_simulator or TeamSimulator()
        self.results: List[ClassificationResult] = []

    async def run_validation(
        self,
        environment: str = "staging",
        parallel_executions: int = 5,
    ) -> ValidationReport:
        """Run full validation pipeline."""
        logger.info(f"Starting validation in {environment} environment")
        logger.info(f"Test cases: {len(self.test_cases)}")

        # Execute classifications
        semaphore = asyncio.Semaphore(parallel_executions)

        async def execute_with_limit(test_case: TestCase) -> ClassificationResult:
            async with semaphore:
                return await self._classify_and_simulate(test_case)

        self.results = await asyncio.gather(*[
            execute_with_limit(tc) for tc in self.test_cases
        ])

        # Calculate metrics
        metrics = self._calculate_metrics()

        # Evaluate thresholds
        threshold_eval = self._evaluate_thresholds(metrics)

        # Generate recommendations
        recommendations = self._generate_recommendations(metrics, threshold_eval)

        return ValidationReport(
            timestamp=datetime.now(timezone.utc),
            environment=environment,
            metrics=metrics,
            threshold_evaluation=threshold_eval,
            results=self.results,
            recommendations=recommendations,
        )

    async def _classify_and_simulate(self, test_case: TestCase) -> ClassificationResult:
        """Classify a test case and simulate execution."""
        # Get classifier prediction
        prediction = self.classifier.classify(test_case.request)
        predicted_team = self._complexity_to_team(prediction.complexity)

        # Simulate or use expected values
        if self.team_simulator:
            simulation = await self.team_simulator.simulate(
                request=test_case.request,
                team_size=predicted_team,
                expected_complexity=test_case.expected_complexity,
            )
            actual_team = simulation.optimal_team_size
            actual_complexity = simulation.measured_complexity
        else:
            # Use expected values for validation
            actual_team = test_case.expected_team
            actual_complexity = test_case.expected_complexity

        return ClassificationResult(
            test_id=test_case.id,
            request=test_case.request,
            predicted_complexity=prediction.complexity,
            predicted_team=predicted_team,
            actual_complexity=actual_complexity,
            actual_team=actual_team,
        )

    @staticmethod
    def _complexity_to_team(complexity: float) -> TeamSize:
        """Convert complexity score to team size."""
        label = complexity_to_team_size(complexity)
        return TeamSize(label)

    def _calculate_metrics(self) -> ValidationMetrics:
        """Calculate comprehensive metrics from results."""
        total = len(self.results)
        correct = sum(1 for r in self.results if r.correct)

        # Confusion matrix counts
        tp = {team: 0 for team in TeamSize}
        fp = {team: 0 for team in TeamSize}
        fn = {team: 0 for team in TeamSize}

        for r in self.results:
            if r.correct:
                tp[r.predicted_team] += 1
            else:
                fp[r.predicted_team] += 1
                fn[r.actual_team] += 1

        # Calculate precision and recall
        def safe_div(num: float, den: float) -> float:
            return num / den if den > 0 else 0.0

        precision = {
            team: safe_div(tp[team], tp[team] + fp[team])
            for team in TeamSize
        }

        recall = {
            team: safe_div(tp[team], tp[team] + fn[team])
            for team in TeamSize
        }

        # F1 scores
        f1 = {
            team: safe_div(
                2 * precision[team] * recall[team],
                precision[team] + recall[team]
            )
            for team in TeamSize
        }

        # Complexity errors
        errors = [r.complexity_error for r in self.results]
        mae = sum(errors) / len(errors) if errors else 0.0
        rmse = np.sqrt(sum(e ** 2 for e in errors) / len(errors)) if errors else 0.0

        # Borderline accuracy
        borderline_results = [
            r for r in self.results
            if abs(r.predicted_complexity - DEFAULT_CONFIG.individual_threshold) < 0.05
            or abs(r.predicted_complexity - DEFAULT_CONFIG.small_team_threshold) < 0.05
        ]
        borderline_accuracy = (
            sum(1 for r in borderline_results if r.correct) / len(borderline_results)
            if borderline_results else 1.0
        )

        return ValidationMetrics(
            total_cases=total,
            correct_classifications=correct,
            accuracy=correct / total if total > 0 else 0.0,
            individual_precision=precision[TeamSize.INDIVIDUAL],
            small_team_precision=precision[TeamSize.SMALL_TEAM],
            full_team_precision=precision[TeamSize.FULL_TEAM],
            individual_recall=recall[TeamSize.INDIVIDUAL],
            small_team_recall=recall[TeamSize.SMALL_TEAM],
            full_team_recall=recall[TeamSize.FULL_TEAM],
            individual_f1=f1[TeamSize.INDIVIDUAL],
            small_team_f1=f1[TeamSize.SMALL_TEAM],
            full_team_f1=f1[TeamSize.FULL_TEAM],
            macro_f1=sum(f1.values()) / len(f1),
            mean_absolute_error=mae,
            root_mean_squared_error=rmse,
            borderline_accuracy=borderline_accuracy,
        )

    def _evaluate_thresholds(self, metrics: ValidationMetrics) -> ThresholdEvaluation:
        """Evaluate metrics against production thresholds."""
        checks = {
            "accuracy": {
                "value": round(metrics.accuracy, 4),
                "threshold": self.THRESHOLDS["accuracy"],
                "passed": metrics.accuracy >= self.THRESHOLDS["accuracy"],
            },
            "individual_precision": {
                "value": round(metrics.individual_precision, 4),
                "threshold": self.THRESHOLDS["individual_precision"],
                "passed": metrics.individual_precision >= self.THRESHOLDS["individual_precision"],
            },
            "full_team_recall": {
                "value": round(metrics.full_team_recall, 4),
                "threshold": self.THRESHOLDS["full_team_recall"],
                "passed": metrics.full_team_recall >= self.THRESHOLDS["full_team_recall"],
            },
            "borderline_accuracy": {
                "value": round(metrics.borderline_accuracy, 4),
                "threshold": self.THRESHOLDS["borderline_accuracy"],
                "passed": metrics.borderline_accuracy >= self.THRESHOLDS["borderline_accuracy"],
            },
            "mae": {
                "value": round(metrics.mean_absolute_error, 4),
                "threshold": self.THRESHOLDS["mae"],
                "passed": metrics.mean_absolute_error <= self.THRESHOLDS["mae"],
            },
        }

        passed = all(check["passed"] for check in checks.values())
        return ThresholdEvaluation(passed=passed, checks=checks)

    def _generate_recommendations(
        self,
        metrics: ValidationMetrics,
        threshold_eval: ThresholdEvaluation,
    ) -> List[str]:
        """Generate calibration recommendations."""
        recommendations = []

        checks = threshold_eval.checks

        if not checks["accuracy"]["passed"]:
            recommendations.append(
                "ACCURACY BELOW THRESHOLD: Consider retraining classifier with "
                "expanded training set or adjusting factor weights."
            )

        if not checks["individual_precision"]["passed"]:
            recommendations.append(
                "LOW INDIVIDUAL PRECISION: Too many simple tasks getting teams. "
                "Consider raising threshold from 0.6 to 0.62-0.65."
            )

        if not checks["full_team_recall"]["passed"]:
            recommendations.append(
                "LOW FULL TEAM RECALL: Complex tasks underperforming. "
                "Consider lowering threshold from 0.8 to 0.75-0.78."
            )

        if metrics.mean_absolute_error > 0.15:
            recommendations.append(
                "HIGH COMPLEXITY ERROR: Classifier predictions diverging from "
                "actual outcomes. Review factor calculation logic."
            )

        if metrics.small_team_precision < 0.7:
            recommendations.append(
                "SMALL TEAM CLASSIFICATION UNSTABLE: Consider adding more "
                "granularity to 0.6-0.8 range or merging with adjacent categories."
            )

        if not recommendations:
            recommendations.append(
                "All metrics within acceptable thresholds. Classifier ready for production."
            )

        return recommendations


@dataclass
class SimulationResult:
    """Result of team execution simulation."""
    measured_complexity: float
    optimal_team_size: TeamSize
    confidence: float
    method: str


class TeamSimulator:
    """
    Simulates team execution to measure actual vs predicted complexity.
    """

    def __init__(
        self,
        historical_data: Optional[List[Dict]] = None,
    ):
        self.historical_data = historical_data or []

    async def simulate(
        self,
        request: str,
        team_size: TeamSize,
        expected_complexity: float,
    ) -> SimulationResult:
        """Simulate execution and determine optimal team size."""
        # Try historical match first
        historical = self._find_historical_match(request)
        if historical:
            return SimulationResult(
                measured_complexity=historical["actual_complexity"],
                optimal_team_size=historical["optimal_team"],
                confidence=0.8,
                method="historical_match",
            )

        # Fall back to factor-based estimation
        factor_complexity = self._estimate_from_factors(request)
        return SimulationResult(
            measured_complexity=factor_complexity,
            optimal_team_size=self._complexity_to_team(factor_complexity),
            confidence=0.6,
            method="factor_estimation",
        )

    def _find_historical_match(self, request: str) -> Optional[Dict]:
        """Find similar requests in historical data."""
        request_words = set(request.lower().split())
        best_match = None
        best_score = 0.0

        for record in self.historical_data:
            record_words = set(record.get("request", "").lower().split())
            if not record_words:
                continue
            overlap = len(request_words & record_words)
            score = overlap / max(len(request_words), len(record_words))

            if score > 0.7 and score > best_score:
                best_score = score
                best_match = record

        return best_match

    def _estimate_from_factors(self, request: str) -> float:
        """Estimate complexity from request characteristics."""
        factors = {
            "length": min(len(request) / 200, 1.0),
            "technical_terms": self._count_technical_terms(request) / 10,
            "integration_indicators": self._count_integration_words(request) / 5,
            "security_keywords": self._count_security_words(request) / 3,
        }

        weights = {
            "length": 0.2,
            "technical_terms": 0.3,
            "integration_indicators": 0.3,
            "security_keywords": 0.2,
        }

        complexity = sum(factors[k] * weights[k] for k in factors)
        return min(max(complexity, 0.0), 1.0)

    @staticmethod
    def _count_technical_terms(request: str) -> int:
        request = request[:INPUT_MAX_LENGTH]
        terms = [
            "api", "database", "websocket", "microservice", "kubernetes",
            "distributed", "async", "queue", "cache", "authentication",
            "authorization", "encryption", "pipeline", "orchestration",
        ]
        return sum(1 for term in terms if term in request.lower())

    @staticmethod
    def _count_integration_words(request: str) -> int:
        request = request[:INPUT_MAX_LENGTH]
        words = [
            "integrate", "connect", "sync", "bridge", "middleware",
            "adapter", "webhook", "callback", "event", "stream",
        ]
        return sum(1 for word in words if word in request.lower())

    @staticmethod
    def _count_security_words(request: str) -> int:
        request = request[:INPUT_MAX_LENGTH]
        words = [
            "auth", "oauth", "sso", "mfa", "encrypt", "hash",
            "token", "credential", "secret", "permission", "rbac",
        ]
        return sum(1 for word in words if word in request.lower())

    @staticmethod
    def _complexity_to_team(complexity: float) -> TeamSize:
        label = complexity_to_team_size(complexity)
        return TeamSize(label)


class ThresholdCalibrator:
    """
    Calibrate complexity thresholds based on validation results.
    """

    def __init__(
        self,
        lower_threshold: float = None,  # Uses DEFAULT_CONFIG.individual_threshold if None
        upper_threshold: float = None,  # Uses DEFAULT_CONFIG.small_team_threshold if None
        step_size: float = 0.02,
    ):
        self.lower = lower_threshold
        self.upper = upper_threshold
        self.step_size = step_size

    def calibrate(
        self,
        results: List[ClassificationResult],
    ) -> "CalibrationResult":
        """Find optimal thresholds based on validation results."""
        best_config = (self.lower, self.upper)
        best_score = -1.0

        for lower in self._generate_range(0.5, 0.7):
            for upper in self._generate_range(0.7, 0.9):
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
            recommendations=self._generate_recommendations(best_config, results),
        )

    def _generate_range(self, start: float, end: float) -> List[float]:
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
        upper: float,
    ) -> float:
        """Evaluate a threshold configuration."""
        reclassified = []
        for r in results:
            predicted = self._classify_with_thresholds(r.predicted_complexity, lower, upper)
            reclassified.append({"predicted": predicted, "actual": r.actual_team})

        correct = sum(1 for r in reclassified if r["predicted"] == r["actual"])
        accuracy = correct / len(reclassified) if reclassified else 0.0

        # Penalize false negatives heavily
        false_negatives = sum(
            1 for r in reclassified
            if r["actual"] == TeamSize.FULL_TEAM and r["predicted"] != TeamSize.FULL_TEAM
        )
        fn_penalty = false_negatives * 0.5

        # Penalize false positives moderately
        false_positives = sum(
            1 for r in reclassified
            if r["actual"] == TeamSize.INDIVIDUAL and r["predicted"] != TeamSize.INDIVIDUAL
        )
        fp_penalty = false_positives * 0.2

        return accuracy - fn_penalty - fp_penalty

    @staticmethod
    def _classify_with_thresholds(
        complexity: float,
        lower: float,
        upper: float,
    ) -> TeamSize:
        if complexity < lower:
            return TeamSize.INDIVIDUAL
        elif complexity < upper:
            return TeamSize.SMALL_TEAM
        else:
            return TeamSize.FULL_TEAM

    def _generate_recommendations(
        self,
        config: Tuple[float, float],
        results: List[ClassificationResult],
    ) -> List[str]:
        lower, upper = config
        recommendations = []

        # Compare against calibrated thresholds (not legacy 0.6/0.8)
        default_lower = DEFAULT_CONFIG.individual_threshold
        default_upper = DEFAULT_CONFIG.small_team_threshold

        if lower > default_lower:
            recommendations.append(
                f"RAISE lower threshold from {default_lower:.2f} to {lower:.2f} to improve "
                "individual precision and reduce team over-allocation."
            )
        elif lower < default_lower:
            recommendations.append(
                f"LOWER lower threshold from {default_lower:.2f} to {lower:.2f} to improve "
                "recall for moderate-complexity tasks."
            )

        if upper < default_upper:
            recommendations.append(
                f"LOWER upper threshold from {default_upper:.2f} to {upper:.2f} to ensure "
                "complex tasks get full team resources."
            )
        elif upper > default_upper:
            recommendations.append(
                f"RAISE upper threshold from {default_upper:.2f} to {upper:.2f} to reduce "
                "unnecessary full team allocation."
            )

        return recommendations


@dataclass
class CalibrationResult:
    """Result of threshold calibration."""
    optimal_lower: float
    optimal_upper: float
    score: float
    recommendations: List[str]


class ABTestFramework:
    """A/B testing for threshold configurations."""

    def __init__(
        self,
        traffic_split: float = 0.1,
    ):
        self.traffic_split = traffic_split

    def assign_variant(self, request_id: str) -> str:
        """Assign request to control or variant group."""
        secret = os.getenv("AB_TEST_SECRET")
        if not secret:
            raise ValueError("AB_TEST_SECRET environment variable required for A/B testing")
        secret_bytes = secret.encode()
        hash_val = int(hmac.new(secret_bytes, request_id.encode(), hashlib.sha256).hexdigest(), 16)
        if hash_val % 100 < (self.traffic_split * 100):
            return "variant"
        return "control"


# Predefined test cases for validation
DEFAULT_TEST_CASES = [
    # COMMUNICATION Domain
    TestCase(
        id="C1",
        request="Send a simple Slack message",
        domain=CapabilityDomain.COMMUNICATION,
        expected_complexity=0.25,
        expected_team=TeamSize.INDIVIDUAL,
        description="Single API call, no auth complexity",
    ),
    TestCase(
        id="C2",
        request="Post to Twitter with rate limiting",
        domain=CapabilityDomain.COMMUNICATION,
        expected_complexity=0.45,
        expected_team=TeamSize.INDIVIDUAL,
        description="Simple API with basic error handling",
    ),
    TestCase(
        id="C4",
        request="Integrate Discord bot with slash commands",
        domain=CapabilityDomain.COMMUNICATION,
        expected_complexity=0.60,
        expected_team=TeamSize.SMALL_TEAM,
        is_borderline=True,
        description="Borderline: WebSocket + command parsing",
    ),
    TestCase(
        id="C5",
        request="Build real-time chat with WebSocket",
        domain=CapabilityDomain.COMMUNICATION,
        expected_complexity=0.72,
        expected_team=TeamSize.SMALL_TEAM,
        description="Stateful connection, message queuing",
    ),
    TestCase(
        id="C6",
        request="Multi-channel notification system with fallbacks",
        domain=CapabilityDomain.COMMUNICATION,
        expected_complexity=0.80,
        expected_team=TeamSize.SMALL_TEAM,
        is_borderline=True,
        description="Borderline: Multiple providers, retry logic",
    ),

    # DATA Domain
    TestCase(
        id="D1",
        request="Parse CSV file",
        domain=CapabilityDomain.DATA,
        expected_complexity=0.20,
        expected_team=TeamSize.INDIVIDUAL,
        description="Standard library, no external deps",
    ),
    TestCase(
        id="D2",
        request="Query PostgreSQL database",
        domain=CapabilityDomain.DATA,
        expected_complexity=0.40,
        expected_team=TeamSize.INDIVIDUAL,
        description="Single connection, simple queries",
    ),
    TestCase(
        id="D4",
        request="ETL pipeline with data validation",
        domain=CapabilityDomain.DATA,
        expected_complexity=0.60,
        expected_team=TeamSize.SMALL_TEAM,
        is_borderline=True,
        description="Borderline: Multi-stage, schema validation",
    ),
    TestCase(
        id="D5",
        request="Real-time data streaming with Kafka",
        domain=CapabilityDomain.DATA,
        expected_complexity=0.75,
        expected_team=TeamSize.SMALL_TEAM,
        description="Distributed system, consumer groups",
    ),

    # INFRASTRUCTURE Domain
    TestCase(
        id="I1",
        request="Check disk space",
        domain=CapabilityDomain.INFRASTRUCTURE,
        expected_complexity=0.15,
        expected_team=TeamSize.INDIVIDUAL,
        description="System call, no network",
    ),
    TestCase(
        id="I4",
        request="Kubernetes deployment with health checks",
        domain=CapabilityDomain.INFRASTRUCTURE,
        expected_complexity=0.60,
        expected_team=TeamSize.SMALL_TEAM,
        is_borderline=True,
        description="Borderline: Multi-resource, probes",
    ),
    TestCase(
        id="I5",
        request="Auto-scaling group with custom metrics",
        domain=CapabilityDomain.INFRASTRUCTURE,
        expected_complexity=0.78,
        expected_team=TeamSize.SMALL_TEAM,
        description="Cloud APIs, metric aggregation",
    ),

    # AUTOMATION Domain
    TestCase(
        id="A1",
        request="Schedule a cron job",
        domain=CapabilityDomain.AUTOMATION,
        expected_complexity=0.20,
        expected_team=TeamSize.INDIVIDUAL,
        description="Time-based trigger, local execution",
    ),
    TestCase(
        id="A4",
        request="CI/CD pipeline with approval gates",
        domain=CapabilityDomain.AUTOMATION,
        expected_complexity=0.60,
        expected_team=TeamSize.SMALL_TEAM,
        is_borderline=True,
        description="Borderline: Multi-stage, human-in-loop",
    ),
    TestCase(
        id="A6",
        request="Self-healing infrastructure automation",
        domain=CapabilityDomain.AUTOMATION,
        expected_complexity=0.80,
        expected_team=TeamSize.SMALL_TEAM,
        is_borderline=True,
        description="Borderline: Monitoring, remediation loops",
    ),

    # INTELLIGENCE Domain
    TestCase(
        id="N1",
        request="Simple text classification",
        domain=CapabilityDomain.INTELLIGENCE,
        expected_complexity=0.30,
        expected_team=TeamSize.INDIVIDUAL,
        description="Pre-trained model, single inference",
    ),
    TestCase(
        id="N4",
        request="Named entity recognition with custom training",
        domain=CapabilityDomain.INTELLIGENCE,
        expected_complexity=0.60,
        expected_team=TeamSize.SMALL_TEAM,
        is_borderline=True,
        description="Borderline: Model fine-tuning, data prep",
    ),
    TestCase(
        id="N5",
        request="Multi-modal RAG system",
        domain=CapabilityDomain.INTELLIGENCE,
        expected_complexity=0.76,
        expected_team=TeamSize.SMALL_TEAM,
        description="Vector DB, embeddings, retrieval",
    ),
    TestCase(
        id="N6",
        request="Autonomous agent with tool use",
        domain=CapabilityDomain.INTELLIGENCE,
        expected_complexity=0.80,
        expected_team=TeamSize.SMALL_TEAM,
        is_borderline=True,
        description="Borderline: Planning, execution loops",
    ),
]


def create_mock_classifier() -> TeamSizeClassifier:
    """Create a mock classifier for testing."""

    class MockClassifier:
        def classify(self, request: str) -> ClassificationPrediction:
            # Simple heuristic-based mock
            complexity = 0.3  # Base

            if any(w in request.lower() for w in ["kubernetes", "distributed", "autonomous"]):
                complexity += 0.4
            if any(w in request.lower() for w in ["pipeline", "multi", "streaming"]):
                complexity += 0.2
            if any(w in request.lower() for w in ["integration", "websocket", "real-time"]):
                complexity += 0.15
            if any(w in request.lower() for w in ["simple", "parse", "check", "schedule"]):
                complexity = max(0.1, complexity - 0.2)

            return ClassificationPrediction(
                complexity=min(complexity, 1.0),
                confidence=0.8,
            )

    return MockClassifier()


async def main():
    """Run validation example."""
    logging.basicConfig(level=logging.INFO)

    classifier = create_mock_classifier()
    validator = ComplexityValidator(
        classifier=classifier,
        test_cases=DEFAULT_TEST_CASES,
    )

    report = await validator.run_validation(environment="staging")
    print(report.to_json())


if __name__ == "__main__":
    asyncio.run(main())
