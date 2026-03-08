# X/Twitter Analytics Dashboard for OpenClaw Growth Tracking

**Objective:** Build a comprehensive analytics system to track OpenClaw's X/Twitter presence, growth metrics, engagement patterns, and attribution.

**Created:** 2026-03-08
**Estimated Duration:** 3-4 hours
**Risk Level:** MEDIUM (depends on X API access)

## Phase 0: Prerequisites & Setup

### Task 0.1: Verify X API Access
- Check for existing X API credentials in environment or config
- Identify required API tier (Free/Basic/Pro) for needed metrics
- Document which metrics are available at current access level

**Duration:** 15 minutes

### Task 0.2: Create Data Storage Schema
- Design SQLite schema for metrics storage
- Create tables: `daily_metrics`, `posts`, `content_pillars`, `attribution_events`
- Add indexes for efficient querying

**Exit Criteria Phase 0:**
- [ ] X API credentials confirmed or placeholder documented
- [ ] Database schema created at `data/x-analytics.db`
- [ ] All tables verified with `.schema` command

**Duration:** 30 minutes

---

## Phase 1: Core Analytics Engine

### Task 1.1: Create `scripts/x-analytics.py`
Implement the main analytics collection class:

```python
class XAnalytics:
    def __init__(self, db_path, bearer_token):
        # Initialize database connection and API client

    def fetch_user_metrics(self):
        # Get follower count, following count, ratio

    def fetch_recent_tweets(self, count=100):
        # Get recent tweets with metrics

    def fetch_tweet_metrics(self, tweet_id):
        # Get detailed metrics for specific tweet

    def calculate_engagement_rate(self, impressions, likes, retweets, replies):
        # (likes + retweets + replies) / impressions * 100

    def classify_content_pillar(self, tweet_text):
        # Classify: announcement, tutorial, community, question, share

    def store_daily_metrics(self):
        # Store today's metrics snapshot

    def store_post_metrics(self):
        # Store individual post metrics
```

**Duration:** 60 minutes

### Task 1.2: Create `scripts/x-report-generator.py`
Implement report generation:

```python
class XReportGenerator:
    def __init__(self, db_path):
        # Load data from database

    def generate_growth_report(self, period="daily"):
        # Follower growth, growth rate, ratio trends

    def generate_engagement_report(self, period="weekly"):
        # Avg impressions, likes, retweets, replies, engagement rate

    def generate_content_performance_report(self):
        # Top posts, best times, pillar breakdown

    def generate_community_report(self):
        # New owners discovered, engaged, questions, setups

    def generate_attribution_report(self):
        # Clicks, installs, joins (if trackable)

    def generate_dashboard_json(self):
        # Export all metrics for dashboard display

    def generate_markdown_report(self, period="weekly"):
        # Human-readable report
```

**Duration:** 45 minutes

**Exit Criteria Phase 1:**
- [ ] `scripts/x-analytics.py` exists and passes syntax check
- [ ] `scripts/x-report-generator.py` exists and passes syntax check
- [ ] Manual test: `python3 scripts/x-analytics.py --test` runs without errors
- [ ] Database tables created on first run

**Dependencies:** Phase 0 must be complete

---

## Phase 2: Dashboard Frontend

### Task 2.1: Create Web Dashboard
Create `scripts/x-dashboard.py` - a lightweight web dashboard:

```python
from flask import Flask, render_template, jsonify
import json

app = Flask(__name__)

@app.route('/')
def dashboard():
    return render_template('x-dashboard.html')

@app.route('/api/metrics/<period>')
def get_metrics(period):
    # Return JSON metrics for daily/weekly/monthly

@app.route('/api/top-posts')
def get_top_posts():
    # Return top performing posts

if __name__ == '__main__':
    app.run(port=5678)
```

**Duration:** 45 minutes

### Task 2.2: Create Dashboard HTML Template
Create `templates/x-dashboard.html` with:
- Metric cards (followers, engagement rate, etc.)
- Growth trend chart (Chart.js or simple CSS bars)
- Top posts table
- Content pillar breakdown
- Time filters (day/week/month)

**Duration:** 60 minutes

