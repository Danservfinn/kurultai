"""Relationship Manager - Integration with Identity Manager for relationship tracking.

This module extends the identity system with relationship capabilities:
- Store and retrieve relationships from Neo4j
- Track relationships to primary human (Danny)
- Integrate with RelationshipDetector and RelationshipAnalyzer
- Provide relationship context for conversations
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tools.identity_manager import IdentityManager, PersonIdentity
from tools.relationship_detector import (
    RelationshipDetector, 
    RelationshipType,
    DetectedRelationship
)
from tools.relationship_analyzer import (
    RelationshipAnalyzer,
    AggregatedRelationship,
    analyze_relationships_horde
)

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class RelationshipContext:
    """Context about a person's relationships."""
    person: PersonIdentity
    relationships: List[AggregatedRelationship]
    relationship_to_primary: Optional[AggregatedRelationship]
    shared_contexts: List[str]
    communication_patterns: Dict[str, Any]


class RelationshipManager:
    """
    Manages relationships between people in the identity system.
    
    Integrates with:
    - IdentityManager for person data
    - RelationshipDetector for single conversation analysis
    - RelationshipAnalyzer for batch/horde analysis
    - Neo4j for persistent storage
    """
    
    def __init__(
        self,
        identity_manager: Optional[IdentityManager] = None,
        neo4j_uri: str = "bolt://localhost:7687",
        neo4j_username: str = "neo4j",
        neo4j_password: Optional[str] = None,
        database: str = "neo4j",
        primary_human: str = "Danny"
    ):
        self.identity_manager = identity_manager
        self.neo4j_uri = neo4j_uri
        self.neo4j_username = neo4j_username
        self.neo4j_password = neo4j_password
        self.database = database
        self.primary_human = primary_human
        
        self._detector = RelationshipDetector(primary_human=primary_human)
        self._analyzer = RelationshipAnalyzer(
            neo4j_uri=neo4j_uri,
            neo4j_username=neo4j_username,
            neo4j_password=neo4j_password,
            database=database,
            primary_human=primary_human
        )
        
        self._driver = None
        self._initialized = False
        
    def initialize(self) -> bool:
        """Initialize the relationship manager."""
        # Initialize analyzer
        self._analyzer.initialize()
        
        # Connect to Neo4j if we have credentials
        if self.neo4j_password:
            try:
                from neo4j import GraphDatabase
                self._driver = GraphDatabase.driver(
                    self.neo4j_uri,
                    auth=(self.neo4j_username, self.neo4j_password)
                )
                self._driver.verify_connectivity()
                self._initialized = True
                logger.info("RelationshipManager initialized with Neo4j")
                return True
            except Exception as e:
                logger.warning(f"Neo4j connection failed: {e}")
        
        self._initialized = True
        logger.info("RelationshipManager initialized (memory-only mode)")
        return True
    
    def close(self):
        """Close connections."""
        self._analyzer.close()
        if self._driver:
            self._driver.close()
            self._driver = None
    
    # ===================================================================
    # Core Relationship Operations
    # ===================================================================
    
    def record_relationship(
        self,
        person_a_id: str,
        person_b_id: str,
        relationship_type: RelationshipType,
        strength: float = 0.5,
        context: str = "",
        confidence: float = 0.5,
        source: str = "detection"
    ) -> bool:
        """
        Record a relationship between two people.
        
        Args:
            person_a_id: First person's ID
            person_b_id: Second person's ID
            relationship_type: Type of relationship
            strength: Relationship strength (0.0-1.0)
            context: Context description
            confidence: Confidence in this relationship
            source: Source of the detection
            
        Returns:
            True if successful
        """
        if not self._driver:
            logger.warning("No Neo4j connection, cannot store relationship")
            return False
        
        now = datetime.now(timezone.utc)
        
        try:
            with self._driver.session(database=self.database) as session:
                session.run("""
                    MERGE (p1:Person {id: $person_a_id})
                    MERGE (p2:Person {id: $person_b_id})
                    MERGE (p1)-[r:KNOWS]-(p2)
                    ON CREATE SET
                        r.type = $rel_type,
                        r.strength = $strength,
                        r.context = $context,
                        r.discovered_at = $now,
                        r.last_updated = $now,
                        r.confidence = $confidence,
                        r.evidence_count = 1,
                        r.source = $source
                    ON MATCH SET
                        r.strength = CASE
                            WHEN r.strength IS NULL THEN $strength
                            ELSE (r.strength * 0.7 + $strength * 0.3)
                        END,
                        r.last_updated = $now,
                        r.confidence = CASE
                            WHEN r.confidence IS NULL THEN $confidence
                            ELSE (r.confidence * 0.9 + $confidence * 0.1)
                        END,
                        r.evidence_count = COALESCE(r.evidence_count, 0) + 1
                """,
                    person_a_id=person_a_id,
                    person_b_id=person_b_id,
                    rel_type=relationship_type.value,
                    strength=round(strength, 2),
                    context=context[:500],  # Limit context length
                    confidence=round(confidence, 2),
                    source=source,
                    now=now
                )
            
            logger.debug(f"Recorded relationship: {person_a_id} -> {person_b_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to record relationship: {e}")
            return False
    
    def get_relationship(
        self,
        person_a_id: str,
        person_b_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get relationship between two people.
        
        Args:
            person_a_id: First person's ID
            person_b_id: Second person's ID
            
        Returns:
            Relationship dict or None
        """
        if not self._driver:
            return None
        
        try:
            with self._driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (p1:Person {id: $person_a_id})-[r:KNOWS]-(p2:Person {id: $person_b_id})
                    RETURN {
                        person_a: p1.name,
                        person_b: p2.name,
                        type: r.type,
                        strength: r.strength,
                        context: r.context,
                        discovered_at: r.discovered_at,
                        last_updated: r.last_updated,
                        confidence: r.confidence,
                        evidence_count: r.evidence_count
                    } as relationship
                """,
                    person_a_id=person_a_id,
                    person_b_id=person_b_id
                )
                
                record = result.single()
                if record:
                    return record["relationship"]
                return None
                
        except Exception as e:
            logger.error(f"Failed to get relationship: {e}")
            return None
    
    def get_person_relationships(
        self,
        person_id: str,
        min_strength: float = 0.0,
        relationship_type: Optional[RelationshipType] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all relationships for a person.
        
        Args:
            person_id: Person's ID
            min_strength: Minimum strength threshold
            relationship_type: Optional type filter
            
        Returns:
            List of relationship dicts
        """
        if not self._driver:
            return []
        
        try:
            with self._driver.session(database=self.database) as session:
                # Build query based on filters
                type_filter = "AND r.type = $rel_type" if relationship_type else ""
                
                result = session.run(f"""
                    MATCH (p:Person {{id: $person_id}})-[r:KNOWS]-(other:Person)
                    WHERE r.strength >= $min_strength {type_filter}
                    RETURN {{
                        person: other.name,
                        person_id: other.id,
                        type: r.type,
                        strength: r.strength,
                        context: r.context,
                        last_updated: r.last_updated,
                        confidence: r.confidence
                    }} as relationship
                    ORDER BY r.strength DESC
                """,
                    person_id=person_id,
                    min_strength=min_strength,
                    rel_type=relationship_type.value if relationship_type else None
                )
                
                return [record["relationship"] for record in result]
                
        except Exception as e:
            logger.error(f"Failed to get person relationships: {e}")
            return []
    
    def get_relationship_to_primary(
        self,
        person_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a person's relationship to the primary human.
        
        Args:
            person_id: Person's ID
            
        Returns:
            Relationship dict or None
        """
        # First try to find by ID with primary human prefix
        primary_ids = [
            f"signal:{self.primary_human}",
            f"discord:{self.primary_human}",
            f"slack:{self.primary_human}",
            self.primary_human
        ]
        
        for primary_id in primary_ids:
            rel = self.get_relationship(person_id, primary_id)
            if rel:
                return rel
        
        # Try by name lookup
        if not self._driver:
            return None
            
        try:
            with self._driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (p:Person {id: $person_id})-[r:KNOWS]-(primary:Person)
                    WHERE primary.name = $primary_name
                       OR primary.id CONTAINS $primary_name
                    RETURN {
                        person: p.name,
                        primary: primary.name,
                        type: r.type,
                        strength: r.strength,
                        context: r.context,
                        confidence: r.confidence
                    } as relationship
                """,
                    person_id=person_id,
                    primary_name=self.primary_human
                )
                
                record = result.single()
                if record:
                    return record["relationship"]
                return None
                
        except Exception as e:
            logger.error(f"Failed to get relationship to primary: {e}")
            return None
    
    # ===================================================================
    # Detection and Analysis Integration
    # ===================================================================
    
    def analyze_and_record(
        self,
        conversation_text: str,
        speaker_id: str,
        speaker_name: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> List[DetectedRelationship]:
        """
        Analyze a conversation and record any detected relationships.
        
        Args:
            conversation_text: Text to analyze
            speaker_id: Speaker's person ID
            speaker_name: Speaker's display name
            conversation_id: Optional conversation identifier
            
        Returns:
            List of recorded relationships
        """
        # Detect relationships
        detected = self._detector.analyze_conversation(
            conversation_text=conversation_text,
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            conversation_id=conversation_id
        )
        
        # Record each detected relationship
        recorded = []
        for rel in detected:
            # Try to get or create the other person
            other_id = rel.person_b
            if self.identity_manager:
                person = self.identity_manager.get_or_create_person(
                    channel="detected",
                    handle=other_id,
                    name=other_id
                )
                other_id = person.id
            
            success = self.record_relationship(
                person_a_id=speaker_id,
                person_b_id=other_id,
                relationship_type=rel.relationship_type,
                strength=rel.strength,
                context=rel.context,
                confidence=rel.confidence,
                source=f"detection:{conversation_id or 'unknown'}"
            )
            
            if success:
                recorded.append(rel)
        
        return recorded
    
    def analyze_conversation_batch(
        self,
        conversations: List[Dict[str, Any]],
        focus_on_primary: bool = True
    ) -> List[AggregatedRelationship]:
        """
        Analyze a batch of conversations using the horde pattern.
        
        Args:
            conversations: List of conversation dicts
            focus_on_primary: Whether to focus on primary human relationships
            
        Returns:
            List of aggregated relationships
        """
        result = self._analyzer.analyze_conversations_horde(
            conversations=conversations,
            focus_on_primary=focus_on_primary
        )
        
        # Store the aggregated relationships
        for rel in result.aggregated_relationships:
            self._store_aggregated_relationship(rel)
        
        return result.aggregated_relationships
    
    def update_relationship_strength(
        self,
        person_a_id: str,
        person_b_id: str,
        strength_delta: float
    ) -> bool:
        """
        Update relationship strength based on new interaction.
        
        Args:
            person_a_id: First person's ID
            person_b_id: Second person's ID
            strength_delta: Change in strength (-1.0 to 1.0)
            
        Returns:
            True if successful
        """
        if not self._driver:
            return False
        
        try:
            with self._driver.session(database=self.database) as session:
                session.run("""
                    MATCH (p1:Person {id: $person_a_id})-[r:KNOWS]-(p2:Person {id: $person_b_id})
                    SET r.strength = CASE
                        WHEN r.strength IS NULL THEN 0.5 + $delta
                        ELSE r.strength + $delta
                    END,
                    r.strength = CASE
                        WHEN r.strength > 1.0 THEN 1.0
                        WHEN r.strength < 0.0 THEN 0.0
                        ELSE r.strength
                    END,
                    r.last_updated = datetime()
                """,
                    person_a_id=person_a_id,
                    person_b_id=person_b_id,
                    delta=strength_delta
                )
            return True
        except Exception as e:
            logger.error(f"Failed to update relationship strength: {e}")
            return False
    
    # ===================================================================
    # Context Building
    # ===================================================================
    
    def get_relationship_context(
        self,
        person_id: str
    ) -> Optional[RelationshipContext]:
        """
        Build comprehensive relationship context for a person.
        
        Args:
            person_id: Person's ID
            
        Returns:
            RelationshipContext or None
        """
        # Get person identity
        person = None
        if self.identity_manager:
            person = self.identity_manager.get_person(person_id)
        
        if not person:
            person = PersonIdentity(
                id=person_id,
                name=person_id,
                handle=person_id,
                channel="unknown"
            )
        
        # Get all relationships
        relationships_data = self.get_person_relationships(person_id)
        relationships = [
            AggregatedRelationship(
                person_a=person_id,
                person_b=r["person"],
                relationship_type=RelationshipType(r["type"]),
                avg_strength=r["strength"],
                max_strength=r["strength"],
                min_strength=r["strength"],
                confidence=r["confidence"],
                evidence_count=1,
                conflicting_assessments=0,
                discovered_at=datetime.now(timezone.utc),
                last_updated=r.get("last_updated", datetime.now(timezone.utc)),
                all_evidence=[],
                agent_votes={r["type"]: 1}
            )
            for r in relationships_data
        ]
        
        # Get relationship to primary
        rel_to_primary_data = self.get_relationship_to_primary(person_id)
        rel_to_primary = None
        if rel_to_primary_data:
            rel_to_primary = AggregatedRelationship(
                person_a=person_id,
                person_b=self.primary_human,
                relationship_type=RelationshipType(rel_to_primary_data["type"]),
                avg_strength=rel_to_primary_data["strength"],
                max_strength=rel_to_primary_data["strength"],
                min_strength=rel_to_primary_data["strength"],
                confidence=rel_to_primary_data["confidence"],
                evidence_count=1,
                conflicting_assessments=0,
                discovered_at=datetime.now(timezone.utc),
                last_updated=rel_to_primary_data.get(
                    "last_updated", 
                    datetime.now(timezone.utc)
                ),
                all_evidence=[],
                agent_votes={rel_to_primary_data["type"]: 1}
            )
        
        # Extract shared contexts from relationship data
        shared_contexts = list(set(
            r.get("context", "")
            for r in relationships_data
            if r.get("context")
        ))[:10]
        
        # Build communication patterns
        communication_patterns = {
            "total_relationships": len(relationships),
            "strong_relationships": sum(
                1 for r in relationships if r.avg_strength > 0.7
            ),
            "primary_human_known": rel_to_primary is not None,
            "relationship_types": list(set(
                r.relationship_type.value for r in relationships
            ))
        }
        
        return RelationshipContext(
            person=person,
            relationships=relationships,
            relationship_to_primary=rel_to_primary,
            shared_contexts=shared_contexts,
            communication_patterns=communication_patterns
        )
    
    # ===================================================================
    # Statistics and Reporting
    # ===================================================================
    
    def get_relationship_stats(self) -> Dict[str, Any]:
        """Get statistics about tracked relationships."""
        if not self._driver:
            return {"error": "No Neo4j connection"}
        
        try:
            with self._driver.session(database=self.database) as session:
                # Count by type
                type_result = session.run("""
                    MATCH ()-[r:KNOWS]-()
                    RETURN r.type as type, count(*) as count
                    ORDER BY count DESC
                """)
                by_type = {r["type"]: r["count"] for r in type_result}
                
                # Average strength
                strength_result = session.run("""
                    MATCH ()-[r:KNOWS]-()
                    RETURN avg(r.strength) as avg_strength,
                           max(r.strength) as max_strength,
                           min(r.strength) as min_strength
                """)
                strength_stats = strength_result.single()
                
                # Relationships to primary human
                primary_result = session.run("""
                    MATCH (p:Person)-[r:KNOWS]-(primary:Person)
                    WHERE primary.name = $primary_name
                       OR primary.id CONTAINS $primary_name
                    RETURN count(*) as count
                """, primary_name=self.primary_human)
                primary_count = primary_result.single()["count"]
                
                return {
                    "total_relationships": sum(by_type.values()),
                    "by_type": by_type,
                    "avg_strength": round(strength_stats["avg_strength"] or 0, 2),
                    "max_strength": round(strength_stats["max_strength"] or 0, 2),
                    "min_strength": round(strength_stats["min_strength"] or 0, 2),
                    "primary_human_relationships": primary_count,
                    "primary_human_name": self.primary_human
                }
                
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {"error": str(e)}
    
    def find_common_connections(
        self,
        person_a_id: str,
        person_b_id: str
    ) -> List[Dict[str, Any]]:
        """
        Find people who know both person A and person B.
        
        Args:
            person_a_id: First person's ID
            person_b_id: Second person's ID
            
        Returns:
            List of common connections
        """
        if not self._driver:
            return []
        
        try:
            with self._driver.session(database=self.database) as session:
                result = session.run("""
                    MATCH (a:Person {id: $person_a_id})-[:KNOWS]-(common:Person)-[:KNOWS]-(b:Person {id: $person_b_id})
                    WHERE common.id <> $person_a_id AND common.id <> $person_b_id
                    RETURN common.name as name,
                           common.id as id,
                           count(*) as connection_strength
                    ORDER BY connection_strength DESC
                """,
                    person_a_id=person_a_id,
                    person_b_id=person_b_id
                )
                
                return [
                    {"name": r["name"], "id": r["id"], "strength": r["connection_strength"]}
                    for r in result
                ]
                
        except Exception as e:
            logger.error(f"Failed to find common connections: {e}")
            return []
    
    # ===================================================================
    # Private Helpers
    # ===================================================================
    
    def _store_aggregated_relationship(self, rel: AggregatedRelationship):
        """Store an aggregated relationship in Neo4j."""
        if not self._driver:
            return
        
        try:
            with self._driver.session(database=self.database) as session:
                session.run("""
                    MERGE (p1:Person {id: $person_a})
                    MERGE (p2:Person {id: $person_b})
                    MERGE (p1)-[r:KNOWS]-(p2)
                    ON CREATE SET
                        r.type = $rel_type,
                        r.strength = $strength,
                        r.confidence = $confidence,
                        r.evidence_count = $evidence_count,
                        r.discovered_at = $discovered_at,
                        r.last_updated = $last_updated
                    ON MATCH SET
                        r.strength = CASE
                            WHEN r.strength IS NULL THEN $strength
                            WHEN $strength > r.strength THEN $strength
                            ELSE (r.strength * 0.8 + $strength * 0.2)
                        END,
                        r.confidence = CASE
                            WHEN r.confidence IS NULL THEN $confidence
                            ELSE (r.confidence * 0.9 + $confidence * 0.1)
                        END,
                        r.evidence_count = COALESCE(r.evidence_count, 0) + $evidence_count,
                        r.last_updated = $last_updated
                """,
                    person_a=rel.person_a,
                    person_b=rel.person_b,
                    rel_type=rel.relationship_type.value,
                    strength=rel.avg_strength,
                    confidence=rel.confidence,
                    evidence_count=rel.evidence_count,
                    discovered_at=rel.discovered_at,
                    last_updated=rel.last_updated
                )
        except Exception as e:
            logger.warning(f"Failed to store aggregated relationship: {e}")


# =============================================================================
# Integration with KurultaiIdentitySystem
# =============================================================================

def extend_identity_system_with_relationships(identity_system):
    """
    Extend a KurultaiIdentitySystem with relationship capabilities.
    
    Args:
        identity_system: KurultaiIdentitySystem instance
        
    Returns:
        RelationshipManager instance
    """
    rel_manager = RelationshipManager(
        identity_manager=identity_system.identity,
        neo4j_uri=identity_system.neo4j_uri,
        neo4j_username=identity_system.neo4j_username,
        neo4j_password=identity_system.neo4j_password,
        database=identity_system.database
    )
    rel_manager.initialize()
    return rel_manager


# =============================================================================
# Convenience Functions
# =============================================================================

def get_person_network(
    person_id: str,
    depth: int = 1,
    min_strength: float = 0.3
) -> Dict[str, Any]:
    """
    Get a person's relationship network.
    
    Args:
        person_id: Person's ID
        depth: How many hops to traverse (1 = direct connections)
        min_strength: Minimum relationship strength
        
    Returns:
        Network dict with nodes and edges
    """
    manager = RelationshipManager()
    manager.initialize()
    
    try:
        if not manager._driver:
            return {"error": "No database connection"}
        
        with manager._driver.session() as session:
            # Get network up to specified depth
            result = session.run("""
                MATCH path = (center:Person {id: $person_id})-[:KNOWS*1..$depth]-(connected:Person)
                WHERE ALL(r IN relationships(path) WHERE r.strength >= $min_strength)
                RETURN center, connected, relationships(path) as rels
                LIMIT 100
            """,
                person_id=person_id,
                depth=depth,
                min_strength=min_strength
            )
            
            nodes = {}
            edges = []
            
            for record in result:
                center = record["center"]
                connected = record["connected"]
                rels = record["rels"]
                
                nodes[center["id"]] = {"id": center["id"], "name": center.get("name")}
                nodes[connected["id"]] = {"id": connected["id"], "name": connected.get("name")}
                
                for rel in rels:
                    edges.append({
                        "source": center["id"],
                        "target": connected["id"],
                        "type": rel.get("type"),
                        "strength": rel.get("strength")
                    })
            
            return {
                "nodes": list(nodes.values()),
                "edges": edges,
                "center": person_id
            }
            
    finally:
        manager.close()


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Example usage
    manager = RelationshipManager(primary_human="Danny")
    manager.initialize()
    
    # Record some relationships
    manager.record_relationship(
        person_a_id="signal:alice",
        person_b_id="signal:danny",
        relationship_type=RelationshipType.COLLEAGUE,
        strength=0.8,
        context="Work together on Kurultai project",
        confidence=0.9
    )
    
    manager.record_relationship(
        person_a_id="signal:bob",
        person_b_id="signal:danny",
        relationship_type=RelationshipType.FRIEND,
        strength=0.9,
        context="Long-time friends from college",
        confidence=0.85
    )
    
    # Get relationships
    print("\nDanny's relationships:")
    rels = manager.get_person_relationships("signal:danny")
    for rel in rels:
        print(f"  - {rel['person']}: {rel['type']} (strength: {rel['strength']})")
    
    # Get stats
    print("\nRelationship stats:")
    stats = manager.get_relationship_stats()
    print(f"  Total: {stats.get('total_relationships')}")
    print(f"  By type: {stats.get('by_type')}")
    
    manager.close()
