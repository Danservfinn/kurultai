"""Canonical agent configuration — single source of truth.

All scripts that need agent lists, roles, or model mappings should import from here.
Model assignments are kept in sync with openclaw.json (authoritative source).
"""

AGENTS = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei"]

AGENT_ROLES = {
    "kublai": "Squad Lead / Router",
    "temujin": "Developer (code, builds, infrastructure)",
    "mongke": "Researcher (web research, API discovery)",
    "chagatai": "Writer (documentation, creative content)",
    "jochi": "Analyst (testing, security, pattern recognition)",
    "ogedei": "Ops (monitoring, health checks, failover)",
}

AGENT_MODELS = {
    "kublai": "bailian/qwen3.5-plus",
    "mongke": "bailian/MiniMax-M2.5",
    "chagatai": "bailian/kimi-k2.5",
    "temujin": "bailian/MiniMax-M2.5",
    "jochi": "bailian/qwen3.5-plus",
    "ogedei": "bailian/qwen3.5-plus",
}
