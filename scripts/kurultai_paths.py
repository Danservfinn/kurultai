"""
kurultai_paths.py — Single source of truth for all Kurultai filesystem paths.

Every script that needs agent directories, task queues, logs, or ledger paths
should import from here instead of defining its own constants.

Usage:
    from kurultai_paths import AGENTS_DIR, agent_tasks_dir, TASK_LEDGER
"""

import os
from pathlib import Path

# Root directories
OPENCLAW_DIR = Path.home() / ".openclaw"
AGENTS_DIR = OPENCLAW_DIR / "agents"
MAIN_DIR = AGENTS_DIR / "main"

# Logs and state
LOGS_DIR = MAIN_DIR / "logs"
TASK_LEDGER = OPENCLAW_DIR / "tasks" / "task-ledger.jsonl"
SPAWN_QUEUE = LOGS_DIR / "spawn-pending.json"
WATCHER_STATE = LOGS_DIR / "task-watcher-state.json"
DISPATCH_STATE = LOGS_DIR / "auto-dispatch-state.json"
DISPATCH_LOG = LOGS_DIR / "auto-dispatch.jsonl"
PROPOSALS_DIR = MAIN_DIR / "proposals"
SCRIPTS_DIR = MAIN_DIR / "scripts"
BRAINSTORM_LOG = LOGS_DIR / "kurultai-brainstorm.log"
BRAINSTORM_COOLDOWN = LOGS_DIR / "brainstorm-cooldown.json"
BRAINSTORM_DOMAIN_ROTATION = LOGS_DIR / "brainstorm-domain-rotation.json"

# Valid agent names (all agents in kurultai.json)
VALID_AGENTS = frozenset({"kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"})
DISPATCH_AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]

# Agent routing keywords (canonical source)
AGENT_KEYWORDS = {
    "temujin": ["code", "build", "implement", "fix", "deploy", "design", "architect",
                "bug", "feature", "api", "script", "brainstorm", "payment", "protocol",
                "refactor", "scaffold", "endpoint", "database", "schema", "sdk",
                "integrate", "migration", "configure", "setup", "create",
                "frontend", "ui", "kanban", "sort", "component", "react", "next"],
    "mongke": ["research", "discover", "competitor", "competitive", "market", "trend", "study", "exploration",
               "landscape", "benchmark", "survey", "literature", "paper", "citation",
               "documentation research", "api discovery", "product analysis", "feature analysis",
               "pricing research", "ecosystem", "alternatives", "comparison", "compare", "market intel",
               "source triangulation", "fact check", "investigate sources", "data gathering",
               "report findings", "gather sources", "research methodology", "evidence",
               "competitor analysis", "market analysis", "pricing analysis", "trend analysis",
               "landscape analysis", "find sources", "source verification", "validate sources",
               "competitive intel", "market research", "competitor research", "industry analysis",
               "web research", "lookup", "find information", "investigate market", "investigate competitor",
               "pricing benchmark", "feature comparison", "product comparison", "api research",
               # AI/LLM research terms (2026-03-11) — model providers, comparisons, benchmarks
               "llm", "gpt", "claude", "anthropic", "openai", "alibaba", "z.ai", "dashscope",
               "model comparison", "ai model", "language model", "embedding", "vector", "rag",
               "model benchmark", "ai pricing", "api pricing comparison", "provider comparison",
               "model research", "ai research", "llm evaluation", "model capabilities",
               "context window", "token limit", "rate limit", "model features", "ai provider"],
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
               "disk", "memory", "process", "fix", "failure", "deploy",
               "railway", "domain", "generate", "api", "auth", "401", "log", "report",
               "configure", "vercel", "server", "gateway", "timeout", "recover",
               "throughput", "failure rate", "fleet"],  # ops metrics (2026-03-12)
               # NOTE (2026-03-23): removed "error" — too generic, causes "fix X error" to route
               # to ogedei when the task is code-focused (temujin domain). Specific ops keywords
               # like "failure", "alert", "monitor" are sufficient for ops error tasks.
    "kublai": ["triage", "coordinate", "prioritize", "system-wide", "assessment", "status assessment",
               "agent status", "backlog", "routing", "dispatch", "workload"],
    "tolui": ["truth", "honest", "brutal", "verify", "completion", "fake", "bs", "quality gate",
              "call out", "assessment", "review", "calling out", "scope creep", "unrealistic"],
}


