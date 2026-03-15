#!/usr/bin/env python3
"""Tests for SPAWNED relationship depth bounds in complete_task()."""

import sys
import os

sys.path.insert(0, os.path.expanduser('~/.openclaw/agents/main/scripts'))

from neo4j_v2_core import TaskStore
from neo4j_v2_schema import apply_schema

TEST_AGENT = '__test_depth__'


def _cleanup(store):
    with store.driver.session() as session:
        session.run("""
            MATCH (t:Task {assigned_to: $a})
            OPTIONAL MATCH (t)-[r1:HAS_OUTPUT]->(o:TaskOutput)
            OPTIONAL MATCH (t)-[r2:HAS_FAILURE]->(f:FailureReport)
            OPTIONAL MATCH (t)-[r]-()
            DELETE r, r1, r2, o, f, t
        """, a=TEST_AGENT)
        session.run("MATCH (a:Agent {name: $a}) WHERE NOT (a)--() DELETE a", a=TEST_AGENT)


def test_pending_child_blocks_completion():
    """Parent cannot complete while child is PENDING."""
    store = TaskStore()
    try:
        parent_id = 'normal-0000000000-depth-p1'
        child_id = 'normal-0000000000-depth-c1'
        store.create_task(task_id=parent_id, title='Parent', prompt='test',
                          assigned_to=TEST_AGENT, priority='normal', domain='ops', source='test')
        store.create_task(task_id=child_id, title='Child', prompt='test',
                          assigned_to=TEST_AGENT, priority='normal', domain='ops', source='test',
                          parent_id=parent_id)

        # Claim parent
        claimed = store.claim_task(TEST_AGENT)
        # If child was claimed instead, claim again for the other
        if claimed['task_id'] == child_id:
            # Put child back and claim parent
            with store.driver.session() as session:
                session.run("MATCH (t:Task {task_id: $tid}) SET t.status = 'PENDING'", tid=child_id)
            claimed = store.claim_task(TEST_AGENT)

        # Try to complete parent while child is PENDING
        ok, reason = store.complete_task(parent_id, claimed['claim_epoch'],
                                          text='done', problem='test',
                                          solution='test', rationale='test')
        assert not ok, f"Should block: child is PENDING, got ok={ok}"
        assert 'block' in reason.lower() or 'child' in reason.lower(), \
            f"Reason should mention blocking children: {reason}"
    finally:
        _cleanup(store)


def test_completed_child_allows_completion():
    """Task with only COMPLETED children can complete."""
    store = TaskStore()
    try:
        parent_id = 'normal-0000000000-depth-p2'
        child_id = 'normal-0000000000-depth-c2'
        store.create_task(task_id=parent_id, title='Parent', prompt='test',
                          assigned_to=TEST_AGENT, priority='normal', domain='ops', source='test')
        store.create_task(task_id=child_id, title='Child', prompt='test',
                          assigned_to=TEST_AGENT, priority='normal', domain='ops', source='test',
                          parent_id=parent_id)

        # Set child to COMPLETED directly via Cypher (avoid claim ordering issues)
        with store.driver.session() as session:
            session.run("""
                MATCH (t:Task {task_id: $tid})
                SET t.status = 'COMPLETED', t.completed_at = datetime()
            """, tid=child_id)

        # Claim and complete parent
        claimed_parent = store.claim_task(TEST_AGENT)
        assert claimed_parent is not None, "Should be able to claim parent"
        assert claimed_parent['task_id'] == parent_id, f"Should claim parent, got {claimed_parent['task_id']}"
        ok, reason = store.complete_task(parent_id, claimed_parent['claim_epoch'],
                                          text='done', problem='test',
                                          solution='test', rationale='test')
        assert ok, f"Should succeed with COMPLETED child, got reason={reason}"
    finally:
        _cleanup(store)


def test_no_children_allows_completion():
    """Task with no children can complete."""
    store = TaskStore()
    try:
        task_id = 'normal-0000000000-depth-solo'
        store.create_task(task_id=task_id, title='Solo', prompt='test',
                          assigned_to=TEST_AGENT, priority='normal', domain='ops', source='test')
        claimed = store.claim_task(TEST_AGENT)
        ok, reason = store.complete_task(task_id, claimed['claim_epoch'],
                                          text='done', problem='test',
                                          solution='test', rationale='test')
        assert ok, f"Should succeed with no children, got reason={reason}"
    finally:
        _cleanup(store)


def test_working_child_blocks_completion():
    """Task with WORKING child blocks completion."""
    store = TaskStore()
    try:
        parent_id = 'normal-0000000000-depth-p3'
        child_id = 'normal-0000000000-depth-c3'
        store.create_task(task_id=parent_id, title='Parent', prompt='test',
                          assigned_to=TEST_AGENT, priority='normal', domain='ops', source='test')
        store.create_task(task_id=child_id, title='Child', prompt='test',
                          assigned_to=TEST_AGENT, priority='normal', domain='ops', source='test',
                          parent_id=parent_id)

        # Claim both - child becomes WORKING
        store.claim_task(TEST_AGENT)  # Claims highest-priority first
        store.claim_task(TEST_AGENT)  # Claims the other

        # Get parent's epoch
        with store.driver.session() as session:
            result = session.run(
                "MATCH (t:Task {task_id: $tid}) RETURN t.claim_epoch AS e, t.status AS s",
                tid=parent_id)
            rec = result.single()
            parent_epoch = rec['e']

        ok, reason = store.complete_task(parent_id, parent_epoch,
                                          text='done', problem='test',
                                          solution='test', rationale='test')
        assert not ok, "Should block: child is WORKING"
    finally:
        _cleanup(store)


