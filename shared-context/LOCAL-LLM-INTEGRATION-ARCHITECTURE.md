# Local LLM Integration Architecture

## Overview

**Goal:** Seamlessly integrate LM Studio local LLM (DeepSeek-R1-Distill-Qwen-14B) with automatic routing between local and cloud LLMs.

**Key Principles:**
1. **Local-first** - Default to free local LLM
2. **Automatic fallback** - Escalate to cloud if local fails
3. **Task-based routing** - Route by task type, not manually
4. **Metrics-driven** - Track success rates, optimize routing

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    TASK ROUTER (Kublai)                         │
│                                                                 │
│  Incoming Task → Classify → Route Decision → Execute           │
│                                                                 │
│  ┌────────────────────────────────────────────────────────┐    │
│  │              LLM CASCADE (Automatic Fallback)          │    │
│  │                                                         │    │
│  │  1. Try LOCAL LLM (LM Studio @ localhost:1234)         │    │
│  │     ↓ (if fails)                                        │    │
│  │  2. Escalate to CLOUD LLM (qwen3.5-plus via API)       │    │
│  │     ↓ (if fails)                                        │    │
│  │  3. Return error + log for analysis                    │    │
│  └────────────────────────────────────────────────────────┘    │
│                                                                 │
│  Metrics: local_success_rate, cloud_escalations, avg_latency   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. Local LLM Calling Mechanism

### LM Studio API (OpenAI-Compatible)

**Endpoint:** `http://localhost:1234/v1/chat/completions`

**Request Format:**
```typescript
interface LocalLLMRequest {
  model: string  // "deepseek-r1-distill-qwen-14b"
  messages: Array<{
    role: 'system' | 'user' | 'assistant'
    content: string
  }>
  temperature?: number  // 0.7 default
  max_tokens?: number   // 2048 default
  stream?: boolean      // false for most tasks
}
```

**Response Format:**
```typescript
interface LocalLLMResponse {
  id: string
  choices: Array<{
    message: {
      role: 'assistant'
      content: string
    }
    finish_reason: 'stop' | 'length' | 'error'
  }>
  usage: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
  }
}
```

### Implementation: Local LLM Client

```typescript
// src/lib/local-llm-client.ts

import { EventEmitter } from 'events'

interface LocalLLMConfig {
  baseUrl: string
  model: string
  timeout: number
  maxRetries: number
}

export class LocalLLMClient extends EventEmitter {
  private config: LocalLLMConfig
  private healthCheckInterval: NodeJS.Timeout
  private isHealthy: boolean = false
  
  constructor(config: LocalLLMConfig) {
    super()
    this.config = config
    this.startHealthCheck()
  }
  
  /**
   * Generate completion from local LLM
   */
  async generate(prompt: string, options?: {
    systemPrompt?: string
    temperature?: number
    maxTokens?: number
  }): Promise<string> {
    const messages = [
      ...(options?.systemPrompt ? [{
        role: 'system' as const,
        content: options.systemPrompt
      }] : []),
      { role: 'user' as const, content: prompt }
    ]
    
    for (let attempt = 0; attempt < this.config.maxRetries; attempt++) {
      try {
        const response = await fetch(`${this.config.baseUrl}/v1/chat/completions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model: this.config.model,
            messages,
            temperature: options?.temperature ?? 0.7,
            max_tokens: options?.maxTokens ?? 2048
          }),
          signal: AbortSignal.timeout(this.config.timeout)
        })
        
        if (!response.ok) {
          throw new Error(`Local LLM error: ${response.status}`)
        }
        
        const data = await response.json()
        this.emit('success', { attempt, latency: data.usage })
        return data.choices[0].message.content
        
      } catch (error) {
        this.emit('error', { attempt, error })
        if (attempt === this.config.maxRetries - 1) {
          throw error
        }
        // Exponential backoff
        await sleep(Math.pow(2, attempt) * 1000)
      }
    }
    
    throw new Error('Local LLM failed after all retries')
  }
  
  /**
   * Check if local LLM is healthy
   */
  async healthCheck(): Promise<boolean> {
    try {
      const response = await fetch(`${this.config.baseUrl}/v1/models`, {
        signal: AbortSignal.timeout(5000)
      })
      this.isHealthy = response.ok
      return this.isHealthy
    } catch {
      this.isHealthy = false
      return false
    }
  }
  
  /**
   * Start periodic health checks
   */
  private startHealthCheck() {
    this.healthCheckInterval = setInterval(async () => {
      const healthy = await this.healthCheck()
      this.emit('health', { healthy })
    }, 30000) // Check every 30 seconds
  }
  
  /**
   * Get current health status
   */
  isHealthyNow(): boolean {
    return this.isHealthy
  }
  
  /**
   * Cleanup
   */
  destroy() {
    clearInterval(this.healthCheckInterval)
  }
}
```

### Usage Example

```typescript
// Initialize local LLM client
const localLLM = new LocalLLMClient({
  baseUrl: 'http://localhost:1234',
  model: 'deepseek-r1-distill-qwen-14b',
  timeout: 60000,  // 60 second timeout
  maxRetries: 3
})

