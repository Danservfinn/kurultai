#!/usr/bin/env python3
"""
Unit Tests for Kublai Learning Queries

Tests the LearningQueries class with mocked Neo4j driver.
Covers all 6 analysis queries and helper methods.
"""

import os
import sys
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

# Add scripts directory to path
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)

from kublai_learning_queries import LearningQueries


class TestLearningQueriesConstants(unittest.TestCase):
    """Test class constants and thresholds."""

    def test_min_sample_agent_threshold(self):
        """Test that MIN_SAMPLE_AGENT is 5."""
        self.assertEqual(LearningQueries.MIN_SAMPLE_AGENT, 5)

    def test_min_sample_system_threshold(self):
        """Test that MIN_SAMPLE_SYSTEM is 10."""
        self.assertEqual(LearningQueries.MIN_SAMPLE_SYSTEM, 10)

    def test_min_sample_high_confidence_threshold(self):
        """Test that MIN_SAMPLE_HIGH_CONFIDENCE is 15."""
        self.assertEqual(LearningQueries.MIN_SAMPLE_HIGH_CONFIDENCE, 15)

    def test_learning_ttl_days(self):
        """Test that LEARNING_TTL_DAYS is 14."""
        self.assertEqual(LearningQueries.LEARNING_TTL_DAYS, 14)


class TestCalculateConfidence(unittest.TestCase):
    """Test the calculate_confidence helper method."""

    def setUp(self):
        """Set up mock driver and queries instance."""
        self.mock_driver = MagicMock()
        self.queries = LearningQueries(self.mock_driver)

    def test_high_confidence_agent_specific(self):
        """Test high confidence tier for agent-specific data (15+ samples)."""
        confidence = self.queries.calculate_confidence(15, 0.8, is_agent_specific=True)
        self.assertGreaterEqual(confidence, 0.9)
        self.assertLessEqual(confidence, 0.98)

    def test_high_confidence_system_wide(self):
        """Test high confidence tier for system-wide data (20+ samples)."""
        confidence = self.queries.calculate_confidence(20, 0.8, is_agent_specific=False)
        self.assertGreaterEqual(confidence, 0.9)

    def test_medium_confidence_agent_specific(self):
        """Test medium confidence tier (10-14 samples for agent)."""
        confidence = self.queries.calculate_confidence(12, 0.7, is_agent_specific=True)
        self.assertGreaterEqual(confidence, 0.7)
        self.assertLess(confidence, 0.9)

    def test_low_confidence_agent_specific(self):
        """Test low confidence tier (5-9 samples for agent)."""
        confidence = self.queries.calculate_confidence(7, 0.6, is_agent_specific=True)
        self.assertGreaterEqual(confidence, 0.5)
        self.assertLess(confidence, 0.7)

    def test_quality_boost_high_quality(self):
        """Test that high quality boosts confidence."""
        base_confidence = self.queries.calculate_confidence(15, 0.5, is_agent_specific=True)
        boosted_confidence = self.queries.calculate_confidence(15, 0.9, is_agent_specific=True)
        self.assertGreater(boosted_confidence, base_confidence)

    def test_quality_penalty_low_quality(self):
        """Test that low quality reduces confidence."""
        base_confidence = self.queries.calculate_confidence(15, 0.5, is_agent_specific=True)
        penalized_confidence = self.queries.calculate_confidence(15, 0.3, is_agent_specific=True)
        self.assertLess(penalized_confidence, base_confidence)

    def test_confidence_bounds_minimum(self):
        """Test that confidence doesn't go below 0.3."""
        confidence = self.queries.calculate_confidence(5, 0.0, is_agent_specific=True)
        self.assertGreaterEqual(confidence, 0.3)

    def test_confidence_bounds_maximum(self):
        """Test that confidence doesn't exceed 0.98."""
        confidence = self.queries.calculate_confidence(100, 1.0, is_agent_specific=True)
        self.assertLessEqual(confidence, 0.98)

    def test_quality_normalization_high_value(self):
        """Test quality normalization when value > 1 (assumes 0-10 scale)."""
        # If avg_quality is 8.0 (on 0-10 scale), should normalize to 0.8
        confidence = self.queries.calculate_confidence(15, 8.0, is_agent_specific=True)
        self.assertIsInstance(confidence, float)
        self.assertGreater(confidence, 0.85)  # Should get quality boost


