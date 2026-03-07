#!/usr/bin/env python3
"""
Tests for @mention direct routing in task_intake.

Run:
    python3 test_mention_routing.py
    python3 -m pytest test_mention_routing.py -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from task_intake import parse_mention, VALID_AGENTS


class TestParseMention(unittest.TestCase):
    """Test the @mention parser."""

    def test_basic_mentions(self):
        """@agent at start routes to correct agent."""
        cases = [
            ("@temujin The kanban board needs dark mode", "temujin", "The kanban board needs dark mode"),
            ("@mongke research competitor X", "mongke", "research competitor X"),
            ("@chagatai write a blog post", "chagatai", "write a blog post"),
            ("@jochi audit the auth module", "jochi", "audit the auth module"),
            ("@ogedei check service health", "ogedei", "check service health"),
            ("@kublai coordinate the sprint", "kublai", "coordinate the sprint"),
            ("@tolui verify this task is actually done", "tolui", "verify this task is actually done"),
        ]
        for text, expected_agent, expected_body in cases:
            agent, stripped = parse_mention(text)
            self.assertEqual(agent, expected_agent, f"parse_mention('{text}') agent")
            self.assertEqual(stripped, expected_body, f"parse_mention('{text}') body")

    def test_case_insensitive(self):
        """@AGENT and @Agent should work."""
        agent, stripped = parse_mention("@TEMUJIN fix the bug")
        self.assertEqual(agent, "temujin")
        self.assertEqual(stripped, "fix the bug")

        agent, stripped = parse_mention("@Mongke research this")
        self.assertEqual(agent, "mongke")

    def test_no_mention(self):
        """Messages without @mention return (None, original_text)."""
        text = "Fix the login bug"
        agent, stripped = parse_mention(text)
        self.assertIsNone(agent)
        self.assertEqual(stripped, text)

    def test_mention_mid_text(self):
        """@mention in middle of text should NOT match (only prefix)."""
        text = "Please ask @temujin to fix this"
        agent, stripped = parse_mention(text)
        self.assertIsNone(agent)
        self.assertEqual(stripped, text)

    def test_invalid_agent(self):
        """@invalid_name should not match."""
        text = "@nobody do something"
        agent, stripped = parse_mention(text)
        self.assertIsNone(agent)
        self.assertEqual(stripped, text)

    def test_mention_only(self):
        """@agent with no message body returns empty string."""
        agent, stripped = parse_mention("@temujin")
        self.assertEqual(agent, "temujin")
        self.assertEqual(stripped, "")

    def test_mention_extra_whitespace(self):
        """@agent followed by extra spaces still strips cleanly."""
        agent, stripped = parse_mention("@temujin   lots of spaces here")
        self.assertEqual(agent, "temujin")
        self.assertEqual(stripped, "lots of spaces here")

    def test_all_valid_agents_recognized(self):
        """Every agent in VALID_AGENTS is parseable."""
        for name in VALID_AGENTS:
            agent, _ = parse_mention(f"@{name} test")
            self.assertEqual(agent, name, f"@{name} not recognized")


class TestMentionInCreateTask(unittest.TestCase):
    """Test that @mention integrates with create_task routing."""

    def test_mention_skips_keyword_routing(self):
        """@mention should bypass keyword routing entirely."""
        # "@mongke implement a feature" should go to mongke, not temujin
        # (even though "implement" is a temujin keyword)
        from task_intake import parse_mention
        agent, stripped = parse_mention("@mongke implement a feature")
        self.assertEqual(agent, "mongke")
        self.assertEqual(stripped, "implement a feature")


if __name__ == "__main__":
    unittest.main()
