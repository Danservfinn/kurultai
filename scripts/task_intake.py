#!/usr/bin/env python3
"""
task_intake.py — Single entry point for all task creation.

Pipeline:
    1. Validate depth (reject if >= MAX_DEPTH)
    2. Route via canonical router (task_router.py)
    3. Alert deduplication (exponential backoff for system alerts)
    4. Duplicate check (has_pending_task)
    5. Create in Neo4j (primary) via create_task_full()
    6. Write filesystem (backward compat, done by create_task_full)

Usage:
    from task_intake import create_task

    task_id = create_task(
        title="Investigate error spike",
        body="Check logs for errors...",
        priority="high",
        source="kublai-actions",
        depth=0,
        agent=None,  # auto-route from title
    )
"""

import os
import re
import sys
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kurultai_paths import AGENTS_DIR, LOGS_DIR, agent_tasks_dir, VALID_AGENTS, AGENT_KEYWORDS
from kurultai_ledger import append_ledger as _kp_append_ledger, generate_task_id, validate_task_id

# Import kublai-route for pause checking
try:
    from kublai_route import should_pause_task, mark_task_paused_in_neo4j, PAUSED_TASK_PATTERNS
    KUBLAI_ROUTE_AVAILABLE = True
except ImportError:
    KUBLAI_ROUTE_AVAILABLE = False
    PAUSED_TASK_PATTERNS = ["llm.survivor", "llmsurvivor", "LLM Survivor", "llm-survivor"]

# Conversation logging integration
try:
    from conversation_logger import ConversationLogger, log_human_conversation
    CONVERSATION_LOGGER_AVAILABLE = True
except ImportError:
    CONVERSATION_LOGGER_AVAILABLE = False
    print("Warning: conversation_logger not available, task-conversation linking disabled")

# Timeout configuration (mirrors agent-task-handler.py)
_TIMEOUT_BY_PRIORITY = {
    'high': 7200,
    'normal': 7200,
    'low': 7200,
}
_SLOW_SKILLS_TIMEOUT = {
    '/horde-brainstorming': 7200,
    '/golden-horde': 7200,
    '/horde-implement': 7200,
    '/horde-review': 7200,
    '/horde-debug': 7200,
    '/horde-learn': 7200,
    '/horde-swarm': 7200,
    '/horde-test': 7200,
}
_DEFAULT_TIMEOUT = 7200


def compute_task_timeout(priority, skill_hint=None):
    """Return effective timeout in seconds for a task, matching agent-task-handler logic."""
    priority_timeout = _TIMEOUT_BY_PRIORITY.get(priority, _DEFAULT_TIMEOUT)
    skill_timeout = _SLOW_SKILLS_TIMEOUT.get(skill_hint, 0) if skill_hint else 0
    return max(priority_timeout, skill_timeout)


# =============================================================================
# Domain Classification System
# =============================================================================

# Valid task domains for frontmatter classification
VALID_DOMAINS = {"research", "implementation", "ops", "documentation", "strategy", "analysis", "autoresearch", "completion", "escalation"}

# Domain-to-agent compatibility matrix for redistribution
# Agents listed can receive tasks of that domain via load balancing or redistribution
# Updated 2026-03-09: Added completion/escalation domains, included Tolui, broadened compatibility
DOMAIN_AGENT_COMPATIBILITY = {
    "research": ["mongke", "jochi", "tolui"],  # added tolui
    "implementation": ["temujin", "ogedei", "jochi", "tolui"],  # added tolui
    "ops": ["ogedei", "temujin", "jochi", "tolui"],  # added tolui
    "documentation": ["chagatai", "mongke", "tolui"],  # added tolui
    "strategy": ["temujin", "kublai", "ogedei", "chagatai"],  # chagatai for strategic documentation/proposals
    "analysis": ["jochi", "mongke", "kublai", "tolui"],  # added tolui
    "autoresearch": ["mongke", "jochi", "chagatai"],
    "completion": ["kublai", "jochi", "ogedei", "temujin", "tolui"],  # any agent can do completion work
    "escalation": ["kublai", "ogedei", "jochi"],  # kublai coordinates, others can handle
}

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
    # Ops skills
    "/kurultai-health": "ops",
    "/dev-deploy": "ops",
    # Documentation skills
    "/content-research-writer": "documentation",
    # Autoresearch skills
    "/autoresearch": "autoresearch",
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
        "inspect", "assess", "quality", "compliance", "risk"
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
        "watchdog", "emergency", "timeout", "stall", "deadlock"
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
    # 1. Skill hint takes precedence
    if skill_hint and skill_hint in SKILL_DOMAIN_MAP:
        return SKILL_DOMAIN_MAP[skill_hint]

    # 2. Keyword-based classification
    task_lower = task_text.lower()
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
from agents_config import AGENT_MODELS as _CANONICAL_MODELS
VALID_MODELS_BY_AGENT = {
    agent: {model} for agent, model in _CANONICAL_MODELS.items()
}
# Tolui runs local model
VALID_MODELS_BY_AGENT["tolui"] = {"ollama/lukey03/qwen3.5-9b-abliterated-vision"}


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
        if canonical_model not in ("claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"):
            # Only flag if canonical model is set to something clearly wrong
            return False, canonical_model, (
                f"MODEL CONFIG ERROR: {agent} canonical model '{canonical_model}' "
                f"is not a known Claude model. Fix in agents_config.py."
            )

        return True, canonical_model, None

    except Exception as e:
        return True, None, f"Validation error (allowing): {e}"

# Pattern: @agentname at start of string, optionally followed by whitespace
_MENTION_RE = re.compile(r"^@(" + "|".join(VALID_AGENTS) + r")\b\s*", re.IGNORECASE)


def parse_mention(text):
    """Parse @agent prefix from message text.

    Returns (agent, stripped_text) if @mention found, else (None, text).
    """
    m = _MENTION_RE.match(text)
    if m:
        agent = m.group(1).lower()
        stripped = text[m.end():].strip()
        return agent, stripped
    return None, text


# Disambiguation rules (first-match-wins) -- mirrors AGENTS.md hard rules
_DISAMBIGUATION = [
    ({"status", "implement"}, "kublai"),  # project status -> kublai (PM)
    ({"status", "progress"}, "kublai"),
    ({"status", "next"}, "kublai"),
    ({"status", "feature"}, "kublai"),
    ({"status", "project"}, "kublai"),
    ({"kanban"}, "temujin"),              # kanban UI work -> dev (before bare status)
    ({"status"}, "ogedei"),               # bare ops status -> ogedei
    ({"research", "security"}, "jochi"),
    ({"research", "vulnerabilit"}, "jochi"),
    ({"research", "audit"}, "jochi"),
    ({"test", "write"}, "jochi"),
    ({"fix", "cron"}, "ogedei"),
    ({"fix", "backup"}, "ogedei"),
    ({"fix", "monitor"}, "ogedei"),
    # MONGKE RESEARCH PROTECTION (2026-03-10)
    # Prevent ops/analysis/dev tasks from routing to mongke through keyword overlap
    # Tasks must be EXPLICITLY research-oriented to route to mongke
    ({"investigate", "calendar"}, "ogedei"),       # calendar investigation -> ops (not research)
    ({"investigate", "cron"}, "ogedei"),           # cron investigation -> ops
    ({"investigate", "backup"}, "ogedei"),
    ({"investigate", "notification"}, "ogedei"),
    ({"enhance", "config"}, "jochi"),              # config enhancement -> analyst (not research)
    ({"enhance", "agent", "config"}, "jochi"),     # agent config enhancement -> analysis
    ({"fix", "config"}, "ogedei"),                 # config fixes -> ops
    ({"calendar", "notification"}, "ogedei"),      # calendar notifications -> ops
    ({"agent", "config", "enhancement"}, "jochi"), # config enhancement -> analyst
    ({"bidirectional", "linking"}, "temujin"),     # dev/testing work -> dev
    ({"test", "linking"}, "jochi"),                # linking tests -> analyst
    ({"verify", "linking"}, "jochi"),
    # Research protection before generic design+research rule (2026-03-09)
    # Use phrase-based matching to handle plurals and word order
    ("design research competitors", "mongke"),          # design research on competitors -> mongke
    ("design research market", "mongke"),               # design market research -> mongke
    ("design research trend", "mongke"),                # design trend research -> mongke
    ("design research pricing", "mongke"),              # design pricing research -> mongke
    ("design research pricing strategy", "mongke"),     # pricing strategy research -> mongke
    ("design research competitive analysis", "mongke"), # competitive analysis -> mongke
    ("research design competitors", "mongke"),          # alternate word order
    ("research design market", "mongke"),
    # Generic design tasks -> temujin (NOT research)
    ({"design", "research"}, "temujin"),  # design research (dev context, not market research)
    ({"create", "content"}, "chagatai"),    # "create content" -> writer
    ({"create", "blog"}, "chagatai"),
    ({"create", "article"}, "chagatai"),
    ({"configure", "cron"}, "ogedei"),      # ops configuration -> ogedei
    ({"configure", "backup"}, "ogedei"),
    ({"configure", "monitor"}, "ogedei"),
    ({"cleanup", "code"}, "temujin"),       # code cleanup -> dev
    ({"queue", "route"}, "kublai"),         # routing/queue -> squad lead
    ({"investigate", "error"}, "jochi"),     # error investigation -> analyst
    ({"investigate", "crash"}, "jochi"),
    ({"investigate", "fatal"}, "jochi"),
    ({"investigate", "spike"}, "jochi"),
    ({"investigate", "timeout"}, "jochi"),
    ({"investigate", "failure"}, "jochi"),
    ({"investigate", "failures"}, "jochi"),  # plural form for task failure investigations
    ({"investigate", "performance"}, "jochi"),  # perf analysis -> analyst
    ({"investigate", "score"}, "jochi"),
    ({"investigate", "cpu"}, "ogedei"),      # resource investigation -> ops
    ({"investigate", "memory"}, "ogedei"),
    ({"investigate", "disk"}, "ogedei"),
    ({"investigate", "health"}, "ogedei"),
    ({"investigate", "usage"}, "ogedei"),
    ({"investigate", "queue"}, "ogedei"),   # queue/pipeline ops -> ogedei
    ({"investigate", "pipeline"}, "ogedei"),
    ({"investigate", "cron"}, "ogedei"),
    ({"investigate", "process"}, "ogedei"),
    ({"triage", "stall"}, "kublai"),        # triage/coordination -> squad lead
    ({"triage", "agent"}, "kublai"),
    ({"triage", "backlog"}, "kublai"),
    ({"tock", "assessment"}, "kublai"),     # tock assessments -> squad lead
    ({"tock", "critical"}, "kublai"),
    ({"audit", "deploy"}, "jochi"),         # audit always -> jochi even if deploy
    ({"audit", "pipeline"}, "jochi"),
    ({"investigate", "unauthorized"}, "jochi"),  # security investigation -> analyst
    ({"investigate", "message"}, "temujin"),     # messaging system issues -> dev
    ({"investigate", "low", "performance"}, "jochi"),  # perf scoring -> analyst
    ({"investigate", "score"}, "jochi"),    # score investigation -> analyst (explicit)
    ({"routing", "audit"}, "kublai"),       # routing audit self-tasks -> squad lead
    ({"review", "routing"}, "kublai"),      # review routing -> squad lead
    ({"queue", "backlog"}, "kublai"),       # queue backlog triage -> squad lead
    ({"process", "queue"}, "kublai"),       # process queue -> squad lead
    ({"create", "soul"}, "chagatai"),       # persona/identity content -> writer
    ({"create", "identity"}, "chagatai"),
    ({"create", "persona"}, "chagatai"),
    ({"update", "persona"}, "chagatai"),    # persona updates -> writer
    ({"create", "skill", "instruction"}, "chagatai"),  # skill docs/instructions -> writer
    ({"enhance", "presentation"}, "chagatai"),         # presentation/UI copy -> writer
    ({"draft", "document"}, "chagatai"),              # drafting docs -> writer
    ({"draft", "blog"}, "chagatai"),
    ({"draft", "guide"}, "chagatai"),
    ({"draft", "proposal"}, "chagatai"),
    ({"write", "report"}, "chagatai"),                # written reports -> writer (vs generate report -> analyst)
    ({"write", "guide"}, "chagatai"),
    ({"write", "tutorial"}, "chagatai"),
    ({"write", "summary"}, "chagatai"),
    ({"summarize", "findings"}, "chagatai"),          # summarization -> writer
    ({"summarize", "research"}, "chagatai"),
    ({"explain", "architecture"}, "chagatai"),        # explanatory docs -> writer
    ({"explain", "system"}, "chagatai"),
    ({"update", "documentation"}, "chagatai"),        # doc maintenance -> writer
    ({"update", "docs"}, "chagatai"),
    ({"update", "readme"}, "chagatai"),
    ({"release", "notes"}, "chagatai"),               # release notes -> writer
    ({"create", "tutorial"}, "chagatai"),              # tutorial creation -> writer
    ({"create", "guide"}, "chagatai"),                 # guide creation -> writer
    ({"create", "documentation"}, "chagatai"),         # documentation creation -> writer
    ({"create", "docs"}, "chagatai"),
    ({"create", "summary"}, "chagatai"),               # summary creation -> writer
    ({"create", "outline"}, "chagatai"),
    # Additional disambiguation for common patterns
    ({"calendar", "implement"}, "temujin"),            # calendar feature dev -> temujin
    ({"calendar", "build"}, "temujin"),
    ({"generate", "report"}, "jochi"),                 # report generation -> analyst
    ({"report", "generate"}, "jochi"),
    ({"mvp", "implement"}, "temujin"),                 # MVP execution -> temujin
    ({"mvp", "build"}, "temujin"),
    ({"subscription", "implement"}, "temujin"),        # subscription feature -> temujin
    ({"stripe", "implement"}, "temujin"),
    ({"billing", "implement"}, "temujin"),
    ({"oauth", "implement"}, "temujin"),
    ({"oauth", "setup"}, "temujin"),
    # Evaluation of implementation features -> temujin (not mongke who has "evaluate")
    ({"evaluate", "integrate"}, "temujin"),            # evaluate integration -> dev
    ({"evaluate", "integration"}, "temujin"),          # evaluate integration -> dev
    ({"evaluate", "kanban"}, "temujin"),               # evaluate kanban -> dev
    ({"evaluate", "implement"}, "temujin"),            # evaluate implementation -> dev
    ({"evaluate", "implementation"}, "temujin"),       # evaluate implementation (noun) -> dev
    ({"fix", "401"}, "ogedei"),                        # auth error fix -> ogedei
    ({"fix", "api"}, "ogedei"),                        # API error fix -> ogedei
    ({"fix", "model"}, "ogedei"),                      # model config fix -> ogedei
    ({"model", "error"}, "ogedei"),
    # AI/LLM model research routes to mongke (2026-03-11)
    # Must be before generic {"investigate", "model"} rule
    ({"investigate", "model", "capabilities"}, "mongke"),   # model capabilities research
    ({"investigate", "ai", "model"}, "mongke"),            # AI model investigation
    ({"investigate", "llm"}, "mongke"),                   # LLM investigation
    ({"investigate", "language", "model"}, "mongke"),      # language model research
    ({"investigate", "embedding"}, "mongke"),             # embedding research
    ({"investigate", "model"}, "ogedei"),                 # model config investigation -> ops
    ({"domain", "generate"}, "ogedei"),                # domain generation -> ogedei
    ({"deploy", "railway"}, "ogedei"),                 # railway deploy -> ogedei
    ({"vercel", "deploy"}, "ogedei"),
    ({"market", "research"}, "mongke"),                # market research -> mongke
    ({"competitor", "research"}, "mongke"),
    ({"competitor", "analysis"}, "mongke"),
    # Visual content creation -> chagatai (not temujin who has "create")
    ({"create", "avatar"}, "chagatai"),                # avatar creation -> writer
    ({"create", "visual"}, "chagatai"),                # visual content -> writer
    ({"create", "image"}, "chagatai"),                 # image creation -> writer
    ({"create", "graphic"}, "chagatai"),               # graphics -> writer
    ({"photorealistic"}, "chagatai"),                  # photorealistic content -> writer
    # Code modification with review -> temujin (not jochi who has "review")
    ({"add", "review", "audit"}, "temujin"),           # add review feature -> dev
    ({"modify", "review"}, "temujin"),                 # modify review system -> dev
    ({"implement", "review"}, "temujin"),              # implement review feature -> dev
    # Review disambiguation (2026-03-11) — fix keyword routing drift
    # Most "review" tasks should go to jochi, EXCEPT for implementation/dev contexts
    ({"3-hour", "review"}, "temujin"),                 # 3-hour code review -> dev (not analyst)
    ({"code", "review"}, "temujin"),                   # code review -> dev (not analyst)
    ({"architecture", "review"}, "temujin"),           # architecture review -> dev
    ({"design", "review"}, "temujin"),                 # design review -> dev
    ({"implementation", "review"}, "temujin"),         # implementation review -> dev
    ({"pull", "request", "review"}, "temujin"),        # PR review -> dev
    ({"pr", "review"}, "temujin"),                     # PR review -> dev
    # Jochi review keywords are for audits, assessments, security reviews, etc.
    ({"audit"}, "jochi"),                              # audit -> analyst (security/quality audit)
    ({"security", "review"}, "jochi"),                 # security review -> analyst
    ({"performance", "review"}, "jochi"),              # performance review -> analyst
    ({"quality", "review"}, "jochi"),                  # quality review -> analyst
    ({"routing", "review"}, "kublai"),                 # routing review -> squad lead
    # Design/architecture tasks -> temujin (not mongke)
    ({"design", "schema"}, "temujin"),                 # schema design -> dev
    ({"design", "neo4j"}, "temujin"),                  # neo4j design -> dev
    ({"brainstorm", "schema"}, "temujin"),             # schema brainstorm -> dev
    ({"brainstorm", "neo4j"}, "temujin"),              # neo4j brainstorm -> dev
    ({"proposal", "voting"}, "temujin"),               # voting system design -> dev
    ({"voting", "system"}, "temujin"),                 # voting system -> dev
    # === CHAGATAI ROUTING GUIDE INTEGRATION ===
    # Reference: docs/chagatai-routing-guide.md
    # Rule C16: chagatai accepts tasks where PRIMARY OUTPUT is prose/content
    # These rules route AWAY from chagatai when primary output is NOT prose
    #
    # Common misroutes (from routing guide "Common Misroutes and Corrections"):
    ({"create", "authentication"}, "temujin"),         # auth system -> dev (not writer)
    ({"create", "auth", "system"}, "temujin"),
    ({"create", "user", "system"}, "temujin"),         # user system -> dev
    ({"create", "feature"}, "temujin"),                # feature creation -> dev
    ({"create", "implementation"}, "temujin"),         # implementation -> dev
    ({"write", "tests"}, "jochi"),                     # write tests -> analyst (not writer)
    ({"write", "test"}, "jochi"),
    ({"write", "unit test"}, "jochi"),
    ({"write", "integration test"}, "jochi"),
    ({"research", "competitor", "pricing"}, "mongke"), # competitor pricing -> researcher
    ({"update", "deployment", "config"}, "ogedei"),    # deployment config -> ops
    ({"update", "deploy", "config"}, "ogedei"),
    ({"fix", "email", "template"}, "temujin"),         # fix template -> dev (even if HTML)
    ({"fix", "template"}, "temujin"),                  # template fix -> dev
    ({"design", "api", "endpoint"}, "temujin"),        # API design -> dev
    ({"design", "new", "api"}, "temujin"),
    ({"design", "endpoint"}, "temujin"),
    # Keyword ambiguity resolution (Primary Output Test):
    # "create" -> chagatai ONLY when content/blog/guide; else -> temujin
    ({"create", "system"}, "temujin"),                 # system creation -> dev
    ({"create", "service"}, "temujin"),                # service creation -> dev
    ({"create", "module"}, "temujin"),                 # module creation -> dev
    ({"create", "function"}, "temujin"),               # function creation -> dev
    ({"create", "component"}, "temujin"),              # component creation -> dev
    ({"create", "api"}, "temujin"),                    # API creation -> dev
    ({"create", "endpoint"}, "temujin"),               # endpoint creation -> dev
    # "update" -> chagatai ONLY when docs/README; else -> temujin/ogedei
    ({"update", "code"}, "temujin"),                   # code update -> dev
    ({"update", "config", "file"}, "ogedei"),          # config update -> ops
    ({"update", "system"}, "temujin"),                 # system update -> dev
    ({"update", "feature"}, "temujin"),                # feature update -> dev
    # "write" -> chagatai ONLY when documentation/post; else -> temujin
    ({"write", "code"}, "temujin"),                    # code writing -> dev
    ({"write", "script"}, "temujin"),                  # script writing -> dev
    ({"write", "function"}, "temujin"),                # function writing -> dev
    ({"write", "implementation"}, "temujin"),          # implementation -> dev
    # "explain" -> chagatai ONLY when in docs/guide context; code explanation -> temujin
    ({"explain", "code"}, "temujin"),                  # explain code -> dev
    ({"explain", "how", "implement"}, "temujin"),      # implementation explanation -> dev
    ({"explain", "bug"}, "temujin"),                   # bug explanation -> dev
    # Special cases from routing guide:
    ({"research", "and", "write", "blog"}, "chagatai"), # research+write blog -> writer
    ({"research", "topic", "write"}, "chagatai"),      # research for content -> writer
    ({"update", "code", "to", "match"}, "temujin"),    # code matches docs -> dev
    ({"create", "slide", "deck"}, "chagatai"),         # slide deck content -> writer
    ({"implement", "presentation"}, "temujin"),        # presentation feature -> dev
    # Research protection rules (2026-03-09): Keep pure research with mongke
    # These rules prevent research tasks from being misrouted to temujin/chagatai
    ({"research", "competitor"}, "mongke"),            # competitor research -> mongke
    ({"research", "market"}, "mongke"),                # market research -> mongke
    ({"research", "trend"}, "mongke"),                 # trend research -> mongke
    ({"research", "pricing"}, "mongke"),               # pricing research -> mongke
    ({"research", "ecosystem"}, "mongke"),             # ecosystem research -> mongke
    ({"discover", "competitor"}, "mongke"),            # competitor discovery -> mongke
    ({"discover", "market"}, "mongke"),                # market discovery -> mongke
    ({"market", "analysis"}, "mongke"),                # market analysis -> mongke
    ({"competitor", "analysis"}, "mongke"),            # competitor analysis -> mongke
    ({"benchmark", "competitor"}, "mongke"),           # competitive benchmarking -> mongke
    ({"landscape", "analysis"}, "mongke"),             # landscape analysis -> mongke
    ({"literature", "review"}, "mongke"),              # literature review -> mongke
    ({"source", "triangulation"}, "mongke"),           # source triangulation -> mongke
]

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


