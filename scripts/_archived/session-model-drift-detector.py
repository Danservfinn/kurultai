#!/usr/bin/env python3
"""
Session Model Drift Detector

Checks active agent sessions against their configured models.
Reports drift when session model != config model.

Usage: python3 session-model-drift-detector.py
Output: JSON report of drifted sessions
"""

import json
import os
import sys
from pathlib import Path

# Configuration
AGENTS_BASE = Path("/Users/kublai/.openclaw/agents")
MAIN_AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"]


def get_config_path(agent: str) -> Path:
    return AGENTS_BASE / agent / "config.json"


def get_sessions_path(agent: str) -> Path:
    return AGENTS_BASE / agent / "sessions" / "sessions.json"

# Valid Claude models
VALID_CLAUDE_MODELS = {
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5"
}


def get_config_model(agent: str) -> str:
    """Get the configured model from agent's config.json."""
    config_file = get_config_path(agent)
    try:
        with open(config_file) as f:
            config = json.load(f)
            return config.get("model", "claude-opus-4-6")  # Default if not set
    except FileNotFoundError:
        return "claude-opus-4-6"  # Default
    except json.JSONDecodeError:
        return "claude-opus-4-6"


def get_session_model(agent: str) -> str:
    """Get the actual model from agent's active session."""
    sessions_file = get_sessions_path(agent)
    try:
        with open(sessions_file) as f:
            sessions = json.load(f)
            if not sessions:
                return None  # No active session

            # Get the most recent session
            latest_id = max(sessions.keys())
            latest_session = sessions[latest_id]

            # Check for model in session metadata
            # Format varies by version - check multiple locations
            if "model" in latest_session:
                return latest_session["model"]
            if "env" in latest_session and "ANTHROPIC_MODEL" in latest_session["env"]:
                return latest_session["env"]["ANTHROPIC_MODEL"]
            return None
    except FileNotFoundError:
        return None  # No session file
    except json.JSONDecodeError:
        return None


def detect_drift() -> dict:
    """Check all agents for session-model drift."""
    results = {
        "drifted": [],
        "clean": [],
        "no_session": [],
        "errors": []
    }

    for agent in MAIN_AGENTS:
        agent_path = AGENTS_BASE / agent
        if not agent_path.exists():
            continue

        config_model = get_config_model(agent)
        session_model = get_session_model(agent)

        if session_model is None:
            results["no_session"].append({
                "agent": agent,
                "config_model": config_model
            })
            continue

        if config_model != session_model:
            results["drifted"].append({
                "agent": agent,
                "config_model": config_model,
                "session_model": session_model,
                "severity": "CRITICAL" if session_model not in VALID_CLAUDE_MODELS else "HIGH"
            })
        else:
            results["clean"].append({
                "agent": agent,
                "model": config_model
            })

    return results


def main():
    results = detect_drift()

    # Output JSON for parsing by watchdog
    print(json.dumps(results, indent=2))

    # Exit with error code if drift detected
    if results["drifted"]:
        drifted_count = len(results["drifted"])
        print(f"\nALERT: {drifted_count} agent(s) with session-model drift!", file=sys.stderr)
        for item in results["drifted"]:
            print(f"  - {item['agent']}: {item['session_model']} != {item['config_model']}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"\nOK: All {len(results['clean'])} agents have matching session/config models")
        sys.exit(0)


if __name__ == "__main__":
    main()
