# Neo4j Cross-Agent Memory Patterns

## Schema Overview

### Node Types
- **Agent** - Represents an AI agent in the Kurultai
- **Task** - Represents a task assigned to an agent
- **Memory** - Operational memory entry
- **Decision** - Routing or strategic decision
- **Escalation** - Critical issue requiring attention
- **Proposal** - A proposal for action requiring unanimous vote
- **Vote** - An agent's vote on a proposal

### Relationships
- **ASSIGNED_TO** - Task → Agent
- **DEPENDS_ON** - Task → Task
- **FED_INTO** - Agent → Agent
- **LOGGED** - Agent → Memory
- **TRIGGERED** - Event → Escalation
- **PROPOSED** - Agent → Proposal
- **VOTED_ON** - Agent → Vote
- **FOR_PROPOSAL** - Vote → Proposal
- **IMPLEMENTED_BY** - Proposal → Task

## Common Queries

### 1. Get Current Agent Status
```cypher
MATCH (a:Agent)
RETURN a.name, a.status, a.current_task, a.last_heartbeat
ORDER BY a.last_heartbeat DESC
```

### 2. Get Pending Tasks for Routing
```cypher
MATCH (t:Task {status: 'pending'})
RETURN t.id, t.type, t.priority, t.payload, t.created_at
ORDER BY t.priority DESC, t.created_at ASC
```

### 3. Get Agent's Recent Context
```cypher
MATCH (a:Agent {name: $agent_name})-[:LOGGED]->(m:Memory)
WHERE m.timestamp > datetime() - duration('P7D')
RETURN m.content, m.entry_type, m.timestamp
ORDER BY m.timestamp DESC
LIMIT 20
```

### 4. Get Cross-Agent Dependencies
```cypher
MATCH (source:Agent)-[:FED_INTO]->(target:Agent)
RETURN source.name, target.name, source.output_type
```

### 5. Get Task Chain
```cypher
MATCH path = (start:Task)-[:DEPENDS_ON*]->(end:Task)
WHERE start.id = $task_id
RETURN [node in nodes(path) | node.id] as dependency_chain
```

### 6. Log New Memory Entry
```cypher
CREATE (m:Memory {
  id: $memory_id,
  agent: $agent_name,
  content: $content,
  entry_type: $entry_type,
  contains_human_pii: $has_pii,
  timestamp: datetime()
})
WITH m
MATCH (a:Agent {name: $agent_name})
CREATE (a)-[:LOGGED]->(m)
RETURN m
```

### 7. Create Task Assignment
```cypher
CREATE (t:Task {
  id: $task_id,
  type: $task_type,
  description: $description,
  priority: $priority,
  status: 'pending',
  created_at: datetime(),
  created_by: $creator
})
WITH t
MATCH (a:Agent {name: $assigned_to})
CREATE (t)-[:ASSIGNED_TO]->(a)
RETURN t
```

### 8. Update Task Status
```cypher
MATCH (t:Task {id: $task_id})
SET t.status = $status,
    t.completed_at = CASE WHEN $status = 'completed' THEN datetime() ELSE t.completed_at END,
    t.result = $result
RETURN t
```

### 9. Get Escalation Events
```cypher
MATCH (e:EscalationEvent)
WHERE e.acknowledged = false
RETURN e.timestamp, e.trigger, e.affected_agents, e.severity
ORDER BY e.timestamp DESC
```

### 10. Full-Text Search on Decisions
```cypher
CALL db.index.fulltext.queryNodes('kublai_decisions', $search_term)
YIELD node, score
RETURN node.content, score
ORDER BY score DESC
LIMIT 10
```

---

## Proposal and Vote Pattern

### Purpose
Enable democratic decision-making across all Kurultai agents. Proposals require unanimous 6/6 YES approval to trigger implementation.

### Schema

