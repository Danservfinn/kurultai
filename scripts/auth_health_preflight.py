#!/usr/bin/env python3
"""
Auth Health Preflight — Check credentials for all agents.

Implements O006: Auth Health Gap Response
- Checks ANTHROPIC_AUTH_TOKEN validity for each agent
- Returns JSON with per-agent status and actionable remediation
- Creates ogedei task if critical failures detected

Usage:
    python3 auth_health_preflight.py [--agent kublai] [--json]
    python3 auth_health_preflight.py --fix  # Run credential health monitor

Exit codes:
    0: All agents healthy
    1: One or more agents have auth issues
    2: Error running checks
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Configuration
AGENTS_DIR = Path.home() / ".openclaw" / "agents"
VALID_AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"]
LOG_DIR = AGENTS_DIR / "main" / "logs"
AUTH_FAILURE_LOG = LOG_DIR / "auth-failures.jsonl"

# Timeout for auth check (seconds) — increased to match agent-task-handler.py
# FIX (2026-03-12): Increased from 15s to 30s because claude-agent takes ~24s to complete
AUTH_TIMEOUT = 30


def log_auth_failure(agent: str, reason: str):
    """Log auth failure for monitoring."""
    AUTH_FAILURE_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "agent": agent,
        "reason": reason,
        "source": "auth_health_preflight"
    }
    with open(AUTH_FAILURE_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def check_agent_auth(agent: str) -> dict:
    """Check if agent can authenticate via claude-agent.

    Returns dict with keys: healthy, reason, token_present, token_length

    IMPORTANT: The live test (claude-agent execution) is the definitive check.
    Static checks of settings.json are for diagnostics only, since tokens may be
    in environment variables or managed by external auth systems.
    """
    # Static check: try to read token from settings.json for diagnostics
    settings_path = AGENTS_DIR / agent / ".claude" / "settings.json"
    token_from_settings = None
    settings_status = "OK"

    try:
        with open(settings_path, "r") as f:
            settings = json.load(f)
        token_from_settings = settings.get("env", {}).get("ANTHROPIC_AUTH_TOKEN", "")
        if not token_from_settings:
            token_from_settings = settings.get("ANTHROPIC_AUTH_TOKEN", "")
        if not token_from_settings:
            settings_status = "No token in settings.json (may be in env)"
    except FileNotFoundError:
        settings_status = "settings.json not found"
    except json.JSONDecodeError:
        settings_status = "settings.json invalid JSON"

    token_length = len(token_from_settings) if token_from_settings else 0

    # Live test: Can claude-agent complete a minimal request? (DEFINITIVE CHECK)
    try:
        result = subprocess.run(
            ["claude-agent", "--agent", agent, "--prompt", "Respond with exactly: OK"],
            capture_output=True,
            timeout=AUTH_TIMEOUT,
        )
        if result.returncode == 0 and b"OK" in result.stdout:
            return {
                "agent": agent,
                "healthy": True,
                "reason": "OK" if settings_status == "OK" else f"OK (live test passed; {settings_status})",
                "token_present": bool(token_from_settings),
                "token_length": token_length
            }
        else:
            return {
                "agent": agent,
                "healthy": False,
                "reason": f"claude-agent failed (rc={result.returncode})",
                "token_present": bool(token_from_settings),
                "token_length": token_length
            }
    except subprocess.TimeoutExpired:
        return {
            "agent": agent,
            "healthy": False,
            "reason": f"claude-agent timeout (> {AUTH_TIMEOUT}s)",
            "token_present": bool(token_from_settings),
            "token_length": token_length
        }
    except FileNotFoundError:
        return {
            "agent": agent,
            "healthy": False,
            "reason": "claude-agent not found",
            "token_present": bool(token_from_settings),
            "token_length": token_length
        }


def check_all_agents() -> dict:
    """Check auth health for all agents.

    Returns dict with:
        - all_healthy: bool
        - agents: dict of agent -> status
        - failed_agents: list of agent names
        - timestamp: ISO timestamp
    """
    results = {}
    failed_agents = []

    for agent in VALID_AGENTS:
        if not (AGENTS_DIR / agent).exists():
            continue
        status = check_agent_auth(agent)
        results[agent] = status
        if not status["healthy"]:
            failed_agents.append(agent)
            log_auth_failure(agent, status["reason"])

    return {
        "timestamp": datetime.now().isoformat(),
        "all_healthy": len(failed_agents) == 0,
        "agents": results,
        "failed_agents": failed_agents,
        "total_checked": len(results),
        "healthy_count": sum(1 for s in results.values() if s["healthy"])
    }


def create_ogedei_task(failed_agents: list) -> bool:
    """Create an ogedei task for auth failures.

    CIRCULAR CASCADE PREVENTION (2026-03-12): If ogedei is already failing,
    route to jochi instead to break the circular failure cascade.

    Returns True if task created successfully.
    """
    if not failed_agents:
        return False

    # CIRCULAR CASCADE PREVENTION: Check if ogedei is failing
    _OGEDEI_FAILURE_THRESHOLD = 0.5
    _target_agent = "ogedei"
    _watchdog_state = LOG_DIR / "ogedei-watchdog-state.json"

    try:
        if _watchdog_state.exists():
            with open(_watchdog_state) as f:
                state = json.load(f)
            flags = state.get("agent_failure_flags", {})
            ogedei_failure = flags.get("ogedei", 0.0)
            if ogedei_failure >= _OGEDEI_FAILURE_THRESHOLD:
                print(f"CIRCULAR CASCADE PREVENTION: ogedei failure flag={ogedei_failure:.2f} >= {_OGEDEI_FAILURE_THRESHOLD}")
                print(f"  Routing auth crisis task to jochi instead of ogedei to break cascade")
                _target_agent = "jochi"
    except Exception:
        pass  # Default to ogedei if state read fails

    task_intake = Path(__file__).parent / "task_intake.py"
    if not task_intake.exists():
        print("ERROR: task_intake.py not found", file=sys.stderr)
        return False

    body = f"""## Auth Health Alert — {len(failed_agents)} agent(s) failing

