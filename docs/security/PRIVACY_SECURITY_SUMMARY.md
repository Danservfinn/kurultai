# Neo4j Privacy & Security Implementation Summary

> **For**: Kurultai 6-Agent OpenClaw System
> **Focus**: Privacy-preserving memory storage in Neo4j
> **Date**: 2026-02-04

---

## Overview

This implementation provides comprehensive security controls for storing operational memory in Neo4j while protecting sensitive data. It implements defense-in-depth with multiple layers of protection.

---

## Files Created

| File | Purpose |
|------|---------|
| `/Users/kurultai/molt/docs/security/neo4j_privacy_security_audit.md` | Complete security audit report with OWASP references |
| `/Users/kurultai/molt/tools/security/__init__.py` | Module exports |
| `/Users/kurultai/molt/tools/security/privacy_boundary.py` | Data classification and boundary enforcement |
| `/Users/kurultai/molt/tools/security/anonymization.py` | PII detection and anonymization |
| `/Users/kurultai/molt/tools/security/encryption.py` | Field-level encryption |
| `/Users/kurultai/molt/tools/security/tokenization.py` | Reversible tokenization |
| `/Users/kurultai/molt/tools/security/access_control.py` | RBAC and sender isolation |
| `/Users/kurultai/molt/tools/security/injection_prevention.py` | Cypher injection prevention |
| `/Users/kurultai/molt/tools/security/config.py` | Security configuration |
| `/Users/kurultai/molt/tools/security/example_usage.py` | Usage examples |
| `/Users/kurultai/molt/tools/security/test_security.py` | Test suite |

---

## 1. Privacy Boundary Framework

### Data Classification

```python
from tools.security import DataClassification, PRIVACY_BOUNDARIES

# Four classification levels:
PUBLIC       # General knowledge, code patterns - store as-is
OPERATIONAL  # Task metadata - anonymize before storage
SENSITIVE    # Business ideas - tokenize + encrypt
PRIVATE      # Personal relationships - NEVER to Neo4j
```

### What Goes Where

| Data Type | Storage | Protection |
|-----------|---------|------------|
| Code patterns | Neo4j | None needed |
| Task descriptions | Neo4j | Anonymize PII |
| Research findings | Neo4j | Anonymize |
| Business ideas | Neo4j | Tokenize + encrypt |
| Personal relationships | Kublai's files only | Block from Neo4j |
| Financial data | Encrypted vault | Block from Neo4j |

### What NEVER Goes to Neo4j

- Raw phone numbers (use HMAC-SHA256 hash)
- Email addresses
- Personal names of friends/family
- SSN, passport numbers
- Credit card numbers
- API keys, passwords
- Health information
- Precise geolocation

---

## 2. PII Detection and Anonymization

### Usage

```python
from tools.security import AnonymizationEngine

# Initialize with salt (from environment)
engine = AnonymizationEngine(salt=os.getenv("ANONYMIZATION_SALT"))

# Detect PII
text = "My friend Sarah's email is sarah@example.com"
entities = engine.detect_pii(text)
# Returns: [PIIEntity(type='email', value='sarah@example.com', ...)]

# Anonymize (irreversible)
anonymized, _ = engine.anonymize(text, reversible=False)
# Result: "My friend [PERSON_NAME_abc123] email is [EMAIL_def456]"

# Anonymize (reversible with token map)
anonymized, token_map = engine.anonymize(text, reversible=True)
# Can restore: engine.deanonymize(anonymized, token_map)
```

### Detected PII Types

- Email addresses
- Phone numbers (US and international)
- SSN (with and without dashes)
- Credit card numbers
- API keys (OpenAI, generic)
- URLs with embedded credentials
- IP addresses
- Cryptocurrency addresses
- Names in context ("My friend X")

---

## 3. Field-Level Encryption

### Usage

```python
from tools.security import FieldEncryption

# Initialize
encryption = FieldEncryption(
    master_key=os.getenv("NEO4J_FIELD_ENCRYPTION_KEY")
)

# Encrypt (randomized - more secure, cannot query)
encrypted = encryption.encrypt("sensitive data", deterministic=False)
# Result: "ENC:R:gAAAAAB..."

# Encrypt (deterministic - allows equality queries)
encrypted = encryption.encrypt("sensitive data", deterministic=True)
# Result: "ENC:D:..."

# Decrypt
decrypted = encryption.decrypt(encrypted)
# Result: "sensitive data"
```

### EncryptedPropertyManager

```python
from tools.security import EncryptedPropertyManager

manager = EncryptedPropertyManager(encryption_key)

# Prepare node properties with selective encryption
properties = {
    "name": "Task description",
    "sensitive_details": "confidential info",
    "public_field": "safe data"
}

encrypted_props = manager.prepare_node_properties(
    properties,
    encrypted_fields=["sensitive_details"],
    queryable_fields=[]  # Can query on these with hash
)
```

---

## 4. Tokenization (Reversible Anonymization)

### Usage

```python
from tools.security import TokenizationService
import redis

# Initialize with vault backend
vault = redis.Redis(host='localhost', port=6379, db=0)
tokenizer = TokenizationService(vault, ttl_days=90)

# Create token
token = tokenizer.tokenize("Acme Corp", context="company_name")
# Result: "TKN:COMPANY_NAME:a1b2c3d4"

# Store token in Neo4j (safe)

# Later, recover original
detokenized = tokenizer.detokenize(token)
# Result: "Acme Corp"
```

---

## 5. Access Control and Sender Isolation

