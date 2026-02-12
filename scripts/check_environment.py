"""
Environment Validation Checks (ENV-001 through ENV-012)

Validates that all required environment variables are set with appropriate
values and that all required directories and files exist.

Checks:
    ENV-001 [CRITICAL]: Gateway token >= 32 chars
    ENV-002 [CRITICAL]: Neo4j password >= 16 chars
    ENV-003 [CRITICAL]: HMAC secret >= 64 chars
    ENV-004: Signal account configured
    ENV-005: Admin phones configured
    ENV-006: S3/GCS credentials set
    ENV-007: Backup encryption key set
    ENV-008: Workspace directory exists
    ENV-009: Souls directory exists
    ENV-010: Agent directories exist (>= 6)
    ENV-011: moltbot.json valid JSON
    ENV-012: Docker socket accessible
"""

import os
import sys
import json
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.check_types import CheckResult, CheckCategory, CheckStatus

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class EnvironmentConfig:
    """Configuration for environment checks."""
    # Critical thresholds
    CRITICAL_GATEWAY_TOKEN_MIN = 32
    CRITICAL_NEO4J_PASSWORD_MIN = 16
    CRITICAL_HMAC_SECRET_MIN = 64

    # Expected directories
    WORKSPACE_DIR = "/data/workspace"
    SOULS_DIR = "/data/souls"
    AGENTS_BASE_DIR = "/data/.clawdbot/agents"

    # Expected admin phones count
    MIN_ADMIN_PHONES = 1

    # Docker socket
    DOCKER_SOCKET = "/var/run/docker.sock"


