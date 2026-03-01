# Neo4j Cross-Agent Memory Patterns

## Schema Overview

### Node Types
- **Agent** - Represents an AI agent in the Kurultai
- **Task** - Represents a task assigned to an agent
- **Memory** - Operational memory entry
- **Decision** - Routing or strategic decision
- **Escalation** - Critical issue requiring attention

### Relationships
- **ASSIGNED_TO** - Task → Agent
- **DEPENDS_ON** - Task → Task
- **FED_INTO** - Agent → Agent
- **LOGGED** - Agent → Memory
- **TRIGGERED** - Event → Escalation

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
