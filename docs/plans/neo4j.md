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
      "account": "+15165643945",
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
```

### Indexes

```cypher
CREATE INDEX agent_knowledge FOR (n) ON (n.agent, n.created_at)
  WHERE n:Research OR n:Content OR n:Application;

CREATE INDEX task_status FOR (t:Task) ON (t.assigned_to, t.status);

CREATE FULLTEXT INDEX knowledge_content
  FOR (n:Research|Content|Concept) ON EACH [n.findings, n.body, n.description];

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

**Step 1.2**: Create agent directories in wrapper startup

```javascript
// In server.js, after STATE_DIR is defined
const agentIds = ['main', 'researcher', 'writer', 'developer', 'analyst', 'ops'];
const agentsDir = path.join(STATE_DIR, 'agents');

for (const agentId of agentIds) {
  const agentDir = path.join(agentsDir, agentId);
  fs.mkdirSync(agentDir, { recursive: true });
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
```

**Step 2.3**: Create schema and indexes

### Phase 3: Memory Module

**Step 3.1**: Create `openclaw_memory.py` module

```python
class OperationalMemory:
    """Neo4j-backed operational memory for cross-agent knowledge."""

    def store_research(self, agent: str, topic: str, findings: str, **kwargs) -> UUID:
        """Store research findings to Neo4j."""

    def query_related(self, agent: str, topic: str, min_confidence: float = 0.7):
        """Query operational knowledge relevant to current task."""

    def record_collaboration(self, from_agent: str, to_agent: str, knowledge_id: UUID):
        """Track that one agent learned from another's output."""
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
- [ ] Agents can query Neo4j
- [ ] Kublai delegates via agentToAgent
- [ ] Personal context stays in files
- [ ] Operational knowledge goes to Neo4j

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
| `moltbot.json` | Add agents.list, agentToAgent config |
| `server.js` | Add agent directory creation |
| `openclaw_memory.py` | Create (new) |
| `/data/workspace/souls/*.md` | Create (6 files) |
| Neo4j schema | Create via Cypher |
