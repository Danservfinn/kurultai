"""
Unit Tests for MVS (Memory Value Score) Scorer Module

Tests the MVS formula:
MVS = (
    type_weight
    + recency_bonus
    + frequency_bonus
    + quality_bonus
    + centrality_bonus
    + cross_agent_bonus
    - bloat_penalty
) * safety_multiplier
"""

import pytest
import math
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../tools/kurultai'))

from mvs_scorer import (
    MVSScorer, TYPE_WEIGHTS, HALF_LIVES, TIER_TARGETS,
    calculate_recency_bonus, calculate_frequency_bonus,
    calculate_quality_bonus, calculate_centrality_bonus,
    calculate_cross_agent_bonus, calculate_bloat_penalty
)


class TestTypeWeights:
    """Tests for TYPE_WEIGHTS configuration."""

    def test_all_types_defined(self):
        """Verify all expected node types have weights."""
        expected_types = [
            'Belief', 'Reflection', 'Analysis', 'Synthesis',
            'Recommendation', 'CompressedContext', 'Task',
            'MemoryEntry', 'SessionContext', 'Notification'
        ]
        
        for node_type in expected_types:
            assert node_type in TYPE_WEIGHTS, f"Type {node_type} not in TYPE_WEIGHTS"
            assert TYPE_WEIGHTS[node_type] > 0, f"Weight for {node_type} must be positive"

    def test_belief_highest_weight(self):
        """Verify Belief has the highest weight."""
        max_weight = max(TYPE_WEIGHTS.values())
        assert TYPE_WEIGHTS['Belief'] == max_weight
        assert TYPE_WEIGHTS['Belief'] == 10.0

    def test_notification_lowest_weight(self):
        """Verify Notification has the lowest weight."""
        min_weight = min(TYPE_WEIGHTS.values())
        assert TYPE_WEIGHTS['Notification'] == min_weight
        assert TYPE_WEIGHTS['Notification'] == 0.5


class TestRecencyBonus:
    """Tests for recency bonus calculation."""

    def test_fresh_entry_max_bonus(self):
        """Test that very fresh entries get max recency bonus."""
        scorer = MVSScorer()
        created_at = datetime.now(timezone.utc)
        
        bonus = scorer.calculate_recency_bonus(created_at, 'Belief')
        
        assert bonus == 3.0

    def test_old_entry_min_bonus(self):
        """Test that old entries get close to 0 bonus."""
        scorer = MVSScorer()
        created_at = datetime.now(timezone.utc) - timedelta(days=365)
        
        bonus = scorer.calculate_recency_bonus(created_at, 'MemoryEntry')
        
        assert bonus < 0.5  # Should be very small after a year
        assert bonus >= 0

    def test_protected_types_max_bonus(self):
        """Test that protected types always get max bonus."""
        scorer = MVSScorer()
        old_date = datetime.now(timezone.utc) - timedelta(days=1000)
        
        bonus = scorer.calculate_recency_bonus(old_date, 'Task')
        
        assert bonus == 3.0  # Tasks are protected

    def test_half_life_decay(self):
        """Test exponential decay at half-life."""
        scorer = MVSScorer()
        half_life = HALF_LIVES['Belief']  # 180 days
        created_at = datetime.now(timezone.utc) - timedelta(days=half_life)
        
        bonus = scorer.calculate_recency_bonus(created_at, 'Belief')
        
        # At half-life, bonus should be approximately 1.5 (half of 3.0)
        assert abs(bonus - 1.5) < 0.1


class TestFrequencyBonus:
    """Tests for frequency bonus calculation."""

    def test_no_access_zero_bonus(self):
        """Test that entries with no access get 0 bonus."""
        scorer = MVSScorer()
        
        bonus = scorer.calculate_frequency_bonus(0)
        
        assert bonus == 0.0

    def test_single_access_small_bonus(self):
        """Test single access gives small bonus."""
        scorer = MVSScorer()
        
        bonus = scorer.calculate_frequency_bonus(1)
        
        assert bonus > 0
        assert bonus < 0.5

    def test_high_access_max_bonus(self):
        """Test that high access count caps at max bonus."""
        scorer = MVSScorer()
        
        bonus = scorer.calculate_frequency_bonus(1000)
        
        assert bonus == 2.0  # Max frequency bonus

    def test_monotonic_increase(self):
        """Test that bonus increases with access count."""
        scorer = MVSScorer()
        
        bonus_1 = scorer.calculate_frequency_bonus(1)
        bonus_10 = scorer.calculate_frequency_bonus(10)
        bonus_100 = scorer.calculate_frequency_bonus(100)
        
        assert bonus_1 < bonus_10 < bonus_100


