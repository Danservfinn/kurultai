"""
Tests for Semantic Similarity Analysis functionality.

Tests cover:
- Cosine similarity calculations
- Dependency detection via similarity
- Dependency type determination
- Vector operations

Location: /Users/kurultai/molt/tests/test_semantic_analysis.py
"""

import os
import sys
from typing import List, Tuple, Dict, Any, Optional
from unittest.mock import Mock, MagicMock, patch
import math

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.multi_goal_orchestration import (
    RelationshipType,
    NodeStatus,
    Priority,
    TaskNode,
    GoalNode,
)


# =============================================================================
# Semantic Analysis Functions
# =============================================================================

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Calculate cosine similarity between two vectors.

    Returns 1.0 for identical vectors, 0.0 for orthogonal vectors.
    """
    if len(vec1) != len(vec2):
        raise ValueError("Vectors must have same length")

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))

    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0

    return dot_product / (magnitude1 * magnitude2)


def analyze_dependencies(
    task1_embedding: List[float],
    task2_embedding: List[float],
    task1_type: str = "generic",
    task2_type: str = "generic"
) -> Tuple[float, str]:
    """
    Analyze if two tasks have a dependency relationship based on semantic similarity.

    Returns:
        Tuple of (similarity_score, dependency_type)
    """
    similarity = cosine_similarity(task1_embedding, task2_embedding)

    if similarity >= 0.8:
        dependency_type = "strong"
    elif similarity >= 0.5:
        dependency_type = "moderate"
    elif similarity >= 0.3:
        dependency_type = "weak"
    else:
        dependency_type = "none"

    return similarity, dependency_type


def determine_dependency_type(
    source_task: Dict[str, Any],
    target_task: Dict[str, Any]
) -> RelationshipType:
    """
    Determine the type of relationship between two tasks.

    Based on task types and semantic analysis.
    """
    source_type = source_task.get("type", "generic")
    target_type = target_task.get("type", "generic")

    # Research should happen before strategy/implementation
    if source_type == "research" and target_type in ["strategy", "implementation"]:
        return RelationshipType.ENABLES

    # Analysis should happen before code
    if source_type == "analysis" and target_type == "code":
        return RelationshipType.ENABLES

    # Testing depends on implementation
    if source_type == "code" and target_type == "test":
        return RelationshipType.ENABLES

    # Documentation can happen in parallel
    if source_type == "documentation" or target_type == "documentation":
        return RelationshipType.INDEPENDENT

    # Default to independent for unknown combinations
    return RelationshipType.INDEPENDENT


# =============================================================================
# TestSemanticAnalysis
# =============================================================================

class TestSemanticAnalysis:
    """Tests for semantic similarity analysis."""

    def test_cosine_similarity_identical_vectors(self):
        """Test cosine similarity of identical vectors."""
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [1.0, 2.0, 3.0]

        similarity = cosine_similarity(vec1, vec2)

        assert math.isclose(similarity, 1.0, rel_tol=1e-9)

    def test_cosine_similarity_orthogonal_vectors(self):
        """Test cosine similarity of orthogonal vectors."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]

        similarity = cosine_similarity(vec1, vec2)

        assert math.isclose(similarity, 0.0, rel_tol=1e-9)

    def test_cosine_similarity_opposite_vectors(self):
        """Test cosine similarity of opposite (negative correlation) vectors."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [-1.0, 0.0, 0.0]

        similarity = cosine_similarity(vec1, vec2)

        assert math.isclose(similarity, -1.0, rel_tol=1e-9)

    def test_cosine_similarity_zero_vector(self):
        """Test cosine similarity with zero vector."""
        vec1 = [0.0, 0.0, 0.0]
        vec2 = [1.0, 2.0, 3.0]

        similarity = cosine_similarity(vec1, vec2)

        assert similarity == 0.0

    def test_cosine_similarity_different_length_raises(self):
        """Test that different length vectors raise an error."""
        vec1 = [1.0, 2.0]
        vec2 = [1.0, 2.0, 3.0]

        with pytest.raises(ValueError):
            cosine_similarity(vec1, vec2)

    def test_cosine_similarity_partial_match(self):
        """Test cosine similarity with partially matching vectors."""
        vec1 = [1.0, 1.0, 0.0]
        vec2 = [1.0, 0.0, 1.0]

        similarity = cosine_similarity(vec1, vec2)

        # Should be between 0 and 1 (partial match)
        assert 0.0 < similarity < 1.0


# =============================================================================
# TestDependencyAnalysis
# =============================================================================

class TestDependencyAnalysis:
    """Tests for dependency analysis based on semantic similarity."""

    def test_analyze_dependencies_high_similarity(self):
        """Test dependency detection with high similarity."""
        vec1 = [0.9, 0.1, 0.0]
        vec2 = [0.85, 0.15, 0.0]

        similarity, dep_type = analyze_dependencies(vec1, vec2)

        assert similarity >= 0.8
        assert dep_type == "strong"

    def test_analyze_dependencies_medium_similarity(self):
        """Test dependency detection with medium similarity."""
        # Use more divergent vectors for medium similarity (~0.5-0.7 range)
        vec1 = [0.8, 0.2, 0.0]
        vec2 = [0.2, 0.8, 0.0]

        similarity, dep_type = analyze_dependencies(vec1, vec2)

        assert 0.3 <= similarity < 0.8
        assert dep_type in ["weak", "moderate"]

    def test_analyze_dependencies_low_similarity(self):
        """Test dependency detection with low similarity."""
        vec1 = [0.9, 0.1, 0.0]
        vec2 = [0.1, 0.9, 0.0]

        similarity, dep_type = analyze_dependencies(vec1, vec2)

        assert similarity < 0.5
        assert dep_type in ["weak", "none"]

    def test_analyze_dependencies_no_similarity(self):
        """Test dependency detection with no similarity."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]

        similarity, dep_type = analyze_dependencies(vec1, vec2)

        assert math.isclose(similarity, 0.0, abs_tol=1e-9)
        assert dep_type == "none"


