# Kublai Multi-Agent Orchestrator - Pre-Deployment Security Checklist

**Version**: 1.0
**Date**: 2026-02-04
**Classification**: CRITICAL - Must complete before production deployment
**OWASP Alignment**: A01-A10, API Security Top 10

---

## Executive Summary

This checklist ensures the Kublai multi-agent orchestrator system meets security standards before production deployment. The system handles sensitive operational data across 6 specialized agents (Kublai, Möngke, Chagatai, Temüjin, Jochi, Ögedei) with Neo4j-backed operational memory.

**Risk Level**: HIGH - Multi-agent system with external integrations (Signal, Neo4j, OpenClaw gateway)

---

## 1. Secrets Management

### 1.1 Environment Variables Verification

| Check | Command/Method | Pass Criteria | Severity |
|-------|----------------|---------------|----------|
| OPENCLAW_GATEWAY_TOKEN set | `echo $OPENCLAW_GATEWAY_TOKEN` | Length >= 32 chars, not default/placeholder | CRITICAL |
| NEO4J_PASSWORD set | `echo $NEO4J_PASSWORD` | Strong password (12+ chars, mixed case, symbols) | CRITICAL |
| AGENT_AUTH_SECRET set | `echo $AGENT_AUTH_SECRET` | Length >= 32 chars, unique per environment | CRITICAL |
| NEO4J_FIELD_ENCRYPTION_KEY set | `echo $NEO4J_FIELD_ENCRYPTION_KEY` | Valid Fernet key (32 bytes base64) | CRITICAL |
| ANONYMIZATION_SALT set | `echo $ANONYMIZATION_SALT` | Unique per deployment | HIGH |
| QUERY_HASH_SALT set | `echo $QUERY_HASH_SALT` | Unique per deployment | HIGH |
| No secrets in .env.example | `grep -i "password\|token\|secret" .env.example` | All values are placeholders | CRITICAL |

**Verification Commands**:
```bash
# Check all required environment variables
python3 << 'EOF'
import os
required = [
    'OPENCLAW_GATEWAY_TOKEN',
    'NEO4J_PASSWORD',
    'AGENT_AUTH_SECRET',
    'NEO4J_FIELD_ENCRYPTION_KEY',
    'ANONYMIZATION_SALT',
    'QUERY_HASH_SALT'
]
missing = [v for v in required if not os.getenv(v)]
if missing:
    print(f"FAIL: Missing variables: {missing}")
else:
    print("PASS: All required environment variables set")
EOF

# Verify token strength
python3 -c "
import os
token = os.getenv('OPENCLAW_GATEWAY_TOKEN', '')
if len(token) >= 32 and token not in ['CHANGE_THIS', 'default', 'test']:
    print('PASS: Gateway token meets length requirement')
else:
    print('FAIL: Gateway token too weak or default')
"
```

### 1.2 Secrets Rotation Policy

| Check | Verification Method | Pass Criteria | Severity |
|-------|---------------------|---------------|----------|
| Rotation schedule documented | Check docs/security/SECRETS_ROTATION.md | Document exists with 90-day schedule | MEDIUM |
| Emergency rotation procedure | Check incident response runbook | Procedure documented | HIGH |
| Old tokens invalidated | Test with old token | Returns 401 Unauthorized | CRITICAL |

### 1.3 Version Control Secrets Scan

| Check | Command | Pass Criteria | Severity |
|-------|---------|---------------|----------|
| No secrets in git history | `git log --all --full-history -- .env` | No .env files committed | CRITICAL |
| No hardcoded credentials | `grep -r "sk-.*[a-zA-Z0-9]{40}" --include="*.py" .` | No matches | CRITICAL |
| No API keys in code | `grep -r "AKIA\|ghp_\|xoxb-" --include="*.py" .` | No matches | CRITICAL |