def route_by_text(text):
    """Keyword routing for programmatic task creation with disambiguation."""
    text_lower = text.lower()

    # Check disambiguation rules first (first-match-wins)
    for rule, target in _DISAMBIGUATION:
        # Handle string-based phrase rules (2026-03-09)
        # String rules use phrase matching (words can be separated), set rules are keyword intersections
        if isinstance(rule, str):
            if _phrase_match(rule, text_lower):
                return target
        elif isinstance(rule, set):
            if all(_kw_match(kw, text_lower) for kw in rule):
                return target

    best, best_score = "temujin", 0
    for agent, keywords in AGENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if _kw_match(kw, text_lower))
        if score > best_score:
            best, best_score = agent, score

    # Apply Primary Output Test for chagatai (Rule C16 compliance)
    # Reference: docs/chagatai-routing-guide.md
    if best == "chagatai":
        primary_output = _primary_output_test(text_lower)
        if primary_output and primary_output != "prose":
            # Route to the agent matching the actual primary output
            best = _PRIMARY_OUTPUT_ROUTE_MAP.get(primary_output, "temujin")

    return best


# Primary Output Test - determines what type of deliverable a task produces
# Reference: docs/chagatai-routing-guide.md "When in Doubt: Primary Output Test"
_PRIMARY_OUTPUT_PATTERNS = {
    # Prose indicators (chagatai domain)
    "prose": [
        "blog", "article", "documentation", "docs", "readme", "changelog",
        "marketing", "copy", "announcement", "social", "twitter", "linkedin",
        "guide", "tutorial", "draft", "outline", "proposal content",
        "release notes", "memo", "narrative", "summary", "summarize"
    ],
    # Code indicators (temujin domain)
    "code": [
        "implement", "build", "code", "function", "api", "endpoint", "service",
        "module", "component", "feature", "bug", "fix", "refactor", "script",
        "system", "authentication", "auth", "database", "schema", "migration",
        "integration", "sdk", "frontend", "backend", "ui component"
    ],
    # Research indicators (mongke domain)
    "research": [
        "research", "discover", "competitor", "market", "trend", "study",
        "benchmark", "survey", "literature", "paper", "citation", "findings",
        "sources", "evidence", "investigate trend", "market analysis",
        # AI/LLM research (2026-03-11)
        "llm", "model comparison", "ai model", "provider comparison", "llm evaluation"
    ],
    # Analysis indicators (jochi domain)
    "analysis": [
        "analyze", "audit", "review", "security", "vulnerability", "test",
        "verify", "validate", "performance", "score", "compliance", "check"
    ],
    # Operations indicators (ogedei domain)
    "operations": [
        "deploy", "monitor", "restart", "backup", "alert", "health", "cron",
        "incident", "status", "queue", "pipeline", "infrastructure", "server"
    ],
}

_PRIMARY_OUTPUT_ROUTE_MAP = {
    "prose": "chagatai",
    "code": "temujin",
    "research": "mongke",
    "analysis": "jochi",
    "operations": "ogedei",
}


def _primary_output_test(text_lower):
    """Determine the primary output type of a task.

    Implements the Primary Output Test from docs/chagatai-routing-guide.md.
    Returns: "prose", "code", "research", "analysis", "operations", or None
    """
    scores = {}
    for output_type, patterns in _PRIMARY_OUTPUT_PATTERNS.items():
        score = sum(1 for p in patterns if p in text_lower)
        if score > 0:
            scores[output_type] = score

    if not scores:
        return None

    # Return the output type with highest score
    return max(scores.items(), key=lambda x: x[1])[0]


# --- LOAD BALANCING CONFIGURATION ---

# Queue depth thresholds
# Previous values (20/30/5) were too permissive — load balancing never fired.
# Temujin accumulated 9+ tasks while idle agents available (2026-03-07 review).
# Lowered HIGH_THRESHOLD from 3 to 2 (2026-03-09) to trigger redistribution for kublai->mongke overflow
QUEUE_HIGH_THRESHOLD = 2       # Route to alternate if primary > this (was 3)
QUEUE_CRITICAL_THRESHOLD = 8   # Broadcast to all capable agents if primary > this
QUEUE_LOW_THRESHOLD = 2        # Consider agent underutilized if < this

# Failure-rate routing bypass — agents failing > this rate are treated as overloaded
# Lowered from 0.80/3 to 0.60/2 (2026-03-10) per /horde-review PRIORITY_FIX:
# ogedei had 100% failure rate across multi-cycle window with no corrective action.
# 2 consecutive failures (100% rate) now triggers bypass immediately.
AGENT_FAILURE_BYPASS_THRESHOLD = 0.60   # 60% failure rate in recent window (was 0.80)
AGENT_FAILURE_WINDOW_H = 4             # Look-back window for failure rate (was 2h, widened for low-throughput periods)
AGENT_FAILURE_MIN_TASKS = 2            # Minimum terminal tasks before applying bypass (was 3)

# Agent capability overlap matrix for cross-training overflow
# Maps: primary_agent -> [(alternate_agent, [task_keywords]), ...]
AGENT_CAPABILITY_MATRIX = {
    "temujin": [
        # mongke can handle PURE research tasks from temujin — NOT mixed dev+research
        # Removed "investigate" (overlaps with dev debugging: "investigate and fix...")
        # Removed "explore" (overlaps with dev: "explore codebase", "explore approach")
        ("mongke", ["research", "discover", "benchmark", "study", "competitor", "market analysis"]),
        # jochi can handle testing/QA, debugging, AND security tasks from temujin (expanded 2026-03-11)
        ("jochi", ["test", "testing", "verify", "audit", "review code", "QA", "quality",
                   "debug", "bug", "error", "crash", "investigate", "performance", "anomaly",
                   "security", "vulnerability", "scan", "injection", "compliance", "unauthorized"]),
        # ogedei can handle deployment/ops tasks from temujin (removed "implement"/"build" to reduce overload)
        ("ogedei", ["deploy", "railway", "docker", "container", "infrastructure", "monitor", "restart", "cleanup"]),
        # chagatai can handle documentation tasks from temujin
        ("chagatai", ["document", "documentation", "write", "readme", "changelog", "content"]),
        # kublai can handle system design/architecture tasks from temujin (added 2026-03-09)
        ("kublai", ["design", "architecture", "system", "protocol", "plan", "strategy"]),
    ],
    "jochi": [
        # Expanded jochi's outgoing options (2026-03-09)
        ("temujin", ["debug", "fix", "error", "crash", "implement fix", "patch"]),
        ("ogedei", ["security audit", "vulnerability scan", "compliance check", "health diagnostic"]),
        # mongke can handle research-investigation tasks from jochi (added 2026-03-09)
        ("mongke", ["research", "competitor analysis", "market research", "investigate trend", "benchmark competitors"]),
        # kublai can handle analysis/triage tasks from jochi (added 2026-03-09)
        ("kublai", ["analyze", "triage", "assess", "review", "investigate issue"]),
    ],
    "mongke": [
        ("chagatai", ["write", "document findings", "summarize research", "content"]),
        # jochi can handle data analysis tasks from mongke (added 2026-03-09)
        ("jochi", ["analyze data", "verify", "validate findings", "score", "benchmark"]),
    ],
    "chagatai": [
        ("mongke", ["research topic", "gather sources", "investigate trend"]),
    ],
    "ogedei": [
        ("temujin", ["fix script", "code cleanup", "automation", "tooling"]),
        ("jochi", ["health check", "diagnostic", "monitor verification"]),
        # mongke can handle research-investigation tasks from ogedei (added 2026-03-09)
        # These are "investigate X" tasks where X requires research, not ops debugging
        ("mongke", ["research", "investigate trend", "market research", "competitor analysis", "benchmark"]),
        # kublai can handle escalation/status tasks from ogedei (added 2026-03-09)
        ("kublai", ["escalate", "status", "report", "notify", "alert"]),
    ],
    # kublai can receive tasks (added 2026-03-09)
    "kublai": [
        # kublai can handle analysis/triage from temujin
        ("temujin", ["triage", "coordinate", "assess", "review system"]),
        # mongke can handle pure research tasks from kublai (added 2026-03-09)
        ("mongke", ["research", "competitor analysis", "market research", "benchmark", "investigate trend"]),
        # kublai can handle analysis from jochi
        ("jochi", ["analyze", "investigate", "review", "assess"]),
        # kublai can handle status/reporting from ogedei
        ("ogedei", ["status", "report", "health check", "escalation"]),
    ],
}

# Legacy overflow map (kept for compatibility with existing code)
OVERFLOW_MAP = {
    # (primary_agent, task_category): [overflow_agents in priority order]
    ("temujin", "code_review"):     ["jochi"],
    ("temujin", "deploy"):          ["ogedei"],
    ("temujin", "infrastructure"):  ["ogedei"],
    ("temujin", "testing"):         ["jochi"],
    ("temujin", "security"):        ["jochi"],        # FIX 2026-03-11: security overflow TO jochi (analyst), not away
    ("jochi", "code_review"):       ["temujin"],      # code review implementation -> dev (jochi reviews audits)
    # REMOVED: ("jochi", "security"): ["temujin", "ogedei"]
    # Security is jochi's PRIMARY domain — jochi should RECEIVE security, not send it away
    ("mongke", "research"):         ["chagatai"],
    ("chagatai", "docs"):           ["mongke"],
    ("ogedei", "deploy"):           ["temujin"],
    ("ogedei", "monitoring"):       ["jochi"],
}

CATEGORY_KEYWORDS = {
    "code_review": ["review", "code review", "pull request", "PR review"],
    "deploy": ["deploy", "deployment", "railway", "production", "ship"],
    "infrastructure": ["infrastructure", "infra", "docker", "container"],
    "testing": ["test", "tests", "testing", "spec", "e2e"],
    "security": ["security", "vulnerability", "audit", "scan", "injection"],
    "research": ["research", "investigate", "discover", "explore", "competitor",
                 # AI/LLM research (2026-03-11)
                 "llm", "model comparison", "ai model", "provider comparison"],
    "docs": ["document", "documentation", "readme", "changelog"],
    "monitoring": ["monitor", "health", "alert", "status", "uptime"],
}


# --- KUBLAI SELF-ABSORPTION ---
# Kublai (router) can absorb certain coordination/analysis tasks when its queue is high
# but it has been idle. This prevents the "router cannot route to itself" failure mode.
KUBLAI_SELF_ABSORB_THRESHOLD = 20      # Trigger when kublai queue >= this
KUBLAI_SELF_ABSORB_IDLE_MINUTES = 30   # No kublai dispatch in this many minutes
KUBLAI_SELF_ABSORB_KEYWORDS = [
    # Core coordination keywords (from AGENT_KEYWORDS["kublai"])
    "triage", "coordinate", "prioritize", "system-wide", "assessment", "status assessment",
    "agent status", "backlog", "routing", "dispatch", "workload",
    # Expanded analysis keywords for self-absorption
    "queue analysis", "queue depth", "throughput", "pipeline health", "bottleneck",
    "agent utilization", "load balance", "routing analysis", "coordination",
    "performance review", "system health", "fleet status", "agent review",
]
_KUBLAI_LAST_DISPATCH_FILE = f"{LOGS_DIR}/kublai_last_dispatch.txt"


def _update_kublai_dispatch_timestamp():
    """Record when kublai last received a task."""
    try:
        with open(_KUBLAI_LAST_DISPATCH_FILE, 'w') as f:
            f.write(str(datetime.now().timestamp()))
    except Exception:
        pass  # Non-critical, don't fail routing


def _get_kublai_idle_minutes():
    """Return minutes since kublai last received a task. Returns 999 if no record."""
    try:
        if not os.path.exists(_KUBLAI_LAST_DISPATCH_FILE):
            return 999  # No record = consider idle
        with open(_KUBLAI_LAST_DISPATCH_FILE, 'r') as f:
            last_ts = float(f.read().strip())
        idle_seconds = datetime.now().timestamp() - last_ts
        return idle_seconds / 60
    except Exception:
        return 999  # Error = consider idle


