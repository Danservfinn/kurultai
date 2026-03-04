# News Feed Task

**Agent:** Mongke (Research)  
**Priority:** MEDIUM  
**Frequency:** Every 4 hours  
**Skill:** scrapling-research

---

## Objective

Gather news articles for LLM Survivor events and Kurultai market intelligence.

---

## Target Sources

| Source | URL | Category |
|--------|-----|----------|
| TechCrunch | https://techcrunch.com/ | Startup news |
| VentureBeat | https://venturebeat.com/ | AI/ML focus |
| The Verge | https://www.theverge.com/ | Tech culture |
| Hacker News | https://news.ycombinator.com/ | Community trends |

---

## Execution

```python
from skills.scrapling_research.spiders.news_gatherer import NewsGathererSpider

# Run news gatherer
spider = NewsGathererSpider(
    max_articles=50,
    output_file='agents/mongke/data/news_feed_{timestamp}.json'
)
result = spider.start()

# Process articles
for article in result.items:
    print(f"Title: {article.get('title')}")
    print(f"Source: {article.get('source')}")
    print(f"URL: {article.get('url')}")
```

---

## Output

**Location:** `agents/mongke/data/news_feed_*.json`

**Format:**
```json
[
  {
    "source": "https://techcrunch.com/",
    "timestamp": "2026-03-04T14:00:00",
    "title": "AI Startup Raises $50M Series B",
    "url": "https://techcrunch.com/2026/03/04/ai-startup-raises-50m/",
    "author": "Sarah Johnson",
    "date": "2026-03-04",
    "summary": "The startup plans to use funds for..."
  }
]
```

---

## LLM Survivor Integration

Articles are filtered for relevance:
- AI/ML developments
- Multi-agent systems
- Startup funding
- Tech layoffs (affects talent pool)
- New LLM releases

Relevant articles → LLM Survivor event feed

---

## Alert Triggers

Notify Kublai if:
- [ ] Major Parse/backend-as-a-service news
- [ ] Competitor funding round (> $10M)
- [ ] AI agent breakthrough announced
- [ ] Regulatory changes affecting AI

---

## Integration

Results feed into:
1. **LLM Survivor** — Event generation
2. **Neo4j** — Market intelligence graph
3. **Chagatai** — Content sourcing

---

*Task template created: 2026-03-04*
