#!/usr/bin/env python3
"""
task_intake.py — Single entry point for all task creation.

Pipeline:
    1. Validate depth (reject if >= MAX_DEPTH)
    2. Route via canonical router (task_router.py)
    3. Duplicate check (has_pending_task)
    4. Create in Neo4j (primary) via create_task_full()
    5. Write filesystem (backward compat, done by create_task_full)

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
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kurultai_paths import AGENTS_DIR, LOGS_DIR, agent_tasks_dir
from kurultai_ledger import append_ledger as _kp_append_ledger

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
VALID_DOMAINS = {"research", "implementation", "ops", "documentation", "strategy", "analysis"}

# Domain-to-agent compatibility matrix for redistribution
# Agents listed can receive tasks of that domain via load balancing or redistribution
DOMAIN_AGENT_COMPATIBILITY = {
    "research": ["mongke"],
    "implementation": ["temujin", "ogedei"],
    "ops": ["ogedei", "temujin"],
    "documentation": ["chagatai"],
    "strategy": ["temujin", "kublai"],
    "analysis": ["jochi", "mongke"],
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
}

# Domain classification by keyword matching (fallback when no skill hint)
DOMAIN_KEYWORDS = {
    "research": [
        "research", "discover", "competitor", "market", "study", "benchmark",
        "survey", "literature", "paper", "citation", "documentation research",
        "api discovery", "product analysis", "feature analysis", "pricing research",
        "ecosystem", "alternatives", "comparison", "market intel", "source triangulation",
        "fact check", "investigate sources", "data gathering", "research methodology",
        "evidence"
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
}


def classify_task_domain(task_text, skill_hint=None):
    """Classify task into domain based on skill hints and keywords.

    Args:
        task_text: Task title or body text
        skill_hint: Optional skill hint (takes precedence over keywords)

    Returns:
        Domain string: "research", "implementation", "ops", "documentation", "strategy", or "analysis"
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


# Valid agents for @mention direct routing
VALID_AGENTS = {"temujin", "mongke", "chagatai", "jochi", "ogedei", "kublai", "tolui"}

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


# Minimal routing table -- source of truth is kurultai-router SKILL.md
# This is the fallback for programmatic task creation (cron, heartbeat, etc.)
AGENT_KEYWORDS = {
    "temujin": ["code", "build", "implement", "fix", "deploy", "design", "architect",
                "bug", "feature", "api", "script", "brainstorm", "payment", "protocol",
                "refactor", "scaffold", "endpoint", "database", "schema", "sdk",
                "integrate", "migration", "configure", "setup", "create",
                "frontend", "ui", "kanban", "sort", "component", "react", "next"],
    "mongke": ["research", "discover", "competitor", "market", "trend", "study",
               "landscape", "benchmark", "survey", "literature", "paper", "citation",
               "documentation research", "api discovery", "product analysis", "feature analysis",
               "pricing research", "ecosystem", "alternatives", "comparison", "market intel",
               "source triangulation", "fact check", "investigate sources", "data gathering",
               "report findings", "gather sources", "research methodology", "evidence"],
    # Removed: "investigate", "explore", "analyze", "evaluate", "find", "compare" (too generic, overlap with other agents)
    # Removed: "source", "gather", "collect" (weak matches, added context-specific variants)
    "chagatai": ["write", "document", "blog", "content", "changelog", "copy", "article",
                 "social", "twitter", "marketing", "announcement", "readme", "presence",
                 "draft", "summarize", "summary", "guide", "tutorial", "outline",
                 "proposal", "narrative", "describe", "explain", "release notes",
                 "documentation", "docs", "communicate", "memo"],
    "jochi": ["test", "verify", "audit", "review", "security", "analyze", "vulnerability",
              "error", "debug", "scan", "prompt injection", "compliance", "validate",
              "performance", "unauthorized", "anomaly", "score", "investigate", "spike",
              "crash", "fatal", "failure", "stalled", "triage", "check", "detect"],
    "ogedei": ["monitor", "health", "restart", "backup", "alert", "uptime", "cron",
               "incident", "status", "queue", "pipeline", "watchdog", "cleanup",
               "disk", "memory", "process", "fix", "error", "failure", "deploy",
               "railway", "domain", "generate", "api", "auth", "401", "log", "report",
               "configure", "vercel", "server", "gateway", "timeout", "recover"],
    "kublai": ["triage", "coordinate", "prioritize", "system-wide", "assessment", "status assessment",
               "agent status", "backlog", "routing", "dispatch", "workload"],
    "tolui": ["truth", "honest", "brutal", "verify", "completion", "fake", "bs", "quality gate",
              "call out", "assessment", "review", "calling out", "scope creep", "unrealistic"],
}

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
    ({"design", "research"}, "temujin"),
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
    ({"investigate", "model"}, "ogedei"),
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
    # Design/architecture tasks -> temujin (not mongke)
    ({"design", "schema"}, "temujin"),                 # schema design -> dev
    ({"design", "neo4j"}, "temujin"),                  # neo4j design -> dev
    ({"brainstorm", "schema"}, "temujin"),             # schema brainstorm -> dev
    ({"brainstorm", "neo4j"}, "temujin"),              # neo4j brainstorm -> dev
    ({"proposal", "voting"}, "temujin"),               # voting system design -> dev
    ({"voting", "system"}, "temujin"),                 # voting system -> dev
]

