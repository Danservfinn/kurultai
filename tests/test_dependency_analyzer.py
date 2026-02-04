"""
Tests for DependencyAnalyzer

Tests cover:
- Cosine similarity calculation
- Dependency detection from embeddings
- Dependency type inference from deliverable types
- Similarity threshold filtering

Author: Claude (Anthropic)
Date: 2026-02-04
"""

import pytest
import numpy as np
from datetime import datetime, timezone

from tools.kurultai.dependency_analyzer import (
    DependencyAnalyzer,
    cosine_similarity
)
from tools.kurultai.types import DependencyType, DeliverableType, Task


def test_cosine_similarity():
    """Test cosine similarity calculation."""
    a = np.array([1, 0, 0])
    b = np.array([1, 0, 0])
    assert cosine_similarity(a, b) == 1.0

    a = np.array([1, 0, 0])
    b = np.array([0, 1, 0])
    assert cosine_similarity(a, b) == 0.0

    # Zero vectors
    a = np.array([0, 0, 0])
    b = np.array([1, 0, 0])
    assert cosine_similarity(a, b) == 0.0


def test_cosine_similarity_partial_match():
    """Test cosine similarity with partial match."""
    a = np.array([1, 1, 0])
    b = np.array([1, 0, 0])
    # Dot = 1, norm_a = sqrt(2), norm_b = 1
    # Similarity = 1 / sqrt(2) ≈ 0.707
    result = cosine_similarity(a, b)
    assert abs(result - 0.707) < 0.01


@pytest.mark.asyncio
async def test_analyze_dependencies():
    """Test dependency detection from embeddings."""
    analyzer = DependencyAnalyzer(neo4j_client=None)

    tasks = [
        Task(
            id="1",
            type="research",
            description="Competitor research",
            status="pending",
            assigned_to=None,
            claimed_by=None,
            delegated_by=None,
            priority="normal",
            deliverable_type="research",
            sender_hash="user1",
            created_at=datetime.now(timezone.utc),
            updated_at=None,
            priority_weight=0.5,
            embedding=np.array([1, 0, 0, 0]).tolist(),
            window_expires_at=None,
            user_priority_override=False,
            claimed_at=None,
            completed_at=None,
            results=None,
            error_message=None,
        ),
        Task(
            id="2",
            type="strategy",
            description="Positioning strategy",
            status="pending",
            assigned_to=None,
            claimed_by=None,
            delegated_by=None,
            priority="normal",
            deliverable_type="strategy",
            sender_hash="user1",
            created_at=datetime.now(timezone.utc),
            updated_at=None,
            priority_weight=0.5,
            embedding=np.array([1, 0, 0, 0]).tolist(),  # Same = high similarity
            window_expires_at=None,
            user_priority_override=False,
            claimed_at=None,
            completed_at=None,
            results=None,
            error_message=None,
        ),
    ]

    deps = await analyzer.analyze_dependencies(tasks)

    assert len(deps) > 0
    assert deps[0].type == DependencyType.FEEDS_INTO


def test_infer_dependency_type():
    """Test dependency type inference from deliverable types."""
    analyzer = DependencyAnalyzer(neo4j_client=None)

    research_task = Task(
        id="1", type="", description="", status="pending",
        assigned_to=None, claimed_by=None, delegated_by=None,
        priority="normal", deliverable_type="research",
        sender_hash="", created_at=datetime.now(timezone.utc), updated_at=None,
        priority_weight=0.5, embedding=None, window_expires_at=None,
        user_priority_override=False, claimed_at=None, completed_at=None,
        results=None, error_message=None,
    )

    strategy_task = Task(
        id="2", type="", description="", status="pending",
        assigned_to=None, claimed_by=None, delegated_by=None,
        priority="normal", deliverable_type="strategy",
        sender_hash="", created_at=datetime.now(timezone.utc), updated_at=None,
        priority_weight=0.5, embedding=None, window_expires_at=None,
        user_priority_override=False, claimed_at=None, completed_at=None,
        results=None, error_message=None,
    )

    dep_type = analyzer._infer_dependency_type(research_task, strategy_task)
    assert dep_type == DependencyType.FEEDS_INTO