**Pre-commit Hook Verification**:
```bash
# Install pre-commit hooks for secrets detection
pip install detect-secrets
detect-secrets scan --all-files --force-use-all-plugins > .secrets.baseline
detect-secrets audit .secrets.baseline
```

---

## 2. Authentication & Authorization

### 2.1 OpenClaw Gateway Authentication

| Check | Test Command | Pass Criteria | Severity | OWASP Ref |
|-------|--------------|---------------|----------|-----------|
| Token auth enforced | `curl -H "Authorization: Bearer invalid" $GATEWAY_URL/health` | Returns 401 | CRITICAL | A01 |
| Valid token accepted | `curl -H "Authorization: Bearer $TOKEN" $GATEWAY_URL/health` | Returns 200 | CRITICAL | A01 |
| Token expiration works | Wait for expiry, retry request | Returns 401 | HIGH | A01 |
| Rate limiting active | `for i in {1..1100}; do curl ...; done` | Returns 429 after limit | HIGH | A07 |

**Verification Script**:
```bash
#!/bin/bash
GATEWAY_URL="${OPENCLAW_GATEWAY_URL:-http://localhost:18789}"
TOKEN="$OPENCLAW_GATEWAY_TOKEN"

echo "Testing authentication..."

# Test 1: No token
response=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY_URL/health")
[ "$response" = "401" ] && echo "PASS: No token returns 401" || echo "FAIL: Expected 401, got $response"

# Test 2: Invalid token
response=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer invalid_token" "$GATEWAY_URL/health")
[ "$response" = "401" ] && echo "PASS: Invalid token returns 401" || echo "FAIL: Expected 401, got $response"

# Test 3: Valid token
response=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "$GATEWAY_URL/health")
[ "$response" = "200" ] && echo "PASS: Valid token returns 200" || echo "FAIL: Expected 200, got $response"
```

### 2.2 Agent-to-Agent Authentication

| Check | Verification | Pass Criteria | Severity |
|-------|--------------|---------------|----------|
| Agent whitelist enforced | Check moltbot.json | Only 6 agents in allow list | CRITICAL |
| Cross-agent messages validated | Send message from unauthorized agent | Rejected with 403 | CRITICAL |
| Message signatures verified | Inspect message handling | Signature validation in code | HIGH |

### 2.3 Neo4j Authentication

| Check | Command | Pass Criteria | Severity |
|-------|---------|---------------|----------|
| Auth enabled | `neo4j-admin dbms status` | Authentication required | CRITICAL |
| Default password changed | Try login with 'neo4j/neo4j' | Login fails | CRITICAL |
| Connection uses auth | Check `openclaw_memory.py` | Auth tuple passed to driver | CRITICAL |

### 2.4 Role-Based Access Control (RBAC)

| Agent | Permissions | Sender Isolation | Max Tasks | Verification |
|-------|-------------|------------------|-----------|--------------|
| main (Kublai) | read, write, delete, admin | No (can see all) | 10 | Check `tools/security/access_control.py` |
| researcher (Möngke) | read, write | Yes | 2 | Check `tools/security/access_control.py` |
| writer (Chagatai) | read, write | Yes | 2 | Check `tools/security/access_control.py` |
| developer (Temüjin) | read, write | Yes | 2 | Check `tools/security/access_control.py` |
| analyst (Jochi) | read, write | Yes | 2 | Check `tools/security/access_control.py` |
| ops (Ögedei) | read, write, delete | No | 5 | Check `tools/security/access_control.py` |

**RBAC Verification**:
```python
from tools.security.access_control import AGENT_ROLES

def verify_rbac():
    """Verify RBAC configuration."""
    required_agents = ['main', 'researcher', 'writer', 'developer', 'analyst', 'ops']

    for agent in required_agents:
        if agent not in AGENT_ROLES:
            print(f"FAIL: Agent {agent} not in RBAC")
            return False

        role = AGENT_ROLES[agent]
        if not role.get('permissions'):
            print(f"FAIL: Agent {agent} has no permissions")
            return False

    print("PASS: RBAC configured for all agents")
    return True

verify_rbac()
```

