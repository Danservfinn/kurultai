# Kublai Multi-Agent Orchestrator - Pre-Deployment Security Checklist

**Version:** 1.0
**Date:** 2026-02-04
**System:** OpenClaw 6-Agent System with Neo4j Operational Memory
**Classification:** Production Security Requirements

---

## Executive Summary

This checklist ensures the Kublai multi-agent orchestrator system meets security requirements before production deployment. It covers authentication, data protection, network security, dependency scanning, and monitoring.

**OWASP Top 10 Coverage:**
- A01:2021 - Broken Access Control
- A02:2021 - Cryptographic Failures
- A03:2021 - Injection
- A05:2021 - Security Misconfiguration
- A07:2021 - Identification and Authentication Failures
- A09:2021 - Security Logging and Monitoring Failures

---

## 1. SECRETS MANAGEMENT

### 1.1 Required Environment Variables

| Variable | Purpose | Verification Command | Pass Criteria |
|----------|---------|---------------------|---------------|
| `NEO4J_URI` | Neo4j connection URI | `echo $NEO4J_URI` | Must use `bolt+s://` or `neo4j+s://` scheme |
| `NEO4J_PASSWORD` | Neo4j authentication | `python3 -c "import os; print('SET' if os.getenv('NEO4J_PASSWORD') else 'MISSING')"` | Must be set, min 16 chars, not default |
| `OPENCLAW_GATEWAY_TOKEN` | Gateway authentication | `python3 -c "import os; t=os.getenv('OPENCLAW_GATEWAY_TOKEN'); print('VALID' if t and len(t)>=32 else 'INVALID')"` | Min 32 chars, cryptographically random |
| `AGENT_AUTH_SECRET` | Inter-agent authentication | `python3 -c "import os; s=os.getenv('AGENT_AUTH_SECRET'); print('VALID' if s and len(s)>=32 else 'INVALID')"` | Min 32 chars, shared across all agents |
| `NEO4J_FIELD_ENCRYPTION_KEY` | Field-level encryption | `python3 -c "import os; print('SET' if os.getenv('NEO4J_FIELD_ENCRYPTION_KEY') else 'MISSING')"` | Must be set for production |
| `ANONYMIZATION_SALT` | PII anonymization | `python3 -c "import os; print('SET' if os.getenv('ANONYMIZATION_SALT') else 'MISSING')"` | Must be set, consistent across restarts |
| `EMBEDDING_ENCRYPTION_KEY` | Vector embedding encryption | `python3 -c "import os; print('SET' if os.getenv('EMBEDDING_ENCRYPTION_KEY') else 'MISSING')"` | Required for SENSITIVE tier data |

### 1.2 Secrets Validation Commands

```bash
# Check no secrets are in .env files committed to git
git log --all --full-history -- .env 2>/dev/null && echo "FAIL: .env found in git history" || echo "PASS: No .env in git history"

# Verify secrets are not in code
grep -r "sk-live\|AKIA\|ghp_\|xoxb-" --include="*.py" . 2>/dev/null && echo "FAIL: Potential secrets in code" || echo "PASS: No obvious secrets in code"

# Check for default/placeholder passwords
grep -ri "password.*123\|password.*change\|default.*password\|changeme" --include="*.py" --include="*.md" . 2>/dev/null && echo "WARN: Check for default passwords" || echo "PASS: No default password patterns"
```

### 1.3 Pass/Fail Criteria

- [ ] **PASS**: All required environment variables are set
- [ ] **PASS**: No secrets committed to version control
- [ ] **PASS**: Neo4j password is not "password", "neo4j", or default
- [ ] **PASS**: All tokens/secrets are minimum 32 characters
- [ ] **PASS**: Encryption keys are base64-encoded Fernet keys (44 chars)
- [ ] **FAIL** if any secrets are hardcoded in source files

---

## 2. AUTHENTICATION & AUTHORIZATION

### 2.1 Neo4j Authentication

| Check | Command | Expected Result |
|-------|---------|-----------------|
| Neo4j auth enabled | `curl -s http://$NEO4J_HOST:7474/db/data/ | head -1` | Should require authentication (401) |
| Password complexity | `python3 -c "import os; p=os.getenv('NEO4J_PASSWORD'); print('STRONG' if p and len(p)>=16 and any(c.isupper() for c in p) and any(c.islower() for c in p) and any(c.isdigit() for c in p) else 'WEAK')"` | STRONG |
| TLS connection | `python3 -c "from urllib.parse import urlparse; import os; uri=os.getenv('NEO4J_URI',''); print('TLS' if uri.startswith(('bolt+s://','neo4j+s://')) else 'PLAINTEXT')"` | TLS |

