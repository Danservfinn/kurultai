"""Team Memory Module - Agent Team Support for Kurultai.

This module extends the OperationalMemory system with team support,
enabling agent teams with lifecycle management, task assignment,
and results aggregation.

Usage:
    from tools.team_memory import TeamMemory, TeamStatus, TeamMemberRole

    # Create team
    team_id = await team_memory.create_team(
        name="Research Alpha",
        lead_agent_id="researcher",
        mission="Deep research on quantum computing"
    )

    # Assign task to team
    await team_memory.assign_task_to_team(task_id, team_id)

    # Claim team task
    task = await team_memory.claim_team_task(agent_id="researcher", team_id=team_id)

Dependencies:
    - tools/memory_integration.py (OperationalMemory base)
    - Neo4j 5.11+ (for vector indexes)
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict
from uuid import UUID, uuid4

from neo4j import AsyncGraphDatabase, AsyncDriver
from neo4j.exceptions import Neo4jError, ConstraintError

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# ENUMERATIONS
# =============================================================================

class TeamStatus(str, Enum):
    """Team lifecycle states."""
    SPAWNING = "spawning"
    ACTIVE = "active"
    PAUSED = "paused"
    SHUTTING_DOWN = "shutting_down"
    DESTROYED = "destroyed"


class TeamMemberRole(str, Enum):
    """Roles within a team."""
    LEAD = "lead"
    SENIOR = "senior"
    MEMBER = "member"
    OBSERVER = "observer"


class TeamMemberStatus(str, Enum):
    """Member participation status."""
    ACTIVE = "active"
    PAUSED = "paused"
    DEPARTED = "departed"


class TeamTaskStatus(str, Enum):
    """Task status within team context."""
    PENDING = "pending"
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class AggregationMode(str, Enum):
    """Results aggregation strategies."""
    INDIVIDUAL = "individual"
    SYNTHESIS = "synthesis"
    VOTING = "voting"
    CONCATENATION = "concatenation"
    BEST_PICK = "best_pick"


class MessageType(str, Enum):
    """Team message types."""
    COORDINATION = "coordination"
    HANDOFF = "handoff"
    ESCALATION = "escalation"
    RESULT = "result"
    BROADCAST = "broadcast"


class AccessTier(str, Enum):
    """Data access tiers."""
    PUBLIC = "PUBLIC"
    SENSITIVE = "SENSITIVE"
    PRIVATE = "PRIVATE"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class AgentTeam:
    """Represents an agent team."""
    id: str
    name: str
    slug: str
    lead_agent_id: str
    max_members: int = 5
    member_count: int = 0
    mission: str = ""
    required_capabilities: List[str] = field(default_factory=list)
    domain: str = ""
    status: TeamStatus = TeamStatus.SPAWNING
    status_changed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    created_by: str = "system"
    spawned_for_task: Optional[str] = None
    destroyed_at: Optional[datetime] = None
    destroy_reason: Optional[str] = None
    auto_destroy_on_complete: bool = False
    idle_timeout_hours: int = 24
    last_activity_at: Optional[datetime] = None
    results_aggregation_mode: AggregationMode = AggregationMode.SYNTHESIS
    aggregate_results_into: Optional[str] = None
    access_tier: AccessTier = AccessTier.PUBLIC
    sender_hash: Optional[str] = None

    @classmethod
    def from_record(cls, record: Dict[str, Any]) -> AgentTeam:
        """Create from Neo4j record."""
        return cls(
            id=record["id"],
            name=record["name"],
            slug=record["slug"],
            lead_agent_id=record["lead_agent_id"],
            max_members=record.get("max_members", 5),
            member_count=record.get("member_count", 0),
            mission=record.get("mission", ""),
            required_capabilities=record.get("required_capabilities", []),
            domain=record.get("domain", ""),
            status=TeamStatus(record.get("status", "spawning")),
            status_changed_at=record.get("status_changed_at"),
            created_at=record.get("created_at"),
            created_by=record.get("created_by", "system"),
            spawned_for_task=record.get("spawned_for_task"),
            destroyed_at=record.get("destroyed_at"),
            destroy_reason=record.get("destroy_reason"),
            auto_destroy_on_complete=record.get("auto_destroy_on_complete", False),
            idle_timeout_hours=record.get("idle_timeout_hours", 24),
            last_activity_at=record.get("last_activity_at"),
            results_aggregation_mode=AggregationMode(
                record.get("results_aggregation_mode", "synthesis")
            ),
            aggregate_results_into=record.get("aggregate_results_into"),
            access_tier=AccessTier(record.get("access_tier", "PUBLIC")),
            sender_hash=record.get("sender_hash"),
        )


@dataclass
class TeamMember:
    """Represents a team member relationship."""
    agent_id: str
    team_id: str
    joined_at: datetime
    joined_reason: str
    role_in_team: TeamMemberRole
    capabilities_contributed: List[str]
    status: TeamMemberStatus
    departed_at: Optional[datetime] = None
    departure_reason: Optional[str] = None
    tasks_completed: int = 0
    tasks_claimed: int = 0
    last_contribution_at: Optional[datetime] = None


@dataclass
class TeamTask:
    """Task assignment to a team."""
    task_id: str
    team_id: str
    assigned_at: datetime
    assigned_by: str
    assignment_reason: str
    team_status: TeamTaskStatus
    claimed_by: Optional[str] = None
    claimed_at: Optional[datetime] = None
    coordination_notes: Optional[str] = None


@dataclass
class TeamMessage:
    """Team communication audit record."""
    id: str
    team_id: str
    message_type: MessageType
    content: str
    payload: Dict[str, Any]
    from_agent: str
    to_agent: Optional[str]
    to_team: Optional[str]
    sent_at: datetime
    received_at: Optional[datetime] = None
    correlation_id: Optional[str] = None
    access_tier: AccessTier = AccessTier.PUBLIC
    sender_hash: Optional[str] = None


@dataclass
class TeamResult:
    """Aggregated team results."""
    id: str
    team_id: str
    task_id: str
    aggregated_at: datetime
    aggregation_mode: AggregationMode
    aggregated_from: List[str]
    summary: str
    deliverable: str
    confidence: float
    quality_score: float
    contributions: Dict[str, Any]
    access_tier: AccessTier = AccessTier.PUBLIC
    sender_hash: Optional[str] = None


# =============================================================================
# EXCEPTIONS
# =============================================================================

class TeamError(Exception):
    """Base exception for team operations."""
    pass


class TeamNotFoundError(TeamError):
    """Team does not exist."""
    pass


class TeamCapacityError(TeamError):
    """Team is at capacity."""
    pass


class TeamMemberError(TeamError):
    """Member-related error."""
    pass


class TeamTaskError(TeamError):
    """Task assignment error."""
    pass


class TeamRaceConditionError(TeamError):
    """Race condition during team operation."""
    pass


# =============================================================================
# TEAM MEMORY CLASS
# =============================================================================

class TeamMemory:
    """Neo4j-backed team memory for Kurultai agent teams.

    This class provides comprehensive team lifecycle management,
    task assignment, message auditing, and results aggregation.

    Example:
        >>> team_memory = TeamMemory(neo4j_driver)
        >>> team_id = await team_memory.create_team(
        ...     name="Research Team",
        ...     lead_agent_id="researcher",
        ...     mission="Research quantum computing"
        ... )
        >>> await team_memory.add_team_member(team_id, "writer")
        >>> task = await team_memory.claim_team_task("researcher", team_id)
    """

    def __init__(self, driver: AsyncDriver):
        """Initialize with Neo4j async driver.

        Args:
            driver: Async Neo4j driver instance
        """
        self.driver = driver

    @classmethod
    async def create(cls, uri: Optional[str] = None,
                     user: Optional[str] = None,
                     password: Optional[str] = None) -> TeamMemory:
        """Factory method to create TeamMemory with new driver.

        Args:
            uri: Neo4j URI (defaults to NEO4J_URI env var)
            user: Neo4j user (defaults to NEO4J_USER env var)
            password: Neo4j password (defaults to NEO4J_PASSWORD env var)

        Returns:
            Configured TeamMemory instance
        """
        uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = user or os.getenv("NEO4J_USER", "neo4j")
        password = password or os.getenv("NEO4J_PASSWORD", "password")

        driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        return cls(driver)

    async def close(self):
        """Close the Neo4j driver."""
        await self.driver.close()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    # ========================================================================
    # TEAM CRUD OPERATIONS
    # ========================================================================

    async def create_team(
        self,
        name: str,
        lead_agent_id: str,
        mission: str = "",
        domain: str = "",
        required_capabilities: Optional[List[str]] = None,
        max_members: int = 5,
        created_by: str = "system",
        spawned_for_task: Optional[str] = None,
        auto_destroy_on_complete: bool = False,
        idle_timeout_hours: int = 24,
        results_aggregation_mode: AggregationMode = AggregationMode.SYNTHESIS,
        access_tier: AccessTier = AccessTier.PUBLIC,
        sender_hash: Optional[str] = None,
    ) -> str:
        """Create a new agent team.

        Args:
            name: Human-readable team name
            lead_agent_id: Agent ID of team lead
            mission: Team purpose description
            domain: Team domain (research, development, etc.)
            required_capabilities: Capabilities needed for team tasks
            max_members: Maximum team size
            created_by: Agent/system that created the team
            spawned_for_task: Optional task that triggered creation
            auto_destroy_on_complete: Auto-destroy when tasks complete
            idle_timeout_hours: Auto-destroy after idle time
            results_aggregation_mode: How to aggregate results
            access_tier: Data access tier
            sender_hash: Sender isolation hash

        Returns:
            Created team ID

        Raises:
            TeamError: If team creation fails
        """
        team_id = str(uuid4())
        slug = name.lower().replace(" ", "-")[:50]

        query = """
            MATCH (lead:Agent {id: $lead_agent_id})
            CREATE (t:AgentTeam {
                id: $team_id,
                name: $name,
                slug: $slug,
                lead_agent_id: $lead_agent_id,
                max_members: $max_members,
                member_count: 1,
                mission: $mission,
                required_capabilities: $required_capabilities,
                domain: $domain,
                status: 'active',
                status_changed_at: datetime(),
                created_at: datetime(),
                created_by: $created_by,
                spawned_for_task: $spawned_for_task,
                auto_destroy_on_complete: $auto_destroy_on_complete,
                idle_timeout_hours: $idle_timeout_hours,
                last_activity_at: datetime(),
                results_aggregation_mode: $results_aggregation_mode,
                access_tier: $access_tier,
                sender_hash: $sender_hash
            })
            CREATE (lead)-[:TEAM_MEMBER {
                joined_at: datetime(),
                joined_reason: 'assigned',
                role_in_team: 'lead',
                capabilities_contributed: lead.primary_capabilities,
                status: 'active',
                tasks_completed: 0,
                tasks_claimed: 0
            }]->(t)
            CREATE (e:TeamLifecycleEvent {
                id: randomUUID(),
                team_id: t.id,
                event_type: 'created',
                new_state: 'active',
                triggered_by: $created_by,
                triggered_at: datetime(),
                reason: 'Team created with lead ' + $lead_agent_id
            })
            RETURN t.id as team_id
        """

        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "team_id": team_id,
                        "name": name,
                        "slug": slug,
                        "lead_agent_id": lead_agent_id,
                        "max_members": max_members,
                        "mission": mission,
                        "required_capabilities": required_capabilities or [],
                        "domain": domain,
                        "created_by": created_by,
                        "spawned_for_task": spawned_for_task,
                        "auto_destroy_on_complete": auto_destroy_on_complete,
                        "idle_timeout_hours": idle_timeout_hours,
                        "results_aggregation_mode": results_aggregation_mode.value,
                        "access_tier": access_tier.value,
                        "sender_hash": sender_hash,
                    },
                )
                record = await result.single()
                if not record:
                    raise TeamError("Team creation failed - no record returned")

                logger.info(f"Created team {team_id} with lead {lead_agent_id}")
                return record["team_id"]

        except ConstraintError as e:
            logger.error(f"Team constraint violation: {e}")
            raise TeamError(f"Team with slug '{slug}' may already exist") from e
        except Neo4jError as e:
            logger.error(f"Neo4j error creating team: {e}")
            raise TeamError(f"Failed to create team: {e}") from e

    async def get_team(self, team_id: str) -> AgentTeam:
        """Get team by ID.

        Args:
            team_id: Team UUID

        Returns:
            AgentTeam instance

        Raises:
            TeamNotFoundError: If team doesn't exist
        """
        query = """
            MATCH (t:AgentTeam {id: $team_id})
            RETURN t
        """

        async with self.driver.session() as session:
            result = await session.run(query, {"team_id": team_id})
            record = await result.single()

            if not record:
                raise TeamNotFoundError(f"Team {team_id} not found")

            return AgentTeam.from_record(dict(record["t"]))

    async def get_team_by_slug(self, slug: str) -> AgentTeam:
        """Get team by slug.

        Args:
            slug: Team slug

        Returns:
            AgentTeam instance

        Raises:
            TeamNotFoundError: If team doesn't exist
        """
        query = """
            MATCH (t:AgentTeam {slug: $slug})
            RETURN t
        """

        async with self.driver.session() as session:
            result = await session.run(query, {"slug": slug})
            record = await result.single()

            if not record:
                raise TeamNotFoundError(f"Team with slug '{slug}' not found")

            return AgentTeam.from_record(dict(record["t"]))

    async def list_teams(
        self,
        status: Optional[TeamStatus] = None,
        domain: Optional[str] = None,
        sender_hash: Optional[str] = None,
        limit: int = 100,
    ) -> List[AgentTeam]:
        """List teams with optional filtering.

        Args:
            status: Filter by team status
            domain: Filter by domain
            sender_hash: Filter by sender isolation
            limit: Maximum results

        Returns:
            List of AgentTeam instances
        """
        query = """
            MATCH (t:AgentTeam)
            WHERE ($status IS NULL OR t.status = $status)
              AND ($domain IS NULL OR t.domain = $domain)
              AND ($sender_hash IS NULL OR t.sender_hash = $sender_hash)
            RETURN t
            ORDER BY t.created_at DESC
            LIMIT $limit
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {
                    "status": status.value if status else None,
                    "domain": domain,
                    "sender_hash": sender_hash,
                    "limit": limit,
                },
            )

            teams = []
            async for record in result:
                teams.append(AgentTeam.from_record(dict(record["t"])))

            return teams

    # ========================================================================
    # TEAM MEMBER OPERATIONS
    # ========================================================================

    async def add_team_member(
        self,
        team_id: str,
        agent_id: str,
        role: TeamMemberRole = TeamMemberRole.MEMBER,
        reason: str = "assigned",
        added_by: str = "system",
    ) -> bool:
        """Add an agent to a team.

        Args:
            team_id: Team UUID
            agent_id: Agent ID to add
            role: Member role in team
            reason: Reason for joining
            added_by: Who added the member

        Returns:
            True if successful

        Raises:
            TeamNotFoundError: If team doesn't exist
            TeamCapacityError: If team is at capacity
            TeamMemberError: If agent is already a member
        """
        query = """
            MATCH (t:AgentTeam {id: $team_id})
            WHERE t.status IN ['spawning', 'active', 'paused']
              AND t.member_count < t.max_members
            MATCH (a:Agent {id: $agent_id})
            WHERE NOT EXISTS {
                MATCH (a)-[existing:TEAM_MEMBER {status: 'active'}]->(t)
            }
            CREATE (a)-[:TEAM_MEMBER {
                joined_at: datetime(),
                joined_reason: $reason,
                role_in_team: $role,
                capabilities_contributed: a.primary_capabilities,
                status: 'active',
                tasks_completed: 0,
                tasks_claimed: 0
            }]->(t)
            SET t.member_count = t.member_count + 1,
                t.last_activity_at = datetime()
            CREATE (e:TeamLifecycleEvent {
                id: randomUUID(),
                team_id: t.id,
                event_type: 'member_joined',
                new_state: t.status,
                triggered_by: $added_by,
                triggered_at: datetime(),
                reason: 'Agent ' + $agent_id + ' joined as ' + $role
            })
            RETURN t.member_count as new_member_count
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {
                    "team_id": team_id,
                    "agent_id": agent_id,
                    "role": role.value,
                    "reason": reason,
                    "added_by": added_by,
                },
            )
            record = await result.single()

            if not record:
                # Check why it failed
                team = await self.get_team(team_id)
                if team.member_count >= team.max_members:
                    raise TeamCapacityError(f"Team {team_id} is at capacity")
                raise TeamMemberError(
                    f"Agent {agent_id} may already be a member or team is not active"
                )

            logger.info(f"Added agent {agent_id} to team {team_id} as {role.value}")
            return True

    async def remove_team_member(
        self,
        team_id: str,
        agent_id: str,
        reason: str = "reassigned",
        removed_by: str = "system",
    ) -> bool:
        """Remove an agent from a team.

        Args:
            team_id: Team UUID
            agent_id: Agent ID to remove
            reason: Reason for departure
            removed_by: Who removed the member

        Returns:
            True if successful
        """
        query = """
            MATCH (a:Agent {id: $agent_id})
                  -[m:TEAM_MEMBER {status: 'active'}]
                  ->(t:AgentTeam {id: $team_id})
            SET m.status = 'departed',
                m.departed_at = datetime(),
                m.departure_reason = $reason,
                t.member_count = t.member_count - 1,
                t.last_activity_at = datetime()
            CREATE (e:TeamLifecycleEvent {
                id: randomUUID(),
                team_id: t.id,
                event_type: 'member_departed',
                previous_state: t.status,
                new_state: CASE WHEN t.member_count = 0 THEN 'shutting_down' ELSE t.status END,
                triggered_by: $removed_by,
                triggered_at: datetime(),
                reason: 'Agent ' + $agent_id + ' departed: ' + $reason
            })
            WITH t, CASE WHEN t.member_count = 0 THEN 'shutting_down' ELSE t.status END as new_status
            SET t.status = new_status
            RETURN t.member_count as remaining_members, t.status as team_status
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {
                    "team_id": team_id,
                    "agent_id": agent_id,
                    "reason": reason,
                    "removed_by": removed_by,
                },
            )
            record = await result.single()

            if not record:
                raise TeamMemberError(
                    f"Agent {agent_id} is not an active member of team {team_id}"
                )

            logger.info(
                f"Removed agent {agent_id} from team {team_id}. "
                f"Remaining: {record['remaining_members']}"
            )
            return True

    async def get_team_members(self, team_id: str) -> List[Dict[str, Any]]:
        """Get all members of a team.

        Args:
            team_id: Team UUID

        Returns:
            List of member details
        """
        query = """
            MATCH (a:Agent)-[m:TEAM_MEMBER]->(t:AgentTeam {id: $team_id})
            RETURN
                a.id as agent_id,
                a.name as name,
                a.primary_capabilities as capabilities,
                m.role_in_team as role,
                m.status as member_status,
                m.joined_at as joined_at,
                m.tasks_completed as tasks_completed,
                m.tasks_claimed as tasks_claimed
            ORDER BY m.joined_at ASC
        """

        async with self.driver.session() as session:
            result = await session.run(query, {"team_id": team_id})
            members = []
            async for record in result:
                members.append(dict(record))
            return members

    async def get_agent_teams(
        self,
        agent_id: str,
        status: Optional[TeamStatus] = None,
    ) -> List[Dict[str, Any]]:
        """Get all teams an agent belongs to.

        Args:
            agent_id: Agent ID
            status: Optional status filter

        Returns:
            List of team memberships
        """
        query = """
            MATCH (a:Agent {id: $agent_id})
                  -[m:TEAM_MEMBER {status: 'active'}]
                  ->(t:AgentTeam)
            WHERE ($status IS NULL OR t.status = $status)
            RETURN
                t.id as team_id,
                t.name as team_name,
                t.slug as team_slug,
                t.status as team_status,
                m.role_in_team as role,
                m.joined_at as joined_at,
                t.mission as mission,
                t.lead_agent_id as lead_agent_id
            ORDER BY m.joined_at DESC
        """

        async with self.driver.session() as session:
            result = await session.run(
                query, {"agent_id": agent_id, "status": status.value if status else None}
            )
            teams = []
            async for record in result:
                teams.append(dict(record))
            return teams

    # ========================================================================
    # TEAM TASK OPERATIONS
    # ========================================================================

    async def assign_task_to_team(
        self,
        task_id: str,
        team_id: str,
        assigned_by: str = "system",
        reason: str = "team_capacity",
    ) -> bool:
        """Assign an existing task to a team.

        Args:
            task_id: Task UUID
            team_id: Team UUID
            assigned_by: Who assigned the task
            reason: Assignment reason

        Returns:
            True if successful
        """
        query = """
            MATCH (task:Task {id: $task_id})
            MATCH (t:AgentTeam {id: $team_id})
            WHERE t.status IN ['spawning', 'active']
            CREATE (task)-[:ASSIGNED_TO_TEAM {
                assigned_at: datetime(),
                assigned_by: $assigned_by,
                assignment_reason: $reason,
                team_status: 'pending',
                claimed_by: null,
                claimed_at: null
            }]->(t)
            SET t.last_activity_at = datetime()
            CREATE (e:TeamLifecycleEvent {
                id: randomUUID(),
                team_id: t.id,
                event_type: 'task_assigned',
                triggered_by: $assigned_by,
                triggered_at: datetime(),
                reason: 'Task ' + $task_id + ' assigned to team'
            })
            RETURN task.id as task_id
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {
                    "task_id": task_id,
                    "team_id": team_id,
                    "assigned_by": assigned_by,
                    "reason": reason,
                },
            )
            record = await result.single()

            if not record:
                raise TeamTaskError(
                    f"Failed to assign task {task_id} to team {team_id}"
                )

            logger.info(f"Assigned task {task_id} to team {team_id}")
            return True

    async def claim_team_task(
        self,
        agent_id: str,
        team_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Claim a pending task assigned to agent's team.

        Args:
            agent_id: Agent ID claiming the task
            team_id: Optional specific team (claims from any team if None)

        Returns:
            Task details if claimed, None if no tasks available

        Raises:
            TeamRaceConditionError: If another agent claimed the task
        """
        # Generate claim attempt ID for race condition detection
        claim_attempt_id = str(uuid4())

        if team_id:
            # Claim from specific team
            query = """
                MATCH (task:Task)-[a:ASSIGNED_TO_TEAM {team_status: 'pending'}]
                      ->(t:AgentTeam {id: $team_id})
                WHERE task.status = 'pending'
                  AND EXISTS {
                    MATCH (:Agent {id: $agent_id})
                          -[:TEAM_MEMBER {status: 'active'}]
                          ->(t)
                  }
                WITH task, a, t
                LIMIT 1
                SET a.team_status = 'claimed',
                    a.claimed_by = $agent_id,
                    a.claimed_at = datetime(),
                    task.status = 'in_progress',
                    task.claimed_by = $agent_id,
                    task.claim_attempt_id = $claim_attempt_id,
                    t.last_activity_at = datetime()
                WITH task, t, a
                MATCH (agent:Agent {id: $agent_id})-[m:TEAM_MEMBER]->(t)
                SET m.tasks_claimed = m.tasks_claimed + 1
                RETURN task.id as task_id,
                       task.description as description,
                       task.priority_weight as priority,
                       a.claimed_at as claimed_at
            """
            params = {
                "team_id": team_id,
                "agent_id": agent_id,
                "claim_attempt_id": claim_attempt_id,
            }
        else:
            # Claim from any team the agent belongs to
            query = """
                MATCH (agent:Agent {id: $agent_id})
                      -[:TEAM_MEMBER {status: 'active'}]
                      ->(t:AgentTeam {status: 'active'})
                MATCH (task:Task)-[a:ASSIGNED_TO_TEAM {team_status: 'pending'}]->(t)
                WHERE task.status = 'pending'
                WITH task, a, t, agent
                ORDER BY task.priority_weight DESC, task.created_at ASC
                LIMIT 1
                SET a.team_status = 'claimed',
                    a.claimed_by = $agent_id,
                    a.claimed_at = datetime(),
                    task.status = 'in_progress',
                    task.claimed_by = $agent_id,
                    task.claim_attempt_id = $claim_attempt_id,
                    t.last_activity_at = datetime()
                WITH task, t, agent
                MATCH (agent)-[m:TEAM_MEMBER]->(t)
                SET m.tasks_claimed = m.tasks_claimed + 1
                RETURN task.id as task_id,
                       task.description as description,
                       task.priority_weight as priority,
                       t.id as team_id,
                       a.claimed_at as claimed_at
            """
            params = {"agent_id": agent_id, "claim_attempt_id": claim_attempt_id}

        async with self.driver.session() as session:
            result = await session.run(query, params)
            record = await result.single()

            if not record:
                return None

            logger.info(f"Agent {agent_id} claimed task {record['task_id']}")
            return dict(record)

    async def get_team_tasks(
        self,
        team_id: str,
        status: Optional[TeamTaskStatus] = None,
    ) -> List[Dict[str, Any]]:
        """Get all tasks assigned to a team.

        Args:
            team_id: Team UUID
            status: Optional status filter

        Returns:
            List of task details
        """
        query = """
            MATCH (task:Task)-[a:ASSIGNED_TO_TEAM]->(t:AgentTeam {id: $team_id})
            WHERE ($status IS NULL OR a.team_status = $status)
            OPTIONAL MATCH (task)<-[:CREATED_BY]-(creator:Agent)
            OPTIONAL MATCH (claimant:Agent {id: a.claimed_by})
            RETURN
                task.id as task_id,
                task.description as description,
                task.status as task_status,
                task.priority_weight as priority,
                task.deliverable_type as deliverable_type,
                a.team_status as team_status,
                a.assigned_at as assigned_at,
                a.claimed_by as claimed_by_agent,
                a.claimed_at as claimed_at,
                creator.id as created_by,
                task.created_at as created_at
            ORDER BY task.priority_weight DESC, task.created_at ASC
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {"team_id": team_id, "status": status.value if status else None},
            )
            tasks = []
            async for record in result:
                tasks.append(dict(record))
            return tasks

    # ========================================================================
    # TEAM LIFECYCLE OPERATIONS
    # ========================================================================

    async def schedule_team_destruction(
        self,
        team_id: str,
        reason: str,
        triggered_by: str = "system",
    ) -> bool:
        """Schedule a team for destruction.

        Args:
            team_id: Team UUID
            reason: Destruction reason
            triggered_by: Who triggered destruction

        Returns:
            True if scheduled
        """
        query = """
            MATCH (t:AgentTeam {id: $team_id})
            WHERE t.status IN ['spawning', 'active', 'paused']
            SET t.status = 'shutting_down',
                t.status_changed_at = datetime()
            CREATE (e:TeamLifecycleEvent {
                id: randomUUID(),
                team_id: t.id,
                event_type: 'destroy_scheduled',
                previous_state: 'active',
                new_state: 'shutting_down',
                triggered_by: $triggered_by,
                triggered_at: datetime(),
                reason: $reason
            })
            WITH t
            MATCH (a:Agent)-[m:TEAM_MEMBER {status: 'active'}]->(t)
            SET m.status = 'departed',
                m.departed_at = datetime(),
                m.departure_reason = 'team_shutdown'
            SET t.member_count = 0
            RETURN t.id as team_id, t.status as status
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {"team_id": team_id, "reason": reason, "triggered_by": triggered_by},
            )
            record = await result.single()

            if not record:
                raise TeamError(f"Team {team_id} not found or not active")

            logger.info(f"Scheduled destruction of team {team_id}: {reason}")
            return True

    async def complete_team_destruction(
        self,
        team_id: str,
        triggered_by: str = "system",
    ) -> bool:
        """Complete team destruction after shutdown period.

        Args:
            team_id: Team UUID
            triggered_by: Who triggered destruction

        Returns:
            True if destroyed
        """
        query = """
            MATCH (t:AgentTeam {id: $team_id})
            WHERE t.status = 'shutting_down'
            SET t.status = 'destroyed',
                t.destroyed_at = datetime(),
                t.destroy_reason = 'mission_complete',
                t.status_changed_at = datetime()
            CREATE (e:TeamLifecycleEvent {
                id: randomUUID(),
                team_id: t.id,
                event_type: 'destroyed',
                previous_state: 'shutting_down',
                new_state: 'destroyed',
                triggered_by: $triggered_by,
                triggered_at: datetime(),
                reason: 'Team destruction completed'
            })
            RETURN t.id as team_id, t.destroyed_at as destroyed_at
        """

        async with self.driver.session() as session:
            result = await session.run(
                query, {"team_id": team_id, "triggered_by": triggered_by}
            )
            record = await result.single()

            if not record:
                raise TeamError(f"Team {team_id} not found or not in shutting_down state")

            logger.info(f"Completed destruction of team {team_id}")
            return True

    # ========================================================================
    # TEAM MESSAGING
    # ========================================================================

    async def record_team_message(
        self,
        team_id: str,
        from_agent: str,
        content: str,
        message_type: MessageType = MessageType.COORDINATION,
        to_agent: Optional[str] = None,
        to_team: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
        access_tier: AccessTier = AccessTier.PUBLIC,
        sender_hash: Optional[str] = None,
    ) -> str:
        """Record a message in team audit trail.

        Args:
            team_id: Team UUID
            from_agent: Sending agent ID
            content: Message content
            message_type: Type of message
            to_agent: Optional recipient agent
            to_team: Optional recipient team
            payload: Optional structured data
            correlation_id: Optional conversation ID
            access_tier: Data access tier
            sender_hash: Sender isolation hash

        Returns:
            Created message ID
        """
        message_id = str(uuid4())

        query = """
            CREATE (m:TeamMessage {
                id: $message_id,
                team_id: $team_id,
                message_type: $message_type,
                content: $content,
                payload: $payload,
                from_agent: $from_agent,
                to_agent: $to_agent,
                to_team: $to_team,
                sent_at: datetime(),
                received_at: null,
                correlation_id: $correlation_id,
                access_tier: $access_tier,
                sender_hash: $sender_hash
            })
            WITH m
            MATCH (t:AgentTeam {id: $team_id})
            SET t.last_activity_at = datetime()
            RETURN m.id as message_id
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {
                    "message_id": message_id,
                    "team_id": team_id,
                    "message_type": message_type.value,
                    "content": content,
                    "payload": payload or {},
                    "from_agent": from_agent,
                    "to_agent": to_agent,
                    "to_team": to_team,
                    "correlation_id": correlation_id or str(uuid4()),
                    "access_tier": access_tier.value,
                    "sender_hash": sender_hash,
                },
            )
            record = await result.single()
            return record["message_id"]

    async def get_team_messages(
        self,
        team_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        message_type: Optional[MessageType] = None,
        correlation_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get team message audit trail.

        Args:
            team_id: Team UUID
            start_time: Optional start filter
            end_time: Optional end filter
            message_type: Optional type filter
            correlation_id: Optional conversation filter
            limit: Maximum results

        Returns:
            List of message records
        """
        query = """
            MATCH (m:TeamMessage {team_id: $team_id})
            WHERE ($start_time IS NULL OR m.sent_at >= $start_time)
              AND ($end_time IS NULL OR m.sent_at <= $end_time)
              AND ($message_type IS NULL OR m.message_type = $message_type)
              AND ($correlation_id IS NULL OR m.correlation_id = $correlation_id)
            OPTIONAL MATCH (sender:Agent {id: m.from_agent})
            OPTIONAL MATCH (recipient:Agent {id: m.to_agent})
            RETURN
                m.id as message_id,
                m.message_type as type,
                m.sent_at as sent_at,
                m.from_agent as from_agent,
                sender.name as sender_name,
                m.to_agent as to_agent,
                recipient.name as recipient_name,
                m.content as content,
                m.payload as payload,
                m.correlation_id as correlation_id,
                m.received_at as received_at
            ORDER BY m.sent_at DESC
            LIMIT $limit
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {
                    "team_id": team_id,
                    "start_time": start_time,
                    "end_time": end_time,
                    "message_type": message_type.value if message_type else None,
                    "correlation_id": correlation_id,
                    "limit": limit,
                },
            )
            messages = []
            async for record in result:
                messages.append(dict(record))
            return messages

    # ========================================================================
    # RESULTS AGGREGATION
    # ========================================================================

    async def aggregate_team_results(
        self,
        team_id: str,
        parent_task_id: str,
        task_ids: List[str],
        aggregation_mode: AggregationMode,
        summary: str,
        deliverable: str,
        confidence: float,
        contributions: Dict[str, Any],
        triggered_by: str = "system",
        access_tier: AccessTier = AccessTier.PUBLIC,
        sender_hash: Optional[str] = None,
    ) -> str:
        """Aggregate completed team tasks into TeamResult.

        Args:
            team_id: Team UUID
            parent_task_id: Parent/composite task ID
            task_ids: List of completed task IDs to aggregate
            aggregation_mode: How results were aggregated
            summary: Human-readable summary
            deliverable: Final deliverable content
            confidence: Confidence score (0-1)
            contributions: Map of agent contributions
            triggered_by: Who triggered aggregation
            access_tier: Data access tier
            sender_hash: Sender isolation hash

        Returns:
            Created result ID
        """
        result_id = str(uuid4())

        query = """
            MATCH (t:AgentTeam {id: $team_id})
            MATCH (parent:Task {id: $parent_task_id})
            MATCH (task:Task)
            WHERE task.id IN $task_ids
              AND task.status = 'completed'
            WITH t, parent, collect(task) as tasks,
                 avg(task.quality_score) as avg_quality
            CREATE (r:TeamResult {
                id: $result_id,
                team_id: $team_id,
                task_id: $parent_task_id,
                aggregated_at: datetime(),
                aggregation_mode: $aggregation_mode,
                aggregated_from: $task_ids,
                summary: $summary,
                deliverable: $deliverable,
                confidence: $confidence,
                quality_score: avg_quality,
                contributions: $contributions,
                access_tier: $access_tier,
                sender_hash: $sender_hash
            })
            CREATE (t)-[:PRODUCED]->(r)
            CREATE (r)-[:CONTRIBUTES_TO]->(parent)
            FOREACH (task IN tasks |
                CREATE (r)-[:AGGREGATES {aggregated_at: datetime()}]->(task)
            )
            CREATE (e:TeamLifecycleEvent {
                id: randomUUID(),
                team_id: t.id,
                event_type: 'results_aggregated',
                triggered_by: $triggered_by,
                triggered_at: datetime(),
                reason: 'Aggregated ' + size($task_ids) + ' tasks into result'
            })
            RETURN r.id as result_id
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {
                    "result_id": result_id,
                    "team_id": team_id,
                    "parent_task_id": parent_task_id,
                    "task_ids": task_ids,
                    "aggregation_mode": aggregation_mode.value,
                    "summary": summary,
                    "deliverable": deliverable,
                    "confidence": confidence,
                    "contributions": contributions,
                    "triggered_by": triggered_by,
                    "access_tier": access_tier.value,
                    "sender_hash": sender_hash,
                },
            )
            record = await result.single()

            if not record:
                raise TeamError("Failed to aggregate team results")

            logger.info(f"Created team result {record['result_id']} for team {team_id}")
            return record["result_id"]

    async def get_team_results(
        self,
        team_id: str,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get aggregated results for a team.

        Args:
            team_id: Team UUID
            since: Optional time filter
            limit: Maximum results

        Returns:
            List of result records
        """
        query = """
            MATCH (r:TeamResult {team_id: $team_id})
            WHERE ($since IS NULL OR r.aggregated_at >= $since)
            OPTIONAL MATCH (r)-[:AGGREGATES]->(task:Task)
            WITH r, collect(task.id) as source_task_ids
            RETURN
                r.id as result_id,
                r.aggregated_at as aggregated_at,
                r.aggregation_mode as mode,
                r.summary as summary,
                r.deliverable as deliverable,
                r.confidence as confidence,
                r.quality_score as quality_score,
                r.contributions as contributions,
                source_task_ids
            ORDER BY r.aggregated_at DESC
            LIMIT $limit
        """

        async with self.driver.session() as session:
            result = await session.run(
                query, {"team_id": team_id, "since": since, "limit": limit}
            )
            results = []
            async for record in result:
                results.append(dict(record))
            return results

    # ========================================================================
    # MAINTENANCE OPERATIONS
    # ========================================================================

    async def get_teams_for_destruction(
        self, idle_hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get teams ready for auto-destruction.

        Args:
            idle_hours: Hours of inactivity threshold

        Returns:
            List of teams ready for cleanup
        """
        query = """
            MATCH (t:AgentTeam)
            WHERE t.status IN ['active', 'paused']
              AND t.auto_destroy_on_complete = true
              AND t.last_activity_at < datetime() - duration({hours: $idle_hours})
              AND NOT EXISTS {
                MATCH (task:Task)-[:ASSIGNED_TO_TEAM {team_status: 'in_progress'}]->(t)
              }
            RETURN
                t.id as team_id,
                t.name as name,
                t.status as status,
                t.last_activity_at as last_activity,
                t.member_count as member_count,
                duration.between(t.last_activity_at, datetime()).hours as idle_hours
            ORDER BY t.last_activity_at ASC
        """

        async with self.driver.session() as session:
            result = await session.run(query, {"idle_hours": idle_hours})
            teams = []
            async for record in result:
                teams.append(dict(record))
            return teams

    async def cleanup_lifecycle_events(self, batch_size: int = 1000) -> int:
        """Purge old lifecycle events past retention.

        Args:
            batch_size: Maximum events to delete

        Returns:
            Number of events deleted
        """
        query = """
            MATCH (e:TeamLifecycleEvent)
            WHERE e.retained_until < datetime()
            WITH e LIMIT $batch_size
            DETACH DELETE e
            RETURN count(e) as deleted_count
        """

        async with self.driver.session() as session:
            result = await session.run(query, {"batch_size": batch_size})
            record = await result.single()
            return record["deleted_count"] if record else 0