class TestQualityBonus:
    """Tests for quality bonus calculation."""

    def test_zero_confidence_zero_bonus(self):
        """Test that 0 confidence gives 0 bonus."""
        scorer = MVSScorer()
        
        bonus = scorer.calculate_quality_bonus(0.0)
        
        assert bonus == 0.0

    def test_full_confidence_max_bonus(self):
        """Test that 1.0 confidence gives max bonus."""
        scorer = MVSScorer()
        
        bonus = scorer.calculate_quality_bonus(1.0)
        
        assert bonus == 2.0  # Max quality bonus

    def test_critical_severity_boost(self):
        """Test that critical severity adds boost."""
        scorer = MVSScorer()
        
        base_bonus = scorer.calculate_quality_bonus(0.8)
        critical_bonus = scorer.calculate_quality_bonus(0.8, 'critical')
        
        assert critical_bonus > base_bonus
        assert critical_bonus == min(2.0, base_bonus + 0.5)

    def test_quality_scales_linearly(self):
        """Test that quality bonus scales linearly with confidence."""
        scorer = MVSScorer()
        
        bonus_50 = scorer.calculate_quality_bonus(0.5)
        bonus_100 = scorer.calculate_quality_bonus(1.0)
        
        assert bonus_50 == 1.0
        assert bonus_100 == 2.0
        assert bonus_100 == 2 * bonus_50


class TestCentralityBonus:
    """Tests for centrality bonus calculation."""

    def test_no_relationships_zero_bonus(self):
        """Test that nodes with no relationships get 0 bonus."""
        scorer = MVSScorer()
        
        bonus = scorer.calculate_centrality_bonus(0)
        
        assert bonus == 0.0

    def test_many_relationships_max_bonus(self):
        """Test that nodes with 10+ relationships get max bonus."""
        scorer = MVSScorer()
        
        bonus = scorer.calculate_centrality_bonus(10)
        
        assert bonus == 1.5  # Max centrality bonus

    def test_many_relationships_capped(self):
        """Test that bonus doesn't exceed max even with many relationships."""
        scorer = MVSScorer()
        
        bonus = scorer.calculate_centrality_bonus(100)
        
        assert bonus == 1.5  # Still capped at max

    def test_linear_scaling(self):
        """Test that bonus scales linearly with relationship count."""
        scorer = MVSScorer()
        
        bonus_5 = scorer.calculate_centrality_bonus(5)
        bonus_10 = scorer.calculate_centrality_bonus(10)
        
        assert bonus_5 == 0.75  # Halfway to max
        assert bonus_10 == 1.5


class TestCrossAgentBonus:
    """Tests for cross-agent access bonus."""

    def test_single_agent_no_bonus(self):
        """Test that single agent access gives 0 bonus."""
        scorer = MVSScorer()
        
        bonus = scorer.calculate_cross_agent_bonus(0)
        
        assert bonus == 0.0

    def test_multiple_agents_increases_bonus(self):
        """Test that multiple agents increase bonus."""
        scorer = MVSScorer()
        
        bonus_1 = scorer.calculate_cross_agent_bonus(1)
        bonus_2 = scorer.calculate_cross_agent_bonus(2)
        bonus_4 = scorer.calculate_cross_agent_bonus(4)
        
        assert bonus_1 == 0.5
        assert bonus_2 == 1.0
        assert bonus_4 == 2.0

    def test_max_four_agents(self):
        """Test that bonus caps at 4 agents."""
        scorer = MVSScorer()
        
        bonus = scorer.calculate_cross_agent_bonus(10)
        
        assert bonus == 2.0  # Max cross-agent bonus


class TestBloatPenalty:
    """Tests for bloat penalty calculation."""

    def test_under_target_no_penalty(self):
        """Test that entries under target get no penalty."""
        scorer = MVSScorer()
        
        penalty = scorer.calculate_bloat_penalty(100, 'HOT')  # Target is 1600
        
        assert penalty == 0.0

    def test_exact_target_no_penalty(self):
        """Test that entries at target get no penalty."""
        scorer = MVSScorer()
        
        penalty = scorer.calculate_bloat_penalty(1600, 'HOT')
        
        assert penalty == 0.0

    def test_over_target_penalty(self):
        """Test that entries over target get penalty."""
        scorer = MVSScorer()
        
        penalty = scorer.calculate_bloat_penalty(2400, 'HOT')  # 50% over
        
        assert penalty > 0
        assert penalty <= 1.5  # Max penalty

    def test_double_target_half_penalty(self):
        """Test that double target gives ~0.75 penalty."""
        scorer = MVSScorer()
        
        penalty = scorer.calculate_bloat_penalty(3200, 'HOT')  # Double target
        
        # Excess ratio = (3200-1600)/1600 = 1.0
        # Penalty = 1.0 * 1.5 = 1.5 (capped)
        assert penalty == 1.5


