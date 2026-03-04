# Scrapling Research Skill

**Created:** 2026-03-04  
**Version:** 1.0.0  
**Status:** ✅ Active

---

## Overview

Web scraping and data extraction skill for the Kurultai using Scrapling framework.

**Capabilities:**
- Adaptive web scraping (survives website redesigns)
- Cloudflare Turnstile bypass
- Concurrent crawling with pause/resume
- MCP server integration for AI-assisted scraping
- Multiple fetcher types (HTTP, stealthy, dynamic)

---

## Installation

```bash
# Already installed via Phase 1
pip install "scrapling[all]"
playwright install chromium
```

**Dependencies:**
- scrapling==0.4.1
- playwright==1.56.0
- curl_cffi>=0.14.0
- browserforge>=1.2.4
- mcp>=1.26.0

---

## Usage

### Python Client

```python
from skills.scrapling_research.scrapling_client import ScraplingClient

client = ScraplingClient()

# Simple fetch
page = client.fetch('https://example.com')

# Stealthy fetch (bypass Cloudflare)
page = client.stealth_fetch('https://protected-site.com')

# Extract data
items = page.css('.item')
for item in items:
    print(item.css('h2::text').get())
```

### CLI Test

```bash
# Test installation
python3 -c "from scrapling.fetchers import Fetcher; page = Fetcher.get('https://quotes.toscrape.com/'); print(f'Scraped {len(page.css(\".quote\"))} quotes')"
```

---

## Example Spiders

### Competitor Monitor

```python
from scrapling.spiders import Spider, Response

class CompetitorMonitor(Spider):
    name = "competitor"
    start_urls = ["https://competitor1.com/pricing", "https://competitor2.com/pricing"]
    
    async def parse(self, response: Response):
        yield {
            "url": response.url,
            "pricing": response.css('.price::text').getall(),
            "features": response.css('.feature::text').getall()
        }
```

### News Gatherer

```python
from scrapling.spiders import Spider, Response

class NewsGatherer(Spider):
    name = "news"
    start_urls = ["https://techcrunch.com", "https://venturebeat.com"]
    concurrent_requests = 10
    
    async def parse(self, response: Response):
        for article in response.css('article'):
            yield {
                "title": article.css('h2::text').get(),
                "url": article.css('a::attr(href)').get(),
                "date": article.css('time::attr(datetime)').get()
            }
```

---

## Agent Integration

| Agent | Use Case | Example |
|-------|----------|---------|
| **Jochi** | Threat intel, error analysis | Monitor security blogs, CVE databases |
| **Mongke** | Market research | Track competitor pricing, features |
| **Chagatai** | Content sourcing | Find trending topics, news |
| **Temujin** | Parse monitoring | Competitor analysis |
| **Kublai** | Strategic intelligence | Multi-source data aggregation |

---

## MCP Server

Start the MCP server for AI-assisted scraping:

```bash
scrapling mcp-server --port 8989
```

Claude/Cursor can then call scraping tools via natural language.

---

## Files

```
skills/scrapling-research/
├── SKILL.md              # This file
├── scrapling_client.py   # Python client library
└── spiders/
    ├── __init__.py
    ├── competitor_monitor.py
    └── news_gatherer.py
```

---

## Testing

```bash
# Basic test
python3 skills/scrapling_research/scrapling_client.py

# Run spider
python3 -c "from skills.scrapling_research.spiders.competitor_monitor import CompetitorMonitor; CompetitorMonitor().start()"
```

---

*Phase 1 complete. Ready for agent integration (Phase 2).*
