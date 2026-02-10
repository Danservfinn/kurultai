"""Tests for Identity Management System."""

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock

# Import components to test
from tools.identity_manager import (
    IdentityManager, PersonIdentity, Fact, PrivacyLevel, FactType
)
from tools.context_memory import ContextMemory, Conversation, Topic
from tools.privacy_guard import PrivacyGuard, AccessAction, PrivacyPolicy, FilterResult
from tools.kurultai_identity_system import KurultaiIdentitySystem
from migrations.v4_identity_management import V4IdentityManagement


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_neo4j_session():
    """Create a mock Neo4j session."""
    session = Mock()
    session.run = Mock(return_value=Mock())
    return session


@pytest.fixture
def mock_neo4j_driver(mock_neo4j_session):
    """Create a mock Neo4j driver."""
    driver = Mock()
    driver.session = Mock(return_value=mock_neo4j_session)
    driver.verify_connectivity = Mock()
    return driver


@pytest.fixture
def identity_manager(mock_neo4j_driver):
    """Create an IdentityManager with mocked Neo4j."""
    with patch('tools.identity_manager.IdentityManager._GraphDatabase') as mock_db:
        mock_db.driver.return_value = mock_neo4j_driver
        manager = IdentityManager(
            neo4j_uri="bolt://localhost:7687",
            neo4j_password="testpass"
        )
        manager._driver = mock_neo4j_driver
        manager._initialized = True
        yield manager


@pytest.fixture
def context_memory(mock_neo4j_driver):
    """Create a ContextMemory with mocked Neo4j."""
    with patch('tools.context_memory.ContextMemory._GraphDatabase') as mock_db:
        mock_db.driver.return_value = mock_neo4j_driver
        memory = ContextMemory(
            neo4j_uri="bolt://localhost:7687",
            neo4j_password="testpass"
        )
        memory._driver = mock_neo4j_driver
        memory._initialized = True
        yield memory


@pytest.fixture
def privacy_guard(mock_neo4j_driver):
    """Create a PrivacyGuard with mocked Neo4j."""
    with patch('tools.privacy_guard.PrivacyGuard._GraphDatabase') as mock_db:
        mock_db.driver.return_value = mock_neo4j_driver
        guard = PrivacyGuard(
            neo4j_uri="bolt://localhost:7687",
            neo4j_password="testpass"
        )
        guard._driver = mock_neo4j_driver
        guard._initialized = True
        yield guard


# =============================================================================
# Identity Manager Tests
# =============================================================================