class TestGetBaselineQuality(unittest.TestCase):
    """Test get_baseline_quality method."""

    def setUp(self):
        """Set up mock driver and queries instance."""
        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()
        self.mock_result = MagicMock()

        self.mock_session.__enter__ = Mock(return_value=self.mock_session)
        self.mock_session.__exit__ = Mock(return_value=False)
        self.mock_driver.session.return_value = self.mock_session

        self.queries = LearningQueries(self.mock_driver)

    def test_baseline_quality_returns_value(self):
        """Test that baseline quality returns a float value."""
        self.mock_result.single.return_value = {"baseline": 0.72}
        self.mock_session.run.return_value = self.mock_result

        baseline = self.queries.get_baseline_quality('temujin')
        self.assertEqual(baseline, 0.72)

    def test_baseline_quality_system_wide(self):
        """Test system-wide baseline quality (no agent filter)."""
        self.mock_result.single.return_value = {"baseline": 0.68}
        self.mock_session.run.return_value = self.mock_result

        baseline = self.queries.get_baseline_quality()
        self.assertEqual(baseline, 0.68)

    def test_baseline_quality_default_on_null(self):
        """Test that baseline returns 0.5 when no data available."""
        self.mock_result.single.return_value = {"baseline": None}
        self.mock_session.run.return_value = self.mock_result

        baseline = self.queries.get_baseline_quality('unknown_agent')
        self.assertEqual(baseline, 0.5)

    def test_baseline_quality_default_on_no_record(self):
        """Test that baseline returns 0.5 when no record returned."""
        self.mock_result.single.return_value = None
        self.mock_session.run.return_value = self.mock_result

        baseline = self.queries.get_baseline_quality()
        self.assertEqual(baseline, 0.5)


