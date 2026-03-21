#!/usr/bin/env python3
"""
Test Group Chat Context Isolation.

Verifies:
1. DM context does not leak into group context assembly
2. Group A messages are invisible in Group B's context
3. SENSITIVE messages never bridge to group context
4. ResponseGuard blocks PII patterns in group responses
5. Shareability classification works correctly
"""

import sys
import os
import uuid

# Ensure scripts dir is on path
SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS_DIR)

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def neo4j_available():
    """Check if Neo4j is available — skip all tests if not."""
    try:
        from neo4j_task_tracker import is_neo4j_available
        if not is_neo4j_available():
            pytest.skip("Neo4j not available")
    except Exception:
        pytest.skip("Neo4j not available")


@pytest.fixture
def test_phone():
    return f"+1999{uuid.uuid4().hex[:7]}"


@pytest.fixture
def test_group_a():
    return f"TEST_GROUP_A_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def test_group_b():
    return f"TEST_GROUP_B_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def cleanup_nodes():
    """Track created node IDs for cleanup after each test."""
    created = {"messages": [], "groups": [], "threads": [], "humans": []}
    yield created

    # Cleanup
    try:
        from neo4j_task_tracker import neo4j_session
        with neo4j_session() as session:
            for mid in created["messages"]:
                session.run("MATCH (m:Message {id: $id}) DETACH DELETE m", id=mid)
            for gid in created["groups"]:
                session.run("MATCH (g:Group {groupId: $id}) DETACH DELETE g", id=gid)
            for tid in created["threads"]:
                session.run("MATCH (t:Thread {id: $id}) DETACH DELETE t", id=tid)
    except Exception as e:
        print(f"Cleanup warning: {e}")


# ---------------------------------------------------------------------------
# Test 1: End-to-End Group Isolation
# ---------------------------------------------------------------------------

class TestGroupIsolation:
    """DM context must not leak into group context assembly."""

    def test_dm_content_invisible_in_group_context(self, neo4j_available, test_phone, test_group_a, cleanup_nodes):
        """Ingest a DM with private content, then verify group context is clean."""
        from conversation_ingester import ingest_message
        from context_assembler import assemble_context

        # Ingest a DM with distinctive private content
        dm_result = ingest_message(
            phone=test_phone,
            content="My salary is $150,000 and my doctor said I need surgery",
            direction="inbound",
            channel="signal",
            group_id=None,  # DM
        )
        cleanup_nodes["messages"].append(dm_result["message_id"])
        if dm_result.get("thread_id"):
            cleanup_nodes["threads"].append(dm_result["thread_id"])
        human_id = dm_result["human_id"]

        # Ingest a group message from same human
        group_result = ingest_message(
            phone=test_phone,
            content="Hey everyone, how's the project going?",
            direction="inbound",
            channel="signal",
            group_id=test_group_a,
        )
        cleanup_nodes["messages"].append(group_result["message_id"])
        cleanup_nodes["groups"].append(test_group_a)
        if group_result.get("thread_id"):
            cleanup_nodes["threads"].append(group_result["thread_id"])

        # Assemble group context
        ctx = assemble_context(human_id, "What's the status?", group_id=test_group_a)

        # Verify: group context should NOT contain DM content
        # Check thread messages
        for msg in ctx.get("thread_messages", []):
            text = msg.get("text", "") or ""
            assert "salary" not in text.lower(), f"DM salary leaked into group thread: {text}"
            assert "doctor" not in text.lower(), f"DM doctor leaked into group thread: {text}"
            assert "surgery" not in text.lower(), f"DM surgery leaked into group thread: {text}"

        # Check similar messages
        for msg in ctx.get("similar_messages", []):
            text = msg.get("text", "") or ""
            assert "salary" not in text.lower(), f"DM salary leaked via vector search: {text}"

        # Verify scope is set
        assert ctx.get("scope") == f"group:{test_group_a}"

    def test_dm_context_still_works(self, neo4j_available, test_phone, cleanup_nodes):
        """DM context assembly should still return DM messages."""
        from conversation_ingester import ingest_message
        from context_assembler import assemble_context

        dm_result = ingest_message(
            phone=test_phone,
            content="Remember our private discussion about the architecture",
            direction="inbound",
            channel="signal",
            group_id=None,
        )
        cleanup_nodes["messages"].append(dm_result["message_id"])
        if dm_result.get("thread_id"):
            cleanup_nodes["threads"].append(dm_result["thread_id"])
        human_id = dm_result["human_id"]

        # DM context assembly should find the message
        ctx = assemble_context(human_id, "What did we discuss?")
        assert ctx.get("scope") == "dm"

        # Should have thread messages from the DM
        thread_texts = [m.get("text", "") or "" for m in ctx.get("thread_messages", [])]
        assert any("architecture" in t.lower() for t in thread_texts), \
            "DM message not found in DM context"


