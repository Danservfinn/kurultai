/**
 * x402 Payment Integration Tests
 * 
 * Tests for payment validation, middleware, and mock payments
 */

import { describe, it, expect, beforeEach } from '@jest/globals'
import {
  validateX402Payment,
  X402Config,
  X402PaymentProof,
  DEFAULT_X402_CONFIG,
  createPaymentRequiredResponse,
} from '@/lib/x402/payment'
import {
  isReplayAttack,
  validatePaymentAmount,
  validatePaymentCurrency,
  validatePaymentTimestamp,
  validateWalletAddress,
  validatePaymentComprehensive,
  getValidationErrorCode,
} from '@/lib/x402/validation'

// Mock payment proof for testing
function createMockPayment(overrides?: Partial<X402PaymentProof>): X402PaymentProof {
  return {
    paymentId: `test_payment_${Date.now()}`,
    payer: 'test-agent@example.com',
    payee: 'parse@kurult.ai',
    amount: 19,
    currency: 'USD',
    timestamp: Math.floor(Date.now() / 1000),
    signature: 'a'.repeat(64), // Mock signature
    ...overrides,
  }
}

describe('x402 Payment Validation', () => {
  beforeEach(() => {
    // Clear replay cache before each test
    // @ts-ignore - accessing private for testing
    REPLAY_CACHE.clear()
  })

  describe('validateX402Payment', () => {
    it('should validate correct payment', async () => {
      const payment = createMockPayment()
      const config: X402Config = {
        payTo: 'parse@kurult.ai',
        amount: 19,
        currency: 'USD',
        description: 'Test payment',
        expiresInSeconds: 300,
      }

      const result = await validateX402Payment(JSON.stringify(payment), config)

      expect(result.valid).toBe(true)
      expect(result.proof).toEqual(payment)
    })

    it('should reject invalid payee', async () => {
      const payment = createMockPayment({ payee: 'wrong@example.com' })
      const config = DEFAULT_X402_CONFIG

      const result = await validateX402Payment(JSON.stringify(payment), config)

      expect(result.valid).toBe(false)
      expect(result.reason).toContain('Invalid payee')
    })

    it('should reject incorrect amount', async () => {
      const payment = createMockPayment({ amount: 10 })
      const config = DEFAULT_X402_CONFIG

      const result = await validateX402Payment(JSON.stringify(payment), config)

      expect(result.valid).toBe(false)
      expect(result.reason).toContain('Invalid amount')
    })

    it('should reject incorrect currency', async () => {
      const payment = createMockPayment({ currency: 'BTC' })
      const config = DEFAULT_X402_CONFIG

      const result = await validateX402Payment(JSON.stringify(payment), config)

      expect(result.valid).toBe(false)
      expect(result.reason).toContain('Invalid currency')
    })

    it('should reject expired payment', async () => {
      const payment = createMockPayment({
        timestamp: Math.floor(Date.now() / 1000) - 400, // 400 seconds ago
      })
      const config = DEFAULT_X402_CONFIG

      const result = await validateX402Payment(JSON.stringify(payment), config)

      expect(result.valid).toBe(false)
      expect(result.reason).toContain('expired')
    })

    it('should reject invalid JSON', async () => {
      const config = DEFAULT_X402_CONFIG

      const result = await validateX402Payment('not valid json', config)

      expect(result.valid).toBe(false)
      expect(result.reason).toContain('Invalid payment format')
    })
  })

  describe('Replay Attack Prevention', () => {
    it('should detect replay attacks', () => {
      const paymentId = 'unique_payment_123'

      // First use should be OK
      const firstUse = isReplayAttack(paymentId)
      expect(firstUse).toBe(false)

      // Second use should be detected as replay
      const secondUse = isReplayAttack(paymentId)
      expect(secondUse).toBe(true)
    })

    it('should allow different payment IDs', () => {
      const firstUse = isReplayAttack('payment_1')
      expect(firstUse).toBe(false)

      const secondUse = isReplayAttack('payment_2')
      expect(secondUse).toBe(false)
    })
  })

  describe('validatePaymentAmount', () => {
    it('should validate correct amount', () => {
      const result = validatePaymentAmount(19, 19)
      expect(result.valid).toBe(true)
    })

    it('should reject insufficient payment', () => {
      const result = validatePaymentAmount(10, 19)
      expect(result.valid).toBe(false)
      expect(result.reason).toContain('Insufficient payment')
    })

    it('should reject overpayment', () => {
      const result = validatePaymentAmount(50, 19)
      expect(result.valid).toBe(false)
      expect(result.reason).toContain('Overpayment')
    })

    it('should accept amount within tolerance', () => {
      const result = validatePaymentAmount(20, 19, 1)
      expect(result.valid).toBe(true)
    })
  })

  describe('validatePaymentCurrency', () => {
    it('should accept USD', () => {
      const result = validatePaymentCurrency('USD')
      expect(result.valid).toBe(true)
    })

    it('should accept BTC and ETH', () => {
      expect(validatePaymentCurrency('BTC').valid).toBe(true)
      expect(validatePaymentCurrency('ETH').valid).toBe(true)
    })

    it('should reject unsupported currency', () => {
      const result = validatePaymentCurrency('EUR', ['USD', 'BTC', 'ETH'])
      expect(result.valid).toBe(false)
      expect(result.reason).toContain('Unsupported currency')
    })
  })

  describe('validatePaymentTimestamp', () => {
    it('should accept recent timestamp', () => {
      const now = Math.floor(Date.now() / 1000)
      const result = validatePaymentTimestamp(now)
      expect(result.valid).toBe(true)
    })

    it('should reject expired timestamp', () => {
      const old = Math.floor(Date.now() / 1000) - 400
      const result = validatePaymentTimestamp(old)
      expect(result.valid).toBe(false)
      expect(result.reason).toContain('expired')
    })

    it('should reject future timestamp', () => {
      const future = Math.floor(Date.now() / 1000) + 120
      const result = validatePaymentTimestamp(future)
      expect(result.valid).toBe(false)
      expect(result.reason).toContain('future')
    })
  })

  describe('validateWalletAddress', () => {
    it('should accept valid email-style address', () => {
      const result = validateWalletAddress('parse@kurult.ai', 'email')
      expect(result.valid).toBe(true)
    })

    it('should reject invalid email format', () => {
      const result = validateWalletAddress('invalid-email', 'email')
      expect(result.valid).toBe(false)
    })

    it('should reject empty address', () => {
      const result = validateWalletAddress('', 'email')
      expect(result.valid).toBe(false)
    })
  })

  describe('validatePaymentComprehensive', () => {
    it('should pass all validations', () => {
      const payment = createMockPayment()
      const config = DEFAULT_X402_CONFIG

      const result = validatePaymentComprehensive(payment, config)

      expect(result.valid).toBe(true)
      expect(result.proof).toEqual(payment)
    })

    it('should fail on first validation error', () => {
      const payment = createMockPayment({ payee: 'wrong@example.com' })
      const config = DEFAULT_X402_CONFIG

      const result = validatePaymentComprehensive(payment, config)

      expect(result.valid).toBe(false)
      expect(result.reason).toContain('Invalid payee')
    })
  })

  describe('getValidationErrorCode', () => {
    it('should return correct error codes', () => {
      expect(getValidationErrorCode('Invalid payee')).toBe('X402_INVALID_PAYEE')
      expect(getValidationErrorCode('Invalid amount')).toBe('X402_INVALID_AMOUNT')
      expect(getValidationErrorCode('Invalid currency')).toBe('X402_INVALID_CURRENCY')
      expect(getValidationErrorCode('Payment expired')).toBe('X402_PAYMENT_EXPIRED')
      expect(getValidationErrorCode('Invalid signature')).toBe('X402_INVALID_SIGNATURE')
      expect(getValidationErrorCode('replay attack')).toBe('X402_REPLAY_ATTACK')
    })

    it('should return generic code for unknown errors', () => {
      const code = getValidationErrorCode('Unknown error')
      expect(code).toBe('X402_VALIDATION_ERROR')
    })
  })
})