---

## 3. Data Protection

### 3.1 PII Handling & Sanitization

| Check | Test Input | Expected Output | Severity | OWASP Ref |
|-------|------------|-----------------|----------|-----------|
| Email redaction | `user@example.com` | `[EMAIL_*]` or tokenized | CRITICAL | A02 |
| Phone redaction | `555-123-4567` | `[PHONE_*]` or tokenized | CRITICAL | A02 |
| SSN redaction | `123-45-6789` | `[SSN_*]` or `[REDACTED_*]` | CRITICAL | A02 |
| API key redaction | `sk-live-abc123...` | `[API_KEY_*]` | CRITICAL | A02 |
| Credit card redaction | `4111-1111-1111-1111` | `[CREDIT_CARD_*]` | CRITICAL | A02 |
| Name detection | "My friend Sarah's startup" | "My friend [PERSON_*] startup" | HIGH | A02 |

**PII Sanitization Test**:
```python
from tools.security.anonymization import AnonymizationEngine

def test_pii_sanitization():
    engine = AnonymizationEngine(salt=os.getenv('ANONYMIZATION_SALT'))

    test_cases = [
        ("Contact john@example.com", "email"),
        ("Call 555-123-4567", "phone"),
        ("SSN: 123-45-6789", "ssn"),
        ("Key: sk-live-51HvXjbK2NXd", "api_key"),
    ]

    all_pass = True
    for text, pii_type in test_cases:
        entities = engine.detect_pii(text)
        if not any(e.entity_type in [pii_type, f"{pii_type}_us"] for e in entities):
            print(f"FAIL: {pii_type} not detected in: {text}")
            all_pass = False

    if all_pass:
        print("PASS: All PII types detected correctly")
    return all_pass

test_pii_sanitization()
```

### 3.2 Encryption at Rest

| Check | Verification Method | Pass Criteria | Severity |
|-------|---------------------|---------------|----------|
| Neo4j encryption enabled | Check Neo4j config | `dbms.security.encryption=true` | CRITICAL |
| Field encryption working | Store sensitive data, verify format | Data stored as `ENC:R:*` or `ENC:D:*` | CRITICAL |
| Encryption key strength | Check key generation | 256-bit key from Fernet | CRITICAL |
| Key rotation supported | Test `rotate_key()` method | Successful re-encryption | MEDIUM |

**Field Encryption Test**:
```python
from tools.security.encryption import FieldEncryption

def test_field_encryption():
    key = os.getenv('NEO4J_FIELD_ENCRYPTION_KEY')
    if not key:
        print("FAIL: NEO4J_FIELD_ENCRYPTION_KEY not set")
        return False

    encryption = FieldEncryption(master_key=key)

    # Test randomized encryption
    plaintext = "sensitive data"
    encrypted = encryption.encrypt(plaintext, deterministic=False)

    if not encrypted.startswith("ENC:R:"):
        print(f"FAIL: Randomized encryption format wrong: {encrypted}")
        return False

    decrypted = encryption.decrypt(encrypted)
    if decrypted != plaintext:
        print(f"FAIL: Decryption failed")
        return False

    print("PASS: Field encryption working correctly")
    return True

test_field_encryption()
```

### 3.3 Encryption in Transit

| Check | Verification | Pass Criteria | Severity | OWASP Ref |
|-------|--------------|---------------|----------|-----------|
| Neo4j TLS | Check connection URI | Uses `bolt+s://` or `neo4j+s://` | CRITICAL | A02 |
| Gateway HTTPS | Check URL scheme | `https://` in production | CRITICAL | A02 |
| Certificate validation | Check SSL context | `verify_mode` not `CERT_NONE` in prod | CRITICAL | A02 |
| Signal proxy TLS | Check signal-proxy config | TLS 1.2+ enforced | HIGH | A02 |