def _kw_match(kw, text_lower):
    """Match a keyword against text using word boundaries for single words,
    plain substring for multi-word phrases. Prevents false positives like
    'ui' matching inside 'build' or 'api' matching inside 'capital'."""
    if ' ' in kw:
        return kw in text_lower
    return bool(re.search(r'\b' + re.escape(kw) + r'\b', text_lower))


def route_by_text(text):
    """Keyword routing for programmatic task creation with disambiguation."""
    text_lower = text.lower()

    # Check disambiguation rules first (first-match-wins)
    for keywords_set, target in _DISAMBIGUATION:
        if all(_kw_match(kw, text_lower) for kw in keywords_set):
            return target

    best, best_score = "temujin", 0
    for agent, keywords in AGENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if _kw_match(kw, text_lower))
        if score > best_score:
            best, best_score = agent, score
    return best

# --- LOAD BALANCING CONFIGURATION ---

# Queue depth thresholds
# Previous values (20/30/5) were too permissive — load balancing never fired.
# Temujin accumulated 9+ tasks while idle agents available (2026-03-07 review).
QUEUE_HIGH_THRESHOLD = 3       # Route to alternate if primary > this
QUEUE_CRITICAL_THRESHOLD = 8   # Broadcast to all capable agents if primary > this
QUEUE_LOW_THRESHOLD = 2        # Consider agent underutilized if < this

# Failure-rate routing bypass — agents failing > this rate are treated as overloaded
AGENT_FAILURE_BYPASS_THRESHOLD = 0.80   # 80% failure rate in recent window
AGENT_FAILURE_WINDOW_H = 2             # Look-back window for failure rate
AGENT_FAILURE_MIN_TASKS = 3            # Minimum terminal tasks before applying bypass

# Agent capability overlap matrix for cross-training overflow
# Maps: primary_agent -> [(alternate_agent, [task_keywords]), ...]
AGENT_CAPABILITY_MATRIX = {
    "temujin": [
        # mongke can handle PURE research tasks from temujin — NOT mixed dev+research
        # Removed "investigate" (overlaps with dev debugging: "investigate and fix...")
        # Removed "explore" (overlaps with dev: "explore codebase", "explore approach")
        ("mongke", ["research", "discover", "benchmark", "study", "competitor", "market analysis"]),
        # jochi can handle testing/QA tasks from temujin
        ("jochi", ["test", "testing", "verify", "audit", "review code", "QA", "quality"]),
        # ogedei can handle deployment/ops tasks AND implementation tasks from temujin
        # Added "implement" per 2026-03-08 routing audit: ogedei is in DOMAIN_AGENT_COMPATIBILITY["implementation"]
        ("ogedei", ["deploy", "railway", "docker", "container", "infrastructure", "monitor", "restart", "cleanup", "implement", "build"]),
        # chagatai can handle documentation tasks from temujin
        ("chagatai", ["document", "documentation", "write", "readme", "changelog", "content"]),
    ],
    "jochi": [
        ("temujin", ["debug", "fix", "error", "crash", "investigate bug"]),
        ("ogedei", ["security audit", "vulnerability scan", "compliance check"]),
    ],
    "mongke": [
        ("chagatai", ["write", "document findings", "summarize research", "content"]),
    ],
    "chagatai": [
        ("mongke", ["research topic", "gather sources", "investigate trend"]),
    ],
    "ogedei": [
        ("temujin", ["fix script", "code cleanup", "automation", "tooling"]),
        ("jochi", ["health check", "diagnostic", "monitor verification"]),
    ],
}

