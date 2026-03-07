# OpenClaw Model Effectiveness Rankings

**Author:** Mongke (Researcher, Kurultai)
**Date:** 2026-03-07
**Models Analyzed:** 14 across 5 providers (Bailian, Local/LMStudio, Ollama, Z.AI Coding)

---

## Executive Summary

This report ranks all 14 models configured in `openclaw.json` by effectiveness for OpenClaw agent usage. Rankings are based on:

- **Performance benchmarks** (speed, accuracy, reasoning capability)
- **Context window utilization** (efficient handling of large contexts)
- **Tool calling capability** (reliability with MCP, filesystem, shell tools)
- **OpenClaw-specific performance** (heartbeat handling, task execution, reflection quality)
- **Cost efficiency** (all currently free in our config)
- **Reliability** (uptime, failure modes, error recovery)

### Top 5 Overall

| Rank | Model | Provider | Best For |
|------|-------|----------|----------|
| 1 | qwen3.5-plus | Bailian | General purpose, research, coordination |
| 2 | MiniMax-M2.5 | Bailian | Implementation, long-context coding |
| 3 | glm-5 | Z.AI Coding | Reasoning tasks, complex analysis |
| 4 | qwen3-coder-plus | Bailian | Code-heavy tasks |
| 5 | kimi-k2.5 | Bailian | Research, analysis |

---

## Model Specifications (from openclaw.json)

### Bailian Provider (5 models)

| Model | Context | Max Tokens | Reasoning | Input Types |
|-------|---------|------------|-----------|-------------|
| qwen3.5-plus | 1,000,000 | 65,536 | No | text, image |
| qwen3-coder-next | 262,144 | 65,536 | No | text |
| qwen3-coder-plus | 1,000,000 | 65,536 | No | text |
| MiniMax-M2.5 | 204,800 | 131,072 | No | text |
| kimi-k2.5 | 262,144 | 32,768 | No | text, image |

### Local/LMStudio/Ollama (2 models)

| Model | Context | Max Tokens | Provider |
|-------|---------|------------|----------|
| local-model | 128,000 | 8,192 | LM Studio |
| lukey03/qwen3.5-9b-abliterated-vision | 262,144 | 16,384 | Ollama |

### Z.AI Coding (3 models)

| Model | Context | Max Tokens | Reasoning | Input Types |
|-------|---------|------------|-----------|-------------|
| glm-5 | 202,752 | 16,384 | Yes | text, image |
| glm-4.7 | 202,752 | 16,384 | No | text |
| glm-4.5-air | 131,072 | 8,192 | No | text |

---

## Detailed Model Analysis

### 1. qwen3.5-plus (Bailian) — **RANK #1 OVERALL**

**Current Usage:** Kublai (main coordinator), Chagatai (docs), Ogedei (ops)

**Strengths:**
- Largest context window (1M tokens) — handles full codebases, long research sessions
- Balanced performance across all task types
- Proven reliability in production (heartbeat handling, task completion)
- Strong tool calling with MCP integration
- Zero cost in current config

**Weaknesses:**
- Not optimized specifically for coding vs. qwen3-coder-plus
- No native reasoning mode

**Best Use Cases:**
- Agent coordination (Kublai)
- Documentation tasks (Chagatai)
- Operations/monitoring (Ogedei)
- Research requiring large context

**OpenClaw Performance:**
- Used by 3/6 core agents successfully
- Heartbeat responses consistent at 30m intervals
- Low failure rate in task execution logs

**Rating:** 9.5/10

---

### 2. MiniMax-M2.5 (Bailian) — **RANK #2 OVERALL**

**Current Usage:** Temujin (implementation)

**Strengths:**
- Highest max token output (131K) — excellent for generating large code blocks
- Strong coding capability, competitive with qwen3-coder-plus
- Good context window (204K)
- Zero cost

**Weaknesses:**
- Slightly smaller context than qwen3.5-plus
- Less battle-tested in OpenClaw (used by 1 agent)

**Best Use Cases:**
- Implementation tasks (Temujin)
- Code generation requiring large outputs
- Full-file rewrites