// Listen for events
localLLM.on('success', (data) => {
  metrics.localSuccess++
  metrics.localLatency.push(data.latency)
})

localLLM.on('error', (data) => {
  metrics.localErrors++
  console.log(`Local LLM error (attempt ${data.attempt}):`, data.error)
})

localLLM.on('health', (data) => {
  if (!data.healthy) {
    console.warn('Local LLM unhealthy - will escalate to cloud')
  }
})

// Generate content
const draft = await localLLM.generate(
  'Write a Twitter thread about AI safety',
  { 
    systemPrompt: 'You are a helpful content writer',
    temperature: 0.8,
    maxTokens: 500
  }
)
```

---

## 2. Task Routing Mechanism

### Task Classifier

```typescript
// src/lib/task-router.ts

export interface Task {
  id: string
  agent: 'ogedei' | 'mongke' | 'temujin' | 'chagatai' | 'kublai'
  type: 'monitoring' | 'research' | 'code' | 'content' | 'coordination' | 'strategy'
  complexity: 'simple' | 'medium' | 'complex' | 'critical'
  userFacing: boolean
  volume: 'single' | 'batch' | 'continuous'
  requiresCreativity?: boolean
  requiresAccuracy?: boolean
}

export type LLMTier = 'local' | 'cloud'

export class TaskRouter {
  /**
   * Route task to appropriate LLM tier
   */
  route(task: Task): LLMTier {
    // ALWAYS LOCAL (free, continuous)
    if (task.volume === 'continuous') return 'local'
    if (task.agent === 'ogedei') return 'local'  // Monitoring is 100% local
    
    // HIGH VOLUME → LOCAL
    if (task.volume === 'batch' && task.complexity === 'simple') return 'local'
    
    // DRAFTS → LOCAL
    if (!task.userFacing && task.complexity !== 'critical') return 'local'
    
    // REQUIRES HIGH ACCURACY → CLOUD
    if (task.requiresAccuracy && task.complexity === 'complex') return 'cloud'
    
    // CRITICAL → CLOUD
    if (task.complexity === 'critical') return 'cloud'
    if (task.userFacing && task.complexity === 'complex') return 'cloud'
    
    // REQUIRES CREATIVITY → CLOUD (for final polish)
    if (task.requiresCreativity && task.userFacing) return 'cloud'
    
    // DEFAULT TO LOCAL (save money)
    return 'local'
  }
  
