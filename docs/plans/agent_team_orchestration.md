# Agent Team Orchestration Design
## Integration with Kurultai v0.2 Capability Acquisition Pipeline

> **Status**: Design Document
> **Date**: 2026-02-05
> **Author**: Kurultai System Architecture
> **Prerequisites**: [`kurultai_0.2.md`](./kurultai_0.2.md), [`kurultai_0.1.md`](./kurultai_0.1.md)

---

## Executive Summary

This document designs the orchestration layer that enables **agent teams** to integrate with the Kurultai v0.2 capability acquisition pipeline and Task Dependency Engine. Instead of sequential delegation (Möngke → Temüjin → Jochi), each phase can spawn a **team of specialists** working in parallel, with intelligent coordination, failure recovery, and cost management.

### Key Innovation

Transform the linear pipeline into a **team-based parallel execution system**:

```
Traditional (Sequential)          Team-Based (Parallel)
─────────────────────            ─────────────────────
Möngke (research)                Research Team (Möngke + specialists)
    ↓                                  ↓
Temüjin (code)                   Implementation Team (Temüjin + reviewers)
    ↓                                  ↓
Jochi (validate)                 Validation Team (Jochi + test specialists)
    ↓                                  ↓
Registry                         Registry (aggregated results)
```

---

## Architecture Overview

### System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CAPABILITY ACQUISITION PIPELINE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   User Request: "Learn how to call phones"                                   │
│        │                                                                     │
│        ▼                                                                     │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │              CAPABILITY CLASSIFIER (Hybrid)                        │   │
│   │   Rule-based (fast) → Semantic → LLM fallback                      │   │
│   │   Output: Complexity score, Risk level, Team size recommendation   │   │
│   └──────────────────────┬──────────────────────────────────────────────┘   │
│                          │                                                   │
│                          ▼                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │              TEAM SPAWN DECISION ENGINE                            │   │
│   │                                                                      │
│   │   IF complexity > threshold AND risk != CRITICAL:                  │
│   │      → Spawn teams for each phase                                  │
│   │   ELSE:                                                            │
│   │      → Use individual agents (original pipeline)                   │
│   └──────────────────────┬──────────────────────────────────────────────┘   │
│                          │                                                   │
│          ┌───────────────┼───────────────┐                                   │
│          ▼               ▼               ▼                                   │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                         │
│   │  RESEARCH   │  │IMPLEMENTATION│  │ VALIDATION  │                         │
│   │    TEAM     │  │    TEAM      │  │    TEAM     │                         │
│   │  (Phase 1)  │  │  (Phase 2)   │  │  (Phase 3)  │                         │
│   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                         │
│          │                │                │                                 │
│          └───────────────┼────────────────┘                                 │
│                          ▼                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │              TOPOLOGICAL EXECUTOR (Modified)                       │   │
│   │                                                                      │
│   │   - Handles TeamTask nodes (not just individual tasks)             │
│   │   - Aggregates team results before passing to next phase           │
│   │   - Manages cross-team dependencies                                │
│   └──────────────────────┬──────────────────────────────────────────────┘   │
│                          │                                                   │
│                          ▼                                                   │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │              CAPABILITY REGISTRY (Neo4j)                           │   │
│   │   - Stores learned capability with team attribution                │
│   │   - Tracks which team members contributed                          │
│   │   - Cost attribution per team member                               │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Team Spawn Triggers

### 1.1 Complexity Threshold Analysis

```python
@dataclass
class ComplexityAssessment:
    """Assessment of capability learning complexity."""
    overall_score: float  # 0.0 - 1.0
    domain_complexity: float
    integration_complexity: float
    security_risk: str  # LOW, MEDIUM, HIGH, CRITICAL
    estimated_team_size: int
    recommended_approach: str  # "individual" | "small_team" | "full_team"


class TeamSpawnDecisionEngine:
    """
    Decides when to spawn teams vs use individual agents.
    """

    # Thresholds for team formation
    COMPLEXITY_THRESHOLD = 0.6  # Above this, consider team
    HIGH_COMPLEXITY_THRESHOLD = 0.8  # Above this, require team

    # Team size by complexity
    TEAM_SIZES = {
        (0.0, 0.6): 1,      # Individual agent
        (0.6, 0.8): 3,      # Small team (lead + 2 specialists)
        (0.8, 1.0): 5,      # Full team (lead + 4 specialists)
    }

    def assess_complexity(self, capability_request: dict) -> ComplexityAssessment:
        """
        Assess complexity of capability learning request.

        Factors:
        1. Domain novelty (has this domain been learned before?)
        2. API complexity (number of endpoints, auth methods)
        3. Integration surface (how many existing systems affected)
        4. Security risk level
        5. Estimated lines of code
        """
        scores = {
            'domain_novelty': self._score_domain_novelty(capability_request),
            'api_complexity': self._score_api_complexity(capability_request),
            'integration_surface': self._score_integration_surface(capability_request),
            'code_volume': self._estimate_code_volume(capability_request),
        }

        # Weighted average
        weights = {
            'domain_novelty': 0.25,
            'api_complexity': 0.30,
            'integration_surface': 0.25,
            'code_volume': 0.20,
        }

        overall = sum(scores[k] * weights[k] for k in scores)

        # Determine team size
        for (low, high), size in self.TEAM_SIZES.items():
            if low <= overall < high:
                team_size = size
                break
        else:
            team_size = 5

        # Determine approach
        if overall < self.COMPLEXITY_THRESHOLD:
            approach = "individual"
        elif overall < self.HIGH_COMPLEXITY_THRESHOLD:
            approach = "small_team"
        else:
            approach = "full_team"

        return ComplexityAssessment(
            overall_score=overall,
            domain_complexity=scores['domain_novelty'],
            integration_complexity=scores['integration_surface'],
            security_risk=capability_request.get('risk_level', 'MEDIUM'),
            estimated_team_size=team_size,
            recommended_approach=approach
        )

    def should_spawn_team(self, assessment: ComplexityAssessment) -> bool:
        """
        Determine if a team should be spawned.

        Rules:
        1. CRITICAL risk → Always individual (security review required)
        2. HIGH complexity → Always team (too much for one agent)
        3. MEDIUM complexity + available capacity → Team
        4. LOW complexity → Individual (faster, cheaper)
        """
        if assessment.security_risk == "CRITICAL":
            return False  # Security review requires individual accountability

        if assessment.overall_score >= self.HIGH_COMPLEXITY_THRESHOLD:
            return True  # Too complex for individual

        if assessment.overall_score >= self.COMPLEXITY_THRESHOLD:
            # Check available agent capacity
            return self._check_agent_capacity(assessment.estimated_team_size)

        return False

    def _check_agent_capacity(self, required_agents: int) -> bool:
        """Check if enough agents are available."""
        # Query Neo4j for available agents
        available = self._get_available_agent_count()
        return available >= required_agents
```