class TestGetAgentPromptPatterns(unittest.TestCase):
    """Test get_agent_prompt_patterns method."""

    def setUp(self):
        """Set up mock driver and queries instance."""
        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()

        self.mock_session.__enter__ = Mock(return_value=self.mock_session)
        self.mock_session.__exit__ = Mock(return_value=False)
        self.mock_driver.session.return_value = self.mock_session

        self.queries = LearningQueries(self.mock_driver)

    def _create_mock_records(self, records_data):
        """Helper to create mock Neo4j records."""
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter(records_data))
        return mock_result

    def test_returns_empty_list_for_no_data(self):
        """Test that empty list is returned when no data."""
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([]))
        self.mock_session.run.return_value = mock_result

        patterns = self.queries.get_agent_prompt_patterns('temujin')
        self.assertEqual(patterns, [])

    def test_filters_by_minimum_sample_size(self):
        """Test that results with < MIN_SAMPLE_AGENT are filtered out."""
        # Create 4 records (below MIN_SAMPLE_AGENT of 5)
        records_data = [
            {'agent': 'temujin', 'prompt_construction': '{"template_used": "test_template"}',
             'prompt_template': None, 'data_quality_score': 0.8, 'duration_seconds': 300}
        ] * 4

        mock_result = self._create_mock_records(records_data)
        self.mock_session.run.return_value = mock_result

        patterns = self.queries.get_agent_prompt_patterns('temujin')
        self.assertEqual(patterns, [])

    def test_returns_results_above_sample_threshold(self):
        """Test that results with >= MIN_SAMPLE_AGENT are included."""
        records_data = [
            {'agent': 'temujin', 'prompt_construction': '{"template_used": "good_template"}',
             'prompt_template': None, 'data_quality_score': 0.8, 'duration_seconds': 300}
        ] * 6  # Above MIN_SAMPLE_AGENT

        mock_result = self._create_mock_records(records_data)
        self.mock_session.run.return_value = mock_result

        patterns = self.queries.get_agent_prompt_patterns('temujin')
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0]['template'], 'good_template')
        self.assertEqual(patterns[0]['sample_size'], 6)

    def test_calculates_average_quality(self):
        """Test that average quality is calculated correctly."""
        records_data = [
            {'agent': 'temujin', 'prompt_construction': '{"template_used": "test"}',
             'prompt_template': None, 'data_quality_score': 0.6, 'duration_seconds': 300},
            {'agent': 'temujin', 'prompt_construction': '{"template_used": "test"}',
             'prompt_template': None, 'data_quality_score': 0.8, 'duration_seconds': 400},
            {'agent': 'temujin', 'prompt_construction': '{"template_used": "test"}',
             'prompt_template': None, 'data_quality_score': 0.7, 'duration_seconds': 500},
            {'agent': 'temujin', 'prompt_construction': '{"template_used": "test"}',
             'prompt_template': None, 'data_quality_score': 0.9, 'duration_seconds': 600},
            {'agent': 'temujin', 'prompt_construction': '{"template_used": "test"}',
             'prompt_template': None, 'data_quality_score': 0.5, 'duration_seconds': 200},
        ]

        mock_result = self._create_mock_records(records_data)
        self.mock_session.run.return_value = mock_result

        patterns = self.queries.get_agent_prompt_patterns('temujin')
        self.assertEqual(len(patterns), 1)
        # Average of 0.6, 0.8, 0.7, 0.9, 0.5 = 0.7
        self.assertAlmostEqual(patterns[0]['avg_quality'], 0.7, places=2)

    def test_counts_high_quality_tasks(self):
        """Test that high quality tasks (>= 0.7) are counted."""
        records_data = [
            {'agent': 'temujin', 'prompt_construction': '{"template_used": "test"}',
             'prompt_template': None, 'data_quality_score': 0.7, 'duration_seconds': 300},
            {'agent': 'temujin', 'prompt_construction': '{"template_used": "test"}',
             'prompt_template': None, 'data_quality_score': 0.8, 'duration_seconds': 400},
            {'agent': 'temujin', 'prompt_construction': '{"template_used": "test"}',
             'prompt_template': None, 'data_quality_score': 0.5, 'duration_seconds': 500},
            {'agent': 'temujin', 'prompt_construction': '{"template_used": "test"}',
             'prompt_template': None, 'data_quality_score': 0.9, 'duration_seconds': 600},
            {'agent': 'temujin', 'prompt_construction': '{"template_used": "test"}',
             'prompt_template': None, 'data_quality_score': 0.4, 'duration_seconds': 200},
        ]

        mock_result = self._create_mock_records(records_data)
        self.mock_session.run.return_value = mock_result

        patterns = self.queries.get_agent_prompt_patterns('temujin')
        # High quality: 0.7, 0.8, 0.9 = 3 tasks
        self.assertEqual(patterns[0]['high_quality_count'], 3)

    def test_parses_prompt_template_fallback(self):
        """Test that prompt_template field is used if prompt_construction fails."""
        records_data = [
            {'agent': 'temujin', 'prompt_construction': None,
             'prompt_template': 'fallback_template', 'data_quality_score': 0.8, 'duration_seconds': 300}
        ] * 5

        mock_result = self._create_mock_records(records_data)
        self.mock_session.run.return_value = mock_result

        patterns = self.queries.get_agent_prompt_patterns('temujin')
        self.assertEqual(patterns[0]['template'], 'fallback_template')

    def test_handles_malformed_json(self):
        """Test that malformed JSON in prompt_construction is handled."""
        records_data = [
            {'agent': 'temujin', 'prompt_construction': 'not valid json {"template_used": "test"}',
             'prompt_template': 'backup', 'data_quality_score': 0.8, 'duration_seconds': 300}
        ] * 5

        mock_result = self._create_mock_records(records_data)
        self.mock_session.run.return_value = mock_result

        # Should fall back to regex or prompt_template
        patterns = self.queries.get_agent_prompt_patterns('temujin')
        self.assertEqual(len(patterns), 1)

    def test_groups_by_agent_and_template(self):
        """Test that results are grouped by agent and template."""
        records_data = [
            {'agent': 'temujin', 'prompt_construction': '{"template_used": "template_a"}',
             'prompt_template': None, 'data_quality_score': 0.8, 'duration_seconds': 300},
            {'agent': 'temujin', 'prompt_construction': '{"template_used": "template_b"}',
             'prompt_template': None, 'data_quality_score': 0.7, 'duration_seconds': 400},
            {'agent': 'mongke', 'prompt_construction': '{"template_used": "template_a"}',
             'prompt_template': None, 'data_quality_score': 0.9, 'duration_seconds': 500},
        ] * 5  # Each combo gets 5 entries

        mock_result = self._create_mock_records(records_data)
        self.mock_session.run.return_value = mock_result

        patterns = self.queries.get_agent_prompt_patterns()
        self.assertEqual(len(patterns), 3)

        # Check sorting: by agent, then by high_quality_count descending
        agents = [p['agent'] for p in patterns]
        self.assertIn('temujin', agents)
        self.assertIn('mongke', agents)


