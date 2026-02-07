# Quality Gate Verification System

Comprehensive documentation for the Kurultai Testing Suite quality gate verification system.

## Table of Contents

1. [Overview](#overview)
2. [Gate Reference](#gate-reference)
3. [Running Verification Locally](#running-verification-locally)
4. [CI/CD Integration](#cicd-integration)
5. [Troubleshooting Guide](#troubleshooting-guide)
6. [Gate Override Process](#gate-override-process)

---

## Overview

### What Are Quality Gates

Quality gates are automated checkpoints that validate code quality, test coverage, and system readiness before deployment. The Kurultai Testing Suite implements a comprehensive **37-gate** verification system that ensures production readiness.

Each gate validates a specific aspect of the system:

- **Environment Gates (ENV-001 to ENV-012)**: Validate configuration and infrastructure
- **Neo4j Gates (NEO-001 to NEO-010)**: Validate database connectivity and performance
- **Authentication Gates (AUTH-001 to AUTH-007)**: Validate security mechanisms
- **Agent Gates (AGENT-001 to AGENT-008)**: Validate multi-agent system configuration

### Why Quality Gates Matter

Quality gates provide:

1. **Deployment Safety**: Prevent broken code from reaching production
2. **Consistency**: Standardized validation across all deployments
3. **Early Detection**: Catch issues before they impact users
4. **Compliance**: Ensure security and performance standards are met
5. **Confidence**: Provide Go/No-Go decision for releases

### Current Gate Thresholds

| Metric | Threshold | Critical |
|--------|-----------|----------|
| Overall Pass Rate | >= 90% | Yes |
| Critical Gate Pass Rate | 100% | Yes |
| Code Coverage | >= 80% | No |
| Test Success Rate | 100% | Yes |
| Linting Errors | 0 | Yes |
| Type Check Errors | 0 | No |

### Critical Gates

The following gates are marked as **CRITICAL** and must pass for deployment:

- **ENV-001**: Gateway token >= 32 chars
- **ENV-002**: Neo4j password >= 16 chars
- **ENV-003**: HMAC secret >= 64 chars
- **NEO-001**: Neo4j reachable on port 7687
- **NEO-002**: Bolt connection works
- **NEO-003**: Write capability
- **AUTH-001**: HMAC generation works (64-char hex)
- **AUTH-002**: HMAC verification works
- **AUTH-003**: Invalid HMAC rejected
- **AGENT-001**: All 6 agents configured
- **AGENT-002**: Agent directories exist

---

## Gate Reference

### Environment Gates (ENV-001 to ENV-012)

#### GATE-1: ENV-001 - Gateway Token Validation

| Attribute | Value |
|-----------|-------|
| **Description** | Validates that OPENCLAW_GATEWAY_TOKEN is set and meets minimum length requirement |
| **Threshold** | Token length >= 32 characters |
| **Critical** | Yes |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category environment
```

**How to Fix Failures:**
```bash
# Generate a secure token
openssl rand -hex 32

# Add to .env file
echo "OPENCLAW_GATEWAY_TOKEN=your_generated_token" >> .env
```

**Example Output - PASS:**
```
[ENV-001] Gateway token set [CRITICAL]
  Status:   PASS
  Expected: Count >= 32
  Actual:   64 chars
  Output:   PASS (64 chars)
```

**Example Output - FAIL:**
```
[ENV-001] Gateway token set [CRITICAL]
  Status:   FAIL
  Expected: Count >= 32
  Actual:   8 chars
  Output:   FAIL: Token is only 8 chars (minimum 32)
```

---

#### GATE-2: ENV-002 - Neo4j Password Validation

| Attribute | Value |
|-----------|-------|
| **Description** | Validates that NEO4J_PASSWORD is set and meets minimum length |
| **Threshold** | Password length >= 16 characters |
| **Critical** | Yes |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category environment
```

**How to Fix Failures:**
```bash
# Generate a secure password
openssl rand -base64 24

# Add to .env file
echo "NEO4J_PASSWORD=your_generated_password" >> .env
```

---

#### GATE-3: ENV-003 - HMAC Secret Validation

| Attribute | Value |
|-----------|-------|
| **Description** | Validates that AGENTS_HMAC_SECRET is set for agent-to-agent authentication |
| **Threshold** | Secret length >= 64 characters |
| **Critical** | Yes |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category environment
```

**How to Fix Failures:**
```bash
# Generate a secure HMAC secret
openssl rand -hex 64

# Add to .env file
echo "AGENTS_HMAC_SECRET=your_generated_secret" >> .env
```

---

#### GATE-4: ENV-004 - Signal Account Configuration

| Attribute | Value |
|-----------|-------|
| **Description** | Validates Signal account is configured with valid E.164 format |
| **Threshold** | Valid E.164 phone number (+ followed by 10-15 digits) |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category environment
```

**How to Fix Failures:**
```bash
# Add to .env file (replace with your actual number)
echo "SIGNAL_ACCOUNT_NUMBER=+1234567890" >> .env
```

---

#### GATE-5: ENV-005 - Admin Phones Configuration

| Attribute | Value |
|-----------|-------|
| **Description** | Validates at least one admin phone is configured |
| **Threshold** | >= 1 admin phone configured |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category environment
```

**How to Fix Failures:**
```bash
# Add admin phones to .env
echo "ADMIN_PHONE_1=+1234567890" >> .env
echo "ADMIN_PHONE_2=+0987654321" >> .env
```

---

#### GATE-6: ENV-006 - Cloud Storage Credentials

| Attribute | Value |
|-----------|-------|
| **Description** | Validates cloud storage credentials for backups (S3, GCS, or Azure) |
| **Threshold** | At least one storage backend configured |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category environment
```

**How to Fix Failures:**
```bash
# For AWS S3
echo "AWS_ACCESS_KEY_ID=your_key" >> .env
echo "AWS_SECRET_ACCESS_KEY=your_secret" >> .env
echo "AWS_DEFAULT_REGION=us-east-1" >> .env

# OR for Google Cloud Storage
echo "GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json" >> .env
```

---

#### GATE-7: ENV-007 - Backup Encryption Key

| Attribute | Value |
|-----------|-------|
| **Description** | Validates backup encryption key is configured |
| **Threshold** | Key length >= 16 characters |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category environment
```

**How to Fix Failures:**
```bash
# Generate encryption key
openssl rand -base64 32

# Add to .env file
echo "BACKUP_ENCRYPTION_KEY=your_generated_key" >> .env
```

---

#### GATE-8: ENV-008 - Workspace Directory

| Attribute | Value |
|-----------|-------|
| **Description** | Validates workspace directory exists |
| **Threshold** | Directory exists at configured path |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category environment
```

**How to Fix Failures:**
```bash
# Create workspace directory
sudo mkdir -p /data/workspace
sudo chown $(whoami):$(whoami) /data/workspace
```

---

#### GATE-9: ENV-009 - Souls Directory

| Attribute | Value |
|-----------|-------|
| **Description** | Validates souls directory exists |
| **Threshold** | Directory exists at /data/souls |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category environment
```

**How to Fix Failures:**
```bash
# Create souls directory
sudo mkdir -p /data/souls
sudo chown $(whoami):$(whoami) /data/souls
```

---

#### GATE-10: ENV-010 - Agent Directories

| Attribute | Value |
|-----------|-------|
| **Description** | Validates at least 6 agent directories exist |
| **Threshold** | >= 6 agent directories |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category environment
```

**How to Fix Failures:**
```bash
# Create agent directories
for agent in main researcher writer developer analyst ops; do
    mkdir -p /data/.clawdbot/agents/$agent
done
```

---

#### GATE-11: ENV-011 - Configuration File Validation

| Attribute | Value |
|-----------|-------|
| **Description** | Validates moltbot.json is valid JSON with required structure |
| **Threshold** | Valid JSON with gateway, agents, channels, session keys |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category environment
# Or manually:
python -c "import json; json.load(open('moltbot.json'))"
```

**How to Fix Failures:**
```bash
# Validate JSON syntax
python -m json.tool moltbot.json

# Check required keys exist
python -c "
import json
config = json.load(open('moltbot.json'))
required = ['gateway', 'agents', 'channels', 'session']
missing = [k for k in required if k not in config]
if missing:
    print(f'Missing keys: {missing}')
else:
    print('All required keys present')
"
```

---

#### GATE-12: ENV-012 - Docker Socket Access

| Attribute | Value |
|-----------|-------|
| **Description** | Validates Docker socket is accessible for container operations |
| **Threshold** | Socket exists and is readable, OR Docker CLI available |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category environment
```

**How to Fix Failures:**
```bash
# Check Docker is installed
docker --version

# Check socket permissions
ls -la /var/run/docker.sock

# Add user to docker group (requires logout/login)
sudo usermod -aG docker $USER
```

---

### Neo4j Gates (NEO-001 to NEO-010)

#### GATE-1: NEO-001 - Neo4j Reachability

| Attribute | Value |
|-----------|-------|
| **Description** | Validates Neo4j is reachable on configured port |
| **Threshold** | Port 7687 (or configured port) is open and accepting connections |
| **Critical** | Yes |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category neo4j
# Or manually:
nc -zv localhost 7687
```

**How to Fix Failures:**
```bash
# Start Neo4j with Docker
docker run -d \
  --name neo4j \
  -p 7687:7687 -p 7474:7474 \
  -e NEO4J_AUTH=neo4j/test_password \
  neo4j:5.13.0

# Wait for Neo4j to be ready
sleep 10

# Verify connection
python -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'test_password'))
driver.verify_connectivity()
print('Connection successful')
driver.close()
"
```

---

#### GATE-2: NEO-002 - Bolt Connection

| Attribute | Value |
|-----------|-------|
| **Description** | Validates Bolt protocol connection works |
| **Threshold** | Successful Bolt connection and query execution |
| **Critical** | Yes |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category neo4j
```

**How to Fix Failures:**
- Verify Neo4j is running (see NEO-001)
- Check credentials in .env file
- Verify network connectivity
- Check Neo4j logs: `docker logs neo4j`

---

#### GATE-3: NEO-003 - Write Capability

| Attribute | Value |
|-----------|-------|
| **Description** | Validates write operations work on the database |
| **Threshold** | Can create and delete test nodes |
| **Critical** | Yes |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category neo4j
```

**How to Fix Failures:**
- Verify Neo4j is not in read-only mode
- Check disk space: `df -h`
- Check user permissions in Neo4j

---

#### GATE-4: NEO-004 - Connection Pool Health

| Attribute | Value |
|-----------|-------|
| **Description** | Validates connection pool is healthy |
| **Threshold** | Can execute multiple concurrent queries |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category neo4j
```

**How to Fix Failures:**
- Restart Neo4j to clear connection pool issues
- Check for connection leaks in application code
- Verify max_connections setting in Neo4j

---

#### GATE-5: NEO-005 - Index Validation

| Attribute | Value |
|-----------|-------|
| **Description** | Validates required indexes exist for performance |
| **Threshold** | >= 10 indexes configured |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category neo4j
# Or manually:
python -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'password'))
with driver.session() as session:
    result = session.run('SHOW INDEXES')
    indexes = [r.data() for r in result]
    print(f'Found {len(indexes)} indexes')
driver.close()
"
```

**How to Fix Failures:**
```bash
# Create required indexes
python -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'password'))
with driver.session() as session:
    # Create indexes for common queries
    session.run('CREATE INDEX Task_id IF NOT EXISTS FOR (t:Task) ON (t.id)')
    session.run('CREATE INDEX Task_status IF NOT EXISTS FOR (t:Task) ON (t.status)')
    session.run('CREATE INDEX Agent_name IF NOT EXISTS FOR (a:Agent) ON (a.name)')
