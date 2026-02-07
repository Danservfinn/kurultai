# Railway Deployment Plan: OpenClaw Multi-Agent System

**Plan Status:** Draft
**Created:** 2026-02-04
**Goal:** Deploy OpenClaw 6-Agent System with Neo4j to Railway (Production)

---

## Overview

**Goal:** Deploy the OpenClaw 6-Agent Multi-Agent System with Neo4j operational memory to Railway and set it live at kublai.kurult.ai.

### Approach:
1. Push latest commits to GitHub (including runbooks)
2. Wipe existing Railway project and create new deployment
3. Configure Neo4j database service
4. Configure environment variables
5. Deploy and verify health endpoints
6. Set live DNS

### Critical Files:
- `railway.yml` - Railway service configuration (moltbot + neo4j)
- `Dockerfile` - Container image definition
- `requirements.txt` - Python dependencies
- `.env.example` - Environment variable reference
- `health_server.py` - Health check endpoint
- `monitoring/runbooks/` - Error recovery documentation

---

## Phase 1: Git Repository Preparation

**Status:** Pending
**Tasks:** 2
**Parallelizable:** No (sequential)

### Task 1.1: Push Commit to GitHub

**Description:** Push the runbooks commit (6f4ff49) to origin/main

**Files:**
- Git remote: origin/main

**Steps:**
```bash
git push origin main
```

**Acceptance:**
- git status shows "up to date"
- Commit visible on GitHub

**Dependencies:** None

### Task 1.2: Verify Railway.yml Configuration

**Description:** Ensure railway.yml is properly configured for deployment

**Files:**
- Review: railway.yml
- Review: Dockerfile
- Review: requirements.txt

**Acceptance:**
- railway.yml has moltbot and neo4j services defined
- Health check paths are correct
- Volume mounts configured for persistence
- Environment variables documented

**Dependencies:** Task 1.1

---

## Phase 2: Railway Project Setup

**Status:** Pending
**Tasks:** 3
**Parallelizable:** No

### Task 2.1: Access Railway Dashboard

**Description:** Log into Railway and prepare for project creation

**Steps:**
1. Navigate to https://railway.app
2. Log in to account
3. Go to Projects section

**Acceptance:**
- Logged into Railway dashboard
- Ready to create new project

**Dependencies:** Task 1.2

### Task 2.2: Wipe/Remove Existing Project

**Description:** Remove the existing Railway project to start fresh

**Steps:**
1. Locate the existing molt/kurultai project
2. Go to Project Settings
3. Select "Delete Project" or "Reset"
4. Confirm deletion

**Acceptance:**
- Old project removed
- Clean slate for new deployment

**Dependencies:** Task 2.1

### Task 2.3: Create New Railway Project from GitHub

**Description:** Create a new Railway project connected to the molt repository

**Steps:**
1. Click "New Project" → "Deploy from GitHub repo"
2. Select the molt repository
3. Railway will auto-detect railway.yml configuration
4. Name the project (e.g., "kurultai-molt" or "kublai")
5. Select region (prefer US East for lowest latency)

**Acceptance:**
- Project created from GitHub
- railway.yml services detected (moltbot + neo4j)
- Build triggered automatically

**Dependencies:** Task 2.2

---

## Phase 3: Environment Configuration

**Status:** Pending
**Tasks:** 2
**Parallelizable:** Yes

### Task 3.1: Configure Neo4j Credentials

**Description:** Set strong Neo4j password in Railway variables

**Files:**
- Railway Variables: NEO4J_PASSWORD, NEO4J_USER

**Steps:**
1. Go to neo4j service in Railway
2. Variables tab
3. Set NEO4J_USER=neo4j
4. Set NEO4J_PASSWORD to a strong password (generate via Railway or use existing)

**Acceptance:**
- NEO4J_USER set to "neo4j"
- NEO4J_PASSWORD set (strong, saved)

**Dependencies:** Task 2.3

### Task 3.2: Configure Application Secrets

**Description:** Set required environment variables for moltbot service

**Files:**
- Railway Variables: OPENCLAW_GATEWAY_TOKEN, AGENT_AUTH_SECRET, etc.

**Steps:**
1. Go to moltbot service in Railway
2. Variables tab
3. Set required variables:
   - OPENCLAW_GATEWAY_URL=https://kublai.kurultai (or Railway domain)
   - OPENCLAW_GATEWAY_TOKEN - generate secure token
   - AGENT_AUTH_SECRET - generate 32+ char secret
   - SIGNAL_ACCOUNT_NUMBER - if using Signal
   - LOG_LEVEL=info

**Acceptance:**
- All critical variables set
- Gateway token generated and saved
- Agent auth secret generated and saved

**Dependencies:** Task 2.3

---

## Phase 4: Deployment

**Status:** Pending
**Tasks:** 2
**Parallelizable:** No (sequential)

### Task 4.1: Trigger Initial Deployment

**Description:** Trigger deployment and monitor build logs

**Steps:**
1. Click "Deploy" on Railway project
2. Monitor build logs for errors
3. Wait for both services to become healthy
4. Check that neo4j starts first (depends_on configured)

**Acceptance:**
- Build completes without errors
- neo4j service shows "Healthy"
- moltbot service shows "Healthy"

**Dependencies:** Tasks 3.1, 3.2

### Task 4.2: Verify Service Health

**Description:** Confirm both services are responding correctly

