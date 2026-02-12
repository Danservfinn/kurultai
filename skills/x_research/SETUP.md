# x-research Skill Setup Documentation

## Overview

The **x-research skill** provides Kurultai agents with X/Twitter research capabilities via the Composio API. This document describes the setup process and integration details.

## Setup Date
**Completed:** 2026-02-12
**Setup Agent:** Kublai (Router Agent)

## Components Created

### 1. Core Module (`skills/x_research/`)
```
skills/x_research/
├── __init__.py          # Main client and functionality
├── SKILL.md             # Comprehensive documentation
├── CLAUDE.md            # Claude Code integration guide
├── patterns.py          # Research patterns library
├── test_skill.py        # Test suite
└── setup.sh             # Setup automation script
```

### 2. Key Features

**XResearchClient Class:**
- `search_tweets()` - Search X content with filters
- `get_user_timeline()` - Retrieve user posts
- `get_trending_topics()` - Get trending hashtags
- `analyze_engagement()` - Calculate engagement metrics
- `extract_insights()` - Extract patterns from data
- `generate_report()` - Generate markdown reports

**Research Patterns:**
- `SentimentAnalysisPattern` - Analyze sentiment around topics
- `CompetitorMonitorPattern` - Monitor competitor activity
- `HashtagResearchPattern` - Research hashtag usage
- `InfluencerDiscoveryPattern` - Discover topic influencers

## Installation Steps

### 1. Directory Structure
```bash
mkdir -p skills/x_research
```

### 2. Dependencies
The skill uses Python standard library only - no external dependencies required for core functionality.

Optional: Composio SDK for enhanced features
```bash
npm install -g composio-core
```

### 3. Environment Configuration
```bash
export COMPOSIO_API_KEY="your-api-key-here"
export X_RESEARCH_LOG_LEVEL="INFO"
```

### 4. Verification
```bash
# Run tests
python3 skills/x_research/test_skill.py --mock

# Test imports
python3 -c "from skills.x_research import XResearchClient; print('OK')"
```

## Integration Points

### Agent Integration

**Möngke (Research Agent):**
```python
from skills.x_research import XResearchClient
from skills.x_research.patterns import sentiment_analysis

client = XResearchClient()
insights = client.extract_insights(tweets)
report = client.generate_report(insights)
```

**Danny (Testing Agent):**
```python
from skills.x_research import test_skill
success = test_skill()  # Validates skill functionality
```

### Task Queue Integration
Tasks can now use x-research:
```json
{
  "task": "Research AI trends on X",
  "skill": "x_research",
  "agent": "Möngke"
}
```

## Testing Results

### Mock Tests (No API Key Required)
- ✅ Client initialization
- ✅ Tweet search (mock data)
- ✅ User timeline fetch
- ✅ Trending topics
- ✅ Engagement analysis
- ✅ Insights extraction
- ✅ Report generation

### Live API Tests (Requires API Key)
Pending: Requires `COMPOSIO_API_KEY` to be configured

## Usage Examples

### Basic Search
```python
from skills.x_research import XResearchClient

client = XResearchClient()
tweets = client.search_tweets("#AI", max_results=50)
```

### Sentiment Analysis
```python
from skills.x_research.patterns import sentiment_analysis

results = sentiment_analysis("OpenAI", timeframe="7d")
print(f"Positive: {results['sentiment_breakdown']['positive']['percentage']}%")
```

### Competitor Monitoring
```python
from skills.x_research.patterns import competitor_monitor

results = competitor_monitor(
    competitors=["@competitor1", "@competitor2"],
    keywords=["product", "launch"]
)
```

### Report Generation
```python
insights = client.extract_insights(tweets)
report = client.generate_report(insights, "AI Research Report")
# Saves to Notion or file
```

## Configuration

### Environment Variables
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| COMPOSIO_API_KEY | No | None | Composio API key for live data |
| X_RESEARCH_LOG_LEVEL | No | INFO | Logging level (DEBUG, INFO, WARN, ERROR) |

### Rate Limits
With Composio API key:
- Search: 450 requests/15min (free tier)
- User Timeline: 1500 requests/15min
- Trends: 75 requests/15min

Without API key:
- Falls back to mock data for testing

## Next Steps

1. **API Key Configuration**
   - Sign up at https://composio.ai
   - Set `COMPOSIO_API_KEY` environment variable
   - Run live tests

2. **Agent Training**
   - Update Möngke agent to use x-research patterns
   - Add research tasks to task queue
   - Document research workflows

3. **Integration Expansion**
   - Connect to Notion for report storage
   - Add scheduled research tasks
   - Build research dashboard

## Maintenance

### Regular Tasks
- Monitor API usage and rate limits
- Update patterns based on research needs
- Expand test coverage

### Troubleshooting
**Issue:** Import errors
- Solution: Ensure `skills/x_research/` is in Python path

**Issue:** No live data
- Solution: Check `COMPOSIO_API_KEY` is set correctly

**Issue:** Rate limit errors
- Solution: Implement backoff or upgrade Composio plan

## References

- **Skill Documentation:** `skills/x_research/SKILL.md`
- **Composio API:** https://docs.composio.ai
- **X API:** https://developer.twitter.com/en/docs
- **Kurultai Agents:** See `IDENTITY.md` for agent roles

---

**Setup Status:** ✅ Complete
**Test Status:** ✅ Mock tests passing
**API Status:** ⏳ Awaiting API key for live testing
