#!/usr/bin/env python3
"""
Configuration validation for the Kurultai routing system.

Validates consistency between:
- VALID_AGENTS (from kurultai_paths.py)
- DOMAIN_AGENT_COMPATIBILITY (from task_intake.py)

This should be called at import time in task_intake.py to catch
configuration drift before it causes production routing issues.
"""

import sys
from pathlib import Path

# Add scripts directory to path for imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    from kurultai_paths import VALID_AGENTS
    from task_intake import DOMAIN_AGENT_COMPATIBILITY
except ImportError as e:
    print(f"ERROR: Failed to import configuration: {e}")
    sys.exit(1)


def validate_routing_config() -> list[str]:
    """
    Validate routing configuration consistency.

    Returns:
        List of error messages (empty if validation passes)
    """
    errors = []

    # Check 1: All agents in DOMAIN_AGENT_COMPATIBILITY must exist in VALID_AGENTS
    for domain, agents in DOMAIN_AGENT_COMPATIBILITY.items():
        for agent in agents:
            if agent not in VALID_AGENTS:
                errors.append(
                    f"Domain '{domain}' lists invalid agent '{agent}' "
                    f"not found in VALID_AGENTS"
                )

    # Check 2: Each domain should have at least one valid agent
    for domain, agents in DOMAIN_AGENT_COMPATIBILITY.items():
        if not agents:
            errors.append(f"Domain '{domain}' has no agents configured")
        else:
            # Verify at least one agent is valid
            valid_agents = [a for a in agents if a in VALID_AGENTS]
            if not valid_agents:
                errors.append(
                    f"Domain '{domain}' has no valid agents "
                    f"(configured: {agents})"
                )

    # Check 3: Warn about agents in VALID_AGENTS not used in any domain
    used_agents = set()
    for agents in DOMAIN_AGENT_COMPATIBILITY.values():
        used_agents.update(agents)

    unused_agents = VALID_AGENTS - used_agents
    if unused_agents:
        # This is a warning, not an error
        print(
            f"WARNING: Agents not used in any domain: {sorted(unused_agents)}. "
            "This may be intentional."
        )

    return errors


def main() -> int:
    """Run validation and exit with appropriate code."""
    errors = validate_routing_config()

    if errors:
        print("CONFIGURATION VALIDATION FAILED")
        print("=" * 60)
        for error in errors:
            print(f"  ✗ {error}")
        print("=" * 60)
        return 1

    print("CONFIGURATION VALIDATION PASSED")
    print("=" * 60)
    print("  All agents in DOMAIN_AGENT_COMPATIBILITY are valid")
    print("  All domains have at least one valid agent")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