driver.close()
"
```

---

#### GATE-6: NEO-006 - Constraint Validation

| Attribute | Value |
|-----------|-------|
| **Description** | Validates required constraints exist for data integrity |
| **Threshold** | >= 5 constraints configured |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category neo4j
```

**How to Fix Failures:**
```bash
# Create required constraints
python -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'password'))
with driver.session() as session:
    session.run('CREATE CONSTRAINT Task_id_unique IF NOT EXISTS FOR (t:Task) REQUIRE t.id IS UNIQUE')
    session.run('CREATE CONSTRAINT Agent_name_unique IF NOT EXISTS FOR (a:Agent) REQUIRE a.name IS UNIQUE')
driver.close()
"
```

---

#### GATE-7: NEO-007 - Migration Version

| Attribute | Value |
|-----------|-------|
| **Description** | Validates database schema migration version is current |
| **Threshold** | Migration version node exists |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category neo4j
```

**How to Fix Failures:**
```bash
# Run migrations
python -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'password'))
with driver.session() as session:
    session.run('CREATE (m:MigrationVersion {version: \"1.0.0\", applied_at: datetime()})')
driver.close()
"
```

---

#### GATE-8: NEO-008 - Fallback Mode

| Attribute | Value |
|-----------|-------|
| **Description** | Validates fallback mode works when Neo4j is unavailable |
| **Threshold** | Operations succeed in fallback mode |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category neo4j
```

