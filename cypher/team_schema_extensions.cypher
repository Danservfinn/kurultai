// =============================================================================
// NEO4J SCHEMA EXTENSIONS FOR AGENT TEAMS
// Kurultai Architecture - Team Support Additions
// =============================================================================
//
// This file extends the existing Neo4j schema from:
// - docs/plans/neo4j.md (base schema: Agent, Task, Research, etc.)
// - docs/plans/kurultai_0.1.md (DAG extensions: DEPENDS_ON, BLOCKS, etc.)
// - docs/plans/kurultai_0.2.md (Research nodes with research_type)
//
// New additions:
// - :AgentTeam nodes for team composition and lifecycle
// - :TeamMember relationships for agent membership
// - :TeamTask relationships for task assignments
// - :TeamMessage for inter-team audit trail
// - :TeamResult for aggregated results
//
// =============================================================================

// =============================================================================
// SECTION 1: TEAM NODE TYPE DEFINITIONS
// =============================================================================

// :AgentTeam - Represents a team of agents working together
(:AgentTeam {
  // Primary identifiers
  id: uuid,                      // Unique team identifier
  name: string,                  // Human-readable team name
  slug: string,                  // URL-safe identifier (e.g., "research-alpha")

  // Team composition
  lead_agent_id: string,         // Agent ID of team lead (must exist in :Agent)
  max_members: integer,          // Maximum team size (default: 5)
  member_count: integer,         // Current member count (computed)

  // Team purpose and capabilities
  mission: string,               // Brief description of team's purpose
  required_capabilities: [string], // Capabilities needed for team tasks
  domain: string,                // "research" | "development" | "analysis" | "operations"

  // Lifecycle state
  status: string,                // "spawning" | "active" | "paused" | "shutting_down" | "destroyed"
  status_changed_at: datetime,   // When status last changed

  // Creation and destruction tracking
  created_at: datetime,          // Team creation timestamp
  created_by: string,            // Agent or user that created the team
  spawned_for_task: uuid,        // Optional: task that triggered team creation

  destroyed_at: datetime,        // When team was destroyed (null if active)
  destroy_reason: string,        // "mission_complete" | "timeout" | "manual" | "reorganization"

  // Operational settings
  auto_destroy_on_complete: boolean, // Destroy when all tasks done (default: false)
  idle_timeout_hours: integer,   // Auto-destroy after idle (default: 24)
  last_activity_at: datetime,    // Last task claim or message

  // Results aggregation
  results_aggregation_mode: string, // "individual" | "synthesis" | "voting"
  aggregate_results_into: uuid,  // Task ID to aggregate results into

  // Access control
  access_tier: string,           // "PUBLIC" | "SENSITIVE" | "PRIVATE"
  sender_hash: string            // For sender isolation (null if system team)
})

// :TeamMember - Relationship properties (Agent)-[:TEAM_MEMBER]->(AgentTeam)
// Note: This is a RELATIONSHIP, not a node
(:TEAM_MEMBER {
  joined_at: datetime,           // When agent joined the team
  joined_reason: string,         // "assigned" | "volunteered" | "auto_assigned"
  role_in_team: string,          // "lead" | "senior" | "member" | "observer"
  capabilities_contributed: [string], // Capabilities this agent brings

  // Status tracking
  status: string,                // "active" | "paused" | "departed"
  departed_at: datetime,         // When agent left (null if active)
  departure_reason: string,      // "task_complete" | "reassigned" | "timeout" | "removed"

  // Performance tracking
  tasks_completed: integer,      // Count of tasks completed as team member
  tasks_claimed: integer,        // Count of tasks claimed
  last_contribution_at: datetime // Last task completion
})

// :TeamTask - Relationship properties (Task)-[:ASSIGNED_TO_TEAM]->(AgentTeam)
// Note: This is a RELATIONSHIP, not a node
(:ASSIGNED_TO_TEAM {
  assigned_at: datetime,         // When task was assigned to team
  assigned_by: string,           // Agent or system that assigned
  assignment_reason: string,     // "team_capacity" | "capability_match" | "manual"

  // Execution tracking
  claimed_by: string,            // Agent ID that claimed (null if unclaimed)
  claimed_at: datetime,          // When claimed

  // Team-specific status
  team_status: string,           // "pending" | "claimed" | "in_progress" | "completed" | "blocked"
  coordination_notes: string     // Notes for team coordination
})

