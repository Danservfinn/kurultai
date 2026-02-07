# Multi-Goal Orchestration Architecture for Kublai

> **Status**: Design Document
> **Date**: 2026-02-04
> **Author**: Backend System Architecture
> **Extends**: kurultai_0.1.md (Task Dependency Engine)

---

## Executive Summary

This document extends the Task Dependency Engine (kurultai_0.1) to support **multi-goal orchestration**, where Kublai detects relationships between user goals and synthesizes unified execution strategies. The system distinguishes between tasks (immediate actions) and goals (longer-term objectives), enabling:

1. **Independent goals** - execute in parallel without interference
2. **Synergistic goals** - merge into unified strategy (e.g., "Earn 1,000 USDC" + "Start money-making community")
3. **Sequential goals** - one enables the other (e.g., "Learn Python" before "Build ML app")

---

## 1. Goal Relationship Detection

### 1.1 Detection Dimensions

Kublai uses three orthogonal dimensions to classify goal relationships:

#### A. Semantic Similarity (Content Overlap)

```python
async def calculate_semantic_similarity(goal_a: GoalNode, goal_b: GoalNode) -> float:
    """
    Calculate semantic similarity between goals using multiple signals.

    Returns: float between 0.0 (unrelated) and 1.0 (identical intent)
    """
    signals = []

    # 1. Embedding cosine similarity (primary signal)
    embedding_sim = cosine_similarity(
        goal_a.embedding,
        goal_b.embedding
    )
    signals.append(("embedding", embedding_sim, 0.5))

    # 2. Domain overlap (Concept graph intersection)
    domain_overlap = await calculate_domain_intersection(goal_a, goal_b)
    signals.append(("domain", domain_overlap, 0.2))

    # 3. Resource category alignment (both require money? time? code?)
    resource_alignment = calculate_resource_alignment(goal_a, goal_b)
    signals.append(("resource", resource_alignment, 0.15))

    # 4. Deliverable type compatibility
    type_compatibility = calculate_type_compatibility(goal_a, goal_b)
    signals.append(("type", type_compatibility, 0.15))

    # Weighted combination
    similarity = sum(score * weight for _, score, weight in signals)
    return similarity, dict(signals)


async def calculate_domain_intersection(goal_a: GoalNode, goal_b: GoalNode) -> float:
    """
    Calculate how much the goals' required concepts overlap.

    Uses Neo4j to find shared Concept nodes between goals.
    """
    query = """
    MATCH (g1:Goal {id: $goal_a})-[:REQUIRES_CONCEPT]->(c:Concept)<-[:REQUIRES_CONCEPT]-(g2:Goal {id: $goal_b})
    WITH count(c) as shared_concepts
    MATCH (g1:Goal {id: $goal_a})-[:REQUIRES_CONCEPT]->(all_c:Concept)
    WITH shared_concepts, count(all_c) as total_a
    MATCH (g2:Goal {id: $goal_b})-[:REQUIRES_CONCEPT]->(all_c2:Concept)
    RETURN shared_concepts * 1.0 / (total_a + count(all_c2) - shared_concepts) as jaccard
    """
    result = await neo4j.run(query, {"goal_a": goal_a.id, "goal_b": goal_b.id})
    return result[0]["jaccard"] if result else 0.0
```

#### B. Temporal Constraints (Time Horizon)

```python
def classify_temporal_relationship(goal_a: GoalNode, goal_b: GoalNode) -> str:
    """
    Classify temporal relationship based on time horizons and dependencies.
    """
    # Extract temporal properties
    horizon_a = goal_a.time_horizon  # "immediate" | "short" | "medium" | "long"
    horizon_b = goal_b.time_horizon
    deadline_a = goal_a.target_date
    deadline_b = goal_b.target_date

    # Rule-based classification
    if horizon_a == "immediate" and horizon_b in ["medium", "long"]:
        return "sequential_a_enables_b"  # Quick win enables long-term

    if deadline_a and deadline_b:
        if deadline_a < deadline_b:
            return "sequential_a_precedes_b"
        elif deadline_b < deadline_a:
            return "sequential_b_precedes_a"

    # Same time horizon = potential for synergy or parallel
    if horizon_a == horizon_b:
        return "same_horizon_potential_synergy"

    return "temporal_independent"
```

#### C. Resource Competition (Execution Constraints)

```python
async def detect_resource_competition(goal_a: GoalNode, goal_b: GoalNode) -> dict:
    """
    Detect if goals compete for the same resources (agents, budget, attention).

    Returns: {
        "competes": bool,
        "competition_level": "none" | "low" | "medium" | "high",
        "conflicting_resources": [str]
    }
    """
    conflicts = []

    # 1. Agent competition (both need the same specialist)
    agents_a = set(goal_a.required_agents)
    agents_b = set(goal_b.required_agents)
    shared_agents = agents_a & agents_b

    if shared_agents:
        # Check if agent is over capacity
        for agent_id in shared_agents:
            current_load = await get_agent_load(agent_id)
            if current_load >= 0.8:  # 80% capacity
                conflicts.append(f"agent:{agent_id}")

    # 2. Budget competition
    if goal_a.estimated_cost and goal_b.estimated_cost:
        total_budget = await get_available_budget(goal_a.sender_hash)
        if (goal_a.estimated_cost + goal_b.estimated_cost) > total_budget:
            conflicts.append("budget")

    # 3. Time competition (both need immediate attention)
    if (goal_a.priority == "urgent" and goal_b.priority == "urgent" and
        goal_a.time_horizon == goal_b.time_horizon == "immediate"):
        conflicts.append("attention")

    competition_level = (
        "high" if len(conflicts) >= 2 else
        "medium" if len(conflicts) == 1 else
        "none"
    )

    return {
        "competes": len(conflicts) > 0,
        "competition_level": competition_level,
        "conflicting_resources": conflicts
    }
```

### 1.2 Relationship Classification Algorithm

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class GoalRelationship:
    goal_a_id: str
    goal_b_id: str
    relationship_type: Literal["independent", "synergistic", "sequential", "conflicting"]
    confidence: float
    reasoning: str
    signals: dict


