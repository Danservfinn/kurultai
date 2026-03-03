#!/bin/bash
# Task Queue Writer - Writes tasks to agent-specific directories
# Kublai decides which agent gets each task based on the routing matrix

set -e

AGENT_DIR="/Users/kublai/.openclaw/agents/main/agent"

usage() {
    echo "Usage: task-queue-write.sh -a <agent> -t <task> [-d <description>]"
    echo ""
    echo "Options:"
    echo "  -a <agent>   Agent name (temujin, mongke, chagatai, jochi, ogedei)"
    echo "  -t <task>    Task description (required)"
    echo "  -d <desc>    Detailed description (optional)"
    echo "  -p <prio>    Priority: high, normal, low (default: normal)"
    echo ""
    echo "Agent Routing Matrix:"
    echo "  temujin  - Code generation, builds, infrastructure"
    echo "  mongke   - Research, API discovery, truth-seeking"
    echo "  chagatai - Writing, documentation, creative"
    echo "  jochi    - Testing, security, analysis, pattern recognition"
    echo "  ogedei   - Monitoring, health checks, failover"
    exit 1
}

# Parse arguments
AGENT=""
TASK=""
DESC=""
PRIORITY="normal"

while getopts "a:t:d:p:h" opt; do
    case $opt in
        a) AGENT="$OPTARG" ;;
        t) TASK="$OPTARG" ;;
        d) DESC="$OPTARG" ;;
        p) PRIORITY="$OPTARG" ;;
        h) usage ;;
        *) usage ;;
    esac
done

# Validate agent
if [ -z "$AGENT" ]; then
    echo "Error: Agent is required (-a)"
    usage
fi

if [ -z "$TASK" ]; then
    echo "Error: Task is required (-t)"
    usage
fi

# Validate agent
case $AGENT in
    temujin|mongke|chagatai|jochi|ogedei|kublai) ;;
    *)
        echo "Error: Invalid agent '$AGENT'"
        echo "Valid agents: temujin, mongke, chagatai, jochi, ogedei, kublai"
        exit 1
        ;;
esac

# Validate priority
case $PRIORITY in
    high|normal|low) ;;
    *)
        echo "Error: Invalid priority '$PRIORITY'"
        echo "Valid priorities: high, normal, low"
        exit 1
        ;;
esac

# Create task file
TASK_DIR="$AGENT_DIR/$AGENT/tasks"
mkdir -p "$TASK_DIR"

TIMESTAMP=$(date +%s)
TASK_FILE="$TASK_DIR/${PRIORITY}-${TIMESTAMP}.md"

cat > "$TASK_FILE" << EOF
---
agent: $AGENT
created: $(date -r $TIMESTAMP +"%Y-%m-%d %H:%M:%S")
priority: $PRIORITY
status: pending
---

# Task: $TASK

$DESC

EOF

echo "Task written to: $TASK_FILE"
echo "Agent: $AGENT | Priority: $PRIORITY"
echo "Task: $TASK"