#!/usr/bin/env python3
"""
Unit Tests for Kublai Learning Generator

Tests the KublaiLearningGenerator class with mocked Neo4j driver.
Covers all learning generation methods and TTL logic.
"""

import os
import sys
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch, call

# Add scripts directory to path
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)


class TestKublaiLearningGeneratorConstants(unittest.TestCase):
    """Test class constants."""

    def test_learning_ttl_days(self):
        """Test that LEARNING_TTL_DAYS is 14."""
        from kublai_learning_generator import KublaiLearningGenerator
        self.assertEqual(KublaiLearningGenerator.LEARNING_TTL_DAYS, 14)

    def test_learning_types(self):
        """Test that all 6 learning types are defined."""
        from kublai_learning_generator import KublaiLearningGenerator
        expected_types = ['prompt_pattern', 'skill_hint', 'timeout', 'context', 'model', 'domain']
        self.assertEqual(KublaiLearningGenerator.LEARNING_TYPES, expected_types)


class TestKublaiLearningGeneratorInit(unittest.TestCase):
    """Test generator initialization."""

    def test_initializes_with_driver(self):
        """Test that generator initializes with driver."""
        from kublai_learning_generator import KublaiLearningGenerator
        mock_driver = MagicMock()

        generator = KublaiLearningGenerator(mock_driver)

        self.assertEqual(generator.driver, mock_driver)
        self.assertIsNotNone(generator.queries)
        self.assertEqual(generator.stats['created'], 0)
        self.assertEqual(generator.stats['deprecated'], 0)
        self.assertEqual(generator.stats['skipped'], 0)
        self.assertEqual(generator.stats['errors'], [])


class TestGenerateLearningId(unittest.TestCase):
    """Test learning ID generation."""

    def test_generates_unique_ids(self):
        """Test that unique IDs are generated."""
        from kublai_learning_generator import KublaiLearningGenerator
        mock_driver = MagicMock()
        generator = KublaiLearningGenerator(mock_driver)

        id1 = generator.generate_learning_id()
        id2 = generator.generate_learning_id()

        self.assertTrue(id1.startswith('kl-'))
        self.assertTrue(id2.startswith('kl-'))
        self.assertNotEqual(id1, id2)

    def test_id_format(self):
        """Test that ID format is correct."""
        from kublai_learning_generator import KublaiLearningGenerator
        mock_driver = MagicMock()
        generator = KublaiLearningGenerator(mock_driver)

        learning_id = generator.generate_learning_id()

        # Format: kl-{12 hex chars}
        self.assertRegex(learning_id, r'^kl-[a-f0-9]{12}$')


class TestCalculateValidUntil(unittest.TestCase):
    """Test TTL calculation."""

    def test_calculates_14_days_ahead(self):
        """Test that valid_until is 14 days in the future."""
        from kublai_learning_generator import KublaiLearningGenerator
        mock_driver = MagicMock()
        generator = KublaiLearningGenerator(mock_driver)

        valid_until_str = generator.calculate_valid_until()
        valid_until = datetime.fromisoformat(valid_until_str)

        expected = datetime.now() + timedelta(days=14)
        delta = abs((valid_until - expected).total_seconds())

        # Allow 1 second tolerance for test execution time
        self.assertLess(delta, 1)


class TestDeprecateOldLearnings(unittest.TestCase):
    """Test deprecation of old learnings."""

    def setUp(self):
        """Set up mocks."""
        from kublai_learning_generator import KublaiLearningGenerator
        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()

        self.mock_session.__enter__ = Mock(return_value=self.mock_session)
        self.mock_session.__exit__ = Mock(return_value=False)
        self.mock_driver.session.return_value = self.mock_session

        self.generator = KublaiLearningGenerator(self.mock_driver)

    def test_deprecates_matching_learnings(self):
        """Test that matching learnings are deprecated."""
        mock_result = MagicMock()
        mock_result.single.return_value = {"deprecated_count": 2}
        self.mock_session.run.return_value = mock_result

        self.generator.deprecate_old_learnings('prompt_pattern', 'test_template', 'temujin')

        self.assertEqual(self.generator.stats['deprecated'], 2)

    def test_deprecates_system_wide_learnings(self):
        """Test deprecation without agent filter."""
        mock_result = MagicMock()
        mock_result.single.return_value = {"deprecated_count": 1}
        self.mock_session.run.return_value = mock_result

        self.generator.deprecate_old_learnings('context', 'memory')

        self.assertEqual(self.generator.stats['deprecated'], 1)


