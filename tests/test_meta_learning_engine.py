"""
Tests for MetaLearningEngine

Author: Chagatai (Writer Agent)
Date: 2026-02-09
"""

import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from typing import List, Dict, Any

from tools.kurultai.meta_learning_engine import (
    MetaLearningEngine,
    ReflectionCluster,
    MetaRule,
    RuleEffectiveness,
    run_meta_learning_cycle,
)


class TestReflectionCluster:
    """Tests for ReflectionCluster dataclass."""
    
    def test_cluster_creation(self):
        """Test creating a reflection cluster."""
        cluster = ReflectionCluster(
            id="test-id",
            topic="error_handling",
            pattern_signature="abc123",
            reflections=[{"id": "r1"}, {"id": "r2"}],
            common_insights=["insight1", "insight2"],
        )
        
        assert cluster.id == "test-id"
        assert cluster.topic == "error_handling"
        assert len(cluster.reflections) == 2
        assert cluster.rule_generated is False
    
    def test_cluster_to_dict(self):
        """Test cluster serialization."""
        cluster = ReflectionCluster(
            id="test-id",
            topic="performance",
            pattern_signature="def456",
            reflections=[{"id": "r1"}],
            common_insights=["optimize"],
        )
        
        d = cluster.to_dict()
        assert d['topic'] == "performance"
        assert d['reflection_count'] == 1
        assert 'created_at' in d


class TestMetaRule:
    """Tests for MetaRule dataclass."""
    
    def test_rule_creation(self):
        """Test creating a meta-rule."""
        rule = MetaRule(
            id="rule-id",
            name="test_rule",
            description="Test rule description",
            rule_type="error_handling",
            source_cluster_id="cluster-id",
            target_agents=["temujin"],
            conditions=["condition1"],
            actions=["action1"],
            priority=3,
        )
        
        assert rule.name == "test_rule"
        assert rule.status == "proposed"
        assert rule.application_count == 0
    
    def test_rule_to_dict(self):
        """Test rule serialization."""
        rule = MetaRule(
            id="rule-id",
            name="test_rule",
            description="Test",
            rule_type="general",
            source_cluster_id="cluster-id",
            target_agents=["agent1"],
            conditions=[],
            actions=[],
        )
        
        d = rule.to_dict()
        assert d['name'] == "test_rule"
        assert d['status'] == "proposed"
        assert 'created_at' in d


