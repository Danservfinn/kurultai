#!/usr/bin/env python3
"""
Neo4j Schema Integration - Python Helper Functions

This module provides safe, atomic operations for the Kurultai Neo4j schema
enhancements. It addresses security and edge case concerns identified in review.

Usage:
    from neo4j_schema_integration import SchemaManager, SafeQueries

    manager = SchemaManager()
    manager.update_skill_affinity('temujin', 'code_review', True, 45.0)
"""

import os
import sys
import json
import re
import uuid
import hashlib
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver

# ============================================================
# SECURITY: Content Sanitization
# ============================================================

SENSITIVE_PATTERNS = [
    (r'sk-[a-zA-Z0-9]{20,}', '[REDACTED_KEY]'),           # OpenAI/Anthropic keys
    (r'xox[baprs]-[a-zA-Z0-9\-]+', '[REDACTED_TOKEN]'),   # Slack tokens
    (r'eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.', '[REDACTED_JWT]'),  # JWTs
    (r'(?i)password["\']?\s*[:=]\s*["\']?[^\s"\']+', '[REDACTED_PASSWORD]'),  # Passwords
    (r'\b[\w\.-]+@[\w\.-]+\.\w+\b', '[REDACTED_EMAIL]'),  # Emails
    (r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[REDACTED_PHONE]'),  # Phone numbers
    (r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', '[REDACTED_CARD]'),  # Credit cards
]

def sanitize_content(content: str) -> Tuple[str, bool]:
    """Sanitize content for Neo4j storage.

    Returns:
        (sanitized_content, contains_pii)
    """
    contains_pii = False
    sanitized = content

    for pattern, replacement in SENSITIVE_PATTERNS:
        if re.search(pattern, content):
            contains_pii = True
            sanitized = re.sub(pattern, replacement, sanitized)

    return sanitized, contains_pii


def hash_content(content: str) -> str:
    """Generate SHA256 hash for deduplication."""
    return hashlib.sha256(content.encode()).hexdigest()


def validate_json_field(value: Any, max_size_bytes: int = 10000) -> Dict:
    """Validate JSON field before storage."""
    if value is None:
        return {}

    if not isinstance(value, dict):
        raise ValueError(f"Expected dict, got {type(value)}")

    serialized = json.dumps(value)
    if len(serialized) > max_size_bytes:
        raise ValueError(f"JSON exceeds {max_size_bytes} bytes")

    return value


# ============================================================
# SCHEMA MANAGER
# ============================================================

class SchemaManager:
    """Manages Neo4j schema operations with safety guarantees."""

    MAX_TRAVERSAL_DEPTH = 5
    MAX_RESULT_COUNT = 1000

    def __init__(self):
        self.driver = get_driver()

    def close(self):
        self.driver.close()

    # --------------------------------------------------------
    # ROUTING INTELLIGENCE
    # --------------------------------------------------------

    def update_skill_affinity(self, agent: str, skill: str,
                              success: bool, duration_seconds: float):
        """Update skill affinity atomically. Uses MERGE for idempotency."""
        with self.driver.session() as session:
            session.run("""
                MERGE (s:SkillAffinity {agent: $agent, skill: $skill})
                ON CREATE SET
                    s.affinity_id = randomUUID(),
                    s.success_rate = 0.0,
                    s.avg_duration_seconds = 0.0,
                    s.sample_count = 0,
                    s.created = datetime()
                ON MATCH SET
                    s.sample_count = s.sample_count + 1,
                    s.success_rate = (s.success_rate * (s.sample_count - 1) +
                        CASE WHEN $success THEN 1 ELSE 0 END) / s.sample_count,
                    s.avg_duration_seconds = (s.avg_duration_seconds *
                        (s.sample_count - 1) + $duration) / s.sample_count,
                    s.last_updated = datetime()
                WITH s
                MATCH (a:Agent {name: $agent})
                MERGE (a)-[r:HAS_SKILL_AFFINITY]->(s)
                SET r.weight = coalesce(r.weight, 1) + 1,
                    r.last_accessed = datetime()
            """, agent=agent, skill=skill, success=success,
                duration=duration_seconds)

    def update_agent_capacity(self, agent: str, queue_depth: int,
                             throughput_1h: int, active_tasks: int):
        """Update agent capacity snapshot."""
        with self.driver.session() as session:
            session.run("""
                MERGE (c:AgentCapacity {agent: $agent})
                ON CREATE SET c.created = datetime()
                SET c.queue_depth = $queue_depth,
                    c.throughput_1h = $throughput,
                    c.active_tasks = $active,
                    c.availability_score = CASE
                        WHEN $queue_depth > 5 THEN 0.3
                        WHEN $queue_depth > 3 THEN 0.6
                        ELSE 1.0
                    END,
                    c.last_updated = datetime()
            """, agent=agent, queue_depth=queue_depth,
                throughput=throughput_1h, active=active_tasks)

    def create_routing_decision(self, task_id: str, from_agent: str,
                                to_agent: str, reason: str,
                                confidence: float, factors: Dict):
        """Create routing decision with validated JSON."""
        factors = validate_json_field(factors)

        with self.driver.session() as session:
            session.run("""
                CREATE (r:RoutingDecision {
                    routing_id: randomUUID(),
                    task_id: $task_id,
                    from_agent: $from_agent,
                    to_agent: $to_agent,
                    reason: $reason,
                    confidence: $confidence,
                    factors: $factors,
                    outcome: 'pending',
                    created: datetime()
                })
                WITH r
                OPTIONAL MATCH (t:Task {task_id: $task_id})
                FOREACH (_ IN CASE WHEN t IS NOT NULL THEN [1] ELSE [] END |
                    CREATE (t)-[:ROUTED_BY]->(r)
                )
                WITH r
                MATCH (a:Agent {name: $to_agent})
                CREATE (r)-[:ROUTED_TO]->(a)
            """, task_id=task_id, from_agent=from_agent, to_agent=to_agent,
                reason=reason, confidence=confidence, factors=factors)

    def resolve_routing_decision(self, task_id: str, outcome: str):
        """Update routing decision outcome."""
        if outcome not in ['success', 'failed', 'rerouted']:
            raise ValueError(f"Invalid outcome: {outcome}")

        with self.driver.session() as session:
            session.run("""
                MATCH (r:RoutingDecision {task_id: $task_id})
                SET r.outcome = $outcome, r.resolved = datetime()
            """, task_id=task_id, outcome=outcome)

    def get_best_agent_for_skill(self, skill: str) -> List[Dict]:
        """Find best agent for a task type (top 3)."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (a:Agent)-[:HAS_SKILL_AFFINITY]->(s:SkillAffinity {skill: $skill})
                MATCH (c:AgentCapacity {agent: a.name})
                WHERE s.success_rate > 0.5 AND c.availability_score > 0.3
                RETURN a.name AS agent,
                       s.success_rate AS success_rate,
                       c.availability_score AS availability,
                       s.success_rate * c.availability_score AS routing_score
                ORDER BY routing_score DESC
                LIMIT 3
            """, skill=skill)
            return [dict(r) for r in result]

    # --------------------------------------------------------
    # SELF-IMPROVEMENT
    # --------------------------------------------------------

    def create_reflection_insight(self, agent: str, insight_type: str,
                                  description: str, impact_score: int) -> str:
        """Create reflection insight. Returns insight_id."""
        if impact_score < 1 or impact_score > 10:
            raise ValueError("impact_score must be 1-10")

        description, contains_pii = sanitize_content(description)

        insight_id = str(uuid.uuid4())[:12]

        with self.driver.session() as session:
            session.run("""
                CREATE (r:ReflectionInsight {
                    insight_id: $id,
                    agent: $agent,
                    timestamp: datetime(),
                    insight_type: $type,
                    description: $description,
                    impact_score: $impact,
                    applied: false,
                    rule_generated: false,
                    created: datetime()
                })
                WITH r
                MATCH (a:Agent {name: $agent})
                CREATE (a)-[:HAS_INSIGHT]->(r)
            """, id=insight_id, agent=agent, type=insight_type,
                description=description, impact=impact_score)

        return insight_id

    def create_failure_pattern(self, error_message: str, category: str,
                               root_cause: str, agent: str) -> str:
        """Create or match failure pattern. Returns pattern_id."""
        error_message, _ = sanitize_content(error_message)
        signature = hash_content(error_message[:200])  # Normalize

        with self.driver.session() as session:
            result = session.run("""
                OPTIONAL MATCH (f:FailurePattern {error_signature: $signature})
                FOREACH (_ IN CASE WHEN f IS NULL THEN [1] ELSE [] END |
                    CREATE (new:FailurePattern {
                        pattern_id: randomUUID(),
                        error_signature: $signature,
                        error_category: $category,
                        root_cause: $root_cause,
                        first_seen: datetime(),
                        last_seen: datetime(),
                        recurrence_count: 1,
                        affected_agents: [$agent]
                    })
                    RETURN new.pattern_id AS id
                )
                FOREACH (_ IN CASE WHEN f IS NOT NULL THEN [1] ELSE [] END |
                    SET f.last_seen = datetime(),
                        f.recurrence_count = f.recurrence_count + 1,
                        f.affected_agents = apoc.coll.toSet(f.affected_agents + $agent)
                    RETURN f.pattern_id AS id
                )
                RETURN coalesce(new.pattern_id, f.pattern_id) AS id
            """, signature=signature, category=category,
                root_cause=root_cause, agent=agent)

            record = result.single()
            return record["id"] if record else None

    def update_skill_evolution(self, agent: str, skill: str, success: bool):
        """Update skill performance evolution."""
        with self.driver.session() as session:
            session.run("""
                MERGE (s:SkillEvolution {agent: $agent, skill: $skill})
                ON CREATE SET
                    s.evo_id = randomUUID(),
                    s.version = '1.0.0',
                    s.baseline_performance = 0.5,
                    s.current_performance = 0.5,
                    s.sample_count = 0,
                    s.created = datetime()
                ON MATCH SET
                    s.current_performance = (s.current_performance * s.sample_count +
                        CASE WHEN $success THEN 1.0 ELSE 0.0 END) / (s.sample_count + 1),
                    s.sample_count = s.sample_count + 1,
                    s.improvement_rate = (s.current_performance - s.baseline_performance) / 7.0,
                    s.proficiency_level = CASE
                        WHEN s.current_performance >= 0.9 THEN 'expert'
                        WHEN s.current_performance >= 0.75 THEN 'proficient'
                        WHEN s.current_performance >= 0.5 THEN 'competent'
                        ELSE 'novice'
                    END,
                    s.updated = datetime()
            """, agent=agent, skill=skill, success=success)

    # --------------------------------------------------------
    # OBSERVABILITY
    # --------------------------------------------------------

    def aggregate_hourly_metrics(self, agent: str, prev_hour: str):
        """Aggregate performance metrics for previous hour."""
        with self.driver.session() as session:
            # Task completion rate
            session.run("""
                MATCH (t:Task)
                WHERE t.agent = $agent
                  AND t.completed >= datetime() - duration('PT1H')
                  AND t.completed < datetime()
                WITH
                    count(t) AS total,
                    sum(CASE WHEN t.status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed
                WITH CASE WHEN total > 0 THEN round(100.0 * completed / total, 2) ELSE 0 END AS rate

                OPTIONAL MATCH (prev:PerformanceMetric {
                    agent: $agent,
                    metric_name: 'task_completion_rate',
                    hour: $hour
                })

                WITH rate, prev,
                    CASE
                        WHEN prev IS NULL THEN 'stable'
                        WHEN rate > prev.value * 1.1 THEN 'up'
                        WHEN rate < prev.value * 0.9 THEN 'down'
                        ELSE 'stable'
                    END AS trend

                CREATE (m:PerformanceMetric {
                    metric_id: randomUUID(),
                    agent: $agent,
                    metric_name: 'task_completion_rate',
                    value: rate,
                    value_min: rate,
                    value_max: rate,
                    value_count: 1,
                    trend: trend,
                    period: 'hourly',
                    hour: $hour,
                    created: datetime()
                })
                WITH m, prev
                MATCH (a:Agent {name: $agent})
                CREATE (a)-[:HAS_METRIC]->(m)
                FOREACH (_ IN CASE WHEN prev IS NOT NULL THEN [1] ELSE [] END |
                    CREATE (prev)-[:PRECEDES]->(m)
                )
            """, agent=agent, hour=prev_hour)

    def update_dependency_health(self, component_a: str, component_b: str,
                                 status: str, latency_ms: int, errors: int):
        """Update dependency graph health status."""
        with self.driver.session() as session:
            session.run("""
                MERGE (d:DependencyGraph {component_a: $a, component_b: $b})
                ON CREATE SET d.created = datetime()
                SET d.dependency_type = 'depends_on',
                    d.health_status = CASE WHEN $status = 'up' THEN 'healthy' ELSE 'down' END,
                    d.latency_ms = $latency,
                    d.error_count = $errors,
                    d.updated = datetime()
            """, a=component_a, b=component_b, status=status,
                latency=latency_ms, errors=errors)

    def create_bottleneck(self, location: str, cause: str,
                         impact_score: int, agents: List[str],
                         task_count: int) -> str:
        """Create or update bottleneck. Returns bottleneck_id."""
        bottleneck_id = str(uuid.uuid4())[:12]

        with self.driver.session() as session:
            result = session.run("""
                OPTIONAL MATCH (existing:Bottleneck {
                    location: $location,
                    cause: $cause,
                    resolved: false
                })
                WHERE existing.first_detected > datetime() - duration('PT2H')

                FOREACH (_ IN CASE WHEN existing IS NULL THEN [1] ELSE [] END |
                    CREATE (b:Bottleneck {
                        bottleneck_id: $id,
                        location: $location,
                        cause: $cause,
                        first_detected: datetime(),
                        last_seen: datetime(),
                        duration_minutes: 5,
                        impact_score: $impact,
                        affected_agents: $agents,
                        affected_tasks: $count,
                        resolved: false,
                        pattern: 'sustained'
                    })
                )

                FOREACH (_ IN CASE WHEN existing IS NOT NULL THEN [1] ELSE [] END |
                    SET existing.last_seen = datetime(),
                        existing.duration_minutes = existing.duration_minutes + 5,
                        existing.impact_score = CASE
                            WHEN $impact > existing.impact_score THEN $impact
                            ELSE existing.impact_score
                        END
                )

                RETURN coalesce(existing.bottleneck_id, $id) AS id
            """, id=bottleneck_id, location=location, cause=cause,
                impact=impact_score, agents=agents, count=task_count)

            record = result.single()
            return record["id"] if record else bottleneck_id

    def resolve_bottleneck(self, bottleneck_id: str, resolved_by: str):
        """Mark bottleneck as resolved."""
        with self.driver.session() as session:
            session.run("""
                MATCH (b:Bottleneck {bottleneck_id: $id})
                SET b.resolved = true,
                    b.resolved_by = $by,
                    b.resolution_time = datetime()
            """, id=bottleneck_id, by=resolved_by)

    def create_system_event(self, event_type: str, severity: str,
                           component: str, message: str,
                           details: Optional[Dict] = None) -> str:
        """Create system event. Returns event_id."""
        if severity not in ['INFO', 'WARNING', 'ERROR', 'CRITICAL']:
            raise ValueError(f"Invalid severity: {severity}")

        message, contains_pii = sanitize_content(message)
        details = validate_json_field(details) if details else {}

        event_id = str(uuid.uuid4())[:12]

        with self.driver.session() as session:
            session.run("""
                CREATE (e:SystemEvent {
                    event_id: $id,
                    type: $type,
                    severity: $severity,
                    component: $component,
                    message: $message,
                    details: $details,
                    resolved: false,
                    created: datetime()
                })
            """, id=event_id, type=event_type, severity=severity,
                component=component, message=message, details=details)

        return event_id

    # --------------------------------------------------------
    # KNOWLEDGE & QUALITY
    # --------------------------------------------------------

    def create_knowledge_artifact(self, agent: str, artifact_type: str,
                                  content: str, keywords: List[str]) -> str:
        """Create knowledge artifact with sanitization."""
        content, contains_pii = sanitize_content(content)
        content_hash = hash_content(content)

        artifact_id = str(uuid.uuid4())[:12]

        with self.driver.session() as session:
            session.run("""
                CREATE (k:KnowledgeArtifact {
                    artifact_id: $id,
                    type: $type,
                    content: $content,
                    content_hash: $hash,
                    keywords: $keywords,
                    created_by: $agent,
                    usage_count: 0,
                    freshness_score: 1.0,
                    sensitivity: CASE WHEN $contains_pii THEN 'confidential' ELSE 'internal' END,
                    created: datetime()
                })
                WITH k
                MATCH (a:Agent {name: $agent})
                CREATE (a)-[:CREATED_ARTIFACT]->(k)
            """, id=artifact_id, type=artifact_type, content=content,
                hash=content_hash, keywords=keywords, agent=agent,
                contains_pii=contains_pii)

        return artifact_id

    def search_knowledge(self, query: str, agent: str, limit: int = 9) -> List[Dict]:
        """Search knowledge artifacts (fulltext)."""
        limit = min(limit, self.MAX_RESULT_COUNT)

        with self.driver.session() as session:
            result = session.run("""
                CALL db.index.fulltext.queryNodes('knowledge_search', $query)
                YIELD node, score
                WHERE node.freshness_score > 0.3
                  AND (node.sensitivity = 'public' OR node.created_by = $agent)
                RETURN node.artifact_id AS id,
                       node.type AS type,
                       node.content AS content,
                       node.keywords AS keywords,
                       node.usage_count AS usage_count,
                       score * node.freshness_score AS relevance
                ORDER BY relevance DESC
                LIMIT $limit
            """, query=query, agent=agent, limit=limit)
            return [dict(r) for r in result]

    def create_quality_gate(self, task_id: str, checkpoint_name: str) -> str:
        """Create quality gate for task."""
        gate_id = str(uuid.uuid4())[:12]

        with self.driver.session() as session:
            session.run("""
                CREATE (q:QualityGate {
                    gate_id: $id,
                    task_id: $task_id,
                    checkpoint_name: $name,
                    passed: false,
                    reviewer: null,
                    notes: null,
                    created: datetime()
                })
                WITH q
                OPTIONAL MATCH (t:Task {task_id: $task_id})
                FOREACH (_ IN CASE WHEN t IS NOT NULL THEN [1] ELSE [] END |
                    CREATE (q)-[:VALIDATES]->(t)
                )
            """, id=gate_id, task_id=task_id, name=checkpoint_name)

        return gate_id

    def pass_quality_gate(self, gate_id: str, reviewer: str, notes: str = ""):
        """Mark quality gate as passed."""
        notes, _ = sanitize_content(notes)

        with self.driver.session() as session:
            session.run("""
                MATCH (q:QualityGate {gate_id: $id})
                SET q.passed = true,
                    q.reviewer = $reviewer,
                    q.notes = $notes,
                    q.checked_at = datetime()
            """, id=gate_id, reviewer=reviewer, notes=notes)

    def create_technical_debt(self, location: str, description: str,
                              impact: str, priority: int,
                              created_by_task: Optional[str] = None) -> str:
        """Create technical debt record."""
        if impact not in ['low', 'medium', 'high', 'critical']:
            raise ValueError(f"Invalid impact: {impact}")

        description, _ = sanitize_content(description)
        debt_id = str(uuid.uuid4())[:12]

        with self.driver.session() as session:
            session.run("""
                CREATE (t:TechnicalDebt {
                    debt_id: $id,
                    location: $location,
                    description: $description,
                    impact: $impact,
                    priority: $priority,
                    resolved: false,
                    created: datetime()
                })
                WITH t
                OPTIONAL MATCH (task:Task {task_id: $task_id})
                FOREACH (_ IN CASE WHEN task IS NOT NULL THEN [1] ELSE [] END |
                    CREATE (t)-[:CREATED_BY]->(task)
                )
            """, id=debt_id, location=location, description=description,
                impact=impact, priority=priority, task_id=created_by_task)

        return debt_id

    # --------------------------------------------------------
    # LIFECYCLE & MAINTENANCE
    # --------------------------------------------------------

    def prune_stale_data(self, metrics_days: int = 30,
                        events_days: int = 7) -> Dict[str, int]:
        """Lifecycle management for time-series data."""
        results = {}

        with self.driver.session() as session:
            # Prune old metrics
            r = session.run("""
                MATCH (m:PerformanceMetric)
                WHERE m.created < datetime() - duration({days: $days})
                DELETE m
                RETURN count(m) AS cnt
            """, days=metrics_days)
            record = r.single()
            results["metrics_pruned"] = record["cnt"] if record else 0

            # Prune old system events (resolved only)
            r = session.run("""
                MATCH (e:SystemEvent)
                WHERE e.resolved = true
                  AND e.created < datetime() - duration({days: $days})
                DELETE e
                RETURN count(e) AS cnt
            """, days=events_days)
            record = r.single()
            results["events_pruned"] = record["cnt"] if record else 0

            # Decay freshness scores
            r = session.run("""
                MATCH (k:KnowledgeArtifact)
                WHERE k.freshness_score > 0.1
                SET k.freshness_score = k.freshness_score * 0.95
                RETURN count(k) AS cnt
            """)
            record = r.single()
            results["artifacts_decayed"] = record["cnt"] if record else 0

            # Mark stale artifacts
            r = session.run("""
                MATCH (k:KnowledgeArtifact)
                WHERE k.freshness_score <= 0.1
                SET k.stale = true
                RETURN count(k) AS cnt
            """)
            record = r.single()
            results["artifacts_stale"] = record["cnt"] if record else 0

        return results

    def detect_zombie_tasks(self, hours: int = 2) -> List[Dict]:
        """Find and timeout tasks stuck in EXECUTING."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.status IN ['EXECUTING', 'running']
                  AND t.started < datetime() - duration({hours: $hours})
                SET t.status = 'TIMEOUT',
                    t.zombie_detected = true,
                    t.completed = datetime()
                RETURN t.task_id AS task_id,
                       t.agent AS agent,
                       t.started AS started,
                       duration.inSeconds(t.started, datetime()).seconds AS seconds_stuck
                ORDER BY seconds_stuck DESC
            """, hours=hours)
            return [dict(r) for r in result]

    def reconcile_resolved_events(self) -> int:
        """Mark resolved system events with duration."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (e:SystemEvent)
                WHERE e.component = $component
                  AND e.resolved = false
                  AND e.type IN ['degradation', 'outage']
                WITH e ORDER BY e.created DESC LIMIT 1
                SET e.resolved = true,
                    e.resolution_time = datetime(),
                    e.duration_seconds = duration.inSeconds(e.created, datetime()).seconds
                RETURN count(e) AS cnt
            """)
            record = result.single()
            return record["cnt"] if record else 0


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