class TestCreatePromptPatternLearnings(unittest.TestCase):
    """Test prompt pattern learning generation."""

    def setUp(self):
        """Set up mocks."""
        from kublai_learning_generator import KublaiLearningGenerator
        from kublai_learning_queries import LearningQueries

        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()

        self.mock_session.__enter__ = Mock(return_value=self.mock_session)
        self.mock_session.__exit__ = Mock(return_value=False)
        self.mock_driver.session.return_value = self.mock_session

        self.generator = KublaiLearningGenerator(self.mock_driver)

        # Mock the queries object
        self.mock_queries = MagicMock()
        self.generator.queries = self.mock_queries

    def test_creates_learning_for_high_quality_template(self):
        """Test that learning is created for high-quality template."""
        # Mock query results
        self.mock_queries.get_agent_prompt_patterns.return_value = [
            {
                'agent': 'temujin',
                'template': 'horde_implement_v2',
                'sample_size': 10,
                'avg_quality': 0.85,
                'high_quality_count': 8,
                'avg_duration': 450
            }
        ]
        self.mock_queries.get_baseline_quality.return_value = 0.70
        self.mock_queries.calculate_confidence.return_value = 0.85
        self.mock_queries.MIN_SAMPLE_AGENT = 5

        # Mock deprecation result
        deprecate_result = MagicMock()
        deprecate_result.single.return_value = {"deprecated_count": 0}

        # Mock create result
        create_result = MagicMock()

        def session_run_side_effect(*args, **kwargs):
            if 'MATCH' in str(args[0]) if args else '':
                return deprecate_result
            return create_result

        self.mock_session.run.side_effect = session_run_side_effect

        results = self.generator.create_prompt_pattern_learnings('temujin')

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['template'], 'horde_implement_v2')
        self.assertEqual(self.generator.stats['created'], 1)

    def test_skips_below_sample_threshold(self):
        """Test that templates below sample threshold are skipped."""
        self.mock_queries.get_agent_prompt_patterns.return_value = [
            {
                'agent': 'temujin',
                'template': 'rare_template',
                'sample_size': 3,  # Below MIN_SAMPLE_AGENT
                'avg_quality': 0.9,
                'high_quality_count': 3,
                'avg_duration': 200
            }
        ]
        self.mock_queries.MIN_SAMPLE_AGENT = 5

        results = self.generator.create_prompt_pattern_learnings('temujin')

        self.assertEqual(len(results), 0)
        self.assertEqual(self.generator.stats['skipped'], 1)

    def test_skips_below_baseline_quality(self):
        """Test that templates below baseline are skipped."""
        self.mock_queries.get_agent_prompt_patterns.return_value = [
            {
                'agent': 'temujin',
                'template': 'poor_template',
                'sample_size': 10,
                'avg_quality': 0.5,  # Below baseline
                'high_quality_count': 3,
                'avg_duration': 300
            }
        ]
        self.mock_queries.get_baseline_quality.return_value = 0.70
        self.mock_queries.MIN_SAMPLE_AGENT = 5

        results = self.generator.create_prompt_pattern_learnings('temujin')

        self.assertEqual(len(results), 0)
        self.assertEqual(self.generator.stats['skipped'], 1)


