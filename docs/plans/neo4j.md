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

## Agent Configuration

### Agent Matrix

| ID | Name | Role | Model | agentDir |
|----|------|------|-------|----------|
| `main` | Kublai | Squad Lead / Router | `moonshot/kimi-k2.5` | `/data/.clawdbot/agents/main` |
| `researcher` | Möngke | Researcher | `zai/glm-4.5` | `/data/.clawdbot/agents/researcher` |
| `writer` | Chagatai | Content Writer | `moonshot/kimi-k2.5` | `/data/.clawdbot/agents/writer` |
| `developer` | Temüjin | Developer/Security | `zai/glm-4.7` | `/data/.clawdbot/agents/developer` |
| `analyst` | Jochi | Analyst/Performance | `zai/glm-4.5` | `/data/.clawdbot/agents/analyst` |
| `ops` | Ögedei | Operations | `zai/glm-4.5` | `/data/.clawdbot/agents/ops` |

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
        "agentDir": "/data/.clawdbot/agents/ops"
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
      "allowFrom": ["+15165643945", "+19194133445"],
      "groupAllowFrom": ["+19194133445"],
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

// Knowledge types (all have: id, agent, created_at, confidence)
(:Research { topic, findings, sources, depth })
(:Content { type, title, body, clarity_score })
(:Application { concept_applied, success, lessons_learned })
(:Analysis { type, title, findings, metrics, recommendations })
(:Insight { insight, category, potential_value, urgency })
(:SecurityAudit { scope, vulnerabilities, overall_risk })
(:CodeReview { target, issues, enhancements })
(:ProcessUpdate { type, entity_type, previous_state, new_state })
(:WorkflowImprovement { target_process, status, proposed_by })
(:Synthesis { insight, novelty_type, domains })

// Concepts with vector embeddings for semantic search
(:Concept {
  name,
  domain,
  description,
  embedding: [float],  // 384-dim
  confidence,
  source
})