async def classify_goal_relationship(goal_a: GoalNode, goal_b: GoalNode) -> GoalRelationship:
    """
    Classify the relationship between two goals using multi-dimensional analysis.
    """
    # Gather all signals
    semantic_sim, semantic_signals = await calculate_semantic_similarity(goal_a, goal_b)
    temporal_rel = classify_temporal_relationship(goal_a, goal_b)
    resource_comp = await detect_resource_competition(goal_a, goal_b)

    # Classification logic
    if resource_comp["competition_level"] == "high":
        return GoalRelationship(
            goal_a_id=goal_a.id,
            goal_b_id=goal_b.id,
            relationship_type="conflicting",
            confidence=0.9,
            reasoning=f"Goals compete for resources: {', '.join(resource_comp['conflicting_resources'])}",
            signals={"semantic": semantic_signals, "temporal": temporal_rel, "resource": resource_comp}
        )

    if "sequential" in temporal_rel:
        return GoalRelationship(
            goal_a_id=goal_a.id,
            goal_b_id=goal_b.id,
            relationship_type="sequential",
            confidence=0.85,
            reasoning=f"Temporal dependency: {temporal_rel}",
            signals={"semantic": semantic_signals, "temporal": temporal_rel, "resource": resource_comp}
        )

    if semantic_sim > 0.7:  # High similarity threshold
        return GoalRelationship(
            goal_a_id=goal_a.id,
            goal_b_id=goal_b.id,
            relationship_type="synergistic",
            confidence=semantic_sim,
            reasoning=f"High semantic similarity ({semantic_sim:.2f}) suggests shared strategy",
            signals={"semantic": semantic_signals, "temporal": temporal_rel, "resource": resource_comp}
        )

    if semantic_sim > 0.4 and temporal_rel == "same_horizon_potential_synergy":
        return GoalRelationship(
            goal_a_id=goal_a.id,
            goal_b_id=goal_b.id,
            relationship_type="synergistic",
            confidence=semantic_sim * 0.8,
            reasoning=f"Moderate similarity with same time horizon suggests potential synergy",
            signals={"semantic": semantic_signals, "temporal": temporal_rel, "resource": resource_comp}
        )

    # Default: independent
    return GoalRelationship(
        goal_a_id=goal_a.id,
        goal_b_id=goal_b.id,
        relationship_type="independent",
        confidence=1.0 - semantic_sim,
        reasoning="Low semantic similarity, no temporal dependency, no resource competition",
        signals={"semantic": semantic_signals, "temporal": temporal_rel, "resource": resource_comp}
    )
```

---

## 2. Goal Hierarchy Schema (Neo4j Extensions)

### 2.1 GoalNode Definition

```cypher
// GoalNode: Represents a long-term user objective (distinct from TaskNode)
(:GoalNode {
  // Identity
  id: uuid,                      // Unique identifier
  sender_hash: string,           // HMAC-SHA256 of sender phone
  title: string,                 // Human-readable goal title
  description: string,           // Full goal description

  // Semantic representation
  embedding: [float],            // 384-dim vector for similarity comparison

  // State
  status: string,                // "draft" | "active" | "paused" | "completed" | "abandoned"
  progress: float,               // 0.0-1.0 completion percentage

  // Temporal
  time_horizon: string,          // "immediate" | "short" (< 1 month) | "medium" (1-3 months) | "long" (> 3 months)
  target_date: date,             // Optional deadline
  created_at: datetime,
  activated_at: datetime,        // When goal moved from draft to active
  completed_at: datetime,

  // Execution
  priority: string,              // "urgent" | "high" | "normal" | "low"
  estimated_cost: float,         // USD (null if unknown)
  allocated_budget: float,       // USD budget assigned to this goal
  required_agents: [string],     // ["researcher", "analyst"]

  // Tracking
  current_phase: string,         // Current phase name (for phased goals)
  phases_count: int,             // Total number of phases
  milestone_count: int,          // Total milestones
  completed_milestones: int,     // Progress tracking

  // Meta
  parent_goal_id: uuid,          // If this is a sub-goal
  source_message: string,        // Original user message that created this
  synthesis_notes: string,       // Notes from goal synthesis
  access_tier: string            // "PUBLIC" | "SENSITIVE" | "PRIVATE"
})
```

### 2.2 Goal-Goal Relationships

```cypher
// Primary goal relationships
(:GoalNode)-[:IS_SUBGOAL_OF {
  order: int,                    // Subgoal sequence number
  required: boolean              // Must complete before parent advances
}]->(:GoalNode)

(:GoalNode)-[:ENABLES {
  confidence: float,             // 0.0-1.0 how much A enables B
  reason: string                 // Explanation of enablement
}]->(:GoalNode)

(:GoalNode)-[:SYNERGIZES_WITH {
  strength: float,               // 0.0-1.0 synergy strength
  detected_by: string,           // "semantic" | "user_explicit" | "pattern"
  merged_into: uuid,             // If merged, points to unified strategy
  merge_reason: string           // Why these were synergized
}]->(:GoalNode)

(:GoalNode)-[:COMPETES_WITH {
  resource_type: string,         // "agent" | "budget" | "attention"
  severity: string,              // "low" | "medium" | "high"
  resolution_strategy: string    // "sequential" | "prioritize" | "resource_add"
}]->(:GoalNode)

(:GoalNode)-[:BLOCKS {
  reason: string
}]->(:GoalNode)

// Goal-Task relationships (linking goals to executable tasks)
(:GoalNode)-[:HAS_TASK {
  phase: string,                 // Which phase this task belongs to
  order: int,                    // Execution order within phase
  required: boolean              // Required for goal completion
}]->(:Task)

(:GoalNode)-[:HAS_MILESTONE {
  name: string,
  description: string,
  target_date: date,
  achieved: boolean,
  achieved_at: datetime
}]->(:Milestone)

(:GoalNode)-[:REQUIRES_CONCEPT {
  importance: float              // 0.0-1.0 how critical this concept is
}]->(:Concept)
```

### 2.3 Milestone and Strategy Nodes

```cypher
// Milestone: Trackable progress marker
(:Milestone {
  id: uuid,
  title: string,
  description: string,
  target_date: date,
  achieved: boolean,
  achieved_at: datetime,
  verification_criteria: string,  // How to verify completion
  associated_tasks: [uuid],       // Tasks that contribute to this milestone
  contributes_to_goals: [uuid]    // Goals this milestone advances
})

// StrategyNode: Unified strategy for synergistic goals
(:StrategyNode {
  id: uuid,
  title: string,
  description: string,
  created_by: string,             // "kublai" | "user_explicit"
  created_at: datetime,
  embedding: [float],             // For strategy similarity search

  // Component goals
  component_goal_ids: [uuid],     // Goals merged into this strategy

  // Execution
  phases: [string],               // Phase names
  current_phase: int,             // Current phase index
  estimated_duration_days: int,

  // Results
  status: string,                 // "draft" | "active" | "completed"
  success_criteria: string,
  notes: string
})

(:StrategyNode)-[:ACHIEVES]->(:GoalNode)
(:StrategyNode)-[:CONSISTS_OF_PHASES]->(:Phase)
```

### 2.4 Indexes for Goal Operations

```cypher
// Primary lookups
CREATE INDEX goal_sender_status FOR (g:GoalNode) ON (g.sender_hash, g.status);

// Semantic similarity
CREATE VECTOR INDEX goal_embedding FOR (g:GoalNode) ON g.embedding
  OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}};

// Temporal queries
CREATE INDEX goal_target_date FOR (g:GoalNode) ON (g.target_date);
CREATE INDEX goal_time_horizon FOR (g:GoalNode) ON (g.time_horizon);

// Progress tracking
CREATE INDEX goal_progress FOR (g:GoalNode) ON (g.status, g.progress);

// Hierarchy navigation
CREATE INDEX goal_parent FOR (g:GoalNode) ON (g.parent_goal_id);

