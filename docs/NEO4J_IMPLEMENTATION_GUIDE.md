# Neo4j Replacement - Immediate Action Plan
**For:** Main Agent (Temüjin for Implementation)  
**From:** Kublai (Architectural Decision)  
**Priority:** CRITICAL

---

## The Decision

**Implement HYBRID ARCHITECTURE (Option 6)**

| Layer | Technology | Purpose | Status |
|-------|------------|---------|--------|
| **Tasks/Queue** | SQLite | ACID transactions, prevents race conditions | NEW |
| **Agent Memories** | Markdown files | Human-readable, version-controllable | NEW |
| **Notifications** | SQLite | Reliable delivery | NEW |
| **Graph/Vector** | Neo4j (optional) | Enhanced queries when available | EXISTING |

---

## Why This Solution?

1. **Works Immediately** - SQLite + Files = zero external dependencies
2. **No Data Loss** - All existing data preserved
3. **Solves Race Conditions** - SQLite transactions prevent task claim collisions
4. **Maintainable** - Boring technology that just works
5. **Future-Proof** - Can re-enable Neo4j later without migration

---

## Implementation Priority

### 🔴 P0 - CRITICAL (Do First)

**File:** `openclaw_memory.py` (NEW adapter)
```python
# 1. Create UnifiedMemoryAdapter class
# 2. Implement SQLiteStore for tasks
# 3. Implement FileStore for memories
# 4. Ensure same API as OperationalMemory
```

**Key Methods to Implement:**
- `create_task(type, description, delegated_by, assigned_to)` → Returns task_id
- `claim_next_task(agent_name)` → Returns task or None (ACID protected)
- `complete_task(task_id, result)` → Marks done
- `get_agent_memories(agent_name)` → Returns list of memories
- `add_notification(agent, type, summary)` → Creates notification

### 🟡 P1 - HIGH (Same Day)

**Files to Create:**
1. `sqlite_store.py` - Database operations with transactions
2. `file_store.py` - Markdown memory management
3. `memory_adapter_factory.py` - Configuration/switching

**Railway Configuration:**
```toml
[deploy.volumes]
sqlite-data = "/data/db"
memory-files = "/data/mem"
```

### 🟢 P2 - MEDIUM (Next Day)

**Testing:**
- Test all 6 agents claiming tasks simultaneously
- Verify no race conditions
- Test memory persistence

**Monitoring:**
- Add health check for SQLite
- Log storage metrics

---

## Quick Start Code

### Step 1: SQLite Schema
```sql
-- Run this to initialize
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    description TEXT NOT NULL,
    delegated_by TEXT NOT NULL,
    assigned_to TEXT,
    status TEXT DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    claimed_at TIMESTAMP,
    completed_at TIMESTAMP,
    claimed_by TEXT,
    result TEXT
);

CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_assigned ON tasks(assigned_to);
```

### Step 2: Claim Task (Race-Safe)
```python
import sqlite3

def claim_next_task(conn, agent_name):
    """Atomically claim next available task."""
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    
    try:
        # Find pending task
        cursor.execute("""
            SELECT * FROM tasks 
            WHERE status = 'pending' 
            AND (assigned_to = ? OR assigned_to = 'any')
            ORDER BY priority DESC, created_at ASC
            LIMIT 1
        """, (agent_name,))
        
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return None
        
        # Claim atomically
        task_id = row['id']
        cursor.execute("""
            UPDATE tasks 
            SET status = 'claimed', claimed_by = ?, claimed_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'pending'
        """, (agent_name, task_id))
        
        if cursor.rowcount == 0:
            conn.rollback()
            raise RaceConditionError("Task claimed by another agent")
        
        conn.commit()
        return dict(row)
        
    except Exception:
        conn.rollback()
        raise
```

### Step 3: Agent Memory (Markdown)
```python
def add_agent_memory(agent_name, memory_type, content):
    """Append to agent's memory file."""
    file_path = f"/data/mem/agents/{agent_name.lower()}.md"
    
    sections = {
        'observation': '## 🔍 Personal Observations',
        'learning': '## 📚 Key Learnings',
        'insight': '## 💡 Signature Insights'
    }
    
    with open(file_path, 'a') as f:
        f.write(f"\n{sections.get(memory_type, '## 📝 Notes')}\n")
        f.write(f"- {content}\n")
```

---

## Migration Checklist

- [ ] Create `/data/db/` and `/data/mem/agents/` directories
- [ ] Initialize SQLite database with schema
- [ ] Create agent memory files (mongke.md, chagatai.md, etc.)
- [ ] Implement UnifiedMemoryAdapter
- [ ] Update railway.toml with volume mounts
- [ ] Test task creation
- [ ] Test concurrent task claiming (race condition test)
- [ ] Verify memory persistence
- [ ] Deploy to Railway
- [ ] Monitor for 24 hours

---

## Rollback Plan

If something goes wrong:
```bash
# Instant rollback to file-only mode
export UNIFIED_MEMORY_ENABLED=false
export NEO4J_FALLBACK_MODE=true
python start_server.py
```

---

## Key Files to Modify

| File | Action |
|------|--------|
| `openclaw_memory.py` | Create UnifiedMemoryAdapter |
| `memory_manager.py` | Use adapter instead of direct Neo4j |
| `railway.toml` | Add volume mounts |
| `scripts/check_environment.py` | Add SQLite health check |

---

## Success Criteria

- [ ] `python scripts/check_neo4j.py` shows fallback mode working
- [ ] All 6 agents can claim tasks without conflicts
- [ ] Agent memories persist across restarts
- [ ] System runs without NEO4J_URI configured

---

**Ready to implement. Start with P0 items.**
