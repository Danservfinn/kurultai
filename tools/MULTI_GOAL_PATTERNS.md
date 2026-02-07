# Multi-Goal DAG Orchestration: Python Implementation Patterns

## Executive Summary

This document provides concrete Python patterns for extending Kurultai's Task Dependency Engine to support multi-goal orchestration. The implementation addresses:

1. **Goal vs Task Classes**: Hierarchical design with inheritance
2. **Relationship Types**: Typed edges with semantic meaning
3. **Detection Algorithm**: Hybrid rule-based + LLM approach
4. **Graph Execution**: NetworkX-based with parallel execution
5. **State Management**: Progress aggregation and tracking

---

## 1. Goal vs Task Classes

### Pattern: Abstract Base Class with Template Method

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto

class NodeStatus(Enum):
    PENDING = auto()
    READY = auto()
    IN_PROGRESS = auto()
    BLOCKED = auto()
    COMPLETED = auto()
    FAILED = auto()

@dataclass
class BaseNode(ABC):
    """Abstract base for all graph nodes."""
    id: str
    title: str
    status: NodeStatus = NodeStatus.PENDING
    priority: int = 0

    @abstractmethod
    def progress_fraction(self) -> float:
        """Each node type defines its own progress calculation."""
        ...

@dataclass
class TaskNode(BaseNode):
    """Atomic executable unit."""
    task_type: str
    assigned_to: str | None = None
    result: Any = None

    def progress_fraction(self) -> float:
        # Binary: done or not done
        return 1.0 if self.status == NodeStatus.COMPLETED else 0.0

@dataclass
class GoalNode(BaseNode):
    """High-level objective with sub-components."""
    success_criteria: list[str]
    contributing_tasks: list[str]
    contributing_subgoals: list[str]

    def progress_fraction(self) -> float:
        # Aggregate from children
        # Weighted average of task completion + subgoal progress
        ...
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Separate `GoalNode` and `TaskNode` | Goals are aggregating containers; Tasks are executable units |
| Shared `BaseNode` | Common properties (id, status, priority) apply to both |
| Abstract `progress_fraction()` | Each type computes progress differently |
| `contributing_tasks` + `contributing_subgoals` | Goals track both leaf tasks and nested goals |

### Alternative: Single Node Class with Type Discriminator

```python
@dataclass
class Node:
    id: str
    title: str
    node_type: Literal["goal", "task"]
    # Goal-specific fields (only used when node_type == "goal")
    success_criteria: list[str] = field(default_factory=list)
    contributing_tasks: list[str] = field(default_factory=list)
    # Task-specific fields
    task_type: str = "generic"

    def is_goal(self) -> bool:
        return self.node_type == "goal"

    def is_task(self) -> bool:
        return self.node_type == "task"
```

**Trade-off**: Single class is simpler to serialize but loses type safety and compile-time checking.

---

## 2. Relationship Types

### Pattern: Typed Edges with Relationship Enum

```python
class RelationshipType(Enum):
    """Semantic relationship types between goals."""
    INDEPENDENT = "parallel_ok"      # Can run in parallel
    SYNERGISTIC = "merge_into"       # Should be unified
    ENABLES = "blocks"               # Sequential dependency
    SUBGOAL_OF = "part_of"           # Hierarchical
    CONFLICTS_WITH = "mutex"         # Cannot both execute
    REINFORCES = "amplifies"         # Better together

@dataclass(frozen=True)
class DependencyEdge:
    """Immutable edge between nodes."""
    source_id: str
    target_id: str
    relationship: RelationshipType
    weight: float = 1.0
```

### Fluent Builder API

```python
# Readable edge construction
edge(goal_a, goal_b).enables()
edge(goal_a, goal_b).synergistic(strategy="unified")
edge(goal_a, goal_b).conflicts()
edge(goal_a, goal_b).reinforces(boost_factor=1.5)

# With chaining
edge(goal_a, goal_b) \
    .synergistic() \
    .with_weight(2.0) \
    .with_metadata(strategy="merge", confidence=0.9) \
    .build()
```

### NetworkX Integration

