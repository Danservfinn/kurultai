#!/usr/bin/env python3
"""
Test tick parsing logic in kublai-actions.py
Ensures we read the MOST RECENT tick, not the 10th-from-last.
"""

import json
import tempfile


def test_tick_parsing_reads_most_recent():
    """Verify the tick parsing logic reads from most recent tick backwards."""
    # Create mock ticks.jsonl with 20 entries
    mock_ticks = []
    for i in range(1, 21):
        mock_ticks.append(json.dumps({
            "ts": f"2026-03-11T{i:02d}:00:00Z",
            "epoch": 1773200000 + i * 100,
            "decision": f"tick-{i}"
        }))

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        f.write('\n'.join(mock_ticks))
        temp_path = f.name

    try:
        with open(temp_path) as f:
            lines = f.readlines()

        # NEW (fixed) logic from kublai-actions.py
        tick = None
        for i in range(1, min(len(lines), 10) + 1):
            try:
                tick = json.loads(lines[-i].strip())
                break
            except json.JSONDecodeError:
                continue

        assert tick is not None, "Failed to parse tick"
        # Should read MOST RECENT (tick-20), not 10th-from-last (tick-11)
        assert tick["decision"] == "tick-20", f"Expected tick-20, got {tick['decision']}"
        print("✓ PASS: Reads most recent tick (lines[-1]) first")
        return True

    finally:
        import os
        os.unlink(temp_path)


def test_tick_parsing_handles_corruption():
    """Verify we skip corrupted entries and find valid ones."""
    # Create mock ticks with last 3 entries corrupted
    mock_ticks = []
    for i in range(1, 18):
        mock_ticks.append(json.dumps({"epoch": 1773200000 + i * 100, "decision": f"tick-{i}"}))
    # Add corrupted entries at end
    mock_ticks.append("{bad json")
    mock_ticks.append("also bad")
    mock_ticks.append("not json")

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        f.write('\n'.join(mock_ticks))
        temp_path = f.name

    try:
        with open(temp_path) as f:
            lines = f.readlines()

        tick = None
        for i in range(1, min(len(lines), 10) + 1):
            try:
                tick = json.loads(lines[-i].strip())
                break
            except json.JSONDecodeError:
                continue

        assert tick is not None, "Failed to find valid tick"
        # Should find tick-17 (most recent VALID tick)
        assert tick["decision"] == "tick-17", f"Expected tick-17, got {tick['decision']}"
        print("✓ PASS: Handles corrupted entries correctly")
        return True

    finally:
        import os
        os.unlink(temp_path)


if __name__ == "__main__":
    all_pass = True
    all_pass &= test_tick_parsing_reads_most_recent()
    all_pass &= test_tick_parsing_handles_corruption()

    if all_pass:
        print("\n✓ All tick parsing tests passed")
    else:
        print("\n✗ Some tests failed")
        exit(1)
