# TaskExecutor Integration Summary

## Problem

The `NotionIntegration` class in `tools/notion_integration.py` has a callback `_on_new_task_callback` that's defined but never connected to an execution system. Tasks from Notion are created in Neo4j but sit idle.

## Solution

Two new modules provide the execution bridge:

1. **`tools/task_executor.py`** - Core execution engine (~1000 lines)
2. **`tools/task_executor_integration.py`** - Integration layer (~300 lines)

## Required Changes to Existing Files

### Option 1: Minimal Change (Add 3 lines)

Add to `tools/kurultai/agent_tasks.py` in the `notion_sync` function or create a startup script:

```python
from tools.task_executor import integrate_with_notion

# After creating NotionIntegration
executor = integrate_with_notion(notion_integration, memory)
# Executor auto-registers callbacks and starts polling
```

### Option 2: Kurultai Integration (Add to heartbeat startup)

In `tools/kurultai/agent_tasks.py`, add to `notion_sync`:

```python
def notion_sync(driver) -> Dict:
    """Enhanced with auto-execution."""
    # ... existing sync code ...
    
    # NEW: Start task executor if not running
    global _task_executor
    if '_task_executor' not in globals():
        from tools.task_executor_integration import TaskExecutionPipeline
        from openclaw_memory import OperationalMemory
        
        memory = OperationalMemory(driver=driver)
        _task_executor = TaskExecutionPipeline(memory)
        _task_executor.start()
        result['task_executor_started'] = True
    
    return result
```

### Option 3: Standalone Service

Create `services/task_executor_service.py`:

```python
#!/usr/bin/env python3
"""Standalone task execution service."""

import sys
import time
sys.path.insert(0, '/data/workspace/souls/main')

from openclaw_memory import OperationalMemory
from tools.task_executor_integration import TaskExecutionPipeline

def main():
    memory = OperationalMemory()
    pipeline = TaskExecutionPipeline(memory)
    
    print("Starting Task Execution Service...")
    pipeline.start()
    
    try:
        while True:
            status = pipeline.get_status()
            active = len(status['active_executions'])
            print(f"Active executions: {active}", end='\r')
            time.sleep(10)
    except KeyboardInterrupt:
        print("\nShutting down...")
        pipeline.stop()

if __name__ == '__main__':
    main()
```

## Key Integration Points

### 1. Callback Registration

The TaskExecutor auto-registers with NotionIntegration:

```python
# In TaskExecutor.start():
if self.notion_integration:
    # Register for new tasks
    self.notion_integration._on_new_task_callback = self._handle_new_notion_task
    
    # Register for status changes (user moves cards)
    self.notion_integration._on_status_change_callback = self._handle_status_change
```

### 2. Task-to-Agent Mapping

Automatic mapping based on task content:

```python
# In TaskExecutor.map_task_to_agent()
task_type = task.get('type', '').lower()
description = task.get('description', '').lower()

# Priority order:
# 1. Explicit assignment
# 2. Keyword matching (research→mongke, build→temujin, etc.)
# 3. Pattern matching (code files, error messages)
# 4. Default agent
```

### 3. Session Spawning

Uses OpenClaw CLI:

```python
cmd = [
    'openclaw', 'sessions_spawn',
    '--agent', agent,           # e.g., 'temujin'
    '--label', f'task-{id}',    # for tracking
    '--context', json.dumps(context),
    '--prompt', task_prompt,
]
```

### 4. Status Synchronization

Bidirectional sync:

```python
# Neo4j → Notion
def _update_task_status(self, task_id, status):
    # Update Neo4j
    self.memory.update_task(task_id, status=status)
    
    # Sync to Notion
    if self.notion_integration:
        self.notion_integration.sync_neo4j_status_to_notion(task_id)
```

## Neo4j Schema Additions

The TaskExecutor creates these new node types:

```cypher
// Session execution tracking
CREATE CONSTRAINT session_execution_id IF NOT EXISTS
FOR (s:SessionExecution) REQUIRE s.id IS UNIQUE;

// Artifacts produced by tasks
CREATE CONSTRAINT artifact_id IF NOT EXISTS
FOR (a:Artifact) REQUIRE a.id IS UNIQUE;

// Indexes for performance
CREATE INDEX task_status_agent IF NOT EXISTS
FOR (t:Task) ON (t.status, t.assigned_to);

CREATE INDEX session_execution_task IF NOT EXISTS
FOR (s:SessionExecution) ON (s.task_id);
```

## Environment Configuration

Add to your environment:

```bash
# Task execution
export TASK_EXECUTOR_MAX_RETRIES=3
export TASK_EXECUTOR_RETRY_DELAY_SECONDS=30
export TASK_EXECUTOR_POLL_INTERVAL=30

# Notion (existing)
export NOTION_TOKEN="secret_..."
export NOTION_TASK_DATABASE_ID="..."
```

## Usage Examples

### Quick Start
```python
from tools.task_executor_integration import TaskExecutionPipeline
from openclaw_memory import OperationalMemory

memory = OperationalMemory()
pipeline = TaskExecutionPipeline(memory)
pipeline.start()
# Tasks now auto-execute
```

### With Custom Mapping
```python
pipeline = TaskExecutionPipeline(
    memory=memory,
    agent_mapping={
        'security': 'jochi',
        'frontend': 'temujin',
    }
)
```

### Manual Execution
```python
attempt_id = pipeline.manually_execute_task("task-123", agent="mongke")
```

## Monitoring Commands

```bash
# Check active executions
openclaw sessions_list

# View task executor stats
python3 -c "
from tools.task_executor_integration import TaskExecutionPipeline
# ... get status
"

# View Neo4j task status
cypher-shell "MATCH (t:Task) RETURN t.id, t.status, t.claimed_by LIMIT 10"
```

## Rollback Plan

If issues occur:

1. Stop the executor:
```python
pipeline.stop()
```

2. Tasks revert to manual - they'll be in Neo4j with status `pending`

3. To disable auto-execution temporarily:
```python
# In TaskExecutorConfig
auto_assign = False  # Tasks won't auto-start
```
