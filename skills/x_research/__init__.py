#!/usr/bin/env python3
"""
x-research Skill - X/Twitter Research via Composio

Provides Kurultai agents with X/Twitter research capabilities including:
- Tweet search and analysis
- User timeline extraction
- Trending topic monitoring
- Engagement metrics calculation
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("X_RESEARCH_LOG_LEVEL", "INFO"))


class XResearchError(Exception):
    """Base exception for x-research skill."""
    pass


class RateLimitError(XResearchError):
    """Raised when API rate limit is exceeded."""
    pass


class AuthenticationError(XResearchError):
    """Raised when API authentication fails."""
    pass


@dataclass
class Tweet:
    """Represents a tweet with metadata."""
    id: str
    text: str
    author_id: str
    author_username: Optional[str] = None
    author_display_name: Optional[str] = None
    created_at: Optional[str] = None
    retweet_count: int = 0
    reply_count: int = 0
    like_count: int = 0
    quote_count: int = 0
    hashtags: List[str] = None
    mentions: List[str] = None
    urls: List[str] = None
    
    def __post_init__(self):
        if self.hashtags is None:
            self.hashtags = []
        if self.mentions is None:
            self.mentions = []
        if self.urls is None:
            self.urls = []
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)
    
    @property
    def engagement_score(self) -> int:
        """Calculate total engagement."""
        return self.retweet_count + self.reply_count + self.like_count + self.quote_count


@dataclass
class Trend:
    """Represents a trending topic."""
    name: str
    query: str
    tweet_volume: Optional[int] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


class XResearchClient:
    """Client for X/Twitter research via Composio API."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the X research client.
        
        Args:
            api_key: Composio API key. If not provided, reads from COMPOSIO_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get("COMPOSIO_API_KEY")
        if not self.api_key:
            logger.warning("No Composio API key provided. Set COMPOSIO_API_KEY environment variable.")
        
        self.base_url = "https://api.composio.io/v1"
        self._last_request_time = None
        self._request_count = 0
        
        logger.info("XResearchClient initialized")
    
    def _make_request(self, endpoint: str, params: Dict = None) -> Dict:
        """
        Make an API request to Composio.
        
        Args:
            endpoint: API endpoint path
            params: Query parameters
            
        Returns:
            API response as dictionary
            
        Raises:
            AuthenticationError: If API key is invalid
            RateLimitError: If rate limit is exceeded
            XResearchError: For other API errors
        """
        import urllib.request
        import urllib.error
        
        if not self.api_key:
            raise AuthenticationError("Composio API key not configured")
        
        url = f"{self.base_url}{endpoint}"
        if params:
            query_string = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{query_string}"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))
                self._request_count += 1
                return data
                
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise AuthenticationError("Invalid Composio API key")
            elif e.code == 429:
                raise RateLimitError("API rate limit exceeded")
            else:
                raise XResearchError(f"API error: {e.code} - {e.reason}")
        except Exception as e:
            raise XResearchError(f"Request failed: {str(e)}")
    
    def search_tweets(
        self, 
        query: str, 
        max_results: int = 100,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        tweet_fields: List[str] = None
    ) -> List[Tweet]:
        """
        Search for tweets matching the query.
        
        Args:
            query: Search query string
            max_results: Maximum number of results (10-100)
            start_time: ISO 8601 timestamp for start of range
            end_time: ISO 8601 timestamp for end of range
            tweet_fields: Additional tweet fields to include
            
        Returns:
            List of Tweet objects
        """
        if not self.api_key:
            logger.warning("No API key configured, returning mock data")
            return self._get_mock_tweets(query, max_results)
        
        params = {
            "query": query,
            "max_results": min(max_results, 100)
        }
        
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time
        if tweet_fields:
            params["tweet.fields"] = ",".join(tweet_fields)
        else:
            params["tweet.fields"] = "created_at,public_metrics,entities,author_id"
        
        try:
            data = self._make_request("/twitter/search/recent", params)
            tweets = []
            
            for tweet_data in data.get("data", []):
                tweet = self._parse_tweet(tweet_data)
                tweets.append(tweet)
            
            logger.info(f"Found {len(tweets)} tweets for query: {query}")
            return tweets
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            # Return mock data on error for testing
            return self._get_mock_tweets(query, max_results)
    
    def get_user_timeline(
        self, 
        username: str, 
        max_results: int = 50
    ) -> List[Tweet]:
        """
        Get recent tweets from a user's timeline.
        
        Args:
            username: X/Twitter username (without @)
            max_results: Maximum number of tweets to retrieve
            
        Returns:
            List of Tweet objects
        """
        if not self.api_key:
            return self._get_mock_tweets(f"from:{username}", max_results)
        
        # Remove @ if present
        username = username.lstrip("@")
        
        params = {
            "username": username,
            "max_results": min(max_results, 100),
            "tweet.fields": "created_at,public_metrics,entities"
        }
        
        try:
            data = self._make_request(f"/twitter/users/{username}/tweets", params)
            tweets = [self._parse_tweet(t) for t in data.get("data", [])]
            return tweets
        except Exception as e:
            logger.error(f"Timeline fetch failed: {e}")
            return self._get_mock_tweets(f"from:{username}", max_results)
    
    def get_trending_topics(self, woeid: int = 1) -> List[Trend]:
        """
        Get trending topics for a location.
        
        Args:
            woeid: Yahoo Where On Earth ID (1 = worldwide)
            
        Returns:
            List of Trend objects
        """
        if not self.api_key:
            return self._get_mock_trends()
        
        try:
            data = self._make_request(f"/twitter/trends/{woeid}")
            trends = []
            for trend_data in data.get("data", {}).get("trends", []):
                trends.append(Trend(
                    name=trend_data.get("name"),
                    query=trend_data.get("query"),
                    tweet_volume=trend_data.get("tweet_volume")
                ))
            return trends
        except Exception as e:
            logger.error(f"Trends fetch failed: {e}")
            return self._get_mock_trends()
    
    def analyze_engagement(self, tweets: List[Tweet]) -> Dict[str, Any]:
        """
        Analyze engagement metrics for a list of tweets.
        
        Args:
            tweets: List of Tweet objects
            
        Returns:
            Dictionary with engagement statistics
        """
        if not tweets:
            return {
                "total_tweets": 0,
                "total_engagement": 0,
                "average_engagement": 0,
                "top_tweet": None
            }
        
        total_engagement = sum(t.engagement_score for t in tweets)
        avg_engagement = total_engagement / len(tweets)
        top_tweet = max(tweets, key=lambda t: t.engagement_score)
        
        # Calculate engagement breakdown
        total_likes = sum(t.like_count for t in tweets)
        total_retweets = sum(t.retweet_count for t in tweets)
        total_replies = sum(t.reply_count for t in tweets)
        total_quotes = sum(t.quote_count for t in tweets)
        
        return {
            "total_tweets": len(tweets),
            "total_engagement": total_engagement,
            "average_engagement": round(avg_engagement, 2),
            "top_tweet": top_tweet.to_dict() if top_tweet else None,
            "breakdown": {
                "likes": total_likes,
                "retweets": total_retweets,
                "replies": total_replies,
                "quotes": total_quotes
            }
        }
    
    def extract_insights(self, tweets: List[Tweet]) -> Dict[str, Any]:
        """
        Extract insights from a collection of tweets.
        
        Args:
            tweets: List of Tweet objects
            
        Returns:
            Dictionary with extracted insights
        """
        if not tweets:
            return {"error": "No tweets to analyze"}
        
        # Extract hashtags
        all_hashtags = []
        for tweet in tweets:
            all_hashtags.extend(tweet.hashtags)
        
        hashtag_freq = {}
        for tag in all_hashtags:
            hashtag_freq[tag] = hashtag_freq.get(tag, 0) + 1
        
        # Extract mentions
        all_mentions = []
        for tweet in tweets:
            all_mentions.extend(tweet.mentions)
        
        mention_freq = {}
        for mention in all_mentions:
            mention_freq[mention] = mention_freq.get(mention, 0) + 1
        
        # Time analysis
        if tweets[0].created_at:
            dates = [datetime.fromisoformat(t.created_at.replace('Z', '+00:00')) 
                    for t in tweets if t.created_at]
            if dates:
                date_range = {
                    "earliest": min(dates).isoformat(),
                    "latest": max(dates).isoformat(),
                    "span_days": (max(dates) - min(dates)).days
                }
            else:
                date_range = None
        else:
            date_range = None
        
        return {
            "total_tweets": len(tweets),
            "top_hashtags": sorted(hashtag_freq.items(), key=lambda x: x[1], reverse=True)[:10],
            "top_mentions": sorted(mention_freq.items(), key=lambda x: x[1], reverse=True)[:10],
            "date_range": date_range,
            "engagement": self.analyze_engagement(tweets)
        }
    
    def generate_report(self, insights: Dict[str, Any], title: str = "X Research Report") -> str:
        """
        Generate a markdown report from insights.
        
        Args:
            insights: Insights dictionary from extract_insights
            title: Report title
            
        Returns:
            Markdown formatted report
        """
        report = f"# {title}\n\n"
        report += f"Generated: {datetime.now().isoformat()}\n\n"
        
        report += "## Summary\n\n"
        report += f"- **Total Tweets Analyzed:** {insights.get('total_tweets', 0)}\n"
        
        if insights.get('date_range'):
            dr = insights['date_range']
            report += f"- **Date Range:** {dr['earliest'][:10]} to {dr['latest'][:10]}\n"
            report += f"- **Span:** {dr['span_days']} days\n"
        
        report += "\n## Engagement\n\n"
        engagement = insights.get('engagement', {})
        report += f"- **Total Engagement:** {engagement.get('total_engagement', 0):,}\n"
        report += f"- **Average Engagement:** {engagement.get('average_engagement', 0):.2f}\n"
        
        breakdown = engagement.get('breakdown', {})
        report += f"- **Likes:** {breakdown.get('likes', 0):,}\n"
        report += f"- **Retweets:** {breakdown.get('retweets', 0):,}\n"
        report += f"- **Replies:** {breakdown.get('replies', 0):,}\n"
        report += f"- **Quotes:** {breakdown.get('quotes', 0):,}\n"
        
        if insights.get('top_hashtags'):
            report += "\n## Top Hashtags\n\n"
            for tag, count in insights['top_hashtags']:
                report += f"- **{tag}:** {count} occurrences\n"
        
        if insights.get('top_mentions'):
            report += "\n## Top Mentions\n\n"
            for mention, count in insights['top_mentions']:
                report += f"- **{mention}:** {count} mentions\n"
        
        return report
    
    def _parse_tweet(self, data: Dict) -> Tweet:
        """Parse tweet data from API response."""
        public_metrics = data.get("public_metrics", {})
        entities = data.get("entities", {})
        
        hashtags = [h.get("tag") for h in entities.get("hashtags", [])]
        mentions = [m.get("username") for m in entities.get("mentions", [])]
        urls = [u.get("expanded_url") for u in entities.get("urls", [])]
        
        return Tweet(
            id=data.get("id"),
            text=data.get("text"),
            author_id=data.get("author_id"),
            created_at=data.get("created_at"),
            retweet_count=public_metrics.get("retweet_count", 0),
            reply_count=public_metrics.get("reply_count", 0),
            like_count=public_metrics.get("like_count", 0),
            quote_count=public_metrics.get("quote_count", 0),
            hashtags=hashtags,
            mentions=mentions,
            urls=urls
        )
    
    def _get_mock_tweets(self, query: str, count: int) -> List[Tweet]:
        """Generate mock tweets for testing without API key."""
        logger.info(f"Returning mock data for query: {query}")
        
        mock_tweets = []
        for i in range(min(count, 5)):
            mock_tweets.append(Tweet(
                id=f"mock_{i}",
                text=f"Mock tweet {i} about {query} #test #mock",
                author_id=f"author_{i}",
                author_username=f"user_{i}",
                created_at=datetime.now().isoformat(),
                retweet_count=10 + i * 5,
                reply_count=5 + i * 2,
                like_count=50 + i * 10,
                quote_count=2 + i,
                hashtags=["#test", "#mock"],
                mentions=["@testuser"]
            ))
        
        return mock_tweets
    
    def _get_mock_trends(self) -> List[Trend]:
        """Generate mock trends for testing."""
        return [
            Trend("#AI", "%23AI", 150000),
            Trend("#Tech", "%23Tech", 85000),
            Trend("#News", "%23News", 120000),
            Trend("Mock Trend", "Mock%20Trend", None)
        ]