**Failed Agents:** {', '.join(failed_agents)}

**Issue:** Agents are failing authentication preflight checks.

**Action Required:**
1. Check credentials in ~/.openclaw/agents/<agent>/.claude/settings.json
2. Verify ANTHROPIC_AUTH_TOKEN is valid and not expired
3. Run `claude-agent --agent <agent> --prompt "OK"` to verify

**Timestamp:** {datetime.now().isoformat()}
"""

    try:
        result = subprocess.run(
            [
                sys.executable,
                str(task_intake),
                "--title", f"Auth Crisis: {len(failed_agents)} agent(s) failing",
                "--body", body,
                "--agent", _target_agent,
                "--priority", "high",
                "--source", "auth_health_preflight"
            ],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0 and "CREATED:" in result.stdout
    except Exception as e:
        print(f"ERROR: Failed to create task: {e}", file=sys.stderr)
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Auth health preflight check")
    parser.add_argument("--agent", help="Check specific agent only")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    parser.add_argument("--fix", action="store_true", help="Run full check and create task if needed")
    args = parser.parse_args()

    if args.agent:
        # Single agent check
        status = check_agent_auth(args.agent)
        if args.json:
            print(json.dumps(status, indent=2))
        else:
            print(f"{args.agent}: {'HEALTHY' if status['healthy'] else 'FAILED'} — {status['reason']}")
        sys.exit(0 if status["healthy"] else 1)

    # Full check
    result = check_all_agents()

    if args.json:
        print(json.dumps(result, indent=2))

    # O006: Create task if auth failures detected
    if args.fix and result["failed_agents"]:
        create_ogedei_task(result["failed_agents"])

    # Exit code reflects overall health
    sys.exit(0 if result["all_healthy"] else 1)


if __name__ == "__main__":
    main()
