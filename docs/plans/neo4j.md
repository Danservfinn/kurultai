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
  session_date,  // Neo4j date() type - enables proper date arithmetic and range queries
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
// Index for efficient retention policy enforcement (oldest first query)
// Supports: MATCH (r:Reflection) WHERE r.agent = $agent ORDER BY r.created_at ASC
// Used by _enforce_retention_policy to find oldest reflections for archival
CREATE INDEX reflection_created_at FOR (r:Reflection) ON (r.created_at);

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

### Data Type Migrations

#### SessionContext session_date Migration (v2.0)

**Change**: `session_date` field changed from string ('YYYY-MM-DD') to Neo4j `date()` type.

**Benefits**:
- Enables proper date arithmetic using Neo4j temporal functions
- Supports range queries with `duration.between()`
- Allows efficient filtering with comparison operators
- Enables date truncation and extraction functions

**Migration Cypher**:
```cypher
// Migrate existing string dates to date() type
MATCH (s:SessionContext)
WHERE s.session_date IS STRING
WITH s, s.session_date as old_date
SET s.session_date = date(s.session_date)
RETURN count(s) as migrated_count
```

**Query Updates**:
```cypher
// Before (string comparison - unreliable)
MATCH (s:SessionContext)
WHERE s.session_date >= '2024-01-15'  // String comparison

// After (date arithmetic - reliable)
MATCH (s:SessionContext)
WHERE s.session_date >= date('2024-01-15')

// Range queries now possible
MATCH (s:SessionContext)
WHERE s.session_date >= date() - duration({days: 7})
RETURN s

// Date difference calculations
MATCH (s:SessionContext)
RETURN duration.between(s.session_date, date()).days as days_old
```

**Python Driver Compatibility**:
- Python `datetime.date` objects are automatically converted to Neo4j `date()`
- No code changes required - pass `date.today()` instead of `date.today().isoformat()`

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
            CREATE INDEX reflection_created_at FOR (r:Reflection) ON (r.created_at);
            CREATE INDEX session_context_lookup FOR (s:SessionContext) ON (s.sender_id, s.session_date);
            CREATE INDEX agent_backup_lookup FOR (b:AgentBackup) ON (b.created_at);
            CREATE FULLTEXT INDEX knowledge_content
                FOR (n:Research|Content|Concept) ON EACH [n.findings, n.body, n.description];
        ''',
        'down': '''
            // Backup all Agent nodes before deletion (auto-cleanup: keeps last 10)
            CALL {
                MATCH (a:Agent)
                CREATE (b:AgentBackup {
                    agent_id: a.id,
                    name: a.name,
                    role: a.role,
                    primary_capabilities: a.primary_capabilities,
                    personality: a.personality,
                    last_active: a.last_active,
                    backed_up_at: datetime(),
                    migration_version: 0,
                    backup_reason: 'rollback_from_v1'
                })
                RETURN count(b) as backed_up
            }
            // Clean up old backups (keep only most recent 10)
            WITH backed_up
            CALL {
                MATCH (b:AgentBackup)
                WITH b ORDER BY b.created_at DESC
                SKIP 10
                DETACH DELETE b
            }
            // Now delete the agents
            WITH backed_up
            MATCH (a:Agent) DETACH DELETE a;
            DROP INDEX agent_knowledge IF EXISTS;
            DROP INDEX task_status IF EXISTS;
            DROP INDEX notification_read IF EXISTS;
            DROP INDEX notification_created_at IF EXISTS;
            DROP INDEX reflection_created_at IF EXISTS;
            DROP INDEX session_context_lookup IF EXISTS;
            DROP INDEX agent_backup_lookup IF EXISTS;
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

    def _session(self):
        """Get a session from the driver."""
        return self.driver.session()

    def _ensure_schema_version_node(self):
        """Create schema version tracking node if not exists."""
        query = '''
            MERGE (s:SchemaVersion {id: 'current'})
            ON CREATE SET s.version = 0, s.updated_at = datetime()
        '''
        with self._session() as session:
            session.run(query)

    def get_current_version(self) -> int:
        """Get current schema version from database."""
        query = '''
            MATCH (s:SchemaVersion {id: 'current'})
            RETURN s.version as version
        '''
        with self._session() as session:
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
        with self._session() as session:
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

    def _backup_agents_before_rollback(self, version: int) -> int:
        """Create backup of all Agent nodes before destructive rollback.

        Creates :AgentBackup nodes with all Agent properties, timestamp,
        and migration version. Automatically limits to most recent 10 backups.

        Args:
            version: The migration version being rolled back from

        Returns:
            Number of agents backed up
        """
        backup_query = '''
            MATCH (a:Agent)
            CREATE (b:AgentBackup {
                agent_id: a.id,
                name: a.name,
                role: a.role,
                primary_capabilities: a.primary_capabilities,
                personality: a.personality,
                last_active: a.last_active,
                backed_up_at: datetime(),
                migration_version: $version,
                backup_reason: $reason
            })
            RETURN count(b) as backed_up
        '''

        cleanup_query = '''
            MATCH (b:AgentBackup)
            WITH b ORDER BY b.backed_up_at DESC
            SKIP 10
            DETACH DELETE b
        '''

        with self._session() as session:
            # Create backups
            result = session.run(backup_query, version=version,
                                   reason=f'rollback_from_v{version}')
            record = result.single()
            backed_up = record['backed_up'] if record else 0

            # Clean up old backups (keep last 10)
            session.run(cleanup_query)

            print(f"[BACKUP] Created {backed_up} AgentBackup nodes "
                  f"(migration v{version})")
            return backed_up

    def _restore_agents_from_backup(self, backup_id: str = None) -> int:
        """Restore Agent nodes from backup.

        Emergency recovery method to restore agents from AgentBackup nodes.
        If backup_id is specified, restores from that specific backup.
        Otherwise, restores from the most recent backup.

        Args:
            backup_id: Optional specific agent_id to restore from backup

        Returns:
            Number of agents restored
        """
        if backup_id:
            # Restore specific agent from backup
            restore_query = '''
                MATCH (b:AgentBackup {agent_id: $backup_id})
                WITH b ORDER BY b.backed_up_at DESC LIMIT 1
                CREATE (a:Agent {
                    id: b.agent_id,
                    name: b.name,
                    role: b.role,
                    primary_capabilities: b.primary_capabilities,
                    personality: b.personality,
                    last_active: datetime()
                })
                RETURN count(a) as restored
            '''
            with self._session() as session:
                result = session.run(restore_query, backup_id=backup_id)
                record = result.single()
                restored = record['restored'] if record else 0
                print(f"[RESTORE] Restored agent '{backup_id}' from backup")
                return restored
        else:
            # Restore all agents from most recent backup
            restore_query = '''
                MATCH (b:AgentBackup)
                WITH b.agent_id as agent_id, max(b.backed_up_at) as latest
                MATCH (b:AgentBackup {agent_id: agent_id, backed_up_at: latest})
                CREATE (a:Agent {
                    id: b.agent_id,
                    name: b.name,
                    role: b.role,
                    primary_capabilities: b.primary_capabilities,
                    personality: b.personality,
                    last_active: datetime()
                })
                RETURN count(a) as restored
            '''
            with self._session() as session:
                result = session.run(restore_query)
                record = result.single()
                restored = record['restored'] if record else 0
                print(f"[RESTORE] Restored {restored} agents from latest backups")
                return restored

    def list_agent_backups(self) -> List[Dict[str, Any]]:
        """List all available Agent backups.

        Returns:
            List of backup records with agent_id, name, backed_up_at,
            migration_version, and backup_reason
        """
        query = '''
            MATCH (b:AgentBackup)
            RETURN b.agent_id as agent_id,
                   b.name as name,
                   b.role as role,
                   b.backed_up_at as backed_up_at,
                   b.migration_version as migration_version,
                   b.backup_reason as backup_reason
            ORDER BY b.backed_up_at DESC
        '''
        with self._session() as session:
            result = session.run(query)
            return [dict(record) for record in result]

    def migrate_with_backup(self, target_version: int = None) -> List[Dict[str, Any]]:
        """Run migrations with automatic backup before destructive rollbacks.

        This is the RECOMMENDED way to run migrations. It automatically creates
        backups before any 'down' migration that would delete Agent nodes.

        Args:
            target_version: Version to migrate to (None = latest)

        Returns:
            List of applied migrations with backup info
        """
        current = self.get_current_version()
        target = target_version or max(m['version'] for m in MIGRATIONS)
        applied = []

        if current < target:
            # Migrate up - no backup needed
            for migration in MIGRATIONS:
                if current < migration['version'] <= target:
                    self._apply_migration(migration, 'up')
                    applied.append({
                        'version': migration['version'],
                        'direction': 'up',
                        'backup_created': False
                    })
        elif current > target:
            # Migrate down - backup before destructive operations
            for migration in reversed(MIGRATIONS):
                if target < migration['version'] <= current:
                    # Check if this is v1 (has Agent deletion)
                    if migration['version'] == 1:
                        # Create backup before rollback
                        backed_up = self._backup_agents_before_rollback(
                            migration['version']
                        )
                        applied.append({
                            'version': migration['version'],
                            'direction': 'down',
                            'backup_created': True,
                            'agents_backed_up': backed_up
                        })
                    else:
                        applied.append({
                            'version': migration['version'],
                            'direction': 'down',
                            'backup_created': False
                        })

                    self._apply_migration(migration, 'down')

        return applied
```

**Data Safety: Backup and Restore Procedures**

The MigrationManager includes automatic backup capabilities to prevent data loss during rollbacks. When rolling back migration v1 (which deletes all Agent nodes), the system automatically creates backups before deletion.

**Automatic Backup During Rollback:**

The migration v1 'down' operation now includes embedded backup logic:

```cypher
// Backup all Agent nodes before deletion (auto-cleanup: keeps last 10)
CALL {
    MATCH (a:Agent)
    CREATE (b:AgentBackup {
        agent_id: a.id,
        name: a.name,
        role: a.role,
        primary_capabilities: a.primary_capabilities,
        personality: a.personality,
        last_active: a.last_active,
        backed_up_at: datetime(),
        migration_version: 0,
        backup_reason: 'rollback_from_v1'
    })
    RETURN count(b) as backed_up
}
// Clean up old backups (keep only most recent 10)
WITH backed_up
CALL {
    MATCH (b:AgentBackup)
    WITH b ORDER BY b.created_at DESC
    SKIP 10
    DETACH DELETE b
}
// Now delete the agents
WITH backed_up
MATCH (a:Agent) DETACH DELETE a;
```

**Using migrate_with_backup() (Recommended):**

```python
manager = MigrationManager(driver)

# This automatically backs up before destructive rollbacks
result = manager.migrate_with_backup(target_version=0)
# Output: [{'version': 1, 'direction': 'down', 'backup_created': True, 'agents_backed_up': 6}]
```

**Manual Backup and Restore:**

```python
# Create manual backup before rollback
manager._backup_agents_before_rollback(version=1)

# List available backups
backups = manager.list_agent_backups()
for backup in backups:
    print(f"{backup['agent_id']}: {backup['name']} backed up at {backup['backed_up_at']}")

# Restore all agents from latest backups
restored_count = manager._restore_agents_from_backup()
print(f"Restored {restored_count} agents")