### 1.2 Metadata Indicating "Team-Worthy" Tasks

```python
TEAM_WORTHY_INDICATORS = {
    # Domain indicators
    "domains": {
        "payment_processing": 0.9,      # High complexity, needs security specialist
        "telephony": 0.8,               # Complex integration
        "machine_learning": 0.85,       # Needs data + model specialists
        "blockchain": 0.9,              # Security + integration complexity
        "authentication": 0.85,         # Security-critical
    },

    # Capability type indicators
    "capability_types": {
        "multi_api_integration": 0.8,   # Multiple APIs to integrate
        "real_time_processing": 0.75,   # Performance considerations
        "user_facing_tool": 0.7,        # UX + backend needed
        "data_pipeline": 0.75,          # ETL + validation needed
        "ml_inference": 0.85,           # Model + serving needed
    },

    # Request metadata
    "request_features": {
        "has_multiple_endpoints": 0.3,
        "requires_oauth": 0.2,
        "has_webhook_handling": 0.25,
        "requires_rate_limiting": 0.15,
        "has_file_processing": 0.2,
        "requires_caching": 0.15,
    }
}
```

---

## 2. Team Lifecycle Integration

### 2.1 Team Task Node Extension

```python
@dataclass
class TeamTaskNode(BaseNode):
    """
    A task that requires a team of agents to complete.

    Extends the base TaskNode with team-specific metadata
    for coordination and result aggregation.
    """
    task_type: str = "team_task"

    # Team composition
    team_lead: Optional[str] = None  # Agent ID of team lead
    team_members: List[str] = field(default_factory=list)  # Specialist agent IDs
    required_specialties: List[str] = field(default_factory=list)

    # Sub-task management
    sub_tasks: List[str] = field(default_factory=list)  # Task IDs
    sub_task_results: Dict[str, Any] = field(default_factory=dict)

    # Aggregation strategy
    aggregation_strategy: str = "merge"  # merge | vote | consensus | hierarchical

    # Team progress tracking
    member_progress: Dict[str, float] = field(default_factory=dict)
    member_status: Dict[str, NodeStatus] = field(default_factory=dict)

    # Cost tracking per member
    member_costs: Dict[str, float] = field(default_factory=dict)
    team_budget: float = 0.0

    def get_overall_progress(self) -> float:
        """Calculate overall team progress."""
        if not self.member_progress:
            return 0.0
        return sum(self.member_progress.values()) / len(self.member_progress)

    def is_team_complete(self) -> bool:
        """Check if all team members have completed."""
        return all(
            status in {NodeStatus.COMPLETED, NodeStatus.FAILED, NodeStatus.SKIPPED}
            for status in self.member_status.values()
        )

    def get_successful_members(self) -> List[str]:
        """Get list of members who completed successfully."""
        return [
            member for member, status in self.member_status.items()
            if status == NodeStatus.COMPLETED
        ]

    def aggregate_results(self) -> Dict[str, Any]:
        """
        Aggregate results from all team members based on strategy.
        """
        if self.aggregation_strategy == "merge":
            return self._merge_results()
        elif self.aggregation_strategy == "vote":
            return self._vote_results()
        elif self.aggregation_strategy == "consensus":
            return self._consensus_results()
        elif self.aggregation_strategy == "hierarchical":
            return self._hierarchical_results()
        else:
            return self._merge_results()

    def _merge_results(self) -> Dict[str, Any]:
        """Merge results from all members (default strategy)."""
        merged = {
            "team_lead": self.team_lead,
            "members": self.get_successful_members(),
            "contributions": self.sub_task_results,
            "aggregated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Merge based on task type
        if self.task_type == "research":
            merged["findings"] = self._merge_research_findings()
        elif self.task_type == "implementation":
            merged["code"] = self._merge_code_contributions()
        elif self.task_type == "validation":
            merged["validation_report"] = self._merge_validation_results()

        return merged

    def _merge_research_findings(self) -> Dict[str, Any]:
        """Merge research findings from multiple researchers."""
        all_sources = []
        all_findings = []

        for member, result in self.sub_task_results.items():
            if isinstance(result, dict):
                all_sources.extend(result.get("sources", []))
                all_findings.extend(result.get("findings", []))

        # Deduplicate sources
        unique_sources = {s["url"]: s for s in all_sources}.values()

        return {
            "sources": list(unique_sources),
            "findings": all_findings,
            "researcher_count": len(self.get_successful_members()),
        }

    def _merge_code_contributions(self) -> Dict[str, Any]:
        """Merge code contributions from multiple developers."""
        # Code merging requires careful conflict resolution
        # This is handled by the team lead
        return {
            "modules": self.sub_task_results,
            "integration_status": "pending_lead_review",
        }

    def _merge_validation_results(self) -> Dict[str, Any]:
        """Merge validation results from multiple validators."""
        all_issues = []
        all_scores = []

        for member, result in self.sub_task_results.items():
            if isinstance(result, dict):
                all_issues.extend(result.get("issues", []))
                all_scores.append(result.get("mastery_score", 0.0))

        return {
            "issues": all_issues,
            "average_mastery_score": sum(all_scores) / len(all_scores) if all_scores else 0.0,
            "min_mastery_score": min(all_scores) if all_scores else 0.0,
            "validation_passed": all(s >= 0.85 for s in all_scores),
        }
```

### 2.2 Extended Topological Executor for Teams

