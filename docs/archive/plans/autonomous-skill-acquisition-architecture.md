# Autonomous Skill Acquisition - System Architecture Diagrams

## 1. Complete Learning Loop Architecture

```mermaid
graph TB
    subgraph "Task Execution"
        A[User Request] --> B[Kublai Analyzes Task]
        B --> C{Skills Available?}
        C -->|Yes| D[Execute Skill]
        C -->|No| E[Create Learning Task]
    end

    subgraph "Phase 1: Research (Mongke)"
        E --> F[Web Search & Documentation]
        F --> G[Compare Providers/Options]
        G --> H[Document Requirements]
        H --> I[Research Complete]
    end

    subgraph "Phase 2: Practice (Temujin)"
        I --> J[Sandbox Environment]
        J --> K[Attempt 1: Test Call]
        K --> L{Success?}
        L -->|Yes| M[Record Success]
        L -->|No| N[Analyze Error]
        N --> O[Adjust Approach]
        O --> P[Attempt N: Retry]
        P --> L
        M --> Q{Threshold Met?}
        Q -->|No| K
        Q -->|Yes| R[Practice Complete]
    end

    subgraph "Phase 3: Validation (Jochi)"
        R --> S[Generate Test Suite]
        S --> T[Run Validation Tests]
        T --> U[Calculate Mastery Score]
        U --> V{Score >= 0.85?}
        V -->|Yes| W[Skill Mastered]
        V -->|No| X[More Practice Needed]
        X --> J
    end

    subgraph "Phase 4: Storage (Neo4j)"
        W --> Y[Create Skill Node]
        Y --> Z[Associate with Agents]
        Z --> AA[Store Dependencies]
        AA --> AB[Available for Use]
    end

    subgraph "Execution"
        AB --> D
        D --> AC[Complete User Request]
    end

    style A fill:#e1f5ff
    style W fill:#c8e6c9
    style AB fill:#c8e6c9
    style E fill:#fff9c4
```

## 2. Neo4j Skill Schema

```mermaid
graph LR
    subgraph "Core Nodes"
        SKILL[Skill]
        RESEARCH[SkillResearch]
        PRACTICE[SkillPracticeAttempt]
        VALIDATION[SkillValidation]
        ERROR[SkillErrorPattern]
        AGENT[Agent]
        TASK[Task]
    end

    subgraph "Relationships"
        AGENT -->|KNOWS| SKILL
        AGENT -->|CAN_USE| SKILL
        AGENT -->|RESEARCHED| RESEARCH
        AGENT -->|PRACTICED| PRACTICE
        AGENT -->|VALIDATED| VALIDATION
        TASK -->|REQUIRES_SKILL| SKILL
        SKILL -->|HAS_ERROR_PATTERN| ERROR
        RESEARCH -->|ENABLES| SKILL
        PRACTICE -->|IMPROVES| SKILL
        VALIDATION -->|CONFIRMS| SKILL
        SKILL -->|REQUIRES| SKILL
    end

    style SKILL fill:#4caf50,color:#fff
    style AGENT fill:#2196f3,color:#fff
    style TASK fill:#ff9800,color:#fff
```

## 3. Agent Roles in Skill Learning

```mermaid
graph TB
    subgraph "Kublai (Orchestrator)"
        K1[Detect Skill Gap]
        K2[Create Learning Task]
        K3[Coordinate Agents]
        K4[Validate Complete]
    end

    subgraph "Mongke (Researcher)"
        M1[Web Search APIs]
        M2[Compare Providers]
        M3[Document Findings]
    end

    subgraph "Temujin (Developer)"
        T1[Implement Skill]
        T2[Practice in Sandbox]
        T3[Debug Errors]
    end

    subgraph "Jochi (Analyst)"
        J1[Design Test Suite]
        J2[Run Validation]
        J3[Score Mastery]
    end

    subgraph "Ogedei (Ops)"
        O1[Monitor Costs]
        O2[Schedule Learning]
        O3[Resource Limits]
    end

    subgraph "Chagatai (Writer)"
        C1[Document Skill]
        C2[Create Examples]
        C3[Share Knowledge]
    end

    K2 --> M1
    M3 --> T1
    T3 --> J1
    J3 --> K4
    K4 --> C1

    style K1 fill:#9c27b0,color:#fff
    style M1 fill:#4caf50,color:#fff
    style T1 fill:#2196f3,color:#fff
    style J1 fill:#ff9800,color:#fff
    style O1 fill:#f44336,color:#fff
    style C1 fill:#00bcd4,color:#fff
```

## 4. Safety Guardrails