def should_kublai_self_absorb(title: str) -> bool:
    """Check if kublai should absorb this task based on queue depth and idle time.

    Returns True if:
    1. Kublai queue >= KUBLAI_SELF_ABSORB_THRESHOLD (20)
    2. Kublai idle for >= KUBLAI_SELF_ABSORB_IDLE_MINUTES (30)
    3. Task title contains self-absorption keywords
    """
    kublai_depth = get_queue_depth("kublai")
    if kublai_depth < KUBLAI_SELF_ABSORB_THRESHOLD:
        return False

    idle_minutes = _get_kublai_idle_minutes()
    if idle_minutes < KUBLAI_SELF_ABSORB_IDLE_MINUTES:
        return False

    title_lower = title.lower()
    return any(kw in title_lower for kw in KUBLAI_SELF_ABSORB_KEYWORDS)


# --- SKILL-AGENT COMPATIBILITY ---
# Skills that belong exclusively to one agent. Prevents misroutes like
# /horde-brainstorming going to chagatai (writer) instead of temujin (dev).
# NOTE: /horde-implement removed 2026-03-08 to allow load balancing to ogedei.
# Implementation tasks will still route to temujin via keywords, but can be
# load-balanced to ogedei when temujin is overloaded.
_SKILL_OWNER = {
    "/horde-brainstorming": "temujin",
    "/horde-plan": "temujin",
    "/golden-horde": "temujin",
    "/horde-debug": "temujin",
    # /systematic-debugging is shared: temujin (dev debugging) AND jochi (analysis)
    # Do NOT add it here — it would force all debugging to one agent.
    "/dev-deploy": "temujin",
    "/horde-learn": "mongke",
    "/scrapling-research": "mongke",
    "/content-research-writer": "chagatai",
    "/changelog-generator": "chagatai",
    # Kurultai health skill belongs to ogedei (2026-03-09 fix)
    "/kurultai-health": "ogedei",
    # Code review and test generation belong to jochi (2026-03-09 fix)
    "/code-reviewer": "jochi",
    "/generate-tests": "jochi",
}

# --- SKILL CAPABLE ALTERNATES (Dynamic Queue Balancing - Phase 4) ---
# Defines alternate agents that can handle a skill when the primary agent
# is overloaded. This enables skill overflow bypass while maintaining
# domain compatibility.
_SKILL_CAPABLE_ALTERNATES = {
    # Design/system architecture can overflow to mongke (analyst), jochi, and chagatai (documentation deliverables)
    "/horde-brainstorming": ["mongke", "jochi", "chagatai"],

    # Implementation can overflow to ogedei (ops can deploy)
    "/horde-implement": ["ogedei"],

    # Debugging can overflow to jochi (analyst) and ogedei (ops diagnostic)
    "/horde-debug": ["jochi", "ogedei"],

    # Review can overflow between temujin and jochi
    "/horde-review": ["jochi"],

    # Planning can overflow to mongke (analyst) and chagatai (proposal/document output)
    "/horde-plan": ["mongke", "chagatai"],

    # Kurultai health can overflow to jochi (diagnostics/analysis) (2026-03-09 fix)
    "/kurultai-health": ["jochi"],

    # Code review can overflow to temujin (dev perspective) (2026-03-09 fix)
    "/code-reviewer": ["temujin"],

    # Generate-tests can overflow to temujin (dev can write tests) (2026-03-09 fix)
    "/generate-tests": ["temujin"],

    # Content writing can overflow to mongke (research+writing) and tolui (documentation-capable)
    "/content-research-writer": ["mongke", "tolui"],

    # Changelog generation can overflow to mongke and tolui
    "/changelog-generator": ["mongke", "tolui"],

    # Research can overflow to jochi (analyst) and chagatai (content from research)
    "/horde-learn": ["jochi", "chagatai"],
}

# --- SKILL HINT DETECTION ---
# Auto-detect the best horde/domain skill for the task
SKILL_HINTS = {
    ("temujin", "design"):     "/horde-brainstorming",
    ("temujin", "architect"):  "/horde-brainstorming",
    ("temujin", "brainstorm"): "/horde-brainstorming",
    ("temujin", "plan"):       "/horde-brainstorming",
    ("temujin", "protocol"):   "/horde-brainstorming",
    ("temujin", "payment"):    "/horde-brainstorming",
    ("temujin", "implement"):  "/horde-implement",
    ("temujin", "build"):      "/horde-implement",
    ("temujin", "scaffold"):   "/horde-implement",
    ("temujin", "finish"):     "/horde-implement",
    ("temujin", "complete"):   "/horde-implement",
    ("temujin", "debug"):      "/systematic-debugging",
    ("temujin", "broken"):     "/systematic-debugging",
    ("temujin", "error"):      "/systematic-debugging",
    ("temujin", "crash"):      "/systematic-debugging",
    ("temujin", "deploy"):     "/dev-deploy",
    ("temujin", "railway"):    "/dev-deploy",
    ("mongke", "research"):    "/horde-learn",
    ("mongke", "investigate"): "/horde-learn",
    ("mongke", "discover"):    "/horde-learn",
    ("mongke", "explore"):     "/horde-learn",
    ("mongke", "scrape"):      "/scrapling-research",
    ("mongke", "crawl"):       "/scrapling-research",
    ("chagatai", "blog"):      "/content-research-writer",
    ("chagatai", "article"):   "/content-research-writer",
    ("chagatai", "content"):   "/content-research-writer",
    ("chagatai", "changelog"): "/changelog-generator",
    ("chagatai", "release"):   "/changelog-generator",
    ("jochi", "debug"):        "/systematic-debugging",
    ("jochi", "bug"):          "/systematic-debugging",
    ("jochi", "error"):        "/systematic-debugging",
    ("jochi", "review"):       "/code-reviewer",
    ("jochi", "audit"):        "/code-reviewer",
    ("jochi", "security"):     "/code-reviewer",
    ("ogedei", "health"):      "/kurultai-health",
    ("ogedei", "diagnostic"):  "/kurultai-health",
    ("ogedei", "deploy"):      "/dev-deploy",
    ("ogedei", "railway"):     "/dev-deploy",
    ("ogedei", "cron"):        "/kurultai-health",
    ("ogedei", "alert"):       "/kurultai-health",
    ("ogedei", "restart"):     "/kurultai-health",
    ("ogedei", "monitor"):     "/kurultai-health",
    ("jochi", "investigate"):  "/systematic-debugging",
    ("jochi", "spike"):        "/systematic-debugging",
    ("jochi", "failure"):      "/systematic-debugging",
    ("jochi", "test"):         "/generate-tests",
    ("temujin", "fix"):        "/systematic-debugging",
    ("temujin", "bug"):        "/systematic-debugging",
    ("temujin", "refactor"):   "/code-reviewer",
    ("chagatai", "document"):  "/content-research-writer",
    ("chagatai", "write"):     "/content-research-writer",
    ("chagatai", "social"):    "/content-research-writer",
    ("chagatai", "marketing"): "/content-research-writer",
    ("chagatai", "persona"):   "/content-research-writer",
    ("chagatai", "identity"):  "/content-research-writer",
    ("chagatai", "create"):    "/content-research-writer",
    ("chagatai", "update"):    "/content-research-writer",
    ("temujin", "frontend"):   "/senior-frontend",
    ("temujin", "ui"):         "/senior-frontend",
    ("temujin", "react"):      "/senior-frontend",
    ("temujin", "kanban"):     "/senior-frontend",
    ("temujin", "component"):  "/senior-frontend",
    ("temujin", "enhance"):    "/senior-fullstack",
    ("temujin", "notification"): "/horde-brainstorming",
    ("temujin", "sort"):       "/senior-frontend",
    ("temujin", "configure"):  "/horde-implement",
    ("temujin", "signal"):     "/horde-implement",
    ("jochi", "performance"):  "/systematic-debugging",
    ("jochi", "stalled"):      "/systematic-debugging",
    ("jochi", "triage"):       "/systematic-debugging",
    ("jochi", "anomaly"):      "/systematic-debugging",
    ("jochi", "unauthorized"): "/code-reviewer",
    ("jochi", "compliance"):   "/code-reviewer",
    # Additional temujin skills
    ("temujin", "calendar"):     "/horde-implement",
    ("temujin", "mvp"):          "/horde-implement",
    ("temujin", "worker"):       "/horde-implement",
    ("temujin", "evaluator"):    "/horde-implement",
    ("temujin", "bullmq"):       "/horde-implement",
    ("temujin", "api"):          "/senior-backend",
    ("temujin", "backend"):      "/senior-backend",
    ("temujin", "endpoint"):     "/senior-backend",
    ("temujin", "billing"):      "/horde-brainstorming",
    ("temujin", "subscription"): "/horde-brainstorming",
    ("temujin", "oauth"):        "/horde-brainstorming",
    ("temujin", "auth"):         "/horde-brainstorming",
    ("temujin", "integration"):  "/horde-implement",
    ("temujin", "sdk"):          "/horde-implement",
    # Additional mongke skills
    ("mongke", "market"):        "/horde-learn",
    ("mongke", "competitor"):    "/horde-learn",
    ("mongke", "benchmark"):     "/horde-learn",
    ("mongke", "analyze"):       "/horde-learn",
    ("mongke", "study"):         "/horde-learn",
    ("mongke", "source"):        "/horde-learn",
    # Additional ogedei skills
    ("ogedei", "investigate"):   "/kurultai-health",
    ("ogedei", "report"):        "/kurultai-health",
    ("ogedei", "failure"):       "/kurultai-health",
    ("ogedei", "error"):         "/kurultai-health",
    ("ogedei", "generate"):      "/dev-deploy",
    ("ogedei", "domain"):        "/dev-deploy",
    ("ogedei", "vercel"):        "/dev-deploy",
}


def detect_skill_hint(agent, text):
    """Auto-detect the best skill for this agent + task combination."""
    text_lower = text.lower()
    for (hint_agent, keyword), skill in SKILL_HINTS.items():
        if agent == hint_agent and _kw_match(keyword, text_lower):
            return skill
    return None


def is_agent_busy(agent):
    """Check if agent has an actively executing task."""
    task_dir = f"{AGENT_DIR}/{agent}/tasks"
    if not os.path.exists(task_dir):
        return False
    for fname in os.listdir(task_dir):
        if '.executing' in fname and '.done' not in fname:
            return True
    return False


def get_agent_load(agent):
    """Get agent workload: count of executing and pending tasks.

    Returns dict with 'executing' and 'pending' counts.
    """
    task_dir = f"{AGENT_DIR}/{agent}/tasks"
    executing = 0
    pending = 0
    if not os.path.exists(task_dir):
        return {"executing": executing, "pending": pending}
    for fname in os.listdir(task_dir):
        # Skip completed, hidden, archived, and backup files
        if '.done' in fname or fname.startswith('.') or fname == 'archived-20260303' or fname.endswith('.bak'):
            continue
        if '.executing' in fname and not fname.endswith('.pid'):
            executing += 1
        elif fname.endswith('.md') and '.executing' not in fname:
            pending += 1
    return {"executing": executing, "pending": pending}


def get_queue_depth(agent):
    """Get total queue depth (executing + pending) for an agent."""
    load = get_agent_load(agent)
    return load["executing"] + load["pending"]


def get_all_agent_queue_depths():
    """Get queue depths for all valid agents.

    Returns dict of {agent: depth}.
    """
    return {agent: get_queue_depth(agent) for agent in VALID_AGENTS}


def calculate_system_load_factor():
    """Calculate normalized system load (0.0 = idle, 1.0 = saturated).

    Load factor is based on total tasks across all agents normalized by capacity.
    Uses TARGET_PER_AGENT=2 as ideal queue depth, with 3x target = saturated.

    Returns:
        float: Load factor between 0.0 and 1.0
    """
    depths = get_all_agent_queue_depths()
    total_tasks = sum(depths.values())

    # Target load per agent and saturation multiplier
    TARGET_PER_AGENT = 2  # Ideal queue depth per agent
    SATURATION_MULTIPLIER = 3  # 3x target = saturated

    max_capacity = len(VALID_AGENTS) * TARGET_PER_AGENT * SATURATION_MULTIPLIER

    if max_capacity == 0:
        return 0.0

    load_factor = min(1.0, total_tasks / max_capacity)
    return load_factor


def _log_threshold_adjustment(thresholds, previous_thresholds=None):
    """Log threshold adjustments to threshold-adjustments.jsonl.

    Args:
        thresholds: Current threshold dict from get_adaptive_thresholds()
        previous_thresholds: Optional previous thresholds for comparison
    """
    log_path = Path("/Users/kublai/.openclaw/logs/threshold-adjustments.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "load_factor": thresholds['load_factor'],
        "high": thresholds['high'],
        "critical": thresholds['critical'],
        "low": thresholds['low']
    }

    if previous_thresholds:
        entry["previous"] = previous_thresholds

    with open(log_path, 'a') as f:
        f.write(json.dumps(entry) + '\n')


def get_agent_failure_rate(agent, hours=None):
    """Get recent failure rate for an agent from the task ledger.

    Returns (rate, total) where rate is 0.0-1.0 and total is the number
    of terminal events in the window. Returns (0.0, 0) if no data.
    """
    if hours is None:
        hours = AGENT_FAILURE_WINDOW_H
    try:
        from kurultai_ledger import read_ledger
        events = read_ledger(hours=hours)
        failed = 0
        completed = 0
        for e in events:
            if e.get("agent") != agent:
                continue
            ev = e.get("event")
            if ev == "FAILED":
                failed += 1
            elif ev == "COMPLETED":
                completed += 1
        total = failed + completed
        if total == 0:
            return 0.0, 0
        return failed / total, total
    except Exception:
        return 0.0, 0


def is_agent_failing(agent):
    """Check if agent has a high recent failure rate that should bypass routing.

    Returns True if agent failure rate exceeds AGENT_FAILURE_BYPASS_THRESHOLD
    with at least AGENT_FAILURE_MIN_TASKS terminal events.
    """
    rate, total = get_agent_failure_rate(agent)
    return total >= AGENT_FAILURE_MIN_TASKS and rate >= AGENT_FAILURE_BYPASS_THRESHOLD


def check_agent_credentials(agent):
    """Check if agent has valid API credentials.

    Returns (is_valid, error_message) tuple:
    - is_valid: True if credentials are valid
    - error_message: Description of issue if invalid, None if valid

    Credential model (2026-03-09):
    1. OAuth for Anthropic (no stored token) — check credentials.json
    2. Centralized vault (provider.env) for fallbacks
    3. Per-agent tokens in settings.json (legacy, being phased out)

    Proactive credential check prevents routing to blocked agents.
    """
    try:
        # 1. Check OAuth status (primary auth method for Anthropic)
        _claude_creds_path = Path.home() / ".claude" / "credentials.json"
        if _claude_creds_path.exists():
            try:
                with open(_claude_creds_path, 'r') as f:
                    _creds = json.load(f)
                if _creds.get('loggedIn') and _creds.get('authMethod') == 'oauth_token':
                    # OAuth is active — credentials are valid
                    return True, None
            except (json.JSONDecodeError, IOError):
                pass  # Fall through to vault check

        # 2. Check centralized vault for fallback credentials
        _vault_path = Path.home() / ".openclaw" / "credentials" / "provider.env"
        if _vault_path.exists():
            try:
                with open(_vault_path, 'r') as f:
                    _vault_content = f.read()
                # Check for Z.AI or Alibaba fallback tokens
                _has_zai = 'ZAI_AUTH_TOKEN=' in _vault_content and 'b5b1f953' in _vault_content
                _has_alibaba = 'ALIBABA_AUTH_TOKEN=' in _vault_content and 'sk-sp-' in _vault_content
                if _has_zai or _has_alibaba:
                    return True, None  # Vault has valid fallback credentials
            except IOError:
                pass  # Fall through to legacy check

        # 3. Legacy: Check for per-agent token in settings.json
        agent_root = AGENTS_DIR / agent
        settings_path = agent_root / ".claude" / "settings.json"

        if not settings_path.exists():
            return False, f"No settings.json found for {agent}"

        with open(settings_path, 'r') as f:
            settings = json.load(f)

        # Check for ANTHROPIC_AUTH_TOKEN in env (Claude Code format)
        auth_token = None
        if 'env' in settings:
            auth_token = settings['env'].get('ANTHROPIC_AUTH_TOKEN')

        # Also check direct apiKey field
        if not auth_token:
            auth_token = settings.get('apiKey')

        if not auth_token:
            return False, f"No ANTHROPIC_AUTH_TOKEN found"

        # Validate token format - accept Anthropic, Z.AI, or Alibaba tokens
        # Anthropic: sk-ant-*
        # Z.AI: 32-hex-chars.32-hex-chars
        # Alibaba: sk-sp-*
        _is_anthropic = auth_token.startswith('sk-ant-')
        _is_zai = len(auth_token.split('.')) == 2 and len(auth_token.split('.')[0]) == 32
        _is_alibaba = auth_token.startswith('sk-sp-') or auth_token.startswith('sk-')

        if not (_is_anthropic or _is_zai or _is_alibaba):
            return False, f"Invalid token: {auth_token[:10]}... (expected sk-ant-*, Z.AI, or Alibaba)"

        return True, None

    except Exception as e:
        return False, f"Credential check error: {e}"


def find_underutilized_agents(exclude=None):
    """Find agents with queue depth below adaptive LOW threshold.

    Args:
        exclude: set of agent names to exclude

    Returns list of (agent, depth) tuples sorted by depth ascending.
    """
    exclude = exclude or set()
    # Get adaptive threshold
    thresholds = get_adaptive_thresholds()
    LOW_THRESHOLD = thresholds['low']

    underutilized = []
    for agent in VALID_AGENTS:
        if agent in exclude:
            continue
        depth = get_queue_depth(agent)
        if depth < LOW_THRESHOLD:
            underutilized.append((agent, depth))
    underutilized.sort(key=lambda x: x[1])
    return underutilized


