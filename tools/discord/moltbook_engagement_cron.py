#!/usr/bin/env python3
"""
Moltbook Engagement Cron Integration
Runs after OSA posts to track engagement metrics.
"""

import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kurultai.moltbook_engagement import MoltbookEngagementTracker
from discord.deliberation_client import send_agent_message, AgentRole


async def track_and_report():
    """Track engagement and report to Discord."""
    print(f"[{datetime.utcnow().isoformat()}] Starting moltbook engagement tracking")
    
    tracker = MoltbookEngagementTracker()
    
    try:
        # Generate report
        report = await tracker.generate_report()
        
        # Format summary for Discord
        summary = tracker.format_report_summary(report)
        
        # Send to Discord council-chamber
        print(f"📊 Engagement trend: {report.trend_direction}")
        print(f"📈 Total posts: {report.total_posts}")
        
        # Only send if there's notable activity
        if report.aggregate_metrics['total_upvotes'] > 0 or report.posts_last_24h > 0:
            result = await send_agent_message(
                "council-chamber",
                AgentRole.OGEDEI.value,
                f"📊 **Moltbook Engagement Update**\n\n{summary}\n\n— Ögedei 📈"
            )
            
            if result.get("success"):
                print("✅ Report sent to Discord")
            else:
                print(f"⚠️ Discord send failed: {result.get('error')}")
        else:
            print("ℹ️ No notable activity to report")
        
        return report
        
    except Exception as e:
        error_msg = f"❌ Error tracking engagement: {e}"
        print(error_msg)
        
        # Send error to Discord
        await send_agent_message(
            "council-chamber",
            AgentRole.OGEDEI.value,
            f"⚠️ **Engagement Tracking Error**\n\n{error_msg}\n\n— Ögedei 📈"
        )
        raise


if __name__ == "__main__":
    result = asyncio.run(track_and_report())
    sys.exit(0 if result else 1)
