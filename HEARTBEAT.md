# HEARTBEAT.md - Kublai (Main/Router)

## Frequency
**Every 5 minutes**

## Background Tasks

### Task 0: Autonomous Task Orchestration
**Schedule**: Every 5 minutes (first priority)
**Description**: Ensure all tasks get assigned, delegated, and started autonomously

**Actions**:
1. Find pending tasks without assignees → Auto-assign based on capability matching
2. Find assigned tasks without AgentMessages → Create delegation messages
3. Find agents with pending tasks but dormant → Trigger spawn
4. Find ready tasks (assigned + messaged) → Auto-start to in_progress

**Agent Capability Mapping**:
- Möngke → research, web_search, api_analysis
- Chagatai → writing, documentation, content
- Temüjin → development, coding, implementation
- Jochi → analysis, security, testing, audit
- Ögedei → operations, monitoring, health_check
- Kublai → orchestration, routing, synthesis

### Task 1: Status Synthesis
**Schedule**: Every 5 minutes
**Description**: Aggregate agent heartbeat results from Neo4j

**Actions**:
1. Query Neo4j for all agent statuses
2. Identify any agents with stale heartbeats
3. Check for critical issues and escalate if needed

### Task 2: Autonomous Task Delegation
**Schedule**: Every 5 minutes  
**Description**: Automatically delegate pending tasks to specialist agents

**Actions**:
1. Query for pending tasks assigned to specialist agents (Möngke, Chagatai, Temüjin, Jochi, Ögedei)
2. For each pending task:
   - Create AgentMessage node with task_assignment payload
   - Set task.delegated_by = 'Kublai'
   - Log delegation to Neo4j
3. Skip if task already has delegation message pending
4. Only delegate if no active delegation exists for that task

**Agent Mapping**:
- Möngke → researcher
- Chagatai → writer  
- Temüjin → developer
- Jochi → analyst
- Ögedei → ops

### Task 3: Critical Escalation Check
**Schedule**: Every 5 minutes (on critical findings)
**Description**: Escalate critical issues immediately

**Escalation Criteria**:
- Multiple agent heartbeats fail consecutively
- Failover protocol activates (Ögedei assumes routing)
- Security issues detected
- Resource exhaustion

### Task 4: Hourly Task List Updates (Via Ögedei)
**Schedule**: Every 5 minutes, trigger at :00 of each hour
**Description**: Send updated task list to user via Notion + Signal

**Actions**:
1. Check if current minute is :00 (top of hour)
2. Query Ögedei for task status from Notion
3. Generate formatted task list:
   - Danny's active tasks (from Notion)
   - Kublai's active tasks (from Neo4j + Notion)
   - Current focus items
   - System status
4. Send via Signal to +19194133445

**Integration**:
- Ögedei manages tasks in Notion "Kurultai Business Operations" database
- Tasks synced bidirectionally with Neo4j
- Updates sent hourly at :00 UTC

### Task 5: Discord Deliberation Sync
**Schedule**: Every 5 minutes
**Description**: Sync heartbeat status to Discord #heartbeat-log and announce completed tasks

**Actions**:
1. Query Neo4j for agent statuses
2. Send status summary to Discord #heartbeat-log
3. Check for tasks completed since last heartbeat
4. Announce completed tasks to #council-chamber with celebration
5. Send critical alerts to #announcements with @everyone

**Integration**:
```python
# Run heartbeat bridge
python tools/discord/heartbeat_bridge.py

# Or continuous mode
python tools/discord/heartbeat_bridge.py --continuous --interval 5
```

**Channels**:
- `#heartbeat-log` - Status summaries every 5 minutes
- `#council-chamber` - Task completion celebrations
- `#announcements` - Critical alerts with @everyone

**Agent Voices**:
- Status updates sent as Ögedei (Operations)
- Task celebrations sent as completing agent
- Critical alerts sent as Kublai (Router)

## Heartbeat Response Rules
- If nothing needs attention → reply `HEARTBEAT_OK`
- If tasks delegated → reply with delegation summary
- If hourly update sent → reply with task summary
- If critical issues → alert text only (no HEARTBEAT_OK)
