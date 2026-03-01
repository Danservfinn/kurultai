/**
 * POST /api/v1/agents/bernays
 * 
 * Bernays Agent - Rhetorical Analysis with x402 Payment
 * 
 * This endpoint demonstrates x402 payment integration.
 * Agents must send payment proof to access the analysis.
 * 
 * @see https://github.com/x402/x402
 */

import { NextRequest } from 'next/server'
import { withX402Payment, x402Response } from '@/middleware/x402-payment'
import { X402PaymentProof } from '@/lib/x402/payment'
import { apiSuccess, apiError } from '@/lib/api-response'

/**
 * Bernays Agent Analysis Request
 */
interface BernaysRequest {
  url: string
  options?: {
    includeSources?: boolean
    maxDepth?: number
  }
}

/**
 * Bernays Agent Analysis Result
 */
interface BernaysResult {
  bernaysScore: number
  techniques: string[]
  confidence: number
  analysis: string
  sources?: string[]
}

/**
 * Mock Bernays agent implementation
 * 
 * TODO: Replace with actual Bernays agent logic
 */
async function runBernaysAgent(request: BernaysRequest): Promise<BernaysResult> {
  // Placeholder implementation
  // TODO: Implement actual Bernays analysis
  
  return {
    bernaysScore: 0.72,
    techniques: ['appeal to authority', 'false dilemma', 'emotional appeal'],
    confidence: 0.85,
    analysis: 'Content contains multiple persuasive techniques characteristic of Bernays-style propaganda.',
    sources: request.options?.includeSources ? ['source1', 'source2'] : undefined,
  }
}

/**
 * POST handler with x402 payment protection
 * 
 * The withX402Payment middleware:
 * 1. Checks for X-Payment-Proof header
 * 2. Validates payment against config
 * 3. Rejects with 402 if payment is missing/invalid
 * 4. Calls handler with validated payment if valid
 */
export const POST = withX402Payment(
  async (request: NextRequest, payment: X402PaymentProof) => {
    // Payment has been validated - proceed with request
    
    // Parse request body
    let body: BernaysRequest
    try {
      body = await request.json()
    } catch (error) {
      return apiError('INVALID_REQUEST', 'Invalid JSON', 400)
    }
    
    // Validate required fields
    if (!body.url || typeof body.url !== 'string') {
      return apiError('INVALID_REQUEST', 'URL is required', 400)
    }
    
    // Run Bernays agent analysis
    try {
      const result = await runBernaysAgent(body)
      
      // Return success with payment info
      return apiSuccess(result, {
        payment: {
          received: true,
          amount: payment.amount,
          currency: payment.currency,
          transactionId: payment.paymentId,
        },
      })
    } catch (error) {
      // Analysis failed, but payment was already received
      console.error('[Bernays] Analysis error:', error)
      
      return apiError(
        'ANALYSIS_ERROR',
        error instanceof Error ? error.message : 'Analysis failed',
        500,
        {
          payment: {
            received: true,
            amount: payment.amount,
            transactionId: payment.paymentId,
          },
        }
      )
    }
  },
  
  // x402 Payment Configuration
  {
    payTo: 'parse@kurult.ai',
    amount: 19, // $0.19 per credit (Pro tier pricing)
    currency: 'USD',
    description: 'Bernays agent analysis (1 credit)',
    expiresInSeconds: 300, // 5 minutes
  },
  
  // Middleware Options
  {
    recordPayment: true, // Record payment for accounting
    skipValidation: process.env.NODE_ENV === 'development', // Skip in dev
  }
)

/**
 * GET handler - Returns payment requirements
 * 
 * Allows clients to discover payment requirements before sending request
 */
export const GET = () => {
  return x402Response.required({
    payTo: 'parse@kurult.ai',
    amount: 19,
    currency: 'USD',
    description: 'Bernays agent analysis (1 credit)',
    expiresInSeconds: 300,
  })
}