**Exit Criteria Phase 2:**
- [ ] `python3 scripts/x-dashboard.py` starts without errors
- [ ] Dashboard accessible at http://localhost:5678
- [ ] All metric cards display data (or "No data" message)
- [ ] Time filters work correctly

**Dependencies:** Phase 1 must be complete

---

## Phase 3: Automated Collection

### Task 3.1: Create Collection Script
Create `scripts/x-analytics-collect.sh`:
```bash
#!/bin/bash
# Run analytics collection
cd ~/.openclaw/agents/ogedei
python3 scripts/x-analytics.py --collect
python3 scripts/x-report-generator.py --update-dashboard
```

**Duration:** 15 minutes

### Task 3.2: Add Cron Job
Add to `~/.openclaw/cron/jobs.json`:
```json
{
  "name": "x-analytics-daily",
  "schedule": "0 9 * * *",
  "command": "~/.openclaw/agents/ogedei/scripts/x-analytics-collect.sh",
  "description": "Daily X/Twitter analytics collection at 9 AM"
}
```

**Duration:** 15 minutes

**Exit Criteria Phase 3:**
- [ ] `scripts/x-analytics-collect.sh` is executable
- [ ] Cron entry added to jobs.json
- [ ] Manual test run completes successfully

**Dependencies:** Phase 1 must be complete

---

## Phase 4: Testing & Validation

### Task 4.1: Integration Test
- Run full collection pipeline
- Verify data stored in database
- Generate sample reports
- Display dashboard

**Duration:** 30 minutes

### Task 4.2: Edge Case Handling
- Handle API rate limits
- Handle missing/malformed data
- Handle network failures gracefully
- Add logging to all operations

**Duration:** 30 minutes

**Exit Criteria Phase 4:**
- [ ] Full pipeline runs end-to-end without errors
- [ ] Dashboard displays realistic data structure
- [ ] Errors logged to `logs/x-analytics.log`
- [ ] API rate limits respected

**Dependencies:** Phases 1, 2, 3 must be complete

---

## Phase 5: Documentation

### Task 5.1: Create Documentation
Create `docs/x-analytics.md` with:
- Setup instructions
- API credential requirements
- Usage examples
- Dashboard access info
- Troubleshooting guide

**Duration:** 30 minutes

**Exit Criteria Phase 5:**
- [ ] Documentation exists and is complete
- [ ] All setup steps verified

**Dependencies:** All previous phases complete

---

## Success Criteria

1. **Data Collection:** Daily metrics automatically collected and stored
2. **Dashboard Access:** Web dashboard displays all requested metric categories
3. **Reporting:** Weekly reports can be generated on demand
4. **Reliability:** Collection runs automatically via cron with error handling
5. **Attribution:** Basic attribution tracking framework in place (even if data limited)

---

## Notes & Considerations

### X API Tier Limitations
- **Free Tier:** Limited to recent tweets, basic metrics only
- **Basic Tier ($100/mo):** Full metrics, 10k tweets/month
- **Pro Tier ($5k/mo):** Full access, webhooks

**Implementation Strategy:** Start with Free tier capabilities, document upgrade path for Basic tier features.

### Content Pillar Classification
Initial heuristic classification:
- **Announcement:** Contains "announce", "release", "new"
- **Tutorial:** Contains "how to", "guide", "tutorial"
- **Community:** Contains @mentions, "welcome", "shoutout"
- **Question:** Ends with "?"
- **Share:** Contains links, "check this out"

### Attribution Challenges
X doesn't provide native link click tracking. Workarounds:
- Use UTM parameters on links shared in tweets
- Track unique coupon codes
- Correlate spikes in metrics with tweet timing
- Manual tracking for "discovered OpenClaw owner" mentions

---

## Gate Classification

| Transition | Depth | Reason |
|-----------|-------|--------|
| Phase 0 → 1 | STANDARD | DB schema consumed by analytics engine |
| Phase 1 → 2 | LIGHT | Code → independent frontend |
| Phase 1 → 3 | LIGHT | Code → independent cron setup |
| Phase 2 → 4 | STANDARD | Frontend consumed by integration test |
| Phase 3 → 4 | STANDARD | Cron consumed by integration test |
| Phase 4 → 5 | NONE | Testing → documentation, independent |
