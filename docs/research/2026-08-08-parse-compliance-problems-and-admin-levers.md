---
type: analysis
status: active
updated: 2026-08-08
created: 2026-08-08
sources: 3
tags: [parse, compliance, governance, admin-dashboard, policy-levers, developers, ciso, rollout, brainstorm]
---

# Parse Compliance Expansion — Problem Brainstorm & Admin Dashboard Levers

> Compliance is a loop: someone writes a policy, humans and agents act, and the gap between the two is either invisible or controlled. Parse's expansion is about making that gap visible to developers first, controllable by enterprises second. This doc brainstorms the problems on both sides of that loop and designs the lever set an admin dashboard needs to close it.

---

## 1. What the repo already documents

Three prior research docs on this branch establish the foundation:

| Doc | What it establishes |
|---|---|
| [[2026-08-08-enterprise-ai-agent-problem-graph]] | 33 enterprise problem nodes across Security (S1–S13), Governance (G1–G6), Visibility (V1–V10). Root-cause analysis: **S10 (untrusted content) + V1 (no agent inventory) + S11 (shadow agents)** gate the entire graph. |
| [[2026-08-08-parse-enterprise-compliance-pivot-assessment]] | Verdict: **hybrid, not pivot**. Developer API is the wedge; compliance is the expansion layer built on existing screening/policy/audit/approval infrastructure. Phased: developer (0–6mo) → compliance layer (6–12mo) → enterprise GTM (12–18mo). |
| [[2026-08-08-parse-compliance-control-panel-build]] | What's built: Organization/AgentRegistry/PolicyRevision/SIEMConfig/ComplianceExport schema, 5-framework crosswalk (OWASP LLM, NIST AI RMF, EU AI Act, ISO 42001, SOC 2), SIEM forwarder (CEF/LEEF/JSON), `/v1/compliance/*` routes, and a 6-tab dashboard at `/dashboard/compliance`. |

**The gap this doc fills.** The problem graph is deliberately CISO-centric — it *explicitly excludes* developer experience ("Important but not an enterprise compliance concern"). But the rollout strategy is developers-first, which means the developer-side compliance problems ARE the product problems for the next two quarters. The control panel build record has one "Policy Levers" tab but no systematic lever inventory, no inheritance model, and no mapping from lever → problem → rollout phase. This doc supplies all three.

---

## 2. Framing: two policy authors, two actor types

Every compliance question Parse can answer fits a 2×2:

```
                      WHO WROTE THE POLICY?
                  Developer policy   Company policy
                  (my agent's rules) (org-wide rules)
                 ┌──────────────────┬──────────────────┐
   WHO   Human   │ "My teammate     │ "An employee     │
   ACTS? employee│  changed the     │  pasted customer │
                 │  prod threshold  │  PII into an     │
                 │  to debug"       │  unsanctioned    │
                 │                  │  agent"          │
                 ├──────────────────┼──────────────────┤
         Agent   │ "My agent called │ "A department's  │
                 │  a tool I never  │  agent emailed a │
                 │  approved"       │  contract owned  │
                 │                  │  by legal"       │
                 └──────────────────┴──────────────────┘
```

- **Developer phase** sells the left column: a developer sets rules for their own agents and needs to know the rules held — against their agent's behavior *and* against their teammates' config changes.
- **Enterprise phase** sells the right column: a CISO sets rules for the whole org and needs them enforced across employees and every agent those employees run.
- The center of the map is the **confused deputy**: an agent acting *on behalf of* an employee, holding the employee's credentials, doing something neither the developer's policy nor the company's policy would allow — while every individual system involved sees an "authorized" request. This is why agent compliance can't be solved by IAM, DLP, or CASB alone, and it's the cell where Parse's screening + trust verification + approval primitives are genuinely differentiated.

"Compliance" here means closing the loop for all four quadrants: **policy written → policy enforced at runtime → deviation detected → deviation attributable → evidence exportable.**

---

## 3. Developer-side problems (D-series)

The developer is anyone shipping an agent: solo hacker, startup team, or a platform team inside a bigger company. Their compliance subjects are their own agents, their own users' inputs, and their own teammates' configuration changes.

### Policy authoring & drift