// :TeamMessage - Audit trail for inter-team communication
(:TeamMessage {
  id: uuid,                      // Message identifier
  team_id: uuid,                 // Reference to AgentTeam

  // Message content
  message_type: string,          // "coordination" | "handoff" | "escalation" | "result" | "broadcast"
  content: string,               // Message content (may be encrypted for SENSITIVE)
  payload: map,                  // Structured data (JSON object)

  // Sender/recipient tracking
  from_agent: string,            // Agent ID of sender
  to_agent: string,              // Agent ID of recipient (null for broadcast)
  to_team: uuid,                 // Target team ID (null for intra-team)

  // Audit fields
  sent_at: datetime,             // When message was sent
  received_at: datetime,         // When recipient processed (null if pending)
  correlation_id: uuid,          // Links related messages

  // Access control
  access_tier: string,           // "PUBLIC" | "SENSITIVE" | "PRIVATE"
  sender_hash: string            // For sender isolation
})

// :TeamResult - Aggregated results from team execution
(:TeamResult {
  id: uuid,                      // Result identifier
  team_id: uuid,                 // Reference to AgentTeam
  task_id: uuid,                 // Reference to parent task

  // Aggregation metadata
  aggregated_at: datetime,       // When aggregation occurred
  aggregation_mode: string,      // "synthesis" | "voting" | "concatenation" | "best_pick"
  aggregated_from: [uuid],       // Task IDs that contributed

  // Result content
  summary: string,               // Human-readable summary
  deliverable: string,           // Final deliverable content
  confidence: float,             // 0.0-1.0 confidence score
  quality_score: float,          // 0.0-1.0 quality assessment

  // Individual contributions (map of agent_id -> contribution summary)
  contributions: map,            // {agent_id: {summary, quality_score, timestamp}}

  // Access control
  access_tier: string,           // "PUBLIC" | "SENSITIVE" | "PRIVATE"
  sender_hash: string            // For sender isolation
})

// :TeamLifecycleEvent - Audit log for team state changes
(:TeamLifecycleEvent {
  id: uuid,                      // Event identifier
  team_id: uuid,                 // Reference to AgentTeam

  // Event details
  event_type: string,            // "created" | "member_joined" | "member_departed" |
                                 // "status_changed" | "task_assigned" | "results_aggregated" |
                                 // "destroy_scheduled" | "destroyed"
  previous_state: string,        // Previous status/state (if applicable)
  new_state: string,             // New status/state (if applicable)

  // Actor tracking
  triggered_by: string,          // Agent ID or "system" that triggered change
  triggered_at: datetime,        // When event occurred

  // Context
  reason: string,                // Human-readable reason
  context: map,                  // Additional context data

  // Retention
  retained_until: datetime       // When this event can be purged
})

// =============================================================================
// SECTION 2: CONSTRAINTS AND INDEXES
// =============================================================================

// ---------------------------------------------------------------------------
// UNIQUE CONSTRAINTS
// ---------------------------------------------------------------------------

CREATE CONSTRAINT team_id_unique IF NOT EXISTS
  FOR (t:AgentTeam) REQUIRE t.id IS UNIQUE;

CREATE CONSTRAINT team_slug_unique IF NOT EXISTS
  FOR (t:AgentTeam) REQUIRE t.slug IS UNIQUE;

CREATE CONSTRAINT team_message_id_unique IF NOT EXISTS
  FOR (m:TeamMessage) REQUIRE m.id IS UNIQUE;

CREATE CONSTRAINT team_result_id_unique IF NOT EXISTS
  FOR (r:TeamResult) REQUIRE r.id IS UNIQUE;

CREATE CONSTRAINT team_lifecycle_event_id_unique IF NOT EXISTS
  FOR (e:TeamLifecycleEvent) REQUIRE e.id IS UNIQUE;

// ---------------------------------------------------------------------------
// PERFORMANCE INDEXES
// ---------------------------------------------------------------------------

// Team lookup indexes
CREATE INDEX team_status_lookup IF NOT EXISTS
  FOR (t:AgentTeam) ON (t.status, t.created_at);

