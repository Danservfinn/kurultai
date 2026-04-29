#!/usr/bin/env python3
from __future__ import annotations

"""Thin adapter bridging raw Telegram updates to the multi-agent coordination protocol.

Integration point for OpenClaw/Kublai:
  Call process_inbound_update(update, agent_id, store) from the agent's
  on_telegram_inbound hook (or equivalent message-received handler).

This module is intentionally free of OpenClaw runtime imports so both
Kublai and Hermes can import it without cross-agent dependencies.

## OpenClaw hook wiring

In each agent's CLAUDE.md or session startup instructions, add:

    When you receive a Telegram group message, run:
        python3 ~/.openclaw/agents/main/shared-context/hermes-kublai/inbound_adapter.py \
            --agent kublai \
            --update-json '<raw_telegram_update_json>'

    If the output contains "action": "claim_and_answer", proceed to answer.
    If "action": "stay_silent", do not post publicly.
    If "action": "contribute", submit a structured contribution via coordination_cli.py contribute.

Alternatively, import and call process_inbound_update() directly in Python.
"""

import json
import sys
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from coordination_store import CoordinationStore, DEFAULT_DB
from intent_classifier import classify_intent
from thread_resolver import extract_message_metadata
from agent_policy import select_owner, select_support_agents


# Tiers that require collaboration (non-trivial lock TTLs)
COLLAB_TIERS = {"tier_2_shared_expertise", "tier2", "tier_3_governance", "tier3"}

TIER_TTL_SECONDS: dict[str, int] = {
    "tier_1_routine": 90,
    "tier1": 90,
    "tier_2_shared_expertise": 120,
    "tier2": 120,
    "tier_3_governance": 900,
    "tier3": 900,
}

DEFAULT_TTL = 120


def process_inbound_update(
    update: dict[str, Any],
    agent_id: str,
    store: CoordinationStore | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Full inbound pipeline from raw Telegram update to lock decision.

    Returns a decision dict:
      action: "claim_and_answer" | "contribute" | "stay_silent" | "observe"
      lock: the lock dict (if claimed or found)
      intent: the classified intent
      meta: normalized message metadata

    This function is idempotent — calling it twice for the same update
    will return the same decision based on current lock state.
    """
    if store is None:
        store = CoordinationStore(db_path or DEFAULT_DB)
        store.init_schema()

    meta = extract_message_metadata(update)
    text = meta.get("text", "")

    if not text.strip():
        return _decision("observe", meta=meta, intent=None, lock=None, reason="empty_text")

    intent = classify_intent(
        text=text,
        root_message_id=meta["root_message_id"],
    )

    if not intent.get("should_respond"):
        return _decision("observe", meta=meta, intent=intent, lock=None, reason="not_actionable")

    channel = meta["channel"]
    chat_id = meta["chat_id"]
    root_msg_id = meta["root_message_id"]
    thread_id = meta["thread_id"]
    tier = intent.get("tier", "tier_1_routine")
    preferred_owner = intent.get("preferred_owner", "kublai")

    # Check if another agent already owns this thread
    existing_lock = store.get_active_lock(channel, chat_id, root_msg_id, thread_id)
    if existing_lock and existing_lock["owner"] != agent_id:
        # Non-owner: possibly contribute if we're a required contributor
        lock_owner = existing_lock["owner"]
        required = existing_lock.get("required_contributors", [])
        if agent_id in required:
            return _decision(
                "contribute",
                meta=meta,
                intent=intent,
                lock=existing_lock,
                reason=f"required_contributor_for_{lock_owner}_lock",
            )
        return _decision(
            "stay_silent",
            meta=meta,
            intent=intent,
            lock=existing_lock,
            reason=f"lock_owned_by_{lock_owner}",
        )

    # Attempt to claim
    if preferred_owner != agent_id:
        # This agent is not the preferred owner — try to claim anyway so
        # we can stay silent if we lose. The claim will fail if the preferred
        # owner already claimed.
        pass

    required = intent.get("support_agents", []) if preferred_owner == agent_id else []
    support = intent.get("support_agents", [])
    ttl = TIER_TTL_SECONDS.get(tier, DEFAULT_TTL)

    lock = store.claim_response_lock(
        channel=channel,
        chat_id=chat_id,
        root_message_id=root_msg_id,
        owner=agent_id,
        tier=tier,
        thread_id=thread_id,
        required_contributors=required if preferred_owner == agent_id else [],
        support_agents=support if preferred_owner == agent_id else [],
        ttl_seconds=ttl,
        risk_level=intent.get("risk_level", "low"),
        domain=intent.get("domain", ""),
        request_type=intent.get("request_type", ""),
        reply_to_message_id=meta.get("message_id"),
    )

    if lock.get("claimed"):
        if preferred_owner != agent_id:
            # Won the claim but not the preferred owner — release ownership back
            # (in practice the preferred owner will re-claim on their turn).
            # For now: claim and answer only if we ARE the correct owner.
            # If this agent is not preferred, stay silent and let the right owner answer.
            store.finalize_lock(lock["lock_id"], status="cancelled", actor=agent_id)
            return _decision(
                "stay_silent",
                meta=meta,
                intent=intent,
                lock=lock,
                reason=f"preferred_owner_is_{preferred_owner}_not_{agent_id}",
            )
        return _decision("claim_and_answer", meta=meta, intent=intent, lock=lock, reason="claimed")

    # Claim failed — another agent owns it
    existing = store.get_active_lock(channel, chat_id, root_msg_id, thread_id)
    if existing and agent_id in (existing.get("required_contributors") or []):
        return _decision("contribute", meta=meta, intent=intent, lock=existing, reason="required_contributor")

    return _decision("stay_silent", meta=meta, intent=intent, lock=lock, reason="claim_lost")


def _decision(
    action: str,
    meta: dict[str, Any] | None,
    intent: dict[str, Any] | None,
    lock: dict[str, Any] | None,
    reason: str = "",
) -> dict[str, Any]:
    return {
        "action": action,
        "reason": reason,
        "meta": meta or {},
        "intent": intent or {},
        "lock": lock,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Process one Telegram inbound update through the coordination protocol")
    parser.add_argument("--agent", required=True, help="Agent ID (kublai or hermes)")
    parser.add_argument("--update-json", required=True, help="Raw Telegram update as JSON string")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Coordination DB path")
    args = parser.parse_args()

    try:
        update_obj = json.loads(args.update_json)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"invalid JSON: {e}"}))
        sys.exit(1)

    store = CoordinationStore(args.db)
    store.init_schema()
    result = process_inbound_update(update_obj, args.agent, store)
    print(json.dumps(result, default=str))
