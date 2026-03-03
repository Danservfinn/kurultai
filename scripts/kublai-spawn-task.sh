#!/bin/bash
# Kublai Task Assignment Helper
# Usage: kublai-spawn-task.sh -a <agent> -t "<task description>"
# This is a convenience wrapper around sessions_spawn

set -e

usage() {
    echo "Kublai Task Spawner"
    echo "Usage: $0 -a <agent> -t <task> [-m <model>]"
    echo ""
    echo "Agents:"
    echo "  temujin  - Code generation, builds (default: qwen3.5-plus)"
    echo "  mongke   - Research, truth-seeking (default: qwen3.5-plus)"
    echo "  chagatai - Writing, creative (default: qwen3.5-plus)"
    echo "  jochi    - Testing, analysis (default: MiniMax-M2.5)"
    echo "  ogedei   - Monitoring, ops (default: qwen3.5-plus)"
    echo ""
    echo "Example:"
    echo "  $0 -a temujin -t \"Fix the login bug in Parse\""
    exit 1
}

AGENT=""
TASK=""
MODEL=""

while getopts "a:t:m:h" opt; do
    case $opt in
        a) AGENT="$OPTARG" ;;
        t) TASK="$OPTARG" ;;
        m) MODEL="$OPTARG" ;;
        h) usage ;;
        *) usage ;;
    esac
done

if [ -z "$AGENT" ] || [ -z "$TASK" ]; then
    usage
fi

# Set default model based on agent
if [ -z "$MODEL" ]; then
    case $AGENT in
        jochi) MODEL="MiniMax-M2.5" ;;
        *) MODEL="qwen3.5-plus" ;;
    esac
fi

# Validate agent
case $AGENT in
    temujin|mongke|chagatai|jochi|ogedei|kublai) ;;
    *)
        echo "Error: Invalid agent '$AGENT'"
        exit 1
        ;;
esac

echo "Spawning $AGENT (model: $MODEL) for task: $TASK"

# Spawn the agent - this echoes the spawn command for Kublai to execute
# Kublai should use sessions_spawn directly in code
echo ""
echo "SESSION_SPAWN_PARAMS:"
echo "  agent: $AGENT"
echo "  task: $TASK"
echo "  model: $MODEL"
echo "  label: ${AGENT}-task-$(date +%s)"