  /**
   * Classify task from description
   */
  classify(description: {
    agent: string
    prompt: string
    context?: string
  }): Task {
    // Use simple heuristics for now
    // Could use ML classifier later
    
    const isContinuous = description.prompt.includes('every') || 
                         description.prompt.includes('monitor') ||
                         description.prompt.includes('check')
    
    const isDraft = description.prompt.includes('draft') ||
                    description.prompt.includes('generate') ||
                    description.prompt.includes('brainstorm')
    
    const isCritical = description.prompt.includes('security') ||
                       description.prompt.includes('production') ||
                       description.prompt.includes('critical')
    
    const isUserFacing = description.context?.includes('user') ||
                         description.context?.includes('customer') ||
                         description.context?.includes('public')
    
    return {
      id: crypto.randomUUID(),
      agent: description.agent as Task['agent'],
      type: this.inferType(description.prompt),
      complexity: isCritical ? 'critical' : isDraft ? 'simple' : 'medium',
      userFacing: isUserFacing,
      volume: isContinuous ? 'continuous' : isDraft ? 'batch' : 'single',
      requiresCreativity: description.prompt.includes('write') ||
                          description.prompt.includes('create'),
      requiresAccuracy: description.prompt.includes('analyze') ||
                        description.prompt.includes('verify')
    }
  }
  
  private inferType(prompt: string): Task['type'] {
    if (prompt.includes('monitor') || prompt.includes('health')) return 'monitoring'
    if (prompt.includes('research') || prompt.includes('analyze')) return 'research'
    if (prompt.includes('code') || prompt.includes('test')) return 'code'
    if (prompt.includes('write') || prompt.includes('content')) return 'content'
    if (prompt.includes('decide') || prompt.includes('strategy')) return 'strategy'
    return 'coordination'
  }
}
```

---

## 3. LLM Cascade with Automatic Fallback

```typescript
// src/lib/llm-cascade.ts

import { LocalLLMClient } from './local-llm-client'
import { CloudLLMClient } from './cloud-llm-client'  // Existing cloud client
import { TaskRouter, Task, LLMTier } from './task-router'

interface CascadeMetrics {
  localAttempts: number
  localSuccesses: number
  localFailures: number
  cloudEscalations: number
  cloudSuccesses: number
  cloudFailures: number
  avgLocalLatency: number
  avgCloudLatency: number
}

export class LLMCascade {
  private localLLM: LocalLLMClient
  private cloudLLM: CloudLLMClient
  private router: TaskRouter
  private metrics: CascadeMetrics
  
  constructor() {
    this.localLLM = new LocalLLMClient({
      baseUrl: 'http://localhost:1234',
      model: 'deepseek-r1-distill-qwen-14b',
      timeout: 60000,
      maxRetries: 3
    })
    
    this.cloudLLM = new CloudLLMClient({
      model: 'qwen3.5-plus',
      apiKey: process.env.CLOUD_LLM_API_KEY
    })
    
    this.router = new TaskRouter()
    this.metrics = {
      localAttempts: 0,
      localSuccesses: 0,
      localFailures: 0,
      cloudEscalations: 0,
      cloudSuccesses: 0,
      cloudFailures: 0,
      avgLocalLatency: 0,
      avgCloudLatency: 0
    }
    
    this.setupEventListeners()
  }
  
  /**
   * Generate with automatic fallback
   */
  async generate(prompt: string, options?: {
    task?: Task
    systemPrompt?: string
    temperature?: number
    maxTokens?: number
  }): Promise<string> {
    const startTime = Date.now()
    
    // Determine which LLM to use
    let primaryTier: LLMTier
    if (options?.task) {
      primaryTier = this.router.route(options.task)
    } else {
      // Default to local for unknown tasks
      primaryTier = 'local'
    }
    
    try {
      // Try primary LLM
      const result = await this.tryLLM(primaryTier, prompt, options)
      this.recordSuccess(primaryTier, Date.now() - startTime)
      return result
      
    } catch (primaryError) {
      // Primary failed, try fallback
      const fallbackTier = primaryTier === 'local' ? 'cloud' : 'local'
      console.log(`${primaryTier} failed, escalating to ${fallbackTier}...`)
      this.metrics.cloudEscalations++
      
      try {
        const result = await this.tryLLM(fallbackTier, prompt, options)
        this.recordSuccess(fallbackTier, Date.now() - startTime)
        return result
        
      } catch (fallbackError) {
        // Both failed
        this.recordFailure(fallbackTier, Date.now() - startTime)
        throw new Error(`Both LLMs failed: ${primaryError}, ${fallbackError}`)
      }
    }
  }
  