class TestIdentityManager:
    """Tests for IdentityManager."""

    def test_person_identity_creation(self):
        """Test PersonIdentity dataclass."""
        now = datetime.now(timezone.utc)
        person = PersonIdentity(
            id="signal:+1234567890",
            name="Alice",
            handle="+1234567890",
            channel="signal",
            first_seen=now,
            last_seen=now,
            total_conversations=5
        )

        assert person.id == "signal:+1234567890"
        assert person.name == "Alice"
        assert person.total_conversations == 5

    def test_fact_creation(self):
        """Test Fact dataclass."""
        now = datetime.now(timezone.utc)
        fact = Fact(
            id="fact-123",
            person_id="signal:+1234567890",
            fact_type=FactType.PREFERENCE,
            fact_key="communication_style",
            fact_value="direct",
            privacy_level=PrivacyLevel.PUBLIC,
            confidence=0.9,
            source="test",
            created_at=now,
            updated_at=now
        )

        assert fact.fact_type == FactType.PREFERENCE
        assert fact.privacy_level == PrivacyLevel.PUBLIC
        assert fact.confidence == 0.9

    def test_privacy_level_enum(self):
        """Test PrivacyLevel enum values."""
        assert PrivacyLevel.PUBLIC.value == "public"
        assert PrivacyLevel.PRIVATE.value == "private"
        assert PrivacyLevel.SENSITIVE.value == "sensitive"

    def test_fact_type_enum(self):
        """Test FactType enum values."""
        assert FactType.PREFERENCE.value == "preference"
        assert FactType.HABIT.value == "habit"
        assert FactType.IDENTITY.value == "identity"

    def test_get_or_create_person_new(self, identity_manager, mock_neo4j_session):
        """Test creating a new person."""
        # Mock the query result
        mock_record = Mock()
        mock_record.__getitem__ = Mock(return_value={
            "id": "signal:+1234567890",
            "name": "Alice",
            "handle": "+1234567890",
            "channel": "signal",
            "total_conversations": 0,
            "is_active": True
        })
        
        mock_result = Mock()
        mock_result.single.return_value = mock_record
        mock_neo4j_session.run.return_value = mock_result

        person = identity_manager.get_or_create_person(
            channel="signal",
            handle="+1234567890",
            name="Alice"
        )

        assert person.id == "signal:+1234567890"
        assert person.name == "Alice"
        assert person.channel == "signal"

    def test_add_fact(self, identity_manager, mock_neo4j_session):
        """Test adding a fact."""
        mock_record = Mock()
        mock_record.__getitem__ = Mock(return_value={
            "id": str(uuid.uuid4()),
            "person_id": "signal:+1234567890",
            "fact_type": "preference",
            "fact_key": "style",
            "fact_value": "direct",
            "privacy_level": "public",
            "confidence": 0.9,
            "source": "test",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        })

        mock_result = Mock()
        mock_result.single.return_value = mock_record
        mock_neo4j_session.run.return_value = mock_result

        fact = identity_manager.add_fact(
            person_id="signal:+1234567890",
            fact_type=FactType.PREFERENCE,
            key="style",
            value="direct",
            privacy_level=PrivacyLevel.PUBLIC,
            confidence=0.9
        )

        assert fact.fact_key == "style"
        assert fact.fact_value == "direct"
        assert fact.privacy_level == PrivacyLevel.PUBLIC

    def test_get_facts_filtering(self, identity_manager, mock_neo4j_session):
        """Test getting facts with filters."""
        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([]))
        mock_neo4j_session.run.return_value = mock_result

        facts = identity_manager.get_facts(
            person_id="signal:+1234567890",
            privacy_levels=[PrivacyLevel.PUBLIC],
            min_confidence=0.7
        )

        assert facts == []


# =============================================================================
# Context Memory Tests
# =============================================================================

class TestContextMemory:
    """Tests for ContextMemory."""

    def test_conversation_creation(self):
        """Test Conversation dataclass."""
        now = datetime.now(timezone.utc)
        conv = Conversation(
            id="conv-123",
            person_id="signal:+1234567890",
            channel="signal",
            timestamp=now,
            summary="Test conversation",
            topics=["test", "example"],
            message_count=10
        )

        assert conv.id == "conv-123"
        assert conv.channel == "signal"
        assert len(conv.topics) == 2

    def test_topic_creation(self):
        """Test Topic dataclass."""
        now = datetime.now(timezone.utc)
        topic = Topic(
            id="topic-123",
            name="Testing",
            normalized_name="testing",
            first_discussed=now,
            last_discussed=now,
            frequency=5
        )

        assert topic.name == "Testing"
        assert topic.frequency == 5

    def test_record_conversation(self, context_memory, mock_neo4j_session):
        """Test recording a conversation."""
        mock_neo4j_session.run.return_value = Mock()

        conv = context_memory.record_conversation(
            person_id="signal:+1234567890",
            channel="signal",
            summary="Test conversation",
            topics=["test"],
            message_count=5
        )

        assert conv.person_id == "signal:+1234567890"
        assert conv.summary == "Test conversation"
        assert conv.message_count == 5

    def test_get_conversations(self, context_memory, mock_neo4j_session):
        """Test getting conversations."""
        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([]))
        mock_neo4j_session.run.return_value = mock_result

        conversations = context_memory.get_conversations(
            person_id="signal:+1234567890",
            limit=10
        )

        assert conversations == []


# =============================================================================
# Privacy Guard Tests
# =============================================================================

