#!/usr/bin/env python3
"""
Context Formatter — Structures assembled context into LLM-ready prompt sections.

Takes raw context from ContextAssembler and formats it into coherent
sections suitable for system/user prompt injection.

Usage:
    from context_formatter import format_context
    formatted = format_context(assembled_context)
    # Returns dict with: identity_preamble, topic_map, narrative_thread,
    #                     predicted_context, social_context, conversation_history
"""

import logging
from typing import Dict, Any, List, Optional
from token_budget import TokenBudget

logger = logging.getLogger(__name__)


def format_context(
    context: Dict[str, Any],
    max_tokens: int = 4000,
) -> Dict[str, str]:
    """Format assembled context into LLM-ready prompt sections.

    Args:
        context: Raw context from ContextAssembler.assemble()
        max_tokens: Total token budget

    Returns:
        Dict of section_name → formatted text
    """
    budget = TokenBudget(max_tokens)
    sections = {}

    # 1. Identity Preamble
    profile = context.get("profile") or {}
    identity = _format_identity(profile, context.get("core_topics", []))
    sections["identity_preamble"] = budget.allocate("identity_preamble", identity)

    # 2. Social Context
    social = _format_social(context.get("social_context", []))
    sections["social_context"] = budget.allocate("social_context", social)

    # 3. Topic Map
    topic_map = _format_topic_map(
        context.get("core_topics", []),
        context.get("communities", []),
        context.get("bridge_topics", []),
    )
    sections["topic_map"] = budget.allocate("topic_map", topic_map)

    # 4. Narrative Thread (drift + active items)
    narrative = _format_narrative(
        context.get("drift_signals", []),
        context.get("action_items", []),
    )
    sections["narrative"] = budget.allocate("narrative", narrative)

    # 5. Active Items
    items = _format_action_items(context.get("action_items", []))
    sections["active_items"] = budget.allocate("active_items", items)

    # 6. Current Thread (elastic)
    thread = _format_thread(context.get("thread_messages", []))
    sections["current_thread"] = budget.allocate_elastic("current_thread", thread)

    # 6b. Group Recent Messages (elastic, group chats only)
    group_recent = _format_group_recent(context.get("group_recent_messages", []))
    if group_recent:
        sections["group_recent"] = budget.allocate_elastic("group_recent", group_recent)

    # 7. Semantic Matches (elastic, fills rest)
    matches = _format_semantic_matches(context.get("similar_messages", []))
    sections["semantic_matches"] = budget.allocate_elastic("semantic_matches", matches)

    # Budget report
    sections["_budget"] = str(budget.get_report())

    return sections


def _format_identity(profile: Dict, core_topics: List[Dict]) -> str:
    """Format identity preamble."""
    name = profile.get("displayName", "Unknown")
    source = profile.get("source", "unknown")
    first_known = profile.get("firstKnown", "unknown")

    lines = [f"Conversing with: {name} (via {source}, known since {first_known})"]

    if core_topics:
        top_labels = [t["label"] for t in core_topics[:5]]
        lines.append(f"Core interests: {', '.join(top_labels)}")

    identifiers = profile.get("identifiers", [])
    for ident in identifiers[:3]:
        lines.append(f"  {ident['type']}: {ident['value']}")

    return "\n".join(lines)


def _format_social(social: List[Dict]) -> str:
    """Format social context."""
    if not social:
        return "No known connections."

    lines = ["Known connections:"]
    for conn in social[:5]:
        name = conn.get("name", "?")
        rel_type = conn.get("relType", "KNOWN_THROUGH")
        ctx = conn.get("context", "")
        lines.append(f"  - {name} ({rel_type}: {ctx})")

    return "\n".join(lines)


def _format_topic_map(
    core: List[Dict], communities: List[Dict], bridges: List[Dict]
) -> str:
    """Format topic map with communities and bridges."""
    lines = []

    if core:
        lines.append("Core topics (by importance):")
        for t in core[:7]:
            score = t.get("score", 0)
            domain = t.get("domain", "")
            mentions = t.get("mentions", 0)
            lines.append(f"  - {t['label']} [{domain}] (score:{score:.2f}, mentions:{mentions})")

    if communities:
        lines.append("\nTopic clusters:")
        for c in communities[:3]:
            topics = c.get("topics", [])[:5]
            lines.append(f"  Cluster: {', '.join(topics)}")

    if bridges:
        bridge_labels = [b["label"] for b in bridges[:3]]
        lines.append(f"\nBridge topics: {', '.join(bridge_labels)}")

    return "\n".join(lines) if lines else "No topic data yet."


