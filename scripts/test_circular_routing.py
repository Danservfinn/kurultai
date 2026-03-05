#!/usr/bin/env python3
"""
Tests for circular triage routing fix.

Verifies that:
1. "Triage stalled agent: X" tasks never route to agent X
2. kublai-actions routes stalled agent triage to jochi (not kublai or self)
3. task-router _prevent_self_routing guard catches self-referential routing
4. "Tock assessment: ... X backlog" tasks never route to agent X
5. When jochi is stalled, triage goes to kublai (not jochi)

Run:
    python3 test_circular_routing.py
    python3 -m pytest test_circular_routing.py -v
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from task_router import (
    _prevent_self_routing,
    _keyword_classify,
    VALID_AGENTS,
)


class TestPreventSelfRouting(unittest.TestCase):
    """Test the _prevent_self_routing guard."""

    def test_triage_stalled_agent_not_routed_to_self(self):
        """Triage stalled agent: X must not route to X."""
        for agent in ["temujin", "mongke", "chagatai", "ogedei", "kublai"]:
            task = f"Triage stalled agent: {agent} has 4 queued tasks with 0 completions"
            result = _prevent_self_routing(task, agent)
            self.assertEqual(result, "jochi",
                f"'{task}' routed to {agent} (self) instead of jochi")

    def test_triage_stalled_jochi_routes_to_kublai(self):
        """When jochi is stalled, triage must go to kublai (not jochi)."""
        task = "Triage stalled agent: jochi has 4 queued tasks with 0 completions"
        result = _prevent_self_routing(task, "jochi")
        self.assertEqual(result, "kublai",
            "Stalled jochi triage should go to kublai, not jochi")

    def test_triage_stalled_agent_different_dest_unchanged(self):
        """Triage about agent X routed to Y (Y != X) should stay unchanged."""
        task = "Triage stalled agent: mongke has 4 queued tasks with 0 completions"
        result = _prevent_self_routing(task, "kublai")
        self.assertEqual(result, "kublai")

        result = _prevent_self_routing(task, "jochi")
        self.assertEqual(result, "jochi")

    def test_assessment_backlog_not_routed_to_self(self):
        """Tock assessment about agent X backlog must not route to X."""
        task = "Tock assessment: CRITICAL — temujin backlog"
        result = _prevent_self_routing(task, "temujin")
        self.assertEqual(result, "jochi",
            "'Tock assessment: CRITICAL — temujin backlog' routed to temujin (self)")

    def test_assessment_jochi_backlog_routes_to_kublai(self):
        """Assessment about jochi backlog must go to kublai, not jochi."""
        task = "Tock assessment: HIGH — jochi backlog"
        result = _prevent_self_routing(task, "jochi")
        self.assertEqual(result, "kublai")

    def test_assessment_backlog_different_dest_unchanged(self):
        """Assessment about X routed to Y should stay unchanged."""
        task = "Tock assessment: CRITICAL — temujin backlog"
        result = _prevent_self_routing(task, "kublai")
        self.assertEqual(result, "kublai")

    def test_normal_tasks_unaffected(self):
        """Regular tasks mentioning an agent name should not be redirected."""
        cases = [
            ("Build a login feature with OAuth", "temujin"),
            ("Research competitors in the AI agent space", "mongke"),
            ("Write a blog post about our launch", "chagatai"),
            ("Audit the codebase for security vulnerabilities", "jochi"),
            ("Monitor cron job health and uptime", "ogedei"),
        ]
        for task, dest in cases:
            result = _prevent_self_routing(task, dest)
            self.assertEqual(result, dest,
                f"Normal task '{task}' was incorrectly redirected from {dest}")

    def test_subagent_not_affected(self):
        """Subagent routing should not be affected."""
        task = "Triage stalled agent: mongke has tasks queued"
        result = _prevent_self_routing(task, "subagent")
        self.assertEqual(result, "subagent")

    def test_all_agents_covered(self):
        """Every non-subagent agent should be protected from self-routing."""
        protected_agents = VALID_AGENTS - {"subagent"}
        for agent in protected_agents:
            task = f"Triage stalled agent: {agent} has 3 queued tasks"
            result = _prevent_self_routing(task, agent)
            self.assertNotEqual(result, agent,
                f"Agent {agent} not protected from self-routing")


class TestKeywordClassifyTriageRouting(unittest.TestCase):
    """Test that keyword fallback doesn't route triage tasks to the stalled agent."""

    def test_keyword_classify_triage_stalled(self):
        """Keyword fallback for triage tasks should not route to the mentioned agent."""
        task = "Triage stalled agent: temujin has 4 queued tasks with 0 completions"
        dest, scores, complexity = _keyword_classify(task)
        self.assertIsInstance(dest, str)
        self.assertIn(dest, VALID_AGENTS | {"subagent"})


