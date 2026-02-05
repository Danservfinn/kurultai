"""
Multi-Goal DAG Orchestration Patterns for Kurultai's Task Dependency Engine.

This module explores concrete Python implementation patterns for multi-goal orchestration,
extending the existing Task Dependency Engine to support:

1. Goal vs Task Classes: Separate GoalNode and TaskNode with proper inheritance
2. Relationship Types: Modeling different edge types in a multi-goal DAG
3. Detection Algorithm: LLM-based and rule-based relationship detection
4. Graph Execution: NetworkX-based DAG execution with priority handling
5. State Management: Progress tracking across multiple goals

Author: Claude (Anthropic)
Date: 2026-02-04
"""

from __future__ import annotations

import abc
import asyncio
import json
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from functools import total_ordering
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Generic,
    Iterator,
    List,
    Optional,
    Protocol,
    Set,
    Tuple,
    TypeVar,
    Union,
)
from weakref import WeakValueDictionary

import networkx as nx
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)

T = TypeVar("T")
NodeID = str

# =============================================================================
# 1. GOAL VS TASK CLASSES - Hierarchical Design
# =============================================================================


class NodeStatus(Enum):
    """Status of a node in the dependency graph."""
    PENDING = auto()
    READY = auto()
    IN_PROGRESS = auto()
    BLOCKED = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()
    SKIPPED = auto()


class RelationshipType(Enum):
    """
    Types of relationships between goals in the DAG.

    INDEPENDENT: Goals can execute in parallel without coordination
    SYNERGISTIC: Goals should be merged into a unified execution strategy
    ENABLES: One goal creates prerequisites for another (sequential dependency)
    SUBGOAL_OF: One goal is a component of a larger goal (hierarchical)
    CONFLICTS_WITH: Goals that cannot both be pursued simultaneously
    REINFORCES: Goals that enhance each other when pursued together
    """
    INDEPENDENT = "parallel_ok"
    SYNERGISTIC = "merge_into"
    ENABLES = "blocks"  # A enables B means A must complete before B starts
    SUBGOAL_OF = "part_of"
    CONFLICTS_WITH = "mutex"
    REINFORCES = "amplifies"


class Priority(Enum):
    """Priority levels for execution ordering."""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


@total_ordering
class PriorityMixin:
    """Mixin class for adding priority comparison to nodes."""

    priority: Priority

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, PriorityMixin):
            return NotImplemented
        return self.priority.value < other.priority.value