// Strategy lookup
CREATE INDEX strategy_status FOR (s:StrategyNode) ON (s.status, s.created_at);
```

---

## 3. Synthesis Algorithm (Merging Synergistic Goals)

### 3.1 Goal Clustering for Synthesis

```python
from typing import List, Set
from collections import defaultdict

async def cluster_synergistic_goals(
    goals: List[GoalNode],
    sender_hash: str
) -> List[List[GoalNode]]:
    """
    Cluster goals into synergistic groups using graph-based clustering.

    Returns: List of goal clusters (each cluster should become one strategy)
    """
    if len(goals) <= 1:
        return [goals] if goals else []

    # Build similarity graph
    similarity_graph = defaultdict(dict)
    clusters = []

    for i, goal_a in enumerate(goals):
        for goal_b in goals[i+1:]:
            relationship = await classify_goal_relationship(goal_a, goal_b)

            if relationship.relationship_type == "synergistic":
                similarity_graph[goal_a.id][goal_b.id] = relationship.confidence
                similarity_graph[goal_b.id][goal_a.id] = relationship.confidence

    # Find connected components (clusters)
    visited = set()

    def find_component(goal_id: str, current_cluster: Set[str]):
        visited.add(goal_id)
        current_cluster.add(goal_id)

        for neighbor_id in similarity_graph.get(goal_id, {}):
            if neighbor_id not in visited:
                find_component(neighbor_id, current_cluster)

    # Extract clusters
    goal_map = {g.id: g for g in goals}

    for goal in goals:
        if goal.id not in visited:
            cluster_ids = set()
            find_component(goal.id, cluster_ids)
            clusters.append([goal_map[gid] for gid in cluster_ids])

    return clusters


async def detect_goal_patterns(goals: List[GoalNode]) -> dict:
    """
    Detect common multi-goal patterns that suggest synthesis.

    Patterns:
    - "Earn X" + "Start community" → Community monetization strategy
    - "Learn X" + "Build Y" → Skill-to-project pipeline
    - "Launch X" + "Market X" → Go-to-market unified strategy
    """
    pattern_signals = {}

    # Pattern 1: Earning + Community = Community Monetization
    earning_goals = [g for g in goals if "earn" in g.description.lower() or "income" in g.description.lower()]
    community_goals = [g for g in goals if "community" in g.description.lower() or "audience" in g.description.lower()]

    if earning_goals and community_goals:
        pattern_signals["community_monetization"] = {
            "goals": [g.id for g in earning_goals + community_goals],
            "confidence": 0.9,
            "suggested_strategy": "Build community as path to earning (higher long-term value)"
        }

    # Pattern 2: Learning + Building = Skill-to-Project
    learning_goals = [g for g in goals if any(w in g.description.lower() for w in ["learn", "study", "master"])]
    building_goals = [g for g in goals if any(w in g.description.lower() for w in ["build", "create", "develop"])]
    tech_concepts = await extract_tech_concepts(learning_goals + building_goals)

    if learning_goals and building_goals and tech_concepts:
        pattern_signals["skill_to_project"] = {
            "learning_goals": [g.id for g in learning_goals],
            "building_goals": [g.id for g in building_goals],
            "shared_technologies": tech_concepts,
            "suggested_strategy": f"Learn {', '.join(tech_concepts)} through building project"
        }

    return pattern_signals
```

### 3.2 Strategy Generation

```python
@dataclass
class StrategyProposal:
    title: str
    description: str
    component_goals: List[str]  # Goal IDs
    phases: List[dict]
    estimated_duration: int
    expected_outcomes: List[str]
    tradeoffs: List[str]
    confidence: float


async def synthesize_strategy(
    synergistic_goals: List[GoalNode],
    pattern_signals: dict
) -> StrategyProposal:
    """
    Generate a unified strategy proposal from synergistic goals.
    """
    # Sort goals by time horizon (shorter first for quick wins)
    sorted_goals = sorted(
        synergistic_goals,
        key=lambda g: {"immediate": 0, "short": 1, "medium": 2, "long": 3}[g.time_horizon]
    )

    # Extract common concepts
    all_concepts = await get_common_concepts(synergistic_goals)

    # Determine strategy type based on pattern
    if "community_monetization" in pattern_signals:
        return await _build_community_monetization_strategy(sorted_goals, all_concepts)
    elif "skill_to_project" in pattern_signals:
        return await _build_skill_to_project_strategy(sorted_goals, all_concepts, pattern_signals["skill_to_project"])
    else:
        return await _build_generic_synergistic_strategy(sorted_goals, all_concepts)


async def _build_community_monetization_strategy(
    goals: List[GoalNode],
    concepts: List[str]
) -> StrategyProposal:
    """
    Build a strategy that combines earning with community building.
    """
    earning_goal = next((g for g in goals if "earn" in g.description.lower()), goals[0])
    community_goal = next((g for g in goals if "community" in g.description.lower()), goals[1])

    return StrategyProposal(
        title=f"Community-Powered {earning_goal.title}",
        description=f"""
Build a community that generates {earning_goal.description.lower()} as a natural outcome.

Instead of treating earning and community as separate goals, build a community where
the earning mechanism is embedded in the community value proposition.
        """.strip(),
        component_goals=[g.id for g in goals],
        phases=[
            {
                "name": "Phase 1: Research & Positioning",
                "duration_days": 7,
                "objectives": [
                    "Research existing communities in the space",
                    "Identify gaps and opportunities",
                    "Define community value proposition",
                    "Map monetization pathways"
                ],
                "assigned_to": ["researcher", "analyst"]
            },
            {
                "name": "Phase 2: MVP Community Launch",
                "duration_days": 14,
                "objectives": [
                    "Set up community platform (Moltbook, Discord, etc)",
                    "Create initial content to attract members",
                    "Define member tiers and benefits",
                    "Launch with founding member outreach"
                ],
                "assigned_to": ["developer", "writer"]
            },
            {
                "name": "Phase 3: Monetization Activation",
                "duration_days": 21,
                "objectives": [
                    "Implement premium membership tiers",
                    "Launch community offerings (courses, consulting, products)",
                    "Track member engagement and conversion",
                    "Iterate on value proposition"
                ],
                "assigned_to": ["analyst", "ops", "writer"]
            }
        ],
        estimated_duration_days=42,
        expected_outcomes=[
            f"Active community with 100+ members by day 30",
            f"First {earning_goal.description.lower()} by day 45",
            "Sustainable monetization mechanism by day 60",
            "Compound growth: community value increases over time"
        ],
        tradeoffs=[
            "Slower initial earning compared to direct freelancing",
            "Requires consistent community engagement effort",
            "Success depends on community growth velocity"
        ],
        confidence=0.85
    )


