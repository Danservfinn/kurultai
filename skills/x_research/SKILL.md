# x-research Skill

X/Twitter research capability via Composio API integration. Enables agents to search, analyze, and extract insights from X (Twitter) content.

## Overview

The x-research skill provides Kurultai agents with the ability to:
- Search X/Twitter for specific topics, hashtags, or accounts
- Extract tweet content and metadata
- Analyze engagement patterns
- Track trending topics
- Monitor account activity
- Generate research reports from X data

## Prerequisites

1. **Composio API Key**: Required for accessing X/Twitter APIs
   - Get one at: https://composio.ai
   - Free tier: 20,000 API calls/month
   - Set as environment variable: `COMPOSIO_API_KEY`

2. **Bun Runtime** (optional): For TypeScript-based research scripts
   - Install: `curl -fsSL https://bun.sh/install | bash`

## Installation

```bash
# Install Composio dependencies
npm install -g composio-core

# Or with Bun
bun install composio-core
```

## Environment Variables

```bash
export COMPOSIO_API_KEY="your-api-key-here"
export X_RESEARCH_LOG_LEVEL="INFO"  # DEBUG, INFO, WARN, ERROR
```

## Usage

### Basic Search

```python
from skills.x_research import XResearchClient

# Initialize client
client = XResearchClient()

# Search for tweets
results = client.search_tweets(
    query="#AI OR #MachineLearning",
    max_results=100,
    start_time="2025-01-01T00:00:00Z"
)
```

### Account Analysis

```python
# Get user timeline
timeline = client.get_user_timeline(
    username="elonmusk",
    max_results=50
)

# Analyze engagement
analysis = client.analyze_engagement(timeline)
```

### Trending Topics

```python
# Get trending topics by location
trends = client.get_trending_topics(
    woeid=1  # Worldwide
)
```

## Research Patterns

### Pattern 1: Sentiment Analysis
```python
from skills.x_research.patterns import sentiment_analysis

results = sentiment_analysis(
    query="your brand name",
    timeframe="7d"
)
```

### Pattern 2: Competitor Monitoring
```python
from skills.x_research.patterns import competitor_monitor

monitor = competitor_monitor(
    competitors=["@competitor1", "@competitor2"],
    keywords=["product", "launch", "update"]
)
```

### Pattern 3: Hashtag Research
```python
from skills.x_research.patterns import hashtag_research

research = hashtag_research(
    hashtags=[#AI, #MachineLearning],
    include_related=True
)
```

## Integration with Kurultai Agents

### Möngke (Research)
```python
# Deep research on emerging topics
def research_topic(topic: str):
    client = XResearchClient()
    
    # Multi-dimensional search
    tweets = client.search_tweets(
        query=f"{topic} -filter:retweets",
        max_results=500
    )
    
    # Extract insights
    insights = client.extract_insights(tweets)
    
    # Generate report
    return client.generate_report(insights)
```

### Danny (Testing/Integration)
```python
# Verify API connectivity and test features
def test_x_research():
    client = XResearchClient()
    
    # Test basic search
    test_results = client.search_tweets(
        query="test",
        max_results=10
    )
    
    assert len(test_results) > 0, "Search failed"
    print("✅ x-research skill operational")
```

## API Rate Limits

| Endpoint | Free Tier | Paid Tier |
|----------|-----------|-----------|
| Search | 450/15min | 3000/15min |
| User Timeline | 1500/15min | 1500/15min |
| Trends | 75/15min | 75/15min |

## Error Handling

```python
from skills.x_research.exceptions import (
    XResearchError,
    RateLimitError,
    AuthenticationError
)

try:
    results = client.search_tweets(query="AI")
except RateLimitError:
    # Wait and retry
    time.sleep(900)
    results = client.search_tweets(query="AI")
except AuthenticationError:
    # Check API key
    logger.error("Invalid Composio API key")
```

## Output Format

### Tweet Object
```json
{
  "id": "1234567890",
  "text": "Tweet content...",
  "author": {
    "id": "987654321",
    "username": "username",
    "display_name": "Display Name"
  },
  "created_at": "2025-01-15T10:30:00Z",
  "public_metrics": {
    "retweet_count": 42,
    "reply_count": 15,
    "like_count": 128,
    "quote_count": 7
  },
  "entities": {
    "hashtags": ["#AI"],
    "mentions": ["@user"],
    "urls": []
  }
}
```

## Testing

```bash
# Run skill tests
python -m pytest skills/x_research/tests/

# Test with mock data
python skills/x_research/test_skill.py --mock

# Test with live API (requires API key)
python skills/x_research/test_skill.py --live
```

## Troubleshooting

### Issue: "API Key Invalid"
- Verify `COMPOSIO_API_KEY` is set correctly
- Check key hasn't expired
- Ensure key has X/Twitter permissions

### Issue: "Rate Limit Exceeded"
- Implement exponential backoff
- Use caching for repeated queries
- Consider upgrading Composio plan

### Issue: "No Results Found"
- Check query syntax
- Verify date range is valid
- Try broader search terms

## Roadmap

- [ ] Advanced sentiment analysis
- [ ] Image content analysis
- [ ] Thread extraction
- [ ] Real-time streaming
- [ ] Multi-language support

## References

- Composio Docs: https://docs.composio.ai
- X API Docs: https://developer.twitter.com/en/docs
- Kurultai Skills Guide: ../docs/SKILLS.md
