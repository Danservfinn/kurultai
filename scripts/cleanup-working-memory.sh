#!/bin/bash
# Cleanup working-memory — delete directories older than 30 days

WORKING_MEMORY="/Users/kublai/.openclaw/agents/shared-context/working-memory"

find "$WORKING_MEMORY" -type d -name "task-*" -mtime +30 -exec rm -rf {} + 2>/dev/null

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Cleaned up working-memory (30+ day old task dirs)"
