# Neo4j Fallback Mode - Feature Compatibility Guide

## Overview

When Neo4j is unavailable (`bolt://neo4j.railway.internal:7687` or any configured URI), the system automatically falls back to SQLite-based storage. This document details what features work in fallback mode and what limitations exist.

---

## ✅ Features That Work Without Neo4j

### Agent Memory System
| Feature | Fallback Support | Notes |
|---------|-----------------|-------|
| `add_memory()` | ✅ Full | Stores to SQLite, syncs later |
| `get_agent_memories()` | ✅ Full | Retrieves from SQLite |
| `record_task_completion_memory()` | ✅ Full | Works with fallback |
| `record_interaction_memory()` | ✅ Full | Works with fallback |
| `migrate_from_markdown()` | ✅ Full | Stores to SQLite if Neo4j down |

### Basic Context Building
| Feature | Fallback Support | Notes |
|---------|-----------------|-------|
| `get_agent_context_for_task()` | ⚠️ Partial | Memories only, no graph relationships |
| `get_relevant_memories_for_task()` | ⚠️ Limited | Importance-based only, no tag matching |

### Utility Functions
| Function | Fallback Support | Notes |
|----------|-----------------|-------|
| `record_agent_memory()` | ✅ Full | Transparent fallback |
| `get_task_context()` | ⚠️ Partial | Reduced context depth |
| `get_memory_status()` | ✅ Full | Shows fallback state |

---

## ❌ Features That Require Neo4j

### Graph Relationship Features
- **Agent Relationship Mapping**: `get_agent_relationships()` - Returns empty dict
- **Cross-agent memory linking**: Requires Neo4j graph traversal
- **Task-memory graph connections**: Relationship queries fail

### Advanced Query Features
- **Tag-based memory filtering**: Limited in fallback mode
- **Graph-based relevance scoring**: Not available
- **Multi-hop relationship queries**: Not supported in SQLite

### Background Tasks (from agent_tasks.py)
| Task | Requires Neo4j | Fallback Behavior |
|------|---------------|-------------------|
| `health_check()` | Partial | System metrics work, Neo4j checks skip |
| `file_consistency()` | Partial | File checks work, Neo4j reference checks skip |
| `memory_curation_rapid()` | ✅ Yes | Skipped/fails gracefully |
| `mvs_scoring_pass()` | ✅ Yes | Skipped/fails gracefully |
| `smoke_tests()` | Partial | Non-Neo4j tests run |
| `full_tests()` | Partial | Non-Neo4j tests run |
| `vector_dedup()` | ✅ Yes | Skipped |
| `deep_curation()` | ✅ Yes | Skipped |
| `reflection_consolidation()` | ✅ Yes | Skipped |
| `knowledge_gap_analysis()` | ✅ Yes | Skipped |
| `status_synthesis()` | Partial | Limited agent status |
| `weekly_reflection()` | ✅ Yes | Skipped |
| `notion_sync()` | ✅ Yes | Skipped |

### Memory Manager (memory_manager.py)
| Feature | Requires Neo4j | Fallback Behavior |
|---------|---------------|-------------------|
| Hot tier (in-memory) | ✅ No | Works fully |
| Warm tier loading | ✅ Yes | Skipped/empty |
| Cold tier loading | ✅ Yes | Skipped/empty |
| Archive queries | ✅ Yes | Returns empty |
| Vector search | ✅ Yes | Not available |

---

## 🔄 Data Synchronization

When Neo4j becomes available again:

1. **Automatic Sync**: The system attempts to sync fallback data on reconnection
2. **Manual Sync**: Use `sync_fallback_to_neo4j()` to force synchronization
3. **Pending Queue**: All changes are queued in `sync_queue` table

### Sync Status Check
```python
from tools.kurultai.neo4j_agent_memory import get_memory_status

status = get_memory_status()
print(status['fallback_stats'])
# Shows: total_memories, unsynced_memories, pending_sync
```

