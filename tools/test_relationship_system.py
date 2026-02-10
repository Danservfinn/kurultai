"""Tests for the Relationship Tracking System.

Tests cover:
- RelationshipDetector: Single conversation analysis
- RelationshipAnalyzer: Horde-based batch analysis
- RelationshipManager: Neo4j integration and context building
"""

import pytest
import sys
import os
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tools.relationship_detector import (
    RelationshipDetector,
    RelationshipType,
    DetectedRelationship,
    detect_relationships,
    detect_relationship_to_primary
)
from tools.relationship_analyzer import (
    RelationshipAnalyzer,
    AggregatedRelationship,
    HordeAnalysisResult,
    AnalysisStatus,
    analyze_relationships_horde
)
from tools.relationship_manager import (
    RelationshipManager,
    RelationshipContext,
    get_person_network
)


# =============================================================================
# RelationshipDetector Tests
# =============================================================================

class TestRelationshipDetector:
    """Tests for RelationshipDetector."""
    
    @pytest.fixture
    def detector(self):
        return RelationshipDetector(primary_human="Danny")
    
    def test_initialization(self):
        """Test detector initialization."""
        detector = RelationshipDetector(primary_human="Alice")
        assert detector.primary_human == "Alice"
    
    def test_extract_people_mentions(self, detector):
        """Test extracting person mentions from text."""
        text = "I was talking to Sarah and John about the project."
        mentions = detector._extract_people_mentions(text, "speaker")
        
        assert "Sarah" in mentions
        assert "John" in mentions
        assert "speaker" not in mentions
    
    def test_extract_at_mentions(self, detector):
        """Test extracting @mentions."""
        text = "Hey @alice and @bob, what do you think?"
        mentions = detector._extract_people_mentions(text, "speaker")
        
        assert "alice" in mentions
        assert "bob" in mentions
    
    def test_analyze_relationship_clue_family(self, detector):
        """Test detecting family relationships."""
        text = "My brother Danny is helping me with the project."
        clue = detector._analyze_relationship_clue(text, "Danny", "speaker")
        
        assert clue.relationship_type == RelationshipType.FAMILY
        assert clue.confidence > 0.3
        assert "brother" in clue.indicators
    
    def test_analyze_relationship_clue_colleague(self, detector):
        """Test detecting colleague relationships."""
        text = "I work with Danny at the startup. He's my colleague."
        clue = detector._analyze_relationship_clue(text, "Danny", "speaker")
        
        assert clue.relationship_type == RelationshipType.COLLEAGUE
        assert any(ind in clue.indicators for ind in ["colleague", "work"])
    
    def test_analyze_relationship_clue_friend(self, detector):
        """Test detecting friend relationships."""
        text = "Danny is my best friend. We go way back."
        clue = detector._analyze_relationship_clue(text, "Danny", "speaker")
        
        assert clue.relationship_type == RelationshipType.FRIEND
        assert clue.confidence > 0.3
    
    def test_analyze_relationship_clue_business(self, detector):
        """Test detecting business partner relationships."""
        text = "Danny is my co-founder and business partner."
        clue = detector._analyze_relationship_clue(text, "Danny", "speaker")
        
        assert clue.relationship_type == RelationshipType.BUSINESS_PARTNER
    
    def test_analyze_relationship_clue_mentor(self, detector):
        """Test detecting mentor relationships."""
        text = "Danny has been mentoring me on my career."
        clue = detector._analyze_relationship_clue(text, "Danny", "speaker")
        
        assert clue.relationship_type == RelationshipType.MENTOR
    
    def test_calculate_strength_modifier_high(self, detector):
        """Test high strength signals."""
        text = "Danny is my best friend. I trust him completely."
        modifier = detector._calculate_strength_modifier(text)
        
        assert modifier > 0
    
    def test_calculate_strength_modifier_low(self, detector):
        """Test low strength signals."""
        text = "I rarely talk to Danny. We're not close."
        modifier = detector._calculate_strength_modifier(text)
        
        assert modifier < 0
    
    def test_analyze_conversation(self, detector):
        """Test analyzing a full conversation."""
        conversation = """
        I've been working with Danny on Kurultai for 6 months.
        He's my business partner. My friend Sarah introduced us.
        """
        
        relationships = detector.analyze_conversation(
            conversation_text=conversation,
            speaker_id="alice",
            speaker_name="Alice"
        )
        
        assert len(relationships) >= 1
        
        # Check Danny relationship
        danny_rel = next(
            (r for r in relationships if r.person_b == "Danny"),
            None
        )
        assert danny_rel is not None
        assert danny_rel.relationship_type == RelationshipType.BUSINESS_PARTNER
    
    def test_analyze_for_primary_human(self, detector):
        """Test analyzing specifically for primary human relationship."""
        conversation = "Danny and I are good friends from college."
        
        rel = detector.analyze_for_primary_human(
            conversation_text=conversation,
            other_person="Alice"
        )
        
        assert rel is not None
        assert rel.relationship_type == RelationshipType.FRIEND
        assert rel.person_b == "Danny"
    
    def test_analyze_for_primary_human_no_mention(self, detector):
        """Test when primary human is not mentioned."""
        conversation = "Alice and I are working on a project."
        
        rel = detector.analyze_for_primary_human(
            conversation_text=conversation,
            other_person="Bob"
        )
        
        assert rel is None
    
    def test_merge_relationships(self, detector):
        """Test merging two relationship detections."""
        from tools.relationship_detector import RelationshipEvidence, RelationshipClue
        
        now = datetime.now(timezone.utc)
        
        existing = DetectedRelationship(
            person_a="Alice",
            person_b="Danny",
            relationship_type=RelationshipType.FRIEND,
            strength=0.7,
            context="Old context",
            discovered_at=now,
            last_updated=now,
            confidence=0.6,
            evidence_count=1,
            evidence=[]
        )
        
        new = DetectedRelationship(
            person_a="Alice",
            person_b="Danny",
            relationship_type=RelationshipType.FRIEND,
            strength=0.8,
            context="New context",
            discovered_at=now,
            last_updated=now,
            confidence=0.7,
            evidence_count=1,
            evidence=[]
        )
        
        merged = detector.merge_relationships(existing, new)
        
        assert merged.strength > existing.strength  # Should increase
        assert merged.strength < new.strength  # But not fully to new
        assert merged.confidence > existing.confidence
        assert merged.evidence_count == 2