class TestCreateSkillHintLearnings(unittest.TestCase):
    """Test skill hint learning generation."""

    def setUp(self):
        """Set up mocks."""
        from kublai_learning_generator import KublaiLearningGenerator

        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()

        self.mock_session.__enter__ = Mock(return_value=self.mock_session)
        self.mock_session.__exit__ = Mock(return_value=False)
        self.mock_driver.session.return_value = self.mock_session

        self.generator = KublaiLearningGenerator(self.mock_driver)
        self.mock_queries = MagicMock()
        self.generator.queries = self.mock_queries

    def test_creates_learning_for_high_success_skill(self):
        """Test that learning is created for high success rate skill."""
        self.mock_queries.get_skill_hint_effectiveness.return_value = [
            {
                'agent': 'temujin',
                'hint': '/horde-implement',
                'total': 15,
                'success_rate': 0.85,
                'avg_quality': 0.80
            }
        ]
        self.mock_queries.calculate_confidence.return_value = 0.88
        self.mock_queries.MIN_SAMPLE_AGENT = 5

        deprecate_result = MagicMock()
        deprecate_result.single.return_value = {"deprecated_count": 0}
        create_result = MagicMock()

        def session_run_side_effect(*args, **kwargs):
            if 'MATCH' in str(args[0]) if args else '':
                return deprecate_result
            return create_result

        self.mock_session.run.side_effect = session_run_side_effect

        results = self.generator.create_skill_hint_learnings('temujin')

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['hint'], '/horde-implement')

    def test_skips_low_success_rate(self):
        """Test that skills with low success rate are skipped."""
        self.mock_queries.get_skill_hint_effectiveness.return_value = [
            {
                'agent': 'temujin',
                'hint': '/experimental-skill',
                'total': 10,
                'success_rate': 0.45,  # Below 0.6 threshold
                'avg_quality': 0.50
            }
        ]
        self.mock_queries.MIN_SAMPLE_AGENT = 5

        results = self.generator.create_skill_hint_learnings('temujin')

        self.assertEqual(len(results), 0)
        self.assertEqual(self.generator.stats['skipped'], 1)


class TestCreateTimeoutLearnings(unittest.TestCase):
    """Test timeout learning generation."""

    def setUp(self):
        """Set up mocks."""
        from kublai_learning_generator import KublaiLearningGenerator

        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()

        self.mock_session.__enter__ = Mock(return_value=self.mock_session)
        self.mock_session.__exit__ = Mock(return_value=False)
        self.mock_driver.session.return_value = self.mock_session

        self.generator = KublaiLearningGenerator(self.mock_driver)
        self.mock_queries = MagicMock()
        self.generator.queries = self.mock_queries

    def test_creates_learning_for_good_utilization(self):
        """Test that learning is created for good timeout utilization."""
        self.mock_queries.get_timeout_analysis.return_value = [
            {
                'agent': 'temujin',
                'timeout_bucket': 'medium',
                'tasks': 10,
                'avg_quality': 0.75,
                'avg_utilization': 0.65,  # Between 0.3 and 0.95
                'success_rate': 0.80
            }
        ]
        self.mock_queries.calculate_confidence.return_value = 0.75
        self.mock_queries.MIN_SAMPLE_AGENT = 5

        create_result = MagicMock()
        self.mock_session.run.return_value = create_result

        results = self.generator.create_timeout_learnings('temujin')

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['bucket'], 'medium')

    def test_skips_low_utilization(self):
        """Test that timeouts with low utilization are skipped."""
        self.mock_queries.get_timeout_analysis.return_value = [
            {
                'agent': 'temujin',
                'timeout_bucket': 'very_long',
                'tasks': 10,
                'avg_quality': 0.75,
                'avg_utilization': 0.20,  # Below 0.3
                'success_rate': 0.80
            }
        ]
        self.mock_queries.MIN_SAMPLE_AGENT = 5

        results = self.generator.create_timeout_learnings('temujin')

        self.assertEqual(len(results), 0)
        self.assertEqual(self.generator.stats['skipped'], 1)

    def test_skips_high_utilization(self):
        """Test that timeouts with very high utilization are skipped."""
        self.mock_queries.get_timeout_analysis.return_value = [
            {
                'agent': 'temujin',
                'timeout_bucket': 'short',
                'tasks': 10,
                'avg_quality': 0.75,
                'avg_utilization': 0.98,  # Above 0.95
                'success_rate': 0.60
            }
        ]
        self.mock_queries.MIN_SAMPLE_AGENT = 5

        results = self.generator.create_timeout_learnings('temujin')

        self.assertEqual(len(results), 0)


