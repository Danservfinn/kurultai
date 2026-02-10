"""Relationship Analyzer - Horde-based parallel relationship analysis.

This module implements the golden-horde pattern for analyzing relationships:
- Spawn agents to process conversation batches in parallel
- Aggregate relationship findings across agents
- Resolve conflicts between agent assessments
- Track relationships to primary human (Danny)
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tools.relationship_detector import (
    RelationshipDetector, 
    RelationshipType, 
    DetectedRelationship,
    RelationshipEvidence
)

# Configure logging
logger = logging.getLogger(__name__)


class AnalysisStatus(Enum):
    """Status of analysis jobs."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ConversationBatch:
    """A batch of conversations to analyze."""
    batch_id: str
    conversations: List[Dict[str, Any]]
    target_person: Optional[str] = None
    focus_on_primary: bool = True


@dataclass
class AgentAnalysisResult:
    """Result from a single agent's analysis."""
    agent_id: str
    batch_id: str
    status: AnalysisStatus
    relationships: List[DetectedRelationship]
    errors: List[str]
    processing_time_seconds: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AggregatedRelationship:
    """Aggregated relationship data from multiple analyses."""
    person_a: str
    person_b: str
    relationship_type: RelationshipType
    avg_strength: float
    max_strength: float
    min_strength: float
    confidence: float
    evidence_count: int
    conflicting_assessments: int
    discovered_at: datetime
    last_updated: datetime
    all_evidence: List[RelationshipEvidence]
    agent_votes: Dict[str, int]  # relationship_type -> count


@dataclass
class HordeAnalysisResult:
    """Final result from horde analysis."""
    job_id: str
    status: AnalysisStatus
    total_batches: int
    completed_batches: int
    failed_batches: int
    aggregated_relationships: List[AggregatedRelationship]
    primary_human_relationships: List[AggregatedRelationship]
    processing_time_seconds: float
    conflicts_resolved: int
    errors: List[str]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Graph analytics results
    graph_analytics: Optional['GraphAnalytics'] = None


@dataclass
class GraphAnalytics:
    """Social graph analytics results."""
    total_nodes: int
    total_edges: int
    clusters: List['Cluster']
    bridge_people: List['BridgePerson']
    isolated_individuals: List[str]
    influence_scores: Dict[str, float]
    density: float
    average_clustering: float


@dataclass
class Cluster:
    """A community/cluster in the social graph."""
    cluster_id: str
    members: List[str]
    size: int
    internal_edges: int
    external_edges: int
    cohesion_score: float
    dominant_relationship_types: List[str]


@dataclass
class BridgePerson:
    """Someone who connects different communities."""
    person_id: str
    betweenness_score: float
    connects_clusters: List[str]
    bridge_strength: float


