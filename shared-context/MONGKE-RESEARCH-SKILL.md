# Mongke Research Skill — Installation Complete

**Date:** 2026-03-04  
**Status:** ✅ Installed (Ollama timeout issue noted)

---

## Overview

Automated research skill combining:
- **Scrapling** — Web scraping with adaptive parsing
- **Ollama (qwen3.5:9b)** — Local LLM for analysis
- **Neo4j** — Knowledge graph storage

---

## Files Created

```
skills/mongke-research/
├── SKILL.md              # Documentation (4.7 KB)
├── __init__.py           # Package init
├── research.py           # Main orchestrator (13 KB)
└── templates/            # Prompt templates (empty)
```

---

## Usage

```bash
cd ~/.openclaw/agents/main

# Basic research
python3 skills/mongke-research/research.py \
  --query "Your research question" \
  --sources "https://url1.com,https://url2.com" \
  --output neo4l,json

# Topic-based research
python3 skills/mongke-research/research.py \
  --topic "Esoteric symbolism" \
  --subtopics "crayfish,zodiac,tarot" \
  --tags "esoteric,occult"
```

---

## Integration with Mongke

Mongke can invoke via Python:

```python
import sys
sys.path.insert(0, '/Users/kublai/.openclaw/agents/main')

from skills.mongke_research.research import MongkeResearchSkill

skill = MongkeResearchSkill()
result = skill.research(
    query="Research question",
    sources=["https://url1.com", "https://url2.com"],
    output="neo4j"
)
```

Or via CLI from task scripts.

---

## Known Issues

### Ollama Timeout

**Issue:** Ollama qwen3.5:9b can be slow to respond (30-60s for first request).

**Workaround:**
- Increase `--ollama-timeout` (default: 90s)
- First request may take longer (model loading)
- Subsequent requests are faster

**Fix in progress:** Ollama service is running but slow.

---

## Neo4j Schema

**Nodes Created:**
- `ResearchEntity` — Organizations, people, places, symbols
- `ResearchConcept` — Ideas, theories, themes

**Relationships:**
- `RELATED_TO` — General associations

**Properties:**
- `tags` — Topic categorization
- `confidence` — LLM confidence (0-1)
- `query` — Original research query
- `updated` — Timestamp

---

## Output Formats

| Format | Description |
|--------|-------------|
| **neo4j** | Knowledge graph (default) |
| **json** | Structured report file |
| **markdown** | Human-readable summary |

---

## Next Steps

1. **Test with longer timeout** — `--ollama-timeout 180`
2. **Create Mongke task** — Assign research task using skill
3. **Build knowledge graph** — Each research adds to Neo4j

---

*Skill ready. Ollama timeout needs monitoring.*
