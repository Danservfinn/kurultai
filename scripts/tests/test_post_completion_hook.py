#!/usr/bin/env python3
"""Unit tests for post_completion_hook.parse_followups()."""

import sys
from pathlib import Path

# Add scripts dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from post_completion_hook import parse_followups, FollowUpDeclaration

# ---------------------------------------------------------------------------
# Fixtures / sample data
# ---------------------------------------------------------------------------

SAMPLE_OUTPUT = """\
## Resolution

Did the thing.

```yaml
follow_ups:
  - title: "Research caching strategy"
    agent: mongke
    priority: normal
    context: "The API is slow, caching layer needed."
  - title: "Implement Redis cache"
    agent: temujin
    priority: high
    skill_hint: /horde-implement
    context: "After mongke's research, build the cache."
```
"""

SINGLE_FOLLOWUP = """\
```yaml
follow_ups:
  - title: "Add auth regression tests"
    agent: jochi
    priority: normal
    skill_hint: /generate-tests
    context: |
      Auth bug was in token refresh. Tests should cover refresh edge cases.
```
"""

# ---------------------------------------------------------------------------
# Basic parsing
# ---------------------------------------------------------------------------

def test_parse_followups_basic():
    result = parse_followups(SAMPLE_OUTPUT)
    assert len(result) == 2
    assert result[0].title == "Research caching strategy"
    assert result[0].agent == "mongke"
    assert result[0].priority == "normal"
    assert result[1].title == "Implement Redis cache"
    assert result[1].agent == "temujin"
    assert result[1].priority == "high"
    assert result[1].skill_hint == "/horde-implement"


def test_parse_followups_skill_hint():
    result = parse_followups(SINGLE_FOLLOWUP)
    assert len(result) == 1
    assert result[0].skill_hint == "/generate-tests"
    assert result[0].agent == "jochi"


def test_parse_followups_context_preserved():
    result = parse_followups(SINGLE_FOLLOWUP)
    assert "token refresh" in result[0].context


# ---------------------------------------------------------------------------
# Empty / no-match cases
# ---------------------------------------------------------------------------

def test_parse_followups_empty_string():
    assert parse_followups("") == []


def test_parse_followups_no_yaml_blocks():
    assert parse_followups("No follow ups here, just plain text.") == []


def test_parse_followups_yaml_block_no_follow_ups_key():
    content = '```yaml\nsome_other_key:\n  - value: 1\n```'
    assert parse_followups(content) == []


def test_parse_followups_empty_follow_ups_list():
    content = '```yaml\nfollow_ups: []\n```'
    assert parse_followups(content) == []


# ---------------------------------------------------------------------------
# Validation — invalid / missing fields
# ---------------------------------------------------------------------------

def test_parse_followups_invalid_agent():
    content = '```yaml\nfollow_ups:\n  - title: "Do something"\n    agent: batman\n```'
    assert parse_followups(content) == []


def test_parse_followups_missing_title():
    content = '```yaml\nfollow_ups:\n  - agent: temujin\n    priority: normal\n```'
    assert parse_followups(content) == []


def test_parse_followups_missing_both_required_fields():
    content = '```yaml\nfollow_ups:\n  - priority: high\n    skill_hint: /foo\n```'
    assert parse_followups(content) == []


def test_parse_followups_agent_case_insensitive():
    content = '```yaml\nfollow_ups:\n  - title: "Case test"\n    agent: TEMUJIN\n```'
    result = parse_followups(content)
    assert len(result) == 1
    assert result[0].agent == "temujin"


def test_parse_followups_invalid_priority_normalizes():
    content = '```yaml\nfollow_ups:\n  - title: "Prio test"\n    agent: jochi\n    priority: superurgent\n```'
    result = parse_followups(content)
    assert len(result) == 1
    assert result[0].priority == "normal"