**How to Fix Failures:**
- Ensure OperationalMemory is properly configured with `fallback_mode=True`
- Check fallback storage directory permissions
- Verify fallback mode logic in code

---

#### GATE-9: NEO-009 - Read Replica (Optional)

| Attribute | Value |
|-----------|-------|
| **Description** | Checks if read replica is configured for HA setups |
| **Threshold** | Read replica URI configured (optional) |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category neo4j
```

**How to Fix (if needed):**
```bash
# Add to .env for HA setups
echo "NEO4J_READ_REPLICA_ENABLED=true" >> .env
echo "NEO4J_READ_REPLICA_URI=bolt://replica:7687" >> .env
```

---

#### GATE-10: NEO-010 - Query Performance

| Attribute | Value |
|-----------|-------|
| **Description** | Validates query performance baseline |
| **Threshold** | Simple queries complete in < 100ms |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category neo4j
```

**How to Fix Failures:**
- Create missing indexes (see NEO-005)
- Optimize slow queries
- Check Neo4j memory configuration
- Monitor system resources

---

### Authentication Gates (AUTH-001 to AUTH-007)

#### GATE-1: AUTH-001 - HMAC Generation

| Attribute | Value |
|-----------|-------|
| **Description** | Validates HMAC signature generation produces correct format |
| **Threshold** | 64-character hex string |
| **Critical** | Yes |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category auth
```

**How to Fix Failures:**
- Ensure HMAC secret is properly configured (ENV-003)
- Check HMAC implementation in code
- Verify SHA-256 digest is being used

---

#### GATE-2: AUTH-002 - HMAC Verification

| Attribute | Value |
|-----------|-------|
| **Description** | Validates valid HMAC signatures are correctly verified |
| **Threshold** | Valid signatures accepted |
| **Critical** | Yes |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category auth
```

**How to Fix Failures:**
- Check HMAC secret consistency
- Verify `hmac.compare_digest()` is used for comparison
- Ensure message encoding is consistent

---

#### GATE-3: AUTH-003 - HMAC Rejection

| Attribute | Value |
|-----------|-------|
| **Description** | Validates invalid HMAC signatures are correctly rejected |
| **Threshold** | Invalid signatures rejected |
| **Critical** | Yes |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category auth
```

**How to Fix Failures:**
- This is a security-critical check
- Ensure proper HMAC comparison using `hmac.compare_digest()`
- Check for timing attack vulnerabilities

---

#### GATE-4: AUTH-004 - Gateway Token Validation

| Attribute | Value |
|-----------|-------|
| **Description** | Validates gateway token meets minimum requirements |
| **Threshold** | Token >= 32 characters |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category auth
```

**How to Fix Failures:**
See ENV-001 fix instructions.

---

#### GATE-5: AUTH-005 - Token Rejection

| Attribute | Value |
|-----------|-------|
| **Description** | Validates invalid tokens are rejected |
| **Threshold** | Invalid tokens rejected with 401 |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category auth
```

**How to Fix Failures:**
- Review token validation logic
- Ensure proper error handling for invalid tokens
- Check authentication middleware

---

#### GATE-6: AUTH-006 - Agent-to-Agent Authentication

| Attribute | Value |
|-----------|-------|
| **Description** | Validates agent-to-agent authentication works |
| **Threshold** | Signed messages verified correctly |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category auth
```

**How to Fix Failures:**
- Ensure AGENTS_HMAC_SECRET is set (ENV-003)
- Check agent communication configuration
- Verify message signing logic

---

#### GATE-7: AUTH-007 - Message Signature

| Attribute | Value |
|-----------|-------|
| **Description** | Validates message signatures include all required fields |
| **Threshold** | All required fields present with valid signature |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category auth
```

**How to Fix Failures:**
- Ensure messages include: from, to, message, signature, timestamp
- Verify signature generation includes timestamp for replay protection
- Check signature length is 64 characters

---

### Agent Gates (AGENT-001 to AGENT-008)

#### GATE-1: AGENT-001 - Agent Count

| Attribute | Value |
|-----------|-------|
| **Description** | Validates at least 6 agents are configured |
| **Threshold** | >= 6 agents in moltbot.json |
| **Critical** | Yes |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category agents
```

**How to Fix Failures:**
```bash
# Edit moltbot.json to add agents
python -c "
import json

with open('moltbot.json', 'r') as f:
    config = json.load(f)

# Ensure at least 6 agents
required_agents = ['main', 'researcher', 'writer', 'developer', 'analyst', 'ops']
existing_ids = [a.get('id') for a in config.get('agents', {}).get('list', [])]

for agent_id in required_agents:
    if agent_id not in existing_ids:
        config['agents']['list'].append({
            'id': agent_id,
            'name': agent_id.capitalize(),
            'model': 'claude-3-5-sonnet-20241022'
        })

with open('moltbot.json', 'w') as f:
    json.dump(config, f, indent=2)

print(f'Now have {len(config[\"agents\"][\"list\"])} agents')
"
```

---

#### GATE-2: AGENT-002 - Agent Directories

| Attribute | Value |
|-----------|-------|
| **Description** | Validates agent directories exist in filesystem |
| **Threshold** | All configured agents have existing directories |
| **Critical** | Yes |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category agents
```

**How to Fix Failures:**
```bash
# Create missing agent directories
python -c "
import json
import os

with open('moltbot.json', 'r') as f:
    config = json.load(f)

for agent in config.get('agents', {}).get('list', []):
    agent_dir = agent.get('agentDir')
    if agent_dir and not os.path.exists(agent_dir):
        os.makedirs(agent_dir, exist_ok=True)
        print(f'Created: {agent_dir}')
"
```

---

#### GATE-3: AGENT-003 - Agent Models

| Attribute | Value |
|-----------|-------|
| **Description** | Validates each agent has a model configured |
| **Threshold** | All agents have models (explicit or default) |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category agents
```