# Legacy overflow map (kept for compatibility with existing code)
OVERFLOW_MAP = {
    # (primary_agent, task_category): [overflow_agents in priority order]
    ("temujin", "code_review"):     ["jochi"],
    ("temujin", "deploy"):          ["ogedei"],
    ("temujin", "infrastructure"):  ["ogedei"],
    ("temujin", "testing"):         ["jochi"],
    ("jochi", "code_review"):       ["temujin"],
    ("jochi", "security"):          ["temujin", "ogedei"],
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
    "research": ["research", "investigate", "discover", "explore", "competitor"],
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
        if '.done' in fname or fname.startswith('.') or fname == 'archived-20260303':
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


def find_underutilized_agents(exclude=None):
    """Find agents with queue depth below QUEUE_LOW_THRESHOLD.

    Args:
        exclude: set of agent names to exclude

    Returns list of (agent, depth) tuples sorted by depth ascending.
    """
    exclude = exclude or set()
    underutilized = []
    for agent in VALID_AGENTS:
        if agent in exclude:
            continue
        depth = get_queue_depth(agent)
        if depth < QUEUE_LOW_THRESHOLD:
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


def find_best_agent_by_load(task_text, primary_agent, task_domain=None):
    """Find the best agent considering queue depth and capabilities.

    Algorithm:
    1. If primary agent queue < QUEUE_HIGH_THRESHOLD, use primary
    2. Find underutilized agents (< QUEUE_LOW_THRESHOLD) with capability match
    3. If primary > QUEUE_CRITICAL_THRESHOLD, broadcast to all capable agents
    4. Otherwise, route to lowest-depth capable alternate
    5. Fall back to primary if no alternates available

    If task_domain is provided, only agents in DOMAIN_AGENT_COMPATIBILITY[task_domain]
    will be considered as valid alternates.

    Returns (agent, reason) tuple.
    """
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
    if primary_depth < QUEUE_HIGH_THRESHOLD:
        return primary_agent, f"primary queue={primary_depth} < threshold={QUEUE_HIGH_THRESHOLD}"

    # Find capable alternates sorted by queue depth
    capable_alternates = get_capable_alternates(primary_agent, task_text, task_domain)

    # Filter to underutilized agents (queue < QUEUE_LOW_THRESHOLD=2)
    underutilized = [(agent, depth) for agent, depth in capable_alternates
                     if depth < QUEUE_LOW_THRESHOLD]

    if underutilized:
        best_agent, best_depth = underutilized[0]
        return best_agent, f"load-balance: {primary_agent} queue={primary_depth}, {best_agent} underutilized (queue={best_depth})"

    # Primary queue is critical - broadcast to all capable
    if primary_depth >= QUEUE_CRITICAL_THRESHOLD and capable_alternates:
        best_agent, best_depth = capable_alternates[0]
        # Log broadcast for audit
        _log_routing_decision(
            title=task_text,
            dest=best_agent,
            method="broadcast_overflow",
            overflow_reason=f"{primary_agent} queue={primary_depth} >= {QUEUE_CRITICAL_THRESHOLD}, routing to lowest alternate"
        )
        return best_agent, f"broadcast: {primary_agent} critical queue={primary_depth}, routing to {best_agent} (queue={best_depth})"

    # Use any capable alternate with lower queue than primary
    if capable_alternates:
        for alt_agent, alt_depth in capable_alternates:
            if alt_depth < primary_depth:
                return alt_agent, f"load-balance: {primary_agent} queue={primary_depth}, {alt_agent} lower (queue={alt_depth})"
        # All alternates also busy - use lowest anyway
        best_agent, best_depth = capable_alternates[0]
        return best_agent, f"load-balance: all busy, {primary_agent} queue={primary_depth}, using {best_agent} (queue={best_depth})"

    # No capable alternates - queue to primary
    return primary_agent, f"no capable alternates, queuing to {primary_agent} (queue={primary_depth})"


def should_redistribute_tasks():
    """Check if redistribution is needed - any agent overloaded while another underutilized.

    Returns list of (overloaded_agent, underutilized_agents) tuples.
    """
    depths = get_all_agent_queue_depths()
    overloaded = [(agent, depth) for agent, depth in depths.items()
                  if depth > QUEUE_HIGH_THRESHOLD]
    underutilized = [(agent, depth) for agent, depth in depths.items()
                     if depth < QUEUE_LOW_THRESHOLD]

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


def get_agent_scores(text):
    """Score all agents for a given task text. Returns dict of {agent: score}."""
    text_lower = text.lower()
    scores = {}
    for agent, keywords in AGENT_KEYWORDS.items():
        scores[agent] = sum(1 for kw in keywords if _kw_match(kw, text_lower))
    return scores


# Agents that should not receive load-balanced overflow tasks
_NO_OVERFLOW_TARGETS = {"kublai", "tolui"}

def find_best_idle_agent(text, primary_agent, task_domain=None):
    """Find the best agent considering queue depth and idle status.

    Uses queue-aware load balancing:
    1. Check queue depth before assigning
    2. If target agent queue >= QUEUE_HIGH_THRESHOLD (3) AND another agent has capacity, route to available agent
    3. Use capability matrix (AGENT_CAPABILITY_MATRIX) for cross-training
    4. Fall back to OVERFLOW_MAP by task category, then find_best_agent_by_load()

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
    primary_depth = get_queue_depth(primary_agent)

    # Check if primary agent has a high failure rate — bypass to alternates
    if is_agent_failing(primary_agent):
        capable_alternates = get_capable_alternates(primary_agent, text, task_domain)
        healthy_alts = [(a, d) for a, d in capable_alternates if not is_agent_failing(a)]
        if healthy_alts:
            best_agent, best_depth = healthy_alts[0]
            rate, _ = get_agent_failure_rate(primary_agent)
            return best_agent, f"failure-bypass: {primary_agent} failure_rate={rate:.0%}, routing to {best_agent} (queue={best_depth})"

    # If primary is idle AND has low queue, use it directly
    if not is_agent_busy(primary_agent) and primary_depth < QUEUE_HIGH_THRESHOLD:
        return primary_agent, f"primary idle, queue={primary_depth}"

    # Try to find an underutilized agent with capability match
    capable_alternates = get_capable_alternates(primary_agent, text, task_domain)
    underutilized = [(agent, depth) for agent, depth in capable_alternates
                     if depth < QUEUE_LOW_THRESHOLD]

    if underutilized:
        best_agent, best_depth = underutilized[0]
        return best_agent, f"load-balance: {primary_agent} busy/loaded (queue={primary_depth}), {best_agent} underutilized (queue={best_depth})"

    # Check overflow map for category-specific idle agents (legacy support)
    category = _detect_category(text)
    if category:
        overflow_agents = OVERFLOW_MAP.get((primary_agent, category), [])
        for overflow in overflow_agents:
            if not is_agent_busy(overflow):
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


def _log_routing_decision(title, dest, method, overflow_reason=None, skill_hint=None, scores=None, queue_info=None, original_agent=None, domain=None):
    """Append routing decision to JSONL log for routing_audit.py consumption.

    Enhanced logging (2026-03-08): includes alt_scores, idle_agents, would_overflow
    for missed opportunity analysis.
    """
    try:
        entry = {
            "ts": datetime.now().isoformat(),
            "task": title[:100],
            "dest": dest,
            "method": method,
        }
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

        # Identify idle agents (queue=0 and not busy)
        idle = []
        for agent_name in VALID_AGENTS:
            if queue_info and queue_info.get(agent_name, 0) == 0 and not is_agent_busy(agent_name):
                idle.append(agent_name)
        entry["idle_agents"] = idle

        # Detect if this routing would trigger overflow (dest queue >= threshold and idle alternatives exist)
        dest_queue = queue_info.get(dest, 0) if queue_info else 0
        would_overflow = dest_queue >= QUEUE_HIGH_THRESHOLD and len(idle) > 0 and dest not in idle
        entry["would_overflow"] = would_overflow

        # Track if routing was changed from original (load balancing)
        if original_agent and original_agent != dest:
            entry["load_balanced_from"] = original_agent

        os.makedirs(os.path.dirname(ROUTING_LOG), exist_ok=True)
        with open(ROUTING_LOG, "a") as f:
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
    # 1. Validate depth
    if depth >= MAX_TASK_DEPTH:
        print(f"REJECT: depth={depth} >= {MAX_TASK_DEPTH} for '{title[:60]}'")
        return None

    # 2. Route: check @mention first, then keyword routing
    mention_agent = None
    _caller_provided_agent = agent is not None
    if agent is None:
        mention_agent, stripped_title = parse_mention(title)
        if mention_agent:
            agent = mention_agent
            title = stripped_title  # Use the message body without @mention prefix
            source = "direct-mention"
        else:
            agent = route_by_text(title)
            if agent == "subagent":
                agent = "kublai"  # Default fallback

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

    # 2.6. Load balancing — prefer agents with low queue depth
    # Skip for @mentions (user explicitly chose agent), kublai/subagent,
    # and tasks locked to an agent by skill ownership.
    # EXCEPT: If primary agent is CRITICALLY overloaded, still try load balancing
    # even for explicitly-routed tasks to prevent queue starvation.
    original_agent = agent
    overflow_reason = None
    original_depth = get_queue_depth(agent)

    # Load balancing applies to:
    # - Auto-routed tasks (not _caller_provided_agent)
    # - OR explicitly-routed tasks to CRITICALLY overloaded agents (>= QUEUE_CRITICAL_THRESHOLD)
    load_balance_needed = (
        agent not in ("kublai", "subagent")
        and not mention_agent
        and not _skill_locked_agent
        and (
            not _caller_provided_agent  # Auto-routed: always load-balance
            or original_depth >= QUEUE_CRITICAL_THRESHOLD  # Explicit: only if critically overloaded
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
    if original_depth > QUEUE_HIGH_THRESHOLD:
        redistribution = should_redistribute_tasks()
        if redistribution:
            for ov_agent, underutilized in redistribution:
                un_list = ", ".join([f"{a}(q={d})" for a, d in underutilized])
                print(f"REDISTRIBUTION_NEEDED: {ov_agent}(q={original_depth}) can offload to: {un_list}")

    # 2.7. Misroute detection: cross-check explicit routing against keyword scoring
    # Exempt system-generated task patterns — these use intentional explicit routing
    _MISROUTE_EXEMPT_PREFIXES = (
        "tock assessment", "triage stalled agent", "critical review",
        "critical performance review", "conduct critical", "hourly reflection",
        "load balancer:", "test high task", "test low task",
    )
    _title_lower_check = title.lower().strip()
    _is_system_task = any(_title_lower_check.startswith(p) for p in _MISROUTE_EXEMPT_PREFIXES)

    if _caller_provided_agent and agent not in ("kublai", "subagent") and not _is_system_task:
        keyword_agent = route_by_text(title)
        if keyword_agent != agent:
            text_lower = title.lower()
            keyword_score = sum(1 for kw in AGENT_KEYWORDS.get(keyword_agent, []) if _kw_match(kw, text_lower))
            caller_score = sum(1 for kw in AGENT_KEYWORDS.get(agent, []) if _kw_match(kw, text_lower))
            # Flag if keyword router strongly disagrees (score >= 2 AND higher than caller)
            # Removed bare `caller_score == 0` — single keyword_score=1 is too weak to flag
            if keyword_score >= 2 and keyword_score > caller_score:
                print(f"MISROUTE WARNING: '{title[:60]}' explicitly routed to {agent} "
                      f"but keywords suggest {keyword_agent} (score {keyword_score} vs {caller_score})")
                _log_routing_decision(
                    title=title,
                    dest=agent,
                    method="explicit_misroute",
                    scores={keyword_agent: keyword_score, agent: caller_score},
                )

    # 2.8. Log routing decision for audit trail
    if mention_agent:
        _routing_method = "mention"
    elif _caller_provided_agent:
        _routing_method = "explicit"
    else:
        _routing_method = "keyword"

    # Build queue info for audit
    _queue_info = get_all_agent_queue_depths()

    # Classify domain for audit trail (will be re-used when task is created)
    _task_domain = classify_task_domain(title, skill_hint)

    _log_routing_decision(
        title=title,
        dest=agent,
        method=_routing_method,
        overflow_reason=overflow_reason if overflow_reason and agent != original_agent else None,
        skill_hint=skill_hint,
        queue_info=_queue_info,
        original_agent=original_agent if original_agent != agent else None,
        domain=_task_domain,
    )

    # 2.9. Force Claude Code preamble
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

    # 3. Duplicate check (exact prefix + fuzzy keyword overlap)
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

{body}
"""
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"CREATED (filesystem-only): {filepath}")
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
    parser.add_argument("--title", required=True, help="Task title")
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

        print(f"\n{'Agent':<12} {'Pending':<8} {'Exec':<6} {'Total':<6} {'Status'}")
        print("-" * 50)

        for agent in sorted(VALID_AGENTS):
            load = loads[agent]
            depth = depths[agent]
            status = []
            if depth >= QUEUE_CRITICAL_THRESHOLD:
                status.append("CRITICAL")
            elif depth >= QUEUE_HIGH_THRESHOLD:
                status.append("HIGH")
            elif depth < QUEUE_LOW_THRESHOLD:
                status.append("UNDERUTILIZED")
            if is_agent_busy(agent):
                status.append("BUSY")
            status_str = ", ".join(status) if status else "OK"
            print(f"{agent:<12} {load['pending']:<8} {load['executing']:<6} {depth:<6} {status_str}")

        print("\n--- Thresholds ---")
        print(f"High: {QUEUE_HIGH_THRESHOLD} | Critical: {QUEUE_CRITICAL_THRESHOLD} | Underutilized: <{QUEUE_LOW_THRESHOLD}")

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