CREATE INDEX team_lead_lookup IF NOT EXISTS
  FOR (t:AgentTeam) ON (t.lead_agent_id, t.status);

CREATE INDEX team_domain_lookup IF NOT EXISTS
  FOR (t:AgentTeam) ON (t.domain, t.status);

CREATE INDEX team_sender_lookup IF NOT EXISTS
  FOR (t:AgentTeam) ON (t.sender_hash, t.status);

// Team activity tracking (for idle timeout detection)
CREATE INDEX team_activity_lookup IF NOT EXISTS
  FOR (t:AgentTeam) ON (t.last_activity_at, t.status)
  WHERE t.status = 'active';

// Team member relationship index (for agent team queries)
CREATE INDEX team_member_lookup IF NOT EXISTS
  FOR ()-[r:TEAM_MEMBER]-() ON (r.status, r.joined_at);

// Team task assignment index
CREATE INDEX team_task_lookup IF NOT EXISTS
  FOR ()-[r:ASSIGNED_TO_TEAM]-() ON (r.team_status, r.assigned_at);

// Message audit trail indexes
CREATE INDEX team_message_team_lookup IF NOT EXISTS
  FOR (m:TeamMessage) ON (m.team_id, m.sent_at);

CREATE INDEX team_message_correlation_lookup IF NOT EXISTS
  FOR (m:TeamMessage) ON (m.correlation_id, m.sent_at);

CREATE INDEX team_message_sender_lookup IF NOT EXISTS
  FOR (m:TeamMessage) ON (m.from_agent, m.sent_at);

// Results aggregation indexes
CREATE INDEX team_result_team_lookup IF NOT EXISTS
  FOR (r:TeamResult) ON (r.team_id, r.aggregated_at);

CREATE INDEX team_result_task_lookup IF NOT EXISTS
  FOR (r:TeamResult) ON (r.task_id, r.aggregated_at);

// Lifecycle event indexes (for audit queries)
CREATE INDEX team_lifecycle_team_lookup IF NOT EXISTS
  FOR (e:TeamLifecycleEvent) ON (e.team_id, e.triggered_at);

CREATE INDEX team_lifecycle_event_type_lookup IF NOT EXISTS
  FOR (e:TeamLifecycleEvent) ON (e.event_type, e.triggered_at);

CREATE INDEX team_lifecycle_retention_lookup IF NOT EXISTS
  FOR (e:TeamLifecycleEvent) ON (e.retained_until)
  WHERE e.retained_until IS NOT NULL;

// Full-text index for team search
CREATE FULLTEXT INDEX team_search IF NOT EXISTS
  FOR (t:AgentTeam) ON EACH [t.name, t.mission];

// =============================================================================
// SECTION 3: RELATIONSHIP DEFINITIONS
// =============================================================================

// Core team relationships
(Agent)-[:TEAM_MEMBER {joined_at, role_in_team, status}]->(AgentTeam)
(AgentTeam)-[:LED_BY]->(Agent)  // Lead agent relationship
(AgentTeam)-[:HAS_MEMBER]->(Agent)  // Inverse of TEAM_MEMBER

// Task relationships
(Task)-[:ASSIGNED_TO_TEAM {assigned_at, team_status}]->(AgentTeam)
(AgentTeam)-[:HAS_TASK]->(Task)  // Inverse

// Message relationships
(Agent)-[:SENT_MESSAGE]->(TeamMessage)
(TeamMessage)-[:SENT_TO]->(Agent)
(TeamMessage)-[:BROADCAST_TO]->(AgentTeam)
(TeamMessage)-[:PART_OF_CONVERSATION {correlation_id}]->(TeamMessage)

// Result relationships
(AgentTeam)-[:PRODUCED]->(TeamResult)
(TeamResult)-[:AGGREGATES]->(Task)  // Links to individual tasks aggregated
(TeamResult)-[:CONTRIBUTES_TO]->(Task)  // Links to parent/composite task

// Lifecycle audit
(AgentTeam)-[:HAS_LIFECYCLE_EVENT]->(TeamLifecycleEvent)
(TeamLifecycleEvent)-[:CHANGED_STATE_FROM {previous_state}]->(AgentTeam)
(TeamLifecycleEvent)-[:CHANGED_STATE_TO {new_state}]->(AgentTeam)

