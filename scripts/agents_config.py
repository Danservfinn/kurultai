"""Canonical agent configuration — reads from kurultai.json (single source of truth).

All scripts that need agent lists, roles, or model mappings should import from here.
Task queue paths are derived from kurultai_paths.AGENTS_DIR (the canonical root).
"""

import json
from pathlib import Path
from kurultai_paths import AGENTS_DIR as _AGENTS_DIR

_KURULTAI_JSON = Path.home() / ".openclaw" / "kurultai.json"

# Load kurultai.json at import time
def _load_kurultai():
    with open(_KURULTAI_JSON, 'r') as f:
        return json.load(f)

_CONFIG = _load_kurultai()

# AGENTS = only claude-code executor agents (backward compat: excludes tolui)
AGENTS = [
    name for name, cfg in _CONFIG['agents'].items()
    if cfg.get('executor') == 'claude-code'
]

# ALL_AGENTS = every agent in kurultai.json
ALL_AGENTS = list(_CONFIG['agents'].keys())

# Canonical task queue paths — single source of truth for all scripts.
TASK_QUEUE_PATHS = {
    agent: str(_AGENTS_DIR / agent / "tasks") for agent in ALL_AGENTS
}

AGENT_ROLES = {
    name: cfg['role'] for name, cfg in _CONFIG['agents'].items()
}

# Backward compat: AGENT_MODELS returns sentinel for claude-code, actual model for others
AGENT_MODELS = {}
for name, cfg in _CONFIG['agents'].items():
    if cfg.get('executor') == 'claude-code':
        AGENT_MODELS[name] = "claude-code/settings"
    elif cfg.get('executor') == 'ollama':
        ec = cfg.get('executor_config', {})
        AGENT_MODELS[name] = ec.get('model_name', 'unknown')
    else:
        AGENT_MODELS[name] = "unknown"


def get_agent_config(name):
    """Get full config for an agent from kurultai.json.

    Returns dict with: executor, role, effort, task_queue_path,
    max_concurrent_subagents, auto_spawn_subagents, and (for ollama) executor_config.
    """
    if name not in _CONFIG['agents']:
        raise KeyError(f"Unknown agent: {name}")
    cfg = dict(_CONFIG['agents'][name])
    cfg['task_queue_path'] = str(_AGENTS_DIR / name / "tasks")
    return cfg


def get_execution_config():
    """Get execution block from kurultai.json (primary/backup settings paths, default effort)."""
    return dict(_CONFIG.get('execution', {}))


def reload():
    """Reload kurultai.json (for long-running processes that need fresh config)."""
    global _CONFIG, AGENTS, ALL_AGENTS, TASK_QUEUE_PATHS, AGENT_ROLES, AGENT_MODELS
    _CONFIG = _load_kurultai()
    AGENTS = [n for n, c in _CONFIG['agents'].items() if c.get('executor') == 'claude-code']
    ALL_AGENTS = list(_CONFIG['agents'].keys())
    TASK_QUEUE_PATHS = {a: str(_AGENTS_DIR / a / "tasks") for a in ALL_AGENTS}
    AGENT_ROLES = {n: c['role'] for n, c in _CONFIG['agents'].items()}
    AGENT_MODELS.clear()
    for n, c in _CONFIG['agents'].items():
        if c.get('executor') == 'claude-code':
            AGENT_MODELS[n] = "claude-code/settings"
        elif c.get('executor') == 'ollama':
            ec = c.get('executor_config', {})
            AGENT_MODELS[n] = ec.get('model_name', 'unknown')
        else:
            AGENT_MODELS[n] = "unknown"
