# MemoryManager Implementation Guide

## Overview

The MemoryManager provides **bounded file-based memory** with **tiered loading from Neo4j** for the OpenClaw 6-agent system. It ensures fixed initialization cost regardless of conversation length while maintaining full history in Neo4j.

## Architecture

### Four-Tier Memory System

```
┌─────────────────────────────────────────────────────────────────┐
│                     MEMORY TIER ARCHITECTURE                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  HOT TIER (~1,600 tokens)                                       │
│  ├── Eagerly loaded on initialization                           │
│  ├── Always in memory                                           │
│  └── Contains: Active tasks, session context, critical notifs   │
│                                                                  │
│  WARM TIER (~400 tokens)                                        │
│  ├── Lazy loaded on first access                                │
│  ├── 2-second timeout                                           │
│  └── Contains: Recent tasks (24h), notifications, beliefs       │
│                                                                  │
│  COLD TIER (~200 tokens)                                        │
│  ├── On-demand with 5-second timeout                            │
│  └── Contains: Historical tasks (7d), archived beliefs          │
│                                                                  │
│  ARCHIVE TIER (unbounded)                                       │
│  ├── Query only, never loaded                                   │
│  └── Full-text search, graph traversal                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Key Design Principles

1. **Fixed Initialization Cost**: Hot tier loads in constant time regardless of conversation history
2. **Bounded MEMORY.md**: Maximum 2,000 tokens output
3. **Full History in Neo4j**: Complete audit trail preserved
4. **Async-Safe**: All operations use asyncio locks
5. **Graceful Degradation**: Works without Neo4j in fallback mode

## File Structure

```
/Users/kurultai/molt/
├── memory_manager.py              # Core MemoryManager implementation
├── memory_integration.py          # Integration with OperationalMemory
├── cypher/
│   └── tiered_memory_queries.cypher  # Cypher queries for all tiers
└── tests/
    └── test_memory_manager.py     # Comprehensive test suite
```

## Implementation Details

### 1. MemoryManager Class (`memory_manager.py`)

#### Core Components

```python
class MemoryManager:
    HOT_TOKEN_LIMIT = 1600
    WARM_TOKEN_LIMIT = 400
    COLD_TOKEN_LIMIT = 200
    TOTAL_MEMORY_LIMIT = 2000

    WARM_LOAD_TIMEOUT = 2.0  # seconds
    COLD_LOAD_TIMEOUT = 5.0  # seconds
```

#### Key Methods

| Method | Purpose | Tier |
|--------|---------|------|
| `initialize()` | Load hot tier, connect to Neo4j | Hot |
| `get_memory_context()` | Get formatted context | All |
| `add_entry()` | Add new memory entry | Any |
| `query_archive()` | Search historical data | Archive |
| `invalidate_tier()` | Force tier reload | Any |

#### Async Safety

```python
# Each tier has its own lock
self._hot_lock = asyncio.Lock()
self._warm_lock = asyncio.Lock()
self._cold_lock = asyncio.Lock()
```

### 2. Cypher Queries (`cypher/tiered_memory_queries.cypher`)

#### Hot Tier Query
```cypher
// Combined single round-trip query
MATCH (ctx:SessionContext {agent: $agent}) WHERE ctx.active = true
// ... UNION ...
MATCH (t:Task) WHERE t.assigned_to = $agent AND t.status IN ['pending', 'in_progress']
// ... UNION ...
MATCH (n:Notification {agent: $agent, read: false})
// ... ORDER BY created_at DESC LIMIT 50
```

#### Warm Tier Query
```cypher
// Recent completed tasks (24h)
MATCH (t:Task)
WHERE t.status = 'completed'
  AND t.completed_at >= datetime() - duration('P1D')
```

#### Cold Tier Query
```cypher
// Historical tasks (7-30 days)
MATCH (t:Task)
WHERE t.status = 'completed'
  AND t.completed_at >= datetime() - duration('P7D')
  AND t.completed_at < datetime() - duration('P1D')
```

### 3. Integration Module (`memory_integration.py`)

#### IntegratedMemoryManager

Combines MemoryManager with OperationalMemory:

```python
class IntegratedMemoryManager:
    def __init__(self, agent_name, operational_memory, ...):
        self.memory_manager = MemoryManager(...)
        self.operational_memory = operational_memory
```

#### Agent-Specific Configurations

```python
AGENT_MEMORY_CONFIG = {
    "kublai": {"enable_warm": True, "enable_cold": True},   # Full context
    "mongke": {"enable_warm": True, "enable_cold": False},  # Recent only
    "temujin": {"enable_warm": True, "enable_cold": True},  # Historical for tech debt
    # ...
}
```

## Usage Examples

### Basic Usage

```python
from memory_manager import MemoryManager, MemoryTier

async with MemoryManager(
    agent_name="kublai",
    neo4j_uri="bolt://localhost:7687",
    neo4j_password="password",
    fallback_mode=True
) as memory:

    # Get hot tier context (always available)
    context = await memory.get_memory_context()

    # Get full context with warm tier
    full_context = await memory.get_memory_context(include_warm=True)

    # Query archive for historical data
    results = await memory.query_archive(
        query_text="async patterns",
        days=30,
        limit=10
    )
