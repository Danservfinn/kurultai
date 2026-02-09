"""
Semantic Search for Kurultai System

Provides semantic search capabilities using vector embeddings.
Integrates with sentence-transformers for embedding generation.

Author: Temüjin (Developer Agent)
"""

import logging
import uuid
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass
from datetime import datetime, timezone
import sys
import os
import math

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tools.kurultai.vector_index_manager import VectorIndexManager, SearchResult

logger = logging.getLogger(__name__)

# Try to import sentence-transformers for embedding generation
try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False
    logger.warning("sentence-transformers not available. Using fallback embeddings.")


@dataclass
class SemanticSearchResult:
    """Enhanced semantic search result."""
    node_id: str
    node_type: str
    score: float
    text_content: str
    metadata: Dict[str, Any]
    properties: Dict[str, Any]


class EmbeddingGenerator:
    """
    Generates vector embeddings for text content.
    
    Uses sentence-transformers if available, otherwise falls back to
    a simple hashing-based approach for testing.
    """
    
    DEFAULT_MODEL = "all-MiniLM-L6-v2"
    EMBEDDING_DIM = 384
    
    def __init__(self, model_name: Optional[str] = None):
        """
        Initialize the embedding generator.
        
        Args:
            model_name: Name of the sentence-transformers model to use
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self.model = None
        self._fallback_cache: Dict[str, List[float]] = {}
        
        if HAS_SENTENCE_TRANSFORMERS:
            try:
                self.model = SentenceTransformer(self.model_name)
                logger.info(f"Loaded embedding model: {self.model_name}")
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                self.model = None
    
    def generate(self, text: str) -> List[float]:
        """
        Generate embedding for text.
        
        Args:
            text: Text to embed
        
        Returns:
            Embedding vector as list of floats
        """
        if not text:
            # Return zero vector for empty text
            return [0.0] * self.EMBEDDING_DIM
        
        if self.model:
            try:
                import numpy as np
                embedding = self.model.encode(text, convert_to_numpy=True)
                return embedding.tolist()
            except Exception as e:
                logger.error(f"Failed to generate embedding: {e}")
                return self._fallback_embedding(text)
        else:
            return self._fallback_embedding(text)
    
    def generate_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
        
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        if self.model:
            try:
                import numpy as np
                embeddings = self.model.encode(texts, convert_to_numpy=True)
                return [emb.tolist() for emb in embeddings]
            except Exception as e:
                logger.error(f"Failed to generate batch embeddings: {e}")
                return [self._fallback_embedding(t) for t in texts]
        else:
            return [self._fallback_embedding(t) for t in texts]
    
    def _fallback_embedding(self, text: str) -> List[float]:
        """
        Generate a deterministic fallback embedding using hashing.
        
        This is NOT for production use - only for testing when
        sentence-transformers is not available.
        """
        # Use cached result if available
        if text in self._fallback_cache:
            return self._fallback_cache[text]
        
        # Generate deterministic embedding using hash
        import hashlib
        
        # Create multiple hash values for different dimensions
        embedding = []
        for i in range(self.EMBEDDING_DIM):
            hash_input = f"{text}:{i}".encode('utf-8')
            hash_val = int(hashlib.md5(hash_input).hexdigest(), 16)
            # Normalize to [-1, 1] range
            normalized = (hash_val % 2000 - 1000) / 1000.0
            embedding.append(normalized)
        
        # Normalize to unit vector (without numpy)
        norm = math.sqrt(sum(x * x for x in embedding))
        if norm > 0:
            embedding = [x / norm for x in embedding]
        
        self._fallback_cache[text] = embedding
        return embedding


class SemanticSearch:
    """
    Semantic search using vector embeddings.
    
    Provides search across:
    - Beliefs
    - Memory entries
    - Research content
    """
    
    def __init__(
        self,
        vector_manager: Optional[VectorIndexManager] = None,
        embedding_generator: Optional[EmbeddingGenerator] = None,
        memory=None,
        uri: Optional[str] = None,
        username: str = "neo4j",
        password: Optional[str] = None
    ):
        """
        Initialize SemanticSearch.
        
        Args:
            vector_manager: Existing VectorIndexManager
            embedding_generator: Existing EmbeddingGenerator
            memory: OperationalMemory instance
            uri: Neo4j URI
            username: Neo4j username
            password: Neo4j password
        """
        if vector_manager:
            self.vector_manager = vector_manager
        elif memory:
            self.vector_manager = VectorIndexManager(memory=memory)
        elif uri and password:
            self.vector_manager = VectorIndexManager(uri=uri, username=username, password=password)
        else:
            self.vector_manager = None
            logger.warning("SemanticSearch initialized without vector manager")
        
        self.embedding_generator = embedding_generator or EmbeddingGenerator()
    
    def search_beliefs(
        self,
        query: str,
        top_k: int = 5,
        min_score: Optional[float] = 0.5
    ) -> List[SemanticSearchResult]:
        """
        Search for beliefs semantically similar to query.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            min_score: Minimum similarity score
        
        Returns:
            List of semantic search results
        """
        query_embedding = self.embedding_generator.generate(query)
        
        if not self.vector_manager:
            logger.error("No vector manager available")
            return []
        
        results = self.vector_manager.query_beliefs(
            query_vector=query_embedding,
            top_k=top_k,
            min_score=min_score
        )
        
        return self._enhance_results(results, "belief")
    
    def search_memories(
        self,
        query: str,
        top_k: int = 5,
        min_score: Optional[float] = 0.5
    ) -> List[SemanticSearchResult]:
        """
        Search for memories semantically similar to query.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            min_score: Minimum similarity score
        
        Returns:
            List of semantic search results
        """
        query_embedding = self.embedding_generator.generate(query)
        
        if not self.vector_manager:
            logger.error("No vector manager available")
            return []
        
        results = self.vector_manager.query_memories(
            query_vector=query_embedding,
            top_k=top_k,
            min_score=min_score
        )
        
        return self._enhance_results(results, "memory")
    
    def search_research(
        self,
        query: str,
        top_k: int = 5,
        min_score: Optional[float] = 0.5
    ) -> List[SemanticSearchResult]:
        """
        Search for research semantically similar to query.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            min_score: Minimum similarity score
        
        Returns:
            List of semantic search results
        """
        query_embedding = self.embedding_generator.generate(query)
        
        if not self.vector_manager:
            logger.error("No vector manager available")
            return []
        
        results = self.vector_manager.query_research(
            query_vector=query_embedding,
            top_k=top_k,
            min_score=min_score
        )
        
        return self._enhance_results(results, "research")
    
    def search_all(
        self,
        query: str,
        top_k: int = 5,
        min_score: Optional[float] = 0.5
    ) -> Dict[str, List[SemanticSearchResult]]:
        """
        Search across all content types.
        
        Args:
            query: Search query text
            top_k: Number of results per type
            min_score: Minimum similarity score
        
        Returns:
            Dictionary mapping content types to results
        """
        return {
            "beliefs": self.search_beliefs(query, top_k, min_score),
            "memories": self.search_memories(query, top_k, min_score),
            "research": self.search_research(query, top_k, min_score)
        }
    
    def search_similar_to_belief(
        self,
        belief_id: str,
        top_k: int = 5,
        min_score: Optional[float] = 0.5
    ) -> List[SemanticSearchResult]:
        """
        Find beliefs similar to a specific belief.
        
        Args:
            belief_id: ID of the reference belief
            top_k: Number of results to return
            min_score: Minimum similarity score
        
        Returns:
            List of similar beliefs
        """
        if not self.vector_manager or not self.vector_manager.memory:
            logger.error("No vector manager available")
            return []
        
        # Get the belief's embedding
        try:
            cypher = """
            MATCH (b:Belief {id: $belief_id})
            RETURN b.belief_embedding as embedding
            """
            
            with self.vector_manager.memory._session() as session:
                if session:
                    result = session.run(cypher, belief_id=belief_id)
                    record = result.single()
                    
                    if record and record["embedding"]:
                        embedding = record["embedding"]
                        results = self.vector_manager.query_beliefs(
                            query_vector=embedding,
                            top_k=top_k + 1,  # +1 to exclude self
                            min_score=min_score
                        )
                        
                        # Filter out the reference belief
                        results = [r for r in results if r.node_id != belief_id]
                        return self._enhance_results(results[:top_k], "belief")
        except Exception as e:
            logger.error(f"Failed to search similar beliefs: {e}")
        
        return []
    
    def _enhance_results(
        self,
        results: List[SearchResult],
        content_type: str
    ) -> List[SemanticSearchResult]:
        """
        Enhance raw search results with text content.
        
        Args:
            results: Raw search results
            content_type: Type of content
        
        Returns:
            Enhanced results with text content
        """
        enhanced = []
        
        for result in results:
            props = result.properties
            
            # Extract text content based on node type
            if content_type == "belief":
                text = props.get("statement", props.get("content", ""))
            elif content_type == "memory":
                text = props.get("description", props.get("content", ""))
            elif content_type == "research":
                text = props.get("findings", props.get("topic", ""))
            else:
                text = ""
            
            # Extract metadata
            metadata = {
                "created_at": props.get("created_at"),
                "agent": props.get("agent"),
                "source": props.get("source")
            }
            
            enhanced.append(SemanticSearchResult(
                node_id=result.node_id,
                node_type=result.node_type,
                score=result.score,
                text_content=text,
                metadata=metadata,
                properties=props
            ))
        
        return enhanced
    
    def get_embedding(self, text: str) -> List[float]:
        """
        Get embedding for text (convenience method).
        
        Args:
            text: Text to embed
        
        Returns:
            Embedding vector
        """
        return self.embedding_generator.generate(text)
    
    def compute_similarity(self, text1: str, text2: str) -> float:
        """
        Compute cosine similarity between two texts.
        
        Args:
            text1: First text
            text2: Second text
        
        Returns:
            Cosine similarity score [-1, 1]
        """
        emb1 = self.embedding_generator.generate(text1)
        emb2 = self.embedding_generator.generate(text2)
        
        # Compute cosine similarity without numpy
        dot_product = sum(a * b for a, b in zip(emb1, emb2))
        norm1 = sum(a * a for a in emb1) ** 0.5
        norm2 = sum(b * b for b in emb2) ** 0.5
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)


# =============================================================================
# Convenience functions
# =============================================================================

def search_semantic(
    query: str,
    content_type: str = "all",
    top_k: int = 5,
    uri: Optional[str] = None,
    password: Optional[str] = None
) -> Union[List[SemanticSearchResult], Dict[str, List[SemanticSearchResult]]]:
    """
    Perform semantic search.
    
    Args:
        query: Search query
        content_type: Type of content to search (beliefs, memories, research, all)
        top_k: Number of results
        uri: Neo4j URI
        password: Neo4j password
    
    Returns:
        Search results
    """
    import os
    
    uri = uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    password = password or os.environ.get("NEO4J_PASSWORD")
    
    if not password:
        raise ValueError("Neo4j password required")
    
    searcher = SemanticSearch(uri=uri, username="neo4j", password=password)
    
    if content_type == "all":
        return searcher.search_all(query, top_k)
    elif content_type == "beliefs":
        return searcher.search_beliefs(query, top_k)
    elif content_type == "memories":
        return searcher.search_memories(query, top_k)
    elif content_type == "research":
        return searcher.search_research(query, top_k)
    else:
        raise ValueError(f"Unknown content type: {content_type}")


# =============================================================================
# Example usage
# =============================================================================

if __name__ == "__main__":
    import os
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Get connection details from environment
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    password = os.environ.get("NEO4J_PASSWORD")
    
    if not password:
        print("Error: NEO4J_PASSWORD environment variable not set")
        print("Using fallback embedding for demonstration...")
        
        # Demo with fallback embeddings
        gen = EmbeddingGenerator()
        query = "authentication security"
        embedding = gen.generate(query)
        print(f"\nGenerated embedding for '{query}':")
        print(f"  Dimensions: {len(embedding)}")
        print(f"  First 5 values: {embedding[:5]}")
        
        # Compute norm manually
        norm = math.sqrt(sum(x * x for x in embedding))
        print(f"  Norm: {norm:.4f}")
        
        # Test similarity
        text1 = "OAuth implementation"
        text2 = "Single sign-on"
        text3 = "Database optimization"
        
        searcher = SemanticSearch()
        searcher.embedding_generator = gen
        
        sim1 = searcher.compute_similarity(text1, text2)
        sim2 = searcher.compute_similarity(text1, text3)
        
        print(f"\nSimilarity scores:")
        print(f"  '{text1}' vs '{text2}': {sim1:.4f}")
        print(f"  '{text1}' vs '{text3}': {sim2:.4f}")
        
        sys.exit(0)
    
    # Test with Neo4j connection
    print("Testing semantic search...")
    
    searcher = SemanticSearch(uri=uri, username="neo4j", password=password)
    
    # Test embedding generation
    query = "security authentication patterns"
    embedding = searcher.get_embedding(query)
    print(f"\nGenerated embedding for '{query}':")
    print(f"  Dimensions: {len(embedding)}")
    print(f"  First 5 values: {embedding[:5]}")
    norm = math.sqrt(sum(x * x for x in embedding))
    print(f"  Norm: {norm:.4f}")
    
    # Test searches
    print("\nSearching beliefs...")
    results = searcher.search_beliefs(query, top_k=3)
    for r in results:
        print(f"  [{r.score:.3f}] {r.text_content[:100]}...")
    
    print("\nSearching memories...")
    results = searcher.search_memories(query, top_k=3)
    for r in results:
        print(f"  [{r.score:.3f}] {r.text_content[:100]}...")