```python
import networkx as nx

class MultiGoalDAG:
    def __init__(self):
        # MultiDiGraph allows parallel edges (different relationship types)
        self.graph = nx.MultiDiGraph()

    def add_edge(self, edge: DependencyEdge):
        self.graph.add_edge(
            edge.source_id,
            edge.target_id,
            relationship=edge.relationship.value,
            weight=edge.weight,
        )
```

### Relationship Semantics

| Relationship | Direction | Execution Meaning |
|--------------|-----------|-------------------|
| `ENABLES` | A -> B | A must complete before B starts |
| `SUBGOAL_OF` | A -> B | A is part of B (B completes when A does) |
| `SYNERGISTIC` | A <-> B | Merge into single execution plan |
| `CONFLICTS_WITH` | A <-> B | Cannot execute both; choose one |
| `REINFORCES` | A <-> B | Execute together for better results |
| `INDEPENDENT` | A, B | No coordination needed |

---

## 3. Detection Algorithm

### Three-Tier Strategy

```python
class RelationshipDetector:
    """Multi-tier relationship detection."""

    def __init__(self):
        # Tier 1: Fast keyword-based
        self.keyword_detector = KeywordRelationshipDetector()
        # Tier 2: Semantic similarity
        self.semantic_detector = SemanticRelationshipDetector()
        # Tier 3: LLM-based (expensive but accurate)
        self.llm_detector = LLMRelationshipDetector(api_key=...)

    async def detect(self, goal1, goal2) -> RelationshipType:
        # Try keyword first (fastest)
        result = self.keyword_detector.detect(goal1, goal2)
        if result.confidence > 0.8:
            return result.relationship

        # Try semantic similarity
        result = self.semantic_detector.detect(goal1, goal2)
        if result.confidence > 0.7:
            return result.relationship

        # Fall back to LLM
        return await self.llm_detector.detect(goal1, goal2)
```

### Keyword-Based Detection

```python
class KeywordRelationshipDetector:
    def __init__(self):
        self.patterns = {
            RelationshipType.ENABLES: [
                r"requires", r"needs", r"depends on", r"prerequisite"
            ],
            RelationshipType.CONFLICTS_WITH: [
                r"vs", r"versus", r"instead of", r"alternative"
            ],
            RelationshipType.REINFORCES: [
                r"supports", r"enhances", r"complements"
            ],
        }

    def detect(self, goal1, goal2) -> DetectionResult:
        text = f"{goal1.title} {goal1.description} {goal2.title} {goal2.description}"

        for rel_type, patterns in self.patterns.items():
            if any(re.search(p, text, re.I) for p in patterns):
                return DetectionResult(relationship=rel_type, confidence=0.9)

        return DetectionResult(relationship=RelationshipType.INDEPENDENT, confidence=0.5)
```

### Semantic Similarity Detection

```python
class SemanticRelationshipDetector:
    def __init__(self):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer('all-MiniLM-L6-v2')

    def detect(self, goal1, goal2) -> DetectionResult:
        emb1 = self.model.encode(f"{goal1.title} {goal1.description}")
        emb2 = self.model.encode(f"{goal2.title} {goal2.description}")

        similarity = cosine_similarity(emb1, emb2)

        if similarity > 0.7:
            return DetectionResult(
                relationship=RelationshipType.SYNERGISTIC,
                confidence=similarity
            )

        return DetectionResult(
            relationship=RelationshipType.INDEPENDENT,
            confidence=1.0 - similarity
        )
```

### LLM-Based Detection

```python
class LLMRelationshipDetector:
    def __init__(self, api_key: str, model: str = "claude-3-haiku"):
        self.client = Anthropic(api_key=api_key)
        self.model = model

    async def detect(self, goal1, goal2) -> RelationshipType:
        prompt = f"""
Classify the relationship between these goals:

Goal A: {goal1.title}
Description: {goal1.description}

Goal B: {goal2.title}
Description: {goal2.description}

Possible relationships:
- INDEPENDENT: Can pursue in parallel
- SYNERGISTIC: Should merge into unified strategy
- ENABLES: One must complete before the other
- SUBGOAL_OF: One is part of the other
- CONFLICTS_WITH: Cannot pursue both
- REINFORCES: Enhances each other

Respond with just the relationship name.
"""

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=20,
            messages=[{"role": "user", "content": prompt}]
        )

        return RelationshipType(response.content.strip())
```

