# Operational Architecture Design
## Ögedei (Operations) Analysis - Code Review Issue Resolution

**Date:** 2026-02-12  
**Architect:** Ögedei (Operations Agent)  
**Status:** Design Document - Pending Review

---

## Executive Summary

This document proposes a unified operational architecture that transforms disconnected systems into an orchestrated, event-driven ecosystem. The architecture addresses four critical gaps:

1. **Task Execution Gap**: Notion polling creates tasks but doesn't execute them
2. **Context Gap**: Discord bot responds with templates instead of contextual responses  
3. **Memory Utilization Gap**: Neo4j memories exist but aren't actively used
4. **Coordination Gap**: No unified task queue for agent work

---

## Current State Analysis

### System Inventory

| System | Purpose | Current Behavior | Gap |
|--------|---------|------------------|-----|
| GitHub Poller | Skill sync | Polls every N min, validates, deploys | No task queue integration |
| DelegationProtocol | Proposal routing | Routes through Ögedei→Temüjin | No health monitoring |
| Proposal State Machine | Lifecycle management | State transitions with guardrails | No failure recovery |
| ProactiveReflection | Architecture analysis | Weekly cron job | No execution trigger |
| GoalOrchestrator | NL command parsing | Parses user intent | No task creation |
| Neo4j | Graph storage | Stores sections/proposals/memories | Not used for context |
| Task Directories | File-based tasks | Inbox→Assigned→In-Progress→Review→Done | No agent assignment logic |
| Discord/Signal/Telegram | Messaging | Template responses | No memory recording |

### Disconnection Points

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Notion Poller  │────→│  Task Creation  │────→│  ??? (No Queue) │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                                               │
         ▼                                               ▼
   Creates Neo4j                                    Tasks sit in
   Task nodes                                       directories
                                                      unread
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Discord Bot    │────→│  Template Resp  │────→│  No Memory      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                                               │
         ▼                                               ▼
   Receives messages                             Conversations
   from users                                    lost forever

┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Agent Tasks    │────→│  File System    │────→│  No Assignment  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                                               │
         ▼                                               ▼
   Background jobs                                No load balancing
   on schedule                                    No health checks
```

---

## Proposed Architecture: The Steppe Orchestrator

### Design Principles

1. **Event-Driven Over Polling**: Replace polling with event-driven architecture where possible
2. **Unified Task Queue**: Single source of truth for all agent work
3. **Memory-First Design**: All interactions recorded to Neo4j for context
4. **Health-Aware Assignment**: Tasks assigned based on agent health and capacity
5. **Failure Domains**: Isolated failure domains with auto-recovery

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          THE STEPPE ORCHESTRATOR                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Event      │  │   Unified    │  │   Health &   │  │   Memory     │     │
│  │   Router     │  │   Task Queue │  │   Recovery   │  │   Service    │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
│         │                 │                 │                 │              │
│         └─────────────────┴─────────────────┴─────────────────┘              │
│                              │                                               │
│                    ┌─────────┴─────────┐                                     │
│                    │  State Manager    │                                     │
│                    │  (Neo4j Core)     │                                     │
│                    └─────────┬─────────┘                                     │
│                              │                                               │
│  ┌───────────────────────────┼───────────────────────────┐                   │
│  │                           │                           │                   │
│  ▼                           ▼                           ▼                   │
│ ┌─────────────┐      ┌─────────────┐      ┌─────────────┐                   │
│ │   Agent     │      │   Agent     │      │   Agent     │                   │
│ │   Pool      │      │   Pool      │      │   Pool      │                   │
│ │ (Ögedei)    │      │ (Temüjin)   │      │ (Kublai)    │                   │
│ └─────────────┘      └─────────────┘      └─────────────┘                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Specifications

### 1. Event Router

**Purpose**: Central event ingestion and routing system

**Events Tracked**:
- `notion.task.created` - New task from Notion
- `discord.message.received` - User message on Discord
- `github.pr.merged` - Code changes merged
- `agent.task.completed` - Task completion
- `agent.health.changed` - Health status change
- `system.threshold.breached` - Resource limits hit

**Implementation**:
```javascript
class EventRouter {
  constructor(neo4jDriver, eventBus) {
    this.driver = neo4jDriver;
    this.subscribers = new Map();
    this.eventLog = []; // Ring buffer for recent events
  }

