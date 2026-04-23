#!/usr/bin/env python3
"""
Conversational Responder — Generates LLM responses using graph context.

Uses assembled context from the conversational memory system to produce
contextually rich responses. Routes through local Ollama (qwen3.5:9b)
with OpenRouter fallback.

Usage:
    from conversational_responder import generate_response
    response = generate_response(human_id, message_text)
"""
from __future__ import annotations

import os
import sys
import json
import time
import logging
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from context_assembler import assemble_context
from context_formatter import format_context
from engagement_assessor import assess_engagement
from pii_scrubber import PIIScrubber

logger = logging.getLogger(__name__)

# ============================================================================
# Credential loading from vault (~/.openclaw/credentials/provider.env)
# ============================================================================
_vault = None

def _load_vault():
    """Load LLM credentials from the Kurultai credential vault."""
    global _vault
    if _vault is not None:
        return _vault

    _vault = {}
    vault_file = os.path.expanduser("~/.openclaw/credentials/provider.env")
    if os.path.exists(vault_file):
        with open(vault_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    _vault[key.strip()] = value.strip()

    # Also check openrouter.env for backward compat
    or_file = os.path.expanduser("~/.openclaw/credentials/openrouter.env")
    if os.path.exists(or_file) and "OPENROUTER_API_KEY" not in _vault:
        with open(or_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("OPENROUTER_API_KEY="):
                    _vault["OPENROUTER_API_KEY"] = line.split("=", 1)[1].strip()

    return _vault


_SOUL_PATH = os.path.expanduser("~/.openclaw/agents/main/SOUL.md")
_AGENTS_PATH = os.path.expanduser("~/.openclaw/agents/main/AGENTS.md")
_KNOWLEDGE_DIR = os.path.expanduser("~/.openclaw/agents/main/knowledge")
_soul_cache = None

# Max bytes of knowledge base content to include in system prompt.
# Budget for smaller models (qwen3.5:9b context ~32k tokens).
_KB_MAX_BYTES = 6000


def _load_knowledge_base() -> str:
    """Load key knowledge base docs for grounded architecture answers.

    Loads the 'Common Agent Infrastructure' section from agent-roster.md
    which documents ASMR, task execution, context profiles, and directory
    structure. This prevents confabulation when answering architecture
    questions about the Kurultai system.
    """
    roster_path = os.path.join(_KNOWLEDGE_DIR, "agent-roster.md")
    if not os.path.exists(roster_path):
        return ""

    try:
        with open(roster_path) as f:
            content = f.read()
    except OSError:
        return ""

    # Extract the "Common Agent Infrastructure" section — this has ASMR,
    # task execution, context profile, and directory structure docs.
    marker = "## Common Agent Infrastructure"
    if marker not in content:
        return ""

    section = content[content.index(marker):]

    # Truncate to budget
    if len(section) > _KB_MAX_BYTES:
        section = section[:_KB_MAX_BYTES].rsplit("\n", 1)[0] + "\n..."

    return "\n\n## System Knowledge (from agent-roster.md)\n\n" + section


def _load_soul() -> str:
    """Load SOUL.md + agent roster + knowledge base, cached after first read."""
    global _soul_cache
    if _soul_cache is not None:
        return _soul_cache

    parts = []

    # Load SOUL.md
    if os.path.exists(_SOUL_PATH):
        with open(_SOUL_PATH) as f:
            parts.append(f.read())

    # Load agent classification table from AGENTS.md
    if os.path.exists(_AGENTS_PATH):
        with open(_AGENTS_PATH) as f:
            content = f.read()
        # Extract just the classification guide section
        if "## Classification Guide" in content:
            section = content.split("## Classification Guide")[1]
            # Take until the next major section
            if "\n## " in section[5:]:
                section = section[:section.index("\n## ", 5)]
            parts.append("## Classification Guide" + section)

    # Load knowledge base docs so architecture answers are grounded
    kb = _load_knowledge_base()
    if kb:
        parts.append(kb)

    _soul_cache = "\n\n".join(parts) if parts else ""
    return _soul_cache


SIGNAL_ADDENDUM = """
## Signal Chat Guidelines
You are responding via Signal messenger. Adapt your SOUL.md personality for chat:
- Be direct, confident, and concise. No filler.
- Keep responses brief (1-3 sentences for casual chat, longer for substantive questions)
- Use the context below to personalize responses — reference past conversations naturally
- When someone asks you to do work: acknowledge it and say you're routing it to the specialist
- Don't mention "graph" or "database" or "embedding" — just use the knowledge naturally

## Epistemic Guardrail
When answering questions about Kurultai systems, scripts, or architecture:
- ONLY state facts that appear in the System Knowledge section above or in the context below.
- If the information is NOT in your system prompt or context, say: "I'd need to check the source code for details on that — let me route it to the right agent."
- NEVER invent technical details (file purposes, cron schedules, data formats) that you cannot cite from the loaded knowledge.
- Acronyms: ASMR = Adaptive Structured Memory Representation (NOT Autonomous Sensory Meridian Response).

{context}"""


GROUP_ADDENDUM = """
## Signal Group Chat Guidelines
You are responding in a Signal GROUP CHAT visible to ALL members.

### PRIVACY RULES (MANDATORY)
1. NEVER reference any private DM conversations
2. NEVER mention health, finances, relationships, or personal struggles
3. If someone asks about a private topic, reply: "Let's discuss that in a DM"
4. You may reference topics the person has discussed IN THIS GROUP only
5. Do NOT reveal phone numbers, file paths, UUIDs, or credentials

### RESPONSE RULES
- Keep responses concise (1-3 sentences, max 500 chars)
- Be helpful but general
- Don't mention "graph" or "database" or "embedding" — just use the knowledge naturally

### Group Context
{context}"""


def _build_system_prompt(context_block: str) -> str:
    """Build the full system prompt from SOUL.md + context."""
    soul = _load_soul()
    addendum = SIGNAL_ADDENDUM.format(context=context_block)
    return soul + "\n\n" + addendum


def _build_group_system_prompt(context_block: str) -> str:
    """Build group-safe system prompt from SOUL.md + group addendum."""
    soul = _load_soul()
    addendum = GROUP_ADDENDUM.format(context=context_block)
    return soul + "\n\n" + addendum


def generate_response(
    human_id: str,
    message_text: str,
    sender_name: str = "",
    engagement_decision: dict = None,
    message_id: str = None,
    group_mode: bool = False,
    group_id: str = None,
) -> str:
    """Generate a conversational response using graph context.

    Args:
        human_id: UUID of the Human
        message_text: Incoming message text
        sender_name: Display name of the sender
        engagement_decision: Pre-computed engagement decision (optional)
        message_id: UUID of the ingested Message node (for engagement persistence)
        group_mode: True if message is from a group chat
        group_id: Group identifier (enables scoped context assembly)

    Returns:
        Response text, or None if engagement says "silent"
    """
    t0 = time.monotonic()

    is_group = group_mode or bool(group_id)

    # Get engagement decision if not provided
    if engagement_decision is None:
        engagement_decision = assess_engagement(
            human_id, message_text, is_group=is_group,
        )

    # Persist engagement decision on the Message node
    if message_id and engagement_decision:
        try:
            from engagement_learner import store_engagement_decision
            store_engagement_decision(message_id, human_id, engagement_decision)
        except Exception as e:
            logger.debug(f"Engagement storage failed: {e}")

    # Check if we should respond
    decision = engagement_decision.get("decision", "respond")
    if decision == "silent":
        logger.info(f"Engagement: silent for {human_id[:8]} — not responding")
        return None

    # Build system prompt — group vs DM path
    if is_group:
        if group_id:
            # Full group pipeline: scoped context assembly
            ctx = assemble_context(human_id, message_text, group_id=group_id)
            formatted = format_context(ctx)
            context_parts = []
            for section in ["identity_preamble", "social_context", "topic_map",
                             "active_items", "current_thread", "group_recent",
                             "semantic_matches"]:
                text = formatted.get(section, "")
                if text and len(text) > 10:
                    context_parts.append(f"## {section.replace('_', ' ').title()}\n{text}")
            context_block = "\n\n".join(context_parts) if context_parts else "(Group chat — no group-specific context yet)"
        else:
            # Emergency fallback: no group_id, zero context
            ctx = {}
            context_block = "(Group chat — no personal context loaded)"
        system = _build_group_system_prompt(context_block)
    else:
        # Standard DM path — V2 structured profile or V1 flat context
        # V2 toggle: check env var OR config file
        _v2_enabled = os.environ.get("CONTEXT_PROFILE_V2") == "true"
        if not _v2_enabled:
            _v2_flag = os.path.expanduser("~/.openclaw/context_profile_v2.enabled")
            _v2_enabled = os.path.exists(_v2_flag)
        if _v2_enabled:
            try:
                from context_profile import build_context_profile
                context_block = build_context_profile(
                    human_id, message_text,
                    scope='dm', has_thread=False)
                if not context_block:
                    context_block = "(No prior context — first interaction)"
                # V2 builds its own ctx dict for downstream compatibility
                ctx = assemble_context(human_id, message_text)
            except Exception as e:
                logger.error(f"Context Profile V2 failed, falling back to V1: {e}")
                ctx = assemble_context(human_id, message_text)
                formatted = format_context(ctx)
                context_parts = []
                for section in ["identity_preamble", "social_context", "topic_map",
                                 "active_items", "current_thread", "semantic_matches"]:
                    text = formatted.get(section, "")
                    if text and len(text) > 10:
                        context_parts.append(f"## {section.replace('_', ' ').title()}\n{text}")
                context_block = "\n\n".join(context_parts) if context_parts else "(No prior context — first interaction)"
        else:
            ctx = assemble_context(human_id, message_text)
            formatted = format_context(ctx)
            context_parts = []
            for section in ["identity_preamble", "social_context", "topic_map",
                             "active_items", "current_thread", "semantic_matches"]:
                text = formatted.get(section, "")
                if text and len(text) > 10:
                    context_parts.append(f"## {section.replace('_', ' ').title()}\n{text}")
            context_block = "\n\n".join(context_parts) if context_parts else "(No prior context — first interaction)"
        system = _build_system_prompt(context_block)

    # Determine response depth from engagement decision
    depth = engagement_decision.get("depth", "standard")
    if depth == "brief" or depth == "acknowledgment":
        system += "\n\nKeep this response very brief — one sentence max."

    # Scrub PII before external LLM calls (message + context block)
    _names = set()
    if ctx.get("profile", {}).get("displayName"):
        _names.add(ctx["profile"]["displayName"])
    for ident in ctx.get("profile", {}).get("identifiers", []):
        if ident.get("type") == "NAME_VARIANT" and ident.get("value"):
            _names.add(ident["value"])
    _scrubber = PIIScrubber(known_names=_names) if _names else PIIScrubber()
    message_scrubbed, _ = _scrubber.scrub(message_text)
    context_block, _ = _scrubber.scrub(context_block)

    # Try providers in agent config order: agent-configured → Z.AI → Ollama → rule-based
    response = _try_agent_model(system, message_scrubbed, sender_name)
    if not response:
        response = _try_zai(system, message_scrubbed, sender_name)
    if not response:
        response = _try_ollama(system, message_scrubbed, sender_name)
    if not response:
        response = _fallback_response(message_text, sender_name, ctx)

    # Apply response guard for group messages
    if is_group:
        response = _guard_group_response(response)

    elapsed = (time.monotonic() - t0) * 1000
    logger.info(f"Response generated for {human_id[:8]} in {elapsed:.0f}ms ({len(response)} chars, {'group' if is_group else 'dm'})")

    return response


def _guard_group_response(response: str) -> str:
    """Post-generation filter for group responses — blocks PII and enforces length."""
    try:
        from response_guard import guard_response
        return guard_response(response, is_group=True)
    except ImportError:
        # response_guard unavailable — fail safe for group messages
        logger.warning("ResponseGuard import failed — using safe fallback for group response")
        return "Let's discuss that in a DM."


def _try_agent_model(system: str, message: str, sender_name: str) -> str:
    """Try the model configured for Kublai agent in settings.json."""
    import json as _json
    settings_path = os.path.expanduser("~/.openclaw/agents/kublai/.claude/settings.json")
    try:
        with open(settings_path) as f:
            settings = _json.load(f)
        env = settings.get("env", {})
        model = env.get("ANTHROPIC_MODEL")
        base_url = env.get("ANTHROPIC_BASE_URL")
        auth_token = env.get("ANTHROPIC_AUTH_TOKEN")

        if not model or not base_url:
            return None

        # If no token in agent settings, try vault
        if not auth_token:
            vault = _load_vault()
            if "dashscope" in base_url:
                auth_token = vault.get("ALIBABA_AUTH_TOKEN")
            elif "z.ai" in base_url:
                auth_token = vault.get("ZAI_AUTH_TOKEN")

        if not auth_token:
            return None

        result = _call_anthropic_api(base_url, auth_token, system, message, sender_name, model=model)
        if result:
            logger.info(f"Response via agent model ({model})")
        return result
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.warning(f"Agent model failed: {e}")
        return None


def _strip_internal_thinking(text: str) -> str:
    """Strip internal thinking/reasoning from model responses.

    Handles multiple formats:
    1. Explicit thinking tags ( Malay/</think/etc)
    2. Internal monologue patterns that precede actual responses
    3. Models that include reasoning without proper block separation

    Pattern detected in glm-5: internal reasoning followed by actual response,
    e.g., "Good, the script...Now I can respond.Hello."
    """
    if not text:
        return text

    # 1. Strip explicit thinking tags (various formats)
    thinking_patterns = [
        r"<think[^>]*>.*?</think\s*>",  # XML-style <think...</think >
        r" Malay.*?```",                # Markdown code block style
        r"\[THINKING\].*?\[/THINKING\]",  # Bracketed style
        r"\{thinking\}.*?\{/thinking\}",  # Brace style
    ]
    for pattern in thinking_patterns:
        text = re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE)

    text = text.strip()

    # 2. Detect internal monologue transition patterns
    # Pattern: reasoning text followed by transition phrase, then actual response
    # Example: "...Now I can respond to Danny.Hello. Good to hear from you."
    # FIX 2026-03-22: Match full transition sentence (up to period) to prevent
    # partial reasoning like "to Dannys greeting." from leaking through.
    transition_patterns = [
        # Match transition phrase + rest of sentence up to period
        r"^.*?(?:Now I can respond|I will now respond|Let me respond|I should respond|Now responding|My response:|Final response:|Response:)[^.]*\.\s*",
        # Match internal task marker + full sentence (handles both period and comma)
        r"^.*?(?:This is an internal task|Internal reasoning|Internal note|Note to self:|Self:)[.,].*?\.\s*",
    ]

    for pattern in transition_patterns:
        match = re.match(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            # Extract just the part after the transition
            remaining = text[match.end():].strip()
            if remaining and len(remaining) < len(text) * 0.7:  # Significant reduction
                text = remaining
                break

    # 3. Final cleanup: remove leading/trailing whitespace and common artifacts
    text = text.strip()

    # Remove any "Good," "OK," "Alright," etc. at start that might be reasoning remnants
    text = re.sub(r"^(?:Good|OK|Alright|Right|Sure),?\s+(?:the|this|I|so|now)\s+[^.]+\.\s*", "", text, flags=re.IGNORECASE)

    return text.strip()


def _call_anthropic_api(base_url: str, auth_token: str, system: str,
                         message: str, sender_name: str, model: str = "claude-sonnet-4-6") -> str:
    """Call an Anthropic-compatible API (Z.AI, Alibaba, or native Anthropic)."""
    import requests
    user_msg = f"[{sender_name}]: {message}" if sender_name else message

    resp = requests.post(
        f"{base_url}/v1/messages",
        headers={
            "x-api-key": auth_token,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 300,
            "system": system,
            "messages": [{"role": "user", "content": user_msg}],
        },
        timeout=30,
    )

    if resp.status_code == 200:
        data = resp.json()
        content = data.get("content", [])
        if content and isinstance(content, list):
            # First: try to find a dedicated text block (skip thinking blocks)
            for block in content:
                if block.get("type") == "thinking":
                    continue  # Explicit thinking block - skip
                if block.get("type") == "text":
                    text = block.get("text", "").strip()
                    if text:
                        # Strip any internal thinking that leaked into text
                        return _strip_internal_thinking(text)

            # Fallback: try first block's text field (but still strip thinking)
            if content:
                text = content[0].get("text", "").strip()
                if text:
                    return _strip_internal_thinking(text)
    return None


def _try_zai(system: str, message: str, sender_name: str) -> str:
    """Try Z.AI (Fallback Tier 1 — glm-5, Anthropic-compatible)."""
    vault = _load_vault()
    token = vault.get("ZAI_AUTH_TOKEN")
    base_url = vault.get("ZAI_BASE_URL")
    if not token or not base_url:
        return None

    try:
        result = _call_anthropic_api(base_url, token, system, message, sender_name)
        if result:
            logger.info("Response via Z.AI")
        return result
    except Exception as e:
        logger.warning(f"Z.AI failed: {e}")
        return None


def _try_alibaba(system: str, message: str, sender_name: str) -> str:
    """Try Alibaba/DashScope (Fallback Tier 2 — qwen3.5-plus, Anthropic-compatible)."""
    vault = _load_vault()
    token = vault.get("ALIBABA_AUTH_TOKEN")
    base_url = vault.get("ALIBABA_BASE_URL")
    if not token or not base_url:
        return None

    try:
        result = _call_anthropic_api(base_url, token, system, message, sender_name)
        if result:
            logger.info("Response via Alibaba/DashScope")
        return result
    except Exception as e:
        logger.warning(f"Alibaba failed: {e}")
        return None


def _try_ollama(system: str, message: str, sender_name: str) -> str:
    """Try local Ollama qwen3.5:9b (last resort before rule-based)."""
    try:
        import requests
        user_msg = f"[{sender_name}]: {message}" if sender_name else message

        resp = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "qwen3.5:9b",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 300},
            },
            timeout=45,
        )

        if resp.status_code == 200:
            text = resp.json().get("message", {}).get("content", "")
            text = text.strip()
            # Strip thinking tags (qwen3.5 sometimes wraps in <think>)
            if "<think>" in text:
                think_end = text.rfind("</think>")
                if think_end >= 0:
                    text = text[think_end + 8:].strip()
            # Apply general internal thinking stripping (consistent with other providers)
            text = _strip_internal_thinking(text)
            if text:
                logger.info("Response via Ollama qwen3.5:9b")
            return text if text else None

    except Exception as e:
        logger.warning(f"Ollama response generation failed: {e}")
    return None


