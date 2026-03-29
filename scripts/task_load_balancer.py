#!/usr/bin/env python3
"""
task_load_balancer.py — Load balancing and queue management for Kurultai task routing.

Extracted from task_intake.py for maintainability.

Usage:
    from task_load_balancer import get_queue_depth, find_best_agent_by_load, get_adaptive_thresholds
"""

import os
import re
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kurultai_paths import AGENTS_DIR, LOGS_DIR, VALID_AGENTS, AGENT_KEYWORDS, agent_tasks_dir
from task_domain import DOMAIN_AGENT_COMPATIBILITY, _kw_match

AGENT_DIR = str(AGENTS_DIR)

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
        ("mongke", ["research", "discover", "benchmark", "study", "competitor", "market analysis"]),
        # jochi can handle testing/QA, debugging, AND security tasks from temujin (expanded 2026-03-11)
        ("jochi", ["test", "testing", "verify", "audit", "review code", "QA", "quality",
                   "debug", "bug", "error", "crash", "investigate", "performance", "anomaly",
                   "security", "vulnerability", "scan", "injection", "compliance", "unauthorized"]),
        # ogedei can handle deployment/ops tasks from temujin
        ("ogedei", ["deploy", "railway", "docker", "container", "infrastructure", "monitor", "restart", "cleanup"]),
        # chagatai can handle documentation tasks from temujin
        ("chagatai", ["document", "documentation", "write", "readme", "changelog", "content"]),
        # kublai can handle system design/architecture tasks from temujin
        ("kublai", ["design", "architecture", "system", "protocol", "plan", "strategy"]),
    ],
    "jochi": [
        ("temujin", ["debug", "fix", "error", "crash", "implement fix", "patch"]),
        ("ogedei", ["security audit", "vulnerability scan", "compliance check", "health diagnostic"]),
        ("mongke", ["research", "competitor analysis", "market research", "investigate trend", "benchmark competitors"]),
        ("kublai", ["analyze", "triage", "assess", "review", "investigate issue"]),
    ],
    "mongke": [
        ("chagatai", ["write", "document findings", "summarize research", "content"]),
        ("jochi", ["analyze data", "verify", "validate findings", "score", "benchmark"]),
    ],
    "chagatai": [
        ("mongke", ["research topic", "gather sources", "investigate trend"]),
    ],
    "ogedei": [
        ("temujin", ["fix script", "code cleanup", "automation", "tooling"]),
        ("jochi", ["health check", "diagnostic", "monitor verification"]),
        ("mongke", ["research", "investigate trend", "market research", "competitor analysis", "benchmark"]),
        ("kublai", ["escalate", "status", "report", "notify", "alert"]),
    ],
    "kublai": [
        ("temujin", ["triage", "coordinate", "assess", "review system"]),
        ("mongke", ["research", "competitor analysis", "market research", "benchmark", "investigate trend"]),
        ("jochi", ["analyze", "investigate", "review", "assess"]),
        ("ogedei", ["status", "report", "health check", "escalation"]),
    ],
}

# Legacy overflow map (kept for compatibility with existing code)
OVERFLOW_MAP = {
    ("temujin", "code_review"):     ["jochi"],
    ("temujin", "deploy"):          ["ogedei"],
    ("temujin", "infrastructure"):  ["ogedei"],
    ("temujin", "testing"):         ["jochi"],
    ("temujin", "security"):        ["jochi"],
    ("jochi", "code_review"):       ["temujin"],
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
                 "llm", "model comparison", "ai model", "provider comparison"],
    "docs": ["document", "documentation", "readme", "changelog"],
    "monitoring": ["monitor", "health", "alert", "status", "uptime"],
}

# Agents that should not receive load-balanced overflow tasks
_NO_OVERFLOW_TARGETS = {"kublai", "tolui"}

