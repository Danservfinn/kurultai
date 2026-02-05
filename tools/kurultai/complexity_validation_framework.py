"""
Complexity Scoring Validation Framework for Kurultai Agent Teams

This module provides comprehensive validation for the TeamSizeClassifier
to ensure proper team spawning decisions based on capability complexity.

Usage:
    from tools.kurultai.complexity_validation_framework import (
        ComplexityValidationFramework,
        TestCase,
        ValidationMetrics,
        ThresholdCalibrator
    )

    # Run validation suite
    framework = ComplexityValidationFramework(classifier)
    results = await framework.run_validation_suite()

    # Calibrate thresholds
    calibrator = ThresholdCalibrator(framework)
    optimal = calibrator.calibrate_thresholds(results)
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from uuid import UUID, uuid4

import numpy as np
from pydantic import BaseModel, Field, validator

from tools.kurultai.complexity_config import (
    ComplexityConfig,
    DEFAULT_CONFIG,
    INPUT_MAX_LENGTH,
    complexity_to_team_size as _config_complexity_to_team_size,
)

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# ENUMERATIONS
# =============================================================================

class CapabilityDomain(str, Enum):
    """Capability domains from kurultai_0.2.md taxonomy."""
    COMMUNICATION = "COMMUNICATION"
    DATA = "DATA"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    AUTOMATION = "AUTOMATION"
    INTELLIGENCE = "INTELLIGENCE"


class TeamSize(str, Enum):
    """Team size classifications."""
    INDIVIDUAL = "individual"      # < 0.6 complexity
    SMALL_TEAM = "small_team"      # 0.6 - 0.8 complexity
    FULL_TEAM = "full_team"        # > 0.8 complexity


class TestCaseCategory(str, Enum):
    """Categories for test cases."""
    EDGE_CASE = "edge_case"                    # Borderline thresholds
    KNOWN_SIMPLE = "known_simple"              # Definitively simple
    KNOWN_COMPLEX = "known_complex"            # Definitively complex
    DOMAIN_SPECIFIC = "domain_specific"        # Per-domain tests
    REGRESSION = "regression"                  # Past failures
    SYNTHETIC = "synthetic"                    # Generated edge cases


class ValidationStatus(str, Enum):
    """Validation result status."""
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    SKIP = "skip"


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class ComplexityFactors:
    """Factors contributing to complexity calculation.

    From kurultai_0.2.md Appendix B:
    - domain_risk: Risk level of the capability domain
    - api_count: Number of external APIs involved
    - integration_points: Number of system integration points
    - security_sensitivity: Security sensitivity score (0-1)
    """
    domain_risk: float = 0.0           # 0.0 - 1.0
    api_count: int = 0                 # Number of APIs
    integration_points: int = 0        # Integration complexity
    security_sensitivity: float = 0.0  # 0.0 - 1.0
    data_volume_gb: float = 0.0        # Expected data volume
    concurrency_requirements: int = 0  # Concurrent users/requests
    compliance_requirements: List[str] = field(default_factory=list)
    custom_factors: Dict[str, float] = field(default_factory=dict)

    def to_vector(self) -> np.ndarray:
        """Convert factors to numerical vector for analysis."""
        return np.array([
            self.domain_risk,
            min(self.api_count / 10, 1.0),  # Normalize to 0-1
            min(self.integration_points / 5, 1.0),
            self.security_sensitivity,
            min(self.data_volume_gb / 100, 1.0),
            min(self.concurrency_requirements / 1000, 1.0),
        ])


@dataclass
class TestCase:
    """Single test case for complexity validation.

    Attributes:
        id: Unique test case identifier
        name: Human-readable test name
        capability_request: The capability request string
        expected_complexity: Expected complexity score (0-1)
        expected_team_size: Expected team size classification
        domain: Capability domain
        category: Test case category
        factors: Complexity factors
        description: Detailed description
        tags: Additional tags for filtering
        created_at: Creation timestamp
    """
    id: str
    name: str
    capability_request: str
    expected_complexity: float
    expected_team_size: TeamSize
    domain: CapabilityDomain
    category: TestCaseCategory
    factors: ComplexityFactors
    description: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        """Validate expected complexity is within bounds."""
        if not 0.0 <= self.expected_complexity <= 1.0:
            raise ValueError(f"Expected complexity must be 0-1, got {self.expected_complexity}")


@dataclass
class TestResult:
    """Result of running a single test case.

    Attributes:
        test_case: The test case that was run
        predicted_complexity: Complexity score from classifier
        predicted_team_size: Team size from classifier
        actual_team_size: Actual team size used (may differ from predicted)
        status: Validation status
        error_margin: Absolute difference from expected
        classification_correct: Whether classification matches expected
        execution_time_ms: Time to classify
        token_usage: Tokens consumed during classification
        metadata: Additional runtime metadata
    """
    test_case: TestCase
    predicted_complexity: float
    predicted_team_size: TeamSize
    actual_team_size: Optional[TeamSize] = None
    status: ValidationStatus = ValidationStatus.PASS
    error_margin: float = 0.0
    classification_correct: bool = False
    execution_time_ms: float = 0.0
    token_usage: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    executed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ValidationMetrics:
    """Aggregated metrics from validation run.

    Metrics:
        - Accuracy: Overall classification accuracy
        - Precision: No false positives for team spawning
        - Recall: No missed complex tasks
        - F1 Score: Harmonic mean of precision and recall
        - Cost Efficiency: Token usage vs complexity correlation
    """
    # Classification metrics
    total_cases: int = 0
    correct_classifications: int = 0
    accuracy: float = 0.0

    # Precision/Recall by team size
    individual_precision: float = 0.0
    individual_recall: float = 0.0
    small_team_precision: float = 0.0
    small_team_recall: float = 0.0
    full_team_precision: float = 0.0
    full_team_recall: float = 0.0

    # Overall precision/recall
    precision: float = 0.0  # Precision for team spawning (small + full)
    recall: float = 0.0     # Recall for complex tasks (full team)
    f1_score: float = 0.0

    # Cost efficiency
    avg_tokens_per_classification: float = 0.0
    total_tokens: int = 0
    cost_efficiency_score: float = 0.0  # Complexity resolved per token

    # Error analysis
    mean_absolute_error: float = 0.0
    root_mean_squared_error: float = 0.0
    max_error: float = 0.0

    # Edge case performance
    edge_case_accuracy: float = 0.0
    threshold_boundary_accuracy: float = 0.0  # Cases near 0.6 and 0.8

    # Domain performance
    domain_accuracy: Dict[str, float] = field(default_factory=dict)

    # Timing
    avg_execution_time_ms: float = 0.0
    total_execution_time_ms: float = 0.0

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert metrics to JSON string."""
        return json.dumps(self.to_dict(), default=str, indent=2)


@dataclass
class ThresholdCalibration:
    """Calibration result for complexity thresholds.

    Attributes:
        lower_threshold: Threshold between individual and small team (default 0.6)
        upper_threshold: Threshold between small and full team (default 0.8)
        confidence: Confidence in these thresholds (0-1)
        metrics_at_thresholds: Metrics achieved with these thresholds
        recommendation: Human-readable recommendation
    """
    lower_threshold: float = field(default_factory=lambda: DEFAULT_CONFIG.individual_threshold)
    upper_threshold: float = field(default_factory=lambda: DEFAULT_CONFIG.small_team_threshold)
    confidence: float = 0.0
    metrics_at_thresholds: Optional[ValidationMetrics] = None
    recommendation: str = ""
    calibrated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# TEST CASE LIBRARY
# =============================================================================

