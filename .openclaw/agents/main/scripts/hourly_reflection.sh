#!/bin/bash
# Hourly Agent Reflection System
# One agent reflects each hour (rotating)

HOUR=$(date +%H)
AGENT_NUM=$((HOUR % 6))

case $AGENT_NUM in
  0) AGENT="kublai" ;;
  1) AGENT="mongke" ;;
  2) AGENT="chagatai" ;;
  3) AGENT="temujin" ;;
  4) AGENT="jochi" ;;
  5) AGENT="ogedei" ;;
esac

echo "[$(date)] Reflection for: $AGENT"

# Create memory entry
mkdir -p /Users/kublai/.openclaw/agents/$AGENT/memory
DATE=$(date +%Y-%m-%d)
TIME=$(date +%H:%M)

cat >> /Users/kublai/.openclaw/agents/$AGENT/memory/$DATE.md << REFLECT

## $TIME - Hourly Reflection

### Completed
- 

### Decisions
- 

### Worked Well
- 

### Improvements
- 

### Next Hour
- 

REFLECT

echo "[$(date)] Done for $AGENT"
