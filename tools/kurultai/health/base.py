"""
Base types and classes for health check modules.

Provides common data structures and base classes used across all health checkers.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class HealthStatus(Enum):
    """Health status enumeration."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class HealthResult:
    """Result of a health check.
    
    Attributes:
        component: Name of the component being checked
        status: Health status (healthy, warning, critical, unknown)
        message: Human-readable description
        details: Additional structured data
        error: Error message if check failed
        timestamp: When the check was performed
        response_time_ms: How long the check took
    """
    component: str
    status: HealthStatus
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    response_time_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'component': self.component,
            'status': self.status.value if isinstance(self.status, HealthStatus) else self.status,
            'message': self.message,
            'details': self.details,
            'error': self.error,
            'timestamp': self.timestamp.isoformat(),
            'response_time_ms': self.response_time_ms
        }
    
    def is_healthy(self) -> bool:
        """Check if status is healthy."""
        return self.status == HealthStatus.HEALTHY
    
    def is_critical(self) -> bool:
        """Check if status is critical."""
        return self.status == HealthStatus.CRITICAL


@dataclass
class HealthSummary:
    """Summary of multiple health checks."""
    healthy_count: int
    warning_count: int
    critical_count: int
    unknown_count: int
    total_count: int
    results: List[HealthResult]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def overall_status(self) -> HealthStatus:
        """Determine overall status based on individual results."""
        if self.critical_count > 0:
            return HealthStatus.CRITICAL
        elif self.warning_count > 0:
            return HealthStatus.WARNING
        elif self.healthy_count == self.total_count:
            return HealthStatus.HEALTHY
        return HealthStatus.UNKNOWN
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'overall_status': self.overall_status.value,
            'healthy_count': self.healthy_count,
            'warning_count': self.warning_count,
            'critical_count': self.critical_count,
            'unknown_count': self.unknown_count,
            'total_count': self.total_count,
            'results': [r.to_dict() for r in self.results],
            'timestamp': self.timestamp.isoformat()
        }


class BaseHealthChecker:
    """Base class for health checkers.
    
    All health checkers should inherit from this class and implement
    the check() method.
    """
    
    def __init__(self, name: str, timeout_seconds: float = 30.0):
        self.name = name
        self.timeout_seconds = timeout_seconds
    
    async def check(self) -> HealthResult:
        """Run the health check.
        
        Must be implemented by subclasses.
        
        Returns:
            HealthResult with the check outcome
        """
        raise NotImplementedError("Subclasses must implement check()")
    
    def check_sync(self) -> HealthResult:
        """Synchronous version of check().
        
        Default implementation runs the async version in a new event loop.
        Subclasses can override for truly synchronous checks.
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If already in an event loop, create a new one in a thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.check())
                    return future.result()
            else:
                return loop.run_until_complete(self.check())
        except RuntimeError:
            # No event loop running
            return asyncio.run(self.check())
