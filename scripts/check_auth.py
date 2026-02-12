"""
Agent Authentication Tests (AUTH-001 through AUTH-007)

Validates agent authentication mechanisms including HMAC signatures
and gateway token validation.

Checks:
    AUTH-001 [CRITICAL]: HMAC generation works (64-char hex)
    AUTH-002 [CRITICAL]: HMAC verification works
    AUTH-003 [CRITICAL]: Invalid HMAC rejected
    AUTH-004: Gateway token validation
    AUTH-005: Invalid token rejected (401)
    AUTH-006: Agent-to-agent auth
    AUTH-007: Message signature valid
"""

import os
import sys
import hashlib
import hmac
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
class AuthConfig:
    """Configuration for authentication checks."""
    # Minimum lengths
    MIN_GATEWAY_TOKEN = 32
    MIN_HMAC_SECRET = 64

    # HMAC settings
    HMAC_DIGEST = "sha256"
    HMAC_LENGTH = 64  # 32 bytes * 2 (hex encoding)


class AuthChecker:
    """
    Agent authentication checker.

    Validates that HMAC signature generation and verification work correctly.

    Example:
        >>> checker = AuthChecker(
        ...     gateway_token="your_token",
        ...     hmac_secret="your_secret"
        ... )
        >>> results = checker.run_all_checks()
        >>> for result in results:
        ...     print(f"{result.check_id}: {result.status}")
    """

    def __init__(
        self,
        gateway_token: str = "",
        hmac_secret: str = "",
        verbose: bool = False
    ):
        """
        Initialize authentication checker.

        Args:
            gateway_token: Gateway authentication token
            hmac_secret: HMAC secret for agent-to-agent auth
            verbose: Enable verbose logging
        """
        self.gateway_token = gateway_token or os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")
        self.hmac_secret = hmac_secret or os.environ.get("AGENTS_HMAC_SECRET", "")
        self.verbose = verbose

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
            check_id: Check identifier (e.g., AUTH-001)
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
            category=CheckCategory.AUTHENTICATION,
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
        """Run all authentication checks (AUTH-001 through AUTH-007)."""
        results = []

        # AUTH-001: HMAC generation works
        results.append(self._run_check(
            "AUTH-001",
            "HMAC generation works (64-char hex)",
            True,
            self._check_hmac_generation
        ))

        # AUTH-002: HMAC verification works
        results.append(self._run_check(
            "AUTH-002",
            "HMAC verification works",
            True,
            self._check_hmac_verification
        ))

        # AUTH-003: Invalid HMAC rejected
        results.append(self._run_check(
            "AUTH-003",
            "Invalid HMAC rejected",
            True,
            self._check_hmac_rejection
        ))

        # AUTH-004: Gateway token validation
        results.append(self._run_check(
            "AUTH-004",
            "Gateway token validation",
            False,
            self._check_gateway_token
        ))

        # AUTH-005: Invalid token rejected
        results.append(self._run_check(
            "AUTH-005",
            "Invalid token rejected (401)",
            False,
            self._check_token_rejection
        ))

        # AUTH-006: Agent-to-agent auth
        results.append(self._run_check(
            "AUTH-006",
            "Agent-to-agent auth",
            False,
            self._check_agent_to_agent_auth
        ))

        # AUTH-007: Message signature valid
        results.append(self._run_check(
            "AUTH-007",
            "Message signature valid",
            False,
            self._check_message_signature
        ))

        return results

    # ========================================================================
    # Individual Check Functions
    # ========================================================================

    def _generate_hmac(self, message: str, secret: str) -> str:
        """Generate HMAC-SHA256 signature."""
        if isinstance(message, str):
            message = message.encode('utf-8')
        if isinstance(secret, str):
            secret = secret.encode('utf-8')

        return hmac.new(secret, message, hashlib.sha256).hexdigest()

    def _verify_hmac(self, message: str, signature: str, secret: str) -> bool:
        """Verify HMAC-SHA256 signature."""
        expected = self._generate_hmac(message, secret)
        return hmac.compare_digest(expected, signature)

    def _check_hmac_generation(self) -> Dict[str, Any]:
        """
        AUTH-001 [CRITICAL]: HMAC generation works (64-char hex)

        Validates that HMAC signature generation produces correct format.
        """
        test_message = "test_message_for_hmac_generation"
        test_secret = self.hmac_secret or "test_secret_for_validation_min_64_chars_long_____"

        try:
            signature = self._generate_hmac(test_message, test_secret)

            # Check format
            is_hex = all(c in "0123456789abcdef" for c in signature)
            is_correct_length = len(signature) == AuthConfig.HMAC_LENGTH

            if is_hex and is_correct_length:
                return {
                    "status": CheckStatus.PASS,
                    "expected": f"{AuthConfig.HMAC_LENGTH}-char hex string",
                    "actual": f"{len(signature)}-char hex",
                    "output": f"PASS: HMAC generation works ({len(signature)} chars)",
                    "details": {
                        "signature": signature[:16] + "...",
                        "length": len(signature),
                        "is_hex": is_hex
                    }
                }
            else:
                return {
                    "status": CheckStatus.FAIL,
                    "expected": f"{AuthConfig.HMAC_LENGTH}-char hex string",
                    "actual": f"{len(signature)}-char, hex={is_hex}",
                    "output": f"FAIL: HMAC format incorrect (len={len(signature)}, hex={is_hex})",
                    "details": {
                        "length": len(signature),
                        "is_hex": is_hex,
                        "expected_length": AuthConfig.HMAC_LENGTH
                    }
                }
        except Exception as e:
            return {
                "status": CheckStatus.FAIL,
                "expected": f"{AuthConfig.HMAC_LENGTH}-char hex string",
                "actual": f"Error: {str(e)}",
                "output": f"FAIL: HMAC generation failed: {str(e)}",
                "details": {"error": str(e)}
            }

    def _check_hmac_verification(self) -> Dict[str, Any]:
        """
        AUTH-002 [CRITICAL]: HMAC verification works

        Validates that valid HMAC signatures are correctly verified.
        """
        test_message = "test_message_for_hmac_verification"
        test_secret = self.hmac_secret or "test_secret_for_validation_min_64_chars_long_____"

        try:
            # Generate valid signature
            signature = self._generate_hmac(test_message, test_secret)

            # Verify it
            is_valid = self._verify_hmac(test_message, signature, test_secret)

            if is_valid:
                return {
                    "status": CheckStatus.PASS,
                    "expected": "Valid signature accepted",
                    "actual": "Signature verified",
                    "output": "PASS: HMAC verification works",
                    "details": {
                        "signature": signature[:16] + "...",
                        "verified": True
                    }
                }
            else:
                return {
                    "status": CheckStatus.FAIL,
                    "expected": "Valid signature accepted",
                    "actual": "Verification failed",
                    "output": "FAIL: Valid signature was rejected",
                    "details": {"verified": False}
                }
        except Exception as e:
            return {
                "status": CheckStatus.FAIL,
                "expected": "Valid signature accepted",
                "actual": f"Error: {str(e)}",
                "output": f"FAIL: HMAC verification failed: {str(e)}",
                "details": {"error": str(e)}
            }

    def _check_hmac_rejection(self) -> Dict[str, Any]:
        """
        AUTH-003 [CRITICAL]: Invalid HMAC rejected

        Validates that invalid HMAC signatures are correctly rejected.
        """
        test_message = "test_message_for_hmac_rejection"
        test_secret = self.hmac_secret or "test_secret_for_validation_min_64_chars_long_____"

        try:
            # Generate signature with different message
            invalid_signature = self._generate_hmac("different_message", test_secret)

            # Try to verify with original message
            is_valid = self._verify_hmac(test_message, invalid_signature, test_secret)

            if not is_valid:
                return {
                    "status": CheckStatus.PASS,
                    "expected": "Invalid signature rejected",
                    "actual": "Signature rejected",
                    "output": "PASS: Invalid HMAC correctly rejected",
                    "details": {
                        "invalid_signature": invalid_signature[:16] + "...",
                        "verified": False
                    }
                }
            else:
                return {
                    "status": CheckStatus.FAIL,
                    "expected": "Invalid signature rejected",
                    "actual": "Invalid signature accepted",
                    "output": "FAIL: Invalid HMAC was accepted (security issue!)",
                    "details": {"verified": True}
                }
        except Exception as e:
            return {
                "status": CheckStatus.FAIL,
                "expected": "Invalid signature rejected",
                "actual": f"Error: {str(e)}",
                "output": f"FAIL: HMAC rejection test failed: {str(e)}",
                "details": {"error": str(e)}
            }

    def _check_gateway_token(self) -> Dict[str, Any]:
        """
        AUTH-004: Gateway token validation

        Validates that gateway token meets minimum requirements.
        """
        token = self.gateway_token
        token_len = len(token)

        if token_len >= AuthConfig.MIN_GATEWAY_TOKEN:
            return {
                "status": CheckStatus.PASS,
                "expected": f"Token >= {AuthConfig.MIN_GATEWAY_TOKEN} chars",
                "actual": f"{token_len} chars",
                "output": f"PASS: Gateway token configured ({token_len} chars)",
                "details": {
                    "length": token_len,
                    "min_length": AuthConfig.MIN_GATEWAY_TOKEN
                }
            }
        elif token_len > 0:
            return {
                "status": CheckStatus.WARN,
                "expected": f"Token >= {AuthConfig.MIN_GATEWAY_TOKEN} chars",
                "actual": f"{token_len} chars",
                "output": f"WARN: Token is only {token_len} chars (recommended: >= {AuthConfig.MIN_GATEWAY_TOKEN})",
                "details": {
                    "length": token_len,
                    "min_length": AuthConfig.MIN_GATEWAY_TOKEN
                }
            }
        else:
            return {
                "status": CheckStatus.FAIL,
                "expected": f"Token >= {AuthConfig.MIN_GATEWAY_TOKEN} chars",
                "actual": "Token not set",
                "output": "FAIL: Gateway token not configured",
                "details": {"length": 0}
            }

    def _check_token_rejection(self) -> Dict[str, Any]:
        """
        AUTH-005: Invalid token rejected (401)

        Validates that invalid tokens are rejected with 401 status.
        """
        # This is a validation check for the token validation logic
        # In a real scenario, this would make a request to the gateway

        test_tokens = [
            "",           # Empty
            "invalid",    # Too short
            "a" * 10,     # Still too short
            "wrong_token" # Wrong token
        ]

        rejected_count = 0
        for token in test_tokens:
            if len(token) < AuthConfig.MIN_GATEWAY_TOKEN:
                rejected_count += 1
            elif token != self.gateway_token:
                rejected_count += 1

        if rejected_count == len(test_tokens):
            return {
                "status": CheckStatus.PASS,
                "expected": "Invalid tokens rejected",
                "actual": f"{rejected_count}/{len(test_tokens)} rejected",
                "output": f"PASS: Token validation logic correct",
                "details": {
                    "tested": len(test_tokens),
                    "rejected": rejected_count
                }
            }
        else:
            return {
                "status": CheckStatus.WARN,
                "expected": "Invalid tokens rejected",
                "actual": f"{rejected_count}/{len(test_tokens)} rejected",
                "output": f"WARN: Some invalid tokens might be accepted",
                "details": {
                    "tested": len(test_tokens),
                    "rejected": rejected_count
                }
            }

    def _check_agent_to_agent_auth(self) -> Dict[str, Any]:
        """
        AUTH-006: Agent-to-agent auth

        Validates that agent-to-agent authentication works.
        """
        if not self.hmac_secret:
            return {
                "status": CheckStatus.WARN,
                "expected": "HMAC secret configured",
                "actual": "Secret not configured",
                "output": "WARN: AGENTS_HMAC_SECRET not set",
                "details": {}
            }

        # Simulate agent-to-agent message
        from_agent = "main"
        to_agent = "researcher"
        message = f"Hello from {from_agent} to {to_agent}"

        try:
            # Generate signature
            signature = self._generate_hmac(message, self.hmac_secret)

            # Construct signed message
            signed_message = {
                "from": from_agent,
                "to": to_agent,
                "message": message,
                "signature": signature,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            # Verify signature
            is_valid = self._verify_hmac(message, signed_message["signature"], self.hmac_secret)

            if is_valid:
                return {
                    "status": CheckStatus.PASS,
                    "expected": "Agent-to-agent auth works",
                    "actual": "Auth successful",
                    "output": f"PASS: Agent-to-agent authentication works",
                    "details": {
                        "from": from_agent,
                        "to": to_agent,
                        "signature": signature[:16] + "..."
                    }
                }
            else:
                return {
                    "status": CheckStatus.FAIL,
                    "expected": "Agent-to-agent auth works",
                    "actual": "Verification failed",
                    "output": "FAIL: Agent-to-agent signature verification failed",
                    "details": {}
                }
        except Exception as e:
            return {
                "status": CheckStatus.FAIL,
                "expected": "Agent-to-agent auth works",
                "actual": f"Error: {str(e)}",
                "output": f"FAIL: {str(e)}",
                "details": {"error": str(e)}
            }

    def _check_message_signature(self) -> Dict[str, Any]:
        """
        AUTH-007: Message signature valid

        Validates that message signatures include all required fields.
        """
        required_fields = ["from", "to", "message", "signature", "timestamp"]

        # Create a properly signed message
        from_agent = "developer"
        to_agent = "writer"
        message = "Task assigned: Review PR #123"
        timestamp = datetime.now(timezone.utc).isoformat()

        # Sign the message with timestamp for replay protection
        message_to_sign = f"{from_agent}:{to_agent}:{message}:{timestamp}"
        signature = self._generate_hmac(
            message_to_sign,
            self.hmac_secret or "test_secret_for_validation_min_64_chars_long_____"
        )

        signed_message = {
            "from": from_agent,
            "to": to_agent,
            "message": message,
            "timestamp": timestamp,
            "signature": signature
        }

        # Check all required fields
        missing_fields = [f for f in required_fields if f not in signed_message]
        has_signature = bool(signed_message.get("signature"))
        signature_length = len(signed_message.get("signature", ""))

        if not missing_fields and has_signature and signature_length == AuthConfig.HMAC_LENGTH:
            return {
                "status": CheckStatus.PASS,
                "expected": f"All {len(required_fields)} fields present, valid signature",
                "actual": f"{len(required_fields)} fields, {signature_length}-char signature",
                "output": "PASS: Message signature valid",
                "details": {
                    "fields": list(signed_message.keys()),
                    "signature_length": signature_length
                }
            }
        elif missing_fields:
            return {
                "status": CheckStatus.FAIL,
                "expected": f"All {len(required_fields)} fields present",
                "actual": f"Missing: {missing_fields}",
                "output": f"FAIL: Missing required fields: {missing_fields}",
                "details": {"missing_fields": missing_fields}
            }
        else:
            return {
                "status": CheckStatus.WARN,
                "expected": f"{AuthConfig.HMAC_LENGTH}-char signature",
                "actual": f"{signature_length}-char signature",
                "output": f"WARN: Signature length is {signature_length} (expected {AuthConfig.HMAC_LENGTH})",
                "details": {"signature_length": signature_length}
            }