#### Proposal Node
```cypher
(:Proposal {
    proposal_id: "uuid-12chars",
    title: "Add X to health check",
    description: "Full proposal text",
    proposing_agent: "ogedei",
    created_at: datetime(),
    expires_at: datetime(),
    status: "pending",
    priority: "high",
    category: "reliability",
    implementation_tasks: [],
    vote_summary: {
        yes_count: 1,
        no_count: 0,
        abstain_count: 0,
        total_votes: 1,
        unanimous: false
    },
    reflection_cycle: "2026-03-08-0300"
})
```

#### Vote Node
```cypher
(:Vote {
    vote_id: "uuid-12chars",
    proposal_id: "ref-to-proposal",
    agent: "temujin",
    decision: "yes",
    reasoning: "Agrees with approach",
    voted_at: datetime(),
    updated_at: datetime(),
    reflection_cycle: "2026-03-08-0300"
})
```

#### Relationships
```cypher
(:Agent)-[:PROPOSED {at: datetime()}]->(:Proposal)
(:Agent)-[:VOTED_ON {at: datetime()}]->(:Vote)
(:Vote)-[:FOR_PROPOSAL]->(:Proposal)
(:Proposal)-[:IMPLEMENTED_BY]->(:Task)
```

### Key Queries

#### Find unanimous proposals (6/6 YES)
```cypher
MATCH (p:Proposal {status: 'pending'})
OPTIONAL MATCH (p)<-[:FOR_PROPOSAL]-(v:Vote)
WITH p,
    count(v) AS total,
    sum(CASE WHEN v.decision = 'yes' THEN 1 ELSE 0 END) AS yes,
    sum(CASE WHEN v.decision = 'no' THEN 1 ELSE 0 END) AS no
WHERE total = 6 AND no = 0
RETURN p.proposal_id, p.title, p.category, yes
```

#### Get vote summary for a proposal
```cypher
MATCH (p:Proposal {proposal_id: $proposal_id})
OPTIONAL MATCH (p)<-[:FOR_PROPOSAL]-(v:Vote)
RETURN p.title,
    p.vote_summary,
    collect({agent: v.agent, decision: v.decision, reasoning: v.reasoning}) AS votes
```

#### Find expired proposals
```cypher
MATCH (p:Proposal {status: 'pending'})
WHERE p.expires_at < datetime()
RETURN p.proposal_id, p.title, p.expires_at
```

#### Get pending proposals needing my vote
```cypher
MATCH (p:Proposal {status: 'pending'})
WHERE NOT (p)<-[:FOR_PROPOSAL]-(:Vote {agent: $my_agent})
RETURN p.proposal_id, p.title, p.priority, p.expires_at
ORDER BY p.priority DESC, p.created_at ASC
```

#### Get proposal implementation tasks
```cypher
MATCH (p:Proposal {proposal_id: $proposal_id})-[:IMPLEMENTED_BY]->(t:Task)
RETURN t.task_id, t.status, t.assigned_to
```

#### Create a new proposal
```cypher
MATCH (a:Agent {name: $agent})
CREATE (p:Proposal {
    proposal_id: $proposal_id,
    title: $title,
    description: $description,
    proposing_agent: $agent,
    created_at: datetime(),
    expires_at: datetime() + duration('P24H'),
    status: 'pending',
    priority: $priority,
    category: $category,
    implementation_tasks: [],
    vote_summary: {yes_count: 0, no_count: 0, abstain_count: 0, total_votes: 0, unanimous: false},
    reflection_cycle: $cycle
})
CREATE (a)-[:PROPOSED {at: datetime()}]->(p)
RETURN p
```

