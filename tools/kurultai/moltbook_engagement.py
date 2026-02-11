"""
Moltbook Engagement Tracker
Queries moltbook API to track post performance and engagement metrics.
"""

import os
import sys
import json
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

# API Configuration
MOLTBOOK_API_BASE = "https://www.moltbook.com/api/v1"  # Must use www subdomain
MOLTBOOK_POSTS_ENDPOINT = f"{MOLTBOOK_API_BASE}/posts"

# Memory storage
MEMORY_DIR = Path("/data/workspace/souls/main/memory/moltbook")
MEMORY_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class PostMetrics:
    """Engagement metrics for a single post."""
    post_id: str
    title: str
    content_preview: str
    upvotes: int
    downvotes: int
    comment_count: int
    created_at: str
    submolt: str
    author: str
    fetched_at: datetime
    
    @property
    def engagement_score(self) -> float:
        """Calculate composite engagement score."""
        # Weighted: upvotes (+1), comments (+2), downvotes (-0.5)
        return self.upvotes + (self.comment_count * 2) - (self.downvotes * 0.5)
    
    @property
    def sentiment_ratio(self) -> float:
        """Ratio of positive to total reactions."""
        total = self.upvotes + self.downvotes
        if total == 0:
            return 1.0
        return self.upvotes / total


@dataclass
class EngagementReport:
    """Full engagement report with analytics."""
    timestamp: str
    total_posts: int
    posts_last_24h: int
    posts_last_7d: int
    top_posts: List[PostMetrics]
    aggregate_metrics: Dict
    trend_direction: str  # "up", "down", "stable"


