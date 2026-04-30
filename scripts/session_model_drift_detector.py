#!/usr/bin/env python3
"""
Session Model Drift Detector

Detects when an agent's active session is using a different model than
its configured model. Session drift occurs when sessions persist with
old models after config changes.

Can be run standalone or imported for reflection pipeline integration.

Usage:
    python3 session_model_drift_detector.py --agent mongke
    python3 session_model_drift_detector.py --all
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, Path(__file__).parent)
from agents_config import AGENT_MODELS

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

# Unapproved providers that should trigger alerts (provider names, not model names)
# These are checked against the provider field, not the model name
UNAPPROVED_PROVIDERS = {"bailian", "dashscope", "deepseek", "unknown"}


def get_session_model(agent):
    """Extract the model from the active session file.

    Returns: (model_string, provider_string) or (None, None) if no active session
    """
    session_file = BASE / agent / "sessions" / "sessions.json"
    if not session_file.exists():
        return None, None

    try:
        with open(session_file) as f:
            sessions = json.load(f)

        if not sessions:
            return None, None

        # Get the first (active) session
        for session_id, session_data in sessions.items():
            if session_data.get("model"):
                model = session_data.get("model", "unknown")
                provider = session_data.get("modelProvider", session_data.get("provider", "unknown"))
                return model, provider

        return None, None
    except Exception:
        return None, None


def get_config_model(agent):
    """Get the expected model from agent config.

    Checks in order:
    1. config.json `model` key
    2. settings.json ANTHROPIC_MODEL env var
    3. AGENT_MODELS from agents_config.py (fallback)
    """
    # Check config.json
    config_file = BASE / agent / "config.json"
    if config_file.exists():
        try:
            with open(config_file) as f:
                config = json.load(f)
                if config.get("model"):
                    return config["model"]
        except Exception:
            pass

    # Check settings.json
    settings_file = BASE / agent / ".claude" / "settings.json"
    if settings_file.exists():
        try:
            with open(settings_file) as f:
                settings = json.load(f)
                env = settings.get("env", {})
                if env.get("ANTHROPIC_MODEL"):
                    return env["ANTHROPIC_MODEL"]
        except Exception:
            pass

    # Fallback to agents_config.py
    return AGENT_MODELS.get(agent, "claude-opus-4-6")


def check_agent(agent):
    """Check a single agent for session-model drift.

    Returns: dict with drift status and details
    """
    session_model, provider = get_session_model(agent)
    config_model = get_config_model(agent)

    if not session_model:
        return {
            "agent": agent,
            "status": "no_session",
            "session_model": None,
            "config_model": config_model,
            "drift": False
        }

    # Normalize for comparison (handle provider prefixes like "zai-coding/glm-5")
    session_norm = session_model.lower().strip()
    config_norm = config_model.lower().strip()

    # Extract base model if provider-prefixed
    if "/" in session_norm:
        session_base = session_norm.split("/")[-1]
    else:
        session_base = session_norm

    # Check if session model is in the valid fallback chain
    is_valid = session_base in VALID_MODELS

    # Only flag provider as unapproved if the model is NOT in our valid list
    # (e.g., bailian is fine for kimi-k2.5, but not for unknown models)
    provider_norm = (provider or "unknown").lower()
    is_unapproved_provider = (not is_valid) and (provider_norm in UNAPPROVED_PROVIDERS)

    # Drift = using invalid model (provider only matters if model is unknown)
    is_drift = not is_valid

    return {
        "agent": agent,
        "status": "drift" if is_drift else "ok",
        "session_model": session_model,
        "session_provider": provider,
        "config_model": config_model,
        "drift": is_drift,
        "is_unapproved_provider": is_unapproved_provider,
        "is_valid": is_valid,
        "fix_command": f"echo '{{}}' > {BASE}/{agent}/sessions/sessions.json"
    }


def format_report(results):
    """Format drift detection results as markdown."""
    lines = ["## Session Model Drift Detection\n"]

    drift_count = sum(1 for r in results if r["drift"])
    unapproved_count = sum(1 for r in results if r.get("is_unapproved_provider"))

    if drift_count == 0:
        lines.append("✅ All agents using correct models.\n")
        return "\n".join(lines)

    lines.append(f"⚠️ Found {drift_count} agent(s) with session drift.\n")

    for r in results:
        if r["drift"]:
            agent = r["agent"]
            session = r["session_model"]
            config = r["config_model"]
            provider = r.get("session_provider", "unknown")

            if r.get("is_unapproved_provider"):
                lines.append(f"### 🚨 {agent} — UNAPPROVED PROVIDER DETECTED")
                lines.append(f"- **Session model**: `{session}` (provider: `{provider}`)")
                lines.append(f"- **Config model**: `{config}`")
                lines.append(f"- **Fix**: Kill session with: `{r['fix_command']}`")
            else:
                lines.append(f"### ⚠️ {agent} — Model Mismatch")
                lines.append(f"- **Session model**: `{session}`")
                lines.append(f"- **Config model**: `{config}`")
                lines.append(f"- **Fix**: Kill session with: `{r['fix_command']}`")
            lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Detect session-model drift")
    parser.add_argument("--agent", help="Check specific agent")
    parser.add_argument("--all", action="store_true", help="Check all agents")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--fix", action="store_true", help="Auto-fix by killing drifted sessions")
    args = parser.parse_args()

    agents = []
    if args.agent:
        agents = [args.agent]
    elif args.all:
        agents = ["temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"]
    else:
        # Default: check all
        agents = ["temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"]

    results = []
    for agent in agents:
        try:
            result = check_agent(agent)
            results.append(result)

            # Auto-fix if requested
            if args.fix and result["drift"]:
                session_file = BASE / agent / "sessions" / "sessions.json"
                session_file.write_text("{}")
                print(f"Fixed {agent}: killed drifted session", file=sys.stderr)
        except Exception as e:
            print(f"Error checking {agent}: {e}", file=sys.stderr)

    # Re-check after fixes to get accurate final state
    if args.fix:
        results = []
        for agent in agents:
            try:
                result = check_agent(agent)
                results.append(result)
            except Exception as e:
                print(f"Error re-checking {agent}: {e}", file=sys.stderr)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(format_report(results))

    # Exit code reflects drift status
    return 1 if any(r["drift"] for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