**TLS Verification**:
```python
from tools.security.config import SecurityConfig

def verify_tls_configuration():
    config = SecurityConfig.from_env()

    issues = []

    # Check Neo4j URI uses TLS
    if not config.NEO4J_URI.startswith(('bolt+s://', 'neo4j+s://')):
        issues.append(f"WARNING: Neo4j URI should use TLS: {config.NEO4J_URI}")

    # Check verify mode
    if config.NEO4J_VERIFY_MODE == "require" and not config.NEO4J_CA_CERT_PATH:
        issues.append("WARNING: TLS verify_mode=require without CA cert (dev mode)")

    if issues:
        for issue in issues:
            print(issue)
        return False

    print("PASS: TLS configuration verified")
    return True

verify_tls_configuration()
```

### 3.4 Sender Isolation

| Check | Test Method | Pass Criteria | Severity |
|-------|-------------|---------------|----------|
| sender_hash required for agents | Query without sender_hash | Rejected for non-main agents | CRITICAL |
| Cross-sender data blocked | Attempt to access other sender's data | Access denied | CRITICAL |
| Main can see all (for synthesis) | Query as main agent | Access granted | HIGH |
| Audit log for cross-sender attempts | Check logs | Violations logged | HIGH |

**Sender Isolation Test**:
```python
from tools.security.access_control import SenderIsolationEnforcer, Neo4jSecurityManager

def test_sender_isolation():
    security = Neo4jSecurityManager(
        uri="bolt://localhost:7687",
        username="neo4j",
        password="test",
        encryption_key="test"
    )
    enforcer = SenderIsolationEnforcer(security)

    query = "MATCH (t:Task) RETURN t"

    # Test 1: Regular agent without sender_hash should fail
    try:
        enforcer.enforce_isolation(query, {}, "researcher", None)
        print("FAIL: Researcher should require sender_hash")
        return False
    except ValueError:
        print("PASS: Researcher requires sender_hash")

    # Test 2: Regular agent with sender_hash should succeed
    try:
        result, params = enforcer.enforce_isolation(query, {}, "researcher", "abc123")
        if "sender_hash" in result and params.get("sender_hash") == "abc123":
            print("PASS: sender_hash filter added correctly")
        else:
            print("FAIL: sender_hash not properly added")
            return False
    except Exception as e:
        print(f"FAIL: Unexpected error: {e}")
        return False

    # Test 3: Main agent without sender_hash should succeed
    try:
        result, params = enforcer.enforce_isolation(query, {}, "main", None)
        if result == query:  # Unchanged
            print("PASS: Main agent bypasses sender isolation")
        else:
            print("FAIL: Main agent query modified unexpectedly")
            return False
    except Exception as e:
        print(f"FAIL: Unexpected error: {e}")
        return False

    return True

test_sender_isolation()
```

---

## 4. Injection Prevention

### 4.1 Cypher Injection Prevention

| Check | Test Input | Expected Result | Severity | OWASP Ref |
|-------|------------|-----------------|----------|-----------|
| String interpolation blocked | `query = f"MATCH (t) WHERE t.id = '{id}'"` | Validation fails | CRITICAL | A03 |
| Comment injection blocked | `"MATCH (t) RETURN t // DELETE ALL"` | Validation fails | CRITICAL | A03 |
| Boolean OR injection blocked | `"' OR '1'='1"` | Sanitized/rejected | CRITICAL | A03 |
| UNION injection blocked | `"UNION ALL MATCH (n)"` | Validation fails | CRITICAL | A03 |
| Parameterized queries enforced | Check all queries use `$param` | All queries pass validation | CRITICAL | A03 |