### 2.2 OpenClaw Gateway Authentication

| Check | Command | Expected Result |
|-------|---------|-----------------|
| Gateway token set | `python3 -c "import os; print('SET' if os.getenv('OPENCLAW_GATEWAY_TOKEN') else 'MISSING')"` | SET |
| Gateway URL valid | `python3 -c "from urllib.parse import urlparse; import os; url=os.getenv('OPENCLAW_GATEWAY_URL',''); print('VALID' if url.startswith(('http://','https://')) else 'INVALID')"` | VALID |

### 2.3 Agent Role-Based Access Control (RBAC)

Verify agent permissions in `/Users/kurultai/molt/tools/security/access_control.py`:

```python
# Test RBAC configuration
python3 << 'EOF'
from tools.security.access_control import AGENT_ROLES, SENDER_ASSOCIATED_LABELS

# Verify all 6 agents have roles
required_agents = ['main', 'researcher', 'writer', 'developer', 'analyst', 'ops']
missing = [a for a in required_agents if a not in AGENT_ROLES]
print(f"Missing agents: {missing}" if missing else "PASS: All agents have roles")

# Verify sender isolation for non-main agents
for agent in ['researcher', 'writer', 'developer', 'analyst']:
    role = AGENT_ROLES.get(agent, {})
    if role.get('sender_isolation', True):
        print(f"PASS: {agent} has sender isolation")
    else:
        print(f"FAIL: {agent} missing sender isolation")

# Verify main and ops can access all senders
for agent in ['main', 'ops']:
    role = AGENT_ROLES.get(agent, {})
    if not role.get('sender_isolation', True):
        print(f"PASS: {agent} can access all senders")
    else:
        print(f"FAIL: {agent} should not have sender isolation")
EOF
```

### 2.4 Pass/Fail Criteria

- [ ] **PASS**: Neo4j requires authentication (no anonymous access)
- [ ] **PASS**: Neo4j connection uses TLS (`bolt+s://` or `neo4j+s://`)
- [ ] **PASS**: All 6 agents have defined RBAC roles
- [ ] **PASS**: Non-main agents have sender isolation enabled
- [ ] **PASS**: Main and Ops agents can access all senders
- [ ] **PASS**: Gateway token is configured and valid

---

## 3. DATA PROTECTION

### 3.1 PII Detection and Sanitization

Run the PII sanitization tests:

```bash
# Run PII sanitization tests
cd /Users/kurultai/molt
python3 -m pytest tests/security/test_pii_sanitization.py -v
```

**Expected Output:**
```
tests/security/test_pii_sanitization.py::TestPIISanitization::test_sanitization_detects_email_addresses PASSED
tests/security/test_pii_sanitization.py::TestPIISanitization::test_sanitization_detects_phone_numbers PASSED
tests/security/test_pii_sanitization.py::TestPIISanitization::test_sanitization_detects_ssn PASSED
tests/security/test_pii_sanitization.py::TestPIISanitization::test_sanitization_detects_api_keys PASSED
...
```

### 3.2 Field-Level Encryption Verification

```python
# Test field-level encryption
python3 << 'EOF'
from tools.security.encryption import FieldEncryption, EncryptedPropertyManager
import os

# Verify encryption key is set
key = os.getenv('NEO4J_FIELD_ENCRYPTION_KEY')
if not key:
    print("FAIL: NEO4J_FIELD_ENCRYPTION_KEY not set")
else:
    try:
        encryption = FieldEncryption(key)
        # Test encrypt/decrypt
        plaintext = "sensitive test data"
        encrypted = encryption.encrypt(plaintext)
        decrypted = encryption.decrypt(encrypted)

        if decrypted == plaintext and encrypted != plaintext and encrypted.startswith("ENC:"):
            print("PASS: Field-level encryption working")
        else:
            print("FAIL: Encryption/decrypt mismatch")
    except Exception as e:
        print(f"FAIL: Encryption error: {e}")
EOF
```

### 3.3 Privacy Boundary Enforcement

