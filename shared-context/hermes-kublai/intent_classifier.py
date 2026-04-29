#!/usr/bin/env python3
from __future__ import annotations

"""Keyword-based intent classifier for Kublai/Hermes group-chat messages.

Returns a classification dict matching the canonical protocol schema.
This is a deterministic rule-based classifier; no LLM calls.
"""

import re
from typing import Any

HERMES_DOMAIN_KEYWORDS: dict[str, frozenset[str]] = {
    "system_health": frozenset({"health", "healthy", "status", "alive", "running", "uptime"}),
    "agent_malfunction": frozenset({"silent", "not responding", "broken", "crashed", "stuck", "hung", "malfunction", "down", "failing"}),
    "runtime_debugging": frozenset({"runtime", "error", "traceback", "exception", "debug", "diagnose", "investigate", "audit"}),
    "cron_hygiene": frozenset({"cron", "scheduled", "launchagent", "plist", "timer", "job", "sweep"}),
    "memory_maintenance": frozenset({"memory", "wiki", "knowledge", "brain", "notes", "index"}),
    "provider_debugging": frozenset({"provider", "llm", "fallback", "token", "quota", "rate limit", "api error"}),
    "kublai_repair": frozenset({"kublai is", "why is kublai", "kublai silent", "kublai not", "fix kublai", "repair kublai"}),
    "incident_response": frozenset({"incident", "outage", "failure mode", "recovery", "restore", "rollback", "revert"}),
}

KUBLAI_DOMAIN_KEYWORDS: dict[str, frozenset[str]] = {
    "routing": frozenset({"route", "routing", "why did", "routed to", "goes to"}),
    "queue_status": frozenset({"queue", "backlog", "pending", "in progress", "task list"}),
    "project_management": frozenset({"project", "sprint", "milestone", "priority", "planning", "roadmap"}),
    "specialist_delegation": frozenset({"delegate", "assign", "have .* do", "route to", "dispatch to", "ask .* to"}),
    "group_chat_behavior": frozenset({"group chat", "group protocol", "chat behavior", "answer in chat"}),
    "protocol_proposal": frozenset({"protocol", "policy", "propose", "proposal", "design", "architecture"}),
    "async_task_intake": frozenset({"create task", "new task", "queue task", "add task", "intake"}),
    "strategy": frozenset({"strategy", "what should we", "recommend", "decide", "plan", "approach"}),
}

TIER2_COLLAB_PATTERNS: list[str] = [
    r"kublai\s+and\s+hermes",
    r"hermes\s+and\s+kublai",
    r"\bboth\s+of\s+you\b",
    r"\bcollaborate\b",
    r"\bjoint\b",
    r"\btogether\b",
    r"\bconsensus\b",
    r"\bjointly\b",
    r"\bco-?write\b",
    r"\bcoordinate\b",
]

TIER3_RISK_KEYWORDS: frozenset[str] = frozenset({
    "deploy", "deployment", "delete", "destroy", "drop", "credential", "secret",
    "api key", "password", "token", "permission", "access control", "production",
    "disable", "rotate", "spend", "money", "billing", "cron", "scheduler",
    "policy decree", "binding decision", "irreversible", "rollout", "ramp",
})

EXPLICIT_AGENT_PATTERNS: dict[str, re.Pattern] = {
    "kublai": re.compile(r"\bkublai\b", re.IGNORECASE),
    "hermes": re.compile(r"\bhermes\b", re.IGNORECASE),
}


def extract_explicit_agents(text: str) -> list[str]:
    return [agent for agent, pat in EXPLICIT_AGENT_PATTERNS.items() if pat.search(text)]


def _is_collab_request(text: str) -> bool:
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in TIER2_COLLAB_PATTERNS)


def _has_tier3_risk(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in TIER3_RISK_KEYWORDS)


def _score_domain(text: str) -> tuple[str, str]:
    """Return (agent_bucket, domain_name) for the highest-scoring domain."""
    text_lower = text.lower()
    best_score = 0
    best_domain = ""
    best_bucket = "kublai"

    for domain, keywords in HERMES_DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > best_score:
            best_score = score
            best_domain = domain
            best_bucket = "hermes"

    for domain, keywords in KUBLAI_DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > best_score:
            best_score = score
            best_domain = domain
            best_bucket = "kublai"

    return best_bucket, best_domain