**Cypher Injection Test**:
```python
from tools.security.injection_prevention import CypherInjectionPrevention

def test_cypher_injection_prevention():
    test_cases = [
        ("MATCH (t:Task {id: $task_id}) RETURN t", True, "Safe query"),
        ('MATCH (t) WHERE t.id = "${user_id}" RETURN t', False, "Template literal"),
        ("MATCH (t) RETURN t // DELETE ALL", False, "Comment injection"),
        ("MATCH (t) WHERE t.id = 'x' OR 1=1 RETURN t", False, "Boolean injection"),
        ("MATCH (t) UNION ALL MATCH (n) RETURN n", False, "UNION injection"),
    ]

    all_pass = True
    for query, should_be_valid, description in test_cases:
        result = CypherInjectionPrevention.validate_query(query)
        if result.is_valid != should_be_valid:
            print(f"FAIL: {description}")
            print(f"  Query: {query}")
            print(f"  Expected valid: {should_be_valid}, Got: {result.is_valid}")
            all_pass = False

    if all_pass:
        print("PASS: All Cypher injection tests passed")
    return all_pass

test_cypher_injection_prevention()
```

### 4.2 Command Injection Prevention

| Check | Test Input | Expected Result | Severity |
|-------|------------|-----------------|----------|
| Semicolon blocked | `"file.txt; rm -rf /"` | ValueError raised | CRITICAL |
| Pipe blocked | `"file.txt | cat /etc/passwd"` | ValueError raised | CRITICAL |
| Backtick blocked | "`whoami`" | ValueError raised | CRITICAL |
| Command substitution blocked | `"$(cat /etc/passwd)"` | ValueError raised | CRITICAL |

### 4.3 Path Traversal Prevention

| Check | Test Input | Expected Result | Severity |
|-------|------------|-----------------|----------|
| Parent directory blocked | `"../../../etc/passwd"` | Pattern detected | CRITICAL |
| URL-encoded traversal blocked | `"%2e%2e%2fetc%2fpasswd"` | Pattern detected | CRITICAL |
| Safe paths allowed | `"uploads/document.pdf"` | No detection | HIGH |

---

## 5. Network Security

### 5.1 Port Configuration

| Service | Port | Protocol | Access Control | Verification |
|---------|------|----------|----------------|--------------|
| OpenClaw Gateway | 18789 | HTTP/HTTPS | Internal/VPN only in prod | `netstat -tlnp` |
| Neo4j Bolt | 7687 | bolt+s:// | Internal network only | Neo4j config |
| Neo4j HTTP | 7474 | HTTPS | Disabled or restricted | Neo4j config |
| Neo4j HTTPS | 7473 | HTTPS | Admin only | Neo4j config |
| Signal Proxy | 8080 | HTTP | Localhost only | Docker config |
| Health Check | 8080 | HTTP | Internal only | Dockerfile |

### 5.2 Firewall Rules

| Rule | Direction | Port | Source | Action |
|------|-----------|------|--------|--------|
| Gateway ingress | Inbound | 18789 | Load balancer/VPN | ALLOW |
| Neo4j ingress | Inbound | 7687 | App servers only | ALLOW |
| Signal proxy | Inbound | 8080 | localhost | ALLOW |
| All other ports | Inbound | * | Any | DENY |

**Firewall Verification**:
```bash
# Check open ports
sudo netstat -tlnp | grep -E "(18789|7687|7474|8080)"

# Check iptables rules (Linux)
sudo iptables -L -n | grep -E "(18789|7687)"

# Check UFW status (Ubuntu)
sudo ufw status verbose
```

### 5.3 TLS Configuration

| Check | Verification | Pass Criteria | Severity |
|-------|--------------|---------------|----------|
| TLS 1.2+ only | `openssl s_client -connect host:port -tls1_1` | Connection fails | CRITICAL |
| Valid certificate | `openssl x509 -in cert.pem -text` | Not expired, correct CN | CRITICAL |
| Strong cipher suites | `nmap --script ssl-enum-ciphers -p 7687 localhost` | No weak ciphers | HIGH |
| HSTS enabled | Check HTTP headers | `Strict-Transport-Security` present | MEDIUM |

