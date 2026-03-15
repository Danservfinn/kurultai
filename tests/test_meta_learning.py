"""
Tests for MetaLearningEngine class.

This module contains comprehensive tests for the meta-learning system
including MetaRule generation, approval workflow, and effectiveness tracking.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch, call
from typing import List, Dict, Optional

# Import the module under test
import sys
sys.path.insert(0, '/Users/kurultai/molt')

from tools.meta_learning import (
    MetaLearningEngine,
    MetaRuleNotFoundError,
    MetaRuleError,
    create_meta_learning_engine,
    generate_and_create_metarule,
)


class TestMetaLearningEngine:
    """Test cases for MetaLearningEngine class."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for MetaLearningEngine."""
        memory = Mock()
        memory._generate_id.return_value = "test-rule-id"
        memory._now.return_value = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        mock_session = Mock()
        mock_context = MagicMock()
        mock_context.__enter__ = Mock(return_value=mock_session)
        mock_context.__exit__ = Mock(return_value=False)
        memory._session.return_value = mock_context

        reflection_memory = Mock()

        return memory, mock_session, reflection_memory

    @pytest.fixture
    def meta_engine(self, mock_dependencies):
        """Create a MetaLearningEngine instance with mocked dependencies."""
        memory, _, reflection_memory = mock_dependencies
        return MetaLearningEngine(
            memory=memory,
            reflection_memory=reflection_memory,
            min_reflections_for_rule=3,
            default_rule_confidence=0.7
        )

    def test_initialization(self, mock_dependencies):
        """Test that MetaLearningEngine initializes correctly."""
        memory, _, reflection_memory = mock_dependencies
        engine = MetaLearningEngine(
            memory=memory,
            reflection_memory=reflection_memory,
            min_reflections_for_rule=5,
            default_rule_confidence=0.8
        )

        assert engine.memory == memory
        assert engine.reflection_memory == reflection_memory
        assert engine.min_reflections_for_rule == 5
        assert engine.default_rule_confidence == 0.8

    def test_generate_metarule_from_reflections_insufficient(self, meta_engine):
        """Test that insufficient reflections raise MetaRuleError."""
        with pytest.raises(MetaRuleError) as exc_info:
            meta_engine.generate_metarule_from_reflections(["ref1", "ref2"])

        assert "Insufficient reflections" in str(exc_info.value)

    def test_generate_metarule_from_reflections_success(self, mock_dependencies):
        """Test successful MetaRule generation from reflections."""
        memory, _, reflection_memory = mock_dependencies

        # Mock reflection data
        reflection_memory.get_reflection.side_effect = [
            {"id": "r1", "mistake_type": "security", "lesson": "Never store passwords in plaintext"},
            {"id": "r2", "mistake_type": "security", "lesson": "Always hash passwords"},
            {"id": "r3", "mistake_type": "security", "lesson": "Use bcrypt for password hashing"},
        ]

        engine = MetaLearningEngine(memory, reflection_memory, min_reflections_for_rule=3)
        rule_content = engine.generate_metarule_from_reflections(["r1", "r2", "r3"])

        assert rule_content is not None
        assert len(rule_content) > 0
        # Should contain absolute directive
        assert "NEVER" in rule_content or "ALWAYS" in rule_content

    def test_abstract_pattern_security_passwords(self, mock_dependencies):
        """Test pattern abstraction for password security issues."""
        memory, _, reflection_memory = mock_dependencies
        engine = MetaLearningEngine(memory, reflection_memory)

        reflections = [
            {"mistake_type": "security", "lesson": "Never store passwords in plaintext", "root_cause": "Forgot to hash", "context": "Auth module"},
            {"mistake_type": "security", "lesson": "Always hash passwords", "root_cause": "Missing hash call", "context": "Login flow"},
        ]

        rule = engine.abstract_pattern(reflections)

        assert "NEVER" in rule or "ALWAYS" in rule
        assert "password" in rule.lower() or "credential" in rule.lower()

    def test_abstract_pattern_security_input(self, mock_dependencies):
        """Test pattern abstraction for input validation issues."""
        memory, _, reflection_memory = mock_dependencies
        engine = MetaLearningEngine(memory, reflection_memory)

        reflections = [
            {"mistake_type": "security", "lesson": "Always sanitize user input", "root_cause": "No validation", "context": "API endpoint"},
            {"mistake_type": "security", "lesson": "Validate input before processing", "root_cause": "Missing validation", "context": "Form handler"},
        ]

        rule = engine.abstract_pattern(reflections)

        assert "input" in rule.lower() or "sanitize" in rule.lower()

    def test_abstract_pattern_security_eval(self, mock_dependencies):
        """Test pattern abstraction for eval() issues."""
        memory, _, reflection_memory = mock_dependencies
        engine = MetaLearningEngine(memory, reflection_memory)

        reflections = [
            {"mistake_type": "security", "lesson": "Never use eval() on untrusted data", "root_cause": "Used eval", "context": "Parser"},
            {"mistake_type": "security", "lesson": "Avoid eval for security", "root_cause": "Dangerous eval", "context": "Config loader"},
        ]

        rule = engine.abstract_pattern(reflections)

        assert "eval" in rule.lower()

    def test_abstract_pattern_logic_null(self, mock_dependencies):
        """Test pattern abstraction for null check issues."""
        memory, _, reflection_memory = mock_dependencies
        engine = MetaLearningEngine(memory, reflection_memory)

        reflections = [
            {"mistake_type": "logic", "lesson": "Always check for null", "root_cause": "No null check", "context": "Data access"},
            {"mistake_type": "logic", "lesson": "Validate None before use", "root_cause": "Missing validation", "context": "Service layer"},
        ]

        rule = engine.abstract_pattern(reflections)

        assert "null" in rule.lower() or "none" in rule.lower()

    def test_abstract_pattern_error_handling(self, mock_dependencies):
        """Test pattern abstraction for error handling issues."""
        memory, _, reflection_memory = mock_dependencies
        engine = MetaLearningEngine(memory, reflection_memory)

        reflections = [
            {"mistake_type": "error", "lesson": "Handle exceptions explicitly", "root_cause": "Missing try-catch", "context": "API handler"},
            {"mistake_type": "error", "lesson": "Catch specific exceptions", "root_cause": "Generic exception handling", "context": "Worker"},
        ]

        rule = engine.abstract_pattern(reflections)

        assert "error" in rule.lower() or "exception" in rule.lower()

    def test_format_rule(self, mock_dependencies):
        """Test rule formatting."""
        memory, _, reflection_memory = mock_dependencies
        engine = MetaLearningEngine(memory, reflection_memory)

        directive = "NEVER do X"
        explanations = ["Reason 1", "Reason 2"]
        example = "Example code"

        rule = engine._format_rule(directive, explanations, example)

        assert directive in rule
        assert "Explanation:" in rule
        assert "- Reason 1" in rule
        assert "- Reason 2" in rule
        assert f"Example: {example}" in rule

    def test_create_metarule_success(self, mock_dependencies):
        """Test successful MetaRule creation."""
        memory, mock_session, reflection_memory = mock_dependencies

        # create_metarule now calls get_reflection to extract applicable_agents
        reflection_memory.get_reflection.return_value = {"agent": "developer"}

        mock_result = Mock()
        mock_result.single.return_value = {"rule_id": "test-rule-id"}
        mock_session.run.return_value = mock_result

        engine = MetaLearningEngine(memory, reflection_memory)
        rule_id = engine.create_metarule(
            rule_content="NEVER store passwords in plaintext",
            rule_type="absolute",
            source_reflections=["r1", "r2", "r3"]
        )

        assert rule_id == "test-rule-id"
        mock_session.run.assert_called_once()

        # Verify parameters
        call_args = mock_session.run.call_args
        assert call_args[1]["rule_content"] == "NEVER store passwords in plaintext"
        assert call_args[1]["rule_type"] == "absolute"
        assert call_args[1]["source_reflections"] == ["r1", "r2", "r3"]
        assert call_args[1]["applicable_agents"] == ["developer"]

    def test_create_metarule_invalid_type(self, meta_engine):
        """Test that invalid rule_type raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            meta_engine.create_metarule(
                rule_content="Test rule",
                rule_type="invalid_type",
                source_reflections=["r1"]
            )

        assert "Invalid rule_type" in str(exc_info.value)

    def test_create_metarule_valid_types(self, mock_dependencies):
        """Test that all valid rule types are accepted."""
        memory, mock_session, reflection_memory = mock_dependencies

        reflection_memory.get_reflection.return_value = {"agent": "developer"}

        mock_result = Mock()
        mock_result.single.return_value = {"rule_id": "test-id"}
        mock_session.run.return_value = mock_result

        engine = MetaLearningEngine(memory, reflection_memory)
        valid_types = ["absolute", "guideline", "conditional"]

        for rule_type in valid_types:
            rule_id = engine.create_metarule(
                rule_content="Test rule",
                rule_type=rule_type,
                source_reflections=["r1"]
            )
            assert rule_id is not None

    def test_approve_metarule_success(self, mock_dependencies):
        """Test successful MetaRule approval."""
        memory, mock_session, reflection_memory = mock_dependencies

        mock_result = Mock()
        mock_result.single.return_value = {"rule_id": "rule-1"}
        mock_session.run.return_value = mock_result

        engine = MetaLearningEngine(memory, reflection_memory)
        result = engine.approve_metarule("rule-1", approved_by="kublai")

        assert result is True

        # Verify notification was created
        memory.create_notification.assert_called_once()
        call_args = memory.create_notification.call_args
        assert call_args[1]["agent"] == "kublai"
        assert call_args[1]["type"] == "metarule_approved"

    def test_approve_metarule_not_found(self, mock_dependencies):
        """Test approving a non-existent MetaRule."""
        memory, mock_session, reflection_memory = mock_dependencies

        mock_result = Mock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result

        engine = MetaLearningEngine(memory, reflection_memory)
        with pytest.raises(MetaRuleNotFoundError):
            engine.approve_metarule("non-existent", approved_by="kublai")

    def test_apply_metarule_success(self, mock_dependencies):
        """Test recording successful MetaRule application."""
        memory, mock_session, reflection_memory = mock_dependencies

        mock_result = Mock()
        mock_result.single.return_value = {"rule_id": "rule-1"}
        mock_session.run.return_value = mock_result

        engine = MetaLearningEngine(memory, reflection_memory)
        result = engine.apply_metarule("rule-1", outcome_success=True)

        assert result is True

        # Verify the update query was called
        call_args = mock_session.run.call_args
        assert call_args[1]["rule_id"] == "rule-1"
        assert call_args[1]["outcome_success"] is True

    def test_apply_metarule_failure(self, mock_dependencies):
        """Test recording failed MetaRule application."""
        memory, mock_session, reflection_memory = mock_dependencies

        mock_result = Mock()
        mock_result.single.return_value = {"rule_id": "rule-1"}
        mock_session.run.return_value = mock_result

        engine = MetaLearningEngine(memory, reflection_memory)
        result = engine.apply_metarule("rule-1", outcome_success=False)

        assert result is True

        call_args = mock_session.run.call_args
        assert call_args[1]["outcome_success"] is False

    def test_get_applicable_rules(self, mock_dependencies):
        """Test getting applicable rules."""
        memory, mock_session, reflection_memory = mock_dependencies

        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([
            {"m": {"id": "r1", "rule_content": "Rule 1", "effectiveness_score": 0.9}},
            {"m": {"id": "r2", "rule_content": "Rule 2", "effectiveness_score": 0.8}},
        ]))
        mock_session.run.return_value = mock_result

        engine = MetaLearningEngine(memory, reflection_memory)
        rules = engine.get_applicable_rules(min_confidence=0.7)

        assert len(rules) == 2
        assert rules[0]["effectiveness_score"] == 0.9

    def test_get_rule_effectiveness(self, mock_dependencies):
        """Test getting rule effectiveness metrics."""
        memory, mock_session, reflection_memory = mock_dependencies

        mock_result = Mock()
        mock_result.single.return_value = {
            "success_count": 10,
            "application_count": 12,
            "effectiveness_score": 0.833
        }
        mock_session.run.return_value = mock_result

        engine = MetaLearningEngine(memory, reflection_memory)
        metrics = engine.get_rule_effectiveness("rule-1")

        assert metrics is not None
        assert metrics["rule_id"] == "rule-1"
        assert metrics["success_count"] == 10
        assert metrics["application_count"] == 12

    def test_update_rule_version(self, mock_dependencies):
        """Test creating a new version of a MetaRule."""
        memory, mock_session, reflection_memory = mock_dependencies

        # First call to get old rule, second to create new rule, third to create relationship
        mock_results = [
            Mock(single=Mock(return_value={"m": {"id": "old-rule", "rule_type": "absolute", "version": 1, "source_reflections": ["r1"]}})),
            Mock(single=Mock(return_value={"rule_id": "test-rule-id"})),
            Mock(single=Mock(return_value={"r": {}})),
        ]
        mock_session.run.side_effect = mock_results

        engine = MetaLearningEngine(memory, reflection_memory)
        new_rule_id = engine.update_rule_version(
            old_rule_id="old-rule",
            new_rule_content="Updated rule content",
            reason="Clarified based on feedback"
        )

        assert new_rule_id == "test-rule-id"
        assert mock_session.run.call_count == 3

    def test_update_rule_version_not_found(self, mock_dependencies):
        """Test versioning a non-existent rule."""
        memory, mock_session, reflection_memory = mock_dependencies

        mock_result = Mock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result

        engine = MetaLearningEngine(memory, reflection_memory)
        with pytest.raises(MetaRuleNotFoundError):
            engine.update_rule_version(
                old_rule_id="non-existent",
                new_rule_content="Updated content",
                reason="Test"
            )

    def test_queue_soul_update(self, mock_dependencies):
        """Test queuing SOUL file update."""
        memory, mock_session, reflection_memory = mock_dependencies

        # Mock get_metarule
        mock_results = [
            Mock(single=Mock(return_value={"m": {"id": "rule-1", "approved": True, "rule_content": "Test rule", "rule_type": "absolute"}})),
        ]
        mock_session.run.side_effect = mock_results

        engine = MetaLearningEngine(memory, reflection_memory)
        result = engine.queue_soul_update(agent="developer", rule_id="rule-1")

        assert result is True
        memory.create_notification.assert_called_once()

        call_args = memory.create_notification.call_args
        assert call_args[1]["agent"] == "developer"
        assert call_args[1]["type"] == "soul_update_required"

    def test_queue_soul_update_unapproved(self, mock_dependencies):
        """Test queuing update for unapproved rule fails."""
        memory, mock_session, reflection_memory = mock_dependencies

        mock_result = Mock()
        mock_result.single.return_value = {"m": {"id": "rule-1", "approved": False}}
        mock_session.run.return_value = mock_result

        engine = MetaLearningEngine(memory, reflection_memory)

        with pytest.raises(MetaRuleError) as exc_info:
            engine.queue_soul_update(agent="developer", rule_id="rule-1")

        assert "unapproved" in str(exc_info.value).lower()

    def test_consolidate_reflections_and_generate_rules(self, mock_dependencies):
        """Test full consolidation pipeline."""
        memory, mock_session, reflection_memory = mock_dependencies

        # Mock consolidation result
        reflection_memory.consolidate_reflections.return_value = {
            "consolidated": True,
            "reflections_processed": 5,
            "reflection_ids": ["r1", "r2", "r3", "r4", "r5"],
            "by_mistake_type": {"security": 5}
        }

        ref_data = {
            "r1": {"id": "r1", "agent": "developer", "mistake_type": "security", "lesson": "Lesson 1", "root_cause": "Cause 1", "context": "Context 1"},
            "r2": {"id": "r2", "agent": "developer", "mistake_type": "security", "lesson": "Lesson 2", "root_cause": "Cause 2", "context": "Context 2"},
            "r3": {"id": "r3", "agent": "developer", "mistake_type": "security", "lesson": "Lesson 3", "root_cause": "Cause 3", "context": "Context 3"},
            "r4": {"id": "r4", "agent": "developer", "mistake_type": "security", "lesson": "Lesson 4", "root_cause": "Cause 4", "context": "Context 4"},
            "r5": {"id": "r5", "agent": "developer", "mistake_type": "security", "lesson": "Lesson 5", "root_cause": "Cause 5", "context": "Context 5"},
        }
        # get_reflection called during both generate_metarule_from_reflections and create_metarule
        reflection_memory.get_reflection.side_effect = lambda rid: ref_data.get(rid)

        # Mock create_metarule result
        mock_result = Mock()
        mock_result.single.return_value = {"rule_id": "new-rule-id"}
        mock_session.run.return_value = mock_result

        engine = MetaLearningEngine(memory, reflection_memory, min_reflections_for_rule=3)
        results = engine.consolidate_reflections_and_generate_rules(agent="developer")

        assert results["reflections_consolidated"] == 5
        assert results["rules_generated"] == 1
        assert "new-rule-id" in results["rule_ids"]
        # Verify reflections were marked consolidated after rule creation
        reflection_memory._mark_reflections_consolidated.assert_called_once()

    def test_consolidate_reflections_insufficient(self, mock_dependencies):
        """Test consolidation with insufficient reflections."""
        memory, _, reflection_memory = mock_dependencies

        reflection_memory.consolidate_reflections.return_value = {
            "consolidated": True,
            "reflections_processed": 2,
            "reflection_ids": ["r1", "r2"]
        }

        engine = MetaLearningEngine(memory, reflection_memory, min_reflections_for_rule=3)
        results = engine.consolidate_reflections_and_generate_rules()

        assert results["reflections_consolidated"] == 2
        assert results["rules_generated"] == 0
        assert "Insufficient" in results["message"]

    def test_determine_rule_type(self, mock_dependencies):
        """Test rule type determination."""
        memory, _, reflection_memory = mock_dependencies
        engine = MetaLearningEngine(memory, reflection_memory)

        # Absolute rules
        assert engine._determine_rule_type("NEVER do X") == "absolute"
        assert engine._determine_rule_type("ALWAYS do Y") == "absolute"

        # Conditional rules
        assert engine._determine_rule_type("If X then Y") == "conditional"
        assert engine._determine_rule_type("When Z occurs, do Y") == "conditional"

        # Guidelines (default)
        assert engine._determine_rule_type("Consider doing X") == "guideline"
        assert engine._determine_rule_type("Prefer Y over Z") == "guideline"

    def test_list_metarules(self, mock_dependencies):
        """Test listing MetaRules with filters."""
        memory, mock_session, reflection_memory = mock_dependencies

        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([
            {"m": {"id": "r1", "approved": True, "rule_type": "absolute"}},
            {"m": {"id": "r2", "approved": True, "rule_type": "guideline"}},
        ]))
        mock_session.run.return_value = mock_result

        engine = MetaLearningEngine(memory, reflection_memory)
        rules = engine.list_metarules(approved=True, rule_type="absolute")

        assert len(rules) == 2

    def test_get_rule_history(self, mock_dependencies):
        """Test getting rule version history."""
        memory, mock_session, reflection_memory = mock_dependencies

        # First call checks for previous version, second gets current rule
        mock_results = [
            Mock(single=Mock(return_value={
                "old": {"id": "v1", "version": 1},
                "r": {"reason": "Initial version", "replaced_at": "2025-01-01"}
            })),
            Mock(single=Mock(return_value=None)),  # No more previous versions
            Mock(single=Mock(return_value={"m": {"id": "v2", "version": 2}})),  # Current rule
        ]
        mock_session.run.side_effect = mock_results

        engine = MetaLearningEngine(memory, reflection_memory)
        history = engine.get_rule_history("v2")

        assert len(history) == 2
        assert history[0]["rule"]["version"] == 1
        assert history[1]["rule"]["version"] == 2

    def test_create_indexes(self, mock_dependencies):
        """Test creating indexes."""
        memory, mock_session, reflection_memory = mock_dependencies

        engine = MetaLearningEngine(memory, reflection_memory)
        indexes = engine.create_indexes()

        assert len(indexes) == 6
        assert "metarule_id_idx" in indexes
        assert "metarule_approved_idx" in indexes
        assert "metarule_type_idx" in indexes
        assert "metarule_version_idx" in indexes
        assert "metarule_created_idx" in indexes
        assert "metarule_effectiveness_idx" in indexes


class TestConvenienceFunctions:
    """Test convenience functions."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies."""
        memory = Mock()
        memory._generate_id.return_value = "test-id"
        memory._now.return_value = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        mock_session = Mock()
        mock_context = MagicMock()
        mock_context.__enter__ = Mock(return_value=mock_session)
        mock_context.__exit__ = Mock(return_value=False)
        memory._session.return_value = mock_context

        reflection_memory = Mock()

        return memory, mock_session, reflection_memory

    def test_create_meta_learning_engine(self, mock_dependencies):
        """Test create_meta_learning_engine convenience function."""
        memory, _, reflection_memory = mock_dependencies
        engine = create_meta_learning_engine(memory, reflection_memory)

        assert isinstance(engine, MetaLearningEngine)

    def test_generate_and_create_metarule(self, mock_dependencies):
        """Test generate_and_create_metarule convenience function."""
        memory, mock_session, reflection_memory = mock_dependencies

        ref_data = {
            "r1": {"id": "r1", "agent": "developer", "mistake_type": "security", "lesson": "Lesson 1"},
            "r2": {"id": "r2", "agent": "developer", "mistake_type": "security", "lesson": "Lesson 2"},
            "r3": {"id": "r3", "agent": "developer", "mistake_type": "security", "lesson": "Lesson 3"},
        }
        # Called during both generate and create
        reflection_memory.get_reflection.side_effect = lambda rid: ref_data.get(rid)

        # Mock create_metarule result
        mock_result = Mock()
        mock_result.single.return_value = {"rule_id": "new-rule-id"}
        mock_session.run.return_value = mock_result

        engine = MetaLearningEngine(memory, reflection_memory, min_reflections_for_rule=3)
        rule_id = generate_and_create_metarule(
            engine,
            reflection_ids=["r1", "r2", "r3"],
            rule_type="absolute"
        )

        assert rule_id == "new-rule-id"