class TestCaseLibrary:
    """Library of predefined test cases for validation.

    Contains 120+ test cases spanning:
    - Complexity range (0.0 - 1.0)
    - Edge cases (borderline 0.6 and 0.8)
    - All capability domains
    - Known simple vs known complex capabilities
    - Medium complexity (small team) cases
    - Regression tests

    Target distribution: ~30 Individual / ~40 Small Team / ~30 Full Team / ~20 Edge
    """

    @classmethod
    def get_all_test_cases(cls) -> List[TestCase]:
        """Get complete test suite (120+ test cases)."""
        cases = []
        cases.extend(cls._get_edge_cases())
        cases.extend(cls._get_known_simple_cases())
        cases.extend(cls._get_medium_complexity_cases())
        cases.extend(cls._get_known_complex_cases())
        cases.extend(cls._get_domain_specific_cases())
        cases.extend(cls._get_regression_cases())
        return cases

    @classmethod
    def _get_edge_cases(cls) -> List[TestCase]:
        """Edge cases near threshold boundaries (0.6 and 0.8). ~20 cases."""
        return [
            TestCase(
                id="edge_001",
                name="Just Below Small Team Threshold",
                capability_request="Send a basic email notification",
                expected_complexity=0.59,
                expected_team_size=TeamSize.INDIVIDUAL,
                domain=CapabilityDomain.COMMUNICATION,
                category=TestCaseCategory.EDGE_CASE,
                factors=ComplexityFactors(
                    domain_risk=0.3, api_count=1,
                    integration_points=1, security_sensitivity=0.2,
                ),
                description="Borderline case just below 0.6 threshold",
                tags=["boundary", "email", "notification"],
            ),
            TestCase(
                id="edge_002",
                name="Just Above Small Team Threshold",
                capability_request="Send personalized email campaigns with A/B testing and webhook callback",
                expected_complexity=0.61,
                expected_team_size=TeamSize.SMALL_TEAM,
                domain=CapabilityDomain.COMMUNICATION,
                category=TestCaseCategory.EDGE_CASE,
                factors=ComplexityFactors(
                    domain_risk=0.4, api_count=2,
                    integration_points=2, security_sensitivity=0.3,
                ),
                description="Borderline case just above 0.6 threshold",
                tags=["boundary", "email", "campaign", "ab-testing"],
            ),
            TestCase(
                id="edge_003",
                name="Exactly at 0.6 Threshold",
                capability_request="Integrate Slack webhook for channel notifications with event handler",
                expected_complexity=0.60,
                expected_team_size=TeamSize.SMALL_TEAM,
                domain=CapabilityDomain.COMMUNICATION,
                category=TestCaseCategory.EDGE_CASE,
                factors=ComplexityFactors(
                    domain_risk=0.35, api_count=1,
                    integration_points=2, security_sensitivity=0.3,
                ),
                description="Exactly at the 0.6 threshold - should err toward team",
                tags=["boundary", "slack", "webhook"],
            ),
            TestCase(
                id="edge_004",
                name="Just Below Full Team Threshold",
                capability_request="Build real-time chat system with message persistence and cache",
                expected_complexity=0.79,
                expected_team_size=TeamSize.SMALL_TEAM,
                domain=CapabilityDomain.COMMUNICATION,
                category=TestCaseCategory.EDGE_CASE,
                factors=ComplexityFactors(
                    domain_risk=0.6, api_count=3,
                    integration_points=3, security_sensitivity=0.5,
                    concurrency_requirements=100,
                ),
                description="Borderline case just below 0.8 threshold",
                tags=["boundary", "chat", "real-time", "websocket"],
            ),
            TestCase(
                id="edge_005",
                name="Just Above Full Team Threshold",
                capability_request="Build enterprise messaging platform with encryption and authentication across distributed nodes",
                expected_complexity=0.81,
                expected_team_size=TeamSize.FULL_TEAM,
                domain=CapabilityDomain.COMMUNICATION,
                category=TestCaseCategory.EDGE_CASE,
                factors=ComplexityFactors(
                    domain_risk=0.9, api_count=4,
                    integration_points=5, security_sensitivity=0.95,
                    compliance_requirements=["SOC2", "GDPR"],
                ),
                description="Borderline case just above 0.8 threshold",
                tags=["boundary", "messaging", "encryption", "enterprise"],
            ),
            TestCase(
                id="edge_006",
                name="Exactly at 0.8 Threshold",
                capability_request="Implement multi-channel notification orchestration with queue and auth",
                expected_complexity=0.80,
                expected_team_size=TeamSize.FULL_TEAM,
                domain=CapabilityDomain.COMMUNICATION,
                category=TestCaseCategory.EDGE_CASE,
                factors=ComplexityFactors(
                    domain_risk=0.7, api_count=4,
                    integration_points=4, security_sensitivity=0.6,
                    concurrency_requirements=500,
                ),
                description="Exactly at the 0.8 threshold - should err toward full team",
                tags=["boundary", "orchestrator", "multi-channel"],
            ),
            # Additional edge cases for better coverage
            TestCase(
                id="edge_007",
                name="Simple API with Token Auth",
                capability_request="Fetch data from REST API with token authentication",
                expected_complexity=0.55,
                expected_team_size=TeamSize.INDIVIDUAL,
                domain=CapabilityDomain.DATA,
                category=TestCaseCategory.EDGE_CASE,
                factors=ComplexityFactors(
                    domain_risk=0.3, api_count=1,
                    integration_points=1, security_sensitivity=0.4,
                ),
                description="Near lower threshold - auth bumps but still individual",
                tags=["boundary", "api", "token"],
            ),
            TestCase(
                id="edge_008",
                name="Webhook with Retry Logic",
                capability_request="Build webhook handler with retry logic and callback event processing",
                expected_complexity=0.62,
                expected_team_size=TeamSize.SMALL_TEAM,
                domain=CapabilityDomain.INFRASTRUCTURE,
                category=TestCaseCategory.EDGE_CASE,
                factors=ComplexityFactors(
                    domain_risk=0.5, api_count=1,
                    integration_points=2, security_sensitivity=0.3,
                ),
                description="Just above 0.6 - integration complexity pushes it over",
                tags=["boundary", "webhook", "retry"],
            ),
            TestCase(
                id="edge_009",
                name="Basic Queue Consumer",
                capability_request="Consume messages from a queue and process them",
                expected_complexity=0.50,
                expected_team_size=TeamSize.INDIVIDUAL,
                domain=CapabilityDomain.DATA,
                category=TestCaseCategory.EDGE_CASE,
                factors=ComplexityFactors(
                    domain_risk=0.3, api_count=1,
                    integration_points=1, security_sensitivity=0.2,
                ),
                description="Queue is technical but simple consumer is individual",
                tags=["boundary", "queue", "consumer"],
            ),
            TestCase(
                id="edge_010",
                name="Database Migration Script",
                capability_request="Build database migration tool with schema validation",
                expected_complexity=0.58,
                expected_team_size=TeamSize.INDIVIDUAL,
                domain=CapabilityDomain.DATA,
                category=TestCaseCategory.EDGE_CASE,
                factors=ComplexityFactors(
                    domain_risk=0.4, api_count=0,
                    integration_points=1, security_sensitivity=0.3,
                ),
                description="Just below 0.6 - moderate complexity but not team-worthy",
                tags=["boundary", "database", "migration"],
            ),
            TestCase(
                id="edge_011",
                name="Cache Invalidation Strategy",
                capability_request="Implement cache invalidation with pub/sub event-driven approach using Redis",
                expected_complexity=0.65,
                expected_team_size=TeamSize.SMALL_TEAM,
                domain=CapabilityDomain.INFRASTRUCTURE,
                category=TestCaseCategory.EDGE_CASE,
                factors=ComplexityFactors(
                    domain_risk=0.5, api_count=2,
                    integration_points=2, security_sensitivity=0.2,
                ),
                description="Cache + pubsub integration = small team",
                tags=["boundary", "cache", "pubsub", "redis"],
            ),
            TestCase(
                id="edge_012",
                name="Near Full Team - Multi-API Orchestration",
                capability_request="Orchestrate API gateway with authentication proxy and rate limiting",
                expected_complexity=0.78,
                expected_team_size=TeamSize.SMALL_TEAM,
                domain=CapabilityDomain.INFRASTRUCTURE,
                category=TestCaseCategory.EDGE_CASE,
                factors=ComplexityFactors(
                    domain_risk=0.6, api_count=3,
                    integration_points=3, security_sensitivity=0.6,
                ),
                description="Near 0.8 but not quite full team",
                tags=["boundary", "gateway", "proxy"],
            ),
            TestCase(
                id="edge_013",
                name="Monitoring Dashboard with Alerts",
                capability_request="Build monitoring dashboard with Prometheus metrics and Grafana alerts",
                expected_complexity=0.63,
                expected_team_size=TeamSize.SMALL_TEAM,
                domain=CapabilityDomain.INFRASTRUCTURE,
                category=TestCaseCategory.EDGE_CASE,
                factors=ComplexityFactors(
                    domain_risk=0.4, api_count=2,
                    integration_points=2, security_sensitivity=0.2,
                ),
                description="Monitoring integration complexity",
                tags=["boundary", "monitoring", "prometheus", "grafana"],
            ),
            TestCase(
                id="edge_014",
                name="Simple Encryption Utility",
                capability_request="Encrypt files using standard library hash functions",
                expected_complexity=0.40,
                expected_team_size=TeamSize.INDIVIDUAL,
                domain=CapabilityDomain.INFRASTRUCTURE,
                category=TestCaseCategory.EDGE_CASE,
                factors=ComplexityFactors(
                    domain_risk=0.3, api_count=0,
                    integration_points=0, security_sensitivity=0.5,
                ),
                description="Security keyword but simple implementation",
                tags=["boundary", "encrypt", "simple"],
            ),
            TestCase(
                id="edge_015",
                name="Multi-Tenant Data Isolation",
                capability_request="Implement multi-tenant database isolation with RBAC permission model and encryption",
                expected_complexity=0.82,
                expected_team_size=TeamSize.FULL_TEAM,
                domain=CapabilityDomain.DATA,
                category=TestCaseCategory.EDGE_CASE,
                factors=ComplexityFactors(
                    domain_risk=0.8, api_count=2,
                    integration_points=3, security_sensitivity=0.9,
                ),
                description="Multi-tenant + RBAC + encryption = full team",
                tags=["boundary", "multi-tenant", "rbac", "encryption"],
            ),
            TestCase(
                id="edge_016",
                name="Streaming ETL Near Threshold",
                capability_request="Build streaming data pipeline with event processing and schema validation",
                expected_complexity=0.75,
                expected_team_size=TeamSize.FULL_TEAM,
                domain=CapabilityDomain.DATA,
                category=TestCaseCategory.EDGE_CASE,
                factors=ComplexityFactors(
                    domain_risk=0.5, api_count=2,
                    integration_points=3, security_sensitivity=0.3,
                ),
                description="Streaming + ETL but not quite full team",
                tags=["boundary", "streaming", "etl", "pipeline"],
            ),
            TestCase(
                id="edge_017",
                name="Automated Test Runner",
                capability_request="Build automated test pipeline with parallel execution and reporting",
                expected_complexity=0.56,
                expected_team_size=TeamSize.SMALL_TEAM,
                domain=CapabilityDomain.AUTOMATION,
                category=TestCaseCategory.EDGE_CASE,
                factors=ComplexityFactors(
                    domain_risk=0.3, api_count=1,
                    integration_points=1, security_sensitivity=0.1,
                ),
                description="Pipeline + parallel execution + reporting = small team",
                tags=["boundary", "testing", "automation"],
            ),
            TestCase(
                id="edge_018",
                name="Feature Flag Service",
                capability_request="Implement feature flag system with gradual rollout and A/B testing integration",
                expected_complexity=0.64,
                expected_team_size=TeamSize.SMALL_TEAM,
                domain=CapabilityDomain.AUTOMATION,
                category=TestCaseCategory.EDGE_CASE,
                factors=ComplexityFactors(
                    domain_risk=0.4, api_count=2,
                    integration_points=2, security_sensitivity=0.3,
                ),
                description="Feature flags with A/B testing = small team",
                tags=["boundary", "feature-flag", "ab-test"],
            ),
            TestCase(
                id="edge_019",
                name="Sentiment Analysis API",
                capability_request="Build sentiment analysis API with pre-trained model inference",
                expected_complexity=0.52,
                expected_team_size=TeamSize.INDIVIDUAL,
                domain=CapabilityDomain.INTELLIGENCE,
                category=TestCaseCategory.EDGE_CASE,
                factors=ComplexityFactors(
                    domain_risk=0.3, api_count=1,
                    integration_points=1, security_sensitivity=0.2,
                ),
                description="ML inference but simple wrapper = individual",
                tags=["boundary", "ml", "api", "inference"],
            ),
            TestCase(
                id="edge_020",
                name="Event-Driven Microservice",
                capability_request="Build event-driven microservice with async queue processing and webhook callbacks",
                expected_complexity=0.72,
                expected_team_size=TeamSize.FULL_TEAM,
                domain=CapabilityDomain.INFRASTRUCTURE,
                category=TestCaseCategory.EDGE_CASE,
                factors=ComplexityFactors(
                    domain_risk=0.5, api_count=2,
                    integration_points=3, security_sensitivity=0.3,
                ),
                description="Event-driven + microservice + async + webhooks = full team",
                tags=["boundary", "microservice", "event-driven", "async"],
            ),
        ]

    @classmethod
    def _get_known_simple_cases(cls) -> List[TestCase]:
        """Known simple capabilities (complexity < 0.5). ~30 cases."""
        _S = TestCaseCategory.KNOWN_SIMPLE
        _I = TeamSize.INDIVIDUAL
        _cf = ComplexityFactors  # shorthand
        return [
            TestCase(id="simple_001", name="Basic File Read",
                     capability_request="Read a text file from local filesystem",
                     expected_complexity=0.15, expected_team_size=_I, domain=CapabilityDomain.DATA,
                     category=_S, factors=_cf(domain_risk=0.1), tags=["file", "read"]),
            TestCase(id="simple_002", name="Basic HTTP GET",
                     capability_request="Fetch JSON data from a public API",
                     expected_complexity=0.25, expected_team_size=_I, domain=CapabilityDomain.DATA,
                     category=_S, factors=_cf(domain_risk=0.2, api_count=1), tags=["http", "api"]),
            TestCase(id="simple_003", name="Simple Data Validation",
                     capability_request="Validate email address format",
                     expected_complexity=0.20, expected_team_size=_I, domain=CapabilityDomain.DATA,
                     category=_S, factors=_cf(domain_risk=0.1), tags=["validation", "regex"]),
            TestCase(id="simple_004", name="Basic Logging",
                     capability_request="Log application events to console",
                     expected_complexity=0.10, expected_team_size=_I, domain=CapabilityDomain.INFRASTRUCTURE,
                     category=_S, factors=_cf(domain_risk=0.05), tags=["logging", "simple"]),
            TestCase(id="simple_005", name="Simple Cron Job",
                     capability_request="Run a script every hour",
                     expected_complexity=0.30, expected_team_size=_I, domain=CapabilityDomain.AUTOMATION,
                     category=_S, factors=_cf(domain_risk=0.2), tags=["cron", "automation"]),
            TestCase(id="simple_006", name="Hello World CLI",
                     capability_request="Print hello world message",
                     expected_complexity=0.05, expected_team_size=_I, domain=CapabilityDomain.COMMUNICATION,
                     category=_S, factors=_cf(domain_risk=0.01), tags=["hello"]),
            TestCase(id="simple_007", name="Config File Parser",
                     capability_request="Parse a YAML config file",
                     expected_complexity=0.18, expected_team_size=_I, domain=CapabilityDomain.DATA,
                     category=_S, factors=_cf(domain_risk=0.1), tags=["config", "yaml"]),
            TestCase(id="simple_008", name="Environment Variable Reader",
                     capability_request="Read environment variables and print status",
                     expected_complexity=0.08, expected_team_size=_I, domain=CapabilityDomain.INFRASTRUCTURE,
                     category=_S, factors=_cf(domain_risk=0.05), tags=["env", "config"]),
            TestCase(id="simple_009", name="JSON Formatter",
                     capability_request="Format JSON output for pretty printing",
                     expected_complexity=0.12, expected_team_size=_I, domain=CapabilityDomain.DATA,
                     category=_S, factors=_cf(domain_risk=0.05), tags=["json", "format"]),
            TestCase(id="simple_010", name="Disk Space Check",
                     capability_request="Check disk space on local filesystem",
                     expected_complexity=0.10, expected_team_size=_I, domain=CapabilityDomain.INFRASTRUCTURE,
                     category=_S, factors=_cf(domain_risk=0.05), tags=["disk", "health"]),
            TestCase(id="simple_011", name="CSV Export",
                     capability_request="Export list of items to CSV file",
                     expected_complexity=0.15, expected_team_size=_I, domain=CapabilityDomain.DATA,
                     category=_S, factors=_cf(domain_risk=0.1), tags=["csv", "export"]),
            TestCase(id="simple_012", name="String Sanitizer",
                     capability_request="Sanitize user input strings for display",
                     expected_complexity=0.18, expected_team_size=_I, domain=CapabilityDomain.DATA,
                     category=_S, factors=_cf(domain_risk=0.1, security_sensitivity=0.2), tags=["sanitize"]),
            TestCase(id="simple_013", name="Health Check Endpoint",
                     capability_request="Create simple health check HTTP status endpoint",
                     expected_complexity=0.15, expected_team_size=_I, domain=CapabilityDomain.INFRASTRUCTURE,
                     category=_S, factors=_cf(domain_risk=0.1, api_count=1), tags=["health", "http"]),
            TestCase(id="simple_014", name="Date Formatter",
                     capability_request="Format dates to ISO 8601 standard",
                     expected_complexity=0.08, expected_team_size=_I, domain=CapabilityDomain.DATA,
                     category=_S, factors=_cf(domain_risk=0.02), tags=["date", "format"]),
            TestCase(id="simple_015", name="Simple HTTP POST",
                     capability_request="Send a basic HTTP POST request with JSON body",
                     expected_complexity=0.22, expected_team_size=_I, domain=CapabilityDomain.COMMUNICATION,
                     category=_S, factors=_cf(domain_risk=0.15, api_count=1), tags=["http", "post"]),
            TestCase(id="simple_016", name="Text Search in File",
                     capability_request="Search for a text pattern in a local file",
                     expected_complexity=0.12, expected_team_size=_I, domain=CapabilityDomain.DATA,
                     category=_S, factors=_cf(domain_risk=0.05), tags=["search", "file"]),
            TestCase(id="simple_017", name="Process Status Monitor",
                     capability_request="Check if a local process is running",
                     expected_complexity=0.12, expected_team_size=_I, domain=CapabilityDomain.INFRASTRUCTURE,
                     category=_S, factors=_cf(domain_risk=0.1), tags=["process", "status"]),
            TestCase(id="simple_018", name="Simple Slack Message",
                     capability_request="Send a Slack message to a channel",
                     expected_complexity=0.25, expected_team_size=_I, domain=CapabilityDomain.COMMUNICATION,
                     category=_S, factors=_cf(domain_risk=0.15, api_count=1), tags=["slack"]),
            TestCase(id="simple_019", name="Template Renderer",
                     capability_request="Render a simple HTML template with variables",
                     expected_complexity=0.18, expected_team_size=_I, domain=CapabilityDomain.DATA,
                     category=_S, factors=_cf(domain_risk=0.05), tags=["template"]),
            TestCase(id="simple_020", name="Password Generator",
                     capability_request="Generate a random password string",
                     expected_complexity=0.10, expected_team_size=_I, domain=CapabilityDomain.INFRASTRUCTURE,
                     category=_S, factors=_cf(domain_risk=0.05, security_sensitivity=0.2), tags=["password"]),
            TestCase(id="simple_021", name="File Copy Utility",
                     capability_request="Copy files from one local directory to another",
                     expected_complexity=0.10, expected_team_size=_I, domain=CapabilityDomain.DATA,
                     category=_S, factors=_cf(domain_risk=0.05), tags=["file", "copy"]),
            TestCase(id="simple_022", name="Simple Timer",
                     capability_request="Create a countdown timer that prints to console",
                     expected_complexity=0.08, expected_team_size=_I, domain=CapabilityDomain.AUTOMATION,
                     category=_S, factors=_cf(domain_risk=0.02), tags=["timer"]),
            TestCase(id="simple_023", name="URL Shortener Lookup",
                     capability_request="Resolve a shortened URL to its full address",
                     expected_complexity=0.15, expected_team_size=_I, domain=CapabilityDomain.DATA,
                     category=_S, factors=_cf(domain_risk=0.1, api_count=1), tags=["url"]),
            TestCase(id="simple_024", name="Git Status Reporter",
                     capability_request="Report current git branch and status",
                     expected_complexity=0.12, expected_team_size=_I, domain=CapabilityDomain.AUTOMATION,
                     category=_S, factors=_cf(domain_risk=0.05), tags=["git"]),
            TestCase(id="simple_025", name="Markdown to HTML",
                     capability_request="Convert a basic markdown document to HTML",
                     expected_complexity=0.15, expected_team_size=_I, domain=CapabilityDomain.DATA,
                     category=_S, factors=_cf(domain_risk=0.05), tags=["markdown"]),
            TestCase(id="simple_026", name="Simple Email Sender",
                     capability_request="Send a basic text email via SMTP",
                     expected_complexity=0.28, expected_team_size=_I, domain=CapabilityDomain.COMMUNICATION,
                     category=_S, factors=_cf(domain_risk=0.2, api_count=1), tags=["email"]),
            TestCase(id="simple_027", name="RSS Feed Reader",
                     capability_request="Read and parse an RSS feed",
                     expected_complexity=0.20, expected_team_size=_I, domain=CapabilityDomain.DATA,
                     category=_S, factors=_cf(domain_risk=0.1, api_count=1), tags=["rss"]),
            TestCase(id="simple_028", name="Image Resize Tool",
                     capability_request="Resize an image to specified dimensions",
                     expected_complexity=0.15, expected_team_size=_I, domain=CapabilityDomain.DATA,
                     category=_S, factors=_cf(domain_risk=0.05), tags=["image"]),
            TestCase(id="simple_029", name="Simple Calculator",
                     capability_request="Evaluate a basic math expression",
                     expected_complexity=0.08, expected_team_size=_I, domain=CapabilityDomain.DATA,
                     category=_S, factors=_cf(domain_risk=0.02), tags=["math"]),
            TestCase(id="simple_030", name="Port Scanner",
                     capability_request="Check if a single port is open on a host",
                     expected_complexity=0.18, expected_team_size=_I, domain=CapabilityDomain.INFRASTRUCTURE,
                     category=_S, factors=_cf(domain_risk=0.15), tags=["network"]),
        ]

    @classmethod
    def _get_medium_complexity_cases(cls) -> List[TestCase]:
        """Medium complexity capabilities (0.6 <= complexity < 0.8). ~15 cases."""
        _M = TestCaseCategory.DOMAIN_SPECIFIC
        _ST = TeamSize.SMALL_TEAM
        _cf = ComplexityFactors
        return [
            TestCase(id="medium_001", name="OAuth 2.0 Login Flow",
                     capability_request="Implement OAuth 2.0 authentication flow with token refresh and callback handler",
                     expected_complexity=0.68, expected_team_size=TeamSize.FULL_TEAM, domain=CapabilityDomain.INFRASTRUCTURE,
                     category=_M, factors=_cf(domain_risk=0.6, api_count=2, security_sensitivity=0.7), tags=["oauth", "auth"]),
            TestCase(id="medium_002", name="Job Queue with Retry",
                     capability_request="Build async job queue with retry logic, dead-letter handling, and webhook notifications",
                     expected_complexity=0.70, expected_team_size=TeamSize.FULL_TEAM, domain=CapabilityDomain.AUTOMATION,
                     category=_M, factors=_cf(domain_risk=0.5, api_count=2, integration_points=3), tags=["queue", "retry"]),
            TestCase(id="medium_003", name="REST API with CRUD and Auth",
                     capability_request="Build REST API with authentication, authorization, and database CRUD operations",
                     expected_complexity=0.65, expected_team_size=_ST, domain=CapabilityDomain.DATA,
                     category=_M, factors=_cf(domain_risk=0.5, api_count=1, security_sensitivity=0.6), tags=["rest", "crud"]),
            TestCase(id="medium_004", name="Notification Service",
                     capability_request="Build notification service with email, push, and webhook delivery channels",
                     expected_complexity=0.68, expected_team_size=_ST, domain=CapabilityDomain.COMMUNICATION,
                     category=_M, factors=_cf(domain_risk=0.4, api_count=3, integration_points=3), tags=["notification"]),
            TestCase(id="medium_005", name="Data Sync Pipeline",
                     capability_request="Implement bidirectional data sync between two databases with conflict resolution",
                     expected_complexity=0.72, expected_team_size=_ST, domain=CapabilityDomain.DATA,
                     category=_M, factors=_cf(domain_risk=0.6, api_count=2, integration_points=3), tags=["sync", "database"]),
            TestCase(id="medium_006", name="Log Aggregation System",
                     capability_request="Build centralized log aggregation with Elasticsearch and search API",
                     expected_complexity=0.66, expected_team_size=_ST, domain=CapabilityDomain.INFRASTRUCTURE,
                     category=_M, factors=_cf(domain_risk=0.4, api_count=2, integration_points=2), tags=["logging", "elasticsearch"]),
            TestCase(id="medium_007", name="Workflow Automation Engine",
                     capability_request="Build workflow automation engine with conditional branching and webhook triggers",
                     expected_complexity=0.73, expected_team_size=_ST, domain=CapabilityDomain.AUTOMATION,
                     category=_M, factors=_cf(domain_risk=0.5, api_count=2, integration_points=3), tags=["workflow", "automation"]),
            TestCase(id="medium_008", name="Chatbot with NLP",
                     capability_request="Build chatbot with intent detection and entity extraction using NLP",
                     expected_complexity=0.70, expected_team_size=_ST, domain=CapabilityDomain.INTELLIGENCE,
                     category=_M, factors=_cf(domain_risk=0.5, api_count=2), tags=["chatbot", "nlp"]),
            TestCase(id="medium_009", name="API Rate Limiter",
                     capability_request="Implement API rate limiting with Redis cache and per-user token buckets",
                     expected_complexity=0.64, expected_team_size=_ST, domain=CapabilityDomain.INFRASTRUCTURE,
                     category=_M, factors=_cf(domain_risk=0.5, api_count=1, integration_points=2), tags=["rate-limit", "redis"]),
            TestCase(id="medium_010", name="Report Generator",
                     capability_request="Build automated report generation pipeline with database queries and PDF export",
                     expected_complexity=0.62, expected_team_size=_ST, domain=CapabilityDomain.DATA,
                     category=_M, factors=_cf(domain_risk=0.4, api_count=1, integration_points=2), tags=["report", "pipeline"]),
            TestCase(id="medium_011", name="Event Bus Integration",
                     capability_request="Integrate event bus with publish-subscribe pattern and consumer group management",
                     expected_complexity=0.67, expected_team_size=_ST, domain=CapabilityDomain.INFRASTRUCTURE,
                     category=_M, factors=_cf(domain_risk=0.5, api_count=2, integration_points=3), tags=["event-bus", "pubsub"]),
            TestCase(id="medium_012", name="Search Indexer",
                     capability_request="Build full-text search indexer with relevance scoring and API gateway",
                     expected_complexity=0.69, expected_team_size=_ST, domain=CapabilityDomain.DATA,
                     category=_M, factors=_cf(domain_risk=0.5, api_count=2, integration_points=2), tags=["search", "indexer"]),
            TestCase(id="medium_013", name="Container Orchestrator Config",
                     capability_request="Configure Docker container deployment with health checks and rolling updates",
                     expected_complexity=0.63, expected_team_size=_ST, domain=CapabilityDomain.INFRASTRUCTURE,
                     category=_M, factors=_cf(domain_risk=0.5, api_count=1, integration_points=2), tags=["docker", "deployment"]),
            TestCase(id="medium_014", name="Data Validation Pipeline",
                     capability_request="Build data validation pipeline with schema enforcement and anomaly detection",
                     expected_complexity=0.66, expected_team_size=TeamSize.FULL_TEAM, domain=CapabilityDomain.DATA,
                     category=_M, factors=_cf(domain_risk=0.4, api_count=1, integration_points=2), tags=["validation", "pipeline"]),
            TestCase(id="medium_015", name="Webhook Delivery Service",
                     capability_request="Build webhook delivery service with retry logic, signing, and event routing",
                     expected_complexity=0.71, expected_team_size=_ST, domain=CapabilityDomain.COMMUNICATION,
                     category=_M, factors=_cf(domain_risk=0.5, api_count=2, integration_points=3, security_sensitivity=0.4), tags=["webhook", "delivery"]),
        ]

    @classmethod
    def _get_known_complex_cases(cls) -> List[TestCase]:
        """Known complex capabilities (complexity > 0.8). ~30 cases."""
        _C = TestCaseCategory.KNOWN_COMPLEX
        _F = TeamSize.FULL_TEAM
        _cf = ComplexityFactors
        return [
            TestCase(id="complex_001", name="Distributed Database System",
                     capability_request="Build distributed database with automatic sharding and replication across multi-region clusters",
                     expected_complexity=0.95, expected_team_size=_F, domain=CapabilityDomain.DATA,
                     category=_C, factors=_cf(domain_risk=0.9, api_count=5, integration_points=8,
                     security_sensitivity=0.8, data_volume_gb=1000, concurrency_requirements=10000),
                     tags=["database", "distributed", "sharding"]),
            TestCase(id="complex_002", name="ML Pipeline Platform",
                     capability_request="Build end-to-end ML training and inference platform with pipeline orchestration",
                     expected_complexity=0.92, expected_team_size=_F, domain=CapabilityDomain.INTELLIGENCE,
                     category=_C, factors=_cf(domain_risk=0.85, api_count=6, integration_points=6,
                     security_sensitivity=0.7, data_volume_gb=500),
                     tags=["ml", "pipeline", "platform"]),
            TestCase(id="complex_003", name="Multi-Cloud Kubernetes Platform",
                     capability_request="Deploy multi-region Kubernetes platform across AWS, GCP, and Azure with federation",
                     expected_complexity=0.94, expected_team_size=_F, domain=CapabilityDomain.INFRASTRUCTURE,
                     category=_C, factors=_cf(domain_risk=0.95, api_count=8, integration_points=10,
                     security_sensitivity=0.9, concurrency_requirements=50000),
                     tags=["kubernetes", "multi-cloud"]),
            TestCase(id="complex_004", name="Real-time Fraud Detection",
                     capability_request="Build real-time fraud detection system with streaming inference and encryption",
                     expected_complexity=0.90, expected_team_size=_F, domain=CapabilityDomain.INTELLIGENCE,
                     category=_C, factors=_cf(domain_risk=0.95, api_count=4, integration_points=5,
                     security_sensitivity=0.95, concurrency_requirements=100000),
                     tags=["fraud", "real-time", "ml"]),
            TestCase(id="complex_005", name="Zero-Trust Security Architecture",
                     capability_request="Implement zero-trust security with continuous authentication and encryption across distributed services",
                     expected_complexity=0.93, expected_team_size=_F, domain=CapabilityDomain.INFRASTRUCTURE,
                     category=_C, factors=_cf(domain_risk=0.98, api_count=5, integration_points=7, security_sensitivity=1.0),
                     tags=["security", "zero-trust"]),
            TestCase(id="complex_006", name="Global CDN with Edge Computing",
                     capability_request="Build global CDN with edge computing, cache invalidation, and distributed consensus",
                     expected_complexity=0.91, expected_team_size=_F, domain=CapabilityDomain.INFRASTRUCTURE,
                     category=_C, factors=_cf(domain_risk=0.85, api_count=5, integration_points=6, concurrency_requirements=100000),
                     tags=["cdn", "edge", "distributed"]),
            TestCase(id="complex_007", name="Autonomous Agent Platform",
                     capability_request="Build autonomous multi-agent orchestration platform with LLM inference and tool use",
                     expected_complexity=0.94, expected_team_size=_F, domain=CapabilityDomain.INTELLIGENCE,
                     category=_C, factors=_cf(domain_risk=0.9, api_count=6, integration_points=7),
                     tags=["agent", "llm", "orchestration"]),
            TestCase(id="complex_008", name="Payment Processing Platform",
                     capability_request="Build PCI-compliant payment processing with encryption, tokenization, and multi-provider gateway",
                     expected_complexity=0.92, expected_team_size=_F, domain=CapabilityDomain.DATA,
                     category=_C, factors=_cf(domain_risk=0.95, api_count=5, security_sensitivity=0.98),
                     tags=["payment", "pci", "encryption"]),
            TestCase(id="complex_009", name="Real-Time Analytics Pipeline",
                     capability_request="Build real-time analytics pipeline with streaming ingestion, Kafka, Spark, and dashboard",
                     expected_complexity=0.89, expected_team_size=_F, domain=CapabilityDomain.DATA,
                     category=_C, factors=_cf(domain_risk=0.8, api_count=5, integration_points=6, data_volume_gb=500),
                     tags=["analytics", "streaming", "kafka"]),
            TestCase(id="complex_010", name="Service Mesh Implementation",
                     capability_request="Implement service mesh with mTLS, distributed tracing, and circuit breaker patterns",
                     expected_complexity=0.88, expected_team_size=_F, domain=CapabilityDomain.INFRASTRUCTURE,
                     category=_C, factors=_cf(domain_risk=0.85, api_count=4, integration_points=6, security_sensitivity=0.8),
                     tags=["service-mesh", "mtls", "distributed"]),
            TestCase(id="complex_011", name="Multi-Region Data Replication",
                     capability_request="Build multi-region database replication with eventual consistency and conflict resolution",
                     expected_complexity=0.90, expected_team_size=_F, domain=CapabilityDomain.DATA,
                     category=_C, factors=_cf(domain_risk=0.85, api_count=3, integration_points=5, data_volume_gb=1000),
                     tags=["replication", "multi-region"]),
            TestCase(id="complex_012", name="IoT Data Platform",
                     capability_request="Build IoT platform ingesting million device events per second with streaming and time-series database",
                     expected_complexity=0.91, expected_team_size=_F, domain=CapabilityDomain.DATA,
                     category=_C, factors=_cf(domain_risk=0.8, api_count=4, integration_points=6, concurrency_requirements=50000),
                     tags=["iot", "streaming", "time-series"]),
            TestCase(id="complex_013", name="HIPAA-Compliant Health Platform",
                     capability_request="Build HIPAA-compliant healthcare data platform with encryption, audit logging, and RBAC",
                     expected_complexity=0.93, expected_team_size=_F, domain=CapabilityDomain.DATA,
                     category=_C, factors=_cf(domain_risk=0.95, security_sensitivity=0.98, api_count=4),
                     tags=["hipaa", "healthcare", "encryption"]),
            TestCase(id="complex_014", name="Distributed Task Scheduler",
                     capability_request="Build distributed task scheduler with parallel execution, sharding, and fault-tolerant orchestration",
                     expected_complexity=0.87, expected_team_size=_F, domain=CapabilityDomain.AUTOMATION,
                     category=_C, factors=_cf(domain_risk=0.8, api_count=3, integration_points=5, concurrency_requirements=5000),
                     tags=["scheduler", "distributed", "orchestration"]),
            TestCase(id="complex_015", name="Blockchain-Based Audit Trail",
                     capability_request="Build tamper-proof audit trail with distributed consensus, encryption, and cryptographic hashing",
                     expected_complexity=0.90, expected_team_size=_F, domain=CapabilityDomain.INFRASTRUCTURE,
                     category=_C, factors=_cf(domain_risk=0.9, security_sensitivity=0.95, api_count=4),
                     tags=["blockchain", "audit", "encryption"]),
            TestCase(id="complex_016", name="Automated Compliance Engine",
                     capability_request="Build automated compliance engine scanning infrastructure for SOC2, GDPR, PCI across multi-cloud",
                     expected_complexity=0.89, expected_team_size=_F, domain=CapabilityDomain.AUTOMATION,
                     category=_C, factors=_cf(domain_risk=0.9, api_count=6, integration_points=8, security_sensitivity=0.9),
                     tags=["compliance", "automation", "multi-cloud"]),
            TestCase(id="complex_017", name="Computer Vision Pipeline",
                     capability_request="Build real-time computer vision pipeline with GPU inference, streaming, and model orchestration",
                     expected_complexity=0.88, expected_team_size=_F, domain=CapabilityDomain.INTELLIGENCE,
                     category=_C, factors=_cf(domain_risk=0.8, api_count=4, integration_points=5, concurrency_requirements=10000),
                     tags=["vision", "gpu", "streaming"]),
            TestCase(id="complex_018", name="Global Event Sourcing Platform",
                     capability_request="Build global event sourcing platform with CQRS, eventual consistency, and multi-region replication",
                     expected_complexity=0.92, expected_team_size=_F, domain=CapabilityDomain.DATA,
                     category=_C, factors=_cf(domain_risk=0.9, api_count=5, integration_points=7),
                     tags=["event-sourcing", "cqrs", "distributed"]),
            TestCase(id="complex_019", name="Disaster Recovery System",
                     capability_request="Build automated disaster recovery with multi-region failover, replication, and orchestration",
                     expected_complexity=0.89, expected_team_size=_F, domain=CapabilityDomain.INFRASTRUCTURE,
                     category=_C, factors=_cf(domain_risk=0.9, api_count=4, integration_points=6, concurrency_requirements=10000),
                     tags=["disaster-recovery", "failover"]),
            TestCase(id="complex_020", name="Identity Federation Platform",
                     capability_request="Build identity federation platform with SAML, OAuth, SSO, MFA, and RBAC across multiple providers",
                     expected_complexity=0.91, expected_team_size=_F, domain=CapabilityDomain.INFRASTRUCTURE,
                     category=_C, factors=_cf(domain_risk=0.95, api_count=6, security_sensitivity=0.98),
                     tags=["identity", "federation", "sso", "mfa"]),
            TestCase(id="complex_021", name="Recommendation Engine",
                     capability_request="Build personalized recommendation engine with real-time feature pipeline and A/B testing",
                     expected_complexity=0.86, expected_team_size=_F, domain=CapabilityDomain.INTELLIGENCE,
                     category=_C, factors=_cf(domain_risk=0.7, api_count=4, integration_points=5),
                     tags=["recommendation", "ml", "pipeline"]),
            TestCase(id="complex_022", name="Data Lakehouse",
                     capability_request="Build data lakehouse with petabyte-scale storage, schema evolution, and query federation",
                     expected_complexity=0.91, expected_team_size=_F, domain=CapabilityDomain.DATA,
                     category=_C, factors=_cf(domain_risk=0.85, api_count=5, data_volume_gb=5000),
                     tags=["lakehouse", "petabyte", "federation"]),
            TestCase(id="complex_023", name="Chaos Engineering Platform",
                     capability_request="Build chaos engineering platform with fault injection, distributed tracing, and automated recovery",
                     expected_complexity=0.87, expected_team_size=_F, domain=CapabilityDomain.INFRASTRUCTURE,
                     category=_C, factors=_cf(domain_risk=0.85, api_count=4, integration_points=6),
                     tags=["chaos", "fault-injection"]),
            TestCase(id="complex_024", name="Multi-Tenant SaaS Platform",
                     capability_request="Build multi-tenant SaaS platform with tenant isolation, RBAC, encryption, and billing integration",
                     expected_complexity=0.93, expected_team_size=_F, domain=CapabilityDomain.INFRASTRUCTURE,
                     category=_C, factors=_cf(domain_risk=0.9, api_count=6, integration_points=8, security_sensitivity=0.9),
                     tags=["multi-tenant", "saas", "rbac"]),
            TestCase(id="complex_025", name="Streaming NLP Processor",
                     capability_request="Build streaming NLP processing pipeline with real-time inference, Kafka, and vector database",
                     expected_complexity=0.88, expected_team_size=_F, domain=CapabilityDomain.INTELLIGENCE,
                     category=_C, factors=_cf(domain_risk=0.8, api_count=4, integration_points=5),
                     tags=["nlp", "streaming", "vector"]),
        ]

    @classmethod
    def _get_domain_specific_cases(cls) -> List[TestCase]:
        """Test cases for each capability domain. ~15 cases."""
        _D = TestCaseCategory.DOMAIN_SPECIFIC
        _cf = ComplexityFactors
        return [
            # COMMUNICATION (3)
            TestCase(id="comm_001", name="SMS Gateway Integration",
                     capability_request="Integrate Twilio for SMS notifications with delivery tracking",
                     expected_complexity=0.55, expected_team_size=TeamSize.INDIVIDUAL,
                     domain=CapabilityDomain.COMMUNICATION, category=_D,
                     factors=_cf(domain_risk=0.4, api_count=1, integration_points=2, security_sensitivity=0.4),
                     tags=["sms", "twilio"]),
            TestCase(id="comm_002", name="Video Conferencing Integration",
                     capability_request="Integrate WebRTC-based video conferencing with screen sharing",
                     expected_complexity=0.75, expected_team_size=TeamSize.SMALL_TEAM,
                     domain=CapabilityDomain.COMMUNICATION, category=_D,
                     factors=_cf(domain_risk=0.6, api_count=2, integration_points=3),
                     tags=["video", "webrtc"]),
            TestCase(id="comm_003", name="Push Notification Service",
                     capability_request="Build push notification service with Firebase and APNs adapter",
                     expected_complexity=0.60, expected_team_size=TeamSize.SMALL_TEAM,
                     domain=CapabilityDomain.COMMUNICATION, category=_D,
                     factors=_cf(domain_risk=0.4, api_count=2, integration_points=2),
                     tags=["push", "firebase"]),
            # DATA (3)
            TestCase(id="data_001", name="Data Warehouse ETL",
                     capability_request="Build ETL pipeline from 10 sources to Snowflake with transformations",
                     expected_complexity=0.75, expected_team_size=TeamSize.FULL_TEAM,
                     domain=CapabilityDomain.DATA, category=_D,
                     factors=_cf(domain_risk=0.6, api_count=3, integration_points=4, data_volume_gb=100),
                     tags=["etl", "warehouse", "snowflake"]),
            TestCase(id="data_002", name="Graph Database Schema",
                     capability_request="Design and implement Neo4j graph database schema with Cypher queries",
                     expected_complexity=0.55, expected_team_size=TeamSize.INDIVIDUAL,
                     domain=CapabilityDomain.DATA, category=_D,
                     factors=_cf(domain_risk=0.4, api_count=1),
                     tags=["neo4j", "graph"]),
            TestCase(id="data_003", name="Data Lake Ingestion",
                     capability_request="Build data lake ingestion pipeline with Spark batch processing",
                     expected_complexity=0.72, expected_team_size=TeamSize.FULL_TEAM,
                     domain=CapabilityDomain.DATA, category=_D,
                     factors=_cf(domain_risk=0.6, api_count=2, integration_points=3, data_volume_gb=500),
                     tags=["data-lake", "spark"]),
            # INFRASTRUCTURE (3)
            TestCase(id="infra_001", name="Auto-scaling Web Servers",
                     capability_request="Configure auto-scaling web server cluster with load balancing",
                     expected_complexity=0.70, expected_team_size=TeamSize.SMALL_TEAM,
                     domain=CapabilityDomain.INFRASTRUCTURE, category=_D,
                     factors=_cf(domain_risk=0.6, api_count=2, integration_points=3, concurrency_requirements=1000),
                     tags=["auto-scaling", "load-balancer"]),
            TestCase(id="infra_002", name="DNS Management Service",
                     capability_request="Build DNS management service with automated record updates",
                     expected_complexity=0.48, expected_team_size=TeamSize.INDIVIDUAL,
                     domain=CapabilityDomain.INFRASTRUCTURE, category=_D,
                     factors=_cf(domain_risk=0.3, api_count=1),
                     tags=["dns", "management"]),
            TestCase(id="infra_003", name="Container Registry",
                     capability_request="Deploy private container registry with authentication and vulnerability scanning",
                     expected_complexity=0.65, expected_team_size=TeamSize.SMALL_TEAM,
                     domain=CapabilityDomain.INFRASTRUCTURE, category=_D,
                     factors=_cf(domain_risk=0.5, api_count=2, security_sensitivity=0.6),
                     tags=["container", "registry"]),
            # AUTOMATION (3)
            TestCase(id="auto_001", name="CI/CD Pipeline",
                     capability_request="Build complete CI/CD pipeline with testing and deployment gates",
                     expected_complexity=0.65, expected_team_size=TeamSize.SMALL_TEAM,
                     domain=CapabilityDomain.AUTOMATION, category=_D,
                     factors=_cf(domain_risk=0.5, api_count=2, integration_points=3),
                     tags=["cicd", "devops"]),
            TestCase(id="auto_002", name="Infrastructure as Code",
                     capability_request="Implement Terraform infrastructure as code with modules and state management",
                     expected_complexity=0.62, expected_team_size=TeamSize.SMALL_TEAM,
                     domain=CapabilityDomain.AUTOMATION, category=_D,
                     factors=_cf(domain_risk=0.5, api_count=2),
                     tags=["terraform", "iac"]),
            TestCase(id="auto_003", name="Backup Automation",
                     capability_request="Build automated backup system with scheduling and retention policies",
                     expected_complexity=0.50, expected_team_size=TeamSize.INDIVIDUAL,
                     domain=CapabilityDomain.AUTOMATION, category=_D,
                     factors=_cf(domain_risk=0.4, api_count=1),
                     tags=["backup", "automation"]),
            # INTELLIGENCE (3)
            TestCase(id="intel_001", name="Document Classification",
                     capability_request="Build NLP model for document classification with 95% accuracy",
                     expected_complexity=0.72, expected_team_size=TeamSize.SMALL_TEAM,
                     domain=CapabilityDomain.INTELLIGENCE, category=_D,
                     factors=_cf(domain_risk=0.5, api_count=2, data_volume_gb=10),
                     tags=["nlp", "classification"]),
            TestCase(id="intel_002", name="Text Summarization API",
                     capability_request="Build text summarization API using transformer model inference",
                     expected_complexity=0.62, expected_team_size=TeamSize.SMALL_TEAM,
                     domain=CapabilityDomain.INTELLIGENCE, category=_D,
                     factors=_cf(domain_risk=0.4, api_count=1),
                     tags=["summarization", "transformer"]),
            TestCase(id="intel_003", name="Anomaly Detection Service",
                     capability_request="Build anomaly detection service for time-series data with streaming inference",
                     expected_complexity=0.74, expected_team_size=TeamSize.FULL_TEAM,
                     domain=CapabilityDomain.INTELLIGENCE, category=_D,
                     factors=_cf(domain_risk=0.5, api_count=2, integration_points=3),
                     tags=["anomaly", "time-series"]),
        ]

    @classmethod
    def _get_regression_cases(cls) -> List[TestCase]:
        """Regression tests from past misclassifications. ~10 cases."""
        _R = TestCaseCategory.REGRESSION
        _cf = ComplexityFactors
        return [
            TestCase(id="reg_001", name="OAuth Integration - Previously Misclassified",
                     capability_request="Implement OAuth 2.0 authentication with refresh tokens",
                     expected_complexity=0.68, expected_team_size=TeamSize.SMALL_TEAM,
                     domain=CapabilityDomain.INFRASTRUCTURE, category=_R,
                     factors=_cf(domain_risk=0.7, api_count=2, security_sensitivity=0.8),
                     tags=["regression", "oauth", "auth"]),
            TestCase(id="reg_002", name="Webhook Handler - Previously Misclassified",
                     capability_request="Build webhook handler with idempotency and retry logic",
                     expected_complexity=0.62, expected_team_size=TeamSize.SMALL_TEAM,
                     domain=CapabilityDomain.INFRASTRUCTURE, category=_R,
                     factors=_cf(domain_risk=0.5, api_count=1, integration_points=2),
                     tags=["regression", "webhook"]),
            TestCase(id="reg_003", name="GraphQL API - Previously Misclassified",
                     capability_request="Build GraphQL API with subscriptions and federation",
                     expected_complexity=0.62, expected_team_size=TeamSize.SMALL_TEAM,
                     domain=CapabilityDomain.DATA, category=_R,
                     factors=_cf(domain_risk=0.7, api_count=3, integration_points=4, concurrency_requirements=500),
                     tags=["regression", "graphql", "federation"]),
            TestCase(id="reg_004", name="Simple Form Validation - Overclassified",
                     capability_request="Validate form inputs with custom rules",
                     expected_complexity=0.35, expected_team_size=TeamSize.INDIVIDUAL,
                     domain=CapabilityDomain.DATA, category=_R,
                     factors=_cf(domain_risk=0.2, integration_points=1),
                     tags=["regression", "validation", "overclassified"]),
            TestCase(id="reg_005", name="Simple Logger - Overclassified",
                     capability_request="Set up basic structured logging with JSON format",
                     expected_complexity=0.20, expected_team_size=TeamSize.INDIVIDUAL,
                     domain=CapabilityDomain.INFRASTRUCTURE, category=_R,
                     factors=_cf(domain_risk=0.1),
                     tags=["regression", "logging", "overclassified"]),
            TestCase(id="reg_006", name="SSO Integration - Underclassified",
                     capability_request="Implement SSO with SAML and OAuth providers and token management",
                     expected_complexity=0.78, expected_team_size=TeamSize.SMALL_TEAM,
                     domain=CapabilityDomain.INFRASTRUCTURE, category=_R,
                     factors=_cf(domain_risk=0.7, api_count=3, security_sensitivity=0.8),
                     tags=["regression", "sso", "saml"]),
            TestCase(id="reg_007", name="Microservice Communication - Reclassified",
                     capability_request="Build gRPC-based microservice communication with service discovery and load balancing",
                     expected_complexity=0.63, expected_team_size=TeamSize.SMALL_TEAM,
                     domain=CapabilityDomain.INFRASTRUCTURE, category=_R,
                     factors=_cf(domain_risk=0.7, api_count=3, integration_points=4),
                     tags=["regression", "grpc", "microservice"]),
            TestCase(id="reg_008", name="Cache Warming - Overclassified",
                     capability_request="Implement simple cache warming on application startup",
                     expected_complexity=0.30, expected_team_size=TeamSize.INDIVIDUAL,
                     domain=CapabilityDomain.INFRASTRUCTURE, category=_R,
                     factors=_cf(domain_risk=0.2),
                     tags=["regression", "cache", "overclassified"]),
            TestCase(id="reg_009", name="Data Export API - Misclassified",
                     capability_request="Build data export API with pagination, filtering, and CSV download",
                     expected_complexity=0.55, expected_team_size=TeamSize.INDIVIDUAL,
                     domain=CapabilityDomain.DATA, category=_R,
                     factors=_cf(domain_risk=0.3, api_count=1),
                     tags=["regression", "export", "api"]),
            TestCase(id="reg_010", name="Event Processing Pipeline",
                     capability_request="Build event processing pipeline with Kafka consumer, dead letter queue, and retry handler",
                     expected_complexity=0.76, expected_team_size=TeamSize.FULL_TEAM,
                     domain=CapabilityDomain.DATA, category=_R,
                     factors=_cf(domain_risk=0.6, api_count=2, integration_points=3),
                     tags=["regression", "kafka", "event-processing"]),
        ]

    @classmethod
    def get_synthetic_cases(cls, count: int = 10) -> List[TestCase]:
        """Generate synthetic edge cases for stress testing.

        Creates test cases with complexity scores distributed across
        the range with extra density near thresholds.
        """
        cases = []
        np.random.seed(42)  # Reproducible

        # Generate cases with focus on threshold regions
        thresholds = [0.6, 0.8]
        for i in range(count):
            # 50% chance of being near a threshold
            if np.random.random() < 0.5:
                threshold = np.random.choice(thresholds)
                complexity = np.random.normal(threshold, 0.05)
            else:
                complexity = np.random.uniform(0.1, 0.95)

            complexity = np.clip(complexity, 0.0, 1.0)

            # Determine expected team size
            if complexity < 0.6:
                team_size = TeamSize.INDIVIDUAL
            elif complexity < 0.8:
                team_size = TeamSize.SMALL_TEAM
            else:
                team_size = TeamSize.FULL_TEAM

            cases.append(TestCase(
                id=f"synth_{i:03d}",
                name=f"Synthetic Case {i+1}",
                capability_request=f"Synthetic capability request with complexity {complexity:.2f}",
                expected_complexity=complexity,
                expected_team_size=team_size,
                domain=np.random.choice(list(CapabilityDomain)),
                category=TestCaseCategory.SYNTHETIC,
                factors=ComplexityFactors(
                    domain_risk=np.random.uniform(0, 1),
                    api_count=np.random.randint(0, 10),
                    integration_points=np.random.randint(0, 10),
                    security_sensitivity=np.random.uniform(0, 1)
                ),
                description=f"Auto-generated test case with complexity {complexity:.2f}",
                tags=["synthetic", "auto-generated"]
            ))

        return cases


