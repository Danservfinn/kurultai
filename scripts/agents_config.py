"""Canonical agent configuration — single source of truth.

All scripts that need agent lists, roles, or model mappings should import from here.
CLAUDE API RATE LIMITED until 2026-03-12 — all agents using glm-5 (Z.ai).
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

# CLAUDE API RATE LIMITED until 2026-03-12 — using glm-5 (Z.ai)
AGENT_MODELS = {
    "kublai": "glm-5",
    "mongke": "glm-5",
    "chagatai": "glm-5",
    "temujin": "glm-5",
    "jochi": "glm-5",
    "ogedei": "glm-5",
}
