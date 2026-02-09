#!/usr/bin/env python3
"""
Scheduling Integration Tests

Tests:
- Cron triggers fire correctly
- Reflection runs on schedule
- Vetting workflow end-to-end

Author: Ögedei (Ops Agent)
Date: 2026-02-09
"""

import json
import os
import subprocess
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import Mock, patch, MagicMock

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Skip tests if neo4j is not available
try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False

# Import the modules under test
try:
    from tools.kurultai.reflection_trigger import ReflectionTrigger
    from tools.kurultai.vetting_handlers import (
        OgedeiVettingHandler, 
        VettingDecision, 
        ShieldPolicies,
        PolicyViolation,
        ResourceEstimate
    )
    MODULES_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import modules: {e}")
    MODULES_AVAILABLE = False


@unittest.skipUnless(MODULES_AVAILABLE, "Modules not available")
class TestReflectionTrigger(unittest.TestCase):
    """Test the weekly reflection trigger functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create mock Neo4j driver
        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()
        self.mock_driver.session.return_value.__enter__.return_value = self.mock_session
        self.mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        
        self.trigger = ReflectionTrigger(neo4j_driver=self.mock_driver)
    
    def test_check_system_idle_no_pending_tasks(self):
        """Test that system is idle when no pending tasks exist."""
        # Mock empty task counts
        self.mock_session.run.side_effect = [
            MockResult([{"pending": 0}]),
            MockResult([{"in_progress": 0}]),
            MockResult([{"high_priority": 0}]),
            MockResult([{"active_agents": 3}]),
        ]
        
        metrics = self.trigger.check_system_idle()
        
        self.assertTrue(metrics["is_idle"])
        self.assertEqual(metrics["pending_tasks"], 0)
        self.assertEqual(metrics["high_priority_tasks"], 0)
        self.assertEqual(metrics["active_agents"], 3)
    
    def test_check_system_idle_with_pending_tasks(self):
        """Test that system is not idle when pending tasks exist."""
        # Mock task counts indicating busy system
        self.mock_session.run.side_effect = [
            MockResult([{"pending": 10}]),
            MockResult([{"in_progress": 5}]),
            MockResult([{"high_priority": 2}]),
            MockResult([{"active_agents": 3}]),
        ]
        
        metrics = self.trigger.check_system_idle()
        
        self.assertFalse(metrics["is_idle"])
        self.assertEqual(metrics["pending_tasks"], 10)
        self.assertEqual(metrics["high_priority_tasks"], 2)
    
    def test_check_system_idle_with_high_priority(self):
        """Test that system is not idle when high priority tasks exist."""
        self.mock_session.run.side_effect = [
            MockResult([{"pending": 2}]),
            MockResult([{"in_progress": 1}]),
            MockResult([{"high_priority": 1}]),  # High priority task exists
            MockResult([{"active_agents": 3}]),
        ]
        
        metrics = self.trigger.check_system_idle()
        
        self.assertFalse(metrics["is_idle"])
        self.assertEqual(metrics["high_priority_tasks"], 1)
    
    def test_identify_improvement_areas_failing_tasks(self):
        """Test identification of frequently failing tasks."""
        # Mock failing tasks
        mock_result = MockResult([
            {"task_type": "api_call", "fail_count": 5},
            {"task_type": "database_query", "fail_count": 3},
        ])
        
        # Mock empty results for other checks
        empty_result = MockResult([])
        
        self.mock_session.run.side_effect = [
            mock_result,      # Failing tasks
            empty_result,     # Orphaned nodes
            MockResult([{"slow_count": 0}]),  # Slow tasks
            empty_result,     # Stale heartbeats
            MockResult([{"backlog_count": 0}]),  # Backlog
        ]
        
        opportunities = self.trigger.identify_improvement_areas()
        
        self.assertEqual(len(opportunities), 2)
        self.assertEqual(opportunities[0]["category"], "reliability")
        self.assertIn("api_call", opportunities[0]["title"])
        # Severity is high only if fail_count > 5
        self.assertEqual(opportunities[0]["severity"], "medium")  # fail_count = 5, needs > 5 for high
        self.assertEqual(opportunities[1]["severity"], "medium")  # fail_count is 3
    
    def test_identify_improvement_areas_stale_heartbeats(self):
        """Test identification of stale agent heartbeats."""
        empty_result = MockResult([])
        
        self.mock_session.run.side_effect = [
            empty_result,     # Failing tasks
            empty_result,     # Orphaned nodes
            MockResult([{"slow_count": 0}]),  # Slow tasks
            MockResult([      # Stale heartbeats
                {"agent_name": "test-agent-1", "last_seen": datetime.now(timezone.utc) - timedelta(hours=2)},
            ]),
            MockResult([{"backlog_count": 0}]),  # Backlog
        ]
        
        opportunities = self.trigger.identify_improvement_areas()
        
        self.assertEqual(len(opportunities), 1)
        self.assertEqual(opportunities[0]["category"], "infrastructure")
        self.assertIn("Stale heartbeat", opportunities[0]["title"])
        self.assertEqual(opportunities[0]["severity"], "high")
    
    def test_generate_improvement_opportunities(self):
        """Test creating ImprovementOpportunity nodes in Neo4j."""
        opportunities = [
            {
                "category": "reliability",
                "title": "Test failing tasks",
                "description": "5 failures detected",
                "severity": "high",
                "source": "test"
            }
        ]
        
        self.trigger.reflection_id = "refl-20260209-000000"
        
        # Mock creation result
        self.mock_session.run.return_value = MockResult([{"id": "opp-test-123"}])
        
        created_ids = self.trigger.generate_improvement_opportunities(opportunities)
        
        self.assertEqual(len(created_ids), 1)
        self.assertEqual(created_ids[0], "opp-test-123")
        self.mock_session.run.assert_called_once()
    
    def test_log_reflection_cycle(self):
        """Test logging reflection cycle to Neo4j."""
        metrics = {
            "is_idle": True,
            "pending_tasks": 0,
            "high_priority_tasks": 0
        }
        opportunities = [{"title": "Test"}]
        created_ids = ["opp-123"]
        
        self.mock_session.run.return_value = None
        
        reflection_id = self.trigger.log_reflection_cycle(metrics, opportunities, created_ids)
        
        self.assertTrue(reflection_id.startswith("refl-"))
        self.mock_session.run.assert_called_once()
    
    def test_trigger_reflection_skips_when_busy(self):
        """Test that reflection is skipped when system is not idle."""
        # Mock non-idle system
        self.mock_session.run.side_effect = [
            MockResult([{"pending": 10}]),
            MockResult([{"in_progress": 5}]),
            MockResult([{"high_priority": 2}]),
            MockResult([{"active_agents": 3}]),
        ]
        
        result = self.trigger.trigger_reflection(force=False, dry_run=True)
        
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "system_not_idle")
    
    def test_trigger_reflection_force_when_busy(self):
        """Test that --force runs reflection even when busy."""
        # Mock non-idle system
        self.mock_session.run.side_effect = [
            MockResult([{"pending": 10}]),
            MockResult([{"in_progress": 5}]),
            MockResult([{"high_priority": 2}]),
            MockResult([{"active_agents": 3}]),
            MockResult([]),  # Failing tasks
            MockResult([]),  # Orphaned nodes
            MockResult([{"slow_count": 0}]),
            MockResult([]),  # Stale heartbeats
            MockResult([{"backlog_count": 0}]),
        ]
        
        result = self.trigger.trigger_reflection(force=True, dry_run=True)
        
        self.assertEqual(result["status"], "dry_run_complete")
        self.assertTrue(result["forced"])
    
    def test_trigger_reflection_dry_run(self):
        """Test dry run mode doesn't write to Neo4j."""
        # Mock idle system
        self.mock_session.run.side_effect = [
            MockResult([{"pending": 0}]),
            MockResult([{"in_progress": 0}]),
            MockResult([{"high_priority": 0}]),
            MockResult([{"active_agents": 3}]),
            MockResult([]),  # Failing tasks
            MockResult([]),  # Orphaned nodes
            MockResult([{"slow_count": 0}]),
            MockResult([]),  # Stale heartbeats
            MockResult([{"backlog_count": 0}]),
        ]
        
        result = self.trigger.trigger_reflection(force=False, dry_run=True)
        
        self.assertEqual(result["status"], "dry_run_complete")
        self.assertTrue(result["dry_run"])


