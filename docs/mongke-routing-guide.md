# Mongke Routing Guide

## Purpose
This document clarifies domain boundaries for the Researcher agent (mongke) to reduce misroutes and ensure research tasks are properly routed.

## Mongke's Domain: Primary Output is RESEARCH FINDINGS

Tasks routed to mongke MUST have **research/investigation** as their PRIMARY output.

### ACCEPTED Task Types (with examples)

| Task Type | Example Tasks | Primary Output |
|-----------|---------------|----------------|
| **competitor research** | "Research competitor pricing", "Analyze competitor features" | Competitor findings |
| **market research** | "Research market trends", "Market analysis for X" | Market insights |
| **api discovery** | "Discover APIs for Y", "Find available APIs for Z" | API inventory |
| **llm research** | "Compare GPT vs Claude models", "Research AI model providers" | Model comparison |
| **pricing research** | "Research SaaS pricing benchmarks", "Pricing analysis" | Pricing data |
| **landscape analysis** | "Analyze ecosystem landscape", "Technology landscape report" | Landscape overview |
| **source gathering** | "Gather sources on topic X", "Find research on Y" | Source collection |
| **benchmarking** | "Benchmark competitors", "Performance comparison research" | Benchmark results |

### REJECTED Task Types (route elsewhere)

| Task Type | Example | Route To | Why |
|-----------|---------|----------|-----|
| code implementation | "Implement API client" | temujin | Primary output is code |
| security audit | "Review for vulnerabilities" | jochi | Security analysis, not research |
| ops monitoring | "Investigate server error" | ogedei | Ops investigation |
| documentation | "Write API documentation" | chagatai | Content creation, not research |
| testing | "Research test frameworks" → then implement | temujin | Output is code/tests |
| config analysis | "Analyze agent config" | jochi | Config analysis |
| calendar/backup ops | "Investigate calendar notifications" | ogedei | Ops, not research |

## Routing Decision Tree

```
Is the PRIMARY OUTPUT research findings?
├─ Yes → Is it discovering NEW information (not analyzing existing)?
│  ├─ Yes → mongke (Researcher)
│  └─ No → Check jochi (analyst) for existing data analysis
└─ No → Not mongke (route by primary output type)
```

## Keyword Ambiguity Resolution

Some keywords overlap with other agents. Use PRIMARY OUTPUT test:

| Keyword | mongke context | Other agent context |
|---------|----------------|-------------------|
| "investigate" | investigate market/competitors/APIs | investigate error → ogedei |
| "analyze" | analyze market/competitor data | analyze code/logs → jochi/ogedei |
| "research" | research external topics | research existing code → temujin |
| "discover" | discover APIs/competitors | discover bugs → jochi |
| "study" | study market trends | study code → temujin |
| "benchmark" | benchmark competitors | benchmark performance → jochi |

## AI/LLM Research Keywords (Added 2026-03-11)

The following keywords now route to mongke for AI/LLM research:

| Keywords | Example Tasks |
|----------|---------------|
| `llm`, `gpt`, `claude`, `anthropic`, `openai` | "Research Claude vs GPT models" |
| `alibaba`, `z.ai`, `dashscope` | "Investigate DashScope model capabilities" |
| `model comparison`, `ai model`, `language model` | "Compare AI model providers" |
| `embedding`, `vector`, `rag` | "Research embedding databases for RAG" |
| `model benchmark`, `ai pricing`, `api pricing` | "Benchmark LLM pricing" |
| `llm evaluation`, `model capabilities` | "Evaluate model capabilities" |
| `context window`, `token limit`, `rate limit` | "Research model limits" |

## Common Misroutes and Corrections

| Misroute | Correct Route | Reason |
|----------|---------------|--------|
| "Investigate calendar bug" | ogedei | Ops bug investigation |
| "Analyze agent config" | jochi | Config analysis (not external research) |
| "Implement API client" | temujin | Code implementation |
| "Write API docs" | chagatai | Documentation (content) |
| "Fix model error" | ogedei | Ops error fix |
| "Research code for bugs" | jochi | Code analysis, not external research |
| "Investigate CPU usage" | ogedei | System monitoring, not research |

## Special Cases

### "Research and implement" tasks
- "Research X and implement" → temujin (primary output is code)
- "Research X for documentation" → chagatai (primary output is content)
- "Research X" (pure research) → mongke

### "Analysis" tasks
- Analysis of external data (market/competitor) → mongke
- Analysis of internal data (logs/metrics) → jochi
- Code analysis → jochi

### "Investigate" tasks
- investigate + external noun (market, competitor, API) → mongke
- investigate + internal noun (error, queue, CPU, calendar) → ogedei

## Disambiguation Rules (MONGKE_RESEARCH_PROTECTION)

The following rules prevent non-research tasks from routing to mongke:

| Pattern | Target | Rationale |
|---------|--------|-----------|
| `investigate calendar/cron/backup/notification` | ogedei | Calendar/backup are ops, not research |
| `enhance config` | jochi | Config enhancement is analysis |
| `bidirectional linking` | temujin | Development task |
| `design research competitors/market/trend/pricing` | mongke | Actual market research (phrase match) |
| `design research` (generic) | temujin | Design tasks are dev, not research |

## When in Doubt: Primary Output Test

Ask: **What is the PRIMARY deliverable?**

- Deliverable is research findings/data → mongke
- Deliverable is code → temujin
- Deliverable is prose/content → chagatai
- Deliverable is analysis/report on internal systems → jochi
- Deliverable is system health/ops → ogedei

## Domain Compatibility (for Load Balancing)

Mongke is compatible with the following domains:
- `research` (primary)
- `autoresearch`
- `analysis` (with jochi, kublai, tolui)
- `documentation` (with chagatai, tolui)

## Skill Hints for Mongke

| Agent + Keyword | Skill Hint |
|-----------------|------------|
| mongke + "research" | `/horde-learn` |
| mongke + "investigate" | `/horde-learn` |
| mongke + "discover" | `/horde-learn` |
| mongke + "scrape" | `/scrapling-research` |
| mongke + "crawl" | `/scrapling-research` |

## Version History
- 2026-03-11: Initial version with AI/LLM research keywords and disambiguation rules