def can_handle_task(alternate_agent, primary_agent, task_text):
    """Check if alternate agent can handle a task based on capability matrix.

    Returns True if alternate is in primary's capability matrix and
    the task keywords match the alternate's capabilities.
    """
    task_lower = task_text.lower()
    capabilities = AGENT_CAPABILITY_MATRIX.get(primary_agent, [])
    for cap_agent, keywords in capabilities:
        if cap_agent == alternate_agent:
            for kw in keywords:
                if _kw_match(kw, task_lower):
                    return True
    return False


def get_capable_alternates(primary_agent, task_text, task_domain=None):
    """Get list of alternate agents capable of handling this task.

    Includes a domain guard: if the primary agent's keyword score is
    significantly higher than the alternate's, skip the alternate to
    prevent cross-domain misroutes (e.g., dev task → research agent
    because both match "investigate").

    If task_domain is provided, only agents in DOMAIN_AGENT_COMPATIBILITY[task_domain]
    will be considered as valid alternates.

    Returns list of (agent, depth) tuples sorted by queue depth.
    """
    capabilities = AGENT_CAPABILITY_MATRIX.get(primary_agent, [])
    capable = []
    task_lower = task_text.lower()

    # Determine valid agents based on domain compatibility
    domain_valid_agents = None
    if task_domain and task_domain in DOMAIN_AGENT_COMPATIBILITY:
        domain_valid_agents = set(DOMAIN_AGENT_COMPATIBILITY[task_domain])
        # Always include primary agent as valid
        domain_valid_agents.add(primary_agent)

    # Score how strongly the task matches the primary agent's domain
    primary_keywords = AGENT_KEYWORDS.get(primary_agent, [])
    primary_score = sum(1 for kw in primary_keywords if _kw_match(kw, task_lower))

    for alt_agent, keywords in capabilities:
        # Domain compatibility filter: skip agents not in the domain's valid set
        if domain_valid_agents is not None and alt_agent not in domain_valid_agents:
            continue
        cap_match_count = sum(1 for kw in keywords if _kw_match(kw, task_lower))
        if cap_match_count == 0:
            continue

        # Also check the alternate's own domain keywords — if the task doesn't
        # match any of the alternate's core keywords, it's likely a false positive.
        alt_domain_keywords = AGENT_KEYWORDS.get(alt_agent, [])
        alt_domain_score = sum(1 for kw in alt_domain_keywords if _kw_match(kw, task_lower))
        if alt_domain_score == 0:
            continue

        # Domain guard: if primary agent matches 2+ of its own domain keywords
        # and the capability match is weak (only 1 keyword), skip this alternate.
        # This prevents "investigate" alone from redirecting a dev task to research.
        # EXCEPTION: If alternate has strong domain match (>= 50% of primary score), allow it.
        # This prevents blocking capable alternates when primary is overloaded.
        domain_guard_ratio = 0.5  # Alternate needs >= 50% of primary's keyword score
        if primary_score >= 2 and cap_match_count <= 1:
            if alt_domain_score < primary_score * domain_guard_ratio:
                continue

        depth = get_queue_depth(alt_agent)
        capable.append((alt_agent, depth))

    # Sort by queue depth (lowest first)
    capable.sort(key=lambda x: x[1])
    return capable


def find_skill_capable_alternates(skill_hint, exclude=None):
    """Find alternate agents capable of handling a skill-based task.

    Args:
        skill_hint: The skill hint (e.g., "/horde-brainstorming")
        exclude: Agent to exclude from results (typically the primary owner)

    Returns:
        List of (agent, queue_depth) tuples sorted by queue depth
    """
    alternates = _SKILL_CAPABLE_ALTERNATES.get(skill_hint, [])
    exclude_set = {exclude} if exclude else set()

    result = []
    for agent in alternates:
        if agent in exclude_set or agent in _NO_OVERFLOW_TARGETS:
            continue
        depth = get_queue_depth(agent)
        result.append((agent, depth))

    # Sort by queue depth (lowest first)
    result.sort(key=lambda x: x[1])
    return result


def should_bypass_skill_lock(skill_hint, target_agent, queue_depth):
    """Determine if skill-based routing should bypass to an alternate agent.

    Bypass conditions:
    1. Skill hint is defined in _SKILL_CAPABLE_ALTERNATES
    2. Target agent queue >= adaptive HIGH threshold
    3. At least one alternate agent exists with lower queue depth

    Args:
        skill_hint: The skill hint (e.g., "/horde-brainstorming")
        target_agent: The primary agent that owns this skill
        queue_depth: Current queue depth of target_agent

    Returns:
        Tuple of (should_bypass: bool, alternate_agent: str or None, reason: str)
    """
    if not skill_hint:
        return False, None, "no_skill_hint"

    if skill_hint not in _SKILL_CAPABLE_ALTERNATES:
        return False, None, f"skill_not_in_alternates: {skill_hint}"

    # Use adaptive threshold
    thresholds = get_adaptive_thresholds()
    HIGH_THRESHOLD = thresholds['high']

    if queue_depth < HIGH_THRESHOLD:
        return False, None, f"queue_depth={queue_depth} < threshold={HIGH_THRESHOLD}"

    alternates = find_skill_capable_alternates(skill_hint, exclude=target_agent)
    if not alternates:
        return False, None, f"no_capable_alternates_for_skill: {skill_hint}"

    # Find best alternate (lowest queue depth)
    best_alt, best_depth = alternates[0]

    # Only bypass if alternate has significantly lower queue
    if best_depth >= queue_depth:
        return False, None, f"alternate_deeper: {best_alt}={best_depth} >= {target_agent}={queue_depth}"

    return True, best_alt, f"skill_overflow_bypass: {skill_hint} from {target_agent}(q={queue_depth}) -> {best_alt}(q={best_depth})"


def find_best_agent_by_load(task_text, primary_agent, task_domain=None):
    """Find the best agent considering queue depth and capabilities.

    Algorithm:
    1. If primary agent queue < adaptive HIGH threshold, use primary
    2. Find underutilized agents (< adaptive LOW threshold) with capability match
    3. If primary > adaptive CRITICAL threshold, broadcast to all capable agents
    4. Otherwise, route to lowest-depth capable alternate
    5. Fall back to primary if no alternates available

    If task_domain is provided, only agents in DOMAIN_AGENT_COMPATIBILITY[task_domain]
    will be considered as valid alternates.

    Returns (agent, reason) tuple.
    """
    # Get adaptive thresholds based on current system load
    thresholds = get_adaptive_thresholds()
    HIGH_THRESHOLD = thresholds['high']
    CRITICAL_THRESHOLD = thresholds['critical']
    LOW_THRESHOLD = thresholds['low']
    load_factor = thresholds['load_factor']

    primary_depth = get_queue_depth(primary_agent)

    # Check if primary agent has a high failure rate — bypass to alternates
    if is_agent_failing(primary_agent):
        capable_alternates = get_capable_alternates(primary_agent, task_text, task_domain)
        # Filter out agents that are also failing
        healthy_alts = [(a, d) for a, d in capable_alternates if not is_agent_failing(a)]
        if healthy_alts:
            best_agent, best_depth = healthy_alts[0]
            rate, _ = get_agent_failure_rate(primary_agent)
            return best_agent, f"failure-bypass: {primary_agent} failure_rate={rate:.0%}, routing to {best_agent} (queue={best_depth})"

    # Primary agent has capacity - use directly
    if primary_depth < HIGH_THRESHOLD:
        return primary_agent, f"primary queue={primary_depth} < threshold={HIGH_THRESHOLD} (load={load_factor:.2f})"

    # Find capable alternates sorted by queue depth
    capable_alternates = get_capable_alternates(primary_agent, task_text, task_domain)

    # Filter to underutilized agents (queue < LOW_THRESHOLD) WITH VALID CREDENTIALS (2026-03-09)
    underutilized = []
    for agent, depth in capable_alternates:
        if depth < LOW_THRESHOLD:
            # CRITICAL: Check credentials before accepting overflow
            alt_valid, alt_error = check_agent_credentials(agent)
            if alt_valid:
                underutilized.append((agent, depth))
            else:
                print(f"LOAD_BALANCE_CREDENTIAL_BLOCK: {agent} has invalid credentials ({alt_error}), not accepting underutilized overflow from {primary_agent}")

    if underutilized:
        best_agent, best_depth = underutilized[0]
        return best_agent, f"load-balance: {primary_agent} queue={primary_depth}, {best_agent} underutilized (queue={best_depth}, low_threshold={LOW_THRESHOLD})"

    # IDLE AGENT WAKE-UP (2026-03-09): When no underutilized capable agents found,
    # check for ANY idle agent (queue=0 and not busy) with valid credentials.
    # This prevents artificial bottlenecks when idle agents exist but aren't in
    # the capability matrix due to keyword mismatch. LLM agents are generally
    # capable enough to help reduce queue pressure.
    idle_agents = get_idle_agents(exclude={primary_agent, "kublai", "tolui"})
    if idle_agents:
        # Filter to agents with valid credentials
        healthy_idle = []
        for idle_agent in idle_agents:
            idle_valid, idle_error = check_agent_credentials(idle_agent)
            if idle_valid:
                idle_depth = get_queue_depth(idle_agent)
                healthy_idle.append((idle_agent, idle_depth))
            else:
                print(f"IDLE_WAKE_CREDENTIAL_BLOCK: {idle_agent} has invalid credentials ({idle_error}), skipping idle wake-up")
        if healthy_idle:
            best_idle_agent, best_idle_depth = healthy_idle[0]
            print(f"IDLE_WAKE_UP: No capable underutilized agents for {primary_agent} (queue={primary_depth}), waking idle agent {best_idle_agent} (queue={best_idle_depth})")
            return best_idle_agent, f"idle-wake: {primary_agent} overloaded (queue={primary_depth}), {best_idle_agent} idle with valid creds (queue={best_idle_depth})"

    # Primary queue is critical - broadcast to all capable WITH VALID CREDENTIALS (2026-03-09)
    if primary_depth >= CRITICAL_THRESHOLD and capable_alternates:
        # Filter to agents with valid credentials
        healthy_capable = []
        for agent, depth in capable_alternates:
            alt_valid, alt_error = check_agent_credentials(agent)
            if alt_valid:
                healthy_capable.append((agent, depth))
            else:
                print(f"BROADCAST_CREDENTIAL_BLOCK: {agent} has invalid credentials ({alt_error}), excluding from broadcast")

        if healthy_capable:
            best_agent, best_depth = healthy_capable[0]
            # Log broadcast for audit
            _log_routing_decision(
                title=task_text,
                dest=best_agent,
                method="broadcast_overflow",
                overflow_reason=f"{primary_agent} queue={primary_depth} >= {CRITICAL_THRESHOLD}, routing to lowest alternate with valid creds"
            )
            return best_agent, f"broadcast: {primary_agent} critical queue={primary_depth}, routing to {best_agent} (queue={best_depth})"
        else:
            print(f"BROADCAST_CREDENTIAL_FAIL: All alternates have invalid credentials, cannot broadcast from {primary_agent}")

    # Use any capable alternate with lower queue than primary WITH VALID CREDENTIALS (2026-03-09)
    if capable_alternates:
        for alt_agent, alt_depth in capable_alternates:
            # Check credentials before selecting alternate
            alt_valid, alt_error = check_agent_credentials(alt_agent)
            if not alt_valid:
                print(f"ALTERNATE_CREDENTIAL_BLOCK: {alt_agent} has invalid credentials ({alt_error}), skipping")
                continue
            if alt_depth < primary_depth:
                return alt_agent, f"load-balance: {primary_agent} queue={primary_depth}, {alt_agent} lower (queue={alt_depth})"
        # All alternates also busy or invalid - use lowest with valid credentials anyway
        healthy_capable = []
        for agent, depth in capable_alternates:
            alt_valid, _ = check_agent_credentials(agent)
            if alt_valid:
                healthy_capable.append((agent, depth))
        if healthy_capable:
            best_agent, best_depth = healthy_capable[0]
            return best_agent, f"load-balance: all busy, {primary_agent} queue={primary_depth}, using {best_agent} (queue={best_depth})"

    # No capable alternates - queue to primary
    return primary_agent, f"no capable alternates, queuing to {primary_agent} (queue={primary_depth})"


def should_redistribute_tasks():
    """Check if redistribution is needed - any agent overloaded while another underutilized.

    Uses adaptive thresholds based on current system load.

    Returns list of (overloaded_agent, underutilized_agents) tuples.
    """
    # Get adaptive thresholds
    thresholds = get_adaptive_thresholds()
    HIGH_THRESHOLD = thresholds['high']
    LOW_THRESHOLD = thresholds['low']

    depths = get_all_agent_queue_depths()
    overloaded = [(agent, depth) for agent, depth in depths.items()
                  if depth > HIGH_THRESHOLD]
    underutilized = [(agent, depth) for agent, depth in depths.items()
                     if depth <= LOW_THRESHOLD]  # FIX: use <= so agents at threshold qualify

    redistribution_needed = []
    for ov_agent, ov_depth in overloaded:
        capable_underutilized = []
        for un_agent, un_depth in underutilized:
            # Check if underutilized agent can handle tasks from overloaded agent
            if AGENT_CAPABILITY_MATRIX.get(ov_agent):
                for cap_agent, _ in AGENT_CAPABILITY_MATRIX[ov_agent]:
                    if cap_agent == un_agent:
                        capable_underutilized.append((un_agent, un_depth))
                        break
        if capable_underutilized:
            redistribution_needed.append((ov_agent, capable_underutilized))

    return redistribution_needed


def get_idle_agents(exclude=None):
    """Return list of agents that are not currently executing any task.

    Args:
        exclude: set of agent names to exclude (e.g., kublai)
    """
    exclude = exclude or set()
    idle = []
    for agent in VALID_AGENTS:
        if agent in exclude:
            continue
        if not is_agent_busy(agent):
            idle.append(agent)
    return idle


# ============================================================
# AUTOMATIC REDISTRIBUTION TRIGGERS (Phase 2 - Dynamic Queue Balancing)
# ============================================================

REDISTRIBUTION_TRIGGERS = {
    # Trigger when: max queue > 2x min queue AND max queue >= 5
    'imbalance_ratio': 2.0,
    'min_overloaded_depth': 5,

    # Trigger when: agent idle for > 10min while others have work
    'idle_time_threshold_s': 600,

    # Trigger when: system load > 0.6 for 3 consecutive checks
    'high_load_streak': 3,
    'high_load_threshold': 0.6,

    # Maximum tasks to move per redistribution cycle
    'max_move_per_cycle': 5,

    # Load history file for streak detection
    'load_history_file': f"{LOGS_DIR}/load-history.jsonl",
}


def get_agent_idle_time(agent):
    """Get seconds since agent last completed a task.

    Returns int seconds (0 if agent has pending/executing tasks).
    """
    task_dir = agent_tasks_dir(agent)
    if not task_dir.exists():
        return 0

    # Agent is not idle if currently executing
    for fname in task_dir.iterdir():
        if '.executing' in fname and '.done' not in fname and not fname.endswith('.pid'):
            return 0

    # Check most recent completed task
    latest_time = None
    for fname in task_dir.iterdir():
        if fname.suffix == '.md' and ('.done' in fname or fname.name.endswith('.done.md')):
            # Get file modification time as proxy for completion time
            mtime = fname.stat().st_mtime
            if latest_time is None or mtime > latest_time:
                latest_time = mtime

    if latest_time is None:
        # No completed tasks found
        return 0

    return int(datetime.now().timestamp() - latest_time)


def _get_load_history(count=5):
    """Get recent load factor measurements from history file.

    Returns list of load factors (most recent first).
    """
    history_file = Path(REDISTRIBUTION_TRIGGERS['load_history_file'])
    if not history_file.exists():
        return []

    try:
        lines = history_file.read_text().strip().split('\n')
        # Get last N entries
        recent = lines[-count:] if len(lines) >= count else lines
        history = []
        for line in recent:
            try:
                data = json.loads(line)
                history.append(data.get('load_factor', 0.0))
            except json.JSONDecodeError:
                continue
        return list(reversed(history))  # Most recent first
    except Exception:
        return []


def _record_load_measurement(load_factor):
    """Append load factor measurement to history file."""
    history_file = Path(REDISTRIBUTION_TRIGGERS['load_history_file'])
    try:
        history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(history_file, 'a') as f:
            f.write(json.dumps({
                'timestamp': datetime.now().isoformat(),
                'load_factor': load_factor,
            }) + '\n')

        # Trim to last 100 entries
        try:
            lines = history_file.read_text().strip().split('\n')
            if len(lines) > 100:
                history_file.write_text('\n'.join(lines[-100:]) + '\n')
        except Exception:
            pass
    except Exception:
        pass


def calculate_system_load_factor():
    """Calculate normalized system load (0.0 = idle, 1.0 = saturated).

    Load factor = total_tasks / (num_agents * TARGET_PER_AGENT * 3)
    """
    depths = get_all_agent_queue_depths()
    total_tasks = sum(depths.values())
    active_agents = sum(1 for d in depths.values() if d > 0)

    # Normalize by number of agents and target load per agent
    TARGET_PER_AGENT = 2  # Ideal queue depth per agent
    max_capacity = len(VALID_AGENTS) * TARGET_PER_AGENT * 3  # 3x target = saturated

    load_factor = min(1.0, total_tasks / max_capacity) if max_capacity > 0 else 0.0
    return load_factor


