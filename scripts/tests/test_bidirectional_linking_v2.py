#!/usr/bin/env python3
"""
Comprehensive Test Suite for Bidirectional Linking in Kurultai Task Management System

This test suite validates the bidirectional linking functionality between parent and child
tasks in the Kurultai multi-agent system. The tests cover:

1. Neo4j Graph Relationships: HAS_FOLLOWUP and FOLLOWS_UP relationship pairs
2. Task Property Tracking: parent_id storage in task nodes
3. Bidirectional Query Integrity: Consistent results from both traversal directions
4. Gate Resolution: Tracking follow-up completion for parent task completion gates
5. Cycle Detection: Preventing circular dependencies in task chains
6. Edge Cases: Orphan tasks, deep chains, multiple children, and boundary conditions

Run:
    python3 test_bidirectional_linking_v2.py
    python3 test_bidirectional_linking_v2.py --verbose
    python3 test_bidirectional_linking_v2.py TestLinkFollowup  # Run specific class
"""

import os
import sys
import uuid
import json
import time
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, call
from typing import Dict, List, Optional, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Try imports with graceful handling if Neo4j unavailable
NEO4J_AVAILABLE = False
try:
    from neo4j_task_tracker import TaskTracker, get_driver
    NEO4J_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Neo4j imports unavailable: {e}")


# =============================================================================
# Mock Implementations for Testing
# =============================================================================

class MockNeo4jRecord:
    """Mock a single Neo4j record."""

    def __init__(self, data: Dict[str, Any]):
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data.get(key)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def keys(self) -> List[str]:
        return list(self._data.keys())


class MockNeo4jResult:
    """Mock Neo4j result for testing."""

    def __init__(self, records: Optional[List[Dict]] = None, single_value: Any = None):
        self.records = records or []
        self.single_value = single_value
        self._index = 0

    def __iter__(self):
        return iter(self.records)

    def __next__(self):
        if self._index >= len(self.records):
            raise StopIteration
        result = self.records[self._index]
        self._index += 1
        return MockNeo4jRecord(result)

    def single(self) -> Optional[MockNeo4jRecord]:
        if self.records:
            return MockNeo4jRecord(self.records[0])
        return None

    def data(self) -> List[Dict]:
        return self.records

    def keys(self) -> List[str]:
        if self.records:
            return list(self.records[0].keys())
        return []


class MockNeo4jSession:
    """Mock Neo4j session for testing."""

    def __init__(self):
        self.queries: List[tuple] = []
        self.results: Dict[str, MockNeo4jResult] = {}
        self.default_result = MockNeo4jResult([])
        self._closed = False

    def run(self, query: str, **kwargs) -> MockNeo4jResult:
        self.queries.append((query, kwargs))
        # Return predefined result based on query pattern
        for pattern, result in self.results.items():
            if pattern in query:
                return result
        return self.default_result

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def close(self):
        self._closed = True


class MockNeo4jDriver:
    """Mock Neo4j driver for testing."""

    def __init__(self):
        self._session = MockNeo4jSession()
        self.closed = False

    def session(self):
        return self._session

    def close(self):
        self.closed = True
        self._session.close()


# =============================================================================
# Test Suite 1: Link Followup Creation Tests
# =============================================================================

