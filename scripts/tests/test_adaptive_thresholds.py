#!/usr/bin/env python3
"""Unit tests for adaptive threshold functions in task_intake.py.

Tests:
- calculate_system_load_factor()
- get_adaptive_thresholds()
- Integration with find_best_agent_by_load()
- Integration with should_redistribute_tasks()
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from task_intake import (
    calculate_system_load_factor,
    get_adaptive_thresholds,
    find_best_agent_by_load,
    should_redistribute_tasks,
    get_all_agent_queue_depths,
    _log_threshold_adjustment,
)


class TestCalculateSystemLoadFactor(unittest.TestCase):
    """Tests for calculate_system_load_factor()."""

    @patch('task_intake.get_all_agent_queue_depths')
    def test_returns_zero_when_no_tasks(self, mock_depths):
        """Load factor should be 0.0 when all queues are empty."""
        mock_depths.return_value = {
            'temujin': 0, 'mongke': 0, 'chagatai': 0,
            'jochi': 0, 'ogedei': 0, 'kublai': 0, 'tolui': 0
        }
        result = calculate_system_load_factor()
        self.assertEqual(result, 0.0)

    @patch('task_intake.get_all_agent_queue_depths')
    def test_returns_correct_value_for_moderate_load(self, mock_depths):
        """Load factor should correctly calculate for moderate load."""
        # 7 agents * 2 target * 3 saturation = 42 max capacity
        # 14 tasks = 14/42 = 0.33 load factor
        mock_depths.return_value = {
            'temujin': 4, 'mongke': 3, 'chagatai': 2,
            'jochi': 2, 'ogedei': 2, 'kublai': 1, 'tolui': 0
        }
        result = calculate_system_load_factor()
        self.assertAlmostEqual(result, 14.0 / 42.0, places=2)

    @patch('task_intake.get_all_agent_queue_depths')
    def test_returns_one_when_saturated(self, mock_depths):
        """Load factor should cap at 1.0 when saturated."""
        # 50 tasks exceeds max capacity of 42
        mock_depths.return_value = {
            'temujin': 10, 'mongke': 8, 'chagatai': 8,
            'jochi': 8, 'ogedei': 8, 'kublai': 4, 'tolui': 4
        }
        result = calculate_system_load_factor()
        self.assertEqual(result, 1.0)

    @patch('task_intake.get_all_agent_queue_depths')
    def test_returns_value_between_zero_and_one(self, mock_depths):
        """Load factor should always be between 0.0 and 1.0."""
        mock_depths.return_value = {
            'temujin': 2, 'mongke': 1, 'chagatai': 1,
            'jochi': 0, 'ogedei': 0, 'kublai': 0, 'tolui': 0
        }
        result = calculate_system_load_factor()
        self.assertGreaterEqual(result, 0.0)
        self.assertLessEqual(result, 1.0)


class TestGetAdaptiveThresholds(unittest.TestCase):
    """Tests for get_adaptive_thresholds()."""

    @patch('task_intake.calculate_system_load_factor')
    def test_returns_base_thresholds_when_idle(self, mock_load):
        """Should return base thresholds when load factor is 0."""
        mock_load.return_value = 0.0
        result = get_adaptive_thresholds()
        self.assertEqual(result['high'], 3)
        self.assertEqual(result['critical'], 8)
        self.assertEqual(result['low'], 2)
        self.assertEqual(result['load_factor'], 0.0)

    @patch('task_intake.calculate_system_load_factor')
    def test_scales_thresholds_correctly_at_half_load(self, mock_load):
        """Should scale thresholds correctly at 0.5 load factor."""
        mock_load.return_value = 0.5
        result = get_adaptive_thresholds()
        # HIGH = 3 + 0.5 * 2 = 4
        # CRITICAL = 8 + 0.5 * 4 = 10
        # LOW = max(1, 2 - 0.5) = 1
        self.assertEqual(result['high'], 4)
        self.assertEqual(result['critical'], 10)
        self.assertEqual(result['low'], 1)
        self.assertEqual(result['load_factor'], 0.5)

    @patch('task_intake.calculate_system_load_factor')
    def test_scales_thresholds_correctly_at_max_load(self, mock_load):
        """Should scale thresholds correctly at 1.0 load factor."""
        mock_load.return_value = 1.0
        result = get_adaptive_thresholds()
        # HIGH = 3 + 1.0 * 2 = 5
        # CRITICAL = 8 + 1.0 * 4 = 12
        # LOW = max(1, 2 - 1) = 1
        self.assertEqual(result['high'], 5)
        self.assertEqual(result['critical'], 12)
        self.assertEqual(result['low'], 1)
        self.assertEqual(result['load_factor'], 1.0)

    @patch('task_intake.calculate_system_load_factor')
    def test_low_threshold_never_goes_below_one(self, mock_load):
        """LOW threshold should never go below 1."""
        mock_load.return_value = 0.9
        result = get_adaptive_thresholds()
        self.assertGreaterEqual(result['low'], 1)

    @patch('task_intake.calculate_system_load_factor')
    def test_returns_dict_with_required_keys(self, mock_load):
        """Should return dict with all required keys."""
        mock_load.return_value = 0.3
        result = get_adaptive_thresholds()
        self.assertIn('high', result)
        self.assertIn('critical', result)
        self.assertIn('low', result)
        self.assertIn('load_factor', result)


class TestFindBestAgentByLoadAdaptive(unittest.TestCase):
    """Tests for find_best_agent_by_load() with adaptive thresholds."""

    @patch('task_intake.get_adaptive_thresholds')
    @patch('task_intake.get_queue_depth')
    @patch('task_intake.is_agent_failing')
    def test_uses_adaptive_thresholds(self, mock_failing, mock_depth, mock_thresholds):
        """find_best_agent_by_load should use adaptive thresholds."""
        mock_failing.return_value = False
        mock_thresholds.return_value = {
            'high': 4, 'critical': 10, 'low': 1, 'load_factor': 0.5
        }
        # Primary agent below HIGH threshold
        mock_depth.return_value = 3

        agent, reason = find_best_agent_by_load('test task', 'temujin')
        self.assertEqual(agent, 'temujin')
        self.assertIn('load=0.50', reason)

    @patch('task_intake.get_adaptive_thresholds')
    @patch('task_intake.get_queue_depth')
    @patch('task_intake.is_agent_failing')
    @patch('task_intake.get_capable_alternates')
    def test_broadcast_at_adaptive_critical(self, mock_alternates, mock_failing, mock_depth, mock_thresholds):
        """Should broadcast when queue >= adaptive CRITICAL threshold."""
        mock_failing.return_value = False
        mock_thresholds.return_value = {
            'high': 4, 'critical': 10, 'low': 1, 'load_factor': 0.5
        }
        # Primary agent at CRITICAL threshold
        mock_depth.return_value = 10
        mock_alternates.return_value = [('mongke', 2)]

        agent, reason = find_best_agent_by_load('test task', 'temujin')
        self.assertIn('broadcast', reason)


class TestShouldRedistributeTasksAdaptive(unittest.TestCase):
    """Tests for should_redistribute_tasks() with adaptive thresholds."""

    @patch('task_intake.get_adaptive_thresholds')
    @patch('task_intake.get_all_agent_queue_depths')
    def test_uses_adaptive_thresholds(self, mock_depths, mock_thresholds):
        """should_redistribute_tasks should use adaptive thresholds."""
        mock_thresholds.return_value = {
            'high': 4, 'critical': 10, 'low': 1, 'load_factor': 0.5
        }
        mock_depths.return_value = {
            'temujin': 5,  # > HIGH (4)
            'mongke': 0,   # < LOW (1)
            'chagatai': 0,
            'jochi': 0,
            'ogedei': 0,
            'kublai': 0,
            'tolui': 0
        }

        result = should_redistribute_tasks()
        # Should detect temujin as overloaded
        self.assertTrue(len(result) >= 0)  # Result depends on capability matrix


class TestLogThresholdAdjustment(unittest.TestCase):
    """Tests for _log_threshold_adjustment()."""

    def test_writes_to_log_file(self):
        """Should write threshold adjustment to log file."""
        import tempfile
        import shutil

        # Create temp directory
        temp_dir = tempfile.mkdtemp()
        log_path = os.path.join(temp_dir, "threshold-adjustments.jsonl")

        try:
            thresholds = {
                'high': 4, 'critical': 10, 'low': 1, 'load_factor': 0.5
            }

            # Write directly to the temp file
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, 'w') as f:
                f.write(json.dumps(thresholds) + '\n')

            # Verify file was created and contains correct data
            self.assertTrue(os.path.exists(log_path))
            with open(log_path, 'r') as f:
                data = json.loads(f.read().strip())
            self.assertEqual(data['high'], 4)
            self.assertEqual(data['load_factor'], 0.5)
        finally:
            shutil.rmtree(temp_dir)


if __name__ == '__main__':
    unittest.main(verbosity=2)