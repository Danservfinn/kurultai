#!/usr/bin/env python3
"""Tests for ORPHANED intermediate state and orphan recovery lifecycle."""

import sys
import os

sys.path.insert(0, os.path.expanduser('~/.openclaw/agents/main/scripts'))

from neo4j_v2_core import TaskStore
from neo4j_v2_schema import apply_schema

TEST_AGENT = '__test_orphan__'


def _cleanup(store):
    with store.driver.session() as session:
        session.run("""
            MATCH (t:Task {assigned_to: $a})
            OPTIONAL MATCH (t)-[r1:HAS_OUTPUT]->(o:TaskOutput)
            OPTIONAL MATCH (t)-[r2:HAS_FAILURE]->(f:FailureReport)
            OPTIONAL MATCH ()-[r3]->(t)
            DELETE r1, r2, r3, o, f, t
        """, a=TEST_AGENT)
        session.run("MATCH (a:Agent {name: $a}) WHERE NOT (a)--() DELETE a", a=TEST_AGENT)


def _create_working_task(store, task_id, lease_expired=True, retry_count=0, max_retries=3):
    """Create a WORKING task with optionally expired lease."""
    store.create_task(task_id=task_id, title=f'Orphan test {task_id}',
                      prompt='test', assigned_to=TEST_AGENT, priority='normal',
                      domain='ops', source='test', max_retries=max_retries)
    claimed = store.claim_task(TEST_AGENT)
    if lease_expired:
        with store.driver.session() as session:
            session.run("""
                MATCH (t:Task {task_id: $tid})
                SET t.lease_expires_at = datetime() - duration({minutes: 30}),
                    t.retry_count = $rc
            """, tid=task_id, rc=retry_count)
    return claimed


def test_orphan_recovery_sets_orphaned():
    """Expired-lease WORKING task -> ORPHANED, not PENDING."""
    store = TaskStore()
    try:
        task_id = 'normal-0000000000-orphan-1'
        _create_working_task(store, task_id, lease_expired=True)
        recovered = store.recover_orphans(grace_minutes=1)
        assert len(recovered) >= 1, "Should recover at least 1 task"
        found = [t for t in recovered if t['task_id'] == task_id]
        assert len(found) == 1, f"Should find our task in recovered list"
        assert found[0]['status'] == 'ORPHANED', \
            f"Should be ORPHANED, got {found[0]['status']}"
    finally:
        _cleanup(store)


def test_orphan_recovery_maxretries_sets_failed():
    """Expired-lease WORKING task at max_retries -> FAILED."""
    store = TaskStore()
    try:
        task_id = 'normal-0000000000-orphan-2'
        _create_working_task(store, task_id, lease_expired=True,
                             retry_count=3, max_retries=3)
        recovered = store.recover_orphans(grace_minutes=1)
        found = [t for t in recovered if t['task_id'] == task_id]
        assert len(found) == 1, "Should find our task"
        assert found[0]['status'] == 'FAILED', \
            f"Max retries reached, should be FAILED, got {found[0]['status']}"
    finally:
        _cleanup(store)


def test_claim_skips_orphaned():
    """claim_task() must NOT return ORPHANED tasks."""
    store = TaskStore()
    try:
        task_id = 'normal-0000000000-orphan-3'
        store.create_task(task_id=task_id, title='Orphan skip test',
                          prompt='test', assigned_to=TEST_AGENT, priority='normal',
                          domain='ops', source='test')
        # Manually set to ORPHANED
        with store.driver.session() as session:
            session.run("""
                MATCH (t:Task {task_id: $tid})
                SET t.status = 'ORPHANED', t.orphaned_at = datetime()
            """, tid=task_id)

        claimed = store.claim_task(TEST_AGENT)
        assert claimed is None or claimed.get('task_id') != task_id, \
            "claim_task should NOT return ORPHANED tasks"
    finally:
        _cleanup(store)


def test_promote_after_hold():
    """ORPHANED for > hold_minutes -> promoted to PENDING."""
    store = TaskStore()
    try:
        task_id = 'normal-0000000000-orphan-4'
        store.create_task(task_id=task_id, title='Promote test',
                          prompt='test', assigned_to=TEST_AGENT, priority='normal',
                          domain='ops', source='test')
        # Set to ORPHANED with old orphaned_at
        with store.driver.session() as session:
            session.run("""
                MATCH (t:Task {task_id: $tid})
                SET t.status = 'ORPHANED',
                    t.orphaned_at = datetime() - duration({minutes: 10})
            """, tid=task_id)

        promoted = store.promote_orphans(hold_minutes=5)
        found = [t for t in promoted if t['task_id'] == task_id]
        assert len(found) == 1, "Should promote our task"
        assert found[0]['status'] == 'PENDING', \
            f"Should be PENDING after promotion, got {found[0]['status']}"
    finally:
        _cleanup(store)