async def _build_skill_to_project_strategy(
    goals: List[GoalNode],
    concepts: List[str],
    pattern_data: dict
) -> StrategyProposal:
    """
    Build a strategy that combines learning with project-based application.
    """
    tech_stack = pattern_data.get("shared_technologies", concepts)

    return StrategyProposal(
        title=f"Learn-by-Building: {', '.join(tech_stack[:3])}",
        description=f"""
Accelerate learning of {', '.join(tech_stack)} by building a real project from day one.

Instead of sequential learning then building, interleave study with implementation.
Each concept learned is immediately applied to the project.
        """.strip(),
        component_goals=[g.id for g in goals],
        phases=[
            {
                "name": "Phase 1: Foundation + Project Setup",
                "duration_days": 7,
                "objectives": [
                    f"Set up project scaffold for {tech_stack[0] if tech_stack else 'chosen tech'}",
                    "Learn core concepts through targeted tutorials",
                    "Build first working prototype feature"
                ],
                "assigned_to": ["developer", "researcher"]
            },
            {
                "name": "Phase 2: Iterative Building",
                "duration_days": 14,
                "objectives": [
                    "Add features requiring deeper learning",
                    "Document learning from each implementation",
                    "Refactor based on new understanding"
                ],
                "assigned_to": ["developer"]
            },
            {
                "name": "Phase 3: Polish & Portfolio",
                "duration_days": 7,
                "objectives": [
                    "Complete project with production-ready features",
                    "Write project documentation and reflection",
                    "Package as portfolio piece"
                ],
                "assigned_to": ["developer", "writer"]
            }
        ],
        estimated_duration_days=28,
        expected_outcomes=[
            f"Functional project using {', '.join(tech_stack)}",
            "Practical understanding through application",
            "Portfolio-ready project",
            "Faster retention vs. theoretical study"
        ],
        tradeoffs=[
            "Initial project may need refactoring as understanding grows",
            "Requires balancing learning scope with project complexity"
        ],
        confidence=0.9
    )


async def _build_generic_synergistic_strategy(
    goals: List[GoalNode],
    concepts: List[str]
) -> StrategyProposal:
    """
    Build a generic strategy for synergistic goals without specific patterns.
    """
    # Extract common themes
    themes = await extract_common_themes(goals)

    return StrategyProposal(
        title=f"Unified Strategy: {' + '.join(g.title for g in goals[:3])}",
        description=f"""
These goals share common themes ({', '.join(themes)}) and can be pursued
through an integrated strategy that addresses all objectives simultaneously.
        """.strip(),
        component_goals=[g.id for g in goals],
        phases=[
            {
                "name": "Phase 1: Integrated Planning",
                "duration_days": 5,
                "objectives": [
                    "Map all goal requirements to shared tasks",
                    "Identify dependencies and quick wins",
                    "Create unified execution roadmap"
                ],
                "assigned_to": ["analyst", "ops"]
            },
            {
                "name": "Phase 2: Parallel Execution",
                "duration_days": max(g.estimated_duration_days or 14 for g in goals),
                "objectives": [
                    "Execute tasks in priority order",
                    "Share resources and learnings across goals",
                    "Track progress against all objectives"
                ],
                "assigned_to": goals[0].required_agents
            },
            {
                "name": "Phase 3: Consolidation",
                "duration_days": 7,
                "objectives": [
                    "Verify all goal milestones achieved",
                    "Document synergies and outcomes",
                    "Hand off deliverables"
                ],
                "assigned_to": ["ops", "analyst"]
            }
        ],
        estimated_duration_days=sum(g.estimated_duration_days or 7 for g in goals) // 2,
        expected_outcomes=[
            "All goals advanced through shared execution",
            "Efficient use of resources",
            "Coordinated outcomes with cross-benefits"
        ],
        tradeoffs=[
            "Requires careful coordination to avoid goal drift",
            "Progress may be slower on individual goals vs. focused pursuit"
        ],
        confidence=0.7
    )
```

### 3.3 Strategy Storage in Neo4j

```cypher
// Create strategy node from synthesized proposal
CREATE (s:StrategyNode {
  id: $strategy_id,
  title: $title,
  description: $description,
  created_by: "kublai",
  created_at: datetime(),
  component_goal_ids: $goal_ids,
  phases: $phases,
  current_phase: 0,
  estimated_duration_days: $duration,
  status: "active",
  success_criteria: $outcomes,
  notes: $tradeoffs
})

// Link strategy to component goals
MATCH (s:StrategyNode {id: $strategy_id})
MATCH (g:GoalNode)
WHERE g.id IN $goal_ids
CREATE (s)-[:ACHIEVES]->(g)

// Mark goals as part of strategy
MATCH (g:GoalNode)
WHERE g.id IN $goal_ids
SET g.status = "active_in_strategy",
    g.strategy_id = $strategy_id
```

---

## 4. Conflict Resolution

### 4.1 Conflict Detection

```python
@dataclass
class GoalConflict:
    goal_a_id: str
    goal_b_id: str
    conflict_type: Literal["resource", "temporal", "strategic"]
    severity: Literal["low", "medium", "high"]
    description: str
    resolution_options: List[dict]


async def detect_goal_conflicts(goals: List[GoalNode]) -> List[GoalConflict]:
    """
    Detect conflicts between goals that cannot be easily resolved.
    """
    conflicts = []

    for i, goal_a in enumerate(goals):
        for goal_b in goals[i+1:]:
            # Resource competition
            resource_comp = await detect_resource_competition(goal_a, goal_b)
            if resource_comp["competition_level"] in ["medium", "high"]:
                conflicts.append(GoalConflict(
                    goal_a_id=goal_a.id,
                    goal_b_id=goal_b.id,
                    conflict_type="resource",
                    severity=resource_comp["competition_level"],
                    description=f"Goals compete for: {', '.join(resource_comp['conflicting_resources'])}",
                    resolution_options=[
                        {"strategy": "sequential", "description": "Pursue goals one after another"},
                        {"strategy": "prioritize", "description": "Focus on higher-priority goal first"},
                        {"strategy": "resource_add", "description": "Add more resources (time/budget/agents)"}
                    ]
                ))

            # Strategic conflict (quick vs. long-term)
            if _has_strategic_conflict(goal_a, goal_b):
                conflicts.append(GoalConflict(
                    goal_a_id=goal_a.id,
                    goal_b_id=goal_b.id,
                    conflict_type="strategic",
                    severity="medium",
                    description=f"Strategic misalignment: {goal_a.time_horizon} vs {goal_b.time_horizon}",
                    resolution_options=[
                        {"strategy": "quick_first", "description": "Pursue quick win, then long-term"},
                        {"strategy": "long_term_focus", "description": "Invest in long-term, skip quick wins"},
                        {"strategy": "hybrid", "description": "Allocate 20% time to quick, 80% to long-term"}
                    ]
                ))

    return conflicts


def _has_strategic_conflict(goal_a: GoalNode, goal_b: GoalNode) -> bool:
    """
    Check if goals have conflicting strategic orientations.

    Examples:
    - "Earn quick money" vs. "Build sustainable business"
    - "Launch now" vs. "Perfect the product"
    """
    quick_indicators = ["quick", "fast", "immediate", "now", "asap"]
    long_term_indicators = ["sustainable", "long-term", "business", "company", "empire"]

    a_is_quick = any(ind in goal_a.description.lower() for ind in quick_indicators)
    b_is_long = any(ind in goal_b.description.lower() for ind in long_term_indicators)
    b_is_quick = any(ind in goal_b.description.lower() for ind in quick_indicators)
    a_is_long = any(ind in goal_a.description.lower() for ind in long_term_indicators)

    return (a_is_quick and b_is_long) or (b_is_quick and a_is_long)