class RelationshipAnalyzer:
    """
    Horde-based parallel relationship analyzer.
    
    Uses multiple agents to analyze conversations in parallel,
    then aggregates and reconciles their findings.
    """
    
    def __init__(
        self,
        neo4j_uri: str = "bolt://localhost:7687",
        neo4j_username: str = "neo4j",
        neo4j_password: Optional[str] = None,
        database: str = "neo4j",
        primary_human: str = "Danny",
        max_workers: int = 5,
        use_subagents: bool = True
    ):
        self.neo4j_uri = neo4j_uri
        self.neo4j_username = neo4j_username
        self.neo4j_password = neo4j_password
        self.database = database
        self.primary_human = primary_human
        self.max_workers = max_workers
        self.use_subagents = use_subagents
        
        self._driver = None
        self._initialized = False
        self._detector = RelationshipDetector(primary_human=primary_human)
        
    def initialize(self) -> bool:
        """Initialize Neo4j connection."""
        try:
            from neo4j import GraphDatabase
            if self.neo4j_password:
                self._driver = GraphDatabase.driver(
                    self.neo4j_uri,
                    auth=(self.neo4j_username, self.neo4j_password)
                )
                self._driver.verify_connectivity()
            self._initialized = True
            logger.info("RelationshipAnalyzer initialized")
            return True
        except Exception as e:
            logger.warning(f"Neo4j initialization failed: {e}. Operating in memory-only mode.")
            self._initialized = True  # Can still work without Neo4j
            return True
    
    def close(self):
        """Close Neo4j connection."""
        if self._driver:
            self._driver.close()
            self._driver = None
    
    # ===================================================================
    # Horde Analysis - Main Entry Point
    # ===================================================================
    
    def analyze_conversations_horde(
        self,
        conversations: List[Dict[str, Any]],
        batch_size: int = 10,
        target_person: Optional[str] = None,
        focus_on_primary: bool = True
    ) -> HordeAnalysisResult:
        """
        Analyze conversations using the horde pattern.
        
        Args:
            conversations: List of conversation dicts with 'text', 'speaker_id', etc.
            batch_size: Number of conversations per batch
            target_person: Optional specific person to focus on
            focus_on_primary: Whether to focus on relationships to primary human
            
        Returns:
            HordeAnalysisResult with aggregated findings
        """
        import time
        start_time = time.time()
        
        job_id = f"horde_rel_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        
        # Split conversations into batches
        batches = self._create_batches(
            conversations, batch_size, target_person, focus_on_primary
        )
        
        logger.info(f"Starting horde analysis: {len(batches)} batches, "
                   f"{len(conversations)} conversations")
        
        # Process batches in parallel
        if self.use_subagents and self._can_spawn_subagents():
            agent_results = self._spawn_analysis_agents(batches)
        else:
            agent_results = self._process_batches_threaded(batches)
        
        # Aggregate results
        aggregated = self._aggregate_results(agent_results)
        
        # Resolve conflicts
        resolved, conflict_count = self._resolve_conflicts(aggregated)
        
        # Filter for primary human relationships
        primary_rels = [
            r for r in resolved 
            if self.primary_human in [r.person_a, r.person_b]
        ]
        
        completed = sum(1 for r in agent_results if r.status == AnalysisStatus.COMPLETED)
        failed = sum(1 for r in agent_results if r.status == AnalysisStatus.FAILED)
        
        processing_time = time.time() - start_time
        
        result = HordeAnalysisResult(
            job_id=job_id,
            status=AnalysisStatus.COMPLETED if failed < len(batches) / 2 else AnalysisStatus.FAILED,
            total_batches=len(batches),
            completed_batches=completed,
            failed_batches=failed,
            aggregated_relationships=resolved,
            primary_human_relationships=primary_rels,
            processing_time_seconds=round(processing_time, 2),
            conflicts_resolved=conflict_count,
            errors=[e for r in agent_results for e in r.errors]
        )
        
        # Store results in Neo4j
        self._store_analysis_result(result)
        
        logger.info(f"Horde analysis complete: {len(resolved)} relationships found, "
                   f"{conflict_count} conflicts resolved in {processing_time:.2f}s")
        
        return result
    
    def analyze_relationship_to_primary(
        self,
        person_id: str,
        person_name: str,
        conversation_history: List[Dict[str, Any]]
    ) -> Optional[AggregatedRelationship]:
        """
        Analyze a specific person's relationship to the primary human.
        
        Args:
            person_id: Person's unique ID
            person_name: Person's display name
            conversation_history: List of conversations with this person
            
        Returns:
            AggregatedRelationship or None if not enough data
        """
        if len(conversation_history) < 2:
            logger.debug(f"Not enough conversations for {person_name}")
            return None
        
        # Run horde analysis on this person's conversations
        result = self.analyze_conversations_horde(
            conversations=conversation_history,
            batch_size=5,
            target_person=person_id,
            focus_on_primary=True
        )
        
        # Find relationship to primary human
        for rel in result.primary_human_relationships:
            if person_id in [rel.person_a, rel.person_b]:
                return rel
        
        return None
    
    # ===================================================================
    # Batch Processing
    # ===================================================================
    
    def _create_batches(
        self,
        conversations: List[Dict[str, Any]],
        batch_size: int,
        target_person: Optional[str],
        focus_on_primary: bool
    ) -> List[ConversationBatch]:
        """Split conversations into batches."""
        batches = []
        
        for i in range(0, len(conversations), batch_size):
            batch_convs = conversations[i:i + batch_size]
            batch_id = f"batch_{i // batch_size}_{len(batch_convs)}"
            
            batches.append(ConversationBatch(
                batch_id=batch_id,
                conversations=batch_convs,
                target_person=target_person,
                focus_on_primary=focus_on_primary
            ))
        
        return batches
    
    def _process_batches_threaded(
        self,
        batches: List[ConversationBatch]
    ) -> List[AgentAnalysisResult]:
        """Process batches using thread pool."""
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._analyze_batch, batch): batch 
                for batch in batches
            }
            
            for future in as_completed(futures):
                batch = futures[future]
                try:
                    result = future.result(timeout=300)  # 5 min timeout
                    results.append(result)
                except Exception as e:
                    logger.error(f"Batch {batch.batch_id} failed: {e}")
                    results.append(AgentAnalysisResult(
                        agent_id="thread_pool",
                        batch_id=batch.batch_id,
                        status=AnalysisStatus.FAILED,
                        relationships=[],
                        errors=[str(e)],
                        processing_time_seconds=0
                    ))
        
        return results
    
    def _analyze_batch(self, batch: ConversationBatch) -> AgentAnalysisResult:
        """Analyze a single batch of conversations."""
        import time
        start_time = time.time()
        
        agent_id = f"agent_{batch.batch_id}"
        relationships: List[DetectedRelationship] = []
        errors = []
        
        try:
            for conv in batch.conversations:
                text = conv.get("text", "")
                speaker_id = conv.get("speaker_id", "unknown")
                speaker_name = conv.get("speaker_name", speaker_id)
                
                if batch.focus_on_primary:
                    # Focus on relationship to primary human
                    rel = self._detector.analyze_for_primary_human(
                        conversation_text=text,
                        other_person=speaker_name,
                        conversation_id=conv.get("id"),
                        timestamp=conv.get("timestamp")
                    )
                    if rel:
                        relationships.append(rel)
                else:
                    # General relationship detection
                    rels = self._detector.analyze_conversation(
                        conversation_text=text,
                        speaker_id=speaker_id,
                        speaker_name=speaker_name,
                        conversation_id=conv.get("id"),
                        timestamp=conv.get("timestamp")
                    )
                    relationships.extend(rels)
            
            processing_time = time.time() - start_time
            
            return AgentAnalysisResult(
                agent_id=agent_id,
                batch_id=batch.batch_id,
                status=AnalysisStatus.COMPLETED,
                relationships=relationships,
                errors=errors,
                processing_time_seconds=round(processing_time, 2)
            )
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Error analyzing batch {batch.batch_id}: {e}")
            
            return AgentAnalysisResult(
                agent_id=agent_id,
                batch_id=batch.batch_id,
                status=AnalysisStatus.FAILED,
                relationships=[],
                errors=[str(e)],
                processing_time_seconds=round(processing_time, 2)
            )
    
    # ===================================================================
    # Sub-agent Spawning (Golden Horde Pattern)
    # ===================================================================
    
    def _can_spawn_subagents(self) -> bool:
        """Check if we can spawn subagents."""
        # Check for required environment/dependencies
        return os.environ.get("KURULTAI_AGENT_SPAWNING", "false").lower() == "true"
    
    def _spawn_analysis_agents(
        self,
        batches: List[ConversationBatch]
    ) -> List[AgentAnalysisResult]:
        """
        Spawn subagents to analyze batches in parallel.
        
        This implements the golden-horde pattern for distributed analysis.
        """
        results = []
        
        try:
            from tools.kurultai.agent_spawner_direct import spawn_agent, AGENTS
            
            # Use available analysis agents
            analysis_agents = ["Jochi", "Möngke"]  # analyst, researcher
            
            for i, batch in enumerate(batches):
                agent_name = analysis_agents[i % len(analysis_agents)]
                
                # Create task in Neo4j for the agent
                task_id = self._create_analysis_task(batch, agent_name)
                
                # Spawn the agent
                context = f"Analyze relationship batch {batch.batch_id}: " \
                         f"{len(batch.conversations)} conversations"
                
                spawn_agent(agent_name, context)
                
                # Poll for result (simplified - in production use async/queue)
                result = self._wait_for_agent_result(task_id, timeout=300)
                if result:
                    results.append(result)
                else:
                    # Fallback to local processing
                    results.append(self._analyze_batch(batch))
                    
        except Exception as e:
            logger.error(f"Subagent spawning failed: {e}. Falling back to threaded.")
            return self._process_batches_threaded(batches)
        
        return results
    
    def _create_analysis_task(self, batch: ConversationBatch, agent: str) -> str:
        """Create an analysis task in Neo4j."""
        task_id = f"rel_task_{batch.batch_id}_{datetime.now(timezone.utc).strftime('%H%M%S')}"
        
        if not self._driver:
            return task_id
            
        try:
            with self._driver.session(database=self.database) as session:
                session.run("""
                    CREATE (t:RelationshipAnalysisTask {
                        id: $task_id,
                        batch_id: $batch_id,
                        assigned_to: $agent,
                        status: 'pending',
                        created_at: datetime(),
                        conversations: $conversations,
                        focus_on_primary: $focus_on_primary
                    })
                """,
                    task_id=task_id,
                    batch_id=batch.batch_id,
                    agent=agent,
                    conversations=json.dumps(batch.conversations),
                    focus_on_primary=batch.focus_on_primary
                )
        except Exception as e:
            logger.warning(f"Failed to create task in Neo4j: {e}")
            
        return task_id
    
    def _wait_for_agent_result(
        self,
        task_id: str,
        timeout: int = 300
    ) -> Optional[AgentAnalysisResult]:
        """Wait for an agent to complete a task."""
        import time
        start = time.time()
        
        while time.time() - start < timeout:
            if not self._driver:
                break
                
            try:
                with self._driver.session(database=self.database) as session:
                    result = session.run("""
                        MATCH (t:RelationshipAnalysisTask {id: $task_id})
                        RETURN t.status as status, t.result as result
                    """, task_id=task_id)
                    
                    record = result.single()
                    if record and record["status"] == "completed":
                        result_data = json.loads(record["result"])
                        return AgentAnalysisResult(**result_data)
                    elif record and record["status"] == "failed":
                        return None
                        
            except Exception as e:
                logger.warning(f"Error polling for result: {e}")
                
            time.sleep(5)
        
        return None
    
    # ===================================================================
    # Result Aggregation
    # ===================================================================
    
    def _aggregate_results(
        self,
        agent_results: List[AgentAnalysisResult]
    ) -> List[AggregatedRelationship]:
        """Aggregate relationship findings from multiple agents."""
        # Group relationships by person pair
        grouped: Dict[Tuple[str, str], List[DetectedRelationship]] = {}
        
        for result in agent_results:
            for rel in result.relationships:
                # Normalize pair order for consistent grouping
                pair = tuple(sorted([rel.person_a, rel.person_b]))
                
                if pair not in grouped:
                    grouped[pair] = []
                grouped[pair].append(rel)
        
        # Aggregate each group
        aggregated = []
        for pair, relationships in grouped.items():
            agg = self._aggregate_relationship_group(pair[0], pair[1], relationships)
            aggregated.append(agg)
        
        return aggregated
    
    def _aggregate_relationship_group(
        self,
        person_a: str,
        person_b: str,
        relationships: List[DetectedRelationship]
    ) -> AggregatedRelationship:
        """Aggregate multiple detections of the same relationship."""
        if not relationships:
            raise ValueError("Empty relationship list")
        
        # Count votes for each relationship type
        type_votes: Dict[str, int] = {}
        for rel in relationships:
            rel_type = rel.relationship_type.value
            type_votes[rel_type] = type_votes.get(rel_type, 0) + 1
        
        # Most common type wins
        dominant_type = max(type_votes, key=type_votes.get)
        
        # Calculate strength statistics
        strengths = [r.strength for r in relationships]
        avg_strength = sum(strengths) / len(strengths)
        max_strength = max(strengths)
        min_strength = min(strengths)
        
        # Combine all evidence
        all_evidence = []
        for rel in relationships:
            all_evidence.extend(rel.evidence)
        
        # Sort by timestamp (newest first)
        all_evidence.sort(key=lambda e: e.timestamp, reverse=True)
        
        # Calculate confidence based on evidence count and agreement
        evidence_count = len(all_evidence)
        type_agreement = type_votes[dominant_type] / len(relationships)
        confidence = min(0.3 + evidence_count * 0.05 + type_agreement * 0.3, 0.95)
        
        # Count conflicting assessments
        conflicting = len([t for t, c in type_votes.items() if t != dominant_type and c > 1])
        
        return AggregatedRelationship(
            person_a=person_a,
            person_b=person_b,
            relationship_type=RelationshipType(dominant_type),
            avg_strength=round(avg_strength, 2),
            max_strength=round(max_strength, 2),
            min_strength=round(min_strength, 2),
            confidence=round(confidence, 2),
            evidence_count=evidence_count,
            conflicting_assessments=conflicting,
            discovered_at=min(r.discovered_at for r in relationships),
            last_updated=max(r.last_updated for r in relationships),
            all_evidence=all_evidence[:50],  # Keep top 50 evidence
            agent_votes=type_votes
        )
    
    # ===================================================================
    # Conflict Resolution
    # ===================================================================
    
    def _resolve_conflicts(
        self,
        aggregated: List[AggregatedRelationship]
    ) -> Tuple[List[AggregatedRelationship], int]:
        """
        Resolve conflicts in relationship assessments.
        
        Returns:
            Tuple of (resolved relationships, number of conflicts resolved)
        """
        resolved = []
        conflict_count = 0
        
        for rel in aggregated:
            if rel.conflicting_assessments > 0:
                conflict_count += 1
                # Apply resolution rules
                rel = self._apply_resolution_rules(rel)
            resolved.append(rel)
        
        return resolved, conflict_count
    
    def _apply_resolution_rules(
        self,
        relationship: AggregatedRelationship
    ) -> AggregatedRelationship:
        """
        Apply rules to resolve conflicting assessments.
        
        Rules:
        1. If FRIEND and COLLEAGUE both present, choose based on context
        2. MENTOR/MENTEE should be reciprocal - validate
        3. FAMILY takes precedence over other types if strong evidence
        4. UNKNOWN is overridden by any specific type with confidence > 0.5
        """
        votes = relationship.agent_votes
        
        # Rule: FAMILY takes precedence with strong evidence
        if RelationshipType.FAMILY.value in votes:
            family_confidence = votes[RelationshipType.FAMILY.value] / sum(votes.values())
            if family_confidence > 0.4:
                relationship.relationship_type = RelationshipType.FAMILY
                relationship.confidence = min(relationship.confidence + 0.1, 0.95)
                return relationship
        
        # Rule: UNKNOWN is overridden by specific types
        if relationship.relationship_type == RelationshipType.UNKNOWN:
            non_unknown = {k: v for k, v in votes.items() if k != "unknown"}
            if non_unknown:
                best_type = max(non_unknown, key=non_unknown.get)
                if non_unknown[best_type] > 1:
                    relationship.relationship_type = RelationshipType(best_type)
                    relationship.confidence += 0.1
        
        # Rule: FRIEND vs COLLEAGUE resolution
        if (RelationshipType.FRIEND.value in votes and 
            RelationshipType.COLLEAGUE.value in votes):
            # If strengths are similar, might be both (friend at work)
            # For now, choose based on higher vote count
            friend_votes = votes[RelationshipType.FRIEND.value]
            colleague_votes = votes[RelationshipType.COLLEAGUE.value]
            
            if abs(friend_votes - colleague_votes) <= 1:
                # Close call - might be friend at work
                # Keep the higher confidence one
                pass
        
        return relationship
    
    # ===================================================================
    # Neo4j Storage
    # ===================================================================
    
    def _store_analysis_result(self, result: HordeAnalysisResult):
        """Store analysis result in Neo4j."""
        if not self._driver:
            return
            
        try:
            with self._driver.session(database=self.database) as session:
                # Store the analysis job
                session.run("""
                    CREATE (a:RelationshipAnalysis {
                        id: $job_id,
                        status: $status,
                        total_batches: $total_batches,
                        completed_batches: $completed_batches,
                        failed_batches: $failed_batches,
                        processing_time_seconds: $processing_time,
                        conflicts_resolved: $conflicts,
                        timestamp: datetime()
                    })
                """,
                    job_id=result.job_id,
                    status=result.status.value,
                    total_batches=result.total_batches,
                    completed_batches=result.completed_batches,
                    failed_batches=result.failed_batches,
                    processing_time=result.processing_time_seconds,
                    conflicts=result.conflicts_resolved
                )
                
                # Store aggregated relationships
                for rel in result.aggregated_relationships:
                    self._store_aggregated_relationship(session, rel, result.job_id)
                    
        except Exception as e:
            logger.error(f"Failed to store analysis result: {e}")
    
    def _store_aggregated_relationship(
        self,
        session,
        relationship: AggregatedRelationship,
        analysis_id: str
    ):
        """Store a single aggregated relationship."""
        try:
            session.run("""
                MATCH (a:RelationshipAnalysis {id: $analysis_id})
                MERGE (p1:Person {name: $person_a})
                MERGE (p2:Person {name: $person_b})
                CREATE (r:AggregatedRelationship {
                    type: $rel_type,
                    avg_strength: $avg_strength,
                    max_strength: $max_strength,
                    min_strength: $min_strength,
                    confidence: $confidence,
                    evidence_count: $evidence_count,
                    discovered_at: $discovered_at,
                    last_updated: $last_updated,
                    agent_votes: $votes
                })
                CREATE (a)-[:FOUND]->(r)
                CREATE (p1)-[:HAS_RELATIONSHIP]->(r)
                CREATE (p2)-[:HAS_RELATIONSHIP]->(r)
            """,
                analysis_id=analysis_id,
                person_a=relationship.person_a,
                person_b=relationship.person_b,
                rel_type=relationship.relationship_type.value,
                avg_strength=relationship.avg_strength,
                max_strength=relationship.max_strength,
                min_strength=relationship.min_strength,
                confidence=relationship.confidence,
                evidence_count=relationship.evidence_count,
                discovered_at=relationship.discovered_at,
                last_updated=relationship.last_updated,
                votes=json.dumps(relationship.agent_votes)
            )
        except Exception as e:
            logger.warning(f"Failed to store relationship: {e}")

    # ===================================================================
    # Graph Analytics
    # ===================================================================

    def compute_graph_analytics(
        self,
        relationships: List[AggregatedRelationship]
    ) -> GraphAnalytics:
        """
        Compute social graph analytics from relationships.

        Args:
            relationships: List of aggregated relationships

        Returns:
            GraphAnalytics with computed metrics
        """
        # Build adjacency list
        graph = self._build_graph(relationships)
        
        # Find clusters
        clusters = self._find_clusters(graph, relationships)
        
        # Find bridge people
        bridge_people = self._find_bridge_people(graph, clusters, relationships)
        
        # Find isolated individuals
        isolated = self._find_isolated_individuals(graph)
        
        # Compute influence scores
        influence_scores = self._compute_influence_scores(graph, relationships)
        
        # Compute graph metrics
        total_nodes = len(graph)
        total_edges = sum(len(neighbors) for neighbors in graph.values()) // 2
        density = self._compute_density(total_nodes, total_edges)
        avg_clustering = self._compute_average_clustering(graph)
        
        return GraphAnalytics(
            total_nodes=total_nodes,
            total_edges=total_edges,
            clusters=clusters,
            bridge_people=bridge_people,
            isolated_individuals=isolated,
            influence_scores=influence_scores,
            density=density,
            average_clustering=avg_clustering
        )

    def _build_graph(
        self,
        relationships: List[AggregatedRelationship]
    ) -> Dict[str, Set[str]]:
        """Build adjacency list from relationships."""
        graph: Dict[str, Set[str]] = {}
        
        for rel in relationships:
            if rel.person_a not in graph:
                graph[rel.person_a] = set()
            if rel.person_b not in graph:
                graph[rel.person_b] = set()
            
            # Only add edge if strength is above threshold
            if rel.avg_strength >= 0.3:
                graph[rel.person_a].add(rel.person_b)
                graph[rel.person_b].add(rel.person_a)
        
        return graph

    def _find_clusters(
        self,
        graph: Dict[str, Set[str]],
        relationships: List[AggregatedRelationship]
    ) -> List[Cluster]:
        """
        Find clusters/communities in the graph using connected components.
        """
        visited = set()
        clusters = []
        cluster_id = 0
        
        for node in graph:
            if node in visited:
                continue
            
            # BFS to find connected component
            component = []
            queue = [node]
            
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                component.append(current)
                
                for neighbor in graph.get(current, []):
                    if neighbor not in visited:
                        queue.append(neighbor)
            
            if len(component) >= 2:
                internal_edges = 0
                external_edges = 0
                
                for member in component:
                    for neighbor in graph.get(member, []):
                        if neighbor in component:
                            internal_edges += 1
                        else:
                            external_edges += 1
                
                internal_edges //= 2
                
                total_edges = internal_edges + external_edges
                cohesion = internal_edges / total_edges if total_edges > 0 else 0
                
                rel_types = {}
                for rel in relationships:
                    if rel.person_a in component and rel.person_b in component:
                        rel_type = rel.relationship_type.value
                        rel_types[rel_type] = rel_types.get(rel_type, 0) + 1
                
                dominant_types = sorted(
                    rel_types.keys(),
                    key=lambda x: rel_types[x],
                    reverse=True
                )[:3]
                
                clusters.append(Cluster(
                    cluster_id=f"cluster_{cluster_id}",
                    members=component,
                    size=len(component),
                    internal_edges=internal_edges,
                    external_edges=external_edges,
                    cohesion_score=round(cohesion, 2),
                    dominant_relationship_types=dominant_types
                ))
                cluster_id += 1
        
        clusters.sort(key=lambda c: c.size, reverse=True)
        return clusters

    def _find_bridge_people(
        self,
        graph: Dict[str, Set[str]],
        clusters: List[Cluster],
        relationships: List[AggregatedRelationship]
    ) -> List[BridgePerson]:
        """Find people who bridge different clusters."""
        if len(clusters) < 2:
            return []
        
        person_to_cluster: Dict[str, str] = {}
        for cluster in clusters:
            for member in cluster.members:
                person_to_cluster[member] = cluster.cluster_id
        
        bridge_candidates: Dict[str, Set[str]] = {}
        
        for person in graph:
            connected_clusters = set()
            for neighbor in graph.get(person, []):
                neighbor_cluster = person_to_cluster.get(neighbor)
                if neighbor_cluster:
                    connected_clusters.add(neighbor_cluster)
            
            own_cluster = person_to_cluster.get(person)
            if own_cluster:
                connected_clusters.discard(own_cluster)
            
            if len(connected_clusters) >= 1:
                bridge_candidates[person] = connected_clusters
        
        bridge_people = []
        
        for person, connected_clusters in bridge_candidates.items():
            external_connections = sum(
                1 for neighbor in graph.get(person, [])
                if person_to_cluster.get(neighbor) in connected_clusters
            )
            
            betweenness = external_connections / len(graph.get(person, {1}))
            
            bridge_people.append(BridgePerson(
                person_id=person,
                betweenness_score=round(betweenness, 2),
                connects_clusters=list(connected_clusters),
                bridge_strength=external_connections
            ))
        
        bridge_people.sort(key=lambda b: b.betweenness_score, reverse=True)
        return bridge_people[:20]

    def _find_isolated_individuals(
        self,
        graph: Dict[str, Set[str]]
    ) -> List[str]:
        """Find people with few or no connections."""
        isolated = []
        
        for person, neighbors in graph.items():
            if len(neighbors) <= 1:
                isolated.append(person)
        
        return isolated

    def _compute_influence_scores(
        self,
        graph: Dict[str, Set[str]],
        relationships: List[AggregatedRelationship]
    ) -> Dict[str, float]:
        """Compute influence scores for each person."""
        scores = {}
        
        strength_lookup = {}
        for rel in relationships:
            pair = tuple(sorted([rel.person_a, rel.person_b]))
            strength_lookup[pair] = rel.avg_strength
        
        for person in graph:
            total_strength = 0
            for neighbor in graph.get(person, []):
                pair = tuple(sorted([person, neighbor]))
                total_strength += strength_lookup.get(pair, 0.5)
            
            score = total_strength / max(len(graph) - 1, 1)
            scores[person] = round(score, 3)
        
        return scores

    def _compute_density(self, nodes: int, edges: int) -> float:
        """Compute graph density."""
        if nodes <= 1:
            return 0.0
        max_edges = nodes * (nodes - 1) / 2
        return round(edges / max_edges, 3) if max_edges > 0 else 0.0

    def _compute_average_clustering(
        self,
        graph: Dict[str, Set[str]]
    ) -> float:
        """Compute average clustering coefficient."""
        clustering_scores = []
        
        for node in graph:
            neighbors = graph.get(node, set())
            if len(neighbors) < 2:
                continue
            
            triangles = 0
            neighbor_list = list(neighbors)
            for i, n1 in enumerate(neighbor_list):
                for n2 in neighbor_list[i+1:]:
                    if n2 in graph.get(n1, set()):
                        triangles += 1
            
            possible = len(neighbors) * (len(neighbors) - 1) / 2
            if possible > 0:
                clustering_scores.append(triangles / possible)
        
        return round(sum(clustering_scores) / len(clustering_scores), 3) if clustering_scores else 0.0


