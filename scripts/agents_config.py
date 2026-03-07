"""Canonical agent configuration — single source of truth.

All scripts that need agent lists, roles, or model mappings should import from here.
All agents execute via Claude Code (claude-opus-4-6). models.json has alternative providers for experimentation only.
Task queue paths are derived from kurultai_paths.AGENTS_DIR (the canonical root).
"""

from kurultai_paths import AGENTS_DIR as _AGENTS_DIR

AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]

# Canonical task queue paths — single source of truth for all scripts.
# Any script that writes or reads task files MUST use these paths.
# Old path (main/agent/{agent}/tasks/) is DEAD — do not use.
TASK_QUEUE_PATHS = {
    agent: str(_AGENTS_DIR / agent / "tasks") for agent in AGENTS
}

AGENT_ROLES = {
    "kublai": "Squad Lead / Router",
    "temujin": "Developer (code, builds, infrastructure)",
    "mongke": "Researcher (web research, API discovery)",
    "chagatai": "Writer (documentation, creative content)",
    "jochi": "Analyst (testing, security, pattern recognition)",
    "ogedei": "Ops (monitoring, health checks, failover)",
}

AGENT_MODELS = {
    "kublai": "claude-opus-4-6",
    "mongke": "claude-opus-4-6",
    "chagatai": "claude-opus-4-6",
    "temujin": "claude-opus-4-6",
    "jochi": "claude-opus-4-6",
    "ogedei": "claude-opus-4-6",
}
