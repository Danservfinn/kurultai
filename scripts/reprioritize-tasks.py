#!/usr/bin/env python3
"""
Reprioritize tasks: calendar tasks -> HIGH, everything else -> NORMAL
"""

import os
import re
from pathlib import Path

AGENTS_DIR = Path(os.path.expanduser("~/.openclaw/agents"))

CALENDAR_KEYWORDS = ["calendar", "signal calendar", "event system", "neo4j calendar"]

def is_calendar_task(content: str) -> bool:
    """Check if task is calendar-related."""
    content_lower = content.lower()
    return any(kw in content_lower for kw in CALENDAR_KEYWORDS)

def update_priority(filepath: Path, new_priority: str) -> bool:
    """Update priority in YAML frontmatter. Returns True if changed."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Find priority line in frontmatter
    match = re.search(r'^priority:\s*(\w+)', content, re.MULTILINE)
    if not match:
        print(f"  SKIP: No priority found in {filepath.name}")
        return False
    
    current_priority = match.group(1)
    if current_priority == new_priority:
        print(f"  SKIP: Already {new_priority} - {filepath.name}")
        return False
    
    # Replace priority
    new_content = re.sub(
        r'^priority:\s*\w+',
        f'priority: {new_priority}',
        content,
        count=1,
        flags=re.MULTILINE
    )
    
    with open(filepath, 'w') as f:
        f.write(new_content)
    
    print(f"  UPDATED: {current_priority} -> {new_priority} : {filepath.name}")
    return True

def main():
    calendar_count = 0
    normal_count = 0
    
    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir():
            continue
        
        tasks_dir = agent_dir / "tasks"
        if not tasks_dir.exists():
            continue
        
        # Skip archived
        archived_dir = tasks_dir / "archived-20260303"
        
        for task_file in tasks_dir.glob("*.md"):
            # Skip archived, done, executing
            if "archived" in str(task_file):
                continue
            if task_file.name.endswith(".done.md"):
                continue
            if task_file.name.endswith(".executing.md"):
                continue
            
            with open(task_file, 'r') as f:
                content = f.read()
            
            if is_calendar_task(content):
                # Keep/set as HIGH
                if update_priority(task_file, "high"):
                    calendar_count += 1
            else:
                # Set to NORMAL
                if update_priority(task_file, "normal"):
                    normal_count += 1
    
    print(f"\nDone! Calendar tasks: {calendar_count}, Normal tasks: {normal_count}")

if __name__ == "__main__":
    main()
