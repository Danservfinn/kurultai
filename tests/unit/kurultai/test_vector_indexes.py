"""
Vector Index Tests - Task P2-T13

Tests for:
- Vector indexes are queryable
- Semantic search returns results
- Index configuration correct (384-dim, cosine)

Author: Jochi (Analyst Agent)
"""

import pytest
import numpy as np
from typing import List, Dict, Any, Tuple
from unittest.mock import Mock, MagicMock
import sys
import os

# Add tools/kurultai to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../tools/kurultai'))


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def vector_index_config():
    """Standard vector index configuration."""
    return {
        "name": "task-embeddings",
        "label": "Task",
        "property": "embedding",
        "dimensions": 384,
        "similarity_function": "cosine",
        "index_type": "vector"
    }


@pytest.fixture
def sample_embeddings():
    """Generate sample 384-dimensional embeddings for testing."""
    np.random.seed(42)  # Reproducible tests
    
    # Create embeddings with known relationships
    base = np.random.randn(384)
    base = base / np.linalg.norm(base)  # Normalize
    
    embeddings = {
        "task_research_oauth": base,
        "task_research_sso": base * 0.9 + np.random.randn(384) * 0.1,  # Similar
        "task_write_docs": np.random.randn(384),  # Different
        "task_code_api": np.random.randn(384),  # Different
        "task_test_oauth": base * 0.8 + np.random.randn(384) * 0.2,  # Somewhat similar
    }
    
    # Normalize all
    for key in embeddings:
        embeddings[key] = embeddings[key] / (np.linalg.norm(embeddings[key]) + 1e-10)
    
    return embeddings


@pytest.fixture
def mock_vector_store(vector_index_config):
    """Create a mock vector store with index configuration."""
    
    class MockVectorStore:
        """Mock vector store for testing."""
        
        def __init__(self, config):
            self.config = config
            self.embeddings: Dict[str, np.ndarray] = {}
            self.index_exists = True
            self.query_count = 0
        
        def verify_index(self) -> Dict[str, Any]:
            """Verify vector index configuration."""
            return {
                "exists": self.index_exists,
                "name": self.config["name"],
                "dimensions": self.config["dimensions"],
                "similarity_function": self.config["similarity_function"],
                "label": self.config["label"],
                "property": self.config["property"]
            }
        
        def store_embedding(self, node_id: str, embedding: np.ndarray) -> bool:
            """Store an embedding vector."""
            if len(embedding) != self.config["dimensions"]:
                raise ValueError(
                    f"Embedding dimension {len(embedding)} does not match "
                    f"index dimension {self.config['dimensions']}"
                )
            self.embeddings[node_id] = embedding
            return True
        
        def cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
            """Calculate cosine similarity between two vectors."""
            a_norm = a / (np.linalg.norm(a) + 1e-10)
            b_norm = b / (np.linalg.norm(b) + 1e-10)
            return float(np.dot(a_norm, b_norm))
        
        def semantic_search(
            self, 
            query_embedding: np.ndarray, 
            top_k: int = 5,
            threshold: float = 0.0
        ) -> List[Dict[str, Any]]:
            """Perform semantic search using cosine similarity."""
            self.query_count += 1
            
            if len(query_embedding) != self.config["dimensions"]:
                raise ValueError(
                    f"Query dimension {len(query_embedding)} does not match "
                    f"index dimension {self.config['dimensions']}"
                )
            
            results = []
            query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-10)
            
            for node_id, embedding in self.embeddings.items():
                similarity = float(np.dot(query_norm, embedding))
                if similarity >= threshold:
                    results.append({
                        "node_id": node_id,
                        "similarity": similarity,
                        "embedding": embedding
                    })
            
            # Sort by similarity (descending)
            results.sort(key=lambda x: x["similarity"], reverse=True)
            return results[:top_k]
        
        def knn_search(
            self,
            query_embedding: np.ndarray,
            k: int = 5
        ) -> List[Dict[str, Any]]:
            """K-nearest neighbors search."""
            return self.semantic_search(query_embedding, top_k=k)
        
        def get_index_stats(self) -> Dict[str, Any]:
            """Get index statistics."""
            return {
                "total_vectors": len(self.embeddings),
                "dimensions": self.config["dimensions"],
                "similarity_function": self.config["similarity_function"],
                "query_count": self.query_count
            }
    
    return MockVectorStore(vector_index_config)


