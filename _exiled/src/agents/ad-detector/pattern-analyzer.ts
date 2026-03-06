/**
 * Parse Ad Detector — Pattern Analysis
 * Detect undisclosed advertising in LLM-generated content
 * 
 * @see https://docs.openclaw.ai for implementation patterns
 */

export type AdIndicatorType =
  | 'affiliate_link'
  | 'brand_mention'
  | 'call_to_action'
  | 'pricing_language'
  | 'superlatives'
  | 'urgency'
  | 'missing_disclosure'
  | 'comparison_bias'

export interface AdIndicator {
  type: AdIndicatorType
  confidence: number
  evidence: string
  weight: number
}

export interface PatternAnalysisResult {
  content: string
  indicators: AdIndicator[]
  patternScore: number
  executionTime: number
}

// Risk weights for each indicator type
const INDICATOR_WEIGHTS: Record<AdIndicatorType, number> = {
  affiliate_link: 0.9,
  brand_mention: 0.5,
  call_to_action: 0.6,
  pricing_language: 0.3,
  superlatives: 0.5,
  urgency: 0.6,
  missing_disclosure: 0.5,
  comparison_bias: 0.7,
}

// Affiliate link patterns
const AFFILIATE_PATTERNS = [
  /amazon\.com\/[^\s]*tag=[^\s]*/i,
  /amzn\.to\/[^\s]*/i,
  /shareasale\.com/i,
  /clickbank\.net/i,
  /cj\.com/i,
  /impact\.com/i,
  /ref=[^\s]*/i,
  /referral=[^\s]*/i,
  /affiliate=[^\s]*/i,
  /aff_id=[^\s]*/i,
  /\?aff=[^\s]*/i,
  /&aff=[^\s]*/i,
]

// Brand mention patterns (common tech/productivity brands)
const BRAND_PATTERNS = [
  /\b(notion|evernote|onenote|asana|trello|monday\.com|clickup)\b/gi,
  /\b(jasper|copy\.ai|writesonic|copywriting|grammarly|hemingway)\b/gi,
  /\b(shopify|woocommerce|magento|bigcommerce|squarespace)\b/gi,
  /\b(mailchimp|convertkit|activecampaign|klaviyo)\b/gi,
  /\b(hubspot|salesforce|pipedrive|zoho)\b/gi,
  /\b(slack|discord|zoom|teams|webex)\b/gi,
  /\b(aws|azure|gcp|digitalocean|heroku|vercel|netlify)\b/gi,
  /\b(stripe|paypal|square|gumroad|lemonsqueezy)\b/gi,
]

