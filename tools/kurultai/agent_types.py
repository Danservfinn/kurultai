"""
Kurultai v0.1 Type Definitions

Shared types for Task Dependency Engine.

Author: Claude (Anthropic)
Date: 2026-02-04
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict


class TaskStatus(Enum):
    """Task status enumeration (matches base neo4j.md schema)."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    ESCALATED = "escalated"
    READY = "ready"  # Additional status for tasks with all dependencies met


class DependencyType(Enum):
    """Types of task dependencies."""
    BLOCKS = "blocks"          # A must complete before B starts
    FEEDS_INTO = "feeds_into"  # A's output informs B
    PARALLEL_OK = "parallel_ok" # No dependency, can run concurrently


class DeliverableType(Enum):
    """Types of task deliverables."""
    RESEARCH = "research"
    CODE = "code"
    ANALYSIS = "analysis"
    CONTENT = "content"
    STRATEGY = "strategy"
    OPS = "ops"
    TESTING = "testing"
    DOCS = "docs"


@dataclass
class Message:
    """Message in the intent window buffer."""
    content: str
    sender_hash: str
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "sender_hash": self.sender_hash,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "metadata": self.metadata or {},
        }


class Task(TypedDict):
    """Task structure matching Neo4j Task node."""
    id: str
    type: str
    description: str
    status: str
    assigned_to: Optional[str]
    claimed_by: Optional[str]
    delegated_by: Optional[str]
    priority: str
    deliverable_type: Optional[str]
    sender_hash: str
    created_at: datetime
    updated_at: Optional[datetime]
    embedding: Optional[List[float]]
    window_expires_at: Optional[datetime]
    user_priority_override: bool
    priority_weight: float
    claimed_at: Optional[datetime]
    completed_at: Optional[datetime]
    results: Optional[Any]
    error_message: Optional[str]


@dataclass
class Dependency:
    """Task dependency relationship."""
    from_task: str
    to_task: str
    type: DependencyType
    weight: float
    detected_by: str  # "semantic" | "explicit" | "inferred"
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "from_task": self.from_task,
            "to_task": self.to_task,
            "type": self.type.value if isinstance(self.type, DependencyType) else self.type,
            "weight": self.weight,
            "detected_by": self.detected_by,
            "confidence": self.confidence,
        }


@dataclass
class ExecutionSummary:
    """Summary of task execution."""
    executed_count: int
    error_count: int
    executed: List[str] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "executed_count": self.executed_count,
            "error_count": self.error_count,
            "executed": self.executed,
            "errors": self.errors,
        }


@dataclass
class AgentRouting:
    """Routing information for agent assignment."""
    agent_id: str
    agent_name: str
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "reason": self.reason,
        }


# Status mapping for Kurultai-specific statuses
STATUS_MAPPING = {
    "ready": "pending",
    "paused": "blocked",
    "aborted": "blocked",
}

# Deliverable type to agent routing mapping
DELIVERABLE_TO_AGENT = {
    DeliverableType.RESEARCH: ("researcher", "Möngke"),
    DeliverableType.ANALYSIS: ("analyst", "Jochi"),
    DeliverableType.CODE: ("developer", "Temüjin"),
    DeliverableType.CONTENT: ("writer", "Chagatai"),
    DeliverableType.STRATEGY: ("analyst", "Jochi"),
    DeliverableType.OPS: ("ops", "Ögedei"),
    DeliverableType.TESTING: ("developer", "Temüjin"),
    DeliverableType.DOCS: ("writer", "Chagatai"),
}

# Default values
DEFAULT_WINDOW_SECONDS = 45
DEFAULT_MAX_MESSAGES = 100
DEFAULT_PRIORITY_WEIGHT = 0.5
DEFAULT_DELIVERABLE_TYPE = DeliverableType.ANALYSIS

# Similarity thresholds for dependency detection
HIGH_SIMILARITY = 0.75
MEDIUM_SIMILARITY = 0.55

# Agent task limits (from neo4j.md)
MAX_TASKS_PER_AGENT = 2