### Detection Performance Comparison

| Method | Speed | Accuracy | Cost |
|--------|-------|----------|------|
| Keyword-based | ~1ms | 60-70% | Free |
| Embedding similarity | ~50ms | 75-85% | Free (local) |
| LLM-based | ~1000ms | 90-95% | $0.001-0.01 per call |

**Recommendation**: Hybrid approach - use keyword/embedding first, LLM for ambiguous cases.

---

## 4. Graph Execution

### Pattern: Topological Sort with Priority Levels

```python
class DAGExecutor:
    """Execute DAG in topological order with parallelization."""

    async def execute(self, dag: MultiGoalDAG, max_parallel: int = 4):
        # 1. Validate no cycles
        if not self._is_valid_dag(dag):
            raise ValueError("DAG contains cycles")

        # 2. Compute execution order
        levels = self._compute_execution_levels(dag)

        # 3. Execute level by level
        for level, nodes in levels.items():
            # Execute nodes at this level in parallel
            await self._execute_level(nodes, max_parallel)

    def _compute_execution_levels(self, dag) -> dict[int, list[str]]:
        """Group nodes by dependency depth."""
        levels = {}
        for node_id in dag.graph.nodes():
            level = self._dependency_depth(dag, node_id)
            levels.setdefault(level, []).append(node_id)
        return levels

    def _dependency_depth(self, dag, node_id: str) -> int:
        """Calculate how deep a node is in the dependency chain."""
        max_depth = 0
        for pred in dag.graph.predecessors(node_id):
            if self._is_enabling_dependency(dag, pred, node_id):
                depth = self._dependency_depth(dag, pred) + 1
                max_depth = max(max_depth, depth)
        return max_depth
```

### Parallel Execution with Semaphore

```python
import asyncio

async def execute_parallel(nodes: list[TaskNode], max_parallel: int):
    """Execute nodes with limited parallelism."""
    semaphore = asyncio.Semaphore(max_parallel)

    async def execute_one(node: TaskNode):
        async with semaphore:
            return await execute_node(node)

    tasks = [execute_one(node) for node in nodes]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

### Handling Synergistic Goals

```python
class SynergyAwareExecutor(DAGExecutor):
    """Executor that merges synergistic goals."""

    async def execute(self, dag: MultiGoalDAG, max_parallel: int = 4):
        # Find synergistic groups
        groups = self._find_synergy_groups(dag)

        # Create unified strategies
        for group in groups:
            unified_plan = await self._create_unified_plan(group)
            # Replace individual goals with unified plan
            self._merge_goals(dag, group, unified_plan)

        # Execute normally
        return await super().execute(dag, max_parallel)

    def _find_synergy_groups(self, dag) -> list[set[str]]:
        """Find connected components via SYNERGISTIC edges."""
        groups = []
        visited = set()

        for node in dag.graph.nodes():
            if node in visited:
                continue

            # Find all nodes connected via synergistic edges
            group = self._dfs_synergy(dag, node, visited)
            if len(group) > 1:
                groups.append(group)

        return groups
```

### Cycle Detection

```python
def detect_cycles(dag: MultiGoalDAG) -> list[list[str]]:
    """Detect cycles in enabling/subgoal relationships."""
    # Extract only enabling and subgoal edges (these form the dependency graph)
    dep_edges = [
        (u, v)
        for u, v, data in dag.graph.edges(data=True)
        if data.get("relationship") in ["blocks", "part_of"]
    ]

    dep_graph = nx.DiGraph(dep_edges)
    return list(nx.simple_cycles(dep_graph))
```

---

## 5. State Management

### Pattern: Aggregating Progress

```python
@dataclass
class GoalNode:
    contributing_tasks: list[str]
    contributing_subgoals: list[str]

    def progress_fraction(self) -> float:
        """
        Progress = weighted average of:
        - Direct tasks (100% if complete)
        - Subgoals (their current progress)
        """
        if not self.contributing_tasks and not self.contributing_subgoals:
            return 0.0

        total = 0.0
        weight_sum = 0.0

        # Get task completion status
        for task_id in self.contributing_tasks:
            task = self._get_task(task_id)
            total += 1.0 if task.status == NodeStatus.COMPLETED else 0.0
            weight_sum += 1.0

        # Get subgoal progress
        for goal_id in self.contributing_subgoals:
            goal = self._get_goal(goal_id)
            total += goal.progress_fraction()
            weight_sum += 1.0

        return total / weight_sum if weight_sum > 0 else 0.0
