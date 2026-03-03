# Implementation Plan - Critical Gap Remediation
**Created:** 2026-02-24
**Status:** Ready for Execution

---

## Phase 1: Critical Stabilization (IMMEDIATE - Execute Now)

### 1.1 Move Codebase to Permanent Location
**Priority:** 🔴 CRITICAL
**Risk:** Data loss on system restart

```bash
# Create permanent workspace
mkdir -p ~/kurultai

# Move codebase from temp to permanent
mv /tmp/kublai-repo ~/kurultai/kublai-repo

# Update any hardcoded paths in scripts
sed -i 's|/tmp/kublai-repo|~/kurultai/kublai-repo|g' ~/kurultai/kublai-repo/.env
sed -i 's|/tmp/kublai-repo|~/kurultai/kublai-repo|g' ~/kurultai/kublai-repo/scripts/*.py

# Create symlink for backward compatibility
ln -s ~/kurultai/kublai-repo /tmp/kublai-repo
```

**Verification:**
```bash
ls -la ~/kurultai/kublai-repo/tools/kurultai/heartbeat_master.py
```

---

### 1.2 Install Kublai Self-Awareness System
**Priority:** 🔴 CRITICAL
**Gap:** Architecture.md references modules not in root codebase

```bash
cd ~/kurultai/kublai-repo

# Create src directory structure
mkdir -p src/kublai
mkdir -p src/workflow
mkdir -p src/agents/ogedei
mkdir -p src/agents/temujin

# Copy self-awareness modules from railway template
cp moltbot-railway-template/src/kublai/architecture-introspection.js src/kublai/
cp moltbot-railway-template/src/kublai/proactive-reflection.js src/kublai/
cp moltbot-railway-template/src/kublai/delegation-protocol.js src/kublai/
cp moltbot-railway-template/src/kublai/scheduled-reflection.js src/kublai/
cp moltbot-railway-template/src/kublai/index.js src/kublai/

# Copy workflow components
cp moltbot-railway-template/src/workflow/*.js src/workflow/

# Copy agent handlers
cp moltbot-railway-template/src/agents/ogedei/*.js src/agents/ogedei/
cp moltbot-railway-template/src/agents/temujin/*.js src/agents/temujin/

# Install Node.js dependencies
npm init -y
npm install neo4j-driver express dotenv
```

**Verification:**
```bash
ls -la src/kublai/
node -e "require('./src/kublai/architecture-introspection.js')"
```

---

### 1.3 Restart Heartbeat Daemon with Persistence
**Priority:** 🔴 CRITICAL
**Gap:** Daemon killed, no background tasks running

```bash
cd ~/kurultai/kublai-repo
source venv/bin/activate
set -a && source .env && set +a

# Kill any existing heartbeat processes
pkill -f heartbeat_master

# Start daemon with nohup for persistence
nohup python -m tools.kurultai.heartbeat_master --daemon > logs/heartbeat.log 2>&1 &

# Save PID for monitoring
echo $! > .heartbeat.pid
```

**Create systemd service (for automatic restart on boot):**
```bash
# Create service file
sudo tee /etc/systemd/system/kurultai-heartbeat.service > /dev/null <<EOF
[Unit]
Description=Kurultai Unified Heartbeat Engine
After=network.target neo4j.service

[Service]
Type=simple
User=$USER
WorkingDirectory=/Users/$USER/kurultai/kublai-repo
Environment=PATH=/Users/$USER/kurultai/kublai-repo/venv/bin
EnvironmentFile=/Users/$USER/kurultai/kublai-repo/.env
ExecStart=/Users/$USER/kurultai/kublai-repo/venv/bin/python -m tools.kurultai.heartbeat_master --daemon
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable service
sudo systemctl daemon-reload
sudo systemctl enable kurultai-heartbeat.service
sudo systemctl start kurultai-heartbeat.service
```

**Verification:**
```bash
ps aux | grep heartbeat_master
sudo systemctl status kurultai-heartbeat
```

---

## Phase 2: Data & Configuration (Within 24 Hours)

### 2.1 Populate Neo4j with Initial Data
**Priority:** 🟡 MODERATE
**Gap:** Empty Task, Capability, AgentKey nodes

