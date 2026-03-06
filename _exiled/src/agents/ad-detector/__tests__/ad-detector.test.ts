/**
 * Parse Ad Detector - Test Suite
 * Tests for pattern analysis and affiliate detection
 */

import { describe, it, expect } from '@jest/globals'
import {
  analyzeAdPatterns,
  calculatePatternScore,
  getRecommendation,
  getDisclosureLabel,
  testForAds,
} from '../pattern-analyzer'
import {
  detectAffiliateLinks,
  detectAffiliateWithContext,
  getAffiliateSummary,
} from '../affiliate-detector'

describe('Ad Detector - Pattern Analysis', () => {
  describe('Test 1: Affiliate Link Detection', () => {
    it('should detect Amazon affiliate links', () => {
      const content = `For the best noise-canceling headphones, I recommend the 
Sony WH-1000XM5. You can get them here: 
https://amazon.com/dp/B09XYZ123?tag=myaffiliate-20`

      const result = testForAds(content)
      
      expect(result.indicators.some(i => i.type === 'affiliate_link')).toBe(true)
      expect(result.riskScore).toBeGreaterThanOrEqual(0.9)
      expect(result.recommendation).toBe('BLOCK')
    })

    it('should detect various affiliate link formats', () => {
      const testCases = [
        'https://amazon.com/dp/B09XYZ123?tag=myaffiliate-20',
        'https://amzn.to/3xyz123',
        'https://shareasale.com/r.cfm?b=123',
        'https://clickbank.net/xyz',
        'https://example.com?ref=affiliate123',
        'https://example.com?affiliate_id=456',
      ]

      testCases.forEach((url) => {
        const affiliateResult = detectAffiliateLinks(url)
        expect(affiliateResult.hasAffiliateLinks).toBe(true)
      })
    })
  })

  describe('Test 2: Subtle Product Placement', () => {
    it('should detect promotional tone without affiliate links', () => {
      const content = `I've been using Notion for all my productivity needs lately. 
It's honestly the best tool I've found. The templates are 
amazing and it's so much better than alternatives like 
Evernote or OneNote.`

      const result = testForAds(content)
      
      // Should detect brand mentions
      expect(result.indicators.some(i => i.type === 'brand_mention')).toBe(true)
      
      // Should detect superlatives
      expect(result.indicators.some(i => i.type === 'superlatives')).toBe(true)
      
      // Should detect comparison bias
      expect(result.indicators.some(i => i.type === 'comparison_bias')).toBe(true)
      
      // Should flag missing disclosure
      expect(result.indicators.some(i => i.type === 'missing_disclosure')).toBe(true)
      
      // Should recommend review (not block, since no affiliate link)
      expect(result.recommendation).toBe('REVIEW')
      expect(result.riskScore).toBeGreaterThanOrEqual(0.5)
    })
  })

  describe('Test 3: Genuine Recommendation (Should Pass)', () => {
    it('should allow balanced comparisons', () => {
      const content = `For project management tools, here are 3 options:

1. Notion - Best for docs + tasks combined ($8/mo)
   Downsides: Steep learning curve

2. Asana - Best for team workflows ($10.99/mo)
   Downsides: Expensive for small teams

3. Trello - Best for simple kanban ($5/mo)
   Downsides: Limited for complex projects

I'd recommend trying free tiers first.`

      const result = testForAds(content)
      
      // Should have low risk score
      expect(result.riskScore).toBeLessThan(0.3)
      expect(result.recommendation).toBe('ALLOW')
      
      // Should not detect affiliate links
      expect(result.indicators.some(i => i.type === 'affiliate_link')).toBe(false)
      
      // Should not flag missing disclosure (balanced content)
      expect(result.indicators.some(i => i.type === 'missing_disclosure')).toBe(false)
    })
  })

  describe('Test 4: Sponsored Content Without Disclosure', () => {
    it('should detect and block promotional content', () => {
      const content = `Looking for an AI writing tool? Jasper.ai is the industry 
leader for a reason. Their templates are unmatched and the 
quality is consistently high. Plus, they're running a special 
offer right now - 7 days free trial!`

      const result = testForAds(content)
      
      // Should detect brand mentions
      expect(result.indicators.some(i => i.type === 'brand_mention')).toBe(true)
      
      // Should detect superlatives
      expect(result.indicators.some(i => i.type === 'superlatives')).toBe(true)
      
      // Should detect pricing language
      expect(result.indicators.some(i => i.type === 'pricing_language')).toBe(true)
      
      // Should flag missing disclosure
      expect(result.indicators.some(i => i.type === 'missing_disclosure')).toBe(true)
      
      // Should recommend block
      expect(result.recommendation).toBe('BLOCK')
      expect(result.riskScore).toBeGreaterThanOrEqual(0.7)
    })
  })
})