# =============================================================================
# PROJECT REGISTRY — Maps project roots to deploy configuration
# =============================================================================

from typing import Optional

PROJECT_REGISTRY = {
    "/Users/kublai/projects/parse-for-agents": {
        "name": "parse-for-agents",
        "repo": "Danservfinn/parse-for-agents",
        "branch": "main",
        "test_cmd": "npm test",
        "build_cmd": "npm run typecheck",
        "deploy_type": "railway",
        "health_url": "https://parse-for-agents-production.up.railway.app/health",
        "auto_merge": True,
        "allowed_agents": ["temujin"],
        "docs_agents": ["chagatai"],
    },
    "/Users/kublai/projects/parsethe.media": {
        "name": "parsethe.media",
        "repo": "Danservfinn/parse",
        "branch": "main",
        "test_cmd": "npm run test:run --if-present",
        "build_cmd": "npm run build",
        "deploy_type": "railway",
        "health_url": "https://api.parsethe.media/api/health",
        "auto_merge": False,
        "allowed_agents": ["temujin"],
        "docs_agents": ["chagatai"],
    },
    str(OPENCLAW_DIR): {
        "name": "kurultai-scripts",
        "repo": "Danservfinn/kurultai-scripts",
        "branch": "main",
        "test_cmd": None,
        "build_cmd": None,
        "deploy_type": "none",
        "health_url": None,
        "auto_merge": False,
        "allowed_agents": ["temujin", "ogedei"],
        "docs_agents": ["chagatai"],
    },
}

DEPLOY_AGENTS = frozenset({"temujin"})


def agent_worktree_dir(agent: str, project_name: str) -> Path:
    """Return the worktree directory for an agent working on a specific project."""
    return AGENTS_DIR / agent / "worktrees" / project_name


def project_for_path(file_path: str) -> Optional[dict]:
    """Given a file path, return the matching PROJECT_REGISTRY entry or None."""
    for root, config in PROJECT_REGISTRY.items():
        if file_path.startswith(root):
            return {**config, "root": root}
    return None


# =============================================================================
# CLAUDE_AGENT Binary Validation (Security)
# =============================================================================

def _validate_claude_agent() -> Path:
    """Validate CLAUDE_AGENT binary exists and is executable.

    Security checks:
    1. Binary exists at expected path
    2. Binary is executable
    3. Symlink validation (if symlink, check target is in expected location)

    Returns:
        Path to validated claude-agent binary

    Raises:
        RuntimeError: If validation fails
    """
    agent_path = Path.home() / ".local" / "bin" / "claude-agent"

    if not agent_path.exists():
        raise RuntimeError(f"CLAUDE_AGENT not found: {agent_path}")

    # Check if it's a symlink
    if agent_path.is_symlink():
        target = os.path.realpath(agent_path)
        # Allow symlinks to common locations
        allowed_prefixes = [
            "/usr/local/bin/",
            "/opt/",
            "/home/",
            "/Users/",
            str(Path.home()),
        ]
        if not any(target.startswith(p) for p in allowed_prefixes):
            raise RuntimeError(
                f"CLAUDE_AGENT symlink to unexpected location: {target}. "
                f"Allowed prefixes: {allowed_prefixes}"
            )

    # Check executable
    if not os.access(agent_path, os.X_OK):
        raise RuntimeError(f"CLAUDE_AGENT not executable: {agent_path}")

    return agent_path


# Claude agent binary - validated at import time
try:
    CLAUDE_AGENT = _validate_claude_agent()
except RuntimeError as e:
    # Log warning but don't fail import - validation happens at runtime
    print(f"[WARN] CLAUDE_AGENT validation failed: {e}")
    CLAUDE_AGENT = Path.home() / ".local" / "bin" / "claude-agent"


def agent_tasks_dir(agent: str) -> Path:
    """Return the canonical task queue directory for an agent."""
    return AGENTS_DIR / agent / "tasks"


def agent_workspace_dir(agent: str) -> Path:
    """Return the workspace directory for an agent."""
    return AGENTS_DIR / agent / "workspace"


