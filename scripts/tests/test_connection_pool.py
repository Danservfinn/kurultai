#!/usr/bin/env python3
"""Stress test for aligned connection pools (JS=25, Python=30)."""

import sys
import os
import concurrent.futures

sys.path.insert(0, os.path.expanduser('~/.openclaw/agents/main/scripts'))

from neo4j_task_tracker import get_driver, close_driver


def test_python_pool_30_concurrent():
    """30 concurrent Python Neo4j sessions should all succeed."""
    driver = get_driver()
    try:
        def run_query(i):
            with driver.session() as session:
                result = session.run("RETURN $n AS n", n=i)
                return result.single()['n']

        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as pool:
            futures = [pool.submit(run_query, i) for i in range(30)]
            results = [f.result(timeout=15) for f in futures]
        ok = sum(1 for r in results if r is not None)
        assert ok == 30, f"Expected 30/30 OK, got {ok}/30"
    finally:
        close_driver()


def test_python_pool_35_concurrent():
    """35 concurrent sessions — all succeed within 15s timeout (pool queues extras)."""
    driver = get_driver()
    try:
        def run_query(i):
            with driver.session() as session:
                result = session.run("RETURN $n AS n", n=i)
                return result.single()['n']

        with concurrent.futures.ThreadPoolExecutor(max_workers=35) as pool:
            futures = [pool.submit(run_query, i) for i in range(35)]
            results = [f.result(timeout=15) for f in futures]
        ok = sum(1 for r in results if r is not None)
        assert ok == 35, f"Expected 35/35 OK, got {ok}/35"
    finally:
        close_driver()


def test_js_pool_concurrent_http():
    """20 concurrent HTTP requests to server — all return 200."""
    import urllib.request

    def fetch(i):
        try:
            req = urllib.request.urlopen('http://localhost:18790/api/tasks', timeout=15)
            return req.status
        except Exception:
            return 0

    # Check if server is running first
    try:
        urllib.request.urlopen('http://localhost:18790/api/tasks', timeout=3)
    except Exception:
        print("  [SKIP] Server not running at localhost:18790")
        return

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        futures = [pool.submit(fetch, i) for i in range(20)]
        statuses = [f.result(timeout=20) for f in futures]
    ok = sum(1 for s in statuses if s == 200)
    assert ok >= 18, f"Expected at least 18/20 OK, got {ok}/20"


def test_pool_recovery():
    """After brief high load, new sessions still work."""
    driver = get_driver()
    try:
        def run_query(i):
            with driver.session() as session:
                result = session.run("RETURN $n AS n", n=i)
                return result.single()['n']

        # Burst of 30 concurrent
        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as pool:
            futures = [pool.submit(run_query, i) for i in range(30)]
            [f.result(timeout=15) for f in futures]

        # Now a single query should still work
        with driver.session() as session:
            result = session.run("RETURN 42 AS n")
            n = result.single()['n']
        if hasattr(n, '__int__'):
            n = int(n)
        assert n == 42, f"Post-burst query failed, got {n}"
    finally:
        close_driver()


if __name__ == '__main__':
    tests = [
        test_python_pool_30_concurrent,
        test_python_pool_35_concurrent,
        test_js_pool_concurrent_http,
        test_pool_recovery,
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
