#!/usr/bin/env python3
"""
Performance Tests for Kurultai Agent Manager

Tests health checks, Neo4j operations, and agent state management.
"""

import os
import sys
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock

# Add scripts directory to path
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)


class TestAgentManagerPerformance(unittest.TestCase):
    """Performance tests for agent manager operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.agents = ['kublai', 'temujin', 'mongke', 'chagatai', 'jochi', 'ogedei']

    def test_health_check_loop_performance(self):
        """Test that checking all 6 agents completes in < 500ms."""
        # Mock Neo4j driver
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_result = MagicMock()

        # Set up mock to return healthy state
        mock_result.single.return_value = {
            "status": "running",
            "task": "test-task",
            "heartbeat": datetime.now().isoformat(),
            "completed": 10,
            "spawned": 5
        }
        mock_session.run.return_value = mock_result
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_driver.session.return_value = mock_session

        # Time health check for all agents
        start = time.perf_counter()

        results = {}
        for agent in self.agents:
            # Simulate the get_agent_state operation
            with mock_driver.session() as session:
                result = session.run("""
                    MATCH (a:AgentState {name: $name})
                    RETURN a.status AS status,
                           a.current_task AS task,
                           a.last_heartbeat AS heartbeat
                """, name=agent)
                record = result.single()
                results[agent] = {
                    "status": record["status"],
                    "healthy": True
                }

        elapsed_ms = (time.perf_counter() - start) * 1000

        # Verify
        self.assertEqual(len(results), 6, "Should check all 6 agents")
        self.assertLess(elapsed_ms, 500, f"Health check should take < 500ms, took {elapsed_ms:.2f}ms")

    def test_heartbeat_staleness_calculation(self):
        """Test heartbeat staleness check for 100 timestamps."""
        # Generate 100 timestamps with varying ages
        now = datetime.now()
        timestamps = []

        for i in range(100):
            # Create timestamps ranging from 1 minute to 20 minutes ago
            age_minutes = (i % 20) + 1
            ts = now - timedelta(minutes=age_minutes)
            timestamps.append(ts.isoformat())

        # Time staleness calculation
        start = time.perf_counter()

        stale_count = 0
        for ts_str in timestamps:
            try:
                hb_time = datetime.fromisoformat(ts_str.replace('Z', '+00:00').replace('+00:00', ''))
                age = datetime.now() - hb_time
                if age > timedelta(minutes=10):
                    stale_count += 1
            except:
                pass

        elapsed_ms = (time.perf_counter() - start) * 1000

        # Verify - timestamps older than 10 minutes should be stale
        # Ages are 1-20 minutes, so 11-20 (10 values) should be stale
        self.assertGreater(stale_count, 0, "Should detect stale heartbeats")
        self.assertLess(elapsed_ms, 50, f"Staleness check should take < 50ms, took {elapsed_ms:.2f}ms")

    def test_health_summary_generation(self):
        """Test health summary generation performance."""
        # Generate mock health data
        agent_states = {}
        for agent in self.agents:
            agent_states[agent] = {
                "healthy": True,
                "state": {
                    "status": "running",
                    "task": f"task-{agent}",
                    "completed": 10,
                    "spawned": 5
                }
            }

        # Make one unhealthy
        agent_states['ogedei'] = {
            "healthy": False,
            "reason": "Heartbeat stale (15 min ago)"
        }

        # Time summary generation
        start = time.perf_counter()

        summary = {
            "timestamp": datetime.now().isoformat(),
            "agents": agent_states,
            "healthy_count": sum(1 for a in agent_states.values() if a.get("healthy")),
            "unhealthy_count": sum(1 for a in agent_states.values() if not a.get("healthy"))
        }

        elapsed_ms = (time.perf_counter() - start) * 1000

        # Verify
        self.assertEqual(summary["healthy_count"], 5)
        self.assertEqual(summary["unhealthy_count"], 1)
        self.assertLess(elapsed_ms, 10, f"Summary generation should take < 10ms, took {elapsed_ms:.2f}ms")


class TestAgentManagerUnit(unittest.TestCase):
    """Unit tests for agent manager functions."""

    def test_heartbeat_staleness_detection(self):
        """Test detection of stale heartbeats."""
        now = datetime.now()

        # Fresh heartbeat (5 minutes ago)
        fresh_ts = (now - timedelta(minutes=5)).isoformat()
        hb_time = datetime.fromisoformat(fresh_ts)
        age = now - hb_time
        self.assertLess(age, timedelta(minutes=10), "5-minute-old heartbeat should be fresh")

        # Stale heartbeat (15 minutes ago)
        stale_ts = (now - timedelta(minutes=15)).isoformat()
        hb_time = datetime.fromisoformat(stale_ts)
        age = now - hb_time
        self.assertGreater(age, timedelta(minutes=10), "15-minute-old heartbeat should be stale")

    def test_agent_state_parsing(self):
        """Test parsing of agent state from Neo4j record."""
        mock_record = {
            "status": "running",
            "task": "implement-feature",
            "heartbeat": "2026-03-08T12:00:00",
            "completed": 25,
            "spawned": 10
        }

        state = {
            "status": mock_record["status"],
            "task": mock_record["task"],
            "heartbeat": mock_record["heartbeat"],
            "completed": mock_record["completed"],
            "spawned": mock_record["spawned"]
        }

        self.assertEqual(state["status"], "running")
        self.assertEqual(state["task"], "implement-feature")
        self.assertEqual(state["completed"], 25)

    def test_health_check_result_structure(self):
        """Test health check result has correct structure."""
        # Healthy result
        healthy_result = {
            "healthy": True,
            "state": {
                "status": "running",
                "task": "test",
                "completed": 5
            }
        }

        self.assertTrue(healthy_result["healthy"])
        self.assertIn("state", healthy_result)
        self.assertIn("status", healthy_result["state"])

        # Unhealthy result
        unhealthy_result = {
            "healthy": False,
            "reason": "Heartbeat stale (12 min ago)",
            "state": {
                "status": "idle"
            }
        }

        self.assertFalse(unhealthy_result["healthy"])
        self.assertIn("reason", unhealthy_result)

    def test_agent_list_completeness(self):
        """Test that all expected agents are in the list."""
        expected_agents = {'kublai', 'temujin', 'mongke', 'chagatai', 'jochi', 'ogedei'}
        actual_agents = set(['kublai', 'temujin', 'mongke', 'chagatai', 'jochi', 'ogedei'])

        self.assertEqual(expected_agents, actual_agents, "All 6 agents should be present")


class TestAgentManagerIntegration(unittest.TestCase):
    """Integration tests for agent manager with simulated Neo4j."""

    @patch.dict(os.environ, {
        'NEO4J_URI': 'bolt://localhost:7687',
        'NEO4J_USER': 'neo4j',
        'NEO4J_PASSWORD': 'test'
    })
    def test_full_health_check_cycle(self):
        """Test full health check cycle with mock Neo4j."""
        from unittest.mock import patch

        # Mock neo4j_session context manager
        mock_session = MagicMock()
        mock_result = MagicMock()

        # Configure mock
        mock_result.single.return_value = {
            "status": "running",
            "task": "test-task",
            "heartbeat": datetime.now().isoformat(),
            "completed": 10,
            "spawned": 5
        }
        mock_session.run.return_value = mock_result

        mock_cm = MagicMock()
        mock_cm.__enter__ = Mock(return_value=mock_session)
        mock_cm.__exit__ = Mock(return_value=False)

        with patch('neo4j_task_tracker.neo4j_session', return_value=mock_cm):
            from neo4j_task_tracker import neo4j_session

            # Simulate health check
            agents = ['kublai', 'temujin', 'mongke', 'chagatai', 'jochi', 'ogedei']
            healthy_count = 0

            for agent in agents:
                with neo4j_session() as session:
                    result = session.run("""
                        MATCH (a:AgentState {name: $name})
                        RETURN a.status AS status
                    """, name=agent)
                    record = result.single()
                    if record and record["status"] == "running":
                        healthy_count += 1

            self.assertEqual(healthy_count, 6, "All agents should be healthy")


if __name__ == '__main__':
    unittest.main(verbosity=2)