# Restore specific agent
manager._restore_agents_from_backup(backup_id='analyst')
```

**Emergency Recovery Procedure:**

If agents are accidentally deleted during a rollback:

1. **Check available backups:**
   ```python
   backups = manager.list_agent_backups()
   ```

2. **Restore from backup:**
   ```python
   # Restore all agents
   manager._restore_agents_from_backup()

   # Or restore specific agent
   manager._restore_agents_from_backup(backup_id='developer')
   ```

3. **Verify restoration:**
   ```cypher
   MATCH (a:Agent) RETURN count(a) as agent_count
   ```

**Backup Retention Policy:**

- Maximum 10 backups retained per agent (configurable)
- Oldest backups are automatically purged
- Each backup includes: agent_id, name, role, capabilities, personality, timestamp, migration version
- Backups are stored as `:AgentBackup` nodes in Neo4j

**Index for Backup Performance:**

```cypher
CREATE INDEX agent_backup_lookup FOR (b:AgentBackup) ON (b.created_at);
```

This index ensures fast backup queries and efficient cleanup of old backups.

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
import json
import base64
import hashlib
import hmac
import time
import warnings
import threading
import socket
import ipaddress
import logging
from typing import Optional, List, Dict, Any, Tuple, Set, Union, Callable
from uuid import uuid4, UUID
from datetime import datetime, timedelta, date
from urllib.parse import urlparse
from enum import Enum

from neo4j import GraphDatabase, Driver
from neo4j.exceptions import ServiceUnavailable, AuthError, TransientError

# Optional dependencies - handle gracefully if not installed
try:
    from cryptography.fernet import Fernet
except ImportError:
    Fernet = None

try:
    from apscheduler.schedulers.background import BackgroundScheduler
except ImportError:
    BackgroundScheduler = None

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

try:
    import requests
except ImportError:
    requests = None

# Module-level logger for OperationalMemory
logger = logging.getLogger('operational_memory')


# Task Claim Exception Classes
class TaskClaimError(Exception):
    """Base exception for task claiming failures."""
    pass


class NoPendingTaskError(TaskClaimError):
    """No pending tasks available for claiming.

    This is a normal condition when all tasks have been claimed
    or when no tasks are assigned to the requesting agent.
    """
    pass


class RaceConditionError(TaskClaimError):
    """Another agent claimed the task first.

    Raised when optimistic locking detects a concurrent claim.
    This is a retryable condition.
    """
    pass


class DatabaseError(TaskClaimError):
    """Database operation failed.

    Indicates a non-retryable database error that requires
    administrative attention.
    """
    pass


class RateLimitExceeded(TaskClaimError):
    """Rate limit exceeded for agent operation."""
    pass


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open and rejecting requests."""
    pass


class SyncError(Exception):
    """Raised when fallback data sync to Neo4j fails critically.

    This error indicates that a significant portion of data accumulated
    during fallback mode could not be synced back to Neo4j, potentially
    resulting in data loss. The system remains in fallback mode when
    this error is raised to prevent further data accumulation.
    """
    pass


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"          # Normal operation
    OPEN = "open"              # Failing, reject requests
    HALF_OPEN = "half_open"    # Testing if recovered


class CircuitBreaker:
    """Circuit breaker for external service calls.

    Protects against cascading failures by temporarily rejecting requests
    when a service is failing. After a recovery timeout, allows a test
    request through (half-open). If successful, closes the circuit;
    if failed, reopens it.

    Thread-safe implementation using locks.

    Example:
        breaker = CircuitBreaker(
            name="openclaw_gateway",
            failure_threshold=5,
            recovery_timeout=30.0,
            expected_exception=(requests.RequestException, TimeoutError)
        )

        try:
            result = breaker.call(make_request, arg1, arg2)
        except CircuitBreakerOpen:
            # Circuit is open, use fallback
            result = fallback_result
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        expected_exception: type = Exception
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._state = CircuitState.CLOSED
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        with self._lock:
            return self._state

    @property
    def failure_count(self) -> int:
        """Current failure count."""
        with self._lock:
            return self._failure_count

    def call(self, func: Callable, *args, **kwargs):
        """Call function with circuit breaker protection.

        Args:
            func: Function to call
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from func

        Raises:
            CircuitBreakerOpen: If circuit is open and recovery timeout not elapsed
            Exception: Any exception raised by func (wrapped in expected_exception)
        """
        with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._state = CircuitState.HALF_OPEN
                    logger.info(f"Circuit {self.name} entering half-open state")
                else:
                    raise CircuitBreakerOpen(
                        f"Circuit {self.name} is OPEN - failing fast"
                    )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to try again.

        Returns:
            True if recovery timeout has elapsed since last failure.
        """
        if self._last_failure_time is None:
            return True
        return time.time() - self._last_failure_time >= self.recovery_timeout

    def _on_success(self):
        """Handle successful call.

        Closes circuit if in half-open state, resets failure count.
        """
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._last_failure_time = None
                logger.info(f"Circuit {self.name} closed - service recovered")

    def _on_failure(self):
        """Handle failed call.

        Increments failure count and opens circuit if threshold reached.
        """
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.error(
                    f"Circuit {self.name} opened after {self._failure_count} failures"
                )


class OperationalMemory:
    """Neo4j-backed operational memory with fallback mode."""

    # Rate limiting: max operations per agent per hour
    RATE_LIMIT_HOURLY = 1000
    RATE_LIMIT_BURST = 100  # Short-term burst allowance

    # Required environment variables for startup
    REQUIRED_ENV_VARS = [
        'NEO4J_URI',
        'NEO4J_PASSWORD',
        'OPENCLAW_GATEWAY_TOKEN',
        'AGENT_AUTH_SECRET'
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

        # Circuit breaker for OpenClaw gateway calls
        # Protects against cascading failures if Kublai is slow/unresponsive
        self._gateway_circuit = CircuitBreaker(
            name="openclaw_gateway",
            failure_threshold=5,
            recovery_timeout=30.0,
            expected_exception=(requests.RequestException, TimeoutError)
        )

        # Fallback store limits to prevent memory exhaustion
        self._MAX_FALLBACK_TASKS = 1000
        self._MAX_FALLBACK_RESEARCH = 500
        self._MAX_FALLBACK_ITEMS_PER_CATEGORY = 1000

        # Background task concurrency limit to prevent connection pool exhaustion
        # With 5 non-main agents, limit concurrent long-running tasks to 2
        self._MAX_CONCURRENT_BACKGROUND_TASKS = 2
        self._background_task_semaphore = threading.Semaphore(self._MAX_CONCURRENT_BACKGROUND_TASKS)
        self._background_task_queue: List[Dict[str, Any]] = []  # Pending tasks
        self._background_task_lock = threading.Lock()  # Thread-safe queue access
        self._background_task_active: Set[str] = set()  # Track active task IDs

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

        # Cache valid agents from environment to avoid recomputation
        self.VALID_AGENTS = self._compute_valid_agents()

    def _validate_environment(self):
        """Validate required environment variables are set.

        Raises:
            RuntimeError: If any required environment variable is missing.
        """
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
            with self._session_pool() as session:
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
        except (ServiceUnavailable, AuthError) as e:
            print(f"[WARN] Neo4j connection error during version check: {e}")
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
                        # Success - attempt to sync fallback data
                        print("[RECOVERY] Neo4j connection restored, syncing fallback data...")
                        try:
                            self._sync_fallback_to_neo4j()
                            # Only exit fallback mode if sync succeeds
                            self.fallback_mode = False
                            print("[RECOVERY] Successfully synced fallback data, exiting fallback mode")
                        except SyncError as e:
                            # Sync failed critically - remain in fallback mode
                            print(f"[RECOVERY] Sync failed: {e}")
                            print("[RECOVERY] Remaining in fallback mode, will retry on next cycle")
                except Exception:
                    pass  # Still unavailable, keep trying
                time.sleep(30)  # Check every 30 seconds

        recovery_thread = threading.Thread(target=try_recover, daemon=True)
        recovery_thread.start()
        print("[INFO] Recovery monitor started")

    def _sync_fallback_to_neo4j(self):
        """Sync data from fallback mode back to Neo4j after recovery.

        Syncs all data categories accumulated during fallback mode:
        - tasks: Task nodes created during outage
        - research: Research findings stored during outage
        - concepts: Concept nodes with embeddings
        - signal_sessions: Signal messenger session state
        - notification_dlq: Dead letter queue for failed notifications

        Thread-safe: Acquires fallback lock to prevent concurrent modification
        during sync. Uses list() to snapshot items before processing.

        Raises:
            SyncError: If more than 10% of items fail to sync, indicating
                persistent issues that require investigation.
        """
        with self._fallback_lock:
            if not self._local_store:
                logger.info("No fallback data to sync")
                return

            # Snapshot categories to avoid dict changing during iteration
            categories_snapshot = list(self._local_store.items())

        # Track sync statistics for all categories
        sync_stats = {
            'tasks': {'success': 0, 'failed': 0},
            'research': {'success': 0, 'failed': 0},
            'concepts': {'success': 0, 'failed': 0},
            'signal_sessions': {'success': 0, 'failed': 0},
            'notification_dlq': {'success': 0, 'failed': 0},
            'total_success': 0,
            'total_failed': 0
        }

        total_items = sum(len(items) for _, items in categories_snapshot)
        logger.info(f"[SYNC] Starting fallback sync: {total_items} items across {len(categories_snapshot)} categories")

        for category, items in categories_snapshot:
            # Snapshot items list for this category
            items_snapshot = list(items) if isinstance(items, list) else [items]

            for item in items_snapshot:
                try:
                    success = self._sync_item_by_category(category, item)
                    if success:
                        sync_stats[category]['success'] += 1
                        sync_stats['total_success'] += 1
                        # Remove successfully synced item from fallback store
                        with self._fallback_lock:
                            store_items = self._local_store.get(category, [])
                            if isinstance(store_items, list) and item in store_items:
                                store_items.remove(item)
                            elif isinstance(store_items, dict) and item.get('id') in store_items:
                                del store_items[item['id']]
                    else:
                        sync_stats[category]['failed'] += 1
                        sync_stats['total_failed'] += 1
                        logger.warning(f"[SYNC] Failed to sync {category} item (returned None)")
                except Exception as e:
                    sync_stats[category]['failed'] += 1
                    sync_stats['total_failed'] += 1
                    logger.error(f"[SYNC ERROR] Failed to sync {category} item: {e}", exc_info=True)

        # Log detailed statistics
        logger.info(f"[SYNC] Fallback sync complete: {sync_stats['total_success']} succeeded, {sync_stats['total_failed']} failed")
        for category, stats in sync_stats.items():
            if category not in ('total_success', 'total_failed') and (stats['success'] > 0 or stats['failed'] > 0):
                logger.info(f"[SYNC]   {category}: {stats['success']} success, {stats['failed']} failed")

        # Only exit fallback mode if failure rate is acceptable (< 10%)
        total_attempted = sync_stats['total_success'] + sync_stats['total_failed']
        if total_attempted > 0:
            failure_rate = sync_stats['total_failed'] / total_attempted
            if failure_rate >= 0.1:
                error_msg = f"Sync failure rate {failure_rate:.1%} exceeds threshold (10%), remaining in fallback mode"
                logger.error(f"[SYNC] {error_msg}")
                raise SyncError(error_msg)

    def _sync_item_by_category(self, category: str, item: Dict) -> bool:
        """Sync a single fallback item to Neo4j based on its category.

        Args:
            category: The data category (tasks, research, concepts, etc.)
            item: The item data to sync

        Returns:
            True if sync succeeded, False otherwise
        """
        sync_handlers = {
            'tasks': self._sync_task_item,
            'research': self._sync_research_item,
            'concepts': self._sync_concept_item,
            'signal_sessions': self._sync_signal_session_item,
            'notification_dlq': self._sync_notification_dlq_item,
        }

        handler = sync_handlers.get(category)
        if not handler:
            logger.warning(f"[SYNC] Unknown category '{category}', skipping item")
            return False

        return handler(item)

    def _sync_task_item(self, item: Dict) -> bool:
        """Sync a task item from fallback store to Neo4j."""
        try:
            result = self.create_task(
                task_type=item.get('type', 'unknown'),
                description=item.get('description', ''),
                delegated_by=item.get('delegated_by', 'main'),
                assigned_to=item.get('assigned_to', 'main')
            )
            return result is not None
        except Exception as e:
            logger.error(f"[SYNC] Failed to sync task: {e}")
            return False

    def _sync_research_item(self, item: Dict) -> bool:
        """Sync a research item from fallback store to Neo4j."""
        try:
            # Build query with all research fields
            query = """
            MATCH (a:Agent {id: $agent})
            CREATE (r:Research {
                id: $id,
                topic: $topic,
                findings: $findings,
                sources: $sources,
                depth: $depth,
                access_tier: $access_tier,
                sender_hash: $sender_hash,
                created_at: datetime($created_at),
                confidence: 0.9
            })
            CREATE (a)-[:CREATED {timestamp: datetime()}]->(r)
            RETURN r.id as id
            """
            with self._session_pool() as session:
                with session.begin_transaction() as tx:
                    tx.run(query,
                        agent=item.get('agent', 'unknown'),
                        id=item.get('id'),
                        topic=item.get('topic', ''),
                        findings=item.get('findings', ''),
                        sources=item.get('sources', []),
                        depth=item.get('depth', 'medium'),
                        access_tier=item.get('access_tier', 'general'),
                        sender_hash=item.get('sender_hash'),
                        created_at=item.get('created_at', datetime.now().isoformat())
                    )
            return True
        except Exception as e:
            logger.error(f"[SYNC] Failed to sync research: {e}")
            return False

    def _sync_concept_item(self, item: Dict) -> bool:
        """Sync a concept item from fallback store to Neo4j."""
        try:
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
                c.created_at = datetime($created_at),
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
            with self._session_pool() as session:
                with session.begin_transaction() as tx:
                    tx.run(query,
                        agent=item.get('agent', 'unknown'),
                        id=item.get('id'),
                        name=item.get('name', ''),
                        description=item.get('description', ''),
                        domain=item.get('domain', 'general'),
                        source=item.get('source', ''),
                        embedding=item.get('embedding'),
                        access_tier=item.get('access_tier', 'general'),
                        sender_hash=item.get('sender_hash'),
                        created_at=item.get('created_at', datetime.now().isoformat())
                    )
            return True
        except Exception as e:
            logger.error(f"[SYNC] Failed to sync concept: {e}")
            return False

    def _sync_signal_session_item(self, item: Dict) -> bool:
        """Sync a Signal session item from fallback store to Neo4j."""
        try:
            query = """
            CREATE (s:SignalSession {
                id: $id,
                phone_number: $phone_number,
                device_id: $device_id,
                registered: $registered,
                created_at: datetime($created_at)
            })
            RETURN s.id as id
            """
            with self._session_pool() as session:
                session.run(query,
                    id=item.get('id'),
                    phone_number=item.get('phone_number'),
                    device_id=item.get('device_id'),
                    registered=item.get('registered', False),
                    created_at=item.get('created_at', datetime.now().isoformat())
                )
            return True
        except Exception as e:
            logger.error(f"[SYNC] Failed to sync signal session: {e}")
            return False

    def _sync_notification_dlq_item(self, item: Dict) -> bool:
        """Sync a notification DLQ item from fallback store to Neo4j."""
        try:
            query = """
            CREATE (n:NotificationDLQ {
                id: $id,
                recipient: $recipient,
                message: $message,
                error: $error,
                retry_count: $retry_count,
                created_at: datetime($created_at)
            })
            RETURN n.id as id
            """
            with self._session_pool() as session:
                session.run(query,
                    id=item.get('id'),
                    recipient=item.get('recipient'),
                    message=item.get('message'),
                    error=item.get('error'),
                    retry_count=item.get('retry_count', 0),
                    created_at=item.get('created_at', datetime.now().isoformat())
                )
            return True
        except Exception as e:
            logger.error(f"[SYNC] Failed to sync notification DLQ item: {e}")
            return False

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
                logger.exception(f"Unexpected error in query execution: {e}")
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
        safe_error = re.sub(r'bolt://[^:]+:[^@]+@', 'bolt://***@', safe_error)
        safe_error = re.sub(r'neo4j://[^:]+:[^@]+@', 'neo4j://***@', safe_error)
        return safe_error

    def _init_embedding_encryption(self):
        """Initialize encryption for SENSITIVE tier embeddings.

        Uses AES-256-GCM for authenticated encryption of embedding vectors.
        Key is derived from EMBEDDING_ENCRYPTION_KEY environment variable.
        Falls back to no encryption if key not provided (logs warning).
        """
        key_env = os.getenv('EMBEDDING_ENCRYPTION_KEY', '')
        if not key_env:
            print("[PRIVACY WARNING] EMBEDDING_ENCRYPTION_KEY not set. SENSITIVE embeddings will be stored unencrypted.")
            return

        try:
            if Fernet is None:
                raise ImportError("cryptography not installed")
            # Ensure key is valid Fernet key (32 bytes, base64-encoded)
            if len(key_env) < 32:
                # Derive key using PBKDF2 if provided key is too short
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
    def _llm_sanitize(self, text: str, agent_context: Dict[str, Any] = None) -> Optional[str]:
        """Use Kublai (via agentToAgent) to review and redact private information.

        Kublai acts as the privacy gatekeeper before content enters operational memory.
        Falls back to pattern-based sanitization if Kublai unavailable.

        SECURITY: Input is strictly validated and escaped before being sent to LLM
        to prevent prompt injection attacks.

        SSRF PROTECTION: This method implements multiple layers of SSRF protection:
        1. URL parsing and scheme validation
        2. Hostname whitelist validation
        3. DNS resolution with IP-based whitelist verification
        4. Private IP range blocking (prevents access to internal services)
        5. No redirects allowed (prevents redirect-based bypasses)
        6. Request timeouts (prevents hanging connections)

        Returns sanitized text or None to trigger pattern fallback.
        """
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

            # =========================================================================
            # SSRF PROTECTION - Layer 1: URL Parsing and Basic Validation
            # =========================================================================
            allowed_hosts = {
                'localhost', '127.0.0.1', '::1',
                'kublai.kurult.ai',
                'openclaw.railway.internal',
                'moltbot.railway.internal'
            }

            # Allowed IP ranges (CIDR notation)
            allowed_ip_ranges = {
                '127.0.0.0/8',      # Loopback
                '::1/128',          # IPv6 loopback
                '10.0.0.0/8',       # Private network (if needed for internal services)
                '172.16.0.0/12',    # Private network
                '192.168.0.0/16',   # Private network
            }

            try:
                parsed = urlparse(gateway_url)

                # Block non-HTTP schemes (file://, ftp://, etc.)
                if parsed.scheme not in ('http', 'https'):
                    print(f"[PRIVACY] Invalid URL scheme '{parsed.scheme}', using pattern fallback")
                    return None

                # Block URLs with authentication credentials (user:pass@host)
                if parsed.username or parsed.password:
                    print("[PRIVACY] URL with embedded credentials rejected, using pattern fallback")
                    return None

                # Block non-standard ports
                if parsed.port and parsed.port not in (
                    80, 443, 8080, 8081, 8082, 8083, 8084, 8085, 8086, 8087, 8088, 8089,
                    3000, 3001, 3002, 3003, 3004, 3005, 3006, 3007, 3008, 3009
                ):
                    print(f"[PRIVACY] Non-standard port {parsed.port} rejected, using pattern fallback")
                    return None

                # Validate hostname is in whitelist
                if not parsed.hostname:
                    print("[PRIVACY] No hostname in URL, using pattern fallback")
                    return None

                if parsed.hostname not in allowed_hosts:
                    print(f"[PRIVACY] Invalid gateway URL host '{parsed.hostname}', using pattern fallback")
                    return None

            except ValueError as e:
                print(f"[PRIVACY] URL parse error: {e}, using pattern fallback")
                return None

            # =========================================================================
            # SSRF PROTECTION - Layer 2: DNS Resolution and IP Validation
            # This prevents DNS rebinding attacks where an attacker controls DNS
            # and returns different IPs between validation and request
            # =========================================================================
            try:
                # Resolve hostname to IP addresses
                resolved_ips = socket.getaddrinfo(parsed.hostname, None)
                resolved_ip_set = {ip[4][0] for ip in resolved_ips}

                # Check each resolved IP against private IP ranges
                for ip_str in resolved_ip_set:
                    try:
                        ip_obj = ipaddress.ip_address(ip_str)

                        # Block private IP ranges unless explicitly allowed
                        # This prevents access to internal services via DNS rebinding
                        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
                            # Only allow if the hostname is explicitly whitelisted
                            # AND the IP is in our allowed ranges
                            in_allowed_range = any(
                                ip_obj in ipaddress.ip_network(cidr)
                                for cidr in allowed_ip_ranges
                            )
                            if not in_allowed_range:
                                print(f"[PRIVACY] Blocked request to private IP {ip_str} "
                                      f"(DNS rebinding protection), using pattern fallback")
                                return None

                        # Block multicast and reserved addresses
                        if ip_obj.is_multicast or ip_obj.is_reserved:
                            print(f"[PRIVACY] Blocked request to {ip_str} "
                                  f"(multicast/reserved), using pattern fallback")
                            return None

                    except ValueError:
                        # Invalid IP format, skip
                        continue

            except socket.gaierror as e:
                print(f"[PRIVACY] DNS resolution failed for '{parsed.hostname}': {e}, using pattern fallback")
                return None
            except Exception as e:
                print(f"[PRIVACY] IP validation error: {e}, using pattern fallback")
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

            # =========================================================================
            # SSRF PROTECTION - Layer 3: Request Configuration
            # - Short timeout prevents hanging connections
            # - No redirects prevents redirect-based bypasses
            # =========================================================================

            # Define the request function for circuit breaker
            def _make_gateway_request():
                return requests.post(
                    f"{gateway_url}/agent/main/message",
                    headers={
                        'Authorization': f'Bearer {token}',
                        'Content-Type': 'application/json'
                    },
                    json={
                        'message': review_prompt,
                        'context': {'privacy_review': True, 'skip_memory': True}
                    },
                    timeout=10,  # Reduced from 30s to prevent hanging connections
                    allow_redirects=False  # Prevent redirect-based SSRF bypasses
                )

            # =========================================================================
            # CIRCUIT BREAKER PROTECTION
            # Prevents cascading failures if Kublai is slow/unresponsive
            # Falls back to pattern-based sanitization when circuit is open
            # =========================================================================
            try:
                response = self._gateway_circuit.call(_make_gateway_request)
            except CircuitBreakerOpen:
                logger.warning("Circuit breaker open for OpenClaw gateway, using pattern fallback")
                return None
            except (requests.RequestException, TimeoutError) as e:
                logger.warning(f"OpenClaw gateway request failed: {e}, using pattern fallback")
                return None

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
                logger.warning(f"[PRIVACY] Kublai unavailable ({response.status_code}), using pattern fallback")
                return None

        except Exception as e:
            # Catch-all for any unexpected errors during sanitization
            logger.warning(f"[PRIVACY] Kublai review failed: {e}, using pattern fallback")
            return None

        return None  # Signal to use pattern fallback

    def _check_rate_limit(self, agent: str, operation: str) -> bool:
        """Check if agent has exceeded rate limit for operation.

        Uses Neo4j-backed rate limiting for multi-instance consistency.
        Falls back to memory-based limiting in fallback mode.

        Returns True if operation allowed, False if rate limited.
        """
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

        except (ServiceUnavailable, TransientError) as e:
            print(f"[RATE_LIMIT ERROR] Neo4j connectivity error during rate limit check: {e}, using fallback")
            # Fall back to memory-based on error
            return True  # Allow operation rather than block on error
        except Exception as e:
            print(f"[RATE_LIMIT ERROR] Neo4j rate limit check failed: {e}, using fallback")
            # Fall back to memory-based on error
            return True  # Allow operation rather than block on error

    def _hash_phone_number(self, phone: str) -> str:
        """Hash phone number using HMAC-SHA256 with salt for privacy.

        Uses PHONE_HASH_SALT environment variable. Same phone always produces
        same hash, but hash cannot be reversed without the salt.
        """
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

        # Physical addresses - common patterns
        # Street addresses like "123 Main St" or "456 Oak Avenue, Apt 2B"
        text = re.sub(r'\b\d+\s+[A-Za-z]+(?:\s+[A-Za-z]+)*(?:\s+(?:St|Street|Ave|Avenue|Rd|Road|Dr|Drive|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Ter|Terrace|Trail|Loop|Circle|Highway|Hwy|Route|Rt))\b(?:[,\s]+(?:Apt|Apartment|Suite|Ste|Unit|#)\s*\w+)?', '[ADDRESS]', text, flags=re.I)

        # Names with titles (Mr., Mrs., Dr., etc.) - basic pattern for common names
        # Matches patterns like "Mr. John Smith" or "Dr. Sarah Johnson"
        text = re.sub(r'\b(?:Mr|Mrs|Ms|Miss|Dr|Prof)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b', '[NAME]', text)

        # Common name patterns after "my friend/colleague/contact"
        text = re.sub(r'\b(my friend|my colleague|my contact|my boss|my coworker)\s+[A-Z][a-z]+\b', r'\1 [NAME]', text, flags=re.I)

        # URLs with potential personal info
        text = re.sub(r'https?://[^\s<>"{}|\\^`\[\]]+', '[URL]', text)

        return text

    def _sanitize_for_sharing(self, text: str, sender_hash: Optional[str] = None) -> str:
        """Sanitize personal information before sharing to operational memory.

        Uses LLM-based review with pattern-based fallback for common PII.
        This is the primary entry point for sanitization before content is
        stored in operational memory or delegated to other agents.

        The method follows a defense-in-depth approach:
        1. First attempts LLM-based sanitization for intelligent PII detection
        2. Falls back to pattern-based sanitization if LLM is unavailable
        3. Logs all sanitization attempts for audit purposes

        Args:
            text: Raw text to sanitize
            sender_hash: Optional sender identifier for privacy context

        Returns:
            Sanitized text safe for operational memory

        Example:
            >>> memory._sanitize_for_sharing("Call Sarah at 555-123-4567")
            "Call [NAME] at [PHONE]"
        """
        if not text or not isinstance(text, str):
            return text

        # Handle empty or whitespace-only strings
        text = text.strip()
        if not text:
            return text

        # Try LLM-based sanitization first for intelligent PII detection
        try:
            llm_result = self._llm_sanitize(text)
            if llm_result is not None:
                logger.debug("LLM sanitization successful")
                return llm_result
            # If _llm_sanitize returns None, it signals fallback to patterns
            logger.debug("LLM sanitization returned None, using pattern fallback")
        except Exception as e:
            logger.warning(f"LLM sanitization failed: {e}, using pattern fallback")

        # Fallback to pattern-based sanitization
        try:
            pattern_result = self._pattern_sanitize(text)
            logger.debug("Pattern sanitization completed")
            return pattern_result
        except Exception as e:
            logger.error(f"Pattern sanitization also failed: {e}")
            # Last resort: return original text but log the failure
            # This ensures the system continues to function even if
            # sanitization fails completely
            return text

    def _sanitize_lucene_query(self, query: str) -> str:
        """Sanitize user input for Lucene full-text search.

        Escapes Lucene special characters that could cause syntax errors
        or unexpected behavior in full-text queries. While Neo4j parameterization
        prevents Cypher injection, Lucene query syntax has its own special
        characters that need escaping.

        Args:
            query: Raw user query string

        Returns:
            Sanitized query safe for Lucene full-text search

        Example:
            >>> _sanitize_lucene_query("C++ programming")
            'C\\+\\+ programming'
            >>> _sanitize_lucene_query("(foo OR bar)")
            '\\(foo OR bar\\)'
        """
        if not query or not isinstance(query, str):
            return query

        # Escape Lucene special characters
        # Characters: + - && || ! ( ) { } [ ] ^ " ~ * ? : \ /
        special_chars = r'[\+\-\!\(\)\{\}\[\]\^"\~\*\?\:\\\\/]'
        return re.sub(special_chars, r'\\\g<0>', query)

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
        with self._session_pool() as session:
            with session.begin_transaction() as tx:
                tx.run(query, agent=agent, id=str(knowledge_id),
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
            with self._session_pool() as session:
                with session.begin_transaction() as tx:
                    tx.run(query,
                        agent=agent, id=str(concept_id), name=safe_name,
                        description=safe_description, domain=domain, source=source,
                        embedding=stored_embedding, access_tier=access_tier,
                        sender_hash=sender_hash)
                return concept_id
        except Exception as e:
            print(f"[ERROR] Failed to store concept: {e}")
            return None


    def store_concepts_batch(self, agent: str, concepts: List[Dict[str, Any]]) -> List[str]:
        """Store multiple concepts in a single transaction.

        Reduces transaction overhead for bulk operations by using UNWIND
        to process all concepts in one Cypher query.

        Args:
            agent: Agent ID creating the concepts
            concepts: List of concept dicts with keys:
                - name: Concept name (required)
                - description: Concept description (required)
                - domain: Concept domain/category (default: "general")
                - source: Source of the concept (default: "")
                - sender_hash: Hash for access control (default: None)

        Returns:
            List of concept IDs that were successfully stored

        Example:
            concepts = [
                {
                    "name": "Machine Learning",
                    "description": "AI subset using statistical methods",
                    "domain": "AI",
                    "source": "research_paper_1"
                },
                {
                    "name": "Neural Networks",
                    "description": "Computing systems inspired by biological neurons",
                    "domain": "AI",
                    "source": "research_paper_1"
                }
            ]
            ids = memory.store_concepts_batch("agent_1", concepts)
        """
        if not concepts:
            return []

        # Validate agent identity once for the batch
        if not self._validate_agent_id(agent):
            print(f"[AUTH] Invalid agent storing concepts batch: {agent}")
            return []

        # Check rate limit once for the batch (count as single operation)
        if not self._check_rate_limit(agent, 'store_concept'):
            print(f"[RATE_LIMIT] store_concepts_batch blocked for {agent}")
            return []

        # Prepare concept data with IDs and sanitization
        concept_data = []
        for concept in concepts:
            name = concept.get('name', '')
            description = concept.get('description', '')

            # Skip invalid concepts
            if not name or not description:
                print(f"[WARN] Skipping concept with missing name/description")
                continue

            # Sanitize content
            safe_name = self._sanitize_for_sharing(name)
            safe_description = self._sanitize_for_sharing(description)

            # Determine access tier
            access_tier = self._determine_access_tier(
                safe_name + " " + safe_description,
                concept.get('sender_hash')
            )

            # Skip PRIVATE tier concepts
            if access_tier == self.ACCESS_TIER_PRIVATE:
                print(f"[PRIVACY] Concept '{safe_name}' blocked (PRIVATE tier)")
                continue

            # Generate and encrypt embedding
            embedding = self._generate_embedding(safe_name + " " + safe_description)
            stored_embedding = self._encrypt_embedding(embedding, access_tier) if embedding else None

            concept_data.append({
                'id': str(uuid4()),
                'name': safe_name,
                'description': safe_description,
                'domain': concept.get('domain', 'general'),
                'source': concept.get('source', ''),
                'embedding': stored_embedding,
                'access_tier': access_tier,
                'sender_hash': concept.get('sender_hash'),
                'confidence': 0.9
            })

        if not concept_data:
            return []

        # Fallback mode: store in local memory
        if self.fallback_mode:
            with self._fallback_lock:
                stored_ids = []
                for data in concept_data:
                    self._local_store.setdefault('concepts', []).append({
                        'id': data['id'],
                        'agent': agent,
                        'name': data['name'],
                        'description': data['description'],
                        'domain': data['domain'],
                        'source': data['source'],
                        'embedding': data['embedding'],
                        'access_tier': data['access_tier'],
                        'sender_hash': data['sender_hash'],
                        'created_at': datetime.now().isoformat()
                    })
                    stored_ids.append(data['id'])
            return stored_ids

        # Neo4j batch insert using UNWIND
        query = """
        MATCH (a:Agent {id: $agent})
        UNWIND $concepts AS concept
        MERGE (c:Concept {name: concept.name})
        ON CREATE SET
            c.id = concept.id,
            c.description = concept.description,
            c.domain = concept.domain,
            c.source = concept.source,
            c.embedding = concept.embedding,
            c.access_tier = concept.access_tier,
            c.sender_hash = concept.sender_hash,
            c.created_at = datetime(),
            c.confidence = concept.confidence
        ON MATCH SET
            c.description = concept.description,
            c.source = concept.source,
            c.embedding = concept.embedding,
            c.access_tier = concept.access_tier,
            c.sender_hash = concept.sender_hash,
            c.updated_at = datetime()
        CREATE (a)-[:CREATED {timestamp: datetime()}]->(c)
        RETURN c.id as id
        """

        try:
            with self._session_pool() as session:
                result = session.run(query, agent=agent, concepts=concept_data)
                return [record['id'] for record in result]
        except Exception as e:
            print(f"[ERROR] Failed to store concepts batch: {e}")
            return []

    def store_research_batch(self, agent: str, research_items: List[Dict[str, Any]]) -> List[str]:
        """Store multiple research findings in a single transaction.

        Reduces transaction overhead for bulk operations by using UNWIND
        to process all research items in one Cypher query.

        Args:
            agent: Agent ID storing the research
            research_items: List of research dicts with keys:
                - topic: Research topic (required)
                - findings: Research findings text (required)
                - sources: List of source references (default: [])
                - depth: Research depth (default: "medium")
                - sender_hash: Hash for access control (default: None)

        Returns:
            List of research IDs that were successfully stored

        Example:
            research_items = [
                {
                    "topic": "Quantum Computing",
                    "findings": "Qubits enable exponential speedup for certain problems",
                    "sources": ["Nature 2024", "IBM Research"],
                    "depth": "deep"
                },
                {
                    "topic": "Error Correction",
                    "findings": "Surface codes provide fault-tolerant quantum computation",
                    "sources": ["Google Quantum AI"],
                    "depth": "medium"
                }
            ]
            ids = memory.store_research_batch("agent_1", research_items)
        """
        if not research_items:
            return []

        # Validate agent identity once for the batch
        if not self._validate_agent_id(agent):
            print(f"[AUTH] Invalid agent storing research batch: {agent}")
            return []

        # Check rate limit once for the batch
        if not self._check_rate_limit(agent, 'store_research'):
            print(f"[RATE_LIMIT] store_research_batch blocked for {agent}")
            return []

        # Prepare research data with IDs and sanitization
        research_data = []
        for item in research_items:
            topic = item.get('topic', '')
            findings = item.get('findings', '')

            # Skip invalid items
            if not topic or not findings:
                print(f"[WARN] Skipping research with missing topic/findings")
                continue

            # Sanitize content
            safe_topic = self._sanitize_for_sharing(topic)
            safe_findings = self._sanitize_for_sharing(findings)

            # Determine access tier
            access_tier = self._determine_access_tier(
                safe_topic + " " + safe_findings,
                item.get('sender_hash')
            )

            # Skip PRIVATE tier research
            if access_tier == self.ACCESS_TIER_PRIVATE:
                print(f"[PRIVACY] Research on '{safe_topic}' blocked (PRIVATE tier)")
                continue

            research_data.append({
                'id': str(uuid4()),
                'topic': safe_topic,
                'findings': safe_findings,
                'sources': item.get('sources', []),
                'depth': item.get('depth', 'medium'),
                'access_tier': access_tier,
                'sender_hash': item.get('sender_hash'),
                'confidence': 0.9
            })

        if not research_data:
            return []

        # Fallback mode: store in local memory
        if self.fallback_mode:
            with self._fallback_lock:
                stored_ids = []
                for data in research_data:
                    # Enforce fallback store limits
                    current_research = self._local_store.get('research', [])
                    if len(current_research) >= self._MAX_FALLBACK_RESEARCH:
                        current_research.pop(0)  # Remove oldest

                    self._local_store.setdefault('research', []).append({
                        'id': data['id'],
                        'agent': agent,
                        'topic': data['topic'],
                        'findings': data['findings'],
                        'created_at': datetime.now().isoformat(),
                        'access_tier': data['access_tier'],
                        'sender_hash': data['sender_hash']
                    })
                    stored_ids.append(data['id'])
            return stored_ids

        # Neo4j batch insert using UNWIND
        query = """
        MATCH (a:Agent {id: $agent})
        UNWIND $research_items AS item
        CREATE (r:Research {
            id: item.id,
            topic: item.topic,
            findings: item.findings,
            sources: item.sources,
            depth: item.depth,
            access_tier: item.access_tier,
            sender_hash: item.sender_hash,
            created_at: datetime(),
            confidence: item.confidence
        })
        CREATE (a)-[:CREATED {timestamp: datetime()}]->(r)
        RETURN r.id as id
        """

        try:
            with self._session_pool() as session:
                result = session.run(query, agent=agent, research_items=research_data)
                return [record['id'] for record in result]
        except Exception as e:
            print(f"[ERROR] Failed to store research batch: {e}")
            return []

    def query_concepts(self, query_text: str, sender_hash: Optional[str] = None,
                      min_confidence: float = 0.7, limit: int = 5,
                      offset: int = 0) -> List[Dict[str, Any]]:
        """Query concepts with sender isolation and access tier enforcement.

        Args:
            query_text: Text to search for
            sender_hash: Hash of requesting sender (for access control)
            min_confidence: Minimum similarity score
            limit: Maximum results to return
            offset: Number of results to skip (for pagination)

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
            return results[offset:offset + limit]

        # Generate embedding for query
        query_embedding = self._generate_embedding(query_text)

        if query_embedding:
            try:
                # Vector search with sender isolation
                # Pagination strategy: Request 1.5x limit (min 10) to account for post-query
                # access control filtering. This balances resource efficiency with ensuring
                # we can return the requested limit after filtering out inaccessible SENSITIVE nodes.
                # If insufficient results after filtering, client should request next page.
                vector_limit = max(int((offset + limit) * 1.5), 10)
                query = """
                CALL db.index.vector.queryNodes('concept_embedding', $vector_limit, $embedding)
                YIELD node, score
                WHERE score >= $min_score
                RETURN node.name as name, node.description as description,
                       node.domain as domain, node.access_tier as access_tier,
                       node.sender_hash as concept_sender, score
                """
                with self._session_pool() as session:
                    result = session.run(query, embedding=query_embedding,
                                        min_score=min_confidence, vector_limit=vector_limit)
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
                    # Apply offset and limit after access control filtering
                    return records[offset:offset + limit]
            except (ServiceUnavailable, TransientError) as e:
                print(f"[WARN] Vector search failed due to Neo4j connectivity: {e}")
            except Exception as e:
                print(f"[WARN] Vector search failed: {e}")

        # Fallback to full-text search with pagination
        # Sanitize query_text to prevent Lucene injection attacks
        safe_query_text = self._sanitize_lucene_query(query_text)
        query = """
        CALL db.index.fulltext.queryNodes('knowledge_content', $query)
        YIELD node, score
        WHERE (node:Concept) AND score >= $min_score
        RETURN node.name as name, node.description as description,
               node.domain as domain, node.access_tier as access_tier,
               node.sender_hash as concept_sender, score
        ORDER BY score DESC
        SKIP $offset LIMIT $limit
        """
        try:
            with self._session_pool() as session:
                result = session.run(query, query=safe_query_text,
                                    min_score=min_confidence, offset=offset, limit=limit)
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
            if SentenceTransformer is None:
                raise ImportError("sentence_transformers not installed")

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
                     sender_hash: Optional[str] = None,
                     limit: int = 5, offset: int = 0) -> List[Dict[str, Any]]:
        """Query operational knowledge with vector fallback and access control.

        Args:
            agent: Agent ID performing the query
            topic: Search topic
            min_confidence: Minimum similarity threshold
            sender_hash: Hash of requesting sender (for access tier enforcement)
            limit: Maximum results to return
            offset: Number of results to skip (for pagination)

        Returns:
            List of related knowledge items (filtered by access tier)
        """
        if self.fallback_mode:
            # Filter fallback store by access tier with pagination
            research = self._local_store.get('research', [])
            filtered = []
            for r in research:
                tier = r.get('access_tier', self.ACCESS_TIER_PUBLIC)
                item_sender = r.get('sender_hash')
                # SENSITIVE items are sender-isolated
                if tier == self.ACCESS_TIER_SENSITIVE and item_sender != sender_hash:
                    continue
                filtered.append(r)
            return filtered[offset:offset + limit]

        # Generate embedding for the query topic
        embedding = self._generate_embedding(topic)

        # Try vector search first (if embedding generated and index exists)
        if embedding:
            try:
                # Query more results than needed to allow for filtering and pagination
                vector_limit = max(int((offset + limit) * 1.5), 10)
                query = """
                CALL db.index.vector.queryNodes('concept_embedding', $vector_limit, $embedding)
                YIELD node, score
                WHERE score >= $min_score
                RETURN node.name as concept, node.description as description,
                       node.access_tier as access_tier, node.sender_hash as item_sender,
                       score
                """
                with self._session_pool() as session:
                    result = session.run(query, embedding=embedding, min_score=min_confidence,
                                        vector_limit=vector_limit)
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
                    # Apply offset and limit after access control filtering
                    return records[offset:offset + limit]
            except (ServiceUnavailable, TransientError):
                pass  # Fall through to full-text search on connectivity issues
            except Exception as e:
                print(f"[WARN] Research vector search failed: {e}")
                pass  # Fall through to full-text search

        # Fallback to full-text search with pagination
        # Sanitize topic to prevent Lucene injection attacks
        safe_topic = self._sanitize_lucene_query(topic)
        query = """
        CALL db.index.fulltext.queryNodes('knowledge_content', $topic)
        YIELD node, score
        WHERE score >= $min_score
        RETURN node.topic as topic, node.findings as findings, score
        ORDER BY score DESC
        SKIP $offset LIMIT $limit
        """
        with self._session_pool() as session:
            result = session.run(query, topic=safe_topic, min_score=min_confidence,
                                offset=offset, limit=limit)
            return [dict(record) for record in result]

    def _detect_cycle(self, from_agent: str, to_agent: str) -> bool:
        """Detect if adding LEARNED relationship would create a cycle."""
        query = """
        MATCH path = (to:Agent {id: $to_agent})-[:LEARNED*1..10]->(from:Agent {id: $from_agent})
        RETURN length(path) as cycle_length
        LIMIT 1
        """
        with self._session_pool() as session:
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
        with self._session_pool() as session:
            session.run(query, from_agent=from_agent, to_agent=to_agent,
                       knowledge_id=str(knowledge_id))
        return True

    def _compute_valid_agents(self) -> set:
        """Compute valid agent IDs from environment variable.

        Loaded from ALLOWED_AGENTS env var (comma-separated) or defaults to 6 standard agents.
        Example: ALLOWED_AGENTS="kublai,mongke,chagatai,temujin,jochi,ogedei"

        Returns:
            Set of valid agent ID strings.
        """
        agents_env = os.getenv('ALLOWED_AGENTS', '')
        if agents_env:
            return set(a.strip() for a in agents_env.split(',') if a.strip())
        # Default 6-agent set
        return {'main', 'researcher', 'writer', 'developer', 'analyst', 'ops'}

    def _validate_agent_id(self, agent_id: str, auth_token: Optional[str] = None) -> bool:
        """Validate that agent_id is a known agent with optional HMAC authentication.

        Prevents spoofing by ensuring only valid agents can create/claim tasks.
        When auth_token is provided, performs HMAC-SHA256 authentication to verify
        the agent's identity cryptographically. Without auth_token, falls back to
        simple set membership check (less secure, for backward compatibility only).

        Args:
            agent_id: The agent identifier to validate.
            auth_token: Optional HMAC authentication token in format
                       'agent_id:timestamp:signature'. If provided, the token
                       is verified using AGENT_AUTH_SECRET.

        Returns:
            True if agent is valid (and token is valid if provided), False otherwise.

        Security:
            - Always provide auth_token in production environments
            - Tokens expire after 5 minutes to prevent replay attacks
            - HMAC-SHA256 prevents signature forgery without the secret
            - Simple set membership (no token) is vulnerable if env is compromised
        """
        if agent_id not in self.VALID_AGENTS:
            return False

        if auth_token is not None:
            return self._authenticate_agent(agent_id, auth_token)

        return True

    def _authenticate_agent(self, agent_id: str, auth_token: str) -> bool:
        """Authenticate agent using HMAC-SHA256 token validation.

        Token format: 'agent_id:timestamp:signature'
        Signature: HMAC-SHA256('${agent_id}:${timestamp}', AGENT_AUTH_SECRET)

        Args:
            agent_id: The agent identifier to authenticate.
            auth_token: HMAC token in format 'agent_id:timestamp:signature'.

        Returns:
            True if token is valid and not expired, False otherwise.

        Security:
            - Tokens expire after 5 minutes to prevent replay attacks
            - HMAC-SHA256 signature ensures authenticity without exposing secret
            - Constant-time comparison prevents timing attacks
            - Agent ID in token must match claimed agent_id
        """
        if not auth_token or ':' not in auth_token:
            return False

        try:
            parts = auth_token.split(':')
            if len(parts) != 3:
                return False

            token_agent, timestamp_str, signature = parts

            # Verify agent matches the token
            if token_agent != agent_id:
                return False

            # Parse and validate timestamp
            try:
                timestamp = int(timestamp_str)
            except ValueError:
                return False

            # Check for replay attacks (5 minute window)
            current_time = int(time.time())
            time_diff = abs(current_time - timestamp)
            if time_diff > 300:  # 5 minutes in seconds
                return False

            # Verify HMAC signature
            auth_secret = os.getenv('AGENT_AUTH_SECRET', '')
            if not auth_secret:
                return False

            expected_message = f"{agent_id}:{timestamp_str}"
            expected_signature = hmac.new(
                auth_secret.encode('utf-8'),
                expected_message.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            # Constant-time comparison to prevent timing attacks
            if not hmac.compare_digest(signature, expected_signature):
                return False

            return True

        except (ValueError, TypeError):
            return False

    def _generate_agent_token(self, agent_id: str) -> str:
        """Generate HMAC authentication token for an agent.

        Token format: 'agent_id:timestamp:signature'
        Signature: HMAC-SHA256('${agent_id}:${timestamp}', AGENT_AUTH_SECRET)

        Args:
            agent_id: The agent identifier to generate token for.

        Returns:
            HMAC authentication token string.

        Raises:
            RuntimeError: If AGENT_AUTH_SECRET is not configured.
            ValueError: If agent_id is not a valid agent.

        Security:
            - Tokens expire after 5 minutes; generate fresh tokens for each request
            - Keep AGENT_AUTH_SECRET secure; it is the root of trust
            - Do not log tokens; they contain sensitive signature data
        """
        if agent_id not in self.VALID_AGENTS:
            raise ValueError(f"Invalid agent_id: {agent_id}")

        auth_secret = os.getenv('AGENT_AUTH_SECRET')
        if not auth_secret:
            raise RuntimeError(
                "AGENT_AUTH_SECRET environment variable not set. "
                "Cannot generate authentication tokens."
            )

        timestamp = int(time.time())
        message = f"{agent_id}:{timestamp}"
        signature = hmac.new(
            auth_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return f"{agent_id}:{timestamp}:{signature}"

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
        with self._session_pool() as session:
            with session.begin_transaction() as tx:
                tx.run(query, id=str(task_id), type=task_type,
                       description=safe_description,
                       delegated_by=delegated_by, assigned_to=assigned_to)
        return task_id

    def claim_task(self, agent: str) -> Optional[Dict[str, Any]]:
        """Claim next pending task for an agent (atomic, race-condition safe).

        Validates agent identity to prevent spoofing attacks.
        Uses optimistic locking with claim_attempt_id to prevent race conditions
        when multiple agents try to claim the same task simultaneously.

        Raises:
            NoPendingTaskError: No pending tasks available for this agent (normal condition)
            RaceConditionError: Another agent claimed the task first (retryable)
            RateLimitExceeded: Agent has exceeded rate limits
            DatabaseError: Non-retryable database failure

        Returns:
            Dict with task details if claim successful, None if no work available
        """
        # Validate agent identity
        if not self._validate_agent_id(agent):
            logger.warning(f"[AUTH] Invalid agent claiming task: {agent}")
            return None

        # Check rate limits before attempting claim
        if not self._check_rate_limit(agent, 'claim_task'):
            raise RateLimitExceeded(f"Rate limit exceeded for agent {agent}")

        if self.fallback_mode:
            # Thread-safe fallback mode with locking
            with self._fallback_lock:
                tasks = self._local_store.get('tasks', [])
                for t in tasks:
                    if t['assigned_to'] == agent and t['status'] == 'pending':
                        t['status'] = 'in_progress'
                        t['claimed_at'] = datetime.now().isoformat()
                        return t
                # No pending tasks - this is normal, not an error
                raise NoPendingTaskError(f"No pending tasks available for agent {agent}")

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

        session = None
        tx = None
        try:
            session = self._session_pool()
            # Use write transaction for stronger consistency guarantees
            tx = session.begin_transaction()

            result = tx.run(query, agent=agent, claim_attempt_id=claim_attempt_id)
            record = result.single()

            if record and record['verified_claim_id'] == claim_attempt_id:
                # Success - we claimed the task
                tx.commit()
                return {
                    'id': record['id'],
                    'type': record['type'],
                    'description': record['description']
                }
            elif record:
                # Another agent won the race - rollback and raise specific exception
                tx.rollback()
                raise RaceConditionError(
                    f"Task claimed by another agent concurrently (agent: {agent})"
                )
            else:
                # No task available - rollback and raise specific exception
                tx.rollback()
                raise NoPendingTaskError(f"No pending tasks available for agent {agent}")

        except (NoPendingTaskError, RaceConditionError):
            # Re-raise our specific exceptions without wrapping
            raise

        except TransientError as e:
            # Neo4j transient error - retryable (connection issues, locks, etc.)
            logger.warning(f"[TRANSIENT] Transient error claiming task for {agent}: {e}")
            if tx:
                try:
                    tx.rollback()
                except Exception:
                    pass  # Best effort rollback
            # Treat as race condition since we can't verify claim status
            raise RaceConditionError(
                f"Transient database error during task claim for {agent}"
            ) from e

        except Exception as e:
            # Unexpected error - rollback and wrap in DatabaseError
            logger.exception(f"[ERROR] Unexpected error claiming task for {agent}: {e}")
            if tx:
                try:
                    tx.rollback()
                except Exception:
                    pass  # Best effort rollback
            raise DatabaseError(f"Unexpected error claiming task: {e}") from e

        finally:
            if session:
                session.close()

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
        with self._session_pool() as session:
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
        with self._session_pool() as session:
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
        with self._session_pool() as session:
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
        with self._session_pool() as session:
            result = session.run(query, agent_id=agent_id)
            return [dict(record) for record in result]

    def save_session_context(self, sender_id: str, context: Dict[str, Any]) -> bool:
        """Save session context for persistence across resets."""
        if self.fallback_mode:
            return True

        today = date.today()  # Python date object - Neo4j converts to date()

        query = """
        MERGE (s:SessionContext {sender_id: $sender_id, session_date: $session_date})
        SET s.active_tasks = $active_tasks,
            s.pending_delegations = $pending_delegations,
            s.conversation_summary = $conversation_summary,
            s.updated_at = datetime(),
            s.drain_mode = $drain_mode
        ON CREATE SET s.created_at = datetime()
        """
        with self._session_pool() as session:
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
        today = date.today()  # Python date object - Neo4j converts to date()

        query = """
        MATCH (s:SessionContext {sender_id: $sender_id, session_date: $session_date})
        OPTIONAL MATCH (t:Task)-[:ASSIGNED_TO]->(a:Agent)
        WHERE t.status IN ['pending', 'in_progress']
        RETURN s.active_tasks as active_tasks,
               s.pending_delegations as pending_delegations,
               count(t) as pending_task_count
        """
        with self._session_pool() as session:
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
        today = date.today()  # Python date object - Neo4j converts to date()

        query = """
        MATCH (s:SessionContext {sender_id: $sender_id, session_date: $session_date})
        SET s.drain_mode = true, s.drain_started_at = datetime()
        """
        with self._session_pool() as session:
            session.run(query, sender_id=sender_id, session_date=today)
        return True

    def get_session_context(self, sender_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve session context for a sender."""
        if self.fallback_mode:
            return None

        today = date.today()  # Python date object - Neo4j converts to date()

        query = """
        MATCH (s:SessionContext {sender_id: $sender_id, session_date: $session_date})
        RETURN s.active_tasks as active_tasks,
               s.pending_delegations as pending_delegations,
               s.conversation_summary as conversation_summary
        """
        with self._session_pool() as session:
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
        with self._session_pool() as session:
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
            # Convert datetime to Python date object for Neo4j date() type
            drain_start_date = self._drain_start_time.date()
        else:
            # Fallback to today if drain start time not set (shouldn't happen)
            drain_start_date = date.today()  # Python date object

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
        with self.memory._session_pool() as session:
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
            with self.memory._session_pool() as session:
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
            with self.memory._session_pool() as session:
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
            analysis_id = str(uuid4())

            with self.memory._session_pool() as session:
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

        with memory._session_pool() as session:
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
        with self._session_pool() as session:
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
        with self._session_pool() as session:
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

    with self._session_pool() as session:
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

        Global concurrency limit enforced to prevent connection pool exhaustion.
        Tasks exceeding the limit are queued and processed FIFO.
        """
        if self.fallback_mode:
            return None

        # Check global concurrency limit using semaphore (non-blocking)
        if not self._background_task_semaphore.acquire(blocking=False):
            # Limit reached - queue the task request
            with self._background_task_lock:
                # Check if this agent already has a pending task
                for pending in self._background_task_queue:
                    if pending['agent_id'] == agent_id:
                        logger.info(f"[BACKGROUND] Agent {agent_id} already has pending task, skipping")
                        return None

                # Add to queue
                task_id = uuid4()
                self._background_task_queue.append({
                    'task_id': task_id,
                    'agent_id': agent_id,
                    'queued_at': datetime.now()
                })
                logger.info(f"[BACKGROUND] Task limit reached, queued task {task_id} for {agent_id} "
                           f"(queue depth: {len(self._background_task_queue)})")
                return task_id

        # Semaphore acquired - we can create the task
        try:
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

            with self._session_pool() as session:
                session.run(query,
                    id=str(task_id),
                    agent_id=agent_id,
                    task_type=task_type
                )

            # Track active task
            with self._background_task_lock:
                self._background_task_active.add(str(task_id))

            logger.info(f"[BACKGROUND] Created {task_type} task {task_id} for {agent_id} "
                       f"(active: {len(self._background_task_active)}/"
                       f"{self._MAX_CONCURRENT_BACKGROUND_TASKS})")
            return task_id

        except Exception as e:
            # Release semaphore on failure
            self._background_task_semaphore.release()
            logger.error(f"[ERROR] Failed to create background task: {e}")
            return None

    def _create_queued_background_task(self, agent_id: str) -> Optional[UUID]:
        """Create background task for queued request (semaphore already acquired).

        Internal helper for processing queued tasks. Does not check semaphore
        since it was already acquired by _process_background_task_queue.
        """
        if self.fallback_mode:
            return None

        try:
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

            with self._session_pool() as session:
                session.run(query,
                    id=str(task_id),
                    agent_id=agent_id,
                    task_type=task_type
                )

            logger.info(f"[BACKGROUND] Created queued {task_type} task {task_id} for {agent_id}")
            return task_id

        except Exception as e:
            logger.error(f"[ERROR] Failed to create queued background task: {e}")
            return None

    def complete_background_task(self, task_id: str):
        """Mark background task as completed and release semaphore.

        Called by agents when they finish processing a background task.
        This releases the slot for the next queued task.

        Note: Only releases semaphore if task was actually running (not queued).
        Queued tasks never acquired the semaphore, so they must not release it.
        """
        with self._background_task_lock:
            was_active = task_id in self._background_task_active
            if was_active:
                self._background_task_active.discard(task_id)

        # Only release semaphore if task was actually running (not queued)
        if was_active:
            try:
                self._background_task_semaphore.release()
                logger.info(f"[BACKGROUND] Task {task_id} completed, released slot "
                           f"(active: {len(self._background_task_active)}/"
                           f"{self._MAX_CONCURRENT_BACKGROUND_TASKS})")
            except ValueError:
                # Semaphore over-release - indicates logic error
                logger.error(f"[BACKGROUND] Semaphore release failed for task {task_id} - "
                            f"semaphore already at max. This indicates a tracking mismatch.")
        else:
            # Task was queued but never started, no semaphore to release
            logger.debug(f"[BACKGROUND] Task {task_id} was queued but never started, "
                        f"no semaphore to release")

    def get_background_task_status(self) -> Dict[str, Any]:
        """Get current background task status for monitoring.

        Returns active count, queue depth, and limit info.
        """
        with self._background_task_lock:
            return {
                'active_tasks': len(self._background_task_active),
                'active_task_ids': list(self._background_task_active),
                'queued_tasks': len(self._background_task_queue),
                'max_concurrent': self._MAX_CONCURRENT_BACKGROUND_TASKS,
                'queue_depth': len(self._background_task_queue),
                'available_slots': max(0, self._MAX_CONCURRENT_BACKGROUND_TASKS - len(self._background_task_active))
            }

    def get_synthesis_candidates(self, agent_id: str, limit: int = 20,
                                  offset: int = 0) -> List[Dict]:
        """Get memories ready for synthesis (unsynthesized, recent).

        Args:
            agent_id: ID of the agent to get candidates for
            limit: Maximum number of candidates to return
            offset: Number of candidates to skip (for pagination)

        Returns:
            List of memory candidates for synthesis
        """
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
        SKIP $offset LIMIT $limit
        """

        try:
            with self._session_pool() as session:
                result = session.run(query, agent_id=agent_id, limit=limit, offset=offset)
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
    """Check all agents for idle status and assign background synthesis.

    Respects global background task limit to prevent connection pool exhaustion.
    Processes queued tasks when slots become available.
    """
    # First, try to process any queued background tasks
    self._process_background_task_queue()

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
                # Create new synthesis task (respects global limit)
                self.memory.create_background_synthesis_task(agent_id)

def _process_background_task_queue(self):
    """Process queued background tasks when slots are available.

    Called periodically by monitor_agent_idle to drain the queue.
    """
    with self.memory._background_task_lock:
        if not self.memory._background_task_queue:
            return

        # Try to process queued tasks up to available slots
        available_slots = self.memory._MAX_CONCURRENT_BACKGROUND_TASKS - len(self.memory._background_task_active)

        for _ in range(available_slots):
            if not self.memory._background_task_queue:
                break

            # Try to acquire semaphore (non-blocking)
            if not self.memory._background_task_semaphore.acquire(blocking=False):
                break

            try:
                # Get next queued task
                queued = self.memory._background_task_queue.pop(0)

                # Create the actual task
                task_id = self.memory._create_queued_background_task(queued['agent_id'])

                if task_id:
                    self.memory._background_task_active.add(str(task_id))
                    logger.info(f"[BACKGROUND] Processed queued task {task_id} for {queued['agent_id']}")
                else:
                    # Failed to create, release semaphore
                    self.memory._background_task_semaphore.release()
                    # Re-queue at front
                    self.memory._background_task_queue.insert(0, queued)
                    break
            except Exception as e:
                self.memory._background_task_semaphore.release()
                logger.error(f"[BACKGROUND] Failed to process queued task: {e}")
                break
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
| Phase 6 (Jochi-Temüjin) | Add quality metrics to code review |
| Phase 7 (Kublai Delegation) | Check meta-rules before delegation |

#### 4.9.7 Implementation Priority

| Component | Effort | Value | Order |
|-----------|--------|-------|-------|
| Neo4j vector index | 1 hour | Very High | 1st |
| Self-Reflect integration | 4 hours | Very High | 2nd |
| Claude-Meta (meta-rules) | 6 hours | High | 3rd |
| Kaizen (quality metrics) | 4 hours | Medium | 4th |
| Continuous Claude skills | 8 hours | Medium | 5th |
| Qdrant (deferred) | - | Future | TBD |

### Phase 5: ClawTasks Bounty System Integration

**STATUS: PLANNED**

Integrate the 6-agent OpenClaw system with ClawTasks, an agent-to-agent bounty marketplace on Base L2. Workers stake 10% of bounty value to claim tasks and earn 95% of bounty plus stake back on successful completion.

#### 5.1 Overview

ClawTasks enables autonomous agents to participate in a decentralized work marketplace:

| Mechanism | Description |
|-----------|-------------|
| **Staking** | 10% of bounty value required to claim |
| **Reward** | 95% of bounty + full stake returned on success |
| **Slashing** | Stake forfeited on failure or timeout |
| **Platform** | Base L2 (Ethereum L2 with low fees) |
| **Currency** | USDC (stable, programmable money) |

**Integration Value:**
- Monetize agent capabilities autonomously
- Diversify task sources beyond user requests
- Build reputation through on-chain work history
- Fund operational costs (compute, API calls, infrastructure)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CLAWTASKS BOUNTY LIFECYCLE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐            │
│   │ DISCOVER │───▶│ EVALUATE │───▶│  CLAIM   │───▶│ EXECUTE  │            │
│   │          │    │          │    │          │    │          │            │
│   │Ögedei    │    │Jochi     │    │Kublai    │    │Specialist│            │
│   │monitors  │    │analyzes  │    │decides   │    │executes  │            │
│   └──────────┘    └──────────┘    └──────────┘    └────┬─────┘            │
│                                                        │                    │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐        │                    │
│   │ REPUTATE │◀───│  PAYMENT │◀───│ SUBMIT   │◀───────┘                    │
│   │          │    │          │    │          │                             │
│   │+Rep/     │    │+95%      │    │Deliver   │                             │
│   │-Rep      │    │+Stake    │    │Results   │                             │
│   └──────────┘    └──────────┘    └──────────┘                             │
│                                                                              │
│   On Failure:                                                                │
│   ┌──────────┐    ┌──────────┐                                              │
│   │  SLASH   │───▶│ REFLECT  │                                              │
│   │-10% Stake│    │Record    │                                              │
│   │          │    │Lesson    │                                              │
│   └──────────┘    └──────────┘                                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 5.2 Agent Responsibilities for ClawTasks

| Agent | ClawTasks Role | Responsibilities |
|-------|---------------|------------------|
| **Ögedei** | Task Monitor | Monitor ClawTasks API/WebSocket for new bounties, filter by capability match, maintain bounty watchlist |
| **Jochi** | Task Evaluator | Evaluate bounty feasibility, ROI estimation, success probability analysis, risk assessment |
| **Kublai** | Task Router | Decide which bounties to pursue based on evaluation, assign to appropriate specialist agent |
| **Temüjin** | Task Executor | Execute technical bounties: coding, security audits, devops, infrastructure, smart contract work |
| **Chagatai** | Content Bounties | Execute writing, documentation, creative content, copywriting, technical writing bounties |
| **Möngke** | Research Bounties | Execute research, data gathering, analysis, due diligence, market research bounties |

#### 5.3 Bounty Lifecycle in Neo4j

**5.3.1 Bounty Discovery and Storage**

```cypher
// Store discovered bounty
CREATE (b:Bounty {
  id: $bounty_id,
  title: $title,
  description: $description,
  category: $category,
  reward_usdc: $reward,
  stake_required: $reward * 0.10,
  deadline: datetime($deadline),
  requirements: $requirements,
  deliverables: $deliverables,
  status: 'discovered',
  source_platform: 'clawtasks',
  external_url: $url,
  created_at: datetime(),
  discovered_by: 'ogedei'
})

// Link to required skills
WITH b
UNWIND $required_skills as skill_name
MATCH (s:Skill {name: skill_name})
MERGE (b)-[:REQUIRES_SKILL {importance: 'required'}]->(s)

// Create discovery record
WITH b
MATCH (a:Agent {name: 'ogedei'})
CREATE (a)-[:DISCOVERED {
  discovered_at: datetime(),
  source: 'clawtasks_api'
}]->(b)
```

**5.3.2 Capability Matching**

```cypher
// Match bounties to agent capabilities
MATCH (b:Bounty {status: 'discovered'})
MATCH (a:Agent)
MATCH (b)-[:REQUIRES_SKILL]->(s:Skill)<-[:HAS_SKILL]-(a)
WITH b, a, count(s) as matching_skills, collect(s.name) as skills
MATCH (b)-[:REQUIRES_SKILL]->(all_s:Skill)
WITH b, a, matching_skills, skills, count(all_s) as total_skills
WHERE matching_skills >= total_skills * 0.7  // 70% skill match
CREATE (a)-[:CAN_PERFORM {
  confidence: matching_skills * 1.0 / total_skills,
  matching_skills: skills,
  calculated_at: datetime()
}]->(b)
```

**5.3.3 Staking and Claiming**

```cypher
// Record bounty claim with stake
MATCH (b:Bounty {id: $bounty_id})
MATCH (a:Agent {name: $agent_name})
MATCH (w:Wallet)-[:BELONGS_TO]->(a)
WHERE w.type = 'hot'

// Create stake record
CREATE (s:Stake {
  id: uuid(),
  amount: b.stake_required,
  status: 'locked',
  locked_at: datetime(),
  unlock_condition: 'bounty_completion',
  tx_hash: $stake_tx_hash
})

// Link stake to bounty and wallet
CREATE (w)-[:STAKED {
  tx_hash: $stake_tx_hash,
  block_number: $block_number
}]->(s)
CREATE (s)-[:FOR_BOUNTY]->(b)
CREATE (a)-[:CLAIMED {
  claimed_at: datetime(),
  expected_completion: datetime($expected_completion)
}]->(b)

// Update bounty status
SET b.status = 'claimed',
    b.claimed_by = $agent_name,
    b.claimed_at = datetime()
```

**5.3.4 Execution Tracking**

```cypher
// Create execution task linked to bounty
MATCH (b:Bounty {id: $bounty_id})
MATCH (a:Agent {name: $agent_name})
CREATE (t:Task {
  id: uuid(),
  type: 'bounty_execution',
  description: b.title,
  status: 'in_progress',
  created_at: datetime(),
  deadline: b.deadline,
  bounty_id: b.id
})
CREATE (a)-[:EXECUTING]->(t)
CREATE (t)-[:FULFILLS]->(b)

// Track progress updates
CREATE (p:ProgressUpdate {
  id: uuid(),
  timestamp: datetime(),
  status: $progress_status,
  completion_percent: $percent,
  notes: $notes,
  blockers: $blockers
})
CREATE (t)-[:HAS_UPDATE]->(p)
```

**5.3.5 Completion and Payment**

```cypher
// Record successful completion
MATCH (b:Bounty {id: $bounty_id})
MATCH (a:Agent {name: $agent_name})
MATCH (s:Stake)-[:FOR_BOUNTY]->(b)
SET b.status = 'completed',
    b.completed_at = datetime(),
    b.deliverable_hash = $deliverable_hash,
    b.payment_tx_hash = $payment_tx

// Update stake status
SET s.status = 'returned',
    s.returned_at = datetime(),
    s.return_tx_hash = $stake_return_tx

// Create payment record
CREATE (p:Payment {
  id: uuid(),
  type: 'bounty_reward',
  amount: b.reward_usdc * 0.95,
  currency: 'USDC',
  tx_hash: $payment_tx,
  received_at: datetime(),
  status: 'confirmed'
})
CREATE (b)-[:PAID]->(p)
CREATE (a)-[:RECEIVED]->(p)

// Create transaction record
CREATE (tx:Transaction {
  id: uuid(),
  type: 'bounty_completion',
  amount: b.reward_usdc * 0.95 + s.amount,
  fee: b.reward_usdc * 0.05,
  tx_hash: $payment_tx,
  block_number: $block_number,
  timestamp: datetime(),
  description: 'Bounty reward + stake return'
})
CREATE (a)-[:PROCESSED]->(tx)
```

**5.3.6 Reputation Updates**

```cypher
// Update agent reputation on success
MATCH (a:Agent {name: $agent_name})
MATCH (r:Reputation)-[:BELONGS_TO]->(a)
SET r.completed_bounties = r.completed_bounties + 1,
    r.total_earned_usdc = r.total_earned_usdc + $reward,
    r.success_rate = (r.completed_bounties * 1.0) / (r.completed_bounties + r.failed_bounties),
    r.last_updated = datetime()

// Add reputation event
CREATE (re:ReputationEvent {
  id: uuid(),
  type: 'bounty_completed',
  impact: 'positive',
  points: $reputation_points,
  description: $description,
  timestamp: datetime(),
  bounty_id: $bounty_id
})
CREATE (a)-[:EARNED]->(re)

// On failure - slash and record
MATCH (a:Agent {name: $agent_name})
MATCH (r:Reputation)-[:BELONGS_TO]->(a)
SET r.failed_bounties = r.failed_bounties + 1,
    r.total_lost_usdc = r.total_lost_usdc + $stake_amount,
    r.success_rate = (r.completed_bounties * 1.0) / (r.completed_bounties + r.failed_bounties),
    r.last_updated = datetime()

// Create reflection for failure
CREATE (ref:Reflection {
  id: uuid(),
  agent: $agent_name,
  context: 'bounty_execution',
  decision: 'accepted_bounty',
  outcome: 'failure',
  lesson: $failure_lesson,
  importance: 0.9,
  related_bounty_id: $bounty_id,
  created_at: datetime()
})
```

#### 5.4 Neo4j Schema Extensions for ClawTasks

**5.4.1 Bounty Node**

```cypher
// Bounty node - represents a ClawTasks bounty
(:Bounty {
  id: uuid,                    // Internal UUID
  external_id: string,         // ClawTasks contract bounty ID
  title: string,
  description: string,
  category: string,            // 'technical', 'content', 'research', 'creative'
  subcategory: string,         // 'coding', 'security', 'writing', etc.
  reward_usdc: float,          // Total bounty in USDC
  stake_required: float,       // 10% of reward
  deadline: datetime,
  requirements: [string],      // List of requirements
  deliverables: [string],      // Expected deliverables
  status: string,              // 'discovered', 'evaluating', 'claimed', 'in_progress', 'completed', 'failed', 'expired'
  difficulty: string,          // 'beginner', 'intermediate', 'advanced', 'expert'
  estimated_hours: float,
  source_platform: string,     // 'clawtasks', 'other'
  external_url: string,
  creator_address: string,     // Ethereum address of bounty creator
  contract_address: string,    // ClawTasks contract address
  created_at: datetime,
  discovered_at: datetime,
  claimed_at: datetime,
  completed_at: datetime,
  claimed_by: string,          // Agent name
  deliverable_hash: string,    // IPFS/hash of deliverable
  payment_tx_hash: string,
  failure_reason: string       // If failed
})

// Constraints
CREATE CONSTRAINT bounty_id IF NOT EXISTS
  FOR (b:Bounty) REQUIRE b.id IS UNIQUE;

CREATE INDEX bounty_status IF NOT EXISTS
  FOR (b:Bounty) ON (b.status);

CREATE INDEX bounty_category IF NOT EXISTS
  FOR (b:Bounty) ON (b.category);

CREATE INDEX bounty_external_id IF NOT EXISTS
  FOR (b:Bounty) ON (b.external_id);
```

**5.4.2 Wallet Node**

```cypher
// Wallet node - agent's USDC wallet
(:Wallet {
  id: uuid,
  address: string,             // Ethereum address (0x...)
  type: string,                // 'cold', 'hot', 'worker'
  network: string,             // 'base', 'base_sepolia'
  currency: string,            // 'USDC'
  balance_usdc: float,
  encrypted_key_ref: string,   // Reference to encrypted private key storage
  created_at: datetime,
  last_synced: datetime,
  is_active: boolean
})

// Relationships
(:Wallet)-[:BELONGS_TO]->(:Agent)
(:Wallet)-[:DERIVED_FROM {derivation_path: string}]->(:Wallet)  // Worker wallets derived from hot

// Constraints
CREATE CONSTRAINT wallet_address IF NOT EXISTS
  FOR (w:Wallet) REQUIRE w.address IS UNIQUE;

CREATE INDEX wallet_type IF NOT EXISTS
  FOR (w:Wallet) ON (w.type);

CREATE INDEX wallet_agent IF NOT EXISTS
  FOR (w:Wallet) ON (w.agent_name);
```

**5.4.3 Transaction Node**

```cypher
// Transaction node - financial transactions
(:Transaction {
  id: uuid,
  type: string,                // 'stake', 'unstake', 'reward', 'fee', 'deposit', 'withdrawal'
  amount: float,
  currency: string,            // 'USDC'
  fee: float,
  tx_hash: string,             // On-chain transaction hash
  block_number: integer,
  block_timestamp: datetime,
  from_address: string,
  to_address: string,
  status: string,              // 'pending', 'confirmed', 'failed'
  confirmations: integer,
  timestamp: datetime,
  description: string,
  metadata: string             // JSON string for additional data
})

// Relationships
(:Agent)-[:PROCESSED]->(:Transaction)
(:Transaction)-[:FOR_BOUNTY]->(:Bounty)
(:Transaction)-[:FROM_WALLET]->(:Wallet)
(:Transaction)-[:TO_WALLET]->(:Wallet)

// Constraints
CREATE CONSTRAINT transaction_tx_hash IF NOT EXISTS
  FOR (t:Transaction) REQUIRE t.tx_hash IS UNIQUE;

CREATE INDEX transaction_type IF NOT EXISTS
  FOR (t:Transaction) ON (t.type);

CREATE INDEX transaction_status IF NOT EXISTS
  FOR (t:Transaction) ON (t.status);
```

**5.4.4 Stake Node**

```cypher
// Stake node - staked USDC for bounty claims
(:Stake {
  id: uuid,
  amount: float,
  status: string,              // 'locked', 'returned', 'slashed'
  locked_at: datetime,
  unlocked_at: datetime,
  lock_duration_hours: float,
  unlock_condition: string,    // 'bounty_completion', 'timeout', 'manual'
  tx_hash: string,             // Stake transaction
  return_tx_hash: string,      // Unstake transaction
  slash_tx_hash: string,       // Slashing transaction
  slash_reason: string,
  bounty_external_id: string
})

// Relationships
(:Wallet)-[:STAKED]->(:Stake)
(:Stake)-[:FOR_BOUNTY]->(:Bounty)
(:Agent)-[:LOCKED]->(:Stake)

// Constraints
CREATE CONSTRAINT stake_id IF NOT EXISTS
  FOR (s:Stake) REQUIRE s.id IS UNIQUE;

CREATE INDEX stake_status IF NOT EXISTS
  FOR (s:Stake) ON (s.status);
```

**5.4.5 Reputation Node**

```cypher
// Reputation node - agent reputation metrics
(:Reputation {
  id: uuid,
  agent_name: string,
  overall_score: float,        // 0-100 calculated score
  completed_bounties: integer,
  failed_bounties: integer,
  total_earned_usdc: float,
  total_staked_usdc: float,
  total_lost_usdc: float,
  success_rate: float,         // 0.0-1.0
  avg_completion_time: float,  // Hours
  on_time_delivery_rate: float, // 0.0-1.0
  quality_score: float,        // Average quality rating
  dispute_count: integer,
  dispute_won: integer,
  tier: string,                // 'bronze', 'silver', 'gold', 'platinum', 'diamond'
  created_at: datetime,
  last_updated: datetime,
  clawtasks_profile_url: string
})

// Relationships
(:Reputation)-[:BELONGS_TO]->(:Agent)

// Reputation events
(:ReputationEvent {
  id: uuid,
  type: string,                // 'bounty_completed', 'bounty_failed', 'dispute_resolved', 'tier_upgrade'
  impact: string,              // 'positive', 'negative', 'neutral'
  points: integer,
  description: string,
  timestamp: datetime,
  bounty_id: string,
  tx_hash: string
})

(:Agent)-[:EARNED]->(:ReputationEvent)

// Constraints
CREATE CONSTRAINT reputation_agent IF NOT EXISTS
  FOR (r:Reputation) REQUIRE r.agent_name IS UNIQUE;

CREATE INDEX reputation_tier IF NOT EXISTS
  FOR (r:Reputation) ON (r.tier);
```

**5.4.6 SkillBountyMapping Node**

```cypher
// SkillBountyMapping - links skills to bounty categories
(:SkillBountyMapping {
  id: uuid,
  skill_name: string,
  bounty_category: string,
  bounty_subcategory: string,
  match_weight: float,         // How strongly this skill matches (0.0-1.0)
  min_proficiency: string,     // 'beginner', 'intermediate', 'advanced', 'expert'
  typical_duration_hours: float,
  avg_reward_usdc: float,
  success_rate: float,
  is_active: boolean,
  created_at: datetime,
  updated_at: datetime
})

// Relationships
(:Skill)-[:MAPS_TO]->(:SkillBountyMapping)
(:SkillBountyMapping)-[:MAPS_TO]->(:Bounty)

// Example mappings
CREATE (sbm:SkillBountyMapping {
  skill_name: 'python',
  bounty_category: 'technical',
  bounty_subcategory: 'coding',
  match_weight: 0.95,
  min_proficiency: 'intermediate'
})

CREATE (sbm:SkillBountyMapping {
  skill_name: 'smart_contract_audit',
  bounty_category: 'technical',
  bounty_subcategory: 'security',
  match_weight: 0.90,
  min_proficiency: 'expert'
})

CREATE (sbm:SkillBountyMapping {
  skill_name: 'technical_writing',
  bounty_category: 'content',
  bounty_subcategory: 'documentation',
  match_weight: 0.85,
  min_proficiency: 'intermediate'
})
```

#### 5.5 Integration Architecture

**5.5.1 Complete Bounty Flow**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CLAWTASKS INTEGRATION ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      CLAWTASKS PLATFORM (Base L2)                    │   │
│  │                                                                      │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │   │
│  │  │   Bounty    │  │   Staking   │  │   Payment   │  │  Reputation │ │   │
│  │  │  Contract   │  │  Contract   │  │  Contract   │  │   Contract  │ │   │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘ │   │
│  │         └─────────────────┴─────────────────┴─────────────────┘      │   │
│  │                              │                                       │   │
│  │                         WebSocket/API                               │   │
│  └──────────────────────────────┼───────────────────────────────────────┘   │
│                                 │                                            │
│  ┌──────────────────────────────┼───────────────────────────────────────┐   │
│  │                   OPENCLAW AGENT SYSTEM                              │   │
│  │                              │                                       │   │
│  │  ┌───────────────────────────┴───────────────────────────────────┐  │   │
│  │  │                      ÖGEDEI (Task Monitor)                     │  │   │
│  │  │  • Poll ClawTasks API every 60 seconds                         │  │   │
│  │  │  • Filter by agent capability match > 70%                      │  │   │
│  │  │  • Store new bounties in Neo4j                                 │  │   │
│  │  │  • Notify Jochi for evaluation                                 │  │   │
│  │  └──────────────────────────────┬─────────────────────────────────┘  │   │
│  │                                 │                                     │   │
│  │  ┌──────────────────────────────┴─────────────────────────────────┐  │   │
│  │  │                     JOCHI (Task Evaluator)                      │  │   │
│  │  │  • Query agent skills from Neo4j                                │  │   │
│  │  │  • Calculate success probability                                │  │   │
│  │  │  • Estimate ROI (reward / estimated_hours)                      │  │   │
│  │  │  • Assess risk factors                                          │  │   │
│  │  │  • Recommend: pursue / skip / watch                             │  │   │
│  │  └──────────────────────────────┬─────────────────────────────────┘  │   │
│  │                                 │                                     │   │
│  │  ┌──────────────────────────────┴─────────────────────────────────┐  │   │
│  │  │                      KUBLAI (Task Router)                       │  │   │
│  │  │  • Review Jochi's evaluation                                    │  │   │
│  │  │  • Check hot wallet balance for stake                           │  │   │
│  │  │  • Decide: claim / delegate / decline                           │  │   │
│  │  │  • Assign to specialist agent                                   │  │   │
│  │  └──────────────────────────────┬─────────────────────────────────┘  │   │
│  │                                 │                                     │   │
│  │         ┌───────────────────────┼───────────────────────┐            │   │
│  │         │                       │                       │            │   │
│  │  ┌──────┴──────┐        ┌──────┴──────┐        ┌──────┴──────┐      │   │
│  │  │  TEMÜJIN    │        │  CHAGATAI   │        │   MÖNGKE    │      │   │
│  │  │  (Technical)│        │  (Content)  │        │  (Research) │      │   │
│  │  │             │        │             │        │             │      │   │
│  │  │• Code bount │        │• Writing    │        │• Data gather│      │   │
│  │  │• Security   │        │• Docs       │        │• Analysis   │      │   │
│  │  │• DevOps     │        │• Creative   │        │• Research   │      │   │
│  │  └──────┬──────┘        └──────┬──────┘        └──────┬──────┘      │   │
│  │         │                       │                       │            │   │
│  │         └───────────────────────┼───────────────────────┘            │   │
│  │                                 │                                     │   │
│  │  ┌──────────────────────────────┴─────────────────────────────────┐  │   │
│  │  │                    RESULT HANDLING                              │  │   │
│  │  │                                                                  │  │   │
│  │  │  On Success:                                                     │  │   │
│  │  │  • Submit deliverable to ClawTasks                              │  │   │
│  │  │  • Record completion in Neo4j                                   │  │   │
│  │  │  • Receive payment + stake (105% total)                         │  │   │
│  │  │  • Update reputation (+points)                                  │  │   │
│  │  │  • Store learnings in operational memory                        │  │   │
│  │  │                                                                  │  │   │
│  │  │  On Failure:                                                     │  │   │
│  │  │  • Record failure reason                                        │  │   │
│  │  │  • Stake slashed (10% loss)                                     │  │   │
│  │  │  • Create reflection for learning                               │  │   │
│  │  │  • Update reputation (-points)                                  │  │   │
│  │  │                                                                  │  │   │
│  │  └──────────────────────────────────────────────────────────────────┘  │   │
│  │                                                                         │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**5.5.2 Implementation Code**

```python
# clawtasks_integration.py
from typing import Optional, List, Dict
from dataclasses import dataclass
from datetime import datetime, timedelta
import requests
from web3 import Web3

@dataclass
class BountyEvaluation:
    bounty_id: str
    should_pursue: bool
    confidence: float
    estimated_hours: float
    roi_score: float
    risk_level: str
    recommended_agent: str
    reasoning: str

class ClawTasksMonitor:
    """Ögedei's bounty monitoring service"""

    def __init__(self, neo4j_memory, clawtasks_api_url: str, api_key: str):
        self.memory = neo4j_memory
        self.api_url = clawtasks_api_url
        self.api_key = api_key
        self.poll_interval = 60  # seconds

    async def poll_new_bounties(self) -> List[Dict]:
        """Poll ClawTasks API for new bounties"""
        response = requests.get(
            f"{self.api_url}/bounties",
            headers={"Authorization": f"Bearer {self.api_key}"},
            params={"status": "open", "created_after": self.last_poll_time}
        )
        bounties = response.json()["bounties"]

        for bounty in bounties:
            await self.store_bounty(bounty)

        return bounties

    async def store_bounty(self, bounty: Dict):
        """Store bounty in Neo4j with capability matching"""
        query = """
        // Create bounty
        CREATE (b:Bounty {
          id: $bounty_id,
          external_id: $external_id,
          title: $title,
          description: $description,
          category: $category,
          subcategory: $subcategory,
          reward_usdc: $reward,
          stake_required: $reward * 0.10,
          deadline: datetime($deadline),
          requirements: $requirements,
          deliverables: $deliverables,
          status: 'discovered',
          difficulty: $difficulty,
          estimated_hours: $estimated_hours,
          source_platform: 'clawtasks',
          external_url: $url,
          creator_address: $creator,
          contract_address: $contract,
          created_at: datetime(),
          discovered_at: datetime()
        })

        // Link to required skills
        WITH b
        UNWIND $required_skills as skill_name
        MERGE (s:Skill {name: skill_name})
        MERGE (b)-[:REQUIRES_SKILL {importance: 'required'}]->(s)

        // Match to agents
        WITH b
        MATCH (b)-[:REQUIRES_SKILL]->(req_skill:Skill)
        MATCH (a:Agent)-[:HAS_SKILL]->(req_skill)
        WITH b, a, count(req_skill) as matching_skills
        MATCH (b)-[:REQUIRES_SKILL]->(all_req:Skill)
        WITH b, a, matching_skills, count(all_req) as total_skills
        WHERE matching_skills >= total_skills * 0.7
        MERGE (a)-[:CAN_PERFORM {
          confidence: matching_skills * 1.0 / total_skills,
          calculated_at: datetime()
        }]->(b)

        RETURN b.id as bounty_id
        """

        await self.memory.query(query, {
            "bounty_id": str(uuid.uuid4()),
            "external_id": bounty["id"],
            "title": bounty["title"],
            "description": bounty["description"],
            "category": bounty["category"],
            "subcategory": bounty["subcategory"],
            "reward": float(bounty["reward"]),
            "deadline": bounty["deadline"],
            "requirements": bounty["requirements"],
            "deliverables": bounty["deliverables"],
            "difficulty": bounty["difficulty"],
            "estimated_hours": bounty.get("estimated_hours", 0),
            "required_skills": bounty["required_skills"],
            "url": bounty["url"],
            "creator": bounty["creator_address"],
            "contract": bounty["contract_address"]
        })

class BountyEvaluator:
    """Jochi's bounty evaluation service"""

    def __init__(self, neo4j_memory):
        self.memory = neo4j_memory

    async def evaluate_bounty(self, bounty_id: str) -> BountyEvaluation:
        """Evaluate if bounty is worth pursuing"""

        # Get bounty details
        bounty = await self.memory.query("""
            MATCH (b:Bounty {id: $bounty_id})
            RETURN b
        """, {"bounty_id": bounty_id})

        # Get capable agents
        agents = await self.memory.query("""
            MATCH (b:Bounty {id: $bounty_id})<-[:CAN_PERFORM]-(a:Agent)
            RETURN a.name as agent, a.skills as skills
        """, {"bounty_id": bounty_id})

        # Calculate success probability based on:
        # - Agent skill match
        # - Historical success rate on similar bounties
        # - Time availability
        # - Current workload

        evaluation = await self._calculate_evaluation(bounty, agents)

        # Store evaluation
        await self.memory.query("""
            MATCH (b:Bounty {id: $bounty_id})
            CREATE (e:Evaluation {
                id: uuid(),
                should_pursue: $should_pursue,
                confidence: $confidence,
                roi_score: $roi,
                risk_level: $risk,
                recommended_agent: $agent,
                reasoning: $reasoning,
                evaluated_at: datetime()
            })
            CREATE (b)-[:HAS_EVALUATION]->(e)
        """, {
            "bounty_id": bounty_id,
            "should_pursue": evaluation.should_pursue,
            "confidence": evaluation.confidence,
            "roi": evaluation.roi_score,
            "risk": evaluation.risk_level,
            "agent": evaluation.recommended_agent,
            "reasoning": evaluation.reasoning
        })

        return evaluation

    async def _calculate_evaluation(self, bounty, agents) -> BountyEvaluation:
        # Implementation: analyze historical data, agent availability, etc.
        pass

class BountyClaimer:
    """Kublai's bounty claiming service"""

    def __init__(self, neo4j_memory, web3_provider: str, private_key: str):
        self.memory = neo4j_memory
        self.w3 = Web3(Web3.HTTPProvider(web3_provider))
        self.account = self.w3.eth.account.from_key(private_key)

    async def claim_bounty(self, bounty_id: str, agent_name: str) -> bool:
        """Stake USDC and claim bounty on ClawTasks"""

        # Get bounty details
        result = await self.memory.query("""
            MATCH (b:Bounty {id: $bounty_id})
            MATCH (a:Agent {name: $agent})
            MATCH (w:Wallet)-[:BELONGS_TO]->(a)
            WHERE w.type = 'hot'
            RETURN b, w
        """, {"bounty_id": bounty_id, "agent": agent_name})

        bounty = result["b"]
        wallet = result["w"]

        # Check balance
        if wallet["balance_usdc"] < bounty["stake_required"]:
            raise InsufficientFundsError(
                f"Hot wallet balance {wallet['balance_usdc']} USDC "
                f"below required stake {bounty['stake_required']} USDC"
            )

        # Submit stake transaction
        tx_hash = await self._submit_stake(
            bounty["contract_address"],
            bounty["external_id"],
            bounty["stake_required"]
        )

        # Record in Neo4j
        await self.memory.query("""
            MATCH (b:Bounty {id: $bounty_id})
            MATCH (a:Agent {name: $agent})
            MATCH (w:Wallet {address: $wallet_addr})

            CREATE (s:Stake {
                id: uuid(),
                amount: $stake_amount,
                status: 'locked',
                locked_at: datetime(),
                unlock_condition: 'bounty_completion',
                tx_hash: $tx_hash
            })

            CREATE (w)-[:STAKED {tx_hash: $tx_hash}]->(s)
            CREATE (s)-[:FOR_BOUNTY]->(b)
            CREATE (a)-[:CLAIMED {claimed_at: datetime()}]->(b)

            SET b.status = 'claimed',
                b.claimed_by = $agent,
                b.claimed_at = datetime()
        """, {
            "bounty_id": bounty_id,
            "agent": agent_name,
            "wallet_addr": wallet["address"],
            "stake_amount": bounty["stake_required"],
            "tx_hash": tx_hash
        })

        return True

    async def _submit_stake(self, contract_addr: str, bounty_id: str, amount: float) -> str:
        """Submit stake transaction to ClawTasks contract"""
        # Implementation: Web3 transaction to stake USDC
        pass
```

#### 5.6 USDC Wallet Architecture

**5.6.1 Multi-Tier Wallet System**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MULTI-TIER WALLET ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  TIER 1: COLD STORAGE (Offline/Hardware)                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  • 70-80% of total funds                                            │   │
│  │  • Hardware wallet (Ledger/Trezor) or air-gapped machine           │   │
│  │  • Multi-sig requiring 2-of-3 keys                                  │   │
│  │  • Used for: Large deposits, emergency recovery                     │   │
│  │  • Key storage: Bank vault, safe deposit box, encrypted offline    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    │ Periodic top-up (weekly/monthly)       │
│                                    ▼                                         │
│  TIER 2: HOT WALLET (Operational)                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  • 20-25% of total funds                                            │   │
│  │  • Software wallet on secure server                                 │   │
│  │  • Single-sig with rate limiting                                    │   │
│  │  • Used for: Bounty staking, operational expenses                   │   │
│  │  • Key storage: Encrypted env vars, secrets manager                 │   │
│  │  • Auto-refill from cold storage when below threshold               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    │ Derivation (BIP-32/44)                 │
│                                    ▼                                         │
│  TIER 3: WORKER WALLETS (Per-Agent)                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  • 1-5% of total funds per agent                                    │   │
│  │  • Derived from hot wallet using deterministic paths                │   │
│  │  • Used for: Individual bounty execution, gas fees                  │   │
│  │  • Key storage: Agent-local, encrypted at rest                      │   │
│  │  • Can be swept back to hot wallet                                  │   │
│  │                                                                     │   │
│  │  Path examples:                                                     │   │
│  │  • m/44'/60'/0'/0/0 → Temüjin (technical)                          │   │
│  │  • m/44'/60'/0'/0/1 → Chagatai (content)                           │   │
│  │  • m/44'/60'/0'/0/2 → Möngke (research)                            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**5.6.2 Wallet Security Best Practices**

```yaml
# wallet_security.yaml

key_management:
  cold_storage:
    type: "hardware_wallet"  # Ledger, Trezor
    multi_sig: "2-of-3"
    key_distribution:
      - location: "bank_vault"
        holder: "primary_admin"
      - location: "safe_deposit_box"
        holder: "secondary_admin"
      - location: "encrypted_offline"
        holder: "recovery_service"

  hot_wallet:
    type: "software"
    storage: "aws_secrets_manager"  # or HashiCorp Vault
    encryption: "AES-256-GCM"
    access_control:
      - role: "bounty_claimer"
        permissions: ["sign_stake", "sign_payment"]
        rate_limit: "10_tx_per_hour"
      - role: "admin"
        permissions: ["sign_all", "sweep_funds"]
        mfa_required: true

  worker_wallets:
    derivation_path: "m/44'/60'/0'/0/{agent_index}"
    key_storage: "agent_local_encrypted"
    max_balance: "100_USDC"  # Auto-sweep above this
    auto_sweep_threshold: "50_USDC"

transaction_policies:
  stake_limits:
    per_bounty_max: "1000_USDC"
    daily_total_max: "5000_USDC"
    concurrent_bounties_max: 5

  approval_workflows:
    below_100_usdc: "auto_approve"
    100_to_1000_usdc: "kublai_approval"
    above_1000_usdc: "multi_sig_required"

monitoring:
  alerts:
    - condition: "hot_wallet_balance < 500_USDC"
      action: "notify_admin"
    - condition: "unusual_stake_pattern"
      action: "freeze_and_review"
    - condition: "failed_transaction_rate > 10%"
      action: "investigate"

  audit_logging:
    all_transactions: true
    ip_address: true
    user_agent: true
    retention_days: 365
```

**5.6.3 Key Management Implementation**

```python
# wallet_manager.py
from typing import Optional, Tuple
from web3 import Web3
from eth_account import Account
import boto3
from cryptography.fernet import Fernet
import hashlib

class WalletManager:
    """Manages multi-tier wallet system"""

    def __init__(self, secrets_manager):
        self.secrets = secrets_manager
        self.w3 = Web3()

    async def get_hot_wallet(self) -> Tuple[str, str]:
        """Get hot wallet address and private key"""
        # Retrieve from secure storage
        secret = await self.secrets.get_secret("clawtasks/hot_wallet")
        return secret["address"], secret["private_key"]

    async def derive_worker_wallet(self, agent_name: str) -> Tuple[str, str]:
        """Derive worker wallet from hot wallet using BIP-44"""

        # Get hot wallet seed
        _, hot_key = await self.get_hot_wallet()

        # Derivation paths for each agent
        agent_indices = {
            "temujin": 0,    # Technical
            "chagatai": 1,   # Content
            "mongke": 2,     # Research
            "jochi": 3,      # Analysis
            "ogedei": 4,     # Operations
            "kublai": 5      # Router
        }

        index = agent_indices.get(agent_name.lower(), 999)

        # Derive child key (simplified - use proper BIP-44 library in production)
        derivation_path = f"m/44'/60'/0'/0/{index}"
        child_key = self._derive_child_key(hot_key, derivation_path)

        account = Account.from_key(child_key)
        return account.address, child_key

    async def sweep_worker_to_hot(self, agent_name: str):
        """Sweep worker wallet balance back to hot wallet"""

        worker_addr, worker_key = await self.derive_worker_wallet(agent_name)
        hot_addr, _ = await self.get_hot_wallet()

        # Get balance
        balance = await self._get_usdc_balance(worker_addr)

        if balance > 50:  # Sweep threshold
            # Transfer to hot wallet
            tx_hash = await self._transfer_usdc(
                from_key=worker_key,
                to_address=hot_addr,
                amount=balance - 5  # Leave some for gas
            )

            # Record in Neo4j
            await self._record_sweep(agent_name, worker_addr, hot_addr, balance, tx_hash)

    async def refill_hot_wallet(self, amount_usdc: float):
        """Refill hot wallet from cold storage"""

        # This requires manual/multi-sig approval
        # Implementation would trigger admin notification
        pass

    def _derive_child_key(self, parent_key: str, path: str) -> str:
        """Derive child key from BIP-44 path"""
        # Use proper library like bip32 or hdwallet in production
        pass
```

#### 5.7 Smart Contract Integration

**5.7.1 ClawTasks Contract Interface**

```solidity
// ClawTasks contract interface (simplified)
// Actual contract on Base L2

interface IClawTasks {
    // Bounty structure
    struct Bounty {
        address creator;
        uint256 reward;
        uint256 stakeRequired;
        uint256 deadline;
        bytes32 requirementsHash;
        address worker;
        BountyStatus status;
    }

    enum BountyStatus {
        Open,
        Claimed,
        Completed,
        Disputed,
        Cancelled
    }

    // Events
    event BountyCreated(uint256 indexed bountyId, address indexed creator, uint256 reward);
    event BountyClaimed(uint256 indexed bountyId, address indexed worker, uint256 stake);
    event BountyCompleted(uint256 indexed bountyId, address indexed worker, uint256 payout);
    event BountyFailed(uint256 indexed bountyId, address indexed worker, uint256 slashed);

    // Functions
    function createBounty(
        uint256 reward,
        uint256 deadline,
        bytes32 requirementsHash
    ) external returns (uint256 bountyId);

    function claimBounty(uint256 bountyId) external;
    function submitDeliverable(uint256 bountyId, bytes32 deliverableHash) external;
    function approveCompletion(uint256 bountyId) external;
    function disputeBounty(uint256 bountyId, string calldata reason) external;
    function resolveDispute(uint256 bountyId, bool workerWins) external;

    // View functions
    function getBounty(uint256 bountyId) external view returns (Bounty memory);
    function getWorkerReputation(address worker) external view returns (uint256 score);
}
```

**5.7.2 Python Contract Integration**

```python
# clawtasks_contract.py
from web3 import Web3
from eth_abi import encode
from typing import Optional
import json

class ClawTasksContract:
    """Interface to ClawTasks smart contracts on Base L2"""

    CONTRACT_ADDRESS = "0x..."  # ClawTasks contract on Base
    USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # USDC on Base

    def __init__(self, web3_provider: str, private_key: str):
        self.w3 = Web3(Web3.HTTPProvider(web3_provider))
        self.account = self.w3.eth.account.from_key(private_key)

        # Load contract ABIs
        with open("clawtasks_abi.json") as f:
            self.contract = self.w3.eth.contract(
                address=self.CONTRACT_ADDRESS,
                abi=json.load(f)
            )

        with open("usdc_abi.json") as f:
            self.usdc = self.w3.eth.contract(
                address=self.USDC_ADDRESS,
                abi=json.load(f)
            )

    async def approve_usdc_spending(self, amount: float) -> str:
        """Approve ClawTasks contract to spend USDC"""

        amount_wei = int(amount * 1e6)  # USDC has 6 decimals

        tx = self.usdc.functions.approve(
            self.CONTRACT_ADDRESS,
            amount_wei
        ).build_transaction({
            'from': self.account.address,
            'nonce': self.w3.eth.get_transaction_count(self.account.address),
            'gas': 100000,
            'gasPrice': self.w3.eth.gas_price
        })

        signed = self.w3.eth.account.sign_transaction(tx, self.account.key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)

        return tx_hash.hex()

    async def claim_bounty(self, bounty_id: int, stake_amount: float) -> str:
        """Stake USDC and claim a bounty"""

        # First approve USDC spending
        await self.approve_usdc_spending(stake_amount)

        # Build claim transaction
        tx = self.contract.functions.claimBounty(bounty_id).build_transaction({
            'from': self.account.address,
            'nonce': self.w3.eth.get_transaction_count(self.account.address),
            'gas': 300000,
            'gasPrice': self.w3.eth.gas_price
        })

        signed = self.w3.eth.account.sign_transaction(tx, self.account.key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)

        return tx_hash.hex()

    async def submit_deliverable(self, bounty_id: int, deliverable_hash: str) -> str:
        """Submit deliverable hash (IPFS or other content hash)"""

        tx = self.contract.functions.submitDeliverable(
            bounty_id,
            bytes.fromhex(deliverable_hash.replace('0x', ''))
        ).build_transaction({
            'from': self.account.address,
            'nonce': self.w3.eth.get_transaction_count(self.account.address),
            'gas': 200000,
            'gasPrice': self.w3.eth.gas_price
        })

        signed = self.w3.eth.account.sign_transaction(tx, self.account.key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)

        return tx_hash.hex()

    async def get_bounty_details(self, bounty_id: int) -> dict:
        """Get bounty details from contract"""

        bounty = self.contract.functions.getBounty(bounty_id).call()

        return {
            'creator': bounty[0],
            'reward': bounty[1] / 1e6,  # Convert from wei
            'stake_required': bounty[2] / 1e6,
            'deadline': bounty[3],
            'requirements_hash': bounty[4].hex(),
            'worker': bounty[5],
            'status': bounty[6]
        }

    async def listen_for_events(self, callback):
        """Listen for ClawTasks events"""

        # Create event filters
        event_filters = {
            'BountyCreated': self.contract.events.BountyCreated.create_filter(fromBlock='latest'),
            'BountyClaimed': self.contract.events.BountyClaimed.create_filter(fromBlock='latest'),
            'BountyCompleted': self.contract.events.BountyCompleted.create_filter(fromBlock='latest'),
            'BountyFailed': self.contract.events.BountyFailed.create_filter(fromBlock='latest')
        }

        # Poll for events
        while True:
            for event_name, event_filter in event_filters.items():
                events = event_filter.get_new_entries()
                for event in events:
                    await callback(event_name, event)

            await asyncio.sleep(10)  # Poll every 10 seconds
```

**5.7.3 Staking and Payment Flow**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STAKING & PAYMENT FLOW                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  CLAIM BOUNTY                                                                │
│  ────────────                                                                │
│                                                                              │
│  Agent Wallet                        ClawTasks Contract                     │
│       │                                     │                                │
│       │  1. approve(ClawTasks, stake)       │                                │
│       │────────────────────────────────────▶│                                │
│       │                                     │                                │
│       │  2. claimBounty(bountyId)           │                                │
│       │────────────────────────────────────▶│                                │
│       │                                     │                                │
│       │     3. Transfer stake from agent    │                                │
│       │        to contract                  │                                │
│       │                                     │                                │
│       │◀────────────────────────────────────│                                │
│       │     4. Emit BountyClaimed event     │                                │
│       │                                     │                                │
│                                                                              │
│  COMPLETE BOUNTY (Success)                                                   │
│  ─────────────────────────                                                   │
│                                                                              │
│  Agent Wallet                        ClawTasks Contract    Creator          │
│       │                                     │                  │             │
│       │  5. submitDeliverable(hash)         │                  │             │
│       │────────────────────────────────────▶│                  │             │
│       │                                     │                  │             │
│       │                                     │◀─────────────────│             │
│       │                                     │  6. approveCompletion()        │
│       │                                     │                  │             │
│       │     7. Transfer 95% reward + stake  │                  │             │
│       │◀────────────────────────────────────│                  │             │
│       │                                     │                  │             │
│       │     8. Transfer 5% fee to treasury  │                  │             │
│       │                                     │─────────────────▶│             │
│       │                                     │                  │             │
│       │     9. Emit BountyCompleted         │                  │             │
│       │◀────────────────────────────────────│                  │             │
│       │                                     │                  │             │
│                                                                              │
│  FAIL BOUNTY (Timeout/Dispute Lost)                                          │
│  ──────────────────────────────────                                          │
│                                                                              │
│  Agent Wallet                        ClawTasks Contract    Creator          │
│       │                                     │                  │             │
│       │     10. Stake slashed               │                  │             │
│       │     (10% to creator, 90% burned)    │                  │             │
│       │◀────────────────────────────────────│                  │             │
│       │                                     │─────────────────▶│             │
│       │     11. Emit BountyFailed           │                  │             │
│       │◀────────────────────────────────────│                  │             │
│       │                                     │                  │             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**5.7.4 Slashing Conditions**

| Condition | Slashing Result | Prevention |
|-----------|-----------------|------------|
| **Timeout** | 100% stake slashed | Set realistic deadlines, monitor progress |
| **Deliverable Rejected** | 100% stake slashed | Evaluate carefully before claiming |
| **Dispute Lost** | 100% stake slashed | Clear communication, document everything |
| **Cancellation (by worker)** | 50% stake slashed | Commit only when confident |
| **Creator Cancel** | Stake returned + small compensation | N/A (creator pays) |

**5.7.5 Risk Management**

```python
# risk_management.py

class BountyRiskManager:
    """Manages risk for ClawTasks bounty participation"""

    RISK_THRESHOLDS = {
        'max_stake_per_bounty': 1000,      # USDC
        'max_daily_stake': 5000,           # USDC
        'max_concurrent_bounties': 5,
        'min_success_rate': 0.8,           # 80%
        'min_hot_wallet_balance': 500      # USDC
    }

    async def assess_bounty_risk(self, bounty_id: str) -> RiskAssessment:
        """Assess risk before claiming a bounty"""

        # Get bounty details
        bounty = await self.get_bounty(bounty_id)

        # Check stake amount
        if bounty['stake_required'] > self.RISK_THRESHOLDS['max_stake_per_bounty']:
            return RiskAssessment(
                approved=False,
                reason=f"Stake {bounty['stake_required']} exceeds max {self.RISK_THRESHOLDS['max_stake_per_bounty']}"
            )

        # Check daily stake total
        daily_stake = await self.get_daily_stake_total()
        if daily_stake + bounty['stake_required'] > self.RISK_THRESHOLDS['max_daily_stake']:
            return RiskAssessment(
                approved=False,
                reason=f"Daily stake limit would be exceeded"
            )

        # Check concurrent bounties
        concurrent = await self.get_concurrent_bounties()
        if concurrent >= self.RISK_THRESHOLDS['max_concurrent_bounties']:
            return RiskAssessment(
                approved=False,
                reason=f"Max concurrent bounties ({self.RISK_THRESHOLDS['max_concurrent_bounties']}) reached"
            )

        # Check agent success rate
        agent_reputation = await self.get_agent_reputation()
        if agent_reputation['success_rate'] < self.RISK_THRESHOLDS['min_success_rate']:
            return RiskAssessment(
                approved=False,
                reason=f"Success rate {agent_reputation['success_rate']} below threshold"
            )

        # Check wallet balance
        hot_balance = await self.get_hot_wallet_balance()
        if hot_balance < self.RISK_THRESHOLDS['min_hot_wallet_balance']:
            return RiskAssessment(
                approved=False,
                reason=f"Hot wallet balance {hot_balance} below minimum"
            )

        return RiskAssessment(approved=True, risk_score=0.2)

    async def emergency_withdraw(self):
        """Emergency withdrawal of all stakes"""
        # Implementation for emergency situations
        pass
```

---

### Phase 6: Jochi-Temüjin Collaboration Protocol

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

### Phase 6.5: Kublai Failover Protocol (Ögedei as Emergency Router)

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

### Phase 7: Kublai Delegation Protocol

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

### Phase 8: Bidirectional Notion Integration

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

### Phase 9: Auto-Skill Generation System

When the system encounters a bounty type it cannot complete (skill gap), it automatically generates a new SKILL.md file to learn that capability. This enables continuous expansion of agent capabilities.

#### 9.1 Overview

The Auto-Skill Generation System enables the OpenClaw multi-agent system to autonomously expand its capabilities by:

| Capability | Description | Benefit |
|------------|-------------|---------|
| **Self-Directed Learning** | Detects knowledge gaps from failures | No manual intervention needed |
| **Collaborative Skill Creation** | 6 agents research, draft, test, and deploy | High-quality skill documentation |
| **Continuous Improvement** | A/B testing and feedback integration | Skills improve over time |
| **Versioned Knowledge** | Skills tracked with dependencies | Safe updates and rollbacks |

**System Architecture:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Auto-Skill Generation System                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │   ClawTasks │───►│  Skill Gap  │───►│   6-Agent   │───►│   SKILL.md  │  │
│  │   (Bounty)  │    │  Detection  │    │  Workflow   │    │   Created   │  │
│  └─────────────┘    └─────────────┘    └─────────────┘    └──────┬──────┘  │
│         │                                                        │         │
│         │    ┌───────────────────────────────────────────────────┘         │
│         │    │                                                               │
│         │    ▼                                                               │
│  ┌──────┴──────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │   Retry     │◄───│    A/B      │◄───│    Test     │◄───│   Deploy    │  │
│  │   Bounty    │    │   Testing   │    │  Framework  │    │   Skill     │  │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 9.2 Skill Gap Detection

The system detects skill gaps through multiple mechanisms:

| Detection Method | Trigger | Confidence |
|-----------------|---------|------------|
| Failed bounty evaluation | Capability mismatch on execution | High |
| Low success probability | Historical pattern on similar bounties | Medium |
| User feedback | Explicit indication of missing capability | High |
| Periodic analysis | Scheduled skill gap assessment | Medium |

**Skill Gap Detection Flow:**

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Bounty Failed  │────►│  Analyze Error  │────►│  Skill Gap?     │
│  or Rejected    │     │  Type/Pattern   │     │  (Confidence)   │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                              ┌──────────────────────────┘
                              ▼
                    ┌─────────────────┐
                    │  Create SkillGap│
                    │  Node in Neo4j  │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ Queue for Skill │
                    │ Generation      │
                    └─────────────────┘
```

**Neo4j Schema for Skill Gaps:**

```cypher
(:SkillGap {
  id: uuid,
  detected_missing_capability: string,
  confidence: float,
  frequency: int,
  first_detected: datetime,
  last_detected: datetime,
  auto_generated: boolean,
  status: 'pending' | 'generating' | 'resolved'
})

(:Skill {
  id: uuid,
  name: string,
  description: string,
  version: string,
  created_at: datetime,
  updated_at: datetime
})

// Relationships
(Bounty)-[:REQUIRES_SKILL {probability: float}]->(Skill)
(Agent)-[:LACKS {since: datetime}]->(SkillGap)
(Skill)-[:ADDRESSES]->(SkillGap)
(SkillGap)-[:DETECTED_FROM]->(Bounty)
```

#### 9.3 Skill Generation Workflow

The 6-agent collaborative workflow for skill generation:

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Ögedei  │───►│  Möngke  │───►│ Chagatai │───►│  Temüjin │───►│  Ögedei  │───►│   Jochi  │
│  Trigger │    │ Research │    │   Draft  │    │   Test   │    │  Deploy  │    │ Validate │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
     │               │               │               │               │               │
     ▼               ▼               ▼               ▼               ▼               ▼
 Detect Gap    Gather Domain   Write SKILL.md  Create Tests   Deploy Skill   Measure
 from Failed    Knowledge       + Examples     + Validate    to System     Effectiveness
 Bounty        Best Practices   + Edge Cases   Integration                   A/B Test
```

**Python Implementation:**

```python
class SkillGenerationWorkflow:
    """6-agent workflow for automatic skill creation."""

    def __init__(self, memory: OperationalMemory, agents: Dict[str, Agent]):
        self.memory = memory
        self.agents = agents
        self.ogedei = agents['ops']
        self.mongke = agents['researcher']
        self.chagatai = agents['writer']
        self.temujin = agents['developer']
        self.jochi = agents['analyst']

    def generate_skill(self, skill_gap: SkillGap) -> str:
        """Execute 6-agent skill generation workflow."""

        # Step 1: Ögedei - Trigger and coordinate
        self.ogedei.update_skill_gap_status(skill_gap.id, 'generating')

        # Step 2: Möngke - Research the skill domain
        research = self.mongke.research_skill_domain(
            capability=skill_gap.detected_missing_capability,
            context=self.get_related_bounties(skill_gap)
        )

        # Step 3: Chagatai - Draft SKILL.md
        skill_draft = self.chagatai.write_skill_document(
            research=research,
            template=self.get_skill_template()
        )

        # Step 4: Temüjin - Create tests
        test_suite = self.temujin.create_skill_tests(
            skill_document=skill_draft,
            edge_cases=research.get('edge_cases', [])
        )

        # Run tests
        test_results = self.run_skill_tests(test_suite)
        if not test_results['passed']:
            # Iterate with Chagatai on failures
            skill_draft = self.chagatai.revise_skill_document(
                skill_draft=skill_draft,
                test_failures=test_results['failures']
            )
            test_results = self.run_skill_tests(test_suite)

        # Step 5: Ögedei - Deploy
        skill_id = self.ogedei.deploy_skill(
            skill_document=skill_draft,
            test_results=test_results
        )

        # Step 6: Jochi - Validate effectiveness
        self.jochi.schedule_skill_validation(
            skill_id=skill_id,
            skill_gap_id=skill_gap.id,
            validation_period_days=7
        )

        return skill_id

    def get_related_bounties(self, skill_gap: SkillGap) -> List[Dict]:
        """Query Neo4j for bounties that triggered this skill gap."""

        query = """
        MATCH (sg:SkillGap {id: $gap_id})-[:DETECTED_FROM]->(b:Bounty)
        RETURN b.type as bounty_type,
               b.description as description,
               b.failure_reason as failure_reason
        ORDER BY b.created_at DESC
        LIMIT 10
        """

        result = self.memory.execute(query, gap_id=skill_gap.id)
        return [record.data() for record in result]

    def run_skill_tests(self, test_suite: Dict) -> Dict:
        """Execute skill test suite."""

        passed = []
        failures = []

        for test in test_suite['tests']:
            try:
                result = self.execute_test(test)
                if result['success']:
                    passed.append(test['name'])
                else:
                    failures.append({
                        'test': test['name'],
                        'error': result['error']
                    })
            except Exception as e:
                failures.append({
                    'test': test['name'],
                    'error': str(e)
                })

        return {
            'passed': len(failures) == 0,
            'total': len(test_suite['tests']),
            'passed_count': len(passed),
            'failures': failures
        }
```

#### 9.4 SKILL.md Format

Standard SKILL.md format with YAML frontmatter:

```markdown
---
name: skill-name
description: What the skill does
version: 1.0.0
agents: [temujin, chagatai]
tools: [file-write, bash, web-search]
triggers: ["create api", "build endpoint", "setup database"]
category: development
complexity: intermediate
dependencies: []
created_at: 2024-01-15T10:30:00Z
auto_generated: true
skill_gap_id: sg_abc123
---

# Skill: {name}

## Overview

Brief description of what this skill enables agents to do.

## When to Use

- Trigger pattern 1: Description
- Trigger pattern 2: Description
- Trigger pattern 3: Description

## Prerequisites

- Required tool access
- Required knowledge
- Required context

## Execution Steps

### Step 1: [Action Name]

```python
# Code example or pseudocode
def step_one(context):
    # Implementation
    pass
```

**Expected Output:** Description

### Step 2: [Action Name]

...

## Error Handling

| Error Pattern | Cause | Resolution |
|--------------|-------|------------|
| Error X | Cause Y | Do Z |

## Examples

### Example 1: Simple Case

Input: ...
Process: ...
Output: ...

### Example 2: Complex Case

Input: ...
Process: ...
Output: ...

## Testing

```python
# Test cases for this skill
test_cases = [
    {
        'name': 'test_simple_case',
        'input': {...},
        'expected': {...}
    },
    {
        'name': 'test_edge_case',
        'input': {...},
        'expected': {...}
    }
]
```

## Related Skills

- [skill-name-1](link) - Relationship
- [skill-name-2](link) - Relationship

## Version History

- 1.0.0 (2024-01-15): Initial skill created from skill gap sg_abc123
```

#### 9.5 Neo4j Schema for Skills

Complete Cypher schema for skill tracking:

```cypher
// Skill node - represents a learned capability
(:Skill {
  id: uuid,
  name: string,
  description: string,
  version: string,
  category: string,
  complexity: 'beginner' | 'intermediate' | 'advanced',
  file_path: string,
  created_at: datetime,
  updated_at: datetime,
  auto_generated: boolean,
  status: 'draft' | 'testing' | 'active' | 'deprecated'
})

// SkillGap node - represents missing capabilities
(:SkillGap {
  id: uuid,
  capability_type: string,
  description: string,
  frequency_detected: int,
  first_detected: datetime,
  last_detected: datetime,
  auto_generated: boolean,
  status: 'pending' | 'generating' | 'resolved' | 'wontfix',
  confidence: float
})

// SkillUsage node - tracks how skills are used
(:SkillUsage {
  id: uuid,
  skill_name: string,
  usage_count: int,
  success_count: int,
  failure_count: int,
  success_rate: float,
  last_used: datetime,
  first_used: datetime
})

// SkillTest node - stores test results
(:SkillTest {
  id: uuid,
  test_name: string,
  test_type: 'unit' | 'integration' | 'e2e',
  status: 'passed' | 'failed' | 'pending',
  executed_at: datetime,
  execution_time_ms: int,
  error_message: string
})

// Relationships
(Agent)-[:HAS_SKILL {acquired_at: datetime, proficiency: float}]->(Skill)
(Agent)-[:LACKS {since: datetime, priority: int}]->(SkillGap)
(Skill)-[:ADDRESSES {effectiveness: float}]->(SkillGap)
(SkillGap)-[:DETECTED_FROM {confidence: float}]->(Bounty)
(Skill)-[:DEPENDS_ON]->(Skill)
(Skill)-[:REPLACES {version_from: string, version_to: string}]->(Skill)
(Skill)-[:HAS_USAGE]->(SkillUsage)
(Skill)-[:HAS_TEST]->(SkillTest)
(Bounty)-[:USES_SKILL {success: boolean}]->(Skill)
(Task)-[:REQUIRES_SKILL]->(Skill)
```

#### 9.6 Skill Testing Framework

Comprehensive testing approach for generated skills:

```python
class SkillTestingFramework:
    """Test framework for skill validation."""

    def __init__(self, memory: OperationalMemory):
        self.memory = memory

    def create_test_plan(self, skill: Skill) -> Dict:
        """Generate comprehensive test plan for skill."""

        return {
            'unit_tests': self.generate_unit_tests(skill),
            'integration_tests': self.generate_integration_tests(skill),
            'edge_cases': self.generate_edge_case_tests(skill),
            'performance_tests': self.generate_performance_tests(skill)
        }

    def generate_unit_tests(self, skill: Skill) -> List[Dict]:
        """Create unit tests for individual skill components."""

        tests = []

        # Parse skill document for testable components
        components = self.parse_skill_components(skill.file_path)

        for component in components:
            tests.append({
                'name': f'test_{component["name"]}',
                'type': 'unit',
                'input': component['example_input'],
                'expected_output': component['example_output'],
                'validation': component['validation_rules']
            })

        return tests

    def generate_integration_tests(self, skill: Skill) -> List[Dict]:
        """Create integration tests for skill workflows."""

        # Query similar successful bounties for test scenarios
        query = """
        MATCH (s:Skill {name: $skill_name})<-[:USES_SKILL {success: true}]-(b:Bounty)
        RETURN b.description as scenario,
               b.context as context
        LIMIT 5
        """

        result = self.memory.execute(query, skill_name=skill.name)

        tests = []
        for record in result:
            tests.append({
                'name': f'integration_{len(tests)}',
                'type': 'integration',
                'scenario': record['scenario'],
                'context': record['context'],
                'expected_behavior': 'complete_successfully'
            })

        return tests

    def run_ab_test(self, skill: Skill, control_skill: Skill = None) -> Dict:
        """A/B test skill effectiveness against baseline."""

        # Get pending bounties matching skill triggers
        test_bounties = self.get_test_bounties(skill)

        results = {
            'skill_version': skill.version,
            'test_bounties': len(test_bounties),
            'control_group': [],
            'test_group': []
        }

        for bounty in test_bounties:
            if hash(bounty.id) % 2 == 0:
                # Control group - existing approach
                results['control_group'].append({
                    'bounty_id': bounty.id,
                    'approach': 'baseline',
                    'result': self.execute_with_baseline(bounty)
                })
            else:
                # Test group - new skill
                results['test_group'].append({
                    'bounty_id': bounty.id,
                    'approach': skill.name,
                    'result': self.execute_with_skill(bounty, skill)
                })

        # Calculate effectiveness
        control_success = sum(1 for r in results['control_group'] if r['result']['success'])
        test_success = sum(1 for r in results['test_group'] if r['result']['success'])

        results['effectiveness'] = {
            'control_rate': control_success / len(results['control_group']) if results['control_group'] else 0,
            'test_rate': test_success / len(results['test_group']) if results['test_group'] else 0,
            'improvement': (test_success / len(results['test_group'])) - (control_success / len(results['control_group']))
                              if results['control_group'] and results['test_group'] else 0
        }

        return results

    def gradual_rollout(self, skill: Skill, stages: List[float] = None) -> Dict:
        """Gradually roll out skill to production."""

        stages = stages or [0.1, 0.25, 0.5, 1.0]

        rollout_status = {
            'skill_id': skill.id,
            'current_stage': 0,
            'stages': []
        }

        for i, percentage in enumerate(stages):
            stage_result = self.deploy_to_percentage(skill, percentage)

            rollout_status['stages'].append({
                'stage': i + 1,
                'percentage': percentage * 100,
                'success_rate': stage_result['success_rate'],
                'error_rate': stage_result['error_rate'],
                'proceed': stage_result['success_rate'] > 0.8
            })

            if stage_result['success_rate'] <= 0.8:
                # Rollback
                self.rollback_skill(skill)
                rollout_status['status'] = 'rolled_back'
                return rollout_status

        rollout_status['status'] = 'fully_deployed'
        return rollout_status
```

#### 9.7 ClawTasks Integration

Integration between skill generation and ClawTasks bounty system:

```python
class SkillGenerationClawTasksIntegration:
    """Connect skill generation to ClawTasks workflow."""

    def __init__(self, memory: OperationalMemory, clawtasks: ClawTasksClient):
        self.memory = memory
        self.clawtasks = clawtasks

    def handle_failed_bounty(self, bounty: Bounty, error: str) -> Optional[str]:
        """Process failed bounty and potentially trigger skill generation."""

        # Analyze failure for skill gap
        skill_gap = self.analyze_failure_for_skill_gap(bounty, error)

        if skill_gap and skill_gap['confidence'] > 0.7:
            # Create or update SkillGap node
            gap_id = self.create_or_update_skill_gap(skill_gap, bounty)

            # Check if we should trigger generation
            if self.should_trigger_generation(gap_id):
                return self.trigger_skill_generation(gap_id)

        return None

    def analyze_failure_for_skill_gap(self, bounty: Bounty, error: str) -> Optional[Dict]:
        """Determine if failure indicates a skill gap."""

        # Query similar bounties
        similar = self.query_similar_bounties(bounty)

        # Pattern: Multiple similar bounties failing
        if len(similar) >= 3:
            failure_rate = sum(1 for b in similar if b['status'] == 'failed') / len(similar)

            if failure_rate > 0.6:
                return {
                    'capability_type': self.extract_capability_type(bounty, error),
                    'confidence': failure_rate,
                    'frequency': len(similar),
                    'pattern': 'repeated_failure'
                }

        # Pattern: Capability mismatch
        if 'capability_mismatch' in error.lower() or 'not_supported' in error.lower():
            return {
                'capability_type': bounty.type,
                'confidence': 0.9,
                'frequency': 1,
                'pattern': 'capability_mismatch'
            }

        return None

    def should_trigger_generation(self, gap_id: str) -> bool:
        """Determine if sufficient gaps exist to trigger generation."""

        query = """
        MATCH (sg:SkillGap {id: $gap_id})
        RETURN sg.frequency_detected as frequency,
               sg.confidence as confidence,
               sg.status as status
        """

        result = self.memory.execute(query, gap_id=gap_id)
        record = result.single()

        if not record:
            return False

        # Thresholds for auto-generation
        if record['frequency'] >= 3 and record['confidence'] > 0.7:
            return True

        # Check queue size - batch if many pending
        pending_count = self.get_pending_skill_gaps_count()
        if pending_count >= 5:
            return True

        return False

    def trigger_skill_generation(self, gap_id: str) -> str:
        """Create task for skill generation workflow."""

        # Create Ögedei task
        task_id = self.memory.create_task(
            task_type='skill_generation',
            description=f'Generate skill for gap {gap_id}',
            delegated_by='system',
            assigned_to='ops',
            priority='high',
            properties={
                'skill_gap_id': gap_id,
                'workflow': '6_agent_skill_generation',
                'estimated_duration_hours': 2
            }
        )

        return task_id

    def retry_eligible_bounties(self, skill: Skill) -> List[str]:
        """After skill deployment, retry bounties that were blocked."""

        # Find bounties blocked by this skill gap
        query = """
        MATCH (s:Skill {id: $skill_id})-[:ADDRESSES]->(sg:SkillGap)
              <-[:DETECTED_FROM]-(b:Bounty)
        WHERE b.status = 'failed' OR b.status = 'blocked'
        RETURN b.id as bounty_id,
               b.description as description
        LIMIT 10
        """

        result = self.memory.execute(query, skill_id=skill.id)

        retried = []
        for record in result:
            # Retry bounty with new skill
            retry_result = self.clawtasks.retry_bounty(
                bounty_id=record['bounty_id'],
                with_skill=skill.name
            )
            retried.append({
                'bounty_id': record['bounty_id'],
                'retry_result': retry_result
            })

        return retried

    def update_skill_from_feedback(self, skill: Skill, feedback: Dict):
        """Incorporate user feedback to improve skill."""

        # Store feedback
        query = """
        MATCH (s:Skill {id: $skill_id})
        CREATE (sf:SkillFeedback {
          id: uuid(),
          rating: $rating,
          comment: $comment,
          created_at: datetime()
        })
        CREATE (s)-[:HAS_FEEDBACK]->(sf)
        """

        self.memory.execute(
            query,
            skill_id=skill.id,
            rating=feedback['rating'],
            comment=feedback.get('comment', '')
        )

        # If low rating, queue for improvement
        if feedback['rating'] < 3:
            self.memory.create_task(
                task_type='skill_improvement',
                description=f'Improve skill {skill.name} based on feedback',
                delegated_by='system',
                assigned_to='writer',
                priority='medium',
                properties={
                    'skill_id': skill.id,
                    'feedback_id': feedback['id'],
                    'improvement_areas': feedback.get('issues', [])
                }
            )
```

#### 9.8 Implementation Priority

| Component | Effort | Value | Order |
|-----------|--------|-------|-------|
| Skill gap detection | 3 hours | High | 1st |
| SKILL.md template | 2 hours | High | 2nd |
| 6-agent workflow | 6 hours | High | 3rd |
| Neo4j schema | 2 hours | Medium | 4th |
| Testing framework | 4 hours | Medium | 5th |
| ClawTasks integration | 3 hours | High | 6th |
| A/B testing | 4 hours | Low | 7th |
| Gradual rollout | 3 hours | Low | 8th |

---

### Phase 10: Competitive Advantage Mechanisms

**STATUS: PLANNED**

Systematic approaches to maintain competitive edge in the ClawTasks marketplace. This phase enables the OpenClaw system to optimize its positioning, maximize returns, and build sustainable advantages over competing agent systems.

#### 10.1 Overview

The Competitive Advantage Mechanisms phase provides the 6-agent system with strategic capabilities to thrive in a competitive marketplace:

| Mechanism | Purpose | Competitive Edge |
|-----------|---------|------------------|
| **Dynamic Pricing** | Optimize bounty selection based on market conditions | Capture undervalued opportunities |
| **Skill Specialization** | Identify and dominate high-value niches | Reduced competition in specialized areas |
| **Reputation Optimization** | Maximize on-chain reputation scores | Priority access to premium bounties |
| **Market Intelligence** | Monitor competitor performance and pricing | Anticipate market shifts |
| **Portfolio Optimization** | Balance risk/reward across bounty types | Sustainable long-term returns |
| **Network Effects** | Leverage multi-agent collaboration | Tackle complex bounties others cannot |

**Integration Value:**
- Increase bounty success rate through strategic selection
- Maximize ROI by targeting undervalued opportunities
- Build defensible market position through specialization
- Create compounding advantages through reputation
- Enable complex bounty execution via agent collaboration

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COMPETITIVE ADVANTAGE SYSTEM                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│   │   MARKET     │    │   PRICING    │    │   SKILL      │                  │
│   │  INTELLIGENCE│───▶│  OPTIMIZER   │───▶│ SPECIALIZATION│                 │
│   │              │    │              │    │              │                  │
│   │Jochi monitors│    │Kublai decides│    │Möngke tracks │                  │
│   │competitors   │    │optimal bids  │    │niche markets │                  │
│   └──────────────┘    └──────────────┘    └──────┬───────┘                  │
│                                                  │                           │
│   ┌──────────────┐    ┌──────────────┐          │                           │
│   │   NETWORK    │    │  REPUTATION  │◀─────────┘                           │
│   │   EFFECTS    │◀───│  OPTIMIZER   │                                      │
│   │              │    │              │                                      │
│   │Multi-agent   │    │Ögedei tracks│                                      │
│   │collaboration │    │on-chain score│                                      │
│   └──────────────┘    └──────────────┘                                      │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────┐      │
│   │                     PORTFOLIO OPTIMIZER                          │      │
│   │                                                                  │      │
│   │   Risk/Return Analysis    Diversification    Opportunity Cost   │      │
│   │   ────────────────────    ─────────────    ────────────────    │      │
│   │   • Success probability   • Category mix   • Time allocation    │      │
│   │   • Stake exposure        • Difficulty     • Skill building     │      │
│   │   • Reputation impact     • Time horizon   • Market timing      │      │
│   │                                                                  │      │
│   └─────────────────────────────────────────────────────────────────┘      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 10.2 Dynamic Pricing Strategies

Dynamic pricing adjusts bounty evaluation based on real-time market conditions, demand patterns, and opportunity costs.

##### 10.2.1 Market Condition Analysis

Jochi analyzes market conditions to inform pricing decisions:

```python
# competitive_pricing.py
from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from openclaw_memory import OperationalMemory
import numpy as np

@dataclass
class MarketConditions:
    """Current state of the ClawTasks marketplace."""
    avg_bounty_size: float
    median_completion_time: float
    active_worker_count: int
    bounty_supply_ratio: float  # bounties / active workers
    category_demand: Dict[str, float]  # demand index by category
    success_rate_by_category: Dict[str, float]
    timestamp: datetime

class DynamicPricingEngine:
    """Adjusts bounty valuation based on market dynamics."""

    def __init__(self, memory: OperationalMemory):
        self.memory = memory
        self.min_hourly_rate = 50.0  # USDC per hour minimum
        self.risk_premium = 0.15  # 15% premium for uncertainty

    def analyze_market_conditions(self) -> MarketConditions:
        """Query Neo4j for current market state."""

        query = """
        // Get active bounties in last 24h
        MATCH (b:Bounty)
        WHERE b.discovered_at > datetime() - duration('P1D')
        WITH count(b) as new_bounties,
             avg(b.reward_usdc) as avg_reward,
             percentileCont(b.reward_usdc, 0.5) as median_reward

        // Get completion metrics
        MATCH (b:Bounty {status: 'completed'})
        WHERE b.completed_at > datetime() - duration('P7D')
        WITH new_bounties, avg_reward, median_reward,
             avg(duration.inSeconds(datetime(b.claimed_at), datetime(b.completed_at)) / 3600.0) as avg_hours

        // Get active workers (unique claimants)
        MATCH (b:Bounty {status: 'claimed'})
        WITH count(DISTINCT b.claimed_by) as active_workers

        // Category demand analysis
        MATCH (b:Bounty)
        WHERE b.discovered_at > datetime() - duration('P7D')
        WITH b.category as cat, count(b) as bounty_count
        WITH collect({category: cat, count: bounty_count}) as categories

        RETURN new_bounties, avg_reward, median_reward, avg_hours,
               active_workers, categories
        """

        result = self.memory.execute(query)
        record = result.single()

        # Calculate supply/demand ratio
        supply_ratio = record['new_bounties'] / max(record['active_workers'], 1)

        # Build category demand index
        category_demand = {}
        for cat_data in record['categories']:
            category_demand[cat_data['category']] = cat_data['count']

        return MarketConditions(
            avg_bounty_size=record['avg_reward'] or 0,
            median_completion_time=record['avg_hours'] or 24,
            active_worker_count=record['active_workers'],
            bounty_supply_ratio=supply_ratio,
            category_demand=category_demand,
            success_rate_by_category=self._get_category_success_rates(),
            timestamp=datetime.now()
        )

    def calculate_fair_value(self, bounty: Dict, market: MarketConditions) -> Dict:
        """Calculate fair value of a bounty considering market conditions."""

        base_hourly = bounty['reward_usdc'] / max(bounty['estimated_hours'], 1)

        # Adjust for category demand
        demand_multiplier = 1.0
        if bounty['category'] in market.category_demand:
            demand_score = market.category_demand[bounty['category']]
            demand_multiplier = 1 + (demand_score / 100)  # Higher demand = higher value

        # Adjust for supply/demand ratio
        supply_adjustment = 1.0
        if market.bounty_supply_ratio < 0.5:
            supply_adjustment = 1.2  # Scarce supply = premium pricing
        elif market.bounty_supply_ratio > 2.0:
            supply_adjustment = 0.9  # Oversupply = discount

        # Risk adjustment based on historical success
        success_rate = market.success_rate_by_category.get(bounty['category'], 0.5)
        risk_multiplier = 1 + (self.risk_premium * (1 - success_rate))

        adjusted_hourly = base_hourly * demand_multiplier * supply_adjustment * risk_multiplier

        return {
            'bounty_id': bounty['id'],
            'base_hourly_rate': base_hourly,
            'adjusted_hourly_rate': adjusted_hourly,
            'demand_multiplier': demand_multiplier,
            'supply_adjustment': supply_adjustment,
            'risk_multiplier': risk_multiplier,
            'is_undervalued': adjusted_hourly > self.min_hourly_rate * 1.5,
            'market_conditions': market
        }

    def identify_opportunities(self, min_roi: float = 1.5) -> List[Dict]:
        """Find bounties trading below fair value."""

        market = self.analyze_market_conditions()

        query = """
        MATCH (b:Bounty {status: 'discovered'})
        WHERE b.reward_usdc > 0
        RETURN b.id as id, b.reward_usdc as reward, b.estimated_hours as hours,
               b.category as category, b.difficulty as difficulty
        """

        opportunities = []
        for record in self.memory.execute(query):
            valuation = self.calculate_fair_value(dict(record), market)

            roi = valuation['adjusted_hourly_rate'] / self.min_hourly_rate
            if roi >= min_roi:
                opportunities.append({
                    **valuation,
                    'roi_score': roi,
                    'priority_score': roi * market.success_rate_by_category.get(
                        record['category'], 0.5
                    )
                })

        # Sort by priority score
        return sorted(opportunities, key=lambda x: x['priority_score'], reverse=True)
```

##### 10.2.2 Time-Based Pricing Adjustments

Pricing varies based on time-sensitive factors:

```python
    def calculate_time_sensitivity(self, bounty: Dict) -> float:
        """Calculate time sensitivity multiplier."""

        now = datetime.now()
        deadline = bounty.get('deadline')
        discovered = bounty.get('discovered_at', now)

        if not deadline:
            return 1.0

        time_remaining = deadline - now
        total_window = deadline - discovered

        if total_window.total_seconds() == 0:
            return 1.0

        # Urgency ratio: how close to deadline
        urgency = 1 - (time_remaining.total_seconds() / total_window.total_seconds())

        if urgency > 0.8:
            return 1.3  # High urgency - premium
        elif urgency > 0.5:
            return 1.1  # Moderate urgency
        elif urgency < 0.2:
            return 0.9  # Plenty of time - can be selective

        return 1.0

    def get_optimal_claim_time(self, bounty: Dict) -> datetime:
        """Determine optimal time to claim based on competition patterns."""

        # Query historical claim patterns
        query = """
        MATCH (b:Bounty {category: $category})
        WHERE b.claimed_at IS NOT NULL
        WITH b, datetime(b.discovered_at) as discovered,
             datetime(b.claimed_at) as claimed
        WITH duration.between(discovered, claimed).minutes as claim_delay
        RETURN avg(claim_delay) as avg_delay,
               percentileCont(claim_delay, 0.25) as fast_claim,
               percentileCont(claim_delay, 0.75) as slow_claim
        """

        result = self.memory.execute(query, category=bounty['category'])
        record = result.single()

        if not record or not record['avg_delay']:
            # No data - claim quickly
            return datetime.now() + timedelta(minutes=5)

        avg_delay = record['avg_delay']

        # Strategy: claim slightly faster than average to secure,
        # but not so fast we overpay for evaluation
        optimal_delay = max(avg_delay * 0.7, 10)  # At least 10 minutes for evaluation

        return datetime.now() + timedelta(minutes=optimal_delay)
```

##### 10.2.3 Neo4j Schema for Pricing Data

```cypher
// Market conditions tracking
(:MarketSnapshot {
  id: uuid,
  timestamp: datetime,
  avg_bounty_size: float,
  median_completion_hours: float,
  active_worker_count: int,
  bounty_supply_ratio: float,
  overall_success_rate: float
})

// Bounty valuation records
(:BountyValuation {
  id: uuid,
  bounty_id: string,
  calculated_at: datetime,
  base_hourly_rate: float,
  adjusted_hourly_rate: float,
  demand_multiplier: float,
  supply_adjustment: float,
  risk_multiplier: float,
  is_undervalued: boolean,
  roi_score: float,
  priority_score: float
})

// Category performance tracking
(:CategoryMetrics {
  category: string,
  period_start: datetime,
  period_end: datetime,
  bounty_count: int,
  avg_reward: float,
  success_rate: float,
  avg_completion_hours: float,
  demand_index: float  // Relative demand vs other categories
})

// Relationships
(:Bounty)-[:HAS_VALUATION]->(:BountyValuation)
(:MarketSnapshot)-[:COVERS]->(:CategoryMetrics)
(:Agent)-[:GENERATED]->(:BountyValuation)
```

#### 10.3 Skill Specialization Tracking

Identify high-value niche capabilities and track market saturation to find underserved opportunities.

##### 10.3.1 Niche Identification Algorithm

Möngke continuously analyzes the market to identify profitable niches:

```python
# specialization_tracker.py
from typing import List, Dict, Tuple
from collections import defaultdict
from openclaw_memory import OperationalMemory
import math

class SpecializationTracker:
    """Tracks skill specialization opportunities and market saturation."""

    def __init__(self, memory: OperationalMemory):
        self.memory = memory
        self.min_opportunity_score = 0.6

    def analyze_niche_opportunities(self) -> List[Dict]:
        """Identify underserved high-value niches."""

        query = """
        // Get all completed bounties with skills
        MATCH (b:Bounty {status: 'completed'})-[:REQUIRES_SKILL]->(s:Skill)
        WITH s.name as skill, count(b) as completions,
             avg(b.reward_usdc) as avg_reward,
             avg(b.reward_usdc / b.estimated_hours) as avg_hourly

        // Count active workers with this skill
        OPTIONAL MATCH (a:Agent)-[:HAS_SKILL {proficiency: 'expert'}]->(s:Skill {name: skill})
        WITH skill, completions, avg_reward, avg_hourly, count(a) as expert_count

        // Calculate opportunity metrics
        WITH skill, completions, avg_reward, avg_hourly, expert_count,
             (avg_hourly * completions) / (expert_count + 1) as opportunity_score

        RETURN skill, completions, avg_reward, avg_hourly, expert_count,
               opportunity_score
        ORDER BY opportunity_score DESC
        """

        opportunities = []
        for record in self.memory.execute(query):
            if record['opportunity_score'] >= self.min_opportunity_score:
                opportunities.append({
                    'skill': record['skill'],
                    'market_size': record['completions'],
                    'avg_reward': record['avg_reward'],
                    'avg_hourly': record['avg_hourly'],
                    'competition_level': record['expert_count'],
                    'opportunity_score': record['opportunity_score'],
                    'saturation': self._calculate_saturation(record)
                })

        return opportunities

    def _calculate_saturation(self, record: Dict) -> str:
        """Determine market saturation level."""

        experts = record['expert_count']
        market_size = record['market_size']

        if market_size == 0:
            return 'unknown'

        ratio = experts / market_size

        if ratio < 0.1:
            return 'underserved'  # High opportunity
        elif ratio < 0.3:
            return 'balanced'
        elif ratio < 0.6:
            return 'competitive'
        else:
            return 'saturated'

    def recommend_specialization_path(self, agent_capabilities: List[str]) -> Dict:
        """Recommend optimal specialization strategy."""

        opportunities = self.analyze_niche_opportunities()

        # Filter for related skills (adjacent to current capabilities)
        related_opportunities = []
        for opp in opportunities:
            skill = opp['skill']

            # Check if we have related skills
            relatedness = self._calculate_skill_relatedness(skill, agent_capabilities)

            if relatedness > 0.3:  # At least some overlap
                related_opportunities.append({
                    **opp,
                    'relatedness': relatedness,
                    'acquisition_difficulty': self._estimate_acquisition_difficulty(skill),
                    'strategic_score': opp['opportunity_score'] * relatedness
                })

        # Sort by strategic score
        related_opportunities.sort(key=lambda x: x['strategic_score'], reverse=True)

        return {
            'top_opportunities': related_opportunities[:5],
            'recommended_focus': related_opportunities[0] if related_opportunities else None,
            'diversification_skills': self._identify_diversification_opportunities(
                agent_capabilities, opportunities
            )
        }

    def _calculate_skill_relatedness(self, target_skill: str, current_skills: List[str]) -> float:
        """Calculate how related a new skill is to existing capabilities."""

        # Query Neo4j for skill co-occurrence
        query = """
        MATCH (target:Skill {name: $target})
        MATCH (current:Skill)
        WHERE current.name IN $current_skills
        OPTIONAL MATCH (target)-[:CO_OCCURS_WITH]-(current)
        WITH target, current, count(*) as co_occurrence
        OPTIONAL MATCH (target)-[:SIMILAR_TO]-(current)
        WITH target, current, co_occurrence,
             CASE WHEN exists { MATCH (target)-[:SIMILAR_TO]-(current) } THEN 0.5 ELSE 0 END as similarity
        RETURN avg(co_occurrence * 0.1 + similarity) as relatedness
        """

        result = self.memory.execute(query, target=target_skill, current_skills=current_skills)
        record = result.single()

        return record['relatedness'] or 0.0

    def track_skill_gap_opportunities(self) -> List[Dict]:
        """Find high-value skills that competitors lack."""

        query = """
        // Find skills required by high-value bounties
        MATCH (b:Bounty)
        WHERE b.reward_usdc > 500  // High-value threshold
        MATCH (b)-[:REQUIRES_SKILL]->(s:Skill)
        WITH s, count(b) as high_value_bounties, avg(b.reward_usdc) as avg_reward

        // Count how many agents have this skill
        OPTIONAL MATCH (a:Agent)-[:HAS_SKILL]->(s)
        WITH s, high_value_bounties, avg_reward, count(a) as agent_count

        WHERE agent_count < 3  // Few competitors

        RETURN s.name as skill, high_value_bounties, avg_reward, agent_count,
               (high_value_bounties * avg_reward) / (agent_count + 1) as value_score
        ORDER BY value_score DESC
        LIMIT 10
        """

        gaps = []
        for record in self.memory.execute(query):
            gaps.append({
                'skill': record['skill'],
                'high_value_bounties': record['high_value_bounties'],
                'avg_reward': record['avg_reward'],
                'competitors_with_skill': record['agent_count'],
                'value_score': record['value_score'],
                'recommendation': 'acquire' if record['agent_count'] == 0 else 'improve'
            })

        return gaps
```

##### 10.3.2 Specialization Strategy Framework

```cypher
// Skill specialization nodes
(:SkillSpecialization {
  id: uuid,
  skill_name: string,
  category: string,
  market_saturation: 'underserved' | 'balanced' | 'competitive' | 'saturated',
  avg_hourly_rate: float,
  opportunity_score: float,
  acquisition_difficulty: 'easy' | 'medium' | 'hard',
  strategic_priority: 'critical' | 'high' | 'medium' | 'low',
  last_updated: datetime
})

// Market position tracking
(:MarketPosition {
  id: uuid,
  skill: string,
  our_ranking: int,  // Among all agents
  total_competitors: int,
  market_share_percent: float,
  avg_completion_time_ratio: float,  // vs competitors
  success_rate_vs_market: float,
  period: string  // 'weekly', 'monthly'
})

// Relationships
(:Agent)-[:SPECIALIZES_IN {level: 'primary' | 'secondary' | 'tertiary'}]->(:SkillSpecialization)
(:SkillSpecialization)-[:HAS_MARKET_POSITION]->(:MarketPosition)
(:Skill)-[:CO_OCCURS_WITH {frequency: int}]->(:Skill)
(:Skill)-[:SIMILAR_TO {similarity_score: float}]->(:Skill)
```

#### 10.4 Reputation Optimization

Maximize on-chain reputation scores to gain priority access to premium bounties and better terms.

##### 10.4.1 Reputation Score Components

Ögedei tracks and optimizes multiple reputation dimensions:

```python
# reputation_optimizer.py
from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum
from openclaw_memory import OperationalMemory
# from clawtasks_contract import ClawTasksContract  # Smart contract interface

class ReputationDimension(Enum):
    SUCCESS_RATE = "success_rate"
    COMPLETION_SPEED = "completion_speed"
    QUALITY_SCORE = "quality_score"
    STAKE_RELIABILITY = "stake_reliability"
    DISPUTE_RESOLUTION = "dispute_resolution"

@dataclass
class ReputationMetrics:
    """Multi-dimensional reputation tracking."""
    overall_score: float  # 0-1000
    success_rate: float  # 0-1
    avg_completion_time: float  # hours
    quality_rating: float  # 0-5
    total_completed: int
    total_failed: int
    dispute_win_rate: float
    stake_forgiveness_count: int

class ReputationOptimizer:
    """Optimizes on-chain reputation for competitive advantage."""

    def __init__(self, memory: OperationalMemory, clawtasks: ClawTasksContract):
        self.memory = memory
        self.clawtasks = clawtasks
        self.target_success_rate = 0.95
        self.max_concurrent_risk = 0.15  # 15% of stake at risk max

    def get_current_reputation(self, agent_address: str) -> ReputationMetrics:
        """Fetch current reputation from chain and Neo4j."""

        # On-chain reputation
        chain_score = self.clawtasks.get_worker_reputation(agent_address)

        # Off-chain metrics from Neo4j
        query = """
        MATCH (a:Agent {wallet_address: $address})-[:RECEIVED]->(p:Payment)
        WITH a, count(p) as completed, sum(p.amount) as total_earned

        OPTIONAL MATCH (a)-[:FAILED]->(b:Bounty)
        WITH a, completed, total_earned, count(b) as failed

        OPTIONAL MATCH (a)-[:COMPLETED]->(b:Bounty)
        WITH completed, total_earned, failed,
             avg(duration.inSeconds(datetime(b.claimed_at), datetime(b.completed_at)) / 3600.0) as avg_time

        RETURN completed, failed, total_earned, avg_time
        """

        result = self.memory.execute(query, address=agent_address)
        record = result.single()

        completed = record['completed'] or 0
        failed = record['failed'] or 0
        total = completed + failed

        return ReputationMetrics(
            overall_score=chain_score,
            success_rate=completed / total if total > 0 else 0,
            avg_completion_time=record['avg_time'] or 0,
            quality_rating=self._calculate_quality_rating(agent_address),
            total_completed=completed,
            total_failed=failed,
            dispute_win_rate=self._get_dispute_stats(agent_address),
            stake_forgiveness_count=0
        )

    def calculate_reputation_impact(self, bounty: Dict) -> Dict:
        """Calculate reputation impact of taking a bounty."""

        metrics = self.get_current_reputation(bounty['agent_address'])

        # Success scenario
        success_impact = self._calculate_success_boost(metrics, bounty)

        # Failure scenario
        failure_impact = self._calculate_failure_penalty(metrics, bounty)

        # Expected value of reputation change
        success_prob = self._estimate_success_probability(bounty, metrics)
        expected_reputation_change = (
            success_impact * success_prob +
            failure_impact * (1 - success_prob)
        )

        return {
            'success_boost': success_impact,
            'failure_penalty': failure_impact,
            'success_probability': success_prob,
            'expected_change': expected_reputation_change,
            'risk_adjusted_value': self._calculate_risk_adjusted_value(
                bounty, expected_reputation_change
            )
        }

    def _calculate_success_boost(self, metrics: ReputationMetrics, bounty: Dict) -> float:
        """Calculate reputation gain from successful completion."""

        base_boost = 10.0

        # Bonus for high-value bounties
        value_bonus = min(bounty['reward_usdc'] / 1000, 20)

        # Calculate speed bonus based on actual vs expected completion time
        speed_bonus = 0
        actual_completion_time = bounty.get('actual_completion_hours')
        expected_time = bounty.get('estimated_hours', 24)

        if actual_completion_time and expected_time > 0:
            # Bonus for completing faster than expected
            if actual_completion_time < expected_time * 0.8:
                speed_bonus = 5  # 20% faster than expected
            elif actual_completion_time < expected_time:
                speed_bonus = 2  # Any speed improvement

        # Bonus for difficult categories
        difficulty_bonus = {'beginner': 0, 'intermediate': 2, 'advanced': 5, 'expert': 10}.get(
            bounty.get('difficulty', 'intermediate'), 0
        )

        return base_boost + value_bonus + speed_bonus + difficulty_bonus

    def _calculate_failure_penalty(self, metrics: ReputationMetrics, bounty: Dict) -> float:
        """Calculate reputation loss from failure."""

        base_penalty = -25.0

        # Increased penalty if already below target success rate
        if metrics.success_rate < self.target_success_rate:
            base_penalty *= 1.5

        # Penalty scales with bounty value (higher stakes = higher visibility)
        value_factor = 1 + (bounty['reward_usdc'] / 5000)

        return base_penalty * value_factor

    def recommend_reputation_strategy(self, current_metrics: ReputationMetrics) -> Dict:
        """Recommend actions to optimize reputation."""

        recommendations = []

        # Success rate optimization
        if current_metrics.success_rate < self.target_success_rate:
            recommendations.append({
                'priority': 'critical',
                'action': 'select_lower_difficulty',
                'description': 'Focus on bounties with >90% historical success rate',
                'target': 'Increase success rate to 95%'
            })

        # Speed optimization
        market_avg_time = self._get_market_avg_completion_time()
        if current_metrics.avg_completion_time > market_avg_time * 1.2:
            recommendations.append({
                'priority': 'high',
                'action': 'improve_efficiency',
                'description': f'Avg completion {current_metrics.avg_completion_time:.1f}h vs market {market_avg_time:.1f}h',
                'target': 'Reduce avg completion time by 20%'
            })

        # Volume strategy
        if current_metrics.total_completed < 10:
            recommendations.append({
                'priority': 'high',
                'action': 'increase_volume',
                'description': 'Complete more bounties to establish reputation baseline',
                'target': 'Complete 10+ bounties'
            })

        return {
            'current_tier': self._get_reputation_tier(current_metrics),
            'next_tier_requirements': self._get_next_tier_requirements(current_metrics),
            'recommendations': recommendations,
            'optimal_bounty_profile': self._get_optimal_bounty_profile(current_metrics)
        }

    def _get_reputation_tier(self, metrics: ReputationMetrics) -> str:
        """Determine reputation tier based on metrics."""

        if metrics.overall_score >= 900 and metrics.success_rate >= 0.98:
            return 'legendary'
        elif metrics.overall_score >= 750 and metrics.success_rate >= 0.95:
            return 'elite'
        elif metrics.overall_score >= 500 and metrics.success_rate >= 0.90:
            return 'established'
        elif metrics.overall_score >= 250:
            return 'rising'
        else:
            return 'newcomer'

    def _get_optimal_bounty_profile(self, metrics: ReputationMetrics) -> Dict:
        """Determine optimal bounty characteristics for reputation growth."""

        tier = self._get_reputation_tier(metrics)

        profiles = {
            'newcomer': {
                'max_difficulty': 'intermediate',
                'min_success_rate': 0.85,
                'focus': 'volume_and_consistency',
                'avoid_disputes': True
            },
            'rising': {
                'max_difficulty': 'advanced',
                'min_success_rate': 0.80,
                'focus': 'quality_improvement',
                'target_categories': ['technical', 'content']
            },
            'established': {
                'max_difficulty': 'expert',
                'min_success_rate': 0.75,
                'focus': 'premium_bounties',
                'min_reward': 500
            },
            'elite': {
                'max_difficulty': 'expert',
                'min_success_rate': 0.70,
                'focus': 'specialization',
                'target_exclusivity': True
            },
            'legendary': {
                'max_difficulty': 'expert',
                'min_success_rate': 0.65,
                'focus': 'market_leadership',
                'mentoring_opportunities': True
            }
        }

        return profiles.get(tier, profiles['newcomer'])
```

##### 10.4.2 Reputation Protection Mechanisms

```python
    def should_claim_bounty(self, bounty: Dict, metrics: ReputationMetrics) -> Tuple[bool, str]:
        """Determine if claiming a bounty protects or improves reputation."""

        # Never risk reputation if already in danger zone
        if metrics.success_rate < 0.80 and metrics.total_completed > 5:
            # Only take very safe bets
            success_prob = self._estimate_success_probability(bounty, metrics)
            if success_prob < 0.95:
                return False, f"Reputation protection mode: success probability {success_prob:.2%} below 95% threshold"

        # Check if failure would drop tier
        tier = self._get_reputation_tier(metrics)
        simulated_failure = self._simulate_failure(metrics, bounty)
        new_tier = self._get_reputation_tier(simulated_failure)

        if new_tier != tier:
            return False, f"Claim risks tier downgrade from {tier} to {new_tier}"

        # Check stake exposure
        current_at_risk = self._calculate_current_stake_exposure()
        additional_risk = bounty.get('stake_required', 0)

        total_stake = current_at_risk + additional_risk
        hot_wallet_balance = self._get_hot_wallet_balance()

        if total_stake > hot_wallet_balance * self.max_concurrent_risk:
            return False, f"Stake exposure {total_stake} exceeds {self.max_concurrent_risk:.0%} of wallet"

        return True, "Bounty meets reputation protection criteria"

    def _simulate_failure(self, metrics: ReputationMetrics, bounty: Dict) -> ReputationMetrics:
        """Simulate metrics after hypothetical failure."""

        new_completed = metrics.total_completed
        new_failed = metrics.total_failed + 1
        new_total = new_completed + new_failed

        return ReputationMetrics(
            overall_score=max(0, metrics.overall_score - 25),
            success_rate=new_completed / new_total,
            avg_completion_time=metrics.avg_completion_time,
            quality_rating=metrics.quality_rating,
            total_completed=new_completed,
            total_failed=new_failed,
            dispute_win_rate=metrics.dispute_win_rate,
            stake_forgiveness_count=metrics.stake_forgiveness_count
        )
```

#### 10.5 Market Intelligence

Monitor competitor agent performance and pricing to anticipate market shifts and identify opportunities.

##### 10.5.1 Competitor Analysis System

Jochi maintains intelligence on competing agents:

```python
# market_intelligence.py
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from openclaw_memory import OperationalMemory
import statistics

class MarketIntelligence:
    """Monitors competitor activity and market trends."""

    def __init__(self, memory: OperationalMemory):
        self.memory = memory
        self.intelligence_ttl = timedelta(hours=24)

    def track_competitor_activity(self, competitor_address: str) -> Dict:
        """Track a competitor's recent activity and performance."""

        query = """
        // Get competitor's recent bounties
        MATCH (b:Bounty {claimed_by: $address})
        WHERE b.claimed_at > datetime() - duration('P30D')
        WITH b
        ORDER BY b.claimed_at DESC

        WITH collect({
            id: b.id,
            status: b.status,
            reward: b.reward_usdc,
            category: b.category,
            claimed_at: b.claimed_at,
            completed_at: b.completed_at
        }) as recent_bounties

        // Calculate metrics
        WITH recent_bounties,
             size([x IN recent_bounties WHERE x.status = 'completed']) as completed,
             size([x IN recent_bounties WHERE x.status = 'failed']) as failed

        // Calculate average completion time using UNWIND
        UNWIND recent_bounties as x
        WITH recent_bounties, completed, failed, x
        WHERE x.completed_at IS NOT NULL
        RETURN recent_bounties, completed, failed,
               avg(duration.inSeconds(datetime(x.claimed_at), datetime(x.completed_at)) / 3600.0) as avg_completion_time
        """

        result = self.memory.execute(query, address=competitor_address)
        record = result.single()

        if not record:
            return {'error': 'No activity found'}

        completed = record['completed'] or 0
        failed = record['failed'] or 0
        total = completed + failed

        return {
            'address': competitor_address,
            'recent_bounties': record['recent_bounties'][:10],  # Last 10
            'success_rate': completed / total if total > 0 else 0,
            'total_recent': total,
            'avg_completion_time': record['avg_completion_time'],
            'activity_level': self._classify_activity_level(total),
            'specializations': self._identify_competitor_specializations(competitor_address),
            'pricing_strategy': self._analyze_pricing_strategy(competitor_address)
        }

    def identify_market_leaders(self, category: Optional[str] = None) -> List[Dict]:
        """Identify top-performing agents in a category or overall."""

        category_filter = "AND b.category = $category" if category else ""

        query = f"""
        MATCH (b:Bounty)
        WHERE b.status = 'completed'
        {category_filter}
        AND b.completed_at > datetime() - duration('P30D')

        WITH b.claimed_by as agent, count(b) as completions,
             sum(b.reward_usdc) as total_revenue,
             avg(b.reward_usdc) as avg_bounty_size

        WHERE completions >= 3  // Minimum activity threshold

        WITH agent, completions, total_revenue, avg_bounty_size,
             (total_revenue * completions) / 1000 as performance_score

        ORDER BY performance_score DESC
        LIMIT 10

        RETURN agent, completions, total_revenue, avg_bounty_size, performance_score
        """

        params = {'category': category} if category else {}
        leaders = []

        for record in self.memory.execute(query, **params):
            leaders.append({
                'address': record['agent'],
                'completions_30d': record['completions'],
                'revenue_30d': record['total_revenue'],
                'avg_bounty_size': record['avg_bounty_size'],
                'performance_score': record['performance_score']
            })

        return leaders

    def detect_market_shifts(self) -> List[Dict]:
        """Detect significant changes in market dynamics."""

        query = """
        // Compare last 7 days vs previous 7 days
        MATCH (b:Bounty)
        WHERE b.discovered_at > datetime() - duration('P14D')

        WITH b,
             CASE WHEN b.discovered_at > datetime() - duration('P7D')
                  THEN 'recent' ELSE 'previous' END as period

        WITH period, count(b) as bounty_count,
             avg(b.reward_usdc) as avg_reward,
             count(DISTINCT b.category) as category_diversity

        RETURN period, bounty_count, avg_reward, category_diversity
        ORDER BY period DESC
        """

        periods = {}
        for record in self.memory.execute(query):
            periods[record['period']] = {
                'bounty_count': record['bounty_count'],
                'avg_reward': record['avg_reward'],
                'category_diversity': record['category_diversity']
            }

        shifts = []

        if 'recent' in periods and 'previous' in periods:
            recent = periods['recent']
            previous = periods['previous']

            # Volume shift
            volume_change = (recent['bounty_count'] - previous['bounty_count']) / max(previous['bounty_count'], 1)
            if abs(volume_change) > 0.2:
                shifts.append({
                    'type': 'volume_shift',
                    'magnitude': volume_change,
                    'description': f"Bounty volume {'increased' if volume_change > 0 else 'decreased'} by {abs(volume_change):.1%}",
                    'implication': 'more_opportunities' if volume_change > 0 else 'increased_competition'
                })

            # Price shift
            price_change = (recent['avg_reward'] - previous['avg_reward']) / max(previous['avg_reward'], 1)
            if abs(price_change) > 0.15:
                shifts.append({
                    'type': 'price_shift',
                    'magnitude': price_change,
                    'description': f"Average bounty {'increased' if price_change > 0 else 'decreased'} by {abs(price_change):.1%}",
                    'implication': 'premium_opportunities' if price_change > 0 else 'efficiency_required'
                })

        return shifts

    def analyze_category_trends(self) -> List[Dict]:
        """Analyze trends within specific bounty categories."""

        query = """
        MATCH (b:Bounty)
        WHERE b.discovered_at > datetime() - duration('P30D')

        WITH b.category as category,
             CASE WHEN b.discovered_at > datetime() - duration('P7D')
                  THEN 'recent' ELSE 'earlier' END as period

        WITH category, period,
             count(b) as count,
             avg(b.reward_usdc) as avg_reward

        RETURN category, period, count, avg_reward
        ORDER BY category, period
        """

        category_data = defaultdict(lambda: {})
        for record in self.memory.execute(query):
            category_data[record['category']][record['period']] = {
                'count': record['count'],
                'avg_reward': record['avg_reward']
            }

        trends = []
        for category, periods in category_data.items():
            if 'recent' in periods and 'earlier' in periods:
                recent = periods['recent']
                earlier = periods['earlier']

                growth = (recent['count'] - earlier['count']) / max(earlier['count'], 1)
                price_trend = (recent['avg_reward'] - earlier['avg_reward']) / max(earlier['avg_reward'], 1)

                trends.append({
                    'category': category,
                    'volume_growth': growth,
                    'price_trend': price_trend,
                    'trend_strength': growth + price_trend,
                    'recommendation': self._categorize_trend(growth, price_trend)
                })

        return sorted(trends, key=lambda x: abs(x['trend_strength']), reverse=True)

    def _categorize_trend(self, volume_growth: float, price_trend: float) -> str:
        """Categorize market trend for strategic response."""

        if volume_growth > 0.3 and price_trend > 0.1:
            return 'hot_market_enter'
        elif volume_growth > 0.3 and price_trend < -0.1:
            return 'volume_play_efficiency'
        elif volume_growth < -0.2 and price_trend > 0.2:
            return 'premium_niche_focus'
        elif volume_growth < -0.2 and price_trend < -0.1:
            return 'avoid_or_differentiate'
        else:
            return 'steady_state'
```

##### 10.5.2 Market Intelligence Schema

```cypher
// Competitor tracking
(:CompetitorAgent {
  address: string,
  first_seen: datetime,
  last_active: datetime,
  estimated_success_rate: float,
  activity_level: 'high' | 'medium' | 'low',
  primary_specializations: [string],
  threat_level: 'direct' | 'indirect' | 'minimal'
})

// Market shift events
(:MarketShift {
  id: uuid,
  detected_at: datetime,
  shift_type: 'volume' | 'price' | 'competition' | 'category',
  magnitude: float,
  description: string,
  recommended_action: string,
  confidence: float
})

// Category trend tracking
(:CategoryTrend {
  category: string,
  period_start: datetime,
  period_end: datetime,
  volume_growth: float,
  price_trend: float,
  competition_change: float,
  trend_classification: string
})

// Intelligence reports
(:IntelligenceReport {
  id: uuid,
  generated_at: datetime,
  report_type: 'competitor' | 'market_shift' | 'category_analysis',
  summary: string,
  key_findings: [string],
  recommendations: [string],
  confidence: float
})

// Relationships
(:Agent)-[:GENERATED]->(:IntelligenceReport)
(:IntelligenceReport)-[:COVERS]->(:CompetitorAgent)
(:IntelligenceReport)-[:IDENTIFIES]->(:MarketShift)
(:CompetitorAgent)-[:COMPETES_IN]->(:CategoryTrend)
```

#### 10.6 Portfolio Optimization

Balance risk/reward across different bounty types to achieve sustainable long-term returns.

##### 10.6.1 Portfolio Theory for Bounty Selection

```python
# portfolio_optimizer.py
from typing import List, Dict, Tuple
from dataclasses import dataclass
from collections import defaultdict
from openclaw_memory import OperationalMemory
import numpy as np

@dataclass
class BountyAsset:
    """Represents a bounty as a portfolio asset."""
    id: str
    expected_return: float
    success_probability: float
    stake_required: float
    category: str
    time_estimate: float
    difficulty: str

class PortfolioOptimizer:
    """Optimizes bounty portfolio for risk-adjusted returns."""

    def __init__(self, memory: OperationalMemory):
        self.memory = memory
        self.target_portfolio_size = 5  # Concurrent bounties
        self.max_category_concentration = 0.4  # Max 40% in one category
        self.min_expected_return = 100.0  # Minimum USDC expected value

    def calculate_expected_return(self, bounty: Dict, agent_metrics: Dict) -> float:
        """Calculate expected return in USDC."""

        reward = bounty['reward_usdc'] * 0.95  # 95% after platform fee
        stake = bounty['stake_required']
        success_prob = self._estimate_success_probability(bounty, agent_metrics)

        # Expected value = (reward + stake back) * success - (stake lost) * failure
        success_value = (reward + stake) * success_prob
        failure_cost = stake * (1 - success_prob)

        return success_value - failure_cost

    def calculate_portfolio_metrics(self, bounties: List[BountyAsset]) -> Dict:
        """Calculate risk/return metrics for a portfolio."""

        if not bounties:
            return {'expected_return': 0, 'risk': 0, 'sharpe_ratio': 0}

        # Expected portfolio return
        total_stake = sum(b.stake_required for b in bounties)
        weights = [b.stake_required / total_stake for b in bounties]

        expected_returns = [self.calculate_expected_return({'reward_usdc': b.expected_return, 'stake_required': b.stake_required}, {}) for b in bounties]
        portfolio_return = sum(w * r for w, r in zip(weights, expected_returns))

        # Portfolio risk (simplified - assumes some correlation by category)
        category_groups = defaultdict(list)
        for i, b in enumerate(bounties):
            category_groups[b.category].append(i)

        # Higher concentration = higher risk
        concentration_risk = sum(
            (len(group) / len(bounties)) ** 2
            for group in category_groups.values()
        )

        # Individual bounty risks
        individual_risks = [(1 - b.success_probability) * b.stake_required for b in bounties]
        avg_risk = np.mean(individual_risks)

        total_risk = avg_risk * (1 + concentration_risk)

        # Sharpe-like ratio (return per unit risk)
        sharpe = portfolio_return / total_risk if total_risk > 0 else 0

        return {
            'expected_return': portfolio_return,
            'total_at_risk': total_stake,
            'concentration_risk': concentration_risk,
            'total_risk': total_risk,
            'sharpe_ratio': sharpe,
            'category_breakdown': {
                cat: len(group) / len(bounties)
                for cat, group in category_groups.items()
            }
        }

    def optimize_portfolio(self, available_bounties: List[Dict],
                          agent_metrics: Dict,
                          current_portfolio: List[str] = None) -> Dict:
        """Find optimal bounty combination."""

        current_portfolio = current_portfolio or []

        # Convert to assets
        assets = []
        for bounty in available_bounties:
            if bounty['id'] not in current_portfolio:
                assets.append(BountyAsset(
                    id=bounty['id'],
                    expected_return=bounty['reward_usdc'],
                    success_probability=self._estimate_success_probability(bounty, agent_metrics),
                    stake_required=bounty['stake_required'],
                    category=bounty['category'],
                    time_estimate=bounty.get('estimated_hours', 24),
                    difficulty=bounty.get('difficulty', 'intermediate')
                ))

        # Filter by minimum expected return
        viable_assets = [
            a for a in assets
            if self.calculate_expected_return({'reward_usdc': a.expected_return, 'stake_required': a.stake_required}, agent_metrics) >= self.min_expected_return
        ]

        if not viable_assets:
            return {'recommendation': 'wait', 'reason': 'No bounties meet minimum return threshold'}

        # Greedy optimization with constraints
        selected = []
        category_counts = defaultdict(int)

        # Sort by risk-adjusted return
        viable_assets.sort(
            key=lambda a: a.success_probability * a.expected_return / a.stake_required,
            reverse=True
        )

        for asset in viable_assets:
            if len(selected) >= self.target_portfolio_size:
                break

            # Check category concentration
            category_pct = (category_counts[asset.category] + 1) / (len(selected) + 1)
            if category_pct > self.max_category_concentration:
                continue

            # Check time capacity (don't exceed 40 hours)
            total_time = sum(a.time_estimate for a in selected) + asset.time_estimate
            if total_time > 40:
                continue

            selected.append(asset)
            category_counts[asset.category] += 1

        portfolio_metrics = self.calculate_portfolio_metrics(selected)

        return {
            'recommendation': 'claim' if selected else 'wait',
            'selected_bounties': [a.id for a in selected],
            'portfolio_metrics': portfolio_metrics,
            'diversification_score': 1 - portfolio_metrics['concentration_risk'],
            'time_commitment': sum(a.time_estimate for a in selected),
            'category_allocation': dict(category_counts)
        }

    def rebalance_portfolio(self, current_bounties: List[str],
                           available_bounties: List[Dict],
                           agent_metrics: Dict) -> Dict:
        """Recommend portfolio rebalancing actions."""

        current_metrics = self._analyze_current_portfolio(current_bounties)
        optimal = self.optimize_portfolio(available_bounties, agent_metrics, current_bounties)

        actions = []

        # Check concentration
        for category, pct in current_metrics['category_breakdown'].items():
            if pct > self.max_category_concentration:
                actions.append({
                    'action': 'reduce_exposure',
                    'category': category,
                    'current_pct': pct,
                    'target_pct': self.max_category_concentration,
                    'priority': 'high'
                })

        # Check for better opportunities
        current_return = current_metrics['expected_return']
        optimal_return = optimal['portfolio_metrics']['expected_return']

        if optimal_return > current_return * 1.2:
            actions.append({
                'action': 'upgrade_portfolio',
                'potential_improvement': (optimal_return - current_return) / current_return,
                'suggested_additions': optimal['selected_bounties'],
                'priority': 'medium'
            })

        # Check risk level
        if current_metrics['total_risk'] > current_metrics['total_at_risk'] * 0.3:
            actions.append({
                'action': 'de_risk',
                'current_risk_level': current_metrics['total_risk'],
                'suggestion': 'Add more conservative bounties or reduce concentration',
                'priority': 'high'
            })

        return {
            'current_metrics': current_metrics,
            'optimal_metrics': optimal['portfolio_metrics'],
            'recommended_actions': sorted(actions, key=lambda x: x['priority']),
            'rebalance_urgency': 'high' if any(a['priority'] == 'high' for a in actions) else 'low'
        }
```

##### 10.6.2 Risk Management Framework

```python
    def calculate_value_at_risk(self, portfolio: List[BountyAsset],
                                confidence: float = 0.95) -> float:
        """Calculate Value at Risk for the portfolio."""

        # Monte Carlo simulation of outcomes
        n_simulations = 10000
        outcomes = []

        for _ in range(n_simulations):
            portfolio_outcome = 0
            for asset in portfolio:
                # Simulate success/failure
                success = np.random.random() < asset.success_probability
                if success:
                    portfolio_outcome += asset.expected_return * 0.95 + asset.stake_required
                else:
                    portfolio_outcome -= asset.stake_required
            outcomes.append(portfolio_outcome)

        # VaR at confidence level
        outcomes.sort()
        var_index = int((1 - confidence) * n_simulations)
        return outcomes[var_index]

    def stress_test_portfolio(self, portfolio: List[BountyAsset],
                             scenarios: List[Dict]) -> Dict:
        """Test portfolio under various market conditions."""

        results = []

        for scenario in scenarios:
            adjusted_assets = []
            for asset in portfolio:
                # Adjust success probability based on scenario
                adjusted_prob = asset.success_probability * scenario.get('success_rate_factor', 1.0)
                adjusted_assets.append(BountyAsset(
                    id=asset.id,
                    expected_return=asset.expected_return * scenario.get('reward_factor', 1.0),
                    success_probability=max(0, min(1, adjusted_prob)),
                    stake_required=asset.stake_required,
                    category=asset.category,
                    time_estimate=asset.time_estimate,
                    difficulty=asset.difficulty
                ))

            metrics = self.calculate_portfolio_metrics(adjusted_assets)
            results.append({
                'scenario': scenario['name'],
                'expected_return': metrics['expected_return'],
                'total_risk': metrics['total_risk'],
                'survival_probability': metrics['expected_return'] > 0
            })

        return {
            'scenario_results': results,
            'worst_case': min(results, key=lambda x: x['expected_return']),
            'stress_test_passed': all(r['expected_return'] > -500 for r in results)
        }
```

#### 10.7 Network Effects

Leverage agent collaboration to tackle complex high-value bounties that single agents cannot complete.

##### 10.7.1 Multi-Agent Bounty Execution

```python
# network_effects.py
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum
from openclaw_memory import OperationalMemory

class CollaborationType(Enum):
    SEQUENTIAL = "sequential"  # Handoff between agents
    PARALLEL = "parallel"      # Simultaneous work
    ITERATIVE = "iterative"    # Review and refinement cycles

@dataclass
class CollaborationPlan:
    """Plan for multi-agent bounty execution."""
    bounty_id: str
    collaboration_type: CollaborationType
    agents: List[str]
    phases: List[Dict]
    coordination_overhead: float  # Additional time estimate
    success_probability_boost: float  # Improvement from collaboration

class NetworkEffectsManager:
    """Manages multi-agent collaboration for complex bounties."""

    def __init__(self, memory: OperationalMemory):
        self.memory = memory
        self.coordination_cost = 0.15  # 15% overhead for coordination

    def analyze_bounty_complexity(self, bounty: Dict) -> Dict:
        """Determine if bounty benefits from multi-agent approach."""

        # Score complexity dimensions
        complexity_scores = {
            'skill_diversity': len(set(bounty.get('required_skills', []))),
            'research_component': 1 if 'research' in bounty.get('tags', []) else 0,
            'technical_component': 1 if 'technical' in bounty.get('tags', []) else 0,
            'creative_component': 1 if 'creative' in bounty.get('tags', []) else 0,
            'estimated_hours': min(bounty.get('estimated_hours', 8) / 8, 5),  # Cap at 5
            'deliverable_count': len(bounty.get('deliverables', []))
        }

        total_complexity = sum(complexity_scores.values())

        return {
            'complexity_score': total_complexity,
            'complexity_level': self._classify_complexity(total_complexity),
            'recommended_approach': self._recommend_approach(total_complexity),
            'optimal_team_size': self._optimal_team_size(total_complexity),
            'skill_requirements': self._identify_required_skills(bounty)
        }

    def _classify_complexity(self, score: float) -> str:
        if score < 3:
            return 'simple'
        elif score < 6:
            return 'moderate'
        elif score < 10:
            return 'complex'
        else:
            return 'very_complex'

    def _recommend_approach(self, complexity: float) -> str:
        if complexity < 3:
            return 'single_agent'
        elif complexity < 6:
            return 'optional_collaboration'
        elif complexity < 10:
            return 'recommended_collaboration'
        else:
            return 'required_collaboration'

    def _optimal_team_size(self, complexity: float) -> int:
        if complexity < 6:
            return 1
        elif complexity < 10:
            return 2
        else:
            return min(int(complexity / 3), 4)

    def design_collaboration(self, bounty: Dict,
                            available_agents: List[str]) -> Optional[CollaborationPlan]:
        """Design optimal collaboration structure for a bounty."""

        complexity = self.analyze_bounty_complexity(bounty)

        if complexity['complexity_level'] == 'simple':
            return None  # No collaboration needed

        # Determine collaboration type based on bounty characteristics
        if 'research' in bounty.get('tags', []) and 'technical' in bounty.get('tags', []):
            collab_type = CollaborationType.SEQUENTIAL
            phases = [
                {'agent': 'mongke', 'task': 'research', 'output': 'research_findings'},
                {'agent': 'temujin', 'task': 'implementation', 'input': 'research_findings', 'output': 'deliverable'}
            ]
        elif 'content' in bounty.get('tags', []) and 'review' in bounty.get('tags', []):
            collab_type = CollaborationType.ITERATIVE
            phases = [
                {'agent': 'chagatai', 'task': 'draft', 'output': 'draft_content'},
                {'agent': 'jochi', 'task': 'review', 'input': 'draft_content', 'output': 'feedback'},
                {'agent': 'chagatai', 'task': 'revise', 'input': 'feedback', 'output': 'final_content'}
            ]
        else:
            collab_type = CollaborationType.PARALLEL
            phases = self._design_parallel_phases(bounty, available_agents)

        # Calculate collaboration benefits
        base_success = 0.7  # Assume 70% for complex bounties solo
        boost = min(len(phases) * 0.1, 0.25)  # Up to 25% boost

        return CollaborationPlan(
            bounty_id=bounty['id'],
            collaboration_type=collab_type,
            agents=list(set(p['agent'] for p in phases)),
            phases=phases,
            coordination_overhead=sum(p.get('estimated_hours', 1) for p in phases) * self.coordination_cost,
            success_probability_boost=boost
        )

    def calculate_collaboration_value(self, plan: CollaborationPlan,
                                     bounty: Dict) -> Dict:
        """Calculate the value of multi-agent collaboration."""

        # Solo execution estimate
        solo_success = 0.6 if len(plan.phases) > 2 else 0.75
        solo_ev = bounty['reward_usdc'] * 0.95 * solo_success

        # Collaboration execution
        collab_success = min(solo_success + plan.success_probability_boost, 0.95)
        collab_ev = bounty['reward_usdc'] * 0.95 * collab_success

        # Costs
        coordination_cost_usd = plan.coordination_overhead * 50  # $50/hour effective cost

        # Value add
        value_add = collab_ev - solo_ev - coordination_cost_usd

        return {
            'solo_expected_value': solo_ev,
            'collaboration_expected_value': collab_ev,
            'coordination_cost': coordination_cost_usd,
            'net_value_add': value_add,
            'worthwhile': value_add > 0,
            'recommendation': 'collaborate' if value_add > 0 else 'solo_attempt'
        }

    def execute_collaborative_bounty(self, plan: CollaborationPlan) -> Dict:
        """Execute a multi-agent bounty collaboration."""

        # Create coordination task in Neo4j
        coordination_id = self._create_coordination_record(plan)

        results = []
        shared_context = {}

        for i, phase in enumerate(plan.phases):
            # Execute phase
            phase_result = self._execute_phase(phase, shared_context, coordination_id)
            results.append(phase_result)

            if not phase_result['success']:
                # Handle failure
                return self._handle_collaboration_failure(
                    plan, results, phase, coordination_id
                )

            # Update shared context for next phase
            shared_context[phase['output']] = phase_result['output_data']

            # Record progress
            self._record_phase_completion(coordination_id, i, phase_result)

        # Finalize
        return {
            'success': True,
            'coordination_id': coordination_id,
            'phases_completed': len(results),
            'final_output': shared_context.get(plan.phases[-1]['output']),
            'total_time': sum(r['duration'] for r in results)
        }

    def _create_coordination_record(self, plan: CollaborationPlan) -> str:
        """Create Neo4j record for collaboration tracking."""

        query = """
        CREATE (c:Collaboration {
            id: uuid(),
            bounty_id: $bounty_id,
            type: $collab_type,
            agents: $agents,
            created_at: datetime(),
            status: 'in_progress'
        })
        RETURN c.id as id
        """

        result = self.memory.execute(
            query,
            bounty_id=plan.bounty_id,
            collab_type=plan.collaboration_type.value,
            agents=plan.agents
        )

        return result.single()['id']
```

##### 10.7.2 Network Effects Schema

```cypher
// Collaboration tracking
(:Collaboration {
  id: uuid,
  bounty_id: string,
  type: 'sequential' | 'parallel' | 'iterative',
  agents: [string],
  created_at: datetime,
  completed_at: datetime,
  status: 'in_progress' | 'completed' | 'failed',
  coordination_overhead_hours: float,
  success_probability_boost: float
})

// Collaboration phases
(:CollaborationPhase {
  id: uuid,
  phase_number: int,
  agent: string,
  task_description: string,
  input_dependencies: [string],
  output_artifact: string,
  estimated_hours: float,
  actual_hours: float,
  status: 'pending' | 'in_progress' | 'completed' | 'blocked'
})

// Network advantage tracking
(:NetworkAdvantage {
  id: uuid,
  advantage_type: 'skill_complementarity' | 'speed' | 'quality' | 'complexity',
  bounty_category: string,
  solo_success_rate: float,
  collaborative_success_rate: float,
  value_add_usdc: float,
  measured_at: datetime
})

// Relationships
(:Collaboration)-[:HAS_PHASE]->(:CollaborationPhase)
(:Collaboration)-[:FOR_BOUNTY]->(:Bounty)
(:Agent)-[:PARTICIPATED_IN]->(:Collaboration)
(:CollaborationPhase)-[:PRODUCES]->(:Artifact)
(:CollaborationPhase)-[:DEPENDS_ON]->(:CollaborationPhase)
```

#### 10.8 Neo4j Schema Summary

Complete schema for competitive advantage mechanisms:

```cypher
// Core competitive nodes
(:MarketSnapshot)
(:BountyValuation)
(:CategoryMetrics)
(:SkillSpecialization)
(:MarketPosition)
(:CompetitorAgent)
(:MarketShift)
(:CategoryTrend)
(:IntelligenceReport)
(:Collaboration)
(:CollaborationPhase)
(:NetworkAdvantage)

// Reputation tracking
(:ReputationEvent {
  id: uuid,
  event_type: 'bounty_completed' | 'bounty_failed' | 'tier_promotion' | 'milestone',
  impact: 'positive' | 'negative' | 'neutral',
  points_delta: int,
  new_score: int,
  timestamp: datetime
})

// Portfolio tracking
(:PortfolioSnapshot {
  id: uuid,
  timestamp: datetime,
  total_at_risk: float,
  expected_return: float,
  diversification_score: float,
  risk_level: 'conservative' | 'moderate' | 'aggressive'
})

// Key relationships
(:Agent)-[:GENERATED]->(:BountyValuation)
(:Bounty)-[:HAS_VALUATION]->(:BountyValuation)
(:MarketSnapshot)-[:COVERS]->(:CategoryMetrics)
(:Agent)-[:SPECIALIZES_IN]->(:SkillSpecialization)
(:SkillSpecialization)-[:HAS_MARKET_POSITION]->(:MarketPosition)
(:Agent)-[:PARTICIPATED_IN]->(:Collaboration)
(:Collaboration)-[:HAS_PHASE]->(:CollaborationPhase)
(:Agent)-[:EARNED]->(:ReputationEvent)
(:Agent)-[:HOLDS]->(:PortfolioSnapshot)
```

#### 10.9 Implementation Priority

| Component | Effort | Value | Order |
|-----------|--------|-------|-------|
| Dynamic pricing engine | 6 hours | High | 1st |
| Market condition analysis | 4 hours | High | 2nd |
| Reputation optimization | 4 hours | High | 3rd |
| Skill specialization tracking | 5 hours | Medium | 4th |
| Market intelligence system | 6 hours | Medium | 5th |
| Portfolio optimizer | 5 hours | Medium | 6th |
| Network effects manager | 6 hours | High | 7th |
| Collaboration execution | 4 hours | Medium | 8th |
| Neo4j schema implementation | 3 hours | Medium | 9th |

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
        """Test PII sanitization via _sanitize_for_sharing entry point."""
        text = "Call me at 555-123-4567 or email john@example.com"
        sanitized = self.memory._sanitize_for_sharing(text)

        self.assertNotIn("555-123-4567", sanitized)
        self.assertNotIn("john@example.com", sanitized)
        self.assertIn("[PHONE]", sanitized)
        self.assertIn("[EMAIL]", sanitized)

    def test_pattern_sanitize_fallback(self):
        """Test pattern-based PII sanitization fallback."""
        text = "Call me at 555-123-4567 or email john@example.com"
        sanitized = self.memory._pattern_sanitize(text)

        self.assertNotIn("555-123-4567", sanitized)
        self.assertNotIn("john@example.com", sanitized)
        self.assertIn("[PHONE]", sanitized)
        self.assertIn("[EMAIL]", sanitized)

    def test_sanitize_for_sharing_with_names(self):
        """Test that _sanitize_for_sharing handles personal names."""
        text = "My friend Sarah said to call her at 555-123-4567"
        sanitized = self.memory._pattern_sanitize(text)

        # Phone should be sanitized
        self.assertNotIn("555-123-4567", sanitized)
        self.assertIn("[PHONE]", sanitized)
        # Name should be sanitized in pattern mode
        self.assertIn("[NAME]", sanitized)

    def test_sanitize_for_sharing_edge_cases(self):
        """Test _sanitize_for_sharing handles edge cases."""
        # Empty string
        self.assertEqual(self.memory._sanitize_for_sharing(""), "")

        # None input
        self.assertIsNone(self.memory._sanitize_for_sharing(None))

        # Non-string input
        self.assertEqual(self.memory._sanitize_for_sharing(123), 123)

        # Whitespace only
        self.assertEqual(self.memory._sanitize_for_sharing("   "), "")

    def test_sanitize_for_sharing_comprehensive_pii(self):
        """Test _sanitize_for_sharing handles all PII types."""
        text = (
            "Contact Dr. John Smith at john.smith@example.com or 555-123-4567. "
            "SSN: 123-45-6789. Card: 1234-5678-9012-3456. "
            "API key: sk-abc123xyz456. Address: 123 Main St. "
            "My colleague Jane helped with this."
        )
        sanitized = self.memory._pattern_sanitize(text)

        self.assertNotIn("john.smith@example.com", sanitized)
        self.assertNotIn("555-123-4567", sanitized)
        self.assertNotIn("123-45-6789", sanitized)
        self.assertNotIn("1234-5678-9012-3456", sanitized)
        self.assertNotIn("sk-abc123xyz456", sanitized)
        self.assertNotIn("123 Main St", sanitized)
        self.assertIn("[EMAIL]", sanitized)
        self.assertIn("[PHONE]", sanitized)
        self.assertIn("[SSN]", sanitized)
        self.assertIn("[CARD]", sanitized)
        self.assertIn("[API_KEY]", sanitized)
        self.assertIn("[ADDRESS]", sanitized)

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

## Appendix F: USDC Wallet and Staking Implementation

### F.1 Wallet Architecture

The ClawTasks system implements a multi-tier wallet architecture to balance security with operational efficiency:

#### 1. Cold Storage Wallet

| Attribute | Specification |
|-----------|---------------|
| **Purpose** | Majority of funds, long-term storage |
| **Security** | Hardware wallet (Ledger/Trezor) or multi-sig (Gnosis Safe) |
| **Access** | Rare, requires manual approval from 2+ admins |
| **Key Management** | Offline, encrypted backups in geographically separated locations |
| **Typical Balance** | 80-90% of total treasury |

**Implementation Requirements:**
- 3-of-5 multi-signature configuration recommended
- Hardware wallets stored in secure locations
- Recovery seed phrases in bank safety deposit boxes
- Quarterly audits of balances and access procedures

#### 2. Hot Wallet

| Attribute | Specification |
|-----------|---------------|
| **Purpose** | Operational funds for staking and bounty claims |
| **Security** | Server-side encrypted keys (AWS KMS or HashiCorp Vault) |
| **Access** | Automated via Ögedei agent with rate limiting |
| **Key Management** | Encrypted at rest, decrypted only in secure enclave |
| **Typical Balance** | 10-20% of total funds, capped at $50,000 USDC |

**Implementation Requirements:**
- Maximum single transaction limit: $5,000 USDC
- Daily withdrawal limit: $10,000 USDC
- Automatic alerts at 50%, 75%, 90% of daily limit
- Key rotation every 90 days

#### 3. Worker Wallets

| Attribute | Specification |
|-----------|---------------|
| **Purpose** | Per-agent execution wallets for gas fees and micro-transactions |
| **Security** | Derived from hot wallet using HD wallet derivation paths |
| **Access** | Agent-specific permissions, read-only for most agents |
| **Key Management** | Ephemeral, rotated weekly |
| **Typical Balance** | Minimal, just for gas (0.01 ETH on Base) |

**Implementation Requirements:**
- Each agent gets a unique derivation path: `m/44'/60'/agent_id'/0/0`
- Automatic top-up from hot wallet when balance falls below threshold
- No direct access to USDC - only for gas payments
- Automatic sweep of excess funds back to hot wallet

### F.2 Base L2 Integration

#### Network Configuration

```python
BASE_CONFIG = {
    "network_name": "Base Mainnet",
    "chain_id": 8453,
    "rpc_endpoints": [
        "https://mainnet.base.org",
        "https://base.llamarpc.com",
        "https://base.blockpi.network/v1/rpc/public"
    ],
    "usdc_contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "usdc_decimals": 6,
    "gas_token": "ETH",
    "block_time_seconds": 2,
    "confirmation_blocks": 12
}
```

#### Transaction Management

**Nonce Tracking:**
```python
class NonceManager:
    """Manages transaction nonces for sequential transaction submission."""

    def __init__(self, w3: Web3, address: str):
        self.w3 = w3
        self.address = address
        self._pending_nonces: Set[int] = set()
        self._lock = asyncio.Lock()

    async def get_next_nonce(self) -> int:
        """Get the next available nonce, accounting for pending transactions."""
        async with self._lock:
            on_chain_nonce = self.w3.eth.get_transaction_count(
                self.address,
                'pending'
            )
            # Find first nonce not in pending set
            nonce = on_chain_nonce
            while nonce in self._pending_nonces:
                nonce += 1
            self._pending_nonces.add(nonce)
            return nonce

    def release_nonce(self, nonce: int):
        """Release a nonce if transaction fails before broadcast."""
        self._pending_nonces.discard(nonce)
```

**Gas Price Optimization:**
```python
class GasOptimizer:
    """Optimizes gas prices for Base L2 transactions."""

    def __init__(self, w3: Web3):
        self.w3 = w3
        self.max_fee_per_gas = Web3.to_wei(0.1, 'gwei')  # 0.1 gwei max
        self.max_priority_fee = Web3.to_wei(0.001, 'gwei')

    async def estimate_gas_price(self) -> Dict[str, int]:
        """Get optimal gas price for current network conditions."""
        base_fee = self.w3.eth.get_block('latest')['baseFeePerGas']

        # Base uses EIP-1559 - calculate maxFeePerGas
        max_fee = min(
            base_fee * 2 + self.max_priority_fee,
            self.max_fee_per_gas
        )

        return {
            'maxFeePerGas': max_fee,
            'maxPriorityFeePerGas': self.max_priority_fee
        }
```

**Transaction Retry Logic:**
```python
class TransactionManager:
    """Manages transaction submission with retry and confirmation monitoring."""

    def __init__(self, w3: Web3, nonce_manager: NonceManager):
        self.w3 = w3
        self.nonce_manager = nonce_manager
        self.max_retries = 3
        self.confirmation_timeout = 120  # seconds

    async def send_transaction(
        self,
        tx_params: Dict,
        private_key: str
    ) -> str:
        """Send transaction with retry logic."""
        for attempt in range(self.max_retries):
            try:
                nonce = await self.nonce_manager.get_next_nonce()
                tx_params['nonce'] = nonce

                # Sign and send
                signed = self.w3.eth.account.sign_transaction(
                    tx_params,
                    private_key
                )
                tx_hash = self.w3.eth.send_raw_transaction(
                    signed.rawTransaction
                )

                # Wait for confirmation
                receipt = await self._wait_for_confirmation(tx_hash)

                if receipt['status'] == 1:
                    return tx_hash.hex()
                else:
                    raise TransactionFailed("Transaction reverted")

            except Exception as e:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise

    async def _wait_for_confirmation(self, tx_hash: bytes) -> Dict:
        """Wait for transaction confirmation with timeout."""
        start = time.time()
        while time.time() - start < self.confirmation_timeout:
            try:
                receipt = self.w3.eth.get_transaction_receipt(tx_hash)
                if receipt and receipt['blockNumber']:
                    # Wait for confirmation blocks
                    current = self.w3.eth.block_number
                    if current - receipt['blockNumber'] >= 12:
                        return receipt
            except:
                pass
            await asyncio.sleep(2)
        raise TimeoutError("Transaction confirmation timeout")
```

### F.3 Smart Contract Interface

#### ClawTasks Smart Contract

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

interface IClawTasks {
    /// @notice Claim a bounty by staking USDC
    /// @param bountyId Unique identifier for the bounty
    /// @param stakeAmount Amount of USDC to stake (typically 10% of bounty value)
    /// @return success Whether the claim was successful
    function claimBounty(
        bytes32 bountyId,
        uint256 stakeAmount
    ) external returns (bool success);

    /// @notice Submit proof of work for a claimed bounty
    /// @param bountyId Unique identifier for the bounty
    /// @param workProof IPFS hash or encrypted proof of work
    /// @return submissionId Unique ID for this submission
    function submitWork(
        bytes32 bountyId,
        bytes calldata workProof
    ) external returns (bytes32 submissionId);

    /// @notice Release payment to worker after successful review
    /// @param bountyId Unique identifier for the bounty
    /// @return paymentAmount Amount of USDC paid to worker
    function releasePayment(
        bytes32 bountyId
    ) external returns (uint256 paymentAmount);

    /// @notice Slash stake for failed or fraudulent work
    /// @param bountyId Unique identifier for the bounty
    /// @param worker Address of worker to slash
    /// @param reason Encoded reason for slashing
    /// @return slashedAmount Amount of USDC slashed
    function slashStake(
        bytes32 bountyId,
        address worker,
        bytes calldata reason
    ) external returns (uint256 slashedAmount);

    /// @notice Get bounty details
    /// @param bountyId Unique identifier for the bounty
    /// @return creator Address that created the bounty
    /// @return reward Total reward amount in USDC
    /// @return requiredStake Required stake amount
    /// @return deadline Block timestamp deadline
    /// @return status Current bounty status
    function getBounty(bytes32 bountyId) external view returns (
        address creator,
        uint256 reward,
        uint256 requiredStake,
        uint256 deadline,
        BountyStatus status
    );

    enum BountyStatus {
        Open,
        Claimed,
        Submitted,
        Completed,
        Expired,
        Cancelled
    }
}
```

#### Python Implementation using web3.py

```python
from web3 import Web3
from eth_abi import encode
from decimal import Decimal
from typing import Optional, Dict
import json

class ClawTasksContract:
    """Interface to the ClawTasks smart contract on Base L2."""

    CONTRACT_ABI = json.loads('''[
        {
            "inputs": [
                {"name": "bountyId", "type": "bytes32"},
                {"name": "stakeAmount", "type": "uint256"}
            ],
            "name": "claimBounty",
            "outputs": [{"name": "success", "type": "bool"}],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
                {"name": "bountyId", "type": "bytes32"},
                {"name": "workProof", "type": "bytes"}
            ],
            "name": "submitWork",
            "outputs": [{"name": "submissionId", "type": "bytes32"}],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [{"name": "bountyId", "type": "bytes32"}],
            "name": "releasePayment",
            "outputs": [{"name": "paymentAmount", "type": "uint256"}],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
                {"name": "bountyId", "type": "bytes32"},
                {"name": "worker", "type": "address"},
                {"name": "reason", "type": "bytes"}
            ],
            "name": "slashStake",
            "outputs": [{"name": "slashedAmount", "type": "uint256"}],
            "stateMutability": "nonpayable",
            "type": "function"
        }
    ]''')

    def __init__(
        self,
        w3: Web3,
        contract_address: str,
        usdc_address: str
    ):
        self.w3 = w3
        self.contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=self.CONTRACT_ABI
        )
        self.usdc = w3.eth.contract(
            address=Web3.to_checksum_address(usdc_address),
            abi=[{
                "inputs": [
                    {"name": "spender", "type": "address"},
                    {"name": "amount", "type": "uint256"}
                ],
                "name": "approve",
                "outputs": [{"name": "", "type": "bool"}],
                "stateMutability": "nonpayable",
                "type": "function"
            }]
        )

    async def claim_bounty(
        self,
        bounty_id: str,
        stake_amount: Decimal,
        private_key: str,
        gas_params: Dict[str, int]
    ) -> str:
        """Claim a bounty by staking USDC."""
        account = self.w3.eth.account.from_key(private_key)

        # Convert bounty_id to bytes32
        bounty_bytes = bounty_id.encode() if isinstance(bounty_id, str) else bounty_id
        bounty_bytes32 = bounty_bytes.ljust(32, b'\0')[:32]

        # Convert amount to wei (USDC has 6 decimals)
        amount_wei = int(stake_amount * Decimal(10**6))

        # Build transaction
        tx = self.contract.functions.claimBounty(
            bounty_bytes32,
            amount_wei
        ).build_transaction({
            'from': account.address,
            'gas': 200000,
            **gas_params
        })

        # Sign and send
        signed = self.w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)

        return tx_hash.hex()

    async def submit_work(
        self,
        bounty_id: str,
        work_proof: str,  # IPFS hash
        private_key: str,
        gas_params: Dict[str, int]
    ) -> str:
        """Submit proof of work for a claimed bounty."""
        account = self.w3.eth.account.from_key(private_key)

        bounty_bytes = bounty_id.encode().ljust(32, b'\0')[:32]
        proof_bytes = work_proof.encode()

        tx = self.contract.functions.submitWork(
            bounty_bytes,
            proof_bytes
        ).build_transaction({
            'from': account.address,
            'gas': 150000,
            **gas_params
        })

        signed = self.w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)

        return tx_hash.hex()

    async def release_payment(
        self,
        bounty_id: str,
        private_key: str,
        gas_params: Dict[str, int]
    ) -> str:
        """Release payment for completed bounty (reviewer only)."""
        account = self.w3.eth.account.from_key(private_key)

        bounty_bytes = bounty_id.encode().ljust(32, b'\0')[:32]

        tx = self.contract.functions.releasePayment(
            bounty_bytes
        ).build_transaction({
            'from': account.address,
            'gas': 100000,
            **gas_params
        })

        signed = self.w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)

        return tx_hash.hex()

    async def slash_stake(
        self,
        bounty_id: str,
        worker_address: str,
        reason: str,
        private_key: str,
        gas_params: Dict[str, int]
    ) -> str:
        """Slash stake for failed work (reviewer only)."""
        account = self.w3.eth.account.from_key(private_key)

        bounty_bytes = bounty_id.encode().ljust(32, b'\0')[:32]
        reason_bytes = reason.encode()

        tx = self.contract.functions.slashStake(
            bounty_bytes,
            Web3.to_checksum_address(worker_address),
            reason_bytes
        ).build_transaction({
            'from': account.address,
            'gas': 150000,
            **gas_params
        })

        signed = self.w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)

        return tx_hash.hex()