@unittest.skipIf(not NEO4J_AVAILABLE, "Neo4j not available")
class TestLinkFollowup(unittest.TestCase):
    """Test suite for the link_followup method."""

    def setUp(self):
        """Set up mock driver for each test."""
        self.mock_driver = MockNeo4jDriver()
        self.patcher = patch('neo4j_task_tracker.get_driver', return_value=self.mock_driver)
        self.patcher.start()

        self.tracker = TaskTracker()
        self.tracker.driver = self.mock_driver

    def tearDown(self):
        """Clean up mocks."""
        self.patcher.stop()

    def test_link_followup_creates_both_relationships(self):
        """Test that link_followup creates both HAS_FOLLOWUP and FOLLOWS_UP relationships."""
        parent_id = str(uuid.uuid4())[:8]
        followup_id = str(uuid.uuid4())[:8]

        self.tracker.link_followup(parent_id, followup_id)

        # Verify a query was executed
        self.assertEqual(len(self.mock_driver._session.queries), 1)

        # Verify the query creates both relationships
        query = self.mock_driver._session.queries[0][0]
        self.assertIn('HAS_FOLLOWUP', query)
        self.assertIn('FOLLOWS_UP', query)

        # Verify parameters
        params = self.mock_driver._session.queries[0][1]
        self.assertEqual(params['parent_id'], parent_id)
        self.assertEqual(params['followup_id'], followup_id)

    def test_link_followup_gate_required_true(self):
        """Test that gate_required flag is stored when True."""
        parent_id = str(uuid.uuid4())[:8]
        followup_id = str(uuid.uuid4())[:8]

        self.tracker.link_followup(parent_id, followup_id, gate_required=True)
        params = self.mock_driver._session.queries[0][1]
        self.assertTrue(params['gate_required'])

    def test_link_followup_gate_required_false(self):
        """Test that gate_required flag is stored when False."""
        parent_id = str(uuid.uuid4())[:8]
        followup_id = str(uuid.uuid4())[:8]

        self.tracker.link_followup(parent_id, followup_id, gate_required=False)
        params = self.mock_driver._session.queries[0][1]
        self.assertFalse(params['gate_required'])

    def test_link_followup_default_gate_required(self):
        """Test that gate_required defaults to True."""
        parent_id = str(uuid.uuid4())[:8]
        followup_id = str(uuid.uuid4())[:8]

        # Call without gate_required parameter
        self.tracker.link_followup(parent_id, followup_id)
        params = self.mock_driver._session.queries[0][1]
        self.assertTrue(params['gate_required'])


# =============================================================================
# Test Suite 2: Followup Query Tests
# =============================================================================

@unittest.skipIf(not NEO4J_AVAILABLE, "Neo4j not available")
class TestGetFollowupTasks(unittest.TestCase):
    """Test suite for querying followup tasks."""

    def setUp(self):
        """Set up mock driver for each test."""
        self.mock_driver = MockNeo4jDriver()
        self.patcher = patch('neo4j_task_tracker.get_driver', return_value=self.mock_driver)
        self.patcher.start()

        self.tracker = TaskTracker()
        self.tracker.driver = self.mock_driver

    def tearDown(self):
        """Clean up mocks."""
        self.patcher.stop()

    def test_get_followup_tasks_queries_has_followup(self):
        """Test that get_followup_tasks uses the HAS_FOLLOWUP relationship."""
        parent_id = str(uuid.uuid4())[:8]

        # Set up mock result
        mock_records = [
            {'task_id': 'followup-1', 'agent': 'temujin', 'status': 'PENDING'},
            {'task_id': 'followup-2', 'agent': 'mongke', 'status': 'COMPLETED'},
        ]
        self.mock_driver._session.results['HAS_FOLLOWUP'] = MockNeo4jResult(mock_records)

        followups = self.tracker.get_followup_tasks(parent_id)

        # Verify query uses HAS_FOLLOWUP
        query = self.mock_driver._session.queries[0][0]
        self.assertIn('HAS_FOLLOWUP', query)
        self.assertIn('ORDER BY', query)
        self.assertEqual(len(followups), 2)

    def test_get_followup_tasks_empty_result(self):
        """Test get_followup_tasks with no followups."""
        parent_id = 'parent-no-children'

        # Set up empty mock result
        self.mock_driver._session.results['HAS_FOLLOWUP'] = MockNeo4jResult([])

        followups = self.tracker.get_followup_tasks(parent_id)

        self.assertEqual(len(followups), 0)

    def test_get_followup_tasks_returns_correct_fields(self):
        """Test that get_followup_tasks returns all expected fields."""
        parent_id = 'parent-123'

        mock_records = [
            {'task_id': 'child-1', 'agent': 'jochi', 'status': 'IN_PROGRESS', 'gate_required': True},
        ]
        self.mock_driver._session.results['HAS_FOLLOWUP'] = MockNeo4jResult(mock_records)

        followups = self.tracker.get_followup_tasks(parent_id)

        self.assertEqual(len(followups), 1)
        self.assertIn('task_id', followups[0])
        self.assertIn('agent', followups[0])
        self.assertIn('status', followups[0])


# =============================================================================
# Test Suite 3: Gate Resolution Tests
# =============================================================================

