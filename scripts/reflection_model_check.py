#!/usr/bin/env python3
"""
Reflection Model Consistency Check

Quick verification that agent's session model matches configured model.
Runs during reflection to catch drift early. Auto-clears empty sessions.

Usage:
    python3 reflection_model_check.py --agent chagatai
    python3 reflection_model_check.py --all
"""

import argparse
import json
import sys
from pathlib import Path

BASE = Path.home() / ".openclaw/agents"

# All valid models across the multi-tier fallback chain (Claude + Z.AI + Alibaba)
# Source: memory/model-fixes.md and claude-agent wrapper
VALID_MODELS = {
    # Anthropic (primary/Tier 0)
    "claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5",
    # Z.AI (Tier 1 fallback) - intentional, not drift!
    "glm-5", "kimi-k2.5", "qkimi-k2.5",
    # Alibaba (Tier 2 fallback)
    "qwen3.5-plus",
}

# Legacy: deprecated name, use VALID_MODELS now
VALID_CLAUDE_MODELS = VALID_MODELS

def check_agent(agent):
    """Check agent for session drift. Returns (status, message, action_taken)."""
    # Check settings.json for configured model
    settings_file = BASE / agent / ".claude" / "settings.json"
    config_model = "claude-opus-4-6"  # default
    
    if settings_file.exists():
        try:
            with open(settings_file) as f:
                settings = json.load(f)
            config_model = settings.get("env", {}).get("ANTHROPIC_MODEL", config_model)
        except Exception:
            pass
    
    # Check sessions.json
    session_file = BASE / agent / "sessions" / "sessions.json"
    
    if not session_file.exists():
        return "ok", f"No sessions file", None
    
    try:
        with open(session_file) as f:
            sessions = json.load(f)
    except Exception:
        return "ok", f"Invalid sessions JSON (will recreate)", None
    
    # Empty session file is OK - next spawn will use correct model
    if not sessions or sessions == {}:
        return "ok", f"Session empty, will use {config_model}", None
    
    # Get session model from nested structure
    session_model = None
    session_provider = None
    
    for session_id, session_data in sessions.items():
        # Check for model in systemPromptReport
        if "systemPromptReport" in session_data:
            session_model = session_data["systemPromptReport"].get("model")
            session_provider = session_data["systemPromptReport"].get("provider")
        elif "model" in session_data:
            session_model = session_data.get("model")
            session_provider = session_data.get("modelProvider", session_data.get("provider"))
        
        if session_model:
            break
    
    if not session_model:
        return "ok", f"No model in session, will use {config_model}", None

    # Normalize session model (extract base model if provider prefixed)
    session_model_normalized = session_model
    if "/" in session_model:
        session_model_normalized = session_model.split("/")[-1]

    # Check if session model is in the valid fallback chain
    if session_model_normalized in VALID_MODELS:
        # Valid model - no drift
        if session_model_normalized != config_model:
            return "ok", f"Fallback active: {session_model_normalized} (config: {config_model})", None
        return "ok", f"Model OK: {session_model_normalized}", None

    # Unknown/invalid model - this is actual drift
    try:
        session_file.write_text("{}")
        return "fixed", f"Cleared unknown model {session_model}, will use {config_model}", "cleared"
    except Exception:
        return "drift", f"Unknown model {session_model} (manual fix needed)", None
    
    return "ok", f"Model OK: {session_model}", None


def main():
    parser = argparse.ArgumentParser(description="Quick model check for reflection")
    parser.add_argument("--agent", help="Check specific agent")
    parser.add_argument("--all", action="store_true", help="Check all agents")
    parser.add_argument("--quiet", action="store_true", help="Only output issues")
    args = parser.parse_args()
    
    if args.agent:
        agents = [args.agent]
    else:
        agents = ["temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"]
    
    issues = []
    fixed = []
    
    for agent in agents:
        status, message, action = check_agent(agent)
        
        if status == "drift":
            issues.append(f"⚠️ {agent}: {message}")
        elif status == "fixed":
            fixed.append(f"✓ {agent}: {message}")
        elif not args.quiet:
            print(f"✓ {agent}: {message}", file=sys.stderr)
    
    # Report fixes
    if fixed and not args.quiet:
        print("\n=== AUTO-FIXED ===", file=sys.stderr)
        for f in fixed:
            print(f, file=sys.stderr)
    
    # Report issues
    if issues:
        print("\n=== ISSUES REQUIRING ATTENTION ===", file=sys.stderr)
        for i in issues:
            print(i, file=sys.stderr)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