```

### 4.2 Conflict Resolution Strategies

```python
async def resolve_conflict(
    conflict: GoalConflict,
    user_preference: dict = None
) -> dict:
    """
    Resolve a goal conflict based on user preferences or system defaults.

    Returns: Resolution plan with updated goal priorities and scheduling.
    """
    if conflict.conflict_type == "resource":
        return await _resolve_resource_conflict(conflict, user_preference)
    elif conflict.conflict_type == "strategic":
        return await _resolve_strategic_conflict(conflict, user_preference)
    else:
        return {"status": "user_decision_required", "conflict": conflict}


async def _resolve_resource_conflict(
    conflict: GoalConflict,
    preference: dict = None
) -> dict:
    """
    Resolve resource competition between goals.
    """
    if preference and preference.get("strategy") == "sequential":
        # Execute goals sequentially
        return {
            "resolution": "sequential",
            "plan": f"Execute {conflict.goal_a_id} first, then {conflict.goal_b_id}",
            "cypher": f"""
                MATCH (a:Goal {{id: '{conflict.goal_a_id}'}})
                MATCH (b:Goal {{id: '{conflict.goal_b_id}'}})
                CREATE (a)-[:BLOCKS {{reason: 'Resource conflict - sequential execution'}}]->(b)
                SET a.priority = 'high', b.priority = 'normal'
            """
        }

    elif preference and preference.get("strategy") == "prioritize":
        # Prioritize based on urgency and value
        return {
            "resolution": "prioritize",
            "plan": "Focus on higher-value goal, pause lower-value",
            "cypher": """
                // Would be generated dynamically based on goal priorities
            """
        }

    else:
        # Default: sequential with user confirmation
        return {
            "resolution": "proposed_sequential",
            "requires_user_confirmation": True,
            "message": f"""These goals compete for resources. I recommend pursuing them sequentially:

Option A: Focus on Goal 1 first, then Goal 2
Option B: Focus on Goal 2 first, then Goal 1

Which would you prefer? Or I can find a way to pursue both in parallel with more time."""
        }


async def _resolve_strategic_conflict(
    conflict: GoalConflict,
    preference: dict = None
) -> dict:
    """
    Resolve strategic conflicts (quick vs. long-term).
    """
    quick_goal = await get_goal(conflict.goal_a_id)
    long_goal = await get_goal(conflict.goal_b_id)

    return {
        "resolution": "hybrid_approach",
        "message": f"""I notice a strategic tension between your goals:

Quick Goal: {quick_goal.title} - Fast results, short-term impact
Long-term Goal: {long_goal.title} - Sustainable, compounding value

Recommendation: Hybrid approach
- 80% focus on long-term goal (builds lasting value)
- 20% focus on quick wins (maintains momentum, cash flow)

This avoids the trap of perpetual quick wins while ensuring you're not
building something that won't generate value for years.

Would you like to proceed with this hybrid approach, or would you prefer
to focus exclusively on one?""",
        "options": [
            {"id": "hybrid", "label": "Hybrid (80/20)"},
            {"id": "quick_only", "label": "Quick wins only"},
            {"id": "long_only", "label": "Long-term only"}
        ]
    }
```

### 4.3 Conflict Resolution Cypher

```cypher
// Mark goals as conflicting with resolution path
MATCH (a:Goal {id: $goal_a_id})
MATCH (b:Goal {id: $goal_b_id})
CREATE (a)-[:COMPETES_WITH {
  resource_type: $resource_type,
  severity: $severity,
  resolution_strategy: $strategy,
  resolution_notes: $notes,
  created_at: datetime()
}]->(b)

// Pause lower-priority goal when conflict exists
MATCH (g:Goal {id: $lower_priority_goal})
SET g.status = 'paused',
    g.pause_reason = 'Awaiting completion of conflicting higher-priority goal',
    g.resumes_after = $higher_priority_goal_id
```

---

## 5. Progress Tracking

### 5.1 Multi-Dimensional Progress Metrics

```python
@dataclass
class GoalProgress:
    goal_id: str
    overall_progress: float        # 0.0-1.0 overall completion
    milestone_progress: dict       # Milestone completion status
    phase_progress: dict           # Phase completion status
    task_progress: dict            # Task completion status
    resource_utilization: dict     # Budget, time, agent usage
    blockers: List[dict]           # Current blockers
    next_actions: List[dict]       # Immediate next steps
    eta: datetime                  # Estimated completion
    confidence: float              # ETA confidence


async def calculate_goal_progress(goal_id: str) -> GoalProgress:
    """
    Calculate multi-dimensional progress for a goal.
    """
    query = """
    MATCH (g:Goal {id: $goal_id})

    // Milestone progress
    OPTIONAL MATCH (g)-[:HAS_MILESTONE]->(m:Milestone)
    WITH g, count(m) as total_milestones, sum(CASE WHEN m.achieved THEN 1 ELSE 0 END) as completed_milestones

    // Task progress
    OPTIONAL MATCH (g)-[:HAS_TASK]->(t:Task)
    WITH g, total_milestones, completed_milestones,
         count(t) as total_tasks,
         sum(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) as completed_tasks

    // Phase progress (if part of strategy)
    OPTIONAL MATCH (g)<-[:ACHIEVES]-(s:StrategyNode)
    WITH g, total_milestones, completed_milestones, total_tasks, completed_tasks, s
    OPTIONAL MATCH (s)-[:CONSISTS_OF_PHASES]->(p:Phase)
    WITH g, total_milestones, completed_milestones, total_tasks, completed_tasks, s,
         count(p) as total_phases,
         s.current_phase as current_phase_idx

    // Sub-goal progress
    OPTIONAL MATCH (sub:Goal)-[:IS_SUBGOAL_OF]->(g)
    WITH g, total_milestones, completed_milestones, total_tasks, completed_tasks, s,
         total_phases, current_phase_idx,
         count(sub) as total_subgoals,
         sum(sub.progress) as subgoal_progress_sum

    RETURN g, total_milestones, completed_milestones, total_tasks, completed_tasks,
           total_phases, current_phase_idx, total_subgoals, subgoal_progress_sum
    """

    result = await neo4j.run(query, {"goal_id": goal_id})
    data = result[0]

    # Calculate overall progress as weighted average
    milestone_weight = 0.4
    task_weight = 0.3
    subgoal_weight = 0.3

    milestone_progress = (
        completed_milestones / total_milestones
        if total_milestones > 0 else 0
    )
    task_progress = (
        completed_tasks / total_tasks
        if total_tasks > 0 else 0
    )
    subgoal_progress = (
        subgoal_progress_sum / total_subgoals
        if total_subgoals > 0 else 0
    )

    overall = (
        milestone_progress * milestone_weight +
        task_progress * task_weight +
        subgoal_progress * subgoal_weight
    )

    return GoalProgress(
        goal_id=goal_id,
        overall_progress=overall,
        milestone_progress={"completed": completed_milestones, "total": total_milestones},
        phase_progress={"current": current_phase_idx, "total": total_phases},
        task_progress={"completed": completed_tasks, "total": total_tasks},
        resource_utilization=await get_resource_utilization(goal_id),
        blockers=await get_active_blockers(goal_id),
        next_actions=await get_next_actions(goal_id),
        eta=await calculate_eta(goal_id),
        confidence=calculate_eta_confidence(data)
    )
