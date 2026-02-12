# Implementation Recommendations
## Steppe Orchestrator - Actionable Steps

**Date:** 2026-02-12  
**Status:** Ready for Implementation

---

## Quick Wins (Week 1)

### 1. Implement Agent Heartbeat
**File:** `src/orchestrator/health-service.js`

Add heartbeat to all existing agents:
```javascript
// Add to each agent constructor
setInterval(() => {
  this.sendHeartbeat();
}, 30000); // Every 30 seconds

async sendHeartbeat() {
  const session = this.driver.session();
  try {
    await session.run(`
      MERGE (a:Agent {id: $agentId})
      SET a.last_heartbeat = datetime(),
          a.status = 'healthy',
          a.current_load = $load,
          a.max_concurrent = $max
    `, {
      agentId: this.id,
      load: this.activeTasks.size,
      max: this.maxConcurrent
    });
  } finally {
    await session.close();
  }
}
```

### 2. Create Task Queue Schema
**File:** `migrations/001-task-queue.cypher`

```cypher
// Create constraints and indexes
CREATE CONSTRAINT task_id IF NOT EXISTS
FOR (t:Task) REQUIRE t.id IS UNIQUE;

CREATE CONSTRAINT agent_id IF NOT EXISTS
FOR (a:Agent) REQUIRE a.id IS UNIQUE;

CREATE INDEX task_status_priority IF NOT EXISTS
FOR (t:Task) ON (t.status, t.priority);

CREATE INDEX task_assigned IF NOT EXISTS
FOR (t:Task) ON (t.assigned_to, t.status);

CREATE INDEX agent_heartbeat IF NOT EXISTS
FOR (a:Agent) ON (a.status, a.last_heartbeat);
```

### 3. Connect Notion to Task Creation
**File:** `src/integrations/notion-task-queue.js`

Modify existing poller to create tasks:
```javascript
// In NotionIntegration.pollForTasks()
async pollForTasks() {
  const tasks = await this.fetchNotionTasks();
  
  for (const task of tasks) {
    const taskId = await this.taskQueue.enqueue({
      type: 'notion_task',
      priority: this.mapPriority(task.priority),
      payload: {
        notionId: task.id,
        title: task.title,
        assignee: task.assignee
      },
      requiredCapability: this.inferCapability(task)
    });
    
    // Update Notion
    await this.notion.pages.update({
      page_id: task.id,
      properties: {
        Status: { select: { name: 'Queued' } },
        TaskId: { rich_text: [{ text: { content: taskId } }] }
      }
    });
  }
}
```

---

## Core Implementation (Week 2-3)

### 4. EventRouter Implementation
**File:** `src/orchestrator/event-router.js`

```javascript
class EventRouter {
  constructor(neo4jDriver, logger) {
    this.driver = neo4jDriver;
    this.logger = logger;
    this.subscribers = new Map();
    this.eventBuffer = [];
    
    // Start event persistence loop
    setInterval(() => this.flushEvents(), 5000);
  }
  
  async publish(type, payload, metadata = {}) {
    const event = {
      id: randomUUID(),
      type,
      payload,
      timestamp: new Date(),
      correlationId: metadata.correlationId || randomUUID(),
      source: metadata.source || 'unknown'
    };
    
    // Buffer for batch persistence
    this.eventBuffer.push(event);
    
    // Immediate routing
    const handlers = this.subscribers.get(type) || [];
    const results = await Promise.allSettled(
      handlers.map(h => h(event))
    );
    
    // Log failures
    results.forEach((result, i) => {
      if (result.status === 'rejected') {
        this.logger.error(`Handler ${i} failed for ${type}:`, result.reason);
      }
    });
    
    return event;
  }
  
  async flushEvents() {
    if (this.eventBuffer.length === 0) return;
    
    const events = this.eventBuffer.splice(0, this.eventBuffer.length);
    const session = this.driver.session();
    
    try {
      await session.run(`
        UNWIND $events as event
        CREATE (e:Event {
          id: event.id,
          type: event.type,
          payload: event.payload,
          timestamp: datetime(event.timestamp),
          correlation_id: event.correlationId,
          source: event.source
        })
      `, { events });
    } finally {
      await session.close();
    }
  }
  
  subscribe(eventType, handler) {
    if (!this.subscribers.has(eventType)) {
      this.subscribers.set(eventType, []);
    }
    this.subscribers.get(eventType).push(handler);
  }
}
```

### 5. Unified Task Queue
**File:** `src/orchestrator/task-queue.js`

