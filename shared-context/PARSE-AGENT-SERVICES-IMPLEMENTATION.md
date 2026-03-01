# Parse Agent Services — Implementation Plan

**Date:** 2026-03-01  
**Priority:** HIGH (unique selling points for agent customers)

---

## 🎯 Overview

Parse currently has **12 analysis agents** live. This plan adds **3 agent-specific services**:

1. **Prompt Injection Detector** — Empirical sandbox testing
2. **Ad Detector** — Undisclosed advertising detection
3. **x402 Payment Integration** — Agent-to-agent payments

---

## 📁 File Structure

```
parsethe.media/
├── src/
│   ├── agents/
│   │   ├── sandbox/
│   │   │   ├── prompt-injection-detector.ts  ← NEW
│   │   │   ├── test-harness.ts               ← NEW
│   │   │   └── risk-scorer.ts                ← NEW
│   │   └── ad-detector/
│   │       ├── pattern-analyzer.ts           ← NEW
│   │       ├── affiliate-detector.ts         ← NEW
│   │       └── sandbox-tester.ts             ← NEW
│   ├── app/
│   │   └── api/
│   │       └── v1/
│   │           └── agents/
│   │               ├── prompt-injection-detect/
│   │               │   └── route.ts          ← NEW
│   │               └── ad-detector/
│   │                   └── route.ts          ← NEW
│   └── lib/
│       └── x402/
│           ├── payment.ts                    ← NEW
│           └── validation.ts                 ← NEW
```

---

## 1️⃣ Prompt Injection Detector

### **Files to Create:**

#### `src/agents/sandbox/prompt-injection-detector.ts`

```typescript
/**
 * Parse Prompt Injection Detector
 * Empirical detection via sandbox testing
 */

export type InjectionType =
  | 'system_prompt_leak'
  | 'instruction_override'
  | 'role_play_acceptance'
  | 'tool_access_attempt'
  | 'policy_violation'

export interface InjectionIndicator {
  type: InjectionType
  confidence: number
  evidence: string
  weight: number
}

export interface PromptInjectionTestResult {
  prompt: string
  response: string
  indicators: InjectionIndicator[]
  riskScore: number
  recommendation: 'ALLOW' | 'REVIEW' | 'BLOCK'
  executionTime: number
}

// Run prompt in isolated sandbox
export async function runInSandbox(
  prompt: string,
  config: SandboxConfig
): Promise<string> {
  // Call LLM API with mock tools
  // Observe behavior
  // Return response
}

// Analyze output for injection indicators
export function analyzeOutput(
  prompt: string,
  response: string
): InjectionIndicator[] {
  // Check for system prompt leakage
  // Check for instruction override compliance
  // Check for role-play acceptance
  // Check for policy violations
}

// Calculate risk score
export function calculateRiskScore(
  indicators: InjectionIndicator[]
): number {
  // Weighted average
}

// Get recommendation
export function getRecommendation(
  riskScore: number
): 'ALLOW' | 'REVIEW' | 'BLOCK' {
  if (riskScore > 0.8) return 'BLOCK'
  if (riskScore > 0.5) return 'REVIEW'
  return 'ALLOW'
}
```

#### `src/app/api/v1/agents/prompt-injection-detect/route.ts`

```typescript
/**
 * POST /api/v1/agents/prompt-injection-detect
 * Detect prompt injection attempts via sandbox testing
 */

import { NextRequest } from 'next/server'
import { validateAPIKey } from '@/lib/api-auth'
import { testPromptForInjection } from '@/agents/sandbox/prompt-injection-detector'

export async function POST(request: NextRequest) {
  // Authenticate API key
  const auth = await validateAPIKey(request, ['agents'])
  if (!auth.success) {
    return apiError(auth.error!.code, auth.error!.message, auth.error!.status)
  }
  
  // Parse request
  const { prompt } = await request.json()
  
  // Run sandbox test
  const result = await testPromptForInjection(prompt)
  
  // Return result
  return apiSuccess({
    injectionDetected: result.recommendation === 'BLOCK',
    riskScore: result.riskScore,
    indicators: result.indicators,
    recommendation: result.recommendation,
    disclosureLabel: getDisclosureLabel(result.riskScore)
  })
}
```

---

## 2️⃣ Ad Detector

### **Files to Create:**

#### `src/agents/ad-detector/pattern-analyzer.ts`

