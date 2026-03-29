#!/bin/bash
# Retry rate-limited tasks script
# Run at 11pm when Claude Code rate limit resets

PENDING_DIR="$HOME/.openclaw/agents/main/tasks-pending-rate-limit"
AGENTS_DIR="$HOME/.openclaw/agents"

echo "[$(date -Iseconds)] Starting rate-limited task retry..."

if [ ! -d "$PENDING_DIR" ]; then
    echo "No pending tasks directory found"
    exit 0
fi

# Move tasks back to agent queues
for task_file in "$PENDING_DIR"/*.md; do
    if [ -f "$task_file" ]; then
        filename=$(basename "$task_file")
        
        # Determine target agent from filename prefix or content
        if [[ "$filename" == high-* ]] || [[ "$filename" == normal-* ]] || [[ "$filename" == low-* ]]; then
            # Extract agent from task file content
            agent=$(grep "^agent:" "$task_file" | cut -d' ' -f2 | tr -d '[:space:]')
            
            if [ -n "$agent" ] && [ -d "$AGENTS_DIR/$agent/tasks" ]; then
                mv "$task_file" "$AGENTS_DIR/$agent/tasks/"
                echo "Moved: $filename -> $agent/tasks/"
            else
                echo "WARNING: Could not determine agent for $filename"
            fi
        fi
    fi
done

# Clear task watcher state for these tasks so they'll be re-executed
python3 << 'PYTHON_EOF'
import json
from pathlib import Path
import glob

state_file = Path.home() / ".openclaw/agents/main/logs/task-watcher-state.json"
agents_dir = Path.home() / ".openclaw/agents"

if state_file.exists():
    with open(state_file) as f:
        state = json.load(f)
    
    # Remove state entries for all .md files in agent task directories
    for agent_dir in agents_dir.iterdir():
        if not agent_dir.is_dir():
            continue
        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue
        for task_file in tasks_dir.glob("*.md"):
            if not task_file.name.endswith('.executing.md') and not task_file.name.endswith('.done.md'):
                key = f"{agent_dir.name}/{task_file.name}"
                if key in state:
                    del state[key]
                    print(f"Cleared state: {key}")
    
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)

print("State file updated")
PYTHON_EOF

# Restart unified task executor (replaced task-watcher as of 2026-03-22)
echo "[$(date -Iseconds)] Restarting task executor..."
launchctl kickstart -k "gui/$(id -u)/com.kurultai.task-executor" 2>/dev/null || true

echo "[$(date -Iseconds)] Task executor restarted. Pending tasks will be processed."

# Clean up
rmdir "$PENDING_DIR" 2>/dev/null || true

echo "[$(date -Iseconds)] Done."
