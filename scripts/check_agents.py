"""
Agent Operational Tests

Validates that all configured agents are operational and can communicate.

Checks:
    AGENT-001 [CRITICAL]: All 6 agents configured
    AGENT-002 [CRITICAL]: Agent directories exist
    AGENT-003: Agent models configured
    AGENT-004: Agent-to-agent communication enabled
    AGENT-005: Failover configuration valid
    AGENT-006: Default agent specified
    AGENT-007: Agent roles unique
    AGENT-008: Workspace paths valid
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.check_types import CheckResult, CheckCategory, CheckStatus

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for agent checks."""
    # Minimum requirements
    MIN_AGENTS = 6

    # Expected agents
    EXPECTED_AGENT_IDS = ["main", "researcher", "writer", "developer", "analyst", "ops"]

    # Agent roles
    AGENT_ROLES = {
        "main": "coordinator",
        "researcher": "research",
        "writer": "content",
        "developer": "coding",
        "analyst": "analysis",
        "ops": "operations"
    }


class AgentChecker:
    """
    Agent operational checker.

    Validates that all configured agents are properly set up and can communicate.

    Example:
        >>> checker = AgentChecker(config=moltbot_config)
        >>> results = checker.run_all_checks()
        >>> for result in results:
        ...     print(f"{result.check_id}: {result.status}")
    """

    def __init__(self, config: Dict, verbose: bool = False):
        """
        Initialize agent checker.

        Args:
            config: Moltbot configuration dictionary
            verbose: Enable verbose logging
        """
        self.config = config
        self.verbose = verbose

        # Extract agent list
        self.agents = config.get("agents", {}).get("list", [])

    def _run_check(
        self,
        check_id: str,
        description: str,
        critical: bool,
        check_func: callable
    ) -> CheckResult:
        """
        Run a single check.

        Args:
            check_id: Check identifier (e.g., AGENT-001)
            description: Check description
            critical: Whether this is a critical check
            check_func: Function that performs the check

        Returns:
            CheckResult with status and details
        """
        start_time = datetime.now(timezone.utc)

        try:
            result = check_func()
        except Exception as e:
            logger.error(f"Error running {check_id}: {e}")
            result = {
                "status": CheckStatus.FAIL,
                "expected": "Check to complete without error",
                "actual": f"Exception: {str(e)}",
                "output": f"Check failed with exception: {str(e)}",
                "details": {"error": str(e), "error_type": type(e).__name__}
            }

        duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

        return CheckResult(
            check_id=check_id,
            category=CheckCategory.AGENTS,
            description=description,
            critical=critical,
            status=result.get("status", CheckStatus.FAIL),
            expected=result.get("expected", ""),
            actual=result.get("actual", ""),
            output=result.get("output", ""),
            duration_ms=duration_ms,
            details=result.get("details", {})
        )

    def run_all_checks(self) -> List[CheckResult]:
        """Run all agent checks."""
        results = []

        # AGENT-001: All 6 agents configured
        results.append(self._run_check(
            "AGENT-001",
            "All 6 agents configured",
            True,
            self._check_agent_count
        ))

        # AGENT-002: Agent directories exist
        results.append(self._run_check(
            "AGENT-002",
            "Agent directories exist",
            True,
            self._check_agent_directories
        ))

        # AGENT-003: Agent models configured
        results.append(self._run_check(
            "AGENT-003",
            "Agent models configured",
            False,
            self._check_agent_models
        ))

        # AGENT-004: Agent-to-agent communication enabled
        results.append(self._run_check(
            "AGENT-004",
            "Agent-to-agent communication enabled",
            False,
            self._check_agent_communication
        ))

        # AGENT-005: Failover configuration valid
        results.append(self._run_check(
            "AGENT-005",
            "Failover configuration valid",
            False,
            self._check_failover_config
        ))

        # AGENT-006: Default agent specified
        results.append(self._run_check(
            "AGENT-006",
            "Default agent specified",
            False,
            self._check_default_agent
        ))

        # AGENT-007: Agent IDs unique
        results.append(self._run_check(
            "AGENT-007",
            "Agent IDs unique",
            False,
            self._check_unique_ids
        ))

        # AGENT-008: Workspace paths valid
        results.append(self._run_check(
            "AGENT-008",
            "Workspace paths valid",
            False,
            self._check_workspace_paths
        ))

        return results

    # ========================================================================
    # Individual Check Functions
    # ========================================================================

    def _check_agent_count(self) -> Dict[str, Any]:
        """
        AGENT-001 [CRITICAL]: All 6 agents configured

        Validates that at least 6 agents are configured.
        """
        agent_count = len(self.agents)
        min_count = AgentConfig.MIN_AGENTS

        if agent_count >= min_count:
            agent_ids = [a.get("id", "unknown") for a in self.agents]
            return {
                "status": CheckStatus.PASS,
                "expected": f"At least {min_count} agents",
                "actual": f"{agent_count} agents",
                "output": f"PASS: {agent_count} agents configured: {', '.join(agent_ids)}",
                "details": {
                    "agent_count": agent_count,
                    "agent_ids": agent_ids
                }
            }
        else:
            agent_ids = [a.get("id", "unknown") for a in self.agents]
            return {
                "status": CheckStatus.FAIL,
                "expected": f"At least {min_count} agents",
                "actual": f"{agent_count} agents",
                "output": f"FAIL: Only {agent_count} agents configured (need {min_count})",
                "details": {
                    "agent_count": agent_count,
                    "agent_ids": agent_ids,
                    "min_required": min_count
                }
            }

    def _check_agent_directories(self) -> Dict[str, Any]:
        """
        AGENT-002 [CRITICAL]: Agent directories exist

        Validates that agent directories exist in the filesystem.
        """
        existing_dirs = []
        missing_dirs = []

        for agent in self.agents:
            agent_dir = agent.get("agentDir")
            if agent_dir:
                if os.path.exists(agent_dir) and os.path.isdir(agent_dir):
                    existing_dirs.append(agent_dir)
                else:
                    missing_dirs.append(agent_dir)
            else:
                missing_dirs.append(f"{agent.get('id', 'unknown')}: no directory specified")

        if not missing_dirs:
            return {
                "status": CheckStatus.PASS,
                "expected": "All agent directories exist",
                "actual": f"{len(existing_dirs)} directories found",
                "output": f"PASS: All {len(existing_dirs)} agent directories exist",
                "details": {
                    "directories": existing_dirs,
                    "count": len(existing_dirs)
                }
            }
        elif existing_dirs:
            return {
                "status": CheckStatus.WARN,
                "expected": "All agent directories exist",
                "actual": f"{len(existing_dirs)} found, {len(missing_dirs)} missing",
                "output": f"WARN: {len(missing_dirs)} agent directories missing: {missing_dirs}",
                "details": {
                    "existing": existing_dirs,
                    "missing": missing_dirs
                }
            }
        else:
            return {
                "status": CheckStatus.FAIL,
                "expected": "Agent directories exist",
                "actual": "No directories found",
                "output": f"FAIL: No agent directories found",
                "details": {"missing": missing_dirs}
            }

    def _check_agent_models(self) -> Dict[str, Any]:
        """
        AGENT-003: Agent models configured

        Validates that each agent has a model configured.
        """
        default_model = self.config.get("agents", {}).get("defaults", {}).get("model", {}).get("primary")

        agents_with_models = []
        agents_without_models = []

        for agent in self.agents:
            agent_id = agent.get("id", "unknown")
            agent_model = agent.get("model")

            if agent_model:
                agents_with_models.append(f"{agent_id}:{agent_model}")
            elif default_model:
                agents_with_models.append(f"{agent_id}:{default_model} (default)")
            else:
                agents_without_models.append(agent_id)

        if not agents_without_models:
            return {
                "status": CheckStatus.PASS,
                "expected": "All agents have models configured",
                "actual": f"{len(agents_with_models)} agents with models",
                "output": f"PASS: All agents have models configured",
                "details": {
                    "agents": agents_with_models,
                    "default_model": default_model
                }
            }
        else:
            return {
                "status": CheckStatus.WARN,
                "expected": "All agents have models configured",
                "actual": f"{len(agents_without_models)} agents without models",
                "output": f"WARN: Agents without models: {agents_without_models}",
                "details": {
                    "without_models": agents_without_models,
                    "with_models": agents_with_models
                }
            }

    def _check_agent_communication(self) -> Dict[str, Any]:
        """
        AGENT-004: Agent-to-agent communication enabled

        Validates that agent-to-agent communication is enabled.
        """
        agent_to_agent_config = self.config.get("tools", {}).get("agentToAgent", {})
        enabled = agent_to_agent_config.get("enabled", False)
        allow_list = agent_to_agent_config.get("allow", [])

        if enabled:
            if allow_list:
                return {
                    "status": CheckStatus.PASS,
                    "expected": "Agent-to-agent communication enabled",
                    "actual": f"Enabled for {len(allow_list)} agents",
                    "output": f"PASS: Agent-to-agent communication enabled for: {', '.join(allow_list)}",
                    "details": {
                        "enabled": True,
                        "allowed_agents": allow_list
                    }
                }
            else:
                return {
                    "status": CheckStatus.WARN,
                    "expected": "Agent-to-agent communication enabled",
                    "actual": "Enabled but no allow list",
                    "output": "WARN: Agent-to-agent enabled but no agents in allow list",
                    "details": {"enabled": True, "allowed_agents": []}
                }
        else:
            return {
                "status": CheckStatus.WARN,
                "expected": "Agent-to-agent communication enabled",
                "actual": "Disabled",
                "output": "WARN: Agent-to-agent communication is disabled",
                "details": {"enabled": False}
            }

    def _check_failover_config(self) -> Dict[str, Any]:
        """
        AGENT-005: Failover configuration valid

        Validates that failover configuration is correct.
        """
        failover_agents = []
        invalid_failovers = []

        for agent in self.agents:
            agent_id = agent.get("id")
            failover_for = agent.get("failoverFor", [])

            if failover_for:
                # Check that failover targets exist
                agent_ids = [a.get("id") for a in self.agents]
                for target in failover_for:
                    if target in agent_ids:
                        failover_agents.append(f"{agent_id} -> {target}")
                    else:
                        invalid_failovers.append(f"{agent_id} -> {target} (target not found)")

        if failover_agents and not invalid_failovers:
            return {
                "status": CheckStatus.PASS,
                "expected": "Valid failover configuration",
                "actual": f"{len(failover_agents)} failover rules",
                "output": f"PASS: {len(failover_agents)} valid failover rules configured",
                "details": {
                    "failover_rules": failover_agents
                }
            }
        elif invalid_failovers:
            return {
                "status": CheckStatus.WARN,
                "expected": "Valid failover configuration",
                "actual": f"{len(invalid_failovers)} invalid rules",
                "output": f"WARN: Invalid failover targets: {invalid_failovers}",
                "details": {
                    "valid": failover_agents,
                    "invalid": invalid_failovers
                }
            }
        else:
            return {
                "status": CheckStatus.WARN,
                "expected": "Failover configuration",
                "actual": "No failover configured",
                "output": "WARN: No failover configuration found",
                "details": {}
            }

    def _check_default_agent(self) -> Dict[str, Any]:
        """
        AGENT-006: Default agent specified

        Validates that a default agent is configured.
        """
        default_agent = None
        agent_ids = [a.get("id") for a in self.agents]

        # Find agent marked as default
        for agent in self.agents:
            if agent.get("default"):
                default_agent = agent.get("id")
                break

        if default_agent:
            return {
                "status": CheckStatus.PASS,
                "expected": "Default agent specified",
                "actual": f"Default: {default_agent}",
                "output": f"PASS: Default agent is '{default_agent}'",
                "details": {
                    "default_agent": default_agent,
                    "all_agents": agent_ids
                }
            }
        elif agent_ids:
            # Check if 'main' exists (common default)
            if "main" in agent_ids:
                return {
                    "status": CheckStatus.WARN,
                    "expected": "Default agent specified",
                    "actual": "No explicit default, 'main' exists",
                    "output": "WARN: No explicit default agent (but 'main' exists)",
                    "details": {"available_agents": agent_ids}
                }
            else:
                return {
                    "status": CheckStatus.WARN,
                    "expected": "Default agent specified",
                    "actual": "No default found",
                    "output": "WARN: No default agent configured",
                    "details": {"available_agents": agent_ids}
                }
        else:
            return {
                "status": CheckStatus.FAIL,
                "expected": "Default agent specified",
                "actual": "No agents configured",
                "output": "FAIL: No agents configured",
                "details": {}
            }

    def _check_unique_ids(self) -> Dict[str, Any]:
        """
        AGENT-007: Agent IDs unique

        Validates that all agent IDs are unique.
        """
        agent_ids = [a.get("id") for a in self.agents]
        unique_ids = list(set(agent_ids))

        duplicates = [
            aid for aid in unique_ids
            if agent_ids.count(aid) > 1
        ]

        if not duplicates:
            return {
                "status": CheckStatus.PASS,
                "expected": "All agent IDs unique",
                "actual": f"{len(agent_ids)} unique IDs",
                "output": f"PASS: All {len(agent_ids)} agent IDs are unique",
                "details": {
                    "agent_ids": agent_ids,
                    "count": len(agent_ids)
                }
            }
        else:
            return {
                "status": CheckStatus.FAIL,
                "expected": "All agent IDs unique",
                "actual": f"Duplicates: {duplicates}",
                "output": f"FAIL: Duplicate agent IDs found: {duplicates}",
                "details": {
                    "duplicates": duplicates,
                    "all_ids": agent_ids
                }
            }

    def _check_workspace_paths(self) -> Dict[str, Any]:
        """
        AGENT-008: Workspace paths valid

        Validates that workspace paths are valid.
        """
        default_workspace = self.config.get("agents", {}).get("defaults", {}).get("workspace")

        if not default_workspace:
            return {
                "status": CheckStatus.WARN,
                "expected": "Workspace path configured",
                "actual": "No workspace configured",
                "output": "WARN: No default workspace configured",
                "details": {}
            }

        # Check if workspace directory exists or is a valid path format
        if os.path.exists(default_workspace):
            is_writable = os.access(default_workspace, os.W_OK)
            if is_writable:
                return {
                    "status": CheckStatus.PASS,
                    "expected": "Valid workspace path",
                    "actual": f"{default_workspace} (writable)",
                    "output": f"PASS: Workspace exists and is writable: {default_workspace}",
                    "details": {
                        "path": default_workspace,
                        "writable": True
                    }
                }
            else:
                return {
                    "status": CheckStatus.WARN,
                    "expected": "Valid workspace path",
                    "actual": f"{default_workspace} (not writable)",
                    "output": f"WARN: Workspace exists but not writable: {default_workspace}",
                    "details": {
                        "path": default_workspace,
                        "writable": False
                    }
                }
        else:
            # Path might be valid but not created yet
            if default_workspace.startswith("/"):
                return {
                    "status": CheckStatus.WARN,
                    "expected": "Valid workspace path",
                    "actual": f"{default_workspace} (not found)",
                    "output": f"WARN: Workspace path not found: {default_workspace}",
                    "details": {"path": default_workspace, "exists": False}
                }
            else:
                return {
                    "status": CheckStatus.WARN,
                    "expected": "Valid workspace path",
                    "actual": f"{default_workspace} (relative path)",
                    "output": f"WARN: Workspace uses relative path: {default_workspace}",
                    "details": {"path": default_workspace}
                }