class EnvironmentChecker:
    """
    Environment validation checker.

    Validates that all required environment variables are set with
    appropriate values and that all required directories and files exist.

    Example:
        >>> checker = EnvironmentChecker()
        >>> results = checker.run_all_checks()
        >>> for result in results:
        ...     print(f"{result.check_id}: {result.status}")
    """

    def __init__(
        self,
        config_path: str = "moltbot.json",
        env_path: str = ".env",
        env_vars: Optional[Dict[str, str]] = None,
        verbose: bool = False
    ):
        """
        Initialize environment checker.

        Args:
            config_path: Path to moltbot.json config file
            env_path: Path to .env file
            env_vars: Optional pre-loaded environment variables (for testing)
            verbose: Enable verbose logging
        """
        self.config_path = config_path
        self.env_path = env_path
        self.verbose = verbose

        # Load configuration
        self.config = self._load_config()
        self.env_vars = env_vars if env_vars is not None else self._load_env_vars()

    def _load_config(self) -> Dict:
        """Load moltbot.json configuration."""
        try:
            with open(self.config_path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config file not found: {self.config_path}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            return {}

    def _load_env_vars(self) -> Dict[str, str]:
        """Load environment variables from .env file and environment."""
        env_vars = dict(os.environ)

        # Also try to load from .env file
        try:
            with open(self.env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        env_vars[key.strip()] = value.strip()
        except FileNotFoundError:
            logger.debug(f".env file not found: {self.env_path}")

        return env_vars

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
            check_id: Check identifier (e.g., ENV-001)
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
            category=CheckCategory.ENVIRONMENT,
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
        """Run all environment checks (ENV-001 through ENV-012)."""
        results = []

        # ENV-001: Gateway token check
        results.append(self._run_check(
            "ENV-001",
            "Gateway token set",
            True,
            self._check_gateway_token
        ))

        # ENV-002: Neo4j password check
        results.append(self._run_check(
            "ENV-002",
            "Neo4j password set",
            True,
            self._check_neo4j_password
        ))

        # ENV-003: HMAC secret check
        results.append(self._run_check(
            "ENV-003",
            "HMAC secret set",
            True,
            self._check_hmac_secret
        ))

        # ENV-004: Signal account check
        results.append(self._run_check(
            "ENV-004",
            "Signal account configured",
            False,
            self._check_signal_account
        ))

        # ENV-005: Admin phones check
        results.append(self._run_check(
            "ENV-005",
            "Admin phones configured",
            False,
            self._check_admin_phones
        ))

        # ENV-006: S3/GCS credentials check
        results.append(self._run_check(
            "ENV-006",
            "S3/GCS credentials set",
            False,
            self._check_storage_credentials
        ))

        # ENV-007: Backup encryption key check
        results.append(self._run_check(
            "ENV-007",
            "Backup encryption key set",
            False,
            self._check_backup_key
        ))

        # ENV-008: Workspace directory check
        results.append(self._run_check(
            "ENV-008",
            "Workspace directory exists",
            False,
            self._check_workspace_dir
        ))

        # ENV-009: Souls directory check
        results.append(self._run_check(
            "ENV-009",
            "Souls directory exists",
            False,
            self._check_souls_dir
        ))

        # ENV-010: Agent directories check
        results.append(self._run_check(
            "ENV-010",
            "Agent directories exist",
            False,
            self._check_agent_dirs
        ))

        # ENV-011: moltbot.json valid JSON check
        results.append(self._run_check(
            "ENV-011",
            "moltbot.json valid JSON",
            False,
            self._check_config_json
        ))

        # ENV-012: Docker socket check
        results.append(self._run_check(
            "ENV-012",
            "Docker socket accessible",
            False,
            self._check_docker_socket
        ))

        return results

    # ========================================================================
    # Individual Check Functions
    # ========================================================================

    def _check_gateway_token(self) -> Dict[str, Any]:
        """
        ENV-001 [CRITICAL]: Gateway token >= 32 chars

        Validates that OPENCLAW_GATEWAY_TOKEN is set and meets minimum length.
        """
        token = self.env_vars.get("OPENCLAW_GATEWAY_TOKEN", "")

        # Handle ${VAR} substitution in config
        if token.startswith("${") and token.endswith("}"):
            var_name = token[2:-1]
            token = self.env_vars.get(var_name, "")

        token_len = len(token)
        min_len = EnvironmentConfig.CRITICAL_GATEWAY_TOKEN_MIN

        if token_len >= min_len:
            return {
                "status": CheckStatus.PASS,
                "expected": f"Count >= {min_len}",
                "actual": f"{token_len} chars",
                "output": f"PASS ({token_len} chars)",
                "details": {"token_length": token_len}
            }
        elif token_len > 0:
            return {
                "status": CheckStatus.FAIL,
                "expected": f"Count >= {min_len}",
                "actual": f"{token_len} chars",
                "output": f"FAIL: Token is only {token_len} chars (minimum {min_len})",
                "details": {"token_length": token_len, "minimum": min_len}
            }
        else:
            return {
                "status": CheckStatus.FAIL,
                "expected": f"Count >= {min_len}",
                "actual": "0 chars (not set)",
                "output": "FAIL: OPENCLAW_GATEWAY_TOKEN not set",
                "details": {"token_length": 0, "minimum": min_len}
            }

    def _check_neo4j_password(self) -> Dict[str, Any]:
        """
        ENV-002 [CRITICAL]: Neo4j password >= 16 chars

        Validates that NEO4J_PASSWORD is set and meets minimum length.
        """
        password = self.env_vars.get("NEO4J_PASSWORD", "")
        password_len = len(password)
        min_len = EnvironmentConfig.CRITICAL_NEO4J_PASSWORD_MIN

        if password_len >= min_len:
            return {
                "status": CheckStatus.PASS,
                "expected": f"Count >= {min_len}",
                "actual": f"{password_len} chars",
                "output": f"PASS ({password_len} chars)",
                "details": {"password_length": password_len}
            }
        elif password_len > 0:
            return {
                "status": CheckStatus.FAIL,
                "expected": f"Count >= {min_len}",
                "actual": f"{password_len} chars",
                "output": f"FAIL: Password is only {password_len} chars (minimum {min_len})",
                "details": {"password_length": password_len, "minimum": min_len}
            }
        else:
            return {
                "status": CheckStatus.FAIL,
                "expected": f"Count >= {min_len}",
                "actual": "0 chars (not set)",
                "output": "FAIL: NEO4J_PASSWORD not set",
                "details": {"password_length": 0, "minimum": min_len}
            }

    def _check_hmac_secret(self) -> Dict[str, Any]:
        """
        ENV-003 [CRITICAL]: HMAC secret >= 64 chars

        Validates that AGENTS_HMAC_SECRET is set and meets minimum length.
        """
        secret = self.env_vars.get("AGENTS_HMAC_SECRET", "")
        secret_len = len(secret)
        min_len = EnvironmentConfig.CRITICAL_HMAC_SECRET_MIN

        if secret_len >= min_len:
            return {
                "status": CheckStatus.PASS,
                "expected": f"Count >= {min_len}",
                "actual": f"{secret_len} chars",
                "output": f"PASS ({secret_len} chars)",
                "details": {"secret_length": secret_len}
            }
        elif secret_len > 0:
            return {
                "status": CheckStatus.FAIL,
                "expected": f"Count >= {min_len}",
                "actual": f"{secret_len} chars",
                "output": f"FAIL: Secret is only {secret_len} chars (minimum {min_len})",
                "details": {"secret_length": secret_len, "minimum": min_len}
            }
        else:
            return {
                "status": CheckStatus.FAIL,
                "expected": f"Count >= {min_len}",
                "actual": "0 chars (not set)",
                "output": "FAIL: AGENTS_HMAC_SECRET not set",
                "details": {"secret_length": 0, "minimum": min_len}
            }

    def _check_signal_account(self) -> Dict[str, Any]:
        """
        ENV-004: Signal account configured

        Validates that SIGNAL_ACCOUNT_NUMBER is set with valid E.164 format.
        """
        account = self.env_vars.get("SIGNAL_ACCOUNT_NUMBER", "")

        # Also check config
        if not account and "channels" in self.config:
            account = self.config.get("channels", {}).get("signal", {}).get("account", "")

        # E.164 format: + followed by 10-15 digits
        e164_pattern = r"^\+[1-9]\d{6,14}$"

        if account and re.match(e164_pattern, account):
            return {
                "status": CheckStatus.PASS,
                "expected": "Valid E.164 phone number",
                "actual": account[:7] + "..." + account[-2:],
                "output": f"PASS: {account[:7]}...{account[-2:]}",
                "details": {"account": account}
            }
        elif account:
            return {
                "status": CheckStatus.WARN,
                "expected": "Valid E.164 phone number (+xxxxxxxxxx)",
                "actual": account,
                "output": f"WARN: Account format may be invalid: {account}",
                "details": {"account": account}
            }
        else:
            return {
                "status": CheckStatus.WARN,
                "expected": "Valid E.164 phone number",
                "actual": "Not configured",
                "output": "WARN: SIGNAL_ACCOUNT_NUMBER not configured",
                "details": {}
            }

    def _check_admin_phones(self) -> Dict[str, Any]:
        """
        ENV-005: Admin phones configured

        Validates that at least one admin phone is configured.
        """
        admin_phones = []

        # Check environment variables
        for i in range(1, 10):  # Check up to ADMIN_PHONE_10
            phone = self.env_vars.get(f"ADMIN_PHONE_{i}")
            if phone:
                admin_phones.append(phone)

        # Also check config for allowFrom
        if "channels" in self.config:
            signal_config = self.config.get("channels", {}).get("signal", {})
            allow_from = signal_config.get("allowFrom", [])
            if allow_from:
                admin_phones.extend(allow_from)

        # Remove duplicates
        admin_phones = list(set(admin_phones))
        phone_count = len(admin_phones)

        if phone_count >= EnvironmentConfig.MIN_ADMIN_PHONES:
            masked_phones = [
                p[:7] + "..." + p[-2:] if len(p) > 9 else p
                for p in admin_phones
            ]
            return {
                "status": CheckStatus.PASS,
                "expected": f"At least {EnvironmentConfig.MIN_ADMIN_PHONES} admin phone",
                "actual": f"{phone_count} configured",
                "output": f"PASS: {phone_count} admin phone(s) configured",
                "details": {"admin_phones": masked_phones}
            }
        else:
            return {
                "status": CheckStatus.WARN,
                "expected": f"At least {EnvironmentConfig.MIN_ADMIN_PHONES} admin phone",
                "actual": f"{phone_count} configured",
                "output": f"WARN: No admin phones configured",
                "details": {"admin_phones": []}
            }

    def _check_storage_credentials(self) -> Dict[str, Any]:
        """
        ENV-006: S3/GCS credentials set

        Validates that cloud storage credentials are configured for backups.
        """
        # Check for AWS S3 credentials
        aws_key_id = self.env_vars.get("AWS_ACCESS_KEY_ID")
        aws_secret = self.env_vars.get("AWS_SECRET_ACCESS_KEY")
        aws_region = self.env_vars.get("AWS_DEFAULT_REGION")

        # Check for GCS credentials
        gcs_key = self.env_vars.get("GOOGLE_APPLICATION_CREDENTIALS")
        gcs_bucket = self.env_vars.get("GCS_BUCKET")

        # Check for Azure credentials
        azure_account = self.env_vars.get("AZURE_STORAGE_ACCOUNT")
        azure_key = self.env_vars.get("AZURE_STORAGE_KEY")

        aws_configured = bool(aws_key_id and aws_secret)
        gcs_configured = bool(gcs_key or gcs_bucket)
        azure_configured = bool(azure_account and azure_key)

        if aws_configured or gcs_configured or azure_configured:
            configured = []
            if aws_configured:
                configured.append(f"AWS S3 (region: {aws_region or 'default'})")
            if gcs_configured:
                configured.append("Google Cloud Storage")
            if azure_configured:
                configured.append("Azure Blob Storage")

            return {
                "status": CheckStatus.PASS,
                "expected": "At least one storage backend configured",
                "actual": ", ".join(configured),
                "output": f"PASS: {', '.join(configured)}",
                "details": {
                    "aws": aws_configured,
                    "gcs": gcs_configured,
                    "azure": azure_configured
                }
            }
        else:
            return {
                "status": CheckStatus.WARN,
                "expected": "At least one storage backend configured",
                "actual": "None configured",
                "output": "WARN: No cloud storage credentials configured (backups may fail)",
                "details": {
                    "aws": False,
                    "gcs": False,
                    "azure": False
                }
            }

    def _check_backup_key(self) -> Dict[str, Any]:
        """
        ENV-007: Backup encryption key set

        Validates that backup encryption key is configured.
        """
        backup_key = self.env_vars.get("BACKUP_ENCRYPTION_KEY")
        passphrase = self.env_vars.get("BACKUP_PASSPHRASE")

        if backup_key or passphrase:
            key_type = "BACKUP_ENCRYPTION_KEY" if backup_key else "BACKUP_PASSPHRASE"
            key_len = len(backup_key or passphrase)

            if key_len >= 16:
                return {
                    "status": CheckStatus.PASS,
                    "expected": "Encryption key configured (>= 16 chars)",
                    "actual": f"{key_len} chars ({key_type})",
                    "output": f"PASS: {key_type} configured",
                    "details": {"key_type": key_type, "length": key_len}
                }
            else:
                return {
                    "status": CheckStatus.WARN,
                    "expected": "Encryption key configured (>= 16 chars)",
                    "actual": f"{key_len} chars ({key_type})",
                    "output": f"WARN: {key_type} is only {key_len} chars (recommended: >= 16)",
                    "details": {"key_type": key_type, "length": key_len}
                }
        else:
            return {
                "status": CheckStatus.WARN,
                "expected": "Encryption key configured",
                "actual": "Not configured",
                "output": "WARN: No backup encryption key configured",
                "details": {}
            }

    def _check_workspace_dir(self) -> Dict[str, Any]:
        """
        ENV-008: Workspace directory exists

        Validates that the workspace directory exists.
        """
        workspace_dir = self.env_vars.get(
            "WORKSPACE_DIR",
            self.config.get("agents", {}).get("defaults", {}).get("workspace", EnvironmentConfig.WORKSPACE_DIR)
        )

        if os.path.exists(workspace_dir) and os.path.isdir(workspace_dir):
            return {
                "status": CheckStatus.PASS,
                "expected": f"Directory exists: {workspace_dir}",
                "actual": f"Directory exists",
                "output": f"PASS: {workspace_dir}",
                "details": {"path": workspace_dir}
            }
        else:
            return {
                "status": CheckStatus.WARN,
                "expected": f"Directory exists: {workspace_dir}",
                "actual": "Not found",
                "output": f"WARN: Workspace directory not found: {workspace_dir}",
                "details": {"path": workspace_dir}
            }

    def _check_souls_dir(self) -> Dict[str, Any]:
        """
        ENV-009: Souls directory exists

        Validates that the souls directory exists.
        """
        souls_dir = self.env_vars.get(
            "SOULS_DIR",
            EnvironmentConfig.SOULS_DIR
        )

        if os.path.exists(souls_dir) and os.path.isdir(souls_dir):
            return {
                "status": CheckStatus.PASS,
                "expected": f"Directory exists: {souls_dir}",
                "actual": f"Directory exists",
                "output": f"PASS: {souls_dir}",
                "details": {"path": souls_dir}
            }
        else:
            return {
                "status": CheckStatus.WARN,
                "expected": f"Directory exists: {souls_dir}",
                "actual": "Not found",
                "output": f"WARN: Souls directory not found: {souls_dir}",
                "details": {"path": souls_dir}
            }

    def _check_agent_dirs(self) -> Dict[str, Any]:
        """
        ENV-010: Agent directories exist (>= 6)

        Validates that at least 6 agent directories exist.
        """
        agents_base = EnvironmentConfig.AGENTS_BASE_DIR
        min_agents = 6

        if os.path.exists(agents_base) and os.path.isdir(agents_base):
            agent_dirs = [
                d for d in os.listdir(agents_base)
                if os.path.isdir(os.path.join(agents_base, d))
            ]
            agent_count = len(agent_dirs)
        else:
            agent_dirs = []
            agent_count = 0

        # Also check config for agent count
        if "agents" in self.config and "list" in self.config["agents"]:
            config_agents = len(self.config["agents"]["list"])
            if config_agents > agent_count:
                agent_count = config_agents

        if agent_count >= min_agents:
            return {
                "status": CheckStatus.PASS,
                "expected": f"At least {min_agents} agent directories",
                "actual": f"{agent_count} found",
                "output": f"PASS: {agent_count} agent directories found",
                "details": {"agent_count": agent_count, "min_required": min_agents}
            }
        elif agent_count > 0:
            return {
                "status": CheckStatus.WARN,
                "expected": f"At least {min_agents} agent directories",
                "actual": f"{agent_count} found",
                "output": f"WARN: Only {agent_count} agent directories found (need {min_agents})",
                "details": {"agent_count": agent_count, "min_required": min_agents}
            }
        else:
            return {
                "status": CheckStatus.FAIL,
                "expected": f"At least {min_agents} agent directories",
                "actual": "0 found",
                "output": f"FAIL: No agent directories found",
                "details": {"agent_count": 0, "min_required": min_agents}
            }

    def _check_config_json(self) -> Dict[str, Any]:
        """
        ENV-011: moltbot.json valid JSON

        Validates that moltbot.json is valid JSON and has required structure.
        """
        config = self.config

        if not config:
            return {
                "status": CheckStatus.FAIL,
                "expected": "Valid JSON file",
                "actual": "File not found or invalid",
                "output": f"FAIL: Could not load {self.config_path}",
                "details": {}
            }

        # Check for required top-level keys
        required_keys = ["gateway", "agents", "channels", "session"]
        missing_keys = [k for k in required_keys if k not in config]

        if not missing_keys:
            # Check agent list
            agent_list = config.get("agents", {}).get("list", [])
            agent_count = len(agent_list)

            return {
                "status": CheckStatus.PASS,
                "expected": "Valid JSON with required keys",
                "actual": f"Valid JSON with {agent_count} agents",
                "output": f"PASS: Valid moltbot.json with {agent_count} agents",
                "details": {
                    "keys": list(config.keys()),
                    "agent_count": agent_count
                }
            }
        else:
            return {
                "status": CheckStatus.WARN,
                "expected": f"Keys: {', '.join(required_keys)}",
                "actual": f"Missing: {', '.join(missing_keys)}",
                "output": f"WARN: Missing required keys: {', '.join(missing_keys)}",
                "details": {"missing_keys": missing_keys}
            }

    def _check_docker_socket(self) -> Dict[str, Any]:
        """
        ENV-012: Docker socket accessible

        Validates that Docker socket is accessible for container operations.
        """
        docker_socket = self.env_vars.get(
            "DOCKER_SOCKET",
            EnvironmentConfig.DOCKER_SOCKET
        )

        if os.path.exists(docker_socket):
            # Check if readable
            if os.access(docker_socket, os.R_OK):
                return {
                    "status": CheckStatus.PASS,
                    "expected": f"Socket accessible: {docker_socket}",
                    "actual": "Accessible",
                    "output": f"PASS: Docker socket accessible",
                    "details": {"path": docker_socket}
                }
            else:
                return {
                    "status": CheckStatus.WARN,
                    "expected": f"Socket accessible: {docker_socket}",
                    "actual": "Not readable",
                    "output": f"WARN: Docker socket exists but not readable",
                    "details": {"path": docker_socket}
                }
        else:
            # Check if docker command works instead
            try:
                import subprocess
                result = subprocess.run(
                    ["docker", "--version"],
                    capture_output=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return {
                        "status": CheckStatus.PASS,
                        "expected": "Docker available",
                        "actual": result.stdout.decode().strip(),
                        "output": f"PASS: Docker CLI available",
                        "details": {"docker_version": result.stdout.decode().strip()}
                    }
            except Exception:
                pass

            return {
                "status": CheckStatus.WARN,
                "expected": f"Socket accessible: {docker_socket}",
                "actual": "Not found",
                "output": f"WARN: Docker socket not found (may not be needed)",
                "details": {"path": docker_socket}
            }
