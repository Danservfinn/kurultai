---
type: analysis
status: active
updated: 2026-08-08
created: 2026-08-08
sources: 3
tags: [parse, enforcement, gateway, credential-custody, screening-receipts, mcp, choke-points, coverage-attestation, compliance, architecture]
---

# Parse Enforcement Architecture — Making Screening Non-Optional

> Today Parse is a voluntary API call: the developer chooses to call `parsePrompt()` before hitting the model, and nothing happens if they don't. That is problem D2/C5 from the problem brainstorm — coverage is asserted, never proven. This doc answers the question: **is there some way to enforce Parse usage in AI agents?** Yes — but only by controlling a choke point the agent cannot route around. Everything else is assurance, not enforcement.

---

## 1. The enforcement ladder

Enforcement mechanisms fall on a ladder. Each rung up trades integration cost for guarantee strength:

```
  POLITENESS   "please call the API"          ── docs, system prompts, convention
       │
  ASSURANCE    "we can tell when you didn't"  ── SDK wrappers, CI gates,
       │                                         coverage attestation
       │
  PREVENTION   "you physically can't skip it" ── credential custody + gateway,
                                                 egress pinning, resource-side
                                                 receipt verification
```

Parse today lives entirely on the politeness rung. The product opportunity is the top two rungs — and the rollout logic (developers first, enterprise second) maps cleanly onto them: **developers buy assurance; enterprises buy prevention.**

---

## 2. Choke point 1 — Credential custody + gateway mode (strongest)

Parse becomes an LLM forward proxy: agents are configured with an OpenAI/Anthropic-compatible base URL pointing at Parse, and **only the gateway holds the real provider keys**. Agents never possess credentials that reach a model directly, so screening cannot be skipped — enforcement stops being a policy and becomes physics.

Mechanics:

1. Org (or developer) enrolls provider keys into Parse's vault; agents receive Parse-issued virtual keys.
2. Agent SDKs need a one-line change: `base_url = "https://gw.parse.dev/v1"`.
3. Gateway screens input inline (existing 3-layer `parsePrompt()` pipeline), forwards to the provider, screens output on the return path (existing `analyzeOutputRisks()`), and persists the screening event — every call, by construction.
4. Enterprise hardening closes the side doors:
   - **Provider-side egress pinning** — Anthropic/OpenAI enterprise orgs support IP allowlisting; pin the org account to the gateway's IPs so even a leaked raw key is useless off-path.
   - **Network egress blocking** — corporate firewall/SWG blocks `api.openai.com`, `api.anthropic.com`, etc. for everything except the gateway. Pairs with the egress-destination-allowlist lever from the lever inventory.

Costs and risks (why this is not a free win):

- **Architectural shift** from "API you call" to "wire you sit on." Latency budget per call, availability SLA, and fail-open vs. fail-closed (X3) become existential product questions rather than dashboard settings.
- **Competitive lane change** — inline puts Parse against LLM gateways (LiteLLM, Portkey, Cloudflare AI Gateway, Kong AI). Differentiation must be the screening/policy/audit depth, not the proxying.
- **Blast radius of C17** — an inline control plane that holds provider keys and sees every prompt is the highest-value target in the org. Gateway mode raises the bar on Parse's own security story (SOC 2, key management, regional deployment) before enterprises will accept it.
- Nothing in the current codebase does this; it is a new runtime mode, not an extension of an existing route.

---

## 3. Choke point 2 — Resource-side verification: screening receipts (the inversion)

Instead of forcing agents *through* Parse, make the things worth protecting *demand proof of screening*. Parse issues a short-TTL, HMAC/asymmetrically-signed **verdict token bound to a hash of the prompt or canonicalized action**; internal APIs, MCP tool servers, databases, and mail gateways reject agent requests that don't carry a fresh, valid receipt. Unscreened agents don't get blocked by Parse — they find doors locked everywhere that matters.

Why this is the most Parse-native option: it is the **same primitive the approval workflow already ships** — HMAC-signed tokens, action canonicalization/hashing, TTL expiry (`src/lib/approvals.ts`). A screening receipt is that machinery applied to verdicts instead of human approvals:

```
  agent ──prompt──▶ Parse /v1/parse ──▶ verdict + receipt JWT
    │                                      (hash(action), score, policy_id,
    │                                       exp: +60s, sig)
    └──action + receipt──▶ internal API / MCP server
                              │
                              └── verifies sig, hash match, freshness,
                                  verdict=allow → executes
```

Properties:

- **Distributed enforcement, central policy.** Each protected resource is a policy enforcement point; Parse is the policy decision point. This is the OAuth/zero-trust shape applied to agent actions.
- **Directly attacks the confused deputy** (center cell of the 2×2 in the problem doc): a downstream service can finally distinguish "screened, policy-passing agent action" from "raw credential use," because the receipt binds verdict → specific action → time window.
- **Attribution becomes audit-grade** (answers open question 3 in the problem doc): receipts carry `agent_id` and acting-user identity signed by Parse, closing D16/C13.
- **Bootstrap problem is real**: receipts are worthless until resources verify them. Adoption path: ship verifier middleware (Express/FastAPI/MCP-server SDKs, ~50 lines each), start with the customer's highest-value internal API as the first locked door, expand outward. The verify side must be free and open source; the issue side is the product.

---

## 4. Choke point 3 — The action path: an MCP screening proxy

The model path is not the only wire — and for harm, the **tool/action path matters more**. A wrapping MCP server that proxies any other MCP server puts every tool call through screening regardless of which framework or model the agent uses:

1. Admin registers real MCP servers with the Parse MCP proxy; agents are configured to talk only to the proxy (enforceable by the same credential-custody trick: the proxy holds the real servers' credentials).
2. Every `tools/call` is screened pre-execution: tool-allowlist lever, action approval matrix, trust threshold, rate/spend caps — the action levers from the lever inventory get their enforcement point here.
3. Tool *outputs* are screened on the return path before re-entering the agent's context (the indirect-injection defense — S10/S1).

Because MCP is converging as the tool bus, this is **one integration that covers many frameworks** — a far better choke point than per-framework middleware, and it's the natural home for the exposure-evaluation capability (`/v1/exposure`) that already assesses MCP-server risk.

---

## 5. Rung 2 — Assurance mechanisms (developer phase)

These don't guarantee usage; they make omission **visible and expensive**. They are cheap, ship first, and create the data that later justifies prevention:

| Mechanism | What it does | What it fixes |
|---|---|---|
| **SDK interceptors** — `parse.wrap(openai_client)` | Wraps the client once; every call site inherits screening. One init line instead of hand-wiring N call sites. | D2 (missed call sites) within a codebase |
| **CI lint gate** | Static rule failing builds on unwrapped LLM client construction / raw fetches to provider domains; ships as eslint/ruff plugins | D2 at review time; X4 (continuous, not quarterly) |
| **Compliance regression gate** | Golden should-block/should-allow prompt set replayed in CI on policy or model change (lever D-family, already specced) | D10 (model bumps silently changing behavior) |
| **Coverage attestation** | Reconcile provider-side token/spend metrics against Parse-screened traffic; the delta **is** the unscreened surface, charted per agent per day | C3 ("can't prove a negative") — turns it into a number |

Coverage attestation deserves emphasis: it converts the enforcement question from binary ("are we enforcing?") into the single most persuasive dashboard stat — **"94% of your org's LLM traffic is screened; here are the three services producing the other 6%."** That number is what walks a P2 team customer into the P3 gateway conversation. It belongs on the console's Overview tab next to the enforcement dial.

---

## 6. Comparison and rollout mapping

| Mechanism | Guarantee | Who deploys it | Latency cost | Build size | Phase |
|---|---|---|---|---|---|
| SDK interceptors | Assurance | Developer | ~0 (async modes possible) | Small (per-language shims) | **P1** |
| CI lint gate | Assurance | Developer | 0 (build-time) | Small | **P1** |
| Coverage attestation | Assurance (measurement) | Developer/team | 0 (batch reconciliation) | Medium (provider metrics ingestion) | **P2** |
| Compliance regression gate | Assurance | Team | 0 (CI-time) | Medium | **P2** |
| Gateway mode (opt-in) | Prevention-lite (sticky convenience) | Developer/team | Inline: +screening latency | Large (new runtime mode) | **P2** |
| MCP screening proxy | Prevention (action path) | Team/enterprise | Inline on tool calls | Large | **P2–P3** |
| Credential custody + egress pinning | Prevention (model path) | Enterprise IT | Inline | Gateway + vault + network docs | **P3** |
| Screening receipts + verifier SDKs | Prevention (resource side) | Enterprise platform teams | ~0 on agent; verify cost on resource | Medium (extends approvals primitives) | **P3** |

Sequencing logic:

- **P1 ships assurance** — wrappers, CI gate. Sell: "never miss a call site again."
- **P2 ships opt-in gateway + coverage attestation.** Developers adopt the gateway for convenience (one URL swap, keys managed, dashboards free); stickiness comes as a side effect. Attestation quantifies the remaining gap.
- **P3 turns the same gateway into hard enforcement** — credential custody, egress pinning, receipts for internal services, MCP proxy fleet-wide. The org-claim flow (problems-and-levers doc §7) is the moment the opt-in wiring flips to mandatory: the CISO inherits an already-deployed gateway and dials it from "available" to "required."

New dashboard levers this implies (extending the lever inventory):

| Lever | Family | Phase |
|---|---|---|
| Gateway required (per scope: off → available → required) | Identity & trust | P3 |
| Receipt required (per registered resource) | Action & egress | P3 |
| Coverage attestation panel + unscreened-surface alerting | Visibility & evidence | P2 |
| Gateway fail posture (fail-open with loud alerts / fail-closed) per scope | Policy lifecycle | P2 |

---

## 7. Honest gaps

- **Employees on web UIs.** None of the above touches an employee pasting data into a personal ChatGPT/Claude browser session. That is CASB/SWG/enterprise-browser territory (S11/C1). Parse should integrate signals from those tools in P3 shadow discovery — not pretend to be one.
- **Fully self-hosted models.** An agent running a local model with local tools transits nothing Parse controls. Receipts are the only lever with reach here (its *actions* against org resources can still demand proof), which is another argument for the receipt architecture.
- **A determined insider developer** can stand up unscreened side channels. Assurance (attestation deltas) detects the drift; prevention narrows it; nothing eliminates it. The claim Parse can honestly make is "screened by default, bypass visible," not "bypass impossible."

---

## 8. Open questions

1. **Gateway fail posture default** — fail-open with loud alerting is developer-friendly; fail-closed is what "enforce" means to an auditor. Per-scope lever with fail-closed mandated by the EU-AI-Act framework bundle? (Continues X3 and open question 1 of the problems doc.)
2. **Inline latency budget** — what p95 overhead is acceptable before gateway mode self-defeats via X2 (friction → route-around)? Pattern+structural phases are fast; the LLM semantic phase (Phase 3) likely needs to be async/sampled in gateway mode.
3. **Receipt signing scheme** — HMAC (shared-secret, matches current approvals code) vs. asymmetric (verifiers hold only public keys — safer for distributed verification, C17-friendlier). Likely: asymmetric for receipts, keep HMAC for internal approval tokens.
4. **Who verifies first** — receipts need a flagship verifier integration to prove the pattern. Candidate: the MCP proxy itself (it can demand receipts on every tool call), making choke points 2 and 3 one product motion.
5. **Gateway competitive posture** — partner with existing LLM gateways (Parse as their screening plugin) vs. compete head-on? Partnering reaches enforcement faster with less infra risk and keeps Parse in its differentiated layer; competing owns the choke point outright.

---

## Next steps

1. Spec `parse.wrap()` interceptor SDKs (TS + Python) and the CI lint rule — P1-sized, immediately shippable.
2. Prototype coverage attestation against one provider (Anthropic usage API vs. screening-event counts) to validate the reconciliation math.
3. Design doc for receipt format (claims, TTL, signing, verifier SDK surface) as an extension of `src/lib/approvals.ts` primitives.
4. Decide gateway build-vs-partner (open question 5) before any inline work begins — it gates the P2 roadmap's largest line item.

---

*Authored 2026-08-08. Companion to [[2026-08-08-parse-compliance-problems-and-admin-levers]], [[2026-08-08-enterprise-ai-agent-problem-graph]], [[2026-08-08-parse-enterprise-compliance-pivot-assessment]], and [[2026-08-08-parse-compliance-control-panel-build]].*
