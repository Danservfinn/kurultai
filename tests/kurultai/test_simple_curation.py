"""Tests for simplified memory curation."""

import pytest
from unittest.mock import Mock, MagicMock
import sys
import os

# Add tools/kurultai to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'tools', 'kurultai'))

from curation_simple import SimpleCuration


class TestSimpleCuration:
    """Test the SimpleCuration class."""

    @pytest.fixture
    def mock_driver(self):
        """Create a mock Neo4j driver with session support."""
        driver = Mock()

        # Create a mock session that supports context manager
        session = MagicMock()
        session.run = Mock()

        # Configure the context manager
        driver.session.return_value.__enter__ = Mock(return_value=session)
        driver.session.return_value.__exit__ = Mock(return_value=False)

        yield driver, session

        # Reset mock after each test
        session.reset_mock()
        driver.reset_mock()

    def test_curation_rapid_enforces_budget(self, mock_driver):
        """Test that curation_rapid enforces HOT token budget."""
        driver, session = mock_driver

        # Mock the query results - sequence of return values for each query
        session.run.return_value.single.side_effect = [
            {"c": 2000},  # hot_count query - over budget
            {"demoted": 5},  # demote query
            {"deleted": 10},  # notifications query
            {"deleted": 3},  # sessions query
        ]

        curation = SimpleCuration(driver)
        result = curation.curation_rapid()

        assert "hot_demoted" in result
        assert "notifications_deleted" in result
        assert "sessions_deleted" in result

        # Verify HOT budget enforcement query was called
        calls = session.run.call_args_list
        assert len(calls) >= 1

        # Check first call is for HOT budget enforcement
        first_call = calls[0]
        assert 'HOT' in str(first_call)
        assert 'count' in str(first_call)

    def test_curation_rapid_cleans_notifications(self, mock_driver):
        """Test that curation_rapid cleans old notifications."""
        driver, session = mock_driver

        # Mock the query results - sequence of return values for each query
        session.run.return_value.single.side_effect = [
            {"c": 1000},  # hot_count query - under budget, no demotion
            {"deleted": 10},  # notifications query
            {"deleted": 3},  # sessions query
        ]

        curation = SimpleCuration(driver)
        result = curation.curation_rapid()

        assert result["notifications_deleted"] == 10

        # Verify notification cleanup query
        calls = session.run.call_args_list
        notification_calls = [c for c in calls if 'Notification' in str(c)]
        assert len(notification_calls) >= 1

    def test_curation_rapid_cleans_sessions(self, mock_driver):
        """Test that curation_rapid cleans inactive sessions."""
        driver, session = mock_driver

        # Mock the query results - sequence of return values for each query
        session.run.return_value.single.side_effect = [
            {"c": 1000},  # hot_count query - under budget
            {"deleted": 10},  # notifications query
            {"deleted": 3},  # sessions query
        ]

        curation = SimpleCuration(driver)
        result = curation.curation_rapid()

        assert result["sessions_deleted"] == 3

        # Verify session cleanup query
        calls = session.run.call_args_list
        session_calls = [c for c in calls if 'SessionContext' in str(c)]
        assert len(session_calls) >= 1

    def test_curation_standard_archives_tasks(self, mock_driver):
        """Test that curation_standard archives completed tasks."""
        driver, session = mock_driver

        # Mock the query results - sequence for archive and demote queries
        session.run.return_value.single.side_effect = [
            {"archived": 15},  # archive query
            {"demoted": 8},    # demote query
        ]

        curation = SimpleCuration(driver)
        result = curation.curation_standard()

        assert result["archived"] == 15

        # Verify archive query
        calls = session.run.call_args_list
        archive_calls = [c for c in calls if 'completed' in str(c) and 'ARCHIVE' in str(c)]
        assert len(archive_calls) >= 1

    def test_curation_standard_demotes_stale_hot(self, mock_driver):
        """Test that curation_standard demotes stale HOT entries."""
        driver, session = mock_driver

        # Mock the query results - sequence for archive and demote queries
        session.run.return_value.single.side_effect = [
            {"archived": 15},  # archive query
            {"demoted": 8},    # demote query
        ]

        curation = SimpleCuration(driver)
        result = curation.curation_standard()

        assert result["demoted"] == 8

        # Verify demotion query
        calls = session.run.call_args_list
        demote_calls = [c for c in calls if 'demoted_stale' in str(c)]
        assert len(demote_calls) >= 1

    def test_curation_hourly_promotes_cold(self, mock_driver):
        """Test that curation_hourly promotes frequently accessed COLD entries."""
        driver, session = mock_driver

        # Mock the query results - sequence for queries in curation_hourly
        # Note: warm demote query only runs if over budget, so we provide extra values
        session.run.return_value.single.side_effect = [
            {"promoted": 3},   # promote query
            {"decayed": 12},   # decay query
            {"c": 500},        # warm count query - under budget
            {"demoted": 0},    # extra value in case needed
        ]

        curation = SimpleCuration(driver)
        result = curation.curation_hourly()

        assert result["promoted"] == 3

        # Verify promotion query
        calls = session.run.call_args_list
        promote_calls = [c for c in calls if 'promoted_access' in str(c)]
        assert len(promote_calls) >= 1

    def test_curation_hourly_decays_belief_confidence(self, mock_driver):
        """Test that curation_hourly decays belief confidence."""
        driver, session = mock_driver

        # Mock the query results - sequence for queries in curation_hourly
        # Note: warm demote query only runs if over budget, so we provide extra values
        session.run.return_value.single.side_effect = [
            {"promoted": 3},   # promote query
            {"decayed": 12},   # decay query
            {"c": 500},        # warm count query - under budget
            {"demoted": 0},    # extra value in case needed
        ]

        curation = SimpleCuration(driver)
        result = curation.curation_hourly()

        assert result["confidence_decayed"] == 12

        # Verify decay query
        calls = session.run.call_args_list
        decay_calls = [c for c in calls if 'Belief' in str(c) and 'confidence' in str(c)]
        assert len(decay_calls) >= 1

    def test_curation_deep_removes_orphans(self, mock_driver):
        """Test that curation_deep removes orphaned nodes."""
        driver, session = mock_driver

        # Mock the query results - sequence for 4 queries in curation_deep
        session.run.return_value.single.side_effect = [
            {"deleted": 7},    # orphans query
            {"deleted": 5},    # tombstones query
            {"c": 150},        # cold count query - under budget
        ]

        curation = SimpleCuration(driver)
        result = curation.curation_deep()

        assert result["orphans_deleted"] == 7

        # Verify orphan deletion query
        calls = session.run.call_args_list
        orphan_calls = [c for c in calls if 'orphan' in str(c).lower() or 'NOT (n)--()' in str(c)]
        assert len(orphan_calls) >= 1

    def test_curation_deep_purges_tombstones(self, mock_driver):
        """Test that curation_deep purges old tombstoned entries."""
        driver, session = mock_driver

        # Mock the query results - sequence for 4 queries in curation_deep
        session.run.return_value.single.side_effect = [
            {"deleted": 7},    # orphans query
            {"deleted": 5},    # tombstones query
            {"c": 150},        # cold count query - under budget
        ]

        curation = SimpleCuration(driver)
        result = curation.curation_deep()

        assert result["tombstones_purged"] == 5

        # Verify tombstone purge query
        calls = session.run.call_args_list
        tombstone_calls = [c for c in calls if 'tombstone' in str(c)]
        assert len(tombstone_calls) >= 1

    def test_token_budgets(self, mock_driver):
        """Test that token budgets are set correctly."""
        driver, _ = mock_driver

        curation = SimpleCuration(driver)

        assert curation.HOT_TOKENS == 1600
        assert curation.WARM_TOKENS == 400
        assert curation.COLD_TOKENS == 200

    def test_safety_rules_in_queries(self, mock_driver):
        """Test that safety rules are present in curation queries."""
        driver, session = mock_driver

        # Mock to return appropriate values based on query content
        def side_effect(*args, **kwargs):
            query = args[0] if args else ""
            if "count(m) AS c" in query:
                return {"c": 1000}
            elif "RETURN count(m) AS demoted" in query:
                return {"demoted": 0}
            elif "RETURN count(n) AS deleted" in query:
                return {"deleted": 0}
            elif "RETURN count(s) AS deleted" in query:
                return {"deleted": 0}
            elif "RETURN count(t) AS archived" in query:
                return {"archived": 0}
            elif "RETURN count(b) AS decayed" in query:
                return {"decayed": 0}
            elif "RETURN count(o) AS deleted" in query:
                return {"deleted": 0}
            elif "RETURN count(m) AS deleted" in query:
                return {"deleted": 0}
            return {"c": 0}

        session.run.return_value.single.side_effect = side_effect

        curation = SimpleCuration(driver)

        # Run all curation methods
        curation.curation_rapid()
        curation.curation_standard()
        curation.curation_hourly()
        curation.curation_deep()

        # Get all queries executed
        calls = session.run.call_args_list
        all_queries = ' '.join([str(c) for c in calls])

        # Verify safety patterns are present
        # Should NOT delete Agent nodes without protection
        assert 'NOT n:Agent' in all_queries or 'NOT n:AgentKey' in all_queries

        # Should have safety checks for age
        assert 'created_at' in all_queries


