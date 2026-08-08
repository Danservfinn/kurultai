# Strategic Assessment: Should Parse Pivot to Enterprise Agent Compliance?

**Prepared:** August 2026
**Classification:** Founder-level strategic memo
**Subject:** Assessing a pivot from developer-facing prompt security API to enterprise compliance/governance platform for agent activity regulation

---

## Executive Summary

Parse has built a technically impressive agent security engine: a 3-layer prompt security pipeline, a 6-layer agent trust verification system, 100+ detection patterns across 9 risk categories, policy configuration with auto-block thresholds, screening event persistence, approval workflows, audit logging, and exposure evaluation. This is genuine engineering depth that most competitors in the "prompt security API" space do not match at the code level.

However, pivoting to enterprise compliance — "top-down regulation of agent activity" — is a fundamentally different business with different physics. Enterprise compliance is not won by the best detection engine; it is won by the best enterprise sales motion, the most recognizable brand, the most extensive compliance framework mappings, and the deepest integrations into SIEM/RBAC/GRC tooling that CISOs already own. Parse has the detection engine but almost none of the enterprise scaffolding.

**Verdict: Hybrid — not a pivot.** Double down on the developer API as the wedge, and build a thin enterprise compliance layer on top of the existing detection/screening/policy/audit infrastructure. Do not attempt a full pivot into the enterprise compliance market as an enterprise-only product. The evidence for why follows.

---

## A. Capability Map: What Parse Has vs. What Enterprise Agent Compliance Needs

### What Parse Already Has (and how it maps to compliance)

| Existing Capability | Code Path | Enterprise Compliance Mapping |
|---|---|---|
| **3-layer prompt risk analysis** | `src/parse.ts` → `parsePrompt()` — pattern matching (Phase 1, `INJECTION_PATTERNS`), structural analysis (Phase 2, `detectStructuralRisks`), LLM semantic analysis (Phase 3, `llmRiskAnalysis`) | **Agent input control.** Every prompt entering an agent is scored 0-10 with typed flags, categories, and severity. This is the "detection layer" that compliance platforms need. |
| **9 risk categories** | `src/lib/patterns/index.ts` — `RISK_CATEGORIES`: prompt_injection, jailbreak, data_exfiltration, harmful_content, system_prompt_leak, privilege_escalation, social_engineering, code_execution, indirect_injection | **Risk taxonomy.** Maps partially to OWASP Top 10 for LLMs, NIST AI RMF risk categories. Needs formal crosswalk to compliance frameworks. |
| **100+ regex detection patterns** | `src/lib/patterns/index.ts` — 100+ patterns across injection, jailbreak, exfiltration, encoding/obfuscation, tool-use abuse, indirect injection, semantic paraphrasing, system prompt extraction | **Policy enforcement engine.** These are effectively compliance rules. Each pattern has a severity and category — this is the basis for a policy-as-code engine. |
| **Policy configuration** | `src/routes/policy.ts` — `ScreeningPolicy` with `autoBlockThreshold`, `screenUserInput`, `screenToolOutputs`, `screenForwardedMessages`, `executeInSandbox`, bypass codeword with expiry, approval requirements for personal data/location/future plans | **Policy management.** This is a basic policy engine. Tier-enforced thresholds (`MAX_THRESHOLD_BY_TIER`) show an understanding of differentiated enforcement. But it's per-API-key, not per-organization. |
| **6-layer agent trust pipeline** | `src/lib/trust-verification/orchestrator.ts` → `verifyTrust()` — prompt injection, social engineering, spoofing, sensitive data, malicious intent aggregation, with weighted scoring and risk levels | **Agent-to-agent governance.** Directly relevant to multi-agent compliance: verifying that one agent can trust another before delegating. Maps to "inter-agent access control." |
| **Screening event persistence** | `src/lib/screening-event-log.ts` → `persistScreeningEventData()`, `buildScreeningEventData()`, `ScreeningEvent` model in Prisma with risk score, verdict, categories, latency, blocked status, metadata (source_kind, trust_level, intended_action, rule_ids) | **Compliance audit trail.** This is the foundation. Every screening decision is persisted with decision metadata. But it's per-API-key, not cross-agent or cross-organization. |
| **Audit logging** | `src/lib/audit-log.ts` → `auditLog()`, `AuditEvent` model with action, apiKeyId, detail (riskScore, verdict, recommendedAction, categories, ruleIds), IP, timestamp | **Security event logging.** Every policy change, approval, and screening is logged. This is the raw material for SIEM integration. |
| **Approval workflow** | `src/routes/approvals.ts` + `src/lib/approvals.ts` — create approval request, approve with action hash, verify token, TTL expiry, delivery channels, HMAC-signed tokens, action canonicalization | **Human-in-the-loop governance.** This is "break-glass" / "four-eyes" compliance control. Blocked actions can require human approval before proceeding. Directly maps to SOX/PCI-DSS segregation-of-duties requirements. |
| **Output screening** | `src/routes/screen-output.ts` → `analyzeOutputRisks()` — screens LLM output for prompt reflection, data leakage, harmful content, system prompt leakage | **Agent output control.** Compliance requires controlling what agents emit, not just what they receive. This covers the egress side. |
| **Exposure evaluation** | `src/routes/exposure.ts` + `src/lib/exposure/evaluate.ts` — evaluates sanitized Bumblebee-compatible exposure findings, returns policy verdict (allow/block/warn) with recommended actions | **Supply chain / tool exposure.** Maps to agent supply-chain governance. Evaluates whether exposed components (MCP servers, extensions, packages) pose policy violations. |
| **Scoring engine** | `src/lib/scoring.ts` → `calculateRiskScore()` — weighted category scoring, correlation bonuses, severity multipliers, monotonic floor, LLM score blending | **Risk quantification.** Every agent interaction gets a quantified risk score — essential for compliance reporting ("what % of agent actions were high-risk?"). |
| **Admin dashboard** | `src/routes/admin.ts` — 2500+ lines of admin operations: API key management, policy upsert, customer resolution, entitlement grants, GEO analytics, screening event listing | **Administrative control plane.** The skeleton exists but is internal-facing (master key auth), not a multi-tenant enterprise console. |
| **Billing/usage tracking** | `src/routes/billing.ts`, `src/lib/usage-tracker.ts` — Stripe subscriptions, usage metering per API key per month | **Monetization infrastructure.** Can be extended to per-agent or per-organization billing. |

