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

**Privacy Rule**: Kublai strips personal identifiers before delegating. "My friend Sarah's startup" → "a startup in X sector".

### Task Queue Delegation Pattern

To prevent Kublai from becoming a bottleneck, use Neo4j as the task queue instead of direct agentToAgent delegation:

```
User Request
     ↓
Kublai creates Task node in Neo4j
     ↓
Specialist agents poll for tasks
     ↓
Agent claims task (status: pending → in_progress)
     ↓
Agent completes work, stores results
     ↓
Kublai notified, synthesizes response
```

This decouples Kublai from waiting on specialist responses and enables async processing.

---

## Agent Configuration

### Agent Matrix

| ID | Name | Role | Model | agentDir |
|----|------|------|-------|----------|
| `main` | Kublai | Squad Lead / Router | `moonshot/kimi-k2.5` | `/data/.clawdbot/agents/main` |
| `researcher` | Möngke | Researcher | `zai/glm-4.5` | `/data/.clawdbot/agents/researcher` |
| `writer` | Chagatai | Content Writer | `moonshot/kimi-k2.5` | `/data/.clawdbot/agents/writer` |
| `developer` | Temüjin | Developer | `zai/glm-4.7` | `/data/.clawdbot/agents/developer` |
| `analyst` | Jochi | Analyst | `zai/glm-4.5` | `/data/.clawdbot/agents/analyst` |
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
  status,  // "pending" | "in_progress" | "completed" | "blocked"
  assigned_to,
  delegated_by,
  quality_score
})

// Session context for persistence across daily resets
(:SessionContext {
  sender_id,
  session_date,
  active_tasks,
  pending_delegations,
  conversation_summary
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

// Collaboration tracking
(Agent)-[:LEARNED {knowledge_id, timestamp}]->(Agent)
(Agent)-[:COLLABORATES_WITH {domain}]->(Agent)

// Approval workflow
(WorkflowImprovement)-[:APPROVED_BY]->(Agent {id: "main"})

// Knowledge provenance (CREATED relationship for all knowledge nodes)
(Agent)-[:CREATED {timestamp}]->(Research|Content|Application|Analysis|Insight|SecurityAudit|CodeReview|ProcessUpdate|WorkflowImprovement|Synthesis|Concept|Task)
```

### Indexes

```cypher
CREATE INDEX agent_knowledge FOR (n) ON (n.agent, n.created_at)
  WHERE n:Research OR n:Content OR n:Application;

CREATE INDEX task_status FOR (t:Task) ON (t.assigned_to, t.status);

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

function createAgentDirWithRetry(agentDir, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      fs.mkdirSync(agentDir, { recursive: true });
      return;
    } catch (err) {
      if (i === maxRetries - 1) throw err;
      setTimeout(() => {}, 100 * (i + 1));
    }
  }
}

for (const agentId of agentIds) {
  const agentDir = path.join(agentsDir, agentId);
  createAgentDirWithRetry(agentDir);
}
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

**Step 2.2**: Set environment variables

```
NEO4J_URI=bolt://neo4j.railway.internal:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<generate-secure-password>
SIGNAL_ACCOUNT_NUMBER=+15165643945
```

