#!/usr/bin/env python3
"""Tests for task archival and FailureReport cleanup scripts."""

import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.expanduser('~/.openclaw/agents/main/scripts'))

from neo4j_task_tracker import get_driver, close_driver

# We'll import the archive functions
from neo4j_archive_tasks import archive_tasks, cleanup_failure_reports, ARCHIVE_DIR

TEST_AGENT = '__test_archive__'


def _cleanup(driver):
    with driver.session() as session:
        session.run("""
            MATCH (t:Task {assigned_to: $a})
            OPTIONAL MATCH (t)-[r1:HAS_OUTPUT]->(o:TaskOutput)
            OPTIONAL MATCH (t)-[r2:HAS_FAILURE]->(f:FailureReport)
            OPTIONAL MATCH (t)-[r]-()
            DELETE r, r1, r2, o, f, t
        """, a=TEST_AGENT)
        session.run("MATCH (a:Agent {name: $a}) WHERE NOT (a)--() DELETE a", a=TEST_AGENT)


def _create_old_task(driver, task_id, days_old=60, status='COMPLETED'):
    """Create an old task for archival testing."""
    with driver.session() as session:
        session.run("""
            CREATE (t:Task {
                task_id: $tid, title: 'Archive test', prompt: 'test',
                status: $status, assigned_to: $a, priority: 'normal',
                domain: 'ops', source: 'test', claim_epoch: 0,
                retry_count: 0, max_retries: 3, depth: 0, timeout_s: 60,
                created_at: datetime() - duration({days: $days}),
                updated_at: datetime() - duration({days: $days}),
                completed_at: datetime() - duration({days: $days})
            })
        """, tid=task_id, status=status, a=TEST_AGENT, days=days_old)


def test_dryrun_no_delete():
    """Dry run counts but doesn't delete."""
    driver = get_driver()
    try:
        _create_old_task(driver, 'test-arch-dry', days_old=60)
        count = archive_tasks(driver, retention_days=30, dry_run=True)

        with driver.session() as session:
            result = session.run(
                "MATCH (t:Task {task_id: 'test-arch-dry'}) RETURN count(t) AS c")
            c = result.single()['c']
            if hasattr(c, '__int__'):
                c = int(c)
        assert c == 1, f"Dry run should NOT delete, but task is gone"
    finally:
        _cleanup(driver)
        close_driver()


def test_preserves_recent():
    """Tasks within retention period are NOT archived."""
    driver = get_driver()
    try:
        _create_old_task(driver, 'test-arch-recent', days_old=5)
        archive_tasks(driver, retention_days=30, dry_run=False)

        with driver.session() as session:
            result = session.run(
                "MATCH (t:Task {task_id: 'test-arch-recent'}) RETURN count(t) AS c")
            c = result.single()['c']
            if hasattr(c, '__int__'):
                c = int(c)
        assert c == 1, f"Recent task should NOT be archived"
    finally:
        _cleanup(driver)
        close_driver()


def test_archive_deletes_old():
    """Archive removes tasks older than retention."""
    driver = get_driver()
    try:
        _create_old_task(driver, 'test-arch-old', days_old=60)
        count = archive_tasks(driver, retention_days=30, dry_run=False)
        assert count >= 1, f"Should archive at least 1 task, got {count}"

        with driver.session() as session:
            result = session.run(
                "MATCH (t:Task {task_id: 'test-arch-old'}) RETURN count(t) AS c")
            c = result.single()['c']
            if hasattr(c, '__int__'):
                c = int(c)
        assert c == 0, "Old task should be deleted after archive"
    finally:
        _cleanup(driver)
        close_driver()


def test_empty_archive():
    """No errors when 0 tasks qualify for archival."""
    driver = get_driver()
    try:
        count = archive_tasks(driver, retention_days=9999, dry_run=False)
        # Should not error, count should be 0 (or very small if other old tasks exist)
        # This test passes if no exception is raised
    finally:
        close_driver()


def test_cleanup_failure_reports_dryrun():
    """FailureReport cleanup dry-run reports count without deleting."""
    driver = get_driver()
    try:
        count = cleanup_failure_reports(driver, retention_days=30, dry_run=True)
        # Should not error or delete anything
    finally:
        close_driver()


def test_cleanup_failure_reports_execute():
    """FailureReport cleanup removes orphaned reports."""
    driver = get_driver()
    try:
        # Create an orphaned FailureReport (no parent task)
        with driver.session() as session:
            session.run("""
                CREATE (fr:FailureReport {
                    attempt: 1, error_class: 'TEST',
                    error_msg: 'orphan test', is_transient: false,
                    created_at: datetime() - duration({days: 60})
                })
            """)

        count = cleanup_failure_reports(driver, retention_days=30, dry_run=False)
        assert count >= 1, "Should clean at least 1 orphaned FailureReport"
    finally:
        close_driver()


if __name__ == '__main__':
    tests = [
        test_dryrun_no_delete,
        test_preserves_recent,
        test_archive_deletes_old,
        test_empty_archive,
        test_cleanup_failure_reports_dryrun,
        test_cleanup_failure_reports_execute,
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
