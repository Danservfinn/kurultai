# Task Executor Design Document

## Problem Statement

Notion tasks are created in Neo4j but never actually get executed by agents. The `NotionIntegration` class has `_on_new_task_callback` defined but never connected to an execution system.

## Solution Overview

The **TaskExecutor** class bridges the gap between Notion task creation and actual agent execution by:

1. **Listening** for new tasks via NotionIntegration callbacks
2. **Mapping** task types to appropriate agents (research→Möngke, build→Temüjin, etc.)
3. **Spawning** OpenClaw sessions for task execution
4. **Tracking** execution status with retry logic
5. **Syncing** completion status back to Notion/Neo4j

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Notion Board  │────▶│ NotionIntegration│────▶│   TaskExecutor  │
│  (User creates  │     │  (polls + syncs) │     │ (maps + spawns) │
│     tasks)      │◄────│                  │◄────│                 │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                              ┌───────────────────────────┼───────────┐
                              │                           │           │
                              ▼                           ▼           ▼
                    ┌─────────────────┐         ┌────────────────┐  ┌──────────────┐
                    │   Neo4j Task    │         │ OpenClaw Agent │  │   Notion     │
                    │    Storage      │         │  (execution)   │  │  (status)    │
                    └─────────────────┘         └────────────────┘  └──────────────┘
```

## Core Components

### 1. TaskExecutor (`tools/task_executor.py`)

The main execution engine with the following key methods:

#### Task-to-Agent Mapping
```python
def map_task_to_agent(self, task: Dict[str, Any]) -> str:
    """Map task to appropriate agent based on type/content."""
    # Priority order:
    # 1. Explicit assignment in task
    # 2. Required agents list
    # 3. Keyword matching on task type/description
    # 4. Pattern matching (code, research, writing)
    # 5. Default agent (main)
```

**Default Mappings:**
| Pattern | Agent | Use Case |
|---------|-------|----------|
| research, investigate | mongke | Research tasks |
| analyze, audit | jochi | Analysis tasks |
| write, document, compose | chagatai | Writing tasks |
| build, develop, code, fix | temujin | Development tasks |
| ops, deploy, monitor | ogedei | Operations tasks |
| orchestrate, coordinate | kublai | Coordination tasks |

#### Session Spawning
```python
def _spawn_agent_session(self, task, agent, attempt_id) -> Optional[str]:
    """Spawn OpenClaw session for task execution."""
    # 1. Build task prompt with context
    # 2. Call `openclaw sessions_spawn --agent <agent>`
    # 3. Track spawned session
    # 4. Return session ID for monitoring
```

#### Status Tracking
- PENDING → ASSIGNED → IN_PROGRESS → COMPLETED/FAILED
- Retry logic with exponential backoff
- Error classification and routing
- Checkpoint support for interrupted tasks

### 2. TaskExecutionPipeline (`tools/task_executor_integration.py`)

High-level integration providing:

```python
class TaskExecutionPipeline:
    """Unified pipeline: Notion polling + agent execution."""
    
    def start(self):
        # 1. Start Notion polling
        # 2. Start TaskExecutor
        # 3. Wire callbacks
        # 4. Tasks now auto-execute
```

## Integration Points

### 1. NotionIntegration Callback

The TaskExecutor registers itself with NotionIntegration:

```python
# In TaskExecutor.start():
if self.notion_integration:
    self.notion_integration._on_new_task_callback = self._handle_new_notion_task
```

When a new Notion task is detected:
1. NotionIntegration creates Neo4j task
2. Callback fires with NotionTask object
3. TaskExecutor spawns appropriate agent
4. Agent executes task
5. Status synced back to Notion

### 2. Neo4j Schema

New node types for execution tracking:

```cypher
// Execution attempts
CREATE (s:SessionExecution {
    id: "attempt-id",
    session_id: "openclaw-session-id",
    task_id: "task-id",
    agent: "temujin",
    status: "active",
    created_at: datetime()
})

// Task-produced artifacts
CREATE (a:Artifact {
    id: "artifact-id",
    type: "file",
    path: "/path/to/output",
    description: "Generated code"
})
CREATE (t:Task)-[:PRODUCED]->(a)
```

### 3. Agent Session Spawning

Uses OpenClaw CLI for session management:

```bash
# Spawn command
openclaw sessions_spawn \
    --agent temujin \
    --label "task-abc123" \
    --context '{"task_id": "...", "description": "..."}' \
    --prompt "Execute this task: ..."

# Returns: session-id for tracking
```

## Error Handling

### Retry Logic
```python
RETRYABLE_ERRORS = ['timeout_error', 'connection_error', 'api_error']
NON_RETRYABLE_ERRORS = ['syntax_error', 'type_error', 'permission_error']

# Exponential backoff: delay * (2 ^ retry_count)
# Max retries: 3 (configurable)
```

### Error Routing
Failed tasks route to specialized agents:
- Code errors → temujin
- API/connection errors → ogedei
- Research gaps → mongke
- Writing issues → chagatai

## Usage Examples

### Basic Usage
```python
from openclaw_memory import OperationalMemory
from tools.task_executor_integration import TaskExecutionPipeline

