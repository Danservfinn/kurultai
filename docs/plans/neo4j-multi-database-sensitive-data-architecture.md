# Neo4j Multi-Database Architecture for Sensitive Data Isolation

## Executive Summary

This document provides a comprehensive Neo4j multi-database design that separates sensitive data (credentials, PII, financial records) from operational data in the OpenClaw multi-agent system. The design prioritizes security, real-time access, and years of data retention while maintaining operational efficiency.

**Key Design Decisions:**
- **Separate Neo4j instances** for maximum isolation (vs multi-database single instance)
- **UUID-based reference pattern** for cross-database linking without data leakage
- **Kublai-only access** to sensitive database via dedicated connection pool
- **Time-based partitioning** using date sharding for multi-year retention

---

## 1. Deployment Architecture Comparison

### 1.1 Option A: Multiple Databases in Single Neo4j Instance (Enterprise)

```yaml
# neo4j.conf - Single instance, multiple databases
# Default operational database
dbms.default_database=operational

# Additional databases (Enterprise feature)
dbms.databases.default_to_read_only=false
```

```cypher
// Create additional databases (Enterprise only)
CREATE DATABASE sensitive IF NOT EXISTS;
CREATE DATABASE audit IF NOT EXISTS;
CREATE DATABASE archive IF NOT EXISTS;

// Show all databases
SHOW DATABASES;
```

**Pros:**
- Shared memory and cache management
- Simpler backup/restore coordination
- Single connection pool with database switching
- Lower infrastructure cost

**Cons:**
- Single point of failure for all data
- Shared resource contention
- Limited isolation (same process, same filesystem)
- Enterprise license required ($$$)
- No true network isolation

**Verdict:** Not recommended for sensitive data isolation

---

### 1.2 Option B: Separate Neo4j Instances (Recommended)

```yaml
# Instance 1: Operational Data (operational-neo4j)
# /etc/neo4j/neo4j.conf
server.bolt.enabled=true
server.bolt.listen_address=0.0.0.0:7687
server.http.listen_address=0.0.0.0:7474
server.directories.data=/var/lib/neo4j/data
server.memory.heap.max_size=4G
server.memory.pagecache.size=2G
```

```yaml
# Instance 2: Sensitive Data (sensitive-neo4j)
# /etc/neo4j-sensitive/neo4j.conf
server.bolt.enabled=true
server.bolt.listen_address=0.0.0.0:7688  # Different port
server.http.listen_address=0.0.0.0:7475  # Different port
server.directories.data=/var/lib/neo4j-sensitive/data  # Separate storage
server.memory.heap.max_size=2G
server.memory.pagecache.size=1G

# Enhanced security settings
server.security.auth_enabled=true
server.security.log_successful_authentication=true
server.security.log_failed_authentication=true
```

```yaml
# Instance 3: Audit Logs (audit-neo4j)
# /etc/neo4j-audit/neo4j.conf
server.bolt.listen_address=0.0.0.0:7689
server.directories.data=/var/lib/neo4j-audit/data
server.memory.heap.max_size=1G

# Audit-specific: Append-optimized
server.logs.gc.enabled=true
server.logs.gc.rotation.size=100m
```

**Pros:**
- True process isolation
- Independent resource allocation
- Network-level access control (firewall rules)
- Independent backup/restore schedules
- Can run different Neo4j versions
- No Enterprise license required for Community Edition

**Cons:**
- Higher infrastructure cost
- More complex connection management
- Cross-instance queries require application-layer coordination

**Verdict:** RECOMMENDED for production sensitive data isolation

---

### 1.3 Option C: Neo4j Fabric for Cross-Database Queries

```cypher
// Fabric configuration (neo4j.conf)
fabric.database.name=fabric
fabric.graph.0.name=operational
fabric.graph.0.uri=neo4j://localhost:7687
fabric.graph.0.database=neo4j

fabric.graph.1.name=sensitive
fabric.graph.1.uri=neo4j://localhost:7688
fabric.graph.1.database=neo4j

fabric.graph.2.name=audit
fabric.graph.2.uri=neo4j://localhost:7689
fabric.graph.2.database=neo4j
```

```cypher
// Cross-database query using Fabric
USE fabric.operational
MATCH (t:Task {id: "task-123"})
RETURN t.id as task_id, t.operational_uuid as uuid

UNION

USE fabric.sensitive
MATCH (s:SensitiveData {operational_uuid: "uuid-from-above"})
RETURN s.id as task_id, s.credential_reference as cred_ref
```

**Pros:**
- Unified query interface across databases
- Simplified cross-database joins
- Single connection point

**Cons:**
- Enterprise Edition only
- Adds complexity and potential bottleneck
- Requires careful security configuration
- Limited to read-only operations across graphs in Community Edition

**Verdict:** Optional enhancement for read-only analytics, not core architecture

---

### 1.4 Recommended Architecture Summary

| Aspect | Operational DB | Sensitive DB | Audit DB |
|--------|---------------|--------------|----------|
| **Port** | 7687 | 7688 | 7689 |
| **HTTP** | 7474 | 7475 | 7476 |
| **Memory** | 4GB heap | 2GB heap | 1GB heap |
| **Storage** | SSD | Encrypted SSD | Standard |
| **Access** | All agents | Kublai only | Append-only |
| **Backup** | Daily | Hourly (incremental) | Continuous |
| **Retention** | 90 days hot | 7 years | Permanent |
| **Encryption** | At-rest | At-rest + in-transit + field-level | At-rest |

---

## 2. Schema Design

### 2.1 Operational Database Schema

```cypher
// ============================================================================
// OPERATIONAL DATABASE - Shared agent memory
// ============================================================================

// Core nodes (existing)
(:Agent {id: string, name: string, role: string, status: string})
(:Task {id: string, description: string, status: string, priority: string})
(:Notification {id: string, type: string, summary: string, read: boolean})
(:Belief {id: string, content: string, confidence: float, state: string})

// NEW: Reference nodes for cross-database linking
(:SensitiveDataRef {
    id: string,                          // Operational UUID
    sensitive_uuid: string,              // UUID in sensitive database
    data_type: string,                   // "credential" | "pii" | "financial"
    created_at: datetime,
    expires_at: datetime,                // For TTL cleanup
    access_policy: string                // JSON-encoded policy rules
})

// NEW: Data classification tags
(:DataClassification {
    id: string,
    classification_level: string,        // "public" | "internal" | "confidential"
    data_category: string,               // "operational" | "user_preference"
    retention_days: int,
    encryption_required: boolean
})

// Relationships
(:Agent)-[:CREATED]->(:Task)
(:Agent)-[:ASSIGNED_TO]->(:Task)
(:Task)-[:HAS_SENSITIVE_REF]->(:SensitiveDataRef)
(:Task)-[:CLASSIFIED_AS]->(:DataClassification)
```

### 2.2 Sensitive Database Schema

