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

## Heartbeat Response Rules
- If nothing needs attention → reply `HEARTBEAT_OK`
- If tasks delegated → reply with delegation summary
- If critical issues → alert text only (no HEARTBEAT_OK)
