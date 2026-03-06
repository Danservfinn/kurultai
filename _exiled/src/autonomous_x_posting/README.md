# Autonomous X Posting System for Kublai

Autonomous Twitter/X posting system that:
1. Fetches live news articles from RSS feeds
2. Sends articles to Parse Platform for AI analysis
3. Generates tweet threads from Parse outputs
4. Posts threads to X autonomously

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure `.x_api_credentials` exists with X API credentials

3. Run the scheduler:
```bash
python scheduler.py
```

## Schedule

- **Article Analysis**: 3x daily (9 AM, 2 PM, 7 PM EST)
- **Capabilities Promo**: Every 2 days at 12 PM EST

## Files

- `config.py` - Configuration and credentials
- `fetch_parse_analysis.py` - RSS feed fetching + Parse API
- `generate_thread.py` - Thread generation from Parse outputs
- `post_to_x.py` - X API posting with OAuth 1.0a
- `scheduler.py` - APScheduler for autonomous scheduling