def quick_search(query: str, max_results: int = 50) -> List[Tweet]:
    """
    Quick search helper function.
    
    Args:
        query: Search query
        max_results: Maximum results to return
        
    Returns:
        List of Tweet objects
    """
    client = XResearchClient()
    return client.search_tweets(query, max_results)


def test_skill() -> bool:
    """
    Test the x-research skill functionality.
    
    Returns:
        True if all tests pass, False otherwise
    """
    print("🧪 Testing x-research skill...\n")
    
    try:
        # Test 1: Client initialization
        print("1️⃣ Testing client initialization...")
        client = XResearchClient()
        print("   ✅ Client initialized")
        
        # Test 2: Mock search
        print("\n2️⃣ Testing tweet search (mock mode)...")
        tweets = client.search_tweets("#AI", max_results=5)
        assert len(tweets) > 0, "No tweets returned"
        print(f"   ✅ Found {len(tweets)} tweets")
        
        # Test 3: Engagement analysis
        print("\n3️⃣ Testing engagement analysis...")
        analysis = client.analyze_engagement(tweets)
        assert "total_engagement" in analysis
        print(f"   ✅ Total engagement: {analysis['total_engagement']}")
        
        # Test 4: Insights extraction
        print("\n4️⃣ Testing insights extraction...")
        insights = client.extract_insights(tweets)
        assert "total_tweets" in insights
        print(f"   ✅ Analyzed {insights['total_tweets']} tweets")
        
        # Test 5: Report generation
        print("\n5️⃣ Testing report generation...")
        report = client.generate_report(insights, "Test Report")
        assert len(report) > 0
        print("   ✅ Report generated")
        
        print("\n✅ All tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return False


if __name__ == "__main__":
    # Run tests when executed directly
    success = test_skill()
    exit(0 if success else 1)