#### Cast a vote on a proposal
```cypher
// First, delete existing vote from this agent
MATCH (v:Vote {proposal_id: $proposal_id, agent: $agent})
DETACH DELETE v

// Create new vote
MATCH (p:Proposal {proposal_id: $proposal_id})
MATCH (a:Agent {name: $agent})
CREATE (a)-[:VOTED_ON {at: datetime()}]->(v:Vote {
    vote_id: $vote_id,
    proposal_id: $proposal_id,
    agent: $agent,
    decision: $decision,
    reasoning: $reasoning,
    voted_at: datetime(),
    updated_at: datetime(),
    reflection_cycle: $cycle
})
CREATE (v)-[:FOR_PROPOSAL]->(p)

// Update vote summary cache
WITH p
OPTIONAL MATCH (p)<-[:FOR_PROPOSAL]-(v2:Vote)
WITH p,
    count(v2) AS total,
    sum(CASE WHEN v2.decision = 'yes' THEN 1 ELSE 0 END) AS yes,
    sum(CASE WHEN v2.decision = 'no' THEN 1 ELSE 0 END) AS no,
    sum(CASE WHEN v2.decision = 'abstain' THEN 1 ELSE 0 END) AS abstain
SET p.vote_summary = {
    yes_count: coalesce(yes, 0),
    no_count: coalesce(no, 0),
    abstain_count: coalesce(abstain, 0),
    total_votes: total,
    unanimous: (total = 6 AND coalesce(no, 0) = 0)
}
RETURN v
```

### Scripts
- `proposal_manager.py` - Proposal CRUD operations
- `vote_manager.py` - Vote casting and aggregation
- `proposal_expiration.py` - Expire stale proposals
- `proposal_approval_handler.py` - Process approved proposals

### Constraints
```cypher
CREATE CONSTRAINT proposal_id_unique IF NOT EXISTS
FOR (p:Proposal) REQUIRE p.proposal_id IS UNIQUE

CREATE CONSTRAINT vote_id_unique IF NOT EXISTS
FOR (v:Vote) REQUIRE v.vote_id IS UNIQUE
```

### Indexes
```cypher
CREATE INDEX proposal_status_idx IF NOT EXISTS
FOR (p:Proposal) WHERE p.status IS NOT NULL

CREATE INDEX proposal_expires_at_idx IF NOT EXISTS
FOR (p:Proposal) WHERE p.expires_at IS NOT NULL

CREATE INDEX proposal_category_idx IF NOT EXISTS
FOR (p:Proposal) WHERE p.category IS NOT NULL

CREATE INDEX vote_proposal_idx IF NOT EXISTS
FOR (v:Vote) WHERE v.proposal_id IS NOT NULL

CREATE INDEX vote_agent_idx IF NOT EXISTS
FOR (v:Vote) WHERE v.agent IS NOT NULL
```

---

## Privacy Rules

**NEVER store in Neo4j:**
- Human names, emails, phone numbers
- API keys, passwords, tokens
- Personal health information
- Financial account details
- Private communications

**ALWAYS store in Neo4j:**
- Task routing decisions
- Agent status and metrics
- Operational patterns
- Shared beliefs/philosophy
- Non-PII workflow data
- Proposals and votes

## Write Decision Flow

```
Creating memory entry
    ↓
Does it contain human PII or sensitive data?
    ↓ YES → File ONLY (never Neo4j)
    ↓ NO → Neo4j FIRST (then file backup)
```

## Maintenance Queries

### Archive Old Memory
```cypher
MATCH (m:Memory)
WHERE m.timestamp < datetime() - duration('P30D')
SET m.archived = true
```

### Clean Up Completed Tasks
```cypher
MATCH (t:Task)
WHERE t.status = 'completed'
  AND t.completed_at < datetime() - duration('P7D')
DELETE t
```

### Get Agent Performance Metrics
```cypher
MATCH (a:Agent)<-[:ASSIGNED_TO]-(t:Task)
WHERE t.created_at > datetime() - duration('P7D')
RETURN a.name,
       count(CASE WHEN t.status = 'completed' THEN 1 END) as completed,
       count(CASE WHEN t.status = 'failed' THEN 1 END) as failed,
       avg(duration.between(t.created_at, t.completed_at).minutes) as avg_completion_time
```