class TestPrivacyGuard:
    """Tests for PrivacyGuard."""

    def test_privacy_policy_defaults(self):
        """Test PrivacyPolicy defaults."""
        policy = PrivacyPolicy()

        assert policy.default_fact_privacy == PrivacyLevel.PRIVATE
        assert policy.retain_audit_logs_days == 90
        assert policy.enable_audit_logging == True

    def test_filter_result_creation(self):
        """Test FilterResult dataclass."""
        result = FilterResult(
            original_content="secret info here",
            filtered_content="[REDACTED] here",
            was_modified=True,
            filtered_items=["secret info"],
            privacy_violations=["Filtered private fact"]
        )

        assert result.was_modified == True
        assert len(result.filtered_items) == 1

    def test_check_content_privacy_safe(self, privacy_guard):
        """Test content privacy check with safe content."""
        result = privacy_guard.check_content_privacy(
            "Hello, how are you today?",
            target_privacy=PrivacyLevel.PUBLIC
        )

        assert result["is_safe"] == True
        assert len(result["warnings"]) == 0

    def test_check_content_privacy_with_email(self, privacy_guard):
        """Test content privacy check with email."""
        result = privacy_guard.check_content_privacy(
            "Contact me at user@example.com",
            target_privacy=PrivacyLevel.PUBLIC
        )

        assert result["is_safe"] == False
        assert any("email" in w.lower() for w in result["warnings"])

    def test_filter_content_for_audience(self, privacy_guard, mock_neo4j_session):
        """Test filtering content for audience."""
        # Mock finding no facts in content
        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([]))
        mock_neo4j_session.run.return_value = mock_result

        result = privacy_guard.filter_content_for_audience(
            content="Hello world",
            owner_person_id="signal:alice",
            audience_person_id="signal:bob",
            accessed_by="test"
        )

        assert result.was_modified == False
        assert result.filtered_content == "Hello world"


# =============================================================================
# Kurultai Identity System Tests
# =============================================================================

class TestKurultaiIdentitySystem:
    """Tests for KurultaiIdentitySystem integration."""

    def test_initialization(self):
        """Test system initialization."""
        with patch('tools.identity_manager.IdentityManager._GraphDatabase'), \
             patch('tools.context_memory.ContextMemory._GraphDatabase'), \
             patch('tools.privacy_guard.PrivacyGuard._GraphDatabase'):
            
            system = KurultaiIdentitySystem(
                neo4j_uri="bolt://localhost:7687",
                neo4j_password="testpass"
            )
            
            # Mock the components
            system.identity._initialized = True
            system.context._initialized = True
            system.privacy._initialized = True
            
            assert system.initialize() == True

    def test_on_message_received(self):
        """Test message reception hook."""
        with patch('tools.identity_manager.IdentityManager._GraphDatabase'), \
             patch('tools.context_memory.ContextMemory._GraphDatabase'), \
             patch('tools.privacy_guard.PrivacyGuard._GraphDatabase'):
            
            system = KurultaiIdentitySystem(
                neo4j_uri="bolt://localhost:7687",
                neo4j_password="testpass"
            )
            
            # Mock components
            mock_person = PersonIdentity(
                id="signal:+1234567890",
                name="Alice",
                handle="+1234567890",
                channel="signal",
                first_seen=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
                total_conversations=5
            )
            
            system.identity.get_or_create_person = Mock(return_value=mock_person)
            system.identity.get_person_context = Mock(return_value=Mock(
                preferences={"style": "direct"},
                recent_facts=[]
            ))
            system.context.get_conversations = Mock(return_value=[])
            system.context.get_recurring_topics = Mock(return_value=[])
            system.privacy.log_access = Mock()
            
            context = system.on_message_received(
                channel="signal",
                sender_handle="+1234567890",
                sender_name="Alice"
            )
            
            assert context["person_id"] == "signal:+1234567890"
            assert context["total_conversations"] == 5

    def test_filter_outgoing_message(self):
        """Test outgoing message filtering."""
        with patch('tools.identity_manager.IdentityManager._GraphDatabase'), \
             patch('tools.context_memory.ContextMemory._GraphDatabase'), \
             patch('tools.privacy_guard.PrivacyGuard._GraphDatabase'):
            
            system = KurultaiIdentitySystem(
                neo4j_uri="bolt://localhost:7687",
                neo4j_password="testpass"
            )
            
            # Mock privacy guard
            system.privacy.filter_content_for_audience = Mock(return_value=FilterResult(
                original_content="secret here",
                filtered_content="[REDACTED] here",
                was_modified=True,
                filtered_items=["secret"],
                privacy_violations=["private fact"]
            ))
            
            result = system.filter_outgoing_message(
                content="secret here",
                sender_person_id="signal:alice",
                recipient_person_id="signal:bob"
            )
            
            assert result["was_filtered"] == True
            assert result["content"] == "[REDACTED] here"

    def test_can_share_information(self):
        """Test information sharing permission."""
        with patch('tools.identity_manager.IdentityManager._GraphDatabase'), \
             patch('tools.context_memory.ContextMemory._GraphDatabase'), \
             patch('tools.privacy_guard.PrivacyGuard._GraphDatabase'):
            
            system = KurultaiIdentitySystem(
                neo4j_uri="bolt://localhost:7687",
                neo4j_password="testpass"
            )
            
            # Public can always be shared
            assert system.can_share_information(
                "signal:alice", "signal:bob", PrivacyLevel.PUBLIC
            ) == True
            
            # Private only with same person
            assert system.can_share_information(
                "signal:alice", "signal:alice", PrivacyLevel.PRIVATE
            ) == True
            assert system.can_share_information(
                "signal:alice", "signal:bob", PrivacyLevel.PRIVATE
            ) == False


