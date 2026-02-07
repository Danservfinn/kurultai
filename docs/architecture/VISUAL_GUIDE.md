# Kurultai v0.2 Visual Architecture Guide

**Version**: v0.2 | **Date**: 2026-02-06 | **Platform**: Railway | **Domain**: `kublai.kurult.ai`

This guide provides comprehensive visual diagrams of the Kurultai v0.2 architecture for developers new to the project. All diagrams use box-drawing characters for clarity.

---

## Section 1: System Architecture & Service Topology

### 1.1 High-Level System Overview

The platform consists of 6 Railway services, a managed PostgreSQL instance, and an external Neo4j AuraDB graph database, integrated with the Signal messaging network and the Anthropic Claude API.

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                            EXTERNAL DEPENDENCIES                                    │
│                                                                                     │
│  ┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐             │
│  │   Neo4j AuraDB    │   │  Signal Network   │   │   Anthropic API   │             │
│  │  (neo4j+s://)     │   │  (E2EE Protocol)  │   │  (Claude Sonnet)  │             │
│  │  Port: 7687/TLS   │   │  Signal Protocol  │   │  api.anthropic.com│             │
│  └────────┬──────────┘   └────────┬──────────┘   └────────┬──────────┘             │
│           │                       │                        │                        │
└───────────┼───────────────────────┼────────────────────────┼────────────────────────┘
            │                       │                        │
┌───────────┼───────────────────────┼────────────────────────┼────────────────────────┐
│           │         RAILWAY PROJECT: kurultai (US East)    │                        │
│           │                       │                        │                        │
│  ┌────────┴──────────────────┐    │    ┌───────────────────┴───────────┐            │
│  │                           │    │    │                               │            │
│  │  ┌─── AUTH TIER ────────────────────────────────────────────┐      │            │
│  │  │                                                          │      │            │
│  │  │  ┌──────────────────┐  ┌──────────────────┐             │      │            │
│  │  │  │ authentik-server │  │ authentik-worker  │             │      │            │
│  │  │  │ :9000 (internal) │  │ (background jobs) │             │      │            │
│  │  │  │ SSO + Admin UI   │  │ Celery tasks      │             │      │            │
│  │  │  └────────┬─────────┘  └──────────┬────────┘             │      │            │
│  │  │           │     ┌─────────────────┘                      │      │            │
│  │  │           │     │                                        │      │            │
│  │  │  ┌────────┴─────┴────┐     ┌──────────────────┐         │      │            │
│  │  │  │   PostgreSQL      │     │  authentik-proxy  │◀─ DNS ─┼──────┼── Internet │
│  │  │  │   (Railway)       │     │  (Caddy) :8080    │         │      │            │
│  │  │  │   Sessions, Users │     │  kublai.kurult.ai │         │      │            │
│  │  │  └───────────────────┘     └────────┬─────────┘         │      │            │
│  │  │                                     │ forward_auth      │      │            │
│  │  └─────────────────────────────────────┼────────────────────┘      │            │
│  │                                        │                           │            │
│  │  ┌─── APP TIER ────────────────────────┼──────────────────────┐    │            │
│  │  │                                     │                      │    │            │
│  │  │  ┌──────────────────────────────────┴──────────┐           │    │            │
│  │  │  │         moltbot-railway-template             │           │    │            │
│  │  │  │         :8080 (internal)                     │           │    │            │
│  │  │  │  ┌─────────────┐  ┌──────────────────┐      │           │    │            │
│  │  │  │  │  Express.js  │  │  Python Bridge   │──────┼───────────┼────┘            │
│  │  │  │  │  (Node 20)   │  │  (Python 3.13)   │      │◀──────────┘                │
│  │  │  │  │  server.js   │  │  openclaw + tools │      │  Neo4j queries             │
│  │  │  │  └─────────────┘  └──────────────────┘      │                             │
│  │  │  │  supervisord manages both processes          │                             │
│  │  │  └──────────────────────────────────────────────┘                             │
│  │  │                                                                               │
│  │  └───────────────────────────────────────────────────────────────────┘            │
│  │                                                                                  │
│  │  ┌─── SIGNAL TIER ──────────────────────────────────┐                            │
│  │  │                                                   │                            │
│  │  │  ┌──────────────────┐    ┌──────────────────┐    │                            │
│  │  │  │  signal-proxy    │    │ signal-cli-daemon │    │                            │
│  │  │  │  (Caddy) :8080   │───▶│  :8080 (internal) │────┼──── Signal Network        │
│  │  │  │  X-API-Key auth  │    │  Native binary    │    │                            │
│  │  │  └──────────────────┘    └──────────────────┘    │                            │
│  │  │                                                   │                            │
│  │  └───────────────────────────────────────────────────┘                            │
│  │                                                                                  │
└──┴──────────────────────────────────────────────────────────────────────────────────┘
```

**Service Count Summary**:
- 6 Railway services: authentik-server, authentik-worker, authentik-proxy, moltbot-railway-template, signal-cli-daemon, signal-proxy
- 1 Railway-managed PostgreSQL instance
- 1 External Neo4j AuraDB (neo4j+s:// TLS)
- External APIs: Anthropic (Claude), Signal Network

### 1.2 Request Flow

This diagram shows how a browser request traverses the system from the internet to the moltbot application and back.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                              REQUEST FLOW                                        │
│                                                                                  │
│  ┌──────────┐                                                                    │
│  │ Browser  │                                                                    │
│  └────┬─────┘                                                                    │
│       │                                                                          │
│       │ 1. HTTPS GET kublai.kurult.ai/dashboard                                  │
│       ▼                                                                          │
│  ┌──────────────┐                                                                │
│  │   GoDaddy    │  CNAME kublai -> authentik-proxy.up.railway.app                │
│  │   DNS        │  TTL: 600s                                                     │
│  └────┬─────────┘                                                                │
│       │                                                                          │
│       │ 2. Resolved to Railway edge                                              │
│       ▼                                                                          │
│  ┌──────────────┐                                                                │
│  │ Railway Edge │  TLS termination (Let's Encrypt auto-provisioned)              │
│  │  (CDN/LB)   │                                                                │
│  └────┬─────────┘                                                                │
│       │                                                                          │
│       │ 3. Route to authentik-proxy container                                    │
│       ▼                                                                          │
│  ┌──────────────────────────────────────────────────────────────┐                │
│  │                  authentik-proxy (Caddy :8080)                │                │
│  │                                                              │                │
│  │   Step 4: Check bypass routes table (see below)              │                │
│  │           If bypass match ──▶ skip auth, proxy directly      │                │
│  │           If no match ──▶ continue to forward_auth           │                │
│  │                                                              │                │
│  │   Step 5: forward_auth ──▶ authentik-server:9000             │                │
│  │           ┌──────────────────────────────────────┐           │                │
│  │           │ Authentik checks session cookie       │           │                │
│  │           │                                       │           │                │
│  │           │ If valid session:                     │           │                │
│  │           │   Returns 200 + X-Authentik-* headers │           │                │
│  │           │                                       │           │                │
│  │           │ If no session:                        │           │                │
│  │           │   Returns 401 -> Caddy sends 302      │           │                │
│  │           │   Redirect to /if/flow/authentication/│           │                │
│  │           └──────────────────────────────────────┘           │                │
│  │                                                              │                │
│  │   Step 6: proxy_pass to moltbot:8080                         │                │
│  │           Headers forwarded:                                 │                │
│  │             X-Authentik-Username                              │                │
│  │             X-Authentik-Email                                 │                │
│  │             X-Authentik-Name                                  │                │
│  │             X-Authentik-Uid                                   │                │
│  │             X-Authentik-Groups                                │                │
│  └──────────────────────┬───────────────────────────────────────┘                │
│                         │                                                        │
│                         │ 7. Authenticated request                               │
│                         ▼                                                        │
│                  ┌──────────────┐                                                │
│                  │   Moltbot    │  Express.js receives request                    │
│                  │   :8080      │  Reads X-Authentik-* headers                    │
│                  └──────┬───────┘                                                │
│                         │                                                        │
│                         │ 8. Response flows back                                 │
│                         ▼                                                        │
│                  Browser receives response                                       │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Bypass Routes Table** (evaluated in Caddy order):

```
┌─────────────────────────────────┬──────────────────────────┬──────────────────────┐
│ Route Pattern                   │ Authentication           │ Reason               │
├─────────────────────────────────┼──────────────────────────┼──────────────────────┤
│ /setup/api/signal-link          │ X-Signal-Token header    │ QR code device link  │
│ /ws/*                           │ Session-based            │ WebSocket upgrade    │
│ /outpost.goauthentik.io/*       │ None (internal)          │ Authentik outpost    │
│ /application/*                  │ Session-based            │ Authentik app API    │
│ /flows/*                        │ None (public)            │ Auth flow pages      │
│ /health                         │ None (public)            │ Railway monitoring   │
│ /* (everything else)            │ Authentik forward_auth   │ Protected routes     │
└─────────────────────────────────┴──────────────────────────┴──────────────────────┘
```

WARNING: Route evaluation order matters. The `/health` bypass must be present or Railway health checks will trigger auth redirects and mark the service as unhealthy.

### 1.3 Service Communication Matrix

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                         SERVICE COMMUNICATION MATRIX                                     │
├───────────────────────┬──────────────────────┬──────────┬──────────┬──────────────────────┤
│ Source                │ Destination          │ Protocol │ Network  │ Auth Method          │
├───────────────────────┼──────────────────────┼──────────┼──────────┼──────────────────────┤
│ Internet (Browser)    │ authentik-proxy      │ HTTPS    │ Public   │ None (entry point)   │
│ authentik-proxy       │ authentik-server     │ HTTP     │ Internal │ forward_auth proto   │
│ authentik-proxy       │ moltbot              │ HTTP     │ Internal │ X-Authentik-* hdrs   │
│ authentik-server      │ PostgreSQL           │ TCP      │ Internal │ Password             │
│ authentik-worker      │ PostgreSQL           │ TCP      │ Internal │ Password             │
│ moltbot               │ Neo4j AuraDB         │ Bolt/TLS │ External │ Username + Password  │
│ moltbot               │ signal-proxy         │ HTTP     │ Internal │ X-API-Key header     │
│ moltbot               │ Anthropic API        │ HTTPS    │ External │ Bearer API key       │
│ signal-proxy          │ signal-cli-daemon    │ HTTP     │ Internal │ None (trusted net)   │
│ signal-cli-daemon     │ Signal Network       │ Signal   │ External │ Signal Protocol E2EE │
│ moltbot               │ Notion API           │ HTTPS    │ External │ Bearer NOTION_TOKEN  │
└───────────────────────┴──────────────────────┴──────────┴──────────┴──────────────────────┘
```

**Internal Railway URLs** (only reachable within Railway private network):

```
┌─────────────────────────────────────────────────────────────────────────┐
│  authentik-server.railway.internal:9000                                 │
│  authentik-proxy.railway.internal:8080                                  │
│  moltbot-railway-template.railway.internal:8080                         │
│  signal-cli-daemon.railway.internal:8080                                │
│  signal-proxy.railway.internal:8080                                     │
│  postgres.railway.internal:5432                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.4 Data Flow

How a user message flows through the agent pipeline, into Neo4j, and back.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         END-TO-END DATA FLOW                                     │
│                                                                                  │
│  ┌──────────┐     ┌──────────────┐     ┌──────────────────────────────────┐      │
│  │  User    │────▶│  Caddy Proxy │────▶│  Moltbot Express.js              │      │
│  │  Input   │     │  (auth check)│     │  server.js :8080                 │      │
│  └──────────┘     └──────────────┘     └───────────────┬──────────────────┘      │
│                                                        │                         │
│                                            ┌───────────▼───────────┐             │
│                                            │  Python Bridge        │             │
│                                            │  (openclaw CLI)       │             │
│                                            └───────────┬───────────┘             │
│                                                        │                         │
│               ┌────────────────────────────────────────▼────────────────┐        │
│               │                 KUBLAI (main)                           │        │
│               │                                                         │        │
│               │  1. Read personal context                               │        │
│               │     /data/workspace/souls/main/MEMORY.md                │        │
│               │                                                         │        │
│               │  2. Query operational context                           │        │
│               │     Neo4j: MATCH (r:Research), (c:CodePattern)...       │        │
│               │                                                         │        │
│               │  3. Sanitize PII via PIISanitizer                       │        │
│               │     "sarah@gmail.com" -> "[REDACTED_EMAIL]"             │        │
│               │                                                         │        │
│               │  4. Classify + delegate to specialist agent             │        │
│               │     HMAC-SHA256 signed message                          │        │
│               └──────────┬──────────────────────────────────────────────┘        │
│                          │                                                       │
│            ┌─────────────┼─────────────┬─────────────┬─────────────┐             │
│            ▼             ▼             ▼             ▼             ▼              │
│     ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│     │ Mongke   │  │ Chagatai │  │ Temujin  │  │  Jochi   │  │ Ogedei   │       │
│     │ research │  │  write   │  │   dev    │  │ analyze  │  │   ops    │       │
│     └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
│          │              │             │              │             │              │
│          └──────────────┴──────┬──────┴──────────────┴─────────────┘              │
│                                │                                                  │
│                   ┌────────────▼────────────┐                                     │
│                   │      Neo4j AuraDB       │                                     │
│                   │                         │                                     │
│                   │  :Research nodes        │                                     │
│                   │  :CodePattern nodes     │                                     │
│                   │  :Analysis nodes        │                                     │
│                   │  :LearnedCapability     │                                     │
│                   │  :Task nodes + DAG      │                                     │
│                   └────────────┬────────────┘                                     │
│                                │                                                  │
│               ┌────────────────▼────────────────┐                                │
│               │         KUBLAI (main)            │                                │
│               │  5. Synthesize results from      │                                │
│               │     specialist agents + Neo4j    │                                │
│               │  6. Format response for user     │                                │
│               └────────────────┬─────────────────┘                                │
│                                │                                                  │
│                    ┌───────────▼───────────┐                                      │
│                    │    User receives      │                                      │
│                    │    final response     │                                      │
│                    └───────────────────────┘                                      │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## Section 2: Security Architecture

### 2.1 Authentication Flow

Full Authentik SSO flow with WebAuthn challenge-response sequence for passwordless login.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                    AUTHENTIK SSO + WEBAUTHN AUTHENTICATION FLOW                       │
│                                                                                      │
│  ┌────────┐        ┌──────────────┐        ┌────────────────┐        ┌────────────┐ │
│  │ Client │        │ Caddy Proxy  │        │   Authentik    │        │  Moltbot   │ │
│  │Browser │        │ :8080 (pub)  │        │  Server :9000  │        │  :8080     │ │
│  └───┬────┘        └──────┬───────┘        └───────┬────────┘        └─────┬──────┘ │
│      │                    │                        │                       │         │
│      │  1. GET /dashboard │                        │                       │         │
│      │───────────────────▶│                        │                       │         │
│      │                    │                        │                       │         │
│      │                    │  2. forward_auth       │                       │         │
│      │                    │  GET /-/outpost.goau.. │                       │         │
│      │                    │───────────────────────▶│                       │         │
│      │                    │                        │                       │         │
│      │                    │  3. 401 Unauthorized   │                       │         │
│      │                    │◀───────────────────────│                       │         │
│      │                    │                        │                       │         │
│      │  4. 302 Redirect   │                        │                       │         │
│      │  Location: /if/flow/authentication/         │                       │         │
│      │◀───────────────────│                        │                       │         │
│      │                    │                        │                       │         │
│      │  5. GET /if/flow/authentication/            │                       │         │
│      │────────────────────────────────────────────▶│                       │         │
│      │                    │                        │                       │         │
│      │  6. Login page (WebAuthn prompt)            │                       │         │
│      │◀────────────────────────────────────────────│                       │         │
│      │                    │                        │                       │         │
│      │  ┌─────────────────────────────────────────────────────────┐       │         │
│      │  │              WEBAUTHN CHALLENGE-RESPONSE                │       │         │
│      │  │                                                         │       │         │
│      │  │  7a. Authentik sends challenge:                         │       │         │
│      │  │      { publicKey: { challenge, rpId, timeout: 60s,     │       │         │
│      │  │        userVerification: "preferred",                   │       │         │
│      │  │        residentKey: "preferred" } }                     │       │         │
│      │  │                                                         │       │         │
│      │  │  7b. Browser prompts security key / biometric           │       │         │
│      │  │      (Touch ID, YubiKey, Windows Hello)                 │       │         │
│      │  │                                                         │       │         │
│      │  │  7c. Client signs challenge with private key            │       │         │
│      │  │      Sends authenticatorData + signature                │       │         │
│      │  └─────────────────────────────────────────────────────────┘       │         │
│      │                    │                        │                       │         │
│      │  7d. POST signed assertion                  │                       │         │
│      │────────────────────────────────────────────▶│                       │         │
│      │                    │                        │                       │         │
│      │                    │                        │ Verify signature      │         │
│      │                    │                        │ against stored        │         │
│      │                    │                        │ public key in         │         │
│      │                    │                        │ PostgreSQL            │         │
│      │                    │                        │                       │         │
│      │  8. Set-Cookie: authentik_session=...       │                       │         │
│      │  302 Redirect to /dashboard                 │                       │         │
│      │◀────────────────────────────────────────────│                       │         │
│      │                    │                        │                       │         │
│      │  9. GET /dashboard │                        │                       │         │
│      │  Cookie: authentik_session=...              │                       │         │
│      │───────────────────▶│                        │                       │         │
│      │                    │                        │                       │         │
│      │                    │ 10. forward_auth       │                       │         │
│      │                    │───────────────────────▶│                       │         │
│      │                    │                        │                       │         │
│      │                    │ 11. 200 OK             │                       │         │
│      │                    │ X-Authentik-Username    │                       │         │
│      │                    │ X-Authentik-Email       │                       │         │
│      │                    │ X-Authentik-Uid         │                       │         │
│      │                    │ X-Authentik-Groups      │                       │         │
│      │                    │◀───────────────────────│                       │         │
│      │                    │                        │                       │         │
│      │                    │ 12. proxy_pass to moltbot                      │         │
│      │                    │ + X-Authentik-* headers │                       │         │
│      │                    │───────────────────────────────────────────────▶│         │
│      │                    │                        │                       │         │
│      │                    │ 13. Response from moltbot                      │         │
│      │                    │◀───────────────────────────────────────────────│         │
│      │                    │                        │                       │         │
│      │  14. Dashboard rendered                     │                       │         │
│      │◀───────────────────│                        │                       │         │
│      │                    │                        │                       │         │
└──────┴────────────────────┴────────────────────────┴───────────────────────┴─────────┘
```

### 2.2 Agent Trust & CBAC Model

6 agents with their trust levels, HMAC-SHA256 inter-agent signing, and Capability-Based Access Control.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                    AGENT TRUST HIERARCHY & CBAC MODEL                                 │
│                                                                                      │
│  TRUST LEVELS:                                                                       │
│  ┌──────────────────────────────────────────────────────────────────────────────┐     │
│  │  Level 4 ─ Administrative  (system config, key rotation)                    │     │
│  │  Level 3 ─ Elevated        (code execution, DB writes)                      │     │
│  │  Level 2 ─ Standard        (API calls, file operations)                     │     │
│  │  Level 1 ─ Basic           (read-only operations)                           │     │
│  │  Level 0 ─ None            (default for new agents)                         │     │
│  └──────────────────────────────────────────────────────────────────────────────┘     │
│                                                                                      │
│  AGENT TRUST ASSIGNMENTS:                                                            │
│                                                                                      │
│  ┌─────────────────────────────────────────────────┐                                 │
│  │            KUBLAI (main) ─ Level 4              │                                 │
│  │  Orchestrator, PII access, delegation, CBAC mgr │                                 │
│  │  Can: grant capabilities, rotate keys, config   │                                 │
│  └────────────────────┬────────────────────────────┘                                 │
│                       │ Delegates via HMAC-SHA256 signed messages                     │
│         ┌─────────────┼─────────────┬──────────────┬──────────────┐                  │
│         ▼             ▼             ▼              ▼              ▼                   │
│  ┌────────────┐┌────────────┐┌────────────┐┌────────────┐┌────────────┐              │
│  │  Mongke    ││  Chagatai  ││  Temujin   ││   Jochi    ││  Ogedei    │              │
│  │ researcher ││   writer   ││ developer  ││  analyst   ││    ops     │              │
│  │  Level 2   ││  Level 2   ││  Level 3   ││  Level 3   ││  Level 3   │              │
│  │            ││            ││            ││            ││            │              │
│  │ API calls  ││ Doc gen    ││ Code exec  ││ AST parse  ││ Infra mgmt │              │
│  │ Web search ││ Reports    ││ DB writes  ││ Security   ││ Monitoring │              │
│  │ Knowledge  ││ Comms      ││ Testing    ││ Audit      ││ File watch │              │
│  └────────────┘└────────────┘└────────────┘└────────────┘└────────────┘              │
│                                                                                      │
│  HMAC-SHA256 SIGNING PROTOCOL:                                                       │
│                                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────┐     │
│  │                                                                              │     │
│  │  ┌─────────┐        ┌──────────┐        ┌──────────┐        ┌─────────┐     │     │
│  │  │ Sender  │       │ Neo4j    │        │ Message  │        │Receiver │     │     │
│  │  │ Agent   │       │ AuraDB   │        │ Channel  │        │ Agent   │     │     │
│  │  └────┬────┘       └────┬─────┘        └────┬─────┘        └────┬────┘     │     │
│  │       │                 │                   │                   │           │     │
│  │       │ 1. Get active key                   │                   │           │     │
│  │       │ MATCH (a:Agent)-[:HAS_KEY]->(k:AgentKey {is_active:true})           │     │
│  │       │────────────────▶│                   │                   │           │     │
│  │       │                 │                   │                   │           │     │
│  │       │ 2. key_hash     │                   │                   │           │     │
│  │       │◀────────────────│                   │                   │           │     │
│  │       │                 │                   │                   │           │     │
│  │       │ 3. Compute signature:               │                   │           │     │
│  │       │    HMAC-SHA256(key_hash,            │                   │           │     │
│  │       │      message + timestamp + nonce)   │                   │           │     │
│  │       │                 │                   │                   │           │     │
│  │       │ 4. Send message + X-Agent-Signature │                   │           │     │
│  │       │────────────────────────────────────▶│                   │           │     │
│  │       │                 │                   │                   │           │     │
│  │       │                 │                   │ 5. Forward msg    │           │     │
│  │       │                 │                   │──────────────────▶│           │     │
│  │       │                 │                   │                   │           │     │
│  │       │                 │  6. Validate sig  │                   │           │     │
│  │       │                 │◀──────────────────────────────────────│           │     │
│  │       │                 │                   │                   │           │     │
│  │       │                 │  7. Check: timestamp drift < 300s    │           │     │
│  │       │                 │     Check: nonce not replayed        │           │     │
│  │       │                 │  8. Return valid/invalid             │           │     │
│  │       │                 │──────────────────────────────────────▶│           │     │
│  │       │                 │                   │                   │           │     │
│  │  └────┴────┘       └────┴─────┘        └────┴─────┘        └────┴────┘     │     │
│  │                                                                              │     │
│  │  Key Rotation: 90-day expiry, 7-day overlap, secrets.token_hex(32)          │     │
│  └──────────────────────────────────────────────────────────────────────────────┘     │
│                                                                                      │
│  CBAC (Capability-Based Access Control) in Neo4j:                                    │
│                                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────┐     │
│  │                                                                              │     │
│  │   (:Agent {id:"developer"})                                                  │     │
│  │        │                                                                     │     │
│  │        │──[:HAS_CAPABILITY {granted_at, expires_at, granted_by:"main"}]──▶   │     │
│  │        │                                                                     │     │
│  │   (:Capability {id:"execute_code"})                                          │     │
│  │                                                                              │     │
│  │   Authorization check:                                                       │     │
│  │   FOR EACH required_capability IN LearnedCapability.required_capabilities:   │     │
│  │     Agent must have HAS_CAPABILITY rel where expires_at IS NULL              │     │
│  │     OR expires_at > datetime()                                               │     │
│  │                                                                              │     │
│  └──────────────────────────────────────────────────────────────────────────────┘     │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Security Controls Pipeline

All 5 layered security controls in the capability acquisition pipeline.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                   5-LAYER SECURITY CONTROLS PIPELINE                                  │
│                                                                                      │
│  User sends: /learn <capability request>                                             │
│       │                                                                              │
│       ▼                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────────┐       │
│  │  LAYER 1: PromptInjectionFilter                                           │       │
│  │  File: tools/kurultai/security/prompt_injection_filter.py                 │       │
│  │  Phase: 0 (pre-check, before classification)                              │       │
│  │                                                                            │       │
│  │  Step 1: NFKC Unicode Normalization                                       │       │
│  │  ┌──────────────────────────────────────────────────────────────┐          │       │
│  │  │  Input: "ignore all previous instructions"                   │          │       │
│  │  │         (fullwidth Unicode homoglyphs)                       │          │       │
│  │  │                                                              │          │       │
│  │  │  unicodedata.normalize('NFKC', text)                        │          │       │
│  │  │                                                              │          │       │
│  │  │  Output: "ignore all previous instructions"                  │          │       │
│  │  │         (normalized ASCII equivalents)                       │          │       │
│  │  └──────────────────────────────────────────────────────────────┘          │       │
│  │                                                                            │       │
│  │  Step 2: Pattern Matching (7+ patterns, case-insensitive regex)           │       │
│  │  ┌──────────────────────────────────────────────────────────────┐          │       │
│  │  │  Pattern 1: ignore (all )?(previous|above) instructions      │          │       │
│  │  │  Pattern 2: disregard (all )?(previous|above) instructions   │          │       │
│  │  │  Pattern 3: (forget|clear|reset) (all )?(instructions|...)   │          │       │
│  │  │  Pattern 4: you are now (a|an) .{0,50} (model|assistant|ai)  │          │       │
│  │  │  Pattern 5: act as (a|an) .{0,100}                           │          │       │
│  │  │  Pattern 6: pretend (you are|to be) .{0,100}                 │          │       │
│  │  │  Pattern 7: override (your )?(programming|safety|constraints)│          │       │
│  │  └──────────────────────────────────────────────────────────────┘          │       │
│  │                                                                            │       │
│  │  Result: PASS ──▶ continue  |  FAIL ──▶ BLOCK (return error)              │       │
│  └───────────────────────────────────────────┬────────────────────────────────┘       │
│                                              │ PASS                                   │
│                                              ▼                                        │
│  ┌────────────────────────────────────────────────────────────────────────────┐       │
│  │  LAYER 2: CostEnforcer (Pre-Authorization)                                │       │
│  │  File: tools/kurultai/security/cost_enforcer.py                           │       │
│  │  Phase: Before Phase 2 (Research)                                         │       │
│  │                                                                            │       │
│  │  ┌─────────────────────────────────────────────────────────────────┐       │       │
│  │  │  1. authorize_spending(skill_id, estimated_cost)                │       │       │
│  │  │  2. Neo4j atomic check: remaining >= estimated_cost?            │       │       │
│  │  │     ┌─────────┐                                                 │       │       │
│  │  │     │ Budget  │  remaining -= estimated_cost                    │       │       │
│  │  │     │  Node   │  reserved  += estimated_cost                    │       │       │
│  │  │     └─────────┘                                                 │       │       │
│  │  │  3. On completion: reserved -= actual, spent += actual          │       │       │
│  │  │  4. Surplus returned: remaining += (estimated - actual)         │       │       │
│  │  │  5. On failure:  remaining += estimated, reserved -= estimated  │       │       │
│  │  └─────────────────────────────────────────────────────────────────┘       │       │
│  │                                                                            │       │
│  │  Result: PASS (budget OK) ──▶ continue  |  FAIL ──▶ BLOCK (over budget)   │       │
│  └───────────────────────────────────────────┬────────────────────────────────┘       │
│                                              │ PASS                                   │
│                                              ▼                                        │
│           ┌──────────────────────────────────────────────────┐                        │
│           │  Phases 1-3 Execute:                              │                        │
│           │   Phase 1: Classification (Kublai)               │                        │
│           │   Phase 2: Research (Mongke)                     │                        │
│           │   Phase 3: Implementation (Temujin)              │                        │
│           └──────────────────────┬───────────────────────────┘                        │
│                                  │                                                    │
│                                  ▼                                                    │
│  ┌────────────────────────────────────────────────────────────────────────────┐       │
│  │  LAYER 3: SandboxExecutor                                                  │       │
│  │  File: tools/kurultai/sandbox_executor.py                                 │       │
│  │  Phase: 4 (Validation)                                                    │       │
│  │                                                                            │       │
│  │  Subprocess-based sandbox (Railway-compatible, no Docker)                 │       │
│  │  ┌──────────────────────────────────────────────────────────┐             │       │
│  │  │  Resource Limits:                                        │             │       │
│  │  │  ┌──────────────────┬────────────┬────────────────────┐  │             │       │
│  │  │  │ Resource         │ Limit      │ Constant           │  │             │       │
│  │  │  ├──────────────────┼────────────┼────────────────────┤  │             │       │
│  │  │  │ CPU Time         │ 30 seconds │ RLIMIT_CPU         │  │             │       │
│  │  │  │ Address Space    │ 512 MB     │ RLIMIT_AS          │  │             │       │
│  │  │  │ File Descriptors │ 100        │ RLIMIT_NOFILE      │  │             │       │
│  │  │  └──────────────────┴────────────┴────────────────────┘  │             │       │
│  │  │                                                          │             │       │
│  │  │  NOTE: RLIMIT_AS enforced on Linux (Railway).            │             │       │
│  │  │  macOS (dev) ignores RLIMIT_AS -- use platform detect.   │             │       │
│  │  └──────────────────────────────────────────────────────────┘             │       │
│  └───────────────────────────────────────────┬────────────────────────────────┘       │
│                                              │                                        │
│                                              ▼                                        │
│  ┌────────────────────────────────────────────────────────────────────────────┐       │
│  │  LAYER 4: Jochi AST Analyzer (tree-sitter)                                │       │
│  │  File: tools/kurultai/static_analysis/ast_parser.py                       │       │
│  │  Phase: 4 (Validation) + ongoing monitoring                               │       │
│  │                                                                            │       │
│  │  ┌──────────────────────────────────────────────────────────┐             │       │
│  │  │  Detection Categories:                                   │             │       │
│  │  │  ┌─────────────────────┬──────────────────┬────────────┐ │             │       │
│  │  │  │ Category            │ Patterns         │ Severity   │ │             │       │
│  │  │  ├─────────────────────┼──────────────────┼────────────┤ │             │       │
│  │  │  │ Code Execution      │ eval, exec,      │ high       │ │             │       │
│  │  │  │                     │ compile          │            │ │             │       │
│  │  │  │ SQL Injection       │ string concat    │ high       │ │             │       │
│  │  │  │                     │ in SQL queries   │            │ │             │       │
│  │  │  │ Hardcoded Secrets   │ API key patterns │ critical   │ │             │       │
│  │  │  │ Command Injection   │ os.system,       │ critical   │ │             │       │
│  │  │  │                     │ shell=True       │            │ │             │       │
│  │  │  └─────────────────────┴──────────────────┴────────────┘ │             │       │
│  │  │                                                          │             │       │
│  │  │  Dependencies: tree-sitter, tree-sitter-python           │             │       │
│  │  │  Installed via: /opt/venv/bin/pip                        │             │       │
│  │  └──────────────────────────────────────────────────────────┘             │       │
│  │                                                                            │       │
│  │  Result: PASS ──▶ continue  |  FAIL ──▶ BLOCK (findings reported)         │       │
│  └───────────────────────────────────────────┬────────────────────────────────┘       │
│                                              │ PASS                                   │
│                                              ▼                                        │
│  ┌────────────────────────────────────────────────────────────────────────────┐       │
│  │  LAYER 5: CostEnforcer (Release)                                          │       │
│  │  File: tools/kurultai/security/cost_enforcer.py                           │       │
│  │  Phase: Post-pipeline                                                     │       │
│  │                                                                            │       │
│  │  Finalizes budget: reserved -= actual_cost, spent += actual_cost          │       │
│  │  Returns surplus: remaining += (estimated_cost - actual_cost)             │       │
│  └───────────────────────────────────────────┬────────────────────────────────┘       │
│                                              │                                        │
│                                              ▼                                        │
│                                   Capability Registered                               │
│                                   LearnedCapability node created                      │
│                                   CBAC grants assigned                                │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.4 Signal Integration Security

Encryption boundaries, authentication layers, and allowlist enforcement for Signal messaging.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                    SIGNAL INTEGRATION SECURITY                                        │
│                                                                                      │
│  ┌── ENCRYPTION BOUNDARY: Signal Protocol E2EE ──────────────────────────────────┐   │
│  │                                                                                │   │
│  │  ┌─────────────┐                                  ┌──────────────────┐         │   │
│  │  │ Authorized  │◀════════ E2EE Channel ══════════▶│ signal-cli-daemon│         │   │
│  │  │ User Phone  │   Signal Protocol encryption     │ :8080 (internal) │         │   │
│  │  │             │   (keys never leave devices)     │ Native binary    │         │   │
│  │  └─────────────┘                                  └────────┬─────────┘         │   │
│  │                                                            │                   │   │
│  └────────────────────────────────────────────────────────────┼───────────────────┘   │
│                                                               │                       │
│                                          Plaintext HTTP       │                       │
│                                          (Railway internal    │                       │
│                                           network only)       │                       │
│                                                               │                       │
│  ┌── AUTH BOUNDARY: X-API-Key ────────────────────────────────┼───────────────────┐   │
│  │                                                            │                   │   │
│  │  ┌──────────────────────────────────────────────┐          │                   │   │
│  │  │              signal-proxy (Caddy)             │          │                   │   │
│  │  │              :8080 (internal)                 │◀─────────┘                   │   │
│  │  │                                              │                              │   │
│  │  │  ┌────────────────────────────────────────┐  │                              │   │
│  │  │  │  Authentication Check:                  │  │                              │   │
│  │  │  │  @unauthorized {                        │  │                              │   │
│  │  │  │    not header X-API-Key {$SIGNAL_...}   │  │                              │   │
│  │  │  │  }                                      │  │                              │   │
│  │  │  │  handle @unauthorized -> 401            │  │                              │   │
│  │  │  └────────────────────────────────────────┘  │                              │   │
│  │  │                                              │                              │   │
│  │  │  API Translation:                            │                              │   │
│  │  │  ┌─────────────────────┬────────────────────┐│                              │   │
│  │  │  │ Moltbot Endpoint    │ signal-cli Endpoint││                              │   │
│  │  │  ├─────────────────────┼────────────────────┤│                              │   │
│  │  │  │ /api/v1/check       │ /v1/about          ││                              │   │
│  │  │  │ /api/v1/events?...  │ /v1/receive/+...   ││                              │   │
│  │  │  │ /api/v1/send        │ /v2/send           ││                              │   │
│  │  │  │ /api/v1/rpc         │ N/A (stub)         ││                              │   │
│  │  │  └─────────────────────┴────────────────────┘│                              │   │
│  │  └──────────────────────────────────────────────┘                              │   │
│  │                                                                                │   │
│  └────────────────────────────────────────────────────────────────────────────────┘   │
│                              ▲                                                        │
│                              │  X-API-Key header required                             │
│                              │                                                        │
│  ┌── ALLOWLIST ENFORCEMENT ──┼────────────────────────────────────────────────────┐   │
│  │                           │                                                    │   │
│  │  ┌───────────────────────────────────────────────────────────────────┐         │   │
│  │  │                  Moltbot (moltbot.json)                           │         │   │
│  │  │                                                                   │         │   │
│  │  │  channels.signal.allowFrom:                                       │         │   │
│  │  │    +15165643945  (self - bot's own number)                        │         │   │
│  │  │    +19194133445  (authorized user)                                │         │   │
│  │  │                                                                   │         │   │
│  │  │  channels.signal.groupAllowFrom:                                  │         │   │
│  │  │    +19194133445  (authorized user)                                │         │   │
│  │  │                                                                   │         │   │
│  │  │  Message from unlisted number ──▶ DROPPED (silent)               │         │   │
│  │  │  Message from listed number   ──▶ Processed by agent pipeline    │         │   │
│  │  └───────────────────────────────────────────────────────────────────┘         │   │
│  │                                                                                │   │
│  └────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
│  QR DEVICE LINKING (one-time setup):                                                 │
│  ┌────────────────────────────────────────────────────────────────────────────┐       │
│  │  POST /setup/api/signal-link                                               │       │
│  │  Header: X-Signal-Token: $SIGNAL_LINK_TOKEN                               │       │
│  │  Body: {"phoneNumber": "+15165643945"}                                     │       │
│  │                                                                            │       │
│  │  This route bypasses Authentik (in Caddy bypass table)                    │       │
│  │  but requires its own token authentication.                               │       │
│  └────────────────────────────────────────────────────────────────────────────┘       │
│                                                                                      │
│  v0.2 SECURITY CHANGES:                                                              │
│  ┌────────────────────────────────────────────────────────────────────────────┐       │
│  │  REMOVED: Public JSON-RPC endpoint (was unauthenticated)                  │       │
│  │  REMOVED: Direct curl to signal-cli-daemon (no auth)                      │       │
│  │  ADDED:   X-API-Key on all signal-proxy endpoints                         │       │
│  │  ADDED:   signal-cli-daemon internal-only (no public access)              │       │
│  │  ADDED:   Token-protected QR linking endpoint                             │       │
│  └────────────────────────────────────────────────────────────────────────────┘       │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Section 3: Agent Architecture & Neo4j Memory

### 3.1 Agent Hierarchy

Kublai acts as the orchestrator and sole user-facing agent. The 5 specialist agents receive delegated tasks and write results to shared Neo4j memory.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                         AGENT HIERARCHY                                               │
│                                                                                      │
│                        ┌──────────────────────────────┐                              │
│                        │        USER REQUEST           │                              │
│                        └──────────────┬───────────────┘                              │
│                                       │                                              │
│                                       ▼                                              │
│  ┌────────────────────────────────────────────────────────────────────────────┐       │
│  │                     KUBLAI (main) - ORCHESTRATOR                          │       │
│  │                                                                            │       │
│  │  Role: User interface, delegation, PII sanitization, CBAC management      │       │
│  │  Trust Level: 4 (Administrative)                                          │       │
│  │  Personal Memory: /data/workspace/souls/main/MEMORY.md                    │       │
│  │  Unique Access: PII data (names, emails, phone numbers)                   │       │
│  │                                                                            │       │
│  │  Functions:                                                                │       │
│  │    1. Read personal context (files) ── only Kublai has PII access         │       │
│  │    2. Query operational context (Neo4j) ── shared with all agents         │       │
│  │    3. Sanitize PII via PIISanitizer before delegation                     │       │
│  │    4. Classify intent and route to specialist                             │       │
│  │    5. Sign delegation with HMAC-SHA256                                    │       │
│  │    6. Synthesize specialist responses                                     │       │
│  │    7. Manage CBAC grants and key rotation                                 │       │
│  └────────────────────────────────┬───────────────────────────────────────────┘       │
│                                   │                                                   │
│                                   │ HMAC-SHA256 signed delegation                     │
│                                   │                                                   │
│       ┌───────────┬───────────────┼───────────────┬───────────────┐                   │
│       ▼           ▼               ▼               ▼               ▼                   │
│  ┌─────────┐ ┌─────────┐  ┌──────────┐   ┌──────────┐   ┌──────────┐               │
│  │ MONGKE  │ │CHAGATAI │  │ TEMUJIN  │   │  JOCHI   │   │ OGEDEI   │               │
│  │researcher│ │ writer  │  │developer │   │ analyst  │   │   ops    │               │
│  ├─────────┤ ├─────────┤  ├──────────┤   ├──────────┤   ├──────────┤               │
│  │Level: 2 │ │Level: 2 │  │Level: 3  │   │Level: 3  │   │Level: 3  │               │
│  ├─────────┤ ├─────────┤  ├──────────┤   ├──────────┤   ├──────────┤               │
│  │Web      │ │Docs     │  │Code gen  │   │AST parse │   │Infra     │               │
│  │search   │ │Reports  │  │Implement │   │Security  │   │Monitoring│               │
│  │API      │ │Comms    │  │Testing   │   │Audit     │   │File watch│               │
│  │research │ │         │  │DB writes │   │Backend   │   │Notion    │               │
│  │Knowledge│ │         │  │          │   │monitor   │   │sync      │               │
│  ├─────────┤ ├─────────┤  ├──────────┤   ├──────────┤   ├──────────┤               │
│  │Writes:  │ │Writes:  │  │Writes:   │   │Writes:   │   │Writes:   │               │
│  │:Research│ │:Content │  │:Code     │   │:Analysis │   │:FileConsi│               │
│  │nodes    │ │:Synthesis│  │Pattern   │   │:Security │   │stencyRpt │               │
│  │         │ │         │  │:Learned  │   │Audit     │   │:SyncEvent│               │
│  │         │ │         │  │Capability│   │          │   │          │               │
│  └─────────┘ └─────────┘  └──────────┘   └──────────┘   └──────────┘               │
│       │           │             │              │              │                       │
│       └───────────┴──────┬──────┴──────────────┴──────────────┘                       │
│                          │                                                            │
│                          ▼                                                            │
│               ┌──────────────────────┐                                                │
│               │    Neo4j AuraDB      │  Shared operational memory                     │
│               │    (all 6 agents)    │  Graph-based, vector-indexed                   │
│               └──────────────────────┘                                                │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Neo4j Graph Schema

All node types and relationships from migration v3, with indexes including vector indexes.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                        NEO4J GRAPH SCHEMA (v3 Migration)                              │
│                                                                                      │
│  CORE NODES (with key properties):                                                   │
│                                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────┐     │
│  │                                                                              │     │
│  │  ┌────────────────┐     [:HAS_KEY]     ┌────────────────────────┐           │     │
│  │  │   :Agent       │────────────────────▶│     :AgentKey          │           │     │
│  │  │  id (UNIQUE)   │                    │  id (UNIQUE)           │           │     │
│  │  │  name          │                    │  key_hash              │           │     │
│  │  └───────┬────────┘                    │  created_at            │           │     │
│  │          │                              │  expires_at (90 days) │           │     │
│  │          │                              │  is_active             │           │     │
│  │          │                              └────────────────────────┘           │     │
│  │          │                                                                   │     │
│  │          │ [:HAS_CAPABILITY {expires_at, granted_by, granted_at}]            │     │
│  │          │                                                                   │     │
│  │          ▼                                                                   │     │
│  │  ┌────────────────┐                                                          │     │
│  │  │  :Capability   │                                                          │     │
│  │  │  id (UNIQUE)   │                                                          │     │
│  │  │  name          │                                                          │     │
│  │  │  description   │                                                          │     │
│  │  └────────────────┘                                                          │     │
│  │                                                                              │     │
│  │  ┌────────────────┐  [:PERFORMED]  ┌────────────────────────────┐           │     │
│  │  │   :Agent       │───────────────▶│       :Research            │           │     │
│  │  └────────────────┘                │  id (UNIQUE)               │           │     │
│  │                                    │  content, source           │           │     │
│  │                                    │  timestamp, agent          │           │     │
│  │                                    │  research_type             │           │     │
│  │                                    │  capability_name           │           │     │
│  │                                    │  embedding (384-dim vector)│           │     │
│  │                                    └───────────┬────────────────┘           │     │
│  │                                                │                            │     │
│  │                                                │ [:CONTRIBUTED_TO]           │     │
│  │                                                ▼                            │     │
│  │  ┌────────────────┐  [:LEARNED]  ┌──────────────────────────────┐           │     │
│  │  │   :Agent       │─────────────▶│    :LearnedCapability        │           │     │
│  │  └────────────────┘              │  id (UNIQUE)                 │           │     │
│  │                                  │  name, agent, tool_path      │           │     │
│  │                                  │  version, learned_at, cost   │           │     │
│  │                                  │  mastery_score, risk_level   │           │     │
│  │                                  │  signature                   │           │     │
│  │                                  │  required_capabilities       │           │     │
│  │                                  │  min_trust_level             │           │     │
│  │                                  └──────────────────────────────┘           │     │
│  │                                                                              │     │
│  │  ┌──────────────────────────────┐  [:DEPENDS_ON]  ┌──────────────────┐      │     │
│  │  │          :Task               │────────────────▶│     :Task        │      │     │
│  │  │  id (UNIQUE)                 │   type           │                  │      │     │
│  │  │  description, status         │   weight         │  (dependency     │      │     │
│  │  │  priority_weight             │   detected_by    │   target)        │      │     │
│  │  │  assigned_to, sender_hash    │   confidence     │                  │      │     │
│  │  │  embedding (384-dim vector)  │   created_at     │                  │      │     │
│  │  │  window_expires_at           │                  │                  │      │     │
│  │  └──────────────────────────────┘                  └──────────────────┘      │     │
│  │                                                                              │     │
│  │  ┌──────────────────────────┐                                                │     │
│  │  │      :Analysis           │                                                │     │
│  │  │  id (UNIQUE)             │                                                │     │
│  │  │  file_path, agent        │                                                │     │
│  │  │  status, severity        │                                                │     │
│  │  │  assigned_to, findings   │                                                │     │
│  │  └──────────────────────────┘                                                │     │
│  │                                                                              │     │
│  └──────────────────────────────────────────────────────────────────────────────┘     │
│                                                                                      │
│  ADDITIONAL NODE TYPES (18 from v3 migration, all with UNIQUE(id)):                  │
│                                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────┐     │
│  │                                                                              │     │
│  │  ┌─────────────────┐ ┌─────────────────┐ ┌────────────────────┐             │     │
│  │  │ :SessionContext  │ │ :SignalSession  │ │ :AgentResponseRoute│             │     │
│  │  └─────────────────┘ └─────────────────┘ └────────────────────┘             │     │
│  │  ┌─────────────────┐ ┌─────────────────┐ ┌────────────────────┐             │     │
│  │  │ :Notification   │ │  :Reflection    │ │   :RateLimit       │             │     │
│  │  └─────────────────┘ └─────────────────┘ └────────────────────┘             │     │
│  │  ┌─────────────────┐ ┌────────────────────────┐ ┌────────────────┐          │     │
│  │  │ :BackgroundTask │ │ :FileConsistencyReport │ │ :FileConflict  │          │     │
│  │  └─────────────────┘ └────────────────────────┘ └────────────────┘          │     │
│  │  ┌──────────────────────┐ ┌─────────────┐ ┌──────────────┐                  │     │
│  │  │ :WorkflowImprovement │ │ :Synthesis  │ │  :Concept    │                  │     │
│  │  └──────────────────────┘ └─────────────┘ └──────────────┘                  │     │
│  │  ┌─────────────────┐ ┌──────────────┐ ┌────────────────────┐                │     │
│  │  │   :Content      │ │ :Application │ │    :Insight        │                │     │
│  │  └─────────────────┘ └──────────────┘ └────────────────────┘                │     │
│  │  ┌─────────────────┐ ┌──────────────┐ ┌────────────────────┐                │     │
│  │  │ :SecurityAudit  │ │ :CodeReview  │ │  :ProcessUpdate    │                │     │
│  │  └─────────────────┘ └──────────────┘ └────────────────────┘                │     │
│  │  ┌─────────────────┐ ┌──────────────┐                                       │     │
│  │  │   :SyncEvent    │ │ :SyncChange  │  (Notion audit trail)                 │     │
│  │  │ sender_hash     │ │ task_id      │                                       │     │
│  │  │ triggered_at    │ │              │                                       │     │
│  │  └─────────────────┘ └──────────────┘                                       │     │
│  │                                                                              │     │
│  └──────────────────────────────────────────────────────────────────────────────┘     │
│                                                                                      │
│  INDEXES (including 2 vector indexes, 384-dim cosine):                               │
│                                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────┐     │
│  │  Standard Indexes:                                                          │     │
│  │  ┌─────────────────────────────────────┬────────────────────────────────┐   │     │
│  │  │ Index Name                          │ Target                         │   │     │
│  │  ├─────────────────────────────────────┼────────────────────────────────┤   │     │
│  │  │ agent_id                            │ (Agent).id                     │   │     │
│  │  │ research_agent                      │ (Research).agent               │   │     │
│  │  │ capability_research_lookup          │ (Research).capability_name,    │   │     │
│  │  │                                     │            .agent              │   │     │
│  │  │ analysis_agent_status               │ (Analysis).agent,.status,      │   │     │
│  │  │                                     │           .severity            │   │     │
│  │  │ analysis_assigned_lookup            │ (Analysis).assigned_to,.status │   │     │
│  │  │ capability_grants                   │ [HAS_CAPABILITY].expires_at    │   │     │
│  │  │ task_claim_lock                     │ (Task).status,.assigned_to     │   │     │
│  │  │ task_window                         │ (Task).window_expires_at       │   │     │
│  │  │ task_sender_status                  │ (Task).sender_hash,.status     │   │     │
│  │  │ task_agent_status                   │ (Task).assigned_to,.status     │   │     │
│  │  │ depends_on_type                     │ [DEPENDS_ON].type              │   │     │
│  │  │ task_priority                       │ (Task).priority_weight,        │   │     │
│  │  │                                     │       .created_at              │   │     │
│  │  │ sync_event_sender                   │ (SyncEvent).sender_hash,       │   │     │
│  │  │                                     │            .triggered_at       │   │     │
│  │  │ sync_change_task                    │ (SyncChange).task_id           │   │     │
│  │  │ file_report_severity                │ (FileConsistencyReport)        │   │     │
│  │  │                                     │  .severity,.status             │   │     │
│  │  │ file_conflict_status                │ (FileConflict).status,         │   │     │
│  │  │                                     │              .severity         │   │     │
│  │  └─────────────────────────────────────┴────────────────────────────────┘   │     │
│  │                                                                              │     │
│  │  Vector Indexes (384-dimensional, cosine similarity):                       │     │
│  │  ┌─────────────────────────────────────┬────────────────────────────────┐   │     │
│  │  │ capability_research_embedding       │ (Research).embedding           │   │     │
│  │  │ task_embedding                      │ (Task).embedding               │   │     │
│  │  └─────────────────────────────────────┴────────────────────────────────┘   │     │
│  └──────────────────────────────────────────────────────────────────────────────┘     │
│                                                                                      │
│  MIGRATIONS: v1 (Agent, Research, CodePattern) -> v2 (Task, Deps) -> v3 (CBAC, all)  │
│  Run: python scripts/run_migrations.py --target-version 3                            │
│  Rollback: python scripts/run_migrations.py --target-version 2                       │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.3 Two-Tier Memory Architecture

Personal files (PII-containing, Kublai-only) vs Operational Neo4j (shared, PII-sanitized).

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                       TWO-TIER MEMORY ARCHITECTURE                                    │
│                                                                                      │
│  ┌─── PERSONAL TIER (Files) ─────────────────────────────────────────────────────┐   │
│  │  Storage: /data/workspace/souls/{agent_id}/MEMORY.md                          │   │
│  │  Access: KUBLAI ONLY (not shared with other agents)                           │   │
│  │  Contains: PII (names, emails, phone numbers, preferences)                    │   │
│  │                                                                                │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                             │   │
│  │  │ souls/main/ │ │souls/       │ │souls/       │  ...and 3 more              │   │
│  │  │ MEMORY.md   │ │researcher/  │ │writer/      │                              │   │
│  │  │             │ │MEMORY.md    │ │MEMORY.md    │                              │   │
│  │  │ User prefs  │ │ Research    │ │ Writing     │                              │   │
│  │  │ Friend names│ │ notes       │ │ style prefs │                              │   │
│  │  │ Birthdays   │ │             │ │             │                              │   │
│  │  └─────────────┘ └─────────────┘ └─────────────┘                             │   │
│  └────────────────────────────────────┬───────────────────────────────────────────┘   │
│                                       │                                               │
│                          ┌────────────▼────────────┐                                 │
│                          │  PII SANITIZATION        │                                 │
│                          │  BOUNDARY                │                                 │
│                          │                          │                                 │
│                          │  PIISanitizer applied:   │                                 │
│                          │  ┌──────────────────────┐│                                 │
│                          │  │ Email    -> REDACTED  ││                                 │
│                          │  │ Phone    -> REDACTED  ││                                 │
│                          │  │ SSN      -> REDACTED  ││                                 │
│                          │  │ Credit#  -> REDACTED  ││                                 │
│                          │  │ API Key  -> REDACTED  ││                                 │
│                          │  └──────────────────────┘│                                 │
│                          │                          │                                 │
│                          │  3 Layers:               │                                 │
│                          │  L1: Regex patterns      │                                 │
│                          │  L2: LLM-based review    │                                 │
│                          │  L3: Tokenization        │                                 │
│                          └────────────┬─────────────┘                                 │
│                                       │                                               │
│                                       ▼ Sanitized data only                           │
│  ┌─── OPERATIONAL TIER (Neo4j) ──────────────────────────────────────────────────┐   │
│  │  Storage: Neo4j AuraDB (neo4j+s:// TLS)                                      │   │
│  │  Access: ALL 6 AGENTS (shared operational memory)                             │   │
│  │  Contains: Research, code patterns, analysis, capabilities (NO PII)           │   │
│  │                                                                                │   │
│  │  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐     │   │
│  │  │  :Research    │ │ :CodePattern  │ │  :Analysis    │ │  :Learned     │     │   │
│  │  │  (Mongke)     │ │ (Temujin)     │ │  (Jochi)      │ │  Capability   │     │   │
│  │  │  findings,    │ │ patterns,     │ │  security     │ │  tools,       │     │   │
│  │  │  sources,     │ │ language,     │ │  findings,    │ │  versions,    │     │   │
│  │  │  embeddings   │ │ use_case      │ │  severity     │ │  mastery      │     │   │
│  │  └───────────────┘ └───────────────┘ └───────────────┘ └───────────────┘     │   │
│  │                                                                                │   │
│  │  ┌───────────────┐ ┌───────────────┐                                          │   │
│  │  │  :Task (DAG)  │ │ :SyncEvent   │                                          │   │
│  │  │  dependencies │ │ :SyncChange  │  (Notion audit)                           │   │
│  │  │  embeddings   │ │              │                                           │   │
│  │  └───────────────┘ └───────────────┘                                          │   │
│  └────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.4 Capability Acquisition Pipeline

The 6-phase horde-learn pipeline with security gates at each stage.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                   6-PHASE HORDE-LEARN CAPABILITY ACQUISITION                          │
│                                                                                      │
│  User: "/learn how to send SMS messages"                                             │
│       │                                                                              │
│       ▼                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐               │
│  │  SECURITY PRE-CHECK (Phase 0)                                      │               │
│  │  PromptInjectionFilter + NFKC normalization                       │               │
│  │  BLOCK if injection detected                                      │               │
│  └────────────────────────────────────────┬───────────────────────────┘               │
│                                           │ PASS                                      │
│                                           ▼                                           │
│  ┌────────────────────────────────────────────────────────────────────┐               │
│  │  PHASE 1: CLASSIFICATION (Kublai)                                  │               │
│  │  Classify capability type, risk level, estimate cost              │               │
│  │  Output: {type: "external_api", risk_level: "medium", cost: $2}   │               │
│  └────────────────────────────────────────┬───────────────────────────┘               │
│                                           │                                           │
│                                           ▼                                           │
│  ┌────────────────────────────────────────────────────────────────────┐               │
│  │  BUDGET GATE: CostEnforcer.authorize_spending()                   │               │
│  │  Atomic Neo4j check: remaining >= estimated_cost?                 │               │
│  │  Reserve funds: remaining -= cost, reserved += cost               │               │
│  │  BLOCK if insufficient budget                                     │               │
│  └────────────────────────────────────────┬───────────────────────────┘               │
│                                           │ PASS                                      │
│                                           ▼                                           │
│  ┌────────────────────────────────────────────────────────────────────┐               │
│  │  PHASE 2: RESEARCH (Mongke)                                        │               │
│  │  Find documentation, APIs, examples                               │               │
│  │  Output: Research nodes in Neo4j with embeddings                  │               │
│  │  (e.g., Twilio API docs, SMS best practices)                      │               │
│  └────────────────────────────────────────┬───────────────────────────┘               │
│                                           │                                           │
│                                           ▼                                           │
│  ┌────────────────────────────────────────────────────────────────────┐               │
│  │  PHASE 3: IMPLEMENTATION (Temujin)                                 │               │
│  │  Generate code module + tests                                     │               │
│  │  Output: tools/twilio_client.py with send_sms()                   │               │
│  └────────────────────────────────────────┬───────────────────────────┘               │
│                                           │                                           │
│                                           ▼                                           │
│  ┌────────────────────────────────────────────────────────────────────┐               │
│  │  PHASE 4: VALIDATION (Jochi)                                       │               │
│  │                                                                    │               │
│  │  ┌──────────────────────────────────────────────────────────┐     │               │
│  │  │  4a. SandboxExecutor: Run code in subprocess sandbox     │     │               │
│  │  │      CPU: 30s, Memory: 512MB, FDs: 100                  │     │               │
│  │  └──────────────────────────────┬───────────────────────────┘     │               │
│  │                                 │                                  │               │
│  │  ┌──────────────────────────────▼───────────────────────────┐     │               │
│  │  │  4b. AST Analyzer (tree-sitter): Static analysis         │     │               │
│  │  │      Check for eval/exec, SQL injection, hardcoded       │     │               │
│  │  │      secrets, command injection                          │     │               │
│  │  └──────────────────────────────┬───────────────────────────┘     │               │
│  │                                 │                                  │               │
│  │  Result: PASS (no findings) or FAIL (findings reported)           │               │
│  └────────────────────────────────────────┬───────────────────────────┘               │
│                                           │ PASS                                      │
│                                           ▼                                           │
│  ┌────────────────────────────────────────────────────────────────────┐               │
│  │  PHASE 5: REGISTRATION (Kublai)                                    │               │
│  │  Create LearnedCapability node in Neo4j                           │               │
│  │  Link: (Agent)-[:LEARNED]->(LearnedCapability)                    │               │
│  │  Link: (Research)-[:CONTRIBUTED_TO]->(LearnedCapability)          │               │
│  └────────────────────────────────────────┬───────────────────────────┘               │
│                                           │                                           │
│                                           ▼                                           │
│  ┌────────────────────────────────────────────────────────────────────┐               │
│  │  PHASE 6: AUTHORIZATION (Kublai)                                   │               │
│  │  Setup CBAC grants: (Agent)-[:HAS_CAPABILITY]->(Capability)       │               │
│  │  Assign trust level, expiry (90 days), granted_by: "main"         │               │
│  └────────────────────────────────────────┬───────────────────────────┘               │
│                                           │                                           │
│                                           ▼                                           │
│  ┌────────────────────────────────────────────────────────────────────┐               │
│  │  BUDGET RELEASE: CostEnforcer                                      │               │
│  │  reserved -= actual_cost, spent += actual_cost                    │               │
│  │  remaining += (estimated_cost - actual_cost)  [surplus returned]  │               │
│  └────────────────────────────────────────────────────────────────────┘               │
│                                                                                      │
│  Capability now available. User can invoke: "Send SMS to +1234567890"                │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.5 Task Dependency Engine

Intent window buffering, DAG building, topological execution, and priority overrides.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                       TASK DEPENDENCY ENGINE                                          │
│                                                                                      │
│  USER SENDS RAPID-FIRE MESSAGES:                                                     │
│  ┌─────────────────────────────────────────────────────────────────┐                 │
│  │  t=0s   "Research Neo4j best practices"                         │                 │
│  │  t=5s   "Write a database migration guide"                      │                 │
│  │  t=12s  "Implement the new schema"                              │                 │
│  │  t=20s  "Run security audit on the code"                        │                 │
│  └─────────────────────────────────────────────────────────────────┘                 │
│       │                                                                              │
│       ▼                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────────┐       │
│  │  INTENT WINDOW BUFFER                                                      │       │
│  │  File: tools/kurultai/intent_buffer.py                                    │       │
│  │                                                                            │       │
│  │  Collects messages within configurable window (default 45 seconds)        │       │
│  │  ┌─────────────────────────────────────────────────────────┐              │       │
│  │  │                                                         │              │       │
│  │  │  ┌────┐ ┌────┐ ┌────┐ ┌────┐        window_expires_at  │              │       │
│  │  │  │ M1 │ │ M2 │ │ M3 │ │ M4 │  ◀──── 45s from first    │              │       │
│  │  │  └────┘ └────┘ └────┘ └────┘         message            │              │       │
│  │  │  0s     5s     12s    20s                               │              │       │
│  │  │                                                         │              │       │
│  │  │  Window closes at t=45s (or configurable)               │              │       │
│  │  │  All buffered messages sent to DAG Builder               │              │       │
│  │  └─────────────────────────────────────────────────────────┘              │       │
│  └────────────────────────────────────────┬───────────────────────────────────┘       │
│                                           │                                           │
│                                           ▼                                           │
│  ┌────────────────────────────────────────────────────────────────────────────┐       │
│  │  DAG BUILDER                                                               │       │
│  │  File: tools/kurultai/dependency_analyzer.py                              │       │
│  │                                                                            │       │
│  │  1. Create :Task nodes in Neo4j for each message                          │       │
│  │  2. Generate 384-dim embeddings for semantic comparison                   │       │
│  │  3. Detect dependencies via:                                              │       │
│  │     - Semantic similarity (vector cosine distance)                        │       │
│  │     - Explicit keywords ("before", "after", "depends on")                 │       │
│  │     - Inferred from task types (research before implementation)           │       │
│  │  4. Create [:DEPENDS_ON] relationships with type, weight, confidence      │       │
│  │  5. Cycle detection: atomic Cypher query with path existence check        │       │
│  │                                                                            │       │
│  │  Resulting DAG:                                                            │       │
│  │  ┌──────────────────────────────────────────────────────────────────┐     │       │
│  │  │                                                                  │     │       │
│  │  │   ┌──────────┐                                                   │     │       │
│  │  │   │ Task 1   │  "Research Neo4j best practices"                  │     │       │
│  │  │   │ research │  Agent: Mongke (researcher)                       │     │       │
│  │  │   └────┬─────┘                                                   │     │       │
│  │  │        │ DEPENDS_ON                                              │     │       │
│  │  │        │ (type:"feeds_into", weight:0.85)                        │     │       │
│  │  │        ▼                                                         │     │       │
│  │  │   ┌──────────┐         ┌──────────┐                              │     │       │
│  │  │   │ Task 2   │         │ Task 3   │                              │     │       │
│  │  │   │ content  │◀────────│  code    │  DEPENDS_ON Task 1           │     │       │
│  │  │   │ Chagatai │         │ Temujin  │  (type:"blocks", w:0.9)      │     │       │
│  │  │   └──────────┘         └────┬─────┘                              │     │       │
│  │  │                             │ DEPENDS_ON                         │     │       │
│  │  │                             │ (type:"feeds_into", weight:0.92)   │     │       │
│  │  │                             ▼                                    │     │       │
│  │  │                        ┌──────────┐                              │     │       │
│  │  │                        │ Task 4   │                              │     │       │
│  │  │                        │ analysis │  "Run security audit"        │     │       │
│  │  │                        │  Jochi   │                              │     │       │
│  │  │                        └──────────┘                              │     │       │
│  │  │                                                                  │     │       │
│  │  └──────────────────────────────────────────────────────────────────┘     │       │
│  └────────────────────────────────────────┬───────────────────────────────────┘       │
│                                           │                                           │
│                                           ▼                                           │
│  ┌────────────────────────────────────────────────────────────────────────────┐       │
│  │  TOPOLOGICAL EXECUTOR                                                      │       │
│  │  File: tools/kurultai/topological_executor.py                             │       │
│  │                                                                            │       │
│  │  Dispatches independent batches in parallel:                              │       │
│  │                                                                            │       │
│  │  Batch 1 (parallel):  Task 1 (research) ──▶ Mongke                        │       │
│  │       │                                                                    │       │
│  │       │  Task 1 completes                                                  │       │
│  │       ▼                                                                    │       │
│  │  Batch 2 (parallel):  Task 2 (content) ──▶ Chagatai                       │       │
│  │                       Task 3 (code)    ──▶ Temujin                        │       │
│  │       │                                                                    │       │
│  │       │  Tasks 2,3 complete                                                │       │
│  │       ▼                                                                    │       │
│  │  Batch 3:             Task 4 (audit)   ──▶ Jochi                          │       │
│  │                                                                            │       │
│  │  Task Status Flow:                                                        │       │
│  │  PENDING ──▶ READY ──▶ RUNNING ──▶ COMPLETED                              │       │
│  │                              └──▶ FAILED ──▶ ESCALATED                    │       │
│  └────────────────────────────────────────────────────────────────────────────┘       │
│                                                                                      │
│  PRIORITY OVERRIDE COMMANDS (real-time user control):                                │
│  ┌────────────────────────────────────────────────────────────────────────────┐       │
│  │  "Priority: research first"    ──▶ Sets priority_weight = 1.0             │       │
│  │  "Do research before code"     ──▶ Creates explicit BLOCKS edge           │       │
│  │  "These are independent"       ──▶ Creates PARALLEL_OK edges              │       │
│  │  "Focus on research, pause"    ──▶ Pauses others, boosts research         │       │
│  │  "What's the plan?"            ──▶ Explains current DAG state             │       │
│  └────────────────────────────────────────────────────────────────────────────┘       │
│                                                                                      │
│  AGENT ROUTING MAP:                                                                  │
│  ┌──────────────────┬──────────────┬──────────────┐                                  │
│  │ Deliverable Type │ Agent ID     │ Agent Name   │                                  │
│  ├──────────────────┼──────────────┼──────────────┤                                  │
│  │ research         │ researcher   │ Mongke       │                                  │
│  │ analysis         │ analyst      │ Jochi        │                                  │
│  │ code             │ developer    │ Temujin      │                                  │
│  │ content          │ writer       │ Chagatai     │                                  │
│  │ ops              │ ops          │ Ogedei       │                                  │
│  │ strategy         │ analyst      │ Jochi        │                                  │
│  │ testing          │ developer    │ Temujin      │                                  │
│  └──────────────────┴──────────────┴──────────────┘                                  │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.6 Notion Integration

Bidirectional sync flow with polling engine and reconciliation safety rules.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                       NOTION INTEGRATION                                              │
│                                                                                      │
│  ┌─── NOTION SIDE ──────────────────────────────────────────────────────────────┐    │
│  │                                                                               │    │
│  │  ┌──────────────────────────────────────────────────────────┐                │    │
│  │  │  Notion Database (Task Board)                             │                │    │
│  │  │                                                           │                │    │
│  │  │  ┌──────┬──────────┬──────────┬────────┬──────────────┐  │                │    │
│  │  │  │ Name │ Status   │ Priority │ Agent  │ Last Synced  │  │                │    │
│  │  │  ├──────┼──────────┼──────────┼────────┼──────────────┤  │                │    │
│  │  │  │ T-1  │ Ready    │ High     │ Mongke │ 2m ago       │  │                │    │
│  │  │  │ T-2  │ Running  │ Medium   │ Temujin│ 1m ago       │  │                │    │
│  │  │  │ T-3  │ Pending  │ Low      │  --    │ 5m ago       │  │                │    │
│  │  │  └──────┴──────────┴──────────┴────────┴──────────────┘  │                │    │
│  │  └──────────────────────────────┬───────────────────────────┘                │    │
│  │                                 │                                             │    │
│  └─────────────────────────────────┼─────────────────────────────────────────────┘    │
│                                    │ HTTPS (Bearer NOTION_TOKEN)                      │
│                                    │                                                  │
│  ┌─── SYNC MODES ─────────────────┼─────────────────────────────────────────────┐    │
│  │                                 │                                             │    │
│  │  MODE 1: Command-Based         │                                             │    │
│  │  User: "Sync from Notion" ─────┼──▶ Notion ──▶ Neo4j                         │    │
│  │                                 │                                             │    │
│  │  MODE 2: Continuous Polling     │                                             │    │
│  │  Ogedei polls every 60s ───────┼──▶ Notion ──▶ Neo4j                         │    │
│  │  (via last_edited_time filter)  │                                             │    │
│  │                                 │                                             │    │
│  │  MODE 3: Bidirectional          │                                             │    │
│  │  Neo4j task completion ─────────┼──▶ Neo4j ──▶ Notion                         │    │
│  │                                 │                                             │    │
│  └─────────────────────────────────┼─────────────────────────────────────────────┘    │
│                                    │                                                  │
│                                    ▼                                                  │
│  ┌─── SYNC PIPELINE ──────────────────────────────────────────────────────────┐       │
│  │                                                                            │       │
│  │  ┌────────────────────────┐                                                │       │
│  │  │  NotionTaskClient      │  API client with retry + exponential backoff  │       │
│  │  │  tools/notion_sync.py  │                                                │       │
│  │  └───────────┬────────────┘                                                │       │
│  │              │                                                             │       │
│  │              ▼                                                             │       │
│  │  ┌────────────────────────────────┐                                        │       │
│  │  │  NotionPollingEngine           │  Ogedei continuous poll loop           │       │
│  │  │  tools/kurultai/notion_polling │  Filters by last_edited_time           │       │
│  │  │  Interval: NOTION_POLL_INTERVAL│  (default 60s)                         │       │
│  │  └───────────┬────────────────────┘                                        │       │
│  │              │                                                             │       │
│  │              ▼                                                             │       │
│  │  ┌────────────────────────────────────────────────────────────────┐        │       │
│  │  │  ReconciliationEngine                                          │        │       │
│  │  │  tools/kurultai/reconciliation.py                              │        │       │
│  │  │                                                                │        │       │
│  │  │  SAFETY RULES:                                                 │        │       │
│  │  │  ┌─────────┬──────────────────────┬──────────────────────────┐│        │       │
│  │  │  │ Rule    │ Condition            │ Action                   ││        │       │
│  │  │  ├─────────┼──────────────────────┼──────────────────────────┤│        │       │
│  │  │  │ Rule 1  │ Task is in_progress  │ Skip all except priority ││        │       │
│  │  │  │ Rule 2  │ Task is completed    │ Skip all Notion changes  ││        │       │
│  │  │  │ Rule 3  │ BLOCKS dep unmet     │ Don't enable dependent   ││        │       │
│  │  │  │ Rule 4  │ Priority change      │ Always apply (safe)      ││        │       │
│  │  │  └─────────┴──────────────────────┴──────────────────────────┘│        │       │
│  │  └───────────┬────────────────────────────────────────────────────┘        │       │
│  │              │                                                             │       │
│  │              ▼                                                             │       │
│  │  ┌────────────────────────────────────────────────────────────────┐        │       │
│  │  │  NotionSyncHandler                                             │        │       │
│  │  │  tools/kurultai/notion_sync_handler.py                         │        │       │
│  │  │  Extends PriorityCommandHandler                                │        │       │
│  │  │  Applies changes to Neo4j :Task nodes                          │        │       │
│  │  └───────────┬────────────────────────────────────────────────────┘        │       │
│  │              │                                                             │       │
│  │              ▼                                                             │       │
│  │  ┌────────────────────────────────────────────────────────────────┐        │       │
│  │  │  AUDIT TRAIL (Neo4j)                                           │        │       │
│  │  │  :SyncEvent {id, sender_hash, triggered_at}                    │        │       │
│  │  │  :SyncChange {id, task_id}                                     │        │       │
│  │  │  Every sync operation creates audit nodes                      │        │       │
│  │  └────────────────────────────────────────────────────────────────┘        │       │
│  └────────────────────────────────────────────────────────────────────────────┘       │
│                                                                                      │
│  FIELD MAPPING:                                                                      │
│  ┌──────────────────┬──────────┬─────────────────────┬──────────────────┐            │
│  │ Notion Property  │ Type     │ Neo4j Task Property │ Direction        │            │
│  ├──────────────────┼──────────┼─────────────────────┼──────────────────┤            │
│  │ Name             │ Title    │ description         │ Bidirectional    │            │
│  │ Status           │ Select   │ status              │ Bidirectional    │            │
│  │ Priority         │ Select   │ priority_weight     │ Notion -> Neo4j  │            │
│  │ Agent            │ Select   │ assigned_to         │ Notion -> Neo4j  │            │
│  │ ID               │ Text     │ id                  │ Read-only        │            │
│  │ Last Synced      │ Date     │ notion_synced_at    │ Neo4j -> Notion  │            │
│  └──────────────────┴──────────┴─────────────────────┴──────────────────┘            │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.7 File Consistency Monitoring

Ogedei-driven hash-based workspace file monitoring with conflict detection and resolution.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                    FILE CONSISTENCY MONITORING (Phase 6.5)                             │
│                                                                                      │
│  ┌─── MONITORED AGENT DIRECTORIES (Railway container paths) ────────────────────┐    │
│  │                                                                               │    │
│  │  /data/.clawdbot/agents/                                                      │    │
│  │  ├── main/       ── heartbeat.md, memory.md, CLAUDE.md                        │    │
│  │  ├── researcher/ ── heartbeat.md, memory.md, CLAUDE.md                        │    │
│  │  ├── writer/     ── heartbeat.md, memory.md, CLAUDE.md                        │    │
│  │  ├── developer/  ── heartbeat.md, memory.md, CLAUDE.md                        │    │
│  │  ├── analyst/    ── heartbeat.md, memory.md, CLAUDE.md                        │    │
│  │  └── ops/        ── heartbeat.md, memory.md, CLAUDE.md                        │    │
│  │                                                                               │    │
│  │  6 agents x 3 files = 18 files monitored                                     │    │
│  └───────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  ┌─── MONITORING PIPELINE ──────────────────────────────────────────────────────┐    │
│  │                                                                               │    │
│  │  ┌────────────────────────────────────────────────────────────┐               │    │
│  │  │  OgedeiFileMonitor                                         │               │    │
│  │  │  tools/kurultai/ogedei_file_monitor.py                     │               │    │
│  │  │  Runs every 5 minutes (configurable)                       │               │    │
│  │  └──────────────────────┬─────────────────────────────────────┘               │    │
│  │                         │                                                     │    │
│  │                         ▼                                                     │    │
│  │  ┌────────────────────────────────────────────────────────────┐               │    │
│  │  │  FileConsistencyChecker                                    │               │    │
│  │  │  tools/kurultai/file_consistency.py                        │               │    │
│  │  │                                                            │               │    │
│  │  │  1. Compute SHA-256 hash of each monitored file            │               │    │
│  │  │  2. Compare with previous scan's hashes                    │               │    │
│  │  │  3. Cross-file comparison for contradictions               │               │    │
│  │  │  4. Detect: stale data, parse errors, contradictions       │               │    │
│  │  └──────────────────────┬─────────────────────────────────────┘               │    │
│  │                         │                                                     │    │
│  │                         ▼                                                     │    │
│  │  ┌────────────────────────────────────────────────────────────────────────┐   │    │
│  │  │  CONFLICT DETECTION & RESOLUTION                                       │   │    │
│  │  │                                                                        │   │    │
│  │  │  ┌────────────────┬─────────────────────────────────────────────┐      │   │    │
│  │  │  │ Conflict Type  │ Resolution                                  │      │   │    │
│  │  │  ├────────────────┼─────────────────────────────────────────────┤      │   │    │
│  │  │  │ Stale data     │ AUTO: Flag older file for refresh           │      │   │    │
│  │  │  │ Parse errors   │ MANUAL: Queued for manual review            │      │   │    │
│  │  │  │ Contradictions │ MANUAL: Escalated to Kublai via Analysis    │      │   │    │
│  │  │  └────────────────┴─────────────────────────────────────────────┘      │   │    │
│  │  │                                                                        │   │    │
│  │  │  Manual resolution flow:                                               │   │    │
│  │  │  Conflict detected ──▶ :FileConflict {status:'open'} created           │   │    │
│  │  │                   ──▶ :FileConsistencyReport created                    │   │    │
│  │  │                   ──▶ Escalated to Kublai via :Analysis node            │   │    │
│  │  │                                                                        │   │    │
│  │  └────────────────────────────────────────────────────────────────────────┘   │    │
│  │                                                                               │    │
│  └───────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  HEALTH ENDPOINT:                                                                    │
│  GET /health/file-consistency                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐                │
│  │  Returns:                                                        │                │
│  │  {                                                               │                │
│  │    "status": "healthy" | "degraded",                             │                │
│  │    "file_consistency": {                                         │                │
│  │      "monitor_running": true/false,                              │                │
│  │      "last_severity": "low" | "medium" | "high" | "critical",   │                │
│  │      "last_scan": "ISO-8601 timestamp"                           │                │
│  │    }                                                             │                │
│  │  }                                                               │                │
│  │                                                                  │                │
│  │  Degraded if: monitor_running=false OR last_severity >= high     │                │
│  └──────────────────────────────────────────────────────────────────┘                │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.8 Neo4j Fallback Mode

Circuit breaker pattern with in-memory fallback store and automatic recovery.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                       NEO4J FALLBACK MODE                                             │
│                                                                                      │
│  Module: openclaw_memory.py (OperationalMemory class)                                │
│                                                                                      │
│  ┌─── CIRCUIT BREAKER STATE MACHINE ─────────────────────────────────────────┐       │
│  │                                                                            │       │
│  │                          Normal operations                                 │       │
│  │                     ┌────────────────────────┐                             │       │
│  │                     │                        │                             │       │
│  │                     ▼                        │                             │       │
│  │              ┌──────────────┐                │                             │       │
│  │              │              │         success on every                     │       │
│  │              │    CLOSED    │◀──────── request                            │       │
│  │              │   (normal)   │                │                             │       │
│  │              │              │                │                             │       │
│  │              └──────┬───────┘                │                             │       │
│  │                     │                        │                             │       │
│  │          5 consecutive                       │                             │       │
│  │           failures                           │                             │       │
│  │                     │                        │                             │       │
│  │                     ▼                        │                             │       │
│  │              ┌──────────────┐                │                             │       │
│  │              │              │                │                             │       │
│  │              │     OPEN     │         ┌──────┴───────┐                     │       │
│  │              │  (rejecting) │────────▶│  HALF_OPEN   │                     │       │
│  │              │              │  60s    │  (test 1 req)│                     │       │
│  │              └──────────────┘ timeout └──────┬───────┘                     │       │
│  │                     ▲                        │                             │       │
│  │                     │                  failure on                          │       │
│  │                     │                  test request                        │       │
│  │                     │                        │                             │       │
│  │                     └────────────────────────┘                             │       │
│  │                                                                            │       │
│  │  Config:                                                                   │       │
│  │  ┌──────────────────────┬─────────┬──────────────────────────────────┐     │       │
│  │  │ Parameter            │ Value   │ Description                      │     │       │
│  │  ├──────────────────────┼─────────┼──────────────────────────────────┤     │       │
│  │  │ failure_threshold    │ 5       │ Failures before circuit opens    │     │       │
│  │  │ recovery_timeout     │ 60s     │ Wait before half-open test      │     │       │
│  │  │ half_open_max_reqs   │ 1       │ Test requests in half-open      │     │       │
│  │  └──────────────────────┴─────────┴──────────────────────────────────┘     │       │
│  └────────────────────────────────────────────────────────────────────────────┘       │
│                                                                                      │
│  ┌─── FALLBACK BEHAVIOR (when circuit is OPEN) ──────────────────────────────┐       │
│  │                                                                            │       │
│  │  In-memory dict: _local_store                                             │       │
│  │                                                                            │       │
│  │  ┌──────────────────────┬────────────────────────────────────────────┐     │       │
│  │  │ Operation            │ Fallback Behavior                          │     │       │
│  │  ├──────────────────────┼────────────────────────────────────────────┤     │       │
│  │  │ create_task()        │ Stored in _local_store['tasks']            │     │       │
│  │  │ claim_task()         │ Simulated from local store                 │     │       │
│  │  │ complete_task()      │ Marked complete in local store             │     │       │
│  │  │ store_research()     │ Stored in _local_store['research']         │     │       │
│  │  │ check_rate_limit()   │ Always allows (disabled)                   │     │       │
│  │  │ health_check()       │ Returns status: 'fallback_mode'           │     │       │
│  │  │ _store_report()      │ Skipped (logs warning)                     │     │       │
│  │  └──────────────────────┴────────────────────────────────────────────┘     │       │
│  │                                                                            │       │
│  │  Memory Limits (prevent OOM):                                             │       │
│  │  ┌─────────────────────┬─────────────┐                                    │       │
│  │  │ Category            │ Max Items   │                                    │       │
│  │  ├─────────────────────┼─────────────┤                                    │       │
│  │  │ Tasks               │ 1,000       │                                    │       │
│  │  │ Research            │ 500         │                                    │       │
│  │  │ Other categories    │ 1,000 each  │                                    │       │
│  │  └─────────────────────┴─────────────┘                                    │       │
│  └────────────────────────────────────────────────────────────────────────────┘       │
│                                                                                      │
│  ┌─── AUTOMATIC RECOVERY ────────────────────────────────────────────────────┐       │
│  │                                                                            │       │
│  │  Background daemon thread: _start_recovery_monitor                        │       │
│  │  Checks Neo4j every 30 seconds                                            │       │
│  │                                                                            │       │
│  │  ┌──────────────────────────────────────────────────────────────────┐     │       │
│  │  │                                                                  │     │       │
│  │  │  1. driver.verify_connectivity()                                 │     │       │
│  │  │     │                                                            │     │       │
│  │  │     ├──▶ FAIL: Stay in fallback, retry in 30s                    │     │       │
│  │  │     │                                                            │     │       │
│  │  │     └──▶ SUCCESS:                                                │     │       │
│  │  │          │                                                       │     │       │
│  │  │          ▼                                                       │     │       │
│  │  │     2. _sync_fallback_to_neo4j()                                 │     │       │
│  │  │        Sync each item individually                               │     │       │
│  │  │        Track per-item failures                                   │     │       │
│  │  │          │                                                       │     │       │
│  │  │          ├──▶ Failure rate < 10%:                                 │     │       │
│  │  │          │    EXIT fallback mode                                  │     │       │
│  │  │          │    Resume normal Neo4j operations                      │     │       │
│  │  │          │    Circuit breaker -> CLOSED                           │     │       │
│  │  │          │                                                       │     │       │
│  │  │          └──▶ Failure rate >= 10%:                                │     │       │
│  │  │               REMAIN in fallback mode                             │     │       │
│  │  │               Retry next cycle (30s)                              │     │       │
│  │  │                                                                  │     │       │
│  │  └──────────────────────────────────────────────────────────────────┘     │       │
│  └────────────────────────────────────────────────────────────────────────────┘       │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Section 4: Deployment & Operations

### 4.1 Railway Deployment Topology

All 6 services with build methods, health checks, and connectivity.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│               RAILWAY DEPLOYMENT TOPOLOGY                                             │
│               Project: kurultai | Region: US East | Env: production                  │
│                                                                                      │
│  ┌─── SERVICE 1: authentik-server ──────────────────────────────────────────────┐    │
│  │  Image: ghcr.io/goauthentik/server:2025.10.0                                │    │
│  │  Build: Dockerfile (ENTRYPOINT [] + CMD ["dumb-init","--","ak","server"])    │    │
│  │  Port: 9000 (internal only)                                                  │    │
│  │  Health: GET /-/health/ready/                                                │    │
│  │  Depends: PostgreSQL (Railway internal)                                      │    │
│  │  Internal URL: authentik-server.railway.internal:9000                        │    │
│  │  Public Domain: None                                                         │    │
│  └──────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  ┌─── SERVICE 2: authentik-worker ──────────────────────────────────────────────┐    │
│  │  Image: ghcr.io/goauthentik/server:2025.10.0                                │    │
│  │  Build: Dockerfile (ENTRYPOINT [] + CMD ["dumb-init","--","ak","worker"])    │    │
│  │  Port: None (background jobs only)                                           │    │
│  │  Health: None                                                                │    │
│  │  Depends: PostgreSQL, authentik-server                                       │    │
│  │  Internal URL: N/A                                                           │    │
│  └──────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  ┌─── SERVICE 3: authentik-proxy ───────────────────────────────────────────────┐    │
│  │  Image: caddy:2-alpine                                                       │    │
│  │  Build: Dockerfile (COPY Caddyfile + CMD caddy run)                          │    │
│  │  Port: 8080 (public)                                                         │    │
│  │  Health: GET /health                                                         │    │
│  │  Custom Domain: kublai.kurult.ai (CNAME -> authentik-proxy.up.railway.app)  │    │
│  │  Internal URL: authentik-proxy.railway.internal:8080                         │    │
│  │  SSL: Auto (Let's Encrypt via Railway)                                       │    │
│  └──────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  ┌─── SERVICE 4: moltbot-railway-template ──────────────────────────────────────┐    │
│  │  Image: node:20-alpine + Python 3.13 (multi-runtime)                         │    │
│  │  Build: Dockerfile (supervisord manages Node + Python)                       │    │
│  │  Port: 8080 (internal, accessed via proxy)                                   │    │
│  │  Health: GET /health (HEALTHCHECK in Dockerfile, 30s interval)              │    │
│  │  Volume: /data (persistent)                                                  │    │
│  │  Depends: Neo4j AuraDB, Signal services                                      │    │
│  │  Internal URL: moltbot-railway-template.railway.internal:8080               │    │
│  │  Public Domain: Via authentik-proxy (forward auth)                            │    │
│  └──────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  ┌─── SERVICE 5: signal-cli-daemon ─────────────────────────────────────────────┐    │
│  │  Image: registry.gitlab.com/packaging/signal-cli/signal-cli-native:latest    │    │
│  │  Build: Dockerfile (non-root user, signal-cli config dir)                    │    │
│  │  Port: 8080 (internal only)                                                  │    │
│  │  Health: signal-cli listAccounts (30s interval, 60s start period)           │    │
│  │  Visibility: Internal only (NO public access)                                │    │
│  │  Internal URL: signal-cli-daemon.railway.internal:8080                      │    │
│  └──────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  ┌─── SERVICE 6: signal-proxy ──────────────────────────────────────────────────┐    │
│  │  Image: caddy:2-alpine                                                       │    │
│  │  Build: Dockerfile (COPY Caddyfile)                                          │    │
│  │  Port: 8080 (internal only)                                                  │    │
│  │  Health: GET /health                                                         │    │
│  │  Auth: X-API-Key on all endpoints                                            │    │
│  │  Internal URL: signal-proxy.railway.internal:8080                            │    │
│  └──────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  ┌─── MANAGED DATABASE: PostgreSQL ─────────────────────────────────────────────┐    │
│  │  Provided by Railway (managed)                                                │    │
│  │  Internal URL: postgres.railway.internal:5432                                │    │
│  │  Used by: authentik-server, authentik-worker                                 │    │
│  └──────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Container Architecture (moltbot internals)

The moltbot container runs two runtimes managed by supervisord.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│             MOLTBOT CONTAINER ARCHITECTURE                                            │
│                                                                                      │
│  ┌─── node:20-alpine Base Image ────────────────────────────────────────────────┐    │
│  │                                                                               │    │
│  │  ┌────────────────────────────────────────────────────────────────┐           │    │
│  │  │  supervisord (PID 1 via dumb-init)                             │           │    │
│  │  │  /etc/supervisor/conf.d/supervisord.conf                       │           │    │
│  │  │  nodaemon=true, user=root                                      │           │    │
│  │  │                                                                │           │    │
│  │  │  ┌──────────────────────────┐  ┌──────────────────────────┐   │           │    │
│  │  │  │  [program:nodejs]        │  │  [program:openclaw]      │   │           │    │
│  │  │  │                          │  │                          │   │           │    │
│  │  │  │  Express.js server       │  │  Python 3.13 bridge      │   │           │    │
│  │  │  │  node server.js          │  │  python3 -m openclaw.cli │   │           │    │
│  │  │  │  :8080 (HTTP)            │  │                          │   │           │    │
│  │  │  │                          │  │  Venv: /opt/venv/        │   │           │    │
│  │  │  │  Routes:                 │  │  Packages:               │   │           │    │
│  │  │  │  /health                 │  │  - neo4j driver          │   │           │    │
│  │  │  │  /health/neo4j           │  │  - tree-sitter           │   │           │    │
│  │  │  │  /health/disk            │  │  - tree-sitter-python    │   │           │    │
│  │  │  │  /health/file-consistency│  │  - openclaw modules      │   │           │    │
│  │  │  │  /api/learn              │  │  - kurultai tools        │   │           │    │
│  │  │  │  /api/auth/me            │  │                          │   │           │    │
│  │  │  │  /agent/{id}/message     │  │  Modules:                │   │           │    │
│  │  │  │  /ws/*                   │  │  - openclaw_memory.py    │   │           │    │
│  │  │  │                          │  │  - tools/kurultai/*      │   │           │    │
│  │  │  │  autostart=true          │  │  - tools/security/*      │   │           │    │
│  │  │  │  autorestart=true        │  │  - migrations/*          │   │           │    │
│  │  │  │                          │  │                          │   │           │    │
│  │  │  │  Logs:                   │  │  autostart=true          │   │           │    │
│  │  │  │  stdout -> nodejs.log    │  │  autorestart=true        │   │           │    │
│  │  │  │  stderr -> nodejs-err.log│  │                          │   │           │    │
│  │  │  │                          │  │  Logs:                   │   │           │    │
│  │  │  │                          │  │  stdout -> openclaw.log  │   │           │    │
│  │  │  │                          │  │  stderr -> openclaw-err  │   │           │    │
│  │  │  └──────────────────────────┘  └──────────────────────────┘   │           │    │
│  │  └────────────────────────────────────────────────────────────────┘           │    │
│  │                                                                               │    │
│  │  ┌─── LOG ROTATION ──────────────────────────────────────────────────────┐   │    │
│  │  │  Location: /data/workspace/logs/                                      │   │    │
│  │  │                                                                       │   │    │
│  │  │  ┌────────────────────────────┬──────────┬─────────────┐              │   │    │
│  │  │  │ File                       │ Max Size │ Backups     │              │   │    │
│  │  │  ├────────────────────────────┼──────────┼─────────────┤              │   │    │
│  │  │  │ supervisord.log            │ 100 MB   │ 5 files     │              │   │    │
│  │  │  │ nodejs.log                 │ 100 MB   │ 3 files     │              │   │    │
│  │  │  │ nodejs-error.log           │  50 MB   │ 2 files     │              │   │    │
│  │  │  │ openclaw.log               │ 100 MB   │ 3 files     │              │   │    │
│  │  │  │ openclaw-error.log         │  50 MB   │ 2 files     │              │   │    │
│  │  │  └────────────────────────────┴──────────┴─────────────┘              │   │    │
│  │  └───────────────────────────────────────────────────────────────────────┘   │    │
│  │                                                                               │    │
│  │  ┌─── PERSISTENT VOLUME: /data ──────────────────────────────────────────┐   │    │
│  │  │  /data/.clawdbot/         State dir (configs, credentials, sessions)  │   │    │
│  │  │  /data/workspace/         Agent workspace (souls, logs, user files)   │   │    │
│  │  │  /data/backups/           Optional local backups                      │   │    │
│  │  └───────────────────────────────────────────────────────────────────────┘   │    │
│  │                                                                               │    │
│  └───────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  DOCKER HEALTHCHECK:                                                                 │
│  --interval=30s --timeout=10s --start-period=40s --retries=3                        │
│  CMD: node -e "require('http').get('http://localhost:8080/health', (r) =>             │
│       { process.exit(r.statusCode === 200 ? 0 : 1) })"                              │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Deployment Pipeline

How code changes get deployed to Railway.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                       DEPLOYMENT PIPELINE                                             │
│                                                                                      │
│  ┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐        │
│  │ Developer │     │    GitHub    │     │   Railway    │     │  Container   │        │
│  │           │     │    Repo      │     │  Builder     │     │  Registry    │        │
│  └─────┬────┘     └──────┬───────┘     └──────┬───────┘     └──────┬───────┘        │
│        │                 │                     │                    │                 │
│        │ 1. git push     │                     │                    │                 │
│        │────────────────▶│                     │                    │                 │
│        │                 │                     │                    │                 │
│        │                 │ 2. Webhook trigger  │                    │                 │
│        │                 │────────────────────▶│                    │                 │
│        │                 │                     │                    │                 │
│        │                 │                     │ 3. Build Docker    │                 │
│        │                 │                     │    image from      │                 │
│        │                 │                     │    Dockerfile      │                 │
│        │                 │                     │                    │                 │
│        │                 │                     │ 4. Push image      │                 │
│        │                 │                     │───────────────────▶│                 │
│        │                 │                     │                    │                 │
│        │                 │                     │ 5. Start new       │                 │
│        │                 │                     │    container       │                 │
│        │                 │                     │◀───────────────────│                 │
│        │                 │                     │                    │                 │
│        │                 │                     │ 6. Health check    │                 │
│        │                 │                     │    (wait for 200   │                 │
│        │                 │                     │     on /health)    │                 │
│        │                 │                     │                    │                 │
│        │                 │                     │ 7. Route traffic   │                 │
│        │                 │                     │    to new container│                 │
│        │                 │                     │    (zero-downtime) │                 │
│        │                 │                     │                    │                 │
│        │                 │                     │ 8. Stop old        │                 │
│        │                 │                     │    container       │                 │
│        │                 │                     │                    │                 │
│        │ 9. Deployment   │                     │                    │                 │
│        │    complete     │                     │                    │                 │
│        │◀───────────────────────────────────────                    │                 │
│        │                 │                     │                    │                 │
│                                                                                      │
│  ROLLBACK: railway rollback --service <service-name>                                 │
│                                                                                      │
│  RAILWAY CONSTRAINTS:                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────────┐    │
│  │  - No Docker-in-Docker (sandbox.mode must be "off")                         │    │
│  │  - Railway strips CMD from images (use ENTRYPOINT [] + CMD [...])           │    │
│  │  - `railway up` uploads entire cwd (use temp dirs for minimal deploys)      │    │
│  │  - Variable table display truncates values (verify with --json)             │    │
│  │  - PORT env var auto-set to 8080                                            │    │
│  │  - Must set trustedProxies: ["*"] for Railway edge proxies                  │    │
│  │  - browser.enabled must be false (no browser containers)                    │    │
│  │  - tools.profile must be "coding" (excludes browser/computer tools)         │    │
│  └──────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.4 DNS & Routing

All Caddy routes in evaluation order with security warnings.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                       DNS & ROUTING CONFIGURATION                                     │
│                                                                                      │
│  DNS CHAIN:                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────────────┐    │
│  │                                                                              │    │
│  │  Browser                                                                     │    │
│  │    │                                                                         │    │
│  │    │  kublai.kurult.ai                                                       │    │
│  │    ▼                                                                         │    │
│  │  GoDaddy DNS                                                                 │    │
│  │    │  CNAME kublai -> authentik-proxy.up.railway.app (TTL: 600s)             │    │
│  │    ▼                                                                         │    │
│  │  Railway Edge                                                                │    │
│  │    │  TLS termination (Let's Encrypt, auto-provisioned)                      │    │
│  │    ▼                                                                         │    │
│  │  authentik-proxy container (:8080)                                           │    │
│  │                                                                              │    │
│  │  Verify: dig kublai.kurult.ai  (expect CNAME to Railway)                    │    │
│  └──────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  CADDY ROUTES (evaluation order in authentik-proxy/Caddyfile):                      │
│                                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────┐    │
│  │                                                                              │    │
│  │  ORDER  ROUTE PATTERN              AUTH             DESTINATION              │    │
│  │  ─────  ──────────────────────     ───────────────  ────────────────────     │    │
│  │                                                                              │    │
│  │   1.    /setup/api/signal-link     X-Signal-Token   moltbot:8080             │    │
│  │         [WARNING: Must have token check or anyone can link devices]          │    │
│  │                                                                              │    │
│  │   2.    /ws/*                      Session-based    moltbot:8080 (ws)        │    │
│  │         [WebSocket upgrade, maintains session from HTTP handshake]           │    │
│  │                                                                              │    │
│  │   3.    /outpost.goauthentik.io/*  None (internal)  authentik-server:9000    │    │
│  │         [WARNING: Must bypass or causes auth loop]                           │    │
│  │                                                                              │    │
│  │   4.    /application/*             Session-based    authentik-server:9000    │    │
│  │         [Authentik application management API]                               │    │
│  │                                                                              │    │
│  │   5.    /flows/*                   None (public)    authentik-server:9000    │    │
│  │         [Login/registration flow pages - must be public]                     │    │
│  │                                                                              │    │
│  │   6.    /health                    None (public)    moltbot:8080             │    │
│  │         [WARNING: MUST bypass auth or Railway marks service unhealthy]       │    │
│  │                                                                              │    │
│  │   7.    /* (catch-all)             forward_auth     moltbot:8080             │    │
│  │         Authentik validates session before proxying                           │    │
│  │         Sets X-Authentik-* headers on success                                │    │
│  │         Returns 302 redirect to login on failure                             │    │
│  │                                                                              │    │
│  └──────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  CRITICAL WARNING:                                                                   │
│  If the /health bypass route is removed or misordered, Railway health checks         │
│  will fail because they cannot authenticate. This causes the service to be           │
│  marked as unhealthy and potentially restarted in a loop.                            │
│                                                                                      │
│  PROTECTED ROUTES (require Authentik session):                                       │
│  ┌──────────────────────────────────────────────────────────────────────────────┐    │
│  │  /dashboard/*       Main control panel (Next.js)                             │    │
│  │  /control-panel/*   Agent configuration                                      │    │
│  │  /api/agent/*       Agent API endpoints                                      │    │
│  │  /api/learn         Capability learning                                      │    │
│  │  /api/auth/me       Current user info                                        │    │
│  └──────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.5 Monitoring Checklist

Health endpoints, alerts, and operational thresholds.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                       MONITORING & HEALTH CHECKLIST                                   │
│                                                                                      │
│  HEALTH ENDPOINTS:                                                                   │
│                                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────┐    │
│  │                                                                              │    │
│  │  ┌─────────────────────────────┬──────────────────────────────────────────┐  │    │
│  │  │ Endpoint                    │ Checks                                   │  │    │
│  │  ├─────────────────────────────┼──────────────────────────────────────────┤  │    │
│  │  │ GET /health                 │ Node.js running, Python running,         │  │    │
│  │  │                             │ Neo4j connected, Authentik reachable     │  │    │
│  │  ├─────────────────────────────┼──────────────────────────────────────────┤  │    │
│  │  │ GET /health/neo4j           │ Neo4j connection, version, node/rel     │  │    │
│  │  │                             │ counts, URI, database name              │  │    │
│  │  ├─────────────────────────────┼──────────────────────────────────────────┤  │    │
│  │  │ GET /health/disk            │ /data volume: total, used, available,   │  │    │
│  │  │                             │ percent_used                            │  │    │
│  │  ├─────────────────────────────┼──────────────────────────────────────────┤  │    │
│  │  │ GET /health/file-consistency│ monitor_running, last_severity,         │  │    │
│  │  │                             │ last_scan timestamp                     │  │    │
│  │  ├─────────────────────────────┼──────────────────────────────────────────┤  │    │
│  │  │ GET /-/health/ready/        │ Authentik server readiness              │  │    │
│  │  │ (authentik-server:9000)     │                                         │  │    │
│  │  └─────────────────────────────┴──────────────────────────────────────────┘  │    │
│  │                                                                              │    │
│  └──────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  ALERT THRESHOLDS:                                                                   │
│                                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────┐    │
│  │                                                                              │    │
│  │  ┌──────────────────────────┬───────────┬──────────────────────────────┐     │    │
│  │  │ Metric                   │ Threshold │ Action                       │     │    │
│  │  ├──────────────────────────┼───────────┼──────────────────────────────┤     │    │
│  │  │ /health returns non-200  │ 3 retries │ Railway restarts container   │     │    │
│  │  │ Disk usage               │ > 80%     │ Alert, review log rotation   │     │    │
│  │  │ Neo4j connection         │ 5 fails   │ Circuit breaker opens,       │     │    │
│  │  │                          │           │ fallback mode activates      │     │    │
│  │  │ Neo4j fallback mode      │ Active    │ Recovery daemon checks 30s   │     │    │
│  │  │ File consistency         │ >= high   │ Escalate to Kublai           │     │    │
│  │  │ Agent key expiry         │ < 7 days  │ Auto-rotate via agent_auth   │     │    │
│  │  │ CBAC grant expiry        │ < 7 days  │ Review and re-grant          │     │    │
│  │  │ Signal connection        │ Timeout   │ Check signal-cli-daemon,     │     │    │
│  │  │                          │           │ re-link if session expired   │     │    │
│  │  │ Log file size            │ > 100 MB  │ supervisord auto-rotates     │     │    │
│  │  │ Notion sync              │ > 5 min   │ Check NOTION_TOKEN, API      │     │    │
│  │  │                          │ stale     │ rate limits                  │     │    │
│  │  └──────────────────────────┴───────────┴──────────────────────────────┘     │    │
│  │                                                                              │    │
│  └──────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  STRUCTURED LOGGING (Pino JSON format):                                              │
│                                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────┐    │
│  │  Format: {"level":"info","time":"ISO-8601","method":"GET",                  │    │
│  │           "path":"/health","statusCode":200,"duration":15,                  │    │
│  │           "userAgent":"Railway-HealthCheck/1.0","msg":"request completed"}  │    │
│  │                                                                              │    │
│  │  File: moltbot-railway-template/middleware/logger.js                        │    │
│  │  Level: Controlled by LOG_LEVEL env var (default: info)                     │    │
│  │  PII: Sanitized before logging (PIISanitizer in middleware)                 │    │
│  └──────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  OPERATIONAL CHECKLIST:                                                               │
│                                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────┐    │
│  │  Daily:                                                                      │    │
│  │  [ ] Verify /health returns 200 for all services                            │    │
│  │  [ ] Check Neo4j is not in fallback mode (/health/neo4j)                    │    │
│  │  [ ] Review /health/file-consistency for conflicts                          │    │
│  │  [ ] Check disk usage < 80% (/health/disk)                                  │    │
│  │                                                                              │    │
│  │  Weekly:                                                                     │    │
│  │  [ ] Review Neo4j node/relationship counts for anomalies                    │    │
│  │  [ ] Verify Signal integration (send test message)                          │    │
│  │  [ ] Check log files for error patterns                                     │    │
│  │  [ ] Review Notion sync audit trail (SyncEvent nodes)                       │    │
│  │                                                                              │    │
│  │  Monthly:                                                                    │    │
│  │  [ ] Rotate agent HMAC keys (< 90 day expiry)                               │    │
│  │  [ ] Review CBAC grants for least privilege                                  │    │
│  │  [ ] Run Neo4j backup and verify restore                                    │    │
│  │  [ ] Review PromptInjectionFilter patterns                                  │    │
│  │  [ ] Verify CostEnforcer budget limits                                      │    │
│  │  [ ] Test Neo4j fallback mode (circuit breaker + recovery)                  │    │
│  │  [ ] Check all tokens are not committed to git                              │    │
│  └──────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Section 5: Operational Reference

### 5.1 Deployment Phase Sequence

The v0.2 deployment follows a phased approach with half-phases for new features. Each phase depends on the completion of the previous phase.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                         DEPLOYMENT PHASES (v0.2)                                      │
│                                                                                      │
│  Phase -1 ─── Wipe and Rebuild                                                       │
│       │        Clean slate teardown of previous deployment                            │
│       ▼                                                                              │
│  Phase 0 ──── Environment & Security Setup                                            │
│       │        Credentials, env vars, security controls                               │
│       ▼                                                                              │
│  Phase 1 ──── Neo4j & Foundation                                                      │
│       │        AuraDB setup, migrations v1/v2/v3, agent keys                          │
│       ▼                                                                              │
│  Phase 1.5 ── Task Dependency Engine  ◀── NEW                                         │
│       │        Intent window buffering, DAG builder, topological executor              │
│       ▼                                                                              │
│  Phase 2 ──── Capability Acquisition System                                           │
│       │        6-phase horde-learn pipeline, CBAC                                     │
│       ▼                                                                              │
│  Phase 3 ──── Railway Deployment                                                      │
│       │        Dockerfiles, service creation, container deployment                     │
│       ▼                                                                              │
│  Phase 4 ──── Signal Integration                                                      │
│       │        signal-cli-daemon, signal-proxy, API translation                       │
│       ▼                                                                              │
│  Phase 4.5 ── Notion Integration  ◀── NEW                                             │
│       │        Bidirectional sync, polling engine, reconciliation                      │
│       ▼                                                                              │
│  Phase 5 ──── Authentik Web App Integration                                           │
│       │        SSO, WebAuthn, forward auth proxy                                      │
│       ▼                                                                              │
│  Phase 6 ──── Monitoring & Health Checks                                              │
│       │        Structured logging, health endpoints, log rotation                     │
│       ▼                                                                              │
│  Phase 6.5 ── File Consistency Monitoring  ◀── NEW                                    │
│       │        Ogedei file monitor, conflict detection, resolution                    │
│       ▼                                                                              │
│  Phase 7 ──── Testing & Validation  (depends on Phase 6.5)                            │
│                End-to-end tests, schema validation, load testing                      │
│                                                                                      │
│  Appendices: A (Env Vars), B (Service Config), C (Troubleshooting),                  │
│              D (Rollback), E (Security Ref), F (Fallback Procedures),                │
│              G (Scope Boundary)                                                       │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Environment Variables Reference

All 26 environment variables required for v0.2 deployment, organized by scope.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                     ENVIRONMENT VARIABLES (v0.2)                                      │
├──────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  PROJECT-LEVEL (shared across services)                                              │
│  ┌────────────────────────────┬──────────┬──────────────────────────────────────────┐│
│  │ Variable                   │ Required │ Example                                  ││
│  ├────────────────────────────┼──────────┼──────────────────────────────────────────┤│
│  │ NEO4J_URI                  │ Yes      │ neo4j+s://xxxxx.databases.neo4j.io       ││
│  │ NEO4J_USER                 │ Yes      │ neo4j                                    ││
│  │ NEO4J_PASSWORD             │ Yes      │ $SECURE_PASSWORD                         ││
│  │ NEO4J_DATABASE             │ No       │ neo4j (default)                          ││
│  │ ANTHROPIC_API_KEY          │ Yes      │ sk-ant-...                               ││
│  │ ANTHROPIC_BASE_URL         │ No       │ https://api.z.ai/api/anthropic           ││
│  │ AUTHENTIK_SECRET_KEY       │ Yes      │ $(openssl rand -hex 32)                  ││
│  │ AUTHENTIK_BOOTSTRAP_PASS.. │ Yes      │ $(openssl rand -base64 24)               ││
│  │ AUTHENTIK_EXTERNAL_HOST    │ Yes      │ https://kublai.kurult.ai                 ││
│  │ SIGNAL_LINK_TOKEN          │ Yes      │ $(openssl rand -hex 32)                  ││
│  │ OPENCLAW_GATEWAY_TOKEN     │ Yes      │ $(openssl rand -base64 48)               ││
│  │ OPENCLAW_GATEWAY_URL       │ Yes      │ http://moltbot-railway-template          ││
│  │                            │          │   .railway.internal:8080                  ││
│  │ NOTION_TOKEN               │ Yes*     │ secret_xxxxx                             ││
│  │ NOTION_DATABASE_ID         │ Yes*     │ (database UUID)                          ││
│  └────────────────────────────┴──────────┴──────────────────────────────────────────┘│
│                                                                                      │
│  SERVICE-LEVEL (per-service configuration)                                           │
│  ┌────────────────────────────┬──────────┬──────────────────────────────────────────┐│
│  │ Variable                   │ Required │ Example                                  ││
│  ├────────────────────────────┼──────────┼──────────────────────────────────────────┤│
│  │ AUTHENTIK_POSTGRESQL__HOST │ Yes      │ postgres.railway.internal                ││
│  │ AUTHENTIK_POSTGRESQL__NAME │ Yes      │ railway                                  ││
│  │ AUTHENTIK_POSTGRESQL__USER │ Yes      │ postgres                                 ││
│  │ AUTHENTIK_POSTGRESQL__PASS │ Yes      │ $POSTGRES_PASSWORD                       ││
│  │ SIGNAL_API_KEY             │ Yes      │ $(openssl rand -hex 32)                  ││
│  │ SIGNAL_ACCOUNT_NUMBER      │ Yes      │ +15165643945                             ││
│  │ KURLTAI_ENABLED            │ Yes      │ true                                     ││
│  │ KURLTAI_MAX_PARALLEL_TASKS │ No       │ 10 (default)                             ││
│  │ CLAWDBOT_STATE_DIR         │ Yes      │ /data/.clawdbot                          ││
│  │ CLAWDBOT_WORKSPACE_DIR     │ Yes      │ /data/workspace                          ││
│  │ PORT                       │ Auto     │ 8080 (Railway auto-set)                  ││
│  │ LOG_LEVEL                  │ No       │ info (default)                           ││
│  │ NOTION_POLL_INTERVAL       │ No       │ 30 (seconds)                             ││
│  │ NOTION_SYNC_ENABLED        │ No       │ true                                     ││
│  │ NOTION_LAST_SYNC_CURSOR    │ No       │ (auto-managed)                           ││
│  └────────────────────────────┴──────────┴──────────────────────────────────────────┘│
│                                                                                      │
│  * Notion vars required only when NOTION_SYNC_ENABLED=true                           │
│                                                                                      │
│  GENERATE SECURE CREDENTIALS:                                                        │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐│
│  │  openssl rand -hex 32              # AUTHENTIK_SECRET_KEY, SIGNAL_API_KEY,       ││
│  │                                    # SIGNAL_LINK_TOKEN                           ││
│  │  openssl rand -base64 24           # AUTHENTIK_BOOTSTRAP_PASSWORD                ││
│  │  openssl rand -base64 48           # OPENCLAW_GATEWAY_TOKEN                      ││
│  └──────────────────────────────────────────────────────────────────────────────────┘│
│                                                                                      │
│  WARNING: Railway variable table display TRUNCATES values.                            │
│  Always verify with: railway variables --json                                        │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 5.3 Backup and Recovery

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                     BACKUP TARGETS                                                    │
├──────────────────────────────┬──────────────┬──────────┬─────────────────────────────┤
│ Target                       │ Priority     │ Frequency│ Method                      │
├──────────────────────────────┼──────────────┼──────────┼─────────────────────────────┤
│ /data/.clawdbot/moltbot.json │ Critical     │ Before   │ tar -czf config.tar.gz      │
│ /data/.clawdbot/openclaw.json│ Critical     │ changes  │                             │
│ /data/.clawdbot/credentials/ │ Critical     │ Daily    │                             │
├──────────────────────────────┼──────────────┼──────────┼─────────────────────────────┤
│ /data/workspace/souls/       │ High         │ Daily    │ tar -czf souls.tar.gz       │
├──────────────────────────────┼──────────────┼──────────┼─────────────────────────────┤
│ Environment variables        │ Critical     │ On       │ railway variables --json     │
│                              │              │ creation │ (sanitize secrets)           │
├──────────────────────────────┼──────────────┼──────────┼─────────────────────────────┤
│ Neo4j database               │ Critical     │ Daily    │ OpenClawMemory.export_to_   │
│                              │              │          │ json('/data/backups/...')    │
├──────────────────────────────┼──────────────┼──────────┼─────────────────────────────┤
│ Authentik database           │ Critical     │ Daily    │ ak export_blueprint >       │
│                              │              │          │ authentik-backup.yaml        │
└──────────────────────────────┴──────────────┴──────────┴─────────────────────────────┘
```

**Rollback Procedures:**

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                     ROLLBACK PROCEDURES                                               │
│                                                                                      │
│  1. ROLLBACK RAILWAY SERVICE                                                         │
│     ┌──────────────────────────────────────────────────────────────────────┐          │
│     │  railway rollback --service moltbot-railway-template                │          │
│     │  railway rollback --service authentik-proxy                         │          │
│     └──────────────────────────────────────────────────────────────────────┘          │
│                                                                                      │
│  2. ROLLBACK NEO4J MIGRATION                                                         │
│     ┌──────────────────────────────────────────────────────────────────────┐          │
│     │  python scripts/run_migrations.py --target-version 2  # v3 → v2    │          │
│     │  python scripts/run_migrations.py --target-version 1  # v2 → v1    │          │
│     └──────────────────────────────────────────────────────────────────────┘          │
│     WARNING: V3 DOWN_CYPHER rollback has ~25 drop statements.                        │
│     Verify all constraints/indexes are dropped cleanly.                               │
│                                                                                      │
│  3. RESTORE CONFIGURATION                                                            │
│     ┌──────────────────────────────────────────────────────────────────────┐          │
│     │  tar -xzf /data/backups/<timestamp>/config.tar.gz -C /             │          │
│     │  railway service restart --service moltbot-railway-template         │          │
│     └──────────────────────────────────────────────────────────────────────┘          │
│                                                                                      │
│  4. RESTORE NEO4J DATA                                                               │
│     ┌──────────────────────────────────────────────────────────────────────┐          │
│     │  python -c "                                                        │          │
│     │    from openclaw_memory import OpenClawMemory                       │          │
│     │    OpenClawMemory().import_from_json('<backup>/neo4j.json')         │          │
│     │  "                                                                  │          │
│     └──────────────────────────────────────────────────────────────────────┘          │
│                                                                                      │
│  5. EMERGENCY ACCESS (DISABLE AUTHENTIK)                                              │
│     ┌──────────────────────────────────────────────────────────────────────┐          │
│     │  railway service stop --service authentik-proxy                     │          │
│     │  railway domains --service moltbot-railway-template \               │          │
│     │    add kublai-direct.kurult.ai                                      │          │
│     └──────────────────────────────────────────────────────────────────────┘          │
│     This bypasses authentication entirely. Use only in emergencies.                  │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 5.4 Scope Boundary — Deferred to v0.3

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                     DEFERRED TO v0.3                                                  │
├──────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│  These features are NOT in v0.2 scope. Node types are pre-reserved in Neo4j v3       │
│  migration but have no implementation.                                               │
│                                                                                      │
│  ┌──────────────────────────────┬──────────────────────────────────────────────────┐  │
│  │ Feature                      │ Status                                          │  │
│  ├──────────────────────────────┼──────────────────────────────────────────────────┤  │
│  │ Team orchestration           │ Schema reserved (TeamMembership, TeamGoal)       │  │
│  │ Goal tracking                │ Schema reserved (Goal, GoalProgress)             │  │
│  │ Conversation memory          │ Schema reserved (Conversation, Message)          │  │
│  │ Tool execution tracking      │ Schema reserved (ToolExecution, ToolResult)      │  │
│  │ User preferences             │ Schema reserved (UserPreference)                 │  │
│  │ Cost tracking                │ Schema reserved (CostRecord)                     │  │
│  │ Semantic search expansion    │ Schema reserved (SemanticCluster)                │  │
│  │ Audit logging                │ Schema reserved (AuditLog)                       │  │
│  └──────────────────────────────┴──────────────────────────────────────────────────┘  │
│                                                                                      │
│  These 12 reserved node types enable forward-compatible schema design.                │
│  v0.3 can add implementations without requiring a new migration.                     │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

**End of Visual Architecture Guide**

**Source Document**: `/Users/kurultai/molt/ARCHITECTURE.md` (2,062 lines)
**Generated**: 2026-02-06
**Coverage**: 5 sections, 21 subsections, all v0.2 features including Task Dependency Engine, Notion Integration, File Consistency Monitoring, Neo4j Fallback Mode, NFKC normalization, deployment phases, environment variables, backup/recovery, and scope boundary.
