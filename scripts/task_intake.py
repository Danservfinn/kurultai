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
from kurultai_ledger import generate_task_id, validate_task_id

# Ogedei failure flag state file (watchdog writes this)
_OGEDEI_WATCHDOG_STATE = LOGS_DIR / "ogedei-watchdog-state.json"

# Valid task file extensions (prevents false positives from intermediate state files)
VALID_TASK_EXTENSIONS = {
    '.md',            # Standard markdown task files
    '.pending.md',    # Pending state
    '.executing.md',  # Currently executing
    '.done.md',       # Completed tasks
    '.failed.md',     # Failed tasks
}

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

# Timeout configuration — imported from canonical source (kurultai_paths.py)
from kurultai_paths import CLAUDE_TIMEOUT as _DEFAULT_TIMEOUT, TIMEOUT_BY_PRIORITY as _TIMEOUT_BY_PRIORITY
from kurultai_paths import SLOW_SKILLS as _SLOW_SKILLS_TIMEOUT

# Single source of truth for system sources (used for routing bypass checks)
_SYSTEM_SOURCES = frozenset({
    "kublai-actions", "ogedei-watchdog", "task-watcher", "routing_audit",
    "reflection", "tick", "tock", "hourly_reflection", "mongke_self_task",
    "cascade_detector", "throughput_anomaly", "stall_detector",
    "action_resolution", "signal_calendar", "redistribution",
    "system-health-check", "task_intake", "queue-audit", "kurultai-monitor",
    "kublai-initiative", "idle-monitor", "kublai-diagnostic", "idle-crisis",
    "idle-prevention", "heartbeat-escalation", "anomaly-scanner",
    "routing-retry", "cron-test", "test-cron", "cron-3hr-test", "cron-3hr-review",
    "signal", "api", "direct-mention", "kurultai-delegate",
    "jochi-debug",
    "daily-task-review",
})


def compute_task_timeout(priority, skill_hint=None):
    """Return effective timeout in seconds for a task, matching agent-task-handler logic."""
    priority_timeout = _TIMEOUT_BY_PRIORITY.get(priority, _DEFAULT_TIMEOUT)
    skill_timeout = _SLOW_SKILLS_TIMEOUT.get(skill_hint, 0) if skill_hint else 0
    return max(priority_timeout, skill_timeout)


def _get_ogedei_failure_flag() -> float:
    """Read ogedei's current failure flag from watchdog state.

    Returns:
        float: Failure flag value (0.0 = healthy, 1.0 = completely failing).
               Returns 0.0 if state file unavailable or missing data.
    """
    try:
        if _OGEDEI_WATCHDOG_STATE.exists():
            with open(_OGEDEI_WATCHDOG_STATE) as f:
                state = json.load(f)
            flags = state.get("agent_failure_flags", {})
            return flags.get("ogedei", 0.0)
    except Exception:
        pass
    return 0.0



# =============================================================================
# Extracted modules (backward-compatible re-exports)
# =============================================================================
from task_domain import (
    DOMAIN_AGENT_COMPATIBILITY, VALID_DOMAINS, SKILL_DOMAIN_MAP,
    DOMAIN_KEYWORDS, classify_task_domain, is_domain_compatible,
    VALID_MODELS_BY_AGENT, validate_agent_model,
    _kw_match, _phrase_match,
)

from task_router import (
    _MENTION_RE, parse_mention, _DISAMBIGUATION,
    route_by_text, detect_skill_hint,
    _PRIMARY_OUTPUT_PATTERNS, _PRIMARY_OUTPUT_ROUTE_MAP, _primary_output_test,
    KUBLAI_SELF_ABSORB_THRESHOLD, KUBLAI_SELF_ABSORB_IDLE_MINUTES,
    KUBLAI_SELF_ABSORB_KEYWORDS, should_kublai_self_absorb,
    _SKILL_OWNER, SKILL_HINTS,
    _update_kublai_dispatch_timestamp,
    _get_kublai_idle_minutes,
)

