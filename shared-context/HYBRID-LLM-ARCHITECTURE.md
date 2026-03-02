# Hybrid LLM Architecture Plan

## Overview

Combine unlimited local LLM (qwen2.5-coder-14b-instruct) with cloud LLMs for maximum efficiency and zero-cost continuous operation.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    TASK ROUTER (Kublai)                         │
│                                                                 │
│  Incoming Task → Classify Complexity → Route to Appropriate    │
│                                                                 │
│  │                                                              │
│  ├── SIMPLE/HIGH-VOLUME → Local LLM (qwen2.5-coder-14b)        │
│  │   - Free, unlimited                                         │
│  │   - Fast (~50 tok/s locally)                                │
│  │   - Good for: drafts, monitoring, simple tasks              │
│  │                                                              │
│  └── COMPLEX/CRITICAL → Cloud LLM (qwen3.5-plus)               │
│      - Paid, rate-limited                                      │
│      - Slower but more capable                                 │
│      - Good for: final review, strategy, complex code          │
└─────────────────────────────────────────────────────────────────┘
```

## Task Classification Matrix

| Task Type | Local LLM | Cloud LLM | Rationale |
|-----------|-----------|-----------|-----------|
| **Content Drafts** | ✅ First pass | ✅ Polish | Local generates 50 posts, cloud polishes top 5 |
| **Code Generation** | ✅ Simple functions | ✅ Complex systems | Local writes tests, cloud writes architecture |
| **Monitoring** | ✅ Continuous | ❌ Too expensive | Local runs 24/7, alerts on anomalies |
| **Research** | ✅ Summarization | ✅ Deep analysis | Local summarizes 100 articles, cloud analyzes top 10 |
| **User Responses** | ❌ Risk of errors | ✅ Final output | Cloud ensures quality for user-facing |
| **Data Processing** | ✅ Batch processing | ❌ Too expensive | Local processes 1000s of articles |
| **Testing** | ✅ Run tests | ✅ Review failures | Local runs, cloud debugs |
| **Strategy** | ❌ Not capable | ✅ Strategic decisions | Cloud for high-stakes decisions |

## Implementation Plan

### Phase 1: Local LLM Setup (Hour 1)

```bash
# 1. Install Ollama (or your preferred local runner)
brew install ollama

# 2. Pull qwen2.5-coder-14b-instruct
ollama pull qwen2.5-coder-14b-instruct

# 3. Start local server
ollama serve

# 4. Test local endpoint
curl http://localhost:11434/api/generate -d '{
  "model": "qwen2.5-coder-14b-instruct",
  "prompt": "Hello",
  "stream": false
}'
```

### Phase 2: ACP Backend Configuration (Hour 2)

```json5
// openclaw.json
{
  "acp": {
    "enabled": true,
    "backend": "acpx",
    "defaultAgent": "local-codex",
    "allowedAgents": [
      "local-codex",      // qwen2.5-coder-14b (free)
      "cloud-codex",      // qwen3.5-plus (paid)
      "cloud-claude"      // claude-opus (paid)
    ],
    "routing": {
      "simple": "local-codex",
      "complex": "cloud-codex",
      "critical": "cloud-claude"
    }
  }
}
```

### Phase 3: Task Router Implementation (Hour 3-4)

```typescript
// src/lib/task-router.ts

interface Task {
  type: 'content' | 'code' | 'research' | 'monitoring' | 'strategy'
  complexity: 'simple' | 'medium' | 'complex' | 'critical'
  userFacing: boolean
  volume: 'single' | 'batch' | 'continuous'
}

function routeTask(task: Task): 'local' | 'cloud' {
  // Route to local if:
  // - Simple/medium complexity
  // - High volume or continuous
  // - Not user-facing
  
  if (task.volume === 'continuous' || task.volume === 'batch') {
    return 'local'  // Cost savings on volume
  }
  
  if (task.complexity === 'simple' && !task.userFacing) {
    return 'local'  // Good enough for internal tasks
  }
  
  if (task.complexity === 'complex' || task.complexity === 'critical') {
    return 'cloud'  // Need full capability
  }
  
  if (task.userFacing && task.complexity === 'medium') {
    return 'cloud'  // Quality matters for users
  }
  
  return 'local'  // Default to free
}

// Example usage:
const contentDraft = {
  type: 'content',
  complexity: 'simple',
  userFacing: false,
  volume: 'batch'
}
routeTask(contentDraft)  // → 'local' (generate 50 drafts free)

const finalPolish = {
  type: 'content',
  complexity: 'medium',
  userFacing: true,
  volume: 'single'
}
routeTask(finalPolish)  // → 'cloud' (polish top 5 for posting)
```

### Phase 4: Agent Configuration (Hour 5)

```typescript
// agents/temujin/config.ts