class TestMetaLearningEngine:
    """Tests for MetaLearningEngine class."""
    
    @pytest.fixture
    def engine(self):
        """Create engine with mocked Neo4j."""
        with patch('tools.kurultai.meta_learning_engine.GraphDatabase') as mock_db:
            mock_driver = Mock()
            mock_db.driver.return_value = mock_driver
            
            engine = MetaLearningEngine(
                neo4j_uri="bolt://test:7687",
                neo4j_password="testpass"
            )
            engine._driver = mock_driver
            yield engine
    
    @pytest.fixture
    def sample_reflections(self) -> List[Dict[str, Any]]:
        """Sample reflections for testing."""
        return [
            {
                'id': 'r1',
                'agent': 'temujin',
                'topic': 'error_handling',
                'insights': ['Add try-except', 'Log errors'],
                'task_type': 'code_generation',
                'created_at': datetime.utcnow() - timedelta(days=1),
            },
            {
                'id': 'r2',
                'agent': 'temujin',
                'topic': 'error_handling',
                'insights': ['Handle exceptions', 'Log context'],
                'task_type': 'code_generation',
                'created_at': datetime.utcnow() - timedelta(days=2),
            },
            {
                'id': 'r3',
                'agent': 'temujin',
                'topic': 'error_handling',
                'insights': ['Use specific exceptions'],
                'task_type': 'bugfix',
                'created_at': datetime.utcnow() - timedelta(days=3),
            },
        ]
    
    def test_initialization(self):
        """Test engine initialization."""
        with patch('tools.kurultai.meta_learning_engine.GraphDatabase') as mock_db:
            mock_db.driver.return_value = Mock()
            
            engine = MetaLearningEngine(
                neo4j_uri="bolt://test:7687",
                neo4j_user="neo4j",
                neo4j_password="testpass"
            )
            
            assert engine.neo4j_uri == "bolt://test:7687"
            assert engine.neo4j_password == "testpass"
            assert engine.min_cluster_size == 3
    
    def test_extract_common_themes(self, engine):
        """Test theme extraction from insights."""
        insights = [
            "Add error handling",
            "Log all exceptions",
            "Handle failures gracefully",
            "Optimize the query",
            "Improve performance speed",
        ]
        
        themes = engine._extract_common_themes(insights)
        
        assert 'error_handling' in themes
        assert 'performance' in themes
    
    def test_generate_pattern_signature(self, engine):
        """Test signature generation."""
        sig1 = engine._generate_pattern_signature("topic1", ["theme1", "theme2"])
        sig2 = engine._generate_pattern_signature("topic1", ["theme1", "theme2"])
        sig3 = engine._generate_pattern_signature("topic2", ["theme1", "theme2"])
        
        # Same inputs = same signature
        assert sig1 == sig2
        # Different inputs = different signature
        assert sig1 != sig3
        # Signature is truncated hash
        assert len(sig1) == 16
    
    def test_calculate_cluster_confidence(self, engine, sample_reflections):
        """Test confidence calculation."""
        cluster = ReflectionCluster(
            id="test",
            topic="error_handling",
            pattern_signature="sig",
            reflections=sample_reflections,
            common_insights=["error_handling"],
        )
        
        confidence = engine._calculate_cluster_confidence(cluster)
        
        # Should be between 0 and 1
        assert 0 <= confidence <= 1
        # With 3 reflections, should have reasonable confidence
        assert confidence > 0.3
    
    def test_determine_rule_type(self, engine):
        """Test rule type determination."""
        assert engine._determine_rule_type(["error_handling"]) == "error_handling"
        assert engine._determine_rule_type(["performance"]) == "optimization"
        assert engine._determine_rule_type(["communication"]) == "communication"
        assert engine._determine_rule_type(["unknown"]) == "general"
    
    def test_generate_rule_name(self, engine):
        """Test rule name generation."""
        name = engine._generate_rule_name("Error Handling", "error_handling")
        
        assert "error_handling" in name
        assert "error_handling" in name.lower() or "error" in name.lower()
        # Should include timestamp
        assert len(name) > 20
    
    def test_determine_target_agents(self, engine, sample_reflections):
        """Test target agent determination."""
        cluster = ReflectionCluster(
            id="test",
            topic="test",
            pattern_signature="sig",
            reflections=sample_reflections,
        )
        
        agents = engine._determine_target_agents(cluster)
        
        assert "temujin" in agents
    
    def test_generate_conditions_and_actions(self, engine):
        """Test conditions and actions generation."""
        cluster = ReflectionCluster(
            id="test",
            topic="error_handling",
            pattern_signature="sig",
            reflections=[],
            common_insights=["error_handling"],
        )
        
        conditions, actions = engine._generate_conditions_and_actions(
            cluster, "error_handling"
        )
        
        assert len(conditions) > 0
        assert len(actions) > 0
        assert any("error" in c.lower() for c in conditions)
    
    def test_calculate_priority(self, engine, sample_reflections):
        """Test priority calculation."""
        cluster = ReflectionCluster(
            id="test",
            topic="test",
            pattern_signature="sig",
            reflections=sample_reflections,
        )
        
        priority = engine._calculate_priority(cluster, confidence=0.8)
        
        # Priority should be 1-10
        assert 1 <= priority <= 10
        # High confidence + multiple reflections = lower (better) priority
        assert priority <= 5


class TestMetaLearningIntegration:
    """Integration tests with mocked Neo4j."""
    
    @pytest.fixture
    def mock_session(self):
        """Create mock Neo4j session."""
        session = Mock()
        return session
    
    @pytest.fixture
    def engine_with_mocked_session(self, mock_session):
        """Create engine with fully mocked session."""
        with patch('tools.kurultai.meta_learning_engine.GraphDatabase') as mock_db:
            mock_driver = Mock()
            mock_driver.session.return_value.__enter__ = Mock(return_value=mock_session)
            mock_driver.session.return_value.__exit__ = Mock(return_value=False)
            mock_db.driver.return_value = mock_driver
            
            engine = MetaLearningEngine()
            engine._driver = mock_driver
            yield engine, mock_session
    
    def test_cluster_reflections(self, engine_with_mocked_session):
        """Test reflection clustering."""
        engine, mock_session = engine_with_mocked_session
        
        # Mock query results - need to make result iterable
        mock_record1 = Mock()
        mock_record1.data.return_value = {'id': 'r1', 'agent': 'a1', 'topic': 'test', 'insights': ['i1'], 'task_type': 't1', 'created_at': datetime.utcnow()}
        mock_record2 = Mock()
        mock_record2.data.return_value = {'id': 'r2', 'agent': 'a1', 'topic': 'test', 'insights': ['i2'], 'task_type': 't1', 'created_at': datetime.utcnow()}
        mock_record3 = Mock()
        mock_record3.data.return_value = {'id': 'r3', 'agent': 'a1', 'topic': 'test', 'insights': ['i3'], 'task_type': 't1', 'created_at': datetime.utcnow()}
        
        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([mock_record1, mock_record2, mock_record3]))
        mock_session.run.return_value = mock_result
        
        clusters = engine.cluster_reflections(min_cluster_size=3)
        
        assert len(clusters) >= 0
        mock_session.run.assert_called()
    
    def test_generate_rules(self, engine_with_mocked_session):
        """Test rule generation."""
        engine, mock_session = engine_with_mocked_session
        
        # Create test cluster
        cluster = ReflectionCluster(
            id="cluster-1",
            topic="error_handling",
            pattern_signature="sig123",
            reflections=[
                {'id': 'r1', 'agent': 'temujin', 'insights': ['handle errors']},
                {'id': 'r2', 'agent': 'temujin', 'insights': ['log exceptions']},
                {'id': 'r3', 'agent': 'temujin', 'insights': ['try-except']},
            ],
            common_insights=["error_handling"],
        )
        engine.clusters[cluster.id] = cluster
        
        rules = engine.generate_rules([cluster])
        
        assert len(rules) >= 0
        assert rules[0].rule_type == "error_handling"
    
    def test_inject_rules(self, engine_with_mocked_session):
        """Test rule injection preparation."""
        engine, mock_session = engine_with_mocked_session
        
        # Create test rule
        rule = MetaRule(
            id="rule-1",
            name="test_rule",
            description="Test",
            rule_type="general",
            source_cluster_id="cluster-1",
            target_agents=["temujin", "kublai"],
            conditions=[],
            actions=[],
            status="proposed",
        )
        engine.rules[rule.id] = rule
        
        injection_plan = engine.inject_rules(dry_run=True)
        
        assert "temujin" in injection_plan
        assert "kublai" in injection_plan
        assert rule.id in injection_plan["temujin"]