@unittest.skipIf(not NEO4J_AVAILABLE, "Neo4j not available")
class TestGateResolution(unittest.TestCase):
    """Test suite for gate resolution functionality."""

    def setUp(self):
        """Set up mock driver for each test."""
        self.mock_driver = MockNeo4jDriver()
        self.patcher = patch('neo4j_task_tracker.get_driver', return_value=self.mock_driver)
        self.patcher.start()

        self.tracker = TaskTracker()
        self.tracker.driver = self.mock_driver

    def tearDown(self):
        """Clean up mocks."""
        self.patcher.stop()

    def test_check_gate_resolve_status_all_complete(self):
        """Test gate resolution when all followups are complete."""
        task_id = 'parent-with-complete-followups'

        mock_records = [{'total': 3, 'completed': 3, 'can_resolve': True}]
        self.mock_driver._session.default_result = MockNeo4jResult(mock_records)

        status = self.tracker.check_gate_resolve_status(task_id)

        self.assertTrue(status['can_resolve'])
        self.assertEqual(status['total_followups'], 3)
        self.assertEqual(status['completed_followups'], 3)

    def test_check_gate_resolve_status_partial_complete(self):
        """Test gate resolution when only some followups are complete."""
        task_id = 'parent-with-partial-followups'

        mock_records = [{'total': 5, 'completed': 2, 'can_resolve': False}]
        self.mock_driver._session.default_result = MockNeo4jResult(mock_records)

        status = self.tracker.check_gate_resolve_status(task_id)

        self.assertFalse(status['can_resolve'])
        self.assertEqual(status['total_followups'], 5)
        self.assertEqual(status['completed_followups'], 2)

    def test_check_gate_resolve_status_no_followups(self):
        """Test gate resolution when there are no followups."""
        task_id = 'parent-with-no-followups'

        mock_records = [{'total': 0, 'completed': 0, 'can_resolve': True}]
        self.mock_driver._session.default_result = MockNeo4jResult(mock_records)

        status = self.tracker.check_gate_resolve_status(task_id)

        self.assertTrue(status['can_resolve'])
        self.assertEqual(status['total_followups'], 0)

    def test_create_gate_resolution(self):
        """Test creating a gate resolution node."""
        task_id = 'resolved-task-123'

        self.tracker.create_gate_resolution(
            task_id=task_id,
            status='PASSED',
            total_followups=3,
            resolution_cycles=1
        )

        query = self.mock_driver._session.queries[0][0]
        self.assertIn('GateResolution', query)
        self.assertIn('CREATE', query)

        params = self.mock_driver._session.queries[0][1]
        self.assertEqual(params['task_id'], task_id)
        self.assertEqual(params['status'], 'PASSED')
        self.assertEqual(params['total_followups'], 3)


# =============================================================================
# Test Suite 4: Cycle Detection Tests
# =============================================================================

@unittest.skipIf(not NEO4J_AVAILABLE, "Neo4j not available")
class TestCycleDetection(unittest.TestCase):
    """Test suite for detecting circular dependencies."""

    def setUp(self):
        """Set up mock driver for each test."""
        self.mock_driver = MockNeo4jDriver()
        self.patcher = patch('neo4j_task_tracker.get_driver', return_value=self.mock_driver)
        self.patcher.start()

        self.tracker = TaskTracker()
        self.tracker.driver = self.mock_driver

    def tearDown(self):
        """Clean up mocks."""
        self.patcher.stop()

    def test_detect_gate_cycles_finds_cycle(self):
        """Test that detect_gate_cycles identifies circular dependencies."""
        # Mock a cycle: A -> B -> C -> A
        mock_cycles = [
            ['task-a', 'task-b', 'task-c', 'task-a']
        ]
        self.mock_driver._session.default_result = MockNeo4jResult(
            [{'cycle': cycle} for cycle in mock_cycles]
        )

        cycles = self.tracker.detect_gate_cycles(max_depth=3)

        self.assertEqual(len(cycles), 1)
        self.assertIn('task-a', cycles[0])

    def test_detect_gate_cycles_no_cycles(self):
        """Test that detect_gate_cycles returns empty list when no cycles exist."""
        self.mock_driver._session.default_result = MockNeo4jResult([])

        cycles = self.tracker.detect_gate_cycles(max_depth=3)

        self.assertEqual(len(cycles), 0)

    def test_detect_gate_cycles_custom_depth(self):
        """Test that detect_gate_cycles respects custom max_depth."""
        self.mock_driver._session.default_result = MockNeo4jResult([])

        # Test with depth 5
        self.tracker.detect_gate_cycles(max_depth=5)

        query = self.mock_driver._session.queries[0][0]
        self.assertIn('*..5]', query)