**Steps:**
```bash
# Check moltbot health
curl https://<railway-domain>.railway.app/health

# Check Neo4j Browser access
# Navigate to: https://<railway-domain>.railway.app:7474
# Login with neo4j / <NEO4J_PASSWORD>
```

**Acceptance:**
- /health returns 200 OK
- Neo4j Browser accessible at :7474
- Neo4j accepts bolt connections

**Dependencies:** Task 4.1

---

## Phase 5: DNS Configuration (Set Live)

**Status:** Pending
**Tasks:** 2
**Parallelizable:** No

### Task 5.1: Configure Custom Domain

**Description:** Set up kublai.kurult.ai to point to Railway deployment

**Steps:**
1. Go to moltbot service in Railway
2. "Networking" tab
3. "Generate Domain" or "Custom Domain"
4. Enter kublai.kurult.ai
5. Railway will provide CNAME target

**Acceptance:**
- Domain added to Railway
- CNAME target provided

**Dependencies:** Task 4.2

### Task 5.2: Update DNS Records

**Description:** Update DNS records for kublai.kurult.ai

**Steps:**
1. Go to DNS provider (where kurult.ai is hosted)
2. Add CNAME record:
   - Name: kublai (or * for wildcard)
   - Target: Railway-provided domain
   - TTL: 300 (or as low as possible)
3. Save DNS changes

**Acceptance:**
- CNAME record created
- DNS propagated (check with dig command)

**Dependencies:** Task 5.1

---

## Phase 6: Verification & Smoke Tests

**Status:** Pending
**Tasks:** 2
**Parallelizable:** Yes

### Task 6.1: Health Endpoint Tests

**Description:** Verify all health endpoints are accessible

**Steps:**
```bash
# Moltbot health check
curl -f https://kublai.kurult.ai/health

# Expected response: {"status": "healthy", "service": "openclaw-agent-config", ...}
```

**Acceptance:**
- HTTPS works on custom domain
- Health check returns valid JSON
- No 502 errors

**Dependencies:** Task 5.2

### Task 6.2: Neo4j Connectivity Test

**Description:** Verify Neo4j is accessible from application

**Steps:**
1. Check Railway logs for Neo4j connection
2. Verify no Neo4j connection errors in logs
3. Test Neo4j Browser at https://kublai.kurult.ai:7474

**Acceptance:**
- Neo4j logs show successful startup
- No connection errors in application logs
- Neo4j Browser loads and accepts login

**Dependencies:** Task 5.2

---

## Phase 7: Runbooks Integration Verification

**Status:** Pending
**Tasks:** 1
**Parallelizable:** No

### Task 7.1: Verify Error Recovery Runbooks Accessible

**Description:** Confirm runbooks are available in deployed container

**Steps:**
1. Check that monitoring/runbooks/ directory exists in container
2. Verify ErrorRecoveryManager can load runbooks
3. Check Railway build logs for file copy confirmation

**Acceptance:**
- Runbooks directory present in container
- All 7 runbook files accessible
- ErrorRecoveryManager.load_runbook() works for all scenarios

**Dependencies:** Task 4.2

---

## Dependencies

```
Phase 1 (Git Prep)
    └── Phase 2 (Railway Setup) - depends on Phase 1
        └── Phase 3 (Env Config) - depends on Phase 2
            ├── Phase 4 (Deploy) - depends on Phase 3
            │   └── Phase 5 (DNS) - depends on Phase 4
            │       └── Phase 6 (Verify) - depends on Phase 5
            └── Phase 7 (Runbooks) - depends on Phase 4
```

---

## Pre-Deployment Checklist

### Git Repository
- [ ] All commits pushed to origin/main
- [ ] railway.yml is up to date
- [ ] Dockerfile is current
- [ ] requirements.txt includes all dependencies

### Railway Configuration
- [ ] Account is active and has credits
- [ ] Repository is connected to GitHub
- [ ] Build can access public npm/pypi packages

### Security
- [ ] NEO4J_PASSWORD is strong (16+ chars)
- [ ] OPENCLAW_GATEWAY_TOKEN is generated (32+ chars)
- [ ] AGENT_AUTH_SECRET is generated (32+ chars)
- [ ] .env file is NOT in repository (gitignored)

### Domain
- [ ] DNS provider access available
- [ ] Domain kublai.kurult.ai is owned/controlled

---

## Post-Deployment Verification

### Health Checks
- [ ] https://kublai.kurult.ai/health returns 200
- [ ] Neo4j Browser accessible at :7474
- [ ] No critical errors in Railway logs

### Functionality
- [ ] Moltbot gateway responds on port 18789
- [ ] Neo4j stores and retrieves data
- [ ] Error recovery runbooks are loaded by ErrorRecoveryManager
- [ ] Health check passes for both services

### Monitoring
- [ ] Railway metrics dashboard accessible
- [ ] Logs are being collected
- [ ] Alerts configured (if available in plan)

---

## Rollback Plan

If deployment fails:
1. Check Railway build logs for specific errors
2. Verify environment variables are correctly set
3. Check neo4j service is healthy before moltbot
4. If DNS fails, use Railway-provided domain temporarily
5. Runbooks are static - deployment not critical for runbooks functionality

---

## Success Criteria

Deployment Complete:
- Code pushed to GitHub and visible in Railway
- Both services (moltbot, neo4j) show "Healthy" status
- Custom domain kublai.kurult.ai is accessible
- Health endpoints return valid responses
- Neo4j Browser is functional
- Error recovery runbooks are accessible in the container