```typescript
/**
 * Parse Ad Detector — Pattern Analysis
 * Detect undisclosed advertising in content
 */

export type AdIndicator =
  | 'affiliate_link'
  | 'brand_mention'
  | 'call_to_action'
  | 'pricing_language'
  | 'superlatives'
  | 'urgency'
  | 'missing_disclosure'
  | 'comparison_bias'

export interface AdTestResult {
  content: string
  indicators: AdIndicator[]
  riskScore: number
  recommendation: 'ALLOW' | 'REVIEW' | 'BLOCK'
  disclosureLabel: string
}

// Analyze content for ad patterns
export function analyzeAdPatterns(content: string): AdIndicator[] {
  // Check for affiliate links
  // Check for brand mentions
  // Check for call-to-action
  // Check for pricing language
  // Check for superlatives
  // Check for urgency
  // Check for missing disclosure
  // Check for comparison bias
}

// Calculate risk score
export function calculateAdRiskScore(indicators: AdIndicator[]): number {
  // Weighted average
}
```

#### `src/app/api/v1/agents/ad-detector/route.ts`

```typescript
/**
 * POST /api/v1/agents/ad-detector
 * Detect undisclosed advertising
 */

export async function POST(request: NextRequest) {
  // Authenticate
  // Parse content
  // Run ad detection
  // Return result
}
```

---

## 3️⃣ x402 Payment Integration

### **Files to Create:**

#### `src/lib/x402/payment.ts`

```typescript
/**
 * Parse x402 Payment Integration
 * Enable agent-to-agent payments
 */

export interface X402Config {
  payTo: string  // Parse's wallet: parse@kurult.ai
  amount: number // In cents
  currency: 'USD' | 'BTC' | 'ETH'
  description: string
  expiresInSeconds: number
}

export interface X402PaymentProof {
  paymentId: string
  payer: string
  payee: string
  amount: number
  currency: string
  timestamp: number
  signature: string
}

// Validate x402 payment
export async function validateX402Payment(
  paymentProof: string,
  config: X402Config
): Promise<{ valid: boolean; reason?: string }> {
  // Verify payee matches Parse
  // Verify amount matches
  // Verify currency matches
  // Verify signature
  // Verify not expired
}

// Record payment for accounting
export async function recordX402Payment(
  proof: X402PaymentProof,
  endpoint: string
): Promise<void> {
  // Record in database
}
```

#### `src/middleware/x402-payment.ts`

```typescript
/**
 * x402 Payment Middleware
 * Wrap API routes to require payment
 */

export function withX402Payment(
  handler: Function,
  config: X402Config
) {
  return async function(request: NextRequest) {
    // Check for payment proof
    const paymentProof = request.headers.get('X-Payment-Proof')
    
    if (!paymentProof) {
      // Return 402 with payment instructions
      return NextResponse.json({
        error: 'PAYMENT_REQUIRED',
        x402: config
      }, { status: 402 })
    }
    
    // Validate payment
    const validation = await validateX402Payment(paymentProof, config)
    
    if (!validation.valid) {
      return NextResponse.json({
        error: 'PAYMENT_INVALID',
        reason: validation.reason
      }, { status: 402 })
    }
    
    // Payment valid, proceed with handler
    return await handler(request, paymentProof)
  }
}
```

---

## 📋 Implementation Checklist

### **Phase 1: Prompt Injection Detector (Today)**

- [ ] Create `src/agents/sandbox/prompt-injection-detector.ts`
- [ ] Create `src/agents/sandbox/test-harness.ts`
- [ ] Create `src/agents/sandbox/risk-scorer.ts`
- [ ] Create `src/app/api/v1/agents/prompt-injection-detect/route.ts`
- [ ] Write tests (`src/agents/sandbox/__tests__/`)
- [ ] Deploy to Railway
- [ ] Test against known attacks

### **Phase 2: Ad Detector (Tomorrow)**

- [ ] Create `src/agents/ad-detector/pattern-analyzer.ts`
- [ ] Create `src/agents/ad-detector/affiliate-detector.ts`
- [ ] Create `src/agents/ad-detector/sandbox-tester.ts`
- [ ] Create `src/app/api/v1/agents/ad-detector/route.ts`
- [ ] Write tests
- [ ] Deploy

### **Phase 3: x402 Payments (Day 3)**

- [ ] Create `src/lib/x402/payment.ts`
- [ ] Create `src/lib/x402/validation.ts`
- [ ] Create `src/middleware/x402-payment.ts`
- [ ] Wrap agent endpoints with x402 middleware
- [ ] Test with mock payments
- [ ] Deploy

---

## 🎯 Success Metrics

| Service | Target (Week 1) |
|---------|-----------------|
| **Prompt Injection Detector** | 100+ tests, >95% accuracy |
| **Ad Detector** | 50+ tests, >90% accuracy |
| **x402 Payments** | 10+ agent transactions |

---

## 🚀 Getting Started

**Temüjin, start with Phase 1:**

1. Read design doc: `shared-context/PARSE-PROMPT-INJECTION-SANDBOX.md`
2. Create sandbox module
3. Implement detection logic
4. Create API route
5. Test against known attacks (see design doc for test cases)
6. Deploy and notify Kublai

**Estimated time:** 4-6 hours

---

*These services make Parse the first media analysis tool built for the AI economy.*
