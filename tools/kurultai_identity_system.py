"""Kurultai Identity System - Integrated identity management for all message flows.

This module provides a unified interface combining:
- IdentityManager: Person tracking and facts
- ContextMemory: Conversation history and topics
- PrivacyGuard: Privacy enforcement and audit

It hooks into message reception and sending for automatic identity tracking.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass

# Import components
from tools.identity_manager import IdentityManager, PrivacyLevel, FactType
from tools.context_memory import ContextMemory
from tools.privacy_guard import PrivacyGuard, AccessAction, PrivacyPolicy

logger = logging.getLogger(__name__)


@dataclass
class MessageContext:
    """Complete context for a message."""
    sender: Optional[Any] = None
    conversation_summary: Optional[Any] = None
    relevant_facts: List[Any] = None
    recent_topics: List[str] = None
    privacy_filtered: bool = False


class KurultaiIdentitySystem:
    """
    Unified identity system for Kurultai.
    
    Provides:
    - Automatic identity tracking on message receipt
    - Privacy-aware context building
    - Content filtering before sending
    - Comprehensive audit trails
    """

    def __init__(
        self,
        neo4j_uri: str = "bolt://localhost:7687",
        neo4j_username: str = "neo4j",
        neo4j_password: Optional[str] = None,
        database: str = "neo4j",
        fallback_mode: bool = True,
        privacy_policy: Optional[PrivacyPolicy] = None,
        embedding_generator: Optional[Any] = None
    ):
        self.neo4j_uri = neo4j_uri
        self.neo4j_username = neo4j_username
        self.neo4j_password = neo4j_password
        self.database = database
        self.fallback_mode = fallback_mode

        # Initialize components
        self.identity = IdentityManager(
            neo4j_uri=neo4j_uri,
            neo4j_username=neo4j_username,
            neo4j_password=neo4j_password,
            database=database,
            fallback_mode=fallback_mode
        )

        self.context = ContextMemory(
            neo4j_uri=neo4j_uri,
            neo4j_username=neo4j_username,
            neo4j_password=neo4j_password,
            database=database,
            fallback_mode=fallback_mode,
            embedding_generator=embedding_generator
        )

        self.privacy = PrivacyGuard(
            neo4j_uri=neo4j_uri,
            neo4j_username=neo4j_username,
            neo4j_password=neo4j_password,
            database=database,
            fallback_mode=fallback_mode,
            policy=privacy_policy
        )

        self._initialized = False

    def initialize(self) -> bool:
        """Initialize all components."""
        identity_ok = self.identity.initialize()
        context_ok = self.context.initialize()
        privacy_ok = self.privacy.initialize()

        self._initialized = identity_ok or context_ok or privacy_ok

        if self._initialized:
            logger.info("KurultaiIdentitySystem initialized")
        else:
            logger.warning("KurultaiIdentitySystem initialized in fallback mode")

        return self._initialized

    def close(self):
        """Close all components."""
        self.identity.close()
        self.context.close()
        self.privacy.close()
        self._initialized = False

    # ===================================================================
    # Message Reception Hooks
    # ===================================================================

    def on_message_received(
        self,
        channel: str,
        sender_handle: str,
        sender_name: Optional[str] = None,
        message_text: Optional[str] = None,
        sender_hash: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Hook called when a message is received.
        
        Automatically:
        1. Gets or creates sender identity
        2. Updates last_seen timestamp
        3. Extracts context
        4. Builds conversation context
        
        Args:
            channel: Message channel (signal, discord, etc.)
            sender_handle: Sender's channel handle
            sender_name: Sender's display name
            message_text: Message content
            sender_hash: For sender isolation
            metadata: Additional metadata
            
        Returns:
            Context dictionary for the conversation
        """
        # Get or create person identity
        person = self.identity.get_or_create_person(
            channel=channel,
            handle=sender_handle,
            name=sender_name,
            sender_hash=sender_hash,
            **(metadata or {})
        )

        # Log the access
        self.privacy.log_access(
            person_id=person.id,
            action=AccessAction.READ,
            accessed_by="kurultai",
            context=f"Message received on {channel}",
            privacy_level=PrivacyLevel.PRIVATE
        )

        # Get recent conversations for context
        recent_conversations = self.context.get_conversations(
            person_id=person.id,
            limit=5
        )

        # Get recurring topics
        topics = self.context.get_recurring_topics(
            person_id=person.id,
            min_frequency=2,
            limit=10
        )

        # Get person context with private info
        person_context = self.identity.get_person_context(
            person_id=person.id,
            include_private=True,
            include_sensitive=False
        )

        return {
            "person": person,
            "person_id": person.id,
            "recent_conversations": [
                {
                    "summary": c.summary,
                    "topics": c.topics,
                    "timestamp": c.timestamp.isoformat()
                }
                for c in recent_conversations
            ],
            "recurring_topics": [{"name": t.name, "frequency": t.frequency} for t in topics],
            "preferences": person_context.preferences if person_context else {},
            "facts": [
                {
                    "key": f.fact_key,
                    "value": f.fact_value,
                    "privacy": f.privacy_level.value,
                    "confidence": f.confidence
                }
                for f in (person_context.recent_facts if person_context else [])
            ],
            "total_conversations": person.total_conversations
        }

    def extract_facts_from_message(
        self,
        person_id: str,
        message_text: str,
        extracted_facts: List[Dict[str, Any]]
    ) -> List[Any]:
        """
        Extract and store facts from a message.
        
        Args:
            person_id: Person's unique ID
            message_text: Message content
            extracted_facts: List of fact dicts from NLP extraction
                Each should have: {type, key, value, confidence}
                
        Returns:
            List of stored Fact objects
        """
        stored_facts = []

        for fact_data in extracted_facts:
            try:
                fact_type = FactType(fact_data.get("type", "other"))
            except ValueError:
                fact_type = FactType.OTHER

            # Determine privacy level based on content
            privacy_check = self.privacy.check_content_privacy(
                fact_data.get("value", ""),
                target_privacy=PrivacyLevel.PUBLIC
            )

            privacy_level = PrivacyLevel(
                privacy_check.get("recommendation", "private")
            )

            fact = self.identity.add_fact(
                person_id=person_id,
                fact_type=fact_type,
                key=fact_data.get("key", "unknown"),
                value=fact_data.get("value", ""),
                privacy_level=privacy_level,
                confidence=fact_data.get("confidence", 0.8),
                source="message_extraction"
            )

            stored_facts.append(fact)

            # Audit the write
            self.privacy.log_access(
                person_id=person_id,
                action=AccessAction.WRITE,
                accessed_by="kurultai",
                context=f"Extracted fact from message: {fact.fact_key}",
                fact_id=fact.id,
                privacy_level=privacy_level
            )

        return stored_facts

    def record_conversation_summary(
        self,
        person_id: str,
        channel: str,
        summary: str,
        topics: Optional[List[str]] = None,
        message_count: int = 0,
        duration_minutes: Optional[int] = None
    ) -> Any:
        """
        Record conversation summary after interaction.
        
        Args:
            person_id: Person's unique ID
            channel: Channel name
            summary: Conversation summary
            topics: Topics discussed
            message_count: Number of messages
            duration_minutes: Duration
            
        Returns:
            Conversation object
        """
        # Increment conversation count
        self.identity.increment_conversation_count(person_id)

        # Record the conversation
        conversation = self.context.record_conversation(
            person_id=person_id,
            channel=channel,
            summary=summary,
            topics=topics or [],
            message_count=message_count,
            duration_minutes=duration_minutes
        )

        return conversation

    # ===================================================================
    # Message Sending Hooks
    # ===================================================================

    def filter_outgoing_message(
        self,
        content: str,
        sender_person_id: Optional[str],
        recipient_person_id: str,
        agent_name: str = "kurultai"
    ) -> Dict[str, Any]:
        """
        Filter outgoing message for privacy before sending.
        
        Args:
            content: Message content
            sender_person_id: Person sending (may be None for system)
            recipient_person_id: Person receiving
            agent_name: Agent generating the response
            
        Returns:
            Filter result with safe content and metadata
        """
        # If no sender specified, only filter if content contains person data
        if sender_person_id is None:
            # Just check for sensitive content
            privacy_check = self.privacy.check_content_privacy(
                content,
                target_privacy=PrivacyLevel.PUBLIC
            )

            if privacy_check["is_safe"]:
                return {
                    "content": content,
                    "was_filtered": False,
                    "violations": [],
                    "safe_to_send": True
                }
            else:
                return {
                    "content": content,
                    "was_filtered": False,
                    "violations": privacy_check["warnings"],
                    "safe_to_send": False,
                    "recommendation": "Review content for sensitive information"
                }

        # Filter content for the specific recipient
        filter_result = self.privacy.filter_content_for_audience(
            content=content,
            owner_person_id=sender_person_id,
            audience_person_id=recipient_person_id,
            accessed_by=agent_name,
            context="outgoing_message"
        )

        return {
            "content": filter_result.filtered_content,
            "was_filtered": filter_result.was_modified,
            "violations": filter_result.privacy_violations,
            "filtered_items": filter_result.filtered_items,
            "safe_to_send": True  # If we filtered it, it's safe
        }

    def build_response_context(
        self,
        recipient_person_id: str,
        current_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build complete context for generating a response.
        
        This provides everything needed to generate a personalized,
        context-aware response while respecting privacy.
        
        Args:
            recipient_person_id: Person to respond to
            current_message: Current message (for similarity search)
            
        Returns:
            Context dictionary safe for response generation
        """
        # Get person identity
        person = self.identity.get_person(recipient_person_id)

        if not person:
            return {
                "person_id": recipient_person_id,
                "known_identity": False,
                "context": {}
            }

        # Get allowed facts (public only - we're sending to this person about themselves)
        # Actually for response generation, we want private info about them too
        facts = self.identity.get_facts(
            person_id=recipient_person_id,
            privacy_levels=[PrivacyLevel.PUBLIC, PrivacyLevel.PRIVATE],
            min_confidence=0.6,
            limit=15
        )

        # Build context memory
        context = self.context.build_response_context(
            person_id=recipient_person_id,
            current_message=current_message,
            include_similar=True
        )

        return {
            "person_id": recipient_person_id,
            "known_identity": True,
            "person_name": person.name,
            "total_conversations": person.total_conversations,
            "first_seen": person.first_seen.isoformat() if person.first_seen else None,
            "facts": [
                {
                    "key": f.fact_key,
                    "value": f.fact_value,
                    "type": f.fact_type.value,
                    "confidence": f.confidence
                }
                for f in facts
            ],
            "context": context
        }

    # ===================================================================
    # Cross-Person Privacy
    # ===================================================================

    def can_share_information(
        self,
        source_person_id: str,
        target_person_id: str,
        information_privacy: PrivacyLevel
    ) -> bool:
        """
        Check if information can be shared between persons.
        
        Args:
            source_person_id: Person the info is about
            target_person_id: Person who would receive it
            information_privacy: Privacy level of the info
            
        Returns:
            True if sharing is allowed
        """
        # Public information can always be shared
        if information_privacy == PrivacyLevel.PUBLIC:
            return True

        # Private/Sensitive info only if same person
        return source_person_id == target_person_id

    def get_safe_facts_for_sharing(
        self,
        source_person_id: str,
        target_person_id: str,
        fact_type: Optional[FactType] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get facts that are safe to share with a specific person.
        
        Args:
            source_person_id: Person the facts are about
            target_person_id: Person to share with
            fact_type: Optional type filter
            limit: Maximum facts
            
        Returns:
            List of safe facts
        """
        # Only get public facts
        facts = self.identity.get_facts(
            person_id=source_person_id,
            fact_type=fact_type,
            privacy_levels=[PrivacyLevel.PUBLIC],
            min_confidence=0.7,
            limit=limit
        )

        return [
            {
                "key": f.fact_key,
                "value": f.fact_value,
                "type": f.fact_type.value,
                "confidence": f.confidence
            }
            for f in facts
        ]

    # ===================================================================
    # Maintenance
    # ===================================================================

    def run_maintenance(self) -> Dict[str, int]:
        """
        Run maintenance tasks:
        - Purge expired audit logs
        - Archive old conversations
        
        Returns:
            Summary of maintenance actions
        """
        audit_purged = self.privacy.purge_expired_audit_logs()
        conversations_archived = self.privacy.archive_old_conversations()

        return {
            "audit_logs_purged": audit_purged,
            "conversations_archived": conversations_archived
        }

    def get_system_stats(self) -> Dict[str, Any]:
        """Get statistics about the identity system."""
        # This would query Neo4j for aggregate stats
        # For now, return placeholder
        return {
            "components": {
                "identity_manager": "initialized" if self.identity._initialized else "not_initialized",
                "context_memory": "initialized" if self.context._initialized else "not_initialized",
                "privacy_guard": "initialized" if self.privacy._initialized else "not_initialized"
            },
            "privacy_policy": {
                "default_fact_privacy": self.privacy.policy.default_fact_privacy.value,
                "audit_retention_days": self.privacy.policy.retain_audit_logs_days
            }
        }


# =============================================================================
# Singleton Instance
# =============================================================================

_identity_system: Optional[KurultaiIdentitySystem] = None


def get_identity_system(
    neo4j_uri: str = "bolt://localhost:7687",
    neo4j_username: str = "neo4j",
    neo4j_password: Optional[str] = None
) -> KurultaiIdentitySystem:
    """Get or create singleton identity system instance."""
    global _identity_system

    if _identity_system is None:
        _identity_system = KurultaiIdentitySystem(
            neo4j_uri=neo4j_uri,
            neo4j_username=neo4j_username,
            neo4j_password=neo4j_password
        )
        _identity_system.initialize()

    return _identity_system


def close_identity_system():
    """Close the singleton identity system."""
    global _identity_system
    if _identity_system:
        _identity_system.close()
        _identity_system = None


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    import os

    logging.basicConfig(level=logging.INFO)

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    password = os.environ.get("NEO4J_PASSWORD")

    system = KurultaiIdentitySystem(neo4j_uri=uri, neo4j_password=password)

    if system.initialize():
        # Simulate receiving a message
        context = system.on_message_received(
            channel="signal",
            sender_handle="+1234567890",
            sender_name="Alice",
            message_text="I prefer direct communication"
        )
        print(f"Received message from {context['person'].name}")

        # Extract facts
        facts = system.extract_facts_from_message(
            person_id=context["person_id"],
            message_text="I prefer direct communication",
            extracted_facts=[
                {"type": "preference", "key": "communication_style", "value": "direct", "confidence": 0.9}
            ]
        )
        print(f"Extracted {len(facts)} facts")

        # Build response context
        response_ctx = system.build_response_context(context["person_id"])
        print(f"Response context has {len(response_ctx['facts'])} facts")

        # Filter outgoing message
        filtered = system.filter_outgoing_message(
            content="Alice's password is secret123 but she likes pizza",
            sender_person_id=None,
            recipient_person_id=context["person_id"]
        )
        print(f"Filtered content: {filtered['content']}")

        # Record conversation
        conv = system.record_conversation_summary(
            person_id=context["person_id"],
            channel="signal",
            summary="Discussed communication preferences",
            topics=["preferences", "communication"],
            message_count=5
        )
        print(f"Recorded conversation: {conv.id}")

    system.close()
