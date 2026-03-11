#!/usr/bin/env python3
"""
get_model.py - Get the LLM model for an agent or the default model.

Usage:
    python3 get_model.py --agent kublai
    python3 get_model.py --agent temujin
    python3 get_model.py --default  # Get default model from main agent

Returns the model name (e.g., "qwen3.5-plus", "claude-sonnet-4-6")
"""

import json
import os
import sys
from pathlib import Path

OPENCLAW_DIR = Path.home() / ".openclaw"
AGENTS_DIR = OPENCLAW_DIR / "agents"


def get_agent_model(agent: str) -> str:
    """Get the model for a specific agent from .claude/settings.json."""
    settings_file = AGENTS_DIR / agent / ".claude" / "settings.json"
    if not settings_file.exists():
        return "unknown"

    try:
        with open(settings_file) as f:
            config = json.load(f)

        # Check ANTHROPIC_MODEL in env
        if "env" in config and "ANTHROPIC_MODEL" in config["env"]:
            return config["env"]["ANTHROPIC_MODEL"]

        # Check top-level model key
        if "model" in config:
            return config["model"]

        return "unknown"
    except (json.JSONDecodeError, IOError):
        return "unknown"


def get_default_model() -> str:
    """Get the default model from the main agent."""
    return get_agent_model("main")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Get LLM model for an agent")
    parser.add_argument("--agent", help="Agent name (e.g., kublai, temujin)")
    parser.add_argument("--default", action="store_true", help="Get default model from main agent")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.agent:
        model = get_agent_model(args.agent)
    elif args.default:
        model = get_default_model()
    else:
        # Default to main agent
        model = get_default_model()

    if args.json:
        print(json.dumps({"model": model, "agent": args.agent or "main"}))
    else:
        print(model)


if __name__ == "__main__":
    main()
