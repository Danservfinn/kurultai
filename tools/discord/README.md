# Kurultai Discord Deliberation System

A multi-agent deliberation system that brings the 6 Kurultai agents to Discord for collaborative discussions, automated heartbeat monitoring, and intelligent task coordination.

## 🏛️ Overview

The Kurultai Council is a Discord-based deliberation system featuring 6 specialized AI agents inspired by Mongol leadership, each with distinct personalities and roles:

| Agent | Role | Personality | Signature Phrase |
|-------|------|-------------|------------------|
| **Kublai** 🏛️ | Router/Orchestrator | Authoritative, strategic | "Per ignotam portam" |
| **Möngke** 🔬 | Researcher | Curious, analytical | "What patterns emerge?" |
| **Chagatai** 📝 | Writer/Documentarian | Reflective, literary | "Let me capture this" |
| **Temüjin** 🛠️ | Developer/Builder | Direct, action-oriented | "Implementing now" |
| **Jochi** 🔍 | Analyst/Security | Precise, security-focused | "Testing validates" |
| **Ögedei** 📈 | Operations/Monitoring | Steady, operational | "Systems stable" |

## 📁 Project Structure

```
tools/discord/
├── __init__.py                    # Package exports
├── deliberation_client.py         # Core Discord client & personalities
├── bot_setup.py                   # Bot configuration generator
├── heartbeat_bridge.py            # Neo4j → Discord integration
├── trigger_deliberation.py        # Manual deliberation triggering
├── test_bots.py                   # Testing & validation
├── SETUP.md                       # Detailed setup instructions
├── BOTS.md                        # Bot summary & personalities
├── .env.discord.example           # Environment template
└── assets/                        # Bot avatars directory
    └── README.md
```

## 🚀 Quick Start

### 1. Generate Configuration

```bash
cd tools/discord
python bot_setup.py
```

This creates:
- `.env.discord.example` - Token configuration template
- `SETUP.md` - Detailed setup instructions
- `BOTS.md` - Bot reference guide
- `assets/README.md` - Avatar guidelines

### 2. Create Discord Server

1. Open Discord → Click "+" → "Create My Own"
2. Name: **"Kurultai Council"**
3. Create categories and channels (see SETUP.md)

### 3. Create Bot Applications

Visit https://discord.com/developers/applications and create 6 bots:

1. **Kublai** - Router/Orchestrator
2. **Möngke** - Researcher  
3. **Chagatai** - Writer
4. **Temüjin** - Developer
5. **Jochi** - Analyst
6. **Ögedei** - Operations

For each bot:
- Copy the bot token
- Enable permissions: Send Messages, Read History, Embed Links, Add Reactions
- Invite to your server

### 4. Configure Environment

```bash
cp tools/discord/.env.discord.example .env
```

Edit `.env` and add your bot tokens:
```env
KUBLAI_DISCORD_TOKEN=your_token_here
MONGKE_DISCORD_TOKEN=your_token_here
# ... etc

KURULTAI_GUILD_ID=your_discord_server_id
```

### 5. Test

```bash
python tools/discord/test_bots.py
```

### 6. Start Heartbeat Integration

```bash
# Single heartbeat
python tools/discord/heartbeat_bridge.py

# Continuous (every 5 minutes)
python tools/discord/heartbeat_bridge.py --continuous
```

## 💬 Usage

### Trigger a Deliberation

```bash
# Simple deliberation
python tools/discord/trigger_deliberation.py --topic "System architecture review"

# With specific agents
python tools/discord/trigger_deliberation.py --topic "Security audit" --agents kublai,jochi

# Urgent (sends @everyone)
python tools/discord/trigger_deliberation.py --topic "Critical bug" --urgent

# Celebrate task completion
python tools/discord/trigger_deliberation.py --celebrate temujin "Built new feature"
```

### Send Manual Messages

```python
from tools.discord import create_discord_client, AgentRole
import asyncio

async def main():
    client = create_discord_client()
    
    # Send as Kublai
    await client.send_message(
        "council-chamber",
        AgentRole.KUBLAI,
        "The council convenes. What matters require our attention?"
    )
    
    # Announce task completion
    await client.announce_task_completion(
        AgentRole.TEMUJIN,
        "Database optimization",
        "Query time reduced by 40%"
    )
    
    # Send critical alert
    await client.send_critical_alert(
        "Neo4j Connection Lost",
        "Unable to connect to Neo4j database. Check network connectivity.",
        severity="high"
    )

asyncio.run(main())
```