### Archive Expired Proposals
```cypher
MATCH (p:Proposal {status: 'pending'})
WHERE p.expires_at < datetime()
SET p.status = 'expired'
RETURN count(p) as archived_count
```

---

## 🧠 Weighted Memory Patterns (Cognee-Inspired)

**Principle:** Frequently-accessed connections strengthen over time. Stale connections weaken and are pruned.

### Increment Edge Weight on Access
```cypher
// When a relationship is accessed, strengthen it
MATCH (a:Agent)-[r:ASSIGNED_TO]->(t:Task)
SET r.weight = COALESCE(r.weight, 1) + 1,
    r.last_accessed = datetime()
RETURN r.weight
```

### Decay Stale Edges (Weekly)
```cypher
// Weaken edges not accessed in 14 days
MATCH ()-[r]-()
WHERE r.last_accessed < datetime() - duration('P14D')
SET r.weight = r.weight * 0.5
RETURN count(r) as weakened_edges
```

### Query by Weight (Prioritize Strong Connections)
```cypher
// Get tasks for agent, prioritizing frequently-assigned types
MATCH (a:Agent {name: $agent_name})<-[r:ASSIGNED_TO]-(t:Task)
WHERE t.status = 'pending'
RETURN t, r.weight as priority
ORDER BY r.weight DESC, t.priority ASC
```

### Auto-Prune Orphaned Nodes (Monthly)
```cypher
// Delete nodes with no connections older than 30 days
MATCH (n)
WHERE NOT ()--(n)
  AND n.created_at < datetime() - duration('P30D')
DETACH DELETE n
RETURN count(n) as pruned_nodes
```

### Get Strongest Agent Relationships
```cypher
// Find which agents work together most often
MATCH (a1:Agent)-[r:FED_INTO]-(a2:Agent)
RETURN a1.name, a2.name, r.weight as collaboration_strength
ORDER BY r.weight DESC
LIMIT 10
```

### Memory Access Analytics
```cypher
// Track which memory entries are accessed most
MATCH (a:Agent)-[r:LOGGED]->(m:Memory)
WHERE r.last_accessed > datetime() - duration('P7D')
RETURN m.content, r.weight as access_count
ORDER BY r.weight DESC
LIMIT 20
```

---

## 📊 Weight Schema

| Relationship Type | Initial Weight | Decay Rate | Prune Threshold |
|------------------|----------------|------------|-----------------|
| **ASSIGNED_TO** | 1 | 0.5x per 14 days | <0.1 |
| **LOGGED** | 1 | 0.5x per 14 days | <0.1 |
| **DEPENDS_ON** | 1 | 0.5x per 30 days | <0.1 |
| **FED_INTO** | 1 | 0.5x per 14 days | <0.1 |
| **TRIGGERED** | 1 | 0.5x per 30 days | <0.1 |
| **PROPOSED** | 1 | 0.5x per 30 days | <0.1 |
| **VOTED_ON** | 1 | 0.5x per 14 days | <0.1 |
| **FOR_PROPOSAL** | 1 | 0.5x per 14 days | <0.1 |

---

## 🔧 Implementation Notes

### Weight Increment (On Every Access)
```typescript
export async function incrementEdgeWeight(
  fromNode: string,
  relationship: string,
  toNode: string
): Promise<number> {
  const result = await neo4j.query(`
    MATCH (a)-[r:${relationship}]->(b)
    WHERE a.id = $fromId AND b.id = $toId
    SET r.weight = COALESCE(r.weight, 1) + 1,
        r.last_accessed = datetime()
    RETURN r.weight
  `, { fromId: fromNode, toId: toNode })

  return result.records[0].get('r.weight')
}
```

### Weekly Decay (Cron Job)
```typescript
export async function decayStaleEdges(): Promise<number> {
  const result = await neo4j.query(`
    MATCH ()-[r]-()
    WHERE r.last_accessed < datetime() - duration('P14D')
    SET r.weight = r.weight * 0.5
    RETURN count(r) as weakened_edges
  `)

  return result.records[0].get('weakened_edges')
}
```

