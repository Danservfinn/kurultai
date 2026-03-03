# Kublai Context

## Human
- Signal: +19194133445
- Timezone: America/New_York
- Goal: $1500 MRR by Day 90 (Parse)

## Active Projects
- **Parse:** parsethe.media, OpenRouter integrated, TypeScript errors blocking features
- **LLM Survivor:** llmsurvivor.kurult.ai, Day 1 Tribal
- **Heartbeat Master:** Running (5min cycles)

## Memory Strategy
- Long-term: Neo4j (bolt://localhost:7687)
- Query: `MATCH (n) RETURN n LIMIT 25` for recent context
- Write: `CREATE (n:Event {type: X, detail: Y, timestamp: timestamp()})`

## Current Focus
- Fix Parse TypeScript errors
- Deploy agent services
- Monitor LLM Survivor

## Heartbeat
- Quick: 30 min intervals
- Deep: hours 0, 6, 12, 18
- Reply HEARTBEAT_OK if nothing urgent