# AGT-001: Agent Unresponsive

**Severity**: High
**Affected Component**: Agent Process (Kublai, Temüjin, Jochi, Chagatai, Ögedei, Subutai)
**Recovery Time**: 2-5 minutes

## Symptoms
- Agent process not responding to health checks
- Task assignments to agent fail
- No heartbeat received from agent for > 60 seconds
- Agent container in "Exited" or "Restarting" state
- Error logs show stack traces or OOM errors

## Diagnosis
```bash
# 1. Check agent container status
docker ps -a | grep agent

# 2. Check agent logs
docker logs <agent-container> --tail 200

# 3. Check for OOM kills
docker inspect <agent-container> --format='{{.State.OOMKilled}}'
dmesg | grep -i "killed process"

# 4. Check resource usage
docker stats <agent-container> --no-stream

# 5. Check agent's last known state in Neo4j
cypher-shell -u neo4j -p password "
  MATCH (a:Agent {id: 'AGENT_ID'})
  RETURN a.status, a.last_heartbeat, a.current_task
"

# 6. Check for deadlocks or blocked threads (Java agents)
docker exec <agent-container> jstack <pid> 2>/dev/null || true
```

## Recovery Steps
### Step 1: Diagnose Agent State
```bash
# Get agent container status
AGENT_ID="kublai"  # Replace with actual agent ID
CONTAINER_NAME="openclaw-agent-${AGENT_ID}"

docker ps -a | grep $CONTAINER_NAME

# Check logs for crash reason
docker logs $CONTAINER_NAME --tail 100
```

### Step 2: Handle In-Flight Tasks
```python
# Reassign tasks from crashed agent
import subprocess

# Cypher query to reassign tasks
cypher = """
MATCH (t:Task {assigned_agent: $agent_id, status: 'in_progress'})
SET t.status = 'pending',
    t.assigned_agent = NULL,
    t.previous_agent = $agent_id,
    t.recovery_timestamp = datetime()
RETURN count(t) as reassigned
"""

# Execute via cypher-shell or OperationalMemory
```

### Step 3: Restart Agent Container
```bash
# Option A: Restart existing container
docker restart $CONTAINER_NAME

# Option B: Recreate container if restart fails
docker stop $CONTAINER_NAME
docker rm $CONTAINER_NAME

# Recreate with original configuration
docker run -d \
    --name $CONTAINER_NAME \
    --restart unless-stopped \
    -e AGENT_ID=$AGENT_ID \
    -e NEO4J_URI=$NEO4J_URI \
    -v /data/workspace:/workspace \
    openclaw/agent:latest
```

### Step 4: Verify Recovery
```bash
# Wait for agent to initialize (30 seconds)
sleep 30

# Check agent heartbeat in Neo4j
cypher-shell -u neo4j -p password "
  MATCH (a:Agent {id: '${AGENT_ID}'})
  RETURN a.status, a.last_heartbeat
"

# Verify container is healthy
docker ps | grep $CONTAINER_NAME
```

## Rollback Options
1. **Process Rollback**: Restart agent process, preserving container state
2. **Container Rollback**: Recreate container, losing ephemeral state
3. **Full Rollback**: Restore agent state from last checkpoint

## Prevention Measures

```python
# Agent monitoring configuration
AGENT_MONITORING = {
    'heartbeat_interval': 30,  # seconds
    'heartbeat_timeout': 60,   # seconds before marking unresponsive
    'memory_threshold': 85,    # percent
    'cpu_threshold': 90,       # percent
    'max_restarts': 3,         # per hour before escalation
    'health_check_endpoint': '/health',
}

# Resource limits for agent containers
DOCKER_RESOURCE_LIMITS = {
    'memory': '2g',
    'memory_swap': '2g',
    'cpu_quota': 100000,
    'restart_policy': 'unless-stopped',
}
```
