"""
Dependency Analyzer

Analyzes semantic similarity between tasks to detect relationships.

Author: Claude (Anthropic)
Date: 2026-02-04
"""

import numpy as np
from typing import List, Optional

from .types import (
    Dependency,
    DependencyType,
    Task,
    DeliverableType,
    HIGH_SIMILARITY,
    MEDIUM_SIMILARITY,
)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Compute cosine similarity between two vectors.

    Args:
        a: First vector
        b: Second vector

    Returns:
        Similarity score between 0 and 1
    """
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(np.dot(a, b) / (norm_a * norm_b))


class DependencyAnalyzer:
    """
    Analyzes tasks to detect dependency relationships.

    Uses semantic similarity and deliverable type heuristics
    to infer task dependencies.
    """

    # Deliverable type mappings for dependency inference
    DEPENDENCY_RULES = {
        # Research feeds into strategy
        (DeliverableType.RESEARCH, DeliverableType.STRATEGY): DependencyType.FEEDS_INTO,
        # Analysis blocks code
        (DeliverableType.ANALYSIS, DeliverableType.CODE): DependencyType.BLOCKS,
        # Research feeds into content
        (DeliverableType.RESEARCH, DeliverableType.CONTENT): DependencyType.FEEDS_INTO,
        # Strategy feeds into ops
        (DeliverableType.STRATEGY, DeliverableType.OPS): DependencyType.FEEDS_INTO,
        # Strategy feeds into code
        (DeliverableType.STRATEGY, DeliverableType.CODE): DependencyType.FEEDS_INTO,
        # Research feeds into analysis
        (DeliverableType.RESEARCH, DeliverableType.ANALYSIS): DependencyType.FEEDS_INTO,
        # Code blocks testing
        (DeliverableType.CODE, DeliverableType.TESTING): DependencyType.BLOCKS,
        # Docs feed into content
        (DeliverableType.DOCS, DeliverableType.CONTENT): DependencyType.FEEDS_INTO,
    }

    def __init__(self, neo4j_client=None):
        self.neo4j = neo4j_client

    async def analyze_dependencies(
        self,
        tasks: List[Task],
        similarity_threshold: float = None
    ) -> List[Dependency]:
        """
        Compare task embeddings to detect relationships.

        Args:
            tasks: List of tasks to analyze
            similarity_threshold: Minimum similarity for relationship detection

        Returns:
            List of detected dependencies
        """
        if similarity_threshold is None:
            similarity_threshold = HIGH_SIMILARITY

        dependencies = []

        for i, task_a in enumerate(tasks):
            for task_b in tasks[i+1:]:
                # Skip if no embeddings
                if not task_a.get("embedding") or not task_b.get("embedding"):
                    continue

                # Handle different embedding formats
                emb_a = self._get_embedding_array(task_a["embedding"])
                emb_b = self._get_embedding_array(task_b["embedding"])

                if emb_a is None or emb_b is None:
                    continue

                similarity = cosine_similarity(emb_a, emb_b)

                # High similarity = likely related
                if similarity >= similarity_threshold:
                    dep_type = self._infer_dependency_type(task_a, task_b)
                    dependencies.append(Dependency(
                        from_task=task_a["id"],
                        to_task=task_b["id"],
                        type=dep_type,
                        weight=similarity,
                        detected_by="semantic",
                        confidence=similarity
                    ))

                # Medium similarity = might be parallel
                elif similarity >= MEDIUM_SIMILARITY:
                    dependencies.append(Dependency(
                        from_task=task_a["id"],
                        to_task=task_b["id"],
                        type=DependencyType.PARALLEL_OK,
                        weight=similarity,
                        detected_by="semantic",
                        confidence=similarity
                    ))

        return dependencies

    def _get_embedding_array(self, embedding) -> Optional[np.ndarray]:
        """
        Convert embedding to numpy array.

        Args:
            embedding: Embedding data (list, tuple, or array)

        Returns:
            Numpy array or None if conversion fails
        """
        try:
            if isinstance(embedding, np.ndarray):
                return embedding
            elif isinstance(embedding, (list, tuple)):
                return np.array(embedding, dtype=float)
            else:
                return None
        except (TypeError, ValueError):
            return None

    def _infer_dependency_type(self, a: Task, b: Task) -> DependencyType:
        """
        Infer dependency direction based on deliverable types.

        Args:
            a: First task
            b: Second task

        Returns:
            Inferred dependency type
        """
        type_a_str = a.get("deliverable_type", "analysis")
        type_b_str = b.get("deliverable_type", "analysis")

        try:
            type_a = DeliverableType(type_a_str)
            type_b = DeliverableType(type_b_str)
        except ValueError:
            # Unknown deliverable types, default to parallel
            return DependencyType.PARALLEL_OK

        # Check rules
        if (type_a, type_b) in self.DEPENDENCY_RULES:
            return self.DEPENDENCY_RULES[(type_a, type_b)]
        elif (type_b, type_a) in self.DEPENDENCY_RULES:
            # Reverse direction
            return self.DEPENDENCY_RULES[(type_b, type_a)]

        # Default: parallel is safe
        return DependencyType.PARALLEL_OK

    async def find_similar_tasks(
        self,
        embedding: np.ndarray,
        sender_hash: str,
        threshold: float = None,
        limit: int = 10
    ) -> List[Task]:
        """
        Find similar tasks using vector search with fallback.

        Args:
            embedding: Query vector
            sender_hash: User identifier
            threshold: Minimum similarity score
            limit: Maximum results

        Returns:
            List of similar tasks
        """
        if threshold is None:
            threshold = HIGH_SIMILARITY

        # Try vector index first
        if self.neo4j:
            try:
                vector_query = """
                CALL db.index.vector.queryNodes('task_embedding', $limit, $embedding)
                YIELD node, score
                WHERE node.sender_hash = $sender_hash AND score >= $threshold
                RETURN node as task, score
                """
                results = await self._run_query(vector_query, {
                    "embedding": embedding.tolist(),
                    "sender_hash": sender_hash,
                    "threshold": threshold,
                    "limit": limit
                })
                if results:
                    return results
            except Exception as e:
                # Vector index unavailable, fall back to text search
                print(f"Vector index unavailable: {e}")

        # Fallback: return empty for now
        # Could implement full-text search here
        return []

    async def _run_query(self, query: str, params: dict) -> List[Task]:
        """Run a Neo4j query and return results."""
        if not self.neo4j:
            return []

        try:
            with self.neo4j._session() as session:
                if session is None:
                    return []

                result = session.run(query, **params)
                return [dict(record["task"]) for record in result]
        except Exception:
            return []

    def compute_embedding_fallback(self, text: str) -> np.ndarray:
        """
        Fallback embedding using simple word overlap.

        This is a very basic fallback that creates a simple vector
        based on word presence. For production, use a proper
        embedding model.

        Args:
            text: Text to embed

        Returns:
            Numpy array representing the text
        """
        # Simple word-based fallback
        words = set(text.lower().split())
        # Create a hash-based vector
        vector = np.zeros(384)  # Match common embedding dimension
        for word in words:
            # Simple hash to position
            idx = hash(word) % 384
            vector[idx] = 1.0
        return vector
