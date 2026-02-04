"""
Kurultai v0.1 Task Dependency Engine

A DAG-based task execution system that enables Kublai to batch, prioritize,
and execute multiple user requests as a unified dependency graph.

Components:
- IntentWindowBuffer: Message buffering (45-second window)
- DependencyAnalyzer: Semantic similarity-based dependency detection
- TopologicalExecutor: DAG execution engine
- PriorityCommandHandler: User priority override system

Author: Claude (Anthropic)
Date: 2026-02-04
"""

from .types import (
    TaskStatus,
    DependencyType,
    DeliverableType,
    Message,
    Task,
    Dependency,
    ExecutionSummary,
    STATUS_MAPPING,
    DELIVERABLE_TO_AGENT,
    DEFAULT_WINDOW_SECONDS,
    DEFAULT_MAX_MESSAGES,
    DEFAULT_PRIORITY_WEIGHT,
    DEFAULT_DELIVERABLE_TYPE,
    HIGH_SIMILARITY,
    MEDIUM_SIMILARITY,
    MAX_TASKS_PER_AGENT,
)

from .intent_buffer import IntentWindowBuffer
from .dependency_analyzer import DependencyAnalyzer, cosine_similarity
from .topological_executor import TopologicalExecutor
from .priority_override import PriorityCommandHandler, PriorityOverride

__all__ = [
    # Types
    "TaskStatus",
    "DependencyType",
    "DeliverableType",
    "Message",
    "Task",
    "Dependency",
    "ExecutionSummary",
    "STATUS_MAPPING",
    "DELIVERABLE_TO_AGENT",
    # Constants
    "DEFAULT_WINDOW_SECONDS",
    "DEFAULT_MAX_MESSAGES",
    "DEFAULT_PRIORITY_WEIGHT",
    "DEFAULT_DELIVERABLE_TYPE",
    "HIGH_SIMILARITY",
    "MEDIUM_SIMILARITY",
    "MAX_TASKS_PER_AGENT",
    # Main classes
    "IntentWindowBuffer",
    "DependencyAnalyzer",
    "TopologicalExecutor",
    "PriorityCommandHandler",
    "PriorityOverride",
    "cosine_similarity",
]

__version__ = "0.1.0"
