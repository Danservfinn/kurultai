# Parse x402 Payment Integration

**Date:** 2026-03-01  
**Purpose:** Enable AI agents to pay for Parse services via x402 protocol

---

## 🎯 Why x402?

**x402 is the payment protocol for AI agents:**
- Standardized payment format across AI services
- Micropayments (per-API-call billing)
- No human intervention needed
- Agents can budget, spend, and track usage autonomously

**For Parse:**
- Other AI agents can call Parse APIs directly
- Payments happen automatically (no human billing)
- Enables agent-to-agent economy
- Recurring revenue from agent subscriptions

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Parse x402 Integration                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Agent Client → x402 Payment → Parse API → Analysis → Response  │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   AGENT      │    │   x402       │    │    PARSE     │      │
│  │   (Client)   │    │   PAYMENT    │    │    API       │      │
│  │              │    │              │    │              │      │
│  │ • Has x402   │    │ • Validates  │    │ • Receives   │      │
│  │   wallet     │    │   payment    │    │   payment    │      │
│  │ • Requests   │    │ • Forwards   │    │ • Processes  │      │
│  │   analysis   │    │   to Parse   │    │   request    │      │
│  │              │    │              │    │              │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 💰 Payment Flow

### 1. Agent Requests Analysis

```json
POST /api/v1/agents/bernays
Content-Type: application/json
X-Payment-Required: true

{
  "url": "https://example.com/article"
}
```

### 2. Parse Returns Payment Required

```json
HTTP 402 Payment Required
Content-Type: application/json

{
  "error": "PAYMENT_REQUIRED",
  "x402": {
    "payTo": "parse@kurult.ai",
    "amount": 1,
    "currency": "USD",
    "description": "Bernays agent analysis (1 credit)",
    "expiresAt": "2026-03-01T03:15:00Z"
  }
}
```

### 3. Agent Sends x402 Payment

```json
POST /api/v1/agents/bernays
Content-Type: application/json
X-Payment-Proof: <x402-payment-proof>

{
  "url": "https://example.com/article"
}
```

### 4. Parse Validates + Processes

```json
HTTP 200 OK
Content-Type: application/json

{
  "success": true,
  "data": {
    "bernaysScore": 0.72,
    "techniques": ["appeal to authority", "false dilemma"],
    "confidence": 0.85
  },
  "payment": {
    "received": true,
    "amount": 1,
    "transactionId": "x402_txn_..."
  }
}
```

---

## 🔧 Implementation

### 1. x402 Middleware

```typescript
// src/middleware/x402-payment.ts

import { NextRequest, NextResponse } from 'next/server'
import { validateX402Payment, X402PaymentProof } from '@/lib/x402'

export interface X402Config {
  // Parse's x402 wallet address
  payTo: string
  
  // Amount in cents (1 credit = $0.19 for Pro tier)
  amount: number
  
  // Currency
  currency: 'USD' | 'BTC' | 'ETH'
  
  // Payment description
  description: string
  
  // Payment expires in (seconds)
  expiresInSeconds: number
}

export const DEFAULT_X402_CONFIG: X402Config = {
  payTo: 'parse@kurult.ai',
  amount: 19, // $0.19 per credit (Pro tier pricing)
  currency: 'USD',
  description: 'Parse agent analysis',
  expiresInSeconds: 300 // 5 minutes
}

/**
 * x402 Payment Middleware
 * 
 * Wraps API routes to require x402 payment before processing
 */
export function withX402Payment(
  handler: (request: NextRequest, payment: X402PaymentProof) => Promise<NextResponse>,
  config: X402Config = DEFAULT_X402_CONFIG
) {
  return async function (request: NextRequest): Promise<NextResponse> {
    // Check for payment proof
    const paymentProof = request.headers.get('X-Payment-Proof')
    
    if (!paymentProof) {
      // Return 402 with payment instructions
      return NextResponse.json({
        error: 'PAYMENT_REQUIRED',
        x402: {
          payTo: config.payTo,
          amount: config.amount,
          currency: config.currency,
          description: config.description,
          expiresAt: new Date(Date.now() + config.expiresInSeconds * 1000).toISOString()
        }
      }, { status: 402 })
    }
    
    // Validate payment
    try {
      const payment = await validateX402Payment(paymentProof, config)
      
      if (!payment.valid) {
        return NextResponse.json({
          error: 'PAYMENT_INVALID',
          reason: payment.reason
        }, { status: 402 })
      }
      
      // Payment valid, proceed with handler
      return await handler(request, payment.proof)
      
    } catch (error) {
      return NextResponse.json({
        error: 'PAYMENT_ERROR',
        message: error instanceof Error ? error.message : 'Unknown error'
      }, { status: 500 })
    }
  }
}
```