from task_load_balancer import (
    QUEUE_HIGH_THRESHOLD, QUEUE_CRITICAL_THRESHOLD, QUEUE_LOW_THRESHOLD,
    AGENT_FAILURE_BYPASS_THRESHOLD, AGENT_FAILURE_WINDOW_H, AGENT_FAILURE_MIN_TASKS,
    AGENT_CAPABILITY_MATRIX, OVERFLOW_MAP, CATEGORY_KEYWORDS,
    _NO_OVERFLOW_TARGETS, _SKILL_CAPABLE_ALTERNATES,
    is_agent_busy, get_agent_load, get_queue_depth,
    get_all_agent_queue_depths, calculate_system_load_factor,
    get_adaptive_thresholds, _log_threshold_adjustment,
    get_agent_failure_rate, is_agent_failing, check_agent_credentials,
    find_underutilized_agents, can_handle_task,
    get_capable_alternates, find_skill_capable_alternates,
    should_bypass_skill_lock, find_best_agent_by_load,
    should_redistribute_tasks, get_idle_agents,
    REDISTRIBUTION_TRIGGERS, get_agent_idle_time,
    should_trigger_redistribution,
    get_agent_scores, route_with_queue_penalty,
    find_best_idle_agent, find_overflow_agent,
    _detect_category, _log_overflow, _log_routing_decision, _log_skill_overflow,
    AGENT_DIR, ROUTING_LOG,
)

from alert_deduplication import (
    ALERT_PATTERNS, should_suppress_alert, record_alert_created,
    _extract_topic_keys, normalize_task_filename,
)


MAX_TASK_DEPTH = 3

def has_pending_task(agent, title_prefix, full_title=None):
    """Check if an agent already has an uncompleted task with this title prefix
    or a semantically similar title (>60% keyword overlap).

    FIX 2026-03-12: Exclude .done.md and .failed.md from duplicate detection.
    Only active tasks (.md, .pending.md, .executing.md) should count.
    """
    task_dir = f"{AGENT_DIR}/{agent}/tasks"
    if not os.path.exists(task_dir):
        return False
    topic_keys = _extract_topic_keys(full_title or title_prefix)
    # Filter to only active task extensions (exclude completed/failed)
    active_extensions = ('.md', '.pending.md', '.executing.md')
    for fname in os.listdir(task_dir):
        # Skip completed/failed files and non-task files
        if fname.endswith('.done.md') or fname.endswith('.failed.md'):
            continue
        # Skip files without valid active extensions
        if not any(fname.endswith(ext) for ext in active_extensions if fname.endswith(ext)):
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


CLAUDE_CODE_PREAMBLE = """**EXECUTION METHOD:** Use Claude Code for this task.
Include relevant horde skills in the task description (e.g., /horde-brainstorming, /horde-implement, /horde-review).

"""