# =============================================================================
# Convenience Function Tests
# =============================================================================

def test_detect_relationships_convenience():
    """Test the detect_relationships convenience function."""
    conversation = "My colleague Danny and I are working on a project."
    
    relationships = detect_relationships(
        conversation_text=conversation,
        speaker_id="alice",
        primary_human="Danny"
    )
    
    assert len(relationships) >= 1


def test_detect_relationship_to_primary_convenience():
    """Test the detect_relationship_to_primary convenience function."""
    conversation = "Danny is my mentor and guide."
    
    rel = detect_relationship_to_primary(
        conversation_text=conversation,
        other_person="Alice",
        primary_human="Danny"
    )
    
    assert rel is not None
    assert rel.relationship_type == RelationshipType.MENTOR


# =============================================================================
# RelationshipAnalyzer Tests
# =============================================================================

class TestRelationshipAnalyzer:
    """Tests for RelationshipAnalyzer."""
    
    @pytest.fixture
    def analyzer(self):
        analyzer = RelationshipAnalyzer(
            primary_human="Danny",
            max_workers=2,
            use_subagents=False  # Don't spawn real agents in tests
        )
        analyzer.initialize()
        return analyzer
    
    def test_initialization(self, analyzer):
        """Test analyzer initialization."""
        assert analyzer._initialized
        assert analyzer.primary_human == "Danny"
    
    def test_create_batches(self, analyzer):
        """Test batch creation."""
        conversations = [
            {"text": f"conv {i}", "speaker_id": f"user_{i}"}
            for i in range(25)
        ]
        
        batches = analyzer._create_batches(
            conversations, 
            batch_size=10,
            target_person=None,
            focus_on_primary=True
        )
        
        assert len(batches) == 3  # 25 / 10 = 3 batches
        assert len(batches[0].conversations) == 10
        assert len(batches[1].conversations) == 10
        assert len(batches[2].conversations) == 5
    
    def test_analyze_batch(self, analyzer):
        """Test single batch analysis."""
        from tools.relationship_analyzer import ConversationBatch
        
        batch = ConversationBatch(
            batch_id="test_batch",
            conversations=[{
                "text": "Danny is my colleague and we work together.",
                "speaker_id": "alice",
                "speaker_name": "Alice",
                "timestamp": datetime.now(timezone.utc)
            }],
            focus_on_primary=True
        )
        
        result = analyzer._analyze_batch(batch)
        
        assert result.status == AnalysisStatus.COMPLETED
        assert result.batch_id == "test_batch"
        assert len(result.relationships) >= 1
    
    def test_aggregate_relationships(self, analyzer):
        """Test result aggregation."""
        from tools.relationship_analyzer import AgentAnalysisResult
        
        now = datetime.now(timezone.utc)
        
        # Create mock agent results
        agent_results = [
            AgentAnalysisResult(
                agent_id="agent1",
                batch_id="batch1",
                status=AnalysisStatus.COMPLETED,
                relationships=[
                    DetectedRelationship(
                        person_a="Alice",
                        person_b="Danny",
                        relationship_type=RelationshipType.COLLEAGUE,
                        strength=0.8,
                        context="Work together",
                        discovered_at=now,
                        last_updated=now,
                        confidence=0.7,
                        evidence_count=1,
                        evidence=[]
                    )
                ],
                errors=[],
                processing_time_seconds=1.0
            ),
            AgentAnalysisResult(
                agent_id="agent2",
                batch_id="batch2",
                status=AnalysisStatus.COMPLETED,
                relationships=[
                    DetectedRelationship(
                        person_a="Alice",
                        person_b="Danny",
                        relationship_type=RelationshipType.COLLEAGUE,
                        strength=0.75,
                        context="Co-workers",
                        discovered_at=now,
                        last_updated=now,
                        confidence=0.65,
                        evidence_count=1,
                        evidence=[]
                    )
                ],
                errors=[],
                processing_time_seconds=1.2
            )
        ]
        
        aggregated = analyzer._aggregate_results(agent_results)
        
        assert len(aggregated) == 1
        assert aggregated[0].person_a == "Alice"
        assert aggregated[0].person_b == "Danny"
        assert aggregated[0].relationship_type == RelationshipType.COLLEAGUE
        assert 0.7 < aggregated[0].avg_strength < 0.8  # Average of 0.8 and 0.75
        assert aggregated[0].evidence_count == 2
    
    def test_resolve_conflicts(self, analyzer):
        """Test conflict resolution."""
        now = datetime.now(timezone.utc)
        
        aggregated = [
            AggregatedRelationship(
                person_a="Alice",
                person_b="Danny",
                relationship_type=RelationshipType.UNKNOWN,
                avg_strength=0.5,
                max_strength=0.5,
                min_strength=0.5,
                confidence=0.4,
                evidence_count=2,
                conflicting_assessments=1,
                discovered_at=now,
                last_updated=now,
                all_evidence=[],
                agent_votes={"unknown": 1, "friend": 1}
            )
        ]
        
        resolved, conflict_count = analyzer._resolve_conflicts(aggregated)
        
        assert conflict_count == 1
        # Should resolve to FRIEND since UNKNOWN is overridden
        assert resolved[0].relationship_type == RelationshipType.FRIEND
    
    def test_apply_resolution_rules_family_precedence(self, analyzer):
        """Test that family relationships take precedence."""
        now = datetime.now(timezone.utc)
        
        relationship = AggregatedRelationship(
            person_a="Alice",
            person_b="Danny",
            relationship_type=RelationshipType.COLLEAGUE,
            avg_strength=0.7,
            max_strength=0.8,
            min_strength=0.6,
            confidence=0.6,
            evidence_count=3,
            conflicting_assessments=1,
            discovered_at=now,
            last_updated=now,
            all_evidence=[],
            agent_votes={"colleague": 2, "family": 1}
        )
        
        resolved = analyzer._apply_resolution_rules(relationship)
        
        # Family has 1 vote which is 33%, below the 40% threshold
        # So it should stay as COLLEAGUE
        assert resolved.relationship_type == RelationshipType.COLLEAGUE


