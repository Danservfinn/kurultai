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

# Import only the safe modules (those that don't import numpy/neo4j)
from .intent_buffer import IntentWindowBuffer
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

# Lazy imports for modules that import numpy (to avoid recursion issues during test collection)
_import_cache = {}


def __getattr__(name):
    """Lazy import modules that depend on numpy to avoid recursion issues."""
    if name in _import_cache:
        return _import_cache[name]

    if name == "DependencyAnalyzer":
        from .dependency_analyzer import DependencyAnalyzer as cls
        _import_cache[name] = cls
        return cls
    if name == "cosine_similarity":
        from .dependency_analyzer import cosine_similarity as fn
        _import_cache[name] = fn
        return fn

    raise AttributeError(f"module 'tools.kurultai' has no attribute '{name}'")