def get_routing_recommendation(skill: str) -> Dict:
    """Get best agent and capacity for a skill."""
    manager = SchemaManager()
    try:
        agents = manager.get_best_agent_for_skill(skill)
        if agents:
            best = agents[0]
            return {
                "recommended_agent": best["agent"],
                "confidence": best["routing_score"],
                "success_rate": best["success_rate"],
                "availability": best["availability"],
                "alternatives": agents[1:]
            }
        return {"recommended_agent": None, "reason": "No qualified agents"}
    finally:
        manager.close()


def log_task_routing(task_id: str, skill: str, from_agent: str = "gateway"):
    """Log a routing decision and return the chosen agent."""
    recommendation = get_routing_recommendation(skill)

    if recommendation.get("recommended_agent"):
        to_agent = recommendation["recommended_agent"]
        confidence = recommendation["confidence"]

        manager = SchemaManager()
        try:
            manager.create_routing_decision(
                task_id=task_id,
                from_agent=from_agent,
                to_agent=to_agent,
                reason="skill_match",
                confidence=confidence,
                factors={"skill": skill, "method": "affinity_routing"}
            )
        finally:
            manager.close()

        return to_agent

    return None


if __name__ == "__main__":
    # Test the integration
    manager = SchemaManager()

    print("Testing SchemaManager...")

    # Test skill affinity
    manager.update_skill_affinity('temujin', 'code_review', True, 45.0)

    # Test capacity
    manager.update_agent_capacity('temujin', 2, 5, 1)

    # Test routing
    best = manager.get_best_agent_for_skill('code_review')
    print(f"Best agent for code_review: {best}")

    # Test lifecycle
    zombies = manager.detect_zombie_tasks()
    print(f"Zombie tasks: {zombies}")

    manager.close()
    print("Tests completed.")