def should_trigger_redistribution():
    """Determine if redistribution should run proactively.

    Returns tuple of (should_trigger: bool, reason: str).

    Three trigger conditions:
    1. Severe imbalance: max queue >= 5 and max/min ratio >= 2.0
    2. Idle agent: agent idle for > 10min while others have work
    3. Sustained high load: load > 0.6 for 3 consecutive checks

    Also records current load factor for streak detection.
    """
    depths = get_all_agent_queue_depths()
    non_zero = [d for d in depths.values() if d > 0]

    if len(non_zero) < 2:
        return False, "Not enough agents with work"

    max_depth = max(depths.values())
    min_depth = min(depths.values())

    # Condition 1: Severe imbalance
    if max_depth >= REDISTRIBUTION_TRIGGERS['min_overloaded_depth']:
        ratio = max_depth / max(min_depth, 1)
        if ratio >= REDISTRIBUTION_TRIGGERS['imbalance_ratio']:
            return True, f"Imbalance: max={max_depth}, min={min_depth}, ratio={ratio:.1f}"

    # Condition 2: Idle agent while work exists
    for agent in VALID_AGENTS:
        if agent in {'kublai', 'tolui'}:
            continue
        if depths[agent] == 0:
            idle_time = get_agent_idle_time(agent)
            if idle_time > REDISTRIBUTION_TRIGGERS['idle_time_threshold_s']:
                others_have_work = any(depths[a] > 2 for a in VALID_AGENTS if a not in {agent, 'kublai', 'tolui'})
                if others_have_work:
                    return True, f"Agent {agent} idle for {idle_time}s while work exists"

    # Condition 3: Sustained high load
    load_factor = calculate_system_load_factor()
    _record_load_measurement(load_factor)  # Record for next check

    load_history = _get_load_history(count=REDISTRIBUTION_TRIGGERS['high_load_streak'])
    if len(load_history) >= REDISTRIBUTION_TRIGGERS['high_load_streak']:
        if all(l > REDISTRIBUTION_TRIGGERS['high_load_threshold'] for l in load_history):
            return True, f"Sustained high load: {[f'{l:.2f}' for l in load_history]}"

    return False, "No trigger conditions met"


def get_agent_scores(text):
    """Score all agents for a given task text. Returns dict of {agent: score}."""
    text_lower = text.lower()
    scores = {}
    for agent, keywords in AGENT_KEYWORDS.items():
        scores[agent] = sum(1 for kw in keywords if _kw_match(kw, text_lower))
    return scores


def get_adaptive_thresholds():
    """Calculate thresholds based on current system load.

    Returns dict with 'high', 'critical', 'low', and 'load_factor' keys.

    Threshold scaling (adjusted 2026-03-09 for aggressive redistribution):
    - Load 0.0: HIGH=2, CRITICAL=6, LOW=1 (base values)
    - Load 0.5: HIGH=3, CRITICAL=8, LOW=2
    - Load 1.0: HIGH=4, CRITICAL=10, LOW=2
    """
    load = calculate_system_load_factor()

    # Base thresholds (adjusted 2026-03-09 for more aggressive redistribution)
    # Lower HIGH_THRESHOLD triggers redistribution earlier
    # Lower LOW_THRESHOLD makes more agents eligible to receive overflow
    BASE_HIGH = 2      # Was 3 - agents with 2+ tasks are overloaded
    BASE_CRITICAL = 6  # Was 8 - earlier critical threshold
    BASE_LOW = 1       # Was 2 - agents with 1 or 0 tasks are underutilized

    # Scaled thresholds (linear interpolation, reduced scaling for 2026-03-09)
    # When load = 0.5: HIGH=3, CRITICAL=8, LOW=2
    # When load = 1.0: HIGH=4, CRITICAL=10, LOW=2
    HIGH = int(BASE_HIGH + load * 2)   # Reduced from load * 2
    CRITICAL = int(BASE_CRITICAL + load * 4)  # Kept same

    # LOW threshold increases more slowly - want underutilized agents even at high load
    # This keeps jochi and other low-queue agents eligible for overflow
    LOW = BASE_LOW + int(load * 1)  # Was load * 2 - more agents qualify now

    return {
        'high': HIGH,
        'critical': CRITICAL,
        'low': LOW,
        'load_factor': load
    }


def route_with_queue_penalty(text, thresholds=None):
    """Route task considering both keyword match and queue depth.

    Applies exponential penalty to agent scores based on queue depth:
    - No penalty when depth < LOW threshold
    - Soft penalty (0.95^depth) when depth between LOW and HIGH
    - Hard penalty (0.9^(depth - HIGH + 1)) when depth >= HIGH

    Args:
        text: Task title/text to route
        thresholds: Optional dict from get_adaptive_thresholds(). If None,
                    uses static QUEUE_*_THRESHOLD constants.

    Returns:
        Tuple of (best_agent, metadata) where metadata contains:
        - original_scores: Raw keyword match scores
        - penalized_scores: Scores after queue penalty applied
        - queue_depths: Current queue depth for each agent
        - thresholds: Thresholds used for penalty calculation
    """
    if thresholds is None:
        thresholds = get_adaptive_thresholds()

    scores = get_agent_scores(text)
    depths = get_all_agent_queue_depths()

    # Calculate penalized scores
    penalized = {}
    for agent, score in scores.items():
        depth = depths[agent]

        # Penalty formula per design doc:
        # - Over HIGH: score * 0.9^(depth - HIGH + 1)
        # - Between LOW and HIGH: score * 0.95^depth
        # - Below LOW: no penalty
        if depth >= thresholds['high']:
            penalty_factor = 0.9 ** (depth - thresholds['high'] + 1)
        elif depth >= thresholds['low']:
            penalty_factor = 0.95 ** depth
        else:
            penalty_factor = 1.0

        penalized[agent] = score * penalty_factor

    # Find best agent by penalized score
    best = max(penalized.items(), key=lambda x: x[1])

    return best[0], {
        'original_scores': scores,
        'penalized_scores': penalized,
        'queue_depths': depths,
        'thresholds': thresholds
    }


# Agents that should not receive load-balanced overflow tasks
_NO_OVERFLOW_TARGETS = {"kublai", "tolui"}

def find_best_idle_agent(text, primary_agent, task_domain=None):
    """Find the best agent considering queue depth and idle status.

    Uses queue-aware load balancing:
    1. Check queue depth before assigning
    2. If target agent queue >= adaptive HIGH threshold AND another agent has capacity, route to available agent
    3. Use capability matrix (AGENT_CAPABILITY_MATRIX) for cross-training
    4. Fall back to OVERFLOW_MAP by task category, then find_best_agent_by_load()
    5. EQUAL-QUEUE BALANCING (2026-03-11): When primary and alternate have equal queue depth,
       prefer alternate based on priority order to prevent task concentration

    CRITICAL FIX: task_domain parameter prevents cross-domain misroutes.
    When task_domain is provided, only agents in DOMAIN_AGENT_COMPATIBILITY[task_domain]
    are considered as valid alternates. This prevents implementation tasks (skill_hint=/horde-implement)
    from being routed to research agents like mongke.

    Args:
        text: Task title/text
        primary_agent: Original target agent
        task_domain: Optional domain string ("implementation", "research", etc.) for filtering

    Returns (agent, reason) tuple.
    """
    # Get adaptive thresholds
    thresholds = get_adaptive_thresholds()
    HIGH_THRESHOLD = thresholds['high']
    LOW_THRESHOLD = thresholds['low']

    primary_depth = get_queue_depth(primary_agent)

    # CREDENTIAL HEALTH CHECK: Proactively block routing to agents with invalid credentials
    # Implements behavioral rule #1: detect invalid tokens BEFORE routing
    creds_valid, creds_error = check_agent_credentials(primary_agent)
    if not creds_valid:
        capable_alternates = get_capable_alternates(primary_agent, text, task_domain)
        # Filter to agents with valid credentials
        healthy_alts = []
        for alt_agent, alt_depth in capable_alternates:
            alt_valid, _ = check_agent_credentials(alt_agent)
            if alt_valid:
                healthy_alts.append((alt_agent, alt_depth))
        if healthy_alts:
            best_agent, best_depth = healthy_alts[0]
            print(f"CREDENTIAL_BYPASS: {primary_agent} has invalid credentials ({creds_error}), routing to {best_agent}")
            return best_agent, f"credential-bypass: {primary_agent} credentials invalid, routing to {best_agent} (queue={best_depth})"
        else:
            print(f"CREDENTIAL_BLOCK: {primary_agent} has invalid credentials ({creds_error}) — NO capable alternates available")
            # Fall through to queue logic - task will likely fail but at least we logged it

    # Check if primary agent has a high failure rate — bypass to alternates
    if is_agent_failing(primary_agent):
        capable_alternates = get_capable_alternates(primary_agent, text, task_domain)
        healthy_alts = [(a, d) for a, d in capable_alternates if not is_agent_failing(a)]
        if healthy_alts:
            best_agent, best_depth = healthy_alts[0]
            rate, _ = get_agent_failure_rate(primary_agent)
            return best_agent, f"failure-bypass: {primary_agent} failure_rate={rate:.0%}, routing to {best_agent} (queue={best_depth})"

    # EQUAL-QUEUE LOAD BALANCING (2026-03-11): Check for capable alternatives
    # even when primary is idle, if there's an alternate with equal or lower queue depth.
    # This fixes "missed routing opportunities" where tasks went to busy agents
    # when equally idle alternatives existed (e.g., mongke queue=1 vs chagatai queue=1).
    capable_alternates = get_capable_alternates(primary_agent, text, task_domain)
    # FILTER BY VALID CREDENTIALS - prevents overflow to broken agents
    better_or_equal_alternates = []
    for alt_agent, alt_depth in capable_alternates:
        alt_valid, alt_error = check_agent_credentials(alt_agent)
        if not alt_valid:
            print(f"OVERFLOW_CREDENTIAL_BLOCK: {alt_agent} has invalid credentials ({alt_error}), not accepting overflow from {primary_agent}")
            continue
        # Consider alternate if it has equal or lower queue depth than primary
        # This enables load balancing even when primary is "idle" but not alone in being idle
        if alt_depth <= primary_depth:
            better_or_equal_alternates.append((alt_agent, alt_depth))

    # If primary is idle, has low queue, AND no equal-or-better alternatives exist, use it directly
    if not is_agent_busy(primary_agent) and primary_depth < HIGH_THRESHOLD and not better_or_equal_alternates:
        if creds_valid:
            return primary_agent, f"primary idle, queue={primary_depth}, no equal alternatives"

    # Filter to underutilized agents (< LOW_THRESHOLD) from the better-or-equal set
    underutilized = [(a, d) for a, d in better_or_equal_alternates if d < LOW_THRESHOLD]

    if underutilized:
        best_agent, best_depth = underutilized[0]
        return best_agent, f"load-balance: {primary_agent} busy/loaded (queue={primary_depth}), {best_agent} underutilized (queue={best_depth})"

    # EQUAL-QUEUE BALANCING (2026-03-11): If no underutilized agents but we have
    # equal-queue capable alternates, distribute load to prevent concentration.
    # Sort by queue depth (lowest first) to prefer truly idle agents over equal ones.
    if better_or_equal_alternates:
        best_agent, best_depth = better_or_equal_alternates[0]
        # Only redirect if alternate has strictly lower queue OR equal queue with tiebreaker
        if best_depth < primary_depth:
            return best_agent, f"equal-queue-balance: {primary_agent} (queue={primary_depth}) -> {best_agent} (queue={best_depth})"
        elif best_depth == primary_depth and best_agent != primary_agent:
            # Tiebreaker: prefer alternate based on agent priority order
            # This prevents all equal-queue tasks from going to the same agent
            priority_order = ["chagatai", "mongke", "jochi", "temujin", "ogedei", "kublai"]
            primary_priority = priority_order.index(primary_agent) if primary_agent in priority_order else 999
            alt_priority = priority_order.index(best_agent) if best_agent in priority_order else 999
            if alt_priority < primary_priority:
                return best_agent, f"equal-queue-tiebreak: {primary_agent} (queue={primary_depth}) -> {best_agent} (queue={best_depth}, priority {alt_priority} < {primary_priority})"

    # IDLE AGENT WAKE-UP (2026-03-09): When no underutilized capable agents found,
    # check for ANY idle agent (not busy executing) with valid credentials.
    # This prevents artificial bottlenecks when primary is overloaded but idle
    # agents exist that aren't in the capability matrix due to keyword mismatch.
    idle_agents = get_idle_agents(exclude={primary_agent, "kublai", "tolui"})
    if idle_agents:
        # Filter to agents with valid credentials AND with queue < primary's queue
        healthy_idle = []
        for idle_agent in idle_agents:
            idle_valid, idle_error = check_agent_credentials(idle_agent)
            if not idle_valid:
                print(f"IDLE_WAKE_CREDENTIAL_BLOCK: {idle_agent} has invalid credentials ({idle_error}), skipping idle wake-up")
                continue
            idle_depth = get_queue_depth(idle_agent)
            # Only wake if the idle agent has less queue depth than primary
            if idle_depth < primary_depth:
                healthy_idle.append((idle_agent, idle_depth))
        if healthy_idle:
            best_idle_agent, best_idle_depth = healthy_idle[0]
            print(f"IDLE_WAKE_UP: No capable underutilized agents for {primary_agent} (queue={primary_depth}), waking idle agent {best_idle_agent} (queue={best_idle_depth})")
            return best_idle_agent, f"idle-wake: {primary_agent} busy/loaded (queue={primary_depth}), {best_idle_agent} idle with valid creds (queue={best_idle_depth})"

    # Check overflow map for category-specific idle agents (legacy support)
    category = _detect_category(text)
    if category:
        overflow_agents = OVERFLOW_MAP.get((primary_agent, category), [])
        for overflow in overflow_agents:
            if not is_agent_busy(overflow):
                # CRITICAL: Check credentials before accepting overflow (2026-03-09)
                ov_valid, ov_error = check_agent_credentials(overflow)
                if not ov_valid:
                    print(f"OVERFLOW_CREDENTIAL_BLOCK: {overflow} has invalid credentials ({ov_error}), skipping overflow-map route")
                    continue
                ov_depth = get_queue_depth(overflow)
                return overflow, f"load-balance: {primary_agent} busy, {overflow} idle (overflow-map, {category}, queue={ov_depth})"

    # No idle/underutilized agent found - use queue-aware routing
    return find_best_agent_by_load(text, primary_agent, task_domain)


def _detect_category(text):
    """Detect task category from text for overflow lookup.

    Uses word-boundary matching to prevent false positives
    (e.g. 'testnet' should NOT match 'test' category).
    """
    text_lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if ' ' in kw:
                # Multi-word keywords: plain substring match is fine
                if kw in text_lower:
                    return category
            else:
                # Single-word keywords: require word boundary
                if re.search(r'\b' + re.escape(kw) + r'\b', text_lower):
                    return category
    return None


def find_overflow_agent(primary_agent, text):
    """Find an available overflow agent if primary is busy or quality-poor.
    Returns (agent, overflow_reason) tuple.
    """
    # Quality-aware diversion check (before busy check)
    try:
        from route_quality_tracker import should_divert, load_scores
        scores = load_scores()
        if scores:
            divert, reason = should_divert(primary_agent, text, scores)
            if divert:
                category = _detect_category(text)
                if category:
                    for overflow in OVERFLOW_MAP.get((primary_agent, category), []):
                        o_divert, _ = should_divert(overflow, text, scores)
                        if not o_divert and not is_agent_busy(overflow):
                            return overflow, f"quality divert: {reason}"
    except Exception:
        pass

    if not is_agent_busy(primary_agent):
        return primary_agent, None

    category = _detect_category(text)
    if not category:
        return primary_agent, "no category match"

    overflow_agents = OVERFLOW_MAP.get((primary_agent, category), [])
    for overflow in overflow_agents:
        if not is_agent_busy(overflow):
            return overflow, f"{primary_agent} busy, {category} -> {overflow}"

    return primary_agent, "all overflow agents busy"


def _log_overflow(original, overflow, title, reason):
    """Log overflow routing decision to JSONL."""
    import json as _json
    from datetime import datetime as _dt
    log_path = os.path.expanduser("~/.openclaw/agents/main/logs/routing-overflow.jsonl")
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        entry = {"ts": _dt.now().isoformat(), "from": original, "to": overflow,
                 "title": title[:100], "reason": reason}
        with open(log_path, "a") as f:
            f.write(_json.dumps(entry) + "\n")
    except Exception:
        pass


MAX_TASK_DEPTH = 3

AGENT_DIR = str(AGENTS_DIR)
ROUTING_LOG = str(LOGS_DIR / "routing-decisions.jsonl")