```

### Progress Tracking in Neo4j

```cypher
-- Goal node with progress tracking
CREATE (g:Goal {
    id: "goal-123",
    title: "Earn $1000",
    progress: 0.0,
    contributing_tasks: ["task-1", "task-2"],
    contributing_subgoals: ["subgoal-1"]
})

-- Update progress when task completes
MATCH (g:Goal {id: "goal-123"})
MATCH (t:Task {id: "task-2"})
SET g.progress = (
    CASE t.status
        WHEN "completed" THEN g.progress + 0.5
        ELSE g.progress
    END
)
```

### State Persistence

```python
from pydantic import BaseModel

class GoalState(BaseModel):
    """Serializable goal state."""
    id: str
    title: str
    status: str
    progress: float
    contributing_tasks: list[str]

    def save(self, db):
        db.execute("""
            MERGE (g:Goal {id: $id})
            SET g.progress = $progress,
                g.status = $status,
                g.updated_at = datetime()
        """, {"id": self.id, "progress": self.progress, "status": self.status})

    @classmethod
    def load(cls, db, goal_id: str) -> GoalState:
        result = db.execute("""
            MATCH (g:Goal {id: $id})
            RETURN g
        """, {"id": goal_id})
        return cls(**result[0])
```

---

## 6. Integration with Existing Code

### Integrating with DelegationProtocol

```python
# In existing delegation_protocol.py
from multi_goal_orchestration import GoalNode, TaskNode, MultiGoalDAG

class DelegationProtocol:
    def __init__(self, memory, dag: MultiGoalDAG):
        self.memory = memory
        self.dag = dag

    def delegate_goal(self, goal: GoalNode) -> DelegationResult:
        """Delegate a goal that decomposes into tasks."""
        # Decompose goal into subtasks
        tasks = self._decompose_goal(goal)

        # Add tasks to DAG
        for task in tasks:
            self.dag.add_node(task)
            self.dag.add_edge(
                DependencyEdge(
                    source_id=task.id,
                    target_id=goal.id,
                    relationship=RelationshipType.ENABLES
                )
            )

        # Create task nodes in Neo4j
        for task in tasks:
            self._create_task_in_neo4j(task)

        return DelegationResult(
            success=True,
            task_id=goal.id,
            message=f"Goal {goal.title} decomposed into {len(tasks)} tasks"
        )
```

### Integrating with OperationalMemory

```python
# Extend OperationalMemory to support goals
class OperationalMemory:
    def create_goal(self, goal: GoalNode) -> str:
        """Create a goal node in Neo4j."""
        cypher = """
        CREATE (g:Goal {
            id: $id,
            title: $title,
            description: $description,
            status: 'pending',
            progress: 0.0,
            priority: $priority,
            created_at: datetime()
        })
        RETURN g.id as id
        """
        with self._session() as session:
            result = session.run(
                cypher,
                id=goal.id,
                title=goal.title,
                description=goal.description,
                priority=goal.priority.value
            )
            return result.single()["id"]

    def update_goal_progress(self, goal_id: str, progress: float) -> None:
        """Update goal progress."""
        cypher = """
        MATCH (g:Goal {id: $id})
        SET g.progress = $progress,
            g.updated_at = datetime()
        """
        with self._session() as session:
            session.run(cypher, id=goal_id, progress=progress)
```

---

## 7. Usage Examples

### Example 1: Independent Goals

```python
orchestrator = GoalOrchestrator(name="independent_goals")

# Create two independent goals
goal1 = orchestrator.add_goal("Fix bug in authentication")
goal2 = orchestrator.add_goal("Write API documentation")

# Auto-detect relationship (should be INDEPENDENT)
rel = orchestrator.auto_relate(goal1, goal2)
print(f"Relationship: {rel}")  # INDEPENDENT