@dataclass
class BaseNode(PriorityMixin):
    """
    Abstract base class for all nodes in the dependency graph.

    Uses the Template Method pattern - subclasses implement specific behavior
    while the base class provides common functionality.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    status: NodeStatus = NodeStatus.PENDING
    priority: Priority = Priority.NORMAL
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, BaseNode):
            return False
        return self.id == other.id

    def mark_status(self, status: NodeStatus) -> None:
        """Update status and timestamp."""
        self.status = status
        self.updated_at = datetime.now(timezone.utc)

    def is_terminal(self) -> bool:
        """Check if node is in a terminal state."""
        return self.status in {
            NodeStatus.COMPLETED,
            NodeStatus.FAILED,
            NodeStatus.CANCELLED,
            NodeStatus.SKIPPED,
        }

    def is_ready(self) -> bool:
        """Check if node is ready to execute."""
        return self.status in {NodeStatus.READY, NodeStatus.IN_PROGRESS}

    @abc.abstractmethod
    def progress_fraction(self) -> float:
        """Return progress as a fraction 0.0 to 1.0."""
        ...


@dataclass
class TaskNode(BaseNode):
    """
    Atomic executable unit in the DAG.

    A TaskNode represents a single concrete action that can be executed.
    Tasks are the leaves of the goal decomposition tree.
    """
    task_type: str = "generic"
    assigned_to: Optional[str] = None  # Agent ID
    result: Optional[Any] = None
    error_message: Optional[str] = None
    estimated_duration_seconds: Optional[int] = None
    actual_duration_seconds: Optional[int] = None

    def progress_fraction(self) -> float:
        """Tasks are either complete (1.0) or not (0.0)."""
        return 1.0 if self.status == NodeStatus.COMPLETED else 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "type": "task",
            "title": self.title,
            "description": self.description,
            "status": self.status.name,
            "priority": self.priority.name,
            "task_type": self.task_type,
            "assigned_to": self.assigned_to,
            "result": str(self.result) if self.result else None,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class GoalNode(BaseNode):
    """
    High-level objective composed of sub-goals or tasks.

    Goals differ from tasks in that they:
    1. Can be decomposed into smaller goals/tasks
    2. Have progress that aggregates from children
    3. May have synergistic relationships with other goals
    4. Can be abstract until decomposed
    """
    success_criteria: List[str] = field(default_factory=list)
    contributing_tasks: List[str] = field(default_factory=list)  # Task IDs
    contributing_subgoals: List[str] = field(default_factory=list)  # Goal IDs
    target_progress: float = 1.0  # May be >1.0 for stretch goals

    # Goal-specific state
    decomposition_complete: bool = False
    current_strategy: Optional[str] = None  # For synergistic goals

    def progress_fraction(self) -> float:
        """
        Calculate progress based on contributing tasks and subgoals.

        This is a weighted average where:
        - Direct tasks contribute fully
        - Subgoals contribute their current progress
        """
        if not self.contributing_tasks and not self.contributing_subgoals:
            # No decomposition yet, progress is status-based
            if self.status == NodeStatus.COMPLETED:
                return 1.0
            return 0.0

        total = 0.0
        count = 0

        for task_id in self.contributing_tasks:
            # Tasks would be looked up from the graph
            # For now, assume they contribute when completed
            total += 1.0  # Placeholder
            count += 1

        for subgoal_id in self.contributing_subgoals:
            # Subgoals contribute their progress fraction
            total += 0.5  # Placeholder
            count += 1

        return min(total / max(count, 1), self.target_progress)

    def add_contributing_task(self, task_id: str) -> None:
        """Add a task that contributes to this goal."""
        if task_id not in self.contributing_tasks:
            self.contributing_tasks.append(task_id)
            self.updated_at = datetime.now(timezone.utc)

    def add_subgoal(self, goal_id: str) -> None:
        """Add a subgoal that contributes to this goal."""
        if goal_id not in self.contributing_subgoals:
            self.contributing_subgoals.append(goal_id)
            self.updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "type": "goal",
            "title": self.title,
            "description": self.description,
            "status": self.status.name,
            "priority": self.priority.name,
            "success_criteria": self.success_criteria,
            "contributing_tasks": self.contributing_tasks,
            "contributing_subgoals": self.contributing_subgoals,
            "progress": self.progress_fraction(),
            "decomposition_complete": self.decomposition_complete,
            "current_strategy": self.current_strategy,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }

    def is_leaf(self) -> bool:
        """Check if this is a leaf goal (no subgoals)."""
        return len(self.contributing_subgoals) == 0


class NodeFactory:
    """
    Factory for creating nodes with proper validation.

    Uses the Factory pattern to ensure nodes are created with valid state.
    """

    _task_cache: ClassVar[WeakValueDictionary] = WeakValueDictionary()

    @classmethod
    def create_task(
        cls,
        title: str,
        description: str = "",
        task_type: str = "generic",
        priority: Priority = Priority.NORMAL,
        **kwargs
    ) -> TaskNode:
        """Create a new task node."""
        task = TaskNode(
            title=title,
            description=description,
            task_type=task_type,
            priority=priority,
            **kwargs
        )
        cls._task_cache[task.id] = task
        logger.debug(f"Created task {task.id}: {title}")
        return task

    @classmethod
    def create_goal(
        cls,
        title: str,
        description: str = "",
        success_criteria: List[str] | None = None,
        priority: Priority = Priority.NORMAL,
        **kwargs
    ) -> GoalNode:
        """Create a new goal node."""
        goal = GoalNode(
            title=title,
            description=description,
            success_criteria=success_criteria or [],
            priority=priority,
            **kwargs
        )
        logger.debug(f"Created goal {goal.id}: {title}")
        return goal


# =============================================================================
# 2. EDGE AND RELATIONSHIP MODELING
# =============================================================================


@dataclass(frozen=True)
class DependencyEdge:
    """
    Represents a relationship between two nodes in the DAG.

    Immutable edge with typed relationship for semantic meaning.
    """
    source_id: str
    target_id: str
    relationship: RelationshipType
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        """Validate edge."""
        if self.source_id == self.target_id:
            raise ValueError("Cannot create self-loop edge")

    def reversed(self) -> DependencyEdge:
        """Return edge with reversed direction."""
        return DependencyEdge(
            source_id=self.target_id,
            target_id=self.source_id,
            relationship=self._reverse_relationship(),
            weight=self.weight,
            metadata=self.metadata.copy(),
        )

    def _reverse_relationship(self) -> RelationshipType:
        """Get the inverse relationship type."""
        reverses = {
            RelationshipType.ENABLES: RelationshipType.ENABLES,  # Transitive
            RelationshipType.SUBGOAL_OF: RelationshipType.SUBGOAL_OF,
            RelationshipType.SYNERGISTIC: RelationshipType.SYNERGISTIC,  # Symmetric
            RelationshipType.CONFLICTS_WITH: RelationshipType.CONFLICTS_WITH,  # Symmetric
            RelationshipType.REINFORCES: RelationshipType.REINFORCES,  # Symmetric
            RelationshipType.INDEPENDENT: RelationshipType.INDEPENDENT,
        }
        return reverses.get(self.relationship, RelationshipType.INDEPENDENT)


class EdgeBuilder:
    """
    Builder for constructing typed edges with validation.

    Uses the Builder pattern for fluent edge construction.
    """

    def __init__(self, source_id: str, target_id: str):
        self.source_id = source_id
        self.target_id = target_id
        self._relationship = RelationshipType.INDEPENDENT
        self._weight = 1.0
        self._metadata = {}

    def enables(self) -> EdgeBuilder:
        """Mark as enabling relationship."""
        self._relationship = RelationshipType.ENABLES
        return self

    def subgoal_of(self) -> EdgeBuilder:
        """Mark as subgoal relationship."""
        self._relationship = RelationshipType.SUBGOAL_OF
        return self

    def synergistic(self, strategy: str = "") -> EdgeBuilder:
        """Mark as synergistic relationship."""
        self._relationship = RelationshipType.SYNERGISTIC
        if strategy:
            self._metadata["strategy"] = strategy
        return self

    def conflicts(self) -> EdgeBuilder:
        """Mark as conflicting relationship."""
        self._relationship = RelationshipType.CONFLICTS_WITH
        return self

    def reinforces(self, boost_factor: float = 1.5) -> EdgeBuilder:
        """Mark as reinforcing relationship."""
        self._relationship = RelationshipType.REINFORCES
        self._weight = boost_factor
        return self

    def independent(self) -> EdgeBuilder:
        """Mark as independent relationship."""
        self._relationship = RelationshipType.INDEPENDENT
        return self

    def with_weight(self, weight: float) -> EdgeBuilder:
        """Set edge weight."""
        self._weight = weight
        return self

    def with_metadata(self, **metadata) -> EdgeBuilder:
        """Add metadata."""
        self._metadata.update(metadata)
        return self

    def build(self) -> DependencyEdge:
        """Construct the edge."""
        return DependencyEdge(
            source_id=self.source_id,
            target_id=self.target_id,
            relationship=self._relationship,
            weight=self._weight,
            metadata=self._metadata.copy(),
        )


def edge(source_id: str, target_id: str) -> EdgeBuilder:
    """Start building an edge."""
    return EdgeBuilder(source_id, target_id)


# =============================================================================
# 3. RELATIONSHIP DETECTION ALGORITHM
# =============================================================================


class SimilarityMetric(Protocol):
    """Protocol for similarity metrics."""

    def __call__(self, text1: str, text2: str) -> float:
        """Return similarity score between 0.0 and 1.0."""
        ...


class JaccardSimilarity:
    """Jaccard similarity for word sets."""

    def __init__(self, preprocess: Callable[[str], Set[str]] | None = None):
        self.preprocess = preprocess or self._default_preprocess

    @staticmethod
    def _default_preprocess(text: str) -> Set[str]:
        """Default text preprocessing."""
        words = text.lower().split()
        return {w.strip(".,!?;:") for w in words if len(w) > 2}

    def __call__(self, text1: str, text2: str) -> float:
        """Calculate Jaccard similarity."""
        set1 = self.preprocess(text1)
        set2 = self.preprocess(text2)

        if not set1 and not set2:
            return 1.0
        if not set1 or not set2:
            return 0.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0


class EmbeddingSimilarity:
    """Embedding-based similarity using vector representations."""

    def __init__(self, model: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(model)
            self._dimension = 384  # For all-MiniLM-L6-v2
        except ImportError:
            logger.warning("sentence_transformers not available, using Jaccard fallback")
            self.model = None
            self._fallback = JaccardSimilarity()

    def __call__(self, text1: str, text2: str) -> float:
        """Calculate cosine similarity."""
        if self.model is None:
            return self._fallback(text1, text2)

        emb1 = self.model.encode(text1)
        emb2 = self.model.encode(text2)

        # Cosine similarity
        import numpy as np
        dot = np.dot(emb1, emb2)
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        return dot / (norm1 * norm2) if norm1 and norm2 else 0.0


@dataclass
class RelationshipDetection:
    """
    Detect relationships between goals using multiple strategies.

    Combines:
    1. Semantic similarity (threshold-based)
    2. Keyword extraction and matching
    3. LLM-based classification (optional)
    4. Rule-based heuristics
    """

    similarity_threshold: float = 0.3
    synergy_threshold: float = 0.6
    conflict_keywords: Set[str] = field(default_factory=lambda: {
        "vs", "versus", "against", "opposite", "instead",
        "rather than", "alternative", "competing",
    })
    enable_keywords: Set[str] = field(default_factory=lambda: {
        "requires", "needs", "depends on", "after", "before",
        "prerequisite", "enables", "leads to",
    })
    reinforce_keywords: Set[str] = field(default_factory=lambda: {
        "supports", "enhances", "amplifies", "strengthens",
        "complements", "improves",
    })
    similarity_metric: SimilarityMetric = field(default_factory=JaccardSimilarity)

    def detect(
        self,
        goal1: GoalNode,
        goal2: GoalNode,
        context: Dict[str, Any] | None = None
    ) -> RelationshipType:
        """
        Detect the relationship type between two goals.

        Returns the most likely relationship type.
        """
        # Combine title and description for analysis
        text1 = f"{goal1.title} {goal1.description}"
        text2 = f"{goal2.title} {goal2.description}"

        # Calculate similarity
        similarity = self.similarity_metric(text1, text2)

        # Check for conflict indicators
        if self._has_conflict(text1, text2):
            return RelationshipType.CONFLICTS_WITH

        # Check for enabling relationship
        if self._has_enabling(text1, text2):
            return RelationshipType.ENABLES

        # Check for reinforcing relationship
        if self._has_reinforcing(text1, text2):
            return RelationshipType.REINFORCES

        # Check for synergy (high semantic similarity)
        if similarity >= self.synergy_threshold:
            return RelationshipType.SYNERGISTIC

        # Check for hierarchical relationship
        if self._is_subgoal(goal1, goal2):
            return RelationshipType.SUBGOAL_OF

        # Default to independent
        return RelationshipType.INDEPENDENT

    def _has_conflict(self, text1: str, text2: str) -> bool:
        """Check for conflict indicators."""
        combined = text1.lower() + " " + text2.lower()
        return any(kw in combined for kw in self.conflict_keywords)

    def _has_enabling(self, text1: str, text2: str) -> bool:
        """Check for enabling/prerequisite indicators."""
        combined = text1.lower() + " " + text2.lower()
        return any(kw in combined for kw in self.enable_keywords)

    def _has_reinforcing(self, text1: str, text2: str) -> bool:
        """Check for reinforcing indicators."""
        combined = text1.lower() + " " + text2.lower()
        return any(kw in combined for kw in self.reinforce_keywords)

    def _is_subgoal(self, goal1: GoalNode, goal2: GoalNode) -> bool:
        """Check if one goal is a subgoal of the other."""
        # Simple heuristic: if one title is contained in the other
        title1_lower = goal1.title.lower()
        title2_lower = goal2.title.lower()

        return (title1_lower in title2_lower or title2_lower in title1_lower)


class LLMRelationshipDetector:
    """
    LLM-based relationship detection using Claude/OpenAI.

    This is more accurate but slower and requires API access.
    """

    def __init__(self, api_key: str, model: str = "claude-3-haiku-20240307"):
        self.api_key = api_key
        self.model = model

    async def detect(
        self,
        goal1: GoalNode,
        goal2: GoalNode,
        context: Dict[str, Any] | None = None
    ) -> tuple[RelationshipType, float]:
        """
        Use LLM to classify relationship and return confidence score.

        Returns:
            Tuple of (relationship_type, confidence_score)
        """
        prompt = self._build_prompt(goal1, goal2, context)

        # This would make an actual API call
        # For now, return a placeholder
        logger.debug(f"LLM detection for {goal1.id} <-> {goal2.id}")

        return RelationshipType.INDEPENDENT, 0.5

    def _build_prompt(
        self,
        goal1: GoalNode,
        goal2: GoalNode,
        context: Dict[str, Any] | None
    ) -> str:
        """Build the LLM prompt."""
        return f"""