```python
class TeamAwareTopologicalExecutor(TopologicalExecutor):
    """
    Extended executor that handles both individual tasks and team tasks.
    """

    def __init__(
        self,
        executor: Callable[[BaseNode], Any] | None = None,
        team_coordinator: TeamCoordinator | None = None,
        max_retries: int = 3
    ):
        super().__init__(executor, max_retries)
        self.team_coordinator = team_coordinator or TeamCoordinator()

    async def get_ready_tasks(
        self,
        sender_hash: str,
        limit: int = 50
    ) -> List[BaseNode]:
        """
        Find tasks ready for execution, including team tasks.
        """
        # Get regular ready tasks
        ready_tasks = await super().get_ready_tasks(sender_hash, limit)

        # Check for team tasks that need member assignment
        team_tasks = [
            task for task in ready_tasks
            if isinstance(task, TeamTaskNode) and not task.team_members
        ]

        # Assign teams to unassigned team tasks
        for team_task in team_tasks:
            await self.team_coordinator.assign_team(team_task)

        return ready_tasks

    async def execute_ready_set(
        self,
        sender_hash: str,
        max_execution_limit: int = 50
    ) -> dict:
        """
        Execute ready tasks, handling team tasks specially.
        """
        ready = await self.get_ready_tasks(sender_hash, limit=max_execution_limit)

        # Separate individual and team tasks
        individual_tasks = [t for t in ready if not isinstance(t, TeamTaskNode)]
        team_tasks = [t for t in ready if isinstance(t, TeamTaskNode)]

        results = {
            "executed_count": 0,
            "error_count": 0,
            "executed": [],
            "errors": [],
            "team_results": [],
        }

        # Execute individual tasks normally
        if individual_tasks:
            individual_results = await self._execute_individual_tasks(
                individual_tasks
            )
            results.update(individual_results)

        # Execute team tasks with coordination
        for team_task in team_tasks:
            try:
                team_result = await self._execute_team_task(team_task)
                results["team_results"].append(team_result)
                results["executed_count"] += 1
            except Exception as e:
                results["errors"].append({
                    "task_id": team_task.id,
                    "error": str(e),
                    "type": "team_execution_failed"
                })
                results["error_count"] += 1

        return results

    async def _execute_team_task(self, team_task: TeamTaskNode) -> Dict[str, Any]:
        """
        Execute a team task by coordinating all team members.
        """
        logger.info(f"Executing team task {team_task.id} with {len(team_task.team_members)} members")

        # Spawn sub-tasks for each team member
        sub_task_futures = []
        for member_id in team_task.team_members:
            future = self._spawn_member_task(team_task, member_id)
            sub_task_futures.append(future)

        # Wait for all members to complete (with timeout)
        timeout_seconds = 600  # 10 minutes per team task
        try:
            member_results = await asyncio.wait_for(
                asyncio.gather(*sub_task_futures, return_exceptions=True),
                timeout=timeout_seconds
            )
        except asyncio.TimeoutError:
            logger.error(f"Team task {team_task.id} timed out")
            return await self._handle_team_timeout(team_task)

        # Process results
        for member_id, result in zip(team_task.team_members, member_results):
            if isinstance(result, Exception):
                team_task.member_status[member_id] = NodeStatus.FAILED
                team_task.sub_task_results[member_id] = {"error": str(result)}
            else:
                team_task.member_status[member_id] = NodeStatus.COMPLETED
                team_task.sub_task_results[member_id] = result

        # Check if team lead needs to do integration
        if team_task.team_lead and team_task.aggregation_strategy == "hierarchical":
            integration_result = await self._execute_lead_integration(team_task)
            team_task.sub_task_results["lead_integration"] = integration_result

        # Aggregate final results
        final_result = team_task.aggregate_results()

        # Mark team task complete
        team_task.mark_status(NodeStatus.COMPLETED)
        team_task.result = final_result

        return {
            "task_id": team_task.id,
            "team_size": len(team_task.team_members),
            "successful_members": len(team_task.get_successful_members()),
            "result": final_result,
        }

    async def _spawn_member_task(
        self,
        team_task: TeamTaskNode,
        member_id: str
    ) -> Any:
        """
        Spawn a sub-task for a team member.
        """
        # Create sub-task context
        sub_task_context = {
            "parent_task_id": team_task.id,
            "team_role": self._get_team_role(team_task, member_id),
            "specialty": self._get_member_specialty(member_id),
            "aggregation_strategy": team_task.aggregation_strategy,
        }

        # Delegate to agent via agentToAgent
        return await self.team_coordinator.delegate_to_member(
            team_task=team_task,
            member_id=member_id,
            context=sub_task_context
        )

    async def _execute_lead_integration(
        self,
        team_task: TeamTaskNode
    ) -> Dict[str, Any]:
        """
        Have team lead integrate member contributions.
        """
        lead_id = team_task.team_lead

        integration_context = {
            "parent_task_id": team_task.id,
            "team_role": "lead_integrator",
            "member_results": team_task.sub_task_results,
            "integration_instructions": self._get_integration_instructions(team_task),
        }

        return await self.team_coordinator.delegate_to_member(
            team_task=team_task,
            member_id=lead_id,
            context=integration_context
        )
```

---

## 3. Coordination Patterns

### 3.1 Team Coordinator