class TestCreateContextLearnings(unittest.TestCase):
    """Test context source learning generation."""

    def setUp(self):
        """Set up mocks."""
        from kublai_learning_generator import KublaiLearningGenerator

        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()

        self.mock_session.__enter__ = Mock(return_value=self.mock_session)
        self.mock_session.__exit__ = Mock(return_value=False)
        self.mock_driver.session.return_value = self.mock_session

        self.generator = KublaiLearningGenerator(self.mock_driver)
        self.mock_queries = MagicMock()
        self.generator.queries = self.mock_queries

    def test_creates_learning_for_high_value_source(self):
        """Test that learning is created for high-value context source."""
        self.mock_queries.get_context_source_value.return_value = [
            {
                'source': 'memory',
                'frequency': 15,
                'avg_quality': 0.82,
                'high_quality_rate': 0.70
            }
        ]
        self.mock_queries.calculate_confidence.return_value = 0.80
        self.mock_queries.MIN_SAMPLE_SYSTEM = 10

        create_result = MagicMock()
        self.mock_session.run.return_value = create_result

        results = self.generator.create_context_learnings()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['source'], 'memory')

    def test_skips_low_quality_source(self):
        """Test that low-quality sources are skipped."""
        self.mock_queries.get_context_source_value.return_value = [
            {
                'source': 'unreliable_source',
                'frequency': 15,
                'avg_quality': 0.45,  # Below 0.6 threshold
                'high_quality_rate': 0.30
            }
        ]
        self.mock_queries.MIN_SAMPLE_SYSTEM = 10

        results = self.generator.create_context_learnings()

        self.assertEqual(len(results), 0)
        self.assertEqual(self.generator.stats['skipped'], 1)


class TestCreateModelLearnings(unittest.TestCase):
    """Test model performance learning generation."""

    def setUp(self):
        """Set up mocks."""
        from kublai_learning_generator import KublaiLearningGenerator

        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()

        self.mock_session.__enter__ = Mock(return_value=self.mock_session)
        self.mock_session.__exit__ = Mock(return_value=False)
        self.mock_driver.session.return_value = self.mock_session

        self.generator = KublaiLearningGenerator(self.mock_driver)
        self.mock_queries = MagicMock()
        self.generator.queries = self.mock_queries

    def test_creates_learning_for_high_performing_model(self):
        """Test that learning is created for high-performing model."""
        self.mock_queries.get_model_performance.return_value = [
            {
                'agent': 'temujin',
                'provider': 'anthropic',
                'model': 'claude-sonnet-4-6',
                'sample_size': 12,
                'avg_quality': 0.82,
                'token_efficiency': 15.5
            }
        ]
        self.mock_queries.calculate_confidence.return_value = 0.85
        self.mock_queries.MIN_SAMPLE_AGENT = 5

        create_result = MagicMock()
        self.mock_session.run.return_value = create_result

        results = self.generator.create_model_learnings('temujin')

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['model'], 'anthropic:claude-sonnet-4-6')

    def test_skips_low_quality_model(self):
        """Test that low-quality models are skipped."""
        self.mock_queries.get_model_performance.return_value = [
            {
                'agent': 'temujin',
                'provider': 'test',
                'model': 'test-model',
                'sample_size': 10,
                'avg_quality': 0.55,  # Below 0.65 threshold
                'token_efficiency': 8.0
            }
        ]
        self.mock_queries.MIN_SAMPLE_AGENT = 5

        results = self.generator.create_model_learnings('temujin')

        self.assertEqual(len(results), 0)
        self.assertEqual(self.generator.stats['skipped'], 1)