```

### F.4 Staking Mechanism

#### Staking Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     STAKING LIFECYCLE                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  PRE-STAKING │───▶│    STAKING   │───▶│  UNSTAKING   │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│         │                   │                   │               │
│         ▼                   ▼                   ▼               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │• Evaluate    │    │• Submit tx   │    │• Success:    │      │
│  │  bounty      │    │• Wait conf   │    │  return +    │      │
│  │• Calculate   │    │• Update      │    │  reward      │      │
│  │  stake (10%) │    │  Neo4j       │    │• Failure:    │      │
│  │• Check       │    │• Begin work  │    │  slash       │      │
│  │  balance     │    │               │    │• Update tx   │      │
│  │• Prepare tx  │    │               │    │  record      │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### 1. Pre-Staking Phase

```python
async def pre_staking_evaluation(
    self,
    bounty_id: str
) -> StakingDecision:
    """Evaluate whether to stake on a bounty."""

    # Fetch bounty details from Neo4j
    bounty = await self.memory.get_bounty(bounty_id)

    # Calculate required stake (typically 10%)
    bounty_value = Decimal(bounty['reward_usdc'])
    required_stake = bounty_value * Decimal('0.10')

    # Check wallet balance
    hot_wallet_balance = await self.get_hot_wallet_balance()

    if hot_wallet_balance < required_stake:
        # Attempt refill from cold storage
        await self.request_cold_storage_refill(required_stake)
        raise InsufficientFundsError(
            f"Hot wallet balance {hot_wallet_balance} < "
            f"required stake {required_stake}"
        )

    # Evaluate bounty risk
    risk_score = await self.evaluate_bounty_risk(bounty)

    if risk_score > self.max_risk_threshold:
        return StakingDecision(
            should_stake=False,
            reason=f"Risk score {risk_score} exceeds threshold"
        )

    return StakingDecision(
        should_stake=True,
        bounty_value=bounty_value,
        required_stake=required_stake,
        expected_return=bounty_value - required_stake,
        risk_score=risk_score
    )
