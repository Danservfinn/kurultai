# Steppe Orchestrator - Architecture Diagram

## System Overview

```mermaid
flowchart TB
    subgraph External["External Systems"]
        Notion["Notion API"]
        Discord["Discord Bot"]
        GitHub["GitHub Webhooks"]
        Signal["Signal Bot"]
        Telegram["Telegram Bot"]
    end

    subgraph Orchestrator["Steppe Orchestrator"]
        direction TB
        
        subgraph EventLayer["Event Layer"]
            Router["Event Router"]
            Bus[(Event Bus)]
        end
        
        subgraph Core["Core Services"]
            Queue["Unified Task Queue"]
            Health["Health & Recovery"]
            Memory["Memory Service"]
            State[(Neo4j State Manager)]
        end
        
        subgraph Agents["Agent Pools"]
            Ogedei["Ögedei Pool\n(Ops)"]
            Temujin["Temüjin Pool\n(Dev)"]
            Kublai["Kublai Pool\n(Strategy)"]
            Subagents["Sub-agents\n(Specialized)"]
        end
        
        subgraph Monitors["Monitoring"]
            Dashboard["Ops Dashboard"]
            Alerts["Alert Router"]
        end
    end

    subgraph Storage["Persistent Storage"]
        Neo4j[(Neo4j Graph DB)]
        Redis[(Redis Cache)]
        TaskDirs["Task Directories"]
    end

    %% External → Orchestrator
    Notion -->|Webhook / Poll| Router
    Discord -->|Gateway Events| Router
    GitHub -->|Webhook| Router
    Signal -->|Message| Router
    Telegram -->|Webhook| Router

    %% Event Flow
    Router --> Bus
    Bus --> Queue
    Bus --> Memory
    Bus --> Health

    %% Core Service Interactions
    Queue <-->|Atomic Ops| State
    Memory -->|Store/Retrieve| Neo4j
    Health <-->|Check/Update| State
    
    %% Task Assignment
    Queue -->|Assign Tasks| Ogedei
    Queue -->|Assign Tasks| Temujin
    Queue -->|Assign Tasks| Kublai
    Queue -->|Assign Tasks| Subagents

    %% Agent Updates
    Ogedei -->|Heartbeat| State
    Temujin -->|Heartbeat| State
    Kublai -->|Heartbeat| State
    Subagents -->|Heartbeat| State

    %% Health & Recovery
    Health -->|Reassign| Queue
    Health -->|Scale| Agents
    Health -->|Trigger| Alerts

    %% Monitoring
    State -->|Metrics| Dashboard
    Queue -->|Metrics| Dashboard
    Health -->|Alerts| Alerts
    Alerts -->|Notify| Discord
    Alerts -->|Notify| Signal

    %% Storage
    State -->|Persist| Neo4j
    Queue -->|Cache| Redis
    Agents -->|Read/Write| TaskDirs
```

## Task Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Pending: Task Created
    
    Pending --> Assigned: Agent Available
    Pending --> Failed: Max Retries
    
    Assigned --> InProgress: Agent Accepts
    Assigned --> Pending: Agent Unhealthy
    
    InProgress --> Completed: Success
    InProgress --> Failed: Error
    InProgress --> Stalled: Timeout
    
    Stalled --> Pending: Retry
    Stalled --> Failed: Max Retries
    
    Failed --> Pending: Auto-Retry
    Failed --> Escalated: Manual Required
    
    Completed --> Archived: After 24h
    Escalated --> [*]
    Archived --> [*]
```

## Event Flow Examples

### Notion Task → Agent Execution

```mermaid
sequenceDiagram
    participant Notion as Notion API
    participant Router as Event Router
    participant Queue as Task Queue
    participant State as Neo4j State
    participant Agent as Ögedei Agent
    participant Health as Health Service

    Notion->>Router: notion.task.created
    Router->>State: Persist Event
    Router->>Queue: Enqueue Task
    Queue->>State: Create Task Node
    
    loop Health Check
        Health->>State: Check Agent Health
        State-->>Health: Agent Status
    end
    
    Queue->>State: Assign to Agent
    State-->>Queue: Assignment Confirmed
    Queue->>Agent: Deliver Task
    
    Agent->>Agent: Execute Task
    Agent->>State: Update Progress
    Agent->>Queue: Task Complete
    Queue->>State: Mark Completed
    Queue->>Router: task.completed
    Router->>Notion: Update Task Status
```

### Discord Message → Contextual Response

```mermaid
sequenceDiagram
    participant User as Discord User
    participant Discord as Discord Bot
    participant Router as Event Router
    participant Memory as Memory Service
    participant Neo4j as Neo4j Graph
    participant Queue as Task Queue
    participant Agent as Response Agent

    User->>Discord: Send Message
    Discord->>Router: discord.message.received
    Router->>Memory: Record Message
    Memory->>Neo4j: Store Conversation
    
    Router->>Queue: Enqueue Response Task
    Queue->>Agent: Assign Response Task
    
    Agent->>Memory: Get Context
    Memory->>Neo4j: Query History
    Neo4j-->>Memory: Recent Messages
    Neo4j-->>Memory: Relevant Memories
    Memory-->>Agent: Context Bundle
    
    Agent->>Agent: Generate Response
    Agent->>Memory: Record Response
    Agent->>Discord: Send Message
    Discord->>User: Contextual Response