```cypher
// ============================================================================
// SENSITIVE DATABASE - Credentials, PII, Financial data
// ============================================================================

// Core sensitive data node
(:SensitiveData {
    id: string,                          // Sensitive DB UUID (primary key)
    operational_uuid: string,            // Reference back to operational DB
    data_type: string,                   // "credential" | "pii" | "financial" | "api_key"
    encryption_version: string,          // "v1" | "v2" for key rotation
    created_at: datetime,
    updated_at: datetime,
    expires_at: datetime,                // For credential rotation
    access_count: int,                   // Audit tracking
    last_accessed: datetime,
    access_policy: string                // JSON policy
})

// Credential-specific node
(:Credential {
    id: string,
    operational_uuid: string,
    credential_type: string,             // "password" | "token" | "certificate" | "api_key"
    service_name: string,                // "aws" | "github" | "stripe"
    account_identifier: string,          // Username, account ID (hashed)
    encrypted_credential: string,        // AES-256-GCM encrypted
    credential_hash: string,             // SHA-256 hash for duplicate detection
    rotation_due: datetime,
    created_at: datetime,
    expires_at: datetime
})

// PII-specific node
(:PII {
    id: string,
    operational_uuid: string,
    pii_type: string,                    // "ssn" | "email" | "phone" | "address" | "dob"
    pii_category: string,                // "direct" | "indirect" | "sensitive"
    encrypted_value: string,             // Encrypted PII value
    value_hash: string,                  // Hash for correlation without decryption
    data_subject_id: string,             // Reference to data subject (hashed)
    consent_status: string,              // "granted" | "revoked" | "expired"
    consent_expires: datetime,
    created_at: datetime
})

// Financial data node
(:FinancialRecord {
    id: string,
    operational_uuid: string,
    record_type: string,                 // "transaction" | "account" | "invoice"
    encrypted_payload: string,           // Full encrypted record
    amount_hash: string,                 // Range-queryable hash (bucketed)
    date_bucket: string,                 // "2024-01" for time queries without decryption
    currency: string,
    compliance_tags: [string],           // ["pci_dss", "sox", "gdpr"]
    retention_until: datetime
})

// Access policy node
(:AccessPolicy {
    id: string,
    policy_name: string,
    allowed_agents: [string],            // ["kublai"]
    allowed_operations: [string],        // ["read", "write", "delete"]
    require_approval_above: string,      // Threshold for additional approval
    audit_level: string,                 // "full" | "summary" | "none"
    created_at: datetime
})

// Data subject (for GDPR/CCPA)
(:DataSubject {
    id: string,                          // Hashed identifier
    subject_type: string,                // "user" | "customer" | "employee"
    consent_record: string,              // Encrypted consent JSON
    data_retention_authorized: boolean,
    deletion_requested: datetime,        // For right-to-be-forgotten
    created_at: datetime
})

// Relationships
(:SensitiveData)-[:HAS_CREDENTIAL]->(:Credential)
(:SensitiveData)-[:HAS_PII]->(:PII)
(:SensitiveData)-[:HAS_FINANCIAL]->(:FinancialRecord)
(:SensitiveData)-[:GOVERNED_BY]->(:AccessPolicy)
(:PII)-[:BELONGS_TO]->(:DataSubject)
(:FinancialRecord)-[:BELONGS_TO]->(:DataSubject)
```

### 2.3 Audit Database Schema

```cypher
// ============================================================================
// AUDIT DATABASE - Immutable audit trail
// ============================================================================

// Access audit log
(:AccessAudit {
    id: string,
    timestamp: datetime,
    agent: string,
    action: string,                      // "read" | "write" | "delete" | "query"
    resource_type: string,               // "credential" | "pii" | "financial"
    operational_uuid: string,            // Reference (not sensitive_uuid)
    success: boolean,
    failure_reason: string,
    query_fingerprint: string,           // Hash of query pattern
    rows_accessed: int,
    client_ip: string,
    session_id: string
})

// Data modification audit
(:DataModificationAudit {
    id: string,
    timestamp: datetime,
    agent: string,
    operation: string,                   // "create" | "update" | "delete"
    resource_type: string,
    operational_uuid: string,
    field_changed: string,
    previous_hash: string,               // Hash of previous value
    new_hash: string,                    // Hash of new value
    change_reason: string
})

// Security event audit
(:SecurityAudit {
    id: string,
    timestamp: datetime,
    event_type: string,                  // "authentication_failure" | "unauthorized_access" | "anomaly"
    severity: string,                    // "low" | "medium" | "high" | "critical"
    agent: string,
    source_ip: string,
    details: string,
    resolved: boolean,
    resolution_time: datetime
})

// Compliance snapshot
(:ComplianceSnapshot {
    id: string,
    timestamp: datetime,
    compliance_framework: string,        // "gdpr" | "pci_dss" | "hipaa" | "sox"
    check_type: string,
    status: string,                      // "pass" | "fail" | "warning"
    findings: string,
    remediation_required: boolean
})
```

---

## 3. Reference Patterns for Cross-Database Linking

### 3.1 UUID-Based Reference Pattern (Recommended)