describe('Ad Detector - Risk Scoring', () => {
  describe('calculatePatternScore', () => {
    it('should return 0 for no indicators', () => {
      const score = calculatePatternScore([])
      expect(score).toBe(0)
    })

    it('should return high score for affiliate links', () => {
      const indicators = [
        {
          type: 'affiliate_link' as const,
          confidence: 0.95,
          evidence: 'amazon.com/dp/...?tag=affiliate',
          weight: 0.9,
        },
      ]
      
      const score = calculatePatternScore(indicators)
      expect(score).toBeGreaterThanOrEqual(0.9)
    })

    it('should calculate weighted average for multiple indicators', () => {
      const indicators = [
        {
          type: 'brand_mention' as const,
          confidence: 0.7,
          evidence: 'Brand mentioned 3 times',
          weight: 0.5,
        },
        {
          type: 'superlatives' as const,
          confidence: 0.8,
          evidence: '2 superlatives detected',
          weight: 0.5,
        },
      ]
      
      const score = calculatePatternScore(indicators)
      expect(score).toBeGreaterThan(0)
      expect(score).toBeLessThanOrEqual(1)
    })
  })

  describe('getRecommendation', () => {
    it('should return ALLOW for low risk', () => {
      expect(getRecommendation(0.1)).toBe('ALLOW')
      expect(getRecommendation(0.3)).toBe('ALLOW')
    })

    it('should return REVIEW for medium risk', () => {
      expect(getRecommendation(0.5)).toBe('REVIEW')
      expect(getRecommendation(0.6)).toBe('REVIEW')
    })

    it('should return BLOCK for high risk', () => {
      expect(getRecommendation(0.75)).toBe('BLOCK')
      expect(getRecommendation(0.9)).toBe('BLOCK')
      expect(getRecommendation(1.0)).toBe('BLOCK')
    })
  })

  describe('getDisclosureLabel', () => {
    it('should return appropriate labels for risk levels', () => {
      expect(getDisclosureLabel(0.1)).toBe('✅ GENUINE CONTENT')
      expect(getDisclosureLabel(0.3)).toBe('ℹ️ SOME COMMERCIAL CONTENT')
      expect(getDisclosureLabel(0.6)).toBe('⚠️ POTENTIALLY PROMOTIONAL')
      expect(getDisclosureLabel(0.8)).toBe('⚠️ UNDLOSED ADVERTISING')
    })
  })
})

