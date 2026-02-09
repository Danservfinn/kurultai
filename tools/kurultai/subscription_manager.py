#!/usr/bin/env python3
"""
Subscription Manager for Kurultai

Manages cross-agent event subscriptions using Neo4j SUBSCRIBES_TO relationships.
Coordinates with Temüjin's HMAC signing for secure message delivery.

Author: Kublai (Orchestrator)
Date: 2026-02-09
"""

import json
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass

from neo4j import GraphDatabase


@dataclass
class Subscription:
    """Represents a subscription relationship between agents."""
    id: str
    subscriber_id: str
    target_id: str
    topic: str
    filter_criteria: Optional[Dict[str, Any]]
    created_at: datetime


class SubscriptionManager:
    """
    Manages agent subscriptions for cross-agent event notifications.
    
    Uses Neo4j SUBSCRIBES_TO relationships with properties:
    - id: Unique subscription identifier
    - topic: Event topic pattern (e.g., 'research.completed', 'task.*')
    - filter: JSON criteria for filtering events
    - created_at: When subscription was created
    """
    
    def __init__(self, neo4j_driver=None):
        """Initialize with optional Neo4j driver."""
        self.driver = neo4j_driver or self._create_driver()
    
    def _create_driver(self):
        """Create Neo4j driver from environment."""
        import os
        uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
        password = os.environ.get('NEO4J_PASSWORD')
        if not password:
            raise ValueError("NEO4J_PASSWORD not set")
        return GraphDatabase.driver(uri, auth=('neo4j', password))
    
    def subscribe(
        self,
        subscriber: str,
        topic: str,
        filter_criteria: Optional[Dict[str, Any]] = None,
        target: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a subscription for an agent to receive events.
        
        Args:
            subscriber: Agent ID subscribing to events (e.g., 'kublai')
            topic: Event topic pattern to subscribe to (e.g., 'research.completed')
            filter_criteria: Optional JSON criteria to filter events
            target: Optional specific target agent to subscribe to (default: all agents)
            
        Returns:
            Dict with subscription details including id
        """
        subscription_id = str(uuid.uuid4())
        filter_json = json.dumps(filter_criteria) if filter_criteria else None
        
        with self.driver.session() as session:
            # Ensure subscriber agent node exists
            session.run("""
                MERGE (a:Agent {id: $agent_id})
                ON CREATE SET a.created_at = datetime()
            """, agent_id=subscriber)
            
            if target:
                # Subscribe to specific target agent
                session.run("""
                    MERGE (target:Agent {id: $target_id})
                    ON CREATE SET target.created_at = datetime()
                    MERGE (sub:Agent {id: $subscriber_id})
                    CREATE (sub)-[s:SUBSCRIBES_TO {
                        id: $sub_id,
                        topic: $topic,
                        filter: $filter,
                        created_at: datetime(),
                        subscriber_id: $subscriber_id,
                        target_id: $target_id
                    }]->(target)
                    RETURN s.id as id
                """, {
                    'subscriber_id': subscriber,
                    'target_id': target,
                    'sub_id': subscription_id,
                    'topic': topic,
                    'filter': filter_json
                })
            else:
                # Subscribe to all agents (wildcard target)
                session.run("""
                    MERGE (sub:Agent {id: $subscriber_id})
                    CREATE (sub)-[s:SUBSCRIBES_TO {
                        id: $sub_id,
                        topic: $topic,
                        filter: $filter,
                        created_at: datetime(),
                        subscriber_id: $subscriber_id,
                        target_id: '*'
                    }]->(all:AllAgents)
                    ON CREATE SET all.created_at = datetime()
                    RETURN s.id as id
                """, {
                    'subscriber_id': subscriber,
                    'sub_id': subscription_id,
                    'topic': topic,
                    'filter': filter_json
                })
        
        return {
            'status': 'success',
            'subscription_id': subscription_id,
            'subscriber': subscriber,
            'target': target or '*',
            'topic': topic,
            'filter': filter_criteria,
            'created_at': datetime.now().isoformat()
        }
    
    def unsubscribe(self, subscriber: str, topic: str, target: Optional[str] = None) -> Dict[str, Any]:
        """
        Remove a subscription.
        
        Args:
            subscriber: Agent ID that owns the subscription
            topic: Topic pattern to unsubscribe from
            target: Optional specific target (if None, removes all matching subscriptions)
            
        Returns:
            Dict with removal status
        """
        with self.driver.session() as session:
            if target:
                result = session.run("""
                    MATCH (sub:Agent {id: $subscriber_id})-[s:SUBSCRIBES_TO {topic: $topic}]->(target:Agent {id: $target_id})
                    DELETE s
                    RETURN count(s) as removed
                """, {
                    'subscriber_id': subscriber,
                    'topic': topic,
                    'target_id': target
                })
            else:
                result = session.run("""
                    MATCH (sub:Agent {id: $subscriber_id})-[s:SUBSCRIBES_TO {topic: $topic}]->()
                    DELETE s
                    RETURN count(s) as removed
                """, {
                    'subscriber_id': subscriber,
                    'topic': topic
                })
            
            removed_count = result.single()['removed']
        
        return {
            'status': 'success',
            'removed_count': removed_count,
            'subscriber': subscriber,
            'topic': topic,
            'target': target
        }
    
    def get_subscribers(self, topic: str, payload: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Get all subscribers for a given topic, optionally filtering by payload.
        
        Args:
            topic: Event topic that was published
            payload: Optional event payload to filter against subscription criteria
            
        Returns:
            List of subscriber dictionaries with agent info and filter criteria
        """
        with self.driver.session() as session:
            # Get all subscriptions matching this topic
            # Using pattern matching for wildcard topics (e.g., 'research.*' matches 'research.completed')
            result = session.run("""
                MATCH (sub:Agent)-[s:SUBSCRIBES_TO]->(target)
                WHERE s.topic = $topic 
                   OR s.topic = '*'
                   OR $topic STARTS WITH replace(s.topic, '.*', '.')
                   OR $topic ENDS WITH replace(s.topic, '*.,', '.')
                RETURN sub.id as subscriber_id,
                       s.topic as subscription_topic,
                       s.filter as filter,
                       s.id as subscription_id,
                       s.target_id as target_id
            """, {'topic': topic})
            
            subscribers = []
            for record in result:
                filter_json = record.get('filter')
                filter_criteria = json.loads(filter_json) if filter_json else None
                
                # Apply filter criteria if present and payload provided
                if filter_criteria and payload:
                    if not self._matches_filter(payload, filter_criteria):
                        continue
                
                subscribers.append({
                    'agent_id': record['subscriber_id'],
                    'subscription_id': record['subscription_id'],
                    'topic': record['subscription_topic'],
                    'filter': filter_criteria,
                    'target_id': record['target_id']
                })
        
        return subscribers
    
    def _matches_filter(self, payload: Dict[str, Any], criteria: Dict[str, Any]) -> bool:
        """
        Check if payload matches filter criteria.
        
        Supports operators:
        - Exact match: {"status": "completed"}
        - Comparison: {"confidence": {"$gte": 0.8}}
        - In list: {"type": {"$in": ["research", "analysis"]}}
        - Exists: {"result": {"$exists": true}}
        """
        for key, condition in criteria.items():
            value = payload.get(key)
            
            if isinstance(condition, dict):
                # Operator-based filtering
                for op, target in condition.items():
                    if op == '$gte' and (value is None or value < target):
                        return False
                    elif op == '$gt' and (value is None or value <= target):
                        return False
                    elif op == '$lte' and (value is None or value > target):
                        return False
                    elif op == '$lt' and (value is None or value >= target):
                        return False
                    elif op == '$eq' and value != target:
                        return False
                    elif op == '$ne' and value == target:
                        return False
                    elif op == '$in' and value not in target:
                        return False
                    elif op == '$nin' and value in target:
                        return False
                    elif op == '$exists':
                        if target and value is None:
                            return False
                        if not target and value is not None:
                            return False
            else:
                # Exact match
                if value != condition:
                    return False
        
        return True
    
    def list_subscriptions(self, agent: str) -> List[Dict[str, Any]]:
        """
        List all subscriptions for an agent.
        
        Args:
            agent: Agent ID to list subscriptions for
            
        Returns:
            List of subscription dictionaries
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (sub:Agent {id: $agent_id})-[s:SUBSCRIBES_TO]->(target)
                RETURN s.id as id,
                       s.topic as topic,
                       s.filter as filter,
                       s.created_at as created_at,
                       s.target_id as target_id,
                       target.id as target_agent_id
            """, {'agent_id': agent})
            
            subscriptions = []
            for record in result:
                filter_json = record.get('filter')
                subscriptions.append({
                    'id': record['id'],
                    'topic': record['topic'],
                    'filter': json.loads(filter_json) if filter_json else None,
                    'created_at': record['created_at'],
                    'target_id': record['target_id'] or record['target_agent_id']
                })
        
        return subscriptions
    
    def get_subscription(self, subscription_id: str) -> Optional[Dict[str, Any]]:
        """
        Get details of a specific subscription.
        
        Args:
            subscription_id: UUID of the subscription
            
        Returns:
            Subscription dict or None if not found
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (sub:Agent)-[s:SUBSCRIBES_TO {id: $sub_id}]->(target)
                RETURN s.id as id,
                       sub.id as subscriber_id,
                       s.topic as topic,
                       s.filter as filter,
                       s.created_at as created_at,
                       s.target_id as target_id,
                       target.id as target_agent_id
            """, {'sub_id': subscription_id})
            
            record = result.single()
            if not record:
                return None
            
            filter_json = record.get('filter')
            return {
                'id': record['id'],
                'subscriber_id': record['subscriber_id'],
                'topic': record['topic'],
                'filter': json.loads(filter_json) if filter_json else None,
                'created_at': record['created_at'],
                'target_id': record['target_id'] or record['target_agent_id']
            }
    
    def close(self):
        """Close Neo4j driver connection."""
        if self.driver:
            self.driver.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