```python
# Test privacy boundaries
python3 << 'EOF'
from tools.security.privacy_boundary import (
    PRIVACY_BOUNDARIES, NEVER_STORE_IN_NEO4J,
    DataClassification, StorageLocation
)

# Verify critical privacy boundaries
required_boundaries = ['task_metadata', 'research_findings', 'personal_relationships',
                       'business_ideas', 'financial_data', 'security_audits']
missing = [b for b in required_boundaries if b not in PRIVACY_BOUNDARIES]
print(f"Missing boundaries: {missing}" if missing else "PASS: All privacy boundaries defined")

# Verify personal relationships are PRIVATE
pr_boundary = PRIVACY_BOUNDARIES.get('personal_relationships')
if pr_boundary and pr_boundary.classification == DataClassification.PRIVATE:
    print("PASS: Personal relationships classified as PRIVATE")
else:
    print("FAIL: Personal relationships should be PRIVATE")

# Verify financial data uses encrypted vault
fin_boundary = PRIVACY_BOUNDARIES.get('financial_data')
if fin_boundary and fin_boundary.storage == StorageLocation.ENCRYPTED_VAULT:
    print("PASS: Financial data requires encrypted vault")
else:
    print("FAIL: Financial data should use encrypted vault")
EOF
```

### 3.4 Embedding Encryption for SENSITIVE Tier

```python
# Test embedding encryption
python3 << 'EOF'
import os
from cryptography.fernet import Fernet

key = os.getenv('EMBEDDING_ENCRYPTION_KEY')
if not key:
    print("WARN: EMBEDDING_ENCRYPTION_KEY not set - SENSITIVE embeddings will be unencrypted")
else:
    try:
        cipher = Fernet(key.encode() if isinstance(key, str) else key)
        test_data = b"test embedding data"
        encrypted = cipher.encrypt(test_data)
        decrypted = cipher.decrypt(encrypted)
        if decrypted == test_data:
            print("PASS: Embedding encryption working")
        else:
            print("FAIL: Embedding encryption/decryption mismatch")
    except Exception as e:
        print(f"FAIL: Embedding encryption error: {e}")
EOF
```

### 3.5 Pass/Fail Criteria

- [ ] **PASS**: All PII sanitization tests pass
- [ ] **PASS**: Field-level encryption is configured and functional
- [ ] **PASS**: Personal relationships marked as PRIVATE (never to Neo4j)
- [ ] **PASS**: Financial data requires encrypted vault storage
- [ ] **PASS**: SENSITIVE tier embedding encryption is available
- [ ] **PASS**: Anonymization salt is set and consistent

---

## 4. INJECTION PREVENTION

### 4.1 Cypher Injection Tests

```bash
# Run injection prevention tests
cd /Users/kurultai/molt
python3 -m pytest tests/security/test_injection_prevention.py -v
```

**Expected Output:**
```
tests/security/test_injection_prevention.py::TestCypherInjection::test_cypher_query_injection_detected PASSED
tests/security/test_injection_prevention.py::TestCypherInjection::test_cypher_tautology_detection PASSED
tests/security/test_injection_prevention.py::TestCommandInjection::test_command_injection_semicolon PASSED
tests/security/test_injection_prevention.py::TestCommandInjection::test_command_injection_pipe PASSED
...
```

### 4.2 Parameterized Query Validation

```python
# Test parameterized query validation
python3 << 'EOF'
from tools.security.injection_prevention import CypherInjectionPrevention, SecureQueryBuilder

# Test dangerous patterns are detected
dangerous_queries = [
    "MATCH (t:Task) RETURN t; DROP TABLE users--",
    "MATCH (t:Task) WHERE t.id = '1' OR '1'='1' RETURN t",
    "MATCH (t:Task) WHERE t.id = $id; DELETE t",
]

validator = CypherInjectionPrevention()
for query in dangerous_queries:
    result = validator.validate_query(query)
    if not result.is_valid:
        print(f"PASS: Detected dangerous query: {query[:40]}...")
    else:
        print(f"FAIL: Missed dangerous query: {query[:40]}...")

# Test safe parameterized queries pass
safe_query = "MATCH (t:Task {id: $task_id}) RETURN t"
result = validator.validate_query(safe_query, allowed_params={"task_id"})
if result.is_valid:
    print("PASS: Safe parameterized query accepted")
else:
    print(f"FAIL: Safe query rejected: {result.errors}")
EOF
```

### 4.3 Pass/Fail Criteria