### Agent Roles

```python
from tools.security import AGENT_ROLES, Neo4jSecurityManager

# Each agent has defined permissions:
AGENT_ROLES = {
    "main": {
        "permissions": ["read", "write", "delete", "admin"],
        "sender_isolation": False,  # Can see all senders
    },
    "researcher": {
        "permissions": ["read", "write"],
        "sender_isolation": True,   # Isolated to one sender
        "allowed_labels": ["Research", "Concept", "Task"]
    },
    # ... etc
}
```

### Sender Isolation Enforcement

```python
from tools.security import SenderIsolationEnforcer

enforcer = SenderIsolationEnforcer(security_manager)

# All queries from regular agents get sender_hash filter added
query = "MATCH (t:Task) WHERE t.status = 'pending' RETURN t"
safe_query, params = enforcer.enforce_isolation(
    query, {}, agent_id="researcher", sender_hash="abc123"
)
# Result: "MATCH (t:Task) WHERE sender_hash = $sender_hash AND ..."
```

---

## 6. Cypher Injection Prevention

### Secure Query Builder

```python
from tools.security import SecureQueryBuilder

builder = SecureQueryBuilder()

query, params = (builder
    .match("(t:Task)")
    .where("t.id = $task_id", task_id=user_input)  # Auto-sanitized
    .and_where("t.status = $status", status="pending")
    .return_("t")
    .build()
)

# Query is validated for injection attempts
# Parameters are automatically sanitized
```

### Manual Validation

```python
from tools.security import CypherInjectionPrevention

result = CypherInjectionPrevention.validate_query(query)
if not result.is_valid:
    raise CypherInjectionError(result.errors[0])

# Sanitize individual parameters
safe_value = CypherInjectionPrevention.sanitize_parameter(
    "description", user_input
)
```

---

## 7. Complete Privacy Pipeline

### Usage Example

```python
from tools.security import (
    AnonymizationEngine,
    TokenizationService,
    FieldEncryption,
    HybridPrivacyProcessor,
    apply_privacy_boundary
)

# Initialize components
processor = HybridPrivacyProcessor(
    anonymizer=AnonymizationEngine(salt="..."),
    tokenizer=TokenizationService(vault),
    encryption=FieldEncryption(key="...")
)

# Process data for Neo4j
task_data = {
    "description": "My friend Sarah's startup idea at sarah@example.com"
}

try:
    processed, metadata = await processor.process_for_neo4j(
        task_data, "task_metadata"
    )
    # processed["description"] = "My friend [PERSON_NAME_abc] startup..."
    # metadata shows processing steps and detected PII
except PrivacyBlockedError:
    # Data classified as PRIVATE - store in Kublai's files instead
    pass
```

---

## 8. Environment Variables

```bash
# Required
NEO4J_FIELD_ENCRYPTION_KEY="base64-encoded-fernet-key"
ANONYMIZATION_SALT="random-salt-for-consistent-hashing"
NEO4J_PASSWORD="neo4j-password"

# Optional
QUERY_HASH_SALT="salt-for-query-hashes"
TOKEN_VAULT_URL="redis://localhost:6379"
TOKEN_TTL_DAYS="90"
NEO4J_URI="bolt+s://localhost:7687"
NEO4J_VERIFY_MODE="verify-full"
NEO4J_CA_CERT_PATH="/path/to/ca-cert.pem"
```

---

## 9. Integration with Existing Code

### Before (Current)

```python
# Kublai creates task directly
task_id = memory.create_task(
    description=user_message,  # May contain PII!
    sender_hash=sender_hash
)
```

### After (With Privacy Protection)

```python
from tools.security import (
    HybridPrivacyProcessor,
    apply_privacy_boundary
)

# Process through privacy pipeline
processed_data, metadata = await apply_privacy_boundary(
    data={"description": user_message},
    data_type="task_metadata",
    sender_hash=sender_hash,
    privacy_processor=privacy_processor
)

# Now safe to store in Neo4j
task_id = memory.create_task(**processed_data)
```

---

## 10. Security Checklist

Before deploying to production:

- [ ] Generate and set `NEO4J_FIELD_ENCRYPTION_KEY`
- [ ] Generate and set `ANONYMIZATION_SALT`
- [ ] Configure Neo4j with TLS (bolt+s://)
- [ ] Set up token vault (Redis or HashiCorp Vault)
- [ ] Enable audit logging
- [ ] Review all data types in `PRIVACY_BOUNDARIES`
- [ ] Test PII detection on sample data
- [ ] Verify sender isolation on all queries
- [ ] Run security test suite
- [ ] Document data retention policies

---

## 11. OWASP Coverage

| OWASP Category | Implementation |
|----------------|----------------|
| A01:2021-Broken Access Control | Sender isolation, RBAC |
| A02:2021-Cryptographic Failures | Field-level encryption, TLS |
| A03:2021-Injection | Query validation, parameterized queries |
| A05:2021-Security Misconfiguration | Config validation, secure defaults |

---

## 12. Next Steps

1. **Review** the full audit report: `/Users/kurultai/molt/docs/security/neo4j_privacy_security_audit.md`
2. **Test** the example: `python -m tools.security.example_usage`
3. **Integrate** privacy pipeline into task creation flow
4. **Configure** environment variables for production
5. **Set up** Redis or HashiCorp Vault for tokenization
6. **Enable** audit logging
7. **Train** Kublai agent on privacy rules

---

*For questions or issues, refer to the detailed audit report or security module documentation.*