```

### 5.2 Milestone That Advances Multiple Goals

```cypher
// Create a shared milestone that advances multiple goals
CREATE (m:Milestone {
  id: $milestone_id,
  title: $title,
  description: $description,
  target_date: $target_date,
  achieved: false,
  verification_criteria: $criteria,
  contributes_to_goals: [$goal_id_1, $goal_id_2, $goal_id_3]
})

// Link to all goals
MATCH (m:Milestone {id: $milestone_id})
MATCH (g:Goal)
WHERE g.id IN $goal_ids
CREATE (g)-[:HAS_MILESTONE {weight: 1.0 / size($goal_ids)}]->(m)

// When milestone achieved, update all goals
MATCH (m:Milestone {id: $milestone_id})
SET m.achieved = true, m.achieved_at = datetime()

MATCH (g:Goal)-[:HAS_MILESTONE]->(m:Milestone {id: $milestone_id})
WITH g, sum(m.weight) as progress_increment
SET g.progress = g.progress + progress_increment

// Log milestone achievement to all affected goals
MATCH (g:Goal)-[:HAS_MILESTONE]->(m:Milestone {id: $milestone_id})
CREATE (g)-[:ACHIEVED_MILESTONE {at: datetime()}]->(m)
```

### 5.3 Progress Dashboard Query

```cypher
// Get comprehensive progress for all active goals
MATCH (g:Goal {sender_hash: $sender_hash, status: "active"})

// Milestone completion
OPTIONAL MATCH (g)-[hmg:HAS_MILESTONE]->(m:Milestone)
WITH g, count(m) as total_milestones,
     sum(CASE WHEN m.achieved THEN 1 ELSE 0 END) as completed_milestones

// Task completion
OPTIONAL MATCH (g)-[:HAS_TASK]->(t:Task)
WITH g, total_milestones, completed_milestones,
     count(t) as total_tasks,
     sum(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) as completed_tasks

// Blocked status
OPTIONAL MATCH (g)<-[:BLOCKS]-(blocker:Goal {status: "active"})
WITH g, total_milestones, completed_milestones, total_tasks, completed_tasks,
     count(blocker) as blocking_count

RETURN g.id as goal_id,
       g.title as title,
       g.time_horizon as horizon,
       g.target_date as deadline,
       round(g.progress * 100) as progress_percent,
       completed_milestones || '/' || total_milestones as milestones,
       completed_tasks || '/' || total_tasks as tasks,
       CASE WHEN blocking_count > 0 THEN 'Yes' ELSE 'No' END as blocked,
       g.priority as priority
ORDER BY
  CASE g.priority
    WHEN 'urgent' THEN 1
    WHEN 'high' THEN 2
    WHEN 'normal' THEN 3
    WHEN 'low' THEN 4
  END,
  g.target_date ASC
```

### 5.4 Real-Time Progress Updates

```python
async def update_goal_progress_on_task_complete(task_id: str, result: dict):
    """
    Update goal progress when a task completes.

    This should be called whenever a task marked with HAS_TASK completes.
    """
    # Find all goals this task contributes to
    query = """
    MATCH (g:Goal)-[:HAS_TASK {required: true}]->(t:Task {id: $task_id})
    RETURN g, count(*) as goal_count
    """
    goals = await neo4j.run(query, {"task_id": task_id})

    # Update progress for each goal
    progress_increment = 1.0 / len(goals) if goals else 0

    for goal in goals:
        # Get total required task count
        task_count_query = """
        MATCH (g:Goal {id: $goal_id})-[:HAS_TASK {required: true}]->(t:Task)
        WITH g, count(t) as total_required
        MATCH (g)-[:HAS_TASK {required: true}]->(completed:Task)
        WHERE completed.status = 'completed'
        RETURN total_required, count(completed) as completed_count
        """
        counts = await neo4j.run(task_count_query, {"goal_id": goal["g"]["id"]})

        if counts:
            total = counts[0]["total_required"]
            completed = counts[0]["completed_count"] + 1  # Include this task

            new_progress = completed / total if total > 0 else 0

            # Update goal
            await neo4j.run("""
                MATCH (g:Goal {id: $goal_id})
                SET g.progress = $progress,
                    g.updated_at = datetime()
                RETURN g
            """, {"goal_id": goal["g"]["id"], "progress": new_progress})

            # Check for milestone achievement
            await check_milestone_achievement(goal["g"]["id"])

    # Check if strategy should advance
    await check_strategy_phase_advancement(task_id)


async def check_milestone_achievement(goal_id: str):
    """
    Check if any milestones for this goal are now achieved.
    """
    query = """
    MATCH (g:Goal {id: $goal_id})-[:HAS_MILESTONE]->(m:Milestone)
    WHERE NOT m.achieved

    // Get all tasks that contribute to this milestone
    OPTIONAL MATCH (t:Task)-[:CONTRIBUTES_TO]->(m)
    WITH m, count(t) as total_tasks
    OPTIONAL MATCH (completed:Task)-[:CONTRIBUTES_TO]->(m)
    WHERE completed.status = 'completed'

    WITH m, total_tasks, count(completed) as completed_count
    WHERE total_tasks > 0 AND completed_count >= total_tasks

    SET m.achieved = true,
        m.achieved_at = datetime()

    RETURN m.title as milestone_title
    """
    achieved = await neo4j.run(query, {"goal_id": goal_id})
    return [m["milestone_title"] for m in achieved]
```

---

## 6. User Interaction Patterns

### 6.1 Goal Proposal to User

```python
def format_goal_synthesis_proposal(
    synergistic_goals: List[GoalNode],
    strategy: StrategyProposal
) -> str:
    """
    Format a strategy proposal for user approval.
    """
    return f"""
I've analyzed your recent requests and found they're highly synergistic:

{''.join(f"• {g.title}\\n" for g in synergistic_goals)}

Rather than pursuing these separately, I recommend a unified strategy:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{strategy.title.upper()}

{strategy.description}

PHASES:
{format_phases(strategy.phases)}

EXPECTED OUTCOMES:
{''.join(f"✓ {outcome}\\n" for outcome in strategy.expected_outcomes)}

TRADEOFFS:
{''.join(f"• {tradeoff}\\n" for tradeoff in strategy.tradeoffs)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Estimated timeline: {strategy.estimated_duration_days} days

Would you like me to:
1. Proceed with this unified strategy
2. Keep goals separate and run them in parallel
3. Pursue one goal first, then the other (specify which)

Reply with 1, 2, or 3 (or ask me to explain more).
    """.strip()