  async publish(eventType, payload, metadata = {}) {
    const event = {
      id: randomUUID(),
      type: eventType,
      payload,
      metadata: {
        timestamp: new Date(),
        source: metadata.source,
        correlationId: metadata.correlationId || randomUUID(),
        ...metadata
      }
    };

    // Persist to Neo4j for audit trail
    await this.persistEvent(event);

    // Route to subscribers
    const handlers = this.subscribers.get(eventType) || [];
    await Promise.all(handlers.map(h => h(event).catch(err => {
      this.logger.error(`Handler failed for ${eventType}:`, err);
    })));

    return event;
  }

  subscribe(eventType, handler) {
    if (!this.subscribers.has(eventType)) {
      this.subscribers.set(eventType, []);
    }
    this.subscribers.get(eventType).push(handler);
  }
}
```

**Event Flow**:
```
Notion Webhook → Event Router → Task Queue → Agent Assignment
Discord Message → Event Router → Memory Service → Context Enrichment → Response
GitHub Webhook → Event Router → Proposal Creation → Delegation Protocol
Health Alert → Event Router → Recovery Service → Auto-remediation
```

---

### 2. Unified Task Queue

**Purpose**: Single source of truth for all agent work with priority-based scheduling

**Queue Design**:
```
┌─────────────────────────────────────────────────────────────┐
│                    TASK QUEUE STRUCTURE                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Priority Tiers (Highest to Lowest):                        │
│                                                              │
│  ┌─────────────┐  Critical: System health, failures         │
│  │   P0        │  Max wait: 30 seconds                      │
│  │ Critical    │  Preempts: All lower priorities            │
│  └─────────────┘                                            │
│                                                              │
│  ┌─────────────┐  High: User-facing tasks, revenue impact   │
│  │   P1        │  Max wait: 5 minutes                       │
│  │ High        │  Preempts: P2, P3                          │
│  └─────────────┘                                            │
│                                                              │
│  ┌─────────────┐  Normal: Standard work, proposals          │
│  │   P2        │  Max wait: 30 minutes                      │
│  │ Normal      │  Preempts: P3                              │
│  └─────────────┘                                            │
│                                                              │
│  ┌─────────────┐  Low: Background tasks, cleanup            │
│  │   P3        │  Max wait: 2 hours                         │
│  │ Low         │  Preempts: None                            │
│  └─────────────┘                                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Scheduling Algorithm**: Weighted Fair Queueing with Agent Affinity

