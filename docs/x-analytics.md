# X/Twitter Analytics Dashboard for OpenClaw

Complete analytics system for tracking OpenClaw's X/Twitter presence, growth metrics, and engagement patterns.

## Overview

The X Analytics system provides:
- **Daily metric collection** from X API (followers, engagement, posts)
- **Web dashboard** for visualizing trends and performance
- **Automated reporting** with markdown and JSON exports
- **Content pillar analysis** to understand what resonates
- **Attribution tracking framework** for measuring impact

## Quick Start

### 1. Initial Setup

```bash
# Initialize the database
cd ~/.openclaw/agents/ogedei
python3 scripts/x-analytics.py --init-db
```

### 2. Configure X API Access (Optional)

For real data, set your X API Bearer Token:

```bash
export X_BEARER_TOKEN="your_bearer_token_here"
```

Without a token, the system uses **mock data** for testing.

### 3. Collect Metrics

```bash
# Collect and store metrics
python3 scripts/x-analytics.py --collect

# Generate reports
python3 scripts/x-report-generator.py --dashboard
```

### 4. View Dashboard

```bash
# Start the web dashboard
python3 scripts/x-dashboard.py

# Open in browser: http://localhost:5678
```

## Components

### Scripts

| Script | Purpose |
|--------|---------|
| `x-analytics.py` | Core analytics engine - collects metrics from X API |
| `x-report-generator.py` | Generates reports (JSON, markdown) |
| `x-dashboard.py` | Flask web dashboard server |
| `x-analytics-collect.sh` | Wrapper script for cron automation |

### Data Storage

- **Database:** `data/x-analytics.db` (SQLite)
- **Dashboard JSON:** `data/x-dashboard.json`
- **Reports:** `workspace/x-reports/`
- **Logs:** `logs/x-analytics.log`

### Database Schema

| Table | Purpose |
|-------|---------|
| `daily_metrics` | Daily follower/following snapshots |
| `posts` | Individual tweet metrics |
| `content_pillars` | Aggregated performance by content type |
| `attribution_events` | Clicks, installs, joins (framework) |
| `hourly_performance` | Best posting times analysis |

## Usage

### Command Line

```bash
# Initialize database
python3 scripts/x-analytics.py --init-db

# Test API connection (or mock data)
python3 scripts/x-analytics.py --test

# Collect metrics
python3 scripts/x-analytics.py --collect

# View summary
python3 scripts/x-analytics.py --summary 7

# Generate dashboard JSON
python3 scripts/x-report-generator.py --dashboard

# Generate markdown report
python3 scripts/x-report-generator.py --markdown --report weekly

# Generate everything
python3 scripts/x-report-generator.py --all

# Start web dashboard
python3 scripts/x-dashboard.py [--port 8080] [--host 0.0.0.0]
```

### Web Dashboard

The dashboard displays:
- **Metric cards:** Followers, engagement rate, impressions, likes
- **Growth chart:** 7-day follower trend
- **Content pillars:** Performance by content type
- **Top posts:** Best performing tweets with engagement breakdown

## Metrics Tracked

### Growth Metrics
- Follower count (daily)
- Follower growth rate (weekly)
- Following count
- Follower/following ratio

### Engagement Metrics
- Impressions per post
- Likes per post (average)
- Retweets per post (average)
- Replies per post (average)
- Engagement rate %: `(likes + retweets + replies) / impressions × 100`

### Content Pillars
Posts are automatically classified into:
- **Announcement:** Product releases, new features
- **Tutorial:** How-to guides, walkthroughs
- **Community:** Shoutouts, welcomes
- **Question:** Questions, requests for feedback
- **Share:** Links, resources
- **General:** Unclassified content

### Attribution Framework
Placeholders for tracking:
- Clicks to documentation (via UTM parameters)
- Clicks to GitHub
- New installations
- Discord joins

## Automation

### Cron Job