```javascript
class UnifiedTaskQueue {
  constructor(neo4jDriver, config = {}) {
    this.driver = neo4jDriver;
    this.config = {
      maxRetries: config.maxRetries || 3,
      retryDelayMs: config.retryDelayMs || 60000,
      taskTimeoutMinutes: config.taskTimeoutMinutes || 30
    };
  }
  
  async enqueue(taskSpec) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        CREATE (t:Task {
          id: randomUUID(),
          type: $type,
          priority: $priority,
          status: 'pending',
          payload: $payload,
          created_at: datetime(),
          expires_at: datetime() + duration({minutes: $timeout}),
          attempts: 0,
          max_attempts: $maxAttempts
        })
        WITH t
        OPTIONAL MATCH (a:Agent)
        WHERE a.capabilities CONTAINS $capability
          AND a.status = 'healthy'
        WITH t, collect(a.id) as agents
        SET t.potential_agents = agents
        RETURN t.id as id
      `, {
        type: taskSpec.type,
        priority: taskSpec.priority || 'P2',
        payload: JSON.stringify(taskSpec.payload),
        capability: taskSpec.requiredCapability || 'general',
        timeout: this.config.taskTimeoutMinutes,
        maxAttempts: this.config.maxRetries
      });
      
      return result.records[0].get('id');
    } finally {
      await session.close();
    }
  }
  
  async assignNext(agentId) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (t:Task {status: 'pending'})
        WHERE t.expires_at > datetime()
          AND $agentId IN t.potential_agents
        WITH t
        ORDER BY 
          CASE t.priority
            WHEN 'P0' THEN 0
            WHEN 'P1' THEN 1
            WHEN 'P2' THEN 2
            ELSE 3
          END,
          t.created_at ASC
        LIMIT 1
        MATCH (a:Agent {id: $agentId})
        WHERE a.current_load < a.max_concurrent
        SET t.status = 'assigned',
            t.assigned_to = $agentId,
            t.assigned_at = datetime(),
            a.current_load = a.current_load + 1
        RETURN t.id as taskId, t.payload as payload
      `, { agentId });
      
      if (result.records.length === 0) return null;
      
      return {
        taskId: result.records[0].get('taskId'),
        payload: JSON.parse(result.records[0].get('payload'))
      };
    } finally {
      await session.close();
    }
  }
}
```

### 6. Discord Context Integration
**File:** `src/integrations/discord-context.js`

```javascript
class DiscordContextIntegration {
  constructor(discordClient, memoryService, taskQueue) {
    this.discord = discordClient;
    this.memory = memoryService;
    this.queue = taskQueue;
    
    this.discord.on('messageCreate', (msg) => this.handleMessage(msg));
  }
  
  async handleMessage(message) {
    if (message.author.bot) return;
    
    // Record immediately
    await this.memory.recordConversation({
      channel: 'discord',
      channelId: message.channelId,
      userId: message.author.id,
      content: message.content,
      timestamp: new Date()
    });
    
    // Check if needs response
    if (this.shouldRespond(message)) {
      await this.queue.enqueue({
        type: 'discord_response',
        priority: 'P2',
        payload: {
          messageId: message.id,
          channelId: message.channelId,
          userId: message.author.id,
          content: message.content
        },
        requiredCapability: 'conversation'
      });
      
      // Acknowledge
      await message.react('👀');
    }
  }
  
  async generateResponse(task) {
    const context = await this.memory.getContext({
      channel: 'discord',
      userId: task.payload.userId,
      limit: 10
    });
    
    const response = await this.llm.generate({
      system: this.buildSystemPrompt(context),
      messages: context.history
    });
    
    const channel = await this.discord.channels.fetch(task.payload.channelId);
    await channel.send({
      content: response,
      reply: { messageReference: task.payload.messageId }
    });
    
    // Record response
    await this.memory.recordConversation({
      channel: 'discord',
      userId: task.payload.userId,
      content: task.payload.content,
      response,
      timestamp: new Date()
    });
  }
}
```

---

## Memory Service (Week 4)

### 7. Memory Schema
**File:** `migrations/002-memory-schema.cypher`

```cypher
// Conversation memory
CREATE CONSTRAINT conversation_id IF NOT EXISTS
FOR (c:Conversation) REQUIRE c.id IS UNIQUE;

CREATE INDEX conversation_user_channel IF NOT EXISTS
FOR (c:Conversation) ON (c.user_id, c.channel);

// Message nodes
CREATE INDEX message_timestamp IF NOT EXISTS
FOR (m:Message) ON (m.timestamp);

// Memory nodes for long-term storage
CREATE FULLTEXT INDEX memory_search IF NOT EXISTS
FOR (m:Memory) ON EACH [m.content, m.tags];
```

### 8. Memory Service Implementation
**File:** `src/services/memory-service.js`