# Skill capable alternates for overflow (used by find_skill_capable_alternates)
# Updated 2026-03-23: Expanded alternates for better load distribution
# See: routing-audit-response-guide.md, workspace/routing-audit-fix-20260323.md
_SKILL_CAPABLE_ALTERNATES = {
    # Core horde skills
    "/horde-brainstorming": ["mongke", "jochi", "chagatai", "temujin"],  # +temujin for architecture/design
    "/horde-implement": ["ogedei", "temujin"],  # +temujin for implementation overflow
    "/horde-debug": ["jochi", "ogedei", "temujin"],  # +temujin for code debugging
    "/horde-review": ["jochi", "mongke"],  # +mongke for research reviews
    "/horde-plan": ["mongke", "chagatai", "temujin"],  # +temujin for implementation planning
    "/horde-learn": ["jochi", "chagatai", "mongke"],  # +mongke for research extraction
    "/horde-test": ["temujin", "jochi"],  # NEW: testing tasks
    "/golden-horde": ["ogedei", "temujin"],  # NEW: orchestration overflow
    # Ops skills
    "/kurultai-health": ["temujin", "jochi"],  # +jochi for health analysis/triage
    # Development skills
    "/code-reviewer": ["temujin", "jochi"],  # +jochi for security review
    "/generate-tests": ["temujin", "jochi"],  # +jochi for test generation
    "/systematic-debugging": ["jochi", "ogedei", "temujin"],  # NEW: structured debugging
    "/senior-architect": ["temujin", "mongke"],  # NEW: architecture tasks
    "/senior-frontend": ["temujin", "jochi"],  # NEW: frontend tasks
    "/senior-backend": ["temujin", "jochi"],  # NEW: backend tasks
    "/senior-fullstack": ["temujin", "jochi"],  # NEW: fullstack tasks
    "/senior-devops": ["ogedei", "temujin"],  # NEW: devops tasks
    # Content skills
    "/content-research-writer": ["mongke", "chagatai", "jochi"],  # +jochi for analysis
    "/changelog-generator": ["mongke", "chagatai", "jochi"],  # +jochi for changelog analysis
}

# Routing log path
ROUTING_LOG = str(LOGS_DIR / "routing-decisions.jsonl")


# =============================================================================
# Core Load Functions
# =============================================================================

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


def get_adaptive_thresholds():
    """Calculate thresholds based on current system load.

    Returns dict with 'high', 'critical', 'low', and 'load_factor' keys.

    Threshold scaling (adjusted 2026-03-09 for aggressive redistribution):
    - Load 0.0: HIGH=2, CRITICAL=6, LOW=1 (base values)
    - Load 0.5: HIGH=3, CRITICAL=8, LOW=2
    - Load 1.0: HIGH=4, CRITICAL=10, LOW=2
    """
    load = calculate_system_load_factor()

    BASE_HIGH = 2
    BASE_CRITICAL = 6
    BASE_LOW = 1

    HIGH = int(BASE_HIGH + load * 2)
    CRITICAL = int(BASE_CRITICAL + load * 4)
    LOW = BASE_LOW + int(load * 1)

    return {
        'high': HIGH,
        'critical': CRITICAL,
        'low': LOW,
        'load_factor': load
    }


def _log_threshold_adjustment(thresholds, previous_thresholds=None):
    """Log threshold adjustments to threshold-adjustments.jsonl."""
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


