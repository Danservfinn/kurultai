"""Relationship Detector - Analyze conversations for relationship clues.

This module provides relationship detection from conversations:
- Extract mentions of other people
- Infer relationship type from context
- Track relationship strength over time
- Detect relationship changes
"""

import re
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum

# Configure logging
logger = logging.getLogger(__name__)


class RelationshipType(Enum):
    """Types of relationships between people."""
    FRIEND = "friend"                    # Personal connection
    COLLEAGUE = "colleague"              # Professional connection
    FAMILY = "family"                    # Family member
    BUSINESS_PARTNER = "business_partner"  # Business relationship
    MENTOR = "mentor"                    # Guidance provider
    MENTEE = "mentee"                    # Guidance recipient
    ACQUAINTANCE = "acquaintance"        # Casual connection
    UNKNOWN = "unknown"                  # Relationship unclear


@dataclass
class RelationshipClue:
    """A detected clue about a relationship."""
    person_name: str                     # Name of the related person
    relationship_type: RelationshipType  # Inferred type
    confidence: float                    # 0.0 to 1.0
    context: str                         # Text context
    indicators: List[str]                # Specific indicators found
    extracted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RelationshipEvidence:
    """Evidence supporting a relationship."""
    source_conversation: str             # ID or text of source
    timestamp: datetime
    clue: RelationshipClue
    supporting_text: str


@dataclass
class DetectedRelationship:
    """A detected relationship between two people."""
    person_a: str                        # Person ID or name
    person_b: str                        # Person ID or name
    relationship_type: RelationshipType
    strength: float                      # 0.0 to 1.0
    context: str
    discovered_at: datetime
    last_updated: datetime
    confidence: float
    evidence_count: int
    evidence: List[RelationshipEvidence] = field(default_factory=list)