class TestCurationIntegration:
    """Integration tests for the curation system."""

    @pytest.fixture
    def mock_driver(self):
        """Create a mock Neo4j driver with realistic responses."""
        driver = Mock()
        session = MagicMock()

        # Mock to return appropriate values based on query content
        def side_effect(*args, **kwargs):
            query = args[0] if args else ""
            if "count(m) AS c" in query:
                return {"c": 1000}
            elif "RETURN count(m) AS demoted" in query:
                return {"demoted": 2}
            elif "RETURN count(n) AS deleted" in query:
                return {"deleted": 5}
            elif "RETURN count(s) AS deleted" in query:
                return {"deleted": 3}
            elif "RETURN count(t) AS archived" in query:
                return {"archived": 10}
            elif "RETURN count(m) AS promoted" in query:
                return {"promoted": 3}
            elif "RETURN count(b) AS decayed" in query:
                return {"decayed": 8}
            elif "RETURN count(o) AS deleted" in query:
                return {"deleted": 7}
            elif "RETURN count(m) AS deleted" in query:
                return {"deleted": 5}
            return {"c": 0}

        session.run.return_value.single.side_effect = side_effect
        driver.session.return_value.__enter__ = Mock(return_value=session)
        driver.session.return_value.__exit__ = Mock(return_value=False)

        yield driver, session

        session.reset_mock()
        driver.reset_mock()

    def test_full_curation_cycle(self, mock_driver):
        """Test running all curation operations in sequence."""
        driver, session = mock_driver
        curation = SimpleCuration(driver)

        # Run all curation operations
        rapid_result = curation.curation_rapid()
        standard_result = curation.curation_standard()
        hourly_result = curation.curation_hourly()
        deep_result = curation.curation_deep()

        # Verify all operations completed
        assert rapid_result is not None
        assert standard_result is not None
        assert hourly_result is not None
        assert deep_result is not None

        # Verify expected keys in each result
        assert "hot_demoted" in rapid_result
        assert "archived" in standard_result
        assert "promoted" in hourly_result
        assert "orphans_deleted" in deep_result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