# ---------------------------------------------------------------------------
# Test 2: Multi-Group Isolation
# ---------------------------------------------------------------------------

class TestMultiGroupIsolation:
    """Messages in Group A must be invisible in Group B's context."""

    def test_cross_group_isolation(self, neo4j_available, test_phone, test_group_a, test_group_b, cleanup_nodes):
        from conversation_ingester import ingest_message
        from context_assembler import assemble_context

        # Ingest message in Group A
        result_a = ingest_message(
            phone=test_phone,
            content="Group A secret: the deployment is at midnight",
            direction="inbound",
            channel="signal",
            group_id=test_group_a,
        )
        cleanup_nodes["messages"].append(result_a["message_id"])
        cleanup_nodes["groups"].append(test_group_a)
        if result_a.get("thread_id"):
            cleanup_nodes["threads"].append(result_a["thread_id"])
        human_id = result_a["human_id"]

        # Ingest message in Group B
        result_b = ingest_message(
            phone=test_phone,
            content="Group B chat about lunch plans",
            direction="inbound",
            channel="signal",
            group_id=test_group_b,
        )
        cleanup_nodes["messages"].append(result_b["message_id"])
        cleanup_nodes["groups"].append(test_group_b)
        if result_b.get("thread_id"):
            cleanup_nodes["threads"].append(result_b["thread_id"])

        # Group B context should NOT contain Group A content
        ctx_b = assemble_context(human_id, "What's happening?", group_id=test_group_b)
        for msg in ctx_b.get("thread_messages", []):
            text = msg.get("text", "") or ""
            assert "deployment" not in text.lower(), f"Group A content leaked to Group B: {text}"
            assert "midnight" not in text.lower(), f"Group A content leaked to Group B: {text}"

        # Group A context should NOT contain Group B content
        ctx_a = assemble_context(human_id, "What's happening?", group_id=test_group_a)
        for msg in ctx_a.get("thread_messages", []):
            text = msg.get("text", "") or ""
            assert "lunch" not in text.lower(), f"Group B content leaked to Group A: {text}"


# ---------------------------------------------------------------------------
# Test 3: Message Scope on Ingested Messages
# ---------------------------------------------------------------------------

class TestMessageScope:
    """Verify scope property is correctly set on ingested messages."""

    def test_dm_message_gets_dm_scope(self, neo4j_available, test_phone, cleanup_nodes):
        from conversation_ingester import ingest_message
        from neo4j_task_tracker import neo4j_session

        result = ingest_message(
            phone=test_phone,
            content="This is a DM",
            direction="inbound",
            channel="signal",
            group_id=None,
        )
        cleanup_nodes["messages"].append(result["message_id"])
        if result.get("thread_id"):
            cleanup_nodes["threads"].append(result["thread_id"])

        with neo4j_session() as session:
            rec = session.run(
                "MATCH (m:Message {id: $mid}) RETURN m.scope AS scope, m.groupId AS gid",
                mid=result["message_id"],
            ).single()
            assert rec["scope"] == "dm", f"Expected 'dm', got '{rec['scope']}'"
            assert rec["gid"] is None, f"Expected None groupId for DM, got '{rec['gid']}'"

    def test_group_message_gets_group_scope(self, neo4j_available, test_phone, test_group_a, cleanup_nodes):
        from conversation_ingester import ingest_message
        from neo4j_task_tracker import neo4j_session

        result = ingest_message(
            phone=test_phone,
            content="This is a group message",
            direction="inbound",
            channel="signal",
            group_id=test_group_a,
        )
        cleanup_nodes["messages"].append(result["message_id"])
        cleanup_nodes["groups"].append(test_group_a)
        if result.get("thread_id"):
            cleanup_nodes["threads"].append(result["thread_id"])

        with neo4j_session() as session:
            rec = session.run(
                "MATCH (m:Message {id: $mid}) RETURN m.scope AS scope, m.groupId AS gid",
                mid=result["message_id"],
            ).single()
            assert rec["scope"] == f"group:{test_group_a}"
            assert rec["gid"] == test_group_a

    def test_group_node_created(self, neo4j_available, test_phone, test_group_a, cleanup_nodes):
        from conversation_ingester import ingest_message
        from neo4j_task_tracker import neo4j_session

        result = ingest_message(
            phone=test_phone,
            content="First message in group",
            direction="inbound",
            channel="signal",
            group_id=test_group_a,
        )
        cleanup_nodes["messages"].append(result["message_id"])
        cleanup_nodes["groups"].append(test_group_a)
        if result.get("thread_id"):
            cleanup_nodes["threads"].append(result["thread_id"])

        with neo4j_session() as session:
            rec = session.run(
                "MATCH (g:Group {groupId: $gid}) RETURN g.status AS status, g.messageCount AS count",
                gid=test_group_a,
            ).single()
            assert rec is not None, "Group node not created"
            assert rec["status"] == "ACTIVE"
            assert rec["count"] >= 1


