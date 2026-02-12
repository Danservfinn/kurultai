#!/usr/bin/env python3
"""
Research patterns for x-research skill.

Common research workflows and analysis patterns for X/Twitter data.
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from skills.x_research import XResearchClient, Tweet


class ResearchPattern:
    """Base class for research patterns."""
    
    def __init__(self, client: XResearchClient = None):
        self.client = client or XResearchClient()
    
    def execute(self, **kwargs) -> Dict:
        """Execute the research pattern."""
        raise NotImplementedError


class SentimentAnalysisPattern(ResearchPattern):
    """
    Analyze sentiment around a topic or brand.
    
    Example:
        pattern = SentimentAnalysisPattern()
        results = pattern.execute(
            query="your brand name",
            timeframe="7d"
        )
    """
    
    def execute(self, query: str, timeframe: str = "7d") -> Dict:
        """
        Execute sentiment analysis.
        
        Args:
            query: Search query
            timeframe: Time window (1d, 7d, 30d)
            
        Returns:
            Analysis results with sentiment breakdown
        """
        # Calculate date range
        days = int(timeframe[:-1])
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        # Search tweets
        tweets = self.client.search_tweets(
            query=query,
            max_results=100,
            start_time=start_time.isoformat() + "Z",
            end_time=end_time.isoformat() + "Z"
        )
        
        # Simple keyword-based sentiment (placeholder for ML model)
        positive_words = ["good", "great", "excellent", "love", "amazing", "best", "awesome"]
        negative_words = ["bad", "terrible", "hate", "awful", "worst", "sucks", "horrible"]
        
        positive = 0
        negative = 0
        neutral = 0
        
        for tweet in tweets:
            text_lower = tweet.text.lower()
            pos_count = sum(1 for w in positive_words if w in text_lower)
            neg_count = sum(1 for w in negative_words if w in text_lower)
            
            if pos_count > neg_count:
                positive += 1
            elif neg_count > pos_count:
                negative += 1
            else:
                neutral += 1
        
        total = len(tweets)
        
        return {
            "query": query,
            "timeframe": timeframe,
            "total_tweets": total,
            "sentiment_breakdown": {
                "positive": {"count": positive, "percentage": round(positive/total*100, 2) if total else 0},
                "negative": {"count": negative, "percentage": round(negative/total*100, 2) if total else 0},
                "neutral": {"count": neutral, "percentage": round(neutral/total*100, 2) if total else 0}
            },
            "engagement": self.client.analyze_engagement(tweets)
        }


class CompetitorMonitorPattern(ResearchPattern):
    """
    Monitor competitor activity on X.
    
    Example:
        pattern = CompetitorMonitorPattern()
        results = pattern.execute(
            competitors=["@competitor1", "@competitor2"],
            keywords=["product", "launch"]
        )
    """
    
    def execute(
        self, 
        competitors: List[str], 
        keywords: List[str] = None,
        max_results_per_account: int = 50
    ) -> Dict:
        """
        Monitor competitor accounts.
        
        Args:
            competitors: List of competitor usernames
            keywords: Optional keywords to filter for
            max_results_per_account: Max tweets per account
            
        Returns:
            Competitor activity analysis
        """
        results = {
            "competitors": {},
            "summary": {
                "total_tweets": 0,
                "total_engagement": 0
            }
        }
        
        for competitor in competitors:
            username = competitor.lstrip("@")
            
            # Get timeline
            tweets = self.client.get_user_timeline(username, max_results_per_account)
            
            # Filter by keywords if specified
            if keywords:
                tweets = [t for t in tweets 
                         if any(kw.lower() in t.text.lower() for kw in keywords)]
            
            # Analyze
            engagement = self.client.analyze_engagement(tweets)
            insights = self.client.extract_insights(tweets)
            
            results["competitors"][username] = {
                "tweet_count": len(tweets),
                "engagement": engagement,
                "insights": insights
            }
            
            results["summary"]["total_tweets"] += len(tweets)
            results["summary"]["total_engagement"] += engagement["total_engagement"]
        
        return results


class HashtagResearchPattern(ResearchPattern):
    """
    Research hashtag usage and trends.
    
    Example:
        pattern = HashtagResearchPattern()
        results = pattern.execute(
            hashtags=["#AI", "#MachineLearning"],
            include_related=True
        )
    """
    
    def execute(
        self, 
        hashtags: List[str], 
        include_related: bool = True,
        max_results: int = 100
    ) -> Dict:
        """
        Research hashtags.
        
        Args:
            hashtags: List of hashtags to research
            include_related: Whether to find related hashtags
            max_results: Max tweets to analyze
            
        Returns:
            Hashtag research results
        """
        # Clean hashtags
        clean_tags = [tag if tag.startswith("#") else f"#{tag}" for tag in hashtags]
        
        # Build query
        query = " OR ".join(clean_tags)
        
        # Search
        tweets = self.client.search_tweets(query, max_results=max_results)
        
        # Extract insights
        insights = self.client.extract_insights(tweets)
        
        # Find related hashtags if requested
        related_hashtags = {}
        if include_related and insights.get("top_hashtags"):
            for tag, count in insights["top_hashtags"]:
                if tag not in [t.lower() for t in clean_tags]:
                    related_hashtags[tag] = count
        
        return {
            "target_hashtags": clean_tags,
            "total_tweets": len(tweets),
            "tweet_sample": [t.text for t in tweets[:5]],
            "insights": insights,
            "related_hashtags": related_hashtags
        }


class InfluencerDiscoveryPattern(ResearchPattern):
    """
    Discover influencers in a topic area.
    
    Example:
        pattern = InfluencerDiscoveryPattern()
        results = pattern.execute(
            topic="#AI",
            min_followers=10000
        )
    """
    
    def execute(
        self, 
        topic: str, 
        min_engagement: int = 100,
        max_results: int = 200
    ) -> Dict:
        """
        Discover influencers.
        
        Args:
            topic: Topic to search
            min_engagement: Minimum engagement score threshold
            max_results: Max tweets to analyze
            
        Returns:
            Influencer discovery results
        """
        # Search for tweets
        tweets = self.client.search_tweets(topic, max_results=max_results)
        
        # Group by author and calculate engagement
        authors = {}
        for tweet in tweets:
            author = tweet.author_username or tweet.author_id
            if author not in authors:
                authors[author] = {
                    "tweets": [],
                    "total_engagement": 0,
                    "tweet_count": 0
                }
            
            authors[author]["tweets"].append(tweet)
            authors[author]["total_engagement"] += tweet.engagement_score
            authors[author]["tweet_count"] += 1
        
        # Filter by engagement threshold
        influencers = {
            author: data for author, data in authors.items()
            if data["total_engagement"] >= min_engagement
        }
        
        # Sort by engagement
        sorted_influencers = sorted(
            influencers.items(),
            key=lambda x: x[1]["total_engagement"],
            reverse=True
        )
        
        return {
            "topic": topic,
            "min_engagement_threshold": min_engagement,
            "total_authors": len(authors),
            "influencers_found": len(influencers),
            "top_influencers": [
                {
                    "username": author,
                    "tweet_count": data["tweet_count"],
                    "total_engagement": data["total_engagement"],
                    "avg_engagement": round(data["total_engagement"] / data["tweet_count"], 2)
                }
                for author, data in sorted_influencers[:10]
            ]
        }


# Convenience functions for quick use

def sentiment_analysis(query: str, timeframe: str = "7d") -> Dict:
    """Quick sentiment analysis."""
    pattern = SentimentAnalysisPattern()
    return pattern.execute(query, timeframe)


def competitor_monitor(
    competitors: List[str], 
    keywords: List[str] = None
) -> Dict:
    """Quick competitor monitoring."""
    pattern = CompetitorMonitorPattern()
    return pattern.execute(competitors, keywords)


def hashtag_research(
    hashtags: List[str], 
    include_related: bool = True
) -> Dict:
    """Quick hashtag research."""
    pattern = HashtagResearchPattern()
    return pattern.execute(hashtags, include_related)


def discover_influencers(topic: str, min_engagement: int = 100) -> Dict:
    """Quick influencer discovery."""
    pattern = InfluencerDiscoveryPattern()
    return pattern.execute(topic, min_engagement)
