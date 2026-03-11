#!/bin/bash
# Regression test runner for task state filename detection bug
# Run this to verify no regressions in the filename detection patterns

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../.."

echo "=========================================="
echo "Running Filename Detection Regression Tests"
echo "=========================================="
echo ""

python3 tests/test_filename_detection.py

exit $?