def test_parse_followups_valid_priorities():
    for priority in ("critical", "high", "normal", "low"):
        content = f'```yaml\nfollow_ups:\n  - title: "Test"\n    agent: mongke\n    priority: {priority}\n```'
        result = parse_followups(content)
        assert result[0].priority == priority


# ---------------------------------------------------------------------------
# Cap at MAX_FOLLOWUPS = 5
# ---------------------------------------------------------------------------

def test_parse_followups_caps_at_5():
    items = "\n".join(
        f'  - title: "Task {i}"\n    agent: temujin' for i in range(10)
    )
    content = f'```yaml\nfollow_ups:\n{items}\n```'
    result = parse_followups(content)
    assert len(result) == 5


def test_parse_followups_exactly_5_is_allowed():
    items = "\n".join(
        f'  - title: "Task {i}"\n    agent: jochi' for i in range(5)
    )
    content = f'```yaml\nfollow_ups:\n{items}\n```'
    result = parse_followups(content)
    assert len(result) == 5


# ---------------------------------------------------------------------------
# Multiple YAML blocks
# ---------------------------------------------------------------------------

def test_parse_followups_multiple_blocks():
    """Follow-ups from multiple yaml blocks are merged."""
    content = """\
```yaml
follow_ups:
  - title: "Task A"
    agent: temujin
```

Some text in between.

```yaml
follow_ups:
  - title: "Task B"
    agent: mongke
```
"""
    result = parse_followups(content)
    assert len(result) == 2
    assert result[0].title == "Task A"
    assert result[1].title == "Task B"


def test_parse_followups_mixed_valid_invalid_blocks():
    """Valid follow-up in second block is still parsed even if first is invalid."""
    content = """\
```yaml
some_other_key: value
```

```yaml
follow_ups:
  - title: "Valid task"
    agent: chagatai
```
"""
    result = parse_followups(content)
    assert len(result) == 1
    assert result[0].title == "Valid task"


# ---------------------------------------------------------------------------
# Error resilience
# ---------------------------------------------------------------------------

def test_parse_followups_malformed_yaml_does_not_raise():
    content = '```yaml\nfollow_ups:\n  - title: "x"\n    agent: [unclosed\n```'
    # Should not raise, just return empty
    result = parse_followups(content)
    assert isinstance(result, list)


def test_parse_followups_non_dict_items_skipped():
    content = '```yaml\nfollow_ups:\n  - "just a string"\n  - title: "real task"\n    agent: jochi\n```'
    result = parse_followups(content)
    assert len(result) == 1
    assert result[0].title == "real task"


# ---------------------------------------------------------------------------
# All valid agents
# ---------------------------------------------------------------------------

def test_parse_followups_all_valid_agents():
    for agent in ("temujin", "mongke", "chagatai", "jochi", "ogedei"):
        content = f'```yaml\nfollow_ups:\n  - title: "Test for {agent}"\n    agent: {agent}\n```'
        result = parse_followups(content)
        assert len(result) == 1, f"Expected 1 result for agent={agent}"
        assert result[0].agent == agent


def test_parse_followups_kublai_not_valid_agent():
    """kublai is not a valid target agent for follow-ups."""
    content = '```yaml\nfollow_ups:\n  - title: "Route to kublai"\n    agent: kublai\n```'
    assert parse_followups(content) == []


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------

def test_parse_followups_default_priority():
    content = '```yaml\nfollow_ups:\n  - title: "No priority set"\n    agent: temujin\n```'
    result = parse_followups(content)
    assert result[0].priority == "normal"


def test_parse_followups_default_skill_hint_empty():
    content = '```yaml\nfollow_ups:\n  - title: "No hint"\n    agent: temujin\n```'
    result = parse_followups(content)
    assert result[0].skill_hint == ""


def test_parse_followups_default_context_empty():
    content = '```yaml\nfollow_ups:\n  - title: "No context"\n    agent: temujin\n```'
    result = parse_followups(content)
    assert result[0].context == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
