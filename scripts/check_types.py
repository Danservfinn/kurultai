"""
Pre-Flight Check Type Definitions

Common types and enums used across all pre-flight check modules.
This module is imported by all check modules and the main pre_flight_check module.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

# Configure logging
logger = logging.getLogger(__name__)


class CheckStatus(Enum):
    """Status of a pre-flight check."""
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


class CheckCategory(Enum):
    """Categories of pre-flight checks."""
    ENVIRONMENT = "environment"
    NEO4J = "neo4j"
    AUTHENTICATION = "authentication"
    AGENTS = "agents"


@dataclass
class CheckResult:
    """
    Result of a single pre-flight check.

    Attributes:
        check_id: Unique check identifier (e.g., ENV-001)
        category: Check category
        description: Human-readable description
        critical: Whether this is a critical check
        status: Check status (pass/fail/warn/skip)
        expected: Expected value description
        actual: Actual value found
        output: Status output message
        timestamp: ISO format timestamp
        duration_ms: Check duration in milliseconds
        details: Additional details dict
    """
    check_id: str
    category: CheckCategory
    description: str
    critical: bool = False
    status: CheckStatus = CheckStatus.PASS
    expected: str = ""
    actual: str = ""
    output: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    duration_ms: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "check_id": self.check_id,
            "category": self.category.value,
            "description": self.description,
            "critical": self.critical,
            "status": self.status.value,
            "expected": self.expected,
            "actual": self.actual,
            "output": self.output,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "details": self.details
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckResult":
        """Create from dictionary."""
        return cls(
            check_id=data["check_id"],
            category=CheckCategory(data["category"]),
            description=data["description"],
            critical=data.get("critical", False),
            status=CheckStatus(data["status"]),
            expected=data.get("expected", ""),
            actual=data.get("actual", ""),
            output=data.get("output", ""),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            duration_ms=data.get("duration_ms", 0.0),
            details=data.get("details", {})
        )


@dataclass
class GoNoGoDecision:
    """
    Go/No-Go decision for production deployment.

    Attributes:
        decision: "GO" or "NO-GO"
        pass_rate: Percentage of checks that passed
        critical_passed: Whether all critical checks passed
        total_checks: Total number of checks run
        passed_checks: Number of checks that passed
        failed_checks: Number of checks that failed
        warning_checks: Number of checks with warnings
        skipped_checks: Number of skipped checks
        reasoning: Human-readable reasoning for the decision
        blockers: List of blocking issues
        recommendations: List of recommendations
    """
    decision: str  # "GO" or "NO-GO"
    pass_rate: float
    critical_passed: bool
    total_checks: int
    passed_checks: int
    failed_checks: int
    warning_checks: int
    skipped_checks: int
    reasoning: str
    blockers: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "decision": self.decision,
            "pass_rate": self.pass_rate,
            "critical_passed": self.critical_passed,
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "warning_checks": self.warning_checks,
            "skipped_checks": self.skipped_checks,
            "reasoning": self.reasoning,
            "blockers": self.blockers,
            "recommendations": self.recommendations
        }
