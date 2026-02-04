# NEO-001: Neo4j Connection Loss

**Severity**: Critical
**Affected Component**: Neo4j Database / OperationalMemory
**Recovery Time**: 5-10 minutes

## Symptoms

- Agents report "Failed to connect to Neo4j" errors
- Memory operations timeout or fail
- Health check endpoint returns `neo4j: false`
- Tasks cannot be created or updated
- Agent state cannot be persisted

## Diagnosis

```bash
# 1. Check Neo4j container status
docker ps | grep neo4j

# 2. Check Neo4j logs
docker logs neo4j --tail 100

# 3. Test Neo4j connectivity
curl -u neo4j:password http://localhost:7474/db/data/

# 4. Check network connectivity
nc -zv localhost 7474
nc -zv localhost 7687

# 5. Verify Neo4j process inside container
docker exec neo4j ps aux | grep neo4j

# 6. Check disk space
docker exec neo4j df -h

# 7. Check memory usage
docker stats neo4j --no-stream
```

## Recovery Steps

### Step 1: Assess Current State

```bash
# Check if Neo4j container is running
docker ps | grep neo4j

# If running, check logs for errors
docker logs neo4j --tail 100
```

### Step 2: Attempt Graceful Recovery

```bash
# Restart Neo4j service inside container
docker exec neo4j neo4j restart

# Wait for Neo4j to become ready (up to 60 seconds)
for i in {1..30}; do
    if curl -s -u neo4j:password http://localhost:7474/db/data/ > /dev/null 2>&1; then
        echo "Neo4j is responding"
        break
    fi
    sleep 2
done
```

### Step 3: Container-Level Recovery

```bash
# Stop container if running
docker stop neo4j

# Start container
docker start neo4j

# Verify startup
docker logs neo4j -f | grep "Started"
```

### Step 4: Recovery from Backup (if needed)

```bash
# List available backups
ls -lt /data/backups/neo4j/

# Stop container
docker stop neo4j

# Restore from latest backup
docker run --rm \
    -v /data/backups/neo4j:/backups \
    -v /data/neo4j/data:/data \
    neo4j:latest neo4j-admin restore \
    --from=/backups/latest.backup \
    --database=neo4j --force

# Start container
docker start neo4j
```

## Rollback Options

1. **Immediate Rollback**: Restart OpenClaw agents in fallback mode (file-based storage)
2. **Partial Rollback**: Use read-only Neo4j replica if available
3. **Full Rollback**: Restore from latest backup and replay transactions from logs

## Prevention Measures

```yaml
# docker-compose.yml - Neo4j resilience configuration
services:
  neo4j:
    image: neo4j:5.x-enterprise
    restart: unless-stopped
    environment:
      - NEO4J_dbms_memory_heap_initial__size=2G
      - NEO4J_dbms_memory_heap_max__size=4G
      - NEO4J_dbms_memory_pagecache_size=2G
    healthcheck:
      test: ["CMD", "cypher-shell", "-u", "neo4j", "-p", "${NEO4J_PASSWORD}", "RETURN 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    deploy:
      resources:
        limits:
          memory: 8G
        reservations:
          memory: 4G
```
