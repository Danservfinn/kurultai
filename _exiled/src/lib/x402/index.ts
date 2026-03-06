/**
 * x402 Payment Integration
 * 
 * Complete x402 payment support for Parse API
 * Enables AI agents to pay for services autonomously
 * 
 * @module @/lib/x402
 * 
 * @example
 * ```typescript
 * // Import payment utilities
 * import { validateX402Payment, DEFAULT_X402_CONFIG } from '@/lib/x402'
 * 
 * // Import middleware
 * import { withX402Payment } from '@/middleware/x402-payment'
 * 
 * // Import mock payment for testing
 * import { createMockPayment } from '@/lib/x402/mock-payment'
 * ```
 */

// Payment types and validation
export {
  validateX402Payment,
  recordX402Payment,
  getX402ConfigForEndpoint,
  createPaymentRequiredResponse,
  DEFAULT_X402_CONFIG,
  X402_PRICING_TIERS,
  X402PaymentProofSchema,
} from './payment'

export type {
  X402Config,
  X402PaymentProof,
  X402ValidationResult,
  X402Transaction,
} from './payment'

// Additional validation utilities
export {
  isReplayAttack,
  validatePaymentAmount,
  validatePaymentCurrency,
  validatePaymentTimestamp,
  validateWalletAddress,
  validatePaymentComprehensive,
  validateSignatureStructure,
  getValidationErrorCode,
} from './validation'

// Mock payment utilities (for testing)
export {
  createMockPayment,
  createMockPaymentHeader,
  testPaymentFlow,
  testScenarios,
  runAllTestScenarios,
  generateCurlCommand,
  generateTestDocumentation,
} from './mock-payment'

export type {
  PaymentFlowResult,
} from './mock-payment'
