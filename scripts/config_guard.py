#!/usr/bin/env python3
"""
PreToolUse hook — blocks agents from modifying config files.
Only the dashboard server (which doesn't use Claude Code hooks) can modify these.
"""
import json
import sys
import os

PROTECTED_FILES = [
    "settings.json",     # .claude/settings.json per agent
    "kurultai.json",     # OpenClaw agent config
    "provider.env",      # LLM credentials
    "config.json",       # agent config.json
    "mode.json",         # dispatch mode
]

PROTECTED_PATHS = [
    ".claude/settings.json",
    ".openclaw/kurultai.json",
    ".openclaw/claude/settings.json",
    ".openclaw/claude/settings.backup.json",
    ".openclaw/claude/mode.json",
    ".openclaw/credentials/provider.env",
]

def is_protected(filepath):
    if not filepath:
        return False
    basename = os.path.basename(filepath)
    if basename in PROTECTED_FILES:
        for ppath in PROTECTED_PATHS:
            if ppath in filepath:
                return True
    return False

def check_bash_command(command):
    """Check if a bash command writes to protected files."""
    if not command:
        return False
    danger_patterns = [
        "settings.json", "kurultai.json", "provider.env",
        "mode.json", "config.json"
    ]
    write_indicators = [">", ">>", "tee ", "mv ", "cp ", "sed -i", "chmod "]
    for pattern in danger_patterns:
        if pattern in command:
            for indicator in write_indicators:
                if indicator in command:
                    return True
    return False

def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        print("{}")
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    # Check Write and Edit tools
    if tool_name in ("Write", "Edit"):
        filepath = tool_input.get("file_path", "")
        if is_protected(filepath):
            print(json.dumps({
                "decision": "block",
                "reason": f"CONFIG LOCKED: {os.path.basename(filepath)} is managed by the dashboard (https://the.kurult.ai). Agents cannot modify configuration files directly."
            }))
            sys.exit(0)

    # Check Bash tool for commands that write to config files
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        if check_bash_command(command):
            print(json.dumps({
                "decision": "block",
                "reason": "CONFIG LOCKED: This command appears to modify a protected configuration file. Configuration is managed by the dashboard (https://the.kurult.ai)."
            }))
            sys.exit(0)

    # Allow everything else
    print("{}")
    sys.exit(0)

if __name__ == "__main__":
    main()