# Execute in parallel
await orchestrator.execute(max_parallel=2)
```

### Example 2: Synergistic Goals

```python
orchestrator = GoalOrchestrator(name="synergistic_goals")

# Create synergistic goals
revenue = orchestrator.add_goal(
    "Earn $1000 monthly",
    success_criteria=["Launch product", "Get customers"]
)
community = orchestrator.add_goal(
    "Build developer community",
    success_criteria=["1000 members", "Weekly events"]
)

# Mark as synergistic (should be merged)
orchestrator.relate(revenue.id, community.id, RelationshipType.SYNERGISTIC)

# Execute with synergy-aware strategy
orchestrator.executor = SynergyExecutor()
await orchestrator.execute()
```

### Example 3: Sequential Goals

```python
orchestrator = GoalOrchestrator(name="sequential_goals")

research = orchestrator.add_goal("Research market fit")
prototype = orchestrator.add_goal("Build prototype")
launch = orchestrator.add_goal("Launch product")

# Chain them sequentially
orchestrator.relate(research.id, prototype.id, RelationshipType.ENABLES)
orchestrator.relate(prototype.id, launch.id, RelationshipType.ENABLES)

# Execute in order
await orchestrator.execute()
```

---

## 8. Testing Strategies

```python
import pytest
from multi_goal_orchestration import GoalOrchestrator, RelationshipType

def test_goal_creation():
    orchestrator = GoalOrchestrator()
    goal = orchestrator.add_goal("Test Goal")
    assert goal.title == "Test Goal"
    assert goal.status == NodeStatus.PENDING

def test_edge_creation():
    orchestrator = GoalOrchestrator()
    g1 = orchestrator.add_goal("Goal 1")
    g2 = orchestrator.add_goal("Goal 2")
    orchestrator.relate(g1.id, g2.id, RelationshipType.ENABLES)
    assert len(orchestrator.dag.graph.edges) == 1

def test_cycle_detection():
    orchestrator = GoalOrchestrator()
    g1, g2, g3 = [orchestrator.add_goal(f"G{i}") for i in range(3)]
    orchestrator.relate(g1.id, g2.id, RelationshipType.ENABLES)
    orchestrator.relate(g2.id, g3.id, RelationshipType.ENABLES)
    orchestrator.relate(g3.id, g1.id, RelationshipType.ENABLES)
    is_valid, errors = orchestrator.dag.validate()
    assert not is_valid
    assert "cycle" in errors[0].lower()

@pytest.mark.asyncio
async def test_execution_order():
    orchestrator = GoalOrchestrator()
    g1, g2, g3 = [orchestrator.add_goal(f"G{i}") for i in range(3)]
    orchestrator.relate(g1.id, g2.id, RelationshipType.ENABLES)
    orchestrator.relate(g2.id, g3.id, RelationshipType.ENABLES)
    order = orchestrator.dag.execution_order()
    assert order.index(g1.id) < order.index(g2.id)
    assert order.index(g2.id) < order.index(g3.id)
```

---

## 9. Performance Considerations

| Operation | Complexity | Notes |
|-----------|------------|-------|
| Add node | O(1) | Direct graph insertion |
| Add edge | O(1) | Direct graph insertion |
| Cycle detection | O(V + E) | DFS-based |
| Topological sort | O(V + E) | Kahn's algorithm |
| Progress calculation | O(depth) | Recursive for nested goals |
| Relationship detection | O(1) - O(1000ms) | Depends on method |

### Optimization Tips

1. **Cache progress calculations**: Store computed progress and invalidate on changes
2. **Batch relationship detection**: Detect all relationships in one LLM call
3. **Use async I/O**: Parallelize external operations (API calls, database)
4. **Limit LLM calls**: Use keyword/embedding pre-filtering

---

## 10. Next Steps

1. **Integrate with Neo4j**: Persist graph structure in database
2. **Add webhook support**: Notify on goal completion
3. **Build visualization UI**: Show DAG in steppe-visualization
4. **Add retry logic**: Handle transient failures
5. **Implement rollback**: Revert failed goal executions

---

## References

- NetworkX Documentation: https://networkx.org/documentation/stable/
- Neo4j Python Driver: https://neo4j.com/docs/python-manual/
- Pydantic Documentation: https://docs.pydantic.dev/