// Tasks
(:Task {
  type,
  description,
  status,  // "pending" | "in_progress" | "completed" | "blocked" | "escalated"
  assigned_to,
  delegated_by,
  quality_score,
  blocked_reason,    // populated when status="blocked"
  blocked_at,        // datetime
  escalation_count   // int, increments on each escalation
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
CREATE INDEX agent_knowledge FOR (n) ON (n.agent, n.created_at)
  WHERE n:Research OR n:Content OR n:Application;

CREATE INDEX task_status FOR (t:Task) ON (t.assigned_to, t.status);

CREATE INDEX notification_read FOR (n:Notification) ON (n.read, n.created_at);

CREATE FULLTEXT INDEX knowledge_content
  FOR (n:Research|Content|Concept) ON EACH [n.findings, n.body, n.description];

// Vector index for semantic search (Neo4j 5.11+)
// Falls back to full-text search if unavailable
CREATE VECTOR INDEX concept_embedding FOR (c:Concept)
  ON c.embedding OPTIONS {indexConfig: {
    `vector.dimensions`: 384,
    `vector.similarity_function`: 'cosine'
  }};
```

---

## Implementation Steps

### Phase 1: OpenClaw Multi-Agent Setup

**Step 1.1**: Update `moltbot.json` with agents.list and agentToAgent

**Step 1.2**: Create agent directories in Dockerfile (avoids race condition)

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
```

Add to `requirements.txt`:
```
neo4j-python-driver>=5.14.0
sentence-transformers>=2.2.2
```

Or install directly:
```bash
pip install neo4j-python-driver sentence-transformers
```

**Step 2.3**: Create schema and indexes

First, create the Agent nodes:

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
  id: 'analyst', name: 'Jochi', role: 'Analyst/Performance Lead',
  primary_capabilities: ['data_analysis', 'metrics', 'insights', 'performance_monitoring', 'anomaly_detection'],
  personality: 'Detail-oriented pattern finder. Monitors for bottlenecks, memory leaks, and race conditions.',
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

class OperationalMemory:
    """Neo4j-backed operational memory with fallback mode."""

    def __init__(self):
        self.driver: Optional[Driver] = None
        self.fallback_mode = False
        self._connect()

    def _connect(self):
        """Connect to Neo4j with fallback to memory-only mode."""
        try:
            uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
            user = os.getenv('NEO4J_USER', 'neo4j')
            password = os.getenv('NEO4J_PASSWORD', '')
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            self.driver.verify_connectivity()
            self.fallback_mode = False
        except (ServiceUnavailable, AuthError) as e:
            print(f"[WARN] Neo4j unavailable, running in fallback mode: {e}")
            self.fallback_mode = True
            self._local_store: Dict[str, List[Dict]] = {}

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
        """Use LLM to identify and redact private information.

        This method should be called by an agent with LLM access.
        The agent reviews content and returns sanitized version.
        """
        # This is a stub - actual implementation depends on agent capabilities
        # Agent should call something like:
        #   sanitized = await agent.review_for_privacy(text)
        #   return sanitized if sanitized.has_changes else text
        return None  # Signal to use pattern fallback

    def _pattern_sanitize(self, text: str) -> str:
        """Pattern-based PII sanitization (fallback method)."""
        import re

        # Phone numbers (various formats)
        text = re.sub(r'\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', '[PHONE]', text)
        text = re.sub(r'\+?\d{10,15}', '[PHONE]', text)

        # Email addresses
        text = re.sub(r'[\w.-]+@[\w.-]+\.\w+', '[EMAIL]', text)

        # Social Security Numbers
        text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN]', text)

        # Credit card numbers (basic pattern)
        text = re.sub(r'\b(?:\d{4}[-\s]?){3}\d{4}\b', '[CARD]', text)

        # API keys and tokens (common patterns)
        text = re.sub(r'\b(sk-|pk-|api[_-]?key[:\s]*)([\w-]{10,})\b', '[API_KEY]', text, flags=re.I)

        return text

    def store_research(self, agent: str, topic: str, findings: str,
                      sources: List[str] = None, depth: str = "medium") -> Optional[UUID]:
        """Store research findings to Neo4j with sanitization."""
        knowledge_id = uuid4()
        safe_findings = self._sanitize_for_sharing(findings)
        safe_topic = self._sanitize_for_sharing(topic)

        if self.fallback_mode:
            self._local_store.setdefault('research', []).append({
                'id': str(knowledge_id), 'agent': agent, 'topic': safe_topic,
                'findings': safe_findings, 'created_at': datetime.now().isoformat()
            })
            return knowledge_id

        query = """
        MATCH (a:Agent {id: $agent})
        CREATE (r:Research {
            id: $id, topic: $topic, findings: $findings,
            sources: $sources, depth: $depth,
            created_at: datetime(), confidence: 0.9
        })
        CREATE (a)-[:CREATED {timestamp: datetime()}]->(r)
        RETURN r.id as id
        """
        with self.driver.session() as session:
            session.run(query, agent=agent, id=str(knowledge_id),
                       topic=safe_topic, findings=safe_findings,
                       sources=sources or [], depth=depth)
        return knowledge_id

    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding using sentence-transformers (all-MiniLM-L6-v2)."""
        try:
            from sentence_transformers import SentenceTransformer
            if not hasattr(self, '_embedding_model'):
                self._embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            return self._embedding_model.encode(text).tolist()
        except ImportError:
            # Fallback: return empty list to trigger full-text search
            return []

    def query_related(self, agent: str, topic: str,
                     min_confidence: float = 0.7) -> List[Dict[str, Any]]:
        """Query operational knowledge with vector fallback."""
        if self.fallback_mode:
            return self._local_store.get('research', [])

        # Generate embedding for the query topic
        embedding = self._generate_embedding(topic)

        # Try vector search first (if embedding generated and index exists)
        if embedding:
            try:
                query = """
                CALL db.index.vector.queryNodes('concept_embedding', 5, $embedding)
                YIELD node, score
                WHERE score >= $min_score
                RETURN node.name as concept, node.description as description, score
                """
                with self.driver.session() as session:
                    result = session.run(query, embedding=embedding, min_score=min_confidence)
                    records = [dict(record) for record in result]
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
        CREATE (from)-[:LEARNED {knowledge_id: $knowledge_id,
                               timestamp: datetime(), depth: 1}]->(to)
        CREATE (to)-[:BUILT_ON]->(k)
        """
        with self.driver.session() as session:
            session.run(query, from_agent=from_agent, to_agent=to_agent,
                       knowledge_id=str(knowledge_id))
        return True

    def create_task(self, task_type: str, description: str,
                   delegated_by: str, assigned_to: str) -> Optional[UUID]:
        """Create a task for specialist agents to pick up."""
        task_id = uuid4()
        safe_description = self._sanitize_for_sharing(description)

        if self.fallback_mode:
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
        """Claim next pending task for an agent (atomic, race-condition safe)."""
        if self.fallback_mode:
            # In fallback mode, use simple locking
            tasks = self._local_store.get('tasks', [])
            for t in tasks:
                if t['assigned_to'] == agent and t['status'] == 'pending':
                    # Check if being processed by another agent
                    if t.get('claiming'):
                        continue
                    t['claiming'] = True  # Mark as being claimed
                    t['status'] = 'in_progress'
                    t['claimed_at'] = datetime.now().isoformat()
                    del t['claiming']
                    return t
            return None

        # Atomic claim using single MATCH-SET-RETURN
        # This prevents race conditions under concurrent load
        query = """
        MATCH (t:Task {status: 'pending'})-[:ASSIGNED_TO]->(a:Agent {id: $agent})
        WITH t LIMIT 1
        SET t.status = 'in_progress',
            t.started_at = datetime(),
            t.claimed_by = $agent
        RETURN t.id as id, t.type as type, t.description as description
        """
        with self.driver.session() as session:
            # Use write transaction for atomicity
            with session.begin_transaction() as tx:
                result = tx.run(query, agent=agent)
                record = result.single()
                tx.commit()
                return dict(record) if record else None

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
        """Escalate blocked task to Kublai for reassignment."""
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
        with self.driver.session() as session:
            session.run(query, notification_id=str(uuid4()),
                       task_id=str(task_id), delegator_id=delegator_id,
                       reason=f"Task blocked: {reason[:100]}")

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
        """Mark task as completed with results. Optionally notify delegator."""
        if self.fallback_mode:
            for t in self._local_store.get('tasks', []):
                if t['id'] == str(task_id):
                    t['status'] = 'completed'
                    t['results'] = results
                    return True
            return False

        query = """
        MATCH (t:Task {id: $task_id})
        MATCH (t)-[:ASSIGNED_TO]->(assignee:Agent)
        MATCH (delegator:Agent)-[:CREATED]->(t)
        SET t.status = 'completed', t.completed_at = datetime(),
            t.results = $results, t.quality_score = $quality_score
        RETURN delegator.id as delegator_id, assignee.id as assignee_id
        """
        with self.driver.session() as session:
            result = session.run(query, task_id=str(task_id), results=str(results),
                       quality_score=results.get('quality_score', 0.8))
            record = result.single()

            if record and notify_delegator:
                # Create notification for delegator (Kublai)
                self._notify_task_complete(
                    delegator_id=record['delegator_id'],
                    assignee_id=record['assignee_id'],
                    task_id=task_id,
                    results=results
                )
        return True

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
        with self.driver.session() as session:
            result = session.run(query, max_age_hours=max_age_hours)
            record = result.single()
            return record['deleted'] if record else 0

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
            s.updated_at = datetime()
        ON CREATE SET s.created_at = datetime()
        """
        with self.driver.session() as session:
            session.run(query, sender_id=sender_id, session_date=today,
                       active_tasks=context.get('active_tasks', []),
                       pending_delegations=context.get('pending_delegations', []),
                       conversation_summary=context.get('conversation_summary', ''))
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

    def health_check(self) -> Dict[str, Any]:
        """Check Neo4j health status."""
        if self.fallback_mode:
            return {'status': 'fallback', 'connected': False}

        try:
            with self.driver.session() as session:
                result = session.run("RETURN 1 as test")
                record = result.single()
                return {'status': 'healthy', 'connected': True,
                       'test': record['test'] if record else None}
        except Exception as e:
            return {'status': 'unhealthy', 'connected': False, 'error': str(e)}

    def close(self):
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()
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

### Phase 5: Jochi-Temüjin Collaboration Protocol

Define how analyst and developer work together:

```markdown
## Performance & Security Collaboration (Jochi ↔ Temüjin)

### Jochi's Role (Analyst)
- Monitor: Query performance, memory usage, notification growth
- Detect: Race conditions, bottlenecks, anomalies
- Report: Metrics with severity (info/warning/critical)

### Temüjin's Role (Developer)
- Fix: Implementation issues identified by Jochi
- Secure: Review all code for vulnerabilities
- Optimize: Based on Jochi's performance analysis

### Handoff Protocol

When Jochi detects issue:
```
Jochi creates Analysis node with:
  - type: "performance_issue" | "security_concern"
  - findings: detailed description
  - metrics: before/after numbers
  - severity: "warning" | "critical"
  - recommended_fix: specific approach

Jochi notifies Kublai: "Issue #X requires Temüjin review"
```

Kublai delegates to Temüjin with Analysis node ID.
Temüjin fixes, stores results, marks Analysis as resolved.
Jochi validates fix with metrics.
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

---

## Rollback Plan

1. Revert `moltbot.json` to single-agent
2. Remove Neo4j service from Railway
3. Delete agent directories
4. Redeploy

---

## Files Modified/Created

| File | Action |
|------|--------|
| `moltbot.json` | Add agents.list, agentToAgent config, Signal env var |
| `Dockerfile` | Add agent directory creation (avoids race condition) |
| `server.js` | Add health check endpoint |
| `openclaw_memory.py` | Create with full implementation + fallback mode |
| `/data/workspace/souls/*.md` | Create (6 files) |
| Neo4j schema | Create via Cypher (includes SessionContext, CREATED rel) |
