import requests
import feedparser
from typing import Dict, Optional, List
from config import PARSE_API_URL, logger, RSS_FEEDS

def fetch_latest_articles(limit: int = 5) -> List[Dict[str, str]]:
    """Fetches the latest articles from configured RSS feeds."""
    articles = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:limit]:
                articles.append({
                    "title": entry.title,
                    "link": entry.link,
                    "summary": entry.get('summary', '')
                })
        except Exception as e:
            logger.error(f"Error fetching feed {feed_url}: {e}")
    return articles

def get_parse_analysis(article_url: str) -> Optional[Dict]:
    """Sends an article URL to Parse Platform for analysis."""
    logger.info(f"Fetching Parse analysis for: {article_url}")
    try:
        response = requests.post(
            PARSE_API_URL,
            json={"url": article_url},
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching analysis from Parse API: {e}")
        return None