---

## 📊 Fallback Storage Schema

The SQLite database is stored at:
```
/data/workspace/souls/main/memory/fallback_neo4j.db
```

### Tables
1. **agent_memories** - Stores memory entries
2. **tasks** - Stores task data
3. **agent_state** - Stores agent status
4. **sync_queue** - Queue for Neo4j synchronization

---

## 🚨 Emergency Workarounds

### 1. Force Fallback Mode
```python
from tools.kurultai.neo4j_agent_memory import Neo4jAgentMemory

# Create with fallback forced
memory = Neo4jAgentMemory(fallback_enabled=True)
# Will use SQLite even if Neo4j appears available
```

### 2. Check Current Mode
```python
if memory._is_fallback_mode():
    print("Running in fallback mode - some features limited")
```

### 3. Manual Data Export
```python
# Export all fallback data to JSON
import json
from tools.kurultai.resilient_neo4j import FallbackStorage

fallback = FallbackStorage()
memories = fallback.get_agent_memories("temujin", limit=1000)
with open('fallback_backup.json', 'w') as f:
    json.dump(memories, f, indent=2)
```

### 4. Clear Sync Queue (if needed)
```python
# If sync queue is stuck, clear it
fallback = FallbackStorage()
conn = fallback._get_connection()
conn.execute("DELETE FROM sync_queue WHERE retry_count > 10")
conn.commit()
```

---

## 🔧 Configuration

### Environment Variables
```bash
# Neo4j connection (normal operation)
NEO4J_URI=bolt://neo4j.railway.internal:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password

# Optional: Disable fallback (not recommended)
NEO4J_DISABLE_FALLBACK=true
```

### Retry Configuration
```python
from tools.kurultai.resilient_neo4j import RetryConfig

retry_config = RetryConfig(
    max_retries=5,
    base_delay=1.0,
    max_delay=60.0
)
```

---

## 📝 Best Practices

1. **Always enable fallback** in production: `Neo4jAgentMemory(fallback_enabled=True)`

2. **Check mode before graph operations**:
```python
if not memory._is_fallback_mode():
    relationships = memory.get_agent_relationships(agent_name)
else:
    relationships = {}  # Handle fallback case
```

3. **Monitor sync status** regularly:
```python
status = memory.get_status()
if status['fallback_stats']['pending_sync'] > 100:
    print("Warning: Large sync backlog")
```

4. **Backup fallback database** periodically:
```bash
cp /data/workspace/souls/main/memory/fallback_neo4j.db \
   /data/workspace/souls/main/memory/fallback_neo4j.db.backup
```

---

## 🔍 Troubleshooting

### Issue: "Neo4j unavailable - using SQLite fallback"
**Solution**: This is expected behavior. Check Neo4j connectivity separately.

### Issue: Sync queue growing too large
**Solution**: 
1. Check Neo4j is reachable: `memory._connection._try_connect()`
2. Force manual sync: `memory.sync_fallback_to_neo4j()`
3. If Neo4j permanently down, export data manually

### Issue: "Fallback storage not available"
**Solution**: Check disk space and permissions for `memory/fallback_neo4j.db`

### Issue: Circuit breaker keeps opening
**Solution**: Neo4j is likely down or misconfigured. Check:
- Network connectivity to `neo4j.railway.internal:7687`
- Authentication credentials
- Neo4j server logs

---

## 📈 Performance Impact

| Operation | Neo4j Mode | Fallback Mode | Impact |
|-----------|-----------|---------------|--------|
| Add memory | ~10ms | ~5ms | Faster in fallback |
| Get memories | ~15ms | ~3ms | Faster in fallback |
| Graph query | ~20ms | N/A | Not available |
| Relationship lookup | ~25ms | N/A | Not available |

**Note**: Fallback is actually faster for simple CRUD but lacks graph capabilities.
