# TaskExecutor Quick Reference

## Installation

No installation needed - files are in `tools/` directory:
- `tools/task_executor.py` - Core execution engine
- `tools/task_executor_integration.py` - High-level integration

## One-Line Start

```python
from tools.task_executor_integration import TaskExecutionPipeline
from openclaw_memory import OperationalMemory

memory = OperationalMemory()
TaskExecutionPipeline(memory).start()  # Tasks now auto-execute
```

## Common Tasks

### Start Auto-Execution
```python
pipeline = TaskExecutionPipeline(memory)
pipeline.start()
```

### Stop Auto-Execution
```python
pipeline.stop()
```

### Execute Specific Task
```python
attempt_id = pipeline.manually_execute_task("task-123", agent="temujin")
```

### Check Status
```python
# Pipeline status
pipeline.get_status()

# Specific execution
pipeline.executor.get_execution_status(attempt_id)

# All active
pipeline.executor.get_active_executions()
```

### Cancel Task
```python
pipeline.cancel_task(attempt_id)
```

## Agent Mapping

| Task Contains | Agent | Example |
|--------------|-------|---------|
| research, investigate | mongke | "Research Python async" |
| analyze, audit | jochi | "Analyze performance" |
| write, document | chagatai | "Write API docs" |
| build, develop, code, fix | temujin | "Fix login bug" |
| ops, deploy, monitor | ogedei | "Deploy to prod" |
| orchestrate, coordinate | kublai | "Review PRs" |

## Configuration

```python
pipeline = TaskExecutionPipeline(
    memory=memory,
    max_retries=5,                    # Retry failed tasks
    poll_interval=30,                 # Check for new tasks every 30s
    agent_mapping={                   # Custom mappings
        'security_audit': 'jochi',
        'frontend': 'temujin',
    }
)
```

## Callbacks

```python
def on_complete(task_id, summary):
    print(f"✅ {task_id}: {summary}")

def on_fail(task_id, error, message):
    print(f"❌ {task_id}: {error} - {message}")

pipeline = TaskExecutionPipeline(
    memory=memory,
    on_task_complete=on_complete,
    on_task_fail=on_fail
)
```

## Environment Variables

```bash
export TASK_EXECUTOR_MAX_RETRIES=3
export TASK_EXECUTOR_RETRY_DELAY_SECONDS=30
export TASK_EXECUTOR_POLL_INTERVAL=30
```

## Context Manager (Auto-cleanup)

```python
with TaskExecutionPipeline(memory) as pipeline:
    # Tasks auto-execute
    time.sleep(3600)  # Run for 1 hour
# Auto-stopped on exit
```

## Troubleshooting

### Tasks Not Executing
```python
# Check if polling
print(pipeline.notion.is_polling())
print(pipeline.executor.is_running())

# Check for pending tasks
cypher-shell "MATCH (t:Task {status: 'pending'}) RETURN count(t)"
```

### Wrong Agent Selected
```python
# Check mapping
task = {'type': 'my_task', 'description': '...'}
print(pipeline.executor.map_task_to_agent(task))
```

### Session Spawn Failed
```bash
# Check openclaw CLI
openclaw sessions_spawn --help

# Verify agent exists
openclaw agents_list
```

## Neo4j Queries

```cypher
-- Active executions
MATCH (t:Task)-[:HAS_EXECUTION]->(s:SessionExecution)
WHERE s.status = 'active'
RETURN t.id, s.agent, s.created_at;

-- Failed tasks with retries
MATCH (t:Task)
WHERE t.status = 'failed' AND t.retry_count > 0
RETURN t.id, t.retry_count, t.error_message;

-- Recent completions
MATCH (t:Task)
WHERE t.status = 'completed'
  AND t.completed_at > datetime() - duration('PT1H')
RETURN t.id, t.claimed_by, t.completed_at
ORDER BY t.completed_at DESC;
```
