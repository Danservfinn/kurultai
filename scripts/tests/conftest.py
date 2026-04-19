"""Pytest shared conftest for the hermes scripts test suite.

Loads the hermes_test_isolation plugin when HERMES_TEST_ISOLATED=1 is
set in the environment, so baseline/post-apply test runs invoked by
hermes_fix_engine cannot contact prod Signal/Neo4j.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make sibling modules importable as usual for test discovery
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if os.environ.get("HERMES_TEST_ISOLATED") == "1":
    pytest_plugins = ["tests.hermes_test_isolation"]