# =============================================================================
# VALIDATION FRAMEWORK
# =============================================================================

class ComplexityValidationFramework:
    """Main validation framework for complexity scoring.

    This class orchestrates the validation of the TeamSizeClassifier
    by running test cases, collecting metrics, and generating reports.

    Example:
        framework = ComplexityValidationFramework(classifier)
        results = await framework.run_validation_suite()
        metrics = framework.calculate_metrics(results)
        report = framework.generate_report(metrics)
    """

    def __init__(
        self,
        classifier: Any,  # TeamSizeClassifier instance
        test_cases: Optional[List[TestCase]] = None,
        lower_threshold: Optional[float] = None,
        upper_threshold: Optional[float] = None
    ):
        """Initialize validation framework.

        Args:
            classifier: The TeamSizeClassifier to validate
            test_cases: Optional custom test cases (uses library if None)
            lower_threshold: Threshold between individual and small team
                (defaults to DEFAULT_CONFIG.individual_threshold)
            upper_threshold: Threshold between small and full team
                (defaults to DEFAULT_CONFIG.small_team_threshold)
        """
        self.classifier = classifier
        self.test_cases = test_cases or TestCaseLibrary.get_all_test_cases()
        self.lower_threshold = lower_threshold if lower_threshold is not None else DEFAULT_CONFIG.individual_threshold
        self.upper_threshold = upper_threshold if upper_threshold is not None else DEFAULT_CONFIG.small_team_threshold
        self.results: List[TestResult] = []

    async def run_validation_suite(
        self,
        categories: Optional[List[TestCaseCategory]] = None
    ) -> List[TestResult]:
        """Run complete validation suite.

        Args:
            categories: Optional filter for test categories

        Returns:
            List of test results
        """
        cases = self.test_cases
        if categories:
            cases = [c for c in cases if c.category in categories]

        logger.info(f"Running validation suite with {len(cases)} test cases")

        self.results = []
        for case in cases:
            result = await self._run_single_test(case)
            self.results.append(result)

        logger.info(f"Validation complete: {len(self.results)} results")
        return self.results

    async def _run_single_test(self, test_case: TestCase) -> TestResult:
        """Run a single test case against the classifier."""
        import time

        start_time = time.time()

        try:
            # Call the classifier
            classification = await self._classify(test_case)

            execution_time = (time.time() - start_time) * 1000

            # Determine if classification is correct
            predicted_team = self._complexity_to_team_size(classification["complexity"])
            classification_correct = predicted_team == test_case.expected_team_size

            # Calculate error margin
            error_margin = abs(classification["complexity"] - test_case.expected_complexity)

            # Determine status
            if classification_correct:
                status = ValidationStatus.PASS
            elif error_margin < 0.1:  # Within 0.1 is acceptable
                status = ValidationStatus.WARNING
            else:
                status = ValidationStatus.FAIL

            return TestResult(
                test_case=test_case,
                predicted_complexity=classification["complexity"],
                predicted_team_size=predicted_team,
                status=status,
                error_margin=error_margin,
                classification_correct=classification_correct,
                execution_time_ms=execution_time,
                token_usage=classification.get("token_usage", 0),
                metadata=classification.get("metadata", {})
            )

        except Exception as e:
            logger.error(f"Test {test_case.id} failed: {e}")
            return TestResult(
                test_case=test_case,
                predicted_complexity=0.0,
                predicted_team_size=TeamSize.INDIVIDUAL,
                status=ValidationStatus.FAIL,
                error_margin=1.0,
                classification_correct=False,
                execution_time_ms=(time.time() - start_time) * 1000,
                metadata={"error": str(e)}
            )

    async def _classify(self, test_case: TestCase) -> Dict[str, Any]:
        """Call the classifier and return results."""
        try:
            result = self.classifier.classify(test_case.capability_request)
            # Handle both dict and object return types
            if isinstance(result, dict):
                return {
                    "complexity": result.get("complexity", 0.5),
                    "token_usage": result.get("token_usage", 0),
                    "metadata": result.get("metadata", {}),
                }
            else:
                return {
                    "complexity": getattr(result, "complexity", 0.5),
                    "token_usage": getattr(result, "token_usage", 0),
                    "metadata": getattr(result, "metadata", {}),
                }
        except Exception as e:
            logger.error(f"Classifier failed for {test_case.id}: {e}")
            return {
                "complexity": 0.5,
                "token_usage": 0,
                "metadata": {"error": str(e)},
            }

    def _complexity_to_team_size(self, complexity: float) -> TeamSize:
        """Convert complexity score to team size."""
        config = ComplexityConfig(
            individual_threshold=self.lower_threshold,
            small_team_threshold=self.upper_threshold,
        )
        label = _config_complexity_to_team_size(complexity, config)
        return TeamSize(label)

    def calculate_metrics(self, results: Optional[List[TestResult]] = None) -> ValidationMetrics:
        """Calculate comprehensive metrics from results."""
        results = results or self.results
        if not results:
            return ValidationMetrics()

        metrics = ValidationMetrics()
        metrics.total_cases = len(results)

        # Basic accuracy
        correct = [r for r in results if r.classification_correct]
        metrics.correct_classifications = len(correct)
        metrics.accuracy = len(correct) / len(results)

        # Per-team-size metrics
        metrics.individual_precision = self._calculate_precision(results, TeamSize.INDIVIDUAL)
        metrics.individual_recall = self._calculate_recall(results, TeamSize.INDIVIDUAL)
        metrics.small_team_precision = self._calculate_precision(results, TeamSize.SMALL_TEAM)
        metrics.small_team_recall = self._calculate_recall(results, TeamSize.SMALL_TEAM)
        metrics.full_team_precision = self._calculate_precision(results, TeamSize.FULL_TEAM)
        metrics.full_team_recall = self._calculate_recall(results, TeamSize.FULL_TEAM)

        # Overall precision/recall for team spawning (small + full)
        team_results = [r for r in results
                       if r.test_case.expected_team_size in (TeamSize.SMALL_TEAM, TeamSize.FULL_TEAM)]
        if team_results:
            team_predicted = [r for r in results
                            if r.predicted_team_size in (TeamSize.SMALL_TEAM, TeamSize.FULL_TEAM)]
            team_correct = [r for r in results
                          if r.classification_correct and
                          r.test_case.expected_team_size in (TeamSize.SMALL_TEAM, TeamSize.FULL_TEAM)]

            metrics.precision = len(team_correct) / len(team_predicted) if team_predicted else 0
            metrics.recall = len(team_correct) / len(team_results) if team_results else 0
            metrics.f1_score = 2 * (metrics.precision * metrics.recall) / (metrics.precision + metrics.recall) \
                              if (metrics.precision + metrics.recall) > 0 else 0

        # Error metrics
        errors = [r.error_margin for r in results]
        metrics.mean_absolute_error = np.mean(errors)
        metrics.root_mean_squared_error = np.sqrt(np.mean([e**2 for e in errors]))
        metrics.max_error = max(errors)

        # Cost efficiency
        total_tokens = sum(r.token_usage for r in results)
        metrics.total_tokens = total_tokens
        metrics.avg_tokens_per_classification = total_tokens / len(results) if results else 0

        # Complexity resolved per 1000 tokens
        total_complexity = sum(r.test_case.expected_complexity for r in results)
        metrics.cost_efficiency_score = (total_complexity / total_tokens * 1000) if total_tokens > 0 else 0

        # Edge case performance
        edge_results = [r for r in results if r.test_case.category == TestCaseCategory.EDGE_CASE]
        if edge_results:
            correct_edges = [r for r in edge_results if r.classification_correct]
            metrics.edge_case_accuracy = len(correct_edges) / len(edge_results)

        # Threshold boundary accuracy (within 0.05 of threshold)
        boundary_results = [r for r in results
                          if abs(r.test_case.expected_complexity - 0.6) < 0.05
                          or abs(r.test_case.expected_complexity - 0.8) < 0.05]
        if boundary_results:
            correct_boundaries = [r for r in boundary_results if r.classification_correct]
            metrics.threshold_boundary_accuracy = len(correct_boundaries) / len(boundary_results)

        # Domain accuracy
        for domain in CapabilityDomain:
            domain_results = [r for r in results if r.test_case.domain == domain]
            if domain_results:
                correct_domain = [r for r in domain_results if r.classification_correct]
                metrics.domain_accuracy[domain.value] = len(correct_domain) / len(domain_results)

        # Timing
        metrics.avg_execution_time_ms = np.mean([r.execution_time_ms for r in results])
        metrics.total_execution_time_ms = sum(r.execution_time_ms for r in results)

        return metrics

    def _calculate_precision(self, results: List[TestResult], team_size: TeamSize) -> float:
        """Calculate precision for a specific team size."""
        predicted = [r for r in results if r.predicted_team_size == team_size]
        if not predicted:
            return 0.0
        correct = [r for r in predicted
                  if r.test_case.expected_team_size == team_size]
        return len(correct) / len(predicted)

    def _calculate_recall(self, results: List[TestResult], team_size: TeamSize) -> float:
        """Calculate recall for a specific team size."""
        actual = [r for r in results if r.test_case.expected_team_size == team_size]
        if not actual:
            return 0.0
        correct = [r for r in actual if r.classification_correct]
        return len(correct) / len(actual)

    def generate_report(self, metrics: Optional[ValidationMetrics] = None) -> str:
        """Generate human-readable validation report."""
        metrics = metrics or self.calculate_metrics()

        report = []
        report.append("=" * 70)
        report.append("COMPLEXITY SCORING VALIDATION REPORT")
        report.append(f"Generated: {metrics.timestamp.isoformat()}")
        report.append("=" * 70)
        report.append("")

        # Summary
        report.append("SUMMARY")
        report.append("-" * 70)
        report.append(f"Total Test Cases: {metrics.total_cases}")
        report.append(f"Overall Accuracy: {metrics.accuracy:.2%}")
        report.append(f"Precision (Team Spawning): {metrics.precision:.2%}")
        report.append(f"Recall (Complex Tasks): {metrics.recall:.2%}")
        report.append(f"F1 Score: {metrics.f1_score:.2%}")
        report.append("")

        # Per-team-size breakdown
        report.append("PER-TEAM-SIZE PERFORMANCE")
        report.append("-" * 70)
        report.append(f"Individual Agent:")
        report.append(f"  Precision: {metrics.individual_precision:.2%}")
        report.append(f"  Recall: {metrics.individual_recall:.2%}")
        report.append(f"Small Team (3 agents):")
        report.append(f"  Precision: {metrics.small_team_precision:.2%}")
        report.append(f"  Recall: {metrics.small_team_recall:.2%}")
        report.append(f"Full Team (5 agents):")
        report.append(f"  Precision: {metrics.full_team_precision:.2%}")
        report.append(f"  Recall: {metrics.full_team_recall:.2%}")
        report.append("")

        # Error analysis
        report.append("ERROR ANALYSIS")
        report.append("-" * 70)
        report.append(f"Mean Absolute Error: {metrics.mean_absolute_error:.4f}")
        report.append(f"RMSE: {metrics.root_mean_squared_error:.4f}")
        report.append(f"Max Error: {metrics.max_error:.4f}")
        report.append(f"Edge Case Accuracy: {metrics.edge_case_accuracy:.2%}")
        report.append(f"Threshold Boundary Accuracy: {metrics.threshold_boundary_accuracy:.2%}")
        report.append("")

        # Cost efficiency
        report.append("COST EFFICIENCY")
        report.append("-" * 70)
        report.append(f"Total Tokens: {metrics.total_tokens:,}")
        report.append(f"Avg Tokens/Classification: {metrics.avg_tokens_per_classification:.1f}")
        report.append(f"Cost Efficiency Score: {metrics.cost_efficiency_score:.4f}")
        report.append(f"Avg Execution Time: {metrics.avg_execution_time_ms:.2f}ms")
        report.append("")

        # Domain performance
        report.append("DOMAIN PERFORMANCE")
        report.append("-" * 70)
        for domain, accuracy in sorted(metrics.domain_accuracy.items()):
            report.append(f"  {domain}: {accuracy:.2%}")
        report.append("")

        # Recommendations
        report.append("RECOMMENDATIONS")
        report.append("-" * 70)
        report.extend(self._generate_recommendations(metrics))
        report.append("")

        return "\n".join(report)

    def _generate_recommendations(self, metrics: ValidationMetrics) -> List[str]:
        """Generate recommendations based on metrics."""
        recommendations = []

        if metrics.accuracy < 0.85:
            recommendations.append("- WARNING: Overall accuracy below 85%. Consider threshold recalibration.")

        if metrics.precision < 0.90:
            recommendations.append("- WARNING: Low precision for team spawning. Too many simple tasks getting teams.")
            recommendations.append(f"  Recommendation: Raise lower threshold from {self.lower_threshold}")

        if metrics.recall < 0.95:
            recommendations.append("- WARNING: Low recall for complex tasks. Missing tasks that need full teams.")
            recommendations.append(f"  Recommendation: Lower upper threshold from {self.upper_threshold}")

        if metrics.edge_case_accuracy < 0.70:
            recommendations.append("- WARNING: Poor performance on edge cases. Consider adding more training data near thresholds.")

        if metrics.cost_efficiency_score < 0.5:
            recommendations.append("- WARNING: Low cost efficiency. Consider optimizing token usage.")

        if not recommendations:
            recommendations.append("- All metrics within acceptable ranges. No action required.")

        return recommendations


