from __future__ import annotations

"""Tests for core duplicate-claim/no-duplicate-send and Kublai/Hermes ownership routing.

Regression scenarios from canonical protocol Section 15.
"""

import importlib.util
from pathlib import Path


def load_store_module():
    path = Path(__file__).resolve().parents[1] / "coordination_store.py"
    spec = importlib.util.spec_from_file_location("coordination_store", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_policy_module():
    path = Path(__file__).resolve().parents[1] / "agent_policy.py"
    spec = importlib.util.spec_from_file_location("agent_policy", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_classifier_module():
    base = Path(__file__).resolve().parents[1]
    import sys
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    path = base / "intent_classifier.py"
    spec = importlib.util.spec_from_file_location("intent_classifier", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _store(tmp_path, filename="coordination.db"):
    store_mod = load_store_module()
    store = store_mod.CoordinationStore(tmp_path / filename)
    store.init_schema()
    return store, store_mod


# ─── Scenario 6: Duplicate simultaneous claims ────────────────────────────────

def test_first_claim_wins_second_claim_returns_false(tmp_path):
    """Scenario 6: SQLite atomic insert picks one winner; loser gets claimed=False."""
    store, _ = _store(tmp_path)

    kublai_lock = store.claim_response_lock(
        channel="telegram", chat_id="-5287556083", root_message_id="42",
        owner="kublai", tier="tier2",
    )
    hermes_attempt = store.claim_response_lock(
        channel="telegram", chat_id="-5287556083", root_message_id="42",
        owner="hermes", tier="tier2",
    )

    assert kublai_lock["claimed"] is True
    assert hermes_attempt["claimed"] is False
    assert hermes_attempt["owner"] == "kublai"
    assert hermes_attempt["lock_id"] == kublai_lock["lock_id"]


def test_loser_sees_existing_owner_in_returned_lock(tmp_path):
    store, _ = _store(tmp_path)
    store.claim_response_lock("telegram", "-chat", "99", "hermes", tier="tier1")
    kublai_result = store.claim_response_lock("telegram", "-chat", "99", "kublai", tier="tier1")
    assert kublai_result["claimed"] is False
    assert kublai_result["owner"] == "hermes"


def test_owner_can_reclaim_own_lock(tmp_path):
    """Owner re-claiming the same lock should succeed."""
    store, _ = _store(tmp_path)
    first = store.claim_response_lock("telegram", "-chat", "77", "kublai")
    second = store.claim_response_lock("telegram", "-chat", "77", "kublai")
    assert first["claimed"] is True
    assert second["claimed"] is True
    assert first["lock_id"] == second["lock_id"]


# ─── Scenario 6 extension: Active lock detection (observer behavior) ──────────

def test_get_active_lock_returns_none_when_no_lock(tmp_path):
    store, _ = _store(tmp_path)
    result = store.get_active_lock("telegram", "-5287556083", "99")
    assert result is None


def test_get_active_lock_returns_lock_when_claimed(tmp_path):
    store, _ = _store(tmp_path)
    lock = store.claim_response_lock("telegram", "-5287556083", "99", "kublai")
    active = store.get_active_lock("telegram", "-5287556083", "99")
    assert active is not None
    assert active["owner"] == "kublai"
    assert active["lock_id"] == lock["lock_id"]


def test_get_active_lock_returns_none_after_answered(tmp_path):
    store, _ = _store(tmp_path)
    lock = store.claim_response_lock("telegram", "-5287556083", "55", "kublai")
    store.finalize_lock(lock["lock_id"], status="answered", final_summary="done")
    active = store.get_active_lock("telegram", "-5287556083", "55")
    assert active is None


# ─── Scenario 3: Explicit collaboration → Kublai owns, Hermes contributes ─────

def test_tier2_kublai_owns_hermes_contributes(tmp_path):
    store, _ = _store(tmp_path)
    lock = store.claim_response_lock(
        channel="telegram", chat_id="-5287556083", root_message_id="371",
        owner="kublai", tier="tier2",
        required_contributors=["hermes"], support_agents=["hermes"],
    )
    assert lock["claimed"] is True
    assert lock["required_contributors"] == ["hermes"]

    contribution = store.add_contribution(
        lock["lock_id"], contributor="hermes",
        summary="Use lock plus send gate; add stale-owner recovery.",
        stance="support_with_additions",
        key_points=["Do not expose deliberation.", "Record timeout honestly."],
    )
    assert contribution["contributor"] == "hermes"
    assert contribution["stance"] == "support_with_additions"
    assert len(contribution["key_points"]) == 2

    store.finalize_lock(lock["lock_id"], status="ready_to_answer", final_summary="Ready.", actor="kublai")
    why = store.explain_why("telegram", "-5287556083", "371")
    assert why["lock"]["status"] == "ready_to_answer"
    assert why["contributions"][0]["contributor"] == "hermes"


# ─── Scenario 2: Hermes health question — Hermes owns, Kublai silent ──────────

def test_hermes_owns_health_domain_intent():
    p = load_policy_module()
    intent = {"explicit_owner": "hermes", "requires_collaboration": False, "domain": "system_health"}
    owner = p.select_owner(intent)
    assert owner == "hermes"


def test_kublai_silent_on_hermes_health_lock(tmp_path):
    """If Hermes has the lock, Kublai attempting to claim gets claimed=False."""
    store, _ = _store(tmp_path)
    hermes_lock = store.claim_response_lock("telegram", "-5287556083", "200", "hermes", tier="tier1")
    kublai_attempt = store.claim_response_lock("telegram", "-5287556083", "200", "kublai", tier="tier1")
    assert hermes_lock["claimed"] is True
    assert kublai_attempt["claimed"] is False


# ─── Scenario 14: Conflicting domain — repair Kublai → Hermes owns ────────────

def test_kublai_repair_routes_to_hermes_explicit_collab():
    p = load_policy_module()
    intent = {"requires_collaboration": True, "domain": "kublai_repair"}
    assert p.select_owner(intent) == "hermes"


# ─── No-duplicate-send: send gate idempotency ─────────────────────────────────

def test_send_gate_prevents_duplicate_sends(tmp_path):
    store, store_mod = _store(tmp_path)
    lock = store.claim_response_lock("telegram", "-5287556083", "42", "kublai")

    send_key = store.make_send_key("telegram", "-5287556083", "", "42", "kublai", "answer")
    first = store.enqueue_send_once(send_key, "telegram", "-5287556083", "", "one answer")
    duplicate = store.enqueue_send_once(send_key, "telegram", "-5287556083", "", "duplicate answer")

    assert first["enqueued"] is True
    assert duplicate["enqueued"] is False
    assert store.get_outbox_item(send_key)["text"] == "one answer"


def test_different_owners_get_different_send_keys(tmp_path):
    store, _ = _store(tmp_path)
    key_kublai = store.make_send_key("telegram", "-5287556083", "", "42", "kublai", "answer")
    key_hermes = store.make_send_key("telegram", "-5287556083", "", "42", "hermes", "answer")
    assert key_kublai != key_hermes


def test_scope_version_changes_send_key(tmp_path):
    """Different scope_versions must produce different send_keys so old drafts can't post."""
    store, _ = _store(tmp_path)
    key_v1 = store.make_send_key("telegram", "-5287556083", "", "42", "kublai", "answer")
    key_v2 = store.make_send_key("telegram", "-5287556083", "", "42", "kublai", "answer:v2")
    assert key_v1 != key_v2


# ─── Intent classifier: Kublai/Hermes ownership routing ──────────────────────

def test_classifier_kublai_routing_question():
    mod = load_classifier_module()
    result = mod.classify_intent("Kublai, why did that route to Mongke?")
    assert result["should_respond"] is True
    assert result["preferred_owner"] == "kublai"
    assert result["tier"] == "tier_1_routine"


def test_classifier_hermes_health_question():
    mod = load_classifier_module()
    result = mod.classify_intent("Hermes, is the cron healthy?")
    assert result["should_respond"] is True
    assert result["preferred_owner"] == "hermes"


def test_classifier_explicit_collab_request():
    mod = load_classifier_module()
    result = mod.classify_intent("Kublai and Hermes, collaborate on one proposal for group chat routing.")
    assert result["should_respond"] is True
    assert result["requires_collaboration"] is True
    assert result["tier"] == "tier_2_shared_expertise"
    assert result["preferred_owner"] == "kublai"


def test_classifier_hermes_kublai_repair():
    mod = load_classifier_module()
    result = mod.classify_intent("Hermes, check why Kublai is silent.")
    assert result["should_respond"] is True
    assert result["preferred_owner"] == "hermes"


def test_classifier_deployment_decision_is_tier3():
    mod = load_classifier_module()
    result = mod.classify_intent("Both of you decide whether to deploy this.")
    assert result["tier"] == "tier_3_governance"
    assert result["requires_human_approval"] is True


def test_classifier_casual_chat_no_response():
    mod = load_classifier_module()
    result = mod.classify_intent("Thanks, that looks good!")
    assert result["should_respond"] is False


# ─── Claim token and epoch ────────────────────────────────────────────────────

def test_claim_token_is_set_on_claim(tmp_path):
    store, _ = _store(tmp_path)
    lock = store.claim_response_lock("telegram", "-5287556083", "88", "kublai")
    assert len(lock["owner_claim_token"]) > 0


def test_owner_epoch_increments_on_reclaim(tmp_path):
    store, _ = _store(tmp_path)
    first = store.claim_response_lock("telegram", "-5287556083", "89", "kublai")
    second = store.claim_response_lock("telegram", "-5287556083", "89", "kublai")
    assert second["owner_epoch"] == first["owner_epoch"] + 1


def test_heartbeat_update_requires_correct_token(tmp_path):
    store, _ = _store(tmp_path)
    lock = store.claim_response_lock("telegram", "-5287556083", "90", "kublai")
    updated = store.update_heartbeat(lock["lock_id"], "kublai", lock["owner_claim_token"])
    assert updated is True

    rejected = store.update_heartbeat(lock["lock_id"], "kublai", "wrong_token")
    assert rejected is False


# ─── message_tool_guard ──────────────────────────────────────────────────────

def test_message_tool_guard_raises_for_same_chat():
    import sys
    scripts = Path(__file__).resolve().parents[3] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import importlib
    ts_mod = importlib.import_module("telegram_send") if "telegram_send" in sys.modules else None
    if ts_mod is None:
        spec = importlib.util.spec_from_file_location("telegram_send", scripts / "telegram_send.py")
        ts_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ts_mod)

    try:
        ts_mod.message_tool_guard("-5287556083", "-5287556083")
        assert False, "should have raised SameChatMessageToolDenied"
    except ts_mod.SameChatMessageToolDenied:
        pass


def test_message_tool_guard_allows_cross_chat():
    import sys
    scripts = Path(__file__).resolve().parents[3] / "scripts"
    spec = importlib.util.spec_from_file_location("tg_send_guard", scripts / "telegram_send.py")
    ts_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ts_mod)
    ts_mod.message_tool_guard("-5287556083", "-1111111111")


def test_message_tool_guard_approved_exception_bypasses():
    import sys
    scripts = Path(__file__).resolve().parents[3] / "scripts"
    spec = importlib.util.spec_from_file_location("tg_send_guard2", scripts / "telegram_send.py")
    ts_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ts_mod)
    ts_mod.message_tool_guard("-5287556083", "-5287556083", purpose="approved_exception")
