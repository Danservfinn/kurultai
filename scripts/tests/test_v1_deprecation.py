#!/usr/bin/env python3
"""Tests for V1 deprecation guards and status normalization migration."""

import sys
import os
import warnings

sys.path.insert(0, os.path.expanduser('~/.openclaw/agents/main/scripts'))

from neo4j_task_tracker import TaskTracker, neo4j_session


TEST_AGENT = '__test_v1dep__'


def _cleanup():
    with neo4j_session() as session:
        session.run("""
            MATCH (t:Task) WHERE t.assigned_to = $a OR t.agent = $a
            OPTIONAL MATCH (t)-[r]-()
            DELETE r, t
        """, a=TEST_AGENT)
        session.run("MATCH (a:Agent {name: $a}) WHERE NOT (a)--() DELETE a", a=TEST_AGENT)


def test_deprecation_warning_create():
    """create_task() emits DeprecationWarning when V1_DEPRECATED=true."""
    os.environ['V1_DEPRECATED'] = 'true'
    # Re-import to pick up env change
    import neo4j_task_tracker as ntt
    ntt._V1_DEPRECATED = True

    tracker = TaskTracker()
    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            tracker.create_task('test-dep-1', TEST_AGENT, 'Test deprecation')
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1, \
                f"Expected DeprecationWarning, got {len(dep_warnings)} warnings: {[str(x.message) for x in w]}"
    finally:
        _cleanup()
        tracker.close()


def test_deprecation_warning_update_status():
    """update_status() emits DeprecationWarning."""
    import neo4j_task_tracker as ntt
    ntt._V1_DEPRECATED = True

    tracker = TaskTracker()
    try:
        # Create task first (ignore its warning)
        tracker.create_task('test-dep-2', TEST_AGENT, 'Test update')
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            tracker.update_status('test-dep-2', 'completed')
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1, "update_status should emit DeprecationWarning"
    finally:
        _cleanup()
        tracker.close()


def test_deprecation_warning_increment_retry():
    """increment_retry() emits DeprecationWarning."""
    import neo4j_task_tracker as ntt
    ntt._V1_DEPRECATED = True

    tracker = TaskTracker()
    try:
        tracker.create_task('test-dep-3', TEST_AGENT, 'Test retry')
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            tracker.increment_retry('test-dep-3')
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1, "increment_retry should emit DeprecationWarning"
    finally:
        _cleanup()
        tracker.close()


def test_deprecation_disabled():
    """V1_DEPRECATED=false suppresses warnings."""
    import neo4j_task_tracker as ntt
    ntt._V1_DEPRECATED = False

    tracker = TaskTracker()
    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            tracker.create_task('test-dep-4', TEST_AGENT, 'Test no warning')
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) == 0, \
                f"Should NOT emit warning when disabled, got {len(dep_warnings)}"
    finally:
        ntt._V1_DEPRECATED = True  # Restore
        _cleanup()
        tracker.close()


def test_readonly_no_warning():
    """Read-only methods never emit warnings."""
    import neo4j_task_tracker as ntt
    ntt._V1_DEPRECATED = True

    tracker = TaskTracker()
    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            tracker.get_tasks_by_agent(TEST_AGENT)
            tracker.get_hourly_summary()
            tracker.get_completion_rate()
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) == 0, \
                f"Read-only methods should NOT warn, got {len(dep_warnings)}"
    finally:
        tracker.close()


def test_migration_dryrun():
    """Migration dry-run reports counts without modifying."""
    from neo4j_migrate_v1_status import migrate_statuses
    from neo4j_task_tracker import get_driver
    driver = get_driver()
    try:
        # Insert a test task with lowercase status
        with neo4j_session() as session:
            session.run("""
                CREATE (t:Task {
                    task_id: 'test-mig-dry', status: 'ready',
                    assigned_to: $a, created_at: datetime(), updated_at: datetime()
                })
            """, a=TEST_AGENT)

        count = migrate_statuses(driver, dry_run=True)
        # Verify the task still has lowercase status (not changed)
        with neo4j_session() as session:
            result = session.run(
                "MATCH (t:Task {task_id: 'test-mig-dry'}) RETURN t.status AS s")
            status = result.single()['s']
        assert status == 'ready', f"Dry run should not change status, got {status}"
    finally:
        _cleanup()


def test_migration_execute():
    """Execute normalizes ready->PENDING."""
    from neo4j_migrate_v1_status import migrate_statuses
    from neo4j_task_tracker import get_driver
    driver = get_driver()
    try:
        with neo4j_session() as session:
            session.run("""
                CREATE (t:Task {
                    task_id: 'test-mig-exec', status: 'ready',
                    assigned_to: $a, created_at: datetime(), updated_at: datetime()
                })
            """, a=TEST_AGENT)

        migrate_statuses(driver, dry_run=False)

        with neo4j_session() as session:
            result = session.run(
                "MATCH (t:Task {task_id: 'test-mig-exec'}) RETURN t.status AS s")
            status = result.single()['s']
        assert status == 'PENDING', f"Should normalize to PENDING, got {status}"
    finally:
        _cleanup()


def test_migration_idempotent():
    """Running migration twice produces same result."""
    from neo4j_migrate_v1_status import migrate_statuses
    from neo4j_task_tracker import get_driver
    driver = get_driver()
    try:
        with neo4j_session() as session:
            session.run("""
                CREATE (t:Task {
                    task_id: 'test-mig-idem', status: 'running',
                    assigned_to: $a, created_at: datetime(), updated_at: datetime()
                })
            """, a=TEST_AGENT)

        migrate_statuses(driver, dry_run=False)
        migrate_statuses(driver, dry_run=False)  # Second run

        with neo4j_session() as session:
            result = session.run(
                "MATCH (t:Task {task_id: 'test-mig-idem'}) RETURN t.status AS s")
            status = result.single()['s']
        assert status == 'WORKING', f"Should be WORKING, got {status}"
    finally:
        _cleanup()


def test_no_lowercase_after_migration():
    """Post-migration: no lowercase statuses remain for test tasks."""
    from neo4j_migrate_v1_status import migrate_statuses
    from neo4j_task_tracker import get_driver
    driver = get_driver()
    try:
        with neo4j_session() as session:
            for old_status in ['ready', 'running', 'completed', 'failed', 'killed']:
                session.run("""
                    CREATE (t:Task {
                        task_id: $tid, status: $s,
                        assigned_to: $a, created_at: datetime(), updated_at: datetime()
                    })
                """, tid=f'test-mig-lc-{old_status}', s=old_status, a=TEST_AGENT)

        migrate_statuses(driver, dry_run=False)

        with neo4j_session() as session:
            result = session.run("""
                MATCH (t:Task) WHERE t.assigned_to = $a AND t.status =~ '[a-z]+'
                RETURN count(t) AS cnt
            """, a=TEST_AGENT)
            count = result.single()['cnt']
        if hasattr(count, '__int__'):
            count = int(count)
        assert count == 0, f"Found {count} tasks with lowercase status after migration"
    finally:
        _cleanup()


if __name__ == '__main__':
    tests = [
        test_deprecation_warning_create,
        test_deprecation_warning_update_status,
        test_deprecation_warning_increment_retry,
        test_deprecation_disabled,
        test_readonly_no_warning,
        test_migration_dryrun,
        test_migration_execute,
        test_migration_idempotent,
        test_no_lowercase_after_migration,
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
