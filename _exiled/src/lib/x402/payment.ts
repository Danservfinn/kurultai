/**
 * Parse x402 Payment Integration
 * Enable agent-to-agent autonomous payments
 * 
 * @see https://github.com/x402/x402
 * @see https://www.npmjs.com/package/@x402/sdk
 */

import { z } from 'zod'

/**
 * x402 payment configuration
 */
export interface X402Config {
  /** Parse's x402 wallet address */
  payTo: string
  
  /** Amount in cents (1 credit = $0.19 for Pro tier) */
  amount: number
  
  /** Currency */
  currency: 'USD' | 'BTC' | 'ETH'
  
  /** Payment description */
  description: string
  
  /** Payment expires in (seconds) */
  expiresInSeconds: number
}

/**
 * Default x402 configuration for Parse
 * Uses Pro tier pricing: $0.19 per credit
 */
export const DEFAULT_X402_CONFIG: X402Config = {
  payTo: 'parse@kurult.ai',
  amount: 19, // $0.19 per credit (Pro tier pricing)
  currency: 'USD',
  description: 'Parse agent analysis',
  expiresInSeconds: 300, // 5 minutes
}

/**
 * Pricing tiers for x402 payments
 */
export const X402_PRICING_TIERS = {
  FREE: { amount: 10, description: 'Free tier (10 cents/credit)' },
  PRO: { amount: 19, description: 'Pro tier (19 cents/credit)' },
  MAX: { amount: 49, description: 'Max tier (49 cents/credit)' },
  ENTERPRISE: { amount: 0, description: 'Custom negotiated pricing' },
}

/**
 * x402 payment proof schema
 * Validates the structure of payment proofs sent by agent clients
 */
export const X402PaymentProofSchema = z.object({
  /** Unique payment ID */
  paymentId: z.string(),
  
  /** Payer wallet address */
  payer: z.string(),
  
  /** Payee wallet address (should match Parse's wallet) */
  payee: z.string(),
  
  /** Amount in cents */
  amount: z.number(),
  
  /** Currency */
  currency: z.enum(['USD', 'BTC', 'ETH']),
  
  /** Unix timestamp (seconds) */
  timestamp: z.number(),
  
  /** Cryptographic signature */
  signature: z.string(),
  
  /** Network (testnet/mainnet) */
  network: z.enum(['testnet', 'mainnet']).optional(),
})

export type X402PaymentProof = z.infer<typeof X402PaymentProofSchema>

/**
 * x402 validation result
 */
export interface X402ValidationResult {
  /** Whether payment is valid */
  valid: boolean
  
  /** Reason if invalid */
  reason?: string
  
  /** Validated payment proof */
  proof?: X402PaymentProof
}

/**
 * x402 transaction record for accounting
 */
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
 * Validate x402 payment proof
 * 
 * @param paymentProof - JSON string containing payment proof
 * @param config - Expected payment configuration
 * @returns Validation result with proof if valid
 */
export async function validateX402Payment(
  paymentProof: string,
  config: X402Config
): Promise<X402ValidationResult> {
  try {
    // Parse payment proof
    const proof: unknown = JSON.parse(paymentProof)
    const validated = X402PaymentProofSchema.parse(proof)
    
    // Verify payee matches Parse
    if (validated.payee !== config.payTo) {
      return {
        valid: false,
        reason: `Invalid payee: expected ${config.payTo}, got ${validated.payee}`,
      }
    }
    
    // Verify amount matches
    if (validated.amount !== config.amount) {
      return {
        valid: false,
        reason: `Invalid amount: expected ${config.amount}, got ${validated.amount}`,
      }
    }
    
    // Verify currency matches
    if (validated.currency !== config.currency) {
      return {
        valid: false,
        reason: `Invalid currency: expected ${config.currency}, got ${validated.currency}`,
      }
    }
    
    // Verify signature (cryptographic validation)
    const signatureValid = await verifyX402Signature(validated)
    if (!signatureValid) {
      return {
        valid: false,
        reason: 'Invalid signature',
      }
    }
    
    // Verify not expired (5 minute window)
    const now = Math.floor(Date.now() / 1000)
    const age = now - validated.timestamp
    if (age > 300) {
      return {
        valid: false,
        reason: 'Payment expired (older than 5 minutes)',
      }
    }
    
    // Payment is valid
    return {
      valid: true,
      proof: validated,
    }
  } catch (error) {
    return {
      valid: false,
      reason: error instanceof Error ? error.message : 'Invalid payment format',
    }
  }
}

/**
 * Verify x402 signature
 * 
 * TODO: Implement actual cryptographic verification
 * This would use the payer's public key to verify the signature
 * 
 * @param proof - Payment proof to verify
 * @returns True if signature is valid
 */
async function verifyX402Signature(proof: X402PaymentProof): Promise<boolean> {
  // TODO: Implement actual signature verification
  // This requires:
  // 1. Access to payer's public key (from x402 registry or DID document)
  // 2. Cryptographic verification using the signature algorithm
  // 3. Verification that signature covers: paymentId + payer + payee + amount + timestamp
  
  // Placeholder for development/testing
  // In production, this MUST be replaced with actual crypto verification
  console.log(`[x402] Signature verification placeholder for payment: ${proof.paymentId}`)
  return true
}

/**
 * Record x402 payment for accounting
 * 
 * @param proof - Validated payment proof
 * @param endpoint - API endpoint that was called
 * @param userId - User/agent identifier
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
  
  const transaction: X402Transaction = {
    transactionId: proof.paymentId,
    payer: proof.payer,
    payee: proof.payee,
    amount: proof.amount,
    currency: proof.currency,
    endpoint,
    timestamp: new Date(proof.timestamp * 1000),
    status: 'completed',
  }
  
  console.log(`[x402] Payment recorded:`, transaction)
  
  // TODO: Insert into database
  // await db.x402Transactions.create(transaction)
}

/**
 * Get x402 config for specific endpoint
 * 
 * Different endpoints may have different pricing
 * 
 * @param endpoint - API endpoint path
 * @returns x402 configuration for that endpoint
 */
export function getX402ConfigForEndpoint(endpoint: string): X402Config {
  // Default to Pro tier pricing
  const baseConfig = { ...DEFAULT_X402_CONFIG }
  
  // Customize description based on endpoint
  if (endpoint.includes('bernays')) {
    baseConfig.description = 'Bernays agent analysis (1 credit)'
  } else if (endpoint.includes('prompt-injection')) {
    baseConfig.description = 'Prompt injection detection (1 credit)'
  } else if (endpoint.includes('ad-detector')) {
    baseConfig.description = 'Ad detection analysis (1 credit)'
  }
  
  return baseConfig
}

/**
 * Create x402 payment required response
 * 
 * @param config - Payment configuration
 * @returns Response object for 402 Payment Required
 */
export function createPaymentRequiredResponse(config: X402Config) {
  return {
    error: 'PAYMENT_REQUIRED',
    x402: {
      payTo: config.payTo,
      amount: config.amount,
      currency: config.currency,
      description: config.description,
      expiresAt: new Date(Date.now() + config.expiresInSeconds * 1000).toISOString(),
    },
  }
}
