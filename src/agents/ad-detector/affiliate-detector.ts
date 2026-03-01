/**
 * Parse Ad Detector — Affiliate Link Detection
 * Specialized detection for affiliate marketing links
 */

import { AdIndicator } from './pattern-analyzer'

export interface AffiliateLinkInfo {
  url: string
  network: string
  confidence: number
  evidence: string
}

export interface AffiliateDetectionResult {
  hasAffiliateLinks: boolean
  links: AffiliateLinkInfo[]
  confidence: number
}

// Affiliate network patterns
const AFFILIATE_NETWORKS: Array<{ pattern: RegExp; name: string }> = [
  { pattern: /amazon\.com\/[^\s]*tag=[^\s]*/i, name: 'Amazon Associates' },
  { pattern: /amzn\.to\/[^\s]*/i, name: 'Amazon Short Link' },
  { pattern: /shareasale\.com/i, name: 'ShareASale' },
  { pattern: /clickbank\.net/i, name: 'ClickBank' },
  { pattern: /cj\.com/i, name: 'Commission Junction' },
  { pattern: /impact\.com/i, name: 'Impact' },
  { pattern: /rakuten\.com/i, name: 'Rakuten' },
  { pattern: /awin\.com/i, name: 'Awin' },
  { pattern: /partnerstack\.com/i, name: 'PartnerStack' },
  { pattern: /refersion\.com/i, name: 'Refersion' },
  { pattern: /postaffiliatepro\.com/i, name: 'Post Affiliate Pro' },
  { pattern: /tapfiliate\.com/i, name: 'Tapfiliate' },
  { pattern: /affiliate\.com/i, name: 'Affiliate.com' },
  { pattern: /skimlinks\.com/i, name: 'Skimlinks' },
  { pattern: /skimresources\.com/i, name: 'Skimresources' },
  { pattern: /sailthru\.com/i, name: 'Sailthru' },
  { pattern: /linkshare\.com/i, name: 'LinkShare' },
  { pattern: /flexoffers\.com/i, name: 'FlexOffers' },
  { pattern: /epicplay\.com/i, name: 'Epic Play' },
  { pattern: /digi store24\.com/i, name: 'Digistore24' },
]

// URL parameter patterns indicating affiliate links
const AFFILIATE_PARAM_PATTERNS = [
  /\btag=/i,
  /\bref=/i,
  /\baffiliate=/i,
  /\baff_id=/i,
  /\baffiliate_id=/i,
  /\bpartner=/i,
  /\bpartner_id=/i,
  /\breferral=/i,
  /\breferral_id=/i,
  /\btracking_id=/i,
  /\btracking=/i,
  /\baffiliate_code=/i,
  /\baff=/i,
  /\bpid=/i, // Partner ID
  /\bsource=/i, // When combined with other affiliate indicators
  /\bcampaign=/i, // When combined with other affiliate indicators
]

// Common affiliate URL structures
const AFFILIATE_URL_PATTERNS = [
  /go\.[^\/]+\//i, // go.domain.com/
  /get\.[^\/]+\//i, // get.domain.com/
  /try\.[^\/]+\//i, // try.domain.com/
  /link\.[^\/]+\//i, // link.domain.com/
  /track\.[^\/]+\//i, // track.domain.com/
  /click\.[^\/]+\//i, // click.domain.com/
  /redirect\.[^\/]+\//i, // redirect.domain.com/
  /r\.([^\/]+)\//i, // r.domain.com/
  /u\.([^\/]+)\//i, // u.domain.com/
]

/**
 * Extract all URLs from content
 */
