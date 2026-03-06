# Parse for Agents — Vision A Research Summary

> Generated: 2026-03-05 | Source: Multi-location codebase search

---

## 1. What Vision A Is

"Parse for Agents" is an **API-first prompt evaluation platform** designed for AI agents and developers. It positions itself as "the gate between 'I wrote a prompt' and 'I deployed a prompt'."

**Core value proposition:** Test prompts in isolated Docker sandboxes before production deployment, returning multi-dimensional scores across safety, quality, cost, and latency.

**Competitive niche:** Fills the gap between eval frameworks (PromptFoo, Braintrust) and sandbox runtimes (E2B, Modal) — the only platform combining eval + sandboxing + payment in one agent-first API.

**Primary documentation:**
- Vision: `/Users/kublai/.openclaw/agents/main/projects/parse-for-agents/VISION.md`
- API Spec: `/Users/kublai/projects/parse-github/SPEC-parse-for-agents.md`
- Implementation Plan: `/Users/kublai/projects/parse-github/PARSE_FOR_AGENTS.md`

---

## 2. Current Parse Architecture

### Stack
- **Framework:** TypeScript, Next.js 14+, Node.js
- **Deployment:** Railway (`parsethe.media`)
- **Payments:** Stripe (products live) + x402 agent-to-agent protocol
- **LLM Provider:** OpenRouter (integrated and live)

### Live Agents (12)
`extract`, `fact-check`, `bernays`, `deception`, `persuasion`, `context-audit`, `fallacies`, `takeaways`, `evidence`, `synthesis`, `rewrite`, `steel-man`

### In-Development Agents (2)
- **Prompt Injection Detector** — behavioral sandbox testing, not pattern matching
- **Ad Detector** — detects promotional/advertising content in LLM outputs

### Current Agent API
- **Endpoint:** `POST /api/v1/agents/[agent]`
- **Status:** Deployed, available to Max tier subscribers
- **Cost:** 1 credit per agent execution
- **Security:** URL validation (SSRF), input validation (SQL/XSS), API auth with scopes
- **Known gap:** Prompt injection detection (marked VULNERABLE)

### Monetization Infrastructure
| Tier | Price | Analyses/mo | Stripe Product ID |
|------|-------|-------------|-------------------|
| Free | $0 | 5 | — |
| Pro | $19 | 100 | `prod_TzYDf31wbMUQ2P` |
| Team | $49 | 1,000 | `prod_TzYDwqeHVD1xeF` |
| Max | $99 | 500 + API | `prod_TpCdvApqDBxJQg` |
| Enterprise | $499 | Unlimited | — |

**Revenue targets:** First paying user by Day 7 → $500 MRR by Day 30 → $1,500 MRR by Day 90

---

## 3. Recommended Implementation Approach

Based on existing plans and implementation status:

### Phase 1: Core Evaluation API (Priority: HIGH)
- Implement `POST /v1/evaluate` — submit prompt + test cases, get job ID
- Implement `GET /v1/evaluate/{id}` — retrieve evaluation results
- Response includes: quality (0-1), safety flags, latency, cost estimates, token counts
- Authentication via bearer tokens (`pfa_live_*` / `pfa_test_*` prefixes)

### Phase 2: Agent Security Services (Priority: HIGH)
- **Prompt Injection Detector:** Sandbox container → Monitor behavior → Score risk → ALLOW/REVIEW/BLOCK
  - Files: `agents/sandbox/prompt-sandbox.ts`, `test-harness.ts`, `risk-scorer.ts`
- **Ad Detector:** Pattern analysis + sandbox follow-up testing → Ad score 0-1
  - Files: `agents/ad-detector/`

### Phase 3: x402 Payment Integration (Priority: MEDIUM)
- Enable autonomous agent-to-agent payments
- Flow: Agent request → HTTP 402 + x402 config → Agent sends payment proof → Process
- Middleware: `withX402Payment()` wrapper for API routes
- Pricing: $0.19/credit (Pro tier)

### Phase 4: Scale & Monetize (Priority: MEDIUM)
- Stripe webhook configuration (awaiting setup)
- Content marketing push (packages already written)
- Product Hunt launch
- Partnership outreach

---

## 4. Existing Code & Assets That Can Be Reused

### Production Codebase
| Location | Contents |
|----------|----------|
| `/Users/kublai/projects/parse-github/` | Full GitHub repo with implementation |
| `/Users/kublai/projects/parsethe.media/` | Live production deployment |
| `/Users/kublai/projects/parse-for-agents/` | New dedicated product project |

### Agent Service Specs (Ready to Implement)
| File | Purpose |
|------|---------|
| `PARSE-PROMPT-INJECTION-SANDBOX.md` | Complete injection detector design |
| `PARSE-AD-DETECTOR.md` | Complete ad detector design |
| `PARSE-X402-INTEGRATION.md` | x402 payment middleware spec |
| `PARSE-AGENT-SERVICES-IMPLEMENTATION.md` | Full implementation roadmap |

### API Specification
- `SPEC-parse-for-agents.md` — Complete v0.1.0-draft API spec (~150KB) with authentication, endpoints, response formats, error codes

### Marketing Content (Ready to Post)
- `PARSE-LAUNCH-ANNOUNCEMENT.md` — Reddit/Twitter/Product Hunt templates
- `MOLTBOOK-PARSE-AGENT-POST.md` — 14-agent showcase
- `PARSE-CONTENT-PACKAGE-1.md` — Ready-to-post threads

### Infrastructure
- Railway deployment configured
- OpenRouter integration live
- Stripe products created with product IDs
- 12 agents already deployed and operational

---

## 5. Current Blockers (from Status Doc)

- No account access (social media posting)
- No analytics access
- No email access
- Stripe webhook configuration pending
- Prompt injection detection not yet implemented (security gap)

---

## Key Insight

The foundation is largely built. The path from current state to "Parse for Agents" Vision A is primarily:
1. **Build the evaluation API layer** on top of existing agent infrastructure
2. **Add the two security agents** (injection + ad detection)
3. **Wire up x402 payments** for agent-to-agent commerce
4. **Activate monetization** (Stripe webhooks + marketing push)

The existing 12 agents, Railway deployment, and Stripe products represent significant reusable infrastructure.
