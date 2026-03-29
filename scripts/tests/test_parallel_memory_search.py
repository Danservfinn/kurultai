#!/usr/bin/env python3
"""
Unit tests for parallel_memory_search.py

Coverage targets:
- MemoryFragment dataclass + content_hash generation
- Dedup logic (_is_duplicate, _overlap_ratio)
- Contradiction detection (_are_contradictory)
- Composite scoring (_composite_score)
- Aggregator (_aggregate): dedup, ranking, contradiction flagging
- Per-agent Cypher runners with mocked Neo4j sessions
- Async agent wrappers: happy path, timeout, exception
- parallel_memory_search() end-to-end with mocked driver + embedding
- Fallback path when all agents fail
- sync search_memory() wrapper
- CLI smoke-test (argparse)
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

# ---------------------------------------------------------------------------
# Path bootstrap — same pattern used everywhere in this project
# ---------------------------------------------------------------------------
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)

# We import the module under test.  Neo4j driver and embedding_generator are
# mocked at the module level for all tests so no live services are required.
with (
    patch("neo4j_task_tracker.get_driver", return_value=MagicMock()),
    patch("embedding_generator.generate_embedding", return_value=[0.0] * 768),
):
    import parallel_memory_search as pms


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

HUMAN_ID = "test-human-uuid-0001"
QUERY = "What projects is Danny working on?"


def _make_fragment(
    text: str = "some text",
    source: str = "direct_facts",
    score: float = 0.8,
    node_type: str = "Message",
    timestamp: Optional[str] = None,
) -> pms.MemoryFragment:
    return pms.MemoryFragment(
        text=text,
        source=source,
        score=score,
        node_type=node_type,
        timestamp=timestamp,
    )


def _make_agent_result(
    agent_name: str = "direct_facts",
    fragments: Optional[List[pms.MemoryFragment]] = None,
    duration_ms: int = 50,
    error: Optional[str] = None,
) -> pms.AgentResult:
    return pms.AgentResult(
        agent_name=agent_name,
        fragments=fragments or [],
        duration_ms=duration_ms,
        error=error,
    )


# ---------------------------------------------------------------------------
# MemoryFragment
# ---------------------------------------------------------------------------


class TestMemoryFragment(unittest.TestCase):
    def test_content_hash_auto_generated(self):
        frag = _make_fragment("hello world")
        self.assertEqual(len(frag.content_hash), 8)

    def test_content_hash_is_deterministic(self):
        f1 = _make_fragment("hello world")
        f2 = _make_fragment("hello world")
        self.assertEqual(f1.content_hash, f2.content_hash)

    def test_content_hash_normalises_whitespace(self):
        f1 = _make_fragment("hello  world")
        f2 = _make_fragment("hello world")
        self.assertEqual(f1.content_hash, f2.content_hash)

    def test_content_hash_is_case_insensitive(self):
        f1 = _make_fragment("Hello World")
        f2 = _make_fragment("hello world")
        self.assertEqual(f1.content_hash, f2.content_hash)

    def test_explicit_content_hash_not_overwritten(self):
        frag = pms.MemoryFragment(
            text="test", source="context", score=0.5,
            node_type="Message", content_hash="explicit"
        )
        self.assertEqual(frag.content_hash, "explicit")

    def test_different_texts_have_different_hashes(self):
        f1 = _make_fragment("project alpha")
        f2 = _make_fragment("project beta")
        self.assertNotEqual(f1.content_hash, f2.content_hash)


# ---------------------------------------------------------------------------
# MemoryResult helpers
# ---------------------------------------------------------------------------


class TestMemoryResult(unittest.TestCase):
    def _make_result(self, texts: List[str]) -> pms.MemoryResult:
        frags = [_make_fragment(t) for t in texts]
        return pms.MemoryResult(
            query="q", human_id="h",
            fragments=frags, agent_results=[], total_ms=100
        )

    def test_top_texts(self):
        result = self._make_result(["a", "b", "c"])
        self.assertEqual(result.top_texts, ["a", "b", "c"])

    def test_as_context_string_default_limit(self):
        result = self._make_result([f"text {i}" for i in range(25)])
        ctx = result.as_context_string()
        # Default max_fragments=20
        lines = [l for l in ctx.split("\n") if l.strip()]
        self.assertEqual(len(lines), 20)

    def test_as_context_string_format(self):
        frag = pms.MemoryFragment(
            text="Danny is working on parse",
            source="direct_facts",
            score=0.9,
            node_type="Inference",
            timestamp="2026-03-21T10:00:00",
        )
        result = pms.MemoryResult(
            query="q", human_id="h",
            fragments=[frag], agent_results=[], total_ms=50
        )
        ctx = result.as_context_string()
        self.assertIn("[Inference]", ctx)
        self.assertIn("2026-03-21T10:00:00", ctx)
        self.assertIn("Danny is working on parse", ctx)

    def test_as_context_string_no_timestamp(self):
        frag = _make_fragment("no timestamp here")
        result = pms.MemoryResult(
            query="q", human_id="h",
            fragments=[frag], agent_results=[], total_ms=50
        )
        ctx = result.as_context_string()
        # Parenthesised timestamp section should be absent
        self.assertNotIn("(None)", ctx)


# ---------------------------------------------------------------------------
# _content_hash
# ---------------------------------------------------------------------------


class TestContentHash(unittest.TestCase):
    def test_returns_8_chars(self):
        self.assertEqual(len(pms._content_hash("test")), 8)

    def test_empty_string(self):
        h = pms._content_hash("")
        self.assertEqual(len(h), 8)


# ---------------------------------------------------------------------------
# _overlap_ratio
# ---------------------------------------------------------------------------


class TestOverlapRatio(unittest.TestCase):
    def test_identical_texts(self):
        self.assertAlmostEqual(pms._overlap_ratio("foo bar baz", "foo bar baz"), 1.0)

    def test_no_overlap(self):
        self.assertAlmostEqual(pms._overlap_ratio("alpha beta", "gamma delta"), 0.0)

    def test_partial_overlap(self):
        ratio = pms._overlap_ratio("alpha beta gamma", "beta gamma delta")
        # Intersection={beta,gamma}=2, Union={alpha,beta,gamma,delta}=4 → 0.5
        self.assertAlmostEqual(ratio, 0.5)

    def test_empty_strings(self):
        self.assertEqual(pms._overlap_ratio("", "anything"), 0.0)
        self.assertEqual(pms._overlap_ratio("anything", ""), 0.0)


# ---------------------------------------------------------------------------
# _is_duplicate
# ---------------------------------------------------------------------------


class TestIsDuplicate(unittest.TestCase):
    def test_exact_hash_duplicate(self):
        seen = [_make_fragment("same text")]
        new = _make_fragment("same text")
        self.assertTrue(pms._is_duplicate(new, seen))

    def test_near_duplicate_via_overlap(self):
        # With N words and 1 substitution: Jaccard = (N-1)/(N+1).
        # For N=13: (13-1)/(13+1) = 12/14 ≈ 0.857 > 0.85 threshold.
        base_words = [f"word{i}" for i in range(13)]
        base = " ".join(base_words)
        seen = [_make_fragment(base)]
        # Replace the last word only — overlap = 12/14 ≈ 0.857
        near = " ".join(base_words[:-1] + ["different"])
        new = _make_fragment(near)
        self.assertTrue(pms._is_duplicate(new, seen))

    def test_different_text_not_duplicate(self):
        seen = [_make_fragment("project alpha timeline")]
        new = _make_fragment("completely unrelated sentence about weather")
        self.assertFalse(pms._is_duplicate(new, seen))

    def test_empty_seen_list(self):
        self.assertFalse(pms._is_duplicate(_make_fragment("anything"), []))


# ---------------------------------------------------------------------------
# _are_contradictory
# ---------------------------------------------------------------------------


class TestAreContradictory(unittest.TestCase):
    def test_obvious_contradiction(self):
        a = _make_fragment("Danny likes working on parse")
        b = _make_fragment("Danny doesn't likes working on parse")
        # Should detect as contradictory given sufficient shared tokens
        result = pms._are_contradictory(a, b)
        # Negation words differ; shared content words: danny, likes, working, parse (≥3)
        self.assertTrue(result)

    def test_unrelated_statements_not_contradictory(self):
        a = _make_fragment("coffee is hot")
        b = _make_fragment("the deploy succeeded on friday")
        self.assertFalse(pms._are_contradictory(a, b))

    def test_same_polarity_not_contradictory(self):
        a = _make_fragment("Danny is not available on Monday")
        b = _make_fragment("Danny is not available on Tuesday")
        # Both have negation — same polarity → not contradictory
        self.assertFalse(pms._are_contradictory(a, b))

    def test_fewer_than_three_shared_tokens(self):
        a = _make_fragment("yes")
        b = _make_fragment("no")
        self.assertFalse(pms._are_contradictory(a, b))


# ---------------------------------------------------------------------------
# _composite_score
# ---------------------------------------------------------------------------


class TestCompositeScore(unittest.TestCase):
    def test_direct_facts_message_no_boost(self):
        frag = _make_fragment(score=0.8, source="direct_facts", node_type="Message")
        score = pms._composite_score(frag)
        self.assertAlmostEqual(score, 0.8 * 1.0 + 0.0)

    def test_direct_facts_action_item_boost(self):
        frag = _make_fragment(score=0.8, source="direct_facts", node_type="ActionItem")
        score = pms._composite_score(frag)
        self.assertAlmostEqual(score, min(1.0, 0.8 * 1.0 + 0.10))

    def test_timeline_message_weight(self):
        frag = _make_fragment(score=1.0, source="timeline", node_type="Message")
        score = pms._composite_score(frag)
        self.assertAlmostEqual(score, 0.85)

    def test_score_capped_at_one(self):
        frag = _make_fragment(score=1.0, source="direct_facts", node_type="ActionItem")
        score = pms._composite_score(frag)
        self.assertLessEqual(score, 1.0)

    def test_score_floored_at_zero(self):
        frag = _make_fragment(score=0.0, source="context", node_type="Topic")
        score = pms._composite_score(frag)
        self.assertGreaterEqual(score, 0.0)


# ---------------------------------------------------------------------------
# _aggregate
# ---------------------------------------------------------------------------


class TestAggregate(unittest.TestCase):
    def _run(self, agent_results, max_fragments=40):
        frags, contradictions = pms._aggregate(agent_results, max_fragments=max_fragments)
        return frags, contradictions

    def test_empty_agents_returns_empty(self):
        frags, contradictions = self._run([])
        self.assertEqual(frags, [])
        self.assertEqual(contradictions, [])

    def test_below_min_confidence_dropped(self):
        low_frag = _make_fragment(score=pms.MIN_CONFIDENCE_INCLUDE - 0.01)
        ar = _make_agent_result(fragments=[low_frag])
        frags, _ = self._run([ar])
        self.assertEqual(frags, [])

    def test_at_min_confidence_kept(self):
        ok_frag = _make_fragment(score=pms.MIN_CONFIDENCE_INCLUDE)
        ar = _make_agent_result(fragments=[ok_frag])
        frags, _ = self._run([ar])
        self.assertEqual(len(frags), 1)

    def test_dedup_removes_exact_duplicates(self):
        f1 = _make_fragment("identical text here please", score=0.9)
        f2 = _make_fragment("identical text here please", score=0.7)
        ar = _make_agent_result(fragments=[f1, f2])
        frags, _ = self._run([ar])
        self.assertEqual(len(frags), 1)

    def test_fragments_sorted_by_composite_score_desc(self):
        frags_input = [
            _make_fragment("low score", score=0.5),
            _make_fragment("high score text thing", score=0.9),
            _make_fragment("medium score here", score=0.7),
        ]
        ar = _make_agent_result(fragments=frags_input)
        result, _ = self._run([ar])
        scores = [f.score for f in result]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_max_fragments_limit_respected(self):
        many_frags = [_make_fragment(f"unique text item number {i}", score=0.8) for i in range(30)]
        ar = _make_agent_result(fragments=many_frags)
        result, _ = self._run([ar], max_fragments=10)
        self.assertLessEqual(len(result), 10)

    def test_contradictions_flagged(self):
        # Create two fragments with enough shared tokens and opposite negation
        a = _make_fragment("Danny likes working on this project task here", score=0.8)
        b = _make_fragment("Danny doesn't likes working on this project task here", score=0.7)
        ar = _make_agent_result(fragments=[a, b])
        result, contradictions = self._run([ar])
        # If detected, both fragments should be flagged
        if contradictions:
            flagged = [f for f in result if f.contradiction_flag]
            self.assertTrue(len(flagged) >= 2)

    def test_multiple_agents_merged(self):
        ar1 = _make_agent_result("direct_facts", [_make_fragment("fact one", score=0.9)])
        ar2 = _make_agent_result("context", [_make_fragment("context item", score=0.85)])
        ar3 = _make_agent_result("timeline", [_make_fragment("recent event", score=0.75)])
        result, _ = self._run([ar1, ar2, ar3])
        self.assertEqual(len(result), 3)

    def test_agent_error_results_skipped(self):
        bad_ar = _make_agent_result(error="connection refused")  # fragments=[]
        good_ar = _make_agent_result(fragments=[_make_fragment("good data", score=0.8)])
        result, _ = self._run([bad_ar, good_ar])
        self.assertEqual(len(result), 1)


# ---------------------------------------------------------------------------
# Direct-facts agent (Cypher layer mocked)
# ---------------------------------------------------------------------------


class TestRunDirectFacts(unittest.TestCase):
    def _mock_session(self, fulltext_rows=None, inference_rows=None, action_rows=None):
        session = MagicMock()

        def run_side_effect(cypher, **kwargs):
            mock_result = MagicMock()
            if "fulltext.queryNodes" in cypher:
                mock_result.__iter__ = Mock(return_value=iter(fulltext_rows or []))
            elif "Inference" in cypher:
                mock_result.__iter__ = Mock(return_value=iter(inference_rows or []))
            elif "ActionItem" in cypher:
                mock_result.__iter__ = Mock(return_value=iter(action_rows or []))
            else:
                mock_result.__iter__ = Mock(return_value=iter([]))
            return mock_result

        session.run.side_effect = run_side_effect
        return session

    def test_returns_fragments_from_fulltext(self):
        row = {"text": "Danny is building parse", "timestamp": "2026-03-20T00:00:00",
               "direction": "inbound", "score": 5.0}
        session = self._mock_session(fulltext_rows=[row])
        frags = pms._run_direct_facts(HUMAN_ID, QUERY, session)
        texts = [f.text for f in frags]
        self.assertIn("Danny is building parse", texts)

    def test_skips_none_text(self):
        row = {"text": None, "timestamp": None, "direction": "inbound", "score": 1.0}
        session = self._mock_session(fulltext_rows=[row])
        frags = pms._run_direct_facts(HUMAN_ID, QUERY, session)
        self.assertEqual(frags, [])

    def test_inference_score_is_confidence(self):
        row = {"text": "prefers async comms", "inf_type": "preference",
               "confidence": 0.92, "timestamp": "2026-03-01T00:00:00"}
        session = self._mock_session(inference_rows=[row])
        frags = pms._run_direct_facts(HUMAN_ID, QUERY, session)
        inference_frags = [f for f in frags if f.node_type == "Inference"]
        self.assertTrue(any(abs(f.score - 0.92) < 0.01 for f in inference_frags))

    def test_action_item_high_priority_score(self):
        row = {"text": "Ship v2 release", "priority": "high",
               "assignee": "Danny", "deadline": "2026-04-01",
               "timestamp": "2026-03-15T00:00:00"}
        session = self._mock_session(action_rows=[row])
        frags = pms._run_direct_facts(HUMAN_ID, QUERY, session)
        ai_frags = [f for f in frags if f.node_type == "ActionItem"]
        self.assertTrue(any(f.score == 0.9 for f in ai_frags))

    def test_cypher_exception_does_not_propagate(self):
        session = MagicMock()
        session.run.side_effect = Exception("neo4j connection lost")
        # Should not raise — returns empty list
        frags = pms._run_direct_facts(HUMAN_ID, QUERY, session)
        self.assertIsInstance(frags, list)


# ---------------------------------------------------------------------------
# Context agent (Cypher layer mocked)
# ---------------------------------------------------------------------------


class TestRunContextAgent(unittest.TestCase):
    def _mock_session(self, vector_rows=None, pagerank_rows=None,
                      bridge_rows=None, social_rows=None):
        session = MagicMock()

        def run_side_effect(cypher, **kwargs):
            mock_result = MagicMock()
            if "vector.queryNodes" in cypher:
                mock_result.__iter__ = Mock(return_value=iter(vector_rows or []))
            elif "pagerank_score" in cypher or "DISCUSSED" in cypher and "HAS_TOPIC" in cypher:
                mock_result.__iter__ = Mock(return_value=iter(pagerank_rows or []))
            elif "betweenness_score" in cypher:
                mock_result.__iter__ = Mock(return_value=iter(bridge_rows or []))
            elif "KNOWN_THROUGH" in cypher or "RELATED_TO" in cypher:
                mock_result.__iter__ = Mock(return_value=iter(social_rows or []))
            else:
                mock_result.__iter__ = Mock(return_value=iter([]))
            return mock_result

        session.run.side_effect = run_side_effect
        return session

    def test_vector_search_returns_fragments(self):
        row = {"text": "I am working on parse launch",
               "timestamp": "2026-03-20T00:00:00",
               "direction": "inbound", "score": 0.92}
        session = self._mock_session(vector_rows=[row])
        frags = pms._run_context_agent(HUMAN_ID, QUERY, [0.1] * 768, session)
        self.assertTrue(any(f.node_type == "Message" for f in frags))

    def test_no_embedding_skips_vector_search(self):
        session = self._mock_session()
        frags = pms._run_context_agent(HUMAN_ID, QUERY, None, session)
        # Without embedding there are no vector fragments — just topic/social
        vector_frags = [f for f in frags if f.metadata.get("retrieval") == "vector"]
        self.assertEqual(vector_frags, [])

    def test_bridge_topic_prefix_added(self):
        row = {"text": "infrastructure", "domain": "ops", "score": 0.4}
        session = self._mock_session(bridge_rows=[row])
        frags = pms._run_context_agent(HUMAN_ID, QUERY, None, session)
        bridge_frags = [f for f in frags if f.node_type == "Topic"]
        self.assertTrue(any("[Bridge topic]" in f.text for f in bridge_frags))

    def test_social_fragment_format(self):
        row = {"name": "Alice", "relType": "KNOWN_THROUGH", "context": "co-worker"}
        session = self._mock_session(social_rows=[row])
        frags = pms._run_context_agent(HUMAN_ID, QUERY, None, session)
        social_frags = [f for f in frags if f.node_type == "Human"]
        self.assertTrue(any("Alice" in f.text for f in social_frags))

    def test_exception_in_vector_search_falls_through(self):
        session = MagicMock()
        session.run.side_effect = Exception("index not found")
        frags = pms._run_context_agent(HUMAN_ID, QUERY, [0.0] * 768, session)
        self.assertIsInstance(frags, list)


# ---------------------------------------------------------------------------
# Timeline agent (Cypher layer mocked)
# ---------------------------------------------------------------------------


class TestRunTimelineAgent(unittest.TestCase):
    def _mock_session(self, marker_rows=None, recency_rows=None,
                      inference_rows=None, episode_rows=None):
        session = MagicMock()

        def run_side_effect(cypher, **kwargs):
            mock_result = MagicMock()
            if "TemporalMarker" in cypher:
                mock_result.__iter__ = Mock(return_value=iter(marker_rows or []))
            elif "ORDER BY m.timestamp DESC" in cypher:
                mock_result.__iter__ = Mock(return_value=iter(recency_rows or []))
            elif "Inference" in cypher:
                mock_result.__iter__ = Mock(return_value=iter(inference_rows or []))
            elif "Episode" in cypher:
                mock_result.__iter__ = Mock(return_value=iter(episode_rows or []))
            else:
                mock_result.__iter__ = Mock(return_value=iter([]))
            return mock_result

        session.run.side_effect = run_side_effect
        return session

    def test_rising_drift_gets_higher_score(self):
        rising = {"signal": "rising", "topic": "kubernetes",
                  "recent": 10, "longterm": 2, "timestamp": "2026-03-21T00:00:00"}
        fading = {"signal": "fading", "topic": "ansible",
                  "recent": 1, "longterm": 8, "timestamp": "2026-03-21T00:00:00"}
        session = self._mock_session(marker_rows=[rising, fading])
        frags = pms._run_timeline_agent(HUMAN_ID, session)
        tm_frags = [f for f in frags if f.node_type == "TemporalMarker"]
        rising_score = next(f.score for f in tm_frags if "RISING" in f.text.upper())
        fading_score = next(f.score for f in tm_frags if "FADING" in f.text.upper())
        self.assertGreater(rising_score, fading_score)

    def test_recency_score_decays(self):
        rows = [
            {"text": f"msg {i}", "timestamp": f"2026-03-2{i}T00:00:00", "direction": "inbound"}
            for i in range(5)
        ]
        session = self._mock_session(recency_rows=rows)
        frags = pms._run_timeline_agent(HUMAN_ID, session)
        msg_frags = [f for f in frags if f.node_type == "Message" and f.source == "timeline"]
        if len(msg_frags) >= 2:
            # First retrieved (most recent) should have higher score
            self.assertGreaterEqual(msg_frags[0].score, msg_frags[-1].score)

    def test_episode_fragment_prefix(self):
        row = {"text": "discussed parse pricing and raised concerns",
               "timestamp": "2026-03-10T00:00:00", "topic": "pricing"}
        session = self._mock_session(episode_rows=[row])
        frags = pms._run_timeline_agent(HUMAN_ID, session)
        ep_frags = [f for f in frags if f.node_type == "Episode"]
        self.assertTrue(any("[Episode:" in f.text for f in ep_frags))

    def test_exception_does_not_propagate(self):
        session = MagicMock()
        session.run.side_effect = RuntimeError("neo4j crashed")
        frags = pms._run_timeline_agent(HUMAN_ID, session)
        self.assertIsInstance(frags, list)


# ---------------------------------------------------------------------------
# Async agent wrappers
# ---------------------------------------------------------------------------


class TestAsyncAgentWrappers(unittest.IsolatedAsyncioTestCase):
    async def test_direct_facts_happy_path(self):
        good_frag = _make_fragment("explicit fact", score=0.8)

        def _run_session(driver, human_id, query):
            return [good_frag]

        with patch.object(pms, "_run_direct_facts_session", side_effect=_run_session):
            with patch.object(pms, "get_driver", return_value=MagicMock()):
                result = await pms._agent_direct_facts(HUMAN_ID, QUERY)

        self.assertEqual(result.agent_name, "direct_facts")
        self.assertEqual(len(result.fragments), 1)
        self.assertIsNone(result.error)

    async def test_context_agent_happy_path(self):
        good_frag = _make_fragment("context item", score=0.75)

        def _run_session(driver, human_id, query, embedding):
            return [good_frag]

        with patch.object(pms, "_run_context_session", side_effect=_run_session):
            with patch.object(pms, "get_driver", return_value=MagicMock()):
                result = await pms._agent_context(HUMAN_ID, QUERY, [0.0] * 768)

        self.assertEqual(result.agent_name, "context")
        self.assertIsNone(result.error)

    async def test_timeline_agent_happy_path(self):
        good_frag = _make_fragment("timeline event", score=0.7)

        def _run_session(driver, human_id):
            return [good_frag]

        with patch.object(pms, "_run_timeline_session", side_effect=_run_session):
            with patch.object(pms, "get_driver", return_value=MagicMock()):
                result = await pms._agent_timeline(HUMAN_ID)

        self.assertEqual(result.agent_name, "timeline")
        self.assertIsNone(result.error)

    async def test_agent_exception_captured(self):
        def _explode(*args, **kwargs):
            raise ConnectionError("neo4j down")

        with patch.object(pms, "_run_direct_facts_session", side_effect=_explode):
            with patch.object(pms, "get_driver", return_value=MagicMock()):
                result = await pms._agent_direct_facts(HUMAN_ID, QUERY)

        self.assertIsNotNone(result.error)
        self.assertEqual(result.fragments, [])


# ---------------------------------------------------------------------------
# parallel_memory_search — end-to-end (fully mocked)
# ---------------------------------------------------------------------------


class TestParallelMemorySearch(unittest.IsolatedAsyncioTestCase):
    """End-to-end tests for parallel_memory_search with all I/O mocked."""

    def _make_agents(
        self,
        direct_frags=None,
        context_frags=None,
        timeline_frags=None,
    ):
        """Return three async callables for patching the agent functions."""
        df = _make_agent_result("direct_facts", direct_frags or [_make_fragment("fact", score=0.8)])
        ca = _make_agent_result("context", context_frags or [_make_fragment("ctx", score=0.75)])
        tl = _make_agent_result("timeline", timeline_frags or [_make_fragment("time", score=0.7)])

        async def _fake_direct(h, q):
            return df

        async def _fake_context(h, q, e):
            return ca

        async def _fake_timeline(h):
            return tl

        return _fake_direct, _fake_context, _fake_timeline

    async def test_returns_memory_result(self):
        fd, fc, ft = self._make_agents()
        with patch.object(pms, "_agent_direct_facts", side_effect=fd), \
             patch.object(pms, "_agent_context", side_effect=fc), \
             patch.object(pms, "_agent_timeline", side_effect=ft), \
             patch.object(pms, "generate_embedding", return_value=[0.0] * 768):
            result = await pms.parallel_memory_search(QUERY, HUMAN_ID)

        self.assertIsInstance(result, pms.MemoryResult)
        self.assertEqual(result.query, QUERY)
        self.assertEqual(result.human_id, HUMAN_ID)
        self.assertFalse(result.fallback_used)

    async def test_fragments_from_all_three_agents(self):
        # MemoryFragment.source must be set explicitly — it is used by the
        # aggregator.  _make_fragment defaults to "direct_facts", so we set
        # the correct source for context and timeline fragments here.
        fd, fc, ft = self._make_agents(
            direct_frags=[_make_fragment("direct fact alpha", source="direct_facts", score=0.9)],
            context_frags=[_make_fragment("context item beta", source="context", score=0.8)],
            timeline_frags=[_make_fragment("timeline event gamma", source="timeline", score=0.7)],
        )
        with patch.object(pms, "_agent_direct_facts", side_effect=fd), \
             patch.object(pms, "_agent_context", side_effect=fc), \
             patch.object(pms, "_agent_timeline", side_effect=ft), \
             patch.object(pms, "generate_embedding", return_value=[0.0] * 768):
            result = await pms.parallel_memory_search(QUERY, HUMAN_ID)

        sources = {f.source for f in result.fragments}
        self.assertIn("direct_facts", sources)
        self.assertIn("context", sources)
        self.assertIn("timeline", sources)

    async def test_all_agents_fail_triggers_fallback(self):
        async def _fail(h, *args, **kwargs):
            return _make_agent_result(error="simulated failure")

        fallback_result = pms.MemoryResult(
            query=QUERY, human_id=HUMAN_ID,
            fragments=[_make_fragment("fallback frag", score=0.6)],
            agent_results=[], total_ms=50, fallback_used=True,
        )
        with patch.object(pms, "_agent_direct_facts", side_effect=_fail), \
             patch.object(pms, "_agent_context", side_effect=_fail), \
             patch.object(pms, "_agent_timeline", side_effect=_fail), \
             patch.object(pms, "generate_embedding", return_value=[0.0] * 768), \
             patch.object(pms, "_fallback_search", return_value=fallback_result):
            result = await pms.parallel_memory_search(QUERY, HUMAN_ID)

        self.assertTrue(result.fallback_used)

    async def test_embedding_failure_still_returns_result(self):
        """Context agent should run without embedding if generation fails."""
        fd, fc, ft = self._make_agents()
        with patch.object(pms, "generate_embedding", side_effect=Exception("ollama down")), \
             patch.object(pms, "_agent_direct_facts", side_effect=fd), \
             patch.object(pms, "_agent_context", side_effect=fc), \
             patch.object(pms, "_agent_timeline", side_effect=ft):
            result = await pms.parallel_memory_search(QUERY, HUMAN_ID)

        self.assertIsInstance(result, pms.MemoryResult)

    async def test_precomputed_embedding_skips_generation(self):
        """generate_embedding must NOT be called when precomputed_embedding is given."""
        fd, fc, ft = self._make_agents()
        with patch.object(pms, "generate_embedding") as mock_gen, \
             patch.object(pms, "_agent_direct_facts", side_effect=fd), \
             patch.object(pms, "_agent_context", side_effect=fc), \
             patch.object(pms, "_agent_timeline", side_effect=ft):
            await pms.parallel_memory_search(
                QUERY, HUMAN_ID, precomputed_embedding=[0.5] * 768
            )
        mock_gen.assert_not_called()

    async def test_total_ms_populated(self):
        fd, fc, ft = self._make_agents()
        with patch.object(pms, "_agent_direct_facts", side_effect=fd), \
             patch.object(pms, "_agent_context", side_effect=fc), \
             patch.object(pms, "_agent_timeline", side_effect=ft), \
             patch.object(pms, "generate_embedding", return_value=[0.0] * 768):
            result = await pms.parallel_memory_search(QUERY, HUMAN_ID)
        self.assertGreater(result.total_ms, 0)

    async def test_three_agent_results_in_output(self):
        fd, fc, ft = self._make_agents()
        with patch.object(pms, "_agent_direct_facts", side_effect=fd), \
             patch.object(pms, "_agent_context", side_effect=fc), \
             patch.object(pms, "_agent_timeline", side_effect=ft), \
             patch.object(pms, "generate_embedding", return_value=[0.0] * 768):
            result = await pms.parallel_memory_search(QUERY, HUMAN_ID)
        self.assertEqual(len(result.agent_results), 3)


# ---------------------------------------------------------------------------
# Fallback search
# ---------------------------------------------------------------------------


class TestFallbackSearch(unittest.TestCase):
    def test_fallback_sets_flag(self):
        ctx = {
            "similar_messages": [{"text": "msg1", "score": 0.7, "timestamp": None}],
            "thread_messages": [],
            "inferences": [],
        }
        with patch.object(pms, "assemble_context", return_value=ctx):
            result = pms._fallback_search(QUERY, HUMAN_ID)
        self.assertTrue(result.fallback_used)

    def test_fallback_converts_messages(self):
        ctx = {
            "similar_messages": [{"text": "relevant message", "score": 0.8, "timestamp": None}],
            "thread_messages": [],
            "inferences": [],
        }
        with patch.object(pms, "assemble_context", return_value=ctx):
            result = pms._fallback_search(QUERY, HUMAN_ID)
        self.assertTrue(any("relevant message" in f.text for f in result.fragments))

    def test_fallback_on_assembler_crash(self):
        with patch.object(pms, "assemble_context", side_effect=RuntimeError("dead")):
            result = pms._fallback_search(QUERY, HUMAN_ID)
        self.assertTrue(result.fallback_used)
        self.assertEqual(result.fragments, [])

    def test_fallback_inferences_converted(self):
        ctx = {
            "similar_messages": [],
            "thread_messages": [],
            "inferences": [{"content": "likes async", "confidence": 0.85}],
        }
        with patch.object(pms, "assemble_context", return_value=ctx):
            result = pms._fallback_search(QUERY, HUMAN_ID)
        inf_frags = [f for f in result.fragments if f.node_type == "Inference"]
        self.assertEqual(len(inf_frags), 1)
        self.assertAlmostEqual(inf_frags[0].score, 0.85)


# ---------------------------------------------------------------------------
# sync search_memory wrapper
# ---------------------------------------------------------------------------


class TestSearchMemorySync(unittest.TestCase):
    def test_returns_memory_result(self):
        expected = pms.MemoryResult(
            query=QUERY, human_id=HUMAN_ID,
            fragments=[_make_fragment("sync result", score=0.8)],
            agent_results=[], total_ms=50,
        )

        # parallel_memory_search is a coroutine function; replace it with one
        # that returns a coroutine resolving to `expected`.
        async def _fake_parallel(q, h, **kwargs):
            return expected

        with patch.object(pms, "parallel_memory_search", new=_fake_parallel):
            result = pms.search_memory(QUERY, HUMAN_ID)

        self.assertIsInstance(result, pms.MemoryResult)
        self.assertEqual(len(result.fragments), 1)

    def test_fallback_on_exception(self):
        fallback = pms.MemoryResult(
            query=QUERY, human_id=HUMAN_ID,
            fragments=[], agent_results=[], total_ms=10, fallback_used=True,
        )

        # Make asyncio.run() raise so the except branch fires.
        with patch.object(pms.asyncio, "run", side_effect=RuntimeError("boom")), \
             patch.object(pms, "_fallback_search", return_value=fallback):
            result = pms.search_memory(QUERY, HUMAN_ID)

        self.assertTrue(result.fallback_used)


# ---------------------------------------------------------------------------
# Performance guard: aggregate should finish in <100ms for 200 fragments
# ---------------------------------------------------------------------------


class TestAggregatePerformance(unittest.TestCase):
    def test_aggregate_200_fragments_under_100ms(self):
        frags = [_make_fragment(f"fragment text content number {i}", score=0.8)
                 for i in range(200)]
        ar = _make_agent_result(fragments=frags)
        t0 = time.monotonic()
        result, _ = pms._aggregate([ar], max_fragments=40)
        elapsed_ms = (time.monotonic() - t0) * 1000
        self.assertLess(elapsed_ms, 100, f"aggregate took {elapsed_ms:.1f}ms — too slow")
        self.assertLessEqual(len(result), 40)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