Classify the relationship between these two goals:

Goal 1:
Title: {goal1.title}
Description: {goal1.description}
Success Criteria: {goal1.success_criteria}

Goal 2:
Title: {goal2.title}
Description: {goal2.description}
Success Criteria: {goal2.success_criteria}

Possible relationships:
- INDEPENDENT: Can be pursued in parallel
- SYNERGISTIC: Should be merged into unified strategy
- ENABLES: One must complete before the other starts
- SUBGOAL_OF: One is a component of the other
- CONFLICTS_WITH: Cannot both be pursued
- REINFORCES: Enhances each other when pursued together

Respond with: RELATIONSHIP_TYPE (confidence 0-100)
"""


class HybridRelationshipDetector:
    """
    Hybrid detector combining rule-based and LLM-based detection.

    Uses fast rule-based detection first, falls back to LLM for
    ambiguous cases.
    """

    def __init__(
        self,
        rule_detector: RelationshipDetection | None = None,
        llm_detector: LLMRelationshipDetector | None = None,
        ambiguity_threshold: float = 0.5
    ):
        self.rule_detector = rule_detector or RelationshipDetection()
        self.llm_detector = llm_detector
        self.ambiguity_threshold = ambiguity_threshold

    async def detect(
        self,
        goal1: GoalNode,
        goal2: GoalNode,
        context: Dict[str, Any] | None = None
    ) -> RelationshipType:
        """Detect relationship using hybrid approach."""
        # First try rule-based detection
        rule_result = self.rule_detector.detect(goal1, goal2, context)

        # If we have high confidence (or no LLM), use rule result
        if self.llm_detector is None:
            return rule_result

        # Use LLM for ambiguous cases
        llm_result, confidence = await self.llm_detector.detect(
            goal1, goal2, context
        )

        if confidence < self.ambiguity_threshold:
            return rule_result

        return llm_result


# =============================================================================
# 4. GRAPH EXECUTION WITH NETWORKX
# =============================================================================


class MultiGoalDAG:
    """
    Multi-goal DAG using NetworkX for graph operations.

    Supports:
    - Typed edges with different relationship types
    - Topological sorting with priority handling
    - Parallel execution detection
    - Cycle detection and validation
    """

    def __init__(self, name: str = "multi_goal_dag"):
        self.name = name
        # Use MultiDiGraph to allow multiple edges between same nodes
        self.graph = nx.MultiDiGraph(name=name)
        self._nodes: Dict[str, BaseNode] = {}

    def add_node(self, node: BaseNode) -> None:
        """Add a node to the DAG."""
        self._nodes[node.id] = node
        self.graph.add_node(
            node.id,
            node_type="goal" if isinstance(node, GoalNode) else "task",
            title=node.title,
            priority=node.priority.value,
            status=node.status.name,
        )

    def add_edge(self, edge: DependencyEdge) -> None:
        """Add a typed edge to the DAG."""
        if edge.source_id not in self._nodes:
            raise ValueError(f"Source node {edge.source_id} not found")
        if edge.target_id not in self._nodes:
            raise ValueError(f"Target node {edge.target_id} not found")

        self.graph.add_edge(
            edge.source_id,
            edge.target_id,
            relationship=edge.relationship.value,
            weight=edge.weight,
            **edge.metadata
        )

    def get_node(self, node_id: str) -> BaseNode | None:
        """Get a node by ID."""
        return self._nodes.get(node_id)

    def get_nodes_by_type(self, node_type: type) -> List[BaseNode]:
        """Get all nodes of a specific type."""
        return [n for n in self._nodes.values() if isinstance(n, node_type)]

    def detect_cycles(self) -> List[List[str]]:
        """Detect cycles in the graph."""
        try:
            cycles = list(nx.simple_cycles(self.graph))
            return cycles
        except nx.NetworkXError:
            return []

    def validate(self) -> tuple[bool, List[str]]:
        """
        Validate the DAG structure.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Check for cycles in enabling relationships
        enabling_subgraph = self._relationship_subgraph(RelationshipType.ENABLES)
        try:
            nx.find_cycle(enabling_subgraph)
            errors.append("Cycle detected in enabling relationships")
        except nx.NetworkXNoCycle:
            pass  # No cycle is good

        # Check for subgoal cycles
        subgoal_subgraph = self._relationship_subgraph(RelationshipType.SUBGOAL_OF)
        try:
            nx.find_cycle(subgoal_subgraph)
            errors.append("Cycle detected in subgoal hierarchy")
        except nx.NetworkXNoCycle:
            pass

        return len(errors) == 0, errors

    def _relationship_subgraph(
        self,
        relationship: RelationshipType
    ) -> nx.DiGraph:
        """Extract subgraph for a specific relationship type."""
        edges = [
            (u, v)
            for u, v, data in self.graph.edges(data=True)
            if data.get("relationship") == relationship.value
        ]
        return nx.DiGraph(edges)

    def execution_order(self) -> List[str]:
        """
        Get execution order considering dependencies and priorities.

        Returns a list of node IDs in execution order.
        """
        # Get enabling dependencies only
        enabling_edges = [
            (u, v)
            for u, v, data in self.graph.edges(data=True)
            if data.get("relationship") == RelationshipType.ENABLES.value
        ]

        dep_graph = nx.DiGraph()
        dep_graph.add_nodes_from(self._nodes.keys())
        dep_graph.add_edges_from(enabling_edges)

        try:
            # Topological sort gives us dependency order
            order = list(nx.topological_sort(dep_graph))

            # Sort each level by priority
            sorted_order = self._sort_by_priority_levels(order, dep_graph)

            return sorted_order

        except nx.NetworkXUnfeasible:
            logger.error("Cannot compute execution order: cycle detected")
            return list(self._nodes.keys())

    def _sort_by_priority_levels(
        self,
        topo_order: List[str],
        dep_graph: nx.DiGraph
    ) -> List[str]:
        """Sort nodes by priority within each dependency level."""
        # Group by level (nodes with same dependency depth)
        levels = self._group_by_level(topo_order, dep_graph)

        # Sort each level by priority
        result = []
        for level in sorted(levels.keys()):
            level_nodes = levels[level]
            level_nodes.sort(key=lambda nid: self._nodes[nid].priority.value)
            result.extend(level_nodes)

        return result

    def _group_by_level(
        self,
        nodes: List[str],
        dep_graph: nx.DiGraph
    ) -> Dict[int, List[str]]:
        """Group nodes by their dependency level."""
        levels: Dict[int, List[str]] = defaultdict(list)

        for node in nodes:
            level = self._dependency_level(node, dep_graph)
            levels[level].append(node)

        return levels

    def _dependency_level(self, node: str, dep_graph: nx.DiGraph) -> int:
        """Calculate the dependency level of a node."""
        level = 0
        visited = set()

        def traverse(n: str, depth: int) -> None:
            nonlocal level
            if n in visited:
                return
            visited.add(n)
            level = max(level, depth)
            for pred in dep_graph.predecessors(n):
                traverse(pred, depth + 1)

        traverse(node, 0)
        return level

    def get_ready_nodes(self) -> List[str]:
        """
        Get nodes that are ready to execute (no pending dependencies).
        """
        ready = []

        for node_id, node in self._nodes.items():
            if node.status != NodeStatus.PENDING:
                continue

            # Check enabling dependencies
            blockers = self._get_blocking_dependencies(node_id)
            if not blockers:
                ready.append(node_id)

        # Sort by priority
        ready.sort(key=lambda nid: self._nodes[nid].priority.value)
        return ready

    def _get_blocking_dependencies(self, node_id: str) -> List[str]:
        """Get IDs of dependencies that block this node."""
        blockers = []

        for pred in self.graph.predecessors(node_id):
            edge_data = self.graph.get_edge_data(pred, node_id)
            for edge in edge_data.values():
                if edge.get("relationship") == RelationshipType.ENABLES.value:
                    pred_node = self._nodes[pred]
                    if not pred_node.is_terminal():
                        blockers.append(pred)

        return blockers

    def get_parallelizable_nodes(self, node_id: str) -> List[str]:
        """
        Get nodes that can execute in parallel with the given node.

        These are nodes with:
        - No enabling relationship between them
        - No conflicts
        - Independent relationship type
        """
        parallelizable = []

        for other_id, other_node in self._nodes.items():
            if other_id == node_id:
                continue

            # Check if there's a blocking relationship
            if self._has_blocking_relationship(node_id, other_id):
                continue

            # Check if there's a conflict
            if self._has_conflict(node_id, other_id):
                continue

            parallelizable.append(other_id)

        return parallelizable

    def _has_blocking_relationship(self, node1: str, node2: str) -> bool:
        """Check if there's a blocking/enabling relationship between nodes."""
        # Check node1 -> node2
        edges = self.graph.get_edge_data(node1, node2)
        if edges:
            for edge in edges.values():
                if edge.get("relationship") in {
                    RelationshipType.ENABLES.value,
                    RelationshipType.SUBGOAL_OF.value,
                }:
                    return True

        # Check node2 -> node1
        edges = self.graph.get_edge_data(node2, node1)
        if edges:
            for edge in edges.values():
                if edge.get("relationship") in {
                    RelationshipType.ENABLES.value,
                    RelationshipType.SUBGOAL_OF.value,
                }:
                    return True

        return False

    def _has_conflict(self, node1: str, node2: str) -> bool:
        """Check if nodes have a conflicting relationship."""
        edges = self.graph.get_edge_data(node1, node2)
        if edges:
            for edge in edges.values():
                if edge.get("relationship") == RelationshipType.CONFLICTS_WITH.value:
                    return True
        return False

    def visualize(self, output_path: str | None = None) -> str:
        """
        Generate a visualization of the DAG.

        Returns the DOT format representation.
        """
        import io

        dot = io.StringIO()
        dot.write(f"digraph {self.name} {{\n")
        dot.write("  rankdir=TB;\n")
        dot.write("  node [shape=box];\n\n")

        # Write nodes with styling based on status
        for node_id, node in self._nodes.items():
            label = f"{node.title}\\n[{node.status.name}]"
            color = self._status_color(node.status)
            dot.write(f'  "{node_id}" [label="{label}", style=filled, fillcolor={color}];\n')

        dot.write("\n")

        # Write edges with styling based on relationship
        written_edges = set()
        for u, v, data in self.graph.edges(data=True):
            edge_key = (u, v)
            if edge_key in written_edges:
                continue
            written_edges.add(edge_key)

            relationship = data.get("relationship", "independent")
            style = self._relationship_style(relationship)
            dot.write(f'  "{u}" -> "{v}" [{style}];\n')

        dot.write("}\n")

        result = dot.getvalue()

        if output_path:
            with open(output_path, "w") as f:
                f.write(result)

        return result

    def _status_color(self, status: NodeStatus) -> str:
        """Get color for node status."""
        colors = {
            NodeStatus.PENDING: "lightgray",
            NodeStatus.READY: "lightblue",
            NodeStatus.IN_PROGRESS: "yellow",
            NodeStatus.BLOCKED: "orange",
            NodeStatus.COMPLETED: "lightgreen",
            NodeStatus.FAILED: "lightcoral",
            NodeStatus.CANCELLED: "pink",
            NodeStatus.SKIPPED: "lightgray",
        }
        return colors.get(status, "white")

    def _relationship_style(self, relationship: str) -> str:
        """Get DOT style for relationship type."""
        styles = {
            RelationshipType.ENABLES.value: "style=solid, color=black",
            RelationshipType.SUBGOAL_OF.value: "style=dashed, color=blue",
            RelationshipType.SYNERGISTIC.value: "style=bold, color=green",
            RelationshipType.CONFLICTS_WITH.value: "style=dotted, color=red",
            RelationshipType.REINFORCES.value: "style=tapered, color=purple",
            RelationshipType.INDEPENDENT.value: "style=solid, color=gray",
        }
        return styles.get(relationship, "style=solid")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the DAG to a dictionary."""
        return {
            "name": self.name,
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [
                {
                    "source": u,
                    "target": v,
                    "relationship": data.get("relationship"),
                    "weight": data.get("weight", 1.0),
                }
                for u, v, data in self.graph.edges(data=True)
            ],
            "execution_order": self.execution_order(),
        }


# =============================================================================
# 5. STATE MANAGEMENT AND EXECUTION ENGINE
# =============================================================================


class ExecutionStrategy(Protocol):
    """Protocol for execution strategies."""

    async def execute(
        self,
        dag: MultiGoalDAG,
        max_parallel: int = 4
    ) -> Dict[str, Any]:
        """Execute the DAG and return results."""
        ...


class TopologicalExecutor:
    """
    Execute DAG in topological order with parallel execution where possible.

    Strategy:
    1. Process nodes in topological order
    2. At each level, execute ready nodes in parallel
    3. Wait for all nodes at level to complete before proceeding
    4. Track progress and handle failures
    """

    def __init__(
        self,
        executor: Callable[[TaskNode], Any] | None = None,
        max_retries: int = 3
    ):
        self.executor = executor or self._default_executor
        self.max_retries = max_retries

    async def execute(
        self,
        dag: MultiGoalDAG,
        max_parallel: int = 4
    ) -> Dict[str, Any]:
        """
        Execute the DAG.

        Returns execution summary with timing and results.
        """
        start_time = datetime.now(timezone.utc)
        results = {}
        errors = {}

        # Validate first
        is_valid, validation_errors = dag.validate()
        if not is_valid:
            raise ValueError(f"Invalid DAG: {validation_errors}")

        # Process in execution order
        execution_order = dag.execution_order()

        # Group by dependency level for parallel execution
        levels = self._group_by_level(dag, execution_order)

        for level, node_ids in levels.items():
            logger.info(f"Processing level {level} with {len(node_ids)} nodes")

            # Execute nodes at this level in parallel
            level_results = await self._execute_level(
                dag, node_ids, max_parallel
            )

            results.update(level_results["completed"])
            errors.update(level_results["failed"])

            # Check if we should abort
            if level_results["should_abort"]:
                logger.warning(f"Aborting at level {level} due to failures")
                break

        end_time = datetime.now(timezone.utc)

        return {
            "status": "completed" if not errors else "partial",
            "duration_seconds": (end_time - start_time).total_seconds(),
            "nodes_completed": len(results),
            "nodes_failed": len(errors),
            "results": results,
            "errors": errors,
        }

    def _group_by_level(
        self,
        dag: MultiGoalDAG,
        execution_order: List[str]
    ) -> Dict[int, List[str]]:
        """Group nodes by their dependency level."""
        levels: Dict[int, List[str]] = defaultdict(list)
        level_map: Dict[str, int] = {}

        for node_id in execution_order:
            # Calculate level based on dependencies
            level = 0
            for pred in dag.graph.predecessors(node_id):
                edge_data = dag.graph.get_edge_data(pred, node_id)
                for edge in edge_data.values():
                    if edge.get("relationship") == RelationshipType.ENABLES.value:
                        pred_level = level_map.get(pred, 0)
                        level = max(level, pred_level + 1)

            level_map[node_id] = level
            levels[level].append(node_id)

        return dict(levels)

    async def _execute_level(
        self,
        dag: MultiGoalDAG,
        node_ids: List[str],
        max_parallel: int
    ) -> Dict[str, Any]:
        """Execute all nodes at a given level in parallel."""
        results = {}
        errors = {}
        semaphore = asyncio.Semaphore(max_parallel)

        async def execute_one(node_id: str) -> tuple[str, Any | None]:
            async with semaphore:
                node = dag.get_node(node_id)
                if node is None:
                    return node_id, None

                if isinstance(node, GoalNode):
                    # Goals are tracked but not directly executed
                    return node_id, {"type": "goal", "progress": node.progress_fraction()}

                if isinstance(node, TaskNode):
                    return await self._execute_task(dag, node)

                return node_id, None

        # Execute all tasks in this level
        tasks = [execute_one(nid) for nid in node_ids]
        task_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in task_results:
            if isinstance(result, Exception):
                logger.error(f"Task execution error: {result}")
                continue

            node_id, value = result
            if value is not None:
                # Check if this is an error result
                if isinstance(value, dict) and "error" in value:
                    errors[node_id] = value
                else:
                    results[node_id] = value

        # Check for blocking failures
        should_abort = any(
            dag.get_node(nid).status == NodeStatus.FAILED
            for nid in node_ids
            if dag.get_node(nid) is not None
        )

        return {
            "completed": results,
            "failed": errors,
            "should_abort": should_abort,
        }

    async def _execute_task(
        self,
        dag: MultiGoalDAG,
        task: TaskNode
    ) -> tuple[str, Dict[str, Any]]:
        """Execute a single task."""
        task.mark_status(NodeStatus.IN_PROGRESS)

        try:
            result = await self._safe_execute(task)

            task.mark_status(NodeStatus.COMPLETED)
            task.result = result

            return task.id, {
                "type": "task",
                "title": task.title,
                "result": result,
            }

        except Exception as e:
            task.mark_status(NodeStatus.FAILED)
            task.error_message = str(e)

            logger.error(f"Task {task.id} failed: {e}")
            return task.id, {
                "type": "task",
                "title": task.title,
                "error": str(e),
            }

    async def _safe_execute(self, task: TaskNode) -> Any:
        """Execute task with error handling and retries."""
        last_error = None

        for attempt in range(self.max_retries):
            try:
                # Check if executor is async or sync
                if asyncio.iscoroutinefunction(self.executor):
                    return await self.executor(task)
                else:
                    return await asyncio.to_thread(self.executor, task)

            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    raise

        raise last_error if last_error else RuntimeError("Execution failed")

    @staticmethod
    def _default_executor(task: TaskNode) -> Any:
        """Default executor that just returns the task info."""
        return {
            "task_id": task.id,
            "title": task.title,
            "type": task.task_type,
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }


class SynergyExecutor:
    """
    Executor for synergistic goals that should be merged.

    When goals are marked as SYNERGISTIC, this executor:
    1. Groups synergistic goals
    2. Creates a unified execution plan
    3. Executes the plan as a single coordinated effort
    """

    def __init__(self, base_executor: TopologicalExecutor | None = None):
        self.base_executor = base_executor or TopologicalExecutor()

    async def execute(
        self,
        dag: MultiGoalDAG,
        max_parallel: int = 4
    ) -> Dict[str, Any]:
        """Execute DAG with synergy handling."""
        # Find synergistic groups
        synergy_groups = self._find_synergy_groups(dag)

        if not synergy_groups:
            # No synergies, use standard execution
            return await self.base_executor.execute(dag, max_parallel)

        # Create unified strategies for each group
        for group in synergy_groups:
            await self._create_unified_strategy(dag, group)

        # Execute with merged strategies
        return await self.base_executor.execute(dag, max_parallel)

    def _find_synergy_groups(self, dag: MultiGoalDAG) -> List[List[str]]:
        """Find groups of synergistically connected goals."""
        groups = []
        visited = set()

        for node_id in dag._nodes:
            if node_id in visited:
                continue

            group = self._find_connected_component(dag, node_id, visited)
            if len(group) > 1:
                groups.append(group)

        return groups

    def _find_connected_component(
        self,
        dag: MultiGoalDAG,
        start: str,
        visited: Set[str]
    ) -> List[str]:
        """Find all nodes connected via synergistic edges."""
        component = []
        to_visit = [start]

        while to_visit:
            node_id = to_visit.pop()
            if node_id in visited:
                continue

            visited.add(node_id)
            component.append(node_id)

            # Find synergistic neighbors
            for neighbor in dag.graph.neighbors(node_id):
                edge_data = dag.graph.get_edge_data(node_id, neighbor)
                for edge in edge_data.values():
                    if edge.get("relationship") == RelationshipType.SYNERGISTIC.value:
                        to_visit.append(neighbor)

        return component

    async def _create_unified_strategy(
        self,
        dag: MultiGoalDAG,
        group: List[str]
    ) -> None:
        """Create a unified execution strategy for synergistic goals."""
        # This would use LLM to create a unified plan
        strategy_id = str(uuid.uuid4())

        for node_id in group:
            node = dag.get_node(node_id)
            if isinstance(node, GoalNode):
                node.current_strategy = strategy_id


# =============================================================================
# 6. PYDANTIC MODELS FOR SERIALIZATION
# =============================================================================


class GoalNodeModel(BaseModel):
    """Pydantic model for GoalNode serialization."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str = Field(default="goal")
    title: str
    description: str = ""
    status: str = "PENDING"
    priority: str = "NORMAL"
    success_criteria: List[str] = Field(default_factory=list)
    contributing_tasks: List[str] = Field(default_factory=list)
    contributing_subgoals: List[str] = Field(default_factory=list)
    target_progress: float = 1.0
    decomposition_complete: bool = False
    current_strategy: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @validator("status")
    def validate_status(cls, v):
        valid = {s.name for s in NodeStatus}
        if v not in valid:
            raise ValueError(f"Invalid status: {v}")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Earn $1000 from side projects",
                "description": "Generate recurring revenue through software products",
                "success_criteria": [
                    "Launch 2 products",
                    "Acquire 10 paying customers",
                    "Reach $1000 MRR"
                ],
                "priority": "HIGH"
            }
        }


