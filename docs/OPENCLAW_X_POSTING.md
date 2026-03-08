# OpenClaw X/Twitter Posting System

Automated posting system for OpenClaw updates to X/Twitter with approval workflow and scheduling.

## Overview

The OpenClaw X posting system generates and posts updates from task metrics, including:
- Daily system status (8 AM)
- "Building in public" updates (4 PM)
- Weekly summary threads (Fridays 10 AM)
- Milestone celebrations (triggered automatically)
- Feature announcements

## Files

| File | Description |
|------|-------------|
| `scripts/x_poster.py` | Main posting logic with XPoster class |
| `scripts/x_content_generator.py` | Content generation from Neo4j metrics |
| `scripts/x-poster-control.sh` | Control script for pause/resume/status |
| `data/openclaw_x_posts.db` | SQLite queue for draft/scheduled posts |
| `logs/openclaw-x-poster.log` | Activity logs |
| `data/x_posting_paused` | Pause flag (exists = paused) |

## Setup

### Prerequisites

1. X API credentials configured at `~/.openclaw/agents/main/.x_api_credentials`
2. Neo4j running for task metrics (optional - uses mock data if unavailable)

### Verify Installation

```bash
# Check status
~/.openclaw/agents/main/scripts/x-poster-control.sh status

# Test content generation
python3 ~/.openclaw/agents/main/scripts/x_content_generator.py status
```

## Usage

### Control Script

```bash
# Show system status
x-poster-control.sh status

# Pause all automated posting
x-poster-control.sh pause

# Resume posting
x-poster-control.sh resume

# Post immediately (outside schedule)
x-poster-control.sh post-status      # Daily status
x-poster-control.sh post-public      # Build in public
x-poster-control.sh post-weekly      # Weekly summary

# List posts awaiting approval
x-poster-control.sh list-pending

# Approve a draft post
x-poster-control.sh approve <post-id>

# Dry run - see what would be posted
x-poster-control.sh dry-run
```

### Direct Python Usage

```bash
# Post daily status update
python3 x_poster.py post_status

# Post milestone
python3 x_poster.py milestone --milestone-type tasks --milestone-value 100

# Post feature announcement
python3 x_poster.py feature --feature-name "Auto-Retry" --feature-desc "Tasks now auto-retry on transient failures"

# Post a custom thread
python3 x_poster.py thread --topic "🧵 OpenClaw Architecture" --points "Point 1" "Point 2" "Point 3"

# View queue status
python3 x_poster.py status --json
```

## Content Generation

### Content Types

| Type | Description | Example |
|------|-------------|---------|
| `status` | Daily system metrics | "42 tasks completed, 95% success rate" |
| `build_public` | Behind-the-scenes updates | "Working on multi-agent reflection" |
| `weekly` | Week summary thread | "📊 Week 12 🧵" |
| `milestone` | Milestone celebration | "🎉 100 tasks completed!" |
| `feature` | New feature announcement | "✨ New Feature: Auto-Retry" |

### Generating Content

```python
from x_content_generator import ContentGenerator

gen = ContentGenerator()

# Generate status update
post = gen.generate_status_update()
print(post.text)

# Generate milestone post
post = gen.generate_milestone_post("tasks", 100)

# Generate feature announcement
post = gen.generate_feature_showcase("Auto-Retry", "Tasks auto-retry on transient failures")
```

## Scheduling

### Automated Posts (via cron/jobs.json)

| Time | Type | Cron Expression |
|------|------|-----------------|
| 8 AM ET | Daily status | `0 8 * * *` |
| 4 PM ET | Build in public | `0 16 * * *` |
| Fri 10 AM ET | Weekly review | `0 10 * * 5` |

### Schedule Custom Post

```python
from datetime import datetime, timedelta
from x_poster import XPoster

poster = XPoster()

# Schedule a post for tomorrow at noon
tomorrow = datetime.now() + timedelta(days=1)
tomorrow = tomorrow.replace(hour=12, minute=0, second=0, microsecond=0)

post_id = poster.schedule_post(
    content="Big announcement coming tomorrow! 🚀",
    scheduled_time=tomorrow,
    category="announcement"
)
```

## Approval Workflow

Posts go through these states:

```
DRAFT → APPROVED → SCHEDULED → POSTED
         ↓                      ↓
       (manual)            FAILED
```

### Process Flow

1. **Draft**: Post created in queue (unapproved)
2. **Approve**: Use `x-poster-control.sh approve <id>` or `python3 x_poster.py approve`
3. **Post**: System posts approved content automatically

### Listing Pending Posts

```bash
# List all draft posts
x-poster-control.sh list-pending

# Or with Python
python3 x_poster.py list_pending --json
```

## Milestones

Milestones are automatically tracked and posted once per unique value:

| Type | Thresholds |
|------|------------|
| `tasks` | 100, 500, 1000, 10000 |
| `uptime` | 7, 30, 90, 365 days |
| `agents` | 5, 10 agents |