class TestFullMVSCalculation:
    """Tests for complete MVS calculation."""

    @pytest.fixture
    def scorer(self):
        """Create an MVS scorer with mocked driver."""
        driver = Mock()
        return MVSScorer(driver)

    def test_high_value_belief(self, scorer):
        """Test MVS for high-value Belief."""
        node_data = {
            'type': 'Belief',
            'created_at': datetime.now(timezone.utc) - timedelta(days=1),
            'access_count_7d': 10,
            'confidence': 0.95,
            'relationship_count': 5,
            'cross_agent_access': 2,
            'token_count': 200,
            'tier': 'WARM'
        }
        
        mvs = scorer.calculate_mvs(node_data)
        
        assert mvs >= 50.0  # Should be safety-multiplied
        assert mvs > 100  # High confidence Belief with safety multiplier

    def test_notification_low_value(self, scorer):
        """Test MVS for low-value Notification."""
        old_date = datetime.now(timezone.utc) - timedelta(days=7)
        node_data = {
            'type': 'Notification',
            'created_at': old_date,
            'access_count_7d': 0,
            'confidence': 0.5,
            'relationship_count': 0,
            'cross_agent_access': 0,
            'token_count': 50,
            'tier': 'WARM'
        }
        
        mvs = scorer.calculate_mvs(node_data)
        
        assert mvs < 5.0  # Notifications should have low MVS

    def test_protected_entry_safety_multiplier(self, scorer):
        """Test that protected entries get safety multiplier."""
        fresh_date = datetime.now(timezone.utc) - timedelta(hours=1)
        node_data = {
            'type': 'MemoryEntry',
            'created_at': fresh_date,
            'access_count_7d': 0,
            'confidence': 0.5,
            'relationship_count': 0,
            'cross_agent_access': 0,
            'token_count': 100,
            'tier': 'WARM'
        }
        
        mvs = scorer.calculate_mvs(node_data)
        
        # Should be multiplied by 100 due to < 24h safety rule
        assert mvs >= 100

    def test_high_confidence_belief_protected(self, scorer):
        """Test that high-confidence Beliefs are protected."""
        old_date = datetime.now(timezone.utc) - timedelta(days=365)
        node_data = {
            'type': 'Belief',
            'created_at': old_date,
            'access_count_7d': 0,
            'confidence': 0.95,  # High confidence
            'relationship_count': 0,
            'cross_agent_access': 0,
            'token_count': 100,
            'tier': 'WARM'
        }
        
        mvs = scorer.calculate_mvs(node_data)
        
        # Should be multiplied by 100 due to high confidence Belief rule
        assert mvs >= 500  # Base would be ~10 + small bonuses


class TestCurationActions:
    """Tests for curation action determination."""

    @pytest.fixture
    def scorer(self):
        """Create an MVS scorer."""
        return MVSScorer(Mock())

    def test_keep_high_mvs(self, scorer):
        """Test that high MVS entries should be kept."""
        action = scorer.get_curation_action(50.0, 'Belief')
        assert action == 'KEEP'

    def test_keep_good_mvs(self, scorer):
        """Test that good MVS entries should be kept."""
        action = scorer.get_curation_action(8.0, 'Reflection')
        assert action == 'KEEP'

    def test_improve_moderate_mvs(self, scorer):
        """Test that moderate MVS entries should be improved."""
        action = scorer.get_curation_action(4.0, 'MemoryEntry')
        assert action == 'IMPROVE'

    def test_demote_low_mvs(self, scorer):
        """Test that low MVS entries should be demoted."""
        action = scorer.get_curation_action(2.0, 'MemoryEntry')
        assert action == 'DEMOTE'

    def test_prune_very_low_mvs(self, scorer):
        """Test that very low MVS entries should be pruned."""
        action = scorer.get_curation_action(0.3, 'Notification')
        assert action == 'PRUNE'


class TestScoreAllNodes:
    """Tests for batch scoring functionality."""

    def test_score_all_nodes_with_mock(self):
        """Test scoring multiple nodes."""
        driver = Mock()
        session = Mock()
        driver.session.return_value = session
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        
        # Mock query results
        record1 = Mock()
        record1.__getitem__ = Mock(side_effect=lambda k: {
            'id': 'node1',
            'type': 'Belief',
            'created_at': datetime.now(timezone.utc),
            'access_count': 5,
            'confidence': 0.8,
            'severity': None,
            'tokens': 100,
            'tier': 'WARM'
        }.get(k))
        
        result = Mock()
        result.__iter__ = Mock(return_value=iter([record1]))
        
        session.run.return_value = result
        
        scorer = MVSScorer(driver)
        count = scorer.score_all_nodes(limit=10)
        
        assert count == 1
        session.run.assert_called()


class TestTierTargets:
    """Tests for TIER_TARGETS configuration."""

    def test_hot_tier_target(self):
        """Verify HOT tier target."""
        assert TIER_TARGETS['HOT'] == 1600

    def test_warm_tier_target(self):
        """Verify WARM tier target."""
        assert TIER_TARGETS['WARM'] == 400

    def test_cold_tier_target(self):
        """Verify COLD tier target."""
        assert TIER_TARGETS['COLD'] == 200
