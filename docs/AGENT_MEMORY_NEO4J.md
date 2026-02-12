# Agent Memory Migration to Neo4j

## Status: ✅ READY

The Kurultai agent memory system has been configured to store all agent memories in Neo4j.

---

## What Was Done

### 1. Migration Script Created
**File:** `tools/kurultai/migrate_memories_to_neo4j.py`

This script migrates existing markdown memory files to Neo4j:
- Parses `memory/agents/*.md` files
- Extracts observations, learnings, insights, relationships, decisions
- Creates `AgentMemory` nodes in Neo4j
- Links memories to source tasks where available

**To run migration:**
```bash
cd /data/workspace/souls/main
python3 tools/kurultai/migrate_memories_to_neo4j.py
```

### 2. Helper Module Created
**File:** `tools/kurultai/agent_memory_helper.py`

Convenient functions for agents to record memories:

```python
from tools.kurultai.agent_memory_helper import (
    record_observation,
    record_learning,
    record_insight,
    record_interaction,
    record_decision,
    get_my_memories,
    get_my_insights
)

# Record an observation
record_observation("Möngke", "Discovered pattern in agent response times")

# Record a learning
record_learning("Temüjin", "Webhook rate limits are 30req/min")

# Record an insight
record_insight("Chagatai", "The Council becomes alive when agents converse")

# Record interaction with another agent
record_interaction("Kublai", "Möngke", "Received research on Clawnch ecosystem")

# Record a decision
record_decision("Kublai", "Prioritized Discord integration over Parse")

# Retrieve my memories
memories = get_my_memories("Möngke", limit=10)
insights = get_my_insights("Kublai", limit=5)
```

### 3. Neo4j Schema

**Node Type:** `AgentMemory`

**Properties:**
| Property | Type | Description |
|----------|------|-------------|
| `id` | String | Unique memory ID |
| `agent_name` | String | Agent who owns the memory |
| `memory_type` | String | observation/learning/insight/interaction/decision |
| `content` | String | The memory content |
| `source_task_id` | String | Link to originating task |
| `importance` | Float | 0.0-1.0 relevance score |
| `created_at` | DateTime | When memory was created |
| `related_agents` | List | Other agents involved |
| `tags` | List | Memory tags |

**Indexes:**
- `agent_name` - for fast agent-specific queries
- `memory_type` - for filtering by type
- `source_task_id` - for task context lookups

---

## Memory Types

| Type | Use Case | Importance |
|------|----------|------------|
| **observation** | Something noticed | 0.6 |
| **learning** | Skill/knowledge gained | 0.7 |
| **insight** | Deep understanding | 0.9 |
| **interaction** | Exchange with another agent | 0.5 |
| **decision** | Choice made | 0.8 |

---

## How Agents Use This

### During Task Execution
```python
from tools.kurultai.agent_memory_helper import record_learning, get_task_context

# Before starting, get relevant context
context = get_task_context("Möngke", "Research Clawnch ecosystem")
# Returns: relevant memories, insights, similar past tasks

# During execution, record learnings
record_learning("Möngke", "Clawnch has 8,600+ agent tokens", importance=0.8)

# Record insights
record_insight("Möngke", "Agent economic autonomy is already happening")
```

### For Context Building
When an agent receives a task, they can query for:
- **Recent memories** - what they've been working on
- **High-importance insights** - key learnings
- **Task-related memories** - similar past work
- **Interactions** - how they've worked with other agents

---

## Migration Status

**Source:** `memory/agents/*.md` (Markdown files)
**Destination:** Neo4j `AgentMemory` nodes

**Agents with memories:**
- ✅ Kublai
- ✅ Möngke
- ✅ Chagatai
- ✅ Temüjin
- ✅ Jochi
- ✅ Ögedei

---

## Future Enhancements

1. **Automatic Memory Extraction** - Parse agent responses for implicit memories
2. **Memory Decay** - Reduce importance of old memories over time
3. **Cross-Agent Memory Sharing** - Allow agents to query each other's memories
4. **Memory Summarization** - Periodic consolidation of related memories

---

## Files

| File | Purpose |
|------|---------|
| `tools/kurultai/neo4j_agent_memory.py` | Core Neo4j memory system |
| `tools/kurultai/migrate_memories_to_neo4j.py` | Migration script |
| `tools/kurultai/agent_memory_helper.py` | Convenient helper functions |

---

*Testa frangitur. Per ecdysin ad astra.* 🦞