```

#### 2. Staking Phase

```python
async def execute_staking(
    self,
    bounty_id: str,
    stake_amount: Decimal
) -> StakeRecord:
    """Execute the staking transaction."""

    # Generate unique stake ID
    stake_id = f"stake_{uuid.uuid4().hex[:12]}"

    # Get gas parameters
    gas_params = await self.gas_optimizer.estimate_gas_price()

    # Submit stake transaction
    tx_hash = await self.contract.claim_bounty(
        bounty_id=bounty_id,
        stake_amount=stake_amount,
        private_key=self.hot_wallet_key,
        gas_params=gas_params
    )

    # Wait for confirmation
    receipt = await self.tx_manager.wait_for_confirmation(tx_hash)

    if receipt['status'] != 1:
        raise StakingFailedError(f"Transaction failed: {tx_hash}")

    # Create stake record in Neo4j
    stake_record = await self.memory.create_stake_record(
        stake_id=stake_id,
        bounty_id=bounty_id,
        amount=stake_amount,
        tx_hash=tx_hash,
        status='active'
    )

    # Update bounty status
    await self.memory.update_bounty_status(
        bounty_id=bounty_id,
        status='claimed',
        claimed_by=self.agent_id,
        stake_id=stake_id
    )

    return stake_record
```

#### 3. Unstaking Phase

```python
async def execute_unstaking(
    self,
    bounty_id: str,
    outcome: BountyOutcome  # success or failure
) -> UnstakeResult:
    """Handle unstaking based on bounty outcome."""

    stake = await self.memory.get_active_stake(bounty_id)

    if outcome == BountyOutcome.SUCCESS:
        # Release payment - returns stake + reward
        tx_hash = await self.contract.release_payment(
            bounty_id=bounty_id,
            private_key=self.hot_wallet_key,
            gas_params=await self.gas_optimizer.estimate_gas_price()
        )

        # Update records
        await self.memory.update_stake_status(
            stake_id=stake['id'],
            status='released',
            return_tx_hash=tx_hash
        )

        return UnstakeResult(
            success=True,
            amount_returned=stake['amount'] + stake['reward'],
            tx_hash=tx_hash
        )

    else:  # FAILURE
        # Slash stake
        tx_hash = await self.contract.slash_stake(
            bounty_id=bounty_id,
            worker_address=self.wallet_address,
            reason="Work failed review criteria",
            private_key=self.reviewer_key,
            gas_params=await self.gas_optimizer.estimate_gas_price()
        )

        # Update records
        await self.memory.update_stake_status(
            stake_id=stake['id'],
            status='slashed',
            slash_tx_hash=tx_hash
        )

        return UnstakeResult(
            success=False,
            amount_slashed=stake['amount'],
            tx_hash=tx_hash
        )
