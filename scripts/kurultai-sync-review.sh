#!/bin/bash
# Kublai Kurultai Sync Review
# Purpose: Review sync results, distill learnings, execute actions

SYNC_FILE=$(ls -t /Users/kublai/.openclaw/agents/main/shared-context/KURULTAI-SYNC-*.md 2>/dev/null | head -1)

if [ -z "$SYNC_FILE" ]; then
    echo "❌ No Kurultai Sync files found"
    exit 1
fi

echo "=== Kurultai Sync Review ==="
echo "File: $SYNC_FILE"
echo ""

# Show the sync file
cat "$SYNC_FILE"

echo ""
echo "=== Kublai Action Prompts ==="
echo ""
echo "1. What patterns do you see across agents?"
echo "2. What blockers need immediate action?"
echo "3. What dependencies need coordination?"
echo "4. What synergies can be enabled?"
echo "5. What process improvements should be implemented?"
echo ""
echo "After reviewing, update the sync file with:"
echo "  - Distilled learnings"
echo "  - Action items"
echo "  - Process improvements"
echo ""
echo "Then run:"
echo "  ./scripts/kurultai-sync-log.sh"
echo ""
