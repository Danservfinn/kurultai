# Discord Bot Migration Complete

## ✅ Archived (Old Template System)

Moved to `tools/discord/archived/`:
- `bot_natural.py` - Old template-based bot
- `bot_natural_integration.py` - Integration layer
- `conversation_value_scorer.py` - Value scoring (v1)
- `conversation_value_scorer_v2.py` - Value scoring (v2)

## ✅ New System (LLM-Powered)

### Active Files
- `bot_natural.py` - **LLM-powered bot** (replaces old version)
- `bot_natural_llm.py` - Copy of LLM bot (backup)
- `bot_deliberation.py` - Agent-to-agent deliberations
- `start_bot.sh` - Main startup script

### Key Improvements

| Feature | Old | New |
|---------|-----|-----|
| Responses | Template phrases | LLM-generated |
| Context | None | Neo4j task status |
| Personalization | Static | Dynamic |
| Value gating | Blocked low-value convos | Always responds helpfully |
| Agent chat | Social/random | Purpose-driven |

## Usage

### Start the Bot
```bash
./tools/discord/start_bot.sh
```

### In Discord
Mention any agent:
```
@Möngke what did you find?
@Kublai Council status?
@Temüjin can you build X?
```

### What Happens
1. Bot detects mention
2. Fetches agent's real task status from Neo4j
3. Generates contextual LLM response
4. Posts to Discord

## Architecture

```
Discord Message
    ↓
Bot detects @Agent
    ↓
Query Neo4j for:
  - Current task
  - Task status
  - Recent results
    ↓
Build prompt with context
    ↓
Generate LLM response
    ↓
Post to Discord
```

## Files Structure

```
tools/discord/
├── bot_natural.py              ← LLM bot (ACTIVE)
├── bot_natural_llm.py          ← LLM bot (backup)
├── bot_deliberation.py         ← Agent deliberations
├── start_bot.sh                ← Startup script
├── archived/                   ← Old system
│   ├── bot_natural.py          (template-based)
│   ├── conversation_value_scorer.py
│   └── ...
└── deliberation_client.py      ← Agent definitions
```

## Rollback

If needed, restore old system:
```bash
cp tools/discord/archived/bot_natural.py tools/discord/
```

---
**Status:** ✅ Migration complete