**How to Fix Failures:**
```bash
# Set default model in moltbot.json
python -c "
import json

with open('moltbot.json', 'r') as f:
    config = json.load(f)

# Set default model if not present
if 'defaults' not in config.get('agents', {}):
    config['agents']['defaults'] = {}
if 'model' not in config['agents']['defaults']:
    config['agents']['defaults']['model'] = {}
if 'primary' not in config['agents']['defaults']['model']:
    config['agents']['defaults']['model']['primary'] = 'claude-3-5-sonnet-20241022'

with open('moltbot.json', 'w') as f:
    json.dump(config, f, indent=2)
"
```

---

#### GATE-4: AGENT-004 - Agent Communication

| Attribute | Value |
|-----------|-------|
| **Description** | Validates agent-to-agent communication is enabled |
| **Threshold** | Communication enabled with allow list |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category agents
```

**How to Fix Failures:**
```bash
# Enable agent-to-agent communication in moltbot.json
python -c "
import json

with open('moltbot.json', 'r') as f:
    config = json.load(f)

if 'tools' not in config:
    config['tools'] = {}
if 'agentToAgent' not in config['tools']:
    config['tools']['agentToAgent'] = {}

config['tools']['agentToAgent']['enabled'] = True
config['tools']['agentToAgent']['allow'] = ['main', 'researcher', 'writer', 'developer', 'analyst', 'ops']

with open('moltbot.json', 'w') as f:
    json.dump(config, f, indent=2)
"
```

---

#### GATE-5: AGENT-005 - Failover Configuration

| Attribute | Value |
|-----------|-------|
| **Description** | Validates failover configuration is correct |
| **Threshold** | Valid failover targets for all agents |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category agents
```

**How to Fix Failures:**
```bash
# Configure failover in moltbot.json
python -c "
import json

with open('moltbot.json', 'r') as f:
    config = json.load(f)

# Example: Configure ops as failover for main
for agent in config.get('agents', {}).get('list', []):
    if agent.get('id') == 'ops':
        agent['failoverFor'] = ['main']

with open('moltbot.json', 'w') as f:
    json.dump(config, f, indent=2)
"
```

---

#### GATE-6: AGENT-006 - Default Agent

| Attribute | Value |
|-----------|-------|
| **Description** | Validates a default agent is configured |
| **Threshold** | One agent marked as default |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category agents
```

**How to Fix Failures:**
```bash
# Set default agent in moltbot.json
python -c "
import json

with open('moltbot.json', 'r') as f:
    config = json.load(f)

# Mark 'main' as default
for agent in config.get('agents', {}).get('list', []):
    if agent.get('id') == 'main':
        agent['default'] = True
        break

with open('moltbot.json', 'w') as f:
    json.dump(config, f, indent=2)
"
```

---

#### GATE-7: AGENT-007 - Unique Agent IDs

| Attribute | Value |
|-----------|-------|
| **Description** | Validates all agent IDs are unique |
| **Threshold** | No duplicate agent IDs |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category agents
```

**How to Fix Failures:**
```bash
# Check and fix duplicate IDs
python -c "
import json

with open('moltbot.json', 'r') as f:
    config = json.load(f)

agent_ids = [a.get('id') for a in config.get('agents', {}).get('list', [])]
duplicates = set([aid for aid in agent_ids if agent_ids.count(aid) > 1])

if duplicates:
    print(f'Duplicate IDs found: {duplicates}')
    # Remove duplicates, keeping first occurrence
    seen = set()
    unique_agents = []
    for agent in config['agents']['list']:
        if agent['id'] not in seen:
            seen.add(agent['id'])
            unique_agents.append(agent)
    config['agents']['list'] = unique_agents

    with open('moltbot.json', 'w') as f:
        json.dump(config, f, indent=2)
    print('Fixed duplicates')
else:
    print('No duplicates found')
"
```

---

#### GATE-8: AGENT-008 - Workspace Paths

| Attribute | Value |
|-----------|-------|
| **Description** | Validates workspace paths are valid |
| **Threshold** | Valid workspace path (exists or absolute path) |
| **Critical** | No |
| **CI Job** | pre-flight-checks |

**Verification Command:**
```bash
python -m scripts.pre_flight_check --category agents
```

**How to Fix Failures:**
```bash
# Set valid workspace in moltbot.json
python -c "
import json
import os

with open('moltbot.json', 'r') as f:
    config = json.load(f)

workspace = config.get('agents', {}).get('defaults', {}).get('workspace', '/data/workspace')
if not os.path.exists(workspace):
    os.makedirs(workspace, exist_ok=True)
    print(f'Created workspace: {workspace}')

config['agents']['defaults']['workspace'] = workspace

with open('moltbot.json', 'w') as f:
    json.dump(config, f, indent=2)
"
```

---

## Running Verification Locally

### Quick Check Command

Run a quick validation of critical gates only:

```bash
# Run only critical checks
python -m scripts.pre_flight_check 2>&1 | grep -E "(CRITICAL|DECISION)"
```

**Example Output:**
```
[ENV-001] Gateway token set [CRITICAL]
  Status:   PASS
[ENV-002] Neo4j password set [CRITICAL]
  Status:   PASS
[ENV-003] HMAC secret set [CRITICAL]
  Status:   PASS
...
  DECISION: GO
```

### Full Verification Command

Run the complete pre-flight checklist:

```bash
# Run all checks
python -m scripts.pre_flight_check

# Run with verbose output
python -m scripts.pre_flight_check --verbose

# Run specific category
python -m scripts.pre_flight_check --category environment
python -m scripts.pre_flight_check --category neo4j
python -m scripts.pre_flight_check --category auth
python -m scripts.pre_flight_check --category agents

# Save results to JSON
python -m scripts.pre_flight_check --output preflight_results.json
```

### Running Tests with Coverage

```bash
# Run all tests with coverage
pytest

# Run without coverage (faster)
pytest --no-cov

# Run specific test categories
pytest -m unit
pytest -m integration
pytest -m security

# Run with coverage report
pytest --cov-report=html
open htmlcov/index.html
```

### Interpreting Results

