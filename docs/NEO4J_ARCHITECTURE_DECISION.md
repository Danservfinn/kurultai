# Neo4j Architecture Decision Document
## Kurultai Multi-Agent System - Kublai (Router/Orchestrator)
**Date:** 2026-02-12  
**Status:** DECISION REQUIRED  
**Priority:** CRITICAL - Blocking Production

---

## 1. Problem Statement

Neo4j is currently unreachable in the Railway environment, blocking the Kurultai multi-agent system from functioning. We need a solution that:
1. **Works immediately** (short-term fix)
2. **Is maintainable long-term** (technical debt consideration)
3. **Doesn't lose data or functionality** (preserve capabilities)

### Current Impact
- ❌ Task queue unavailable
- ❌ Agent memories inaccessible
- ❌ Discord bot context broken
- ❌ Notion integration failing
- ❌ Notifications not routing

---

## 2. System Context

### Current Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                    Kurultai Multi-Agent System                  │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ Möngke   │  │ Chagatai │  │ Temüjin  │  │ Jochi    │        │
│  │Researcher│  │  Writer  │  │Developer │  │  Analyst │        │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘        │
│       │             │             │             │               │
│  ┌────┴─────┐  ┌────┴─────┐  ┌────┴─────┐  ┌────┴─────┐        │
│  │  Ögedei  │  │  Kublai  │◄─┤ Router   │  │(Ops/QA)  │        │
│  │  (Ops)   │  │(Squad Lead)│  └─────────┘  └──────────┘        │
│  └────┬─────┘  └────┬─────┘                                    │
│       │             │                                           │
│       └─────────────┴──────────────────┐                        │
│                                        ▼                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              OperationalMemory (Neo4j)                   │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │   │
│  │  │    Tasks     │  │   Memories   │  │Notifications │   │   │
│  │  │  - pending   │  │  - hot       │  │  - unread    │   │   │
│  │  │  - claimed   │  │  - warm      │  │  - read      │   │   │
│  │  │  - completed │  │  - cold      │  │  - alerts    │   │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Neo4j Graph Database                        │   │
│  │         (railway.internal networking)                    │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Key Data Structures
1. **Tasks** - `id`, `status`, `assigned_to`, `delegated_by`, `description`, `priority`
2. **Agent Memories** - `id`, `agent_name`, `memory_type`, `content`, `importance`, `source_task_id`
3. **Notifications** - `id`, `agent`, `type`, `summary`, `read`, `created_at`
4. **Rate Limits** - Composite key tracking for API throttling
5. **Session Context** - Active sessions per agent

---

## 3. Option Evaluation Matrix

### Summary Scoring (1-5 scale)

| Option | Implementation | Durability | Performance | Maintainability | Compatibility | **Total** |
|--------|---------------|------------|-------------|-----------------|---------------|-----------|
| 1. File-based | 5 | 3 | 2 | 3 | 4 | **17** |
| 2. SQLite | 4 | 4 | 4 | 4 | 4 | **20** |
| 3. Redis | 2 | 2 | 5 | 3 | 2 | **14** |
| 4. External Neo4j | 2 | 5 | 3 | 3 | 5 | **18** |
| 5. Railway Fix | 3 | 5 | 4 | 5 | 5 | **22** |
| 6. **Hybrid (Recommended)** | 3 | 4 | 4 | 4 | 5 | **20** |

---

## 4. Detailed Option Analysis

### Option 1: File-based Fallback (JSON/Markdown)

**Implementation:** Store all data in structured JSON files and Markdown for memories.

**Pros:**
- ✅ Immediate implementation - code already has fallback_mode support
- ✅ Zero external dependencies
- ✅ Easy to version control (memories as Markdown)
- ✅ Human-readable

