# SHIELD.md - Operational Policies for Kurultai

**SHIELD** = **S**ecurity **H**ealth **I**ntegrity **E**fficiency **L**imits **D**efinitions

This document defines the operational policies that govern the Kurultai multi-agent system.
All proposals, implementations, and system changes must be validated against these policies.

---

## 1. Security Policies

### S1.1: No Secrets in Code
- **Policy**: No API keys, passwords, tokens, or secrets may be hardcoded in source code
- **Enforcement**: Pre-commit hooks, static analysis
- **Exception Process**: Security team approval required

### S1.2: Input Validation
- **Policy**: All user inputs must be validated and sanitized
- **Requirements**:
  - Phone numbers: E.164 format validation
  - Email: RFC 5322 compliance
  - API payloads: Schema validation
  - File uploads: Type and size limits

### S1.3: Rate Limiting
- **Policy**: All external-facing endpoints must have rate limiting
- **Defaults**:
  - API endpoints: 100 requests/minute per user
  - Signal messages: 50 messages/minute per sender
  - Task creation: 1000 tasks/hour per sender

### S1.4: Authentication
- **Policy**: All administrative actions require authentication
- **Methods**:
  - Web UI: Authentik SSO with WebAuthn
  - API: Token-based authentication
  - Inter-agent: HMAC-SHA256 message signing