class TaskNodeModel(BaseModel):
    """Pydantic model for TaskNode serialization."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str = Field(default="task")
    title: str
    description: str = ""
    status: str = "PENDING"
    priority: str = "NORMAL"
    task_type: str = "generic"
    assigned_to: str | None = None
    estimated_duration_seconds: int | None = None
    actual_duration_seconds: int | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Set up Stripe integration",
                "description": "Add payment processing to the product",
                "task_type": "code",
                "estimated_duration_seconds": 3600
            }
        }


class EdgeModel(BaseModel):
    """Pydantic model for DependencyEdge serialization."""

    source_id: str
    target_id: str
    relationship: str
    weight: float = 1.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DAGStateModel(BaseModel):
    """Complete DAG state for persistence."""

    name: str
    nodes: List[Union[GoalNodeModel, TaskNodeModel]]
    edges: List[EdgeModel]
    execution_order: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dag(self) -> MultiGoalDAG:
        """Convert model back to MultiGoalDAG instance."""
        dag = MultiGoalDAG(name=self.name)

        for node_data in self.nodes:
            if node_data.type == "goal":
                node = GoalNode(**node_data.model_dump())
            else:
                node = TaskNode(**node_data.model_dump())
            dag.add_node(node)

        for edge_data in self.edges:
            edge = DependencyEdge(
                source_id=edge_data.source_id,
                target_id=edge_data.target_id,
                relationship=RelationshipType(edge_data.relationship),
                weight=edge_data.weight,
                metadata=edge_data.metadata,
            )
            dag.add_edge(edge)

        return dag


# =============================================================================
# 7. HIGH-LEVEL API
# =============================================================================


class GoalOrchestrator:
    """
    High-level API for multi-goal orchestration.

    Combines all components into a simple interface:
    - Create goals and tasks
    - Auto-detect relationships
    - Execute with appropriate strategy
    - Track progress
    """

    def __init__(
        self,
        name: str = "goal_orchestrator",
        detector: RelationshipDetection | None = None,
        executor: ExecutionStrategy | None = None
    ):
        self.name = name
        self.dag = MultiGoalDAG(name=name)
        self.detector = detector or RelationshipDetection()
        self.executor = executor or TopologicalExecutor()

    def add_goal(
        self,
        title: str,
        description: str = "",
        success_criteria: List[str] | None = None,
        priority: Priority = Priority.NORMAL
    ) -> GoalNode:
        """Add a new goal."""
        goal = NodeFactory.create_goal(
            title=title,
            description=description,
            success_criteria=success_criteria,
            priority=priority
        )
        self.dag.add_node(goal)
        return goal

    def add_task(
        self,
        title: str,
        description: str = "",
        task_type: str = "generic",
        priority: Priority = Priority.NORMAL
    ) -> TaskNode:
        """Add a new task."""
        task = NodeFactory.create_task(
            title=title,
            description=description,
            task_type=task_type,
            priority=priority
        )
        self.dag.add_node(task)
        return task

    def relate(
        self,
        source_id: str,
        target_id: str,
        relationship: RelationshipType,
        **metadata
    ) -> None:
        """Create a relationship between two nodes."""
        edge_builder = edge(source_id, target_id)

        method_map = {
            RelationshipType.ENABLES: edge_builder.enables,
            RelationshipType.SUBGOAL_OF: edge_builder.subgoal_of,
            RelationshipType.SYNERGISTIC: edge_builder.synergistic,
            RelationshipType.CONFLICTS_WITH: edge_builder.conflicts,
            RelationshipType.REINFORCES: edge_builder.reinforces,
            RelationshipType.INDEPENDENT: edge_builder.independent,
        }

        builder = method_map[relationship]()
        for key, value in metadata.items():
            if key == "strategy":
                builder = builder.synergistic(value)
            elif key == "boost_factor":
                builder = builder.with_weight(value)

        self.dag.add_edge(builder.build())

    def auto_relate(self, goal1: GoalNode, goal2: GoalNode) -> RelationshipType:
        """Auto-detect and create relationship between goals."""
        relationship = self.detector.detect(goal1, goal2)
        self.dag.add_edge(
            DependencyEdge(
                source_id=goal1.id,
                target_id=goal2.id,
                relationship=relationship
            )
        )
        return relationship

    def decompose(
        self,
        goal_id: str,
        subgoal_ids: List[str] | None = None,
        task_ids: List[str] | None = None
    ) -> None:
        """Decompose a goal into subgoals/tasks."""
        goal = self.dag.get_node(goal_id)
        if not isinstance(goal, GoalNode):
            raise ValueError(f"{goal_id} is not a GoalNode")

        if subgoal_ids:
            for sub_id in subgoal_ids:
                goal.add_subgoal(sub_id)
                self.relate(sub_id, goal_id, RelationshipType.SUBGOAL_OF)

        if task_ids:
            for task_id in task_ids:
                goal.add_contributing_task(task_id)
                self.relate(task_id, goal_id, RelationshipType.ENABLES)

        goal.decomposition_complete = True

    async def execute(self, max_parallel: int = 4) -> Dict[str, Any]:
        """Execute all goals in the DAG."""
        # Validate before execution
        is_valid, errors = self.dag.validate()
        if not is_valid:
            raise ValueError(f"DAG validation failed: {errors}")

        # Execute
        return await self.executor.execute(self.dag, max_parallel)

    def get_progress(self, goal_id: str | None = None) -> Dict[str, float]:
        """Get progress for goals."""
        if goal_id:
            goal = self.dag.get_node(goal_id)
            if isinstance(goal, GoalNode):
                return {goal_id: goal.progress_fraction()}
            return {}

        # Return progress for all goals
        return {
            gid: g.progress_fraction()
            for gid, g in self.dag._nodes.items()
            if isinstance(g, GoalNode)
        }

    def get_status(self) -> Dict[str, Any]:
        """Get overall status."""
        goals = self.dag.get_nodes_by_type(GoalNode)
        tasks = self.dag.get_nodes_by_type(TaskNode)

        return {
            "name": self.name,
            "goals": {
                "total": len(goals),
                "pending": sum(1 for g in goals if g.status == NodeStatus.PENDING),
                "in_progress": sum(1 for g in goals if g.status == NodeStatus.IN_PROGRESS),
                "completed": sum(1 for g in goals if g.status == NodeStatus.COMPLETED),
                "failed": sum(1 for g in goals if g.status == NodeStatus.FAILED),
            },
            "tasks": {
                "total": len(tasks),
                "pending": sum(1 for t in tasks if t.status == NodeStatus.PENDING),
                "in_progress": sum(1 for t in tasks if t.status == NodeStatus.IN_PROGRESS),
                "completed": sum(1 for t in tasks if t.status == NodeStatus.COMPLETED),
                "failed": sum(1 for t in tasks if t.status == NodeStatus.FAILED),
            },
            "execution_order": self.dag.execution_order(),
            "ready_nodes": self.dag.get_ready_nodes(),
        }

    def visualize(self, output_path: str | None = None) -> str:
        """Generate visualization."""
        return self.dag.visualize(output_path)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return self.dag.to_dict()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GoalOrchestrator:
        """Deserialize from dictionary."""
        model = DAGStateModel(**data)
        dag = model.to_dag()

        orchestrator = cls(name=dag.name)
        orchestrator.dag = dag

        return orchestrator


# =============================================================================
# 8. EXAMPLE USAGE
# =============================================================================


async def example_multi_goal_orchestration() -> None:
    """Example of multi-goal orchestration."""

    # Create orchestrator
    orchestrator = GoalOrchestrator(name="example_project")

    # Create goals
    revenue_goal = orchestrator.add_goal(
        title="Earn $1000 monthly revenue",
        description="Generate recurring income through SaaS products",
        success_criteria=["Launch product", "Get 10 customers", "$1000 MRR"],
        priority=Priority.HIGH
    )

    community_goal = orchestrator.add_goal(
        title="Build developer community",
        description="Create engaged community around products",
        success_criteria=["1000 Discord members", "Weekly events"],
        priority=Priority.NORMAL
    )

    # Create tasks for revenue goal
    product_task = orchestrator.add_task(
        title="Build MVP product",
        description="Create minimum viable product",
        task_type="code",
        priority=Priority.HIGH
    )

    stripe_task = orchestrator.add_task(
        title="Integrate payments",
        description="Add Stripe for payment processing",
        task_type="code",
        priority=Priority.NORMAL
    )

    # Create tasks for community goal
    discord_task = orchestrator.add_task(
        title="Set up Discord server",
        description="Create community Discord",
        task_type="ops",
        priority=Priority.NORMAL
    )

    content_task = orchestrator.add_task(
        title="Create content strategy",
        description="Plan content for community growth",
        task_type="writing",
        priority=Priority.NORMAL
    )

    # Decompose goals
    orchestrator.decompose(
        revenue_goal.id,
        task_ids=[product_task.id, stripe_task.id]
    )

    orchestrator.decompose(
        community_goal.id,
        task_ids=[discord_task.id, content_task.id]
    )

    # Auto-detect relationship (likely synergistic)
    relationship = orchestrator.auto_relate(revenue_goal, community_goal)
    print(f"Detected relationship: {relationship.value}")

    # Add enabling relationship between tasks
    orchestrator.relate(product_task.id, stripe_task.id, RelationshipType.ENABLES)

    # Get status
    status = orchestrator.get_status()
    print(f"Status: {json.dumps(status, indent=2)}")

    # Visualize
    dot = orchestrator.visualize()
    print(f"DAG visualization:\n{dot}")

    # Execute (in production, this would run actual tasks)
    results = await orchestrator.execute(max_parallel=2)
    print(f"Execution results: {json.dumps(results, indent=2)}")


# =============================================================================
# SUMMARY: KEY PATTERNS EXPLORED
# =============================================================================

"""
1. GOAL VS TASK CLASSES
   - BaseNode abstract base class with common properties
   - GoalNode for high-level objectives with aggregating progress
   - TaskNode for atomic executable units
   - PriorityMixin for consistent priority handling
   - NodeFactory for validated creation