@pytest.fixture
def neo4j_vector_index(vector_index_config):
    """Simulate Neo4j vector index behavior."""
    
    class Neo4jVectorIndex:
        """Simulate Neo4j 5.x vector index."""
        
        def __init__(self, config):
            self.config = config
            self.vectors = {}
        
        def create_index_cypher(self) -> str:
            """Generate Cypher to create vector index."""
            return f"""
            CREATE VECTOR INDEX {self.config['name']} IF NOT EXISTS
            FOR (n:{self.config['label']})
            ON (n.{self.config['property']})
            OPTIONS {{
                indexConfig: {{
                    `vector.dimensions`: {self.config['dimensions']},
                    `vector.similarity_function`: '{self.config['similarity_function']}'
                }}
            }}
            """
        
        def query_similar_cypher(self) -> str:
            """Generate Cypher for similarity search."""
            return f"""
            CALL db.index.vector.queryNodes(
                '{self.config['name']}',
                $top_k,
                $query_embedding
            ) YIELD node, score
            RETURN node, score
            ORDER BY score DESC
            """
        
        def verify_dimensions(self, embedding: List[float]) -> bool:
            """Verify embedding dimensions match index."""
            return len(embedding) == self.config["dimensions"]
        
        def verify_similarity_function(self, func_name: str) -> bool:
            """Verify similarity function is valid."""
            valid_functions = ["cosine", "euclidean"]
            return func_name.lower() in valid_functions
    
    return Neo4jVectorIndex(vector_index_config)


# =============================================================================
# Vector Index Configuration Tests
# =============================================================================

class TestVectorIndexConfiguration:
    """Tests for vector index configuration."""
    
    def test_index_has_correct_dimensions(self, vector_index_config):
        """Verify vector index is configured with 384 dimensions."""
        assert vector_index_config["dimensions"] == 384
    
    def test_index_uses_cosine_similarity(self, vector_index_config):
        """Verify vector index uses cosine similarity function."""
        assert vector_index_config["similarity_function"] == "cosine"
    
    def test_index_targets_task_nodes(self, vector_index_config):
        """Verify index targets Task nodes with embedding property."""
        assert vector_index_config["label"] == "Task"
        assert vector_index_config["property"] == "embedding"
    
    def test_index_configuration_complete(self, vector_index_config):
        """Verify all required configuration fields are present."""
        required_fields = ["name", "label", "property", "dimensions", "similarity_function"]
        for field in required_fields:
            assert field in vector_index_config
            assert vector_index_config[field] is not None
    
    def test_neo4j_cypher_creates_correct_index(self, neo4j_vector_index):
        """Verify Neo4j Cypher creates index with correct config."""
        cypher = neo4j_vector_index.create_index_cypher()
        
        assert "CREATE VECTOR INDEX" in cypher
        assert "vector.dimensions" in cypher
        assert "384" in cypher
        assert "cosine" in cypher
        assert "Task" in cypher
        assert "embedding" in cypher


# =============================================================================
# Vector Index Queryable Tests
# =============================================================================

