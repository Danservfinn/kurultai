# Kublai System Pre-Deployment Infrastructure Checklist

> **Version**: 1.0
> **Date**: 2026-02-04
> **Status**: Production Ready
> **System**: OpenClaw 6-Agent Multi-Agent System with Neo4j

---

## Table of Contents

1. [Neo4j Deployment Requirements](#1-neo4j-deployment-requirements)
2. [Authentik Biometric Authentication](#2-authentik-biometric-authentication)
3. [Python Environment Requirements](#3-python-environment-requirements)
4. [Environment Variable Configuration](#4-environment-variable-configuration)
5. [Health Check Endpoints](#5-health-check-endpoints)
6. [Monitoring and Observability Setup](#6-monitoring-and-observability-setup)
7. [Backup and Disaster Recovery](#7-backup-and-disaster-recovery)
8. [Scaling Considerations](#8-scaling-considerations)
9. [Pre-Deployment Verification Commands](#9-pre-deployment-verification-commands)

---

## 1. Neo4j Deployment Requirements

### 1.1 Version Requirements

| Component | Required Version | Verification Command |
|-----------|------------------|---------------------|
| Neo4j Database | 5.x Community or Enterprise | `neo4j-admin --version` |
| Neo4j Python Driver | >=5.15.0 | `pip show neo4j` |
| APOC Plugin | 5.x compatible | Check Neo4j Browser `:apoc` |
| GDS Plugin | 5.x compatible | Check Neo4j Browser `:gds` |

**Verification Commands:**
```bash
# Check Neo4j version
neo4j-admin --version

# Check Python driver version
python -c "import neo4j; print(neo4j.__version__)"

# Verify APOC is installed
cypher-shell -u neo4j -p $NEO4J_PASSWORD "RETURN apoc.version()"
```

### 1.2 Hardware Requirements

| Environment | CPU | Memory | Storage | Network |
|-------------|-----|--------|---------|---------|
| **Development** | 1 core | 2 GB RAM | 10 GB SSD | 100 Mbps |
| **Production (Single)** | 2 cores | 4 GB RAM | 50 GB SSD | 1 Gbps |
| **Production (Cluster)** | 4 cores per node | 8 GB RAM per node | 100 GB SSD per node | 10 Gbps |

**Railway Configuration (Current):**
- CPU: 1 core
- Memory: 2Gi (with 512m heap + 512m pagecache)
- Storage: 20Gi volume

### 1.3 Neo4j Configuration

**Required Settings:**
```properties
# Memory Settings
NEO4J_dbms_memory_heap_initial__size=512m
NEO4J_dbms_memory_heap_max__size=1G
NEO4J_dbms_memory_pagecache_size=512m

# Network Settings
NEO4J_dbms_default__listen__address=0.0.0.0

# Authentication
NEO4J_AUTH=neo4j/${NEO4J_PASSWORD}

# Plugins
NEO4J_PLUGINS=["apoc", "gds"]

# Logging
NEO4J_dbms_logs_debug_level=INFO
```

**Verification Commands:**
```bash
# Check Neo4j configuration
cypher-shell -u neo4j -p $NEO4J_PASSWORD "CALL dbms.listConfig() YIELD name, value RETURN name, value ORDER BY name"

# Verify memory settings
cypher-shell -u neo4j -p $NEO4J_PASSWORD "CALL dbms.memory.listPools()"

# Check active plugins
cypher-shell -u neo4j -p $NEO4J_PASSWORD "CALL dbms.procedures() YIELD name RETURN name LIMIT 20"
```

### 1.4 Clustering (Optional for Production)

**For High Availability:**
- Minimum 3 core servers for causal clustering
- 2 read replicas minimum
- Separate discovery and transaction listeners
- SSL/TLS for intra-cluster communication

**Verification Commands:**
```bash
# Check cluster status (if clustered)
cypher-shell -u neo4j -p $NEO4J_PASSWORD "CALL dbms.cluster.overview()"

# Check cluster health
cypher-shell -u neo4j -p $NEO4J_PASSWORD "CALL dbms.cluster.health()"
```

---

## 2. Authentik Biometric Authentication

### 2.1 Authentik Deployment Requirements

**Services:**
| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| authentik-db | postgres:15-alpine | 5432 | PostgreSQL database |
| authentik-server | ghcr.io/goauthentik/server:2025.10 | 9000 | Identity provider |
| authentik-worker | ghcr.io/goauthentik/server:2025.10 | - | Background tasks |
| authentik-proxy | caddy:2-alpine | 8080 | Reverse proxy with forward auth |

**Hardware Requirements:**
| Environment | CPU | Memory | Storage |
|-------------|-----|--------|---------|
| **Production** | 2 cores total | 3Gi total | 15Gi (10Gi DB + 5Gi misc) |
| - authentik-db | 0.5 core | 512Mi | 10Gi |
| - authentik-server | 0.5 core | 1Gi | - |
| - authentik-worker | 0.25 core | 512Mi | - |
| - authentik-proxy | 0.25 core | 256Mi | - |

**Verification Commands:**
```bash
# Check Authentik version
railway logs --service authentik-server | grep "authentik"

# Verify database connection
railway connect authentik-db
pg_isready -U postgres -d authentik

# Check all services are running
railway status
```

### 2.2 Environment Variables

**Required Variables:**
| Variable | Required | Description |
|----------|----------|-------------|
| `AUTHENTIK_SECRET_KEY` | Yes | 50+ char encryption key |
| `AUTHENTIK_BOOTSTRAP_PASSWORD` | Yes | Initial admin password |
| `AUTHENTIK_EXTERNAL_HOST` | Yes | https://kublai.kurult.ai |
| `AUTHENTIK_POSTGRESQL__HOST` | Yes | authentik-db.railway.internal |
| `AUTHENTIK_POSTGRESQL__NAME` | Yes | Database name |
| `AUTHENTIK_POSTGRESQL__USER` | Yes | Database user |
| `AUTHENTIK_POSTGRESQL__PASSWORD` | Yes | Database password |
| `SIGNAL_LINK_TOKEN` | Yes | SSE endpoint auth token |

**Verification Commands:**
```bash
# Check all required variables are set
for var in AUTHENTIK_SECRET_KEY AUTHENTIK_BOOTSTRAP_PASSWORD AUTHENTIK_EXTERNAL_HOST \
           AUTHENTIK_POSTGRESQL__PASSWORD SIGNAL_LINK_TOKEN; do
  if [ -n "${!var}" ]; then
    echo "✓ $var is set"
  else
    echo "✗ $var is NOT set"
  fi
done

# Verify secret key length
if [ ${#AUTHENTIK_SECRET_KEY} -ge 50 ]; then
  echo "✓ AUTHENTIK_SECRET_KEY is ${#AUTHENTIK_SECRET_KEY} chars (OK)"
else
  echo "✗ AUTHENTIK_SECRET_KEY is only ${#AUTHENTIK_SECRET_KEY} chars (need 50+)"
fi
```

### 2.3 Health Check Endpoints

| Service | Endpoint | Port |
|---------|----------|------|
| authentik-server | `/-/health/ready/` | 9000 |
| authentik-proxy | `/health` | 8080 |
| authentik-db | `pg_isready` | 5432 |

**Verification Commands:**
```bash
# Test Authentik server health
curl -f http://authentik-server.railway.internal:9000/-/health/ready/

# Test proxy health
curl -f http://authentik-proxy.railway.internal:8080/health

# Test database
railway connect authentik-db -- pg_isready -U postgres -d authentik
```

### 2.4 WebAuthn Configuration

**Browser Requirements:**
- Chrome 67+, Firefox 60+, Safari 13+, Edge 79+
- HTTPS required (not localhost)
- Platform authenticator (Face ID, Touch ID) or roaming authenticator (YubiKey)

**Verification Steps:**
1. Access `https://kublai.kurult.ai/if/admin/`
2. Login with akadmin credentials
3. Navigate to **Flows & Stages → Stages**
4. Verify WebAuthn stage exists and is configured
5. Test biometric registration on supported device

**Troubleshooting:**
```bash
# Check WebAuthn configuration
python authentik-proxy/bootstrap_authentik.py --check-only

# Verify external host uses HTTPS
echo $AUTHENTIK_EXTERNAL_HOST | grep -q "^https://" && echo "✓ HTTPS enabled" || echo "✗ Must use HTTPS"

# Check browser compatibility
curl -s https://kublai.kurult.ai/if/flow/kublai-webauthn-auth/ | head -20
```

### 2.5 Backup and Recovery

**Automated Backups:**
```bash
# Run backup script
./scripts/backup-authentik-db.sh

# Configure cron (via Railway)
railway cron create "0 2 * * *" --command "./scripts/backup-authentik-db.sh"
```

**Restore Procedure:**
```bash
# Restore from backup
gunzip < authentik_backup_YYYYMMDD_HHMMSS.sql.gz | \
  railway connect authentik-db -- psql -U postgres -d authentik
```

**Verification:**
```bash
# List backups
ls -la /backups/authentik/

# Verify backup integrity
aws s3 ls s3://$R2_BUCKET/authentik/db/ --endpoint-url $R2_ENDPOINT
```

### 2.6 Security Checklist

- [ ] AUTHENTIK_SECRET_KEY is 50+ random characters
- [ ] AUTHENTIK_BOOTSTRAP_PASSWORD changed after first login
- [ ] HTTPS enforced (AUTHENTIK_EXTERNAL_HOST uses https://)
- [ ] Rate limiting configured in Authentik admin
- [ ] Session timeout set to 24 hours
- [ ] Audit logging enabled
- [ ] Database backups configured
- [ ] Signal SSE endpoint token is unique and random

---

## 3. Python Environment Requirements

### 2.1 Python Version

| Requirement | Version | Verification |
|-------------|---------|--------------|
| Python | 3.11, 3.12, or 3.13 | `python --version` |
| pip | Latest | `pip --version` |
| setuptools | Latest | `pip show setuptools` |

**Verification Commands:**
```bash
# Check Python version
python --version  # Should be 3.11+

# Verify pip is up to date
python -m pip install --upgrade pip

# Check all Python versions (if using pyenv)
pyenv versions
```

### 2.2 Core Dependencies

From `/Users/kurultai/molt/requirements.txt`:

| Package | Minimum Version | Purpose |
|---------|-----------------|---------|
| neo4j | >=5.15.0 | Database driver |
| pydantic | >=2.5.0 | Data validation |
| pydantic-settings | >=2.1.0 | Configuration management |
| httpx | >=0.25.0 | HTTP client |
| python-dotenv | >=1.0.0 | Environment variables |
| structlog | >=23.2.0 | Structured logging |
| tenacity | >=8.2.0 | Retry logic |
| pyyaml | >=6.0.1 | YAML parsing |
| anyio | >=4.0.0 | Async support |
| python-dateutil | >=2.8.2 | Date/time handling |
| orjson | >=3.9.0 | JSON processing |
| cryptography | >=41.0.0 | Secure token handling |

**Verification Commands:**
```bash
# Install dependencies
pip install -r requirements.txt

# Verify all packages installed
pip list | grep -E "neo4j|pydantic|httpx|python-dotenv|structlog|tenacity|pyyaml|anyio|dateutil|orjson|cryptography"

# Check for dependency conflicts
pip check

# Generate dependency tree
pipdeptree  # Requires: pip install pipdeptree
```

### 2.3 Test Dependencies (for CI/CD)

From `/Users/kurultai/molt/test-requirements.txt`:

| Package | Minimum Version | Purpose |
|---------|-----------------|---------|
| pytest | >=7.4.0 | Testing framework |
| pytest-cov | >=4.1.0 | Coverage reporting |
| pytest-asyncio | >=0.21.0 | Async testing |
| pytest-xdist | >=3.5.0 | Parallel execution |
| testcontainers | >=4.5.0 | Docker-based integration tests |
| mypy | >=1.8.0 | Type checking |
| bandit | >=1.7.0 | Security linting |
| safety | >=2.3.0 | Vulnerability scanning |

**Verification Commands:**
```bash
# Install test dependencies
pip install -r test-requirements.txt

# Run tests
pytest --version
pytest -v --tb=short

# Run with coverage
pytest --cov --cov-report=term-missing --cov-fail-under=80

# Security scan
bandit -r . -f json -o bandit-report.json || true
safety check || true

# Type check
mypy openclaw_memory.py tools/ || true
```

### 2.4 Docker Requirements

**Dockerfile Configuration:**
- Base Image: `python:3.12-slim`
- User: Non-root (UID 1000)
- Working Directory: `/app`
- Exposed Ports: 8080, 18789

**Verification Commands:**
```bash
# Build Docker image
docker build -t kublai-system:latest .

# Verify image built
docker images | grep kublai

# Run container locally
docker run -p 18789:18789 --env-file .env kublai-system:latest

# Check container health
docker ps
docker exec <container_id> curl -f http://localhost:18789/health
```

---

## 3. Environment Variable Configuration

### 3.1 Required Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEO4J_URI` | Yes | `bolt://localhost:7687` | Neo4j connection URI |
| `NEO4J_USER` | Yes | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | Yes | - | Neo4j password (16+ chars) |
| `NEO4J_DATABASE` | No | `neo4j` | Neo4j database name |
| `OPENCLAW_GATEWAY_URL` | Yes | - | Gateway URL |
| `OPENCLAW_GATEWAY_TOKEN` | Yes | - | Secure auth token (64 hex chars) |
| `AGENT_AUTH_SECRET` | Yes | - | Agent-to-agent auth (32+ chars) |
| `LOG_LEVEL` | No | `info` | Logging level |
| `PROMETHEUS_PORT` | No | `9090` | Metrics port |

### 3.2 Optional Environment Variables

| Variable | Purpose |
|----------|---------|
| `SIGNAL_ACCOUNT_NUMBER` | Signal messenger integration |
| `SIGNAL_CLI_PATH` | Path to signal-cli binary |
| `ADMIN_PHONE_1` | Primary admin phone number |
| `ADMIN_PHONE_2` | Secondary admin phone number |
| `NOTION_API_TOKEN` | Notion integration |
| `NOTION_DATABASE_ID` | Notion database ID |
| `MOONSHOT_API_KEY` | LLM API key |

### 3.3 Environment Variable Verification

**Verification Commands:**
```bash
# Check .env file exists and is readable
ls -la .env

# Verify no secrets are committed
grep -r "NEO4J_PASSWORD\|OPENCLAW_GATEWAY_TOKEN\|AGENT_AUTH_SECRET" . --include="*.py" --include="*.yml" --include="*.yaml" | grep -v ".env"

# Load and verify environment
python -c "
import os
from dotenv import load_dotenv
load_dotenv()

required = ['NEO4J_URI', 'NEO4J_USER', 'NEO4J_PASSWORD', 'OPENCLAW_GATEWAY_URL', 'OPENCLAW_GATEWAY_TOKEN', 'AGENT_AUTH_SECRET']
missing = [var for var in required if not os.getenv(var)]

if missing:
    print(f'MISSING: {missing}')
    exit(1)
else:
    print('All required environment variables set')
    print(f'NEO4J_URI: {os.getenv(\"NEO4J_URI\")}')
    print(f'LOG_LEVEL: {os.getenv(\"LOG_LEVEL\", \"info\")}')
"

# Generate secure tokens (if needed)
openssl rand -hex 32  # For AGENT_AUTH_SECRET
openssl rand -hex 32  # For OPENCLAW_GATEWAY_TOKEN

# Validate password strength
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
pwd = os.getenv('NEO4J_PASSWORD', '')
if len(pwd) < 16:
    print(f'WARNING: NEO4J_PASSWORD is only {len(pwd)} chars (recommended: 16+)')
else:
    print(f'NEO4J_PASSWORD length: {len(pwd)} chars (OK)')
"
```

### 3.4 Railway-Specific Configuration

From `/Users/kurultai/molt/railway.yml`:

```yaml
environment:
  - name: NEO4J_URI
    value: "bolt://neo4j:7687"
  - name: NEO4J_USER
    value: "neo4j"
  - name: NEO4J_AUTH
    value: ${NEO4J_USER}/${NEO4J_PASSWORD}
```

**Verification Commands:**
```bash
# Validate railway.yml syntax
railway check  # Requires Railway CLI

# Preview environment variables
railway variables  # Requires Railway CLI
```

---

## 4. Health Check Endpoints

### 4.1 Moltbot Service Health Check

**Endpoint:** `GET /health`
**Port:** 18789
**File:** `/Users/kurultai/molt/health_server.py`

**Expected Response:**
```json
{
  "status": "healthy",
  "service": "openclaw-agent-config",
  "timestamp": "2026-02-04T12:00:00.000000"
}
```

**Railway Configuration:**
```yaml
healthcheck:
  path: /health
  port: 18789
  interval: 30s
  timeout: 10s
  startPeriod: 5s
  retries: 3
```

### 4.2 Neo4j Health Check

**Endpoint:** `GET /db/manage/server/jmx/domain/org.neo4j/instance%3Dkernel%230%2Cname%3DDiagnostics`
**Port:** 7474

**Railway Configuration:**
```yaml
healthcheck:
  path: /db/manage/server/jmx/domain/org.neo4j/instance%3Dkernel%230%2Cname%3DDiagnostics
  port: 7474
  interval: 30s
  timeout: 10s
  startPeriod: 60s
  retries: 5
```

### 4.3 Application-Level Health Check

From `/Users/kurultai/molt/openclaw_memory.py`:

**Method:** `OperationalMemory.health_check()`

**Returns:**
```python
{
    "status": "healthy",  # or "degraded", "unavailable"
    "connected": True,
    "writable": True,
    "response_time_ms": 15.2,
    "error": None,
    "timestamp": "2026-02-04T12:00:00+00:00"
}
```

### 4.4 Health Check Verification Commands

```bash
# Test moltbot health (local)
curl -f http://localhost:18789/health | jq

# Test moltbot health (Railway)
curl -f https://<railway-domain>.railway.app/health | jq

# Test Neo4j HTTP endpoint
curl -u neo4j:$NEO4J_PASSWORD http://localhost:7474/db/manage/server/jmx/domain/org.neo4j/instance%3Dkernel%230%2Cname%3DDiagnostics

# Test Neo4j Bolt connectivity
cypher-shell -u neo4j -p $NEO4J_PASSWORD "RETURN 1 as health_check"

# Application-level health check
python -c "
import os
from dotenv import load_dotenv
load_dotenv()

from openclaw_memory import OperationalMemory

memory = OperationalMemory(
    uri=os.getenv('NEO4J_URI'),
    username=os.getenv('NEO4J_USER'),
    password=os.getenv('NEO4J_PASSWORD')
)

health = memory.health_check()
print(f'Status: {health[\"status\"]}')
print(f'Connected: {health[\"connected\"]}')
print(f'Writable: {health[\"writable\"]}')
print(f'Response Time: {health[\"response_time_ms\"]}ms')
"

# Docker health check
docker run --rm --env-file .env kublai-system:latest curl -f http://localhost:18789/health || echo "Health check failed"
```

---

## 5. Monitoring and Observability Setup

### 5.1 Logging Configuration

**Log Levels:** debug, info, warn, error
**Default:** info
**Structured Logging:** structlog

**Verification Commands:**
```bash
# Check log configuration
python -c "
import structlog
import logging

logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger()

logger.info('Test info message')
logger.warning('Test warning message')
logger.error('Test error message')
"

# View logs (Docker)
docker logs <container_id> --tail 100 -f

# View logs (Railway)
railway logs  # Requires Railway CLI
```

### 5.2 Metrics Collection

**Prometheus Port:** 9090 (configurable via `PROMETHEUS_PORT`)

**Key Metrics to Monitor:**
- Connection pool usage
- Query execution time
- Error rate
- Task throughput
- Agent heartbeat latency

**Verification Commands:**
```bash
# Check Prometheus metrics endpoint
curl http://localhost:9090/metrics

# Check specific metrics
curl -s http://localhost:9090/metrics | grep neo4j

# Performance issue detection
python -c "
from openclaw_memory import OperationalMemory
import os
from dotenv import load_dotenv
load_dotenv()

memory = OperationalMemory(
    uri=os.getenv('NEO4J_URI'),
    username=os.getenv('NEO4J_USER'),
    password=os.getenv('NEO4J_PASSWORD')
)

# Simulate metrics
metrics = {
    'connection_pool_usage': 85,
    'query_time_ms': 1200,
    'error_rate': 2,
    'memory_usage_mb': 512,
    'retry_count': 10
}

issues = memory.detect_performance_issues(metrics)
for issue in issues:
    print(f'{issue[\"severity\"].upper()}: {issue[\"issue_type\"]} - {issue[\"description\"]}')
"
```

### 5.3 Alerting Thresholds

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Connection Pool Usage | 80% | 95% | Scale or optimize |
| Query Time | 1000ms | 5000ms | Add indexes |
| Error Rate | 5% | 10% | Investigate |
| Memory Usage | 1GB | 2GB | Check for leaks |
| Circuit Breaker Trips | 2 | 5 | Check Neo4j health |

### 5.4 Distributed Tracing

**Trace Context:** Passed via `traceparent` header
**Correlation ID:** Included in all logs

**Verification Commands:**
```bash
# Check trace context propagation
curl -H "traceparent: 00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01" \
     http://localhost:18789/health

# Verify correlation IDs in logs
grep "trace_id" /var/log/kublai/*.log | head -10
```

---

## 6. Backup and Disaster Recovery

### 6.1 Backup Strategy

**Backup Types:**
- Daily: 7-day retention
- Weekly: 28-day retention (Sundays)
- Monthly: 365-day retention (1st of month)

**Backup Location:** `/var/lib/neo4j/backups`

**Verification Commands:**
```bash
# Create manual backup
neo4j-admin database dump neo4j --to-path=/var/lib/neo4j/backups/manual-$(date +%Y%m%d_%H%M%S).dump

# List existing backups
ls -lah /var/lib/neo4j/backups/

# Verify backup integrity
gunzip -t /var/lib/neo4j/backups/neo4j-daily-*.dump.gz
sha256sum -c /var/lib/neo4j/backups/*.sha256

# Check backup script exists and is executable
ls -la /opt/neo4j/scripts/neo4j-backup.sh
/opt/neo4j/scripts/neo4j-backup.sh --dry-run 2>/dev/null || echo "Script not configured"
```

### 6.2 Automated Backup Schedule

**Cron Configuration:**
```cron
# Daily backup at 2 AM
0 2 * * * /opt/neo4j/scripts/neo4j-backup.sh full

# Hourly incremental (if configured)
0 * * * * /opt/neo4j/scripts/neo4j-backup.sh incremental
```

**Verification Commands:**
```bash
# Check cron jobs
crontab -l | grep neo4j

# Check systemd timer (if using systemd)
systemctl list-timers | grep neo4j
systemctl status neo4j-backup.timer 2>/dev/null || echo "Timer not configured"
```

### 6.3 Cloud Backup Replication

**Supported Providers:**
- AWS S3
- Google Cloud Storage
- Azure Blob Storage

**Environment Variables:**
```bash
S3_BUCKET=kublai-neo4j-backups
GCS_BUCKET=kublai-neo4j-backups
AZURE_CONTAINER=neo4j-backups
```

**Verification Commands:**
```bash
# Test S3 upload
aws s3 ls s3://$S3_BUCKET/neo4j-backups/ 2>/dev/null || echo "S3 not configured"

# Test GCS upload
gsutil ls gs://$GCS_BUCKET/neo4j-backups/ 2>/dev/null || echo "GCS not configured"

# Verify backup metadata
cat /var/lib/neo4j/backups/neo4j-daily-*.meta 2>/dev/null | jq
```

### 6.4 Disaster Recovery Procedures

**Recovery Time Objective (RTO):** 30 minutes
**Recovery Point Objective (RPO):** 1 hour

**Verification Commands:**
```bash
# Test restore procedure (to temp database)
/opt/neo4j/scripts/neo4j-restore.sh /var/lib/neo4j/backups/neo4j-daily-*.dump.gz neo4j_temp

# Verify restored database
cypher-shell -d neo4j_temp -u neo4j -p $NEO4J_PASSWORD "MATCH (n) RETURN count(n) as node_count"

# Point-in-time recovery (if transaction logs available)
/opt/neo4j/scripts/point-in-time-recovery.sh 2026-02-04T10:00:00

# Documented runbooks
ls -la /Users/kurultai/molt/monitoring/runbooks/
```

### 6.5 Runbook Verification

**Available Runbooks:**
- `AGT-001_agent_unresponsive.md`
- `MIG-001_migration_failure.md`
- `NEO4J-001_connection_failure.md`

**Verification Commands:**
```bash
# List all runbooks
find /Users/kurultai/molt/monitoring/runbooks -name "*.md" -type f

# Verify runbook accessibility
cat /Users/kurultai/molt/monitoring/runbooks/NEO4J-001_connection_failure.md | head -50
```

---

## 7. Scaling Considerations

### 7.1 Horizontal Scaling

**Moltbot Service:**
- Stateless design supports horizontal scaling
- Session affinity not required
- Load balancer distributes requests

**Railway Configuration:**
```yaml
deploy:
  replicas:
    moltbot: 3  # Scale to 3 instances
    neo4j: 1    # Keep Neo4j single instance
```

### 7.2 Vertical Scaling

**Neo4j Memory Tuning:**
```properties
# For 4GB RAM allocation
NEO4J_dbms_memory_heap_initial__size=1G
NEO4J_dbms_memory_heap_max__size=2G
NEO4J_dbms_memory_pagecache_size=1G
```

**Verification Commands:**
```bash
# Monitor memory usage
cypher-shell -u neo4j -p $NEO4J_PASSWORD "CALL dbms.memory.listPools()"

# Check heap usage
jstat -gc <neo4j_pid> 1000 10 2>/dev/null || echo "jstat not available"

# Monitor connection pool
python -c "
from openclaw_memory import OperationalMemory
import os
from dotenv import load_dotenv
load_dotenv()

memory = OperationalMemory(
    uri=os.getenv('NEO4J_URI'),
    username=os.getenv('NEO4J_USER'),
    password=os.getenv('NEO4J_PASSWORD')
)

# Check pool statistics (if available via driver)
print('Connection pool monitoring requires driver-specific implementation')
"
```

### 7.3 Read Replicas

**For Read-Heavy Workloads:**
- Deploy Neo4j read replicas
- Route read queries to replicas
- Write operations go to primary

**Verification Commands:**
```bash
# Check read replica status (if clustered)
cypher-shell -u neo4j -p $NEO4J_PASSWORD "CALL dbms.cluster.readReplicaStatus()"

# Verify routing
cypher-shell -u neo4j -p $NEO4J_PASSWORD "CALL dbms.routing.getRoutingTable({}, 'neo4j')"
```

### 7.4 Rate Limiting

**Default Limits:**
- 1000 requests per hour per agent
- Configurable per operation type

**Verification Commands:**
```bash
# Check current rate limit status
python -c "
from openclaw_memory import OperationalMemory
import os
from dotenv import load_dotenv
load_dotenv()

memory = OperationalMemory(
    uri=os.getenv('NEO4J_URI'),
    username=os.getenv('NEO4J_USER'),
    password=os.getenv('NEO4J_PASSWORD')
)

allowed, count, reset = memory.check_rate_limit('main', 'task_create', max_requests=1000)
print(f'Rate Limit Status:')
print(f'  Allowed: {allowed}')
print(f'  Current Count: {count}')
print(f'  Reset Time: {reset}')
"
```

### 7.5 Circuit Breaker Pattern

**Configuration:**
- Failure threshold: 5 errors
- Recovery timeout: 30 seconds
- Half-open requests: 1 test request

**Verification Commands:**
```bash
# Test circuit breaker behavior
python -c "
from openclaw_memory import OperationalMemory, CircuitBreaker
import os
from dotenv import load_dotenv
load_dotenv()

# Simulate circuit breaker
cb = CircuitBreaker(failure_threshold=5, recovery_timeout=30)
print(f'Circuit state: {cb.state}')
print(f'Failure count: {cb.failure_count}')
"
```

---

## 8. Pre-Deployment Verification Commands

### 8.1 Complete Pre-Deployment Checklist Script

```bash
#!/bin/bash
# Kublai System Pre-Deployment Verification Script
# Run this script before deploying to production

set -e

echo "=========================================="
echo "Kublai System Pre-Deployment Verification"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0
WARN=0

check_pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((PASS++))
}

check_fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    ((FAIL++))
}

check_warn() {
    echo -e "${YELLOW}⚠ WARN${NC}: $1"
    ((WARN++))
}

echo "1. Python Environment"
echo "---------------------"

# Check Python version
PYTHON_VERSION=$(python --version 2>&1 | cut -d' ' -f2)
if python -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
    check_pass "Python version: $PYTHON_VERSION (>= 3.11)"
else
    check_fail "Python version: $PYTHON_VERSION (requires >= 3.11)"
fi

# Check pip
if pip --version > /dev/null 2>&1; then
    check_pass "pip is installed"
else
    check_fail "pip is not installed"
fi

echo ""
echo "2. Dependencies"
echo "---------------"

# Check requirements.txt exists
if [ -f "requirements.txt" ]; then
    check_pass "requirements.txt exists"
else
    check_fail "requirements.txt not found"
fi

# Check key packages
for pkg in neo4j pydantic httpx structlog; do
    if pip show $pkg > /dev/null 2>&1; then
        VERSION=$(pip show $pkg | grep Version | cut -d' ' -f2)
        check_pass "$pkg installed (v$VERSION)"
    else
        check_fail "$pkg not installed"
    fi
done

echo ""
echo "3. Environment Variables"
echo "------------------------"

# Check .env file
if [ -f ".env" ]; then
    check_pass ".env file exists"
else
    check_warn ".env file not found (using system env)"
fi

# Check required variables
for var in NEO4J_URI NEO4J_USER NEO4J_PASSWORD OPENCLAW_GATEWAY_TOKEN AGENT_AUTH_SECRET; do
    if [ -n "${!var}" ]; then
        check_pass "$var is set"
    else
        check_fail "$var is not set"
    fi
done

# Check password strength
if [ -n "$NEO4J_PASSWORD" ]; then
    PWD_LEN=${#NEO4J_PASSWORD}
    if [ $PWD_LEN -ge 16 ]; then
        check_pass "NEO4J_PASSWORD is $PWD_LEN characters (strong)"
    else
        check_warn "NEO4J_PASSWORD is only $PWD_LEN characters (recommended: 16+)"
    fi
fi

echo ""
echo "4. Neo4j Connection"
echo "-------------------"

# Test Neo4j connectivity
if python -c "
import os
from neo4j import GraphDatabase
try:
    driver = GraphDatabase.driver(os.getenv('NEO4J_URI', 'bolt://localhost:7687'), auth=(os.getenv('NEO4J_USER', 'neo4j'), os.getenv('NEO4J_PASSWORD', '')))
    driver.verify_connectivity()
    driver.close()
    exit(0)
except Exception as e:
    print(f'Error: {e}')
    exit(1)
" 2>/dev/null; then
    check_pass "Neo4j connection successful"
else
    check_fail "Cannot connect to Neo4j"
fi

echo ""
echo "5. Application Health"
echo "---------------------"

# Check health_server.py exists
if [ -f "health_server.py" ]; then
    check_pass "health_server.py exists"
else
    check_fail "health_server.py not found"
fi

# Check openclaw_memory.py exists
if [ -f "openclaw_memory.py" ]; then
    check_pass "openclaw_memory.py exists"
else
    check_fail "openclaw_memory.py not found"
fi

echo ""
echo "6. Docker Configuration"
echo "-----------------------"

# Check Dockerfile exists
if [ -f "Dockerfile" ]; then
    check_pass "Dockerfile exists"
else
    check_fail "Dockerfile not found"
fi

# Check Docker is available
if docker --version > /dev/null 2>&1; then
    check_pass "Docker is installed"
else
    check_warn "Docker not installed (optional for non-Docker deployments)"
fi

echo ""
echo "7. Railway Configuration"
echo "------------------------"

# Check railway.yml exists
if [ -f "railway.yml" ]; then
    check_pass "railway.yml exists"
else
    check_fail "railway.yml not found"
fi

# Check for required services in railway.yml
if grep -q "moltbot:" railway.yml && grep -q "neo4j:" railway.yml; then
    check_pass "railway.yml has moltbot and neo4j services"
else
    check_fail "railway.yml missing required services"
fi

echo ""
echo "8. Monitoring and Runbooks"
echo "--------------------------"

# Check monitoring directory
if [ -d "monitoring/runbooks" ]; then
    check_pass "monitoring/runbooks directory exists"
    RUNBOOK_COUNT=$(find monitoring/runbooks -name "*.md" | wc -l)
    check_pass "$RUNBOOK_COUNT runbooks found"
else
    check_warn "monitoring/runbooks directory not found"
fi

echo ""
echo "=========================================="
echo "Verification Summary"
echo "=========================================="
echo -e "${GREEN}Passed: $PASS${NC}"
echo -e "${YELLOW}Warnings: $WARN${NC}"
echo -e "${RED}Failed: $FAIL${NC}"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}✓ Ready for deployment!${NC}"
    exit 0
else
    echo -e "${RED}✗ Please fix failed checks before deploying.${NC}"
    exit 1
fi
```

### 8.2 Quick Verification Commands

```bash
# One-liner to check everything
echo "=== Kublai Pre-Deployment Check ===" && \
python --version && \
pip show neo4j pydantic httpx > /dev/null && echo "✓ Core deps installed" || echo "✗ Missing deps" && \
test -f .env && echo "✓ .env exists" || echo "✗ .env missing" && \
test -f railway.yml && echo "✓ railway.yml exists" || echo "✗ railway.yml missing" && \
test -f Dockerfile && echo "✓ Dockerfile exists" || echo "✗ Dockerfile missing" && \
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print('✓ Env vars loaded') if all(os.getenv(v) for v in ['NEO4J_URI','NEO4J_PASSWORD','OPENCLAW_GATEWAY_TOKEN']) else print('✗ Missing env vars')" 2>/dev/null && \
echo "=== Check Complete ==="
```

### 8.3 Post-Deployment Verification

```bash
# After deployment, verify services are healthy

# 1. Check moltbot health
curl -sf https://kublai.kurult.ai/health | jq

# 2. Check Neo4j Browser
curl -sf -u neo4j:$NEO4J_PASSWORD https://kublai.kurult.ai:7474/browser/

# 3. Check Authentik health
curl -sf http://authentik-server.railway.internal:9000/-/health/ready/

# 4. Check proxy health
curl -sf http://authentik-proxy.railway.internal:8080/health

# 5. Test Authentik authentication flow
curl -sf https://kublai.kurult.ai/if/flow/kublai-webauthn-auth/ | grep -q "Sign in" && echo "✓ Auth flow accessible" || echo "✗ Auth flow error"

# 3. Test Neo4j connection
python -c "
from openclaw_memory import OperationalMemory
import os
from dotenv import load_dotenv
load_dotenv()

memory = OperationalMemory(
    uri=os.getenv('NEO4J_URI'),
    username=os.getenv('NEO4J_USER'),
    password=os.getenv('NEO4J_PASSWORD')
)

health = memory.health_check()
assert health['status'] == 'healthy', f'Unhealthy: {health}'
print('✓ Neo4j operational memory healthy')
"

# 4. Create and claim a test task
python -c "
from openclaw_memory import OperationalMemory
import os
from dotenv import load_dotenv
load_dotenv()

memory = OperationalMemory(
    uri=os.getenv('NEO4J_URI'),
    username=os.getenv('NEO4J_USER'),
    password=os.getenv('NEO4J_PASSWORD')
)

# Create test task
task_id = memory.create_task(
    task_type='health_check',
    description='Post-deployment health check',
    delegated_by='main',
    assigned_to='test_agent'
)
print(f'✓ Created test task: {task_id}')

# Claim task
task = memory.claim_task('test_agent')
assert task is not None, 'Failed to claim task'
print(f'✓ Claimed task: {task[\"id\"]}')

# Complete task
memory.complete_task(task['id'], 'test_agent', {'status': 'success'})
print('✓ Completed test task')
"
```

---

## Appendix A: File Locations

| File | Path | Purpose |
|------|------|---------|
| Requirements | `/Users/kurultai/molt/requirements.txt` | Production dependencies |
| Test Requirements | `/Users/kurultai/molt/test-requirements.txt` | Testing dependencies |
| Dockerfile | `/Users/kurultai/molt/Dockerfile` | Container definition |
| Railway Config | `/Users/kurultai/molt/railway.yml` | Railway deployment |
| Environment Example | `/Users/kurultai/molt/.env.example` | Environment template |
| Health Server | `/Users/kurultai/molt/health_server.py` | Health check endpoint |
| Memory Module | `/Users/kurultai/molt/openclaw_memory.py` | Neo4j operations |
| Pytest Config | `/Users/kurultai/molt/pytest.ini` | Test configuration |
| CI/CD Workflow | `/Users/kurultai/molt/.github/workflows/tests.yml` | GitHub Actions |

## Appendix B: Reference Documentation

| Document | Path | Content |
|----------|------|---------|
| Neo4j Implementation | `/Users/kurultai/molt/docs/plans/neo4j.md` | Full Neo4j schema and implementation |
| Authentik Setup | `/Users/kurultai/molt/docs/deployment/authentik-setup.md` | Biometric auth deployment guide |
| Deployment Plan | `/Users/kurultai/molt/kurultaideploy.md` | Railway deployment steps |
| Runbooks | `/Users/kurultai/molt/monitoring/runbooks/` | Error recovery procedures |

### Authentik Files Reference

| File | Path | Purpose |
|------|------|---------|
| Railway Config | `/Users/kurultai/molt/railway.yml` | Service definitions (authentik-db, server, worker, proxy) |
| Caddyfile | `/Users/kurultai/molt/authentik-proxy/Caddyfile` | Reverse proxy with forward auth |
| Bootstrap Script | `/Users/kurultai/molt/authentik-proxy/bootstrap_authentik.py` | API-based configuration |
| Server Dockerfile | `/Users/kurultai/molt/authentik-server/Dockerfile` | Authentik 2025.10 server |
| Worker Dockerfile | `/Users/kurultai/molt/authentik-worker/Dockerfile` | Authentik worker |
| Proxy Dockerfile | `/Users/kurultai/molt/authentik-proxy/Dockerfile` | Caddy 2 alpine |
| Blueprints | `/Users/kurultai/molt/authentik-proxy/config/*.yaml` | WebAuthn flow, provider, application |
| Deploy Script | `/Users/kurultai/molt/scripts/deploy-authentik.sh` | Deployment automation |
| Backup Script | `/Users/kurultai/molt/scripts/backup-authentik-db.sh` | Database backup to R2/S3 |
| Environment | `/Users/kurultai/molt/.env.example` | Environment variable template |

---

**End of Checklist**

*Last Updated: 2026-02-05* (Added Authentik biometric authentication section)
