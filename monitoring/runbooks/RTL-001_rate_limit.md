# RTL-001: Rate Limit Exceeded

**Severity**: Low
**Affected Component**: External API Calls / Agent Operations
**Recovery Time**: 30 seconds - 5 minutes

## Symptoms
- "Rate limit exceeded" errors in logs
- HTTP 429 responses from APIs
- Operations failing with retry-after headers
- Gradual degradation of service
- Queue processing slowdown

## Diagnosis
```bash
# 1. Check rate limit status in Neo4j
cypher-shell -u neo4j -p password "
  MATCH (rl:RateLimit)
  RETURN rl.agent_id, rl.operation_type, rl.count, rl.limit, rl.window_start
  ORDER BY rl.count DESC
  LIMIT 10
"

# 2. Check application logs for rate limit errors
grep -i "rate limit\|429\|too many requests" /var/log/openclaw/*.log

# 3. Check external API rate limit headers
curl -I https://api.example.com/endpoint | grep -i "x-rate-limit"

# 4. Monitor queue depths
redis-cli LLEN task:queue
redis-cli LLEN signal:outgoing

# 5. Check agent activity levels
cypher-shell -u neo4j -p password "
  MATCH (o:Observation)
  WHERE o.timestamp > datetime() - duration('PT1H')
  RETURN o.agent_id, count(*) as operations
  ORDER BY operations DESC
"
```

## Recovery Steps
### Step 1: Diagnose Rate Limit Status
```bash
# Get current rate limit utilization
cypher-shell -u neo4j -p password "
  MATCH (rl:RateLimit)
  WHERE rl.count >= rl.limit * 0.8
  RETURN rl.agent_id, rl.operation_type,
         toFloat(rl.count) / rl.limit as utilization,
         rl.count, rl.limit
  ORDER BY utilization DESC
"
```

### Step 2: Pause Non-Critical Operations
```python
# Create flow control node
cypher = """
MATCH (a:Agent)
WHERE a.id IN $affected_agents
CREATE (fc:FlowControl {
    type: 'rate_limit_pause',
    timestamp: datetime(),
    pause_non_critical: true,
    expires_at: datetime() + duration('PT5M')
})
CREATE (a)-[:SUBJECT_TO]->(fc)
"""

# Or set Redis flag
redis-cli SET rate_limit:pause true EX 300
```

### Step 3: Apply Exponential Backoff
```python
import time

# Calculate backoff: 2^level * base_delay
backoff_level = get_current_backoff_level(agent_id)
backoff_seconds = 60 * (2 ** backoff_level)  # 60, 120, 240, 480, 960

# Set backoff expiration
cypher = """
MATCH (a:Agent {id: $agent_id})
SET a.backoff_level = $level,
    a.backoff_until = datetime() + duration({seconds: $seconds}),
    a.last_backoff = datetime()
"""

print(f"Applied level {backoff_level} backoff ({backoff_seconds}s)")
```

### Step 4: Redistribute Load
```python
# Find alternative agents
cypher = """
MATCH (a:Agent)
WHERE a.status = 'active'
  AND NOT EXISTS {
    MATCH (a)-[:SUBJECT_TO]->(fc:FlowControl)
    WHERE fc.expires_at > datetime()
  }
RETURN a.id, a.capacity
ORDER BY a.capacity DESC
LIMIT 5
"""

# Update routing preferences
cypher = """
MATCH (a:Agent {id: $agent_id})
SET a.preferred_operations = coalesce(a.preferred_operations, []) + $operation
"""
```

### Step 5: Clear Expired Windows
```python
# Remove expired rate limit entries
cypher = """
MATCH (rl:RateLimit)
WHERE rl.window_start + rl.window_duration < datetime()
DELETE rl
"""
```

### Step 6: Gradual Resume
```python
# Stagger resume by 30 seconds per agent
for i, agent_id in enumerate(affected_agents):
    delay = i * 30
    cypher = """
    MATCH (a:Agent {id: $agent_id})
    SET a.resume_at = datetime() + duration({seconds: $delay}),
        a.backoff_level = 0
    """
    print(f"Agent {agent_id} will resume in {delay}s")
```

## Rollback Options
1. **Agent-level Rollback**: Clear individual agent rate limits
2. **Operation-level Rollback**: Reset rate limits for specific operations
3. **Global Rollback**: Clear all rate limits (use with caution)

## Prevention Measures

```python
# Rate limit prevention configuration
RATE_LIMIT_CONFIG = {
    'warning_threshold': 0.8,    # 80% of limit
    'backoff_base_seconds': 60,
    'max_backoff_level': 5,
    'window_size_seconds': 60,
    'enable_preemptive_throttle': True,
}

# Proactive rate limiting
class RateLimitPreventer:
    def __init__(self):
        self.windows = {}  # {(agent, operation): {'count': n, 'reset_at': time}}

    def check_and_throttle(self, agent_id, operation, limit=100):
        key = (agent_id, operation)
        now = time.time()

        if key not in self.windows or now > self.windows[key]['reset_at']:
            self.windows[key] = {'count': 0, 'reset_at': now + 60}

        if self.windows[key]['count'] >= limit * 0.8:
            # Warning threshold
            send_alert(f"Rate limit warning: {agent_id}/{operation}")

        if self.windows[key]['count'] >= limit:
            return False  # Throttle

        self.windows[key]['count'] += 1
        return True
```

```yaml
# API client configuration with rate limiting
api_clients:
  external_api:
    max_requests_per_minute: 100
    max_retries: 3
    retry_backoff: exponential
    retry_multiplier: 2
    max_wait_seconds: 300
```