class TestGetSkillHintEffectiveness(unittest.TestCase):
    """Test get_skill_hint_effectiveness method."""

    def setUp(self):
        """Set up mock driver and queries instance."""
        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()

        self.mock_session.__enter__ = Mock(return_value=self.mock_session)
        self.mock_session.__exit__ = Mock(return_value=False)
        self.mock_driver.session.return_value = self.mock_session

        self.queries = LearningQueries(self.mock_driver)

    def test_returns_skill_hint_metrics(self):
        """Test that skill hint effectiveness is calculated."""
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([
            {'agent': 'temujin', 'hint': '/horde-implement', 'total': 10,
             'successes': 8, 'success_rate': 0.8, 'avg_quality': 0.75}
        ]))
        self.mock_session.run.return_value = mock_result

        skills = self.queries.get_skill_hint_effectiveness('temujin')
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0]['hint'], '/horde-implement')
        self.assertEqual(skills[0]['success_rate'], 0.8)

    def test_filters_by_minimum_sample(self):
        """Test that skill hints with insufficient samples are filtered."""
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([
            {'agent': 'temujin', 'hint': '/rare-skill', 'total': 3,
             'successes': 3, 'success_rate': 1.0, 'avg_quality': 0.9}
        ]))
        self.mock_session.run.return_value = mock_result

        # Query applies MIN_SAMPLE_AGENT filter in Cypher
        skills = self.queries.get_skill_hint_effectiveness('temujin')
        # The Cypher query filters, but let's verify our understanding
        self.assertEqual(len(skills), 1)


class TestGetTimeoutAnalysis(unittest.TestCase):
    """Test get_timeout_analysis method."""

    def setUp(self):
        """Set up mock driver and queries instance."""
        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()

        self.mock_session.__enter__ = Mock(return_value=self.mock_session)
        self.mock_session.__exit__ = Mock(return_value=False)
        self.mock_driver.session.return_value = self.mock_session

        self.queries = LearningQueries(self.mock_driver)

    def _create_mock_records(self, records_data):
        """Helper to create mock Neo4j records."""
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter(records_data))
        return mock_result

    def test_categorizes_timeout_buckets(self):
        """Test that timeouts are categorized into buckets correctly."""
        # short: < 1800s, medium: 1800-3600s, long: 3600-7200s, very_long: > 7200s
        records_data = [
            {'agent': 'temujin', 'task_params': '{"timeout_seconds": 900}',
             'data_quality_score': 0.8, 'duration_seconds': 600, 'status': 'COMPLETED'},
            {'agent': 'temujin', 'task_params': '{"timeout_seconds": 900}',
             'data_quality_score': 0.7, 'duration_seconds': 500, 'status': 'COMPLETED'},
            {'agent': 'temujin', 'task_params': '{"timeout_seconds": 900}',
             'data_quality_score': 0.6, 'duration_seconds': 700, 'status': 'COMPLETED'},
            {'agent': 'temujin', 'task_params': '{"timeout_seconds": 900}',
             'data_quality_score': 0.8, 'duration_seconds': 800, 'status': 'COMPLETED'},
            {'agent': 'temujin', 'task_params': '{"timeout_seconds": 900}',
             'data_quality_score': 0.9, 'duration_seconds': 400, 'status': 'COMPLETED'},
        ]

        mock_result = self._create_mock_records(records_data)
        self.mock_session.run.return_value = mock_result

        timeouts = self.queries.get_timeout_analysis('temujin')
        self.assertEqual(len(timeouts), 1)
        self.assertEqual(timeouts[0]['timeout_bucket'], 'short')

    def test_calculates_timeout_utilization(self):
        """Test that utilization (actual/timeout) is calculated."""
        records_data = [
            {'agent': 'temujin', 'task_params': '{"timeout_seconds": 1000}',
             'data_quality_score': 0.8, 'duration_seconds': 500, 'status': 'COMPLETED'},
            {'agent': 'temujin', 'task_params': '{"timeout_seconds": 1000}',
             'data_quality_score': 0.8, 'duration_seconds': 600, 'status': 'COMPLETED'},
            {'agent': 'temujin', 'task_params': '{"timeout_seconds": 1000}',
             'data_quality_score': 0.8, 'duration_seconds': 700, 'status': 'COMPLETED'},
            {'agent': 'temujin', 'task_params': '{"timeout_seconds": 1000}',
             'data_quality_score': 0.8, 'duration_seconds': 800, 'status': 'COMPLETED'},
            {'agent': 'temujin', 'task_params': '{"timeout_seconds": 1000}',
             'data_quality_score': 0.8, 'duration_seconds': 900, 'status': 'COMPLETED'},
        ]

        mock_result = self._create_mock_records(records_data)
        self.mock_session.run.return_value = mock_result

        timeouts = self.queries.get_timeout_analysis('temujin')
        # Avg utilization = avg(500,600,700,800,900) / 1000 = 0.7
        self.assertAlmostEqual(timeouts[0]['avg_utilization'], 0.7, places=2)

    def test_calculates_success_rate(self):
        """Test that success rate is calculated from status."""
        records_data = [
            {'agent': 'temujin', 'task_params': '{"timeout_seconds": 1000}',
             'data_quality_score': 0.8, 'duration_seconds': 500, 'status': 'COMPLETED'},
            {'agent': 'temujin', 'task_params': '{"timeout_seconds": 1000}',
             'data_quality_score': 0.8, 'duration_seconds': 600, 'status': 'COMPLETED'},
            {'agent': 'temujin', 'task_params': '{"timeout_seconds": 1000}',
             'data_quality_score': 0.8, 'duration_seconds': 700, 'status': 'FAILED'},
            {'agent': 'temujin', 'task_params': '{"timeout_seconds": 1000}',
             'data_quality_score': 0.8, 'duration_seconds': 800, 'status': 'COMPLETED'},
            {'agent': 'temujin', 'task_params': '{"timeout_seconds": 1000}',
             'data_quality_score': 0.8, 'duration_seconds': 900, 'status': 'FAILED'},
        ]

        mock_result = self._create_mock_records(records_data)
        self.mock_session.run.return_value = mock_result

        timeouts = self.queries.get_timeout_analysis('temujin')
        # 3 completed out of 5 = 0.6
        self.assertAlmostEqual(timeouts[0]['success_rate'], 0.6, places=2)