// Team-to-team relationships (for larger organizations)
(AgentTeam)-[:PARENT_TEAM]->(AgentTeam)  // Hierarchical teams
(AgentTeam)-[:COLLABORATES_WITH {domain}]->(AgentTeam)  // Cross-team collaboration
(AgentTeam)-[:DEPENDS_ON {reason}]->(AgentTeam)  // Team dependencies

// Integration with existing Task DAG
// Teams can have their own subgraph within the larger DAG
(AgentTeam)-[:OWNS_SUBGRAPH {subgraph_id}]->(Task)  // Entry point to team tasks

// =============================================================================
// SECTION 4: QUERY PATTERNS
// =============================================================================

// ---------------------------------------------------------------------------
// QUERY: Get all active teams for an agent
// ---------------------------------------------------------------------------
// Returns all teams where the agent is an active member
//
// Parameters:
//   $agent_id - The agent ID to query for
//
// Returns:
//   team_id, team_name, role_in_team, joined_at, team_status, member_count

// Cypher:
MATCH (a:Agent {id: $agent_id})-[m:TEAM_MEMBER {status: 'active'}]->(t:AgentTeam)
WHERE t.status IN ['spawning', 'active', 'paused']
RETURN
  t.id as team_id,
  t.name as team_name,
  t.slug as team_slug,
  m.role_in_team as role,
  m.joined_at as joined_at,
  t.status as team_status,
  t.lead_agent_id as lead_agent_id,
  t.mission as mission,
  t.member_count as member_count
ORDER BY m.joined_at DESC;

// ---------------------------------------------------------------------------
// QUERY: Get all tasks for a team
// ---------------------------------------------------------------------------
// Returns all tasks assigned to a team with their current status
//
// Parameters:
//   $team_id - The team ID to query for
//   $status_filter - Optional: filter by team_status
//
// Returns:
//   task details with assignment metadata

// Cypher (all tasks):
MATCH (task:Task)-[a:ASSIGNED_TO_TEAM]->(t:AgentTeam {id: $team_id})
MATCH (task)-[:CREATED_BY]->(creator:Agent)
OPTIONAL MATCH (task)-[:CLAIMED_BY]->(claimer:Agent)
RETURN
  task.id as task_id,
  task.description as description,
  task.status as status,
  task.priority_weight as priority,
  task.deliverable_type as deliverable_type,
  a.team_status as team_status,
  a.assigned_at as assigned_at,
  a.claimed_by as claimed_by_agent,
  a.claimed_at as claimed_at,
  creator.id as created_by,
  task.created_at as created_at
ORDER BY task.priority_weight DESC, task.created_at ASC;

// Cypher (pending tasks only):
MATCH (task:Task)-[a:ASSIGNED_TO_TEAM {team_status: 'pending'}]->(t:AgentTeam {id: $team_id})
WHERE task.status IN ['pending', 'ready']
RETURN
  task.id as task_id,
  task.description as description,
  task.priority_weight as priority,
  task.deliverable_type as deliverable_type,
  task.embedding as embedding
ORDER BY task.priority_weight DESC, task.created_at ASC;

// ---------------------------------------------------------------------------
// QUERY: Get team results for aggregation
// ---------------------------------------------------------------------------
// Returns completed team results ready for aggregation
//
// Parameters:
//   $team_id - The team ID to query for
//   $parent_task_id - Optional: specific parent task
//
// Returns:
//   Aggregated results with individual contributions

// Cypher:
MATCH (r:TeamResult {team_id: $team_id})
WHERE r.aggregated_at >= datetime() - duration({hours: 24})
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
  r.aggregated_from as source_task_ids,
  source_task_ids
ORDER BY r.aggregated_at DESC;

// ---------------------------------------------------------------------------
// QUERY: Get team message audit trail
// ---------------------------------------------------------------------------
// Returns message history for audit purposes
//
// Parameters:
//   $team_id - The team ID to query for
//   $start_time - Optional: start of time range
//   $end_time - Optional: end of time range
//   $message_type - Optional: filter by message type
//
// Returns:
//   Message history with sender/recipient details