```

### Health Failure → Auto-Recovery

```mermaid
sequenceDiagram
    participant Health as Health Service
    participant State as Neo4j State
    participant Queue as Task Queue
    participant Router as Event Router
    participant Alerts as Alert Service
    participant Agent1 as Failed Agent
    participant Agent2 as Healthy Agent

    loop Every 30s
        Health->>State: Check Heartbeats
        State-->>Health: Agent1 Last Ping: 5min ago
        Health->>Health: Detect Timeout
    end
    
    Health->>State: Mark Unhealthy
    Health->>Router: agent.health.changed
    Router->>Alerts: Send Alert
    
    Health->>Queue: Reassign Tasks
    Queue->>State: Find Agent1 Tasks
    State-->>Queue: 3 Active Tasks
    Queue->>State: Update to Pending
    Queue->>Agent2: Assign Tasks
    
    Agent2->>State: Heartbeat
    State-->>Health: New Health Status
```

## Priority Queue Structure

```mermaid
graph LR
    subgraph P0["P0 - Critical"]
        P0_1[System Health]
        P0_2[Security Alert]
        P0_3[Data Loss Risk]
    end
    
    subgraph P1["P1 - High"]
        P1_1[User Request]
        P1_2[Revenue Impact]
        P1_3[SLA Breach]
    end
    
    subgraph P2["P2 - Normal"]
        P2_1[Code Review]
        P2_2[Documentation]
        P2_3[Proposal Review]
    end
    
    subgraph P3["P3 - Low"]
        P3_1[Cleanup]
        P3_2[Analytics]
        P3_3[Archival]
    end
    
    Queue[(Unified Queue)]
    
    P0 -->|Preempts All| Queue
    P1 -->|Preempts P2/P3| Queue
    P2 -->|Preempts P3| Queue
    P3 --> Queue
```

## Memory Graph Schema

```mermaid
graph TD
    subgraph MemoryGraph["Neo4j Memory Graph"]
        User((User))
        Conversation((Conversation))
        Message((Message))
        Task((Task))
        Memory((Memory))
        Agent((Agent))
        
        User -->|PARTICIPATES_IN| Conversation
        Conversation -->|HAS_MESSAGE| Message
        User -->|SENT| Message
        
        User -->|CREATED| Task
        User -->|ASSIGNED_TO| Task
        Agent -->|EXECUTED| Task
        
        Message -->|REFERENCES| Memory
        Task -->|CREATED| Memory
        
        Agent -->|HAS_CAPABILITY| Capability
        Agent -->|HAS_STATE| AgentState
    end
```

## Circuit Breaker Pattern

```mermaid
stateDiagram-v2
    [*] --> Closed: Service Healthy
    
    Closed --> Open: 5 Failures
    Closed --> Closed: Success
    
    Open --> HalfOpen: 60s Timeout
    Open --> Open: Request Blocked
    
    HalfOpen --> Closed: Success
    HalfOpen --> Open: Failure
    
    note right of Closed
        Requests flow normally
        Failures counted
    end note
    
    note right of Open
        All requests blocked
        Fast fail
    end note
    
    note right of HalfOpen
        Test request allowed
        Determine health
    end note
```

## Deployment Architecture

```mermaid
graph TB
    subgraph Railway["Railway Platform"]
        subgraph MainService["Main Service"]
            API["API Gateway"]
            Router["Event Router"]
            Queue["Task Queue"]
            Health["Health Service"]
        end
        
        subgraph AgentServices["Agent Workers"]
            Worker1["Ögedei Worker"]
            Worker2["Temüjin Worker"]
            Worker3["Kublai Worker"]
            WorkerN["Sub-agent Workers"]
        end
        
        subgraph DataLayer["Data Layer"]
            Neo4j[(Neo4j Aura)]
            Redis[(Redis/Valkey)]
        end
    end
    
    subgraph External["External Services"]
        NotionAPI["Notion API"]
        DiscordAPI["Discord Gateway"]
        GitHubAPI["GitHub API"]
        OpenAI["OpenAI API"]
    end
    
    subgraph Monitoring["Monitoring"]
        Datadog["Datadog / Grafana"]
        PagerDuty["PagerDuty"]
    end

    API --> Router
    Router --> Queue
    Queue --> Worker1
    Queue --> Worker2
    Queue --> Worker3
    Queue --> WorkerN
    
    Health --> Worker1
    Health --> Worker2
    Health --> Worker3
    Health --> WorkerN
    
    Router --> NotionAPI
    Router --> DiscordAPI
    Router --> GitHubAPI
    
    Worker1 --> Neo4j
    Worker2 --> Neo4j
    Queue --> Redis
    
    Worker3 --> OpenAI
    
    Health --> Datadog
    Health --> PagerDuty
```

## Data Flow Summary

```mermaid
flowchart LR
    subgraph Inputs["Inputs"]
        N[Notion Tasks]
        D[Discord Messages]
        G[GitHub Events]
        S[System Events]
    end
    
    subgraph Processing["Processing"]
        R[Event Router]
        Q[Priority Queue]
        M[Memory Service]
    end
    
    subgraph Execution["Execution"]
        A1[Ögedei]
        A2[Temüjin]
        A3[Kublai]
    end
    
    subgraph Outputs["Outputs"]
        O1[Task Completion]
        O2[Contextual Responses]
        O3[Documentation Updates]
        O4[Alerts]
    end
    
    N --> R
    D --> R
    G --> R
    S --> R
    
    R --> Q
    R --> M
    
    Q --> A1
    Q --> A2
    Q --> A3
    
    M -.->|Context| A1
    M -.->|Context| A2
    M -.->|Context| A3
    
    A1 --> O1
    A1 --> O4
    A2 --> O3
    A3 --> O2
    
    A1 -.->|Updates| M
    A2 -.->|Updates| M
    A3 -.->|Updates| M
```
