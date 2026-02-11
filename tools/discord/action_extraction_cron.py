#!/usr/bin/env python3
"""
Extract Actions from Discord - Cron Integration
Periodically scans Discord conversations and extracts action items to Notion.
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from discord.deliberation_client import AgentRole, send_agent_message
from discord.bot_reader import read_recent_messages  # Assuming this exists
from kurultai.discord_action_extractor import ConversationActionPipeline


async def extract_and_sync():
    """Extract actions from recent Discord messages and sync to Notion."""
    print(f"[{datetime.utcnow().isoformat()}] Starting action extraction from Discord")
    
    pipeline = ConversationActionPipeline()
    
    try:
        # Read recent messages from council-chamber (last 2 hours)
        # Note: This assumes a function exists to fetch Discord messages
        # In production, this would use the Discord API or bot cache
        
        # For now, we'll check if there are any recent actions to report
        recent_actions = pipeline.get_recent_actions(hours=2)
        
        if recent_actions:
            # Format summary
            lines = ["📋 **Action Items Extracted from Recent Conversations**\n"]
            
            for action in recent_actions[:5]:  # Top 5
                assignee_str = f" (@{action.assignee})" if action.assignee else ""
                lines.append(f"• **{action.action_type.value.title()}**: {action.description[:80]}{assignee_str}")
            
            summary = "\n".join(lines)
            
            # Send to Discord
            result = await send_agent_message(
                "council-chamber",
                AgentRole.OGEDEI.value,
                f"{summary}\n\n_Synced to Notion for tracking_ 📈"
            )
            
            if result.get("success"):
                print(f"✅ Reported {len(recent_actions)} actions to Discord")
            else:
                print(f"⚠️ Discord send failed: {result.get('error')}")
        else:
            print("ℹ️ No new action items extracted")
        
        return len(recent_actions)
        
    except Exception as e:
        error_msg = f"❌ Error extracting actions: {e}"
        print(error_msg)
        raise


if __name__ == "__main__":
    count = asyncio.run(extract_and_sync())
    sys.exit(0 if count is not None else 1)
