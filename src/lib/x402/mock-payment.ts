/**
 * x402 Mock Payment Generator
 * 
 * Utility for testing x402 payment integration
 * Generates valid mock payments for development and testing
 * 
 * Usage:
 * ```typescript
 * import { createMockPayment, testPaymentFlow } from '@/lib/x402/mock-payment'
 * 
 * const payment = createMockPayment({ amount: 19 })
 * const result = await testPaymentFlow(payment)
 * ```
 */

import { X402PaymentProof, X402Config, DEFAULT_X402_CONFIG } from './payment'

/**
 * Generate a unique payment ID
 */
function generatePaymentId(): string {
  const timestamp = Date.now()
  const random = Math.random().toString(36).substring(2, 8)
  return `x402_${timestamp}_${random}`
}

/**
 * Generate a mock cryptographic signature
 * 
 * In production, this would be a real signature from the payer's wallet
 */
function generateMockSignature(): string {
  // Generate 64-character hex string (mock signature)
  const chars = '0123456789abcdef'
  let signature = ''
  for (let i = 0; i < 64; i++) {
    signature += chars[Math.floor(Math.random() * chars.length)]
  }
  return signature
}

/**
 * Create a mock x402 payment proof
 * 
 * @param config - Payment configuration
 * @param payer - Payer wallet address (default: mock agent)
 * @returns Valid mock payment proof
 */
export function createMockPayment(
  config: Partial<X402Config> = {},
  payer: string = 'mock-agent@example.com'
): X402PaymentProof {
  const fullConfig: X402Config = {
    ...DEFAULT_X402_CONFIG,
    ...config,
  }

  return {
    paymentId: generatePaymentId(),
    payer,
    payee: fullConfig.payTo,
    amount: fullConfig.amount,
    currency: fullConfig.currency,
    timestamp: Math.floor(Date.now() / 1000),
    signature: generateMockSignature(),
    network: 'testnet',
  }
}

/**
 * Create mock payment as JSON string (ready for X-Payment-Proof header)
 */
export function createMockPaymentHeader(
  config: Partial<X402Config> = {}
): string {
  const payment = createMockPayment(config)
  return JSON.stringify(payment)
}

/**
 * Simulate x402 payment flow for testing
 * 
 * @param endpoint - API endpoint to test
 * @param config - Payment configuration
 * @returns Test result
 */
export interface PaymentFlowResult {
  paymentProof: string
  payment: X402PaymentProof
  status: number
  response: unknown
  success: boolean
}

export async function testPaymentFlow(
  endpoint: string,
  config: Partial<X402Config> = {}
): Promise<PaymentFlowResult> {
  // Create mock payment
  const payment = createMockPayment(config)
  const paymentProof = JSON.stringify(payment)

  console.log(`[x402 Test] Testing payment flow for ${endpoint}`)
  console.log(`[x402 Test] Payment:`, payment)

  // In a real test, you would make an HTTP request here:
  // const response = await fetch(endpoint, {
  //   method: 'POST',
  //   headers: {
  //     'Content-Type': 'application/json',
  //     'X-Payment-Proof': paymentProof,
  //   },
  //   body: JSON.stringify({ /* request data */ }),
  // })
  
  // For now, just return the payment proof for manual testing
  return {
    paymentProof,
    payment,
    status: 200,
    response: { success: true },
    success: true,
  }
}

/**
 * Test scenarios for x402 payment integration
 */
