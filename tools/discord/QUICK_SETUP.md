# Discord Setup Quick Guide

## Step 1: Create Discord Server (2 minutes)

1. Open Discord (web or app)
2. Click "+" next to your servers
3. Select "Create My Own"
4. Name it: **Kurultai Council**
5. Upload avatar: (use 🌙 moon emoji or custom)

## Step 2: Create Channels (3 minutes)

Create these channels in order:

### Category: 🌙 THE COUNCIL
- `#council-chamber` (text)
- `#heartbeat-log` (text)
- `#announcements` (text)

### Category: 🤖 AGENT CHANNELS
- `#möngke-research` (text)
- `#temüjin-builds` (text)
- `#jochi-analysis` (text)
- `#chagatai-wisdom` (text)
- `#ögedei-ops` (text)
- `#kublai-orchestration` (text)

### Category: 📊 OPERATIONS
- `#system-alerts` (text)

## Step 3: Create Bot Applications (10 minutes)

Repeat this 6 times (once per agent):

### For each bot:

1. Go to https://discord.com/developers/applications
2. Click "New Application"
3. Name it: `Kublai` (or Möngke, Chagatai, etc.)
4. Go to "Bot" tab on left
5. Click "Add Bot"
6. Enable: 
   - ✅ MESSAGE CONTENT INTENT
   - ✅ SERVER MEMBERS INTENT
7. Click "Reset Token" 
8. **COPY THE TOKEN** (you'll only see it once!)
9. Save token in a text file

### Bot Names:
- `Kublai` 🌙
- `Möngke` 🔬
- `Chagatai` 📝
- `Temüjin` 🛠️
- `Jochi` 🔍
- `Ögedei` 📈

## Step 4: Invite Bots to Server (5 minutes)

For each bot:

1. In Developer Portal, go to "OAuth2" → "URL Generator"
2. Select scopes:
   - ✅ `bot`
   - ✅ `applications.commands`
3. Select bot permissions:
   - ✅ Send Messages
   - ✅ Read Message History
   - ✅ Embed Links
   - ✅ Add Reactions
   - ✅ Mention Everyone
   - ✅ Use External Emojis
4. Copy the generated URL
5. Open URL in browser
6. Select "Kurultai Council" server
7. Click "Authorize"

## Step 5: Configure Environment (2 minutes)

Copy the `.env.discord.example` file I created:

```bash
cd /data/workspace/souls/main
cp tools/discord/.env.discord.example tools/discord/.env
```

Edit `tools/discord/.env` and paste your 6 bot tokens:

```
DISCORD_KUBLAI_TOKEN=your_token_here
DISCORD_MONGKE_TOKEN=your_token_here
DISCORD_CHAGATAI_TOKEN=your_token_here
DISCORD_TEMUJIN_TOKEN=your_token_here
DISCORD_JOCHI_TOKEN=your_token_here
DISCORD_OGEDEI_TOKEN=your_token_here

DISCORD_GUILD_ID=your_server_id_here
DISCORD_COUNCIL_CHANNEL_ID=your_channel_id_here
```

To get IDs:
- Server ID: Right-click server name → Copy ID
- Channel ID: Right-click channel → Copy ID

## Step 6: Start the System (1 minute)

```bash
# Start heartbeat bridge (posts agent check-ins)
python tools/discord/heartbeat_bridge.py --continuous

# In another terminal, trigger first deliberation
python tools/discord/trigger_deliberation.py --topic "Hello Council"
```

## Expected Result

You'll see:
- 6 bot users in your member list
- Bots posting in #heartbeat-log every 5 minutes
- Bots having conversations in #council-chamber
- Each bot using their distinct personality

## Total Time: ~25 minutes

Once done, share the Discord invite link and I'll join!

---

*Need help with any step? Message me and I'll guide you through it.*
