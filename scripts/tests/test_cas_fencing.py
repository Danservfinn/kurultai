#!/usr/bin/env python3
"""Unit tests for CAS fencing, retry backoff, and claim_epoch guards."""

import sys
import os

sys.path.insert(0, os.path.expanduser('~/.openclaw/agents/main/scripts'))

from neo4j_v2_core import TaskStore
from neo4j_v2_schema import apply_schema


def _cleanup_test_tasks(agent, store):
    with store.driver.session() as session:
        session.run("""
            MATCH (t:Task {assigned_to: $a})
            OPTIONAL MATCH (t)-[r1:HAS_OUTPUT]->(o:TaskOutput)
            OPTIONAL MATCH (t)-[r2:HAS_FAILURE]->(f:FailureReport)
            OPTIONAL MATCH ()-[r3]->(t)
            DELETE r1, r2, r3, o, f, t
        """, a=agent)
        session.run("""
            MATCH (a:Agent {name: $a}) WHERE NOT (a)--() DELETE a
        """, a=agent)


TEST_AGENT = '__test_cas__'


def test_retry_after_future():
    """Task with future retry_after should NOT be claimable."""
    store = TaskStore()
    try:
        task_id = f"normal-0000000000-cas-future"
        store.create_task(task_id=task_id, title='Test retry_after future',
                          prompt='test', assigned_to=TEST_AGENT, priority='normal',
                          domain='ops', source='test')
        with store.driver.session() as session:
            session.run("""
                MATCH (t:Task {task_id: $tid})
                SET t.retry_after = datetime() + duration({minutes: 10})
            """, tid=task_id)

        claimed = store.claim_task(TEST_AGENT)
        assert claimed is None or claimed.get('task_id') != task_id, \
            f"Should NOT claim task with future retry_after, got {claimed}"
    finally:
        _cleanup_test_tasks(TEST_AGENT, store)


def test_retry_after_past():
    """Task with past retry_after SHOULD be claimable."""
    store = TaskStore()
    try:
        task_id = f"normal-0000000000-cas-past"
        store.create_task(task_id=task_id, title='Test retry_after past',
                          prompt='test', assigned_to=TEST_AGENT, priority='normal',
                          domain='ops', source='test')
        with store.driver.session() as session:
            session.run("""
                MATCH (t:Task {task_id: $tid})
                SET t.retry_after = datetime() - duration({minutes: 1})
            """, tid=task_id)

        claimed = store.claim_task(TEST_AGENT)
        assert claimed is not None and claimed.get('task_id') == task_id, \
            f"Should claim task with past retry_after"
    finally:
        _cleanup_test_tasks(TEST_AGENT, store)


def test_retry_after_null():
    """Task with NULL retry_after SHOULD be claimable."""
    store = TaskStore()
    try:
        task_id = f"normal-0000000000-cas-null"
        store.create_task(task_id=task_id, title='Test retry_after null',
                          prompt='test', assigned_to=TEST_AGENT, priority='normal',
                          domain='ops', source='test')

        claimed = store.claim_task(TEST_AGENT)
        assert claimed is not None and claimed.get('task_id') == task_id, \
            f"Should claim task with null retry_after"
    finally:
        _cleanup_test_tasks(TEST_AGENT, store)


def test_backoff_progression():
    """Verify exponential backoff sets retry_after on transient failure."""
    store = TaskStore()
    try:
        task_id = f"normal-0000000000-cas-backoff"
        store.create_task(task_id=task_id, title='Test backoff',
                          prompt='test', assigned_to=TEST_AGENT, priority='normal',
                          domain='ops', source='test', max_retries=6)

        # Claim and fail with transient error
        claimed = store.claim_task(TEST_AGENT)
        assert claimed is not None, "Should claim task"
        ok, new_status = store.fail_task(task_id, claimed['claim_epoch'],
                                          'TRANSIENT', 'test error', is_transient=True)
        assert ok, "fail_task should succeed"
        assert new_status == 'PENDING', f"Should be PENDING after transient fail, got {new_status}"

        # Check retry_after is set
        with store.driver.session() as session:
            result = session.run("""
                MATCH (t:Task {task_id: $tid})
                RETURN t.retry_after AS ra, t.retry_count AS rc
            """, tid=task_id)
            record = result.single()
            assert record['ra'] is not None, "retry_after should be set after transient failure"
            assert record['rc'] == 1 or int(record['rc']) == 1, \
                f"Retry count should be 1, got {record['rc']}"
    finally:
        _cleanup_test_tasks(TEST_AGENT, store)


def test_stale_epoch_rejection():
    """complete_task() with wrong claim_epoch must fail."""
    store = TaskStore()
    try:
        task_id = f"normal-0000000000-cas-stale"
        store.create_task(task_id=task_id, title='Test stale epoch',
                          prompt='test', assigned_to=TEST_AGENT, priority='normal',
                          domain='ops', source='test')
        claimed = store.claim_task(TEST_AGENT)
        assert claimed is not None, "Should claim task"
        stale_epoch = claimed['claim_epoch'] - 1
        ok, reason = store.complete_task(task_id, stale_epoch,
                                          text='test', problem='test',
                                          solution='test', rationale='test')
        assert not ok, f"Should reject stale epoch, got ok={ok}"
        assert 'epoch' in reason.lower() or 'mismatch' in reason.lower() or 'wrong' in reason.lower(), \
            f"Reason should mention epoch issue: {reason}"
    finally:
        _cleanup_test_tasks(TEST_AGENT, store)


def test_permanent_failure():
    """fail_task() with is_transient=False -> FAILED regardless of retry budget."""
    store = TaskStore()
    try:
        task_id = f"normal-0000000000-cas-perm"
        store.create_task(task_id=task_id, title='Test permanent fail',
                          prompt='test', assigned_to=TEST_AGENT, priority='normal',
                          domain='ops', source='test')
        claimed = store.claim_task(TEST_AGENT)
        assert claimed is not None, "Should claim task"
        ok, new_status = store.fail_task(task_id, claimed['claim_epoch'],
                                          'PERMANENT', 'fatal error', is_transient=False)
        assert ok, "fail_task should succeed"
        with store.driver.session() as session:
            result = session.run("MATCH (t:Task {task_id: $tid}) RETURN t.status AS s", tid=task_id)
            status = result.single()['s']
        assert status == 'FAILED', f"Permanent failure should set FAILED, got {status}"
    finally:
        _cleanup_test_tasks(TEST_AGENT, store)


if __name__ == '__main__':
    # Ensure schema
    store = TaskStore()
    apply_schema(store.driver, verbose=False)

    tests = [test_retry_after_future, test_retry_after_past, test_retry_after_null,
             test_backoff_progression, test_stale_epoch_rejection, test_permanent_failure]
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