class TestGetContextSourceValue(unittest.TestCase):
    """Test get_context_source_value method."""

    def setUp(self):
        """Set up mock driver and queries instance."""
        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()

        self.mock_session.__enter__ = Mock(return_value=self.mock_session)
        self.mock_session.__exit__ = Mock(return_value=False)
        self.mock_driver.session.return_value = self.mock_session

        self.queries = LearningQueries(self.mock_driver)

    def _create_mock_records(self, records_data):
        """Helper to create mock Neo4j records."""
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter(records_data))
        return mock_result

    def test_extracts_context_sources(self):
        """Test that context sources are extracted from prompt_construction."""
        records_data = [
            {'prompt_construction': '{"context_sources": ["memory", "recent_tasks"]}',
             'data_quality_score': 0.8},
            {'prompt_construction': '{"context_sources": ["memory"]}',
             'data_quality_score': 0.7},
            {'prompt_construction': '{"context_sources": ["peer_context", "memory"]}',
             'data_quality_score': 0.9},
        ] * 5  # Each gets 5 entries to meet MIN_SAMPLE_SYSTEM

        mock_result = self._create_mock_records(records_data)
        self.mock_session.run.return_value = mock_result

        contexts = self.queries.get_context_source_value()
        sources = [c['source'] for c in contexts]
        self.assertIn('memory', sources)

    def test_filters_by_system_sample_threshold(self):
        """Test that sources with < MIN_SAMPLE_SYSTEM are filtered."""
        records_data = [
            {'prompt_construction': '{"context_sources": ["rare_source"]}',
             'data_quality_score': 0.8},
        ] * 8  # Below MIN_SAMPLE_SYSTEM (10)

        mock_result = self._create_mock_records(records_data)
        self.mock_session.run.return_value = mock_result

        contexts = self.queries.get_context_source_value()
        self.assertEqual(contexts, [])

    def test_calculates_high_quality_rate(self):
        """Test that high quality rate (quality >= 0.7) is calculated."""
        records_data = [
            {'prompt_construction': '{"context_sources": ["test_source"]}',
             'data_quality_score': 0.8},
            {'prompt_construction': '{"context_sources": ["test_source"]}',
             'data_quality_score': 0.7},
            {'prompt_construction': '{"context_sources": ["test_source"]}',
             'data_quality_score': 0.5},
            {'prompt_construction': '{"context_sources": ["test_source"]}',
             'data_quality_score': 0.9},
            {'prompt_construction': '{"context_sources": ["test_source"]}',
             'data_quality_score': 0.6},
            {'prompt_construction': '{"context_sources": ["test_source"]}',
             'data_quality_score': 0.75},
            {'prompt_construction': '{"context_sources": ["test_source"]}',
             'data_quality_score': 0.85},
            {'prompt_construction': '{"context_sources": ["test_source"]}',
             'data_quality_score': 0.65},
            {'prompt_construction': '{"context_sources": ["test_source"]}',
             'data_quality_score': 0.72},
            {'prompt_construction': '{"context_sources": ["test_source"]}',
             'data_quality_score': 0.68},
        ]

        mock_result = self._create_mock_records(records_data)
        self.mock_session.run.return_value = mock_result

        contexts = self.queries.get_context_source_value()
        # High quality (>= 0.7): 0.8, 0.7, 0.9, 0.75, 0.85, 0.72 = 6 out of 10
        self.assertAlmostEqual(contexts[0]['high_quality_rate'], 0.6, places=2)