- **D1 — A system prompt is not a policy.** The only "policy" most agents have is prose in a system prompt. Models drift from instructions, especially under injection pressure; "please never reveal the system prompt" is a wish, not a control. Developers have no way to express *enforceable* rules outside the model's goodwill. *(maps to G1, G2)*
- **D2 — No single choke point.** Agent frameworks call tools and LLMs directly from many call sites. Screening has to be hand-wired into each one; a single missed call site is an unscreened path, and nothing detects the omission. Coverage is asserted, never proven. *(G2)*
- **D3 — Environment drift.** Dev, staging, and prod policies diverge silently. A threshold relaxed to debug locally gets committed and ships. There is no diff, no promotion gate, no "prod is stricter than dev" invariant. *(new — no graph node; per-environment policy is a developer-native concern)*
- **D4 — Bypass creep.** Bypass codewords, allowlists, and `SCREENING=off` env flags added during development quietly become permanent. Nothing expires them, nothing reports them. Every mature codebase accumulates fossilized bypasses. *(G2; Parse already has bypass-with-expiry — the problem is surfacing and auto-expiring them)*
- **D5 — No policy history.** When an incident happens, the first question is "what policy was active at the time?" Without versioned policy with timestamps and actor attribution, that question is unanswerable. *(V2; PolicyRevision model addresses the storage side, not yet the surfacing)*

### Runtime behavior