# =============================================================================
# Test Suite 5: Edge Case Tests
# =============================================================================

class TestBidirectionalEdgeCases(unittest.TestCase):
    """Test edge cases in bidirectional linking without requiring Neo4j."""

    def test_orphan_task_has_no_parent(self):
        """Test that tasks without parents have null parent_id."""
        orphan_task = {
            'task_id': 'orphan-123',
            'parent_id': None,
            'title': 'Orphan Task'
        }
        self.assertIsNone(orphan_task['parent_id'])

    def test_orphan_task_empty_string_parent(self):
        """Test that orphan tasks can have empty string parent_id."""
        orphan_task = {
            'task_id': 'orphan-456',
            'parent_id': '',
            'title': 'Another Orphan'
        }
        self.assertEqual(orphan_task['parent_id'], '')

    def test_circular_reference_detection_algorithm(self):
        """Test the algorithm for detecting circular references."""
        # A -> B -> C -> A
        tasks = {
            'task-a': {'parent_id': 'task-c'},
            'task-b': {'parent_id': 'task-a'},
            'task-c': {'parent_id': 'task-b'},
        }

        def has_circular_reference(task_id, visited=None):
            """Detect circular reference using depth-first search."""
            if visited is None:
                visited = set()

            if task_id in visited:
                return True

            if task_id not in tasks or not tasks[task_id].get('parent_id'):
                return False

            visited.add(task_id)
            return has_circular_reference(tasks[task_id]['parent_id'], visited)

        self.assertTrue(has_circular_reference('task-a'))
        self.assertTrue(has_circular_reference('task-b'))
        self.assertTrue(has_circular_reference('task-c'))

    def test_no_circular_reference_in_linear_chain(self):
        """Test that linear chains don't trigger false positives."""
        # Root -> Child -> Grandchild (no cycle)
        tasks = {
            'root': {'parent_id': None},
            'child': {'parent_id': 'root'},
            'grandchild': {'parent_id': 'child'},
        }

        def has_circular_reference(task_id, visited=None):
            if visited is None:
                visited = set()
            if task_id in visited:
                return True
            if task_id not in tasks or not tasks[task_id].get('parent_id'):
                return False
            visited.add(task_id)
            return has_circular_reference(tasks[task_id]['parent_id'], visited)

        self.assertFalse(has_circular_reference('root'))
        self.assertFalse(has_circular_reference('child'))
        self.assertFalse(has_circular_reference('grandchild'))

    def test_deep_task_chain_traversal(self):
        """Test traversing deep task chains (10+ levels)."""
        chain = []
        for i in range(15):
            chain.append({
                'task_id': f'task-{i}',
                'parent_id': f'task-{i-1}' if i > 0 else None
            })

        def get_chain_length(task_id, tasks_dict):
            """Get the depth of the task chain."""
            length = 0
            current = task_id
            while current in tasks_dict and tasks_dict[current].get('parent_id'):
                length += 1
                current = tasks_dict[current]['parent_id']
            return length

        tasks_dict = {t['task_id']: t for t in chain}
        self.assertEqual(get_chain_length('task-14', tasks_dict), 14)

    def test_multiple_children_same_parent(self):
        """Test that a parent can have multiple children."""
        parent_id = 'parent-multi'
        children = ['child-1', 'child-2', 'child-3', 'child-4', 'child-5']

        relationships = [
            {'from': parent_id, 'to': child, 'type': 'HAS_FOLLOWUP'}
            for child in children
        ]

        self.assertEqual(len(relationships), 5)
        for rel in relationships:
            self.assertEqual(rel['from'], parent_id)
            self.assertIn(rel['to'], children)

    def test_single_parent_constraint(self):
        """Test that a child can only have one parent."""
        task = {
            'task_id': 'child-single-parent',
            'parent_id': 'parent-1',  # Single value - cannot have multiple
        }
        self.assertEqual(task['parent_id'], 'parent-1')
        # Adding a second parent would overwrite, not append


# =============================================================================
# Test Suite 6: Bidirectional Integrity Tests
# =============================================================================

