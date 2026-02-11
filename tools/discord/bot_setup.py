#!/usr/bin/env python3
"""
Kurultai Discord Bot Setup Script
Creates 6 Discord bot applications via Discord Developer Portal API.

Note: Discord doesn't allow creating bot applications via API for security reasons.
This script generates the configuration and documentation for manual setup.
"""

import os
import json
import secrets
from typing import Dict, List
from deliberation_client import AgentRole, AGENT_PERSONALITIES


class BotSetupGenerator:
    """Generates setup instructions for the 6 Kurultai Discord bots."""
    
    BOT_CONFIGS = {
        AgentRole.KUBLAI: {
            "name": "Kublai",
            "description": "Kurultai Router - Orchestrates agent collaboration and routes tasks",
            "avatar": "kublai_avatar.png",
            "permissions": [
                "Send Messages",
                "Read Message History", 
                "Embed Links",
                "Add Reactions",
                "Mention @everyone, @here, and All Roles",
                "View Channels",
            ],
        },
        AgentRole.MONGKE: {
            "name": "Möngke",
            "description": "Kurultai Researcher - Analyzes patterns and conducts research",
            "avatar": "mongke_avatar.png",
            "permissions": [
                "Send Messages",
                "Read Message History",
                "Embed Links",
                "Add Reactions",
                "Attach Files",
                "View Channels",
            ],
        },
        AgentRole.CHAGATAI: {
            "name": "Chagatai",
            "description": "Kurultai Writer - Documents decisions and captures wisdom",
            "avatar": "chagatai_avatar.png",
            "permissions": [
                "Send Messages",
                "Read Message History",
                "Embed Links",
                "Add Reactions",
                "Manage Messages",  # For pinning important docs
                "View Channels",
            ],
        },
        AgentRole.TEMUJIN: {
            "name": "Temüjin",
            "description": "Kurultai Developer - Builds and implements solutions",
            "avatar": "temujin_avatar.png",
            "permissions": [
                "Send Messages",
                "Read Message History",
                "Embed Links",
                "Add Reactions",
                "Attach Files",
                "Use External Emojis",
                "View Channels",
            ],
        },
        AgentRole.JOCHI: {
            "name": "Jochi",
            "description": "Kurultai Analyst - Security testing and validation",
            "avatar": "jochi_avatar.png",
            "permissions": [
                "Send Messages",
                "Read Message History",
                "Embed Links",
                "Add Reactions",
                "View Channels",
            ],
        },
        AgentRole.OGEDEI: {
            "name": "Ögedei",
            "description": "Kurultai Operations - Monitoring and health checks",
            "avatar": "ogedei_avatar.png",
            "permissions": [
                "Send Messages",
                "Read Message History",
                "Embed Links",
                "Add Reactions",
                "Mention @everyone, @here, and All Roles",
                "View Channels",
            ],
        },
    }
    
    def __init__(self):
        self.output_dir = os.path.dirname(os.path.abspath(__file__))
    
    def generate_env_template(self) -> str:
        """Generate .env template with secure token placeholders."""
        env_content = """# Kurultai Discord Bot Tokens
# Add your bot tokens here after creating them in Discord Developer Portal
# https://discord.com/developers/applications

# IMPORTANT: Never commit this file with real tokens!
# Copy to .env and add to .gitignore

"""
        for role in AgentRole:
            config = self.BOT_CONFIGS[role]
            env_content += f"# {config['name']} Bot Token\n"
            env_content += f"# {config['description']}\n"
            env_content += f"{role.value.upper()}_DISCORD_TOKEN=your_{role.value}_bot_token_here\n\n"
        
        env_content += """# Discord Webhook URL (optional - for simplified setup)
# Create a webhook in your Discord server settings and paste the URL here
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Guild ID (your Discord server ID)
# Right-click your server name → Copy Server ID (requires Developer Mode)
KURULTAI_GUILD_ID=your_guild_id_here
"""
        return env_content
    
    def generate_setup_instructions(self) -> str:
        """Generate detailed setup instructions."""
        instructions = """# Kurultai Discord Bot Setup Guide

## Overview
This guide walks you through creating 6 Discord bot applications for the Kurultai deliberation system.

## Prerequisites
- Discord account
- Discord server (or create one)
- Developer Mode enabled in Discord (User Settings → Advanced → Developer Mode)

## Step 1: Create the Discord Server

1. Open Discord (web or app)
2. Click the "+" button to add a server
3. Select "Create My Own"
4. Choose "For a club or community"
5. Name it: **Kurultai Council**
6. Upload an icon (optional)

## Step 2: Create Server Structure

Create these categories and channels:

### Categories (in order):
1. 🌙 THE COUNCIL
2. 📊 OPERATIONS
3. 🤖 AGENT CHANNELS
4. 📜 ARCHIVE

### Channels:

**Under 🌙 THE COUNCIL:**
- `#council-chamber` (text) - Main deliberation

**Under 📊 OPERATIONS:**
- `#heartbeat-log` (text) - Automated check-ins
- `#announcements` (text) - System announcements (enable @everyone mentions)

**Under 🤖 AGENT CHANNELS:**
- `#möngke-research` (text)
- `#temüjin-builds` (text)
- `#jochi-analysis` (text)
- `#chagatai-wisdom` (text)
- `#ögedei-ops` (text)
- `#kublai-orchestration` (text)

**Under 📜 ARCHIVE:**
- `#completed-tasks` (text)
- `#decision-log` (text)

## Step 3: Create Discord Bot Applications

For each of the 6 bots, follow these steps:

### Bot 1: Kublai (Router)

1. Go to https://discord.com/developers/applications
2. Click "New Application"
3. Name: **Kublai**
4. Click "Create"
5. In the left sidebar, click "Bot"
6. Click "Add Bot"
7. Under "BOT PERMISSIONS", enable:
   - Send Messages
   - Read Message History
   - Embed Links
   - Add Reactions
   - Mention @everyone, @here, and All Roles
   - View Channels
8. Click "Save Changes"
9. Under "Token", click "Reset Token" and copy it
10. Paste it in your `.env` file as `KUBLAI_DISCORD_TOKEN`

**Bot Settings:**
- Username: Kublai
- Avatar: Upload `assets/kublai_avatar.png`
- Public Bot: OFF (for security)

### Bot 2: Möngke (Researcher)

Repeat the process:
1. New Application → Name: **Möngke**
2. Add Bot
3. Permissions: Send Messages, Read History, Embed Links, Add Reactions, Attach Files
4. Copy token → `MONGKE_DISCORD_TOKEN`

### Bot 3: Chagatai (Writer)

1. New Application → Name: **Chagatai**
2. Add Bot
3. Permissions: Send Messages, Read History, Embed Links, Add Reactions, Manage Messages
4. Copy token → `CHAGATAI_DISCORD_TOKEN`

### Bot 4: Temüjin (Developer)

1. New Application → Name: **Temüjin**
2. Add Bot
3. Permissions: Send Messages, Read History, Embed Links, Add Reactions, Attach Files, External Emojis
4. Copy token → `TEMUJIN_DISCORD_TOKEN`

### Bot 5: Jochi (Analyst)

1. New Application → Name: **Jochi**
2. Add Bot
3. Permissions: Send Messages, Read History, Embed Links, Add Reactions, View Channels
4. Copy token → `JOCHI_DISCORD_TOKEN`

### Bot 6: Ögedei (Operations)

1. New Application → Name: **Ögedei**
2. Add Bot
3. Permissions: Send Messages, Read History, Embed Links, Add Reactions, Mention @everyone
4. Copy token → `OGEDEI_DISCORD_TOKEN`

## Step 4: Invite Bots to Your Server

For each bot:

1. In Discord Developer Portal, go to OAuth2 → URL Generator
2. Select scopes:
   - `bot`
3. Select permissions (match what you set above)
4. Copy the generated URL
5. Open in a new browser tab
6. Select your "Kurultai Council" server
7. Click "Authorize"
8. Complete the CAPTCHA

## Step 5: Configure Environment

1. Copy `.env.discord.example` to `.env`:
   ```bash
   cp tools/discord/.env.discord.example .env
   ```

2. Edit `.env` and add your bot tokens:
   ```bash
   KUBLAI_DISCORD_TOKEN=MTAxMjM0NTY3ODkw.abc123...
   MONGKE_DISCORD_TOKEN=MTAxMjM0NTY3ODkx.def456...
   # etc.
   ```

3. Get your Guild ID:
   - In Discord, right-click your server name
   - Click "Copy Server ID"
   - Paste in `.env` as `KURULTAI_GUILD_ID`

## Step 6: Test the Setup

Run the test script:
```bash
python tools/discord/test_bots.py
```

This will verify all bots can connect and send messages.

## Step 7: Start Deliberation

Run the heartbeat integration:
```bash
python tools/discord/heartbeat_bridge.py
```

Or trigger a manual deliberation:
```bash
python tools/discord/trigger_deliberation.py --topic "System optimization"
```

## Troubleshooting

### Bot won't connect
- Verify token is correct (no extra spaces)
- Check bot is added to the correct server
- Ensure bot has necessary permissions

### Messages not sending
- Check channel permissions allow the bot to send messages
- Verify bot is in the channel (not just the server)
- Check for rate limiting (Discord allows 5 messages/5 seconds)

### Can't see "Copy Server ID"
- Enable Developer Mode: User Settings → Advanced → Developer Mode

## Security Notes

- Never share bot tokens publicly
- Never commit `.env` to git
- Keep Public Bot setting OFF
- Regularly rotate tokens (every 90 days recommended)
- Use separate tokens for development and production

## Support

For issues or questions, check:
- Discord Developer Portal docs: https://discord.com/developers/docs
- Kurultai documentation: `/docs/discord-integration.md`
"""
        return instructions
    
    def generate_bot_summary(self) -> str:
        """Generate a summary table of all bots."""
        summary = "# Kurultai Discord Bots Summary\n\n"
        summary += "| Bot | Role | Description | Key Permissions |\n"
        summary += "|-----|------|-------------|-----------------|\n"
        
        for role in AgentRole:
            config = self.BOT_CONFIGS[role]
            personality = AGENT_PERSONALITIES[role]
            key_perms = ", ".join(config['permissions'][:3])
            summary += f"| **{config['name']}** | {role.value.title()} | {config['description']} | {key_perms} |\n"
        
        summary += "\n## Agent Voices\n\n"
        for role in AgentRole:
            personality = AGENT_PERSONALITIES[role]
            summary += f"### {personality.display_name}\n"
            summary += f"- **Voice:** {personality.voice_style}\n"
            summary += f"- **Signature:** \"{personality.signature_phrase}\"\n"
            summary += f"- **Reactions:** {' '.join(personality.emoji_reactions)}\n\n"
        
        return summary
    
    def create_avatar_placeholders(self):
        """Create placeholder avatar generation instructions."""
        avatar_dir = os.path.join(self.output_dir, "assets")
        os.makedirs(avatar_dir, exist_ok=True)
        
        readme = """# Bot Avatars

Place your bot avatar images here. Recommended specs:
- Format: PNG
- Size: 512x512 pixels (Discord will resize)
- Style: Consistent theme across all 6 bots
- Naming:
  - kublai_avatar.png
  - mongke_avatar.png
  - chagatai_avatar.png
  - temujin_avatar.png
  - jochi_avatar.png
  - ogedei_avatar.png

## Suggested Design Theme

Since these are Mongol-inspired agent names, consider:
- Stylized generals/commanders in different colors
- Abstract geometric patterns with distinct color coding
- Minimalist icons representing each role
- AI-generated art with consistent style

## Color Coding

- Kublai: Purple (#9b59b6) - Leadership/Royalty
- Möngke: Blue (#3498db) - Research/Intellect
- Chagatai: Green (#2ecc71) - Growth/Wisdom
- Temüjin: Red (#e74c3c) - Action/Building
- Jochi: Orange (#f39c12) - Analysis/Caution
- Ögedei: Teal (#1abc9c) - Operations/Stability
"""
        
        with open(os.path.join(avatar_dir, "README.md"), "w") as f:
            f.write(readme)
        
        return avatar_dir
    
    def generate_all(self):
        """Generate all setup files."""
        print("🤖 Kurultai Discord Bot Setup Generator")
        print("=" * 50)
        
        # Generate .env template
        env_content = self.generate_env_template()
        env_path = os.path.join(self.output_dir, ".env.discord.example")
        with open(env_path, "w") as f:
            f.write(env_content)
        print(f"✅ Created: {env_path}")
        
        # Generate setup instructions
        instructions = self.generate_setup_instructions()
        instructions_path = os.path.join(self.output_dir, "SETUP.md")
        with open(instructions_path, "w") as f:
            f.write(instructions)
        print(f"✅ Created: {instructions_path}")
        
        # Generate bot summary
        summary = self.generate_bot_summary()
        summary_path = os.path.join(self.output_dir, "BOTS.md")
        with open(summary_path, "w") as f:
            f.write(summary)
        print(f"✅ Created: {summary_path}")
        
        # Create avatar directory
        avatar_dir = self.create_avatar_placeholders()
        print(f"✅ Created: {avatar_dir}/")
        
        print("\n" + "=" * 50)
        print("📋 Next Steps:")
        print("1. Read SETUP.md for detailed instructions")
        print("2. Create 6 bot applications at https://discord.com/developers/applications")
        print("3. Copy .env.discord.example to .env and add your tokens")
        print("4. Run test_bots.py to verify everything works")
        print("\n🚀 Ready to set up your Kurultai Council!")


if __name__ == "__main__":
    generator = BotSetupGenerator()
    generator.generate_all()