class TestCommunicationAndGenericRules:
    """Test communication and generic rule generation."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies."""
        memory = Mock()
        memory._generate_id.return_value = "test-id"
        memory._now.return_value = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_session = Mock()
        mock_context = MagicMock()
        mock_context.__enter__ = Mock(return_value=mock_session)
        mock_context.__exit__ = Mock(return_value=False)
        memory._session.return_value = mock_context
        reflection_memory = Mock()
        return memory, mock_session, reflection_memory

    def test_abstract_pattern_communication(self, mock_dependencies):
        """Test pattern abstraction for communication issues."""
        memory, _, reflection_memory = mock_dependencies
        engine = MetaLearningEngine(memory, reflection_memory)

        reflections = [
            {"mistake_type": "communication", "lesson": "Document intent clearly", "root_cause": "Poor docs", "context": "Team review"},
            {"mistake_type": "communication", "lesson": "Confirm understanding first", "root_cause": "Miscommunication", "context": "Feature spec"},
        ]

        rule = engine.abstract_pattern(reflections)
        assert "communicate" in rule.lower() or "intent" in rule.lower()
        assert "Explanation:" in rule

    def test_abstract_pattern_generic(self, mock_dependencies):
        """Test pattern abstraction for unknown/other mistake types."""
        memory, _, reflection_memory = mock_dependencies
        engine = MetaLearningEngine(memory, reflection_memory)

        reflections = [
            {"mistake_type": "other", "lesson": "Review deployment pipeline carefully", "root_cause": "Missed step", "context": "Release process"},
            {"mistake_type": "other", "lesson": "Check deployment pipeline before release", "root_cause": "Skipped check", "context": "Release"},
        ]

        rule = engine.abstract_pattern(reflections)
        assert "ALWAYS" in rule
        assert "Example:" in rule

    def test_abstract_pattern_mixed_types_picks_dominant(self, mock_dependencies):
        """Test that abstract_pattern picks the dominant mistake type."""
        memory, _, reflection_memory = mock_dependencies
        engine = MetaLearningEngine(memory, reflection_memory)

        reflections = [
            {"mistake_type": "security", "lesson": "Hash passwords", "root_cause": "No hash", "context": "Auth"},
            {"mistake_type": "security", "lesson": "Use bcrypt", "root_cause": "Weak hash", "context": "Auth"},
            {"mistake_type": "logic", "lesson": "Check nulls", "root_cause": "NPE", "context": "API"},
        ]

        rule = engine.abstract_pattern(reflections)
        # Security is dominant (2 vs 1), so should generate security rule
        assert "password" in rule.lower() or "NEVER" in rule or "ALWAYS" in rule

    def test_generate_security_rule_generic_fallback(self, mock_dependencies):
        """Test security rule fallback when no specific keywords match."""
        memory, _, reflection_memory = mock_dependencies
        engine = MetaLearningEngine(memory, reflection_memory)

        rule = engine._generate_security_rule(
            lessons=["Apply defense measures"],
            root_causes=["Insufficient layers"],
            contexts=["Production system"]
        )
        assert "defense-in-depth" in rule.lower()

    def test_logic_rule_race_condition(self, mock_dependencies):
        """Test logic rule for race condition issues."""
        memory, _, reflection_memory = mock_dependencies
        engine = MetaLearningEngine(memory, reflection_memory)

        rule = engine._generate_logic_rule(
            lessons=["Use proper locking for concurrent access"],
            root_causes=["Race condition in shared state"],
            contexts=["Worker pool"]
        )
        assert "synchronization" in rule.lower() or "concurrent" in rule.lower()

    def test_logic_rule_generic_fallback(self, mock_dependencies):
        """Test logic rule fallback for generic issues."""
        memory, _, reflection_memory = mock_dependencies
        engine = MetaLearningEngine(memory, reflection_memory)

        rule = engine._generate_logic_rule(
            lessons=["Verify data transformations"],
            root_causes=["Incorrect mapping"],
            contexts=["ETL pipeline"]
        )
        assert "validate" in rule.lower() or "assertion" in rule.lower()

    def test_get_applicable_rules_with_agent_filter(self, mock_dependencies):
        """Test that agent filter is passed to query."""
        memory, mock_session, reflection_memory = mock_dependencies

        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([
            {"m": {"id": "r1", "rule_content": "Rule 1", "effectiveness_score": 0.9, "applicable_agents": ["developer"]}},
        ]))
        mock_session.run.return_value = mock_result

        engine = MetaLearningEngine(memory, reflection_memory)
        rules = engine.get_applicable_rules(agent="developer", min_confidence=0.7)

        assert len(rules) == 1
        # Verify the query included agent filter
        call_args = mock_session.run.call_args
        assert "agent" in call_args[1]
        assert call_args[1]["agent"] == "developer"


