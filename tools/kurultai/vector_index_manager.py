"""
Vector Index Manager for Kurultai System

Manages Neo4j vector indexes for semantic search across:
- Belief nodes
- MemoryEntry nodes
- Research nodes
- Task nodes

Author: Temüjin (Developer Agent)
"""

import logging
import uuid
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass
from datetime import datetime, timezone
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from openclaw_memory import OperationalMemory, with_retry, CircuitBreaker
    HAS_OPENCLAW = True
except ImportError:
    HAS_OPENCLAW = False

logger = logging.getLogger(__name__)


@dataclass
class VectorIndexConfig:
    """Configuration for a vector index."""
    name: str
    label: str
    property: str
    dimensions: int = 384
    similarity_function: str = "cosine"


@dataclass
class SearchResult:
    """Result from a vector similarity search."""
    node_id: str
    node_type: str
    score: float
    properties: Dict[str, Any]


class VectorIndexManager:
    """
    Manager for Neo4j vector indexes.
    
    Provides methods to:
    - Create vector indexes
    - Query similar vectors
    - Delete indexes
    - Verify index configuration
    """
    
    # Standard index configurations
    INDEX_CONFIGS = {
        "belief": VectorIndexConfig(
            name="belief_embedding_index",
            label="Belief",
            property="belief_embedding",
            dimensions=384,
            similarity_function="cosine"
        ),
        "memory": VectorIndexConfig(
            name="memory_entry_embedding_index",
            label="MemoryEntry",
            property="memory_entry_embedding",
            dimensions=384,
            similarity_function="cosine"
        ),
        "research": VectorIndexConfig(
            name="research_embedding_index",
            label="Research",
            property="research_embedding",
            dimensions=384,
            similarity_function="cosine"
        ),
        "task": VectorIndexConfig(
            name="task_embedding_index",
            label="Task",
            property="embedding",
            dimensions=384,
            similarity_function="cosine"
        )
    }
    
    def __init__(
        self,
        memory: Optional['OperationalMemory'] = None,
        uri: Optional[str] = None,
        username: str = "neo4j",
        password: Optional[str] = None
    ):
        """
        Initialize the VectorIndexManager.
        
        Args:
            memory: Existing OperationalMemory instance
            uri: Neo4j URI (if memory not provided)
            username: Neo4j username (if memory not provided)
            password: Neo4j password (if memory not provided)
        """
        if memory:
            self.memory = memory
            self._owns_memory = False
        elif HAS_OPENCLAW and uri and password:
            self.memory = OperationalMemory(uri=uri, username=username, password=password)
            self._owns_memory = True
        else:
            self.memory = None
            self._owns_memory = False
            logger.warning("VectorIndexManager initialized without Neo4j connection")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._owns_memory and self.memory:
            self.memory.close()
        return False
    
    def create_index(
        self,
        index_name: str,
        label: str,
        property_name: str,
        dimensions: int = 384,
        similarity_function: str = "cosine"
    ) -> bool:
        """
        Create a vector index.
        
        Args:
            index_name: Name of the index
            label: Node label to index
            property_name: Property containing the vector
            dimensions: Vector dimensions (default: 384)
            similarity_function: Similarity function (default: cosine)
        
        Returns:
            True if successful
        """
        if not self.memory:
            logger.error("No Neo4j connection available")
            return False
        
        cypher = f"""
        CREATE VECTOR INDEX {index_name} IF NOT EXISTS
        FOR (n:{label})
        ON (n.{property_name})
        OPTIONS {{
            indexConfig: {{
                `vector.dimensions`: {dimensions},
                `vector.similarity_function`: '{similarity_function}'
            }}
        }}
        """
        
        try:
            with self.memory._session() as session:
                if session:
                    session.run(cypher)
                    logger.info(f"Created vector index: {index_name}")
                    return True
        except Exception as e:
            logger.error(f"Failed to create vector index {index_name}: {e}")
            return False
        
        return False
    
    def create_all_indexes(self) -> Dict[str, bool]:
        """
        Create all standard vector indexes.
        
        Returns:
            Dictionary mapping index names to success status
        """
        results = {}
        
        for name, config in self.INDEX_CONFIGS.items():
            success = self.create_index(
                index_name=config.name,
                label=config.label,
                property_name=config.property,
                dimensions=config.dimensions,
                similarity_function=config.similarity_function
            )
            results[config.name] = success
        
        return results
    
    def query_similar(
        self,
        index_name: str,
        query_vector: List[float],
        top_k: int = 5,
        min_score: Optional[float] = None
    ) -> List[SearchResult]:
        """
        Query for similar vectors.
        
        Args:
            index_name: Name of the vector index
            query_vector: Query embedding vector
            top_k: Number of results to return
            min_score: Minimum similarity score (optional)
        
        Returns:
            List of SearchResult objects
        """
        if not self.memory:
            logger.error("No Neo4j connection available")
            return []
        
        if len(query_vector) != 384:
            logger.error(f"Query vector has wrong dimensions: {len(query_vector)} (expected 384)")
            return []
        
        cypher = """
        CALL db.index.vector.queryNodes($index_name, $top_k, $query_vector)
        YIELD node, score
        RETURN node, score
        ORDER BY score DESC
        """
        
        results = []
        
        try:
            with self.memory._session() as session:
                if session:
                    query_result = session.run(
                        cypher,
                        index_name=index_name,
                        top_k=top_k,
                        query_vector=query_vector
                    )
                    
                    for record in query_result:
                        node = record["node"]
                        score = record["score"]
                        
                        if min_score is not None and score < min_score:
                            continue
                        
                        # Extract node properties
                        properties = dict(node)
                        node_id = properties.get("id", str(uuid.uuid4()))
                        
                        # Determine node type from labels
                        node_type = list(node.labels)[0] if node.labels else "Unknown"
                        
                        results.append(SearchResult(
                            node_id=node_id,
                            node_type=node_type,
                            score=score,
                            properties=properties
                        ))
        except Exception as e:
            logger.error(f"Failed to query vector index {index_name}: {e}")
        
        return results
    
    def query_beliefs(
        self,
        query_vector: List[float],
        top_k: int = 5,
        min_score: Optional[float] = None
    ) -> List[SearchResult]:
        """Query for similar beliefs."""
        return self.query_similar(
            index_name="belief_embedding_index",
            query_vector=query_vector,
            top_k=top_k,
            min_score=min_score
        )
    
    def query_memories(
        self,
        query_vector: List[float],
        top_k: int = 5,
        min_score: Optional[float] = None
    ) -> List[SearchResult]:
        """Query for similar memories."""
        return self.query_similar(
            index_name="memory_entry_embedding_index",
            query_vector=query_vector,
            top_k=top_k,
            min_score=min_score
        )
    
    def query_research(
        self,
        query_vector: List[float],
        top_k: int = 5,
        min_score: Optional[float] = None
    ) -> List[SearchResult]:
        """Query for similar research."""
        return self.query_similar(
            index_name="research_embedding_index",
            query_vector=query_vector,
            top_k=top_k,
            min_score=min_score
        )
    
    def delete_index(self, index_name: str) -> bool:
        """
        Delete a vector index.
        
        Args:
            index_name: Name of the index to delete
        
        Returns:
            True if successful
        """
        if not self.memory:
            logger.error("No Neo4j connection available")
            return False
        
        cypher = f"DROP INDEX {index_name} IF EXISTS"
        
        try:
            with self.memory._session() as session:
                if session:
                    session.run(cypher)
                    logger.info(f"Deleted vector index: {index_name}")
                    return True
        except Exception as e:
            logger.error(f"Failed to delete vector index {index_name}: {e}")
            return False
        
        return False
    
    def delete_all_indexes(self) -> Dict[str, bool]:
        """
        Delete all standard vector indexes.
        
        Returns:
            Dictionary mapping index names to success status
        """
        results = {}
        
        for name, config in self.INDEX_CONFIGS.items():
            success = self.delete_index(config.name)
            results[config.name] = success
        
        return results
    
    def list_indexes(self) -> List[Dict[str, Any]]:
        """
        List all vector indexes.
        
        Returns:
            List of index information dictionaries
        """
        if not self.memory:
            logger.error("No Neo4j connection available")
            return []
        
        cypher = """
        SHOW INDEXES
        YIELD name, type, entityType, labelsOrTypes, properties, options
        WHERE type = 'VECTOR'
        RETURN name, type, entityType, labelsOrTypes, properties,
               options.indexConfig.`vector.dimensions` as dimensions,
               options.indexConfig.`vector.similarity_function` as similarity_function
        """
        
        results = []
        
        try:
            with self.memory._session() as session:
                if session:
                    query_result = session.run(cypher)
                    for record in query_result:
                        results.append(dict(record))
        except Exception as e:
            logger.error(f"Failed to list vector indexes: {e}")
        
        return results
    
    def verify_index(self, index_name: str) -> Dict[str, Any]:
        """
        Verify a vector index exists and has correct configuration.
        
        Args:
            index_name: Name of the index to verify
        
        Returns:
            Verification result dictionary
        """
        indexes = self.list_indexes()
        
        for idx in indexes:
            if idx["name"] == index_name:
                return {
                    "exists": True,
                    "name": idx["name"],
                    "type": idx["type"],
                    "entity_type": idx["entityType"],
                    "labels": idx["labelsOrTypes"],
                    "properties": idx["properties"],
                    "dimensions": idx["dimensions"],
                    "similarity_function": idx["similarity_function"]
                }
        
        return {
            "exists": False,
            "name": index_name
        }
    
    def verify_all_indexes(self) -> Dict[str, Dict[str, Any]]:
        """
        Verify all standard vector indexes.
        
        Returns:
            Dictionary mapping index names to verification results
        """
        results = {}
        
        for name, config in self.INDEX_CONFIGS.items():
            results[name] = self.verify_index(config.name)
        
        return results
    
    def get_index_stats(self, index_name: str) -> Dict[str, Any]:
        """
        Get statistics for a vector index.
        
        Args:
            index_name: Name of the index
        
        Returns:
            Statistics dictionary
        """
        if not self.memory:
            logger.error("No Neo4j connection available")
            return {}
        
        # Get index info
        info = self.verify_index(index_name)
        
        if not info["exists"]:
            return {"exists": False, "name": index_name}
        
        # Count nodes with embeddings
        label = info.get("labels", [None])[0] if info.get("labels") else None
        property_name = info.get("properties", [None])[0] if info.get("properties") else None
        
        if label and property_name:
            try:
                cypher = f"""
                MATCH (n:{label})
                WHERE n.{property_name} IS NOT NULL
                RETURN count(n) as count
                """
                
                with self.memory._session() as session:
                    if session:
                        result = session.run(cypher)
                        record = result.single()
                        count = record["count"] if record else 0
                        
                        return {
                            "exists": True,
                            "name": index_name,
                            "label": label,
                            "property": property_name,
                            "dimensions": info.get("dimensions"),
                            "similarity_function": info.get("similarity_function"),
                            "indexed_nodes": count
                        }
            except Exception as e:
                logger.error(f"Failed to get index stats: {e}")
        
        return {
            "exists": True,
            "name": index_name,
            **info
        }
    
    def wait_for_indexes(self, timeout_seconds: int = 30) -> bool:
        """
        Wait for all indexes to be online.
        
        Args:
            timeout_seconds: Maximum time to wait
        
        Returns:
            True if all indexes are online
        """
        if not self.memory:
            logger.error("No Neo4j connection available")
            return False
        
        try:
            cypher = "CALL db.awaitIndexes($timeout)"
            
            with self.memory._session() as session:
                if session:
                    session.run(cypher, timeout=timeout_seconds)
                    logger.info("All indexes are online")
                    return True
        except Exception as e:
            logger.error(f"Failed to wait for indexes: {e}")
            return False
        
        return False