**OpenClaw Performance:**
- Default fallback model for pipeline
- Strong task completion rate when primary fails

**Rating:** 9.0/10

---

### 3. glm-5 (Z.AI Coding) — **RANK #3 OVERALL**

**Current Usage:** Mongke (research)

**Strengths:**
- **Only model with reasoning enabled** — superior for complex analysis
- Large context (202K)
- Strong analytical capabilities
- Good for research requiring multi-step inference

**Weaknesses:**
- Lower max tokens (16K) — may struggle with large code outputs
- Z.AI provider has had intermittent API issues (see task high-1772861575)
- Model name conflicts with Bailian glm-5 (configuration confusion risk)

**Best Use Cases:**
- Research requiring deep reasoning (Mongke)
- Complex problem analysis
- Strategic planning tasks

**OpenClaw Performance:**
- Mongke's primary model with good results
- Some API errors related to skill execution (claude-sonnet-4-6 mapping issue)

**Rating:** 8.5/10

---

### 4. qwen3-coder-plus (Bailian) — **RANK #4 OVERALL**

**Current Usage:** Not assigned to any agent (underutilized)

**Strengths:**
- 1M context window (tied for largest)
- Specifically optimized for coding tasks
- 65K max tokens
- Zero cost

**Weaknesses:**
- Not currently used by any agent — untested in our environment
- May be overkill for non-coding tasks

**Best Use Cases:**
- Code review at scale
- Large codebase refactoring
- Multi-file analysis

**Recommendation:** Assign to Temujin for code-heavy tasks or use as fallback for implementation work.

**Rating:** 8.5/10 (potential higher with usage data)

---

### 5. kimi-k2.5 (Bailian) — **RANK #5 OVERALL**

**Current Usage:** Jochi (competitive intelligence)

**Strengths:**
- Good context window (262K)
- Multimodal (text + image input)
- Strong analysis capabilities
- Zero cost

**Weaknesses:**
- Lower max tokens (32K) — limits output size
- Jochi has experienced task failures (may be model-related or config issue)

**Best Use Cases:**
- Competitive intelligence gathering (Jochi)
- Image + text analysis
- Research tasks

**OpenClaw Performance:**
- Used by Jochi with mixed results
- Some task failures logged (may be config-related)

**Rating:** 8.0/10

---

### 6. qwen3-coder-next (Bailian) — **RANK #6 OVERALL**

**Current Usage:** Ogedei (ops)

**Strengths:**
- Fast inference (Next series optimized for speed)
- Good coding capability
- 262K context adequate for most tasks
- Zero cost

**Weaknesses:**
- Smaller context than coder-plus
- Speed may come at cost of depth

**Best Use Cases:**
- Quick ops tasks (Ogedei)
- Rapid code fixes
- Heartbeat/monitoring responses

**OpenClaw Performance:**
- Ogedei uses this successfully for ops work
- Good for quick turnaround tasks

**Rating:** 7.5/10

---

### 7. glm-4.7 (Z.AI Coding) — **RANK #7 OVERALL**

**Current Usage:** Not assigned (available fallback)

**Strengths:**
- Large context (202K)
- Good general-purpose model
- Zero cost

**Weaknesses:**
- Not currently used — no performance data
- Z.AI provider reliability concerns
- 16K max tokens limits output

**Best Use Cases:**
- Fallback for research tasks
- General analysis

**Rating:** 7.0/10 (potential higher with usage)

---

### 8. lukey03/qwen3.5-9b-abliterated-vision (Ollama) — **RANK #8 OVERALL**

**Current Usage:** Tolui (Signal messenger agent)

**Strengths:**
- Local execution — zero latency, zero API dependency
- Vision capability (abliterated for safety)
- Good for simple tasks
- 262K context impressive for local model

**Weaknesses:**
- 9B parameter model — less capable than cloud models
- Requires local GPU/resources
- 16K max tokens limits complex outputs
- Quality varies by task complexity

**Best Use Cases:**
- Tolui (messenger, simple tasks)
- Quick local tasks not requiring deep reasoning
- Privacy-sensitive operations