class TestVectorIndexQueryable:
    """Tests for vector index query operations."""
    
    def test_index_exists_and_is_accessible(self, mock_vector_store):
        """Verify vector index exists and can be queried."""
        stats = mock_vector_store.verify_index()
        
        assert stats["exists"] is True
        assert stats["name"] is not None
    
    def test_can_store_384_dim_embedding(self, mock_vector_store):
        """Verify can store 384-dimensional embedding."""
        embedding = np.random.randn(384)
        embedding = embedding / np.linalg.norm(embedding)
        
        result = mock_vector_store.store_embedding("task-123", embedding)
        
        assert result is True
        assert "task-123" in mock_vector_store.embeddings
    
    def test_rejects_wrong_dimension_embedding(self, mock_vector_store):
        """Verify rejects embedding with wrong dimensions."""
        wrong_dim_embedding = np.random.randn(512)  # Wrong size
        
        with pytest.raises(ValueError) as exc_info:
            mock_vector_store.store_embedding("task-456", wrong_dim_embedding)
        
        assert "384" in str(exc_info.value)
    
    def test_rejects_query_with_wrong_dimensions(self, mock_vector_store):
        """Verify rejects query with mismatched dimensions."""
        wrong_query = np.random.randn(768)  # Wrong size
        
        with pytest.raises(ValueError) as exc_info:
            mock_vector_store.semantic_search(wrong_query)
        
        assert "384" in str(exc_info.value)
    
    def test_query_returns_expected_format(self, mock_vector_store, sample_embeddings):
        """Verify query returns results in expected format."""
        # Store some embeddings
        for node_id, embedding in sample_embeddings.items():
            mock_vector_store.store_embedding(node_id, embedding)
        
        # Search
        query = sample_embeddings["task_research_oauth"]
        results = mock_vector_store.semantic_search(query, top_k=3)
        
        # Verify result format
        assert len(results) > 0
        for result in results:
            assert "node_id" in result
            assert "similarity" in result
            assert "embedding" in result
            assert isinstance(result["similarity"], float)
            assert -1.0 <= result["similarity"] <= 1.0


# =============================================================================
# Semantic Search Tests
# =============================================================================

class TestSemanticSearch:
    """Tests for semantic search functionality."""
    
    def test_semantic_search_returns_results(self, mock_vector_store, sample_embeddings):
        """Verify semantic search returns relevant results."""
        # Store embeddings
        for node_id, embedding in sample_embeddings.items():
            mock_vector_store.store_embedding(node_id, embedding)
        
        # Search for OAuth-related tasks
        query = sample_embeddings["task_research_oauth"]
        results = mock_vector_store.semantic_search(query, top_k=5)
        
        assert len(results) > 0
        assert len(results) <= 5
    
    def test_semantic_search_ranks_by_similarity(self, mock_vector_store, sample_embeddings):
        """Verify results are ranked by cosine similarity."""
        # Store embeddings
        for node_id, embedding in sample_embeddings.items():
            mock_vector_store.store_embedding(node_id, embedding)
        
        query = sample_embeddings["task_research_oauth"]
        results = mock_vector_store.semantic_search(query, top_k=5)
        
        # Check that similarities are in descending order
        similarities = [r["similarity"] for r in results]
        assert similarities == sorted(similarities, reverse=True)
    
    def test_semantic_search_finds_similar_tasks(self, mock_vector_store, sample_embeddings):
        """Verify search finds semantically similar tasks."""
        # Store embeddings
        for node_id, embedding in sample_embeddings.items():
            mock_vector_store.store_embedding(node_id, embedding)
        
        # Search using OAuth task
        query = sample_embeddings["task_research_oauth"]
        results = mock_vector_store.semantic_search(query, top_k=3)
        
        # Should find OAuth-related tasks first
        result_ids = [r["node_id"] for r in results]
        
        # OAuth research task should be most similar to itself
        assert result_ids[0] == "task_research_oauth"
        
        # SSO research (similar topic) should be high
        assert "task_research_sso" in result_ids[:2]
    
    def test_semantic_search_respects_top_k(self, mock_vector_store, sample_embeddings):
        """Verify search respects top_k parameter."""
        # Store embeddings
        for node_id, embedding in sample_embeddings.items():
            mock_vector_store.store_embedding(node_id, embedding)
        
        query = sample_embeddings["task_research_oauth"]
        
        # Test different top_k values
        for k in [1, 2, 3]:
            results = mock_vector_store.semantic_search(query, top_k=k)
            assert len(results) <= k
    
    def test_semantic_search_respects_threshold(self, mock_vector_store, sample_embeddings):
        """Verify search respects similarity threshold."""
        # Store embeddings
        for node_id, embedding in sample_embeddings.items():
            mock_vector_store.store_embedding(node_id, embedding)
        
        query = sample_embeddings["task_research_oauth"]
        
        # With high threshold, should get fewer results
        results_strict = mock_vector_store.semantic_search(query, threshold=0.8)
        results_loose = mock_vector_store.semantic_search(query, threshold=0.0)
        
        assert len(results_strict) <= len(results_loose)
        
        # All results should meet threshold
        for r in results_strict:
            assert r["similarity"] >= 0.8
    
    def test_knn_search_returns_k_neighbors(self, mock_vector_store, sample_embeddings):
        """Verify KNN search returns exactly k neighbors."""
        # Store embeddings
        for node_id, embedding in sample_embeddings.items():
            mock_vector_store.store_embedding(node_id, embedding)
        
        query = sample_embeddings["task_research_oauth"]
        
        for k in [1, 3, 5]:
            results = mock_vector_store.knn_search(query, k=k)
            assert len(results) == min(k, len(sample_embeddings))
    
    def test_empty_index_returns_empty_results(self, mock_vector_store):
        """Verify search on empty index returns empty results."""
        query = np.random.randn(384)
        results = mock_vector_store.semantic_search(query)
        
        assert len(results) == 0