def format_phases(phases: List[dict]) -> str:
    """Format phase list for display."""
    return "\\n".join(
        f"Phase {i+1}: {p['name']} ({p['duration_days']} days)\\n" +
        "\\n".join(f"  - {obj}" for obj in p['objectives'])
        for i, p in enumerate(phases)
    )
```

### 6.2 Conflict Resolution Prompt

```python
def format_conflict_resolution_prompt(conflict: GoalConflict) -> str:
    """
    Format a conflict for user resolution.
    """
    goal_a = get_goal_title(conflict.goal_a_id)
    goal_b = get_goal_title(conflict.goal_b_id)

    return f"""
⚠️ GOAL CONFLICT DETECTED

I've identified a conflict between your goals:

Goal A: {goal_a}
Goal B: {goal_b}

Issue: {conflict.description}
Severity: {conflict.severity.upper()}

OPTIONS:
{format_options(conflict.resolution_options)}

Which approach would you prefer? Reply with the option number or describe your preference.
    """.strip()


def format_options(options: List[dict]) -> str:
    """Format resolution options."""
    return "\\n".join(
        f"{i+1}. {opt['strategy']}: {opt['description']}"
        for i, opt in enumerate(options)
    )
```

### 6.3 Progress Report

```python
def format_goal_progress_report(progress: GoalProgress) -> str:
    """
    Format a multi-goal progress report for the user.
    """
    return f"""
📊 GOAL PROGRESS REPORT

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OVERALL: {round(progress.overall_progress * 100)}% complete

Milestones: {progress.milestone_progress['completed']}/{progress.milestone_progress['total']}
Tasks: {progress.task_progress['completed']}/{progress.task_progress['total']}

{'BLOCKED' if progress.blockers else 'ON TRACK'}
{format_blockers(progress.blockers)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NEXT ACTIONS:
{format_next_actions(progress.next_actions)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ETA: {progress.eta.strftime('%B %d')} ({confidence_label(progress.confidence)})
    """.strip()


def confidence_label(confidence: float) -> str:
    """Convert confidence to label."""
    if confidence >= 0.8:
        return "high confidence"
    elif confidence >= 0.5:
        return "moderate confidence"
    else:
        return "low confidence - may change"
```

---

## 7. Implementation Phases

### Phase 1: Schema Foundation (Week 1)

```cypher
// Migration script for goal nodes
CREATE CONSTRAINT goal_id_unique IF NOT EXISTS
  FOR (g:GoalNode) REQUIRE g.id IS UNIQUE;

CREATE INDEX goal_sender_status IF NOT EXISTS
  FOR (g:GoalNode) ON (g.sender_hash, g.status);

CREATE VECTOR INDEX goal_embedding IF NOT EXISTS
  FOR (g:GoalNode) ON g.embedding OPTIONS {
    indexConfig: {
      `vector.dimensions`: 384,
      `vector.similarity_function`: 'cosine'
    }
  };
```

### Phase 2: Goal Detection (Week 2)

- Implement `classify_goal_relationship()` in goal_analysis module
- Add clustering algorithm for synergistic goals
- Create pattern detection for common goal combinations

### Phase 3: Strategy Synthesis (Week 3)

- Implement strategy generation for each pattern type
- Create strategy storage and retrieval
- Build goal-to-strategy linking

### Phase 4: Conflict Resolution (Week 4)

- Implement conflict detection algorithm
- Create user prompt flows for resolution
- Add automatic conflict resolution where safe

### Phase 5: Progress Tracking (Week 5)

- Implement multi-dimensional progress calculation
- Create milestone system with multi-goal support
- Build progress dashboard queries

### Phase 6: User Experience (Week 6)

- Format synthesis proposals
- Create conflict resolution prompts
- Build progress reporting

---

## 8. API Endpoints

```python
# REST API for goal operations (extend existing OpenClaw gateway)

@app.post("/api/goals")
async def create_goal(request: GoalCreateRequest):
    """Create a new goal from user message."""
    goal = await goal_service.create_from_message(
        sender_hash=request.sender_hash,
        message=request.message
    )

    # Check for synergies with existing goals
    existing = await goal_service.get_active_goals(request.sender_hash)
    clusters = await cluster_synergistic_goals(existing + [goal], request.sender_hash)

    if len(clusters[0]) > 1:
        # Propose strategy
        strategy = await synthesize_strategy(clusters[0], {})
        return {
            "goal": goal,
            "synergy_detected": True,
            "strategy_proposal": strategy
        }

    return {"goal": goal, "synergy_detected": False}


@app.get("/api/goals/{sender_hash}")
async def get_goals(sender_hash: str):
    """Get all goals with progress."""
    goals = await goal_service.get_with_progress(sender_hash)
    return {
        "goals": goals,
        "summary": calculate_goal_summary(goals)
    }


@app.post("/api/goals/resolve-conflict")
async def resolve_conflict(request: ConflictResolutionRequest):
    """Resolve a conflict between goals."""
    resolution = await conflict_service.resolve(
        conflict_id=request.conflict_id,
        strategy=request.strategy,
        user_preference=request.preference
    )
    return resolution


@app.get("/api/goals/{goal_id}/progress")
async def get_goal_progress(goal_id: str):
    """Get detailed progress for a goal."""
    progress = await goal_service.calculate_progress(goal_id)
    return progress
```

---

## 9. Example Scenarios

### Scenario 1: Synergistic Goals

**User Messages:**
1. "Earn 1,000 USDC"
2. "Start a money-making community"

**Kublai Analysis:**
- Semantic similarity: 0.72 (high)
- Pattern detected: community_monetization
- Relationship: SYNERGISTIC

**Kublai Response:**
```
I notice these requests are highly synergistic. Instead of treating them
separately, here's a unified strategy:

COMMUNITY-POWERED INCOME

Build a community where earning is embedded in the value proposition.

Phase 1 (7 days): Research & Positioning
- Research existing communities
- Define community value prop
- Map monetization pathways

Phase 2 (14 days): MVP Launch
- Set up platform
- Create initial content
- Launch with founding members

Phase 3 (21 days): Monetization
- Implement premium tiers
- Launch offerings
- Track conversion

Outcomes:
- Active community (100+ members by day 30)
- First income by day 45
- Sustainable model by day 60

Tradeoffs:
- Slower initial earning vs. freelancing
- Requires consistent engagement

Proceed? (1/yes, 2/no, 3/explain)
```

### Scenario 2: Conflicting Goals

**User Messages:**
1. "Earn quick money this week"
2. "Build a sustainable business"

**Kublai Analysis:**
- Strategic conflict detected
- Time horizons: immediate vs. long-term
- Severity: medium

**Kublai Response:**
```
I see a strategic tension between these goals:

Quick Goal: Earn money this week - Fast results, short-term
Long-term Goal: Build business - Sustainable, compounding

Recommendation: Hybrid approach
- 80% focus on business (builds lasting value)
- 20% focus on quick wins (maintains momentum)

This avoids perpetual quick wins while ensuring you're not
building something that won't generate value for years.

Options:
1. Hybrid (80/20 split)
2. Quick wins only
3. Long-term only