// Cypher (full audit trail):
MATCH (m:TeamMessage {team_id: $team_id})
WHERE ($start_time IS NULL OR m.sent_at >= $start_time)
  AND ($end_time IS NULL OR m.sent_at <= $end_time)
  AND ($message_type IS NULL OR m.message_type = $message_type)
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
ORDER BY m.sent_at DESC;

// Cypher (conversation thread):
MATCH (m:TeamMessage {team_id: $team_id, correlation_id: $correlation_id})
OPTIONAL MATCH (sender:Agent {id: m.from_agent})
RETURN
  m.id as message_id,
  m.message_type as type,
  m.sent_at as sent_at,
  m.from_agent as from_agent,
  sender.name as sender_name,
  m.content as content
ORDER BY m.sent_at ASC;

// ---------------------------------------------------------------------------
// QUERY: Get teams ready for destruction (cleanup)
// ---------------------------------------------------------------------------
// Returns teams that should be auto-destroyed based on idle timeout
//
// Parameters:
//   $idle_hours - Hours of inactivity before destruction
//
// Returns:
//   Teams ready for cleanup

// Cypher:
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
ORDER BY t.last_activity_at ASC;

// ---------------------------------------------------------------------------
// QUERY: Get team composition with capabilities
// ---------------------------------------------------------------------------
// Returns full team roster with member capabilities
//
// Parameters:
//   $team_id - The team ID to query for
//
// Returns:
//   Team members with their capabilities and roles

// Cypher:
MATCH (t:AgentTeam {id: $team_id})
MATCH (lead:Agent {id: t.lead_agent_id})
MATCH (a:Agent)-[m:TEAM_MEMBER]->(t)
RETURN
  t.id as team_id,
  t.name as team_name,
  t.status as team_status,
  t.mission as mission,
  lead.id as lead_id,
  lead.name as lead_name,
  collect({
    agent_id: a.id,
    name: a.name,
    role: m.role_in_team,
    status: m.status,
    joined_at: m.joined_at,
    capabilities: a.primary_capabilities,
    tasks_completed: m.tasks_completed
  }) as members;

// ---------------------------------------------------------------------------
// QUERY: Find teams by capability match
// ---------------------------------------------------------------------------
// Returns teams that have agents with specific capabilities
//
// Parameters:
//   $required_capabilities - List of required capability strings
//   $min_match_count - Minimum number of capabilities to match
//
// Returns:
//   Teams ranked by capability match

// Cypher:
MATCH (t:AgentTeam {status: 'active'})
MATCH (a:Agent)-[:TEAM_MEMBER {status: 'active'}]->(t)
WITH t, collect(DISTINCT cap IN a.primary_capabilities) as team_caps
WITH t, team_caps,
     size([cap IN team_caps WHERE cap IN $required_capabilities]) as match_count
WHERE match_count >= $min_match_count
RETURN
  t.id as team_id,
  t.name as team_name,
  t.domain as domain,
  team_caps as capabilities,
  match_count,
  size($required_capabilities) as required_count,
  round(100.0 * match_count / size($required_capabilities), 2) as match_percentage
ORDER BY match_count DESC, t.member_count DESC;

// =============================================================================
// SECTION 5: TEAM LIFECYCLE OPERATIONS
// =============================================================================

// ---------------------------------------------------------------------------
// OPERATION: Create a new team
// ---------------------------------------------------------------------------
// Creates a team and adds the lead agent as first member
//
// Parameters:
//   $name, $slug, $lead_agent_id, $mission, $domain, $created_by, etc.
//
// Returns:
//   Created team ID

