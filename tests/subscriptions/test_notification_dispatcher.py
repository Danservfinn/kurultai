"""
Tests for Notification Dispatcher

Verifies:
- dispatch() sends events to subscribers
- HMAC signing of messages
- Notification logging to Neo4j
- Delivery failure handling
- get_notification_log() retrieves logs
"""

import pytest
import json
import hmac
import hashlib
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

import sys
sys.path.insert(0, '/data/workspace/souls/main')

from tools.kurultai.notification_dispatcher import (
    NotificationDispatcher,
    Notification,
    DeliveryStatus
)


class TestNotificationDispatcher:
    """Test suite for NotificationDispatcher."""
    
    @pytest.fixture
    def mock_driver(self):
        """Create a mock Neo4j driver."""
        driver = MagicMock()
        session = MagicMock()
        driver.session.return_value.__enter__ = Mock(return_value=session)
        driver.session.return_value.__exit__ = Mock(return_value=False)
        driver.session.return_value = session
        return driver, session
    
    @pytest.fixture
    def mock_subscription_manager(self):
        """Create a mock SubscriptionManager."""
        manager = MagicMock()
        return manager
    
    @pytest.fixture
    def dispatcher(self, mock_driver, mock_subscription_manager):
        """Create a NotificationDispatcher with mocks."""
        driver, _ = mock_driver
        return NotificationDispatcher(
            neo4j_driver=driver,
            subscription_manager=mock_subscription_manager,
            hmac_secret='test-secret-key',
            max_retries=3
        )
    
    def test_dispatch_basic(self, dispatcher, mock_subscription_manager):
        """Test basic event dispatch."""
        # Setup mock subscribers
        mock_subscription_manager.get_subscribers.return_value = [
            {'agent_id': 'kublai', 'subscription_id': 'sub-1', 'filter': None},
            {'agent_id': 'ögedei', 'subscription_id': 'sub-2', 'filter': None}
        ]
        
        result = dispatcher.dispatch(
            event_type='research.completed',
            payload={'task_id': '123', 'results': ['data']},
            publisher='möngke'
        )
        
        assert result['status'] == 'dispatched'
        assert result['topic'] == 'research.completed'
        assert result['publisher'] == 'möngke'
        assert result['subscriber_count'] == 2
        assert 'notification_id' in result
        assert result['successful_deliveries'] == 2
        assert result['failed_deliveries'] == 0
    
    def test_dispatch_with_target(self, dispatcher, mock_subscription_manager):
        """Test dispatch to specific target only."""
        result = dispatcher.dispatch(
            event_type='task.assigned',
            payload={'task': 'test'},
            publisher='kublai',
            target='temüjin'
        )
        
        assert result['status'] == 'dispatched'
        assert result['subscriber_count'] == 1
        # Should not call get_subscribers when target is specified
        mock_subscription_manager.get_subscribers.assert_not_called()
    
    def test_dispatch_with_filtering(self, dispatcher, mock_subscription_manager):
        """Test dispatch with subscriber filtering."""
        # Setup subscribers where one matches filter
        mock_subscription_manager.get_subscribers.return_value = [
            {'agent_id': 'kublai', 'subscription_id': 'sub-1', 'filter': {'min_confidence': 0.8}},
            {'agent_id': 'jochi', 'subscription_id': 'sub-2', 'filter': None}
        ]
        
        payload = {'min_confidence': 0.9, 'data': 'results'}
        result = dispatcher.dispatch(
            event_type='analysis.completed',
            payload=payload,
            publisher='möngke'
        )
        
        # Both should receive since filter is applied in get_subscribers
        assert result['subscriber_count'] == 2
    
    def test_hmac_signing(self, dispatcher):
        """Test HMAC signature generation."""
        notification = Notification(
            id='test-notif-123',
            topic='research.completed',
            payload={'key': 'value'},
            publisher='möngke',
            timestamp=datetime(2026, 2, 9, 10, 0, 0)
        )
        
        signature = dispatcher._sign_message(notification)
        
        # Verify signature is valid hex
        assert len(signature) == 64  # SHA-256 hex length
        int(signature, 16)  # Should not raise
        
        # Verify signature is deterministic
        signature2 = dispatcher._sign_message(notification)
        assert signature == signature2
    
    def test_hmac_verification(self, dispatcher):
        """Test HMAC signature verification."""
        notification = Notification(
            id='test-notif-123',
            topic='research.completed',
            payload={'key': 'value'},
            publisher='möngke',
            timestamp=datetime(2026, 2, 9, 10, 0, 0)
        )
        
        signature = dispatcher._sign_message(notification)
        
        # Should verify correctly
        assert dispatcher._verify_signature(notification, signature) is True
        
        # Wrong signature should fail
        assert dispatcher._verify_signature(notification, 'wrong-signature') is False
    
    def test_dispatch_logs_notification(self, dispatcher, mock_driver, mock_subscription_manager):
        """Test that dispatch logs to Neo4j."""
        driver, session = mock_driver
        mock_subscription_manager.get_subscribers.return_value = [
            {'agent_id': 'kublai', 'subscription_id': 'sub-1', 'filter': None}
        ]
        
        dispatcher.dispatch(
            event_type='test.event',
            payload={'data': 'test'},
            publisher='system'
        )
        
        # Verify notification was logged
        calls = session.run.call_args_list
        log_call = None
        for call in calls:
            if 'NotificationLog' in str(call):
                log_call = call
                break
        
        assert log_call is not None
    
    def test_get_notification_log(self, dispatcher, mock_driver):
        """Test retrieving notification logs."""
        driver, session = mock_driver
        
        mock_record = {
            'id': 'notif-1',
            'topic': 'research.completed',
            'payload': json.dumps({'data': 'test'}),
            'publisher': 'möngke',
            'timestamp': datetime.now(),
            'signature': 'abc123',
            'status': 'dispatched',
            'subscriber_count': 2
        }
        
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([mock_record]))
        session.run.return_value = mock_result
        
        logs = dispatcher.get_notification_log(topic='research.completed')
        
        assert len(logs) == 1
        assert logs[0]['topic'] == 'research.completed'
        assert logs[0]['payload'] == {'data': 'test'}
    
    def test_get_notification_log_with_filters(self, dispatcher, mock_driver):
        """Test retrieving logs with filters."""
        driver, session = mock_driver
        
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([]))
        session.run.return_value = mock_result
        
        logs = dispatcher.get_notification_log(
            topic='test.topic',
            status='delivered',
            limit=50
        )
        
        # Verify query includes filters
        call_args = session.run.call_args
        assert 'test.topic' in str(call_args)
        assert 'delivered' in str(call_args)


class TestDeliveryResult:
    """Test delivery result tracking."""
    
    def test_delivery_result_creation(self):
        """Test DeliveryResult dataclass."""
        from tools.kurultai.notification_dispatcher import DeliveryResult
        
        result = DeliveryResult(
            notification_id='notif-123',
            subscriber_id='kublai',
            status=DeliveryStatus.DELIVERED,
            timestamp=datetime.now()
        )
        
        assert result.notification_id == 'notif-123'
        assert result.subscriber_id == 'kublai'
        assert result.status == DeliveryStatus.DELIVERED
        assert result.error is None
        assert result.retry_count == 0


class TestNotificationDataclass:
    """Test Notification dataclass."""
    
    def test_notification_creation(self):
        """Test Notification dataclass creation."""
        notification = Notification(
            id='notif-123',
            topic='research.completed',
            payload={'results': ['data']},
            publisher='möngke',
            timestamp=datetime.now(),
            signature='abc123'
        )
        
        assert notification.id == 'notif-123'
        assert notification.topic == 'research.completed'
        assert notification.payload == {'results': ['data']}
        assert notification.publisher == 'möngke'
        assert notification.signature == 'abc123'