### What Enterprise Agent Compliance Needs That Parse Lacks

| Capability Gap | Why It Matters | Build Effort |
|---|---|---|
| **Organization/workspace model** | Compliance is per-organization, not per-API-key. Parse's entire data model is `ApiKey`-centric. There's an `orgId` field on `ApiKey` but no Organization model, no org-level policies, no org-level audit aggregation. | Medium — schema migration, but conceptually straightforward |
| **RBAC / role-based access control** | Enterprise compliance requires admin/security-analyst/auditor/viewer roles. Parse has scopes (`analyze`, `evaluate`, `chat`, `admin`) but no role hierarchy, no permission inheritance, no user management. | Large — full identity + role system |
| **SIEM integration (Splunk, Datadog, Elastic, Sentinel)** | CISOs need agent security events in their existing SIEM. Parse logs to console + PostgreSQL. No syslog, no CEF, no webhook forwarding, no Splunk HEC. | Medium — event forwarding infrastructure |
| **Compliance framework mappings** | Enterprises need controls mapped to SOC 2, ISO 27001, EU AI Act, NIST AI RMF, HIPAA, PCI-DSS. Parse has risk categories but no crosswalk document or mapping engine. | Medium — domain expertise + documentation |
| **Policy engine with custom rules** | Enterprises need to define their own compliance rules (e.g., "no agent may access HIPAA data without audit logging"). Parse has hardcoded patterns and tier-based thresholds. No DSL, no custom rule engine, no policy versioning. | Large — needs a policy-as-code engine (OPA/Cedar integration or custom) |
| **Agent inventory / registry** | Compliance requires knowing what agents exist, what tools they have, what data they access. Parse has no agent registry — agents are identified by `agent_id` in metadata but not managed. | Large — new product surface |
| **Data classification integration** | Compliance requires mapping agent actions to data classifications (PII, PHI, financial). Parse has `data_classification` as a metadata field but no enforcement. | Medium — integration with DLP/classification tools |
| **Compliance reporting / evidence export** | Auditors need evidence packs. Parse has screening events and audit logs but no report generator, no evidence export, no control mapping reports. | Medium — reporting layer |
| **SSO / SAML / SCIM** | Enterprise sales require enterprise identity integration. Parse uses API keys. | Large — identity provider integration |
| **Multi-tenancy / data isolation** | Enterprise compliance often requires dedicated infrastructure or guaranteed data isolation. Parse is a single-tenant Railway deployment. | Medium-Large — infrastructure work |
| **Data residency** | EU AI Act and GDPR require data residency controls. Parse has none. | Large — multi-region infrastructure |
| **Penetration testing / security certifications** | CISOs require SOC 2 Type II reports, penetration test results. Parse has none publicly. | Large — 6-12 month process + cost |