### Monthly Pruning (Cron Job)
```typescript
export async function pruneOrphanedNodes(): Promise<number> {
  const result = await neo4j.query(`
    MATCH (n)
    WHERE NOT ()--(n)
      AND n.created_at < datetime() - duration('P30D')
    DETACH DELETE n
    RETURN count(n) as pruned_nodes
  `)

  return result.records[0].get('pruned_nodes')
}
```

---

## 📈 Benefits of Weighted Memory

| Benefit | Impact |
|---------|--------|
| **Prioritized queries** | Frequently-accessed relationships returned first |
| **Auto-optimization** | System learns what matters through usage |
| **Stale data cleanup** | Old, unused connections automatically pruned |
| **Better routing** | Agent assignments based on historical success |
| **Faster search** | High-weight edges prioritized in traversal |

---

## 🧠 Schema Enhancements (v1.0 - 2026-03-08)

**Purpose:** Enable intelligent routing, self-improvement, observability, and knowledge management.

### New Node Types (17)

#### Routing Intelligence
| Node | Purpose | Key Properties |
|------|---------|----------------|
| **SkillAffinity** | Track agent skill proficiency | agent, skill, success_rate, avg_duration |
| **AgentCapacity** | Real-time workload metrics | queue_depth, throughput_1h, availability_score |
| **RoutingDecision** | Record routing choices | task_id, from_agent, to_agent, reason, confidence |
| **TaskComplexity** | Estimate task difficulty | estimated_effort, actual_effort, complexity_factors |

#### Self-Improvement
| Node | Purpose | Key Properties |
|------|---------|----------------|
| **ReflectionInsight** | Hourly reflection insights | insight_type, description, impact_score |
| **FailurePattern** | Cluster similar failures | error_signature, root_cause, resolution |
| **SkillEvolution** | Track skill improvement | proficiency_level, current_performance |
| **LearningEvent** | Discrete learning moments | event_type, lesson, confidence |

#### Observability
| Node | Purpose | Key Properties |
|------|---------|----------------|
| **PerformanceMetric** | Time-series metrics (hourly) | metric_name, value, trend, hour |
| **DependencyGraph** | Component relationships | health_status, latency_ms |
| **Bottleneck** | Detected bottlenecks | location, cause, impact_score, resolved |
| **SystemEvent** | Non-pipeline events | type, severity, message, resolved |

#### Knowledge & Quality
| Node | Purpose | Key Properties |
|------|---------|----------------|
| **KnowledgeArtifact** | Reusable knowledge | content_hash, freshness_score, usage_count |
| **ContextChain** | Session context chains | session_id, decision_points, outcomes_summary |
| **LessonLearned** | Cross-agent learning | situation, action_taken, generalization |
| **QualityGate** | Verification checkpoints | checkpoint_name, passed, reviewer |
| **TechnicalDebt** | Debt tracking | location, impact, priority, resolved |

### New Relationships (24)