**Step 2.3**: Create schema and indexes

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

    def _sanitize_for_sharing(self, text: str) -> str:
        """Strip personal identifiers before storing to shared memory."""
        # Phone numbers
        text = re.sub(r'\+?1?\d{10,15}', '[PHONE]', text)
        # Email addresses
        text = re.sub(r'[\w.-]+@[\w.-]+\.\w+', '[EMAIL]', text)
        # Names (common patterns like "My friend X", "X's startup")
        text = re.sub(r'(?i)(?:my\s+(?:friend|contact|colleague)\s+)(\w+)', 'a contact', text)
        # Specific identifiers
        text = re.sub(r'(?i)(?:sarah|john|mike|alex|chris|jordan)[\'\']?s', 'a contact\'s', text)
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

    def query_related(self, agent: str, topic: str,
                     min_confidence: float = 0.7) -> List[Dict[str, Any]]:
        """Query operational knowledge with vector fallback."""
        if self.fallback_mode:
            return self._local_store.get('research', [])

        # Try vector search first (if available)
        try:
            query = """
            CALL db.index.vector.queryNodes('concept_embedding', 5, $embedding)
            YIELD node, score
            WHERE score >= $min_score
            RETURN node.name as concept, node.description as description, score
            """
            # Note: embedding generation would happen here
            with self.driver.session() as session:
                result = session.run(query, embedding=[], min_score=min_confidence)
                return [dict(record) for record in result]
        except Exception:
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

    def record_collaboration(self, from_agent: str, to_agent: str,
                           knowledge_id: UUID) -> bool:
        """Track that one agent learned from another's output."""
        if self.fallback_mode:
            return True

        query = """
        MATCH (from:Agent {id: $from_agent})
        MATCH (to:Agent {id: $to_agent})
        MATCH (k {id: $knowledge_id})
        CREATE (from)-[:LEARNED {knowledge_id: $knowledge_id,
                               timestamp: datetime()}]->(to)
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
        """Claim next pending task for an agent."""
        if self.fallback_mode:
            tasks = self._local_store.get('tasks', [])
            for t in tasks:
                if t['assigned_to'] == agent and t['status'] == 'pending':
                    t['status'] = 'in_progress'
                    return t
            return None

        query = """
        MATCH (t:Task {status: 'pending'})-[:ASSIGNED_TO]->(a:Agent {id: $agent})
        SET t.status = 'in_progress', t.started_at = datetime()
        RETURN t.id as id, t.type as type, t.description as description
        LIMIT 1
        """
        with self.driver.session() as session:
            result = session.run(query, agent=agent)
            record = result.single()
            return dict(record) if record else None

    def complete_task(self, task_id: UUID, results: Dict[str, Any]) -> bool:
        """Mark task as completed with results."""
        if self.fallback_mode:
            for t in self._local_store.get('tasks', []):
                if t['id'] == str(task_id):
                    t['status'] = 'completed'
                    t['results'] = results
                    return True
            return False

        query = """
        MATCH (t:Task {id: $task_id})
        SET t.status = 'completed', t.completed_at = datetime(),
            t.results = $results, t.quality_score = $quality_score
        """
        with self.driver.session() as session:
            session.run(query, task_id=str(task_id), results=str(results),
                       quality_score=results.get('quality_score', 0.8))
        return True

    def save_session_context(self, sender_id: str, context: Dict[str, Any]) -> bool:
        """Save session context for persistence across resets."""
        if self.fallback_mode:
            return True

        query = """
        MERGE (s:SessionContext {sender_id: $sender_id, session_date: date()})
        SET s.active_tasks = $active_tasks,
            s.pending_delegations = $pending_delegations,
            s.conversation_summary = $conversation_summary,
            s.updated_at = datetime()
        """
        with self.driver.session() as session:
            session.run(query, sender_id=sender_id,
                       active_tasks=context.get('active_tasks', []),
                       pending_delegations=context.get('pending_delegations', []),
                       conversation_summary=context.get('conversation_summary', ''))
        return True

    def get_session_context(self, sender_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve session context for a sender."""
        if self.fallback_mode:
            return None

        query = """
        MATCH (s:SessionContext {sender_id: $sender_id, session_date: date()})
        RETURN s.active_tasks as active_tasks,
               s.pending_delegations as pending_delegations,
               s.conversation_summary as conversation_summary
        """
        with self.driver.session() as session:
            result = session.run(query, sender_id=sender_id)
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

### Phase 4: Kublai Delegation Protocol

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
3. **Strip personal identifiers** - "My friend Sarah" → "a contact"
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

  // Check Signal
  health.services.signal = signalClient?.isConnected() ? 'healthy' : 'disconnected';

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
