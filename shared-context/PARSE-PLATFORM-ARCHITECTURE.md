# Parse Platform Architecture

**Date:** 2026-03-01  
**Stack:** TypeScript, Next.js 14+, Node.js  
**Purpose:** AI-powered media analysis platform with agent services

---

## 🏗️ Application Layer (`src/`)

### Directory Structure

```
src/
├── agents/
│   ├── sandbox/
│   │   └── prompt-injection-detector.ts    # Empirical injection detection
│   └── ad-detector/
│       ├── pattern-analyzer.ts             # Ad pattern detection
│       ├── affiliate-detector.ts           # Affiliate link detection
│       └── __tests__/ad-detector.test.ts   # Test suite
├── app/
│   └── api/v1/
│       └── agents/
│           ├── [agent]/route.ts            # Dynamic agent endpoint
│           ├── prompt-injection-detect/    # NEW: Injection detection
│           └── ad-detector/                # NEW: Ad detection
├── lib/
│   ├── memory/
│   │   ├── search.ts                       # Unified search API
│   │   └── entity-extractor.ts             # Auto-entity extraction
│   └── x402/
│       ├── payment.ts                      # x402 payment protocol
│       ├── validation.ts                   # Payment validation
│       ├── mock-payment.ts                 # Mock for testing
│       └── __tests__/payment.test.ts       # Test suite
└── middleware/
    └── x402-payment.ts                     # Payment enforcement
```

---

## 🤖 Agent Services

### Existing Agents (Live)

| Agent | Endpoint | Status |
|-------|----------|--------|
| **extract** | `/api/v1/agents/extract` | ✅ Live |
| **fact-check** | `/api/v1/agents/fact-check` | ✅ Live |
| **bernays** | `/api/v1/agents/bernays` | ✅ Live |
| **deception** | `/api/v1/agents/deception` | ✅ Live |
| **steel-man** | `/api/v1/agents/steel-man` | ✅ Live |
| **persuasion** | `/api/v1/agents/persuasion` | ✅ Live |
| **context-audit** | `/api/v1/agents/context-audit` | ✅ Live |
| **fallacies** | `/api/v1/agents/fallacies` | ✅ Live |
| **takeaways** | `/api/v1/agents/takeaways` | ✅ Live |
| **evidence** | `/api/v1/agents/evidence` | ✅ Live |
| **synthesis** | `/api/v1/agents/synthesis` | ✅ Live |
| **rewrite** | `/api/v1/agents/rewrite` | ✅ Live |

### New Agents (In Development)

| Agent | Location | Status | ETA |
|-------|----------|--------|-----|
| **prompt-injection-detect** | `src/agents/sandbox/` | 🔄 Building | EOD |
| **ad-detector** | `src/agents/ad-detector/` | 🔄 Building | Tomorrow |

---

## 💰 Payment Integration

### x402 Payment Protocol

**Purpose:** Enable agent-to-agent autonomous payments

| Component | File | Status |
|-----------|------|--------|
| **Payment Creation** | `src/lib/x402/payment.ts` | ✅ Implemented |
| **Validation** | `src/lib/x402/validation.ts` | ✅ Implemented |
| **Middleware** | `src/middleware/x402-payment.ts` | ✅ Implemented |
| **Mock Testing** | `src/lib/x402/mock-payment.ts` | ✅ Implemented |
| **Tests** | `src/lib/x402/__tests__/` | ✅ Implemented |

**Configuration:**
```typescript
{
  payTo: 'parse@kurult.ai',
  amount: 19, // $0.19 per credit (Pro tier)
  currency: 'USD',
  description: 'Parse agent analysis',
  expiresInSeconds: 300
}
```

---

## 🔍 Memory Services

### Unified Search API

**File:** `src/lib/memory/search.ts`

**Features:**
- Single search across Neo4j + files + shared context
- Relevance scoring
- Weight-based ranking (Cognee-inspired)
- Snippet extraction

**Usage:**
```typescript
const results = await kurultaiSearch("prompt injection detector")
```

### Entity Extractor

**File:** `src/lib/memory/entity-extractor.ts`

**Features:**
- Auto-extract entities from memory files
- Create Neo4j nodes automatically
- Link entities with relationships
- Batch processing support