### 2. x402 Validation Library

```typescript
// src/lib/x402.ts

import { z } from 'zod'

// x402 payment proof schema
export const X402PaymentProofSchema = z.object({
  // Payment ID
  paymentId: z.string(),
  
  // Payer wallet address
  payer: z.string(),
  
  // Payee wallet address
  payee: z.string(),
  
  // Amount in cents
  amount: z.number(),
  
  // Currency
  currency: z.enum(['USD', 'BTC', 'ETH']),
  
  // Timestamp
  timestamp: z.number(),
  
  // Signature (cryptographic proof)
  signature: z.string(),
  
  // Network (testnet/mainnet)
  network: z.enum(['testnet', 'mainnet']).optional()
})

export type X402PaymentProof = z.infer<typeof X402PaymentProofSchema>

export interface X402ValidationResult {
  valid: boolean
  reason?: string
  proof?: X402PaymentProof
}

/**
 * Validate x402 payment proof
 */
export async function validateX402Payment(
  paymentProof: string,
  config: { payTo: string; amount: number; currency: string }
): Promise<X402ValidationResult> {
  try {
    // Parse payment proof
    const proof = JSON.parse(paymentProof)
    const validated = X402PaymentProofSchema.parse(proof)
    
    // Verify payee matches Parse
    if (validated.payee !== config.payTo) {
      return {
        valid: false,
        reason: `Invalid payee: expected ${config.payTo}, got ${validated.payee}`
      }
    }
    
    // Verify amount matches
    if (validated.amount !== config.amount) {
      return {
        valid: false,
        reason: `Invalid amount: expected ${config.amount}, got ${validated.amount}`
      }
    }
    
    // Verify currency matches
    if (validated.currency !== config.currency) {
      return {
        valid: false,
        reason: `Invalid currency: expected ${config.currency}, got ${validated.currency}`
      }
    }
    
    // Verify signature (cryptographic validation)
    const signatureValid = await verifyX402Signature(validated)
    if (!signatureValid) {
      return {
        valid: false,
        reason: 'Invalid signature'
      }
    }
    
    // Verify not expired (5 minute window)
    const now = Math.floor(Date.now() / 1000)
    const age = now - validated.timestamp
    if (age > 300) {
      return {
        valid: false,
        reason: 'Payment expired (older than 5 minutes)'
      }
    }
    
    // Payment is valid
    return {
      valid: true,
      proof: validated
    }
    
  } catch (error) {
    return {
      valid: false,
      reason: error instanceof Error ? error.message : 'Invalid payment format'
    }
  }
}

/**
 * Verify x402 signature
 * 
 * TODO: Implement actual cryptographic verification
 * For now, placeholder
 */
async function verifyX402Signature(proof: X402PaymentProof): Promise<boolean> {
  // TODO: Implement actual signature verification
  // This would use the payer's public key to verify the signature
  
  // Placeholder for development
  return true
}

/**
 * Record x402 payment for accounting
 */
export async function recordX402Payment(
  proof: X402PaymentProof,
  endpoint: string,
  userId: string
): Promise<void> {
  // TODO: Record payment in database for accounting
  // Track:
  // - Payer wallet
  // - Amount
  // - Endpoint called
  // - Timestamp
  // - Transaction ID
  
  console.log(`x402 payment recorded: ${proof.payer} paid ${proof.amount} ${proof.currency} for ${endpoint}`)
}
```

### 3. API Route Integration

