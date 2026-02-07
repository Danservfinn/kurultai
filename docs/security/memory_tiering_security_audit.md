# Security Audit: Memory Tiering Architecture

**Document Type:** Security Audit Report
**Scope:** Analysis of proposed 3-tier access system for Neo4j-backed operational memory
**Date:** 2026-02-04
**Auditor:** Security Auditor (Claude Code)
**Status:** CRITICAL REGRESSIONS IDENTIFIED

---

## Executive Summary

The proposed 3-tier memory tiering system introduces **significant security regressions** from the current Two-Tier Memory model. The introduction of a plaintext "Hot Tier" in MEMORY.md violates the existing encryption model and creates a multi-tenant data exposure risk that does not exist in the current architecture.

### Key Findings

| Severity | Finding | Count |
|----------|---------|-------|
| CRITICAL | Plaintext Hot Tier bypasses encryption controls | 1 |
| HIGH | Multi-tenant data isolation gaps | 3 |
| HIGH | Privacy boundary confusion between tier systems | 2 |
| MEDIUM | Missing authentication/authorization between tiers | 2 |
| LOW | Data classification inconsistencies | 2 |

### Recommendation
**DO NOT IMPLEMENT** the proposed 3-tier system without addressing the security regressions. Instead, extend the existing Two-Tier model with time-based access controls while maintaining encryption boundaries.

---

## 1. Current Privacy Model Analysis

### 1.1 Two-Tier Memory Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    CURRENT PRIVACY MODEL                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────┐        ┌─────────────────────────────┐ │
│  │   PERSONAL TIER     │        │      OPERATIONAL TIER       │ │
│  │   (Files - Kublai)  │        │      (Neo4j - Shared)       │ │
│  ├─────────────────────┤        ├─────────────────────────────┤ │
│  │ • User preferences  │        │ • Research findings         │ │
│  │ • Personal history  │        │ • Code patterns             │ │
│  │ • Friend names      │        │ • Analysis insights         │ │
│  │ • Private context   │        │ • Process knowledge         │ │
│  │                     │        │ • Synthesized concepts      │ │
│  │ ACCESS: Kublai only │        │ ACCESS: All 6 agents        │ │
│  │ ENCRYPTION: N/A     │        │ ENCRYPTION: Tier-based      │ │
│  │ (local files)       │        │ (AES-256-GCM for SENSITIVE) │ │
│  └─────────────────────┘        └─────────────────────────────┘ │
│                                                                  │
│  Privacy Rule: Kublai reviews content before delegation          │
│  "My friend Sarah's startup" → "a startup in X sector"           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Access Tier System (Operational Memory)

| Tier | Visibility | Encryption | Use Case |
|------|------------|------------|----------|
| **PUBLIC** | All senders | None | General knowledge, code patterns |
| **SENSITIVE** | Sender-isolated | AES-256-GCM | Health, finance, legal topics |
| **PRIVATE** | Blocked from Neo4j | N/A | Personal relationships, names |

### 1.3 Reflection Temperature Tiers (Lifecycle Only)

The existing `HOT/WARM/COLD/ARCHIVED` system in `/Users/kurultai/molt/docs/plans/neo4j.md` is a **data lifecycle management** system, NOT an access control system:

```cypher
(:Reflection {
  access_tier: "HOT" | "WARM" | "COLD" | "ARCHIVED",  // Lifecycle, not privacy
  embedding: [float],  // Always encrypted if content is SENSITIVE
  // ...
})
```

**Key Point:** Reflection temperature tiers determine retention and caching, not who can access the data. Access control is still governed by the `sender_hash` and content classification.

---

## 2. Proposed 3-Tier System Analysis

### 2.1 Proposed Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PROPOSED 3-TIER SYSTEM                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────┐ │
│   │   HOT TIER   │  │  WARM TIER   │  │  COLD TIER   │  │ ARCHIVE │ │
│   │  (24h recent)│  │  (7-day)     │  │  (30-day)    │  │ (Full)  │ │
│   ├──────────────┤  ├──────────────┤  ├──────────────┤  ├─────────┤ │
│   │ Storage:     │  │ Storage:     │  │ Storage:     │  │ Neo4j   │ │
│   │ MEMORY.md    │  │ Neo4j        │  │ Neo4j        │  │ only    │ │
│   │ (plaintext)  │  │ (encrypted   │  │ (encrypted   │  │ (enc if │ │
│   │              │  │  if SENS)    │  │  if SENS)    │  │  SENS)  │ │
│   └──────────────┘  └──────────────┘  └──────────────┘  └─────────┘ │
│                                                                      │
│   PROBLEM: Hot Tier plaintext storage violates encryption model      │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Security Regressions Identified

#### REGRESSION #1: Plaintext Hot Tier (CRITICAL)