def agent_memory_dir(agent: str) -> Path:
    """Return the memory directory for an agent."""
    return AGENTS_DIR / agent / "memory"


def agent_config_path(agent: str) -> Path:
    """Return the config.json path for an agent."""
    return AGENTS_DIR / agent / "config.json"


def agent_sessions_path(agent: str) -> Path:
    """Return the sessions.json path for an agent."""
    return AGENTS_DIR / agent / "sessions" / "sessions.json"


# Session bloat threshold (bytes) - auto-reset when exceeded
SESSION_BLOAT_THRESHOLD = 15_000  # 15KB


# =============================================================================
# TIMEOUT CONSTANTS (Consolidated from scattered definitions)
# =============================================================================

# Task Execution Timeouts
CLAUDE_TIMEOUT = 10800  # 3 hours (aligned with agent-task-handler operational value)
STALE_EXECUTING_SECS = 900  # 15 minutes - task-watcher stale detection
STALE_REVERT_SECS = 1200  # 20 min — auto_dispatch uses this for .executing reversion (intentionally > STALE_EXECUTING_SECS)
TASK_WATCHER_INTERVAL = 60  # seconds between checks

# Priority-based timeouts
TIMEOUT_BY_PRIORITY = {
    'critical': 3600,  # 1 hour (from kublai_task_optimizer)
    'high': 10800,     # 3 hours
    'normal': 10800,   # 3 hours
    'low': 7200,       # 2 hours
}

# --- SLA (Service-Level Agreement) Configuration ---
# Maximum minutes a task should wait in PENDING before being considered overdue.
# Used by claim_task() for aging-boost priority escalation.
SLA_DEADLINES_MINUTES = {
    'critical': 5,      # 5 minutes
    'high': 30,         # 30 minutes
    'normal': 120,      # 2 hours
    'low': 480,         # 8 hours
}

# Aging boost: every N minutes in queue, task gets +1 priority boost
# A "normal" task waiting 60min will have effective priority "high"
SLA_AGING_BOOST_INTERVAL_MINUTES = 30

# Timeout escalation multiplier on retry (retry 2 gets 1.5x timeout, retry 3 gets 2.25x)
SLA_TIMEOUT_ESCALATION_MULTIPLIER = 1.5

# Skills that need extra time or special handling
SLOW_SKILLS = {
    '/horde-brainstorming': 7200,
    '/golden-horde': 7200,
    '/horde-implement': 7200,
    '/horde-review': 7200,
    '/horde-debug': 7200,
    '/horde-learn': 7200,
    '/horde-swarm': 7200,
    '/horde-test': 7200,
    # Medium-complexity skills: get slow stall thresholds
    '/senior-frontend': 0,
    '/senior-backend': 0,
    '/senior-fullstack': 0,
    '/senior-architect': 0,
    '/systematic-debugging': 0,
    '/content-research-writer': 0,
    '/horde-gate-testing': 0,
    '/horde-plan': 0,
    # Ogedei ops skills: need relaxed stall thresholds (session setup + tool loading)
    '/kurultai-health': 0,
    '/code-reviewer': 0,
    '/kurultai-model-switcher': 0,
    # Parse project context skills (no special timeout)
    '/parsethe-media': 0,
    '/parse-for-agents': 0,
}

# Health Check Timeouts
HTTP_TIMEOUT = 5  # system-health-check.py
NEO4J_TIMEOUT = 3  # system-health-check.py
SUBPROCESS_TIMEOUT = 30  # system-health-check.py

# Experiment Timeouts
EXPERIMENT_DEFAULT_TIMEOUT = 600  # experiment_manager.py

# Reflection Timeouts
REFLECTION_TIMEOUT = 420  # generate_hourly_report.py
REVIEW_TIMEOUT = 120  # generate_hourly_report.py

# Rate Limiting
MAX_RATE_LIMIT_RETRIES = 1  # Only retry once with fallback model

# Valid Claude model IDs (single source of truth)
VALID_CLAUDE_MODELS = frozenset({'claude-opus-4-6', 'claude-sonnet-4-6', 'claude-haiku-4-5'})


# =============================================================================
# EXTERNAL SERVICE CONFIGURATION
# =============================================================================

# Neo4j Configuration
import os
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")

# Redis Configuration
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")


