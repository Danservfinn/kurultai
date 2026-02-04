"""
Tests for AgentReflectionMemory class.

This module contains comprehensive tests for the reflection memory system
including mistake recording, semantic search, and consolidation.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch
from typing import List, Dict, Optional

# Import the module under test
import sys
sys.path.insert(0, '/Users/kurultai/molt')

from tools.reflection_memory import (
    AgentReflectionMemory,
    ReflectionNotFoundError,
    ReflectionError,
    create_reflection_memory,
    record_agent_mistake,
)


class TestAgentReflectionMemory:
    """Test cases for AgentReflectionMemory class."""

    @pytest.fixture
    def mock_memory(self):
        """Create a mock OperationalMemory."""
        memory = Mock()
        memory._generate_id.return_value = "test-reflection-id"
        memory._now.return_value = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Mock session context manager
        mock_session = Mock()
        mock_context = MagicMock()
        mock_context.__enter__ = Mock(return_value=mock_session)
        mock_context.__exit__ = Mock(return_value=False)
        memory._session.return_value = mock_context

        return memory, mock_session

    @pytest.fixture
    def reflection_memory(self, mock_memory):
        """Create an AgentReflectionMemory instance with mocked dependencies."""
        memory, _ = mock_memory
        return AgentReflectionMemory(memory)

    def test_initialization(self, mock_memory):
        """Test that AgentReflectionMemory initializes correctly."""
        memory, _ = mock_memory
        rm = AgentReflectionMemory(memory, embedding_dimension=512)

        assert rm.memory == memory
        assert rm.embedding_dimension == 512
        assert rm._embedding_model is None  # sentence-transformers not available in tests

    def test_initialization_with_sentence_transformers(self, mock_memory):
        """Test initialization when sentence-transformers is available."""
        memory, _ = mock_memory

        # Create a mock module with SentenceTransformer
        mock_st_module = Mock()
        mock_model = Mock()
        mock_model.encode.return_value = [0.1] * 384
        mock_st_module.SentenceTransformer.return_value = mock_model

        with patch.dict('sys.modules', {'sentence_transformers': mock_st_module}):
            rm = AgentReflectionMemory(memory)
            assert rm._embedding_model is not None

    def test_generate_embedding_with_model(self, mock_memory):
        """Test embedding generation with sentence-transformers."""
        memory, _ = mock_memory

        # Create a mock module with SentenceTransformer
        mock_st_module = Mock()
        mock_model = Mock()
        # encode() returns a numpy-like array with tolist() method
        mock_array = Mock()
        mock_array.tolist.return_value = [0.1] * 384
        mock_model.encode.return_value = mock_array
        mock_st_module.SentenceTransformer.return_value = mock_model

        with patch.dict('sys.modules', {'sentence_transformers': mock_st_module}):
            rm = AgentReflectionMemory(memory)
            embedding = rm._generate_embedding("test text")

            assert len(embedding) == 384
            assert all(v == 0.1 for v in embedding)

    def test_generate_embedding_fallback(self, reflection_memory):
        """Test fallback embedding generation without sentence-transformers."""
        embedding = reflection_memory._generate_embedding("test text")

        assert len(embedding) == reflection_memory.embedding_dimension
        assert all(isinstance(v, float) for v in embedding)
        assert all(-1.0 <= v <= 1.0 for v in embedding)

    def test_generate_embedding_deterministic(self, reflection_memory):
        """Test that fallback embeddings are deterministic."""
        embedding1 = reflection_memory._generate_embedding("test text")
        embedding2 = reflection_memory._generate_embedding("test text")

        assert embedding1 == embedding2

    def test_record_mistake_success(self, mock_memory):
        """Test successful mistake recording."""
        memory, mock_session = mock_memory

        # Mock the session run result
        mock_result = Mock()
        mock_result.single.return_value = {"reflection_id": "test-reflection-id"}
        mock_session.run.return_value = mock_result

        rm = AgentReflectionMemory(memory)
        reflection_id = rm.record_mistake(
            agent="developer",
            mistake_type="security",
            context="Implementing authentication",
            expected_behavior="Password should be hashed",
            actual_behavior="Password stored in plaintext",
            root_cause="Forgot to call hash function",
            lesson="Always use hash_password()"
        )

        assert reflection_id == "test-reflection-id"
        mock_session.run.assert_called_once()

        # Verify the cypher query was called with correct parameters
        call_args = mock_session.run.call_args
        assert call_args[1]["agent"] == "developer"
        assert call_args[1]["mistake_type"] == "security"
        assert call_args[1]["lesson"] == "Always use hash_password()"
        assert "embedding" in call_args[1]

    def test_record_mistake_invalid_type(self, reflection_memory):
        """Test that invalid mistake_type raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            reflection_memory.record_mistake(
                agent="developer",
                mistake_type="invalid_type",
                context="test",
                expected_behavior="test",
                actual_behavior="test",
                root_cause="test",
                lesson="test"
            )

        assert "Invalid mistake_type" in str(exc_info.value)

    def test_record_mistake_valid_types(self, mock_memory):
        """Test that all valid mistake types are accepted."""
        memory, mock_session = mock_memory
        mock_result = Mock()
        mock_result.single.return_value = {"reflection_id": "test-id"}
        mock_session.run.return_value = mock_result

        rm = AgentReflectionMemory(memory)
        valid_types = ["logic", "error", "communication", "security", "other"]

        for mistake_type in valid_types:
            reflection_id = rm.record_mistake(
                agent="developer",
                mistake_type=mistake_type,
                context="test",
                expected_behavior="test",
                actual_behavior="test",
                root_cause="test",
                lesson="test"
            )
            assert reflection_id is not None

    def test_record_mistake_fallback_mode(self, mock_memory):
        """Test mistake recording in fallback mode."""
        memory, mock_session = mock_memory

        # Set session to None for fallback mode
        mock_context = MagicMock()
        mock_context.__enter__ = Mock(return_value=None)
        mock_context.__exit__ = Mock(return_value=False)
        memory._session.return_value = mock_context

        rm = AgentReflectionMemory(memory)
        reflection_id = rm.record_mistake(
            agent="developer",
            mistake_type="security",
            context="test",
            expected_behavior="test",
            actual_behavior="test",
            root_cause="test",
            lesson="test"
        )

        assert reflection_id == "test-reflection-id"

    def test_get_reflection_success(self, mock_memory):
        """Test getting a reflection by ID."""
        memory, mock_session = mock_memory

        # Create a mock that behaves like a dict when passed to dict()
        mock_node = {"id": "reflection-1", "agent": "developer", "mistake_type": "security", "lesson": "Test lesson"}

        mock_result = Mock()
        mock_result.single.return_value = {"r": mock_node}
        mock_session.run.return_value = mock_result

        rm = AgentReflectionMemory(memory)
        reflection = rm.get_reflection("reflection-1")

        assert reflection is not None
        assert reflection["id"] == "reflection-1"

    def test_get_reflection_not_found(self, mock_memory):
        """Test getting a non-existent reflection."""
        memory, mock_session = mock_memory

        mock_result = Mock()
        mock_result.single.return_value = None
        mock_session.run.return_value = mock_result

        rm = AgentReflectionMemory(memory)
        reflection = rm.get_reflection("non-existent")

        assert reflection is None

    def test_list_reflections(self, mock_memory):
        """Test listing reflections with filters."""
        memory, mock_session = mock_memory

        mock_records = [
            Mock(**{"__getitem__": Mock(return_value={"id": "r1", "agent": "dev1"})}),
            Mock(**{"__getitem__": Mock(return_value={"id": "r2", "agent": "dev1"})}),
        ]

        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([
            {"r": {"id": "r1", "agent": "dev1"}},
            {"r": {"id": "r2", "agent": "dev1"}}
        ]))
        mock_session.run.return_value = mock_result

        rm = AgentReflectionMemory(memory)
        reflections = rm.list_reflections(agent="dev1", consolidated=False, limit=10)

        assert len(reflections) == 2
        mock_session.run.assert_called_once()

    def test_list_reflections_fallback_mode(self, mock_memory):
        """Test listing reflections in fallback mode."""
        memory, mock_session = mock_memory

        mock_context = MagicMock()
        mock_context.__enter__ = Mock(return_value=None)
        mock_context.__exit__ = Mock(return_value=False)
        memory._session.return_value = mock_context

        rm = AgentReflectionMemory(memory)
        reflections = rm.list_reflections()

        assert reflections == []

    def test_search_similar_reflections(self, mock_memory):
        """Test semantic search for similar reflections."""
        memory, mock_session = mock_memory

        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([
            {"r": {"id": "r1", "agent": "dev1", "lesson": "password security"}, "similarity": 0.95},
            {"r": {"id": "r2", "agent": "dev1", "lesson": "hash passwords"}, "similarity": 0.87},
        ]))
        mock_session.run.return_value = mock_result

        rm = AgentReflectionMemory(memory)
        results = rm.search_similar_reflections("password hashing", agent="dev1", limit=5)

        assert len(results) == 2
        assert results[0]["similarity"] == 0.95

    def test_consolidate_reflections(self, mock_memory):
        """Test consolidating reflections."""
        memory, mock_session = mock_memory

        # Mock the list_reflections result
        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([
            {"r": {"id": "r1", "agent": "dev1", "mistake_type": "security", "lesson": "lesson1"}},
            {"r": {"id": "r2", "agent": "dev1", "mistake_type": "security", "lesson": "lesson2"}},
        ]))
        mock_session.run.return_value = mock_result

        rm = AgentReflectionMemory(memory)
        summary = rm.consolidate_reflections(agent="dev1")

        assert summary["consolidated"] is True
        assert summary["reflections_processed"] == 2
        assert "r1" in summary["reflection_ids"]
        assert "r2" in summary["reflection_ids"]

    def test_consolidate_reflections_no_unconsolidated(self, mock_memory):
        """Test consolidating when no unconsolidated reflections exist."""
        memory, mock_session = mock_memory

        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([]))
        mock_session.run.return_value = mock_result

        rm = AgentReflectionMemory(memory)
        summary = rm.consolidate_reflections()

        assert summary["consolidated"] is False
        assert "No unconsolidated reflections" in summary["reason"]

    def test_consolidate_reflections_with_ids(self, mock_memory):
        """Test consolidating specific reflection IDs."""
        memory, mock_session = mock_memory

        # First two calls for get_reflection (r1, r2), third for _mark_reflections_consolidated
        mock_results = [
            Mock(single=Mock(return_value={"r": {"id": "r1", "agent": "dev1", "mistake_type": "security", "consolidated": False}})),
            Mock(single=Mock(return_value={"r": {"id": "r2", "agent": "dev1", "mistake_type": "security", "consolidated": False}})),
            Mock(),  # For _mark_reflections_consolidated which doesn't check return value
        ]
        mock_session.run.side_effect = mock_results

        rm = AgentReflectionMemory(memory)
        summary = rm.consolidate_reflections(reflection_ids=["r1", "r2"])

        assert summary["consolidated"] is True
        assert summary["reflections_processed"] == 2

    def test_count_reflections(self, mock_memory):
        """Test counting reflections."""
        memory, mock_session = mock_memory

        mock_result = Mock()
        mock_result.single.return_value = {"count": 42}
        mock_session.run.return_value = mock_result

        rm = AgentReflectionMemory(memory)
        count = rm.count_reflections(agent="dev1", consolidated=False)

        assert count == 42

    def test_create_indexes(self, mock_memory):
        """Test creating indexes."""
        memory, mock_session = mock_memory

        rm = AgentReflectionMemory(memory)
        indexes = rm.create_indexes()

        assert len(indexes) == 5
        assert "reflection_id_idx" in indexes
        assert "reflection_agent_idx" in indexes
        assert "reflection_type_idx" in indexes
        assert "reflection_consolidated_idx" in indexes
        assert "reflection_created_idx" in indexes

    def test_create_indexes_fallback_mode(self, mock_memory):
        """Test creating indexes in fallback mode."""
        memory, mock_session = mock_memory

        mock_context = MagicMock()
        mock_context.__enter__ = Mock(return_value=None)
        mock_context.__exit__ = Mock(return_value=False)
        memory._session.return_value = mock_context

        rm = AgentReflectionMemory(memory)
        indexes = rm.create_indexes()

        assert indexes == []