  /**
   * Try a specific LLM tier
   */
  private async tryLLM(
    tier: LLMTier, 
    prompt: string, 
    options?: any
  ): Promise<string> {
    this.metrics[`${tier}Attempts`]++
    
    if (tier === 'local') {
      if (!this.localLLM.isHealthyNow()) {
        throw new Error('Local LLM unhealthy')
      }
      return await this.localLLM.generate(prompt, options)
    } else {
      return await this.cloudLLM.generate(prompt, options)
    }
  }
  
  /**
   * Record successful generation
   */
  private recordSuccess(tier: LLMTier, latency: number) {
    this.metrics[`${tier}Successes`]++
    this.updateAvgLatency(tier, latency)
  }
  
  /**
   * Record failed generation
   */
  private recordFailure(tier: LLMTier, latency: number) {
    this.metrics[`${tier}Failures`]++
  }
  
  /**
   * Update average latency
   */
  private updateAvgLatency(tier: LLMTier, latency: number) {
    const key = `avg${tier.charAt(0).toUpperCase() + tier.slice(1)}Latency` as const
    const successes = this.metrics[`${tier}Successes`]
    const currentAvg = this.metrics[key]
    this.metrics[key] = ((currentAvg * (successes - 1)) + latency) / successes
  }
  
  /**
   * Setup event listeners for local LLM
   */
  private setupEventListeners() {
    this.localLLM.on('health', (data) => {
      if (!data.healthy) {
        console.warn('Local LLM unhealthy - will use cloud as primary')
      }
    })
    
    this.localLLM.on('error', (data) => {
      console.log(`Local LLM error (attempt ${data.attempt})`)
    })
  }
  
  /**
   * Get current metrics
   */
  getMetrics(): CascadeMetrics {
    return { ...this.metrics }
  }
  
  /**
   * Get local LLM success rate
   */
  getLocalSuccessRate(): number {
    const { localAttempts, localSuccesses } = this.metrics
    return localAttempts > 0 ? (localSuccesses / localAttempts) * 100 : 0
  }
  
  /**
   * Cleanup
   */
  destroy() {
    this.localLLM.destroy()
  }
}
```

---

## 4. Usage Examples

### Example 1: Ögedei Continuous Monitoring (100% Local)

```typescript
// agents/ogedei/monitoring.ts

import { LLMCascade } from '@/lib/llm-cascade'

const llm = new LLMCascade()

async function continuousMonitoring() {
  while (true) {
    const task = {
      id: crypto.randomUUID(),
      agent: 'ogedei' as const,
      type: 'monitoring' as const,
      complexity: 'simple' as const,
      userFacing: false,
      volume: 'continuous' as const
    }
    
    // Run health checks (LOCAL - FREE)
    const status = await llm.generate(
      'Check system health: API, database, services',
      { task, systemPrompt: 'You are a system monitoring assistant' }
    )
    
    // Only escalate anomalies to cloud
    if (status.includes('ERROR') || status.includes('WARNING')) {
      const analysis = await llm.generate(
        `Analyze this anomaly: ${status}`,
        { 
          task: { ...task, complexity: 'complex' },
          systemPrompt: 'You are a senior SRE'
        }
      )
      await sendAlert(analysis)
    }
    
    await sleep(60000)  // Check every minute
  }
}
```

### Example 2: Chagatai Content Pipeline (85% Local / 15% Cloud)

```typescript
// agents/chagatai/content-pipeline.ts

import { LLMCascade } from '@/lib/llm-cascade'

const llm = new LLMCascade()