// Cypher:
CREATE (t:AgentTeam {
  id: randomUUID(),
  name: $name,
  slug: $slug,
  lead_agent_id: $lead_agent_id,
  max_members: $max_members,
  member_count: 1,
  mission: $mission,
  required_capabilities: $required_capabilities,
  domain: $domain,
  status: 'spawning',
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
WITH t
MATCH (lead:Agent {id: $lead_agent_id})
CREATE (lead)-[:TEAM_MEMBER {
  joined_at: datetime(),
  joined_reason: 'assigned',
  role_in_team: 'lead',
  capabilities_contributed: lead.primary_capabilities,
  status: 'active',
  tasks_completed: 0,
  tasks_claimed: 0
}]->(t)
CREATE (t)-[:HAS_LIFECYCLE_EVENT {
  id: randomUUID(),
  event_type: 'created',
  triggered_by: $created_by,
  triggered_at: datetime(),
  reason: 'Team created with lead ' + $lead_agent_id
}]->(e:TeamLifecycleEvent {
  id: randomUUID(),
  team_id: t.id,
  event_type: 'created',
  new_state: 'spawning',
  triggered_by: $created_by,
  triggered_at: datetime(),
  reason: 'Team created'
})
SET t.status = 'active'
RETURN t.id as team_id;

// ---------------------------------------------------------------------------
// OPERATION: Add member to team
// ---------------------------------------------------------------------------
// Adds an agent to an existing team
//
// Parameters:
//   $team_id, $agent_id, $role, $reason
//
// Returns:
//   Success status

// Cypher:
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
RETURN t.member_count as new_member_count;

// ---------------------------------------------------------------------------
// OPERATION: Remove member from team
// ---------------------------------------------------------------------------
// Marks an agent as departed from the team
//
// Parameters:
//   $team_id, $agent_id, $reason, $removed_by
//
// Returns:
//   Success status

// Cypher:
MATCH (a:Agent {id: $agent_id})-[m:TEAM_MEMBER {status: 'active'}]->(t:AgentTeam {id: $team_id})
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
  new_state: t.status,
  triggered_by: $removed_by,
  triggered_at: datetime(),
  reason: 'Agent ' + $agent_id + ' departed: ' + $reason
})
// If member count reaches 0, schedule destruction
WITH t, CASE WHEN t.member_count = 0 THEN 'destroy_scheduled' ELSE t.status END as new_status
SET t.status = new_status
RETURN t.member_count as remaining_members, t.status as team_status;

// ---------------------------------------------------------------------------
// OPERATION: Schedule team destruction
// ---------------------------------------------------------------------------
// Initiates team shutdown sequence
//
// Parameters:
//   $team_id, $reason, $triggered_by
//
// Returns:
//   Success status

// Cypher:
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
// Mark all active members as departing
WITH t
MATCH (a:Agent)-[m:TEAM_MEMBER {status: 'active'}]->(t)
SET m.status = 'departed',
    m.departed_at = datetime(),
    m.departure_reason = 'team_shutdown'
SET t.member_count = 0
RETURN t.id as team_id, t.status as status;

// ---------------------------------------------------------------------------
// OPERATION: Complete team destruction
// ---------------------------------------------------------------------------
// Finalizes team destruction after shutdown period
//
// Parameters:
//   $team_id, $triggered_by
//
// Returns:
//   Success status

// Cypher:
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
RETURN t.id as team_id, t.destroyed_at as destroyed_at;

// ---------------------------------------------------------------------------
// OPERATION: Assign task to team
// ---------------------------------------------------------------------------
// Assigns a task to a team for execution
//
// Parameters:
//   $task_id, $team_id, $assigned_by, $reason
//
// Returns:
//   Success status

// Cypher:
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
RETURN task.id as task_id, t.id as team_id;

// ---------------------------------------------------------------------------
// OPERATION: Claim team task
// ---------------------------------------------------------------------------
// Team member claims a task assigned to their team
//
// Parameters:
//   $task_id, $team_id, $agent_id, $claim_attempt_id
//
// Returns:
//   Success status (with race condition handling)

// Cypher:
MATCH (task:Task {id: $task_id})-[a:ASSIGNED_TO_TEAM]->(t:AgentTeam {id: $team_id})
WHERE a.team_status = 'pending'
  AND task.status = 'pending'
  AND EXISTS {
    MATCH (:Agent {id: $agent_id})-[:TEAM_MEMBER {status: 'active'}]->(t)
  }
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
RETURN task.id as task_id, a.claimed_by as claimed_by;

// ---------------------------------------------------------------------------
// OPERATION: Record team message
// ---------------------------------------------------------------------------
// Records a message in the team audit trail
//
// Parameters:
//   $team_id, $from_agent, $to_agent, $message_type, $content, $payload, etc.
//
// Returns:
//   Created message ID