```javascript
class MemoryService {
  constructor(neo4jDriver) {
    this.driver = neo4jDriver;
  }
  
  async recordConversation({ channel, userId, content, response, metadata }) {
    const session = this.driver.session();
    try {
      await session.run(`
        MERGE (u:User {id: $userId})
        ON CREATE SET u.created_at = datetime()
        
        MERGE (c:Conversation {user_id: $userId, channel: $channel})
        ON CREATE SET c.created_at = datetime()
        
        CREATE (m:Message {
          id: randomUUID(),
          content: $content,
          response: $response,
          timestamp: datetime(),
          channel: $channel,
          sentiment: $sentiment
        })
        
        CREATE (c)-[:HAS_MESSAGE]->(m)
        CREATE (u)-[:SENT]->(m)
        
        SET c.last_message_at = datetime(),
            c.message_count = coalesce(c.message_count, 0) + 1
      `, { channel, userId, content, response, sentiment: metadata?.sentiment });
    } finally {
      await session.close();
    }
  }
  
  async getContext({ channel, userId, limit = 10 }) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (c:Conversation {user_id: $userId, channel: $channel})-[:HAS_MESSAGE]->(m:Message)
        WHERE m.timestamp > datetime() - duration({hours: 24})
        RETURN m.content as content, m.response as response, m.timestamp as ts
        ORDER BY m.timestamp DESC
        LIMIT $limit
      `, { userId, channel, limit });
      
      return result.records.map(r => ({
        content: r.get('content'),
        response: r.get('response'),
        timestamp: r.get('ts')
      }));
    } finally {
      await session.close();
    }
  }
}
```

---

## Monitoring Setup (Week 5)

### 9. Health Check Endpoint
**File:** `src/api/health.js`

```javascript
app.get('/health', async (req, res) => {
  const session = driver.session();
  try {
    const agents = await session.run(`
      MATCH (a:Agent)
      RETURN a.id as id, a.status as status, 
             a.last_heartbeat as heartbeat,
             a.current_load as load,
             a.max_concurrent as max
    `);
    
    const tasks = await session.run(`
      MATCH (t:Task)
      RETURN t.status as status, count(*) as count
    `);
    
    const unhealthyAgents = agents.records.filter(r => {
      const lastHeartbeat = new Date(r.get('heartbeat'));
      return Date.now() - lastHeartbeat > 120000; // 2 min
    });
    
    const status = unhealthyAgents.length === 0 ? 'healthy' : 'degraded';
    
    res.json({
      status,
      timestamp: new Date().toISOString(),
      agents: agents.records.map(r => ({
        id: r.get('id'),
        status: r.get('status'),
        load: `${r.get('load')}/${r.get('max')}`
      })),
      tasks: tasks.records.reduce((acc, r) => {
        acc[r.get('status')] = r.get('count').toNumber();
        return acc;
      }, {}),
      alerts: unhealthyAgents.map(r => ({
        type: 'agent_unhealthy',
        agent: r.get('id')
      }))
    });
  } finally {
    await session.close();
  }
});
```

### 10. Queue Depth Alert
**File:** `src/alerts/queue-monitor.js`

```javascript
class QueueMonitor {
  constructor(neo4jDriver, alertRouter) {
    this.driver = neo4jDriver;
    this.alerts = alertRouter;
    
    setInterval(() => this.checkQueueDepth(), 60000);
  }
  