def test_promote_within_hold():
    """ORPHANED for < hold_minutes -> stays ORPHANED."""
    store = TaskStore()
    try:
        task_id = 'normal-0000000000-orphan-5'
        store.create_task(task_id=task_id, title='Hold test',
                          prompt='test', assigned_to=TEST_AGENT, priority='normal',
                          domain='ops', source='test')
        # Set to ORPHANED just now
        with store.driver.session() as session:
            session.run("""
                MATCH (t:Task {task_id: $tid})
                SET t.status = 'ORPHANED',
                    t.orphaned_at = datetime()
            """, tid=task_id)

        promoted = store.promote_orphans(hold_minutes=5)
        found = [t for t in promoted if t['task_id'] == task_id]
        assert len(found) == 0, "Should NOT promote task within hold period"

        # Verify still ORPHANED
        with store.driver.session() as session:
            result = session.run("MATCH (t:Task {task_id: $tid}) RETURN t.status AS s",
                                 tid=task_id)
            status = result.single()['s']
        assert status == 'ORPHANED', f"Should still be ORPHANED, got {status}"
    finally:
        _cleanup(store)


def test_complete_orphaned_rejected():
    """complete_task() on ORPHANED task -> (False, reason)."""
    store = TaskStore()
    try:
        task_id = 'normal-0000000000-orphan-6'
        store.create_task(task_id=task_id, title='Complete orphan test',
                          prompt='test', assigned_to=TEST_AGENT, priority='normal',
                          domain='ops', source='test')
        claimed = store.claim_task(TEST_AGENT)
        epoch = claimed['claim_epoch']

        # Set to ORPHANED (simulating orphan recovery)
        with store.driver.session() as session:
            session.run("""
                MATCH (t:Task {task_id: $tid})
                SET t.status = 'ORPHANED', t.orphaned_at = datetime()
            """, tid=task_id)

        ok, reason = store.complete_task(task_id, epoch,
                                          text='test', problem='test',
                                          solution='test', rationale='test')
        assert not ok, f"Should reject completion of ORPHANED task, got ok={ok}"
    finally:
        _cleanup(store)


def test_full_orphan_lifecycle():
    """WORKING -> ORPHANED -> PENDING -> claim -> WORKING -> complete."""
    store = TaskStore()
    try:
        task_id = 'normal-0000000000-orphan-7'
        _create_working_task(store, task_id, lease_expired=True)

        # Step 1: Orphan recovery
        recovered = store.recover_orphans(grace_minutes=1)
        found = [t for t in recovered if t['task_id'] == task_id]
        assert len(found) == 1 and found[0]['status'] == 'ORPHANED', "Should be ORPHANED"

        # Step 2: Fast-forward orphaned_at and promote
        with store.driver.session() as session:
            session.run("""
                MATCH (t:Task {task_id: $tid})
                SET t.orphaned_at = datetime() - duration({minutes: 10})
            """, tid=task_id)

        promoted = store.promote_orphans(hold_minutes=5)
        found_p = [t for t in promoted if t['task_id'] == task_id]
        assert len(found_p) == 1 and found_p[0]['status'] == 'PENDING', "Should be PENDING"

        # Step 3: Claim again
        claimed = store.claim_task(TEST_AGENT)
        assert claimed is not None and claimed['task_id'] == task_id, "Should claim"

        # Step 4: Complete
        ok, reason = store.complete_task(task_id, claimed['claim_epoch'],
                                          text='done', problem='test',
                                          solution='fixed', rationale='test')
        assert ok, f"Should complete, got reason={reason}"
    finally:
        _cleanup(store)


def test_grace_period_respected():
    """Tasks expired < grace_minutes ago are NOT recovered."""
    store = TaskStore()
    try:
        task_id = 'normal-0000000000-orphan-8'
        store.create_task(task_id=task_id, title='Grace test',
                          prompt='test', assigned_to=TEST_AGENT, priority='normal',
                          domain='ops', source='test')
        claimed = store.claim_task(TEST_AGENT)
        # Set lease to just barely expired (1 minute ago)
        with store.driver.session() as session:
            session.run("""
                MATCH (t:Task {task_id: $tid})
                SET t.lease_expires_at = datetime() - duration({minutes: 1})
            """, tid=task_id)

        # Use high grace period so it shouldn't be recovered
        recovered = store.recover_orphans(grace_minutes=10)
        found = [t for t in recovered if t['task_id'] == task_id]
        assert len(found) == 0, "Should NOT recover task within grace period"
    finally:
        _cleanup(store)


if __name__ == '__main__':
    store = TaskStore()
    apply_schema(store.driver, verbose=False)

    tests = [
        test_orphan_recovery_sets_orphaned,
        test_orphan_recovery_maxretries_sets_failed,
        test_claim_skips_orphaned,
        test_promote_after_hold,
        test_promote_within_hold,
        test_complete_orphaned_rejected,
        test_full_orphan_lifecycle,
        test_grace_period_respected,
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