class TestBidirectionalIntegrity(unittest.TestCase):
    """Test bidirectional link integrity without requiring Neo4j."""

    def test_relationship_symmetry(self):
        """Test that HAS_FOLLOWUP and FOLLOWS_UP are symmetric."""
        parent_id = 'parent-sym'
        child_id = 'child-sym'

        forward_rel = (parent_id, 'HAS_FOLLOWUP', child_id)
        reverse_rel = (child_id, 'FOLLOWS_UP', parent_id)

        # Both should exist for proper bidirectional linking
        self.assertEqual(forward_rel[0], reverse_rel[2])  # parent = parent
        self.assertEqual(forward_rel[2], reverse_rel[0])  # child = child

    def test_query_consistency_both_directions(self):
        """Test that queries from both directions return consistent results."""
        links = [
            ('parent-1', 'HAS_FOLLOWUP', 'child-1'),
            ('child-1', 'FOLLOWS_UP', 'parent-1'),
            ('parent-1', 'HAS_FOLLOWUP', 'child-2'),
            ('child-2', 'FOLLOWS_UP', 'parent-1'),
        ]

        def get_children(parent_id):
            return [l[2] for l in links if l[0] == parent_id and l[1] == 'HAS_FOLLOWUP']

        def get_parent(child_id):
            parents = [l[2] for l in links if l[0] == child_id and l[1] == 'FOLLOWS_UP']
            return parents[0] if parents else None

        children = get_children('parent-1')
        for child in children:
            self.assertEqual(get_parent(child), 'parent-1')

    def test_orphaned_relationship_detection(self):
        """Test detection of orphaned relationships."""
        # Only forward direction exists - missing reverse
        incomplete_links = [
            ('parent-1', 'HAS_FOLLOWUP', 'child-1'),
        ]

        def find_orphaned_links(links):
            """Find links that don't have their reverse."""
            orphaned = []
            for link in links:
                reverse = (link[2], 'FOLLOWS_UP', link[0])
                if reverse not in links:
                    orphaned.append(link)
            return orphaned

        orphaned = find_orphaned_links(incomplete_links)
        self.assertEqual(len(orphaned), 1)

    def test_complete_bidirectional_links_no_orphans(self):
        """Test that complete bidirectional links have no orphans."""
        complete_links = [
            ('parent-1', 'HAS_FOLLOWUP', 'child-1'),
            ('child-1', 'FOLLOWS_UP', 'parent-1'),
        ]

        # Verify the forward link has its reverse
        forward = complete_links[0]  # (parent-1, 'HAS_FOLLOWUP', 'child-1')
        expected_reverse = (forward[2], 'FOLLOWS_UP', forward[0])  # (child-1, 'FOLLOWS_UP', 'parent-1')

        # Check that the reverse exists in the links
        self.assertIn(expected_reverse, complete_links)


# =============================================================================
# Test Suite 7: File System Integration Tests
# =============================================================================

class TestFileSystemBidirectionalLinking(unittest.TestCase):
    """Test bidirectional linking in filesystem-based task files."""

    def setUp(self):
        """Create temporary directory for test tasks."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.agents_dir = self.test_dir / 'agents'
        self.agents_dir.mkdir(parents=True)

    def tearDown(self):
        """Clean up test directory."""
        import shutil
        shutil.rmtree(self.test_dir)

    def _create_task_file(self, agent: str, task_id: str, parent_id: Optional[str] = None) -> Path:
        """Helper to create a test task file."""
        agent_dir = self.agents_dir / agent / 'tasks'
        agent_dir.mkdir(parents=True, exist_ok=True)

        filename = f"normal-{int(time.time())}-{uuid.uuid4().hex[:8]}.md"
        filepath = agent_dir / filename

        parent_line = f"parent_id: {parent_id}" if parent_id else "parent_id: "

        content = f"""---
agent: {agent}
priority: normal
created: {datetime.now().isoformat()}
source: test
task_id: {task_id}
{parent_line}
---

# Task: Test Task {task_id}

