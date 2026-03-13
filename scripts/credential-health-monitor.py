#!/usr/bin/env python3
"""
credential-health-monitor.py — Validate all agent API credentials

Checks credentials from models.json AND monitors auth failures in logs.
This dual approach detects:
1. Static credential health (from models.json)
2. Runtime auth failures (from auth-failures.jsonl)

Outputs:
  - logs/credential-alerts.json  (current state)
  - logs/credential-health.log   (append-only history)

Exit codes: 0=all valid, 1=some invalid, 2=all invalid (fleet crisis)
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kurultai_paths import AGENTS_DIR, LOGS_DIR, VALID_AGENTS

# Known providers and their API key patterns
PROVIDER_PATTERNS = {
    "zai-coding": {"prefix": "b64", "name": "Z.AI (fleet default)", "required": True},
    "bailian": {"prefix": "sk-sp", "name": "Alibaba Bailian (jochi/ogedei)", "required": True},
    "moonshot": {"prefix": "sk-kimi", "name": "Moonshot/Kimi", "required": False},
    "openrouter": {"prefix": "sk-or", "name": "OpenRouter", "required": False},
}

# Optional providers that don't require API keys
OPTIONAL_PROVIDERS = {"ollama", "local"}


def read_models_json() -> dict:
    """Read models.json to get configured credentials.

    Returns:
        Dict of provider -> (apiKey, status)
    """
    # models.json is in the scripts directory's parent agent folder
    script_dir = Path(__file__).parent
    models_path = script_dir.parent / "agent" / "models.json"
    if not models_path.exists():
        return {}

    try:
        with open(models_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

    providers = {}
    for provider_name, provider_config in data.get("providers", {}).items():
        api_key = provider_config.get("apiKey", "")
        if api_key and api_key != "not-needed" and not api_key.startswith("OPENROUTER"):
            providers[provider_name] = {
                "token": api_key[:12] + "...",
                "name": PROVIDER_PATTERNS.get(provider_name, {}).get("name", provider_name),
                "hasKey": True,
            }
        else:
            providers[provider_name] = {
                "token": None,
                "name": PROVIDER_PATTERNS.get(provider_name, {}).get("name", provider_name),
                "hasKey": False,
            }

    return providers


def get_recent_auth_failures(minutes: int = 60) -> dict:
    """Count recent auth failures from logs.

    Returns:
        Dict of agent -> failure_count
    """
    auth_log = LOGS_DIR / "auth-failures.jsonl"
    if not auth_log.exists():
        return {}

    cutoff = datetime.now().astimezone() - timedelta(minutes=minutes)
    failures = {}

    try:
        with open(auth_log) as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    timestamp_str = entry.get("timestamp", "")
                    # Parse ISO timestamp, ensuring timezone-aware result
                    try:
                        # Replace Z with +00:00 for UTC timestamps
                        ts_for_parse = timestamp_str.replace("Z", "+00:00")
                        timestamp = datetime.fromisoformat(ts_for_parse)
                        # Ensure timezone-aware (assume UTC if no tzinfo)
                        if timestamp.tzinfo is None:
                            timestamp = timestamp.replace(tzinfo=timezone.utc)
                    except ValueError:
                        # Fallback for different formats
                        continue

                    if timestamp >= cutoff:
                        agent = entry.get("agent", "unknown")
                        failures[agent] = failures.get(agent, 0) + 1
                except (json.JSONDecodeError, ValueError):
                    continue
    except IOError:
        pass

    return failures


def check_all_providers() -> dict:
    """Check credentials for all providers and recent auth failures.

    Returns:
        Dict with provider status, recent failures, and fleet-wide summary
    """
    providers = read_models_json()
    recent_failures = get_recent_auth_failures(minutes=60)

    # Map agents to their likely provider based on auth failures
    agent_provider_map = {
        "jochi": "bailian",
        "ogedei": "bailian",
    }
    fleet_default = "zai-coding"

    results = {}
    for provider, info in providers.items():
        status = "valid" if info["hasKey"] else "missing"
        results[provider] = {
            "name": info["name"],
            "token": info.get("token"),
            "status": status,
        }

        # Add recent failure context
        affected_agents = []
        for agent, provider_name in agent_provider_map.items():
            if provider_name == provider:
                affected_agents.append(agent)
        if provider == fleet_default:
            affected_agents = [a for a in VALID_AGENTS if a not in agent_provider_map]

        agent_failures = sum(recent_failures.get(a, 0) for a in affected_agents)
        if agent_failures > 0:
            results[provider]["recent_failures"] = agent_failures
            results[provider]["status"] = "degraded"

    # Summary counts (only count required providers)
    def is_required_provider(provider_name: str) -> bool:
        """Check if a provider is required for fleet operation."""
        if provider_name in OPTIONAL_PROVIDERS:
            return False
        # Check PROVIDER_PATTERNS for required flag
        pattern = PROVIDER_PATTERNS.get(provider_name, {})
        return pattern.get("required", True)  # Default to True if unknown

    required_providers = {k: v for k, v in results.items()
                          if is_required_provider(k)}
    total = len(required_providers)
    valid = sum(1 for r in required_providers.values() if r["status"] == "valid")
    degraded = sum(1 for r in required_providers.values() if r["status"] == "degraded")
    missing = sum(1 for r in required_providers.values() if r["status"] == "missing")

    fleet_health = "healthy"
    if valid == 0:
        fleet_health = "crisis"
    elif degraded > 0 or missing > 0:
        fleet_health = "degraded"

    return {
        "timestamp": datetime.now().isoformat(),
        "fleet_health": fleet_health,
        "summary": {
            "total": total,
            "valid": valid,
            "degraded": degraded,
            "missing": missing,
            "recent_auth_failures": sum(recent_failures.values()),
        },
        "providers": results,
        "recent_agent_failures": recent_failures,
    }


def main():
    result = check_all_providers()

    # Write current state
    alerts_path = LOGS_DIR / "credential-alerts.json"
    with open(alerts_path, "w") as f:
        json.dump(result, f, indent=2)

    # Append to history log
    log_path = LOGS_DIR / "credential-health.log"
    with open(log_path, "a") as f:
        summary = result["summary"]
        f.write(
            f"[{result['timestamp']}] "
            f"fleet={result['fleet_health']} "
            f"valid={summary['valid']} "
            f"degraded={summary['degraded']} "
            f"missing={summary['missing']} "
            f"auth_failures_1h={summary['recent_auth_failures']}\n"
        )

    # Console output for tick watchdog
    print(json.dumps(result))

    # Exit code for monitoring
    if result["fleet_health"] == "crisis":
        sys.exit(2)
    elif result["fleet_health"] == "degraded":
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