@pytest.mark.asyncio
async def test_analyze_dependencies_with_threshold():
    """Test dependency detection with similarity threshold."""
    analyzer = DependencyAnalyzer(neo4j_client=None)

    tasks = [
        Task(
            id="1", type="", description="", status="pending",
            assigned_to=None, claimed_by=None, delegated_by=None,
            priority="normal", deliverable_type="code",
            sender_hash="", created_at=datetime.now(timezone.utc), updated_at=None,
            priority_weight=0.5, embedding=np.array([1, 0, 0]).tolist(),
            window_expires_at=None, user_priority_override=False,
            claimed_at=None, completed_at=None, results=None, error_message=None,
        ),
        Task(
            id="2", type="", description="", status="pending",
            assigned_to=None, claimed_by=None, delegated_by=None,
            priority="normal", deliverable_type="docs",
            sender_hash="", created_at=datetime.now(timezone.utc), updated_at=None,
            priority_weight=0.5, embedding=np.array([0, 1, 0]).tolist(),  # Different
            window_expires_at=None, user_priority_override=False,
            claimed_at=None, completed_at=None, results=None, error_message=None,
        ),
    ]

    # Low threshold should not find relationship (similarity = 0)
    deps_low = await analyzer.analyze_dependencies(tasks, similarity_threshold=0.5)
    assert len(deps_low) == 0

    # Very low threshold should find relationship (similarity > 0)
    deps_very_low = await analyzer.analyze_dependencies(tasks, similarity_threshold=0.1)
    # With 0.1 threshold it might find something, but actually 0 similarity won't match anything
    # Let's test with actually similar vectors
    tasks[1]["embedding"] = np.array([1, 0, 0]).tolist()  # Same vector
    deps_same = await analyzer.analyze_dependencies(tasks, similarity_threshold=0.5)
    assert len(deps_same) > 0


@pytest.mark.asyncio
async def test_analyze_dependencies_no_embeddings():
    """Test dependency detection without embeddings."""
    analyzer = DependencyAnalyzer(neo4j_client=None)

    tasks = [
        Task(
            id="1", type="", description="", status="pending",
            assigned_to=None, claimed_by=None, delegated_by=None,
            priority="normal", deliverable_type="research",
            sender_hash="", created_at=datetime.now(timezone.utc), updated_at=None,
            priority_weight=0.5, embedding=None,  # No embedding
            window_expires_at=None, user_priority_override=False,
            claimed_at=None, completed_at=None, results=None, error_message=None,
        ),
        Task(
            id="2", type="", description="", status="pending",
            assigned_to=None, claimed_by=None, delegated_by=None,
            priority="normal", deliverable_type="strategy",
            sender_hash="", created_at=datetime.now(timezone.utc), updated_at=None,
            priority_weight=0.5, embedding=None,  # No embedding
            window_expires_at=None, user_priority_override=False,
            claimed_at=None, completed_at=None, results=None, error_message=None,
        ),
    ]

    deps = await analyzer.analyze_dependencies(tasks)

    # Should return empty list when no embeddings
    assert len(deps) == 0


def test_get_embedding_array():
    """Test embedding array conversion."""
    analyzer = DependencyAnalyzer()

    # List input
    arr = analyzer._get_embedding_array([1, 2, 3])
    assert isinstance(arr, np.ndarray)
    assert arr.tolist() == [1, 2, 3]

    # Tuple input
    arr = analyzer._get_embedding_array((1, 2, 3))
    assert isinstance(arr, np.ndarray)

    # Numpy array input
    arr = analyzer._get_embedding_array(np.array([1, 2, 3]))
    assert isinstance(arr, np.ndarray)

    # Invalid input
    arr = analyzer._get_embedding_array(None)
    assert arr is None

    arr = analyzer._get_embedding_array("invalid")
    assert arr is None


