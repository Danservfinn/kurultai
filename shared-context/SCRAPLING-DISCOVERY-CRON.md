# OpenClaw Discovery Cron Job ✅

**Date:** 2026-03-04  
**Status:** COMPLETE  
**Cron ID:** `3e18b42c-7c3a-4801-8c1c-42b575484f7f`

---

## Overview

Automated discovery of new OpenClaw tools, skills, integrations, and community resources.

**Purpose:** Keep the Kurultai informed about new capabilities, security updates, and ecosystem developments.

---

## Configuration

| Setting | Value |
|---------|-------|
| **Name** | Scrapling: OpenClaw Discovery |
| **Schedule** | Every 12 hours (43,200,000 ms) |
| **Agent** | Mongke (Research) |
| **Output** | `agents/mongke/data/openclaw_discovery_*.json` |
| **Status** | ✅ Enabled |

---

## What It Discovers

| Category | Sources | Examples |
|----------|---------|----------|
| **Skills** | GitHub, ClawHub | Community-built agent skills |
| **Plugins** | NPM, PyPI | Claude Code plugins, Python packages |
| **Integrations** | Docs, tutorials | API integrations, webhooks |
| **Tutorials** | Medium, Dev.to, DigitalOcean | How-to guides, best practices |
| **Security** | Security blogs, advisories | Vulnerability reports, patches |
| **Community** | Discord, Reddit, Twitter | Announcements, discussions |

---

## Execution

### Manual Run

```bash
python3 ~/.openclaw/agents/main/scripts/find-openclaw-resources.py
```

### Output Location

```
~/.openclaw/agents/main/agents/mongke/data/openclaw_discovery_YYYYMMDD_HHMM.json
```

### Sample Output

```json
[
  {
    "title": "ClawHub - Community Skills",
    "url": "https://clawhub.ai/",
    "source": "clawhub.ai",
    "category": "skill",
    "description": "Community-built skills marketplace (5,700+ skills)",
    "found_at": "2026-03-04T14:12:44"
  },
  {
    "title": "OpenClaw Security Best Practices",
    "url": "https://www.malwarebytes.com/blog/...",
    "source": "malwarebytes.com",
    "category": "security",
    "description": "Security considerations for OpenClaw deployment",
    "found_at": "2026-03-04T14:12:44"
  }
]
```

---

## Alert Triggers

Mongke should notify Kublai if discovery finds:

- [ ] **New official skill** released by OpenClaw team
- [ ] **Security vulnerability** disclosed (CVE, advisory)
- [ ] **Major update** announced (version bump, breaking changes)
- [ ] **High-value integration** (Slack, Salesforce, etc.)
- [ ] **Community skill** with 100+ GitHub stars
- [ ] **Performance breakthrough** (new model support, speed improvements)

---

## Integration with Kurultai

### Mongke (Research)
- Reviews discovery results every 12 hours
- Filters for relevant items
- Creates tasks for promising skills

### Kublai (Strategy)
- Receives weekly summary of ecosystem trends
- Decides which skills to install
- Plans integration roadmap

### Jochi (Intelligence)
- Monitors security-related discoveries
- Tracks competitor/alternative tools

---

## Next Run

**Scheduled:** Every 12 hours from anchor time  
**Next:** Check cron state for exact timestamp

---

## Files Created

| File | Purpose |
|------|---------|
| `scripts/find-openclaw-resources.py` | Discovery script |
| `agents/mongke/tasks/scraping/openclaw-discovery.md` | Task template |
| `skills/scrapling-research/spiders/openclaw_discovery.py` | Spider (alternative) |
| `shared-context/SCRAPLING-DISCOVERY-CRON.md` | This documentation |

---

## Cron Jobs Summary

| Job | Schedule | Purpose |
|-----|----------|---------|
| **Scrapling: OpenClaw Discovery** | Every 12 hours | Ecosystem monitoring |
| **Scrapling: Competitor Monitoring** | Every 6 hours | Parse competitor tracking |
| tock-gather | Every 30 min | System telemetry |
| heartbeat-watchdog | Every 5 min | Gateway health |
| Hourly Kurultai Reflection | Every hour | Agent reflection |

---

*Discovery cron configured and running.*
