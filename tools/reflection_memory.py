"""
Agent Reflection Memory - Learning from mistakes for the OpenClaw system.

This module provides the AgentReflectionMemory class for recording agent mistakes,
storing reflections with vector embeddings for semantic similarity search, and
consolidating reflections into learnings.

Named after the reflection and learning capabilities that enable agents to improve
over time through self-analysis and pattern recognition.
"""

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from neo4j.exceptions import Neo4jError

# Configure logging
logger = logging.getLogger(__name__)


class ReflectionNotFoundError(Exception):
    """Raised when a reflection ID is not found."""
    pass


class ReflectionError(Exception):
    """Raised when a reflection operation fails."""
    pass


class AgentReflectionMemory:
    """
    Agent reflection memory for recording and learning from mistakes.

    Provides capabilities for:
    - Recording agent mistakes with full context
    - Vector embeddings for semantic similarity search
    - Consolidating reflections into MetaRules
    - Tracking reflection status and history

    Attributes:
        memory: OperationalMemory instance for persistence
        embedding_dimension: Dimension of vector embeddings (default: 384 for MiniLM)
    """

    # Valid mistake types
    VALID_MISTAKE_TYPES = ["logic", "error", "communication", "security", "other"]

    def __init__(
        self,
        memory: Any,  # OperationalMemory
        embedding_dimension: int = 384
    ):
        """
        Initialize the AgentReflectionMemory.

        Args:
            memory: OperationalMemory instance for Neo4j persistence
            embedding_dimension: Dimension of vector embeddings
        """
        self.memory = memory
        self.embedding_dimension = embedding_dimension

        # Try to load sentence-transformers for embeddings
        self._embedding_model = None
        try:
            from sentence_transformers import SentenceTransformer
            self._embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("Loaded sentence-transformers model for embeddings")
        except ImportError:
            logger.warning("sentence-transformers not available, using hash-based fallback embeddings")

        logger.info(f"AgentReflectionMemory initialized with embedding_dimension={embedding_dimension}")

    def _generate_id(self) -> str:
        """Generate a unique ID using the memory's method or fallback to uuid."""
        if hasattr(self.memory, '_generate_id'):
            return self.memory._generate_id()
        return str(uuid.uuid4())

    def _now(self) -> datetime:
        """Get current UTC datetime using the memory's method or fallback."""
        if hasattr(self.memory, '_now'):
            return self.memory._now()
        return datetime.now(timezone.utc)

    def _session(self):
        """Get Neo4j session context manager from memory."""
        if hasattr(self.memory, '_session'):
            return self.memory._session()
        # Fallback - return a no-op context manager
        from contextlib import nullcontext
        return nullcontext(None)

    def _generate_embedding(self, text: str) -> List[float]:
        """
        Generate vector embedding for text.

        Uses sentence-transformers if available, otherwise falls back to
        a simple hash-based embedding for deterministic results.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector
        """
        if self._embedding_model is not None:
            try:
                embedding = self._embedding_model.encode(text).tolist()
                return embedding
            except Exception as e:
                logger.warning(f"Embedding model failed, using fallback: {e}")

        # Fallback: hash-based embedding (deterministic but not semantic)
        # Use MD5 hash to generate fixed-size vector
        hash_obj = hashlib.md5(text.encode())
        hash_hex = hash_obj.hexdigest()

        # Create embedding from hash (repeat pattern to reach desired dimension)
        embedding = []
        while len(embedding) < self.embedding_dimension:
            for i in range(0, len(hash_hex), 2):
                if len(embedding) >= self.embedding_dimension:
                    break
                # Convert hex pair to float between -1 and 1
                val = int(hash_hex[i:i+2], 16) / 127.5 - 1.0
                embedding.append(val)

        return embedding[:self.embedding_dimension]

    def record_mistake(
        self,
        agent: str,
        mistake_type: str,
        context: str,
        expected_behavior: str,
        actual_behavior: str,
        root_cause: str,
        lesson: str
    ) -> str:
        """
        Record a mistake reflection.

        Args:
            agent: Agent who made the mistake
            mistake_type: Type of mistake (logic/error/communication/security/other)
            context: What was happening when the mistake occurred
            expected_behavior: What should have happened
            actual_behavior: What actually happened
            root_cause: Analysis of why the mistake occurred
            lesson: What was learned from this mistake

        Returns:
            Reflection ID string

        Raises:
            ValueError: If mistake_type is invalid
            ReflectionError: If recording fails
        """
        if mistake_type not in self.VALID_MISTAKE_TYPES:
            raise ValueError(
                f"Invalid mistake_type '{mistake_type}'. "
                f"Must be one of: {self.VALID_MISTAKE_TYPES}"
            )

        reflection_id = self._generate_id()
        created_at = self._now()

        # Generate embedding for semantic search
        # Combine key fields for embedding
        embedding_text = f"{context} {expected_behavior} {actual_behavior} {root_cause} {lesson}"
        embedding = self._generate_embedding(embedding_text)

        cypher = """
        CREATE (r:Reflection {
            id: $reflection_id,
            agent: $agent,
            mistake_type: $mistake_type,
            context: $context,
            expected_behavior: $expected_behavior,
            actual_behavior: $actual_behavior,
            root_cause: $root_cause,
            lesson: $lesson,
            embedding: $embedding,
            consolidated: false,
            created_at: $created_at
        })
        RETURN r.id as reflection_id
        """

        with self._session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Reflection recording simulated for {agent}")
                return reflection_id

            try:
                result = session.run(
                    cypher,
                    reflection_id=reflection_id,
                    agent=agent,
                    mistake_type=mistake_type,
                    context=context,
                    expected_behavior=expected_behavior,
                    actual_behavior=actual_behavior,
                    root_cause=root_cause,
                    lesson=lesson,
                    embedding=embedding,
                    created_at=created_at
                )
                record = result.single()
                if record:
                    logger.info(f"Reflection recorded: {reflection_id} for agent {agent}")
                    return record["reflection_id"]
                else:
                    raise ReflectionError("Reflection recording failed: no record returned")
            except Neo4jError as e:
                logger.error(f"Failed to record reflection: {e}")
                raise ReflectionError(f"Failed to record reflection: {e}")

    def get_reflection(self, reflection_id: str) -> Optional[Dict]:
        """
        Get a reflection by ID.

        Args:
            reflection_id: Reflection ID to retrieve

        Returns:
            Reflection dict if found, None otherwise
        """
        cypher = """
        MATCH (r:Reflection {id: $reflection_id})
        RETURN r
        """

        with self._session() as session:
            if session is None:
                return None

            try:
                result = session.run(cypher, reflection_id=reflection_id)
                record = result.single()
                if record:
                    reflection = dict(record["r"])
                    # Remove embedding from result (too large, not useful for display)
                    reflection.pop("embedding", None)
                    return reflection
                return None
            except Neo4jError as e:
                logger.error(f"Failed to get reflection: {e}")
                return None

    def list_reflections(
        self,
        agent: Optional[str] = None,
        consolidated: Optional[bool] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        List reflections with optional filters.

        Args:
            agent: Filter by agent name
            consolidated: Filter by consolidation status
            limit: Maximum number of reflections to return

        Returns:
            List of reflection dicts
        """
        conditions = []
        params = {"limit": limit}

        if agent is not None:
            conditions.append("r.agent = $agent")
            params["agent"] = agent

        if consolidated is not None:
            conditions.append("r.consolidated = $consolidated")
            params["consolidated"] = consolidated

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        cypher = f"""
        MATCH (r:Reflection)
        {where_clause}
        RETURN r
        ORDER BY r.created_at DESC
        LIMIT $limit
        """

        with self._session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher, **params)
                reflections = []
                for record in result:
                    reflection = dict(record["r"])
                    # Remove embedding from result
                    reflection.pop("embedding", None)
                    reflections.append(reflection)
                return reflections
            except Neo4jError as e:
                logger.error(f"Failed to list reflections: {e}")
                return []

    def search_similar_reflections(
        self,
        query_text: str,
        agent: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """
        Search for semantically similar reflections.

        Uses vector similarity to find reflections with similar meaning.

        Args:
            query_text: Text to search for
            agent: Optional agent filter
            limit: Maximum number of results

        Returns:
            List of reflection dicts with similarity scores
        """
        query_embedding = self._generate_embedding(query_text)

        # Build query with optional agent filter
        agent_filter = "AND r.agent = $agent" if agent else ""
        params = {
            "query_embedding": query_embedding,
            "limit": limit
        }
        if agent:
            params["agent"] = agent

        # Use cosine similarity for vector comparison
        # Neo4j doesn't have native vector similarity, so we use a workaround
        # by comparing embeddings manually or using a simpler approach
        cypher = f"""
        MATCH (r:Reflection)
        WHERE r.consolidated = false {agent_filter}
        WITH r, r.embedding as embedding
        WHERE embedding IS NOT NULL
        WITH r, embedding,
             reduce(dot = 0.0, i in range(0, size(embedding)-1) |
                 dot + embedding[i] * $query_embedding[i]
             ) / (
                 sqrt(reduce(sum = 0.0, x in embedding | sum + x^2)) *
                 sqrt(reduce(sum = 0.0, x in $query_embedding | sum + x^2))
             ) as similarity
        RETURN r, similarity
        ORDER BY similarity DESC
        LIMIT $limit
        """

        with self._session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher, **params)
                reflections = []
                for record in result:
                    reflection = dict(record["r"])
                    reflection.pop("embedding", None)
                    reflection["similarity"] = record["similarity"]
                    reflections.append(reflection)
                return reflections
            except Neo4jError as e:
                logger.error(f"Failed to search similar reflections: {e}")
                # Fallback: return recent reflections without similarity
                return self.list_reflections(agent=agent, limit=limit)

    def consolidate_reflections(
        self,
        agent: Optional[str] = None,
        reflection_ids: Optional[List[str]] = None
    ) -> Dict:
        """
        Consolidate reflections into a summary for MetaRule generation.

        Marks reflections as consolidated and returns a summary for the
        MetaLearningEngine to process.

        Args:
            agent: Optional agent filter for consolidation
            reflection_ids: Optional specific reflection IDs to consolidate

        Returns:
            Dict with consolidation summary
        """
        # Get reflections to consolidate
        if reflection_ids:
            reflections = []
            for rid in reflection_ids:
                ref = self.get_reflection(rid)
                if ref and not ref.get("consolidated", False):
                    reflections.append(ref)
        else:
            reflections = self.list_reflections(agent=agent, consolidated=False, limit=100)

        if not reflections:
            return {
                "consolidated": False,
                "reason": "No unconsolidated reflections found",
                "reflections_processed": 0,
                "reflection_ids": []
            }

        # Group reflections by mistake type
        by_type: Dict[str, List[Dict]] = {}
        for reflection in reflections:
            mtype = reflection.get("mistake_type", "other")
            if mtype not in by_type:
                by_type[mtype] = []
            by_type[mtype].append(reflection)

        # Mark reflections as consolidated
        consolidated_ids = [r["id"] for r in reflections]
        self._mark_reflections_consolidated(consolidated_ids)

        # Create summary for MetaLearningEngine
        summary = {
            "consolidated": True,
            "reflections_processed": len(reflections),
            "reflection_ids": consolidated_ids,
            "by_mistake_type": {
                mtype: len(items) for mtype, items in by_type.items()
            },
            "agents": list(set(r.get("agent", "unknown") for r in reflections)),
            "common_themes": self._extract_common_themes(reflections)
        }

        logger.info(
            f"Consolidated {len(reflections)} reflections for MetaRule generation: "
            f"types={summary['by_mistake_type']}"
        )

        return summary

    def _mark_reflections_consolidated(self, reflection_ids: List[str]) -> None:
        """
        Mark reflections as consolidated.

        Args:
            reflection_ids: List of reflection IDs to mark
        """
        cypher = """
        MATCH (r:Reflection)
        WHERE r.id IN $reflection_ids
        SET r.consolidated = true,
            r.consolidated_at = $consolidated_at
        """

        with self._session() as session:
            if session is None:
                return

            try:
                session.run(
                    cypher,
                    reflection_ids=reflection_ids,
                    consolidated_at=self._now()
                )
                logger.debug(f"Marked {len(reflection_ids)} reflections as consolidated")
            except Neo4jError as e:
                logger.error(f"Failed to mark reflections as consolidated: {e}")

    def _extract_common_themes(self, reflections: List[Dict]) -> List[str]:
        """
        Extract common themes from a list of reflections.

        Args:
            reflections: List of reflection dicts

        Returns:
            List of common theme strings
        """
        # Combine all text fields for analysis
        all_text = ""
        for reflection in reflections:
            all_text += " " + reflection.get("context", "")
            all_text += " " + reflection.get("root_cause", "")
            all_text += " " + reflection.get("lesson", "")

        # Simple keyword extraction (words that appear multiple times)
        words = all_text.lower().split()
        word_counts: Dict[str, int] = {}

        for word in words:
            # Clean word
            clean = ''.join(c for c in word if c.isalnum())
            if len(clean) > 4:  # Only consider words longer than 4 chars
                word_counts[clean] = word_counts.get(clean, 0) + 1

        # Return words that appear more than once, sorted by frequency
        themes = [
            word for word, count in sorted(
                word_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )
            if count > 1
        ][:10]  # Top 10 themes

        return themes

    def count_reflections(
        self,
        agent: Optional[str] = None,
        consolidated: Optional[bool] = None
    ) -> int:
        """
        Count reflections with optional filters.

        Args:
            agent: Filter by agent name
            consolidated: Filter by consolidation status

        Returns:
            Number of matching reflections
        """
        conditions = []
        params = {}

        if agent is not None:
            conditions.append("r.agent = $agent")
            params["agent"] = agent

        if consolidated is not None:
            conditions.append("r.consolidated = $consolidated")
            params["consolidated"] = consolidated

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        cypher = f"""
        MATCH (r:Reflection)
        {where_clause}
        RETURN count(r) as count
        """

        with self._session() as session:
            if session is None:
                return 0

            try:
                result = session.run(cypher, **params)
                record = result.single()
                return record["count"] if record else 0
            except Neo4jError as e:
                logger.error(f"Failed to count reflections: {e}")
                return 0

    def create_indexes(self) -> List[str]:
        """
        Create recommended indexes for reflection tracking.

        Returns:
            List of created index names
        """
        indexes = [
            ("CREATE INDEX reflection_id_idx IF NOT EXISTS FOR (r:Reflection) ON (r.id)", "reflection_id_idx"),
            ("CREATE INDEX reflection_agent_idx IF NOT EXISTS FOR (r:Reflection) ON (r.agent)", "reflection_agent_idx"),
            ("CREATE INDEX reflection_type_idx IF NOT EXISTS FOR (r:Reflection) ON (r.mistake_type)", "reflection_type_idx"),
            ("CREATE INDEX reflection_consolidated_idx IF NOT EXISTS FOR (r:Reflection) ON (r.consolidated)", "reflection_consolidated_idx"),
            ("CREATE INDEX reflection_created_idx IF NOT EXISTS FOR (r:Reflection) ON (r.created_at)", "reflection_created_idx"),
        ]

        created = []

        with self._session() as session:
            if session is None:
                logger.warning("Cannot create indexes: Neo4j unavailable")
                return created

            for cypher, name in indexes:
                try:
                    session.run(cypher)
                    created.append(name)
                    logger.info(f"Created index: {name}")
                except Neo4jError as e:
                    if "already exists" not in str(e).lower():
                        logger.error(f"Failed to create index {name}: {e}")

        return created


# =============================================================================
# Convenience Functions
# =============================================================================

def create_reflection_memory(
    memory: Any,
    embedding_dimension: int = 384
) -> AgentReflectionMemory:
    """
    Create an AgentReflectionMemory instance.

    Args:
        memory: OperationalMemory instance
        embedding_dimension: Dimension of vector embeddings

    Returns:
        AgentReflectionMemory instance
    """
    return AgentReflectionMemory(
        memory=memory,
        embedding_dimension=embedding_dimension
    )


def record_agent_mistake(
    reflection_memory: AgentReflectionMemory,
    agent: str,
    mistake_type: str,
    context: str,
    expected_behavior: str,
    actual_behavior: str,
    root_cause: str,
    lesson: str
) -> str:
    """
    Record an agent mistake using the reflection memory.

    Args:
        reflection_memory: AgentReflectionMemory instance
        agent: Agent who made the mistake
        mistake_type: Type of mistake
        context: What was happening
        expected_behavior: What should have happened
        actual_behavior: What actually happened
        root_cause: Why it happened
        lesson: What was learned

    Returns:
        Reflection ID
    """
    return reflection_memory.record_mistake(
        agent=agent,
        mistake_type=mistake_type,
        context=context,
        expected_behavior=expected_behavior,
        actual_behavior=actual_behavior,
        root_cause=root_cause,
        lesson=lesson
    )


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Configure logging for example
    logging.basicConfig(level=logging.INFO)

    # Example usage (requires OperationalMemory)
    print("AgentReflectionMemory - Example Usage")
    print("=" * 50)

    print("""
    from openclaw_memory import OperationalMemory
    from tools.reflection_memory import AgentReflectionMemory

    # Initialize
    with OperationalMemory(
        uri="bolt://localhost:7687",
        username="neo4j",
        password="password"
    ) as memory:

        # Create reflection memory
        reflection_memory = AgentReflectionMemory(memory=memory)

        # Create indexes
        reflection_memory.create_indexes()

        # Record a mistake
        reflection_id = reflection_memory.record_mistake(
            agent="developer",
            mistake_type="logic",
            context="Implementing user authentication",
            expected_behavior="Password should be hashed before storage",
            actual_behavior="Password stored in plaintext",
            root_cause="Forgot to call hash_password() function",
            lesson="Always use hash_password() before storing passwords"
        )

        # Search for similar reflections
        similar = reflection_memory.search_similar_reflections(
            query_text="password security issue",
            limit=5
        )

        # Consolidate reflections
        summary = reflection_memory.consolidate_reflections(agent="developer")

        # List unconsolidated reflections
        unconsolidated = reflection_memory.list_reflections(
            consolidated=False,
            limit=10
        )
    """)