# =============================================================================
# Failure Rate & Credential Functions
# =============================================================================

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

    Returns (is_valid, error_message) tuple.
    """
    # TOLUI SPECIAL CASE: Uses ollama/local models, no Anthropic credentials needed
    if agent == "tolui":
        return True, None  # Tolui uses local ollama models

    try:
        # 1. Check OAuth status (primary auth method for Anthropic)
        _claude_creds_path = Path.home() / ".claude" / "credentials.json"
        if _claude_creds_path.exists():
            try:
                with open(_claude_creds_path, 'r') as f:
                    _creds = json.load(f)
                if _creds.get('loggedIn') and _creds.get('authMethod') == 'oauth_token':
                    return True, None
            except (json.JSONDecodeError, IOError):
                pass

        # 2. Check centralized vault for fallback credentials
        _vault_path = Path.home() / ".openclaw" / "credentials" / "provider.env"
        if _vault_path.exists():
            try:
                with open(_vault_path, 'r') as f:
                    _vault_content = f.read()
                _has_zai = 'ZAI_AUTH_TOKEN=' in _vault_content and 'b5b1f953' in _vault_content
                _has_alibaba = 'ALIBABA_AUTH_TOKEN=' in _vault_content and 'sk-sp-' in _vault_content
                if _has_zai or _has_alibaba:
                    return True, None
            except IOError:
                pass

        # 3. Legacy: Check for per-agent token in settings.json
        agent_root = AGENTS_DIR / agent
        settings_path = agent_root / ".claude" / "settings.json"

        if not settings_path.exists():
            return False, f"No settings.json found for {agent}"

        with open(settings_path, 'r') as f:
            settings = json.load(f)

        auth_token = None
        if 'env' in settings:
            auth_token = settings['env'].get('ANTHROPIC_AUTH_TOKEN')
        if not auth_token:
            auth_token = settings.get('apiKey')
        if not auth_token:
            return False, f"No ANTHROPIC_AUTH_TOKEN found"

        _is_anthropic = auth_token.startswith('sk-ant-')
        _is_zai = len(auth_token.split('.')) == 2 and len(auth_token.split('.')[0]) == 32
        _is_alibaba = auth_token.startswith('sk-sp-') or auth_token.startswith('sk-')

        if not (_is_anthropic or _is_zai or _is_alibaba):
            return False, f"Invalid token: {auth_token[:10]}... (expected sk-ant-*, Z.AI, or Alibaba)"

        return True, None

    except Exception as e:
        return False, f"Credential check error: {e}"


# =============================================================================
# Capability & Alternates Functions
# =============================================================================

def find_underutilized_agents(exclude=None):
    """Find agents with queue depth below adaptive LOW threshold."""
    exclude = exclude or set()
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
    """Check if alternate agent can handle a task based on capability matrix."""
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
    significantly higher than the alternate's, skip the alternate.

    Returns list of (agent, depth) tuples sorted by queue depth.
    """
    capabilities = AGENT_CAPABILITY_MATRIX.get(primary_agent, [])
    capable = []
    task_lower = task_text.lower()

    domain_valid_agents = None
    if task_domain and task_domain in DOMAIN_AGENT_COMPATIBILITY:
        domain_valid_agents = set(DOMAIN_AGENT_COMPATIBILITY[task_domain])
        domain_valid_agents.add(primary_agent)

    primary_keywords = AGENT_KEYWORDS.get(primary_agent, [])
    primary_score = sum(1 for kw in primary_keywords if _kw_match(kw, task_lower))

    for alt_agent, keywords in capabilities:
        if domain_valid_agents is not None and alt_agent not in domain_valid_agents:
            continue
        cap_match_count = sum(1 for kw in keywords if _kw_match(kw, task_lower))
        if cap_match_count == 0:
            continue

        alt_domain_keywords = AGENT_KEYWORDS.get(alt_agent, [])
        alt_domain_score = sum(1 for kw in alt_domain_keywords if _kw_match(kw, task_lower))
        if alt_domain_score == 0:
            continue

        domain_guard_ratio = 0.5
        if primary_score >= 2 and cap_match_count <= 1:
            if alt_domain_score < primary_score * domain_guard_ratio:
                continue

        depth = get_queue_depth(alt_agent)
        capable.append((alt_agent, depth))

    capable.sort(key=lambda x: x[1])
    return capable


def find_skill_capable_alternates(skill_hint, exclude=None):
    """Find alternate agents capable of handling a skill-based task."""
    alternates = _SKILL_CAPABLE_ALTERNATES.get(skill_hint, [])
    exclude_set = {exclude} if exclude else set()

    result = []
    for agent in alternates:
        if agent in exclude_set or agent in _NO_OVERFLOW_TARGETS:
            continue
        depth = get_queue_depth(agent)
        result.append((agent, depth))

    result.sort(key=lambda x: x[1])
    return result