```python
# Python implementation of cross-database reference management

import uuid
import hashlib
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import json

@dataclass
class CrossDatabaseReference:
    """Manages references between operational and sensitive databases."""
    operational_uuid: str
    sensitive_uuid: str
    data_type: str
    created_at: datetime
    expires_at: Optional[datetime]

class ReferenceManager:
    """
    Manages UUID-based cross-database references.

    Design principles:
    1. Operational DB stores only UUID reference, no sensitive data
    2. Sensitive DB stores operational_uuid for lookup
    3. No direct foreign keys - loose coupling
    4. References can be broken without data loss
    """

    def __init__(self, operational_db, sensitive_db):
        self.op_db = operational_db
        self.sens_db = sensitive_db

    def create_reference(
        self,
        data_type: str,
        sensitive_data: Dict[str, Any],
        access_policy: Dict[str, Any],
        ttl_days: Optional[int] = None
    ) -> CrossDatabaseReference:
        """
        Create a new cross-database reference.

        Args:
            data_type: Type of sensitive data (credential, pii, financial)
            sensitive_data: The actual sensitive data (will be encrypted)
            access_policy: JSON-serializable access policy
            ttl_days: Optional time-to-live for auto-cleanup

        Returns:
            CrossDatabaseReference linking operational and sensitive UUIDs
        """
        # Generate UUIDs
        operational_uuid = str(uuid.uuid4())
        sensitive_uuid = str(uuid.uuid4())

        created_at = datetime.utcnow()
        expires_at = created_at + timedelta(days=ttl_days) if ttl_days else None

        # 1. Store reference in operational database (no sensitive data)
        self._create_operational_ref(
            operational_uuid=operational_uuid,
            sensitive_uuid=sensitive_uuid,
            data_type=data_type,
            created_at=created_at,
            expires_at=expires_at,
            access_policy=access_policy
        )

        # 2. Store sensitive data in sensitive database
        self._create_sensitive_record(
            sensitive_uuid=sensitive_uuid,
            operational_uuid=operational_uuid,
            data_type=data_type,
            sensitive_data=sensitive_data,
            created_at=created_at,
            expires_at=expires_at,
            access_policy=access_policy
        )

        return CrossDatabaseReference(
            operational_uuid=operational_uuid,
            sensitive_uuid=sensitive_uuid,
            data_type=data_type,
            created_at=created_at,
            expires_at=expires_at
        )

    def _create_operational_ref(
        self,
        operational_uuid: str,
        sensitive_uuid: str,
        data_type: str,
        created_at: datetime,
        expires_at: Optional[datetime],
        access_policy: Dict[str, Any]
    ):
        """Create reference node in operational database."""
        cypher = """
        CREATE (r:SensitiveDataRef {
            id: $operational_uuid,
            sensitive_uuid: $sensitive_uuid,
            data_type: $data_type,
            created_at: $created_at,
            expires_at: $expires_at,
            access_policy: $access_policy
        })
        RETURN r.id as id
        """

        with self.op_db.session() as session:
            session.run(cypher, {
                'operational_uuid': operational_uuid,
                'sensitive_uuid': sensitive_uuid,
                'data_type': data_type,
                'created_at': created_at.isoformat(),
                'expires_at': expires_at.isoformat() if expires_at else None,
                'access_policy': json.dumps(access_policy)
            })

    def _create_sensitive_record(
        self,
        sensitive_uuid: str,
        operational_uuid: str,
        data_type: str,
        sensitive_data: Dict[str, Any],
        created_at: datetime,
        expires_at: Optional[datetime],
        access_policy: Dict[str, Any]
    ):
        """Create encrypted record in sensitive database."""
        # Encrypt sensitive data
        encrypted_payload = self._encrypt_sensitive_data(sensitive_data)

        cypher = """
        CREATE (s:SensitiveData {
            id: $sensitive_uuid,
            operational_uuid: $operational_uuid,
            data_type: $data_type,
            encryption_version: 'v1',
            encrypted_payload: $encrypted_payload,
            created_at: $created_at,
            updated_at: $created_at,
            expires_at: $expires_at,
            access_policy: $access_policy,
            access_count: 0
        })
        RETURN s.id as id
        """

        with self.sens_db.session() as session:
            session.run(cypher, {
                'sensitive_uuid': sensitive_uuid,
                'operational_uuid': operational_uuid,
                'data_type': data_type,
                'encrypted_payload': encrypted_payload,
                'created_at': created_at.isoformat(),
                'expires_at': expires_at.isoformat() if expires_at else None,
                'access_policy': json.dumps(access_policy)
            })

    def resolve_reference(
        self,
        operational_uuid: str,
        agent: str,
        purpose: str
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve a reference to retrieve sensitive data.

        Args:
            operational_uuid: UUID from operational database
            agent: Requesting agent (must be authorized)
            purpose: Reason for access (for audit log)

        Returns:
            Decrypted sensitive data or None if not found/unauthorized
        """
        # 1. Verify agent authorization
        if not self._is_authorized(agent, operational_uuid):
            self._log_unauthorized_access(agent, operational_uuid)
            return None

        # 2. Get sensitive UUID from operational DB
        sensitive_uuid = self._get_sensitive_uuid(operational_uuid)
        if not sensitive_uuid:
            return None

        # 3. Retrieve and decrypt from sensitive DB
        sensitive_data = self._get_sensitive_data(sensitive_uuid)
        if not sensitive_data:
            return None

        # 4. Log access to audit database
        self._log_access(agent, operational_uuid, sensitive_uuid, purpose)

        # 5. Update access count in sensitive DB
        self._update_access_stats(sensitive_uuid)

        return sensitive_data

    def _get_sensitive_uuid(self, operational_uuid: str) -> Optional[str]:
        """Lookup sensitive UUID from operational database."""
        cypher = """
        MATCH (r:SensitiveDataRef {id: $operational_uuid})
        WHERE r.expires_at IS NULL OR r.expires_at > datetime()
        RETURN r.sensitive_uuid as sensitive_uuid
        """

        with self.op_db.session() as session:
            result = session.run(cypher, {'operational_uuid': operational_uuid})
            record = result.single()
            return record['sensitive_uuid'] if record else None

    def _get_sensitive_data(self, sensitive_uuid: str) -> Optional[Dict[str, Any]]:
        """Retrieve and decrypt from sensitive database."""
        cypher = """
        MATCH (s:SensitiveData {id: $sensitive_uuid})
        WHERE s.expires_at IS NULL OR s.expires_at > datetime()
        RETURN s.encrypted_payload as payload,
               s.encryption_version as version
        """

        with self.sens_db.session() as session:
            result = session.run(cypher, {'sensitive_uuid': sensitive_uuid})
            record = result.single()
            if record:
                return self._decrypt_sensitive_data(
                    record['payload'],
                    record['version']
                )
            return None

    def _is_authorized(self, agent: str, operational_uuid: str) -> bool:
        """Check if agent is authorized to access this data."""
        # Only Kublai can access sensitive data
        if agent != 'kublai':
            return False

        # Additional policy checks can be added here
        return True

    def _encrypt_sensitive_data(self, data: Dict[str, Any]) -> str:
        """Encrypt sensitive data for storage."""
        # Implementation using AES-256-GCM
        from cryptography.fernet import Fernet
        import base64

        key = self._get_encryption_key()
        f = Fernet(key)
        json_bytes = json.dumps(data).encode('utf-8')
        encrypted = f.encrypt(json_bytes)
        return base64.b64encode(encrypted).decode('utf-8')

    def _decrypt_sensitive_data(self, encrypted: str, version: str) -> Dict[str, Any]:
        """Decrypt sensitive data from storage."""
        from cryptography.fernet import Fernet
        import base64

        key = self._get_encryption_key(version)
        f = Fernet(key)
        encrypted_bytes = base64.b64decode(encrypted.encode('utf-8'))
        decrypted = f.decrypt(encrypted_bytes)
        return json.loads(decrypted.decode('utf-8'))

    def _get_encryption_key(self, version: str = 'v1') -> bytes:
        """Retrieve encryption key from secure key management."""
        # In production, use AWS KMS, HashiCorp Vault, etc.
        # This is a placeholder
        import os
        key = os.environ.get(f'SENSITIVE_DB_KEY_{version}')
        if not key:
            raise ValueError(f"Encryption key not found for version {version}")
        return key.encode('utf-8')

    def _log_access(
        self,
        agent: str,
        operational_uuid: str,
        sensitive_uuid: str,
        purpose: str
    ):
        """Log access to audit database."""
        cypher = """
        CREATE (a:AccessAudit {
            id: randomUUID(),
            timestamp: datetime(),
            agent: $agent,
            action: 'read',
            resource_type: 'sensitive_data',
            operational_uuid: $operational_uuid,
            success: true,
            query_fingerprint: $purpose,
            session_id: $session_id
        })
        """

        with self.audit_db.session() as session:
            session.run(cypher, {
                'agent': agent,
                'operational_uuid': operational_uuid,
                'purpose': hashlib.sha256(purpose.encode()).hexdigest()[:16],
                'session_id': str(uuid.uuid4())
            })

    def _update_access_stats(self, sensitive_uuid: str):
        """Update access statistics in sensitive database."""
        cypher = """
        MATCH (s:SensitiveData {id: $sensitive_uuid})
        SET s.access_count = s.access_count + 1,
            s.last_accessed = datetime()
        """

        with self.sens_db.session() as session:
            session.run(cypher, {'sensitive_uuid': sensitive_uuid})
```

