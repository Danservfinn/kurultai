#!/usr/bin/env python3
"""
Notification Dispatcher for Kurultai

Dispatches events to subscribed agents using the SUBSCRIBES_TO relationship graph.
Coordinates with Temüjin's HMAC signing for secure message delivery.

Features:
- Filter events by subscription criteria
- Log all notifications for audit trail
- Handle delivery failures with retry logic
- Sign messages using HMAC (coordinated with Temüjin)

Author: Kublai (Orchestrator)
Date: 2026-02-09
"""

import json
import uuid
import hmac
import hashlib
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum

from neo4j import GraphDatabase

# Import subscription manager for subscriber lookup
from .subscription_manager import SubscriptionManager


class DeliveryStatus(Enum):
    """Status of a notification delivery attempt."""
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"
    EXPIRED = "expired"


@dataclass
class Notification:
    """Represents a notification to be dispatched."""
    id: str
    topic: str
    payload: Dict[str, Any]
    publisher: str
    timestamp: datetime
    signature: Optional[str] = None


@dataclass
class DeliveryResult:
    """Result of a delivery attempt."""
    notification_id: str
    subscriber_id: str
    status: DeliveryStatus
    timestamp: datetime
    error: Optional[str] = None
    retry_count: int = 0


class NotificationDispatcher:
    """
    Dispatches events to subscribed agents.
    
    Uses HMAC signing for message integrity (coordinated with Temüjin's security work).
    Logs all notifications to Neo4j for audit trail.
    """
    
    def __init__(
        self,
        neo4j_driver=None,
        subscription_manager=None,
        hmac_secret: Optional[str] = None,
        max_retries: int = 3
    ):
        """
        Initialize the dispatcher.
        
        Args:
            neo4j_driver: Neo4j driver instance
            subscription_manager: SubscriptionManager instance
            hmac_secret: Secret key for HMAC signing (should match Temüjin's)
            max_retries: Maximum delivery retry attempts
        """
        self.driver = neo4j_driver or self._create_driver()
        self.subscription_manager = subscription_manager or SubscriptionManager(self.driver)
        self.hmac_secret = hmac_secret or self._load_hmac_secret()
        self.max_retries = max_retries
        self.logger = logging.getLogger(__name__)
    
    def _create_driver(self):
        """Create Neo4j driver from environment."""
        import os
        uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
        password = os.environ.get('NEO4J_PASSWORD')
        if not password:
            raise ValueError("NEO4J_PASSWORD not set")
        return GraphDatabase.driver(uri, auth=('neo4j', password))
    
    def _load_hmac_secret(self) -> str:
        """Load HMAC secret from environment."""
        import os
        secret = os.environ.get('KURULTAI_HMAC_SECRET')
        if not secret:
            # Fallback for development - in production this should fail
            self.logger.warning("KURULTAI_HMAC_SECRET not set, using fallback")
            secret = "dev-secret-do-not-use-in-production"
        return secret
    
    def _sign_message(self, notification: Notification) -> str:
        """
        Create HMAC signature for a notification.
        Coordinates with Temüjin's HMAC signing implementation.
        
        Args:
            notification: Notification to sign
            
        Returns:
            HMAC hex digest signature
        """
        # Create canonical message representation
        message_data = {
            'id': notification.id,
            'topic': notification.topic,
            'payload': notification.payload,
            'publisher': notification.publisher,
            'timestamp': notification.timestamp.isoformat()
        }
        message = json.dumps(message_data, sort_keys=True, separators=(',', ':'))
        
        # Generate HMAC signature
        signature = hmac.new(
            self.hmac_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    def _verify_signature(self, notification: Notification, signature: str) -> bool:
        """
        Verify HMAC signature of a notification.
        
        Args:
            notification: Notification to verify
            signature: Expected signature
            
        Returns:
            True if signature is valid
        """
        expected = self._sign_message(notification)
        return hmac.compare_digest(expected, signature)
    
    def dispatch(
        self,
        event_type: str,
        payload: Dict[str, Any],
        publisher: str = 'system',
        target: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Dispatch an event to all subscribed agents.
        
        Args:
            event_type: Type/topic of the event (e.g., 'research.completed')
            payload: Event data to deliver
            publisher: Agent or system that published the event
            target: Optional specific target agent (bypasses subscription lookup)
            
        Returns:
            Dict with dispatch summary including delivery results
        """
        notification_id = str(uuid.uuid4())
        timestamp = datetime.now()
        
        # Create notification object
        notification = Notification(
            id=notification_id,
            topic=event_type,
            payload=payload,
            publisher=publisher,
            timestamp=timestamp
        )
        
        # Sign the notification
        notification.signature = self._sign_message(notification)
        
        # Find subscribers
        if target:
            # Direct delivery to specific target
            subscribers = [{'agent_id': target, 'subscription_id': None, 'filter': None}]
        else:
            # Lookup subscribers based on topic and filter
            subscribers = self.subscription_manager.get_subscribers(event_type, payload)
        
        # Log notification
        self._log_notification(notification, len(subscribers))
        
        # Deliver to each subscriber
        delivery_results = []
        for sub in subscribers:
            result = self._deliver(notification, sub['agent_id'])
            delivery_results.append(asdict(result))
        
        # Calculate summary statistics
        successful = sum(1 for r in delivery_results if r['status'] == DeliveryStatus.DELIVERED)
        failed = sum(1 for r in delivery_results if r['status'] == DeliveryStatus.FAILED)
        
        return {
            'status': 'dispatched',
            'notification_id': notification_id,
            'topic': event_type,
            'publisher': publisher,
            'timestamp': timestamp.isoformat(),
            'subscriber_count': len(subscribers),
            'successful_deliveries': successful,
            'failed_deliveries': failed,
            'deliveries': delivery_results
        }
    
    def _log_notification(self, notification: Notification, subscriber_count: int):
        """
        Log notification to Neo4j for audit trail.
        
        Args:
            notification: Notification that was dispatched
            subscriber_count: Number of subscribers
        """
        with self.driver.session() as session:
            session.run("""
                CREATE (n:NotificationLog {
                    id: $id,
                    topic: $topic,
                    payload: $payload,
                    publisher: $publisher,
                    timestamp: $timestamp,
                    signature: $signature,
                    subscriber_count: $subscriber_count,
                    status: 'dispatched'
                })
            """, {
                'id': notification.id,
                'topic': notification.topic,
                'payload': json.dumps(notification.payload),
                'publisher': notification.publisher,
                'timestamp': notification.timestamp,
                'signature': notification.signature,
                'subscriber_count': subscriber_count
            })
    
    def _deliver(
        self,
        notification: Notification,
        subscriber_id: str
    ) -> DeliveryResult:
        """
        Deliver notification to a specific subscriber.
        
        Args:
            notification: Notification to deliver
            subscriber_id: Target agent ID
            
        Returns:
            DeliveryResult with status
        """
        result = DeliveryResult(
            notification_id=notification.id,
            subscriber_id=subscriber_id,
            status=DeliveryStatus.PENDING,
            timestamp=datetime.now()
        )
        
        try:
            # Attempt delivery
            delivery_success = self._send_to_agent(notification, subscriber_id)
            
            if delivery_success:
                result.status = DeliveryStatus.DELIVERED
                self._log_delivery(notification.id, subscriber_id, 'delivered')
            else:
                result.status = DeliveryStatus.FAILED
                result.error = 'Delivery rejected by agent'
                self._log_delivery(notification.id, subscriber_id, 'failed', result.error)
                
                # Trigger retry logic
                self._schedule_retry(notification, subscriber_id)
                
        except Exception as e:
            result.status = DeliveryStatus.FAILED
            result.error = str(e)
            self.logger.error(f"Delivery failed to {subscriber_id}: {e}")
            self._log_delivery(notification.id, subscriber_id, 'failed', str(e))
            
            # Trigger retry logic
            self._schedule_retry(notification, subscriber_id)
        
        return result
    
    def _send_to_agent(self, notification: Notification, agent_id: str) -> bool:
        """
        Send notification to an agent.
        
        This is a placeholder for the actual delivery mechanism.
        In production, this would:
        - Send via Signal message
        - Trigger OpenClaw session
        - Queue for agent pickup
        
        Args:
            notification: Notification to send
            agent_id: Target agent
            
        Returns:
            True if delivery was successful
        """
        # TODO: Integrate with actual agent delivery mechanism
        # For now, simulate successful delivery
        self.logger.info(f"Would deliver notification {notification.id} to {agent_id}")
        return True
    
    def _log_delivery(
        self,
        notification_id: str,
        subscriber_id: str,
        status: str,
        error: Optional[str] = None
    ):
        """
        Log delivery attempt to Neo4j.
        
        Args:
            notification_id: Notification UUID
            subscriber_id: Target agent
            status: Delivery status
            error: Optional error message
        """
        with self.driver.session() as session:
            if status == 'delivered':
                session.run("""
                    MATCH (n:NotificationLog {id: $notif_id})
                    MATCH (a:Agent {id: $agent_id})
                    CREATE (n)-[d:DELIVERED_TO {
                        timestamp: datetime(),
                        status: 'delivered'
                    }]->(a)
                """, {
                    'notif_id': notification_id,
                    'agent_id': subscriber_id
                })
            else:
                session.run("""
                    MATCH (n:NotificationLog {id: $notif_id})
                    MATCH (a:Agent {id: $agent_id})
                    CREATE (n)-[d:FAILED_DELIVERY {
                        timestamp: datetime(),
                        status: 'failed',
                        reason: $error
                    }]->(a)
                """, {
                    'notif_id': notification_id,
                    'agent_id': subscriber_id,
                    'error': error or 'Unknown error'
                })
    
    def _schedule_retry(self, notification: Notification, subscriber_id: str):
        """
        Schedule a retry for failed delivery.
        
        Args:
            notification: Failed notification
            subscriber_id: Target agent
        """
        # In production, this would queue to a retry system
        # For now, just log the retry intent
        self.logger.info(f"Retry scheduled for {notification.id} to {subscriber_id}")
    
    def get_notification_log(
        self,
        topic: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get notification log entries.
        
        Args:
            topic: Filter by topic
            status: Filter by status
            limit: Maximum results
            
        Returns:
            List of notification log entries
        """
        with self.driver.session() as session:
            query = """
                MATCH (n:NotificationLog)
                WHERE 1=1
            """
            params = {}
            
            if topic:
                query += " AND n.topic = $topic"
                params['topic'] = topic
            
            if status:
                query += " AND n.status = $status"
                params['status'] = status
            
            query += """
                RETURN n.id as id,
                       n.topic as topic,
                       n.payload as payload,
                       n.publisher as publisher,
                       n.timestamp as timestamp,
                       n.signature as signature,
                       n.status as status,
                       n.subscriber_count as subscriber_count
                ORDER BY n.timestamp DESC
                LIMIT $limit
            """
            params['limit'] = limit
            
            result = session.run(query, params)
            
            logs = []
            for record in result:
                payload_json = record.get('payload')
                logs.append({
                    'id': record['id'],
                    'topic': record['topic'],
                    'payload': json.loads(payload_json) if payload_json else None,
                    'publisher': record['publisher'],
                    'timestamp': record['timestamp'],
                    'signature': record['signature'],
                    'status': record['status'],
                    'subscriber_count': record['subscriber_count']
                })
        
        return logs
    
    def close(self):
        """Close connections."""
        if self.subscription_manager:
            self.subscription_manager.close()
        elif self.driver:
            self.driver.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