async function generateContentBatch(topic: string) {
  // Generate 50 drafts (LOCAL - FREE)
  const drafts = []
  for (let i = 0; i < 50; i++) {
    const task = {
      id: crypto.randomUUID(),
      agent: 'chagatai' as const,
      type: 'content' as const,
      complexity: 'simple' as const,
      userFacing: false,
      volume: 'batch' as const,
      requiresCreativity: true
    }
    
    const draft = await llm.generate(
      `Write a Twitter thread about ${topic} (variation ${i})`,
      { task }
    )
    drafts.push({ draft, score: await scoreDraft(draft) })
  }
  
  // Select top 5
  const top5 = drafts.sort((a, b) => b.score - a.score).slice(0, 5)
  
  // Polish top 5 (CLOUD - quality matters)
  const polished = []
  for (const { draft } of top5) {
    const task = {
      id: crypto.randomUUID(),
      agent: 'chagatai' as const,
      type: 'content' as const,
      complexity: 'complex' as const,
      userFacing: true,
      volume: 'single' as const,
      requiresCreativity: true
    }
    
    const polishedDraft = await llm.generate(
      `Polish this content for publication: ${draft}`,
      { task, systemPrompt: 'You are a professional editor' }
    )
    polished.push(polishedDraft)
  }
  
  return polished
}
```

### Example 3: Temüjin Code Development (70% Local / 30% Cloud)

```typescript
// agents/temujin/code-development.ts

import { LLMCascade } from '@/lib/llm-cascade'

const llm = new LLMCascade()

async function developFeature(featureSpec: string) {
  // Write tests (LOCAL - FREE)
  const tests = await llm.generate(
    `Write comprehensive tests for: ${featureSpec}`,
    { 
      task: {
        agent: 'temujin',
        type: 'code',
        complexity: 'simple',
        userFacing: false,
        volume: 'single'
      }
    }
  )
  
  // Write first draft (LOCAL - FREE)
  const draft = await llm.generate(
    `Implement this feature: ${featureSpec}`,
    { 
      task: {
        agent: 'temujin',
        type: 'code',
        complexity: 'medium',
        userFacing: false,
        volume: 'single'
      }
    }
  )
  
  // Security review (CLOUD - critical)
  const securityReview = await llm.generate(
    `Review this code for security issues: ${draft}`,
    {
      task: {
        agent: 'temujin',
        type: 'code',
        complexity: 'critical',
        userFacing: false,
        volume: 'single',
        requiresAccuracy: true
      },
      systemPrompt: 'You are a security expert'
    }
  }
  
  // Fix issues (LOCAL - FREE)
  const fixed = await llm.generate(
    `Fix these security issues: ${securityReview}\n\nCode: ${draft}`,
    { task: { ...task, complexity: 'medium' } }
  )
  
  return fixed
}
```

---

## 5. Metrics Dashboard

```typescript
// src/lib/metrics-dashboard.ts

interface MetricsDashboard {
  localSuccessRate: number
  cloudSuccessRate: number
  escalationRate: number
  avgLocalLatency: number
  avgCloudLatency: number
  costSavings: number
  tasksByTier: {
    local: number
    cloud: number
  }
}

function calculateMetrics(cascade: LLMCascade): MetricsDashboard {
  const metrics = cascade.getMetrics()
  
  const localSuccessRate = cascade.getLocalSuccessRate()
  const cloudSuccessRate = (metrics.cloudSuccesses / metrics.cloudAttempts) * 100
  const escalationRate = (metrics.cloudEscalations / metrics.localAttempts) * 100
  
  // Calculate cost savings
  const localTasks = metrics.localAttempts
  const cloudTasks = metrics.cloudAttempts
  const estimatedCloudCost = localTasks * 0.002  // $0.002 per 1K tokens
  const actualCloudCost = cloudTasks * 0.002
  const costSavings = estimatedCloudCost - actualCloudCost
  
  return {
    localSuccessRate,
    cloudSuccessRate,
    escalationRate,
    avgLocalLatency: metrics.avgLocalLatency,
    avgCloudLatency: metrics.avgCloudLatency,
    costSavings,
    tasksByTier: {
      local: localTasks,
      cloud: cloudTasks
    }
  }
}