**Passing Output:**
```
================================================================================
OPENCLAW PRE-FLIGHT CHECKLIST REPORT
================================================================================

  ========================================
  DECISION: GO
  ========================================

SUMMARY
----------------------------------------
  Total Checks:    37
  Passed:          35 (94.6%)
  Failed:          0
  Warnings:        2
  Skipped:         0
  Critical Passed: 11/11

DECISION REASONING
----------------------------------------
  All 11 critical checks passed and 94.6% overall pass rate meets threshold
```

**Failing Output:**
```
  ########################################
  DECISION: NO-GO
  ########################################

SUMMARY
----------------------------------------
  Total Checks:    37
  Passed:          28 (75.7%)
  Failed:          3
  Warnings:        6
  Skipped:         0
  Critical Passed: 9/11

DECISION REASONING
----------------------------------------
  2 critical check(s) failed | Pass rate 75.7% is below 90% threshold

BLOCKING ISSUES
----------------------------------------
  - [ENV-001] Gateway token set: OPENCLAW_GATEWAY_TOKEN not set
  - [NEO-001] Neo4j reachable on port 7687: Cannot connect to localhost:7687
```

---

## CI/CD Integration

### Overview

The quality gates run in GitHub Actions via the `.github/workflows/quality-gates.yml` workflow. The pipeline consists of **5 jobs** that execute sequentially based on dependencies.

### CI Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Quality Gates CI Pipeline                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐                                                        │
│  │  Pre-flight     │  All 37 gates (ENV-*, NEO-*, AUTH-*, AGENT-*)         │
│  │  Checks         │  Neo4j service container                               │
│  │  (Job 0)        │  GO/NO-GO decision gate                                │
│  └────────┬────────┘                                                        │
│           │                                                                 │
│           ▼ (on GO decision)                                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │  Quality Gates  │  │  Security Scan  │  │  Performance    │             │
│  │  (Job 1)        │  │  (Job 2)        │  │  Benchmark      │             │
│  │                 │  │                 │  │  (Job 3)        │             │
│  │ • Black format  │  │ • Bandit        │  │                 │             │
│  │ • Ruff lint     │  │ • Safety        │  │ • Benchmarks    │             │
│  │ • isort         │  │ • pip-audit     │  │ • Comparison    │             │
│  │ • mypy          │  │                 │  │ • Regression    │             │
│  │ • Tests         │  │                 │  │   detection     │             │
│  │ • Coverage      │  │                 │  │                 │             │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘             │
│           │                    │                    │                       │
│           └────────────────────┼────────────────────┘                       │
│                                ▼                                            │
│                       ┌─────────────────┐                                   │
│                       │  Final Summary  │  Aggregated results               │
│                       │  (Job 4)        │  PR comments, notifications       │
│                       └─────────────────┘                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Job Dependencies

| Job | Depends On | Condition |
|-----|------------|-----------|
| `pre-flight-checks` | - | Always runs first |
| `quality-gates` | `pre-flight-checks` | Only if pre-flight GO decision |
| `security-scan` | `pre-flight-checks` | Only if `!inputs.skip_security` |
| `performance-benchmark` | `pre-flight-checks` | Only if `!inputs.skip_performance` |
| `quality-gates-summary` | All above | Always runs (aggregates results) |

### Pre-flight Check Job

The **pre-flight-checks** job runs first and executes all 37 gates:

#### Service Container Configuration

```yaml
services:
  neo4j:
    image: neo4j:5.13.0
    env:
      NEO4J_AUTH: neo4j/test_password
    ports:
      - 7687:7687
      - 7474:7474
    options: >-
      --health-cmd "cypher-shell -u neo4j -p test_password 'RETURN 1'"
      --health-interval 10s
      --health-timeout 5s
      --health-retries 5
```

#### Pre-flight Checks Executed

| Category | Gates | Critical Count |
|----------|-------|----------------|
| Environment (ENV-*) | ENV-001 to ENV-012 | 3 (ENV-001, ENV-002, ENV-003) |
| Neo4j (NEO-*) | NEO-001 to NEO-010 | 3 (NEO-001, NEO-002, NEO-003) |
| Authentication (AUTH-*) | AUTH-001 to AUTH-007 | 3 (AUTH-001, AUTH-002, AUTH-003) |
| Agents (AGENT-*) | AGENT-001 to AGENT-008 | 2 (AGENT-001, AGENT-002) |
| **Total** | **37 gates** | **11 critical** |

#### NO-GO Decision Handling

When pre-flight checks result in a **NO-GO** decision:

1. The job fails with exit code 1
2. All downstream jobs are skipped
3. A summary is posted to the GitHub Actions step summary
4. Blocking issues are listed in the output

```yaml
- name: Parse pre-flight results and check decision
  run: |
    if [ "$DECISION" == "NO-GO" ]; then
      echo "### Blockers" >> $GITHUB_STEP_SUMMARY
      echo "The following blocking checks failed:" >> $GITHUB_STEP_SUMMARY
      exit 1  # Blocks downstream jobs
    fi
```

**Example NO-GO Output:**
```
## Pre-flight Check Results

| Metric | Value |
|--------|-------|
| Total Checks | 37 |
| Passed Checks | 28 |
| Pass Rate | 75.7% |
| Decision | NO-GO |

### Blockers
The following blocking checks failed:
- ENV-001: Gateway token set
- NEO-001: Neo4j reachable on port 7687

**Pre-flight check failed. Stopping workflow.**
```

### Viewing Pre-flight Results

#### In GitHub Actions UI

1. Navigate to the Actions tab
2. Select the Quality Gates workflow run
3. Click on the **Pre-flight Checks** job
4. Expand the **Parse pre-flight results** step

#### Downloading Artifacts

Pre-flight results are saved as artifacts:

```bash
# Download preflight.json artifact
curl -L -o preflight.json \
  https://github.com/owner/repo/actions/runs/RUN_ID/artifacts/preflight-report-RUN_ID
```

#### From Workflow Summary

The job summary is displayed at the top of the workflow run page:

```
## Pre-flight Check Results

| Metric | Value |
|--------|-------|
| Total Checks | 37 |
| Passed Checks | 35 |
| Pass Rate | 94.6% |
| Decision | GO |

**Pre-flight check passed. Proceeding with workflow.**
```

### Gate Mapping to CI Jobs

