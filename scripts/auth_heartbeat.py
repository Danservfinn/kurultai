#!/usr/bin/env python3
"""
Auth Heartbeat — Credential health status for all agents.

Creates a heartbeat file similar to last-heartbeat.json but for auth status.
Task-watcher can check this BEFORE dispatching tasks to prevent auth failures.

Usage:
    python auth_heartbeat.py              # Check all agents
    python auth_heartbeat.py --agent jochi # Check specific agent
    python auth_heartbeat.py --force      # Force recheck even if recent

Output:
    Writes logs/auth-heartbeat.json with last-success timestamps for each agent
    Format: {"agent": {"last_success": "2026-03-11T23:00:00", "status": "ok|fail"}}
"""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Configuration
AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]
AGENTS_DIR = Path("/Users/kublai/.openclaw/agents")
LOGS_DIR = AGENTS_DIR / "main" / "logs"
HEARTBEAT_FILE = LOGS_DIR / "auth-heartbeat.json"
CLAUDE_AGENT_BIN = Path("/Users/kublai/.local/bin/claude-agent")

# Auth thresholds
AUTH_TIMEOUT = 30  # Seconds to wait for auth check (increased from 15s due to Exit 124 timeouts)
AUTH_STALE_SECONDS = 300  # 5 minutes - auth is stale if older than this

# Provider mapping (must match hourly_reflection.sh)
# All agents -> Z.AI (Tier 1) - Alibaba (sk-sp-*) timing out with Exit 124
PROVIDER_MAP = {
    "jochi": "zai",  # Fixed 2026-03-12: was alibaba, timeout Exit 124
    "ogedei": "zai",  # Fixed 2026-03-12: was alibaba, proactively moved to zai for reliability
    "kublai": "zai",
    "temujin": "zai",
    "mongke": "zai",
    "chagatai": "zai",
}


def load_heartbeat() -> dict:
    """Load existing auth heartbeat data."""
    if HEARTBEAT_FILE.exists():
        try:
            with open(HEARTBEAT_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_heartbeat(data: dict) -> None:
    """Save auth heartbeat data atomically."""
    HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = HEARTBEAT_FILE.with_suffix(".tmp")
    with open(tmp_file, "w") as f:
        json.dump(data, f, indent=2)
    tmp_file.replace(HEARTBEAT_FILE)


def check_agent_auth(agent: str) -> dict:
    """Check if an agent can authenticate.

    Returns dict with:
        - status: "ok" | "fail"
        - last_success: ISO timestamp
        - error: error message if failed
    """
    agent_dir = AGENTS_DIR / agent
    if not agent_dir.is_dir():
        return {
            "status": "fail",
            "last_success": None,
            "error": f"Agent directory not found: {agent_dir}"
        }

    provider = PROVIDER_MAP.get(agent, "zai")

    # Quick test: Can claude-agent complete a minimal request?
    # We run from the agent's directory to ensure correct context
    try:
        result = subprocess.run(
            [
                "timeout", f"{AUTH_TIMEOUT}s",
                str(CLAUDE_AGENT_BIN),
                "Respond with exactly: OK"
            ],
            cwd=str(agent_dir),
            capture_output=True,
            text=True,
            timeout=AUTH_TIMEOUT + 2,
            env={
                "PATH": subprocess.os.environ["PATH"],
                "HOME": subprocess.os.environ["HOME"],
                "CLAUDE_PROVIDER": provider,
            }
        )

        if result.returncode == 0 and "OK" in result.stdout:
            return {
                "status": "ok",
                "last_success": datetime.now().isoformat(),
                "error": None
            }
        else:
            # Log auth failure for monitoring
            auth_failure_log = LOGS_DIR / "auth-failures.jsonl"
            try:
                with open(auth_failure_log, "a") as af:
                    af.write(f'{{"timestamp": "{datetime.now().isoformat()}", "agent": "{agent}", "label": "auth_heartbeat", "script": "auth_heartbeat.py", "reason": "auth_check_failed"}}\n')
            except Exception:
                pass

            return {
                "status": "fail",
                "last_success": None,
                "error": f"Exit {result.returncode}: {result.stderr[:100] if result.stderr else 'no output'}"
            }

    except subprocess.TimeoutExpired:
        return {
            "status": "fail",
            "last_success": None,
            "error": f"Timeout after {AUTH_TIMEOUT}s"
        }
    except Exception as e:
        return {
            "status": "fail",
            "last_success": None,
            "error": str(e)
        }


def is_agent_healthy(agent: str, heartbeat_data: dict) -> bool:
    """Check if an agent's auth status is healthy (recent success)."""
    if agent not in heartbeat_data:
        return False

    entry = heartbeat_data[agent]
    if entry.get("status") != "ok":
        return False

    last_success = entry.get("last_success")
    if not last_success:
        return False

    try:
        last_success_time = datetime.fromisoformat(last_success)
        age_seconds = (datetime.now() - last_success_time).total_seconds()
        return age_seconds < AUTH_STALE_SECONDS
    except (ValueError, TypeError):
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Check auth health for agents")
    parser.add_argument("--agent", help="Check specific agent only")
    parser.add_argument("--force", action="store_true", help="Force recheck even if recent")
    parser.add_argument("--check-only", action="store_true", help="Only check, don't update")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    args = parser.parse_args()

    # Load existing heartbeat
    heartbeat_data = load_heartbeat()

    # Determine which agents to check
    agents_to_check = [args.agent] if args.agent else AGENTS

    results = {}
    failed_agents = []

    for agent in agents_to_check:
        # Skip if recent and not forced
        if not args.force and is_agent_healthy(agent, heartbeat_data):
            # Still healthy, no need to recheck
            results[agent] = heartbeat_data[agent]
            continue

        # Check auth
        result = check_agent_auth(agent)
        results[agent] = result

        if result["status"] == "fail":
            failed_agents.append(agent)

    # Update heartbeat file (unless check-only)
    if not args.check_only:
        # Merge with existing data
        for agent, result in results.items():
            heartbeat_data[agent] = result

        # Add metadata
        heartbeat_data["_meta"] = {
            "last_check": datetime.now().isoformat(),
            "stale_threshold_seconds": AUTH_STALE_SECONDS,
        }

        save_heartbeat(heartbeat_data)

    # Output results
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for agent, result in results.items():
            status_symbol = "✓" if result["status"] == "ok" else "✗"
            last_success = result.get("last_success", "never")
            print(f"{status_symbol} {agent}: {result['status']} (last: {last_success})")
            if result.get("error"):
                print(f"  Error: {result['error']}")

    # Exit code based on failures
    if failed_agents:
        # Print summary for monitoring
        print(f"\nFAILED: {', '.join(failed_agents)}", file=sys.stderr)
        sys.exit(1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