### 3.2 Hash-Based Correlation Pattern

For scenarios where you need to correlate data without revealing the actual value:

```cypher
// Store hash in operational DB for correlation
MATCH (t:Task {id: "task-123"})
CREATE (ref:SensitiveDataRef {
    id: "ref-456",
    sensitive_uuid: "sens-789",
    data_type: "pii",
    value_hash: "sha256:abc123...",  // Hash only, not the value
    hash_algorithm: "sha256",
    created_at: datetime()
})
CREATE (t)-[:HAS_SENSITIVE_REF]->(ref)

// Query: Find all tasks related to same data subject
// Without revealing who the subject is
MATCH (ref1:SensitiveDataRef {value_hash: "sha256:abc123..."})
MATCH (ref1)<-[:HAS_SENSITIVE_REF]-(t:Task)
RETURN t.id as related_task
```

### 3.3 Token-Based Access Pattern

For temporary, time-limited access:

```python
class TokenBasedAccess:
    """Generate time-limited access tokens for sensitive data."""

    def grant_temporary_access(
        self,
        operational_uuid: str,
        agent: str,
        duration_minutes: int = 30
    ) -> str:
        """Grant temporary access token."""
        token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(minutes=duration_minutes)

        cypher = """
        MATCH (r:SensitiveDataRef {id: $operational_uuid})
        CREATE (t:AccessToken {
            token_hash: $token_hash,
            agent: $agent,
            granted_at: datetime(),
            expires_at: $expires,
            used: false
        })
        CREATE (r)-[:HAS_TEMPORARY_TOKEN]->(t)
        RETURN t.token_hash as hash
        """

        # Store in sensitive DB
        with self.sens_db.session() as session:
            session.run(cypher, {
                'operational_uuid': operational_uuid,
                'token_hash': hashlib.sha256(token.encode()).hexdigest(),
                'agent': agent,
                'expires': expires.isoformat()
            })

        return token

    def access_with_token(self, token: str) -> Optional[Dict]:
        """Access sensitive data using temporary token."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        cypher = """
        MATCH (t:AccessToken {token_hash: $token_hash})
        WHERE t.expires_at > datetime() AND t.used = false
        MATCH (t)<-[:HAS_TEMPORARY_TOKEN]-(r:SensitiveDataRef)
        MATCH (s:SensitiveData {operational_uuid: r.id})
        SET t.used = true,
            t.used_at = datetime()
        RETURN s.encrypted_payload as payload
        """

        with self.sens_db.session() as session:
            result = session.run(cypher, {'token_hash': token_hash})
            record = result.single()
            if record:
                return self._decrypt(record['payload'])
            return None
```

---

## 4. Time-Based Partitioning for Years of Data Retention

### 4.1 Date Sharding Strategy

```cypher
// ============================================================================
// TIME-BASED PARTITIONING USING DATE PREFIXES
// ============================================================================

// Instead of single :FinancialRecord label, use year-based labels
// This allows efficient querying and archiving by time period

// 2024 financial records
(:FinancialRecord2024 {
    id: string,
    operational_uuid: string,
    month: "01",  // Allows month-level queries
    encrypted_payload: string,
    date_bucket: "2024-01"
})

// 2023 financial records (can be moved to cold storage)
(:FinancialRecord2023 { ... })

// Create records with automatic year labeling
CREATE (f:FinancialRecord2024:FinancialRecord {
    id: "fin-" + randomUUID(),
    operational_uuid: $op_uuid,
    year: 2024,
    month: "01",
    created_at: datetime(),
    date_bucket: "2024-01",
    encrypted_payload: $encrypted
})
```

### 4.2 Automated Partition Management

```python
class TimePartitionManager:
    """Manages time-based data partitioning for multi-year retention."""

    def __init__(self, sensitive_db):
        self.db = sensitive_db
        self.retention_years = 7

    def create_partitioned_record(
        self,
        data_type: str,
        record_data: Dict,
        timestamp: Optional[datetime] = None
    ) -> str:
        """Create a record in the appropriate time partition."""
        ts = timestamp or datetime.utcnow()
        year = ts.year
        month = f"{ts.month:02d}"

        # Dynamic label based on year
        label = f"{data_type}{year}"

        cypher = f"""
        CREATE (r:{label}:{data_type} {{
            id: $id,
            operational_uuid: $op_uuid,
            year: $year,
            month: $month,
            date_bucket: $date_bucket,
            created_at: $created_at,
            encrypted_payload: $encrypted,
            retention_until: $retention_until
        }})
        RETURN r.id as id
        """

        record_id = f"{data_type.lower()}-{uuid.uuid4()}"
        retention_until = ts + timedelta(days=365 * self.retention_years)

        with self.db.session() as session:
            result = session.run(cypher, {
                'id': record_id,
                'op_uuid': record_data['operational_uuid'],
                'year': year,
                'month': month,
                'date_bucket': f"{year}-{month}",
                'created_at': ts.isoformat(),
                'encrypted': self._encrypt(record_data),
                'retention_until': retention_until.isoformat()
            })
            return result.single()['id']

    def query_by_time_range(
        self,
        data_type: str,
        start_date: datetime,
        end_date: datetime,
        agent: str
    ) -> List[Dict]:
        """Query records across time partitions."""
        # Generate list of year labels to query
        years = range(start_date.year, end_date.year + 1)
        labels = [f"{data_type}{y}" for y in years]

        results = []
        for label in labels:
            cypher = f"""
            MATCH (r:{label})
            WHERE r.created_at >= $start_date
              AND r.created_at <= $end_date
              AND (r.retention_until IS NULL OR r.retention_until > datetime())
            RETURN r.id as id,
                   r.operational_uuid as op_uuid,
                   r.date_bucket as bucket,
                   r.encrypted_payload as payload
            """

            with self.db.session() as session:
                result = session.run(cypher, {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat()
                })

                for record in result:
                    # Log access for each record
                    self._log_partition_access(agent, record['id'])
                    results.append({
                        'id': record['id'],
                        'operational_uuid': record['op_uuid'],
                        'date_bucket': record['bucket'],
                        'data': self._decrypt(record['payload'])
                    })

        return results

    def archive_old_partitions(self, current_year: int):
        """Move partitions older than retention period to archive."""
        cutoff_year = current_year - self.retention_years

        # Find partitions to archive
        cypher = """
        CALL db.labels() YIELD label
        WHERE label STARTS WITH 'FinancialRecord'
          AND label <> 'FinancialRecord'
          AND toInteger(substring(label, 15)) < $cutoff_year
        RETURN label as old_partition
        """

        with self.db.session() as session:
            result = session.run(cypher, {'cutoff_year': cutoff_year})
            partitions = [r['old_partition'] for r in result]

        for partition in partitions:
            self._archive_partition(partition)

    def _archive_partition(self, partition_label: str):
        """Archive a partition to cold storage."""
        # Export to encrypted archive file
        cypher = f"""
        MATCH (r:{partition_label})
        RETURN r.id as id,
               r.operational_uuid as op_uuid,
               r.encrypted_payload as payload,
               r.created_at as created_at
        """

        archive_file = f"/archive/sensitive/{partition_label}.json.enc"

        with self.db.session() as session:
            result = session.run(cypher)
            records = [dict(r) for r in result]

        # Encrypt and write to archive
        self._write_archive(archive_file, records)

        # Delete from hot storage (optional - can keep for query)
        # cypher = f"MATCH (r:{partition_label}) DELETE r"
```

