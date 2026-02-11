"""
Agent Avatar Generator for Kurultai Discord Bots

Creates distinctive profile images for each of the 6 agents.
Uses emoji-based avatars as a quick solution, can be replaced with custom art.
"""

AGENT_AVATARS = {
    "Kublai": {
        "emoji": "🌙",
        "color": "#9b59b6",  # Purple
        "description": "Crescent moon - threshold between worlds",
    },
    "Möngke": {
        "emoji": "🔬",
        "color": "#3498db",  # Blue
        "description": "Microscope - seeking truth",
    },
    "Chagatai": {
        "emoji": "📜",
        "color": "#2ecc71",  # Green
        "description": "Scroll - preserving wisdom",
    },
    "Temüjin": {
        "emoji": "🛠️",
        "color": "#e74c3c",  # Red
        "description": "Tools - building systems",
    },
    "Jochi": {
        "emoji": "🔍",
        "color": "#f39c12",  # Orange
        "description": "Magnifying glass - analysis",
    },
    "Ögedei": {
        "emoji": "📈",
        "color": "#1abc9c",  # Teal
        "description": "Chart - monitoring systems",
    },
}

# For production, replace with actual image URLs
# These would be uploaded to a CDN or Discord asset library
AGENT_AVATAR_URLS = {
    # Example (replace with actual URLs):
    # "Kublai": "https://cdn.discordapp.com/avatars/.../kublai.png",
}

# Emoji-based avatars work immediately with webhooks
# Set avatar_url to None to use username with emoji