---

## 6. Dependency Vulnerability Scanning

### 6.1 Python Dependencies

| Check | Command | Pass Criteria | Severity |
|-------|---------|---------------|----------|
| No critical vulnerabilities | `pip-audit --desc` | 0 critical CVEs | CRITICAL |
| No high vulnerabilities | `pip-audit --desc` | 0 high CVEs | HIGH |
| Dependencies up to date | `pip list --outdated` | Review outdated packages | MEDIUM |
| Known vulnerable packages | `safety check` | No known vulnerabilities | CRITICAL |

**Dependency Scan Commands**:
```bash
# Install scanning tools
pip install pip-audit safety

# Run pip-audit
pip-audit --requirement requirements.txt --desc

# Run safety check
safety check -r requirements.txt

# Check for outdated packages
pip list --outdated
```

### 6.2 Container Security

| Check | Command | Pass Criteria | Severity |
|-------|---------|---------------|----------|
| Base image vulnerabilities | `trivy image python:3.12-slim` | No critical CVEs | CRITICAL |
| Container image scan | `trivy image kublai:latest` | No critical/high CVEs | CRITICAL |
| Non-root user | Check Dockerfile | `USER` directive present | HIGH |
| Minimal attack surface | Check installed packages | No unnecessary packages | MEDIUM |

**Container Scan**:
```bash
# Install Trivy
# See: https://aquasecurity.github.io/trivy/

# Scan base image
trivy image python:3.12-slim

# Scan built image
docker build -t kublai:security-scan .
trivy image kublai:security-scan
```

### 6.3 Neo4j Version Check

| Check | Command | Pass Criteria | Severity |
|-------|---------|---------------|----------|
| Latest stable version | Check Neo4j website | Running latest or recent version | HIGH |
| No known CVEs | Search CVE database | No unpatched vulnerabilities | CRITICAL |

---

## 7. Security Monitoring & Logging

### 7.1 Audit Logging

| Check | Verification | Pass Criteria | Severity |
|-------|--------------|---------------|----------|
| Data access logged | Check `AuditLogger` | All queries logged | HIGH |
| Permission violations logged | Simulate violation | Event in logs | HIGH |
| Cross-sender access detected | Attempt cross-sender query | Critical alert generated | CRITICAL |
| Log retention policy | Check configuration | 90 days minimum | MEDIUM |

### 7.2 Security Event Monitoring

| Event Type | Log Location | Alert Threshold | Severity |
|------------|--------------|-----------------|----------|
| Authentication failures | Application logs | > 5 failures in 5 min | HIGH |
| Permission violations | Security audit log | Any occurrence | CRITICAL |
| Injection attempts | Security audit log | Any occurrence | CRITICAL |
| Rate limit exceeded | Application logs | > 10 violations in 1 min | MEDIUM |
| Neo4j connection failures | Application logs | > 3 failures in 5 min | HIGH |

### 7.3 Log Security

| Check | Verification | Pass Criteria | Severity |
|-------|--------------|---------------|----------|
| No PII in logs | Search logs for email/phone patterns | No raw PII found | CRITICAL |
| No secrets in logs | Search for token/key patterns | No secrets found | CRITICAL |
| Log access restricted | Check file permissions | 640 or stricter | HIGH |
| Centralized logging | Check configuration | Logs forwarded to SIEM | MEDIUM |

**Log Security Verification**:
```bash
# Check for PII in logs
grep -rE "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}" /var/log/kublai/ || echo "No emails found"
grep -rE "\b[0-9]{3}-[0-9]{2}-[0-9]{4}\b" /var/log/kublai/ || echo "No SSNs found"

# Check for secrets
grep -riE "(sk-|pk-|bearer|token|password|secret)" /var/log/kublai/ | grep -v "REDACTED" || echo "No secrets found"

# Check log permissions
ls -la /var/log/kublai/
```

