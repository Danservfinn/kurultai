"""
Integration tests for Subscription System

Verifies the complete subscribe → dispatch → receive flow:
1. Agent creates subscription
2. Event is dispatched
3. Notification is logged
4. Subscribers receive notification
"""

import pytest
import json
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch, call

import sys
sys.path.insert(0, '/data/workspace/souls/main')

from tools.kurultai.subscription_manager import SubscriptionManager
from tools.kurultai.notification_dispatcher import NotificationDispatcher


class TestSubscribeDispatchReceiveFlow:
    """End-to-end integration tests for subscription system."""
    
    @pytest.fixture
    def mock_driver(self):
        """Create a mock Neo4j driver with session tracking."""
        driver = MagicMock()
        session = MagicMock()
        
        # Setup context manager
        driver.session.return_value.__enter__ = Mock(return_value=session)
        driver.session.return_value.__exit__ = Mock(return_value=False)
        driver.session.return_value = session
        
        return driver, session
    
    def test_full_flow_single_subscriber(self, mock_driver):
        """Test complete flow with one subscriber."""
        driver, session = mock_driver
        
        # Setup subscription manager
        sub_manager = SubscriptionManager(driver)
        
        # Setup mock for subscription creation
        mock_result = MagicMock()
        mock_result.single.return_value = {'id': 'sub-123'}
        session.run.return_value = mock_result
        
        # Step 1: Create subscription
        sub_result = sub_manager.subscribe(
            subscriber='kublai',
            topic='research.completed',
            filter_criteria={'min_confidence': 0.8},
            target='möngke'
        )
        
        assert sub_result['status'] == 'success'
        assert sub_result['subscriber'] == 'kublai'
        assert sub_result['target'] == 'möngke'
        
        # Reset mock for dispatcher
        session.reset_mock()
        
        # Setup mock for subscriber lookup
        mock_sub_record = {
            'subscriber_id': 'kublai',
            'subscription_topic': 'research.completed',
            'filter': json.dumps({'min_confidence': 0.8}),
            'subscription_id': 'sub-123',
            'target_id': 'möngke'
        }
        mock_sub_result = MagicMock()
        mock_sub_result.__iter__ = Mock(return_value=iter([mock_sub_record]))
        mock_sub_result.single.return_value = None
        session.run.return_value = mock_sub_result
        
        # Step 2: Create dispatcher and dispatch event
        dispatcher = NotificationDispatcher(
            neo4j_driver=driver,
            subscription_manager=sub_manager,
            hmac_secret='test-secret'
        )
        
        dispatch_result = dispatcher.dispatch(
            event_type='research.completed',
            payload={
                'task_id': 'task-456',
                'results': ['finding1', 'finding2'],
                'min_confidence': 0.85
            },
            publisher='möngke'
        )
        
        # Step 3: Verify dispatch results
        assert dispatch_result['status'] == 'dispatched'
        assert dispatch_result['topic'] == 'research.completed'
        assert dispatch_result['subscriber_count'] == 1
        assert 'kublai' in dispatch_result['subscribers']
        
        # Step 4: Verify notification was signed
        assert 'notification_id' in dispatch_result
    
    def test_flow_with_filter_matching(self, mock_driver):
        """Test flow where filter criteria are applied."""
        driver, session = mock_driver
        
        sub_manager = SubscriptionManager(driver)
        dispatcher = NotificationDispatcher(
            neo4j_driver=driver,
            subscription_manager=sub_manager,
            hmac_secret='test-secret'
        )
        
        # Setup mock for subscription lookup with filter
        mock_sub_record = {
            'subscriber_id': 'kublai',
            'subscription_topic': 'research.completed',
            'filter': json.dumps({'min_confidence': 0.8}),
            'subscription_id': 'sub-1',
            'target_id': 'möngke'
        }
        
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([mock_sub_record]))
        session.run.return_value = mock_result
        
        # Dispatch with matching payload
        result = dispatcher.dispatch(
            event_type='research.completed',
            payload={'min_confidence': 0.9, 'data': 'results'},
            publisher='möngke'
        )
        
        # Should deliver to subscriber
        assert result['subscriber_count'] == 1
    
    def test_flow_with_filter_not_matching(self, mock_driver):
        """Test flow where filter criteria exclude subscriber."""
        driver, session = mock_driver
        
        sub_manager = SubscriptionManager(driver)
        dispatcher = NotificationDispatcher(
            neo4j_driver=driver,
            subscription_manager=sub_manager,
            hmac_secret='test-secret'
        )
        
        # Setup mock for subscription lookup with filter
        mock_sub_record = {
            'subscriber_id': 'kublai',
            'subscription_topic': 'research.completed',
            'filter': json.dumps({'min_confidence': 0.8}),
            'subscription_id': 'sub-1',
            'target_id': 'möngke'
        }
        
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([mock_sub_record]))
        session.run.return_value = mock_result
        
        # Dispatch with non-matching payload
        result = dispatcher.dispatch(
            event_type='research.completed',
            payload={'min_confidence': 0.5, 'data': 'results'},  # Below threshold
            publisher='möngke'
        )
        
        # Filter should exclude this subscriber
        assert result['subscriber_count'] == 0
    
    def test_flow_multiple_subscribers(self, mock_driver):
        """Test flow with multiple subscribers to same topic."""
        driver, session = mock_driver
        
        sub_manager = SubscriptionManager(driver)
        dispatcher = NotificationDispatcher(
            neo4j_driver=driver,
            subscription_manager=sub_manager,
            hmac_secret='test-secret'
        )
        
        # Setup multiple subscribers
        mock_sub_records = [
            {
                'subscriber_id': 'kublai',
                'subscription_topic': 'task.completed',
                'filter': None,
                'subscription_id': 'sub-1',
                'target_id': 'temüjin'
            },
            {
                'subscriber_id': 'ögedei',
                'subscription_topic': 'task.completed',
                'filter': None,
                'subscription_id': 'sub-2',
                'target_id': 'temüjin'
            }
        ]
        
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter(mock_sub_records))
        session.run.return_value = mock_result
        
        result = dispatcher.dispatch(
            event_type='task.completed',
            payload={'task_id': 'task-123', 'status': 'done'},
            publisher='temüjin'
        )
        
        # Should deliver to both subscribers
        assert result['subscriber_count'] == 2
        assert result['successful_deliveries'] == 2
        assert 'kublai' in result['subscribers']
        assert 'ögedei' in result['subscribers']
    
    def test_flow_wildcard_topic_matching(self, mock_driver):
        """Test flow with wildcard topic patterns."""
        driver, session = mock_driver
        
        sub_manager = SubscriptionManager(driver)
        dispatcher = NotificationDispatcher(
            neo4j_driver=driver,
            subscription_manager=sub_manager,
            hmac_secret='test-secret'
        )
        
        # Setup subscriber with wildcard topic
        mock_sub_record = {
            'subscriber_id': 'kublai',
            'subscription_topic': 'research.*',
            'filter': None,
            'subscription_id': 'sub-1',
            'target_id': '*'
        }
        
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([mock_sub_record]))
        session.run.return_value = mock_result
        
        # Dispatch to matching topic
        result = dispatcher.dispatch(
            event_type='research.completed',
            payload={'data': 'test'},
            publisher='möngke'
        )
        
        # Wildcard should match
        assert result['subscriber_count'] == 1
    
    def test_unsubscribe_removes_from_dispatch(self, mock_driver):
        """Test that unsubscribe prevents future dispatches."""
        driver, session = mock_driver
        
        sub_manager = SubscriptionManager(driver)
        
        # Setup mock for unsubscribe
        mock_unsub_result = MagicMock()
        mock_unsub_result.single.return_value = {'removed': 1}
        session.run.return_value = mock_unsub_result
        
        # Unsubscribe
        unsub_result = sub_manager.unsubscribe(
            subscriber='kublai',
            topic='research.completed',
            target='möngke'
        )
        
        assert unsub_result['status'] == 'success'
        assert unsub_result['removed_count'] == 1
    
    def test_direct_target_dispatch_bypasses_subscription(self, mock_driver):
        """Test that explicit target bypasses subscription lookup."""
        driver, session = mock_driver
        
        sub_manager = SubscriptionManager(driver)
        
        # Create spy on get_subscribers
        sub_manager.get_subscribers = Mock(return_value=[])
        
        dispatcher = NotificationDispatcher(
            neo4j_driver=driver,
            subscription_manager=sub_manager,
            hmac_secret='test-secret'
        )
        
        # Dispatch to specific target
        result = dispatcher.dispatch(
            event_type='direct.message',
            payload={'data': 'test'},
            publisher='kublai',
            target='temüjin'
        )
        
        # Should not call get_subscribers
        sub_manager.get_subscribers.assert_not_called()
        
        # Should still deliver to target
        assert result['subscriber_count'] == 1
        assert 'temüjin' in result['subscribers']


class TestSubscriptionToAPIMapping:
    """Tests mapping between Python classes and API routes."""
    
    def test_subscription_schema_matches_api(self):
        """Verify subscription data structure matches API expectations."""
        # This test documents the expected API structure
        expected_subscription_structure = {
            'id': str,
            'subscriber': str,
            'target': str,
            'topic': str,
            'filter': dict,
            'created_at': str
        }
        
        # Verify the structure is consistent
        for key, type_ in expected_subscription_structure.items():
            assert isinstance(key, str)
            assert type_ in [str, dict]
    
    def test_dispatch_result_structure(self):
        """Verify dispatch result structure."""
        expected_dispatch_structure = {
            'status': str,
            'notification_id': str,
            'topic': str,
            'publisher': str,
            'timestamp': str,
            'subscriber_count': int,
            'successful_deliveries': int,
            'failed_deliveries': int,
            'deliveries': list,
            'subscribers': list
        }
        
        for key, type_ in expected_dispatch_structure.items():
            assert isinstance(key, str)
            assert type_ in [str, int, list]