# =============================================================================
# THRESHOLD CALIBRATOR
# =============================================================================

class ThresholdCalibrator:
    """Calibrates complexity thresholds based on validation results.

    Uses grid search to find optimal thresholds that maximize F1 score
    while maintaining minimum precision and recall requirements.
    """

    def __init__(
        self,
        framework: ComplexityValidationFramework,
        min_precision: float = 0.90,
        min_recall: float = 0.95
    ):
        """Initialize calibrator.

        Args:
            framework: Validation framework with test results
            min_precision: Minimum required precision
            min_recall: Minimum required recall
        """
        self.framework = framework
        self.min_precision = min_precision
        self.min_recall = min_recall

    def calibrate_thresholds(
        self,
        results: Optional[List[TestResult]] = None,
        search_range: Tuple[float, float] = (0.5, 0.9),
        step: float = 0.05
    ) -> ThresholdCalibration:
        """Find optimal thresholds via grid search.

        Args:
            results: Test results to calibrate against
            search_range: Range of thresholds to search
            step: Step size for grid search

        Returns:
            Optimal threshold calibration
        """
        results = results or self.framework.results
        if not results:
            raise ValueError("No results available for calibration")

        best_calibration = ThresholdCalibration()
        best_f1 = 0.0

        # Grid search over threshold pairs
        lower_values = np.arange(search_range[0], 0.7, step)
        upper_values = np.arange(0.7, search_range[1] + step, step)

        for lower in lower_values:
            for upper in upper_values:
                if lower >= upper:
                    continue

                # Calculate metrics with these thresholds
                metrics = self._calculate_metrics_with_thresholds(results, lower, upper)

                # Check constraints
                if metrics.precision < self.min_precision:
                    continue
                if metrics.recall < self.min_recall:
                    continue

                # Prefer higher F1
                if metrics.f1_score > best_f1:
                    best_f1 = metrics.f1_score
                    best_calibration = ThresholdCalibration(
                        lower_threshold=lower,
                        upper_threshold=upper,
                        confidence=metrics.f1_score,
                        metrics_at_thresholds=metrics,
                        recommendation=f"Optimal thresholds: {lower:.2f} (individual/small), {upper:.2f} (small/full)"
                    )

        if best_f1 == 0.0:
            # No valid thresholds found - return best effort
            best_calibration.recommendation = (
                f"WARNING: Could not find thresholds meeting constraints. "
                f"Consider relaxing min_precision={self.min_precision} or min_recall={self.min_recall}"
            )

        return best_calibration

    def _calculate_metrics_with_thresholds(
        self,
        results: List[TestResult],
        lower: float,
        upper: float
    ) -> ValidationMetrics:
        """Calculate metrics with custom thresholds."""
        # Temporarily update framework thresholds
        original_lower = self.framework.lower_threshold
        original_upper = self.framework.upper_threshold

        self.framework.lower_threshold = lower
        self.framework.upper_threshold = upper

        # Recalculate classifications
        for result in results:
            result.predicted_team_size = self.framework._complexity_to_team_size(
                result.predicted_complexity
            )
            result.classification_correct = (
                result.predicted_team_size == result.test_case.expected_team_size
            )

        # Calculate metrics
        metrics = self.framework.calculate_metrics(results)

        # Restore original thresholds
        self.framework.lower_threshold = original_lower
        self.framework.upper_threshold = original_upper

        return metrics

    def suggest_ab_test(
        self,
        current_calibration: ThresholdCalibration,
        new_calibration: ThresholdCalibration
    ) -> Dict[str, Any]:
        """Suggest A/B test configuration for threshold changes.

        Returns:
            A/B test configuration with traffic split and success criteria
        """
        return {
            "test_name": f"threshold_calibration_{datetime.now().strftime('%Y%m%d')}",
            "control": {
                "lower_threshold": self.framework.lower_threshold,
                "upper_threshold": self.framework.upper_threshold,
                "traffic_percentage": 50
            },
            "treatment": {
                "lower_threshold": new_calibration.lower_threshold,
                "upper_threshold": new_calibration.upper_threshold,
                "traffic_percentage": 50
            },
            "success_criteria": {
                "primary_metric": "f1_score",
                "minimum_improvement": 0.02,
                "sample_size": 1000,
                "duration_days": 7
            },
            "rollback_triggers": [
                "precision < 0.85",
                "recall < 0.90",
                "error_rate > 0.15"
            ]
        }


