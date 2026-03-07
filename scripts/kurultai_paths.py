"""
kurultai_paths.py — Single source of truth for all Kurultai filesystem paths.

Every script that needs agent directories, task queues, logs, or ledger paths
should import from here instead of defining its own constants.

Usage:
    from kurultai_paths import AGENTS_DIR, agent_tasks_dir, TASK_LEDGER
"""

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

# Valid agent names
VALID_AGENTS = frozenset({"kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"})
DISPATCH_AGENTS = ["temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"]

# Claude agent binary
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