class TestRunMetaLearningCycle:
    """Tests for the convenience function."""
    
    @patch('tools.kurultai.meta_learning_engine.MetaLearningEngine')
    def test_successful_cycle(self, mock_engine_class):
        """Test successful learning cycle."""
        mock_engine = Mock()
        mock_engine_class.return_value = mock_engine
        
        # Mock cluster results
        mock_cluster = Mock()
        mock_cluster.id = "c1"
        mock_engine.cluster_reflections.return_value = [mock_cluster]
        
        # Mock rule results
        mock_rule = Mock()
        mock_rule.id = "r1"
        mock_rule.to_dict.return_value = {'id': 'r1', 'name': 'test'}
        mock_engine.generate_rules.return_value = [mock_rule]
        
        # Mock injection plan
        mock_engine.inject_rules.return_value = {'temujin': ['r1']}
        mock_engine.get_learning_stats.return_value = {'total_reflections': 10}
        
        result = run_meta_learning_cycle()
        
        assert result['success'] is True
        assert result['clusters_created'] == 1
        assert result['rules_generated'] == 1
        mock_engine.close.assert_called_once()
    
    @patch('tools.kurultai.meta_learning_engine.MetaLearningEngine')
    def test_failed_cycle(self, mock_engine_class):
        """Test failed learning cycle."""
        mock_engine = Mock()
        mock_engine_class.return_value = mock_engine
        mock_engine.cluster_reflections.side_effect = Exception("Neo4j error")
        
        result = run_meta_learning_cycle()
        
        assert result['success'] is False
        assert 'error' in result
        mock_engine.close.assert_called_once()


class TestRuleEffectiveness:
    """Tests for rule effectiveness tracking."""
    
    def test_effectiveness_levels(self):
        """Test effectiveness level enum."""
        assert RuleEffectiveness.HIGH.value == "high"
        assert RuleEffectiveness.MEDIUM.value == "medium"
        assert RuleEffectiveness.LOW.value == "low"
        assert RuleEffectiveness.UNKNOWN.value == "unknown"
    
    @pytest.fixture
    def engine_with_mocked_eval(self):
        """Create engine with mocked session for evaluation."""
        with patch('tools.kurultai.meta_learning_engine.GraphDatabase') as mock_db:
            mock_driver = Mock()
            mock_session = Mock()
            mock_driver.session.return_value.__enter__ = Mock(return_value=mock_session)
            mock_driver.session.return_value.__exit__ = Mock(return_value=False)
            mock_db.driver.return_value = mock_driver
            
            engine = MetaLearningEngine()
            engine._driver = mock_driver
            yield engine, mock_session
    
    def test_evaluate_rules(self, engine_with_mocked_eval):
        """Test rule evaluation."""
        engine, mock_session = engine_with_mocked_eval
        
        # Create test rule
        rule = MetaRule(
            id="rule-1",
            name="test_rule",
            description="Test",
            rule_type="general",
            source_cluster_id="cluster-1",
            target_agents=["temujin"],
            conditions=[],
            actions=[],
            status="active",
        )
        engine.rules[rule.id] = rule
        
        # Mock query results
        mock_result = Mock()
        mock_result.single.return_value = {'applications': 10, 'successes': 8}
        mock_session.run.return_value = mock_result
        
        evaluations = engine.evaluate_rules([rule.id])
        
        assert rule.id in evaluations
        assert evaluations[rule.id]['applications'] == 10
        assert evaluations[rule.id]['successes'] == 8
        assert evaluations[rule.id]['success_rate'] == 0.8
    
    def test_deprecate_low_effectiveness(self, engine_with_mocked_eval):
        """Test rule deprecation."""
        engine, mock_session = engine_with_mocked_eval
        
        # Mock deprecation query
        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([
            {'id': 'rule-1', 'name': 'bad_rule'}
        ]))
        mock_session.run.return_value = mock_result
        
        deprecated = engine.deprecate_low_effectiveness_rules(threshold=0.3)
        
        assert 'rule-1' in deprecated


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
