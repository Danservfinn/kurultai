/**
 * POST /api/v1/agents/ad-detector
 * Detect undisclosed advertising in LLM-generated content
 * 
 * Request:
 * {
 *   "content": "LLM-generated text to analyze"
 * }
 * 
 * Response:
 * {
 *   "success": true,
 *   "data": {
 *     "adDetected": true,
 *     "riskScore": 0.75,
 *     "disclosureLabel": "⚠️ UNDLOSED ADVERTISING",
 *     "indicators": [...],
 *     "recommendation": "BLOCK"
 *   },
 *   "creditsUsed": 1,
 *   "creditsRemaining": 99
 * }
 */

import { NextRequest } from 'next/server'
import { testForAds, AdIndicator } from './pattern-analyzer'
import { detectAffiliateWithContext } from './affiliate-detector'

// API error response helper
function apiError(code: string, message: string, status: number = 400) {
  return Response.json(
    { success: false, error: { code, message } },
    { status }
  )
}

// API success response helper
function apiSuccess(data: any, creditsUsed: number = 1, creditsRemaining: number = 99) {
  return Response.json({
    success: true,
    data,
    creditsUsed,
    creditsRemaining,
  })
}

// Simple API key validation (placeholder - integrate with actual auth system)
async function validateAPIKey(request: NextRequest, requiredScopes: string[] = []) {
  const authHeader = request.headers.get('authorization')
  const apiKey = request.headers.get('x-api-key')
  
  if (!authHeader && !apiKey) {
    return {
      success: false,
      error: {
        code: 'UNAUTHORIZED',
        message: 'API key required',
        status: 401,
      },
    }
  }
  
  // TODO: Implement actual API key validation against database
  // For now, accept any non-empty key for development
  const key = apiKey || authHeader?.replace('Bearer ', '')
  
  if (!key || key.length < 10) {
    return {
      success: false,
      error: {
        code: 'INVALID_API_KEY',
        message: 'Invalid API key',
        status: 401,
      },
    }
  }
  
  return { success: true, apiKey: key }
}

export async function POST(request: NextRequest) {
  try {
    // Authenticate API key
    const auth = await validateAPIKey(request, ['agents'])
    if (!auth.success) {
      return apiError(auth.error!.code, auth.error!.message, auth.error!.status)
    }
    
    // Parse request body
    let body
    try {
      body = await request.json()
    } catch (parseError) {
      return apiError('INVALID_JSON', 'Request body must be valid JSON', 400)
    }
    
    const { content } = body
    
    // Validate input
    if (!content || typeof content !== 'string') {
      return apiError('INVALID_INPUT', 'Content field is required and must be a string', 400)
    }
    
    if (content.length === 0) {
      return apiError('EMPTY_CONTENT', 'Content cannot be empty', 400)
    }
    
    if (content.length > 50000) {
      return apiError('CONTENT_TOO_LONG', 'Content must be less than 50,000 characters', 400)
    }
    
    // Run ad detection
    const patternResult = testForAds(content)
    const affiliateResult = detectAffiliateWithContext(content)
    
    // Combine results
    const indicators: AdIndicator[] = [...patternResult.indicators]
    
    // Add affiliate indicator if not already present
    const hasAffiliateIndicator = indicators.some(i => i.type === 'affiliate_link')
    if (affiliateResult.hasAffiliateLinks && !hasAffiliateIndicator) {
      indicators.push({
        type: 'affiliate_link',
        confidence: affiliateResult.confidence,
        evidence: affiliateResult.links.map(l => `${l.network}: ${l.url}`).join(', '),
        weight: 0.9,
      })
    }
    
    // Calculate final risk score (combine pattern and affiliate detection)
    let riskScore = patternResult.riskScore
    
    // Boost risk score if affiliate links detected without disclosure
    if (affiliateResult.hasAffiliateLinks && !affiliateResult.disclosurePresent) {
      riskScore = Math.max(riskScore, affiliateResult.contextScore)
    }
    
    // Ensure risk score is capped at 1.0
    riskScore = Math.min(1, riskScore)
    
    // Determine final recommendation
    const recommendation = patternResult.recommendation === 'BLOCK' || 
                          affiliateResult.recommendation === 'BLOCK'
      ? 'BLOCK'
      : patternResult.recommendation === 'REVIEW' || affiliateResult.recommendation === 'REVIEW'
      ? 'REVIEW'
      : 'ALLOW'
    
    // Get disclosure label
    const disclosureLabel = getDisclosureLabel(riskScore)
    
    // Build response
    const responseData = {
      adDetected: recommendation === 'BLOCK' || recommendation === 'REVIEW',
      riskScore: Math.round(riskScore * 100) / 100, // Round to 2 decimal places
      disclosureLabel,
      indicators: indicators.map(i => ({
        type: i.type,
        confidence: Math.round(i.confidence * 100) / 100,
        evidence: i.evidence,
        weight: i.weight,
      })),
      recommendation,
      affiliateLinks: affiliateResult.links,
      affiliateDisclosurePresent: affiliateResult.disclosurePresent,
      executionTime: patternResult.executionTime,
    }
    
    // TODO: Deduct credits from user's account
    const creditsUsed = 1
    const creditsRemaining = 99 // Placeholder - fetch from actual user account
    
    return apiSuccess(responseData, creditsUsed, creditsRemaining)
    
  } catch (error) {
    console.error('Ad detector API error:', error)
    
    if (error instanceof Error) {
      return apiError('INTERNAL_ERROR', error.message, 500)
    }
    
    return apiError('INTERNAL_ERROR', 'An unexpected error occurred', 500)
  }
}

export async function GET() {
  return apiSuccess({
    name: 'Parse Ad Detector',
    version: '1.0.0',
    description: 'Detect undisclosed advertising in LLM-generated content',
    endpoints: {
      detect: 'POST /api/v1/agents/ad-detector',
    },
    indicators: [
      'affiliate_link',
      'brand_mention',
      'call_to_action',
      'pricing_language',
      'superlatives',
      'urgency',
      'missing_disclosure',
      'comparison_bias',
    ],
    recommendations: ['ALLOW', 'REVIEW', 'BLOCK'],
  })
}

/**
 * Get disclosure label based on risk score
 */
function getDisclosureLabel(riskScore: number): string {
  if (riskScore > 0.7) return '⚠️ UNDLOSED ADVERTISING'
  if (riskScore > 0.4) return '⚠️ POTENTIALLY PROMOTIONAL'
  if (riskScore > 0.2) return 'ℹ️ SOME COMMERCIAL CONTENT'
  return '✅ GENUINE CONTENT'
}