---

## 🛠️ Scripts & Automation

| Script | Purpose | Status |
|--------|---------|--------|
| `cron-health-monitor.sh` | Monitor 3 critical cron jobs | ✅ Active |
| `prune-memory.sh` | Weekly memory pruning | ✅ Active |
| `quick-commit.sh` | Git commit automation | ✅ Active |
| `hourly_reflection.sh` | Agent hourly reflections | ✅ Active |

---

## 📊 Operational Systems

| System | Status | Details |
|--------|--------|---------|
| **Hourly Reflections** | ✅ Active | Cron: `0 * * * *` |
| **Architecture Verification** | ✅ Active | Cron: `0 */12 * * *` |
| **Daily Goal Progress** | ✅ Active | Cron: `0 7 * * *` |
| **Cron Health Monitor** | ✅ Active | Every 15 minutes |
| **Memory Pruning** | ✅ Active | Weekly (Sunday 3 AM) |

---

## 📁 Documentation Files

### Parse Platform (14 files)

| File | Purpose |
|------|---------|
| `PARSE-AD-DETECTOR.md` | Ad detector design |
| `PARSE-AGENT-API-ANALYSIS.md` | Agent API capabilities |
| `PARSE-AGENT-SERVICES-IMPLEMENTATION.md` | Implementation plan |
| `PARSE-CONTENT-PACKAGE-1.md` | Launch content (3 threads, 2 posts) |
| `PARSE-CONTENT-WORKFLOW.md` | Content generation workflow |
| `PARSE-LAUNCH-ANNOUNCEMENT.md` | Launch announcement drafts |
| `PARSE-MONETIZATION.md` | Monetization strategy |
| `PARSE-PROMPT-INJECTION-SANDBOX.md` | Prompt injection design |
| `PARSE-REVENUE-DASHBOARD.md` | Revenue tracking |
| `PARSE-STRIPE-LIVE.md` | Stripe integration (live) |
| `PARSE-X402-INTEGRATION.md` | x402 payment design |
| `STRIPE-CONFIG.md` | Stripe configuration |
| `GOAL-PARSE-MONETIZATION.md` | $1500 MRR by Day 90 goal |
| `PARSE-AGENT-STATUS.md` | Agent services status |

### Kurultai Operations (4 files)

| File | Purpose |
|------|---------|
| `KURULTAI-ARCHITECTURE-GAP.md` | 6-agent architecture gap analysis |
| `KURULTAI-SYNC-PROTOCOL.md` | Real-time agent collaboration |
| `KURULTAI-SYNC-2026-03-01-10-00.md` | First sync transcript |
| `MOLTBOOK-PARSE-AGENT-POST.md` | Moltbook showcase post |

### Design & Planning (5 files)

| File | Purpose |
|------|---------|
| `PROMPT-INJECTION-IMPLEMENTATION.md` | Prompt injection implementation plan |
| `CLAUDE.md` | Claude Code lessons adopted |
| `CRITICAL_GAP_ASSESSMENT.md` | Gap assessment |
| `GAP_ANALYSIS_POST_PLAN.md` | Post-plan gap analysis |
| `GAP_FIX_STATUS.md` | Gap fix status |

---

## 📈 Revenue Status

| Metric | Current | Target |
|--------|---------|--------|
| **MRR** | $0 | $1,500 (Day 90) |
| **Paying Users** | 0 | 150 (Day 90) |
| **Days Remaining** | 89 | — |

**Content Ready:**
- Content Package #1 (3 X threads, 2 Reddit posts)
- Moltbook showcase post
- Cross-post variations

**Blocker:** Content not posted (awaiting human)

---

## 🚀 Next Steps

### Priority 1: Deploy New Agent Services
- [ ] Complete prompt injection detector (EOD)
- [ ] Complete ad detector (Tomorrow)
- [ ] Deploy x402 payments (Day 3)

### Priority 2: Launch Content
- [ ] Post Content Package #1
- [ ] Monitor engagement
- [ ] Iterate based on performance

### Priority 3: First Paying User
- [ ] Target: Day 7
- [ ] Strategy: Content → Traffic → Free signup → Paid conversion

---

*Parse is evolving from media analysis tool to full AI agent platform.*
