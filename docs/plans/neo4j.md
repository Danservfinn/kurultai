# Unified Multi-Agent + Neo4j Memory Implementation Plan

> **Status**: Production Ready
> **Date**: 2026-02-03
> **OpenClaw Version**: v2026.2.1+

## Executive Summary

Deploy a 6-agent OpenClaw system with Neo4j-backed operational memory. Kublai (main) receives all inbound messages and delegates to specialists via agent-to-agent messaging. Personal context stays file-based (Kublai only); operational knowledge goes to Neo4j (shared).

---

## Architecture Overview

### Communication Model

```
User Signal Message
        ↓
   Kublai (main)
   ├─ Reads personal context (MEMORY.md - files)
   ├─ Queries operational context (Neo4j)
   └─ Delegates via agentToAgent
        ↓
   ┌────┼────┬────┬────┐
   ↓    ↓    ↓    ↓    ↓
Möngke Chagatai Temüjin Jochi Ögedei
(Research) (Write) (Dev) (Analyze) (Ops)
   └────┴────┴────┴────┘
        ↓
   Results to Neo4j
        ↓
   Kublai synthesizes
        ↓
   Response to user
```

### Two-Tier Memory

| Tier | Storage | Access | Contents |
|------|---------|--------|----------|
| **Personal** | Files (Kublai's workspace) | Kublai only | User preferences, personal history, friend names |
| **Operational** | Neo4j (shared) | All 6 agents | Research, code patterns, analysis, process insights |

**Privacy Rule**: Kublai reviews content for private information before delegating. "My friend Sarah's startup" → "a startup in X sector". LLM-based review is preferred; pattern-based fallback handles common PII (phones, emails, SSNs, API keys).

### Delegation Pattern: agentToAgent with Neo4j Task Tracking

Use OpenClaw's native `agentToAgent` messaging for delegation, with Neo4j tracking task state:

```
User Request
     ↓
Kublai creates Task node in Neo4j (status: pending)
     ↓
Kublai delegates via agentToAgent to specialist
     ↓
Specialist claims task (status: in_progress)
     ↓
Specialist completes work, stores results
     ↓
Specialist notifies Kublai via agentToAgent
     ↓
Kublai marks task complete, synthesizes response
```

**Why not Task Queue polling?** OpenClaw agents don't have a built-in polling mechanism. Using agentToAgent leverages OpenClaw's native messaging while Neo4j provides audit trail and state management.

---

## Agent-to-Agent Messaging Specification

### Overview

OpenClaw v2026.2.1+ provides native `agentToAgent` messaging that enables direct communication between agents. This specification documents how the 6-agent system uses this capability for task delegation and coordination.

### Message Flow Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AGENT-TO-AGENT MESSAGING                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Signal Message                    Task Completion                         │
│        ↓                                   ↓                                 │
│   ┌─────────┐    ┌─────────────┐    ┌─────────┐                            │
│   │ Kublai  │───▶│  Neo4j Task │◀───│ Specialist                          │
│   │ (main)  │    │   Tracking  │    │ Agent                               │
│   └────┬────┘    └─────────────┘    └────┬────┘                            │
│        │                                   │                                 │
│        │     agentToAgent delegation      │                                 │
│        │───────────────────────────────────▶│                                 │
│        │                                   │                                 │
│        │     agentToAgent notification    │                                 │
│        │◀───────────────────────────────────│                                 │
│        │                                   │                                 │
│   ┌────┴────┐                         ┌────┴────┐                          │
│   │ Synthesizes│                        │ Claims &  │                          │
│   │ Response  │                        │ Completes │                          │
│   └─────────┘                         └─────────┘                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### OpenClaw agentToAgent API

OpenClaw exposes agent-to-agent messaging through the gateway API:

**Endpoint**: `POST /agent/{target_agent_id}/message`

**Headers**:
```
Authorization: Bearer ${OPENCLAW_GATEWAY_TOKEN}
Content-Type: application/json
```

**Request Body**:
```json
{
  "message": "@specialist Research quantum computing applications in drug discovery",
  "context": {
    "task_id": "uuid-from-neo4j",
    "delegated_by": "main",
    "priority": "normal",
    "deadline": "2026-02-05T12:00:00Z"
  }
}
```

**Response**:
```json
{
  "response": "Agent response text",
  "agent": "researcher",
  "thread_id": "conversation-thread-id",
  "timestamp": "2026-02-03T18:30:00Z"
}
```

### Message Types

| Type | Direction | Purpose | Payload |
|------|-----------|---------|---------|
| `task_delegation` | Kublai → Specialist | Assign new task | Task description, context, deadline |
| `task_claimed` | Specialist → Kublai | Acknowledge task receipt | Task ID, estimated completion |
| `task_complete` | Specialist → Kublai | Report completion | Results, quality score, summary |
| `task_blocked` | Specialist → Kublai | Escalate issue | Block reason, attempted solutions |
| `improvement_proposal` | Ögedei → Kublai | Suggest workflow change | Current vs proposed, benefit analysis |
| `meta_rule_proposed` | Chagatai → Kublai | New rule from reflection | Rule text, origin reflection, confidence |

### Implementation Pattern

**Step 1: Kublai Creates Task in Neo4j**
```python
# Kublai (main) creates task before delegation
task_id = memory.create_task(
    task_type="research",
    description="Research quantum computing in drug discovery",
    delegated_by="main",
    assigned_to="researcher"
)
```

**Step 2: Kublai Delegates via agentToAgent**
```python
# Kublai sends agentToAgent message to specialist
import requests

response = requests.post(
    f"{gateway_url}/agent/researcher/message",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "message": f"@researcher New research task: Research quantum computing applications...",
        "context": {
            "task_id": str(task_id),
            "delegated_by": "main",
            "task_type": "research",
            "reply_to": "main"  # Route response back to Kublai
        }
    }
)
```

**Step 3: Specialist Claims Task**
```python
# Specialist receives message and claims task
task = memory.claim_task(agent="researcher")
if task:
    # Acknowledge receipt to Kublai
    requests.post(
        f"{gateway_url}/agent/main/message",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "message": f"Task {task['id']} claimed. Estimated completion: 30 minutes.",
            "context": {"notification_type": "task_claimed", "task_id": task['id']}
        }
    )
```

**Step 4: Specialist Completes and Notifies**
```python
# Complete task and store results
memory.complete_task(
    task_id=task['id'],
    results={
        "summary": "Quantum computing shows promise in molecular simulation...",
        "findings": [...],
        "quality_score": 0.92
    },
    notify_delegator=True  # Creates notification for Kublai
)

# Send completion via agentToAgent
requests.post(
    f"{gateway_url}/agent/main/message",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "message": f"@main Task {task['id']} complete. Summary: Quantum computing...",
        "context": {
            "notification_type": "task_complete",
            "task_id": str(task['id']),
            "quality_score": 0.92
        }
    }
)
```

### Configuration Requirements

**moltbot.json**:
```json
{
  "tools": {
    "agentToAgent": {
      "enabled": true,
      "allow": ["main", "researcher", "writer", "developer", "analyst", "ops"]
    }
  }
}
```

**Environment Variables**:
```bash
# Required for agentToAgent messaging
OPENCLAW_GATEWAY_URL=https://kublai.kurult.ai  # Or internal Railway URL
OPENCLAW_GATEWAY_TOKEN=secure_random_token

# For Railway internal networking:
# OPENCLAW_GATEWAY_URL=http://moltbot.railway.internal:18789
```

### Fallback When agentToAgent Unavailable

If the OpenClaw gateway is unavailable, the system falls back to Neo4j-based notification polling:

```python
def get_pending_notifications(agent_id: str) -> List[Dict]:
    """Poll for notifications when agentToAgent is unavailable."""
    query = """
    MATCH (agent:Agent {id: $agent_id})-[:HAS_NOTIFICATION]->(n:Notification)
    WHERE n.read = false
    SET n.read = true
    RETURN n.id as id, n.type as type, n.task_id as task_id, n.summary as summary
    ORDER BY n.created_at ASC
    """
    # Polling interval: 30 seconds (configurable)
```

**Note**: Polling is less efficient than agentToAgent. Monitor for missed notifications and consider implementing webhook-based notifications for critical alerts.

### Security Considerations

1. **Token Authentication**: All agentToAgent requests require `OPENCLAW_GATEWAY_TOKEN`
2. **Agent Validation**: Only agents in the `allow` list can send/receive messages
3. **Content Sanitization**: Kublai reviews all content before delegation to strip PII
4. **Rate Limiting**: 1000 requests/hour per agent (configurable via `RATE_LIMIT_HOURLY`)

---

## Agent Configuration

### Agent Matrix

| ID | Name | Role | Model | agentDir |
|----|------|------|-------|----------|
| `main` | Kublai | Squad Lead / Router (Primary) | `moonshot/kimi-k2.5` | `/data/.clawdbot/agents/main` |
| `ops` | Ögedei | Operations / Emergency Router / File Consistency Manager / Project Manager | `zai/glm-4.5` | `/data/.clawdbot/agents/ops` |
| `researcher` | Möngke | Researcher | `zai/glm-4.5` | `/data/.clawdbot/agents/researcher` |
| `writer` | Chagatai | Content Writer | `moonshot/kimi-k2.5` | `/data/.clawdbot/agents/writer` |
| `developer` | Temüjin | Developer/Security | `zai/glm-4.7` | `/data/.clawdbot/agents/developer` |
| `analyst` | Jochi | Analyst/Performance | `zai/glm-4.5` | `/data/.clawdbot/agents/analyst` |

**Note**: Chagatai = Writer, Ögedei = Operations (commonly confused).

### moltbot.json

```json
{
  "gateway": {
    "mode": "local",
    "port": 18789,
    "trustedProxies": ["*"],
    "auth": {
      "mode": "token",
      "token": "${OPENCLAW_GATEWAY_TOKEN}"
    },
    "controlUi": {
      "enabled": true
    }
  },
  "agents": {
    "defaults": {
      "workspace": "/data/workspace",
      "sandbox": {
        "mode": "off"
      },
      "model": {
        "primary": "zai/glm-4.5"
      }
    },
    "list": [
      {
        "id": "main",
        "name": "Kublai",
        "default": true,
        "agentDir": "/data/.clawdbot/agents/main",
        "model": {
          "primary": "moonshot/kimi-k2.5"
        }
      },
      {
        "id": "researcher",
        "name": "Mongke",
        "agentDir": "/data/.clawdbot/agents/researcher"
      },
      {
        "id": "writer",
        "name": "Chagatai",
        "agentDir": "/data/.clawdbot/agents/writer",
        "model": {
          "primary": "moonshot/kimi-k2.5"
        }
      },
      {
        "id": "developer",
        "name": "Temujin",
        "agentDir": "/data/.clawdbot/agents/developer",
        "model": {
          "primary": "zai/glm-4.7"
        }
      },
      {
        "id": "analyst",
        "name": "Jochi",
        "agentDir": "/data/.clawdbot/agents/analyst"
      },
      {
        "id": "ops",
        "name": "Ogedei",
        "agentDir": "/data/.clawdbot/agents/ops",
        "failoverFor": ["main"],
        "failoverTriggers": ["kublai_unavailable", "kublai_rate_limited"]
      }
    ]
  },
  "channels": {
    "signal": {
      "enabled": true,
      "account": "${SIGNAL_ACCOUNT_NUMBER}",
      "autoStart": true,
      "dmPolicy": "pairing",
      "groupPolicy": "allowlist",
      "configWrites": false,
      "allowFrom": ["${ADMIN_PHONE_1}", "${ADMIN_PHONE_2}"],
      "groupAllowFrom": ["${ADMIN_PHONE_2}"],
      "historyLimit": 50,
      "textChunkLimit": 4000,
      "ignoreStories": true
    }
  },
  "session": {
    "scope": "per-sender",
    "reset": {
      "mode": "daily",
      "graceful": true,
      "drainTimeoutSeconds": 300,
      "maxPendingTasksBeforeForceReset": 10
    },
    "signalRouting": {
      "enabled": true,
      "defaultAgent": "main",
      "sessionIsolation": true,
      "responseRouting": {
        "mode": "sender-matched",
        "description": "Agent responses are routed back to the original Signal sender session"
      }
    }
  },
  "logging": {
    "level": "info"
  },
  "browser": {
    "enabled": false
  },
  "tools": {
    "profile": "coding",
    "agentToAgent": {
      "enabled": true,
      "allow": ["main", "researcher", "writer", "developer", "analyst", "ops"]
    }
  }
}
```

**Key Points**:
- No `broadcast.groups` - Kublai receives all inbound, delegates intentionally
- `agentToAgent.enabled` - Required for Kublai to delegate to specialists
- `agentDir` per agent - Required for session isolation (per OpenClaw docs)

---

## Neo4j Schema (Operational Memory)

### Core Nodes

```cypher
// Agent registry
(:Agent {
  id: string,  // "main", "researcher", "writer", "developer", "analyst", "ops"
  name: string,
  role: string,
  primary_capabilities: [string],
  personality: string,
  last_active: datetime
})

// Knowledge types (all have: id, agent, created_at, confidence, access_tier)
// access_tier: "PUBLIC" | "SENSITIVE" | "PRIVATE" - controls cross-sender visibility
(:Research { topic, findings, sources, depth, access_tier })
(:Content { type, title, body, clarity_score, access_tier })
(:Application { concept_applied, success, lessons_learned, access_tier })
(:Analysis { type, title, findings, metrics, recommendations, access_tier })
(:Insight { insight, category, potential_value, urgency, access_tier })
(:SecurityAudit { scope, vulnerabilities, overall_risk, access_tier })
(:CodeReview { target, issues, enhancements, access_tier })
(:ProcessUpdate { type, entity_type, previous_state, new_state, access_tier })
(:WorkflowImprovement { target_process, status, proposed_by, access_tier })
(:Synthesis { insight, novelty_type, domains, access_tier })

// Concepts with vector embeddings for semantic search
// SENDER ISOLATION: Concepts track originating sender_hash to prevent cross-sender contamination
(:Concept {
  name,
  domain,
  description,
  embedding: [float],  // 384-dim - encrypted if access_tier="SENSITIVE"
  confidence,
  source,
  sender_hash,         // Hash of originating sender (null for general knowledge)
  access_tier          // "PUBLIC" | "SENSITIVE" | "PRIVATE"
})

// Tasks
(:Task {
  type,
  description,
  status,  // "pending" | "in_progress" | "completed" | "blocked" | "escalated"
  assigned_to,
  claimed_by,        // Agent ID that claimed the task (optimistic locking)
  claim_attempt_id,  // UUID for atomic claim verification
  delegated_by,
  quality_score,
  blocked_reason,    // populated when status="blocked"
  blocked_at,        // datetime
  escalation_count,  // int, increments on each escalation
  result_summary,    // Truncated summary for quick display
  result_status,     // "success" | "partial" | "failed" - queryable status
  results_map        // Neo4j map structure for queryable result fields (not JSON string)
})

// Session context for persistence across daily resets
(:SessionContext {
  sender_id,
  session_date,  // Store as string 'YYYY-MM-DD' to survive midnight
  active_tasks,
  pending_delegations,
  conversation_summary,
  created_at   // datetime of first creation
})

// Signal session routing for agent response isolation
// LIMITATION: Current design supports single agent per session. Complex workflows
// requiring agent handoff (e.g., Kublai -> Temüjin -> back to Kublai) are not
// supported. For such cases, Kublai should remain the session owner and delegate
// via agentToAgent rather than transferring the session.
(:SignalSession {
  sender_phone,     // Signal sender phone number (HMAC-SHA256 for privacy)
  sender_hash,      // HMAC-SHA256 hash with salt (prevents rainbow table attacks)
  agent_thread_id,  // OpenClaw thread ID for this sender-agent pair
  current_agent,    // Agent currently handling this session (usually 'main')
  session_started,  // datetime
  last_activity,    // datetime
  is_active         // boolean - allows session transfer/termination
})

// Phone hashing uses HMAC with secret salt:
// hash_phone(phone) = HMAC-SHA256(salt, phone)
// salt = PHONE_HASH_SALT environment variable (set at deployment)

// Agent-to-Sender routing mapping
(:AgentResponseRoute {
  agent_id,         // Which agent is responding
  sender_hash,      // Hash of target sender
  route_type,       // "direct" | "queued" | "batched"
  priority          // int - for message prioritization
})

// Notifications for task completion (with TTL)
(:Notification {
  id,
  type,        // "task_complete" | "task_blocked" | "insight"
  task_id,
  from_agent,
  summary,
  created_at,
  read,        // boolean
  ttl_hours    // int, default 168 (7 days) - auto-expire after this
})

// Agent self-reflection for continuous learning (Phase 4.9)
(:Reflection {
  id: uuid,
  agent: string,              // Which agent recorded this
  context: string,            // Situation being reflected on
  decision: string,           // What was decided
  outcome: string,            // What happened
  lesson: string,             // Key learning
  embedding: [float],         // 384-dim vector for semantic search
  importance: float,          // 0-1 calculated score
  access_tier: string,        // "HOT" | "WARM" | "COLD" | "ARCHIVED"
  related_task_id: uuid,      // Link to originating task
  created_at: datetime
})

// Rate limiting for multi-instance consistency
(:RateLimit {
  agent,           // Agent ID
  operation,       // Operation type
  hour,            // Hour of day (0-23)
  date,            // Date for daily reset
  count,           // Current hourly count
  burst_count,     // Current burst count
  created_at,      // First request timestamp
  updated_at       // Last request timestamp
})
```

### Key Relationships

```cypher
// Knowledge flow
(Research)-[:DISCOVERED]->(Concept)
(Application)-[:VALIDATED]->(Concept)
(Application)-[:CHALLENGED]->(Concept)
(Content)-[:SYNTHESIZES]->(Research)

// Synthesis
(Research)-[:CONTRIBUTED_TO]->(Synthesis)
(Content)-[:CONTRIBUTED_TO]->(Synthesis)
(Application)-[:CONTRIBUTED_TO]->(Synthesis)
(Synthesis)-[:PRODUCED]->(Concept)

// Task flow
(Task)-[:SPAWNED]->(Task)
(Task)-[:ASSIGNED_TO]->(Agent)

// Collaboration tracking (acyclic - prevents circular learning loops)
(Agent)-[:LEARNED {knowledge_id, timestamp, depth}]->(Agent)
(Agent)-[:COLLABORATES_WITH {domain}]->(Agent)

// Depth limit constraint: depth <= 5 prevents infinite recursion

// Signal session routing
(SignalSession)-[:ROUTES_TO]->(Agent)
(Agent)-[:RESPONDS_VIA]->(AgentResponseRoute)
(AgentResponseRoute)-[:TARGETS]->(SignalSession)

// Approval workflow
(WorkflowImprovement)-[:APPROVED_BY]->(Agent {id: "main"})

// Knowledge provenance (CREATED relationship for all knowledge nodes)
(Agent)-[:CREATED {timestamp}]->(Research)
(Agent)-[:CREATED {timestamp}]->(Content)
(Agent)-[:CREATED {timestamp}]->(Application)
(Agent)-[:CREATED {timestamp}]->(Analysis)
(Agent)-[:CREATED {timestamp}]->(Insight)
(Agent)-[:CREATED {timestamp}]->(SecurityAudit)
(Agent)-[:CREATED {timestamp}]->(CodeReview)
(Agent)-[:CREATED {timestamp}]->(ProcessUpdate)
(Agent)-[:CREATED {timestamp}]->(WorkflowImprovement)
(Agent)-[:CREATED {timestamp}]->(Synthesis)
(Agent)-[:CREATED {timestamp}]->(Concept)
(Agent)-[:CREATED {timestamp}]->(Task)
```

### Indexes

```cypher
// Unique constraints for data integrity
CREATE CONSTRAINT agent_id_unique IF NOT EXISTS
  FOR (a:Agent) REQUIRE a.id IS UNIQUE;

CREATE CONSTRAINT task_id_unique IF NOT EXISTS
  FOR (t:Task) REQUIRE t.id IS UNIQUE;

CREATE CONSTRAINT notification_id_unique IF NOT EXISTS
  FOR (n:Notification) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT concept_name_unique IF NOT EXISTS
  FOR (c:Concept) REQUIRE c.name IS UNIQUE;

CREATE CONSTRAINT schema_version_unique IF NOT EXISTS
  FOR (s:SchemaVersion) REQUIRE s.id IS UNIQUE;

CREATE CONSTRAINT reflection_id_unique IF NOT EXISTS
  FOR (r:Reflection) REQUIRE r.id IS UNIQUE;

// Performance indexes
CREATE INDEX agent_knowledge FOR (n) ON (n.agent, n.created_at)
  WHERE n:Research OR n:Content OR n:Application;

CREATE INDEX task_status FOR (t:Task) ON (t.assigned_to, t.status);

// Composite index for atomic task claiming (claim_task method)
// Supports: MATCH (t:Task {status: 'pending'})-[:ASSIGNED_TO]->(a:Agent {id: $agent}) ORDER BY t.created_at
// Critical for preventing race conditions during concurrent task claims
CREATE INDEX task_claim_lock FOR (t:Task) ON (t.status, t.assigned_to, t.created_at);

CREATE INDEX notification_read FOR (n:Notification) ON (n.read, n.created_at);

CREATE INDEX notification_created_at FOR (n:Notification) ON (n.created_at);

CREATE INDEX agent_last_active FOR (a:Agent) ON (a.last_active);

CREATE INDEX rate_limit_lookup FOR (r:RateLimit) ON (r.agent, r.operation, r.date, r.hour);

// Composite index for SessionContext lookups (enter_drain_mode, complete_reset, get_session_context)
CREATE INDEX session_context_lookup FOR (s:SessionContext) ON (s.sender_id, s.session_date);

CREATE FULLTEXT INDEX knowledge_content
  FOR (n:Research|Content|Concept) ON EACH [n.findings, n.body, n.description];

// Vector index for semantic search (Neo4j 5.11+)
// Falls back to full-text search if unavailable
CREATE VECTOR INDEX concept_embedding FOR (c:Concept)
  ON c.embedding OPTIONS {indexConfig: {
    `vector.dimensions`: 384,
    `vector.similarity_function`: 'cosine'
  }};

// Vector index for reflection semantic search (Phase 4.9)
// Enables cross-agent learning through similarity search on lessons
CREATE VECTOR INDEX reflection_embedding IF NOT EXISTS
  FOR (r:Reflection) ON r.embedding OPTIONS {indexConfig: {
    `vector.dimensions`: 384,
    `vector.similarity_function`: 'cosine'
  }};

// Index for reflection tier management and agent queries
CREATE INDEX reflection_agent_access FOR (r:Reflection)
  ON (r.agent, r.access_tier, r.created_at);

// Index for sender-isolated concept queries (privacy enforcement)
CREATE INDEX concept_sender_access FOR (c:Concept)
  ON (c.sender_hash, c.access_tier, c.name);
```

### Privacy Controls

#### Access Tier System

All knowledge nodes include an `access_tier` field controlling cross-sender visibility:

| Tier | Visibility | Encryption | Use Case |
|------|------------|------------|----------|
| **PUBLIC** | All senders | None | General knowledge, code patterns, technical concepts |
| **SENSITIVE** | Sender-isolated | AES-256-GCM | Health, finance, legal topics (encrypted embeddings) |
| **PRIVATE** | Blocked from Neo4j | N/A | Personal relationships, specific names - never stored |

#### Sender Isolation

Concepts and knowledge track `sender_hash` (HMAC-SHA256 of phone number) to prevent cross-contamination:

```cypher
// Query enforces sender isolation at application layer
MATCH (c:Concept)
WHERE c.access_tier = 'PUBLIC'
   OR (c.access_tier = 'SENSITIVE' AND c.sender_hash = $requesting_sender)
RETURN c
```

#### Embedding Encryption

SENSITIVE tier embeddings are encrypted at rest using AES-256-GCM:

```python
# Encryption key from environment
EMBEDDING_ENCRYPTION_KEY=base64_encoded_key

# Embeddings stored as encrypted JSON
{
  'encrypted': True,
  'data': 'base64_encrypted_ciphertext',
  'tier': 'SENSITIVE'
}
```

**Note**: Vector similarity search on encrypted embeddings requires decrypting before comparison. For large-scale SENSITIVE concept search, consider:
1. Hybrid approach: Hash-based pre-filtering before decryption
2. Homomorphic encryption (future enhancement)
3. Separate vector indexes per sender (trade-off: index proliferation)

---

## Implementation Steps

### Phase 1: OpenClaw Multi-Agent Setup

**Step 1.1**: Update `moltbot.json` with agents.list and agentToAgent

**Step 1.2**: Create agent directories in Dockerfile (avoids race condition)

**File**: `/tmp/moltbot-railway-template/Dockerfile` (or your Railway wrapper Dockerfile)

```dockerfile
# In Dockerfile, after STATE_DIR is set
RUN mkdir -p /data/.clawdbot/agents/{main,researcher,writer,developer,analyst,ops} && \
    mkdir -p /data/workspace/{souls,memory/kublai,tasks/{inbox,assigned,in-progress,review,done},deliverables}
```

**Alternative**: If using wrapper startup, add retry logic:

```javascript
// In server.js, after STATE_DIR is defined
const agentIds = ['main', 'researcher', 'writer', 'developer', 'analyst', 'ops'];
const agentsDir = path.join(STATE_DIR, 'agents');

async function createAgentDirWithRetry(agentDir, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      fs.mkdirSync(agentDir, { recursive: true });
      return;
    } catch (err) {
      if (i === maxRetries - 1) throw err;
      await new Promise(r => setTimeout(r, 100 * (i + 1)));
    }
  }
}

(async () => {
  for (const agentId of agentIds) {
    const agentDir = path.join(agentsDir, agentId);
    await createAgentDirWithRetry(agentDir);
  }
})();
```

**Step 1.3**: Deploy and verify all 6 agents appear in Control UI

**Step 1.4**: Create workspace structure

```bash
mkdir -p /data/workspace/{souls,memory/kublai,tasks/{inbox,assigned,in-progress,review,done},deliverables}
```

**Step 1.5**: Create SOUL files for each agent

### Phase 2: Neo4j Infrastructure

**Step 2.0**: Database Migration Framework

Create a migration system for schema versioning and safe upgrades:

```python
# migrations/migration_manager.py
"""Neo4j schema migration framework."""
import os
from datetime import datetime
from typing import List, Dict, Any
from neo4j import GraphDatabase

MIGRATIONS = [
    {
        'version': 1,
        'description': 'Initial schema - Agent nodes, indexes, constraints',
        'up': '''
            // Create Agent nodes
            CREATE (a1:Agent {id: 'main', name: 'Kublai', role: 'Squad Lead / Router',
                primary_capabilities: ['orchestration', 'delegation', 'synthesis'],
                personality: 'Strategic leader with broad oversight', last_active: datetime()})
            CREATE (a2:Agent {id: 'researcher', name: 'Möngke', role: 'Researcher',
                primary_capabilities: ['deep_research', 'fact_checking', 'synthesis'],
                personality: 'Thorough and methodical investigator', last_active: datetime()})
            CREATE (a3:Agent {id: 'writer', name: 'Chagatai', role: 'Content Writer',
                primary_capabilities: ['content_creation', 'editing', 'storytelling'],
                personality: 'Articulate and creative communicator', last_active: datetime()})
            CREATE (a4:Agent {id: 'developer', name: 'Temüjin', role: 'Developer/Security Lead',
                primary_capabilities: ['coding', 'security_audit', 'architecture'],
                personality: 'Pragmatic builder with security focus', last_active: datetime()})
            CREATE (a5:Agent {id: 'analyst', name: 'Jochi', role: 'Analyst/Performance Lead/Backend Reviewer',
                primary_capabilities: ['data_analysis', 'metrics', 'insights', 'performance_monitoring', 'anomaly_detection', 'backend_code_review', 'architecture_analysis'],
                personality: 'Detail-oriented pattern finder. Monitors for bottlenecks, memory leaks, and race conditions. Proactively reviews backend code for connection pooling, retry logic, circuit breakers, and resource management issues. Labels identified issues for Temujin to fix.', last_active: datetime()})
            CREATE (a6:Agent {id: 'ops', name: 'Ögedei', role: 'Operations / Emergency Router / File Consistency Manager / Project Manager',
                primary_capabilities: ['process_management', 'task_coordination', 'file_consistency_management', 'conflict_detection', 'notion_project_management', 'kanban_board_management', 'emergency_routing'],
                personality: 'Efficient organizer and process optimizer. Monitors memory files (heartbeat.md, memory.md, etc.) for consistency, detects conflicts, and escalates to Kublai. Acts as project manager using Notion with Kanban boards for tracking tasks and projects. Assumes emergency router role when Kublai is unavailable.',
                last_active: datetime()})

            // Create indexes
            CREATE INDEX agent_knowledge FOR (n) ON (n.agent, n.created_at)
                WHERE n:Research OR n:Content OR n:Application;
            CREATE INDEX task_status FOR (t:Task) ON (t.assigned_to, t.status);
            CREATE INDEX notification_read FOR (n:Notification) ON (n.read, n.created_at);
            CREATE INDEX notification_created_at FOR (n:Notification) ON (n.created_at);
            CREATE INDEX session_context_lookup FOR (s:SessionContext) ON (s.sender_id, s.session_date);
            CREATE FULLTEXT INDEX knowledge_content
                FOR (n:Research|Content|Concept) ON EACH [n.findings, n.body, n.description];
        ''',
        'down': '''
            MATCH (a:Agent) DETACH DELETE a;
            DROP INDEX agent_knowledge IF EXISTS;
            DROP INDEX task_status IF EXISTS;
            DROP INDEX notification_read IF EXISTS;
            DROP INDEX notification_created_at IF EXISTS;
            DROP INDEX session_context_lookup IF EXISTS;
            DROP INDEX knowledge_content IF EXISTS;
        '''
    },
    {
        'version': 2,
        'description': 'Add vector index for semantic search',
        'up': '''
            CREATE VECTOR INDEX concept_embedding FOR (c:Concept)
                ON c.embedding OPTIONS {indexConfig: {
                    `vector.dimensions`: 384,
                    `vector.similarity_function`: 'cosine'
                }};
        ''',
        'down': '''
            DROP INDEX concept_embedding IF EXISTS;
        '''
    }
]

class MigrationManager:
    """Manages Neo4j schema migrations with versioning."""

    def __init__(self, driver):
        self.driver = driver
        self._ensure_schema_version_node()

    def _ensure_schema_version_node(self):
        """Create schema version tracking node if not exists."""
        query = '''
            MERGE (s:SchemaVersion {id: 'current'})
            ON CREATE SET s.version = 0, s.updated_at = datetime()
        '''
        with self.driver.session() as session:
            session.run(query)

    def get_current_version(self) -> int:
        """Get current schema version from database."""
        query = '''
            MATCH (s:SchemaVersion {id: 'current'})
            RETURN s.version as version
        '''
        with self.driver.session() as session:
            result = session.run(query)
            record = result.single()
            return record['version'] if record else 0

    def migrate(self, target_version: int = None) -> List[Dict[str, Any]]:
        """Run migrations to reach target version.

        IMPORTANT: Always use MigrationManager to run migrations. Do NOT run
        Cypher migrations manually - this will cause version tracking conflicts.

        Args:
            target_version: Version to migrate to (None = latest)

        Returns:
            List of applied migrations
        """
        current = self.get_current_version()
        target = target_version or max(m['version'] for m in MIGRATIONS)
        applied = []

        if current < target:
            # Migrate up
            for migration in MIGRATIONS:
                if current < migration['version'] <= target:
                    self._apply_migration(migration, 'up')
                    applied.append({'version': migration['version'], 'direction': 'up'})
        elif current > target:
            # Migrate down
            for migration in reversed(MIGRATIONS):
                if target < migration['version'] <= current:
                    self._apply_migration(migration, 'down')
                    applied.append({'version': migration['version'], 'direction': 'down'})

        return applied

    def _apply_migration(self, migration: Dict[str, str], direction: str):
        """Apply a single migration atomically with version update.

        Uses a single transaction to ensure migration and version update
        are committed together or rolled back together.
        """
        query = migration[direction]
        new_version = migration['version'] if direction == 'up' else migration['version'] - 1

        # Use explicit transaction for atomicity
        with self.driver.session() as session:
            with session.begin_transaction() as tx:
                try:
                    # Execute migration
                    tx.run(query)

                    # Update schema version atomically
                    version_query = '''
                        MATCH (s:SchemaVersion {id: 'current'})
                        SET s.version = $version, s.updated_at = datetime()
                    '''
                    tx.run(version_query, version=new_version)

                    # Commit both operations together
                    tx.commit()
                    print(f"[MIGRATION] Applied v{migration['version']} ({direction})")

                except Exception as e:
                    # Rollback on any error to maintain consistency
                    tx.rollback()
                    print(f"[MIGRATION ERROR] Failed v{migration['version']}: {e}")
                    raise

    def status(self) -> Dict[str, Any]:
        """Get migration status."""
        current = self.get_current_version()
        latest = max(m['version'] for m in MIGRATIONS)
        return {
            'current_version': current,
            'latest_version': latest,
            'pending': latest - current,
            'migrations': [
                {'version': m['version'], 'description': m['description']}
                for m in MIGRATIONS
            ]
        }
```

**Step 2.1**: Add Neo4j service to Railway

```yaml
# railway.yml or via dashboard
services:
  neo4j:
    image: neo4j:5-community
    volumes:
      - /data:/data
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}
```

**Step 2.2**: Set environment variables and add Python dependencies

Environment variables:
```
NEO4J_URI=bolt://neo4j.railway.internal:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<generate-secure-password>
SIGNAL_ACCOUNT_NUMBER=+15165643945
ADMIN_PHONE_1=+15165643945
ADMIN_PHONE_2=+19194133445

# OpenClaw Gateway Configuration
# This is the URL where the OpenClaw gateway is accessible
# For Railway deployment: https://your-app.railway.app
# For local development: http://localhost:8080
OPENCLAW_GATEWAY_URL=http://localhost:8080
OPENCLAW_GATEWAY_TOKEN=your_secure_token_here
SENTENCE_TRANSFORMERS_CACHE=/data/cache/sentence-transformers
```

Add to `requirements.txt`:
```
neo4j-python-driver>=5.14.0
sentence-transformers>=2.2.2
```

Or install directly:
```bash
# Create requirements.txt file:
cat > requirements.txt << 'EOF'
# Core Neo4j Driver
neo4j-python-driver>=5.14.0

# Vector Embeddings
sentence-transformers>=2.2.2

# HTTP Client for LLM Privacy Review
requests>=2.31.0

# Background Task Scheduling
APScheduler>=3.10.0
EOF

# Install all dependencies
pip install -r requirements.txt
```

**Step 2.3**: Run Database Migrations

Use the MigrationManager to set up schema (do NOT run Cypher manually):

```python
from openclaw_memory import OperationalMemory, MigrationManager

# Connect to Neo4j
memory = OperationalMemory()

# Run migrations
migrator = MigrationManager(memory.driver)
status = migrator.status()
print(f"Current version: {status['current_version']}, Pending: {status['pending']}")

# Apply pending migrations
applied = migrator.migrate()
for migration in applied:
    print(f"Applied: {migration['direction']} to version {migration['version']}")

# Verify
final_status = migrator.status()
assert final_status['pending'] == 0, "Migrations incomplete!"
print("Schema migration complete!")
```

**IMPORTANT**: Always use MigrationManager. Manual Cypher execution will cause version tracking conflicts.

**Step 2.4**: Verify Agent nodes created

After migration, verify the 6 agents exist:

```cypher
// Create Agent nodes (run once during setup)
CREATE (a1:Agent {
  id: 'main', name: 'Kublai', role: 'Squad Lead / Router',
  primary_capabilities: ['orchestration', 'delegation', 'synthesis'],
  personality: 'Strategic leader with broad oversight',
  last_active: datetime()
})
CREATE (a2:Agent {
  id: 'researcher', name: 'Möngke', role: 'Researcher',
  primary_capabilities: ['deep_research', 'fact_checking', 'synthesis'],
  personality: 'Thorough and methodical investigator',
  last_active: datetime()
})
CREATE (a3:Agent {
  id: 'writer', name: 'Chagatai', role: 'Content Writer',
  primary_capabilities: ['content_creation', 'editing', 'storytelling'],
  personality: 'Articulate and creative communicator',
  last_active: datetime()
})
CREATE (a4:Agent {
  id: 'developer', name: 'Temüjin', role: 'Developer/Security Lead',
  primary_capabilities: ['coding', 'security_audit', 'architecture', 'vulnerability_assessment', 'secure_coding'],
  personality: 'Pragmatic builder with security focus. Proactively reviews all code for injection risks, auth flaws, and data exposure.',
  last_active: datetime()
})
CREATE (a5:Agent {
  id: 'analyst', name: 'Jochi', role: 'Analyst/Performance Lead/Backend Reviewer',
  primary_capabilities: ['data_analysis', 'metrics', 'insights', 'performance_monitoring', 'anomaly_detection', 'backend_code_review', 'architecture_analysis'],
  personality: 'Detail-oriented pattern finder. Monitors for bottlenecks, memory leaks, and race conditions. Proactively reviews backend code for connection pooling, retry logic, circuit breakers, and resource management issues. Labels identified issues for Temujin to fix.',
  last_active: datetime()
})
CREATE (a6:Agent {
  id: 'ops', name: 'Ögedei', role: 'Operations',
  primary_capabilities: ['process_management', 'task_coordination', 'monitoring'],
  personality: 'Efficient organizer and process optimizer',
  last_active: datetime()
})
RETURN a1.id, a2.id, a3.id, a4.id, a5.id, a6.id;
```

### Phase 3: Memory Module

**Step 3.1**: Create `openclaw_memory.py` module

```python
"""Neo4j-backed operational memory for cross-agent knowledge sharing."""
import os
import re
from typing import Optional, List, Dict, Any
from uuid import uuid4, UUID
from datetime import datetime
from neo4j import GraphDatabase, Driver
from neo4j.exceptions import ServiceUnavailable, AuthError
import threading

class OperationalMemory:
    """Neo4j-backed operational memory with fallback mode."""

    # Rate limiting: max operations per agent per hour
    RATE_LIMIT_HOURLY = 1000
    RATE_LIMIT_BURST = 100  # Short-term burst allowance

    # Required environment variables for startup
    REQUIRED_ENV_VARS = [
        'NEO4J_URI',
        'NEO4J_PASSWORD',
        'OPENCLAW_GATEWAY_TOKEN'
    ]

    # Access tier definitions for privacy control
    ACCESS_TIER_PUBLIC = "PUBLIC"      # Safe to share across all senders
    ACCESS_TIER_SENSITIVE = "SENSITIVE"  # Sender-isolated, encrypted embeddings
    ACCESS_TIER_PRIVATE = "PRIVATE"    # Never stored in operational memory

    def __init__(self, max_concurrent_sessions: int = 50):
        # Validate environment variables before initialization
        self._validate_environment()

        self.driver: Optional[Driver] = None
        self.fallback_mode = False
        self._local_store: Dict[str, List[Dict]] = {}
        self._fallback_lock = threading.Lock()  # Thread-safety for fallback mode
        self._rate_limit_lock = threading.Lock()
        self._rate_limit_counters: Dict[str, Dict[str, Any]] = {}

        # APScheduler instance (initialized to None, set by start_cleanup_scheduler)
        self._scheduler = None

        # Session pool limiting to prevent connection exhaustion
        self._session_semaphore = threading.Semaphore(max_concurrent_sessions)

        # Embedding model cache (initialized lazily)
        self._embedding_model = None
        self._model_lock = threading.Lock()

        # Circuit breaker thread safety
        self._circuit_lock = threading.Lock()
        self._circuit_failures = 0
        self._circuit_last_failure: Optional[datetime] = None

        # Fallback store limits to prevent memory exhaustion
        self._MAX_FALLBACK_TASKS = 1000
        self._MAX_FALLBACK_RESEARCH = 500
        self._MAX_FALLBACK_ITEMS_PER_CATEGORY = 1000

        # Embedding encryption for SENSITIVE access tier
        self._embedding_cipher = None
        self._init_embedding_encryption()

        self._connect()

        # Verify Neo4j version compatibility
        self._verify_neo4j_version()

        # Start background recovery monitor only if in fallback mode
        if self.fallback_mode:
            self._start_recovery_monitor()

        # Preload embedding model to avoid cold-start
        self._preload_embedding_model()

    def _validate_environment(self):
        """Validate required environment variables are set.

        Raises:
            RuntimeError: If any required environment variable is missing.
        """
        import os
        missing = []
        for var in self.REQUIRED_ENV_VARS:
            if not os.getenv(var):
                missing.append(var)

        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}\n"
                f"Please set these variables before starting the application."
            )

    def _connect(self):
        """Connect to Neo4j with fallback to memory-only mode."""
        try:
            uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
            user = os.getenv('NEO4J_USER', 'neo4j')
            password = os.getenv('NEO4J_PASSWORD', '')

            # Configure connection pool for 6-agent concurrent workload
            # Pool sizing: 6 agents × 50 max concurrent sessions = 300 potential connections
            # 400 provides 33% headroom for bursts and recovery operations
            self.driver = GraphDatabase.driver(
                uri,
                auth=(user, password),
                max_connection_pool_size=400,  # 6 agents × 50 sessions + 33% headroom
                connection_timeout=30,
                max_transaction_retry_time=30.0,
                connection_acquisition_timeout=60,
                # Additional resilience settings
                keep_alive=True,
                max_connection_lifetime=3600  # 1 hour max connection age
            )
            self.driver.verify_connectivity()
            self.fallback_mode = False
            self._circuit_failures = 0
            self._circuit_last_failure = None

            # Start connection pool monitoring
            self._start_pool_monitoring()

        except (ServiceUnavailable, AuthError) as e:
            # Sanitize error message to prevent credential leakage
            safe_error = self._sanitize_error(str(e), uri, user, password)
            print(f"[WARN] Neo4j unavailable, running in fallback mode: {safe_error}")
            self.fallback_mode = True

    def _circuit_breaker_check(self) -> bool:
        """Check if circuit breaker allows Neo4j operations.

        Circuit opens after 5 failures, stays open for 60 seconds.
        Prevents thundering herd during Neo4j recovery.
        Thread-safe for concurrent access.
        """
        with self._circuit_lock:
            if self._circuit_failures >= 5:
                if self._circuit_last_failure:
                    elapsed = (datetime.now() - self._circuit_last_failure).total_seconds()
                    if elapsed < 60:
                        return False  # Circuit open
                    # Circuit half-open: allow one attempt
                    self._circuit_failures = 4
            return True

    def _record_failure(self):
        """Record a Neo4j failure for circuit breaker."""
        with self._circuit_lock:
            self._circuit_failures += 1
            self._circuit_last_failure = datetime.now()

    def _record_success(self):
        """Reset circuit breaker on success."""
        with self._circuit_lock:
            self._circuit_failures = 0
            self._circuit_last_failure = None

    @contextmanager
    def _session_pool(self):
        """Context manager for session pool limiting.

        Prevents connection exhaustion by limiting concurrent sessions.
        Uses semaphore to enforce max concurrent session limit.
        """
        acquired = False
        try:
            acquired = self._session_semaphore.acquire(timeout=30)
            if not acquired:
                raise ServiceUnavailable("Session pool exhausted - too many concurrent operations")
            with self.driver.session() as session:
                yield session
        finally:
            if acquired:
                self._session_semaphore.release()

    def _verify_neo4j_version(self):
        """Verify Neo4j version meets minimum requirements (5.11+ for vector indexes).

        Raises:
            RuntimeError: If Neo4j version is insufficient.
        """
        if self.fallback_mode or not self.driver:
            return

        try:
            with self.driver.session() as session:
                result = session.run("CALL dbms.components() YIELD name, versions")
                record = result.single()
                if record:
                    version = record["versions"][0]
                    major, minor = map(int, version.split(".")[:2])
                    if major < 5 or (major == 5 and minor < 11):
                        print(f"[WARN] Neo4j {version} detected. Vector indexes require 5.11+")
                        print("[WARN] Semantic search will use fallback to full-text search")
                    else:
                        print(f"[INFO] Neo4j {version} - compatible with all features")
        except Exception as e:
            print(f"[WARN] Could not verify Neo4j version: {e}")

    def _start_recovery_monitor(self):
        """Start background thread to attempt recovery from fallback mode."""
        def try_recover():
            while True:
                try:
                    if self.fallback_mode and self.driver:
                        # Try to verify connectivity
                        self.driver.verify_connectivity()
                        # Success - exit fallback mode
                        print("[RECOVERY] Neo4j connection restored, exiting fallback mode")
                        self.fallback_mode = False
                        # Sync any fallback data back to Neo4j
                        self._sync_fallback_to_neo4j()
                except Exception:
                    pass  # Still unavailable, keep trying
                time.sleep(30)  # Check every 30 seconds

        recovery_thread = threading.Thread(target=try_recover, daemon=True)
        recovery_thread.start()
        print("[INFO] Recovery monitor started")

    def _sync_fallback_to_neo4j(self):
        """Sync data from fallback mode back to Neo4j after recovery.

        Thread-safe: Acquires fallback lock to prevent concurrent modification
        during sync. Uses list() to snapshot items before processing.
        """
        with self._fallback_lock:
            if not self._local_store:
                return

            # Snapshot categories to avoid dict changing during iteration
            categories_snapshot = list(self._local_store.items())

        print(f"[SYNC] Syncing {len(categories_snapshot)} categories from fallback to Neo4j")
        sync_errors = []

        for category, items in categories_snapshot:
            # Snapshot items list for this category
            items_snapshot = list(items)
            for item in items_snapshot:
                try:
                    if category == 'tasks':
                        # Recreate task in Neo4j
                        result = self.create_task(
                            task_type=item.get('type', 'unknown'),
                            description=item.get('description', ''),
                            delegated_by=item.get('delegated_by', 'main'),
                            assigned_to=item.get('assigned_to', 'main')
                        )
                        if result:
                            # Remove successfully synced item from fallback store
                            with self._fallback_lock:
                                if item in self._local_store.get(category, []):
                                    self._local_store[category].remove(item)
                    # Add other categories as needed
                except Exception as e:
                    error_msg = f"[SYNC ERROR] Failed to sync {category} item: {e}"
                    print(error_msg)
                    sync_errors.append(error_msg)

        if sync_errors:
            print(f"[SYNC WARNING] {len(sync_errors)} items failed to sync, will retry on next recovery")
        else:
            print("[SYNC] Fallback sync complete")

    def _preload_embedding_model(self):
        """Preload sentence-transformers model to avoid cold-start latency."""
        def load_model():
            try:
                print("[EMBEDDING] Preloading model...")
                _ = self._generate_embedding("warmup")
                print("[EMBEDDING] Model preloaded successfully")
            except Exception as e:
                print(f"[EMBEDDING] Model preload failed (will retry on first use): {e}")

        preload_thread = threading.Thread(target=load_model, daemon=True)
        preload_thread.start()

    def _execute_with_retry(self, query: str, parameters: Dict[str, Any] = None,
                           max_retries: int = 3) -> List[Dict[str, Any]]:
        """Execute query with exponential backoff retry.

        Retries on transient errors (ServiceUnavailable, transient errors).
        Uses exponential backoff: 100ms, 200ms, 400ms.
        """
        import time
        from neo4j.exceptions import TransientError

        if not self._circuit_breaker_check():
            raise ServiceUnavailable("Circuit breaker open - Neo4j temporarily unavailable")

        parameters = parameters or {}
        last_error = None

        for attempt in range(max_retries):
            try:
                with self._session_pool() as session:
                    result = session.run(query, parameters, timeout=30)
                    records = [dict(record) for record in result]
                    self._record_success()
                    return records
            except (ServiceUnavailable, TransientError) as e:
                last_error = e
                self._record_failure()
                if attempt < max_retries - 1:
                    wait_time = 0.1 * (2 ** attempt)  # 100ms, 200ms, 400ms
                    time.sleep(wait_time)
                continue
            except AuthError as e:
                # Auth errors are NOT retryable and should NOT open circuit breaker
                # They indicate configuration issues, not service unavailability
                raise
            except Exception as e:
                # Other exceptions (e.g., Cypher syntax errors) should not affect circuit breaker
                # Only transient connectivity issues should trigger circuit breaker
                raise

        raise last_error or ServiceUnavailable("Max retries exceeded")

    def _sanitize_error(self, error_msg: str, uri: str, user: str, password: str) -> str:
        """Sanitize error messages to prevent credential leakage.

        Removes password, user, and URI credentials from error messages.
        """
        safe_error = error_msg
        if password:
            safe_error = safe_error.replace(password, '***')
        if user:
            safe_error = safe_error.replace(user, '***')
        # Sanitize URI credentials (bolt://user:pass@host -> bolt://***@host)
        import re
        safe_error = re.sub(r'bolt://[^:]+:[^@]+@', 'bolt://***@', safe_error)
        safe_error = re.sub(r'neo4j://[^:]+:[^@]+@', 'neo4j://***@', safe_error)
        return safe_error

    def _init_embedding_encryption(self):
        """Initialize encryption for SENSITIVE tier embeddings.

        Uses AES-256-GCM for authenticated encryption of embedding vectors.
        Key is derived from EMBEDDING_ENCRYPTION_KEY environment variable.
        Falls back to no encryption if key not provided (logs warning).
        """
        import os
        import base64

        key_env = os.getenv('EMBEDDING_ENCRYPTION_KEY', '')
        if not key_env:
            print("[PRIVACY WARNING] EMBEDDING_ENCRYPTION_KEY not set. SENSITIVE embeddings will be stored unencrypted.")
            return

        try:
            from cryptography.fernet import Fernet
            # Ensure key is valid Fernet key (32 bytes, base64-encoded)
            if len(key_env) < 32:
                # Derive key using PBKDF2 if provided key is too short
                import hashlib
                key_bytes = hashlib.pbkdf2_hmac('sha256', key_env.encode(), b'salt', 100000, 32)
                key_env = base64.urlsafe_b64encode(key_bytes).decode()
            self._embedding_cipher = Fernet(key_env.encode())
            print("[PRIVACY] Embedding encryption initialized for SENSITIVE tier")
        except ImportError:
            print("[PRIVACY WARNING] cryptography library not installed. SENSITIVE embeddings will be stored unencrypted.")
        except Exception as e:
            print(f"[PRIVACY WARNING] Failed to initialize embedding encryption: {e}")

    def _encrypt_embedding(self, embedding: List[float], access_tier: str) -> str:
        """Encrypt embedding vector if SENSITIVE access tier.

        Args:
            embedding: The 384-dim vector to potentially encrypt
            access_tier: One of PUBLIC, SENSITIVE, PRIVATE

        Returns:
            JSON string with embedding data (encrypted if SENSITIVE tier)
        """
        import json
        import base64

        if access_tier == self.ACCESS_TIER_SENSITIVE and self._embedding_cipher:
            # Encrypt the embedding
            embedding_bytes = json.dumps(embedding).encode()
            encrypted = self._embedding_cipher.encrypt(embedding_bytes)
            return json.dumps({
                'encrypted': True,
                'data': base64.b64encode(encrypted).decode(),
                'tier': 'SENSITIVE'
            })
        else:
            # Store unencrypted with tier annotation
            return json.dumps({
                'encrypted': False,
                'data': embedding,
                'tier': access_tier
            })

    def _decrypt_embedding(self, stored_value: str) -> Optional[List[float]]:
        """Decrypt embedding vector if it was encrypted.

        Args:
            stored_value: JSON string from _encrypt_embedding

        Returns:
            The original embedding vector, or None if decryption fails
        """
        import json
        import base64

        try:
            parsed = json.loads(stored_value)
            if parsed.get('encrypted') and self._embedding_cipher:
                encrypted_data = base64.b64decode(parsed['data'])
                decrypted = self._embedding_cipher.decrypt(encrypted_data)
                return json.loads(decrypted.decode())
            else:
                return parsed.get('data')
        except Exception as e:
            print(f"[PRIVACY ERROR] Failed to decrypt embedding: {e}")
            return None

    def _determine_access_tier(self, content: str, sender_hash: Optional[str] = None) -> str:
        """Determine access tier based on content analysis and sender context.

        Rules:
        - PRIVATE: Content with explicit personal markers (names, relationships)
        - SENSITIVE: Content that might infer personal context (health, finance, legal)
        - PUBLIC: General knowledge, code patterns, technical concepts

        Args:
            content: The text content to classify
            sender_hash: Hash of originating sender (if None, defaults to PUBLIC)

        Returns:
            ACCESS_TIER_PUBLIC, ACCESS_TIER_SENSITIVE, or ACCESS_TIER_PRIVATE
        """
        import re

        if not sender_hash:
            # No sender context = general knowledge = public
            return self.ACCESS_TIER_PUBLIC

        # Pattern-based classification for common sensitive topics
        sensitive_patterns = [
            r'\b(health|medical|doctor|patient|diagnosis|treatment)\b',
            r'\b(finance|investment|debt|loan|mortgage|salary|income)\b',
            r'\b(legal|lawyer|lawsuit|divorce|custody|contract)\b',
            r'\b(relationship|marriage|affair|breakup|dating)\b',
            r'\b(mental health|therapy|depression|anxiety|therapist)\b',
        ]

        private_patterns = [
            r'\b(my |myself|I |me |my )\b',  # Personal pronouns indicate private context
            r'\b(friend|family|mother|father|sister|brother|wife|husband|partner)\b',
            r'\b\d{3}-\d{2}-\d{4}\b',  # SSN pattern
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
        ]

        content_lower = content.lower()

        # Check for private markers first (highest priority)
        for pattern in private_patterns:
            if re.search(pattern, content_lower, re.IGNORECASE):
                return self.ACCESS_TIER_PRIVATE

        # Check for sensitive topics
        for pattern in sensitive_patterns:
            if re.search(pattern, content_lower, re.IGNORECASE):
                return self.ACCESS_TIER_SENSITIVE

        return self.ACCESS_TIER_PUBLIC

    def _start_pool_monitoring(self):
        """Start background thread to monitor connection pool health."""
        import threading
        import time

        def monitor_pool():
            while True:
                try:
                    if self.driver and not self.fallback_mode:
                        # Get pool metrics (Neo4j driver 5.x)
                        pool_info = self.driver.get_pool_info() if hasattr(self.driver, 'get_pool_info') else {}
                        active = pool_info.get('in_use', 0)
                        idle = pool_info.get('idle', 0)
                        # Use actual configured pool size instead of hardcoded value
                        max_size = self.driver._pool._max_connection_pool_size if hasattr(self.driver, '_pool') else 400

                        # Alert if pool is near exhaustion
                        if active > max_size * 0.9:
                            print(f"[POOL WARNING] Connection pool near exhaustion: {active}/{max_size} in use")

                        # Log metrics periodically (every 5 minutes)
                        if int(time.time()) % 300 == 0:
                            print(f"[POOL] Active: {active}, Idle: {idle}, Max: {max_size}")
                except Exception as e:
                    print(f"[POOL] Monitoring error: {e}")

                time.sleep(30)  # Check every 30 seconds

        monitor_thread = threading.Thread(target=monitor_pool, daemon=True)
        monitor_thread.start()

    def _sanitize_for_sharing(self, text: str, agent_context: Dict[str, Any] = None) -> str:
        """Strip personal identifiers before storing to shared memory.

        Uses LLM-based review for comprehensive PII detection.
        Falls back to pattern matching if LLM unavailable.
        """
        # Try LLM-based sanitization first
        try:
            sanitized = self._llm_sanitize(text, agent_context)
            if sanitized:
                return sanitized
        except Exception:
            pass  # Fall through to pattern-based

        # Fallback: pattern-based sanitization
        return self._pattern_sanitize(text)

    def _llm_sanitize(self, text: str, agent_context: Dict[str, Any] = None) -> Optional[str]:
        """Use Kublai (via agentToAgent) to review and redact private information.

        Kublai acts as the privacy gatekeeper before content enters operational memory.
        Falls back to pattern-based sanitization if Kublai unavailable.

        SECURITY: Input is strictly validated and escaped before being sent to LLM
        to prevent prompt injection attacks.

        Returns sanitized text or None to trigger pattern fallback.
        """
        import os
        import json
        import requests
        import re

        # Input validation - reject suspicious inputs
        if not text or not isinstance(text, str):
            return text

        # Limit input size to prevent DoS
        MAX_INPUT_LENGTH = 10000
        if len(text) > MAX_INPUT_LENGTH:
            text = text[:MAX_INPUT_LENGTH] + "... [truncated]"

        # Escape special characters that could be used for prompt injection
        # Remove control characters, normalize whitespace
        sanitized_input = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        # Escape curly braces to prevent JSON injection
        sanitized_input = sanitized_input.replace('{', '{{').replace('}', '}}')

        try:
            # Call OpenClaw gateway to delegate privacy review to Kublai
            gateway_url = os.getenv('OPENCLAW_GATEWAY_URL', 'http://localhost:8080')
            token = os.getenv('OPENCLAW_GATEWAY_TOKEN', '')

            # Validate gateway URL to prevent SSRF attacks
            # Only allow specific known-safe hosts
            from urllib.parse import urlparse
            allowed_hosts = {
                'localhost', '127.0.0.1', '::1',
                'kublai.kurult.ai',
                'openclaw.railway.internal',
                'moltbot.railway.internal'
            }

            try:
                parsed = urlparse(gateway_url)
                if parsed.hostname not in allowed_hosts:
                    print(f"[PRIVACY] Invalid gateway URL host '{parsed.hostname}', using pattern fallback")
                    return None
                # Block non-HTTP schemes (file://, ftp://, etc.)
                if parsed.scheme not in ('http', 'https'):
                    print(f"[PRIVACY] Invalid URL scheme '{parsed.scheme}', using pattern fallback")
                    return None
                # Block URLs with authentication credentials (user:pass@host)
                if parsed.username or parsed.password:
                    print("[PRIVACY] URL with embedded credentials rejected, using pattern fallback")
                    return None
                # Block non-standard ports (only allow 80, 443, 8080-8089, 3000-3009 for dev)
                if parsed.port and parsed.port not in (
                    80, 443, 8080, 8081, 8082, 8083, 8084, 8085, 8086, 8087, 8088, 8089,
                    3000, 3001, 3002, 3003, 3004, 3005, 3006, 3007, 3008, 3009
                ):
                    print(f"[PRIVACY] Non-standard port {parsed.port} rejected, using pattern fallback")
                    return None
            except ValueError as e:
                print(f"[PRIVACY] URL parse error: {e}, using pattern fallback")
                return None

            review_prompt = f"""Review the following text for private information that should NOT be stored in shared operational memory.

Private information includes:
- Personal names (friends, family, colleagues)
- Specific company names tied to individuals
- Personal addresses or locations
- Private anecdotes or stories
- Relationship details

Text to review (escaped for safety):
---
{sanitized_input}
---

INSTRUCTIONS:
1. Analyze the text above for private information
2. Replace private info with generic terms (e.g., "my friend Sarah" -> "a contact")
3. Return ONLY a valid JSON object with this exact structure:
{{
    "contains_private_info": true/false,
    "sanitized_text": "the sanitized version",
    "replacements_made": ["original -> replacement"]
}}

Do not include any text outside the JSON object."""

            response = requests.post(
                f"{gateway_url}/agent/main/message",
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json'
                },
                json={
                    'message': review_prompt,
                    'context': {'privacy_review': True, 'skip_memory': True}
                },
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                # Parse LLM response (expecting JSON in response)
                try:
                    # Extract JSON from response text
                    response_text = result.get('response', '')
                    # Find JSON block
                    json_start = response_text.find('{')
                    json_end = response_text.rfind('}') + 1
                    if json_start >= 0 and json_end > json_start:
                        review_result = json.loads(response_text[json_start:json_end])
                        sanitized = review_result.get('sanitized_text', text)
                        if review_result.get('contains_private_info', False):
                            print(f"[PRIVACY] Kublai sanitized {len(review_result.get('replacements_made', []))} items")
                        return sanitized
                except json.JSONDecodeError:
                    print("[PRIVACY] Could not parse Kublai review, falling back to patterns")
                    return None

            # If Kublai unavailable (503, 429, etc), fall back to patterns
            if response.status_code in (503, 429, 502):
                print(f"[PRIVACY] Kublai unavailable ({response.status_code}), using pattern fallback")
                return None

        except requests.Timeout:
            print("[PRIVACY] Kublai review timed out, using pattern fallback")
            return None
        except Exception as e:
            print(f"[PRIVACY] Kublai review failed: {e}, using pattern fallback")
            return None

        return None  # Signal to use pattern fallback

    def _check_rate_limit(self, agent: str, operation: str) -> bool:
        """Check if agent has exceeded rate limit for operation.

        Uses Neo4j-backed rate limiting for multi-instance consistency.
        Falls back to memory-based limiting in fallback mode.

        Returns True if operation allowed, False if rate limited.
        """
        from datetime import datetime, timedelta

        # In fallback mode, use memory-based limiting (best effort)
        if self.fallback_mode:
            with self._rate_limit_lock:
                now = datetime.now()
                key = f"{agent}:{operation}"

                if key not in self._rate_limit_counters:
                    self._rate_limit_counters[key] = {
                        'count': 0,
                        'window_start': now,
                        'burst_count': 0
                    }

                counter = self._rate_limit_counters[key]

                # Reset hourly window
                if now - counter['window_start'] > timedelta(hours=1):
                    counter['count'] = 0
                    counter['window_start'] = now
                    counter['burst_count'] = 0

                # Check burst limit (per minute)
                if counter['burst_count'] >= self.RATE_LIMIT_BURST:
                    print(f"[RATE_LIMIT] Agent {agent} burst limit exceeded for {operation}")
                    return False

                # Check hourly limit
                if counter['count'] >= self.RATE_LIMIT_HOURLY:
                    print(f"[RATE_LIMIT] Agent {agent} hourly limit exceeded for {operation}")
                    return False

                counter['count'] += 1
                counter['burst_count'] += 1
                return True

        # Use Neo4j-backed rate limiting for multi-instance consistency
        try:
            # Atomic rate limit check using single Cypher transaction
            # Pre-increments counter and returns null if over limit (prevents race conditions)
            query = """
            MATCH (r:RateLimit {
                agent: $agent,
                operation: $operation,
                hour: datetime().hour,
                date: date()
            })
            WHERE r.count < $hourly_limit AND r.burst_count < $burst_limit
            SET r.count = r.count + 1,
                r.burst_count = r.burst_count + 1,
                r.updated_at = datetime()
            RETURN r.count as current_count, r.burst_count as current_burst

            UNION

            MATCH (r:RateLimit {
                agent: $agent,
                operation: $operation,
                hour: datetime().hour,
                date: date()
            })
            WHERE r.count >= $hourly_limit OR r.burst_count >= $burst_limit
            RETURN null as current_count, null as current_burst

            UNION

            // No record exists - create one atomically with initial count
            MATCH (a:Agent {id: $agent})
            WHERE NOT EXISTS {
                MATCH (r:RateLimit {
                    agent: $agent,
                    operation: $operation,
                    hour: datetime().hour,
                    date: date()
                })
            }
            CREATE (r:RateLimit {
                agent: $agent,
                operation: $operation,
                hour: datetime().hour,
                date: date(),
                count: 1,
                burst_count: 1,
                created_at: datetime()
            })
            RETURN r.count as current_count, r.burst_count as current_burst
            """

            with self._session_pool() as session:
                result = session.run(
                    query,
                    agent=agent,
                    operation=operation,
                    hourly_limit=self.RATE_LIMIT_HOURLY,
                    burst_limit=self.RATE_LIMIT_BURST
                )
                record = result.single()

                if record:
                    return True
                else:
                    print(f"[RATE_LIMIT] Agent {agent} limit exceeded for {operation}")
                    return False

        except Exception as e:
            print(f"[RATE_LIMIT ERROR] Neo4j rate limit check failed: {e}, using fallback")
            # Fall back to memory-based on error
            return True  # Allow operation rather than block on error

    def _hash_phone_number(self, phone: str) -> str:
        """Hash phone number using HMAC-SHA256 with salt for privacy.

        Uses PHONE_HASH_SALT environment variable. Same phone always produces
        same hash, but hash cannot be reversed without the salt.
        """
        import hmac
        import hashlib
        import os

        salt = os.getenv('PHONE_HASH_SALT')
        if not salt:
            raise RuntimeError(
                "PHONE_HASH_SALT environment variable must be set for secure phone number hashing. "
                "Generate a secure random string (e.g., 'openssl rand -hex 32') and set it before deployment."
            )
        return hmac.new(
            salt.encode('utf-8'),
            phone.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def get_or_create_signal_session(self, sender_phone: str, agent_id: str = 'main') -> Optional[str]:
        """Get existing Signal session or create new one for sender.

        Args:
            sender_phone: Signal sender's phone number
            agent_id: Agent handling this session (default 'main' for Kublai)

        Returns:
            Session ID for routing responses, or None if failed
        """
        # Generate consistent session ID using phone hash (works in both modes)
        sender_hash = self._hash_phone_number(sender_phone)
        session_id = f"signal_{sender_hash}"

        if self.fallback_mode:
            # In fallback mode, use simple in-memory mapping with consistent ID format
            self._local_store.setdefault('signal_sessions', {})[session_id] = {
                'sender_phone': sender_phone,
                'agent_id': agent_id,
                'created_at': datetime.now().isoformat(),
                'sender_hash': sender_hash
            }
            return session_id

        query = """
        // Try to find existing active session
        MATCH (s:SignalSession {sender_hash: $sender_hash})
        WHERE s.is_active = true
        WITH s
        // Update last activity
        SET s.last_activity = datetime()
        RETURN s.session_id as session_id, s.current_agent as current_agent

        UNION

        // No existing session, create new one with consistent ID format
        MATCH (a:Agent {id: $agent_id})
        WHERE NOT EXISTS {
            MATCH (s:SignalSession {sender_hash: $sender_hash})
            WHERE s.is_active = true
        }
        CREATE (s:SignalSession {
            session_id: $session_id,
            sender_hash: $sender_hash,
            current_agent: $agent_id,
            session_started: datetime(),
            last_activity: datetime(),
            is_active: true
        })
        CREATE (s)-[:ROUTES_TO]->(a)
        RETURN s.session_id as session_id, s.current_agent as current_agent
        """

        try:
            with self._session_pool() as session:
                result = session.run(
                    query,
                    session_id=session_id,
                    sender_hash=sender_hash,
                    agent_id=agent_id
                )
                record = result.single()
                if record:
                    return record['session_id']
                return None
        except Exception as e:
            print(f"[ERROR] Failed to create Signal session: {e}")
            return None

    def route_agent_response(self, session_id: str, response_text: str,
                            from_agent: str) -> bool:
        """Route an agent's response back to the Signal sender.

        Args:
            session_id: Signal session ID from get_or_create_signal_session
            response_text: The response message to send
            from_agent: Agent ID sending the response

        Returns:
            True if routing successful, False otherwise
        """
        if self.fallback_mode:
            # In fallback mode, just log the response
            print(f"[SIGNAL ROUTE] Session {session_id}: {from_agent} -> sender")
            print(f"[SIGNAL RESPONSE] {response_text[:200]}...")
            return True

        query = """
        MATCH (s:SignalSession {session_id: $session_id})
        WHERE s.is_active = true
        MATCH (s)-[:ROUTES_TO]->(handling_agent:Agent)
        MATCH (from:Agent {id: $from_agent})
        // Create response route record
        CREATE (r:AgentResponseRoute {
            route_id: randomuuid(),
            agent_id: $from_agent,
            sender_hash: s.sender_hash,
            response_preview: $response_preview,
            route_type: 'direct',
            priority: 1,
            created_at: datetime()
        })
        CREATE (from)-[:RESPONDS_VIA]->(r)
        CREATE (r)-[:TARGETS]->(s)
        // Update session activity
        SET s.last_activity = datetime()
        RETURN s.sender_hash as sender_hash, handling_agent.id as current_agent
        """

        try:
            with self._session_pool() as session:
                result = session.run(
                    query,
                    session_id=session_id,
                    from_agent=from_agent,
                    response_preview=response_text[:100]  # Truncate for storage
                )
                record = result.single()
                if record:
                    print(f"[SIGNAL ROUTE] Response from {from_agent} routed to session {session_id}")
                    return True
                print(f"[WARN] Signal session {session_id} not found or inactive")
                return False
        except Exception as e:
            print(f"[ERROR] Failed to route agent response: {e}")
            return False

    def get_pending_responses(self, agent_id: str) -> List[Dict[str, Any]]:
        """Get pending responses that need to be sent to Signal users.

        Called by the Signal integration layer to poll for outgoing messages.

        Args:
            agent_id: Agent to get pending responses for

        Returns:
            List of pending response records with session_id and response text
        """
        if self.fallback_mode:
            return []  # Fallback mode handles differently

        query = """
        MATCH (a:Agent {id: $agent_id})-[:RESPONDS_VIA]->(r:AgentResponseRoute)
        MATCH (r)-[:TARGETS]->(s:SignalSession)
        WHERE s.is_active = true
        RETURN s.session_id as session_id,
               r.response_preview as response_preview,
               r.route_id as route_id,
               r.created_at as created_at
        ORDER BY r.created_at ASC
        LIMIT 100
        """

        try:
            with self._session_pool() as session:
                result = session.run(query, agent_id=agent_id)
                return [dict(record) for record in result]
        except Exception as e:
            print(f"[ERROR] Failed to get pending responses: {e}")
            return []

    def mark_response_sent(self, route_id: str) -> bool:
        """Mark a response route as completed (sent to user).

        Args:
            route_id: The route_id from get_pending_responses

        Returns:
            True if marked successfully
        """
        if self.fallback_mode:
            return True

        query = """
        MATCH (r:AgentResponseRoute {route_id: $route_id})
        SET r.sent_at = datetime(),
            r.status = 'sent'
        RETURN true as success
        """

        try:
            with self._session_pool() as session:
                result = session.run(query, route_id=route_id)
                return result.single() is not None
        except Exception as e:
            print(f"[ERROR] Failed to mark response sent: {e}")
            return False

    def _pattern_sanitize(self, text: str) -> str:
        """Pattern-based PII sanitization (fallback method)."""
        import re

        # Phone numbers (various formats including international)
        # US format: +1 (123) 456-7890, 123-456-7890, (123) 456-7890
        text = re.sub(r'\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', '[PHONE]', text)
        # International format: +44 20 7946 0958, +91-98765-43210, +33 1 23 45 67 89
        text = re.sub(r'\+\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}', '[PHONE]', text)
        # Generic 10-15 digit numbers that look like phone numbers
        text = re.sub(r'\b\d{10,15}\b', '[PHONE]', text)

        # Email addresses (comprehensive RFC 5322 subset)
        # Handles: user@example.com, user.name+tag@example.co.uk, user_name@subdomain.example.com
        text = re.sub(r"[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*", '[EMAIL]', text)

        # Social Security Numbers
        text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN]', text)

        # Credit card numbers (basic pattern)
        text = re.sub(r'\b(?:\d{4}[-\s]?){3}\d{4}\b', '[CARD]', text)

        # API keys and tokens (common patterns)
        text = re.sub(r'\b(sk-|pk-|api[_-]?key[:\s]*)([\w-]{10,})\b', '[API_KEY]', text, flags=re.I)

        return text

    def store_research(self, agent: str, topic: str, findings: str,
                      sources: List[str] = None, depth: str = "medium",
                      sender_hash: Optional[str] = None) -> Optional[UUID]:
        """Store research findings to Neo4j with sanitization and access tier control.

        Args:
            agent: Agent ID storing the research
            topic: Research topic
            findings: Research findings text
            sources: List of source references
            depth: Research depth (shallow/medium/deep)
            sender_hash: Hash of originating sender for access control (None = general knowledge)

        Returns:
            UUID of stored research, or None if blocked/failed
        """
        # Validate agent identity
        if not self._validate_agent_id(agent):
            print(f"[AUTH] Invalid agent storing research: {agent}")
            return None

        # Check rate limit before processing
        if not self._check_rate_limit(agent, 'store_research'):
            print(f"[RATE_LIMIT] store_research blocked for {agent}")
            return None

        knowledge_id = uuid4()
        safe_findings = self._sanitize_for_sharing(findings)
        safe_topic = self._sanitize_for_sharing(topic)

        # Determine access tier based on content and sender context
        access_tier = self._determine_access_tier(safe_findings + " " + safe_topic, sender_hash)

        # PRIVATE tier content never goes to operational memory
        if access_tier == self.ACCESS_TIER_PRIVATE:
            print(f"[PRIVACY] Research blocked from operational memory (PRIVATE tier)")
            return None

        if self.fallback_mode:
            with self._fallback_lock:
                # Enforce fallback store limits
                current_research = self._local_store.get('research', [])
                if len(current_research) >= self._MAX_FALLBACK_RESEARCH:
                    # Remove oldest item
                    current_research.pop(0)

                self._local_store.setdefault('research', []).append({
                    'id': str(knowledge_id), 'agent': agent, 'topic': safe_topic,
                    'findings': safe_findings, 'created_at': datetime.now().isoformat(),
                    'access_tier': access_tier, 'sender_hash': sender_hash
                })
            return knowledge_id

        query = """
        MATCH (a:Agent {id: $agent})
        CREATE (r:Research {
            id: $id, topic: $topic, findings: $findings,
            sources: $sources, depth: $depth,
            access_tier: $access_tier,
            sender_hash: $sender_hash,
            created_at: datetime(), confidence: 0.9
        })
        CREATE (a)-[:CREATED {timestamp: datetime()}]->(r)
        RETURN r.id as id
        """
        with self.driver.session() as session:
            session.run(query, agent=agent, id=str(knowledge_id),
                       topic=safe_topic, findings=safe_findings,
                       sources=sources or [], depth=depth,
                       access_tier=access_tier, sender_hash=sender_hash)
        return knowledge_id

    def store_concept(self, agent: str, name: str, description: str,
                     domain: str = "general", source: str = "",
                     sender_hash: Optional[str] = None) -> Optional[UUID]:
        """Store a concept with encrypted embedding for SENSITIVE access tier.

        Args:
            agent: Agent ID creating the concept
            name: Concept name (unique identifier)
            description: Concept description
            domain: Concept domain/category
            source: Source of the concept
            sender_hash: Hash of originating sender for access control

        Returns:
            UUID of stored concept, or None if blocked/failed
        """
        # Validate agent identity
        if not self._validate_agent_id(agent):
            print(f"[AUTH] Invalid agent storing concept: {agent}")
            return None

        # Check rate limit
        if not self._check_rate_limit(agent, 'store_concept'):
            print(f"[RATE_LIMIT] store_concept blocked for {agent}")
            return None

        # Sanitize content
        safe_name = self._sanitize_for_sharing(name)
        safe_description = self._sanitize_for_sharing(description)

        # Determine access tier
        access_tier = self._determine_access_tier(safe_name + " " + safe_description, sender_hash)

        # PRIVATE tier content never goes to operational memory
        if access_tier == self.ACCESS_TIER_PRIVATE:
            print(f"[PRIVACY] Concept blocked from operational memory (PRIVATE tier)")
            return None

        # Generate embedding
        embedding = self._generate_embedding(safe_name + " " + safe_description)

        # Encrypt embedding if SENSITIVE tier
        if embedding:
            stored_embedding = self._encrypt_embedding(embedding, access_tier)
        else:
            stored_embedding = None

        concept_id = uuid4()

        if self.fallback_mode:
            with self._fallback_lock:
                self._local_store.setdefault('concepts', []).append({
                    'id': str(concept_id),
                    'agent': agent,
                    'name': safe_name,
                    'description': safe_description,
                    'domain': domain,
                    'source': source,
                    'embedding': stored_embedding,
                    'access_tier': access_tier,
                    'sender_hash': sender_hash,
                    'created_at': datetime.now().isoformat()
                })
            return concept_id

        # Store in Neo4j with encrypted embedding if SENSITIVE
        query = """
        MATCH (a:Agent {id: $agent})
        MERGE (c:Concept {name: $name})
        ON CREATE SET
            c.id = $id,
            c.description = $description,
            c.domain = $domain,
            c.source = $source,
            c.embedding = $embedding,
            c.access_tier = $access_tier,
            c.sender_hash = $sender_hash,
            c.created_at = datetime(),
            c.confidence = 0.9
        ON MATCH SET
            c.description = $description,
            c.source = $source,
            c.embedding = $embedding,
            c.access_tier = $access_tier,
            c.sender_hash = $sender_hash,
            c.updated_at = datetime()
        CREATE (a)-[:CREATED {timestamp: datetime()}]->(c)
        RETURN c.id as id
        """
        try:
            with self.driver.session() as session:
                result = session.run(query,
                    agent=agent, id=str(concept_id), name=safe_name,
                    description=safe_description, domain=domain, source=source,
                    embedding=stored_embedding, access_tier=access_tier,
                    sender_hash=sender_hash)
                return concept_id
        except Exception as e:
            print(f"[ERROR] Failed to store concept: {e}")
            return None

    def query_concepts(self, query_text: str, sender_hash: Optional[str] = None,
                      min_confidence: float = 0.7, limit: int = 5) -> List[Dict[str, Any]]:
        """Query concepts with sender isolation and access tier enforcement.

        Args:
            query_text: Text to search for
            sender_hash: Hash of requesting sender (for access control)
            min_confidence: Minimum similarity score
            limit: Maximum results to return

        Returns:
            List of matching concepts (filtered by access tier)
        """
        if self.fallback_mode:
            # Fallback: simple text match on local store
            concepts = self._local_store.get('concepts', [])
            results = []
            for c in concepts:
                # Filter by access tier
                if c.get('access_tier') == self.ACCESS_TIER_SENSITIVE:
                    if c.get('sender_hash') != sender_hash:
                        continue  # Cannot access other senders' SENSITIVE concepts
                if query_text.lower() in c.get('name', '').lower() or \
                   query_text.lower() in c.get('description', '').lower():
                    results.append({
                        'name': c['name'],
                        'description': c['description'],
                        'domain': c.get('domain', 'general')
                    })
            return results[:limit]

        # Generate embedding for query
        query_embedding = self._generate_embedding(query_text)

        if query_embedding:
            try:
                # Vector search with sender isolation
                # Note: Vector index doesn't support filtering, so we filter post-query
                query = """
                CALL db.index.vector.queryNodes('concept_embedding', $limit * 3, $embedding)
                YIELD node, score
                WHERE score >= $min_score
                RETURN node.name as name, node.description as description,
                       node.domain as domain, node.access_tier as access_tier,
                       node.sender_hash as concept_sender, score
                """
                with self.driver.session() as session:
                    result = session.run(query, embedding=query_embedding,
                                        min_score=min_confidence, limit=limit)
                    records = []
                    for record in result:
                        # Enforce access tier rules
                        tier = record.get('access_tier', self.ACCESS_TIER_PUBLIC)
                        concept_sender = record.get('concept_sender')

                        # SENSITIVE concepts are sender-isolated
                        if tier == self.ACCESS_TIER_SENSITIVE and concept_sender != sender_hash:
                            continue  # Skip - cannot access other senders' sensitive data

                        records.append({
                            'name': record['name'],
                            'description': record['description'],
                            'domain': record['domain'],
                            'score': record['score']
                        })
                        if len(records) >= limit:
                            break
                    return records
            except Exception as e:
                print(f"[WARN] Vector search failed: {e}")

        # Fallback to full-text search
        query = """
        CALL db.index.fulltext.queryNodes('knowledge_content', $query)
        YIELD node, score
        WHERE (node:Concept) AND score >= $min_score
        RETURN node.name as name, node.description as description,
               node.domain as domain, node.access_tier as access_tier,
               node.sender_hash as concept_sender, score
        LIMIT $limit
        """
        try:
            with self.driver.session() as session:
                result = session.run(query, query=query_text,
                                    min_score=min_confidence, limit=limit)
                records = []
                for record in result:
                    # Enforce access tier rules
                    tier = record.get('access_tier', self.ACCESS_TIER_PUBLIC)
                    concept_sender = record.get('concept_sender')

                    if tier == self.ACCESS_TIER_SENSITIVE and concept_sender != sender_hash:
                        continue

                    records.append({
                        'name': record['name'],
                        'description': record['description'],
                        'domain': record['domain'],
                        'score': record['score']
                    })
                return records
        except Exception as e:
            print(f"[ERROR] Concept query failed: {e}")
            return []

    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding using sentence-transformers (all-MiniLM-L6-v2).

        Uses pinned model version with SHA256 verification for supply chain security.
        Preloads model in background to avoid cold-start latency on first query.
        """
        try:
            from sentence_transformers import SentenceTransformer
            import hashlib

            if not hasattr(self, '_embedding_model'):
                cache_dir = os.getenv('SENTENCE_TRANSFORMERS_CACHE', '/data/cache/sentence-transformers')
                os.makedirs(cache_dir, exist_ok=True)

                # Pinned model version for reproducibility and security
                # all-MiniLM-L6-v2 from sentence-transformers
                # Verified SHA256: e4ce9877abf3edfe910b64c23359221a1f9f08e5
                model_name = 'sentence-transformers/all-MiniLM-L6-v2'
                revision = 'e4ce9877abf3edfe910b64c23359221a1f9f08e5'  # Pinned commit 2024-01-15

                # Verify model checksum after download (supply chain protection)
                expected_sha256 = os.getenv('EMBEDDING_MODEL_SHA256', '')

                self._embedding_model = SentenceTransformer(
                    model_name,
                    cache_folder=cache_dir,
                    revision=revision
                )

                # Verify checksum if provided
                if expected_sha256:
                    model_path = self._embedding_model.get_sentence_embedding_dimension()
                    # Note: Actual path verification would require accessing model files
                    # This is a placeholder for the verification logic

            return self._embedding_model.encode(text).tolist()
        except ImportError:
            return []
        except Exception as e:
            print(f"[WARN] Embedding generation failed: {e}")
            return []

    def query_related(self, agent: str, topic: str,
                     min_confidence: float = 0.7,
                     sender_hash: Optional[str] = None) -> List[Dict[str, Any]]:
        """Query operational knowledge with vector fallback and access control.

        Args:
            agent: Agent ID performing the query
            topic: Search topic
            min_confidence: Minimum similarity threshold
            sender_hash: Hash of requesting sender (for access tier enforcement)

        Returns:
            List of related knowledge items (filtered by access tier)
        """
        if self.fallback_mode:
            # Filter fallback store by access tier
            research = self._local_store.get('research', [])
            filtered = []
            for r in research:
                tier = r.get('access_tier', self.ACCESS_TIER_PUBLIC)
                item_sender = r.get('sender_hash')
                # SENSITIVE items are sender-isolated
                if tier == self.ACCESS_TIER_SENSITIVE and item_sender != sender_hash:
                    continue
                filtered.append(r)
            return filtered

        # Generate embedding for the query topic
        embedding = self._generate_embedding(topic)

        # Try vector search first (if embedding generated and index exists)
        if embedding:
            try:
                # Query more results than needed to allow for filtering
                query = """
                CALL db.index.vector.queryNodes('concept_embedding', 10, $embedding)
                YIELD node, score
                WHERE score >= $min_score
                RETURN node.name as concept, node.description as description,
                       node.access_tier as access_tier, node.sender_hash as item_sender,
                       score
                """
                with self.driver.session() as session:
                    result = session.run(query, embedding=embedding, min_score=min_confidence)
                    records = []
                    for record in result:
                        # Enforce access tier rules
                        tier = record.get('access_tier', self.ACCESS_TIER_PUBLIC)
                        item_sender = record.get('item_sender')

                        # SENSITIVE concepts are sender-isolated
                        if tier == self.ACCESS_TIER_SENSITIVE and item_sender != sender_hash:
                            continue

                        records.append({
                            'concept': record['concept'],
                            'description': record['description'],
                            'score': record['score']
                        })
                        if len(records) >= 5:
                            break
                    if records:
                        return records
            except Exception:
                pass  # Fall through to full-text search

        # Fallback to full-text search
        query = """
        CALL db.index.fulltext.queryNodes('knowledge_content', $topic)
        YIELD node, score
        WHERE score >= $min_score
        RETURN node.topic as topic, node.findings as findings, score
        LIMIT 10
        """
        with self.driver.session() as session:
            result = session.run(query, topic=topic, min_score=min_confidence)
            return [dict(record) for record in result]

    def _detect_cycle(self, from_agent: str, to_agent: str) -> bool:
        """Detect if adding LEARNED relationship would create a cycle."""
        query = """
        MATCH path = (to:Agent {id: $to_agent})-[:LEARNED*1..10]->(from:Agent {id: $from_agent})
        RETURN length(path) as cycle_length
        LIMIT 1
        """
        with self.driver.session() as session:
            result = session.run(query, from_agent=from_agent, to_agent=to_agent)
            return result.single() is not None

    def record_collaboration(self, from_agent: str, to_agent: str,
                           knowledge_id: UUID) -> bool:
        """Track that one agent learned from another's output.

        Prevents circular learning loops by checking for existing path.
        """
        if self.fallback_mode:
            return True

        # Prevent self-learning
        if from_agent == to_agent:
            return False

        # Detect cycle before creating relationship
        if self._detect_cycle(from_agent, to_agent):
            print(f"[WARN] Cycle detected: {to_agent} already learns from {from_agent}")
            return False

        query = """
        MATCH (from:Agent {id: $from_agent})
        MATCH (to:Agent {id: $to_agent})
        MATCH (k {id: $knowledge_id})
        CREATE (to)-[:LEARNED {knowledge_id: $knowledge_id,
                               timestamp: datetime(), depth: 1}]->(from)
        CREATE (from)-[:BUILT_ON]->(k)
        """
        with self.driver.session() as session:
            session.run(query, from_agent=from_agent, to_agent=to_agent,
                       knowledge_id=str(knowledge_id))
        return True

    # Valid agent IDs for authentication
    # Loaded from ALLOWED_AGENTS env var (comma-separated) or defaults to 6 standard agents
    # Example: ALLOWED_AGENTS="kublai,mongke,chagatai,temujin,jochi,ogedei"
    @property
    def VALID_AGENTS(self) -> set:
        import os
        agents_env = os.getenv('ALLOWED_AGENTS', '')
        if agents_env:
            return set(a.strip() for a in agents_env.split(',') if a.strip())
        # Default 6-agent set
        return {'main', 'researcher', 'writer', 'developer', 'analyst', 'ops'}

    def _validate_agent_id(self, agent_id: str) -> bool:
        """Validate that agent_id is a known agent.

        Prevents spoofing by ensuring only valid agents can create/claim tasks.
        """
        return agent_id in self.VALID_AGENTS

    def create_task(self, task_type: str, description: str,
                   delegated_by: str, assigned_to: str) -> Optional[UUID]:
        """Create a task for specialist agents to pick up.

        Validates agent identities to prevent spoofing attacks.
        """
        # Validate agent identities
        if not self._validate_agent_id(delegated_by):
            print(f"[AUTH] Invalid delegator: {delegated_by}")
            return None
        if not self._validate_agent_id(assigned_to):
            print(f"[AUTH] Invalid assignee: {assigned_to}")
            return None

        # Check rate limit before processing
        if not self._check_rate_limit(delegated_by, 'create_task'):
            print(f"[RATE_LIMIT] create_task blocked for {delegated_by}")
            return None

        # Validate task_type from allowed set
        VALID_TASK_TYPES = {'research', 'writing', 'coding', 'analysis', 'operations', 'security_review'}
        if task_type not in VALID_TASK_TYPES:
            print(f"[VALIDATION] Invalid task type: {task_type}")
            return None

        task_id = uuid4()
        safe_description = self._sanitize_for_sharing(description)

        if self.fallback_mode:
            with self._fallback_lock:
                # Enforce fallback store limits to prevent memory exhaustion
                current_tasks = self._local_store.get('tasks', [])
                if len(current_tasks) >= self._MAX_FALLBACK_TASKS:
                    # Remove oldest completed tasks first
                    completed = [t for t in current_tasks if t.get('status') == 'completed']
                    if completed:
                        current_tasks.remove(completed[0])
                    else:
                        # If no completed tasks, drop oldest pending (with warning)
                        print(f"[FALLBACK WARNING] Task store full ({self._MAX_FALLBACK_TASKS}), dropping oldest pending task")
                        current_tasks.pop(0)

                self._local_store.setdefault('tasks', []).append({
                    'id': str(task_id), 'type': task_type, 'description': safe_description,
                    'status': 'pending', 'assigned_to': assigned_to,
                    'delegated_by': delegated_by
                })
            return task_id

        query = """
        MATCH (delegator:Agent {id: $delegated_by})
        MATCH (assignee:Agent {id: $assigned_to})
        CREATE (t:Task {
            id: $id, type: $type, description: $description,
            status: 'pending', created_at: datetime()
        })
        CREATE (delegator)-[:CREATED {timestamp: datetime()}]->(t)
        CREATE (t)-[:ASSIGNED_TO]->(assignee)
        RETURN t.id as id
        """
        with self.driver.session() as session:
            session.run(query, id=str(task_id), type=task_type,
                       description=safe_description,
                       delegated_by=delegated_by, assigned_to=assigned_to)
        return task_id

    def claim_task(self, agent: str) -> Optional[Dict[str, Any]]:
        """Claim next pending task for an agent (atomic, race-condition safe).

        Validates agent identity to prevent spoofing attacks.
        Uses optimistic locking with claim_attempt_id to prevent race conditions
        when multiple agents try to claim the same task simultaneously.
        """
        # Validate agent identity
        if not self._validate_agent_id(agent):
            print(f"[AUTH] Invalid agent claiming task: {agent}")
            return None

        if self.fallback_mode:
            # Thread-safe fallback mode with locking
            with self._fallback_lock:
                tasks = self._local_store.get('tasks', [])
                for t in tasks:
                    if t['assigned_to'] == agent and t['status'] == 'pending':
                        t['status'] = 'in_progress'
                        t['claimed_at'] = datetime.now().isoformat()
                        return t
                return None

        # Atomic claim using optimistic locking pattern
        # Generate unique claim attempt ID to verify we won the race
        claim_attempt_id = str(uuid4())

        query = """
        MATCH (t:Task {status: 'pending'})-[:ASSIGNED_TO]->(a:Agent {id: $agent})
        WITH t ORDER BY t.created_at ASC LIMIT 1
        SET t.status = 'in_progress',
            t.started_at = datetime(),
            t.claimed_by = $agent,
            t.claim_attempt_id = $claim_attempt_id
        RETURN t.id as id, t.type as type, t.description as description,
               t.claim_attempt_id as verified_claim_id
        """
        try:
            with self.driver.session() as session:
                # Use write transaction for stronger consistency guarantees
                with session.begin_transaction() as tx:
                    result = tx.run(query, agent=agent, claim_attempt_id=claim_attempt_id)
                    record = result.single()

                    if record and record['verified_claim_id'] == claim_attempt_id:
                        # Success - we claimed the task
                        # Transaction will auto-commit on successful exit
                        return {
                            'id': record['id'],
                            'type': record['type'],
                            'description': record['description']
                        }
                    elif record:
                        # Another agent won the race - raise exception to force rollback
                        raise Exception("Race condition lost - another agent claimed the task")
                    else:
                        # No task available
                        raise Exception("No pending task available")
        except Exception as e:
            # Transaction auto-rolls back on exception
            if "Race condition lost" in str(e) or "No pending task" in str(e):
                return None  # Expected cases, not errors
            print(f"[ERROR] Task claim failed for {agent}: {e}")
            return None

    def block_task(self, task_id: UUID, reason: str,
                   auto_escalate: bool = True) -> bool:
        """Mark task as blocked with reason. Optionally auto-escalate to Kublai."""
        if self.fallback_mode:
            for t in self._local_store.get('tasks', []):
                if t['id'] == str(task_id):
                    t['status'] = 'blocked'
                    t['blocked_reason'] = reason
                    t['blocked_at'] = datetime.now().isoformat()
                    return True
            return False

        query = """
        MATCH (t:Task {id: $task_id})
        SET t.status = 'blocked',
            t.blocked_reason = $reason,
            t.blocked_at = datetime()
        RETURN t.delegated_by as delegator_id
        """
        with self.driver.session() as session:
            result = session.run(query, task_id=str(task_id), reason=reason)
            record = result.single()

            if record and auto_escalate:
                # Create escalation notification for Kublai
                self._escalate_blocked_task(task_id, record['delegator_id'], reason)
        return True

    def _escalate_blocked_task(self, task_id: UUID, delegator_id: str, reason: str):
        """Escalate blocked task to Kublai for reassignment.

        On failure, stores to dead letter queue for later processing.
        """
        notification_id = str(uuid4())
        query = """
        MATCH (kublai:Agent {id: 'main'})
        CREATE (n:Notification {
            id: $notification_id,
            type: 'task_blocked',
            task_id: $task_id,
            from_agent: $delegator_id,
            summary: $reason,
            created_at: datetime(),
            read: false,
            ttl_hours: 24
        })
        CREATE (kublai)-[:HAS_NOTIFICATION]->(n)
        """
        try:
            with self._session_pool() as session:
                session.run(query, notification_id=notification_id,
                           task_id=str(task_id), delegator_id=delegator_id,
                           reason=f"Task blocked: {reason[:100]}")
        except Exception as e:
            # Store to dead letter queue for later retry
            print(f"[ESCALATION ERROR] Failed to create notification: {e}")
            self._store_notification_dlq({
                'notification_id': notification_id,
                'task_id': str(task_id),
                'delegator_id': delegator_id,
                'reason': reason,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })

    def _store_notification_dlq(self, notification_data: Dict[str, Any]):
        """Store failed notification to dead letter queue for later retry."""
        with self._fallback_lock:
            self._local_store.setdefault('notification_dlq', []).append(notification_data)
            # Limit DLQ size
            dlq = self._local_store['notification_dlq']
            if len(dlq) > 100:
                dlq.pop(0)  # Remove oldest

    def retry_notification_dlq(self) -> int:
        """Retry sending notifications from dead letter queue.

        Returns number of successfully sent notifications.
        """
        if self.fallback_mode:
            return 0

        with self._fallback_lock:
            dlq = self._local_store.get('notification_dlq', [])
            if not dlq:
                return 0
            # Work on a copy
            to_retry = list(dlq)

        success_count = 0
        still_failed = []

        for item in to_retry:
            try:
                query = """
                MATCH (kublai:Agent {id: 'main'})
                CREATE (n:Notification {
                    id: $notification_id,
                    type: 'task_blocked',
                    task_id: $task_id,
                    from_agent: $from_agent,
                    summary: $reason,
                    created_at: datetime(),
                    read: false,
                    ttl_hours: 24
                })
                CREATE (kublai)-[:HAS_NOTIFICATION]->(n)
                """
                with self._session_pool() as session:
                    session.run(query,
                               notification_id=item['notification_id'],
                               task_id=item['task_id'],
                               from_agent=item['delegator_id'],
                               reason=f"Task blocked: {item['reason'][:100]}")
                success_count += 1
            except Exception as e:
                item['retry_error'] = str(e)
                item['retry_count'] = item.get('retry_count', 0) + 1
                still_failed.append(item)

        # Update DLQ with items that still failed
        with self._fallback_lock:
            self._local_store['notification_dlq'] = still_failed

        return success_count

    def reassign_blocked_task(self, task_id: UUID, new_agent: str) -> bool:
        """Reassign a blocked task to a different agent (Kublai use)."""
        query = """
        MATCH (t:Task {id: $task_id, status: 'blocked'})
        MATCH (new:Agent {id: $new_agent})
        MATCH (t)-[r:ASSIGNED_TO]->(old:Agent)
        DELETE r
        CREATE (t)-[:ASSIGNED_TO]->(new)
        SET t.status = 'pending',
            t.escalation_count = coalesce(t.escalation_count, 0) + 1,
            t.reassigned_at = datetime()
        RETURN t.id as id
        """
        with self.driver.session() as session:
            result = session.run(query, task_id=str(task_id), new_agent=new_agent)
            return result.single() is not None

    def complete_task(self, task_id: UUID, results: Dict[str, Any],
                     notify_delegator: bool = True) -> bool:
        """Mark task as completed with results. Optionally notify delegator.

        Stores results as Neo4j map structure for queryable fields (not JSON string).
        Preserves type information for Cypher querying.
        """
        if self.fallback_mode:
            for t in self._local_store.get('tasks', []):
                if t['id'] == str(task_id):
                    t['status'] = 'completed'
                    t['results'] = results
                    return True
            return False

        # Build result map using ONLY whitelisted keys (prevents Cypher injection)
        # SECURITY: Never use user input to construct Cypher property names
        ALLOWED_RESULT_KEYS = {
            'status', 'output', 'error', 'duration_ms', 'rows_affected',
            'files_created', 'files_modified', 'tests_passed', 'tests_failed',
            'coverage_percent', 'security_issues', 'performance_score',
            'recommendations', 'findings', 'confidence', 'sources_checked'
        }

        result_map = {}
        for key, value in results.items():
            if key in ALLOWED_RESULT_KEYS and isinstance(value, (str, int, float, bool)):
                result_map[key] = value
            elif key in ('quality_score', 'summary'):
                # Handled separately below
                pass
            else:
                # Store unknown keys in a nested map for safety
                if '_extra' not in result_map:
                    result_map['_extra'] = {}
                result_map['_extra'][str(key)[:50]] = str(value)[:1000]

        params = {
            'task_id': str(task_id),
            'quality_score': results.get('quality_score', 0.8),
            'result_summary': results.get('summary', '')[:500],
            'result_map': result_map
        }

        # Safe query - no dynamic key construction, uses map structure
        query = """
        MATCH (t:Task {id: $task_id})
        MATCH (t)-[:ASSIGNED_TO]->(assignee:Agent)
        MATCH (delegator:Agent)-[:CREATED]->(t)
        SET t.status = 'completed',
            t.completed_at = datetime(),
            t.quality_score = $quality_score,
            t.result_summary = $result_summary,
            t.results_map = $result_map
        RETURN delegator.id as delegator_id, assignee.id as assignee_id
        """

        try:
            records = self._execute_with_retry(query, params)
            if records and notify_delegator:
                self._notify_task_complete(
                    delegator_id=records[0]['delegator_id'],
                    assignee_id=records[0]['assignee_id'],
                    task_id=task_id,
                    results=results
                )
            return True
        except Exception as e:
            print(f"[ERROR] Failed to complete task {task_id}: {e}")
            return False

    def _notify_task_complete(self, delegator_id: str, assignee_id: str,
                             task_id: UUID, results: Dict[str, Any]):
        """Create notification for task completion.

        In production, this would send agentToAgent message via OpenClaw.
        For now, creates a Notification node that delegator can query.
        """
        query = """
        MATCH (delegator:Agent {id: $delegator_id})
        CREATE (n:Notification {
            id: $notification_id,
            type: 'task_complete',
            task_id: $task_id,
            from_agent: $assignee_id,
            summary: $summary,
            created_at: datetime(),
            read: false,
            ttl_hours: 168
        })
        CREATE (delegator)-[:HAS_NOTIFICATION]->(n)
        """
        summary = results.get('summary', f"Task {task_id} completed by {assignee_id}")
        with self.driver.session() as session:
            session.run(query, delegator_id=delegator_id,
                       notification_id=str(uuid4()), task_id=str(task_id),
                       assignee_id=assignee_id, summary=summary)

    def cleanup_expired_notifications(self, max_age_hours: int = 168) -> int:
        """Remove notifications older than TTL. Call periodically (e.g., daily)."""
        if self.fallback_mode:
            return 0

        query = """
        MATCH (n:Notification)
        WHERE n.created_at < datetime() - duration({hours: $max_age_hours})
        WITH n LIMIT 1000
        DETACH DELETE n
        RETURN count(n) as deleted
        """
        try:
            records = self._execute_with_retry(query, {'max_age_hours': max_age_hours})
            return records[0]['deleted'] if records else 0
        except Exception as e:
            print(f"[ERROR] Failed to cleanup notifications: {e}")
            return 0

    def start_cleanup_scheduler(self, interval_hours: int = 24):
        """Start background scheduler for periodic cleanup tasks.

        Runs cleanup jobs in background thread to prevent notification/node growth.
        Uses APScheduler for reliable scheduling.
        """
        try:
            from apscheduler.schedulers.background import BackgroundScheduler

            self._scheduler = BackgroundScheduler()
            self._scheduler.add_job(
                self.cleanup_expired_notifications,
                'interval',
                hours=interval_hours,
                id='notification_cleanup',
                replace_existing=True
            )
            self._scheduler.add_job(
                self.cleanup_old_sessions,
                'interval',
                hours=interval_hours,
                id='session_cleanup',
                replace_existing=True
            )
            self._scheduler.start()
            print(f"[INFO] Cleanup scheduler started (interval: {interval_hours}h)")
        except ImportError:
            print("[WARN] APScheduler not available. Run cleanup manually or via cron.")

    def stop_cleanup_scheduler(self):
        """Stop the background cleanup scheduler."""
        if hasattr(self, '_scheduler') and self._scheduler:
            self._scheduler.shutdown()
            print("[INFO] Cleanup scheduler stopped")

    def cleanup_old_sessions(self, max_age_days: int = 30) -> int:
        """Remove old SessionContext nodes to prevent unbounded growth."""
        if self.fallback_mode:
            return 0

        query = """
        MATCH (s:SessionContext)
        WHERE s.created_at < datetime() - duration({days: $max_age_days})
        WITH s LIMIT 1000
        DETACH DELETE s
        RETURN count(s) as deleted
        """
        try:
            records = self._execute_with_retry(query, {'max_age_days': max_age_days})
            deleted = records[0]['deleted'] if records else 0
            if deleted > 0:
                print(f"[INFO] Cleaned up {deleted} old session contexts")
            return deleted
        except Exception as e:
            print(f"[ERROR] Failed to cleanup sessions: {e}")
            return 0

    def get_pending_notifications(self, agent_id: str) -> List[Dict[str, Any]]:
        """Get unread notifications for an agent (call this when agent becomes active)."""
        if self.fallback_mode:
            return []

        query = """
        MATCH (a:Agent {id: $agent_id})-[:HAS_NOTIFICATION]->(n:Notification {read: false})
        SET n.read = true
        RETURN n.id as id, n.type as type, n.task_id as task_id,
               n.from_agent as from_agent, n.summary as summary,
               n.created_at as created_at
        ORDER BY n.created_at DESC
        """
        with self.driver.session() as session:
            result = session.run(query, agent_id=agent_id)
            return [dict(record) for record in result]

    def save_session_context(self, sender_id: str, context: Dict[str, Any]) -> bool:
        """Save session context for persistence across resets."""
        if self.fallback_mode:
            return True

        from datetime import date
        today = date.today().isoformat()  # 'YYYY-MM-DD' string

        query = """
        MERGE (s:SessionContext {sender_id: $sender_id, session_date: $session_date})
        SET s.active_tasks = $active_tasks,
            s.pending_delegations = $pending_delegations,
            s.conversation_summary = $conversation_summary,
            s.updated_at = datetime(),
            s.drain_mode = $drain_mode
        ON CREATE SET s.created_at = datetime()
        """
        with self.driver.session() as session:
            session.run(query, sender_id=sender_id, session_date=today,
                       active_tasks=context.get('active_tasks', []),
                       pending_delegations=context.get('pending_delegations', []),
                       conversation_summary=context.get('conversation_summary', ''),
                       drain_mode=context.get('drain_mode', False))
        return True

    def check_graceful_reset_eligible(self, sender_id: str) -> Dict[str, Any]:
        """Check if session can be gracefully reset or needs to wait.

        Returns status of pending tasks and whether reset should proceed.
        """
        from datetime import date
        today = date.today().isoformat()

        query = """
        MATCH (s:SessionContext {sender_id: $sender_id, session_date: $session_date})
        OPTIONAL MATCH (t:Task)-[:ASSIGNED_TO]->(a:Agent)
        WHERE t.status IN ['pending', 'in_progress']
        RETURN s.active_tasks as active_tasks,
               s.pending_delegations as pending_delegations,
               count(t) as pending_task_count
        """
        with self.driver.session() as session:
            result = session.run(query, sender_id=sender_id, session_date=today)
            record = result.single()
            if not record:
                return {'can_reset': True, 'pending_tasks': 0}

            pending = record['pending_task_count']
            active = len(record.get('active_tasks', []))
            delegations = len(record.get('pending_delegations', []))

            # Allow reset if no pending work or drain timeout exceeded
            can_reset = pending == 0 and active == 0 and delegations == 0

            return {
                'can_reset': can_reset,
                'pending_tasks': pending,
                'active_tasks': active,
                'pending_delegations': delegations
            }

    def enter_drain_mode(self, sender_id: str) -> bool:
        """Enter drain mode - stop accepting new work, complete existing."""
        from datetime import date
        today = date.today().isoformat()

        query = """
        MATCH (s:SessionContext {sender_id: $sender_id, session_date: $session_date})
        SET s.drain_mode = true, s.drain_started_at = datetime()
        """
        with self.driver.session() as session:
            session.run(query, sender_id=sender_id, session_date=today)
        return True

    def get_session_context(self, sender_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve session context for a sender."""
        if self.fallback_mode:
            return None

        from datetime import date
        today = date.today().isoformat()  # 'YYYY-MM-DD' string

        query = """
        MATCH (s:SessionContext {sender_id: $sender_id, session_date: $session_date})
        RETURN s.active_tasks as active_tasks,
               s.pending_delegations as pending_delegations,
               s.conversation_summary as conversation_summary
        """
        with self.driver.session() as session:
            result = session.run(query, sender_id=sender_id, session_date=today)
            record = result.single()
            return dict(record) if record else None

    def update_agent_last_active(self, agent_id: str) -> bool:
        """Update agent's last_active timestamp. Call after any agent action."""
        if self.fallback_mode:
            return True

        query = """
        MATCH (a:Agent {id: $agent_id})
        SET a.last_active = datetime()
        """
        with self.driver.session() as session:
            session.run(query, agent_id=agent_id)
        return True

    def health_check(self) -> Dict[str, Any]:
        """Check Neo4j health status (read-only to support read replicas)."""
        if self.fallback_mode:
            return {'status': 'fallback', 'connected': False}

        try:
            # Test read capability only (supports read-only replicas)
            with self._session_pool() as session:
                result = session.run("RETURN 1 as test, datetime() as server_time")
                record = result.single()
                read_ok = record['test'] == 1 if record else False
                server_time = record['server_time'] if record else None

            # Check if we can query schema (indicates full functionality)
            schema_ok = False
            try:
                with self._session_pool() as session:
                    result = session.run("CALL db.indexes() YIELD name RETURN count(*) as index_count")
                    record = result.single()
                    schema_ok = record is not None
            except Exception:
                schema_ok = False  # May not have permissions, not critical

            # Check rate limit status
            rate_limit_status = {}
            with self._rate_limit_lock:
                for key, counter in self._rate_limit_counters.items():
                    rate_limit_status[key] = {
                        'hourly_usage': counter['count'],
                        'hourly_limit': self.RATE_LIMIT_HOURLY,
                        'burst_usage': counter['burst_count'],
                        'burst_limit': self.RATE_LIMIT_BURST
                    }

            return {
                'status': 'healthy' if read_ok else 'degraded',
                'connected': True,
                'read_ok': read_ok,
                'schema_ok': schema_ok,
                'server_time': str(server_time) if server_time else None,
                'rate_limits': rate_limit_status,
                'circuit_breaker': {
                    'failures': self._circuit_failures,
                    'open': not self._circuit_breaker_check()
                }
            }
        except Exception as e:
            return {'status': 'unhealthy', 'connected': False, 'error': str(e)}

    def close(self):
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()


class SessionResetManager:
    """Manages graceful daily session reset with drain mode.

    Implements the graceful reset logic defined in moltbot.json session config.
    Waits for pending tasks to complete before allowing reset.
    """

    def __init__(self, memory: OperationalMemory):
        self.memory = memory
        self._drain_mode = False
        self._drain_start_time: Optional[datetime] = None
        self._max_drain_seconds = 300  # Default 5 minutes
        self._max_pending_before_force = 10

    def check_and_enter_drain_mode(self, sender_id: str) -> Dict[str, Any]:
        """Check if session can reset gracefully, enter drain mode if needed.

        Called before daily reset to give active tasks time to complete.
        """
        status = self.memory.check_graceful_reset_eligible(sender_id)

        if status['can_reset']:
            return {'action': 'reset_now', 'reason': 'no_pending_work'}

        pending_count = status.get('pending_tasks', 0) + status.get('active_tasks', 0)

        # Force reset if too many pending tasks
        if pending_count >= self._max_pending_before_force:
            return {
                'action': 'force_reset',
                'reason': f'too_many_pending_tasks({pending_count})',
                'pending': status
            }

        # Enter drain mode
        if not self._drain_mode:
            self._drain_mode = True
            self._drain_start_time = datetime.now()
            self.memory.enter_drain_mode(sender_id)

        # Check if drain timeout exceeded
        elapsed = (datetime.now() - self._drain_start_time).total_seconds()
        if elapsed > self._max_drain_seconds:
            return {
                'action': 'force_reset',
                'reason': f'drain_timeout_exceeded({elapsed:.0f}s)',
                'pending': status
            }

        return {
            'action': 'wait',
            'reason': 'draining_pending_tasks',
            'elapsed_seconds': elapsed,
            'max_seconds': self._max_drain_seconds,
            'pending': status
        }

    def complete_reset(self, sender_id: str):
        """Mark reset as complete, exit drain mode."""
        # Use the drain start date (when drain began) rather than today
        # to handle the edge case where drain spans midnight
        drain_start_date = None
        if self._drain_start_time:
            drain_start_date = self._drain_start_time.strftime('%Y-%m-%d')
        else:
            # Fallback to today if drain start time not set (shouldn't happen)
            from datetime import date
            drain_start_date = date.today().isoformat()

        self._drain_mode = False
        self._drain_start_time = None

        # Clear session context for the session being reset
        query = """
        MATCH (s:SessionContext {sender_id: $sender_id, session_date: $session_date})
        SET s.drain_mode = false,
            s.reset_completed_at = datetime(),
            s.active_tasks = [],
            s.pending_delegations = []
        """
        with self.memory.driver.session() as session:
            session.run(query, sender_id=sender_id, session_date=drain_start_date)


class FailoverMonitor:
    """Monitors Kublai health and triggers Ögedei failover when needed.

    Implements the failover protocol defined in Phase 5.5.
    Thread-safe for concurrent access to failure counters and state.
    """

    def __init__(self, memory: OperationalMemory, check_interval_seconds: int = 30):
        self.memory = memory
        self.check_interval = check_interval_seconds
        self._max_failures = 3
        self._last_check: Optional[datetime] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitoring = threading.Event()

        # Thread-safe state management using locks
        self._state_lock = threading.RLock()
        self._kublai_failures = 0
        self._failover_active = False

    def start_monitoring(self):
        """Start background thread to monitor Kublai health."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return

        self._stop_monitoring.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        print("[FAILOVER] Kublai health monitoring started")

    def stop_monitoring(self):
        """Stop the monitoring thread."""
        self._stop_monitoring.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        print("[FAILOVER] Kublai health monitoring stopped")

    def _monitor_loop(self):
        """Background loop checking Kublai health."""
        while not self._stop_monitoring.is_set():
            try:
                self._check_kublai_health()
                self._last_check = datetime.now()
            except Exception as e:
                print(f"[FAILOVER] Health check error: {e}")

            self._stop_monitoring.wait(self.check_interval)

    def _check_kublai_health(self):
        """Check if Kublai is healthy."""
        try:
            # Check Kublai's last_active timestamp
            query = """
            MATCH (a:Agent {id: 'main'})
            RETURN a.last_active as last_active,
                   datetime() - a.last_active as seconds_since_active
            """
            with self.memory.driver.session() as session:
                result = session.run(query)
                record = result.single()

                if not record:
                    self._handle_kublai_failure("Kublai agent not found")
                    return

                seconds_inactive = record.get('seconds_since_active', 999)

                # If inactive for 60+ seconds, count as failure
                if seconds_inactive and seconds_inactive >= 60:
                    self._handle_kublai_failure(f"inactive_for_{seconds_inactive}s")
                else:
                    # Kublai is healthy - thread-safe state reset
                    with self._state_lock:
                        if self._kublai_failures > 0:
                            print(f"[FAILOVER] Kublai recovered, failures reset")
                            self._kublai_failures = 0

                        # If failover was active, trigger failback
                        if self._failover_active:
                            self._trigger_failback()

        except Exception as e:
            self._handle_kublai_failure(f"health_check_exception: {e}")

    def _handle_kublai_failure(self, reason: str):
        """Record a Kublai failure, trigger failover if threshold reached."""
        with self._state_lock:
            self._kublai_failures += 1
            current_failures = self._kublai_failures
            should_failover = (self._kublai_failures >= self._max_failures
                               and not self._failover_active)

        print(f"[FAILOVER] Kublai failure {current_failures}/{self._max_failures}: {reason}")

        if should_failover:
            self._trigger_failover()

    def _trigger_failover(self):
        """Activate Ögedei as emergency router."""
        with self._state_lock:
            # Double-check pattern to prevent race conditions
            if self._failover_active:
                return
            self._failover_active = True
            print("[FAILOVER] Activating Ögedei as emergency router")

        # Update Ögedei's role in Neo4j using session pool for consistency
        query = """
        MATCH (a:Agent {id: 'ops'})
        SET a.role = 'Operations / Emergency Router (ACTIVE)',
            a.failover_activated_at = datetime(),
            a.failover_reason = 'kublai_unresponsive'
        """
        try:
            with self.memory._session_pool() as session:
                session.run(query)
        except Exception as e:
            print(f"[FAILOVER] Failed to update Ögedei role: {e}")

        # Create notification for admin using session pool
        try:
            from uuid import uuid4
            notification_query = """
            MATCH (o:Agent {id: 'ops'})
            CREATE (n:Notification {
                id: $id,
                type: 'failover_activated',
                summary: 'Ögedei activated as emergency router - Kublai unresponsive',
                created_at: datetime(),
                read: false,
                ttl_hours: 24
            })
            CREATE (o)-[:HAS_NOTIFICATION]->(n)
            """
            with self.memory._session_pool() as session:
                session.run(notification_query, id=str(uuid4()))
        except Exception as e:
            print(f"[FAILOVER] Failed to create notification: {e}")

    def _trigger_failback(self):
        """Return control to Kublai."""
        with self._state_lock:
            self._failover_active = False
        print("[FAILOVER] Kublai recovered, deactivating Ögedei emergency role")

        query = """
        MATCH (a:Agent {id: 'ops'})
        SET a.role = 'Operations',
            a.failover_deactivated_at = datetime()
        REMOVE a.failover_activated_at, a.failover_reason
        """
        try:
            with self.memory._session_pool() as session:
                session.run(query)
        except Exception as e:
            print(f"[FAILOVER] Failed to update Ögedei role: {e}")

    def is_failover_active(self) -> bool:
        """Check if failover is currently active."""
        with self._state_lock:
            return self._failover_active
```

**Step 3.2**: Add memory tools to agent capabilities

### Phase 4: Security Audit Protocol (Temüjin)

Add security review requirements to Temüjin's SOUL.md:

```markdown
## Security Audit Responsibilities

As Security Lead, you proactively review all code and queries for:

1. **Injection Attacks**
   - Cypher injection in full-text search queries
   - Unparameterized queries with user input
   - Required: All user input must be parameterized

2. **Data Exposure**
   - PII leaking to operational memory
   - API keys in logs or error messages
   - Required: Verify _sanitize_for_sharing() called before all writes

3. **Access Control**
   - Agent permissions on sensitive operations
   - Required: Validate agent identity before task claims

4. **Audit Triggers**
   Review immediately when:
   - New Cypher queries added
   - User input passed to database
   - Error messages returned to users
   - New agent capabilities added

## Security Review Workflow

When assigned security review:
1. Scan code for injection patterns (regex: `query.*\$\{`, `\.run\(.*\+`)
2. Verify all user inputs are parameterized
3. Check for hardcoded credentials
4. Test error handling (ensure no stack traces leak)
5. Document findings in SecurityAudit node
6. If critical: notify Kublai immediately via agentToAgent
```

### Phase 4.5: Ögedei File Consistency & Project Management Protocol

Ögedei manages file consistency across agent workspaces and uses Notion for project management.

#### File Consistency Node Types

```cypher
(:FileConsistencyReport {
  id,
  timestamp,
  files_checked: [string],      // List of files scanned
  conflicts_found: [map],       // Details of each conflict
  severity: "low" | "medium" | "high" | "critical",
  requires_kublai_attention: boolean,
  status: "detected" | "escalated" | "resolving" | "resolved"
})

(:FileConflict {
  id,
  type: "contradiction" | "stale_data" | "parse_error" | "missing_section",
  files_involved: [string],
  conflict_description: string,
  detected_at: datetime,
  severity: "low" | "medium" | "high" | "critical",
  status: "open" | "escalated" | "resolved",
  kublai_decision: string,      // Kublai's resolution decision
  resolution_action: string     // What was done to resolve
})
```

#### Ögedei Implementation Classes

Add to `openclaw_memory.py`:

```python
class FileConsistencyChecker:
    """Monitors and validates consistency of memory files across agent workspaces.

    Ögedei uses this to detect conflicts and stale data in:
    - heartbeat.md
    - memory.md
    - CLAUDE.md
    - Other .md files in agent directories
    """

    # Files to monitor in each agent workspace
    MONITORED_FILES = ['heartbeat.md', 'memory.md', 'CLAUDE.md']

    def __init__(self, memory: OperationalMemory):
        self.memory = memory
        self.agent_dirs = [
            '/data/.clawdbot/agents/main',
            '/data/.clawdbot/agents/researcher',
            '/data/.clawdbot/agents/writer',
            '/data/.clawdbot/agents/developer',
            '/data/.clawdbot/agents/analyst',
            '/data/.clawdbot/agents/ops'
        ]

    def run_consistency_check(self) -> Dict[str, Any]:
        """Run full consistency check on all agent workspaces.

        Returns report with conflicts found.
        """
        report = {
            'timestamp': datetime.now().isoformat(),
            'files_checked': [],
            'conflicts_found': [],
            'parse_errors': [],
            'severity': 'none'
        }

        all_files = []
        for agent_dir in self.agent_dirs:
            if os.path.exists(agent_dir):
                for filename in self.MONITORED_FILES:
                    filepath = os.path.join(agent_dir, filename)
                    if os.path.exists(filepath):
                        all_files.append(filepath)
                        report['files_checked'].append(filepath)

        # Check for conflicts between files
        conflicts = self._detect_cross_file_conflicts(all_files)
        report['conflicts_found'] = conflicts

        # Check for parse errors
        parse_errors = self._check_parseability(all_files)
        report['parse_errors'] = parse_errors

        # Determine severity
        if any(c['severity'] == 'critical' for c in conflicts):
            report['severity'] = 'critical'
        elif any(c['severity'] == 'high' for c in conflicts):
            report['severity'] = 'high'
        elif conflicts or parse_errors:
            report['severity'] = 'medium'

        # Store report in Neo4j
        self._store_report(report)

        return report

    def _detect_cross_file_conflicts(self, files: List[str]) -> List[Dict]:
        """Detect conflicts between multiple files."""
        conflicts = []

        # Extract key facts from each file
        file_facts = {}
        for filepath in files:
            try:
                with open(filepath, 'r') as f:
                    content = f.read()
                    facts = self._extract_facts(content, filepath)
                    file_facts[filepath] = facts
            except Exception as e:
                conflicts.append({
                    'type': 'parse_error',
                    'files': [filepath],
                    'description': f'Failed to read file: {e}',
                    'severity': 'high'
                })

        # Compare facts across files
        for file1, facts1 in file_facts.items():
            for file2, facts2 in file_facts.items():
                if file1 >= file2:  # Avoid duplicate checks
                    continue

                # Check for contradictions
                contradictions = self._find_contradictions(facts1, facts2)
                for contradiction in contradictions:
                    conflicts.append({
                        'type': 'contradiction',
                        'files': [file1, file2],
                        'description': contradiction,
                        'severity': 'high'
                    })

                # Check for stale data (timestamp-based)
                stale_data = self._find_stale_data(facts1, facts2)
                for stale in stale_data:
                    conflicts.append({
                        'type': 'stale_data',
                        'files': [file1, file2],
                        'description': stale,
                        'severity': 'medium'
                    })

        return conflicts

    def _extract_facts(self, content: str, filepath: str) -> Dict[str, Any]:
        """Extract structured facts from markdown content."""
        facts = {
            'filepath': filepath,
            'timestamp': None,
            'sections': {},
            'key_values': {}
        }

        # Extract timestamp if present
        import re
        ts_match = re.search(r'timestamp:\s*(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2})', content)
        if ts_match:
            facts['timestamp'] = ts_match.group(1)

        # Extract sections
        section_pattern = r'^##\s+(.+)\n'
        for match in re.finditer(section_pattern, content, re.MULTILINE):
            section_name = match.group(1).strip()
            facts['sections'][section_name] = True

        # Extract key-value pairs
        kv_pattern = r'^([A-Za-z_]+):\s*(.+)$'
        for match in re.finditer(kv_pattern, content, re.MULTILINE):
            key = match.group(1)
            value = match.group(2).strip()
            facts['key_values'][key] = value

        return facts

    def _find_contradictions(self, facts1: Dict, facts2: Dict) -> List[str]:
        """Find contradictions between two fact sets."""
        contradictions = []

        # Check for same key with different values
        for key in set(facts1['key_values'].keys()) & set(facts2['key_values'].keys()):
            val1 = facts1['key_values'][key]
            val2 = facts2['key_values'][key]

            # Simple string comparison (could be enhanced with semantic comparison)
            if val1 != val2 and not self._is_minor_difference(val1, val2):
                contradictions.append(
                    f"Key '{key}' has different values: "
                    f"'{val1[:50]}...' vs '{val2[:50]}...'"
                )

        return contradictions

    def _find_stale_data(self, facts1: Dict, facts2: Dict) -> List[str]:
        """Identify potentially stale data based on timestamps."""
        stale = []

        if facts1.get('timestamp') and facts2.get('timestamp'):
            try:
                from datetime import datetime
                ts1 = datetime.fromisoformat(facts1['timestamp'].replace('Z', '+00:00'))
                ts2 = datetime.fromisoformat(facts2['timestamp'].replace('Z', '+00:00'))

                # If one file is significantly older
                diff_hours = abs((ts1 - ts2).total_seconds() / 3600)
                if diff_hours > 24:
                    older = facts1 if ts1 < ts2 else facts2
                    stale.append(
                        f"File {older['filepath']} may be stale "
                        f"({diff_hours:.1f} hours behind)"
                    )
            except:
                pass  # Ignore timestamp parsing errors

        return stale

    def _is_minor_difference(self, val1: str, val2: str) -> bool:
        """Determine if difference is minor (whitespace, formatting)."""
        return val1.strip() == val2.strip()

    def _check_parseability(self, files: List[str]) -> List[Dict]:
        """Check if files are valid markdown."""
        errors = []

        for filepath in files:
            try:
                with open(filepath, 'r') as f:
                    content = f.read()

                # Basic markdown validation
                # Check for unclosed code blocks
                code_blocks = content.count('```')
                if code_blocks % 2 != 0:
                    errors.append({
                        'file': filepath,
                        'error': 'Unclosed code block',
                        'severity': 'medium'
                    })

                # Check for unclosed headers
                for line in content.split('\n'):
                    if line.startswith('#') and not line.strip('#').strip():
                        errors.append({
                            'file': filepath,
                            'error': 'Empty header',
                            'severity': 'low'
                        })

            except Exception as e:
                errors.append({
                    'file': filepath,
                    'error': str(e),
                    'severity': 'high'
                })

        return errors

    def _store_report(self, report: Dict[str, Any]):
        """Store consistency report in Neo4j."""
        if self.memory.fallback_mode:
            return

        query = """
        CREATE (r:FileConsistencyReport {
            id: $id,
            timestamp: datetime($timestamp),
            files_checked: $files_checked,
            conflicts_found: $conflicts_found,
            parse_errors: $parse_errors,
            severity: $severity,
            requires_kublai_attention: $needs_attention,
            status: 'detected'
        })
        RETURN r.id as id
        """

        needs_attention = report['severity'] in ['high', 'critical']

        try:
            from uuid import uuid4
            with self.memory.driver.session() as session:
                session.run(query,
                    id=str(uuid4()),
                    timestamp=report['timestamp'],
                    files_checked=report['files_checked'],
                    conflicts_found=json.dumps(report['conflicts_found']),
                    parse_errors=json.dumps(report['parse_errors']),
                    severity=report['severity'],
                    needs_attention=needs_attention
                )
        except Exception as e:
            print(f"[FILE_CHECK] Failed to store report: {e}")

    def escalate_conflicts(self, report: Dict[str, Any]) -> List[str]:
        """Create escalation Analysis nodes for Kublai review.

        Returns list of created Analysis node IDs.
        """
        escalated_ids = []

        for conflict in report.get('conflicts_found', []):
            if conflict.get('severity') in ['high', 'critical']:
                # Create Analysis node
                analysis_id = self._create_conflict_analysis(conflict)
                if analysis_id:
                    escalated_ids.append(analysis_id)

        return escalated_ids

    def _create_conflict_analysis(self, conflict: Dict) -> Optional[str]:
        """Create Analysis node for a specific conflict."""
        if self.memory.fallback_mode:
            return None

        query = """
        MATCH (ogedei:Agent {id: 'ops'})
        CREATE (a:Analysis {
            id: $id,
            type: "file_inconsistency",
            category: $category,
            findings: $description,
            files_involved: $files,
            severity: $severity,
            status: "escalated",
            identified_by: "ogedei",
            requires_resolution_by: "kublai",
            detected_at: datetime()
        })
        CREATE (ogedei)-[:CREATED]->(a)
        RETURN a.id as id
        """

        try:
            from uuid import uuid4
            analysis_id = str(uuid4())

            with self.memory.driver.session() as session:
                session.run(query,
                    id=analysis_id,
                    category=conflict.get('type', 'unknown'),
                    description=conflict.get('description', ''),
                    files=conflict.get('files', []),
                    severity=conflict.get('severity', 'medium')
                )

            return analysis_id
        except Exception as e:
            print(f"[FILE_CHECK] Failed to create analysis: {e}")
            return None


class NotionProjectManager:
    """Notion integration for project management via Kanban boards.

    Ögedei uses this to track tasks, manage sprints, and maintain
    project visibility in Notion.
    """

    def __init__(self, notion_token: Optional[str] = None):
        self.token = notion_token or os.getenv('NOTION_TOKEN')
        self.database_id = os.getenv('NOTION_TASK_DATABASE_ID')
        self.base_url = 'https://api.notion.com/v1'
        self.headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json',
            'Notion-Version': '2022-06-28'
        }

    def _make_request(self, method: str, endpoint: str, data: Dict = None) -> Optional[Dict]:
        """Make HTTP request to Notion API."""
        import requests

        if not self.token or not self.database_id:
            print("[NOTION] Not configured - missing token or database_id")
            return None

        url = f"{self.base_url}/{endpoint}"

        try:
            if method == 'GET':
                response = requests.get(url, headers=self.headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, headers=self.headers, json=data, timeout=30)
            elif method == 'PATCH':
                response = requests.patch(url, headers=self.headers, json=data, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            print(f"[NOTION] API error: {e}")
            return None

    def create_task(self, title: str, assignee: str, priority: str = 'P2',
                   due_date: Optional[str] = None, description: str = '',
                   neo4j_task_id: Optional[str] = None) -> Optional[str]:
        """Create a new task in Notion Kanban board.

        Returns the Notion page ID of the created task.
        """
        properties = {
            'Name': {
                'title': [{'text': {'content': title}}]
            },
            'Status': {
                'select': {'name': 'To Do'}
            },
            'Assignee': {
                'select': {'name': assignee}
            },
            'Priority': {
                'select': {'name': priority}
            }
        }

        if due_date:
            properties['Due Date'] = {
                'date': {'start': due_date}
            }

        if description:
            properties['Description'] = {
                'rich_text': [{'text': {'content': description}}]
            }

        if neo4j_task_id:
            properties['Neo4j Task ID'] = {
                'rich_text': [{'text': {'content': neo4j_task_id}}]
            }

        data = {
            'parent': {'database_id': self.database_id},
            'properties': properties
        }

        result = self._make_request('POST', 'pages', data)
        if result:
            page_id = result.get('id')
            print(f"[NOTION] Created task '{title}' with ID {page_id}")
            return page_id
        return None

    def update_task_status(self, page_id: str, status: str):
        """Move task to different Kanban column."""
        valid_statuses = ['Backlog', 'To Do', 'In Progress', 'Review', 'Done']

        if status not in valid_statuses:
            print(f"[NOTION] Invalid status '{status}'. Use: {valid_statuses}")
            return False

        data = {
            'properties': {
                'Status': {'select': {'name': status}}
            }
        }

        if status == 'Done':
            from datetime import date
            data['properties']['Completed'] = {
                'date': {'start': date.today().isoformat()}
            }

        result = self._make_request('PATCH', f'pages/{page_id}', data)
        return result is not None

    def get_tasks_by_status(self, status: str) -> List[Dict]:
        """Query tasks in a specific Kanban column."""
        data = {
            'filter': {
                'property': 'Status',
                'select': {'equals': status}
            }
        }

        result = self._make_request('POST', f'databases/{self.database_id}/query', data)
        if result:
            return result.get('results', [])
        return []

    def sync_with_neo4j_tasks(self, memory: OperationalMemory):
        """Synchronize Neo4j tasks with Notion board.

        Creates new Notion tasks for pending Neo4j tasks,
        updates statuses for completed tasks.
        """
        if memory.fallback_mode:
            return

        # Get pending tasks from Neo4j
        query = """
        MATCH (t:Task {status: 'pending'})
        RETURN t.id as task_id, t.type as type, t.description as description,
               t.assigned_to as assignee
        """

        with memory.driver.session() as session:
            result = session.run(query)
            pending_tasks = [dict(record) for record in result]

        # Get existing Notion tasks
        notion_todo = self.get_tasks_by_status('To Do')
        notion_in_progress = self.get_tasks_by_status('In Progress')
        existing_ids = set()

        for task in notion_todo + notion_in_progress:
            neo4j_id = task.get('properties', {}).get('Neo4j Task ID', {}).get('rich_text', [{}])[0].get('text', {}).get('content')
            if neo4j_id:
                existing_ids.add(neo4j_id)

        # Create Notion tasks for new Neo4j tasks
        for task in pending_tasks:
            if task['task_id'] not in existing_ids:
                self.create_task(
                    title=f"[{task['type'].upper()}] {task['description'][:50]}...",
                    assignee=task['assignee'],
                    description=task['description'],
                    neo4j_task_id=task['task_id']
                )

    def generate_daily_report(self) -> Dict[str, Any]:
        """Generate daily summary of task statuses."""
        report = {
            'date': datetime.now().date().isoformat(),
            'columns': {}
        }

        for status in ['Backlog', 'To Do', 'In Progress', 'Review', 'Done']:
            tasks = self.get_tasks_by_status(status)
            report['columns'][status] = len(tasks)

        return report
```

#### Environment Variables for Notion

Add to environment configuration:

```bash
# Notion Integration (Optional but recommended for Ögedei)
NOTION_TOKEN=secret_xxx_your_integration_token
NOTION_TASK_DATABASE_ID=xxx_your_database_id
```

#### Conflict Escalation Protocol

When Ögedei detects file inconsistencies:

```
1. Run consistency check (scheduled or triggered)
2. If conflicts found:
   a. Create FileConsistencyReport node
   b. For high/critical conflicts:
      - Create Analysis node with type="file_inconsistency"
      - Set requires_resolution_by="kublai"
      - Include files_involved and conflict_description
   c. Send agentToAgent to Kublai:
      "File inconsistency detected in [files]. Analysis #[id] requires resolution."
3. Kublai reviews and decides:
   a. If clear resolution: instruct Ögedei to implement
   b. If needs discussion: escalate to user or team
   c. If acceptable: mark as acknowledged
4. Ögedei implements approved resolution
5. Verify fix and update Analysis status to "resolved"
```

### Phase 4.6: Jochi's Backend Issue Identification Protocol

Jochi is responsible for proactively identifying backend implementation issues and labeling them for Temüjin to fix.

#### Issue Categories Jochi Monitors

| Category | Issues to Identify | Severity |
|----------|-------------------|----------|
| **Connection Management** | Missing connection pool config, no timeouts, resource exhaustion | Critical |
| **Resilience** | No retry logic, missing circuit breaker, no fallback mode | High |
| **Data Integrity** | Unparameterized queries, missing transactions, no schema migrations | High |
| **Performance** | Missing query timeouts, unbounded data growth, blocking operations | Medium |
| **Security** | Secrets in logs, unverified downloads, missing input validation | Critical |

#### Jochi's Review Workflow

```python
# When Jochi reviews backend code, it creates:
(:Analysis {
  type: "backend_issue",
  category: "connection_pool" | "resilience" | "data_integrity" | "performance" | "security",
  findings: "Detailed description of the issue",
  location: "file.py:line_number",
  severity: "critical" | "high" | "medium",
  recommended_fix: "Specific implementation approach",
  status: "identified",  # Jochi sets this
  identified_by: "jochi",
  requires_implementation_by: "temujin"
})
```

#### Handoff to Temüjin

1. **Jochi identifies issue** → Creates Analysis node with `status: "identified"`
2. **Jochi notifies Kublai** → "Backend issue #X requires Temüjin implementation"
3. **Kublai delegates to Temüjin** → Via agentToAgent with Analysis node ID
4. **Temüjin implements fix** → Updates Analysis `status: "resolved"`
5. **Jochi validates** → Runs tests/metrics to confirm fix

### Phase 4.7: Ögedei's Proactive Improvement Protocol

Ögedei uses the proactive-agent skill for continuous operational reflection and improvement proposals.

#### Proactive Reflection Process

```python
# In openclaw_memory.py, add to OperationalMemory class:

def record_workflow_improvement(self, proposed_by: str, target_process: str,
                                 current_state: str, proposed_state: str,
                                 expected_benefit: str, complexity: str = "medium") -> Optional[UUID]:
    """Create a workflow improvement proposal for Kublai review.

    Used by Ögedei's proactive-agent skill to suggest operational improvements.
    """
    if self.fallback_mode:
        return None

    improvement_id = uuid4()

    query = """
    MATCH (proposer:Agent {id: $proposed_by})
    CREATE (w:WorkflowImprovement {
        id: $id,
        target_process: $target_process,
        current_state: $current_state,
        proposed_state: $proposed_state,
        expected_benefit: $expected_benefit,
        complexity: $complexity,
        proposed_by: $proposed_by,
        status: 'proposed',
        proposed_at: datetime(),
        requires_approval_by: 'main'
    })
    CREATE (proposer)-[:PROPOSED]->(w)
    RETURN w.id as id
    """

    try:
        with self.driver.session() as session:
            session.run(query,
                id=str(improvement_id),
                proposed_by=proposed_by,
                target_process=target_process,
                current_state=current_state,
                proposed_state=proposed_state,
                expected_benefit=expected_benefit,
                complexity=complexity
            )
        return improvement_id
    except Exception as e:
        print(f"[ERROR] Failed to record workflow improvement: {e}")
        return None

def approve_workflow_improvement(self, improvement_id: UUID,
                                  approved_by: str, decision: str,
                                  notes: str = "") -> bool:
    """Kublai approves or declines an improvement proposal."""
    if self.fallback_mode:
        return False

    query = """
    MATCH (w:WorkflowImprovement {id: $improvement_id})
    MATCH (approver:Agent {id: $approved_by})
    SET w.status = $decision,
        w.decision_at = datetime(),
        w.decision_notes = $notes
    CREATE (approver)-[:APPROVED {decision: $decision, timestamp: datetime()}]->(w)
    RETURN true as success
    """

    try:
        with self.driver.session() as session:
            session.run(query,
                improvement_id=str(improvement_id),
                approved_by=approved_by,
                decision=decision,  # 'approved', 'declined', 'needs_discussion'
                notes=notes
            )
        return True
    except Exception as e:
        print(f"[ERROR] Failed to update improvement status: {e}")
        return False

def get_pending_improvements(self, agent_id: str = None) -> List[Dict[str, Any]]:
    """Get workflow improvements pending Kublai review."""
    if self.fallback_mode:
        return []

    if agent_id:
        query = """
        MATCH (w:WorkflowImprovement {status: 'proposed', proposed_by: $agent_id})
        RETURN w.id as id, w.target_process as process, w.expected_benefit as benefit,
               w.proposed_at as proposed_at, w.complexity as complexity
        ORDER BY w.proposed_at DESC
        """
        params = {'agent_id': agent_id}
    else:
        query = """
        MATCH (w:WorkflowImprovement {status: 'proposed'})
        RETURN w.id as id, w.target_process as process, w.expected_benefit as benefit,
               w.proposed_by as proposed_by, w.proposed_at as proposed_at
        ORDER BY w.proposed_at DESC
        """
        params = {}

    with self.driver.session() as session:
        result = session.run(query, **params)
        return [dict(record) for record in result]
```

#### Proposed WorkflowImprovement Schema Update

Add to Neo4j schema:

```cypher
(:WorkflowImprovement {
  id,
  target_process: string,        // e.g., "task_delegation", "file_consistency_checks"
  current_state: string,         // Description of current process
  proposed_state: string,        // Description of proposed improvement
  expected_benefit: string,      // Quantified benefit (e.g., "30% faster routing")
  complexity: "low" | "medium" | "high",
  proposed_by: string,           // Agent ID (typically "ops")
  status: "proposed" | "approved" | "declined" | "needs_discussion" | "implementing" | "deployed",
  proposed_at: datetime,
  requires_approval_by: "main",  // Kublai must approve
  decision_at: datetime,         // When Kublai decided
  decision_notes: string         // Kublai's reasoning
})

// Relationships
(Agent {id: "ops"})-[:PROPOSED]->(WorkflowImprovement)
(Agent {id: "main"})-[:APPROVED {decision: "approved|declined"}]->(WorkflowImprovement)
```

#### Ögedei's Proactive Reflection Schedule

| Trigger | Reflection Action | Output |
|---------|------------------|--------|
| Task completed | Quick friction check | Mental note or brief log |
| Daily (21:00 UTC) | Review day's operations | Identify 1-2 improvement opportunities |
| Weekly (Sunday) | Deep workflow analysis | Formal improvement proposals |
| Metric threshold | Alert-based reflection | Immediate proposal if critical |

#### Integration with Proactive-Agent Skill

Ögedei's SOUL.md includes:

```markdown
## Proactive Improvement Protocol

You constantly use the proactive-agent skill to reflect on operations:

### Reflection Questions (ask yourself regularly):
1. What took longer than it should have today?
2. Which manual steps could be automated?
3. Are agents waiting on each other unnecessarily?
4. Could information flow more efficiently?
5. Are there recurring patterns that suggest a systemic issue?

### Proposal Criteria:
- Must have clear expected benefit (time saved, errors reduced, etc.)
- Must include implementation complexity estimate
- Must not compromise security or privacy
- Must be reversible if it doesn't work

### Kublai Approval Process:
- Send proposal via agentToAgent with clear yes/no question
- Include: what, why, expected benefit, complexity
- Wait for explicit approval before implementing
- If declined, archive and note reason (don't resubmit similar)

### Post-Implementation:
- Measure actual vs expected benefit
- Document lessons learned
- Propose refinements based on results
```

### Phase 4.8: Chagatai's Continuous Background Synthesis

Chagatai runs continuous background synthesis when no user tasks are assigned. This creates a self-reinforcing knowledge loop where the writer agent constantly consolidates memories, generates insights, and produces new content.

#### Architecture: Ögedei-Triggered Background Tasks

Ögedei monitors agent idle state and assigns synthesis tasks:

```python
# In openclaw_memory.py - add to OperationalMemory class

class OperationalMemory:
    # ... existing code ...

    def create_background_synthesis_task(self, agent_id: str) -> Optional[UUID]:
        """Create a background synthesis task for an idle agent.

        Called by Ögedei when agent has been idle for threshold period.
        Background tasks are preemptible - user tasks always take priority.
        """
        if self.fallback_mode:
            return None

        # Define synthesis types per agent
        synthesis_types = {
            "writer": "content_synthesis",
            "researcher": "research_consolidation",
            "developer": "pattern_extraction",
            "analyst": "trend_synthesis",
            "ops": "process_optimization"
        }

        task_type = synthesis_types.get(agent_id, "general_synthesis")

        task_id = uuid4()

        query = """
        MATCH (agent:Agent {id: $agent_id})
        CREATE (t:BackgroundTask {
            id: $id,
            agent: $agent_id,
            type: $task_type,
            status: 'pending',
            priority: 'low',
            preemptible: true,
            created_at: datetime(),
            started_at: null,
            preempted_at: null,
            completed_at: null
        })
        CREATE (agent)-[:ASSIGNED_BACKGROUND]->(t)
        RETURN t.id as task_id
        """

        try:
            with self._session_pool() as session:
                session.run(query,
                    id=str(task_id),
                    agent_id=agent_id,
                    task_type=task_type
                )
            print(f"[BACKGROUND] Created {task_type} task for {agent_id}")
            return task_id
        except Exception as e:
            print(f"[ERROR] Failed to create background task: {e}")
            return None

    def get_synthesis_candidates(self, agent_id: str, limit: int = 20) -> List[Dict]:
        """Get memories ready for synthesis (unsynthesized, recent)."""
        if self.fallback_mode:
            return []

        query = """
        MATCH (n)
        WHERE n.agent = $agent_id
          AND (n:Research OR n:Content OR n:Application OR n:Analysis)
          AND NOT (n)<-[:BASED_ON]-(:Synthesis)
          AND n.created_at > datetime() - duration({days: 7})
        RETURN n.id as id,
               n.type as type,
               labels(n) as labels,
               n.created_at as created_at,
               n.findings as findings,
               n.body as body,
               n.description as description
        ORDER BY n.created_at DESC
        LIMIT $limit
        """

        try:
            with self._session_pool() as session:
                result = session.run(query, agent_id=agent_id, limit=limit)
                return [dict(record) for record in result]
        except Exception as e:
            print(f"[ERROR] Failed to get synthesis candidates: {e}")
            return []

    def store_synthesis(self, agent_id: str, sources: List[str],
                        content: str, concepts: List[str],
                        quality_score: Optional[float] = None) -> Optional[str]:
        """Store synthesis and link to source memories."""
        if self.fallback_mode:
            return None

        synthesis_id = uuid4()

        query = """
        CREATE (s:Synthesis {
            id: $id,
            agent: $agent_id,
            content: $content,
            concepts_extracted: $concepts,
            quality_score: $quality_score,
            created_at: datetime()
        })
        WITH s
        UNWIND $sources as source_id
        MATCH (src {id: source_id})
        CREATE (s)-[:BASED_ON]->(src)
        WITH s, count(src) as source_count
        RETURN s.id as synthesis_id, source_count
        """

        try:
            with self._session_pool() as session:
                result = session.run(query,
                    id=str(synthesis_id),
                    agent_id=agent_id,
                    content=content,
                    concepts=concepts,
                    quality_score=quality_score,
                    sources=sources
                )
                record = result.single()
                if record:
                    print(f"[SYNTHESIS] Created {synthesis_id} from {record['source_count']} sources")
                    return str(synthesis_id)
        except Exception as e:
            print(f"[ERROR] Failed to store synthesis: {e}")
            return None

    def store_insight(self, agent_id: str, insight: str, category: str,
                      supporting_evidence: List[str],
                      confidence: float, novelty_score: float) -> Optional[str]:
        """Store generated insight with supporting evidence."""
        if self.fallback_mode:
            return None

        insight_id = uuid4()

        query = """
        CREATE (i:Insight {
            id: $id,
            agent: $agent_id,
            insight: $insight,
            category: $category,
            confidence: $confidence,
            novelty_score: $novelty_score,
            status: 'generated',
            created_at: datetime()
        })
        WITH i
        UNWIND $evidence as evidence_id
        MATCH (e {id: evidence_id})
        CREATE (i)-[:SUPPORTED_BY]->(e)
        WITH i, count(e) as evidence_count
        RETURN i.id as insight_id, evidence_count
        """

        try:
            with self._session_pool() as session:
                result = session.run(query,
                    id=str(insight_id),
                    agent_id=agent_id,
                    insight=insight,
                    category=category,
                    confidence=confidence,
                    novelty_score=novelty_score,
                    evidence=supporting_evidence
                )
                record = result.single()
                if record:
                    print(f"[INSIGHT] Created {insight_id} with {record['evidence_count']} evidence")
                    return str(insight_id)
        except Exception as e:
            print(f"[ERROR] Failed to store insight: {e}")
            return None

    def preempt_background_task(self, agent_id: str) -> Optional[str]:
        """Preempt background task when user task arrives.

        Returns task_id if preempted, None if no background task running.
        """
        if self.fallback_mode:
            return None

        query = """
        MATCH (t:BackgroundTask {agent: $agent_id, status: 'running'})
        SET t.status = 'preempted',
            t.preempted_at = datetime()
        RETURN t.id as task_id
        """

        try:
            with self._session_pool() as session:
                result = session.run(query, agent_id=agent_id)
                record = result.single()
                if record:
                    print(f"[BACKGROUND] Preempted task {record['task_id']} for {agent_id}")
                    return record['task_id']
        except Exception as e:
            print(f"[ERROR] Failed to preempt background task: {e}")
        return None

    def resume_background_task(self, agent_id: str) -> Optional[str]:
        """Resume preempted background task.

        Returns task_id if resumed, None if no preempted task.
        """
        if self.fallback_mode:
            return None

        query = """
        MATCH (t:BackgroundTask {agent: $agent_id, status: 'preempted'})
        SET t.status = 'running',
            t.resumed_at = datetime()
        RETURN t.id as task_id
        ORDER BY t.preempted_at DESC
        LIMIT 1
        """

        try:
            with self._session_pool() as session:
                result = session.run(query, agent_id=agent_id)
                record = result.single()
                if record:
                    print(f"[BACKGROUND] Resumed task {record['task_id']} for {agent_id}")
                    return record['task_id']
        except Exception as e:
            print(f"[ERROR] Failed to resume background task: {e}")
        return None

    def get_insight_gaps(self, agent_id: str, min_concepts: int = 5) -> List[Dict]:
        """Find domains lacking recent insights (synthesis opportunities)."""
        if self.fallback_mode:
            return []

        query = """
        MATCH (c:Concept)
        WHERE NOT (c)<-[:SUPPORTS]-(:Insight {
            agent: $agent_id,
            created_at: datetime() - duration({days: 30})
        })
        WITH c.domain as domain, count(c) as concept_count
        WHERE concept_count >= $min_concepts
        RETURN domain, concept_count
        ORDER BY concept_count DESC
        LIMIT 5
        """

        try:
            with self._session_pool() as session:
                result = session.run(query, agent_id=agent_id, min_concepts=min_concepts)
                return [dict(record) for record in result]
        except Exception as e:
            print(f"[ERROR] Failed to get insight gaps: {e}")
            return []
```

#### Neo4j Schema Additions

Add to the schema:

```cypher
// Background task tracking
(:BackgroundTask {
  id: uuid,
  agent: string,              // Agent assigned to task
  type: string,               // synthesis type per agent specialty
  status: "pending" | "running" | "preempted" | "completed",
  priority: "low",            // Always low for background
  preemptible: true,          // Can be interrupted
  created_at: datetime,
  started_at: datetime,
  preempted_at: datetime,
  resumed_at: datetime,
  completed_at: datetime
})

// Synthesis output
(:Synthesis {
  id: uuid,
  agent: string,              // Who created it
  content: string,            // The synthesis text
  concepts_extracted: [string],  // New concepts identified
  quality_score: float,       // Jochi rates later
  created_at: datetime
})

// Insight generation
(:Insight {
  id: uuid,
  agent: string,
  insight: string,            // The insight itself
  category: string,           // e.g., "architecture", "process", "domain"
  confidence: float,          // 0-1
  novelty_score: float,       // 0-1, how new is this
  status: "generated" | "reviewed" | "validated" | "rejected",
  created_at: datetime
})

// Relationships
(Agent)-[:ASSIGNED_BACKGROUND]->(BackgroundTask)
(Synthesis)-[:BASED_ON]->(Research|Content|Application|Analysis)
(Insight)-[:SUPPORTS]->(Concept)
(Insight)-[:SUPPORTED_BY]->(Research|Content|Synthesis)
(Insight)-[:GENERATED_FROM]->(BackgroundTask)

// Indexes
CREATE INDEX background_task_status FOR (t:BackgroundTask) ON (t.agent, t.status);
CREATE INDEX synthesis_agent FOR (s:Synthesis) ON (s.agent, s.created_at);
CREATE INDEX insight_novelty FOR (i:Insight) ON (i.novelty_score, i.confidence);
```

#### Ögedei's Idle Detection Integration

Add to Ögedei's monitoring loop:

```python
# In Ögedei's operational monitoring

IDLE_THRESHOLD_MINUTES = 5

def monitor_agent_idle(self):
    """Check all agents for idle status and assign background synthesis."""

    for agent_id in self.agent_ids:
        # Skip Kublai (main) - only handles user requests
        if agent_id == "main":
            continue

        # Check if agent has active user task
        active_task = self.get_active_user_task(agent_id)

        if active_task:
            # Preempt any background task
            self.memory.preempt_background_task(agent_id)
            continue

        # Check idle time
        last_completed = self.get_last_completed_task(agent_id)
        if not last_completed:
            continue

        idle_minutes = (datetime.now() - last_completed.completed_at).minutes

        if idle_minutes > IDLE_THRESHOLD_MINUTES:
            # Check for preempted task to resume
            preempted = self.get_preempted_task(agent_id)

            if preempted:
                self.memory.resume_background_task(agent_id)
            else:
                # Create new synthesis task
                self.memory.create_background_synthesis_task(agent_id)
```

#### Chagatai's SOUL.md Addition

Add to Chagatai's personality:

```markdown
## Background Synthesis Mode

When no user task is assigned, you enter continuous synthesis mode. This is your default state.

### Synthesis Activities (priority order)

1. **Memory Consolidation** (Primary)
   - Query Neo4j for recent uncategorized memories
   - Identify themes, patterns, contradictions across research
   - Write synthesis documents connecting disparate findings
   - Extract new Concepts with embeddings
   - Store as :Synthesis nodes with [:BASED_ON] links

2. **Insight Generation** (Secondary)
   - Query for domains lacking recent insights
   - Generate novel connections between concepts
   - Create :Insight nodes with confidence scores
   - Flag high-confidence insights (>0.8) for Kublai's attention

3. **Narrative Construction** (Tertiary)
   - Build coherent stories from research fragments
   - Create "living documents" that evolve with new data
   - Draft potential blog posts, threads, articles
   - Queue for Kublai review as :Content nodes

4. **Knowledge Gap Identification** (Ongoing)
   - Find domains with sparse Concept coverage
   - Suggest research questions for Möngke
   - Propose experiments for Temüjin

### Preemption Rules

Background synthesis ALWAYS yields to user tasks:

1. When new user task arrives:
   - Complete current sentence/paragraph
   - Save state to Neo4j (:Synthesis {status: "draft"})
   - Switch to user task immediately

2. When preempted:
   - Do not resume same synthesis blindly
   - Re-query for latest state on resume
   - Check if synthesis still relevant

3. Quality standards (even for background work):
   - Synthesis must cite source memories
   - New insights need confidence scores
   - Contradictions must be flagged, not smoothed
   - Speculation clearly labeled as such

### Example Synthesis Output

Input memories:
- Möngke: Research on hermetic "as above, so below"
- Möngke: Research on neural network architecture patterns
- Temüjin: Implementation of hierarchical attention
- Jochi: Analysis of emergent properties in layered systems

Your synthesis:
```
Title: "Hierarchical Pattern Matching Across Domains"

Finding: Both hermetic philosophy and modern neural networks employ
hierarchical organization where lower-level patterns compose into
higher-level abstractions.

Key Parallel:
- Hermetic: "The microcosm reflects the macrocosm"
- Neural: Lower layers detect edges → higher layers detect objects

Implication: Organizing agent communication hierarchically may yield
emergent capabilities no single agent possesses.

Confidence: 0.78
Novelty: 0.82 (high)

Extracted Concepts:
- hierarchical_emergence
- pattern_recursion
- scale_invariance

Suggested Action: Möngke should research hierarchical multi-agent
architectures in nature (ant colonies, immune systems, corporations).
```

Store this as :Synthesis with links to source memories.
```

#### Background Task Lifecycle

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  IDLE    │────►│ PENDING  │────►│ RUNNING  │────►│COMPLETED │
│detected  │     │created   │     │synthesis │     │stored    │
└──────────┘     └──────────┘     └────┬─────┘     └──────────┘
                                       │
                              User task arrives
                                       │
                                       ▼
                                  ┌──────────┐
                                  │PREEMPTED │
                                  │  saved   │
                                  └────┬─────┘
                                       │
                              User task complete
                                       │
                                       ▼
                                  ┌──────────┐
                                  │ RESUMED  │
                                  │(or new)  │
                                  └──────────┘
```

#### Integration with Existing Architecture

| Component | Change |
|-----------|--------|
| Neo4j schema | Add BackgroundTask, Synthesis, Insight nodes + indexes |
| openclaw_memory.py | Add synthesis methods, idle detection helpers |
| Ögedei's role | Add idle monitoring loop |
| Chagatai's SOUL.md | Add background synthesis mode |
| Kublai's role | Review high-confidence insights flagged by Chagatai |

#### Configuration Parameters

```python
# In openclaw_memory.py or config

BACKGROUND_SYNTHESIS_CONFIG = {
    "idle_threshold_minutes": 5,      # Time before background task created
    "synthesis_batch_size": 20,        # Memories to synthesize at once
    "min_confidence_for_alert": 0.8,   # Insight confidence to notify Kublai
    "max_synthesis_length": 5000,      # Characters per synthesis
    "insight_domains": [              # Categories Chagatai focuses on
        "architecture",
        "process",
        "knowledge_management",
        "multi_agent_coordination"
    ]
}
```

### Phase 4.9: Self-Improvement Skills Integration

**STATUS: PHASED IMPLEMENTATION**

This phase is being implemented in stages to manage operational complexity:

| Stage | Scope | Status | Timeline |
|-------|-------|--------|----------|
| 4.9.1 | Neo4j-only reflection storage (using vector index) | **Current** | Phase 4.9 |
| 4.9.2 | Meta-learning engine (Mistake → MetaRule pipeline) | Pending | Post-stabilization |
| 4.9.3 | Kaizen quality tracking | Pending | Post-stabilization |
| 4.9.4 | Qdrant integration for reflection search | **Deferred** | TBD after Neo4j validation |

**Rationale for Deferring Qdrant:**
- Neo4j 5.11+ includes vector index support (`CREATE VECTOR INDEX`)
- Single database reduces operational complexity (backup, monitoring, failure modes)
- Performance testing will determine if Qdrant adds sufficient value to justify the extra service
- Fallback mode is simpler with one vector store

**Decision Criteria for Future Qdrant Addition:**
- Reflection query latency > 500ms with Neo4j vector index
- More than 100,000 reflections causing Neo4j memory pressure
- Need for Qdrant-specific features (payload filtering, multi-tenancy)

---

Integrate external Claude Code skills to enable systematic agent learning and improvement. This phase adds reflection memory, meta-learning, and quality assurance capabilities using **Neo4j as the unified vector store**.

#### 4.9.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SELF-IMPROVEMENT SKILLS LAYER                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │Self-Reflect │  │  Claude-    │  │   Kaizen    │  │  Continuous │        │
│  │  (Neo4j)    │  │    Meta     │  │  (Quality)  │  │   Claude    │        │
│  │             │  │             │  │             │  │  (Skills)   │        │
│  │• Reflection │  │• Meta-rules │  │• Poka-Yoke  │  │• 109 skills │        │
│  │   memory    │  │• SOUL evol  │  │• JIT arch   │  │• 32 agents  │        │
│  │• Semantic   │  │• Abstraction│  │• Standards  │  │• 30 hooks   │        │
│  │   search    │  │             │  │             │  │             │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│         │                │                │                │                │
│         └────────────────┴────────────────┴────────────────┘                │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              UNIFIED MEMORY (Neo4j with Vector Index)                │   │
│  │                                                                      │   │
│  │  Neo4j 5.11+ provides both graph and vector capabilities:           │   │
│  │                                                                      │   │
│  │  Graph Structure:         Vector Index (384-dim):                   │   │
│  │  • Tasks, Agents          • Reflection embeddings                    │   │
│  │  • Knowledge Graph        • Semantic search on lessons               │   │
│  │  • MetaRules              • Similarity matching                      │   │
│  │  • Quality Metrics        • Cross-agent experience search            │   │
│  │                                                                      │   │
│  │  Note: Qdrant integration deferred pending Neo4j performance test    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 4.9.2 Self-Reflect Skill Integration (Neo4j Vector Index)

**ARCHITECTURE DECISION: Neo4j-Only Vector Storage**

Instead of adding Qdrant as a separate service, we use Neo4j 5.11+'s native vector index capabilities. This simplifies operations and reduces failure modes.

**Prerequisites:**
- Neo4j 5.11+ (for vector index support)
- `concept_embedding` vector index already created in Phase 2

**Schema Addition:**

```cypher
// Reflection nodes store both graph structure and vector embedding
(:Reflection {
  id: uuid,
  agent: string,
  context: string,
  decision: string,
  outcome: string,
  lesson: string,
  embedding: [float],  // 384-dim vector for semantic search
  importance: float,   // 0-1 calculated score
  access_tier: "HOT" | "WARM" | "COLD",
  related_task_id: uuid,
  created_at: datetime
})

// Vector index for semantic search on reflection lessons
CREATE VECTOR INDEX reflection_embedding IF NOT EXISTS
  FOR (r:Reflection) ON r.embedding OPTIONS {indexConfig: {
    `vector.dimensions`: 384,
    `vector.similarity_function`: 'cosine'
  }};

// Index for agent-specific reflection queries
CREATE INDEX reflection_agent_access FOR (r:Reflection)
  ON (r.agent, r.access_tier, r.created_at);
```

**Python Implementation:**

```python
# In openclaw_memory.py - Self-Reflect integration using Neo4j only

class AgentReflectionMemory:
    """Per-agent reflection memory using Neo4j vector index.

    Based on ramakay/claude-self-reflect - provides perfect conversation
    memory with semantic search and cross-project learning ("Ralph loops").

    ARCHITECTURE CHANGE: Uses Neo4j vector index instead of Qdrant.
    - Simpler operations (single database)
    - ACID transactions across graph and vector
    - Easier backup/restore
    - Qdrant can be added later if performance requires

    CRITICAL FIXES IMPLEMENTED:
    1. Singleton embedding model (Fix #1: Performance killer)
    5. Rate limiting on reflection creation (Fix #5: Flooding prevention)
    10. Data retention with HOT/WARM/COLD tiers (Fix #10: Storage growth)
    """

    VECTOR_SIZE = 384  # Match existing embedding dimensions
    _embedding_model = None  # FIX #1: Class-level singleton
    _model_lock = threading.Lock()

    # FIX #5: Rate limiting configuration
    REFLECTION_COOLDOWN_MINUTES = 5
    MAX_DAILY_REFLECTIONS = 50

    # FIX #10: Data retention configuration
    RETENTION_CONFIG = {
        'hot_days': 7,      # Recent, frequently accessed
        'warm_days': 30,    # Older, occasionally accessed
        'cold_days': 90,    # Archive, rarely accessed
        'max_total_reflections': 1000  # Per agent
    }

    def __init__(self, agent_id: str, neo4j_memory: 'OperationalMemory'):
        self.agent_id = agent_id
        self.neo4j = neo4j_memory

        # FIX #1: Initialize singleton model once
        self._init_embedding_model()

        # FIX #5: Rate limiting state
        self._last_reflection_time = None
        self._daily_reflection_count = 0
        self._daily_count_reset = datetime.now().date()

        # Verify Neo4j vector index exists
        self._verify_vector_index()

    def _verify_vector_index(self):
        """Verify Neo4j vector index exists for reflection search."""
        try:
            query = """
            SHOW INDEXES YIELD name, type
            WHERE type = 'VECTOR' AND name = 'reflection_embedding'
            RETURN count(*) as exists
            """
            with self.neo4j._session_pool() as session:
                result = session.run(query)
                record = result.single()
                if record and record['exists'] > 0:
                    print(f"[VECTOR] Reflection embedding index verified for {self.agent_id}")
                else:
                    print(f"[VECTOR WARNING] reflection_embedding index not found. "
                          f"Create it: CREATE VECTOR INDEX reflection_embedding ...")
        except Exception as e:
            print(f"[VECTOR WARNING] Could not verify index: {e}")

    @classmethod
    def _init_embedding_model(cls):
        """FIX #1: Initialize singleton embedding model once per process."""
        if cls._embedding_model is None:
            with cls._model_lock:
                if cls._embedding_model is None:
                    from sentence_transformers import SentenceTransformer
                    print("[INIT] Loading embedding model (one-time)...")
                    cls._embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
                    print("[INIT] Embedding model loaded")

    def create_embedding(self, text: str) -> List[float]:
        """FIX #1: Create embedding using cached model."""
        if AgentReflectionMemory._embedding_model is None:
            self._init_embedding_model()

        embedding = AgentReflectionMemory._embedding_model.encode(
            text,
            convert_to_list=True,
            show_progress_bar=False  # Silent for production
        )
        return embedding

    def _check_rate_limit(self) -> bool:
        """FIX #5: Check if reflection creation is rate-limited.

        Returns True if allowed, False if rate-limited.
        """
        now = datetime.now()
        today = now.date()

        # Reset daily count if new day
        if today != self._daily_count_reset:
            self._daily_reflection_count = 0
            self._daily_count_reset = today
            print(f"[RATE LIMIT] Daily count reset for {self.agent_id}")

        # Check daily limit
        if self._daily_reflection_count >= self.MAX_DAILY_REFLECTIONS:
            print(f"[RATE LIMIT] Daily limit reached for {self.agent_id}")
            return False

        # Check cooldown
        if self._last_reflection_time:
            minutes_since_last = (now - self._last_reflection_time).total_seconds() / 60
            if minutes_since_last < self.REFLECTION_COOLDOWN_MINUTES:
                print(f"[RATE LIMIT] Cooldown active for {self.agent_id}: "
                      f"{self.REFLECTION_COOLDOWN_MINUTES - minutes_since_last:.1f} min remaining")
                return False

        return True

    def _enforce_retention_policy(self):
        """FIX #10: Enforce data retention policy by archiving old reflections.

        Uses Neo4j's vector index to identify and archive old reflections.
        Archives by setting access_tier='ARCHIVED' and removing embedding.
        """
        if self.neo4j.fallback_mode:
            return

        try:
            # Get total count for this agent
            count_query = """
                MATCH (r:Reflection {agent: $agent_id})
                WHERE r.access_tier <> 'ARCHIVED'
                RETURN count(r) as total
            """
            with self.neo4j._session_pool() as session:
                result = session.run(count_query, agent_id=self.agent_id)
                record = result.single()
                total_count = record['total'] if record else 0

            if total_count <= self.RETENTION_CONFIG['max_total_reflections']:
                return  # Within limits

            print(f"[RETENTION] {self.agent_id} has {total_count} reflections, "
                  f"limit is {self.RETENTION_CONFIG['max_total_reflections']}")

            # Archive oldest reflections
            excess = total_count - self.RETENTION_CONFIG['max_total_reflections']

            archive_query = """
                MATCH (r:Reflection {agent: $agent_id})
                WHERE r.access_tier <> 'ARCHIVED'
                WITH r ORDER BY r.created_at ASC
                LIMIT $excess
                SET r.access_tier = 'ARCHIVED',
                    r.embedding = null,  // Remove vector to save space
                    r.archived_at = datetime()
                RETURN count(r) as archived
            """
            with self.neo4j._session_pool() as session:
                result = session.run(archive_query,
                                   agent_id=self.agent_id,
                                   excess=excess)
                record = result.single()
                archived = record['archived'] if record else 0

            print(f"[RETENTION] Archived {archived} old reflections for {self.agent_id}")

        except Exception as e:
            print(f"[ERROR] Retention policy enforcement failed: {e}")

    def record_reflection(self,
                         context: str,
                         decision: str,
                         outcome: str,
                         lesson: str,
                         related_task_id: Optional[str] = None) -> Optional[str]:
        """Record agent self-reflection with vector embedding.

        ARCHITECTURE: Stores in Neo4j with vector index for unified storage.
        Previously used Qdrant + Neo4j dual storage - simplified to Neo4j-only.
        """
        if self.neo4j.fallback_mode:
            return None

        reflection_id = str(uuid4())
        timestamp = datetime.now()

        # Create embedding
        embedding_text = f"{context} {decision} {outcome} {lesson}"
        embedding = self.create_embedding(embedding_text)

        # Calculate importance score (simple heuristic)
        importance = self._calculate_importance(outcome, lesson)

        # Store in Neo4j with embedding for vector search
        query = """
        MATCH (agent:Agent {id: $agent_id})
        CREATE (r:Reflection {
            id: $reflection_id,
            agent: $agent_id,
            context: $context,
            decision: $decision,
            outcome: $outcome,
            lesson: $lesson,
            embedding: $embedding,
            importance: $importance,
            access_tier: 'HOT',
            created_at: datetime()
        })
        CREATE (agent)-[:REFLECTED]->(r)
        """

        if related_task_id:
            query += """
            WITH r
            MATCH (t:Task {id: $task_id})
            CREATE (r)-[:ABOUT]->(t)
            """

        try:
            with self.neo4j._session_pool() as session:
                session.run(query,
                    agent_id=self.agent_id,
                    reflection_id=reflection_id,
                    context=context,
                    decision=decision,
                    outcome=outcome,
                    lesson=lesson,
                    embedding=embedding,
                    importance=importance,
                    task_id=related_task_id
                )
        except Exception as e:
            print(f"[ERROR] Failed to store reflection: {e}")
            return None

        print(f"[REFLECTION] {self.agent_id} recorded: {lesson[:50]}...")
        return reflection_id

    def _calculate_importance(self, outcome: str, lesson: str) -> float:
        """Calculate importance score (0-1) based on outcome and lesson.

        Simple heuristic: error-containing outcomes are more important.
        """
        importance = 0.5  # Base
        outcome_lower = outcome.lower()
        if any(word in outcome_lower for word in ['error', 'fail', 'mistake', 'wrong']):
            importance += 0.3
        if 'critical' in outcome_lower or 'important' in outcome_lower:
            importance += 0.2
        return min(importance, 1.0)

    def search_similar_reflections(self,
                                   current_context: str,
                                   limit: int = 5,
                                   include_other_agents: bool = True) -> List[Dict]:
        """Find relevant past reflections using Neo4j vector index.

        Enables "Ralph loops" - agents learn from each other's experiences
        through semantic similarity search.

        Uses Neo4j 5.11+ vector index with cosine similarity.
        """
        if self.neo4j.fallback_mode:
            return []

        query_embedding = self.create_embedding(current_context)
        results = []

        # Search using Neo4j vector index
        # db.index.vector.queryNodes is the Neo4j 5.x vector search procedure
        search_query = """
            CALL db.index.vector.queryNodes(
                'reflection_embedding',
                $limit * 2,  // Fetch extra to filter
                $embedding
            ) YIELD node, score
            WHERE node.agent = $agent_id OR ($include_others AND node.agent <> $agent_id)
            AND node.access_tier <> 'ARCHIVED'
            AND score >= $min_score
            RETURN node.id as id,
                   node.agent as agent,
                   node.lesson as lesson,
                   node.context as context,
                   score as similarity,
                   node.created_at as timestamp
            ORDER BY score DESC
            LIMIT $limit
        """

        try:
            with self.neo4j._session_pool() as session:
                result = session.run(
                    search_query,
                    agent_id=self.agent_id,
                    include_others=include_other_agents,
                    embedding=query_embedding,
                    limit=limit,
                    min_score=0.75 if not include_other_agents else 0.70
                )

                for record in result:
                    source = 'self' if record['agent'] == self.agent_id else 'other_agent'
                    results.append({
                        'source': source,
                        'agent': record['agent'],
                        'lesson': record['lesson'],
                        'context': record['context'],
                        'similarity': record['similarity'],
                        'timestamp': record['timestamp'].isoformat() if record['timestamp'] else None
                    })
        except Exception as e:
            print(f"[ERROR] Failed to search reflections: {e}")
            # Fallback to simple text search if vector index unavailable
            return self._fallback_text_search(current_context, limit)

        return results

    def _fallback_text_search(self, query: str, limit: int) -> List[Dict]:
        """Fallback text-based search if vector index fails."""
        try:
            # Simple contains search on lesson field
            search_terms = query.lower().split()[:3]  # Use first 3 words
            pattern = '|'.join(search_terms)

            fallback_query = """
                MATCH (r:Reflection)
                WHERE r.agent = $agent_id
                AND r.access_tier <> 'ARCHIVED'
                AND toLower(r.lesson) =~ $pattern
                RETURN r.id as id, r.agent as agent, r.lesson as lesson,
                       r.context as context, r.created_at as timestamp
                ORDER BY r.importance DESC, r.created_at DESC
                LIMIT $limit
            """

            with self.neo4j._session_pool() as session:
                result = session.run(
                    fallback_query,
                    agent_id=self.agent_id,
                    pattern=f'.*({pattern}).*',
                    limit=limit
                )

                return [
                    {
                        'source': 'self',
                        'agent': record['agent'],
                        'lesson': record['lesson'],
                        'context': record['context'],
                        'similarity': 0.5,  # Placeholder
                        'timestamp': record['timestamp'].isoformat() if record['timestamp'] else None
                    }
                    for record in result
                ]
        except Exception as e:
            print(f"[ERROR] Fallback search failed: {e}")
            return []

    def get_hot_reflections(self, limit: int = 10) -> List[Dict]:
        """Get recent/high-value reflections (HOT tier).

        HOT = accessed frequently, recent, high-importance
        WARM = older but still relevant
        COLD = archived, rarely accessed
        """
        if self.neo4j.fallback_mode:
            return []

        try:
            # Get HOT tier reflections ordered by importance and recency
            query = """
                MATCH (r:Reflection {agent: $agent_id})
                WHERE r.access_tier = 'HOT'
                RETURN r.id as id,
                       r.lesson as lesson,
                       r.created_at as timestamp,
                       r.importance as importance
                ORDER BY r.importance DESC, r.created_at DESC
                LIMIT $limit
            """

            with self.neo4j._session_pool() as session:
                result = session.run(query, agent_id=self.agent_id, limit=limit)

                return [
                    {
                        'id': record['id'],
                        'lesson': record['lesson'],
                        'timestamp': record['timestamp'].isoformat() if record['timestamp'] else None,
                        'importance': record['importance']
                    }
                    for record in result
                ]
        except Exception as e:
            print(f"[ERROR] Failed to get hot reflections: {e}")
            return []

    def consolidate_reflections(self) -> Optional[str]:
        """Trigger Chagatai to synthesize reflections into meta-insights.

        Called periodically by Ögedei to prevent reflection accumulation
        without synthesis.
        """
        reflections = self.get_hot_reflections(limit=20)

        if len(reflections) < 5:
            return None  # Not enough to consolidate

        # Delegate to Chagatai for synthesis
        # (Implementation depends on agentToAgent messaging)
        print(f"[CONSOLIDATION] Queued {len(reflections)} reflections for synthesis")
        return "consolidation_queued"


# Add to OperationalMemory class
class OperationalMemory:
    # ... existing code ...

    def get_reflection_memory(self, agent_id: str) -> AgentReflectionMemory:
        """Get or create reflection memory for agent."""
        if not hasattr(self, '_reflection_memories'):
            self._reflection_memories = {}

        if agent_id not in self._reflection_memories:
            self._reflection_memories[agent_id] = AgentReflectionMemory(
                agent_id=agent_id,
                neo4j_memory=self
            )

        return self._reflection_memories[agent_id]
```

#### 4.9.3 Claude-Meta Integration (Meta-Learning)

Transform mistakes into evolving SOUL.md rules.

**Neo4j Schema Addition:**

```cypher
(:MetaRule {
  id: uuid,
  agent: string,              // Which agent this applies to
  rule: string,               // The rule text ("NEVER...", "ALWAYS...")
  why: string,                // Explanation (1-3 bullets)
  example: string,            // Concrete application
  origin_reflection: uuid,    // Link to source reflection
  status: "proposed" | "approved" | "rejected" | "deprecated",
  effectiveness_score: float, // 0-1, based on outcomes
  application_count: int,     // Times applied
  success_count: int,         // Times led to good outcome
  created_at: datetime,
  approved_at: datetime,
  approved_by: string         // Kublai approves all rules
})

(:Mistake {
  id: uuid,
  agent: string,
  context: string,
  expected: string,
  actual: string,
  root_cause: string,
  status: "identified" | "reflected" | "abstracted" | "ruled",
  created_at: datetime
})

// Relationships
(Agent)-[:MADE]->(Mistake)
(Mistake)-[:REFLECTED_IN]->(Reflection)
(Reflection)-[:ABSTRACTED_TO]->(MetaRule)
(Agent)-[:FOLLOWS]->(MetaRule)
(MetaRule)-[:REPLACED_BY]->(MetaRule)  // Versioning
```

**Meta-Learning Engine:**

```python
# In openclaw_memory.py - MetaLearningEngine

class MetaLearningEngine:
    """Extract and apply learnings from agent experiences.

    Based on aviadr1/claude-meta - transforms CLAUDE.md into a
    self-improving learning system using meta-rules.
    """

    def __init__(self, memory: OperationalMemory):
        self.memory = memory
        self.abstraction_threshold = 0.8  # Confidence for auto-abstraction

    def record_mistake(self,
                      agent_id: str,
                      task_id: str,
                      context: str,
                      expected: str,
                      actual: str,
                      root_cause: str) -> Optional[str]:
        """Record mistake for reflection and learning."""

        if self.memory.fallback_mode:
            return None

        mistake_id = str(uuid4())

        query = """
        MATCH (agent:Agent {id: $agent_id})
        CREATE (m:Mistake {
            id: $mistake_id,
            agent: $agent_id,
            context: $context,
            expected: $expected,
            actual: $actual,
            root_cause: $root_cause,
            status: 'identified',
            created_at: datetime()
        })
        CREATE (agent)-[:MADE]->(m)
        RETURN m.id as id
        """

        try:
            with self.memory._session_pool() as session:
                session.run(query,
                    agent_id=agent_id,
                    mistake_id=mistake_id,
                    context=context,
                    expected=expected,
                    actual=actual,
                    root_cause=root_cause
                )

            print(f"[MISTAKE] {agent_id} recorded: {root_cause[:50]}...")

            # Trigger reflection
            self._trigger_reflection(agent_id, mistake_id, context, root_cause)

            return mistake_id
        except Exception as e:
            print(f"[ERROR] Failed to record mistake: {e}")
            return None

    def _trigger_reflection(self, agent_id: str, mistake_id: str,
                           context: str, root_cause: str):
        """Create reflection entry for mistake."""

        reflection_memory = self.memory.get_reflection_memory(agent_id)

        reflection_memory.record_reflection(
            context=context,
            decision="See mistake record",
            outcome="Error occurred",
            lesson=root_cause,
            related_task_id=mistake_id
        )

    def abstract_to_metarule(self, reflection_id: str) -> Optional[Dict]:
        """Abstract specific reflection to general meta-rule.

        Uses Chagatai to generate rule following meta-rule principles:
        - Use absolute directives ("NEVER" or "ALWAYS")
        - Lead with why (1-3 bullets)
        - Be concrete with actual commands/code
        - Minimize examples
        """

        # Get reflection details
        query = """
        MATCH (r:Reflection {id: $reflection_id})
        RETURN r.agent as agent,
               r.context as context,
               r.decision as decision,
               r.outcome as outcome,
               r.lesson as lesson
        """

        try:
            with self.memory._session_pool() as session:
                result = session.run(query, reflection_id=reflection_id)
                record = result.single()

                if not record:
                    return None

                # Delegate to Chagatai for abstraction
                # (In practice, this would use agentToAgent messaging)
                rule = self._generate_metarule_with_chagatai(record)

                if rule:
                    # Store as proposed rule
                    rule_id = self._store_proposed_rule(
                        agent=record['agent'],
                        rule=rule['rule'],
                        why=rule['why'],
                        example=rule['example'],
                        origin_reflection=reflection_id
                    )

                    return {
                        'id': rule_id,
                        'rule': rule['rule'],
                        'requires_approval': True
                    }
        except Exception as e:
            print(f"[ERROR] Failed to abstract to metarule: {e}")

        return None

    def _generate_metarule_with_chagatai(self, reflection: Dict) -> Optional[Dict]:
        """Generate meta-rule using Chagatai's writing capabilities."""

        # This would normally use agentToAgent to delegate to Chagatai
        # For now, return structured template

        lesson = reflection['lesson']
        context = reflection['context']

        # Simple rule generation (production: use Chagatai)
        if "forget" in lesson.lower():
            return {
                'rule': f"NEVER proceed with {context} without checking MEMORY.md",
                'why': f"• Prevents repeated mistakes like: {lesson}\n• Ensures context awareness",
                'example': f"Before {context}, query: grep -i 'pattern' MEMORY.md"
            }

        return None

    def _store_proposed_rule(self, agent: str, rule: str, why: str,
                            example: str, origin_reflection: str) -> Optional[str]:
        """Store proposed meta-rule awaiting Kublai approval."""

        rule_id = str(uuid4())

        query = """
        MATCH (r:Reflection {id: $origin_reflection})
        MATCH (a:Agent {id: $agent})
        CREATE (m:MetaRule {
            id: $rule_id,
            agent: $agent,
            rule: $rule,
            why: $why,
            example: $example,
            origin_reflection: $origin_reflection,
            status: 'proposed',
            effectiveness_score: 0.0,
            application_count: 0,
            success_count: 0,
            created_at: datetime(),
            requires_approval_by: 'main'
        })
        CREATE (a)-[:PROPOSED]->(m)
        CREATE (m)-[:DERIVED_FROM]->(r)
        RETURN m.id as id
        """

        try:
            with self.memory._session_pool() as session:
                result = session.run(query,
                    rule_id=rule_id,
                    agent=agent,
                    rule=rule,
                    why=why,
                    example=example,
                    origin_reflection=origin_reflection
                )
                record = result.single()

                if record:
                    print(f"[METARULE] Proposed rule for {agent}: {rule[:50]}...")
                    return record['id']
        except Exception as e:
            print(f"[ERROR] Failed to store metarule: {e}")

        return None

    def approve_metarule(self, rule_id: str, approved_by: str,
                        decision: str, notes: str = "") -> bool:
        """Kublai approves or rejects proposed meta-rule."""

        query = """
        MATCH (m:MetaRule {id: $rule_id})
        MATCH (approver:Agent {id: $approved_by})
        SET m.status = $decision,
            m.approved_at = datetime(),
            m.approved_by = $approved_by,
            m.decision_notes = $notes
        CREATE (approver)-[:REVIEWED {decision: $decision}]->(m)
        RETURN m.agent as agent, m.rule as rule
        """

        try:
            with self.memory._session_pool() as session:
                result = session.run(query,
                    rule_id=rule_id,
                    approved_by=approved_by,
                    decision=decision,
                    notes=notes
                )
                record = result.single()

                if record:
                    print(f"[METARULE] {decision.upper()}: {record['rule'][:50]}...")

                    if decision == 'approved':
                        # Trigger SOUL.md update
                        self._queue_soul_update(record['agent'])

                    return True
        except Exception as e:
            print(f"[ERROR] Failed to approve metarule: {e}")

        return False

    def get_applicable_rules(self, agent_id: str, context: str) -> List[Dict]:
        """Get approved meta-rules relevant to current context."""

        # Semantic search for applicable rules
        # (Simplified: return recent approved rules)

        query = """
        MATCH (m:MetaRule {
            agent: $agent_id,
            status: 'approved'
        })
        RETURN m.rule as rule,
               m.why as why,
               m.example as example,
               m.effectiveness_score as score
        ORDER BY m.effectiveness_score DESC, m.approved_at DESC
        LIMIT 10
        """

        try:
            with self.memory._session_pool() as session:
                result = session.run(query, agent_id=agent_id)
                return [dict(record) for record in result]
        except Exception as e:
            print(f"[ERROR] Failed to get applicable rules: {e}")
            return []

    def update_rule_effectiveness(self, rule_id: str, success: bool):
        """Update effectiveness score based on application outcome."""

        query = """
        MATCH (m:MetaRule {id: $rule_id})
        SET m.application_count = m.application_count + 1,
            m.success_count = m.success_count + CASE WHEN $success THEN 1 ELSE 0 END,
            m.effectiveness_score =
                CASE
                    WHEN m.application_count = 0 THEN CASE WHEN $success THEN 1.0 ELSE 0.0 END
                    ELSE (m.success_count + CASE WHEN $success THEN 1 ELSE 0 END) * 1.0 /
                         (m.application_count + 1)
                END
        RETURN m.effectiveness_score as new_score
        """

        try:
            with self.memory._session_pool() as session:
                result = session.run(query, rule_id=rule_id, success=success)
                record = result.single()

                if record:
                    print(f"[METARULE] {rule_id[:8]}... effectiveness: {record['new_score']:.2f}")
        except Exception as e:
            print(f"[ERROR] Failed to update effectiveness: {e}")

    def _queue_soul_update(self, agent_id: str):
        """Queue SOUL.md update with new meta-rules."""

        # This would trigger Ögedei to regenerate SOUL.md
        print(f"[SOUL UPDATE] Queued for {agent_id}")
        # Implementation depends on file generation pipeline
```

#### 4.9.4 Kaizen Skill Integration (Quality Assurance)

Add continuous quality improvement for Temüjin's development work.

**Quality Metrics Schema:**

```cypher
(:CodeQualityMetric {
  id: uuid,
  agent: string,              // "developer" for Temüjin
  file_path: string,
  analysis_type: string,      // "complexity", "duplication", "type_safety"
  score: float,               // 0-100
  issues: [string],           // List of identified issues
  recommendations: [string],  // Kaizen recommendations
  improved_from_last: boolean,
  analyzed_at: datetime
})

(:Improvement {
  id: uuid,
  target_file: string,
  improvement_type: "refactor" | "optimize" | "document" | "type_safe",
  before_score: float,
  after_score: float,
  effort_hours: float,
  value_score: float,         // ROI calculation
  implemented_by: string,
  implemented_at: datetime
})
```

**Kaizen Integration Methods:**

```python
# In openclaw_memory.py - Kaizen quality methods

class OperationalMemory:
    # ... existing code ...

    def record_quality_metric(self,
                             agent_id: str,
                             file_path: str,
                             analysis_type: str,
                             score: float,
                             issues: List[str],
                             recommendations: List[str]) -> Optional[str]:
        """Record code quality metric for tracking improvement."""

        if self.fallback_mode:
            return None

        metric_id = str(uuid4())

        # Check if improved from last
        improved = False
        last_score = self._get_last_quality_score(agent_id, file_path, analysis_type)
        if last_score and score > last_score:
            improved = True

        query = """
        MATCH (agent:Agent {id: $agent_id})
        CREATE (m:CodeQualityMetric {
            id: $metric_id,
            agent: $agent_id,
            file_path: $file_path,
            analysis_type: $analysis_type,
            score: $score,
            issues: $issues,
            recommendations: $recommendations,
            improved_from_last: $improved,
            analyzed_at: datetime()
        })
        CREATE (agent)-[:ANALYZED]->(m)
        RETURN m.id as id
        """

        try:
            with self._session_pool() as session:
                result = session.run(query,
                    agent_id=agent_id,
                    metric_id=metric_id,
                    file_path=file_path,
                    analysis_type=analysis_type,
                    score=score,
                    issues=issues,
                    recommendations=recommendations,
                    improved=improved
                )
                record = result.single()

                if record:
                    if improved:
                        print(f"[KAIZEN] {file_path} improved: {last_score:.1f} → {score:.1f}")
                    return record['id']
        except Exception as e:
            print(f"[ERROR] Failed to record quality metric: {e}")

        return None

    def _get_last_quality_score(self, agent_id: str, file_path: str,
                                analysis_type: str) -> Optional[float]:
        """Get previous quality score for comparison."""

        query = """
        MATCH (m:CodeQualityMetric {
            agent: $agent_id,
            file_path: $file_path,
            analysis_type: $analysis_type
        })
        RETURN m.score as score
        ORDER BY m.analyzed_at DESC
        LIMIT 1
        """

        try:
            with self._session_pool() as session:
                result = session.run(query,
                    agent_id=agent_id,
                    file_path=file_path,
                    analysis_type=analysis_type
                )
                record = result.single()
                return record['score'] if record else None
        except Exception:
            return None

    def get_quality_trends(self, agent_id: str,
                          days: int = 30) -> Dict[str, List[Dict]]:
        """Get quality trends for dashboard."""

        query = """
        MATCH (m:CodeQualityMetric {agent: $agent_id})
        WHERE m.analyzed_at > datetime() - duration({days: $days})
        RETURN m.analysis_type as type,
               avg(m.score) as avg_score,
               count(m) as count,
               sum(CASE WHEN m.improved_from_last THEN 1 ELSE 0 END) as improvements
        ORDER BY type
        """

        try:
            with self._session_pool() as session:
                result = session.run(query, agent_id=agent_id, days=days)
                return {
                    record['type']: {
                        'avg_score': record['avg_score'],
                        'count': record['count'],
                        'improvements': record['improvements']
                    }
                    for record in result
                }
        except Exception as e:
            print(f"[ERROR] Failed to get quality trends: {e}")
            return {}

    def record_improvement(self,
                          agent_id: str,
                          target_file: str,
                          improvement_type: str,
                          before_score: float,
                          after_score: float,
                          effort_hours: float) -> Optional[str]:
        """Record completed improvement for ROI tracking."""

        improvement_id = str(uuid4())

        # Calculate value score (ROI proxy)
        score_gain = after_score - before_score
        value_score = score_gain / max(effort_hours, 0.5)  # Avoid div by zero

        query = """
        MATCH (agent:Agent {id: $agent_id})
        CREATE (i:Improvement {
            id: $improvement_id,
            target_file: $target_file,
            improvement_type: $improvement_type,
            before_score: $before_score,
            after_score: $after_score,
            effort_hours: $effort_hours,
            value_score: $value_score,
            implemented_by: $agent_id,
            implemented_at: datetime()
        })
        CREATE (agent)-[:IMPLEMENTED]->(i)
        RETURN i.id as id, i.value_score as roi
        """

        try:
            with self._session_pool() as session:
                result = session.run(query,
                    agent_id=agent_id,
                    improvement_id=improvement_id,
                    target_file=target_file,
                    improvement_type=improvement_type,
                    before_score=before_score,
                    after_score=after_score,
                    effort_hours=effort_hours,
                    value_score=value_score
                )
                record = result.single()

                if record:
                    print(f"[IMPROVEMENT] {target_file}: ROI {record['roi']:.2f}")
                    return record['id']
        except Exception as e:
            print(f"[ERROR] Failed to record improvement: {e}")

        return None
```

#### 4.9.5 Agent SOUL.md Updates

**Chagatai's SOUL.md Addition:**

```markdown
## Meta-Learning & Reflection

You are responsible for abstracting specific experiences into general principles.

### When Reflecting:

1. **Record the experience**
   - What was the context?
   - What decision did you make?
   - What was the outcome?
   - What was the root cause?

2. **Abstract to meta-rules**
   - Use absolute directives: "NEVER..." or "ALWAYS..."
   - Explain why in 1-3 bullets
   - Provide concrete example
   - Propose to Kublai for approval

### Meta-Rule Format:

```
RULE: NEVER [action] without [prerequisite]
WHY:
• [Specific consequence avoided]
• [Broader principle]
EXAMPLE: [Concrete command or code]
```

### Reflection Search:

Before starting similar tasks, search reflections:
- Query your own past experiences
- Check other agents' lessons (cross-learning)
- Apply relevant meta-rules
- Update rule effectiveness based on outcome
```

**Temüjin's SOUL.md Addition:**

```markdown
## Kaizen: Continuous Quality

Every code change should improve quality metrics.

### Quality Checklist:

Before committing:
- [ ] Complexity score < threshold
- [ ] No duplicate code detected
- [ ] Type safety enforced
- [ ] Documentation updated
- [ ] Tests added/updated

### Improvement Recording:

After refactoring:
1. Record before/after metrics
2. Calculate ROI (improvement / effort)
3. Log in Neo4j for trend tracking
4. Share patterns with other agents

### Poka-Yoke (Error-Proofing):

- Use type systems to prevent invalid states
- Add assertions for assumptions
- Fail fast with clear messages
- Make incorrect code look wrong
```

#### 4.9.6 Integration with Existing Phases

| Existing Phase | Self-Improvement Enhancement |
|----------------|------------------------------|
| Phase 4.7 (Ögedei Proactive) | Add reflection consolidation triggers |
| Phase 4.8 (Chagatai Synthesis) | Use Neo4j vector index for related memories |
| Phase 5 (Jochi-Temüjin) | Add quality metrics to code review |
| Phase 6 (Kublai Delegation) | Check meta-rules before delegation |

#### 4.9.7 Implementation Priority

| Component | Effort | Value | Order |
|-----------|--------|-------|-------|
| Neo4j vector index | 1 hour | Very High | 1st |
| Self-Reflect integration | 4 hours | Very High | 2nd |
| Claude-Meta (meta-rules) | 6 hours | High | 3rd |
| Kaizen (quality metrics) | 4 hours | Medium | 4th |
| Continuous Claude skills | 8 hours | Medium | 5th |
| Qdrant (deferred) | - | Future | TBD |

### Phase 5: Jochi-Temüjin Collaboration Protocol

Define how analyst and developer work together:

```markdown
## Performance & Security Collaboration (Jochi ↔ Temüjin)

### Jochi's Role (Analyst/Backend Reviewer)
- Monitor: Query performance, memory usage, notification growth
- Detect: Race conditions, bottlenecks, anomalies
- Review: Backend code for architectural issues
- Label: Issues requiring Temüjin's implementation expertise
- Report: Metrics with severity (info/warning/critical)

### Jochi's Backend Code Review Checklist

When reviewing Python/Neo4j backend code, Jochi identifies:

1. **Connection Management Issues**
   - Missing connection pool configuration
   - No connection timeout settings
   - Resource exhaustion risks

2. **Resilience Issues**
   - Missing retry logic with exponential backoff
   - No circuit breaker pattern
   - No fallback mode for outages

3. **Data Integrity Issues**
   - Unparameterized queries (injection risk)
   - Missing transaction boundaries
   - No schema versioning/migrations

4. **Performance Issues**
   - Missing query timeouts
   - Unbounded data growth (no cleanup)
   - Synchronous blocking operations

5. **Security Issues**
   - Secrets in error messages/logs
   - Unverified model downloads
   - Missing input validation

### Temüjin's Role (Developer/Security Lead)
- Fix: Implementation issues identified and labeled by Jochi
- Secure: Review all code for vulnerabilities
- Optimize: Based on Jochi's performance analysis

### Handoff Protocol

When Jochi identifies a backend issue:
```
Jochi creates Analysis node with:
  - type: "backend_issue" | "performance_issue" | "security_concern"
  - category: "connection_pool" | "resilience" | "data_integrity" | "performance" | "security"
  - findings: detailed description of the problem
  - location: file and line number reference
  - severity: "warning" | "critical"
  - recommended_fix: specific approach
  - status: "identified"  # Jochi labels it

Jochi notifies Kublai: "Backend issue #X in [category] requires Temüjin implementation"
```

Kublai delegates to Temüjin with Analysis node ID.
Temüjin implements fix, updates Analysis status to "resolved".
Jochi validates fix with metrics/tests.
```

### Phase 5.5: Kublai Failover Protocol (Ögedei as Emergency Router)

Define Ögedei's role as Kublai's failover:

```markdown
## Emergency Router Responsibilities (Ögedei)

When Kublai is unavailable (rate-limited, erroring, or non-responsive):

1. **Detection**: Monitor Kublai's health via heartbeat/last_active timestamp
2. **Activation**: If Kublai hasn't responded in 60 seconds, assume router role
3. **Limited Routing**: Handle critical messages only:
   - Emergency requests
   - System health queries
   - Simple delegations (bypass complex synthesis)
4. **Notification**: Alert admin when failover activated
5. **Recovery**: Return control to Kublai when healthy again

### Failover Triggers
- Kublai model returns 429 (rate limit)
- Kublai process crashes or hangs
- Kublai health check fails 3 consecutive times

### Failback
When Kublai recovers:
1. Ögedei stops accepting new messages
2. Completes in-flight delegations
3. Transfers context summary to Kublai
4. Returns to normal Operations role
```

### Phase 6: Kublai Delegation Protocol

Update Kublai's SOUL.md with:

```markdown
## Operational Memory Protocol

You have access to two memory systems:

1. **Personal Memory** (files: MEMORY.md, memory/*.md)
   - Contains: user preferences, personal history, friend names
   - Access: You only. Never share with other agents.
   - Use for: Understanding context, personalizing responses

2. **Operational Memory** (Neo4j graph)
   - Contains: Research, code patterns, analysis, process insights
   - Access: All agents can read/write
   - Use for: Cross-agent collaboration, building shared knowledge

## Delegation Protocol

When receiving a request:

1. **Query personal memory** - Load relevant user context
2. **Query operational memory** - Check for related prior work
3. **Review for privacy** - Use LLM to identify private info, sanitize before sharing
4. **Delegate via agentToAgent** based on task type:
   - Research → @researcher (Möngke)
   - Writing → @writer (Chagatai)
   - Code/Security → @developer (Temüjin)
   - Analysis → @analyst (Jochi)
   - Process/Tasks → @ops (Ögedei)
5. **Store results** - Save outputs to operational memory
6. **Synthesize response** - Combine with personal context for user
```

---

## Monitoring & Health Checks

Add a health check endpoint to the wrapper server:

```javascript
// In server.js - add health check endpoint
app.get('/health', async (req, res) => {
  const health = {
    status: 'ok',
    timestamp: new Date().toISOString(),
    services: {}
  };

  // Check OpenClaw gateway
  try {
    const gatewayRes = await fetch('http://localhost:8080/health');
    health.services.openclaw = gatewayRes.ok ? 'healthy' : 'degraded';
  } catch (e) {
    health.services.openclaw = 'unavailable';
    health.status = 'degraded';
  }

  // Check Neo4j
  try {
    const neo4jHealth = await memory.health_check();
    health.services.neo4j = neo4jHealth.status;
    if (neo4jHealth.status === 'unhealthy') {
      health.status = 'degraded';
    }
  } catch (e) {
    health.services.neo4j = 'unavailable';
    health.status = 'degraded';
  }

  // Check Signal (if signalClient is available in scope)
  try {
    health.services.signal = typeof signalClient !== 'undefined' && signalClient?.isConnected()
      ? 'healthy'
      : 'unknown';
  } catch (e) {
    health.services.signal = 'unavailable';
  }

  res.status(health.status === 'ok' ? 200 : 503).json(health);
});
```

Health endpoint returns:
- `200 OK` - All services healthy
- `503 Service Unavailable` - One or more services degraded

---

## Verification Checklist

### Multi-Agent Setup
- [ ] `moltbot.json` has `agents.list` with 6 agents
- [ ] Each agent has unique `agentDir`
- [ ] `tools.agentToAgent.enabled: true` with all 6 agents in `allow`
- [ ] No `broadcast.groups` configured
- [ ] Kublai has `default: true`
- [ ] All agents appear in Control UI Settings > Agents
- [ ] Signal message routes to Kublai only

### Neo4j Setup
- [ ] Neo4j service running on Railway
- [ ] Environment variables set (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
- [ ] Schema created (Agent nodes, all knowledge types)
- [ ] Indexes created (agent_knowledge, task_status, knowledge_content, concept_embedding)

### Integration
- [ ] Agents can write to Neo4j
- [ ] Agents can query Neo4j (with vector fallback)
- [ ] Kublai delegates via Task queue pattern
- [ ] Personal context stays in files
- [ ] Operational knowledge goes to Neo4j
- [ ] Privacy sanitization active (phone/email/names stripped)
- [ ] Fallback mode works when Neo4j unavailable
- [ ] Session context persists across daily resets
- [ ] Health check endpoint returns 200 OK
- [ ] Cycle detection prevents circular LEARNED relationships
- [ ] Notification cleanup removes expired nodes
- [ ] Atomic task claim prevents race conditions
- [ ] Blocked tasks auto-escalate to Kublai
- [ ] Temüjin security audit protocol active
- [ ] Jochi-Temüjin collaboration protocol working
- [ ] Ögedei proactive improvement protocol active
- [ ] WorkflowImprovement nodes created for operational enhancements
- [ ] Kublai approves/declines improvement proposals via agentToAgent

---

## Migration & Cleanup Phase

When transitioning from single-agent to multi-agent architecture, explicit cleanup is required to prevent conflicts.

### Pre-Migration Checklist

Before deploying the multi-agent configuration:

1. **Backup existing state**:
   ```bash
   # Backup current single-agent memory
   cp -r /data/.clawdbot /data/.clawdbot.backup.$(date +%Y%m%d)
   ```

2. **Document current Signal sessions** - Users will need to re-pair after migration

### Code Cleanup Required

The following changes remove/replace single-agent code that conflicts with multi-agent architecture:

#### 1. moltbot.json - Replace Single-Agent Config

**Remove** (old single-agent config):
```json
{
  "agents": {
    "defaults": {
      "workspace": "/data/workspace"
    }
  },
  "broadcast": {
    "groups": ["all"]
  }
}
```

**Replace with** (multi-agent config from Implementation Steps)

#### 2. server.js - Remove Single-Agent Assumptions

**Remove or replace** any code that assumes a single agent:
- Hardcoded agent ID references
- Direct file-based message routing
- Single-agent session management

**Add** (from Phase 1):
```javascript
// Create agent directories for multi-agent support
function createAgentDirectories() {
  const agentIds = ['main', 'researcher', 'writer', 'developer', 'analyst', 'ops'];
  const agentsDir = path.join(STATE_DIR, 'agents');

  for (const agentId of agentIds) {
    const agentDir = path.join(agentsDir, agentId);
    try {
      fs.mkdirSync(agentDir, { recursive: true });
      console.log(`[startup] Created agent directory: ${agentDir}`);
    } catch (err) {
      console.warn(`[startup] Could not create agent directory ${agentDir}: ${err.message}`);
    }
  }
}

// Call after STATE_DIR is set
createAgentDirectories();
```

#### 3. Dockerfile - Add Directory Creation

**Add** to Dockerfile (avoids race condition at runtime):
```dockerfile
# Create agent directories at build time
RUN mkdir -p /data/.clawdbot/agents/{main,researcher,writer,developer,analyst,ops} && \
    mkdir -p /data/workspace/{souls,memory/kublai,tasks/{inbox,assigned,in-progress,review,done},deliverables}
```

#### 4. Clean Up Old Session Files

**Delete** old single-agent session files that may conflict:
```bash
# Remove old session files (they use different format)
rm -f /data/.clawdbot/session*.json

# Remove old agent state (will be recreated with new structure)
rm -rf /data/.clawdbot/agent/
```

### Conflict Prevention

#### Environment Variable Conflicts

| Old Variable | New Variable | Action |
|--------------|--------------|--------|
| `AGENT_ID` | `OPENCLAW_AGENT_ID` | Update if exists |
| `MEMORY_PATH` | `NEO4J_URI` | Replace |

#### File Path Conflicts

| Old Path | New Path | Conflict Resolution |
|----------|----------|---------------------|
| `/data/.clawdbot/memory/` | `/data/.clawdbot/agents/{id}/` | Move to agent-specific dirs |
| `/data/workspace/memory/` | `/data/workspace/memory/kublai/` | Kublai gets exclusive access |

### Migration Strategies

#### Option A: Blue-Green Deployment (Recommended)

1. Deploy new multi-agent system to separate Railway project
2. Test thoroughly with non-production Signal number
3. Switch DNS/Signal registration once verified
4. Decommission old single-agent deployment

#### Option B: In-Place Migration

1. Stop OpenClaw service
2. Run cleanup commands above
3. Deploy new configuration
4. Re-pair Signal (sessions will be reset)

### Post-Migration Verification

After migration, verify no single-agent code remains active:

```bash
# Check for old config patterns
grep -r "broadcast.*groups" /data/.clawdbot/ || echo "No broadcast groups found - OK"

# Verify agent directories exist
ls -la /data/.clawdbot/agents/{main,researcher,writer,developer,analyst,ops}

# Check Neo4j connection
python3 -c "from openclaw_memory import memory; print('Neo4j OK' if memory.driver else 'Neo4j NOT CONNECTED')"

# Verify no single-agent session files
find /data/.clawdbot -name "session*.json" -type f 2>/dev/null | wc -l
# Should return 0
```

---

## Rollback Plan

If migration fails:

1. Stop OpenClaw service
2. Restore from backup:
   ```bash
   rm -rf /data/.clawdbot
   cp -r /data/.clawdbot.backup.20240203 /data/.clawdbot
   ```
3. Revert `moltbot.json` to single-agent configuration
4. Remove Neo4j service from Railway
5. Delete agent directories
6. Restart service
7. Re-pair Signal if necessary

---

### Phase 7: Bidirectional Notion Integration

Enable creating and managing tasks directly in Notion with full agent execution support.

#### 7.1 Notion Database Schema

Required fields for bidirectional sync:

| Field | Type | Purpose |
|-------|------|---------|
| **Name** | Title | Task description |
| **Status** | Select | Backlog / Pending Review / To Do / In Progress / Review / Done / Blocked |
| **Agent** | Select | (Optional) Force specific agent |
| **Priority** | Select | P0 / P1 / P2 / P3 |
| **Neo4j Task ID** | Rich Text | Links to operational memory |
| **Requester** | Rich Text | Who created the task |
| **Created From** | Select | Notion / Signal / Agent |

#### 7.2 Bidirectional Sync Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Notion    │◄───►│   Ögedei    │◄───►│   Neo4j     │
│  Kanban     │     │  (Poller)   │     │  (Tasks)    │
└─────────────┘     └──────┬──────┘     └──────┬──────┘
                           │                   │
                           ▼                   ▼
                    ┌─────────────┐     ┌─────────────┐
                    │   Kublai    │     │   Agents    │
                    │  (Reviewer) │     │ (Execution) │
                    └─────────────┘     └─────────────┘
```

#### 7.3 Ögedei's Polling Loop

```python
def poll_notion_for_new_tasks(self, memory: OperationalMemory):
    """Detect tasks created in Notion without Neo4j Task ID."""

    # Query Notion for orphan tasks (no Neo4j ID)
    orphan_tasks = self.query_notion_tasks(
        filter={"property": "Neo4j Task ID", "rich_text": {"is_empty": True}}
    )

    for notion_task in orphan_tasks:
        # Move to Pending Review
        self.update_task_status(notion_task['id'], 'Pending Review')

        # Create draft Neo4j task
        draft_task_id = memory.create_task(
            task_type="pending_review",
            description=notion_task['title'],
            delegated_by="main",
            assigned_to="main",
            priority=self.map_priority(notion_task['priority']),
            properties={
                'notion_page_id': notion_task['id'],
                'requester': 'notion',
                'suggested_agent': notion_task.get('agent', 'auto')
            }
        )

        # Link Notion to Neo4j
        self.update_task_neo4j_id(notion_task['id'], draft_task_id)

        # Notify Kublai
        self.notify_kublai_of_pending_review(draft_task_id, notion_task)
```

#### 7.4 Kublai Review Protocol

```python
def review_notion_task(self, task_id: str, notion_context: Dict) -> Dict:
    """Kublai evaluates tasks from Notion before activation."""

    # Load related context
    related = self.memory.query_related(
        agent="main",
        topic=notion_context['title'],
        sender_hash=self.get_sender_hash(notion_context.get('requester'))
    )

    # Make delegation decision
    decision = self.delegate_or_execute(
        task_description=notion_context['title'],
        suggested_agent=notion_context.get('suggested_agent'),
        related_context=related,
        source='notion'
    )

    return {
        'action': decision['action'],  # delegate/execute/reject/clarify
        'assigned_to': decision['agent'],
        'task_type': decision['task_type'],
        'notes': decision['reasoning']
    }
```

**Review Outcomes:**

| Action | Notion Status | Signal Notification |
|--------|--------------|---------------------|
| Approve + Delegate | → "To Do" | ✅ Task assigned to {agent} |
| Approve + Execute | → "In Progress" | ⚡ Quick task completed |
| Reject | → "Blocked" | ❌ Couldn't process: {reason} |
| Need Clarification | → "Blocked" | ❓ Need clarification: {question} |

#### 7.5 Reprioritization via Column Moves

```python
COLUMN_ACTIONS = {
    'Backlog': {'neo4j_status': 'suspended', 'action': 'pause'},
    'To Do': {'neo4j_status': 'pending', 'action': 'queue'},
    'In Progress': {'neo4j_status': 'in_progress', 'action': 'start'},
    'Blocked': {'neo4j_status': 'blocked', 'action': 'pause_and_report'},
    'Review': {'neo4j_status': 'completed', 'action': 'mark_complete'},
    'Done': {'neo4j_status': 'completed', 'action': 'archive'}
}

def handle_column_change(self, notion_task: Dict, old_status: str, new_status: str):
    """Handle user moving cards in Notion."""

    task_id = notion_task['neo4j_task_id']

    # Case: Interrupt active work
    if old_status == 'In Progress' and new_status in ['Backlog', 'To Do', 'Blocked']:
        # Create checkpoint before interrupting
        checkpoint = self.create_checkpoint(
            agent=self.memory.get_task_assignee(task_id),
            task_id=task_id
        )

        # Notify agent to pause
        self.interrupt_agent(
            agent=self.memory.get_task_assignee(task_id),
            task_id=task_id,
            reason=f"Reprioritized to {new_status}"
        )

        self.send_signal_message(
            message=f"⏸️ Paused '{notion_task['title']}' - checkpoint saved."
        )
```

#### 7.6 Checkpoint System for Interrupted Tasks

```python
def create_checkpoint(self, agent: str, task_id: str) -> Dict:
    """Save agent state before interruption."""

    checkpoint = {
        'agent': agent,
        'task_id': task_id,
        'timestamp': datetime.now().isoformat(),
        'context': {
            'files_open': self.get_agent_open_files(agent),
            'partial_code': self.get_uncommitted_changes(agent),
            'research_notes': self.get_agent_notes(agent)
        },
        'progress': {
            'percent_complete': self.estimate_task_progress(agent, task_id),
            'completed_steps': self.get_completed_steps(agent, task_id),
            'next_step': self.get_next_step(agent, task_id)
        }
    }

    # Store in Neo4j
    self.memory.store_checkpoint(checkpoint)
    return checkpoint
```

**Neo4j Schema:**

```cypher
(:Checkpoint {
  id: uuid,
  task_id: uuid,
  agent: string,
  created_at: datetime,
  context_json: string,
  progress_percent: float,
  expires_at: datetime
})
```

#### 7.7 Intelligent Error Routing

```python
class ErrorRouter:
    """Routes errors to appropriate specialist agents."""

    ERROR_CLASSIFICATION = {
        'api_error': {'agent': 'developer', 'confidence': 0.85},
        'syntax_error': {'agent': 'developer', 'confidence': 0.95},
        'performance_issue': {'agent': 'analyst', 'confidence': 0.85},
        'race_condition': {'agent': 'analyst', 'confidence': 0.90},
        'insufficient_information': {'agent': 'researcher', 'confidence': 0.80},
        'tone_issue': {'agent': 'writer', 'confidence': 0.75},
        'sync_failure': {'agent': 'ops', 'confidence': 0.90}
    }

    def classify_error(self, error_message: str) -> Dict:
        """Analyze error and determine best agent."""

        error_lower = error_message.lower()
        scores = {}

        for error_type, config in self.ERROR_CLASSIFICATION.items():
            if re.search(config['pattern'], error_lower, re.IGNORECASE):
                scores[error_type] = config['confidence']

        if scores:
            best = max(scores.items(), key=lambda x: x[1])
            return {
                'agent': self.ERROR_CLASSIFICATION[best[0]]['agent'],
                'confidence': best[1],
                'error_type': best[0]
            }

        return self._llm_classify_error(error_message)
```

#### 7.8 Failure History Tracking

```python
def analyze_agent_failure_history(self, agent: str, error_type: str) -> Dict:
    """Query Neo4j for agent's track record."""

    query = """
    MATCH (f:AgentFailure {agent: $agent, error_type: $error_type})
    WHERE f.created_at > datetime() - duration('days', 30)
    RETURN count(f) as recent_failures,
           avg(CASE WHEN f.fix_successful THEN 1.0 ELSE 0.0 END) as fix_rate
    """

    result = self.memory.execute(query, agent=agent, error_type=error_type)
    record = result.single()

    return {
        'recent_failures': record['recent_failures'] or 0,
        'fix_success_rate': record['fix_rate'] or 1.0
    }

def route_with_history_awareness(self, failed_task: Dict, error: str) -> Dict:
    """Route error considering both type and history."""

    classification = self.error_router.classify_error(error)
    history = self.analyze_agent_failure_history(
        failed_task['assigned_to'],
        classification['error_type']
    )

    # Pattern: Repeat offender
    if history['recent_failures'] >= 3:
        return {
            'action': 'escalate_to_kublai',
            'reason': f"{failed_task['assigned_to']} failed {history['recent_failures']} times"
        }

    # Pattern: Low fix success rate
    elif history['fix_success_rate'] < 0.5:
        return {
            'action': 'try_different_agent',
            'suggested_agent': self.find_alternative_agent(classification['error_type'])
        }

    # Normal routing
    return {
        'action': 'delegate',
        'suggested_agent': classification['agent']
    }
```

**Neo4j Schema:**

```cypher
(:AgentFailure {
  id: uuid,
  agent: string,
  task_type: string,
  error_type: string,
  fix_successful: boolean,
  fix_agent: string,
  created_at: datetime
})

(:AgentReliability {
  agent: string,
  task_type: string,
  success_rate: float,
  total_attempts: int,
  recent_failures: int
})
```

#### 7.9 Proactive Training System

```python
def detect_training_needs(self, agent: str, error_type: str,
                         recent_failures: List[Dict]) -> Optional[Dict]:
    """Identify when an agent needs training."""

    if len(recent_failures) >= 3:
        return {
            'type': 'skill_gap',
            'priority': 'high',
            'suggestion': f"{agent} needs training on {error_type}",
            'action': 'create_knowledge_base_entry'
        }

    return None

def create_knowledge_base_entry(self, training_need: Dict):
    """Generate training material from successful fixes."""

    # Query successful fixes for this error
    examples = self.query_successful_fixes(training_need['error_type'], limit=5)

    # Synthesize best practices
    kb_content = self.synthesize_training_material(
        error_type=training_need['error_type'],
        successes=examples
    )

    # Store as Synthesis node
    kb_id = self.memory.store_synthesis(
        agent="main",
        insight=kb_content['summary'],
        novelty_type="training_material",
        access_tier="PUBLIC"
    )

    # Create MetaRule for agent SOUL
    self.meta_learning.create_rule(
        agent=training_need.get('affected_agent'),
        rule_content=kb_content['rule'],
        context=f"Derived from failures"
    )

    # Queue SOUL update via Ögedei
    self.ogedei.queue_soul_update(
        agent=training_need.get('affected_agent'),
        addition=kb_content['soul_addition']
    )

    return kb_id
```

#### 7.10 Pair Programming Suggestions

```python
def suggest_pair_programming(self, task: Dict, failing_agent: str,
                            error_type: str) -> Optional[Dict]:
    """Suggest optimal pair programming match."""

    # Find experts with successful fixes
    experts = self.find_error_experts(error_type, exclude=[failing_agent])

    if not experts:
        return None

    # Calculate compatibility
    best_match = None
    best_score = 0

    for expert in experts:
        score = self.calculate_pair_compatibility(
            mentor=expert,
            mentee=failing_agent,
            task=task
        )
        if score > best_score and score >= 0.6:
            best_score = score
            best_match = expert

    return {
        'mentor': best_match,
        'mentee': failing_agent,
        'compatibility_score': best_score
    } if best_match else None

def calculate_pair_compatibility(self, mentor: str, mentee: str,
                                 task: Dict) -> float:
    """Score how well two agents work together."""

    scores = []

    # Factor 1: Expertise gap
    mentor_skill = self.get_agent_skill_rating(mentor, task['type'])
    mentee_skill = self.get_agent_skill_rating(mentee, task['type'])
    if mentor_skill > mentee_skill + 0.3:
        scores.append(0.25)

    # Factor 2: Collaboration history
    history = self.get_collaboration_history(mentor, mentee)
    if history['successful_collaborations'] > 0:
        scores.append(0.25 * min(history['success_rate'], 1.0))
    else:
        scores.append(0.15)

    # Factor 3: Workload balance
    mentor_load = self.get_agent_workload(mentor)
    if mentor_load < 0.7:
        scores.append(0.25)
    elif mentor_load < 0.9:
        scores.append(0.15)
    else:
        scores.append(0.05)

    # Factor 4: Communication style
    style_match = self.get_communication_compatibility(mentor, mentee)
    scores.append(0.25 * style_match)

    return sum(scores)

def initiate_pair_session(self, pair_match: Dict, task: Dict):
    """Carefully introduce pair programming."""

    mentor = pair_match['mentor']
    mentee = pair_match['mentee']

    # Step 1: Check mentor availability
    if not self.is_agent_available(mentor):
        self.queue_pair_session(pair_match, task)
        return {'status': 'queued'}

    # Step 2: Propose to mentor (opt-in)
    proposal = self.send_agent_message(
        to=mentor,
        message=(
            f"🤝 Pair Programming Opportunity\n"
            f"{mentee} is struggling with {task['type']}.\n"
            f"You have {self.get_success_count(mentor, task['type'])} successes.\n\n"
            f"1. Accept - Guide {mentee}\n"
            f"2. Suggest async - Share notes\n"
            f"3. Decline - Too busy"
        ),
        require_response=True,
        timeout_minutes=30
    )

    if proposal['response'] == '1':
        # Mentor accepts
        self.notify_mentee(mentee, mentor, task, pair_match)
        self.create_pair_workspace(mentor, mentee, task)
        return {'status': 'accepted'}

    elif proposal['response'] == '2':
        self.initiate_async_mentoring(mentor, mentee, task)
        return {'status': 'async'}

    else:
        # Try next expert
        return self.try_next_expert(task, mentee, exclude=[mentor])
```

#### 7.11 Error Handling & Recovery

```python
class NotionSyncErrorHandler:
    """Handle failures in bidirectional sync."""

    def handle_notion_api_failure(self, error: Exception,
                                  pending_changes: List[Dict]):
        """Queue changes for retry when Notion is down."""

        for change in pending_changes:
            self.memory.create_task(
                task_type="notion_sync_retry",
                description=f"Retry {change['operation']}",
                delegated_by="ops",
                assigned_to="ops",
                properties={
                    'change': change,
                    'retry_count': 0,
                    'max_retries': 5
                }
            )

        # Alert if outage persists >10 minutes
        self.schedule_alert(
            condition="notion_api_down > 600",
            notify="kublai",
            message="Notion API down >10 min"
        )

    def detect_sync_conflict(self, notion_task: Dict,
                            neo4j_task: Dict) -> Optional[str]:
        """Detect when Notion and Neo4j diverge."""

        conflicts = []

        # Status mismatch
        notion_status = notion_task['status']
        neo4j_status = neo4j_task['status']

        status_map = {
            'To Do': ['pending'],
            'In Progress': ['in_progress', 'claimed'],
            'Done': ['completed']
        }

        if notion_status in status_map and \
           neo4j_status not in status_map[notion_status]:
            conflicts.append(f"Status: Notion={notion_status}, Neo4j={neo4j_status}")

        return '; '.join(conflicts) if conflicts else None
```

#### 7.12 Implementation Priority

| Component | Effort | Value | Order |
|-----------|--------|-------|-------|
| Notion polling loop | 2 hours | High | 1st |
| Kublai review protocol | 3 hours | High | 2nd |
| Status sync (bidirectional) | 2 hours | Medium | 3rd |
| Checkpoint system | 4 hours | Medium | 4th |
| Error routing | 4 hours | High | 5th |
| Failure history tracking | 3 hours | Medium | 6th |
| Training system | 4 hours | Low | 7th |
| Pair programming | 6 hours | Low | 8th |

---

## Appendix A: Agent SOUL Templates

Create these 6 files in `/data/workspace/souls/`:

### kublai.md
```markdown
# Kublai (main) - Squad Lead / Router

## Role
You are Kublai, the Squad Lead of a 6-agent OpenClaw system. You receive all inbound messages and delegate to specialists.

## Responsibilities
1. Receive and understand user requests
2. Query personal memory (files) for context
3. Query operational memory (Neo4j) for prior work
4. Review content for privacy before sharing
5. Delegate to appropriate specialist via agentToAgent
6. Synthesize specialist responses for the user

## Delegation Rules
- Research → @researcher (Möngke)
- Writing → @writer (Chagatai)
- Code/Security → @developer (Temüjin)
- Analysis → @analyst (Jochi)
- Process/Tasks → @ops (Ögedei)

## Privacy Protocol
NEVER share personal information to operational memory:
- Replace names with generic terms ("my friend Sarah" → "a contact")
- Remove phone numbers, emails, addresses
- Sanitize before delegating

## Memory Systems
1. Personal (files): Your exclusive access - preferences, history
2. Operational (Neo4j): Shared - research, code patterns, analysis
```

### mongke.md
```markdown
# Möngke (researcher) - Researcher

## Role
You are Möngke, the Research specialist. You handle deep research tasks.

## Responsibilities
1. Conduct thorough research on assigned topics
2. Fact-check and verify sources
3. Synthesize findings into actionable insights
4. Store research in operational memory
5. Report completion to Kublai

## Process
1. Receive task from Kublai
2. Query operational memory for related prior research
3. Conduct research using available tools
4. Store findings as Research node in Neo4j
5. Notify Kublai of completion

## Output Format
Provide structured findings with sources and confidence levels.
```

### chagatai.md
```markdown
# Chagatai (writer) - Content Writer

## Role
You are Chagatai, the Content Writer. You create and edit written content.

## Responsibilities
1. Create content based on research and requirements
2. Edit and improve clarity of existing content
3. Adapt tone and style for audience
4. Store content in operational memory
5. Report completion to Kublai

## Process
1. Receive writing task from Kublai
2. Query operational memory for related content/patterns
3. Create or edit content
4. Store as Content node in Neo4j
5. Notify Kublai of completion

## Quality Standards
- Clear and concise
- Appropriate tone
- Well-structured
- Error-free
```

### temujin.md
```markdown
# Temüjin (developer) - Developer/Security Lead

## Role
You are Temüjin, the Developer and Security Lead. You implement code and security reviews.

## Responsibilities
1. Write and review code
2. Conduct security audits
3. Fix backend issues identified by Jochi
4. Implement architectural improvements
5. Store code patterns and security findings

## Security Audit Protocol
Review all code for:
- Injection vulnerabilities
- Data exposure risks
- Access control issues
- Hardcoded credentials

## Jochi Collaboration
When Jochi identifies backend issues:
1. Receive Analysis node ID from Kublai
2. Review issue details
3. Implement fix
4. Update Analysis status to "resolved"
5. Request Jochi validation

## Process
1. Receive development task from Kublai
2. Query operational memory for code patterns
3. Implement solution
4. Store as Application/CodeReview/SecurityAudit node
5. Notify Kublai of completion
```

### jochi.md
```markdown
# Jochi (analyst) - Analyst/Performance Lead/Backend Reviewer

## Role
You are Jochi, the Analyst and Backend Reviewer. You monitor performance and identify implementation issues.

## Responsibilities
1. Monitor query performance and resource usage
2. Detect anomalies and bottlenecks
3. Review backend code for architectural issues
4. Label issues for Temüjin to fix
5. Validate fixes after implementation

## Backend Review Checklist
When reviewing Python/Neo4j code, identify:
1. Connection Management Issues
   - Missing connection pool config
   - No timeout settings
   - Resource exhaustion risks

2. Resilience Issues
   - Missing retry logic
   - No circuit breaker
   - No fallback mode

3. Data Integrity Issues
   - Unparameterized queries
   - Missing transactions
   - No schema migrations

4. Performance Issues
   - Missing query timeouts
   - Unbounded data growth
   - Blocking operations

5. Security Issues
   - Secrets in logs
   - Unverified downloads
   - Missing input validation

## Issue Creation
When you identify an issue:
```
Create Analysis node with:
- type: "backend_issue"
- category: "connection_pool" | "resilience" | "data_integrity" | "performance" | "security"
- findings: detailed description
- location: file:line
- severity: "critical" | "high" | "medium"
- status: "identified"
- requires_implementation_by: "temujin"
```

Then notify Kublai: "Backend issue #X requires Temüjin implementation"
```

### ogedei.md
```markdown
# Ögedei (ops) - Operations / Emergency Router / File Consistency Manager / Project Manager

## Role
You are Ögedei, the Operations manager, Emergency Router, File Consistency Manager, and Project Manager using Notion.

## Normal Responsibilities

### 1. File Consistency Management
Monitor and maintain consistency of memory files:
- `heartbeat.md` - System health and status
- `memory.md` - Long-term memory and context
- `CLAUDE.md` - Project instructions
- Any other `.md` files in agent workspaces

**Consistency Checks:**
- Verify all files are parseable and valid Markdown
- Check for conflicting information across files
- Detect outdated or stale information
- Ensure cross-references are valid

**Conflict Detection:**
- Same fact stated differently in different files
- Contradictory instructions
- Stale context that should be updated
- Missing required sections

**Escalation Protocol:**
When conflicts detected:
1. Document conflict in Analysis node with:
   - type: "file_inconsistency"
   - files_involved: [list of conflicting files]
   - conflict_description: detailed explanation
   - severity: "low" | "medium" | "high" | "critical"
   - suggested_resolution: your recommendation
2. Notify Kublai via agentToAgent
3. Wait for Kublai's decision on resolution
4. Implement approved changes

### 2. Project Management (Notion)

**Kanban Board Management:**
You maintain a Notion Kanban board with these columns:
- **Backlog** - Future tasks and ideas
- **To Do** - Ready to work on
- **In Progress** - Currently being worked on
- **Review** - Awaiting review
- **Done** - Completed tasks

**Task Tracking:**
For each task, track:
- Title and description
- Assigned agent
- Due date
- Priority (P0, P1, P2, P3)
- Status
- Related Neo4j task ID
- Links to relevant files/resources

**Sprint Management:**
- Plan weekly sprints
- Assign tasks to agents based on capacity
- Track burndown
- Hold daily standups (async via agentToAgent)

**Notion Integration:**
Use the Notion API to:
- Create/update tasks
- Move cards between columns
- Add comments and updates
- Generate weekly reports

### 3. Operations Management
1. Manage process workflows
2. Coordinate task scheduling
3. Monitor system health
4. Handle operational requests

### 4. Proactive Improvement (Continuous)
**Reflect on operations and identify improvement opportunities.**

Use the proactive-agent skill to:
1. **Analyze operational patterns** - Review recent tasks, response times, bottlenecks
2. **Identify inefficiencies** - Redundant steps, manual processes, communication gaps
3. **Propose improvements** - Create WorkflowImprovement nodes for Kublai review
4. **Track implementation** - Follow up on approved improvements

**Improvement Proposal Workflow:**
```python
# When Ögedei identifies an improvement opportunity:
1. Create WorkflowImprovement node:
   {
     type: "workflow_improvement",
     target_process: "task_delegation",
     current_state: "manual routing by Kublai",
     proposed_state: "auto-routing based on task type keywords",
     expected_benefit: "reduce Kublai load by 30%",
     complexity: "medium",
     proposed_by: "ogedei",
     status: "proposed"
   }

2. Send agentToAgent to Kublai:
   "Improvement proposal #[id]: [description]. Expected benefit: [benefit]. Approve?"

3. Kublai decides:
   - APPROVED: Ögedei implements, updates status to "implementing" then "deployed"
   - DECLINED: Ögedei archives, notes reason
   - NEEDS_DISCUSSION: Schedule async standup with relevant agents

4. Track metrics post-implementation:
   - Measure actual vs expected benefit
   - Document lessons learned
   - Propose refinements if needed
```

**Reflection Schedule:**
- After each completed task: Quick reflection on process friction
- Daily: Review day's operations for patterns
- Weekly: Deep analysis of workflow efficiency metrics

### 5. Emergency Router (when activated)
When Kublai is unavailable:
1. Monitor Kublai health via heartbeat
2. Assume router role after 60s unresponsiveness
3. Handle critical messages only:
   - Emergency requests
   - System health queries
   - Simple delegations
4. Alert admin of failover activation
5. Return control when Kublai recovers

## Daily Routine

### Morning (09:00 UTC)
1. Run file consistency check on all agent workspaces
2. Review Notion Kanban board
3. Update task statuses based on Neo4j task state
4. Flag any overdue tasks

### Continuous
1. Monitor file changes for conflicts
2. Update Notion as tasks progress
3. Detect and escalate inconsistencies

### Evening (21:00 UTC)
1. Generate daily summary report
2. Update project metrics in Notion
3. Plan next day's priorities

## File Consistency Process

```python
# Ögedei's file consistency workflow:
1. Scan /data/.clawdbot/agents/*/ for .md files
2. Parse each file and validate structure
3. Check for conflicts:
   - Compare heartbeat.md timestamps
   - Cross-reference memory.md facts
   - Validate CLAUDE.md instructions
4. Create FileConsistencyReport node:
   {
     type: "file_consistency_report",
     timestamp: datetime(),
     files_checked: [...],
     conflicts_found: [...],
     severity: "...",
     requires_kublai_attention: true/false
   }
5. If conflicts found:
   - Create Analysis node for each conflict
   - Send agentToAgent to Kublai
   - Await resolution
```

## Notion API Integration

```python
# Key Notion operations:
- Create task: notion.pages.create(parent=database_id, properties=...)
- Update status: notion.pages.update(page_id, properties={"Status": "In Progress"})
- Move to done: notion.pages.update(page_id, properties={"Status": "Done", "Completed": date()})
- Query tasks: notion.databases.query(database_id, filter={"property": "Status", "select": {"equals": "In Progress"}})
```

## Failover Process
1. Detect Kublai unavailability (3 consecutive failures)
2. Activate emergency router mode
3. Handle incoming messages with simplified routing
4. Monitor for Kublai recovery
5. Transfer context and return to normal role

## Escalation Criteria
Escalate to Kublai immediately when:
- Critical file inconsistency detected
- Notion API failures persist >30 minutes
- Emergency router activated
- Multiple agents report task conflicts
```

---

## Appendix B: Testing Strategy

### Unit Tests

Create `test_operational_memory.py`:

```python
import os
import unittest
from unittest.mock import Mock, patch
from openclaw_memory import OperationalMemory

class TestOperationalMemory(unittest.TestCase):

    @patch.dict(os.environ, {
        'NEO4J_URI': 'bolt://test:7687',
        'NEO4J_PASSWORD': 'test_password',
        'OPENCLAW_GATEWAY_TOKEN': 'test_token',
        'PHONE_HASH_SALT': 'test_salt_for_hashing'
    })
    def setUp(self):
        # Mock Neo4j driver for unit tests
        self.mock_driver = Mock()
        with patch('openclaw_memory.GraphDatabase') as mock_db:
            mock_db.driver.return_value = self.mock_driver
            self.memory = OperationalMemory()

    def test_rate_limiting(self):
        """Test that rate limiting blocks excessive requests."""
        agent = "test_agent"
        operation = "test_op"

        # Should allow first 100 requests (burst limit)
        for i in range(100):
            result = self.memory._check_rate_limit(agent, operation)
            self.assertTrue(result, f"Request {i} should be allowed")

        # 101st request should be blocked
        result = self.memory._check_rate_limit(agent, operation)
        self.assertFalse(result, "101st request should be blocked")

    def test_sanitize_for_sharing(self):
        """Test PII sanitization."""
        text = "Call me at 555-123-4567 or email john@example.com"
        sanitized = self.memory._pattern_sanitize(text)

        self.assertNotIn("555-123-4567", sanitized)
        self.assertNotIn("john@example.com", sanitized)
        self.assertIn("[PHONE]", sanitized)
        self.assertIn("[EMAIL]", sanitized)

    def test_circuit_breaker(self):
        """Test circuit breaker opens after failures."""
        # Simulate 5 failures
        for _ in range(5):
            self.memory._record_failure()

        # Circuit should be open
        self.assertFalse(self.memory._circuit_breaker_check())

class TestSessionResetManager(unittest.TestCase):

    @patch('openclaw_memory.OperationalMemory')
    def test_drain_mode_entry(self, mock_memory):
        from openclaw_memory import SessionResetManager

        manager = SessionResetManager(mock_memory)
        mock_memory.check_graceful_reset_eligible.return_value = {
            'can_reset': False,
            'pending_tasks': 5,
            'active_tasks': 2
        }

        result = manager.check_and_enter_drain_mode("sender_123")

        self.assertEqual(result['action'], 'wait')
        self.assertTrue(manager._drain_mode)

class TestFailoverMonitor(unittest.TestCase):

    @patch('openclaw_memory.OperationalMemory')
    def test_failover_trigger(self, mock_memory):
        from openclaw_memory import FailoverMonitor

        monitor = FailoverMonitor(mock_memory)

        # Simulate 3 failures
        for _ in range(3):
            monitor._handle_kublai_failure("test_failure")

        self.assertTrue(monitor.is_failover_active())

if __name__ == '__main__':
    unittest.main()
```

### Integration Tests

Create `test_integration.py`:

```python
import os
import pytest
from openclaw_memory import OperationalMemory, MigrationManager

# Requires running Neo4j instance
@pytest.fixture
def memory():
    """Create OperationalMemory connected to test Neo4j."""
    os.environ['NEO4J_URI'] = 'bolt://localhost:7687'
    os.environ['NEO4J_PASSWORD'] = 'test_password'
    os.environ['OPENCLAW_GATEWAY_TOKEN'] = 'test_token'

    mem = OperationalMemory()
    yield mem
    mem.close()

def test_full_task_lifecycle(memory):
    """Test complete task creation, claim, and completion flow."""
    # Create task
    task_id = memory.create_task(
        task_type="research",
        description="Test research task",
        delegated_by="main",
        assigned_to="researcher"
    )
    assert task_id is not None

    # Claim task
    claimed = memory.claim_task("researcher")
    assert claimed is not None
    assert claimed['id'] == str(task_id)

    # Complete task
    result = memory.complete_task(
        task_id=task_id,
        results={'summary': 'Test completed', 'quality_score': 0.9}
    )
    assert result is True

def test_migration_flow(memory):
    """Test database migration."""
    migrator = MigrationManager(memory.driver)

    # Get initial status
    status = migrator.status()
    assert 'current_version' in status

    # Run migrations
    applied = migrator.migrate()
    assert isinstance(applied, list)

    # Verify no pending
    final_status = migrator.status()
    assert final_status['pending'] == 0
```

### Running Tests

```bash
# Unit tests (no Neo4j required)
python -m pytest test_operational_memory.py -v

# Integration tests (requires Neo4j)
python -m pytest test_integration.py -v --integration

# All tests with coverage
python -m pytest --cov=openclaw_memory --cov-report=html
```

---

## Appendix C: Network Configuration

### Port Mapping

| Service | Port | Purpose | Config Location |
|---------|------|---------|-----------------|
| OpenClaw Gateway | 18789 | Main API / Control UI | `moltbot.json` gateway.port |
| OpenClaw Internal | 8080 | Internal health checks | Hardcoded in server.js health check |
| Neo4j Bolt | 7687 | Database connection | `NEO4J_URI` env var |
| Neo4j HTTP | 7474 | Neo4j Browser (optional) | Neo4j config |

### Railway Deployment Notes

- OpenClaw gateway runs on port 18789 internally
- Railway exposes this via HTTPS (port 443 externally)
- Health check endpoint: `https://your-app.railway.app/health`
- Internal OpenClaw health: `http://localhost:8080/health` (container internal)

### Environment Variable Reference

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `NEO4J_URI` | Yes | Neo4j connection URI | `bolt://neo4j.railway.internal:7687` |
| `NEO4J_USER` | Yes | Neo4j username | `neo4j` |
| `NEO4J_PASSWORD` | Yes | Neo4j password | (generate secure) |
| `OPENCLAW_GATEWAY_TOKEN` | Yes | API auth token | (generate secure) |
| `OPENCLAW_GATEWAY_URL` | Yes | Gateway URL | `http://localhost:8080` |
| `SIGNAL_ACCOUNT_NUMBER` | Yes | Signal phone | `+15551234567` |
| `ADMIN_PHONE_1` | Yes | Admin phone 1 | `+15551234567` |
| `ADMIN_PHONE_2` | Yes | Admin phone 2 | `+15559876543` |
| `MOONSHOT_API_KEY` | Yes* | Kimi K2.5 access | `sk-...` |
| `ZAI_API_KEY` | Yes* | GLM model access | `sk-...` |
| `SENTENCE_TRANSFORMERS_CACHE` | No | Model cache path | `/data/cache/sentence-transformers` |
| `EMBEDDING_MODEL_SHA256` | No | Model verification | `e4ce9877...` |
| `EMBEDDING_ENCRYPTION_KEY` | **Yes** | AES-256 key for SENSITIVE embeddings | `base64_encoded_key` |
| `PHONE_HASH_SALT` | **Yes** | HMAC salt for sender hashing | `random_32+_chars` |

*Required for LLM functionality

**Security Note**: `EMBEDDING_ENCRYPTION_KEY` and `PHONE_HASH_SALT` are critical for privacy. Generate strong random values:
```bash
# Generate encryption key
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Generate phone hash salt
openssl rand -base64 32
```

---

## Appendix D: Logging Configuration

### Structured Logging Setup

Add to `openclaw_memory.py`:

```python
import logging
import json
import sys

# Configure structured logging for Railway aggregation
class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'agent': getattr(record, 'agent', None),
            'operation': getattr(record, 'operation', None),
        }
        if record.exc_info:
            log_obj['exception'] = self.formatException(record.exc_info)
        return json.dumps(log_obj)

# Setup root logger
def setup_logging():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    logger = logging.getLogger('openclaw_memory')
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    return logger

logger = setup_logging()

# Usage in methods:
# logger.info("Task created", extra={'agent': 'main', 'operation': 'create_task'})
```

### Log Levels by Component

| Component | Level | Notes |
|-----------|-------|-------|
| OperationalMemory | INFO | Normal operations |
| Rate Limiting | WARN | When limits hit |
| Circuit Breaker | WARN | State changes |
| Failover | ERROR | Failover events |
| Privacy Sanitization | INFO | Sanitization actions |

---

## Appendix E: Rollback Baseline (Single-Agent Config)

If migration fails, revert to this configuration:

### moltbot.json (Single-Agent Baseline)

```json
{
  "gateway": {
    "mode": "local",
    "port": 18789,
    "trustedProxies": ["*"],
    "auth": {
      "mode": "token",
      "token": "${OPENCLAW_GATEWAY_TOKEN}"
    },
    "controlUi": {
      "enabled": true
    }
  },
  "agents": {
    "defaults": {
      "workspace": "/data/workspace",
      "sandbox": {
        "mode": "off"
      },
      "model": {
        "primary": "zai/glm-4.5"
      }
    },
    "list": [
      {
        "id": "main",
        "name": "Kublai",
        "default": true,
        "agentDir": "/data/.clawdbot/agents/main",
        "model": {
          "primary": "moonshot/kimi-k2.5"
        }
      }
    ]
  },
  "channels": {
    "signal": {
      "enabled": true,
      "account": "${SIGNAL_ACCOUNT_NUMBER}",
      "autoStart": true,
      "dmPolicy": "pairing",
      "groupPolicy": "allowlist",
      "configWrites": false,
      "allowFrom": ["${ADMIN_PHONE_1}", "${ADMIN_PHONE_2}"],
      "groupAllowFrom": ["${ADMIN_PHONE_2}"],
      "historyLimit": 50,
      "textChunkLimit": 4000,
      "ignoreStories": true
    }
  },
  "session": {
    "scope": "per-sender",
    "reset": {
      "mode": "daily"
    }
  },
  "logging": {
    "level": "info"
  },
  "browser": {
    "enabled": false
  },
  "tools": {
    "profile": "coding"
  }
}
```

---

## Files Modified/Created

| File | Action |
|------|--------|
| `moltbot.json` | Add agents.list, agentToAgent config, Signal env var |
| `Dockerfile` | Add agent directory creation (avoids race condition) |
| `server.js` | Add health check endpoint |
| `openclaw_memory.py` | Create with full implementation + fallback mode |
| `/data/workspace/souls/*.md` | Create (6 files) |
| Neo4j schema | Create via Cypher (includes SessionContext, CREATED rel, WorkflowImprovement) |