```mermaid
graph TB
    subgraph "Pre-Execution Checks"
        A1[Skill Mastered?]
        A2[Secrets Available?]
        A3[Cost Limit OK?]
        A4[Validation Current?]
    end

    subgraph "Execution Safeguards"
        B1[Sandbox Mode]
        B2[Cost Tracking]
        B3[Attempt Limits]
        B4[Timeout Protection]
    end

    subgraph "Post-Execution"
        C1[Sanitize Output]
        C2[Record Result]
        C3[Check Errors]
        C4[Update Statistics]
    end

    subgraph "Emergency Stops"
        D1[Cost Limit Exceeded]
        D2[Too Many Failures]
        D3[Secret Leaked]
        D4[Learning Loop Detected]
    end

    A1 -->|No| STOP[Block Execution]
    A2 -->|No| STOP
    A3 -->|No| STOP
    A4 -->|No| STOP

    A1 -->|Yes| B1
    B1 --> B2
    B2 --> B3
    B3 --> B4

    B4 --> C1
    C1 --> C2
    C2 --> C3
    C3 --> C4

    B2 -->|Limit Exceeded| D1
    B3 -->|Failures > N| D2
    C1 -->|Secret Detected| D3
    C3 -->|Loop Detected| D4

    D1 --> STOP
    D2 --> STOP
    D3 --> STOP
    D4 --> STOP

    style STOP fill:#f44336,color:#fff
    style A1 fill:#fff9c4
    style B1 fill:#e1f5ff
    style C1 fill:#c8e6c9
```

## 5. Skill Lifecycle State Machine

```mermaid
stateDiagram-v2
    [*] --> researching: Gap Detected
    researching --> practicing: Research Complete
    researching --> [*]: Research Failed

    practicing --> practicing: More Attempts Needed
    practicing --> validating: Practice Threshold Met
    practicing --> [*]: Practice Failed

    validating --> mastered: Score >= 0.85
    validating --> practicing: Score < 0.85
    validating --> [*]: Validation Failed

    mastered --> mastered: In Use
    mastered --> degraded: API Changed
    mastered --> deprecated: Obsolete

    degraded --> validating: Re-validation
    degraded --> [*]: Cannot Fix

    deprecated --> [*]
```

## 6. Example: Learning to Call Someone

```mermaid
sequenceDiagram
    participant User
    participant Kublai
    participant Mongke
    participant Temujin
    participant Jochi
    participant Neo4j
    participant TwilioAPI

    User->>Kublai: "Call Sarah about meeting"
    Kublai->>Kublai: Parse intent: voice_call needed
    Kublai->>Neo4j: Check for voice_call skill
    Neo4j-->>Kublai: Skill not found

    Kublai->>Mongke: Research voice call APIs
    Mongke->>Mongke: Web search, compare providers
    Mongke->>Neo4j: Store research (Twilio recommended)
    Mongke-->>Kublai: Research complete

    Kublai->>Temujin: Implement and practice
    Temujin->>TwilioAPI: Test call 1 (sandbox)
    TwilioAPI-->>Temujin: SUCCESS
    Temujin->>TwilioAPI: Test call 2 (invalid number)
    TwilioAPI-->>Temujin: ERROR (learned pattern)
    Temujin->>TwilioAPI: Test call 3-5
    Temujin->>Neo4j: Store practice results
    Temujin-->>Kublai: Practice complete

    Kublai->>Jochi: Validate skill
    Jochi->>Jochi: Run test suite (10 tests)
    Jochi->>Neo4j: Store validation (score: 0.91)
    Jochi-->>Kublai: Skill mastered

    Kublai->>Neo4j: Mark skill as mastered
    Kublai->>Temujin: Execute voice_call skill
    Temujin->>TwilioAPI: Call Sarah
    TwilioAPI-->>User: Phone rings
    Temujin-->>Kublai: Call complete
    Kublai-->>User: "Called Sarah, call connected"
```

## 7. Cost Monitoring Architecture

```mermaid
graph TB
    subgraph "Cost Tracking"
        A[Skill Execution] --> B[Track Cost]
        B --> C{Session Total > Limit?}
        C -->|No| D[Continue]
        C -->|Yes| E[Alert Kublai]
        E --> F{Total > Hard Limit?}
        F -->|No| D
        F -->|Yes| G[Stop Execution]
    end

    subgraph "Per-Agent Limits"
        H[Daily Limit: $10]
        I[Per-Skill Limit: $5]
        J[Per-Session Limit: $1]
    end

    subgraph "Aggregate Monitoring"
        K[Total Cost by Agent]
        L[Total Cost by Skill]
        M[Total Cost by Day]
    end

    D --> K
    D --> L
    D --> M

    H --> C
    I --> C
    J --> C

    style G fill:#f44336,color:#fff
    style E fill:#fff9c4
    style D fill:#c8e6c9
```
