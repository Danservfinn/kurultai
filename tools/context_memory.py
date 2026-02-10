"""Context Memory System - Conversation tracking and context building for Kurultai.

This module provides:
- Conversation storage and retrieval
- Topic tracking across conversations
- Preference and habit learning
- Conversation linking and relationship detection
- Semantic search for related conversations
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from contextlib import contextmanager

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class Conversation:
    """Represents a conversation with a person."""
    id: str
    person_id: str
    channel: str
    timestamp: datetime
    summary: str
    topics: List[str] = field(default_factory=list)
    content_snippet: Optional[str] = None
    message_count: int = 0
    duration_minutes: Optional[int] = None
    embedding: Optional[List[float]] = None
    related_conversations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Topic:
    """A topic that has been discussed."""
    id: str
    name: str
    normalized_name: str  # Lowercase, normalized
    first_discussed: datetime
    last_discussed: datetime
    frequency: int = 1
    persons: List[str] = field(default_factory=list)
    related_topics: List[str] = field(default_factory=list)


@dataclass
class ConversationSummary:
    """Summary of conversation history for a person."""
    person_id: str
    total_conversations: int
    total_messages: int
    recurring_topics: List[Topic]
    recent_conversations: List[Conversation]
    conversation_patterns: Dict[str, Any]
    last_interaction: Optional[datetime] = None


class ContextMemory:
    """
    Manages conversation context and memory for the Kurultai system.
    
    Features:
    - Store conversation summaries with topics
    - Track recurring topics and interests
    - Link related conversations
    - Semantic search for similar conversations
    - Build rich context for conversations
    """

    def __init__(
        self,
        neo4j_uri: str = "bolt://localhost:7687",
        neo4j_username: str = "neo4j",
        neo4j_password: Optional[str] = None,
        database: str = "neo4j",
        fallback_mode: bool = True,
        embedding_generator: Optional[Any] = None
    ):
        self.neo4j_uri = neo4j_uri
        self.neo4j_username = neo4j_username
        self.neo4j_password = neo4j_password
        self.database = database
        self.fallback_mode = fallback_mode
        self._embedding_generator = embedding_generator
        self._driver = None
        self._initialized = False

        self._import_neo4j()

    def _import_neo4j(self):
        """Lazy import Neo4j."""
        try:
            from neo4j import GraphDatabase
            from neo4j.exceptions import ServiceUnavailable
            self._GraphDatabase = GraphDatabase
            self._ServiceUnavailable = ServiceUnavailable
        except ImportError:
            logger.warning("Neo4j driver not available")
            self._GraphDatabase = None

    def initialize(self) -> bool:
        """Initialize Neo4j connection."""
        if self._GraphDatabase is None:
            logger.error("Neo4j driver not available")
            return False

        if self.neo4j_password is None:
            raise ValueError("Neo4j password is required")

        try:
            self._driver = self._GraphDatabase.driver(
                self.neo4j_uri,
                auth=(self.neo4j_username, self.neo4j_password)
            )
            self._driver.verify_connectivity()
            self._initialized = True
            logger.info("ContextMemory initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Neo4j: {e}")
            if not self.fallback_mode:
                raise
            return False

    def close(self):
        """Close Neo4j connection."""
        if self._driver:
            self._driver.close()
            self._driver = None
            self._initialized = False

    @contextmanager
    def _session(self):
        """Context manager for Neo4j sessions."""
        if not self._driver:
            yield None
            return
        session = self._driver.session(database=self.database)
        try:
            yield session
        finally:
            session.close()

    # ===================================================================
    # Conversation Operations
    # ===================================================================

    def record_conversation(
        self,
        person_id: str,
        channel: str,
        summary: str,
        topics: Optional[List[str]] = None,
        content_snippet: Optional[str] = None,
        message_count: int = 0,
        duration_minutes: Optional[int] = None,
        related_to: Optional[List[str]] = None,
        embedding: Optional[List[float]] = None,
        **metadata
    ) -> Conversation:
        """
        Record a new conversation.
        
        Args:
            person_id: Person's unique ID
            channel: Channel (signal, discord, etc.)
            summary: Conversation summary
            topics: List of topics discussed
            content_snippet: Sample of conversation content
            message_count: Number of messages
            duration_minutes: Duration of conversation
            related_to: IDs of related conversations
            embedding: Vector embedding for semantic search
            **metadata: Additional metadata
            
        Returns:
            Created Conversation object
        """
        conv_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        topics = topics or []

        # Generate embedding if not provided and generator available
        if embedding is None and self._embedding_generator:
            try:
                text_for_embedding = f"{summary} {' '.join(topics)}"
                embedding = self._embedding_generator.generate(text_for_embedding)
            except Exception as e:
                logger.warning(f"Failed to generate embedding: {e}")

        with self._session() as session:
            if session is None:
                return Conversation(
                    id=conv_id,
                    person_id=person_id,
                    channel=channel,
                    timestamp=now,
                    summary=summary,
                    topics=topics,
                    content_snippet=content_snippet,
                    message_count=message_count,
                    duration_minutes=duration_minutes,
                    embedding=embedding,
                    related_conversations=related_to or [],
                    metadata=metadata
                )

            # Create conversation node
            cypher = """
            MATCH (p:Person {id: $person_id})
            CREATE (c:Conversation {
                id: $conv_id,
                person_id: $person_id,
                channel: $channel,
                timestamp: $now,
                summary: $summary,
                topics: $topics,
                content_snippet: $content_snippet,
                message_count: $message_count,
                duration_minutes: $duration_minutes,
                embedding: $embedding,
                metadata: $metadata,
                created_at: $now
            })
            CREATE (p)-[:PARTICIPATED_IN {at: $now}]->(c)
            """

            session.run(
                cypher,
                person_id=person_id,
                conv_id=conv_id,
                channel=channel,
                now=now,
                summary=summary,
                topics=topics,
                content_snippet=content_snippet,
                message_count=message_count,
                duration_minutes=duration_minutes,
                embedding=embedding or [],
                metadata=str(metadata) if metadata else "{}"
            )

            # Link to topics
            for topic in topics:
                self._link_conversation_to_topic(session, conv_id, person_id, topic, now)

            # Link related conversations
            if related_to:
                for related_id in related_to:
                    self._link_conversations(session, conv_id, related_id, now)

            # Update person's conversation count
            session.run(
                """
                MATCH (p:Person {id: $person_id})
                SET p.total_conversations = COALESCE(p.total_conversations, 0) + 1,
                    p.last_seen = $now
                """,
                person_id=person_id,
                now=now
            )

        return Conversation(
            id=conv_id,
            person_id=person_id,
            channel=channel,
            timestamp=now,
            summary=summary,
            topics=topics,
            content_snippet=content_snippet,
            message_count=message_count,
            duration_minutes=duration_minutes,
            embedding=embedding,
            related_conversations=related_to or [],
            metadata=metadata
        )

    def _link_conversation_to_topic(
        self,
        session,
        conv_id: str,
        person_id: str,
        topic_name: str,
        timestamp: datetime
    ):
        """Link a conversation to a topic, creating if needed."""
        normalized = topic_name.lower().strip()
        topic_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"topic:{normalized}"))

        cypher = """
        MERGE (t:Topic {normalized_name: $normalized})
        ON CREATE SET
            t.id = $topic_id,
            t.name = $topic_name,
            t.first_discussed = $timestamp,
            t.frequency = 0
        ON MATCH SET
            t.frequency = COALESCE(t.frequency, 0) + 1
        SET t.last_discussed = $timestamp
        WITH t
        MATCH (c:Conversation {id: $conv_id})
        MERGE (c)-[:DISCUSSED_TOPIC {at: $timestamp}]->(t)
        WITH t
        MATCH (p:Person {id: $person_id})
        MERGE (p)-[:DISCUSSED_TOPIC {count: t.frequency}]->(t)
        """

        session.run(
            cypher,
            topic_id=topic_id,
            topic_name=topic_name,
            normalized=normalized,
            conv_id=conv_id,
            person_id=person_id,
            timestamp=timestamp
        )

    def _link_conversations(self, session, conv_id1: str, conv_id2: str, timestamp: datetime):
        """Create relationship between related conversations."""
        cypher = """
        MATCH (c1:Conversation {id: $conv_id1})
        MATCH (c2:Conversation {id: $conv_id2})
        MERGE (c1)-[r:RELATED_TO]->(c2)
        ON CREATE SET r.created_at = $timestamp, r.strength = 1
        ON MATCH SET r.strength = COALESCE(r.strength, 0) + 1
        """
        session.run(cypher, conv_id1=conv_id1, conv_id2=conv_id2, timestamp=timestamp)

    def get_conversation(self, conv_id: str) -> Optional[Conversation]:
        """Get a conversation by ID."""
        with self._session() as session:
            if session is None:
                return None

            cypher = """
            MATCH (c:Conversation {id: $conv_id})
            OPTIONAL MATCH (c)-[:RELATED_TO]-(related:Conversation)
            RETURN c, collect(related.id) as related_ids
            """
            result = session.run(cypher, conv_id=conv_id)
            record = result.single()
            if record:
                conv = self._record_to_conversation(record["c"])
                conv.related_conversations = record["related_ids"] or []
                return conv
            return None

    def get_conversations(
        self,
        person_id: str,
        limit: int = 20,
        days: Optional[int] = None,
        include_topics: Optional[List[str]] = None
    ) -> List[Conversation]:
        """
        Get conversations for a person with optional filtering.
        
        Args:
            person_id: Person's unique ID
            limit: Maximum number to return
            days: Only conversations within last N days
            include_topics: Filter by topics
        """
        with self._session() as session:
            if session is None:
                return []

            # Build filter conditions
            conditions = ["c.person_id = $person_id"]
            params = {"person_id": person_id, "limit": limit}

            if days:
                conditions.append("c.timestamp >= $since")
                params["since"] = datetime.now(timezone.utc) - timedelta(days=days)

            if include_topics:
                conditions.append("ANY(topic IN c.topics WHERE topic IN $topics)")
                params["topics"] = include_topics

            where_clause = " AND ".join(conditions)

            cypher = f"""
            MATCH (c:Conversation)
            WHERE {where_clause}
            OPTIONAL MATCH (c)-[:RELATED_TO]-(related:Conversation)
            WITH c, collect(related.id) as related_ids
            ORDER BY c.timestamp DESC
            LIMIT $limit
            RETURN c, related_ids
            """

            result = session.run(cypher, **params)
            conversations = []
            for record in result:
                conv = self._record_to_conversation(record["c"])
                conv.related_conversations = record["related_ids"] or []
                conversations.append(conv)
            return conversations

    def find_similar_conversations(
        self,
        person_id: str,
        query_text: str,
        limit: int = 5,
        min_similarity: float = 0.7
    ) -> List[Tuple[Conversation, float]]:
        """
        Find conversations similar to query text using vector search.
        
        Requires embedding generator to be configured.
        """
        if not self._embedding_generator:
            logger.warning("No embedding generator configured for similarity search")
            return []

        try:
            query_embedding = self._embedding_generator.generate(query_text)
        except Exception as e:
            logger.error(f"Failed to generate query embedding: {e}")
            return []

        with self._session() as session:
            if session is None:
                return []

            cypher = """
            CALL db.index.vector.queryNodes('conversation_embedding', $limit, $query_embedding)
            YIELD node, score
            WHERE node.person_id = $person_id AND score >= $min_similarity
            RETURN node as c, score
            ORDER BY score DESC
            """

            result = session.run(
                cypher,
                person_id=person_id,
                query_embedding=query_embedding,
                limit=limit,
                min_similarity=min_similarity
            )

            return [
                (self._record_to_conversation(record["c"]), record["score"])
                for record in result
            ]

    # ===================================================================
    # Topic Tracking
    # ===================================================================

    def get_recurring_topics(
        self,
        person_id: str,
        min_frequency: int = 2,
        limit: int = 20
    ) -> List[Topic]:
        """
        Get topics that recur across conversations with a person.
        
        Args:
            person_id: Person's unique ID
            min_frequency: Minimum times discussed
            limit: Maximum topics to return
        """
        with self._session() as session:
            if session is None:
                return []

            cypher = """
            MATCH (p:Person {id: $person_id})-[d:DISCUSSED_TOPIC]->(t:Topic)
            WITH t, sum(d.count) as total_frequency,
                 min(d.at) as first_discussed,
                 max(d.at) as last_discussed
            WHERE total_frequency >= $min_frequency
            RETURN t, total_frequency as frequency,
                   first_discussed, last_discussed
            ORDER BY total_frequency DESC, last_discussed DESC
            LIMIT $limit
            """

            result = session.run(
                cypher,
                person_id=person_id,
                min_frequency=min_frequency,
                limit=limit
            )

            return [
                Topic(
                    id=record["t"].get("id", ""),
                    name=record["t"].get("name", ""),
                    normalized_name=record["t"].get("normalized_name", ""),
                    first_discussed=record["first_discussed"],
                    last_discussed=record["last_discussed"],
                    frequency=record["frequency"]
                )
                for record in result
            ]

    def get_topic_history(
        self,
        person_id: str,
        topic_name: str,
        limit: int = 10
    ) -> List[Conversation]:
        """Get all conversations about a specific topic."""
        normalized = topic_name.lower().strip()

        with self._session() as session:
            if session is None:
                return []

            cypher = """
            MATCH (c:Conversation)-[:DISCUSSED_TOPIC]->(t:Topic {normalized_name: $normalized})
            WHERE c.person_id = $person_id
            RETURN c
            ORDER BY c.timestamp DESC
            LIMIT $limit
            """

            result = session.run(
                cypher,
                person_id=person_id,
                normalized=normalized,
                limit=limit
            )

            return [self._record_to_conversation(record["c"]) for record in result]

    # ===================================================================
    # Conversation Summary Building
    # ===================================================================

    def build_conversation_summary(
        self,
        person_id: str,
        days: int = 30
    ) -> ConversationSummary:
        """
        Build a comprehensive summary of recent conversation history.
        
        Args:
            person_id: Person's unique ID
            days: Look back period in days
            
        Returns:
            ConversationSummary with patterns and insights
        """
        conversations = self.get_conversations(person_id, limit=100, days=days)
        topics = self.get_recurring_topics(person_id, min_frequency=2, limit=20)

        total_messages = sum(c.message_count for c in conversations)
        last_interaction = conversations[0].timestamp if conversations else None

        # Calculate patterns
        patterns = self._analyze_patterns(conversations)

        return ConversationSummary(
            person_id=person_id,
            total_conversations=len(conversations),
            total_messages=total_messages,
            recurring_topics=topics,
            recent_conversations=conversations[:10],
            conversation_patterns=patterns,
            last_interaction=last_interaction
        )

    def _analyze_patterns(
        self,
        conversations: List[Conversation]
    ) -> Dict[str, Any]:
        """Analyze conversation patterns."""
        if not conversations:
            return {}

        # Time between conversations
        gaps = []
        for i in range(1, len(conversations)):
            gap = (conversations[i-1].timestamp - conversations[i].timestamp).total_seconds() / 3600
            gaps.append(gap)

        avg_gap = sum(gaps) / len(gaps) if gaps else 0

        # Preferred channel
        channels = {}
        for c in conversations:
            channels[c.channel] = channels.get(c.channel, 0) + 1
        preferred_channel = max(channels, key=channels.get) if channels else None

        # Average conversation length
        avg_duration = sum(
            c.duration_minutes for c in conversations if c.duration_minutes
        ) / len([c for c in conversations if c.duration_minutes]) if any(c.duration_minutes for c in conversations) else None

        # All unique topics
        all_topics = set()
        for c in conversations:
            all_topics.update(c.topics)

        return {
            "average_hours_between_conversations": round(avg_gap, 2),
            "preferred_channel": preferred_channel,
            "average_duration_minutes": round(avg_duration, 2) if avg_duration else None,
            "unique_topics_count": len(all_topics),
            "channel_distribution": channels
        }

    # ===================================================================
    # Context Building for Responses
    # ===================================================================

    def build_response_context(
        self,
        person_id: str,
        current_message: Optional[str] = None,
        include_similar: bool = True
    ) -> Dict[str, Any]:
        """
        Build context to inform response generation.
        
        Args:
            person_id: Person's unique ID
            current_message: Current message being responded to
            include_similar: Whether to include similar past conversations
            
        Returns:
            Context dictionary for response generation
        """
        context = {
            "person_id": person_id,
            "recent_conversations": [],
            "recurring_topics": [],
            "similar_conversations": [],
            "conversation_patterns": {}
        }

        # Get recent conversations
        recent = self.get_conversations(person_id, limit=5)
        context["recent_conversations"] = [
            {
                "summary": c.summary,
                "topics": c.topics,
                "timestamp": c.timestamp.isoformat(),
                "message_count": c.message_count
            }
            for c in recent
        ]

        # Get recurring topics
        topics = self.get_recurring_topics(person_id, min_frequency=2, limit=10)
        context["recurring_topics"] = [
            {"name": t.name, "frequency": t.frequency}
            for t in topics
        ]

        # Find similar conversations if message provided
        if current_message and include_similar:
            similar = self.find_similar_conversations(
                person_id, current_message, limit=3
            )
            context["similar_conversations"] = [
                {
                    "summary": conv.summary,
                    "similarity": score,
                    "topics": conv.topics
                }
                for conv, score in similar
            ]

        # Add patterns
        summary = self.build_conversation_summary(person_id, days=30)
        context["conversation_patterns"] = summary.conversation_patterns
        context["total_conversations_30d"] = summary.total_conversations

        return context

    # ===================================================================
    # Utility Methods
    # ===================================================================

    def _record_to_conversation(self, record: Any) -> Conversation:
        """Convert Neo4j record to Conversation."""
        return Conversation(
            id=record.get("id", ""),
            person_id=record.get("person_id", ""),
            channel=record.get("channel", ""),
            timestamp=record.get("timestamp"),
            summary=record.get("summary", ""),
            topics=record.get("topics", []),
            content_snippet=record.get("content_snippet"),
            message_count=record.get("message_count", 0),
            duration_minutes=record.get("duration_minutes"),
            embedding=record.get("embedding"),
            metadata=self._parse_metadata(record.get("metadata", "{}"))
        )

    def _parse_metadata(self, metadata_str: str) -> Dict[str, Any]:
        """Parse metadata string."""
        import json
        try:
            if isinstance(metadata_str, dict):
                return metadata_str
            return json.loads(metadata_str)
        except:
            return {}


# =============================================================================
# Convenience Functions
# =============================================================================

def create_context_memory(
    neo4j_uri: str = "bolt://localhost:7687",
    neo4j_username: str = "neo4j",
    neo4j_password: Optional[str] = None,
    embedding_generator: Optional[Any] = None
) -> ContextMemory:
    """Create and initialize ContextMemory."""
    memory = ContextMemory(
        neo4j_uri=neo4j_uri,
        neo4j_username=neo4j_username,
        neo4j_password=neo4j_password,
        embedding_generator=embedding_generator
    )
    memory.initialize()
    return memory


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    import os

    logging.basicConfig(level=logging.INFO)

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    password = os.environ.get("NEO4J_PASSWORD")

    memory = ContextMemory(neo4j_uri=uri, neo4j_password=password)

    if memory.initialize():
        # Record a conversation
        conv = memory.record_conversation(
            person_id="signal:+1234567890",
            channel="signal",
            summary="Discussed project architecture and database design",
            topics=["architecture", "database", "neo4j"],
            message_count=15,
            duration_minutes=30
        )
        print(f"Recorded conversation: {conv.id}")

        # Get recurring topics
        topics = memory.get_recurring_topics("signal:+1234567890")
        print(f"Recurring topics: {[t.name for t in topics]}")

        # Build context
        context = memory.build_response_context("signal:+1234567890")
        print(f"Context has {len(context['recent_conversations'])} recent conversations")

    memory.close()