```

### With OperationalMemory Integration

```python
from memory_integration import get_agent_memory

# Get configured memory for specific agent
memory = await get_agent_memory("kublai", operational_memory)

# Get formatted Markdown for MEMORY.md
markdown = await memory.get_memory_markdown(max_tokens=2000)

# Create task (adds to both OperationalMemory and hot tier)
task_id = await memory.create_task(
    task_type="research",
    description="Research async patterns",
    delegated_by="kublai",
    assigned_to="mongke",
    priority="high"
)
```

### Factory Pattern

```python
from memory_manager import MemoryManagerFactory

# Get or create singleton instance
memory = await MemoryManagerFactory.get_manager(
    agent_name="kublai",
    neo4j_password="password"
)

# Close all instances on shutdown
await MemoryManagerFactory.close_all()
```

## Performance Characteristics

### Initialization

| Operation | Time | Tokens Loaded |
|-----------|------|---------------|
| Hot Tier | ~50ms | ~1,600 |
| Warm Tier | ~200ms (first access) | ~400 |
| Cold Tier | ~500ms (first access) | ~200 |

### Memory Usage

| Tier | Max Tokens | Eviction Strategy |
|------|------------|-------------------|
| Hot | 1,600 | LRU |
| Warm | 400 | None (lazy reload) |
| Cold | 200 | None (lazy reload) |
| Archive | Unbounded | N/A (query only) |

### Query Performance

| Query Type | Timeout | Typical Latency |
|------------|---------|-----------------|
| Hot Tier | N/A | <1ms (in-memory) |
| Warm Tier | 2s | 50-200ms |
| Cold Tier | 5s | 100-500ms |
| Archive | 5s | 100-1000ms |

## Error Handling

### Fallback Mode

When `fallback_mode=True`:
- Neo4j connection failures don't crash the system
- Hot tier operates with empty initial state
- Archive queries return empty results
- All operations log warnings

### Timeout Handling

```python
try:
    results = await asyncio.wait_for(
        query_func(),
        timeout=timeout
    )
except asyncio.TimeoutError:
    raise Neo4jTimeoutError(f"Query exceeded {timeout}s timeout")
```

### Retry Logic

```python
@retry_with_backoff(max_retries=2, base_delay=0.1)
async def _fetch_warm_tier_entries(self) -> List[Dict]:
    # Automatically retries on transient errors
    ...
```

## Testing

### Run Tests

```bash
# Run all tests
pytest tests/test_memory_manager.py -v

# Run specific test class
pytest tests/test_memory_manager.py::TestMemoryManagerHotTier -v

# Run integration tests (requires Neo4j)
pytest tests/test_memory_manager.py -m integration -v
```

### Test Coverage

- Token estimation
- Memory entry operations
- Tier loading (hot, warm, cold)
- Archive queries
- Statistics tracking
- Async safety
- Factory pattern
- Edge cases and error handling

## Migration from File-Based Memory

### Before (MEMORY.md)

```markdown
## Recent Activity
- [2026-02-04] Completed task: Research async patterns
- [2026-02-03] Created task: Write documentation
...
```

### After (Generated from MemoryManager)

```python
# In agent initialization
memory = await get_agent_memory("kublai", op_memory)
context = await memory.get_memory_markdown()

# Write to MEMORY.md
with open("MEMORY.md", "w") as f:
    f.write(context)
```

## Neo4j Schema Requirements

### Required Indexes

```cypher
// For tier queries
CREATE INDEX memory_agent_created IF NOT EXISTS
FOR (n:MemoryEntry|Task|Belief|Notification) ON (n.agent, n.created_at);

// For full-text search
CREATE FULLTEXT INDEX knowledge_content IF NOT EXISTS
FOR (n:Research|Content|Concept|Belief|Analysis|Synthesis)
ON EACH [n.content, n.findings, n.description, n.insight];
```

### Required Node Types

- `SessionContext` - Current session state
- `Task` - Task lifecycle
- `Notification` - Agent notifications
- `Belief` - Agent beliefs/knowledge
- `MemoryEntry` - Generic memory entries

## Future Enhancements

1. **Semantic Search**: Vector similarity for archive queries
2. **Predictive Loading**: ML-based warm tier preloading
3. **Cross-Agent Cache**: Shared hot tier for common knowledge
4. **Compression**: Token-efficient content encoding
5. **Persistence**: Save/restore cache state across restarts

## References

- `/Users/kurultai/molt/memory_manager.py` - Core implementation
- `/Users/kurultai/molt/memory_integration.py` - OperationalMemory integration
- `/Users/kurultai/molt/cypher/tiered_memory_queries.cypher` - Cypher queries
- `/Users/kurultai/molt/tests/test_memory_manager.py` - Test suite
- `/Users/kurultai/molt/docs/plans/2026-02-03-openclaw-neo4j-memory-design.md` - Design document