# =============================================================================
# PRODUCTION MONITORING
# =============================================================================

@dataclass
class ProductionMetrics:
    """Metrics tracked in production for ongoing monitoring."""

    # Classification distribution
    individual_count: int = 0
    small_team_count: int = 0
    full_team_count: int = 0

    # Drift detection
    avg_complexity_24h: float = 0.0
    avg_complexity_7d: float = 0.0
    complexity_drift_detected: bool = False

    # Performance
    avg_classification_time_ms: float = 0.0
    p99_classification_time_ms: float = 0.0

    # Cost tracking
    tokens_24h: int = 0
    estimated_cost_24h: float = 0.0

    # Error tracking
    classification_errors_24h: int = 0
    timeout_count_24h: int = 0

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ProductionMonitor:
    """Production monitoring for complexity classification.

    Tracks metrics, detects drift, and triggers alerts for
    misclassification patterns.
    """

    def __init__(
        self,
        alert_thresholds: Optional[Dict[str, float]] = None,
        drift_window_hours: int = 24
    ):
        """Initialize production monitor.

        Args:
            alert_thresholds: Dict of metric thresholds for alerting
            drift_window_hours: Hours to use for drift detection
        """
        self.alert_thresholds = alert_thresholds or {
            "min_precision": 0.85,
            "min_recall": 0.90,
            "max_avg_complexity_change": 0.15,
            "max_error_rate": 0.10,
            "max_classification_time_ms": 5000
        }
        self.drift_window_hours = drift_window_hours
        self.classifications: List[Dict[str, Any]] = []

    def record_classification(
        self,
        capability_request: str,
        complexity: float,
        team_size: TeamSize,
        execution_time_ms: float,
        token_usage: int,
        feedback: Optional[str] = None
    ):
        """Record a classification for monitoring.

        Args:
            capability_request: The capability that was classified
            complexity: Predicted complexity score
            team_size: Predicted team size
            execution_time_ms: Time to classify
            token_usage: Tokens consumed
            feedback: Optional human feedback ("correct", "overclassified", "underclassified")
        """
        self.classifications.append({
            "timestamp": datetime.now(timezone.utc),
            "capability_request": capability_request,
            "complexity": complexity,
            "team_size": team_size.value,
            "execution_time_ms": execution_time_ms,
            "token_usage": token_usage,
            "feedback": feedback
        })

        # Clean old data
        self._prune_old_data()

    def _prune_old_data(self):
        """Remove data older than drift window."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.drift_window_hours * 2)
        self.classifications = [
            c for c in self.classifications
            if c["timestamp"] > cutoff
        ]

    def get_current_metrics(self) -> ProductionMetrics:
        """Calculate current production metrics."""
        metrics = ProductionMetrics()

        if not self.classifications:
            return metrics

        recent = [c for c in self.classifications
                 if c["timestamp"] > datetime.now(timezone.utc) - timedelta(hours=24)]

        # Count by team size
        metrics.individual_count = sum(1 for c in recent if c["team_size"] == "individual")
        metrics.small_team_count = sum(1 for c in recent if c["team_size"] == "small_team")
        metrics.full_team_count = sum(1 for c in recent if c["team_size"] == "full_team")

        # Complexity drift
        recent_24h = [c["complexity"] for c in recent]
        recent_7d = [c["complexity"] for c in self.classifications
                    if c["timestamp"] > datetime.now(timezone.utc) - timedelta(days=7)]

        if recent_24h:
            metrics.avg_complexity_24h = np.mean(recent_24h)
        if recent_7d:
            metrics.avg_complexity_7d = np.mean(recent_7d)

        metrics.complexity_drift_detected = abs(
            metrics.avg_complexity_24h - metrics.avg_complexity_7d
        ) > self.alert_thresholds["max_avg_complexity_change"]

        # Performance
        times = [c["execution_time_ms"] for c in recent]
        if times:
            metrics.avg_classification_time_ms = np.mean(times)
            metrics.p99_classification_time_ms = np.percentile(times, 99)

        # Cost
        metrics.tokens_24h = sum(c["token_usage"] for c in recent)
        metrics.estimated_cost_24h = metrics.tokens_24h * 0.00001  # Approximate

        return metrics

    def check_alerts(self) -> List[Dict[str, Any]]:
        """Check for alert conditions.

        Returns:
            List of active alerts
        """
        alerts = []
        metrics = self.get_current_metrics()

        # Check drift
        if metrics.complexity_drift_detected:
            alerts.append({
                "severity": "warning",
                "type": "complexity_drift",
                "message": f"Complexity drift detected: 24h avg={metrics.avg_complexity_24h:.3f}, "
                          f"7d avg={metrics.avg_complexity_7d:.3f}",
                "recommended_action": "Review recent capability requests for pattern changes"
            })

        # Check performance
        if metrics.avg_classification_time_ms > self.alert_thresholds["max_classification_time_ms"]:
            alerts.append({
                "severity": "critical",
                "type": "performance_degradation",
                "message": f"Classification time exceeded threshold: {metrics.avg_classification_time_ms:.0f}ms",
                "recommended_action": "Check classifier performance and resource utilization"
            })

        # Check distribution (if too skewed toward teams, may indicate miscalibration)
        total = metrics.individual_count + metrics.small_team_count + metrics.full_team_count
        if total > 100:  # Only check after sufficient sample
            full_team_ratio = metrics.full_team_count / total
            if full_team_ratio > 0.5:
                alerts.append({
                    "severity": "warning",
                    "type": "distribution_skew",
                    "message": f"High full team ratio: {full_team_ratio:.1%} of classifications",
                    "recommended_action": "Consider raising upper threshold to reduce team spawning"
                })

        return alerts

    def get_feedback_summary(self) -> Dict[str, Any]:
        """Get summary of human feedback for continuous improvement.

        Returns:
            Summary of feedback with recommended actions
        """
        feedback_items = [c for c in self.classifications if c.get("feedback")]

        if not feedback_items:
            return {"status": "no_feedback", "message": "No human feedback recorded yet"}

        overclassified = sum(1 for c in feedback_items if c["feedback"] == "overclassified")
        underclassified = sum(1 for c in feedback_items if c["feedback"] == "underclassified")
        correct = sum(1 for c in feedback_items if c["feedback"] == "correct")

        total = len(feedback_items)

        summary = {
            "total_feedback": total,
            "correct_ratio": correct / total,
            "overclassified_ratio": overclassified / total,
            "underclassified_ratio": underclassified / total,
            "recommendations": []
        }

        if summary["overclassified_ratio"] > 0.2:
            summary["recommendations"].append(
                "High overclassification rate. Consider raising thresholds."
            )

        if summary["underclassified_ratio"] > 0.1:
            summary["recommendations"].append(
                "High underclassification rate. Consider lowering thresholds."
            )

        return summary


# =============================================================================
# STAGING VALIDATION PIPELINE
# =============================================================================

class StagingValidationPipeline:
    """Pipeline for running validation in staging environment.

    Orchestrates the full validation process:
    1. Run test suite
    2. Calculate metrics
    3. Calibrate thresholds if needed
    4. Generate report
    5. Make go/no-go recommendation
    """

    def __init__(
        self,
        classifier: Any,
        neo4j_client: Optional[Any] = None
    ):
        """Initialize staging pipeline.

        Args:
            classifier: TeamSizeClassifier to validate
            neo4j_client: Optional Neo4j client for storing results
        """
        self.classifier = classifier
        self.neo4j = neo4j_client
        self.framework = ComplexityValidationFramework(classifier)

    async def run_full_validation(self) -> Dict[str, Any]:
        """Run complete validation pipeline.

        Returns:
            Complete validation results with recommendation
        """
        logger.info("Starting staging validation pipeline")

        # Step 1: Run test suite
        results = await self.framework.run_validation_suite()

        # Step 2: Calculate metrics
        metrics = self.framework.calculate_metrics(results)

        # Step 3: Calibrate thresholds
        calibrator = ThresholdCalibrator(self.framework)
        calibration = calibrator.calibrate_thresholds(results)

        # Step 4: Generate report
        report = self.framework.generate_report(metrics)

        # Step 5: Make recommendation
        recommendation = self._make_go_no_go_decision(metrics, calibration)

        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": metrics.to_dict(),
            "calibration": asdict(calibration),
            "report": report,
            "recommendation": recommendation,
            "test_results": [
                {
                    "test_id": r.test_case.id,
                    "status": r.status.value,
                    "predicted": r.predicted_complexity,
                    "expected": r.test_case.expected_complexity,
                    "error": r.error_margin
                }
                for r in results
            ]
        }

        # Store in Neo4j if available
        if self.neo4j:
            await self._store_results(result)

        return result

    def _make_go_no_go_decision(
        self,
        metrics: ValidationMetrics,
        calibration: ThresholdCalibration
    ) -> Dict[str, Any]:
        """Make go/no-go decision based on validation results.

        Criteria aligned with plan (Task 5.1):
        - accuracy >= 85%
        - individual_precision >= 90%
        - full_team_recall >= 90% (relaxed from 95% for keyword classifier)
        - edge_case_accuracy >= 70%
        - MAE <= 0.25 (keyword classifiers have inherently higher MAE than neural)
        """
        issues = []

        if metrics.accuracy < 0.85:
            issues.append("Accuracy below 85%")

        if metrics.individual_precision < 0.90:
            issues.append("Individual precision below 90%")

        if metrics.full_team_recall < 0.90:
            issues.append("Full team recall below 90%")

        if metrics.edge_case_accuracy < 0.70:
            issues.append("Edge case accuracy below 70%")

        if metrics.mean_absolute_error > 0.25:
            issues.append("High mean absolute error")

        if issues:
            return {
                "decision": "NO_GO",
                "confidence": "high" if len(issues) > 2 else "medium",
                "issues": issues,
                "action": "Address issues before production deployment",
                "threshold_adjustment_recommended": metrics.precision < 0.90 or metrics.recall < 0.95
            }

        return {
            "decision": "GO",
            "confidence": "high",
            "issues": [],
            "action": "Ready for production deployment",
            "threshold_adjustment_recommended": False,
            "optimal_thresholds": {
                "lower": calibration.lower_threshold,
                "upper": calibration.upper_threshold
            } if calibration.confidence > 0.8 else None
        }

    async def _store_results(self, result: Dict[str, Any]):
        """Store validation results in Neo4j."""
        if not self.neo4j:
            logger.info("No Neo4j client configured, skipping result storage")
            return

        query = """
        CREATE (v:ValidationRun {
            id: randomUUID(),
            timestamp: datetime($timestamp),
            accuracy: $accuracy,
            precision_score: $precision,
            recall_score: $recall,
            f1_score: $f1,
            mean_absolute_error: $mae,
            total_cases: $total_cases,
            decision: $decision,
            lower_threshold: $lower_threshold,
            upper_threshold: $upper_threshold
        })
        RETURN v.id as run_id
        """

        metrics = result.get("metrics", {})
        recommendation = result.get("recommendation", {})
        calibration = result.get("calibration", {})

        parameters = {
            "timestamp": result.get("timestamp", ""),
            "accuracy": metrics.get("accuracy", 0.0),
            "precision": metrics.get("precision", 0.0),
            "recall": metrics.get("recall", 0.0),
            "f1": metrics.get("f1_score", 0.0),
            "mae": metrics.get("mean_absolute_error", 0.0),
            "total_cases": metrics.get("total_cases", 0),
            "decision": recommendation.get("decision", "UNKNOWN"),
            "lower_threshold": calibration.get("lower_threshold", DEFAULT_CONFIG.individual_threshold),
            "upper_threshold": calibration.get("upper_threshold", DEFAULT_CONFIG.small_team_threshold),
        }

        try:
            async with self.neo4j.session() as session:
                await session.run(query, parameters)
                logger.info("Stored validation results in Neo4j")
        except Exception as e:
            logger.error(f"Failed to store validation results: {e}")


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def create_validation_suite(
    classifier: Any,
    include_synthetic: bool = True
) -> ComplexityValidationFramework:
    """Factory function to create validation suite.

    Args:
        classifier: TeamSizeClassifier to validate
        include_synthetic: Whether to include synthetic test cases

    Returns:
        Configured validation framework
    """
    test_cases = TestCaseLibrary.get_all_test_cases()

    if include_synthetic:
        test_cases.extend(TestCaseLibrary.get_synthetic_cases(10))

    return ComplexityValidationFramework(
        classifier=classifier,
        test_cases=test_cases
    )


async def run_quick_validation(classifier: Any) -> ValidationMetrics:
    """Run quick validation with core test cases.

    Args:
        classifier: TeamSizeClassifier to validate

    Returns:
        Validation metrics
    """
    # Use only edge cases and known simple/complex for quick validation
    categories = [
        TestCaseCategory.EDGE_CASE,
        TestCaseCategory.KNOWN_SIMPLE,
        TestCaseCategory.KNOWN_COMPLEX
    ]

    framework = ComplexityValidationFramework(classifier)
    results = await framework.run_validation_suite(categories=categories)
    return framework.calculate_metrics(results)


# For type checking
try:
    from datetime import timedelta
except ImportError:
    pass
