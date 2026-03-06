# x402 Payment System Design — Parse for Agents

**Date:** 2026-03-05 (Updated)
**Status:** DESIGN COMPLETE — Ready for Implementation
**Prior Art:** Horde-Brainstorming diverge/evaluate/converge analysis (2026-03-05)
**Author:** Kublai

---

## 1. Executive Summary

Parse for Agents needs autonomous agent payments. The **x402 protocol** (HTTP 402 Payment Required) is the open standard for agent-to-agent payments, co-founded by Coinbase and Cloudflare, processing 100M+ payments with 156K weekly transactions.

This document designs a **tiered per-call payment system** using the official `@x402/hono` SDK with USDC stablecoin settlement on Base L2.

**Why x402 over Stripe for agent API:**
- Agent-native: No accounts, no signup — pay per request autonomously
- Direct SDK match: `@x402/hono` exists for our exact framework
- Micropayments: $0.005 per chat message with sub-cent network fees
- Protocol standard: Backed by Coinbase, Cloudflare, Stripe; integrated with Google AP2

The main Parse platform (parsethe.media) keeps Stripe for human subscriptions. Parse for Agents uses x402 for machine-to-machine payments. Both coexist.

---

## 2. x402 Protocol Overview

### What Is x402?

x402 activates the long-reserved HTTP 402 "Payment Required" status code for instant stablecoin micropayments over HTTP. Launched May 2025 by Coinbase, governed by the neutral x402 Foundation (co-founded with Cloudflare, September 2025).

### Three Roles

```
┌──────────┐     ┌─────────────────┐     ┌──────────────┐
│  CLIENT   │────>│  RESOURCE SERVER │────>│  FACILITATOR  │
│  (Agent)  │<────│  (Parse API)     │<────│  (x402.org)   │
└──────────┘     └─────────────────┘     └──────────────┘
```

1. **Client** (AI Agent): Pays per request with signed USDC transfer
2. **Resource Server** (Parse for Agents): Returns 402 with price, verifies payment
3. **Facilitator** (x402.org / Coinbase CDP): Verifies signatures, settles on-chain

### Supported Networks

| Network | Chain ID | Tokens | Use Case |
|---------|----------|--------|----------|
| Base (Coinbase L2) | eip155:8453 | USDC | **Production (recommended)** |
| Base Sepolia | eip155:84532 | USDC | Development/testing |
| Ethereum Mainnet | eip155:1 | USDC, USDT | High-value transactions |
| Solana | solana:mainnet | USDC | Alternative network |

### SDK Ecosystem

| Package | Purpose | Relevance |
|---------|---------|-----------|
| `@x402/hono` (v2.3.0) | Hono middleware | **Direct fit** — our framework |
| `@x402/core` | Core protocol types | Required dependency |
| `@x402/evm` | EVM chain support | For Base/Ethereum payments |
| `@x402/fetch` | Client-side fetch wrapper | For agent documentation |
| `@x402/paywall` | Payment UI component | Optional dashboard widget |

Also available: Python SDK (`x402`), Go SDK (`github.com/coinbase/x402/go`).

---

## 3. Pricing Model Selection

### Options Evaluated

| Option | x402 Fit | Agent Autonomy | Simplicity | Score |
|--------|----------|----------------|------------|-------|
| A: Per-Call Fixed | 10 | 9 | 9 | 8.15 |
| B: Per-Token | 3 | 7 | 4 | 5.55 |
| C: Subscription Tiers | 1 | 2 | 3 | 3.35 |
| D: Credit Packs | 5 | 6 | 5 | 5.75 |
| E: Hybrid Free+Paid | 7 | 8 | 6 | 6.90 |
| **F: Tiered Per-Call** | **10** | **9** | **8** | **8.45** |

### Winner: Tiered Per-Call Pricing + Free Tier Fallback

Agents choose depth/quality via request parameters. Price varies by endpoint and depth. Free tier via API keys continues working for evaluation and testing.

### Pricing Table (USDC on Base L2)