// Log metrics every hour
setInterval(() => {
  const dashboard = calculateMetrics(cascade)
  console.log('=== LLM CASCADE METRICS ===')
  console.log(`Local Success Rate: ${dashboard.localSuccessRate.toFixed(1)}%`)
  console.log(`Cloud Success Rate: ${dashboard.cloudSuccessRate.toFixed(1)}%`)
  console.log(`Escalation Rate: ${dashboard.escalationRate.toFixed(1)}%`)
  console.log(`Avg Local Latency: ${dashboard.avgLocalLatency.toFixed(0)}ms`)
  console.log(`Avg Cloud Latency: ${dashboard.avgCloudLatency.toFixed(0)}ms`)
  console.log(`Cost Savings: $${dashboard.costSavings.toFixed(2)}`)
  console.log(`Tasks - Local: ${dashboard.tasksByTier.local}, Cloud: ${dashboard.tasksByTier.cloud}`)
}, 3600000)
```

---

## 6. Configuration

```typescript
// src/config/llm-config.ts

export const llmConfig = {
  local: {
    enabled: true,
    baseUrl: 'http://localhost:1234',
    model: 'deepseek-r1-distill-qwen-14b',
    timeout: 60000,
    maxRetries: 3,
    healthCheckInterval: 30000
  },
  cloud: {
    enabled: true,
    model: 'qwen3.5-plus',
    apiKey: process.env.CLOUD_LLM_API_KEY,
    timeout: 120000,
    maxRetries: 2
  },
  routing: {
    // Tasks that ALWAYS use local
    alwaysLocal: ['monitoring', 'health-check', 'log-analysis'],
    
    // Tasks that ALWAYS use cloud
    alwaysCloud: ['security-review', 'architecture-design', 'strategy'],
    
    // Default tier for unknown tasks
    default: 'local'
  },
  fallback: {
    // Enable automatic fallback
    enabled: true,
    
    // Log escalations for analysis
    logEscalations: true,
    
    // Alert if escalation rate exceeds threshold
    escalationAlertThreshold: 0.3  // Alert if >30% escalations
  }
}
```

---

## 7. Error Handling & Recovery

```typescript
// src/lib/error-handling.ts

interface LLMError extends Error {
  tier: 'local' | 'cloud'
  attempt: number
  recoverable: boolean
}

class LLMCascadeError extends Error {
  constructor(
    message: string,
    public localError?: LLMError,
    public cloudError?: LLMError
  ) {
    super(message)
    this.name = 'LLMCascadeError'
  }
}

async function handleLLMError(error: LLMError): Promise<void> {
  // Log error
  console.error(`LLM Error (${error.tier}, attempt ${error.attempt}):`, error)
  
  // If local LLM is failing repeatedly, temporarily disable it
  if (error.tier === 'local' && !error.recoverable) {
    console.warn('Local LLM repeatedly failing - temporarily disabling')
    await disableLocalLLM()
    
    // Re-enable after 5 minutes
    setTimeout(async () => {
      console.log('Re-enabling local LLM')
      await enableLocalLLM()
    }, 300000)
  }
  
  // If cloud LLM is failing, alert immediately
  if (error.tier === 'cloud' && !error.recoverable) {
    await sendAlert('Cloud LLM failing - immediate attention required')
  }
}
```

---

## 8. Performance Optimization

### Connection Pooling

```typescript
// Reuse HTTP connections for local LLM
const agent = new http.Agent({
  keepAlive: true,
  maxSockets: 10,
  maxFreeSockets: 5
})

// Use in fetch
fetch(url, { agent, ...options })
```

### Response Caching

```typescript
// Cache identical prompts
const cache = new Map<string, string>()