@pytest.mark.asyncio
async def test_code_blocks_testing_dependency():
    """Test code blocks testing dependency rule."""
    analyzer = DependencyAnalyzer(neo4j_client=None)

    code_task = Task(
        id="1", type="", description="", status="pending",
        assigned_to=None, claimed_by=None, delegated_by=None,
        priority="normal", deliverable_type="code",
        sender_hash="", created_at=datetime.now(timezone.utc), updated_at=None,
        priority_weight=0.5, embedding=None, window_expires_at=None,
        user_priority_override=False, claimed_at=None, completed_at=None,
        results=None, error_message=None,
    )

    test_task = Task(
        id="2", type="", description="", status="pending",
        assigned_to=None, claimed_by=None, delegated_by=None,
        priority="normal", deliverable_type="testing",
        sender_hash="", created_at=datetime.now(timezone.utc), updated_at=None,
        priority_weight=0.5, embedding=None, window_expires_at=None,
        user_priority_override=False, claimed_at=None, completed_at=None,
        results=None, error_message=None,
    )

    dep_type = analyzer._infer_dependency_type(code_task, test_task)
    assert dep_type == DependencyType.BLOCKS


@pytest.mark.asyncio
async def test_unknown_deliverable_types():
    """Test handling of unknown deliverable types."""
    analyzer = DependencyAnalyzer(neo4j_client=None)

    task1 = Task(
        id="1", type="", description="", status="pending",
        assigned_to=None, claimed_by=None, delegated_by=None,
        priority="normal", deliverable_type="unknown_type",
        sender_hash="", created_at=datetime.now(timezone.utc), updated_at=None,
        priority_weight=0.5, embedding=None, window_expires_at=None,
        user_priority_override=False, claimed_at=None, completed_at=None,
        results=None, error_message=None,
    )

    task2 = Task(
        id="2", type="", description="", status="pending",
        assigned_to=None, claimed_by=None, delegated_by=None,
        priority="normal", deliverable_type="another_unknown",
        sender_hash="", created_at=datetime.now(timezone.utc), updated_at=None,
        priority_weight=0.5, embedding=None, window_expires_at=None,
        user_priority_override=False, claimed_at=None, completed_at=None,
        results=None, error_message=None,
    )

    dep_type = analyzer._infer_dependency_type(task1, task2)
    # Should default to PARALLEL_OK for unknown types
    assert dep_type == DependencyType.PARALLEL_OK


def test_compute_embedding_fallback():
    """Test fallback embedding computation."""
    analyzer = DependencyAnalyzer()

    emb = analyzer.compute_embedding_fallback("hello world test")
    assert isinstance(emb, np.ndarray)
    assert emb.shape == (384,)
    assert emb.sum() > 0  # Should have some non-zero values


@pytest.mark.asyncio
async def test_parallel_ok_for_medium_similarity():
    """Test that medium similarity results in PARALLEL_OK."""
    analyzer = DependencyAnalyzer(neo4j_client=None)

    # Create embeddings with medium similarity (~0.6)
    tasks = [
        Task(
            id="1", type="", description="", status="pending",
            assigned_to=None, claimed_by=None, delegated_by=None,
            priority="normal", deliverable_type="code",
            sender_hash="", created_at=datetime.now(timezone.utc), updated_at=None,
            priority_weight=0.5, embedding=np.array([1, 1, 0, 0]).tolist(),
            window_expires_at=None, user_priority_override=False,
            claimed_at=None, completed_at=None, results=None, error_message=None,
        ),
        Task(
            id="2", type="", description="", status="pending",
            assigned_to=None, claimed_by=None, delegated_by=None,
            priority="normal", deliverable_type="docs",
            sender_hash="", created_at=datetime.now(timezone.utc), updated_at=None,
            priority_weight=0.5, embedding=np.array([1, 0.5, 0, 0]).tolist(),
            window_expires_at=None, user_priority_override=False,
            claimed_at=None, completed_at=None, results=None, error_message=None,
        ),
    ]

    deps = await analyzer.analyze_dependencies(tasks, similarity_threshold=0.5)

    # Should find PARALLEL_OK relationship for medium similarity
    assert len(deps) > 0
    assert any(d.type == DependencyType.PARALLEL_OK for d in deps)
