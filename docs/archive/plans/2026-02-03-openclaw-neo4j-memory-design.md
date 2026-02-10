# OpenClaw Neo4j Memory System Design

> **Status**: Ready for Implementation
> **Date**: 2026-02-03
> **Author**: Brainstorming session with senior-architect, senior-data-engineer skills

## Executive Summary

This design replaces OpenClaw's file-based memory system (MEMORY.md, memory/*.md, HEARTBEAT.md) with a Neo4j graph database that enables:

- **Structured knowledge** with relationships and provenance
- **Cross-agent learning** through a shared knowledge pool
- **Self-reflection cycles** adapted from BYRD's architecture
- **Graph algorithms** for intelligent context retrieval
- **Peer-to-peer collaboration** between all 6 agents

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [The 6 Agents](#the-6-agents)
3. [Neo4j Schema](#neo4j-schema)
4. [Tiered Connection Model](#tiered-connection-model)
5. [Knowledge Flow Patterns](#knowledge-flow-patterns)
6. [Kublai Approval Gate](#kublai-approval-gate)
7. [Deployment Architecture](#deployment-architecture)
8. [Implementation Plan](#implementation-plan)

---

## Architecture Overview

### What's Being Replaced

| OpenClaw File | Replacement | Rationale |
|---------------|-------------|-----------|
| MEMORY.md | Belief nodes | Structured, queryable, confidence-tracked |
| memory/YYYY-MM-DD.md | Experience/Event nodes | Timestamped, relationship-linked |
| HEARTBEAT.md | Dynamic graph queries | Intelligent, context-aware checklist |
| IDENTITY.md | AgentState node | Emergent personality tracking |

### What's Being Kept (Static Config)

- SOUL.md - Persona boundaries (loaded at session start)
- USER.md - User identity
- AGENTS.md - Operating instructions
- TOOLS.md - Tool reference

### Hybrid Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  HYBRID MEMORY ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  FILES (Static)              NEO4J (Dynamic Knowledge)          │
│  ─────────────               ─────────────────────────          │
│  SOUL.md ──────────────────► (loaded at session start)          │
│  USER.md                                                         │
│  AGENTS.md                   ┌──────────────────────┐           │
│  TOOLS.md                    │   GRAPH DATABASE     │           │
│                              │                      │           │
│  (retired) MEMORY.md ───────►│  Beliefs, Concepts   │           │
│  (retired) memory/*.md ─────►│  Experiences, Events │           │
│  (retired) HEARTBEAT.md ────►│  Dynamic Queries     │           │
│                              │  Cross-Agent Pool    │           │
│                              └──────────────────────┘           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## The 6 Agents

| Agent | ID | Role | Primary Capabilities |
|-------|-----|------|---------------------|
| **Kublai** | main | Squad Lead | Orchestration, synthesis, quality gate, human interface |
| **Möngke** | researcher | Deep Researcher | Evidence gathering, citations, competitive analysis |
| **Chagatai** | writer | Content Writer | Content creation, editing, voice adaptation |
| **Temüjin** | developer | Developer | Code, security audits, automation, technical debt |
| **Jochi** | analyst | Analyst/Strategist | Patterns, metrics, SEO, opportunity identification |
| **Ögedei** | ops | Operations | Process management, documentation, deadlines |

### Agent Definitions

```cypher
// Kublai - Squad Lead & Orchestrator
CREATE (:Agent {
  id: "kublai",
  name: "Kublai",
  role: "orchestrator",
  primary_capabilities: ["coordination", "delegation", "quality_review",
                         "human_interface", "synthesis", "blocker_resolution"],
  personality: "Diplomatic, strategic, sees the big picture",
  output_types: ["ProcessInsight", "Synthesis", "Task"],
  input_types: ["all"],
  heartbeat_schedule: ":00"
})

// Möngke - Deep Researcher
CREATE (:Agent {
  id: "mongke",
  name: "Möngke",
  role: "researcher",
  primary_capabilities: ["deep_research", "citation_tracking",
                         "competitive_analysis", "market_research", "evidence_gathering"],
  personality: "Skeptical, thorough, evidence-based. Patient scholar.",
  output_types: ["Research", "Concept"],
  input_types: ["Task", "Insight"],
  heartbeat_schedule: ":03",
  daily_minimum: "3 research briefs"
})

// Chagatai - Content Writer
CREATE (:Agent {
  id: "chagatai",
  name: "Chagatai",
  role: "writer",
  primary_capabilities: ["content_writing", "editing", "polishing",
                         "voice_adaptation", "community_content"],
  personality: "Generous with feedback, meticulous with prose",
  output_types: ["Content"],
  input_types: ["Research"],
  heartbeat_schedule: ":06",
  daily_minimum: "1 polished piece OR 3 drafts"
})

// Temüjin - Developer & Security Guardian
CREATE (:Agent {
  id: "temujin",
  name: "Temüjin",
  role: "developer",
  primary_capabilities: ["code_implementation", "security_review", "automation",
                         "technical_debt", "bug_fixing", "dependency_audit"],
  personality: "Security-conscious, builds for generations",
  output_types: ["Application", "SecurityAudit", "CodeReview"],
  input_types: ["Concept", "Content", "Task"],
  heartbeat_schedule: ":09",
  weekly_minimum: "1 security audit + 3-5 enhancements"
})

// Jochi - Analyst & Strategist
CREATE (:Agent {
  id: "jochi",
  name: "Jochi",
  role: "analyst",
  primary_capabilities: ["pattern_recognition", "metrics_tracking", "seo_monitoring",
                         "competitive_intelligence", "opportunity_identification",
                         "strategic_analysis"],
  personality: "Independent thinker who sees what others miss",
  output_types: ["Analysis", "Insight", "Opportunity"],
  input_types: ["Research", "Application", "Content"],
  heartbeat_schedule: ":12"
})

// Ögedei - Operations & Admin
CREATE (:Agent {
  id: "ogedei",
  name: "Ögedei",
  role: "ops",
  primary_capabilities: ["task_management", "documentation", "deadline_tracking",
                         "workflow_optimization", "process_maintenance", "admin_handling"],
  personality: "Strict adherent to process and protocol",
  output_types: ["ProcessUpdate", "Documentation", "WorkflowImprovement"],
  input_types: ["all"],
  heartbeat_schedule: ":15"
})
```

---

## Neo4j Schema

### Core Node Types

#### Entity Nodes (Anchors)

```cypher
(:Entity {
  id: UUID,
  name: string,
  type: string,  // "user", "system", "api", "codebase", "tool", "domain"
  first_seen: datetime,
  last_seen: datetime
})

(:Concept {
  id: UUID,
  name: string,
  domain: string,
  description: string,
  embedding: [float],  // 384-dim vector for semantic search
  confidence: float,
  source: "research" | "application" | "synthesis" | "user",
  created_at: datetime,
  updated_at: datetime
})

(:Agent {
  id: string,
  name: string,
  role: string,
  primary_capabilities: [string],
  personality: string,
  output_types: [string],
  input_types: [string],
  heartbeat_schedule: string,
  state: "active" | "idle",
  last_active: datetime,
  created_at: datetime
})
```

#### Event Nodes

```cypher
(:Event {
  id: UUID,
  description: string,
  type: string,
  agent: string,
  outcome: "success" | "partial" | "failed",
  timestamp: datetime,
  resolved: boolean
})

(:Task {
  id: UUID,
  type: "research" | "writing" | "application" | "orchestration" | "analysis" | "ops",
  description: string,
  status: "pending" | "in_progress" | "completed" | "blocked",
  outcome: "success" | "partial" | "failed",
  requested_by: string,
  assigned_to: string,
  delegated_by: string,
  quality_score: float,
  created_at: datetime,
  started_at: datetime,
  completed_at: datetime
})
```

#### Knowledge Nodes (By Agent Specialty)

```cypher
// Möngke's output
(:Research {
  id: UUID,
  topic: string,
  findings: string,
  sources: [string],
  confidence: float,
  depth: "surface" | "moderate" | "deep",
  novelty: float,
  agent: "mongke",
  task_id: UUID,
  created_at: datetime
})

// Chagatai's output
(:Content {
  id: UUID,
  type: "article" | "summary" | "documentation" | "report",
  title: string,
  body: string,
  clarity_score: float,
  completeness: float,
  agent: "chagatai",
  task_id: UUID,
  created_at: datetime
})

// Temüjin's outputs
(:Application {
  id: UUID,
  concept_applied: UUID,
  context: string,
  success: boolean,
  result: string,
  lessons_learned: string,
  agent: "temujin",
  task_id: UUID,
  created_at: datetime
})

(:SecurityAudit {
  id: UUID,
  scope: string,
  vulnerabilities: JSON,  // [{severity, description, location, remediation}]
  overall_risk: "critical" | "high" | "medium" | "low" | "secure",
  recommendations: [string],
  agent: "temujin",
  task_id: UUID,
  created_at: datetime
})

(:CodeReview {
  id: UUID,
  target: string,
  issues: JSON,  // [{type, severity, description, suggestion}]
  enhancements: [string],
  automation_opportunities: [string],
  agent: "temujin",
  task_id: UUID,
  created_at: datetime
})

// Jochi's outputs
(:Analysis {
  id: UUID,
  type: "pattern" | "metric" | "competitive" | "opportunity" | "risk",
  title: string,
  findings: string,
  data_sources: [string],
  metrics: JSON,
  trends: JSON,
  opportunities: [string],
  risks: [string],
  recommendations: [string],
  confidence: float,
  agent: "jochi",
  task_id: UUID,
  created_at: datetime
})

(:Insight {
  id: UUID,
  insight: string,
  category: "market" | "competitive" | "technical" | "process" | "opportunity",
  based_on: [UUID],
  potential_value: "high" | "medium" | "low",
  urgency: "immediate" | "soon" | "eventual",
  relevant_to: [string],
  confidence: float,
  agent: "jochi",
  created_at: datetime
})

(:Opportunity {
  id: UUID,
  description: string,
  category: "content" | "technical" | "market" | "process",
  potential_impact: float,
  effort_estimate: "low" | "medium" | "high",
  confidence: float,
  recommended_agent: string,
  suggested_approach: string,
  status: "identified" | "assigned" | "in_progress" | "captured" | "passed",
  agent: "jochi",
  created_at: datetime
})

// Ögedei's outputs
(:ProcessUpdate {
  id: UUID,
  type: "status" | "blocker" | "completion" | "handoff",
  entity_type: string,
  entity_id: UUID,
  previous_state: string,
  new_state: string,
  notes: string,
  blockers: [string],
  agent: "ogedei",
  created_at: datetime
})

(:Documentation {
  id: UUID,
  type: "process" | "reference" | "guide" | "changelog",
  title: string,
  content: string,
  documents: [UUID],
  last_verified: datetime,
  needs_update: boolean,
  agent: "ogedei",
  created_at: datetime,
  updated_at: datetime
})

(:WorkflowImprovement {
  id: UUID,
  target_process: string,
  current_state: string,
  proposed_state: string,
  based_on_analysis: [UUID],
  metrics_before: JSON,
  projected_metrics: JSON,
  implementation_steps: [string],
  effort_estimate: "low" | "medium" | "high",
  risk_level: "low" | "medium" | "high",
  // Status with Kublai approval gate
  status: "proposed" | "pending_approval" | "approved" | "rejected" |
          "implementing" | "measuring" | "complete",
  proposed_by: string,
  co_created_with: string,
  // Kublai approval fields
  submitted_for_approval: datetime,
  reviewed_by: "kublai",
  review_decision: "approved" | "rejected" | "needs_revision",
  review_notes: string,
  reviewed_at: datetime,
  agent: "ogedei",
  created_at: datetime
})

// Kublai's output
(:Synthesis {
  id: UUID,
  insight: string,
  summary: string,
  research_ids: [UUID],
  content_ids: [UUID],
  application_ids: [UUID],
  novelty_type: "combination" | "refinement" | "correction" |
                "extension" | "contradiction_resolution",
  domains: [string],
  confidence: float,
  validated: boolean,
  validation_method: string,
  concepts_created: [UUID],
  concepts_updated: [UUID],
  created_by: "kublai",
  created_at: datetime,
  synthesis_trigger: string
})

(:ProcessInsight {
  id: UUID,
  insight: string,
  category: "delegation" | "timing" | "quality" | "handoff" | "synthesis",
  based_on_tasks: [UUID],
  confidence: float,
  agent: "kublai",
  created_at: datetime
})

(:ProcessPattern {
  id: UUID,
  pattern_type: "delegation" | "handoff" | "feedback" | "synthesis",
  description: string,
  sequence: [string],
  conditions: JSON,
  success_rate: float,
  avg_quality: float,
  sample_size: int,
  created_at: datetime,
  updated_at: datetime
})
```

#### Reflection Nodes (Self-Awareness)

```cypher
(:Reflection {
  id: UUID,
  content: string,
  agent: string,
  trigger: string,
  beliefs_formed: [UUID],
  insights_gained: [string],
  created_at: datetime
})

(:Belief {
  id: UUID,
  content: string,
  confidence: float,
  strength: float,
  agent: string | "shared",
  domain: string,
  source_type: "reflection" | "experience" | "synthesis" | "user",
  source_id: UUID,
  state: "active" | "superseded" | "archived",
  created_at: datetime,
  updated_at: datetime,
  last_accessed: datetime
})
```

#### Shared Knowledge Pool

```cypher
(:SharedKnowledge {
  id: UUID,
  knowledge_id: UUID,
  knowledge_type: string,
  shared_by: string,
  shared_at: datetime,
  min_confidence: float,
  accessed_by: [string],
  applied_by: [string]
})
```

### Relationships

```cypher
// Knowledge flow
(r:Research)-[:DISCOVERED]->(c:Concept)
(r:Research)-[:REFINED {changes: string}]->(c:Concept)
(c:Content)-[:SYNTHESIZES]->(r:Research)
(c:Content)-[:EXPLAINS]->(concept:Concept)
(a:Application)-[:VALIDATED]->(c:Concept)
(a:Application)-[:CHALLENGED {reason: string}]->(c:Concept)

// Synthesis relationships
(r:Research)-[:CONTRIBUTED_TO]->(s:Synthesis)
(c:Content)-[:CONTRIBUTED_TO]->(s:Synthesis)
(a:Application)-[:CONTRIBUTED_TO]->(s:Synthesis)
(s:Synthesis)-[:PRODUCED]->(c:Concept)
(s:Synthesis)-[:UPDATED {changes: string}]->(c:Concept)
(s1:Synthesis)-[:ENABLED]->(s2:Synthesis)

// Task flow
(parent:Task)-[:SPAWNED]->(child:Task)
(t:Task)-[:ASSIGNED_TO]->(a:Agent)
(t1:Task)-[:DEPENDS_ON]->(t2:Task)

// Agent relationships
(a1:Agent)-[:SUBSCRIBES_TO {
  knowledge_types: [string],
  domains: [string],
  min_confidence: float,
  notify_immediately: boolean,
  batch_interval: duration,
  tier: string
}]->(a2:Agent)

(a1:Agent)-[:LEARNED {
  knowledge_id: UUID,
  timestamp: datetime
}]->(a2:Agent)

// Approval relationships
(wi:WorkflowImprovement)-[:APPROVED_BY {
  decision: string,
  notes: string,
  conditions: [string],
  reviewed_at: datetime
}]->(kublai:Agent {id: "kublai"})

// Operations improvement loop
(ogedei:Agent)-[:IMPROVES_WITH {domain: "operations"}]->(jochi:Agent)
(jochi:Agent)-[:ANALYZES_FOR {domain: "process_metrics"}]->(ogedei:Agent)

// Belief evolution
(old:Belief)-[:EVOLVED_INTO {reason: string}]->(new:Belief)
(b1:Belief)-[:SUPPORTS]->(b2:Belief)
(b1:Belief)-[:CONTRADICTS]->(b2:Belief)
```

### Indexes for Performance

```cypher
// Composite indexes for common queries
CREATE INDEX agent_knowledge FOR (n) ON (n.agent, n.created_at)
  WHERE n:Research OR n:Content OR n:Application;

CREATE INDEX task_status FOR (t:Task) ON (t.assigned_to, t.status);

CREATE INDEX belief_retrieval FOR (b:Belief)
  ON (b.agent, b.domain, b.state, b.confidence);

// Full-text search
CREATE FULLTEXT INDEX knowledge_content
  FOR (n:Research|Content|Concept|Belief) ON EACH [n.content, n.findings, n.description];

// Vector index for semantic search
CREATE VECTOR INDEX concept_embedding FOR (c:Concept)
  ON c.embedding OPTIONS {indexConfig: {
    `vector.dimensions`: 384,
    `vector.similarity_function`: 'cosine'
  }};
```

---

## Tiered Connection Model

### Tier 1: Direct Connections (Push - Immediate)

High-bandwidth relationships with immediate notifications.

```
Jochi ══► Möngke     (research priorities - insights drive research)
Jochi ◄══► Ögedei    (ops improvement loop - bidirectional)
Möngke ══► Chagatai  (content source - research feeds writing)
Ögedei ◄══► Temüjin  (implementation handoffs)
All ══► Kublai       (quality gate, synthesis, approvals)
```

### Tier 2: Shared Pool (Pull - On Demand)

Any agent can query any other agent's knowledge.

- High-confidence knowledge auto-shares to pool
- Any agent queries pool when working on a task
- Graph traversal finds relevant cross-agent knowledge

### Tier 3: Broadcast (Push - Batched)

Important announcements go to everyone.

- Synthesis nodes (cross-agent insights)
- Security alerts (from Temüjin)
- Approved process changes (from Ögedei via Kublai)

### Default Subscriptions

```cypher
// Kublai - monitors everything
CREATE (:Subscription {
  subscriber: "kublai",
  source_agent: "all",
  knowledge_types: ["all"],
  min_confidence: 0.0,
  notify_immediately: false,
  batch_interval: duration('PT5M'),
  tier: "orchestrator"
})

// Möngke - research priorities from Jochi, feedback from Temüjin
CREATE (:Subscription {
  subscriber: "mongke",
  source_agent: "jochi",
  knowledge_types: ["Insight", "Opportunity", "Analysis"],
  min_confidence: 0.6,
  notify_immediately: true,
  tier: "direct"
})

CREATE (:Subscription {
  subscriber: "mongke",
  source_agent: "temujin",
  knowledge_types: ["Application"],
  min_confidence: 0.0,
  notify_immediately: true,
  tier: "direct"
})

// Chagatai - research from Möngke, content insights from Jochi
CREATE (:Subscription {
  subscriber: "chagatai",
  source_agent: "mongke",
  knowledge_types: ["Research"],
  min_confidence: 0.7,
  notify_immediately: true,
  tier: "direct"
})

CREATE (:Subscription {
  subscriber: "chagatai",
  source_agent: "jochi",
  knowledge_types: ["Insight", "Analysis"],
  domains: ["content", "seo", "engagement"],
  min_confidence: 0.7,
  notify_immediately: false,
  tier: "direct"
})

// Temüjin - concepts to implement, security insights
CREATE (:Subscription {
  subscriber: "temujin",
  source_agent: "all",
  knowledge_types: ["Concept", "Research"],
  domains: ["technical", "security", "automation"],
  min_confidence: 0.7,
  notify_immediately: true,
  tier: "pool"
})

CREATE (:Subscription {
  subscriber: "temujin",
  source_agent: "jochi",
  knowledge_types: ["Analysis", "Insight"],
  domains: ["security", "risk", "technical"],
  min_confidence: 0.6,
  notify_immediately: true,
  tier: "direct"
})

// Jochi - all outputs for pattern analysis
CREATE (:Subscription {
  subscriber: "jochi",
  source_agent: "all",
  knowledge_types: ["Research", "Content", "Application", "SecurityAudit", "Task"],
  min_confidence: 0.5,
  notify_immediately: false,
  batch_interval: duration('PT1H'),
  tier: "analyst"
})

// Ögedei - process events, direct from Jochi
CREATE (:Subscription {
  subscriber: "ogedei",
  source_agent: "jochi",
  knowledge_types: ["Analysis", "Insight"],
  domains: ["process", "workflow", "efficiency", "bottleneck"],
  min_confidence: 0.5,
  notify_immediately: true,
  tier: "direct"
})

CREATE (:Subscription {
  subscriber: "ogedei",
  source_agent: "all",
  knowledge_types: ["Task", "ProcessUpdate"],
  min_confidence: 0.0,
  notify_immediately: false,
  batch_interval: duration('PT15M'),
  tier: "ops"
})
```

---

## Knowledge Flow Patterns

### Cross-Agent Learning Flow

```
1. TEMÜJIN applies Möngke's research on "async patterns"
   └── Discovers edge case Möngke didn't document

2. TEMÜJIN creates new knowledge:
   └── Research: "Async patterns fail under memory pressure"
   └── Concept: "memory-aware-async"
   └── confidence: 0.85 (auto-shares to pool)

3. MÖNGKE (subscribed to Temüjin) gets notified
   └── Reviews Temüjin's finding
   └── Creates deeper Research on the topic
   └── Updates original "async-patterns" concept

4. CHAGATAI (subscribed to domain: "async") gets notified
   └── Writes documentation combining both findings
   └── Creates Content explaining the nuance

5. KUBLAI observes the collaboration pattern
   └── Creates ProcessInsight: "Application feedback improves research"
   └── Updates ProcessPattern to route more tasks this way
   └── Creates Synthesis combining all three perspectives

RESULT: All agents learned, knowledge improved, process optimized
```

### Ögedei ↔ Jochi Operations Improvement Loop

```
1. JOCHI analyzes process metrics
   └── Task completion times, bottlenecks, agent utilization

2. JOCHI shares Analysis with ÖGEDEI

3. ÖGEDEI proposes WorkflowImprovement
   └── status: "proposed"

4. ÖGEDEI submits for approval
   └── status: "pending_approval"

5. KUBLAI reviews and decides
   ├── approved → status: "approved"
   ├── needs_revision → back to ÖGEDEI
   └── rejected → status: "rejected"

6. ÖGEDEI implements (if approved)
   └── status: "implementing"

7. JOCHI measures results
   └── status: "measuring"

8. Results confirmed
   └── status: "complete"
   └── Kublai sees improvement metrics
```

---

## Kublai Approval Gate

### WorkflowImprovement Status Flow

```
proposed → pending_approval → approved → implementing → measuring → complete
                           └→ rejected
                           └→ needs_revision → (back to proposed)
```

### Approval Queries

```cypher
// Ögedei: Submit for approval
MATCH (wi:WorkflowImprovement {id: $id, status: "proposed"})
SET wi.status = "pending_approval",
    wi.submitted_for_approval = datetime()
RETURN wi

// Kublai: Get pending approvals
MATCH (wi:WorkflowImprovement {status: "pending_approval"})
OPTIONAL MATCH (wi)-[:BASED_ON]->(analysis:Analysis)
RETURN wi.id, wi.target_process, wi.proposed_state,
       wi.effort_estimate, wi.risk_level, wi.projected_metrics,
       analysis.findings AS backing
ORDER BY wi.submitted_for_approval ASC

// Kublai: Approve
MATCH (wi:WorkflowImprovement {id: $id})
MATCH (kublai:Agent {id: "kublai"})
SET wi.status = "approved",
    wi.reviewed_by = "kublai",
    wi.review_decision = "approved",
    wi.review_notes = $notes,
    wi.reviewed_at = datetime()
MERGE (wi)-[:APPROVED_BY {
  decision: "approved",
  notes: $notes,
  reviewed_at: datetime()
}]->(kublai)
RETURN wi

// Kublai: Heartbeat check for pending approvals
MATCH (wi:WorkflowImprovement {status: "pending_approval"})
WHERE wi.submitted_for_approval < datetime() - duration('PT1H')
RETURN "Pending approval: " + wi.target_process AS item,
       1.0 AS priority
```

---

## Deployment Architecture

### Railway Configuration

```
Railway Project
├── openclaw (existing)
│   └── Env: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
├── signal-cli-native (existing)
├── neo4j (new service)
│   └── Image: neo4j:5-community
│   └── Volume: /data (persistent)
│   └── Env: NEO4J_AUTH=neo4j/${NEO4J_PASSWORD}
│   └── Internal URL: neo4j.railway.internal:7687
└── Environment Variables (shared)
    └── NEO4J_URI=bolt://neo4j.railway.internal:7687
    └── NEO4J_USER=neo4j
    └── NEO4J_PASSWORD=${secret}
```

### Integration Pattern (Option 3: Agent Instructions)

Agents use memory tools instead of file operations:

```python
from openclaw_memory import Memory

memory = Memory(
    neo4j_uri=os.environ["NEO4J_URI"],
    neo4j_user=os.environ["NEO4J_USER"],
    neo4j_password=os.environ["NEO4J_PASSWORD"],
    agent_name="kublai"
)

# Store experience
memory.add_experience(
    content="User requested competitor analysis",
    type="task_request"
)

# Query relevant knowledge
beliefs = memory.get_beliefs(
    domain="competitive",
    min_confidence=0.7,
    include_shared=True
)

# Trigger reflection
memory.reflect()
```

### Agent Instructions Update

```
You have access to memory tools:
- memory_store(content, type, confidence) - store knowledge
- memory_query(topic, min_confidence) - retrieve relevant knowledge
- memory_reflect() - synthesize recent experiences into beliefs
- memory_share(knowledge_id) - share to cross-agent pool

Do NOT use MEMORY.md or memory/*.md files.
Use these tools for all persistent memory operations.
```

---

## Implementation Plan

### Phase 1: Infrastructure

1. Add Neo4j service to Railway
2. Configure environment variables
3. Create database indexes

### Phase 2: Core Schema

1. Create all node types
2. Create all relationships
3. Create agent nodes with subscriptions

### Phase 3: Memory Module

1. Port memory operations from BYRD
2. Adapt for multi-agent use
3. Add agent attribution to all nodes

### Phase 4: Agent Integration

1. Update agent instructions
2. Add memory tools to agent capabilities
3. Retire file-based memory

### Phase 5: Advanced Features

1. Implement reflection cycles
2. Add graph algorithms (PageRank, community detection)
3. Implement intelligent heartbeat queries

### Phase 6: Validation

1. Test cross-agent knowledge flow
2. Validate approval gates
3. Measure performance vs file-based system

---

## Appendix: Key Queries

### Cross-Agent Knowledge Discovery

```cypher
// Find knowledge from other agents I haven't seen
MATCH (me:Agent {name: $agent})
MATCH (other:Agent)-[:CREATED]->(k)
WHERE other.name <> $agent
  AND NOT (me)-[:ACCESSED]->(k)
  AND k.confidence > 0.7
OPTIONAL MATCH (me)-[sub:SUBSCRIBES_TO]->(other)
WITH k, other, sub
WHERE sub IS NOT NULL
   OR EXISTS { MATCH (sk:SharedKnowledge {knowledge_id: k.id}) }
RETURN other.name AS from_agent,
       labels(k)[0] AS type,
       k.name AS knowledge,
       k.confidence
ORDER BY k.created_at DESC
LIMIT 20
```

### Synthesis Opportunities

```cypher
// Research + failed applications = refinement needed
MATCH (r:Research)-[:DISCOVERED]->(c:Concept)<-[:CHALLENGED]-(a:Application)
WHERE NOT EXISTS {
  MATCH (s:Synthesis)-[:UPDATED]->(c)
  WHERE s.created_at > a.created_at
}
RETURN "refinement" AS type, c.name AS concept, r.findings, a.lessons_learned
```

### Process Health Metrics

```cypher
// Pipeline performance by stage
MATCH (t:Task)
WHERE t.created_at > datetime() - duration('P7D')
WITH t.type AS stage,
     count(*) AS total,
     sum(CASE WHEN t.outcome = 'success' THEN 1 ELSE 0 END) AS successes,
     avg(t.quality_score) AS avg_quality
RETURN stage,
       successes * 1.0 / total AS success_rate,
       avg_quality
ORDER BY stage
```

---

*Document generated from brainstorming session 2026-02-03*