# =============================================================================
# RelationshipManager Tests
# =============================================================================

class TestRelationshipManager:
    """Tests for RelationshipManager."""
    
    @pytest.fixture
    def mock_driver(self):
        """Create a mock Neo4j driver."""
        mock = MagicMock()
        mock.session.return_value.__enter__ = Mock(return_value=MagicMock())
        mock.session.return_value.__exit__ = Mock(return_value=False)
        return mock
    
    @pytest.fixture
    def manager(self, mock_driver):
        """Create a RelationshipManager with mocked driver."""
        with patch('neo4j.GraphDatabase.driver', return_value=mock_driver):
            manager = RelationshipManager(
                neo4j_password="test_password",
                primary_human="Danny"
            )
            manager._driver = mock_driver
            manager._initialized = True
            return manager
    
    def test_initialization(self, manager):
        """Test manager initialization."""
        assert manager._initialized
        assert manager.primary_human == "Danny"
    
    def test_record_relationship(self, manager):
        """Test recording a relationship."""
        result = manager.record_relationship(
            person_a_id="alice",
            person_b_id="danny",
            relationship_type=RelationshipType.FRIEND,
            strength=0.8,
            context="Long-time friends",
            confidence=0.9
        )
        
        assert result is True
        # Verify the query was executed
        assert manager._driver.session.called
    
    def test_get_relationship(self, manager):
        """Test retrieving a relationship."""
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {
            "relationship": {
                "person_a": "Alice",
                "person_b": "Danny",
                "type": "friend",
                "strength": 0.8,
                "confidence": 0.9
            }
        }
        mock_session.run.return_value = mock_result
        
        with patch.object(manager._driver, 'session', return_value=mock_session):
            rel = manager.get_relationship("alice", "danny")
        
        assert rel is not None
        assert rel["type"] == "friend"
        assert rel["strength"] == 0.8
    
    def test_get_person_relationships(self, manager):
        """Test getting all relationships for a person."""
        mock_session = MagicMock()
        mock_result = [
            MagicMock(**{"__getitem__": lambda s, k: {
                "relationship": {
                    "person": "Bob",
                    "type": "colleague",
                    "strength": 0.7
                }
            }[k]})
        ]
        mock_session.run.return_value = mock_result
        
        with patch.object(manager._driver, 'session', return_value=mock_session):
            rels = manager.get_person_relationships("alice", min_strength=0.5)
        
        assert isinstance(rels, list)
    
    def test_update_relationship_strength(self, manager):
        """Test updating relationship strength."""
        result = manager.update_relationship_strength(
            person_a_id="alice",
            person_b_id="danny",
            strength_delta=0.1
        )
        
        assert result is True
        assert manager._driver.session.called


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the full relationship system."""
    
    def test_end_to_end_conversation_analysis(self):
        """Test complete flow from conversation to stored relationship."""
        # This test uses mocked Neo4j and doesn't require a real database
        
        conversations = [
            {
                "text": "Danny is my business partner. We co-founded Kurultai.",
                "speaker_id": "alice",
                "speaker_name": "Alice",
                "timestamp": datetime.now(timezone.utc)
            },
            {
                "text": "I've known Danny for years. He's a good friend.",
                "speaker_id": "bob",
                "speaker_name": "Bob",
                "timestamp": datetime.now(timezone.utc)
            },
            {
                "text": "My mentor Danny has been guiding my career.",
                "speaker_id": "carol",
                "speaker_name": "Carol",
                "timestamp": datetime.now(timezone.utc)
            }
        ]
        
        # Analyze with horde pattern
        result = analyze_relationships_horde(
            conversations=conversations,
            primary_human="Danny",
            batch_size=2,
            focus_on_primary=True
        )
        
        assert result.status == AnalysisStatus.COMPLETED
        assert len(result.primary_human_relationships) >= 1
        
        # Check that we found relationships
        person_names = [
            rel.person_a if rel.person_b == "Danny" else rel.person_b
            for rel in result.primary_human_relationships
        ]
        
        assert any(name in person_names for name in ["Alice", "Bob", "Carol"])
    
    def test_relationship_type_detection_accuracy(self):
        """Test that relationship types are detected correctly."""
        test_cases = [
            ("My brother Danny helped me.", RelationshipType.FAMILY),
            ("Danny is my colleague at work.", RelationshipType.COLLEAGUE),
            ("Danny and I co-founded the company.", RelationshipType.BUSINESS_PARTNER),
            ("Danny has been mentoring me.", RelationshipType.MENTOR),
            ("Danny is my best friend.", RelationshipType.FRIEND),
        ]
        
        detector = RelationshipDetector(primary_human="Danny")
        
        for text, expected_type in test_cases:
            rel = detector.analyze_for_primary_human(
                conversation_text=text,
                other_person="TestSpeaker"
            )
            
            assert rel is not None, f"No relationship detected for: {text}"
            assert rel.relationship_type == expected_type, \
                f"Expected {expected_type.value} but got {rel.relationship_type.value} for: {text}"


# =============================================================================
# Performance Tests
# =============================================================================

class TestPerformance:
    """Performance tests for the relationship system."""
    
    def test_large_batch_processing(self):
        """Test processing a large batch of conversations."""
        conversations = [
            {
                "text": f"Conversation {i} with Danny. He's my colleague.",
                "speaker_id": f"user_{i % 10}",  # 10 unique speakers
                "speaker_name": f"User {i % 10}",
                "timestamp": datetime.now(timezone.utc)
            }
            for i in range(100)
        ]
        
        import time
        start = time.time()
        
        result = analyze_relationships_horde(
            conversations=conversations,
            primary_human="Danny",
            batch_size=20,
            focus_on_primary=True
        )
        
        elapsed = time.time() - start
        
        assert result.status == AnalysisStatus.COMPLETED
        assert elapsed < 60  # Should complete in under 60 seconds
        print(f"Processed 100 conversations in {elapsed:.2f}s")


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_empty_conversation(self):
        """Test handling of empty conversation."""
        detector = RelationshipDetector()
        
        relationships = detector.analyze_conversation(
            conversation_text="",
            speaker_id="test"
        )
        
        assert len(relationships) == 0
    
    def test_no_people_mentioned(self):
        """Test conversation with no person mentions."""
        detector = RelationshipDetector()
        
        relationships = detector.analyze_conversation(
            conversation_text="The weather is nice today.",
            speaker_id="test"
        )
        
        assert len(relationships) == 0
    
    def test_self_reference(self):
        """Test that speaker doesn't get relationship with themselves."""
        detector = RelationshipDetector()
        
        relationships = detector.analyze_conversation(
            conversation_text="I, Alice, am working on this alone.",
            speaker_id="alice",
            speaker_name="Alice"
        )
        
        # Should not have a relationship with self
        self_rels = [r for r in relationships if r.person_b.lower() == "alice"]
        assert len(self_rels) == 0
    
    def test_multiple_relationship_types_in_context(self):
        """Test when multiple relationship indicators are present."""
        detector = RelationshipDetector(primary_human="Danny")
        
        # Both friend and colleague indicators present
        text = "Danny is my colleague at work but also a good friend."
        
        rel = detector.analyze_for_primary_human(
            conversation_text=text,
            other_person="Speaker"
        )
        
        assert rel is not None
        # Should pick one based on strongest signal
        assert rel.relationship_type in [RelationshipType.FRIEND, RelationshipType.COLLEAGUE]
    
    def test_very_long_conversation(self):
        """Test handling of very long conversation text."""
        detector = RelationshipDetector(primary_human="Danny")
        
        long_text = "Danny is my colleague. " * 1000  # Very long text
        
        rel = detector.analyze_for_primary_human(
            conversation_text=long_text,
            other_person="Speaker"
        )
        
        assert rel is not None
        assert rel.relationship_type == RelationshipType.COLLEAGUE


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
