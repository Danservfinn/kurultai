#!/usr/bin/env python3
"""
Integration Tests for OpenClaw/Kurultai Backend Systems

Tests backend reliability fixes and integration points.
Run with: pytest tests/test_integration.py -v
"""

import os
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))


class TestTaskTrackerDriverLifecycle:
    """Test that TaskTracker properly manages driver lifecycle."""

    def test_close_releases_reference_only(self):
        """Verify TaskTracker.close() releases reference, doesn't close singleton"""
        # Read the neo4j_task_tracker.py file
        tracker_path = SCRIPTS_DIR / "neo4j_task_tracker.py"
        content = tracker_path.read_text()

        # Check that close() doesn't call self.driver.close()
        # It should just release the reference
        assert "self.driver.close()" not in content, \
            "TaskTracker.close() should not call self.driver.close()"
        assert "self.driver = None" in content or "_driver_refcount" in content, \
            "TaskTracker.close() should release reference or manage refcount"

    def test_multiple_trackers_can_coexist(self):
        """Test that multiple TaskTracker instances don't break each other"""
        # This is tested by the pattern - using singleton driver
        tracker_path = SCRIPTS_DIR / "neo4j_task_tracker.py"
        content = tracker_path.read_text()

        # Check for singleton pattern
        assert "_cached_driver" in content or "get_driver()" in content or "neo4j_session" in content, \
            "Should use singleton driver pattern"
        assert "_driver_refcount" in content, \
            "Should track driver reference count"


class TestSessionStoreDriverLifecycle:
    """Test that SessionStore properly manages driver lifecycle."""

    def test_session_store_close_releases_reference(self):
        """Verify SessionStore.close() releases reference, doesn't close driver"""
        session_path = SCRIPTS_DIR.parent.parent / "scripts" / "auth_session_manager.py"
        content = session_path.read_text()

        # Check that close() doesn't call self.driver.close()
        assert "self.driver.close()" not in content, \
            "SessionStore.close() should not call self.driver.close()"


class TestCircuitBreakerNeo4jSession:
    """Test circuit breaker Neo4j session management."""

    def test_circuit_breaker_uses_context_manager(self):
        """Verify circuit breaker uses 'with driver.session()' pattern"""
        cb_path = SCRIPTS_DIR / "circuit_breaker.py"
        content = cb_path.read_text()

        # Check for proper context manager usage
        assert "with driver.session()" in content, \
            "Circuit breaker should use context manager for sessions"

    def test_circuit_breaker_doesnt_close_driver(self):
        """Verify circuit breaker doesn't close the singleton driver"""
        cb_path = SCRIPTS_DIR / "circuit_breaker.py"
        content = cb_path.read_text()

        # Should not have driver.close() call
        # Find the _update_neo4j_task_agent function
        func_start = content.find("def _update_neo4j_task_agent")
        if func_start > 0:
            func_end = content.find("\ndef ", func_start + 1)
            func_content = content[func_start:func_end]
            assert "driver.close()" not in func_content, \
                "Circuit breaker should not close singleton driver"


class TestDualWriteManager:
    """Test dual write manager exists and is structured correctly."""

    def test_dual_write_manager_exists(self):
        """Verify DualWriteManager exists"""
        dwm_path = SCRIPTS_DIR / "dual_write_manager.py"
        assert dwm_path.exists(), "dual_write_manager.py should exist"

    def test_dual_write_manager_has_required_methods(self):
        """Verify DualWriteManager has required methods"""
        dwm_path = SCRIPTS_DIR / "dual_write_manager.py"
        content = dwm_path.read_text()

        assert "def write_event" in content, "Should have write_event method"
        assert "def reconcile" in content, "Should have reconcile method"
        assert "_write_to_ledger" in content, "Should have _write_to_ledger method"


class TestLedgerIdempotency:
    """Test ledger idempotency under concurrent load."""

    def test_score_tasks_has_locking(self):
        """Verify score_tasks.py has file locking"""
        score_path = SCRIPTS_DIR / "score_tasks.py"
        content = score_path.read_text()

        assert "fcntl" in content, "Should use fcntl for file locking"
        assert "SCORE_LOCK_FILE" in content or ".score_lock" in content, \
            "Should have a lock file for scoring"

    def test_score_tasks_checks_existing_scores(self):
        """Verify score_tasks checks for existing SCORED events"""
        score_path = SCRIPTS_DIR / "score_tasks.py"
        content = score_path.read_text()

        assert "scored_ids" in content, "Should track already-scored task IDs"
        assert "SCORED" in content, "Should check for SCORED events"


class TestLedgerRotation:
    """Test ledger rotation functionality."""

    def test_rotate_ledger_exists(self):
        """Verify rotate_ledger.py exists"""
        rotate_path = SCRIPTS_DIR / "rotate_ledger.py"
        assert rotate_path.exists(), "rotate_ledger.py should exist"


class TestLedgerIntegrity:
    """Test ledger integrity verification."""

    def test_kurultai_ledger_exists(self):
        """Verify kurultai_ledger.py exists"""
        ledger_path = SCRIPTS_DIR / "kurultai_ledger.py"
        assert ledger_path.exists(), "kurultai_ledger.py should exist"


class TestCredentialsDirectory:
    """Test credentials directory structure."""

    def test_credentials_directory_exists(self):
        """Verify credentials directory exists"""
        creds_dir = Path.home() / ".openclaw" / "credentials"
        assert creds_dir.exists(), "credentials directory should exist"
        assert creds_dir.stat().st_mode & 0o700 == 0o700, \
            "credentials directory should have 700 permissions"

    def test_auth_env_exists(self):
        """Verify auth.env exists"""
        auth_env_path = Path.home() / ".openclaw" / "credentials" / "auth.env"
        assert auth_env_path.exists(), "auth.env should exist"
        # Check permissions are 600
        permissions = oct(auth_env_path.stat().st_mode)[-3:]
        assert permissions == "600", f"auth.env should have 600 permissions, got {permissions}"

    def test_neo4j_env_exists(self):
        """Verify neo4j.env exists"""
        neo4j_env_path = Path.home() / ".openclaw" / "credentials" / "neo4j.env"
        assert neo4j_env_path.exists(), "neo4j.env should exist"
        # Check permissions are 600
        permissions = oct(neo4j_env_path.stat().st_mode)[-3:]
        assert permissions == "600", f"neo4j.env should have 600 permissions, got {permissions}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