def create_task(title, body, priority="normal", source="task_intake",
                depth=0, agent=None, parent_id=None, skip_duplicate_check=False,
                skill_hint=None, force_claude_code=False,
                notify_on_complete=False, notify_channel="signal",
                notify_target=None, bucket=None,
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
        force_claude_code: Prepend Claude Code invocation instruction to body
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
            # v2 graph-based routing (Phase 4 cutover 2026-03-12)
            try:
                from neo4j_v2_router import route_task as _v2_route
                from neo4j_v2_core import TaskStore as _V2Store
                _v2_store = _V2Store()
                agent = _v2_route(_v2_store, title, priority, skill_hint=skill_hint)
                _v2_store.close()
                _route_metadata = {"method": "v2_graph_routing"}
                print(f"  V2_ROUTE: {title[:50]} -> {agent}")
            except Exception as _v2_err:
                print(f"  V2_ROUTE_FALLBACK: {_v2_err}")
                agent, _route_metadata = route_with_queue_penalty(title)
            if agent == "subagent":
                agent = "kublai"  # Default fallback
    else:
        # Caller provided an explicit agent — check if keyword routing disagrees
        # FIX (2026-03-11): Reduce explicit routing by checking keyword matches
        # even when agent is specified, unless it's a system source or direct mention
        _system_sources = _SYSTEM_SOURCES
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
                skill_hint=skill_hint,
                route_metadata={
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

    # 2.5.2b. DOMAIN COMPATIBILITY CHECK (O005 enforcement)
    # Reject tasks routed to agents that cannot handle the classified domain.
    # Prevents the 8-hour stuck task issue where ogedei held a documentation task.
    # System sources and direct mentions bypass this check (they know what they're doing).
    _system_sources = _SYSTEM_SOURCES
    if (_caller_provided_agent and
        source not in _system_sources and
        not mention_agent and
        _task_domain in DOMAIN_AGENT_COMPATIBILITY and
        agent not in DOMAIN_AGENT_COMPATIBILITY[_task_domain]):

        _compatible_agents = DOMAIN_AGENT_COMPATIBILITY[_task_domain]
        _suggested = _compatible_agents[0] if _compatible_agents else "kublai"

        print(f"DOMAIN_MISMATCH: agent='{agent}' cannot handle domain='{_task_domain}'")
        print(f"  Task: '{title[:80]}'")
        print(f"  Compatible agents for {_task_domain}: {', '.join(_compatible_agents)}")
        print(f"  Suggested: {_suggested}")
        print(f"  REJECTING task creation — use agent='{_suggested}' or @mention to override")

        # Log domain mismatch for telemetry
        _log_routing_decision(
            title=title,
            dest=agent,
            method="domain_mismatch_reject",
            domain=_task_domain,
            route_metadata={
                "reject_reason": f"agent {agent} not in domain compatibility list",
                "compatible_agents": _compatible_agents,
                "suggested_agent": _suggested,
                "source": source,
            },
        )

        return None  # Reject task creation

    # 2.5.2c. TITLE-DOMAIN CONFLICT CHECK (skill hint override protection)
    # Detect cases where skill hint overrides a clear title-domain signal.
    # Example: /horde-implement on "Document ESCALATION_PROTOCOL.md" → documentation task
    # misclassified as implementation, then routed to ogedei who can't do docs.
    #
    # FIX 2026-03-12: When domain came from skill hint, only reject if title domain
    # score is significantly higher (2x) than classified domain score. This prevents
    # false rejects on titles with generic words like "create" or "feature" that
    # accidentally score higher for the wrong domain.
    _domain_from_skill_hint = (skill_hint and skill_hint in SKILL_DOMAIN_MAP)

    _title_keywords_domain = None
    _title_lower = title.lower()
    _title_scores = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in _title_lower)
        if score > 0:
            _title_scores[domain] = score

    if _title_scores:
        _title_keywords_domain = max(_title_scores.items(), key=lambda x: x[1])[0]

    # Check if title-based domain conflicts with classified domain
    # AND if the target agent is incompatible with the title-based domain
    _skip_title_conflict_check = False
    if (_title_keywords_domain and
        _title_keywords_domain != _task_domain and
        _title_keywords_domain in DOMAIN_AGENT_COMPATIBILITY and
        agent not in DOMAIN_AGENT_COMPATIBILITY[_title_keywords_domain]):

        # When domain came from skill hint, require 2x score threshold to reject
        # This filters out weak conflicts from generic keywords while protecting
        # against clear mismatches (e.g., /horde-implement on "Document X")
        if _domain_from_skill_hint:
            _classified_score = _title_scores.get(_task_domain, 0)
            _conflict_score = _title_scores.get(_title_keywords_domain, 0)
            # Only reject if conflict score is MORE than 2x higher (strong signal)
            # Special case: if classified domain has 0 matches but conflict has >0,
            # the skill hint is clearly wrong - reject to prevent misrouting.
            if _classified_score == 0 and _conflict_score > 0:
                # Skill hint domain has no keyword support in title - reject
                print(f"TITLE_DOMAIN_CONFLICT: skill hint domain '{_task_domain}' has 0 keyword matches, title suggests '{_title_keywords_domain}' (score {_conflict_score})")
                # Fall through to reject below
            elif _conflict_score <= 2 * max(_classified_score, 1):
                print(f"TITLE_DOMAIN_CONFLICT: skipped (weak conflict: {_conflict_score} vs {_classified_score}, domain from skill hint)")
                _skip_title_conflict_check = True  # Skip rejection, allow task through

        if not _skip_title_conflict_check:
            _compatible_for_title = DOMAIN_AGENT_COMPATIBILITY[_title_keywords_domain]
            _suggested_for_title = _compatible_for_title[0] if _compatible_for_title else "kublai"

            print(f"TITLE_DOMAIN_CONFLICT: title suggests '{_title_keywords_domain}' but classified as '{_task_domain}'")
            print(f"  Task: '{title[:80]}'")
            print(f"  Title keywords point to: {_title_keywords_domain}")
            print(f"  Classified as: {_task_domain} (from skill hint: {skill_hint})")
            print(f"  Target agent '{agent}' is incompatible with title-domain '{_title_keywords_domain}'")
            print(f"  Compatible agents for {_title_keywords_domain}: {', '.join(_compatible_for_title)}")
            print(f"  REJECTING task creation — this appears to be a {_title_keywords_domain} task")
            print(f"  Suggested: use agent='{_suggested_for_title}' or remove skill hint to rely on title keywords")

            # Log title-domain conflict for telemetry
            _log_routing_decision(
                title=title,
                dest=agent,
                method="title_domain_conflict_reject",
                domain=_title_keywords_domain,
                route_metadata={
                    "reject_reason": f"title suggests {_title_keywords_domain} but classified as {_task_domain}",
                    "title_domain": _title_keywords_domain,
                    "classified_domain": _task_domain,
                    "skill_hint": skill_hint,
                    "compatible_agents": _compatible_for_title,
                    "suggested_agent": _suggested_for_title,
                    "source": source,
                },
            )

            return None  # Reject task creation

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
    _dispatch_agents = ["temujin", "mongke", "chagatai", "jochi", "ogedei"]
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

        return None

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

    # REDUCE EXPLICIT ROUTING (2026-03-11): Even for explicitly-routed tasks,
    # check if keyword routing strongly disagrees. This reduces the 81% explicit
    # routing rate by catching misroutes before they happen.
    # 
    # Only skip keyword override for:
    # 1. Direct @mentions (user explicitly chose agent)
    # 2. System sources that require specific agents (watchdog, health checks)
    # 3. Tasks with skill hints that lock to specific agents
    _system_sources_requiring_explicit = _SYSTEM_SOURCES
    _is_system_source = source in _system_sources_requiring_explicit

    # Load balancing applies to:
    # - Auto-routed tasks (not _caller_provided_agent)
    # - OR explicitly-routed tasks from non-system sources where keyword routing disagrees
    load_balance_needed = (
        agent not in ("kublai", "subagent")
        and not mention_agent
        and not _skill_locked_agent
        and (
            not _caller_provided_agent  # Auto-routed: always load-balance
            or (not _is_system_source and original_depth >= _lb_thresholds['high'])  # Explicit from non-system: only if overloaded
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

                        return None
                    else:
                        # CIRCULAR FAILURE CASCADE PREVENTION (2026-03-12)
                        # Check if ogedei is already failing before routing CRITICAL tasks to it
                        # This breaks the circular cascade: ogedei fails → CRITICAL task → ogedei
                        _ogedei_failure = _get_ogedei_failure_flag()
                        _OGEDEI_FAILURE_THRESHOLD = 0.5  # Exclude ogedei at 50%+ failure rate

                        if _ogedei_failure >= _OGEDEI_FAILURE_THRESHOLD:
                            # ogedei is failing — route CRITICAL task to jochi instead
                            print(f"  CIRCULAR CASCADE PREVENTION: ogedei failure flag={_ogedei_failure:.2f} >= {_OGEDEI_FAILURE_THRESHOLD}")
                            print(f"  Routing CRITICAL escalation to jochi instead of ogedei to break cascade")
                            _escalation_target = "jochi"
                        else:
                            # ogedei is healthy — can receive escalation
                            print(f"  Creating CRITICAL escalation for ogedei to fix credentials")
                            _escalation_target = "ogedei"

                        # Create escalation task for the determined target
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
                        # Create task file directly in target agent's queue
                        _target_queue = AGENTS_DIR / _escalation_target / "tasks"
                        _target_queue.mkdir(parents=True, exist_ok=True)
                        _esc_id = f"cred-fail-{int(time.time())}"
                        _esc_file = _target_queue / f"{_esc_id}.md"
                        _esc_file.write_text(f"# {_escalation_title}\n\n{_escalation_body}")
                        print(f"  ESCALATION created: {_esc_file.name} -> {_escalation_target}")
                        return None

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
            route_metadata={"reason": suppress_reason},
        )
        return None

    # 3.5. Duplicate check (exact prefix + fuzzy keyword overlap)
    if not skip_duplicate_check:
        prefix = title[:40]
        if has_pending_task(agent, prefix, full_title=title):
            print(f"SKIP: duplicate task for {agent}: '{title[:60]}'")
            return None

    # 4-5. Create in Neo4j + filesystem
    # Derive notify_target from origin_initiator when it's a phone number
    if notify_target is None:
        if origin_initiator and origin_initiator.startswith("+"):
            notify_target = origin_initiator
        else:
            notify_target = "+19194133445"

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
        # FIX 2026-03-14: Verify task file persisted to disk before reporting success
        _task_file = agent_tasks_dir(agent) / f"{task_id}.md"
        if not _task_file.exists():
            print(f"WARNING: Task file not persisted to disk for {task_id} (expected: {_task_file})")
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
        # FIX 2026-03-14: Call directly — function is imported at module level (line 128)
        if agent == "kublai":
            _update_kublai_dispatch_timestamp()
        # Record alert for deduplication tracking
        record_alert_created(agent, title, source, task_id)

        # v2: set v2 properties on Neo4j node (Phase 4 cutover 2026-03-12)
        # FIX 2026-03-14: Use context manager to close session and prevent connection pool leak
        try:
            _domain = classify_task_domain(title, skill_hint)
            _timeout = compute_task_timeout(priority, skill_hint)
            with tracker.driver.session() as _session:
                _session.run("""
                    MATCH (t:Task {task_id: $id})
                    SET t.v2_eligible = true,
                        t.assigned_to = t.agent,
                        t.prompt = $body,
                        t.domain = $domain,
                        t.claim_epoch = 0,
                        t.claimed_by = null,
                        t.lease_expires_at = null,
                        t.timeout_s = $timeout,
                        t.created_at = coalesce(t.created_at, t.created),
                        t.started_at = null,
                        t.completed_at = null,
                        t.updated_at = datetime()
                """, id=task_id, body=body, domain=_domain, timeout=_timeout)
        except Exception as e:
            print(f"  V2_FLAG_WARN: Could not set v2 properties on {task_id}: {e}")

        return task_id
    except Exception as e:
        # REMOVED: Filesystem-only fallback (2026-03-11)
        # Neo4j is the source of truth. If Neo4j is unavailable, task creation
        # MUST fail rather than create filesystem-only tasks that cause
        # reconciliation issues and orphan cleanup race conditions.
        print(f"ERROR: Neo4j unavailable — task creation FAILED: {e}")
        print("ACTION REQUIRED: Check Neo4j connectivity before retrying.")
        raise


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Task Intake — single entry point for task creation")
    parser.add_argument("--title", required=False, help="Task title")
    parser.add_argument("--body", default="", help="Task body")
    parser.add_argument("--priority", default="normal", choices=["high", "normal", "low"])
    parser.add_argument("--agent", default=None, help="Target agent (auto-routed if omitted)")
    parser.add_argument("--source", default="cli", help="Task source")
    parser.add_argument("--skill-hint", default=None, help="Explicit skill hint (overrides auto-detection)")
    parser.add_argument("--force-claude-code", action="store_true", help="Prepend Claude Code invocation instruction")
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
            load = loads.get(agent, {'pending': 0, 'executing': 0})
            depth = depths.get(agent, 0)
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