```python
class TeamCoordinator:
    """
    Coordinates team formation, task distribution, and progress reporting.
    """

    def __init__(
        self,
        neo4j_client: OperationalMemory,
        delegation_protocol: DelegationProtocol,
        cost_enforcer: CostEnforcer
    ):
        self.neo4j = neo4j_client
        self.delegation = delegation_protocol
        self.cost_enforcer = cost_enforcer
        self.active_teams: Dict[str, TeamTaskNode] = {}

    async def assign_team(self, team_task: TeamTaskNode) -> bool:
        """
        Assign team members to a team task.

        1. Select team lead based on task type
        2. Select specialists based on required_specialties
        3. Pre-authorize budget for entire team
        4. Store team assignment in Neo4j
        """
        # Select team lead
        team_task.team_lead = self._select_team_lead(team_task)

        # Select team members
        team_task.team_members = self._select_team_members(
            team_task.required_specialties,
            exclude=[team_task.team_lead]
        )

        # Pre-authorize team budget
        team_budget = self._calculate_team_budget(team_task)
        authorized = await self.cost_enforcer.authorize_team_spending(
            team_task_id=team_task.id,
            team_size=len(team_task.team_members) + 1,  # +1 for lead
            estimated_cost=team_budget
        )

        if not authorized:
            logger.error(f"Budget authorization failed for team task {team_task.id}")
            return False

        team_task.team_budget = team_budget

        # Store in Neo4j
        await self._persist_team_assignment(team_task)

        self.active_teams[team_task.id] = team_task

        logger.info(
            f"Assigned team for task {team_task.id}: "
            f"lead={team_task.team_lead}, "
            f"members={team_task.team_members}"
        )

        return True

    def _select_team_lead(self, team_task: TeamTaskNode) -> str:
        """
        Select appropriate team lead based on task type.

        Research tasks → Möngke
        Implementation tasks → Temüjin
        Validation tasks → Jochi
        """
        lead_mapping = {
            "research": "researcher",
            "implementation": "developer",
            "validation": "analyst",
        }

        default_lead = "main"  # Kublai as fallback
        return lead_mapping.get(team_task.task_type, default_lead)

    def _select_team_members(
        self,
        required_specialties: List[str],
        exclude: List[str]
    ) -> List[str]:
        """
        Select agents with required specialties.

        Specialty → Agent mapping:
        - "api_research" → researcher
        - "security_audit" → developer (security focus)
        - "code_review" → developer
        - "performance_analysis" → analyst
        - "test_design" → analyst
        """
        specialty_agents = {
            "api_research": ["researcher"],
            "documentation_extraction": ["researcher", "writer"],
            "pattern_analysis": ["analyst"],
            "security_audit": ["developer"],
            "code_generation": ["developer"],
            "code_review": ["developer"],
            "test_design": ["analyst"],
            "performance_analysis": ["analyst"],
            "integration_testing": ["developer", "analyst"],
        }

        selected = []
        for specialty in required_specialties:
            candidates = specialty_agents.get(specialty, [])
            for candidate in candidates:
                if candidate not in exclude and candidate not in selected:
                    selected.append(candidate)
                    break

        return selected

    async def delegate_to_member(
        self,
        team_task: TeamTaskNode,
        member_id: str,
        context: Dict[str, Any]
    ) -> Any:
        """
        Delegate a sub-task to a team member.
        """
        # Create member-specific task description
        task_description = self._create_member_task_description(
            team_task, member_id, context
        )

        # Check cost budget before delegation
        member_budget = team_task.team_budget / (len(team_task.team_members) + 1)
        can_spend = await self.cost_enforcer.check_member_budget(
            team_task_id=team_task.id,
            member_id=member_id,
            amount=member_budget
        )

        if not can_spend:
            raise BudgetExceededError(
                f"Budget exceeded for team {team_task.id}, member {member_id}"
            )

        # Delegate via agentToAgent
        result = self.delegation.delegate_task(
            task_description=task_description,
            context={
                **context,
                "sender_hash": team_task.metadata.get("sender_hash"),
                "team_task_id": team_task.id,
                "member_id": member_id,
                "budget_limit": member_budget,
            },
            suggested_agent=member_id,
            priority="normal",
            delegated_by="main"
        )

        # Track cost
        actual_cost = result.get("cost", 0.0)
        team_task.member_costs[member_id] = actual_cost

        return result

    async def report_team_progress(
        self,
        team_task_id: str,
        kublai_gateway: str
    ) -> Dict[str, Any]:
        """
        Report team progress to Kublai.
        """
        team_task = self.active_teams.get(team_task_id)
        if not team_task:
            return {"error": "Team task not found"}

        progress_report = {
            "team_task_id": team_task_id,
            "task_type": team_task.task_type,
            "overall_progress": team_task.get_overall_progress(),
            "member_status": {
                member: {
                    "status": status.name,
                    "progress": team_task.member_progress.get(member, 0.0),
                    "cost": team_task.member_costs.get(member, 0.0),
                }
                for member, status in team_task.member_status.items()
            },
            "budget_remaining": team_task.team_budget - sum(team_task.member_costs.values()),
            "estimated_completion": self._estimate_completion(team_task),
        }

        # Send to Kublai via gateway
        await self._send_progress_to_kublai(progress_report, kublai_gateway)

        return progress_report

    def _estimate_completion(self, team_task: TeamTaskNode) -> Optional[datetime]:
        """Estimate completion time based on progress and remaining work."""
        if team_task.is_team_complete():
            return datetime.now(timezone.utc)

        progress = team_task.get_overall_progress()
        if progress == 0:
            return None

        # Assume linear progress (simplified)
        elapsed = (datetime.now(timezone.utc) - team_task.created_at).total_seconds()
        estimated_total = elapsed / progress
        remaining = estimated_total - elapsed

        return datetime.now(timezone.utc) + timedelta(seconds=remaining)
```

### 3.2 Cross-Team Dependency Management

```python
class CrossTeamDependencyManager:
    """
    Manages dependencies between teams/phases.

    Prevents circular dependencies and ensures proper sequencing.
    """

    def __init__(self, neo4j_client: OperationalMemory):
        self.neo4j = neo4j_client

    async def create_phase_dependency(
        self,
        from_phase: str,  # e.g., "research_team"
        to_phase: str,    # e.g., "implementation_team"
        dependency_type: str = "feeds_into"
    ) -> bool:
        """
        Create a dependency between phases.

        Valid phase transitions:
        - research_team → implementation_team
        - implementation_team → validation_team
        - validation_team → registry
        """
        # Validate no circular dependency
        if await self._would_create_cycle(from_phase, to_phase):
            raise CycleDetectedError(
                f"Cannot create dependency: {from_phase} → {to_phase} would create cycle"
            )

        # Create dependency in Neo4j
        query = """
        MATCH (from:Phase {name: $from_phase}), (to:Phase {name: $to_phase})
        CREATE (from)-[:PHASE_DEPENDS_ON {
            type: $dep_type,
            created_at: datetime()
        }]->(to)
        RETURN id(r) as relationship_id
        """

        result = await self.neo4j.run(query, {
            "from_phase": from_phase,
            "to_phase": to_phase,
            "dep_type": dependency_type
        })

        return len(result) > 0

    async def _would_create_cycle(self, from_phase: str, to_phase: str) -> bool:
        """Check if adding this dependency would create a cycle."""
        query = """
        MATCH path = (to:Phase {name: $to_phase})-[:PHASE_DEPENDS_ON*]->(from:Phase {name: $from_phase})
        RETURN count(path) > 0 as has_cycle
        """

        result = await self.neo4j.run(query, {
            "from_phase": from_phase,
            "to_phase": to_phase
        })

        return result[0]["has_cycle"] if result else False

    async def get_ready_phases(self) -> List[str]:
        """
        Get phases that are ready to execute (all dependencies met).
        """
        query = """
        MATCH (p:Phase)
        WHERE NOT EXISTS {
            MATCH (p)-[:PHASE_DEPENDS_ON]->(dep:Phase)
            WHERE dep.status != "completed"
        }
        AND p.status = "pending"
        RETURN p.name as phase_name
        """

        result = await self.neo4j.run(query)
        return [r["phase_name"] for r in result]

    async def propagate_results(
        self,
        completed_phase: str,
        results: Dict[str, Any]
    ) -> List[str]:
        """
        Propagate results from completed phase to waiting phases.

        Returns list of phases that are now ready.
        """
        # Store results
        await self._store_phase_results(completed_phase, results)

        # Mark phase complete
        await self._mark_phase_complete(completed_phase)

        # Check which phases are now ready
        ready_phases = await self.get_ready_phases()

        return ready_phases

    async def _store_phase_results(
        self,
        phase: str,
        results: Dict[str, Any]
    ) -> None:
        """Store phase results in Neo4j."""
        query = """
        MATCH (p:Phase {name: $phase})
        SET p.results = $results,
            p.completed_at = datetime(),
            p.status = "completed"
        """

        await self.neo4j.run(query, {
            "phase": phase,
            "results": json.dumps(results)
        })
```