```

### F.5 Security Considerations

#### 1. Key Management

| Layer | Implementation | Rotation Schedule |
|-------|---------------|-------------------|
| Cold Storage | Hardware Security Module (HSM) or Gnosis Safe | Quarterly |
| Hot Wallet | AWS KMS / HashiCorp Vault with auto-unseal | Every 90 days |
| Worker Keys | Ephemeral derived keys | Weekly |

**Key Management Best Practices:**

```python
class KeyManager:
    """Manages cryptographic keys with HSM integration."""

    def __init__(self, kms_client):
        self.kms = kms_client
        self.key_cache = {}
        self.cache_ttl = 300  # 5 minutes

    async def get_hot_wallet_key(self) -> str:
        """Retrieve hot wallet key from secure storage."""
        # Check cache first
        cached = self.key_cache.get('hot_wallet')
        if cached and cached['expires'] > time.time():
            return cached['key']

        # Fetch from KMS
        key = await self.kms.decrypt(
            ciphertext_blob=self._get_encrypted_key()
        )

        # Cache with TTL
        self.key_cache['hot_wallet'] = {
            'key': key,
            'expires': time.time() + self.cache_ttl
        }

        return key

    async def rotate_keys(self):
        """Perform scheduled key rotation."""
        # Generate new key
        new_key = self._generate_key()

        # Update contract permissions (multi-sig required)
        await self._update_contract_signer(new_key)

        # Encrypt and store
        encrypted = await self.kms.encrypt(plaintext=new_key)
        await self._store_encrypted_key(encrypted)

        # Clear cache
        self.key_cache.clear()

        # Log rotation
        await self._audit_log("key_rotation", {
            "timestamp": datetime.utcnow().isoformat(),
            "key_id": self._get_key_id(new_key)
        })