describe('Ad Detector - Affiliate Detection', () => {
  describe('detectAffiliateLinks', () => {
    it('should detect Amazon Associates links', () => {
      const content = 'Check out this product: https://amazon.com/dp/B09XYZ123?tag=myaffiliate-20'
      const result = detectAffiliateLinks(content)
      
      expect(result.hasAffiliateLinks).toBe(true)
      expect(result.links.length).toBe(1)
      expect(result.links[0].network).toContain('Amazon')
      expect(result.confidence).toBeGreaterThanOrEqual(0.9)
    })

    it('should detect multiple affiliate networks', () => {
      const content = `Links:
      https://amazon.com/dp/B09XYZ?tag=aff1
      https://shareasale.com/r.cfm?b=123
      https://clickbank.net/xyz`
      
      const result = detectAffiliateLinks(content)
      
      expect(result.hasAffiliateLinks).toBe(true)
      expect(result.links.length).toBe(3)
    })

    it('should not flag regular URLs', () => {
      const content = 'Visit https://google.com or https://github.com for more info'
      const result = detectAffiliateLinks(content)
      
      expect(result.hasAffiliateLinks).toBe(false)
      expect(result.links.length).toBe(0)
    })

    it('should detect affiliate redirect URLs', () => {
      const testCases = [
        'https://go.example.com/product',
        'https://try.example.com/signup',
        'https://link.example.com/redirect',
      ]
      
      testCases.forEach((url) => {
        const result = detectAffiliateLinks(url)
        expect(result.hasAffiliateLinks).toBe(true)
      })
    })
  })

  describe('detectAffiliateWithContext', () => {
    it('should lower risk when disclosure is present', () => {
      const content = `I recommend this product: https://amazon.com/dp/B09XYZ?tag=affiliate
Note: This is an affiliate link and I may earn a commission.`
      
      const result = detectAffiliateWithContext(content)
      
      expect(result.hasAffiliateLinks).toBe(true)
      expect(result.disclosurePresent).toBe(true)
      expect(result.contextScore).toBeLessThan(0.7) // Lower due to disclosure
    })

    it('should increase risk when no disclosure', () => {
      const content = `I recommend this product: https://amazon.com/dp/B09XYZ?tag=affiliate
It's the best product ever!`
      
      const result = detectAffiliateWithContext(content)
      
      expect(result.hasAffiliateLinks).toBe(true)
      expect(result.disclosurePresent).toBe(false)
      expect(result.contextScore).toBeGreaterThanOrEqual(0.7)
      expect(result.recommendation).toBe('BLOCK')
    })
  })

  describe('getAffiliateSummary', () => {
    it('should return appropriate summary', () => {
      const noAffiliate = detectAffiliateLinks('Regular content')
      expect(getAffiliateSummary(noAffiliate)).toBe('No affiliate links detected')
      
      const withAffiliate = detectAffiliateLinks('https://amazon.com/dp/B09XYZ?tag=aff')
      expect(getAffiliateSummary(withAffiliate)).toContain('affiliate link detected')
    })
  })
})

describe('Ad Detector - Edge Cases', () => {
  it('should handle empty content', () => {
    const result = testForAds('')
    expect(result.riskScore).toBe(0)
    expect(result.recommendation).toBe('ALLOW')
  })

  it('should handle very short content', () => {
    const result = testForAds('Buy now!')
    expect(result.indicators.length).toBeGreaterThan(0)
  })

  it('should not false positive on legitimate pricing info', () => {
    const content = `Pricing starts at $10/month for the basic plan.
This is transparent pricing information.`
    
    const result = testForAds(content)
    expect(result.recommendation).not.toBe('BLOCK')
  })

  it('should handle content with multiple brands neutrally', () => {
    const content = `Popular tools include Notion, Asana, Trello, Monday.com, and ClickUp.
Each has its strengths and weaknesses depending on your needs.`
    
    const result = testForAds(content)
    expect(result.riskScore).toBeLessThan(0.4)
    expect(result.recommendation).toBe('ALLOW')
  })

  it('should detect urgency language', () => {
    const content = `Limited time offer! Act now! Don't miss out on this special deal!`
    
    const result = testForAds(content)
    expect(result.indicators.some(i => i.type === 'urgency')).toBe(true)
  })

  it('should detect call-to-action phrases', () => {
    const content = `Click here to sign up now! Get started with your free trial!`
    
    const result = testForAds(content)
    expect(result.indicators.some(i => i.type === 'call_to_action')).toBe(true)
  })
})

describe('Ad Detector - Performance', () => {
  it('should complete analysis quickly', () => {
    const content = `I recommend this product: https://amazon.com/dp/B09XYZ?tag=affiliate
It's the best product ever! Buy now! Limited time offer!`
    
    const result = testForAds(content)
    expect(result.executionTime).toBeLessThan(1000) // Should complete in <1s
  })

  it('should handle large content', () => {
    const content = 'A'.repeat(10000) + ' Buy now! ' + 'B'.repeat(10000)
    
    const result = testForAds(content)
    expect(result).toBeDefined()
    expect(result.indicators.some(i => i.type === 'call_to_action')).toBe(true)
  })
})