---

## 4. Failure Recovery Strategies

### 4.1 Team Lead Failure Recovery

```python
class TeamFailureRecovery:
    """
    Handles failures within teams.
    """

    def __init__(
        self,
        team_coordinator: TeamCoordinator,
        neo4j_client: OperationalMemory
    ):
        self.coordinator = team_coordinator
        self.neo4j = neo4j_client

    async def handle_team_lead_failure(
        self,
        team_task: TeamTaskNode,
        failure_reason: str
    ) -> Dict[str, Any]:
        """
        Handle failure of team lead.

        Strategy:
        1. Promote most senior member to lead
        2. Reassign integration work
        3. Notify Kublai
        """
        logger.error(f"Team lead {team_task.team_lead} failed for task {team_task.id}")

        # Select new lead from remaining members
        new_lead = self._select_new_lead(team_task)

        if not new_lead:
            # No available members - escalate to Kublai
            return await self._escalate_to_kublai(team_task, failure_reason)

        # Promote new lead
        old_lead = team_task.team_lead
        team_task.team_lead = new_lead

        # Remove old lead from members if present
        if old_lead in team_task.team_members:
            team_task.team_members.remove(old_lead)

        # Reassign integration work
        await self._reassign_integration_work(team_task, new_lead)

        # Update Neo4j
        await self._update_lead_in_neo4j(team_task.id, new_lead, old_lead)

        return {
            "recovery_action": "lead_reassigned",
            "old_lead": old_lead,
            "new_lead": new_lead,
            "team_task_id": team_task.id,
        }

    async def handle_member_failure(
        self,
        team_task: TeamTaskNode,
        failed_member: str,
        failure_reason: str
    ) -> Dict[str, Any]:
        """
        Handle failure of a team member (not lead).

        Strategy:
        1. Check if work can be redistributed
        2. If critical specialty lost, find replacement
        3. If non-critical, continue with reduced team
        """
        logger.warning(f"Team member {failed_member} failed for task {team_task.id}")

        # Mark member as failed
        team_task.member_status[failed_member] = NodeStatus.FAILED

        # Check if specialty is critical
        specialty = self._get_member_specialty(failed_member)
        is_critical = self._is_specialty_critical(team_task, specialty)

        if is_critical:
            # Try to find replacement
            replacement = self._find_replacement_member(team_task, specialty)

            if replacement:
                team_task.team_members.remove(failed_member)
                team_task.team_members.append(replacement)

                # Delegate to replacement
                await self.coordinator.delegate_to_member(
                    team_task=team_task,
                    member_id=replacement,
                    context={"is_replacement": True, "original_member": failed_member}
                )

                return {
                    "recovery_action": "member_replaced",
                    "failed_member": failed_member,
                    "replacement": replacement,
                }
            else:
                # No replacement available - escalate
                return await self._escalate_to_kublai(team_task, failure_reason)
        else:
            # Non-critical member - continue with warning
            return {
                "recovery_action": "member_skipped",
                "failed_member": failed_member,
                "impact": "reduced_team_capacity",
            }

    async def handle_hung_team(
        self,
        team_task: TeamTaskNode,
        timeout_seconds: int = 600
    ) -> Dict[str, Any]:
        """
        Handle a team that appears hung (no progress).

        Strategy:
        1. Check individual member status
        2. Cancel hung members
        3. Attempt recovery with partial results
        """
        logger.error(f"Team {team_task.id} appears hung")

        hung_members = []
        for member, status in team_task.member_status.items():
            if status == NodeStatus.IN_PROGRESS:
                # Check last progress update
                last_update = team_task.member_progress.get(member, 0)
                if last_update == 0:  # No progress reported
                    hung_members.append(member)

        # Cancel hung members
        for member in hung_members:
            await self._cancel_member_task(team_task, member)
            team_task.member_status[member] = NodeStatus.CANCELLED

        # Check if we have enough results to proceed
        successful = team_task.get_successful_members()

        if len(successful) >= len(team_task.team_members) / 2:
            # Proceed with partial results
            return {
                "recovery_action": "partial_completion",
                "successful_members": successful,
                "cancelled_members": hung_members,
                "result_quality": "degraded",
            }
        else:
            # Not enough results - escalate
            return await self._escalate_to_kublai(
                team_task,
                f"Team hung, only {len(successful)}/{len(team_task.team_members)} completed"
            )

    async def graceful_degradation_to_individual(
        self,
        team_task: TeamTaskNode
    ) -> DelegationResult:
        """
        Fall back to individual agent execution.

        Used when:
        - Team formation fails
        - Budget constraints
        - Too many team failures
        """
        logger.info(f"Falling back to individual execution for task {team_task.id}")

        # Cancel all team member tasks
        for member in team_task.team_members:
            await self._cancel_member_task(team_task, member)

        # Delegate to team lead as individual
        lead = team_task.team_lead or "main"

        result = self.coordinator.delegation.delegate_task(
            task_description=team_task.description,
            context={
                "original_team_task_id": team_task.id,
                "degraded_from_team": True,
                "sender_hash": team_task.metadata.get("sender_hash"),
            },
            suggested_agent=lead,
            priority="high",  # Elevate priority due to failure
            delegated_by="main"
        )

        # Mark team task as degraded
        team_task.metadata["degraded_to_individual"] = True
        team_task.metadata["individual_task_id"] = result.task_id

        return result

    def _select_new_lead(self, team_task: TeamTaskNode) -> Optional[str]:
        """Select new lead from remaining members."""
        available = [
            m for m in team_task.team_members
            if team_task.member_status.get(m) != NodeStatus.FAILED
        ]

        if not available:
            return None

        # Prefer members with lead experience
        # For now, just take first available
        return available[0]

    async def _escalate_to_kublai(
        self,
        team_task: TeamTaskNode,
        reason: str
    ) -> Dict[str, Any]:
        """Escalate failure to Kublai for human decision."""
        escalation = {
            "type": "team_failure_escalation",
            "team_task_id": team_task.id,
            "task_type": team_task.task_type,
            "reason": reason,
            "team_composition": {
                "lead": team_task.team_lead,
                "members": team_task.team_members,
                "status": {m: s.name for m, s in team_task.member_status.items()},
            },
            "costs_incurred": sum(team_task.member_costs.values()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Store escalation in Neo4j
        await self._store_escalation(escalation)

        # Notify Kublai (via gateway)
        await self._notify_kublai(escalation)

        return {
            "recovery_action": "escalated_to_kublai",
            "escalation_id": escalation.get("id"),
        }
```