### S1.5: Data Encryption
- **Policy**: Sensitive data must be encrypted at rest and in transit
- **Requirements**:
  - Neo4j: Use encrypted connection (bolt+s://)
  - Signal: E2E encryption via Signal Protocol
  - Backups: Encrypted with AES-256

---

## 2. Health Policies

### H2.1: Agent Heartbeats
- **Policy**: All agents must report heartbeat every 5 minutes
- **Failure Handling**:
  - > 10 min: Warning logged
  - > 30 min: Agent marked stale
  - > 60 min: Automatic task reassignment

### H2.2: Database Connectivity
- **Policy**: System must maintain Neo4j connection
- **Retry Logic**: Exponential backoff, max 5 retries
- **Circuit Breaker**: Open after 3 consecutive failures

### H2.3: Disk Space
- **Policy**: Minimum 20% free disk space required
- **Monitoring**: Checked every 15 minutes
- **Alert Threshold**: < 25% free space triggers warning

### H2.4: Memory Usage
- **Policy**: Container memory usage should not exceed 80%
- **Action**: OOM events trigger automatic restart

---

## 3. Integrity Policies

### I3.1: Schema Validation
- **Policy**: All Neo4j schema changes require migration files
- **Requirements**:
  - Up migrations must be idempotent
  - Down migrations must be provided
  - Migration version numbers are sequential

### I3.2: Data Consistency
- **Policy**: Orphaned nodes must not persist > 24 hours
- **Enforcement**: Deep curation task runs every 6 hours
- **Exception**: Agent nodes may be orphaned intentionally

### I3.3: Task State Management
- **Policy**: Task status transitions must be valid
- **Allowed Transitions**:
  - pending → ready → in_progress → completed
  - pending → ready → in_progress → failed → escalated
  - Any status → blocked (manual override)

### I3.4: File Consistency
- **Policy**: All agent SOUL.md files must exist and be valid
- **Validation**: Checked every 15 minutes
- **Required Files**:
  - `/data/workspace/souls/main/SOUL.md`
  - `/data/workspace/souls/researcher/SOUL.md`
  - `/data/workspace/souls/developer/SOUL.md`
  - `/data/workspace/souls/analyst/SOUL.md`
  - `/data/workspace/souls/writer/SOUL.md`
  - `/data/workspace/souls/ops/SOUL.md`

---

## 4. Efficiency Policies

### E4.1: Token Budgets
- **Policy**: All automated tasks have token budgets
- **Limits**:
  - 5-minute tasks: ≤ 500 tokens
  - 15-minute tasks: ≤ 1000 tokens
  - Hourly tasks: ≤ 2000 tokens
  - Daily tasks: ≤ 5000 tokens

### E4.2: Task Prioritization
- **Policy**: High-priority tasks must be processed first
- **Weight Calculation**:
  - Base priority: 0.0 - 1.0
  - User override: +0.5
  - Age decay: -0.1 per day
  - Dependency bonus: +0.1 per dependent task

### E4.3: Resource Limits
- **Policy**: Tasks must complete within resource limits
- **Defaults**:
  - CPU: 30 seconds per task
  - Memory: 512MB per sandbox
  - File descriptors: 100 per task

### E4.4: Parallelization
- **Policy**: Independent tasks should run in parallel
- **Max Concurrent**: 10 tasks per agent
- **Dependency Resolution**: DAG-based scheduling

---

## 5. Limits Policies

### L5.1: Task Limits
- **Policy**: Per-sender task limits enforced
- **Limits**:
  - Max pending per sender: 100
  - Max total system tasks: 1000
  - Max task age: 30 days (auto-archive)

### L5.2: Storage Limits
- **Policy**: Neo4j storage limits based on tier
- **Free Tier (AuraDB)**:
  - Max nodes: 200,000
  - Max relationships: 440,000
  - Max storage: 8GB

### L5.3: API Rate Limits
- **Policy**: External API calls are rate-limited
- **Limits**:
  - Anthropic: 4000 requests/minute
  - Notion: 3 requests/second
  - Neo4j: 1000 queries/second

### L5.4: Message Size
- **Policy**: Message content has size limits
- **Limits**:
  - Signal messages: 4000 characters
  - Task descriptions: 10,000 characters
  - Research content: 100,000 characters

---

## 6. Definitions

### D6.1: Agent Roles
| Agent | Role | Responsibilities |
|-------|------|------------------|
| Kublai | Main | Delegation, synthesis, user communication |
| Möngke | Researcher | Research, documentation, knowledge gaps |
| Temüjin | Developer | Code implementation, testing, validation |
| Jochi | Analyst | Analysis, metrics, monitoring, curation |
| Chagatai | Writer | Content creation, documentation, reflection |
| Ögedei | Ops | Infrastructure, security, scheduling |

### D6.2: Task Statuses
| Status | Meaning | Next States |
|--------|---------|-------------|
| pending | Awaiting assignment | ready, blocked |
| ready | Dependencies met, ready to run | in_progress, blocked |
| in_progress | Currently being executed | completed, failed, blocked |
| completed | Successfully finished | (terminal) |
| failed | Execution failed | escalated, pending (retry) |
| blocked | Cannot proceed | pending (unblock) |
| escalated | Requires manual intervention | pending, completed |

### D6.3: Severity Levels
| Level | Criteria | Response Time |
|-------|----------|---------------|
| critical | System outage, data loss | Immediate |
| high | Major feature broken | 1 hour |
| medium | Degraded performance | 4 hours |
| low | Cosmetic issues | 24 hours |

### D6.4: Resource Tiers
| Tier | Memory | CPU | Use Case |
|------|--------|-----|----------|
| small | 256MB | 0.5 | Quick tasks, health checks |
| medium | 512MB | 1.0 | Standard tasks |
| large | 1GB | 2.0 | Complex analysis |
| xlarge | 2GB | 4.0 | Heavy computation |

---

## 7. Proposal Vetting Criteria

### V7.1: Architecture Proposals
Proposals must be evaluated against:
1. **Security**: Does it comply with S1.x policies?
2. **Health**: Will it impact system health (H2.x)?
3. **Integrity**: Does it maintain data integrity (I3.x)?
4. **Efficiency**: Is it within token/resource budgets (E4.x)?
5. **Limits**: Does it respect system limits (L5.x)?

### V7.2: Approval Requirements
- **Auto-approve**: Low risk, within all budgets, no schema changes
- **Ögedei Review**: Medium risk, token budget > 1000, schema changes
- **Full Review**: High risk, security implications, new external dependencies

### V7.3: Rejection Criteria
Proposals must be rejected if they:
- Violate security policies (S1.x)
- Exceed hard resource limits (L5.x)
- Lack rollback plan
- Have no validation criteria
- Introduce circular dependencies

---

## 8. Compliance Verification

### C8.1: Automated Checks
- Pre-commit: Static analysis, secret scanning
- CI/CD: Unit tests, integration tests
- Deployment: Health checks, smoke tests

### C8.2: Audit Trail
All policy violations must be logged:
```cypher
CREATE (pv:PolicyViolation {
    id: randomUUID(),
    policy: 'S1.1',
    description: 'Secret found in commit',
    detected_at: datetime(),
    severity: 'critical'
})
```

### C8.3: Review Cadence
- Policies reviewed: Quarterly
- Metrics reviewed: Weekly
- Incidents reviewed: Within 24 hours

---

*Document Version: 1.0*
*Last Updated: 2026-02-09*
*Owner: Ögedei (Ops Agent)*