def classify_intent(
    text: str,
    reply_chain_context: str = "",
    root_message_id: str | None = None,
    is_followup: bool = False,
) -> dict[str, Any]:
    """Classify a Telegram message into the canonical intent object.

    Returns a dict matching the canonical protocol intent schema:
      should_respond, request_type, domain, tier, explicit_agents,
      requires_collaboration, requires_specialist_routing,
      requires_human_approval, preferred_owner, support_agents,
      urgency, risk_level, is_followup, root_message_id, scope_summary.
    """
    full_text = (text + " " + reply_chain_context).strip()
    explicit_agents = extract_explicit_agents(full_text)
    requires_collab = _is_collab_request(full_text)
    has_risk = _has_tier3_risk(full_text)
    _, domain = _score_domain(full_text)

    is_actionable = bool(explicit_agents) or requires_collab or bool(domain)

    if not is_actionable:
        return {
            "should_respond": False,
            "request_type": "observe",
            "domain": "",
            "tier": "mode_0_observe",
            "explicit_agents": [],
            "requires_collaboration": False,
            "requires_specialist_routing": False,
            "requires_human_approval": False,
            "preferred_owner": None,
            "support_agents": [],
            "urgency": "normal",
            "risk_level": "none",
            "is_followup": is_followup,
            "root_message_id": root_message_id,
            "scope_summary": text[:120],
        }

    if has_risk or (requires_collab and _contains_risk_verb(full_text)):
        tier = "tier_3_governance"
        risk_level = "high"
        requires_human_approval = True
    elif requires_collab or len(explicit_agents) >= 2:
        tier = "tier_2_shared_expertise"
        risk_level = "medium"
        requires_human_approval = False
    else:
        tier = "tier_1_routine"
        risk_level = "low"
        requires_human_approval = False

    requires_routing = _contains_routing_verb(full_text) and not requires_collab

    from agent_policy import select_owner, select_support_agents
    intent_draft: dict[str, Any] = {
        "explicit_owner": explicit_agents[0] if len(explicit_agents) == 1 and not requires_collab else None,
        "requires_collaboration": requires_collab,
        "domain": domain,
        "requires_specialist_routing": requires_routing,
    }
    preferred_owner = select_owner(intent_draft)
    support = select_support_agents(preferred_owner, {"requires_collaboration": requires_collab, "tier": tier})

    request_type = _infer_request_type(full_text, domain, requires_collab)

    return {
        "should_respond": True,
        "request_type": request_type,
        "domain": domain,
        "tier": tier,
        "explicit_agents": explicit_agents,
        "requires_collaboration": requires_collab,
        "requires_specialist_routing": requires_routing,
        "requires_human_approval": requires_human_approval,
        "preferred_owner": preferred_owner,
        "support_agents": support,
        "urgency": "normal",
        "risk_level": risk_level,
        "is_followup": is_followup,
        "root_message_id": root_message_id,
        "scope_summary": text[:120],
    }


def _contains_risk_verb(text: str) -> bool:
    risk_verbs = frozenset({"deploy", "delete", "disable", "destroy", "rotate", "send to", "change", "modify"})
    text_lower = text.lower()
    return any(v in text_lower for v in risk_verbs)


def _contains_routing_verb(text: str) -> bool:
    routing_verbs = frozenset({"have .* do", "route to", "ask .* to", "delegate", "assign to", "create task"})
    text_lower = text.lower()
    return any(re.search(v, text_lower) for v in routing_verbs)


def _infer_request_type(text: str, domain: str, requires_collab: bool) -> str:
    text_lower = text.lower()
    if requires_collab:
        return "collaboration_request"
    if domain in ("routing", "queue_status"):
        return "routing_question"
    if domain in ("system_health", "agent_malfunction", "runtime_debugging", "cron_hygiene"):
        return "health_check"
    if domain in ("protocol_proposal", "group_chat_behavior", "group_chat_protocol"):
        return "protocol_design"
    if domain in ("project_management", "specialist_delegation", "async_task_intake"):
        return "task_management"
    if "why" in text_lower:
        return "explanation_request"
    if "?" in text:
        return "question"
    return "general_request"