# ---------------------------------------------------------------------------
# Test 4: Shareability Classification
# ---------------------------------------------------------------------------

class TestShareability:
    """Verify shareability classification catches sensitive content."""

    def test_sensitive_health(self):
        from group_context_bridge import classify_shareability
        assert classify_shareability("my doctor appointment is Thursday") == "SENSITIVE"
        assert classify_shareability("started new medication today") == "SENSITIVE"

    def test_sensitive_finance(self):
        from group_context_bridge import classify_shareability
        assert classify_shareability("salary is $150k") == "SENSITIVE"
        assert classify_shareability("I owe a lot on my mortgage") == "SENSITIVE"

    def test_sensitive_legal(self):
        from group_context_bridge import classify_shareability
        assert classify_shareability("my lawyer said to file by Friday") == "SENSITIVE"

    def test_private_feelings(self):
        from group_context_bridge import classify_shareability
        assert classify_shareability("feeling really stressed lately") == "PRIVATE"
        assert classify_shareability("just between us, I'm worried") == "PRIVATE"

    def test_group_safe(self):
        from group_context_bridge import classify_shareability
        assert classify_shareability("the deployment looks good") == "GROUP_SAFE"
        assert classify_shareability("hey everyone, the build passed") == "GROUP_SAFE"

    def test_empty_content(self):
        from group_context_bridge import classify_shareability
        assert classify_shareability("") == "GROUP_SAFE"


# ---------------------------------------------------------------------------
# Test 5: ResponseGuard
# ---------------------------------------------------------------------------

class TestResponseGuard:
    """Verify ResponseGuard filters PII from group responses."""

    def test_blocks_phone_numbers(self):
        from response_guard import guard_response
        result = guard_response("Call +19194133445 for info", is_group=True)
        assert "+1919" not in result
        assert "[phone]" in result

    def test_blocks_file_paths(self):
        from response_guard import guard_response
        result = guard_response("Check /Users/kublai/file.txt", is_group=True)
        assert "/Users/" not in result
        assert "[path]" in result

    def test_blocks_uuids(self):
        from response_guard import guard_response
        result = guard_response("ID is 550e8400-e29b-41d4-a716-446655440000", is_group=True)
        assert "550e8400" not in result

    def test_blocks_credentials(self):
        from response_guard import guard_response
        result = guard_response("Use sk_live_abc123def456ghi789", is_group=True)
        assert "sk_live" not in result

    def test_dm_passthrough(self):
        from response_guard import guard_response
        original = "Call +19194133445 for info"
        result = guard_response(original, is_group=False)
        assert result == original, "DM response should not be filtered"

    def test_enforces_length_cap(self):
        from response_guard import guard_response
        long_text = "x" * 600
        result = guard_response(long_text, is_group=True)
        assert len(result) <= 500, f"Group response too long: {len(result)} chars"

    def test_fallback_on_heavy_redaction(self):
        from response_guard import guard_response
        # Multiple PII items should trigger fallback
        heavy = "Call +19194133445 or +16624580725, check /Users/kublai/secret.txt, use sk_test_abc123def456ghi789 and pk_test_xyz987"
        result = guard_response(heavy, is_group=True)
        assert result == "Let's discuss that in a DM."


# ---------------------------------------------------------------------------
# Test 6: Group Engagement Heuristics
# ---------------------------------------------------------------------------