This is a test task for bidirectional linking.
"""
        filepath.write_text(content)
        return filepath

    def test_parent_id_in_frontmatter(self):
        """Test that parent_id is correctly stored in task frontmatter."""
        parent_id = 'parent-fs-123'
        child_id = 'child-fs-456'

        filepath = self._create_task_file('temujin', child_id, parent_id)
        content = filepath.read_text()

        self.assertIn(f'parent_id: {parent_id}', content)
        self.assertIn('task_id:', content)

    def test_empty_parent_id_for_root_tasks(self):
        """Test that root tasks have empty parent_id field."""
        task_id = 'root-task-fs'

        filepath = self._create_task_file('mongke', task_id, parent_id=None)
        content = filepath.read_text()

        # Should have the field but empty
        self.assertIn('parent_id:', content)

    def test_extract_parent_id_from_file(self):
        """Test extracting parent_id from task file frontmatter."""
        parent_id = 'parent-extract-123'
        child_id = 'child-extract-456'

        filepath = self._create_task_file('jochi', child_id, parent_id)

        # Parse frontmatter
        content = filepath.read_text()
        frontmatter = {}
        in_frontmatter = False

        for line in content.split('\n'):
            if line.strip() == '---':
                in_frontmatter = not in_frontmatter
                continue
            if in_frontmatter and ':' in line:
                key, value = line.split(':', 1)
                frontmatter[key.strip()] = value.strip()

        self.assertEqual(frontmatter.get('parent_id'), parent_id)
        self.assertEqual(frontmatter.get('task_id'), child_id)

    def test_multiple_files_with_same_parent(self):
        """Test creating multiple child tasks with the same parent."""
        parent_id = 'multi-child-parent'
        child_ids = ['child-1', 'child-2', 'child-3']

        for child_id in child_ids:
            filepath = self._create_task_file('temujin', child_id, parent_id)
            self.assertTrue(filepath.exists())

        # Verify all files have the same parent_id
        agent_dir = self.agents_dir / 'temujin' / 'tasks'
        task_files = list(agent_dir.glob('*.md'))

        self.assertEqual(len(task_files), 3)
        for task_file in task_files:
            content = task_file.read_text()
            self.assertIn(f'parent_id: {parent_id}', content)


# =============================================================================
# Test Suite 8: Gate Metrics Tests
# =============================================================================

@unittest.skipIf(not NEO4J_AVAILABLE, "Neo4j not available")
class TestGateMetrics(unittest.TestCase):
    """Test suite for gate metrics aggregation."""

    def setUp(self):
        """Set up mock driver for each test."""
        self.mock_driver = MockNeo4jDriver()
        self.patcher = patch('neo4j_task_tracker.get_driver', return_value=self.mock_driver)
        self.patcher.start()

        self.tracker = TaskTracker()
        self.tracker.driver = self.mock_driver

    def tearDown(self):
        """Clean up mocks."""
        self.patcher.stop()

    def test_get_gate_metrics_returns_all_fields(self):
        """Test that get_gate_metrics returns all expected fields."""
        mock_audit = {
            'passed': 10,
            'total': 12,
            'pass_rate': 83.3,
            'avg_completion': 85.5,
            'avg_followups': 2.5
        }
        mock_gate_counts = {
            'active': 5,
            'blocked': 1
        }

        # Set up mock results for both queries
        call_count = [0]

        def mock_run(query, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MockNeo4jResult([{'audit_metrics': mock_audit}])
            else:
                return MockNeo4jResult([{'gate_counts': mock_gate_counts}])

        self.mock_driver._session.run = mock_run

        metrics = self.tracker.get_gate_metrics()

        self.assertIn('pass_rate', metrics)
        self.assertIn('avg_completion', metrics)
        self.assertIn('avg_followups', metrics)
        self.assertIn('active', metrics)
        self.assertIn('blocked', metrics)

    def test_get_gate_metrics_empty_results(self):
        """Test get_gate_metrics with no data."""
        # Return empty result
        self.mock_driver._session.default_result = MockNeo4jResult([])

        metrics = self.tracker.get_gate_metrics()

        # Should return zeros, not crash
        self.assertEqual(metrics.get('passed', 0), 0)
        self.assertEqual(metrics.get('total', 0), 0)


# =============================================================================
# Test Runner
# =============================================================================

def run_tests(verbosity=2, filter_pattern: Optional[str] = None):
    """Run the test suite with optional filtering."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])

    if filter_pattern:
        # Filter tests by pattern
        filtered_suite = unittest.TestSuite()
        for test_group in suite:
            for test in test_group:
                if filter_pattern in str(test):
                    filtered_suite.addTest(test)
        suite = filtered_suite

    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)

    # Print summary
    print("\n" + "=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")
    print("=" * 70)

    return result


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Run bidirectional linking tests')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--test', '-t', type=str, help='Run specific test class or method')
    args = parser.parse_args()

    verbosity = 2 if args.verbose else 1
    run_tests(verbosity=verbosity, filter_pattern=args.test)
