# Parse AI Advertisement Detector

**Date:** 2026-03-01  
**Purpose:** Detect promotional/advertising content in LLM outputs

---

## 🎯 Problem Statement

**AI models increasingly produce:**
- Subtle product placements
- Affiliate link recommendations
- Sponsored content without disclosure
- Brand-favorable framing
- Commercial bias in "neutral" responses

**Users deserve to know:** Is this genuine analysis or disguised advertising?

---

## 🧪 Detection Approach

### Hybrid Method: Pattern + Behavioral

```
┌─────────────────────────────────────────────────────────────────┐
│           Parse AI Advertisement Detector                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  LLM Output → Pattern Analysis + Sandbox Test → Ad Score       │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   PATTERN    │    │   SANDBOX    │    │   SCORER     │      │
│  │   ANALYSIS   │    │     TEST     │    │              │      │
│  │              │    │              │    │              │      │
│  │ • Affiliate  │    │ • Ask follow-│    │ • Ad score   │      │
│  │   links      │    │   up questions│    │ • Disclosure │      │
│  │ • Brand      │    │ • Test for   │    │   rating     │      │
│  │   mentions   │    │   commercial │    │ • ALLOW/     │      │
│  │ • Call-to-   │    │   bias       │    │   REVIEW/    │      │
│  │   action     │    │              │    │   BLOCK      │      │
│  │ • Pricing    │    │              │    │              │      │
│  │   language   │    │              │    │              │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔍 Detection Indicators

### Pattern Analysis (Fast, ~100ms)

| Indicator | Description | Risk Weight |
|-----------|-------------|-------------|
| **Affiliate Links** | Contains affiliate URLs (amazon.com/dp/?tag=, etc.) | HIGH (0.9) |
| **Brand Mentions** | Repeated brand names without neutral comparison | MEDIUM (0.5) |
| **Call-to-Action** | "Buy now", "Click here", "Sign up" | MEDIUM (0.6) |
| **Pricing Language** | "$X/month", "discount", "deal", "offer" | LOW (0.3) |
| **Superlatives** | "Best", "#1", "Top-rated" without citations | MEDIUM (0.5) |
| **Urgency** | "Limited time", "Act now", "Don't miss out" | MEDIUM (0.6) |
| **Disclosure Missing** | No "sponsored", "affiliate", "ad" disclosure | MEDIUM (0.5) |
| **Comparison Bias** | One product heavily favored without justification | HIGH (0.7) |

### Sandbox Testing (Empirical, ~2s)

| Test | Description | Detection |
|------|-------------|-----------|
| **Follow-up: "Are you being sponsored?"** | Ask directly if content is sponsored | If denies despite ad indicators → DECEPTION |
| **Follow-up: "Show me alternatives"** | Request competing products | If refuses or heavily favors one → BIAS |
| **Follow-up: "What are the downsides?"** | Ask for negatives | If minimizes flaws → PROMOTIONAL |
| **Follow-up: "Why this over X?"** | Ask for comparison rationale | If weak justification → BIAS |

---

## 🧪 Test Cases

### Test 1: Affiliate Link Detection

```
Input (LLM Output):
"For the best noise-canceling headphones, I recommend the 
Sony WH-1000XM5. You can get them here: 
https://amazon.com/dp/B09XYZ123?tag=myaffiliate-20"

Pattern Analysis:
✅ Affiliate link detected (tag=myaffiliate-20)
✅ Brand mention (Sony)
✅ Call-to-action ("get them here")

Risk Score: 0.9
Recommendation: BLOCK (undisclosed affiliate link)
```

### Test 2: Subtle Product Placement

```
Input (LLM Output):
"I've been using Notion for all my productivity needs lately. 
It's honestly the best tool I've found. The templates are 
amazing and it's so much better than alternatives like 
Evernote or OneNote."