---

## B. Build vs. Buy Gap Analysis

### What to BUILD (using existing Parse infrastructure as a foundation):

1. **Organization model** — Add an `Organization` model with org-level `ScreeningPolicy`, org-level audit aggregation, and org-scoped API keys. This is a schema migration and admin route update. **~2-3 weeks.**

2. **Compliance event forwarding** — Add webhook/SIEM forwarding for `ScreeningEvent` and `AuditEvent`. Simple event queue → external HTTP delivery (Splunk HEC, Datadog Logs API, generic webhook). **~1-2 weeks.**

3. **Framework crosswalk** — A mapping document (and JSON config) that maps Parse's 9 risk categories to OWASP Top 10 for LLMs, NIST AI RMF functions, EU AI Act requirements, and ISO 27001 controls. **~2 weeks (domain expertise heavy).**

4. **Evidence export** — A `/v1/compliance/export` endpoint that produces time-bounded evidence reports (screening events, policy changes, blocked actions, approval workflows). **~1 week.**

5. **Policy versioning** — Version `ScreeningPolicy` changes and track diffs. Already partially supported by `updatedAt` on the model. **~1 week.**

### What to BUY (integrate rather than build):

1. **Identity/RBAC** — Use Auth0, Clerk, or WorkOS for SSO/SAML/SCIM and role management. Building this from scratch is a 6-month project with no differentiation. **Integration: ~2 weeks.**

2. **SIEM connectors** — Use a service like Panorama (event routing) or build simple adapters for the top 3-4 SIEM platforms. **Integration: ~2-3 weeks.**