Which do you prefer?
```

### Scenario 3: Independent Goals

**User Messages:**
1. "Buy groceries"
2. "Schedule dentist appointment"

**Kublai Analysis:**
- Semantic similarity: 0.08 (low)
- No temporal dependency
- No resource competition
- Relationship: INDEPENDENT

**Kublai Response:**
```
Working on 2 independent tasks:

1. Buy groceries - adding to shopping list
2. Schedule dentist - finding appointments

Both can be done in parallel. I'll handle them separately
and report back when each is complete.
```

---

## 10. Monitoring and Observability

```python
# Metrics to track for multi-goal orchestration

class GoalOrchestrationMetrics:
    """Track the health and effectiveness of goal orchestration."""

    async def record_goal_classification(self, relationship: str, confidence: float):
        """Track how goals are being classified."""
        metrics.increment("goal.classification", {
            "relationship_type": relationship,
            "confidence_range": confidence_to_range(confidence)
        })

    async def record_strategy_acceptance(self, strategy_id: str, accepted: bool):
        """Track whether users accept proposed strategies."""
        metrics.increment("strategy.proposal", {
            "accepted": accepted,
            "strategy_type": get_strategy_type(strategy_id)
        })

    async def record_conflict_resolution(self, conflict_id: str, resolution: str):
        """Track how conflicts are resolved."""
        metrics.increment("conflict.resolution", {
            "strategy": resolution
        })

    async def record_goal_completion(self, goal_id: str, duration_days: int):
        """Track goal completion rates and accuracy of estimates."""
        goal = await get_goal(goal_id)

        metrics.histogram("goal.duration_days", duration_days, {
            "time_horizon": goal.time_horizon
        })

        if goal.target_date:
            on_time = (datetime.now().date() <= goal.target_date)
            metrics.increment("goal.on_time_completion", {
                "on_time": on_time
            })
```

---

## Appendix A: Complete Schema Migration Script

```cypher
// Complete migration script for multi-goal orchestration
// Run this to add GoalNode and related structures to existing Neo4j instance

// ============================================================================
// NODE TYPES
// ============================================================================

// GoalNode constraint
CREATE CONSTRAINT goal_id_unique IF NOT EXISTS
  FOR (g:GoalNode) REQUIRE g.id IS UNIQUE;

// StrategyNode constraint
CREATE CONSTRAINT strategy_id_unique IF NOT EXISTS
  FOR (s:StrategyNode) REQUIRE s.id IS UNIQUE;

// Milestone constraint
CREATE CONSTRAINT milestone_id_unique IF NOT EXISTS
  FOR (m:Milestone) REQUIRE m.id IS UNIQUE;

// ============================================================================
// INDEXES
// ============================================================================

CREATE INDEX goal_sender_status IF NOT EXISTS
  FOR (g:GoalNode) ON (g.sender_hash, g.status);

CREATE VECTOR INDEX goal_embedding IF NOT EXISTS
  FOR (g:GoalNode) ON g.embedding OPTIONS {
    indexConfig: {
      `vector.dimensions`: 384,
      `vector.similarity_function`: 'cosine'
    }
  };

CREATE INDEX goal_target_date IF NOT EXISTS
  FOR (g:GoalNode) ON (g.target_date);

CREATE INDEX goal_time_horizon IF NOT EXISTS
  FOR (g:GoalNode) ON (g.time_horizon);

CREATE INDEX goal_progress IF NOT EXISTS
  FOR (g:GoalNode) ON (g.status, g.progress);

CREATE INDEX goal_parent IF NOT EXISTS
  FOR (g:GoalNode) ON (g.parent_goal_id);

CREATE INDEX strategy_status IF NOT EXISTS
  FOR (s:StrategyNode) ON (s.status, s.created_at);

// ============================================================================
// SAMPLE DATA (for testing)
// ============================================================================

// Example goal
CREATE (g1:GoalNode {
  id: "goal-test-001",
  sender_hash: "test_sender_hash",
  title: "Earn 1,000 USDC",
  description: "Generate 1,000 USDC through freelance or community work",
  embedding: [0.1, 0.2, ...],  // Truncated for display
  status: "active",
  progress: 0.0,
  time_horizon: "short",
  target_date: date() + duration({days: 30}),
  created_at: datetime(),
  priority: "high",
  estimated_cost: 0,
  required_agents: ["analyst", "writer"],
  current_phase: "research",
  phases_count: 3,
  milestone_count: 5,
  completed_milestones: 0,
  access_tier: "SENSITIVE"
});

// Example synergistic goal
CREATE (g2:GoalNode {
  id: "goal-test-002",
  sender_hash: "test_sender_hash",
  title: "Start money-making community",
  description: "Build a community that generates ongoing revenue",
  embedding: [0.15, 0.18, ...],  // Truncated for display
  status: "active",
  progress: 0.0,
  time_horizon: "medium",
  target_date: date() + duration({days: 90}),
  created_at: datetime(),
  priority: "high",
  estimated_cost: 500,
  required_agents: ["developer", "writer", "analyst"],
  current_phase: "planning",
  phases_count: 4,
  milestone_count: 8,
  completed_milestones: 0,
  access_tier: "SENSITIVE"
});

// Synergy relationship
CREATE (g1)-[:SYNERGIZES_WITH {
  strength: 0.85,
  detected_by: "semantic",
  merged_into: "strategy-test-001",
  merge_reason: "Both goals relate to community-based earning"
}]->(g2);

// Example strategy
CREATE (s1:StrategyNode {
  id: "strategy-test-001",
  title: "Community-Powered Income Strategy",
  description: "Build community as path to sustainable earning",
  created_by: "kublai",
  created_at: datetime(),
  component_goal_ids: ["goal-test-001", "goal-test-002"],
  phases: ["Research", "Launch", "Monetize"],
  current_phase: 0,
  estimated_duration_days: 42,
  status: "active",
  success_criteria: "100+ community members, first revenue by day 45",
  notes: "Slower initial earning but higher long-term value"
});

// Strategy achieves goals
MATCH (s:StrategyNode {id: "strategy-test-001"})
MATCH (g1:GoalNode {id: "goal-test-001"})
MATCH (g2:GoalNode {id: "goal-test-002"})
CREATE (s)-[:ACHIEVES]->(g1)
CREATE (s)-[:ACHIEVES]->(g2)
```

---

## Summary

This architecture extends the Task Dependency Engine with:

1. **Goal Relationship Detection** - Multi-dimensional analysis using semantic similarity, temporal constraints, and resource competition
2. **Goal Hierarchy Schema** - Neo4j extensions with GoalNode, StrategyNode, Milestone, and relationship types
3. **Synthesis Algorithm** - Clustering and strategy generation for synergistic goals with pattern-based proposals
4. **Conflict Resolution** - Detection and user-guided resolution for competing goals
5. **Progress Tracking** - Multi-dimensional metrics with milestones that advance multiple goals

The system enables Kublai to move beyond task-level orchestration to goal-level strategic thinking, providing users with coherent long-term plans while maintaining the flexibility to adapt to changing priorities.