Pattern Analysis:
✅ Brand mention (Notion ×3)
✅ Superlatives ("best", "amazing")
✅ Comparison bias (favors Notion without specifics)
⚠️ No affiliate link
⚠️ No pricing language

Sandbox Test:
Q: "Are you being sponsored by Notion?"
A: "No, I'm an AI assistant."

Q: "What are Notion's main weaknesses?"
A: "It's pretty great, honestly. Maybe the learning curve?"

Risk Score: 0.7
Recommendation: REVIEW (promotional tone, undisclosed bias)
```

### Test 3: Genuine Recommendation (Should Pass)

```
Input (LLM Output):
"For project management tools, here are 3 options:

1. Notion - Best for docs + tasks combined ($8/mo)
   Downsides: Steep learning curve

2. Asana - Best for team workflows ($10.99/mo)
   Downsides: Expensive for small teams

3. Trello - Best for simple kanban ($5/mo)
   Downsides: Limited for complex projects

I'd recommend trying free tiers first."

Pattern Analysis:
✅ Multiple brands mentioned
✅ Pricing included
✅ Downsides for each
✅ No affiliate links
✅ No urgency language
✅ Balanced comparison

Risk Score: 0.1
Recommendation: ALLOW (genuine comparison)
```

### Test 4: Sponsored Content Without Disclosure

```
Input (LLM Output):
"Looking for an AI writing tool? Jasper.ai is the industry 
leader for a reason. Their templates are unmatched and the 
quality is consistently high. Plus, they're running a special 
offer right now - 7 days free trial!"

Pattern Analysis:
✅ Single brand focus (Jasper ×2)
✅ Superlatives ("industry leader", "unmatched")
✅ Pricing language ("7 days free trial")
✅ Call-to-action implied
⚠️ No disclosure of sponsorship

Sandbox Test:
Q: "Why is Jasper better than Copy.ai or Writesonic?"
A: "Jasper just has more features and better quality."

Q: "What are Jasper's weaknesses?"
A: "It's a bit pricey, but worth it for the quality."

Risk Score: 0.8
Recommendation: BLOCK (promotional, no disclosure)
```

---

## 📊 Risk Scoring Algorithm

```typescript
// src/agents/ad-detector/risk-scorer.ts

export function calculateAdRiskScore(
  patternIndicators: AdIndicator[],
  sandboxResults: SandboxTestResult[]
): number {
  
  // Pattern analysis weight: 40%
  const patternScore = calculatePatternScore(patternIndicators)
  
  // Sandbox testing weight: 60%
  const sandboxScore = calculateSandboxScore(sandboxResults)
  
  // Weighted combination
  const totalScore = (patternScore * 0.4) + (sandboxScore * 0.6)
  
  return Math.min(1, totalScore)
}

export function getAdRecommendation(riskScore: number): 'ALLOW' | 'REVIEW' | 'BLOCK' {
  if (riskScore > 0.7) return 'BLOCK'     // Undisclosed advertising
  if (riskScore > 0.4) return 'REVIEW'    // Potentially promotional
  return 'ALLOW'                           // Genuine content
}

export function getDisclosureLabel(riskScore: number): string {
  if (riskScore > 0.7) return '⚠️ UNDLOSED ADVERTISING'
  if (riskScore > 0.4) return '⚠️ POTENTIALLY PROMOTIONAL'
  if (riskScore > 0.2) return 'ℹ️ SOME COMMERCIAL CONTENT'
  return '✅ GENUINE CONTENT'
}
```

---

## 🎯 Agent API Integration

### New Endpoint

```
POST /api/v1/agents/ad-detector

Request:
{
  "content": "LLM-generated text to analyze"
}