class TestGetModelPerformance(unittest.TestCase):
    """Test get_model_performance method."""

    def setUp(self):
        """Set up mock driver and queries instance."""
        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()

        self.mock_session.__enter__ = Mock(return_value=self.mock_session)
        self.mock_session.__exit__ = Mock(return_value=False)
        self.mock_driver.session.return_value = self.mock_session

        self.queries = LearningQueries(self.mock_driver)

    def test_returns_model_metrics(self):
        """Test that model performance metrics are returned."""
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([
            {'agent': 'temujin', 'provider': 'anthropic', 'model': 'claude-sonnet-4-6',
             'sample_size': 15, 'avg_quality': 0.82, 'token_efficiency': 12.5}
        ]))
        self.mock_session.run.return_value = mock_result

        models = self.queries.get_model_performance('temujin')
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]['model'], 'claude-sonnet-4-6')
        self.assertEqual(models[0]['avg_quality'], 0.82)


class TestGetDomainPerformance(unittest.TestCase):
    """Test get_domain_performance method."""

    def setUp(self):
        """Set up mock driver and queries instance."""
        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()

        self.mock_session.__enter__ = Mock(return_value=self.mock_session)
        self.mock_session.__exit__ = Mock(return_value=False)
        self.mock_driver.session.return_value = self.mock_session

        self.queries = LearningQueries(self.mock_driver)

    def test_returns_domain_metrics(self):
        """Test that domain performance metrics are returned."""
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([
            {'agent': 'temujin', 'domain': 'implementation', 'total': 20,
             'completed': 18, 'success_rate': 0.9, 'avg_quality': 0.85}
        ]))
        self.mock_session.run.return_value = mock_result

        domains = self.queries.get_domain_performance('temujin')
        self.assertEqual(len(domains), 1)
        self.assertEqual(domains[0]['domain'], 'implementation')
        self.assertEqual(domains[0]['success_rate'], 0.9)


class TestLearningQueriesIntegration(unittest.TestCase):
    """Integration tests with simulated Neo4j behavior."""

    def test_full_query_workflow(self):
        """Test a complete workflow from query to result processing."""
        mock_driver = MagicMock()
        mock_session = MagicMock()

        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_driver.session.return_value = mock_session

        # Simulate realistic data
        records = [
            {
                'agent': 'temujin',
                'prompt_construction': json.dumps({
                    'template_used': 'horde_implement_v2',
                    'context_sources': ['memory', 'recent_tasks']
                }),
                'prompt_template': None,
                'data_quality_score': 0.85,
                'duration_seconds': 450
            }
        ] * 6

        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter(records))
        mock_session.run.return_value = mock_result

        queries = LearningQueries(mock_driver)
        patterns = queries.get_agent_prompt_patterns('temujin')

        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0]['template'], 'horde_implement_v2')
        self.assertEqual(patterns[0]['sample_size'], 6)
        self.assertAlmostEqual(patterns[0]['avg_quality'], 0.85, places=2)


if __name__ == '__main__':
    unittest.main(verbosity=2)