| Gate ID | Category | CI Job | On Failure |
|---------|----------|--------|------------|
| ENV-001 | Environment | pre-flight-checks | Pipeline stops |
| ENV-002 | Environment | pre-flight-checks | Pipeline stops |
| ENV-003 | Environment | pre-flight-checks | Pipeline stops |
| ENV-004 | Environment | pre-flight-checks | Warning only |
| ENV-005 | Environment | pre-flight-checks | Warning only |
| ENV-006 | Environment | pre-flight-checks | Warning only |
| ENV-007 | Environment | pre-flight-checks | Warning only |
| ENV-008 | Environment | pre-flight-checks | Warning only |
| ENV-009 | Environment | pre-flight-checks | Warning only |
| ENV-010 | Environment | pre-flight-checks | Warning only |
| ENV-011 | Environment | pre-flight-checks | Warning only |
| ENV-012 | Environment | pre-flight-checks | Warning only |
| NEO-001 | Neo4j | pre-flight-checks | Pipeline stops |
| NEO-002 | Neo4j | pre-flight-checks | Pipeline stops |
| NEO-003 | Neo4j | pre-flight-checks | Pipeline stops |
| NEO-004 | Neo4j | pre-flight-checks | Warning only |
| NEO-005 | Neo4j | pre-flight-checks | Warning only |
| NEO-006 | Neo4j | pre-flight-checks | Warning only |
| NEO-007 | Neo4j | pre-flight-checks | Warning only |
| NEO-008 | Neo4j | pre-flight-checks | Warning only |
| NEO-009 | Neo4j | pre-flight-checks | Skipped (optional) |
| NEO-010 | Neo4j | pre-flight-checks | Warning only |
| AUTH-001 | Auth | pre-flight-checks | Pipeline stops |
| AUTH-002 | Auth | pre-flight-checks | Pipeline stops |
| AUTH-003 | Auth | pre-flight-checks | Pipeline stops |
| AUTH-004 | Auth | pre-flight-checks | Warning only |
| AUTH-005 | Auth | pre-flight-checks | Warning only |
| AUTH-006 | Auth | pre-flight-checks | Warning only |
| AUTH-007 | Auth | pre-flight-checks | Warning only |
| AGENT-001 | Agents | pre-flight-checks | Pipeline stops |
| AGENT-002 | Agents | pre-flight-checks | Pipeline stops |
| AGENT-003 | Agents | pre-flight-checks | Warning only |
| AGENT-004 | Agents | pre-flight-checks | Warning only |
| AGENT-005 | Agents | pre-flight-checks | Warning only |
| AGENT-006 | Agents | pre-flight-checks | Warning only |
| AGENT-007 | Agents | pre-flight-checks | Warning only |
| AGENT-008 | Agents | pre-flight-checks | Warning only |

### Quality Gates Job

The **quality-gates** job runs code quality checks:

| Check | Tool | Threshold |
|-------|------|-----------|
| Black Formatting | black | No formatting errors |
| Ruff Linting | ruff | No linting errors |
| Import Sorting | isort | Correct import order |
| Type Checking | mypy | No type errors (non-blocking) |
| Test Execution | pytest | All tests pass |
| Code Coverage | pytest-cov | >= 80% |

### Security Scan Job

The **security-scan** job runs security analysis:

| Tool | Purpose | Failure Condition |
|------|---------|-------------------|
| Bandit | Python security linter | High severity issues |
| Safety | Dependency vulnerability scan | Known vulnerabilities |
| pip-audit | PyPI package audit | Known CVEs |

### Performance Benchmark Job

The **performance-benchmark** job runs performance tests:

| Check | Tool | Threshold |
|-------|------|-----------|
| Benchmark Execution | pytest-benchmark | All benchmarks complete |
| Regression Detection | custom comparison | < 10% regression vs baseline |

### Debugging Failures in CI

1. **Download Artifacts:**
   ```bash
   # Download coverage report from CI artifacts
   # Or reproduce locally:
   pytest --cov-report=html
   open htmlcov/index.html
   ```

2. **Reproduce Locally:**
   ```bash
   # Match CI Python version
   python --version

   # Run same checks as CI
   pytest -v --tb=short

   # Run pre-flight checks
   python -m scripts.pre_flight_check
   ```

3. **Check Environment Differences:**
   ```bash
   # Compare dependencies
   pip freeze > requirements-frozen.txt
   diff requirements.txt requirements-frozen.txt
   ```

---

## Gate Override Process

### CI Override Inputs

The workflow supports manual overrides via workflow dispatch inputs:

| Input | Type | Description |
|-------|------|-------------|
| `skip_tests` | boolean | Skip test execution (for emergency fixes) |
| `skip_security` | boolean | Skip security scan (for emergency fixes) |
| `skip_performance` | boolean | Skip performance benchmarks (for emergency fixes) |

### Using Override Inputs

#### Via GitHub Web UI

1. Navigate to **Actions** > **Quality Gates**
2. Click **Run workflow**
3. Select the branch
4. Check the appropriate override boxes:
   - [ ] Skip test execution
   - [ ] Skip security scan
   - [ ] Skip performance benchmarks
5. Click **Run workflow**

#### Via GitHub CLI

```bash
# Skip tests for emergency fix
gh workflow run quality-gates.yml \
  --ref main \
  -f skip_tests=true

# Skip security scan (requires approval)
gh workflow run quality-gates.yml \
  --ref main \
  -f skip_security=true

# Skip multiple checks
gh workflow run quality-gates.yml \
  --ref main \
  -f skip_tests=true \
  -f skip_performance=true
```

#### Via API

```bash
# Trigger workflow with overrides
curl -X POST \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/owner/repo/actions/workflows/quality-gates.yml/dispatches \
  -d '{
    "ref": "main",
    "inputs": {
      "skip_tests": "true",
      "skip_security": "false",
      "skip_performance": "true"
    }
  }'
```

### Emergency Override Procedures

#### When to Override (Emergencies Only)

Gate overrides should only be used in genuine emergencies:

1. **Production Outage**: Critical bug fix needed immediately
2. **Security Incident**: Security patch must be deployed
3. **Dependency Failure**: External service failure causing false negatives
4. **Known Issue**: Gate failure is a known issue with approved workaround

**DO NOT override gates for:**
- Convenience or time pressure
- Unreviewed code changes
- Test failures that haven't been investigated
- Coverage gaps in new features

#### Required Approvals

To override a quality gate:

1. **Technical Lead Approval**: Must be approved by a technical lead or architect
2. **Security Review**: Security-related gate overrides require security team approval
3. **Documentation**: Override must be documented with justification