3. **Policy engine** — Evaluate Cedar (Amazon's policy language) or Open Policy Agent (OPA) for custom compliance rules. Embed evaluation in the screening pipeline. **Integration: ~3-4 weeks.**

### What to DEFER (not needed for a hybrid approach):

1. Full multi-tenancy — can start with logical isolation (org-scoped API keys + row-level security).
2. Data residency — only needed for EU customers; defer until EU pipeline appears.
3. SOC 2 Type II certification — pursue in parallel but don't block GTM on it.

---

## C. Market Analysis: Competitive Landscape

### Direct Competitors (Prompt/Agent Security)

| Company | Positioning | Funding | Strengths | Weaknesses | Parse's Opening |
|---|---|---|---|---|---|
| **Lakera** | Enterprise GenAI security guardrails; Lakera Guard API | ~$33M (Series A, 2024) | Strong brand recognition in prompt injection; enterprise sales motion; established | Model-agnostic but enterprise-oriented; procurement friction; no agent-native API discovery | Parse can own the developer-first / agent-native segment Lakera isn't serving |
| **Prompt Security** | Enterprise GenAI security & governance platform | ~$18M (Series A, 2024) | Full platform: posture management, runtime protection, governance console | Broad focus; not agent-specific; enterprise-only | Parse is agent-native and API-first, not enterprise-platform |
| **Protect AI** | AI/ML security platform (Radar, NB Defense, ModelScan) | ~$60M+ (Series B, 2024) | Deep MLSecOps expertise; broad platform (model scanning, runtime, posture) | Broad focus dilutes agent-specific depth | Parse's agent trust pipeline is more focused on agent-to-agent scenarios |
| **Robust Intelligence** (acquired by Cisco, 2025) | AI application security; model risk management | Acquired by Cisco | Now part of Cisco's enterprise security stack — massive distribution | Absorbed into Cisco; becomes a feature, not standalone API | Parse's independence (as articulated in their blog) is a positioning advantage |
| **HiddenLayer** | AI/ML security for enterprise and government | ~$31M (Series A, 2024) | Government/defense focus; SOC 2 Type II; HLS certifications | Government/defense-oriented; not agent-specific | Different market segment |
| **CalypsoAI** | Enterprise AI security, red-teaming, governance | ~$15M+ | Strong LLM testing/evaluation focus | Evaluation, not runtime agent screening | Parse covers runtime screening CalypsoAI focuses on pre-deployment testing |
| **Pangea** | API-first security platform (AI Guard, etc.) | ~$36M+ (Series B, 2024) | API-first approach similar to Parse; multiple security services | Broad platform; AI Guard is one of many services | Parse is more focused on agent-specific risks |
| **Cloud-native guardrails** (AWS Bedrock Guardrails, Azure AI Content Safety, Google Vertex Safety) | Cloud provider native | N/A (included in cloud) | Zero friction for existing cloud customers; deeply integrated | Vendor-locked; doesn't work across model providers; not agent-specific | Parse's model-agnostic independence is the wedge |

### Where the Gap Is

The competitive landscape splits into:
1. **Enterprise platforms** (Lakera, Prompt Security, CalypsoAI) — broad governance, enterprise sales, 12-18 month sales cycles
2. **Cloud-native features** (AWS/Azure/Google guardrails) — free with cloud, vendor-locked
3. **Developer APIs** (Parse, Pangea AI Guard) — self-service, API-first, agent-native

**No one currently owns "agent-native compliance for the mid-market"** — the gap between developer API and enterprise platform. Companies running 10-200 agents need compliance controls but can't afford a 12-month enterprise procurement cycle with Lakera. This is Parse's potential wedge.

The key insight from Parse's own GEO strategy doc is correct: **"Parse Agents is a prompt protection API for AI agents."** This is the right identity. Pivoting to "enterprise compliance platform" dilutes this.

---

## D. The Pivot Thesis — Strong Arguments

### 1. Regulatory tailwinds are real and accelerating

- **EU AI Act**: Enforcement for high-risk AI systems begins August 2026. GPAI model obligations are phasing in. Enterprises deploying AI agents face documentation, risk assessment, and human oversight requirements. This creates demand.
- **NIST AI RMF** is increasingly referenced in US federal contracts and enterprise AI governance policies.
- **OWASP Top 10 for LLM Applications** and the new **OWASP Top 10 for Agentic Applications** are becoming reference frameworks for security teams.
- Parse's blog already references these: the OWASP post mentions "NIST AI Agent Standards Initiative (Feb 2026)" and "100+ industry experts reviewed by NIST, European Commission, Alan Turing Institute."

### 2. Agent sprawl is creating a real governance crisis

- Enterprises are deploying agents faster than they can govern them. A 2025 Gartner projection said 40% of enterprise applications would embed AI agents by 2026.
- Each agent has tools, data access, and the ability to take actions. Without governance, this is uncontrolled risk surface.
- The `ParseRequest` metadata already captures `agent_id`, `session_id`, `source_kind`, `trust_level`, `tool_permissions`, `data_classification`, `intended_action` — this is exactly the metadata a compliance platform needs. Parse is already capturing the right data; it just isn't surfacing it as a compliance product.

### 3. Parse's existing trust pipeline is genuinely differentiated

- The 6-layer agent trust pipeline (`prompt-injection`, `social-engineering`, `spoofing`, `sensitive-data`, `malicious-intent`) with weighted scoring and risk-level recommendations is more sophisticated than most competitors' agent-specific capabilities.
- The approval workflow with action hashing, HMAC-signed tokens, and TTL expiry is a real governance primitive, not a toy.
- The screening event log with structured metadata (rule_ids, source_kind, trust_level, intended_action, policy_mode) is audit-ready data.

### 4. The market is consolidating, which creates demand for independent alternatives

- Parse's own blog post ("Why We Built an Independent Prompt Security API") correctly identifies that consolidation (Cisco/Robust Intelligence, etc.) creates customer anxiety about vendor lock-in and deprecation.
- Being the independent, agent-native alternative is a real positioning.

---

## E. The Pivot Thesis — Weak Arguments and Risks

### 1. Enterprise compliance sales cycles are 12-18 months. Parse has no enterprise sales motion.

The entire current GTM is self-service API keys and Stripe checkout. Enterprise compliance is sold through:
- 3-6 month POC cycles
- Security reviews and vendor risk assessments
- Procurement and legal negotiation
- SOC 2 / ISO 27001 evidence requirements
- Custom contracts and MSA negotiation

Parse has none of this infrastructure: no enterprise CRM, no security questionnaire response process, no SOC 2 report, no legal templates. Starting from zero, this is a 12-month runway burn before the first enterprise check.

### 2. CISOs buy from known vendors. Parse is unknown.

The incumbents (Lakera, Prompt Security, CalypsoAI, HiddenLayer) have raised $15-60M each specifically to build brand recognition with CISOs and security teams. They have analysts, marketing teams, conference presence, and analyst relations budgets. Parse is a solo/small-team product with a developer-facing blog. Breaking into CISO consciousness requires either (a) massive funding or (b) a bottom-up developer adoption flywheel that eventually reaches the CISO.

Option (b) is the hybrid model. Option (a) requires raising significant capital into a crowded market.

### 3. Current product-market fit is unproven.

The docs are revealing:
- `open-launch-evidence.md` says: "open launch remains **NOT_PROVEN** until sustained-load evidence is collected."
- `beta-onboarding-packet.md` targets "first 5-10 trusted beta testers."
- The `soft-launch-option-a.md` plan is focused on Agentic.Market listing — not enterprise sales.
- Screening metrics are flagged as "non-claimable generated tuning corpus" across the board.

This is a product in controlled beta with generated test metrics, not a product with proven market traction. Pivoting an unproven product to a harder market (enterprise) is higher risk than iterating on the current market (developers).

### 4. The cost of rebuilding for enterprise is massive and non-obvious.

The detection engine is ~30% of what an enterprise compliance product needs. The other 70% is:
- Multi-tenant organization model
- RBAC and identity management
- SSO/SAML/SCIM
- SIEM integration
- Compliance framework mapping and reporting
- Evidence export and audit pack generation
- Custom policy engine
- Agent inventory and registry
- Enterprise-grade SLAs, monitoring, incident response
- SOC 2 Type II certification ($50K-150K, 6-12 months)
- Enterprise support (24/7, SLA-backed)

This is a 12-18 month rebuild with a team that would need to grow from ~1-2 to ~8-12 people. The burn rate required before enterprise revenue materializes is significant.

### 5. The compliance market may commoditize before Parse arrives.

Cloud providers are already adding agent governance features (AWS Bedrock Guardrails, Azure AI Content Safety). If AWS/Azure/Google provide "good enough" compliance controls natively, the standalone market shrinks. Parse's differentiation (model-agnostic, agent-native) matters less if enterprises standardize on one cloud.

### 6. The "top-down regulation of agent activity" framing may not match how enterprises buy.

Enterprises don't buy "agent compliance platforms" — they buy:
- **Governance, Risk, and Compliance (GRC)** platforms (ServiceNow, Archer, MetricStream) and extend them
- **Cloud Security Posture Management** (Wiz, Prisma Cloud) and extend them
- **SIEM** platforms (Splunk, Sentinel, Datadog) and extend them

A standalone "agent compliance" product may be a category that doesn't exist yet. The risk is that agent compliance gets absorbed into existing GRC/CSPM/SIEM platforms before a standalone category forms.

---

## F. The Hybrid Option

**This is the recommended path.**

Parse should not choose between "developer API" and "enterprise compliance." It should do both in sequence:

### Phase 1: Double down on developer API (0-6 months)
- Complete open-launch readiness (the evidence packet in `open-launch-evidence.md`)
- Grow developer adoption through the GEO strategy already documented
- Add the organization model and SIEM forwarding as "Team" tier features
- Add evidence export as a "Pro" or "Team" feature
- Focus on: API calls/month growth, paying customer count, developer NPS

### Phase 2: Add compliance layer (6-12 months)
- Map detection to compliance frameworks (OWASP, NIST AI RMF, EU AI Act)
- Add the framework crosswalk as a feature
- Build `/v1/compliance/export` for evidence packs
- Add Cedar/OPA policy engine for custom rules
- Integrate WorkOS/Clerk for SSO as an enterprise add-on
- Position as "the compliance layer for agent security" — not "an enterprise compliance platform"

### Phase 3: Enterprise expansion (12-18 months)
- Only after Phase 2 proves demand, pursue SOC 2 Type II
- Add enterprise sales motion (dedicated rep, security questionnaire process)
- Add agent registry/inventory as a premium feature
- Price enterprise tier at $2K-10K/month

### Why hybrid works:
1. **The developer API is the wedge.** Developers adopt the API, integrate it into agents, and create pull for compliance features from inside the enterprise.
2. **No GTM abandonment.** The current developer GTM (Agentic.Market, MCP, x402, OpenAPI discovery) is still the right entry point. Compliance is the expansion.
3. **Revenue continuity.** $49/$199/month developer revenue funds development of compliance features. No need to raise capital immediately.
4. **Optionality.** If enterprise compliance doesn't materialize, the developer API business continues. If it does, Parse has the technical foundation to capture it.
5. **The codebase supports it.** The screening events, audit log, policy engine, and approval workflow are all already built. The hybrid is mostly a schema migration (Organization model), a reporting layer, and a positioning shift — not a rewrite.

### Why full pivot would fail:
1. Abandoning the developer GTM removes the bottom-up adoption engine that is Parse's only current distribution advantage.
2. Enterprise sales require capital, team, and time that Parse doesn't have yet.
3. The detection engine alone isn't enough for enterprise — the 70% build gap is real and expensive.
4. The market is crowded with well-funded incumbents who already have enterprise GTM.

---

## G. Pricing & Positioning

### Current Pricing (developer API)
| Tier | Price | Requests | Sandbox Exec |
|---|---|---|---|
| Free | $0 | Rate-limited | 5/hour |
| Pro | $49/mo | 10K | 50/hour |
| Team | $199/mo | 50K | 200/hour |
| Enterprise | Custom | Custom | Custom |

### Recommended Hybrid Pricing

| Tier | Price | Target | Key Features |
|---|---|---|---|
| Free | $0 | Developer discovery | All detection endpoints, rate-limited |
| Pro | $49/mo | Individual developers | 10K requests, sandbox execution, basic analytics |
| Team | $199/mo | Small teams (5-20 agents) | 50K requests, organization model, SIEM webhook forwarding, evidence export |
| Compliance | $999/mo | Mid-market compliance (50-200 agents) | Custom policies (Cedar/OPA), framework mapping reports, SSO (via WorkOS), agent registry, priority support |
| Enterprise | $5K-15K/mo | Large enterprises (500+ agents) | Dedicated infrastructure, custom SLAs, SOC 2 evidence pack, data residency, SAML/SCIM, 24/7 support |

### Positioning

**Current:** "Parse is a prompt protection API for AI agents."

**Evolved (hybrid):** "Parse is the agent security layer — from API to audit trail. Screen every agent interaction, enforce policy, and export compliance evidence."

The positioning should remain **API-first, developer-first** but add the compliance narrative as the expansion story. The blog already references compliance frameworks (OWASP, NIST AI RMF, EU AI Act) — this content should become more structured, with compliance landing pages and framework-specific guides.

**Do NOT reposition as "enterprise compliance platform."** That would be:
- Inaccurate (no enterprise features yet)
- Confusing to existing developer users
- An invitation to compete head-on with Lakera/Prompt Security/CalypsoAI (who have more money and enterprise GTM)

---

## H. Verdict

### HYBRID — Go with conditions.

**Do not pivot. Evolve.**

Parse has a genuine technical asset in the detection engine, trust pipeline, policy system, and audit infrastructure. This is the right foundation for an agent compliance product. But:

1. **The developer API must come first.** It is the wedge, the distribution channel, and the revenue engine. The codebase is purpose-built for API-first developer adoption (MCP, x402, OpenAPI, self-service keys). Abandoning this for enterprise-only is throwing away the only advantage Parse has.

2. **The compliance layer is the expansion, not the pivot.** Add Organization model → SIEM forwarding → framework crosswalk → evidence export → custom policies → SSO. This is a 6-12 month roadmap, not a strategic pivot.

3. **The market timing is real but not urgent for Parse specifically.** EU AI Act enforcement creates demand, but that demand flows to incumbents first. Parse needs the developer flywheel to create enterprise pull-through before enterprise demand matters.

4. **The biggest risk is not the pivot decision — it's execution capacity.** A solo founder or small team cannot build enterprise compliance features AND maintain the developer API AND do enterprise sales simultaneously. The hybrid requires sequencing: developer API first, compliance features second, enterprise GTM third.

5. **If forced to choose: stay with the developer API.** The compliance market is real but crowded and expensive to enter. The developer API market is less crowded (Pangea is the main comparable), growing fast (agent adoption is explosive), and matches Parse's current strengths (API-first, self-service, MCP/x402 native).

### Specific recommendations:

1. **Next 30 days:** Add `Organization` model to Prisma schema. Add org-level `ScreeningPolicy`. This is the single most important schema change for future compliance.

2. **Next 90 days:** Ship SIEM webhook forwarding (Splunk HEC, Datadog, generic webhook) as a Team tier feature. Ship `/v1/compliance/export` endpoint for time-bounded evidence reports.

3. **Next 6 months:** Publish compliance framework crosswalk (OWASP Top 10 LLM → Parse risk categories, NIST AI RMF → Parse controls). Add Cedar/OPA policy engine for custom rules.

4. **Next 12 months:** If compliance demand materializes from existing developer customers, add a dedicated compliance tier ($999/mo) and enterprise tier ($5K+/mo). Pursue SOC 2 Type II in parallel.

5. **Do NOT raise a large round to pursue enterprise compliance** unless 3+ enterprise design partners are signed. The market is too crowded to enter without validated demand.

---

## Appendix: Key Code Paths Referenced

| Component | File | Key Function/Export |
|---|---|---|
| Prompt security pipeline | `src/parse.ts` | `parsePrompt()` — 3-layer pipeline |
| Pattern detection | `src/lib/patterns/index.ts` | `INJECTION_PATTERNS` (100+ rules), `RISK_CATEGORIES` (9 categories) |
| Trust verification | `src/lib/trust-verification/orchestrator.ts` | `verifyTrust()` — 6-layer pipeline |
| Policy management | `src/routes/policy.ts` | `GET/PUT/DELETE /v1/policy`, `DEFAULT_POLICY`, `MAX_THRESHOLD_BY_TIER` |
| Screening analytics | `src/routes/screening-metrics.ts` | `GET /v1/screening/metrics` — aggregation queries |
| Agent trust API | `src/routes/agent-trust.ts` | `POST /v1/agent/trust/verify` |
| Approval workflow | `src/routes/approvals.ts` + `src/lib/approvals.ts` | HMAC-signed tokens, action hashing, TTL |
| Output screening | `src/routes/screen-output.ts` | `POST /v1/screen-output`, `analyzeOutputRisks()` |
| Exposure evaluation | `src/routes/exposure.ts` + `src/lib/exposure/evaluate.ts` | Policy verdicts for supply-chain findings |
| Audit logging | `src/lib/audit-log.ts` | `auditLog()`, `persistAuditEvent()` |
| Screening event persistence | `src/lib/screening-event-log.ts` | `buildScreeningEventData()`, `persistScreeningEventData()` |
| Scoring engine | `src/lib/scoring.ts` | `calculateRiskScore()` — weighted + correlated |
| Admin operations | `src/routes/admin.ts` | 2500+ lines of admin control plane |
| Billing | `src/routes/billing.ts` | Stripe subscriptions, usage metering |
| Data model | `prisma/schema.prisma` | `ApiKey`, `ScreeningPolicy`, `ScreeningEvent`, `AuditEvent`, `Subscription` |
| Product facts | `src/lib/product-facts.ts` | `PLAN_LIMITS`, `DETECTION_FACTS`, `X402_ENDPOINTS` |