class TestCreateDomainLearnings(unittest.TestCase):
    """Test domain specialization learning generation."""

    def setUp(self):
        """Set up mocks."""
        from kublai_learning_generator import KublaiLearningGenerator

        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()

        self.mock_session.__enter__ = Mock(return_value=self.mock_session)
        self.mock_session.__exit__ = Mock(return_value=False)
        self.mock_driver.session.return_value = self.mock_session

        self.generator = KublaiLearningGenerator(self.mock_driver)
        self.mock_queries = MagicMock()
        self.generator.queries = self.mock_queries

    def test_creates_learning_for_strong_domain(self):
        """Test that learning is created for strong domain fit."""
        self.mock_queries.get_domain_performance.return_value = [
            {
                'agent': 'temujin',
                'domain': 'implementation',
                'total': 15,
                'completed': 13,
                'success_rate': 0.87,
                'avg_quality': 0.82
            }
        ]
        self.mock_queries.calculate_confidence.return_value = 0.85
        self.mock_queries.MIN_SAMPLE_AGENT = 5

        create_result = MagicMock()
        self.mock_session.run.return_value = create_result

        results = self.generator.create_domain_learnings('temujin')

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['domain'], 'implementation')

    def test_skips_low_success_domain(self):
        """Test that domains with low success rate are skipped."""
        self.mock_queries.get_domain_performance.return_value = [
            {
                'agent': 'temujin',
                'domain': 'experimental',
                'total': 10,
                'completed': 5,
                'success_rate': 0.50,  # Below 0.7 threshold
                'avg_quality': 0.60
            }
        ]
        self.mock_queries.MIN_SAMPLE_AGENT = 5

        results = self.generator.create_domain_learnings('temujin')

        self.assertEqual(len(results), 0)
        self.assertEqual(self.generator.stats['skipped'], 1)


class TestGenerateAll(unittest.TestCase):
    """Test generate_all method."""

    def setUp(self):
        """Set up mocks."""
        from kublai_learning_generator import KublaiLearningGenerator

        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()

        self.mock_session.__enter__ = Mock(return_value=self.mock_session)
        self.mock_session.__exit__ = Mock(return_value=False)
        self.mock_driver.session.return_value = self.mock_session

        self.generator = KublaiLearningGenerator(self.mock_driver)
        self.mock_queries = MagicMock()
        self.generator.queries = self.mock_queries

    def test_generates_all_learning_types(self):
        """Test that all learning types are generated."""
        # Mock all query methods to return empty lists
        self.mock_queries.get_agent_prompt_patterns.return_value = []
        self.mock_queries.get_skill_hint_effectiveness.return_value = []
        self.mock_queries.get_timeout_analysis.return_value = []
        self.mock_queries.get_context_source_value.return_value = []
        self.mock_queries.get_model_performance.return_value = []
        self.mock_queries.get_domain_performance.return_value = []
        self.mock_queries.MIN_SAMPLE_AGENT = 5
        self.mock_queries.MIN_SAMPLE_SYSTEM = 10

        results = self.generator.generate_all()

        self.assertIn('created', results)
        self.assertIn('deprecated', results)
        self.assertIn('skipped', results)
        self.assertIn('errors', results)
        self.assertIn('learnings', results)

    def test_filters_by_learning_type(self):
        """Test that specific learning types can be filtered."""
        self.mock_queries.get_agent_prompt_patterns.return_value = []
        self.mock_queries.MIN_SAMPLE_AGENT = 5

        results = self.generator.generate_all(learning_types=['prompt_pattern'])

        # Should only call the specified learning type
        self.mock_queries.get_agent_prompt_patterns.assert_called()

    def test_tracks_errors(self):
        """Test that errors are tracked."""
        self.mock_queries.get_agent_prompt_patterns.side_effect = Exception("Test error")
        self.mock_queries.MIN_SAMPLE_AGENT = 5

        results = self.generator.generate_all(learning_types=['prompt_pattern'])

        self.assertEqual(len(results['errors']), 1)
        self.assertIn('Test error', results['errors'][0])