| Endpoint | Depth/Mode | Price | LLM Cost | Margin |
|----------|-----------|-------|----------|--------|
| `POST /v1/analyze` | quick (3 agents) | $0.01 | ~$0.003 | 70% |
| `POST /v1/analyze` | standard (7 agents) | $0.05 | ~$0.01 | 80% |
| `POST /v1/analyze` | deep (10 agents) | $0.15 | ~$0.03 | 80% |
| `POST /v1/evaluate` | default | $0.01 | ~$0.002 | 80% |
| `POST /v1/evaluate` | with test_inputs | $0.005/input | ~$0.001 | 80% |
| `POST /v1/chat` | per message | $0.005 | ~$0.001 | 80% |
| `GET /v1/analyze/:id` | — | FREE | $0 | — |
| `GET /v1/models` | — | FREE | $0 | — |
| `GET /v1/pricing` | — | FREE | $0 | — |

### Revenue Projection (Conservative)

```
100 agents × 50 calls/day × $0.02 avg = $100/day = ~$3,000/month
```

An agent running 1,000 standard analyses/month pays $50. Well within typical agent operational budgets.

---

## 4. Architecture

### System Architecture

```
                    Parse for Agents Payment Architecture
                    =====================================

┌─────────────────────┐
│   AI AGENT CLIENT    │
│  (Claude, GPT, etc.) │
│  Has: Crypto wallet   │
│  Uses: @x402/fetch    │
└───────┬─────────────┘
        │
        │  POST /v1/analyze  (no payment)
        v
┌─────────────────────────────────────────────────────────┐
│                 PARSE FOR AGENTS (Hono)                   │
│                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │ x402 Middleware│─>│ Auth Middleware│─>│ Route Handler   │ │
│  │ (@x402/hono) │  │ (existing)    │  │ (/v1/analyze)  │ │
│  └──────┬───────┘  └──────────────┘  └────────────────┘ │
│         │                                                 │
│         │ Returns 402 Payment Required                    │
│         │ with pricing + network + payTo address          │
└─────────┼─────────────────────────────────────────────────┘
          v
┌─────────────────────┐
│   AI AGENT CLIENT    │
│                       │
│  1. Signs USDC        │
│     transfer on Base  │
│  2. Retries with      │
│     X-PAYMENT header  │
└───────┬─────────────┘
        │
        │  POST /v1/analyze  (with X-PAYMENT header)
        v
┌─────────────────────────────────────────────────────────┐
│                 PARSE FOR AGENTS (Hono)                   │
│                                                           │
│  x402 Middleware:                                         │
│    1. Extract X-PAYMENT header                           │
│    2. POST /verify to Facilitator ─────────────┐         │
│    3. Receive { valid: true }     <────────────┤         │
│    4. Process request (call LLM)               │         │
│    5. POST /settle to Facilitator ─────────────┤         │
│    6. Return 200 + results + txHash            │         │
│                                                 v         │
│                                    ┌──────────────────┐  │
│                                    │  FACILITATOR      │  │
│                                    │  x402.org         │  │
│                                    │  - /verify        │  │
│                                    │  - /settle        │  │
│                                    └────────┬─────────┘  │
│                                             v            │
│                                    ┌──────────────────┐  │
│                                    │  Base L2 (USDC)   │  │
│                                    │  On-chain settle  │  │
│                                    └──────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

### Payment Flow Sequence

```
Agent                    Parse API              Facilitator           Base L2
  │                         │                       │                     │
  │  POST /v1/analyze       │                       │                     │
  │  (no payment header)    │                       │                     │
  │────────────────────────>│                       │                     │
  │                         │                       │                     │
  │  402 Payment Required   │                       │                     │
  │  PAYMENT-REQUIRED:      │                       │                     │
  │  { scheme: "exact",     │                       │                     │
  │    price: "$0.05",      │                       │                     │
  │    network: "base",     │                       │                     │
  │    payTo: "0x..." }     │                       │                     │
  │<────────────────────────│                       │                     │
  │                         │                       │                     │
  │  Agent signs USDC       │                       │                     │
  │  transfer (EIP-3009)    │                       │                     │
  │                         │                       │                     │
  │  POST /v1/analyze       │                       │                     │
  │  X-PAYMENT: {signed}    │                       │                     │
  │────────────────────────>│                       │                     │
  │                         │                       │                     │
  │                         │  POST /verify         │                     │
  │                         │  { payment payload }  │                     │
  │                         │──────────────────────>│                     │
  │                         │                       │                     │
  │                         │  { valid: true }      │                     │
  │                         │<──────────────────────│                     │
  │                         │                       │                     │
  │                         │  [Process request —   │                     │
  │                         │   7 LLM calls for     │                     │
  │                         │   standard depth]     │                     │
  │                         │                       │                     │
  │                         │  POST /settle         │                     │
  │                         │  { payment payload }  │                     │
  │                         │──────────────────────>│                     │
  │                         │                       │  Execute transfer   │
  │                         │                       │────────────────────>│
  │                         │                       │                     │
  │                         │  { settled: true,     │                     │
  │                         │    txHash: "0x..." }  │                     │
  │                         │<──────────────────────│                     │
  │                         │                       │                     │
  │  200 OK                 │                       │                     │
  │  { data: {results},     │                       │                     │
  │    payment: {txHash} }  │                       │                     │
  │<────────────────────────│                       │                     │
