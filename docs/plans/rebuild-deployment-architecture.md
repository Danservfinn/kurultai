# Kurultai v0.2 Rebuild Deployment Architecture Design

**Status:** Complete Deployment Architecture Design
**Version:** 1.0
**Date:** 2026-02-06
**Author:** Rebuild Architect (team-lead agent)

---

## Executive Summary

After analyzing the integrated plan (`kurultai_0.2.md`), architecture docs, and existing implementation, I've designed the complete deployment topology for Kurultai v0.2. The design focuses on **CORRECTNESS** and leverages existing components while fixing identified gaps.

---

## 1. Service Dependency Graph

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           KURULTAI V0.2 DEPLOYMENT                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐                                                            │
│  │    INTERNET  │                                                           │
│  └──────┬───────┘                                                            │
│         │                                                                   │
│         ▼                                                                   │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │                    Railway Load Balancer                            │     │
│  │                    (kublai.kurult.ai)                               │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│         │                                                                   │
│         ├─────────────────────────────────────────────────────────────────┤
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              authentik-proxy (Caddy) :8080                           │   │
│  │              Public Endpoint / Bypass Routes                          │   │
│  │    ┌──────────────────────────────────────────────────────────────┐  │   │
│  │    │ Route Decision Matrix:                                       │  │   │
│  │    │                                                               │  │   │
│  │    │ /setup/api/signal-link ──┐ Bypass auth → moltbot             │  │   │
│  │    │ /ws/*                 ──┤                                    │  │   │
│  │    │ /outpost.goauthentik.io││                                    │  │   │
│  │    │ /application/*         ││ Authentik server                   │  │   │
│  │    │ /flows/*              │└→                                    │  │   │
│  │    │ /if/*                  │                                    │  │   │
│  │    │ /api/*                 │                                    │  │   │
│  │    │ /* (default)          ──▶ forward_auth → moltbot (if auth) │  │   │
│  │    └──────────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│         │                     │                                           │
│         │ forward_auth         │ internal                                   │
│         ▼                     ▼                                           │
│  ┌──────────────────┐  ┌──────────────────────────────────────────────┐   │
│  │ authentik-server │  │    moltbot-railway-template :8080             │   │
│  │    :9000         │  │    (Express.js Gateway)                       │   │
│  │                  │  │    ┌─────────────────────────────────────────┐│   │
│  │ ┌──────────────┐ │  │    │  Routes:                                 ││   │
│  │ │ WebAuthn     │ │  │    │  - GET  /health                          ││   │
│  │ │              │ │  │    │  - GET  /signal/status                   ││   │
│  │ └──────────────┘ │  │    │  - TODO: /agent/* (agentToAgent gateway) ││   │
│  │                  │  │    │  - TODO: WebSocket proxy to OpenClaw     ││   │
│  │ ┌──────────────┐ │  │    └─────────────────────────────────────────┘│   │
│  │ │   OAuth      │ │  │                                                │   │
│  │ │  Provider    │ │  │  ┌────────────────────────────────────────────┐│   │
│  │ └──────────────┘ │  │  │ Signal CLI Daemon (embedded)               ││   │
│  └──────────────────┘  │  │  - HTTP: 127.0.0.1:8081                     ││   │
│         │              │  │  - Binary: /usr/local/bin/signal-cli        ││   │
│         │              │  │  - Data: /data/.signal                       ││   │
│         │              │  └────────────────────────────────────────────┘│   │
│         │              │             ┌────────────────────────────────────┐│   │
│         │              └─────────────▶│  Python Bridge (TODO: implement)     ││   │
│         │                            │  - OpenClaw protocol                  ││   │
│         │                            │  - Kurultai Engine                   ││   │
│         │                            │  - DelegationProtocol                ││   │
│         │                            └────────────────────────────────────┘│   │
│         └────────────────────────────────────────────────────────────────┘│   │
│                                                                      │    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    AUTHENTIK WORKER                               │   │
│  │                   (Background Tasks)                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                      │    │
└──────────────────────────────────────────────────────────────────────────────┘
                                    │ Railway Private Network
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        EXTERNAL SERVICES (Managed)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐      ┌──────────────────┐                            │
│  │  Neo4j AuraDB    │      │  Railway         │                            │
│  │  (neo4j+s://)    │      │  PostgreSQL      │                            │
│  │                  │      │  (for Authentik) │                            │
│  │  - Operational   │      │                  │                            │
│  │    Memory        │      └──────────────────┘                            │
│  │  - Task Registry │                                                     │
│  │  - Research      │                                                     │
│  │  - Capabilities  │                                                     │
│  │  - Agent Keys    │                                                     │
│  └──────────────────┘                                                     │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Railway Services Specification

| Service Name | Image/Build | Internal Port | Public | Purpose | Health Check |
|---------------|-------------|---------------|--------|---------|--------------|
| **authentik-proxy** | `caddy:2-alpine` | 8080 | YES (domain) | Reverse proxy + forward auth | GET /health |
| **authentik-server** | `ghcr.io/goauthentik/server:2025.10` | 9000 | NO | SSO authentication server | GET /-/health/ready/ |
| **authentik-worker** | `ghcr.io/goauthentik/server:2025.10` | N/A | NO | Background task processing | (none) |
| **moltbot-railway-template** | `node:20-slim` (custom Dockerfile) | 8080 | NO (via proxy) | Gateway + Signal CLI + Python bridge | GET /health |

**Critical Finding:** The existing `moltbot-railway-template` has Express.js routes and Signal CLI embedded but is **MISSING**:
1. Python bridge to OpenClaw protocol
2. `/agent/{target_agent}/message` endpoint for agentToAgent messaging
3. WebSocket proxy to OpenClaw

These MUST be implemented for v0.2 to work.

---

## 3. Environment Variable Flow

### 3.1 Project-Level Variables (Shared Across All Services)

```ini
# Neo4j AuraDB (external managed service)
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=*******
NEO4J_DATABASE=neo4j

# Kurultai Configuration
KURLTAI_ENABLED=true
KURLTAI_MAX_PARALLEL_TASKS=10

# Authentik (shared across server + worker + proxy)
AUTHENTIK_SECRET_KEY=********************************
AUTHENTIK_BOOTSTRAP_PASSWORD=********************************
AUTHENTIK_EXTERNAL_HOST=https://kublai.kurult.ai

# Signal Integration
SIGNAL_LINK_TOKEN=********************************
SIGNAL_ACCOUNT=+1234567890

# Gateway Authentication (for agentToAgent messaging)
OPENCLAW_GATEWAY_TOKEN=********************************
```

### 3.2 Service-Specific Variables

**authentik-server:**
```ini
AUTHENTIK_POSTGRESQL__HOST=postgres.railway.internal
AUTHENTIK_POSTGRESQL__NAME=railway
AUTHENTIK_POSTGRESQL__USER=postgres
AUTHENTIK_POSTGRESQL__PASSWORD=*******
# Inherits project-level AUTHENTIK_* variables
```

**authentik-worker:**
```ini
# Same as authentik-server
AUTHENTIK_POSTGRESQL__HOST=postgres.railway.internal
AUTHENTIK_POSTGRESQL__NAME=railway
AUTHENTIK_POSTGRESQL__USER=postgres
AUTHENTIK_POSTGRESQL__PASSWORD=*******
```

**authentik-proxy:**
```ini
PORT=8080
SIGNAL_LINK_TOKEN=${SIGNAL_LINK_TOKEN}  # For /setup/api/signal-link bypass
```

**moltbot-railway-template:**
```ini
PORT=8080
NODE_ENV=production
LOG_LEVEL=info

# Signal CLI
SIGNAL_ENABLED=true
SIGNAL_ACCOUNT=${SIGNAL_ACCOUNT}
SIGNAL_DATA_DIR=/data/.signal
SIGNAL_CLI_PATH=/usr/local/bin/signal-cli

# Neo4j (for Kurultai Engine)
NEO4J_URI=${NEO4J_URI}
NEO4J_USER=${NEO4J_USER}
NEO4J_PASSWORD=${NEO4J_PASSWORD}

# Gateway Token
OPENCLAW_GATEWAY_TOKEN=${OPENCLAW_GATEWAY_TOKEN}
```

### 3.3 Internal Service URLs (Railway Private Network)

```
authentik-server.railway.internal:9000  → Authentik server
authentik-proxy.railway.internal:8080  → Caddy proxy
moltbot-railway-template.railway.internal:8080  → Moltbot gateway
postgres.railway.internal              → Railway PostgreSQL
```

---

## 4. Health Check Endpoints

| Service | Endpoint | Response Format | Success Criteria |
|---------|----------|-----------------|-------------------|
| **authentik-proxy** | GET /health | `{"status": "healthy"}` | HTTP 200 |
| **moltbot-railway-template** | GET /health | `{"status": "healthy", "signal": {...}}` | HTTP 200 |
| **authentik-server** | GET /-/health/ready/ | Built-in Authentik health response | HTTP 200 |

---

## 5. Authentication Flows

### 5.1 User → Web UI Flow (WebAuthn)

```
1. User navigates to https://kublai.kurult.ai/dashboard
2. Caddy (authentik-proxy) intercepts request
3. Caddy → forward_auth to authentik-server
4. authentik-server: User not authenticated → 302 redirect to /if/flow/authentication/
5. User completes WebAuthn biometric authentication
6. authentik-server sets session cookie, redirects back to /dashboard
7. Caddy validates session via forward_auth, passes request to moltbot
8. moltbot returns authenticated dashboard with X-Authentik-* headers populated
```

### 5.2 Signal Link Bypass Flow

```
1. POST /setup/api/signal-link (with X-Signal-Token header)
2. Caddy: route bypasses forward_auth (token validation only)
3. Caddy validates X-Signal-Token matches env var
4. moltbot: receives request, validates token again (defense in depth)
5. Signal CLI: processes link request
6. Response: 200 OK with Signal account status
```

### 5.3 Agent Messaging Flow (TODO: Must Implement)

```
1. Kublai (main agent) wants to delegate task to specialist
2. DelegationProtocol creates Task node in Neo4j
3. POST http://moltbot-railway-template.railway.internal:8080/agent/researcher/message
   Headers: Authorization: Bearer {OPENCLAW_GATEWAY_TOKEN}
   Body: {"message": "@researcher ...", "context": {"task_id": "...", "reply_to": "main"}}
4. moltbot Python bridge receives request
5. Python processes via OpenClaw protocol
6. Specialist agent (Möngke) processes task
7. Results stored in Neo4j, synthesized back to user
```

---

## 6. Integration Points

### 6.1 Signal CLI ↔ Moltbot
- **Status:** EXISTS (embedded in moltbot container)
- **Protocol:** signal-cli daemon HTTP on 127.0.0.1:8081
- **Data Directory:** /data/.signal (persistent volume needed)
- **Gap:** Need to implement actual send/receive endpoints beyond status checking

### 6.2 Authentik ↔ Moltbot
- **Status:** EXISTS (forward auth configured in Caddyfile)
- **Headers Passed:** X-Authentik-Username, X-Authentik-Email, X-Authentik-Name, X-Authentik-Uid, X-Authentik-Groups
- **Gap:** moltbot doesn't read/use these headers yet for user context

### 6.3 Neo4j ↔ Kurultai Engine
- **Status:** PARTIAL (OperationalMemory class exists in src/protocols/delegation.py)
- **Gap:** No actual Neo4j driver instantiation in moltbot
- **Needed:** Python subprocess bridge from Express.js to OpenClaw/Kurultai

### 6.4 Gateway ↔ Specialist Agents
- **Status:** MISSING (CRITICAL GAP)
- **Needed:** `/agent/{target}/message` endpoint in moltbot
- **Protocol:** DelegationProtocol.delegate_via_agenttoagent() (implemented but no REST endpoint)

---

## 7. Deployment Order

**Phase 1: Foundation (must be first)**
1. Create Neo4j AuraDB instance (free tier: 200k nodes)
2. Create Railway project
3. Set project-level environment variables
4. Generate secure credentials

**Phase 2: Authentication Layer**
5. Deploy authentik-server (depends on Railway PostgreSQL)
6. Deploy authentik-worker
7. Configure Authentik via admin UI:
   - WebAuthn authenticator
   - Authentication flow
   - Proxy provider blueprint
8. Deploy authentik-proxy with Caddyfile

**Phase 3: Application Layer**
9. Deploy moltbot-railway-template
10. Configure custom domain (kublai.kurult.ai) on authentik-proxy
11. Verify end-to-end auth flow
12. Test health endpoints

**Phase 4: Agent System (requires implementation work)**
13. Run Neo4j migrations (schema, indexes, agent keys)
14. Implement missing moltbot endpoints:
    - Python bridge subprocess communication
    - /agent/{target}/message REST endpoint
    - WebSocket proxy to OpenClaw
15. Deploy Kurultai engine configuration
16. Test agent delegation end-to-end

---

## 8. Critical Gaps Identified

| Gap | Severity | Impact | Fix Required |
|-----|----------|--------|-------------|
| **Python bridge missing** | CRITICAL | No agentToAgent messaging, cannot delegate tasks | Implement subprocess bridge from Express.js to Python OpenClaw |
| **/agent/\*/message endpoint** | CRITICAL | Cannot receive agent delegation requests | Add Express route + Python handler |
| **Neo4j driver not initialized** | HIGH | No operational memory, tasks not tracked | Configure Neo4j connection in moltbot, import driver |
| **X-Authentik headers not read** | MEDIUM | No user context in application | Add middleware to read and use headers |
| **Signal send/receive endpoints** | MEDIUM | Cannot send messages via Signal | Add Signal API endpoints to moltbot |

