#!/usr/bin/env python3
"""
PostToolUse hook for Claude Code — fires on every Skill tool invocation.
Reads JSON from stdin, extracts skill name + agent, appends to skill-invocations.jsonl.
Registered in ~/.claude/settings.json under hooks.PostToolUse.
"""
import fcntl
import json
import sys
import os
from datetime import datetime
from pathlib import Path


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        print("{}")
        sys.exit(0)

    if data.get("tool_name") != "Skill":
        print("{}")
        sys.exit(0)

    cwd = data.get("cwd", "")
    agent = cwd.rstrip("/").split("/")[-1]
    tool_input = data.get("tool_input", {})
    tool_result = data.get("tool_result", {})

    record = {
        "ts": datetime.now().isoformat(),
        "session_id": data.get("session_id", ""),
        "agent": agent,
        "skill": tool_input.get("skill", ""),
        "args_preview": str(tool_input.get("args", ""))[:500],
        "success": tool_result.get("success", False),
        "cwd": cwd,
        "executor": "claude-code",
    }

    out = Path.home() / ".openclaw/tasks/skill-invocations.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)

    # Use exclusive file locking to prevent corruption from concurrent hooks
    with open(out, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(json.dumps(record) + "\n")
            f.flush()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

    print("{}")  # required: empty JSON response to Claude Code
    sys.exit(0)


if __name__ == "__main__":
    main()