```javascript
class UnifiedTaskQueue {
  constructor(neo4jDriver, config) {
    this.driver = neo4jDriver;
    this.config = {
      maxConcurrentPerAgent: config.maxConcurrentPerAgent || 3,
      taskTimeoutMinutes: config.taskTimeoutMinutes || 30,
      retryAttempts: config.retryAttempts || 3,
      retryBackoffMs: config.retryBackoffMs || 60000
    };
  }

  async enqueue(task) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        CREATE (t:Task {
          id: $id,
          type: $type,
          priority: $priority,
          status: 'pending',
          payload: $payload,
          created_at: datetime(),
          expires_at: datetime() + duration({minutes: $timeout}),
          attempts: 0,
          max_attempts: $maxAttempts,
          assigned_to: null,
          correlation_id: $correlationId
        })
        WITH t
        OPTIONAL MATCH (a:Agent)
        WHERE a.capabilities CONTAINS $requiredCapability
          AND a.status = 'healthy'
          AND a.current_load < a.max_concurrent
        WITH t, collect(a.id) as availableAgents
        SET t.potential_agents = availableAgents
        RETURN t.id as id
      `, {
        id: randomUUID(),
        type: task.type,
        priority: task.priority || 'P2',
        payload: JSON.stringify(task.payload),
        timeout: this.config.taskTimeoutMinutes,
        maxAttempts: this.config.retryAttempts,
        correlationId: task.correlationId,
        requiredCapability: task.requiredCapability
      });

      return result.records[0].get('id');
    } finally {
      await session.close();
    }
  }

  async assignNextTask(agentId) {
    const session = this.driver.session();
    try {
      // Atomic assignment with conflict resolution
      const result = await session.run(`
        MATCH (t:Task {status: 'pending'})
        WHERE t.expires_at > datetime()
          AND (t.assigned_to IS NULL OR t.assigned_to = $agentId)
          AND $agentId IN t.potential_agents
        WITH t
        ORDER BY 
          CASE t.priority
            WHEN 'P0' THEN 0
            WHEN 'P1' THEN 1
            WHEN 'P2' THEN 2
            WHEN 'P3' THEN 3
            ELSE 4
          END,
          t.created_at ASC
        LIMIT 1
        MATCH (a:Agent {id: $agentId})
        WHERE a.current_load < a.max_concurrent
        SET t.status = 'assigned',
            t.assigned_to = $agentId,
            t.assigned_at = datetime(),
            a.current_load = a.current_load + 1
        RETURN t.id as taskId, t.type as type, t.payload as payload
      `, { agentId });

      if (result.records.length === 0) {
        return null;
      }

      return {
        taskId: result.records[0].get('taskId'),
        type: result.records[0].get('type'),
        payload: JSON.parse(result.records[0].get('payload'))
      };
    } finally {
      await session.close();
    }
  }

  async completeTask(taskId, result, agentId) {
    const session = this.driver.session();
    try {
      await session.run(`
        MATCH (t:Task {id: $taskId})
        MATCH (a:Agent {id: $agentId})
        SET t.status = 'completed',
            t.completed_at = datetime(),
            t.result = $result,
            a.current_load = CASE 
              WHEN a.current_load > 0 THEN a.current_load - 1 
              ELSE 0 
            END
        CREATE (t)-[:COMPLETED_BY]->(a)
      `, { taskId, agentId, result: JSON.stringify(result) });
    } finally {
      await session.close();
    }
  }

  async failTask(taskId, error, agentId) {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (t:Task {id: $taskId})
        SET t.attempts = t.attempts + 1,
            t.last_error = $error,
            t.failed_at = datetime()
        WITH t
        CALL {
          WITH t
          WITH t,
            CASE 
              WHEN t.attempts >= t.max_attempts THEN 'failed_permanently'
              ELSE 'pending'
            END as newStatus,
            CASE 
              WHEN t.attempts >= t.max_attempts THEN null
              ELSE datetime() + duration({milliseconds: $backoff})
            END as retryAt
          SET t.status = newStatus,
              t.retry_at = retryAt
          RETURN newStatus
        }
        MATCH (a:Agent {id: $agentId})
        SET a.current_load = CASE 
          WHEN a.current_load > 0 THEN a.current_load - 1 
          ELSE 0 
        END
        CREATE (t)-[:FAILED_BY {error: $error, at: datetime()}]->(a)
        RETURN t.status as finalStatus
      `, { taskId, agentId, error: error.message, backoff: this.config.retryBackoffMs });

      return result.records[0].get('finalStatus');
    } finally {
      await session.close();
    }
  }
}
```

---

### 3. Health & Recovery Service

**Purpose**: Monitor system health and trigger auto-recovery procedures

**Health Metrics**:
- Agent heartbeat (last ping time)
- Task completion rate (success/failure ratio)
- Queue depth (tasks waiting > threshold)
- Resource utilization (memory, CPU, disk)
- External service health (Neo4j, Notion, Discord)

**Recovery Procedures**:
```
┌─────────────────────────────────────────────────────────────┐
│                  FAILURE SCENARIOS & RECOVERY                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Agent Unresponsive:                                         │
│  1. Mark agent as 'unhealthy'                                │
│  2. Reassign active tasks to other agents                    │
│  3. Alert operator after 3 consecutive failures              │
│  4. Attempt agent restart (if containerized)                 │
│                                                              │
│  Task Stalled:                                               │
│  1. Detect tasks > timeout threshold                         │
│  2. Force-cancel and retry with exponential backoff          │
│  3. Escalate to P0 if retry limit exceeded                   │
│                                                              │
│  Queue Backlog:                                              │
│  1. Alert when queue depth > threshold                       │
│  2. Auto-scale agent pool (if supported)                     │
│  3. Degrade non-critical services                            │
│                                                              │
│  External Service Down:                                      │
│  1. Circuit breaker pattern - fail fast                      │
│  2. Queue affected tasks for retry                           │
│  3. Notify via alternative channels                          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Implementation**:
```javascript
class HealthRecoveryService {
  constructor(neo4jDriver, eventRouter, config) {
    this.driver = neo4jDriver;
    this.eventRouter = eventRouter;
    this.config = {
      agentTimeoutSeconds: config.agentTimeoutSeconds || 60,
      queueDepthThreshold: config.queueDepthThreshold || 100,
      failureRateThreshold: config.failureRateThreshold || 0.3,
      checkIntervalSeconds: config.checkIntervalSeconds || 30
    };
    this.circuitBreakers = new Map();
  }

  async checkAgentHealth() {
    const session = this.driver.session();
    try {
      const result = await session.run(`
        MATCH (a:Agent)
        WHERE a.last_heartbeat < datetime() - duration({seconds: $timeout})
          AND a.status = 'healthy'
        SET a.status = 'unhealthy',
            a.unhealthy_since = datetime()
        RETURN a.id as agentId
      `, { timeout: this.config.agentTimeoutSeconds });

      for (const record of result.records) {
        const agentId = record.get('agentId');
        this.logger.warn(`Agent ${agentId} marked unhealthy`);

        // Reassign tasks
        await this.reassignAgentTasks(agentId);

        // Publish event
        await this.eventRouter.publish('agent.health.changed', {
          agentId,
          status: 'unhealthy',
          reason: 'heartbeat_timeout'
        });
      }
    } finally {
      await session.close();
    }
  }

  async reassignAgentTasks(agentId) {
    const session = this.driver.session();
    try {
      // Find tasks assigned to unhealthy agent
      const result = await session.run(`
        MATCH (t:Task {assigned_to: $agentId, status: 'assigned'})
        SET t.status = 'pending',
            t.assigned_to = null,
            t.reassigned = true,
            t.reassigned_at = datetime()
        RETURN t.id as taskId
      `, { agentId });

      this.logger.info(`Reassigned ${result.records.length} tasks from ${agentId}`);
    } finally {
      await session.close();
    }
  }

  async checkCircuitBreaker(serviceName) {
    const cb = this.circuitBreakers.get(serviceName) || {
      state: 'closed',
      failures: 0,
      lastFailure: null
    };

    if (cb.state === 'open') {
      const elapsed = Date.now() - cb.lastFailure;
      if (elapsed > 60000) { // 1 minute cooldown
        cb.state = 'half-open';
        this.circuitBreakers.set(serviceName, cb);
      }
      return cb.state;
    }

    return cb.state;
  }

  recordFailure(serviceName) {
    const cb = this.circuitBreakers.get(serviceName) || {
      state: 'closed',
      failures: 0,
      lastFailure: null
    };

    cb.failures++;
    cb.lastFailure = Date.now();

    if (cb.failures >= 5) {
      cb.state = 'open';
      this.logger.error(`Circuit breaker OPEN for ${serviceName}`);
    }

    this.circuitBreakers.set(serviceName, cb);
  }
}
```

---

### 4. Memory Service

**Purpose**: Record all interactions to Neo4j for context-aware responses

**Memory Types**:
- **Conversation Memory**: Discord/Signal/Telegram message history
- **Task Memory**: Task creation, assignment, completion history
- **System Memory**: Health events, failures, recoveries
- **User Memory**: User preferences, interaction patterns

**Implementation**:
```javascript
class MemoryService {
  constructor(neo4jDriver) {
    this.driver = neo4jDriver;
  }

  async recordConversation(channel, userId, message, response, metadata = {}) {
    const session = this.driver.session();
    try {
      await session.run(`
        MATCH (u:User {id: $userId})
        MERGE (c:Conversation {channel: $channel, user_id: $userId})
        ON CREATE SET c.created_at = datetime()
        CREATE (m:Message {
          id: randomUUID(),
          content: $message,
          response: $response,
          timestamp: datetime(),
          channel: $channel,
          sentiment: $sentiment,
          intent: $intent
        })
        CREATE (c)-[:HAS_MESSAGE]->(m)
        CREATE (u)-[:SENT]->(m)

        // Update conversation summary
        WITH c
        SET c.last_message_at = datetime(),
            c.message_count = coalesce(c.message_count, 0) + 1
      `, {
        channel,
        userId,
        message,
        response,
        sentiment: metadata.sentiment,
        intent: metadata.intent
      });
    } finally {
      await session.close();
    }
  }

  async getContextForResponse(channel, userId, currentMessage) {
    const session = this.driver.session();
    try {
      // Get recent conversation history
      const historyResult = await session.run(`
        MATCH (c:Conversation {channel: $channel, user_id: $userId})-[:HAS_MESSAGE]->(m:Message)
        WHERE m.timestamp > datetime() - duration({hours: 24})
        RETURN m.content as content, m.response as response, m.timestamp as ts
        ORDER BY m.timestamp DESC
        LIMIT 10
      `, { channel, userId });

      // Get relevant memories from knowledge graph
      const memoryResult = await session.run(`
        CALL db.index.fulltext.queryNodes('memory_search', $query)
        YIELD node, score
        WHERE score > 0.5
        RETURN node.content as content, node.type as type, score
        ORDER BY score DESC
        LIMIT 5
      `, { query: currentMessage });

      // Get user's task history
      const taskResult = await session.run(`
        MATCH (u:User {id: $userId})-[:CREATED|ASSIGNED_TO]->(t:Task)
        WHERE t.created_at > datetime() - duration({days: 7})
        RETURN t.type as type, t.status as status, t.result as result
        ORDER BY t.created_at DESC
        LIMIT 5
      `, { userId });

      return {
        conversationHistory: historyResult.records.map(r => ({
          content: r.get('content'),
          response: r.get('response'),
          timestamp: r.get('ts')
        })),
        relevantMemories: memoryResult.records.map(r => ({
          content: r.get('content'),
          type: r.get('type'),
          score: r.get('score')
        })),
        recentTasks: taskResult.records.map(r => ({
          type: r.get('type'),
          status: r.get('status'),
          result: r.get('result')
        }))
      };
    } finally {
      await session.close();
    }
  }
}
```

---

## Integration Points

### Notion Integration

```javascript
class NotionIntegration {
  constructor(notionClient, eventRouter, taskQueue) {
    this.notion = notionClient;
    this.eventRouter = eventRouter;
    this.taskQueue = taskQueue;
  }

  async pollForTasks() {
    // Fetch new tasks from Notion
    const tasks = await this.notion.databases.query({
      database_id: process.env.NOTION_TASKS_DB,
      filter: {
        property: 'Status',
        select: { equals: 'Not Started' }
      }
    });

    for (const notionTask of tasks.results) {
      // Create task in unified queue
      const taskId = await this.taskQueue.enqueue({
        type: 'notion_task',
        priority: this.inferPriority(notionTask),
        payload: {
          notionId: notionTask.id,
          title: notionTask.properties.Name.title[0]?.plain_text,
          description: notionTask.properties.Description?.rich_text[0]?.plain_text,
          assignee: notionTask.properties.Assignee?.select?.name
        },
        requiredCapability: this.inferCapability(notionTask)
      });

      // Update Notion with task reference
      await this.notion.pages.update({
        page_id: notionTask.id,
        properties: {
          Status: { select: { name: 'In Queue' } },
          InternalTaskId: { rich_text: [{ text: { content: taskId } }] }
        }
      });

      // Publish event
      await this.eventRouter.publish('notion.task.queued', {
        notionId: notionTask.id,
        taskId
      });
    }
  }

  inferPriority(notionTask) {
    const priority = notionTask.properties.Priority?.select?.name;
    const mapping = {
      'Urgent': 'P0',
      'High': 'P1',
      'Medium': 'P2',
      'Low': 'P3'
    };
    return mapping[priority] || 'P2';
  }

  inferCapability(notionTask) {
    const tags = notionTask.properties.Tags?.multi_select?.map(t => t.name) || [];
    if (tags.includes('code')) return 'development';
    if (tags.includes('ops')) return 'operations';
    if (tags.includes('strategy')) return 'strategy';
    return 'general';
  }
}
```

### Discord Integration

```javascript
class DiscordIntegration {
  constructor(discordClient, eventRouter, memoryService, taskQueue) {
    this.discord = discordClient;
    this.eventRouter = eventRouter;
    this.memory = memoryService;
    this.taskQueue = taskQueue;
  }

  async handleMessage(message) {
    // Skip bot messages
    if (message.author.bot) return;

    // Record to memory immediately
    await this.memory.recordConversation(
      'discord',
      message.author.id,
      message.content,
      null, // Response to be filled later
      {
        sentiment: await this.analyzeSentiment(message.content),
        intent: await this.classifyIntent(message.content)
      }
    );

    // Publish event
    await this.eventRouter.publish('discord.message.received', {
      userId: message.author.id,
      channelId: message.channelId,
      content: message.content,
      timestamp: message.createdTimestamp
    });

    // Check if this needs agent attention
    if (this.requiresAgentResponse(message)) {
      // Create a response task
      const taskId = await this.taskQueue.enqueue({
        type: 'discord_response',
        priority: this.inferPriority(message),
        payload: {
          messageId: message.id,
          channelId: message.channelId,
          userId: message.author.id,
          content: message.content
        },
        requiredCapability: 'conversation'
      });

      // Acknowledge receipt
      await message.react('👀');
    }
  }

  async generateResponse(task) {
    // Get context from memory
    const context = await this.memory.getContextForResponse(
      'discord',
      task.payload.userId,
      task.payload.content
    );

    // Generate contextual response
    const response = await this.llm.generate({
      messages: [
        { role: 'system', content: this.buildSystemPrompt(context) },
        ...context.conversationHistory.map(h => [
          { role: 'user', content: h.content },
          { role: 'assistant', content: h.response }
        ]).flat(),
        { role: 'user', content: task.payload.content }
      ]
    });

    // Send response
    const channel = await this.discord.channels.fetch(task.payload.channelId);
    await channel.send({
      content: response,
      reply: { messageReference: task.payload.messageId }
    });

    // Update memory with response
    await this.memory.recordConversation(
      'discord',
      task.payload.userId,
      task.payload.content,
      response
    );

    return { sent: true, responseLength: response.length };
  }

  buildSystemPrompt(context) {
    return `You are a helpful assistant with memory of past conversations.

Recent context:
${context.relevantMemories.map(m => `- ${m.content}`).join('\n')}

Recent tasks:
${context.recentTasks.map(t => `- ${t.type} (${t.status})`).join('\n')}

Respond naturally, referencing context when relevant.`;
  }
}
```

---

## Resource Limits & Scaling

### Concurrent Agent Sessions

| Agent Type | Max Concurrent | Queue Depth Alert |
|------------|----------------|-------------------|
| Ögedei (Ops) | 3 | 20 |
| Temüjin (Dev) | 5 | 30 |
| Kublai (Strategy) | 2 | 10 |
| Sub-agents | 10 total | 50 |

### Circuit Breaker Thresholds

| Service | Failure Threshold | Recovery Time |
|---------|-------------------|---------------|
| Neo4j | 5 failures/min | 60s |
| Notion API | 3 failures/min | 30s |
| Discord API | 5 failures/min | 60s |
| OpenAI API | 10 failures/min | 120s |

### Auto-Scaling Triggers

| Metric | Threshold | Action |
|--------|-----------|--------|
| Queue depth | > 100 tasks | Alert + Scale up |
| Task wait time | > 10 min (P1) | Escalate to P0 |
| Agent failure rate | > 30% | Restart agent pool |
| Memory usage | > 80% | Clear old conversation history |

---

## Monitoring & Alerting

### Dashboard Metrics

```
┌─────────────────────────────────────────────────────────────┐
│                     OPERATIONS DASHBOARD                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Queue Health          Agent Health        System Health    │
│  ────────────          ───────────         ─────────────    │
│  Pending: 23           Ögedei: ✅          Neo4j: ✅        │
│  In Progress: 5        Temüjin: ✅         Notion: ✅       │
│  Stalled: 0            Kublai: ✅          Discord: ✅      │
│  Failed (1h): 2        Sub-agents: 4/10    Memory: 45%      │
│                                                              │
│  Recent Activity                                             │
│  ─────────────                                               │
│  [10:23] Task completed: Update deployment docs             │
│  [10:15] Agent recovered: Temüjin (was unhealthy)           │
│  [10:08] Task assigned: Review PR #234                      │
│  [09:45] Alert: Queue depth exceeded 100 (resolved)         │
│                                                              │
│  Active Tasks by Agent                                       │
│  ─────────────────────                                       │
│  Ögedei: 2/3    ████████░░                                  │
│  Temüjin: 3/5   ██████████░░                                │
│  Kublai: 1/2    ██████░░░░                                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Alert Channels

| Severity | Channel | Response Time |
|----------|---------|---------------|
| P0 (Critical) | Signal + Discord + Email | Immediate |
| P1 (High) | Discord + Email | 5 minutes |
| P2 (Normal) | Discord | 30 minutes |
| P3 (Low) | Dashboard only | N/A |

---

## Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
1. Implement EventRouter with Neo4j persistence
2. Create UnifiedTaskQueue with priority scheduling
3. Build HealthRecoveryService with circuit breakers
4. Set up basic monitoring dashboard

### Phase 2: Integration (Week 3-4)
1. Connect NotionIntegration to UnifiedTaskQueue
2. Connect DiscordIntegration with MemoryService
3. Migrate existing agents to task-based model
4. Implement agent heartbeat mechanism

### Phase 3: Intelligence (Week 5-6)
1. Deploy MemoryService with full context retrieval
2. Implement contextual Discord responses
3. Add auto-recovery procedures
4. Create alert routing system

### Phase 4: Optimization (Week 7-8)
1. Performance tuning based on metrics
2. Add predictive scaling
3. Implement task result caching
4. Create runbook automation

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Neo4j becomes bottleneck | Medium | High | Connection pooling, read replicas |
| Event router loses messages | Low | Critical | Persistent event log, at-least-once delivery |
| Agent pool exhaustion | Medium | Medium | Auto-scaling, circuit breakers |
| Cascade failures | Low | High | Circuit breakers, failure isolation |
| Data inconsistency | Medium | High | ACID transactions, idempotent operations |

---

## Success Metrics

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Task execution rate | ~0% (manual) | >90% | Tasks completed / Tasks created |
| Response context quality | Low (templates) | High | User satisfaction score |
| Memory utilization | <5% | >80% | Neo4j query coverage |
| Mean time to recovery | Manual | <5 min | Health event to recovery |
| Queue wait time (P1) | N/A | <2 min | Time from enqueue to assign |

---

## Conclusion

The Steppe Orchestrator architecture provides a unified, event-driven solution to the identified operational gaps. By implementing:

1. **Event Router**: All system events flow through a central hub
2. **Unified Task Queue**: Single source of truth for agent work with priority scheduling
3. **Health & Recovery**: Automatic detection and remediation of failures
4. **Memory Service**: Contextual awareness for all interactions

The architecture transforms disconnected systems into an intelligent, self-healing operational fabric that scales with demand and learns from interactions.

**Next Steps:**
1. Review and approve architecture design
2. Prioritize Phase 1 implementation
3. Set up staging environment for testing
4. Begin EventRouter development
