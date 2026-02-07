"""
Shared Data Models for Complexity Scoring System.

This module provides canonical data class definitions for the complexity
validation framework. All other complexity modules should import from here
to ensure type consistency and avoid duplication.

Author: Claude (Anthropic)
Date: 2026-02-06 (Extracted from complexity_validation_framework.py)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List

import numpy as np


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
    INDIVIDUAL = "individual"      # < individual_threshold complexity (default 0.21)
    SMALL_TEAM = "small_team"      # individual_threshold to small_team_threshold (default 0.21-0.64)
    FULL_TEAM = "full_team"        # >= small_team_threshold complexity (default >= 0.64)


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
        - Balanced Accuracy: Mean of per-class recall (handles class imbalance)
        - Precision: No false positives for team spawning
        - Recall: No missed complex tasks
        - F1 Score: Harmonic mean of precision and recall
        - Cost Efficiency: Token usage vs complexity correlation
    """
    # Classification metrics
    total_cases: int = 0
    correct_classifications: int = 0
    accuracy: float = 0.0
    balanced_accuracy: float = 0.0  # Mean of per-class recall (handles class imbalance)

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
    threshold_boundary_accuracy: float = 0.0  # Cases near individual_threshold and small_team_threshold

    # Domain performance
    domain_accuracy: Dict[str, float] = field(default_factory=dict)

    # Timing
    avg_execution_time_ms: float = 0.0
    total_execution_time_ms: float = 0.0