def _fallback_response(message: str, sender_name: str, ctx: dict) -> str:
    """Simple rule-based fallback when all LLMs are unavailable."""
    text = message.strip().lower()
    name = sender_name or "there"

    if any(g in text for g in ["hello", "hi", "hey", "morning", "evening", "afternoon"]):
        return f"Hey {name}! What's on your mind?"

    if "?" in message:
        return f"Good question. Let me look into that — I'll get back to you shortly."

    if any(w in text for w in ["thanks", "thank you", "thx", "cheers"]):
        return "Anytime!"

    return f"Got it, {name}. Let me know if you need anything."


def detect_task_escalation(response: str) -> bool:
    """Check if Kublai's response indicates it wants to route a task.

    Returns True if the response mentions routing to an agent,
    which means signal_message_handler should create an actual task.
    """
    escalation_signals = [
        "route", "routing", "routed to",
        "i'll have temujin", "i'll have mongke", "i'll have chagatai",
        "i'll have jochi", "i'll have ogedei",
        "i'll ask temujin", "i'll ask mongke",
        "let me route", "let me assign",
        "i'll get the team on",
    ]
    lower = response.lower()
    return any(sig in lower for sig in escalation_signals)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("human_id")
    parser.add_argument("message")
    parser.add_argument("--name", default="")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    response = generate_response(args.human_id, args.message, args.name)
    print(f"Response: {response}")