def should_bypass_skill_lock(skill_hint, target_agent, queue_depth):
    """Determine if skill-based routing should bypass to an alternate agent.

    Returns:
        Tuple of (should_bypass: bool, alternate_agent: str or None, reason: str)
    """
    if not skill_hint:
        return False, None, "no_skill_hint"

    if skill_hint not in _SKILL_CAPABLE_ALTERNATES:
        return False, None, f"skill_not_in_alternates: {skill_hint}"

    thresholds = get_adaptive_thresholds()
    HIGH_THRESHOLD = thresholds['high']

    if queue_depth < HIGH_THRESHOLD:
        return False, None, f"queue_depth={queue_depth} < threshold={HIGH_THRESHOLD}"

    alternates = find_skill_capable_alternates(skill_hint, exclude=target_agent)
    if not alternates:
        return False, None, f"no_capable_alternates_for_skill: {skill_hint}"

    best_alt, best_depth = alternates[0]

    if best_depth >= queue_depth:
        return False, None, f"alternate_deeper: {best_alt}={best_depth} >= {target_agent}={queue_depth}"

    return True, best_alt, f"skill_overflow_bypass: {skill_hint} from {target_agent}(q={queue_depth}) -> {best_alt}(q={best_depth})"


# =============================================================================
# Primary Load Balancing
# =============================================================================

def find_best_agent_by_load(task_text, primary_agent, task_domain=None):
    """Find the best agent considering queue depth and capabilities.

    Returns (agent, reason) tuple.
    """
    thresholds = get_adaptive_thresholds()
    HIGH_THRESHOLD = thresholds['high']
    CRITICAL_THRESHOLD = thresholds['critical']
    LOW_THRESHOLD = thresholds['low']
    load_factor = thresholds['load_factor']

    primary_depth = get_queue_depth(primary_agent)

    # Check if primary agent has a high failure rate
    if is_agent_failing(primary_agent):
        capable_alternates = get_capable_alternates(primary_agent, task_text, task_domain)
        healthy_alts = [(a, d) for a, d in capable_alternates if not is_agent_failing(a)]
        if healthy_alts:
            best_agent, best_depth = healthy_alts[0]
            rate, _ = get_agent_failure_rate(primary_agent)
            return best_agent, f"failure-bypass: {primary_agent} failure_rate={rate:.0%}, routing to {best_agent} (queue={best_depth})"

    # Primary agent has capacity
    if primary_depth < HIGH_THRESHOLD:
        return primary_agent, f"primary queue={primary_depth} < threshold={HIGH_THRESHOLD} (load={load_factor:.2f})"

    # Find capable alternates sorted by queue depth
    capable_alternates = get_capable_alternates(primary_agent, task_text, task_domain)

    # Filter to underutilized agents WITH VALID CREDENTIALS
    underutilized = []
    for agent, depth in capable_alternates:
        if depth < LOW_THRESHOLD:
            alt_valid, alt_error = check_agent_credentials(agent)
            if alt_valid:
                underutilized.append((agent, depth))
            else:
                print(f"LOAD_BALANCE_CREDENTIAL_BLOCK: {agent} has invalid credentials ({alt_error}), not accepting underutilized overflow from {primary_agent}")

    if underutilized:
        best_agent, best_depth = underutilized[0]
        return best_agent, f"load-balance: {primary_agent} queue={primary_depth}, {best_agent} underutilized (queue={best_depth}, low_threshold={LOW_THRESHOLD})"

    # IDLE AGENT WAKE-UP
    idle_agents = get_idle_agents(exclude={primary_agent, "kublai", "tolui"})
    if idle_agents:
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

    # Primary queue is critical — broadcast to all capable WITH VALID CREDENTIALS
    if primary_depth >= CRITICAL_THRESHOLD and capable_alternates:
        healthy_capable = []
        for agent, depth in capable_alternates:
            alt_valid, alt_error = check_agent_credentials(agent)
            if alt_valid:
                healthy_capable.append((agent, depth))
            else:
                print(f"BROADCAST_CREDENTIAL_BLOCK: {agent} has invalid credentials ({alt_error}), excluding from broadcast")

        if healthy_capable:
            best_agent, best_depth = healthy_capable[0]
            _log_routing_decision(
                title=task_text,
                dest=best_agent,
                method="broadcast_overflow",
                overflow_reason=f"{primary_agent} queue={primary_depth} >= {CRITICAL_THRESHOLD}, routing to lowest alternate with valid creds"
            )
            return best_agent, f"broadcast: {primary_agent} critical queue={primary_depth}, routing to {best_agent} (queue={best_depth})"
        else:
            print(f"BROADCAST_CREDENTIAL_FAIL: All alternates have invalid credentials, cannot broadcast from {primary_agent}")

    # Use any capable alternate with lower queue than primary
    if capable_alternates:
        for alt_agent, alt_depth in capable_alternates:
            alt_valid, alt_error = check_agent_credentials(alt_agent)
            if not alt_valid:
                print(f"ALTERNATE_CREDENTIAL_BLOCK: {alt_agent} has invalid credentials ({alt_error}), skipping")
                continue
            if alt_depth < primary_depth:
                return alt_agent, f"load-balance: {primary_agent} queue={primary_depth}, {alt_agent} lower (queue={alt_depth})"
        healthy_capable = []
        for agent, depth in capable_alternates:
            alt_valid, _ = check_agent_credentials(agent)
            if alt_valid:
                healthy_capable.append((agent, depth))
        if healthy_capable:
            best_agent, best_depth = healthy_capable[0]
            return best_agent, f"load-balance: all busy, {primary_agent} queue={primary_depth}, using {best_agent} (queue={best_depth})"

    # No capable alternates
    return primary_agent, f"no capable alternates, queuing to {primary_agent} (queue={primary_depth})"