// Call-to-action phrases
const CTA_PATTERNS = [
  /\b(buy now|click here|sign up|register now|get started)\b/gi,
  /\b(try it free|start free trial|get yours|order now)\b/gi,
  /\b(shop now|learn more|see pricing|check it out)\b/gi,
  /\b(don't miss|grab yours|get access|join now)\b/gi,
]

// Pricing language patterns
const PRICING_PATTERNS = [
  /\$\d+(\.\d{2})?\s*(\/|\s*per\s*)(month|year|user)/gi,
  /\b(free trial|7 days free|14 days free|30 days free)\b/gi,
  /\b(discount|deal|offer|sale|promo|coupon)\b/gi,
  /\b(cheapest|affordable|budget-friendly|premium)\b/gi,
]

// Superlative patterns
const SUPERLATIVE_PATTERNS = [
  /\b(best|top|number one|#1|leading|industry leader)\b/gi,
  /\b(amazing|incredible|unmatched|unbeatable|perfect)\b/gi,
  /\b(highly recommend|must-have|game-changer|revolutionary)\b/gi,
]

// Urgency patterns
const URGENCY_PATTERNS = [
  /\b(limited time|act now|hurry|don't miss out|last chance)\b/gi,
  /\b(ending soon|expires|while supplies last|only a few left)\b/gi,
  /\b(special offer|today only|flash sale|exclusive deal)\b/gi,
]

// Disclosure patterns (looking for absence of these)
const DISCLOSURE_PATTERNS = [
  /\b(sponsored|advertisement|ad |affiliate|partnership)\b/gi,
  /\b(paid promotion|brand deal|collaboration|pr)\b/gi,
  /\b(i earn commissions|affiliate links|may earn)\b/gi,
]

/**
 * Analyze content for advertising patterns
 */
export function analyzeAdPatterns(content: string): AdIndicator[] {
  const indicators: AdIndicator[] = []
  const lowerContent = content.toLowerCase()

  // Check for affiliate links
  for (const pattern of AFFILIATE_PATTERNS) {
    const matches = content.match(pattern)
    if (matches && matches.length > 0) {
      indicators.push({
        type: 'affiliate_link',
        confidence: 0.95,
        evidence: matches[0],
        weight: INDICATOR_WEIGHTS.affiliate_link,
      })
      break // One affiliate link detection is enough
    }
  }

  // Check for brand mentions (multiple mentions of same brand)
  const brandMentions: Record<string, number> = {}
  for (const patternGroup of BRAND_PATTERNS) {
    const matches = lowerContent.match(patternGroup)
    if (matches) {
      for (const match of matches) {
        brandMentions[match.toLowerCase()] = (brandMentions[match.toLowerCase()] || 0) + 1
      }
    }
  }
  
  // If any brand is mentioned 2+ times, flag it
  for (const [brand, count] of Object.entries(brandMentions)) {
    if (count >= 2) {
      indicators.push({
        type: 'brand_mention',
        confidence: Math.min(0.9, 0.5 + (count * 0.1)),
        evidence: `"${brand}" mentioned ${count} times`,
        weight: INDICATOR_WEIGHTS.brand_mention,
      })
    }
  }

  // Check for call-to-action
  let ctaCount = 0
  for (const pattern of CTA_PATTERNS) {
    const matches = lowerContent.match(pattern)
    if (matches) {
      ctaCount += matches.length
    }
  }
  if (ctaCount > 0) {
    indicators.push({
      type: 'call_to_action',
      confidence: Math.min(0.9, 0.5 + (ctaCount * 0.1)),
      evidence: `${ctaCount} call-to-action phrase(s) detected`,
      weight: INDICATOR_WEIGHTS.call_to_action,
    })
  }

  // Check for pricing language
  let pricingCount = 0
  for (const pattern of PRICING_PATTERNS) {
    const matches = lowerContent.match(pattern)
    if (matches) {
      pricingCount += matches.length
    }
  }
  if (pricingCount > 0) {
    indicators.push({
      type: 'pricing_language',
      confidence: Math.min(0.8, 0.4 + (pricingCount * 0.1)),
      evidence: `${pricingCount} pricing-related phrase(s) detected`,
      weight: INDICATOR_WEIGHTS.pricing_language,
    })
  }

  // Check for superlatives
  let superlativeCount = 0
  for (const pattern of SUPERLATIVE_PATTERNS) {
    const matches = lowerContent.match(pattern)
    if (matches) {
      superlativeCount += matches.length
    }
  }
  if (superlativeCount > 0) {
    indicators.push({
      type: 'superlatives',
      confidence: Math.min(0.85, 0.5 + (superlativeCount * 0.1)),
      evidence: `${superlativeCount} superlative(s) detected`,
      weight: INDICATOR_WEIGHTS.superlatives,
    })
  }

  // Check for urgency
  let urgencyCount = 0
  for (const pattern of URGENCY_PATTERNS) {
    const matches = lowerContent.match(pattern)
    if (matches) {
      urgencyCount += matches.length
    }
  }
  if (urgencyCount > 0) {
    indicators.push({
      type: 'urgency',
      confidence: Math.min(0.85, 0.5 + (urgencyCount * 0.1)),
      evidence: `${urgencyCount} urgency phrase(s) detected`,
      weight: INDICATOR_WEIGHTS.urgency,
    })
  }

  // Check for missing disclosure
  let hasDisclosure = false
  for (const pattern of DISCLOSURE_PATTERNS) {
    if (pattern.test(lowerContent)) {
      hasDisclosure = true
      break
    }
  }
  
  // If we have other indicators but no disclosure, flag it
  if (indicators.length > 0 && !hasDisclosure) {
    indicators.push({
      type: 'missing_disclosure',
      confidence: 0.8,
      evidence: 'No sponsorship/affiliate disclosure found',
      weight: INDICATOR_WEIGHTS.missing_disclosure,
    })
  }

  // Check for comparison bias (one product heavily favored)
  const comparisonBias = detectComparisonBias(content)
  if (comparisonBias) {
    indicators.push(comparisonBias)
  }

  return indicators
}

/**
 * Detect comparison bias in content
 */
function detectComparisonBias(content: string): AdIndicator | null {
  const lowerContent = content.toLowerCase()
  
  // Look for comparison patterns
  const comparisonKeywords = ['better than', 'vs', 'versus', 'compared to', 'over', 'instead of']
  let hasComparison = false
  
  for (const keyword of comparisonKeywords) {
    if (lowerContent.includes(keyword)) {
      hasComparison = true
      break
    }
  }

  if (!hasComparison) {
    return null
  }

  // Check if one product is heavily favored without justification
  const positiveWords = ['best', 'amazing', 'perfect', 'excellent', 'superior', 'unmatched']
  const negativeWords = ['worst', 'terrible', 'awful', 'poor', 'inferior', 'disappointing']
  
  let positiveCount = 0
  let negativeCount = 0
  
  for (const word of positiveWords) {
    const matches = lowerContent.match(new RegExp(`\\b${word}\\b`, 'g'))
    if (matches) positiveCount += matches.length
  }
  
  for (const word of negativeWords) {
    const matches = lowerContent.match(new RegExp(`\\b${word}\\b`, 'g'))
    if (matches) negativeCount += matches.length
  }

  // If heavily positive with little negative, flag bias
  if (positiveCount >= 2 && negativeCount === 0) {
    return {
      type: 'comparison_bias',
      confidence: 0.7,
      evidence: `Heavily positive comparison (${positiveCount} positive, ${negativeCount} negative points)`,
      weight: INDICATOR_WEIGHTS.comparison_bias,
    }
  }

  return null
}

/**
 * Calculate pattern-based risk score
 */
export function calculatePatternScore(indicators: AdIndicator[]): number {
  if (indicators.length === 0) {
    return 0
  }

  // Calculate weighted average
  let totalWeight = 0
  let weightedSum = 0

  for (const indicator of indicators) {
    const contribution = indicator.confidence * indicator.weight
    weightedSum += contribution
    totalWeight += indicator.weight
  }

  // Normalize to 0-1 range
  const score = totalWeight > 0 ? weightedSum / totalWeight : 0
  
  // Boost score if affiliate link is present (high confidence indicator)
  const hasAffiliateLink = indicators.some(i => i.type === 'affiliate_link')
  if (hasAffiliateLink) {
    return Math.max(score, 0.9)
  }

  return Math.min(1, score)
}

/**
 * Get recommendation based on risk score
 */
export function getRecommendation(riskScore: number): 'ALLOW' | 'REVIEW' | 'BLOCK' {
  if (riskScore > 0.7) return 'BLOCK'     // Undisclosed advertising
  if (riskScore > 0.4) return 'REVIEW'    // Potentially promotional
  return 'ALLOW'                           // Genuine content
}

/**
 * Get disclosure label for UI display
 */
export function getDisclosureLabel(riskScore: number): string {
  if (riskScore > 0.7) return '⚠️ UNDLOSED ADVERTISING'
  if (riskScore > 0.4) return '⚠️ POTENTIALLY PROMOTIONAL'
  if (riskScore > 0.2) return 'ℹ️ SOME COMMERCIAL CONTENT'
  return '✅ GENUINE CONTENT'
}

/**
 * Main pattern analysis function
 */
export function analyzePatterns(content: string): PatternAnalysisResult {
  const startTime = Date.now()
  
  const indicators = analyzeAdPatterns(content)
  const patternScore = calculatePatternScore(indicators)
  
  const executionTime = Date.now() - startTime

  return {
    content,
    indicators,
    patternScore,
    executionTime,
  }
}

/**
 * Full ad detection test (pattern analysis only)
 */
export interface AdTestResult {
  content: string
  indicators: AdIndicator[]
  riskScore: number
  recommendation: 'ALLOW' | 'REVIEW' | 'BLOCK'
  disclosureLabel: string
  executionTime: number
}

export function testForAds(content: string): AdTestResult {
  const patternResult = analyzePatterns(content)
  const riskScore = patternResult.patternScore
  const recommendation = getRecommendation(riskScore)
  const disclosureLabel = getDisclosureLabel(riskScore)

  return {
    content,
    indicators: patternResult.indicators,
    riskScore,
    recommendation,
    disclosureLabel,
    executionTime: patternResult.executionTime,
  }
}
