# Kurultai X/Twitter Maintenance System

Automated Twitter presence management for the Kurultai multi-agent system.

## Overview

This system maintains Kurultai's X/Twitter presence through automated:
- **Scheduled posting**: 2-3 tweets per day (9am, 2pm, 7pm)
- **Community engagement**: Likes and retweets of AI/developer content
- **Weekly summaries**: Sunday threads on system achievements

## Files

| File | Description |
|------|-------------|
| `twitter_maintenance.py` | Main Python script with API client, queue, and orchestrator |
| `twitter_cron.txt` | Cron job definitions (alternative to LaunchAgent) |
| `ai.kurultai.twitter-maintenance.plist` | macOS LaunchAgent for scheduled execution |

## Installation

### Option 1: LaunchAgent (macOS, Recommended)

```bash
# Copy plist to LaunchAgents
cp ai.kurultai.twitter-maintenance.plist ~/Library/LaunchAgents/

# Load the agent
launchctl load ~/Library/LaunchAgents/ai.kurultai.twitter-maintenance.plist

# Verify it's loaded
launchctl list | grep kurultai
```

### Option 2: Cron (Linux/macOS)

```bash
# Add cron jobs
crontab ~/.openclaw/agents/main/scripts/twitter_cron.txt

# Verify
crontab -l
```

## Usage

### Manual Commands

```bash
# Initialize content queue
python3 twitter_maintenance.py init

# Post one scheduled tweet
python3 twitter_maintenance.py tweet

# Run community engagement
python3 twitter_maintenance.py engage

# Post weekly summary (Sundays only)
python3 twitter_maintenance.py weekly

# Auto mode (determines action by time)
python3 twitter_maintenance.py auto

# Check status
python3 twitter_maintenance.py status

# Add custom tweet
python3 twitter_maintenance.py --add-tweet "Your tweet here" --category insight --approve
```

### Content Categories

- `technical` - Technical deep-dives and architecture
- `achievement` - System milestones and metrics
- `community` - Questions and engagement
- `insight` - Observations and opinions
- `summary` - Weekly summary threads

## Data Storage

- **Queue database**: `~/.openclaw/data/twitter_queue.db` (SQLite)
- **Logs**: `~/.openclaw/logs/twitter-maintenance.log`
- **Credentials**: `~/.openclaw/agents/main/.x_api_credentials`

## Schedule

| Time | Action | Days |
|------|--------|------|
| 9:00 AM | Morning tweet | Daily |
| 12:00 PM | Community engagement | Daily |
| 2:00 PM | Afternoon tweet | Daily |
| 7:00 PM | Evening tweet | Daily |
| 10:00 AM | Weekly summary | Sundays |

## Safety Features

1. **Rate limiting**: Built-in tracking of X API rate limits
2. **Content approval**: Queue supports approved/unapproved content
3. **Duplicate prevention**: Content hash checking
4. **Pause capability**: Stop LaunchAgent with `launchctl unload`
5. **Filtered engagement**: Avoids controversial topics

## Rate Limits

The system respects X API v2 limits:
- **Tweets**: 200 per 24 hours
- **Likes**: 1000 per 24 hours
- **Retweets**: 1000 per 24 hours

## Monitoring

```bash
# Check recent log output
tail -f ~/.openclaw/logs/twitter-maintenance.log

# Check queue status
python3 twitter_maintenance.py status

# Check LaunchAgent status
launchctl list | grep kurultai
```

## Content Queue

Default content is pre-populated with 13 approved tweets across categories. Add more:

```bash
python3 twitter_maintenance.py \
  --add-tweet "Your custom tweet here" \
  --category technical \
  --approve
```

## Uninstall

```bash
# Unload LaunchAgent
launchctl unload ~/Library/LaunchAgents/ai.kurultai.twitter-maintenance.plist
rm ~/Library/LaunchAgents/ai.kurultai.twitter-maintenance.plist

# Or remove cron jobs
crontab -e  # Delete the kurultai lines

# Clean data (optional)
rm ~/.openclaw/data/twitter_queue.db
```

## Troubleshooting

### Script won't run
```bash
# Check Python and dependencies
python3 --version
pip3 install requests
```

### API errors
- Verify credentials in `~/.openclaw/agents/main/.x_api_credentials`
- Check rate limit status in logs
- Ensure API tokens haven't expired

### Duplicate tweets
- The system prevents duplicates via content hashing
- Clear queue and re-init if needed: `rm ~/.openclaw/data/twitter_queue.db && python3 twitter_maintenance.py init`