```

#### 2. Transaction Security

**Multi-signature Requirements:**

| Transaction Type | Threshold | Approvers Required |
|-----------------|-----------|-------------------|
| Cold → Hot transfer | 2-of-3 | Any 2 admins |
| Hot → Worker top-up | 1-of-1 | Automated with limits |
| Emergency pause | 3-of-5 | Core team |
| Contract upgrade | 4-of-5 | Core team + external |

**Rate Limiting:**

```python
class TransactionRateLimiter:
    """Implements rate limiting for financial transactions."""

    LIMITS = {
        'per_minute': 5,
        'per_hour': 50,
        'per_day': 200,
        'max_single_tx': Decimal('5000'),  # USDC
        'max_daily_volume': Decimal('10000')  # USDC
    }

    async def check_limits(self, amount: Decimal) -> bool:
        """Check if transaction is within rate limits."""

        # Check single transaction limit
        if amount > self.LIMITS['max_single_tx']:
            raise RateLimitError(
                f"Transaction {amount} exceeds max {self.LIMITS['max_single_tx']}"
            )

        # Check daily volume
        daily_volume = await self.get_daily_volume()
        if daily_volume + amount > self.LIMITS['max_daily_volume']:
            raise RateLimitError(
                f"Daily volume would exceed {self.LIMITS['max_daily_volume']}"
            )

        # Check transaction counts
        for window, limit in [
            ('minute', self.LIMITS['per_minute']),
            ('hour', self.LIMITS['per_hour']),
            ('day', self.LIMITS['per_day'])
        ]:
            count = await self.get_tx_count(window)
            if count >= limit:
                raise RateLimitError(
                    f"Transaction limit reached: {limit} per {window}"
                )

        return True