```bash
cd ~/kurultai/kublai-repo
source venv/bin/activate

# Create initial agent keys for authentication
python -c "
from tools.kurultai.security import AgentAuthenticator
import os

# Generate keys for all 6 agents
agents = ['kublai', 'mongke', 'chagatai', 'temujin', 'jochi', 'ogedei']
for agent in agents:
    key = AgentAuthenticator.generate_key()
    print(f'{agent}: {key}')
    # Store in Neo4j
"

# Seed initial capabilities for CBAC
python -c "
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv
load_dotenv()

driver = GraphDatabase.driver(
    os.getenv('NEO4J_URI', 'bolt://localhost:7687'),
    auth=(os.getenv('NEO4J_USER', 'neo4j'), os.getenv('NEO4J_PASSWORD'))
)

with driver.session() as session:
    # Create base capabilities
    capabilities = [
        ('research_basic', 'LOW', 'Basic research capability'),
        ('write_content', 'LOW', 'Content writing'),
        ('code_generation', 'MEDIUM', 'Generate code'),
        ('security_audit', 'HIGH', 'Security analysis'),
        ('orchestrate_tasks', 'HIGH', 'Task orchestration'),
        ('ops_monitoring', 'MEDIUM', 'Operations monitoring')
    ]
    
    for cap_id, risk, desc in capabilities:
        session.run('''
            MERGE (c:Capability {id: $id})
            SET c.name = $id,
                c.risk_level = $risk,
                c.description = $desc,
                c.created_at = datetime()
        ''', id=cap_id, risk=risk, desc=desc)
    
    # Grant capabilities to agents
    grants = [
        ('kublai', 'orchestrate_tasks'),
        ('mongke', 'research_basic'),
        ('chagatai', 'write_content'),
        ('temujin', 'code_generation'),
        ('jochi', 'security_audit'),
        ('ogedei', 'ops_monitoring')
    ]
    
    for agent, cap in grants:
        session.run('''
            MATCH (a:Agent {id: $agent}), (c:Capability {id: $cap})
            MERGE (a)-[r:HAS_CAPABILITY]->(c)
            SET r.granted_at = datetime(),
                r.expires_at = datetime() + duration('P90D')
        ''', agent=agent, cap=cap)

driver.close()
print('Capabilities seeded successfully')
"
```

**Verification:**
```bash
python -c "
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv
load_dotenv()

driver = GraphDatabase.driver(os.getenv('NEO4J_URI'), auth=(os.getenv('NEO4J_USER'), os.getenv('NEO4J_PASSWORD')))
with driver.session() as session:
    caps = session.run('MATCH (c:Capability) RETURN count(c) as n').single()['n']
    keys = session.run('MATCH (k:AgentKey) RETURN count(k) as n').single()['n']
    print(f'Capabilities: {caps}, AgentKeys: {keys}')
driver.close()
"
```

---

### 2.2 Configure Missing Environment Variables
**Priority:** 🟡 MODERATE
**Gap:** Authentik and Gateway tokens not set

```bash
cd ~/kurultai/kublai-repo

# Generate secure keys
AUTHE_SECRET=$(openssl rand -hex 32)
AUTHE_BOOTSTRAP=$(openssl rand -hex 16)
GATEWAY_TOKEN=$(openssl rand -hex 32)

# Append to .env
cat >> .env <<EOF

# === Phase 2 Configuration ===
AUTHENTIK_SECRET_KEY=$AUTHE_SECRET
AUTHENTIK_BOOTSTRAP_PASSWORD=$AUTHE_BOOTSTRAP
OPENCLAW_GATEWAY_TOKEN=$GATEWAY_TOKEN

# Notion integration (optional - fill in if available)
# NOTION_API_TOKEN=secret_xxx
# NOTION_DATABASE_ID=xxx

# Railway deployment (fill in if deploying)
# RAILWAY_TOKEN=xxx
# RAILWAY_PROJECT_ID=xxx
EOF

# Secure the .env file
chmod 600 .env
```

**Verification:**
```bash
grep -c "AUTHENTIK_SECRET_KEY" .env
grep -c "OPENCLAW_GATEWAY_TOKEN" .env
```

---

### 2.3 Update OpenClaw Configuration
**Priority:** 🟡 MODERATE
**Gap:** Model configuration conflicts