function extractUrls(content: string): string[] {
  const urlPattern = /(https?:\/\/[^\s<>"{}|\\^`\[\]]+)/gi
  const matches = content.match(urlPattern)
  return matches || []
}

/**
 * Check if a URL contains affiliate parameters
 */
function hasAffiliateParams(url: string): boolean {
  for (const pattern of AFFILIATE_PARAM_PATTERNS) {
    if (pattern.test(url)) {
      return true
    }
  }
  return false
}

/**
 * Identify affiliate network from URL
 */
function identifyNetwork(url: string): string {
  for (const { pattern, name } of AFFILIATE_NETWORKS) {
    if (pattern.test(url)) {
      return name
    }
  }
  
  // Check for common affiliate URL structures
  for (const pattern of AFFILIATE_URL_PATTERNS) {
    if (pattern.test(url)) {
      return 'Affiliate Redirect'
    }
  }
  
  return 'Unknown Affiliate'
}

/**
 * Calculate confidence score for affiliate link
 */
function calculateConfidence(url: string): number {
  let confidence = 0.5 // Base confidence for matching pattern
  
  // Boost confidence for known networks
  for (const { pattern, name } of AFFILIATE_NETWORKS) {
    if (pattern.test(url)) {
      if (name.includes('Amazon')) {
        confidence = 0.98 // Amazon affiliate links are very reliable
      } else {
        confidence = 0.9 // Other known networks
      }
      break
    }
  }
  
  // Check for multiple affiliate indicators
  let indicatorCount = 0
  for (const pattern of AFFILIATE_PARAM_PATTERNS) {
    if (pattern.test(url)) {
      indicatorCount++
    }
  }
  
  if (indicatorCount >= 2) {
    confidence = Math.max(confidence, 0.95)
  } else if (indicatorCount === 1) {
    confidence = Math.max(confidence, 0.85)
  }
  
  return Math.min(1, confidence)
}

/**
 * Detect affiliate links in content
 */
export function detectAffiliateLinks(content: string): AffiliateDetectionResult {
  const urls = extractUrls(content)
  const links: AffiliateLinkInfo[] = []
  
  for (const url of urls) {
    // Check if URL matches affiliate patterns
    let isAffiliate = false
    let network = 'Unknown'
    let evidence = ''
    
    // Check against known affiliate networks
    for (const { pattern, name } of AFFILIATE_NETWORKS) {
      if (pattern.test(url)) {
        isAffiliate = true
        network = name
        evidence = `Matches ${name} pattern`
        break
      }
    }
    
    // Check for affiliate parameters
    if (!isAffiliate && hasAffiliateParams(url)) {
      isAffiliate = true
      network = 'Parameter-based Affiliate'
      evidence = 'Contains affiliate tracking parameters'
    }
    
    // Check for affiliate URL structures
    if (!isAffiliate) {
      for (const pattern of AFFILIATE_URL_PATTERNS) {
        if (pattern.test(url)) {
          isAffiliate = true
          network = 'Affiliate Redirect'
          evidence = 'Matches affiliate redirect URL structure'
          break
        }
      }
    }
    
    if (isAffiliate) {
      const confidence = calculateConfidence(url)
      links.push({
        url,
        network,
        confidence,
        evidence,
      })
    }
  }
  
  return {
    hasAffiliateLinks: links.length > 0,
    links,
    confidence: links.length > 0 
      ? Math.max(...links.map(l => l.confidence))
      : 0,
  }
}

/**
 * Create affiliate link indicator for pattern analyzer
 */
export function createAffiliateIndicator(result: AffiliateDetectionResult): AdIndicator | null {
  if (!result.hasAffiliateLinks || result.links.length === 0) {
    return null
  }
  
  const topLink = result.links[0]
  
  return {
    type: 'affiliate_link',
    confidence: topLink.confidence,
    evidence: `${topLink.network}: ${topLink.url}`,
    weight: 0.9, // High weight for affiliate links
  }
}

/**
 * Enhanced affiliate detection with context analysis
 */
export interface EnhancedAffiliateResult extends AffiliateDetectionResult {
  contextScore: number
  disclosurePresent: boolean
  recommendation: 'ALLOW' | 'REVIEW' | 'BLOCK'
}

export function detectAffiliateWithContext(content: string): EnhancedAffiliateResult {
  const baseResult = detectAffiliateLinks(content)
  const lowerContent = content.toLowerCase()
  
  // Check for disclosure
  const disclosurePatterns = [
    /\b(affiliate link|affiliate disclosure|disclosure)\b/i,
    /\b(i earn commissions|may earn commission)\b/i,
    /\b(sponsored|partnership|paid promotion)\b/i,
    /\b(affiliate marketing|affiliate program)\b/i,
  ]
  
  let disclosurePresent = false
  for (const pattern of disclosurePatterns) {
    if (pattern.test(lowerContent)) {
      disclosurePresent = true
      break
    }
  }
  
  // Calculate context score
  let contextScore = 0
  
  // Base score from affiliate detection
  if (baseResult.hasAffiliateLinks) {
    contextScore += baseResult.confidence * 0.6
  }
  
  // No disclosure increases score
  if (baseResult.hasAffiliateLinks && !disclosurePresent) {
    contextScore += 0.4
  }
  
  // Multiple affiliate links increase score
  if (baseResult.links.length > 1) {
    contextScore += Math.min(0.2, baseResult.links.length * 0.05)
  }
  
  contextScore = Math.min(1, contextScore)
  
  // Generate recommendation
  let recommendation: 'ALLOW' | 'REVIEW' | 'BLOCK' = 'ALLOW'
  if (contextScore > 0.7) {
    recommendation = 'BLOCK'
  } else if (contextScore > 0.4) {
    recommendation = 'REVIEW'
  }
  
  return {
    ...baseResult,
    contextScore,
    disclosurePresent,
    recommendation,
  }
}

/**
 * Get human-readable summary of affiliate detection
 */
export function getAffiliateSummary(result: AffiliateDetectionResult): string {
  if (!result.hasAffiliateLinks) {
    return 'No affiliate links detected'
  }
  
  const count = result.links.length
  const networks = [...new Set(result.links.map(l => l.network))]
  
  if (count === 1) {
    return `1 affiliate link detected (${networks[0]})`
  }
  
  return `${count} affiliate links detected from ${networks.length} network(s): ${networks.join(', ')}`
}