class MoltbookEngagementTracker:
    """Tracks engagement metrics for OSA posts on moltbook."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("MOLTBOOK_API_KEY")
        self.posts_cache: Dict[str, PostMetrics] = {}
        
    async def fetch_posts(self, limit: int = 50) -> List[PostMetrics]:
        """Fetch recent posts from moltbook API."""
        if not self.api_key:
            raise ValueError("MOLTBOOK_API_KEY not configured")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                MOLTBOOK_POSTS_ENDPOINT,
                headers=headers,
                params={"limit": limit}
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"API error {resp.status}: {error_text}")
                
                data = await resp.json()
                posts = []
                
                for post_data in data.get("posts", []):
                    metrics = PostMetrics(
                        post_id=post_data.get("id", ""),
                        title=post_data.get("title", "")[:100],
                        content_preview=post_data.get("content", "")[:200],
                        upvotes=post_data.get("upvotes", 0),
                        downvotes=post_data.get("downvotes", 0),
                        comment_count=post_data.get("comment_count", 0),
                        created_at=post_data.get("created_at", ""),
                        submolt=post_data.get("submolt", ""),
                        author=post_data.get("author", ""),
                        fetched_at=datetime.utcnow()
                    )
                    posts.append(metrics)
                    self.posts_cache[metrics.post_id] = metrics
                
                return posts
    
    def load_historical_data(self, days: int = 7) -> List[Dict]:
        """Load historical engagement data from memory files."""
        history = []
        for i in range(days):
            date = datetime.utcnow() - timedelta(days=i)
            filepath = MEMORY_DIR / f"engagement_{date.strftime('%Y-%m-%d')}.json"
            if filepath.exists():
                with open(filepath) as f:
                    history.append(json.load(f))
        return history
    
    def save_engagement_data(self, posts: List[PostMetrics]):
        """Save today's engagement data to memory."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        filepath = MEMORY_DIR / f"engagement_{today}.json"
        
        data = {
            "date": today,
            "timestamp": datetime.utcnow().isoformat(),
            "post_count": len(posts),
            "posts": [asdict(p) for p in posts]
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    
    def calculate_trend(self, current: List[PostMetrics]) -> str:
        """Calculate engagement trend vs yesterday."""
        yesterday_data = self.load_historical_data(days=1)
        if not yesterday_data:
            return "stable"
        
        yesterday_posts = yesterday_data[0].get("posts", [])
        if not yesterday_posts:
            return "stable"
        
        # Calculate average engagement scores
        current_avg = sum(p.engagement_score for p in current) / len(current) if current else 0
        yesterday_avg = sum(
            p.get("upvotes", 0) + (p.get("comment_count", 0) * 2) 
            for p in yesterday_posts
        ) / len(yesterday_posts)
        
        if current_avg > yesterday_avg * 1.2:
            return "up"
        elif current_avg < yesterday_avg * 0.8:
            return "down"
        return "stable"
    
    async def generate_report(self) -> EngagementReport:
        """Generate full engagement report."""
        posts = await self.fetch_posts(limit=50)
        self.save_engagement_data(posts)
        
        now = datetime.utcnow()
        day_ago = now - timedelta(hours=24)
        week_ago = now - timedelta(days=7)
        
        posts_last_24h = sum(
            1 for p in posts 
            if datetime.fromisoformat(p.created_at.replace('Z', '+00:00')) > day_ago
        )
        posts_last_7d = sum(
            1 for p in posts 
            if datetime.fromisoformat(p.created_at.replace('Z', '+00:00')) > week_ago
        )
        
        # Sort by engagement score
        top_posts = sorted(posts, key=lambda p: p.engagement_score, reverse=True)[:5]
        
        # Calculate aggregate metrics
        total_upvotes = sum(p.upvotes for p in posts)
        total_downvotes = sum(p.downvotes for p in posts)
        total_comments = sum(p.comment_count for p in posts)
        avg_sentiment = sum(p.sentiment_ratio for p in posts) / len(posts) if posts else 1.0
        
        aggregate = {
            "total_upvotes": total_upvotes,
            "total_downvotes": total_downvotes,
            "total_comments": total_comments,
            "average_sentiment_ratio": round(avg_sentiment, 2),
            "engagement_rate": round((total_upvotes + total_comments) / len(posts), 2) if posts else 0
        }
        
        trend = self.calculate_trend(posts)
        
        return EngagementReport(
            timestamp=now.isoformat(),
            total_posts=len(posts),
            posts_last_24h=posts_last_24h,
            posts_last_7d=posts_last_7d,
            top_posts=top_posts,
            aggregate_metrics=aggregate,
            trend_direction=trend
        )
    
    def format_report_summary(self, report: EngagementReport) -> str:
        """Format report as readable summary."""
        trend_emoji = {"up": "📈", "down": "📉", "stable": "➡️"}
        
        lines = [
            "📊 **Moltbook Engagement Report**",
            f"Generated: {report.timestamp[:19]}",
            "",
            f"**Trend:** {trend_emoji.get(report.trend_direction, '➡️')} {report.trend_direction.upper()}",
            f"**Total Posts:** {report.total_posts}",
            f"**Posts (24h):** {report.posts_last_24h}",
            f"**Posts (7d):** {report.posts_last_7d}",
            "",
            "**Aggregate Metrics:**",
            f"• Upvotes: {report.aggregate_metrics['total_upvotes']}",
            f"• Comments: {report.aggregate_metrics['total_comments']}",
            f"• Avg Sentiment: {report.aggregate_metrics['average_sentiment_ratio']:.0%}",
            f"• Engagement Rate: {report.aggregate_metrics['engagement_rate']:.1f}",
            "",
            "**Top Performing Posts:**",
        ]
        
        for i, post in enumerate(report.top_posts[:3], 1):
            lines.append(f"{i}. {post.title[:50]}... (👍 {post.upvotes}, 💬 {post.comment_count})")
        
        return "\n".join(lines)


async def main():
    """CLI entry point for engagement tracking."""
    tracker = MoltbookEngagementTracker()
    
    try:
        report = await tracker.generate_report()
        print(tracker.format_report_summary(report))
        
        # Save full report
        report_file = MEMORY_DIR / f"report_{datetime.utcnow().strftime('%Y-%m-%d_%H')}.json"
        with open(report_file, 'w') as f:
            json.dump(asdict(report), f, indent=2, default=str)
        
        return report
    except Exception as e:
        print(f"❌ Error generating report: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