class RelationshipDetector:
    """
    Detects relationships between people from conversation text.
    
    Uses pattern matching, NLP, and context analysis to identify:
    - Mentions of other people
    - Relationship indicators (keywords, phrases)
    - Strength signals (frequency, sentiment, detail level)
    """
    
    # Keywords indicating relationship types
    RELATIONSHIP_INDICATORS = {
        RelationshipType.FAMILY: [
            "mother", "father", "mom", "dad", "parent", "parents",
            "brother", "sister", "sibling", "siblings",
            "son", "daughter", "child", "children", "kid", "kids",
            "husband", "wife", "spouse", "married",
            "grandmother", "grandfather", "grandma", "grandpa", "grandparent",
            "uncle", "aunt", "cousin", "niece", "nephew",
            "family", "relative", "in-law", "in-laws"
        ],
        RelationshipType.COLLEAGUE: [
            "colleague", "coworker", "co-worker", "teammate", "team-mate",
            "boss", "manager", "supervisor", "director", "executive",
            "employee", "report", "reports to", "works under",
            "colleague at", "works with", "works at", "work with",
            "team member", "on my team", "our team", "my team",
            "office", "workplace", "company", "startup",
            "project with", "working on", "collaborate", "collaboration"
        ],
        RelationshipType.BUSINESS_PARTNER: [
            "co-founder", "cofounder", "founder", "partner",
            "business partner", "investor", "advisor", "board member",
            "stakeholder", "shareholder", "client", "customer",
            "vendor", "supplier", "contractor", "consultant",
            "deal with", "contract with", "partnership"
        ],
        RelationshipType.MENTOR: [
            "mentor", "mentored by", "learned from", "guided by",
            "advisor", "adviser", "coach", "taught me",
            "helped me grow", "career advice", "professional guidance"
        ],
        RelationshipType.MENTEE: [
            "mentee", "mentoring", "coaching", "advising",
            "my student", "I mentor", "I coach", "I advise",
            "helping them", "guiding them", "their career"
        ],
        RelationshipType.FRIEND: [
            "friend", "buddy", "pal", "best friend", "close friend",
            "old friend", "childhood friend", "college friend",
            "we hang out", "we go way back", "known each other",
            "friendship", "hang out", "get together", "catch up"
        ],
        RelationshipType.ACQUAINTANCE: [
            "acquaintance", "know of", "heard of", "met once",
            "briefly met", "ran into", "saw at", "someone I know",
            "not close", "don't know well", "casual"
        ]
    }
    
    # Pronouns and possessives that indicate relationship
    POSSESSIVE_PATTERNS = [
        r"my\s+(\w+)",
        r"(\w+)\s+and\s+I",
        r"I\s+and\s+(\w+)",
        r"with\s+(\w+)",
        r"(\w+)'s\s+(?:\w+\s+)?(?:idea|thought|opinion|advice)"
    ]
    
    # Name extraction patterns
    NAME_PATTERNS = [
        r"(?:^|\s)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",  # Capitalized names
        r"@(\w+)",  # @mentions
    ]
    
    # Strength indicators
    STRENGTH_SIGNALS = {
        "high": [
            "best", "closest", "dear", "dearest", "love",
            "always", "everything", "would do anything",
            "trust completely", "know everything"
        ],
        "medium": [
            "often", "regularly", "usually", "good", "solid",
            "respect", "appreciate", "rely on"
        ],
        "low": [
            "sometimes", "occasionally", "rarely", "used to",
            "not close", "distant", "lost touch"
        ]
    }
    
    def __init__(self, primary_human: str = "Danny"):
        """
        Initialize the relationship detector.
        
        Args:
            primary_human: The primary person's name (default: Danny)
        """
        self.primary_human = primary_human
        self._name_cache: Dict[str, str] = {}  # Cache for normalized names
        
    def analyze_conversation(
        self,
        conversation_text: str,
        speaker_id: str,
        speaker_name: Optional[str] = None,
        conversation_id: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ) -> List[DetectedRelationship]:
        """
        Analyze a conversation for relationship clues.
        
        Args:
            conversation_text: The conversation text to analyze
            speaker_id: ID of the person speaking
            speaker_name: Display name of the speaker
            conversation_id: Optional conversation identifier
            timestamp: Optional conversation timestamp
            
        Returns:
            List of detected relationships
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
            
        speaker_name = speaker_name or speaker_id
        relationships: List[DetectedRelationship] = []
        
        # Extract mentions of other people
        mentioned_people = self._extract_people_mentions(conversation_text, speaker_name)
        
        for person_name in mentioned_people:
            # Analyze relationship to this person
            clue = self._analyze_relationship_clue(
                conversation_text, person_name, speaker_name
            )
            
            if clue.confidence > 0.3:  # Minimum confidence threshold
                evidence = RelationshipEvidence(
                    source_conversation=conversation_id or "unknown",
                    timestamp=timestamp,
                    clue=clue,
                    supporting_text=clue.context[:200]  # Truncate for storage
                )
                
                relationship = DetectedRelationship(
                    person_a=speaker_id,
                    person_b=person_name,
                    relationship_type=clue.relationship_type,
                    strength=clue.confidence,
                    context=clue.context[:500],
                    discovered_at=timestamp,
                    last_updated=timestamp,
                    confidence=clue.confidence,
                    evidence_count=1,
                    evidence=[evidence]
                )
                
                relationships.append(relationship)
                
                logger.debug(
                    f"Detected relationship: {speaker_name} -> {person_name} "
                    f"({clue.relationship_type.value}, confidence: {clue.confidence:.2f})"
                )
        
        return relationships
    
    def analyze_for_primary_human(
        self,
        conversation_text: str,
        other_person: str,
        conversation_id: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ) -> Optional[DetectedRelationship]:
        """
        Analyze a conversation specifically for relationship to primary human.
        
        Args:
            conversation_text: The conversation text
            other_person: Name/ID of the other person in the conversation
            conversation_id: Optional conversation identifier
            timestamp: Optional timestamp
            
        Returns:
            DetectedRelationship if found, None otherwise
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
            
        # Check if primary human is mentioned
        if not self._mentions_person(conversation_text, self.primary_human):
            return None
            
        # Analyze the relationship clue
        clue = self._analyze_relationship_clue(
            conversation_text, self.primary_human, other_person
        )
        
        if clue.confidence < 0.2:
            return None
            
        evidence = RelationshipEvidence(
            source_conversation=conversation_id or "unknown",
            timestamp=timestamp,
            clue=clue,
            supporting_text=clue.context[:200]
        )
        
        return DetectedRelationship(
            person_a=other_person,
            person_b=self.primary_human,
            relationship_type=clue.relationship_type,
            strength=clue.confidence,
            context=clue.context[:500],
            discovered_at=timestamp,
            last_updated=timestamp,
            confidence=clue.confidence,
            evidence_count=1,
            evidence=[evidence]
        )
    
    def _extract_people_mentions(
        self,
        text: str,
        exclude_name: str
    ) -> Set[str]:
        """
        Extract mentions of people in the text.
        
        Args:
            text: Text to analyze
            exclude_name: Name to exclude (the speaker)
            
        Returns:
            Set of detected person names
        """
        mentions: Set[str] = set()
        
        # Look for capitalized names (simple heuristic)
        # More sophisticated: use NER if available
        words = text.split()
        for i, word in enumerate(words):
            # Check for capitalized words that aren't sentence starts
            clean_word = re.sub(r'[^\w]', '', word)
            if (len(clean_word) > 2 and 
                clean_word[0].isupper() and 
                clean_word not in ["I", "The", "A", "An", "This", "That"]):
                
                # Check if it's not the start of a sentence
                if i == 0 or words[i-1].endswith((".", "!", "?", ":", ";")):
                    # Could be sentence start, but might still be a name
                    pass
                    
                # Look for full names (First Last)
                if i < len(words) - 1:
                    next_word = re.sub(r'[^\w]', '', words[i + 1])
                    if (len(next_word) > 2 and 
                        next_word[0].isupper() and 
                        next_word not in ["I", "The", "A", "An"]):
                        full_name = f"{clean_word} {next_word}"
                        if full_name.lower() != exclude_name.lower():
                            mentions.add(full_name)
                            continue
                
                if clean_word.lower() != exclude_name.lower():
                    mentions.add(clean_word)
        
        # Look for @mentions
        at_mentions = re.findall(r'@(\w+)', text)
        mentions.update(at_mentions)
        
        return mentions
    
    def _analyze_relationship_clue(
        self,
        text: str,
        target_person: str,
        source_person: str
    ) -> RelationshipClue:
        """
        Analyze text to determine relationship type and confidence.
        
        Args:
            text: Conversation text
            target_person: The person being described
            source_person: The person speaking
            
        Returns:
            RelationshipClue with analysis results
        """
        text_lower = text.lower()
        target_lower = target_person.lower()
        
        indicators_found: List[str] = []
        type_scores: Dict[RelationshipType, float] = {}
        
        # Find sentences mentioning the target person
        sentences = re.split(r'[.!?]+', text)
        relevant_sentences = [
            s for s in sentences 
            if target_lower in s.lower() or target_person in s
        ]
        context = " ".join(relevant_sentences[:2]) if relevant_sentences else text[:200]
        
        # Score each relationship type
        for rel_type, keywords in self.RELATIONSHIP_INDICATORS.items():
            score = 0.0
            matches = 0
            
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    matches += 1
                    # Check proximity to target person's name
                    keyword_positions = [m.start() for m in re.finditer(
                        re.escape(keyword), text_lower
                    )]
                    target_positions = [m.start() for m in re.finditer(
                        re.escape(target_lower), text_lower
                    )]
                    
                    # Boost score if keyword is near target name
                    for kp in keyword_positions:
                        for tp in target_positions:
                            distance = abs(kp - tp)
                            if distance < 50:  # Within 50 chars
                                score += 0.3
                            elif distance < 100:
                                score += 0.15
                            else:
                                score += 0.05
                                
                    indicators_found.append(keyword)
            
            if matches > 0:
                type_scores[rel_type] = min(score + matches * 0.1, 1.0)
        
        # Determine best relationship type
        if type_scores:
            best_type = max(type_scores, key=type_scores.get)
            base_confidence = type_scores[best_type]
        else:
            best_type = RelationshipType.ACQUAINTANCE
            base_confidence = 0.2
        
        # Adjust confidence based on strength signals
        strength_modifier = self._calculate_strength_modifier(text)
        final_confidence = min(base_confidence * (1 + strength_modifier), 1.0)
        
        return RelationshipClue(
            person_name=target_person,
            relationship_type=best_type,
            confidence=round(final_confidence, 2),
            context=context.strip(),
            indicators=list(set(indicators_found))[:10]  # Limit stored indicators
        )
    
    def _calculate_strength_modifier(self, text: str) -> float:
        """
        Calculate strength modifier based on signal words.
        
        Args:
            text: Text to analyze
            
        Returns:
            Modifier value (-0.3 to +0.3)
        """
        text_lower = text.lower()
        modifier = 0.0
        
        for signal in self.STRENGTH_SIGNALS["high"]:
            if signal in text_lower:
                modifier += 0.1
                
        for signal in self.STRENGTH_SIGNALS["low"]:
            if signal in text_lower:
                modifier -= 0.1
                
        return max(-0.3, min(0.3, modifier))
    
    def _mentions_person(self, text: str, person: str) -> bool:
        """Check if text mentions a specific person."""
        text_lower = text.lower()
        person_lower = person.lower()
        
        # Direct mention
        if person_lower in text_lower:
            return True
            
        # Check for variations
        name_parts = person_lower.split()
        if len(name_parts) > 1:
            # Check first name only
            if name_parts[0] in text_lower:
                return True
                
        return False
    
    def merge_relationships(
        self,
        existing: DetectedRelationship,
        new: DetectedRelationship
    ) -> DetectedRelationship:
        """
        Merge two relationship detections, updating strength and evidence.
        
        Args:
            existing: Previously detected relationship
            new: New detection to merge
            
        Returns:
            Merged relationship
        """
        # Combine evidence
        all_evidence = existing.evidence + new.evidence
        
        # Calculate new strength (exponential moving average)
        alpha = 0.3  # Weight for new evidence
        new_strength = (1 - alpha) * existing.strength + alpha * new.strength
        
        # Update confidence based on evidence count
        new_confidence = min(0.5 + len(all_evidence) * 0.05, 0.95)
        
        return DetectedRelationship(
            person_a=existing.person_a,
            person_b=existing.person_b,
            relationship_type=existing.relationship_type,  # Keep original type
            strength=round(new_strength, 2),
            context=existing.context,  # Keep original context
            discovered_at=existing.discovered_at,
            last_updated=datetime.now(timezone.utc),
            confidence=round(new_confidence, 2),
            evidence_count=len(all_evidence),
            evidence=all_evidence[-20:]  # Keep last 20 evidence items
        )