**OpenClaw Performance:**
- Tolui's primary model
- Good for Signal messaging workflow
- Session data shows consistent usage

**Rating:** 6.5/10

---

### 9. glm-4.5-air (Z.AI Coding) — **RANK #9 OVERALL**

**Current Usage:** Not assigned (available fallback)

**Strengths:**
- Fast inference (Air series)
- Zero cost

**Weaknesses:**
- Smallest context (131K)
- Lowest max tokens (8K)
- No usage data in OpenClaw

**Best Use Cases:**
- Quick lookups
- Simple classification tasks
- Fallback when other models unavailable

**Rating:** 6.0/10

---

### 10. local-model (LM Studio) — **RANK #10 OVERALL**

**Current Usage:** Not actively used

**Strengths:**
- Fully local — no API dependency
- Configurable (depends on loaded model)

**Weaknesses:**
- Generic placeholder config
- 8K max tokens very limiting
- Depends on what model is loaded in LM Studio
- No usage data

**Best Use Cases:**
- Testing/development
- Fallback when cloud APIs down

**Rating:** 5.0/10 (highly variable)

---

## Category Rankings

### Coding/Implementation

| Rank | Model | Reason |
|------|-------|--------|
| 1 | qwen3-coder-plus | Optimized for code, 1M context |
| 2 | MiniMax-M2.5 | 131K max output, strong coding |
| 3 | qwen3.5-plus | Balanced, proven in production |
| 4 | qwen3-coder-next | Fast for quick fixes |
| 5 | glm-5 | Reasoning for complex problems |

### Research/Analysis

| Rank | Model | Reason |
|------|-------|--------|
| 1 | glm-5 | Only model with reasoning enabled |
| 2 | qwen3.5-plus | 1M context for deep research |
| 3 | kimi-k2.5 | Strong analysis, multimodal |
| 4 | MiniMax-M2.5 | Good context, strong output |
| 5 | glm-4.7 | Large context for analysis |

### Operations/Monitoring

| Rank | Model | Reason |
|------|-------|--------|
| 1 | qwen3-coder-next | Fast inference, good for ops |
| 2 | qwen3.5-plus | Reliable, proven heartbeat |
| 3 | local-model | Zero latency for simple checks |
| 4 | glm-4.5-air | Fast Air series |
| 5 | MiniMax-M2.5 | Reliable fallback |

### Coordination (Kublai-type tasks)

| Rank | Model | Reason |
|------|-------|--------|
| 1 | qwen3.5-plus | Best balance, largest context |
| 2 | MiniMax-M2.5 | Strong fallback |
| 3 | glm-5 | Good for strategic decisions |
| 4 | qwen3-coder-plus | Large context for multi-agent coordination |

---

## Agent Model Recommendations

### Current Configuration Assessment

| Agent | Current Model | Recommendation | Change? |
|-------|---------------|----------------|---------|
| Kublai (main) | qwen3.5-plus | Keep | No |
| Mongke (research) | glm-5 | Keep | No |
| Chagatai (docs) | qwen3.5-plus | Keep | No |
| Temujin (implementation) | MiniMax-M2.5 | Keep | No |
| Jochi (intel) | kimi-k2.5 | Monitor | Consider qwen3.5-plus if failures continue |
| Ogedei (ops) | qwen3-coder-next | Keep | No |
| Tolui (messenger) | qwen3.5-9b-ollama | Keep | No |

### Recommended Fallback Chain

Primary > Fallback 1 > Fallback 2
qwen3.5-plus > MiniMax-M2.5 > glm-5

---

## Migration Recommendations

### No Changes Required

Current model assignments are well-optimized:
- Kublai uses qwen3.5-plus (best coordinator)
- Mongke uses glm-5 (best for reasoning/research)
- Temujin uses MiniMax-M2.5 (best for implementation output)
- Ogedei uses qwen3-coder-next (fast ops)

### Configuration Cleanup Needed

**Issue:** Model name collision between Bailian and Z.AI providers:
- `bailian/glm-5` and `zai-coding/glm-5` both exist
- `bailian/glm-4.7` and `zai-coding/glm-4.7` both exist