def should_redistribute_tasks():
    """Check if redistribution is needed.

    Returns list of (overloaded_agent, underutilized_agents) tuples.
    """
    thresholds = get_adaptive_thresholds()
    HIGH_THRESHOLD = thresholds['high']
    LOW_THRESHOLD = thresholds['low']

    depths = get_all_agent_queue_depths()
    overloaded = [(agent, depth) for agent, depth in depths.items()
                  if depth > HIGH_THRESHOLD]
    underutilized = [(agent, depth) for agent, depth in depths.items()
                     if depth <= LOW_THRESHOLD]

    redistribution_needed = []
    for ov_agent, ov_depth in overloaded:
        capable_underutilized = []
        for un_agent, un_depth in underutilized:
            if AGENT_CAPABILITY_MATRIX.get(ov_agent):
                for cap_agent, _ in AGENT_CAPABILITY_MATRIX[ov_agent]:
                    if cap_agent == un_agent:
                        capable_underutilized.append((un_agent, un_depth))
                        break
        if capable_underutilized:
            redistribution_needed.append((ov_agent, capable_underutilized))

    return redistribution_needed


def get_idle_agents(exclude=None):
    """Return list of agents that are not currently executing any task."""
    exclude = exclude or set()
    idle = []
    for agent in VALID_AGENTS:
        if agent in exclude:
            continue
        if not is_agent_busy(agent):
            idle.append(agent)
    return idle


# =============================================================================
# Redistribution Triggers
# =============================================================================

REDISTRIBUTION_TRIGGERS = {
    'imbalance_ratio': 2.0,
    'min_overloaded_depth': 5,
    'idle_time_threshold_s': 600,
    'high_load_streak': 3,
    'high_load_threshold': 0.6,
    'max_move_per_cycle': 5,
    'load_history_file': f"{LOGS_DIR}/load-history.jsonl",
}


def get_agent_idle_time(agent):
    """Get seconds since agent last completed a task."""
    task_dir = agent_tasks_dir(agent)
    if not task_dir.exists():
        return 0

    for fname in task_dir.iterdir():
        if '.executing' in fname.name and '.done' not in fname.name and not fname.name.endswith('.pid'):
            return 0

    latest_time = None
    for fname in task_dir.iterdir():
        if fname.suffix == '.md' and ('.done' in fname.name or fname.name.endswith('.done.md')):
            mtime = fname.stat().st_mtime
            if latest_time is None or mtime > latest_time:
                latest_time = mtime

    if latest_time is None:
        return 0

    return int(datetime.now().timestamp() - latest_time)