class TestConvenienceFunctions:
    """Test convenience functions."""

    @pytest.fixture
    def mock_memory(self):
        """Create a mock OperationalMemory."""
        memory = Mock()
        memory._generate_id.return_value = "test-id"
        memory._now.return_value = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        mock_session = Mock()
        mock_context = MagicMock()
        mock_context.__enter__ = Mock(return_value=mock_session)
        mock_context.__exit__ = Mock(return_value=False)
        memory._session.return_value = mock_context

        return memory, mock_session

    def test_create_reflection_memory(self, mock_memory):
        """Test create_reflection_memory convenience function."""
        memory, _ = mock_memory
        rm = create_reflection_memory(memory, embedding_dimension=256)

        assert isinstance(rm, AgentReflectionMemory)
        assert rm.embedding_dimension == 256

    def test_record_agent_mistake(self, mock_memory):
        """Test record_agent_mistake convenience function."""
        memory, mock_session = mock_memory

        mock_result = Mock()
        mock_result.single.return_value = {"reflection_id": "test-id"}
        mock_session.run.return_value = mock_result

        rm = AgentReflectionMemory(memory)
        reflection_id = record_agent_mistake(
            rm,
            agent="developer",
            mistake_type="security",
            context="test context",
            expected_behavior="expected",
            actual_behavior="actual",
            root_cause="cause",
            lesson="lesson"
        )

        assert reflection_id == "test-id"