# =============================================================================
# TestDependencyTypeDetermination
# =============================================================================

class TestDependencyTypeDetermination:
    """Tests for determining dependency types based on task types."""

    def test_determine_dependency_type_research_to_strategy(self):
        """Test dependency from research to strategy."""
        source = {"type": "research", "title": "Research auth methods"}
        target = {"type": "strategy", "title": "Define auth strategy"}

        rel_type = determine_dependency_type(source, target)

        assert rel_type == RelationshipType.ENABLES

    def test_determine_dependency_type_research_to_implementation(self):
        """Test dependency from research to implementation."""
        source = {"type": "research", "title": "Research API options"}
        target = {"type": "implementation", "title": "Implement API"}

        rel_type = determine_dependency_type(source, target)

        assert rel_type == RelationshipType.ENABLES

    def test_determine_dependency_type_analysis_to_code(self):
        """Test dependency from analysis to code."""
        source = {"type": "analysis", "title": "Analyze requirements"}
        target = {"type": "code", "title": "Implement features"}

        rel_type = determine_dependency_type(source, target)

        assert rel_type == RelationshipType.ENABLES

    def test_determine_dependency_type_code_to_test(self):
        """Test dependency from code to test."""
        source = {"type": "code", "title": "Implement feature"}
        target = {"type": "test", "title": "Write tests"}

        rel_type = determine_dependency_type(source, target)

        assert rel_type == RelationshipType.ENABLES

    def test_determine_dependency_type_documentation_independent(self):
        """Test that documentation is independent."""
        source = {"type": "documentation", "title": "Write docs"}
        target = {"type": "code", "title": "Implement feature"}

        rel_type = determine_dependency_type(source, target)

        assert rel_type == RelationshipType.INDEPENDENT

    def test_determine_dependency_type_default_parallel(self):
        """Test default to independent for unknown combinations."""
        source = {"type": "unknown", "title": "Task A"}
        target = {"type": "also_unknown", "title": "Task B"}

        rel_type = determine_dependency_type(source, target)

        assert rel_type == RelationshipType.INDEPENDENT

    def test_determine_dependency_type_generic_to_generic(self):
        """Test generic tasks default to independent."""
        source = {"type": "generic", "title": "Task A"}
        target = {"type": "generic", "title": "Task B"}

        rel_type = determine_dependency_type(source, target)

        assert rel_type == RelationshipType.INDEPENDENT


# =============================================================================
# TestSimilarityThresholds
# =============================================================================