```typescript
// src/app/api/v1/agents/bernays/route.ts

import { NextRequest } from 'next/server'
import { withX402Payment } from '@/middleware/x402-payment'
import { runBernaysAgent } from '@/agents/bernays-agent'
import { apiSuccess, apiError } from '@/lib/api-response'

// Wrap handler with x402 payment requirement
export const POST = withX402Payment(
  async (request: NextRequest, payment) => {
    // Payment validated, process request
    let body: unknown
    try {
      body = await request.json()
    } catch {
      return apiError('INVALID_REQUEST', 'Invalid JSON', 400)
    }
    
    // Run Bernays agent
    const result = await runBernaysAgent(body)
    
    // Record payment for accounting
    await recordX402Payment(payment, '/api/v1/agents/bernays', 'x402-user')
    
    return apiSuccess(result, {
      payment: {
        received: true,
        amount: payment.amount,
        transactionId: payment.paymentId
      }
    })
  },
  {
    payTo: 'parse@kurult.ai',
    amount: 19, // $0.19 per credit
    currency: 'USD',
    description: 'Bernays agent analysis (1 credit)',
    expiresInSeconds: 300
  }
)
```

---

## 💳 Pricing Tiers (x402)

| Tier | Price per Credit | x402 Amount |
|------|-----------------|-------------|
| **Free** | $0.10/credit | 10 cents |
| **Pro** | $0.19/credit | 19 cents |
| **Max** | $0.49/credit | 49 cents |
| **Enterprise** | Custom | Negotiated |

**Note:** x402 payments use Pro tier pricing by default (no subscription needed)

---

## 🤖 Agent Client Example

```typescript
// Example: Another AI agent calling Parse with x402

import { createX402Payment } from '@x402/sdk'

async function analyzeArticle(articleUrl: string) {
  // Create x402 payment
  const payment = await createX402Payment({
    payTo: 'parse@kurult.ai',
    amount: 19, // $0.19
    currency: 'USD',
    description: 'Bernays agent analysis'
  })
  
  // Call Parse API with payment
  const response = await fetch('https://www.parsethe.media/api/v1/agents/bernays', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Payment-Proof': JSON.stringify(payment)
    },
    body: JSON.stringify({
      url: articleUrl
    })
  })
  
  if (response.status === 402) {
    const error = await response.json()
    throw new Error(`Payment required: ${error.x402.description}`)
  }
  
  const result = await response.json()
  return result.data
}

// Usage
const analysis = await analyzeArticle('https://example.com/article')
console.log(analysis.bernaysScore)
```

---

## 📊 Revenue Tracking

### x402 Payment Ledger

```typescript
// src/lib/x402-ledger.ts

export interface X402Transaction {
  transactionId: string
  payer: string
  payee: string
  amount: number
  currency: string
  endpoint: string
  timestamp: Date
  status: 'completed' | 'pending' | 'failed'
}

/**
 * Track x402 revenue
 */
export async function trackX402Revenue(
  transaction: X402Transaction
): Promise<void> {
  // Record in database
  // Update revenue dashboard
  // Send notification if large payment
}

/**
 * Get x402 revenue report
 */
export async function getX402RevenueReport(
  startDate: Date,
  endDate: Date
): Promise<{
  totalRevenue: number
  transactionCount: number
  topEndpoints: Array<{ endpoint: string; revenue: number }>
  topPayers: Array<{ payer: string; revenue: number }>
}> {
  // Query database for x402 transactions
  // Aggregate by endpoint, payer
  // Return report
}
```

---

## 🚀 Rollout Plan

### Phase 1: x402 Support (Week 1)
- [ ] Implement x402 middleware
- [ ] Add x402 validation library
- [ ] Update all agent endpoints to support x402
- [ ] Test with mock payments

### Phase 2: Agent SDK (Week 2)
- [ ] Create `@parse/x402-client` SDK
- [ ] Document x402 integration for agents
- [ ] Example code for common agent frameworks

### Phase 3: Agent Outreach (Week 3)
- [ ] Contact AI agent developers
- [ ] Offer free x402 credits for testing
- [ ] Gather feedback, iterate

### Phase 4: Revenue Tracking (Week 4)
- [ ] x402 revenue dashboard
- [ ] Daily/weekly reports
- [ ] Payout system for Parse sustainability

---

## 🎯 Success Metrics

| Metric | Target (Month 1) |
|--------|-----------------|
| **x402 Transactions** | 100+ |
| **Agent Clients** | 10+ |
| **x402 Revenue** | $100+ |
| **Repeat Payers** | 50%+ |

---

## 🔗 Resources

- **x402 Spec:** https://github.com/x402/x402
- **x402 SDK:** https://www.npmjs.com/package/@x402/sdk
- **Parse x402 Wallet:** `parse@kurult.ai`

---

*x402 enables autonomous agent-to-agent commerce. Parse becomes a revenue-generating service for the AI economy.*