```cypher
// Routing Intelligence
(a:Agent)-[:HAS_SKILL_AFFINITY]->(s:SkillAffinity)
(a:Agent)-[:HAS_CAPACITY]->(c:AgentCapacity)
(t:Task)-[:ROUTED_BY]->(r:RoutingDecision)
(r:RoutingDecision)-[:ROUTED_TO]->(a:Agent)
(t:Task)-[:HAS_COMPLEXITY]->(c:TaskComplexity)

// Self-Improvement
(a:Agent)-[:HAS_INSIGHT]->(r:ReflectionInsight)
(r:ReflectionInsight)-[:GENERATED_RULE]->(ru:Rule)
(f:FailurePattern)-[:MATCHES]->(t:Task)
(a:Agent)-[:HAS_SKILL_EVO]->(s:SkillEvolution)
(l:LearningEvent)-[:DERIVED_FROM]->(t:Task)
(l:LearningEvent)-[:VALIDATED_BY]->(a:Agent)

// Observability
(a:Agent)-[:HAS_METRIC]->(m:PerformanceMetric)
(m:PerformanceMetric)-[:PRECEDES]->(m2:PerformanceMetric)
(d:DependencyGraph)-[:AFFECTS]->(a:Agent)
(b:Bottleneck)-[:LOCATED_AT]->(d:DependencyGraph)
(b:Bottleneck)-[:AFFECTS_AGENT]->(a:Agent)
(e:SystemEvent)-[:TRIGGERED_BY]->(d:DependencyGraph)

// Knowledge & Quality
(a:Agent)-[:CREATED_ARTIFACT]->(k:KnowledgeArtifact)
(k:KnowledgeArtifact)-[:USED_IN]->(t:Task)
(c:ContextChain)-[:INCLUDES]->(t:Task)
(l:LessonLearned)-[:APPLIES_TO]->(a:Agent)
(q:QualityGate)-[:VALIDATES]->(t:Task)
(t:TechnicalDebt)-[:CREATED_BY]->(t2:Task)
```

### Key Queries

#### Best Agent for Skill (Routing Intelligence)
```cypher
MATCH (a:Agent)-[:HAS_SKILL_AFFINITY]->(s:SkillAffinity {skill: $skill})
MATCH (c:AgentCapacity {agent: a.name})
WHERE s.success_rate > 0.5 AND c.availability_score > 0.3
RETURN a.name, s.success_rate, c.availability_score,
       s.success_rate * c.availability_score AS routing_score
ORDER BY routing_score DESC LIMIT 3
```

#### Active Bottlenecks
```cypher
MATCH (b:Bottleneck)
WHERE b.resolved = false
RETURN b.location, b.cause, b.impact_score, b.affected_agents
ORDER BY b.impact_score DESC LIMIT 9
```

#### Unapplied High-Impact Insights
```cypher
MATCH (r:ReflectionInsight)
WHERE r.applied = false AND r.impact_score >= 7
RETURN r.agent, r.insight_type, r.description, r.impact_score
ORDER BY r.impact_score DESC, r.timestamp DESC LIMIT 9
```

#### Search Knowledge Artifacts
```cypher
CALL db.index.fulltext.queryNodes('knowledge_search', $query)
YIELD node, score
WHERE node.freshness_score > 0.3
RETURN node.type, node.content, node.keywords, score
ORDER BY score * node.freshness_score DESC LIMIT 9
```

### Integration Points

| Telemetry | Nodes | Frequency |
|-----------|-------|-----------|
| task-ledger.jsonl | Task, RoutingDecision, TaskComplexity | Per-task |
| watchdog-gather.sh | AgentCapacity, DependencyGraph, SystemEvent | 5 min |
| tock-gather.sh | PerformanceMetric | 30 min (hour boundary) |
| meta_reflection.py | ReflectionInsight, LessonLearned | Hourly |
| throughput_anomaly.py | Bottleneck | On anomaly |

### Lifecycle Management

```cypher
// Prune old metrics (30 days)
MATCH (m:PerformanceMetric)
WHERE m.created < datetime() - duration({days: 30})
DELETE m

// Decay knowledge freshness
MATCH (k:KnowledgeArtifact)
WHERE k.freshness_score > 0.1
SET k.freshness_score = k.freshness_score * 0.95

// Detect zombie tasks (2+ hours stuck)
MATCH (t:Task)
WHERE t.status IN ['EXECUTING', 'running']
  AND t.started < datetime() - duration({hours: 2})
SET t.status = 'TIMEOUT', t.zombie_detected = true
```

### Files

- **Schema:** `/agents/temujin/workspace/neo4j-schema-enhancements.cypher`
- **Queries:** `/agents/temujin/workspace/neo4j-schema-queries.md`
- **Integration:** `/agents/temujin/workspace/neo4j_schema_integration.py`
- **Design:** `/agents/temujin/workspace/neo4j-schema-brainstorm-report.md`