---

## 8. Error Handling & Information Disclosure

### 8.1 Error Message Security

| Check | Test Method | Pass Criteria | Severity | OWASP Ref |
|-------|-------------|---------------|----------|-----------|
| No stack traces to users | Trigger error via API | Generic error message | CRITICAL | A05 |
| No database details exposed | Invalid query | No schema/structure leaked | CRITICAL | A05 |
| No system info exposed | Check error responses | No paths, versions, etc. | HIGH | A05 |
| Sensitive ops logged internally | Check internal logs | Full details for debugging | HIGH | A09 |

### 8.2 Debug Mode Verification

| Check | Verification | Pass Criteria | Severity |
|-------|--------------|---------------|----------|
| Debug mode disabled | Check environment | `DEBUG=false` or unset | CRITICAL |
| No debug endpoints exposed | Port scan | No /debug, /console endpoints | CRITICAL |
| No profiler enabled | Check configuration | Profiling disabled in prod | HIGH |

---

## 9. Backup & Recovery Security

### 9.1 Neo4j Backup Security

| Check | Verification | Pass Criteria | Severity |
|-------|--------------|---------------|----------|
| Encrypted backups | Check backup script | Encryption enabled | CRITICAL |
| Backup access restricted | Check permissions | Only admin access | CRITICAL |
| Offsite backup encryption | Check cloud storage | Client-side encryption | CRITICAL |
| Backup retention | Check policy | 30 days minimum | MEDIUM |

### 9.2 Disaster Recovery

| Check | Verification | Pass Criteria | Severity |
|-------|--------------|---------------|----------|
| Recovery procedure tested | Last test date | Within 90 days | HIGH |
| RTO documented | Check docs | RTO defined | MEDIUM |
| RPO documented | Check docs | RPO defined | MEDIUM |

---

## 10. Compliance & Documentation

### 10.1 Security Documentation

| Document | Location | Status | Required |
|----------|----------|--------|----------|
| Security architecture | `docs/security/ARCHITECTURE.md` | Exists | Yes |
| Incident response plan | `docs/security/INCIDENT_RESPONSE.md` | Exists | Yes |
| Secrets rotation policy | `docs/security/SECRETS_ROTATION.md` | Exists | Recommended |
| Data classification | `tools/security/privacy_boundary.py` | Implemented | Yes |
| Privacy pre-storage checklist | `PRE_NEO4J_CHECKLIST` in privacy_boundary.py | Implemented | Yes |

### 10.2 Privacy Compliance

| Check | Verification | Pass Criteria | Severity |
|-------|--------------|---------------|----------|
| Data retention enforced | Check retention policies | Automatic purging | HIGH |
| GDPR right to erasure | Test delete functionality | Complete removal | HIGH |
| Data classification applied | Check stored data | Classification metadata present | HIGH |
| PII minimization | Review data flows | Only necessary data stored | HIGH |

---

## 11. Deployment-Specific Checks

### 11.1 Railway Deployment

| Check | Verification | Pass Criteria | Severity |
|-------|--------------|---------------|----------|
| Environment variables in Railway dashboard | Check Railway UI | All secrets in env vars, not code | CRITICAL |
| No secrets in railway.json | `cat railway.json` | No hardcoded credentials | CRITICAL |
| Health check endpoint working | `curl /health` | Returns 200 | HIGH |
| Auto-restart on failure | Check Railway config | Enabled | MEDIUM |

### 11.2 Docker Deployment

| Check | Verification | Pass Criteria | Severity |
|-------|--------------|---------------|----------|
| Non-root user | Check Dockerfile | `USER 1000:1000` | HIGH |
| Read-only root filesystem | Check docker-compose | `read_only: true` | MEDIUM |
| No secrets in image layers | `docker history` | No env vars with secrets | CRITICAL |
| Resource limits set | Check docker-compose | Memory/CPU limits defined | MEDIUM |

