#!/usr/bin/env python3
"""
Smoke test for post_completion_hook — validates parse + horde-prompt round trip.

Usage:
    cd /Users/kublai/.openclaw/agents/main/scripts/tests
    python3 smoke_post_completion_hook.py

Expected output:
    Parsed follow-up: 'Add auth regression tests' → jochi
    === Generated body (N chars) ===
    ...
    ✅ Smoke test passed
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from post_completion_hook import parse_followups, invoke_horde_prompt

SAMPLE = """\
## Resolution
Fixed the authentication bug in the login flow.

```yaml
follow_ups:
  - title: "Add auth regression tests"
    agent: jochi
    priority: normal
    skill_hint: /generate-tests
    context: |
      Auth bug was in token refresh logic. Need tests covering:
      - Expired token refresh
      - Concurrent refresh requests
      - Refresh during active session
```
"""


async def smoke():
    # Phase 1: parse
    followups = parse_followups(SAMPLE)
    assert len(followups) == 1, f"Expected 1 followup, got {len(followups)}"
    fu = followups[0]
    assert fu.title == "Add auth regression tests", f"Wrong title: {fu.title!r}"
    assert fu.agent == "jochi", f"Wrong agent: {fu.agent!r}"
    assert fu.priority == "normal", f"Wrong priority: {fu.priority!r}"
    assert fu.skill_hint == "/generate-tests", f"Wrong skill_hint: {fu.skill_hint!r}"
    print(f"Parsed follow-up: {fu.title!r} → {fu.agent}")

    # Phase 2: generate body via horde-prompt
    body = await invoke_horde_prompt(fu, "parent-task-abc123", "Fix authentication bug in login flow")
    assert len(body) >= 50, f"Body too short: {len(body)} chars"
    print(f"\n=== Generated body ({len(body)} chars) ===")
    print(body[:400])
    if len(body) > 400:
        print("... [truncated]")

    print("\n✅ Smoke test passed")


if __name__ == "__main__":
    asyncio.run(smoke())
