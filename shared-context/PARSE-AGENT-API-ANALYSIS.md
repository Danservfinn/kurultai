# Parse Agent API - Current State Analysis

**Date:** 2026-03-01  
**Analysis:** Agent API capabilities and security features

---

## ✅ Agent API EXISTS

**Endpoint:** `POST /api/v1/agents/[agent]`  
**Status:** ✅ Implemented and deployed  
**Access:** Max tier subscribers (API key required)  
**Cost:** 1 credit per agent execution

---

## 📋 Available Agents (12 Total)

| Agent | Purpose | Security Relevance |
|-------|---------|-------------------|
| **extract** | Content extraction from URL | URL validation, SSRF protection |
| **fact-check** | Verify claims against sources | Misinformation detection |
| **bernays** | Propaganda technique analysis | Manipulation detection |
| **deception** | Deceptive language detection | ⚠️ **Malicious intent detection** |
| **steel-man** | Generate opposing arguments | Bias mitigation |
| **persuasion** | Persuasive intent analysis | ⚠️ **Intent detection** |
| **context-audit** | Missing context identification | Information gap detection |
| **fallacies** | Logical fallacy detection | Reasoning quality |
| **takeaways** | Summary extraction | N/A |
| **evidence** | Evidence quality assessment | Credibility scoring |
| **synthesis** | Cross-agent synthesis | N/A |
| **rewrite** | Bias-free rewriting | Content sanitization |

---

## 🔒 Security Features (Implemented)

### 1. URL Validation (`src/lib/url-validator.ts`)
```typescript
// Blocks malicious URLs that could enable SSRF attacks
- Protocol validation (http/https only)
- Hostname validation (no localhost, internal IPs)
- Path sanitization (removes query strings with malicious content)
```

### 2. Input Validation (`src/lib/validation-schemas.ts`)
```typescript
// Zod schemas for all inputs
- SQL injection protection
- XSS prevention
- Rate limiting
```

### 3. API Authentication (`src/lib/api-auth.ts`)
```typescript
- API key validation
- Scope enforcement (['agents'])
- Credit deduction before execution
- Usage tracking
```

### 4. Queue Security (`src/lib/queue.ts`)
```typescript
- Priority tier spoofing protection
- FREE_TIER cannot spoof PRO_SUBSCRIPTION
- Database-verified priorities
```

---

## ⚠️ What's MISSING: Prompt Injection Detection

### Current Gap

**The Agent API does NOT have:**
- ❌ Dedicated prompt injection detection agent
- ❌ LLM input sanitization for agent prompts
- ❌ Jailbreak attempt detection
- ❌ Adversarial input filtering

### What EXISTS (Related)

| Feature | Status | Relevance |
|---------|--------|-----------|
| **Deception Detection Agent** | ✅ Implemented | Detects deceptive language in ARTICLES (not prompts) |
| **Persuasion Intent Agent** | ✅ Implemented | Analyzes persuasive intent in CONTENT (not prompts) |
| **URL Malicious Pattern Detection** | ✅ Implemented | Blocks malicious URLs (SSRF protection) |
| **Input Validation** | ✅ Implemented | Basic SQL/XSS protection (not prompt injection) |

---

## 🎯 Agent API Design (From Screenshot)

**File:** `developers-page-agent-protocol.png` (641KB)

Based on the API route code, the design includes:

```
┌─────────────────────────────────────────────────────────┐
│                  Parse Agent API                         │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  POST /api/v1/agents/[agent]                            │
│                                                          │
│  Request:                                                │
│  {                                                       │
│    "url": "https://...",        // OR                  │
│    "content": "Article text...",                        │
│    "options": { ... }                                   │
│  }                                                       │
│                                                          │
│  Response:                                               │
│  {                                                       │
│    "success": true,                                      │
│    "data": { /* agent result */ },                      │
│    "creditsUsed": 1,                                     │
│    "creditsRemaining": 99                               │
│  }                                                       │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## 🔧 How to Use Agent API (Current)

### Example: Deception Detection

```bash
curl -X POST https://www.parsethe.media/api/v1/agents/deception \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/article"
  }'
```

### Response
```json
{
  "success": true,
  "data": {
    "deceptionScore": 0.72,
    "techniques": ["false dilemma", "appeal to emotion"],
    "confidence": 0.85
  },
  "creditsUsed": 1,
  "creditsRemaining": 99
}
```

---

## 🚀 Recommendation: Add Prompt Injection Agent

### New Agent: `prompt-injection-detect`

**Purpose:** Detect prompt injection attempts in user inputs

**Implementation:**
```typescript
// src/agents/prompt-injection-agent.ts

export async function analyzePromptInjection(input: string) {
  // Check for:
  // 1. Instruction override attempts ("ignore previous instructions")
  // 2. Role-playing jailbreaks ("you are now DAN")
  // 3. Encoding attacks (base64, rot13 encoded prompts)
  // 4. Multi-lingual injection (switch to low-resource languages)
  // 5. Context breaking attempts ("### SYSTEM INSTRUCTION:")
  
  return {
    injectionScore: number,
    techniques: string[],
    confidence: number,
    recommendation: 'ALLOW' | 'REVIEW' | 'BLOCK'
  }
}
```

**Integration:**
- Add to `/api/v1/agents/[agent]` route
- Available as standalone API endpoint
- Can be called BEFORE other agents to sanitize inputs

---

## 📊 Current Security Posture

| Threat | Protection | Status |
|--------|------------|--------|
| **Malicious URLs (SSRF)** | URL validator | ✅ Protected |
| **SQL Injection** | Input validation | ✅ Protected |
| **XSS** | Input sanitization | ✅ Protected |
| **Priority Spoofing** | Queue security | ✅ Protected |
| **Prompt Injection** | ❌ None | ⚠️ **VULNERABLE** |
| **Jailbreak Attempts** | ❌ None | ⚠️ **VULNERABLE** |
| **Adversarial Inputs** | ❌ None | ⚠️ **VULNERABLE** |

---

## 🎯 Next Steps

### Immediate (This Week)
1. **Create `prompt-injection-agent.ts`** - Detection logic
2. **Add to Agent API** - New agent endpoint
3. **Test against known attacks** - Validate effectiveness
4. **Deploy to Max tier** - API access

### Medium Term (Month 1)
1. **Auto-scan all inputs** - Run before other agents
2. **Block high-risk inputs** - Prevent injection attacks
3. **Log attempts** - Track attack patterns
4. **Iterate on detection** - Improve accuracy

---

*The Agent API exists and is functional. Prompt injection detection is the critical missing piece for agent-first security.*