- [ ] **PASS**: All injection prevention tests pass
- [ ] **PASS**: Dangerous Cypher keywords are blocked
- [ ] **PASS**: String interpolation patterns are detected
- [ ] **PASS**: Parameterized queries are enforced
- [ ] **PASS**: Command injection patterns are blocked

---

## 5. NETWORK SECURITY

### 5.1 Port Configuration

| Service | Port | Protocol | Required | Verification |
|---------|------|----------|----------|--------------|
| OpenClaw Gateway | 18789 | TCP | Yes | `netstat -tlnp 2>/dev/null \| grep 18789` |
| Neo4j Bolt | 7687 | TCP | Yes | `nc -zv $NEO4J_HOST 7687` |
| Neo4j HTTP | 7474 | TCP | Optional | `curl -s http://$NEO4J_HOST:7474` |
| Health Check | 8080 | TCP | Yes | `curl -s http://localhost:8080/health` |

### 5.2 TLS Configuration

```bash
# Verify Neo4j TLS is enabled
python3 << 'EOF'
import os
uri = os.getenv('NEO4J_URI', '')
if uri.startswith(('bolt+s://', 'neo4j+s://')):
    print("PASS: Neo4j using TLS encryption")
elif uri.startswith(('bolt://', 'neo4j://')):
    print("FAIL: Neo4j not using TLS - use bolt+s:// or neo4j+s://")
else:
    print("WARN: Cannot determine Neo4j TLS status")
EOF
```

### 5.3 Firewall Rules

**Required Firewall Configuration:**

| Direction | Port | Source | Action | Purpose |
|-----------|------|--------|--------|---------|
| INBOUND | 18789 | Load Balancer | ALLOW | Gateway API |
| INBOUND | 7687 | Internal Only | ALLOW | Neo4j Bolt |
| INBOUND | 7474 | Admin IPs Only | ALLOW | Neo4j Browser |
| OUTBOUND | 443 | Any | ALLOW | HTTPS APIs |
| OUTBOUND | 80 | Any | DENY | No HTTP |

### 5.4 Pass/Fail Criteria

- [ ] **PASS**: Neo4j uses TLS encryption (`bolt+s://` or `neo4j+s://`)
- [ ] **PASS**: Only required ports are exposed
- [ ] **PASS**: Neo4j HTTP (7474) restricted to admin IPs
- [ ] **PASS**: No plaintext HTTP for external communication
- [ ] **PASS**: Health check endpoint responds correctly

---

## 6. DEPENDENCY VULNERABILITY SCANNING

### 6.1 Python Dependencies

```bash
# Install safety and bandit if not present
pip install safety bandit

# Scan for known vulnerabilities in dependencies
cd /Users/kurultai/molt
safety check -r requirements.txt

# Security linting of Python code
bandit -r . -f json -o bandit-report.json 2>/dev/null || bandit -r . -ll
```

### 6.2 Required Dependency Versions

| Package | Min Version | Security Requirement |
|---------|-------------|---------------------|
| neo4j | 5.15.0 | Latest stable with security fixes |
| cryptography | 41.0.0 | CVE-2023-49083, CVE-2023-50782 fixes |
| pydantic | 2.5.0 | Secure parsing |
| httpx | 0.25.0 | HTTP/2 security |

### 6.3 Dependency Verification

```bash
# Check installed versions
python3 << 'EOF'
import pkg_resources
import sys

required = {
    'neo4j': '5.15.0',
    'cryptography': '41.0.0',
    'pydantic': '2.5.0',
    'httpx': '0.25.0'
}

for package, min_version in required.items():
    try:
        installed = pkg_resources.get_distribution(package)
        if pkg_resources.parse_version(installed.version) >= pkg_resources.parse_version(min_version):
            print(f"PASS: {package} {installed.version} >= {min_version}")
        else:
            print(f"FAIL: {package} {installed.version} < {min_version}")
    except pkg_resources.DistributionNotFound:
        print(f"FAIL: {package} not installed")
EOF
```

### 6.4 Pass/Fail Criteria

- [ ] **PASS**: No high/critical vulnerabilities in dependencies (`safety check`)
- [ ] **PASS**: All required packages meet minimum secure versions
- [ ] **PASS**: Bandit security scan shows no high-severity issues
- [ ] **PASS**: No deprecated or unmaintained dependencies

---

## 7. SECURITY MONITORING & LOGGING

### 7.1 Audit Logging Configuration

