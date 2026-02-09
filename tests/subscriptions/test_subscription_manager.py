"""
Tests for Subscription Manager

Verifies:
- subscribe() creates subscriptions correctly
- unsubscribe() removes subscriptions
- get_subscribers() filters by topic and criteria
- list_subscriptions() returns agent's subscriptions
- Filter matching works with various operators
"""

import pytest
import json
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

# Import the module under test
import sys
sys.path.insert(0, '/data/workspace/souls/main')

from tools.kurultai.subscription_manager import SubscriptionManager, Subscription


class TestSubscriptionManager:
    """Test suite for SubscriptionManager."""
    
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
    def subscription_manager(self, mock_driver):
        """Create a SubscriptionManager with mock driver."""
        driver, _ = mock_driver
        return SubscriptionManager(driver)
    
    def test_subscribe_with_target(self, subscription_manager, mock_driver):
        """Test subscribing to a specific target agent."""
        driver, session = mock_driver
        
        # Setup mock result
        mock_result = MagicMock()
        mock_result.single.return_value = {'id': 'test-sub-id'}
        session.run.return_value = mock_result
        
        # Call subscribe
        result = subscription_manager.subscribe(
            subscriber='kublai',
            topic='research.completed',
            target='möngke'
        )
        
        # Verify result structure
        assert result['status'] == 'success'
        assert result['subscriber'] == 'kublai'
        assert result['target'] == 'möngke'
        assert result['topic'] == 'research.completed'
        assert 'subscription_id' in result
        
        # Verify Neo4j calls
        assert session.run.call_count == 2  # MERGE agent + CREATE subscription
    
    def test_subscribe_with_filter(self, subscription_manager, mock_driver):
        """Test subscribing with filter criteria."""
        driver, session = mock_driver
        
        mock_result = MagicMock()
        mock_result.single.return_value = {'id': 'test-sub-id'}
        session.run.return_value = mock_result
        
        filter_criteria = {'min_confidence': 0.8, 'status': 'validated'}
        
        result = subscription_manager.subscribe(
            subscriber='kublai',
            topic='analysis.completed',
            filter_criteria=filter_criteria,
            target='jochi'
        )
        
        assert result['status'] == 'success'
        assert result['filter'] == filter_criteria
    
    def test_subscribe_wildcard_target(self, subscription_manager, mock_driver):
        """Test subscribing to all agents (no specific target)."""
        driver, session = mock_driver
        
        mock_result = MagicMock()
        mock_result.single.return_value = {'id': 'test-sub-id'}
        session.run.return_value = mock_result
        
        result = subscription_manager.subscribe(
            subscriber='ögedei',
            topic='task.*'
        )
        
        assert result['status'] == 'success'
        assert result['target'] == '*'
    
    def test_unsubscribe_specific_target(self, subscription_manager, mock_driver):
        """Test unsubscribing from a specific target."""
        driver, session = mock_driver
        
        mock_result = MagicMock()
        mock_result.single.return_value = {'removed': 1}
        session.run.return_value = mock_result
        
        result = subscription_manager.unsubscribe(
            subscriber='kublai',
            topic='research.completed',
            target='möngke'
        )
        
        assert result['status'] == 'success'
        assert result['removed_count'] == 1
        assert result['subscriber'] == 'kublai'
    
    def test_unsubscribe_all_targets(self, subscription_manager, mock_driver):
        """Test unsubscribing from all targets for a topic."""
        driver, session = mock_driver
        
        mock_result = MagicMock()
        mock_result.single.return_value = {'removed': 3}
        session.run.return_value = mock_result
        
        result = subscription_manager.unsubscribe(
            subscriber='kublai',
            topic='task.*'
        )
        
        assert result['status'] == 'success'
        assert result['removed_count'] == 3
    
    def test_get_subscribers_basic(self, subscription_manager, mock_driver):
        """Test getting subscribers for a topic."""
        driver, session = mock_driver
        
        # Setup mock records
        mock_record1 = {
            'subscriber_id': 'kublai',
            'subscription_topic': 'research.completed',
            'filter': None,
            'subscription_id': 'sub-1',
            'target_id': 'möngke'
        }
        mock_record2 = {
            'subscriber_id': 'ögedei',
            'subscription_topic': 'research.*',
            'filter': None,
            'subscription_id': 'sub-2',
            'target_id': '*'
        }
        
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([mock_record1, mock_record2]))
        session.run.return_value = mock_result
        
        subscribers = subscription_manager.get_subscribers('research.completed')
        
        assert len(subscribers) == 2
        assert subscribers[0]['agent_id'] == 'kublai'
        assert subscribers[1]['agent_id'] == 'ögedei'
    
    def test_get_subscribers_with_filter_matching(self, subscription_manager, mock_driver):
        """Test getting subscribers with payload filtering - matching."""
        driver, session = mock_driver
        
        filter_criteria = {'min_confidence': 0.8}
        mock_record = {
            'subscriber_id': 'kublai',
            'subscription_topic': 'research.completed',
            'filter': json.dumps(filter_criteria),
            'subscription_id': 'sub-1',
            'target_id': 'möngke'
        }
        
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([mock_record]))
        session.run.return_value = mock_result
        
        payload = {'min_confidence': 0.9, 'results': ['item1']}
        subscribers = subscription_manager.get_subscribers('research.completed', payload)
        
        assert len(subscribers) == 1
        assert subscribers[0]['agent_id'] == 'kublai'
    
    def test_get_subscribers_with_filter_not_matching(self, subscription_manager, mock_driver):
        """Test getting subscribers with payload filtering - not matching."""
        driver, session = mock_driver
        
        filter_criteria = {'min_confidence': 0.8}
        mock_record = {
            'subscriber_id': 'kublai',
            'subscription_topic': 'research.completed',
            'filter': json.dumps(filter_criteria),
            'subscription_id': 'sub-1',
            'target_id': 'möngke'
        }
        
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([mock_record]))
        session.run.return_value = mock_result
        
        payload = {'min_confidence': 0.5}  # Below threshold
        subscribers = subscription_manager.get_subscribers('research.completed', payload)
        
        assert len(subscribers) == 0  # Filtered out
    
    def test_list_subscriptions(self, subscription_manager, mock_driver):
        """Test listing all subscriptions for an agent."""
        driver, session = mock_driver
        
        mock_record1 = {
            'id': 'sub-1',
            'topic': 'research.completed',
            'filter': json.dumps({'status': 'validated'}),
            'created_at': datetime.now(),
            'target_id': None,
            'target_agent_id': 'möngke'
        }
        mock_record2 = {
            'id': 'sub-2',
            'topic': 'task.*',
            'filter': None,
            'created_at': datetime.now(),
            'target_id': '*',
            'target_agent_id': None
        }
        
        mock_result = MagicMock()
        mock_result.__iter__ = Mock(return_value=iter([mock_record1, mock_record2]))
        session.run.return_value = mock_result
        
        subscriptions = subscription_manager.list_subscriptions('kublai')
        
        assert len(subscriptions) == 2
        assert subscriptions[0]['topic'] == 'research.completed'
        assert subscriptions[0]['filter'] == {'status': 'validated'}
        assert subscriptions[1]['topic'] == 'task.*'
    
    def test_get_subscription_by_id(self, subscription_manager, mock_driver):
        """Test getting a specific subscription by ID."""
        driver, session = mock_driver
        
        mock_record = {
            'id': 'sub-123',
            'subscriber_id': 'kublai',
            'topic': 'research.completed',
            'filter': json.dumps({'min_confidence': 0.8}),
            'created_at': datetime.now(),
            'target_id': None,
            'target_agent_id': 'möngke'
        }
        
        mock_result = MagicMock()
        mock_result.single.return_value = mock_record
        session.run.return_value = mock_result
        
        subscription = subscription_manager.get_subscription('sub-123')
        
        assert subscription is not None
        assert subscription['id'] == 'sub-123'
        assert subscription['subscriber_id'] == 'kublai'
        assert subscription['filter'] == {'min_confidence': 0.8}
    
    def test_get_subscription_not_found(self, subscription_manager, mock_driver):
        """Test getting a non-existent subscription."""
        driver, session = mock_driver
        
        mock_result = MagicMock()
        mock_result.single.return_value = None
        session.run.return_value = mock_result
        
        subscription = subscription_manager.get_subscription('non-existent')
        
        assert subscription is None