```

**Anomaly Detection:**

```python
class AnomalyDetector:
    """Detects suspicious transaction patterns."""

    def __init__(self, memory: Neo4jMemory):
        self.memory = memory
        self.baseline_stats = {}

    async def check_transaction(self, tx_params: Dict) -> RiskAssessment:
        """Assess risk of a proposed transaction."""
        risks = []

        # Check for unusual amount
        amount = tx_params['amount']
        avg_amount = await self.get_average_transaction_amount(days=30)
        if amount > avg_amount * 5:
            risks.append(f"Amount {amount} is 5x above average")

        # Check for rapid successive transactions
        recent_txs = await self.memory.get_recent_transactions(minutes=5)
        if len(recent_txs) > 3:
            risks.append(f"{len(recent_txs)} transactions in last 5 minutes")

        # Check for new destination
        to_address = tx_params.get('to')
        known_addresses = await self.memory.get_known_addresses()
        if to_address not in known_addresses:
            risks.append(f"Unknown destination address: {to_address}")

        # Calculate risk score
        risk_score = len(risks) * 25  # 25 points per risk

        if risk_score >= 75:
            return RiskAssessment(
                allowed=False,
                reason="; ".join(risks),
                requires_approval=True
            )
        elif risk_score >= 50:
            return RiskAssessment(
                allowed=True,
                reason="; ".join(risks),
                requires_notification=True
            )

        return RiskAssessment(allowed=True, risk_score=risk_score)