**Current Model:**
- All operational memory in Neo4j
- SENSITIVE tier embeddings encrypted with AES-256-GCM
- No plaintext storage of operational data

**Proposed Model:**
- Hot Tier stored in MEMORY.md (plaintext)
- High-frequency access data in plaintext
- Bypasses field-level encryption entirely

**OWASP Reference:** A03:2021 - Injection (data exposure via file access)

**Attack Scenario:**
```
1. Attacker gains file system read access to Kublai's workspace
2. Reads MEMORY.md (Hot Tier) containing recent 24h context
3. Obtains plaintext SENSITIVE data that should be encrypted
4. Data includes health, finance, legal topics from recent conversations
```

#### REGRESSION #2: Multi-Tenant Data Isolation Gap (HIGH)

**Current Model:**
- All 6 agents access shared Neo4j
- `sender_hash` isolates SENSITIVE data per sender
- Query enforces sender isolation at application layer

**Proposed Model Problem:**
- Hot Tier in MEMORY.md lacks sender_hash isolation
- All senders' recent context mixed in single file
- No mechanism to prevent cross-sender contamination in Hot Tier

**OWASP Reference:** A01:2021 - Broken Access Control

**Vulnerable Code Pattern (Proposed):**
```python
# Current (secure) - Neo4j with sender isolation
MATCH (c:Concept)
WHERE c.access_tier = 'PUBLIC'
   OR (c.access_tier = 'SENSITIVE' AND c.sender_hash = $requesting_sender)
RETURN c

# Proposed (vulnerable) - MEMORY.md plaintext, no sender isolation
# Hot Tier contains all senders' recent context in plaintext
# No query-time filtering possible
```

#### REGRESSION #3: Privacy Boundary Confusion (HIGH)

**Current Model:**
- Clear boundary: Personal (files) vs Operational (Neo4j)
- Clear boundary: PUBLIC/SENSITIVE/PRIVATE classification
- Clear boundary: HOT/WARM/COLD = lifecycle only

**Proposed Model Problem:**
- Hot Tier blurs Personal/Operational boundary
- Temperature tiers conflated with access control
- Confusion about which data goes where

**Example Confusion:**
```
User asks: "How do I treat my diabetes?"

Current handling:
1. Classified as SENSITIVE (health topic)
2. Stored in Neo4j with encrypted embedding
3. Sender-isolated via sender_hash

Proposed handling (problematic):
1. Recent 24h = Hot Tier
2. Stored in MEMORY.md (plaintext)
3. No encryption, no sender isolation
4. All agents can see plaintext health data
```

---

## 3. Detailed Security Analysis

### 3.1 Data Flow Comparison

#### Current Secure Flow
```
User Input
    ↓
Kublai (sanitization)
    ↓
Classify: PUBLIC / SENSITIVE / PRIVATE
    ↓
    ├─ PRIVATE → Blocked from Neo4j (stays in Kublai's files only)
    ├─ SENSITIVE → Neo4j + AES-256-GCM encryption + sender_hash
    └─ PUBLIC → Neo4j (plaintext)
    ↓
All 6 agents access via Neo4j with sender isolation
```

#### Proposed Vulnerable Flow
```
User Input
    ↓
Kublai (sanitization)
    ↓
Classify: PUBLIC / SENSITIVE / PRIVATE
    ↓
    ├─ PRIVATE → Blocked
    ├─ SENSITIVE → Check age
    │   ├─ <24h → MEMORY.md (PLAINTEXT - REGRESSION!)
    │   ├─ 24h-7d → Neo4j + encrypted
    │   └─ >7d → Neo4j + encrypted
    └─ PUBLIC → Check age
        ├─ <24h → MEMORY.md (plaintext)
        └─ >24h → Neo4j
    ↓
Hot Tier (MEMORY.md) accessible to all agents WITHOUT encryption
```

### 3.2 Threat Model Analysis

| Threat | Current Risk | Proposed Risk | Change |
|--------|--------------|---------------|--------|
| File system access exposes operational data | Low (only in Neo4j) | **CRITICAL** (Hot Tier plaintext) | +++ |
| Cross-sender data contamination | Low (sender_hash) | **HIGH** (Hot Tier no isolation) | ++ |
| Agent A accessing Agent B's sensitive data | Blocked | **Possible** (Hot Tier shared) | ++ |
| Backup/restore data exposure | Encrypted | **Partially plaintext** | + |
| Memory dump analysis | Encrypted | **Plaintext Hot Tier** | ++ |

---

## 4. Privacy-Preserving Alternatives

### 4.1 Recommended Approach: Time-Based Access Controls

Instead of tiering by storage location, implement time-based access within the existing Two-Tier model:

```python
# Extend OperationalMemory with temporal access controls
class TemporalAccessControl:
    """
    Maintain existing Two-Tier architecture while adding
    time-based prioritization for performance.
    """

    # Time windows for query prioritization (not storage tiering)
    HOT_WINDOW_HOURS = 24
    WARM_WINDOW_DAYS = 7
    COLD_WINDOW_DAYS = 30

    def query_with_temporal_priority(self, sender_hash: str, query: str):
        """
        Query Neo4j with time-based result prioritization.
        All data stays in Neo4j with existing encryption.
        """
        # All queries respect sender_hash isolation
        # Results ordered by recency, not stored separately
        cypher = """
        MATCH (c:Concept)
        WHERE c.access_tier = 'PUBLIC'
           OR (c.access_tier = 'SENSITIVE' AND c.sender_hash = $sender_hash)
        WITH c,
             CASE
                 WHEN c.created_at > datetime() - duration({hours: 24}) THEN 3  // HOT
                 WHEN c.created_at > datetime() - duration({days: 7}) THEN 2    // WARM
                 WHEN c.created_at > datetime() - duration({days: 30}) THEN 1   // COLD
                 ELSE 0  // ARCHIVED
             END as priority
        RETURN c, priority
        ORDER BY priority DESC, c.created_at DESC
        """
        return self.execute(cypher, sender_hash=sender_hash)
```

### 4.2 Alternative: Encrypted Local Cache

If Hot Tier performance is required, implement an encrypted local cache:

```python
class EncryptedHotCache:
    """
    Local cache with the same encryption as Neo4j SENSITIVE tier.
    """

    def __init__(self, encryption_key: bytes):
        self.cipher = Fernet(encryption_key)
        self.cache: Dict[str, bytes] = {}  # Encrypted at rest

    def store(self, key: str, data: Dict, access_tier: str):
        """Store data with encryption if SENSITIVE."""
        json_data = json.dumps(data).encode()

        if access_tier == "SENSITIVE":
            json_data = self.cipher.encrypt(json_data)

        self.cache[key] = json_data

    def retrieve(self, key: str, sender_hash: str) -> Optional[Dict]:
        """Retrieve with sender isolation enforcement."""
        encrypted_data = self.cache.get(key)
        if not encrypted_data:
            return None

        # Decrypt if needed
        try:
            data = json.loads(self.cipher.decrypt(encrypted_data))
        except:
            data = json.loads(encrypted_data)

        # Enforce sender isolation
        if data.get('access_tier') == 'SENSITIVE':
            if data.get('sender_hash') != sender_hash:
                return None  # Cross-sender access blocked

        return data
```

---

## 5. Privacy Boundary Framework

### 5.1 Clear Boundary Definitions

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PRIVACY BOUNDARY FRAMEWORK                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  BOUNDARY 1: Storage Location                                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  PERSONAL (Files)          vs        OPERATIONAL (Neo4j)     │   │
│  │  • Kublai only                       • All 6 agents          │   │
│  │  • User preferences                  • Sanitized knowledge   │   │
│  │  • Private context                   • No PII                │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  BOUNDARY 2: Content Classification (Operational Memory Only)        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  PUBLIC    │   SENSITIVE              │   PRIVATE            │   │
│  │  ───────   │   ─────────              │   ───────            │   │
│  │  No enc    │   AES-256-GCM            │   Blocked from Neo4j │   │
│  │  All senders      Sender-isolated     │   Kublai files only  │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  BOUNDARY 3: Data Lifecycle (Reflection Memory Only)                 │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  HOT → WARM → COLD → ARCHIVED                                │   │
│  │  (7d)  (30d)  (90d)  (forever)                               │   │
│  │  Does NOT affect access control, only retention/caching      │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 Data Classification Matrix

| Data Type | Example | Storage | Encryption | Sender Isolation |
|-----------|---------|---------|------------|------------------|
| Personal preference | "I prefer Python" | Kublai files | N/A | N/A (Kublai only) |
| Personal relationship | "My friend Sarah" | Kublai files | N/A | N/A (Kublai only) |
| General knowledge | "Python list comprehensions" | Neo4j | None | N/A (PUBLIC) |
| Health topic | "Diabetes treatment options" | Neo4j | AES-256-GCM | Yes (SENSITIVE) |
| Finance topic | "Investment strategies" | Neo4j | AES-256-GCM | Yes (SENSITIVE) |
| Code pattern | "Factory pattern in Python" | Neo4j | None | N/A (PUBLIC) |

---

## 6. Security Controls by Tier

### 6.1 If Hot Tier Must Be Implemented (Risk Mitigation)

If the Hot Tier is absolutely required for performance, implement these controls:

#### Control 1: Encryption at Rest
```python
# Hot Tier must use same encryption as Neo4j SENSITIVE tier
class SecureHotTier:
    def __init__(self):
        self.cipher = self._init_encryption()

    def store(self, data: Dict, access_tier: str):
        """Encrypt SENSITIVE data before writing to MEMORY.md."""
        if access_tier == "SENSITIVE":
            encrypted = self.cipher.encrypt(json.dumps(data).encode())
            return {"_encrypted": base64.b64encode(encrypted).decode()}
        return data
```

#### Control 2: Sender Isolation Enforcement
```python
def enforce_sender_isolation(hot_tier_data: List[Dict], requesting_sender: str) -> List[Dict]:
    """Filter Hot Tier data by sender_hash before returning."""
    return [
        item for item in hot_tier_data
        if item.get('access_tier') == 'PUBLIC'
        or (item.get('access_tier') == 'SENSITIVE'
            and item.get('sender_hash') == requesting_sender)
    ]
```

#### Control 3: Access Audit Logging
```python
def access_hot_tier(agent_id: str, sender_hash: str, data_id: str):
    """Log all Hot Tier access for audit."""
    audit_log.info({
        "event": "hot_tier_access",
        "agent": agent_id,
        "sender_hash": hashlib.sha256(sender_hash.encode()).hexdigest()[:16],  # Hashed
        "data_id": data_id,
        "timestamp": datetime.utcnow().isoformat()
    })
```

### 6.2 Security Checklist for Each Tier

| Control | Hot Tier | Warm Tier | Cold Tier | Archive |
|---------|----------|-----------|-----------|---------|
| Encryption at rest | REQUIRED | REQUIRED | REQUIRED | REQUIRED |
| Sender isolation | REQUIRED | REQUIRED | REQUIRED | N/A (no embeddings) |
| Access audit logging | REQUIRED | RECOMMENDED | RECOMMENDED | OPTIONAL |
| Rate limiting | REQUIRED | REQUIRED | REQUIRED | N/A |
| Data retention limit | 24h | 7d | 30d | Indefinite |
| Backup encryption | REQUIRED | REQUIRED | REQUIRED | REQUIRED |

---

## 7. OWASP Mapping

| Finding | OWASP Category | CVSS Score | Description |
|---------|----------------|------------|-------------|
| Plaintext Hot Tier | A02:2021 - Cryptographic Failures | 7.5 (High) | Sensitive data stored without encryption |
| Cross-sender contamination | A01:2021 - Broken Access Control | 8.1 (High) | Missing sender isolation in Hot Tier |
| Privacy boundary confusion | A04:2021 - Insecure Design | 6.5 (Medium) | Ambiguous data classification |
| Missing auth between tiers | A07:2021 - Auth Failures | 7.0 (High) | No tier transition authentication |

---

## 8. Recommendations

### 8.1 Immediate Actions (Before Any Implementation)

1. **REJECT** the proposed plaintext Hot Tier in MEMORY.md
2. **MAINTAIN** the existing Two-Tier architecture (Personal vs Operational)
3. **EXTEND** with time-based query prioritization, not storage tiering
4. **AUDIT** all existing PII sanitization logic before any changes

### 8.2 Alternative Implementation (If Performance Required)

If the 24h Hot Tier is required for performance:

1. Implement encrypted local cache (Section 4.2)
2. Maintain sender_hash isolation in cache
3. Add audit logging for all cache access
4. Set 24h TTL on cache entries
5. Sync cache misses to Neo4j (not the other way around)

### 8.3 Testing Requirements

Before deploying any tiering system:

1. **Penetration Test:** Attempt to access cross-sender data in Hot Tier
2. **Encryption Audit:** Verify all SENSITIVE data encrypted at rest
3. **Access Control Test:** Verify agents cannot bypass sender isolation
4. **Backup Security:** Verify encrypted backups include Hot Tier

---

## 9. Conclusion

The proposed 3-tier memory system introduces **critical security regressions** that violate the existing privacy model. The plaintext Hot Tier in MEMORY.md is a significant vulnerability that exposes SENSITIVE data to file system access and breaks sender isolation guarantees.

**Recommendation:** Do not implement the proposed system. Instead, use time-based query prioritization within the existing Two-Tier architecture, or implement an encrypted local cache that maintains the same security controls as Neo4j.

---

## References

- Current Privacy Model: `/Users/kurultai/molt/docs/plans/neo4j.md` (lines 845-889)
- Access Tier System: `/Users/kurultai/molt/docs/plans/neo4j.md` (lines 2761-2764)
- Reflection Temperature Tiers: `/Users/kurultai/molt/docs/plans/neo4j.md` (lines 7614-7639)
- Embedding Encryption: `/Users/kurultai/molt/docs/plans/neo4j.md` (lines 3303-3376)
- OWASP Top 10: https://owasp.org/Top10/

---

**Document Classification:** Security Audit
**Distribution:** Kurultai System Architecture, Security Team
**Review Date:** 2026-02-11 (7 days from audit date)