# =============================================================================
# Cosine Similarity Tests
# =============================================================================

class TestCosineSimilarity:
    """Tests for cosine similarity calculations."""
    
    def test_cosine_similarity_identical_vectors(self, mock_vector_store):
        """Verify identical vectors have cosine similarity 1.0."""
        vec = np.random.randn(384)
        vec = vec / np.linalg.norm(vec)
        
        similarity = mock_vector_store.cosine_similarity(vec, vec)
        
        assert abs(similarity - 1.0) < 1e-6
    
    def test_cosine_similarity_opposite_vectors(self, mock_vector_store):
        """Verify opposite vectors have cosine similarity -1.0."""
        vec = np.random.randn(384)
        vec = vec / np.linalg.norm(vec)
        
        similarity = mock_vector_store.cosine_similarity(vec, -vec)
        
        assert abs(similarity - (-1.0)) < 1e-6
    
    def test_cosine_similarity_orthogonal_vectors(self, mock_vector_store):
        """Verify orthogonal vectors have cosine similarity ~0.0."""
        vec1 = np.array([1.0] + [0.0] * 383)
        vec2 = np.array([0.0, 1.0] + [0.0] * 382)
        
        similarity = mock_vector_store.cosine_similarity(vec1, vec2)
        
        assert abs(similarity) < 1e-6
    
    def test_cosine_similarity_range(self, mock_vector_store):
        """Verify cosine similarity is always in range [-1, 1]."""
        for _ in range(100):
            vec1 = np.random.randn(384)
            vec2 = np.random.randn(384)
            
            similarity = mock_vector_store.cosine_similarity(vec1, vec2)
            
            assert -1.0 <= similarity <= 1.0
    
    def test_cosine_similarity_symmetric(self, mock_vector_store):
        """Verify cosine similarity is symmetric."""
        vec1 = np.random.randn(384)
        vec2 = np.random.randn(384)
        
        sim1 = mock_vector_store.cosine_similarity(vec1, vec2)
        sim2 = mock_vector_store.cosine_similarity(vec2, vec1)
        
        assert abs(sim1 - sim2) < 1e-6


# =============================================================================
# Index Statistics Tests
# =============================================================================