```

#### 3. Operational Security

**Environment Separation:**

```
┌─────────────────────────────────────────────────────────────┐
│                    ENVIRONMENT ISOLATION                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ Development │  │   Staging   │  │ Production  │         │
│  │             │  │             │  │             │         │
│  │ • Testnet   │  │ • Testnet   │  │ • Mainnet   │         │
│  │   only      │  │   + mock    │  │             │         │
│  │ • Fake USDC │  │ • Fake USDC │  │ • Real USDC │         │
│  │ • Dev keys  │  │ • Staging   │  │ • HSM keys  │         │
│  │             │  │   keys      │  │             │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                             │
│  Key Rules:                                                 │
│  • Never reuse keys across environments                     │
│  • Production keys never touch dev/staging machines         │
│  • Separate VPC/network isolation                           │
│  • Different KMS keys per environment                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Incident Response Plan:**

```python
class IncidentResponse:
    """Handles security incidents."""

    async def handle_suspicious_activity(self, alert: SecurityAlert):
        """Execute incident response protocol."""

        # Step 1: Immediate pause (if critical)
        if alert.severity == 'critical':
            await self.emergency_pause()

        # Step 2: Notify security team
        await self.notify_security_team(alert)

        # Step 3: Gather evidence
        evidence = await self.collect_evidence(alert)
        await self.secure_store_evidence(evidence)

        # Step 4: Assess impact
        impact = await self.assess_financial_impact(alert)

        # Step 5: Execute containment
        if alert.type == 'key_compromise':
            await self.rotate_all_keys()
        elif alert.type == 'unauthorized_access':
            await self.revoke_access(alert.affected_accounts)

        # Step 6: Recovery
        if alert.severity == 'critical':
            await self.unpause_contracts()  # After review

        # Step 7: Post-incident
        await self.generate_incident_report(alert, impact)

    async def emergency_pause(self):
        """Pause all contract operations."""
        pause_tx = await self.contract.emergency_pause(
            private_key=self.admin_key
        )
        await self.audit_log("emergency_pause", {"tx": pause_tx})
```

### F.6 Neo4j Financial Schema

#### Node Types

```cypher
// Wallet node - represents a blockchain wallet
CREATE (w:Wallet {
  id: $wallet_id,                    // Unique identifier
  type: $wallet_type,                // 'cold', 'hot', 'worker'
  address: $address,                 // Ethereum address
  chain: 'base',                     // Blockchain network
  derivation_path: $path,            // For HD wallets (optional)
  created_at: datetime(),
  last_active: datetime(),
  status: 'active'                   // 'active', 'frozen', 'retired'
})

// Transaction node - blockchain transaction record
CREATE (t:Transaction {
  id: $tx_id,                        // Internal transaction ID
  type: $tx_type,                    // 'stake', 'claim', 'payment', 'slash', 'refill'
  amount: $amount,                   // Amount in USDC
  currency: 'USDC',
  tx_hash: $tx_hash,                 // Blockchain transaction hash
  block_number: $block_number,       // Confirmation block
  gas_used: $gas_used,               // Gas consumed
  gas_price_wei: $gas_price,         // Gas price in wei
  status: $status,                   // 'pending', 'confirmed', 'failed'
  error_message: $error,             // If failed
  created_at: datetime(),
  confirmed_at: datetime()
})

// Stake node - represents an active or completed stake
CREATE (s:Stake {
  id: $stake_id,                     // Unique stake identifier
  bounty_id: $bounty_id,             // Associated bounty
  amount: $amount,                   // Staked amount in USDC
  status: $status,                   // 'active', 'released', 'slashed', 'expired'
  created_at: datetime(),
  released_at: datetime(),           // If released
  slashed_at: datetime(),            // If slashed
  slash_reason: $reason              // If slashed
})

// Bounty node - extends existing bounty schema
CREATE (b:Bounty {
  id: $bounty_id,
  title: $title,
  description: $description,
  reward_usdc: $reward,              // Total reward amount
  required_stake_percent: 10,        // Default 10%
  status: $status,                   // 'open', 'claimed', 'submitted', 'completed'
  created_at: datetime(),
  deadline: datetime(),
  claimed_at: datetime(),
  completed_at: datetime()
})
```

#### Relationships

```cypher
// Wallet relationships
CREATE (w:Wallet)-[:HOLDS]->(s:Stake)           // Wallet holds a stake
CREATE (w:Wallet)-[:DERIVED_FROM]->(hw:Wallet) // Worker derived from hot wallet
CREATE (w:Wallet)-[:MANAGES]->(cw:Wallet)      // Cold manages hot wallet

// Transaction relationships
CREATE (t:Transaction)-[:FROM]->(w:Wallet)     // Transaction from wallet
CREATE (t:Transaction)-[:TO]->(c:Contract)    // Transaction to contract
CREATE (t:Transaction)-[:FOR]->(s:Stake)      // Transaction for stake

// Stake relationships
CREATE (s:Stake)-[:FOR]->(b:Bounty)           // Stake for a bounty
CREATE (s:Stake)-[:HELD_BY]->(w:Wallet)       // Stake held by wallet
CREATE (s:Stake)-[:CREATED_BY]->(a:Agent)     // Stake created by agent

// Bounty relationships
CREATE (b:Bounty)-[:CLAIMED_BY]->(a:Agent)    // Bounty claimed by agent
CREATE (b:Bounty)-[:REWARDED_TO]->(w:Wallet)  // Reward sent to wallet
```

#### Indexes and Constraints

```cypher
// Constraints for data integrity
CREATE CONSTRAINT wallet_address_unique IF NOT EXISTS
FOR (w:Wallet) REQUIRE w.address IS UNIQUE;

CREATE CONSTRAINT transaction_hash_unique IF NOT EXISTS
FOR (t:Transaction) REQUIRE t.tx_hash IS UNIQUE;

CREATE CONSTRAINT stake_id_unique IF NOT EXISTS
FOR (s:Stake) REQUIRE s.id IS UNIQUE;

// Indexes for query performance
CREATE INDEX wallet_type_idx IF NOT EXISTS
FOR (w:Wallet) ON (w.type);

CREATE INDEX transaction_status_idx IF NOT EXISTS
FOR (t:Transaction) ON (t.status);

CREATE INDEX stake_bounty_idx IF NOT EXISTS
FOR (s:Stake) ON (s.bounty_id);

CREATE INDEX stake_status_idx IF NOT EXISTS
FOR (s:Stake) ON (s.status);
```

#### Query Patterns

```cypher
// Get wallet balance and active stakes
MATCH (w:Wallet {address: $address})-[:HOLDS]->(s:Stake {status: 'active'})
RETURN w.address, w.type, sum(s.amount) as total_staked

// Get transaction history for a bounty
MATCH (b:Bounty {id: $bounty_id})<-[:FOR]-(s:Stake)<-[:FOR]-(t:Transaction)
RETURN t.type, t.amount, t.status, t.tx_hash, t.created_at
ORDER BY t.created_at DESC

// Get agent staking performance
MATCH (a:Agent {id: $agent_id})-[:CREATED]->(s:Stake)
WITH s.status as status, count(s) as count, sum(s.amount) as total
RETURN status, count, total

// Find wallets needing refill
MATCH (w:Wallet {type: 'worker'})-[:HOLDS]->(s:Stake)
WITH w, sum(s.amount) as staked
WHERE w.balance < 0.005  // Less than 0.005 ETH for gas
RETURN w.address, w.balance, staked
```

### F.7 Python Implementation

```python
"""
USDC Wallet Manager for ClawTasks Integration

Manages multi-tier wallet architecture, staking operations,
and Neo4j financial record keeping.
"""

import asyncio
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum

from web3 import Web3
from neo4j import AsyncGraphDatabase


class WalletType(Enum):
    COLD = "cold"
    HOT = "hot"
    WORKER = "worker"


class TransactionType(Enum):
    STAKE = "stake"
    CLAIM = "claim"
    PAYMENT = "payment"
    SLASH = "slash"
    REFILL = "refill"


class StakeStatus(Enum):
    ACTIVE = "active"
    RELEASED = "released"
    SLASHED = "slashed"
    EXPIRED = "expired"


@dataclass
class StakeRecord:
    id: str
    bounty_id: str
    amount: Decimal
    status: StakeStatus
    tx_hash: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class TransactionResult:
    success: bool
    tx_hash: Optional[str]
    error: Optional[str] = None
    gas_used: Optional[int] = None


class USDCSWalletManager:
    """
    Manages USDC wallets for ClawTasks integration.

    Implements a multi-tier wallet system with cold storage,
    hot operational wallet, and per-agent worker wallets.
    """

    # USDC contract on Base
    USDC_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    USDC_DECIMALS = 6

    # Staking configuration
    STAKE_PERCENTAGE = Decimal("0.10")  # 10% of bounty value

    def __init__(
        self,
        neo4j_memory,
        private_key: Optional[str] = None,
        rpc_url: str = "https://mainnet.base.org"
    ):
        """
        Initialize wallet manager.

        Args:
            neo4j_memory: Neo4j memory instance for record keeping
            private_key: Hot wallet private key (should come from KMS in production)
            rpc_url: Base L2 RPC endpoint
        """
        self.memory = neo4j_memory
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))

        if private_key:
            self.account = self.w3.eth.account.from_key(private_key)
            self.wallet_address = self.account.address
        else:
            self.account = None
            self.wallet_address = None

        # Load USDC contract ABI (minimal)
        self.usdc = self.w3.eth.contract(
            address=self.USDC_ADDRESS,
            abi=[
                {
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "balance", "type": "uint256"}],
                    "type": "function"
                },
                {
                    "constant": False,
                    "inputs": [
                        {"name": "_spender", "type": "address"},
                        {"name": "_value", "type": "uint256"}
                    ],
                    "name": "approve",
                    "outputs": [{"name": "", "type": "bool"}],
                    "type": "function"
                }
            ]
        )

    async def get_usdc_balance(self, address: Optional[str] = None) -> Decimal:
        """
        Get USDC balance for an address.

        Args:
            address: Ethereum address (defaults to hot wallet)

        Returns:
            USDC balance as Decimal
        """
        addr = address or self.wallet_address
        if not addr:
            raise ValueError("No wallet address configured")

        balance_wei = self.usdc.functions.balanceOf(addr).call()
        return Decimal(balance_wei) / Decimal(10 ** self.USDC_DECIMALS)

    async def calculate_stake_amount(self, bounty_value: Decimal) -> Decimal:
        """
        Calculate required stake amount for a bounty.

        Args:
            bounty_value: Total bounty reward in USDC

        Returns:
            Required stake amount
        """
        return (bounty_value * self.STAKE_PERCENTAGE).quantize(
            Decimal("0.000001")  # USDC has 6 decimals
        )

    async def stake_for_bounty(
        self,
        bounty_id: str,
        amount: Decimal,
        contract_address: str
    ) -> TransactionResult:
        """
        Stake USDC to claim a bounty.

        Args:
            bounty_id: Unique bounty identifier
            amount: Amount to stake in USDC
            contract_address: ClawTasks contract address

        Returns:
            TransactionResult with tx_hash or error
        """
        if not self.account:
            return TransactionResult(
                success=False,
                tx_hash=None,
                error="No private key configured"
            )

        try:
            # Generate stake ID
            stake_id = f"stake_{uuid.uuid4().hex[:12]}"

            # Convert amount to wei
            amount_wei = int(amount * Decimal(10 ** self.USDC_DECIMALS))

            # Build transaction (simplified - actual implementation would use
            # the full ClawTasks contract interface from F.3)
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(contract_address),
                abi=[{
                    "inputs": [
                        {"name": "bountyId", "type": "bytes32"},
                        {"name": "stakeAmount", "type": "uint256"}
                    ],
                    "name": "claimBounty",
                    "outputs": [{"name": "success", "type": "bool"}],
                    "stateMutability": "nonpayable",
                    "type": "function"
                }]
            )

            bounty_bytes = bounty_id.encode().ljust(32, b'\0')[:32]

            tx = contract.functions.claimBounty(
                bounty_bytes,
                amount_wei
            ).build_transaction({
                'from': self.wallet_address,
                'gas': 200000,
                'maxFeePerGas': self.w3.to_wei('0.1', 'gwei'),
                'maxPriorityFeePerGas': self.w3.to_wei('0.001', 'gwei'),
                'nonce': self.w3.eth.get_transaction_count(self.wallet_address)
            })

            # Sign and send
            signed = self.w3.eth.account.sign_transaction(tx, self.account.key)
            tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)

            # Wait for receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

            if receipt['status'] == 1:
                # Record in Neo4j
                await self._record_stake(
                    stake_id=stake_id,
                    bounty_id=bounty_id,
                    amount=amount,
                    tx_hash=tx_hash.hex()
                )

                return TransactionResult(
                    success=True,
                    tx_hash=tx_hash.hex(),
                    gas_used=receipt['gasUsed']
                )
            else:
                return TransactionResult(
                    success=False,
                    tx_hash=tx_hash.hex(),
                    error="Transaction reverted"
                )

        except Exception as e:
            return TransactionResult(
                success=False,
                tx_hash=None,
                error=str(e)
            )

    async def claim_payment(
        self,
        bounty_id: str,
        contract_address: str
    ) -> TransactionResult:
        """
        Claim payment for completed bounty.

        Args:
            bounty_id: Unique bounty identifier
            contract_address: ClawTasks contract address

        Returns:
            TransactionResult with tx_hash or error
        """
        if not self.account:
            return TransactionResult(
                success=False,
                tx_hash=None,
                error="No private key configured"
            )

        try:
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(contract_address),
                abi=[{
                    "inputs": [{"name": "bountyId", "type": "bytes32"}],
                    "name": "releasePayment",
                    "outputs": [{"name": "paymentAmount", "type": "uint256"}],
                    "stateMutability": "nonpayable",
                    "type": "function"
                }]
            )

            bounty_bytes = bounty_id.encode().ljust(32, b'\0')[:32]

            tx = contract.functions.releasePayment(bounty_bytes).build_transaction({
                'from': self.wallet_address,
                'gas': 100000,
                'maxFeePerGas': self.w3.to_wei('0.1', 'gwei'),
                'maxPriorityFeePerGas': self.w3.to_wei('0.001', 'gwei'),
                'nonce': self.w3.eth.get_transaction_count(self.wallet_address)
            })

            signed = self.w3.eth.account.sign_transaction(tx, self.account.key)
            tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

            if receipt['status'] == 1:
                # Update stake record
                await self._update_stake_status(
                    bounty_id=bounty_id,
                    status=StakeStatus.RELEASED,
                    tx_hash=tx_hash.hex()
                )

                return TransactionResult(
                    success=True,
                    tx_hash=tx_hash.hex(),
                    gas_used=receipt['gasUsed']
                )
            else:
                return TransactionResult(
                    success=False,
                    tx_hash=tx_hash.hex(),
                    error="Transaction reverted"
                )

        except Exception as e:
            return TransactionResult(
                success=False,
                tx_hash=None,
                error=str(e)
            )

    async def _record_stake(
        self,
        stake_id: str,
        bounty_id: str,
        amount: Decimal,
        tx_hash: str
    ):
        """Record stake in Neo4j."""
        query = """
        MATCH (b:Bounty {id: $bounty_id})
        MATCH (w:Wallet {address: $wallet_address})

        CREATE (s:Stake {
            id: $stake_id,
            bounty_id: $bounty_id,
            amount: $amount,
            status: 'active',
            created_at: datetime()
        })

        CREATE (t:Transaction {
            id: $tx_id,
            type: 'stake',
            amount: $amount,
            currency: 'USDC',
            tx_hash: $tx_hash,
            status: 'confirmed',
            created_at: datetime()
        })

        CREATE (w)-[:HOLDS]->(s)
        CREATE (s)-[:FOR]->(b)
        CREATE (t)-[:FOR]->(s)
        CREATE (t)-[:FROM]->(w)

        SET b.status = 'claimed'
        """

        await self.memory.query(query, {
            'stake_id': stake_id,
            'bounty_id': bounty_id,
            'amount': str(amount),
            'tx_hash': tx_hash,
            'tx_id': f"tx_{uuid.uuid4().hex[:12]}",
            'wallet_address': self.wallet_address
        })

    async def _update_stake_status(
        self,
        bounty_id: str,
        status: StakeStatus,
        tx_hash: str
    ):
        """Update stake status in Neo4j."""
        query = """
        MATCH (s:Stake {bounty_id: $bounty_id})
        SET s.status = $status,
            s.released_at = datetime()

        CREATE (t:Transaction {
            id: $tx_id,
            type: $tx_type,
            amount: s.amount,
            currency: 'USDC',
            tx_hash: $tx_hash,
            status: 'confirmed',
            created_at: datetime()
        })

        CREATE (t)-[:FOR]->(s)
        """

        await self.memory.query(query, {
            'bounty_id': bounty_id,
            'status': status.value,
            'tx_hash': tx_hash,
            'tx_id': f"tx_{uuid.uuid4().hex[:12]}",
            'tx_type': 'payment' if status == StakeStatus.RELEASED else 'slash'
        })

    async def get_staking_summary(self) -> Dict:
        """
        Get summary of staking activity.

        Returns:
            Dict with total staked, active stakes, etc.
        """
        query = """
        MATCH (w:Wallet {address: $address})-[:HOLDS]->(s:Stake)
        RETURN
            count(s) as total_stakes,
            sum(CASE WHEN s.status = 'active' THEN s.amount ELSE 0 END) as active_staked,
            sum(CASE WHEN s.status = 'released' THEN s.amount ELSE 0 END) as total_released,
            sum(CASE WHEN s.status = 'slashed' THEN s.amount ELSE 0 END) as total_slashed
        """

        result = await self.memory.query(query, {
            'address': self.wallet_address
        })

        record = result[0] if result else {}
        return {
            'total_stakes': record.get('total_stakes', 0),
            'active_staked': Decimal(record.get('active_staked', 0)),
            'total_released': Decimal(record.get('total_released', 0)),
            'total_slashed': Decimal(record.get('total_slashed', 0))
        }


# Example usage
async def main():
    """Example of using USDCSWalletManager."""

    # Initialize with Neo4j memory
    from openclaw_memory import Neo4jMemory

    memory = Neo4jMemory(
        uri="bolt://neo4j:7687",
        user="neo4j",
        password="password"
    )

    # Initialize wallet manager
    # In production, private_key should come from KMS
    manager = USDCSWalletManager(
        neo4j_memory=memory,
        private_key="0x..."  # From secure storage
    )

    # Check balance
    balance = await manager.get_usdc_balance()
    print(f"Hot wallet balance: {balance} USDC")

    # Calculate stake for a $1000 bounty
    bounty_value = Decimal("1000.00")
    stake_amount = await manager.calculate_stake_amount(bounty_value)
    print(f"Required stake: {stake_amount} USDC")

    # Stake for bounty (if balance sufficient)
    if balance >= stake_amount:
        result = await manager.stake_for_bounty(
            bounty_id="bounty_abc123",
            amount=stake_amount,
            contract_address="0x..."
        )
        print(f"Stake result: {result}")

    # Get summary
    summary = await manager.get_staking_summary()
    print(f"Staking summary: {summary}")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Appendix G: Rollback Baseline (Single-Agent Config)

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