2. RELATIONSHIP TYPES
   - Enum-based typed relationships (ENABLES, SYNERGISTIC, etc.)
   - DependencyEdge immutable dataclass
   - EdgeBuilder for fluent construction
   - Helper function edge() for readable syntax

3. DETECTION ALGORITHM
   - JaccardSimilarity for fast keyword-based comparison
   - EmbeddingSimilarity for semantic comparison
   - RelationshipDetection combining heuristics
   - LLMRelationshipDetector for AI-based classification
   - HybridRelationshipDetector for best of both

4. GRAPH EXECUTION
   - MultiGoalDAG wrapping NetworkX MultiDiGraph
   - TopologicalExecutor for level-by-level execution
   - SynergyExecutor for merging synergistic goals
   - Parallel execution within dependency levels
   - Cycle detection and validation

5. STATE MANAGEMENT
   - Progress aggregation in GoalNode.progress_fraction()
   - Status tracking via NodeStatus enum
   - Pydantic models for serialization
   - DAG persistence via to_dict/from_dict
   - Real-time progress queries

USAGE EXAMPLES:

    # Basic usage
    orchestrator = GoalOrchestrator()
    goal = orchestrator.add_goal("My Goal")
    task = orchestrator.add_task("My Task")
    orchestrator.relate(task.id, goal.id, RelationshipType.ENABLES)
    await orchestrator.execute()

    # Advanced usage
    orchestrator.auto_relate(goal1, goal2)  # Auto-detect relationship
    orchestrator.decompose(goal.id, subgoal_ids=[s1, s2], task_ids=[t1])
    progress = orchestrator.get_progress(goal.id)
    status = orchestrator.get_status()

INTEGRATION WITH EXISTING CODE:

    # Can integrate with DelegationProtocol
    protocol = DelegationProtocol(memory=memory)

    async def execute_with_delegation(task: TaskNode) -> Any:
        result = protocol.delegate_task(
            task_description=task.title,
            context={"task_id": task.id},
            priority=task.priority.name.lower()
        )
        return result

    executor = TopologicalExecutor(executor=execute_with_delegation)
    orchestrator.executor = executor
"""

if __name__ == "__main__":
    # Run example
    logging.basicConfig(level=logging.INFO)
    asyncio.run(example_multi_goal_orchestration())