class TestIdAndSessionFallbacks:
    """Test _generate_id, _now, _session fallback paths."""

    def test_generate_id_fallback_no_method(self):
        """Test _generate_id when memory has no _generate_id method."""
        memory = Mock(spec=[])  # No methods at all
        reflection_memory = Mock()
        engine = MetaLearningEngine(memory, reflection_memory)
        result = engine._generate_id()
        # Should return a valid UUID string
        assert len(result) == 36  # UUID format
        assert "-" in result

    def test_now_fallback_no_method(self):
        """Test _now when memory has no _now method."""
        memory = Mock(spec=[])
        reflection_memory = Mock()
        engine = MetaLearningEngine(memory, reflection_memory)
        result = engine._now()
        assert isinstance(result, datetime)
        assert result.tzinfo == timezone.utc

    def test_session_fallback_no_method(self):
        """Test _session when memory has no _session method."""
        memory = Mock(spec=[])
        reflection_memory = Mock()
        engine = MetaLearningEngine(memory, reflection_memory)
        ctx = engine._session()
        with ctx as session:
            assert session is None


class TestFallbackMode:
    """Test fallback mode behavior."""

    @pytest.fixture
    def fallback_engine(self):
        """Create a MetaLearningEngine in fallback mode."""
        memory = Mock()
        memory._generate_id.return_value = "test-id"
        memory._now.return_value = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Set session to None for fallback mode
        mock_context = MagicMock()
        mock_context.__enter__ = Mock(return_value=None)
        mock_context.__exit__ = Mock(return_value=False)
        memory._session.return_value = mock_context

        reflection_memory = Mock()

        return MetaLearningEngine(memory, reflection_memory)

    def test_create_metarule_fallback(self, fallback_engine):
        """Test create_metarule in fallback mode returns ID."""
        fallback_engine.reflection_memory.get_reflection.return_value = {"agent": "developer"}
        rule_id = fallback_engine.create_metarule(
            rule_content="Test rule",
            rule_type="guideline",
            source_reflections=["r1"]
        )
        assert rule_id == "test-id"

    def test_approve_metarule_fallback(self, fallback_engine):
        """Test approve in fallback mode."""
        result = fallback_engine.approve_metarule("rule-1", approved_by="kublai")
        assert result is True

    def test_apply_metarule_fallback(self, fallback_engine):
        """Test apply in fallback mode."""
        result = fallback_engine.apply_metarule("rule-1", outcome_success=True)
        assert result is True

    def test_get_applicable_rules_fallback(self, fallback_engine):
        """Test get applicable rules in fallback mode."""
        rules = fallback_engine.get_applicable_rules()
        assert rules == []

    def test_get_rule_effectiveness_fallback(self, fallback_engine):
        """Test get effectiveness in fallback mode."""
        metrics = fallback_engine.get_rule_effectiveness("rule-1")
        assert metrics is not None
        assert metrics["success_count"] == 0

    def test_update_rule_version_fallback(self, fallback_engine):
        """Test rule versioning in fallback mode (rule not found)."""
        with pytest.raises(MetaRuleNotFoundError):
            fallback_engine.update_rule_version("old-id", "new content", "reason")

    def test_list_metarules_fallback(self, fallback_engine):
        """Test list_metarules in fallback mode."""
        rules = fallback_engine.list_metarules()
        assert rules == []

    def test_get_rule_history_fallback(self, fallback_engine):
        """Test get_rule_history in fallback mode."""
        history = fallback_engine.get_rule_history("rule-1")
        assert history == []

    def test_create_indexes_fallback(self, fallback_engine):
        """Test create_indexes in fallback mode."""
        indexes = fallback_engine.create_indexes()
        assert indexes == []

    def test_queue_soul_update_not_found_fallback(self, fallback_engine):
        """Test queue_soul_update when rule not found in fallback mode."""
        with pytest.raises(MetaRuleNotFoundError):
            fallback_engine.queue_soul_update("developer", "nonexistent")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
