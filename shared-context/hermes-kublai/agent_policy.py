#!/usr/bin/env python3
from __future__ import annotations

"""Deterministic owner selection for Kublai/Hermes group-chat collaboration.

Implements the canonical scoring rules from the group-chat-collaboration-protocol.
Both agents import this module to determine who owns a given response.
"""

from typing import Any

HERMES_PRIMARY_DOMAINS = frozenset({
    "system_health",
    "agent_malfunction",
    "runtime_debugging",
    "cron_hygiene",
    "memory_maintenance",
    "wiki_maintenance",
    "protocol_maintenance",
    "provider_debugging",
    "kublai_repair",
    "openclaw_repair",
    "incident_response",
})

KUBLAI_PRIMARY_DOMAINS = frozenset({
    "routing",
    "queue_status",
    "project_management",
    "specialist_delegation",
    "kurultai_architecture",
    "group_chat_behavior",
    "protocol_proposal",
    "cross_agent_coordination",
    "async_task_intake",
    "strategy",
    "feature_planning",
    "task_dispatch",
    "group_chat_protocol",
})

CLAIM_PRIORITY: dict[str, int] = {
    "explicit_mentioned_owner": 100,
    "domain_primary_owner": 80,
    "collaboration_default_aggregator": 60,
    "fallback_owner": 20,
}

AGENT_TIEBREAK: dict[str, int] = {
    "kublai": 10,
    "hermes": 5,
}

KNOWN_AGENTS = frozenset({"kublai", "hermes"})


def select_owner(intent: dict[str, Any]) -> str:
    """Return the deterministic owner agent for this intent.

    Intent fields used (all optional with safe defaults):
      explicit_owner: str | None — agent directly addressed by name
      requires_collaboration: bool — "both of you", "collaborate" phrasing
      domain: str — classified domain string
      requires_specialist_routing: bool — needs async task routing
      topic: str — synonym for domain when present

    Priority:
      1. Explicit single-agent mention (no collab required) → that agent
      2. Hermes-primary domain → hermes
      3. Kublai-primary domain → kublai
      4. Needs specialist routing → kublai (routing default)
      5. Collab request in Hermes-primary topic → hermes
      6. Collab request (default) → kublai
      7. Fallback → kublai
    """
    explicit_owner: str | None = intent.get("explicit_owner") or intent.get("preferred_owner")
    requires_collab: bool = bool(intent.get("requires_collaboration") or intent.get("requires_collab"))
    domain: str = (intent.get("domain") or intent.get("topic") or "").lower().replace("-", "_").replace(" ", "_")
    needs_routing: bool = bool(intent.get("requires_specialist_routing"))

    if explicit_owner and explicit_owner in KNOWN_AGENTS and not requires_collab:
        return explicit_owner

    if domain in HERMES_PRIMARY_DOMAINS:
        return "hermes"

    if domain in KUBLAI_PRIMARY_DOMAINS:
        return "kublai"

    if needs_routing:
        return "kublai"

    if requires_collab and domain in HERMES_PRIMARY_DOMAINS:
        return "hermes"

    if requires_collab:
        return "kublai"

    return "kublai"


def select_support_agents(owner: str, intent: dict[str, Any]) -> list[str]:
    """Return the list of support agents for a collaborative request.

    For Tier 2/3 collaboration, the non-owner agent contributes internally.
    """
    requires_collab: bool = bool(intent.get("requires_collaboration") or intent.get("requires_collab"))
    tier: str = intent.get("tier", "tier1")
    is_collab_tier = requires_collab or tier in ("tier2", "tier2_shared_expertise", "tier3", "tier3_governance")
    if not is_collab_tier:
        return []
    if owner == "kublai":
        return ["hermes"]
    if owner == "hermes":
        return ["kublai"]
    return []


def score_claim(agent: str, intent: dict[str, Any]) -> int:
    """Return numeric claim priority score for an agent given this intent.

    Higher score = stronger claim. Used when two agents race to claim.
    """
    explicit_owner: str | None = intent.get("explicit_owner") or intent.get("preferred_owner")
    domain: str = (intent.get("domain") or "").lower().replace("-", "_").replace(" ", "_")

    if explicit_owner == agent:
        return CLAIM_PRIORITY["explicit_mentioned_owner"] + AGENT_TIEBREAK.get(agent, 0)

    if agent == "hermes" and domain in HERMES_PRIMARY_DOMAINS:
        return CLAIM_PRIORITY["domain_primary_owner"] + AGENT_TIEBREAK.get(agent, 0)

    if agent == "kublai" and domain in KUBLAI_PRIMARY_DOMAINS:
        return CLAIM_PRIORITY["domain_primary_owner"] + AGENT_TIEBREAK.get(agent, 0)

    requires_routing = bool(intent.get("requires_specialist_routing"))
    if agent == "kublai" and requires_routing:
        return CLAIM_PRIORITY["collaboration_default_aggregator"] + AGENT_TIEBREAK.get(agent, 0)

    requires_collab = bool(intent.get("requires_collaboration") or intent.get("requires_collab"))
    if requires_collab and agent == "kublai":
        return CLAIM_PRIORITY["collaboration_default_aggregator"] + AGENT_TIEBREAK.get(agent, 0)

    return CLAIM_PRIORITY["fallback_owner"] + AGENT_TIEBREAK.get(agent, 0)