### 4.3 Rolling Window Views

```cypher
// Create a view-like query for rolling 7-year window
// This can be called by applications for consistent time-filtering

// Function-like query pattern
WITH datetime() - duration('P7Y') as seven_years_ago

// Query recent partitions
MATCH (r:FinancialRecord)
WHERE r.created_at >= seven_years_ago
  AND (r.retention_until IS NULL OR r.retention_until > datetime())

// Union with specific year partitions for older data
UNION

MATCH (r:FinancialRecord2023)
WHERE r.created_at >= seven_years_ago

UNION

MATCH (r:FinancialRecord2024)
WHERE r.created_at >= seven_years_ago

RETURN r.id as id,
       r.operational_uuid as op_uuid,
       r.date_bucket as period,
       r.encrypted_payload as payload
ORDER BY r.created_at DESC
```

---

## 5. Access Control Implementation

### 5.1 Neo4j Role-Based Access Control

```cypher
// ============================================================================
// SENSITIVE DATABASE - Role Configuration
// ============================================================================

// Create roles (run as admin)
CREATE ROLE kublai_sensitive_access IF NOT EXISTS;
CREATE ROLE audit_reader IF NOT EXISTS;
CREATE ROLE no_sensitive_access IF NOT EXISTS;

// Grant privileges to Kublai role
GRANT READ {*} ON GRAPH sensitive TO kublai_sensitive_access;
GRANT WRITE ON GRAPH sensitive TO kublai_sensitive_access;
GRANT CREATE ON GRAPH sensitive TO kublai_sensitive_access;
GRANT DELETE ON GRAPH sensitive TO kublai_sensitive_access;

// Restrict to specific labels (fine-grained)
DENY READ {encrypted_credential, encrypted_payload}
    ON GRAPH sensitive
    NODES Credential, PII, FinancialRecord, SensitiveData
    TO audit_reader;

// Grant only metadata access to audit role
GRANT READ {id, operational_uuid, data_type, created_at, access_count}
    ON GRAPH sensitive
    TO audit_reader;

// Create users and assign roles
CREATE USER kublai_agent IF NOT EXISTS
    SET PASSWORD 'secure-password-here'
    CHANGE REQUIRED;

GRANT ROLE kublai_sensitive_access TO kublai_agent;

// Other agents get no access
CREATE USER mongke_agent IF NOT EXISTS SET PASSWORD '...';
GRANT ROLE no_sensitive_access TO mongke_agent;
```

### 5.2 Subgraph Access Control (Neo4j 5.x Enterprise)

```cypher
// Neo4j 5.x Enterprise feature: Subgraph access control
// Allows defining which nodes/relationships a role can see

// Create alias for sensitive data subgraph
CREATE ALIAS sensitive.credentials FOR DATABASE sensitive;

// Define subgraph for credential management
CREATE SUBGRAPH credential_management
    NODES Credential, AccessPolicy
    RELATIONSHIPS HAS_CREDENTIAL, GOVERNED_BY;

// Grant access to subgraph only
GRANT ACCESS ON SUBGRAPH credential_management TO kublai_sensitive_access;

// Deny access to PII subgraph
DENY ACCESS ON SUBGRAPH pii_data TO kublai_sensitive_access;
```

### 5.3 Query-Level Restrictions

```python
class QueryEnforcer:
    """Enforces query-level restrictions for sensitive database."""

    # Forbidden patterns in sensitive DB queries
    FORBIDDEN_PATTERNS = [
        r'RETURN\s+\*',  # No SELECT *
        r'MATCH\s+\(\s*\)',  # No unlabeled nodes
        r'CALL\s+db\.schema',  # No schema introspection
        r'apoc\.export',  # No data export
        r'apoc\.load',  # No data load
    ]

    # Required patterns for sensitive queries
    REQUIRED_PATTERNS = [
        r'WHERE.*operational_uuid',  # Must filter by UUID
    ]

    def validate_query(self, query: str, agent: str) -> bool:
        """Validate query against security policy."""
        import re

        # Check forbidden patterns
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                self._log_violation(agent, query, f"Forbidden pattern: {pattern}")
                return False

        # Check required patterns (for non-admin agents)
        if agent != 'kublai':
            for pattern in self.REQUIRED_PATTERNS:
                if not re.search(pattern, query, re.IGNORECASE):
                    self._log_violation(agent, query, f"Missing required pattern: {pattern}")
                    return False

        return True

    def sanitize_query(self, query: str) -> str:
        """Sanitize query by removing comments and extra whitespace."""
        # Remove Cypher comments
        import re
        query = re.sub(r'//.*$', '', query, flags=re.MULTILINE)
        query = re.sub(r'/\*.*?\*/', '', query, flags=re.DOTALL)
        return query.strip()
```

---

## 6. Performance and Operations

### 6.1 Backup Strategies

```bash
#!/bin/bash
# backup-sensitive-db.sh - Run hourly for sensitive data

SENSITIVE_DB_PATH="/var/lib/neo4j-sensitive"
BACKUP_PATH="/backup/sensitive"
DATE=$(date +%Y%m%d_%H%M%S)

# Online backup using neo4j-admin
neo4j-admin database dump \
    --database=neo4j \
    --to-path="${BACKUP_PATH}/sensitive_${DATE}.dump" \
    --compress \
    --verbose

# Encrypt backup
openssl enc -aes-256-cbc -salt \
    -in "${BACKUP_PATH}/sensitive_${DATE}.dump" \
    -out "${BACKUP_PATH}/sensitive_${DATE}.dump.enc" \
    -pass pass:"${BACKUP_ENCRYPTION_KEY}"

rm "${BACKUP_PATH}/sensitive_${DATE}.dump"

# Sync to offsite (S3 with encryption)
aws s3 cp "${BACKUP_PATH}/sensitive_${DATE}.dump.enc" \
    s3://company-backups/neo4j-sensitive/ \
    --sse aws:kms \
    --kms-key-id alias/neo4j-backup-key

# Cleanup old backups (keep 30 days locally)
find "${BACKUP_PATH}" -name "sensitive_*.dump.enc" -mtime +30 -delete
```

```python
# Incremental backup for audit database (high volume, append-only)
class AuditBackupManager:
    """Manages incremental backups for high-volume audit database."""

    def create_incremental_backup(self, since_timestamp: datetime):
        """Create incremental backup of new audit records."""
        cypher = """
        MATCH (a:AccessAudit)
        WHERE a.timestamp > $since
        RETURN a.id as id,
               a.timestamp as ts,
               a.agent as agent,
               a.action as action,
               a.operational_uuid as op_uuid
        """

        with self.audit_db.session() as session:
            result = session.run(cypher, {'since': since_timestamp.isoformat()})
            records = [dict(r) for r in result]

        # Write to compressed JSONL
        backup_file = f"/backup/audit/incremental_{datetime.utcnow().isoformat()}.jsonl.gz"
        import gzip
        import json

        with gzip.open(backup_file, 'wt') as f:
            for record in records:
                f.write(json.dumps(record) + '\n')

        return backup_file
```