def _get_load_history(count=5):
    """Get recent load factor measurements from history file."""
    history_file = Path(REDISTRIBUTION_TRIGGERS['load_history_file'])
    if not history_file.exists():
        return []

    try:
        lines = history_file.read_text().strip().split('\n')
        recent = lines[-count:] if len(lines) >= count else lines
        history = []
        for line in recent:
            try:
                data = json.loads(line)
                history.append(data.get('load_factor', 0.0))
            except json.JSONDecodeError:
                continue
        return list(reversed(history))
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

        try:
            lines = history_file.read_text().strip().split('\n')
            if len(lines) > 100:
                history_file.write_text('\n'.join(lines[-100:]) + '\n')
        except Exception:
            pass
    except Exception:
        pass


def should_trigger_redistribution():
    """Determine if redistribution should run proactively.

    Returns tuple of (should_trigger: bool, reason: str).
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
        if depths.get(agent, 0) == 0:
            idle_time = get_agent_idle_time(agent)
            if idle_time > REDISTRIBUTION_TRIGGERS['idle_time_threshold_s']:
                others_have_work = any(depths.get(a, 0) > 2 for a in VALID_AGENTS if a not in {agent, 'kublai', 'tolui'})
                if others_have_work:
                    return True, f"Agent {agent} idle for {idle_time}s while work exists"

    # Condition 3: Sustained high load
    load_factor = calculate_system_load_factor()
    _record_load_measurement(load_factor)

    load_history = _get_load_history(count=REDISTRIBUTION_TRIGGERS['high_load_streak'])
    if len(load_history) >= REDISTRIBUTION_TRIGGERS['high_load_streak']:
        if all(l > REDISTRIBUTION_TRIGGERS['high_load_threshold'] for l in load_history):
            return True, f"Sustained high load: {[f'{l:.2f}' for l in load_history]}"

    return False, "No trigger conditions met"


# =============================================================================
# Scoring and Queue-Penalized Routing
# =============================================================================

def get_agent_scores(text):
    """Score all agents for a given task text. Returns dict of {agent: score}."""
    text_lower = text.lower()
    scores = {}
    for agent, keywords in AGENT_KEYWORDS.items():
        scores[agent] = sum(1 for kw in keywords if _kw_match(kw, text_lower))
    return scores


def route_with_queue_penalty(text, thresholds=None):
    """Route task considering both keyword match and queue depth.

    Returns:
        Tuple of (best_agent, metadata)
    """
    if thresholds is None:
        thresholds = get_adaptive_thresholds()

    scores = get_agent_scores(text)
    depths = get_all_agent_queue_depths()

    penalized = {}
    for agent, score in scores.items():
        depth = depths.get(agent, 0)

        if depth >= thresholds['high']:
            penalty_factor = 0.9 ** (depth - thresholds['high'] + 1)
        elif depth >= thresholds['low']:
            penalty_factor = 0.95 ** depth
        else:
            penalty_factor = 1.0

        penalized[agent] = score * penalty_factor

    best = max(penalized.items(), key=lambda x: x[1])

    return best[0], {
        'original_scores': scores,
        'penalized_scores': penalized,
        'queue_depths': depths,
        'thresholds': thresholds
    }


# =============================================================================
# Best Idle Agent (complex load balancing)
# =============================================================================

def find_best_idle_agent(text, primary_agent, task_domain=None):
    """Find the best agent considering queue depth and idle status.

    Returns (agent, reason) tuple.
    """
    thresholds = get_adaptive_thresholds()
    HIGH_THRESHOLD = thresholds['high']
    LOW_THRESHOLD = thresholds['low']

    primary_depth = get_queue_depth(primary_agent)

    # CREDENTIAL HEALTH CHECK
    creds_valid, creds_error = check_agent_credentials(primary_agent)
    if not creds_valid:
        capable_alternates = get_capable_alternates(primary_agent, text, task_domain)
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

    # Check failure rate
    if is_agent_failing(primary_agent):
        capable_alternates = get_capable_alternates(primary_agent, text, task_domain)
        healthy_alts = [(a, d) for a, d in capable_alternates if not is_agent_failing(a)]
        if healthy_alts:
            best_agent, best_depth = healthy_alts[0]
            rate, _ = get_agent_failure_rate(primary_agent)
            return best_agent, f"failure-bypass: {primary_agent} failure_rate={rate:.0%}, routing to {best_agent} (queue={best_depth})"

    # EQUAL-QUEUE LOAD BALANCING
    capable_alternates = get_capable_alternates(primary_agent, text, task_domain)
    better_or_equal_alternates = []
    for alt_agent, alt_depth in capable_alternates:
        alt_valid, alt_error = check_agent_credentials(alt_agent)
        if not alt_valid:
            print(f"OVERFLOW_CREDENTIAL_BLOCK: {alt_agent} has invalid credentials ({alt_error}), not accepting overflow from {primary_agent}")
            continue
        if alt_depth <= primary_depth:
            better_or_equal_alternates.append((alt_agent, alt_depth))

    # TOLUI DISPATCH CHECK
    if primary_agent == "tolui":
        tolui_idle_time = get_agent_idle_time("tolui")
        if tolui_idle_time > 300 and primary_depth > 0:
            print(f"TOLUI_DISPATCH_STALL: tolui idle for {tolui_idle_time}s with {primary_depth} pending tasks")

    # If primary is idle, has low queue, AND no equal-or-better alternatives exist
    if not is_agent_busy(primary_agent) and primary_depth < HIGH_THRESHOLD and not better_or_equal_alternates:
        if creds_valid and primary_agent != "tolui":
            return primary_agent, f"primary idle, queue={primary_depth}, no equal alternatives"
        elif primary_agent == "tolui" and get_agent_idle_time("tolui") < 300:
            return primary_agent, f"tolui idle, queue={primary_depth}, not stalled"

    # Filter to underutilized agents
    underutilized = [(a, d) for a, d in better_or_equal_alternates if d < LOW_THRESHOLD]

    if underutilized:
        best_agent, best_depth = underutilized[0]
        return best_agent, f"load-balance: {primary_agent} busy/loaded (queue={primary_depth}), {best_agent} underutilized (queue={best_depth})"

    # EQUAL-QUEUE BALANCING
    if better_or_equal_alternates:
        best_agent, best_depth = better_or_equal_alternates[0]
        if best_depth < primary_depth:
            return best_agent, f"equal-queue-balance: {primary_agent} (queue={primary_depth}) -> {best_agent} (queue={best_depth})"
        elif best_depth == primary_depth and best_agent != primary_agent:
            priority_order = ["chagatai", "mongke", "jochi", "temujin", "ogedei", "kublai"]
            primary_priority = priority_order.index(primary_agent) if primary_agent in priority_order else 999
            alt_priority = priority_order.index(best_agent) if best_agent in priority_order else 999
            if alt_priority < primary_priority:
                return best_agent, f"equal-queue-tiebreak: {primary_agent} (queue={primary_depth}) -> {best_agent} (queue={best_depth}, priority {alt_priority} < {primary_priority})"

    # IDLE AGENT WAKE-UP
    idle_agents = get_idle_agents(exclude={primary_agent, "kublai", "tolui"})
    if idle_agents:
        healthy_idle = []
        for idle_agent in idle_agents:
            idle_valid, idle_error = check_agent_credentials(idle_agent)
            if not idle_valid:
                print(f"IDLE_WAKE_CREDENTIAL_BLOCK: {idle_agent} has invalid credentials ({idle_error}), skipping idle wake-up")
                continue
            idle_depth = get_queue_depth(idle_agent)
            idle_time = get_agent_idle_time(idle_agent)

            stall_penalty = 0
            if idle_time > 600 and idle_depth > 0:
                stall_penalty = 10

            if idle_agent == "tolui" and idle_depth > 0:
                if idle_time > 300:
                    print(f"TOLUI_STALL_CHECK: {idle_agent} idle {idle_time}s with {idle_depth} pending")
                    stall_penalty = 5

            effective_depth = idle_depth + stall_penalty

            if effective_depth < primary_depth:
                healthy_idle.append((idle_agent, idle_depth, effective_depth))

        if healthy_idle:
            healthy_idle.sort(key=lambda x: x[2])
            best_idle_agent, best_idle_depth, _ = healthy_idle[0]
            print(f"IDLE_WAKE_UP: No capable underutilized agents for {primary_agent} (queue={primary_depth}), waking idle agent {best_idle_agent} (queue={best_idle_depth})")
            return best_idle_agent, f"idle-wake: {primary_agent} busy/loaded (queue={primary_depth}), {best_idle_agent} idle with valid creds (queue={best_idle_depth})"

    # Check overflow map for category-specific idle agents (legacy)
    category = _detect_category(text)
    if category:
        overflow_agents = OVERFLOW_MAP.get((primary_agent, category), [])
        for overflow in overflow_agents:
            if not is_agent_busy(overflow):
                ov_valid, ov_error = check_agent_credentials(overflow)
                if not ov_valid:
                    print(f"OVERFLOW_CREDENTIAL_BLOCK: {overflow} has invalid credentials ({ov_error}), skipping overflow-map route")
                    continue
                ov_depth = get_queue_depth(overflow)
                return overflow, f"load-balance: {primary_agent} busy, {overflow} idle (overflow-map, {category}, queue={ov_depth})"

    # No idle/underutilized agent found
    return find_best_agent_by_load(text, primary_agent, task_domain)


# =============================================================================
# Overflow & Categorization
# =============================================================================

def _detect_category(text):
    """Detect task category from text for overflow lookup."""
    text_lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if ' ' in kw:
                if kw in text_lower:
                    return category
            else:
                if re.search(r'\b' + re.escape(kw) + r'\b', text_lower):
                    return category
    return None


def find_overflow_agent(primary_agent, text):
    """Find an available overflow agent if primary is busy or quality-poor.
    Returns (agent, overflow_reason) tuple.
    """
    # Quality-aware diversion check
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


# =============================================================================
# Logging Functions
# =============================================================================

def _log_overflow(original, overflow, title, reason):
    """Log overflow routing decision to JSONL."""
    log_path = os.path.expanduser("~/.openclaw/agents/main/logs/routing-overflow.jsonl")
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        entry = {"ts": datetime.now().isoformat(), "from": original, "to": overflow,
                 "title": title[:100], "reason": reason}
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _log_routing_decision(title, dest, method, overflow_reason=None, skill_hint=None, scores=None, queue_info=None, original_agent=None, domain=None, penalized_scores=None, route_metadata=None, task_source=None):
    """Append routing decision to JSONL log for routing_audit.py consumption."""
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

        all_scores = get_agent_scores(title)
        entry["alt_scores"] = all_scores

        if penalized_scores:
            entry["penalized_scores"] = penalized_scores
        if route_metadata:
            entry["metadata"] = route_metadata

        idle = []
        for agent_name in VALID_AGENTS:
            if queue_info and queue_info.get(agent_name, 0) == 0 and not is_agent_busy(agent_name):
                idle.append(agent_name)
        entry["idle_agents"] = idle

        dest_queue = queue_info.get(dest, 0) if queue_info else 0
        thresholds = get_adaptive_thresholds()
        would_overflow = dest_queue >= thresholds['high'] and len(idle) > 0 and dest not in idle
        entry["would_overflow"] = would_overflow

        if original_agent and original_agent != dest:
            entry["load_balanced_from"] = original_agent

        os.makedirs(os.path.dirname(ROUTING_LOG), exist_ok=True)
        with open(ROUTING_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _log_skill_overflow(skill_hint, primary_agent, alternate_agent, primary_depth, reason):
    """Log skill overflow bypass events."""
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
        pass
