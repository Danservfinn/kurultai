# TSK-001: Task Queue Overflow

**Severity**: Medium
**Affected Component**: Task Queue / Task Orchestration
**Recovery Time**: 1-3 minutes

## Symptoms
- Task queue depth exceeds threshold (>1000 pending tasks)
- New tasks take excessive time to be claimed
- Workers unable to keep up with task creation rate
- Redis/RabbitMQ memory warnings
- Tasks timing out before processing

## Diagnosis
```bash
# 1. Check queue depth
redis-cli LLEN task:queue
redis-cli LLEN task:pending

# 2. Check worker status
docker ps | grep worker
docker stats worker-* --no-stream

# 3. Check task processing rate
cypher-shell -u neo4j -p password "
  MATCH (t:Task {status: 'pending'})
  RETURN count(t) as pending
"

# 4. Check for stuck tasks
cypher-shell -u neo4j -p password "
  MATCH (t:Task {status: 'in_progress'})
  WHERE t.started_at < datetime() - duration('PT1H')
  RETURN count(t) as stuck
"

# 5. Check queue consumer lag
redis-cli PUBLISH task:queue "healthcheck"
```

## Recovery Steps
### Step 1: Assess Queue State
```bash
# Get queue statistics
PENDING=$(redis-cli LLEN task:queue)
IN_PROGRESS=$(redis-cli LLEN task:processing)
echo "Pending: $PENDING, In Progress: $IN_PROGRESS"

# Calculate overflow condition
if [ "$PENDING" -gt 1000 ]; then
    echo "Queue overflow detected"
fi
```

### Step 2: Throttle New Task Creation
```python
# Create flow control node in Neo4j
cypher = """
MERGE (fc:FlowControl {type: 'task_throttle'})
SET fc.active = true,
    fc.created_at = datetime(),
    fc.expires_at = datetime() + duration('PT10M'),
    fc.reason = 'Queue overflow recovery'
"""

# Or set flag in Redis
redis-cli SET task:throttle true EX 600
```

### Step 3: Scale Up Workers
```bash
# Get current worker count
CURRENT_WORKERS=$(docker ps -q -f name=worker | wc -l)
echo "Current workers: $CURRENT_WORKERS"

# Scale up (Docker Compose)
docker-compose up -d --scale worker=5

# Or Kubernetes
kubectl scale deployment worker --replicas=5

# Verify new workers registered
sleep 10
docker ps | grep worker
```

### Step 4: Process Backlog
```python
# Enable batch processing mode
BATCH_SIZE = 100

# Process tasks in batches until queue is under control
while True:
    queue_depth = redis_cli.llen("task:queue")
    if queue_depth < 500:
        break

    # Trigger batch processing
    trigger_batch_processing(batch_size=BATCH_SIZE)
    time.sleep(5)
```

### Step 5: Resume Normal Operations
```bash
# Clear throttle flag when queue is manageable
if [ "$(redis-cli LLEN task:queue)" -lt 500 ]; then
    redis-cli DEL task:throttle

    # Remove flow control node
    cypher-shell -u neo4j -p password "
        MATCH (fc:FlowControl {type: 'task_throttle'})
        DELETE fc
    "
fi
```

## Rollback Options
1. **Queue Purge**: Remove low-priority tasks from queue
2. **Priority Re-routing**: Redirect critical tasks to fast lane
3. **Worker Isolation**: Dedicate workers to backlog processing

## Prevention Measures

```yaml
# Queue monitoring configuration
queue_monitoring:
  thresholds:
    warning: 500
    critical: 1000
    emergency: 2000

  auto_scaling:
    enabled: true
    min_workers: 2
    max_workers: 10
    scale_up_threshold: 500
    scale_down_threshold: 100

  priority_queues:
    - name: critical
      weight: 10
    - name: normal
      weight: 5
    - name: low
      weight: 1
```

```python
# Task queue configuration with overflow protection
TASK_QUEUE_CONFIG = {
    'max_depth': 1000,
    'throttle_on_overflow': True,
    'throttle_duration_minutes': 10,
    'worker_scale_factor': 2,
    'batch_size': 50,
    'enable_priority': True,
}
```