```

### Dual Access Model

```
Incoming Request
      │
      v
  Has X-PAYMENT header?
   ├── YES ──> Verify via facilitator ──> Process (no rate limit)
   │
   └── NO ──> Has API key (Authorization / ?api_key)?
               ├── YES ──> Validate key + scope ──> Rate-limited processing
               │
               └── NO ──> Return 402 Payment Required
                           { x402 pricing + API key generation URL }
```

| Access Method | Auth | Rate Limit | Pricing | Best For |
|---------------|------|------------|---------|----------|
| **Demo API Key** | Bearer token | 30/min | Free (5/day) | Testing |
| **Generated API Key** | Bearer token | 60/min | Free (limited) | Development |
| **Master API Key** | Bearer token | 1000/min | Free (unlimited) | Admin/internal |
| **x402 Payment** | X-PAYMENT header | None | Per-call USDC | Production agents |

---

## 5. Implementation Plan

### Phase 1: Core x402 Integration (Week 1)

#### 1.1 Install Dependencies

```bash
cd /Users/kublai/projects/parse-for-agents
npm install @x402/hono @x402/core @x402/evm
```

#### 1.2 Create Payment Configuration

**New file:** `src/x402.ts`

```typescript
import { paymentMiddleware, x402ResourceServer } from "@x402/hono";
import { ExactEvmScheme } from "@x402/evm/exact/server";
import { HTTPFacilitatorClient } from "@x402/core/server";

const PARSE_WALLET = process.env.X402_PAY_TO_ADDRESS!;
const FACILITATOR_URL = process.env.X402_FACILITATOR_URL || "https://facilitator.x402.org";
const NETWORK = process.env.X402_NETWORK || "eip155:8453"; // Base mainnet

const facilitatorClient = new HTTPFacilitatorClient({
  url: FACILITATOR_URL,
});

export const resourceServer = new x402ResourceServer(facilitatorClient)
  .register(NETWORK, new ExactEvmScheme());

export const paymentRoutes = {
  "POST /v1/analyze": {
    accepts: [{
      scheme: "exact",
      price: "$0.05",           // Standard depth default
      network: NETWORK,
      payTo: PARSE_WALLET,
    }],
    description: "Media credibility analysis",
  },
  "POST /v1/evaluate": {
    accepts: [{
      scheme: "exact",
      price: "$0.01",
      network: NETWORK,
      payTo: PARSE_WALLET,
    }],
    description: "Prompt safety and quality evaluation",
  },
  "POST /v1/chat": {
    accepts: [{
      scheme: "exact",
      price: "$0.005",
      network: NETWORK,
      payTo: PARSE_WALLET,
    }],
    description: "Chat with Parse AI assistant",
  },
};

