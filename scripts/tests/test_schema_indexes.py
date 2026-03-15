#!/usr/bin/env python3
"""Verify schema state after overhaul: indexes, constraints, and dropped artifacts."""

import sys
import os

sys.path.insert(0, os.path.expanduser('~/.openclaw/agents/main/scripts'))

from neo4j_task_tracker import get_driver, close_driver
from neo4j_v2_schema import apply_schema, verify_schema, V2_DEPRECATED_INDEXES, V2_DEAD_CONSTRAINTS


def _get_schema_names(driver):
    """Get all index and constraint names from Neo4j."""
    names = set()
    with driver.session() as session:
        for label in ("INDEXES", "CONSTRAINTS"):
            try:
                for rec in session.run(f"SHOW {label}"):
                    name = rec.get("name") or rec.get("constraintName") or rec.get("indexName")
                    if name:
                        names.add(name)
            except Exception:
                pass
    return names


def test_composite_claim_index_exists():
    """v2_task_claim_composite index present."""
    driver = get_driver()
    try:
        names = _get_schema_names(driver)
        assert 'v2_task_claim_composite' in names, \
            f"v2_task_claim_composite not found in {names}"
    finally:
        close_driver()


def test_composite_orphan_index_exists():
    """v2_task_orphan_composite index present."""
    driver = get_driver()
    try:
        names = _get_schema_names(driver)
        assert 'v2_task_orphan_composite' in names, \
            f"v2_task_orphan_composite not found in {names}"
    finally:
        close_driver()


def test_deprecated_priority_index_gone():
    """v2_task_priority index removed."""
    driver = get_driver()
    try:
        names = _get_schema_names(driver)
        assert 'v2_task_priority' not in names, \
            "v2_task_priority should have been dropped"
    finally:
        close_driver()


def test_deprecated_claim_epoch_index_gone():
    """v2_task_claim_epoch index removed."""
    driver = get_driver()
    try:
        names = _get_schema_names(driver)
        assert 'v2_task_claim_epoch' not in names, \
            "v2_task_claim_epoch should have been dropped"
    finally:
        close_driver()


def test_dead_skill_constraint_gone():
    """skill_name_unique constraint removed."""
    driver = get_driver()
    try:
        names = _get_schema_names(driver)
        assert 'skill_name_unique' not in names, \
            "skill_name_unique should have been dropped"
    finally:
        close_driver()


def test_dead_domain_constraint_gone():
    """domain_name_unique constraint removed."""
    driver = get_driver()
    try:
        names = _get_schema_names(driver)
        assert 'domain_name_unique' not in names, \
            "domain_name_unique should have been dropped"
    finally:
        close_driver()


def test_task_id_unique_still_exists():
    """task_id_unique constraint still exists."""
    driver = get_driver()
    try:
        names = _get_schema_names(driver)
        assert 'task_id_unique' in names, "task_id_unique should still exist"
    finally:
        close_driver()


def test_agent_name_unique_still_exists():
    """agent_name_unique constraint still exists."""
    driver = get_driver()
    try:
        names = _get_schema_names(driver)
        assert 'agent_name_unique' in names, "agent_name_unique should still exist"
    finally:
        close_driver()


def test_status_agent_index_still_exists():
    """v2_task_status_agent index still exists."""
    driver = get_driver()
    try:
        names = _get_schema_names(driver)
        assert 'v2_task_status_agent' in names, "v2_task_status_agent should still exist"
    finally:
        close_driver()


def test_lease_index_still_exists():
    """v2_task_lease index still exists."""
    driver = get_driver()
    try:
        names = _get_schema_names(driver)
        assert 'v2_task_lease' in names, "v2_task_lease should still exist"
    finally:
        close_driver()


def test_skill_constraint_dropped():
    """Skill uniqueness constraint dropped (nodes may still exist as legacy data)."""
    driver = get_driver()
    try:
        names = _get_schema_names(driver)
        assert 'skill_name_unique' not in names, \
            "skill_name_unique constraint should have been dropped"
    finally:
        close_driver()


def test_domain_constraint_dropped():
    """Domain uniqueness constraint dropped (nodes may still exist as legacy data)."""
    driver = get_driver()
    try:
        names = _get_schema_names(driver)
        assert 'domain_name_unique' not in names, \
            "domain_name_unique constraint should have been dropped"
    finally:
        close_driver()


def test_apply_schema_idempotent():
    """Running apply_schema() twice produces identical state."""
    driver = get_driver()
    try:
        apply_schema(driver, verbose=False)
        names1 = _get_schema_names(driver)
        apply_schema(driver, verbose=False)
        names2 = _get_schema_names(driver)
        assert names1 == names2, f"Schema changed between runs: {names1.symmetric_difference(names2)}"
    finally:
        close_driver()


def test_verify_schema_passes():
    """verify_schema() returns True after apply."""
    driver = get_driver()
    try:
        apply_schema(driver, verbose=False)
        ok = verify_schema(driver, verbose=False)
        assert ok, "verify_schema should return True"
    finally:
        close_driver()


if __name__ == '__main__':
    # Ensure schema is applied first
    driver = get_driver()
    apply_schema(driver, verbose=False)
    close_driver()

    tests = [
        test_composite_claim_index_exists,
        test_composite_orphan_index_exists,
        test_deprecated_priority_index_gone,
        test_deprecated_claim_epoch_index_gone,
        test_dead_skill_constraint_gone,
        test_dead_domain_constraint_gone,
        test_task_id_unique_still_exists,
        test_agent_name_unique_still_exists,
        test_status_agent_index_still_exists,
        test_lease_index_still_exists,
        test_skill_constraint_dropped,
        test_domain_constraint_dropped,
        test_apply_schema_idempotent,
        test_verify_schema_passes,
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