memory = OperationalMemory(...)

# Simple setup - auto-executes Notion tasks
pipeline = TaskExecutionPipeline(memory)
pipeline.start()

# Leave running - all Notion tasks auto-execute
```

### Custom Agent Mapping
```python
pipeline = TaskExecutionPipeline(
    memory=memory,
    agent_mapping={
        'security_audit': 'jochi',
        'performance_opt': 'jochi',
        'frontend': 'temujin',
        'backend': 'temujin',
    },
    max_retries=5
)
```

### Manual Task Execution
```python
# Execute specific task with specific agent
attempt_id = pipeline.manually_execute_task("task-123", agent="mongke")

# Check status
status = pipeline.executor.get_execution_status(attempt_id)

# Cancel if needed
pipeline.cancel_task(attempt_id)
```

### With Callbacks
```python
def on_complete(task_id, summary):
    print(f"✅ Task {task_id} complete: {summary}")

def on_fail(task_id, error_type, message):
    print(f"❌ Task {task_id} failed: {error_type} - {message}")

pipeline = TaskExecutionPipeline(
    memory=memory,
    on_task_complete=on_complete,
    on_task_fail=on_fail
)
```

## Configuration

### Environment Variables
```bash
# Retry configuration
TASK_EXECUTOR_MAX_RETRIES=3
TASK_EXECUTOR_RETRY_DELAY_SECONDS=30

# Polling intervals
TASK_EXECUTOR_POLL_INTERVAL=30
NOTION_POLL_INTERVAL_SECONDS=60

# Session spawning
OPENCLAW_SESSIONS_SPAWN_CMD="openclaw sessions_spawn"
```

### Programmatic Configuration
```python
from tools.task_executor import TaskExecutorConfig

config = TaskExecutorConfig(
    max_retries=5,
    retry_delay_seconds=60,
    poll_interval_seconds=30,
    agent_mapping={...},
    spawn_timeout_seconds=300,
    claim_timeout_minutes=10,
    auto_assign=True,
    track_execution=True
)

executor = TaskExecutor(memory, notion_integration, config)
```

## Monitoring

### Active Executions
```python
# Get currently running tasks
active = pipeline.executor.get_active_executions()
for exec in active:
    print(f"{exec['task_id']}: {exec['agent']} - {exec['status']}")
```

### Statistics
```python
stats = pipeline.executor.get_stats()
print(f"Active: {stats['active_executions']}")
print(f"Sessions: {stats['spawned_sessions']}")
```

### Pipeline Status
```python
status = pipeline.get_status()
print(json.dumps(status, indent=2))
```

## Task Prompt Format

Agents receive structured prompts:

```
TASK ID: task-abc123
ATTEMPT ID: attempt-xyz789
TYPE: build_task
PRIORITY: high

DESCRIPTION:
Implement user authentication API

INSTRUCTIONS:
1. Read the task description carefully
2. Execute the task to completion
3. Report your results using the appropriate format
4. Update task status when complete

NOTION REFERENCE: https://notion.so/...

ADDITIONAL CONTEXT:
{
  "repository": "backend-api",
  "framework": "FastAPI"
}

When you complete the task, report status with:
- TASK_COMPLETE: <summary>
- Or if failed: TASK_FAILED: <reason>

Begin execution now.
```

## Future Enhancements

1. **Agent Collaboration**: Multi-agent task decomposition
2. **Workflow Chains**: Sequential/parallel task dependencies
3. **Resource Limits**: Token budgets per execution
4. **Approval Gates**: Human-in-the-loop for sensitive operations
5. **Performance Metrics**: Agent success rate tracking

## Testing

### Unit Tests
```python
def test_task_to_agent_mapping():
    executor = TaskExecutor(memory)
    
    # Code task → temujin
    task = {'type': 'build', 'description': 'Fix login bug'}
    assert executor.map_task_to_agent(task) == 'temujin'
    
    # Research task → mongke
    task = {'type': 'research', 'description': 'Analyze patterns'}
    assert executor.map_task_to_agent(task) == 'mongke'
```

### Integration Tests
```python
def test_full_pipeline():
    with TaskExecutionPipeline(memory) as pipeline:
        # Create test task
        task_id = memory.create_task(
            type='test_task',
            description='Test execution'
        )
        
        # Execute
        attempt_id = pipeline.manually_execute_task(task_id)
        
        # Wait for completion
        time.sleep(5)
        
        # Verify status
        status = pipeline.executor.get_execution_status(attempt_id)
        assert status['status'] in ['completed', 'failed']
```

## Migration Guide

### Existing Code
```python
# Before: Tasks created but not executed
notion = NotionIntegration(memory)
notion.start_polling()
# Tasks sit in Neo4j forever
```

### After Integration
```python
# After: Tasks auto-execute
from tools.task_executor_integration import TaskExecutionPipeline

pipeline = TaskExecutionPipeline(memory)
pipeline.start()
# Tasks are picked up and executed automatically
```

### Minimal Change Option
```python
# If you already have NotionIntegration
from tools.task_executor import integrate_with_notion

executor = integrate_with_notion(notion_integration, memory)
# Executor registers callbacks and starts polling
```
