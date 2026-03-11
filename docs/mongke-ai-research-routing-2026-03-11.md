# mongke AI/LLM Research Routing Enhancement (2026-03-11)

## Problem
mongke had near-zero utilization (2 tasks in 7 days) because the routing keywords did not include AI/LLM research terms. This was a critical gap given:
- The Kurultai fleet runs on Z.AI (Alibaba DashScope) models
- Anthropic API is used as a fallback
- No keywords existed to route research about AI providers, LLMs, or model comparisons

## Solution
Expanded research keywords across 4 locations to include AI/LLM terminology:

### 1. kurultai_paths.py - AGENT_KEYWORDS["mongke"]
Added 14 new AI/LLM keywords:
- Providers: `llm`, `gpt`, `claude`, `anthropic`, `openai`, `alibaba`, `z.ai`, `dashscope`
- Research types: `model comparison`, `ai model`, `language model`, `embedding`, `vector`, `rag`
- Analysis: `model benchmark`, `ai pricing`, `api pricing comparison`, `provider comparison`
- Evaluation: `model research`, `ai research`, `llm evaluation`, `model capabilities`, `ai provider`

### 2. task_intake.py - DOMAIN_KEYWORDS["research"]
Added same 14 AI/LLM keywords for domain classification consistency

### 3. task_intake.py - _PRIMARY_OUTPUT_PATTERNS["research"]
Added 5 AI/LLM keywords for primary output test:
- `llm`, `model comparison`, `ai model`, `provider comparison`, `llm evaluation`

### 4. task_intake.py - CATEGORY_KEYWORDS["research"]
Added 4 AI/LLM keywords for category detection:
- `llm`, `model comparison`, `ai model`, `provider comparison`

### 5. task_intake.py - _DISAMBIGUATION
Added 4 new rules BEFORE `({"investigate", "model"}, "ogedei")` to prevent AI model research from being routed to ops:
- `({"investigate", "model", "capabilities"}, "mongke")`
- `({"investigate", "ai", "model"}, "mongke")`
- `({"investigate", "llm"}, "mongke")`
- `({"investigate", "language", "model"}, "mongke")`
- `({"investigate", "embedding"}, "mongke")`

## Verification

### AI/LLM Research Routing (10/10 PASS)
```
✓ research alibaba dashscope models                  -> mongke
✓ compare gpt vs claude vs openai                    -> mongke
✓ llm provider pricing comparison                    -> mongke
✓ investigate z.ai model capabilities                -> mongke
✓ benchmark ai language models                       -> mongke
✓ research embedding and vector databases for rag    -> mongke
✓ investigate llm providers                          -> mongke
✓ investigate ai model features                      -> mongke
✓ research openai gpt models                         -> mongke
✓ claude vs gpt comparison research                  -> mongke
```

### Research Protection Rules (6/6 PASS)
Non-research tasks correctly do NOT route to mongke:
```
✓ investigate calendar notifications       -> ogedei
✓ enhance agent config                     -> jochi
✓ bidirectional linking                    -> temujin
✓ fix model error                          -> ogedei
✓ investigate cpu usage                    -> ogedei
✓ investigate queue depth                  -> ogedei
```

## Impact
- mongke can now receive and route AI/LLM research tasks
- Protection rules (R006) remain intact - non-research still blocked
- Domain keywords, primary output test, and category detection all updated for consistency

## Files Modified
1. `/Users/kublai/.openclaw/agents/main/scripts/kurultai_paths.py` (AGENT_KEYWORDS)
2. `/Users/kublai/.openclaw/agents/main/scripts/task_intake.py` (4 sections updated)