# =============================================================================
# Convenience Functions
# =============================================================================

def detect_relationships(
    conversation_text: str,
    speaker_id: str,
    speaker_name: Optional[str] = None,
    primary_human: str = "Danny"
) -> List[DetectedRelationship]:
    """
    Convenience function to detect relationships in a conversation.
    
    Args:
        conversation_text: Text to analyze
        speaker_id: ID of the speaker
        speaker_name: Display name of speaker
        primary_human: Name of primary human
        
    Returns:
        List of detected relationships
    """
    detector = RelationshipDetector(primary_human=primary_human)
    return detector.analyze_conversation(
        conversation_text=conversation_text,
        speaker_id=speaker_id,
        speaker_name=speaker_name
    )


def detect_relationship_to_primary(
    conversation_text: str,
    other_person: str,
    primary_human: str = "Danny"
) -> Optional[DetectedRelationship]:
    """
    Detect relationship specifically to primary human.
    
    Args:
        conversation_text: Text to analyze
        other_person: Name of other person
        primary_human: Name of primary human
        
    Returns:
        Detected relationship or None
    """
    detector = RelationshipDetector(primary_human=primary_human)
    return detector.analyze_for_primary_human(
        conversation_text=conversation_text,
        other_person=other_person
    )


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Example conversation
    conversation = """
    I've been working with Danny on the Kurultai project for about 6 months now.
    He's my business partner and we co-founded this together. 
    My mentor, Sarah, introduced us back in 2023.
    I also collaborate with Mike from the engineering team.
    """
    
    detector = RelationshipDetector(primary_human="Danny")
    
    relationships = detector.analyze_conversation(
        conversation_text=conversation,
        speaker_id="signal:+1234567890",
        speaker_name="Alice"
    )
    
    print(f"Detected {len(relationships)} relationships:")
    for rel in relationships:
        print(f"  - {rel.person_a} -> {rel.person_b}: "
              f"{rel.relationship_type.value} (strength: {rel.strength}, "
              f"confidence: {rel.confidence})")
    
    # Analyze for primary human specifically
    primary_rel = detector.analyze_for_primary_human(
        conversation_text=conversation,
        other_person="Alice"
    )
    
    if primary_rel:
        print(f"\nRelationship to {detector.primary_human}:")
        print(f"  - {primary_rel.relationship_type.value} "
              f"(strength: {primary_rel.strength})")