// Cypher:
CREATE (m:TeamMessage {
  id: randomUUID(),
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
RETURN m.id as message_id;

// ---------------------------------------------------------------------------
// OPERATION: Aggregate team results
// ---------------------------------------------------------------------------
// Creates aggregated result from completed team tasks
//
// Parameters:
//   $team_id, $parent_task_id, $task_ids, $aggregation_mode, etc.
//
// Returns:
//   Created result ID

// Cypher:
MATCH (t:AgentTeam {id: $team_id})
MATCH (parent:Task {id: $parent_task_id})
MATCH (task:Task)
WHERE task.id IN $task_ids
  AND task.status = 'completed'
WITH t, parent, collect(task) as tasks,
     avg(task.quality_score) as avg_quality,
     sum(task.completion_time_minutes) as total_time
CREATE (r:TeamResult {
  id: randomUUID(),
  team_id: $team_id,
  task_id: $parent_task_id,
  aggregated_at: datetime(),
  aggregation_mode: $aggregation_mode,
  aggregated_from: $task_ids,
  summary: $summary,
  deliverable: $deliverable,
  confidence: $confidence,
  quality_score: avg_quality,
  contributions: $contributions_map,
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
RETURN r.id as result_id;

// =============================================================================
// SECTION 6: INTEGRATION WITH EXISTING TASK DAG
// =============================================================================

// ---------------------------------------------------------------------------
// CONCEPT: Team Tasks in the DAG
// ---------------------------------------------------------------------------
//
// Team tasks participate in the existing Task DAG with these patterns:
//
// 1. Individual Tasks (existing):
//    (:Task)-[:DEPENDS_ON {type: 'blocks'}]->(:Task)
//
// 2. Team Tasks (new):
//    (:Task)-[:ASSIGNED_TO_TEAM]->(:AgentTeam)
//    The team tasks STILL participate in DEPENDS_ON relationships
//
// 3. Team Subgraph Pattern:
//    A team can own a subgraph of related tasks:
//    (:AgentTeam)-[:OWNS_SUBGRAPH]->(entry:Task)
//    (entry)-[:DEPENDS_ON]->(task2:Task)-[:DEPENDS_ON]->(task3:Task)
//    All tasks in subgraph are assigned to same team
//
// 4. Cross-Team Dependencies:
//    (team1_task:Task)-[:ASSIGNED_TO_TEAM]->(:AgentTeam {id: 'team1'})
//    (team2_task:Task)-[:ASSIGNED_TO_TEAM]->(:AgentTeam {id: 'team2'})
//    (team2_task)-[:DEPENDS_ON {type: 'blocks'}]->(team1_task)
//    // team2_task waits for team1_task regardless of team assignment

// ---------------------------------------------------------------------------
// QUERY: Get team subgraph entry points
// ---------------------------------------------------------------------------
// Returns tasks that are entry points to team-owned subgraphs
//
// Parameters:
//   $team_id - The team ID
//
// Returns:
//   Entry point tasks with dependency counts

// Cypher:
MATCH (t:AgentTeam {id: $team_id})-[:OWNS_SUBGRAPH]->(entry:Task)
OPTIONAL MATCH (entry)<-[in_dep:DEPENDS_ON]-(dep:Task)
OPTIONAL MATCH (entry)-[out_dep:DEPENDS_ON]->(dep_task:Task)
RETURN
  entry.id as task_id,
  entry.description as description,
  entry.status as status,
  count(DISTINCT in_dep) as incoming_deps,
  count(DISTINCT out_dep) as outgoing_deps,
  collect(DISTINCT dep_task.id) as dependent_tasks;

// ---------------------------------------------------------------------------
// QUERY: Topological execution with team awareness
// ---------------------------------------------------------------------------
// Returns ready tasks considering both individual and team assignments
//
// This query extends the existing topological executor to handle team tasks
//
// Parameters:
//   $sender_hash - Optional sender isolation
//
// Returns:
//   Ready tasks with assignment info

// Cypher (ready tasks - individual):
MATCH (task:Task)
WHERE task.status = 'pending'
  AND ($sender_hash IS NULL OR task.sender_hash = $sender_hash)
  AND NOT EXISTS {
    // No unmet BLOCKS dependencies
    MATCH (task)<-[:DEPENDS_ON {type: 'blocks'}]-(blocker:Task)
    WHERE blocker.status <> 'completed'
  }
  AND NOT EXISTS {
    // Not assigned to a team
    MATCH (task)-[:ASSIGNED_TO_TEAM]->(:AgentTeam)
  }
RETURN
  task.id as task_id,
  task.description as description,
  'individual' as assignment_type,
  task.assigned_to as assigned_agent,
  task.priority_weight as priority
ORDER BY task.priority_weight DESC, task.created_at ASC;

// Cypher (ready tasks - team):
MATCH (task:Task)-[a:ASSIGNED_TO_TEAM {team_status: 'pending'}]->(t:AgentTeam)
WHERE task.status = 'pending'
  AND ($sender_hash IS NULL OR task.sender_hash = $sender_hash)
  AND NOT EXISTS {
    MATCH (task)<-[:DEPENDS_ON {type: 'blocks'}]-(blocker:Task)
    WHERE blocker.status <> 'completed'
  }
  AND t.status = 'active'
RETURN
  task.id as task_id,
  task.description as description,
  'team' as assignment_type,
  t.id as team_id,
  t.name as team_name,
  t.lead_agent_id as lead_agent,
  task.priority_weight as priority
ORDER BY task.priority_weight DESC, task.created_at ASC;

// ---------------------------------------------------------------------------
// QUERY: Get all tasks in team subgraph
// ---------------------------------------------------------------------------
// Returns all tasks reachable from team's entry point
//
// Parameters:
//   $team_id - The team ID
//
// Returns:
//   All tasks in the team's subgraph

// Cypher:
MATCH (t:AgentTeam {id: $team_id})-[:OWNS_SUBGRAPH]->(entry:Task)
CALL apoc.path.subgraphNodes(entry, {
  relationshipFilter: 'DEPENDS_ON>',
  labelFilter: 'Task',
  minLevel: 0
}) YIELD node
WITH entry, collect(node) as subgraph_tasks
UNWIND subgraph_tasks as task
RETURN
  task.id as task_id,
  task.description as description,
  task.status as status,
  task.priority_weight as priority,
  task.id = entry.id as is_entry_point;

// =============================================================================
// SECTION 7: RETENTION AND CLEANUP
// =============================================================================

// ---------------------------------------------------------------------------
// OPERATION: Purge old team lifecycle events
// ---------------------------------------------------------------------------
// Removes lifecycle events past their retention date
//
// Parameters:
//   $batch_size - Maximum events to delete per run
//
// Returns:
//   Number of events deleted

// Cypher:
MATCH (e:TeamLifecycleEvent)
WHERE e.retained_until < datetime()
WITH e LIMIT $batch_size
DETACH DELETE e
RETURN count(e) as deleted_count;

// ---------------------------------------------------------------------------
// OPERATION: Archive destroyed teams
// ---------------------------------------------------------------------------
// Moves destroyed team data to archive (optional cold storage)
//
// Parameters:
//   $older_than_days - Only archive teams destroyed before this
//
// Returns:
//   Number of teams archived

// Cypher:
MATCH (t:AgentTeam)
WHERE t.status = 'destroyed'
  AND t.destroyed_at < datetime() - duration({days: $older_than_days})
OPTIONAL MATCH (t)<-[:TEAM_MEMBER]-(member:Agent)
OPTIONAL MATCH (t)<-[a:ASSIGNED_TO_TEAM]-(task:Task)
CREATE (archive:ArchivedTeam {
  original_id: t.id,
  name: t.name,
  mission: t.mission,
  domain: t.domain,
  lead_agent_id: t.lead_agent_id,
  member_count: t.member_count,
  created_at: t.created_at,
  destroyed_at: t.destroyed_at,
  destroy_reason: t.destroy_reason,
  archived_at: datetime(),
  member_ids: collect(DISTINCT member.id),
  task_count: count(DISTINCT task)
})
WITH t, archive
DETACH DELETE t
RETURN count(archive) as archived_count;

// =============================================================================
// END OF SCHEMA EXTENSIONS
// =============================================================================