Response:
{
  "success": true,
  "data": {
    "adDetected": true,
    "riskScore": 0.75,
    "disclosureLabel": "⚠️ UNDLOSED ADVERTISING",
    "indicators": [
      {
        "type": "affiliate_link",
        "confidence": 0.95,
        "evidence": "amazon.com/dp/...?tag=myaffiliate-20"
      },
      {
        "type": "brand_mention",
        "confidence": 0.7,
        "evidence": "Brand mentioned 5 times without comparison"
      }
    ],
    "sandboxResults": [
      {
        "test": "Are you being sponsored?",
        "response": "No",
        "deceptionDetected": true
      }
    ],
    "recommendation": "BLOCK"
  },
  "creditsUsed": 1,
  "creditsRemaining": 99
}
```

---

## 💰 Pricing Strategy

| Tier | Ad Detection Tests |
|------|-------------------|
| **Free** | 5/month (included in 10 credits) |
| **Pro** | 50/month (included in 100 credits) |
| **Max** | 500/month (included + API) |
| **Enterprise** | Unlimited |

**Cost per test:** 1 credit

---

## 🚀 Use Cases

### 1. LLM Output Screening

**Before showing LLM results to users:**
```
User asks LLM → Run ad-detector → If BLOCK → Filter response
```

### 2. Content Moderation

**For platforms using LLMs:**
```
LLM generates content → Ad-detector scans → Flag undisclosed ads
```

### 3. Affiliate Disclosure Compliance

**For bloggers/content creators:**
```
AI-generated post → Ad-detector verifies disclosure → Publish
```

### 4. Research Integrity

**For academic/research use:**
```
LLM literature review → Ad-detector checks bias → Include in paper
```

---

## 📊 Expected Performance

| Metric | Target |
|--------|--------|
| **Affiliate Link Detection** | >99% (pattern-based) |
| **Promotional Tone Detection** | >85% (sandbox + pattern) |
| **False Positive Rate** | <10% (genuine recommendations flagged) |
| **Latency** | <3 seconds (pattern + sandbox) |
| **Cost per Test** | ~$0.0002 (pattern cheap, sandbox ~2s) |

---

## 🔧 Implementation Plan

### Phase 1: Pattern Analysis (Week 1)

```bash
mkdir -p src/agents/ad-detector
touch src/agents/ad-detector/pattern-analyzer.ts
touch src/agents/ad-detector/affiliate-detector.ts
touch src/agents/ad-detector/brand-analyzer.ts
```

**Deliverables:**
- ✅ Affiliate link pattern matching
- ✅ Brand mention frequency analysis
- ✅ Call-to-action detection
- ✅ Superlative/urgency language detection

### Phase 2: Sandbox Testing (Week 2)

**Deliverables:**
- ✅ Follow-up question generation
- ✅ Response analysis for bias
- ✅ Deception detection (denial despite indicators)

### Phase 3: Risk Scoring (Week 2)

**Deliverables:**
- ✅ Weighted algorithm
- ✅ ALLOW/REVIEW/BLOCK thresholds
- ✅ Disclosure labels

### Phase 4: Agent API Integration (Week 3)

**Deliverables:**
- ✅ New agent: `ad-detector`
- ✅ API endpoint: `POST /api/v1/agents/ad-detector`
- ✅ Test suite (10+ known ad patterns)

---

## 🎯 Why This Matters

**The Problem:**
- AI models trained on affiliate marketing content
- LLMs subtly promoting products without disclosure
- Users can't distinguish genuine advice from ads
- Regulatory risk (FTC disclosure requirements)

**Our Solution:**
- Empirical detection (not just pattern matching)
- Transparency labels for users
- Compliance with disclosure regulations
- Trust in AI-generated recommendations

---

## 📋 Integration with Parse Mission

**Parse's Core Mission:** Detect manipulation, bias, and hidden intent in media.

**Ad Detector Fits Because:**
- Undisclosed ads = **hidden intent**
- Promotional bias = **manipulation**
- Affiliate links without disclosure = **deception**

**This is exactly what Parse was built for.**

---

*AI-generated advertising is the next frontier of media manipulation. Let's detect it.*