### 4.2 Circuit Breaker for Team Operations

```python
class TeamCircuitBreaker:
    """
    Circuit breaker pattern for team operations.

    Prevents cascading failures by stopping team formation
    when failure rate exceeds threshold.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 300,  # 5 minutes
        half_open_max_calls: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self.state = "closed"  # closed, open, half_open
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_calls = 0

    def can_execute(self) -> bool:
        """Check if team operation can proceed."""
        if self.state == "closed":
            return True

        if self.state == "open":
            if self._should_attempt_reset():
                self.state = "half_open"
                self.half_open_calls = 0
                return True
            return False

        if self.state == "half_open":
            if self.half_open_calls < self.half_open_max_calls:
                self.half_open_calls += 1
                return True
            return False

        return True

    def record_success(self) -> None:
        """Record successful team operation."""
        if self.state == "half_open":
            self.state = "closed"
            self.failure_count = 0
            self.half_open_calls = 0
        else:
            self.failure_count = max(0, self.failure_count - 1)

    def record_failure(self) -> None:
        """Record failed team operation."""
        self.failure_count += 1
        self.last_failure_time = datetime.now(timezone.utc)

        if self.state == "half_open":
            self.state = "open"
        elif self.failure_count >= self.failure_threshold:
            self.state = "open"

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if not self.last_failure_time:
            return True

        elapsed = (datetime.now(timezone.utc) - self.last_failure_time).total_seconds()
        return elapsed >= self.recovery_timeout
```

---

## 5. Cost Tracking Across Teams

### 5.1 Team Cost Enforcer

```python
@dataclass
class TeamBudgetAllocation:
    """Budget allocation for a team."""
    team_task_id: str
    total_budget: float
    lead_allocation: float
    member_allocation: float  # Per member
    contingency: float  # For replacements/overruns


class TeamCostEnforcer:
    """
    Enforces budget limits across team operations.

    Tracks costs per team, per member, and provides
    pre-authorization for team operations.
    """

    def __init__(self, neo4j_client: OperationalMemory):
        self.neo4j = neo4j_client
        self.active_budgets: Dict[str, TeamBudgetAllocation] = {}

    async def authorize_team_spending(
        self,
        team_task_id: str,
        team_size: int,
        estimated_cost: float
    ) -> bool:
        """
        Pre-authorize spending for a team operation.

        Uses atomic Neo4j transaction to reserve budget.
        """
        # Calculate allocations
        lead_allocation = estimated_cost * 0.4  # Lead gets 40%
        member_allocation = estimated_cost * 0.5 / max(team_size - 1, 1)  # Members split 50%
        contingency = estimated_cost * 0.1  # 10% contingency

        total_required = lead_allocation + (member_allocation * (team_size - 1)) + contingency

        # Atomic budget reservation
        query = """
        MATCH (b:Budget {category: 'capability_learning'})
        WHERE b.remaining >= $total_required
        SET b.remaining = b.remaining - $total_required,
            b.reserved = b.reserved + $total_required
        RETURN b.remaining as new_remaining
        """

        result = await self.neo4j.run(query, {"total_required": total_required})

        if not result:
            logger.error(f"Budget authorization failed for team {team_task_id}")
            return False

        # Store allocation
        allocation = TeamBudgetAllocation(
            team_task_id=team_task_id,
            total_budget=total_required,
            lead_allocation=lead_allocation,
            member_allocation=member_allocation,
            contingency=contingency
        )
        self.active_budgets[team_task_id] = allocation

        logger.info(
            f"Authorized budget for team {team_task_id}: "
            f"${total_required:.2f} (lead: ${lead_allocation:.2f}, "
            f"per_member: ${member_allocation:.2f})"
        )

        return True

    async def check_member_budget(
        self,
        team_task_id: str,
        member_id: str,
        amount: float
    ) -> bool:
        """
        Check if member has sufficient budget remaining.
        """
        allocation = self.active_budgets.get(team_task_id)
        if not allocation:
            return False

        # Query actual spent
        query = """
        MATCH (t:TeamTask {id: $team_task_id})-[r:HAS_MEMBER_COST]->(m:Member {id: $member_id})
        RETURN sum(r.cost) as spent
        """

        result = await self.neo4j.run(query, {
            "team_task_id": team_task_id,
            "member_id": member_id
        })

        spent = result[0]["spent"] if result else 0.0

        # Determine member's allocation
        if member_id == "team_lead":  # Would need actual lead ID
            member_budget = allocation.lead_allocation
        else:
            member_budget = allocation.member_allocation

        remaining = member_budget - spent

        return remaining >= amount

    async def record_member_cost(
        self,
        team_task_id: str,
        member_id: str,
        cost: float,
        operation: str
    ) -> bool:
        """
        Record cost incurred by a team member.
        """
        query = """
        MATCH (t:TeamTask {id: $team_task_id})
        MERGE (m:Member {id: $member_id})
        CREATE (t)-[r:HAS_MEMBER_COST {
            cost: $cost,
            operation: $operation,
            timestamp: datetime()
        }]->(m)
        RETURN r
        """

        try:
            await self.neo4j.run(query, {
                "team_task_id": team_task_id,
                "member_id": member_id,
                "cost": cost,
                "operation": operation
            })

            # Update active tracking
            allocation = self.active_budgets.get(team_task_id)
            if allocation:
                spent_so_far = allocation.total_budget - allocation.contingency
                # Could update real-time tracking here

            return True
        except Exception as e:
            logger.error(f"Failed to record member cost: {e}")
            return False

    async def release_unused_budget(self, team_task_id: str) -> float:
        """
        Release unused budget back to pool when team completes.
        """
        allocation = self.active_budgets.pop(team_task_id, None)
        if not allocation:
            return 0.0

        # Calculate actual spent
        query = """
        MATCH (t:TeamTask {id: $team_task_id})-[r:HAS_MEMBER_COST]->()
        RETURN sum(r.cost) as total_spent
        """

        result = await self.neo4j.run(query, {"team_task_id": team_task_id})
        total_spent = result[0]["total_spent"] if result else 0.0

        unused = allocation.total_budget - total_spent

        if unused > 0:
            # Return to budget pool
            release_query = """
            MATCH (b:Budget {category: 'capability_learning'})
            SET b.remaining = b.remaining + $unused,
                b.reserved = b.reserved - $unused
            RETURN b.remaining
            """

            await self.neo4j.run(release_query, {"unused": unused})

            logger.info(
                f"Released unused budget for team {team_task_id}: ${unused:.2f}"
            )

        return unused

    async def get_team_cost_report(self, team_task_id: str) -> Dict[str, Any]:
        """
        Generate cost report for a team operation.
        """
        query = """
        MATCH (t:TeamTask {id: $team_task_id})-[r:HAS_MEMBER_COST]->(m)
        RETURN m.id as member_id,
               sum(r.cost) as total_cost,
               count(r) as operation_count,
               collect(distinct r.operation) as operations
        """

        results = await self.neo4j.run(query, {"team_task_id": team_task_id})

        allocation = self.active_budgets.get(team_task_id)

        return {
            "team_task_id": team_task_id,
            "allocated_budget": allocation.total_budget if allocation else 0.0,
            "member_costs": [
                {
                    "member_id": r["member_id"],
                    "total_cost": r["total_cost"],
                    "operation_count": r["operation_count"],
                    "operations": r["operations"],
                }
                for r in results
            ],
            "total_spent": sum(r["total_cost"] for r in results),
            "variance": (allocation.total_budget if allocation else 0.0) -
                        sum(r["total_cost"] for r in results),
        }
```

