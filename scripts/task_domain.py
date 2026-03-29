#!/usr/bin/env python3
"""
task_domain.py — Domain classification system for Kurultai task routing.

Extracted from task_intake.py for maintainability.

Usage:
    from task_domain import classify_task_domain, is_domain_compatible, validate_agent_model
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kurultai_paths import VALID_AGENTS

# =============================================================================
# Domain Classification System
# =============================================================================

# Domain-to-agent compatibility matrix for redistribution
# Agents listed can receive tasks of that domain via load balancing or redistribution
# Updated 2026-03-11: Removed tolui (uses ollama executor, not dispatch-capable)
DOMAIN_AGENT_COMPATIBILITY = {
    "research": ["mongke", "jochi"],
    "implementation": ["temujin", "ogedei", "jochi"],
    "ops": ["ogedei", "temujin", "jochi"],
    "documentation": ["chagatai", "mongke"],
    "strategy": ["temujin", "ogedei", "chagatai"],  # chagatai for strategic documentation/proposals
    "analysis": ["jochi", "mongke", "ogedei"],
    "autoresearch": ["mongke", "jochi", "chagatai"],
    "completion": ["jochi", "ogedei", "temujin"],
    "escalation": ["ogedei", "jochi", "temujin"],  # ogedei handles escalation (ops domain)
}

# Valid task domains - derived from DOMAIN_AGENT_COMPATIBILITY keys for single source of truth
VALID_DOMAINS = set(DOMAIN_AGENT_COMPATIBILITY.keys())

# Skill hint to domain mapping for classification
SKILL_DOMAIN_MAP = {
    # Research skills
    "/horde-learn": "research",
    # Implementation skills
    "/horde-implement": "implementation",
    "/horde-debug": "implementation",
    # Strategy skills
    "/horde-brainstorming": "strategy",
    "/horde-plan": "strategy",
    # Analysis skills
    "/horde-review": "analysis",
    "/code-reviewer": "analysis",
    "/systematic-debugging": "implementation",  # Changed 2026-03-14: Debugging/fixing is implementation work
    # Ops skills
    "/kurultai-health": "ops",
    "/dev-deploy": "ops",
    # Documentation skills
    "/content-research-writer": "documentation",
    # Autoresearch skills
    "/autoresearch": "autoresearch",
    # Parse project context skills
    "/parsethe-media": "implementation",
    "/parse-for-agents": "implementation",
}

# Domain classification by keyword matching (fallback when no skill hint)
DOMAIN_KEYWORDS = {
    "research": [
        "research", "discover", "competitor", "market", "study", "benchmark",
        "survey", "literature", "paper", "citation", "documentation research",
        "api discovery", "product analysis", "feature analysis", "pricing research",
        "ecosystem", "alternatives", "comparison", "market intel", "source triangulation",
        "fact check", "investigate sources", "data gathering", "research methodology",
        "evidence",
        # AI/LLM research terms (2026-03-11) — model providers, comparisons, benchmarks
        "llm", "gpt", "claude", "anthropic", "openai", "alibaba", "z.ai", "dashscope",
        "model comparison", "ai model", "language model", "embedding", "vector", "rag",
        "model benchmark", "ai pricing", "api pricing comparison", "provider comparison",
        "model research", "ai research", "llm evaluation", "model capabilities"
    ],
    "implementation": [
        "implement", "build", "create", "fix", "code", "develop", "scaffold",
        "deploy", "refactor", "migrate", "integrate", "bug", "feature"
    ],
    "ops": [
        "monitor", "restart", "health", "backup", "pipeline", "queue", "docker",
        "container", "railway", "infrastructure", "server", "cron", "cleanup"
    ],
    "documentation": [
        "document", "write", "blog", "readme", "changelog", "content", "guide",
        "tutorial", "article", "post", "draft", "edit"
    ],
    "strategy": [
        "design", "plan", "architect", "brainstorm", "strategy", "roadmap",
        "proposal", "evaluate approach", "decision", "prioritize"
    ],
    "analysis": [
        "review", "audit", "verify", "test", "security", "performance", "qa",
        "inspect", "assess", "quality", "compliance", "risk",
        "triage"  # 2026-03-13: Enable redistribution of stalled-agent tasks to mongke
    ],
    "autoresearch": [
        "autoresearch", "auto research", "autonomous research", "auto-investigate",
        "autonomous investigate", "auto-discover", "autonomous discover"
    ],
    "completion": [
        "fix-resolution", "completion gate", "gate-passed", "task-complete",
        "resolution", "resolve", "completion", "finalize", "finish"
    ],
    "escalation": [
        "escalate", "escalation", "stale task", "stuck task", "unblock",
        "watchdog", "emergency", "timeout", "stall", "stalled", "deadlock"
    ],
}


def classify_task_domain(task_text, skill_hint=None):
    """Classify task into domain based on skill hints and keywords.

    Args:
        task_text: Task title or body text
        skill_hint: Optional skill hint (takes precedence over keywords)

    Returns:
        Domain string: "research", "implementation", "ops", "documentation", "strategy", "analysis", "completion", "escalation", or "autoresearch"
    """
    # Special case: Fix tasks should always be implementation, regardless of skill hint
    # This prevents /code-reviewer from routing fix tasks to analysis domain
    task_lower = task_text.lower()
    _fix_keywords = {"fix", "bug", "debug", "patch", "resolve error", "resolve issue"}
    if any(kw in task_lower for kw in _fix_keywords):
        # Fix tasks are implementation by default - only override if explicitly analysis-only
        # Check if this is purely an analysis task (not a fix)
        _analysis_only_keywords = {"review", "audit", "analyze", "assess", "verify", "inspect", "triage"}
        _has_analysis_kw = any(kw in task_lower for kw in _analysis_only_keywords)
        _has_fix_kw = any(kw in task_lower for kw in _fix_keywords)

        # If it has both analysis and fix keywords, prioritize fix (implementation)
        if _has_fix_kw:
            return "implementation"

    # 1. Skill hint takes precedence
    if skill_hint and skill_hint in SKILL_DOMAIN_MAP:
        return SKILL_DOMAIN_MAP[skill_hint]

    # 2. Keyword-based classification
    scores = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in task_lower)
        if score > 0:
            scores[domain] = score

    if scores:
        best_domain = max(scores.items(), key=lambda x: x[1])
        return best_domain[0]

    # 3. Default to implementation (most common for dev agents)
    return "implementation"


def is_domain_compatible(domain, target_agent):
    """Check if an agent can handle tasks of a given domain.

    Args:
        domain: Task domain string
        target_agent: Agent name to check

    Returns:
        True if agent is compatible with the domain
    """
    if domain not in DOMAIN_AGENT_COMPATIBILITY:
        return False
    return target_agent in DOMAIN_AGENT_COMPATIBILITY[domain]


# Valid models for agent dispatch — derived from canonical agents_config.AGENT_MODELS.
# All agents run claude-opus-4-6 via Claude Code. Third-party models in models.json
# are for experimentation only and should NOT appear here.
# Note: tolui excluded (uses ollama executor, not dispatch-capable)
from agents_config import AGENT_MODELS as _CANONICAL_MODELS
VALID_MODELS_BY_AGENT = {
    agent: {model} for agent, model in _CANONICAL_MODELS.items()
    if agent != "tolui"  # Exclude tolui from dispatch validation
}


def validate_agent_model(agent):
    """Validate that an agent has a properly configured model.

    Returns (is_valid, actual_model, error_msg)

    Note: All agents execute via Claude Code (claude-opus-4-6) regardless of
    the model field in openclaw.json. The openclaw.json model field is for the
    OpenClaw gateway/alternative providers, not for Claude Code task execution.
    Validation compares against agents_config.AGENT_MODELS (canonical source).
    """
    try:
        canonical_model = _CANONICAL_MODELS.get(agent)
        if not canonical_model:
            return True, None, None  # Unknown agent, assume ok

        # All agents run via Claude Code — openclaw.json model is gateway config,
        # not execution model. Validate that the canonical config itself is sane.
        # "claude-code/settings" is the sentinel for claude-code executor agents and is always valid.
        if canonical_model == "claude-code/settings":
            return True, canonical_model, None
        if canonical_model not in ("claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"):
            # Only flag if canonical model is set to something clearly wrong
            return False, canonical_model, (
                f"MODEL CONFIG ERROR: {agent} canonical model '{canonical_model}' "
                f"is not a known Claude model. Fix in agents_config.py."
            )

        return True, canonical_model, None

    except Exception as e:
        return True, None, f"Validation error (allowing): {e}"


# Shared text matching utility (used by task_router and task_load_balancer)
def _kw_match(kw, text_lower):
    """Match a keyword against text using word boundaries for single words,
    plain substring for multi-word phrases. Prevents false positives like
    'ui' matching inside 'build' or 'api' matching inside 'capital'."""
    if ' ' in kw:
        return kw in text_lower
    return bool(re.search(r'\b' + re.escape(kw) + r'\b', text_lower))


def _phrase_match(phrase, text_lower):
    """Match a multi-word phrase allowing other words between.
    'design research competitor' matches 'design research on competitors'.
    All words in phrase must appear in text (order-independent)."""
    words = phrase.split()
    return all(_kw_match(word, text_lower) for word in words)