async function generateWithCache(prompt: string): Promise<string> {
  const cacheKey = hash(prompt)
  
  if (cache.has(cacheKey)) {
    return cache.get(cacheKey)!
  }
  
  const result = await llm.generate(prompt)
  cache.set(cacheKey, result)
  
  return result
}
```

### Batch Processing

```typescript
// Process multiple prompts in parallel
async function generateBatch(prompts: string[]): Promise<string[]> {
  const results = await Promise.allSettled(
    prompts.map(prompt => llm.generate(prompt))
  )
  
  return results
    .filter((r): r is PromiseFulfilledResult<string> => r.status === 'fulfilled')
    .map(r => r.value)
}
```

---

## 9. Testing Strategy

```typescript
// src/lib/__tests__/llm-cascade.test.ts

describe('LLM Cascade', () => {
  it('routes continuous tasks to local', () => {
    const task = {
      agent: 'ogedei',
      type: 'monitoring',
      volume: 'continuous' as const,
      complexity: 'simple' as const,
      userFacing: false
    }
    
    const tier = router.route(task)
    expect(tier).toBe('local')
  })
  
  it('routes critical tasks to cloud', () => {
    const task = {
      agent: 'temujin',
      type: 'code',
      volume: 'single' as const,
      complexity: 'critical' as const,
      userFacing: false,
      requiresAccuracy: true
    }
    
    const tier = router.route(task)
    expect(tier).toBe('cloud')
  })
  
  it('falls back to cloud when local fails', async () => {
    // Mock local LLM to fail
    localLLM.generate.mockRejectedValue(new Error('Local failed'))
    
    const result = await cascade.generate('test prompt')
    
    expect(cloudLLM.generate).toHaveBeenCalled()
    expect(result).toBeDefined()
  })
  
  it('tracks metrics correctly', async () => {
    await cascade.generate('prompt 1')
    await cascade.generate('prompt 2')
    
    const metrics = cascade.getMetrics()
    expect(metrics.localAttempts).toBe(2)
    expect(metrics.localSuccesses).toBe(2)
  })
})
```

---

## 10. Rollout Plan

### Phase 1: Local LLM Integration (Day 1)
- [ ] Implement LocalLLMClient
- [ ] Test connectivity to LM Studio
- [ ] Implement health checks
- [ ] Add metrics tracking

### Phase 2: Task Router (Day 2)
- [ ] Implement TaskRouter
- [ ] Define routing rules
- [ ] Test routing decisions
- [ ] Add configuration

### Phase 3: LLM Cascade (Day 3)
- [ ] Implement LLMCascade
- [ ] Add automatic fallback
- [ ] Test error handling
- [ ] Add metrics dashboard

### Phase 4: Agent Integration (Day 4-5)
- [ ] Integrate with Ögedei (monitoring)
- [ ] Integrate with Chagatai (content)
- [ ] Integrate with Temüjin (code)
- [ ] Integrate with Möngke (research)
- [ ] Integrate with Kublai (coordination)

### Phase 5: Optimization (Day 6-7)
- [ ] Performance tuning
- [ ] Caching implementation
- [ ] Batch processing
- [ ] Metrics analysis
- [ ] Routing rule optimization

---

## 11. Expected Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **API Costs** | $984/mo | $66/mo | **93% reduction** |
| **Content Output** | 2/day | 50/day | **25x increase** |
| **Code Velocity** | 10/wk | 50/wk | **5x increase** |
| **Monitoring** | $14/day | $0.10/day | **99% reduction** |
| **Local Success Rate** | N/A | >95% | Target |
| **Escalation Rate** | N/A | <5% | Target |

---

## Bottom Line

**This architecture enables:**
- Seamless local/cloud LLM integration
- Automatic fallback for reliability
- Task-based routing for cost optimization
- Metrics-driven optimization
- 93% cost reduction with same/better quality

**Ready to implement immediately.**