```bash
# Update openclaw.json to use working model
jq '.agents.defaults.model.primary = "google/gemini-3.1-pro-preview" | 
    .agents.list[].model = "google/gemini-3.1-pro-preview" |
    .agents.defaults.models = {"google/gemini-3.1-pro-preview": {}}' \
    ~/.openclaw/openclaw.json > ~/.openclaw/openclaw.json.tmp && \
mv ~/.openclaw/openclaw.json.tmp ~/.openclaw/openclaw.json
```

---

## Phase 3: Self-Awareness Activation (Within 48 Hours)

### 3.1 Initialize Self-Awareness System
**Priority:** 🟡 MODERATE
**Gap:** System documented but not running

```bash
cd ~/kurultai/kublai-repo

# Run architecture sync to populate Neo4j with ARCHITECTURE.md sections
node scripts/sync-architecture-to-neo4j.js

# Verify sections were created
python -c "
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv
load_dotenv()

driver = GraphDatabase.driver(os.getenv('NEO4J_URI'), auth=(os.getenv('NEO4J_USER'), os.getenv('NEO4J_PASSWORD')))
with driver.session() as session:
    result = session.run('MATCH (s:ArchitectureSection) RETURN count(s) as n')
    print(f'Architecture sections in Neo4j: {result.single()[\"n\"]}')
driver.close()
"
```

---

### 3.2 Create Express API Server for Self-Awareness
**Priority:** 🟡 MODERATE

```bash
cd ~/kurultai/kublai-repo

# Create server file
cat > src/server.js <<'EOF'
const express = require('express');
const { UnifiedHeartbeat } = require('../tools/kurultai/heartbeat_master');
const architectureIntrospection = require('./kublai/architecture-introspection');
const proactiveReflection = require('./kublai/proactive-reflection');
const delegationProtocol = require('./kublai/delegation-protocol');

const app = express();
app.use(express.json());

// Health endpoints
app.get('/health', (req, res) => res.json({ status: 'ok' }));

// Proposal management
app.get('/api/proposals', async (req, res) => {
  const opportunities = await proactiveReflection.getOpportunities(req.query.status);
  res.json(opportunities);
});

app.post('/api/proposals/reflect', async (req, res) => {
  const result = await proactiveReflection.triggerReflection();
  res.json(result);
});

// Workflow control
app.post('/api/workflow/process', async (req, res) => {
  const result = await delegationProtocol.processPendingWorkflows();
  res.json(result);
});

const PORT = process.env.PORT || 8082;
app.listen(PORT, () => {
  console.log(`Kublai Self-Awareness API running on port ${PORT}`);
});
EOF

# Start server
nohup node src/server.js > logs/self-awareness.log 2>&1 &
echo $! > .self-awareness.pid
```

**Verification:**
```bash
curl http://localhost:8082/health
```

---

## Phase 4: Long-Term Architecture (Within 1 Week)

### 4.1 Railway Deployment Synchronization
**Priority:** 🟢 LOW
**Goal:** Deploy local setup to Railway

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login to Railway
railway login

# Link to existing project (if you have the project ID)
railway link --project 26201f75-3375-46ce-98c7-9d1dde5f9569

# Or create new project
# railway init

# Set environment variables in Railway
railway variables set NEO4J_URI="bolt://your-neo4j-instance:7687"
railway variables set NEO4J_USER="neo4j"
railway variables set NEO4J_PASSWORD="your-password"
railway variables set AUTHENTIK_SECRET_KEY="$(grep AUTHENTIK_SECRET_KEY .env | cut -d= -f2)"
railway variables set OPENCLAW_GATEWAY_TOKEN="$(grep OPENCLAW_GATEWAY_TOKEN .env | cut -d= -f2)"

# Deploy
railway up
```

---

### 4.2 Process Management with PM2
**Priority:** 🟢 LOW
**Alternative to systemd for better logging/monitoring**

```bash
# Install PM2 globally
npm install -g pm2