---

## 6. Pseudocode for Key Orchestration Functions

### 6.1 Main Orchestration Flow

```python
async def orchestrate_capability_acquisition(
    user_request: str,
    sender_hash: str,
    kublai_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Main orchestration function for capability acquisition with team support.
    """

    # Step 1: Classify and assess complexity
    classifier = CapabilityClassifier()
    classification = await classifier.classify(user_request)

    complexity_engine = TeamSpawnDecisionEngine()
    complexity = complexity_engine.assess_complexity(classification)

    # Step 2: Decide on team vs individual approach
    use_teams = complexity_engine.should_spawn_team(complexity)

    # Step 3: Create DAG
    dag = MultiGoalDAG(name=f"capability_learning_{uuid.uuid4().hex[:8]}")

    if use_teams:
        # Create team tasks for each phase
        research_team = create_research_team_task(
            classification, complexity, sender_hash
        )
        implementation_team = create_implementation_team_task(
            classification, complexity, sender_hash
        )
        validation_team = create_validation_team_task(
            classification, complexity, sender_hash
        )

        # Add to DAG
        dag.add_node(research_team)
        dag.add_node(implementation_team)
        dag.add_node(validation_team)

        # Create phase dependencies
        dag.add_edge(edge(research_team.id, implementation_team.id).enables().build())
        dag.add_edge(edge(implementation_team.id, validation_team.id).enables().build())

    else:
        # Create individual tasks (original pipeline)
        research_task = create_individual_task("research", classification, sender_hash)
        implementation_task = create_individual_task("implementation", classification, sender_hash)
        validation_task = create_individual_task("validation", classification, sender_hash)

        dag.add_node(research_task)
        dag.add_node(implementation_task)
        dag.add_node(validation_task)

        dag.add_edge(edge(research_task.id, implementation_task.id).enables().build())
        dag.add_edge(edge(implementation_task.id, validation_task.id).enables().build())

    # Step 4: Execute with team-aware executor
    executor = TeamAwareTopologicalExecutor(
        team_coordinator=TeamCoordinator(
            neo4j_client=kublai_context["neo4j"],
            delegation_protocol=kublai_context["delegation"],
            cost_enforcer=TeamCostEnforcer(kublai_context["neo4j"])
        )
    )

    execution_result = await executor.execute(dag, max_parallel=4)

    # Step 5: Register successful capability
    if execution_result["status"] == "completed":
        registry = CapabilityRegistry(kublai_context["neo4j"])

        # Aggregate results from all phases
        capability_data = aggregate_phase_results(dag, execution_result)

        registration = await registry.register(
            name=classification["capability_name"],
            agent="main",  # Kublai registers on behalf of team
            tool_path=capability_data["tool_path"],
            metadata={
                "team_based": use_teams,
                "team_composition": get_team_composition(dag),
                "cost_breakdown": get_cost_breakdown(dag),
                "mastery_score": capability_data["mastery_score"],
            }
        )

        return {
            "status": "success",
            "capability_id": registration["id"],
            "team_based": use_teams,
            "total_cost": execution_result.get("total_cost", 0),
            "execution_time": execution_result.get("duration_seconds", 0),
        }

    else:
        # Handle partial failure
        return await handle_execution_failure(execution_result, dag, kublai_context)
```

### 6.2 Team Task Creation

```python
def create_research_team_task(
    classification: Dict[str, Any],
    complexity: ComplexityAssessment,
    sender_hash: str
) -> TeamTaskNode:
    """Create a research team task."""

    return TeamTaskNode(
        title=f"Research: {classification['capability_name']}",
        description=classification["research_scope"],
        task_type="research",
        team_lead="researcher",  # Möngke
        required_specialties=[
            "api_research",
            "documentation_extraction",
            "pattern_analysis",
        ],
        aggregation_strategy="merge",
        priority=Priority.HIGH if complexity.overall_score > 0.7 else Priority.NORMAL,
        metadata={
            "sender_hash": sender_hash,
            "capability_name": classification["capability_name"],
            "domain": classification["domain"],
        }
    )


def create_implementation_team_task(
    classification: Dict[str, Any],
    complexity: ComplexityAssessment,
    sender_hash: str
) -> TeamTaskNode:
    """Create an implementation team task."""

    specialties = ["code_generation"]

    if complexity.security_risk in ["HIGH", "CRITICAL"]:
        specialties.append("security_audit")

    if complexity.integration_complexity > 0.6:
        specialties.append("code_review")

    return TeamTaskNode(
        title=f"Implement: {classification['capability_name']}",
        description=f"Generate code for {classification['capability_name']}",
        task_type="implementation",
        team_lead="developer",  # Temüjin
        required_specialties=specialties,
        aggregation_strategy="hierarchical",  # Lead integrates code
        priority=Priority.HIGH,
        metadata={
            "sender_hash": sender_hash,
            "capability_name": classification["capability_name"],
            "template_type": classification.get("template_type", "api_client"),
        }
    )


def create_validation_team_task(
    classification: Dict[str, Any],
    complexity: ComplexityAssessment,
    sender_hash: str
) -> TeamTaskNode:
    """Create a validation team task."""

    return TeamTaskNode(
        title=f"Validate: {classification['capability_name']}",
        description=f"Test and validate {classification['capability_name']}",
        task_type="validation",
        team_lead="analyst",  # Jochi
        required_specialties=[
            "test_design",
            "performance_analysis",
        ],
        aggregation_strategy="consensus",  # All validators must agree
        priority=Priority.HIGH,
        metadata={
            "sender_hash": sender_hash,
            "capability_name": classification["capability_name"],
            "mastery_threshold": 0.85,
        }
    )
```