### 6.2 Query Optimization

```cypher
// ============================================================================
// PERFORMANCE INDEXES FOR SENSITIVE DATABASE
// ============================================================================

// Primary lookup indexes
CREATE CONSTRAINT sensitive_data_id IF NOT EXISTS
FOR (s:SensitiveData) REQUIRE s.id IS UNIQUE;

CREATE CONSTRAINT sensitive_data_op_uuid IF NOT EXISTS
FOR (s:SensitiveData) REQUIRE s.operational_uuid IS UNIQUE;

// Query performance indexes
CREATE INDEX sensitive_data_type_lookup IF NOT EXISTS
FOR (s:SensitiveData) ON (s.data_type, s.created_at);

CREATE INDEX sensitive_data_expiry IF NOT EXISTS
FOR (s:SensitiveData) ON (s.expires_at)
WHERE s.expires_at IS NOT NULL;

CREATE INDEX credential_service_lookup IF NOT EXISTS
FOR (c:Credential) ON (c.service_name, c.credential_type);

CREATE INDEX credential_rotation IF NOT EXISTS
FOR (c:Credential) ON (c.rotation_due)
WHERE c.rotation_due IS NOT NULL;

CREATE INDEX pii_type_lookup IF NOT EXISTS
FOR (p:PII) ON (p.pii_type, p.data_subject_id);

CREATE INDEX pii_consent IF NOT EXISTS
FOR (p:PII) ON (p.consent_expires)
WHERE p.consent_expires IS NOT NULL;

CREATE INDEX financial_date_bucket IF NOT EXISTS
FOR (f:FinancialRecord) ON (f.date_bucket, f.record_type);

CREATE INDEX financial_retention IF NOT EXISTS
FOR (f:FinancialRecord) ON (f.retention_until);

// Composite index for common query pattern
CREATE INDEX sensitive_access_stats IF NOT EXISTS
FOR (s:SensitiveData) ON (s.access_count, s.last_accessed);
```

### 6.3 Connection Management

```python
import asyncio
from contextlib import asynccontextmanager
from neo4j import AsyncGraphDatabase
from typing import Optional

class MultiDatabaseConnectionPool:
    """
    Manages connection pools for multiple Neo4j instances.

    Provides:
    - Separate pools per database
    - Health checking
    - Automatic reconnection
    - Query routing
    """

    def __init__(self):
        self.pools = {}
        self.configs = {}

    def register_database(
        self,
        name: str,
        uri: str,
        username: str,
        password: str,
        max_pool_size: int = 10,
        timeout: float = 30.0
    ):
        """Register a database connection pool."""
        self.configs[name] = {
            'uri': uri,
            'auth': (username, password),
            'max_pool_size': max_pool_size,
            'timeout': timeout
        }

        self.pools[name] = AsyncGraphDatabase.driver(
            uri,
            auth=(username, password),
            max_connection_pool_size=max_pool_size,
            connection_timeout=timeout
        )

    async def health_check(self, name: str) -> bool:
        """Check if database is healthy."""
        try:
            pool = self.pools.get(name)
            if not pool:
                return False

            await pool.verify_connectivity()
            return True
        except Exception:
            return False

    @asynccontextmanager
    async def session(self, name: str, database: str = "neo4j"):
        """Get a session from the specified pool."""
        pool = self.pools.get(name)
        if not pool:
            raise ValueError(f"Unknown database: {name}")

        session = None
        try:
            session = pool.session(database=database)
            yield session
        finally:
            if session:
                await session.close()

    async def execute_on_all(
        self,
        query: str,
        parameters: Optional[dict] = None
    ) -> dict:
        """Execute a query on all registered databases."""
        results = {}

        for name in self.pools:
            try:
                async with self.session(name) as session:
                    result = await session.run(query, parameters or {})
                    records = await result.data()
                    results[name] = {'success': True, 'data': records}
            except Exception as e:
                results[name] = {'success': False, 'error': str(e)}

        return results

    async def close_all(self):
        """Close all connection pools."""
        for name, pool in self.pools.items():
            try:
                await pool.close()
            except Exception as e:
                print(f"Error closing pool {name}: {e}")


# Usage in application
async def main():
    pools = MultiDatabaseConnectionPool()

    # Register databases
    pools.register_database(
        'operational',
        'bolt://localhost:7687',
        'neo4j',
        'operational-password'
    )

    pools.register_database(
        'sensitive',
        'bolt://localhost:7688',
        'kublai_agent',
        'sensitive-password',
        max_pool_size=5  # Smaller pool for sensitive data
    )

    pools.register_database(
        'audit',
        'bolt://localhost:7689',
        'audit_writer',
        'audit-password',
        max_pool_size=3
    )

    # Health check all databases
    for name in ['operational', 'sensitive', 'audit']:
        healthy = await pools.health_check(name)
        print(f"{name}: {'healthy' if healthy else 'unhealthy'}")

    # Execute cross-database transaction
    async with pools.session('operational') as op_session, \
               pools.session('sensitive') as sens_session:

        # Get reference from operational
        result = await op_session.run(
            "MATCH (r:SensitiveDataRef {id: $id}) RETURN r.sensitive_uuid as uuid",
            {'id': 'op-uuid-123'}
        )
        record = await result.single()
        sensitive_uuid = record['uuid']

        # Get data from sensitive
        result = await sens_session.run(
            "MATCH (s:SensitiveData {id: $id}) RETURN s",
            {'id': sensitive_uuid}
        )
        data = await result.single()

        return data
```

---

## 7. Complete Implementation Example

### 7.1 Kublai Agent Integration