# Create ecosystem file
cat > ecosystem.config.js <<EOF
module.exports = {
  apps: [
    {
      name: 'kurultai-heartbeat',
      script: './venv/bin/python',
      args: '-m tools.kurultai.heartbeat_master --daemon',
      cwd: '/Users/$USER/kurultai/kublai-repo',
      env: {
        NODE_ENV: 'production',
        PYTHONPATH: '/Users/$USER/kurultai/kublai-repo'
      },
      log_file: './logs/heartbeat-combined.log',
      out_file: './logs/heartbeat-out.log',
      error_file: './logs/heartbeat-error.log',
      time: true,
      restart_delay: 10000,
      max_restarts: 5
    },
    {
      name: 'kublai-self-awareness',
      script: './src/server.js',
      cwd: '/Users/$USER/kurultai/kublai-repo',
      env: {
        NODE_ENV: 'production',
        PORT: 8082
      },
      log_file: './logs/self-awareness-combined.log',
      time: true,
      restart_delay: 5000
    }
  ]
};
EOF

# Start with PM2
pm2 start ecosystem.config.js
pm2 save
pm2 startup
```

**Verification:**
```bash
pm2 status
pm2 logs kurultai-heartbeat --lines 20
```

---

## Phase 5: Testing & Validation

### 5.1 Run Integration Tests
```bash
cd ~/kurultai/kublai-repo
source venv/bin/activate

# Run health checks first
python scripts/check_neo4j.py
python scripts/check_agents.py

# Run core tests
pytest tests/integration/test_heartbeat_system.py -v
pytest tests/kurultai/test_unified_heartbeat.py -v

# Run self-awareness tests
npm test -- tests/kublai/
```

---

### 5.2 Verify Full System
```bash
# Check all components
./scripts/pre_flight_check.py

# Query Neo4j for system state
python -c "
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv
load_dotenv()

driver = GraphDatabase.driver(os.getenv('NEO4J_URI'), auth=(os.getenv('NEO4J_USER'), os.getenv('NEO4J_PASSWORD')))

with driver.session() as session:
    print('=== System State ===')
    
    # Heartbeat status
    hc = session.run('MATCH (hc:HeartbeatCycle) RETURN count(hc) as n').single()['n']
    print(f'Heartbeat cycles: {hc}')
    
    # Agent status
    agents = session.run('MATCH (a:Agent) RETURN a.name, a.status').data()
    print(f'\\nAgents: {len(agents)}')
    for a in agents:
        print(f'  - {a[\"a.name\"]}: {a[\"a.status\"]}')
    
    # Capabilities
    caps = session.run('MATCH (c:Capability) RETURN count(c) as n').single()['n']
    print(f'\\nCapabilities: {caps}')
    
    # Architecture sections
    sections = session.run('MATCH (s:ArchitectureSection) RETURN count(s) as n').single()['n']
    print(f'Architecture sections: {sections}')

driver.close()
"
```

---

## Execution Checklist

- [ ] Phase 1.1: Move codebase to ~/kurultai/kublai-repo
- [ ] Phase 1.2: Copy Kublai Self-Awareness modules to src/kublai/
- [ ] Phase 1.3: Restart heartbeat daemon with systemd
- [ ] Phase 2.1: Seed Neo4j with capabilities and agent keys
- [ ] Phase 2.2: Configure missing env vars
- [ ] Phase 2.3: Update OpenClaw model config
- [ ] Phase 3.1: Sync ARCHITECTURE.md to Neo4j
- [ ] Phase 3.2: Start Express API server
- [ ] Phase 4.1: Deploy to Railway (optional)
- [ ] Phase 4.2: Setup PM2 process management
- [ ] Phase 5.1: Run integration tests
- [ ] Phase 5.2: Full system verification

---

## Rollback Plan

If any phase fails:

```bash
# Stop services
sudo systemctl stop kurultai-heartbeat
pm2 delete all

# Restore from temp if needed
mv ~/kurultai/kublai-repo /tmp/kublai-repo-restored

# Check Neo4j backup (if available)
neo4j-admin database dump neo4j --to=/path/to/backup.dump
```

---

## Notes

- **Phase 1** must be completed immediately to prevent data loss
- **Phase 2** should be completed within 24 hours for full functionality
- **Phase 3** enables the Kublai Self-Awareness system documented in ARCHITECTURE.md
- **Phase 4** is optional but recommended for production stability
- All scripts assume macOS/Linux environment with Homebrew