class TestCleanupExpiredLearnings(unittest.TestCase):
    """Test expired learning cleanup."""

    def setUp(self):
        """Set up mocks."""
        from kublai_learning_generator import KublaiLearningGenerator

        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()

        self.mock_session.__enter__ = Mock(return_value=self.mock_session)
        self.mock_session.__exit__ = Mock(return_value=False)
        self.mock_driver.session.return_value = self.mock_session

        self.generator = KublaiLearningGenerator(self.mock_driver)

    def test_archives_expired_learnings(self):
        """Test that expired learnings are archived."""
        mock_result = MagicMock()
        mock_result.single.return_value = {"expired_count": 5}
        self.mock_session.run.return_value = mock_result

        expired_count = self.generator.cleanup_expired_learnings()

        self.assertEqual(expired_count, 5)

    def test_handles_no_expired(self):
        """Test handling when no expired learnings exist."""
        mock_result = MagicMock()
        mock_result.single.return_value = {"expired_count": 0}
        self.mock_session.run.return_value = mock_result

        expired_count = self.generator.cleanup_expired_learnings()

        self.assertEqual(expired_count, 0)


class TestGetActiveLearningsSummary(unittest.TestCase):
    """Test active learnings summary."""

    def setUp(self):
        """Set up mocks."""
        from kublai_learning_generator import KublaiLearningGenerator

        self.mock_driver = MagicMock()
        self.mock_session = MagicMock()

        self.mock_session.__enter__ = Mock(return_value=self.mock_session)
        self.mock_session.__exit__ = Mock(return_value=False)
        self.mock_driver.session.return_value = self.mock_session

        self.generator = KublaiLearningGenerator(self.mock_driver)

    def test_returns_summary(self):
        """Test that summary is returned correctly."""
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([
            {'type': 'prompt_pattern', 'count': 5, 'avg_confidence': 0.85, 'avg_sample_size': 12},
            {'type': 'skill_hint', 'count': 3, 'avg_confidence': 0.78, 'avg_sample_size': 8}
        ]))
        self.mock_session.run.return_value = mock_result

        summary = self.generator.get_active_learnings_summary()

        self.assertEqual(len(summary), 2)
        self.assertEqual(summary[0]['type'], 'prompt_pattern')


class TestTTLLearningExpiry(unittest.TestCase):
    """Test 14-day TTL expiry logic."""

    def test_learning_node_has_14_day_ttl(self):
        """Test that learning nodes have 14-day valid_until."""
        from kublai_learning_generator import KublaiLearningGenerator

        mock_driver = MagicMock()
        mock_session = MagicMock()

        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)
        mock_driver.session.return_value = mock_session

        generator = KublaiLearningGenerator(mock_driver)

        # Verify the TTL constant
        self.assertEqual(generator.LEARNING_TTL_DAYS, 14)

        # Verify calculate_valid_until produces 14-day future date
        valid_until = generator.calculate_valid_until()
        valid_date = datetime.fromisoformat(valid_until)

        expected = datetime.now() + timedelta(days=14)
        delta = abs((valid_date - expected).total_seconds())

        self.assertLess(delta, 1, "TTL should be exactly 14 days")


class TestStatisticalThresholds(unittest.TestCase):
    """Test statistical threshold validation."""

    def test_agent_threshold_is_5(self):
        """Test that agent-specific minimum sample is 5."""
        from kublai_learning_queries import LearningQueries
        self.assertEqual(LearningQueries.MIN_SAMPLE_AGENT, 5)

    def test_system_threshold_is_10(self):
        """Test that system-wide minimum sample is 10."""
        from kublai_learning_queries import LearningQueries
        self.assertEqual(LearningQueries.MIN_SAMPLE_SYSTEM, 10)

    def test_high_confidence_threshold_is_15(self):
        """Test that high confidence minimum sample is 15."""
        from kublai_learning_queries import LearningQueries
        self.assertEqual(LearningQueries.MIN_SAMPLE_HIGH_CONFIDENCE, 15)


if __name__ == '__main__':
    unittest.main(verbosity=2)