export const temujinConfig = {
  // Use local LLM for continuous work
  continuousTasks: {
    model: 'local-codex',  // qwen2.5-coder-14b
    tasks: [
      'code-generation-drafts',
      'test-writing',
      'documentation',
      'simple-refactoring'
    ]
  },
  
  // Use cloud LLM for critical work
  criticalTasks: {
    model: 'cloud-codex',  // qwen3.5-plus
    tasks: [
      'architecture-design',
      'security-review',
      'production-deploys',
      'complex-debugging'
    ]
  }
}
```

## Specific Use Cases

### 1. Content Generation at Scale

**Current (Cloud Only):**
```
Cost: $0.50 per article analysis
100 articles = $50/day
```

**Hybrid:**
```
Local LLM: Generate 100 draft analyses ($0)
Cloud LLM: Polish top 10 ($5)
Total: $5/day (90% savings)
```

**Implementation:**
```bash
# Local generates drafts
ollama run qwen2.5-coder-14b-instruct "
Analyze these 100 articles for bias.
Output: JSON with bias_score, techniques_detected
" > drafts.json

# Cloud polishes top 10
# (via ACP with cloud-codex)
```

### 2. Continuous Monitoring

**Current (Cloud Only):**
```
Cost: $0.01 per check
1440 checks/day = $14.40/day
```

**Hybrid:**
```
Local LLM: Run all 1440 checks ($0)
Cloud LLM: Review anomalies only (~10/day = $0.10)
Total: $0.10/day (99% savings)
```

**Implementation:**
```typescript
// agents/ogedei/monitoring.ts

// Local monitoring (continuous, free)
async function continuousMonitoring() {
  while (true) {
    const status = await checkAllServices()
    
    if (status.anomalies.length > 0) {
      // Escalate to cloud for analysis
      await escalateToCloud(status.anomalies)
    }
    
    await sleep(60000)  // Check every minute
  }
}

// Cloud analysis (only when needed)
async function escalateToCloud(anomalies) {
  // Use cloud LLM for root cause analysis
  const analysis = await cloudLLM.analyze(anomalies)
  await sendAlert(analysis)
}
```

### 3. Code Development

**Current (Cloud Only):**
```
Cost: $2 per complex feature
10 features/week = $80/week
```

**Hybrid:**
```
Local LLM: Write tests, docs, simple functions ($0)
Cloud LLM: Architecture, complex logic, review ($0.50/feature)
Total: $5/week (94% savings)
```

**Implementation:**
```typescript
// agents/temujin/workflow.ts

// Step 1: Local writes tests (free)
const tests = await localLLM.generate(`
  Write comprehensive tests for ${functionName}
  Include edge cases, error handling
`)

// Step 2: Local writes first draft (free)
const draft = await localLLM.generate(`
  Implement ${functionName} to pass these tests
`)

// Step 3: Cloud reviews and refines ($0.10)
const refined = await cloudLLM.generate(`
  Review and improve this implementation:
  ${draft}
  
  Focus on:
  - Security
  - Performance
  - Edge cases
`)
```

### 4. Research at Scale

**Current (Cloud Only):**
```
Cost: $0.05 per article summary
1000 articles = $50
```

**Hybrid:**
```
Local LLM: Summarize all 1000 articles ($0)
Cloud LLM: Deep analysis of top 50 ($2.50)
Total: $2.50 (95% savings)
```

## Cost Comparison

| Scenario | Cloud Only | Hybrid | Savings |
|----------|------------|--------|---------|
| **Content (100/day)** | $50/day | $5/day | 90% |
| **Monitoring (24/7)** | $14/day | $0.10/day | 99% |
| **Code (10 features/wk)** | $80/wk | $5/wk | 94% |
| **Research (1000 articles)** | $50 | $2.50 | 95% |
| **Total Monthly** | ~$3,000 | ~$300 | **90%** |

## Performance Considerations

### Local LLM Limitations

| Aspect | qwen2.5-coder-14b | qwen3.5-plus |
|--------|-------------------|--------------|
| **Context** | 32K tokens | 256K tokens |
| **Speed** | ~50 tok/s (local) | ~20 tok/s (API) |
| **Quality** | Good for drafts | Excellent for final |
| **Cost** | $0 (your hardware) | $0.002/1K tokens |

### Mitigation Strategies

1. **Chunking**: Break large tasks into 32K chunks for local
2. **Cascading**: Local first, escalate to cloud if needed
3. **Caching**: Cache cloud responses, reuse for similar tasks
4. **Batching**: Batch similar tasks for cloud efficiency

## Rollout Plan

### Week 1: Setup
- [ ] Install local LLM runner (Ollama)
- [ ] Configure ACP backend
- [ ] Test local endpoint
- [ ] Create task router

### Week 2: Content Pipeline
- [ ] Local generates 50 content drafts
- [ ] Cloud polishes top 10
- [ ] Measure quality difference
- [ ] Optimize prompts

### Week 3: Monitoring
- [ ] Local runs continuous monitoring
- [ ] Cloud reviews anomalies only
- [ ] Set up escalation thresholds
- [ ] Measure cost savings

### Week 4: Development
- [ ] Local writes tests + drafts
- [ ] Cloud reviews critical code
- [ ] Measure velocity change
- [ ] Optimize workflow

## Success Metrics

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| **API Costs** | $3,000/mo | $300/mo | Stripe dashboard |
| **Content Output** | 2/day | 50/day | Content files |
| **Code Velocity** | 1 feature/wk | 5 features/wk | Git commits |
| **Research Scale** | 10 articles/day | 100 articles/day | Analyses run |

## Bottom Line

**Hybrid architecture enables:**
- 90% cost reduction
- 25x content output
- 5x code velocity
- 10x research scale

**All while maintaining quality through strategic cloud LLM use.**

**Ready to implement immediately when local LLM is available.**