class TestGroupEngagement:
    """Verify group engagement rules default to silent."""

    def test_default_silent_in_group(self):
        from engagement_assessor import _heuristic_assess_group
        result = _heuristic_assess_group("random chat message", "inbound")
        assert result["decision"] == "silent"

    def test_respond_when_addressed(self):
        from engagement_assessor import _heuristic_assess_group
        result = _heuristic_assess_group("Hey Kublai, what do you think?", "inbound")
        assert result["decision"] == "respond"

    def test_respond_to_questions(self):
        from engagement_assessor import _heuristic_assess_group
        result = _heuristic_assess_group("What's the status of the deployment?", "inbound")
        assert result["decision"] == "respond"

    def test_silent_for_short_questions(self):
        from engagement_assessor import _heuristic_assess_group
        result = _heuristic_assess_group("huh?", "inbound")
        assert result["decision"] == "silent"  # Too short

    def test_silent_for_outbound(self):
        from engagement_assessor import _heuristic_assess_group
        result = _heuristic_assess_group("message", "outbound")
        assert result["decision"] == "silent"


# ---------------------------------------------------------------------------
# Test 7: Inference, Drift Signal, and Action Item Exclusion
# ---------------------------------------------------------------------------

class TestInferenceAndDriftExclusion:
    """Verify inferences, drift signals, and action items are excluded from group context."""

    def test_inferences_excluded_from_group(self, neo4j_available, test_phone, test_group_a, cleanup_nodes):
        from conversation_ingester import ingest_message
        from context_assembler import assemble_context

        result = ingest_message(
            phone=test_phone,
            content="Group hello",
            direction="inbound",
            channel="signal",
            group_id=test_group_a,
        )
        cleanup_nodes["messages"].append(result["message_id"])
        cleanup_nodes["groups"].append(test_group_a)
        if result.get("thread_id"):
            cleanup_nodes["threads"].append(result["thread_id"])

        ctx = assemble_context(result["human_id"], "msg", group_id=test_group_a)
        assert ctx.get("inferences") == [], "Inferences should be excluded from group context"

    def test_drift_signals_excluded_from_group(self, neo4j_available, test_phone, test_group_a, cleanup_nodes):
        from conversation_ingester import ingest_message
        from context_assembler import assemble_context

        result = ingest_message(
            phone=test_phone,
            content="Group hello",
            direction="inbound",
            channel="signal",
            group_id=test_group_a,
        )
        cleanup_nodes["messages"].append(result["message_id"])
        cleanup_nodes["groups"].append(test_group_a)
        if result.get("thread_id"):
            cleanup_nodes["threads"].append(result["thread_id"])

        ctx = assemble_context(result["human_id"], "msg", group_id=test_group_a)
        assert ctx.get("drift_signals") == [], "Drift signals should be excluded from group context"

    def test_action_items_excluded_from_group(self, neo4j_available, test_phone, test_group_a, cleanup_nodes):
        from conversation_ingester import ingest_message
        from context_assembler import assemble_context

        result = ingest_message(
            phone=test_phone,
            content="Group hello",
            direction="inbound",
            channel="signal",
            group_id=test_group_a,
        )
        cleanup_nodes["messages"].append(result["message_id"])
        cleanup_nodes["groups"].append(test_group_a)
        if result.get("thread_id"):
            cleanup_nodes["threads"].append(result["thread_id"])

        ctx = assemble_context(result["human_id"], "msg", group_id=test_group_a)
        assert ctx.get("action_items") == [], "Action items should be excluded from group context"

    def test_dm_still_gets_all_data(self, neo4j_available, test_phone, cleanup_nodes):
        from conversation_ingester import ingest_message
        from context_assembler import assemble_context

        result = ingest_message(
            phone=test_phone,
            content="DM hello",
            direction="inbound",
            channel="signal",
            group_id=None,
        )
        cleanup_nodes["messages"].append(result["message_id"])
        if result.get("thread_id"):
            cleanup_nodes["threads"].append(result["thread_id"])

        ctx = assemble_context(result["human_id"], "msg")
        # DM context should NOT force-exclude these (they may be empty if no data exists,
        # but the key is they're not forced to [])
        assert ctx.get("scope") == "dm"
        # These are lists, not forced to [] — they were fetched from the DB
        assert isinstance(ctx.get("drift_signals"), list)
        assert isinstance(ctx.get("action_items"), list)
        assert isinstance(ctx.get("inferences"), list)