---

## 9. Capability Acquisition (Horde-Learn) Integration

The horde-learn skill is available but needs integration into Kurultai v0.2:

```
┌─────────────────────────────────────────────────────────────────┐
│                     HORDE-LEARN ARCHITECTURE                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. User: "/learn how to send SMS messages"                    │
│       │                                                          │
│       ▼                                                          │
│  2. Kublai: CapabilityClassifier.classify()                     │
│       │                                                          │
│       ▼                                                          │
│  3. Möngke (researcher): Find documentation                     │
│       │                                                          │
│       ▼                                                          │
│  4. Temüjin (developer): Generate code                          │
│       │                                                          │
│       ▼                                                          │
│  5. Jochi (analyst): Validate + security scan                  │
│       │                                                          │
│       ▼                                                          │
│  6. CapabilityRegistry: Store in Neo4j                          │
│       │                                                          │
│       ▼                                                          │
│  7. CBAC: Grant capability to agents                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Skills Directory Structure:**
```
.claude/skills/
├── horde-learn/          # Extract insights from text
├── horde-swarm/          # Parallel agent dispatch (35+ agent types)
├── golden-horde/         # Inter-agent collaboration (8 patterns)
└── horde-skill-creator/  # Create new skills dynamically
```

---

## 10. Next Steps

1. **Immediate:** Implement missing moltbot endpoints (Python bridge, agent messaging)
2. **Then:** Complete Railway deployment per order above
3. **Then:** Configure Authentik WebAuthn and test auth flow
4. **Finally:** Run Neo4j migrations and test agent delegation

---

## Appendix A: File Structure for Implementation

```
molt/
├── authentik-proxy/
│   ├── Caddyfile           # EXISTS - verified correct
│   └── Dockerfile          # EXISTS - uses caddy:2-alpine
├── authentik-server/
│   └── Dockerfile          # EXISTS - uses ghcr.io/goauthentik/server:2025.10
├── authentik-worker/
│   └── Dockerfile          # EXISTS - uses ghcr.io/goauthentik/server:2025.10
├── moltbot-railway-template/
│   ├── Dockerfile          # EXISTS - node:20-slim + signal-cli
│   ├── package.json        # EXISTS - Express.js dependencies
│   ├── src/
│   │   ├── index.js        # EXISTS - Express server, Signal CLI mgmt
│   │   └── config/
│   │       └── channels.js # EXISTS - Signal config
│   └── TODO: Add routes/agent.js for agentToAgent messaging
├── src/protocols/
│   └── delegation.py      # EXISTS - DelegationProtocol with Neo4j
└── migrations/
    └── TODO: migration_runner.py for Neo4j schema setup
```

---

**Document Status:** Complete Architecture Design
**Last Updated:** 2026-02-06
**Maintainer:** Kurultai Rebuild Architecture Team