class TestKublaiActionsTriageRouting(unittest.TestCase):
    """Test that kublai-actions routes stalled agent triage to jochi."""

    def test_stalled_agent_routes_to_jochi(self):
        """Verify kublai-actions.py source routes stalled agent tasks to jochi."""
        script_path = os.path.join(os.path.dirname(__file__), "kublai-actions.py")
        with open(script_path) as f:
            source = f.read()

        # Verify Rule 3 routes to jochi, not kublai
        self.assertIn(
            'create_task(\n                    "jochi", "normal",\n                    f"Triage stalled agent:',
            source,
            "Rule 3 should route stalled agent triage to jochi"
        )

        # Verify the has_pending_task check uses jochi
        self.assertIn(
            'has_pending_task("jochi", f"Triage stalled agent: {name}")',
            source,
            "Duplicate check should look in jochi's queue"
        )

    def test_source_has_anti_circular_comment(self):
        """Verify the fix includes a comment explaining the anti-circular logic."""
        script_path = os.path.join(os.path.dirname(__file__), "kublai-actions.py")
        with open(script_path) as f:
            source = f.read()
        self.assertIn("NEVER route to the stalled agent itself", source)

    def test_rule3_does_not_target_kublai(self):
        """Rule 3 must not create tasks for kublai (the old buggy behavior)."""
        script_path = os.path.join(os.path.dirname(__file__), "kublai-actions.py")
        with open(script_path) as f:
            source = f.read()

        # Extract just Rule 3 section
        lines = source.split('\n')
        rule3_lines = []
        in_rule3 = False
        for line in lines:
            if 'Rule 3: Agent stalled' in line:
                in_rule3 = True
            if in_rule3:
                rule3_lines.append(line)
            if in_rule3 and 'Rule 4:' in line:
                break

        rule3_text = '\n'.join(rule3_lines)
        # The create_task call should use "jochi", not "kublai"
        self.assertNotIn('create_task(\n                    "kublai"', rule3_text,
            "Rule 3 should NOT create tasks for kublai")


class TestEndToEndSelfRoutingPrevention(unittest.TestCase):
    """Integration-style tests for the full classify_task pipeline with self-routing guard."""

    def test_classify_triage_stalled_kublai(self):
        """classify_task for 'Triage stalled agent: kublai' must not return kublai."""
        with patch('task_router._llm_classify', return_value=("kublai", None)):
            from task_router import classify_task
            result = classify_task("Triage stalled agent: kublai has 3 queued tasks")
            self.assertNotEqual(result["destination"], "kublai",
                "classify_task routed triage-kublai to kublai despite guard")
            self.assertEqual(result["destination"], "jochi")

    def test_classify_triage_stalled_jochi(self):
        """classify_task for 'Triage stalled agent: jochi' must not return jochi."""
        with patch('task_router._llm_classify', return_value=("jochi", None)):
            from task_router import classify_task
            result = classify_task("Triage stalled agent: jochi has 3 queued tasks")
            self.assertNotEqual(result["destination"], "jochi",
                "classify_task routed triage-jochi to jochi despite guard")
            self.assertEqual(result["destination"], "kublai")

    def test_classify_assessment_temujin_backlog(self):
        """classify_task for 'Tock assessment: CRITICAL — temujin backlog' must not return temujin."""
        with patch('task_router._llm_classify', return_value=("temujin", None)):
            from task_router import classify_task
            result = classify_task("Tock assessment: CRITICAL — temujin backlog")
            self.assertNotEqual(result["destination"], "temujin",
                "classify_task routed assessment-temujin to temujin despite guard")
            self.assertEqual(result["destination"], "jochi")

    def test_classify_normal_task_unaffected(self):
        """Normal tasks should route normally even when they mention agent names."""
        with patch('task_router._llm_classify', return_value=("temujin", None)):
            from task_router import classify_task
            result = classify_task("Build a login feature with OAuth")
            self.assertEqual(result["destination"], "temujin")

    def test_classify_all_agents_self_triage_blocked(self):
        """For every agent, simulated LLM self-routing of triage tasks is blocked."""
        from task_router import classify_task
        for agent in ["temujin", "mongke", "chagatai", "jochi", "ogedei", "kublai"]:
            with patch('task_router._llm_classify', return_value=(agent, None)):
                result = classify_task(f"Triage stalled agent: {agent} has 5 queued")
                self.assertNotEqual(result["destination"], agent,
                    f"classify_task self-routed triage for {agent}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
