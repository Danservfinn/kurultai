# Sensitive Data Isolation Architecture for Kurultai/OpenClaw

## Executive Summary

This document presents a comprehensive backend architecture for isolating sensitive data (passwords, PII, financial data, API keys) in a separate Neo4j database within the 6-agent Kurultai/OpenClaw system. The architecture provides defense-in-depth security while maintaining real-time access patterns through the Kublai orchestrator.

## Current State Analysis

### Existing Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    CURRENT SINGLE-DATABASE                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌─────────────┐                                               │
│   │   Kublai    │◀── Router/Orchestrator                       │
│   │   (main)    │                                               │
│   └──────┬──────┘                                               │
│          │                                                       │
│   ┌──────┴──────┬────────┬────────┬────────┐                   │
│   ↓             ↓        ↓        ↓        ↓                   │
│ Möngke      Chagatai  Temüjin   Jochi   Ögedei                │
│(Research)    (Write)   (Dev)   (Analyze)  (Ops)               │
│   └─────────────┴────────┴────────┴────────┘                   │
│          │                                                       │
│          ▼                                                       │
│   ┌─────────────┐                                               │
│   │   Neo4j     │◀── Single instance (bolt://localhost:7687)   │
│   │  (neo4j)    │    Stores: tasks, notifications, knowledge   │
│   └─────────────┘                                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Current Security Measures

The existing system already implements several privacy controls:

1. **Privacy Boundary Framework** (`tools/security/privacy_boundary.py`)
   - Data classification: PUBLIC, OPERATIONAL, SENSITIVE, PRIVATE
   - Storage location determination (Neo4j vs file-based)
   - Pre-storage validation checklist

2. **Tokenization Service** (`tools/security/tokenization.py`)
   - Reversible tokenization for sensitive values
   - Token vault with TTL and access tracking
   - Batch tokenization for text

3. **Field-Level Encryption** (`tools/security/encryption.py`)
   - AES-256-GCM encryption for sensitive properties
   - Deterministic encryption for queryable fields
   - Key rotation support

4. **Access Control** (`tools/security/access_control.py`)
   - Role-based permissions per agent
   - Sender isolation enforcement
   - Audit logging

### Gaps in Current Architecture

1. **Single Database Risk**: All data in one Neo4j instance
2. **No Physical Separation**: Sensitive data shares infrastructure with operational data
3. **Limited Compartmentalization**: Breach of operational DB exposes token vault references
4. **No Database-Level Access Control**: Relies solely on application-layer controls

---

## Proposed Architecture: Two-Database Pattern with Secure Vault

### High-Level Design

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PROPOSED MULTI-DATABASE ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                         KUBLAI ORCHESTRATOR                          │   │
│   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │   │
│   │  │   Sanitizer  │  │   Gateway    │  │   Circuit    │              │   │
│   │  │   Service    │  │   Service    │  │   Breaker    │              │   │
│   │  └──────────────┘  └──────────────┘  └──────────────┘              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│           ┌────────────────────────┼────────────────────────┐                │
│           │                        │                        │                │
│           ▼                        ▼                        ▼                │
│   ┌───────────────┐       ┌───────────────┐       ┌─────────────────┐       │
│   │   Neo4j       │       │   Neo4j       │       │   Token Vault   │       │
│   │  Operational  │       │   Secure      │       │   (Redis/HSM)   │       │
│   │   (neo4j)     │       │  (neo4j-vault)│       │                 │       │
│   ├───────────────┤       ├───────────────┤       ├─────────────────┤       │
│   │ • Tasks       │       │ • PII         │       │ • Token maps    │       │
│   │ • Knowledge   │       │ • Passwords   │       │ • API keys      │       │
│   │ • Concepts    │       │ • Financial   │       │ • Credentials   │       │
│   │ • Reflections │       │ • Credentials │       │ • Session data  │       │
│   │ • Audit logs  │       │ • Encrypted   │       │ • TTL mgmt      │       │
│   │               │       │   embeddings  │       │                 │       │
│   │ Tokens: TKN:  │◀─────▶│ References:   │◀─────▶│ Encryption keys │       │
│   │ xxx           │       │ SEC:xxx       │       │ (separate)      │       │
│   └───────────────┘       └───────────────┘       └─────────────────┘       │
│                                                                              │
│   Connection: bolt://      Connection: bolt+s://     Connection: rediss://  │
│   (internal network)       (mTLS + cert auth)       (TLS + AUTH)            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Architecture Patterns Explored

### Pattern 1: Two-Database Approach (Recommended)

**Design**: Separate Neo4j instances for operational and sensitive data.

```
┌─────────────────────────────────────────────────────────────────┐
│                    TWO-DATABASE PATTERN                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Operational DB (neo4j)          Secure DB (neo4j-secure)      │
│   ┌─────────────────────┐         ┌─────────────────────┐       │
│   │  Tasks              │         │  SensitiveRecords   │       │
│   │  - id               │         │  - id               │       │
│   │  - description      │         │  - record_type      │       │
│   │  - status           │         │  - encrypted_data   │       │
│   │  - assigned_to      │         │  - access_tier      │       │
│   │  - sender_hash      │         │  - allowed_agents   │       │
│   │                     │         │  - audit_log        │       │
│   │  Concepts           │         │                     │       │
│   │  - name             │         │  AccessLogs         │       │
│   │  - embedding        │◀───────▶│  - agent_id         │       │
│   │  - sender_hash      │  ref    │  - action           │       │
│   │                     │         │  - timestamp        │       │
│   └─────────────────────┘         └─────────────────────┘       │
│                                                                  │
│   Cross-DB Reference Pattern:                                    │
│   Operational.task.sensitive_ref ──▶ Secure.record.id           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Pros**:
- Physical isolation of sensitive data
- Independent scaling and backup strategies
- Different security profiles (mTLS for secure DB)
- Clear compliance boundaries (PCI-DSS, HIPAA)

**Cons**:
- Cross-database query complexity
- Transaction coordination challenges
- Higher operational overhead

**Trade-off Analysis**:
| Factor | Impact | Mitigation |
|--------|--------|------------|
| Complexity | High | Gateway service abstracts cross-DB operations |
| Performance | Medium | Async operations + caching layer |
| Security | High | Defense in depth justifies overhead |
| Cost | Medium | Smaller secure DB instance (less data) |

---

### Pattern 2: API Gateway/Proxy Pattern

**Design**: Centralized access control through a gateway service.

```
┌─────────────────────────────────────────────────────────────────┐
│                    API GATEWAY PATTERN                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│                         ┌─────────────┐                         │
│                         │   Kublai    │                         │
│                         └──────┬──────┘                         │
│                                │                                │
│                    ┌───────────┴───────────┐                    │
│                    ▼                       ▼                    │
│            ┌──────────────┐       ┌──────────────┐              │
│            │   Secure     │       │  Operational │              │
│            │   Gateway    │       │   Gateway    │              │
│            │   Service    │       │   Service    │              │
│            └──────┬───────┘       └──────┬───────┘              │
│                   │                      │                       │
│                   ▼                      ▼                       │
│            ┌──────────┐           ┌──────────┐                   │
│            │  Neo4j   │           │  Neo4j   │                   │
│            │ (secure) │           │   (op)   │                   │
│            └──────────┘           └──────────┘                   │
│                                                                  │
│   Gateway Responsibilities:                                      │
│   • Authentication/Authorization                                 │
│   • Rate limiting per agent                                      │
│   • Request/response sanitization                                │
│   • Audit logging                                                │
│   • Circuit breaker for DB failures                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Pros**:
- Centralized security policy enforcement
- Single point for audit logging
- Can implement complex access rules
- Easier to add new data sources

**Cons**:
- Additional latency (hop through gateway)
- Gateway becomes single point of failure
- Requires careful capacity planning

---

### Pattern 3: Event-Driven Sync Between Databases

**Design**: Async replication using event streaming for cross-DB consistency.

```
┌─────────────────────────────────────────────────────────────────┐
│                    EVENT-DRIVEN SYNC PATTERN                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌─────────────┐    Events      ┌─────────────┐                │
│   │  Neo4j      │───────────────▶│  Event      │                │
│   │ Operational │   (change)     │  Stream     │                │
│   │             │                │  (Kafka/    │                │
│   │             │◀───────────────│   Redis)    │                │
│   └─────────────┘    Sync ack    └──────┬──────┘                │
│                                         │                        │
│                                         │ Events                 │
│                                         ▼                        │
│                                  ┌─────────────┐                 │
│                                  │  Secure DB  │                 │
│                                  │  Sync       │                 │
│                                  │  Consumer   │                 │
│                                  └──────┬──────┘                 │
│                                         │                        │
│                                         ▼                        │
│                                  ┌─────────────┐                 │
│                                  │  Neo4j      │                 │
│                                  │  Secure     │                 │
│                                  └─────────────┘                 │
│                                                                  │
│   Event Types:                                                   │
│   • SensitiveDataStored {record_id, access_tier, allowed_agents} │
│   • SensitiveDataAccessed {record_id, agent_id, timestamp}       │
│   • SensitiveDataDeleted {record_id, reason}                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Pros**:
- Loose coupling between databases
- Natural audit trail from event log
- Can replay events for recovery
- Scalable async processing

**Cons**:
- Eventual consistency (not immediate)
- Complexity of event handling
- Need for dead letter queues
- Schema evolution challenges

**Best For**: Audit logging, analytics, non-critical sync operations

---

### Pattern 4: CQRS Pattern for Read/Write Separation

**Design**: Separate read and write models with different storage optimizations.

```
┌─────────────────────────────────────────────────────────────────┐
│                    CQRS PATTERN                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Write Path (Commands)                                          │
│   ┌─────────┐    ┌─────────┐    ┌─────────────────────────┐     │
│   │ Agent   │───▶│ Kublai  │───▶│   Sanitization Service  │     │
│   │ Request │    │ Router  │    │   (PII detection)       │     │
│   └─────────┘    └─────────┘    └───────────┬─────────────┘     │
│                                             │                    │
│                              ┌──────────────┼──────────────┐    │
│                              ▼              ▼              ▼    │
│                        ┌─────────┐    ┌─────────┐    ┌────────┐ │
│                        │ Neo4j   │    │ Neo4j   │    │ Token  │ │
│                        │   Op    │    │ Secure  │    │ Vault  │ │
│                        │ (Write) │    │ (Write) │    │        │ │
│                        └────┬────┘    └────┬────┘    └───┬────┘ │
│                             │              │             │      │
│                             └──────────────┴─────────────┘      │
│                                            │                    │
│   Read Path (Queries)                      ▼ Events              │
│   ┌─────────┐    ┌─────────┐    ┌─────────────────────────┐     │
│   │ Agent   │◀───│  Read   │◀───│   Read Model Projections│     │
│   │ Query   │    │ Service │    │   (denormalized views)  │     │
│   └─────────┘    └─────────┘    └─────────────────────────┘     │
│                                                                  │
│   Read Models:                                                   │
│   • TaskSummary (no sensitive data)                              │
│   • AgentContext (tokenized references)                          │
│   • AuditTrail (aggregated access logs)                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Pros**:
- Optimized read models for different access patterns
- Clear separation of concerns
- Can scale read and write independently
- Natural fit for event sourcing

**Cons**:
- Higher complexity
- Data consistency challenges
- More infrastructure to maintain

**Best For**: High-read scenarios with complex query patterns

---

## Recommended Architecture: Hybrid Two-Database with Gateway

### Overview

Combine Pattern 1 (Two-Database) with Pattern 2 (Gateway) for optimal security and usability:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RECOMMENDED HYBRID ARCHITECTURE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   LAYER 1: AGENTS                                                            │
│   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐              │
│   │ Kublai  │ │ Möngke  │ │Chagatai │ │ Temüjin │ │  Jochi  │  Ögedei      │
│   │ (main)  │ │(research│ │ (writer)│ │  (dev)  │ │(analyst)│  (ops)       │
│   └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘              │
│        │           │           │           │           │                   │
│   LAYER 2: API GATEWAY (Kong/Envoy/custom)                                   │
│        │           │           │           │           │                   │
│        └───────────┴───────────┴─────┬─────┴───────────┘                   │
│                                      │                                       │
│                              ┌───────┴───────┐                              │
│                              ▼               ▼                              │
│   LAYER 3: DATA ACCESS SERVICES                                             │
│                    ┌─────────────┐   ┌─────────────┐                        │
│                    │  Secure     │   │ Operational │                        │
│                    │  Service    │   │  Service    │                        │
│                    │  (vault)    │   │   (core)    │                        │
│                    └──────┬──────┘   └──────┬──────┘                        │
│                           │                  │                              │
│   LAYER 4: DATA STORES                                                      │
│                           ▼                  ▼                              │
│                    ┌──────────┐       ┌──────────┐                          │
│                    │ Neo4j    │       │ Neo4j    │                          │
│                    │ Secure   │       │ Core     │                          │
│                    │ (bolt+s) │       │ (bolt)   │                          │
│                    └────┬─────┘       └────┬─────┘                          │
│                         │                  │                                │
│                         └────────┬─────────┘                                │
│                                  ▼                                          │
│                           ┌──────────┐                                      │
│                           │  Redis   │                                      │
│                           │  Token   │                                      │
│                           │  Vault   │                                      │
│                           └──────────┘                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow Architecture

### 1. Sensitive Data Entry Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SENSITIVE DATA ENTRY FLOW                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Step 1: Detection                                                          │
│   ┌─────────┐                                                                │
│   │  User   │─── "My password is Secret123 and my SSN is 123-45-6789"       │
│   │ Message │                                                                │
│   └────┬────┘                                                                │
│        │                                                                     │
│        ▼                                                                     │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │                    SANITIZATION PIPELINE                         │       │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │       │
│   │  │   Regex     │─▶│    LLM      │─▶│ Classification│            │       │
│   │  │   Scanner   │  │   Review    │  │   Engine      │            │       │
│   │  └─────────────┘  └─────────────┘  └─────────────┘             │       │
│   │        │                 │                 │                    │       │
│   │        ▼                 ▼                 ▼                    │       │
│   │  Password detected   Confirmed PII    SENSITIVE tier            │       │
│   │  SSN pattern match   Health context   classification            │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│        │                                                                     │
│        ▼                                                                     │
│   Step 2: Extraction & Tokenization                                          │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │  Original: "My password is Secret123 and my SSN is 123-45-6789" │       │
│   │                                                                 │       │
│   │  Sanitized: "My password is [PASSWORD] and my SSN is [SSN]"     │       │
│   │                                                                 │       │
│   │  Token Map:                                                     │       │
│   │    [PASSWORD] ──▶ TKN:PASSWORD:a1b2c3d4 ──▶ "Secret123"         │       │
│   │    [SSN] ───────▶ TKN:SSN:e5f6g7h8 ───────▶ "123-45-6789"       │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│        │                                                                     │
│        ▼                                                                     │
│   Step 3: Storage                                                            │
│   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│   │  Neo4j Core     │    │  Neo4j Secure   │    │  Token Vault    │         │
│   │                 │    │                 │    │                 │         │
│   │  Message {      │    │  SensitiveRecord│    │  TKN:PASSWORD   │         │
│   │    content:     │    │  {              │    │    value:       │         │
│   │    "password    │◀───│    id: "sec-1", │    │    "Secret123"  │         │
│   │    is [PWD]"    │ref │    type: "pwd", │    │    expires:...  │         │
│   │    sender_hash  │    │    encrypted:   │    │                 │         │
│   │  }              │    │    "ENC:...",   │    │  TKN:SSN        │         │
│   │                 │    │    core_ref:    │    │    value:       │         │
│   │                 │    │    "msg-123"    │    │    "123-45..."  │         │
│   │                 │    │  }              │    │                 │         │
│   └─────────────────┘    └─────────────────┘    └─────────────────┘         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2. Sensitive Data Retrieval Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SENSITIVE DATA RETRIEVAL FLOW                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Step 1: Request                                                            │
│   ┌─────────┐                                                                │
│   │  Agent  │─── "Retrieve context for user ABC123"                         │
│   │  Query  │                                                                │
│   └────┬────┘                                                                │
│        │                                                                     │
│        ▼                                                                     │
│   Step 2: Authorization Check                                                │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │  RBAC Check: Does agent have permission?                        │       │
│   │  • Agent role: "researcher"                                     │       │
│   │  • Required: "sensitive:read"                                   │       │
│   │  • Result: DENIED (researcher cannot access passwords)          │       │
│   │                                                                 │       │
│   │  Alternative:                                                   │       │
│   │  • Agent role: "main" (Kublai)                                  │       │
│   │  • Required: "sensitive:read"                                   │       │
│   │  • Result: ALLOWED with audit logging                           │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│        │                                                                     │
│        ▼                                                                     │
│   Step 3: Fetch from Secure DB                                               │
│   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│   │  Neo4j Core     │    │  Neo4j Secure   │    │  Token Vault    │         │
│   │                 │    │                 │    │                 │         │
│   │  Message {      │───▶│  SensitiveRecord│───▶│  TKN:PASSWORD   │         │
│   │    id: "msg-123│ref │  {              │    │    value:       │         │
│   │    content:     │    │    id: "sec-1", │    │    "Secret123"  │         │
│   │    "password    │    │    type: "pwd", │    │                 │         │
│   │    is [PWD]"    │    │    encrypted:   │    │  TKN:SSN        │         │
│   │  }              │    │    "ENC:...",   │◀───│    value:       │         │
│   │                 │    │    core_ref:    │    │    "123-45..."  │         │
│   └─────────────────┘    └─────────────────┘    └─────────────────┘         │
│        │                                                                     │
│        ▼                                                                     │
│   Step 4: Reconstruction                                                     │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │  Sanitized: "My password is [PASSWORD] and my SSN is [SSN]"     │       │
│   │                                                                 │       │
│   │  Detokenized: "My password is Secret123 and my SSN is           │       │
│   │  [REDACTED]"  (agent lacks SSN access permission)               │       │
│   │                                                                 │       │
│   │  Audit Log:                                                     │       │
│   │    { agent: "kublai", action: "sensitive_access",               │       │
│   │      records: ["sec-1"], timestamp: "..." }                     │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Performance Considerations

### 1. Query Optimization for Cross-Database Operations

**Challenge**: Joining data across two Neo4j instances.

**Solutions**:

```python
# Pattern 1: Application-Level Join (Recommended for small datasets)
async def get_enriched_context(sender_hash: str) -> Dict:
    """Fetch from both DBs and merge in application."""

    # Parallel queries to both databases
    core_task = operational_db.query("""
        MATCH (m:Message {sender_hash: $sender_hash})
        RETURN m.id as id, m.content as content
    """, sender_hash=sender_hash)

    secure_task = secure_db.query("""
        MATCH (s:SensitiveRecord {sender_hash: $sender_hash})
        RETURN s.core_ref as ref, s.type as type, s.token as token
    """, sender_hash=sender_hash)

    # Execute in parallel
    core_results, secure_results = await asyncio.gather(core_task, secure_task)

    # Merge in application layer
    enriched = {}
    for msg in core_results:
        enriched[msg['id']] = {
            'content': msg['content'],
            'sensitive': []
        }

    for sec in secure_results:
        if sec['ref'] in enriched:
            enriched[sec['ref']]['sensitive'].append({
                'type': sec['type'],
                'token': sec['token']
            })

    return enriched
```

```python
# Pattern 2: Reference-Based Lookup (Recommended for large datasets)
async def get_sensitive_for_message(message_id: str) -> List[Dict]:
    """Lazy-load sensitive data only when needed."""

    # First, check if message has sensitive references
    refs = await operational_db.query("""
        MATCH (m:Message {id: $id})
        RETURN m.has_sensitive as has_sensitive,
               m.sensitive_refs as refs
    """, id=message_id)

    if not refs or not refs[0]['has_sensitive']:
        return []

    # Fetch only referenced sensitive records
    return await secure_db.query("""
        MATCH (s:SensitiveRecord)
        WHERE s.id IN $refs
        RETURN s.type as type, s.encrypted_data as data
    """, refs=refs[0]['refs'])
```

### 2. Connection Pooling Configuration

```python
# Operational DB - Higher throughput, less security
operational_config = {
    "max_connection_pool_size": 100,
    "connection_timeout": 10,
    "max_transaction_retry_time": 30,
    "connection_acquisition_timeout": 30,
    "max_connection_lifetime": 3600,  # 1 hour
    "ssl_mode": "DISABLED"  # Internal network only
}

# Secure DB - Lower throughput, higher security
secure_config = {
    "max_connection_pool_size": 20,  # Smaller pool
    "connection_timeout": 30,
    "max_transaction_retry_time": 60,
    "connection_acquisition_timeout": 60,
    "max_connection_lifetime": 1800,  # 30 minutes (faster rotation)
    "ssl_mode": "REQUIRE",
    "ssl_context": create_secure_ssl_context()  # mTLS
}
```

### 3. Caching Strategy

**What CAN be cached**:
- Operational data (tasks, knowledge, concepts)
- Token vault metadata (not values)
- Access control decisions (short TTL)
- Query results for non-sensitive data

**What CANNOT be cached**:
- Passwords, API keys, credentials
- PII (names, addresses, phone numbers)
- Financial data
- Session tokens
- Encryption keys

```python
# Tiered caching architecture
class SecureCachingStrategy:
    """Caching strategy respecting data classification."""

    CACHE_TIERS = {
        # Public data - aggressive caching
        "PUBLIC": {"ttl": 3600, "encrypted": False},

        # Operational data - moderate caching
        "OPERATIONAL": {"ttl": 300, "encrypted": False},

        # Sensitive data - minimal caching, encrypted
        "SENSITIVE": {"ttl": 60, "encrypted": True},

        # Private data - no caching
        "PRIVATE": {"ttl": 0, "encrypted": True}
    }

    async def get_with_cache(self, key: str, data_type: str, fetch_func):
        """Get data with appropriate caching."""
        tier = self.CACHE_TIERS.get(data_type, self.CACHE_TIERS["PRIVATE"])

        if tier["ttl"] == 0:
            # No caching - fetch directly
            return await fetch_func()

        # Check cache
        cached = await self.cache.get(key)
        if cached:
            if tier["encrypted"]:
                return self.decrypt(cached)
            return cached

        # Fetch and cache
        data = await fetch_func()

        if tier["ttl"] > 0:
            value = self.encrypt(data) if tier["encrypted"] else data
            await self.cache.set(key, value, ttl=tier["ttl"])

        return data
```

---

## Failure Modes and Resilience

### 1. Secure Database Unavailable

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SECURE DB FAILURE HANDLING                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Scenario: Secure Neo4j becomes unavailable                                 │
│                                                                              │
│   ┌─────────────┐                                                            │
│   │  Request    │─── "Get user credentials"                                  │
│   └──────┬──────┘                                                            │
│          │                                                                   │
│          ▼                                                                   │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │                    CIRCUIT BREAKER PATTERN                       │       │
│   │                                                                  │       │
│   │  State: CLOSED (normal)                                          │       │
│   │  ┌─────────┐                                                     │       │
│   │  │ Attempt │─── Timeout after 5s                                  │       │
│   │  │ Secure  │                                                      │       │
│   │  │   DB    │                                                      │       │
│   │  └────┬────┘                                                      │       │
│   │       │                                                          │       │
│   │       ▼ Failure                                                    │       │
│   │  ┌─────────┐                                                     │       │
│   │  │  Retry  │─── 3 attempts with backoff                           │       │
│   │  │  Logic  │                                                      │       │
│   │  └────┬────┘                                                      │       │
│   │       │                                                          │       │
│   │       ▼ Still failing                                              │       │
│   │  ┌─────────┐     ┌─────────────┐                                 │       │
│   │  │ Circuit │────▶│ State: OPEN │                                 │       │
│   │  │ Breaker │     │ (30s timeout)│                                 │       │
│   │  └─────────┘     └──────┬──────┘                                 │       │
│   │                         │                                        │       │
│   │                         ▼                                        │       │
│   │              ┌─────────────────────┐                             │       │
│   │              │   FALLBACK MODE     │                             │       │
│   │              │                     │                             │       │
│   │              │ • Return sanitized  │                             │       │
│   │              │   data only         │                             │       │
│   │              │ • Queue sensitive   │                             │       │
│   │              │   requests for      │                             │       │
│   │              │   retry             │                             │       │
│   │              │ • Alert operations  │                             │       │
│   │              │ • Log all access    │                             │       │
│   │              │   attempts          │                             │       │
│   │              └─────────────────────┘                             │       │
│   │                                                                  │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
│   Recovery:                                                                  │
│   1. Health checks every 10s                                                 │
│   2. On success, transition to HALF-OPEN                                     │
│   3. Test request succeeds → CLOSED                                          │
│   4. Test request fails → OPEN (extended timeout)                            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Implementation**:

```python
from circuitbreaker import circuit
from enum import Enum

class SecureDBCircuit:
    """Circuit breaker for secure database access."""

    class State(Enum):
        CLOSED = "closed"       # Normal operation
        OPEN = "open"          # Failing, reject fast
        HALF_OPEN = "half_open"  # Testing recovery

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
        half_open_max_calls: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.state = self.State.CLOSED
        self.failures = 0
        self.last_failure_time = None
        self.half_open_calls = 0

    async def call(self, func, fallback_func, *args, **kwargs):
        """Execute function with circuit breaker protection."""

        if self.state == self.State.OPEN:
            if self._should_attempt_reset():
                self.state = self.State.HALF_OPEN
                self.half_open_calls = 0
            else:
                # Circuit open - use fallback
                return await fallback_func(*args, **kwargs)

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            if self.state == self.State.OPEN:
                return await fallback_func(*args, **kwargs)
            raise

    def _on_success(self):
        """Handle successful call."""
        if self.state == self.State.HALF_OPEN:
            self.half_open_calls += 1
            if self.half_open_calls >= self.half_open_max_calls:
                # Recovery confirmed
                self.state = self.State.CLOSED
                self.failures = 0
        else:
            self.failures = max(0, self.failures - 1)

    def _on_failure(self):
        """Handle failed call."""
        self.failures += 1
        self.last_failure_time = time.time()

        if self.state == self.State.HALF_OPEN:
            # Recovery failed
            self.state = self.State.OPEN
        elif self.failures >= self.failure_threshold:
            self.state = self.State.OPEN

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to try recovery."""
        if self.last_failure_time is None:
            return True
        return (time.time() - self.last_failure_time) >= self.recovery_timeout
```

### 2. Fallback Strategies

```python
class SecureDBFallback:
    """Fallback strategies when secure DB is unavailable."""

    async def get_sensitive_data_fallback(
        self,
        record_type: str,
        record_id: str
    ) -> FallbackResult:
        """
        Fallback when secure DB is unavailable.

        Strategy depends on data criticality:
        - CRITICAL: Queue for later, return unavailable
        - HIGH: Return cached if available, else unavailable
        - NORMAL: Return placeholder
        """

        criticality = self._get_criticality(record_type)

        if criticality == "CRITICAL":
            # Cannot proceed without this data
            await self.queue_for_retry(record_type, record_id)
            return FallbackResult(
                success=False,
                data=None,
                message="Secure database unavailable. Request queued for retry.",
                retry_after=60
            )

        elif criticality == "HIGH":
            # Try cache (if available and not expired)
            cached = await self.stale_cache.get(record_id)
            if cached and not self._is_cache_expired(cached, max_age=300):
                return FallbackResult(
                    success=True,
                    data=cached,
                    message="Serving stale cached data",
                    stale=True
                )

            return FallbackResult(
                success=False,
                data=None,
                message="Secure database unavailable, no valid cache",
                retry_after=30
            )

        else:  # NORMAL
            return FallbackResult(
                success=True,
                data={"placeholder": True, "type": record_type},
                message="Serving placeholder data",
                placeholder=True
            )

    async def degraded_mode_response(self, agent_request: Dict) -> Dict:
        """
        Provide degraded service when secure DB is down.

        Kublai can still:
        - Route tasks to agents
        - Access operational memory
        - Respond with non-sensitive context

        Kublai cannot:
        - Access passwords/credentials
        - Retrieve PII
        - Access financial data
        """
        return {
            "status": "degraded",
            "available_services": ["task_routing", "operational_memory"],
            "unavailable_services": ["sensitive_data_access", "pii_retrieval"],
            "message": "Operating in degraded mode. Some features unavailable.",
            "estimated_recovery": self.circuit_breaker.estimated_recovery_time()
        }
```

### 3. Data Consistency During Failures

```python
class SecureDataQueue:
    """Queue for sensitive operations during outages."""

    def __init__(self, redis_client):
        self.redis = redis_client
        self.queue_key = "secure_db:pending_operations"
        self.dlq_key = "secure_db:dead_letter"

    async def enqueue_sensitive_write(
        self,
        operation: str,
        data: Dict,
        priority: int = 5
    ) -> str:
        """
        Queue a sensitive write operation for later execution.

        Returns operation ID for tracking.
        """
        operation_id = str(uuid.uuid4())

        queued_op = {
            "id": operation_id,
            "operation": operation,
            "data": self._encrypt_for_queue(data),  # Encrypt in queue
            "priority": priority,
            "enqueued_at": datetime.utcnow().isoformat(),
            "retry_count": 0,
            "max_retries": 3
        }

        # Priority queue (lower number = higher priority)
        await self.redis.zadd(
            self.queue_key,
            {json.dumps(queued_op): priority}
        )

        return operation_id

    async def process_queue(self, secure_db_client):
        """Process queued operations when DB recovers."""

        while True:
            # Get highest priority operation
            result = await self.redis.zpopmin(self.queue_key)
            if not result:
                break

            op = json.loads(result[0][0])

            try:
                # Decrypt and execute
                data = self._decrypt_from_queue(op["data"])
                await self._execute_operation(
                    secure_db_client,
                    op["operation"],
                    data
                )

                # Success - log completion
                logger.info(f"Queued operation {op['id']} completed")

            except Exception as e:
                # Retry or move to DLQ
                op["retry_count"] += 1
                op["last_error"] = str(e)

                if op["retry_count"] >= op["max_retries"]:
                    await self.redis.lpush(self.dlq_key, json.dumps(op))
                    logger.error(f"Operation {op['id']} moved to DLQ")
                else:
                    # Re-queue with higher priority (lower number)
                    new_priority = op["priority"] - 1
                    await self.redis.zadd(
                        self.queue_key,
                        {json.dumps(op): new_priority}
                    )
```

---

## Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)

1. **Infrastructure Setup**
   - Deploy second Neo4j instance for secure data
   - Configure mTLS between services and secure DB
   - Set up Redis for token vault

2. **Core Services**
   - Implement SecureDatabaseService
   - Implement GatewayService with routing logic
   - Add circuit breaker infrastructure

### Phase 2: Data Migration (Weeks 3-4)

1. **Schema Design**
   - Design secure database schema
   - Create migration scripts
   - Implement data classification pipeline

2. **Migration Execution**
   - Scan existing data for sensitive content
   - Migrate sensitive records to secure DB
   - Update references in operational DB
   - Verify data integrity

### Phase 3: Integration (Weeks 5-6)

1. **Agent Integration**
   - Update Kublai orchestrator to use new architecture
   - Implement sanitization in message flow
   - Add access control checks

2. **Testing**
   - Unit tests for all services
   - Integration tests for cross-DB operations
   - Chaos testing for failure scenarios
   - Security penetration testing

### Phase 4: Production (Week 7+)

1. **Deployment**
   - Blue-green deployment
   - Monitor circuit breaker metrics
   - Gradual traffic shifting

2. **Monitoring**
   - Alert on secure DB availability
   - Track cross-DB query latency
   - Monitor queue depths
   - Audit log analysis

---

## Trade-off Summary

| Aspect | Single DB (Current) | Two-DB (Proposed) |
|--------|---------------------|-------------------|
| **Security** | Medium (app-layer only) | High (defense in depth) |
| **Complexity** | Low | Medium-High |
| **Performance** | Fast (single query) | Medium (cross-DB calls) |
| **Operational Cost** | Low | Medium (2 DBs + Redis) |
| **Compliance** | Harder (mixed data) | Easier (clear boundaries) |
| **Availability** | Single point of failure | Graceful degradation |
| **Scalability** | Limited | Better separation |

### Recommendation

Proceed with the **Two-Database with Gateway** architecture because:

1. **Security is paramount** for the data types involved (passwords, PII, financial)
2. **Compliance requirements** likely mandate physical separation
3. **Defense in depth** - multiple layers of protection
4. **Graceful degradation** - system remains functional during secure DB outages
5. **Clear boundaries** - easier to audit and reason about security

The additional complexity is justified by the sensitivity of the data and the multi-agent nature of the system where multiple agents could potentially access data inappropriately.

---

## Appendix: Schema Definitions

### Secure Neo4j Schema

```cypher
// Sensitive Records
(:SensitiveRecord {
    id: uuid,
    record_type: string,  // "password", "pii", "financial", "api_key"
    encrypted_data: string,  // AES-256-GCM encrypted
    data_hash: string,  // For integrity verification
    access_tier: string,  // "CRITICAL", "HIGH", "NORMAL"
    allowed_agents: [string],  // Which agents can access
    core_ref: string,  // Reference to operational DB record
    created_at: datetime,
    expires_at: datetime,  // TTL for automatic deletion
    access_count: int
})

// Access Audit Log
(:SecureAccessLog {
    id: uuid,
    agent_id: string,
    record_id: string,
    action: string,  // "read", "write", "delete"
    timestamp: datetime,
    success: boolean,
    reason: string  // For denials
})

// Encryption Key References
(:KeyReference {
    id: uuid,
    key_version: string,
    created_at: datetime,
    rotated_at: datetime,
    status: string  // "active", "deprecated", "revoked"
})

// Indexes
CREATE CONSTRAINT sensitive_record_id_unique
    FOR (s:SensitiveRecord) REQUIRE s.id IS UNIQUE;

CREATE INDEX sensitive_record_core_ref
    FOR (s:SensitiveRecord) ON (s.core_ref);

CREATE INDEX sensitive_record_type
    FOR (s:SensitiveRecord) ON (s.record_type, s.access_tier);

CREATE INDEX secure_access_log_agent
    FOR (l:SecureAccessLog) ON (l.agent_id, l.timestamp);

CREATE INDEX secure_access_log_record
    FOR (l:SecureAccessLog) ON (l.record_id, l.timestamp);
```

---

*Document Version: 1.0*
*Last Updated: 2026-02-04*
*Author: Backend Architecture Team*
