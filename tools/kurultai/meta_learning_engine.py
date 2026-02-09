"""
Meta-Learning Engine for Kurultai

Clusters reflection patterns, generates MetaRule nodes from patterns,
updates SOUL.md files with learned rules, and tracks rule effectiveness.

Author: Chagatai (Writer Agent)
Date: 2026-02-09
"""

import os
import re
import uuid
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import logging

from neo4j import GraphDatabase


logger = logging.getLogger(__name__)


class RuleEffectiveness(Enum):
    """Effectiveness levels for learned rules."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


@dataclass
class ReflectionCluster:
    """A cluster of similar reflections."""
    id: str
    topic: str
    pattern_signature: str
    reflections: List[Dict[str, Any]] = field(default_factory=list)
    common_insights: List[str] = field(default_factory=list)
    rule_generated: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "topic": self.topic,
            "pattern_signature": self.pattern_signature,
            "reflection_count": len(self.reflections),
            "common_insights": self.common_insights,
            "rule_generated": self.rule_generated,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class MetaRule:
    """A rule generated from reflection patterns."""
    id: str
    name: str
    description: str
    rule_type: str
    source_cluster_id: str
    target_agents: List[str]
    conditions: List[str]
    actions: List[str]
    priority: int = 5
    effectiveness_score: float = 0.0
    application_count: int = 0
    success_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_evaluated: Optional[datetime] = None
    status: str = "proposed"  # proposed, active, deprecated, rejected
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "rule_type": self.rule_type,
            "source_cluster_id": self.source_cluster_id,
            "target_agents": self.target_agents,
            "conditions": self.conditions,
            "actions": self.actions,
            "priority": self.priority,
            "effectiveness_score": self.effectiveness_score,
            "application_count": self.application_count,
            "success_count": self.success_count,
            "created_at": self.created_at.isoformat(),
            "last_evaluated": self.last_evaluated.isoformat() if self.last_evaluated else None,
            "status": self.status,
        }


class MetaLearningEngine:
    """
    Engine for learning from agent reflections and generating improvement rules.
    
    Key capabilities:
    - Cluster similar reflections to identify patterns
    - Generate MetaRule nodes from identified patterns
    - Track rule effectiveness over time
    - Coordinate with SOULInjector for rule deployment
    """
    
    def __init__(self, neo4j_uri: Optional[str] = None, 
                 neo4j_user: str = "neo4j",
                 neo4j_password: Optional[str] = None):
        """
        Initialize the MetaLearningEngine.
        
        Args:
            neo4j_uri: Neo4j connection URI
            neo4j_user: Neo4j username
            neo4j_password: Neo4j password
        """
        self.neo4j_uri = neo4j_uri or os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password or os.environ.get('NEO4J_PASSWORD')
        
        self._driver = None
        self.clusters: Dict[str, ReflectionCluster] = {}
        self.rules: Dict[str, MetaRule] = {}
        
        # Configuration
        self.min_cluster_size = 3
        self.similarity_threshold = 0.75
        self.min_confidence_for_rule = 0.6
        
    def _get_driver(self) -> GraphDatabase.driver:
        """Get or create Neo4j driver."""
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.neo4j_uri, 
                auth=(self.neo4j_user, self.neo4j_password)
            )
        return self._driver
    
    def close(self):
        """Close Neo4j connection."""
        if self._driver:
            self._driver.close()
            self._driver = None
    
    def cluster_reflections(self, min_cluster_size: Optional[int] = None,
                           time_window_days: int = 30) -> List[ReflectionCluster]:
        """
        Cluster similar reflections to identify patterns.
        
        Args:
            min_cluster_size: Minimum reflections per cluster (default: self.min_cluster_size)
            time_window_days: Only consider reflections from last N days
            
        Returns:
            List of ReflectionCluster objects
        """
        min_size = min_cluster_size or self.min_cluster_size
        cutoff_date = datetime.utcnow() - timedelta(days=time_window_days)
        
        driver = self._get_driver()
        clusters = []
        
        with driver.session() as session:
            # Find unconsolidated reflections within time window
            result = session.run("""
                MATCH (r:Reflection)
                WHERE r.consolidated = false 
                      OR r.consolidated IS NULL
                      OR r.created_at > $cutoff_date
                RETURN r.id as id, r.agent as agent, r.topic as topic,
                       r.insights as insights, r.trigger_task_type as task_type,
                       r.created_at as created_at
                ORDER BY r.topic, r.created_at DESC
            """, cutoff_date=cutoff_date.isoformat())
            
            reflections = [record.data() for record in result]
        
        if not reflections:
            logger.info("No reflections found for clustering")
            return clusters
        
        # Group by topic for initial clustering
        topic_groups: Dict[str, List[Dict]] = {}
        for reflection in reflections:
            topic = reflection.get('topic', 'unknown')
            if topic not in topic_groups:
                topic_groups[topic] = []
            topic_groups[topic].append(reflection)
        
        # Create clusters from topic groups
        for topic, topic_reflections in topic_groups.items():
            if len(topic_reflections) >= min_size:
                cluster = self._create_cluster_from_reflections(topic, topic_reflections)
                clusters.append(cluster)
                self.clusters[cluster.id] = cluster
                
                # Store cluster in Neo4j
                self._persist_cluster(cluster)
        
        logger.info(f"Created {len(clusters)} clusters from {len(reflections)} reflections")
        return clusters
    
    def _create_cluster_from_reflections(self, topic: str, 
                                         reflections: List[Dict]) -> ReflectionCluster:
        """Create a cluster from grouped reflections."""
        # Generate pattern signature from insights
        all_insights = []
        for r in reflections:
            insights = r.get('insights', [])
            if isinstance(insights, str):
                insights = [insights]
            all_insights.extend(insights)
        
        # Extract common themes using simple keyword extraction
        common_insights = self._extract_common_themes(all_insights)
        
        # Generate signature
        signature = self._generate_pattern_signature(topic, common_insights)
        
        cluster = ReflectionCluster(
            id=str(uuid.uuid4()),
            topic=topic,
            pattern_signature=signature,
            reflections=reflections,
            common_insights=common_insights,
        )
        
        return cluster
    
    def _extract_common_themes(self, insights: List[str]) -> List[str]:
        """Extract common themes from a list of insights."""
        if not insights:
            return []
        
        # Simple keyword-based theme extraction
        theme_keywords = {
            'error_handling': ['error', 'exception', 'fail', 'catch', 'handle'],
            'performance': ['slow', 'fast', 'performance', 'optimize', 'speed', 'latency'],
            'communication': ['communicate', 'message', 'notify', 'inform', 'response'],
            'planning': ['plan', 'organize', 'structure', 'sequence', 'order'],
            'documentation': ['doc', 'document', 'comment', 'explain', 'clarify'],
            'testing': ['test', 'verify', 'validate', 'check', 'assert'],
            'security': ['security', 'auth', 'encrypt', 'protect', 'vulnerable'],
            'memory': ['memory', 'remember', 'forget', 'recall', 'store'],
        }
        
        theme_scores = {theme: 0 for theme in theme_keywords}
        
        for insight in insights:
            insight_lower = insight.lower()
            for theme, keywords in theme_keywords.items():
                for keyword in keywords:
                    if keyword in insight_lower:
                        theme_scores[theme] += 1
                        break
        
        # Return themes that appear at least twice
        common_themes = [theme for theme, score in theme_scores.items() if score >= 2]
        return common_themes if common_themes else ['general']
    
    def _generate_pattern_signature(self, topic: str, themes: List[str]) -> str:
        """Generate a unique signature for a pattern."""
        content = f"{topic}:{','.join(sorted(themes))}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _persist_cluster(self, cluster: ReflectionCluster):
        """Persist cluster to Neo4j."""
        driver = self._get_driver()
        
        with driver.session() as session:
            # Create cluster node
            session.run("""
                MERGE (rc:ReflectionCluster {id: $id})
                ON CREATE SET 
                    rc.topic = $topic,
                    rc.pattern_signature = $signature,
                    rc.common_insights = $insights,
                    rc.created_at = datetime(),
                    rc.reflection_count = $count,
                    rc.rule_generated = false
            """, 
                id=cluster.id,
                topic=cluster.topic,
                signature=cluster.pattern_signature,
                insights=cluster.common_insights,
                count=len(cluster.reflections)
            )
            
            # Link reflections to cluster
            for reflection in cluster.reflections:
                session.run("""
                    MATCH (rc:ReflectionCluster {id: $cluster_id})
                    MATCH (r:Reflection {id: $reflection_id})
                    CREATE (r)-[:BELONGS_TO {clustered_at: datetime()}]->(rc)
                    SET r.consolidated = true
                """,
                    cluster_id=cluster.id,
                    reflection_id=reflection['id']
                )
    
    def generate_rules(self, clusters: Optional[List[ReflectionCluster]] = None,
                      min_confidence: Optional[float] = None) -> List[MetaRule]:
        """
        Generate MetaRule nodes from reflection clusters.
        
        Args:
            clusters: Clusters to generate rules from (default: self.clusters)
            min_confidence: Minimum confidence threshold for rule generation
            
        Returns:
            List of generated MetaRule objects
        """
        clusters_to_process = clusters or list(self.clusters.values())
        confidence_threshold = min_confidence or self.min_confidence_for_rule
        
        generated_rules = []
        
        for cluster in clusters_to_process:
            if cluster.rule_generated:
                continue
            
            # Calculate confidence based on cluster size and consistency
            confidence = self._calculate_cluster_confidence(cluster)
            
            if confidence >= confidence_threshold:
                rule = self._create_rule_from_cluster(cluster, confidence)
                if rule:
                    generated_rules.append(rule)
                    self.rules[rule.id] = rule
                    cluster.rule_generated = True
                    
                    # Persist to Neo4j
                    self._persist_rule(rule)
        
        logger.info(f"Generated {len(generated_rules)} rules from {len(clusters_to_process)} clusters")
        return generated_rules
    
    def _calculate_cluster_confidence(self, cluster: ReflectionCluster) -> float:
        """Calculate confidence score for a cluster."""
        # Base confidence from cluster size
        size_factor = min(len(cluster.reflections) / 10.0, 1.0)
        
        # Theme consistency factor
        theme_consistency = len(cluster.common_insights) / max(len(cluster.reflections), 1)
        theme_factor = min(theme_consistency * 3, 1.0)  # Scale up
        
        # Time consistency (reflections clustered in time = higher confidence)
        if len(cluster.reflections) >= 2:
            timestamps = []
            for r in cluster.reflections:
                created_at = r.get('created_at')
                if created_at:
                    if isinstance(created_at, str):
                        try:
                            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        except:
                            continue
                    timestamps.append(created_at)
            
            if len(timestamps) >= 2:
                time_span = max(timestamps) - min(timestamps)
                # Shorter time span = higher consistency
                time_factor = max(0, 1.0 - (time_span.days / 30.0))
            else:
                time_factor = 0.5
        else:
            time_factor = 0.5
        
        # Weighted combination
        confidence = (size_factor * 0.4) + (theme_factor * 0.4) + (time_factor * 0.2)
        return round(confidence, 2)
    
    def _create_rule_from_cluster(self, cluster: ReflectionCluster, 
                                  confidence: float) -> Optional[MetaRule]:
        """Create a MetaRule from a reflection cluster."""
        # Determine rule type from themes
        rule_type = self._determine_rule_type(cluster.common_insights)
        
        # Generate rule name
        name = self._generate_rule_name(cluster.topic, rule_type)
        
        # Generate description
        description = self._generate_rule_description(cluster, confidence)
        
        # Determine target agents
        target_agents = self._determine_target_agents(cluster)
        
        # Generate conditions and actions
        conditions, actions = self._generate_conditions_and_actions(cluster, rule_type)
        
        rule = MetaRule(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            rule_type=rule_type,
            source_cluster_id=cluster.id,
            target_agents=target_agents,
            conditions=conditions,
            actions=actions,
            priority=self._calculate_priority(cluster, confidence),
            effectiveness_score=confidence,
        )
        
        return rule
    
    def _determine_rule_type(self, themes: List[str]) -> str:
        """Determine rule type from themes."""
        type_mapping = {
            'error_handling': 'error_handling',
            'performance': 'optimization',
            'communication': 'communication',
            'planning': 'workflow',
            'documentation': 'documentation',
            'testing': 'quality_assurance',
            'security': 'security',
            'memory': 'memory_management',
        }
        
        for theme in themes:
            if theme in type_mapping:
                return type_mapping[theme]
        
        return 'general'
    
    def _generate_rule_name(self, topic: str, rule_type: str) -> str:
        """Generate a descriptive rule name."""
        # Clean topic for naming
        clean_topic = re.sub(r'[^\w\s]', '', topic).strip()
        clean_topic = re.sub(r'\s+', '_', clean_topic).lower()
        
        timestamp = datetime.utcnow().strftime("%Y%m%d")
        return f"{rule_type}_{clean_topic}_{timestamp}"
    
    def _generate_rule_description(self, cluster: ReflectionCluster, 
                                   confidence: float) -> str:
        """Generate rule description from cluster data."""
        reflection_count = len(cluster.reflections)
        themes_str = ', '.join(cluster.common_insights[:3])
        
        return (
            f"Auto-generated rule from {reflection_count} reflections on "
            f"'{cluster.topic}'. Common themes: {themes_str}. "
            f"Confidence: {confidence:.0%}"
        )
    
    def _determine_target_agents(self, cluster: ReflectionCluster) -> List[str]:
        """Determine which agents this rule applies to."""
        agents = set()
        for reflection in cluster.reflections:
            agent = reflection.get('agent')
            if agent:
                agents.add(agent)
        
        # If no specific agents, apply to all
        if not agents:
            return ['kublai', 'mongke', 'chagatai', 'temujin', 'jochi', 'ogedei']
        
        return sorted(list(agents))
    
    def _generate_conditions_and_actions(self, cluster: ReflectionCluster,
                                         rule_type: str) -> Tuple[List[str], List[str]]:
        """Generate rule conditions and actions based on type."""
        conditions = []
        actions = []
        
        # Base condition on task type
        task_types = set()
        for reflection in cluster.reflections:
            task_type = reflection.get('task_type')
            if task_type:
                task_types.add(task_type)
        
        if task_types:
            conditions.append(f"task_type IN {sorted(list(task_types))}")
        
        # Type-specific conditions and actions
        if rule_type == 'error_handling':
            conditions.append("error_rate > 0.1")
            actions.append("Add try-except blocks with specific exception types")
            actions.append("Log errors with context before retrying")
        elif rule_type == 'optimization':
            conditions.append("execution_time > threshold")
            actions.append("Profile code to identify bottlenecks")
            actions.append("Consider caching frequently accessed data")
        elif rule_type == 'communication':
            conditions.append("multiple_agents_involved")
            actions.append("Use structured message formats")
            actions.append("Include context summaries in handoffs")
        elif rule_type == 'workflow':
            conditions.append("complex_task_sequence")
            actions.append("Break into smaller, verifiable steps")
            actions.append("Document dependencies between steps")
        elif rule_type == 'documentation':
            conditions.append("code_changed_or_created")
            actions.append("Update docstrings for all public functions")
            actions.append("Add examples to complex functions")
        elif rule_type == 'quality_assurance':
            conditions.append("new_feature_implemented")
            actions.append("Write unit tests before marking complete")
            actions.append("Run integration tests if external APIs involved")
        elif rule_type == 'security':
            conditions.append("handling_sensitive_data")
            actions.append("Validate all inputs")
            actions.append("Use parameterized queries")
        elif rule_type == 'memory_management':
            conditions.append("large_data_processing")
            actions.append("Use generators for large datasets")
            actions.append("Clear references when done")
        else:
            actions.append("Review similar past tasks for patterns")
            actions.append("Document learnings for future reference")
        
        return conditions, actions
    
    def _calculate_priority(self, cluster: ReflectionCluster, confidence: float) -> int:
        """Calculate rule priority (1-10, lower is higher priority)."""
        base_priority = 5
        
        # Higher confidence = higher priority (lower number)
        confidence_adjustment = int((1 - confidence) * 3)
        
        # More reflections = more evidence = higher priority
        size_adjustment = max(0, 3 - len(cluster.reflections))
        
        priority = base_priority + confidence_adjustment - size_adjustment
        return max(1, min(10, priority))
    
    def _persist_rule(self, rule: MetaRule):
        """Persist rule to Neo4j."""
        driver = self._get_driver()
        
        with driver.session() as session:
            session.run("""
                CREATE (mr:MetaRule {
                    id: $id,
                    name: $name,
                    description: $description,
                    rule_type: $rule_type,
                    target_agents: $target_agents,
                    conditions: $conditions,
                    actions: $actions,
                    priority: $priority,
                    effectiveness_score: $effectiveness_score,
                    application_count: 0,
                    success_count: 0,
                    created_at: datetime(),
                    status: 'proposed'
                })
            """,
                id=rule.id,
                name=rule.name,
                description=rule.description,
                rule_type=rule.rule_type,
                target_agents=rule.target_agents,
                conditions=rule.conditions,
                actions=rule.actions,
                priority=rule.priority,
                effectiveness_score=rule.effectiveness_score
            )
            
            # Link to source cluster
            session.run("""
                MATCH (mr:MetaRule {id: $rule_id})
                MATCH (rc:ReflectionCluster {id: $cluster_id})
                CREATE (mr)-[:GENERATED_FROM {confidence: $confidence}]->(rc)
                SET rc.rule_generated = true
            """,
                rule_id=rule.id,
                cluster_id=rule.source_cluster_id,
                confidence=rule.effectiveness_score
            )
    
    def inject_rules(self, rules: Optional[List[MetaRule]] = None,
                    agent_filter: Optional[List[str]] = None,
                    dry_run: bool = False) -> Dict[str, List[str]]:
        """
        Prepare rules for injection into agent SOUL files.
        
        Args:
            rules: Rules to inject (default: all proposed rules)
            agent_filter: Only inject for specific agents
            dry_run: If True, return what would be injected without persisting
            
        Returns:
            Dict mapping agent IDs to list of rule IDs to be injected
        """
        rules_to_inject = rules or [
            r for r in self.rules.values() 
            if r.status == 'proposed'
        ]
        
        injection_plan: Dict[str, List[str]] = {}
        
        for rule in rules_to_inject:
            # Filter by agent if specified
            if agent_filter:
                target_agents = [a for a in rule.target_agents if a in agent_filter]
            else:
                target_agents = rule.target_agents
            
            for agent in target_agents:
                if agent not in injection_plan:
                    injection_plan[agent] = []
                injection_plan[agent].append(rule.id)
        
        if not dry_run:
            # Update rule status to active
            driver = self._get_driver()
            with driver.session() as session:
                for rule in rules_to_inject:
                    session.run("""
                        MATCH (mr:MetaRule {id: $id})
                        SET mr.status = 'active', mr.activated_at = datetime()
                    """, id=rule.id)
                    rule.status = 'active'
        
        logger.info(f"Injection plan: {len(injection_plan)} agents, "
                   f"{sum(len(v) for v in injection_plan.values())} rules")
        return injection_plan
    
    def evaluate_rules(self, rule_ids: Optional[List[str]] = None,
                      evaluation_window_days: int = 7) -> Dict[str, Dict[str, Any]]:
        """
        Track and evaluate rule effectiveness.
        
        Args:
            rule_ids: Specific rules to evaluate (default: all active rules)
            evaluation_window_days: Days to look back for effectiveness metrics
            
        Returns:
            Dict mapping rule IDs to evaluation results
        """
        cutoff_date = datetime.utcnow() - timedelta(days=evaluation_window_days)
        
        rules_to_evaluate = []
        if rule_ids:
            rules_to_evaluate = [self.rules.get(rid) for rid in rule_ids if rid in self.rules]
        else:
            rules_to_evaluate = [r for r in self.rules.values() if r.status == 'active']
        
        results = {}
        driver = self._get_driver()
        
        with driver.session() as session:
            for rule in rules_to_evaluate:
                # Count applications in window
                app_result = session.run("""
                    MATCH (mr:MetaRule {id: $rule_id})<-[:USED_RULE]-(t:Task)
                    WHERE t.created_at > $cutoff
                    RETURN count(t) as applications,
                           count(CASE WHEN t.status = 'completed' THEN 1 END) as successes
                """, rule_id=rule.id, cutoff=cutoff_date.isoformat())
                
                record = app_result.single()
                if record:
                    applications = record['applications']
                    successes = record['successes']
                    
                    # Update rule stats
                    rule.application_count = applications
                    rule.success_count = successes
                    rule.last_evaluated = datetime.utcnow()
                    
                    # Calculate effectiveness
                    if applications > 0:
                        success_rate = successes / applications
                        rule.effectiveness_score = round(
                            (rule.effectiveness_score * 0.3) + (success_rate * 0.7), 2
                        )
                    
                    # Determine effectiveness level
                    if rule.effectiveness_score >= 0.8:
                        effectiveness = RuleEffectiveness.HIGH
                    elif rule.effectiveness_score >= 0.5:
                        effectiveness = RuleEffectiveness.MEDIUM
                    elif rule.effectiveness_score > 0:
                        effectiveness = RuleEffectiveness.LOW
                    else:
                        effectiveness = RuleEffectiveness.UNKNOWN
                    
                    # Update Neo4j
                    session.run("""
                        MATCH (mr:MetaRule {id: $id})
                        SET mr.application_count = $applications,
                            mr.success_count = $successes,
                            mr.effectiveness_score = $score,
                            mr.last_evaluated = datetime(),
                            mr.effectiveness_level = $level
                    """,
                        id=rule.id,
                        applications=applications,
                        successes=successes,
                        score=rule.effectiveness_score,
                        level=effectiveness.value
                    )
                    
                    results[rule.id] = {
                        'rule_name': rule.name,
                        'applications': applications,
                        'successes': successes,
                        'success_rate': successes / max(applications, 1),
                        'effectiveness_score': rule.effectiveness_score,
                        'effectiveness_level': effectiveness.value,
                    }
        
        logger.info(f"Evaluated {len(rules_to_evaluate)} rules")
        return results
    
    def deprecate_low_effectiveness_rules(self, threshold: float = 0.3) -> List[str]:
        """
        Deprecate rules with low effectiveness scores.
        
        Args:
            threshold: Minimum effectiveness score to keep active
            
        Returns:
            List of deprecated rule IDs
        """
        deprecated = []
        driver = self._get_driver()
        
        with driver.session() as session:
            result = session.run("""
                MATCH (mr:MetaRule)
                WHERE mr.status = 'active'
                  AND mr.effectiveness_score < $threshold
                  AND mr.application_count > 5
                SET mr.status = 'deprecated',
                    mr.deprecated_at = datetime(),
                    mr.deprecation_reason = 'Low effectiveness score'
                RETURN mr.id as id, mr.name as name
            """, threshold=threshold)
            
            for record in result:
                deprecated.append(record['id'])
                if record['id'] in self.rules:
                    self.rules[record['id']].status = 'deprecated'
                logger.info(f"Deprecated rule: {record['name']}")
        
        return deprecated
    
    def get_rules_for_agent(self, agent_id: str, 
                           rule_type: Optional[str] = None) -> List[MetaRule]:
        """Get all active rules applicable to an agent."""
        driver = self._get_driver()
        rules = []
        
        with driver.session() as session:
            query = """
                MATCH (mr:MetaRule)
                WHERE mr.status = 'active'
                  AND $agent_id IN mr.target_agents
            """
            params = {'agent_id': agent_id}
            
            if rule_type:
                query += " AND mr.rule_type = $rule_type"
                params['rule_type'] = rule_type
            
            query += " RETURN mr ORDER BY mr.priority, mr.effectiveness_score DESC"
            
            result = session.run(query, **params)
            
            for record in result:
                node = record['mr']
                rule = MetaRule(
                    id=node['id'],
                    name=node['name'],
                    description=node['description'],
                    rule_type=node['rule_type'],
                    source_cluster_id='',  # Not needed for retrieval
                    target_agents=node['target_agents'],
                    conditions=node['conditions'],
                    actions=node['actions'],
                    priority=node['priority'],
                    effectiveness_score=node['effectiveness_score'],
                    application_count=node.get('application_count', 0),
                    success_count=node.get('success_count', 0),
                    status=node['status'],
                )
                rules.append(rule)
        
        return rules
    
    def get_learning_stats(self) -> Dict[str, Any]:
        """Get statistics about the meta-learning system."""
        driver = self._get_driver()
        
        with driver.session() as session:
            # Count reflections
            reflection_count = session.run("""
                MATCH (r:Reflection) RETURN count(r) as count
            """).single()['count']
            
            # Count clusters
            cluster_count = session.run("""
                MATCH (rc:ReflectionCluster) RETURN count(rc) as count
            """).single()['count']
            
            # Count rules by status
            rules_by_status = session.run("""
                MATCH (mr:MetaRule)
                RETURN mr.status as status, count(mr) as count
            """).data()
            
            # Average effectiveness
            avg_effectiveness = session.run("""
                MATCH (mr:MetaRule)
                WHERE mr.effectiveness_score > 0
                RETURN avg(mr.effectiveness_score) as avg
            """).single()['avg'] or 0
        
        return {
            'total_reflections': reflection_count,
            'total_clusters': cluster_count,
            'rules_by_status': {r['status']: r['count'] for r in rules_by_status},
            'average_effectiveness': round(avg_effectiveness, 2),
            'in_memory_clusters': len(self.clusters),
            'in_memory_rules': len(self.rules),
        }


# Convenience functions for standalone usage
def run_meta_learning_cycle(engine: Optional[MetaLearningEngine] = None,
                            min_cluster_size: int = 3,
                            generate_rules: bool = True,
                            inject: bool = False) -> Dict[str, Any]:
    """
    Run a complete meta-learning cycle.
    
    Args:
        engine: MetaLearningEngine instance (creates new if None)
        min_cluster_size: Minimum reflections per cluster
        generate_rules: Whether to generate rules from clusters
        inject: Whether to prepare rules for injection
        
    Returns:
        Summary of the learning cycle
    """
    if engine is None:
        engine = MetaLearningEngine()
    
    try:
        # Step 1: Cluster reflections
        clusters = engine.cluster_reflections(min_cluster_size=min_cluster_size)
        
        # Step 2: Generate rules
        rules = []
        if generate_rules and clusters:
            rules = engine.generate_rules(clusters)
        
        # Step 3: Prepare injection
        injection_plan = {}
        if inject and rules:
            injection_plan = engine.inject_rules(rules, dry_run=True)
        
        return {
            'success': True,
            'clusters_created': len(clusters),
            'rules_generated': len(rules),
            'injection_plan': injection_plan,
            'stats': engine.get_learning_stats(),
        }
    except Exception as e:
        logger.error(f"Meta-learning cycle failed: {e}")
        return {
            'success': False,
            'error': str(e),
        }
    finally:
        engine.close()
