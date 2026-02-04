# MEM-001: Memory Exhaustion

**Severity**: Critical
**Affected Component**: Agent Processes / System Memory
**Recovery Time**: 1-2 minutes

## Symptoms
- System memory usage > 90%
- Processes being killed by OOM killer
- "Out of memory" errors in logs
- Slow response times due to swapping
- Container restarts with OOMKilled=true

## Diagnosis
```bash
# 1. Check system memory
free -h
vmstat -s

# 2. Check per-process memory usage
ps aux --sort=-%mem | head -20
top -b -n 1 | head -20

# 3. Check Docker container memory
docker stats --no-stream | sort -k 4 -h

# 4. Check for OOM kills
dmesg | grep -i "out of memory\|killed process"
journalctl -k | grep -i oom

# 5. Check swap usage
swapon -s
cat /proc/swaps

# 6. Check Python process memory (if applicable)
python -c "
import psutil
p = psutil.Process()
print(f'Memory: {p.memory_info().rss / 1024 / 1024:.1f} MB')
"
```

## Recovery Steps
### Step 1: Assess Memory State
```python
import psutil
import gc

memory = psutil.virtual_memory()
print(f"Memory: {memory.percent}% used")
print(f"Available: {memory.available / 1024**3:.2f} GB")

if memory.percent > 90:
    print("CRITICAL: Memory exhausted")
elif memory.percent > 80:
    print("WARNING: Memory high")
```

### Step 2: Clear Application Caches
```python
# Clear in-memory caches
if hasattr(memory, '_cache'):
    memory._cache.clear()

# Clear LRU caches
from functools import lru_cache
# Note: lru_cache doesn't have a clear method in older Python versions
# Use cache_clear() on specific functions if available

# Clear session caches
if hasattr(session, 'cache'):
    session.cache.clear()

print("Caches cleared")
```

### Step 3: Trigger Garbage Collection
```python
import gc

# Force full garbage collection
collected = gc.collect()
print(f"GC collected {collected} objects")

# Get memory before/after
process = psutil.Process()
before = process.memory_info().rss / (1024**2)
gc.collect()
after = process.memory_info().rss / (1024**2)
print(f"Memory freed: {before - after:.1f} MB")
```

### Step 4: Restart Bloated Processes
```bash
# Identify bloated containers
docker stats --no-stream | awk '$4 ~ /[0-9]{3}/ {print $1, $4}'

# Restart specific container
docker restart <container_name>

# Or use Docker healthcheck to auto-restart
docker update --restart=unless-stopped <container_name>
```

### Step 5: Verify Memory Recovery
```bash
# Check memory after recovery
free -h

# Verify process is healthy
docker ps | grep <container_name>

# Check logs for successful restart
docker logs <container_name> --tail 20
```

## Rollback Options
1. **Process Restart**: Restart individual bloated process
2. **Service Degradation**: Disable non-essential features
3. **Full Restart**: Restart all agent services

## Prevention Measures

```yaml
# Docker memory limits
docker_compose_config:
  services:
    agent:
      deploy:
        resources:
          limits:
            memory: 2G
          reservations:
            memory: 512M
      memswap_limit: 2G
```

```python
# Memory monitoring configuration
MEMORY_CONFIG = {
    'warning_threshold': 80,    # percent
    'critical_threshold': 90,   # percent
    'cache_max_size': 1000,     # items
    'enable_gc_monitoring': True,
    'gc_interval_seconds': 60,
    'max_cache_memory_mb': 100,
}

# Implement LRU cache with size limit
from functools import lru_cache

@lru_cache(maxsize=1000)
def expensive_function(arg):
    # Auto-evicts oldest entries when limit reached
    pass
```

```bash
# Proactive memory monitoring script
#!/bin/bash
THRESHOLD=85

while true; do
    USAGE=$(free | awk '/Mem/{printf("%.0f"), $3/$2*100}')

    if [ "$USAGE" -ge "$THRESHOLD" ]; then
        echo "Memory at ${USAGE}%, triggering cleanup"
        # Send alert
        curl -X POST https://alerts.example.com/memory -d "{\"usage\": $USAGE}"
        # Clear caches via API
        curl -X POST http://localhost:18789/admin/clear-cache
    fi

    sleep 60
done
```