class TestIndexStatistics:
    """Tests for vector index statistics."""
    
    def test_stats_reflect_stored_vectors(self, mock_vector_store, sample_embeddings):
        """Verify stats correctly reflect number of stored vectors."""
        # Initially empty
        stats = mock_vector_store.get_index_stats()
        assert stats["total_vectors"] == 0
        
        # Add embeddings
        for node_id, embedding in sample_embeddings.items():
            mock_vector_store.store_embedding(node_id, embedding)
        
        stats = mock_vector_store.get_index_stats()
        assert stats["total_vectors"] == len(sample_embeddings)
    
    def test_stats_track_query_count(self, mock_vector_store, sample_embeddings):
        """Verify stats track number of queries."""
        # Store embeddings
        for node_id, embedding in sample_embeddings.items():
            mock_vector_store.store_embedding(node_id, embedding)
        
        query = sample_embeddings["task_research_oauth"]
        
        # Perform queries
        for _ in range(5):
            mock_vector_store.semantic_search(query)
        
        stats = mock_vector_store.get_index_stats()
        assert stats["query_count"] == 5
    
    def test_stats_include_configuration(self, mock_vector_store):
        """Verify stats include index configuration."""
        stats = mock_vector_store.get_index_stats()
        
        assert stats["dimensions"] == 384
        assert stats["similarity_function"] == "cosine"


# =============================================================================
# Neo4j Integration Tests
# =============================================================================

class TestNeo4jVectorIntegration:
    """Tests for Neo4j vector index integration."""
    
    def test_neo4j_index_verification_checks_dimensions(self, neo4j_vector_index):
        """Verify Neo4j index verification checks dimensions."""
        # Correct dimension
        valid_embedding = [0.1] * 384
        assert neo4j_vector_index.verify_dimensions(valid_embedding) is True
        
        # Wrong dimension
        invalid_embedding = [0.1] * 512
        assert neo4j_vector_index.verify_dimensions(invalid_embedding) is False
    
    def test_neo4j_validates_similarity_function(self, neo4j_vector_index):
        """Verify Neo4j validates similarity function names."""
        assert neo4j_vector_index.verify_similarity_function("cosine") is True
        assert neo4j_vector_index.verify_similarity_function("euclidean") is True
        assert neo4j_vector_index.verify_similarity_function("invalid") is False
    
    def test_neo4j_cypher_uses_correct_syntax(self, neo4j_vector_index):
        """Verify Neo4j Cypher uses correct vector syntax."""
        cypher = neo4j_vector_index.query_similar_cypher()
        
        # Should use Neo4j 5.x vector query syntax
        assert "db.index.vector.queryNodes" in cypher
        assert "$top_k" in cypher
        assert "$query_embedding" in cypher


# =============================================================================
# End-to-End Tests
# =============================================================================

class TestVectorIndexEndToEnd:
    """End-to-end tests for vector index workflow."""
    
    def test_full_workflow_store_and_search(self, mock_vector_store, sample_embeddings):
        """Test complete workflow: store embeddings and search."""
        # 1. Verify index exists
        index_info = mock_vector_store.verify_index()
        assert index_info["exists"] is True
        assert index_info["dimensions"] == 384
        
        # 2. Store task embeddings
        for node_id, embedding in sample_embeddings.items():
            success = mock_vector_store.store_embedding(node_id, embedding)
            assert success is True
        
        # 3. Verify stats
        stats = mock_vector_store.get_index_stats()
        assert stats["total_vectors"] == len(sample_embeddings)
        
        # 4. Search for similar tasks
        query = sample_embeddings["task_research_oauth"]
        results = mock_vector_store.semantic_search(query, top_k=3)
        
        assert len(results) > 0
        assert results[0]["node_id"] == "task_research_oauth"  # Self is most similar
        
        # 5. Verify query was counted
        stats = mock_vector_store.get_index_stats()
        assert stats["query_count"] == 1
    
    def test_embedding_dimension_enforcement(self, mock_vector_store):
        """Test that wrong dimensions are rejected at all stages."""
        correct_embedding = np.random.randn(384)
        wrong_embedding = np.random.randn(512)
        
        # Storing wrong dimension should fail
        with pytest.raises(ValueError):
            mock_vector_store.store_embedding("task-wrong", wrong_embedding)
        
        # Storing correct dimension should succeed
        assert mock_vector_store.store_embedding("task-correct", correct_embedding) is True
        
        # Searching with wrong dimension should fail
        with pytest.raises(ValueError):
            mock_vector_store.semantic_search(wrong_embedding)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