- **D6 — Their users are the injection vector.** A developer's end users (and the content those users point the agent at) inject prompts. No individual developer can author and maintain 100+ detection patterns across encodings, homoglyphs, and paraphrase attacks — this is exactly the shared-infrastructure argument for Parse. *(S1, S10)*
- **D7 — Output is liability.** The agent may emit secrets, PII, another customer's data, or the system prompt itself — under the developer's brand and API key. Input screening alone covers half the pipe. *(S8; screen-output exists, egress defaults don't)*
- **D8 — Third-party tools are unvetted.** MCP servers and plugins are third-party code the agent trusts implicitly. Developers have no attestation, pinning, or approval flow — they `npm install` trust. *(S4, G3)*
- **D9 — Delegation dilutes policy.** Agent A (screened, policied) calls agent B (neither). Policy does not propagate across delegation; the weakest agent in the chain sets the real security level. *(S5; Parse's trust-verification pipeline is the primitive here)*
- **D10 — Model updates silently change compliance behavior.** A provider model bump changes what the agent will and won't do under identical policy. There's no compliance regression suite — no way to assert "the agent still refuses X" across model versions. *(new — no graph node; this is a developer CI concern)*

### Operations

- **D11 — The friction economics of screening.** Every enforcement layer adds latency and cost. When screening slows the demo, developers turn it off — and the moment of maximum risk (launch) is exactly when it's off. A compliance product's top competitor is `if (false)`. *(new — structural, see X2)*
- **D12 — False positives train people to ignore the tool.** A few bad blocks and the developer lowers the threshold to 9.9 or stops reading alerts. Precision is adoption. *(V4-adjacent)*
- **D13 — Can't reconstruct why the agent acted.** Logs capture the tool call, not the reasoning chain or the inputs that led to it. Post-incident, the developer cannot replay what the agent "saw." *(V2)*
- **D14 — Secrets end up in context.** Developers paste keys into prompts; agents carry secrets in memory across turns; screening events can accidentally *persist* the secret they caught. Detection without redaction converts a leak into a stored leak. *(S3, S8)*
- **D15 — Overrides leave no trace.** A developer overrides a block to ship a demo. No record, no expiry, no review. Compare D4: bypass creep is the config version; this is the human version. *(V2, V10)*
- **D16 — Agent actions are indistinguishable from human actions downstream.** The agent acts with the developer's (or employee's) credentials. GitHub, Gmail, and the database all log a *human* doing things a human never did. Attribution has to be captured at the agent boundary or it's lost forever. *(V1, V10, V2)*

---

## 4. CISO-side problems (C-series)

The CISO's compliance subjects are employees (using agents, sanctioned or not) and every agent running inside or on behalf of the org. Most of these extend graph nodes; the extensions here are the *compliance-loop* framing — not just "the risk exists" but "I cannot demonstrate control over it."

### Visibility — "I can't see it"

- **C1 — Shadow agents outnumber sanctioned ones.** Employees use personal ChatGPT/Claude accounts and homegrown agents for work tasks. Blocking fails (web interfaces); ignoring fails (data is leaving). The CISO's real starting inventory is unknown. *(S11, G6)*
- **C2 — No agent inventory, so no denominator.** Every compliance percentage needs a denominator ("100% of agents are screened" — out of *how many*?). Without a registry of agents, owners, tools, and data access, all coverage claims are undefined. *(V1)*
- **C3 — Can't prove a negative.** "Show me that no agent touched restricted data this quarter" requires *complete* interception coverage, not sampling. Partial deployment produces confident-looking dashboards that are silently wrong. *(V2, V3)*
- **C4 — Audit trails capture actions, not intent.** Existing logs show an API was called; they don't show the prompt chain, the injected content, or the trust context that caused it. Forensics and regulators both increasingly want the "why." *(V2)*

### Control — "I can't stop it"

- **C5 — Policy exists as PDF, not as enforcement.** The org has an AI acceptable-use policy; nothing in the runtime path evaluates it. Policies without a policy enforcement point are documentation. *(G1, G2)*
- **C6 — Every team uses a different agent stack.** LangChain here, CrewAI there, a custom framework in the data team. One policy cannot be applied uniformly; per-framework middleware is fragile and perpetually incomplete. *(G1)*
- **C7 — Employees route around sanctioned paths.** If the compliant path is slower than the personal-account path, employees take the personal-account path. Enforcement that ignores friction manufactures shadow usage. *(S11; the control-side twin of D11)*
- **C8 — Exceptions become the policy.** Business units demand exceptions; exceptions get granted under deadline pressure; nothing expires or re-reviews them. Two years later the exception list *is* the effective policy. *(G2; twin of D4 at org scale)*
- **C9 — Agents accumulate permissions and never shed them.** Each integration adds scopes; nothing prunes them. A compromised agent's blast radius grows monotonically. *(S7)*
- **C10 — Human-in-the-loop rubber-stamps at scale.** Route everything risky to approval and approvers click "yes" 200 times a day. Approval quality collapses exactly when the volume that justified buying an approval system arrives. *(V5, S12)*
- **C11 — Agents amplify insider misuse.** An employee who could never manually exfiltrate 40,000 records can instruct an agent to do it in minutes, through legitimate credentials. Intent detection at the instruction layer is the only place this is visible. *(S2 variant with a malicious principal, not a manipulated agent)*
- **C12 — No containment procedure for a compromised agent.** When an agent is injected or its memory poisoned, there is no kill switch, no quarantine, no forensic-preservation step, no blast-radius assessment. IR playbooks assume hosts and accounts, not agents. *(V7)*

### Accountability & evidence — "I can't prove it"

- **C13 — Nobody owns the harm.** Agent sends the wrong contract: is it the employee who prompted it, the developer who built it, the team that approved the tool, or the vendor? Regulators increasingly require named accountability; orgs have finger-pointing. *(V10)*
- **C14 — Framework evidence is assembled by hand.** EU AI Act Art. 12 (logging), Art. 14 (human oversight), NIST AI RMF, ISO 42001, SOC 2 — each audit cycle means weeks of manual evidence assembly from logs that weren't designed for it. *(G5, V6)*
- **C15 — Data subject rights don't reach agent memory.** A GDPR erasure request must cover conversation logs, agent memory, RAG stores, and screening-event payloads. Nobody can enumerate where a person's data landed, let alone delete it. *(V8)*
- **C16 — Prompt data crosses borders invisibly.** Which model provider, which region, what retention? Residency obligations attach to prompt/context data the moment an employee types customer information at an agent. *(S8, G4)*
- **C17 — The control plane is the crown jewel.** A screening layer sees every prompt in the org — making it the highest-value target and a single point of failure. CISOs will ask: what's *your* SOC 2, what's your fail posture, what do you retain? The compliance vendor must be more compliant than the customer. *(new — vendor-risk reflexive node)*
- **C18 — Agent risk can't be quantified for the board.** "How exposed are we to agent risk, trending which way?" has no defensible answer without normalized per-action risk scoring aggregated over time. CISOs buy what they can chart. *(V4, V9)*

---

## 5. Structural problems shared by both sides (X-series)

These aren't owned by either persona — they're properties of the compliance loop itself, and they drive dashboard design more than any individual D or C node.

- **X1 — The policy language gap.** Developers think in code and thresholds; CISOs think in frameworks and controls. A policy system must be *one* source of truth that renders both ways: as config/API for developers, as OWASP/NIST/EU-AI-Act control coverage for security teams. (Parse's framework crosswalk is exactly this bridge — the lever set below treats it as a first-class rendering, not a report.)
- **X2 — Friction economics decide adoption.** Both D11 and C7 are the same law: *if the compliant path is slower than the non-compliant path, the non-compliant path wins.* Every lever below must state its latency/UX cost; monitor-mode-first exists because of this law.
- **X3 — Who watches the watcher.** Fail-open leaks; fail-closed bricks production. Neither default is universally right, so failure posture must itself be a per-policy lever with an audited setting — and the enforcement layer's own availability/decisions must appear in the audit trail. *(pairs with C17)*
- **X4 — Velocity mismatch.** Agents and models change weekly; security review cycles run quarterly. Governance that gates on human review of every change loses to reality. The dashboard must make *continuous* enforcement cheap and reserve human gates for high-blast-radius changes.
- **X5 — The monitor→enforce chasm.** No org (and no developer) turns on blocking day one. The single most important product primitive is a *staged enforcement dial* — observe, then warn, then block — per policy, per environment, per agent, with data at each stage proving the next stage is safe (i.e., the false-positive rate visible *before* blocks are real).

---

## 6. The admin dashboard — lever inventory

### Design principles

Extending the six decisions in the control-panel build record:

1. **Every lever is a real API mutation** (already true: dashboard toggles call `PUT /v1/policy`). No decorative controls.
2. **Monitor-first default.** Every enforcement lever ships in `monitor` and must be explicitly dialed to `warn`/`enforce`. Never brick an agent on day one. *(X5, X2)*
3. **Pulling a lever is itself an audited event** — actor, before/after diff, reason string, expiry if temporary. Levers write to `PolicyRevision` + `AuditEvent`. *(D5, D15, C8)*
4. **Levers inherit down a scope chain** — org → team → agent → environment — with child overrides recorded and (in enterprise phase) permission-gated. Developers use the chain as `my key → my agents → prod/staging`. *(D3, C6)*
5. **Failure posture is a lever, not a constant.** Each enforcement point declares fail-open or fail-closed, visibly. *(X3)*
6. **Temporary is the default for exceptions.** Bypasses, overrides, and exceptions all carry mandatory TTLs and appear on a single "active holes" panel until they expire. *(D4, D15, C8)*

### Dashboard shape

The existing 6-tab panel (Overview, Audit Trail, Policy Levers, Frameworks, Evidence Export, SIEM) grows into:

```
┌─ PARSE COMPLIANCE CONSOLE ─────────────────────────────────────────────┐
│ Scope: [Org ▾] > [Team ▾] > [Agent ▾] > [Env: prod ▾]    Mode: ENFORCE │
├────────────────────────────────────────────────────────────────────────┤
│ Overview │ Agents │ Policies │ Approvals │ Audit │ Frameworks │ SIEM   │
├────────────────────────────────────────────────────────────────────────┤
│  ┌─ Enforcement Dial ──────────┐  ┌─ Active Holes ────────────────┐    │
│  │  MONITOR ──▶ WARN ──▶ BLOCK │  │ 2 bypasses (1 expires in 3h)  │    │
│  │  would-block last 7d: 14    │  │ 1 override (no expiry ⚠)      │    │
│  │  false-positive est: 0.4%   │  │ 3 unregistered agents seen    │    │
│  └─────────────────────────────┘  └───────────────────────────────┘    │
│  ┌─ Kill Switch ───────────────┐  ┌─ Risk Trend (board view) ─────┐    │
│  │ [Freeze agent] [Freeze all] │  │ ▂▃▂▅▃▂▁  blocked: 12  p95: 4.2│    │
│  └─────────────────────────────┘  └───────────────────────────────┘    │
└────────────────────────────────────────────────────────────────────────┘
```

The scope selector at top is principle 4 made visible; the enforcement dial is X5 made visible; "Active Holes" is principle 6 made visible.

### Lever families

Phases: **P1** = developer self-serve (Free/Pro), **P2** = team tier, **P3** = enterprise (Compliance/Enterprise tiers).

#### A. Ingress levers — what may enter an agent

| Lever | What it does | Problems | Phase |
|---|---|---|---|
| Per-source screening toggles | Screen user input / tool outputs / forwarded (agent-to-agent) messages / web & file content independently (extends existing `screenUserInput` etc.) | D2, D6, S10 | P1 |
| Auto-block threshold slider | 0–10 risk score cutoff, per scope + per environment (prod may be stricter than dev; promote-with-diff) | D3, D12 | P1 |
| Per-category thresholds | Tighter cutoffs for specific categories (e.g. block `data_exfiltration` ≥ 5 while `harmful_content` stays at 8) | D12, C18 | P1 |
| Enforcement dial (monitor/warn/block) | Staged rollout per policy + would-have-blocked counterfactual counts at each stage | X5, X2, D11 | P1 |
| Quarantine mode | Hold flagged inputs for review instead of hard allow/block; release or purge with receipt | C10, D12 | P2 |
| Encoding & obfuscation strictness | Dial for base64/homoglyph/zero-width handling: flag → strip → block | S1, S10 | P1 |
| Source trust levels | Assign trust tiers to input origins (own UI > known API > open web); thresholds keyed to tier | S10, D9 | P2 |

#### B. Action & egress levers — what an agent may do and emit

| Lever | What it does | Problems | Phase |
|---|---|---|---|
| Tool allowlist / blocklist | Per-agent permitted tool set, registry-driven; unknown tool → block or flag | D8, G3, C9 | P2 |
| Sandbox-required toggle | Code/shell execution only inside sandbox (extends existing `executeInSandbox`) | S6 | P1 |
| Action approval matrix | Grid: action type × data classification → allow / require approval / block (builds on existing approval workflow + HMAC tokens) | C5, C10, S12 | P2 |
| Egress destination allowlist | Domains/endpoints an agent may contact; everything else blocked or flagged | S2, C11 | P2 |
| Output screening toggles | PII redaction, secret detection, system-prompt-leak blocking on the egress side (extends `screen-output`) | D7, D14, S8 | P1 |
| Per-agent rate & spend caps | Calls/hour per tool, tokens/day, $ ceiling — throttle beats breach for runaway agents | C11, S12 | P2 |
| Data-classification routing | Restricted-class data → designated models/regions only, or block (uses existing `data_classification` metadata) | G4, C16 | P3 |

#### C. Identity & trust levers — who is acting

| Lever | What it does | Problems | Phase |
|---|---|---|---|
| Agent registration requirement | Dial: unregistered agents allowed → logged → blocked. Turns AgentRegistry from inventory into enforcement | C1, C2, V1 | P2 |
| Agent-to-agent trust threshold | Minimum trust-verification score before delegated calls are honored (uses existing 6-layer `verifyTrust`) | D9, S5 | P2 |
| On-behalf-of attribution requirement | Require `agent_id` + acting-user identity on every call, so downstream actions are attributable at the boundary | D16, C13, V10 | P2 |
| Credential scoping & TTL | Max lifetime/scopes for agent credentials; stale-permission report and one-click prune | C9, S3, S7 | P3 |
| Kill switch | Freeze one agent / team / all agents. Big red lever; every use audited; unfreeze requires reason | C12, V7 | P1 (per-key) / P3 (org-wide) |

#### D. Policy lifecycle levers — how rules change

| Lever | What it does | Problems | Phase |
|---|---|---|---|
| Policy versioning & rollback | Every change is a `PolicyRevision` with diff, actor, reason; one-click rollback | D5, C8 | P1 |
| Environment pinning & promotion | Separate dev/staging/prod policies; promote with diff review; invariant checks ("prod ≥ staging strictness") | D3 | P2 |
| Bypass issuance with mandatory expiry | Codeword/override creation *requires* TTL + reason; all live bypasses on the Active Holes panel | D4, D15 | P1 |
| Exception workflow | Request → approve → auto-expire → re-review; exceptions are data, not tribal knowledge | C8 | P3 |
| Compliance regression gate | Replay a golden set of should-block/should-allow prompts against policy + model version; run on model bump or policy change; CI-callable | D10, X4 | P2 |
| Policy-as-code export/import | Policy as versionable config (and later Cedar/OPA rules) so developers manage it in git like everything else | X1, C6 | P2/P3 |

#### E. Visibility & evidence levers — who sees what

| Lever | What it does | Problems | Phase |
|---|---|---|---|
| Audit trail with reasoning context | Filterable event log including matched rules, source kind, trust level, intended action — the "why," not just the "what" | C4, D13, V2 | P1 |
| SIEM forwarding config | Per-event-type forwarding to Splunk/Datadog/Elastic/Sentinel/webhook (built: CEF/LEEF/JSON) | C3, V3 | P2 |
| Alert routing rules | Severity × category → Slack/PagerDuty/email/none; per-scope, to fight fatigue with precision | D12, V3 | P2 |
| Log redaction level | Store full prompt / redacted / hash-only per data class — so the audit trail doesn't become the leak | D14, C17, S8 | P2 |
| Retention dial | Per-event-class retention windows aligned to framework requirements (e.g. EU AI Act Art. 12 logging) | C14, C16 | P3 |
| Evidence export | Time-bounded, framework-filtered, SHA-256-signed packs (built); scheduled auto-export per audit cycle | C14, V6 | P1 (manual) / P3 (scheduled) |
| Framework coverage view | Live control-coverage % per framework with per-control evidence links (built: crosswalk) — the CISO rendering of X1 | X1, G5 | P2 |
| Board risk view | Normalized risk-score trend, blocked-action counts, coverage denominator — chartable posture over time | C18, V9 | P3 |

#### F. Human-in-the-loop levers — when people decide

| Lever | What it does | Problems | Phase |
|---|---|---|---|
| Approval routing rules | Which action classes route to which approver roles/channels; TTL on pending approvals (extends existing approval workflow) | C10, V5 | P2 |
| Approval friction budget | Cap approvals/person/day + rubber-stamp detector (approval latency & uniformity stats) — protects decision quality | C10 | P3 |
| Four-eyes for high-blast-radius | Two distinct approvers for designated actions (prod data deletion, bulk sends, payments) | C10, S12 | P3 |
| Break-glass | Pre-authorized emergency bypass: instant, loud (alerts fire), auto-expiring, always audited | X3, C12 | P3 |

#### G. Enterprise governance levers (P3 — the second rollout wave)

| Lever | What it does | Problems |
|---|---|---|
| Org hierarchy & policy inheritance | Org → team → agent chains with explicit, permission-gated overrides (activates Organization model) | C5, C6, D3 |
| RBAC roles | Admin / policy-author / security-analyst / auditor / viewer; auditors get read-only evidence access | C17, G-layer |
| SSO/SAML/SCIM enforcement | Console access via corporate identity; deprovisioning propagates (buy: WorkOS/Auth0 per pivot assessment) | C17 |
| Shadow discovery & enrollment | Ingest network/endpoint signals of unsanctioned agent use; one-click "bring into registry" flow — discovery must end in enrollment, not just a report | C1, S11, G6 |
| Per-employee agent policy | Which employees/groups may run which agents with which tools — the HR-side twin of the agent-side levers | C11, right column of §2 |
| DSR console | Search a data subject across screening events/exports; erasure with tamper-evident receipt | C15, V8 |
| Data residency selector | Pin screening, storage, and LLM-analysis regions per org | C16 |
| Legal hold | Freeze retention/erasure for named scopes during litigation; overrides retention dial, visibly | C14-adjacent |
| Framework mode bundles | "EU AI Act mode" / "SOC 2 mode" presets that flip the required lever set on and show the residual gap | C14, X1 |

### The five levers that matter most

Ranked by problems-covered × adoption leverage, if only five ship first:

1. **Enforcement dial (monitor→warn→block)** — X5 is the chasm every customer must cross; the counterfactual "would-have-blocked" data is what makes crossing it safe. Without this, nothing else gets turned on.
2. **Auto-block threshold + per-category thresholds** — the core daily-driver control; already half-built (`autoBlockThreshold`, `MAX_THRESHOLD_BY_TIER`).
3. **Bypass/override with mandatory expiry + Active Holes panel** — D4/D15/C8 is the quiet killer on both sides of the market, and it's cheap to build on existing bypass support.
4. **Tool allowlist per agent** — the first lever that governs *actions* rather than *content*; it's what makes the AgentRegistry real and is the bridge from screening product to governance product.
5. **Kill switch** — rarely pulled, always demanded; C12/V7 is unanswered in every framework stack today, and it's the demo moment that sells the console.

---

## 7. Rollout sequencing — developers first, then enterprise

The wedge logic from the pivot assessment, made concrete per lever family:

### Phase P1 — Developer self-serve (now → +3 months; Free/Pro, $0–49)

Ship: per-source toggles, thresholds, enforcement dial, sandbox toggle, output screening, policy versioning/rollback, bypass-with-expiry, audit trail, manual evidence export, per-key kill switch.

- Sell it as **observability for your agent**, not compliance. The developer's question is "what did my agent just do and can I stop it doing that?" — D1–D16 language, zero framework language on the landing page.
- Success metric: % of active keys with the dial past `monitor` — that's the leading indicator that enforcement (the enterprise value) actually works.

### Phase P2 — Teams (+3 → +9 months; Team tier, $199)

Ship: environment pinning/promotion, agent registration dial, tool allowlists, trust thresholds, attribution requirement, quarantine, approval routing, SIEM forwarding, alert routing, redaction levels, compliance regression gate, framework coverage view, policy-as-code export.

- This is where the left column of §2 gets fully closed: teammates' changes are versioned, environments can't drift, agents are enumerable, actions are attributable.
- The **framework coverage view and SIEM forwarding are deliberately in P2, not P3**: they're the artifacts a developer forwards to their own security team — the internal-champion flywheel. The CISO's first contact with Parse should be a Splunk event and a coverage report that already exist.

### Phase P3 — Enterprise (+9 → +18 months; Compliance $999 / Enterprise $5K+)

Ship: org hierarchy + inheritance, RBAC, SSO/SCIM, org-wide kill switch, credential scoping, data-classification routing, exception workflow, four-eyes, break-glass, approval friction budget, scheduled evidence export, retention dial, residency, DSR console, shadow discovery + enrollment, per-employee policy, legal hold, framework mode bundles.

- Entry mechanism: **org claim**. A CISO discovers (via SIEM events, expense reports, or the coverage report a developer forwarded) that N teams already run Parse. Domain-verified claim converts those API-key-scoped views into one org scope with inheritance — land-and-expand where the landing already happened, and the enterprise sale starts with a populated dashboard instead of an empty one.
- Gate P3 spend on the pivot assessment's condition: 3+ design partners pulled from existing P1/P2 customers before building the long tail (residency, DSR, legal hold on demand-evidence only).

### What deliberately does NOT ship early

- **No org-wide anything in P1** — org scoping before a single developer loves the per-key view repeats the classic enterprise-too-early mistake called out in the pivot assessment.
- **No blocking defaults, ever** — every lever family enters life in monitor mode (X2/X5).
- **No custom policy DSL until P2/P3** — thresholds and toggles first; Cedar/OPA when real customers articulate rules the toggles can't express.
- **No shadow-discovery agents/endpoint software until P3** — it drags Parse into endpoint-security procurement and against C17 scrutiny before the SOC 2 story is ready.

---

## 8. Open questions

1. **Fail posture default** (X3): fail-open with loud alerting is the developer-friendly default, but is fail-closed mandatory for `enforce`-mode prod scopes? Likely needs to be per-scope, with fail-closed required by the EU-AI-Act framework bundle.
2. **Pricing the levers vs. pricing volume**: current tiers price request volume; the lever inventory suggests pricing *governance surface* (registry size, SIEM, RBAC) instead. Which axis carries the P2→P3 upgrade?
3. **Attribution spoofing** (D16/C13): `agent_id` and acting-user are caller-supplied metadata today. How far up the trust chain must Parse verify identity before attribution claims are audit-grade — and is that signed-SDK territory?
4. **Regression corpus ownership** (D10): does Parse ship and maintain the golden prompt set (a moat, but a liability if stale), or host customer-owned sets (safer, less differentiated)?
5. **The rubber-stamp detector** (C10): measuring approver behavior is powerful and invasive — is employee-level approval analytics a P3 feature or a reputational risk to defer?

---

## Next steps

1. Validate D-series against 5–10 beta developers (the beta packet's existing audience) — which three problems do they volunteer *unprompted*?
2. Wireframe the Overview + Policies tabs around the enforcement dial and Active Holes panel; usability-test the scope selector with a two-env solo developer.
3. Spec the five priority levers against existing code paths (`policy.ts`, `approvals.ts`, AgentRegistry, PolicyRevision) — most are extensions, not new systems.
4. Draft the org-claim flow (domain verification → key aggregation → inheritance bootstrap) as the P2→P3 bridge design doc.

---

*Authored 2026-08-08. Companion to [[2026-08-08-enterprise-ai-agent-problem-graph]], [[2026-08-08-parse-enterprise-compliance-pivot-assessment]], and [[2026-08-08-parse-compliance-control-panel-build]].*