**Approval Process:**
```
1. Create override request ticket
2. Document business justification
3. Identify risks and mitigations
4. Obtain required approvals
5. Execute override with monitoring
6. Post-incident review within 48 hours
```

### Documentation Requirements

All gate overrides must include:

1. **Override Request ID**: Unique identifier for tracking
2. **Gate(s) Being Overridden**: Specific gate IDs (e.g., ENV-001, NEO-003)
3. **Justification**: Detailed explanation of why override is necessary
4. **Risk Assessment**: Potential risks of deploying without gate passing
5. **Mitigation Plan**: Steps to address the underlying issue
6. **Timeline**: When the issue will be properly fixed
7. **Approvals**: Names and timestamps of approvers

**Override Template:**
```markdown
## Gate Override Request

**Request ID:** GO-2024-001
**Date:** 2024-01-15
**Requestor:** Jane Doe

### Gates Overridden
- ENV-001 (Gateway token validation)
- NEO-005 (Index validation)

### Justification
Production outage due to expired gateway token. Emergency fix required
to restore service. Token renewal process is underway but will take
2 hours. Service degradation is affecting 10,000+ users.

### Risk Assessment
- **Risk Level**: Medium
- **Impact**: Temporary bypass of security validation
- **Mitigation**: Token renewal in progress; manual monitoring active

### Mitigation Plan
1. Renew gateway token (ETA: 2 hours)
2. Re-run pre-flight checks
3. Remove override
4. Post-incident review

### Timeline
- Override expires: 2024-01-15 18:00 UTC
- Fix completion: 2024-01-15 16:00 UTC
- Review scheduled: 2024-01-17 10:00 UTC

### Approvals
- **Technical Lead**: John Smith (2024-01-15 14:30 UTC)
- **Security Team**: Security On-Call (2024-01-15 14:35 UTC)
```

### Executing an Override

**Temporary Override (Single Deployment):**
```bash
# Set override environment variable
export GATE_OVERRIDE_ENV_001=true
export GATE_OVERRIDE_NEO_005=true

# Run deployment with override
./deploy.sh --with-overrides
```

**Programmatic Override:**
```python
# In deployment script
import os

# Check for override
if os.environ.get('GATE_OVERRIDE_ENV_001'):
    logger.warning("OVERRIDE: Skipping ENV-001 validation")
else:
    # Normal validation
    validate_gateway_token()
```

**CI/CD Override:**
```yaml
# In GitHub Actions workflow (requires manual approval)
- name: Deploy with Override
  if: github.event.inputs.override == 'true'
  env:
    GATE_OVERRIDE: ${{ github.event.inputs.gates_to_override }}
  run: |
    echo "WARNING: Deploying with gate overrides: $GATE_OVERRIDE"
    ./deploy.sh --override-gates "$GATE_OVERRIDE"
```

### Post-Override Review

All overrides must be reviewed within 48 hours:

1. **Root Cause Analysis**: Why did the gate fail?
2. **Process Review**: Could this have been prevented?
3. **Fix Verification**: Was the underlying issue resolved?
4. **Documentation Update**: Update runbooks if needed

**Review Template:**
```markdown
## Post-Override Review

**Override ID:** GO-2024-001
**Review Date:** 2024-01-17

### Root Cause
Gateway token expired due to missing renewal automation.

### Resolution
- Token renewed manually
- Automation added for future renewals
- Monitoring added for token expiration

### Lessons Learned
- Need automated token renewal
- Better monitoring for credential expiration
- Override process worked well

### Action Items
- [ ] Implement token renewal automation
- [ ] Add expiration alerts
- [ ] Update runbook with renewal procedure
```

---

## Troubleshooting Guide

### "Coverage Below Threshold"

**Symptoms:**
```
FAIL: Coverage below 80% (actual: 75.3%)
```

**Solutions:**

1. **Check Coverage Report:**
   ```bash
   pytest --cov-report=html
   open htmlcov/index.html
   ```

2. **Identify Uncovered Code:**
   ```bash
   # Show missing lines in terminal
   pytest --cov-report=term-missing
   ```

3. **Add Missing Tests:**
   ```python
   # Example: Add test for uncovered function
   def test_uncovered_function():
       result = my_module.uncovered_function()
       assert result is not None
   ```

4. **Exclude Non-Critical Code:**
   ```ini
   # In pytest.ini
   [coverage:run]
   omit =
       tests/*
       */tests/*
       scripts/debug_*.py
   ```

---

### "Tests Failing"

**Symptoms:**
```
FAILED tests/test_example.py::TestExample::test_something - AssertionError
```

**Solutions:**

1. **Run Single Test with Debug:**
   ```bash
   pytest tests/test_example.py::TestExample::test_something -v --tb=long
   ```

2. **Check for Environment Issues:**
   ```bash
   # Verify Neo4j is running
   python -m scripts.pre_flight_check --category neo4j

   # Check environment variables
   python -m scripts.pre_flight_check --category environment
   ```

3. **Use Fallback Mode for Tests:**
   ```bash
   export FALLBACK_MODE=true
   pytest
   ```

4. **Run with PDB:**
   ```bash
   pytest --pdb -x
   ```

---

### "Linting Errors"

**Symptoms:**
```
error: E501 line too long (120 > 88 characters)
error: F401 'module' imported but unused
```

**Solutions:**

1. **Auto-Fix with Ruff:**
   ```bash
   ruff check . --fix
   ```

2. **Auto-Format with Black:**
   ```bash
   black .
   ```

3. **Check Specific File:**
   ```bash
   ruff check myfile.py
   black --check --diff myfile.py
   ```

4. **Configure Ignores (if needed):**
   ```toml
   # In pyproject.toml
   [tool.ruff]
   line-length = 100
   ignore = ["E501"]
   ```

---

### "Type Check Failures"

**Symptoms:**
```
error: Argument 1 to "function" has incompatible type "str"; expected "int"
```

**Solutions:**

1. **Run Type Checker:**
   ```bash
   mypy .
   ```

2. **Fix Type Annotations:**
   ```python
   # Before
   def process(data):
       return data + 1

   # After
   def process(data: int) -> int:
       return data + 1
   ```

3. **Add Type Stubs:**
   ```bash
   pip install types-requests types-python-dateutil
   ```

---

### "Neo4j Connection Failed"