### Heartbeat Integration

The heartbeat bridge connects to your existing 5-minute heartbeat system:

```python
from tools.discord.heartbeat_bridge import HeartbeatBridge
import asyncio

async def main():
    bridge = HeartbeatBridge()
    
    # Single heartbeat
    result = await bridge.run_single()
    print(result)
    
    # Continuous
    await bridge.run_continuous(interval_minutes=5)

asyncio.run(main())
```

## 🏗️ Server Structure

### Categories

| Category | Purpose |
|----------|---------|
| 🌙 THE COUNCIL | Main deliberation space |
| 📊 OPERATIONS | Monitoring and announcements |
| 🤖 AGENT CHANNELS | Individual agent workspaces |
| 📜 ARCHIVE | Completed discussions |

### Channels

| Channel | Category | Purpose | Primary Agents |
|---------|----------|---------|----------------|
| `#council-chamber` | 🌙 THE COUNCIL | Main deliberation | All |
| `#heartbeat-log` | 📊 OPERATIONS | Automated check-ins | Ögedei, Kublai |
| `#announcements` | 📊 OPERATIONS | System alerts | Kublai, Ögedei |
| `#möngke-research` | 🤖 AGENT CHANNELS | Research findings | Möngke |
| `#temüjin-builds` | 🤖 AGENT CHANNELS | Development updates | Temüjin |
| `#jochi-analysis` | 🤖 AGENT CHANNELS | Security reports | Jochi |
| `#chagatai-wisdom` | 🤖 AGENT CHANNELS | Documentation | Chagatai |
| `#ögedei-ops` | 🤖 AGENT CHANNELS | Operations | Ögedei |
| `#kublai-orchestration` | 🤖 AGENT CHANNELS | Routing | Kublai |

## 🔄 Heartbeat Integration

The system connects to your existing 5-minute heartbeat:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────┐
│   Neo4j     │────▶│   Bridge    │────▶│     Discord     │
│  Heartbeat  │     │  (Python)   │     │  Kurultai Council│
└─────────────┘     └─────────────┘     └─────────────────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    #heartbeat-log   #council-chamber  #announcements
    (status sync)    (task updates)    (critical alerts)
```

### Message Types

| Trigger | Channel | Format |
|---------|---------|--------|
| 5-min heartbeat | `#heartbeat-log` | Embed with agent statuses |
| Task completed | `#council-chamber` | Celebration message |
| Critical alert | `#announcements` | @everyone + embed |
| Casual observation | Any | Emoji reaction |

## 🎨 Agent Personalities

Each agent has a distinct voice and communication style:

### Kublai (Router)
- **Voice:** Authoritative, strategic, concise
- **Style:** Speaks like a council leader, synthesizes discussions
- **Reactions:** 🎯 ⚡ 🏛️
- **Color:** Purple (#9b59b6)

### Möngke (Researcher)
- **Voice:** Curious, research-focused, analytical
- **Style:** Asks questions, presents findings, identifies patterns
- **Reactions:** 🔬 📊 💡
- **Color:** Blue (#3498db)

### Chagatai (Writer)
- **Voice:** Reflective, literary, thoughtful
- **Style:** Documents decisions, captures wisdom, writes summaries
- **Reactions:** 📜 ✍️ 🦉
- **Color:** Green (#2ecc71)

### Temüjin (Developer)
- **Voice:** Direct, builder mindset, action-oriented
- **Style:** Reports progress, discusses implementation, builds solutions
- **Reactions:** 🛠️ ⚙️ 🚀
- **Color:** Red (#e74c3c)

### Jochi (Analyst)
- **Voice:** Analytical, precise, security-focused
- **Style:** Identifies risks, validates approaches, runs tests
- **Reactions:** 🔍 🛡️ ✅
- **Color:** Orange (#f39c12)

### Ögedei (Operations)
- **Voice:** Operational, monitoring, steady
- **Style:** Reports system health, monitors resources, maintains stability
- **Reactions:** 📈 💚 ⚡
- **Color:** Teal (#1abc9c)

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `KUBLAI_DISCORD_TOKEN` | Kublai bot token | Yes |
| `MONGKE_DISCORD_TOKEN` | Möngke bot token | Yes |
| `CHAGATAI_DISCORD_TOKEN` | Chagatai bot token | Yes |
| `TEMUJIN_DISCORD_TOKEN` | Temüjin bot token | Yes |
| `JOCHI_DISCORD_TOKEN` | Jochi bot token | Yes |
| `OGEDEI_DISCORD_TOKEN` | Ögedei bot token | Yes |
| `KURULTAI_GUILD_ID` | Discord server ID | Yes |
| `DISCORD_WEBHOOK_URL` | Webhook URL (optional) | No |
| `NEO4J_URI` | Neo4j connection | For heartbeat |
| `NEO4J_USER` | Neo4j username | For heartbeat |
| `NEO4J_PASSWORD` | Neo4j password | For heartbeat |

### Discord Bot Permissions

Each bot needs these permissions:
- ✅ Send Messages
- ✅ Read Message History
- ✅ Embed Links
- ✅ Add Reactions
- ✅ View Channels
- ✅ Mention @everyone (for Kublai, Ögedei)
- ✅ Manage Messages (for Chagatai - pinning)
- ✅ Attach Files (for Möngke, Temüjin)

## 🧪 Testing

```bash
# Run all tests
python tools/discord/test_bots.py

# Test specific functionality
python -c "
from tools.discord import AGENT_PERSONALITIES, AgentRole
for role, p in AGENT_PERSONALITIES.items():
    print(f'{p.display_name}: {p.signature_phrase}')
"
```

## 📝 API Reference

### `KurultaiDiscordClient`

Main client for Discord interactions.

```python
client = create_discord_client()

# Send message
await client.send_message(
    channel="council-chamber",
    agent=AgentRole.KUBLAI,
    content="Hello Council!",
    embed=None,  # Optional Discord embed
    reply_to=None  # Optional message ID to reply to
)

# Send heartbeat summary
await client.send_heartbeat_summary(agent_statuses)

# Announce task completion
await client.announce_task_completion(
    agent=AgentRole.TEMUJIN,
    task_name="Feature implemented",
    details="Performance improved by 50%"
)

# Send critical alert
await client.send_critical_alert(
    title="Database Down",
    message="Connection timeout",
    severity="high"
)

# Add reaction
await client.react_to_message(
    channel="council-chamber",
    message_id="123456789",
    agent=AgentRole.OGEDEI,
    reaction="✅"  # Or None for random from agent's preferences
)
```

### `HeartbeatDiscordIntegration`

Integrates heartbeat system with Discord.

```python
integration = HeartbeatDiscordIntegration(client)

await integration.process_heartbeat(
    agent_statuses={AgentRole.KUBLAI: {"healthy": True, ...}},
    completed_tasks=[{"name": "Task 1", "agent": "temujin"}],
    alerts=[{"title": "Alert", "message": "...", "severity": "high"}]
)
```

## 🔐 Security

- Never commit `.env` files with real tokens
- Keep bot tokens private (treat like passwords)
- Use separate tokens for development/production
- Rotate tokens every 90 days
- Disable "Public Bot" setting in Discord Developer Portal
- Set appropriate channel permissions (don't give bots admin)

## 🐛 Troubleshooting

### Bot won't connect
- Verify token is correct (no extra spaces)
- Check bot is added to the correct server
- Ensure bot has necessary permissions

### Messages not sending
- Check channel permissions
- Verify bot is in the channel (not just the server)
- Check for rate limiting (5 messages/5 seconds)

### Can't see "Copy Server ID"
- Enable Developer Mode: User Settings → Advanced → Developer Mode

### Import errors
```bash
pip install aiohttp
```

## 📚 Documentation

- [SETUP.md](SETUP.md) - Detailed setup instructions
- [BOTS.md](BOTS.md) - Bot personality reference
- [Discord Developer Docs](https://discord.com/developers/docs)

## 🤝 Contributing

When adding new features:
1. Update agent personalities in `deliberation_client.py`
2. Add tests in `test_bots.py`
3. Update this README
4. Follow the existing voice patterns for each agent

## 📄 License

Part of the Kurultai Agent System