describe('x402 Payment Response', () => {
  describe('createPaymentRequiredResponse', () => {
    it('should create correct 402 response', () => {
      const config: X402Config = {
        payTo: 'parse@kurult.ai',
        amount: 19,
        currency: 'USD',
        description: 'Test payment',
        expiresInSeconds: 300,
      }

      const response = createPaymentRequiredResponse(config)

      expect(response.error).toBe('PAYMENT_REQUIRED')
      expect(response.x402.payTo).toBe('parse@kurult.ai')
      expect(response.x402.amount).toBe(19)
      expect(response.x402.currency).toBe('USD')
      expect(response.x402.description).toBe('Test payment')
      expect(response.x402.expiresAt).toBeDefined()
    })
  })
})

describe('Mock Payment Generation', () => {
  it('should generate valid mock payment for testing', () => {
    const payment = createMockPayment()

    expect(payment.paymentId).toMatch(/test_payment_\d+/)
    expect(payment.payer).toBe('test-agent@example.com')
    expect(payment.payee).toBe('parse@kurult.ai')
    expect(payment.amount).toBe(19)
    expect(payment.currency).toBe('USD')
    expect(payment.signature).toHaveLength(64)
  })

  it('should allow overrides', () => {
    const payment = createMockPayment({
      amount: 49,
      currency: 'BTC',
      payer: 'custom@example.com',
    })

    expect(payment.amount).toBe(49)
    expect(payment.currency).toBe('BTC')
    expect(payment.payer).toBe('custom@example.com')
  })
})