```python
# kublai_sensitive_access.py
"""
Kublai agent's interface to sensitive data.
All other agents route through Kublai for sensitive data access.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import hashlib
import json

class KublaiSensitiveAccess:
    """
    Kublai's exclusive interface to sensitive database.

    Responsibilities:
    1. Authenticate and authorize all sensitive data requests
    2. Audit all access
    3. Enforce data retention policies
    4. Handle encryption/decryption
    """

    def __init__(self, connection_pools: MultiDatabaseConnectionPool):
        self.pools = connection_pools
        self.reference_manager = ReferenceManager(
            operational_db=pools,
            sensitive_db=pools
        )

    async def store_credential(
        self,
        service_name: str,
        account_identifier: str,
        credential_value: str,
        credential_type: str = "api_key",
        rotation_days: int = 90,
        requested_by: str = "kublai"
    ) -> str:
        """
        Store a new credential in sensitive database.

        Args:
            service_name: e.g., "aws", "github", "stripe"
            account_identifier: Username or account ID
            credential_value: The actual credential (will be encrypted)
            credential_type: Type of credential
            rotation_days: Days until rotation required
            requested_by: Agent requesting storage

        Returns:
            operational_uuid: Reference UUID for operational database
        """
        # Only Kublai can store credentials
        if requested_by != "kublai":
            await self._log_security_event(
                "unauthorized_credential_storage_attempt",
                requested_by,
                {"service": service_name}
            )
            raise PermissionError("Only Kublai can store credentials")

        # Create cross-database reference
        sensitive_data = {
            'service_name': service_name,
            'account_identifier': self._hash_identifier(account_identifier),
            'credential_value': credential_value,
            'credential_type': credential_type
        }

        access_policy = {
            'allowed_agents': ['kublai'],
            'allowed_operations': ['read', 'delete'],
            'require_approval_above': None,
            'audit_level': 'full'
        }

        ref = self.reference_manager.create_reference(
            data_type='credential',
            sensitive_data=sensitive_data,
            access_policy=access_policy,
            ttl_days=rotation_days
        )

        # Create credential-specific node in sensitive DB
        await self._create_credential_node(
            sensitive_uuid=ref.sensitive_uuid,
            service_name=service_name,
            account_identifier=account_identifier,
            credential_type=credential_type,
            rotation_days=rotation_days
        )

        # Log to audit database
        await self._log_access(
            agent=requested_by,
            action='create',
            resource_type='credential',
            operational_uuid=ref.operational_uuid,
            success=True
        )

        return ref.operational_uuid

    async def retrieve_credential(
        self,
        operational_uuid: str,
        purpose: str,
        requested_by: str = "kublai"
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a credential by operational UUID.

        Args:
            operational_uuid: Reference UUID
            purpose: Reason for access (logged)
            requested_by: Agent requesting access

        Returns:
            Credential data or None if not found/unauthorized
        """
        # Only Kublai can retrieve credentials
        if requested_by != "kublai":
            await self._log_security_event(
                "unauthorized_credential_access_attempt",
                requested_by,
                {"operational_uuid": operational_uuid}
            )
            return None

        # Resolve reference and get sensitive data
        data = self.reference_manager.resolve_reference(
            operational_uuid=operational_uuid,
            agent=requested_by,
            purpose=purpose
        )

        if data:
            # Log successful access
            await self._log_access(
                agent=requested_by,
                action='read',
                resource_type='credential',
                operational_uuid=operational_uuid,
                success=True
            )

        return data

    async def store_pii(
        self,
        pii_type: str,
        pii_value: str,
        data_subject_id: str,
        consent_status: str = "granted",
        consent_expires: Optional[datetime] = None,
        requested_by: str = "kublai"
    ) -> str:
        """Store PII with consent tracking."""
        if requested_by != "kublai":
            raise PermissionError("Only Kublai can store PII")

        # Check consent
        if consent_status not in ["granted", "pending"]:
            raise ValueError(f"Invalid consent status: {consent_status}")

        sensitive_data = {
            'pii_type': pii_type,
            'pii_value': pii_value,
            'data_subject_id': self._hash_identifier(data_subject_id),
            'consent_status': consent_status,
            'consent_expires': consent_expires.isoformat() if consent_expires else None
        }

        access_policy = {
            'gdpr_compliant': True,
            'right_to_deletion': True,
            'purpose_limitation': 'operational_only'
        }

        ref = self.reference_manager.create_reference(
            data_type='pii',
            sensitive_data=sensitive_data,
            access_policy=access_policy,
            ttl_days=None  # PII retained per policy, not TTL
        )

        # Create data subject record if not exists
        await self._ensure_data_subject(data_subject_id, consent_status)

        await self._log_access(
            agent=requested_by,
            action='create',
            resource_type='pii',
            operational_uuid=ref.operational_uuid,
            success=True
        )

        return ref.operational_uuid

    async def delete_pii(
        self,
        operational_uuid: str,
        reason: str,
        requested_by: str = "kublai"
    ) -> bool:
        """
        Delete PII (right to be forgotten).

        Args:
            operational_uuid: Reference to PII
            reason: Deletion reason (gdpr_request, retention_expired, etc.)
            requested_by: Agent requesting deletion

        Returns:
            True if deleted, False otherwise
        """
        if requested_by != "kublai":
            return False

        # Get sensitive UUID
        sensitive_uuid = await self._get_sensitive_uuid(operational_uuid)
        if not sensitive_uuid:
            return False

        # Delete from sensitive database
        async with self.pools.session('sensitive') as session:
            await session.run("""
                MATCH (p:PII {id: $id})
                DETACH DELETE p
            """, {'id': sensitive_uuid})

            await session.run("""
                MATCH (s:SensitiveData {id: $id})
                DETACH DELETE s
            """, {'id': sensitive_uuid})

        # Mark reference as deleted in operational DB
        async with self.pools.session('operational') as session:
            await session.run("""
                MATCH (r:SensitiveDataRef {id: $id})
                SET r.deleted = true,
                    r.deleted_at = datetime(),
                    r.deletion_reason = $reason
            """, {'id': operational_uuid, 'reason': reason})

        # Log deletion
        await self._log_access(
            agent=requested_by,
            action='delete',
            resource_type='pii',
            operational_uuid=operational_uuid,
            success=True
        )

        return True

    async def query_financial_records(
        self,
        date_range_start: datetime,
        date_range_end: datetime,
        record_type: Optional[str] = None,
        requested_by: str = "kublai"
    ) -> List[Dict[str, Any]]:
        """
        Query financial records with date filtering.

        Uses time-partitioned labels for efficient querying.
        """
        if requested_by != "kublai":
            return []

        partition_manager = TimePartitionManager(self.pools)

        results = partition_manager.query_by_time_range(
            data_type='FinancialRecord',
            start_date=date_range_start,
            end_date=date_range_end,
            agent=requested_by
        )

        # Filter by record type if specified
        if record_type:
            results = [r for r in results if r.get('record_type') == record_type]

        # Log bulk query
        await self._log_access(
            agent=requested_by,
            action='query',
            resource_type='financial',
            operational_uuid='bulk_query',
            success=True,
            metadata={
                'record_count': len(results),
                'date_range': f"{date_range_start} to {date_range_end}"
            }
        )

        return results

    def _hash_identifier(self, identifier: str) -> str:
        """Create deterministic hash of identifier."""
        return hashlib.sha256(identifier.encode()).hexdigest()[:32]

    async def _log_access(
        self,
        agent: str,
        action: str,
        resource_type: str,
        operational_uuid: str,
        success: bool,
        metadata: Optional[Dict] = None
    ):
        """Log access to audit database."""
        async with self.pools.session('audit') as session:
            await session.run("""
                CREATE (a:AccessAudit {
                    id: randomUUID(),
                    timestamp: datetime(),
                    agent: $agent,
                    action: $action,
                    resource_type: $resource_type,
                    operational_uuid: $op_uuid,
                    success: $success,
                    metadata: $metadata
                })
            """, {
                'agent': agent,
                'action': action,
                'resource_type': resource_type,
                'op_uuid': operational_uuid,
                'success': success,
                'metadata': json.dumps(metadata or {})
            })

    async def _log_security_event(
        self,
        event_type: str,
        agent: str,
        details: Dict[str, Any]
    ):
        """Log security event to audit database."""
        async with self.pools.session('audit') as session:
            await session.run("""
                CREATE (s:SecurityAudit {
                    id: randomUUID(),
                    timestamp: datetime(),
                    event_type: $event_type,
                    severity: 'high',
                    agent: $agent,
                    details: $details,
                    resolved: false
                })
            """, {
                'event_type': event_type,
                'agent': agent,
                'details': json.dumps(details)
            })
```