---

## 12. Security Testing Summary

### 12.1 Automated Security Tests

Run the following test suites before deployment:

```bash
# Run all security tests
pytest tests/security/ -v --tb=short

# Run with coverage
pytest tests/security/ --cov=tools.security --cov-report=html

# Run specific test categories
pytest tests/security/test_pii_sanitization.py -v
pytest tests/security/test_injection_prevention.py -v
pytest tools/security/test_security.py -v
```

### 12.2 Manual Penetration Testing

| Test | Method | Expected Result | Priority |
|------|--------|-----------------|----------|
| SQL/Cypher injection | Use sqlmap or manual testing | No injection possible | P1 |
| Authentication bypass | Attempt token forgery | All attempts fail | P1 |
| Authorization bypass | Access other sender's data | Access denied | P1 |
| Rate limiting | Flood with requests | Rate limited appropriately | P2 |
| Input validation | Fuzzing with invalid inputs | Graceful handling | P2 |

---

## 13. Sign-Off Checklist

Before deploying to production, obtain sign-off from:

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Security Lead (Temüjin) | | | |
| DevOps Lead (Ögedei) | | | |
| Project Owner (Kublai) | | | |

### Final Verification

- [ ] All CRITICAL checks passed
- [ ] All HIGH severity checks passed
- [ ] No CRITICAL or HIGH vulnerabilities in dependencies
- [ ] Security tests passing: `pytest tests/security/ -q`
- [ ] Incident response plan reviewed
- [ ] Rollback procedure tested
- [ ] Monitoring and alerting configured
- [ ] Team trained on security procedures

---

## Appendix A: Quick Reference Commands

```bash
# Full security verification
python3 << 'EOF'
import os
import sys

# Check environment variables
required = ['OPENCLAW_GATEWAY_TOKEN', 'NEO4J_PASSWORD', 'AGENT_AUTH_SECRET',
            'NEO4J_FIELD_ENCRYPTION_KEY', 'ANONYMIZATION_SALT']
missing = [v for v in required if not os.getenv(v)]
if missing:
    print(f"FAIL: Missing: {missing}")
    sys.exit(1)

# Run security tests
import subprocess
result = subprocess.run(['pytest', 'tests/security/', '-q'], capture_output=True)
if result.returncode != 0:
    print("FAIL: Security tests failed")
    print(result.stdout.decode())
    sys.exit(1)

print("PASS: All security checks passed")
EOF

# Dependency vulnerability scan
pip-audit --requirement requirements.txt

# Container scan
trivy image kublai:latest
```

## Appendix B: Security Contacts

| Role | Contact | Escalation |
|------|---------|------------|
| Security Lead | Temüjin (developer agent) | Kublai (main) |
| Infrastructure | Ögedei (ops agent) | Kublai (main) |
| Emergency | On-call rotation | All agents notified |

## Appendix C: Related Documentation

- `/Users/kurultai/molt/tools/security/privacy_boundary.py` - Data classification and privacy rules
- `/Users/kurultai/molt/tools/security/access_control.py` - RBAC implementation
- `/Users/kurultai/molt/tools/security/encryption.py` - Field-level encryption
- `/Users/kurultai/molt/tools/security/injection_prevention.py` - Cypher injection prevention
- `/Users/kurultai/molt/tools/security/anonymization.py` - PII detection and anonymization
- `/Users/kurultai/molt/tests/security/test_pii_sanitization.py` - PII sanitization tests
- `/Users/kurultai/molt/tests/security/test_injection_prevention.py` - Injection prevention tests
- `/Users/kurultai/molt/docs/plans/neo4j.md` - Neo4j implementation with security sections

---

**Document Version History**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-04 | Security Audit | Initial checklist |

**Review Schedule**: Quarterly or after any security incident