@unittest.skipUnless(MODULES_AVAILABLE, "Modules not available")
class TestVettingHandler(unittest.TestCase):
    """Test the Ögedei vetting handler functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()
        self.mock_driver.session.return_value.__enter__.return_value = self.mock_session
        self.mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        
        self.handler = OgedeiVettingHandler(neo4j_driver=self.mock_driver)
    
    def test_get_proposal_found(self):
        """Test fetching an existing proposal."""
        expected_proposal = {
            "id": "prop-123",
            "title": "Test Proposal",
            "description": "Test description",
            "status": "submitted"
        }
        self.mock_session.run.return_value = MockResult([{"proposal": expected_proposal}])
        
        proposal = self.handler.get_proposal("prop-123")
        
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal["id"], "prop-123")
        self.assertEqual(proposal["title"], "Test Proposal")
    
    def test_get_proposal_not_found(self):
        """Test fetching a non-existent proposal."""
        self.mock_session.run.return_value = MockResult([None])
        
        proposal = self.handler.get_proposal("non-existent")
        
        self.assertIsNone(proposal)
    
    def test_list_pending_proposals(self):
        """Test listing pending proposals."""
        mock_proposals = [
            {"id": "prop-1", "title": "Proposal 1", "status": "submitted"},
            {"id": "prop-2", "title": "Proposal 2", "status": "under_review"},
        ]
        self.mock_session.run.return_value = MockResult([
            {"proposal": p} for p in mock_proposals
        ])
        
        proposals = self.handler.list_pending_proposals()
        
        self.assertEqual(len(proposals), 2)
        self.assertEqual(proposals[0]["id"], "prop-1")
    
    def test_estimate_resources_simple(self):
        """Test resource estimation for simple proposal."""
        proposal = {
            "title": "Simple Task",
            "description": "A basic task that runs every hour"
        }
        
        estimate = self.handler._estimate_resources(proposal)
        
        self.assertGreater(estimate.tokens, 0)
        self.assertGreater(estimate.memory_mb, 0)
        self.assertGreater(estimate.cpu_seconds, 0)
    
    def test_estimate_resources_with_migration(self):
        """Test resource estimation for migration proposal."""
        proposal = {
            "title": "Add Migration",
            "description": "Create Neo4j migration for new schema"
        }
        
        estimate = self.handler._estimate_resources(proposal)
        
        # Migration should have higher token estimate
        self.assertGreaterEqual(estimate.tokens, 1000)
    
    def test_estimate_resources_explicit_tokens(self):
        """Test extracting explicit token count from description."""
        proposal = {
            "title": "Task",
            "description": "This task requires approximately 2000 tokens to complete"
        }
        
        estimate = self.handler._estimate_resources(proposal)
        
        self.assertEqual(estimate.tokens, 2000)
    
    def test_check_security_policies_no_secrets(self):
        """Test security check passes for clean proposal."""
        proposal = {
            "title": "Clean Proposal",
            "description": "This is a safe proposal with no secrets"
        }
        
        violations = self.handler._check_security_policies(proposal)
        
        self.assertEqual(len(violations), 0)
    
    def test_check_security_policies_hardcoded_secret(self):
        """Test detection of hardcoded secrets."""
        proposal = {
            "title": "API Integration",
            "description": "Add API key = 'sk-abc123' to the config"
        }
        
        violations = self.handler._check_security_policies(proposal)
        
        self.assertGreaterEqual(len(violations), 1)
        self.assertTrue(any(v.policy_id == ShieldPolicies.SECURITY_NO_SECRETS for v in violations))
    
    def test_check_security_policies_missing_auth(self):
        """Test detection of missing authentication."""
        proposal = {
            "title": "Admin Endpoint",
            "description": "Create admin delete endpoint for user management"
        }
        
        violations = self.handler._check_security_policies(proposal)
        
        self.assertTrue(any(v.policy_id == ShieldPolicies.SECURITY_AUTHENTICATION for v in violations))
    
    def test_check_efficiency_policies_within_budget(self):
        """Test efficiency check passes within budget."""
        proposal = {
            "title": "Hourly Task",
            "description": "Run every hour to check system status"
        }
        estimate = ResourceEstimate(tokens=1000, memory_mb=256, cpu_seconds=60)
        
        violations = self.handler._check_efficiency_policies(proposal, estimate)
        
        # Should have no violations for reasonable estimate
        self.assertEqual(len(violations), 0)
    
    def test_check_efficiency_policies_exceeds_budget(self):
        """Test detection of token budget violation."""
        proposal = {
            "title": "5-min Task",
            "description": "Run every 5 minutes"
        }
        estimate = ResourceEstimate(tokens=10000, memory_mb=256, cpu_seconds=60)
        
        violations = self.handler._check_efficiency_policies(proposal, estimate)
        
        self.assertTrue(any(v.policy_id == ShieldPolicies.EFFICIENCY_TOKEN_BUDGETS for v in violations))
    
    def test_review_proposal_not_found(self):
        """Test reviewing non-existent proposal."""
        self.mock_session.run.return_value = MockResult([None])
        
        result = self.handler.review_proposal("non-existent")
        
        self.assertEqual(result.decision, VettingDecision.REJECT)
        self.assertEqual(result.confidence, 1.0)
        self.assertIn("not found", result.reasoning)
    
    def test_review_proposal_approve_clean(self):
        """Test approval of clean proposal."""
        proposal = {
            "id": "prop-clean",
            "title": "Simple Update",
            "description": "Update documentation with new examples",
            "status": "submitted"
        }
        
        # Mock proposal fetch
        self.mock_session.run.side_effect = [
            MockResult([{"proposal": proposal}]),  # Fetch proposal
            None,  # Update status
            MockResult([{"node_count": 1000}]),  # Check nodes
            MockResult([{"rel_count": 2000}]),  # Check relationships
            MockResult([{"vetting_id": "vet-123"}]),  # Create vetting
            None,  # Link vetting
            None,  # Create violations (none)
        ]
        
        result = self.handler.review_proposal("prop-clean")
        
        self.assertEqual(result.decision, VettingDecision.APPROVE)
        self.assertGreater(result.confidence, 0.8)
    
    def test_review_proposal_reject_critical_violations(self):
        """Test rejection of proposal with critical violations."""
        proposal = {
            "id": "prop-bad",
            "title": "API Integration",
            "description": "Add admin endpoint with password = 'secret123'",
            "status": "submitted"
        }
        
        self.mock_session.run.side_effect = [
            MockResult([{"proposal": proposal}]),
            None,
            MockResult([{"node_count": 1000}]),
            MockResult([{"rel_count": 2000}]),
            MockResult([{"vetting_id": "vet-456"}]),
            None,
            None,
        ]
        
        result = self.handler.review_proposal("prop-bad")
        
        self.assertEqual(result.decision, VettingDecision.REJECT)
        self.assertTrue(any(v.severity == "critical" for v in result.violations))
    
    def test_batch_review(self):
        """Test batch review of multiple proposals."""
        proposals = [
            {"id": "prop-1", "title": "Good Proposal", "description": "Clean proposal"},
            {"id": "prop-2", "title": "Bad Proposal", "description": "password = 'secret'"},
        ]
        
        # Mock list and individual reviews
        self.mock_session.run.side_effect = [
            MockResult([{"proposal": p} for p in proposals]),  # List pending
            # First proposal review
            MockResult([{"proposal": proposals[0]}]),
            None,
            MockResult([{"node_count": 1000}]),
            MockResult([{"rel_count": 2000}]),
            MockResult([{"vetting_id": "vet-1"}]),
            None,
            None,
            # Second proposal review
            MockResult([{"proposal": proposals[1]}]),
            None,
            MockResult([{"node_count": 1000}]),
            MockResult([{"rel_count": 2000}]),
            MockResult([{"vetting_id": "vet-2"}]),
            None,
            None,
        ]
        
        results = self.handler.batch_review(max_proposals=10)
        
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].decision, VettingDecision.APPROVE)
        self.assertEqual(results[1].decision, VettingDecision.REJECT)


class TestCronConfiguration(unittest.TestCase):
    """Test cron configuration matches expected schedule."""
    
    def test_railway_toml_exists(self):
        """Test that railway.toml exists."""
        railway_toml = project_root / "railway.toml"
        self.assertTrue(railway_toml.exists(), "railway.toml should exist")
    
    def test_weekly_reflection_cron_configured(self):
        """Test weekly reflection cron is configured."""
        railway_toml = project_root / "railway.toml"
        content = railway_toml.read_text()
        
        # Check for weekly reflection schedule
        self.assertIn("ogedei-weekly-reflection", content)
        self.assertIn("0 0 * * 0", content)  # Sundays at midnight
        self.assertIn("reflection_trigger", content)
    
    def test_reflection_trigger_module_exists(self):
        """Test reflection_trigger.py exists."""
        trigger_file = project_root / "tools" / "kurultai" / "reflection_trigger.py"
        self.assertTrue(trigger_file.exists(), "reflection_trigger.py should exist")
    
    def test_vetting_handlers_module_exists(self):
        """Test vetting_handlers.py exists."""
        vetting_file = project_root / "tools" / "kurultai" / "vetting_handlers.py"
        self.assertTrue(vetting_file.exists(), "vetting_handlers.py should exist")
    
    def test_shield_policies_exist(self):
        """Test SHIELD.md exists."""
        shield_file = project_root / "SHIELD.md"
        self.assertTrue(shield_file.exists(), "SHIELD.md should exist")


class TestEndToEndWorkflow(unittest.TestCase):
    """Test end-to-end vetting and reflection workflow."""
    
    @unittest.skipUnless(MODULES_AVAILABLE, "Modules not available")
    def test_full_workflow(self):
        """Test complete workflow from proposal to vetting to reflection."""
        # This is a comprehensive integration test
        # It mocks the entire Neo4j interaction
        
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
        
        # Step 1: Create a proposal
        proposal = {
            "id": "prop-integration-test",
            "title": "Integration Test Proposal",
            "description": "Add new feature with proper validation and testing",
            "status": "submitted",
            "priority": "medium"
        }
        
        # Step 2: Vet the proposal
        mock_session.run.side_effect = [
            MockResult([{"proposal": proposal}]),
            None,
            MockResult([{"node_count": 5000}]),
            MockResult([{"rel_count": 10000}]),
            MockResult([{"vetting_id": "vet-integration"}]),
            None,
            None,
        ]
        
        handler = OgedeiVettingHandler(neo4j_driver=mock_driver)
        vetting_result = handler.review_proposal("prop-integration-test")
        
        # Proposal should be approved (it's a clean proposal)
        self.assertEqual(vetting_result.decision, VettingDecision.APPROVE)
        self.assertEqual(vetting_result.proposal_id, "prop-integration-test")
        
        # Step 3: Check reflection trigger
        mock_session.reset_mock()
        mock_session.run.side_effect = [
            MockResult([{"pending": 0}]),
            MockResult([{"in_progress": 0}]),
            MockResult([{"high_priority": 0}]),
            MockResult([{"active_agents": 6}]),
            MockResult([]),  # Failing tasks
            MockResult([]),  # Orphaned nodes
            MockResult([{"slow_count": 0}]),
            MockResult([]),  # Stale heartbeats
            MockResult([{"backlog_count": 0}]),
        ]
        
        trigger = ReflectionTrigger(neo4j_driver=mock_driver)
        result = trigger.trigger_reflection(dry_run=True)
        
        self.assertEqual(result["status"], "dry_run_complete")
        self.assertTrue(result["system_metrics"]["is_idle"])


# Helper classes for mocking Neo4j results

class MockRecord(dict):
    """Mock Neo4j record that behaves like both dict and object."""
    
    def __init__(self, data):
        super().__init__(data)
        self._data = data
    
    def __getattr__(self, key):
        try:
            return self._data[key]
        except KeyError:
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{key}'")
    
    def __getitem__(self, key):
        return self._data[key]
    
    def get(self, key, default=None):
        return self._data.get(key, default)


class MockResult:
    """Mock Neo4j result that returns MockRecord objects."""
    
    def __init__(self, records):
        self._records = [MockRecord(r) if r is not None else None for r in records]
    
    def __iter__(self):
        for record in self._records:
            if record is not None:
                yield record
    
    def single(self):
        if not self._records:
            return None
        return self._records[0]
    
    def peek(self):
        if not self._records:
            return None
        return self._records[0]


def run_tests():
    """Run all tests."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestReflectionTrigger))
    suite.addTests(loader.loadTestsFromTestCase(TestVettingHandler))
    suite.addTests(loader.loadTestsFromTestCase(TestCronConfiguration))
    suite.addTests(loader.loadTestsFromTestCase(TestEndToEndWorkflow))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Return exit code
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