def test_failed_child_allows_completion():
    """Task with FAILED child allows completion (FAILED is terminal)."""
    store = TaskStore()
    try:
        parent_id = 'normal-0000000000-depth-p4'
        child_id = 'normal-0000000000-depth-c4'
        store.create_task(task_id=parent_id, title='Parent', prompt='test',
                          assigned_to=TEST_AGENT, priority='normal', domain='ops', source='test')
        store.create_task(task_id=child_id, title='Child', prompt='test',
                          assigned_to=TEST_AGENT, priority='normal', domain='ops', source='test',
                          parent_id=parent_id)

        # Set child to FAILED directly via Cypher
        with store.driver.session() as session:
            session.run("""
                MATCH (t:Task {task_id: $tid})
                SET t.status = 'FAILED', t.completed_at = datetime()
            """, tid=child_id)

        # Claim and complete parent
        claimed_parent = store.claim_task(TEST_AGENT)
        assert claimed_parent is not None, "Should claim parent"
        assert claimed_parent['task_id'] == parent_id, f"Should claim parent, got {claimed_parent['task_id']}"
        ok, reason = store.complete_task(parent_id, claimed_parent['claim_epoch'],
                                          text='done', problem='test',
                                          solution='test', rationale='test')
        assert ok, f"Should succeed with FAILED child, got reason={reason}"
    finally:
        _cleanup(store)


def test_depth_5_chain_blocked():
    """5-deep chain with PENDING leaf blocks root completion."""
    store = TaskStore()
    try:
        ids = [f'normal-0000000000-depth5-{i}' for i in range(6)]  # root + 5 children

        # Create chain: root -> c1 -> c2 -> c3 -> c4 -> leaf(PENDING)
        store.create_task(task_id=ids[0], title='Root', prompt='test',
                          assigned_to=TEST_AGENT, priority='normal', domain='ops', source='test')
        for i in range(1, 6):
            store.create_task(task_id=ids[i], title=f'Child-{i}', prompt='test',
                              assigned_to=TEST_AGENT, priority='normal', domain='ops', source='test',
                              parent_id=ids[i-1], depth=i)

        # Set all except leaf to WORKING with proper epochs
        with store.driver.session() as session:
            for i in range(5):
                session.run("""
                    MATCH (t:Task {task_id: $tid})
                    SET t.status = 'WORKING', t.claim_epoch = 1
                """, tid=ids[i])

        # Try to complete root
        ok, reason = store.complete_task(ids[0], 1,
                                          text='done', problem='test',
                                          solution='test', rationale='test')
        assert not ok, "Should block: PENDING child at depth 5"
    finally:
        _cleanup(store)


def test_depth_6_not_blocked():
    """6-deep chain — leaf beyond depth 5 bound is not seen, root completes."""
    store = TaskStore()
    try:
        ids = [f'normal-0000000000-depth6-{i}' for i in range(7)]  # root + 6 children

        store.create_task(task_id=ids[0], title='Root', prompt='test',
                          assigned_to=TEST_AGENT, priority='normal', domain='ops', source='test')
        for i in range(1, 7):
            store.create_task(task_id=ids[i], title=f'Child-{i}', prompt='test',
                              assigned_to=TEST_AGENT, priority='normal', domain='ops', source='test',
                              parent_id=ids[i-1], depth=i)

        # Set all middle nodes to COMPLETED, only leaf at depth 6 is PENDING
        with store.driver.session() as session:
            session.run("MATCH (t:Task {task_id: $tid}) SET t.status = 'WORKING', t.claim_epoch = 1",
                        tid=ids[0])
            for i in range(1, 6):
                session.run("MATCH (t:Task {task_id: $tid}) SET t.status = 'COMPLETED'",
                            tid=ids[i])
            # ids[6] stays PENDING — at depth 6 (beyond *1..5 bound)

        ok, reason = store.complete_task(ids[0], 1,
                                          text='done', problem='test',
                                          solution='test', rationale='test')
        assert ok, f"Should succeed — depth 6 is beyond bound, got reason={reason}"
    finally:
        _cleanup(store)


if __name__ == '__main__':
    store = TaskStore()
    apply_schema(store.driver, verbose=False)

    tests = [
        test_pending_child_blocks_completion,
        test_completed_child_allows_completion,
        test_no_children_allows_completion,
        test_working_child_blocks_completion,
        test_failed_child_allows_completion,
        test_depth_5_chain_blocked,
        test_depth_6_not_blocked,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  [PASS] {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {e}")
            failed += 1
    print(f"\nResults: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