# =============================================================================
# Migration Tests
# =============================================================================

class TestV4Migration:
    """Tests for V4 Identity Management migration."""

    def test_migration_version(self):
        """Test migration version is correct."""
        assert V4IdentityManagement.VERSION == 4
        assert V4IdentityManagement.NAME == "identity_management"

    def test_migration_summary(self):
        """Test migration summary."""
        summary = V4IdentityManagement.get_summary()

        assert summary["version"] == 4
        assert summary["constraints_created"] == 6
        assert summary["indexes_created"] == 20
        assert "Person" in summary["node_types"]
        assert "Fact" in summary["node_types"]

    def test_migration_has_up_cypher(self):
        """Test migration has UP Cypher."""
        assert "CREATE CONSTRAINT person_id_unique" in V4IdentityManagement.UP_CYPHER
        assert "CREATE INDEX person_channel_lookup" in V4IdentityManagement.UP_CYPHER

    def test_migration_has_down_cypher(self):
        """Test migration has DOWN Cypher."""
        assert "DROP CONSTRAINT person_id_unique" in V4IdentityManagement.DOWN_CYPHER
        assert "DROP INDEX person_channel_lookup" in V4IdentityManagement.DOWN_CYPHER


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the full identity system."""

    @pytest.mark.skip(reason="Requires real Neo4j instance")
    def test_full_workflow(self):
        """Test complete workflow with real Neo4j (skipped by default)."""
        import os
        
        # This test requires a real Neo4j instance
        uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        password = os.environ.get("NEO4J_PASSWORD", "password")
        
        system = KurultaiIdentitySystem(
            neo4j_uri=uri,
            neo4j_password=password
        )
        
        try:
            assert system.initialize()
            
            # Create person
            person = system.identity.get_or_create_person(
                channel="test",
                handle="test-user",
                name="Test User"
            )
            
            assert person.id == "test:test-user"
            
            # Add facts
            fact = system.identity.add_fact(
                person_id=person.id,
                fact_type=FactType.PREFERENCE,
                key="test_pref",
                value="test_value",
                privacy_level=PrivacyLevel.PUBLIC
            )
            
            assert fact.fact_key == "test_pref"
            
            # Record conversation
            conv = system.context.record_conversation(
                person_id=person.id,
                channel="test",
                summary="Test conversation",
                topics=["test"]
            )
            
            assert conv.summary == "Test conversation"
            
            # Filter message
            result = system.filter_outgoing_message(
                content="Test message",
                sender_person_id=None,
                recipient_person_id=person.id
            )
            
            assert result["safe_to_send"] == True
            
        finally:
            system.close()


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