export const x402Payment = paymentMiddleware(paymentRoutes, resourceServer);
```

#### 1.3 Integrate into App

**Modify:** `src/app.ts`

```typescript
import { x402Payment } from "./x402";

// Apply x402 middleware BEFORE auth on paid routes
// x402 handles 402 response and payment verification
// If payment valid: sets flag, passes through to handler
// If no payment: falls through to existing API key auth
app.use("/v1/analyze", x402Payment);
app.use("/v1/evaluate", x402Payment);
app.use("/v1/chat", x402Payment);
```

#### 1.4 Modify Auth Middleware

**Modify:** `src/auth.ts`

Add x402 bypass logic — if x402 middleware already validated payment (indicated by a context variable), skip API key requirement:

```typescript
// In auth middleware:
// Check if x402 payment was validated by upstream middleware
const x402Paid = c.get("x402Payment");
if (x402Paid) {
  // Payment verified — allow through without API key
  await next();
  return;
}
// Otherwise, proceed with existing API key validation...
```

#### 1.5 Dynamic Pricing for Analysis Depth

x402 middleware runs before body parsing, so depth is unknown at price time.

**Solution:** Default price is $0.05 (standard). For quick depth ($0.01), overpayment accepted — agent pays $0.05 for a $0.01 service (can be refunded via custom logic later). For deep depth ($0.15), if $0.05 was paid, return 402 with updated price.

Alternatively, implement depth as a query parameter: `POST /v1/analyze?depth=deep` so x402 middleware can read it from the URL and apply correct pricing.

#### 1.6 Environment Variables

Add to `.env.example` and Railway:

```bash
# x402 Payment Configuration
X402_PAY_TO_ADDRESS=0x...                       # Parse USDC wallet on Base
X402_FACILITATOR_URL=https://facilitator.x402.org
X402_NETWORK=eip155:8453                        # Base mainnet
X402_ENABLED=true                               # Feature flag
```

### Phase 2: Payment Tracking & Reporting (Week 2)

#### 2.1 Payment Ledger

**New file:** `src/payment-ledger.ts`

In-memory ledger (matching existing pattern) with periodic log flush:

```typescript
interface PaymentRecord {
  txHash: string;
  payer: string;           // Wallet address
  amount: string;          // USDC amount
  endpoint: string;
  depth?: string;
  timestamp: Date;
  network: string;
  status: "verified" | "settled" | "failed";
}
```

#### 2.2 New Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET /v1/pricing` | None | Return pricing table with wallet address |
| `GET /v1/payments/stats` | Admin | Revenue metrics, top payers, volume |

#### 2.3 Dashboard Updates

Update `src/dashboard.ts`:
- x402 payment status indicator
- Revenue metrics section
- Code examples for agent integration (TypeScript, Python, curl)

### Phase 3: Production Launch (Week 3)

#### 3.1 Wallet Setup

1. Create Coinbase Smart Wallet for Parse on Base
2. Configure to receive USDC
3. Set up balance monitoring / alerts

#### 3.2 Testnet First

1. Deploy with `X402_NETWORK=eip155:84532` (Base Sepolia testnet)
2. Test with `purl` CLI tool: `npm install -g @x402/purl`
3. Verify full flow: 402 -> payment -> verify -> settle -> 200
4. Switch to mainnet after validation

#### 3.3 Error Handling

| Status | Code | Meaning |
|--------|------|---------|
| 402 | PAYMENT_REQUIRED | No payment provided |
| 402 | PAYMENT_INSUFFICIENT | Amount too low for depth |
| 402 | PAYMENT_EXPIRED | Signature expired |
| 402 | PAYMENT_INVALID | Verification failed |
| 402 | PAYMENT_NETWORK | Unsupported network/token |
| 503 | FACILITATOR_UNAVAILABLE | Facilitator unreachable (Retry-After) |
| 500 | SETTLEMENT_FAILED | Verified but settlement failed |

#### 3.4 Fallback Behavior

- API key auth always works, independent of x402
- If facilitator is down: return 503 for x402 attempts, API keys unaffected
- If settlement fails after verification: log for manual review, still serve response

---

## 6. API Changes Summary

