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

---

## 🧠 Weighted Memory Patterns (Cognee-Inspired)

**Principle:** Frequently-accessed connections strengthen over time. Stale connections weaken and are pruned.

### 10. Increment Edge Weight on Access
```cypher
// When a relationship is accessed, strengthen it
MATCH (a:Agent)-[r:ASSIGNED_TO]->(t:Task)
SET r.weight = COALESCE(r.weight, 1) + 1,
    r.last_accessed = datetime()
RETURN r.weight
```

### 11. Decay Stale Edges (Weekly)
```cypher
// Weaken edges not accessed in 14 days
MATCH ()-[r]-()
WHERE r.last_accessed < datetime() - duration('P14D')
SET r.weight = r.weight * 0.5
RETURN count(r) as weakened_edges
```

### 12. Query by Weight (Prioritize Strong Connections)
```cypher
// Get tasks for agent, prioritizing frequently-assigned types
MATCH (a:Agent {name: $agent_name})<-[r:ASSIGNED_TO]-(t:Task)
WHERE t.status = 'pending'
RETURN t, r.weight as priority
ORDER BY r.weight DESC, t.priority ASC
```

### 13. Auto-Prune Orphaned Nodes (Monthly)
```cypher
// Delete nodes with no connections older than 30 days
MATCH (n)
WHERE NOT ()--(n)
  AND n.created_at < datetime() - duration('P30D')
DETACH DELETE n
RETURN count(n) as pruned_nodes
```

### 14. Get Strongest Agent Relationships
```cypher
// Find which agents work together most often
MATCH (a1:Agent)-[r:FED_INTO]-(a2:Agent)
RETURN a1.name, a2.name, r.weight as collaboration_strength
ORDER BY r.weight DESC
LIMIT 10
```

### 15. Memory Access Analytics
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

---

## 🔧 Implementation Notes

### Weight Increment (On Every Access)
```typescript
// src/lib/neo4j/weighted-access.ts

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
// src/lib/neo4j/decay-stale-edges.ts

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
// src/lib/neo4j/prune-orphaned-nodes.ts

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

## 🚀 Next Steps

1. **Add weight properties** to existing Neo4j relationships
2. **Increment on access** (every query updates weights)
3. **Weekly decay cron** (auto-weaken stale edges)
4. **Monthly pruning cron** (remove orphaned nodes)
5. **Update queries** to use weight-based ordering