A cron job is configured in `~/.openclaw/cron/jobs.json`:

```json
{
  "name": "X/Twitter Analytics Daily Collection",
  "schedule": "0 9 * * *",
  "enabled": true
}
```

This runs `x-analytics-collect.sh` daily at 9 AM local time.

### Collection Script

The wrapper script (`x-analytics-collect.sh`):
1. Initializes database if needed
2. Runs `x-analytics.py --collect`
3. Runs `x-report-generator.py --dashboard`
4. Logs to `logs/x-analytics-collection.log`
5. Optional: Signal notification (if configured)

## X API Requirements

### API Tiers

| Tier | Cost | Tweet Lookup | Metrics |
|------|------|--------------|---------|
| **Free** | $0 | Last 7 days, 10 requests/15min | Basic public metrics |
| **Basic** | $100/mo | Last 30 days, 10k tweets/month | Full metrics, 1 request/sec |
| **Pro** | $5,000/mo | Full archive, 1M tweets/month | Full metrics + webhooks |

### Current Implementation

The code works with **any tier**:
- Free tier: Limited data (last 7 days only)
- Basic/Pro: Full historical data

**Without API access**, the system uses mock data for testing.

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `X_BEARER_TOKEN` | X API v2 Bearer Token | (empty = mock data) |
| `OPENCLAW_X_USERNAME` | X username to track | `@openclaw` |
| `X_ANALYTICS_DB` | Database path | `data/x-analytics.db` |
| `X_ANALYTICS_LOG` | Log file path | `logs/x-analytics.log` |
| `X_ANALYTICS_SIGNAL_RECIPIENT` | Signal number for alerts | (optional) |

## Troubleshooting

### No data appears in dashboard

1. Run collection manually: `python3 scripts/x-analytics.py --collect`
2. Check logs: `tail -f logs/x-analytics.log`
3. Verify database exists: `ls -la data/x-analytics.db`

### API authentication errors

- Verify `X_BEARER_TOKEN` is set correctly
- Check token hasn't expired
- Free tier has rate limits — wait 15 minutes between requests

### Engagement rate shows 0%

- Old data before engagement calculation was added — re-run collection
- Check if impressions are 0 (X API sometimes doesn't provide impressions)

### Dashboard won't start

- Install Flask: `pip3 install flask`
- Check port 5678 isn't in use: `lsof -i :5678`
- Use different port: `python3 scripts/x-dashboard.py --port 8080`

## Development

### Adding New Metrics

1. Add collection logic to `XAnalytics` class in `x-analytics.py`
2. Add database table in `init_database()`
3. Add report generation in `XReportGenerator` class
4. Update dashboard template if displaying

### Adding New Content Pillars

Edit `CONTENT_PILLAR_KEYWORDS` in `x-analytics.py`:

```python
CONTENT_PILLAR_KEYWORDS = {
    "announcement": ["announce", "release", "new"],
    "your_pillar": ["keyword1", "keyword2"],
}
```

## File Locations

```
~/.openclaw/agents/ogedei/
├── scripts/
│   ├── x-analytics.py           # Core analytics engine
│   ├── x-report-generator.py    # Report generation
│   ├── x-dashboard.py           # Web dashboard
│   └── x-analytics-collect.sh   # Collection wrapper
├── templates/
│   └── x-dashboard.html         # Dashboard UI
├── data/
│   ├── x-analytics.db           # SQLite database
│   └── x-dashboard.json         # Dashboard data export
├── workspace/x-reports/
│   └── x-analytics-*.md         # Generated reports
├── logs/
│   └── x-analytics.log          # Collection logs
└── docs/
    └── x-analytics.md           # This file
```

## License

Part of the OpenClaw multi-agent system.

## Support

For issues or questions:
1. Check logs: `logs/x-analytics.log`
2. Run test: `python3 scripts/x-analytics.py --test`
3. Create an issue in the OpenClaw repository