### Trigger Milestone

```bash
# Manually post a milestone
python3 x_poster.py milestone --milestone-type tasks --milestone-value 100

# The system remembers which milestones were posted
# Duplicate milestones are automatically skipped
```

## Hashtags

Default hashtags included on all posts:
- `#OpenClaw`
- `#MultiAgent`
- `#AI`
- `#DevTools`

Additional hashtags by type:
- Milestone: `#Milestone`
- Feature: `#NewFeature`
- Build Public: `#BuildInPublic`, `#DevLog`

## Rate Limits

The system respects X API v2 limits:
- **Tweets**: 200 per 24 hours
- **Daily scheduled posts**: 2-3 (well under limits)
- **Status tracking**: Built-in rate limit awareness

## Emergency Controls

### Pause All Posting

```bash
# Create pause flag
x-poster-control.sh pause

# Or manually
touch ~/.openclaw/data/x_posting_paused
```

### Resume Posting

```bash
# Remove pause flag
x-poster-control.sh resume

# Or manually
rm ~/.openclaw/data/x_posting_paused
```

When paused, all scheduled posts are skipped. The pause flag is checked before each post.

## Monitoring

### Check Logs

```bash
# Real-time log monitoring
tail -f ~/.openclaw/logs/openclaw-x-poster.log

# Recent activity
tail -100 ~/.openclaw/logs/openclaw-x-poster.log
```

### Queue Status

```bash
# Full status overview
x-poster-control.sh status

# With JSON for parsing
python3 x_poster.py status --json
```

## Database Schema

### posts table
```sql
CREATE TABLE posts (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    category TEXT NOT NULL,
    status TEXT NOT NULL,           -- draft, approved, scheduled, posted, failed
    created_at TEXT,
    scheduled_for TEXT,
    posted_at TEXT,
    thread_items TEXT,              -- JSON array for threads
    hashtags TEXT,                  -- JSON array
    media_path TEXT,
    error_message TEXT,
    tweet_id TEXT                   -- X tweet ID if posted
)
```

### milestones table
```sql
CREATE TABLE milestones (
    milestone_type TEXT,
    milestone_value INTEGER,
    posted_at TEXT,
    PRIMARY KEY (milestone_type, milestone_value)
)
```

## Troubleshooting

### Post not appearing

1. Check if paused: `x-poster-control.sh status`
2. Check logs: `tail -f ~/.openclaw/logs/openclaw-x-poster.log`
3. Verify credentials: `cat ~/.openclaw/agents/main/.x_api_credentials`

### Rate limit errors

The system tracks rate limits automatically. If you hit limits:
1. Wait for reset (tracked in client state)
2. Check remaining: `python3 x_poster.py status --json`

### Neo4j connection errors

If Neo4j is unavailable, the content generator falls back to mock data. Check:
```bash
# Test Neo4j connectivity
cypher-shell -u neo4j -p password "RETURN 1"
```

## API Reference

### XPoster Class

```python
class XPoster:
    def post_status_update(self, dry_run: bool = False) -> bool
    def post_milestone(self, milestone_type: str, value: int, dry_run: bool = False) -> bool
    def post_feature_showcase(self, feature_name: str, description: str, dry_run: bool = False) -> bool
    def schedule_post(self, content: str, scheduled_time: datetime, category: str = "custom") -> str
    def generate_thread(self, topic: str, points: List[str], dry_run: bool = False) -> bool
    def get_pending_posts(self) -> List[Dict]
    def approve_post(self, post_id: str) -> bool
    def emergency_pause(self) -> None
    def resume(self) -> None
    def is_paused(self) -> bool
    def get_status(self) -> Dict
```

### ContentGenerator Class

```python
class ContentGenerator:
    def generate_status_update(self) -> GeneratedPost
    def generate_milestone_post(self, milestone_type: str, value: int) -> GeneratedPost
    def generate_feature_showcase(self, feature_name: str, description: str) -> GeneratedPost
    def generate_build_public(self) -> GeneratedPost
    def generate_weekly_thread(self) -> GeneratedPost
    def generate_from_template(self, template_type: str, **kwargs) -> GeneratedPost
```

## Development

### Adding New Post Types

1. Add generator method in `x_content_generator.py`:
```python
def generate_custom_type(self) -> GeneratedPost:
    stats = self.metrics.get_task_stats()
    text = f"Custom post with {stats['completed']} tasks"
    return GeneratedPost(text=text, category=PostCategory.CUSTOM, hashtags=[])
```

2. Add poster method in `x_poster.py`:
```python
def post_custom_type(self, dry_run: bool = False) -> bool:
    post = self.generator.generate_custom_type()
    post_id = self.queue.add_post(text=post.text, category=post.category.value)
    return self._post_queued(post_id)
```

3. Add cron job in `jobs.json` following existing format

## License

Part of the OpenClaw multi-agent system.