  async checkQueueDepth() {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (t:Task {status: 'pending'})
        RETURN count(*) as pending
      `);
      
      const pending = result.records[0].get('pending').toNumber();
      
      if (pending > 100) {
        await this.alerts.send({
          severity: 'warning',
          title: 'Queue Depth Alert',
          message: `${pending} tasks pending in queue`,
          metric: 'queue_depth',
          value: pending
        });
      }
      
      if (pending > 200) {
        await this.alerts.send({
          severity: 'critical',
          title: 'Queue Backlog Critical',
          message: `${pending} tasks pending - scaling recommended`,
          metric: 'queue_depth',
          value: pending
        });
      }
    } finally {
      await session.close();
    }
  }
}
```

---

## Migration Path

### Existing Code Changes Required

| Component | Change | Effort |
|-----------|--------|--------|
| NotionIntegration | Add task queue enqueue | 2 hours |
| DelegationProtocol | Add event publishing | 1 hour |
| Discord Bot | Add memory recording | 4 hours |
| ProposalStateMachine | Add task creation on state change | 2 hours |
| All Agents | Add heartbeat + task consumption | 4 hours |

### Database Migration

```bash
# Run migrations
node scripts/run-cypher-migration.js migrations/001-task-queue.cypher
node scripts/run-cypher-migration.js migrations/002-memory-schema.cypher
```

### Environment Variables

```bash
# Add to .env
ORCHESTRATOR_ENABLED=true
TASK_QUEUE_MAX_RETRIES=3
TASK_TIMEOUT_MINUTES=30
AGENT_HEARTBEAT_SECONDS=30
QUEUE_DEPTH_ALERT_THRESHOLD=100
```

---

## Testing Strategy

### Unit Tests
```javascript
// test/task-queue.test.js
describe('UnifiedTaskQueue', () => {
  test('enqueue creates task with correct priority', async () => {
    const taskId = await queue.enqueue({ type: 'test', priority: 'P1' });
    const task = await getTask(taskId);
    expect(task.priority).toBe('P1');
  });
  
  test('assignNext respects agent capability', async () => {
    // Create agent with specific capability
    await createAgent({ id: 'test-agent', capabilities: ['dev'] });
    
    // Create task requiring different capability
    await queue.enqueue({ type: 'test', requiredCapability: 'ops' });
    
    // Should not assign
    const assigned = await queue.assignNext('test-agent');
    expect(assigned).toBeNull();
  });
});
```

### Integration Tests
```javascript
// test/orchestrator-integration.test.js
describe('End-to-End Flow', () => {
  test('Notion task → Queue → Agent → Completion', async () => {
    // 1. Create Notion task
    const notionTask = await notion.createTask({ title: 'Test' });
    
    // 2. Poll and queue
    await notionIntegration.pollForTasks();
    
    // 3. Verify task in queue
    const queued = await queue.getPending();
    expect(queued).toHaveLength(1);
    
    // 4. Simulate agent pickup
    const task = await queue.assignNext('test-agent');
    expect(task).not.toBeNull();
    
    // 5. Complete task
    await queue.completeTask(task.taskId, { success: true }, 'test-agent');
    
    // 6. Verify Notion updated
    const updated = await notion.getTask(notionTask.id);
    expect(updated.status).toBe('Completed');
  });
});
```

---

## Rollout Plan

### Phase 1: Silent Mode (Week 1)
- Deploy EventRouter with logging only
- Deploy Task Queue alongside existing system
- No agent changes yet

### Phase 2: Parallel Running (Week 2)
- Enable task creation from Notion
- Agents read from new queue AND old system
- Compare results, fix issues

### Phase 3: Cutover (Week 3)
- Switch agents to new queue exclusively
- Disable old polling mechanisms
- Monitor closely

### Phase 4: Cleanup (Week 4)
- Remove old code paths
- Optimize based on metrics
- Document learnings

---

## Files to Create

```
src/
  orchestrator/
    event-router.js
    task-queue.js
    health-service.js
    agent-pool.js
  services/
    memory-service.js
    alert-service.js
  integrations/
    notion-task-queue.js
    discord-context.js
    github-webhook.js
  api/
    health.js
    metrics.js
    tasks.js
  agents/
    base-agent.js          # Base class with heartbeat, task consumption
    ogedei-agent.js        # Refactored Ögedei
    temujin-agent.js       # Refactored Temüjin
    kublai-agent.js        # Refactored Kublai
  alerts/
    queue-monitor.js
    health-monitor.js
    circuit-breaker.js

migrations/
  001-task-queue.cypher
  002-memory-schema.cypher
  003-agent-state.cypher

test/
  orchestrator/
    event-router.test.js
    task-queue.test.js
    health-service.test.js
  integration/
    end-to-end.test.js
```

---

## Success Metrics Dashboard

Track these metrics from day 1:

```javascript
// metrics to collect
const metrics = {
  // Queue health
  'tasks.pending': () => getPendingCount(),
  'tasks.in_progress': () => getInProgressCount(),
  'tasks.completed_per_minute': () => getCompletionRate(),
  'tasks.avg_wait_time_ms': () => getAvgWaitTime(),
  
  // Agent health
  'agents.healthy': () => getHealthyAgentCount(),
  'agents.unhealthy': () => getUnhealthyAgentCount(),
  'agents.avg_load': () => getAvgAgentLoad(),
  
  // Memory utilization
  'memory.conversations_recorded': () => getConversationCount(),
  'memory.context_hits': () => getContextHitRate(),
  
  // System health
  'events.per_minute': () => getEventRate(),
  'circuit_breaker.opens': () => getCircuitBreakerOpens(),
  'auto_recoveries': () => getAutoRecoveryCount()
};
```

---

## Questions for Review

1. **Scaling**: Should we support horizontal scaling of agents across multiple Railway instances?

2. **Priority Inversion**: How do we handle cases where a P3 task holds resources needed by a P0 task?

3. **Dead Letter Queue**: Where do permanently failed tasks go for manual review?

4. **Multi-tenancy**: Do we need to support multiple teams/agents with isolated queues?

5. **Backpressure**: How do we handle when downstream (LLM API) is rate-limited?

---

**Ready for Implementation Review**
