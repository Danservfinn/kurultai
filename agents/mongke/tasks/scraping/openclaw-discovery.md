# OpenClaw Discovery Task

**Agent:** Mongke (Research)  
**Priority:** HIGH  
**Frequency:** Every 12 hours  
**Skill:** scrapling-research

---

## Objective

Discover new tools, skills, tips, tricks, and integrations for OpenClaw that would be helpful for the Kurultai.

---

## Target Sources

| Source | URL | Focus |
|--------|-----|-------|
| **GitHub** | https://github.com/search?q=openclaw | Skills, plugins, forks |
| **GitHub** | https://github.com/search?q=claude-code+skill | Claude Code skills |
| **NPM** | https://www.npmjs.com/search?q=openclaw | NPM packages |
| **PyPI** | https://pypi.org/search/?q=openclaw | Python packages |
| **ClawHub** | https://clawhub.com | Community skills |
| **Reddit** | https://reddit.com/r/claude | Tips, discussions |
| **Discord** | https://discord.gg/clawd | Community announcements |
| **Twitter/X** | https://x.com/search?q=openclaw | Announcements |
| **Dev.to** | https://dev.to/search?q=openclaw | Tutorials |
| **Medium** | https://medium.com/search?q=openclaw | Articles |

---

## Execution

```python
from skills.scrapling_research.spiders.openclaw_discovery import OpenClawDiscoverySpider

# Run discovery
spider = OpenClawDiscoverySpider(
    output_file='agents/mongke/data/openclaw_discovery_{timestamp}.json',
    max_results=50
)
result = spider.start()

# Review results
for item in result.items:
    print(f"Found: {item.get('title')}")
    print(f"  Source: {item.get('source')}")
    print(f"  URL: {item.get('url')}")
    print(f"  Category: {item.get('category')}")
```

---

## Output

**Location:** `agents/mongke/data/openclaw_discovery_*.json`

**Format:**
```json
[
  {
    "title": "OpenClaw Skill: Weather API",
    "url": "https://github.com/user/openclaw-weather-skill",
    "source": "github.com",
    "category": "skill",
    "description": "Weather integration for OpenClaw agents",
    "stars": 45,
    "found_at": "2026-03-04T14:00:00"
  }
]
```

---

## Categories

| Category | Description |
|----------|-------------|
| **skill** | New OpenClaw skills to install |
| **plugin** | Claude Code plugins |
| **integration** | API integrations (Slack, Discord, etc.) |
| **tool** | Developer tools for OpenClaw |
| **tutorial** | How-to guides and tips |
| **discussion** | Community discussions with insights |
| **announcement** | Official announcements |

---

## Alert Triggers

Notify Kublai if:
- [ ] New official OpenClaw skill released
- [ ] Claude Code plugin with high stars (>100)
- [ ] Integration for missing service (e.g., WhatsApp, Slack)
- [ ] Security vulnerability disclosed
- [ ] Major OpenClaw update announced
- [ ] Community skill with >50 GitHub stars

---

## Integration

Results feed into:
1. **Kublai Dashboard** — New capabilities overview
2. **Skills Backlog** — Candidates for installation
3. **Weekly Report** — Ecosystem trends

---

*Task template created: 2026-03-04*
