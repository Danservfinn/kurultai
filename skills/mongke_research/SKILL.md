# Mongke Research Skill

**Created:** 2026-03-04  
**Version:** 1.0.0  
**Status:** ✅ Active

---

## Overview

Automated research skill for Mongke (Researcher agent) that combines:
- **Scrapling** — Web scraping with adaptive parsing, anti-bot bypass
- **Ollama (qwen3.5:9b)** — Local LLM for analysis and synthesis
- **Neo4j** — Knowledge graph storage

**Purpose:** Enable Mongke to conduct comprehensive research tasks autonomously.

---

## Installation

Already installed (uses existing Scrapling + Ollama setup).

**Dependencies:**
- scrapling>=0.4.1 ✅
- ollama (qwen3.5:9b model) ✅
- neo4j Python driver ✅
- searxng (optional, for auto source discovery) ⚠️

### Optional: SearXNG for Auto Source Discovery

SearXNG enables automatic web search to find research sources.

**Option A: Self-host with Docker**
```bash
mkdir -p ~/searxng && cd ~/searxng
curl -sL https://raw.githubusercontent.com/searxng/searxng/master/docker/docker-compose.yml -o docker-compose.yml
docker compose up -d
```

See `SEARXNG-SETUP.md` for detailed setup instructions.

**Option B: Manual URLs**
If SearXNG isn't available, provide URLs manually to the research method.

---

## Usage

### Basic Research Query

```bash
python3 skills/mongke-research/research.py \
  --query "What is the history of OpenClaw?" \
  --sources "https://github.com/openclaw/openclaw" \
  --output neo4j
```

### Multi-Source Research

```bash
python3 skills/mongke-research/research.py \
  --query "Compare Parse.com alternatives" \
  --sources "https://back4app.com,https://supabase.com,https://firebase.google.com" \
  --depth 2 \
  --output neo4j,json
```

### Focused Topic Research

```bash
python3 skills/mongke-research/research.py \
  --topic "esoteric symbolism" \
  --subtopics "crayfish,zodiac,moon tarot" \
  --build-graph \
  --tags "esoteric,occult,symbolism"
```

---

## Features

| Feature | Description |
|---------|-------------|
| **Adaptive Scraping** | Survives website redesigns automatically |
| **Cloudflare Bypass** | StealthyFetcher handles protected sites |
| **Local LLM Analysis** | Ollama qwen3.5:9b for privacy, no API costs |
| **Knowledge Graph** | Neo4j storage with entities, concepts, relationships |
| **Multi-Source** | Parallel crawling of multiple URLs |
| **Depth Control** | Crawl 1-N levels deep per source |
| **Tagging System** | Organize findings by topic/tags |

---

## Output Formats

| Format | Description |
|--------|-------------|
| **Neo4j** | Knowledge graph (entities, concepts, relationships) |
| **JSON** | Structured research report |
| **Markdown** | Human-readable summary |
| **All** | All three formats |

---

## Files

```
skills/mongke-research/
├── SKILL.md                 # This documentation
├── research.py              # Main research orchestrator
├── scraper.py               # Scrapling wrapper
├── analyzer.py              # Ollama analysis module
├── knowledge_graph.py       # Neo4j storage module
└── templates/
    ├── entity_prompt.txt    # Entity extraction prompt
    └── synthesis_prompt.txt # Report synthesis prompt
```

---

## Example Workflow

```
1. User assigns research task to Mongke
2. Mongke calls mongke-research skill
3. Skill scrapes target URLs with Scrapling
4. Ollama analyzes content, extracts entities/concepts
5. Findings saved to Neo4j knowledge graph
6. Summary report returned to Mongke
7. Mongke reports findings to user
```

---

## Integration with Mongke

Mongke can invoke this skill via:

```python
from skills.mongke_research.research import ResearchSkill

skill = ResearchSkill()
result = skill.research(
    query="Research topic here",
    sources=["url1", "url2"],
    output="neo4j"
)
```

Or via CLI from task scripts:

```bash
python3 skills/mongke-research/research.py --query "..." --sources "..."
```

---

## Neo4j Schema

**Nodes:**
- `ResearchEntity` — Organizations, people, places
- `ResearchConcept` — Ideas, theories, themes
- `ResearchSource` — URLs, documents

**Relationships:**
- `RELATED_TO` — General association
- `DERIVED_FROM` — Concept from source
- `INFLUENCES` — Entity influences entity
- `SYMBOLIZES` — Symbol relationships

**Properties:**
- `tags` — Topic categorization
- `confidence` — LLM confidence score (0-1)
- `sources` — Source URLs
- `created` — Timestamp

---

## Performance

| Metric | Value |
|--------|-------|
| **Pages/minute** | ~10-20 (single-threaded) |
| **Analysis time** | ~5-10s per page (Ollama) |
| **Neo4j write** | ~100ms per entity |
| **Token usage** | ~500-1000 tokens/page |

---

## Best Practices

1. **Start narrow** — 2-3 sources, depth=1
2. **Review first pass** — Check entity extraction quality
3. **Scale up** — Increase depth/sources once validated
4. **Tag consistently** — Use consistent tagging for graph queries
5. **Build incrementally** — Each research adds to knowledge graph

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Ollama timeout | Increase `--ollama-timeout` (default: 90s) |
| Scrapling blocked | Add `--stealthy` flag for Cloudflare sites |
| Neo4j connection | Verify `bolt://localhost:7687` is accessible |
| Empty results | Check source URLs, try `--depth 2` |

---

*Skill ready for Mongke research tasks.*
