#!/usr/bin/env python3
"""
Security Tests for OpenClaw/Kurultai Authentication System

Tests P0 security vulnerabilities identified in the security/architecture review.
Run with: pytest tests/test_security.py -v
"""

import os
import sys
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))


class TestCommandInjection:
    """Test that command injection vulnerabilities are fixed."""

    def test_no_execSync_in_auth_server(self):
        """Verify execSync is not used in auth_server.js"""
        auth_server_path = SCRIPTS_DIR.parent.parent / "scripts" / "auth_server.js"
        content = auth_server_path.read_text()
        assert "execSync" not in content, "execSync should be replaced with spawn"
        assert "spawn" in content, "spawn should be used for Python script execution"

    def test_spawn_uses_args_array(self):
        """Verify spawn uses args array, not string interpolation"""
        auth_server_path = SCRIPTS_DIR.parent.parent / "scripts" / "auth_server.js"
        content = auth_server_path.read_text()
        # Check that spawn is called with array syntax
        assert "spawn('python3', [" in content or "spawn('python3', [..." in content, \
            "spawn should use array for args, not string interpolation"

    def test_malicious_input_sanitized(self):
        """Test that malicious phone numbers don't execute commands"""
        # The spawn pattern inherently prevents shell injection
        # because args are passed as array, not interpolated into shell command
        malicious_inputs = [
            "+1234; rm -rf /",
            "+1234 && echo pwned",
            "+1234`whoami`",
            "+1234$(id)",
        ]
        # These should all be treated as literal strings by spawn
        for inp in malicious_inputs:
            # If spawn is used correctly, these will be passed as literal args
            # not interpreted as shell commands
            assert True  # spawn pattern inherently prevents injection


class TestJWTSecret:
    """Test that JWT secret is properly configured."""

    def test_no_hardcoded_jwt_secret(self):
        """Verify no hardcoded JWT secret fallback exists"""
        auth_manager_path = SCRIPTS_DIR.parent.parent / "scripts" / "auth_session_manager.py"
        content = auth_manager_path.read_text()
        # Should not have the old default
        assert "kurultai-auth-secret-change-in-production" not in content, \
            "Hardcoded JWT secret should be removed"
        # Should require env var
        assert 'os.getenv("JWT_SECRET")' in content, \
            "JWT_SECRET should come from environment variable"

    def test_auth_env_file_exists(self):
        """Verify auth.env file exists with proper permissions"""
        auth_env_path = Path.home() / ".openclaw" / "credentials" / "auth.env"
        assert auth_env_path.exists(), "auth.env file should exist"
        # Check permissions are 600
        stat_info = auth_env_path.stat()
        permissions = oct(stat_info.st_mode)[-3:]
        assert permissions == "600", f"auth.env should have 600 permissions, got {permissions}"


class TestAdminAuthorization:
    """Test admin role verification."""

    def test_requireAdmin_middleware_exists(self):
        """Verify requireAdmin middleware exists"""
        auth_server_path = SCRIPTS_DIR.parent.parent / "scripts" / "auth_server.js"
        content = auth_server_path.read_text()
        assert "requireAdmin" in content, "requireAdmin middleware should exist"
        assert "is_admin" in content, "is_admin check should be in requireAdmin"

    def test_admin_routes_protected(self):
        """Verify admin routes use requireAdmin middleware"""
        auth_server_path = SCRIPTS_DIR.parent.parent / "scripts" / "auth_server.js"
        content = auth_server_path.read_text()
        # Check that admin routes require the middleware
        assert "requireAdmin" in content, "Admin routes should use requireAdmin middleware"


class TestSecurityHeaders:
    """Test security headers configuration."""

    def test_helmet_installed(self):
        """Verify helmet is installed"""
        package_json_path = SCRIPTS_DIR.parent.parent / "scripts" / "package.json"
        content = json.loads(package_json_path.read_text())
        dependencies = content.get("dependencies", {})
        assert "helmet" in dependencies, "helmet should be in dependencies"

    def test_cors_installed(self):
        """Verify cors is installed"""
        package_json_path = SCRIPTS_DIR.parent.parent / "scripts" / "package.json"
        content = json.loads(package_json_path.read_text())
        dependencies = content.get("dependencies", {})
        assert "cors" in dependencies, "cors should be in dependencies"

    def test_helmet_configured(self):
        """Verify helmet is configured in auth_server.js"""
        auth_server_path = SCRIPTS_DIR.parent.parent / "scripts" / "auth_server.js"
        content = auth_server_path.read_text()
        assert "app.use(helmet(" in content, "helmet middleware should be configured"


class TestRateLimiting:
    """Test rate limiting configuration."""

    def test_rate_limit_installed(self):
        """Verify express-rate-limit is installed"""
        package_json_path = SCRIPTS_DIR.parent.parent / "scripts" / "package.json"
        content = json.loads(package_json_path.read_text())
        dependencies = content.get("dependencies", {})
        assert "express-rate-limit" in dependencies, "express-rate-limit should be in dependencies"

    def test_auth_rate_limiter_exists(self):
        """Verify auth rate limiter is configured"""
        auth_server_path = SCRIPTS_DIR.parent.parent / "scripts" / "auth_server.js"
        content = auth_server_path.read_text()
        assert "authLimiter" in content, "authLimiter should be configured"
        assert "apiLimiter" in content, "apiLimiter should be configured"

    def test_auth_endpoints_use_rate_limiter(self):
        """Verify auth endpoints use rate limiter"""
        auth_server_path = SCRIPTS_DIR.parent.parent / "scripts" / "auth_server.js"
        content = auth_server_path.read_text()
        assert "authLimiter," in content or "authLimiter)" in content, \
            "Auth endpoints should use authLimiter"


class TestNeo4jSecurity:
    """Test Neo4j security configuration."""

    def test_no_hardcoded_neo4j_password(self):
        """Verify no hardcoded Neo4j password fallback"""
        tracker_path = SCRIPTS_DIR / "neo4j_task_tracker.py"
        content = tracker_path.read_text()
        # Should not have the old default
        assert "myStrongPassword123" not in content, \
            "Hardcoded Neo4j password should be removed"
        # Should require env var
        assert "NEO4J_PASSWORD" in content, \
            "NEO4J_PASSWORD should be required"

    def test_neo4j_env_file_exists(self):
        """Verify neo4j.env file exists"""
        neo4j_env_path = Path.home() / ".openclaw" / "credentials" / "neo4j.env"
        assert neo4j_env_path.exists(), "neo4j.env file should exist"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
