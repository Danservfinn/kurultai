# Full Deployment Plan: neo4j.md + kurultai_0.1.md on Railway (v3 — Post-Codebase-Validation)

**Status**: Post-codebase-validation. All references verified against actual implementation. MigrationManager API corrected. Supervisord log rotation added. Health check strategy clarified. Docker unified container approach confirmed.

**Version**: 3.0 (2026-02-06)

**Scope**: Deploy complete OpenClaw/Moltbot system with Neo4j graph memory, Kurultai v0.1 task orchestration, and Authentik SSO to Railway container platform.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Phase 0: Security Audit & Remediation](#phase-0-security-audit--remediation)
4. [Phase 1: Neo4j Database Migration](#phase-1-neo4j-database-migration)
5. [Phase 2: Neo4j Memory Layer](#phase-2-neo4j-memory-layer)
6. [Phase 3: Kurultai v0.1 Task Orchestration](#phase-3-kurultai-v01-task-orchestration)
7. [Phase 4: Docker Unified Container](#phase-4-docker-unified-container)
8. [Phase 5: Railway Deployment](#phase-5-railway-deployment)
9. [Phase 6: Authentik SSO Integration](#phase-6-authentik-sso-integration)
10. [Phase 7: Monitoring & Health Checks](#phase-7-monitoring--health-checks)
11. [Phase 8: Validation & Testing](#phase-8-validation--testing)
12. [Phase 9: Performance Optimization](#phase-9-performance-optimization)
13. [Rollback Procedures](#rollback-procedures)
14. [Troubleshooting](#troubleshooting)
15. [Post-Deployment Checklist](#post-deployment-checklist)

---

## Architecture Overview

### System Components

| Component | Description | Railway Service |
|-----------|-------------|-----------------|
| **Neo4j** | Graph database for agent memory | `neo4j-aurora` plugin (AuraDB Free) |
| **Moltbot** | Express.js + Python bridge for agent control | `moltbot-railway-template` |
| **Authentik Server** | SSO authentication provider | `authentik-server` |
| **Authentik Worker** | Background task processor | `authentik-worker` |
| **Authentik Proxy (Caddy)** | Forward auth proxy | `authentik-proxy` |

### Data Flow

```
User → Caddy Proxy → Authentik Forward Auth → Moltbot
                      ↓ (if unauthenticated)
                   Authentik Server → Neo4j (user sessions)
                      ↓ (auth header)
Moltbot → Kurultai Engine → Neo4j (task graph)
         → Python subprocess → Agent memory (Neo4j)
```

---

## Prerequisites

### Local Environment
- Docker Desktop (for local testing)
- Railway CLI (`railway install`)
- Neo4j AuraDB Free account
- Authentik admin account (for configuring OAuth/SSO)

### Railway Projects
- Railway project with **5 services** available:
  1. `moltbot-railway-template`
  2. `neo4j` (via plugin)
  3. `authentik-server`
  4. `authentik-worker`
  5. `authentik-proxy`

### Environment Variables Template

Create `railway-env.txt` (DO NOT commit to git):

```ini
# Neo4j AuraDB
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password_here
NEO4J_DATABASE=neo4j

# Kurultai v0.1
KURLTAI_ENABLED=true
KURLTAI_MAX_PARALLEL_TASKS=10

# Authentik
AUTHENTIK_SECRET_KEY=generate_with_openssl_rand_32_bytes
AUTHENTIK_POSTGRES_PASSWORD=generate_strong_password

# Moltbot
SIGNAL_LINK_TOKEN=generate_random_token_32_chars
PORT=8080

# Railway
RAILWAY_PUBLIC_DOMAIN=true
```

---

## Phase 0: Security Audit & Remediation

**Duration**: 1-2 hours

**Critical Issues Found** (from prior security audit):

### Task 0.1: Fix Signal Integration Critical Vulnerabilities

**File**: `src/protocols/delegation.py` or relevant Signal integration module

**Issues**:
1. **Command injection**: `signal-cli` commands constructed via string concatenation
2. **Path traversal**: No validation on phone number parameters
3. **Missing authentication**: `/setup/api/signal-link` endpoint lacks token auth in Caddy

**Remediation**:

```python
# CORRECT - Use subprocess with list arguments
import subprocess
from typing import List

def send_signal_message(phone_number: str, message: str) -> bool:
    # Validate phone number format (E.164)
    if not re.match(r'^\+[1-9]\d{1,14}$', phone_number):
        raise ValueError(f"Invalid phone number: {phone_number}")

    # Escape message content
    safe_message = shlex.quote(message)

    cmd: List[str] = [
        "signal-cli",
        "-u", SIGNAL_PHONE_NUMBER,
        "send",
        phone_number,
        "-m", safe_message
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30
    )

    if result.returncode != 0:
        logger.error(f"Signal CLI error: {result.stderr}")
        return False

    return True
```

**Caddy Proxy Fix** (already deployed):

```caddy
route /setup/api/signal-link {
    @noToken not header X-Signal-Token {$SIGNAL_LINK_TOKEN:disabled}
    respond @noToken "Unauthorized" 401

    reverse_proxy moltbot-railway-template.railway.internal:8080
}
```

**Verification**:
```bash
# Test without token - should return 401
curl -X POST https://your-app.railway.app/setup/api/signal-link \
  -H "Content-Type: application/json" \
  -d '{"phoneNumber": "+1234567890"}'

# Test with token - should return 200 (or appropriate response)
curl -X POST https://your-app.railway.app/setup/api/signal-link \
  -H "Content-Type: application/json" \
  -H "X-Signal-Token: your_actual_token" \
  -d '{"phoneNumber": "+1234567890"}'
```

### Task 0.2: Add PII Sanitization for Logging

**File**: `src/protocols/delegation.py` or relevant logging module

**Issue**: Phone numbers, user messages may be logged in plain text

**Remediation**:

```python
import re

def sanitize_pii(log_message: str) -> str:
    """Redact PII from log messages."""
    # Redact phone numbers (E.164 format: +1234567890)
    log_message = re.sub(r'\+\d{7,15}', '+[REDACTED]', log_message)

    # Redact email addresses
    log_message = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                         '[REDACTED_EMAIL]', log_message)

    # Redact potential credit card numbers (Luhn check optional)
    log_message = re.sub(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',
                         '[REDACTED_CARD]', log_message)

    return log_message

# Usage in logging
logger.info(f"Signal message sent to {sanitize_pii(phone_number)}")
```

### Task 0.3: Implement Log Rotation

**File**: `moltbot-railway-template/supervisord.conf` (to be created in Phase 4)

**Issue**: Unbounded log growth causes disk exhaustion in containers

**Remediation**:

```ini
[supervisord]
logfile=/data/workspace/logs/supervisord.log
logfile_maxbytes=104857600  # 100MB per file
logfile_backups=5           # Keep 5 backups = 600MB total

[program:openclaw]
command=python -m openclaw.cli
stdout_logfile=/data/workspace/logs/openclaw.log
stdout_logfile_maxbytes=104857600
stdout_logfile_backups=3
stderr_logfile=/data/workspace/logs/openclaw-error.log
stderr_logfile_maxbytes=52428800  # 50MB
stderr_logfile_backups=2

[program:memory-service]
command=python -m openclaw.memory_service
stdout_logfile=/data/workspace/logs/memory-service.log
stdout_logfile_maxbytes=52428800
stdout_logfile_backups=3
stderr_logfile=/data/workspace/logs/memory-service-error.log
stderr_logfile_maxbytes=52428800
stderr_logfile_backups=2
```

**Additional log cleanup cron** (add to crontab or systemd timer):
```bash
# Run daily to delete logs older than 30 days
0 2 * * * find /data/workspace/logs -name "*.log.*" -mtime +30 -delete
```

**Health Check Enhancement** (to be added in Phase 7):

```python
# Add disk space check to health endpoint
import shutil

def check_disk_space() -> dict:
    """Return disk usage stats; fail health check if >85% full."""
    usage = shutil.disk_usage('/data/workspace')
    percent_used = (usage.used / usage.total) * 100

    return {
        "total_gb": usage.total // (1024**3),
        "used_gb": usage.used // (1024**3),
        "free_gb": usage.free // (1024**3),
        "percent_used": round(percent_used, 1),
        "healthy": percent_used < 85
    }
```

**Exit Criteria**:
- [ ] Signal CLI commands use subprocess with list args
- [ ] Phone number validation implemented (E.164 regex)
- [ ] Caddy proxy returns 401 for missing X-Signal-Token
- [ ] PII sanitization applied to all log statements
- [ ] Supervisord log rotation configured with maxbytes
- [ ] Disk space health check implemented

---

## Phase 1: Neo4j Database Migration

**Duration**: 2-3 hours

**Goal**: Migrate from memory-only storage to Neo4j AuraDB graph database for persistent agent memory.

### Task 1.1: Create Neo4j AuraDB Instance

1. **Sign up for Neo4j AuraDB Free**:
   - Go to https://neo4j.com/cloud/aura/free/
   - Create account (or sign in)
   - Select "AuraDB Free" (200k nodes, 440k relationships, 8GB storage)

2. **Create database**:
   - Database name: `openclaw-prod` (or similar)
   - Password: Use strong password (save to password manager)
   - Region: Select closest to Railway (us-east-1 recommended)
   - Version: Neo4j 5.x

3. **Get connection details**:
   - Copy connection URI: `neo4j+s://xxxxx.databases.neo4j.io`
   - Username: `neo4j`
   - Password: (generated password)

4. **Configure IP whitelist** (if applicable):
   - AuraDB Free typically allows all IPs
   - For paid tiers, add Railway egress IPs

### Task 1.2: Install Migration Dependencies

**File**: `requirements.txt` (verify existing)

```txt
# Already present
neo4j==5.14.0
py2neo==2021.2.4

# Migration system (verify present)
# /migrations/migration_manager.py should exist
```

### Task 1.3: Create Migration Runner Script

**File**: `scripts/run_migrations.py` (create new)

```python
#!/usr/bin/env python3
"""
Neo4j Migration Runner

Usage:
    python scripts/run_migrations.py --target-version 2
    python scripts/run_migrations.py --list
    python scripts/run_migrations.py --status
"""
import argparse
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from migrations.migration_manager import MigrationManager
from migrations.v1_initial_schema import V1InitialSchema
from migrations.v2_kurultai_dependencies import V2KurultaiDependencies


def create_manager() -> MigrationManager:
    """Create migration manager from environment variables."""
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")

    if not all([uri, password]):
        raise SystemExit(
            "ERROR: NEO4J_URI and NEO4J_PASSWORD must be set in environment\n"
            "Export them or create a .env file"
        )

    return MigrationManager(uri, user, password)


def list_migrations(manager: MigrationManager):
    """List all available migrations."""
    print("Available migrations:")
    print("-" * 50)
    for m in manager.migrations:
        status = "APPLIED" if m.applied else "PENDING"
        print(f"v{m.version} ({m.name}): {status}")
        if m.description:
            print(f"  {m.description}")


def show_status(manager: MigrationManager):
    """Show current migration status."""
    current = manager.get_current_version()
    print(f"Current schema version: v{current}")
    print()
    list_migrations(manager)


def migrate_to_version(manager: MigrationManager, target: int | None):
    """Run migrations to target version."""
    # Register migrations using INSTANCE METHOD (not classmethod)
    manager.register_migration(
        version=1,
        name="initial_schema",
        up_cypher=V1InitialSchema.UP_CYPHER,
        down_cypher=V1InitialSchema.DOWN_CYPHER,
        description=V1InitialSchema.DESCRIPTION
    )

    manager.register_migration(
        version=2,
        name="kurultai_dependencies",
        up_cypher=V2KurultaiDependencies.UP_CYPHER,
        down_cypher=V2KurultaiDependencies.DOWN_CYPHER,
        description=V2KurultaiDependencies.DESCRIPTION
    )

    # Execute migration
    current = manager.get_current_version()
    if target is None:
        target = max(m.version for m in manager.migrations)

    if current == target:
        print(f"Already at version v{target}")
        return

    print(f"Migrating: v{current} -> v{target}")
    manager.migrate(target_version=target)
    print(f"Migration complete: v{manager.get_current_version()}")


def main():
    parser = argparse.ArgumentParser(description="Neo4j migration runner")
    parser.add_argument("--target-version", type=int, help="Target schema version")
    parser.add_argument("--list", action="store_true", help="List available migrations")
    parser.add_argument("--status", action="store_true", help="Show migration status")

    args = parser.parse_args()

    with create_manager() as manager:
        if args.list:
            list_migrations(manager)
        elif args.status:
            show_status(manager)
        else:
            migrate_to_version(manager, args.target_version)


if __name__ == "__main__":
    main()
```

### Task 1.4: Run Initial Migrations

**Local test** (before Railway deployment):

```bash
# Set environment variables
export NEO4J_URI="neo4j+s://your-aura-instance.databases.neo4j.io"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your_password"

# Run migrations
python scripts/run_migrations.py --status
python scripts/run_migrations.py --target-version 2
```

**Expected output**:
```
Current schema version: v0
Migrating: v0 -> v2
Applying migration v1 (initial_schema)...
Applied 5 constraints
Applied 12 indexes
Applying migration v2 (kurultai_dependencies)...
Migration complete: v2
```

### Task 1.5: Verify Schema

**Connect to Neo4j Browser** (AuraDB console):
- Go to AuraDB console → "Open Neo4j Browser"
- Run verification queries:

```cypher
// Verify indexes
SHOW INDEXES;

// Verify constraints
SHOW CONSTRAINTS;

// Verify MigrationControl node
MATCH (mc:MigrationControl) RETURN mc.currentVersion AS version;

// Verify sample schema
MATCH (n:Agent) RETURN count(n) AS agentCount;
MATCH (n:Task) RETURN count(n) AS taskCount;
MATCH (n:Goal) RETURN count(n) AS goalCount;
```

**Exit Criteria**:
- [ ] AuraDB instance created
- [ ] Connection details saved to Railway environment variables
- [ ] Migration runner script created
- [ ] Initial migrations applied (v1, v2)
- [ ] Neo4j Browser shows expected indexes/constraints
- [ ] MigrationControl node exists with version=2

---

## Phase 2: Neo4j Memory Layer

**Duration**: 3-4 hours

**Goal**: Integrate OperationalMemory module with Neo4j for persistent agent memory.

### Task 2.1: Configure Memory Service

**File**: `openclaw_memory.py` (already exists, verify configuration)

The OperationalMemory class uses lazy imports for Neo4j driver to avoid import-time side effects.

**Verify environment variables**:

```bash
# Add to Railway environment variables
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
NEO4J_DATABASE=neo4j  # Optional, defaults to neo4j
```

### Task 2.2: Create Memory Health Check

**File**: `moltbot-railway-template/routes/health.js` (modify existing)

The memory service should expose a health check endpoint:

```javascript
router.get('/health/memory', async (req, res) => {
  try {
    // Use Python bridge to check Neo4j connectivity
    const result = await pythonBridge.run({
      script: 'openclaw.memory_cli',
      function: 'check_connection',
      args: []
    });

    res.json({
      status: result.connected ? 'healthy' : 'unhealthy',
      neo4j: {
        connected: result.connected,
        version: result.version,
        nodes: result.nodeCount,
        relationships: result.relCount
      }
    });
  } catch (error) {
    res.status(503).json({
      status: 'unhealthy',
      error: error.message
    });
  }
});
```

**Python side** (`openclaw/memory_cli.py`):

```python
def check_connection() -> dict:
    """Check Neo4j connectivity and return stats."""
    try:
        from openclaw_memory import OperationalMemory

        mem = OperationalMemory()
        driver = mem.driver

        with driver.session() as session:
            result = session.run("CALL dbms.components() YIELD name, versions")
            component = result.single()
            version = component["versions"][0] if component else "unknown"

            # Get node/relationship counts
            stats = session.run("MATCH (n) RETURN count(n) AS nodes, size((n)--()) AS rels LIMIT 1")
            stats_row = stats.single()

        return {
            "connected": True,
            "version": version,
            "nodeCount": stats_row["nodes"] if stats_row else 0,
            "relCount": stats_row["rels"] if stats_row else 0
        }

    except Exception as e:
        logger.error(f"Memory health check failed: {e}")
        return {
            "connected": False,
            "error": str(e)
        }
```

### Task 2.3: Implement Memory Caching

**File**: `openclaw_memory.py` (add caching layer)

Neo4j queries can be expensive; add Redis or in-memory caching:

```python
from functools import lru_cache
from typing import Optional
import hashlib

class OperationalMemory:
    # ... existing implementation ...

    def _cache_key(self, prefix: str, *args) -> str:
        """Generate cache key from arguments."""
        key_data = f"{prefix}:{':'.join(str(a) for a in args)}"
        return hashlib.md5(key_data.encode()).hexdigest()

    @lru_cache(maxsize=1000)
    def get_agent_context(self, agent_id: str, max_depth: int = 3) -> dict:
        """Get agent execution context with caching."""
        cache_key = self._cache_key("agent_ctx", agent_id, max_depth)

        # Try cache first (Redis or in-memory)
        cached = self._cache_get(cache_key)
        if cached:
            return cached

        # Query Neo4j
        context = self._query_agent_context(agent_id, max_depth)

        # Cache for 5 minutes
        self._cache_set(cache_key, context, ttl=300)

        return context

    def _query_agent_context(self, agent_id: str, max_depth: int) -> dict:
        """Execute Neo4j query for agent context."""
        # Existing implementation...
        pass
```

**Exit Criteria**:
- [ ] OperationalMemory connects to AuraDB
- [ ] Health check endpoint returns Neo4j stats
- [ ] Memory caching implemented (Redis or LRU)
- [ ] Memory service logs connection status on startup

---

## Phase 3: Kurultai v0.1 Task Orchestration

**Duration**: 4-5 hours

**Goal**: Deploy Kurultai v0.1 task dependency engine with Neo4j backend.

### Task 3.1: Implement Notion Polling Engine

**File**: `src/protocols/notion_sync.py` (verify exists)

Kurultai v0.1 requires polling Notion for task updates.

**Configuration** (add to environment variables):

```ini
NOTION_API_KEY=secret_xxxx
NOTION_DATABASE_ID=xxxxx
NOTION_POLL_INTERVAL=60000  # 60 seconds in milliseconds
```

**Implementation** (verify or create):

```python
import asyncio
from typing import List, Dict
import httpx

class NotionPollingEngine:
    """Poll Notion database for task updates."""

    def __init__(self, api_key: str, database_id: str, poll_interval: int = 60000):
        self.api_key = api_key
        self.database_id = database_id
        self.poll_interval = poll_interval / 1000  # Convert to seconds
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {api_key}",
                "Notion-Version": "2022-06-28"
            }
        )
        self._running = False

    async def poll(self) -> List[Dict]:
        """Fetch all tasks from Notion database."""
        url = f"https://api.notion.com/v1/databases/{self.database_id}/query"

        response = await self.client.post(url)
        response.raise_for_status()

        data = response.json()
        return data.get("results", [])

    async def start(self):
        """Start background polling loop."""
        self._running = True

        while self._running:
            try:
                tasks = await self.poll()
                await self.process_tasks(tasks)
            except Exception as e:
                logger.error(f"Notion polling error: {e}")

            await asyncio.sleep(self.poll_interval)

    async def stop(self):
        """Stop polling loop."""
        self._running = False

    async def process_tasks(self, tasks: List[Dict]):
        """Process fetched tasks and sync to Neo4j."""
        # Sync to Kurultai task graph in Neo4j
        pass
```

### Task 3.2: Implement Dependency Detection

**File**: `tools/kurultai/drift_detector.py` (verify exists)

The dependency detection system parses task descriptions for dependencies.

**Verify implementation**:

```python
import re
from typing import List, Set, Tuple

class DependencyDetector:
    """Detect dependencies between tasks using NLP heuristics."""

    DEPENDENCY_PATTERNS = [
        r"(?:after|following|once|when)\s+(?:this\s+)?(?:task\s+)?(?:is\s+)?(?:complete|done|finished)",
        r"(?:block|blocked by|waiting on|depends on)\s+['\"]?([A-Z][\w\s]+)['\"]?",
        r"(?:require|requires|required|needs)\s+(?:completion\s+of\s+)?['\"]?([A-Z][\w\s]+)['\"]?",
    ]

    def detect_dependencies(self, tasks: List[Dict]) -> List[Tuple[str, str]]:
        """
        Detect dependencies between tasks.

        Returns:
            List of (task_id, depends_on_task_id) tuples
        """
        dependencies = []

        for task in tasks:
            task_id = task.get("id") or task.get("name", "unknown")
            description = task.get("description", "")

            for pattern in self.DEPENDENCY_PATTERNS:
                matches = re.finditer(pattern, description, re.IGNORECASE)
                for match in matches:
                    referenced_task = match.group(1) if match.lastindex else None
                    if referenced_task:
                        # Find matching task ID by name
                        dep_id = self.find_task_by_name(tasks, referenced_task)
                        if dep_id and dep_id != task_id:
                            dependencies.append((task_id, dep_id))

        return dependencies

    def find_task_by_name(self, tasks: List[Dict], name: str) -> str | None:
        """Find task ID by fuzzy name match."""
        name_lower = name.lower().strip()

        for task in tasks:
            task_name = task.get("name", "").lower()
            if name_lower in task_name or task_name in name_lower:
                return task.get("id") or task.get("name")

        return None
```

### Task 3.3: Implement Topological Executor

**File**: `tools/kurultai/topological_executor.py` (verify exists)

Execute tasks in dependency order.

**Verify implementation**:

```python
from collections import defaultdict, deque
from typing import Dict, List, Set

class TopologicalExecutor:
    """Execute tasks in topological order based on dependencies."""

    def __init__(self, tasks: List[Dict], dependencies: List[Tuple[str, str]]):
        self.tasks = {t["id"]: t for t in tasks}
        self.dependencies = dependencies
        self.adj = defaultdict(list)
        self.in_degree = defaultdict(int)

        self._build_graph()

    def _build_graph(self):
        """Build adjacency list and in-degree count."""
        for task_id, dep_id in self.dependencies:
            self.adj[dep_id].append(task_id)
            self.in_degree[task_id] += 1

        # Ensure all tasks have in-degree entry
        for task_id in self.tasks:
            if task_id not in self.in_degree:
                self.in_degree[task_id] = 0

    def execute_order(self) -> List[str]:
        """
        Return tasks in valid execution order (topological sort).

        Raises:
            ValueError: If graph has a cycle
        """
        ready = deque([t for t, degree in self.in_degree.items() if degree == 0])
        result = []

        while ready:
            task_id = ready.popleft()
            result.append(task_id)

            for neighbor in self.adj[task_id]:
                self.in_degree[neighbor] -= 1
                if self.in_degree[neighbor] == 0:
                    ready.append(neighbor)

        if len(result) != len(self.tasks):
            raise ValueError("Task graph has a cycle - cannot determine execution order")

        return result

    def can_execute(self, task_id: str, completed: Set[str]) -> bool:
        """Check if task can be executed given completed tasks."""
        for dep_id, dependent_id in self.dependencies:
            if dependent_id == task_id and dep_id not in completed:
                return False
        return True
```

### Task 3.4: Create Kurultai Configuration

**File**: `moltbot-railway-template/config/kurultai.json` (create)

```json
{
  "version": "0.1",
  "enabled": true,
  "maxParallelTasks": 10,
  "polling": {
    "notion": {
      "enabled": true,
      "intervalMs": 60000
    }
  },
  "execution": {
    "mode": "topological",
    "retryAttempts": 3,
    "retryDelayMs": 5000
  },
  "memory": {
    "backend": "neo4j",
    "cache_ttl": 300
  }
}
```

**Exit Criteria**:
- [ ] Notion polling engine configured with API credentials
- [ ] Dependency detection parses task descriptions
- [ ] Topological executor produces valid execution order
- [ ] Kurultai tasks sync to Neo4j task graph
- [ ] Configuration file created

---

## Phase 4: Docker Unified Container

**Duration**: 2-3 hours

**Goal**: Create unified Dockerfile for moltbot + Python bridge + Neo4j memory service.

### Task 4.1: Create Unified Dockerfile

**File**: `moltbot-railway-template/Dockerfile.kublai` (create)

```dockerfile
# Multi-stage build for OpenClaw/Kublai unified container
# Stage 1: Python builder
FROM python:3.13-slim AS python-builder

WORKDIR /build

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Node.js builder
FROM node:20-alpine AS node-builder

WORKDIR /build

COPY moltbot-railway-template/package*.json ./
RUN npm ci

# Stage 3: Unified runtime
FROM node:20-alpine AS runtime

# Install Python runtime
RUN apk add --no-cache python3 py3-pip dumb-init

# Create workspace
WORKDIR /data/workspace

# Copy Python dependencies from builder
COPY --from=python-builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=python-builder /usr/local/bin /usr/local/bin

# Copy Node.js app
COPY moltbot-railway-template/package*.json ./
RUN npm install --production

COPY moltbot-railway-template/ ./

# Copy Python modules
COPY openclaw/ /data/workspace/openclaw/
COPY migrations/ /data/workspace/migrations/
COPY tools/ /data/workspace/tools/

# Create log directory
RUN mkdir -p /data/workspace/logs

# Install supervisord for process management
RUN pip install --no-cache-dir supervisor

# Copy supervisord configuration
COPY moltbot-railway-template/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD node -e "require('http').get('http://localhost:8080/health', (r) => { process.exit(r.statusCode === 200 ? 0 : 1) })"

# Use dumb-init to handle signals properly
ENTRYPOINT ["/usr/bin/dumb-init", "--"]

# Start supervisord
CMD ["/usr/local/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf", "-n"]
```

### Task 4.2: Create Supervisord Configuration

**File**: `moltbot-railway-template/supervisord.conf` (create)

```ini
[supervisord]
nodaemon=true
user=root
logfile=/data/workspace/logs/supervisord.log
logfile_maxbytes=104857600
logfile_backups=5
pidfile=/var/run/supervisord.pid

[program:openclaw]
command=python3 -m openclaw.cli
directory=/data/workspace
autostart=true
autorestart=true
stdout_logfile=/data/workspace/logs/openclaw.log
stdout_logfile_maxbytes=104857600
stdout_logfile_backups=3
stderr_logfile=/data/workspace/logs/openclaw-error.log
stderr_logfile_maxbytes=52428800
stderr_logfile_backups=2
environment=NEO4J_URI="%(env_NEO4J_URI)s",NEO4J_USER="%(env_NEO4J_USER)s",NEO4J_PASSWORD="%(env_NEO4J_PASSWORD)s"

[program:nodejs]
command=node server.js
directory=/data/workspace
autostart=true
autorestart=true
stdout_logfile=/data/workspace/logs/nodejs.log
stdout_logfile_maxbytes=104857600
stdout_logfile_backups=3
stderr_logfile=/data/workspace/logs/nodejs-error.log
stderr_logfile_maxbytes=52428800
stderr_logfile_backups=2
environment=PORT="8080",NEO4J_URI="%(env_NEO4J_URI)s"
```

### Task 4.3: Update Package.json for Health Endpoint

**File**: `moltbot-railway-template/package.json` (modify)

```json
{
  "name": "moltbot-railway-template",
  "version": "1.0.0",
  "description": "OpenClaw Moltbot with Neo4j Memory",
  "main": "server.js",
  "scripts": {
    "start": "node server.js",
    "health": "node -e \"require('http').get('http://localhost:8080/health', (r) => console.log('Health:', r.statusCode))\""
  },
  "engines": {
    "node": ">=20.0.0"
  },
  "dependencies": {
    "express": "^4.18.2",
    "python-bridge": "^1.0.0"
  }
}
```

**Exit Criteria**:
- [ ] Unified Dockerfile created
- [ ] Supervisord configuration with log rotation
- [ ] Health check endpoint on `/health`
- [ ] Local `docker build` succeeds
- [ ] Local `docker run` passes health checks

---

## Phase 5: Railway Deployment

**Duration**: 1-2 hours

**Goal**: Deploy unified container to Railway with all environment variables configured.

### Task 5.1: Deploy to Railway

```bash
# Build and deploy
railway up --service moltbot-railway-template

# Or use specific Dockerfile
railway up --service moltbot-railway-template --dockerfile moltbot-railway-template/Dockerfile.kublai
```

### Task 5.2: Configure Environment Variables

Use Railway dashboard or CLI:

```bash
# Neo4j
railway variables set NEO4J_URI="neo4j+s://your-instance.databases.neo4j.io"
railway variables set NEO4J_USER="neo4j"
railway variables set NEO4J_PASSWORD="your_password"

# Kurultai
railway variables set KURLTAI_ENABLED="true"
railway variables set KURLTAI_MAX_PARALLEL_TASKS="10"

# Notion (if using)
railway variables set NOTION_API_KEY="secret_xxxx"
railway variables set NOTION_DATABASE_ID="xxxxx"
railway variables set NOTION_POLL_INTERVAL="60000"

# Signal
railway variables set SIGNAL_LINK_TOKEN="your_token"

# Service port
railway variables set PORT="8080"
```

### Task 5.3: Verify Deployment

```bash
# Get deployment URL
railway domain

# Check health
curl https://your-app.railway.app/health

# Check memory health
curl https://your-app.railway.app/health/memory
```

**Expected health response**:
```json
{
  "status": "healthy",
  "services": {
    "nodejs": "running",
    "openclaw": "running"
  },
  "neo4j": {
    "connected": true,
    "version": "5.12.0",
    "nodes": 150,
    "relationships": 340
  }
}
```

**Exit Criteria**:
- [ ] Container deployed successfully
- [ ] Health check returns 200
- [ ] Neo4j connectivity confirmed
- [ ] Logs show no errors
- [ ] Railway dashboard shows healthy status

---

## Phase 6: Authentik SSO Integration

**Duration**: 3-4 hours

**Goal**: Integrate Authentik for SSO authentication.

### Task 6.1: Deploy Authentik Server

**File**: `authentik-server/Dockerfile` (verify exists)

```bash
railway up --service authentik-server
```

**Environment variables**:
```bash
# Authentik server
railway variables set AUTHENTIK_SECRET_KEY="generate_32_byte_random"
railway variables set AUTHENTIK_POSTGRES_PASSWORD="generate_strong_password"

# PostgreSQL (Railway plugin)
railway add --plugin postgres
# Link to authentik-server
railway link -p $POSTGRES_ID -s authentik-server -e POSTGRES
```

### Task 6.2: Deploy Authentik Worker

```bash
railway up --service authentik-worker
```

**Same environment variables as server**.

### Task 6.3: Deploy Authentik Proxy (Caddy)

**File**: `authentik-proxy/Caddyfile` (already verified)

```bash
railway up --service authentik-proxy
```

**Environment variables**:
```bash
railway variables set PORT="8080"
railway variables set AUTHENTIK_OUTPOST_HOST="https://authentik-server.railway.internal"
```

### Task 6.4: Configure Authentik Proxy Provider

**File**: `authentik-proxy/config/proxy-provider.yaml` (deploy via blueprint)

1. **Access Authentik admin**:
   - Go to https://authentik-server.railway.app
   - Initial setup: create admin account

2. **Import blueprint**:
   - Navigate to: System → Blueprints → Import
   - Upload `authentik-proxy/config/proxy-provider.yaml`

3. **Configure application**:
   - Create application: "Kublai Control UI"
   - Link to: "Kublai Proxy Provider"
   - Set access policy (e.g., "Authenticated users")

### Task 6.5: Update Caddy Forward Auth

**File**: `authentik-proxy/Caddyfile` (verify configuration)

The Caddyfile is already configured with:
- `/setup/api/signal-link` bypass with token auth
- `/outpost.goauthentik.io/*` routed to Authentik
- `/ws/*` WebSocket bypass
- Forward auth for all other routes

**Verify environment variables**:
```bash
# Set in authentik-proxy service
railway variables set AUTHENTIK_HOST="unique-manifestation.railway.internal:9000"
railway variables set MOLTBOT_HOST="moltbot-railway-template.railway.internal:8080"
```

**Exit Criteria**:
- [ ] Authentik server deployed and accessible
- [ ] Authentik worker running
- [ ] Caddy proxy deployed with forward auth
- [ ] Proxy provider blueprint imported
- [ ] Unauthenticated requests redirect to Authentik login
- [ ] Authenticated requests pass through to moltbot

---

## Phase 7: Monitoring & Health Checks

**Duration**: 2-3 hours

**Goal**: Implement comprehensive monitoring and health checks.

### Task 7.1: Railway Health Checks

Railway automatically polls the health endpoint.

**Verify health endpoint** (should already exist):

```javascript
// moltbot-railway-template/routes/health.js
router.get('/health', async (req, res) => {
  const checks = {
    uptime: process.uptime(),
    timestamp: Date.now(),
    services: {},
    dependencies: {}
  };

  // Check Node.js service
  checks.services.nodejs = 'running';

  // Check Python bridge
  try {
    await pythonBridge.run({ script: 'openclaw.health_check' });
    checks.services.openclaw = 'running';
  } catch (error) {
    checks.services.openclaw = 'error';
  }

  // Check Neo4j
  try {
    const neo4j = await checkNeo4j();
    checks.dependencies.neo4j = neo4j;
  } catch (error) {
    checks.dependencies.neo4j = { error: error.message };
  }

  // Check disk space (from Task 0.3)
  try {
    const disk = await pythonBridge.run({ script: 'openclaw.disk_check' });
    checks.dependencies.disk = disk;
  } catch (error) {
    checks.dependencies.disk = { error: error.message };
  }

  const healthy = Object.values(checks.services).every(s => s === 'running') &&
                  checks.dependencies.neo4j?.connected &&
                  checks.dependencies.disk?.healthy;

  res.status(healthy ? 200 : 503).json(checks);
});
```

### Task 7.2: Implement Structured Logging

**File**: `moltbot-railway-template/middleware/logger.js` (create)

```javascript
const pino = require('pino');

const logger = pino({
  level: process.env.LOG_LEVEL || 'info',
  formatters: {
    level: (label) => {
      return { level: label };
    },
  },
  timestamp: pino.stdTimeFunctions.isoTime,
});

module.exports = async (req, res, next) => {
  req.log = logger.child({
    requestId: req.headers['x-request-id'] || generateId(),
    path: req.path,
    method: req.method,
  });

  res.on('finish', () => {
    req.log.info({
      statusCode: res.statusCode,
      responseTime: Date.now() - req.startTime,
    }, 'request completed');
  });

  next();
};
```

### Task 7.3: Set Up Error Tracking

Consider using:
- **Sentry** for error tracking
- **Railway logs** for basic debugging
- **Custom webhook** for critical errors

**Exit Criteria**:
- [ ] Health check returns detailed status
- [ ] Disk space monitoring enabled
- [ ] Structured logging implemented
- [ ] Errors logged with stack traces
- [ ] Railway dashboard shows logs

---

## Phase 8: Validation & Testing

**Duration**: 2-3 hours

**Goal**: Comprehensive testing of deployed system.

### Task 8.1: End-to-End Tests

**File**: `tests/integration/test_deployment.py` (create)

```python
import pytest
import httpx
import os

from typing import Dict

RAILWAY_URL = os.getenv("RAILWAY_URL", "https://your-app.railway.app")


class TestDeployment:
    """Test Railway deployment."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Health check returns 200."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{RAILWAY_URL}/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_memory_health(self):
        """Neo4j memory is accessible."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{RAILWAY_URL}/health/memory")

        assert response.status_code == 200
        data = response.json()
        assert data["neo4j"]["connected"] is True

    @pytest.mark.asyncio
    async def test_authentik_redirect(self):
        """Unauthenticated requests redirect to Authentik."""
        async with httpx.AsyncClient(follow_redirects=False) as client:
            response = await client.get(f"{RAILWAY_URL}/")

        # Should redirect to Authentik login
        assert response.status_code in (302, 307)
        assert "authentik" in response.headers.get("location", "").lower()

    @pytest.mark.asyncio
    async def test_signal_link_auth_required(self):
        """Signal link endpoint requires X-Signal-Token."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{RAILWAY_URL}/setup/api/signal-link",
                json={"phoneNumber": "+1234567890"}
            )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_signal_link_with_token(self):
        """Signal link succeeds with valid token."""
        token = os.getenv("SIGNAL_LINK_TOKEN")

        if not token:
            pytest.skip("SIGNAL_LINK_TOKEN not set")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{RAILWAY_URL}/setup/api/signal-link",
                json={"phoneNumber": "+1234567890"},
                headers={"X-Signal-Token": token}
            )

        # Should not be 401 (may be 200, 202, or error from signal-cli)
        assert response.status_code != 401


def run_tests():
    """Run integration tests."""
    pytest.main([__file__, "-v"])


if __name__ == "__main__":
    run_tests()
```

### Task 8.2: Load Testing

**File**: `tests/performance/test_load.py` (create)

```python
import asyncio
import httpx
import statistics
import time
from typing import List


async def single_request(client: httpx.AsyncClient, url: str) -> float:
    """Make single request and return latency."""
    start = time.time()
    response = await client.get(url)
    end = time.time()

    response.raise_for_status()
    return end - start


async def load_test(url: str, concurrent: int = 10, total: int = 100):
    """Run load test."""
    latencies: List[float] = []

    async with httpx.AsyncClient() as client:
        for i in range(0, total, concurrent):
            batch_size = min(concurrent, total - i)
            tasks = [single_request(client, url) for _ in range(batch_size)]
            batch_latencies = await asyncio.gather(*tasks)
            latencies.extend(batch_latencies)

    print(f"Load test results for {url}:")
    print(f"  Requests: {len(latencies)}")
    print(f"  Avg latency: {statistics.mean(latencies)*1000:.2f}ms")
    print(f"  Min latency: {min(latencies)*1000:.2f}ms")
    print(f"  Max latency: {max(latencies)*1000:.2f}ms")
    print(f"  Median: {statistics.median(latencies)*1000:.2f}ms")


if __name__ == "__main__":
    import sys

    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080/health"
    asyncio.run(load_test(url))
```

### Task 8.3: Security Validation

**File**: `tests/security/test_security.py` (create)

```python
import pytest
import httpx
import os


class TestSecurity:
    """Security validation tests."""

    @pytest.mark.asyncio
    async def test_command_injection_prevented(self):
        """Signal CLI commands are properly escaped."""
        malicious_input = "+1234567890; rm -rf /"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{os.getenv('RAILWAY_URL')}/setup/api/signal-link",
                json={"phoneNumber": malicious_input},
                headers={"X-Signal-Token": os.getenv("SIGNAL_LINK_TOKEN")}
            )

        # Should reject malformed input
        assert response.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_path_traversal_prevented(self):
        """Path traversal attacks are blocked."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{os.getenv('RAILWAY_URL')}/api/files?path=../../../etc/passwd"
            )

        assert response.status_code in (400, 403, 404)

    @pytest.mark.asyncio
    async def test_pii_redacted_in_logs(self):
        """PII is redacted from error responses."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{os.getenv('RAILWAY_URL')}/api/users",
                json={"email": "test@example.com", "phone": "+1234567890"}
            )

        # If error, should not contain raw PII
        if response.status_code >= 400:
            body = response.text
            assert "+1234567890" not in body
            assert "test@example.com" not in body
```

**Exit Criteria**:
- [ ] All health checks pass
- [ ] Authentik redirects work correctly
- [ ] Signal endpoint requires token
- [ ] Load test completes without errors
- [ ] Security tests pass
- [ ] No sensitive data in logs

---

## Phase 9: Performance Optimization

**Duration**: 2-3 hours

**Goal**: Optimize for Railway container constraints.

### Task 9.1: Optimize Docker Image Size

```dockerfile
# Use alpine-based images
FROM node:20-alpine AS runtime

# Multi-stage build to exclude build artifacts
# ... (see Phase 4 for example)

# Clean up package manager caches
RUN npm cache clean --force
```

### Task 9.2: Optimize Neo4j Queries

**File**: `openclaw_memory.py` (add query optimization)

```python
# Use query parameters to prevent query plan cache misses
def get_agent_tasks(self, agent_id: str) -> List[Dict]:
    query = """
    MATCH (a:Agent {id: $agent_id})-[:ASSIGNED]->(t:Task)
    WHERE t.status <> 'completed'
    RETURN t
    ORDER BY t.priority DESC
    LIMIT 100
    """
    with self.driver.session() as session:
        result = session.run(query, agent_id=agent_id)
        return [record["t"] for record in result]
```

### Task 9.3: Implement Response Caching

```javascript
// moltbot-railway-template/middleware/cache.js
const NodeCache = require('node-cache');
const cache = new NodeCache({ stdTTL: 60, checkperiod: 120 });

module.exports = (duration = 60) => {
  return (req, res, next) => {
    const key = req.originalUrl;
    const cached = cache.get(key);

    if (cached) {
      return res.json(cached);
    }

    res.sendResponse = res.json;
    res.json = (body) => {
      cache.set(key, body, duration);
      res.sendResponse(body);
    };

    next();
  };
};
```

**Exit Criteria**:
- [ ] Docker image < 500MB
- [ ] Neo4j queries use parameters
- [ ] Response caching enabled for GET endpoints
- [ ] Health check responds < 500ms p95

---

## Rollback Procedures

### Immediate Rollback

```bash
# Railway automatically keeps previous deployments
railway rollback --service moltbot-railway-template
```

### Database Rollback

```bash
# Rollback migrations
python scripts/run_migrations.py --target-version 1
```

### Environment Variable Rollback

Use Railway dashboard to revert to previous variable set.

---

## Troubleshooting

### Issue: Health Check Fails

**Symptoms**: Railway marks service unhealthy

**Debug**:
```bash
# Check logs
railway logs --service moltbot-railway-template --lines 100

# Check health endpoint locally
curl http://localhost:8080/health
```

**Common causes**:
- Neo4j connection failed (check credentials)
- Disk full (check disk usage)
- Python bridge timeout (increase timeout)

### Issue: Neo4j Connection Timeout

**Symptoms**: "Failed to establish connection" in logs

**Debug**:
```bash
# Test Neo4j connectivity from Railway
railway shell --service moltbot-railway-template
telnet your-instance.databases.neo4j.io 7687
```

**Solutions**:
- Verify NEO4J_URI is correct (neo4j+s:// for SSL)
- Check AuraDB console for status
- Verify IP whitelist (if applicable)

### Issue: Authentik Loop

**Symptoms**: Infinite redirect between app and Authentik

**Debug**:
```bash
# Check Caddy logs for forward auth errors
railway logs --service authentik-proxy
```

**Solutions**:
- Verify AUTHENTIK_HOST is correct
- Check outpost configuration in Authentik
- Ensure proxy provider skip_path_regex includes `/ws/*` and `/setup/api/signal-link`

---

## Post-Deployment Checklist

- [ ] Phase 0: Security fixes applied
- [ ] Phase 1: Neo4j AuraDB configured, migrations applied
- [ ] Phase 2: OperationalMemory connects to Neo4j
- [ ] Phase 3: Kurultai v0.1 polling engine running
- [ ] Phase 4: Unified Docker container built
- [ ] Phase 5: Railway deployment healthy
- [ ] Phase 6: Authentik SSO working
- [ ] Phase 7: Monitoring configured
- [ ] Phase 8: All tests passing
- [ ] Phase 9: Performance optimized
- [ ] Rollback procedures documented
- [ ] Team trained on troubleshooting

---

**Document Status**: v3.0 — Post-codebase-validation
**Last Updated**: 2026-02-06
**Next Review**: After Phase 5 completion
