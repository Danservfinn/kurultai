# Kurultai Discord Bot Setup Guide

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