# ---------------------------------------------------------------------------
# Test 8: Vector Search Isolation
# ---------------------------------------------------------------------------

class TestVectorSearchIsolation:
    """Verify vector search respects scope filtering with over-fetch."""

    def test_vector_search_uses_scope(self, neo4j_available, test_phone, test_group_a, cleanup_nodes):
        from conversation_ingester import ingest_message
        from context_assembler import assemble_context

        # Ingest DM
        dm_result = ingest_message(
            phone=test_phone,
            content="My private thoughts about quantum computing research",
            direction="inbound",
            channel="signal",
            group_id=None,
        )
        cleanup_nodes["messages"].append(dm_result["message_id"])
        if dm_result.get("thread_id"):
            cleanup_nodes["threads"].append(dm_result["thread_id"])

        # Ingest group msg
        group_result = ingest_message(
            phone=test_phone,
            content="Let's discuss quantum computing in the group",
            direction="inbound",
            channel="signal",
            group_id=test_group_a,
        )
        cleanup_nodes["messages"].append(group_result["message_id"])
        cleanup_nodes["groups"].append(test_group_a)
        if group_result.get("thread_id"):
            cleanup_nodes["threads"].append(group_result["thread_id"])

        # Group context should not contain DM messages in similar_messages
        ctx = assemble_context(dm_result["human_id"], "quantum computing", group_id=test_group_a)
        for msg in ctx.get("similar_messages", []):
            text = msg.get("text", "") or ""
            assert "private thoughts" not in text.lower(), \
                f"DM content leaked into group vector search: {text}"


# ---------------------------------------------------------------------------
# Test 9: Profile Privacy
# ---------------------------------------------------------------------------

class TestProfilePrivacy:
    """Verify phone numbers stripped from group profile."""

    def test_group_profile_no_phone_identifiers(self, neo4j_available, test_phone, test_group_a, cleanup_nodes):
        from conversation_ingester import ingest_message
        from context_assembler import assemble_context

        result = ingest_message(
            phone=test_phone,
            content="Hello group",
            direction="inbound",
            channel="signal",
            group_id=test_group_a,
        )
        cleanup_nodes["messages"].append(result["message_id"])
        cleanup_nodes["groups"].append(test_group_a)
        if result.get("thread_id"):
            cleanup_nodes["threads"].append(result["thread_id"])

        ctx = assemble_context(result["human_id"], "hi", group_id=test_group_a)
        profile = ctx.get("profile") or {}
        identifiers = profile.get("identifiers", [])
        for ident in identifiers:
            assert ident.get("type") not in ("PHONE", "EMAIL", "SSN"), \
                f"Sensitive identifier type leaked to group: {ident}"


# ---------------------------------------------------------------------------
# Test 10: Social Context Privacy
# ---------------------------------------------------------------------------

class TestSocialContextPrivacy:
    """Verify sensitive relationship context filtered in groups."""

    def test_classify_shareability_for_social_filter(self):
        from group_context_bridge import classify_shareability
        # Sensitive content should be classified
        assert classify_shareability("diagnosed with anxiety") == "SENSITIVE"
        assert classify_shareability("owes money on mortgage") == "SENSITIVE"
        # Safe content should pass
        assert classify_shareability("works on the same team") == "GROUP_SAFE"


# ---------------------------------------------------------------------------
# Test 11: Unicode Normalization in Response Guard
# ---------------------------------------------------------------------------

class TestResponseGuardUnicode:
    """Verify Unicode normalization prevents bypass."""

    def test_fullwidth_digits_caught(self):
        from response_guard import guard_response
        # Full-width digits: ＋１９１９４１３３４４５
        fullwidth = "\uff0b\uff11\uff19\uff11\uff19\uff14\uff11\uff13\uff13\uff14\uff14\uff15"
        result = guard_response(fullwidth, is_group=True)
        assert "[phone]" in result, f"Full-width phone not caught: {result}"

    def test_zero_width_chars_stripped(self):
        from response_guard import guard_response
        # Insert zero-width chars in a phone number
        zwj_phone = "+1\u200b919\u200c413\u200d3445"
        result = guard_response(zwj_phone, is_group=True)
        assert "+1" not in result or "[phone]" in result, \
            f"Zero-width bypass not caught: {result}"
