# Competitor Intelligence Task

**Agent:** Jochi (Intelligence)  
**Priority:** HIGH  
**Frequency:** Every 6 hours  
**Skill:** scrapling-research

---

## Objective

Monitor Parse.com competitors for pricing changes, feature updates, and strategic moves.

---

## Target Sites

| Competitor | URL | Focus |
|------------|-----|-------|
| Back4App | https://www.back4app.com/pricing | Pricing, features |
| ParsePlatform | https://parseplatform.org/ | Official updates |
| Supabase | https://supabase.com/pricing | Alternative positioning |
| Firebase | https://firebase.google.com/pricing | Google's offering |

---

## Execution

```python
from skills.scrapling_research.spiders.competitor_monitor import CompetitorMonitorSpider

# Run competitor monitor
spider = CompetitorMonitorSpider(
    output_file='agents/jochi/data/competitor_scan_{timestamp}.json'
)
result = spider.start()

# Analyze results
for item in result.items:
    print(f"Scraped: {item.get('url')}")
    print(f"  Prices: {item.get('prices', [])}")
    print(f"  Features: {len(item.get('features', []))} found")
```

---

## Output

**Location:** `agents/jochi/data/competitor_scan_*.json`

**Format:**
```json
[
  {
    "url": "https://www.back4app.com/pricing",
    "timestamp": "2026-03-04T14:00:00",
    "title": "Back4App Pricing",
    "prices": ["$5/month", "$25/month", "$200/month"],
    "features": ["Unlimited requests", "Custom domain", "Support"],
    "jobs": []
  }
]
```

---

## Alert Triggers

Create escalation if:
- [ ] New pricing tier detected (±20% from baseline)
- [ ] New feature category mentioned
- [ ] Job postings mention "Parse migration" or "Parse alternative"
- [ ] Marketing messaging targets Parse directly

---

## Integration

Results feed into:
1. **Neo4j** — Store in `Competitor` nodes
2. **Kublai Dashboard** — Strategic overview
3. **Weekly Report** — Trend analysis

---

*Task template created: 2026-03-04*