---

## 8. Deployment Checklist

### 8.1 Infrastructure Setup

```yaml
# docker-compose.yml - Multi-instance Neo4j deployment
version: '3.8'

services:
  neo4j-operational:
    image: neo4j:5.15-community
    container_name: neo4j-operational
    ports:
      - "7687:7687"
      - "7474:7474"
    environment:
      - NEO4J_AUTH=neo4j/operational-password
      - NEO4J_dbms_memory_heap_max__size=4G
      - NEO4J_dbms_memory_pagecache_size=2G
    volumes:
      - operational-data:/data
      - operational-logs:/logs
    networks:
      - neo4j-network

  neo4j-sensitive:
    image: neo4j:5.15-community
    container_name: neo4j-sensitive
    ports:
      - "7688:7687"
      - "7475:7474"
    environment:
      - NEO4J_AUTH=kublai_agent/sensitive-password
      - NEO4J_dbms_memory_heap_max__size=2G
      - NEO4J_dbms_memory_pagecache_size=1G
      - NEO4J_dbms_security_auth__enabled=true
      - NEO4J_dbms_logs_security_level=DEBUG
    volumes:
      - sensitive-data:/data
      - sensitive-logs:/logs
    networks:
      - neo4j-network
    # Additional security: dedicated network segment
    # Firewall rules restrict access to Kublai service only

  neo4j-audit:
    image: neo4j:5.15-community
    container_name: neo4j-audit
    ports:
      - "7689:7687"
      - "7476:7474"
    environment:
      - NEO4J_AUTH=audit_writer/audit-password
      - NEO4J_dbms_memory_heap_max__size=1G
      - NEO4J_dbms_memory_pagecache_size=512M
    volumes:
      - audit-data:/data
      - audit-logs:/logs
    networks:
      - neo4j-network

volumes:
  operational-data:
    driver: local
  sensitive-data:
    driver: local
    # In production, use encrypted volume
  audit-data:
    driver: local

networks:
  neo4j-network:
    driver: bridge
```

### 8.2 Security Configuration

```bash
#!/bin/bash
# setup-sensitive-db-security.sh

# 1. Generate encryption keys
export SENSITIVE_DB_KEY_V1=$(openssl rand -base64 32)
echo "SENSITIVE_DB_KEY_V1=$SENSITIVE_DB_KEY_V1" >> /etc/neo4j-sensitive/.env

# 2. Set up SSL/TLS for sensitive database
mkdir -p /etc/neo4j-sensitive/certificates
cd /etc/neo4j-sensitive/certificates

# Generate self-signed cert (use proper CA in production)
openssl req -newkey rsa:4096 \
    -x509 \
    -sha256 \
    -days 365 \
    -nodes \
    -out neo4j-cert.pem \
    -keyout neo4j-key.pem \
    -subj "/C=US/ST=State/L=City/O=Organization/CN=sensitive-neo4j"

# 3. Configure Neo4j to use SSL
 cat >> /etc/neo4j-sensitive/neo4j.conf << EOF
server.bolt.tls_level=REQUIRED
server.bolt.ssl_policy=default
server.ssl.policy.default.base_directory=/certificates
server.ssl.policy.default.private_key=neo4j-key.pem
server.ssl.policy.default.public_certificate=neo4j-cert.pem
EOF

# 4. Set up firewall rules (only Kublai can access)
iptables -A INPUT -p tcp --dport 7688 -s 10.0.0.5 -j ACCEPT  # Kublai service IP
iptables -A INPUT -p tcp --dport 7688 -j DROP

# 5. Enable audit logging
cat >> /etc/neo4j-sensitive/neo4j.conf << EOF
server.logs.query.enabled=INFO
server.logs.query.threshold=0
server.logs.query.parameter_logging_enabled=false  # Don't log sensitive params
EOF

# 6. Set up backup encryption key
export BACKUP_ENCRYPTION_KEY=$(openssl rand -hex 32)
echo "BACKUP_ENCRYPTION_KEY=$BACKUP_ENCRYPTION_KEY" >> /etc/neo4j-sensitive/.env
```

### 8.3 Monitoring Queries

```cypher
// Monitor sensitive data access patterns
MATCH (a:AccessAudit)
WHERE a.timestamp > datetime() - duration('P1D')
RETURN a.agent as agent,
       a.action as action,
       a.resource_type as resource,
       count(*) as count
ORDER BY count DESC;

// Check for unusual access patterns
MATCH (a:AccessAudit)
WHERE a.timestamp > datetime() - duration('PT1H')
WITH a.agent as agent, count(*) as access_count
WHERE access_count > 100  // Threshold for alerting
RETURN agent, access_count, "High volume access" as alert;

// Monitor credential rotation status
MATCH (c:Credential)
WHERE c.rotation_due < datetime() + duration('P7D')
RETURN c.service_name as service,
       c.rotation_due as due_date,
       CASE
           WHEN c.rotation_due < datetime() THEN 'OVERDUE'
           ELSE 'DUE SOON'
       END as status;

// Check PII consent expiration
MATCH (p:PII)
WHERE p.consent_expires < datetime() + duration('P30D')
RETURN p.pii_type as type,
       p.consent_expires as expires,
       p.data_subject_id as subject;

// Database size monitoring
CALL apoc.meta.stats() YIELD nodeCount, relCount, labels
RETURN nodeCount as total_nodes,
       relCount as relationships,
       labels as distribution;

// Query performance
CALL db.stats.retrieve('QUERIES') YIELD section, data
WHERE section = 'query'
RETURN data.query as query,
       data.invocations as calls,
       data.elapsedTimeMs as total_ms,
       data.elapsedTimeMs / data.invocations as avg_ms
ORDER BY avg_ms DESC
LIMIT 10;
```

---

## 9. Summary

This architecture provides:

1. **True Isolation**: Separate Neo4j instances prevent data leakage through shared resources
2. **UUID-Based References**: Loose coupling allows independent scaling and backup
3. **Time Partitioning**: Efficient multi-year retention with query performance
4. **Kublai-Only Access**: Centralized access control through single trusted agent
5. **Comprehensive Audit**: All access logged to dedicated audit database
6. **Encryption Layers**: At-rest, in-transit, and field-level encryption
7. **Compliance Ready**: GDPR right-to-deletion, consent tracking, retention policies

**Key Files:**
- `/Users/kurultai/molt/docs/plans/neo4j-multi-database-sensitive-data-architecture.md` - This document
- Operational schema: See existing `neo4j.md`
- Cypher queries: `/Users/kurultai/molt/cypher/tiered_memory_queries.cypher`
- Implementation: `memory_manager.py`