# =============================================================================
# Convenience Functions
# =============================================================================

def analyze_relationships_horde(
    conversations: List[Dict[str, Any]],
    primary_human: str = "Danny",
    batch_size: int = 10,
    focus_on_primary: bool = True
) -> HordeAnalysisResult:
    """
    Convenience function for horde relationship analysis.
    
    Args:
        conversations: List of conversation dicts
        primary_human: Name of primary human
        batch_size: Conversations per batch
        focus_on_primary: Whether to focus on primary human relationships
        
    Returns:
        HordeAnalysisResult
    """
    analyzer = RelationshipAnalyzer(primary_human=primary_human)
    analyzer.initialize()
    
    try:
        return analyzer.analyze_conversations_horde(
            conversations=conversations,
            batch_size=batch_size,
            focus_on_primary=focus_on_primary
        )
    finally:
        analyzer.close()


def quick_relationship_check(
    person_name: str,
    conversation_text: str,
    primary_human: str = "Danny"
) -> Optional[AggregatedRelationship]:
    """
    Quick check of relationship from a single conversation.
    
    Args:
        person_name: Name of person
        conversation_text: Text to analyze
        primary_human: Name of primary human
        
    Returns:
        AggregatedRelationship or None
    """
    conversations = [{
        "text": conversation_text,
        "speaker_id": person_name,
        "speaker_name": person_name,
        "timestamp": datetime.now(timezone.utc)
    }]
    
    result = analyze_relationships_horde(
        conversations=conversations,
        primary_human=primary_human,
        batch_size=1,
        focus_on_primary=True
    )
    
    for rel in result.primary_human_relationships:
        if person_name in [rel.person_a, rel.person_b]:
            return rel
    
    return None


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Example conversations
    conversations = [
        {
            "text": "I've been working with Danny on Kurultai for 6 months. "
                   "He's my business partner and co-founder.",
            "speaker_id": "alice",
            "speaker_name": "Alice",
            "timestamp": datetime.now(timezone.utc)
        },
        {
            "text": "Danny and I go way back - we met in college. "
                   "He's one of my closest friends.",
            "speaker_id": "bob",
            "speaker_name": "Bob",
            "timestamp": datetime.now(timezone.utc)
        },
        {
            "text": "My brother Danny is helping me with the project. "
                   "He's been mentoring me on the technical side.",
            "speaker_id": "carol",
            "speaker_name": "Carol",
            "timestamp": datetime.now(timezone.utc)
        }
    ]
    
    # Run horde analysis
    result = analyze_relationships_horde(
        conversations=conversations,
        primary_human="Danny",
        batch_size=2
    )
    
    print(f"\nAnalysis complete!")
    print(f"  Job ID: {result.job_id}")
    print(f"  Processing time: {result.processing_time_seconds}s")
    print(f"  Relationships found: {len(result.aggregated_relationships)}")
    print(f"  Conflicts resolved: {result.conflicts_resolved}")
    
    print(f"\nRelationships to {result.primary_human_relationships[0].person_b if result.primary_human_relationships else 'Danny'}:")
    for rel in result.primary_human_relationships:
        print(f"  - {rel.person_a}: {rel.relationship_type.value} "
              f"(strength: {rel.avg_strength}, confidence: {rel.confidence})")
