#!/usr/bin/env python3
"""
Parse Slack Bot

A Slack bot that integrates with Parse API to provide article analysis,
truth scoring, and bias-free rewrites directly in Slack workspaces.

Commands:
    /parse score <url>      - Quick truth score (0-100)
    /parse analyze <url>    - Full analysis with breakdown
    /parse rewrite <url>    - Bias-free rewrite
    /parse help             - Show command reference

Environment Variables Required:
    SLACK_BOT_TOKEN         - xoxb- token from Slack app
    SLACK_SIGNING_SECRET    - Signing secret from Slack app
    PARSE_API_KEY           - Parse API key (parse_pk_prod_...)
    PARSE_BASE_URL          - Parse API base URL (optional)

Installation:
    pip install slack-sdk parse-api-client

Usage:
    python app.py
"""

from __future__ import annotations

import asyncio
import os
import logging
from datetime import datetime, timezone
from typing import Optional

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.parse_api_client import ParseClient, ParseAPIError, CredibilityLevel


# ============================================================================
# Configuration
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("parse-slack-bot")

# Parse configuration
PARSE_API_KEY = os.getenv("PARSE_API_KEY")
PARSE_BASE_URL = os.getenv("PARSE_BASE_URL")

# Slack configuration
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
SLACK_APP_LEVEL_TOKEN = os.getenv("SLACK_APP_LEVEL_TOKEN")  # xapp- token for socket mode

# Check required environment variables
if not all([PARSE_API_KEY, SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET]):
    missing = []
    if not PARSE_API_KEY:
        missing.append("PARSE_API_KEY")
    if not SLACK_BOT_TOKEN:
        missing.append("SLACK_BOT_TOKEN")
    if not SLACK_SIGNING_SECRET:
        missing.append("SLACK_SIGNING_SECRET")
    logger.error(f"Missing required environment variables: {', '.join(missing)}")
    sys.exit(1)


# ============================================================================
# Parse Client
# ============================================================================

parse_client = ParseClient(
    api_key=PARSE_API_KEY,
    base_url=PARSE_BASE_URL,
    user_agent="ParseSlackBot/1.0"
)


# ============================================================================
# Slack App
# ============================================================================

app = App(
    token=SLACK_BOT_TOKEN,
    signing_secret=SLACK_SIGNING_SECRET
)


# ============================================================================
# Helper Functions
# ============================================================================

def format_score_block(score: int, url: str, title: str = "") -> dict:
    """Format a truth score result as a Slack block."""
    level = ParseClient.get_credibility_level(score)

    # Color mapping
    colors = {
        CredibilityLevel.VERY_HIGH: "#36a64f",  # green
        CredibilityLevel.HIGH: "#6cc24a",       # light green
        CredibilityLevel.MODERATE: "#eab308",   # yellow
        CredibilityLevel.LOW: "#f97316",        # orange
        CredibilityLevel.VERY_LOW: "#ef4444",   # red
    }
    color = colors.get(level, "#6366f1")

    # Level emoji
    emojis = {
        CredibilityLevel.VERY_HIGH: "🟢",
        CredibilityLevel.HIGH: "🟢",
        CredibilityLevel.MODERATE: "🟡",
        CredibilityLevel.LOW: "🟠",
        CredibilityLevel.VERY_LOW: "🔴",
    }
    emoji = emojis.get(level, "⚪")

    return {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f"*{emoji} Truth Score: {score}/100*\n"
                f"*Credibility:* {level.value.replace('_', ' ').title()}\n"
                f"{title}\n{url}"
            )
        },
        "accessory": {
            "type": "button",
            "text": {
                "type": "plain_text",
                "text": "View Full Analysis"
            },
            "url": f"{PARSE_BASE_URL}/analyze?url={url}",
            "action_id": "view_analysis"
        }
    }


def format_analysis_block(result: dict, url: str) -> list:
    """Format full analysis result as Slack blocks."""
    score = result.get("credibilityScore", result.get("score", 0))
    level = ParseClient.get_credibility_level(score)

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📊 Parse Analysis: {score}/100",
                "emoji": True
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Credibility: *{level.value.replace('_', ' ').title()}*"
                }
            ]
        },
        {"type": "divider"}
    ]

    # Score breakdown if available
    if "scoreBreakdown" in result:
        breakdown = result["scoreBreakdown"]
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Score Breakdown:*\n" + "\n".join(
                    f"• {k.capitalize()}: {v}" for k, v in breakdown.items()
                )
            }
        })
        blocks.append({"type": "divider"})

    # AI Assessment if available
    if "aiAssessment" in result:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*💬 What AI Thinks:*\n{result['aiAssessment']}"
            }
        })
        blocks.append({"type": "divider"})

    # Deception detected if available
    if result.get("deceptionDetected"):
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*⚠️ Deception Detected:*"
            }
        })
        for deception in result["deceptionDetected"][:3]:  # Max 3
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"• _{deception.get('type', 'Unknown')}_\n{deception.get('description', '')[:100]}..."
                }
            })
        blocks.append({"type": "divider"})

    # Action buttons
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "View Full Analysis"
                },
                "url": f"{PARSE_BASE_URL}/analyze?url={url}",
                "action_id": "view_analysis"
            }
        ]
    })

    return blocks


def format_rewrite_block(result: dict, url: str) -> list:
    """Format rewrite result as Slack blocks."""
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "✍️ Bias-Free Rewrite",
                "emoji": True
            }
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{result.get('rewrittenTitle', 'Rewritten Article')}*\n\n{result.get('rewrittenContent', '')[:500]}..."
            }
        },
        {"type": "divider"},
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Original: <{url}|Link>"
                }
            ]
        }
    ]