**Symptoms:**
```
[NEO-001] Neo4j reachable on port 7687 [CRITICAL]
  Status:   FAIL
  Output:   FAIL: Cannot connect to localhost:7687
```

**Solutions:**

1. **Start Neo4j:**
   ```bash
   docker run -d \
     --name neo4j \
     -p 7687:7687 -p 7474:7474 \
     -e NEO4J_AUTH=neo4j/test_password \
     neo4j:5.13.0
   ```

2. **Use Fallback Mode:**
   ```bash
   export FALLBACK_MODE=true
   python -m scripts.pre_flight_check
   ```

3. **Check Credentials:**
   ```bash
   # Verify NEO4J_PASSWORD is set
   python -m scripts.pre_flight_check --category environment
   ```

---

### "Critical Gate Failed"

**Symptoms:**
```
DECISION: NO-GO
BLOCKING ISSUES
  - [ENV-001] Gateway token set: OPENCLAW_GATEWAY_TOKEN not set
```

**Solutions:**

1. **Check All Critical Gates:**
   ```bash
   python -m scripts.pre_flight_check 2>&1 | grep -A2 "CRITICAL"
   ```

2. **Fix Environment Variables:**
   ```bash
   # Check .env file exists
   ls -la .env

   # Create if missing
   touch .env

   # Add required variables
   echo "OPENCLAW_GATEWAY_TOKEN=$(openssl rand -hex 32)" >> .env
   echo "NEO4J_PASSWORD=$(openssl rand -base64 24)" >> .env
   echo "AGENTS_HMAC_SECRET=$(openssl rand -hex 64)" >> .env
   ```

3. **Source Environment:**
   ```bash
   export $(cat .env | xargs)
   ```

---

## Appendix: Quick Reference

### All Gates Summary

| Gate ID | Category | Description | Critical | CI Job |
|---------|----------|-------------|----------|--------|
| ENV-001 | Environment | Gateway token >= 32 chars | Yes | pre-flight-checks |
| ENV-002 | Environment | Neo4j password >= 16 chars | Yes | pre-flight-checks |
| ENV-003 | Environment | HMAC secret >= 64 chars | Yes | pre-flight-checks |
| ENV-004 | Environment | Signal account configured | No | pre-flight-checks |
| ENV-005 | Environment | Admin phones configured | No | pre-flight-checks |
| ENV-006 | Environment | Cloud storage credentials | No | pre-flight-checks |
| ENV-007 | Environment | Backup encryption key | No | pre-flight-checks |
| ENV-008 | Environment | Workspace directory exists | No | pre-flight-checks |
| ENV-009 | Environment | Souls directory exists | No | pre-flight-checks |
| ENV-010 | Environment | Agent directories >= 6 | No | pre-flight-checks |
| ENV-011 | Environment | moltbot.json valid | No | pre-flight-checks |
| ENV-012 | Environment | Docker socket accessible | No | pre-flight-checks |
| NEO-001 | Neo4j | Neo4j reachable on port 7687 | Yes | pre-flight-checks |
| NEO-002 | Neo4j | Bolt connection works | Yes | pre-flight-checks |
| NEO-003 | Neo4j | Write capability | Yes | pre-flight-checks |
| NEO-004 | Neo4j | Connection pool healthy | No | pre-flight-checks |
| NEO-005 | Neo4j | Index validation >= 10 | No | pre-flight-checks |
| NEO-006 | Neo4j | Constraint validation >= 5 | No | pre-flight-checks |
| NEO-007 | Neo4j | Migration version check | No | pre-flight-checks |
| NEO-008 | Neo4j | Fallback mode test | No | pre-flight-checks |
| NEO-009 | Neo4j | Read replica check | No | pre-flight-checks |
| NEO-010 | Neo4j | Query performance < 100ms | No | pre-flight-checks |
| AUTH-001 | Auth | HMAC generation works | Yes | pre-flight-checks |
| AUTH-002 | Auth | HMAC verification works | Yes | pre-flight-checks |
| AUTH-003 | Auth | Invalid HMAC rejected | Yes | pre-flight-checks |
| AUTH-004 | Auth | Gateway token validation | No | pre-flight-checks |
| AUTH-005 | Auth | Invalid token rejected | No | pre-flight-checks |
| AUTH-006 | Auth | Agent-to-agent auth | No | pre-flight-checks |
| AUTH-007 | Auth | Message signature valid | No | pre-flight-checks |
| AGENT-001 | Agents | All 6 agents configured | Yes | pre-flight-checks |
| AGENT-002 | Agents | Agent directories exist | Yes | pre-flight-checks |
| AGENT-003 | Agents | Agent models configured | No | pre-flight-checks |
| AGENT-004 | Agents | Agent communication enabled | No | pre-flight-checks |
| AGENT-005 | Agents | Failover configuration valid | No | pre-flight-checks |
| AGENT-006 | Agents | Default agent specified | No | pre-flight-checks |
| AGENT-007 | Agents | Agent IDs unique | No | pre-flight-checks |
| AGENT-008 | Agents | Workspace paths valid | No | pre-flight-checks |

### CI Jobs Summary

| Job | Purpose | Gates/Checks | Dependencies |
|-----|---------|--------------|--------------|
| pre-flight-checks | Run all 37 gates | ENV-001..012, NEO-001..010, AUTH-001..007, AGENT-001..008 | None |
| quality-gates | Code quality & tests | Black, Ruff, isort, mypy, pytest, coverage | pre-flight-checks |
| security-scan | Security analysis | Bandit, Safety, pip-audit | pre-flight-checks |
| performance-benchmark | Performance tests | pytest-benchmark, regression detection | pre-flight-checks |
| quality-gates-summary | Final aggregation | All job results | All above |

### Common Commands

```bash
# Run all pre-flight checks
python -m scripts.pre_flight_check

# Run specific category
python -m scripts.pre_flight_check --category environment
python -m scripts.pre_flight_check --category neo4j
python -m scripts.pre_flight_check --category auth
python -m scripts.pre_flight_check --category agents

# Run tests
pytest
pytest -m unit
pytest -m integration
pytest --no-cov

# Check formatting
black --check --diff .
ruff check .

# Fix formatting
black .
ruff check . --fix

# Generate coverage report
pytest --cov-report=html
open htmlcov/index.html
```

---

*Last updated: 2026-02-04*
*Quality Gate Version: 1.0*
