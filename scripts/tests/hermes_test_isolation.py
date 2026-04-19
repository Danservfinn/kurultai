"""Pytest plugin: hermes test isolation.

When HERMES_TEST_ISOLATED=1 is set in the environment (which the fix
engine sets before invoking baseline/post-apply test subprocesses),
this plugin stubs out the production Signal + Neo4j + notification
queue so tests cannot accidentally pollute them.

Tests that want these mocks also during regular dev runs can enable
them by setting HERMES_TEST_ISOLATED=1 in the shell. Otherwise tests
run with the unmocked imports (existing _isolate_neo4j fixture in
individual test files still applies per-test).
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock


def pytest_configure(config):
    """Install stubs before test collection begins."""
    if os.environ.get("HERMES_TEST_ISOLATED") != "1":
        return

    stubs = {
        "neo4j_v2_core": MagicMock(),
        "notification_queue": MagicMock(),
        "neo4j_task_tracker": MagicMock(),
    }
    for name, mock in stubs.items():
        sys.modules[name] = mock

    # signal_send.send is a function, not a module — stub it to a no-op.
    if "signal_send" in sys.modules:
        sys.modules["signal_send"].send = lambda *a, **kw: (0, {"dry": True})
    else:
        fake = MagicMock()
        fake.send = lambda *a, **kw: (0, {"dry": True})
        sys.modules["signal_send"] = fake