### 6.3 Result Aggregation

```python
def aggregate_phase_results(
    dag: MultiGoalDAG,
    execution_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Aggregate results from all phases into final capability data.
    """

    results = {
        "capability_name": None,
        "tool_path": None,
        "mastery_score": 0.0,
        "research_findings": None,
        "generated_code": None,
        "validation_report": None,
    }

    # Extract results from team tasks
    for team_result in execution_result.get("team_results", []):
        task_id = team_result["task_id"]
        node = dag.get_node(task_id)

        if not node:
            continue

        if node.task_type == "research":
            results["research_findings"] = team_result["result"]
            results["capability_name"] = node.metadata.get("capability_name")

        elif node.task_type == "implementation":
            results["generated_code"] = team_result["result"]
            # Extract tool path from code generation result
            if "code" in team_result["result"]:
                results["tool_path"] = team_result["result"]["code"].get("tool_path")

        elif node.task_type == "validation":
            results["validation_report"] = team_result["result"]
            results["mastery_score"] = team_result["result"].get(
                "average_mastery_score", 0.0
            )

    return results
```

---

## 7. Neo4j Schema Extensions

### 7.1 Team-Related Node Types

```cypher
// Team task node (extends Task)
(:TeamTask {
    id: uuid,
    type: "team_task",
    task_type: string,           // "research" | "implementation" | "validation"
    team_lead: string,           // Agent ID
    required_specialties: [string],
    aggregation_strategy: string, // "merge" | "vote" | "consensus" | "hierarchical"
    team_budget: float,
    sender_hash: string,
    created_at: datetime,
    status: string
})

// Team member assignment
(:TeamMemberAssignment {
    id: uuid,
    team_task_id: uuid,
    member_id: string,           // Agent ID
    role: string,                // "lead" | "specialist"
    specialty: string,
    status: string,              // "assigned" | "in_progress" | "completed" | "failed"
    progress: float,             // 0.0 - 1.0
    cost: float,
    assigned_at: datetime,
    completed_at: datetime
})

// Phase node for cross-phase dependencies
(:Phase {
    name: string,                // "research_team" | "implementation_team" | "validation_team"
    status: string,              // "pending" | "in_progress" | "completed" | "failed"
    team_task_id: uuid,
    results: string,             // JSON string
    created_at: datetime,
    completed_at: datetime
})

// Cost tracking
(:TeamCostRecord {
    id: uuid,
    team_task_id: uuid,
    member_id: string,
    operation: string,
    cost: float,
    timestamp: datetime
})

// Relationships
(:TeamTask)-[:HAS_MEMBER]->(:TeamMemberAssignment)
(:TeamTask)-[:HAS_COST]->(:TeamCostRecord)
(:Phase)-[:PHASE_DEPENDS_ON {type: string}]->(:Phase)
(:Phase)-[:EXECUTES]->(:TeamTask)
```

### 7.2 Indexes

```cypher
// Team task lookups
CREATE INDEX team_task_status IF NOT EXISTS FOR (t:TeamTask) ON (t.status, t.sender_hash);
CREATE INDEX team_task_lead IF NOT EXISTS FOR (t:TeamTask) ON (t.team_lead);

// Member assignment lookups
CREATE INDEX team_member_task IF NOT EXISTS FOR (m:TeamMemberAssignment) ON (m.team_task_id, m.member_id);
CREATE INDEX team_member_status IF NOT EXISTS FOR (m:TeamMemberAssignment) ON (m.status);

// Phase lookups
CREATE INDEX phase_status IF NOT EXISTS FOR (p:Phase) ON (p.name, p.status);
CREATE INDEX phase_dependency IF NOT EXISTS FOR ()-[r:PHASE_DEPENDS_ON]-() ON (r.type);

// Cost tracking
CREATE INDEX team_cost_task IF NOT EXISTS FOR (c:TeamCostRecord) ON (c.team_task_id);
CREATE INDEX team_cost_member IF NOT EXISTS FOR (c:TeamCostRecord) ON (c.team_task_id, c.member_id);
```

---

## 8. Integration Summary

### 8.1 Files to Modify

| File | Changes |
|------|---------|
| `tools/kurultai/horde_learn_adapter.py` | Add team orchestration logic |
| `tools/kurultai/capability_classifier.py` | Add complexity assessment |
| `tools/multi_goal_orchestration.py` | Add TeamTaskNode, TeamAwareTopologicalExecutor |
| `tools/delegation_protocol.py` | Add team delegation methods |
| `tools/kurultai/security/cost_enforcer.py` | Add TeamCostEnforcer |
| `openclaw_memory.py` | Add team-related Neo4j methods |

### 8.2 New Files to Create

| File | Purpose |
|------|---------|
| `tools/kurultai/team_orchestration.py` | TeamCoordinator, TeamSpawnDecisionEngine |
| `tools/kurultai/team_failure_recovery.py` | TeamFailureRecovery, TeamCircuitBreaker |
| `tools/kurultai/cross_team_dependencies.py` | CrossTeamDependencyManager |

### 8.3 Key Design Decisions

1. **Team Formation**: Teams spawn based on complexity threshold (0.6+) and non-CRITICAL risk
2. **Lead Selection**: Fixed by phase type (Möngke/Temüjin/Jochi) with fallback promotion
3. **Aggregation Strategies**: Research=merge, Implementation=hierarchical, Validation=consensus
4. **Failure Recovery**: Automatic for members, escalates to Kublai for lead failures
5. **Cost Tracking**: Pre-authorized team budget with per-member limits
6. **Circular Prevention**: Phase dependency graph validated before execution

---

*End of Document*