def _format_narrative(
    drift: List[Dict], action_items: List[Dict]
) -> str:
    """Format narrative thread with drift signals."""
    lines = []

    if drift:
        rising = [d for d in drift if d.get("signal") == "rising"]
        fading = [d for d in drift if d.get("signal") == "fading"]

        if rising:
            labels = [d["topic"] for d in rising[:3]]
            lines.append(f"Rising interests: {', '.join(labels)}")
        if fading:
            labels = [d["topic"] for d in fading[:3]]
            lines.append(f"Fading interests: {', '.join(labels)}")

    return "\n".join(lines) if lines else ""


def _format_action_items(items: List[Dict]) -> str:
    """Format active action items."""
    if not items:
        return ""

    lines = ["Open action items:"]
    for item in items[:5]:
        priority = item.get("priority", "medium")
        desc = item.get("description", "")
        assignee = item.get("assignee", "")
        prefix = "!" if priority == "high" else "-"
        line = f"  {prefix} {desc}"
        if assignee:
            line += f" (assigned: {assignee})"
        lines.append(line)

    return "\n".join(lines)


def _format_thread(messages: List[Dict]) -> str:
    """Format current thread messages."""
    if not messages:
        return "No active conversation."

    lines = ["Recent conversation:"]
    for msg in reversed(messages[:15]):  # Show oldest first
        direction = "→" if msg.get("direction") == "outbound" else "←"
        text = msg.get("text") or msg.get("summary") or "(no content)"
        ts = msg.get("timestamp", "")[:19]
        lines.append(f"  {direction} [{ts}] {text[:200]}")

    return "\n".join(lines)


def _format_group_recent(messages: List[Dict]) -> str:
    """Format recent messages from other group members (shared context)."""
    if not messages:
        return ""

    lines = ["Recent group messages (from others):"]
    for msg in reversed(messages[:10]):  # Show oldest first
        sender = msg.get("sender", "Unknown")
        direction = "→" if msg.get("direction") == "outbound" else "←"
        text = msg.get("text") or msg.get("summary") or "(no content)"
        ts = msg.get("timestamp", "")[:19]
        lines.append(f"  {direction} [{ts}] {sender}: {text[:200]}")

    return "\n".join(lines)


def _format_semantic_matches(matches: List[Dict]) -> str:
    """Format semantically similar past messages."""
    if not matches:
        return ""

    lines = ["Relevant past messages:"]
    for msg in matches[:7]:
        text = msg.get("text") or msg.get("summary") or ""
        score = msg.get("score", 0)
        ts = msg.get("timestamp", "")[:10]
        direction = "→" if msg.get("direction") == "outbound" else "←"
        lines.append(f"  {direction} [{ts}] (sim:{score:.2f}) {text[:150]}")

    return "\n".join(lines)


if __name__ == "__main__":
    # Demo with mock context
    mock = {
        "profile": {"displayName": "Danny", "source": "signal", "firstKnown": "2026-01-15"},
        "core_topics": [
            {"label": "deployment", "domain": "technical", "score": 0.85, "mentions": 12},
            {"label": "authentication", "domain": "technical", "score": 0.72, "mentions": 8},
        ],
        "communities": [{"communityId": 1, "topics": ["deployment", "docker", "ci/cd"]}],
        "bridge_topics": [{"label": "security", "score": 3.2}],
        "drift_signals": [{"signal": "rising", "topic": "kubernetes"}],
        "thread_messages": [
            {"text": "How's the deploy going?", "direction": "inbound", "timestamp": "2026-03-19T10:00:00"},
            {"text": "All green, pushed to prod", "direction": "outbound", "timestamp": "2026-03-19T10:05:00"},
        ],
        "similar_messages": [],
        "social_context": [{"name": "Liz", "relType": "KNOWN_THROUGH", "context": "mentioned in conversation"}],
        "action_items": [{"description": "Review PR #42", "priority": "high", "assignee": "Danny"}],
    }

    formatted = format_context(mock)
    for section, text in formatted.items():
        if section.startswith("_"):
            continue
        print(f"\n--- {section} ---")
        print(text or "(empty)")