class TestFilterMatching:
    """Test suite for filter matching logic."""
    
    @pytest.fixture
    def manager(self):
        """Create a SubscriptionManager for testing filters."""
        mock_driver = MagicMock()
        return SubscriptionManager(mock_driver)
    
    def test_exact_match(self, manager):
        """Test exact value matching."""
        payload = {'status': 'completed', 'type': 'research'}
        criteria = {'status': 'completed'}
        
        assert manager._matches_filter(payload, criteria) is True
    
    def test_exact_match_failure(self, manager):
        """Test exact value not matching."""
        payload = {'status': 'pending'}
        criteria = {'status': 'completed'}
        
        assert manager._matches_filter(payload, criteria) is False
    
    def test_gte_operator(self, manager):
        """Test greater-than-or-equal operator."""
        payload = {'confidence': 0.8}
        criteria = {'confidence': {'$gte': 0.7}}
        
        assert manager._matches_filter(payload, criteria) is True
    
    def test_gte_operator_failure(self, manager):
        """Test GTE operator with lower value."""
        payload = {'confidence': 0.6}
        criteria = {'confidence': {'$gte': 0.7}}
        
        assert manager._matches_filter(payload, criteria) is False
    
    def test_gt_operator(self, manager):
        """Test greater-than operator."""
        payload = {'score': 95}
        criteria = {'score': {'$gt': 90}}
        
        assert manager._matches_filter(payload, criteria) is True
    
    def test_lte_operator(self, manager):
        """Test less-than-or-equal operator."""
        payload = {'errors': 3}
        criteria = {'errors': {'$lte': 5}}
        
        assert manager._matches_filter(payload, criteria) is True
    
    def test_lt_operator(self, manager):
        """Test less-than operator."""
        payload = {'latency': 100}
        criteria = {'latency': {'$lt': 200}}
        
        assert manager._matches_filter(payload, criteria) is True
    
    def test_eq_operator(self, manager):
        """Test equality operator."""
        payload = {'type': 'analysis'}
        criteria = {'type': {'$eq': 'analysis'}}
        
        assert manager._matches_filter(payload, criteria) is True
    
    def test_ne_operator(self, manager):
        """Test not-equal operator."""
        payload = {'status': 'active'}
        criteria = {'status': {'$ne': 'deleted'}}
        
        assert manager._matches_filter(payload, criteria) is True
    
    def test_in_operator(self, manager):
        """Test in-list operator."""
        payload = {'type': 'research'}
        criteria = {'type': {'$in': ['research', 'analysis', 'summary']}}
        
        assert manager._matches_filter(payload, criteria) is True
    
    def test_nin_operator(self, manager):
        """Test not-in-list operator."""
        payload = {'type': 'other'}
        criteria = {'type': {'$nin': ['research', 'analysis']}}
        
        assert manager._matches_filter(payload, criteria) is True
    
    def test_exists_operator_true(self, manager):
        """Test exists operator with existing field."""
        payload = {'result': 'data'}
        criteria = {'result': {'$exists': True}}
        
        assert manager._matches_filter(payload, criteria) is True
    
    def test_exists_operator_false(self, manager):
        """Test exists operator with missing field."""
        payload = {'other': 'data'}
        criteria = {'result': {'$exists': False}}
        
        assert manager._matches_filter(payload, criteria) is True
    
    def test_multiple_criteria(self, manager):
        """Test multiple criteria - all must match."""
        payload = {
            'status': 'completed',
            'confidence': 0.85,
            'type': 'research'
        }
        criteria = {
            'status': 'completed',
            'confidence': {'$gte': 0.8},
            'type': {'$in': ['research', 'analysis']}
        }
        
        assert manager._matches_filter(payload, criteria) is True
    
    def test_multiple_criteria_partial_failure(self, manager):
        """Test multiple criteria where one fails."""
        payload = {
            'status': 'completed',
            'confidence': 0.7  # Below threshold
        }
        criteria = {
            'status': 'completed',
            'confidence': {'$gte': 0.8}
        }
        
        assert manager._matches_filter(payload, criteria) is False