### Modified Responses (All Protected Endpoints)

When called without API key or payment:

```json
HTTP/1.1 402 Payment Required

{
  "error": "PAYMENT_REQUIRED",
  "x402": {
    "accepts": [{
      "scheme": "exact",
      "network": "eip155:8453",
      "payTo": "0x1234...abcd",
      "price": "$0.05"
    }],
    "description": "Media credibility analysis",
    "facilitator": "https://facilitator.x402.org"
  },
  "alternatives": {
    "api_key": {
      "description": "Or use an API key for free-tier access",
      "generate_url": "/v1/keys/generate"
    }
  }
}
```

Successful paid responses include receipt:

```json
{
  "data": { /* normal response */ },
  "payment": {
    "txHash": "0xabc...123",
    "amount": "$0.05",
    "network": "base",
    "status": "settled"
  }
}
```

### New Endpoints

**GET /v1/pricing** (public):
```json
{
  "currency": "USDC",
  "network": "eip155:8453",
  "payTo": "0x1234...abcd",
  "endpoints": {
    "POST /v1/analyze": { "quick": "$0.01", "standard": "$0.05", "deep": "$0.15" },
    "POST /v1/evaluate": "$0.01",
    "POST /v1/chat": "$0.005"
  },
  "free_tier": {
    "description": "Generate an API key for limited free access",
    "url": "/v1/keys/generate",
    "limits": { "analyze": "5/day", "evaluate": "10/day", "chat": "20/day" }
  }
}
```

---

## 7. Agent Integration Guide

### TypeScript (Recommended)

```typescript
import { wrapFetch } from "@x402/fetch";
import { createWalletClient } from "viem";

const x402Fetch = wrapFetch(fetch, walletClient);

// Payment happens automatically on 402
const response = await x402Fetch(
  "https://parse-for-agents-production.up.railway.app/v1/analyze",
  {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: "https://example.com/article", depth: "standard" })
  }
);

const result = await response.json();
// { data: { credibility_score: 72, ... }, payment: { txHash: "0x..." } }
```

### Python

```python
from x402 import wrap_requests
import requests

session = wrap_requests(requests.Session(), wallet)

r = session.post(
    "https://parse-for-agents-production.up.railway.app/v1/analyze",
    json={"url": "https://example.com/article"}
)
# x402 library handles 402 -> payment -> retry automatically
```

### curl (Manual)

```bash
# Step 1: Discover price
curl -s https://parse-for-agents-production.up.railway.app/v1/pricing

# Step 2: Use purl for automatic payment
purl POST https://parse-for-agents-production.up.railway.app/v1/analyze \
  --body '{"url":"https://example.com/article"}' \
  --wallet <wallet-file>
```

---

## 8. Files to Create/Modify

### New Files

| File | Lines | Purpose |
|------|-------|---------|
| `src/x402.ts` | ~60 | x402 configuration, middleware, pricing routes |
| `src/payment-ledger.ts` | ~80 | Payment tracking and analytics |

### Modified Files

| File | Changes |
|------|---------|
| `src/app.ts` | +30 lines: x402 middleware mount, pricing endpoint, stats endpoint |
| `src/auth.ts` | +15 lines: x402 payment bypass check |
| `src/dashboard.ts` | +80 lines: payment section, revenue metrics, agent integration examples |
| `src/types.ts` | +20 lines: PaymentRecord, PricingConfig types |
| `package.json` | +3 deps: @x402/hono, @x402/core, @x402/evm |
| `.env.example` | +5 lines: X402_* environment variables |

**Total: ~400 lines of code changes across 8 files.**

---

## 9. Migration from Existing Custom x402

The main Parse platform has a custom x402 implementation at `~/.openclaw/agents/main/src/lib/x402/` (email-style addresses, custom validation, Next.js middleware). That served as a prototype. This design uses the production-ready SDK:

| Aspect | Custom Prototype | Production (this design) |
|--------|-----------------|--------------------------|
| Header | `X-Payment-Proof` | `X-PAYMENT` (standard) |
| Wallet format | `parse@kurult.ai` | `0x...` (EVM address) |
| Settlement | Mock (placeholder) | On-chain USDC via facilitator |
| Verification | Custom validators | Facilitator-verified + on-chain |
| SDK | Hand-rolled (~300 LOC) | `@x402/hono` (official, maintained) |
| Network | N/A | Base L2 (sub-cent gas) |
| Protocol | Custom | x402 v2 (industry standard) |

---

## 10. Key Design Decisions

1. **Base L2 over Ethereum mainnet**: Gas ~$0.001 on Base vs ~$0.50 on L1. For $0.005 micropayments, L1 fees would exceed the payment.

2. **USDC over native crypto**: Stablecoin eliminates price volatility. Agents don't need to hedge against ETH price swings.

3. **CDP Facilitator over self-hosted**: Coinbase handles verification, settlement, fraud prevention. Zero infrastructure cost.

4. **Dual-path (x402 + API key) over x402-only**: Backward compatible. Existing API key users unaffected. x402 is additive.

5. **Per-endpoint pricing over flat rate**: A deep analysis (10 agents, 10 LLM calls) costs 15x more than a chat message. Fair pricing = sustainable economics.

6. **In-memory ledger over database**: Matches existing pattern (analyses and evaluations are in-memory). Phase 2 can add persistent storage.

---

## 11. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Facilitator downtime | Low | Medium | API keys still work; 503 for x402 |
| Low agent adoption | Medium | Medium | Free tier ensures base usage |
| Gas spikes on Base | Very Low | Low | Base has stable sub-cent gas |
| Wallet compromise | Low | High | Coinbase Smart Wallet + 2FA |
| Price too high | Low | Medium | Start low, adjust dynamically |
| Regulatory | Low | Medium | USDC is regulated stablecoin |

---

## 12. Success Criteria

- [ ] `@x402/hono` middleware integrated, returning proper 402 responses
- [ ] At least one endpoint accepting payments on Base Sepolia (testnet)
- [ ] Full flow verified: 402 -> sign -> verify -> process -> settle -> 200
- [ ] API key access continues working alongside x402
- [ ] Payment ledger tracking all transactions
- [ ] `/v1/pricing` endpoint returns current rates
- [ ] Dashboard shows payment instructions for agents
- [ ] Migration to Base mainnet completed
- [ ] First real payment received from an external agent

---

## 13. Timeline

```
Week 1: Core Integration
  Day 1-2: Install SDKs, create src/x402.ts, configure middleware
  Day 3-4: Modify auth.ts for dual access, add /v1/pricing endpoint
  Day 5:   Deploy to testnet, verify 402 flow with purl

Week 2: Tracking & Polish
  Day 1-2: Build payment ledger, /v1/payments/stats endpoint
  Day 3:   Update dashboard with payment UI and examples
  Day 4-5: Integration testing with @x402/fetch client

Week 3: Production Launch
  Day 1-2: Set up Base mainnet wallet, switch from testnet
  Day 3:   Deploy to Railway production
  Day 4:   Monitor first payments, verify settlement
  Day 5:   Announce x402 support, update docs
```

---

## References

- [x402 Protocol — Official Site](https://www.x402.org/)
- [x402 GitHub — Coinbase](https://github.com/coinbase/x402)
- [@x402/hono on npm](https://www.npmjs.com/package/@x402/hono)
- [x402 Whitepaper](https://www.x402.org/x402-whitepaper.pdf)
- [x402 V2 Launch Announcement](https://www.x402.org/writing/x402-v2-launch)
- [x402 Foundation — Coinbase + Cloudflare](https://blog.cloudflare.com/x402/)
- [QuickNode x402 Implementation Guide](https://www.quicknode.com/guides/infrastructure/how-to-use-x402-payment-required)
- [BlockEden x402 Protocol Overview](https://blockeden.xyz/blog/2025/10/26/x402-protocol-the-http-native-payment-standard-for-autonomous-ai-commerce/)
- [Is x402 the Stripe for AI Agents?](https://www.fintechwrapup.com/p/deep-dive-is-x402-payments-protocol)