def _log_routing_decision(title, dest, method, overflow_reason=None, skill_hint=None, scores=None, queue_info=None, original_agent=None, domain=None, penalized_scores=None, route_metadata=None, task_source=None):
    """Append routing decision to JSONL log for routing_audit.py consumption.

    Enhanced logging (2026-03-08): includes alt_scores, idle_agents, would_overflow
    for missed opportunity analysis.

    Phase 5 enhancement (2026-03-08): includes penalized_scores when using
    queue-penalized routing for Dynamic Queue Balancing.
    """
    try:
        entry = {
            "ts": datetime.now().isoformat(),
            "task": title[:100],
            "dest": dest,
            "method": method,
        }
        if task_source:
            entry["source"] = task_source
        if overflow_reason:
            entry["overflow"] = overflow_reason
        if skill_hint:
            entry["skill_hint"] = skill_hint
        if domain:
            entry["domain"] = domain
        if scores:
            entry["top_scores"] = {k: v for k, v in scores.items() if v > 0}
        if queue_info:
            entry["queue"] = queue_info

        # Enhanced logging: alt_scores, idle_agents, would_overflow
        # Compute all agent scores for missed opportunity analysis
        all_scores = get_agent_scores(title)
        entry["alt_scores"] = all_scores

        # Phase 5: Include penalized scores for queue-aware routing analysis
        if penalized_scores:
            entry["penalized_scores"] = penalized_scores
        if route_metadata:
            entry["thresholds"] = route_metadata.get("thresholds", {})

        # Identify idle agents (queue=0 and not busy)
        idle = []
        for agent_name in VALID_AGENTS:
            if queue_info and queue_info.get(agent_name, 0) == 0 and not is_agent_busy(agent_name):
                idle.append(agent_name)
        entry["idle_agents"] = idle

        # Detect if this routing would trigger overflow (dest queue >= threshold and idle alternatives exist)
        dest_queue = queue_info.get(dest, 0) if queue_info else 0
        thresholds = get_adaptive_thresholds()
        would_overflow = dest_queue >= thresholds['high'] and len(idle) > 0 and dest not in idle
        entry["would_overflow"] = would_overflow

        # Track if routing was changed from original (load balancing)
        if original_agent and original_agent != dest:
            entry["load_balanced_from"] = original_agent

        os.makedirs(os.path.dirname(ROUTING_LOG), exist_ok=True)
        with open(ROUTING_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Never let logging break task creation


def _log_skill_overflow(skill_hint, primary_agent, alternate_agent, primary_depth, reason):
    """Log skill overflow bypass events for Dynamic Queue Balancing telemetry.

    Track when skill-based routing bypasses the primary agent due to overload.
    """
    try:
        overflow_log = LOGS_DIR / "skill-overflow.jsonl"
        entry = {
            "ts": datetime.now().isoformat(),
            "skill_hint": skill_hint,
            "primary_agent": primary_agent,
            "alternate_agent": alternate_agent,
            "primary_depth": primary_depth,
            "alternate_depth": get_queue_depth(alternate_agent),
            "reason": reason,
        }
        os.makedirs(os.path.dirname(overflow_log), exist_ok=True)
        with open(overflow_log, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Never let logging break task creation

def _extract_topic_keys(title):
    """Extract normalized topic keywords from a task title for fuzzy dedup."""
    # Lowercase, strip common verbs/prepositions
    noise = {'investigate', 'fix', 'debug', 'check', 'add', 'implement',
             'update', 'create', 'review', 'the', 'and', 'for', 'all',
             'across', 'from', 'with', 'when', 'not', 'is', 'are', 'to',
             'a', 'an', 'of', 'in', 'on', 'by', 'be', 'that', 'this'}
    words = re.sub(r'[^a-z0-9\s]', '', title.lower()).split()
    return frozenset(w for w in words if w not in noise and len(w) > 2)


def has_pending_task(agent, title_prefix, full_title=None):
    """Check if an agent already has an uncompleted task with this title prefix
    or a semantically similar title (>60% keyword overlap)."""
    task_dir = f"{AGENT_DIR}/{agent}/tasks"
    if not os.path.exists(task_dir):
        return False
    topic_keys = _extract_topic_keys(full_title or title_prefix)
    for fname in os.listdir(task_dir):
        if '.done' in fname:
            continue
        fpath = os.path.join(task_dir, fname)
        try:
            with open(fpath) as f:
                content = f.read(500)
            # Exact prefix match
            if f"# Task: {title_prefix}" in content:
                return True
            # Fuzzy keyword overlap match
            if topic_keys and '# Task: ' in content:
                existing_title = content.split('# Task: ')[1].split('\n')[0]
                existing_keys = _extract_topic_keys(existing_title)
                if existing_keys and topic_keys:
                    overlap = len(topic_keys & existing_keys)
                    smaller = min(len(topic_keys), len(existing_keys))
                    if smaller > 0 and overlap / smaller >= 0.6:
                        print(f"DEDUP_FUZZY: '{(full_title or title_prefix)[:60]}' ≈ '{existing_title[:60]}' ({overlap}/{smaller} overlap)")
                        return True
        except Exception:
            continue
    return False


# =============================================================================
# Alert Deduplication with Exponential Backoff
# =============================================================================

# Alert patterns that should trigger deduplication
ALERT_PATTERNS = [
    "system health alert",
    "health check",
    "watchdog alert",
    "stall alert",
    "queue imbalance",
    "throughput escalation",
]

# Deduplication state file
_ALERT_DEDUP_PATH = LOGS_DIR / "alert-dedup.json"

# Backoff intervals: 1st alert=0min, 2nd=10min, 3rd=30min, 4th+=60min
_BACKOFF_INTERVALS = [0, 10, 30, 60]


def _get_alert_dedup_state() -> dict:
    """Load alert dedup state, returning empty dict if not exists."""
    if not _ALERT_DEDUP_PATH.exists():
        return {}
    try:
        with open(_ALERT_DEDUP_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_alert_dedup_state(state: dict):
    """Persist alert dedup state."""
    try:
        os.makedirs(os.path.dirname(_ALERT_DEDUP_PATH), exist_ok=True)
        with open(_ALERT_DEDUP_PATH, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass  # Never let dedup break task creation


def _cleanup_old_alerts(state: dict, cutoff_hours: int = 24):
    """Remove alert entries older than cutoff_hours."""
    cutoff = datetime.now() - timedelta(hours=cutoff_hours)
    cutoff_iso = cutoff.isoformat()
    to_delete = []
    for key, entry in state.items():
        if entry.get("last_seen", "") < cutoff_iso:
            to_delete.append(key)
    for key in to_delete:
        del state[key]
    return state


def _normalize_alert_key(agent: str, title: str, source: str) -> str:
    """Create a normalized key for alert deduplication.
    Groups similar alerts by agent + normalized source + topic keywords."""
    title_lower = title.lower()
    # Extract alert type from source or title
    for pattern in ALERT_PATTERNS:
        if pattern in title_lower or pattern in source.lower():
            # Use the pattern as part of the key
            return f"{agent}:{pattern}"
    # If no pattern matches, use extracted keywords
    topic_keys = _extract_topic_keys(title)
    if topic_keys:
        keyword_key = "-".join(sorted(topic_keys)[:3])  # First 3 keywords
        return f"{agent}:alert:{keyword_key}"
    return f"{agent}:unknown"


def should_suppress_alert(agent: str, title: str, source: str) -> tuple[bool, str]:
    """Check if an alert should be suppressed due to recent similar alerts.

    Returns:
        (should_suppress, reason) tuple

    Implements exponential backoff:
    - 1st alert: always allow (0min cooldown)
    - 2nd alert: suppress if <10min since last
    - 3rd alert: suppress if <30min since last
    - 4th+ alert: suppress if <60min since last
    """
    # Only apply to alert-type tasks
    title_lower = title.lower()
    source_lower = source.lower()
    is_alert = any(pattern in title_lower or pattern in source_lower
                  for pattern in ALERT_PATTERNS)

    if not is_alert:
        return False, ""

    state = _get_alert_dedup_state()
    state = _cleanup_old_alerts(state)

    key = _normalize_alert_key(agent, title, source)
    entry = state.get(key, {})

    if not entry:
        # First alert of this type
        return False, ""

    # Get backoff interval based on strike count
    strikes = entry.get("strikes", 0)
    interval_idx = min(strikes, len(_BACKOFF_INTERVALS) - 1)
    cooldown_minutes = _BACKOFF_INTERVALS[interval_idx]

    if cooldown_minutes == 0:
        return False, ""

    # Check if enough time has passed
    last_seen = datetime.fromisoformat(entry["last_seen"])
    elapsed = (datetime.now() - last_seen).total_seconds() / 60

    if elapsed < cooldown_minutes:
        reason = f"ALERT_DEDUP: {key} suppressed ({elapsed:.0f}min < {cooldown_minutes}min cooldown, strike={strikes})"
        print(reason)
        return True, reason

    return False, ""


def record_alert_created(agent: str, title: str, source: str, task_id: str = None):
    """Record that an alert was created, incrementing strike count."""
    # Only record alert-type tasks
    title_lower = title.lower()
    source_lower = source.lower()
    is_alert = any(pattern in title_lower or pattern in source_lower
                  for pattern in ALERT_PATTERNS)

    if not is_alert:
        return

    state = _get_alert_dedup_state()
    state = _cleanup_old_alerts(state)

    key = _normalize_alert_key(agent, title, source)
    entry = state.get(key, {})

    entry["strikes"] = entry.get("strikes", 0) + 1
    entry["last_seen"] = datetime.now().isoformat()
    entry["last_title"] = title[:100]
    entry["last_source"] = source
    if task_id:
        entry["last_task_id"] = task_id

    state[key] = entry
    _save_alert_dedup_state(state)


# Self-task creation rate limiting
SELF_TASK_LIMITS = {
    "normal_low_per_hour": 3,
    "high_per_4_hours": 1,
    "max_depth": 3,
}


def _get_self_task_tracker_path(agent: str) -> Path:
    return Path.home() / f".openclaw/agents/{agent}/self_task_tracker.json"


def _load_tracker(agent: str) -> dict:
    path = _get_self_task_tracker_path(agent)
    if not path.exists():
        return {"window_start": None, "normal_low_count": 0, "high_count": 0, "last_high_at": None}
    with open(path) as f:
        return json.load(f)


def _save_tracker(agent: str, data: dict):
    path = _get_self_task_tracker_path(agent)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def _reset_window_if_needed(data: dict) -> dict:
    now = datetime.now()
    if data["window_start"] is None:
        data["window_start"] = now.isoformat()
    else:
        window_start = datetime.fromisoformat(data["window_start"])
        if now - window_start >= timedelta(hours=1):
            data["window_start"] = now.isoformat()
            data["normal_low_count"] = 0
    return data


def check_self_task_limit(agent: str, priority: str) -> tuple[bool, str]:
    """Check if agent can create another self-task.

    Returns (allowed, reason) tuple.
    """
    tracker = _load_tracker(agent)
    tracker = _reset_window_if_needed(tracker)

    if priority in ("normal", "low"):
        if tracker["normal_low_count"] >= SELF_TASK_LIMITS["normal_low_per_hour"]:
            return False, f"Rate limit: {SELF_TASK_LIMITS['normal_low_per_hour']} self-tasks/hour"
        tracker["normal_low_count"] += 1
    elif priority == "high":
        # Check 4-hour window for HIGH
        now = datetime.now()
        if tracker["last_high_at"]:
            last_high = datetime.fromisoformat(tracker["last_high_at"])
            if now - last_high < timedelta(hours=4):
                return False, f"Rate limit: 1 HIGH self-task per 4 hours"
        tracker["high_count"] += 1
        tracker["last_high_at"] = now.isoformat()

    _save_tracker(agent, tracker)
    return True, "OK"


def create_self_task(
    agent: str,
    title: str,
    body: str,
    priority: str = "normal",
    skill_hint: str = None,
    parent_task_id: str = None,
    justification: str = None,
) -> Optional[str]:
    """Create a self-initiated task with rate limiting.

    Args:
        agent: Creator agent name
        title: Task title
        body: Task body/description
        priority: "normal", "low", or "high" (high requires justification)
        skill_hint: Explicit skill hint for routing
        parent_task_id: Parent task ID for chain tracking
        justification: Required for HIGH priority tasks

    Returns:
        task_id string on success, None on rejection
    """
    # Check rate limit
    allowed, reason = check_self_task_limit(agent, priority)
    if not allowed:
        print(f"REJECT: Self-task rate limit — {reason}")
        return None

    # HIGH priority requires justification
    if priority == "high" and not justification:
        print("REJECT: HIGH priority self-task requires justification")
        return None

    # Calculate remaining rate limit for ledger
    tracker = _load_tracker(agent)
    remaining = SELF_TASK_LIMITS["normal_low_per_hour"] - tracker.get("normal_low_count", 0)
    if priority == "high":
        remaining = SELF_TASK_LIMITS["high_per_4_hours"] - tracker.get("high_count", 0)

    # Standard creation via task_intake
    task_id = create_task(
        title=title,
        body=body,
        priority=priority,
        source="self-created",
        agent=agent,  # May be re-routed by load balancing
        parent_id=parent_task_id,
        skill_hint=skill_hint,
    )

    if task_id:
        # Log to ledger
        _kp_append_ledger({
            "task_id": task_id,
            "event": "SELF_TASK_CREATED",
            "ts": datetime.now().isoformat(),
            "creator_agent": agent,
            "priority": priority,
            "skill_hint": skill_hint,
            "parent_task_id": parent_task_id,
            "justification": justification,
            "source": "self-created",
            "approval_required": priority == "high",
            "rate_limit_remaining": remaining,
        })

    return task_id


# =============================================================================
# CONVERSATION LOGGING INTEGRATION
# =============================================================================

def _extract_task_topics(title: str, body: str, priority: str, agent: str) -> list:
    """Extract conversation topics from task data.

    Args:
        title: Task title
        body: Task body/description
        priority: Task priority
        agent: Assigned agent

    Returns:
        List of topic strings
    """
    topics = []

    # Add task title as topic (truncated if long)
    if title:
        # Extract key words from title
        title_words = title.lower().split()
        # Add first few meaningful words
        meaningful_words = [w for w in title_words if len(w) > 3][:5]
        topics.extend(meaningful_words)

    # Add priority
    if priority:
        topics.append(f"priority:{priority}")

    # Add agent
    if agent:
        topics.append(f"agent:{agent}")

    # Add generic task topic
    topics.append("task")

    # Extract key phrases from body
    if body:
        body_lower = body.lower()
        # Common task-related keywords
        task_keywords = [
            "implement", "fix", "bug", "feature", "deploy", "test",
            "research", "document", "review", "optimize", "refactor",
            "security", "performance", "api", "database", "frontend",
            "backend", "integration", "migration", "monitor"
        ]
        for keyword in task_keywords:
            if keyword in body_lower:
                topics.append(keyword)
                break  # Only add one keyword to avoid noise

    return topics


def _link_task_to_conversation(
    task_id: str,
    phone_number: str,
    title: str,
    body: str,
    priority: str,
    agent: str,
    source: str
) -> None:
    """Link a newly created task to the conversation that triggered it.

    Args:
        task_id: The created task ID
        phone_number: Human's phone number (origin_initiator)
        title: Task title
        body: Task body
        priority: Task priority
        agent: Assigned agent
        source: Task source
    """
    if not CONVERSATION_LOGGER_AVAILABLE:
        return

    logger = ConversationLogger()
    conversation_date = datetime.now().isoformat()

    # Link conversation to task (bidirectional)
    logger._link_conversation_to_tasks(
        phone_number=phone_number,
        conversation_date=conversation_date,
        task_ids=[task_id]
    )

    # Log task creation as conversation
    topics = _extract_task_topics(title, body, priority, agent)

    # Build content for conversation log
    content = f"Task created: {title}"
    if body:
        content += f"\n{body[:200]}"  # Truncate long descriptions

    log_human_conversation(
        phone_number=phone_number,
        direction="inbound",
        content=content,
        channel="system",
        context="task_created",
        topics=topics,
        related_tasks=[task_id],
        metadata={
            "task_id": task_id,
            "agent": agent,
            "priority": priority,
            "source": source
        }
    )


def update_task_status(
    task_id: str,
    status: str,
    phone_number: str,
    title: Optional[str] = None,
    agent: Optional[str] = None,
    error: Optional[str] = None
) -> bool:
    """Update task status and log as conversation.

    This function updates a task's status in Neo4j and logs the change
    as a conversation for audit trail and human visibility.

    Args:
        task_id: Task ID to update
        status: New status (e.g., "completed", "failed", "in_progress")
        phone_number: Human's phone number for notification
        title: Optional task title for context
        agent: Optional agent name
        error: Optional error message if status is "failed"

    Returns:
        True if update succeeded, False otherwise
    """
    from neo4j_task_tracker import get_tracker

    # Update in Neo4j
    try:
        tracker = get_tracker()
        tracker.update_status(task_id, status, error=error)
        print(f"UPDATED: task {task_id} status to {status}")
    except Exception as e:
        print(f"ERROR: Failed to update task {task_id}: {e}")
        return False

    # Log as conversation if human-initiated
    if CONVERSATION_LOGGER_AVAILABLE and phone_number:
        try:
            topics = ["task", "update", status]
            if agent:
                topics.append(f"agent:{agent}")

            # Build content
            if title:
                content = f"Task '{title}' ({task_id}) status updated to {status}"
            else:
                content = f"Task {task_id} status updated to {status}"

            if error:
                content += f"\nError: {error}"

            log_human_conversation(
                phone_number=phone_number,
                direction="inbound",
                content=content,
                channel="system",
                context="task_update",
                related_tasks=[task_id],
                topics=topics,
                metadata={
                    "task_id": task_id,
                    "status": status,
                    "agent": agent,
                    "error": error
                }
            )
        except Exception as e:
            print(f"Warning: Failed to log task update for {task_id}: {e}")

    return True


CLAUDE_CODE_PREAMBLE = """**EXECUTION METHOD:** Use Claude Code via ACP for this task.
Command: sessions_spawn({ runtime: "acp", agentId: "claude", mode: "run" })
Include relevant horde skills in the task description (e.g., /horde-brainstorming, /horde-implement, /horde-review).

"""


def create_task(title, body, priority="normal", source="task_intake",
                depth=0, agent=None, parent_id=None, skip_duplicate_check=False,
                skill_hint=None, force_claude_code=False,
                notify_on_complete=False, notify_channel="signal",
                notify_target="+19194133445", bucket=None,
                origin_type=None, origin_initiator=None, origin_source=None):
    """Create a task through the canonical pipeline.

    Args:
        title: Task title (used for routing if agent is None)
        body: Task body/description
        priority: "high", "normal", or "low"
        source: Origin of the task
        depth: Current task chain depth
        agent: Target agent (auto-routed from title if None)
        parent_id: Parent task ID for chain tracking
        skip_duplicate_check: Set True to skip the has_pending_task guard
        skill_hint: Explicit skill hint (skips auto-detection if provided)
        force_claude_code: Prepend Claude Code ACP invocation instruction to body
        notify_on_complete: Send Signal notification when task completes
        notify_channel: Notification channel (default: "signal")
        notify_target: Notification target phone number
        bucket: Task bucket (CRITICAL/TODAY/WEEK/BACKLOG/BLOCKED/DELEGATED).
                Auto-assigned from priority if not provided.
        origin_type: Type of origin ("human" or "agent"). Auto-detected if not provided.
        origin_initiator: Who initiated the task (phone number or agent name).
        origin_source: Source channel (signal, reflection, proposal, api, cron).

    Returns:
        task_id string on success, None on rejection
    """
    # 0. Check if task should be paused (before any processing)
    full_text = f"{title} {body}".lower()
    for pattern in PAUSED_TASK_PATTERNS:
        if pattern.lower() in full_text:
            print(f"REJECT: Task matches paused pattern '{pattern}': '{title[:60]}'")
            print(f"  Paused tasks are not routed. Use --unpause flag to resume.")
            return None

    # 1. Validate depth
    if depth >= MAX_TASK_DEPTH:
        print(f"REJECT: depth={depth} >= {MAX_TASK_DEPTH} for '{title[:60]}'")
        return None

    # 2. Route: check @mention first, then keyword routing
    mention_agent = None
    _caller_provided_agent = agent is not None
    _route_metadata = None  # Will be populated by queue-penalized routing
    _explicit_agent_override = False  # Tracks when caller's agent override was used

    if agent is None:
        mention_agent, stripped_title = parse_mention(title)
        if mention_agent:
            agent = mention_agent
            title = stripped_title  # Use the message body without @mention prefix
            source = "direct-mention"
        else:
            # Use queue-penalized routing (Dynamic Queue Balancing - Phase 5)
            agent, _route_metadata = route_with_queue_penalty(title)
            if agent == "subagent":
                agent = "kublai"  # Default fallback
    else:
        # Caller provided an explicit agent — check if keyword routing disagrees
        # FIX (2026-03-11): Reduce explicit routing by checking keyword matches
        # even when agent is specified, unless it's a system source or direct mention
        _system_sources = {
            "kublai-actions", "ogedei-watchdog", "task-watcher", "routing_audit",
            "reflection", "tick", "tock", "hourly_reflection", "mongke_self_task",
            "cascade_detector", "throughput_anomaly", "stall_detector",
            "action_resolution", "signal_calendar", "redistribution",
            "system-health-check", "task_intake", "queue-audit", "kurultai-monitor",
            "kublai-initiative", "idle-monitor", "kublai-diagnostic", "idle-crisis",
            "idle-prevention", "heartbeat-escalation", "anomaly-scanner",
            "routing-retry", "cron-test", "test-cron", "cron-3hr-test", "cron-3hr-review",
        }
        _is_system_source = source in _system_sources

        if not _is_system_source:
            # For non-system sources, check if keyword routing strongly disagrees
            mention_agent, stripped_title = parse_mention(title)
            if not mention_agent:
                # Get keyword-based suggestion
                kw_agent, kw_metadata = route_with_queue_penalty(title)
                if kw_agent == "subagent":
                    kw_agent = "kublai"

                # Check if keyword router strongly disagrees (score >= 2)
                kw_scores = kw_metadata.get("penalized_scores", {})
                original_scores = kw_metadata.get("original_scores", {})
                kw_score = original_scores.get(kw_agent, 0)
                caller_score = original_scores.get(agent, 0)

                # Use keyword routing if:
                # 1. Keyword score >= 2 (meaningful match) AND
                # 2. Keyword score > caller's score (caller has weak/no match)
                if kw_score >= 2 and kw_score > caller_score:
                    print(f"KEYWORD_OVERRIDE: caller specified {agent} (score={caller_score}) "
                          f"but keywords suggest {kw_agent} (score={kw_score})")
                    agent = kw_agent
                    _route_metadata = kw_metadata
                    _explicit_agent_override = True
                    _caller_provided_agent = False  # Now using keyword routing
                    _log_routing_decision(
                        title=title,
                        dest=agent,
                        method="keyword_override",
                        scores=original_scores,
                        original_agent=agent if not _explicit_agent_override else kw_agent,
                        route_metadata=kw_metadata,
                    )

    # 2.5. Skill hint detection BEFORE load balancing (prevents domain misroutes)
    # Detect skill first so _SKILL_OWNER can block incompatible load-balance targets.
    # If skill_hint detected after load balancing, it uses the wrong agent's keyword table.
    if skill_hint is None:
        skill_hint = detect_skill_hint(agent, title)

    # 2.5.1. Skill-agent compatibility: reroute if skill doesn't belong to this agent
    _skill_locked_agent = False
    if skill_hint and skill_hint in _SKILL_OWNER:
        correct_agent = _SKILL_OWNER[skill_hint]
        if agent != correct_agent:
            print(f"SKILL REROUTE: {skill_hint} belongs to {correct_agent}, not {agent} — rerouting")
            _log_routing_decision(
                title=title,
                dest=correct_agent,
                method="skill_reroute",
                scores={agent: 0, correct_agent: 1},
            )
            agent = correct_agent
        _skill_locked_agent = True  # Prevent load balancing from overriding

    # 2.5.1b. Skill Overflow Bypass (Dynamic Queue Balancing - Phase 4)
    # If the skill-locked agent is overloaded, allow overflow to capable alternates
    # This breaks the skill lock when primary agent queue >= QUEUE_HIGH_THRESHOLD
    if _skill_locked_agent and skill_hint:
        primary_depth = get_queue_depth(agent)
        should_bypass, alternate_agent, bypass_reason = should_bypass_skill_lock(
            skill_hint, agent, primary_depth
        )
        if should_bypass and alternate_agent:
            print(f"SKILL OVERFLOW BYPASS: {bypass_reason}")
            _log_routing_decision(
                title=title,
                dest=alternate_agent,
                method="skill_overflow_bypass",
                scores={agent: 0, alternate_agent: 1},
                metadata={
                    "skill_hint": skill_hint,
                    "primary_agent": agent,
                    "primary_depth": primary_depth,
                    "bypass_reason": bypass_reason
                },
            )
            # Save primary agent before reassignment for logging
            primary_agent_for_log = agent
            agent = alternate_agent
            _skill_locked_agent = False  # Allow load balancing to run on alternate
            # Log the skill overflow event for telemetry
            _log_skill_overflow(skill_hint, primary_agent_for_log, alternate_agent, primary_depth, bypass_reason)

    # 2.5.2. Classify domain BEFORE load balancing (prevents domain-incompatible routes)
    # This ensures DOMAIN_AGENT_COMPATIBILITY is respected when selecting alternates.
    _task_domain = classify_task_domain(title, skill_hint)

    # 2.5.3. Kublai self-absorption: when router is overloaded but idle, absorb coordination tasks
    # This fixes the "router cannot route to itself" failure mode where kublai's queue grows
    # without bound because it never takes tasks for itself.
    if agent != "kublai" and not mention_agent and not _skill_locked_agent:
        if should_kublai_self_absorb(title):
            original_agent = agent
            agent = "kublai"
            print(f"KUBLAI_SELF_ABSORB: {original_agent} -> kublai (queue={get_queue_depth('kublai')}, idle={int(_get_kublai_idle_minutes())}min)")
            _log_routing_decision(
                title=title,
                dest="kublai",
                method="self_absorb",
                original_agent=original_agent,
                domain=_task_domain,
            )

    # 2.5.4. EARLY FLEET-WIDE CREDENTIAL CHECK — fail fast before expensive routing
    # Check all dispatch agents upfront. If ALL have invalid credentials, stop immediately.
    # This prevents wasting time on load balancing/routing when the entire fleet is dead.
    # Implements behavioral rule #1: stop creating tasks when fleet is paralyzed.
    _dispatch_agents = ["temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"]
    _healthy_count = 0
    _unhealthy_agents = []

    for _agent in _dispatch_agents:
        _valid, _error = check_agent_credentials(_agent)
        if _valid:
            _healthy_count += 1
        else:
            _unhealthy_agents.append(_agent)

    # Fleet-wide failure: ALL dispatch agents have invalid credentials
    if _healthy_count == 0:
        print(f"FLEET_CREDENTIAL_FAILURE: ALL {_dispatch_agents} agents have invalid credentials")
        print(f"  Unhealthy: {', '.join(_unhealthy_agents)}")
        print(f"  Blocking task creation for: '{title[:80]}...'")
        print(f"  Writing human alert — fleet is PARALYZED")

        # Write human alert (not a task, to avoid recursion when ogedei also has bad creds)
        _human_alert = f"""
════════════════════════════════════════════════════════════════════════════════
FLEET-WIDE CREDENTIAL FAILURE — ALL AGENTS PARALYZED
Time: {datetime.now().isoformat()}

ALL dispatch agents have INVALID API credentials:
{chr(10).join(f'  ❌ {a}: Invalid token' for a in _unhealthy_agents)}

Blocked task: {title}
Timestamp: {datetime.now().isoformat()}

REQUIRED FIX (human intervention):
1. Obtain valid API keys for all agents:
   - Anthropic: sk-ant-* (primary)
   - Z.AI: 32-hex.32-hex format (fallback tier 1)
   - Alibaba: sk-sp-* (fallback tier 2)
2. Update each agent's ~/.openclaw/agents/{{agent}}/.claude/settings.json
3. Verify ANTHROPIC_BASE_URL matches token type:
   - Anthropic: omit or use https://api.anthropic.com
   - Z.AI: https://api.z.ai/api/anthropic
   - Alibaba: https://coding-intl.dashscope.aliyuncs.com/apps/anthropic
4. Reset sessions/sessions.json to {{}} for each agent

Multi-tier fallback: Anthropic → Z.AI → Alibaba
════════════════════════════════════════════════════════════════════════════════
"""
        _alert_file = AGENTS_DIR.parent / "ACTIVE_ALERTS.txt"
        try:
            _alert_file.write_text(_human_alert)
            print(f"  HUMAN ALERT written to: {_alert_file}")
        except Exception as e:
            print(f"  WARNING: Could not write alert file: {e}")

        return None, "fleet_credential_failure"

    # 2.6. Load balancing — prefer agents with low queue depth
    # Skip for @mentions (user explicitly chose agent), kublai/subagent,
    # and tasks locked to an agent by skill ownership.
    # EXCEPT: If primary agent is CRITICALLY overloaded, still try load balancing
    # even for explicitly-routed tasks to prevent queue starvation.
    original_agent = agent
    overflow_reason = None
    original_depth = get_queue_depth(agent)

    # Get adaptive thresholds for load balancing decisions
    _lb_thresholds = get_adaptive_thresholds()

    # Load balancing applies to:
    # - Auto-routed tasks (not _caller_provided_agent)
    # - OR explicitly-routed tasks to CRITICALLY overloaded agents (>= adaptive CRITICAL threshold)
    load_balance_needed = (
        agent not in ("kublai", "subagent")
        and not mention_agent
        and not _skill_locked_agent
        and (
            not _caller_provided_agent  # Auto-routed: always load-balance
            or original_depth >= _lb_thresholds['critical']  # Explicit: only if critically overloaded
        )
    )

    if load_balance_needed:
        original_agent = agent
        agent, overflow_reason = find_best_idle_agent(title, agent, _task_domain)

        # Log queue depth for audit
        new_depth = get_queue_depth(agent)
        if overflow_reason and agent != original_agent:
            print(f"LOAD-BALANCE: {original_agent} (queue={original_depth}) -> {agent} (queue={new_depth})")
            _log_overflow(original_agent, agent, title, overflow_reason)

    # 2.6.1. Check if redistribution is needed (log warning if imbalance detected)
    if original_depth > _lb_thresholds['high']:
        redistribution = should_redistribute_tasks()
        if redistribution:
            for ov_agent, underutilized in redistribution:
                un_list = ", ".join([f"{a}(q={d})" for a, d in underutilized])
                print(f"REDISTRIBUTION_NEEDED: {ov_agent}(q={original_depth}) can offload to: {un_list}")

    # 2.6.2. FINAL CREDENTIAL CHECK: Even for explicitly-routed/@mention tasks, verify credentials
    # This catches cases that bypass load balancing (mention_agent=True, _skill_locked_agent=True)
    # For these cases, we escalate rather than silently rerouting
    creds_valid, creds_error = check_agent_credentials(agent)
    if not creds_valid and agent not in ("kublai", "subagent"):
        print(f"CREDENTIAL_ERROR: Final agent '{agent}' has invalid credentials: {creds_error}")
        # For explicit routing (@mentions), we still create the task but with a warning
        # The task will fail at execution time, but at least we logged why
        if mention_agent or _caller_provided_agent:
            print(f"  EXPLICIT_ROUTE: User explicitly chose {agent}, allowing task despite credential issue")
            print(f"  Task will fail at execution — user intervention needed")
        else:
            # For auto-routed tasks with bad credentials, try one last reroute to any healthy agent
            print(f"  AUTO_REROUTE: Attempting last-ditch reroute to any agent with valid credentials")
            for healthy_agent in VALID_AGENTS:
                if healthy_agent != agent and healthy_agent not in ("kublai", "subagent"):
                    hv, _ = check_agent_credentials(healthy_agent)
                    if hv:
                        original_agent = agent
                        agent = healthy_agent
                        print(f"  REROUTED: {original_agent} -> {agent} (credential emergency bypass)")
                        _log_routing_decision(
                            title=title,
                            dest=agent,
                            method="credential_emergency",
                            original_agent=original_agent,
                            domain=_task_domain,
                        )
                        break
            else:
                # No healthy agent found — fleet-wide credential failure
                # Implements behavioral rule: stop creating tasks when all agents broken
                if not (mention_agent or _caller_provided_agent):
                    print(f"FLEET_CREDENTIAL_FAILURE: All dispatch agents have invalid credentials")
                    print(f"  Blocking task creation for '{title[:60]}...'")

                    # CIRCULAR DEPENDENCY DETECTION (2026-03-09)
                    # Check if escalation target (ogedei) is also affected
                    # If ALL agents including ogedei are broken, we have a DEADLOCK
                    _ogedei_valid, _ogedei_err = check_agent_credentials("ogedei")

                    if not _ogedei_valid:
                        # DEADLOCK: ogedei also has invalid credentials
                        # Cannot self-heal — create HUMAN-INTERVENTION task instead
                        print(f"  DEADLOCK detected: Escalation target (ogedei) also has invalid credentials")
                        print(f"  Creating HUMAN-INTERVENTION task at ACTIVE_ALERTS.txt")
                        _human_alert = f"""
════════════════════════════════════════════════════════════════════════════════
🚨 FLEET-WIDE CREDENTIAL DEADLOCK — HUMAN INTERVENTION REQUIRED 🚨
════════════════════════════════════════════════════════════════════════════════
Timestamp: {datetime.now().isoformat()}

PROBLEM: All 7 agents (kublai, temujin, mongke, chagatai, jochi, ogedei, tolui)
have invalid Anthropic API credentials. Escalation target (ogedei) is ALSO broken.

DEADLOCK: Task to fix credentials cannot execute because target agent is broken.

FAILED TASK: {title[:80]}

REQUIRED MANUAL FIX:
1. Obtain valid Anthropic API keys (sk-ant-*) for all 7 agents
2. For each agent in kublai temujin mongke chagatai jochi ogedei tolui:
   a. Edit ~/.openclaw/agents/{{agent}}/.claude/settings.json
   b. Set ANTHROPIC_AUTH_TOKEN to valid sk-ant- key
   c. Verify apiKey is also set (if present)
3. Reset each agent's sessions/sessions.json to {{}}
4. Run: for agent in kublai temujin mongke chagatai jochi ogedei tolui; do
     echo "Checking $agent:"; grep ANTHROPIC_AUTH_TOKEN ~/.openclaw/agents/$agent/.claude/settings.json | cut -c1-10; done

VERIFICATION:
Each agent should show: ANTHROPIC_AUTH_TOKEN": "sk-ant-

Do NOT proceed until ALL 7 agents show sk-ant- prefix.
════════════════════════════════════════════════════════════════════════════════
"""
                        _alert_file = AGENTS_DIR.parent / "ACTIVE_ALERTS.txt"
                        try:
                            _alert_file.write_text(_human_alert)
                            print(f"  HUMAN ALERT written to: {_alert_file}")
                        except Exception as e:
                            print(f"  WARNING: Could not write alert file: {e}")

                        return None, "deadlock_human_intervention_required"
                    else:
                        # ogedei is healthy — can receive escalation
                        print(f"  Creating CRITICAL escalation for ogedei to fix credentials")
                        # Create escalation task for ogedei
                        _escalation_title = f"CRITICAL: Fix fleet-wide credential failure (all agents invalid)"
                        _escalation_body = f"""
All dispatch agents have invalid Anthropic API credentials (no sk-ant- prefix found).

Failed task: {title}
Original target: {agent}
Timestamp: {datetime.now().isoformat()}

Required action:
1. Obtain valid Anthropic API keys (sk-ant-*) for all agents
2. Update each agent's ~/.openclaw/agents/{{agent}}/.claude/settings.json
3. Verify ANTHROPIC_AUTH_TOKEN has sk-ant- prefix
4. Reset sessions/sessions.json to {{}}

This is blocking ALL task execution. Fleet is paralyzed.
"""
                        # Recursively call with explicit agent=ogedei and skip duplicate check
                        # to bypass the same credential check for ogedei
                        _ogedei_queue = AGENTS_DIR / "ogedei" / "tasks"
                        _ogedei_queue.mkdir(parents=True, exist_ok=True)
                        _esc_id = f"cred-fail-{int(time.time())}"
                        _esc_file = _ogedei_queue / f"{_esc_id}.md"
                        _esc_file.write_text(f"# {_escalation_title}\n\n{_escalation_body}")
                        print(f"  ESCALATION created: {_esc_file.name}")
                        return None, "fleet_credential_failure"

    # 2.7. Misroute detection AND correction: cross-check explicit routing against keyword scoring
    # Exempt system-generated task patterns — these use intentional explicit routing
    _MISROUTE_EXEMPT_PREFIXES = (
        "tock assessment", "triage stalled agent", "critical review",
        "critical performance review", "conduct critical", "hourly reflection",
        "load balancer:", "test high task", "test low task",
        "3-hour review", "test-3-hour-review",  # Test tasks for systematic-debugging
    )
    _title_lower_check = title.lower().strip()
    _is_system_task = any(_title_lower_check.startswith(p) for p in _MISROUTE_EXEMPT_PREFIXES)

    if _caller_provided_agent and agent not in ("kublai", "subagent") and not _is_system_task:
        keyword_agent = route_by_text(title)
        if keyword_agent != agent:
            text_lower = title.lower()
            keyword_score = sum(1 for kw in AGENT_KEYWORDS.get(keyword_agent, []) if _kw_match(kw, text_lower))
            caller_score = sum(1 for kw in AGENT_KEYWORDS.get(agent, []) if _kw_match(kw, text_lower))
            # Flag AND CORRECT if keyword router strongly disagrees (score >= 2 AND higher than caller)
            # Removed bare `caller_score == 0` — single keyword_score=1 is too weak to flag
            if keyword_score >= 2 and keyword_score > caller_score:
                print(f"MISROUTE CORRECTION: '{title[:60]}' explicitly routed to {agent} "
                      f"but keywords suggest {keyword_agent} (score {keyword_score} vs {caller_score})")
                print(f"  -> Redirecting to {keyword_agent}")
                _log_routing_decision(
                    title=title,
                    dest=keyword_agent,
                    method="misroute_corrected",
                    scores={keyword_agent: keyword_score, agent: caller_score},
                )
                # Actually correct the routing
                agent = keyword_agent
                _caller_provided_agent = False  # Now using keyword routing

    # 2.8. Log routing decision for audit trail
    if mention_agent:
        _routing_method = "mention"
    elif _explicit_agent_override:
        _routing_method = "keyword"  # Keyword override counts as keyword routing (not explicit)
    elif _caller_provided_agent:
        _routing_method = "explicit"
    else:
        _routing_method = "keyword"

    # Build queue info for audit
    _queue_info = get_all_agent_queue_depths()

    # Classify domain for audit trail (will be re-used when task is created)
    _task_domain = classify_task_domain(title, skill_hint)

    # Skip final log if we already logged in keyword_override section
    # to avoid double-counting routing decisions
    if not _explicit_agent_override:
        _log_routing_decision(
            title=title,
            dest=agent,
            method=_routing_method,
            overflow_reason=overflow_reason if overflow_reason and agent != original_agent else None,
            skill_hint=skill_hint,
            queue_info=_queue_info,
            original_agent=original_agent if original_agent != agent else None,
            domain=_task_domain,
            penalized_scores=_route_metadata.get("penalized_scores") if _route_metadata else None,
            route_metadata=_route_metadata,
            task_source=source,
        )

    # 2.9. Autoresearch approval check — block autonomous research without approval
    if _task_domain == "autoresearch":
        try:
            from autoresearch_approval import AutoresearchApproval
            approval = AutoresearchApproval()

            # Check if agent is enabled for autoresearch
            if not approval._is_agent_enabled(agent):
                print(f"AUTORESEARCH BLOCKED: Agent {agent} not enabled for autoresearch")
                body = f"**AUTORESEARCH NOT ENABLED:** Agent {agent} is not in the enabled_agents list.\n\n{body}"

            # Check max parallel tasks
            max_parallel = approval._policy.get("max_parallel_autonomous_tasks", 3)
            active_count = sum(
                1 for req in approval._requests.values()
                if req.agent == agent and req.status.value in ["pending", "approved"]
            )
            if active_count >= max_parallel:
                print(f"AUTORESEARCH BLOCKED: Agent {agent} has {active_count} active tasks (max: {max_parallel})")
                body = f"**AUTORESEARCH CAP REACHED:** Agent {agent} already has {active_count} active autoresearch tasks (max: {max_parallel}). Please wait for existing tasks to complete.\n\n{body}"

            # Create approval request for autoresearch tasks
            files_to_change = []  # Autoresearch typically doesn't commit files initially
            target_branch = "main"  # Default target

            request_id = approval.propose(
                task_id=f"task-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                agent=agent,
                title=title,
                files=files_to_change,
                target_branch=target_branch,
            )

            if request_id:
                print(f"AUTORESEARCH APPROVAL REQUESTED: {request_id} for task '{title[:60]}'")
                body = f"**AUTORESEARCH PENDING APPROVAL:** Request ID `{request_id}`\n\nKublai will review this autonomous research task. You will be notified via Signal when approval is granted.\n\n{body}"
            else:
                print(f"AUTORESEARCH REJECTED: Could not create approval request for '{title[:60]}'")
                body = f"**AUTORESEARCH REJECTED:** This task requires human approval but could not be queued for review.\n\n{body}"

        except ImportError:
            print("WARNING: autoresearch_approval module not available, proceeding without approval check")
        except Exception as e:
            print(f"ERROR: autoresearch approval check failed: {e}")
            body = f"**AUTORESEARCH ERROR:** Approval system encountered an error: {e}\n\n{body}"

    # 2.10. Force Claude Code preamble
    if force_claude_code:
        body = CLAUDE_CODE_PREAMBLE + body

    # 2.10. Pre-dispatch model validation (prevents executor launch failures)
    is_valid, actual_model, error_msg = validate_agent_model(agent)
    if not is_valid:
        print(f"ERROR: {error_msg}")
        # Log to anomaly ledger for visibility
        try:
            _kp_append_ledger({
                "event": "MODEL_CONFIG_ERROR",
                "agent": agent,
                "model": actual_model,
                "error": error_msg,
                "ts": datetime.now().isoformat(),
            })
        except Exception:
            pass
        # Still create the task but with a warning — ops can fix config
        body = f"**WARNING: Agent model misconfiguration detected ({actual_model}).**\n\n{body}"

    # 3. Alert deduplication with exponential backoff (PRIORITY_FIX: reduce alert spam)
    # Check for recent similar alerts before creating new ones
    suppress_alert, suppress_reason = should_suppress_alert(agent, title, source)
    if suppress_alert:
        print(f"SKIP: alert deduplication active for {agent}: '{title[:60]}'")
        _log_routing_decision(
            title=title,
            dest=agent,
            method="alert_dedup_suppressed",
            metadata={"reason": suppress_reason},
        )
        return None

    # 3.5. Duplicate check (exact prefix + fuzzy keyword overlap)
    if not skip_duplicate_check:
        prefix = title[:40]
        if has_pending_task(agent, prefix, full_title=title):
            print(f"SKIP: duplicate task for {agent}: '{title[:60]}'")
            return None

    # 4-5. Create in Neo4j + filesystem
    try:
        from neo4j_task_tracker import get_tracker
        tracker = get_tracker()
        task_id = tracker.create_task_full(
            agent=agent,
            title=title,
            body=body,
            priority=priority,
            source=source,
            depth=depth,
            parent_id=parent_id,
            skill_hint=skill_hint,
            notify_on_complete=notify_on_complete,
            notify_channel=notify_channel,
            notify_target=notify_target,
            timeout=compute_task_timeout(priority, skill_hint),
            bucket=bucket,
            origin_type=origin_type,
            origin_initiator=origin_initiator,
            origin_source=origin_source,
        )
        if skill_hint:
            print(f"CREATED: {priority} task {task_id} for {agent} (skill: {skill_hint}): {title[:60]}")
        else:
            print(f"CREATED: {priority} task {task_id} for {agent}: {title[:60]}")

        # Link task to conversation if human-initiated
        if CONVERSATION_LOGGER_AVAILABLE and origin_initiator and origin_initiator.startswith("+"):
            try:
                _link_task_to_conversation(
                    task_id=task_id,
                    phone_number=origin_initiator,
                    title=title,
                    body=body,
                    priority=priority,
                    agent=agent,
                    source=source
                )
            except Exception as e:
                print(f"Warning: Failed to link task {task_id} to conversation: {e}")

        # Update kublai dispatch timestamp for self-absorption tracking
        if agent == "kublai":
            _update_kublai_dispatch_timestamp()
        # Append QUEUED event to task ledger (enables pending time measurement)
        try:
            _kp_append_ledger({
                "task_id": task_id, "event": "QUEUED",
                "ts": datetime.now().isoformat(),
                "agent": agent, "priority": priority,
                "task_summary": title[:100], "source": source,
            })
        except Exception:
            pass

        # Record alert for deduplication tracking
        record_alert_created(agent, title, source, task_id)

        return task_id
    except Exception as e:
        print(f"ERROR: Neo4j unavailable, falling back to filesystem-only: {e}")
        # Filesystem-only fallback
        import time
        task_dir = f"{AGENT_DIR}/{agent}/tasks"
        os.makedirs(task_dir, exist_ok=True)
        epoch = int(time.time())
        filepath = f"{task_dir}/{priority}-{epoch}.md"
        skill_line = f"skill_hint: {skill_hint}\n" if skill_hint else ""
        notify_lines = ""
        if notify_on_complete:
            notify_lines = f"notify_on_complete: true\nnotify_channel: {notify_channel}\nnotify_target: {notify_target}\n"

        # Auto-detect origin if not provided
        if origin_type is None:
            if origin_initiator and origin_initiator.startswith("+"):
                origin_type = "human"
            elif source in ("signal", "api"):
                origin_type = "human"
            else:
                origin_type = "agent"
        if origin_source is None:
            origin_source = source

        # Origin metadata for frontmatter
        origin_lines = ""
        if origin_type or origin_initiator or origin_source:
            origin_lines = f"origin:\n  type: {origin_type or 'unknown'}\n"
            if origin_initiator:
                origin_lines += f"  initiator: {origin_initiator}\n"
            if origin_source:
                origin_lines += f"  source: {origin_source}\n"
            origin_lines += f"  timestamp: {datetime.now().isoformat()}\n"

        timeout = compute_task_timeout(priority, skill_hint)
        # Auto-assign bucket based on priority if not provided
        if bucket is None:
            bucket_map = {
                'critical': 'CRITICAL',
                'high': 'TODAY',
                'normal': 'WEEK',
                'low': 'BACKLOG'
            }
            bucket = bucket_map.get(priority, 'BACKLOG')

        # R008: Prominent skill invocation instruction (fixes EXECUTING_NO_OUTPUT)
        skill_instruction = ""
        if skill_hint:
            skill_instruction = f"""---
**IMPORTANT:** This task has a skill hint. You MUST invoke the Skill tool with `{skill_hint}` before starting work.

This is a R008 requirement — skill hints are not optional suggestions, they are mandatory invocation instructions.
---

"""

        content = f"""---
agent: {agent}
priority: {priority}
created: {datetime.now().isoformat()}
source: {source}
depth: {depth}
bucket: {bucket}
timeout: {timeout}
{skill_line}{notify_lines}{origin_lines}---

# Task: {title}

{skill_instruction}{body}
"""
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"CREATED (filesystem-only): {filepath}")

        # Link task to conversation if human-initiated (filesystem fallback)
        if CONVERSATION_LOGGER_AVAILABLE and origin_initiator and origin_initiator.startswith("+"):
            try:
                _link_task_to_conversation(
                    task_id=f"fs-{epoch}",
                    phone_number=origin_initiator,
                    title=title,
                    body=body,
                    priority=priority,
                    agent=agent,
                    source=source
                )
            except Exception as e:
                print(f"Warning: Failed to link task fs-{epoch} to conversation: {e}")

        # Update kublai dispatch timestamp for self-absorption tracking
        if agent == "kublai":
            _update_kublai_dispatch_timestamp()
        # Append QUEUED event to task ledger (filesystem-only fallback path)
        try:
            _kp_append_ledger({
                "task_id": f"fs-{epoch}", "event": "QUEUED",
                "ts": datetime.now().isoformat(),
                "agent": agent, "priority": priority,
                "task_summary": title[:100], "source": source,
            })
        except Exception:
            pass
        return f"fs-{epoch}"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Task Intake — single entry point for task creation")
    parser.add_argument("--title", required=False, help="Task title")
    parser.add_argument("--body", default="", help="Task body")
    parser.add_argument("--priority", default="normal", choices=["high", "normal", "low"])
    parser.add_argument("--agent", default=None, help="Target agent (auto-routed if omitted)")
    parser.add_argument("--source", default="cli", help="Task source")
    parser.add_argument("--skill-hint", default=None, help="Explicit skill hint (overrides auto-detection)")
    parser.add_argument("--force-claude-code", action="store_true", help="Prepend Claude Code ACP invocation instruction")
    parser.add_argument("--notify-on-complete", action="store_true", help="Send Signal notification when task completes")
    parser.add_argument("--notify-channel", default="signal", help="Notification channel (default: signal)")
    parser.add_argument("--notify-target", default="+19194133445", help="Notification target (default: +19194133445)")
    parser.add_argument("--status", action="store_true", help="Show queue status and exit")
    parser.add_argument("--redistribute-check", action="store_true", help="Check if redistribution is needed and exit")
    args = parser.parse_args()

    if args.status:
        print("\n=== Kurultai Queue Status ===")
        depths = get_all_agent_queue_depths()
        loads = {agent: get_agent_load(agent) for agent in VALID_AGENTS}

        # Get adaptive thresholds for status display
        thresholds = get_adaptive_thresholds()
        HIGH_THRESHOLD = thresholds['high']
        CRITICAL_THRESHOLD = thresholds['critical']
        LOW_THRESHOLD = thresholds['low']
        load_factor = thresholds['load_factor']

        print(f"\n{'Agent':<12} {'Pending':<8} {'Exec':<6} {'Total':<6} {'Status'}")
        print("-" * 50)

        for agent in sorted(VALID_AGENTS):
            load = loads[agent]
            depth = depths[agent]
            status = []
            if depth >= CRITICAL_THRESHOLD:
                status.append("CRITICAL")
            elif depth >= HIGH_THRESHOLD:
                status.append("HIGH")
            elif depth < LOW_THRESHOLD:
                status.append("UNDERUTILIZED")
            if is_agent_busy(agent):
                status.append("BUSY")
            status_str = ", ".join(status) if status else "OK"
            print(f"{agent:<12} {load['pending']:<8} {load['executing']:<6} {depth:<6} {status_str}")

        print("\n--- Adaptive Thresholds ---")
        print(f"Load Factor: {load_factor:.2f}")
        print(f"High: {HIGH_THRESHOLD} | Critical: {CRITICAL_THRESHOLD} | Underutilized: <{LOW_THRESHOLD}")

        redistribution = should_redistribute_tasks()
        if redistribution:
            print("\n--- Redistribution Recommended ---")
            for ov_agent, underutilized in redistribution:
                un_list = ", ".join([f"{a}(q={d})" for a, d in underutilized])
                print(f"  {ov_agent}(q={depths[ov_agent]}) -> offload to: {un_list}")
        else:
            print("\n--- Load Balanced ---")
        sys.exit(0)

    if args.redistribute_check:
        redistribution = should_redistribute_tasks()
        if redistribution:
            print("REDISTRIBUTION_NEEDED")
            for ov_agent, underutilized in redistribution:
                un_list = ", ".join([f"{a}:{d}" for a, d in underutilized])
                print(f"{ov_agent} -> {un_list}")
            sys.exit(1)
        else:
            print("BALANCED")
            sys.exit(0)

    task_id = create_task(
        title=args.title,
        body=args.body or f"Task: {args.title}",
        priority=args.priority,
        source=args.source,
        agent=args.agent,
        skill_hint=args.skill_hint,
        force_claude_code=args.force_claude_code,
        notify_on_complete=args.notify_on_complete,
        notify_channel=args.notify_channel,
        notify_target=args.notify_target,
    )
    if task_id:
        print(f"Task ID: {task_id}")
    else:
        print("Task creation rejected")
        sys.exit(1)