```python
# Verify audit logging is configured
python3 << 'EOF'
import os
import logging

# Check audit log settings
audit_enabled = os.getenv('AUDIT_LOG_ENABLED', 'true').lower() == 'true'
audit_level = os.getenv('AUDIT_LOG_LEVEL', 'INFO')

if audit_enabled:
    print(f"PASS: Audit logging enabled at {audit_level} level")
else:
    print("FAIL: Audit logging disabled")

# Verify log directory exists and is writable
log_dir = '/data/workspace/logs' if os.path.exists('/data/workspace') else './logs'
if os.path.exists(log_dir) and os.access(log_dir, os.W_OK):
    print(f"PASS: Log directory {log_dir} exists and is writable")
else:
    print(f"WARN: Log directory {log_dir} not accessible")
EOF
```

### 7.2 Security Event Monitoring

**Required Security Events to Log:**

| Event | Severity | Action |
|-------|----------|--------|
| Authentication failure | HIGH | Alert after 5 failures |
| Permission violation | CRITICAL | Immediate alert |
| Cross-sender access | CRITICAL | Immediate alert |
| Injection attempt detected | HIGH | Alert and block |
| PII detected in output | MEDIUM | Log and sanitize |
| Encryption failure | HIGH | Alert and fallback |
| Circuit breaker opened | MEDIUM | Alert |

### 7.3 Health Check Endpoint

```bash
# Test health check endpoint
curl -s http://localhost:18789/health | python3 -m json.tool

# Expected response:
# {
#     "status": "healthy",
#     "service": "openclaw-agent-config",
#     "timestamp": "2026-02-04T..."
# }
```

### 7.4 Pass/Fail Criteria

- [ ] **PASS**: Audit logging is enabled
- [ ] **PASS**: Log directory exists and is writable
- [ ] **PASS**: Health check endpoint returns 200 OK
- [ ] **PASS**: Security events are defined and logged
- [ ] **PASS**: Permission violations trigger alerts

---

## 8. DEPLOYMENT-SPECIFIC CHECKS

### 8.1 Docker Security

```bash
# Verify Dockerfile security
cd /Users/kurultai/molt

# Check for non-root user
grep -E "^USER\s+\d+" Dockerfile && echo "PASS: Non-root user configured" || echo "FAIL: No non-root user"

# Check for health check
grep -E "^HEALTHCHECK" Dockerfile && echo "PASS: Health check configured" || echo "FAIL: No health check"

# Check for minimal base image
grep "FROM python:.*-slim" Dockerfile && echo "PASS: Using slim base image" || echo "WARN: Consider using slim image"
```

### 8.2 Railway Deployment Security

| Check | Command | Expected |
|-------|---------|----------|
| Environment variables set | `railway variables` | All required vars listed |
| Neo4j password strong | Manual check | Not default, 16+ chars |
| Gateway token set | `railway variables get OPENCLAW_GATEWAY_TOKEN` | Token present |
| Private networking | Railway dashboard | Services on private network |

### 8.3 Pass/Fail Criteria

- [ ] **PASS**: Docker container runs as non-root user (UID 1000)
- [ ] **PASS**: Health check is configured in Dockerfile
- [ ] **PASS**: Using minimal base image (python:3.12-slim)
- [ ] **PASS**: All Railway environment variables are set
- [ ] **PASS**: Services communicate over private network

---

## 9. COMPLETE VERIFICATION SCRIPT

Save and run this comprehensive verification:

```bash
#!/bin/bash
# Kublai Security Deployment Verification Script
# Run this script before production deployment

echo "=========================================="
echo "Kublai Security Deployment Verification"
echo "=========================================="
echo ""

PASS=0
FAIL=0
WARN=0

# Function to check and report
check() {
    if [ $1 -eq 0 ]; then
        echo "[PASS] $2"
        ((PASS++))
    else
        echo "[FAIL] $2"
        ((FAIL++))
    fi
}

warn() {
    echo "[WARN] $1"
    ((WARN++))
}

echo "=== 1. Environment Variables ==="
python3 -c "import os; exit(0 if os.getenv('NEO4J_URI') else 1)" 2>/dev/null
check $? "NEO4J_URI is set"

python3 -c "import os; exit(0 if os.getenv('NEO4J_PASSWORD') else 1)" 2>/dev/null
check $? "NEO4J_PASSWORD is set"

python3 -c "import os; exit(0 if os.getenv('OPENCLAW_GATEWAY_TOKEN') else 1)" 2>/dev/null
check $? "OPENCLAW_GATEWAY_TOKEN is set"

python3 -c "import os; exit(0 if os.getenv('AGENT_AUTH_SECRET') else 1)" 2>/dev/null
check $? "AGENT_AUTH_SECRET is set"

echo ""
echo "=== 2. Neo4j TLS ==="
python3 -c "import os; uri=os.getenv('NEO4J_URI',''); exit(0 if uri.startswith(('bolt+s://','neo4j+s://')) else 1)" 2>/dev/null
check $? "Neo4j using TLS"

echo ""
echo "=== 3. Security Tests ==="
python3 -m pytest tests/security/test_pii_sanitization.py -q --tb=no 2>/dev/null
check $? "PII sanitization tests pass"

python3 -m pytest tests/security/test_injection_prevention.py -q --tb=no 2>/dev/null
check $? "Injection prevention tests pass"

echo ""
echo "=== 4. Docker Security ==="
grep -q "USER 1000" Dockerfile
check $? "Dockerfile uses non-root user"

grep -q "HEALTHCHECK" Dockerfile
check $? "Dockerfile has health check"

echo ""
echo "=========================================="
echo "Results: $PASS passed, $FAIL failed, $WARN warnings"
echo "=========================================="

if [ $FAIL -gt 0 ]; then
    echo "DEPLOYMENT BLOCKED: Fix $FAIL failed checks before deploying"
    exit 1
else
    echo "DEPLOYMENT APPROVED: All security checks passed"
    exit 0
fi
```

---

## 10. SIGN-OFF CHECKLIST

Before deploying to production, obtain sign-off from:

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Security Lead | _____________ | _____________ | _______ |
| DevOps Lead | _____________ | _____________ | _______ |
| System Architect | _____________ | _____________ | _______ |

**Final Verification:**

- [ ] All automated security tests pass
- [ ] Manual penetration testing completed (if required)
- [ ] Security documentation updated
- [ ] Incident response plan in place
- [ ] Backup and recovery tested
- [ ] Rollback procedure documented

---

## Appendix A: Security Test Commands Quick Reference

```bash
# Run all security tests
python3 -m pytest tests/security/ -v

# Run specific test file
python3 -m pytest tests/security/test_pii_sanitization.py -v
python3 -m pytest tests/security/test_injection_prevention.py -v

# Run with coverage
python3 -m pytest tests/security/ --cov=tools.security --cov-report=html

# Security linting
bandit -r tools/security/ -ll

# Dependency vulnerability scan
safety check -r requirements.txt
```

## Appendix B: Security File Locations

| Component | File Path |
|-----------|-----------|
| PII Sanitization | `/Users/kurultai/molt/tests/security/test_pii_sanitization.py` |
| Injection Prevention | `/Users/kurultai/molt/tests/security/test_injection_prevention.py` |
| Encryption Module | `/Users/kurultai/molt/tools/security/encryption.py` |
| Access Control | `/Users/kurultai/molt/tools/security/access_control.py` |
| Anonymization | `/Users/kurultai/molt/tools/security/anonymization.py` |
| Privacy Boundaries | `/Users/kurultai/molt/tools/security/privacy_boundary.py` |
| Injection Prevention | `/Users/kurultai/molt/tools/security/injection_prevention.py` |
| Security Config | `/Users/kurultai/molt/tools/security/config.py` |
| Operational Memory | `/Users/kurultai/molt/openclaw_memory.py` |
| Environment Example | `/Users/kurultai/molt/.env.example` |
| Dockerfile | `/Users/kurultai/molt/Dockerfile` |
| Railway Config | `/Users/kurultai/molt/railway.yml` |

## Appendix C: OWASP Mapping

| OWASP Category | Implementation Location | Verification Test |
|----------------|------------------------|-------------------|
| A01: Broken Access Control | `tools/security/access_control.py` | RBAC tests in test files |
| A02: Cryptographic Failures | `tools/security/encryption.py` | Encryption/decryption tests |
| A03: Injection | `tools/security/injection_prevention.py` | Injection prevention tests |
| A05: Security Misconfiguration | `tools/security/config.py` | Environment validation |
| A07: Authentication Failures | `openclaw_memory.py` | Auth error handling tests |

---

**Document Owner:** Security Team
**Review Cycle:** Quarterly or after major releases
**Last Updated:** 2026-02-04