# =============================================================================
# Convenience functions
# =============================================================================

def create_vector_indexes(
    uri: str,
    username: str,
    password: str
) -> Dict[str, bool]:
    """
    Create all standard vector indexes.
    
    Args:
        uri: Neo4j URI
        username: Neo4j username
        password: Neo4j password
    
    Returns:
        Dictionary mapping index names to success status
    """
    with VectorIndexManager(uri=uri, username=username, password=password) as manager:
        return manager.create_all_indexes()


def verify_vector_indexes(
    uri: str,
    username: str,
    password: str
) -> Dict[str, Dict[str, Any]]:
    """
    Verify all standard vector indexes.
    
    Args:
        uri: Neo4j URI
        username: Neo4j username
        password: Neo4j password
    
    Returns:
        Dictionary mapping index names to verification results
    """
    with VectorIndexManager(uri=uri, username=username, password=password) as manager:
        return manager.verify_all_indexes()


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
        sys.exit(1)
    
    # Create all indexes
    print("Creating vector indexes...")
    results = create_vector_indexes(uri=uri, username="neo4j", password=password)
    
    for index_name, success in results.items():
        status = "✓" if success else "✗"
        print(f"  {status} {index_name}")
    
    # Verify indexes
    print("\nVerifying vector indexes...")
    verifications = verify_vector_indexes(uri=uri, username="neo4j", password=password)
    
    for index_name, info in verifications.items():
        if info["exists"]:
            print(f"  ✓ {index_name}: {info.get('dimensions')}d, {info.get('similarity_function')}")
        else:
            print(f"  ✗ {index_name}: NOT FOUND")
