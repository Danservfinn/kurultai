---
type: analysis
status: active
updated: 2026-08-08
created: 2026-08-08
sources: 0
tags: [parse, compliance, control-panel, dashboard, audit, siem, framework, developer-product]
---

# Parse Compliance Control Panel — Design & Build Record

> Auditability is not an enterprise upsell — it's the core developer product. Every developer shipping an agent needs to see what their agent is doing and control it with real levers.

## What Was Built

### 1. Schema (prisma/schema.prisma)
5 new models added:
- **Organization** — org-level scoping (links to ApiKey.orgId)
- **AgentRegistry** — inventory of agents with tools, data access, risk levels, owner, status
- **PolicyRevision** — versioned policy changes with diffs and change reasons
- **SIEMConfig** — Splunk/Datadog/Elastic/Sentinel/webhook forwarding configs
- **ComplianceExport** — tamper-evident evidence packs with SHA-256 integrity hashes

### 2. Framework Crosswalk (src/lib/compliance/framework-crosswalk.ts)
Maps Parse's 9 risk categories + detection capabilities to 5 compliance frameworks:
- **OWASP Top 10 for LLM Applications (2025)** — 10 controls, 100% mapped
- **NIST AI RMF 1.0** — 18 controls across GOVERN/MAP/MEASURE/MANAGE
- **EU AI Act** — 8 articles (Art. 9, 12, 13, 14, 15, 26, 27)
- **ISO/IEC 42001** — 6 clauses
- **SOC 2 Trust Services Criteria** — 6 controls (CC7.1-CC7.5, CC8.1)

Each mapping includes specific Parse code paths as evidence sources.

### 3. SIEM Forwarder (src/lib/compliance/siem-forwarder.ts)
- Format adapters: CEF (Splunk/QRadar), JSON, LEEF (IBM QRadar)
- Platform-specific auth: Splunk HEC, Datadog API key, Elastic API key, Bearer token
- Connection testing with latency measurement
- Event type filtering (screening, audit, policy_change, approval)

### 4. API Routes (src/routes/compliance.ts)
- `GET /v1/compliance/summary` — dashboard KPIs, risk distribution, 7-day trend, top agents
- `GET /v1/compliance/audit-trail` — filterable screening event history with pagination
- `GET /v1/compliance/framework-map` — full crosswalk (all 5 frameworks)
- `GET /v1/compliance/framework-map/:framework` — single-framework view
- `GET /v1/compliance/coverage` — framework coverage percentages
- `POST /v1/compliance/export` — generate SHA-256 signed evidence pack
- `GET/POST/DELETE /v1/compliance/siem` — configure SIEM forwarding
- `POST /v1/compliance/siem/test` — test SIEM connection
- `GET /v1/compliance/policy-history` — versioned policy change log

### 5. Dashboard UI (src/pages/compliance-dashboard.ts)
6-tab control panel at `/dashboard/compliance`:
1. **Overview** — KPIs, 7-day trend chart, risk distribution doughnut, top categories, agents by risk
2. **Audit Trail** — filterable event table (verdict, blocked, categories)
3. **Policy Levers** — toggle switches for screening controls, threshold slider, approval workflow config
4. **Frameworks** — coverage cards + progress bars for all 5 frameworks
5. **Evidence Export** — date range + framework filter → SHA-256 signed export
6. **SIEM Forwarding** — platform selector, endpoint config, connection testing

## Key Design Decisions

1. **API-key scoped, not org-scoped** — Every developer gets their own compliance view. Organization model exists for future expansion but doesn't block the developer experience.
2. **Audit-first** — Every action (screening, policy change, export, SIEM config) is logged via the existing auditLog() infrastructure.
3. **Framework crosswalk as data, not opinions** — The crosswalk maps specific Parse code paths to specific framework controls. This is machine-readable evidence.
4. **Tamper-evident exports** — Every evidence export gets a SHA-256 hash. Auditors can verify integrity.
5. **SIEM formats are platform-native** — CEF for Splunk, LEEF for QRadar, JSON for modern stacks. Not a one-size-fits-all format.
6. **Policy levers are real** — The toggles in the dashboard call the existing PUT /v1/policy endpoint. This is the same enforcement layer that the API uses.

## What This Unlocks

For developers:
- **Visibility**: "What is my agent doing?" → Audit trail tab
- **Control**: "What should my agent be allowed to do?" → Policy levers tab
- **Compliance**: "How does this map to OWASP/NIST/EU AI Act?" → Frameworks tab
- **Evidence**: "Give me an audit pack" → Export tab with SHA-256
- **Integration**: "Pipe this to my SIEM" → SIEM tab

For the business:
- The compliance layer is the expansion, not the pivot
- Developer API is the wedge; compliance control panel is the retention engine
- Framework mapping makes Parse speak the language of security teams
- SIEM forwarding makes Parse events visible to the SOC without a separate product