class TestSimilarityThresholds:
    """Tests for similarity threshold configurations."""

    @pytest.fixture
    def thresholds(self):
        """Default similarity thresholds."""
        return {
            "strong": 0.8,
            "moderate": 0.5,
            "weak": 0.3,
            "none": 0.0
        }

    def test_threshold_strong_dependency(self, thresholds):
        """Test strong dependency threshold."""
        vec1 = [0.85, 0.15, 0.0]
        vec2 = [0.82, 0.18, 0.0]

        similarity, dep_type = analyze_dependencies(vec1, vec2)

        assert similarity >= thresholds["strong"]
        assert dep_type == "strong"

    def test_threshold_moderate_dependency(self, thresholds):
        """Test moderate dependency threshold."""
        # Use vectors with moderate similarity (around 0.5-0.7)
        vec1 = [0.8, 0.3, 0.0]
        vec2 = [0.3, 0.8, 0.0]

        similarity, dep_type = analyze_dependencies(vec1, vec2)

        assert thresholds["moderate"] <= similarity < thresholds["strong"]
        assert dep_type == "moderate"

    def test_threshold_weak_dependency(self, thresholds):
        """Test weak dependency threshold."""
        # Use vectors with low similarity (around 0.3-0.5)
        vec1 = [0.9, 0.1, 0.0]
        vec2 = [0.3, 0.7, 0.4]

        similarity, dep_type = analyze_dependencies(vec1, vec2)

        assert thresholds["weak"] <= similarity < thresholds["moderate"]
        assert dep_type == "weak"

    def test_threshold_no_dependency(self, thresholds):
        """Test no dependency threshold."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 0.0, 1.0]

        similarity, dep_type = analyze_dependencies(vec1, vec2)

        assert similarity < thresholds["weak"]
        assert dep_type == "none"


# =============================================================================
# TestEdgeCases
# =============================================================================

class TestSemanticAnalysisEdgeCases:
    """Edge case tests for semantic analysis."""

    def test_empty_vectors(self):
        """Test handling of empty vectors."""
        vec1 = []
        vec2 = []

        # Implementation returns (0.0, 'none') for empty vectors
        similarity, dep_type = analyze_dependencies(vec1, vec2)
        assert similarity == 0.0
        assert dep_type == 'none'

    def test_single_dimension_vectors(self):
        """Test single dimension vectors."""
        vec1 = [1.0]
        vec2 = [0.5]

        similarity = cosine_similarity(vec1, vec2)

        assert 0.0 <= similarity <= 1.0

    def test_high_dimensional_vectors(self):
        """Test high dimensional vectors."""
        vec1 = [1.0] * 1000
        vec2 = [1.0] * 1000

        similarity = cosine_similarity(vec1, vec2)

        assert math.isclose(similarity, 1.0, rel_tol=1e-9)

    def test_negative_values(self):
        """Test vectors with negative values."""
        vec1 = [0.5, -0.5, 0.0]
        vec2 = [-0.5, 0.5, 0.0]

        similarity = cosine_similarity(vec1, vec2)

        # Should be negative (opposite direction)
        assert similarity < 0

    def test_very_small_values(self):
        """Test vectors with very small values."""
        vec1 = [1e-10, 2e-10, 3e-10]
        vec2 = [2e-10, 4e-10, 6e-10]

        similarity = cosine_similarity(vec1, vec2)

        # Should still compute correctly (proportional vectors)
        assert math.isclose(similarity, 1.0, rel_tol=1e-9)

    def test_mixed_positive_negative(self):
        """Test vectors with mixed positive and negative values."""
        vec1 = [0.7, -0.3, 0.2]
        vec2 = [0.5, -0.2, 0.1]

        similarity = cosine_similarity(vec1, vec2)

        # Should be positive (somewhat aligned)
        assert similarity > 0

    def test_normalized_vectors(self):
        """Test that normalized vectors work correctly."""
        vec1 = [0.6, 0.8, 0.0]  # Already normalized (sqrt(0.6^2 + 0.8^2) = 1)
        vec2 = [0.8, 0.6, 0.0]  # Also normalized

        similarity = cosine_similarity(vec1, vec2)

        expected = 0.6 * 0.8 + 0.8 * 0.6  # Dot product
        assert math.isclose(similarity, expected, rel_tol=1e-9)


# =============================================================================
# TestTaskEmbeddingSimulation
# =============================================================================

class TestTaskEmbeddingSimulation:
    """Tests simulating task embeddings for dependency detection."""

    def test_simulated_research_task_embedding(self):
        """Test simulated embedding for research task."""
        # Research tasks might have high values in "analysis" dimensions
        research_embedding = [0.1, 0.8, 0.1, 0.0, 0.0]

        # Implementation tasks have high values in "code" dimensions
        impl_embedding = [0.0, 0.1, 0.8, 0.1, 0.0]

        similarity = cosine_similarity(research_embedding, impl_embedding)

        # Should have some similarity (related domain) but not identical
        assert 0.0 < similarity < 0.9

    def test_simulated_related_tasks(self):
        """Test that related tasks have higher similarity."""
        # Auth-related tasks
        auth_research = [0.8, 0.1, 0.0, 0.1, 0.0]
        auth_impl = [0.7, 0.2, 0.0, 0.1, 0.0]

        # Unrelated task
        ui_task = [0.0, 0.0, 0.0, 0.9, 0.1]

        auth_sim = cosine_similarity(auth_research, auth_impl)
        ui_sim = cosine_similarity(auth_research, ui_task)

        assert auth_sim > ui_sim

    def test_embedding_dimension_order_preserves_similarity(self):
        """Test that embedding dimension order affects similarity."""
        vec1 = [0.8, 0.2, 0.0, 0.0]
        vec2 = [0.7, 0.3, 0.0, 0.0]  # Same distribution

        vec3 = [0.0, 0.0, 0.8, 0.2]  # Different dimension

        sim12 = cosine_similarity(vec1, vec2)
        sim13 = cosine_similarity(vec1, vec3)

        assert sim12 > sim13
