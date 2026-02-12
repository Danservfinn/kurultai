# Full Context Discord Bot

## The Problem

Discord bots running as standalone Python scripts **cannot** access:
1. **OpenClaw tools** (like `sessions_spawn` for LLM generation)
2. **Notion integration** (requires OpenClaw context for some operations)

## The Solution

Run the Discord bot **inside an OpenClaw session** as a long-running task.

## Architecture

```
OpenClaw Session (has tools)
    ↓
Discord Bot runs continuously
    ↓
When message received:
    - Fetch Neo4j context (direct)
    - Fetch Notion context (via tools)
    - Call LLM via sessions_spawn ✅
    - Post to Discord
```

## How to Run

### Option 1: Manual (Current Session)

```python
# Load environment
import os
with open('tools/discord/.env') as f:
    for line in f:
        if '=' in line and not line.startswith('#'):
            key, val = line.strip().split('=', 1)
            os.environ[key] = val.strip().strip('"').strip("'")

os.environ['DISCORD_WEBHOOK_URL'] = os.environ['DISCORD_COUNCIL_CHAMBER_WEBHOOK_URL']

# Run bot
import asyncio
from tools.discord.bot_full_context import main
asyncio.run(main())
```

### Option 2: Spawn as Background Task

```python
# Spawn bot as long-running sub-agent
sessions_spawn(
    task="""Run the Discord bot with full context.
    
    Instructions:
    1. Load tools/discord/.env
    2. Set DISCORD_WEBHOOK_URL
    3. Run tools/discord/bot_full_context.py
    4. Keep running until stopped
    
    The bot should respond to @mentions in Discord
    with LLM-generated responses based on Neo4j + Notion context.
    """,
    agent_id="ogedei",  # Ops agent manages the bot
    label="discord-bot-full-context",
    timeout_seconds=3600  # Run for 1 hour
)
```

### Option 3: Cron Job (Persistent)

```python
# Add to cron to restart every hour
cron.add(
    job={
        "name": "discord-bot-full-context",
        "schedule": {"kind": "every", "everyMs": 3600000},
        "payload": {
            "kind": "agentTurn",
            "message": "Start Discord bot with full context"
        },
        "sessionTarget": "isolated"
    }
)
```

## What Changes

| Before | After |
|--------|-------|
| ❌ `sessions_spawn` not available | ✅ `sessions_spawn` works |
| ❌ Generic responses | ✅ LLM-generated responses |
| ❌ No Notion access | ✅ Full Notion integration |
| ❌ Limited context | ✅ Neo4j + Notion + OpenClaw |

## Testing

Once running, mention an agent in Discord:

```
@Möngke what are you working on?
```

Expected response:
```
I'm currently analyzing AI self-improvement methodologies. 
Completed: Reflexion paper showing 30% improvement on code tasks. 
Next: Constitutional AI alignment patterns. 

— *What patterns emerge?*
```

## Files

- `bot_full_context.py` - Full context bot (runs in OpenClaw)
- `bot_natural.py` - Basic bot (no OpenClaw context)
- `bot_deliberation.py` - Agent deliberations

## Migration Path

1. **Stop old bot**: `kill $(cat /tmp/discord_bot.pid)`
2. **Start full context bot**: Run in OpenClaw session
3. **Test**: Mention @Agent in Discord
4. **Verify**: Responses should be LLM-generated with real context

---
**Note:** This requires running inside an OpenClaw session. The standalone `bot_natural.py` will have limited functionality (Neo4j only, no LLM generation).