class TestExtractCommonThemes:
    """Test theme extraction functionality."""

    @pytest.fixture
    def reflection_memory(self):
        """Create a reflection memory with mocked dependencies."""
        memory = Mock()
        return AgentReflectionMemory(memory)

    def test_extract_common_themes(self, reflection_memory):
        """Test extracting common themes from reflections."""
        reflections = [
            {"lesson": "Always validate passwords before storing"},
            {"lesson": "Password validation is important for security"},
            {"lesson": "Security requires careful validation"},
        ]

        themes = reflection_memory._extract_common_themes(reflections)

        assert isinstance(themes, list)
        assert len(themes) <= 10
        # "password", "security", and "validation" should appear as common themes
        assert any("password" in t.lower() for t in themes) or any("security" in t.lower() for t in themes)

    def test_extract_themes_empty(self, reflection_memory):
        """Test extracting themes from empty reflections."""
        themes = reflection_memory._extract_common_themes([])
        assert themes == []

    def test_extract_themes_single_word(self, reflection_memory):
        """Test extracting themes with single word lessons."""
        reflections = [
            {"lesson": "test"},
            {"lesson": "test"},
        ]

        themes = reflection_memory._extract_common_themes(reflections)
        # Words shorter than 5 chars are filtered out
        assert "test" not in themes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
