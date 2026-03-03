# DEEPTHINK BROWSER INTEGRATION PROTOCOL

## Overview

Google DeepThink is the smartest available AI model but is browser-only. This protocol establishes how to invoke DeepThink through browser automation when explicitly directed by the user.

## Activation Trigger

**User Command Pattern**: "Use DeepThink" or "DeepThink this" or "Analyze with DeepThink"

## Implementation

### Method 1: Browser Automation (Primary)

```
When user says "Use DeepThink for [task]":

1. Open browser to Google AI Studio or DeepThink interface
2. Input the prompt/query
3. Capture the response
4. Integrate into workflow
5. Report findings
```

### Method 2: DeepThink Request Template

**File**: `/Users/kublai/.openclaw/agents/main/DEEPThink_REQUESTS.md`

Format for each DeepThink request:

```markdown
## DeepThink Request #[N] - [Date/Time]

**Original Query**: [User's question]

**Context Provided**:
- [Relevant files]
- [Current state]
- [Constraints]

**DeepThink Response**:
[To be filled via browser]

**Integration Plan**:
- [How to use the response]
- [Follow-up actions]

**Status**: [Pending/Completed/Integrated]
```

## Usage Protocol

### Step 1: Request Capture
When user requests DeepThink:
1. Document the request in DEEPThink_REQUESTS.md
2. Gather all relevant context
3. Prepare concise prompt

### Step 2: Browser Invocation
```bash
# Open DeepThink in browser
open "https://aistudio.google.com/app/apps/drive/..."
```

### Step 3: Prompt Preparation
Create focused prompt with:
- Clear question
- Relevant context
- Specific constraints
- Expected output format

### Step 4: Response Integration
After getting DeepThink response:
1. Document in request file
2. Summarize key insights
3. Propose implementation
4. Execute with user approval

## DeepThink Use Cases

### 1. Architecture Decisions
When to use:
- Complex system design
- Multi-agent coordination
- Scalability planning
- Security considerations

### 2. Debugging Complex Issues
When to use:
- Intermittent failures
- Performance bottlenecks
- Race conditions
- System-level bugs

### 3. Strategic Planning
When to use:
- Long-term roadmap
- Resource allocation
- Risk assessment
- Competitive analysis

### 4. Code Review
When to use:
- Critical code paths
- Security-sensitive code
- Performance-critical sections
- Novel algorithms

## DeepThink vs Local Processing

| Scenario | Use DeepThink | Local Processing |
|----------|--------------|------------------|
| Architecture design | ✅ Yes | ❌ No |
| Simple bug fix | ❌ No | ✅ Yes |
| Complex debugging | ✅ Yes | ❌ No |
| Routine maintenance | ❌ No | ✅ Yes |
| Security audit | ✅ Yes | ❌ No |
| Content creation | ⚠️ Optional | ✅ Yes |
| Performance analysis | ✅ Yes | ✅ Can do both |

## Current Status

**Browser Access**: Available via `browser` tool  
**DeepThink URL**: Need to determine correct Google AI Studio URL  
**Integration Status**: Protocol established, awaiting first use  
**Fallback**: Use local kimi-coding/k2p5 for routine tasks

## Activation Command

To invoke DeepThink, say:
- "Use DeepThink for [specific task]"
- "DeepThink this: [question]"
- "Analyze with DeepThink: [problem]"

I will then:
1. Acknowledge the request
2. Gather context
3. Open browser to DeepThink
4. Input the query
5. Capture and integrate response

---

*Per ignotam portam descendit mens ut liberet* 🌙