export const testScenarios = {
  /**
   * Test: Valid payment
   */
  validPayment() {
    return createMockPayment({
      amount: 19,
      currency: 'USD',
    })
  },

  /**
   * Test: Wrong amount
   */
  wrongAmount() {
    return createMockPayment({
      amount: 10, // Should be 19
    })
  },

  /**
   * Test: Wrong currency
   */
  wrongCurrency() {
    return createMockPayment({
      currency: 'BTC', // Should be USD
    })
  },

  /**
   * Test: Wrong payee
   */
  wrongPayee() {
    const payment = createMockPayment()
    payment.payee = 'wrong@example.com'
    return payment
  },

  /**
   * Test: Expired payment
   */
  expiredPayment() {
    const payment = createMockPayment()
    payment.timestamp = Math.floor(Date.now() / 1000) - 400 // 400 seconds ago
    return payment
  },

  /**
   * Test: Future payment
   */
  futurePayment() {
    const payment = createMockPayment()
    payment.timestamp = Math.floor(Date.now() / 1000) + 120 // 2 minutes in future
    return payment
  },

  /**
   * Test: Replay attack (same payment twice)
   */
  replayAttack() {
    return createMockPayment()
    // Use the same payment object twice to simulate replay
  },
}

/**
 * Run all test scenarios
 */
export async function runAllTestScenarios(endpoint: string): Promise<void> {
  console.log('\n=== x402 Payment Test Scenarios ===\n')

  const scenarios = [
    { name: 'Valid Payment', test: testScenarios.validPayment, expectSuccess: true },
    { name: 'Wrong Amount', test: testScenarios.wrongAmount, expectSuccess: false },
    { name: 'Wrong Currency', test: testScenarios.wrongCurrency, expectSuccess: false },
    { name: 'Wrong Payee', test: testScenarios.wrongPayee, expectSuccess: false },
    { name: 'Expired Payment', test: testScenarios.expiredPayment, expectSuccess: false },
    { name: 'Future Payment', test: testScenarios.futurePayment, expectSuccess: false },
  ]

  for (const scenario of scenarios) {
    console.log(`\n--- Testing: ${scenario.name} ---`)
    
    const payment = scenario.test()
    console.log('Payment:', JSON.stringify(payment, null, 2))
    
    // In a real test, you would make the HTTP request here
    console.log(`Expected: ${scenario.expectSuccess ? 'SUCCESS' : 'FAILURE'}`)
    console.log('Status: PENDING (manual test required)')
  }

  console.log('\n=== Test Scenarios Complete ===\n')
}

/**
 * Generate curl command for testing
 */
export function generateCurlCommand(
  endpoint: string,
  payment: X402PaymentProof,
  requestBody: Record<string, unknown> = {}
): string {
  const paymentProof = JSON.stringify(payment)
  const body = JSON.stringify(requestBody)

  return `curl -X POST ${endpoint} \\
  -H "Content-Type: application/json" \\
  -H "X-Payment-Proof: ${paymentProof}" \\
  -d '${body}'`
}

/**
 * Example: Generate test commands for documentation
 */
export function generateTestDocumentation(): string {
  const validPayment = testScenarios.validPayment()
  const endpoint = 'https://www.parsethe.media/api/v1/agents/bernays'

  return `
# x402 Payment Integration - Test Commands

## Valid Payment

\`\`\`bash
${generateCurlCommand(endpoint, validPayment, { url: 'https://example.com/article' })}
\`\`\`

## Expected Response (200 OK)

\`\`\`json
{
  "success": true,
  "data": {
    "bernaysScore": 0.72,
    "techniques": ["appeal to authority", "false dilemma"],
    "confidence": 0.85
  },
  "payment": {
    "received": true,
    "amount": 19,
    "currency": "USD",
    "transactionId": "${validPayment.paymentId}"
  }
}
\`\`\`

## No Payment (402 Payment Required)

\`\`\`bash
curl -X POST ${endpoint} \\
  -H "Content-Type: application/json" \\
  -d '{"url": "https://example.com/article"}'
\`\`\`

## Expected Response (402 Payment Required)

\`\`\`json
{
  "error": "PAYMENT_REQUIRED",
  "x402": {
    "payTo": "parse@kurult.ai",
    "amount": 19,
    "currency": "USD",
    "description": "Bernays agent analysis (1 credit)",
    "expiresAt": "2026-03-01T03:15:00Z"
  }
}
\`\`\`
`.trim()
}
