/**
 * x402 Payment Middleware
 * 
 * Wraps Next.js API routes to require x402 payment before processing
 * 
 * Usage:
 * ```typescript
 * export const POST = withX402Payment(
 *   async (request: NextRequest, payment) => {
 *     // Payment validated, process request
 *     return NextResponse.json({ success: true })
 *   },
 *   {
 *     payTo: 'parse@kurult.ai',
 *     amount: 19,
 *     currency: 'USD',
 *     description: 'Agent analysis',
 *     expiresInSeconds: 300
 *   }
 * )
 * ```
 */

import { NextRequest, NextResponse } from 'next/server'
import {
  validateX402Payment,
  validatePaymentComprehensive,
  X402Config,
  X402PaymentProof,
  X402ValidationResult,
  recordX402Payment,
  createPaymentRequiredResponse,
  DEFAULT_X402_CONFIG,
} from '@/lib/x402/payment'
import { getValidationErrorCode } from '@/lib/x402/validation'

/**
 * Handler function type for x402-protected routes
 */
export type X402Handler = (
  request: NextRequest,
  payment: X402PaymentProof
) => Promise<NextResponse>

/**
 * x402 Payment Middleware Options
 */
export interface X402MiddlewareOptions {
  /** Whether to record payment after successful validation (default: true) */
  recordPayment?: boolean
  
  /** Custom user ID extractor (default: extract from payment payer) */
  extractUserId?: (payment: X402PaymentProof) => string
  
  /** Skip payment validation in development (default: false) */
  skipValidation?: boolean
}

/**
 * x402 Payment Middleware
 * 
 * Wraps API routes to require x402 payment before processing
 * 
 * @param handler - The actual request handler (receives validated payment)
 * @param config - x402 payment configuration
 * @param options - Middleware options
 * @returns Wrapped handler that enforces payment
 */
export function withX402Payment(
  handler: X402Handler,
  config: X402Config = DEFAULT_X402_CONFIG,
  options: X402MiddlewareOptions = {}
) {
  const {
    recordPayment = true,
    extractUserId,
    skipValidation = false,
  } = options

  return async function (request: NextRequest): Promise<NextResponse> {
    // Check for payment proof header
    const paymentProof = request.headers.get('X-Payment-Proof')
    
    // No payment provided - return 402 with payment instructions
    if (!paymentProof) {
      return NextResponse.json(createPaymentRequiredResponse(config), {
        status: 402,
        headers: {
          'X-Payment-Required': 'true',
          'Content-Type': 'application/json',
        },
      })
    }
    
    // Development mode: skip validation if configured
    if (skipValidation && process.env.NODE_ENV === 'development') {
      console.log('[x402] Skipping validation in development mode')
      
      // Create mock payment for development
      const mockPayment: X402PaymentProof = {
        paymentId: `dev_${Date.now()}`,
        payer: 'dev@example.com',
        payee: config.payTo,
        amount: config.amount,
        currency: config.currency,
        timestamp: Math.floor(Date.now() / 1000),
        signature: 'dev_signature_placeholder',
      }
      
      // Call handler with mock payment
      return await handler(request, mockPayment)
    }
    
    // Validate payment
    let validation: X402ValidationResult
    
    try {
      // Use comprehensive validation
      const parsedProof: unknown = JSON.parse(paymentProof)
      
      if (typeof parsedProof !== 'object' || parsedProof === null) {
        throw new Error('Payment proof must be a JSON object')
      }
      
      validation = validatePaymentComprehensive(
        parsedProof as X402PaymentProof,
        config
      )
    } catch (error) {
      return NextResponse.json(
        {
          error: 'PAYMENT_INVALID',
          code: 'X402_INVALID_FORMAT',
          reason: error instanceof Error ? error.message : 'Invalid JSON',
        },
        {
          status: 402,
          headers: { 'Content-Type': 'application/json' },
        }
      )
    }
    
    // Payment validation failed
    if (!validation.valid) {
      const errorCode = getValidationErrorCode(validation.reason || '')
      
      return NextResponse.json(
        {
          error: 'PAYMENT_INVALID',
          code: errorCode,
          reason: validation.reason,
        },
        {
          status: 402,
          headers: {
            'Content-Type': 'application/json',
            'X-Validation-Error': errorCode,
          },
        }
      )
    }
    
    // Payment is valid - extract proof
    const proof = validation.proof!
    
    // Record payment for accounting (if enabled)
    if (recordPayment) {
      try {
        const userId = extractUserId ? extractUserId(proof) : proof.payer
        const endpoint = new URL(request.url).pathname
        
        // Record asynchronously (don't block response)
        recordX402Payment(proof, endpoint, userId).catch((err) => {
          console.error('[x402] Failed to record payment:', err)
        })
      } catch (error) {
        console.error('[x402] Error recording payment:', error)
        // Don't fail the request if recording fails
      }
    }
    
    // Call the actual handler with validated payment
    try {
      return await handler(request, proof)
    } catch (error) {
      // Handler error - return 500
      console.error('[x402] Handler error:', error)
      
      return NextResponse.json(
        {
          error: 'INTERNAL_ERROR',
          message: error instanceof Error ? error.message : 'Unknown error',
          payment: {
            received: true,
            amount: proof.amount,
            transactionId: proof.paymentId,
          },
        },
        {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        }
      )
    }
  }
}

/**
 * Create x402 payment headers for client requests
 * 
 * Utility for testing and client implementations
 * 
 * @param paymentProof - Payment proof object
 * @returns Headers object
 */
export function createX402Headers(paymentProof: X402PaymentProof): HeadersInit {
  return {
    'Content-Type': 'application/json',
    'X-Payment-Proof': JSON.stringify(paymentProof),
  }
}

/**
 * Check if request has x402 payment
 * 
 * @param request - Next.js request
 * @returns True if payment proof is present
 */
export function hasX402Payment(request: NextRequest): boolean {
  return request.headers.has('X-Payment-Proof')
}

/**
 * Extract x402 payment proof from request
 * 
 * @param request - Next.js request
 * @returns Payment proof or null if not present
 */
export function extractX402Payment(request: NextRequest): X402PaymentProof | null {
  const paymentProof = request.headers.get('X-Payment-Proof')
  
  if (!paymentProof) {
    return null
  }
  
  try {
    return JSON.parse(paymentProof) as X402PaymentProof
  } catch {
    return null
  }
}

/**
 * x402 Payment Response Helpers
 */
export const x402Response = {
  /**
   * Create 402 Payment Required response
   */
  required(config: X402Config = DEFAULT_X402_CONFIG) {
    return NextResponse.json(createPaymentRequiredResponse(config), {
      status: 402,
      headers: {
        'X-Payment-Required': 'true',
        'Content-Type': 'application/json',
      },
    })
  },
  
  /**
   * Create payment invalid response
   */
  invalid(reason: string, code?: string) {
    return NextResponse.json(
      {
        error: 'PAYMENT_INVALID',
        code: code || getValidationErrorCode(reason),
        reason,
      },
      {
        status: 402,
        headers: { 'Content-Type': 'application/json' },
      }
    )
  },
  
  /**
   * Create payment success response (include payment info)
   */
  success(data: unknown, payment: X402PaymentProof) {
    return NextResponse.json(
      {
        success: true,
        data,
        payment: {
          received: true,
          amount: payment.amount,
          currency: payment.currency,
          transactionId: payment.paymentId,
        },
      },
      {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }
    )
  },
}