def format_error_block(error: ParseAPIError, url: str) -> dict:
    """Format an error as a Slack block."""
    messages = {
        "INSUFFICIENT_CREDITS": "❌ Not enough credits to complete this analysis.",
        "RATE_LIMIT_EXCEEDED": "⏱️ Too many requests. Please try again later.",
        "INVALID_URL": "🔗 Invalid URL format.",
        "DEFAULT": f"❌ Error: {error}"
    }
    message = messages.get(error.code, messages["DEFAULT"])

    return {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"{message}\n\n*Code:* {error.code}"
        }
    }


# ============================================================================
# Slash Commands
# ============================================================================

@app.command("/parse-score")
async def handle_score(ack, body, respond):
    """Handle /parse-score command - quick truth score."""
    await ack()

    url = body.get("text", "").strip()
    if not url:
        await respond("⚠️ Usage: `/parse-score <url>`\nExample: `/parse-score https://www.bbc.com/news/...`")
        return

    # Send initial response
    await respond("🔄 Analyzing article...")

    try:
        result = await parse_client.quick_score(url, agent="slack-bot")
        block = format_score_block(
            result["score"],
            url,
            result.get("title", "")
        )
        await respond(blocks=[block])

    except ParseAPIError as e:
        await respond(blocks=[format_error_block(e, url)])
    except Exception as e:
        logger.error(f"Error in score command: {e}")
        await respond(f"❌ Unexpected error: {str(e)[:100]}")


@app.command("/parse-analyze")
async def handle_analyze(ack, body, respond):
    """Handle /parse-analyze command - full analysis."""
    await ack()

    url = body.get("text", "").strip()
    if not url:
        await respond("⚠️ Usage: `/parse-analyze <url>`\nExample: `/parse-analyze https://www.bbc.com/news/...`")
        return

    # Send initial response
    response = await respond("🔄 Starting full analysis... this may take 1-2 minutes.")

    try:
        result = await parse_client.full_analysis(url, agent="slack-bot")
        blocks = format_analysis_block(result, url)
        await respond(blocks=blocks)

    except ParseAPIError as e:
        await respond(blocks=[format_error_block(e, url)])
    except Exception as e:
        logger.error(f"Error in analyze command: {e}")
        await respond(f"❌ Unexpected error: {str(e)[:100]}")


@app.command("/parse-rewrite")
async def handle_rewrite(ack, body, respond):
    """Handle /parse-rewrite command - bias-free rewrite."""
    await ack()

    url = body.get("text", "").strip()
    if not url:
        await respond("⚠️ Usage: `/parse-rewrite <url>`\nExample: `/parse-rewrite https://www.bbc.com/news/...`")
        return

    # Send initial response
    await respond("🔄 Generating bias-free rewrite...")

    try:
        result = await parse_client.rewrite(url, agent="slack-bot")
        blocks = format_rewrite_block(result, url)
        await respond(blocks=blocks)

    except ParseAPIError as e:
        await respond(blocks=[format_error_block(e, url)])
    except Exception as e:
        logger.error(f"Error in rewrite command: {e}")
        await respond(f"❌ Unexpected error: {str(e)[:100]}")


@app.command("/parse-help")
async def handle_help(ack, body):
    """Handle /parse-help command - show command reference."""
    await ack()

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🤖 Parse Slack Bot Commands",
                "emoji": True
            }
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*Available Commands:*\n\n"
                    "`/parse-score <url>`\n"
                    "Get a quick truth score (0-100) for any article.\n\n"
                    "`/parse-analyze <url>`\n"
                    "Full analysis with deception detection, fallacy breakdown, and AI assessment.\n\n"
                    "`/parse-rewrite <url>`\n"
                    "Generate a bias-free rewrite of the article.\n\n"
                    "`/parse-help`\n"
                    "Show this command reference."
                )
            }
        },
        {"type": "divider"},
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Powered by <https://parsethe.media|Parse> | Truth Detection & Manipulation Detection"
                }
            ]
        }
    ]

    # Respond to the command
    await client.chat_postMessage(
        channel=body["channel_id"],
        blocks=blocks
    )


# ============================================================================
# Events
# ============================================================================

@app.event("app_mention")
async def handle_app_mention(event, client, logger):
    """Handle app mentions - provide help."""
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "👋 Hi! I'm the Parse bot. I can help you analyze articles for truthfulness.\n\n"
                    "Use `/parse-help` to see available commands."
                )
            }
        }
    ]

    try:
        await client.chat_postMessage(
            channel=event["channel"],
            blocks=blocks
        )
    except SlackApiError as e:
        logger.error(f"Error responding to app_mention: {e}")


# ============================================================================
# Main
# ============================================================================

def main():
    """Start the Slack bot in socket mode."""
    logger.info("Starting Parse Slack Bot...")

    # Log usage stats
    stats = ParseClient.get_usage_stats()
    logger.info(f"Daily credit limit: {stats.daily_limit}")
    logger.info(f"Daily credits used: {stats.daily_credits_used}")

    # Socket mode handler (for development)
    if SLACK_APP_LEVEL_TOKEN:
        handler = SocketModeHandler(app, SLACK_APP_LEVEL_TOKEN)
        logger.info("Running in Socket Mode")
        handler.start()
    else:
        # HTTP mode (for production with a server)
        from slack_bolt.adapter.fastapi import SlackRequestHandler
        from fastapi import FastAPI

        api_app = FastAPI()
        handler = SlackRequestHandler(app)

        @api_app.post("/slack/events")
        async def slack_events(req):
            return await handler.handle(req)

        import uvicorn
        logger.info("Running in HTTP Mode on port 3000")
        uvicorn.run(api_app, host="0.0.0.0", port=3000)


if __name__ == "__main__":
    main()