**Cons:**
- ❌ No query capabilities (can't filter tasks by status efficiently)
- ❌ File locking issues with concurrent agents
- ❌ No transactions (race conditions on task claiming)
- ❌ Slow for large datasets
- ❌ No graph relationships

**Effort:** 1-2 days  
**Verdict:** Good for emergency fallback, insufficient for full replacement

---

### Option 2: SQLite Replacement

**Implementation:** Replace Neo4j with SQLite - file-based SQL database.

**Pros:**
- ✅ ACID transactions (solves race conditions)
- ✅ SQL query capabilities
- ✅ Single file, easy to backup
- ✅ Railway volumes support persistent storage
- ✅ Python built-in support
- ✅ Good performance for current data volumes (<100k records)

**Cons:**
- ❌ Loses graph traversal capabilities
- ❌ Schema migration required
- ❌ No built-in vector search (would need additional library)

**Effort:** 3-5 days  
**Migration Path:** Create SQLite schema → Migrate existing data → Update queries  
**Verdict:** Solid technical choice, medium implementation effort

---

### Option 3: Redis

**Implementation:** Use Redis as primary data store with Railway's Redis service.

**Pros:**
- ✅ Excellent performance
- ✅ Railway native support
- ✅ Pub/sub for real-time notifications

**Cons:**
- ❌ Data persistence concerns (unless configured properly)
- ❌ No complex query capabilities
- ❌ Schema-less = more application-side complexity
- ❌ Need to build indexing layer
- ❌ Graph relationships difficult

**Effort:** 5-7 days  
**Verdict:** Overkill for current needs, adds unnecessary complexity

---

### Option 4: External Neo4j (Aura, etc.)

**Implementation:** Move to Neo4j Aura (managed cloud service) or another hosted Neo4j.

**Pros:**
- ✅ Zero code changes
- ✅ Maintains graph capabilities
- ✅ Professional managed service
- ✅ Automatic backups

**Cons:**
- ❌ **Monthly cost** (~$65/month for Aura Pro)
- ❌ External network dependency
- ❌ Data residency concerns
- ❌ Doesn't solve Railway networking issue (root cause)

**Effort:** 1 day (configuration only)  
**Cost:** $65+/month  
**Verdict:** Expensive band-aid, doesn't address root cause

---

### Option 5: Railway Networking Fix

**Implementation:** Properly configure Railway internal networking for Neo4j.

**Pros:**
- ✅ Zero architectural changes
- ✅ Root cause fix
- ✅ Maintains current performance
- ✅ Free (within Railway plan)

**Cons:**
- ❌ Debugging Railway networking can be time-consuming
- ❌ May reoccur with Railway updates
- ❌ Tight coupling to Railway specifics

**Root Cause Analysis:**
Based on `railway.toml` and `railway.yml`, Neo4j is configured to use internal DNS:
- `NEO4J_URI=bolt://neo4j.railway.internal:7687`

**Likely Issues:**
1. Neo4j service not starting correctly
2. DNS resolution failing between services
3. Neo4j port binding issue
4. Authentication misconfiguration

**Effort:** 1-3 days (debugging)  
**Verdict:** Ideal if it works, risky if debugging drags on

---

### Option 6: Hybrid Architecture (RECOMMENDED)

**Implementation:** Tiered approach combining immediate fix with long-term sustainability:

```
┌─────────────────────────────────────────────────────────────────┐
│                  Hybrid Memory Architecture                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Tier 1: Critical Data (Files)               │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │   │
│  │  │   tasks.json │  │ agents/*.md  │  │ notifications│   │   │
│  │  │              │  │              │  │   /json      │   │   │
│  │  │  - pending   │  │  - memories  │  │              │   │   │
│  │  │  - active    │  │  - learnings │  │  - routing   │   │   │
│  │  │  - claimed   │  │  - insights  │  │  - state     │   │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Tier 2: Query Layer (SQLite)                │   │
│  │                                                          │   │
│  │  Provides:                                               │   │
│  │  - ACID transactions for task claiming                   │   │
│  │  - Fast queries (status, agent, priority)                │   │
│  │  - Full-text search                                      │   │
│  │  - Backup/restore                                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │         Tier 3: Graph Layer (Neo4j - Optional)           │   │
│  │                                                          │   │
│  │  When available:                                         │   │
│  │  - Complex relationship queries                          │   │
│  │  - Vector similarity search                              │   │
│  │  - Advanced graph analytics                              │   │
│  │                                                          │   │
│  │  Falls back to SQLite when unavailable                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Key Design Decisions:**

1. **Task Queue → SQLite** (Primary)
   - ACID transactions prevent race conditions
   - Simple schema: `tasks`, `notifications`, `rate_limits`
   - Sync to JSON for human readability/backup

2. **Agent Memories → Markdown Files** (Primary)
   - Each agent has `{agent_name}.md` in `memory/agents/`
   - Human-readable, version-controllable
   - Index in SQLite for search

3. **Neo4j → Optional Enhancement**
   - Code already has `fallback_mode` support
   - When Neo4j available: use for vector search, graph queries
   - When unavailable: degrade gracefully to SQLite

**Pros:**
- ✅ Immediate working solution (Tier 1 + 2)
- ✅ No data loss
- ✅ SQLite is proven, maintainable
- ✅ Files are human-readable and portable
- ✅ Can restore Neo4j later without migration
- ✅ Low cost

**Cons:**
- ⚠️ More complex than single database
- ⚠️ Need sync logic between tiers

**Effort:** 3-4 days  
**Verdict:** Best balance of immediate fix + long-term sustainability

---

## 5. Recommended Solution: Hybrid Architecture

### Rationale

1. **Immediate Need:** Railway Neo4j debugging could take days. We need something working now.

2. **Data Safety:** File-based storage ensures no data loss even if services fail.

3. **Maintainability:** SQLite is boring technology that just works. No external dependencies.

4. **Future Flexibility:** Can re-enable Neo4j later when networking is fixed.

5. **Cost:** Free on Railway (uses volumes for SQLite + files).

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Hybrid Memory System v1.0                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ │
│   │   Möngke    │    │  Chagatai   │    │   Temüjin   │    │    Jochi    │ │
│   │  Researcher │    │   Writer    │    │  Developer  │    │   Analyst   │ │
│   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └──────┬──────┘ │
│          │                  │                  │                  │        │
│   ┌──────┴──────┐    ┌──────┴──────┐    ┌──────┴──────┐    ┌──────┴──────┐│
│   │   Ögedei    │◄──►│   Kublai    │◄──►│  (Router)   │    │    (QA)     ││
│   │     Ops     │    │  Squad Lead │    │             │    │             ││
│   └──────┬──────┘    └──────┬──────┘    └─────────────┘    └─────────────┘│
│          │                  │                                              │
│          └──────────────────┘                                              │
│                     │                                                      │
│                     ▼                                                      │
│   ┌───────────────────────────────────────────────────────────────────┐   │
│   │                  UnifiedMemoryAdapter                              │   │
│   │  ┌─────────────────────────────────────────────────────────────┐ │   │
│   │  │  Interface: Same API as OperationalMemory                   │ │   │
│   │  │  - create_task()                                            │ │   │
│   │  │  - claim_next_task()                                        │ │   │
│   │  │  - complete_task()                                          │ │   │
│   │  │  - get_agent_memories()                                     │ │   │
│   │  │  - add_notification()                                       │ │   │
│   │  └─────────────────────────────────────────────────────────────┘ │   │
│   └────────────────────────┬──────────────────────────────────────────┘   │
│                            │                                               │
│           ┌────────────────┼────────────────┐                              │
│           ▼                ▼                ▼                              │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                    │
│   │  SQLiteStore │  │  FileStore   │  │  Neo4jStore  │                    │
│   │  ─────────── │  │  ─────────── │  │  ─────────── │                    │
│   │  /data/db/   │  │  /data/mem/  │  │ (when avail) │                    │
│   │              │  │              │  │              │                    │
│   │  • tasks     │  │  • agent.md  │  │  • vectors   │                    │
│   │  • queue     │  │  • session   │  │  • graphs    │                    │
│   │  • rates     │  │  • context   │  │  • analytics │                    │
│   │  • index     │  │  • backup    │  │              │                    │
│   └──────────────┘  └──────────────┘  └──────────────┘                    │
│          │                  │                  │                           │
│          └──────────────────┼──────────────────┘                           │
│                             ▼                                              │
│                   ┌─────────────────┐                                      │
│                   │  Sync Manager   │                                      │
│                   │  (keeps tiers   │                                      │
│                   │   consistent)   │                                      │
│                   └─────────────────┘                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
1. Agent creates task:
   └─► UnifiedMemoryAdapter.create_task()
       ├─► SQLite: INSERT INTO tasks (ACID transaction)
       ├─► FileStore: Append to tasks.json
       └─► Neo4j: If available, create graph node

2. Agent claims task:
   └─► UnifiedMemoryAdapter.claim_next_task()
       └─► SQLite: SELECT ... FOR UPDATE (prevents race conditions)
           ├─► Update status to 'claimed'
           └─► Return task to agent

3. Agent retrieves memories:
   └─► UnifiedMemoryAdapter.get_memories(agent_name)
       ├─► FileStore: Read {agent}.md (fast, cached)
       └─► SQLite: Query memory_index for search/filter

4. System notification:
   └─► UnifiedMemoryAdapter.notify(agent, message)
       ├─► SQLite: INSERT notification
       ├─► FileStore: Append to notifications.log
       └─► Discord/Signal: Send message
```

---

## 6. Implementation Plan

### Phase 1: Emergency Fix (Days 1-2) - CRITICAL PATH
**Goal:** Get system operational immediately

**Tasks:**
1. ✅ Create `UnifiedMemoryAdapter` class with same API as `OperationalMemory`
2. ✅ Implement `SQLiteStore` for tasks, notifications, rate limits
3. ✅ Implement `FileStore` for agent memories (Markdown)
4. ✅ Add automatic migration from existing data
5. ✅ Update `railway.toml` to remove Neo4j dependency
6. ✅ Test with all 6 agents

**Deliverable:** Working system without Neo4j

### Phase 2: Hardening (Days 3-4)
**Goal:** Production-ready reliability

**Tasks:**
1. Add sync manager between SQLite and FileStore
2. Implement backup/restore for SQLite
3. Add monitoring for storage health
4. Performance optimization (indexes, caching)
5. Race condition testing

**Deliverable:** Production-ready storage layer

### Phase 3: Neo4j Re-enable (Future - Optional)
**Goal:** Restore graph capabilities when Railway networking fixed

**Tasks:**
1. Fix Railway Neo4j networking
2. Re-enable Neo4jStore in adapter
3. Sync SQLite data back to Neo4j
4. Use Neo4j for vector search (enhancement)

**Deliverable:** Full graph capabilities restored

---

## 7. Schema Design

### SQLite Schema

```sql
-- Tasks table (core functionality)
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    description TEXT NOT NULL,
    delegated_by TEXT NOT NULL,
    assigned_to TEXT,
    status TEXT DEFAULT 'pending', -- pending, claimed, in_progress, completed, failed
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    claimed_at TIMESTAMP,
    completed_at TIMESTAMP,
    claimed_by TEXT,
    result TEXT,
    metadata TEXT -- JSON
);

CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_assigned ON tasks(assigned_to);
CREATE INDEX idx_tasks_created ON tasks(created_at);

-- Notifications table
CREATE TABLE notifications (
    id TEXT PRIMARY KEY,
    agent TEXT NOT NULL,
    type TEXT NOT NULL,
    summary TEXT NOT NULL,
    details TEXT,
    read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP
);

CREATE INDEX idx_notifications_agent ON notifications(agent);
CREATE INDEX idx_notifications_unread ON notifications(agent, read);

-- Rate limiting table
CREATE TABLE rate_limits (
    service TEXT NOT NULL,
    key TEXT NOT NULL,
    count INTEGER DEFAULT 0,
    window_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (service, key)
);

-- Agent memories index (for search)
CREATE TABLE memory_index (
    id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    memory_type TEXT NOT NULL, -- observation, learning, insight, interaction
    content TEXT NOT NULL,
    source_task_id TEXT,
    importance REAL DEFAULT 0.5,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    file_path TEXT -- Reference to Markdown file
);

CREATE INDEX idx_memory_agent ON memory_index(agent_name);
CREATE INDEX idx_memory_type ON memory_index(memory_type);
```

### File Structure

```
/data/workspace/souls/main/
├── data/
│   ├── db/
│   │   └── kurultai.db          # SQLite database
│   ├── mem/
│   │   ├── agents/
│   │   │   ├── mongke.md        # Agent memories
│   │   │   ├── chagatai.md
│   │   │   ├── temujin.md
│   │   │   ├── jochi.md
│   │   │   ├── ogedei.md
│   │   │   └── kublai.md
│   │   ├── tasks.json           # Human-readable task log
│   │   └── notifications/       # Notification history
│   │       └── 2026-02/
│   └── backup/                  # Automated backups
└── memory/                      # Existing memory folder
    └── 2026-02-12.md           # Daily logs (unchanged)
```

---

## 8. Code Implementation

### UnifiedMemoryAdapter (Core Interface)

```python
class UnifiedMemoryAdapter:
    """
    Unified interface for Kurultai memory system.
    
    Routes operations to appropriate store:
    - Tasks/Notifications → SQLiteStore (ACID)
    - Agent Memories → FileStore (Markdown)
    - Graph queries → Neo4jStore (when available)
    """
    
    def __init__(self, 
                 sqlite_path: str = "/data/db/kurultai.db",
                 mem_path: str = "/data/mem",
                 neo4j_uri: Optional[str] = None,
                 fallback_mode: bool = True):
        
        self.sqlite = SQLiteStore(sqlite_path)
        self.files = FileStore(mem_path)
        self.neo4j = Neo4jStore(neo4j_uri) if neo4j_uri else None
        self.fallback_mode = fallback_mode
        
    def create_task(self, task_type: str, description: str, 
                    delegated_by: str, assigned_to: str = "any") -> str:
        """Create a new task."""
        # Primary: SQLite
        task_id = self.sqlite.create_task(task_type, description, 
                                          delegated_by, assigned_to)
        
        # Sync: FileStore
        self.files.log_task(task_id, task_type, description, delegated_by)
        
        # Optional: Neo4j
        if self.neo4j:
            try:
                self.neo4j.create_task_node(task_id, ...)
            except:
                if not self.fallback_mode:
                    raise
        
        return task_id
    
    def claim_next_task(self, agent_name: str) -> Optional[Dict]:
        """Claim next available task (ACID protected)."""
        # SQLite handles race conditions via transactions
        return self.sqlite.claim_next_task(agent_name)
    
    def get_agent_memories(self, agent_name: str, limit: int = 10) -> List[Dict]:
        """Get memories for an agent."""
        # Primary: FileStore (fast, human-readable)
        return self.files.get_agent_memories(agent_name, limit)
    
    def add_agent_memory(self, agent_name: str, memory_type: str, 
                         content: str, **kwargs):
        """Add memory for an agent."""
        # Primary: FileStore (Markdown)
        self.files.add_memory(agent_name, memory_type, content)
        
        # Index: SQLite (for search)
        self.sqlite.index_memory(agent_name, memory_type, content)
        
        # Optional: Neo4j
        if self.neo4j:
            try:
                self.neo4j.add_memory_node(...)
            except:
                pass
```

### SQLiteStore (ACID Operations)

```python
import sqlite3
from contextlib import contextmanager

class SQLiteStore:
    """SQLite-backed store for tasks and notifications."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def claim_next_task(self, agent_name: str) -> Optional[Dict]:
        """
        Atomically claim next task.
        Uses SELECT FOR UPDATE pattern for race condition protection.
        """
        with self._connection() as conn:
            cursor = conn.cursor()
            
            # Start transaction with immediate lock
            cursor.execute("BEGIN IMMEDIATE")
            
            try:
                # Find next pending task
                cursor.execute("""
                    SELECT * FROM tasks 
                    WHERE status = 'pending' 
                    AND (assigned_to = ? OR assigned_to = 'any')
                    ORDER BY priority DESC, created_at ASC
                    LIMIT 1
                """, (agent_name,))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                # Claim it atomically
                task_id = row['id']
                cursor.execute("""
                    UPDATE tasks 
                    SET status = 'claimed', 
                        claimed_by = ?,
                        claimed_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'pending'
                """, (agent_name, task_id))
                
                # Verify claim succeeded (row count = 1)
                if cursor.rowcount == 0:
                    # Another agent claimed it
                    raise RaceConditionError("Task was claimed by another agent")
                
                conn.commit()
                return dict(row)
                
            except:
                conn.rollback()
                raise
```

### FileStore (Markdown Memories)

```python
import os
from datetime import datetime
from pathlib import Path

class FileStore:
    """File-based store for agent memories and logs."""
    
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.agents_path = self.base_path / "agents"
        self.tasks_path = self.base_path / "tasks.json"
        
        # Ensure directories exist
        self.agents_path.mkdir(parents=True, exist_ok=True)
    
    def get_agent_memories(self, agent_name: str, limit: int = 10) -> List[Dict]:
        """Read memories from agent's Markdown file."""
        file_path = self.agents_path / f"{agent_name.lower()}.md"
        
        if not file_path.exists():
            return []
        
        memories = []
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Parse Markdown sections
        current_section = None
        for line in content.split('\n'):
            if '## 🔍 Personal Observations' in line:
                current_section = 'observation'
            elif '## 📚 Key Learnings' in line:
                current_section = 'learning'
            elif '## 💡 Signature Insights' in line:
                current_section = 'insight'
            elif line.startswith('- ') and current_section:
                memories.append({
                    'agent_name': agent_name,
                    'memory_type': current_section,
                    'content': line[2:].strip(),
                    'created_at': datetime.now().isoformat()
                })
        
        return memories[:limit]
    
    def add_memory(self, agent_name: str, memory_type: str, content: str):
        """Append memory to agent's Markdown file."""
        file_path = self.agents_path / f"{agent_name.lower()}.md"
        
        # Determine section header
        section_map = {
            'observation': '## 🔍 Personal Observations',
            'learning': '📚 Key Learnings',
            'insight': '## 💡 Signature Insights',
            'interaction': '## 🤝 Agent Interactions'
        }
        section = section_map.get(memory_type, '## 📝 Notes')
        
        # Append to file
        with open(file_path, 'a') as f:
            f.write(f"\n{section}\n")
            f.write(f"- {content}  <!-- {datetime.now().isoformat()} -->\n")
```

---

## 9. Migration Plan

### Step 1: Data Export (Before deployment)

```bash
# Export existing Neo4j data if accessible
python scripts/export_neo4j_data.py \
  --output data/migration/export_$(date +%Y%m%d).json
```

### Step 2: Deploy New Adapter

```bash
# Deploy with feature flag
UNIFIED_MEMORY_ENABLED=true \
  NEO4J_FALLBACK_MODE=true \
  SQLITE_PATH=/data/db/kurultai.db \
  python start_server.py
```

### Step 3: Verify Operations

```bash
# Run pre-flight checks
python scripts/check_environment.py

# Test task creation
python -c "
from openclaw_memory import UnifiedMemoryAdapter
mem = UnifiedMemoryAdapter()
task_id = mem.create_task('test', 'Migration test', 'kublai')
print(f'Created task: {task_id}')
"
```

### Step 4: Monitor and Rollback Plan

If issues occur:
```bash
# Instant rollback
UNIFIED_MEMORY_ENABLED=false \
  NEO4J_FALLBACK_MODE=true \
  python start_server.py
```

---

## 10. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| SQLite concurrency issues | Low | High | Use IMMEDIATE transactions, test with all 6 agents |
| Data loss during migration | Low | Critical | Backup before migration, idempotent writes |
| File permissions on Railway | Medium | High | Test in Railway staging, proper volume mounts |
| Performance degradation | Low | Medium | Add indexes, implement caching layer |
| Neo4j never comes back | Medium | Low | Hybrid design handles this gracefully |

---

## 11. Decision

**DECISION: Implement Hybrid Architecture (Option 6)**

### Immediate Actions (Today):
1. Create `UnifiedMemoryAdapter` class
2. Implement `SQLiteStore` with ACID task claiming
3. Implement `FileStore` for agent memories
4. Deploy to Railway with volumes configured

### Success Criteria:
- ✅ All 6 agents can create/claim/complete tasks
- ✅ Agent memories persist and are readable
- ✅ No race conditions on task claiming
- ✅ System works without Neo4j connection

### Future State:
When Railway Neo4j networking is fixed:
- Re-enable Neo4j for graph queries and vector search
- Use as enhancement layer, not dependency
- Maintain SQLite/FileStore for durability

---

## 12. Appendix

### A. Environment Variables

```bash
# New variables
UNIFIED_MEMORY_ENABLED=true
SQLITE_PATH=/data/db/kurultai.db
MEMORY_FILES_PATH=/data/mem
SYNC_INTERVAL_SECONDS=60

# Existing (unchanged)
OPENCLAW_GATEWAY_TOKEN=...
SIGNAL_ACCOUNT=...
```

### B. File Locations

| Purpose | Path | Persistence |
|---------|------|-------------|
| SQLite DB | `/data/db/kurultai.db` | Railway Volume |
| Agent Memories | `/data/mem/agents/*.md` | Railway Volume |
| Task Logs | `/data/mem/tasks.json` | Railway Volume |
| Backups | `/data/backup/` | Railway Volume |

### C. Monitoring Queries

```sql
-- Task queue health
SELECT status, COUNT(*) FROM tasks GROUP BY status;

-- Agent workload
SELECT claimed_by, COUNT(*) FROM tasks 
WHERE status = 'claimed' GROUP BY claimed_by;

-- Pending tasks
SELECT * FROM tasks 
WHERE status = 'pending' 
ORDER BY priority DESC, created_at ASC;
```

---

**Document Version:** 1.0  
**Author:** Kublai (Router/Orchestrator)  
**Reviewers:** Temüjin (Implementation), Jochi (Testing)  
**Next Review:** After Phase 1 completion