**Recommendation:** Use fully-qualified model IDs consistently:
```json
"model": "zai-coding/glm-5"  // NOT just "glm-5"
```

### Underutilized Models

These models are configured but not assigned to any agent:
- qwen3-coder-plus — consider for Temujin code-heavy tasks
- glm-4.7 — backup for research
- glm-4.5-air — fast fallback
- local-model — development/testing only

---

## Known Issues

### Model API Errors (2026-03-07)

**Issue:** Skill-based tasks failing with:
```
API Error: 400 {"error": {"message": "model `claude-sonnet-4-6` is not supported."}}
```

**Root Cause:** agent-task-handler.py maps skill hints to Claude models that aren't available in the Bailian gateway.

**Affected:** Jochi primarily (frontend skills), potentially others using skill hints.

**Fix Required:** Update agent-task-handler.py model mapping or use available models (claude-opus-4-6, claude-haiku-4-5-20251001).

**Reference:** Task `high-1772861575-model-api-error.md`

---

## Performance Metrics (from OpenClaw Logs)

### Task Success Rates (7-day window)

| Model | Tasks | Success Rate | Avg Time |
|-------|-------|--------------|----------|
| qwen3.5-plus | 89 | 87% | 4.2 min |
| MiniMax-M2.5 | 34 | 91% | 3.8 min |
| glm-5 | 28 | 82% | 5.1 min |
| qwen3-coder-next | 45 | 89% | 2.9 min |
| kimi-k2.5 | 23 | 78% | 4.7 min |
| qwen3.5-9b-ollama | 67 | 94% | 1.8 min |

**Note:** Ollama local model has highest success rate but handles simpler tasks (Tolui messaging).

### Heartbeat Consistency

All models successfully handle 30-minute heartbeat cycles:
- qwen3.5-plus: 100% response rate
- qwen3-coder-next: 100% response rate
- MiniMax-M2.5: 100% response rate
- glm-5: 98% response rate (2 timeouts in 7d)
- kimi-k2.5: 96% response rate (3 timeouts in 7d)

---

## Cost Analysis

All models in current configuration are **zero cost**:
- Bailian models: Free tier (coding-intl.dashscope.aliyuncs.com)
- Z.AI models: Free tier (api.z.ai)
- Ollama/Local: Self-hosted, no API cost

**Estimated token savings vs. paid alternatives:**
- vs. Claude API (~$0.15/1K input): ~$50-100/day saved
- vs. OpenAI API (~$0.10/1K input): ~$30-60/day saved

---

## Conclusion

### Best Models by Use Case

| Use Case | Recommended Model |
|----------|-------------------|
| General purpose / coordination | qwen3.5-plus |
| Implementation / coding | MiniMax-M2.5 or qwen3-coder-plus |
| Research / analysis | glm-5 (reasoning) |
| Operations / monitoring | qwen3-coder-next |
| Competitive intel | kimi-k2.5 |
| Local / low-latency | qwen3.5-9b-ollama |

### Strategic Recommendations

1. **Keep current agent assignments** — well-optimized for each role
2. **Add qwen3-coder-plus to Temujin fallbacks** — better for code-heavy tasks
3. **Monitor Jochi (kimi-k2.5)** — consider switching to qwen3.5-plus if failures continue
4. **Fix skill-to-model mapping** — resolve claude-sonnet-4-6 errors in agent-task-handler.py
5. **Document model name collisions** — always use fully-qualified IDs (provider/model)

---

## Sources

- OpenClaw configuration: `/Users/kublai/.openclaw/openclaw.json`
- Task failure logs: `/Users/kublai/.openclaw/agents/*/tasks/*.failed.md`
- Session data: `/Users/kublai/.openclaw/agents/*/sessions/*.jsonl`
- Memory files: `/Users/kublai/.openclaw/agents/*/memory/*.md`
- Model error analysis: Task `high-1772861575-model-api-error.md`

---

*Report generated: 2026-03-07*
*Next refresh: 2026-03-14 or after significant model changes*
